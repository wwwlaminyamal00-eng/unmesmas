# routes/finanzas.py - Módulo de Finanzas / Tesorería
#
# Trabaja sobre los documentos que YA existen en el ERP:
#   - Cuentas por cobrar (CxC): comprobantes de venta (tabla comprobantes)
#   - Cuentas por pagar (CxP): comprobantes de proveedor (tabla comprobantes_proveedor)
# y agrega una sola tabla nueva, finanzas_pagos, para registrar cobros y pagos
# (parciales o totales) con trazabilidad de usuario. No modifica ni borra datos existentes.
import json
import os
import threading
from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import Blueprint, render_template, request, jsonify, session
from psycopg2.extras import RealDictCursor

from database import db_query, db_execute, db_tx
from utils import a_decimal, redondear, es_admin, es_aprobador, normalizar_banco
from routes.multiempresa import filtro_sql
from routes import cuentas_proveedor
from routes.moneda import (ErrorMoneda, codigo_moneda, simbolo, pago_en_moneda, tc_referencia,
                           sql_monto_soles)

finanzas_bp = Blueprint('finanzas', __name__)

ROLES_FINANZAS = {r.strip().lower() for r in os.environ.get(
    'ROLES_FINANZAS', 'finanzas,contabilidad,tesoreria,gerencia').split(',') if r.strip()}

METODOS_PAGO = ('Transferencia', 'Depósito', 'Efectivo', 'Cheque', 'Yape/Plin', 'Detracción', 'Otro')
# Cobros por banco: el cliente manda el N.º de operación o solo avisa con una fecha (pedido de Erika 21/10/2026).
# Se exige al menos uno de los dos, no los dos.
METODOS_CON_COMPROBANTE = ('Transferencia', 'Depósito', 'Yape/Plin')

_tablas_listas = False
_lock_tablas = threading.Lock()

# Script equivalente: migrations/001_finanzas_y_mejoras.sql
SQL_DDL_FINANZAS = """
    CREATE TABLE IF NOT EXISTS finanzas_pagos (
        id SERIAL PRIMARY KEY,
        tipo VARCHAR(10) NOT NULL CHECK (tipo IN ('COBRO', 'PAGO')),
        documento_tabla VARCHAR(40) NOT NULL,
        documento_id INTEGER NOT NULL,
        documento_numero VARCHAR(60),
        tercero_nombre VARCHAR(255),
        tercero_documento VARCHAR(20),
        fecha DATE NOT NULL DEFAULT CURRENT_DATE,
        monto NUMERIC(14,2) NOT NULL CHECK (monto > 0),
        metodo VARCHAR(40),
        banco VARCHAR(80),
        numero_operacion VARCHAR(80),
        observaciones TEXT,
        estado VARCHAR(20) NOT NULL DEFAULT 'Registrado',
        usuario_id INTEGER,
        usuario_nombre VARCHAR(150),
        anulado_por INTEGER,
        anulado_en TIMESTAMP,
        motivo_anulacion TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_finanzas_pagos_doc ON finanzas_pagos (documento_tabla, documento_id);
    ALTER TABLE comprobantes_proveedor ADD COLUMN IF NOT EXISTS fecha_vencimiento DATE;
    ALTER TABLE finanzas_pagos ADD COLUMN IF NOT EXISTS fecha_aviso DATE;
    -- Comentario de Finanzas por factura (pedido de Erika 21/10/2026 18:38). Migración 018.
    CREATE TABLE IF NOT EXISTS finanzas_comentarios (
        documento_tabla VARCHAR(40) NOT NULL,
        documento_id INTEGER NOT NULL,
        comentario TEXT,
        usuario_nombre VARCHAR(150),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (documento_tabla, documento_id)
    );
    -- Seguimiento del cobro por factura de venta (Erika 23/10/2026, desde su Excel de seguimiento). Migración 029.
    CREATE TABLE IF NOT EXISTS finanzas_seguimiento_cobro (
        comprobante_id INTEGER PRIMARY KEY,
        portal_ingresado BOOLEAN NOT NULL DEFAULT false,
        portal_fecha DATE,
        fecha_programada DATE,
        retencion_numero VARCHAR(40),
        retencion_monto NUMERIC(14,2) CHECK (retencion_monto >= 0),
        usuario_nombre VARCHAR(150),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    -- Fecha del comprobante de retención del cliente (Erika 26/10/2026). Migración 035.
    ALTER TABLE finanzas_seguimiento_cobro ADD COLUMN IF NOT EXISTS retencion_fecha DATE;
"""


def asegurar_tablas_finanzas():
    """Crea (si no existen) la tabla de pagos y la columna de vencimiento de CxP. No borra nada."""
    global _tablas_listas
    if _tablas_listas:
        return
    with _lock_tablas:
        if _tablas_listas:
            return
        with db_tx() as conn:
            cur = conn.cursor()
            # Bloqueo para que varias peticiones simultáneas no intenten crear la tabla a la vez
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('finanzas_ddl'))")
            cur.execute(SQL_DDL_FINANZAS)
        # Moneda y tipo de cambio de los documentos y pagos (24/10/2026)
        from routes.moneda import asegurar_moneda
        asegurar_moneda()
        # N° MIGO del cliente y de la factura (25/10/2026, migración 031)
        from routes.migo import asegurar_migo
        asegurar_migo()
        # Cuentas 2 y 3 del proveedor (28/10/2026, migración 043): las usa SQL_CXP
        cuentas_proveedor.asegurar()
        _tablas_listas = True


def puede_operar_finanzas():
    rol = (session.get('rol') or '').lower()
    return es_admin() or es_aprobador() or rol in ROLES_FINANZAS


def _semaforo(saldo, vencimiento, hoy):
    if saldo <= 0:
        return 'Pagado'
    if vencimiento is None:
        return 'Al día'
    if isinstance(vencimiento, datetime):
        vencimiento = vencimiento.date()
    if vencimiento < hoy:
        return 'Vencido'
    if vencimiento <= hoy + timedelta(days=7):
        return 'Por vencer'
    return 'Al día'


def _fmt(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()[:10]
    return v


# ============================================================
# CONSULTAS BASE
# ============================================================
SQL_CXC = """
    WITH cobros AS (
        -- Fecha real de pago del cliente = la de su aviso de pago; si no la hay, la del registro (Erika 26/10/2026)
        SELECT documento_id, SUM(monto) AS cobrado, MAX(COALESCE(fecha_aviso, fecha)) AS ultimo_abono
        FROM finanzas_pagos
        WHERE documento_tabla = 'comprobantes' AND tipo = 'COBRO' AND estado <> 'Anulado'
        GROUP BY documento_id
    ),
    nc AS (
        SELECT comprobante_asociado, empresa_id, SUM(monto) AS monto_nc
        FROM notas_credito
        WHERE COALESCE(UPPER(estado), '') NOT IN ('ANULADA', 'ANULADO', 'BORRADOR', 'POR APROBAR', 'RECHAZADA')
        GROUP BY comprobante_asociado, empresa_id
    )
    SELECT c.id, c.tipo_comprobante, c.serie, c.numero,
           COALESCE(c.serie, '') || '-' || LPAD(COALESCE(c.numero::text, ''), 8, '0') AS documento,
           c.cliente_nombre AS tercero, c.cliente_numero_doc AS ruc,
           c.fecha_emision, c.condicion_pago, c.es_credito, c.dias_credito,
           COALESCE(c.fecha_vencimiento::date,
                    c.fecha_emision::date + COALESCE(c.dias_credito, 0)) AS fecha_vencimiento,
           COALESCE(c.total, 0) AS total,
           -- Retención: la que se anotó del comprobante de retención del cliente o, si no, la calculada en la factura
           COALESCE(sg.retencion_monto, c.monto_retenido, 0) AS retencion,
           CASE WHEN sg.retencion_monto IS NOT NULL THEN COALESCE(c.total, 0) - sg.retencion_monto
                ELSE COALESCE(NULLIF(c.monto_a_pagar, 0), c.total, 0) END AS importe_cobrar,
           COALESCE(c.tiene_retencion, false) AS tiene_retencion, COALESCE(c.monto_retenido, 0) AS retencion_factura,
           COALESCE(sg.portal_ingresado, false) AS portal_ingresado, sg.portal_fecha, sg.fecha_programada,
           sg.retencion_numero, sg.retencion_fecha, sg.retencion_monto AS retencion_anotada, sg.usuario_nombre AS seguimiento_por,
           c.numero_migo, EXISTS (SELECT 1 FROM clientes cm WHERE cm.numero_documento = c.cliente_numero_doc
                                  AND COALESCE(cm.pide_migo, false)) AS pide_migo,
           COALESCE(cb.cobrado, 0) AS cobrado,
           COALESCE(nc.monto_nc, 0) AS notas_credito,
           COALESCE(c.estado_sunat, 'Borrador') AS estado_documento,
           cb.ultimo_abono, COALESCE(NULLIF(c.moneda, ''), 'PEN') AS moneda, c.tipo_cambio, c.empresa_id AS empresa_doc,
           NULLIF(c.pc_vinculado, '') AS pc_numero,
           -- N° PC (Pedido del cliente): el de la factura o, si no se escribió, el del PV (Erika 26/10/2026)
           COALESCE(NULLIF(c.orden_compra_cliente, ''),
                    (SELECT NULLIF(to_jsonb(p) ->> 'oc_cliente', '') FROM pedido_compra_pc p
                     WHERE p.numero = c.pc_vinculado ORDER BY p.id DESC LIMIT 1)) AS oc_cliente,
           NULL AS oc_numero, NULL AS tipo_compra, 0 AS adelanto, NULL AS nota_registro,
           c.items_json::text AS items_txt, fc.comentario, fc.usuario_nombre AS comentario_por
    FROM comprobantes c
    LEFT JOIN cobros cb ON cb.documento_id = c.id
    LEFT JOIN finanzas_comentarios fc ON fc.documento_tabla = 'comprobantes' AND fc.documento_id = c.id
    LEFT JOIN finanzas_seguimiento_cobro sg ON sg.comprobante_id = c.id
    LEFT JOIN nc ON nc.comprobante_asociado IN (c.numero::text, LPAD(c.numero::text, 8, '0'),
                                                COALESCE(c.serie, '') || '-' || COALESCE(c.numero::text, ''),
                                                COALESCE(c.serie, '') || '-' || LPAD(COALESCE(c.numero::text, ''), 8, '0'))
                  AND (nc.empresa_id IS NULL OR c.empresa_id IS NULL OR nc.empresa_id = c.empresa_id)
    WHERE COALESCE(UPPER(c.estado_sunat), '') NOT IN ('ANULADO', 'ANULADA')
"""

SQL_CXP = """
    SELECT cp.id, cp.tipo AS tipo_comprobante, NULL AS serie, cp.numero,
           cp.numero AS documento,
           cp.proveedor_nombre AS tercero, cp.ruc_proveedor AS ruc,
           cp.fecha AS fecha_emision, oc.condicion_pago, NULL::boolean AS es_credito,
           NULLIF(regexp_replace(CASE WHEN strpos(lower(COALESCE(oc.condicion_pago, '')), 'adelanto') > 0 THEN '' ELSE COALESCE(oc.condicion_pago, '') END, '\\D', '', 'g'), '')::int AS dias_credito,
           COALESCE(cp.fecha_vencimiento,
                    cp.fecha::date + COALESCE(NULLIF(regexp_replace(CASE WHEN strpos(lower(COALESCE(oc.condicion_pago, '')), 'adelanto') > 0 THEN '' ELSE COALESCE(oc.condicion_pago, '') END, '\\D', '', 'g'), '')::int, 0)
           ) AS fecha_vencimiento,
           COALESCE(cp.monto, 0) AS total,
           0 AS retencion,
           COALESCE(cp.monto, 0) AS importe_cobrar,
           COALESCE(pg.pagado, 0) AS cobrado,
           0 AS notas_credito,
           COALESCE(cp.estado, 'Pendiente') AS estado_documento,
           COALESCE(cp.orden_compra_numero, oc.numero_orden) AS orden_compra,
           pr.banco, pr.numero_cuenta, pr.cci, pr.tipo_cuenta, pr.moneda_cuenta, pr.prov_moneda,
           pr.banco2, pr.tipo_cuenta2, pr.moneda_cuenta2, pr.numero_cuenta2, pr.cci2,
           pr.banco3, pr.tipo_cuenta3, pr.moneda_cuenta3, pr.numero_cuenta3, pr.cci3,
           pg.ultimo_abono, COALESCE(NULLIF(cp.moneda, ''), oc.moneda, 'PEN') AS moneda,
           COALESCE(cp.tipo_cambio, oc.tipo_cambio) AS tipo_cambio, cp.empresa_id AS empresa_doc,
           COALESCE(NULLIF(oc.pc_numeros, ''),
                    (SELECT string_agg(DISTINCT i.pedido_numero, ', ') FROM ordenes_compra_items i
                      WHERE i.orden_compra_id = cp.orden_compra_id AND COALESCE(i.pedido_numero, '') <> '')) AS pc_numero, NULL AS oc_cliente,
           COALESCE(cp.orden_compra_numero, oc.numero_orden) AS oc_numero, oc.tipo_compra,
           COALESCE(pg.adelanto, 0) AS adelanto, cp.observaciones AS nota_registro,
           (SELECT json_agg(json_build_object('producto', i.producto, 'cantidad', i.cantidad) ORDER BY i.id)::text
              FROM ordenes_compra_items i WHERE i.orden_compra_id = cp.orden_compra_id) AS items_txt,
           fc.comentario, fc.usuario_nombre AS comentario_por
    FROM comprobantes_proveedor cp
    -- Pagos de la factura. "Adelanto" = lo pagado en Compras antes de registrar la factura (pasó de la OC a la factura)
    LEFT JOIN LATERAL (
        SELECT SUM(f.monto) AS pagado, MAX(f.fecha) AS ultimo_abono,
               SUM(f.monto) FILTER (WHERE f.created_at < cp.created_at) AS adelanto
        FROM finanzas_pagos f
        WHERE f.documento_tabla = 'comprobantes_proveedor' AND f.documento_id = cp.id
          AND f.tipo = 'PAGO' AND f.estado <> 'Anulado'
    ) pg ON TRUE
    LEFT JOIN ordenes_compra oc ON oc.id = cp.orden_compra_id
    LEFT JOIN finanzas_comentarios fc ON fc.documento_tabla = 'comprobantes_proveedor' AND fc.documento_id = cp.id
    -- Cuenta del proveedor para el recuadro "Pagar a" (por la OC; si no hay OC, por el RUC)
    LEFT JOIN LATERAL (
        SELECT p.banco, p.numero_cuenta, p.cci, p.tipo_cuenta, p.moneda_cuenta, p.moneda AS prov_moneda,
               p.banco2, p.tipo_cuenta2, p.moneda_cuenta2, p.numero_cuenta2, p.cci2,
               p.banco3, p.tipo_cuenta3, p.moneda_cuenta3, p.numero_cuenta3, p.cci3
        FROM proveedores p
        WHERE p.id = oc.proveedor_id OR (oc.proveedor_id IS NULL AND p.ruc = cp.ruc_proveedor)
        ORDER BY (p.id = oc.proveedor_id) DESC NULLS LAST, p.activo DESC NULLS LAST, p.id
        LIMIT 1
    ) pr ON TRUE
    WHERE COALESCE(UPPER(cp.estado), '') NOT IN ('ANULADO', 'ANULADA')
"""


def _productos(items_txt):
    """Productos de la factura (venta) o de su OC (compra): [{'producto', 'cantidad'}]."""
    try:
        items = json.loads(items_txt) if items_txt else []
    except (TypeError, ValueError):
        return []
    if isinstance(items, dict):
        items = items.get('items') or []
    salida = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        nombre = str(it.get('producto') or it.get('descripcion') or it.get('nombre') or '').strip()
        if nombre:
            cant = it.get('cantidad')
            try:
                cant = float(cant) if cant not in (None, '') else None
            except (TypeError, ValueError):
                cant = None
            salida.append({'producto': nombre, 'cantidad': cant})
    return salida


def _detalle(tipo, f, saldo, abonado):
    """Columnas de detalle pedidas por Erika el 21/10/2026 18:38: a qué compra o venta pertenece la factura,
    estado del pago (pendiente / parcial / pagado) y fecha real de pago."""
    es_cxc = tipo == 'cxc'
    if saldo <= 0:
        estado = 'Cobrado' if es_cxc else 'Pagado'
    elif abonado > 0:
        estado = 'Cobro parcial' if es_cxc else 'Pago parcial'
    else:
        estado = 'Por cobrar' if es_cxc else 'Pendiente'
    pc = f.get('pc_numero')
    if not es_cxc and not pc and f.get('oc_numero'):
        pc = 'Compra a stock' if 'stock' in str(f.get('tipo_compra') or '').lower() else 'Sin PV vinculado'
    return {'estado_pago': estado, 'pc_numero': pc,
            'fecha_pago_real': _fmt(f.get('ultimo_abono')) if saldo <= 0 and f.get('ultimo_abono') else None,
            'ultimo_abono': _fmt(f.get('ultimo_abono')),
            'adelanto': float(redondear(a_decimal(f.get('adelanto') or 0))),
            'productos': _productos(f.get('items_txt')), 'items_txt': None}


def _cuentas(tipo, incluir_borradores=False):
    asegurar_tablas_finanzas()
    sql = SQL_CXC if tipo == 'cxc' else SQL_CXP
    if tipo == 'cxc' and not incluir_borradores:
        sql += " AND COALESCE(UPPER(c.estado_sunat), 'BORRADOR') <> 'BORRADOR'"
    # Solo la empresa elegida arriba ("Todas" = consolidado)
    sql_emp, par_emp = filtro_sql('c.empresa_id' if tipo == 'cxc' else 'cp.empresa_id')
    filas = db_query(sql + sql_emp + " ORDER BY 1 DESC", par_emp)
    hoy = date.today()
    resultado = []
    tc_ref = None
    for f in filas:
        importe = a_decimal(f['importe_cobrar'])
        abonado = a_decimal(f['cobrado']) + a_decimal(f['notas_credito'])
        saldo = redondear(importe - abonado)
        if saldo < 0:
            saldo = a_decimal(0)
        venc = f.get('fecha_vencimiento')
        semaforo = _semaforo(saldo, venc, hoy)
        dias_vencido = (hoy - (venc.date() if isinstance(venc, datetime) else venc)).days if venc and semaforo == 'Vencido' else 0
        if tipo != 'cxc':
            # 28/10/2026 (Erika): "Pagar a" usa la cuenta del mismo banco que la empresa (KCF BBVA, AGD BCP)
            f = cuentas_proveedor.aplicar(dict(f), f.get('empresa_doc'), f.get('moneda'))
            f.pop('prov_moneda', None)
        item = {k: _fmt(v) for k, v in f.items()}
        item.update(_detalle(tipo, f, saldo, abonado))
        # 24/10/2026 (Erika): documentos en dólares. Los totales y el flujo suman en soles con el TC del documento
        moneda = codigo_moneda(f.get('moneda'))
        tc = f.get('tipo_cambio')
        if moneda == 'USD' and not tc:
            tc_ref = tc_ref if tc_ref is not None else (tc_referencia(hoy) or 0)
            tc = tc_ref or None
        item.update({
            'moneda': moneda,
            'tipo_cambio': float(tc) if tc else None,
            'saldo_soles': float(redondear(saldo * a_decimal(tc))) if moneda == 'USD' and tc else (float(saldo) if moneda == 'PEN' else None),
            'total': float(redondear(f['total'])),
            'retencion': float(redondear(f['retencion'])),
            'importe': float(redondear(importe)),
            'abonado': float(redondear(f['cobrado'])),
            'notas_credito': float(redondear(f['notas_credito'])),
            'saldo': float(saldo),
            'semaforo': semaforo,
            'dias_vencido': dias_vencido,
        })
        resultado.append(item)
    return resultado


# ============================================================
# VISTA
# ============================================================
@finanzas_bp.route('/finanzas')
def finanzas():
    return render_template('finanzas.html', puede_operar=puede_operar_finanzas(), metodos=METODOS_PAGO)


# ============================================================
# API
# ============================================================
@finanzas_bp.route('/finanzas/api/resumen', methods=['GET'])
def api_resumen():
    try:
        cxc = _cuentas('cxc')
        cxp = _cuentas('cxp')
        hoy = date.today()
        inicio_mes = hoy.replace(day=1)
        sql_emp, par_emp = filtro_sql('empresa_id')
        mov = db_query("""
            SELECT tipo, COALESCE(SUM(""" + sql_monto_soles('finanzas_pagos') + """), 0) AS total FROM finanzas_pagos
            WHERE estado <> 'Anulado' AND fecha >= %s""" + sql_emp + " GROUP BY tipo", (inicio_mes,) + par_emp)
        mov = {m['tipo']: float(m['total']) for m in mov}

        def suma(lista, cond=lambda x: True):
            return round(sum(_saldo_soles(x) for x in lista if cond(x)), 2)

        return jsonify({'success': True, 'data': {
            'por_cobrar': suma(cxc),
            'por_cobrar_vencido': suma(cxc, lambda x: x['semaforo'] == 'Vencido'),
            'por_cobrar_7dias': suma(cxc, lambda x: x['semaforo'] == 'Por vencer'),
            'documentos_por_cobrar': sum(1 for x in cxc if x['saldo'] > 0),
            'por_pagar': suma(cxp),
            'por_pagar_vencido': suma(cxp, lambda x: x['semaforo'] == 'Vencido'),
            'por_pagar_7dias': suma(cxp, lambda x: x['semaforo'] == 'Por vencer'),
            'documentos_por_pagar': sum(1 for x in cxp if x['saldo'] > 0),
            'cobrado_mes': round(mov.get('COBRO', 0), 2),
            'pagado_mes': round(mov.get('PAGO', 0), 2),
            'posicion_neta': round(suma(cxc) - suma(cxp), 2),
        }})
    except Exception as e:
        print(f"❌ Error en finanzas api_resumen: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def _filtrar(lista):
    estado = (request.args.get('estado') or 'pendientes').lower()
    q = (request.args.get('q') or '').strip().lower()
    if estado == 'pendientes':
        lista = [x for x in lista if x['saldo'] > 0]
    elif estado in ('vencido', 'por vencer', 'al día', 'pagado'):
        lista = [x for x in lista if x['semaforo'].lower() == estado]
    if q:
        lista = [x for x in lista if q in (x.get('tercero') or '').lower() or q in (x.get('ruc') or '')
                 or q in (x.get('documento') or '').lower() or q in (x.get('retencion_numero') or '').lower()]
    return lista


@finanzas_bp.route('/finanzas/api/cxc', methods=['GET'])
def api_cxc():
    try:
        incluir = request.args.get('incluir_borradores', 'false').lower() == 'true'
        todas = _cuentas('cxc', incluir)
        return jsonify({'success': True, 'data': _filtrar(todas), 'totales': totales_cxp(todas)})
    except Exception as e:
        print(f"❌ Error en finanzas api_cxc: {e}")
        return jsonify({'success': False, 'error': str(e), 'data': []}), 500


ORDEN_SEMAFORO_CXP = {'Vencido': 0, 'Por vencer': 1, 'Al día': 2, 'Pagado': 3}


def ordenar_cxp(lista):
    """Cuentas por pagar ordenadas como pidió Erika: primero lo vencido (más días de atraso arriba),
    luego lo que vence pronto (menos días que faltan arriba), luego al día y al final lo pagado."""
    hoy = date.today()
    for x in lista:
        venc = x.get('fecha_vencimiento')
        try:
            dv = datetime.strptime(str(venc)[:10], '%Y-%m-%d').date() if venc else None
        except ValueError:
            dv = None
        x['dias_para_vencer'] = (dv - hoy).days if dv and x['semaforo'] in ('Por vencer', 'Al día') else None
        x['condicion'] = 'Crédito' if (x.get('dias_credito') or 0) > 0 or 'crédito' in str(x.get('condicion_pago') or '').lower() \
            or 'credito' in str(x.get('condicion_pago') or '').lower() else 'Contado'
    clave = lambda x: (ORDEN_SEMAFORO_CXP.get(x['semaforo'], 9),
                       -(x.get('dias_vencido') or 0) if x['semaforo'] == 'Vencido' else (x.get('dias_para_vencer') or 0) if x['semaforo'] != 'Pagado' else 0,
                       str(x.get('fecha_vencimiento') or ''))
    return sorted(lista, key=clave)


def _saldo_soles(x):
    """Saldo en soles (los documentos en dólares, con su tipo de cambio)."""
    v = x.get('saldo_soles')
    return x['saldo'] if v is None and x.get('moneda', 'PEN') == 'PEN' else (v or 0)


def totales_cxp(lista):
    def suma(cond):
        return round(sum(_saldo_soles(x) for x in lista if cond(x)), 2)
    usd = round(sum(x['saldo'] for x in lista if x.get('moneda') == 'USD'), 2)
    return {
            'usd': usd, 'docs_usd': sum(1 for x in lista if x.get('moneda') == 'USD' and x['saldo'] > 0),'vencido': suma(lambda x: x['semaforo'] == 'Vencido'),
            'por_vencer': suma(lambda x: x['semaforo'] == 'Por vencer'),
            'al_dia': suma(lambda x: x['semaforo'] == 'Al día'),
            'total': suma(lambda x: True),
            'docs_vencidos': sum(1 for x in lista if x['semaforo'] == 'Vencido'),
            'docs_por_vencer': sum(1 for x in lista if x['semaforo'] == 'Por vencer'),
            'docs_al_dia': sum(1 for x in lista if x['semaforo'] == 'Al día'),
            'docs_total': sum(1 for x in lista if x['saldo'] > 0)}


@finanzas_bp.route('/finanzas/api/cxp', methods=['GET'])
def api_cxp():
    try:
        todas = _cuentas('cxp')
        return jsonify({'success': True, 'data': ordenar_cxp(_filtrar(todas)), 'totales': totales_cxp(todas)})
    except Exception as e:
        print(f"❌ Error en finanzas api_cxp: {e}")
        return jsonify({'success': False, 'error': str(e), 'data': []}), 500


@finanzas_bp.route('/finanzas/api/movimientos', methods=['GET'])
def api_movimientos():
    try:
        asegurar_tablas_finanzas()
        tipo = (request.args.get('tipo') or '').upper()
        q = (request.args.get('q') or '').strip()
        sql_emp, par_emp = filtro_sql('fp.empresa_id')
        # Trazabilidad (Erika 22/10/2026 12:26): cada cobro/pago con su N° OC y N° PV, igual que en CxC/CxP.
        # Pagos: N° OC + N° PV (o "Compra a stock"). Cobros: N° PV + N° PC (Pedido del cliente).
        sql = """
            SELECT fp.*, x.oc_numero, x.pc_numero, x.oc_cliente, x.tipo_compra, x.total_documento, x.ret_factura,
                   sg.retencion_numero, sg.retencion_fecha, sg.retencion_monto
            FROM finanzas_pagos fp
            LEFT JOIN finanzas_seguimiento_cobro sg ON fp.tipo = 'COBRO' AND fp.documento_tabla = 'comprobantes'
                                                   AND sg.comprobante_id = fp.documento_id
            LEFT JOIN LATERAL (
                SELECT COALESCE(cp.orden_compra_numero, ocp.numero_orden, oca.numero_orden) AS oc_numero,
                       COALESCE(NULLIF(c.pc_vinculado, ''), NULLIF(COALESCE(ocp.pc_numeros, oca.pc_numeros), ''),
                                (SELECT string_agg(DISTINCT i.pedido_numero, ', ') FROM ordenes_compra_items i
                                  WHERE i.orden_compra_id = COALESCE(ocp.id, oca.id) AND COALESCE(i.pedido_numero, '') <> '')) AS pc_numero,
                       NULLIF(c.orden_compra_cliente, '') AS oc_cliente,
                       COALESCE(ocp.tipo_compra, oca.tipo_compra) AS tipo_compra,
                       COALESCE(c.total, cp.monto, oca.total) AS total_documento,
                       NULLIF(COALESCE(c.monto_retenido, 0), 0) AS ret_factura
                FROM (SELECT 1) uno
                LEFT JOIN comprobantes c ON fp.documento_tabla = 'comprobantes' AND c.id = fp.documento_id
                LEFT JOIN comprobantes_proveedor cp ON fp.documento_tabla = 'comprobantes_proveedor' AND cp.id = fp.documento_id
                LEFT JOIN ordenes_compra ocp ON ocp.id = cp.orden_compra_id
                LEFT JOIN ordenes_compra oca ON fp.documento_tabla = 'ordenes_compra' AND oca.id = fp.documento_id
            ) x ON TRUE
            WHERE TRUE""" + sql_emp
        params = list(par_emp)
        if tipo in ('COBRO', 'PAGO'):
            sql += " AND fp.tipo = %s"
            params.append(tipo)
        if q:
            # Buscador: documento, cliente / proveedor, RUC, N.º de operación, banco, N° OC o N° PV
            sql += (" AND (fp.documento_numero ILIKE %s OR fp.tercero_nombre ILIKE %s OR fp.tercero_documento ILIKE %s"
                    " OR fp.numero_operacion ILIKE %s OR fp.banco ILIKE %s OR x.oc_numero ILIKE %s OR x.pc_numero ILIKE %s"
                    " OR x.oc_cliente ILIKE %s)")
            params += [f'%{q}%'] * 8
        sql += " ORDER BY fp.fecha DESC, fp.id DESC LIMIT 500"
        filas = db_query(sql, params)
        data = []
        for f in filas:
            item = {k: _fmt(v) for k, v in f.items()}
            item['monto'] = float(f['monto'])
            item['total_documento'] = float(f['total_documento']) if f.get('total_documento') is not None else None
            if f.get('retencion_monto') is None and f.get('ret_factura') is not None and f['tipo'] == 'COBRO':
                f['retencion_monto'] = f['ret_factura']   # la de la factura (3%) mientras no se anote la real
            if f.get('retencion_monto') is not None:
                item['retencion_monto'] = float(f['retencion_monto'])
            if f['tipo'] == 'PAGO' and not f.get('pc_numero') and f.get('oc_numero'):
                item['pc_numero'] = 'Compra a stock' if 'stock' in str(f.get('tipo_compra') or '').lower() else 'Sin PV vinculado'
            data.append(item)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        print(f"❌ Error en finanzas api_movimientos: {e}")
        return jsonify({'success': False, 'error': str(e), 'data': []}), 500


@finanzas_bp.route('/finanzas/api/movimientos', methods=['POST'])
def api_registrar_movimiento():
    """Registra un cobro (CxC) o un pago (CxP). Valida que no supere el saldo pendiente."""
    if not puede_operar_finanzas():
        return jsonify({'success': False, 'error': 'No tienes permisos para registrar cobros o pagos'}), 403
    try:
        asegurar_tablas_finanzas()
        data = request.get_json(silent=True) or {}
        tipo = (data.get('tipo') or '').upper()
        if tipo not in ('COBRO', 'PAGO'):
            return jsonify({'success': False, 'error': 'Tipo inválido (COBRO o PAGO)'}), 400
        try:
            documento_id = int(data.get('documento_id'))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'Documento inválido'}), 400
        monto = redondear(data.get('monto_pagado') if data.get('monto_pagado') not in (None, '') else data.get('monto'))
        if monto <= 0:
            return jsonify({'success': False, 'error': 'El monto debe ser mayor a 0'}), 400
        try:
            fecha = datetime.strptime((data.get('fecha') or date.today().isoformat())[:10], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Fecha inválida'}), 400
        if fecha > date.today() + timedelta(days=1):
            return jsonify({'success': False, 'error': 'La fecha del movimiento no puede ser futura'}), 400
        metodo = data.get('metodo') or 'Transferencia'
        if metodo not in METODOS_PAGO:
            return jsonify({'success': False, 'error': 'Método de pago inválido'}), 400
        numero_operacion = (data.get('numero_operacion') or '').strip() or None
        fecha_aviso = None
        if (data.get('fecha_aviso') or '').strip():
            try:
                fecha_aviso = datetime.strptime(data['fecha_aviso'].strip()[:10], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'success': False, 'error': 'Fecha de aviso de pago inválida'}), 400
        if tipo == 'COBRO' and metodo in METODOS_CON_COMPROBANTE and not numero_operacion and not fecha_aviso:
            return jsonify({'success': False, 'error': 'Escribe el N.º de operación o la fecha de aviso de pago '
                                                       '(lo que haya mandado el cliente).'}), 400

        tabla = 'comprobantes' if tipo == 'COBRO' else 'comprobantes_proveedor'
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            # Bloquea el documento para que dos usuarios no registren el mismo saldo a la vez
            cur.execute(f"SELECT id FROM {tabla} WHERE id = %s FOR UPDATE", (documento_id,))
            if not cur.fetchone():
                return jsonify({'success': False, 'error': 'Documento no encontrado'}), 404
            sql = (SQL_CXC if tipo == 'COBRO' else SQL_CXP) + (" AND c.id = %s" if tipo == 'COBRO' else " AND cp.id = %s")
            cur.execute(sql, (documento_id,))
            doc = cur.fetchone()
            if not doc:
                return jsonify({'success': False, 'error': 'El documento está anulado'}), 409
            if tipo == 'COBRO' and (doc['estado_documento'] or '').upper() == 'BORRADOR':
                return jsonify({'success': False, 'error': 'El comprobante está en borrador: emítelo antes de registrar cobros'}), 409
            saldo = redondear(a_decimal(doc['importe_cobrar']) - a_decimal(doc['cobrado']) - a_decimal(doc['notas_credito']))
            if saldo <= 0:
                return jsonify({'success': False, 'error': 'El documento ya no tiene saldo pendiente'}), 409
            # 24/10/2026 (Erika): documento en dólares pagado/cobrado en soles con el TC (o al revés)
            doc_moneda = codigo_moneda(doc.get('moneda'))
            try:
                monto, moneda_pago, tc_pago, monto_pagado = pago_en_moneda(doc_moneda, data, doc.get('empresa_doc'))
            except ErrorMoneda as em:
                return jsonify({'success': False, 'error': str(em)}), 400
            sim = simbolo(doc_moneda)
            if moneda_pago != doc_moneda and Decimal('0') < monto - saldo <= Decimal('0.02'):
                monto = saldo     # redondeo del tipo de cambio
            if monto > saldo:
                return jsonify({'success': False,
                                'error': f'El monto ({sim} {monto:.2f}) supera el saldo pendiente ({sim} {saldo:.2f})'}), 400
            cur.execute("""
                INSERT INTO finanzas_pagos (tipo, documento_tabla, documento_id, documento_numero, tercero_nombre,
                    tercero_documento, fecha, monto, metodo, banco, numero_operacion, fecha_aviso, observaciones,
                    usuario_id, usuario_nombre)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (tipo, tabla, documento_id, doc['documento'], doc['tercero'], doc['ruc'], fecha, monto, metodo,
                  normalizar_banco(data.get('banco')), numero_operacion, fecha_aviso,
                  (data.get('observaciones') or '').strip() or None,
                  session.get('usuario_id'), session.get('nombre_completo')))
            nuevo_id = cur.fetchone()['id']
            # El cobro/pago queda en la empresa del documento
            cur.execute(f"""UPDATE finanzas_pagos SET empresa_id = (SELECT empresa_id FROM {tabla} WHERE id = %s),
                               moneda_pago = %s, tipo_cambio = %s, monto_pagado = %s WHERE id = %s""",
                        (documento_id, moneda_pago, tc_pago, monto_pagado, nuevo_id))
            saldo_final = saldo - monto
            if saldo_final <= 0:
                if tipo == 'COBRO':
                    cur.execute("UPDATE comprobantes SET estado_sunat = 'Pagado', updated_at = NOW() WHERE id = %s",
                                (documento_id,))
                else:
                    cur.execute("UPDATE comprobantes_proveedor SET estado = 'Pagado', updated_at = NOW() WHERE id = %s",
                                (documento_id,))
        return jsonify({'success': True,
                        'message': f"{'Cobro' if tipo == 'COBRO' else 'Pago'} registrado. Saldo pendiente: {sim} {saldo_final:.2f}",
                        'data': {'id': nuevo_id, 'saldo': float(saldo_final)}})
    except Exception as e:
        print(f"❌ Error registrando movimiento: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@finanzas_bp.route('/finanzas/api/movimientos/<int:mov_id>/anular', methods=['POST'])
def api_anular_movimiento(mov_id):
    if not puede_operar_finanzas():
        return jsonify({'success': False, 'error': 'No tienes permisos para anular movimientos'}), 403
    try:
        asegurar_tablas_finanzas()
        data = request.get_json(silent=True) or {}
        motivo = (data.get('motivo') or '').strip()
        if not motivo:
            return jsonify({'success': False, 'error': 'El motivo de anulación es obligatorio'}), 400
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM finanzas_pagos WHERE id = %s FOR UPDATE", (mov_id,))
            mov = cur.fetchone()
            if not mov:
                return jsonify({'success': False, 'error': 'Movimiento no encontrado'}), 404
            if mov['estado'] == 'Anulado':
                return jsonify({'success': False, 'error': 'El movimiento ya estaba anulado'}), 409
            cur.execute("""UPDATE finanzas_pagos SET estado = 'Anulado', anulado_por = %s, anulado_en = NOW(),
                           motivo_anulacion = %s WHERE id = %s""", (session.get('usuario_id'), motivo, mov_id))
            # Si el documento estaba marcado como pagado, vuelve a quedar pendiente
            if mov['documento_tabla'] == 'comprobantes':
                cur.execute("""UPDATE comprobantes SET estado_sunat = 'Emitido', updated_at = NOW()
                               WHERE id = %s AND estado_sunat = 'Pagado'""", (mov['documento_id'],))
            elif mov['documento_tabla'] == 'comprobantes_proveedor':
                cur.execute("""UPDATE comprobantes_proveedor SET estado = 'Pendiente', updated_at = NOW()
                               WHERE id = %s AND estado = 'Pagado'""", (mov['documento_id'],))
        return jsonify({'success': True, 'message': 'Movimiento anulado'})
    except Exception as e:
        print(f"❌ Error anulando movimiento: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@finanzas_bp.route('/finanzas/api/cxp/<int:cp_id>/vencimiento', methods=['PUT'])
def api_cxp_vencimiento(cp_id):
    if not puede_operar_finanzas():
        return jsonify({'success': False, 'error': 'No tienes permisos para esta acción'}), 403
    try:
        asegurar_tablas_finanzas()
        data = request.get_json(silent=True) or {}
        try:
            fecha = datetime.strptime((data.get('fecha_vencimiento') or '')[:10], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Fecha de vencimiento inválida'}), 400
        doc = db_query("SELECT fecha FROM comprobantes_proveedor WHERE id = %s", (cp_id,))
        if not doc:
            return jsonify({'success': False, 'error': 'Comprobante no encontrado'}), 404
        error = error_vencimiento(doc[0]['fecha'], fecha)
        if error:
            return jsonify({'success': False, 'error': error}), 400
        db_query("UPDATE comprobantes_proveedor SET fecha_vencimiento = %s, updated_at = NOW() "
                 "WHERE id = %s RETURNING id", (fecha, cp_id))
        return jsonify({'success': True, 'message': 'Fecha de vencimiento actualizada'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# Vencimientos absurdos (ej. 25/04/2136 por "Crédito 40000 días"): no se aceptan. Los clientes llegan a 360 días.
MAX_DIAS_CREDITO = 400


def error_vencimiento(emision, vencimiento):
    """Mensaje si el vencimiento no tiene sentido; None si está bien."""
    if isinstance(emision, datetime):
        emision = emision.date()
    if not emision or not vencimiento:
        return None
    if vencimiento < emision:
        return 'El vencimiento no puede ser antes de la fecha de emisión de la factura.'
    if (vencimiento - emision).days > MAX_DIAS_CREDITO:
        return (f'El vencimiento no puede ser más de {MAX_DIAS_CREDITO} días después de la emisión '
                f'({emision.strftime("%d/%m/%Y")}). Revisa el año.')
    return None


@finanzas_bp.route('/finanzas/api/comentario', methods=['POST'])
def api_comentario():
    """Comentario de Finanzas en una factura por cobrar o por pagar (no cambia el documento)."""
    if not puede_operar_finanzas():
        return jsonify({'success': False, 'error': 'No tienes permisos para esta acción'}), 403
    data = request.get_json(silent=True) or {}
    tabla = {'cxc': 'comprobantes', 'cxp': 'comprobantes_proveedor'}.get(str(data.get('tipo') or '').lower())
    try:
        doc_id = int(data.get('id'))
    except (TypeError, ValueError):
        doc_id = None
    if not tabla or not doc_id:
        return jsonify({'success': False, 'error': 'Documento inválido'}), 400
    texto = ' '.join(str(data.get('comentario') or '').split())[:500]
    if texto:
        texto = texto[0].upper() + texto[1:]
    usuario = session.get('nombre') or session.get('usuario') or ''
    try:
        asegurar_tablas_finanzas()
        if not db_query(f"SELECT id FROM {tabla} WHERE id = %s", (doc_id,)):
            return jsonify({'success': False, 'error': 'Documento no encontrado'}), 404
        db_execute("""INSERT INTO finanzas_comentarios (documento_tabla, documento_id, comentario, usuario_nombre, updated_at)
                      VALUES (%s, %s, %s, %s, NOW())
                      ON CONFLICT (documento_tabla, documento_id) DO UPDATE
                      SET comentario = EXCLUDED.comentario, usuario_nombre = EXCLUDED.usuario_nombre, updated_at = NOW()""",
                   (tabla, doc_id, texto or None, usuario))
        return jsonify({'success': True, 'comentario': texto, 'message': 'Comentario guardado'})
    except Exception as e:
        print(f"❌ Error guardando comentario de finanzas: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def _fecha_o_nada(valor, nombre):
    texto = str(valor or '').strip()
    if not texto:
        return None
    try:
        return date.fromisoformat(texto[:10])
    except ValueError:
        raise ValueError(f'{nombre}: fecha no válida')


def _retencion_de(data, doc):
    """N°, fecha y monto del comprobante de retención que envía el cliente (Erika 23/10 y 26/10/2026)."""
    from routes.exportar import ahora_lima
    numero = ' '.join(str(data.get('retencion_numero') or '').split()).upper()[:40] or None
    fecha_ret = _fecha_o_nada(data.get('retencion_fecha'), 'Fecha de la retención')
    monto_txt = str(data.get('retencion_monto') if data.get('retencion_monto') is not None else '').strip()
    monto = None
    if monto_txt:
        monto = redondear(a_decimal(monto_txt))
        if monto < 0 or monto > a_decimal(doc['total']):
            raise ValueError('El monto de la retención debe estar entre 0 y el total de la factura')
    emision = doc.get('fecha_emision')
    if isinstance(emision, datetime):
        emision = emision.date()
    if fecha_ret and emision and fecha_ret < emision:
        raise ValueError('La fecha de la retención no puede ser antes de la emisión de la factura')
    if fecha_ret and fecha_ret > ahora_lima().date():
        raise ValueError('La fecha de la retención no puede ser futura')
    return numero, fecha_ret, monto


@finanzas_bp.route('/finanzas/api/retencion_cobro', methods=['POST'])
def api_retencion_cobro():
    """Solo el comprobante de retención (al registrar el cobro): no toca portal ni fecha programada."""
    if not puede_operar_finanzas():
        return jsonify({'success': False, 'error': 'No tienes permisos para esta acción'}), 403
    data = request.get_json(silent=True) or {}
    try:
        doc_id = int(data.get('id'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Documento inválido'}), 400
    try:
        asegurar_tablas_finanzas()
        doc = db_query("SELECT id, serie, numero, fecha_emision, COALESCE(total, 0) AS total FROM comprobantes WHERE id = %s",
                       (doc_id,))
        if not doc:
            return jsonify({'success': False, 'error': 'Factura no encontrada'}), 404
        numero, fecha_ret, monto = _retencion_de(data, doc[0])
        antes = db_query("SELECT retencion_numero, retencion_fecha, retencion_monto FROM finanzas_seguimiento_cobro "
                         "WHERE comprobante_id = %s", (doc_id,))
        db_execute("""INSERT INTO finanzas_seguimiento_cobro (comprobante_id, retencion_numero, retencion_fecha, retencion_monto,
                                                          usuario_nombre, updated_at)
                      VALUES (%s, %s, %s, %s, %s, NOW())
                      ON CONFLICT (comprobante_id) DO UPDATE SET retencion_numero = EXCLUDED.retencion_numero,
                          retencion_fecha = EXCLUDED.retencion_fecha, retencion_monto = EXCLUDED.retencion_monto,
                          usuario_nombre = EXCLUDED.usuario_nombre, updated_at = NOW()""",
                   (doc_id, numero, fecha_ret, monto, session.get('nombre') or session.get('usuario') or ''))
        despues = {'retencion_numero': numero, 'retencion_fecha': _fmt(fecha_ret),
                   'retencion_monto': float(monto) if monto is not None else None}
        try:
            from routes.auditoria import registrar_auditoria
            registrar_auditoria('ACTUALIZAR', 'Finanzas', 'finanzas_seguimiento_cobro', doc_id,
                                antes={k: _fmt(v) for k, v in antes[0].items()} if antes else None, despues=despues,
                                detalle=f"Retención de {doc[0].get('serie') or ''}-{doc[0].get('numero') or doc_id}")
        except Exception as e:
            print(f"⚠️ Auditoría de retención: {e}")
        return jsonify({'success': True, 'data': despues, 'message': 'Retención guardada'})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@finanzas_bp.route('/finanzas/api/seguimiento_cobro', methods=['POST'])
def api_seguimiento_cobro():
    """Seguimiento de una factura por cobrar (Erika 23/10/2026): si ya se ingresó en el portal del cliente,
    la fecha programada de pago y el comprobante de retención del 3% (N° y monto). No cambia la factura."""
    if not puede_operar_finanzas():
        return jsonify({'success': False, 'error': 'No tienes permisos para esta acción'}), 403
    data = request.get_json(silent=True) or {}
    try:
        doc_id = int(data.get('id'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Documento inválido'}), 400
    try:
        asegurar_tablas_finanzas()
        doc = db_query("SELECT id, serie, numero, fecha_emision, COALESCE(total, 0) AS total FROM comprobantes WHERE id = %s",
                       (doc_id,))
        if not doc:
            return jsonify({'success': False, 'error': 'Factura no encontrada'}), 404
        doc = doc[0]
        portal = bool(data.get('portal_ingresado'))
        portal_fecha = _fecha_o_nada(data.get('portal_fecha'), 'Fecha de ingreso al portal') if portal else None
        programada = _fecha_o_nada(data.get('fecha_programada'), 'Fecha programada de pago')
        numero_ret, fecha_ret, monto_ret = _retencion_de(data, doc)
        emision = doc.get('fecha_emision')
        if isinstance(emision, datetime):
            emision = emision.date()
        if programada and emision and programada < emision:
            return jsonify({'success': False, 'error': 'La fecha programada de pago no puede ser antes de la emisión de la factura'}), 400
        usuario = session.get('nombre') or session.get('usuario') or ''
        # N° MIGO / conformidad (25/10/2026): se guarda en la factura; se puede anotar después de emitirla
        migo_antes = None
        if 'numero_migo' in data:
            from routes.migo import limpiar_migo
            migo_antes = (db_query("SELECT numero_migo FROM comprobantes WHERE id = %s", (doc_id,)) or [{}])[0].get('numero_migo')
            db_execute("UPDATE comprobantes SET numero_migo = %s WHERE id = %s", (limpiar_migo(data.get('numero_migo')), doc_id))
        antes = db_query("SELECT * FROM finanzas_seguimiento_cobro WHERE comprobante_id = %s", (doc_id,))
        db_execute("""INSERT INTO finanzas_seguimiento_cobro
                          (comprobante_id, portal_ingresado, portal_fecha, fecha_programada, retencion_numero, retencion_monto,
                           usuario_nombre, updated_at, retencion_fecha)
                      VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s)
                      ON CONFLICT (comprobante_id) DO UPDATE SET
                          portal_ingresado = EXCLUDED.portal_ingresado, portal_fecha = EXCLUDED.portal_fecha,
                          fecha_programada = EXCLUDED.fecha_programada, retencion_numero = EXCLUDED.retencion_numero,
                          retencion_monto = EXCLUDED.retencion_monto, usuario_nombre = EXCLUDED.usuario_nombre, updated_at = NOW(),
                          retencion_fecha = EXCLUDED.retencion_fecha""",
                   (doc_id, portal, portal_fecha, programada, numero_ret, monto_ret, usuario, fecha_ret))
        despues = {'portal_ingresado': portal, 'portal_fecha': _fmt(portal_fecha), 'fecha_programada': _fmt(programada),
                   'retencion_numero': numero_ret, 'retencion_fecha': _fmt(fecha_ret),
                   'retencion_monto': float(monto_ret) if monto_ret is not None else None}
        if 'numero_migo' in data:
            from routes.migo import limpiar_migo
            despues['numero_migo'] = limpiar_migo(data.get('numero_migo'))
        try:
            from routes.auditoria import registrar_auditoria
            registrar_auditoria('ACTUALIZAR', 'Finanzas', 'finanzas_seguimiento_cobro', doc_id,
                                antes=({k: _fmt(v) for k, v in (antes[0].items() if antes else [])
                                        if k in despues} | ({'numero_migo': migo_antes} if 'numero_migo' in data else {})) or None,
                                despues=despues,
                                detalle=f"Seguimiento de cobro de {doc.get('serie') or ''}-{doc.get('numero') or doc_id}")
        except Exception as e:
            print(f"⚠️ Auditoría de seguimiento de cobro: {e}")
        return jsonify({'success': True, 'data': despues, 'message': 'Seguimiento guardado'})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        print(f"❌ Error guardando seguimiento de cobro: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@finanzas_bp.route('/finanzas/api/flujo', methods=['GET'])
def api_flujo():
    """Flujo de caja proyectado por semana con los saldos pendientes de CxC y CxP."""
    try:
        try:
            semanas = max(1, min(int(request.args.get('semanas', 8)), 26))
        except ValueError:
            semanas = 8
        hoy = date.today()
        inicio = hoy - timedelta(days=hoy.weekday())  # lunes de esta semana
        filas = [{'periodo': 'Vencido (antes de hoy)', 'desde': None, 'hasta': (hoy - timedelta(days=1)).isoformat(),
                  'ingresos': 0.0, 'egresos': 0.0}]
        for i in range(semanas):
            d = inicio + timedelta(weeks=i)
            filas.append({'periodo': f"Semana del {d.strftime('%d/%m')}", 'desde': d.isoformat(),
                          'hasta': (d + timedelta(days=6)).isoformat(), 'ingresos': 0.0, 'egresos': 0.0})
        filas.append({'periodo': 'Posterior', 'desde': (inicio + timedelta(weeks=semanas)).isoformat(), 'hasta': None,
                      'ingresos': 0.0, 'egresos': 0.0})

        def ubicar(venc):
            if not venc:
                return 1
            v = date.fromisoformat(str(venc)[:10])
            if v < hoy:
                return 0
            idx = (v - inicio).days // 7 + 1
            return min(idx, len(filas) - 1)

        for x in _cuentas('cxc'):
            if x['saldo'] > 0:
                filas[ubicar(x['fecha_vencimiento'])]['ingresos'] += _saldo_soles(x)
        for x in _cuentas('cxp'):
            if x['saldo'] > 0:
                filas[ubicar(x['fecha_vencimiento'])]['egresos'] += _saldo_soles(x)
        acumulado = 0.0
        for f in filas:
            f['ingresos'] = round(f['ingresos'], 2)
            f['egresos'] = round(f['egresos'], 2)
            f['neto'] = round(f['ingresos'] - f['egresos'], 2)
            acumulado += f['neto']
            f['acumulado'] = round(acumulado, 2)
        return jsonify({'success': True, 'data': filas})
    except Exception as e:
        print(f"❌ Error en finanzas api_flujo: {e}")
        return jsonify({'success': False, 'error': str(e), 'data': []}), 500
