"""Notas de crédito (REGLA DE ORO de Erika, 26/10/2026): solo Hellen crea, solo Erika aprueba; monto calculado,
trazabilidad automática y nota interna que nunca sale en el documento."""
import json

import pytest

from tests.test_inventario import _sql

ITEMS = [{'codigo': 'PRD-0001', 'producto': 'GUANTE DE NITRILO', 'um': 'NIU', 'cantidad': 10, 'valorVenta': 100}]


@pytest.fixture()
def reglas(monkeypatch):
    import utils
    from routes import nota_credito
    monkeypatch.setattr(nota_credito, 'USUARIOS_NOTA_CREDITO', {'hellen'})
    monkeypatch.setattr(utils, 'USUARIOS_REPORTES', {'admin'})


def _factura(http, numero):
    r = http.post('/ventas/api/comprobantes/guardar', json={
        'tipo': 'FACTURA', 'serie': 'E001', 'numero': numero, 'cliente': 'CLIENTE INDUSTRIAL S.A.C.', 'ruc': '20100070970',
        'total': 1180, 'subtotal': 1000, 'igv': 180, 'estado': 'Borrador', 'items': ITEMS,
        'orden_compra_cliente': 'PC-CLI-55', 'guia': f'T001-0000{numero}', 'cotizacion': 'COT-000077'})
    assert r.status_code == 200, r.json
    cid = r.json['data']['id']
    _sql("UPDATE comprobantes SET estado_sunat = 'Emitido' WHERE id = %s", (cid,), fetch=False)
    return cid


def _nota(cid, **extra):
    d = {'comprobante_id': cid, 'tipo_nota': '07', 'items': [{'idx': 0, 'cantidad': 2}],
         'sustento': 'El cliente devolvió 2 guantes rotos', 'guia_devolucion': 'T001-00000090',
         'causa_interna': 'Error operativo', 'responsable_error': 'María',
         'nota_interna': 'María despachó guantes rotos sin revisar', 'observaciones': 'devolución parcial',
         'monto': 99999, 'enviar': True}
    d.update(extra)
    return d


def test_solo_hellen_crea_y_monto_calculado(reglas, vendedor, admin, aprobador):
    cid = _factura(vendedor, '7701')
    assert vendedor.post('/ventas/api/nc/guardar', json=_nota(cid)).status_code == 403
    assert admin.post('/ventas/api/nc/guardar', json=_nota(cid)).status_code == 403
    r = aprobador.post('/ventas/api/nc/guardar', json=_nota(cid))
    assert r.status_code == 200, r.json
    nid = r.json['data']['id']
    f = _sql("""SELECT monto, subtotal, igv, estado, serie, guia_numero, pc_cliente, cotizacion_numero, observaciones,
                       creado_por_usuario FROM notas_credito WHERE id = %s""", (nid,))[0]
    # 2 x 100 x 1.18 = 236 (el 99999 que mandó el navegador no se usa)
    assert float(f[0]) == 236 and float(f[1]) == 200 and float(f[2]) == 36
    assert f[3] == 'Por aprobar' and f[4] == 'E001'
    assert f[5] == 'T001-00007701' and f[6] == 'PC-CLI-55' and f[7] == 'COT-000077'
    assert f[8] == 'Devolución parcial' and f[9] == 'hellen'


def test_solo_erika_aprueba_y_rechaza(reglas, vendedor, admin, aprobador):
    cid = _factura(vendedor, '7702')
    nid = aprobador.post('/ventas/api/nc/guardar', json=_nota(cid)).json['data']['id']
    assert aprobador.post(f'/ventas/api/nc/{nid}/decidir', json={'decision': 'aprobar'}).status_code == 403
    assert vendedor.post(f'/ventas/api/nc/{nid}/decidir', json={'decision': 'aprobar'}).status_code == 403
    assert admin.post(f'/ventas/api/nc/{nid}/decidir', json={'decision': 'rechazar', 'motivo': ''}).status_code == 400
    r = admin.post(f'/ventas/api/nc/{nid}/decidir', json={'decision': 'rechazar', 'motivo': 'Falta el correo del cliente'})
    assert r.status_code == 200 and r.json['data']['estado'] == 'Rechazada'
    # Hellen la corrige y la vuelve a enviar; Erika la aprueba
    assert aprobador.post('/ventas/api/nc/guardar', json=_nota(cid, id=nid)).status_code == 200
    r = admin.post(f'/ventas/api/nc/{nid}/decidir', json={'decision': 'aprobar'})
    assert r.status_code == 200 and r.json['data']['estado'] == 'Emitida'
    assert _sql("SELECT aprobado_por FROM notas_credito WHERE id = %s", (nid,))[0][0] == 'admin'
    # Ya emitida no se puede cambiar
    assert aprobador.post('/ventas/api/nc/guardar', json=_nota(cid, id=nid)).status_code == 409
    assert _sql("SELECT COUNT(*) FROM erp_auditoria WHERE registro_id::text = %s AND accion LIKE 'NC_%%'", (str(nid),))[0][0] >= 3


def test_no_supera_saldo_y_valida_sustento(reglas, vendedor, aprobador):
    cid = _factura(vendedor, '7703')
    assert aprobador.post('/ventas/api/nc/guardar', json=_nota(cid, items=[{'idx': 0, 'cantidad': 11}])).status_code == 400
    assert aprobador.post('/ventas/api/nc/guardar', json=_nota(cid, sustento='x')).status_code == 400
    assert aprobador.post('/ventas/api/nc/guardar', json=_nota(cid, responsable_error='')).status_code == 400
    assert aprobador.post('/ventas/api/nc/guardar', json=_nota(cid, guia_devolucion='')).status_code == 400
    # Anulación = todo el saldo; una segunda anulación ya no cabe
    r = aprobador.post('/ventas/api/nc/guardar', json=_nota(cid, tipo_nota='01', items=[], guia_devolucion=''))
    assert r.status_code == 200 and r.json['data']['monto'] == 1180
    assert aprobador.post('/ventas/api/nc/guardar', json=_nota(cid, tipo_nota='01', items=[])).status_code == 400


def test_nota_interna_no_sale_en_el_documento(reglas, vendedor, admin, aprobador):
    cid = _factura(vendedor, '7704')
    nid = aprobador.post('/ventas/api/nc/guardar', json=_nota(cid)).json['data']['id']
    html = admin.get(f'/ventas/nc/{nid}/imprimir').get_data(as_text=True)
    assert 'El cliente devolvió 2 guantes rotos' in html and 'Devolución parcial' in html
    assert 'María despachó' not in html and 'Error operativo' not in html
    assert 'nota_interna' not in vendedor.get(f'/ventas/api/nc/{nid}').json['data']
    assert admin.get(f'/ventas/api/nc/{nid}').json['data']['nota_interna'].startswith('María')
    rep = admin.get('/ventas/api/nc/reporte').json['data']
    assert any(x['responsable'] == 'María' for x in rep['por_responsable'])
    assert vendedor.get('/ventas/api/nc/reporte').status_code == 403


def test_pantalla_nota_credito():
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / 'static/js/nota_credito.js').read_text(encoding='utf-8')
    for t in ('Enviar a Erika para aprobar', 'Nota interna', 'Responsable del error', 'calculado, nadie lo escribe',
              'N° PC (Pedido del cliente)', 'N° PV (Pedido de venta)'):
        assert t in js, t
