"""
Pruebas del módulo de Compras bajo pedido (routes/compras_flujo.py).
Escenario: KCF y AGD, sedes San Martín de Porres y Breña, un pedido de cliente (PV) con dos productos.
"""
import json
import pytest
from werkzeug.security import generate_password_hash

from tests.conftest import _login
from tests.test_inventario import _sql


@pytest.fixture(scope='module')
def cx(app):
    _sql("""
        INSERT INTO erp_empresas (codigo, nombre_corto, nombre_comercial, razon_social, ruc, estado, color_primario, color_secundario, color_pastel)
        SELECT 'KCF', 'KCF', 'KCF', 'KCF S.A.C.', '20111111111', 'activo', '#D6243A', '#1D1A1F', '#FDE8EB' WHERE NOT EXISTS (SELECT 1 FROM erp_empresas WHERE codigo='KCF');
        INSERT INTO erp_empresas (codigo, nombre_corto, nombre_comercial, razon_social, ruc, estado, color_primario, color_secundario, color_pastel)
        SELECT 'AGD', 'AGD', 'AGD', 'AGD S.A.C.', '20222222222', 'activo', '#D6243A', '#1D1A1F', '#FDE8EB' WHERE NOT EXISTS (SELECT 1 FROM erp_empresas WHERE codigo='AGD');
        INSERT INTO almacenes (codigo, nombre, direccion, activo)
        SELECT 'SMP', 'San Martín de Porres', 'Av. Perú 123, SMP', true WHERE NOT EXISTS (SELECT 1 FROM almacenes WHERE codigo='SMP');
        INSERT INTO almacenes (codigo, nombre, direccion, activo)
        SELECT 'BRE', 'Breña', 'Jr. Huaraz 456, Breña', true WHERE NOT EXISTS (SELECT 1 FROM almacenes WHERE codigo='BRE');
        INSERT INTO productos (familia, codigo, descripcion, marca, unidad, costo_unitario, precio_unitario, stock, activo) VALUES
            ('GENERAL', 'COM-001', 'IPHONE 17 PRO MAX NARANJA 256GB', 'APPLE', 'UND', 0, 6500, 0, true),
            ('GENERAL', 'COM-002', 'CARGADOR USB-C 20W', 'APPLE', 'UND', 0, 90, 0, true);
        INSERT INTO proveedores (razon_social, ruc, direccion, banco, numero_cuenta, cci, condicion_pago, activo)
        VALUES ('IMPORTADORA MOVIL S.A.C.', '20555555555', 'Av. Wilson 1000, Lima', 'BCP', '191-1234567-0-11', '00219100123456701155', 'Contado', true);
    """, fetch=False)
    _sql("""INSERT INTO usuarios (usuario_sistema, usuario, nombres_apellidos, nombre_completo, correo, password, rol, estado) VALUES
            ('compra1', 'compra1', 'Compradora Uno', 'Compradora Uno', 'co1@t.pe', %s, 'compras', 'activo'),
            ('fin1', 'fin1', 'Finanzas Uno', 'Finanzas Uno', 'f1@t.pe', %s, 'finanzas', 'activo'),
            ('log1', 'log1', 'Logistico Uno', 'Logistico Uno', 'l1@t.pe', %s, 'logistica', 'activo'),
            ('alm9', 'alm9', 'Almacen Sede', 'Almacen Sede', 'a9@t.pe', %s, 'almacen', 'activo')""",
         tuple(generate_password_hash('Clave#2026!') for _ in range(4)), fetch=False)
    emp = dict(_sql("SELECT codigo, id FROM erp_empresas"))
    sede = dict(_sql("SELECT codigo, id FROM almacenes WHERE codigo IN ('SMP', 'BRE')"))
    prod = dict(_sql("SELECT codigo, id FROM productos WHERE codigo LIKE 'COM-%'"))
    prov = _sql("SELECT id FROM proveedores WHERE ruc = '20555555555'")[0][0]
    usu = dict(_sql("SELECT usuario_sistema, id FROM usuarios"))
    items = [{'codigo': 'COM-001', 'producto': 'IPHONE 17 PRO MAX NARANJA 256GB', 'cantidad_pc': 5, 'precio_pc': 6500},
             {'codigo': 'COM-002', 'producto': 'CARGADOR USB-C 20W', 'cantidad_pc': 5, 'precio_pc': 90}]
    pc = _sql("""INSERT INTO pedido_compra_pc (numero, cliente, ruc, estado, items_json, fecha)
                 VALUES ('PC-20261013-0001', 'CELULARES DEL NORTE S.A.C.', '20666666666', 'Pendiente', %s, NOW()) RETURNING id""",
              (json.dumps(items),))[0][0]
    return {'KCF': emp['KCF'], 'AGD': emp['AGD'], 'SMP': sede['SMP'], 'BRE': sede['BRE'], 'IPH': prod['COM-001'],
            'CAR': prod['COM-002'], 'prov': prov, 'pc': pc, 'usu': usu,
            'compra': _login(app, 'compra1', 'Clave#2026!'), 'fin': _login(app, 'fin1', 'Clave#2026!'),
            'log': _login(app, 'log1', 'Clave#2026!'), 'alm': _login(app, 'alm9', 'Clave#2026!')}


def _oc_body(cx, **extra):
    body = {'empresa_id': cx['AGD'], 'proveedor_id': cx['prov'], 'almacen_entrega_id': cx['SMP'],
            'condicion_pago': 'Contado', 'modalidad_entrega': 'Nosotros recogemos', 'direccion_recojo': 'Av. Wilson 1000',
            'fecha_compromiso': '2026-10-15',
            'items': [{'producto_id': cx['IPH'], 'cantidad': 5, 'precio_unitario': 4000, 'pedido_id': cx['pc']},
                      {'producto_id': cx['CAR'], 'cantidad': 5, 'precio_unitario': 50, 'pedido_id': cx['pc']}]}
    body.update(extra)
    return body


def test_pedido_aparece_por_comprar(cx):
    r = cx['compra'].get('/compras/api/flujo/pedidos').get_json()
    pc = next(p for p in r['data'] if p['id'] == cx['pc'])
    assert [i['falta'] for i in pc['items']] == [5, 5]
    assert pc['items'][0]['producto_id'] == cx['IPH']  # resuelto por código


def test_pagina_compras_carga(cx, admin):
    r = admin.get('/compras')
    assert r.status_code == 200 and b'comApp' in r.data
    assert admin.get('/compras/anterior').status_code == 200  # las pantallas de antes siguen


def test_vendedor_no_puede_crear_oc(cx, vendedor):
    r = vendedor.post('/compras/api/flujo/ordenes', json=_oc_body(cx))
    assert r.status_code == 403


def test_no_se_compra_mas_de_lo_pedido(cx):
    body = _oc_body(cx)
    body['items'][0]['cantidad'] = 7
    r = cx['compra'].post('/compras/api/flujo/ordenes', json=body)
    assert r.status_code == 400 and 'solo necesita 5' in r.get_json()['error']


def test_compra_para_stock_exige_motivo(cx):
    body = _oc_body(cx, items=[{'producto_id': cx['CAR'], 'cantidad': 10, 'precio_unitario': 50}])
    r = cx['compra'].post('/compras/api/flujo/ordenes', json=body)
    assert r.status_code == 400 and 'motivo' in r.get_json()['error']


def test_flujo_completo_bajo_pedido(cx, aprobador, app):
    # 1. Compras crea y envía la OC
    r = cx['compra'].post('/compras/api/flujo/ordenes', json=_oc_body(cx, enviar=True))
    assert r.status_code == 200, r.get_json()
    oc_id = r.get_json()['id']
    det = cx['compra'].get(f'/compras/api/flujo/ordenes/{oc_id}').get_json()['data']
    assert det['estado'] == 'Por aprobar' and det['tipo_compra'] == 'Bajo pedido'
    assert det['total'] == pytest.approx((5 * 4000 + 5 * 50) * 1.18)
    # El pedido ya no aparece como "por comprar"
    assert all(p['id'] != cx['pc'] for p in cx['compra'].get('/compras/api/flujo/pedidos').get_json()['data'])

    # 2. Quien la hizo no puede aprobar (no es supervisora); la supervisora sí
    assert cx['compra'].post(f'/compras/api/flujo/ordenes/{oc_id}/aprobar', json={'aprobar': True}).status_code == 403
    r = aprobador.post(f'/compras/api/flujo/ordenes/{oc_id}/aprobar', json={'aprobar': True})
    assert r.status_code == 200, r.get_json()

    # 3. Es al contado: no se puede recibir antes del pago
    rec = {'almacen_id': cx['SMP'], 'guia_proveedor': 'EG01-00000123', 'traido_por_tipo': 'usuario',
           'traido_por_id': cx['usu']['log1'], 'items': []}
    items = cx['alm'].get(f'/compras/api/flujo/ordenes/{oc_id}/para_recibir').get_json()['items']
    assert 'cantidad' not in items[0]  # recepción a ciegas
    rec['items'] = [{'oc_item_id': items[0]['id'], 'cantidad_buena': 4, 'cantidad_danada': 0},
                    {'oc_item_id': items[1]['id'], 'cantidad_buena': 5, 'cantidad_danada': 0}]
    r = cx['alm'].post(f'/compras/api/flujo/ordenes/{oc_id}/recibir', json=rec)
    assert r.status_code == 400 and 'pago' in r.get_json()['error']

    # 4. Pago: sin N° de operación no; quien hizo la OC no puede pagar; Finanzas sí
    assert cx['fin'].post(f'/compras/api/flujo/ordenes/{oc_id}/pago', json={'monto': 100, 'metodo': 'Transferencia'}).status_code == 400
    assert cx['compra'].post(f'/compras/api/flujo/ordenes/{oc_id}/pago', json={'monto': 100, 'metodo': 'Transferencia', 'numero_operacion': '1'}).status_code == 403
    total = det['total']
    r = cx['fin'].post(f'/compras/api/flujo/ordenes/{oc_id}/pago', json={'monto': total + 1, 'metodo': 'Transferencia', 'numero_operacion': '998877'})
    assert r.status_code == 400  # no se paga más del total
    r = cx['fin'].post(f'/compras/api/flujo/ordenes/{oc_id}/pago', json={'monto': total, 'metodo': 'Transferencia', 'numero_operacion': '998877'})
    assert r.status_code == 200, r.get_json()

    # 5. Quien recogió no puede recibir; tampoco quien hizo la OC
    assert cx['log'].post(f'/compras/api/flujo/ordenes/{oc_id}/recibir', json=rec).status_code == 403
    r = cx['alm'].post(f'/compras/api/flujo/ordenes/{oc_id}/recibir', json=rec)
    # 22/10/2026: falta 1 iPhone → primero avisa con la diferencia y no graba; se confirma a propósito
    assert r.status_code == 409 and r.get_json()['codigo'] == 'diferencias', r.get_json()
    assert any('faltan 1' in x['texto'] for x in r.get_json()['diferencias'])
    rec['confirmar_diferencias'] = True
    # 28/10/2026: confirmar con diferencia exige explicar qué pasó
    r = cx['alm'].post(f'/compras/api/flujo/ordenes/{oc_id}/recibir', json=rec)
    assert r.status_code == 400 and 'jefe inmediato' in r.get_json()['error']
    rec['motivo_diferencias'] = 'El proveedor mandó incompleto'
    r = cx['alm'].post(f'/compras/api/flujo/ordenes/{oc_id}/recibir', json=rec)
    assert r.status_code == 200, r.get_json()
    res = r.get_json()
    assert res['estado'] == 'Recibida parcial'
    assert {x['producto']: x['estado'] for x in res['resultado']}['IPHONE 17 PRO MAX NARANJA 256GB'] == 'Faltante'
    # La misma guía no se registra dos veces
    assert cx['alm'].post(f'/compras/api/flujo/ordenes/{oc_id}/recibir', json=rec).status_code == 400

    # 6. Llega el iPhone que faltaba con otra guía
    items = cx['alm'].get(f'/compras/api/flujo/ordenes/{oc_id}/para_recibir').get_json()['items']
    assert len(items) == 1
    r = cx['alm'].post(f'/compras/api/flujo/ordenes/{oc_id}/recibir', json={
        'almacen_id': cx['SMP'], 'guia_proveedor': 'EG01-00000130', 'traido_por_tipo': 'proveedor',
        'items': [{'oc_item_id': items[0]['id'], 'cantidad_buena': 1}]})
    assert r.get_json()['estado'] == 'Recibida'

    # 7. Lo recibido entra SOLO al inventario (empresa de la OC, sede de recepción, costo de la OC)
    #    y queda separado para el cliente del pedido. Ya no aparece como pendiente en Inventario.
    assert r.get_json()['movimientos'] and not r.get_json()['pendientes_inventario']
    pend = cx['alm'].get('/inventario/api/recepciones_pendientes').get_json()['data']
    assert not [p for p in pend if p['orden_compra'] == det['numero']]
    movs = _sql("""SELECT m.empresa_id, m.almacen_id, m.producto_id, m.cantidad, m.costo_unitario, m.motivo
                   FROM inv_movimientos m JOIN recepciones_mercaderia r ON r.id = m.recepcion_id
                   WHERE r.orden_compra_numero = %s ORDER BY m.id""", (det['numero'],))
    assert len(movs) == 3 and all(m[0] == cx['AGD'] and m[1] == cx['SMP'] and m[5] == 'COMPRA' for m in movs)
    assert sum(float(m[3]) for m in movs if m[2] == cx['IPH']) == 5
    assert all(float(m[4]) > 0 for m in movs)
    seps = _sql("""SELECT cliente, SUM(cantidad) FROM inv_separaciones WHERE producto_id = %s AND empresa_id = %s
                   AND estado = 'Activa' GROUP BY cliente""", (cx['IPH'], cx['AGD']))
    assert seps == [('CELULARES DEL NORTE S.A.C.', seps[0][1])] and float(seps[0][1]) == 5
    # Esa recepción ya no se puede ingresar otra vez a mano
    rec_id = _sql("""SELECT r.id FROM recepciones_mercaderia r WHERE r.orden_compra_numero = %s LIMIT 1""", (det['numero'],))[0][0]
    doble = {'motivo': 'COMPRA', 'empresa_id': cx['AGD'], 'almacen_id': cx['SMP'], 'producto_id': cx['IPH'], 'cantidad': 1,
             'costo_unitario': 4000, 'documento_numero': 'EG01-00000123', 'recepcion_id': rec_id}
    assert cx['alm'].post('/inventario/api/movimientos', json=doble).status_code == 400

    # 8. Factura que no cuadra -> NO se guarda (20/10/2026): aviso con lo esperado y se corrige en el momento
    fac = {'tipo': 'Factura', 'numero': 'F001-00000777', 'fecha': '2026-10-13', 'monto': total + 50}
    r = cx['fin'].post(f'/compras/api/flujo/ordenes/{oc_id}/factura', json=fac)
    assert r.status_code == 409 and r.get_json()['codigo'] == 'no_cuadra'
    assert r.get_json()['esperado'] == pytest.approx(total) and r.get_json()['diferencia'] == pytest.approx(50)
    assert _sql("SELECT COUNT(*) FROM comprobantes_proveedor WHERE numero = 'F001-00000777'")[0][0] == 0
    # Solo si la factura física de verdad dice eso: con motivo queda dentro de su OC como diferencia por resolver
    assert cx['fin'].post(f'/compras/api/flujo/ordenes/{oc_id}/factura', json={**fac, 'aceptar_diferencia': True}).status_code == 400
    r = cx['fin'].post(f'/compras/api/flujo/ordenes/{oc_id}/factura',
                       json={**fac, 'aceptar_diferencia': True, 'motivo_diferencia': 'El proveedor cobró flete'})
    assert r.status_code == 200 and r.get_json()['cuadra'] is False
    ver = cx['fin'].get(f"/compras/api/flujo/facturas/{r.get_json()['id']}").get_json()['data']
    assert ver['numero'] == 'F001-00000777' and ver['orden_compra_id'] == oc_id and 'flete' in ver['observaciones']
    assert cx['fin'].get('/compras/api/flujo/facturas/ultima').get_json()['data']['id'] == ver['id']
    det = cx['fin'].get(f'/compras/api/flujo/ordenes/{oc_id}').get_json()['data']
    assert det['estado'] == 'Recibida' and det['paso']['codigo'] == 'incidencia'
    # El pago adelantado pasó a la factura (Finanzas ve el saldo real)
    assert det['facturas'][0]['estado'] == 'Pendiente'
    assert float(_sql("SELECT SUM(monto) FROM finanzas_pagos WHERE documento_tabla='comprobantes_proveedor' AND documento_id=%s",
                      (det['facturas'][0]['id'],))[0][0]) == pytest.approx(total)
    # 9. La supervisora resuelve la diferencia -> OC Cerrada
    inc = det['incidencias'][0]['id']
    assert cx['compra'].post(f'/compras/api/flujo/incidencias/{inc}/resolver', json={'resolucion': 'Nota de crédito F001-12'}).status_code == 403
    r = aprobador.post(f'/compras/api/flujo/incidencias/{inc}/resolver', json={'resolucion': 'Proveedor emite nota de crédito F001-12'})
    assert r.status_code == 200
    det = cx['fin'].get(f'/compras/api/flujo/ordenes/{oc_id}').get_json()['data']
    assert det['estado'] == 'Cerrada'
    assert any(h['accion'] == 'Cerrada' for h in det['historial'])
    # 10. La OC nueva no se puede tocar desde las pantallas anteriores
    assert aprobador.put(f'/compras/api/ordenes/{oc_id}/toggle', json={'estado': 'Confirmada'}).status_code == 409
    assert aprobador.delete(f'/compras/api/ordenes/{oc_id}').status_code == 409


def test_alerta_precio_y_anulacion(cx, aprobador):
    _sql("UPDATE pedido_compra_pc SET items_json = %s WHERE id = %s",
         (json.dumps([{'codigo': 'COM-001', 'producto': 'IPHONE', 'cantidad_pc': 7}]), cx['pc']), fetch=False)
    body = _oc_body(cx, condicion_pago='Crédito', dias_credito=30, modalidad_entrega='Proveedor entrega',
                    items=[{'producto_id': cx['IPH'], 'cantidad': 2, 'precio_unitario': 4800, 'pedido_id': cx['pc']}], enviar=True)
    r = cx['compra'].post('/compras/api/flujo/ordenes', json=body)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['alertas'] and '20' in r.get_json()['alertas'][0]  # 20% más caro que la última compra
    oc_id = r.get_json()['id']
    # A crédito sí se recibe sin pago, pero primero debe aprobarse
    assert cx['alm'].post(f'/compras/api/flujo/ordenes/{oc_id}/recibir', json={
        'almacen_id': cx['BRE'], 'guia_proveedor': 'EG09-1', 'traido_por_tipo': 'proveedor', 'items': []}).status_code == 400
    # Devolver sin motivo no; anular libera el pedido
    assert aprobador.post(f'/compras/api/flujo/ordenes/{oc_id}/aprobar', json={'aprobar': False}).status_code == 400
    r = aprobador.post(f'/compras/api/flujo/ordenes/{oc_id}/anular', json={'motivo': 'Precio muy alto, cotizar otro'})
    assert r.status_code == 200
    pc = next(p for p in cx['compra'].get('/compras/api/flujo/pedidos').get_json()['data'] if p['id'] == cx['pc'])
    assert pc['items'][0]['falta'] == 2


def test_resumen_y_exportar(cx, admin):
    r = admin.get('/compras/api/flujo/resumen').get_json()
    assert r['success'] and 'kpis' in r and r['alertas']
    r = admin.get('/compras/api/flujo/ordenes/exportar')
    assert r.status_code == 200 and b'OC;Fecha' in r.data
    oc = _sql("SELECT id FROM ordenes_compra WHERE flujo='v2' AND estado='Cerrada' LIMIT 1")[0][0]
    r = admin.get(f'/compras/flujo/ordenes/{oc}/imprimir')
    assert r.status_code == 200 and b'ORDEN DE COMPRA' in r.data
    assert admin.get(f'/compras/flujo/ordenes/{oc}/imprimir?hoja=recojo').status_code == 200
    # Nota interna (Erika 28/10/2026): se ve en el ERP, nunca en la OC impresa para el proveedor
    _sql("UPDATE ordenes_compra SET nota_interna = 'SECRETO INTERNO ZZ' WHERE id = %s", (oc,), fetch=False)
    assert 'SECRETO INTERNO ZZ' not in admin.get(f'/compras/flujo/ordenes/{oc}/imprimir').get_data(as_text=True)
    assert admin.get(f'/compras/api/flujo/ordenes/{oc}').get_json()['data']['nota_interna'] == 'SECRETO INTERNO ZZ'
