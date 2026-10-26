# routes/compras_flujo.py - Compras bajo pedido, multiempresa y multisede
#
# Idea central (pensada para personal nuevo):
#   1. Se compra para un PEDIDO DEL CLIENTE (PC). Comprar "para stock" es la excepción y
#      siempre necesita un motivo y la aprobación de una supervisora.
#   2. Toda orden de compra (OC) dice qué EMPRESA compra (KCF, AGD, ...) y en qué SEDE debe
#      terminar la mercadería (San Martín de Porres, Breña, ...). Empresas y sedes son datos.
#   3. Separación de funciones contra robos y errores:
#        - quien hace la OC no la aprueba,
#        - quien hace la OC no la paga (paga Finanzas, solo a la cuenta del proveedor),
#        - quien recogió la mercadería no la recibe: la recibe otra persona en la sede,
#        - la recepción es "a ciegas": quien recibe NO ve cuánto se pidió, cuenta lo que llegó.
#   4. Cada diferencia (faltante, sobrante, dañado, factura que no cuadra) queda como una
#      INCIDENCIA abierta hasta que una supervisora la resuelve.
#   5. Nada se borra: todo queda en el historial de la OC con usuario y fecha.
#
# Tablas: usa las que ya existían (ordenes_compra, ordenes_compra_items, recepciones_mercaderia,
# comprobantes_proveedor, finanzas_pagos) agregando columnas, y crea com_recepciones,
# com_recepcion_items, com_incidencias y com_historial. Script: migrations/004_compras.sql
import csv
import io
import json
import os
import threading
from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import Blueprint, render_template, request, jsonify, session, Response
from psycopg2.extras import RealDictCursor

from database import db_query, db_tx
from utils import a_decimal, redondear, es_admin, es_aprobador, normalizar_banco, rol_actual, tasa_igv, calcular_totales, \
    bloquear_numeracion, id_empresa
from routes.inventario import asegurar_tablas_inventario, ddl_con_tipo_empresa, _siguiente_numero, _fila, _empresas, _sedes, \
    ROLES_ALMACEN, ROLES_CONTROL_INVENTARIO
from routes.finanzas import asegurar_tablas_finanzas, ROLES_FINANZAS, METODOS_PAGO
from routes.multiempresa import filtrar_filas, filtro_sql, empresa_para_crear, empresa_filtro, empresa_id_por_ruc
from routes.moneda import ErrorMoneda, moneda_y_tc, simbolo, en_soles, pago_en_moneda, codigo_moneda, monedas_de_cuentas

compras_flujo_bp = Blueprint('compras_flujo', __name__)


def _roles(nombre, por_defecto):
    return {r.strip().lower() for r in os.environ.get(nombre, por_defecto).split(',') if r.strip()}


# Quién puede preparar órdenes de compra
ROLES_COMPRAS = _roles('ROLES_COMPRAS', 'compras,comprador,logistica,logistico,asistente_compras')
# Aprobación automática para OC pequeñas (0 = todas necesitan aprobación)
MONTO_SIN_APROBACION = a_decimal(os.environ.get('COMPRAS_MONTO_SIN_APROBACION', '0'))
# Alerta si el precio sube más de este % respecto a la última compra del mismo producto
ALERTA_PRECIO_PCT = a_decimal(os.environ.get('COMPRAS_ALERTA_PRECIO_PCT', '10'))
# Tolerancia (S/) para decir que la factura del proveedor "cuadra" con lo recibido
TOLERANCIA_FACTURA = a_decimal(os.environ.get('COMPRAS_TOLERANCIA_FACTURA', '1.00'))
# Días para avisar: pagado y la mercadería no llega / recibido y la factura no llega
DIAS_AVISO = int(os.environ.get('COMPRAS_DIAS_AVISO', '3'))

CONDICIONES = ('Contado', 'Contra entrega', 'Crédito', 'Adelanto 50%')
# 24/10/2026 (equipo de Erika): hay proveedores a los que se paga el 50% antes y el saldo después (lo ve Finanzas)
PORC_ADELANTO = Decimal('0.5')


def es_adelanto(condicion):
    return 'adelanto' in str(condicion or '').lower()


def es_credito(condicion):
    # Erika 25/10/2026: "las que el proveedor nos da al crédito deben pasar por mi aprobación, caso contrario no tienen validez"
    c = str(condicion or '').lower()
    return 'crédito' in c or 'credito' in c


def monto_adelanto(total):
    return redondear(a_decimal(total) * PORC_ADELANTO)
MODALIDADES = ('Proveedor entrega', 'Nosotros recogemos')
ESTADOS_ABIERTOS = ('Aprobada', 'Recibida parcial')
ESTADOS_PC_FUERA = ('ANULADO', 'ANULADA', 'RECHAZADO', 'RECHAZADA', 'CERRADO', 'CERRADA')
# Motivos permitidos para comprar sin pedido de cliente (Erika: poca liquidez, comprar para stock es la excepción)
MOTIVOS_SIN_PEDIDO = ('Stock estratégico', 'Crédito fiscal / IGV', 'Reposición de stock mínimo', 'Otro')
# Datos internos que NUNCA van en la orden que se manda al proveedor (son confidenciales)
CAMPOS_CONFIDENCIALES = ('pedidos', 'clientes', 'pc_numeros', 'cotizaciones_cliente', 'clientes_pedido', 'pedido_id',
                         'motivo_compra', 'motivo_stock', 'tipo_compra', 'sin_pedido', 'cotizaciones')


class ErrorCompras(Exception):
    """Error de negocio con un mensaje claro para el usuario."""


# ============================================================
# TABLAS (se crean solas; script equivalente en migrations/004_compras.sql)
# ============================================================
SQL_DDL_COMPRAS = """
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS flujo VARCHAR(10);
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS empresa_id INTEGER;
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS almacen_entrega_id INTEGER;
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS modalidad_entrega VARCHAR(30);
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS direccion_recojo TEXT;
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS tipo_compra VARCHAR(20);
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS motivo_stock TEXT;
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS fecha_compromiso DATE;
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS dias_credito INTEGER;
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS creado_por_nombre VARCHAR(150);
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS aprobado_por_id INTEGER;
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS aprobado_por VARCHAR(150);
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS aprobado_en TIMESTAMP;
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS anulado_por VARCHAR(150);
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS anulado_en TIMESTAMP;
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS motivo_anulacion TEXT;
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS responsable_recojo_id INTEGER;
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS responsable_recojo VARCHAR(150);
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS responsable_recojo_por VARCHAR(150);
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS responsable_recojo_en TIMESTAMP;
    ALTER TABLE ordenes_compra_items ADD COLUMN IF NOT EXISTS producto_id INTEGER;
    ALTER TABLE ordenes_compra_items ADD COLUMN IF NOT EXISTS unidad VARCHAR(20);
    ALTER TABLE ordenes_compra_items ADD COLUMN IF NOT EXISTS pedido_id INTEGER;
    ALTER TABLE ordenes_compra_items ADD COLUMN IF NOT EXISTS pedido_numero VARCHAR(40);
    ALTER TABLE ordenes_compra_items ADD COLUMN IF NOT EXISTS cliente VARCHAR(255);
    ALTER TABLE ordenes_compra_items ADD COLUMN IF NOT EXISTS cantidad_recibida NUMERIC(14,4) DEFAULT 0;
    ALTER TABLE recepciones_mercaderia ADD COLUMN IF NOT EXISTS producto_id INTEGER;
    ALTER TABLE recepciones_mercaderia ADD COLUMN IF NOT EXISTS empresa_id INTEGER;
    ALTER TABLE recepciones_mercaderia ADD COLUMN IF NOT EXISTS almacen_id INTEGER;
    ALTER TABLE recepciones_mercaderia ADD COLUMN IF NOT EXISTS costo_unitario NUMERIC(16,6);
    ALTER TABLE recepciones_mercaderia ADD COLUMN IF NOT EXISTS com_recepcion_id INTEGER;
    ALTER TABLE recepciones_mercaderia ADD COLUMN IF NOT EXISTS oc_item_id INTEGER;
    ALTER TABLE recepciones_mercaderia ADD COLUMN IF NOT EXISTS pedido_id INTEGER;
    ALTER TABLE recepciones_mercaderia ADD COLUMN IF NOT EXISTS pedido_numero VARCHAR(40);
    ALTER TABLE recepciones_mercaderia ADD COLUMN IF NOT EXISTS cliente VARCHAR(255);
    ALTER TABLE recepciones_mercaderia ADD COLUMN IF NOT EXISTS guia_proveedor VARCHAR(60);
    ALTER TABLE recepciones_mercaderia ADD COLUMN IF NOT EXISTS lote_serie VARCHAR(120);
    ALTER TABLE recepciones_mercaderia ADD COLUMN IF NOT EXISTS fecha_vencimiento DATE;
    ALTER TABLE comprobantes_proveedor ADD COLUMN IF NOT EXISTS empresa_id INTEGER;
    ALTER TABLE comprobantes_proveedor ADD COLUMN IF NOT EXISTS fecha_vencimiento DATE;
    ALTER TABLE comprobantes_proveedor ADD COLUMN IF NOT EXISTS monto_esperado NUMERIC(14,2);
    ALTER TABLE comprobantes_proveedor ADD COLUMN IF NOT EXISTS cuadra BOOLEAN;
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS motivo_compra VARCHAR(60);
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS pedido_id INTEGER;
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS pc_numeros TEXT;
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS cotizaciones_cliente TEXT;
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS clientes_pedido TEXT;
    ALTER TABLE ordenes_compra_items ADD COLUMN IF NOT EXISTS cotizacion_numero VARCHAR(60);
    CREATE TABLE IF NOT EXISTS com_anulaciones (
        id SERIAL PRIMARY KEY,
        fecha TIMESTAMP NOT NULL DEFAULT NOW(),
        tabla VARCHAR(40) NOT NULL,
        registro_id INTEGER NOT NULL,
        numero VARCHAR(60),
        accion VARCHAR(20) NOT NULL,
        motivo TEXT NOT NULL,
        usuario_id INTEGER,
        usuario VARCHAR(150),
        respaldo JSONB
    );
    CREATE INDEX IF NOT EXISTS idx_com_anul_tabla ON com_anulaciones (tabla, registro_id);
    CREATE TABLE IF NOT EXISTS com_recepciones (
        id SERIAL PRIMARY KEY,
        numero VARCHAR(30) UNIQUE,
        fecha TIMESTAMP NOT NULL DEFAULT NOW(),
        orden_compra_id INTEGER NOT NULL,
        empresa_id INTEGER,
        almacen_id INTEGER NOT NULL,
        guia_proveedor VARCHAR(60) NOT NULL,
        traido_por_tipo VARCHAR(20) NOT NULL,
        traido_por_id INTEGER,
        traido_por VARCHAR(150),
        recibido_por_id INTEGER,
        recibido_por VARCHAR(150),
        con_diferencias BOOLEAN NOT NULL DEFAULT false,
        observaciones TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS com_recepcion_items (
        id SERIAL PRIMARY KEY,
        recepcion_id INTEGER NOT NULL REFERENCES com_recepciones(id),
        oc_item_id INTEGER NOT NULL,
        producto_id INTEGER,
        pendiente_antes NUMERIC(14,4),
        cantidad_buena NUMERIC(14,4) NOT NULL DEFAULT 0 CHECK (cantidad_buena >= 0),
        cantidad_danada NUMERIC(14,4) NOT NULL DEFAULT 0 CHECK (cantidad_danada >= 0),
        lote_serie VARCHAR(120),
        fecha_vencimiento DATE,
        comentario TEXT
    );
    CREATE TABLE IF NOT EXISTS com_incidencias (
        id SERIAL PRIMARY KEY,
        numero VARCHAR(30) UNIQUE,
        fecha TIMESTAMP NOT NULL DEFAULT NOW(),
        orden_compra_id INTEGER NOT NULL,
        recepcion_id INTEGER,
        comprobante_id INTEGER,
        producto_id INTEGER,
        tipo VARCHAR(30) NOT NULL,
        cantidad NUMERIC(14,4),
        monto NUMERIC(14,2),
        detalle TEXT,
        estado VARCHAR(20) NOT NULL DEFAULT 'Abierta',
        resolucion TEXT,
        resuelto_por VARCHAR(150),
        resuelto_en TIMESTAMP,
        reportado_por VARCHAR(150)
    );
    CREATE TABLE IF NOT EXISTS com_historial (
        id SERIAL PRIMARY KEY,
        orden_compra_id INTEGER NOT NULL,
        fecha TIMESTAMP NOT NULL DEFAULT NOW(),
        usuario_id INTEGER,
        usuario VARCHAR(150),
        accion VARCHAR(60) NOT NULL,
        detalle TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_oci_pedido ON ordenes_compra_items (pedido_id, producto_id);
    CREATE INDEX IF NOT EXISTS idx_com_hist_oc ON com_historial (orden_compra_id, id);
    CREATE INDEX IF NOT EXISTS idx_com_inc_oc ON com_incidencias (orden_compra_id);
    CREATE INDEX IF NOT EXISTS idx_rm_com ON recepciones_mercaderia (com_recepcion_id);
"""

_tablas_listas = False
_lock_tablas = threading.Lock()


def asegurar_tablas_compras():
    global _tablas_listas
    if _tablas_listas:
        return
    with _lock_tablas:
        if _tablas_listas:
            return
        asegurar_tablas_inventario()
        asegurar_tablas_finanzas()
        with db_tx() as conn:
            cur = conn.cursor()
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('compras_ddl'))")
            cur.execute(ddl_con_tipo_empresa(cur, SQL_DDL_COMPRAS))
        _tablas_listas = True


@compras_flujo_bp.before_request
def _antes():
    asegurar_tablas_compras()


# ============================================================
# PERMISOS
# ============================================================
def puede_comprar():
    return es_admin() or es_aprobador() or rol_actual() in ROLES_COMPRAS


def puede_aprobar():
    # 24/10/2026: también quien tiene "Aprobar" en Orden de compra en Usuarios y permisos (Hellen)
    from routes.acceso import tiene_permiso
    return es_admin() or es_aprobador() or tiene_permiso('ORDEN_COMPRA', 'puede_aprobar')


def puede_pagar():
    return es_admin() or es_aprobador() or rol_actual() in ROLES_FINANZAS


def puede_recibir():
    return es_admin() or es_aprobador() or rol_actual() in ROLES_ALMACEN or rol_actual() in ROLES_CONTROL_INVENTARIO


def puede_facturar():
    return puede_pagar() or puede_comprar()


def _usuario():
    return session.get('usuario_id'), (session.get('nombre_completo') or session.get('usuario') or 'Usuario')


def _no_autorizado(msg):
    return jsonify({'success': False, 'error': msg}), 403


def _respuesta_error(e):
    if isinstance(e, (ErrorCompras, ErrorMoneda)):
        return jsonify({'success': False, 'error': str(e)}), 400
    if isinstance(e, PermissionError):
        return jsonify({'success': False, 'error': str(e)}), 403
    print(f'❌ Compras: {e}')
    return jsonify({'success': False, 'error': 'No se pudo completar la operación. Intenta de nuevo.'}), 500


def _entero(valor, nombre):
    try:
        n = int(valor)
        if n > 0:
            return n
    except (TypeError, ValueError):
        pass
    raise ErrorCompras(f'Elige {nombre}.')


def _empresa(valor, nombre='la empresa que compra'):
    """Id de empresa válido: UUID (Supabase) o entero (bases antiguas)."""
    eid = id_empresa(valor)
    if eid is None:
        raise ErrorCompras(f'Elige {nombre}.')
    return eid


def _historial(cur, oc_id, accion, detalle=None):
    uid, unom = _usuario()
    cur.execute("INSERT INTO com_historial (orden_compra_id, usuario_id, usuario, accion, detalle) VALUES (%s,%s,%s,%s,%s)",
                (oc_id, uid, unom, accion, detalle))


def _incidencia(cur, oc_id, tipo, detalle, recepcion_id=None, comprobante_id=None, producto_id=None,
                cantidad=None, monto=None):
    _, unom = _usuario()
    numero = _siguiente_numero(cur, 'INC', 'com_incidencias')
    cur.execute("""
        INSERT INTO com_incidencias (numero, orden_compra_id, recepcion_id, comprobante_id, producto_id, tipo,
            cantidad, monto, detalle, reportado_por)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id, numero
    """, (numero, oc_id, recepcion_id, comprobante_id, producto_id, tipo, cantidad, monto, detalle, unom))
    return cur.fetchone()


def _cant(n):
    return f'{a_decimal(n).normalize():f}'


def _diferencias_recepcion(oc_items, contados):
    """Lo que no coincide entre lo contado y lo que falta recibir de la OC, en palabras simples."""
    difs = []
    for iid, oi in oc_items.items():
        pendiente = a_decimal(oi['cantidad']) - a_decimal(oi['cantidad_recibida'])
        if iid not in contados:
            if pendiente > 0:
                difs.append({'producto': oi['producto'], 'pide': float(pendiente), 'registras': 0, 'danada': 0,
                             'tipo': 'Falta', 'texto': f"{oi['producto']}: la OC pide {_cant(pendiente)} y no registras ninguno → faltan {_cant(pendiente)}"})
            continue
        buena, danada, _ = contados[iid]
        llego = buena + danada
        u = (' ' + oi['unidad']) if oi.get('unidad') else ''
        base = {'producto': oi['producto'], 'pide': float(pendiente), 'registras': float(buena), 'danada': float(danada)}
        if buena > pendiente:
            difs.append({**base, 'tipo': 'Sobra', 'texto': f"{oi['producto']}: la OC pide {_cant(pendiente)}{u}, estás registrando "
                         f"{_cant(buena)} → sobran {_cant(buena - pendiente)}"})
        elif llego < pendiente:
            difs.append({**base, 'tipo': 'Falta', 'texto': f"{oi['producto']}: la OC pide {_cant(pendiente)}{u}, estás registrando "
                         f"{_cant(llego)} → faltan {_cant(pendiente - llego)}"})
        if danada > 0:
            difs.append({**base, 'tipo': 'Dañado', 'texto': f"{oi['producto']}: {_cant(danada)}{u} dañados"})
    return difs


def motivo_sin_pedido(d):
    """Motivo obligatorio para comprar sin pedido de cliente. Devuelve (motivo de la lista, detalle).
    Acepta motivo_compra (lista) + motivo_stock (texto, obligatorio si es "Otro"). Por compatibilidad,
    un texto libre de 10+ letras sin motivo de lista se guarda como "Otro"."""
    motivo = (d.get('motivo_compra') or '').strip()
    detalle = (d.get('motivo_stock') or d.get('motivo_detalle') or '').strip()
    if motivo:
        if motivo not in MOTIVOS_SIN_PEDIDO:
            raise ErrorCompras('Elige el motivo de la compra sin pedido de la lista.')
        if motivo == 'Otro' and len(detalle) < 5:
            raise ErrorCompras('Elegiste "Otro": escribe el motivo de la compra sin pedido.')
        return motivo, (detalle or motivo)
    if len(detalle) >= 10:
        return 'Otro', detalle
    raise ErrorCompras('Es una compra SIN pedido de cliente (para stock): elige el motivo '
                       '(Stock estratégico, Crédito fiscal / IGV, Reposición de stock mínimo u Otro).')


def registrar_anulacion(cur, tabla, registro_id, numero, accion, motivo, respaldo=None):
    """Deja constancia (no se borra) de quién anuló o eliminó un documento de Compras, cuándo y por qué."""
    uid, unom = _usuario()
    cur.execute("""INSERT INTO com_anulaciones (tabla, registro_id, numero, accion, motivo, usuario_id, usuario, respaldo)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (tabla, registro_id, numero, accion, motivo, uid, unom,
                 json.dumps(respaldo, default=str) if respaldo is not None else None))


def fecha_hora(v):
    """DD/MM/YYYY HH:MM (hora de Lima, como está en la base)."""
    if isinstance(v, datetime):
        return v.strftime('%d/%m/%Y %H:%M')
    if isinstance(v, date):
        return v.strftime('%d/%m/%Y')
    return v or ''


SQL_PROVEEDORES_CON_CONTACTO = """
    SELECT p.id, p.ruc, p.razon_social, p.razon_comercial, p.direccion, p.lugar_recojo, p.condicion_pago,
           p.tiempo_credito, p.banco, p.numero_cuenta, p.cci,
           COALESCE(NULLIF(p.contacto, ''), pc.nombre_contacto) AS contacto,
           COALESCE(NULLIF(p.telefono, ''), pc.telefono) AS telefono,
           COALESCE(NULLIF(p.email, ''), pc.email) AS email,
           pc.cargo AS contacto_cargo
    FROM proveedores p
    LEFT JOIN LATERAL (
        SELECT c.nombre_contacto, c.telefono, c.email, c.cargo FROM proveedores_contactos c
        WHERE c.proveedor_id = p.id AND COALESCE(c.activo, true) = true
        ORDER BY COALESCE(c.principal, false) DESC, c.id LIMIT 1
    ) pc ON true
"""


def proveedores_con_contacto(where='COALESCE(p.activo, true) = true', params=(), limite=2000):
    """Proveedores con su contacto principal (tabla proveedores_contactos) para autollenar la OC:
    razón social, RUC, dirección fiscal, contacto, teléfono y correo."""
    return db_query(SQL_PROVEEDORES_CON_CONTACTO + ' WHERE ' + where + f' ORDER BY p.razon_social LIMIT {int(limite)}', params)


# ============================================================
# CONSULTAS DE APOYO
# ============================================================
def _items_pedido(pc):
    """Normaliza los productos de un pedido del cliente (items_json puede venir como objetos o como listas)."""
    crudo = pc.get('items_json') or []
    if isinstance(crudo, str):
        try:
            crudo = json.loads(crudo)
        except ValueError:
            crudo = []
    if isinstance(crudo, dict):
        crudo = crudo.get('items') or list(crudo.values())
    items = []
    for it in crudo or []:
        if isinstance(it, dict):
            items.append({'producto_id': it.get('producto_id') or it.get('id_producto'),
                          'codigo': (it.get('codigo') or '').strip(),
                          'descripcion': it.get('producto') or it.get('descripcion') or '',
                          'unidad': it.get('um') or it.get('unidad') or '',
                          'cantidad': a_decimal(it.get('cantidad_pc') or it.get('cantidad') or 0)})
        elif isinstance(it, (list, tuple)) and len(it) > 1:
            items.append({'producto_id': None, 'codigo': str(it[0] or '').strip(), 'descripcion': it[1] or '',
                          'unidad': '', 'cantidad': a_decimal(it[5] if len(it) > 5 else 1)})
    return items


def _stock_libre_grupo(producto_ids):
    """Stock que se puede usar sin comprar: todo el grupo, menos lo separado para clientes."""
    if not producto_ids:
        return {}
    filas = db_query("""
        WITH st AS (SELECT producto_id, SUM(cantidad) AS c FROM inv_stock WHERE producto_id = ANY(%s) GROUP BY producto_id),
             sp AS (SELECT producto_id, SUM(cantidad) AS c FROM inv_separaciones
                    WHERE estado = 'Activa' AND vence_el >= CURRENT_DATE AND producto_id = ANY(%s) GROUP BY producto_id)
        SELECT st.producto_id, st.c - COALESCE(sp.c, 0) AS libre FROM st LEFT JOIN sp USING (producto_id)
    """, (list(producto_ids), list(producto_ids)))
    return {f['producto_id']: max(a_decimal(f['libre']), Decimal('0')) for f in filas}


def _stock_libre_empresa(producto_ids, empresa_id):
    """Stock disponible de UNA empresa (todas sus sedes), menos lo separado para clientes."""
    if not producto_ids or empresa_id is None:
        return {}
    filas = db_query("""
        WITH st AS (SELECT producto_id, SUM(cantidad) AS c FROM inv_stock
                    WHERE producto_id = ANY(%s) AND empresa_id = %s GROUP BY producto_id),
             sp AS (SELECT producto_id, SUM(cantidad) AS c FROM inv_separaciones
                    WHERE estado = 'Activa' AND vence_el >= CURRENT_DATE AND producto_id = ANY(%s) AND empresa_id = %s
                    GROUP BY producto_id)
        SELECT st.producto_id, st.c - COALESCE(sp.c, 0) AS libre FROM st LEFT JOIN sp USING (producto_id)
    """, (list(producto_ids), empresa_id, list(producto_ids), empresa_id))
    return {f['producto_id']: max(a_decimal(f['libre']), Decimal('0')) for f in filas}


_cols_cache = {}


def _tiene_columna(tabla, columna):
    clave = (tabla, columna)
    if clave not in _cols_cache:
        _cols_cache[clave] = bool(db_query("""SELECT 1 FROM information_schema.columns
                                             WHERE table_name = %s AND column_name = %s""", (tabla, columna)))
    return _cols_cache[clave]


def _detalle_stock_libre(producto_id):
    filas = db_query("""
        SELECT COALESCE(NULLIF(e.nombre_corto, ''), e.codigo) AS empresa, a.nombre AS sede,
               s.cantidad - COALESCE((SELECT SUM(x.cantidad) FROM inv_separaciones x WHERE x.estado = 'Activa'
                   AND x.vence_el >= CURRENT_DATE AND x.producto_id = s.producto_id AND x.empresa_id = s.empresa_id
                   AND x.almacen_id = s.almacen_id), 0) AS libre
        FROM inv_stock s JOIN erp_empresas e ON e.id = s.empresa_id JOIN almacenes a ON a.id = s.almacen_id
        WHERE s.producto_id = %s AND s.cantidad > 0 ORDER BY e.id, a.id
    """, (producto_id,))
    return [{'empresa': f['empresa'], 'sede': f['sede'], 'libre': float(max(a_decimal(f['libre']), 0))}
            for f in filas if a_decimal(f['libre']) > 0]


def _resolver_productos(items):
    """Completa producto_id por código cuando el pedido no lo trae."""
    codigos = {i['codigo'] for i in items if not i['producto_id'] and i['codigo']}
    if codigos:
        mapa = {f['codigo']: f['id'] for f in db_query(
            "SELECT DISTINCT ON (codigo) codigo, id FROM productos WHERE codigo = ANY(%s) ORDER BY codigo, id",
            (list(codigos),))}
        for i in items:
            if not i['producto_id'] and i['codigo']:
                i['producto_id'] = mapa.get(i['codigo'])
    for i in items:
        try:
            i['producto_id'] = int(i['producto_id']) if i['producto_id'] else None
        except (TypeError, ValueError):
            i['producto_id'] = None
    return items


def _comprado_por_pedido(cur=None, excluir_oc=None):
    sql = """
        SELECT oci.pedido_id, oci.producto_id, SUM(oci.cantidad) AS c
        FROM ordenes_compra_items oci JOIN ordenes_compra oc ON oc.id = oci.orden_compra_id
        WHERE oci.pedido_id IS NOT NULL AND COALESCE(oc.estado, '') <> 'Anulada' AND oc.id <> COALESCE(%s, -1)
        GROUP BY oci.pedido_id, oci.producto_id
    """
    if cur:
        cur.execute(sql, (excluir_oc,))
        filas = cur.fetchall()
    else:
        filas = db_query(sql, (excluir_oc,))
    return {(f['pedido_id'], f['producto_id']): a_decimal(f['c']) for f in filas}


def _pedidos_por_comprar(todos=False, pedido_id=None, excluir_oc=None, sin_filtro=False, solo_por_comprar=False):
    col_emp = 'empresa_id' if _tiene_columna('pedido_compra_pc', 'empresa_id') else 'NULL AS empresa_id'
    filas = db_query("""
        SELECT id, numero, fecha, cliente, ruc, estado, items_json, lugar_entrega, cotizacion_numero, """ + col_emp + """
        FROM pedido_compra_pc
        WHERE COALESCE(UPPER(estado), '') <> ALL(%s) AND (%s::int IS NULL OR id = %s::int)
        ORDER BY fecha DESC NULLS LAST, id DESC LIMIT 300
    """, (list(ESTADOS_PC_FUERA), pedido_id, pedido_id))
    if pedido_id is None and not sin_filtro:
        filas = filtrar_filas('pedido_compra_pc', filas)   # solo los pedidos de la empresa elegida arriba
    comprado = _comprado_por_pedido(excluir_oc=excluir_oc)
    # N° de las OC activas de cada línea, para mostrar "OC ya generada: OC-..." (pedido de Erika 21/10/2026)
    ocs_linea = {}
    for f in db_query("""SELECT oci.pedido_id, oci.producto_id, string_agg(DISTINCT oc.numero_orden, ', ') AS ocs
                          FROM ordenes_compra_items oci JOIN ordenes_compra oc ON oc.id = oci.orden_compra_id
                          WHERE oci.pedido_id IS NOT NULL AND COALESCE(oc.estado, '') <> 'Anulada' AND oc.id <> COALESCE(%s, -1)
                          GROUP BY oci.pedido_id, oci.producto_id""", (excluir_oc,)):
        ocs_linea[(f['pedido_id'], f['producto_id'])] = f['ocs']
    pedidos, ids = [], set()
    for pc in filas:
        items = _resolver_productos(_items_pedido(pc))
        for it in items:
            ya = comprado.get((pc['id'], it['producto_id']), Decimal('0')) if it['producto_id'] else Decimal('0')
            it['comprado'] = ya
            it['ocs'] = ocs_linea.get((pc['id'], it['producto_id'])) if it['producto_id'] else None
            it['falta'] = max(it['cantidad'] - ya, Decimal('0'))
            if it['producto_id']:
                ids.add(it['producto_id'])
        pend = [i for i in items if i['falta'] > 0]
        if not todos and not pend:
            continue
        pedidos.append({'id': pc['id'], 'numero': pc['numero'], 'fecha': pc['fecha'], 'cliente': pc['cliente'],
                        'ruc': pc['ruc'], 'estado': pc['estado'], 'lugar_entrega': pc['lugar_entrega'],
                        'cotizacion': pc['cotizacion_numero'], 'items': items,
                        'empresa_id': pc.get('empresa_id') or empresa_filtro()})
    libre = _stock_libre_grupo(ids)
    por_empresa = {}
    for eid in {p['empresa_id'] for p in pedidos if p['empresa_id'] is not None}:
        por_empresa[eid] = _stock_libre_empresa(ids, eid)
    # El stock libre se REPARTE entre los pedidos, el más antiguo primero (22/10/2026). Antes cada pedido usaba
    # todo el stock: con 32 en stock, un PC de 18 y otro de 40, el de 18 salía "cubierto con stock" y el de 40
    # "comprar 8", pero en total faltan 26 (58 − 32). Ahora al PC más antiguo le tocan 18 y al otro 14.
    restante = {}
    for p in sorted(pedidos, key=lambda x: (str(x['fecha'] or ''), x['id'])):
        for it in p['items']:
            if not it['producto_id']:
                continue
            if p['empresa_id'] is not None:
                llave = (str(p['empresa_id']), it['producto_id'])
                total_st = por_empresa.get(p['empresa_id'], {}).get(it['producto_id'], Decimal('0'))
            else:
                llave = ('grupo', it['producto_id'])
                total_st = libre.get(it['producto_id'], Decimal('0'))
            if llave not in restante:
                restante[llave] = total_st
            toca = min(max(restante[llave], Decimal('0')), it['falta'])
            restante[llave] -= toca
            it['_st_total'], it['_st_asignado'] = total_st, toca
    for p in pedidos:
        for it in p['items']:
            it['stock_libre'] = float(libre.get(it['producto_id'], 0)) if it['producto_id'] else 0
            # Tabla resumen de Erika: pedido del cliente − stock que le toca a este pedido = comprar para el pedido
            st_total = it.pop('_st_total', Decimal('0'))
            st = it.pop('_st_asignado', Decimal('0'))
            it['stock_empresa'] = float(st_total)
            it['stock_asignado'] = float(st)
            it['stock_otros_pedidos'] = float(max(min(st_total, it['falta']) - st, Decimal('0')))
            it['comprar_pedido'] = float(max(it['falta'] - st, Decimal('0')))
            for k in ('cantidad', 'comprado', 'falta'):
                it[k] = float(it[k])
        p['empresa_id'] = str(p['empresa_id']) if p['empresa_id'] is not None else None
        p['fecha'] = p['fecha'].strftime('%Y-%m-%d') if isinstance(p['fecha'], (date, datetime)) else p['fecha']
        p['pendientes'] = sum(1 for i in p['items'] if i['falta'] > 0)
        # Lo que de verdad falta comprar: ni en órdenes ni en stock (pedido de Erika 21/10/2026)
        p['por_comprar'] = sum(1 for i in p['items'] if i['falta'] > 0 and (i['comprar_pedido'] > 0 or not i['producto_id']))
    if solo_por_comprar:
        pedidos = [p for p in pedidos if p['por_comprar'] > 0]
    return pedidos


def _ultimo_precio(cur, producto_id, excluir_oc=None):
    cur.execute("""
        SELECT oci.precio_unitario, oc.numero_orden, COALESCE(oc.fecha_creacion, oc.created_at) AS fecha,
               p.razon_social AS proveedor
        FROM ordenes_compra_items oci JOIN ordenes_compra oc ON oc.id = oci.orden_compra_id
        LEFT JOIN proveedores p ON p.id = oc.proveedor_id
        WHERE oci.producto_id = %s AND COALESCE(oc.estado, '') NOT IN ('Anulada', 'Borrador')
          AND oc.id <> COALESCE(%s, -1) AND COALESCE(oci.precio_unitario, 0) > 0
        ORDER BY oc.id DESC LIMIT 1
    """, (producto_id, excluir_oc))
    return cur.fetchone()


def _alertas_precio(cur, oc_id, items):
    alertas = []
    for it in items:
        u = _ultimo_precio(cur, it['producto_id'], oc_id)
        if not u:
            continue
        antes = a_decimal(u['precio_unitario'])
        ahora = a_decimal(it['precio_unitario'])
        if antes > 0 and ahora > antes * (1 + ALERTA_PRECIO_PCT / 100):
            pct = redondear((ahora / antes - 1) * 100, 1)
            fecha = u['fecha'].strftime('%d/%m/%Y') if u['fecha'] else ''
            alertas.append(f"{it.get('descripcion') or it.get('producto')}: {pct}% más caro que la última compra "
                           f"(S/ {redondear(antes, 2)} a {u['proveedor'] or 'otro proveedor'} el {fecha}, {u['numero_orden']}).")
    return alertas


def _sede_declarada(empresa_id, almacen_id):
    """True / False si está marcado en Inventario ▸ Sedes y SUNAT; None si nadie lo ha marcado aún."""
    f = db_query("SELECT registrado_sunat, es_domicilio_fiscal FROM inv_sede_empresa WHERE empresa_id = %s AND almacen_id = %s",
                 (empresa_id, almacen_id))
    if not f:
        return None
    return bool(f[0]['registrado_sunat'] or f[0]['es_domicilio_fiscal'])


def _pagado_oc(oc_id):
    f = db_query("""
        SELECT COALESCE(SUM(monto), 0) AS pagado FROM finanzas_pagos
        WHERE tipo = 'PAGO' AND estado <> 'Anulado'
          AND ((documento_tabla = 'ordenes_compra' AND documento_id = %s)
            OR (documento_tabla = 'comprobantes_proveedor' AND documento_id IN
                (SELECT id FROM comprobantes_proveedor WHERE orden_compra_id = %s
                   AND COALESCE(UPPER(estado), '') NOT IN ('ANULADO', 'ANULADA'))))
    """, (oc_id, oc_id))
    return a_decimal(f[0]['pagado'])


# ============================================================
# LISTA Y DETALLE DE ÓRDENES (con el "siguiente paso" calculado)
# ============================================================
SQL_OC_LISTA = """
    WITH it AS (
        SELECT orden_compra_id, COUNT(*) AS lineas, SUM(cantidad) AS pedida, SUM(COALESCE(cantidad_recibida, 0)) AS recibida,
               SUM(LEAST(COALESCE(cantidad_recibida, 0), cantidad) * precio_unitario) AS valor_recibido,
               string_agg(DISTINCT pedido_numero, ', ') AS pedidos, string_agg(DISTINCT cliente, ', ') AS clientes,
               string_agg(DISTINCT cotizacion_numero, ', ') AS cotizaciones,
               string_agg(producto, ' · ' ORDER BY id) AS productos
        FROM ordenes_compra_items GROUP BY orden_compra_id
    ),
    pg AS (
        SELECT oc2.id, COALESCE(SUM(fp.monto), 0) AS pagado
        FROM ordenes_compra oc2
        JOIN finanzas_pagos fp ON fp.tipo = 'PAGO' AND fp.estado <> 'Anulado'
          AND ((fp.documento_tabla = 'ordenes_compra' AND fp.documento_id = oc2.id)
            OR (fp.documento_tabla = 'comprobantes_proveedor' AND fp.documento_id IN
                (SELECT cp.id FROM comprobantes_proveedor cp WHERE cp.orden_compra_id = oc2.id)))
        GROUP BY oc2.id
    ),
    fa AS (
        SELECT orden_compra_id, COUNT(*) AS facturas, SUM(monto) AS facturado, BOOL_AND(COALESCE(cuadra, true)) AS cuadra
        FROM comprobantes_proveedor WHERE COALESCE(UPPER(estado), '') NOT IN ('ANULADO', 'ANULADA') AND orden_compra_id IS NOT NULL
        GROUP BY orden_compra_id
    ),
    inc AS (SELECT orden_compra_id, COUNT(*) AS abiertas FROM com_incidencias WHERE estado = 'Abierta' GROUP BY orden_compra_id)
    SELECT oc.id, oc.numero_orden AS numero, COALESCE(oc.fecha_creacion, oc.created_at) AS fecha, oc.estado, oc.flujo,
           oc.empresa_id, COALESCE(NULLIF(e.nombre_corto, ''), e.codigo) AS empresa,
           oc.almacen_entrega_id, a.nombre AS sede, oc.modalidad_entrega, oc.direccion_recojo, oc.tipo_compra,
           oc.motivo_stock, oc.fecha_compromiso, oc.condicion_pago, oc.dias_credito, oc.num_cotizacion, oc.notas,
           oc.proveedor_id, COALESCE(p.razon_social, oc.contacto_proveedor) AS proveedor, p.ruc,
           oc.subtotal, oc.igv, oc.total, COALESCE(oc.moneda, 'PEN') AS moneda, oc.tipo_cambio, oc.usuario_id, oc.creado_por_nombre, oc.aprobado_por_id, oc.aprobado_por,
           oc.aprobado_en, oc.motivo_anulacion, oc.motivo_compra, oc.created_at, oc.updated_at,
           oc.responsable_recojo_id, oc.responsable_recojo, oc.responsable_recojo_por, oc.responsable_recojo_en,
           COALESCE(it.pedidos, oc.pc_numeros) AS pc_numeros, COALESCE(it.cotizaciones, oc.cotizaciones_cliente) AS cotizaciones_cliente,
           COALESCE(it.clientes, oc.clientes_pedido) AS clientes_pedido,
           (COALESCE(it.pedidos, oc.pc_numeros) IS NULL) AS sin_pedido,
           COALESCE(it.lineas, 0) AS lineas, COALESCE(it.pedida, 0) AS pedida, COALESCE(it.recibida, 0) AS recibida,
           COALESCE(it.valor_recibido, 0) AS valor_recibido, it.pedidos, it.clientes, it.productos,
           COALESCE(pg.pagado, 0) AS pagado, COALESCE(fa.facturas, 0) AS facturas, COALESCE(fa.facturado, 0) AS facturado,
           fa.cuadra, COALESCE(inc.abiertas, 0) AS incidencias
    FROM ordenes_compra oc
    LEFT JOIN erp_empresas e ON e.id = oc.empresa_id
    LEFT JOIN almacenes a ON a.id = oc.almacen_entrega_id
    LEFT JOIN proveedores p ON p.id = oc.proveedor_id
    LEFT JOIN it ON it.orden_compra_id = oc.id
    LEFT JOIN pg ON pg.id = oc.id
    LEFT JOIN fa ON fa.orden_compra_id = oc.id
    LEFT JOIN inc ON inc.orden_compra_id = oc.id
"""


def _es_intercompany(ruc):
    try:
        return bool(empresa_id_por_ruc(ruc))
    except Exception:
        return False


def _paso(o):
    """Qué toca hacer con esta OC y quién lo hace. Es lo que ve el personal en la lista."""
    estado = o['estado'] or 'Borrador'
    total = a_decimal(o['total'])
    pagado = a_decimal(o['pagado'])
    contado = (o.get('condicion_pago') or '').startswith('Contado')
    # Compra intercompany (el proveedor es otra empresa del grupo, ej. AGD → KCF): la mercadería se puede
    # recibir antes del pago; el pago queda pendiente como aviso (Erika, 22/10/2026)
    if contado and _es_intercompany(o.get('ruc')):
        contado = False
    if o.get('flujo') != 'v2':
        return {'codigo': 'antigua', 'texto': 'OC del sistema anterior', 'quien': '—'}
    if estado == 'Anulada':
        return {'codigo': 'anulada', 'texto': 'Anulada', 'quien': '—'}
    if estado == 'Borrador':
        return {'codigo': 'enviar', 'texto': 'Terminar y enviar a aprobar', 'quien': 'Compras'}
    if estado == 'Por aprobar':
        return {'codigo': 'aprobar', 'texto': 'Aprobar', 'quien': 'Supervisora'}
    if estado in ESTADOS_ABIERTOS and contado and pagado < total:
        return {'codigo': 'pagar', 'texto': 'Pagar al proveedor (es al contado)', 'quien': 'Finanzas'}
    if estado in ESTADOS_ABIERTOS and es_adelanto(o.get('condicion_pago')) and pagado < monto_adelanto(total) \
            and not _es_intercompany(o.get('ruc')):
        return {'codigo': 'pagar', 'texto': 'Pagar el adelanto del 50% (el saldo lo paga Finanzas después)', 'quien': 'Finanzas'}
    if estado in ESTADOS_ABIERTOS:
        texto = 'Recibir lo que falta' if estado == 'Recibida parcial' else (
            'Recoger y recibir en sede' if o.get('modalidad_entrega') == 'Nosotros recogemos' else 'Recibir en sede')
        return {'codigo': 'recibir', 'texto': texto, 'quien': 'Almacén (otra persona)'}
    if a_decimal(o['incidencias']) > 0:
        return {'codigo': 'incidencia', 'texto': 'Resolver diferencias', 'quien': 'Supervisora'}
    if a_decimal(o['facturas']) == 0:
        return {'codigo': 'factura', 'texto': 'Registrar factura del proveedor', 'quien': 'Finanzas / Compras'}
    if pagado < a_decimal(o['facturado']):
        return {'codigo': 'pagar_credito', 'texto': 'Pagar factura (crédito)', 'quien': 'Finanzas'}
    return {'codigo': 'listo', 'texto': 'Completa', 'quien': '—'}


def _oc_dict(o):
    d = _fila(o)
    d['paso'] = _paso(o)
    d['saldo_pago'] = float(max(a_decimal(o['total']) - a_decimal(o['pagado']), 0))
    if es_adelanto(o.get('condicion_pago')):
        d['adelanto'] = float(monto_adelanto(o['total']))
        d['falta_adelanto'] = float(max(monto_adelanto(o['total']) - a_decimal(o['pagado']), 0))
    d['solo_admin_aprueba'] = es_credito(o.get('condicion_pago'))
    d['intercompany'] = _es_intercompany(o.get('ruc'))
    d['falta_pago_intercompany'] = bool(d['intercompany'] and (o.get('condicion_pago') or '').startswith('Contado')
                                        and d['saldo_pago'] > 0)
    pedida = a_decimal(o['pedida'])
    d['avance_recepcion'] = float(min(a_decimal(o['recibida']) / pedida * 100, 100)) if pedida > 0 else 0
    hoy = date.today()
    fc = o.get('fecha_compromiso')
    d['atrasada'] = bool(fc and fc < hoy and o['estado'] in ESTADOS_ABIERTOS)
    return d


def _listar_ocs(where='', params=()):
    # Solo las órdenes de la empresa elegida arriba ("Todas" = sin filtro)
    sql_emp, par_emp = filtro_sql('oc.empresa_id')
    where = '(' + (where or 'TRUE') + ')' + sql_emp
    filas = db_query(SQL_OC_LISTA + ' WHERE ' + where + ' ORDER BY oc.id DESC LIMIT 500', tuple(params) + par_emp)
    return [_oc_dict(f) for f in filas]


def _obtener_oc(oc_id):
    filas = db_query(SQL_OC_LISTA + ' WHERE oc.id = %s', (oc_id,))
    if not filas:
        raise ErrorCompras('La orden de compra no existe.')
    return filas[0]


# ============================================================
# PÁGINA
# ============================================================
@compras_flujo_bp.route('/compras')
def compras_inicio():
    return render_template('compras/flujo.html',
                           puede_comprar=puede_comprar(), puede_aprobar=puede_aprobar(), puede_pagar=puede_pagar(),
                           puede_recibir=puede_recibir(), puede_facturar=puede_facturar(), es_admin=es_admin(),
                           metodos=METODOS_PAGO, tab=request.args.get('tab') or 'hoy',
                           nueva=request.args.get('nueva') == '1', motivos=MOTIVOS_SIN_PEDIDO)


@compras_flujo_bp.route('/compras/api/flujo/catalogos')
def api_catalogos():
    try:
        empresas = _empresas()
        empresa_sesion = (session.get('empresa') or '').upper()
        defecto = next((e['id'] for e in empresas if (e.get('codigo') or '').upper() == empresa_sesion),
                       empresas[0]['id'] if empresas else None)
        proveedores = proveedores_con_contacto()
        usuarios = db_query("""
            SELECT id, COALESCE(NULLIF(nombres_apellidos, ''), usuario_sistema) AS nombre FROM usuarios
            WHERE COALESCE(LOWER(estado), 'activo') NOT IN ('inactivo', 'inactiva', 'bloqueado') ORDER BY 2
        """)
        registro = db_query("SELECT almacen_id, empresa_id, registrado_sunat, es_domicilio_fiscal FROM inv_sede_empresa")
        return jsonify({'success': True, 'empresas': empresas, 'sedes': _sedes(), 'empresa_defecto': defecto,
                        'proveedores': [_fila(p) for p in proveedores], 'usuarios': [_fila(u) for u in usuarios],
                        'registro_sunat': [_fila(r) for r in registro], 'usuario_id': session.get('usuario_id'),
                        'metodos': list(METODOS_PAGO), 'alerta_precio_pct': float(ALERTA_PRECIO_PCT),
                        'motivos_sin_pedido': list(MOTIVOS_SIN_PEDIDO),
                        # 24/10/2026: monedas de las cuentas de cada empresa (KCF solo soles; AGD soles y dólares)
                        'monedas_cuenta': {str(e['id']): monedas_de_cuentas(e['id']) for e in empresas}})
    except Exception as e:
        return _respuesta_error(e)


# ============================================================
# HOY EN COMPRAS (tablero de tareas y alertas)
# ============================================================
@compras_flujo_bp.route('/compras/api/flujo/resumen')
def api_resumen():
    try:
        ocs = _listar_ocs("oc.flujo = 'v2'")
        hoy = date.today()
        pedidos = _pedidos_por_comprar(solo_por_comprar=True)
        por = lambda c: [o for o in ocs if o['paso']['codigo'] == c]
        alertas = []

        def alerta(nivel, texto, ir=None, cuantos=None):
            alertas.append({'nivel': nivel, 'texto': texto, 'ir': ir, 'cuantos': cuantos})

        if pedidos:
            n = sum(p['por_comprar'] for p in pedidos)
            alerta('info', f'<b>{len(pedidos)} pedido(s) de clientes</b> tienen {n} producto(s) por comprar (sin orden ni stock). '
                           'Antes de comprar, mira la columna "Stock libre en el grupo".', 'pedidos', len(pedidos))
        if por('aprobar'):
            alerta('warn', f'<b>{len(por("aprobar"))} orden(es) esperan aprobación.</b> Sin aprobación no se paga ni se recibe.',
                   'ordenes', len(por('aprobar')))
        if por('pagar'):
            monto = sum(o['saldo_pago'] for o in por('pagar'))
            alerta('warn', f'<b>{len(por("pagar"))} orden(es) al contado por pagar</b> (S/ {monto:,.2f}). '
                           'Finanzas paga solo a la cuenta registrada del proveedor.', 'facturas', len(por('pagar')))
        atrasadas = [o for o in ocs if o['atrasada']]
        if atrasadas:
            alerta('danger', f'<b>{len(atrasadas)} orden(es) atrasadas:</b> pasó la fecha prometida y la mercadería no llega completa: '
                             + ', '.join(o['numero'] for o in atrasadas[:6]) + '. Llama al proveedor.', 'recibir', len(atrasadas))
        pagadas_sin_llegar = [o for o in ocs if o['estado'] in ESTADOS_ABIERTOS and a_decimal(o['pagado']) > 0
                              and o['aprobado_en'] and str(o['aprobado_en'])[:10] <= (hoy - timedelta(days=DIAS_AVISO)).isoformat()]
        if pagadas_sin_llegar:
            alerta('danger', f'<b>{len(pagadas_sin_llegar)} orden(es) pagadas y la mercadería aún no llega completa</b> '
                             f'(más de {DIAS_AVISO} días): ' + ', '.join(o['numero'] for o in pagadas_sin_llegar[:6]) + '.',
                   'recibir', len(pagadas_sin_llegar))
        inc = db_query("SELECT COUNT(*) AS n FROM com_incidencias WHERE estado = 'Abierta'")[0]['n']
        if inc:
            alerta('danger', f'<b>{inc} diferencia(s) abiertas</b> (faltantes, sobrantes, dañados o facturas que no cuadran). '
                             'Una supervisora debe resolverlas.', 'ordenes', inc)
        sin_factura = [o for o in ocs if o['estado'] in ('Recibida', 'Recibida parcial') and not o['facturas']]
        if sin_factura:
            alerta('warn', f'<b>{len(sin_factura)} orden(es) recibidas sin factura del proveedor.</b> Pídela y regístrala.',
                   'facturas', len(sin_factura))
        pagado_sin_factura = [o for o in ocs if a_decimal(o['pagado']) > 0 and not o['facturas'] and o['estado'] != 'Anulada']
        if pagado_sin_factura:
            alerta('warn', f'<b>{len(pagado_sin_factura)} pago(s) sin factura.</b> Se pagó y todavía no hay factura registrada.',
                   'facturas', len(pagado_sin_factura))
        no_ingresadas = db_query("""
            SELECT COUNT(DISTINCT r.com_recepcion_id) AS n FROM recepciones_mercaderia r
            WHERE r.com_recepcion_id IS NOT NULL AND r.fecha < NOW() - INTERVAL '1 day'
              AND NOT EXISTS (SELECT 1 FROM inv_movimientos m WHERE m.recepcion_id = r.id AND m.estado <> 'Rechazado')
        """)[0]['n']
        if no_ingresadas:
            alerta('danger', f'<b>{no_ingresadas} recepción(es) de hace más de un día no están en el Inventario.</b> '
                             'Mercadería que no está en el inventario se puede perder. Ve a Inventario ▸ Entradas y salidas.',
                   None, no_ingresadas)
        propias = [o for o in ocs if o['aprobado_por_id'] and o['aprobado_por_id'] == o['usuario_id']]
        if propias:
            alerta('info', f'{len(propias)} orden(es) fueron aprobadas por la misma persona que las hizo (solo puede hacerlo un administrador): '
                           + ', '.join(o['numero'] for o in propias[:6]) + '.', 'ordenes', len(propias))
        cxp = db_query("""
            SELECT COUNT(*) AS n, COALESCE(SUM(monto), 0) AS m FROM comprobantes_proveedor
            WHERE COALESCE(UPPER(estado), '') NOT IN ('ANULADO', 'ANULADA', 'PAGADO')
              AND fecha_vencimiento BETWEEN CURRENT_DATE AND CURRENT_DATE + 7""" + filtro_sql('empresa_id')[0],
            filtro_sql('empresa_id')[1])[0]
        if cxp['n']:
            alerta('warn', f"<b>{cxp['n']} factura(s) a crédito vencen esta semana</b> (S/ {float(cxp['m']):,.2f}). Ver Finanzas ▸ Cuentas por pagar.",
                   None, cxp['n'])
        stock_mes = sum(float(o['total']) for o in ocs if o['tipo_compra'] == 'Para stock' and o['estado'] != 'Anulada'
                        and str(o['fecha'])[:7] == hoy.isoformat()[:7])
        total_mes = sum(float(o['total']) for o in ocs if o['estado'] != 'Anulada' and str(o['fecha'])[:7] == hoy.isoformat()[:7])
        if stock_mes:
            pct = stock_mes / total_mes * 100 if total_mes else 0
            alerta('warn' if pct > 10 else 'info',
                   f'Este mes se compró <b>S/ {stock_mes:,.2f} para stock</b> ({pct:.0f}% de las compras). La meta es no pasar del 5-10%.',
                   'ordenes', None)
        if not alertas:
            alerta('ok', 'Todo al día. No hay tareas pendientes en Compras. 👍')
        kpis = {
            'pedidos': len(pedidos),
            'por_aprobar': len(por('aprobar')),
            'por_pagar': round(sum(o['saldo_pago'] for o in por('pagar')), 2),
            'por_recibir': len(por('recibir')) + len(por('pagar')),
            'incidencias': inc,
            'compras_mes': round(total_mes, 2),
        }
        return jsonify({'success': True, 'kpis': kpis, 'alertas': alertas})
    except Exception as e:
        return _respuesta_error(e)


# ============================================================
# PEDIDOS DE CLIENTES POR COMPRAR
# ============================================================
@compras_flujo_bp.route('/compras/api/flujo/pedidos')
def api_pedidos():
    try:
        todos = request.args.get('todos') == '1'
        # Por defecto solo lo pendiente de comprar; con "Ver también..." sale todo (para consultar)
        return jsonify({'success': True, 'data': _pedidos_por_comprar(todos=todos, solo_por_comprar=not todos)})
    except Exception as e:
        return _respuesta_error(e)


@compras_flujo_bp.route('/compras/api/flujo/producto/<int:producto_id>')
def api_info_producto(producto_id):
    """Para el formulario de OC: últimas compras (precio y proveedor) y stock libre en el grupo."""
    try:
        compras = db_query("""
            SELECT oc.numero_orden, COALESCE(oc.fecha_creacion, oc.created_at) AS fecha, p.razon_social AS proveedor,
                   oci.cantidad, oci.precio_unitario, COALESCE(NULLIF(e.nombre_corto, ''), e.codigo) AS empresa
            FROM ordenes_compra_items oci JOIN ordenes_compra oc ON oc.id = oci.orden_compra_id
            LEFT JOIN proveedores p ON p.id = oc.proveedor_id LEFT JOIN erp_empresas e ON e.id = oc.empresa_id
            WHERE oci.producto_id = %s AND COALESCE(oc.estado, '') NOT IN ('Anulada', 'Borrador')
            ORDER BY oc.id DESC LIMIT 8
        """, (producto_id,))
        return jsonify({'success': True, 'compras': [_fila(c) for c in compras],
                        'stock_libre': _detalle_stock_libre(producto_id)})
    except Exception as e:
        return _respuesta_error(e)


@compras_flujo_bp.route('/compras/api/flujo/abastecimiento')
def api_abastecimiento():
    """Panel "Resumen de abastecimiento" del formulario de OC (pedido de Erika, 19/10/2026).
    Por producto y para la empresa que compra: stock actual (libre), lo que piden los clientes y aún falta cubrir,
    y lo sugerido a comprar = falta − stock. ?empresa_id=..&productos=1,2,3[&oc_id=..] (oc_id: al corregir una OC
    no se cuenta lo que ya trae esa misma OC)."""
    try:
        ids = sorted({int(x) for x in (request.args.get('productos') or '').split(',') if x.strip().isdigit()})[:200]
        oc_id = request.args.get('oc_id', type=int)
        empresa_id = id_empresa(request.args.get('empresa_id')) if request.args.get('empresa_id') else None
        if not ids:
            return jsonify({'success': True, 'data': []})
        stock_emp = _stock_libre_empresa(ids, empresa_id) if empresa_id is not None else _stock_libre_grupo(ids)
        stock_grupo = _stock_libre_grupo(ids)
        pend = {pid: {'falta': Decimal('0'), 'pedido': Decimal('0'), 'comprado': Decimal('0'), 'por_comprar': Decimal('0'),
                      'pcs': []} for pid in ids}
        for p in _pedidos_por_comprar(excluir_oc=oc_id, sin_filtro=True):
            if empresa_id is not None and p['empresa_id'] is not None and str(p['empresa_id']) != str(empresa_id):
                continue
            for it in p['items']:
                d = pend.get(it['producto_id'])
                if d is None or it['falta'] <= 0:
                    continue
                d['falta'] += a_decimal(it['falta'])
                d['pedido'] += a_decimal(it['cantidad'])
                d['comprado'] += a_decimal(it['comprado'])
                d['por_comprar'] += a_decimal(it['comprar_pedido'])
                # Por pedido (22/10/2026): cuánto pide, cuánto ya está en otras OC, cuánto stock le toca y cuánto comprar
                d['pcs'].append({'pedido_id': p['id'], 'numero': p['numero'], 'cliente': p['cliente'], 'fecha': p['fecha'],
                                 'pide': it['cantidad'], 'en_oc': it['comprado'], 'ocs': it.get('ocs'), 'falta': it['falta'],
                                 'stock_asignado': it['stock_asignado'], 'por_comprar': it['comprar_pedido']})
        prods = {f['id']: f for f in db_query("SELECT id, codigo, descripcion, unidad FROM productos WHERE id = ANY(%s)", (ids,))}
        data = []
        for pid in ids:
            d, st = pend[pid], stock_emp.get(pid, Decimal('0'))
            pr = prods.get(pid) or {}
            data.append({'producto_id': pid, 'codigo': pr.get('codigo'), 'descripcion': pr.get('descripcion'),
                         'unidad': pr.get('unidad'), 'stock': float(st), 'stock_grupo': float(stock_grupo.get(pid, 0)),
                         'pedido_cliente': float(d['falta']), 'pedido_total': float(d['pedido']),
                         'ya_en_ordenes': float(d['comprado']), 'pedidos': d['pcs'][:20],
                         'sugerido': float(max(d['falta'] - st, Decimal('0'))), 'por_comprar': float(d['por_comprar'])})
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return _respuesta_error(e)


@compras_flujo_bp.route('/compras/api/flujo/precios')
def api_precios():
    """Historial de precios por producto y proveedor (para negociar y detectar sobreprecios)."""
    try:
        q = (request.args.get('q') or '').strip()
        filas = db_query("""
            SELECT pr.id AS producto_id, pr.codigo, pr.descripcion, p.razon_social AS proveedor,
                   COUNT(*) AS compras, MIN(oci.precio_unitario) AS minimo, MAX(oci.precio_unitario) AS maximo,
                   (ARRAY_AGG(oci.precio_unitario ORDER BY oc.id DESC))[1] AS ultimo,
                   MAX(COALESCE(oc.fecha_creacion, oc.created_at)) AS ultima_fecha
            FROM ordenes_compra_items oci JOIN ordenes_compra oc ON oc.id = oci.orden_compra_id
            JOIN productos pr ON pr.id = oci.producto_id LEFT JOIN proveedores p ON p.id = oc.proveedor_id
            WHERE COALESCE(oc.estado, '') NOT IN ('Anulada', 'Borrador')
              AND (%s = '' OR pr.codigo ILIKE %s OR pr.descripcion ILIKE %s OR p.razon_social ILIKE %s)
            GROUP BY pr.id, pr.codigo, pr.descripcion, p.razon_social
            ORDER BY pr.descripcion, ultimo LIMIT 300
        """, (q, f'%{q}%', f'%{q}%', f'%{q}%'))
        return jsonify({'success': True, 'data': [_fila(f) for f in filas]})
    except Exception as e:
        return _respuesta_error(e)


# ============================================================
# ÓRDENES DE COMPRA
# ============================================================
@compras_flujo_bp.route('/compras/api/flujo/ordenes')
def api_ordenes():
    try:
        cond, params = [], []
        if id_empresa(request.args.get('empresa_id')) is not None:
            cond.append('oc.empresa_id = %s')
            params.append(id_empresa(request.args['empresa_id']))
        estado = request.args.get('estado') or ''
        if estado == 'abiertas':
            cond.append("COALESCE(oc.estado, '') NOT IN ('Cerrada', 'Anulada')")
        elif estado:
            cond.append('oc.estado = %s')
            params.append(estado)
        if request.args.get('nuevas') != '0':
            cond.append("oc.flujo = 'v2'")
        q = (request.args.get('q') or '').strip()
        if q:
            cond.append("(oc.numero_orden ILIKE %s OR p.razon_social ILIKE %s OR it.clientes ILIKE %s OR it.pedidos ILIKE %s "
                        "OR it.productos ILIKE %s OR oc.pc_numeros ILIKE %s OR oc.clientes_pedido ILIKE %s OR oc.motivo_compra ILIKE %s)")
            params += [f'%{q}%'] * 8
        if request.args.get('sin_pedido') == '1':
            cond.append("COALESCE(it.pedidos, oc.pc_numeros) IS NULL")
        datos = _listar_ocs(' AND '.join(cond), tuple(params))
        paso = request.args.get('paso')
        if paso:
            datos = [d for d in datos if d['paso']['codigo'] in paso.split(',')]
        return jsonify({'success': True, 'data': datos})
    except Exception as e:
        return _respuesta_error(e)


@compras_flujo_bp.route('/compras/api/flujo/ordenes/<int:oc_id>')
def api_orden_detalle(oc_id):
    try:
        o = _oc_dict(_obtener_oc(oc_id))
        items = db_query("""
            SELECT oci.id, oci.producto_id, oci.producto, oci.unidad, oci.cantidad, oci.precio_unitario, oci.total,
                   oci.pedido_id, oci.pedido_numero, oci.cliente, COALESCE(oci.cantidad_recibida, 0) AS cantidad_recibida,
                   oci.cotizacion_numero, pr.codigo
            FROM ordenes_compra_items oci LEFT JOIN productos pr ON pr.id = oci.producto_id
            WHERE oci.orden_compra_id = %s ORDER BY oci.id
        """, (oc_id,))
        o['items'] = [_fila(i) for i in items]
        o['historial'] = [_fila(h) for h in db_query(
            "SELECT fecha, usuario, accion, detalle FROM com_historial WHERE orden_compra_id = %s ORDER BY id", (oc_id,))]
        o['recepciones'] = [_fila(r) for r in db_query("""
            SELECT r.numero, r.fecha, r.guia_proveedor, r.traido_por, r.recibido_por, r.con_diferencias, a.nombre AS sede,
                   r.observaciones
            FROM com_recepciones r LEFT JOIN almacenes a ON a.id = r.almacen_id WHERE r.orden_compra_id = %s ORDER BY r.id
        """, (oc_id,))]
        o['pagos'] = [_fila(p) for p in db_query("""
            SELECT fecha, monto, metodo, banco, numero_operacion, usuario_nombre, documento_numero,
                   moneda_pago, tipo_cambio, monto_pagado FROM finanzas_pagos
            WHERE tipo = 'PAGO' AND estado <> 'Anulado' AND ((documento_tabla = 'ordenes_compra' AND documento_id = %s)
               OR (documento_tabla = 'comprobantes_proveedor' AND documento_id IN
                   (SELECT id FROM comprobantes_proveedor WHERE orden_compra_id = %s)))
            ORDER BY fecha, id
        """, (oc_id, oc_id))]
        o['facturas'] = [_fila(f) for f in db_query("""
            SELECT id, tipo, numero, fecha, monto, monto_esperado, cuadra, estado, fecha_vencimiento,
                   COALESCE(moneda, 'PEN') AS moneda, tipo_cambio
            FROM comprobantes_proveedor WHERE orden_compra_id = %s ORDER BY id
        """, (oc_id,))]
        o['incidencias'] = [_fila(i) for i in db_query("""
            SELECT i.id, i.numero, i.fecha, i.tipo, i.cantidad, i.monto, i.detalle, i.estado, i.resolucion,
                   i.resuelto_por, i.reportado_por, pr.descripcion AS producto
            FROM com_incidencias i LEFT JOIN productos pr ON pr.id = i.producto_id
            WHERE i.orden_compra_id = %s ORDER BY i.id
        """, (oc_id,))]
        prov = db_query("SELECT banco, numero_cuenta, cci, direccion, lugar_recojo, contacto, telefono FROM proveedores WHERE id = %s",
                        (o['proveedor_id'],)) if o.get('proveedor_id') else []
        o['proveedor_datos'] = _fila(prov[0]) if prov else {}
        avisos = []
        if o.get('flujo') == 'v2' and o['estado'] in ('Por aprobar', 'Borrador'):
            with db_tx() as conn:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                avisos += _alertas_precio(cur, oc_id, [dict(i, descripcion=i['producto']) for i in items if i['producto_id']])
        if o.get('empresa_id') and o.get('almacen_entrega_id') and _sede_declarada(o['empresa_id'], o['almacen_entrega_id']) is False:
            avisos.append(f"La sede {o['sede']} no está declarada en SUNAT para {o['empresa']}. La guía del proveedor debe llegar a un "
                          "establecimiento de la empresa que compra. Revisa Inventario ▸ Sedes y SUNAT.")
        o['avisos'] = avisos
        uid = session.get('usuario_id')
        o['soy_creador'] = bool(uid and uid == o['usuario_id'])
        return jsonify({'success': True, 'data': o})
    except Exception as e:
        return _respuesta_error(e)


def _validar_items(cur, items_in, oc_id=None):
    if not items_in:
        raise ErrorCompras('Agrega al menos un producto.')
    comprado = _comprado_por_pedido(cur, excluir_oc=oc_id)
    pedidos_cache = {}
    items, suma_pedido = [], {}
    for it in items_in:
        producto_id = _entero(it.get('producto_id'), 'el producto de la lista (no se puede escribir a mano)')
        cur.execute("SELECT id, codigo, descripcion, unidad FROM productos WHERE id = %s", (producto_id,))
        prod = cur.fetchone()
        if not prod:
            raise ErrorCompras('Uno de los productos no existe.')
        cantidad = a_decimal(it.get('cantidad'))
        precio = a_decimal(it.get('precio_unitario', it.get('precio')))
        nombre = prod['descripcion']
        if cantidad <= 0:
            raise ErrorCompras(f'La cantidad de "{nombre}" debe ser mayor que 0.')
        if precio <= 0:
            raise ErrorCompras(f'Escribe el precio sin IGV de "{nombre}".')
        pedido_id = it.get('pedido_id') or None
        pedido_num = cliente = cotizacion = None
        if pedido_id:
            pedido_id = int(pedido_id)
            if pedido_id not in pedidos_cache:
                cur.execute("SELECT id, numero, cliente, estado, items_json, cotizacion_numero FROM pedido_compra_pc WHERE id = %s", (pedido_id,))
                pc = cur.fetchone()
                if not pc:
                    raise ErrorCompras('El pedido del cliente no existe.')
                if (pc['estado'] or '').upper() in ESTADOS_PC_FUERA:
                    raise ErrorCompras(f"El pedido {pc['numero']} está {pc['estado']}: no se puede comprar para él.")
                pedidos_cache[pedido_id] = (pc, _resolver_productos(_items_pedido(pc)))
            pc, pc_items = pedidos_cache[pedido_id]
            pedido_num, cliente, cotizacion = pc['numero'], pc['cliente'], pc['cotizacion_numero']
            necesita = sum((i['cantidad'] for i in pc_items if i['producto_id'] == producto_id), Decimal('0'))
            if necesita <= 0:
                raise ErrorCompras(f'"{nombre}" no está en el pedido {pedido_num}.')
            clave = (pedido_id, producto_id)
            suma_pedido[clave] = suma_pedido.get(clave, Decimal('0')) + cantidad
            falta = necesita - comprado.get(clave, Decimal('0'))
            if suma_pedido[clave] > falta:
                raise ErrorCompras(f'El pedido {pedido_num} solo necesita {_cant(max(falta, 0))} de "{nombre}" '
                                   f'(pidió {_cant(necesita)} y ya hay {_cant(necesita - falta)} en otras órdenes). '
                                   'Si quieres comprar más para stock, agrega otra línea sin pedido.')
        items.append({'producto_id': producto_id, 'producto': nombre, 'codigo': prod['codigo'],
                      'unidad': prod['unidad'] or 'UND', 'cantidad': cantidad, 'precio_unitario': precio,
                      'total': redondear(cantidad * precio), 'pedido_id': pedido_id, 'pedido_numero': pedido_num,
                      'cliente': cliente, 'cotizacion': cotizacion})
    return items


# Estados en que una OC sigue "activa" (no anulada ni terminada)
ESTADOS_OC_ACTIVA = ('Borrador', 'Por aprobar', 'Aprobada', 'Recibida parcial')


def _oc_duplicada(cur, proveedor_id, items, oc_id):
    """Pedido de Erika 20/10/2026 22:54: no se repite una OC. Bloquea si ya hay una OC activa del mismo
    proveedor para el mismo PC, o con los mismos productos y cantidades. A otro proveedor sí se puede."""
    cur.execute("SELECT id FROM proveedores WHERE id = %s FOR UPDATE", (proveedor_id,))  # dos personas a la vez: una espera
    pedidos = sorted({i['pedido_id'] for i in items if i['pedido_id']})
    if pedidos:
        cur.execute("""SELECT oc.numero_orden, string_agg(DISTINCT it.pedido_numero, ', ') AS pcs
                       FROM ordenes_compra oc JOIN ordenes_compra_items it ON it.orden_compra_id = oc.id
                       WHERE oc.proveedor_id = %s AND oc.flujo = 'v2' AND oc.estado = ANY(%s) AND oc.id <> %s
                         AND it.pedido_id = ANY(%s)
                       GROUP BY oc.id, oc.numero_orden ORDER BY oc.id LIMIT 1""",
                    (proveedor_id, list(ESTADOS_OC_ACTIVA), oc_id or 0, pedidos))
        f = cur.fetchone()
        if f:
            raise ErrorCompras(f"⛔ ERROR: Ya existe una Orden de Compra activa para este pedido ({f['numero_orden']}, "
                               f"PC {f['pcs']}) con este mismo proveedor. No se puede duplicar. "
                               "Si falta algo, corrige esa orden; si está mal, anúlala primero.")
    firma = sorted((i['producto_id'], str(a_decimal(i['cantidad']).normalize())) for i in items)
    cur.execute("""SELECT oc.id, oc.numero_orden, array_agg(it.producto_id) AS prods, array_agg(it.cantidad) AS cants
                   FROM ordenes_compra oc JOIN ordenes_compra_items it ON it.orden_compra_id = oc.id
                   WHERE oc.proveedor_id = %s AND oc.flujo = 'v2' AND oc.estado = ANY(%s) AND oc.id <> %s
                   GROUP BY oc.id, oc.numero_orden""", (proveedor_id, list(ESTADOS_OC_ACTIVA), oc_id or 0))
    for f in cur.fetchall():
        otra = sorted((p, str(a_decimal(c).normalize())) for p, c in zip(f['prods'], f['cants']))
        if otra == firma:
            raise ErrorCompras(f"⛔ ERROR: Ya existe una Orden de Compra activa idéntica ({f['numero_orden']}): mismo proveedor, "
                               "mismos productos y mismas cantidades. No se puede duplicar.")


@compras_flujo_bp.route('/compras/api/flujo/ordenes', methods=['POST'])
def api_orden_guardar():
    """Crea o corrige una OC en Borrador. Con enviar=true la manda a aprobación."""
    if not puede_comprar():
        return _no_autorizado('Tu usuario no puede preparar órdenes de compra.')
    d = request.get_json(silent=True) or {}
    try:
        empresa_id = _empresa(d.get('empresa_id'))
        proveedor_id = _entero(d.get('proveedor_id'), 'el proveedor de la lista')
        almacen_id = _entero(d.get('almacen_entrega_id'), 'la sede donde debe terminar la mercadería')
        condicion = d.get('condicion_pago') or ''
        if condicion not in CONDICIONES:
            raise ErrorCompras('Elige la condición de pago: Contado, Contra entrega, Crédito o Adelanto 50%.')
        dias = int(a_decimal(d.get('dias_credito') or 0))
        if condicion == 'Crédito' and dias <= 0:
            raise ErrorCompras('Escribe los días de crédito que da el proveedor.')
        if condicion == 'Crédito' and dias > 360:
            # Pedido de Erika 21/10/2026: una OC con "Crédito 40000 días" hizo vencer una factura en el año 2136
            raise ErrorCompras(f'{dias} días de crédito no es posible: escribe entre 1 y 360 días.')
        if condicion != 'Crédito':
            dias = 0
        modalidad = d.get('modalidad_entrega') or ''
        if modalidad not in MODALIDADES:
            raise ErrorCompras('Indica si el proveedor entrega o si nosotros recogemos.')
        direccion_recojo = (d.get('direccion_recojo') or '').strip()
        if modalidad == 'Nosotros recogemos' and not direccion_recojo:
            raise ErrorCompras('Escribe la dirección donde se recoge.')
        fecha_compromiso = d.get('fecha_compromiso') or None
        if not fecha_compromiso:
            raise ErrorCompras('Escribe la fecha en que el proveedor entrega o tiene lista la mercadería.')
        enviar = bool(d.get('enviar'))
        oc_id = d.get('id') or None
        # Moneda de la OC (24/10/2026): los precios se escriben en la moneda que vende el proveedor
        moneda, tc = moneda_y_tc(d)
        sim = simbolo(moneda)
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT id FROM erp_empresas WHERE id = %s", (empresa_id,))
            if not cur.fetchone():
                raise ErrorCompras('La empresa no existe.')
            cur.execute("SELECT id FROM almacenes WHERE id = %s AND COALESCE(activo, true) = true", (almacen_id,))
            if not cur.fetchone():
                raise ErrorCompras('La sede no existe o está inactiva.')
            cur.execute("SELECT id, razon_social, ruc, contacto, telefono, email FROM proveedores WHERE id = %s", (proveedor_id,))
            prov = cur.fetchone()
            if not prov:
                raise ErrorCompras('El proveedor no existe. Regístralo en Maestros ▸ Proveedores.')
            if oc_id:
                cur.execute("SELECT estado, flujo, usuario_id FROM ordenes_compra WHERE id = %s FOR UPDATE", (oc_id,))
                actual = cur.fetchone()
                if not actual or actual['flujo'] != 'v2':
                    raise ErrorCompras('La orden no existe.')
                if actual['estado'] != 'Borrador':
                    raise ErrorCompras(f'La orden está "{actual["estado"]}" y ya no se puede cambiar. Si hay un error, anúlala y haz otra.')
            items = _validar_items(cur, d.get('items'), oc_id)
            _oc_duplicada(cur, proveedor_id, items, oc_id)
            sin_pedido = [i for i in items if not i['pedido_id']]
            tipo = 'Para stock' if sin_pedido else 'Bajo pedido'
            motivo_compra = None
            motivo_stock = ''
            if sin_pedido:
                # Comprar sin pedido (para stock) es una decisión explícita: motivo obligatorio de la lista
                motivo_compra, motivo_stock = motivo_sin_pedido(d)
            totales = calcular_totales([{'cantidad': i['cantidad'], 'precio': i['precio_unitario']} for i in items])
            _, unom = _usuario()
            uid = session.get('usuario_id')
            condicion_txt = f'Crédito {dias} días' if condicion == 'Crédito' else condicion
            valores = (empresa_id, proveedor_id, almacen_id, modalidad, direccion_recojo or None, tipo,
                       motivo_stock or None, fecha_compromiso, dias, condicion_txt, totales['subtotal'], totales['igv'],
                       totales['total'], (d.get('num_cotizacion') or '').strip() or None, (d.get('notas') or '').strip() or None,
                       prov['contacto'] or prov['razon_social'], prov['telefono'], prov['email'])
            if oc_id:
                cur.execute("""
                    UPDATE ordenes_compra SET empresa_id=%s, proveedor_id=%s, almacen_entrega_id=%s, modalidad_entrega=%s,
                        direccion_recojo=%s, tipo_compra=%s, motivo_stock=%s, fecha_compromiso=%s, dias_credito=%s,
                        condicion_pago=%s, subtotal=%s, igv=%s, total=%s, num_cotizacion=%s, notas=%s,
                        contacto_proveedor=%s, telefono_proveedor=%s, email_proveedor=%s, updated_at=NOW()
                    WHERE id=%s RETURNING id, numero_orden
                """, valores + (oc_id,))
                oc = cur.fetchone()
                cur.execute("DELETE FROM ordenes_compra_items WHERE orden_compra_id = %s", (oc_id,))
                _historial(cur, oc_id, 'Corregida', f"Total {sim} {totales['total']}")
            else:
                prefijo = f"OC-{datetime.now().strftime('%Y%m%d')}-"
                bloquear_numeracion(cur, 'ordenes_compra:' + prefijo)
                cur.execute("""SELECT COALESCE(MAX(NULLIF(regexp_replace(SUBSTRING(numero_orden FROM %s), '\\D', '', 'g'), '')::int), 0) + 1 AS sig
                               FROM ordenes_compra WHERE numero_orden LIKE %s""", (len(prefijo) + 1, prefijo + '%'))
                numero = prefijo + str(cur.fetchone()['sig']).zfill(4)
                cur.execute("""
                    INSERT INTO ordenes_compra (empresa_id, proveedor_id, almacen_entrega_id, modalidad_entrega,
                        direccion_recojo, tipo_compra, motivo_stock, fecha_compromiso, dias_credito, condicion_pago,
                        subtotal, igv, total, num_cotizacion, notas, contacto_proveedor, telefono_proveedor, email_proveedor,
                        numero_orden, codigo_orden, correlativo, usuario_id, creado_por_nombre, estado, flujo,
                        descuento_porcentaje, descuento_monto, descuento_tipo, fecha_creacion, lugar_entrega, tiempo_entrega)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'Borrador','v2',0,0,'porcentaje',NOW(),
                            (SELECT nombre FROM almacenes WHERE id = %s), %s)
                    RETURNING id, numero_orden
                """, valores + (numero, numero, int(numero[-4:]), uid, unom, almacen_id, str(fecha_compromiso)))
                oc = cur.fetchone()
                oc_id = oc['id']
                _historial(cur, oc_id, 'Creada', f"{tipo} · Total {sim} {totales['total']}"
                                                 + (f" (TC {tc})" if moneda == 'USD' else ''))
            cur.execute("UPDATE ordenes_compra SET moneda = %s, tipo_cambio = %s WHERE id = %s", (moneda, tc, oc_id))
            for i in items:
                cur.execute("""
                    INSERT INTO ordenes_compra_items (orden_compra_id, producto_id, producto, unidad, cantidad, precio_unitario,
                        total, pedido_id, pedido_numero, cliente, cantidad_recibida, cotizacion_numero)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0,%s)
                """, (oc_id, i['producto_id'], i['producto'], i['unidad'], i['cantidad'], i['precio_unitario'], i['total'],
                      i['pedido_id'], i['pedido_numero'], i['cliente'], i.get('cotizacion')))
            # Vista interna: a qué PC, cotización y cliente corresponde la OC, y el motivo si es sin pedido
            unir = lambda k: ', '.join(sorted({str(i[k]) for i in items if i.get(k)})) or None
            cur.execute("""UPDATE ordenes_compra SET motivo_compra = %s, pedido_id = %s, pc_numeros = %s,
                               cotizaciones_cliente = %s, clientes_pedido = %s WHERE id = %s""",
                        (motivo_compra, next((i['pedido_id'] for i in items if i['pedido_id']), None), unir('pedido_numero'),
                         unir('cotizacion'), unir('cliente'), oc_id))
            alertas = _alertas_precio(cur, oc_id, items)
            mensaje = f"Orden {oc['numero_orden']} guardada como borrador."
            if enviar:
                mensaje = _enviar(cur, oc_id, en_soles(totales['total'], moneda, tc), tipo, alertas)
        return jsonify({'success': True, 'id': oc_id, 'numero': oc['numero_orden'], 'message': mensaje, 'alertas': alertas})
    except Exception as e:
        return _respuesta_error(e)


def _enviar(cur, oc_id, total, tipo, alertas):
    if MONTO_SIN_APROBACION > 0 and a_decimal(total) <= MONTO_SIN_APROBACION and tipo == 'Bajo pedido' and not alertas:
        cur.execute("""UPDATE ordenes_compra SET estado = 'Aprobada', aprobado_por = 'Automática', aprobado_en = NOW(),
                       updated_at = NOW() WHERE id = %s RETURNING numero_orden""", (oc_id,))
        num = cur.fetchone()['numero_orden']
        _historial(cur, oc_id, 'Aprobada automáticamente', f'Monto menor a S/ {MONTO_SIN_APROBACION}')
        return f'Orden {num} aprobada automáticamente (monto pequeño).'
    cur.execute("UPDATE ordenes_compra SET estado = 'Por aprobar', updated_at = NOW() WHERE id = %s RETURNING numero_orden", (oc_id,))
    num = cur.fetchone()['numero_orden']
    _historial(cur, oc_id, 'Enviada a aprobar', ' | '.join(alertas) if alertas else None)
    return f'Orden {num} enviada a aprobar.' + (' Ojo: tiene alertas de precio.' if alertas else '')


@compras_flujo_bp.route('/compras/api/flujo/ordenes/<int:oc_id>/enviar', methods=['POST'])
def api_orden_enviar(oc_id):
    if not puede_comprar():
        return _no_autorizado('Tu usuario no puede enviar órdenes de compra.')
    try:
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT estado, flujo, total, tipo_compra, moneda, tipo_cambio FROM ordenes_compra WHERE id = %s FOR UPDATE", (oc_id,))
            oc = cur.fetchone()
            if not oc or oc['flujo'] != 'v2':
                raise ErrorCompras('La orden no existe.')
            if oc['estado'] != 'Borrador':
                raise ErrorCompras('Solo se envían órdenes en Borrador.')
            cur.execute("SELECT producto_id, producto AS descripcion, precio_unitario FROM ordenes_compra_items WHERE orden_compra_id = %s", (oc_id,))
            alertas = _alertas_precio(cur, oc_id, cur.fetchall())
            msg = _enviar(cur, oc_id, en_soles(oc['total'], oc['moneda'], oc['tipo_cambio']), oc['tipo_compra'], alertas)
        return jsonify({'success': True, 'message': msg})
    except Exception as e:
        return _respuesta_error(e)


@compras_flujo_bp.route('/compras/api/flujo/ordenes/<int:oc_id>/aprobar', methods=['POST'])
def api_orden_aprobar(oc_id):
    if not puede_aprobar():
        return _no_autorizado('Solo una supervisora puede aprobar órdenes de compra.')
    d = request.get_json(silent=True) or {}
    try:
        aprobar = bool(d.get('aprobar'))
        motivo = (d.get('motivo') or '').strip()
        uid, unom = _usuario()
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT numero_orden, estado, flujo, usuario_id, condicion_pago FROM ordenes_compra WHERE id = %s FOR UPDATE", (oc_id,))
            oc = cur.fetchone()
            if not oc or oc['flujo'] != 'v2':
                raise ErrorCompras('La orden no existe.')
            if oc['estado'] != 'Por aprobar':
                raise ErrorCompras(f'La orden está "{oc["estado"]}": no está esperando aprobación.')
            if aprobar:
                # Erika 25/10/2026: Hellen sí aprueba sus propias OC; las de crédito solo las aprueba la administradora
                if es_credito(oc['condicion_pago']) and not es_admin():
                    raise PermissionError('Esta orden es a crédito: solo Erika (administradora) puede aprobarla. Sin su aprobación no tiene validez.')
                cur.execute("""UPDATE ordenes_compra SET estado = 'Aprobada', aprobado_por_id = %s, aprobado_por = %s,
                               aprobado_en = NOW(), updated_at = NOW() WHERE id = %s""", (uid, unom, oc_id))
                _historial(cur, oc_id, 'Aprobada', motivo or None)
                msg = f"Orden {oc['numero_orden']} aprobada. Ya se puede enviar al proveedor."
            else:
                if len(motivo) < 5:
                    raise ErrorCompras('Escribe por qué se devuelve la orden, para que la corrijan.')
                cur.execute("UPDATE ordenes_compra SET estado = 'Borrador', updated_at = NOW() WHERE id = %s", (oc_id,))
                _historial(cur, oc_id, 'Devuelta para corregir', motivo)
                msg = f"Orden {oc['numero_orden']} devuelta a Borrador con tu comentario."
        return jsonify({'success': True, 'message': msg})
    except Exception as e:
        return _respuesta_error(e)


@compras_flujo_bp.route('/compras/api/flujo/ordenes/<int:oc_id>/anular', methods=['POST'])
def api_orden_anular(oc_id):
    d = request.get_json(silent=True) or {}
    try:
        motivo = (d.get('motivo') or '').strip()
        if len(motivo) < 5:
            raise ErrorCompras('Escribe el motivo de la anulación.')
        uid, unom = _usuario()
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT numero_orden, estado, flujo, usuario_id FROM ordenes_compra WHERE id = %s FOR UPDATE", (oc_id,))
            oc = cur.fetchone()
            if not oc or oc['flujo'] != 'v2':
                raise ErrorCompras('La orden no existe.')
            if oc['estado'] in ('Anulada', 'Cerrada'):
                raise ErrorCompras(f'La orden ya está {oc["estado"]}.')
            # Candado (Erika: "no quiero que los chicos hagan y deshagan"): solo administración/supervisión anula
            if not puede_aprobar():
                raise PermissionError('Solo un administrador (o la supervisora) puede anular órdenes de compra.')
            cur.execute("SELECT 1 FROM com_recepciones WHERE orden_compra_id = %s LIMIT 1", (oc_id,))
            if cur.fetchone():
                raise ErrorCompras('Ya llegó mercadería de esta orden: no se puede anular. Registra la devolución al proveedor y resuelve las diferencias.')
            if _pagado_oc(oc_id) > 0:
                raise ErrorCompras('Esta orden tiene pagos. Primero Finanzas debe anular el pago o registrar la devolución del dinero.')
            cur.execute("""UPDATE ordenes_compra SET estado = 'Anulada', anulado_por = %s, anulado_en = NOW(),
                           motivo_anulacion = %s, updated_at = NOW() WHERE id = %s""", (unom, motivo, oc_id))
            _historial(cur, oc_id, 'Anulada', motivo)
            registrar_anulacion(cur, 'ordenes_compra', oc_id, oc['numero_orden'], 'Anulada', motivo)
        return jsonify({'success': True, 'message': f"Orden {oc['numero_orden']} anulada. Los pedidos de sus clientes vuelven a 'por comprar'."})
    except Exception as e:
        return _respuesta_error(e)


# ============================================================
# PAGO AL PROVEEDOR (antes de recoger, cuando es al contado)
# ============================================================
@compras_flujo_bp.route('/compras/api/flujo/ordenes/<int:oc_id>/pago', methods=['POST'])
def api_orden_pago(oc_id):
    if not puede_pagar():
        return _no_autorizado('Solo Finanzas o una supervisora registra pagos.')
    d = request.get_json(silent=True) or {}
    try:
        if a_decimal(d.get('monto_pagado') if d.get('monto_pagado') not in (None, '') else d.get('monto')) <= 0:
            raise ErrorCompras('El monto debe ser mayor que 0.')
        metodo = d.get('metodo') or 'Transferencia'
        if metodo not in METODOS_PAGO:
            raise ErrorCompras('Elige el método de pago.')
        operacion = (d.get('numero_operacion') or '').strip()
        if metodo in ('Transferencia', 'Depósito', 'Yape/Plin') and not operacion:
            raise ErrorCompras('Escribe el N° de operación del banco. Sin él no se puede comprobar el pago.')
        if metodo == 'Efectivo' and not (d.get('observaciones') or '').strip():
            raise ErrorCompras('Pago en efectivo: escribe en Observaciones quién entregó el dinero y quién firmó el recibo.')
        try:
            fecha = datetime.strptime((d.get('fecha') or date.today().isoformat())[:10], '%Y-%m-%d').date()
        except ValueError:
            raise ErrorCompras('Fecha inválida.')
        if fecha > date.today():
            raise ErrorCompras('La fecha del pago no puede ser futura.')
        uid, unom = _usuario()
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""SELECT oc.numero_orden, oc.estado, oc.flujo, oc.usuario_id, oc.total, p.razon_social, p.ruc,
                                  COALESCE(oc.moneda, 'PEN') AS moneda, oc.empresa_id
                           FROM ordenes_compra oc LEFT JOIN proveedores p ON p.id = oc.proveedor_id
                           WHERE oc.id = %s FOR UPDATE OF oc""", (oc_id,))
            oc = cur.fetchone()
            # OC en dólares pagada en soles con el TC que da el proveedor (24/10/2026): la deuda baja en dólares
            if oc:
                monto, moneda_pago, tc_pago, monto_pagado = pago_en_moneda(oc['moneda'], d, oc['empresa_id'])
                if monto <= 0:
                    raise ErrorCompras('El monto debe ser mayor que 0.')
            sim = simbolo(oc['moneda'] if oc else 'PEN')
            if not oc or oc['flujo'] != 'v2':
                raise ErrorCompras('La orden no existe.')
            if oc['estado'] in ('Borrador', 'Por aprobar', 'Anulada'):
                raise ErrorCompras(f'La orden está "{oc["estado"]}". Solo se pagan órdenes aprobadas.')
            if oc['usuario_id'] and oc['usuario_id'] == uid and not es_admin():
                raise PermissionError('Quien hizo la orden no puede registrar su pago. Lo hace Finanzas.')
            saldo = redondear(a_decimal(oc['total']) - _pagado_oc(oc_id))
            if moneda_pago != oc['moneda'] and Decimal('0') < monto - saldo <= Decimal('0.02'):
                monto = saldo     # redondeo del tipo de cambio: paga el saldo exacto
            if monto > saldo:
                raise ErrorCompras(f'El monto ({sim} {monto}) supera lo que falta pagar de la orden ({sim} {max(saldo, 0)}).')
            cur.execute("""
                INSERT INTO finanzas_pagos (tipo, documento_tabla, documento_id, documento_numero, tercero_nombre,
                    tercero_documento, fecha, monto, metodo, banco, numero_operacion, observaciones, usuario_id, usuario_nombre)
                VALUES ('PAGO', 'ordenes_compra', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (oc_id, oc['numero_orden'], oc['razon_social'], oc['ruc'], fecha, monto, metodo,
                  normalizar_banco(d.get('banco')), operacion or None, (d.get('observaciones') or '').strip() or None,
                  uid, unom))
            # El pago queda en la empresa de la orden de compra
            cur.execute("""UPDATE finanzas_pagos SET empresa_id = (SELECT empresa_id FROM ordenes_compra WHERE id = %s),
                                  moneda_pago = %s, tipo_cambio = %s, monto_pagado = %s WHERE id = %s""",
                        (oc_id, moneda_pago, tc_pago, monto_pagado, cur.fetchone()['id']))
            pagado_txt = f'{sim} {monto}' + (f' (pagado {simbolo(moneda_pago)} {monto_pagado} con TC {tc_pago})' if tc_pago else '')
            _historial(cur, oc_id, 'Pago registrado', f'{pagado_txt} · {metodo} · Op. {operacion or "-"}')
        resto = saldo - monto
        return jsonify({'success': True, 'message': f'Pago registrado: {pagado_txt}. ' + (
            f'Falta pagar {sim} {resto}.' if resto > 0 else 'La orden quedó pagada: ya se puede recoger o recibir.')})
    except Exception as e:
        return _respuesta_error(e)


# ============================================================
# RECEPCIÓN A CIEGAS EN LA SEDE
# ============================================================
@compras_flujo_bp.route('/compras/api/flujo/por_recibir')
def api_por_recibir():
    """Órdenes listas para recibir. NO muestra cantidades: quien recibe debe contar."""
    try:
        datos = _listar_ocs("oc.flujo = 'v2' AND oc.estado IN ('Aprobada', 'Recibida parcial', 'Por aprobar')")
        res = []
        for o in datos:
            res.append({k: o[k] for k in ('id', 'numero', 'empresa', 'empresa_id', 'sede', 'almacen_entrega_id', 'proveedor',
                                          'modalidad_entrega', 'direccion_recojo', 'fecha_compromiso', 'estado',
                                          'atrasada', 'paso', 'clientes', 'lineas', 'usuario_id',
                                          'responsable_recojo_id', 'responsable_recojo', 'responsable_recojo_por',
                                          'responsable_recojo_en', 'falta_pago_intercompany')})
        return jsonify({'success': True, 'data': res})
    except Exception as e:
        return _respuesta_error(e)


# ============================================================
# RECOJOS: RESPONSABLE Y PROGRAMA DE TRANSPORTE (pedido de Erika 22/10/2026)
# "si hay que recoger y nadie lo recoge, porque a veces se olvida": cada OC que recogemos tiene un responsable
# (Luis, Sebastián...) y la lista se descarga como programa para el personal de logística.
# ============================================================
@compras_flujo_bp.route('/compras/api/flujo/ordenes/<int:oc_id>/responsable_recojo', methods=['POST'])
def api_responsable_recojo(oc_id):
    d = request.get_json(silent=True) or {}
    try:
        if not (puede_comprar() or puede_recibir()):
            return _no_autorizado('Solo Compras, Almacén o la supervisora asignan quién recoge.')
        uid, unom = _usuario()
        resp_id = d.get('usuario_id') or None
        nombre = None
        if resp_id:
            u = db_query("SELECT COALESCE(NULLIF(nombres_apellidos, ''), usuario_sistema) AS nombre FROM usuarios WHERE id = %s",
                         (resp_id,))
            if not u:
                raise ErrorCompras('Esa persona no existe.')
            nombre = u[0]['nombre']
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT estado, flujo, modalidad_entrega FROM ordenes_compra WHERE id = %s FOR UPDATE", (oc_id,))
            oc = cur.fetchone()
            if not oc or oc['flujo'] != 'v2':
                raise ErrorCompras('La orden no existe.')
            if oc['modalidad_entrega'] != 'Nosotros recogemos':
                raise ErrorCompras('Esta orden la entrega el proveedor: no hay que recogerla.')
            if oc['estado'] in ('Anulada', 'Cerrada', 'Recibida'):
                raise ErrorCompras(f'La orden ya está {oc["estado"]}.')
            cur.execute("""UPDATE ordenes_compra SET responsable_recojo_id = %s, responsable_recojo = %s,
                           responsable_recojo_por = %s, responsable_recojo_en = NOW(), updated_at = NOW() WHERE id = %s""",
                        (resp_id, nombre, unom, oc_id))
        return jsonify({'success': True, 'responsable': nombre,
                        'mensaje': f'Recoge: {nombre}.' if nombre else 'Quedó sin responsable.'})
    except PermissionError as e:
        return _no_autorizado(str(e))
    except Exception as e:
        return _respuesta_error(e)


def _recojos_pendientes():
    """OC aprobadas que nosotros recogemos y aún no llegan completas, con lo que falta recoger."""
    ocs = _listar_ocs("oc.flujo = 'v2' AND oc.modalidad_entrega = 'Nosotros recogemos' AND oc.estado IN ('Aprobada', 'Recibida parcial')")
    if not ocs:
        return []
    ids = [o['id'] for o in ocs]
    items = db_query("""SELECT orden_compra_id, producto, unidad,
                                 cantidad - COALESCE(cantidad_recibida, 0) AS falta
                          FROM ordenes_compra_items WHERE orden_compra_id = ANY(%s)
                            AND cantidad - COALESCE(cantidad_recibida, 0) > 0 ORDER BY id""", (ids,))
    provs = {p['id']: p for p in db_query(
        "SELECT id, telefono, contacto FROM proveedores WHERE id = ANY(%s)",
        ([o['proveedor_id'] for o in ocs if o.get('proveedor_id')] or [0],))}
    res = []
    for o in ocs:
        prods = [{'producto': i['producto'], 'unidad': i['unidad'] or 'UND', 'cantidad': float(i['falta'])}
                 for i in items if i['orden_compra_id'] == o['id']]
        if not prods:
            continue
        p = provs.get(o.get('proveedor_id')) or {}
        res.append({**o, 'productos_recoger': prods, 'telefono': p.get('telefono') or '', 'contacto': p.get('contacto') or '',
                    'listo': o['paso']['codigo'] != 'pagar'})
    res.sort(key=lambda o: (o.get('fecha_compromiso') or '9999', o['numero'] or ''))
    return res


@compras_flujo_bp.route('/compras/flujo/programa_transporte')
def programa_transporte():
    try:
        datos = _recojos_pendientes()
        if request.args.get('formato') == 'csv':
            buf = io.StringIO()
            w = csv.writer(buf, delimiter=';')
            w.writerow(['Fecha prometida', 'Responsable de recoger', 'Proveedor', 'RUC', 'Contacto', 'Teléfono', 'N° orden de compra',
                        'Empresa', 'Dirección de recojo', 'Nombre producto', 'Unidad de medida', 'Cantidad a recoger',
                        'Llevar a', 'Estado'])
            for o in datos:
                for i in o['productos_recoger']:
                    fp = o['fecha_compromiso']
                    w.writerow([f'{fp[8:10]}/{fp[5:7]}/{fp[0:4]}' if fp else '', o['responsable_recojo'] or 'SIN ASIGNAR', o['proveedor'], o['ruc'] or '',
                                o['contacto'], o['telefono'], o['numero'], o['empresa'] or '', o['direccion_recojo'] or '',
                                i['producto'], i['unidad'], f"{i['cantidad']:g}", o['sede'] or '',
                                'Listo para recoger' if o['listo'] else 'Falta el pago (no recoger)'])
            return Response('\ufeff' + buf.getvalue(), mimetype='text/csv',
                            headers={'Content-Disposition': f'attachment; filename=programa_transporte_{date.today():%Y%m%d}.csv'})
        return render_template('compras/programa_transporte.html', datos=datos, ahora=datetime.now())
    except Exception as e:
        print(f'❌ Programa de transporte: {e}')
        return 'No se pudo generar el programa de transporte.', 500


@compras_flujo_bp.route('/compras/api/flujo/ordenes/<int:oc_id>/para_recibir')
def api_para_recibir(oc_id):
    try:
        o = _obtener_oc(oc_id)
        items = db_query("""
            SELECT oci.id, oci.producto_id, oci.producto, oci.unidad, pr.codigo, pr.marca, pr.modelo
            FROM ordenes_compra_items oci LEFT JOIN productos pr ON pr.id = oci.producto_id
            WHERE oci.orden_compra_id = %s AND COALESCE(oci.cantidad_recibida, 0) < oci.cantidad ORDER BY oci.id
        """, (oc_id,))
        return jsonify({'success': True, 'orden': {'id': o['id'], 'numero': o['numero'], 'proveedor': o['proveedor'],
                                                    'empresa': o['empresa'], 'sede': o['sede'],
                                                    'almacen_entrega_id': o['almacen_entrega_id'],
                                                    'modalidad_entrega': o['modalidad_entrega'], 'usuario_id': o['usuario_id']},
                        'items': [_fila(i) for i in items]})
    except Exception as e:
        return _respuesta_error(e)


@compras_flujo_bp.route('/compras/api/flujo/ordenes/<int:oc_id>/recibir', methods=['POST'])
def api_orden_recibir(oc_id):
    if not puede_recibir():
        return _no_autorizado('Solo el personal de almacén o de control puede recibir mercadería.')
    d = request.get_json(silent=True) or {}
    try:
        almacen_id = _entero(d.get('almacen_id'), 'la sede donde estás recibiendo')
        guia = (d.get('guia_proveedor') or '').strip().upper()
        if len(guia) < 4:
            raise ErrorCompras('Escribe el N° de guía de remisión del proveedor (ejemplo EG01-00001234). Sin guía no se recibe.')
        traido_tipo = d.get('traido_por_tipo') or ''
        if traido_tipo not in ('proveedor', 'usuario', 'courier'):
            raise ErrorCompras('Indica quién trajo la mercadería.')
        uid, unom = _usuario()
        traido_id, traido_nombre = None, None
        if traido_tipo == 'usuario':
            traido_id = _entero(d.get('traido_por_id'), 'la persona de la empresa que recogió')
            if traido_id == uid:
                raise PermissionError('Tú recogiste la mercadería: no puedes recibirla. La recibe y la cuenta otra persona en la sede.')
            f = db_query("SELECT COALESCE(NULLIF(nombres_apellidos, ''), usuario_sistema) AS n FROM usuarios WHERE id = %s", (traido_id,))
            if not f:
                raise ErrorCompras('La persona que recogió no existe.')
            traido_nombre = f[0]['n']
        elif traido_tipo == 'courier':
            traido_nombre = (d.get('traido_por') or '').strip()
            if not traido_nombre:
                raise ErrorCompras('Escribe el nombre de la empresa de transporte o del chofer.')
        else:
            traido_nombre = 'Transporte del proveedor'
        items_in = d.get('items') or []
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""SELECT oc.*, p.razon_social, p.ruc AS proveedor_ruc FROM ordenes_compra oc
                           LEFT JOIN proveedores p ON p.id = oc.proveedor_id
                           WHERE oc.id = %s FOR UPDATE OF oc""", (oc_id,))
            oc = cur.fetchone()
            if not oc or oc['flujo'] != 'v2':
                raise ErrorCompras('La orden no existe.')
            if oc['estado'] not in ESTADOS_ABIERTOS:
                raise ErrorCompras(f'La orden está "{oc["estado"]}". Solo se recibe mercadería de órdenes aprobadas. '
                                   'Si llegó algo sin orden aprobada, no lo recibas y avisa a tu supervisora.')
            if oc['usuario_id'] and oc['usuario_id'] == uid and not es_admin():
                raise PermissionError('Tú hiciste esta orden de compra: la mercadería la recibe otra persona.')
            if ((oc['condicion_pago'] or '').startswith('Contado') and not _es_intercompany(oc.get('proveedor_ruc'))
                    and _pagado_oc(oc_id) < a_decimal(oc['total'])):
                raise ErrorCompras('Esta orden es al contado y Finanzas todavía no registra el pago completo. '
                                   'Si el proveedor entregó sin pago, avisa a tu supervisora.')
            if (es_adelanto(oc['condicion_pago']) and not _es_intercompany(oc.get('proveedor_ruc'))
                    and _pagado_oc(oc_id) < monto_adelanto(oc['total'])):
                raise ErrorCompras('Esta orden es con adelanto del 50% y Finanzas todavía no registra el adelanto. '
                                   'Si el proveedor entregó sin adelanto, avisa a tu supervisora.')
            cur.execute("SELECT 1 FROM com_recepciones WHERE orden_compra_id = %s AND guia_proveedor = %s", (oc_id, guia))
            if cur.fetchone():
                raise ErrorCompras(f'La guía {guia} ya se registró en esta orden.')
            cur.execute("SELECT id FROM almacenes WHERE id = %s AND COALESCE(activo, true) = true", (almacen_id,))
            if not cur.fetchone():
                raise ErrorCompras('La sede no existe.')
            cur.execute("SELECT * FROM ordenes_compra_items WHERE orden_compra_id = %s ORDER BY id FOR UPDATE", (oc_id,))
            oc_items = {i['id']: i for i in cur.fetchall()}
            contados = {}
            for it in items_in:
                iid = int(it.get('oc_item_id') or 0)
                if iid not in oc_items:
                    raise ErrorCompras('Hay un producto que no es de esta orden.')
                buena = a_decimal(it.get('cantidad_buena'))
                danada = a_decimal(it.get('cantidad_danada'))
                if buena < 0 or danada < 0:
                    raise ErrorCompras('Las cantidades no pueden ser negativas.')
                if it.get('cantidad_buena') in (None, ''):
                    raise ErrorCompras(f'Escribe cuántos llegaron de "{oc_items[iid]["producto"]}" (si no llegó ninguno, escribe 0).')
                contados[iid] = (buena, danada, it)
            if not contados or sum(b + dn for b, dn, _ in contados.values()) <= 0:
                raise ErrorCompras('No escribiste ninguna cantidad. Cuenta lo que llegó.')
            # Pedido de Erika 22/10/2026 12:21: si lo contado no coincide con la OC, antes de grabar se avisa
            # con una ventana clara (la OC pide 5, estás registrando 50: sobran 45). Se cuenta a ciegas igual:
            # la cantidad de la OC solo se ve DESPUÉS de escribir lo contado y pulsar Guardar.
            difs = _diferencias_recepcion(oc_items, contados)
            confirmo = bool(d.get('confirmar_diferencias'))
            if difs and not confirmo:
                _historial(cur, oc_id, 'Aviso de diferencia al recibir',
                           f"Guía {guia}: " + '; '.join(x['texto'] for x in difs) + ' (aún no se grabó)')
                return jsonify({'success': False, 'codigo': 'diferencias', 'diferencias': difs,
                                'error': 'Lo que contaste no coincide con la orden de compra. Revisa antes de grabar.'}), 409
            numero = _siguiente_numero(cur, 'RC', 'com_recepciones')
            cur.execute("""
                INSERT INTO com_recepciones (numero, orden_compra_id, empresa_id, almacen_id, guia_proveedor, traido_por_tipo,
                    traido_por_id, traido_por, recibido_por_id, recibido_por, observaciones)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
            """, (numero, oc_id, oc['empresa_id'], almacen_id, guia, traido_tipo, traido_id, traido_nombre, uid, unom,
                  (d.get('observaciones') or '').strip() or None))
            rec_id = cur.fetchone()['id']
            from routes.stock_automatico import ingresar_recepcion
            resultado, diferencias, linea = [], 0, 0
            ingresados, separados, sin_ingresar = [], [], []
            for iid, (buena, danada, it) in contados.items():
                oi = oc_items[iid]
                pendiente = a_decimal(oi['cantidad']) - a_decimal(oi['cantidad_recibida'])
                llegado = buena + danada
                cur.execute("""
                    INSERT INTO com_recepcion_items (recepcion_id, oc_item_id, producto_id, pendiente_antes, cantidad_buena,
                        cantidad_danada, lote_serie, fecha_vencimiento, comentario)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (rec_id, iid, oi['producto_id'], pendiente, buena, danada, (it.get('lote_serie') or '').strip() or None,
                      it.get('fecha_vencimiento') or None, (it.get('comentario') or '').strip() or None))
                # Lo dañado no se cuenta como recibido: el proveedor debe reponerlo o dar nota de crédito
                cur.execute("UPDATE ordenes_compra_items SET cantidad_recibida = COALESCE(cantidad_recibida, 0) + %s WHERE id = %s",
                            (buena, iid))
                if buena > 0:
                    # En Supabase numero_recepcion es único: una fila por producto (RC-...-1, RC-...-2)
                    linea += 1
                    cur.execute("""
                        INSERT INTO recepciones_mercaderia (numero_recepcion, fecha, estado, orden_compra_id, orden_compra_numero,
                            proveedor_nombre, producto, cantidad, unidad, estado_mercaderia, observaciones, creado_por,
                            producto_id, empresa_id, almacen_id, costo_unitario, com_recepcion_id, oc_item_id, pedido_id,
                            pedido_numero, cliente, guia_proveedor, lote_serie, fecha_vencimiento)
                        VALUES (%s, NOW(), 'Aprobada', %s, %s, %s, %s, %s, %s, 'Buen estado', %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (f'{numero}-{linea}', oc_id, oc['numero_orden'], oc['razon_social'], oi['producto'], buena, oi['unidad'] or 'UND',
                          f'Guía {guia}', uid, oi['producto_id'], oc['empresa_id'], almacen_id, oi['precio_unitario'],
                          rec_id, iid, oi['pedido_id'], oi['pedido_numero'], oi['cliente'], guia,
                          (it.get('lote_serie') or '').strip() or None, it.get('fecha_vencimiento') or None))
                    rm_id = cur.fetchone()['id']
                    # Lo bueno entra solo al inventario (empresa de la OC, sede donde se recibió, costo de la OC)
                    mov, sep = ingresar_recepcion(cur, recepcion_id=rm_id, oc=oc, oi=oi, almacen_id=almacen_id,
                                                  cantidad=buena, guia=guia,
                                                  lote_serie=(it.get('lote_serie') or '').strip() or None,
                                                  fecha_vencimiento=it.get('fecha_vencimiento') or None)
                    if mov:
                        ingresados.append(mov['numero'])
                        if sep:
                            separados.append(f"{oi['producto']} para {oi['cliente']}")
                    else:
                        sin_ingresar.append(oi['producto'])
                fila = {'producto': oi['producto'], 'esperado': float(pendiente), 'llego': float(llegado),
                        'buena': float(buena), 'danada': float(danada), 'estado': 'Completo'}
                if danada > 0:
                    _incidencia(cur, oc_id, 'Dañado', f"{_cant(danada)} {oi['unidad'] or ''} de {oi['producto']} llegaron dañados (guía {guia}).",
                                rec_id, producto_id=oi['producto_id'], cantidad=danada,
                                monto=redondear(danada * a_decimal(oi['precio_unitario'])))
                    fila['estado'] = 'Con dañados'
                    diferencias += 1
                if buena > pendiente:
                    extra = buena - pendiente
                    _incidencia(cur, oc_id, 'Sobrante', f"Llegaron {_cant(extra)} de más de {oi['producto']} (guía {guia}). "
                                "Decidir: devolver al proveedor o pagar la diferencia.", rec_id, producto_id=oi['producto_id'],
                                cantidad=extra, monto=redondear(extra * a_decimal(oi['precio_unitario'])))
                    fila['estado'] = 'Sobrante'
                    diferencias += 1
                elif llegado < pendiente:
                    fila['estado'] = 'Faltante'
                    diferencias += 1
                resultado.append(fila)
            # Productos que no llegaron en esta guía también son faltantes de esta entrega
            for iid, oi in oc_items.items():
                if iid not in contados and a_decimal(oi['cantidad']) > a_decimal(oi['cantidad_recibida']):
                    resultado.append({'producto': oi['producto'], 'esperado': float(a_decimal(oi['cantidad']) - a_decimal(oi['cantidad_recibida'])),
                                      'llego': 0, 'buena': 0, 'danada': 0, 'estado': 'Faltante'})
            cur.execute("""SELECT COUNT(*) FILTER (WHERE COALESCE(cantidad_recibida, 0) < cantidad) AS faltan
                           FROM ordenes_compra_items WHERE orden_compra_id = %s""", (oc_id,))
            completa = cur.fetchone()['faltan'] == 0
            nuevo_estado = 'Recibida' if completa else 'Recibida parcial'
            cur.execute("UPDATE ordenes_compra SET estado = %s, updated_at = NOW() WHERE id = %s", (nuevo_estado, oc_id))
            if diferencias:
                cur.execute("UPDATE com_recepciones SET con_diferencias = true WHERE id = %s", (rec_id,))
            if difs:
                motivo = (d.get('motivo_diferencias') or '').strip()
                _historial(cur, oc_id, 'Recibió confirmando diferencias',
                           f"{numero} · Guía {guia} · " + '; '.join(x['texto'] for x in difs) + (f' · Motivo: {motivo}' if motivo else ''))
            _historial(cur, oc_id, 'Mercadería recibida', f"{numero} · Guía {guia} · trajo: {traido_nombre} · recibió: {unom}"
                       + (f' · sede distinta a la de la OC' if oc['almacen_entrega_id'] and oc['almacen_entrega_id'] != almacen_id else ''))
        faltantes = [r for r in resultado if r['estado'] == 'Faltante']
        msg = f'Recepción {numero} registrada. '
        msg += 'Llegó todo lo que faltaba. ' if completa else f'Aún falta mercadería ({len(faltantes)} producto(s)): la orden sigue abierta. '
        if ingresados:
            msg += f'Ya se sumó al inventario ({len(ingresados)} producto(s)). '
        if separados:
            msg += 'Quedó separado: ' + '; '.join(separados[:5]) + '. '
        if sin_ingresar:
            msg += 'Falta ingresar en Inventario ▸ Entradas y salidas: ' + ', '.join(sin_ingresar[:5]) + '.'
        return jsonify({'success': True, 'message': msg.strip(), 'numero': numero, 'resultado': resultado,
                        'estado': nuevo_estado, 'movimientos': ingresados, 'pendientes_inventario': sin_ingresar})
    except Exception as e:
        return _respuesta_error(e)


@compras_flujo_bp.route('/compras/api/flujo/incidencias/<int:inc_id>/resolver', methods=['POST'])
def api_incidencia_resolver(inc_id):
    if not puede_aprobar():
        return _no_autorizado('Solo una supervisora resuelve diferencias.')
    d = request.get_json(silent=True) or {}
    try:
        resolucion = (d.get('resolucion') or '').strip()
        if len(resolucion) < 5:
            raise ErrorCompras('Escribe cómo se resolvió (ejemplo: "el proveedor repone el lunes", "nota de crédito F001-123").')
        _, unom = _usuario()
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT orden_compra_id, numero, estado FROM com_incidencias WHERE id = %s FOR UPDATE", (inc_id,))
            inc = cur.fetchone()
            if not inc or inc['estado'] != 'Abierta':
                raise ErrorCompras('La diferencia ya estaba resuelta.')
            cur.execute("""UPDATE com_incidencias SET estado = 'Resuelta', resolucion = %s, resuelto_por = %s, resuelto_en = NOW()
                           WHERE id = %s""", (resolucion, unom, inc_id))
            _historial(cur, inc['orden_compra_id'], 'Diferencia resuelta', f"{inc['numero']}: {resolucion}")
            _intentar_cerrar(cur, inc['orden_compra_id'])
        return jsonify({'success': True, 'message': 'Diferencia resuelta.'})
    except Exception as e:
        return _respuesta_error(e)


@compras_flujo_bp.route('/compras/api/flujo/ordenes/<int:oc_id>/cerrar_faltante', methods=['POST'])
def api_cerrar_faltante(oc_id):
    """El proveedor ya no enviará lo que falta: se cierra lo pendiente y queda registrado como diferencia."""
    if not puede_aprobar():
        return _no_autorizado('Solo una supervisora puede dar por terminada una orden con faltante.')
    d = request.get_json(silent=True) or {}
    try:
        motivo = (d.get('motivo') or '').strip()
        if len(motivo) < 5:
            raise ErrorCompras('Explica por qué ya no llegará lo que falta.')
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT estado, flujo FROM ordenes_compra WHERE id = %s FOR UPDATE", (oc_id,))
            oc = cur.fetchone()
            if not oc or oc['flujo'] != 'v2' or oc['estado'] != 'Recibida parcial':
                raise ErrorCompras('Solo se usa en órdenes "Recibida parcial".')
            cur.execute("SELECT * FROM ordenes_compra_items WHERE orden_compra_id = %s AND COALESCE(cantidad_recibida, 0) < cantidad", (oc_id,))
            for oi in cur.fetchall():
                falta = a_decimal(oi['cantidad']) - a_decimal(oi['cantidad_recibida'])
                _incidencia(cur, oc_id, 'Faltante', f"No llegarán {_cant(falta)} de {oi['producto']}. {motivo}",
                            producto_id=oi['producto_id'], cantidad=falta, monto=redondear(falta * a_decimal(oi['precio_unitario'])))
            cur.execute("UPDATE ordenes_compra SET estado = 'Recibida', updated_at = NOW() WHERE id = %s", (oc_id,))
            _historial(cur, oc_id, 'Cerrada con faltante', motivo)
        return jsonify({'success': True, 'message': 'Listo. Lo que faltaba quedó como diferencia: pide la nota de crédito o la devolución del dinero.'})
    except Exception as e:
        return _respuesta_error(e)


# ============================================================
# FACTURA DEL PROVEEDOR (control de 3 vías: OC = recepción = factura)
# ============================================================
def _intentar_cerrar(cur, oc_id):
    cur.execute("""
        SELECT oc.estado,
               (SELECT COUNT(*) FROM com_incidencias WHERE orden_compra_id = oc.id AND estado = 'Abierta') AS inc,
               (SELECT COUNT(*) FROM comprobantes_proveedor WHERE orden_compra_id = oc.id
                  AND COALESCE(UPPER(estado), '') NOT IN ('ANULADO', 'ANULADA')) AS fac
        FROM ordenes_compra oc WHERE oc.id = %s
    """, (oc_id,))
    f = cur.fetchone()
    if f and f['estado'] == 'Recibida' and f['inc'] == 0 and f['fac'] > 0:
        cur.execute("UPDATE ordenes_compra SET estado = 'Cerrada', updated_at = NOW() WHERE id = %s", (oc_id,))
        _historial(cur, oc_id, 'Cerrada', 'Recibida, facturada y sin diferencias')


@compras_flujo_bp.route('/compras/api/flujo/ordenes/<int:oc_id>/factura', methods=['POST'])
def api_orden_factura(oc_id):
    if not puede_facturar():
        return _no_autorizado('Tu usuario no puede registrar facturas de proveedores.')
    d = request.get_json(silent=True) or {}
    try:
        tipo = d.get('tipo') or 'Factura'
        if tipo not in ('Factura', 'Boleta', 'Recibo por honorarios'):
            raise ErrorCompras('Tipo de comprobante inválido.')
        numero = (d.get('numero') or '').strip().upper().replace(' ', '')
        if '-' not in numero or len(numero) < 6:
            raise ErrorCompras('Escribe la serie y el número tal como están en la factura, por ejemplo F001-00012345.')
        monto = redondear(d.get('monto'))
        if monto <= 0:
            raise ErrorCompras('Escribe el total de la factura (con IGV).')
        try:
            fecha = datetime.strptime((d.get('fecha') or '')[:10], '%Y-%m-%d').date()
        except ValueError:
            raise ErrorCompras('Escribe la fecha de emisión de la factura.')
        if fecha > date.today():
            raise ErrorCompras('La fecha de la factura no puede ser futura.')
        uid, unom = _usuario()
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""SELECT oc.*, p.razon_social, p.ruc FROM ordenes_compra oc LEFT JOIN proveedores p ON p.id = oc.proveedor_id
                           WHERE oc.id = %s FOR UPDATE OF oc""", (oc_id,))
            oc = cur.fetchone()
            if not oc or oc['flujo'] != 'v2':
                raise ErrorCompras('La orden no existe.')
            if oc['estado'] in ('Borrador', 'Por aprobar', 'Anulada'):
                raise ErrorCompras(f'La orden está "{oc["estado"]}". La factura se registra cuando la orden está aprobada.')
            # La factura viene en la moneda de la OC; en dólares lleva el TC SUNAT de su fecha (para el registro de compras)
            moneda_f, tc_f = moneda_y_tc({'moneda': oc.get('moneda') or 'PEN', 'tipo_cambio': d.get('tipo_cambio')})
            sim = simbolo(moneda_f)
            ruc = (oc['ruc'] or '').strip()
            cur.execute("""SELECT 1 FROM comprobantes_proveedor WHERE numero = %s AND COALESCE(ruc_proveedor, '') = %s
                           AND COALESCE(UPPER(estado), '') NOT IN ('ANULADO', 'ANULADA')""", (numero, ruc))
            if cur.fetchone():
                raise ErrorCompras(f'La factura {numero} de este proveedor ya está registrada.')
            # Lo que debería cobrar el proveedor: lo recibido en buen estado (o lo pedido si aún no llega nada),
            # menos lo que ya facturó antes en esta misma orden.
            cur.execute("""SELECT SUM(LEAST(COALESCE(cantidad_recibida, 0), cantidad) * precio_unitario) AS rec,
                                  SUM(cantidad * precio_unitario) AS ped FROM ordenes_compra_items WHERE orden_compra_id = %s""", (oc_id,))
            v = cur.fetchone()
            base = a_decimal(v['rec']) if a_decimal(v['rec']) > 0 else a_decimal(v['ped'])
            cur.execute("""SELECT COALESCE(SUM(monto), 0) AS f FROM comprobantes_proveedor WHERE orden_compra_id = %s
                           AND COALESCE(UPPER(estado), '') NOT IN ('ANULADO', 'ANULADA')""", (oc_id,))
            ya_facturado = a_decimal(cur.fetchone()['f'])
            esperado = redondear(redondear(base) + redondear(base * tasa_igv()) - ya_facturado)
            cuadra = abs(monto - esperado) <= TOLERANCIA_FACTURA
            # Pedido de Erika 20/10/2026: si no cuadra NO se guarda; se avisa y se corrige en el mismo momento.
            # Solo si la factura física realmente dice ese monto se registra (dentro de su OC) marcando
            # "aceptar_diferencia" con el motivo; queda como diferencia por resolver, nunca suelta.
            motivo_dif = (d.get('motivo_diferencia') or '').strip()
            if not cuadra and not d.get('aceptar_diferencia'):
                return jsonify({'success': False, 'codigo': 'no_cuadra', 'esperado': float(esperado), 'monto': float(monto),
                                'diferencia': float(redondear(monto - esperado)),
                                'error': f'La factura no cuadra: escribiste {sim} {monto} y según lo recibido debería ser '
                                         f'{sim} {esperado} (diferencia {sim} {redondear(monto - esperado)}). Revisa el total y corrígelo.'}), 409
            if not cuadra and len(motivo_dif) < 5:
                raise ErrorCompras('Escribe por qué registras la factura con diferencia (por ejemplo: "el proveedor cobró flete").')
            dias_oc = int(oc['dias_credito'] or 0)
            if dias_oc > 360:
                raise ErrorCompras(f'La orden {oc["numero_orden"]} tiene {dias_oc} días de crédito (no es posible). '
                                   'Corrige los días de crédito de la orden antes de registrar la factura.')
            vence = fecha + timedelta(days=dias_oc)
            cur.execute("""
                INSERT INTO comprobantes_proveedor (tipo, numero, fecha, monto, ruc_proveedor, proveedor_nombre, orden_compra_id,
                    orden_compra_numero, estado, observaciones, creado_por, empresa_id, fecha_vencimiento, monto_esperado, cuadra)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'Pendiente',%s,%s,%s,%s,%s,%s) RETURNING id
            """, (tipo, numero, fecha, monto, ruc, oc['razon_social'], oc_id, oc['numero_orden'],
                  ' · '.join(x for x in ((d.get('observaciones') or '').strip(),
                                         f'Registrada con diferencia: {motivo_dif}' if not cuadra else '') if x) or None,
                  uid, oc['empresa_id'], vence, esperado, cuadra))
            cp_id = cur.fetchone()['id']
            cur.execute("UPDATE comprobantes_proveedor SET moneda = %s, tipo_cambio = %s WHERE id = %s", (moneda_f, tc_f, cp_id))
            # Los pagos adelantados de la OC pasan a esta factura (así Cuentas por pagar muestra el saldo real)
            cur.execute("""SELECT id, monto FROM finanzas_pagos WHERE documento_tabla = 'ordenes_compra' AND documento_id = %s
                           AND tipo = 'PAGO' AND estado <> 'Anulado' ORDER BY fecha, id FOR UPDATE""", (oc_id,))
            aplicado = Decimal('0')
            for p in cur.fetchall():
                if aplicado + a_decimal(p['monto']) > monto:
                    break
                cur.execute("UPDATE finanzas_pagos SET documento_tabla = 'comprobantes_proveedor', documento_id = %s, documento_numero = %s WHERE id = %s",
                            (cp_id, numero, p['id']))
                aplicado += a_decimal(p['monto'])
            if aplicado >= monto:
                cur.execute("UPDATE comprobantes_proveedor SET estado = 'Pagado' WHERE id = %s", (cp_id,))
            if not cuadra:
                _incidencia(cur, oc_id, 'Factura no cuadra',
                            f'La factura {numero} dice {sim} {monto} y según lo recibido debería ser {sim} {esperado} '
                            f'(diferencia {sim} {redondear(monto - esperado)}). Pide la corrección o una nota de crédito.',
                            comprobante_id=cp_id, monto=redondear(monto - esperado))
            _historial(cur, oc_id, 'Factura registrada', f'{tipo} {numero} · {sim} {monto}' + (f' · TC {tc_f}' if tc_f else '')
                       + ('' if cuadra else f' · NO CUADRA (esperado {sim} {esperado})'))
            _intentar_cerrar(cur, oc_id)
        msg = f'Factura {numero} registrada.'
        msg += ' Cuadra con lo recibido. ✔' if cuadra else f' OJO: no cuadra, debería ser {sim} {esperado}. Quedó como diferencia por resolver.'
        if aplicado:
            msg += f' Se le aplicó el pago adelantado de {sim} {aplicado}.'
        return jsonify({'success': True, 'message': msg, 'cuadra': cuadra, 'esperado': float(esperado), 'id': cp_id})
    except Exception as e:
        return _respuesta_error(e)


def _factura_proveedor(where, params):
    filas = db_query(f"""
        SELECT cp.id, cp.tipo, cp.numero, cp.fecha, cp.monto, cp.monto_esperado, cp.cuadra, cp.estado,
               COALESCE(cp.moneda, 'PEN') AS moneda, cp.tipo_cambio,
               cp.fecha_vencimiento, cp.observaciones, cp.created_at, cp.ruc_proveedor, cp.proveedor_nombre,
               cp.orden_compra_id, cp.orden_compra_numero, u.nombre_completo AS registrado_por
        FROM comprobantes_proveedor cp LEFT JOIN usuarios u ON u.id::text = cp.creado_por::text
        WHERE {where} ORDER BY cp.id DESC LIMIT 1""", params)
    if not filas:
        return None
    f = dict(filas[0])
    for k in ('monto', 'monto_esperado'):
        f[k] = float(f[k]) if f.get(k) is not None else None
    for k in ('fecha', 'fecha_vencimiento', 'created_at'):
        f[k] = f[k].isoformat() if f.get(k) else None
    return f


@compras_flujo_bp.route('/compras/api/flujo/facturas/ultima')
def api_factura_ultima():
    """La última factura de proveedor que registró este usuario (botón "Ver la factura registrada recientemente")."""
    uid, _ = _usuario()
    f = _factura_proveedor('cp.creado_por::text = %s AND cp.orden_compra_id IS NOT NULL', (str(uid),)) if uid else None
    return jsonify({'success': True, 'data': f})


@compras_flujo_bp.route('/compras/api/flujo/facturas/<int:fid>')
def api_factura_ver(fid):
    f = _factura_proveedor('cp.id = %s', (fid,))
    if not f:
        return jsonify({'success': False, 'error': 'La factura no existe.'}), 404
    return jsonify({'success': True, 'data': f})


# ============================================================
# IMPRESIÓN: ORDEN DE COMPRA PARA EL PROVEEDOR Y HOJA DE RECOJO
# ============================================================
@compras_flujo_bp.route('/compras/flujo/ordenes/<int:oc_id>/imprimir')
def orden_imprimir(oc_id):
    try:
        o = _obtener_oc(oc_id)
        if o['estado'] in ('Borrador', 'Por aprobar') and request.args.get('hoja') != 'borrador':
            return 'La orden todavía no está aprobada. Solo se envía al proveedor cuando está aprobada.', 409
        empresa = db_query("SELECT * FROM erp_empresas WHERE id = %s", (o['empresa_id'],)) if o['empresa_id'] else []
        sede = db_query("SELECT * FROM almacenes WHERE id = %s", (o['almacen_entrega_id'],)) if o['almacen_entrega_id'] else []
        prov = db_query("SELECT * FROM proveedores WHERE id = %s", (o['proveedor_id'],)) if o['proveedor_id'] else []
        # 22/10/2026: la hoja lleva modelo y marca del catálogo; si el producto no los tiene, la celda queda vacía
        items = db_query("""SELECT i.id, i.producto, i.unidad, i.cantidad, i.precio_unitario, i.total,
                                   NULLIF(TRIM(to_jsonb(p)->>'modelo'), '') AS modelo,
                                   NULLIF(TRIM(to_jsonb(p)->>'marca'), '') AS marca
                            FROM ordenes_compra_items i
                            LEFT JOIN productos p ON p.id::text = i.producto_id::text
                            WHERE i.orden_compra_id = %s ORDER BY i.id""", (oc_id,))
        # Pedido de Erika 22/10/2026 (reemplaza el del 20/10): el proveedor no ve el N° PC ni ningún N° interno
        # Documento para el PROVEEDOR: nunca lleva cliente, cotización del cliente ni motivo interno
        o = {k: v for k, v in dict(o).items() if k not in CAMPOS_CONFIDENCIALES}
        return render_template('compras/imprimir_oc.html', o=o, empresa=empresa[0] if empresa else {},
                               sede=sede[0] if sede else {}, prov=prov[0] if prov else {}, items=items,
                               hoja=request.args.get('hoja') or 'oc', hoy=date.today(),
                               declarada=_sede_declarada(o['empresa_id'], o['almacen_entrega_id']) if o['empresa_id'] and o['almacen_entrega_id'] else None)
    except Exception as e:
        print(f'❌ Imprimir OC: {e}')
        return 'No se pudo generar la orden.', 500


@compras_flujo_bp.route('/compras/api/flujo/ordenes/exportar')
def api_ordenes_exportar():
    try:
        datos = _listar_ocs("oc.flujo = 'v2'")
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=';')
        w.writerow(['OC', 'Fecha', 'Empresa', 'Sede', 'Proveedor', 'RUC', 'Tipo', 'Pedidos', 'Clientes', 'Condición',
                    'Moneda', 'Tipo de cambio', 'Total', 'Pagado', 'Estado', 'Siguiente paso', 'Diferencias abiertas'])
        for o in datos:
            w.writerow([o['numero'], o['fecha'], o['empresa'], o['sede'], o['proveedor'], o['ruc'], o['tipo_compra'],
                        o['pedidos'], o['clientes'], o['condicion_pago'], o.get('moneda') or 'PEN', o.get('tipo_cambio') or '',
                        o['total'], o['pagado'], o['estado'],
                        o['paso']['texto'], o['incidencias']])
        return Response('﻿' + buf.getvalue(), mimetype='text/csv',
                        headers={'Content-Disposition': f'attachment; filename=ordenes_compra_{date.today():%Y%m%d}.csv'})
    except Exception as e:
        return _respuesta_error(e)
