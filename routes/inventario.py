# routes/inventario.py - Módulo de Inventario multiempresa y multisede
#
# Idea central (pensada para personal nuevo):
#   - El stock se guarda por EMPRESA (dueña legal: KCF, AGD, ...) y por SEDE física
#     (San Martín de Porres, Breña, ...). Empresas y sedes son datos configurables:
#     empresas = tabla erp_empresas, sedes = tabla almacenes (Maestros).
#   - Nada se edita ni se borra: todo cambio de stock es un MOVIMIENTO del kardex con
#     motivo, documento, usuario y fecha. Un error se corrige con un movimiento de reversa.
#   - Separación de funciones: quien envía un traslado no lo recibe, quien cuenta no aprueba
#     su conteo, y las pérdidas, robos, mermas y stock inicial necesitan aprobación.
#   - Separaciones (reservas): el stock separado para un cliente no se puede entregar a otro.
#
# Tablas nuevas (se crean solas, no tocan datos existentes): ver migrations/003_inventario.sql
import os
import random
import threading
from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import Blueprint, render_template, request, jsonify, session, Response
from psycopg2.extras import RealDictCursor

from database import db_query, db_tx
from utils import a_decimal, redondear, es_admin, es_aprobador, rol_actual, bloquear_numeracion, id_empresa

inventario_bp = Blueprint('inventario', __name__, url_prefix='/inventario')


def _roles(nombre, por_defecto):
    return {r.strip().lower() for r in os.environ.get(nombre, por_defecto).split(',') if r.strip()}


# Personal de almacén / logística: registra entradas, salidas y traslados
ROLES_ALMACEN = _roles('ROLES_ALMACEN', 'almacen,almacenero,logistica,logistico')
# Personal de control (NO logística): hace los conteos físicos
ROLES_CONTROL_INVENTARIO = _roles('ROLES_CONTROL_INVENTARIO', 'control,inventario,auditor,contabilidad,finanzas')

DIAS_LENTO = int(os.environ.get('INV_DIAS_LENTO', '30'))
DIAS_INMOVILIZADO = int(os.environ.get('INV_DIAS_INMOVILIZADO', '90'))
DIAS_SEPARACION = int(os.environ.get('INV_DIAS_SEPARACION', '7'))
DIAS_AVISO_VENCIMIENTO = int(os.environ.get('INV_DIAS_AVISO_VENCIMIENTO', '30'))
PRODUCTOS_CONTEO_SORPRESA = int(os.environ.get('INV_PRODUCTOS_CONTEO_SORPRESA', '10'))

# Motivos de movimiento: código -> (tipo, texto para el usuario, código de operación SUNAT tabla 12,
#                                    requiere aprobación, requiere documento)
MOTIVOS = {
    'COMPRA':               ('ENTRADA', 'Compra a proveedor',           '02', False, True),
    'DEVOLUCION_CLIENTE':   ('ENTRADA', 'Devolución de cliente',        '05', False, True),
    'STOCK_INICIAL':        ('ENTRADA', 'Stock inicial',                '16', True,  False),
    'TRASLADO_ENTRADA':     ('ENTRADA', 'Llegada de traslado',          '11', False, False),
    'INTERCOMPANY_ENTRADA': ('ENTRADA', 'Compra a empresa del grupo',   '02', False, False),
    'SOBRANTE_CONTEO':      ('ENTRADA', 'Sobrante en conteo',           '99', False, False),
    'REVERSA_ENTRADA':      ('ENTRADA', 'Corrección (reversa)',         '99', False, False),
    'VENTA':                ('SALIDA',  'Entrega a cliente (venta)',    '01', False, True),
    'DEVOLUCION_PROVEEDOR': ('SALIDA',  'Devolución a proveedor',       '06', False, True),
    'TRASLADO_SALIDA':      ('SALIDA',  'Salida por traslado',          '11', False, False),
    'INTERCOMPANY_SALIDA':  ('SALIDA',  'Venta a empresa del grupo',    '01', False, False),
    'FALTANTE_TRASLADO':    ('SALIDA',  'Faltante al recibir traslado', '99', False, False),
    'MERMA':                ('SALIDA',  'Merma o daño',                 '14', True,  False),
    'VENCIMIENTO':          ('SALIDA',  'Producto vencido',             '14', True,  False),
    'PERDIDA_ROBO':         ('SALIDA',  'Pérdida o robo',               '99', True,  False),
    'FALTANTE_CONTEO':      ('SALIDA',  'Faltante en conteo',           '99', False, False),
    'REVERSA_SALIDA':       ('SALIDA',  'Corrección (reversa)',         '99', False, False),
}
# Lo que el usuario puede elegir en cada formulario (el resto lo generan traslados, conteos, etc.)
MOTIVOS_ENTRADA_MANUAL = ('COMPRA', 'DEVOLUCION_CLIENTE', 'STOCK_INICIAL')
MOTIVOS_SALIDA_MANUAL = ('VENTA', 'DEVOLUCION_PROVEEDOR')
MOTIVOS_PROBLEMA = ('MERMA', 'VENCIMIENTO', 'PERDIDA_ROBO')
MOTIVOS_VENTA = ('VENTA', 'INTERCOMPANY_SALIDA')


class ErrorInventario(Exception):
    """Error de negocio con mensaje claro para el usuario."""


# ============================================================
# TABLAS (se crean solas; script equivalente en migrations/003_inventario.sql)
# ============================================================
SQL_DDL_INVENTARIO = """
    CREATE TABLE IF NOT EXISTS inv_sede_empresa (
        id SERIAL PRIMARY KEY,
        almacen_id INTEGER NOT NULL,
        empresa_id INTEGER NOT NULL,
        registrado_sunat BOOLEAN NOT NULL DEFAULT false,
        codigo_establecimiento VARCHAR(10),
        es_domicilio_fiscal BOOLEAN NOT NULL DEFAULT false,
        observaciones TEXT,
        updated_at TIMESTAMP DEFAULT NOW(),
        UNIQUE (almacen_id, empresa_id)
    );
    CREATE TABLE IF NOT EXISTS inv_stock (
        empresa_id INTEGER NOT NULL,
        almacen_id INTEGER NOT NULL,
        producto_id INTEGER NOT NULL,
        cantidad NUMERIC(14,4) NOT NULL DEFAULT 0 CHECK (cantidad >= 0),
        costo_promedio NUMERIC(16,6) NOT NULL DEFAULT 0,
        valor NUMERIC(16,4) NOT NULL DEFAULT 0,
        ultimo_ingreso TIMESTAMP,
        ultima_salida TIMESTAMP,
        ultimo_movimiento TIMESTAMP,
        PRIMARY KEY (empresa_id, almacen_id, producto_id)
    );
    CREATE TABLE IF NOT EXISTS inv_movimientos (
        id SERIAL PRIMARY KEY,
        numero VARCHAR(30) UNIQUE,
        fecha TIMESTAMP NOT NULL DEFAULT NOW(),
        empresa_id INTEGER NOT NULL,
        almacen_id INTEGER NOT NULL,
        producto_id INTEGER NOT NULL,
        tipo VARCHAR(10) NOT NULL CHECK (tipo IN ('ENTRADA', 'SALIDA')),
        motivo VARCHAR(30) NOT NULL,
        cantidad NUMERIC(14,4) NOT NULL CHECK (cantidad > 0),
        costo_unitario NUMERIC(16,6) DEFAULT 0,
        costo_total NUMERIC(16,4) DEFAULT 0,
        saldo_cantidad NUMERIC(14,4),
        saldo_costo_promedio NUMERIC(16,6),
        saldo_valor NUMERIC(16,4),
        documento_tipo VARCHAR(30),
        documento_numero VARCHAR(60),
        tercero VARCHAR(255),
        lote_serie VARCHAR(120),
        fecha_vencimiento DATE,
        traslado_id INTEGER,
        conteo_id INTEGER,
        separacion_id INTEGER,
        recepcion_id INTEGER,
        grupo VARCHAR(30),
        revierte_id INTEGER,
        revertido_por_id INTEGER,
        estado VARCHAR(20) NOT NULL DEFAULT 'Registrado',
        observaciones TEXT,
        usuario_id INTEGER,
        usuario_nombre VARCHAR(150),
        aprobado_por VARCHAR(150),
        aprobado_en TIMESTAMP,
        motivo_rechazo TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_inv_mov_prod ON inv_movimientos (producto_id, empresa_id, almacen_id, id);
    CREATE INDEX IF NOT EXISTS idx_inv_mov_estado ON inv_movimientos (estado);
    CREATE INDEX IF NOT EXISTS idx_inv_mov_recepcion ON inv_movimientos (recepcion_id);
    CREATE TABLE IF NOT EXISTS inv_traslados (
        id SERIAL PRIMARY KEY,
        numero VARCHAR(30) UNIQUE,
        fecha TIMESTAMP NOT NULL DEFAULT NOW(),
        empresa_id INTEGER NOT NULL,
        origen_id INTEGER NOT NULL,
        destino_id INTEGER NOT NULL,
        estado VARCHAR(30) NOT NULL DEFAULT 'En camino',
        guia_remision VARCHAR(40),
        encargado VARCHAR(150),
        observaciones TEXT,
        enviado_por_id INTEGER,
        enviado_por VARCHAR(150),
        recibido_por_id INTEGER,
        recibido_por VARCHAR(150),
        recibido_en TIMESTAMP,
        observaciones_recepcion TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS inv_traslado_items (
        id SERIAL PRIMARY KEY,
        traslado_id INTEGER NOT NULL REFERENCES inv_traslados(id),
        producto_id INTEGER NOT NULL,
        cantidad NUMERIC(14,4) NOT NULL CHECK (cantidad > 0),
        cantidad_recibida NUMERIC(14,4),
        costo_unitario NUMERIC(16,6) DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS inv_separaciones (
        id SERIAL PRIMARY KEY,
        numero VARCHAR(30) UNIQUE,
        empresa_id INTEGER NOT NULL,
        almacen_id INTEGER NOT NULL,
        producto_id INTEGER NOT NULL,
        cantidad NUMERIC(14,4) NOT NULL CHECK (cantidad >= 0),
        cantidad_inicial NUMERIC(14,4) NOT NULL,
        cliente VARCHAR(255) NOT NULL,
        documento VARCHAR(60),
        vence_el DATE NOT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'Activa',
        observaciones TEXT,
        usuario_id INTEGER,
        usuario_nombre VARCHAR(150),
        cerrado_por VARCHAR(150),
        cerrado_en TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_inv_sep_activa ON inv_separaciones (producto_id, empresa_id, almacen_id) WHERE estado = 'Activa';
    CREATE TABLE IF NOT EXISTS inv_conteos (
        id SERIAL PRIMARY KEY,
        numero VARCHAR(30) UNIQUE,
        fecha TIMESTAMP NOT NULL DEFAULT NOW(),
        empresa_id INTEGER NOT NULL,
        almacen_id INTEGER NOT NULL,
        tipo VARCHAR(20) NOT NULL DEFAULT 'General',
        estado VARCHAR(20) NOT NULL DEFAULT 'En conteo',
        creado_por VARCHAR(150),
        contado_por_id INTEGER,
        contado_por VARCHAR(150),
        contado_en TIMESTAMP,
        aprobado_por VARCHAR(150),
        aprobado_en TIMESTAMP,
        observaciones TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS inv_conteo_items (
        id SERIAL PRIMARY KEY,
        conteo_id INTEGER NOT NULL REFERENCES inv_conteos(id),
        producto_id INTEGER NOT NULL,
        cantidad_contada NUMERIC(14,4),
        stock_sistema NUMERIC(14,4),
        costo_promedio NUMERIC(16,6),
        comentario TEXT
    );
"""

_tablas_listas = False
_lock_tablas = threading.Lock()


def ddl_con_tipo_empresa(cur, sql):
    """empresa_id usa el mismo tipo que erp_empresas.id (UUID en Supabase, INTEGER en bases antiguas)."""
    cur.execute("""SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a
                   WHERE a.attrelid = to_regclass('erp_empresas') AND a.attname = 'id'""")
    fila = cur.fetchone()
    tipo = 'UUID' if fila and fila[0] == 'uuid' else 'INTEGER'
    return sql.replace('empresa_id INTEGER', f'empresa_id {tipo}')


def asegurar_tablas_inventario():
    global _tablas_listas
    if _tablas_listas:
        return
    with _lock_tablas:
        if _tablas_listas:
            return
        with db_tx() as conn:
            cur = conn.cursor()
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('inventario_ddl'))")
            cur.execute(ddl_con_tipo_empresa(cur, SQL_DDL_INVENTARIO))
        _tablas_listas = True


@inventario_bp.before_request
def _antes():
    asegurar_tablas_inventario()


# ============================================================
# PERMISOS
# ============================================================
def puede_operar():
    """Registrar entradas, salidas, traslados y ventas intercompany."""
    return es_admin() or es_aprobador() or rol_actual() in ROLES_ALMACEN


def puede_contar():
    """Contar el stock físico. A propósito NO incluye a logística."""
    return es_admin() or es_aprobador() or rol_actual() in ROLES_CONTROL_INVENTARIO


def puede_aprobar():
    return es_admin() or es_aprobador()


def _usuario():
    return session.get('usuario_id'), (session.get('nombre_completo') or session.get('usuario') or 'Usuario')


def _no_autorizado(msg):
    return jsonify({'success': False, 'error': msg}), 403


# ============================================================
# UTILIDADES
# ============================================================
def _fmt(v):
    if isinstance(v, datetime):
        return v.strftime('%Y-%m-%d %H:%M')
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


def _fila(d):
    return {k: _fmt(v) for k, v in d.items()}


def _num(valor, nombre='La cantidad'):
    n = a_decimal(valor)
    if n <= 0:
        raise ErrorInventario(f'{nombre} debe ser mayor que 0.')
    return n


def _entero(valor, nombre):
    try:
        n = int(valor)
        if n > 0:
            return n
    except (TypeError, ValueError):
        pass
    raise ErrorInventario(f'Selecciona {nombre}.')


def _empresa(valor, nombre='la empresa'):
    """Id de empresa válido: UUID (Supabase) o entero (bases antiguas)."""
    eid = id_empresa(valor)
    if eid is None:
        raise ErrorInventario(f'Selecciona {nombre}.')
    return eid


def _siguiente_numero(cur, prefijo, tabla, columna='numero'):
    """Número correlativo diario, sin duplicados aunque dos personas guarden a la vez: MOV-20261013-0001."""
    bloquear_numeracion(cur, f'inv_{prefijo}')
    base = f"{prefijo}-{datetime.now().strftime('%Y%m%d')}-"
    cur.execute(f"SELECT {columna} AS numero FROM {tabla} WHERE {columna} LIKE %s ORDER BY {columna} DESC LIMIT 1",
                (base + '%',))
    fila = cur.fetchone()
    ultimo = 0
    if fila:
        num = fila['numero'] if isinstance(fila, dict) else fila[0]
        try:
            ultimo = int(num.rsplit('-', 1)[1])
        except (ValueError, IndexError):
            ultimo = 0
    return f'{base}{ultimo + 1:04d}'


def _empresas():
    filas = db_query("""
        SELECT id, codigo, COALESCE(NULLIF(nombre_corto, ''), codigo, razon_social) AS nombre,
               razon_social, ruc, direccion_fiscal, color_primario
        FROM erp_empresas
        WHERE COALESCE(LOWER(estado), 'activo') NOT IN ('inactivo', 'inactiva', 'anulado')
        ORDER BY id
    """)
    return [_fila(f) for f in filas]


def _sedes():
    filas = db_query("""
        SELECT id, codigo, nombre, direccion, responsable, tipo
        FROM almacenes WHERE COALESCE(activo, true) = true ORDER BY id
    """)
    return [_fila(f) for f in filas]


def _validar_empresa_sede(cur, empresa_id, almacen_id):
    cur.execute("SELECT id FROM erp_empresas WHERE id = %s", (empresa_id,))
    if not cur.fetchone():
        raise ErrorInventario('La empresa no existe.')
    cur.execute("SELECT id FROM almacenes WHERE id = %s AND COALESCE(activo, true) = true", (almacen_id,))
    if not cur.fetchone():
        raise ErrorInventario('La sede no existe o está inactiva.')


def _producto(cur, producto_id):
    cur.execute("SELECT id, codigo, descripcion, unidad, COALESCE(costo_unitario, 0) AS costo_unitario, "
                "COALESCE(stock, 0) AS stock FROM productos WHERE id = %s", (producto_id,))
    p = cur.fetchone()
    if not p:
        raise ErrorInventario('El producto no existe.')
    return p


def _reservado(cur, empresa_id, almacen_id, producto_id, excluir_separacion=None):
    cur.execute("""
        SELECT COALESCE(SUM(cantidad), 0) AS r FROM inv_separaciones
        WHERE empresa_id = %s AND almacen_id = %s AND producto_id = %s
          AND estado = 'Activa' AND vence_el >= CURRENT_DATE AND id <> COALESCE(%s, -1)
    """, (empresa_id, almacen_id, producto_id, excluir_separacion))
    return a_decimal(cur.fetchone()['r'])


def _bloquear_stock(cur, empresa_id, almacen_id, producto_id):
    cur.execute("""
        INSERT INTO inv_stock (empresa_id, almacen_id, producto_id) VALUES (%s, %s, %s)
        ON CONFLICT DO NOTHING
    """, (empresa_id, almacen_id, producto_id))
    cur.execute("""
        SELECT cantidad, costo_promedio, valor FROM inv_stock
        WHERE empresa_id = %s AND almacen_id = %s AND producto_id = %s FOR UPDATE
    """, (empresa_id, almacen_id, producto_id))
    return cur.fetchone()


def _stock_antiguo_sin_ubicar(cur, producto_id):
    """Stock cargado antes de este módulo (productos.stock) que todavía no tiene empresa ni sede."""
    cur.execute("SELECT 1 FROM inv_stock WHERE producto_id = %s LIMIT 1", (producto_id,))
    if cur.fetchone():
        return Decimal('0')
    cur.execute("SELECT COALESCE(stock, 0) AS s FROM productos WHERE id = %s", (producto_id,))
    f = cur.fetchone()
    return a_decimal(f['s']) if f else Decimal('0')


def _sincronizar_producto(cur, producto_id):
    """productos.stock = suma de todas las empresas y sedes (lo usan Ventas y Productos)."""
    cur.execute("""
        UPDATE productos SET stock = (SELECT COALESCE(SUM(cantidad), 0) FROM inv_stock WHERE producto_id = %s)
        WHERE id = %s
    """, (producto_id, producto_id))


def aplicar_movimiento(cur, *, empresa_id, almacen_id, producto_id, motivo, cantidad, costo_unitario=None,
                       documento_tipo=None, documento_numero=None, tercero=None, lote_serie=None,
                       fecha_vencimiento=None, observaciones=None, traslado_id=None, conteo_id=None,
                       separacion_id=None, recepcion_id=None, grupo=None, revierte_id=None,
                       usar_reservado=Decimal('0'), aprobado_por=None, movimiento_id=None, fecha=None):
    """
    Aplica un movimiento al stock (dentro de la transacción `cur`) y lo registra en el kardex.
    Usa costo promedio ponderado. Nunca deja stock negativo. Si `movimiento_id` viene, aprueba un
    movimiento que estaba Pendiente en vez de crear uno nuevo.
    """
    tipo = MOTIVOS[motivo][0]
    cantidad = a_decimal(cantidad)
    if cantidad <= 0:
        raise ErrorInventario('La cantidad debe ser mayor que 0.')
    s = _bloquear_stock(cur, empresa_id, almacen_id, producto_id)
    saldo, promedio, valor = a_decimal(s['cantidad']), a_decimal(s['costo_promedio']), a_decimal(s['valor'])

    if tipo == 'ENTRADA':
        cu = a_decimal(costo_unitario) if costo_unitario not in (None, '') else promedio
        if cu < 0:
            raise ErrorInventario('El costo no puede ser negativo.')
        total = cantidad * cu
        saldo_n = saldo + cantidad
        valor_n = valor + total
        promedio_n = (valor_n / saldo_n) if saldo_n > 0 else cu
        campo_fecha = 'ultimo_ingreso'
    else:
        reservado = _reservado(cur, empresa_id, almacen_id, producto_id)
        libre = saldo - reservado + a_decimal(usar_reservado)
        if cantidad > saldo:
            raise ErrorInventario(f'No hay stock suficiente: hay {saldo.normalize():f} y quieres sacar {cantidad.normalize():f}.')
        if motivo in MOTIVOS_VENTA and cantidad > libre:
            raise ErrorInventario(
                f'Hay {saldo.normalize():f} en stock pero {reservado.normalize():f} están separados para otros clientes. '
                f'Solo puedes entregar {max(libre, Decimal(0)).normalize():f}. Si es el mismo pedido, elige su separación.')
        cu = promedio
        total = cantidad * cu
        saldo_n = saldo - cantidad
        valor_n = valor - total if saldo_n > 0 else Decimal('0')
        promedio_n = promedio if saldo_n > 0 else promedio
        campo_fecha = 'ultima_salida'

    ahora = fecha or datetime.now()
    cur.execute(f"""
        UPDATE inv_stock SET cantidad = %s, costo_promedio = %s, valor = %s,
               {campo_fecha} = %s, ultimo_movimiento = %s
        WHERE empresa_id = %s AND almacen_id = %s AND producto_id = %s
    """, (saldo_n, promedio_n, valor_n, ahora, ahora, empresa_id, almacen_id, producto_id))

    uid, unom = _usuario()
    if movimiento_id:
        cur.execute("""
            UPDATE inv_movimientos SET estado = 'Registrado', costo_unitario = %s, costo_total = %s,
                   saldo_cantidad = %s, saldo_costo_promedio = %s, saldo_valor = %s,
                   aprobado_por = %s, aprobado_en = NOW(), fecha = %s
            WHERE id = %s RETURNING id, numero
        """, (cu, total, saldo_n, promedio_n, valor_n, aprobado_por, ahora, movimiento_id))
    else:
        numero = _siguiente_numero(cur, 'MOV', 'inv_movimientos')
        cur.execute("""
            INSERT INTO inv_movimientos (numero, fecha, empresa_id, almacen_id, producto_id, tipo, motivo, cantidad,
                costo_unitario, costo_total, saldo_cantidad, saldo_costo_promedio, saldo_valor,
                documento_tipo, documento_numero, tercero, lote_serie, fecha_vencimiento,
                traslado_id, conteo_id, separacion_id, recepcion_id, grupo, revierte_id, estado, observaciones,
                usuario_id, usuario_nombre, aprobado_por, aprobado_en)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'Registrado',%s,%s,%s,%s,
                    CASE WHEN %s IS NULL THEN NULL ELSE NOW() END)
            RETURNING id, numero
        """, (numero, ahora, empresa_id, almacen_id, producto_id, tipo, motivo, cantidad, cu, total,
              saldo_n, promedio_n, valor_n, documento_tipo, documento_numero, tercero, lote_serie,
              fecha_vencimiento or None, traslado_id, conteo_id, separacion_id, recepcion_id, grupo, revierte_id,
              observaciones, uid, unom, aprobado_por, aprobado_por))
    mov = cur.fetchone()
    _sincronizar_producto(cur, producto_id)
    return mov


def _registrar_pendiente(cur, **d):
    """Guarda un movimiento que espera aprobación. No cambia el stock hasta que se apruebe."""
    uid, unom = _usuario()
    numero = _siguiente_numero(cur, 'MOV', 'inv_movimientos')
    cur.execute("""
        INSERT INTO inv_movimientos (numero, empresa_id, almacen_id, producto_id, tipo, motivo, cantidad, costo_unitario,
            documento_tipo, documento_numero, tercero, lote_serie, fecha_vencimiento, estado, observaciones,
            usuario_id, usuario_nombre)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'Pendiente',%s,%s,%s)
        RETURNING id, numero
    """, (numero, d['empresa_id'], d['almacen_id'], d['producto_id'], MOTIVOS[d['motivo']][0], d['motivo'],
          d['cantidad'], d.get('costo_unitario'), d.get('documento_tipo'), d.get('documento_numero'),
          d.get('tercero'), d.get('lote_serie'), d.get('fecha_vencimiento') or None, d.get('observaciones'), uid, unom))
    return cur.fetchone()


def _respuesta_error(e):
    if isinstance(e, ErrorInventario):
        return jsonify({'success': False, 'error': str(e)}), 400
    print(f'❌ Inventario: {e}')
    return jsonify({'success': False, 'error': 'No se pudo completar la operación. Intenta de nuevo.'}), 500


# ============================================================
# PÁGINA
# ============================================================
@inventario_bp.route('/')
def index():
    motivos = {k: v[1] for k, v in MOTIVOS.items()}
    return render_template(
        'inventario/index.html',
        puede_operar=puede_operar(), puede_contar=puede_contar(), puede_aprobar=puede_aprobar(),
        es_admin=es_admin(), motivos=motivos,
        motivos_entrada=[(m, MOTIVOS[m][1]) for m in MOTIVOS_ENTRADA_MANUAL],
        motivos_salida=[(m, MOTIVOS[m][1]) for m in MOTIVOS_SALIDA_MANUAL],
        motivos_problema=[(m, MOTIVOS[m][1]) for m in MOTIVOS_PROBLEMA],
        dias_separacion=DIAS_SEPARACION)


# ============================================================
# CATÁLOGOS
# ============================================================
@inventario_bp.route('/api/catalogos')
def api_catalogos():
    try:
        empresas = _empresas()
        sedes = _sedes()
        registro = db_query("SELECT almacen_id, empresa_id, registrado_sunat, codigo_establecimiento, "
                            "es_domicilio_fiscal, observaciones FROM inv_sede_empresa")
        empresa_sesion = (session.get('empresa') or '').upper()
        defecto = next((e['id'] for e in empresas if (e.get('codigo') or '').upper() == empresa_sesion),
                       empresas[0]['id'] if empresas else None)
        return jsonify({'success': True, 'empresas': empresas, 'sedes': sedes,
                        'registro_sunat': [_fila(r) for r in registro], 'empresa_defecto': defecto,
                        'motivos': {k: {'tipo': v[0], 'texto': v[1], 'sunat': v[2]} for k, v in MOTIVOS.items()},
                        'usuario_id': session.get('usuario_id')})
    except Exception as e:
        return _respuesta_error(e)


@inventario_bp.route('/api/productos')
def api_productos():
    q = (request.args.get('q') or '').strip()
    filas = db_query("""
        SELECT id, codigo, descripcion, marca, modelo, unidad, COALESCE(costo_unitario, 0) AS costo_unitario
        FROM productos
        WHERE COALESCE(activo, true) = true
          AND (%s = '' OR codigo ILIKE %s OR descripcion ILIKE %s OR COALESCE(marca, '') ILIKE %s
               OR COALESCE(modelo, '') ILIKE %s)
        ORDER BY descripcion LIMIT 30
    """, (q, f'%{q}%', f'%{q}%', f'%{q}%', f'%{q}%'))
    return jsonify({'success': True, 'data': [_fila(f) for f in filas]})


# ============================================================
# STOCK CONSOLIDADO (por producto, empresa y sede)
# ============================================================
def _clasificar_rotacion(dias):
    if dias is None:
        return 'Sin datos'
    if dias <= DIAS_LENTO:
        return 'Se mueve'
    if dias <= DIAS_INMOVILIZADO:
        return 'Lento'
    return 'Inmovilizado'


def _consolidado(empresa_id=None, almacen_id=None, q='', solo_con_stock=True):
    filas = db_query("""
        WITH sep AS (
            SELECT empresa_id, almacen_id, producto_id, SUM(cantidad) AS separado
            FROM inv_separaciones WHERE estado = 'Activa' AND vence_el >= CURRENT_DATE
            GROUP BY 1, 2, 3
        ), ventas AS (
            SELECT producto_id, MAX(fecha) AS ultima_venta,
                   SUM(CASE WHEN fecha >= NOW() - INTERVAL '90 days' THEN cantidad ELSE 0 END) AS vendido_90
            FROM inv_movimientos
            WHERE estado = 'Registrado' AND motivo IN ('VENTA', 'INTERCOMPANY_SALIDA')
            GROUP BY producto_id
        ), primer AS (
            SELECT producto_id, MIN(fecha) AS primer_ingreso FROM inv_movimientos
            WHERE estado = 'Registrado' AND tipo = 'ENTRADA' GROUP BY producto_id
        )
        SELECT s.empresa_id, s.almacen_id, s.producto_id, s.cantidad, s.costo_promedio, s.valor,
               s.ultimo_ingreso, s.ultima_salida, s.ultimo_movimiento,
               COALESCE(sep.separado, 0) AS separado,
               p.codigo, p.descripcion, p.marca, p.modelo, p.unidad, COALESCE(p.stock_minimo, 0) AS stock_minimo,
               v.ultima_venta, COALESCE(v.vendido_90, 0) AS vendido_90, pr.primer_ingreso
        FROM inv_stock s
        JOIN productos p ON p.id = s.producto_id
        LEFT JOIN sep ON sep.empresa_id = s.empresa_id AND sep.almacen_id = s.almacen_id AND sep.producto_id = s.producto_id
        LEFT JOIN ventas v ON v.producto_id = s.producto_id
        LEFT JOIN primer pr ON pr.producto_id = s.producto_id
        WHERE (%s IS NULL OR s.empresa_id = %s) AND (%s IS NULL OR s.almacen_id = %s)
          AND (%s = '' OR p.codigo ILIKE %s OR p.descripcion ILIKE %s OR COALESCE(p.marca, '') ILIKE %s
               OR COALESCE(p.modelo, '') ILIKE %s)
          AND (%s = false OR s.cantidad > 0 OR COALESCE(sep.separado, 0) > 0)
        ORDER BY p.descripcion, s.empresa_id, s.almacen_id
    """, (empresa_id, empresa_id, almacen_id, almacen_id, q, f'%{q}%', f'%{q}%', f'%{q}%', f'%{q}%',
          solo_con_stock))
    hoy = datetime.now()
    productos = {}
    for f in filas:
        p = productos.setdefault(f['producto_id'], {
            'producto_id': f['producto_id'], 'codigo': f['codigo'], 'descripcion': f['descripcion'],
            'marca': f['marca'], 'modelo': f['modelo'], 'unidad': f['unidad'],
            'stock_minimo': float(f['stock_minimo']), 'vendido_90': float(f['vendido_90']),
            'total': 0.0, 'separado': 0.0, 'disponible': 0.0, 'valor': 0.0, 'celdas': {}, 'por_empresa': {},
            'ultimo_movimiento': None})
        cant, sep = float(f['cantidad']), float(f['separado'])
        p['celdas'][f"{f['empresa_id']}-{f['almacen_id']}"] = {
            'cantidad': cant, 'separado': sep, 'disponible': max(cant - sep, 0),
            'costo_promedio': float(f['costo_promedio']), 'valor': float(f['valor'])}
        p['por_empresa'][str(f['empresa_id'])] = p['por_empresa'].get(str(f['empresa_id']), 0) + cant
        p['total'] += cant
        p['separado'] += sep
        p['disponible'] += max(cant - sep, 0)
        p['valor'] += float(f['valor'])
        if f['ultimo_movimiento'] and (p['ultimo_movimiento'] is None or f['ultimo_movimiento'] > p['ultimo_movimiento']):
            p['ultimo_movimiento'] = f['ultimo_movimiento']
        referencia = f['ultima_venta'] or f['primer_ingreso']
        p['dias_sin_vender'] = (hoy - referencia).days if referencia else None
    salida = []
    for p in productos.values():
        p['rotacion'] = _clasificar_rotacion(p.get('dias_sin_vender')) if p['total'] > 0 else 'Sin stock'
        p['ultimo_movimiento'] = _fmt(p['ultimo_movimiento'])
        p['valor'] = round(p['valor'], 2)
        salida.append(p)
    return salida


@inventario_bp.route('/api/consolidado')
def api_consolidado():
    try:
        empresa_id = id_empresa(request.args.get('empresa_id'))
        almacen_id = request.args.get('almacen_id', type=int)
        data = _consolidado(empresa_id, almacen_id, (request.args.get('q') or '').strip(),
                            request.args.get('todos') != 'true')
        rot = request.args.get('rotacion')
        if rot:
            data = [p for p in data if p['rotacion'] == rot]
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return _respuesta_error(e)


@inventario_bp.route('/api/consolidado/exportar')
def api_consolidado_exportar():
    empresas = {e['id']: e['nombre'] for e in _empresas()}
    sedes = {s['id']: s['nombre'] for s in _sedes()}
    data = _consolidado(q=(request.args.get('q') or '').strip())
    columnas = [(e, s) for e in empresas for s in sedes]
    lineas = [';'.join(['Código', 'Producto', 'Unidad'] + [f'{empresas[e]} - {sedes[s]}' for e, s in columnas] +
                       [f'Total {empresas[e]}' for e in empresas] + ['Total', 'Separado', 'Disponible', 'Valor S/', 'Rotación'])]
    for p in data:
        fila = [p['codigo'] or '', (p['descripcion'] or '').replace(';', ','), p['unidad'] or '']
        fila += [str(p['celdas'].get(f'{e}-{s}', {}).get('cantidad', 0)) for e, s in columnas]
        fila += [str(p['por_empresa'].get(str(e), 0)) for e in empresas]
        fila += [str(p['total']), str(p['separado']), str(p['disponible']), f"{p['valor']:.2f}", p['rotacion']]
        lineas.append(';'.join(fila))
    return Response('﻿' + '\r\n'.join(lineas), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename=stock_consolidado_{date.today()}.csv'})


# ============================================================
# ¿DÓNDE ESTÁ? / PREPARAR UN PEDIDO
# ============================================================
@inventario_bp.route('/api/ubicar')
def api_ubicar():
    """Dice dónde está un producto y cómo juntar una cantidad en la sede de despacho."""
    try:
        producto_id = _entero(request.args.get('producto_id'), 'un producto')
        cantidad = a_decimal(request.args.get('cantidad') or '0')
        empresa_venta = id_empresa(request.args.get('empresa_id'))
        sede_despacho = request.args.get('almacen_id', type=int)
        filas = db_query("""
            SELECT s.empresa_id, s.almacen_id, s.cantidad,
                   COALESCE((SELECT SUM(cantidad) FROM inv_separaciones x
                             WHERE x.empresa_id = s.empresa_id AND x.almacen_id = s.almacen_id
                               AND x.producto_id = s.producto_id AND x.estado = 'Activa'
                               AND x.vence_el >= CURRENT_DATE), 0) AS separado
            FROM inv_stock s WHERE s.producto_id = %s AND s.cantidad > 0
        """, (producto_id,))
        empresas = {e['id']: e['nombre'] for e in _empresas()}
        sedes = {s['id']: s['nombre'] for s in _sedes()}
        lugares = []
        for f in filas:
            disp = max(a_decimal(f['cantidad']) - a_decimal(f['separado']), Decimal(0))
            lugares.append({'empresa_id': f['empresa_id'], 'almacen_id': f['almacen_id'],
                            'empresa': empresas.get(f['empresa_id'], '?'), 'sede': sedes.get(f['almacen_id'], '?'),
                            'cantidad': float(f['cantidad']), 'separado': float(f['separado']), 'disponible': float(disp)})

        plan, falta = [], cantidad
        if cantidad > 0 and sede_despacho:
            # Orden: misma empresa en la sede de despacho, misma empresa en otra sede,
            # otra empresa en la sede de despacho, otra empresa en otra sede.
            def prioridad(l):
                return (0 if l['empresa_id'] == empresa_venta else 1, 0 if l['almacen_id'] == sede_despacho else 1)
            for l in sorted(lugares, key=prioridad):
                if falta <= 0:
                    break
                tomar = min(a_decimal(l['disponible']), falta)
                if tomar <= 0:
                    continue
                falta -= tomar
                pasos = []
                if l['almacen_id'] != sede_despacho:
                    pasos.append('traslado')
                if empresa_venta and l['empresa_id'] != empresa_venta:
                    pasos.append('intercompany')
                plan.append({**l, 'tomar': float(tomar), 'pasos': pasos})
        return jsonify({'success': True, 'lugares': lugares, 'plan': plan,
                        'alcanza': cantidad > 0 and falta <= 0, 'falta': float(max(falta, Decimal(0)))})
    except Exception as e:
        return _respuesta_error(e)


# ============================================================
# MOVIMIENTOS (ENTRADAS, SALIDAS, PROBLEMAS)
# ============================================================
@inventario_bp.route('/api/movimientos', methods=['POST'])
def api_movimiento_nuevo():
    d = request.get_json(silent=True) or {}
    motivo = d.get('motivo')
    try:
        if motivo not in MOTIVOS_ENTRADA_MANUAL + MOTIVOS_SALIDA_MANUAL + MOTIVOS_PROBLEMA:
            raise ErrorInventario('Elige un motivo válido.')
        if motivo in MOTIVOS_PROBLEMA:
            if not (puede_operar() or puede_contar()):
                return _no_autorizado('No tienes permiso para reportar problemas de inventario.')
        elif not puede_operar():
            return _no_autorizado('Solo el personal de almacén puede registrar entradas y salidas.')
        empresa_id = _empresa(d.get('empresa_id'), 'la empresa')
        almacen_id = _entero(d.get('almacen_id'), 'la sede')
        producto_id = _entero(d.get('producto_id'), 'un producto')
        cantidad = _num(d.get('cantidad'))
        _, _, _, requiere_aprobacion, requiere_doc = MOTIVOS[motivo]
        documento = (d.get('documento_numero') or '').strip()
        if requiere_doc and not documento:
            raise ErrorInventario('Escribe el número de documento (guía, factura u orden). Sin documento no hay movimiento.')
        if motivo in MOTIVOS_PROBLEMA and not (d.get('observaciones') or '').strip():
            raise ErrorInventario('Explica qué pasó en "Observaciones". Es obligatorio para pérdidas, robos y mermas.')
        costo = d.get('costo_unitario')
        if MOTIVOS[motivo][0] == 'ENTRADA' and motivo != 'DEVOLUCION_CLIENTE' and costo in (None, ''):
            raise ErrorInventario('Escribe el costo unitario sin IGV.')
        datos = dict(empresa_id=empresa_id, almacen_id=almacen_id, producto_id=producto_id, motivo=motivo,
                     cantidad=cantidad, costo_unitario=costo if costo not in ('',) else None,
                     documento_tipo=(d.get('documento_tipo') or '').strip() or None,
                     documento_numero=documento or None, tercero=(d.get('tercero') or '').strip() or None,
                     lote_serie=(d.get('lote_serie') or '').strip() or None,
                     fecha_vencimiento=d.get('fecha_vencimiento') or None,
                     observaciones=(d.get('observaciones') or '').strip() or None)
        recepcion_id = d.get('recepcion_id') or None
        separacion_id = d.get('separacion_id') or None
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            _validar_empresa_sede(cur, empresa_id, almacen_id)
            _producto(cur, producto_id)
            antiguo = _stock_antiguo_sin_ubicar(cur, producto_id)
            if antiguo > 0 and motivo != 'STOCK_INICIAL':
                raise ErrorInventario(
                    f'Este producto tiene {antiguo.normalize():f} unidades registradas antes del nuevo inventario y '
                    'todavía no se sabe de qué empresa ni de qué sede son. Primero regístralas con "Stock inicial".')
            rec = None
            if recepcion_id:
                cur.execute("SELECT 1 FROM inv_movimientos WHERE recepcion_id = %s AND estado <> 'Rechazado'", (recepcion_id,))
                if cur.fetchone():
                    raise ErrorInventario('Esa recepción ya fue ingresada al inventario.')
                rec = _recepcion_compras(cur, recepcion_id)
                if rec and rec.get('producto_id'):
                    # Recepción hecha en Compras: empresa, sede y producto ya se saben. No se pueden cambiar aquí.
                    if (rec['producto_id'], rec['empresa_id'], rec['almacen_id']) != (producto_id, empresa_id, almacen_id):
                        raise ErrorInventario('Esta mercadería se recibió en Compras para otra empresa, sede o producto. '
                                              'Ingrésala tal como se recibió.')
                    if cantidad > a_decimal(rec['cantidad']):
                        raise ErrorInventario(f"En Compras se recibieron {a_decimal(rec['cantidad']).normalize():f}. "
                                              'No puedes ingresar más de lo recibido.')
            if requiere_aprobacion and not puede_aprobar():
                mov = _registrar_pendiente(cur, **datos)
                if recepcion_id:
                    cur.execute("UPDATE inv_movimientos SET recepcion_id = %s WHERE id = %s", (recepcion_id, mov['id']))
                return jsonify({'success': True, 'pendiente': True, 'numero': mov['numero'],
                                'message': f"Registrado {mov['numero']}. Queda pendiente hasta que un supervisor lo apruebe."})
            usar = Decimal('0')
            if separacion_id:
                cur.execute("SELECT * FROM inv_separaciones WHERE id = %s FOR UPDATE", (separacion_id,))
                sep = cur.fetchone()
                if not sep or sep['estado'] != 'Activa':
                    raise ErrorInventario('La separación elegida ya no está activa.')
                if (sep['empresa_id'], sep['almacen_id'], sep['producto_id']) != (empresa_id, almacen_id, producto_id):
                    raise ErrorInventario('La separación elegida es de otro producto, empresa o sede.')
                usar = min(a_decimal(sep['cantidad']), cantidad)
                if not datos['tercero']:
                    datos['tercero'] = sep['cliente']
            _, unom = _usuario()
            mov = aplicar_movimiento(cur, **datos, recepcion_id=recepcion_id, separacion_id=separacion_id,
                                     usar_reservado=usar,
                                     aprobado_por=unom if requiere_aprobacion else None)
            if separacion_id:
                cur.execute("""
                    UPDATE inv_separaciones SET cantidad = cantidad - %s,
                           estado = CASE WHEN cantidad - %s <= 0 THEN 'Entregada' ELSE estado END,
                           cerrado_por = CASE WHEN cantidad - %s <= 0 THEN %s ELSE cerrado_por END,
                           cerrado_en = CASE WHEN cantidad - %s <= 0 THEN NOW() ELSE cerrado_en END
                    WHERE id = %s
                """, (usar, usar, usar, unom, usar, separacion_id))
            sep_num = None
            if rec and rec.get('cliente') and mov and motivo == 'COMPRA':
                # Compra bajo pedido: lo que llega se separa para el cliente del pedido (evita que se revenda)
                uid, unom = _usuario()
                sep_num = _siguiente_numero(cur, 'SEP', 'inv_separaciones')
                cur.execute("""
                    INSERT INTO inv_separaciones (numero, empresa_id, almacen_id, producto_id, cantidad, cantidad_inicial,
                        cliente, documento, vence_el, observaciones, usuario_id, usuario_nombre)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (sep_num, empresa_id, almacen_id, producto_id, cantidad, cantidad, rec['cliente'],
                      rec.get('pedido_numero'), date.today() + timedelta(days=DIAS_SEPARACION),
                      f"Separado automáticamente al ingresar la compra {rec.get('orden_compra_numero') or ''}", uid, unom))
        mensaje = f"Movimiento {mov['numero']} registrado."
        if sep_num:
            mensaje += f" Quedó separado para {rec['cliente']} ({sep_num}): nadie más puede venderlo."
        return jsonify({'success': True, 'numero': mov['numero'], 'separacion': sep_num, 'message': mensaje})
    except Exception as e:
        return _respuesta_error(e)


def _recepcion_compras(cur, recepcion_id):
    """Datos de una recepción hecha en el nuevo módulo de Compras (None si es del sistema anterior)."""
    from routes.compras_flujo import asegurar_tablas_compras
    asegurar_tablas_compras()
    cur.execute("""SELECT producto_id, empresa_id, almacen_id, cantidad, cliente, pedido_numero, orden_compra_numero
                   FROM recepciones_mercaderia WHERE id = %s""", (recepcion_id,))
    return cur.fetchone()


@inventario_bp.route('/api/kardex')
def api_kardex():
    """Kardex valorizado. Con producto, empresa y sede: saldo exacto de esa ubicación."""
    try:
        producto_id = request.args.get('producto_id', type=int)
        empresa_id = id_empresa(request.args.get('empresa_id'))
        almacen_id = request.args.get('almacen_id', type=int)
        desde = request.args.get('desde') or None
        hasta = request.args.get('hasta') or None
        estado = request.args.get('estado') or 'Registrado'
        q = (request.args.get('q') or '').strip()
        filas = db_query("""
            SELECT m.*, p.codigo, p.descripcion, p.unidad, e.codigo AS empresa_codigo,
                   COALESCE(NULLIF(e.nombre_corto, ''), e.codigo) AS empresa, a.nombre AS sede
            FROM inv_movimientos m
            JOIN productos p ON p.id = m.producto_id
            LEFT JOIN erp_empresas e ON e.id = m.empresa_id
            LEFT JOIN almacenes a ON a.id = m.almacen_id
            WHERE (%s IS NULL OR m.producto_id = %s) AND (%s IS NULL OR m.empresa_id = %s)
              AND (%s IS NULL OR m.almacen_id = %s)
              AND (%s::date IS NULL OR m.fecha >= %s::date) AND (%s::date IS NULL OR m.fecha < %s::date + 1)
              AND (%s = 'Todos' OR m.estado = %s)
              AND (%s = '' OR m.numero ILIKE %s OR p.descripcion ILIKE %s OR p.codigo ILIKE %s
                   OR COALESCE(m.documento_numero, '') ILIKE %s OR COALESCE(m.tercero, '') ILIKE %s
                   OR COALESCE(m.lote_serie, '') ILIKE %s)
            ORDER BY m.fecha DESC, m.id DESC LIMIT 1000
        """, (producto_id, producto_id, empresa_id, empresa_id, almacen_id, almacen_id, desde, desde, hasta, hasta,
              estado, estado, q, *[f'%{q}%'] * 6))
        data = []
        for f in filas:
            r = _fila(f)
            r['motivo_texto'] = MOTIVOS.get(f['motivo'], ('', f['motivo']))[1]
            r['codigo_sunat'] = MOTIVOS.get(f['motivo'], ('', '', '99'))[2]
            data.append(r)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return _respuesta_error(e)


@inventario_bp.route('/api/kardex/exportar')
def api_kardex_exportar():
    """Registro de inventario permanente valorizado (estructura del formato 13.1 de SUNAT) en CSV."""
    empresa_id = id_empresa(request.args.get('empresa_id'))
    producto_id = request.args.get('producto_id', type=int)
    desde = request.args.get('desde') or None
    hasta = request.args.get('hasta') or None
    filas = db_query("""
        SELECT m.*, p.codigo, p.descripcion, p.unidad, COALESCE(NULLIF(e.nombre_corto, ''), e.codigo) AS empresa,
               e.ruc, a.nombre AS sede
        FROM inv_movimientos m JOIN productos p ON p.id = m.producto_id
        LEFT JOIN erp_empresas e ON e.id = m.empresa_id LEFT JOIN almacenes a ON a.id = m.almacen_id
        WHERE m.estado = 'Registrado' AND (%s IS NULL OR m.empresa_id = %s) AND (%s IS NULL OR m.producto_id = %s)
          AND (%s::date IS NULL OR m.fecha >= %s::date) AND (%s::date IS NULL OR m.fecha < %s::date + 1)
        ORDER BY m.empresa_id, p.codigo, m.almacen_id, m.id
    """, (empresa_id, empresa_id, producto_id, producto_id, desde, desde, hasta, hasta))
    enc = ['Empresa', 'RUC', 'Sede', 'Código', 'Producto', 'Unidad', 'Fecha', 'N° movimiento', 'Tipo doc.',
           'N° documento', 'Tipo operación SUNAT', 'Motivo', 'Entrada cant.', 'Entrada costo unit.', 'Entrada total',
           'Salida cant.', 'Salida costo unit.', 'Salida total', 'Saldo cant.', 'Saldo costo unit.', 'Saldo total',
           'Lote / serie', 'Usuario']
    lineas = [';'.join(enc)]
    for f in filas:
        ent = f['tipo'] == 'ENTRADA'
        c = lambda v: f'{a_decimal(v):.4f}'
        lineas.append(';'.join(str(x if x is not None else '') for x in [
            f['empresa'], f['ruc'], f['sede'], f['codigo'], (f['descripcion'] or '').replace(';', ','), f['unidad'],
            f['fecha'].strftime('%d/%m/%Y'), f['numero'], f['documento_tipo'], f['documento_numero'],
            MOTIVOS.get(f['motivo'], ('', '', '99'))[2], MOTIVOS.get(f['motivo'], ('', f['motivo']))[1],
            c(f['cantidad']) if ent else '', c(f['costo_unitario']) if ent else '', c(f['costo_total']) if ent else '',
            '' if ent else c(f['cantidad']), '' if ent else c(f['costo_unitario']), '' if ent else c(f['costo_total']),
            c(f['saldo_cantidad']), c(f['saldo_costo_promedio']), c(f['saldo_valor']), f['lote_serie'],
            f['usuario_nombre']]))
    return Response('﻿' + '\r\n'.join(lineas), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename=kardex_{date.today()}.csv'})


@inventario_bp.route('/api/movimientos/<int:mov_id>/aprobar', methods=['POST'])
def api_movimiento_aprobar(mov_id):
    if not puede_aprobar():
        return _no_autorizado('Solo un supervisor puede aprobar.')
    d = request.get_json(silent=True) or {}
    aprobar = d.get('aprobar', True)
    try:
        uid, unom = _usuario()
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM inv_movimientos WHERE id = %s FOR UPDATE", (mov_id,))
            m = cur.fetchone()
            if not m or m['estado'] != 'Pendiente':
                raise ErrorInventario('Ese movimiento ya no está pendiente.')
            if m['usuario_id'] == uid and not es_admin():
                raise ErrorInventario('No puedes aprobar un movimiento que registraste tú. Pide a otro supervisor.')
            if not aprobar:
                motivo = (d.get('motivo') or '').strip()
                if not motivo:
                    raise ErrorInventario('Escribe por qué lo rechazas.')
                cur.execute("UPDATE inv_movimientos SET estado = 'Rechazado', motivo_rechazo = %s, aprobado_por = %s, "
                            "aprobado_en = NOW() WHERE id = %s", (motivo, unom, mov_id))
                return jsonify({'success': True, 'message': f"{m['numero']} rechazado."})
            aplicar_movimiento(cur, empresa_id=m['empresa_id'], almacen_id=m['almacen_id'],
                               producto_id=m['producto_id'], motivo=m['motivo'], cantidad=m['cantidad'],
                               costo_unitario=m['costo_unitario'], aprobado_por=unom, movimiento_id=mov_id)
        return jsonify({'success': True, 'message': f"{m['numero']} aprobado. El stock ya se actualizó."})
    except Exception as e:
        return _respuesta_error(e)


@inventario_bp.route('/api/movimientos/<int:mov_id>/revertir', methods=['POST'])
def api_movimiento_revertir(mov_id):
    """Corrige un error: crea el movimiento contrario. El original queda visible en el kardex."""
    if not puede_aprobar():
        return _no_autorizado('Solo un supervisor puede corregir movimientos.')
    d = request.get_json(silent=True) or {}
    motivo = (d.get('motivo') or '').strip()
    try:
        if not motivo:
            raise ErrorInventario('Escribe por qué se corrige.')
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM inv_movimientos WHERE id = %s FOR UPDATE", (mov_id,))
            m = cur.fetchone()
            if not m or m['estado'] != 'Registrado' or m['revertido_por_id'] or m['revierte_id']:
                raise ErrorInventario('Ese movimiento no se puede corregir (ya fue corregido o no está registrado).')
            if m['traslado_id'] or m['conteo_id'] or m['grupo']:
                raise ErrorInventario('Este movimiento es parte de un traslado, conteo o venta intercompany. '
                                      'Corrígelo desde su pestaña.')
            if m.get('despacho_id'):
                raise ErrorInventario('Este movimiento salió con un despacho. Para devolver el stock, anula el despacho en Ventas.')
            contrario = 'REVERSA_SALIDA' if m['tipo'] == 'ENTRADA' else 'REVERSA_ENTRADA'
            _, unom = _usuario()
            nuevo = aplicar_movimiento(
                cur, empresa_id=m['empresa_id'], almacen_id=m['almacen_id'], producto_id=m['producto_id'],
                motivo=contrario, cantidad=m['cantidad'],
                costo_unitario=m['costo_unitario'] if contrario == 'REVERSA_ENTRADA' else None,
                documento_tipo='Corrección', documento_numero=m['numero'], tercero=m['tercero'],
                observaciones=f"Corrige {m['numero']}: {motivo}", revierte_id=mov_id, aprobado_por=unom)
            cur.execute("UPDATE inv_movimientos SET revertido_por_id = %s WHERE id = %s", (nuevo['id'], mov_id))
        return jsonify({'success': True, 'message': f"{m['numero']} corregido con {nuevo['numero']}."})
    except Exception as e:
        return _respuesta_error(e)


# ============================================================
# RECEPCIONES DE COMPRAS PENDIENTES DE INGRESAR
# ============================================================
@inventario_bp.route('/api/recepciones_pendientes')
def api_recepciones_pendientes():
    try:
        from routes.compras_flujo import asegurar_tablas_compras
        asegurar_tablas_compras()
        filas = db_query("""
            SELECT r.id, r.numero_recepcion, r.fecha, r.producto, r.cantidad, r.unidad, r.proveedor_nombre,
                   r.orden_compra_numero AS orden_compra, r.estado,
                   COALESCE(r.producto_id, (SELECT p.id FROM productos p WHERE p.codigo = r.producto OR p.descripcion ILIKE r.producto
                    ORDER BY (p.codigo = r.producto) DESC LIMIT 1)) AS producto_id_sugerido,
                   r.producto_id IS NOT NULL AS desde_compras, r.empresa_id, r.almacen_id, r.costo_unitario,
                   r.guia_proveedor, r.cliente, r.pedido_numero, r.lote_serie, r.fecha_vencimiento,
                   (SELECT codigo FROM productos WHERE id = r.producto_id) AS codigo
            FROM recepciones_mercaderia r
            WHERE r.estado IN ('Aprobada', 'Almacenada')
              AND NOT EXISTS (SELECT 1 FROM inv_movimientos m WHERE m.recepcion_id = r.id AND m.estado <> 'Rechazado')
            ORDER BY r.fecha DESC LIMIT 200
        """)
        return jsonify({'success': True, 'data': [_fila(f) for f in filas]})
    except Exception as e:
        return _respuesta_error(e)


# ============================================================
# TRASLADOS ENTRE SEDES (misma empresa)
# ============================================================
@inventario_bp.route('/api/traslados')
def api_traslados():
    try:
        estado = request.args.get('estado') or ''
        filas = db_query("""
            SELECT t.*, COALESCE(NULLIF(e.nombre_corto, ''), e.codigo) AS empresa,
                   o.nombre AS origen, d.nombre AS destino,
                   COALESCE(json_agg(json_build_object('id', i.id, 'producto_id', i.producto_id, 'codigo', p.codigo,
                       'descripcion', p.descripcion, 'unidad', p.unidad, 'cantidad', i.cantidad,
                       'cantidad_recibida', i.cantidad_recibida) ORDER BY i.id)
                       FILTER (WHERE i.id IS NOT NULL), '[]') AS items
            FROM inv_traslados t
            LEFT JOIN erp_empresas e ON e.id = t.empresa_id
            LEFT JOIN almacenes o ON o.id = t.origen_id
            LEFT JOIN almacenes d ON d.id = t.destino_id
            LEFT JOIN inv_traslado_items i ON i.traslado_id = t.id
            LEFT JOIN productos p ON p.id = i.producto_id
            WHERE (%s = '' OR t.estado = %s)
            GROUP BY t.id, e.nombre_corto, e.codigo, o.nombre, d.nombre
            ORDER BY (t.estado = 'En camino') DESC, t.fecha DESC LIMIT 300
        """, (estado, estado))
        ahora = datetime.now()
        data = []
        for f in filas:
            r = _fila(f)
            r['horas_en_camino'] = int((ahora - f['fecha']).total_seconds() // 3600) if f['estado'] == 'En camino' else None
            data.append(r)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return _respuesta_error(e)


def crear_traslado(cur, empresa_id, origen_id, destino_id, items, guia=None, encargado=None, observaciones=None):
    if origen_id == destino_id:
        raise ErrorInventario('La sede de origen y la de destino deben ser distintas.')
    _validar_empresa_sede(cur, empresa_id, origen_id)
    _validar_empresa_sede(cur, empresa_id, destino_id)
    if not items:
        raise ErrorInventario('Agrega al menos un producto al traslado.')
    uid, unom = _usuario()
    numero = _siguiente_numero(cur, 'TRA', 'inv_traslados')
    cur.execute("""
        INSERT INTO inv_traslados (numero, empresa_id, origen_id, destino_id, guia_remision, encargado, observaciones,
                                   enviado_por_id, enviado_por)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id, numero
    """, (numero, empresa_id, origen_id, destino_id, guia, encargado, observaciones, uid, unom))
    t = cur.fetchone()
    for it in items:
        producto_id = _entero(it.get('producto_id'), 'un producto')
        cantidad = _num(it.get('cantidad'))
        if _stock_antiguo_sin_ubicar(cur, producto_id) > 0:
            raise ErrorInventario('Uno de los productos tiene stock antiguo sin ubicar. Regístralo primero con "Stock inicial".')
        mov = aplicar_movimiento(cur, empresa_id=empresa_id, almacen_id=origen_id, producto_id=producto_id,
                                 motivo='TRASLADO_SALIDA', cantidad=cantidad, documento_tipo='Guía de remisión',
                                 documento_numero=guia, traslado_id=t['id'], observaciones=f"Traslado {numero}")
        cur.execute("SELECT costo_unitario FROM inv_movimientos WHERE id = %s", (mov['id'],))
        cu = cur.fetchone()['costo_unitario']
        cur.execute("INSERT INTO inv_traslado_items (traslado_id, producto_id, cantidad, costo_unitario) "
                    "VALUES (%s,%s,%s,%s)", (t['id'], producto_id, cantidad, cu))
    return t


@inventario_bp.route('/api/traslados', methods=['POST'])
def api_traslado_nuevo():
    if not puede_operar():
        return _no_autorizado('Solo el personal de almacén puede enviar traslados.')
    d = request.get_json(silent=True) or {}
    try:
        empresa_id = _empresa(d.get('empresa_id'), 'la empresa dueña de la mercadería')
        origen_id = _entero(d.get('origen_id'), 'la sede de origen')
        destino_id = _entero(d.get('destino_id'), 'la sede de destino')
        if not (d.get('encargado') or '').strip():
            raise ErrorInventario('Escribe quién lleva la mercadería.')
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            t = crear_traslado(cur, empresa_id, origen_id, destino_id, d.get('items') or [],
                               (d.get('guia_remision') or '').strip() or None, d['encargado'].strip(),
                               (d.get('observaciones') or '').strip() or None)
        return jsonify({'success': True, 'numero': t['numero'],
                        'message': f"Traslado {t['numero']} enviado. Queda 'En camino' hasta que otra persona lo reciba en destino."})
    except Exception as e:
        return _respuesta_error(e)


@inventario_bp.route('/api/traslados/<int:tid>/recibir', methods=['POST'])
def api_traslado_recibir(tid):
    if not puede_operar():
        return _no_autorizado('Solo el personal de almacén puede recibir traslados.')
    d = request.get_json(silent=True) or {}
    try:
        uid, unom = _usuario()
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM inv_traslados WHERE id = %s FOR UPDATE", (tid,))
            t = cur.fetchone()
            if not t or t['estado'] != 'En camino':
                raise ErrorInventario('Ese traslado ya fue recibido o anulado.')
            if t['enviado_por_id'] == uid and not es_admin():
                raise ErrorInventario('Quien envía no puede recibir su propio traslado. Debe recibirlo otra persona en destino.')
            recibidas = {int(k): v for k, v in (d.get('recibido') or {}).items()}
            cur.execute("SELECT * FROM inv_traslado_items WHERE traslado_id = %s ORDER BY id", (tid,))
            items = cur.fetchall()
            hay_diferencia = False
            for it in items:
                if it['id'] not in recibidas or recibidas[it['id']] in (None, ''):
                    raise ErrorInventario('Escribe la cantidad que llegó de cada producto (aunque sea 0).')
                llego = a_decimal(recibidas[it['id']])
                if llego < 0 or llego > a_decimal(it['cantidad']):
                    raise ErrorInventario('La cantidad recibida no puede ser negativa ni mayor que la enviada.')
                enviado = a_decimal(it['cantidad'])
                aplicar_movimiento(cur, empresa_id=t['empresa_id'], almacen_id=t['destino_id'],
                                   producto_id=it['producto_id'], motivo='TRASLADO_ENTRADA', cantidad=enviado,
                                   costo_unitario=it['costo_unitario'], documento_tipo='Guía de remisión',
                                   documento_numero=t['guia_remision'], traslado_id=tid,
                                   observaciones=f"Traslado {t['numero']}")
                if llego < enviado:
                    hay_diferencia = True
                    aplicar_movimiento(cur, empresa_id=t['empresa_id'], almacen_id=t['destino_id'],
                                       producto_id=it['producto_id'], motivo='FALTANTE_TRASLADO', cantidad=enviado - llego,
                                       documento_tipo='Guía de remisión', documento_numero=t['guia_remision'],
                                       traslado_id=tid, tercero=t['encargado'],
                                       observaciones=f"Faltante en traslado {t['numero']} (llevó: {t['encargado']})")
                cur.execute("UPDATE inv_traslado_items SET cantidad_recibida = %s WHERE id = %s", (llego, it['id']))
            obs = (d.get('observaciones') or '').strip()
            if hay_diferencia and not obs:
                raise ErrorInventario('Llegó menos de lo enviado. Explica la diferencia en "Observaciones".')
            estado = 'Recibido con faltante' if hay_diferencia else 'Recibido'
            cur.execute("UPDATE inv_traslados SET estado = %s, recibido_por_id = %s, recibido_por = %s, recibido_en = NOW(), "
                        "observaciones_recepcion = %s WHERE id = %s", (estado, uid, unom, obs or None, tid))
        msg = f"Traslado {t['numero']} recibido."
        if hay_diferencia:
            msg += ' Se registró el faltante y aparecerá en Alertas para revisión.'
        return jsonify({'success': True, 'message': msg})
    except Exception as e:
        return _respuesta_error(e)


@inventario_bp.route('/api/traslados/<int:tid>/anular', methods=['POST'])
def api_traslado_anular(tid):
    if not puede_aprobar():
        return _no_autorizado('Solo un supervisor puede anular un traslado.')
    d = request.get_json(silent=True) or {}
    try:
        motivo = (d.get('motivo') or '').strip()
        if not motivo:
            raise ErrorInventario('Escribe por qué se anula.')
        _, unom = _usuario()
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM inv_traslados WHERE id = %s FOR UPDATE", (tid,))
            t = cur.fetchone()
            if not t or t['estado'] != 'En camino':
                raise ErrorInventario('Solo se puede anular un traslado que sigue "En camino".')
            cur.execute("SELECT * FROM inv_traslado_items WHERE traslado_id = %s", (tid,))
            for it in cur.fetchall():
                aplicar_movimiento(cur, empresa_id=t['empresa_id'], almacen_id=t['origen_id'], producto_id=it['producto_id'],
                                   motivo='REVERSA_ENTRADA', cantidad=it['cantidad'], costo_unitario=it['costo_unitario'],
                                   documento_tipo='Anulación traslado', documento_numero=t['numero'], traslado_id=tid,
                                   observaciones=f"Anula traslado {t['numero']}: {motivo}", aprobado_por=unom)
            cur.execute("UPDATE inv_traslados SET estado = 'Anulado', observaciones_recepcion = %s WHERE id = %s",
                        (f'Anulado por {unom}: {motivo}', tid))
        return jsonify({'success': True, 'message': f"Traslado {t['numero']} anulado. La mercadería volvió a la sede de origen."})
    except Exception as e:
        return _respuesta_error(e)


@inventario_bp.route('/api/juntar', methods=['POST'])
def api_juntar():
    """Crea de una vez los traslados que propone 'Preparar pedido' (solo los pasos de traslado)."""
    if not puede_operar():
        return _no_autorizado('Solo el personal de almacén puede crear traslados.')
    d = request.get_json(silent=True) or {}
    try:
        destino_id = _entero(d.get('almacen_id'), 'la sede de despacho')
        producto_id = _entero(d.get('producto_id'), 'un producto')
        encargado = (d.get('encargado') or '').strip()
        if not encargado:
            raise ErrorInventario('Escribe quién recogerá la mercadería.')
        numeros = []
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            for paso in d.get('plan') or []:
                if int(paso['almacen_id']) == destino_id:
                    continue
                t = crear_traslado(cur, _empresa(paso['empresa_id']), int(paso['almacen_id']), destino_id,
                                   [{'producto_id': producto_id, 'cantidad': paso['tomar']}], None, encargado,
                                   (d.get('observaciones') or 'Juntar mercadería para despacho').strip())
                numeros.append(t['numero'])
        if not numeros:
            raise ErrorInventario('No hace falta trasladar nada: todo está en la sede de despacho.')
        return jsonify({'success': True, 'numeros': numeros,
                        'message': 'Traslados creados: ' + ', '.join(numeros) + '. Recuerda emitir la guía de remisión.'})
    except Exception as e:
        return _respuesta_error(e)


# ============================================================
# VENTA ENTRE EMPRESAS DEL GRUPO (INTERCOMPANY)
# ============================================================
@inventario_bp.route('/api/intercompany')
def api_intercompany_lista():
    try:
        filas = db_query("""
            SELECT m.grupo, MIN(m.fecha) AS fecha, MAX(m.documento_numero) AS factura,
                   MAX(CASE WHEN m.tipo = 'SALIDA' THEN COALESCE(NULLIF(e.nombre_corto, ''), e.codigo) END) AS vende,
                   MAX(CASE WHEN m.tipo = 'ENTRADA' THEN COALESCE(NULLIF(e.nombre_corto, ''), e.codigo) END) AS compra,
                   MAX(a.nombre) AS sede, MAX(p.codigo) AS codigo, MAX(p.descripcion) AS descripcion,
                   MAX(m.cantidad) AS cantidad, MAX(CASE WHEN m.tipo = 'ENTRADA' THEN m.costo_unitario END) AS precio,
                   MAX(m.usuario_nombre) AS usuario
            FROM inv_movimientos m
            JOIN productos p ON p.id = m.producto_id
            LEFT JOIN erp_empresas e ON e.id = m.empresa_id LEFT JOIN almacenes a ON a.id = m.almacen_id
            WHERE m.motivo IN ('INTERCOMPANY_SALIDA', 'INTERCOMPANY_ENTRADA') AND m.estado = 'Registrado'
            GROUP BY m.grupo ORDER BY MIN(m.fecha) DESC LIMIT 300
        """)
        return jsonify({'success': True, 'data': [_fila(f) for f in filas]})
    except Exception as e:
        return _respuesta_error(e)


@inventario_bp.route('/api/intercompany', methods=['POST'])
def api_intercompany():
    """La mercadería no se mueve de sitio: cambia de dueño (salida en una empresa, entrada en la otra)."""
    if not puede_operar():
        return _no_autorizado('Solo el personal de almacén puede registrar ventas entre empresas.')
    d = request.get_json(silent=True) or {}
    try:
        vende = _empresa(d.get('empresa_vende_id'), 'la empresa que vende')
        compra = _empresa(d.get('empresa_compra_id'), 'la empresa que compra')
        almacen_id = _entero(d.get('almacen_id'), 'la sede donde está la mercadería')
        producto_id = _entero(d.get('producto_id'), 'un producto')
        cantidad = _num(d.get('cantidad'))
        if vende == compra:
            raise ErrorInventario('La empresa que vende y la que compra deben ser distintas.')
        factura = (d.get('factura') or '').strip() or None
        precio = d.get('precio_unitario')
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            _validar_empresa_sede(cur, compra, almacen_id)
            grupo = _siguiente_numero(cur, 'IC', 'inv_movimientos', 'grupo')
            cur.execute("SELECT COALESCE(NULLIF(nombre_corto, ''), codigo) AS n FROM erp_empresas WHERE id IN (%s, %s) "
                        "ORDER BY (id = %s) DESC", (vende, compra, vende))
            nombres = [r['n'] for r in cur.fetchall()]
            if _stock_antiguo_sin_ubicar(cur, producto_id) > 0:
                raise ErrorInventario('Este producto tiene stock antiguo sin ubicar. Regístralo primero con "Stock inicial".')
            sal = aplicar_movimiento(cur, empresa_id=vende, almacen_id=almacen_id, producto_id=producto_id,
                                     motivo='INTERCOMPANY_SALIDA', cantidad=cantidad, documento_tipo='Factura',
                                     documento_numero=factura, tercero=nombres[1] if len(nombres) > 1 else None,
                                     grupo=grupo, observaciones=(d.get('observaciones') or '').strip() or None)
            cur.execute("SELECT costo_unitario FROM inv_movimientos WHERE id = %s", (sal['id'],))
            costo = cur.fetchone()['costo_unitario']
            aplicar_movimiento(cur, empresa_id=compra, almacen_id=almacen_id, producto_id=producto_id,
                               motivo='INTERCOMPANY_ENTRADA', cantidad=cantidad,
                               costo_unitario=precio if precio not in (None, '') else costo,
                               documento_tipo='Factura', documento_numero=factura, tercero=nombres[0],
                               grupo=grupo, observaciones=(d.get('observaciones') or '').strip() or None)
        msg = f'Venta entre empresas registrada ({grupo}).'
        if not factura:
            msg += ' Falta el número de factura: aparecerá en Alertas hasta que lo completes.'
        return jsonify({'success': True, 'grupo': grupo, 'message': msg})
    except Exception as e:
        return _respuesta_error(e)


@inventario_bp.route('/api/intercompany/<grupo>/factura', methods=['POST'])
def api_intercompany_factura(grupo):
    if not puede_operar():
        return _no_autorizado('Sin permiso.')
    factura = ((request.get_json(silent=True) or {}).get('factura') or '').strip()
    if not factura:
        return jsonify({'success': False, 'error': 'Escribe el número de factura.'}), 400
    db_query("UPDATE inv_movimientos SET documento_numero = %s WHERE grupo = %s AND documento_numero IS NULL "
             "RETURNING id", (factura, grupo))
    return jsonify({'success': True, 'message': 'Factura registrada.'})


# ============================================================
# SEPARACIONES (stock reservado para un cliente)
# ============================================================
@inventario_bp.route('/api/separaciones')
def api_separaciones():
    try:
        estado = request.args.get('estado') or 'Activa'
        producto_id = request.args.get('producto_id', type=int)
        empresa_id = id_empresa(request.args.get('empresa_id'))
        almacen_id = request.args.get('almacen_id', type=int)
        filas = db_query("""
            SELECT s.*, p.codigo, p.descripcion, p.unidad, COALESCE(NULLIF(e.nombre_corto, ''), e.codigo) AS empresa,
                   a.nombre AS sede, (s.vence_el < CURRENT_DATE) AS vencida
            FROM inv_separaciones s JOIN productos p ON p.id = s.producto_id
            LEFT JOIN erp_empresas e ON e.id = s.empresa_id LEFT JOIN almacenes a ON a.id = s.almacen_id
            WHERE (%s = 'Todas' OR s.estado = %s) AND (%s IS NULL OR s.producto_id = %s)
              AND (%s IS NULL OR s.empresa_id = %s) AND (%s IS NULL OR s.almacen_id = %s)
            ORDER BY s.vence_el, s.id LIMIT 500
        """, (estado, estado, producto_id, producto_id, empresa_id, empresa_id, almacen_id, almacen_id))
        return jsonify({'success': True, 'data': [_fila(f) for f in filas]})
    except Exception as e:
        return _respuesta_error(e)


@inventario_bp.route('/api/separaciones', methods=['POST'])
def api_separacion_nueva():
    d = request.get_json(silent=True) or {}
    try:
        empresa_id = _empresa(d.get('empresa_id'), 'la empresa')
        almacen_id = _entero(d.get('almacen_id'), 'la sede')
        producto_id = _entero(d.get('producto_id'), 'un producto')
        cantidad = _num(d.get('cantidad'))
        cliente = (d.get('cliente') or '').strip()
        if not cliente:
            raise ErrorInventario('Escribe para qué cliente es la separación.')
        vence = d.get('vence_el') or (date.today() + timedelta(days=DIAS_SEPARACION)).isoformat()
        if vence < date.today().isoformat():
            raise ErrorInventario('La fecha límite no puede ser pasada.')
        uid, unom = _usuario()
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            s = _bloquear_stock(cur, empresa_id, almacen_id, producto_id)
            libre = a_decimal(s['cantidad']) - _reservado(cur, empresa_id, almacen_id, producto_id)
            if cantidad > libre:
                raise ErrorInventario(f'Solo hay {max(libre, Decimal(0)).normalize():f} libres en esa empresa y sede. '
                                      'Revisa "¿Dónde está?" para ver otras sedes.')
            numero = _siguiente_numero(cur, 'SEP', 'inv_separaciones')
            cur.execute("""
                INSERT INTO inv_separaciones (numero, empresa_id, almacen_id, producto_id, cantidad, cantidad_inicial,
                    cliente, documento, vence_el, observaciones, usuario_id, usuario_nombre)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING numero
            """, (numero, empresa_id, almacen_id, producto_id, cantidad, cantidad, cliente,
                  (d.get('documento') or '').strip() or None, vence, (d.get('observaciones') or '').strip() or None,
                  uid, unom))
        return jsonify({'success': True, 'numero': numero,
                        'message': f'Separación {numero} creada. Nadie más podrá vender esas unidades hasta el {vence}.'})
    except Exception as e:
        return _respuesta_error(e)


@inventario_bp.route('/api/separaciones/<int:sid>/liberar', methods=['POST'])
def api_separacion_liberar(sid):
    try:
        uid, unom = _usuario()
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM inv_separaciones WHERE id = %s FOR UPDATE", (sid,))
            s = cur.fetchone()
            if not s or s['estado'] != 'Activa':
                raise ErrorInventario('Esa separación ya no está activa.')
            if s['usuario_id'] != uid and not (puede_aprobar() or puede_operar()):
                raise ErrorInventario('Solo quien la creó, almacén o un supervisor pueden liberarla.')
            cur.execute("UPDATE inv_separaciones SET estado = 'Liberada', cerrado_por = %s, cerrado_en = NOW() WHERE id = %s",
                        (unom, sid))
        return jsonify({'success': True, 'message': 'Separación liberada. Las unidades vuelven a estar disponibles.'})
    except Exception as e:
        return _respuesta_error(e)


# ============================================================
# CONTEOS FÍSICOS (a ciegas)
# ============================================================
@inventario_bp.route('/api/conteos')
def api_conteos():
    try:
        filas = db_query("""
            SELECT c.*, COALESCE(NULLIF(e.nombre_corto, ''), e.codigo) AS empresa, a.nombre AS sede,
                   (SELECT COUNT(*) FROM inv_conteo_items i WHERE i.conteo_id = c.id) AS productos,
                   (SELECT COUNT(*) FROM inv_conteo_items i WHERE i.conteo_id = c.id
                       AND i.stock_sistema IS NOT NULL AND i.cantidad_contada <> i.stock_sistema) AS con_diferencia,
                   (SELECT COALESCE(SUM((i.cantidad_contada - i.stock_sistema) * i.costo_promedio), 0)
                      FROM inv_conteo_items i WHERE i.conteo_id = c.id AND i.stock_sistema IS NOT NULL) AS valor_diferencia
            FROM inv_conteos c LEFT JOIN erp_empresas e ON e.id = c.empresa_id LEFT JOIN almacenes a ON a.id = c.almacen_id
            ORDER BY (c.estado IN ('En conteo', 'Por aprobar')) DESC, c.fecha DESC LIMIT 200
        """)
        return jsonify({'success': True, 'data': [_fila(f) for f in filas]})
    except Exception as e:
        return _respuesta_error(e)


@inventario_bp.route('/api/conteos', methods=['POST'])
def api_conteo_nuevo():
    if not puede_contar():
        return _no_autorizado('Los conteos los hace personal de control, no logística. Pide acceso a tu supervisor.')
    d = request.get_json(silent=True) or {}
    try:
        empresa_id = _empresa(d.get('empresa_id'), 'la empresa')
        almacen_id = _entero(d.get('almacen_id'), 'la sede')
        tipo = 'Sorpresa' if d.get('tipo') == 'Sorpresa' else 'General'
        _, unom = _usuario()
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            _validar_empresa_sede(cur, empresa_id, almacen_id)
            cur.execute("SELECT 1 FROM inv_conteos WHERE empresa_id = %s AND almacen_id = %s AND estado = 'En conteo'",
                        (empresa_id, almacen_id))
            if cur.fetchone():
                raise ErrorInventario('Ya hay un conteo abierto para esa empresa y sede. Termínalo primero.')
            cur.execute("""
                SELECT s.producto_id, s.valor, COALESCE(m.movs, 0) AS movs FROM inv_stock s
                LEFT JOIN (SELECT producto_id, COUNT(*) AS movs FROM inv_movimientos
                           WHERE empresa_id = %s AND almacen_id = %s AND fecha >= NOW() - INTERVAL '60 days'
                           GROUP BY producto_id) m ON m.producto_id = s.producto_id
                WHERE s.empresa_id = %s AND s.almacen_id = %s AND s.cantidad > 0
            """, (empresa_id, almacen_id, empresa_id, almacen_id))
            productos = cur.fetchall()
            if not productos:
                raise ErrorInventario('No hay productos con stock en esa empresa y sede.')
            if tipo == 'Sorpresa':
                # Elige al azar, dando más probabilidad a lo caro y a lo que más se mueve
                pesos = [float(p['valor'] or 0) + 50 * float(p['movs']) + 1 for p in productos]
                elegidos, pool = [], list(zip(productos, pesos))
                while pool and len(elegidos) < PRODUCTOS_CONTEO_SORPRESA:
                    p = random.choices(pool, weights=[w for _, w in pool])[0]
                    elegidos.append(p[0])
                    pool.remove(p)
                productos = elegidos
            numero = _siguiente_numero(cur, 'CNT', 'inv_conteos')
            cur.execute("INSERT INTO inv_conteos (numero, empresa_id, almacen_id, tipo, creado_por, observaciones) "
                        "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                        (numero, empresa_id, almacen_id, tipo, unom, (d.get('observaciones') or '').strip() or None))
            cid = cur.fetchone()['id']
            for p in productos:
                cur.execute("INSERT INTO inv_conteo_items (conteo_id, producto_id) VALUES (%s, %s)", (cid, p['producto_id']))
        return jsonify({'success': True, 'id': cid, 'numero': numero,
                        'message': f'Conteo {numero} creado con {len(productos)} productos.'})
    except Exception as e:
        return _respuesta_error(e)


@inventario_bp.route('/api/conteos/<int:cid>')
def api_conteo_detalle(cid):
    try:
        c = db_query("""SELECT c.*, COALESCE(NULLIF(e.nombre_corto, ''), e.codigo) AS empresa, a.nombre AS sede
                        FROM inv_conteos c LEFT JOIN erp_empresas e ON e.id = c.empresa_id
                        LEFT JOIN almacenes a ON a.id = c.almacen_id WHERE c.id = %s""", (cid,))
        if not c:
            return jsonify({'success': False, 'error': 'Conteo no encontrado.'}), 404
        items = db_query("""SELECT i.*, p.codigo, p.descripcion, p.marca, p.modelo, p.unidad
                            FROM inv_conteo_items i JOIN productos p ON p.id = i.producto_id
                            WHERE i.conteo_id = %s ORDER BY p.descripcion""", (cid,))
        conteo = _fila(c[0])
        datos = [_fila(i) for i in items]
        if conteo['estado'] == 'En conteo':
            # Conteo a ciegas: quien cuenta no ve cuánto dice el sistema
            for i in datos:
                i.pop('stock_sistema', None)
                i.pop('costo_promedio', None)
        else:
            for i in datos:
                if i.get('stock_sistema') is not None and i.get('cantidad_contada') is not None:
                    i['diferencia'] = i['cantidad_contada'] - i['stock_sistema']
                    i['valor_diferencia'] = round(i['diferencia'] * (i.get('costo_promedio') or 0), 2)
        return jsonify({'success': True, 'conteo': conteo, 'items': datos})
    except Exception as e:
        return _respuesta_error(e)


@inventario_bp.route('/api/conteos/<int:cid>/guardar', methods=['POST'])
def api_conteo_guardar(cid):
    """Guarda lo contado. Con terminar=true se cierra y pasa a aprobación."""
    if not puede_contar():
        return _no_autorizado('No tienes permiso para contar.')
    d = request.get_json(silent=True) or {}
    try:
        uid, unom = _usuario()
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM inv_conteos WHERE id = %s FOR UPDATE", (cid,))
            c = cur.fetchone()
            if not c or c['estado'] != 'En conteo':
                raise ErrorInventario('Este conteo ya fue cerrado.')
            for item_id, valor in (d.get('contado') or {}).items():
                if valor in (None, ''):
                    continue
                n = a_decimal(valor)
                if n < 0:
                    raise ErrorInventario('Lo contado no puede ser negativo.')
                cur.execute("UPDATE inv_conteo_items SET cantidad_contada = %s, comentario = %s WHERE id = %s AND conteo_id = %s",
                            (n, (d.get('comentarios') or {}).get(item_id), int(item_id), cid))
            if d.get('terminar'):
                cur.execute("SELECT COUNT(*) AS n FROM inv_conteo_items WHERE conteo_id = %s AND cantidad_contada IS NULL", (cid,))
                if cur.fetchone()['n']:
                    raise ErrorInventario('Faltan productos por contar. Si no hay ninguno, escribe 0.')
                # Foto del stock del sistema en el momento de cerrar el conteo
                cur.execute("UPDATE inv_conteo_items i SET stock_sistema = COALESCE((SELECT s.cantidad FROM inv_stock s, inv_conteos c "
                            "WHERE c.id = i.conteo_id AND s.empresa_id = c.empresa_id AND s.almacen_id = c.almacen_id "
                            "AND s.producto_id = i.producto_id), 0), costo_promedio = COALESCE((SELECT s.costo_promedio "
                            "FROM inv_stock s, inv_conteos c WHERE c.id = i.conteo_id AND s.empresa_id = c.empresa_id "
                            "AND s.almacen_id = c.almacen_id AND s.producto_id = i.producto_id), 0) WHERE i.conteo_id = %s",
                            (cid,))
                cur.execute("UPDATE inv_conteos SET estado = 'Por aprobar', contado_por_id = %s, contado_por = %s, "
                            "contado_en = NOW() WHERE id = %s", (uid, unom, cid))
        return jsonify({'success': True, 'message': 'Conteo enviado a aprobación.' if d.get('terminar') else 'Avance guardado.'})
    except Exception as e:
        return _respuesta_error(e)


@inventario_bp.route('/api/conteos/<int:cid>/aprobar', methods=['POST'])
def api_conteo_aprobar(cid):
    if not puede_aprobar():
        return _no_autorizado('Solo un supervisor puede aprobar conteos.')
    d = request.get_json(silent=True) or {}
    accion = d.get('accion', 'aprobar')
    try:
        uid, unom = _usuario()
        ajustes = 0
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM inv_conteos WHERE id = %s FOR UPDATE", (cid,))
            c = cur.fetchone()
            if not c or c['estado'] != 'Por aprobar':
                raise ErrorInventario('Este conteo no está esperando aprobación.')
            if c['contado_por_id'] == uid:
                raise ErrorInventario('Quien contó no puede aprobar su propio conteo. Debe aprobarlo otra persona.')
            if accion == 'recontar':
                cur.execute("UPDATE inv_conteo_items SET stock_sistema = NULL, costo_promedio = NULL WHERE conteo_id = %s", (cid,))
                cur.execute("UPDATE inv_conteos SET estado = 'En conteo' WHERE id = %s", (cid,))
                return jsonify({'success': True, 'message': 'Conteo devuelto para volver a contar.'})
            cur.execute("SELECT * FROM inv_conteo_items WHERE conteo_id = %s", (cid,))
            for i in cur.fetchall():
                dif = a_decimal(i['cantidad_contada']) - a_decimal(i['stock_sistema'])
                if dif == 0:
                    continue
                ajustes += 1
                aplicar_movimiento(cur, empresa_id=c['empresa_id'], almacen_id=c['almacen_id'], producto_id=i['producto_id'],
                                   motivo='SOBRANTE_CONTEO' if dif > 0 else 'FALTANTE_CONTEO', cantidad=abs(dif),
                                   costo_unitario=i['costo_promedio'] if dif > 0 else None,
                                   documento_tipo='Conteo', documento_numero=c['numero'], conteo_id=cid,
                                   observaciones=i['comentario'], aprobado_por=unom)
            cur.execute("UPDATE inv_conteos SET estado = 'Aprobado', aprobado_por = %s, aprobado_en = NOW() WHERE id = %s",
                        (unom, cid))
        return jsonify({'success': True, 'message': f"Conteo aprobado. {ajustes} producto(s) ajustado(s) en el kardex."})
    except Exception as e:
        return _respuesta_error(e)


# ============================================================
# RESUMEN Y ALERTAS ("Qué revisar hoy")
# ============================================================
def _vencimientos():
    """Atribuye el stock actual a los ingresos más recientes (primero que entra, primero que sale)
    para saber qué lotes con fecha de vencimiento siguen en el almacén."""
    stock = db_query("SELECT empresa_id, almacen_id, producto_id, cantidad FROM inv_stock WHERE cantidad > 0")
    if not stock:
        return []
    entradas = db_query("""
        SELECT m.empresa_id, m.almacen_id, m.producto_id, m.cantidad, m.fecha_vencimiento, m.lote_serie,
               p.descripcion, p.codigo
        FROM inv_movimientos m JOIN productos p ON p.id = m.producto_id
        WHERE m.estado = 'Registrado' AND m.tipo = 'ENTRADA'
          AND EXISTS (SELECT 1 FROM inv_movimientos x WHERE x.producto_id = m.producto_id AND x.fecha_vencimiento IS NOT NULL)
        ORDER BY m.fecha DESC, m.id DESC
    """)
    por_clave = {}
    for e in entradas:
        por_clave.setdefault((e['empresa_id'], e['almacen_id'], e['producto_id']), []).append(e)
    limite = date.today() + timedelta(days=DIAS_AVISO_VENCIMIENTO)
    alertas = []
    for s in stock:
        restante = a_decimal(s['cantidad'])
        for e in por_clave.get((s['empresa_id'], s['almacen_id'], s['producto_id']), []):
            if restante <= 0:
                break
            parte = min(restante, a_decimal(e['cantidad']))
            restante -= parte
            if e['fecha_vencimiento'] and e['fecha_vencimiento'] <= limite:
                alertas.append({'empresa_id': s['empresa_id'], 'almacen_id': s['almacen_id'],
                                'producto_id': s['producto_id'], 'codigo': e['codigo'], 'descripcion': e['descripcion'],
                                'lote_serie': e['lote_serie'], 'cantidad': float(parte),
                                'fecha_vencimiento': e['fecha_vencimiento'].isoformat(),
                                'vencido': e['fecha_vencimiento'] < date.today()})
    return alertas


@inventario_bp.route('/api/resumen')
def api_resumen():
    try:
        empresas = {e['id']: e['nombre'] for e in _empresas()}
        sedes = {s['id']: s['nombre'] for s in _sedes()}
        valor = db_query("""SELECT empresa_id, almacen_id, SUM(valor) AS valor, SUM(cantidad) AS unidades,
                                   COUNT(*) FILTER (WHERE cantidad > 0) AS productos
                            FROM inv_stock GROUP BY 1, 2""")
        consolidado = _consolidado()
        lento = [p for p in consolidado if p['rotacion'] == 'Lento']
        inmovil = [p for p in consolidado if p['rotacion'] == 'Inmovilizado']
        perdidas = db_query("""
            SELECT m.id, m.numero, m.fecha, m.motivo, m.cantidad, m.costo_total, m.observaciones, m.usuario_nombre,
                   m.tercero, p.descripcion, COALESCE(NULLIF(e.nombre_corto, ''), e.codigo) AS empresa, a.nombre AS sede
            FROM inv_movimientos m JOIN productos p ON p.id = m.producto_id
            LEFT JOIN erp_empresas e ON e.id = m.empresa_id LEFT JOIN almacenes a ON a.id = m.almacen_id
            WHERE m.estado = 'Registrado' AND m.motivo IN ('MERMA', 'VENCIMIENTO', 'PERDIDA_ROBO', 'FALTANTE_CONTEO', 'FALTANTE_TRASLADO')
              AND m.fecha >= date_trunc('month', NOW())
            ORDER BY m.fecha DESC
        """)
        pendientes = db_query("""
            SELECT m.id, m.numero, m.fecha, m.motivo, m.cantidad, m.costo_unitario, m.observaciones, m.usuario_nombre,
                   m.usuario_id, p.codigo, p.descripcion, COALESCE(NULLIF(e.nombre_corto, ''), e.codigo) AS empresa,
                   a.nombre AS sede
            FROM inv_movimientos m JOIN productos p ON p.id = m.producto_id
            LEFT JOIN erp_empresas e ON e.id = m.empresa_id LEFT JOIN almacenes a ON a.id = m.almacen_id
            WHERE m.estado = 'Pendiente' ORDER BY m.fecha
        """)
        traslados = db_query("""SELECT t.id, t.numero, t.fecha, t.encargado, o.nombre AS origen, d.nombre AS destino
                                FROM inv_traslados t LEFT JOIN almacenes o ON o.id = t.origen_id
                                LEFT JOIN almacenes d ON d.id = t.destino_id
                                WHERE t.estado = 'En camino' AND t.fecha < NOW() - INTERVAL '24 hours'""")
        ic_sin_factura = db_query("""SELECT DISTINCT grupo FROM inv_movimientos
                                     WHERE motivo = 'INTERCOMPANY_SALIDA' AND estado = 'Registrado'
                                       AND documento_numero IS NULL""")
        sep_vencidas = db_query("""SELECT s.id, s.numero, s.cliente, s.cantidad, s.vence_el, p.descripcion
                                   FROM inv_separaciones s JOIN productos p ON p.id = s.producto_id
                                   WHERE s.estado = 'Activa' AND s.vence_el < CURRENT_DATE""")
        conteos = db_query("SELECT id, numero, estado FROM inv_conteos WHERE estado IN ('En conteo', 'Por aprobar')")
        ultimo_conteo = db_query("""SELECT empresa_id, almacen_id, MAX(aprobado_en) AS ultimo FROM inv_conteos
                                    WHERE estado = 'Aprobado' GROUP BY 1, 2""")
        sin_ubicar = db_query("""SELECT p.id, p.codigo, p.descripcion, p.stock, p.unidad, COALESCE(p.costo_unitario, 0) AS costo_unitario
                                 FROM productos p WHERE COALESCE(p.stock, 0) > 0
                                   AND NOT EXISTS (SELECT 1 FROM inv_stock s WHERE s.producto_id = p.id)
                                   AND NOT EXISTS (SELECT 1 FROM inv_movimientos m WHERE m.producto_id = p.id AND m.estado = 'Pendiente')
                                 ORDER BY p.descripcion LIMIT 500""")
        registro = {(r['almacen_id'], r['empresa_id']): r for r in db_query("SELECT * FROM inv_sede_empresa")}
        sunat = []
        for v in valor:
            r = registro.get((v['almacen_id'], v['empresa_id']))
            if float(v['unidades'] or 0) > 0 and not (r and (r['registrado_sunat'] or r['es_domicilio_fiscal'])):
                sunat.append({'empresa': empresas.get(v['empresa_id'], '?'), 'sede': sedes.get(v['almacen_id'], '?'),
                              'unidades': float(v['unidades']), 'valor': float(v['valor'] or 0)})
        ultimos = {(u['empresa_id'], u['almacen_id']): u['ultimo'] for u in ultimo_conteo}
        sin_conteo = []
        for v in valor:
            if float(v['unidades'] or 0) <= 0:
                continue
            u = ultimos.get((v['empresa_id'], v['almacen_id']))
            if not u or (datetime.now() - u).days > 30:
                sin_conteo.append({'empresa': empresas.get(v['empresa_id'], '?'), 'sede': sedes.get(v['almacen_id'], '?'),
                                   'ultimo': _fmt(u)})
        por_ubicacion = [{'empresa_id': v['empresa_id'], 'almacen_id': v['almacen_id'],
                          'empresa': empresas.get(v['empresa_id'], '?'), 'sede': sedes.get(v['almacen_id'], '?'),
                          'valor': float(v['valor'] or 0), 'unidades': float(v['unidades'] or 0),
                          'productos': v['productos']} for v in valor]
        return jsonify({'success': True, 'data': {
            'valor_total': round(sum(x['valor'] for x in por_ubicacion), 2),
            'por_ubicacion': por_ubicacion,
            'productos_con_stock': len([p for p in consolidado if p['total'] > 0]),
            'lento': len(lento), 'inmovilizado': len(inmovil),
            'valor_inmovilizado': round(sum(p['valor'] for p in inmovil), 2),
            'perdidas_mes': [_fila(p) for p in perdidas],
            'valor_perdidas_mes': round(sum(float(p['costo_total'] or 0) for p in perdidas), 2),
            'pendientes': [dict(_fila(p), motivo_texto=MOTIVOS[p['motivo']][1]) for p in pendientes],
            'traslados_demorados': [_fila(t) for t in traslados],
            'intercompany_sin_factura': len(ic_sin_factura),
            'separaciones_vencidas': [_fila(s) for s in sep_vencidas],
            'conteos_abiertos': [_fila(c) for c in conteos],
            'sin_conteo_30_dias': sin_conteo,
            'sin_ubicar': [_fila(s) for s in sin_ubicar],
            'sedes_no_declaradas': sunat,
            'vencimientos': _vencimientos(),
            'dias_lento': DIAS_LENTO, 'dias_inmovilizado': DIAS_INMOVILIZADO,
        }})
    except Exception as e:
        return _respuesta_error(e)


# ============================================================
# CONFIGURACIÓN: qué sede está declarada en SUNAT para cada empresa
# ============================================================
@inventario_bp.route('/api/sedes_empresas', methods=['POST'])
def api_sedes_empresas():
    if not puede_aprobar():
        return _no_autorizado('Solo gerencia o un supervisor puede cambiar esta configuración.')
    filas = (request.get_json(silent=True) or {}).get('filas') or []
    try:
        with db_tx() as conn:
            cur = conn.cursor()
            for f in filas:
                cur.execute("""
                    INSERT INTO inv_sede_empresa (almacen_id, empresa_id, registrado_sunat, codigo_establecimiento,
                                                  es_domicilio_fiscal, observaciones, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,NOW())
                    ON CONFLICT (almacen_id, empresa_id) DO UPDATE SET registrado_sunat = EXCLUDED.registrado_sunat,
                        codigo_establecimiento = EXCLUDED.codigo_establecimiento,
                        es_domicilio_fiscal = EXCLUDED.es_domicilio_fiscal, observaciones = EXCLUDED.observaciones,
                        updated_at = NOW()
                """, (int(f['almacen_id']), _empresa(f['empresa_id']), bool(f.get('registrado_sunat')),
                      (f.get('codigo_establecimiento') or '').strip() or None, bool(f.get('es_domicilio_fiscal')),
                      (f.get('observaciones') or '').strip() or None))
        return jsonify({'success': True, 'message': 'Configuración guardada.'})
    except Exception as e:
        return _respuesta_error(e)


# Rutas antiguas del esqueleto (se conservan para no romper enlaces)
@inventario_bp.route('/api/estado_stock')
def get_estado_stock():
    return api_consolidado()


@inventario_bp.route('/api/entradas_salidas')
@inventario_bp.route('/api/transferencias')
def get_listas_antiguas():
    return api_kardex()


@inventario_bp.route('/api/nuevo_movimiento', methods=['POST'])
def nuevo_movimiento():
    return api_movimiento_nuevo()
