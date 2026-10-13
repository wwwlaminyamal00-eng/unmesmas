# routes/finanzas.py - Módulo de Finanzas / Tesorería
#
# Trabaja sobre los documentos que YA existen en el ERP:
#   - Cuentas por cobrar (CxC): comprobantes de venta (tabla comprobantes)
#   - Cuentas por pagar (CxP): comprobantes de proveedor (tabla comprobantes_proveedor)
# y agrega una sola tabla nueva, finanzas_pagos, para registrar cobros y pagos
# (parciales o totales) con trazabilidad de usuario. No modifica ni borra datos existentes.
import os
import threading
from datetime import date, datetime, timedelta

from flask import Blueprint, render_template, request, jsonify, session
from psycopg2.extras import RealDictCursor

from database import db_query, db_execute, db_tx
from utils import a_decimal, redondear, es_admin, es_aprobador

finanzas_bp = Blueprint('finanzas', __name__)

ROLES_FINANZAS = {r.strip().lower() for r in os.environ.get(
    'ROLES_FINANZAS', 'finanzas,contabilidad,tesoreria,gerencia').split(',') if r.strip()}

METODOS_PAGO = ('Transferencia', 'Depósito', 'Efectivo', 'Cheque', 'Yape/Plin', 'Detracción', 'Otro')

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
        SELECT documento_id, SUM(monto) AS cobrado
        FROM finanzas_pagos
        WHERE documento_tabla = 'comprobantes' AND tipo = 'COBRO' AND estado <> 'Anulado'
        GROUP BY documento_id
    ),
    nc AS (
        SELECT comprobante_asociado, SUM(monto) AS monto_nc
        FROM notas_credito
        WHERE COALESCE(UPPER(estado), '') NOT IN ('ANULADA', 'ANULADO', 'BORRADOR')
        GROUP BY comprobante_asociado
    )
    SELECT c.id, c.tipo_comprobante, c.serie, c.numero,
           COALESCE(c.serie, '') || '-' || COALESCE(c.numero, '') AS documento,
           c.cliente_nombre AS tercero, c.cliente_numero_doc AS ruc,
           c.fecha_emision, c.condicion_pago, c.es_credito, c.dias_credito,
           COALESCE(c.fecha_vencimiento::date,
                    c.fecha_emision::date + COALESCE(c.dias_credito, 0)) AS fecha_vencimiento,
           COALESCE(c.total, 0) AS total,
           COALESCE(c.monto_retenido, 0) AS retencion,
           COALESCE(NULLIF(c.monto_a_pagar, 0), c.total, 0) AS importe_cobrar,
           COALESCE(cb.cobrado, 0) AS cobrado,
           COALESCE(nc.monto_nc, 0) AS notas_credito,
           COALESCE(c.estado_sunat, 'Borrador') AS estado_documento
    FROM comprobantes c
    LEFT JOIN cobros cb ON cb.documento_id = c.id
    LEFT JOIN nc ON nc.comprobante_asociado IN (c.numero, COALESCE(c.serie, '') || '-' || COALESCE(c.numero, ''))
    WHERE COALESCE(UPPER(c.estado_sunat), '') NOT IN ('ANULADO', 'ANULADA')
"""

SQL_CXP = """
    WITH pagos AS (
        SELECT documento_id, SUM(monto) AS pagado
        FROM finanzas_pagos
        WHERE documento_tabla = 'comprobantes_proveedor' AND tipo = 'PAGO' AND estado <> 'Anulado'
        GROUP BY documento_id
    )
    SELECT cp.id, cp.tipo AS tipo_comprobante, NULL AS serie, cp.numero,
           cp.numero AS documento,
           cp.proveedor_nombre AS tercero, cp.ruc_proveedor AS ruc,
           cp.fecha AS fecha_emision, oc.condicion_pago, NULL::boolean AS es_credito,
           NULLIF(regexp_replace(COALESCE(oc.condicion_pago, ''), '\\D', '', 'g'), '')::int AS dias_credito,
           COALESCE(cp.fecha_vencimiento,
                    cp.fecha::date + COALESCE(NULLIF(regexp_replace(COALESCE(oc.condicion_pago, ''), '\\D', '', 'g'), '')::int, 0)
           ) AS fecha_vencimiento,
           COALESCE(cp.monto, 0) AS total,
           0 AS retencion,
           COALESCE(cp.monto, 0) AS importe_cobrar,
           COALESCE(pg.pagado, 0) AS cobrado,
           0 AS notas_credito,
           COALESCE(cp.estado, 'Pendiente') AS estado_documento,
           COALESCE(cp.orden_compra_numero, oc.numero_orden) AS orden_compra
    FROM comprobantes_proveedor cp
    LEFT JOIN pagos pg ON pg.documento_id = cp.id
    LEFT JOIN ordenes_compra oc ON oc.id = cp.orden_compra_id
    WHERE COALESCE(UPPER(cp.estado), '') NOT IN ('ANULADO', 'ANULADA')
"""


def _cuentas(tipo, incluir_borradores=False):
    asegurar_tablas_finanzas()
    sql = SQL_CXC if tipo == 'cxc' else SQL_CXP
    if tipo == 'cxc' and not incluir_borradores:
        sql += " AND COALESCE(UPPER(c.estado_sunat), 'BORRADOR') <> 'BORRADOR'"
    filas = db_query(sql + " ORDER BY 1 DESC")
    hoy = date.today()
    resultado = []
    for f in filas:
        importe = a_decimal(f['importe_cobrar'])
        abonado = a_decimal(f['cobrado']) + a_decimal(f['notas_credito'])
        saldo = redondear(importe - abonado)
        if saldo < 0:
            saldo = a_decimal(0)
        venc = f.get('fecha_vencimiento')
        semaforo = _semaforo(saldo, venc, hoy)
        dias_vencido = (hoy - (venc.date() if isinstance(venc, datetime) else venc)).days if venc and semaforo == 'Vencido' else 0
        item = {k: _fmt(v) for k, v in f.items()}
        item.update({
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
        mov = db_query("""
            SELECT tipo, COALESCE(SUM(monto), 0) AS total FROM finanzas_pagos
            WHERE estado <> 'Anulado' AND fecha >= %s GROUP BY tipo
        """, (inicio_mes,))
        mov = {m['tipo']: float(m['total']) for m in mov}

        def suma(lista, cond=lambda x: True):
            return round(sum(x['saldo'] for x in lista if cond(x)), 2)

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
                 or q in (x.get('documento') or '').lower()]
    return lista


@finanzas_bp.route('/finanzas/api/cxc', methods=['GET'])
def api_cxc():
    try:
        incluir = request.args.get('incluir_borradores', 'false').lower() == 'true'
        return jsonify({'success': True, 'data': _filtrar(_cuentas('cxc', incluir))})
    except Exception as e:
        print(f"❌ Error en finanzas api_cxc: {e}")
        return jsonify({'success': False, 'error': str(e), 'data': []}), 500


@finanzas_bp.route('/finanzas/api/cxp', methods=['GET'])
def api_cxp():
    try:
        return jsonify({'success': True, 'data': _filtrar(_cuentas('cxp'))})
    except Exception as e:
        print(f"❌ Error en finanzas api_cxp: {e}")
        return jsonify({'success': False, 'error': str(e), 'data': []}), 500


@finanzas_bp.route('/finanzas/api/movimientos', methods=['GET'])
def api_movimientos():
    try:
        asegurar_tablas_finanzas()
        tipo = (request.args.get('tipo') or '').upper()
        sql = "SELECT * FROM finanzas_pagos"
        params = []
        if tipo in ('COBRO', 'PAGO'):
            sql += " WHERE tipo = %s"
            params.append(tipo)
        sql += " ORDER BY fecha DESC, id DESC LIMIT 500"
        filas = db_query(sql, params)
        data = []
        for f in filas:
            item = {k: _fmt(v) for k, v in f.items()}
            item['monto'] = float(f['monto'])
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
        monto = redondear(data.get('monto'))
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
            if monto > saldo:
                return jsonify({'success': False,
                                'error': f'El monto (S/ {monto:.2f}) supera el saldo pendiente (S/ {saldo:.2f})'}), 400
            cur.execute("""
                INSERT INTO finanzas_pagos (tipo, documento_tabla, documento_id, documento_numero, tercero_nombre,
                    tercero_documento, fecha, monto, metodo, banco, numero_operacion, observaciones,
                    usuario_id, usuario_nombre)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (tipo, tabla, documento_id, doc['documento'], doc['tercero'], doc['ruc'], fecha, monto, metodo,
                  (data.get('banco') or '').strip() or None, (data.get('numero_operacion') or '').strip() or None,
                  (data.get('observaciones') or '').strip() or None,
                  session.get('usuario_id'), session.get('nombre_completo')))
            nuevo_id = cur.fetchone()['id']
            saldo_final = saldo - monto
            if saldo_final <= 0:
                if tipo == 'COBRO':
                    cur.execute("UPDATE comprobantes SET estado_sunat = 'Pagado', updated_at = NOW() WHERE id = %s",
                                (documento_id,))
                else:
                    cur.execute("UPDATE comprobantes_proveedor SET estado = 'Pagado', updated_at = NOW() WHERE id = %s",
                                (documento_id,))
        return jsonify({'success': True,
                        'message': f"{'Cobro' if tipo == 'COBRO' else 'Pago'} registrado. Saldo pendiente: S/ {saldo_final:.2f}",
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
        r = db_query("UPDATE comprobantes_proveedor SET fecha_vencimiento = %s, updated_at = NOW() "
                     "WHERE id = %s RETURNING id", (fecha, cp_id))
        if not r:
            return jsonify({'success': False, 'error': 'Comprobante no encontrado'}), 404
        return jsonify({'success': True, 'message': 'Fecha de vencimiento actualizada'})
    except Exception as e:
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
                filas[ubicar(x['fecha_vencimiento'])]['ingresos'] += x['saldo']
        for x in _cuentas('cxp'):
            if x['saldo'] > 0:
                filas[ubicar(x['fecha_vencimiento'])]['egresos'] += x['saldo']
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
