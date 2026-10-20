# routes/stock_automatico.py - Ventas, Compras, Inventario y Caja unidos (pedido de Erika, 15/10/2026)
#
# Reglas (en simple):
#   1. Al DESPACHAR una venta se descuenta el stock de la empresa y la sede que elige quien despacha.
#      Cada producto queda en el kardex como "Entrega a cliente (venta)" con el número del despacho.
#      Puede usar lo separado para ESE cliente; lo separado para otros clientes no se toca.
#      Si falta stock de algún producto, no se despacha nada (todo o nada).
#   2. Al RECIBIR una compra (Compras > Recibir) lo bueno entra solo al inventario de la empresa de la OC,
#      en la sede donde se recibió y con el costo de la OC (sin IGV). Si la compra era para un pedido
#      del cliente, queda separado para ese cliente (nadie más lo puede vender).
#   3. Al ANULAR un despacho (o regresarlo a "Pendiente") el stock vuelve y la separación del cliente también.
#      Al ANULAR un comprobante de venta sus cobros en caja se anulan solos.
# Nada se borra: cada vuelta atrás es un movimiento nuevo de "Corrección (reversa)" en el kardex.
import json
from datetime import date, timedelta
from decimal import Decimal

from flask import Blueprint, jsonify, request, session
from psycopg2.extras import RealDictCursor

from database import db_query, db_tx
from utils import a_decimal, id_empresa
from routes.inventario import (aplicar_movimiento, asegurar_tablas_inventario, ddl_con_tipo_empresa, ErrorInventario,
                               _validar_empresa_sede, _stock_antiguo_sin_ubicar, _siguiente_numero, _usuario,
                               _empresas, _sedes, DIAS_SEPARACION)

stock_auto_bp = Blueprint('stock_automatico', __name__)

ESTADOS_SALIDA = ('Despachado', 'Entregado')

# Columnas nuevas (no borran nada). Script equivalente: migrations/006_stock_automatico.sql
SQL_DDL_STOCK_AUTO = """
    ALTER TABLE despachos ADD COLUMN IF NOT EXISTS stock_empresa_id INTEGER;
    ALTER TABLE despachos ADD COLUMN IF NOT EXISTS stock_almacen_id INTEGER;
    ALTER TABLE despachos ADD COLUMN IF NOT EXISTS stock_estado VARCHAR(20);
    ALTER TABLE despachos ADD COLUMN IF NOT EXISTS stock_detalle JSONB;
    ALTER TABLE despachos ADD COLUMN IF NOT EXISTS stock_fecha TIMESTAMP;
    ALTER TABLE inv_movimientos ADD COLUMN IF NOT EXISTS despacho_id INTEGER;
    CREATE INDEX IF NOT EXISTS idx_inv_mov_despacho ON inv_movimientos (despacho_id);
"""
_listo = False


def asegurar_columnas():
    global _listo
    if _listo:
        return
    asegurar_tablas_inventario()
    with db_tx() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT COUNT(*) FROM information_schema.columns
                       WHERE (table_name = 'despachos' AND column_name IN ('stock_empresa_id', 'stock_almacen_id',
                              'stock_estado', 'stock_detalle', 'stock_fecha'))
                          OR (table_name = 'inv_movimientos' AND column_name = 'despacho_id')""")
        if cur.fetchone()[0] < 6:
            # Solo se ejecuta si falta alguna columna (en Supabase ya se aplicó con la migración 006)
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('stock_auto_ddl'))")
            # stock_empresa_id usa el mismo tipo que erp_empresas.id (UUID en Supabase)
            ddl = ddl_con_tipo_empresa(cur, 'empresa_id INTEGER')
            cur.execute(SQL_DDL_STOCK_AUTO.replace('stock_empresa_id INTEGER', 'stock_' + ddl))
    _listo = True


def _cant(n):
    return f'{a_decimal(n).normalize():f}'


def _items_despacho(cur, desp):
    """Productos del despacho (o de su PC si el despacho no los guardó), con producto_id resuelto por código."""
    from routes.compras_flujo import _items_pedido, _resolver_productos
    items = _items_pedido({'items_json': desp.get('items_json')})
    if not items and desp.get('pc_id'):
        cur.execute("SELECT items_json FROM pedido_compra_pc WHERE id = %s", (desp['pc_id'],))
        pc = cur.fetchone()
        items = _items_pedido(pc) if pc else []
    items = [i for i in _resolver_productos(items) if a_decimal(i['cantidad']) > 0]
    # El mismo producto en dos líneas se descuenta junto
    juntos, sin_codigo = {}, []
    for i in items:
        if not i['producto_id']:
            sin_codigo.append(i['descripcion'] or i['codigo'] or 'producto sin código')
            continue
        if i['producto_id'] in juntos:
            juntos[i['producto_id']]['cantidad'] += a_decimal(i['cantidad'])
        else:
            juntos[i['producto_id']] = dict(i, cantidad=a_decimal(i['cantidad']))
    return list(juntos.values()), sin_codigo


def _separaciones_cliente(cur, desp, empresa_id, almacen_id, producto_id):
    """Separaciones activas de ESTE cliente (o de su PC) en esa empresa y sede."""
    cur.execute("""
        SELECT id, cantidad FROM inv_separaciones
        WHERE empresa_id = %s AND almacen_id = %s AND producto_id = %s AND estado = 'Activa'
          AND vence_el >= CURRENT_DATE AND cantidad > 0
          AND (UPPER(TRIM(cliente)) = UPPER(TRIM(%s)) OR (COALESCE(%s, '') <> '' AND documento = %s))
        ORDER BY vence_el, id FOR UPDATE
    """, (empresa_id, almacen_id, producto_id, desp.get('cliente') or '', desp.get('pc_numero'), desp.get('pc_numero')))
    return cur.fetchall()


class ErrorFaltaStock(ErrorInventario):
    """No alcanza el stock para despachar. `faltan` dice qué producto, en qué empresa y sede, cuánto pide y cuánto hay."""
    def __init__(self, mensaje, faltan):
        super().__init__(mensaje)
        self.faltan = faltan


def descontar_despacho(cur, desp, empresa_id, almacen_id):
    """Saca del stock todos los productos del despacho. Si algo no alcanza lanza ErrorFaltaStock con TODOS los
    productos que faltan (pedido de Erika 20/10/2026: decir qué producto falta y en qué sede)."""
    _validar_empresa_sede(cur, empresa_id, almacen_id)
    cur.execute("SELECT COALESCE(NULLIF(nombre_corto, ''), codigo, razon_social) AS n FROM erp_empresas WHERE id = %s", (empresa_id,))
    nom_empresa = (cur.fetchone() or {}).get('n') or ''
    cur.execute("SELECT nombre FROM almacenes WHERE id = %s", (almacen_id,))
    nom_sede = (cur.fetchone() or {}).get('nombre') or ''
    faltan = []
    items, sin_codigo = _items_despacho(cur, desp)
    if not items:
        raise ErrorInventario('Este despacho no tiene productos del catálogo: no se puede descontar stock. '
                              'Revisa los productos del pedido.')
    _, unom = _usuario()
    detalle = []
    for it in items:
        pid, cantidad = it['producto_id'], it['cantidad']
        nombre = it['descripcion'] or it['codigo']
        if _stock_antiguo_sin_ubicar(cur, pid) > 0:
            raise ErrorInventario(f'"{nombre}" tiene stock antiguo que todavía no tiene empresa ni sede. '
                                  'Primero regístralo en Inventario con "Stock inicial".')
        seps = _separaciones_cliente(cur, desp, empresa_id, almacen_id, pid)
        usar = min(sum((a_decimal(s['cantidad']) for s in seps), Decimal('0')), cantidad)
        cur.execute("SAVEPOINT desp_item")
        try:
            mov = aplicar_movimiento(
                cur, empresa_id=empresa_id, almacen_id=almacen_id, producto_id=pid, motivo='VENTA', cantidad=cantidad,
                documento_tipo='Despacho', documento_numero=desp.get('numero'), tercero=desp.get('cliente'),
                observaciones=f"Despacho {desp.get('numero') or ''}" + (f" · PC {desp['pc_numero']}" if desp.get('pc_numero') else ''),
                separacion_id=seps[0]['id'] if seps else None, usar_reservado=usar)
        except ErrorInventario as e:
            cur.execute("ROLLBACK TO SAVEPOINT desp_item")
            cur.execute("""SELECT COALESCE(SUM(cantidad), 0) AS hay FROM inv_stock
                           WHERE empresa_id = %s AND almacen_id = %s AND producto_id = %s""", (empresa_id, almacen_id, pid))
            hay = a_decimal((cur.fetchone() or {}).get('hay'))
            faltan.append({'producto': nombre, 'codigo': it.get('codigo') or '', 'empresa': nom_empresa, 'sede': nom_sede,
                           'pide': float(cantidad), 'hay': float(hay), 'detalle': str(e)})
            continue
        cur.execute("RELEASE SAVEPOINT desp_item")
        cur.execute("UPDATE inv_movimientos SET despacho_id = %s WHERE id = %s", (desp['id'], mov['id']))
        usadas, resto = [], usar
        for s in seps:
            if resto <= 0:
                break
            t = min(a_decimal(s['cantidad']), resto)
            resto -= t
            cur.execute("""
                UPDATE inv_separaciones SET cantidad = cantidad - %s,
                       estado = CASE WHEN cantidad - %s <= 0 THEN 'Entregada' ELSE estado END,
                       cerrado_por = CASE WHEN cantidad - %s <= 0 THEN %s ELSE cerrado_por END,
                       cerrado_en = CASE WHEN cantidad - %s <= 0 THEN NOW() ELSE cerrado_en END
                WHERE id = %s
            """, (t, t, t, unom, t, s['id']))
            usadas.append({'id': s['id'], 'cantidad': float(t)})
        detalle.append({'movimiento_id': mov['id'], 'movimiento': mov['numero'], 'producto_id': pid,
                        'producto': nombre, 'cantidad': float(cantidad), 'separaciones': usadas})
    if faltan:
        lista = '; '.join(f'"{f["producto"]}" (pide {f["pide"]:g}, hay {f["hay"]:g})' for f in faltan)
        raise ErrorFaltaStock(f'No hay stock suficiente en {nom_empresa} · {nom_sede}: {lista}.', faltan)
    cur.execute("""UPDATE despachos SET stock_empresa_id = %s, stock_almacen_id = %s, stock_estado = 'Descontado',
                   stock_detalle = %s, stock_fecha = NOW() WHERE id = %s""",
                (empresa_id, almacen_id, json.dumps(detalle), desp['id']))
    return detalle, sin_codigo


def revertir_despacho(cur, desp, motivo):
    """Devuelve al stock lo que salió con el despacho y vuelve a separar lo que era del cliente."""
    if desp.get('stock_estado') != 'Descontado':
        return []
    _, unom = _usuario()
    cur.execute("""SELECT * FROM inv_movimientos WHERE despacho_id = %s AND estado = 'Registrado'
                   AND revertido_por_id IS NULL AND revierte_id IS NULL AND tipo = 'SALIDA' ORDER BY id FOR UPDATE""",
                (desp['id'],))
    devueltos = []
    for m in cur.fetchall():
        nuevo = aplicar_movimiento(
            cur, empresa_id=m['empresa_id'], almacen_id=m['almacen_id'], producto_id=m['producto_id'],
            motivo='REVERSA_ENTRADA', cantidad=m['cantidad'], costo_unitario=m['costo_unitario'],
            documento_tipo='Despacho anulado', documento_numero=desp.get('numero'), tercero=m['tercero'],
            observaciones=f"Vuelve al stock: {motivo}", revierte_id=m['id'], aprobado_por=unom)
        cur.execute("UPDATE inv_movimientos SET revertido_por_id = %s WHERE id = %s", (nuevo['id'], m['id']))
        cur.execute("UPDATE inv_movimientos SET despacho_id = %s WHERE id = %s", (desp['id'], nuevo['id']))
        devueltos.append(nuevo['numero'])
    detalle = desp.get('stock_detalle') or []
    if isinstance(detalle, str):
        detalle = json.loads(detalle)
    vence = date.today() + timedelta(days=DIAS_SEPARACION)
    for d in detalle:
        for s in d.get('separaciones') or []:
            cur.execute("""UPDATE inv_separaciones SET cantidad = cantidad + %s, estado = 'Activa', cerrado_por = NULL,
                           cerrado_en = NULL, vence_el = GREATEST(vence_el, %s) WHERE id = %s""",
                        (s['cantidad'], vence, s['id']))
    cur.execute("UPDATE despachos SET stock_estado = 'Revertido', stock_fecha = NOW() WHERE id = %s", (desp['id'],))
    return devueltos


def ingresar_recepcion(cur, *, recepcion_id, oc, oi, almacen_id, cantidad, guia, lote_serie=None, fecha_vencimiento=None):
    """Compras > Recibir: suma al inventario lo recibido en buen estado. Devuelve (movimiento, separación) o
    (None, motivo) si no se pudo hacer solo y queda pendiente en Inventario."""
    if not oi.get('producto_id') or not oc.get('empresa_id'):
        return None, 'sin producto o empresa'
    if _stock_antiguo_sin_ubicar(cur, oi['producto_id']) > 0:
        return None, 'tiene stock antiguo sin ubicar'
    mov = aplicar_movimiento(
        cur, empresa_id=oc['empresa_id'], almacen_id=almacen_id, producto_id=oi['producto_id'], motivo='COMPRA',
        cantidad=cantidad, costo_unitario=oi['precio_unitario'], documento_tipo='Guía proveedor',
        documento_numero=guia, tercero=oc.get('razon_social'), lote_serie=lote_serie,
        fecha_vencimiento=fecha_vencimiento or None, recepcion_id=recepcion_id,
        observaciones=f"Ingreso automático al recibir la OC {oc.get('numero_orden') or ''}")
    sep_num = None
    if oi.get('cliente'):
        uid, unom = _usuario()
        sep_num = _siguiente_numero(cur, 'SEP', 'inv_separaciones')
        cur.execute("""
            INSERT INTO inv_separaciones (numero, empresa_id, almacen_id, producto_id, cantidad, cantidad_inicial,
                cliente, documento, vence_el, observaciones, usuario_id, usuario_nombre)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (sep_num, oc['empresa_id'], almacen_id, oi['producto_id'], cantidad, cantidad, oi['cliente'],
              oi.get('pedido_numero'), date.today() + timedelta(days=DIAS_SEPARACION),
              f"Separado automáticamente al recibir la compra {oc.get('numero_orden') or ''}", uid, unom))
    return mov, sep_num


# ============================================================
# API para la ventana "Despachar" de Ventas
# ============================================================
@stock_auto_bp.route('/ventas/api/despachos/<int:did>/ubicaciones')
def api_ubicaciones_despacho(did):
    """Dónde hay stock para cada producto del despacho y qué empresa/sede alcanza para todo."""
    try:
        asegurar_columnas()
        desp = db_query("SELECT * FROM despachos WHERE id = %s", (did,))
        if not desp:
            return jsonify({'success': False, 'error': 'Despacho no encontrado'}), 404
        desp = desp[0]
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            items, sin_codigo = _items_despacho(cur, desp)
            ids = [i['producto_id'] for i in items]
            filas = []
            if ids:
                cur.execute("""
                    SELECT s.empresa_id, s.almacen_id, s.producto_id, s.cantidad,
                           COALESCE((SELECT SUM(x.cantidad) FROM inv_separaciones x
                                     WHERE x.empresa_id = s.empresa_id AND x.almacen_id = s.almacen_id
                                       AND x.producto_id = s.producto_id AND x.estado = 'Activa' AND x.vence_el >= CURRENT_DATE
                                       AND NOT (UPPER(TRIM(x.cliente)) = UPPER(TRIM(%s))
                                                OR (COALESCE(%s, '') <> '' AND x.documento = %s))), 0) AS de_otros
                    FROM inv_stock s WHERE s.producto_id = ANY(%s) AND s.cantidad > 0
                """, (desp.get('cliente') or '', desp.get('pc_numero'), desp.get('pc_numero'), ids))
                filas = cur.fetchall()
        empresas = _empresas()
        sedes = _sedes()
        disp = {}
        for f in filas:
            disp[(str(f['empresa_id']), f['almacen_id'], f['producto_id'])] = max(
                a_decimal(f['cantidad']) - a_decimal(f['de_otros']), Decimal('0'))
        opciones = []
        for e in empresas:
            for s in sedes:
                faltan = [{'producto': i['descripcion'] or i['codigo'], 'pide': float(i['cantidad']),
                           'hay': float(disp.get((str(e['id']), s['id'], i['producto_id']), 0))}
                          for i in items if disp.get((str(e['id']), s['id'], i['producto_id']), Decimal('0')) < i['cantidad']]
                opciones.append({'empresa_id': e['id'], 'empresa': e['nombre'], 'almacen_id': s['id'], 'sede': s['nombre'],
                                 'alcanza': bool(items) and not faltan, 'faltan': faltan})
        empresa_desp = (desp.get('empresa') or '').upper()
        opciones.sort(key=lambda o: (not o['alcanza'], (o['empresa'] or '').upper() != empresa_desp))
        return jsonify({'success': True, 'productos': [{'producto': i['descripcion'] or i['codigo'],
                                                        'cantidad': float(i['cantidad'])} for i in items],
                        'sin_codigo': sin_codigo, 'opciones': opciones,
                        'stock_estado': desp.get('stock_estado')})
    except Exception as e:
        print(f'❌ Ubicaciones de despacho: {e}')
        return jsonify({'success': False, 'error': 'No se pudo consultar el stock.'}), 500


def cambiar_estado_despacho(did, nuevo_estado, empresa_id=None, almacen_id=None, motivo=None):
    """Cambia el estado del despacho moviendo el stock cuando corresponde. Devuelve (respuesta_json, código)."""
    asegurar_columnas()
    try:
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM despachos WHERE id = %s FOR UPDATE", (did,))
            desp = cur.fetchone()
            if not desp:
                return {'success': False, 'error': 'Despacho no encontrado'}, 404
            actual = desp.get('estado') or ''
            if actual == 'Anulado':
                return {'success': False, 'error': 'El despacho está anulado.'}, 409
            msg_extra = ''
            if nuevo_estado in ESTADOS_SALIDA and desp.get('stock_estado') != 'Descontado':
                eid = id_empresa(empresa_id)
                try:
                    aid = int(almacen_id) if almacen_id else None
                except (TypeError, ValueError):
                    aid = None
                if eid is None or not aid:
                    return {'success': False, 'necesita_ubicacion': True,
                            'error': 'Elige de qué empresa y de qué sede sale la mercadería.'}, 400
                detalle, sin_codigo = descontar_despacho(cur, desp, eid, aid)
                msg_extra = f' Se descontó el stock de {len(detalle)} producto(s).'
                if sin_codigo:
                    msg_extra += f" Sin código del catálogo (no se descontaron): {', '.join(sin_codigo[:5])}."
            elif nuevo_estado == 'Anulado' or (nuevo_estado not in ESTADOS_SALIDA and actual in ESTADOS_SALIDA):
                devueltos = revertir_despacho(cur, desp, motivo or f'despacho pasó a {nuevo_estado}')
                if devueltos:
                    msg_extra = f' El stock volvió al inventario ({len(devueltos)} movimiento(s)).'
            cur.execute("UPDATE despachos SET estado = %s, updated_at = NOW() WHERE id = %s RETURNING id, estado",
                        (nuevo_estado, did))
            fila = cur.fetchone()
        texto = 'Despacho anulado.' if nuevo_estado == 'Anulado' else f'Despacho actualizado a {nuevo_estado}.'
        return {'success': True, 'message': texto + msg_extra, 'data': dict(fila)}, 200
    except ErrorFaltaStock as e:
        return {'success': False, 'codigo': 'falta_stock', 'faltan': e.faltan, 'error': str(e)}, 409
    except ErrorInventario as e:
        return {'success': False, 'error': str(e)}, 400


def anular_cobros_comprobante(cur, comp_id, motivo):
    """Caja: al anular un comprobante de venta, sus cobros quedan anulados (la plata se devuelve al cliente)."""
    from routes.finanzas import asegurar_tablas_finanzas
    asegurar_tablas_finanzas()
    cur.execute("""UPDATE finanzas_pagos SET estado = 'Anulado', anulado_por = %s, anulado_en = NOW(),
                   motivo_anulacion = %s
                   WHERE documento_tabla = 'comprobantes' AND documento_id = %s AND estado <> 'Anulado'
                   RETURNING id""", (session.get('usuario_id'), motivo, comp_id))
    return len(cur.fetchall())
