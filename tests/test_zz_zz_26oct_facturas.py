"""
Ventas ▸ Facturas (Erika 26/10/2026): monto a pagar en la lista, condición de pago FIJA (la del PV; solo Erika la
cambia y queda en auditoría), cotización que se llena sola, N° MIGO a la vista y XML de SUNAT para descargar.
Datos inventados, solo en la base local.
"""
import io
from pathlib import Path

from tests.test_inventario import _sql
from tests.test_zz_zz_19oct_noche import _pc

RAIZ = Path(__file__).resolve().parent.parent


def _factura(cliente, **extra):
    datos = {'tipo': 'FACTURA', 'serie': 'F001', 'cliente': 'CLIENTE INDUSTRIAL S.A.C.', 'ruc': '20100070970',
             'total': 1180, 'subtotal': 1000, 'igv': 180, 'estado': 'Borrador', 'items': []}
    datos.update(extra)
    return cliente.post('/ventas/api/comprobantes/guardar', json=datos)


def test_condicion_fija_del_pc(vendedor):
    assert _pc(vendedor, numero='PC-ZZF-1', cotizacion_numero='COT-ZZF-1', condicion_pago='Crédito 15 días').status_code == 200
    # Alguien intenta poner 6 meses: el servidor deja la del PV
    r = _factura(vendedor, pc='PC-ZZF-1', condicion='Crédito 180 días')
    assert r.status_code == 200, r.json
    fila = _sql("SELECT condicion_pago, dias_credito FROM comprobantes WHERE id = %s", (r.json['data']['id'],))[0]
    assert fila == ('Crédito 15 días', 15)


def test_erika_si_puede_cambiarla_y_queda_en_auditoria(admin, monkeypatch):
    import utils
    monkeypatch.setattr(utils, 'USUARIOS_REPORTES', ['admin'])
    assert _pc(admin, numero='PC-ZZF-2', cotizacion_numero='COT-ZZF-2', condicion_pago='Crédito 15 días').status_code == 200
    r = _factura(admin, pc='PC-ZZF-2', condicion='Crédito 30 días')
    assert r.status_code == 200, r.json
    cid = r.json['data']['id']
    assert _sql("SELECT condicion_pago FROM comprobantes WHERE id = %s", (cid,))[0][0] == 'Crédito 30 días'
    aud = _sql("SELECT detalle FROM erp_auditoria WHERE tabla = 'comprobantes' AND registro_id::text = %s "
               "AND detalle LIKE '%%cambiada por Erika%%'", (str(cid),))
    assert aud and 'Crédito 15 días' in aud[0][0] and 'Crédito 30 días' in aud[0][0]


def test_lista_trae_monto_a_pagar_y_cotizacion_del_pc(vendedor):
    assert _pc(vendedor, numero='PC-ZZF-3', cotizacion_numero='COT-ZZF-3', condicion_pago='Contado').status_code == 200
    if not _sql("SELECT 1 FROM pedido_compra_pc WHERE numero = 'PC-ZZF-3' AND cotizacion_numero = 'COT-ZZF-3'"):
        _sql("UPDATE pedido_compra_pc SET cotizacion_numero = 'COT-ZZF-3' WHERE numero = 'PC-ZZF-3'", fetch=False)
    r = _factura(vendedor, pc='PC-ZZF-3', condicion='Contado', tiene_retencion=True, monto_retenido=35.40, monto_a_pagar=1144.60)
    assert r.status_code == 200, r.json
    cid = r.json['data']['id']
    _sql("UPDATE comprobantes SET documento_asociado = NULL WHERE id = %s", (cid,), fetch=False)
    f = next(x for x in vendedor.get('/ventas/api/comprobantes/listar').json['data'] if x['id'] == cid)
    assert f['cotizacion'] == 'COT-ZZF-3'
    assert 'monto_a_pagar' in f and 'numero_migo' in f and 'xml_id' in f


def test_xml_de_sunat_se_sube_y_se_descarga(vendedor):
    r = _factura(vendedor, condicion='Contado', numero='77')
    assert r.status_code == 200, r.json
    cid = r.json['data']['id']
    serie, numero = r.json['data']['serie'], int(str(r.json['data']['numero']))
    url = f'/ventas/api/comprobantes/{cid}/archivos'
    malo = f'<?xml version="1.0"?><Invoice><cbc:ID>{serie}-{numero + 1:08d}</cbc:ID></Invoice>'.encode()
    r = vendedor.post(url, data={'archivo': (io.BytesIO(malo), 'otra.xml')}, content_type='multipart/form-data')
    assert r.status_code == 400 and 'no de' in r.json['error']
    r = vendedor.post(url, data={'archivo': (io.BytesIO(b'hola'), 'a.exe')}, content_type='multipart/form-data')
    assert r.status_code == 400
    bueno = f'<?xml version="1.0"?><Invoice><cbc:ID>{serie}-{numero}</cbc:ID></Invoice>'.encode()
    r = vendedor.post(url, data={'archivo': (io.BytesIO(bueno), '20602095704-01-F.xml')}, content_type='multipart/form-data')
    assert r.status_code == 200 and r.json['data']['tipo'] == 'XML'
    f = next(x for x in vendedor.get('/ventas/api/comprobantes/listar').json['data'] if x['id'] == cid)
    assert f['xml_id'] == r.json['data']['id']
    d = vendedor.get(f"/ventas/api/comprobantes/archivos/{f['xml_id']}/descargar")
    assert d.status_code == 200 and d.data == bueno and 'attachment' in d.headers['Content-Disposition']
    assert vendedor.get(url).json['data'][0]['tipo'] == 'XML'


def test_pantalla_de_facturas_26oct():
    html = (RAIZ / 'templates/ventas/index.html').read_text(encoding='utf-8')
    assert '>Monto a pagar</th>' in html
    base = (RAIZ / 'templates/base.html').read_text(encoding='utf-8')
    assert 'window.ES_ERIKA' in base
    js = (RAIZ / 'static/js/ventas.js').read_text(encoding='utf-8')
    for t in ('id="compAPagarVista"', 'function montoAPagarDe', 'function ponerVinculoFactura',
              "ponerVinculoFactura('compCotizacion', pc.cotizacion_numero)", 'sel.disabled = !window.ES_ERIKA',
              'Solo Erika la puede cambiar', 'Descargar XML (SUNAT)', 'Adjuntar XML descargado de SUNAT', 'colspan="14"'):
        assert t in js, t
    pdf = (RAIZ / 'pdf_generator.py').read_text(encoding='utf-8')
    assert 'N° MIGO:' not in pdf   # quitado de todos los módulos (Erika 26/10/2026 21:27)


def test_retencion_calculada_y_con_candado(vendedor):
    # Erika 26/10/2026: el bloque de retención es solo retención; nadie escribe % ni monto ni vencimiento a mano
    _sql("DELETE FROM pedido_compra_pc WHERE numero = 'PC-ZZR-1'", fetch=False)
    assert _pc(vendedor, numero='PC-ZZR-1', cotizacion_numero='COT-ZZR-1', condicion_pago='Crédito 7 días').status_code == 200
    _sql("UPDATE pedido_compra_pc SET condicion_pago = 'Crédito 7 días' WHERE numero = 'PC-ZZR-1'", fetch=False)
    r = _factura(vendedor, pc='PC-ZZR-1', tiene_retencion=True, porcentaje_retencion=10, monto_retenido=500,
                 monto_a_pagar=1, dias_credito=120, fecha_vencimiento='2027-12-31', estado_credito='Aceptada en Crédito',
                 obs_retencion='texto inventado')
    assert r.status_code == 200, r.json
    f = _sql("SELECT porcentaje_retencion, monto_retenido, monto_a_pagar, dias_credito, fecha_vencimiento::date - fecha_emision::date, "
             "estado_credito, obs_retencion FROM comprobantes WHERE id = %s", (r.json['data']['id'],))[0]
    assert float(f[0]) == 3 and float(f[1]) == 35.4 and float(f[2]) == 1144.6
    assert f[3] == 7 and f[4] == 7 and f[5] is None, (f, _sql("SELECT condicion_pago, pc_vinculado FROM comprobantes WHERE id = %s", (r.json["data"]["id"],)))
    assert 'retenido S/ 35.40' in f[6]
