# routes/caja_chica.py - Caja chica con fondo fijo (pedido de Erika, 22/10/2026 18:24)
#
# Qué hace (en simple):
#   1. Gastos: Hellen anota cada gasto el mismo día (rubro, quién gastó, a quién se pagó, de dónde a dónde,
#      N° de PC / OC / despacho, tipo de comprobante y foto). El saldo se calcula solo.
#   2. Fondo fijo: la caja arranca cada semana con el mismo monto (S/ 600 por defecto).
#   3. Rendición semanal: Hellen envía los gastos de la semana; Erika (gerencia) aprueba y repone exactamente
#      lo que falta para completar el fondo. La reposición queda como pago en Finanzas ▸ Cobros y pagos,
#      así Conciliación bancaria la encuentra sola en el extracto del banco.
#   4. Arqueo: se cuenta lo que hay (efectivo + saldo de la cuenta de caja) y se compara con el sistema.
#   5. Impresos: vale de caja chica, planilla de movilidad (art. 37 inc. a1 LIR) y acta del fondo fijo.
#   6. Histórico: el Excel de caja chica de Erika (plantilla de 22/10/2026) se importa una sola vez.
#
# Reglas (candados):
#   - Acceso: gerencia o quien tenga el permiso "Caja chica". Aprobar, observar y reponer: solo gerencia.
#   - Un gasto enviado en una rendición ya no se edita; si Erika la observa, vuelve a quedar libre.
#   - Anular pide motivo. Todo queda con usuario y fecha y hora de Lima.
#   - El vale de caja es un documento interno: no reemplaza al comprobante de pago ante SUNAT.
import io
import re
import threading
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from flask import Blueprint, render_template, request, jsonify, session, Response
from psycopg2.extras import RealDictCursor, Json

from database import db_query, db_tx
from utils import a_decimal, redondear, es_admin, id_empresa
from routes.multiempresa import empresas as lista_empresas, empresa_actual, empresa_por_id

caja_chica_bp = Blueprint('caja_chica', __name__)


def _ahora():
    """Fecha y hora de Lima (el servidor de Render está en UTC)."""
    return datetime.now(ZoneInfo('America/Lima')).replace(tzinfo=None)


CERO = Decimal('0')
FONDO_POR_DEFECTO = Decimal('600')
RMV_POR_DEFECTO = Decimal('1230')        # RMV desde el 01/10/2026 (El Peruano, 28/09/2026). Se cambia en Configurar.
TOPE_AVISO = Decimal('100')              # gasto mayor: debe decir quién lo autorizó
RUBROS = ('Flete y transporte de carga', 'Movilidad del personal (pasajes)', 'Taxi', 'Parihuelas y embalaje',
          'Útiles, impresiones y oficina', 'Compras urgentes para pedidos', 'Servicios (teléfono, internet)',
          'Refrigerios y atenciones', 'Gastos bancarios (ITF)', 'Seguros y tributos', 'Otros (explicar)')
RUBRO_MOVILIDAD = 'Movilidad del personal (pasajes)'
COMPROBANTES = ('Factura', 'Boleta', 'Recibo por honorarios', 'Ticket / voucher', 'Planilla de movilidad',
                'Sin comprobante (vale)')
COMPROBANTE_HISTORICO = 'No registrado (histórico)'
CON_NUMERO = ('Factura', 'Boleta', 'Recibo por honorarios')
SUSTENTA_SUNAT = ('Factura', 'Boleta', 'Recibo por honorarios', 'Planilla de movilidad')
TIPOS_PERSONA = ('Trabajador', 'Practicante', 'Transportista', 'Otro')
TIPOS_MOV = ('Gasto', 'Reposición', 'Devolución', 'Saldo inicial')


class ErrorCaja(Exception):
    pass


# ============================================================
# PERMISO (en el servidor)
# ============================================================
def puede_ver_caja():
    if es_admin():
        return True
    try:
        from routes.acceso import acceso_usuario
        acc = acceso_usuario()
    except Exception:
        return False
    return bool(acc.get('configurado') and 'caja_chica' in acc.get('modulos', set()))


@caja_chica_bp.before_request
def _proteger():
    if 'usuario_id' not in session:
        return None
    if not puede_ver_caja():
        msg = ('No tienes permiso para entrar a Caja chica. Lo ve la gerencia y quien tenga el permiso '
               '"Caja chica" en Configuración ▸ Usuarios y permisos.')
        if '/api/' in request.path:
            return jsonify({'success': False, 'error': msg, 'codigo': 'sin_permiso'}), 403
        from flask import flash, redirect, url_for
        flash(msg, 'error')
        return redirect(url_for('index'))
    asegurar_tablas()
    return None


# ============================================================
# TABLAS PROPIAS (equivalente: migrations/027_caja_chica.sql)
# ============================================================
SQL_DDL_CAJA = """
    CREATE TABLE IF NOT EXISTS caja_chica_config (
        empresa_id VARCHAR(64) PRIMARY KEY,
        fondo_fijo NUMERIC(12,2) NOT NULL DEFAULT 600 CHECK (fondo_fijo > 0),
        responsable VARCHAR(150),
        responsable_dni VARCHAR(15),
        cuenta VARCHAR(150),
        rmv NUMERIC(10,2) NOT NULL DEFAULT 1230,
        actualizado_por VARCHAR(150),
        actualizado_en TIMESTAMP DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS caja_chica_personas (
        id SERIAL PRIMARY KEY,
        empresa_id VARCHAR(64) NOT NULL,
        nombre VARCHAR(150) NOT NULL,
        dni VARCHAR(15),
        ruc VARCHAR(11),
        tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('Trabajador', 'Practicante', 'Transportista', 'Otro')),
        activo BOOLEAN NOT NULL DEFAULT true,
        creado_por VARCHAR(150),
        creado_en TIMESTAMP DEFAULT NOW(),
        actualizado_por VARCHAR(150),
        actualizado_en TIMESTAMP DEFAULT NOW()
    );
    CREATE UNIQUE INDEX IF NOT EXISTS uq_caja_chica_persona ON caja_chica_personas (empresa_id, LOWER(nombre));
    CREATE TABLE IF NOT EXISTS caja_chica_rendiciones (
        id SERIAL PRIMARY KEY,
        empresa_id VARCHAR(64) NOT NULL,
        numero INTEGER NOT NULL,
        desde DATE NOT NULL,
        hasta DATE NOT NULL,
        total_gastado NUMERIC(12,2) NOT NULL DEFAULT 0,
        sin_sustento NUMERIC(12,2) NOT NULL DEFAULT 0,
        estado VARCHAR(15) NOT NULL DEFAULT 'Por aprobar' CHECK (estado IN ('Por aprobar', 'Observada', 'Aprobada')),
        enviada_por VARCHAR(150),
        enviada_en TIMESTAMP DEFAULT NOW(),
        revisada_por VARCHAR(150),
        revisada_en TIMESTAMP,
        observacion TEXT,
        monto_repuesto NUMERIC(12,2),
        fecha_reposicion DATE,
        numero_operacion VARCHAR(80),
        finanzas_pago_id INTEGER,
        historial JSONB NOT NULL DEFAULT '[]'::jsonb
    );
    CREATE UNIQUE INDEX IF NOT EXISTS uq_caja_chica_rendicion ON caja_chica_rendiciones (empresa_id, numero);
    CREATE TABLE IF NOT EXISTS caja_chica_movimientos (
        id SERIAL PRIMARY KEY,
        empresa_id VARCHAR(64) NOT NULL,
        numero INTEGER NOT NULL,
        fecha DATE NOT NULL,
        tipo VARCHAR(15) NOT NULL CHECK (tipo IN ('Gasto', 'Reposición', 'Devolución', 'Saldo inicial')),
        empresa_gasto VARCHAR(10),
        rubro VARCHAR(60),
        quien VARCHAR(150),
        quien_id INTEGER REFERENCES caja_chica_personas(id),
        pagado_a VARCHAR(150),
        descripcion TEXT NOT NULL,
        referencia VARCHAR(150),
        comprobante_tipo VARCHAR(30),
        comprobante_numero VARCHAR(40),
        ruc_emisor VARCHAR(11),
        autorizado_por VARCHAR(150),
        ingreso NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (ingreso >= 0),
        egreso NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (egreso >= 0),
        rendicion_id INTEGER REFERENCES caja_chica_rendiciones(id),
        origen VARCHAR(12) NOT NULL DEFAULT 'ERP' CHECK (origen IN ('ERP', 'Histórico')),
        estado VARCHAR(10) NOT NULL DEFAULT 'Activo' CHECK (estado IN ('Activo', 'Anulado')),
        motivo_anulacion TEXT,
        observacion TEXT,
        creado_por VARCHAR(150),
        creado_en TIMESTAMP DEFAULT NOW(),
        actualizado_por VARCHAR(150),
        actualizado_en TIMESTAMP DEFAULT NOW(),
        historial JSONB NOT NULL DEFAULT '[]'::jsonb,
        CHECK ((ingreso > 0 AND egreso = 0) OR (egreso > 0 AND ingreso = 0) OR tipo = 'Saldo inicial')
    );
    CREATE UNIQUE INDEX IF NOT EXISTS uq_caja_chica_mov ON caja_chica_movimientos (empresa_id, numero);
    CREATE INDEX IF NOT EXISTS idx_caja_chica_mov_fecha ON caja_chica_movimientos (empresa_id, fecha);
    CREATE TABLE IF NOT EXISTS caja_chica_fotos (
        id SERIAL PRIMARY KEY,
        movimiento_id INTEGER NOT NULL REFERENCES caja_chica_movimientos(id),
        nombre VARCHAR(150),
        mime VARCHAR(40) NOT NULL,
        datos BYTEA NOT NULL,
        bytes INTEGER NOT NULL,
        subido_por VARCHAR(150),
        subido_en TIMESTAMP DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_caja_chica_fotos_mov ON caja_chica_fotos (movimiento_id);
    CREATE TABLE IF NOT EXISTS caja_chica_arqueos (
        id SERIAL PRIMARY KEY,
        empresa_id VARCHAR(64) NOT NULL,
        fecha DATE NOT NULL,
        saldo_sistema NUMERIC(12,2) NOT NULL,
        efectivo NUMERIC(12,2) NOT NULL DEFAULT 0,
        saldo_cuenta NUMERIC(12,2) NOT NULL DEFAULT 0,
        vales NUMERIC(12,2) NOT NULL DEFAULT 0,
        diferencia NUMERIC(12,2) NOT NULL,
        explicacion TEXT,
        hecho_por VARCHAR(150),
        hecho_en TIMESTAMP DEFAULT NOW()
    );
    ALTER TABLE caja_chica_config ENABLE ROW LEVEL SECURITY;
    ALTER TABLE caja_chica_personas ENABLE ROW LEVEL SECURITY;
    ALTER TABLE caja_chica_rendiciones ENABLE ROW LEVEL SECURITY;
    ALTER TABLE caja_chica_movimientos ENABLE ROW LEVEL SECURITY;
    ALTER TABLE caja_chica_fotos ENABLE ROW LEVEL SECURITY;
    ALTER TABLE caja_chica_arqueos ENABLE ROW LEVEL SECURITY;
"""
_tablas = {'ok': False}
_lock = threading.Lock()


def asegurar_tablas():
    if _tablas['ok']:
        return
    with _lock:
        if _tablas['ok']:
            return
        from routes.finanzas import asegurar_tablas_finanzas
        asegurar_tablas_finanzas()
        with db_tx() as conn:
            cur = conn.cursor()
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('caja_chica_ddl'))")
            cur.execute(SQL_DDL_CAJA)
        _tablas['ok'] = True


# ============================================================
# AYUDAS
# ============================================================
def _usuario():
    return session.get('nombre_completo') or session.get('usuario') or f"Usuario {session.get('usuario_id')}"


def _r(v):
    return redondear(v or 0, 2)


def _n(v):
    return float(_r(v))


def _f(v):
    if isinstance(v, datetime):
        return v.strftime('%Y-%m-%d %H:%M')
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


def _txt(d, campo, largo, obligatorio=False, nombre=None):
    t = re.sub(r'\s+', ' ', str(d.get(campo) or '')).strip()
    if obligatorio and not t:
        raise ErrorCaja(f'Falta {nombre or campo}.')
    return t[:largo] or None


def _fecha(txt, campo='la fecha', obligatorio=True):
    t = (txt or '').strip()[:10]
    if not t:
        if obligatorio:
            raise ErrorCaja(f'Falta {campo}.')
        return None
    try:
        return datetime.strptime(t, '%Y-%m-%d').date()
    except ValueError:
        raise ErrorCaja(f'{campo[0].upper() + campo[1:]} no es válida.')


def _monto(v, campo='el monto'):
    try:
        m = Decimal(str(v).replace(',', '').strip())
    except Exception:
        raise ErrorCaja(f'Escribe {campo} en números.')
    if m <= 0:
        raise ErrorCaja(f'{campo[0].upper() + campo[1:]} debe ser mayor a 0.')
    if m != m.quantize(Decimal('0.01')):
        raise ErrorCaja('Máximo 2 decimales.')
    if m > Decimal('100000'):
        raise ErrorCaja(f'{campo[0].upper() + campo[1:]} es demasiado alto para caja chica.')
    return m


def _empresa(eid_txt=None):
    eid = id_empresa(eid_txt) if eid_txt else None
    e = empresa_por_id(eid) if eid else None
    e = e or empresa_actual()
    if not e:
        lista = lista_empresas()
        e = lista[0] if lista else None
    if not e:
        raise ErrorCaja('No hay empresas configuradas (Configuración ▸ Empresas).')
    return e


def _evento(accion, **extra):
    return Json([{'accion': accion, 'usuario': _usuario(), 'fecha': _ahora().strftime('%Y-%m-%d %H:%M'), **extra}])


def leer_config(eid):
    f = db_query("SELECT * FROM caja_chica_config WHERE empresa_id = %s", (str(eid),))
    if f:
        c = f[0]
        return {'fondo_fijo': a_decimal(c['fondo_fijo']), 'responsable': c['responsable'] or '',
                'responsable_dni': c['responsable_dni'] or '', 'cuenta': c['cuenta'] or '', 'rmv': a_decimal(c['rmv']),
                'configurado': True, 'actualizado_por': c['actualizado_por'], 'actualizado_en': _f(c['actualizado_en'])}
    return {'fondo_fijo': FONDO_POR_DEFECTO, 'responsable': '', 'responsable_dni': '', 'cuenta': '',
            'rmv': RMV_POR_DEFECTO, 'configurado': False}


def tope_movilidad(conf):
    """4% de la RMV por trabajador y por día (art. 37 inc. a1 LIR)."""
    return _r(conf['rmv'] * Decimal('0.04'))


def saldo(eid, hasta=None):
    sql = "SELECT COALESCE(SUM(ingreso - egreso), 0) AS s FROM caja_chica_movimientos WHERE empresa_id = %s AND estado = 'Activo'"
    par = [str(eid)]
    if hasta:
        sql += " AND fecha <= %s"
        par.append(hasta)
    return _r(db_query(sql, par)[0]['s'])


def _siguiente(cur, tabla, eid):
    cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f'{tabla}:{eid}',))
    cur.execute(f"SELECT COALESCE(MAX(numero), 0) + 1 AS n FROM {tabla} WHERE empresa_id = %s", (str(eid),))
    return cur.fetchone()['n']


def _ultima_aprobada(eid):
    f = db_query("""SELECT MAX(hasta) AS h FROM caja_chica_rendiciones WHERE empresa_id = %s AND estado = 'Aprobada'""",
                 (str(eid),))
    return f[0]['h'] if f else None


# ============================================================
# PERSONAS (quién gasta y a quién se paga)
# ============================================================
def personas(eid, solo_activas=False):
    sql = "SELECT * FROM caja_chica_personas WHERE empresa_id = %s"
    if solo_activas:
        sql += " AND activo"
    return db_query(sql + " ORDER BY activo DESC, tipo, nombre", (str(eid),))


def guardar_persona(eid, d, pid=None):
    nombre = _txt(d, 'nombre', 150, True, 'el nombre')
    tipo = d.get('tipo')
    if tipo not in TIPOS_PERSONA:
        raise ErrorCaja('Elige el tipo: trabajador, practicante, transportista u otro.')
    dni = re.sub(r'\D', '', str(d.get('dni') or ''))[:15] or None
    ruc = re.sub(r'\D', '', str(d.get('ruc') or ''))[:11] or None
    if dni and len(dni) < 8:
        raise ErrorCaja('El DNI debe tener 8 dígitos (si es carné de extranjería, escríbelo completo).')
    if ruc and len(ruc) != 11:
        raise ErrorCaja('El RUC debe tener 11 dígitos.')
    activo = d.get('activo') not in (False, 'false', 0, '0')
    try:
        if pid:
            filas = db_query("""UPDATE caja_chica_personas SET nombre = %s, dni = %s, ruc = %s, tipo = %s, activo = %s,
                                actualizado_por = %s, actualizado_en = NOW() WHERE id = %s AND empresa_id = %s RETURNING id""",
                             (nombre, dni, ruc, tipo, activo, _usuario(), pid, str(eid)))
            if not filas:
                raise ErrorCaja('No se encontró a esa persona.')
            return pid
        return db_query("""INSERT INTO caja_chica_personas (empresa_id, nombre, dni, ruc, tipo, activo, creado_por, actualizado_por)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                        (str(eid), nombre, dni, ruc, tipo, activo, _usuario(), _usuario()))[0]['id']
    except ErrorCaja:
        raise
    except Exception as ex:
        if 'uq_caja_chica_persona' in str(ex):
            raise ErrorCaja(f'Ya existe "{nombre}" en la lista.')
        raise


# ============================================================
# MOVIMIENTOS
# ============================================================
def _leer_gasto(eid, d, conf):
    """Valida un gasto y devuelve sus columnas."""
    fecha = _fecha(d.get('fecha'), 'la fecha')
    hoy = _ahora().date()
    if fecha > hoy:
        raise ErrorCaja('La fecha no puede ser futura.')
    if fecha < hoy - timedelta(days=120):
        raise ErrorCaja('La fecha es de hace más de 4 meses: revisa el año.')
    cerrada = _ultima_aprobada(eid)
    if cerrada and fecha <= cerrada:
        raise ErrorCaja(f'La semana hasta el {cerrada:%d/%m/%Y} ya fue aprobada y está cerrada. Usa una fecha posterior.')
    rubro = d.get('rubro')
    if rubro not in RUBROS:
        raise ErrorCaja('Elige el rubro.')
    descripcion = _txt(d, 'descripcion', 500, True, 'la descripción (de dónde a dónde o para qué)')
    if rubro == 'Otros (explicar)' and len(descripcion) < 10:
        raise ErrorCaja('En "Otros" explica bien en qué se gastó.')
    monto = _monto(d.get('monto'))
    tipo_c = d.get('comprobante_tipo')
    if tipo_c not in COMPROBANTES:
        raise ErrorCaja('Elige el tipo de comprobante (si no hay, "Sin comprobante (vale)").')
    numero_c = _txt(d, 'comprobante_numero', 40)
    if tipo_c in CON_NUMERO and not numero_c:
        raise ErrorCaja(f'Escribe el N° de la {tipo_c.lower()} (ej.: F001-123).')
    ruc = re.sub(r'\D', '', str(d.get('ruc_emisor') or ''))[:11] or None
    if tipo_c == 'Factura' and (not ruc or len(ruc) != 11):
        raise ErrorCaja('Escribe el RUC de quien emitió la factura (11 dígitos).')
    quien_id = d.get('quien_id')
    quien = None
    gente = {p['id']: p for p in personas(eid)}
    if quien_id not in (None, ''):
        try:
            quien_id = int(quien_id)
        except (TypeError, ValueError):
            raise ErrorCaja('Elige quién gastó.')
        p = gente.get(quien_id)
        if not p:
            raise ErrorCaja('Esa persona no está en la lista de esta empresa.')
        quien = p['nombre']
    else:
        quien_id = None
    if not quien:
        raise ErrorCaja('Elige quién gastó (o quién entregó el dinero).')
    if tipo_c == 'Planilla de movilidad':
        p = gente[quien_id]
        if rubro != RUBRO_MOVILIDAD:
            raise ErrorCaja('La planilla de movilidad es solo para pasajes del personal (rubro "Movilidad del personal").')
        if p['tipo'] not in ('Trabajador', 'Practicante'):
            raise ErrorCaja('La planilla de movilidad es solo para el personal (trabajadores y practicantes), no para transportistas.')
        if not p['dni']:
            raise ErrorCaja(f'Falta el DNI de {p["nombre"]}: agrégalo en "Personas" (la planilla de movilidad lo pide).')
    empresa_gasto = (d.get('empresa_gasto') or '').upper()[:10] or None
    codigos = {x['codigo'] for x in lista_empresas()}
    if empresa_gasto and codigos and empresa_gasto not in codigos:
        raise ErrorCaja('Empresa del gasto no válida.')
    autorizado = _txt(d, 'autorizado_por', 150)
    if monto > TOPE_AVISO and not autorizado:
        raise ErrorCaja(f'Gasto mayor a S/ {TOPE_AVISO:.0f}: escribe quién lo autorizó (ej.: Erika por WhatsApp).')
    return {'fecha': fecha, 'rubro': rubro, 'descripcion': descripcion, 'egreso': monto, 'comprobante_tipo': tipo_c,
            'comprobante_numero': numero_c, 'ruc_emisor': ruc, 'quien_id': quien_id, 'quien': quien,
            'pagado_a': _txt(d, 'pagado_a', 150), 'referencia': _txt(d, 'referencia', 150),
            'empresa_gasto': empresa_gasto, 'autorizado_por': autorizado, 'observacion': _txt(d, 'observacion', 500)}


def _aviso_movilidad(eid, conf, quien_id, fecha, excluir=None):
    """Total de pasajes con planilla de movilidad de esa persona ese día (para avisar si pasa el tope)."""
    par = [str(eid), quien_id, fecha]
    sql = """SELECT COALESCE(SUM(egreso), 0) AS t FROM caja_chica_movimientos WHERE empresa_id = %s AND quien_id = %s
             AND fecha = %s AND estado = 'Activo' AND comprobante_tipo = 'Planilla de movilidad'"""
    if excluir:
        sql += " AND id <> %s"
        par.append(excluir)
    total = _r(db_query(sql, par)[0]['t'])
    tope = tope_movilidad(conf)
    return total, tope


def registrar_gasto(eid, d):
    conf = leer_config(eid)
    g = _leer_gasto(eid, d, conf)
    with db_tx() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        n = _siguiente(cur, 'caja_chica_movimientos', eid)
        cols = ['empresa_id', 'numero', 'tipo', 'creado_por', 'actualizado_por'] + list(g.keys())
        vals = [str(eid), n, 'Gasto', _usuario(), _usuario()] + list(g.values())
        cur.execute(f"INSERT INTO caja_chica_movimientos ({', '.join(cols)}, historial) VALUES "
                    f"({', '.join(['%s'] * len(vals))}, %s) RETURNING id",
                    vals + [_evento('Registrado', monto=float(g['egreso']))])
        mid = cur.fetchone()['id']
    return mid, n, _avisos_de(eid, conf, g, mid)


def _avisos_de(eid, conf, g, mid):
    avisos = []
    if g['comprobante_tipo'] == 'Planilla de movilidad':
        total, tope = _aviso_movilidad(eid, conf, g['quien_id'], g['fecha'])
        if total > tope:
            avisos.append(f'{g["quien"]} suma S/ {total:.2f} de pasajes el {g["fecha"]:%d/%m/%Y}: pasa el tope de '
                          f'S/ {tope:.2f} al día. El exceso no se descuenta ante SUNAT.')
    s = saldo(eid)
    if s < 0:
        avisos.append(f'El saldo quedó en S/ {s:.2f}: alguien adelantó dinero propio. Se devuelve en la próxima reposición.')
    return avisos


def _mov(cur, eid, mid):
    cur.execute("SELECT * FROM caja_chica_movimientos WHERE id = %s AND empresa_id = %s FOR UPDATE", (mid, str(eid)))
    m = cur.fetchone()
    if not m:
        raise ErrorCaja('No se encontró ese movimiento.')
    return m


def _editable(cur, m):
    if m['estado'] == 'Anulado':
        raise ErrorCaja('Ese movimiento está anulado.')
    if m['origen'] == 'Histórico':
        raise ErrorCaja('Los movimientos del histórico no se editan (vienen del Excel). Si hay un error, anótalo como nuevo gasto o devolución.')
    if m['tipo'] != 'Gasto':
        raise ErrorCaja('Las reposiciones se corrigen desde su rendición.')
    if m['rendicion_id']:
        cur.execute("SELECT numero, estado FROM caja_chica_rendiciones WHERE id = %s", (m['rendicion_id'],))
        r = cur.fetchone()
        if r and r['estado'] != 'Observada':
            raise ErrorCaja(f'Ese gasto está en la rendición N° {r["numero"]} ({r["estado"].lower()}): ya no se cambia.')


def editar_gasto(eid, mid, d):
    conf = leer_config(eid)
    g = _leer_gasto(eid, d, conf)
    with db_tx() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        m = _mov(cur, eid, mid)
        _editable(cur, m)
        cambios = [f'{k}: {_f(m[k])} → {_f(v)}' for k, v in g.items() if _f(m[k]) != _f(v)]
        if not cambios:
            return []
        sets = ', '.join(f'{k} = %s' for k in g)
        cur.execute(f"UPDATE caja_chica_movimientos SET {sets}, actualizado_por = %s, actualizado_en = NOW(), "
                    f"historial = historial || %s WHERE id = %s",
                    list(g.values()) + [_usuario(), _evento('Editado', cambios=cambios), mid])
    return _avisos_de(eid, conf, g, mid)


def anular_movimiento(eid, mid, motivo):
    motivo = (motivo or '').strip()
    if len(motivo) < 5:
        raise ErrorCaja('Escribe el motivo de la anulación.')
    with db_tx() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        m = _mov(cur, eid, mid)
        if m['estado'] == 'Anulado':
            raise ErrorCaja('Ya estaba anulado.')
        if m['origen'] == 'Histórico' and not es_admin():
            raise ErrorCaja('Solo la gerencia anula movimientos del histórico.')
        if m['origen'] != 'Histórico':
            if m['tipo'] == 'Reposición' and m['rendicion_id']:
                raise ErrorCaja('Esta reposición es de una rendición aprobada: no se anula aquí.')
            if m['tipo'] == 'Gasto':
                _editable(cur, m)
            elif not es_admin():
                raise ErrorCaja('Solo la gerencia anula reposiciones y devoluciones.')
        cur.execute("""UPDATE caja_chica_movimientos SET estado = 'Anulado', motivo_anulacion = %s, actualizado_por = %s,
                       actualizado_en = NOW(), rendicion_id = NULL, historial = historial || %s WHERE id = %s""",
                    (motivo[:500], _usuario(), _evento('Anulado', motivo=motivo[:500]), mid))
        # Una reposición suelta con pago en Finanzas: se anula también ese pago
        cur.execute("""UPDATE finanzas_pagos SET estado = 'Anulado', anulado_en = NOW(), motivo_anulacion = %s
                       WHERE documento_tabla = 'caja_chica_movimientos' AND documento_id = %s AND estado <> 'Anulado'""",
                    (f'Anulado en Caja chica: {motivo[:200]}', mid))


def _pago_finanzas(cur, eid, tabla, doc_id, doc_numero, conf, fecha, monto, banco, operacion, obs):
    """Registra la salida del banco de la empresa hacia la cuenta de caja chica (para Conciliación bancaria)."""
    cur.execute("""INSERT INTO finanzas_pagos (tipo, documento_tabla, documento_id, documento_numero, tercero_nombre,
                       tercero_documento, fecha, monto, metodo, banco, numero_operacion, observaciones, usuario_id, usuario_nombre)
                   VALUES ('PAGO', %s, %s, %s, %s, %s, %s, %s, 'Transferencia', %s, %s, %s, %s, %s) RETURNING id""",
                (tabla, doc_id, doc_numero, conf['responsable'] or 'Responsable de caja chica', conf['responsable_dni'] or None,
                 fecha, monto, banco, operacion, obs, session.get('usuario_id'), session.get('nombre_completo')))
    pid = cur.fetchone()['id']
    cur.execute("UPDATE finanzas_pagos SET empresa_id = %s WHERE id = %s", (str(eid), pid))
    return pid


def registrar_ingreso(eid, d):
    """Depósito suelto a la caja (gerencia) o devolución de dinero sobrante."""
    tipo = d.get('tipo')
    if tipo not in ('Reposición', 'Devolución'):
        raise ErrorCaja('Elige si es depósito de la empresa o devolución.')
    if tipo == 'Reposición' and not es_admin():
        raise ErrorCaja('Solo la gerencia registra depósitos a la caja chica.')
    fecha = _fecha(d.get('fecha'), 'la fecha')
    if fecha > _ahora().date():
        raise ErrorCaja('La fecha no puede ser futura.')
    monto = _monto(d.get('monto'))
    descripcion = _txt(d, 'descripcion', 500, True, 'la descripción')
    operacion = _txt(d, 'numero_operacion', 80)
    conf = leer_config(eid)
    with db_tx() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        n = _siguiente(cur, 'caja_chica_movimientos', eid)
        cur.execute("""INSERT INTO caja_chica_movimientos (empresa_id, numero, fecha, tipo, descripcion, ingreso, referencia,
                           creado_por, actualizado_por, historial) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    (str(eid), n, fecha, tipo, descripcion, monto, operacion and f'N° operación {operacion}', _usuario(),
                     _usuario(), _evento('Registrado', monto=float(monto))))
        mid = cur.fetchone()['id']
        if tipo == 'Reposición':
            _pago_finanzas(cur, eid, 'caja_chica_movimientos', mid, f'Caja chica N° {n}', conf, fecha, monto,
                           _txt(d, 'banco', 80), operacion, descripcion)
    return n


def lista_movimientos(eid, desde=None, hasta=None, q=None, incluir_anulados=False):
    par = [str(eid)]
    sql = """SELECT m.*, r.numero AS rendicion_numero, r.estado AS rendicion_estado,
                    (SELECT COUNT(*) FROM caja_chica_fotos f WHERE f.movimiento_id = m.id) AS fotos
             FROM caja_chica_movimientos m LEFT JOIN caja_chica_rendiciones r ON r.id = m.rendicion_id
             WHERE m.empresa_id = %s"""
    if not incluir_anulados:
        sql += " AND m.estado = 'Activo'"
    if desde:
        sql += " AND m.fecha >= %s"
        par.append(desde)
    if hasta:
        sql += " AND m.fecha <= %s"
        par.append(hasta)
    if q:
        sql += """ AND (m.descripcion ILIKE %s OR m.quien ILIKE %s OR m.pagado_a ILIKE %s OR m.referencia ILIKE %s
                   OR m.rubro ILIKE %s OR m.comprobante_numero ILIKE %s OR m.numero::text = %s)"""
        par += [f'%{q}%'] * 6 + [q.strip()]
    filas = db_query(sql + " ORDER BY m.fecha, m.numero", par)
    # Saldo acumulado: se calcula sobre todos los movimientos activos, en orden de fecha
    previo = CERO
    if desde:
        previo = saldo(eid, desde - timedelta(days=1))
    salida = []
    acumulado = previo
    for m in filas:
        item = {k: _f(v) for k, v in m.items() if k != 'historial'}
        if m['estado'] == 'Activo':
            acumulado += a_decimal(m['ingreso']) - a_decimal(m['egreso'])
            item['saldo'] = _n(acumulado) if not q else None
        item['historial'] = m['historial'] or []
        item['sustenta'] = m['comprobante_tipo'] in SUSTENTA_SUNAT
        item['bloqueado'] = bool(m['origen'] == 'Histórico' or m['tipo'] != 'Gasto' or
                                 (m['rendicion_id'] and m['rendicion_estado'] != 'Observada') or m['estado'] == 'Anulado')
        salida.append(item)
    return salida, _n(previo)


def resumen(e):
    eid = str(e['id'])
    conf = leer_config(eid)
    s = saldo(eid)
    hoy = _ahora().date()
    ini_mes = hoy.replace(day=1)
    mes = db_query("""SELECT rubro, COUNT(*) AS n, SUM(egreso) AS total,
                             SUM(CASE WHEN comprobante_tipo IN %s THEN 0 ELSE egreso END) AS sin_sustento
                      FROM caja_chica_movimientos WHERE empresa_id = %s AND estado = 'Activo' AND tipo = 'Gasto'
                        AND fecha >= %s GROUP BY rubro ORDER BY SUM(egreso) DESC""", (SUSTENTA_SUNAT, eid, ini_mes))
    pend = db_query("""SELECT COUNT(*) AS n, COALESCE(SUM(egreso), 0) AS t,
                              COUNT(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM caja_chica_fotos f WHERE f.movimiento_id = m.id)
                                               AND comprobante_tipo <> 'Planilla de movilidad') AS sin_foto
                       FROM caja_chica_movimientos m WHERE empresa_id = %s AND estado = 'Activo' AND tipo = 'Gasto'
                         AND origen = 'ERP' AND rendicion_id IS NULL""", (eid,))[0]
    rend = db_query("""SELECT * FROM caja_chica_rendiciones WHERE empresa_id = %s ORDER BY numero DESC LIMIT 30""", (eid,))
    arq = db_query("""SELECT * FROM caja_chica_arqueos WHERE empresa_id = %s ORDER BY fecha DESC, id DESC LIMIT 10""", (eid,))
    total_mes = sum((a_decimal(x['total']) for x in mes), CERO)
    sin_mes = sum((a_decimal(x['sin_sustento']) for x in mes), CERO)
    hist = db_query("""SELECT COUNT(*) AS n, MIN(fecha) AS desde, MAX(fecha) AS hasta FROM caja_chica_movimientos
                       WHERE empresa_id = %s AND origen = 'Histórico'""", (eid,))[0]
    return {
        'empresa': {'id': eid, 'codigo': e['codigo'], 'razon_social': e.get('razon_social'), 'ruc': e.get('ruc')},
        'config': {**conf, 'fondo_fijo': float(conf['fondo_fijo']), 'rmv': float(conf['rmv']),
                   'tope_movilidad': float(tope_movilidad(conf))},
        'saldo': float(s), 'por_reponer': float(max(conf['fondo_fijo'] - s, CERO)),
        'pendientes': {'n': pend['n'], 'total': _n(pend['t']), 'sin_foto': pend['sin_foto']},
        'mes': {'total': float(total_mes), 'sin_sustento': float(sin_mes),
                'por_rubro': [{'rubro': x['rubro'], 'n': x['n'], 'total': _n(x['total'])} for x in mes]},
        'rendiciones': [{**{k: _f(v) for k, v in r.items() if k != 'historial'}, 'historial': r['historial'] or []} for r in rend],
        'arqueos': [{k: _f(v) for k, v in a.items()} for a in arq],
        'historico': {'n': hist['n'], 'desde': _f(hist['desde']), 'hasta': _f(hist['hasta'])},
        'cerrada_hasta': _f(_ultima_aprobada(eid)),
        'hoy': hoy.isoformat(),
    }


# ============================================================
# FOTOS (se guardan reducidas dentro de la base: Render no guarda archivos)
# ============================================================
MAX_FOTO = 8 * 1024 * 1024


def _reducir(contenido, mime):
    if mime == 'application/pdf':
        if len(contenido) > 2 * 1024 * 1024:
            raise ErrorCaja('El PDF pesa más de 2 MB. Mejor sube una foto.')
        return contenido, mime
    try:
        from PIL import Image, ImageOps
        img = Image.open(io.BytesIO(contenido))
        img = ImageOps.exif_transpose(img).convert('RGB')
        img.thumbnail((1400, 1400))
        out = io.BytesIO()
        img.save(out, 'JPEG', quality=72, optimize=True)
        return out.getvalue(), 'image/jpeg'
    except Exception:
        raise ErrorCaja('No se pudo leer la imagen. Sube una foto JPG o PNG (o un PDF).')


def subir_foto(eid, mid, archivo):
    if not archivo or not archivo.filename:
        raise ErrorCaja('Elige la foto del voucher o comprobante.')
    contenido = archivo.read(MAX_FOTO + 1)
    if len(contenido) > MAX_FOTO:
        raise ErrorCaja('La foto pesa más de 8 MB.')
    nombre = archivo.filename.lower()
    mime = 'application/pdf' if nombre.endswith('.pdf') else 'image/jpeg'
    datos, mime = _reducir(contenido, mime)
    with db_tx() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        m = _mov(cur, eid, mid)
        if m['estado'] == 'Anulado':
            raise ErrorCaja('Ese movimiento está anulado.')
        cur.execute("SELECT COUNT(*) AS n FROM caja_chica_fotos WHERE movimiento_id = %s", (mid,))
        if cur.fetchone()['n'] >= 3:
            raise ErrorCaja('Máximo 3 fotos por gasto.')
        cur.execute("""INSERT INTO caja_chica_fotos (movimiento_id, nombre, mime, datos, bytes, subido_por)
                       VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                    (mid, archivo.filename[:150], mime, datos, len(datos), _usuario()))
        cur.execute("UPDATE caja_chica_movimientos SET historial = historial || %s WHERE id = %s",
                    (_evento('Foto subida', archivo=archivo.filename[:150]), mid))


# ============================================================
# RENDICIÓN SEMANAL Y REPOSICIÓN
# ============================================================
def enviar_rendicion(eid, d):
    hasta = _fecha(d.get('hasta') or _ahora().date().isoformat(), 'la fecha de corte')
    with db_tx() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f'caja_chica_rend:{eid}',))
        cur.execute("SELECT numero FROM caja_chica_rendiciones WHERE empresa_id = %s AND estado = 'Por aprobar'", (str(eid),))
        abierta = cur.fetchone()
        if abierta:
            raise ErrorCaja(f'La rendición N° {abierta["numero"]} todavía espera aprobación. Cuando Erika la apruebe u observe, envías la siguiente.')
        cur.execute("""SELECT id, fecha, egreso, comprobante_tipo FROM caja_chica_movimientos
                       WHERE empresa_id = %s AND estado = 'Activo' AND tipo = 'Gasto' AND origen = 'ERP'
                         AND rendicion_id IS NULL AND fecha <= %s FOR UPDATE""", (str(eid), hasta))
        gastos = cur.fetchall()
        if not gastos:
            raise ErrorCaja('No hay gastos nuevos para rendir hasta esa fecha.')
        total = sum((a_decimal(g['egreso']) for g in gastos), CERO)
        sin = sum((a_decimal(g['egreso']) for g in gastos if g['comprobante_tipo'] not in SUSTENTA_SUNAT), CERO)
        n = _siguiente(cur, 'caja_chica_rendiciones', eid)
        cur.execute("""INSERT INTO caja_chica_rendiciones (empresa_id, numero, desde, hasta, total_gastado, sin_sustento,
                           enviada_por, historial) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    (str(eid), n, min(g['fecha'] for g in gastos), hasta, total, sin, _usuario(),
                     _evento('Enviada', total=float(total))))
        rid = cur.fetchone()['id']
        cur.execute("UPDATE caja_chica_movimientos SET rendicion_id = %s WHERE id = ANY(%s)", (rid, [g['id'] for g in gastos]))
    return n, len(gastos), _r(total)


def _rend(cur, eid, rid):
    cur.execute("SELECT * FROM caja_chica_rendiciones WHERE id = %s AND empresa_id = %s FOR UPDATE", (rid, str(eid)))
    r = cur.fetchone()
    if not r:
        raise ErrorCaja('No se encontró esa rendición.')
    return r


def aprobar_rendicion(eid, rid, d):
    if not es_admin():
        raise ErrorCaja('Solo la gerencia aprueba la rendición.')
    fecha = _fecha(d.get('fecha_reposicion') or _ahora().date().isoformat(), 'la fecha de la transferencia')
    if fecha > _ahora().date():
        raise ErrorCaja('La fecha de la transferencia no puede ser futura.')
    operacion = _txt(d, 'numero_operacion', 80)
    conf = leer_config(eid)
    with db_tx() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        r = _rend(cur, eid, rid)
        if r['estado'] != 'Por aprobar':
            raise ErrorCaja(f'Esa rendición está {r["estado"].lower()}.')
        cur.execute("SELECT COALESCE(SUM(ingreso - egreso), 0) AS s FROM caja_chica_movimientos WHERE empresa_id = %s AND estado = 'Activo'",
                    (str(eid),))
        s = _r(cur.fetchone()['s'])
        sugerido = max(conf['fondo_fijo'] - s, CERO)
        monto = _monto(d['monto'], 'el monto a reponer') if d.get('monto') not in (None, '') else sugerido
        movimiento = None
        pago = None
        if monto > 0:
            n = _siguiente(cur, 'caja_chica_movimientos', eid)
            cur.execute("""INSERT INTO caja_chica_movimientos (empresa_id, numero, fecha, tipo, descripcion, ingreso, referencia,
                               rendicion_id, creado_por, actualizado_por, historial)
                           VALUES (%s, %s, %s, 'Reposición', %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                        (str(eid), n, fecha, f'Reposición de la rendición N° {r["numero"]}', monto,
                         operacion and f'N° operación {operacion}', rid, _usuario(), _usuario(),
                         _evento('Registrado', monto=float(monto))))
            movimiento = cur.fetchone()['id']
            pago = _pago_finanzas(cur, eid, 'caja_chica_rendiciones', rid, f'Caja chica · rendición N° {r["numero"]}', conf,
                                  fecha, monto, _txt(d, 'banco', 80), operacion,
                                  f'Reposición del fondo fijo ({r["desde"]:%d/%m} al {r["hasta"]:%d/%m/%Y})')
        cur.execute("""UPDATE caja_chica_rendiciones SET estado = 'Aprobada', revisada_por = %s, revisada_en = NOW(),
                           monto_repuesto = %s, fecha_reposicion = %s, numero_operacion = %s, finanzas_pago_id = %s,
                           observacion = %s, historial = historial || %s WHERE id = %s""",
                    (_usuario(), monto, fecha, operacion, pago, _txt(d, 'observacion', 500),
                     _evento('Aprobada', repuesto=float(monto)), rid))
    return r['numero'], _r(monto)


def observar_rendicion(eid, rid, motivo):
    if not es_admin():
        raise ErrorCaja('Solo la gerencia observa la rendición.')
    motivo = (motivo or '').strip()
    if len(motivo) < 5:
        raise ErrorCaja('Escribe qué hay que corregir.')
    with db_tx() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        r = _rend(cur, eid, rid)
        if r['estado'] != 'Por aprobar':
            raise ErrorCaja(f'Esa rendición está {r["estado"].lower()}.')
        cur.execute("""UPDATE caja_chica_rendiciones SET estado = 'Observada', revisada_por = %s, revisada_en = NOW(),
                           observacion = %s, historial = historial || %s WHERE id = %s""",
                    (_usuario(), motivo[:500], _evento('Observada', motivo=motivo[:500]), rid))
        # Los gastos vuelven a quedar libres para corregirlos y enviarlos de nuevo
        cur.execute("""UPDATE caja_chica_movimientos SET rendicion_id = NULL, historial = historial || %s
                       WHERE rendicion_id = %s AND tipo = 'Gasto'""",
                    (_evento('Liberado', motivo=f'Rendición N° {r["numero"]} observada'), rid))
    return r['numero']


def detalle_rendicion(eid, rid):
    r = db_query("SELECT * FROM caja_chica_rendiciones WHERE id = %s AND empresa_id = %s", (rid, str(eid)))
    if not r:
        raise ErrorCaja('No se encontró esa rendición.')
    r = r[0]
    if r['estado'] == 'Observada':
        gastos = []
    else:
        gastos = db_query("""SELECT m.*, (SELECT COUNT(*) FROM caja_chica_fotos f WHERE f.movimiento_id = m.id) AS fotos
                             FROM caja_chica_movimientos m WHERE rendicion_id = %s AND estado = 'Activo' AND tipo = 'Gasto'
                             ORDER BY fecha, numero""", (rid,))
    por_rubro = {}
    for g in gastos:
        x = por_rubro.setdefault(g['rubro'], {'rubro': g['rubro'], 'n': 0, 'total': CERO, 'sin_sustento': CERO})
        x['n'] += 1
        x['total'] += a_decimal(g['egreso'])
        if g['comprobante_tipo'] not in SUSTENTA_SUNAT:
            x['sin_sustento'] += a_decimal(g['egreso'])
    return r, gastos, sorted(por_rubro.values(), key=lambda x: -x['total'])


# ============================================================
# ARQUEO
# ============================================================
def registrar_arqueo(eid, d):
    fecha = _fecha(d.get('fecha') or _ahora().date().isoformat(), 'la fecha del arqueo')
    if fecha > _ahora().date():
        raise ErrorCaja('La fecha del arqueo no puede ser futura.')
    vals = {}
    for k, nombre in (('efectivo', 'el efectivo'), ('saldo_cuenta', 'el saldo de la cuenta'), ('vales', 'los vales')):
        v = d.get(k)
        try:
            vals[k] = _r(Decimal(str(v).replace(',', '')) if v not in (None, '') else 0)
        except Exception:
            raise ErrorCaja(f'Escribe {nombre} en números.')
        if vals[k] < 0:
            raise ErrorCaja(f'{nombre[0].upper() + nombre[1:]} no puede ser negativo.')
    sistema = saldo(eid, fecha)
    real = vals['efectivo'] + vals['saldo_cuenta'] + vals['vales']
    dif = _r(real - sistema)
    explicacion = _txt(d, 'explicacion', 500)
    if dif != 0 and not explicacion:
        raise ErrorCaja(f'Hay una diferencia de S/ {dif:.2f}: explica por qué antes de guardar.')
    db_query("""INSERT INTO caja_chica_arqueos (empresa_id, fecha, saldo_sistema, efectivo, saldo_cuenta, vales, diferencia,
                    explicacion, hecho_por) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
             (str(eid), fecha, sistema, vals['efectivo'], vals['saldo_cuenta'], vals['vales'], dif, explicacion, _usuario()))
    return sistema, dif


# ============================================================
# IMPORTAR EL HISTÓRICO (plantilla Excel de 22/10/2026, hoja "Movimientos")
# ============================================================
def leer_historico(contenido):
    """Lee la hoja Movimientos de la plantilla. Devuelve (saldo_inicial, fecha_inicial, filas)."""
    import openpyxl
    try:
        wb = openpyxl.load_workbook(io.BytesIO(contenido), data_only=True, read_only=True)
    except Exception:
        raise ErrorCaja('No se pudo abrir el Excel. Usa la plantilla de caja chica (.xlsx).')
    if 'Movimientos' not in wb.sheetnames:
        raise ErrorCaja('El Excel no tiene la hoja "Movimientos" de la plantilla de caja chica.')
    ws = wb['Movimientos']
    cab = [str(c.value or '').strip().lower() for c in next(ws.iter_rows(min_row=3, max_row=3))]

    def col(texto):
        for i, c in enumerate(cab):
            if c.startswith(texto):
                return i
        raise ErrorCaja(f'Falta la columna "{texto}" en la hoja Movimientos.')
    ix = {k: col(t) for k, t in (('fecha', 'fecha'), ('empresa', 'empresa'), ('tipo', 'tipo'), ('rubro', 'rubro'),
                                  ('quien', 'quién gastó'), ('pagado', 'pagado a'), ('desc', 'descripción'),
                                  ('ref', 'n° pc'), ('comp', 'tipo de comprobante'), ('ncomp', 'n° comprobante'),
                                  ('ing', 'ingreso'), ('eg', 'egreso'), ('obs', 'observación'))}
    inicial = None
    filas = []
    for i, row in enumerate(ws.iter_rows(min_row=4, values_only=True), start=4):
        v = lambda k: row[ix[k]] if ix[k] < len(row) else None
        ing, eg, desc = v('ing'), v('eg'), v('desc')
        if ing in (None, '') and eg in (None, ''):
            continue
        f = v('fecha')
        if isinstance(f, datetime):
            f = f.date()
        if not isinstance(f, date):
            raise ErrorCaja(f'Fila {i}: falta la fecha.')
        try:
            ing = _r(ing or 0)
            eg = _r(eg or 0)
        except Exception:
            raise ErrorCaja(f'Fila {i}: el monto no es un número.')
        if inicial is None:
            inicial = (f, ing - eg, str(desc or 'Saldo inicial'))
            continue
        if eg < 0 or ing < 0:          # signo invertido en el Excel: se respeta su efecto en el saldo
            ing, eg = max(ing, CERO) + max(-eg, CERO), max(eg, CERO) + max(-ing, CERO)
        if (ing > 0) == (eg > 0):
            raise ErrorCaja(f'Fila {i}: debe tener ingreso o egreso, no los dos.')
        tipo = str(v('tipo') or '').strip()
        tipo = 'Gasto' if eg > 0 else ('Devolución' if tipo.lower().startswith('devol') else 'Reposición')
        rubro = v('rubro') if v('rubro') in RUBROS else (('Otros (explicar)') if eg > 0 else None)
        comp = v('comp')
        comp = comp if comp in COMPROBANTES else (COMPROBANTE_HISTORICO if eg > 0 else None)
        filas.append({'fecha': f, 'tipo': tipo, 'empresa_gasto': (str(v('empresa') or '').upper()[:10] or None),
                      'rubro': rubro, 'quien': (str(v('quien')).strip()[:150] if v('quien') else None),
                      'pagado_a': (str(v('pagado')).strip()[:150] if v('pagado') else None),
                      'descripcion': str(desc or '(sin descripción)').strip()[:500],
                      'referencia': (str(v('ref')).strip()[:150] if v('ref') else None),
                      'comprobante_tipo': comp, 'comprobante_numero': (str(v('ncomp')).strip()[:40] if v('ncomp') else None),
                      'ingreso': ing, 'egreso': eg, 'observacion': (str(v('obs')).strip()[:500] if v('obs') else None)})
    if inicial is None or not filas:
        raise ErrorCaja('La hoja Movimientos está vacía.')
    return inicial, filas


def importar_historico(eid, contenido, confirmar=False):
    if not es_admin():
        raise ErrorCaja('Solo la gerencia importa el histórico.')
    inicial, filas = leer_historico(contenido)
    final = inicial[1] + sum((x['ingreso'] - x['egreso'] for x in filas), CERO)
    vista = {'filas': len(filas), 'desde': inicial[0].isoformat(), 'hasta': max(x['fecha'] for x in filas).isoformat(),
             'saldo_inicial': float(inicial[1]), 'saldo_final': float(_r(final)),
             'gastos': float(sum((x['egreso'] for x in filas), CERO)),
             'ingresos': float(sum((x['ingreso'] for x in filas), CERO))}
    if not confirmar:
        return vista
    with db_tx() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f'caja_chica_movimientos:{eid}',))
        cur.execute("SELECT COUNT(*) AS n FROM caja_chica_movimientos WHERE empresa_id = %s", (str(eid),))
        if cur.fetchone()['n']:
            raise ErrorCaja('Esta caja ya tiene movimientos: el histórico solo se importa una vez, en una caja vacía.')
        ev = _evento('Importado del Excel')
        cur.execute("""INSERT INTO caja_chica_movimientos (empresa_id, numero, fecha, tipo, descripcion, ingreso, egreso, origen,
                           creado_por, actualizado_por, historial) VALUES (%s, 1, %s, 'Saldo inicial', %s, %s, %s, 'Histórico', %s, %s, %s)""",
                    (str(eid), inicial[0], inicial[2][:500], max(inicial[1], CERO), max(-inicial[1], CERO), _usuario(), _usuario(), ev))
        for n, x in enumerate(filas, start=2):
            cur.execute("""INSERT INTO caja_chica_movimientos (empresa_id, numero, fecha, tipo, empresa_gasto, rubro, quien,
                               pagado_a, descripcion, referencia, comprobante_tipo, comprobante_numero, ingreso, egreso,
                               observacion, origen, creado_por, actualizado_por, historial)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Histórico', %s, %s, %s)""",
                        (str(eid), n, x['fecha'], x['tipo'], x['empresa_gasto'], x['rubro'], x['quien'], x['pagado_a'],
                         x['descripcion'], x['referencia'], x['comprobante_tipo'], x['comprobante_numero'], x['ingreso'],
                         x['egreso'], x['observacion'], _usuario(), _usuario(), ev))
    return vista


# ============================================================
# RUTAS
# ============================================================
def _err(ex, codigo=400):
    return jsonify({'success': False, 'error': str(ex)}), codigo


def _json():
    return request.get_json(silent=True) or {}


@caja_chica_bp.route('/caja-chica')
def pagina():
    emps = [{'id': x['id'], 'codigo': x['codigo']} for x in lista_empresas()]
    activa = empresa_actual()
    return render_template('caja_chica.html', empresas=emps, empresa_activa=activa['id'] if activa else None,
                           es_admin=es_admin(), rubros=RUBROS, comprobantes=COMPROBANTES, tipos_persona=TIPOS_PERSONA,
                           con_numero=CON_NUMERO, sustenta=SUSTENTA_SUNAT, tope_aviso=float(TOPE_AVISO))


@caja_chica_bp.route('/caja-chica/api/resumen')
def api_resumen():
    try:
        return jsonify({'success': True, 'data': resumen(_empresa(request.args.get('empresa_id')))})
    except ErrorCaja as ex:
        return _err(ex)


@caja_chica_bp.route('/caja-chica/api/movimientos')
def api_movimientos():
    try:
        e = _empresa(request.args.get('empresa_id'))
        desde = _fecha(request.args.get('desde'), 'la fecha desde', obligatorio=False)
        hasta = _fecha(request.args.get('hasta'), 'la fecha hasta', obligatorio=False)
        filas, previo = lista_movimientos(str(e['id']), desde, hasta, (request.args.get('q') or '').strip() or None,
                                          request.args.get('anulados') == '1')
        return jsonify({'success': True, 'data': {'filas': filas, 'saldo_anterior': previo}})
    except ErrorCaja as ex:
        return _err(ex)


@caja_chica_bp.route('/caja-chica/api/gasto', methods=['POST'])
@caja_chica_bp.route('/caja-chica/api/gasto/<int:mid>', methods=['PUT'])
def api_gasto(mid=None):
    try:
        d = _json()
        e = _empresa(d.get('empresa_id'))
        if mid:
            avisos = editar_gasto(str(e['id']), mid, d)
            return jsonify({'success': True, 'message': 'Gasto actualizado.', 'avisos': avisos})
        nuevo, n, avisos = registrar_gasto(str(e['id']), d)
        return jsonify({'success': True, 'id': nuevo, 'numero': n, 'message': f'Gasto N° {n} registrado.', 'avisos': avisos})
    except ErrorCaja as ex:
        return _err(ex)


@caja_chica_bp.route('/caja-chica/api/ingreso', methods=['POST'])
def api_ingreso():
    try:
        d = _json()
        e = _empresa(d.get('empresa_id'))
        n = registrar_ingreso(str(e['id']), d)
        return jsonify({'success': True, 'message': f'Movimiento N° {n} registrado.'})
    except ErrorCaja as ex:
        return _err(ex)


@caja_chica_bp.route('/caja-chica/api/movimiento/<int:mid>/anular', methods=['POST'])
def api_anular(mid):
    try:
        d = _json()
        anular_movimiento(str(_empresa(d.get('empresa_id'))['id']), mid, d.get('motivo'))
        return jsonify({'success': True, 'message': 'Anulado.'})
    except ErrorCaja as ex:
        return _err(ex)


@caja_chica_bp.route('/caja-chica/api/movimiento/<int:mid>/foto', methods=['POST'])
def api_subir_foto(mid):
    try:
        e = _empresa(request.form.get('empresa_id'))
        subir_foto(str(e['id']), mid, request.files.get('foto'))
        return jsonify({'success': True, 'message': 'Foto guardada.'})
    except ErrorCaja as ex:
        return _err(ex)


@caja_chica_bp.route('/caja-chica/api/movimiento/<int:mid>/fotos')
def api_fotos(mid):
    e = _empresa(request.args.get('empresa_id'))
    filas = db_query("""SELECT f.id, f.nombre, f.mime, f.bytes, f.subido_por, f.subido_en FROM caja_chica_fotos f
                        JOIN caja_chica_movimientos m ON m.id = f.movimiento_id
                        WHERE f.movimiento_id = %s AND m.empresa_id = %s ORDER BY f.id""", (mid, str(e['id'])))
    return jsonify({'success': True, 'data': [{k: _f(v) for k, v in f.items()} for f in filas]})


@caja_chica_bp.route('/caja-chica/foto/<int:fid>')
def ver_foto(fid):
    f = db_query("""SELECT f.mime, f.datos, m.empresa_id FROM caja_chica_fotos f
                    JOIN caja_chica_movimientos m ON m.id = f.movimiento_id WHERE f.id = %s""", (fid,))
    if not f or not any(str(x['id']) == str(f[0]['empresa_id']) for x in lista_empresas()):
        return Response('No encontrada', status=404)
    return Response(bytes(f[0]['datos']), mimetype=f[0]['mime'], headers={'Cache-Control': 'private, max-age=86400'})


@caja_chica_bp.route('/caja-chica/api/rendicion', methods=['POST'])
def api_enviar_rendicion():
    try:
        d = _json()
        n, cant, total = enviar_rendicion(str(_empresa(d.get('empresa_id'))['id']), d)
        return jsonify({'success': True, 'message': f'Rendición N° {n} enviada a Erika: {cant} gastos por S/ {total:,.2f}.'})
    except ErrorCaja as ex:
        return _err(ex)


@caja_chica_bp.route('/caja-chica/api/rendicion/<int:rid>')
def api_rendicion(rid):
    try:
        e = _empresa(request.args.get('empresa_id'))
        r, gastos, rubros = detalle_rendicion(str(e['id']), rid)
        return jsonify({'success': True, 'data': {
            'rendicion': {**{k: _f(v) for k, v in r.items() if k != 'historial'}, 'historial': r['historial'] or []},
            'gastos': [{k: _f(v) for k, v in g.items() if k != 'historial'} for g in gastos],
            'por_rubro': [{k: _f(v) for k, v in x.items()} for x in rubros],
            'saldo': float(saldo(str(e['id']))), 'fondo_fijo': float(leer_config(str(e['id']))['fondo_fijo'])}})
    except ErrorCaja as ex:
        return _err(ex)


@caja_chica_bp.route('/caja-chica/api/rendicion/<int:rid>/aprobar', methods=['POST'])
def api_aprobar(rid):
    try:
        d = _json()
        n, monto = aprobar_rendicion(str(_empresa(d.get('empresa_id'))['id']), rid, d)
        return jsonify({'success': True, 'message': f'Rendición N° {n} aprobada. Reposición: S/ {monto:,.2f}.'})
    except ErrorCaja as ex:
        return _err(ex)


@caja_chica_bp.route('/caja-chica/api/rendicion/<int:rid>/observar', methods=['POST'])
def api_observar(rid):
    try:
        d = _json()
        n = observar_rendicion(str(_empresa(d.get('empresa_id'))['id']), rid, d.get('motivo'))
        return jsonify({'success': True, 'message': f'Rendición N° {n} observada: sus gastos vuelven a Hellen para corregir.'})
    except ErrorCaja as ex:
        return _err(ex)


@caja_chica_bp.route('/caja-chica/api/arqueo', methods=['POST'])
def api_arqueo():
    try:
        d = _json()
        sistema, dif = registrar_arqueo(str(_empresa(d.get('empresa_id'))['id']), d)
        msg = 'Arqueo guardado: ✔ cuadra.' if dif == 0 else f'Arqueo guardado con diferencia de S/ {dif:,.2f}.'
        return jsonify({'success': True, 'message': msg})
    except ErrorCaja as ex:
        return _err(ex)


@caja_chica_bp.route('/caja-chica/api/personas')
def api_personas():
    e = _empresa(request.args.get('empresa_id'))
    return jsonify({'success': True, 'data': [{k: _f(v) for k, v in p.items()} for p in personas(str(e['id']))]})


@caja_chica_bp.route('/caja-chica/api/personas', methods=['POST'])
@caja_chica_bp.route('/caja-chica/api/personas/<int:pid>', methods=['PUT'])
def api_guardar_persona(pid=None):
    try:
        d = _json()
        e = _empresa(d.get('empresa_id'))
        nuevo = guardar_persona(str(e['id']), d, pid)
        return jsonify({'success': True, 'id': nuevo, 'message': 'Guardado.'})
    except ErrorCaja as ex:
        return _err(ex)


@caja_chica_bp.route('/caja-chica/api/config', methods=['POST'])
def api_config():
    if not es_admin():
        return _err('Solo la gerencia cambia el fondo fijo y el responsable.', 403)
    try:
        d = _json()
        e = _empresa(d.get('empresa_id'))
        fondo = _monto(d.get('fondo_fijo'), 'el fondo fijo')
        rmv = _monto(d.get('rmv') or RMV_POR_DEFECTO, 'el sueldo mínimo')
        if not Decimal('900') <= rmv <= Decimal('3000'):
            raise ErrorCaja('El sueldo mínimo no es válido.')
        dni = re.sub(r'\D', '', str(d.get('responsable_dni') or ''))[:15] or None
        db_query("""INSERT INTO caja_chica_config (empresa_id, fondo_fijo, responsable, responsable_dni, cuenta, rmv,
                        actualizado_por, actualizado_en) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (empresa_id) DO UPDATE SET fondo_fijo = EXCLUDED.fondo_fijo, responsable = EXCLUDED.responsable,
                        responsable_dni = EXCLUDED.responsable_dni, cuenta = EXCLUDED.cuenta, rmv = EXCLUDED.rmv,
                        actualizado_por = EXCLUDED.actualizado_por, actualizado_en = NOW() RETURNING empresa_id""",
                 (str(e['id']), fondo, _txt(d, 'responsable', 150, True, 'el responsable'), dni,
                  _txt(d, 'cuenta', 150), rmv, _usuario()))
        return jsonify({'success': True, 'message': 'Configuración guardada.'})
    except ErrorCaja as ex:
        return _err(ex)


@caja_chica_bp.route('/caja-chica/api/importar', methods=['POST'])
def api_importar():
    try:
        e = _empresa(request.form.get('empresa_id'))
        arch = request.files.get('archivo')
        if not arch or not arch.filename.lower().endswith('.xlsx'):
            raise ErrorCaja('Sube la plantilla de caja chica (.xlsx).')
        vista = importar_historico(str(e['id']), arch.read(), request.form.get('confirmar') == '1')
        return jsonify({'success': True, 'data': vista})
    except ErrorCaja as ex:
        return _err(ex)


# ============================================================
# IMPRESOS (se abren en una pestaña y se imprimen con Ctrl+P)
# ============================================================
def _letras(monto):
    try:
        from pdf_generator import PDFGenerator
        return PDFGenerator().numero_a_letras(float(monto))
    except Exception:
        return f'{monto:,.2f} SOLES'


@caja_chica_bp.route('/caja-chica/imprimir/vale/<int:mid>')
def imprimir_vale(mid):
    e = _empresa(request.args.get('empresa_id'))
    m = db_query("SELECT * FROM caja_chica_movimientos WHERE id = %s AND empresa_id = %s", (mid, str(e['id'])))
    if not m:
        return Response('No encontrado', status=404)
    return render_template('caja_chica_imprimir.html', doc='vale', e=e, m=m[0], letras=_letras(m[0]['egreso'] or m[0]['ingreso']),
                           conf=leer_config(str(e['id'])), ahora=_ahora())


@caja_chica_bp.route('/caja-chica/imprimir/movilidad')
def imprimir_movilidad():
    """Una planilla por persona (cada uno firma la suya) con sus pasajes del periodo."""
    try:
        e = _empresa(request.args.get('empresa_id'))
        desde = _fecha(request.args.get('desde'), 'la fecha desde')
        hasta = _fecha(request.args.get('hasta'), 'la fecha hasta')
    except ErrorCaja as ex:
        return Response(str(ex), status=400)
    conf = leer_config(str(e['id']))
    filas = db_query("""SELECT m.*, p.dni, p.tipo AS tipo_persona FROM caja_chica_movimientos m
                        JOIN caja_chica_personas p ON p.id = m.quien_id
                        WHERE m.empresa_id = %s AND m.estado = 'Activo' AND m.comprobante_tipo = 'Planilla de movilidad'
                          AND m.fecha BETWEEN %s AND %s ORDER BY m.quien, m.fecha, m.numero""", (str(e['id']), desde, hasta))
    tope = tope_movilidad(conf)
    planillas = {}
    for f in filas:
        p = planillas.setdefault(f['quien_id'], {'nombre': f['quien'], 'dni': f['dni'], 'tipo': f['tipo_persona'],
                                                 'filas': [], 'total': CERO, 'dias': {}})
        p['filas'].append(f)
        p['total'] += a_decimal(f['egreso'])
        p['dias'][f['fecha']] = p['dias'].get(f['fecha'], CERO) + a_decimal(f['egreso'])
    for p in planillas.values():
        p['excede'] = {d: t for d, t in p['dias'].items() if t > tope}
        p['deducible'] = sum((min(t, tope) for t in p['dias'].values()), CERO)
    return render_template('caja_chica_imprimir.html', doc='movilidad', e=e, conf=conf, planillas=list(planillas.values()),
                           desde=desde, hasta=hasta, tope=tope, ahora=_ahora())


@caja_chica_bp.route('/caja-chica/imprimir/rendicion/<int:rid>')
def imprimir_rendicion(rid):
    e = _empresa(request.args.get('empresa_id'))
    try:
        r, gastos, rubros = detalle_rendicion(str(e['id']), rid)
    except ErrorCaja as ex:
        return Response(str(ex), status=404)
    return render_template('caja_chica_imprimir.html', doc='rendicion', e=e, r=r, gastos=gastos, rubros=rubros,
                           conf=leer_config(str(e['id'])), sustenta=SUSTENTA_SUNAT, ahora=_ahora())


@caja_chica_bp.route('/caja-chica/imprimir/acta')
def imprimir_acta():
    e = _empresa(request.args.get('empresa_id'))
    conf = leer_config(str(e['id']))
    return render_template('caja_chica_imprimir.html', doc='acta', e=e, conf=conf, letras=_letras(conf['fondo_fijo']),
                           ahora=_ahora())
