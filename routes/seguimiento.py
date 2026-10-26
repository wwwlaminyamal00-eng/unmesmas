# routes/seguimiento.py - Seguimiento comercial (pedido de Erika, 21/10/2026 23:30)
#
# Qué hace (en simple), todo con los datos de Ventas:
#   1. Cotizaciones sin cerrar: las que ya se mandaron al cliente (Generada / Enviada) y no tienen respuesta.
#      Cada una tiene su "próxima llamada": la que se programó al llamar, o si nunca se llamó,
#      3 días después de hecha. Lo que toca hoy o está atrasado sale en rojo.
#   2. Registrar llamada: medio (llamada, WhatsApp, correo, visita), qué dijo el cliente y cuándo volver a llamar.
#      Si el cliente dijo que no, se marca "No compró" con motivo (la cotización en Ventas no cambia).
#   3. Tasa de cierre por vendedora: de lo cotizado en el periodo, cuánto se ganó (aceptada o con PV),
#      cuánto se perdió y cuánto sigue abierto, en cantidad y en soles.
#   4. Historial de gestiones: cada llamada con usuario y fecha y hora de Lima.
#
# Reglas:
#   - Una cotización está "ganada" si está aceptada por el cliente, facturada o tiene un PV.
#   - "Perdida" si Ventas la rechazó o si aquí se marcó "No compró". Las anuladas no cuentan.
#   - Acceso: administrador o quien tenga "Ver" en "Seguimiento comercial".
import re
import threading
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from flask import Blueprint, render_template, request, jsonify, session

from database import db_query, db_tx
from utils import a_decimal, redondear, es_admin, id_empresa
from routes.multiempresa import empresas as lista_empresas, empresa_actual, empresa_por_id

seguimiento_bp = Blueprint('seguimiento', __name__)


def _ahora():
    """Fecha y hora de Lima (el servidor de Render está en UTC)."""
    return datetime.now(ZoneInfo('America/Lima')).replace(tzinfo=None)


CERO = Decimal('0')
DIAS_PRIMERA_LLAMADA = 3
MEDIOS = ('Llamada', 'WhatsApp', 'Correo', 'Visita')
ENVIADAS = ('Generada', 'Enviada')
GANADAS = ('Aceptada por Cliente', 'Aceptada', 'Facturada')
INTERNAS = ('Borrador', 'En revisión', 'Por validar', 'Validado por Hellen', 'Validada', 'Validado')
MOTIVOS_PERDIDA = ('Precio alto', 'Compró a otro proveedor', 'Tiempo de entrega', 'Ya no lo necesita', 'No responde', 'Otro')


class ErrorSeguimiento(Exception):
    pass


# ============================================================
# PERMISO (en el servidor)
# ============================================================
def puede_ver_seguimiento():
    if es_admin():
        return True
    try:
        from routes.acceso import acceso_usuario
        acc = acceso_usuario()
    except Exception:
        return False
    return bool(acc.get('configurado') and 'seguimiento' in acc.get('modulos', set()))


@seguimiento_bp.before_request
def _proteger():
    if 'usuario_id' not in session:
        return None
    if not puede_ver_seguimiento():
        msg = ('No tienes permiso para entrar a Seguimiento comercial. Pídele al administrador el permiso '
               '"Seguimiento" en Configuración ▸ Usuarios y permisos.')
        if '/api/' in request.path:
            return jsonify({'success': False, 'error': msg, 'codigo': 'sin_permiso'}), 403
        from flask import flash, redirect, url_for
        flash(msg, 'error')
        return redirect(url_for('index'))
    asegurar_tablas()
    return None


# ============================================================
# TABLA PROPIA (equivalente: migrations/022_seguimiento_comercial.sql)
# ============================================================
SQL_DDL_SEGUIMIENTO = """
    CREATE TABLE IF NOT EXISTS ventas_seguimiento (
        id SERIAL PRIMARY KEY,
        cotizacion_id INTEGER NOT NULL,
        empresa_id VARCHAR(64),
        medio VARCHAR(20) NOT NULL,
        comentario TEXT NOT NULL,
        proxima_llamada DATE,
        cierre VARCHAR(15) CHECK (cierre IN ('No compró')),
        motivo_cierre VARCHAR(60),
        creado_por VARCHAR(150),
        creado_en TIMESTAMP DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_ventas_seguimiento_cot ON ventas_seguimiento (cotizacion_id, creado_en);
    ALTER TABLE ventas_seguimiento ENABLE ROW LEVEL SECURITY;
"""
_tablas = {'ok': False}
_lock = threading.Lock()


def asegurar_tablas():
    if _tablas['ok']:
        return
    with _lock:
        if _tablas['ok']:
            return
        with db_tx() as conn:
            cur = conn.cursor()
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('seguimiento_ddl'))")
            cur.execute(SQL_DDL_SEGUIMIENTO)
        _tablas['ok'] = True


# ============================================================
# AYUDAS
# ============================================================
def _usuario():
    return session.get('nombre_completo') or session.get('usuario') or f"Usuario {session.get('usuario_id')}"


def _n(v):
    return float(redondear(v or 0, 2))


def _f(v):
    if isinstance(v, datetime):
        return v.strftime('%Y-%m-%d %H:%M')
    if isinstance(v, date):
        return v.isoformat()
    return v


def _empresa(eid_txt):
    """None = todas las empresas."""
    if eid_txt in (None, '', 'todas'):
        return None
    eid = id_empresa(eid_txt)
    e = empresa_por_id(eid) if eid else None
    if not e:
        raise ErrorSeguimiento('Empresa no encontrada.')
    return e


def dias_vigencia(txt):
    """'15 días' -> 15; '1 mes' -> 30; vacío o sin número -> None."""
    t = (txt or '').lower()
    m = re.search(r'(\d+)', t)
    if not m:
        return None
    n = int(m.group(1))
    if 'mes' in t:
        n *= 30
    elif 'semana' in t:
        n *= 7
    return n if 0 < n <= 365 else None


def _pc_por_cotizacion(ids):
    if not ids:
        return {}
    filas = db_query("""SELECT cotizacion_id, string_agg(numero, ', ' ORDER BY id) AS numeros FROM pedido_compra_pc
                        WHERE cotizacion_id = ANY(%s) AND COALESCE(estado, '') NOT ILIKE 'anulad%%'
                        GROUP BY cotizacion_id""", (list(ids),))
    return {r['cotizacion_id']: r['numeros'] for r in filas}


def _productos(ids):
    """Cantidad y nombre de cada producto de la cotización, en el orden en que se cotizaron."""
    if not ids:
        return {}
    filas = db_query("""SELECT d.cotizacion_id, d.cantidad, COALESCE(NULLIF(TRIM(p.descripcion), ''), 'Producto sin nombre') AS descripcion
                        FROM cotizacion_detalle d LEFT JOIN productos p ON p.id = d.producto_id
                        WHERE d.cotizacion_id = ANY(%s) ORDER BY d.cotizacion_id, d.id""", (list(ids),))
    salida = {}
    for r in filas:
        salida.setdefault(r['cotizacion_id'], []).append({'cantidad': _n(r['cantidad']), 'descripcion': r['descripcion']})
    return salida


def _gestiones(ids):
    if not ids:
        return {}
    filas = db_query("SELECT * FROM ventas_seguimiento WHERE cotizacion_id = ANY(%s) ORDER BY creado_en, id", (list(ids),))
    salida = {}
    for r in filas:
        salida.setdefault(r['cotizacion_id'], []).append(r)
    return salida


def cotizaciones(e, desde=None, hasta=None):
    """Cotizaciones de la empresa (o de todas) con su situación comercial calculada."""
    cond, params = ["c.estado <> 'Anulada'"], []
    if e:
        cond.append('(c.empresa_id IS NULL OR c.empresa_id::text = %s)')
        params.append(str(e['id']))
    if desde:
        cond.append('c.fecha_creacion >= %s')
        params.append(desde)
    if hasta:
        cond.append('c.fecha_creacion < %s')
        params.append(hasta + timedelta(days=1))
    filas = db_query(f"""
        SELECT c.id, c.numero_cotizacion, c.codigo_cotizacion, c.estado, c.fecha_creacion, c.total, c.validez_oferta,
               c.fecha_aceptacion, c.contacto_cliente, c.telefono_cliente, c.email_cliente, c.empresa_id::text AS empresa_id,
               COALESCE(NULLIF(TRIM(c.vendedor), ''), u.nombre_completo, u.usuario, 'Sin vendedora') AS vendedor,
               cl.razon_social AS cliente, cl.numero_documento AS ruc,
               cl.telefono_contacto AS telefono_maestro, cl.nombre_contacto AS contacto_maestro
        FROM cotizaciones c
        LEFT JOIN clientes cl ON cl.id = c.cliente_id
        LEFT JOIN usuarios u ON u.id = c.usuario_id
        WHERE {' AND '.join(cond)}
        ORDER BY c.fecha_creacion DESC, c.id DESC""", tuple(params))
    ids = [f['id'] for f in filas]
    pcs = _pc_por_cotizacion(ids)
    ges = _gestiones(ids)
    prods = _productos(ids)
    hoy = _ahora().date()
    codigos = {str(x['id']): x['codigo'] for x in lista_empresas()}
    salida = []
    for f in filas:
        g = ges.get(f['id'], [])
        ult = g[-1] if g else None
        cerrada_aqui = next((x for x in reversed(g) if x['cierre']), None)
        pc = pcs.get(f['id'])
        if f['estado'] in GANADAS or pc:
            situacion = 'Ganada'
        elif f['estado'] == 'Rechazada' or cerrada_aqui:
            situacion = 'Perdida'
        elif f['estado'] in ENVIADAS:
            situacion = 'Abierta'
        else:
            situacion = 'Por enviar'
        creada = f['fecha_creacion'].date() if f['fecha_creacion'] else hoy
        dv = dias_vigencia(f['validez_oferta'])
        vence = creada + timedelta(days=dv) if dv else None
        proxima = None
        if situacion == 'Abierta':
            programada = next((x['proxima_llamada'] for x in reversed(g) if x['proxima_llamada']), None)
            proxima = programada or (creada + timedelta(days=DIAS_PRIMERA_LLAMADA))
            if ult and not programada:
                proxima = ult['creado_en'].date() + timedelta(days=7)
        salida.append({
            'id': f['id'], 'numero': f['codigo_cotizacion'] or f['numero_cotizacion'], 'estado': f['estado'],
            'empresa': codigos.get(f['empresa_id'] or '', ''), 'vendedor': f['vendedor'],
            'cliente': f['cliente'] or 'Sin cliente', 'ruc': f['ruc'],
            'contacto': f['contacto_cliente'] or f['contacto_maestro'], 'telefono': f['telefono_cliente'] or f['telefono_maestro'],
            'email': f['email_cliente'], 'fecha': _f(creada), 'total': _n(f['total']), 'situacion': situacion,
            'pc': pc, 'dias': (hoy - creada).days, 'vence': _f(vence), 'vencida': bool(vence and vence < hoy),
            'proxima_llamada': _f(proxima), 'llamar_hoy': bool(proxima and proxima <= hoy),
            'atraso': (hoy - proxima).days if proxima and proxima < hoy else 0,
            'gestiones': len(g), 'productos': prods.get(f['id'], []),
            'ultima': {'medio': ult['medio'], 'comentario': ult['comentario'], 'por': ult['creado_por'],
                       'en': _f(ult['creado_en'])} if ult else None,
            'motivo_perdida': (cerrada_aqui['motivo_cierre'] if cerrada_aqui else None) or (
                'Rechazada en Ventas' if f['estado'] == 'Rechazada' else None),
            'dias_cierre': (f['fecha_aceptacion'].date() - creada).days if f['fecha_aceptacion'] and situacion == 'Ganada' else None,
        })
    return salida


def tasa_de_cierre(lista):
    """Por vendedora: enviadas (sin contar las internas), ganadas, perdidas, abiertas, tasa y montos."""
    grupos = {}
    for c in lista:
        if c['situacion'] == 'Por enviar':
            continue
        g = grupos.setdefault(c['vendedor'], {'vendedor': c['vendedor'], 'enviadas': 0, 'ganadas': 0, 'perdidas': 0,
                                              'abiertas': 0, 'monto_enviado': CERO, 'monto_ganado': CERO, 'dias': []})
        g['enviadas'] += 1
        g['monto_enviado'] += a_decimal(c['total'])
        if c['situacion'] == 'Ganada':
            g['ganadas'] += 1
            g['monto_ganado'] += a_decimal(c['total'])
            if c['dias_cierre'] is not None:
                g['dias'].append(c['dias_cierre'])
        elif c['situacion'] == 'Perdida':
            g['perdidas'] += 1
        else:
            g['abiertas'] += 1
    salida = []
    for g in sorted(grupos.values(), key=lambda x: -x['monto_ganado']):
        salida.append({**g, 'tasa': round(g['ganadas'] * 100 / g['enviadas'], 2) if g['enviadas'] else 0.0,
                       'monto_enviado': _n(g['monto_enviado']), 'monto_ganado': _n(g['monto_ganado']),
                       'dias': round(sum(g['dias']) / len(g['dias']), 1) if g['dias'] else None})
    return salida


def por_mes(lista, hoy=None):
    hoy = hoy or _ahora().date()
    meses = []
    a, m = hoy.year, hoy.month
    for _ in range(6):
        meses.append(f'{a:04d}-{m:02d}')
        a, m = (a, m - 1) if m > 1 else (a - 1, 12)
    salida = {p: {'periodo': p, 'enviadas': 0, 'ganadas': 0, 'perdidas': 0, 'monto_ganado': CERO} for p in meses}
    for c in lista:
        p = c['fecha'][:7]
        if p in salida and c['situacion'] != 'Por enviar':
            s = salida[p]
            s['enviadas'] += 1
            if c['situacion'] == 'Ganada':
                s['ganadas'] += 1
                s['monto_ganado'] += a_decimal(c['total'])
            elif c['situacion'] == 'Perdida':
                s['perdidas'] += 1
    return [{**s, 'monto_ganado': _n(s['monto_ganado']),
             'tasa': round(s['ganadas'] * 100 / s['enviadas'], 2) if s['enviadas'] else None} for s in salida.values()]


def resumen(e, dias_periodo=90):
    hoy = _ahora().date()
    todas = cotizaciones(e)
    desde = hoy - timedelta(days=dias_periodo)
    periodo = [c for c in todas if c['fecha'] >= desde.isoformat()]
    abiertas = sorted([c for c in todas if c['situacion'] == 'Abierta'], key=lambda c: (c['proxima_llamada'] or '', -c['total']))
    por_enviar = [c for c in todas if c['situacion'] == 'Por enviar']
    vendedoras = tasa_de_cierre(periodo)
    env = sum(v['enviadas'] for v in vendedoras)
    gan = sum(v['ganadas'] for v in vendedoras)
    mes = hoy.strftime('%Y-%m')
    return {
        'hoy': hoy.isoformat(), 'dias_periodo': dias_periodo, 'desde': desde.isoformat(),
        'abiertas': abiertas, 'por_enviar': por_enviar,
        'kpis': {
            'abiertas': len(abiertas), 'monto_abierto': _n(sum((a_decimal(c['total']) for c in abiertas), CERO)),
            'llamar_hoy': sum(1 for c in abiertas if c['llamar_hoy']),
            'atrasadas': sum(1 for c in abiertas if c['atraso'] > 0),
            'vencidas': sum(1 for c in abiertas if c['vencida']),
            'tasa': round(gan * 100 / env, 2) if env else None, 'enviadas': env, 'ganadas': gan,
            'ganado_mes': _n(sum((a_decimal(c['total']) for c in todas if c['situacion'] == 'Ganada' and c['fecha'][:7] == mes), CERO)),
            'por_enviar': len(por_enviar),
        },
        'vendedoras': vendedoras, 'meses': por_mes(todas, hoy),
        'perdidas': [c for c in periodo if c['situacion'] == 'Perdida'],
    }


def registrar_gestion(cot_id, d):
    medio = d.get('medio')
    if medio not in MEDIOS:
        raise ErrorSeguimiento('Elige cómo lo contactaste: llamada, WhatsApp, correo o visita.')
    comentario = (d.get('comentario') or '').strip()
    if len(comentario) < 3:
        raise ErrorSeguimiento('Escribe qué dijo el cliente.')
    comentario = comentario[0].upper() + comentario[1:]
    cierre = 'No compró' if d.get('no_compro') else None
    motivo = None
    proxima = None
    hoy = _ahora().date()
    if cierre:
        motivo = d.get('motivo_cierre')
        if motivo not in MOTIVOS_PERDIDA:
            raise ErrorSeguimiento('Elige por qué no compró.')
    else:
        txt = (d.get('proxima_llamada') or '').strip()[:10]
        if not txt:
            raise ErrorSeguimiento('Elige cuándo volver a llamar.')
        try:
            proxima = datetime.strptime(txt, '%Y-%m-%d').date()
        except ValueError:
            raise ErrorSeguimiento('La fecha de la próxima llamada no es válida.')
        if proxima < hoy:
            raise ErrorSeguimiento('La próxima llamada no puede ser en el pasado.')
        if proxima > hoy + timedelta(days=120):
            raise ErrorSeguimiento('La próxima llamada debe ser en los próximos 4 meses.')
    with db_tx() as conn:
        cur = conn.cursor()
        cur.execute("SELECT estado, empresa_id::text FROM cotizaciones WHERE id = %s FOR UPDATE", (cot_id,))
        fila = cur.fetchone()
        if not fila:
            raise ErrorSeguimiento('Cotización no encontrada.')
        if fila[0] not in ENVIADAS:
            raise ErrorSeguimiento(f'Esta cotización está "{fila[0]}": solo se hace seguimiento a las que ya se mandaron al cliente.')
        cur.execute("SELECT 1 FROM ventas_seguimiento WHERE cotizacion_id = %s AND cierre IS NOT NULL", (cot_id,))
        if cur.fetchone():
            raise ErrorSeguimiento('Esta cotización ya se marcó como "No compró".')
        cur.execute("""INSERT INTO ventas_seguimiento (cotizacion_id, empresa_id, medio, comentario, proxima_llamada, cierre,
                       motivo_cierre, creado_por, creado_en) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (cot_id, fila[1], medio, comentario[:1000], proxima, cierre, motivo, _usuario(), _ahora()))
    return cierre


def historial(e, limite=300):
    cond, params = '', []
    if e:
        cond = 'WHERE (s.empresa_id IS NULL OR s.empresa_id = %s)'
        params.append(str(e['id']))
    filas = db_query(f"""
        SELECT s.*, COALESCE(c.codigo_cotizacion, c.numero_cotizacion) AS numero, cl.razon_social AS cliente,
               cl.numero_documento AS ruc
        FROM ventas_seguimiento s
        LEFT JOIN cotizaciones c ON c.id = s.cotizacion_id
        LEFT JOIN clientes cl ON cl.id = c.cliente_id
        {cond} ORDER BY s.creado_en DESC, s.id DESC LIMIT {int(limite)}""", tuple(params))
    return [{k: _f(v) for k, v in r.items()} for r in filas]


# ============================================================
# RUTAS
# ============================================================
def _err(ex, codigo=400):
    return jsonify({'success': False, 'error': str(ex)}), codigo


@seguimiento_bp.route('/seguimiento')
def pagina():
    emps = [{'id': x['id'], 'codigo': x['codigo']} for x in lista_empresas()]
    activa = empresa_actual()
    return render_template('seguimiento.html', empresas=emps, empresa_activa=activa['id'] if activa else None,
                           medios=MEDIOS, motivos=MOTIVOS_PERDIDA)


@seguimiento_bp.route('/seguimiento/api/resumen')
def api_resumen():
    try:
        e = _empresa(request.args.get('empresa_id'))
        try:
            dias = int(request.args.get('dias') or 90)
        except ValueError:
            dias = 90
        dias = dias if dias in (30, 90, 180, 365) else 90
        return jsonify({'success': True, 'data': resumen(e, dias)})
    except ErrorSeguimiento as ex:
        return _err(ex)


@seguimiento_bp.route('/seguimiento/api/cotizacion/<int:cot_id>/gestiones')
def api_gestiones(cot_id):
    filas = db_query("SELECT * FROM ventas_seguimiento WHERE cotizacion_id = %s ORDER BY creado_en DESC, id DESC", (cot_id,))
    return jsonify({'success': True, 'data': [{k: _f(v) for k, v in r.items()} for r in filas]})


@seguimiento_bp.route('/seguimiento/api/cotizacion/<int:cot_id>/gestion', methods=['POST'])
def api_registrar(cot_id):
    try:
        cierre = registrar_gestion(cot_id, request.get_json(silent=True) or {})
        return jsonify({'success': True, 'message': 'Marcada como "No compró".' if cierre else 'Llamada registrada.'})
    except ErrorSeguimiento as ex:
        return _err(ex)


@seguimiento_bp.route('/seguimiento/api/historial')
def api_historial():
    try:
        return jsonify({'success': True, 'data': historial(_empresa(request.args.get('empresa_id')))})
    except ErrorSeguimiento as ex:
        return _err(ex)
