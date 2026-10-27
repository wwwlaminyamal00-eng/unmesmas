"""
Descripción del cliente por línea (Erika y Hellen, 27/10/2026, caso Komatsu): cada producto lleva el Nombre producto
del maestro y, debajo, cómo lo pide el cliente (y su Código del cliente). Nace en la cotización, se recuerda por
cliente y producto, pasa al PV y de ahí a lo que aún no se emitió; los PDF muestran los dos nombres.
Datos inventados, solo en la base local.
"""
import json
from pathlib import Path

from tests.test_inventario import _sql

RAIZ = Path(__file__).resolve().parent.parent
BASE_COT = {'cliente_id': 1, 'condicion_pago': 'Crédito 30 días', 'tiempo_entrega': '2 días hábiles',
            'transporte': 'Auto', 'parihuela': 'No', 'estado': 'Borrador'}
PV = 'PV-ZZDESC-1'


def test_cotizacion_guarda_y_recuerda_la_descripcion_del_cliente(vendedor):
    prods = [{'codigo': 'PRD-0001', 'cantidad': 2, 'valorVenta': 50,
              'descripcion_cliente': '  Bloqueador solar sunwer 120 ml ', 'codigo_cliente': '40012345'}]
    r = vendedor.post('/ventas/api/cotizaciones/guardar', json={**BASE_COT, 'productos': prods})
    assert r.status_code == 200, r.json
    cid = r.json['data']['id']
    assert _sql("SELECT descripcion_cliente, codigo_cliente FROM cotizacion_detalle WHERE cotizacion_id = %s",
                (cid,))[0] == ('Bloqueador solar sunwer 120 ml', '40012345')
    p = vendedor.get(f'/ventas/api/cotizaciones/{cid}/completa').json['data']['productos'][0]
    assert p['descripcion_cliente'] == 'Bloqueador solar sunwer 120 ml' and p['codigo_cliente'] == '40012345'
    # La próxima cotización de este cliente lo sugiere
    s = vendedor.get('/ventas/api/descripcion-cliente/sugerencias?cliente_id=1&codigos=PRD-0001,NO-EXISTE').json['data']
    assert s == {'PRD-0001': {'descripcion_cliente': 'Bloqueador solar sunwer 120 ml', 'codigo_cliente': '40012345'}}
    # Sin descripción no se borra lo recordado
    vendedor.post('/ventas/api/cotizaciones/guardar', json={**BASE_COT, 'productos': [
        {'codigo': 'PRD-0001', 'cantidad': 1, 'valorVenta': 50}]})
    s = vendedor.get('/ventas/api/descripcion-cliente/sugerencias?cliente_id=1&codigos=PRD-0001').json['data']
    assert s['PRD-0001']['codigo_cliente'] == '40012345'


def test_pv_corregido_pasa_solo_a_lo_no_emitido():
    from routes import descripcion_cliente as dc
    item = {'codigo': 'ZZD-1', 'producto': 'Arandela plana 5/8', 'cantidad': 2}
    _sql("DELETE FROM despachos WHERE pc_numero = %s", (PV,), fetch=False)
    _sql("DELETE FROM guias_remision WHERE documento_asociado = %s", (PV,), fetch=False)
    sin_guia = _sql("""INSERT INTO despachos (numero, cliente, ruc, estado, pc_numero, items_json)
                       VALUES ('DES-ZZD-1', 'KOMATSU ZZ', '20100070970', 'Pendiente despacho', %s, %s) RETURNING id""",
                    (PV, json.dumps([item])))[0][0]
    con_guia = _sql("""INSERT INTO despachos (numero, cliente, ruc, estado, pc_numero, guia, items_json)
                       VALUES ('DES-ZZD-2', 'KOMATSU ZZ', '20100070970', 'Despachado', %s, 'T001-00099601', %s) RETURNING id""",
                    (PV, json.dumps([item])))[0][0]
    borrador = _sql("""INSERT INTO guias_remision (serie, numero, ruc_destinatario, destinatario_nombre, documento_asociado,
                       items_json, estado_sunat) VALUES ('T001', '00099602', '20100070970', 'KOMATSU ZZ', %s, %s, 'Borrador')
                       RETURNING id""", (PV, json.dumps([item])))[0][0]
    emitida = _sql("""INSERT INTO guias_remision (serie, numero, ruc_destinatario, destinatario_nombre, documento_asociado,
                      items_json, estado_sunat) VALUES ('T001', '00099603', '20100070970', 'KOMATSU ZZ', %s, %s, 'Emitida')
                      RETURNING id""", (PV, json.dumps([item])))[0][0]
    nuevo = [{**item, 'descripcion_cliente': 'Guacha 5/8', 'codigo_cliente': 'MAT-77'}]
    assert dc.propagar_pv(PV, nuevo) == 2

    def desc(tabla, i):
        crudo = _sql(f"SELECT items_json FROM {tabla} WHERE id = %s", (i,))[0][0]
        crudo = json.loads(crudo) if isinstance(crudo, str) else crudo
        return crudo[0].get('descripcion_cliente'), crudo[0].get('codigo_cliente')
    assert desc('despachos', sin_guia) == ('Guacha 5/8', 'MAT-77')
    assert desc('guias_remision', borrador) == ('Guacha 5/8', 'MAT-77')
    assert desc('despachos', con_guia) == (None, None)       # ya salió con guía: no se toca
    assert desc('guias_remision', emitida) == (None, None)   # emitida: no se toca


def test_pdf_lleva_los_dos_nombres():
    from pdf_generator import linea_cliente, _span_cliente
    it = {'producto': 'ARANDELA PLANA 5/8', 'descripcion_cliente': 'Guacha 5/8', 'codigo_cliente': 'MAT-77'}
    assert linea_cliente(it) == 'Según su pedido: Guacha 5/8 · Código del cliente: MAT-77'
    assert linea_cliente({'producto': 'X'}) == ''
    assert '&lt;b&gt;' in _span_cliente({'descripcion_cliente': '<b>'})
    py = (RAIZ / 'pdf_generator.py').read_text(encoding='utf-8')
    assert "(item.get('descripcion_cliente') or '').strip() or" not in py   # ya no reemplaza el nombre del maestro
    js = (RAIZ / 'static/js/ventas.js').read_text(encoding='utf-8-sig')
    assert 'class="cot-desc-cliente"' in js and 'class="cot-cod-cliente"' in js and 'function lineaClienteHTML' in js
    assert "codigo_cliente: (row.querySelector('.pc-cod-cliente')?.value || '').trim()" in js
