"""
Finanzas ▸ Cuentas por cobrar (Erika 26/10/2026 21:31-21:32): N° PV y N° PC en columnas separadas, retención del
cliente con N°, fecha y monto, y la ventana "Registrar cobro" con PV, PC, retención y neto. Datos inventados, base local.
"""
from pathlib import Path

from tests.test_inventario import _sql

RAIZ = Path(__file__).resolve().parent.parent


def _factura_ret(serie, oc_cliente=''):
    return _sql("""INSERT INTO comprobantes (tipo_comprobante, serie, numero, fecha_emision, cliente_tipo_doc, cliente_nombre,
                                             cliente_numero_doc, subtotal, igv, total, tiene_retencion, monto_retenido, monto_a_pagar,
                                             estado_sunat, items_json, orden_compra_cliente)
                   VALUES ('Factura', %s, '9', '2026-10-01', '6', 'CLIENTE RET ZZ', '20888888866', 1000, 180, 1180,
                           true, 35.40, 1144.60, 'Emitida', '[]', %s) RETURNING id""", (serie, oc_cliente))[0][0]


def test_retencion_con_fecha_desde_registrar_cobro(admin):
    cid = _factura_ret('F0ZR', '4500012345')

    def fila():
        return next(x for x in admin.get('/finanzas/api/cxc?estado=todos&q=f0zr').json['data'] if x['id'] == cid)

    f = fila()
    assert f['oc_cliente'] == '4500012345' and f['retencion_fecha'] is None and f['saldo'] == 1144.6
    r = admin.post('/finanzas/api/retencion_cobro', json={'id': cid, 'retencion_numero': ' r001-00000077 ',
                                                          'retencion_fecha': '2026-10-05', 'retencion_monto': '35.40'})
    assert r.status_code == 200, r.json
    f = fila()
    assert f['retencion_numero'] == 'R001-00000077' and f['retencion_fecha'] == '2026-10-05' and f['retencion'] == 35.4
    # No toca el portal ni la fecha programada
    assert f['portal_ingresado'] is False and f['fecha_programada'] is None
    assert _sql("SELECT count(*) FROM erp_auditoria WHERE tabla = 'finanzas_seguimiento_cobro' AND registro_id = %s",
                (str(cid),))[0][0] >= 1
    # Fecha antes de la emisión, futura o monto mayor al total: no
    assert admin.post('/finanzas/api/retencion_cobro', json={'id': cid, 'retencion_fecha': '2026-09-01'}).status_code == 400
    assert admin.post('/finanzas/api/retencion_cobro', json={'id': cid, 'retencion_fecha': '2099-01-01'}).status_code == 400
    assert admin.post('/finanzas/api/retencion_cobro', json={'id': cid, 'retencion_monto': '5000'}).status_code == 400
    # El seguimiento (lápiz) también guarda la fecha
    r = admin.post('/finanzas/api/seguimiento_cobro', json={'id': cid, 'retencion_numero': 'R001-00000077',
                                                            'retencion_fecha': '2026-10-06', 'retencion_monto': '35.40'})
    assert r.status_code == 200, r.json
    assert fila()['retencion_fecha'] == '2026-10-06'


def test_pc_de_relleno_se_limpia_al_guardar_la_factura():
    from routes.ventas import limpiar_pc_cliente
    assert limpiar_pc_cliente('*****') == '' and limpiar_pc_cliente(' - ') == ''
    assert limpiar_pc_cliente('OC-20261023-0001') == ''
    assert limpiar_pc_cliente(' 4500012345 ') == '4500012345' and limpiar_pc_cliente(None) == ''


def test_pantalla_cxc_26oct():
    html = (RAIZ / 'templates' / 'finanzas.html').read_text(encoding='utf-8')
    js = (RAIZ / 'static' / 'js' / 'finanzas.js').read_text(encoding='utf-8')
    assert 'N° PV<small>Pedido de venta</small>' in html and 'N° PC<small>Pedido del cliente</small>' in html
    assert 'Retención 3%<small>N° · fecha · monto</small>' in html and 'Portal y pago' not in html
    assert 'id="pagoRetNum"' in html and 'id="pagoRetFecha"' in html and 'id="pagoRetMonto"' in html
    assert "fila('N° PV (Pedido de venta)'" in js and "fila('N° PC (Pedido del cliente)'" in js
    assert "fila('Monto a cobrar neto'" in js and "'/finanzas/api/retencion_cobro'" in js
    assert 'function pcCliente' in js and 'id="segRetFecha"' in js


def test_un_comprobante_de_retencion_cubre_varias_facturas(admin):
    # Como el R001-00010077 de Cummins: dos facturas E001 en un solo comprobante, cada una con su monto real
    a, b = _factura_ret('F0ZM'), _factura_ret('F0ZN')
    for cid, monto in ((a, '32.53'), (b, '50.00')):
        r = admin.post('/finanzas/api/retencion_cobro', json={'id': cid, 'retencion_numero': 'R001-00099077',
                                                              'retencion_fecha': '2026-10-10', 'retencion_monto': monto})
        assert r.status_code == 200, r.json
    filas = {x['id']: x for x in admin.get('/finanzas/api/cxc?estado=todos&q=r001-00099077').json['data']}
    assert filas[a]['retencion'] == 32.53 and filas[b]['retencion'] == 50
    # El monto real (50, no el 3% = 35.40) es el que rebaja el saldo
    assert filas[b]['saldo'] == 1130


def test_fecha_real_de_pago_es_la_del_aviso_y_se_ve_en_cobros(admin):
    cid = _factura_ret('F0ZQ')
    r = admin.post('/finanzas/api/movimientos', json={'tipo': 'COBRO', 'documento_id': cid, 'monto': 1144.60,
                                                      'fecha': '2026-10-20', 'metodo': 'Transferencia', 'banco': 'BCP',
                                                      'fecha_aviso': '2026-10-18'})
    assert r.status_code == 200, r.json
    f = next(x for x in admin.get('/finanzas/api/cxc?estado=todos&q=f0zq').json['data'] if x['id'] == cid)
    assert f['saldo'] == 0 and f['fecha_pago_real'] == '2026-10-18'
    admin.post('/finanzas/api/retencion_cobro', json={'id': cid, 'retencion_numero': 'R001-00000555', 'retencion_monto': '35.40'})
    m = next(x for x in admin.get('/finanzas/api/movimientos?tipo=COBRO&q=F0ZQ').json['data'] if x['documento_id'] == cid)
    assert m['retencion_numero'] == 'R001-00000555' and m['retencion_monto'] == 35.4 and m['fecha_aviso'] == '2026-10-18'
