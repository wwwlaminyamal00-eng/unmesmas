"""
Ventas ▸ Entregas más simple (Erika 23/10/2026 04:35: "aqui es un si"): cantidad y producto en una casilla,
distrito en vez de la dirección completa, comentario corto editable en la fila y filtros por distrito y fecha de cita.
Datos inventados, solo en la base local.
"""
import json
from pathlib import Path

from routes.ventas import adivinar_distrito
from tests.test_inventario import _sql

RAIZ = Path(__file__).resolve().parent.parent


def test_distrito_sale_de_la_direccion():
    assert adivinar_distrito('AV. NICOLAS DE PIEROLA NRO 346 CERCADO DE LIMA') == 'Cercado de Lima'
    assert adivinar_distrito('RECOJO SMP') == 'San Martín de Porres'
    assert adivinar_distrito('JR. LAS ALMENDRAS 284 LIMA - LIMA - SAN MARTIN DE PORRES') == 'San Martín de Porres'
    # El distrito va al final: la avenida con nombre de distrito no confunde
    assert adivinar_distrito('AV. INDEPENDENCIA 123 - SAN ISIDRO') == 'San Isidro'
    assert adivinar_distrito('Av. Los Próceres, San Juan de Miraflores') == 'San Juan de Miraflores'
    assert adivinar_distrito('PQ. INDUSTRIAL PARC II MZA. F1 LOTE 4A') == ''
    assert adivinar_distrito(None) == ''


def test_distrito_y_comentario_en_la_fila(vendedor):
    items = json.dumps([{'producto': 'CASCO ZZ', 'cantidad': 3.0}, {'producto': 'GUANTE ZZ', 'cantidad': 1.5}])
    _sql("""INSERT INTO despachos (numero, cliente, ruc, estado, destino, items_json)
            VALUES ('DSP-ZZE-1', 'CLIENTE', '20100070970', 'Pendiente despacho', 'AV. ARGENTINA 4793 - CALLAO', %s)""",
         (items,), fetch=False)
    did = _sql("SELECT id FROM despachos WHERE numero = 'DSP-ZZE-1'")[0][0]

    def fila():
        return next(d for d in vendedor.get('/ventas/api/despachos/listar').json['data'] if d['id'] == did)

    f = fila()
    assert f['distrito'] == 'Callao' and f['distrito_escrito'] is False and f['comentario'] == ''
    assert [i['producto'] for i in f['items']] == ['CASCO ZZ', 'GUANTE ZZ']
    # El usuario corrige el distrito (se escribe igual que en la lista aunque lo pongan sin tildes)
    r = vendedor.post(f'/ventas/api/despachos/{did}/dato', json={'campo': 'distrito', 'valor': 'breña'})
    assert r.status_code == 200 and r.json['data']['distrito'] == 'Breña'
    r = vendedor.post(f'/ventas/api/despachos/{did}/dato', json={'campo': 'comentario', 'valor': '  Llamar  antes a Juan '})
    assert r.json['data']['comentario'] == 'Llamar antes a Juan'
    f = fila()
    assert f['distrito'] == 'Breña' and f['distrito_escrito'] is True and f['comentario'] == 'Llamar antes a Juan'
    # Corto: más de 120 letras no se guarda; otros campos no se pueden cambiar por aquí
    assert vendedor.post(f'/ventas/api/despachos/{did}/dato', json={'campo': 'comentario', 'valor': 'x' * 121}).status_code == 400
    assert vendedor.post(f'/ventas/api/despachos/{did}/dato', json={'campo': 'estado', 'valor': 'Despachado'}).status_code == 400
    assert vendedor.post('/ventas/api/despachos/999999/dato', json={'campo': 'comentario', 'valor': 'a'}).status_code == 404
    # Vacío lo borra y el distrito vuelve a leerse de la dirección
    vendedor.post(f'/ventas/api/despachos/{did}/dato', json={'campo': 'distrito', 'valor': ''})
    assert fila()['distrito'] == 'Callao'


def test_pantalla_de_entregas_23oct():
    html = (RAIZ / 'templates/ventas/index.html').read_text(encoding='utf-8')
    tabla = html[html.index('<div id="despachar"'):]
    tabla = tabla[:tabla.index('</thead>')]
    for t in ('id="despachoDistrito"', 'id="despachoCita"', 'id="despachoCitaFecha"', '<th>Cantidad y producto</th>',
              '<th>Comentario</th>', 'Elegir fecha de cita'):
        assert t in tabla, t
    assert '<th>Lugar entrega</th>' not in tabla
    js = (RAIZ / 'static/js/ventas.js').read_text(encoding='utf-8')
    for t in ('function productosDespachoHTML', 'function distritoDespachoHTML', 'title="Dirección: ${dir}"',
              'function comentarioDespachoHTML', "`/ventas/api/despachos/${id}/dato`", 'function pasaFiltroCita',
              'function llenarFiltroDistrito', 'colspan="15"'):
        assert t in js, t


# ---------------------------------------------------------------- Seguimiento del cobro (Erika 23/10/2026, de su Excel)
def test_seguimiento_del_cobro_en_cuentas_por_cobrar(app, admin, vendedor):
    from datetime import date
    from routes.sunat import retenciones_sugeridas
    cid = _sql("""INSERT INTO comprobantes (tipo_comprobante, serie, numero, fecha_emision, cliente_tipo_doc, cliente_nombre,
                                            cliente_numero_doc, subtotal, igv, total, tiene_retencion, monto_retenido, monto_a_pagar,
                                            estado_sunat, items_json)
                  VALUES ('Factura', 'F0ZS', '7', '2031-03-02', '6', 'CLIENTE SEG ZZ', '20888888877', 1000, 180, 1180,
                          true, 35.40, 1144.60, 'Emitida', '[]') RETURNING id""")[0][0]
    _sql("""INSERT INTO finanzas_pagos (tipo, documento_tabla, documento_id, fecha, monto, estado)
            VALUES ('COBRO', 'comprobantes', %s, '2031-03-20', 100, 'Registrado')""", (cid,), fetch=False)

    def fila():
        return next(x for x in admin.get('/finanzas/api/cxc?estado=todos&q=f0zs').json['data'] if x['id'] == cid)

    f = fila()
    assert f['portal_ingresado'] is False and f['retencion'] == 35.4 and f['saldo'] == 1044.6 and f['retencion_numero'] is None
    r = admin.post('/finanzas/api/seguimiento_cobro', json={
        'id': cid, 'portal_ingresado': True, 'portal_fecha': '2031-03-03', 'fecha_programada': '2031-04-15',
        'retencion_numero': ' r001-00006805 ', 'retencion_monto': '35'})
    assert r.status_code == 200, r.json
    f = fila()
    assert f['portal_ingresado'] is True and f['portal_fecha'] == '2031-03-03' and f['fecha_programada'] == '2031-04-15'
    # La retención anotada manda: saldo = 1180 - 35 - 100 cobrado
    assert f['retencion_numero'] == 'R001-00006805' and f['retencion'] == 35 and f['saldo'] == 1045
    assert admin.get('/finanzas/api/cxc?estado=todos&q=r001-00006805').json['data'][0]['id'] == cid
    # Cuadra con SUNAT: la retención del mes del primer cobro es la anotada
    with app.app_context():
        total, n = retenciones_sugeridas(None, date(2031, 3, 1), date(2031, 3, 31))
    assert float(total) == 35 and n == 1
    # Validaciones y permisos
    assert admin.post('/finanzas/api/seguimiento_cobro', json={'id': cid, 'retencion_monto': '2000'}).status_code == 400
    assert admin.post('/finanzas/api/seguimiento_cobro', json={'id': cid, 'fecha_programada': '2031-01-01'}).status_code == 400
    assert admin.post('/finanzas/api/seguimiento_cobro', json={'id': cid, 'fecha_programada': 'mañana'}).status_code == 400
    assert admin.post('/finanzas/api/seguimiento_cobro', json={'id': 999999}).status_code == 404
    assert vendedor.post('/finanzas/api/seguimiento_cobro', json={'id': cid}).status_code == 403
    # Vacío = vuelve la retención de la factura
    admin.post('/finanzas/api/seguimiento_cobro', json={'id': cid, 'portal_ingresado': False})
    f = fila()
    assert f['portal_ingresado'] is False and f['portal_fecha'] is None and f['retencion'] == 35.4


def test_ver_cobro_desde_entregas():
    js = (RAIZ / 'static/js/ventas.js').read_text(encoding='utf-8')
    assert 'function verCobroDespacho' in js and ">Ver cobro</button>" in js and "'/finanzas?tab=cxc&factura='" in js
    fjs = (RAIZ / 'static/js/finanzas.js').read_text(encoding='utf-8')
    for t in ("get('factura')", 'fin-fila-resaltada', 'function celdaSeguimiento', 'function abrirSeguimiento',
              "'/finanzas/api/seguimiento_cobro'", '✖ Falta portal', 'Retención 3%: falta N°'):
        assert t in fjs, t
    html = (RAIZ / 'templates/finanzas.html').read_text(encoding='utf-8')
    assert 'Portal y pago<small>retención 3%</small>' in html
