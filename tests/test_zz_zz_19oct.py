"""
Pedido de Erika del 19/10/2026: panel "Resumen de abastecimiento" en el formulario de OC
(stock actual · pedido del cliente por cubrir · sugerido a comprar) y columnas N° PV / N° Guía
en las tablas de Guías y Facturas. Datos inventados, solo en la base local de pruebas.
"""
import json

import pytest

from tests.test_inventario import _sql


@pytest.fixture(scope='module')
def d19(admin):
    _sql("""
        INSERT INTO erp_empresas (codigo, nombre_corto, nombre_comercial, razon_social, ruc, estado, color_primario, color_secundario, color_pastel)
        SELECT 'KCF', 'KCF', 'KCF', 'KCF S.A.C.', '20111111111', 'activo', '#D6243A', '#1D1A1F', '#FDE8EB'
        WHERE NOT EXISTS (SELECT 1 FROM erp_empresas WHERE codigo = 'KCF');
        INSERT INTO almacenes (codigo, nombre, direccion, activo)
        SELECT 'SMP', 'San Martín de Porres', 'Av. Perú 123, SMP', true WHERE NOT EXISTS (SELECT 1 FROM almacenes WHERE codigo = 'SMP');
        INSERT INTO productos (familia, codigo, descripcion, marca, unidad, costo_unitario, precio_unitario, stock, activo) VALUES
            ('GENERAL', 'ZZ19-001', 'GUANTE ZZ19', 'ZZ', 'PAR', 0, 10, 0, true),
            ('GENERAL', 'ZZ19-002', 'CASCO ZZ19', 'ZZ', 'UND', 0, 30, 0, true);
    """, fetch=False)
    emp = _sql("SELECT id FROM erp_empresas WHERE codigo = 'KCF'")[0][0]
    sede = _sql("SELECT id FROM almacenes WHERE codigo = 'SMP'")[0][0]
    prod = dict(_sql("SELECT codigo, id FROM productos WHERE codigo LIKE 'ZZ19-%'"))
    _sql("INSERT INTO inv_stock (empresa_id, almacen_id, producto_id, cantidad) VALUES (%s, %s, %s, 10)",
         (emp, sede, prod['ZZ19-001']), fetch=False)
    items = [{'codigo': 'ZZ19-001', 'producto': 'GUANTE ZZ19', 'cantidad_pc': 40, 'precio_pc': 10}]
    _sql("""INSERT INTO pedido_compra_pc (numero, cliente, ruc, estado, items_json, fecha, cotizacion_numero)
            VALUES ('PC-ZZ19-0001', 'CLIENTE ZZ19', '20888888819', 'Pendiente', %s, NOW(), 'COT-ZZ19-01')""",
         (json.dumps(items),), fetch=False)
    return {'emp': emp, 'sede': sede, 'GUANTE': prod['ZZ19-001'], 'CASCO': prod['ZZ19-002']}


def _abast(admin, d19, *ids):
    r = admin.get('/compras/api/flujo/abastecimiento',
                  query_string={'empresa_id': str(d19['emp']), 'productos': ','.join(str(i) for i in ids)})
    assert r.status_code == 200, r.json
    return {x['producto_id']: x for x in r.json['data']}


def test_abastecimiento_stock_pedido_y_sugerido(admin, d19):
    data = _abast(admin, d19, d19['GUANTE'], d19['CASCO'])
    g = data[d19['GUANTE']]
    assert g['stock'] == 10 and g['pedido_cliente'] == 40 and g['sugerido'] == 30     # 40 pedido − 10 stock
    assert any(p['numero'] == 'PC-ZZ19-0001' for p in g['pedidos'])
    c = data[d19['CASCO']]
    assert c['stock'] == 0 and c['pedido_cliente'] == 0 and c['sugerido'] == 0          # sin pedido: nada sugerido


def test_abastecimiento_descuenta_lo_ya_pedido_en_otra_oc(admin, d19):
    pc = _sql("SELECT id FROM pedido_compra_pc WHERE numero = 'PC-ZZ19-0001'")[0][0]
    prov = _sql("""INSERT INTO proveedores (razon_social, ruc, direccion, condicion_pago, activo)
                   VALUES ('PROVEEDOR ZZ19', '20777777719', 'Av. 19', 'Contado', true) RETURNING id""")[0][0]
    r = admin.post('/compras/api/flujo/ordenes', json={
        'empresa_id': d19['emp'], 'proveedor_id': prov, 'almacen_entrega_id': d19['sede'], 'condicion_pago': 'Contado',
        'modalidad_entrega': 'Proveedor entrega', 'fecha_compromiso': '2026-10-25',
        'items': [{'producto_id': d19['GUANTE'], 'cantidad': 25, 'precio_unitario': 6, 'pedido_id': pc}]})
    assert r.status_code == 200, r.json
    oc_id = r.json['id']
    g = _abast(admin, d19, d19['GUANTE'])[d19['GUANTE']]
    assert g['pedido_cliente'] == 15 and g['ya_en_ordenes'] == 25 and g['sugerido'] == 5
    # Al corregir esa misma OC, su propia cantidad no se descuenta
    r = admin.get('/compras/api/flujo/abastecimiento', query_string={
        'empresa_id': str(d19['emp']), 'productos': str(d19['GUANTE']), 'oc_id': oc_id})
    assert r.json['data'][0]['pedido_cliente'] == 40


def test_abastecimiento_sin_productos_y_sin_sesion(admin, anonimo):
    assert admin.get('/compras/api/flujo/abastecimiento').json['data'] == []
    assert anonimo.get('/compras/api/flujo/abastecimiento?productos=1').status_code in (302, 401, 403)


def test_guias_y_facturas_traen_pc_y_guia(admin):
    _sql("""
        INSERT INTO guias_remision (serie, numero, fecha_emision, documento_asociado, destinatario_nombre, ruc_destinatario, estado_sunat)
        VALUES ('T019', '00000001', NOW(), 'COT-ZZ19-01', 'CLIENTE ZZ19', '20888888819', 'Emitida');
        INSERT INTO comprobantes (tipo_comprobante, serie, numero, fecha_emision, cliente_tipo_doc, cliente_nombre, cliente_numero_doc,
                                  subtotal, igv, total, documento_asociado, estado_sunat, items_json)
        VALUES ('Factura', 'F019', '1', NOW(), '6', 'CLIENTE ZZ19', '20888888819', 100, 18, 118, 'COT-ZZ19-01', 'Emitida', '[]'),
               ('Factura', 'F019', '2', NOW(), '6', 'CLIENTE ZZ19', '20888888819', 100, 18, 118, 'COT-ZZ19-01', 'Emitida', '[]');
        UPDATE comprobantes SET guia_vinculada = 'T019-OTRA', pc_vinculado = 'OC-CLIENTE-55' WHERE serie = 'F019' AND numero = '2';
    """, fetch=False)
    guia = next(g for g in admin.get('/ventas/api/guias/listar').json['data'] if g['serie'] == 'T019')
    assert guia['pc_numero'] == 'PC-ZZ19-0001'
    facs = {str(f['numero']).lstrip('0'): f for f in admin.get('/ventas/api/comprobantes/listar').json['data'] if f['serie'] == 'F019'}
    assert facs['1']['pc_numero'] == 'PC-ZZ19-0001' and facs['1']['guia_numero'] == 'T019-00000001'   # por la cotización
    assert facs['2']['pc_numero'] == 'OC-CLIENTE-55' and facs['2']['guia_numero'] == 'T019-OTRA'      # lo guardado manda


def test_pantallas_tienen_columnas_y_colores(admin):
    html = admin.get('/ventas').get_data(as_text=True)
    assert html.count('<th>N° PV (Pedido de venta)</th>') >= 2 and html.count('<th>N° Factura</th>') >= 2 and '<th>N° Guía</th>' in html
    assert '<th>Comprobante</th>\r\n                        <th>Origen</th>' not in html
    flujo = admin.get('/compras').get_data(as_text=True)
    assert 'id="ocAbast"' in flujo and 'A comprar al proveedor' in flujo
    css = admin.get('/static/css/compras_flujo.css').get_data(as_text=True)
    assert '.est-aprobada{background:#00C853' in css and 'background:#FFD600' in css
