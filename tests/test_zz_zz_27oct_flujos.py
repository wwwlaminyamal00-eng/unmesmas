"""
Prompt de Adriel aprobado por Erika (27/10/2026): estados de compra, cotización con PV despachado, guía → factura
con precios del PV, PDF de la guía con números vigentes, "Qué hacer hoy" y resumen de la cotización.
Datos inventados, solo en la base local.
"""
import json
from pathlib import Path

from tests.test_inventario import _sql

RAIZ = Path(__file__).resolve().parent.parent


def _producto(codigo):
    _sql("""INSERT INTO productos (familia, codigo, descripcion, marca, unidad, costo_unitario, precio_unitario, stock, activo)
            SELECT 'GENERAL', %s, %s, 'ZZ', 'UND', 0, 100, 0, true WHERE NOT EXISTS (SELECT 1 FROM productos WHERE codigo = %s)""",
         (codigo, 'MUEBLE DE MADERA ' + codigo, codigo), fetch=False)
    return _sql("SELECT id FROM productos WHERE codigo = %s", (codigo,))[0][0]


def _pv(numero, codigo, cantidad, dias, **extra):
    items = [{'codigo': codigo, 'producto': extra.pop('producto', 'Mueble de madera'), 'cantidad_pc': cantidad,
              'precio_pc': extra.pop('precio', 250)}]
    _sql("DELETE FROM pedido_compra_pc WHERE numero = %s", (numero,), fetch=False)
    return _sql("""INSERT INTO pedido_compra_pc (numero, cliente, ruc, estado, items_json, fecha, cotizacion_numero, oc_cliente)
                   VALUES (%s, 'CLIENTE 27OCT', '20100070970', 'Pendiente', %s, NOW() - %s * INTERVAL '1 day', %s, %s) RETURNING id""",
                (numero, json.dumps(items), dias, extra.get('cot'), extra.get('pc_cliente')))[0][0]


def _stock(prod, cantidad):
    emp = _sql("SELECT id FROM erp_empresas ORDER BY codigo LIMIT 1")[0][0]
    alm = _sql("SELECT id FROM almacenes ORDER BY id LIMIT 1")[0][0]
    _sql("DELETE FROM inv_stock WHERE producto_id = %s", (prod,), fetch=False)
    _sql("INSERT INTO inv_stock (empresa_id, almacen_id, producto_id, cantidad) VALUES (%s, %s, %s, %s)",
         (emp, alm, prod, cantidad), fetch=False)


def test_lo_recibido_para_un_pv_queda_para_ese_pv(admin):
    # Hellen compró y recibió 10 para el PV nuevo; un PV más antiguo sin compra no se lo lleva
    prod = _producto('ZZ27-A')
    _stock(prod, 10)
    viejo = _pv('PV-ZZ27-VIEJO', 'ZZ27-A', 10, 5)
    nuevo = _pv('PV-ZZ27-NUEVO', 'ZZ27-A', 10, 1)
    oc = _sql("""INSERT INTO ordenes_compra (numero_orden, estado, total) VALUES ('OC-ZZ27-0001', 'Recibida', 1000) RETURNING id""")[0][0]
    _sql("""INSERT INTO ordenes_compra_items (orden_compra_id, producto_id, producto, cantidad, cantidad_recibida, pedido_id)
            VALUES (%s, %s, 'MUEBLE ZZ27', 10, 10, %s)""", (oc, prod, nuevo), fetch=False)
    est = admin.get('/api/abastecimiento/pc').json['data']
    assert est[str(nuevo)]['estado'] == 'Con stock'
    assert est[str(viejo)]['estado'] == 'Pendiente por compra'


def test_cotizacion_con_pv_despachado_no_dice_pendiente_de_compra(admin):
    prod = _producto('ZZ27-B')
    _stock(prod, 0)
    _sql("DELETE FROM cotizaciones WHERE codigo_cotizacion = 'COT-ZZ27-B'", fetch=False)
    cli = _sql("SELECT id FROM clientes ORDER BY id LIMIT 1")[0][0]
    usu = _sql("SELECT id FROM usuarios ORDER BY id LIMIT 1")[0][0]
    cot = _sql("""INSERT INTO cotizaciones (numero_cotizacion, codigo_cotizacion, cliente_id, usuario_id, estado, subtotal, igv, total)
                  VALUES ('COT-ZZ27-B', 'COT-ZZ27-B', %s, %s, 'Aceptada por Cliente', 100, 18, 118) RETURNING id""", (cli, usu))[0][0]
    _sql("INSERT INTO cotizacion_detalle (cotizacion_id, producto_id, cantidad) VALUES (%s, %s, 5)", (cot, prod), fetch=False)
    pv = _pv('PV-ZZ27-B', 'ZZ27-B', 5, 1, cot='COT-ZZ27-B')
    assert admin.get('/api/abastecimiento/cotizaciones').json['data'][str(cot)]['estado'] == 'Pendiente por compra'
    _sql("DELETE FROM despachos WHERE numero = 'DES-ZZ27-B'", fetch=False)
    _sql("""INSERT INTO despachos (numero, pc_id, pc_numero, estado, cliente, ruc) VALUES ('DES-ZZ27-B', %s, 'PV-ZZ27-B', 'Despachado', 'CLIENTE ZZ27', '20000000001')""",
         (pv,), fetch=False)
    assert admin.get('/api/abastecimiento/cotizaciones').json['data'][str(cot)]['estado'] == 'Despachado'
    assert admin.get('/api/abastecimiento/pc').json['data'][str(pv)]['estado'] == 'Despachado'
    # Compras ▸ Pedidos por comprar: lo despachado ya no se pide
    peds = {p['id']: p for p in admin.get('/compras/api/flujo/pedidos', query_string={'todos': '1'}).json['data']}
    assert pv not in peds or peds[pv]['items'][0]['falta'] == 0
    _sql("UPDATE despachos SET estado = 'Entregado' WHERE numero = 'DES-ZZ27-B'", fetch=False)
    assert admin.get('/api/abastecimiento/cotizaciones').json['data'][str(cot)]['estado'] == 'Entregado'


def test_factura_desde_guia_trae_precios_y_descripcion_del_pv(admin):
    _producto('ZZ27-C')
    _pv('PV-ZZ27-C', 'ZZ27-C', 4, 1, producto='Mueble de madera express', precio=250, cot='COT-ZZ27-C', pc_cliente='4500099999')
    items = [{'codigo': 'ZZ27-C', 'producto': 'Mueble de madera', 'cantidad': 4, 'um': 'NIU'}]
    guia = _sql("""INSERT INTO guias_remision (serie, numero, ruc_destinatario, destinatario_nombre, documento_asociado,
                                                orden_compra_cliente, items_json)
                   VALUES ('T001', '00027001', '20100070970', 'CLIENTE 27OCT', 'PV-ZZ27-C', 'PC-KCF-000001', %s) RETURNING id""",
                (json.dumps(items),))[0][0]
    r = admin.get(f'/ventas/api/guias/{guia}/para-factura')
    assert r.status_code == 200, r.json
    d = r.json['data']
    assert d['pv'] == 'PV-ZZ27-C' and d['pc_cliente'] == '4500099999' and d['cotizacion'] == 'COT-ZZ27-C'
    it = d['items'][0]
    assert it['cantidad'] == 4 and it['valorVenta'] == 250 and it['producto'] == 'Mueble de madera express'
    assert d['subtotal'] == 1000 and d['total'] == 1180 and not d['sin_precio']
    # PDF de la guía: números vigentes del PV (no lo que se copió al crearla)
    from routes.ventas import enriquecer_pdf_guia
    with admin.application.app_context():
        datos = enriquecer_pdf_guia(dict(documento_asociado='PV-ZZ27-C', numero='00027001',
                                         orden_compra_cliente='PC-KCF-000001'), {})
    assert datos['orden_compra_cliente'] == '4500099999' and datos['nro_cotizacion'] == 'COT-ZZ27-C'
    assert datos['nro_pv'] == 'PV-ZZ27-C'


def test_que_hacer_hoy_sin_alertas_de_control(admin):
    r = admin.get('/compras/api/flujo/resumen')
    assert r.status_code == 200, r.json
    textos = ' '.join(a['texto'] for a in r.json['alertas'])
    assert 'aprobadas por la misma persona' not in textos and 'pago(s) sin factura' not in textos


def test_pantallas_27oct():
    js = (RAIZ / 'static/js/ventas.js').read_text(encoding='utf-8')
    assert '/completa`' in js and "'ítems'" in js and '🏷 Descuento' in js and 'COT-${String(Date.now())' not in js
    assert '>Ver OC</button>' in js and "'Despachado': '✔ Despachado'" in js
    assert '/para-factura`' in js and 'async function usarProductosDelPV' in js
    cjs = (RAIZ / 'static/js/compras_flujo.js').read_text(encoding='utf-8')
    assert "qs.get('oc')" in cjs
    pdf = (RAIZ / 'pdf_generator.py').read_text(encoding='utf-8')
    assert 'PV (PEDIDO DE VENTA):' in pdf


def test_adelanto_porcentaje_helpers():
    from decimal import Decimal
    from routes.compras_flujo import pct_adelanto, monto_adelanto
    assert pct_adelanto({'condicion_pago': 'Crédito 30 días', 'adelanto_pct': 50}) == Decimal('50')
    assert pct_adelanto({'condicion_pago': 'Adelanto 50%'}) == Decimal('50')
    assert pct_adelanto({'condicion_pago': 'Crédito 30 días'}) == 0
    assert monto_adelanto('99.10', 50) == Decimal('49.55') and monto_adelanto(200, 30) == Decimal('60.00')


def test_oc_credito_con_adelanto_50_en_pdf_y_pago(admin):
    # Erika 27/10/2026 (OC a PROTENCO "Crédito 30 días"): debajo del IGV, el adelanto y lo que se paga a crédito
    emp = _sql("SELECT id FROM erp_empresas ORDER BY id LIMIT 1")[0][0]
    alm = _sql("SELECT id FROM almacenes WHERE COALESCE(activo, true) ORDER BY id LIMIT 1")[0][0]
    _sql("""INSERT INTO proveedores (razon_social, ruc, direccion, condicion_pago, activo)
            SELECT 'ADELANTO ZZ27 S.A.C.', '20599999927', 'Av. Lima 27', 'Crédito', true
            WHERE NOT EXISTS (SELECT 1 FROM proveedores WHERE ruc = '20599999927')""", fetch=False)
    prov = _sql("SELECT id FROM proveedores WHERE ruc = '20599999927'")[0][0]
    prod = _producto('ZZ27-ADEL')
    body = {'empresa_id': emp, 'proveedor_id': prov, 'almacen_entrega_id': alm, 'condicion_pago': 'Crédito',
            'dias_credito': 30, 'adelanto_pct': 50, 'modalidad_entrega': 'Proveedor entrega', 'fecha_compromiso': '2026-10-30',
            'motivo_compra': 'Stock estratégico', 'motivo_stock': 'Stock estratégico',
            'items': [{'producto_id': prod, 'cantidad': 1, 'precio_unitario': 100}]}
    r = admin.post('/compras/api/flujo/ordenes', json={**body, 'adelanto_pct': 150})
    assert r.status_code == 400
    r = admin.post('/compras/api/flujo/ordenes', json={**body, 'enviar': True})
    assert r.status_code == 200, r.get_json()
    oc_id = r.get_json()['id']
    det = admin.get(f'/compras/api/flujo/ordenes/{oc_id}').get_json()['data']
    assert det['adelanto_pct'] == 50 and det['adelanto'] == 59 and det['condicion_pago'] == 'Crédito 30 días'
    if det['estado'] == 'Por aprobar':
        assert admin.post(f'/compras/api/flujo/ordenes/{oc_id}/aprobar', json={'aprobar': True}).status_code == 200
    html = admin.get(f'/compras/flujo/ordenes/{oc_id}/imprimir').get_data(as_text=True)
    assert 'Adelanto 50% (antes de la entrega)' in html and 'Saldo 50% a crédito 30 días' in html and '59.00' in html
    det = admin.get(f'/compras/api/flujo/ordenes/{oc_id}').get_json()['data']
    assert det['paso']['codigo'] == 'pagar' and '50%' in det['paso']['texto'] and det['falta_adelanto'] == 59
    # Contado no lleva adelanto aparte (ya es todo antes)
    r = admin.post('/compras/api/flujo/ordenes', json={**body, 'condicion_pago': 'Contado', 'items': [
        {'producto_id': prod, 'cantidad': 2, 'precio_unitario': 100}]})
    assert r.status_code == 200, r.get_json()
    assert float(_sql("SELECT adelanto_pct FROM ordenes_compra WHERE id = %s", (r.get_json()['id'],))[0][0]) == 0
