"""
Facturación parcial por posiciones (Erika 27/10/2026 17:07, caso Komatsu): pedido de 5 posiciones, se entregan 4
con guía y se facturan solo esas; la 5 queda con motivo y comentario (nota interna). Cuadre de 3 en las entregas.
Datos inventados, solo en la base local.
"""
import json
from pathlib import Path

from tests.test_inventario import _sql

RAIZ = Path(__file__).resolve().parent.parent
PV = 'PV-ZZPAR-1'


def _escenario():
    items = []
    for i in range(1, 6):
        cod = f'ZZPAR-{i}'
        _sql("""INSERT INTO productos (familia, codigo, descripcion, marca, unidad, costo_unitario, precio_unitario, stock, activo)
                SELECT 'GENERAL', %s, %s, 'ZZ', 'UND', 0, 100, 0, true WHERE NOT EXISTS (SELECT 1 FROM productos WHERE codigo = %s)""",
             (cod, 'REPUESTO ' + cod, cod), fetch=False)
        items.append({'codigo': cod, 'producto': f'Repuesto {i}', 'cantidad_pc': 2, 'precio_pc': 100})
    _sql("DELETE FROM comprobantes WHERE pc_vinculado = %s", (PV,), fetch=False)
    _sql("DELETE FROM guias_remision WHERE documento_asociado = %s", (PV,), fetch=False)
    _sql("DELETE FROM pedido_compra_pc WHERE numero = %s", (PV,), fetch=False)
    _sql("""INSERT INTO pedido_compra_pc (numero, cliente, ruc, estado, items_json, fecha, condicion_pago, oc_cliente)
            VALUES (%s, 'KOMATSU ZZ', '20100070970', 'Pendiente', %s, NOW(), 'Crédito 90 días', '4500012345')""",
         (PV, json.dumps(items)), fetch=False)
    # Se entregaron las posiciones 1 a 4 con guía; la 5 está en importación
    guia = [{'codigo': f'ZZPAR-{i}', 'producto': f'Repuesto {i}', 'cantidad': 2} for i in range(1, 5)]
    _sql("""INSERT INTO guias_remision (serie, numero, ruc_destinatario, destinatario_nombre, documento_asociado, items_json)
            VALUES ('T001', '00099501', '20100070970', 'KOMATSU ZZ', %s, %s)""", (PV, json.dumps(guia)), fetch=False)


def _factura(http, items, **extra):
    data = {'tipo': 'FACTURA', 'serie': 'F001', 'cliente': 'KOMATSU ZZ', 'ruc': '20100070970', 'pc': PV,
            'estado': 'Borrador', 'items': items}
    sub = sum(i['cantidad'] * i['valorVenta'] for i in items)
    data.update({'subtotal': sub, 'igv': round(sub * 0.18, 2), 'total': round(sub * 1.18, 2)})
    data.update(extra)
    return http.post('/ventas/api/comprobantes/guardar', json=data)


def _it(i, cant=2):
    return {'codigo': f'ZZPAR-{i}', 'producto': f'Repuesto {i}', 'cantidad': cant, 'valorVenta': 100}


def test_factura_parcial_solo_lo_entregado_con_motivo(admin):
    _escenario()
    cuatro = [_it(i) for i in range(1, 5)]
    # Sin motivo de la posición 5: no se guarda
    r = _factura(admin, cuatro, facturacion_tipo='Parcial')
    assert r.status_code == 400 and 'Posición 5' in r.json['error']
    # Con motivo pero sin comentario: tampoco
    r = _factura(admin, cuatro, facturacion_tipo='Parcial', pendientes=[{'posicion': 5, 'motivo': 'En importación'}])
    assert r.status_code == 400 and 'comentario' in r.json['error']
    # La posición 5 no tiene guía: no se puede facturar en una parcial
    r = _factura(admin, [_it(5)], facturacion_tipo='Parcial')
    assert r.status_code == 400 and 'guía' in r.json['error']
    # "Total" que no cubre todo el pedido no pasa sin motivo... la primera vez sí se permite (factura anticipada)
    pend = [{'posicion': 5, 'motivo': 'En importación', 'comentario': 'llega de importación en 30 días'}]
    r = _factura(admin, cuatro, facturacion_tipo='Parcial', pendientes=pend)
    assert r.status_code == 200, r.json
    fid = r.json['data']['id']
    f = admin.get(f'/ventas/api/comprobantes/{fid}').json['data']
    assert f['facturacion_tipo'] == 'Parcial'
    pj = f['pendientes_json'] if isinstance(f['pendientes_json'], list) else json.loads(f['pendientes_json'])
    assert pj[0]['posicion'] == 5 and pj[0]['motivo'] == 'En importación' and pj[0]['comentario'].startswith('Llega')
    # Avance del PV: 80% facturado, falta la posición 5
    a = admin.get('/ventas/api/pv/avance', query_string={'numero': PV}).json['data']
    assert a['facturado_pct'] == 80 and a['faltan_facturar'] == [5] and a['guiado_pct'] == 80
    assert a['posiciones'][4]['motivo']['motivo'] == 'En importación'
    lista = admin.get('/ventas/api/pv/avance-lista', query_string={'numeros': PV}).json['data'][PV]
    assert lista['facturado_pct'] == 80 and lista['faltan_facturar'] == [5]
    # Nadie factura dos veces lo ya facturado
    r = _factura(admin, [_it(1)], facturacion_tipo='Parcial', pendientes=pend)
    assert r.status_code == 400
    # "Total" con solo una parte, después de una parcial: pide elegir parcial
    r = _factura(admin, [_it(5, 1)], facturacion_tipo='Total')
    assert r.status_code == 400 and 'Factura parcial' in r.json['error']
    # Alerta en el inicio de Erika
    al = admin.get('/ventas/api/control/alertas').json
    assert any(x['pv'] == PV and x['faltan'] == [5] for x in al['por_facturar'])
    # La nota interna no sale en el PDF
    assert 'importación en 30 días' not in (RAIZ / 'pdf_generator.py').read_text(encoding='utf-8')


def test_cuadre_almacen_guia_cliente(admin):
    from routes.facturacion_parcial import cuadre_despacho, asegurar_columnas
    with admin.application.app_context():
        asegurar_columnas()
        prod = _sql("SELECT id FROM productos WHERE codigo = 'ZZPAR-1'")[0][0]
        g = {('T001', 99501): {'items_json': [{'codigo': 'ZZPAR-1', 'cantidad': 2}]}}
        bien = {'estado': 'Despachado', 'guia': 'T001-00099501', 'stock_detalle': [{'producto_id': prod, 'cantidad': 2}]}
        assert cuadre_despacho(bien, g) == []
        mal = dict(bien, stock_detalle=[{'producto_id': prod, 'cantidad': 3}])
        assert 'Almacén sacó 3' in cuadre_despacho(mal, g)[0]
        assert cuadre_despacho(dict(bien, guia=''), g) == ['Salió del almacén sin guía de remisión']
        assert 'sin fecha real' in cuadre_despacho(dict(bien, estado='Entregado'), g)[0]


def test_confirmar_entrega_guarda_ingreso_del_cliente(admin):
    _sql("DELETE FROM despachos WHERE numero = 'DES-ZZPAR-1'", fetch=False)
    did = _sql("""INSERT INTO despachos (numero, cliente, ruc, estado, pc_numero, guia, fecha_salida)
                  VALUES ('DES-ZZPAR-1', 'KOMATSU ZZ', '20100070970', 'Despachado', %s, 'T001-00099501', NOW() - INTERVAL '1 day')
                  RETURNING id""", (PV,))[0][0]
    r = admin.post(f'/ventas/api/despachos/{did}/entrega', json={'accion': 'entregar',
                                                               'fecha_entrega': __import__('datetime').date.today().isoformat(),
                                                               'ingreso_cliente': ' 5000123456 '})
    assert r.status_code == 200, r.json
    assert _sql("SELECT ingreso_cliente, estado FROM despachos WHERE id = %s", (did,))[0] == ('5000123456', 'Entregado')
    fila = next(d for d in admin.get('/ventas/api/despachos/listar').json['data'] if d['id'] == did)
    assert fila['ingreso_cliente'] == '5000123456'


def test_pantallas_factura_parcial():
    js = (RAIZ / 'static/js/factura_parcial.js').read_text(encoding='utf-8')
    assert 'Factura parcial (solo lo entregado con guía)' in js and 'IGV (18%)' in js and 'Subtotal' in js
    assert 'En importación' in js and 'nota interna' in js
    html = (RAIZ / 'templates/ventas/index.html').read_text(encoding='utf-8')
    assert 'js/factura_parcial.js' in html
    ventas = (RAIZ / 'static/js/ventas.js').read_text(encoding='utf-8')
    assert 'FacturaParcial.listaParaGuardar' in ventas and 'entregaIngreso' in ventas
    assert 'ctrlPanel' in (RAIZ / 'templates/index.html').read_text(encoding='utf-8')
