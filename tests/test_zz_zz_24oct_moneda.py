"""
Soles y dólares con tipo de cambio (Erika 24/10/2026 18:17): "ordenes de compra debe estar en tipo de cambio porque a veces
vendo y compro en dolares / en kcf tengo cuenta soles / en agd tengo cuenta en soles y dolares / los proveedores venden en
dolares y me dan su tipo de cambio para pagar en soles". Datos inventados, solo en la base local.
"""
from decimal import Decimal
from pathlib import Path

import pytest

from routes.moneda import (codigo_moneda, leer_tc, pago_en_moneda, en_soles, ErrorMoneda, moneda_documento,
                           asegurar_moneda)
from tests.test_inventario import _sql

RAIZ = Path(__file__).resolve().parent.parent


def test_lectura_de_moneda_y_tc():
    assert codigo_moneda('Dólares ($)') == 'USD' and codigo_moneda('US$') == 'USD' and codigo_moneda('USD') == 'USD'
    assert codigo_moneda('Soles (S/.)') == 'PEN' and codigo_moneda('S/') == 'PEN' and codigo_moneda(None) == 'PEN'
    assert leer_tc('3,75') == Decimal('3.7500')         # coma decimal
    assert leer_tc('') is None
    with pytest.raises(ErrorMoneda):
        leer_tc('37.5')                                  # fuera de rango (error de tipeo)
    with pytest.raises(ErrorMoneda):
        leer_tc('', obligatorio=True)
    assert en_soles(100, 'USD', Decimal('3.8')) == Decimal('380.00')
    assert en_soles(100, 'USD', None) is None            # sin TC no se inventa
    # Deuda en dólares pagada en soles con el TC del proveedor
    monto_doc, mon, tc, pagado = pago_en_moneda('USD', {'monto_pagado': '380', 'moneda_pago': 'PEN', 'tipo_cambio': '3.80'})
    assert (monto_doc, mon, tc, pagado) == (Decimal('100.00'), 'PEN', Decimal('3.8000'), Decimal('380.00'))
    with pytest.raises(ErrorMoneda):
        pago_en_moneda('USD', {'monto_pagado': '380', 'moneda_pago': 'PEN'})   # falta el TC


@pytest.fixture(scope='module')
def usd(app):
    asegurar_moneda()
    for cod, ruc in (('KCF', '20111111111'), ('AGD', '20222222222')):
        _sql("""INSERT INTO erp_empresas (codigo, nombre_corto, nombre_comercial, razon_social, ruc, estado,
                                         color_primario, color_secundario, color_pastel)
                SELECT %s, %s, %s, %s, %s, 'activo', '#D6243A', '#1D1A1F', '#FDE8EB' WHERE NOT EXISTS (SELECT 1 FROM erp_empresas WHERE codigo = %s)""",
             (cod, cod, cod, cod + ' S.A.C.', ruc, cod), fetch=False)
    _sql("""INSERT INTO almacenes (codigo, nombre, direccion, activo)
            SELECT 'SMP', 'San Martín de Porres', 'Av. Perú 123', true WHERE NOT EXISTS (SELECT 1 FROM almacenes WHERE codigo='SMP')""",
         fetch=False)
    _sql("""INSERT INTO productos (familia, codigo, descripcion, marca, unidad, costo_unitario, precio_unitario, stock, activo)
            VALUES ('GENERAL', 'USD-001', 'GUANTE IMPORTADO ZZ', 'ZZ', 'UND', 0, 10, 0, true)""", fetch=False)
    _sql("""INSERT INTO proveedores (razon_social, ruc, direccion, banco, numero_cuenta, cci, condicion_pago, activo)
            VALUES ('IMPORTA DOLAR ZZ S.A.C.', '20577777771', 'Av. Lima 1', 'BBVA', '0011-0222-33', '01102200000033', 'Contado', true)""",
         fetch=False)
    # TC SUNAT ya guardado (en las pruebas no se consulta internet)
    _sql("INSERT INTO tipo_cambio_dia (fecha, compra, venta, fuente) VALUES ('2026-10-20', 3.74, 3.76, 'prueba') ON CONFLICT DO NOTHING",
         fetch=False)
    emp = dict(_sql("SELECT codigo, id FROM erp_empresas WHERE codigo IN ('KCF', 'AGD')"))
    return {'KCF': emp['KCF'], 'AGD': emp['AGD'], 'SMP': _sql("SELECT id FROM almacenes WHERE codigo='SMP'")[0][0],
            'prod': _sql("SELECT id FROM productos WHERE codigo='USD-001'")[0][0],
            'prov': _sql("SELECT id FROM proveedores WHERE ruc='20577777771'")[0][0]}


def _oc(usd, **extra):
    body = {'empresa_id': usd['AGD'], 'proveedor_id': usd['prov'], 'almacen_entrega_id': usd['SMP'],
            'condicion_pago': 'Contado', 'modalidad_entrega': 'Proveedor entrega', 'fecha_compromiso': '2026-10-30',
            'motivo_compra': 'Stock estratégico', 'motivo_stock': 'Stock estratégico',
            'items': [{'producto_id': usd['prod'], 'cantidad': 10, 'precio_unitario': 10}]}
    body.update(extra)
    return body


def test_oc_en_dolares_pago_en_soles_y_factura(usd, admin):
    # Sin TC no se guarda una OC en dólares
    r = admin.post('/compras/api/flujo/ordenes', json=_oc(usd, moneda='USD'))
    assert r.status_code == 400 and 'tipo de cambio' in r.get_json()['error']
    r = admin.post('/compras/api/flujo/ordenes', json=_oc(usd, moneda='USD', tipo_cambio='3,75', enviar=True))
    assert r.status_code == 200, r.get_json()
    oc_id = r.get_json()['id']
    det = admin.get(f'/compras/api/flujo/ordenes/{oc_id}').get_json()['data']
    assert det['moneda'] == 'USD' and float(det['tipo_cambio']) == 3.75 and det['total'] == pytest.approx(118)
    if det['estado'] == 'Por aprobar':
        assert admin.post(f'/compras/api/flujo/ordenes/{oc_id}/aprobar', json={'aprobar': True}).status_code == 200
    # El PDF para el proveedor sale en US$
    assert 'US$ ' in admin.get(f'/compras/flujo/ordenes/{oc_id}/imprimir').get_data(as_text=True)
    # AGD no tiene cuenta en dólares registrada: no se puede pagar en dólares
    r = admin.post(f'/compras/api/flujo/ordenes/{oc_id}/pago',
                   json={'monto_pagado': 50, 'moneda_pago': 'USD', 'metodo': 'Transferencia', 'numero_operacion': 'ZZ1'})
    assert r.status_code == 400 and 'dólares' in r.get_json()['error']
    # Se paga en soles con el TC que da el proveedor (3.80): S/ 228 = US$ 60 de la deuda
    r = admin.post(f'/compras/api/flujo/ordenes/{oc_id}/pago',
                   json={'monto_pagado': 228, 'moneda_pago': 'PEN', 'tipo_cambio': '3.80', 'metodo': 'Transferencia',
                         'numero_operacion': 'ZZ2', 'fecha': '2026-10-20'})
    assert r.status_code == 200, r.get_json()
    pago = _sql("""SELECT monto, moneda_pago, tipo_cambio, monto_pagado FROM finanzas_pagos
                   WHERE numero_operacion = 'ZZ2'""")[0]
    assert (float(pago[0]), pago[1], float(pago[2]), float(pago[3])) == (60.0, 'PEN', 3.8, 228.0)
    det = admin.get(f'/compras/api/flujo/ordenes/{oc_id}').get_json()['data']
    assert det['pagado'] == pytest.approx(60) and det['pagos'][0]['moneda_pago'] == 'PEN'
    # Si con el TC se pasa del saldo, no se acepta
    r = admin.post(f'/compras/api/flujo/ordenes/{oc_id}/pago',
                   json={'monto_pagado': 500, 'moneda_pago': 'PEN', 'tipo_cambio': '3.80', 'metodo': 'Transferencia',
                         'numero_operacion': 'ZZ3'})
    assert r.status_code == 400
    # Factura del proveedor en dólares: pide su TC (va al registro de compras en soles)
    _sql("UPDATE ordenes_compra SET estado = 'Recibida' WHERE id = %s", (oc_id,), fetch=False)
    _sql("UPDATE ordenes_compra_items SET cantidad_recibida = cantidad WHERE orden_compra_id = %s", (oc_id,), fetch=False)
    fac = {'tipo': 'Factura', 'numero': 'F001-00009901', 'fecha': '2026-10-20', 'monto': 118}
    r = admin.post(f'/compras/api/flujo/ordenes/{oc_id}/factura', json=fac)
    assert r.status_code == 400 and 'tipo de cambio' in r.get_json()['error']
    r = admin.post(f'/compras/api/flujo/ordenes/{oc_id}/factura', json={**fac, 'tipo_cambio': '3.76'})
    assert r.status_code == 200, r.get_json()
    f = _sql("SELECT moneda, tipo_cambio, empresa_id FROM comprobantes_proveedor WHERE numero = 'F001-00009901'")[0]
    assert f[0] == 'USD' and float(f[1]) == 3.76
    # Cuentas por pagar: el saldo sigue en dólares y el total de arriba va en soles con su TC
    from routes.finanzas import totales_cxp
    antes = admin.get('/api/empresa_activa').get_json()['codigo']
    admin.post('/api/empresa_activa', json={'codigo': 'AGD'})
    try:
        cxp = [x for x in admin.get('/finanzas/api/cxp?estado=todos&q=F001-00009901').get_json()['data']
               if x['documento'] == 'F001-00009901']
    finally:
        admin.post('/api/empresa_activa', json={'codigo': antes})
    assert cxp and cxp[0]['moneda'] == 'USD' and cxp[0]['saldo'] == pytest.approx(58)
    assert cxp[0]['saldo_soles'] == pytest.approx(58 * 3.76)
    assert totales_cxp(cxp)['total'] == pytest.approx(round(58 * 3.76, 2)) and totales_cxp(cxp)['usd'] == pytest.approx(58)
    # SUNAT: el registro de compras va en soles con el TC de la factura
    from routes.sunat import compras_erp
    doc = next(d for d in compras_erp(f[2], __import__('datetime').date(2026, 10, 1), __import__('datetime').date(2026, 10, 31))
               if d['serie'] == 'F001' and str(d.get('numero') or '').lstrip('0') == '9901')
    assert float(doc['total']) == pytest.approx(118 * 3.76) and doc['moneda'] == 'USD'


def test_finanzas_pago_en_soles_de_factura_en_dolares(usd, admin):
    cp = _sql("SELECT id FROM comprobantes_proveedor WHERE numero = 'F001-00009901'")[0][0]
    r = admin.post('/finanzas/api/movimientos', json={'tipo': 'PAGO', 'documento_id': cp, 'monto_pagado': 100,
                                                      'moneda_pago': 'PEN', 'tipo_cambio': '4', 'metodo': 'Transferencia',
                                                      'numero_operacion': 'ZZ4'})
    assert r.status_code == 200, r.get_json()
    assert 'US$' in r.get_json()['message'] and r.get_json()['data']['saldo'] == pytest.approx(33)
    fila = _sql("SELECT monto, moneda_pago, monto_pagado FROM finanzas_pagos WHERE numero_operacion = 'ZZ4'")[0]
    assert (float(fila[0]), fila[1], float(fila[2])) == (25.0, 'PEN', 100.0)


def test_documento_de_venta_en_dolares(usd):
    # Sin moneda en el formulario: la del origen (PV / cotización)
    assert moneda_documento({}, respaldo={'moneda': 'USD', 'tipo_cambio': '3.7'}) == ('USD', Decimal('3.7000'))
    assert moneda_documento({'moneda': 'Soles (S/)'}, respaldo={'moneda': 'USD', 'tipo_cambio': '3.7'}) == ('PEN', None)
    # Factura: TC SUNAT de la fecha de emisión si no se escribe
    assert moneda_documento({'moneda': 'USD'}, fecha='2026-10-20', tc_sunat_por_defecto=True) == ('USD', Decimal('3.7600'))
    with pytest.raises(ErrorMoneda):
        moneda_documento({'moneda': 'Dólares ($)'})


def test_cotizacion_y_factura_en_dolares(usd, admin):
    cli = _sql("""INSERT INTO clientes (razon_social, numero_documento, tipo_documento, direccion_fiscal)
                  VALUES ('CLIENTE DOLAR ZZ', '20599999991', 'RUC', 'Av. Uno 1') RETURNING id""")[0][0]
    body = {'estado': 'Borrador', 'cliente_id': cli, 'ruc': '20599999991', 'razon': 'CLIENTE DOLAR ZZ',
            'condicion_pago': 'Contado', 'tiempo_entrega': 'Inmediato', 'validez': '15 días', 'transporte': 'Incluido',
            'parihuela': 'No', 'moneda': 'Dólares ($)',
            'productos': [{'codigo': 'USD-001', 'producto': 'GUANTE IMPORTADO ZZ', 'cantidad': 2, 'valorVenta': 10}]}
    r = admin.post('/ventas/api/cotizaciones/guardar', json=body)
    assert r.status_code == 400 and 'tipo de cambio' in r.get_json()['error']
    r = admin.post('/ventas/api/cotizaciones/guardar', json={**body, 'tipo_cambio': '3.77'})
    assert r.status_code == 200, r.get_json()
    cid = r.get_json().get('id') or (r.get_json().get('data') or {}).get('id')
    fila = _sql("SELECT moneda, tipo_cambio FROM cotizaciones WHERE id = %s", (cid,))[0]
    assert fila[0] == 'USD' and float(fila[1]) == 3.77
    # Factura de venta en dólares sin TC escrito: TC SUNAT de la fecha de emisión
    r = admin.post('/ventas/api/comprobantes/guardar', json={
        'tipo': 'Factura', 'serie': 'F0ZU', 'fecha_emision': '2026-10-20', 'moneda': 'USD', 'cliente': 'CLIENTE DOLAR ZZ',
        'ruc': '20599999991', 'monto': 23.6, 'total': 23.6, 'subtotal': 20, 'igv': 3.6, 'condicion': 'Contado',
        'items': [{'codigo': 'USD-001', 'producto': 'GUANTE IMPORTADO ZZ', 'cantidad': 2, 'valorVenta': 10}]})
    assert r.status_code == 200, r.get_json()
    f = _sql("SELECT moneda, tipo_cambio FROM comprobantes WHERE serie = 'F0ZU' ORDER BY id DESC LIMIT 1")[0]
    assert f[0] == 'USD' and float(f[1]) == 3.76


def test_pantallas_con_moneda():
    js = (RAIZ / 'static/js/moneda.js').read_text(encoding='utf-8')
    assert 'window.Moneda' in js and '/api/tipo_cambio' in js
    assert 'moneda.js' in (RAIZ / 'templates/base.html').read_text(encoding='utf-8')
    flujo = (RAIZ / 'templates/compras/flujo.html').read_text(encoding='utf-8')
    for t in ('id="ocMoneda"', 'id="ocTC"', 'id="pagoMonedaPago"', 'id="pagoTC"', 'id="facTC"'):
        assert t in flujo, t
    ventas = (RAIZ / 'static/js/ventas.js').read_text(encoding='utf-8')
    for t in ('id="fTC"', 'id="pcTC"', 'id="compMoneda"', 'function ponerMonedaPC'):
        assert t in ventas, t
    assert 'id="pagoMonedaPago"' in (RAIZ / 'templates/finanzas.html').read_text(encoding='utf-8')
