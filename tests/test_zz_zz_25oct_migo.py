"""25/10/2026 (Erika): N° MIGO / conformidad. Check en el cliente, campo en la factura y aviso en Cuentas por cobrar."""
from tests.test_inventario import _sql

RUC = '20777000331'


def test_migo_cliente_factura_y_cobranza(admin, vendedor):
    base = {'razon_social': 'CLIENTE MIGO ZZ', 'numero_documento': RUC, 'tipo_documento': 'RUC',
            'direccion_fiscal': 'Av. Migo 1', 'limite_credito': '0', 'descuento': '0', 'condicion_pago': 'Contado'}
    r = admin.post('/maestros/api/clientes/guardar', json={**base, 'pide_migo': True})
    assert r.json['success'], r.json
    cli = _sql("SELECT id, pide_migo FROM clientes WHERE numero_documento = %s", (RUC,))[0]
    assert cli[1] is True
    assert admin.get(f'/maestros/api/clientes/{cli[0]}').json['data']['pide_migo'] is True
    # Guardar la ficha sin el campo (p. ej. desde la cotización) no lo apaga
    assert admin.put(f'/maestros/api/clientes/{cli[0]}', json={'razon_social': 'CLIENTE MIGO ZZ'}).json['success']
    assert _sql("SELECT pide_migo FROM clientes WHERE id = %s", (cli[0],))[0][0] is True
    # La factura sabe que el cliente lo pide
    assert admin.get(f'/ventas/api/comprobantes/condicion-origen?ruc={RUC}').json['data']['pide_migo'] is True
    assert admin.get('/ventas/api/comprobantes/condicion-origen?ruc=20100070970').json['data']['pide_migo'] is False
    # Factura emitida sin MIGO -> "Falta MIGO" en CxC
    cid = _sql("""INSERT INTO comprobantes (tipo_comprobante, serie, numero, fecha_emision, cliente_tipo_doc, cliente_nombre,
                                            cliente_numero_doc, subtotal, igv, total, monto_a_pagar, estado_sunat, items_json)
                  VALUES ('Factura', 'E0MG', '5', '2031-05-02', '6', 'CLIENTE MIGO ZZ', %s, 100, 18, 118, 118, 'Emitida', '[]')
                  RETURNING id""", (RUC,))[0][0]

    def fila():
        return next(x for x in admin.get('/finanzas/api/cxc?estado=todos&q=e0mg').json['data'] if x['id'] == cid)

    f = fila()
    assert f['pide_migo'] is True and f['numero_migo'] is None
    # Se anota después en Finanzas
    r = admin.post('/finanzas/api/seguimiento_cobro', json={'id': cid, 'numero_migo': ' 5000123456 '})
    assert r.status_code == 200, r.json
    assert fila()['numero_migo'] == '5000123456'
    assert vendedor.post('/finanzas/api/seguimiento_cobro', json={'id': cid, 'numero_migo': 'X'}).status_code == 403
    # Sin la clave numero_migo, el seguimiento no lo borra
    admin.post('/finanzas/api/seguimiento_cobro', json={'id': cid, 'portal_ingresado': True, 'portal_fecha': '2031-05-03'})
    assert fila()['numero_migo'] == '5000123456'
    # Y se lee al abrir la factura
    assert admin.get(f'/ventas/api/comprobantes/{cid}').json['data']['numero_migo'] == '5000123456'
    admin.put(f'/maestros/api/clientes/{cli[0]}', json={'razon_social': 'CLIENTE MIGO ZZ', 'pide_migo': False})
    assert _sql("SELECT pide_migo FROM clientes WHERE id = %s", (cli[0],))[0][0] is False


def test_pantallas_ya_no_muestran_migo():
    # Erika 26/10/2026 21:27: "eliminar el MIGO en las facturas y los demás módulos". Solo se quita de la vista;
    # los datos siguen en la base y las pantallas no los borran al guardar.
    import os
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    leer = lambda r: open(os.path.join(raiz, r), encoding='utf-8').read()
    assert 'cli_pideMigo' not in leer('templates/modales/cliente_modal.html')
    assert "...(document.getElementById('cli_pideMigo') ?" in leer('static/js/maestros.js')
    v = leer('static/js/ventas.js')
    assert 'id="compMigoCaja"' not in v and 'class="migo-lista"' not in v
    fz = leer('static/js/finanzas.js')
    assert 'Falta MIGO' not in fz and 'id="segMigo"' not in fz
    assert 'N° MIGO:' not in leer('pdf_generator.py')
