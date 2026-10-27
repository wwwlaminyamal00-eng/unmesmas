"""
Notas de crédito con aprobación (REGLA DE ORO de Erika, 26/10/2026).

Riesgo que se cierra: un colaborador coludido con un cliente emite una nota de crédito y la factura "ya no se debe".
- SOLO Hellen (USUARIOS_NOTA_CREDITO, por defecto hel02kcf) crea, corrige y envía notas de crédito.
- SOLO Erika (USUARIOS_REPORTES, por defecto eri01kcf) aprueba o rechaza. Nadie más, ni el administrador.
- El monto NUNCA se escribe: sale de la factura (anulación / devolución total = saldo), de las cantidades devueltas
  (devolución por ítem, al precio de la factura) o del % de descuento global. Nunca supera el saldo de la factura.
- La trazabilidad se llena sola desde la factura: fecha, guía, PV, PC (Pedido del cliente) y cotización.
- "Observaciones" sale en el documento; la "Nota interna" (causa, responsable del error y detalle) nunca.
- Solo cuenta en Cuentas por cobrar, Reportes y SUNAT cuando Erika la aprueba (estado "Emitida").
Migración 034 (en la base de pruebas las columnas y la tabla de evidencias se crean aquí).
"""
import json
import os
import threading
from datetime import datetime

from flask import Blueprint, jsonify, request, session, render_template, Response

from database import db_query, db_tx
from psycopg2.extras import RealDictCursor
from utils import a_decimal, redondear, tasa_igv, es_duena_reportes, _lista_env
from routes.auditoria import registrar_auditoria
from routes.multiempresa import filtro_sql, empresa_para_crear, marcar_empresa

nota_credito_bp = Blueprint('nota_credito', __name__)

USUARIOS_NOTA_CREDITO = _lista_env('USUARIOS_NOTA_CREDITO', 'hel02kcf')

# Catálogo 09 de SUNAT: solo los tipos cuyo monto el ERP puede calcular sin que nadie lo escriba
TIPOS_NOTA = {
    '01': 'Anulación de la operación',
    '02': 'Anulación por error en el RUC',
    '04': 'Descuento global',
    '06': 'Devolución total',
    '07': 'Devolución por ítem',
}
TIPOS_TOTAL = ('01', '02', '06')
TIPOS_DEVOLUCION = ('06', '07')
CAUSAS = ('Error operativo', 'Pedido del cliente', 'Devolución', 'Descuento comercial', 'Otro')
EDITABLES = ('Borrador', 'Por aprobar', 'Rechazada')
NO_CUENTAN = ('ANULADA', 'ANULADO', 'RECHAZADA')   # para el saldo: lo rechazado o anulado no resta
TIPOS_EVIDENCIA = {'.pdf': 'application/pdf', '.xml': 'application/xml', '.zip': 'application/zip',
                   '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.eml': 'message/rfc822',
                   '.msg': 'application/vnd.ms-outlook'}
MAX_EVIDENCIA = 5 * 1024 * 1024

SQL_DDL_NC = """
    ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS tipo_nota VARCHAR(2);
    ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS sustento TEXT;
    ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS nota_interna TEXT;
    ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS causa_interna VARCHAR(40);
    ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS responsable_error VARCHAR(120);
    ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS comprobante_id INTEGER;
    ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS factura_fecha DATE;
    ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS guia_numero VARCHAR(40);
    ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS pv_numero VARCHAR(40);
    ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS pc_cliente VARCHAR(60);
    ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS cotizacion_numero VARCHAR(40);
    ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS guia_devolucion VARCHAR(60);
    ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS porcentaje NUMERIC(6,2);
    ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS items_json JSONB;
    ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS subtotal NUMERIC(14,2);
    ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS igv NUMERIC(14,2);
    ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS moneda VARCHAR(3);
    ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS creado_por_usuario VARCHAR(60);
    ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS enviado_por VARCHAR(60);
    ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS enviado_en TIMESTAMP;
    ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS aprobado_por VARCHAR(60);
    ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS aprobado_en TIMESTAMP;
    ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS motivo_rechazo TEXT;
    CREATE TABLE IF NOT EXISTS nota_credito_archivos (
        id SERIAL PRIMARY KEY,
        nota_id INTEGER NOT NULL,
        nombre VARCHAR(150) NOT NULL,
        mime VARCHAR(80) NOT NULL,
        datos BYTEA NOT NULL,
        bytes INTEGER NOT NULL,
        subido_por VARCHAR(80),
        created_at TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'America/Lima'));
    CREATE INDEX IF NOT EXISTS idx_nota_credito_archivos_nota ON nota_credito_archivos (nota_id)
"""

_listo = False
_lock = threading.Lock()


def asegurar_nota_credito():
    """Columnas nuevas de notas_credito y la tabla de evidencias. No borra nada."""
    global _listo
    if _listo:
        return
    with _lock:
        if _listo:
            return
        with db_tx() as conn:
            cur = conn.cursor()
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('nota_credito_ddl'))")
            for s in (x.strip() for x in SQL_DDL_NC.split(';')):
                if s:
                    cur.execute(s)
        _listo = True


class ErrorNota(Exception):
    def __init__(self, mensaje, codigo=400):
        super().__init__(mensaje)
        self.codigo = codigo


def usuario_actual():
    return (session.get('usuario') or '').strip().lower()


def puede_crear():
    return usuario_actual() in USUARIOS_NOTA_CREDITO


def puede_aprobar():
    return es_duena_reportes()


def _ahora_lima():
    from routes.exportar import ahora_lima
    return ahora_lima().replace(tzinfo=None)


# ------------------------------------------------------------------ factura de origen
def _buscar_factura(ref):
    """Factura por id o por "SERIE-NÚMERO" (con o sin ceros), solo de la empresa elegida."""
    ref = str(ref or '').strip()
    if not ref:
        return None
    sql_emp, par_emp = filtro_sql('empresa_id')
    if ref.isdigit() and '-' not in ref:
        filas = db_query("SELECT * FROM comprobantes WHERE id = %s" + sql_emp, (int(ref),) + par_emp)
    else:
        filas = db_query("""
            SELECT * FROM comprobantes
            WHERE ((serie || '-' || numero::text) = %s OR (serie || '-' || LTRIM(numero::text, '0')) = %s
                OR (serie || '-' || LPAD(numero::text, 8, '0')) = %s)""" + sql_emp + """
            ORDER BY id DESC LIMIT 1""", (ref,) * 3 + par_emp)
    return filas[0] if filas else None


def _doc(comp):
    return f"{comp.get('serie') or ''}-{str(comp.get('numero') or '').zfill(8)}"


def _refs(comp):
    return [_doc(comp), f"{comp.get('serie')}-{comp.get('numero')}",
            f"{comp.get('serie')}-{str(comp.get('numero') or '').lstrip('0')}"]


def _items_factura(comp):
    try:
        items = comp.get('items_json')
        items = json.loads(items) if isinstance(items, str) else (items or [])
    except (TypeError, ValueError):
        items = []
    salida = []
    for i, it in enumerate(items if isinstance(items, list) else []):
        if not isinstance(it, dict):
            continue
        cant = a_decimal(it.get('cantidad') or 0)
        valor = a_decimal(it.get('valorVenta', it.get('precio_venta_con_descuento', it.get('precio_unitario', 0))) or 0)
        salida.append({'idx': i, 'codigo': it.get('codigo') or '', 'producto': it.get('producto') or it.get('descripcion') or '',
                       # 27/10/2026 (caso Komatsu): cómo lo pide el cliente, igual que en la factura
                       'descripcion_cliente': (it.get('descripcion_cliente') or '').strip(),
                       'codigo_cliente': (it.get('codigo_cliente') or '').strip(),
                       'um': it.get('um') or 'NIU', 'cantidad': float(cant), 'valor_unitario': float(redondear(valor)),
                       'total': float(redondear(cant * valor * (1 + tasa_igv())))})
    return salida


def _saldo(comp, excluir_id=None):
    refs = _refs(comp)
    filas = db_query("""SELECT COALESCE(SUM(monto), 0) AS t FROM notas_credito
                        WHERE (comprobante_id = %s OR comprobante_asociado = ANY(%s))
                          AND COALESCE(UPPER(estado), '') <> ALL(%s) AND id <> %s""",
                     (comp['id'], refs, list(NO_CUENTAN), excluir_id or 0))
    return redondear(a_decimal(comp.get('total') or 0) - a_decimal(filas[0]['t']))


def _trazabilidad(comp):
    """Guía, PV, PC (Pedido del cliente) y cotización de la factura, sin que nadie los escriba."""
    pv = (comp.get('pc_vinculado') or '').strip()
    pc_cliente = (comp.get('orden_compra_cliente') or '').strip()
    cot = (comp.get('documento_asociado') or '').strip()
    if pv and (not pc_cliente or not cot):
        f = db_query("""SELECT to_jsonb(p) ->> 'oc_cliente' AS oc, cotizacion_numero FROM pedido_compra_pc p
                        WHERE numero = %s ORDER BY id DESC LIMIT 1""", (pv,))
        if f:
            pc_cliente = pc_cliente or (f[0].get('oc') or '')
            cot = cot or (f[0].get('cotizacion_numero') or '')
    fecha = comp.get('fecha_emision')
    return {'factura': _doc(comp), 'factura_fecha': str(fecha)[:10] if fecha else None,
            'guia': (comp.get('guia_vinculada') or '').strip() or None, 'pv': pv or None,
            'pc_cliente': pc_cliente or None, 'cotizacion': cot or None}


def serie_para(comp):
    """Factura emitida en el portal SOL (serie E…) -> nota en E001; sistema propio u OSE -> FC01."""
    return 'E001' if str(comp.get('serie') or '').upper().startswith('E') else 'FC01'


def origen(ref, excluir_id=None):
    comp = _buscar_factura(ref)
    if not comp:
        raise ErrorNota('No se encontró la factura o boleta afectada (de la empresa elegida).', 404)
    estado = (comp.get('estado_sunat') or comp.get('estado') or '').upper()
    if estado in ('ANULADO', 'ANULADA', 'BORRADOR'):
        raise ErrorNota(f'La factura {_doc(comp)} está "{comp.get("estado_sunat")}": solo se hace nota de crédito '
                        'a una factura emitida.')
    return comp, {**_trazabilidad(comp), 'comprobante_id': comp['id'], 'cliente': comp.get('cliente_nombre'),
                  'ruc': comp.get('cliente_numero_doc'), 'tipo_doc': comp.get('cliente_tipo_doc') or 'RUC',
                  'moneda': comp.get('moneda') or 'PEN', 'total': float(redondear(a_decimal(comp.get('total') or 0))),
                  'saldo': float(_saldo(comp, excluir_id)), 'items': _items_factura(comp), 'serie_nota': serie_para(comp)}


def calcular(comp, datos, excluir_id=None):
    """Monto de la nota (con IGV), subtotal, IGV e ítems. Nunca sale de lo que escribe el usuario."""
    tipo = str(datos.get('tipo_nota') or '').strip()
    if tipo not in TIPOS_NOTA:
        raise ErrorNota('Elige el tipo de nota de crédito (catálogo SUNAT).')
    saldo = _saldo(comp, excluir_id)
    if saldo <= 0:
        raise ErrorNota(f'La factura {_doc(comp)} ya no tiene saldo: otras notas de crédito la cubren.')
    items = _items_factura(comp)
    porcentaje = None
    if tipo in TIPOS_TOTAL:
        monto = saldo
        detalle = items
    elif tipo == '07':
        pedidos = {}
        for it in datos.get('items') or []:
            try:
                pedidos[int(it.get('idx'))] = a_decimal(it.get('cantidad') or 0)
            except (TypeError, ValueError):
                continue
        detalle, monto = [], a_decimal(0)
        for it in items:
            cant = pedidos.get(it['idx'], a_decimal(0))
            if cant < 0 or cant > a_decimal(it['cantidad']):
                raise ErrorNota(f'"{it["producto"]}": la cantidad devuelta debe estar entre 0 y {it["cantidad"]:g}.')
            if cant > 0:
                total = redondear(cant * a_decimal(it['valor_unitario']) * (1 + tasa_igv()))
                detalle.append({**it, 'cantidad': float(cant), 'total': float(total)})
                monto += total
        if not detalle:
            raise ErrorNota('Indica qué cantidad de cada producto devuelve el cliente.')
        monto = redondear(monto)
    else:   # 04 descuento global
        porcentaje = a_decimal(datos.get('porcentaje') or 0)
        if porcentaje <= 0 or porcentaje > 100:
            raise ErrorNota('Indica el % de descuento global (entre 0.01 y 100).')
        monto = redondear(a_decimal(comp.get('total') or 0) * porcentaje / 100)
        detalle = []
    if monto > saldo:
        raise ErrorNota(f'La nota (S/ {monto:.2f}) supera el saldo de la factura {_doc(comp)} (S/ {saldo:.2f}).')
    subtotal = redondear(monto / (1 + tasa_igv()))
    return {'monto': monto, 'subtotal': subtotal, 'igv': redondear(monto - subtotal), 'items': detalle,
            'porcentaje': porcentaje, 'tipo': tipo}


def _validar_textos(datos):
    tipo = str(datos.get('tipo_nota') or '')
    sustento = ' '.join(str(datos.get('sustento') or '').split())
    if len(sustento) < 10:
        raise ErrorNota('Escribe el sustento para SUNAT (por qué se emite la nota, al menos 10 letras).', 400)
    causa = str(datos.get('causa_interna') or '').strip()
    if causa not in CAUSAS:
        raise ErrorNota('Elige la causa en la nota interna.')
    responsable = ' '.join(str(datos.get('responsable_error') or '').split())[:120]
    if causa == 'Error operativo' and not responsable:
        raise ErrorNota('Si fue un error operativo, indica quién lo cometió (responsable del error).')
    nota_interna = str(datos.get('nota_interna') or '').strip()
    if len(nota_interna) < 10:
        raise ErrorNota('Escribe la nota interna: qué pasó, con detalle (solo la ve Erika).')
    guia_dev = ' '.join(str(datos.get('guia_devolucion') or '').split()).upper()[:60]
    if tipo in TIPOS_DEVOLUCION and not guia_dev:
        raise ErrorNota('En una devolución indica el N° de la guía de devolución (o de la devolución registrada) '
                        'con la que regresó la mercadería al almacén.')
    obs = str(datos.get('observaciones') or '').strip()
    obs = obs[:1].upper() + obs[1:] if obs else ''
    return {'sustento': sustento[:500], 'causa': causa, 'responsable': responsable or None,
            'nota_interna': nota_interna[:2000], 'guia_dev': guia_dev or None, 'obs': obs[:1000] or None}


def guardar(datos):
    """Crea o corrige una nota (solo Hellen). enviar=True la deja "Por aprobar"."""
    asegurar_nota_credito()
    if not puede_crear():
        raise ErrorNota('Solo Hellen puede crear notas de crédito (regla de Erika). Pídeselo a ella.', 403)
    nid = datos.get('id')
    previa = None
    if nid:
        previa = db_query("SELECT * FROM notas_credito WHERE id = %s", (nid,))
        if not previa:
            raise ErrorNota('Nota de crédito no encontrada.', 404)
        previa = previa[0]
        if previa.get('estado') not in EDITABLES:
            raise ErrorNota(f'La nota está "{previa.get("estado")}" y ya no se puede cambiar.', 409)
    comp, info = origen(datos.get('comprobante_id') or datos.get('comprobante_asociado'), excluir_id=nid)
    calc = calcular(comp, datos, excluir_id=nid)
    txt = _validar_textos(datos)
    estado = 'Por aprobar' if datos.get('enviar') else 'Borrador'
    ahora = _ahora_lima()
    usuario = usuario_actual()
    valores = {
        'serie': (previa or {}).get('serie') or info['serie_nota'], 'fecha_emision': ahora.date(),
        'cliente_tipo_doc': info['tipo_doc'], 'cliente_numero_doc': info['ruc'], 'cliente_nombre': info['cliente'],
        'cliente_direccion': comp.get('cliente_direccion'), 'comprobante_asociado': info['factura'],
        'comprobante_id': comp['id'], 'motivo': TIPOS_NOTA[calc['tipo']], 'tipo_nota': calc['tipo'],
        'monto': calc['monto'], 'subtotal': calc['subtotal'], 'igv': calc['igv'], 'moneda': info['moneda'],
        'porcentaje': calc['porcentaje'], 'items_json': json.dumps(calc['items']),
        'observaciones': txt['obs'], 'sustento': txt['sustento'], 'nota_interna': txt['nota_interna'],
        'causa_interna': txt['causa'], 'responsable_error': txt['responsable'], 'guia_devolucion': txt['guia_dev'],
        'factura_fecha': info['factura_fecha'], 'guia_numero': info['guia'], 'pv_numero': info['pv'],
        'pc_cliente': info['pc_cliente'], 'cotizacion_numero': info['cotizacion'], 'estado': estado,
        'motivo_rechazo': None,
    }
    if estado == 'Por aprobar':
        valores.update({'enviado_por': usuario, 'enviado_en': ahora})
    with db_tx() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if previa:
            cols = ', '.join(f'{k} = %s' for k in valores)
            cur.execute(f"UPDATE notas_credito SET {cols}, updated_at = NOW() WHERE id = %s RETURNING id, serie, numero, estado",
                        tuple(valores.values()) + (nid,))
            fila = cur.fetchone()
            accion = 'NC_CORREGIDA'
        else:
            from routes.ventas import _siguiente_numero
            valores['numero'] = _siguiente_numero(cur, 'notas_credito', valores['serie'])
            valores['creado_por'] = session.get('usuario_id')
            valores['creado_por_usuario'] = usuario
            cols = ', '.join(valores)
            cur.execute(f"INSERT INTO notas_credito ({cols}) VALUES ({', '.join(['%s'] * len(valores))}) "
                        "RETURNING id, serie, numero, estado", tuple(valores.values()))
            fila = cur.fetchone()
            accion = 'NC_CREADA'
        registrar_auditoria(accion, 'Ventas · Notas de crédito', 'notas_credito', fila['id'],
                            antes={k: str(previa.get(k)) for k in ('estado', 'monto', 'tipo_nota')} if previa else None,
                            despues={'estado': estado, 'monto': str(calc['monto']), 'factura': info['factura']},
                            detalle=f"{fila['serie']}-{fila['numero']} {estado} por {usuario}", cur=cur)
    if not previa:
        marcar_empresa(None, 'notas_credito', fila['id'], empresa_para_crear(comp.get('empresa_id')))
    return {**fila, 'monto': float(calc['monto'])}


def decidir(nid, decision, motivo=''):
    """Erika aprueba (queda "Emitida" y recién resta del saldo) o rechaza con motivo."""
    asegurar_nota_credito()
    if not puede_aprobar():
        raise ErrorNota('Solo Erika aprueba o rechaza notas de crédito.', 403)
    fila = db_query("SELECT * FROM notas_credito WHERE id = %s", (nid,))
    if not fila:
        raise ErrorNota('Nota de crédito no encontrada.', 404)
    fila = fila[0]
    if fila.get('estado') != 'Por aprobar':
        raise ErrorNota(f'La nota está "{fila.get("estado")}": solo se decide una nota "Por aprobar".', 409)
    ahora = _ahora_lima()
    if decision == 'aprobar':
        comp = _buscar_factura(fila.get('comprobante_id') or fila.get('comprobante_asociado'))
        if comp and a_decimal(fila.get('monto') or 0) > _saldo(comp, excluir_id=nid):
            raise ErrorNota('La factura ya no tiene saldo suficiente para esta nota (otra nota se aprobó antes).', 409)
        nuevo, motivo = 'Emitida', None
    elif decision == 'rechazar':
        motivo = ' '.join(str(motivo or '').split())[:500]
        if len(motivo) < 5:
            raise ErrorNota('Escribe por qué la rechazas (Hellen lo verá para corregirla).')
        nuevo = 'Rechazada'
    else:
        raise ErrorNota('Decisión inválida.')
    with db_tx() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""UPDATE notas_credito SET estado = %s, aprobado_por = %s, aprobado_en = %s, motivo_rechazo = %s,
                              updated_at = NOW() WHERE id = %s AND estado = 'Por aprobar' RETURNING id, serie, numero, estado""",
                    (nuevo, usuario_actual(), ahora, motivo, nid))
        r = cur.fetchone()
        if not r:
            raise ErrorNota('La nota cambió mientras decidías. Vuelve a abrirla.', 409)
        registrar_auditoria('NC_APROBADA' if nuevo == 'Emitida' else 'NC_RECHAZADA', 'Ventas · Notas de crédito',
                            'notas_credito', nid, antes={'estado': 'Por aprobar'},
                            despues={'estado': nuevo, 'motivo_rechazo': motivo},
                            detalle=f"{r['serie']}-{r['numero']} {nuevo} por {usuario_actual()}", cur=cur)
    return r


def _fila_publica(r, con_interna):
    d = {k: (str(v) if isinstance(v, datetime) else v) for k, v in r.items()}
    for k in ('monto', 'subtotal', 'igv', 'porcentaje'):
        if d.get(k) is not None:
            d[k] = float(d[k])
    for k in ('fecha_emision', 'factura_fecha'):
        if d.get(k) is not None:
            d[k] = str(d[k])[:10]
    if isinstance(d.get('items_json'), str):
        try:
            d['items_json'] = json.loads(d['items_json'])
        except ValueError:
            d['items_json'] = []
    if not con_interna:
        for k in ('nota_interna', 'causa_interna', 'responsable_error'):
            d.pop(k, None)
    return d


def ver_interna(fila):
    """La nota interna la ven Erika y quien la escribió (Hellen)."""
    return puede_aprobar() or puede_crear()


# ------------------------------------------------------------------ rutas
def _resp_error(e):
    return jsonify({'success': False, 'error': str(e)}), e.codigo


def _login():
    return 'usuario' in session


@nota_credito_bp.route('/ventas/api/nc/permisos')
def api_nc_permisos():
    if not _login():
        return jsonify({'error': 'Sesión expirada'}), 401
    asegurar_nota_credito()
    por_aprobar = db_query("SELECT COUNT(*) AS n FROM notas_credito WHERE estado = 'Por aprobar'")[0]['n']
    return jsonify({'success': True, 'data': {'puede_crear': puede_crear(), 'puede_aprobar': puede_aprobar(),
                                              'por_aprobar': int(por_aprobar), 'tipos': TIPOS_NOTA, 'causas': CAUSAS}})


@nota_credito_bp.route('/ventas/api/nc/origen')
def api_nc_origen():
    if not _login():
        return jsonify({'error': 'Sesión expirada'}), 401
    try:
        asegurar_nota_credito()
        _, info = origen(request.args.get('comprobante'), excluir_id=request.args.get('excluir', type=int))
        return jsonify({'success': True, 'data': info})
    except ErrorNota as e:
        return _resp_error(e)


@nota_credito_bp.route('/ventas/api/nc/usuarios')
def api_nc_usuarios():
    if not _login():
        return jsonify({'error': 'Sesión expirada'}), 401
    filas = db_query("""SELECT usuario, COALESCE(NULLIF(to_jsonb(u) ->> 'nombre_completo', ''), usuario) AS nombre
                        FROM usuarios u WHERE COALESCE((to_jsonb(u) ->> 'activo')::boolean, true)
                        ORDER BY 2""")
    return jsonify({'success': True, 'data': [{'usuario': f['usuario'], 'nombre': f['nombre']} for f in filas]})


@nota_credito_bp.route('/ventas/api/nc/guardar', methods=['POST'])
def api_nc_guardar():
    if not _login():
        return jsonify({'error': 'Sesión expirada'}), 401
    try:
        return jsonify({'success': True, 'data': guardar(request.get_json(silent=True) or {})})
    except ErrorNota as e:
        return _resp_error(e)


@nota_credito_bp.route('/ventas/api/nc/<int:nid>/decidir', methods=['POST'])
def api_nc_decidir(nid):
    if not _login():
        return jsonify({'error': 'Sesión expirada'}), 401
    d = request.get_json(silent=True) or {}
    try:
        return jsonify({'success': True, 'data': decidir(nid, d.get('decision'), d.get('motivo'))})
    except ErrorNota as e:
        return _resp_error(e)


@nota_credito_bp.route('/ventas/api/nc/<int:nid>')
def api_nc_ver(nid):
    if not _login():
        return jsonify({'error': 'Sesión expirada'}), 401
    asegurar_nota_credito()
    fila = db_query("SELECT * FROM notas_credito WHERE id = %s", (nid,))
    if not fila:
        return jsonify({'success': False, 'error': 'Nota de crédito no encontrada'}), 404
    d = _fila_publica(fila[0], ver_interna(fila[0]))
    d['archivos'] = [dict(a, created_at=str(a['created_at'])[:16]) for a in db_query(
        "SELECT id, nombre, bytes, subido_por, created_at FROM nota_credito_archivos WHERE nota_id = %s ORDER BY id", (nid,))]
    return jsonify({'success': True, 'data': d})


@nota_credito_bp.route('/ventas/api/nc/<int:nid>/archivos', methods=['POST'])
def api_nc_archivo_subir(nid):
    """Evidencia para SUNAT: carta o correo de conformidad del cliente, y el PDF/XML de la nota emitida en SOL."""
    if not _login():
        return jsonify({'error': 'Sesión expirada'}), 401
    asegurar_nota_credito()
    if not (puede_crear() or puede_aprobar()):
        return jsonify({'success': False, 'error': 'Solo Hellen o Erika adjuntan evidencias de la nota.'}), 403
    if not db_query("SELECT 1 FROM notas_credito WHERE id = %s", (nid,)):
        return jsonify({'success': False, 'error': 'Nota de crédito no encontrada'}), 404
    f = request.files.get('archivo')
    if not f or not f.filename:
        return jsonify({'success': False, 'error': 'Elige un archivo.'}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in TIPOS_EVIDENCIA:
        return jsonify({'success': False, 'error': 'Solo PDF, XML, ZIP, imagen (JPG/PNG) o correo (EML/MSG).'}), 400
    datos = f.read(MAX_EVIDENCIA + 1)
    if len(datos) > MAX_EVIDENCIA:
        return jsonify({'success': False, 'error': 'El archivo pesa más de 5 MB.'}), 400
    r = db_query("""INSERT INTO nota_credito_archivos (nota_id, nombre, mime, datos, bytes, subido_por)
                    VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                 (nid, os.path.basename(f.filename)[:150], TIPOS_EVIDENCIA[ext], datos, len(datos), usuario_actual()))
    registrar_auditoria('NC_EVIDENCIA', 'Ventas · Notas de crédito', 'notas_credito', nid,
                        detalle=f'Adjuntó {f.filename} ({len(datos)} bytes)')
    return jsonify({'success': True, 'data': {'id': r[0]['id']}})


@nota_credito_bp.route('/ventas/api/nc/archivos/<int:aid>')
def api_nc_archivo_bajar(aid):
    if not _login():
        return jsonify({'error': 'Sesión expirada'}), 401
    asegurar_nota_credito()
    f = db_query("SELECT nombre, mime, datos FROM nota_credito_archivos WHERE id = %s", (aid,))
    if not f:
        return jsonify({'success': False, 'error': 'Archivo no encontrado'}), 404
    return Response(bytes(f[0]['datos']), mimetype=f[0]['mime'],
                    headers={'Content-Disposition': f'attachment; filename="{f[0]["nombre"]}"'})


@nota_credito_bp.route('/ventas/api/nc/reporte')
def api_nc_reporte():
    """Para Erika: notas de crédito por causa y por responsable del error (para saber a quién llamar la atención)."""
    if not _login():
        return jsonify({'error': 'Sesión expirada'}), 401
    if not puede_aprobar():
        return jsonify({'success': False, 'error': 'Solo Erika ve este reporte.'}), 403
    asegurar_nota_credito()
    sql_emp, par_emp = filtro_sql('empresa_id')
    base = f"FROM notas_credito WHERE COALESCE(UPPER(estado), '') NOT IN ('ANULADA', 'ANULADO') {sql_emp}"
    causas = db_query(f"""SELECT COALESCE(causa_interna, 'Sin causa (antiguas)') AS causa, COUNT(*) AS n,
                                 COALESCE(SUM(monto), 0) AS monto {base} GROUP BY 1 ORDER BY 3 DESC""", par_emp)
    resp = db_query(f"""SELECT responsable_error AS responsable, COUNT(*) AS n, COALESCE(SUM(monto), 0) AS monto,
                               MAX(fecha_emision) AS ultima {base} AND causa_interna = 'Error operativo'
                        GROUP BY 1 ORDER BY 2 DESC, 3 DESC""", par_emp)
    f = lambda filas: [{**x, 'monto': float(x['monto']), **({'ultima': str(x['ultima'])[:10]} if 'ultima' in x else {})}
                       for x in filas]
    return jsonify({'success': True, 'data': {'por_causa': f(causas), 'por_responsable': f(resp)}})


@nota_credito_bp.route('/ventas/nc/<int:nid>/imprimir')
def nc_imprimir(nid):
    """Documento de la nota para imprimir o guardar en PDF. Nunca muestra la nota interna."""
    if not _login():
        return 'Sesión expirada', 401
    asegurar_nota_credito()
    fila = db_query("SELECT * FROM notas_credito WHERE id = %s", (nid,))
    if not fila:
        return 'Nota de crédito no encontrada', 404
    emp = db_query("SELECT * FROM erp_empresas WHERE id::text = %s", (str(fila[0].get('empresa_id')),)) \
        if fila[0].get('empresa_id') else []
    return render_template('ventas/imprimir_nota_credito.html', n=_fila_publica(fila[0], False), tipos=TIPOS_NOTA,
                           empresa=emp[0] if emp else {})
