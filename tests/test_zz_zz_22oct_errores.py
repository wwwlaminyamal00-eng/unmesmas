"""
Pedido urgente de Erika del 22/10/2026 11:05: guardados que fallaban "en silencio" (clientes, cotizaciones),
el buscador de productos de la OC y, a las 11:26, la OC intercompany que no dejaba recibir y las pestañas sin sombrear.
Datos inventados, solo en la base local.
"""
import pytest

from tests.conftest import _login
from tests.test_inventario import _sql
from tests.test_zz_compras import _oc_flujo


@pytest.fixture(scope='module')
def zz(app):
    # Usa los datos que dejó tests/test_zz_compras.py (corre antes por orden alfabético)
    filas = _sql("""SELECT (SELECT id FROM proveedores WHERE ruc = '20777777777' LIMIT 1),
                             (SELECT id FROM productos WHERE codigo = 'ZZC-002' LIMIT 1),
                             (SELECT id FROM erp_empresas WHERE codigo = 'KCF'),
                             (SELECT id FROM almacenes WHERE codigo = 'SMP' LIMIT 1)""")[0]
    if not all(filas):
        pytest.skip('Faltan los datos de tests/test_zz_compras.py')
    return {'prov': filas[0], 'LENTE': filas[1], 'emp': filas[2], 'sede': filas[3],
            'compra': _login(app, 'compra7', 'Clave#2026!')}


def test_cliente_sin_datos_dice_que_campo_falta(admin):
    r = admin.post('/maestros/api/clientes/guardar', json={'numero_documento': '20555555551'})
    assert r.status_code == 400 and r.json['campo'] == 'razon_social' and 'razón social' in r.json['error']
    r = admin.post('/maestros/api/clientes/guardar', json={'razon_social': 'SIN RUC S.A.C.'})
    assert r.status_code == 400 and r.json['campo'] == 'numero_documento'


def test_cliente_error_de_base_explicado_y_registrado(admin):
    # Contador de ids atrasado (pasa al cargar clientes desde Excel con su número): se explica y se corrige solo
    _sql("""INSERT INTO clientes (id, tipo_documento, numero_documento, razon_social, direccion_fiscal)
            VALUES ((SELECT last_value FROM clientes_id_seq) + 1, 'RUC', '20555555552', 'CARGADO A MANO S.A.C.', 'Lima')""", fetch=False)
    r = admin.post('/maestros/api/clientes/guardar', json={'numero_documento': '20555555553', 'razon_social': 'NUEVO ZZ S.A.C.',
                                                          'direccion_fiscal': 'Lima', 'limite_credito': '0', 'descuento': '0'})
    assert r.status_code == 409 and r.json['success'] is False, r.json
    assert 'contador interno' in r.json['error'] and 'vuelve a presionar Guardar' in r.json['error']
    assert r.json['detalle']                      # el texto exacto de la base, para copiarlo
    r = admin.post('/maestros/api/clientes/guardar', json={'numero_documento': '20555555553', 'razon_social': 'NUEVO ZZ S.A.C.',
                                                          'direccion_fiscal': 'Lima', 'limite_credito': '0', 'descuento': '0'})
    assert r.status_code == 200 and r.json['success'], r.json
    # RUC repetido: mensaje claro y el campo a marcar
    r = admin.post('/maestros/api/clientes/guardar', json={'numero_documento': '20555555553', 'razon_social': 'OTRO S.A.C.',
                                                          'limite_credito': '0', 'descuento': '0'})
    if _sql("SELECT COUNT(*) FROM pg_constraint WHERE conname = 'clientes_numero_documento_key'")[0][0]:   # base real
        assert r.json['success'] is False and 'ya está registrado' in r.json['error'] and r.json.get('campo') == 'numero_documento'
    # Todo queda en Herramientas ▸ Registro de errores
    d = admin.get('/herramientas/api/logs?n=50').json
    assert d['fallos_guardados'] >= 1 and any('contador interno' in f['mensaje'] for f in d['data'])


def test_navegador_avisa_fallos_sin_respuesta(admin, anonimo):
    assert anonimo.post('/api/diagnostico/fallo', json={'mensaje': 'x'}).status_code in (302, 401)
    r = admin.post('/api/diagnostico/fallo', json={'mensaje': 'No hubo respuesta del servidor', 'detalle': 'TypeError: Failed to fetch',
                                                  'ruta': '/ventas/api/cotizaciones/guardar', 'metodo': 'POST', 'estado': 'abc'})
    assert r.status_code == 200
    assert _sql("SELECT COUNT(*) FROM erp_log_errores WHERE origen = 'navegador' AND ruta = '/ventas/api/cotizaciones/guardar'")[0][0] >= 1


def test_api_con_error_inesperado_responde_json(admin):
    r = admin.post('/api/ruta-que-no-existe-zz', json={})
    assert r.status_code == 404 and r.is_json and r.json['success'] is False


def test_cotizacion_sin_cliente_dice_por_que(admin):
    r = admin.post('/ventas/api/cotizaciones/guardar', json={'productos': []})
    assert r.status_code == 400 and r.is_json and r.json['error']


def test_pantallas_cargan_el_aviso_de_errores(admin):
    for url in ('/compras', '/maestros/', '/ventas'):
        assert 'errores_guardado.js' in admin.get(url).get_data(as_text=True), url
    js = open('static/js/errores_guardado.js', encoding='utf-8').read()
    assert 'mostrarErrorGuardado' in js and 'botonCargando' in js and 'Tu sesión expiró' in js
    flujo = open('static/js/compras_flujo.js', encoding='utf-8').read()
    assert 'No se pudo buscar' in flujo and "lista.style.position = 'fixed'" in flujo
    base = open('templates/base.html', encoding='utf-8').read()
    assert '#tabsRowCom .tab-btn.active' in base


def test_oc_intercompany_se_recibe_antes_del_pago(zz, admin):
    # El proveedor es otra empresa del grupo (mismo RUC que una empresa del ERP)
    ruc = _sql("SELECT ruc FROM erp_empresas WHERE codigo = 'KCF'")[0][0]
    prov = _sql("""INSERT INTO proveedores (razon_social, ruc, direccion, condicion_pago, activo)
                   VALUES ('EMPRESA DEL GRUPO ZZ S.A.C.', %s, 'Breña', 'Contado', true) RETURNING id""", (ruc,))[0][0]
    r = admin.post('/compras/api/flujo/ordenes', json=_oc_flujo(zz, proveedor_id=prov, motivo_compra='Stock estratégico',
                                                                  items=[{'producto_id': zz['LENTE'], 'cantidad': 23, 'precio_unitario': 7}]))
    assert r.status_code == 200, r.json
    oc_id = r.json['id']
    _sql("UPDATE ordenes_compra SET estado = 'Aprobada' WHERE id = %s", (oc_id,), fetch=False)
    fila = next(o for o in admin.get('/compras/api/flujo/por_recibir').json['data'] if o['id'] == oc_id)
    assert fila['paso']['codigo'] == 'recibir' and fila['falta_pago_intercompany'] is True
    items = admin.get(f'/compras/api/flujo/ordenes/{oc_id}/para_recibir').json['items']
    rec = {'almacen_id': zz['sede'], 'guia_proveedor': 'T001-ZZ-22', 'traido_por_tipo': 'courier', 'traido_por': 'Chofer AGD',
           'items': [{'oc_item_id': items[0]['id'], 'cantidad_buena': 23, 'cantidad_danada': 0}]}
    r = admin.post(f'/compras/api/flujo/ordenes/{oc_id}/recibir', json=rec)
    assert r.status_code == 200 and r.json['success'], r.json
    # Una OC al contado de un proveedor de afuera sigue bloqueada hasta el pago
    otra = admin.post('/compras/api/flujo/ordenes', json=_oc_flujo(zz, motivo_compra='Stock estratégico',
                                                                    items=[{'producto_id': zz['LENTE'], 'cantidad': 29, 'precio_unitario': 7}])).json['id']
    _sql("UPDATE ordenes_compra SET estado = 'Aprobada' WHERE id = %s", (otra,), fetch=False)
    fila = next(o for o in admin.get('/compras/api/flujo/por_recibir').json['data'] if o['id'] == otra)
    assert fila['paso']['codigo'] == 'pagar' and fila['falta_pago_intercompany'] is False


def test_recibir_con_diferencia_avisa_antes_de_grabar(zz, admin):
    # Pedido de Erika 22/10/2026 12:21: la OC pide 5 y se escribe 50 → ventana antes de grabar
    ruc = _sql("SELECT ruc FROM erp_empresas WHERE codigo = 'KCF'")[0][0]
    prov = _sql("SELECT id FROM proveedores WHERE ruc = %s ORDER BY id LIMIT 1", (ruc,))[0][0]
    oc_id = admin.post('/compras/api/flujo/ordenes', json=_oc_flujo(zz, proveedor_id=prov, motivo_compra='Stock estratégico',
                                                                    items=[{'producto_id': zz['LENTE'], 'cantidad': 5, 'precio_unitario': 3}])).json['id']
    _sql("UPDATE ordenes_compra SET estado = 'Aprobada' WHERE id = %s", (oc_id,), fetch=False)
    items = admin.get(f'/compras/api/flujo/ordenes/{oc_id}/para_recibir').json['items']
    rec = {'almacen_id': zz['sede'], 'guia_proveedor': 'T001-ZZ-50', 'traido_por_tipo': 'proveedor',
           'items': [{'oc_item_id': items[0]['id'], 'cantidad_buena': 50, 'cantidad_danada': 0}]}
    r = admin.post(f'/compras/api/flujo/ordenes/{oc_id}/recibir', json=rec)
    assert r.status_code == 409 and r.json['codigo'] == 'diferencias', r.json
    assert 'la OC pide 5' in r.json['diferencias'][0]['texto'] and 'sobran 45' in r.json['diferencias'][0]['texto']
    assert _sql("SELECT COUNT(*) FROM com_recepciones WHERE orden_compra_id = %s", (oc_id,))[0][0] == 0   # no se grabó
    rec.update(confirmar_diferencias=True, motivo_diferencias='El proveedor mandó de más')
    r = admin.post(f'/compras/api/flujo/ordenes/{oc_id}/recibir', json=rec)
    assert r.status_code == 200 and r.json['success'], r.json
    hist = [h[0] for h in _sql("SELECT detalle FROM com_historial WHERE orden_compra_id = %s AND accion = 'Recibió confirmando diferencias'", (oc_id,))]
    assert hist and 'sobran 45' in hist[0] and 'mandó de más' in hist[0]
    assert _sql("SELECT COUNT(*) FROM com_incidencias WHERE orden_compra_id = %s AND tipo = 'Sobrante'", (oc_id,))[0][0] == 1


def test_cobros_y_pagos_muestran_oc_y_pc(admin):
    # Erika 22/10/2026 12:26: cada pago con su N° OC y N° PV (trazabilidad), y se puede buscar por ellos
    pagos = admin.get('/finanzas/api/movimientos?tipo=PAGO').json['data']
    con_oc = [m for m in pagos if m.get('oc_numero')]
    assert con_oc, 'los pagos de las pruebas de Compras deberían tener su OC'
    m = con_oc[0]
    assert m['pc_numero']           # N° PV, o "Compra a stock" / "Sin PV vinculado"
    r = admin.get('/finanzas/api/movimientos', query_string={'q': m['oc_numero']}).json['data']
    assert any(x['id'] == m['id'] for x in r)
    for c in admin.get('/finanzas/api/movimientos?tipo=COBRO').json['data']:
        assert 'pc_numero' in c and 'oc_cliente' in c
    assert 'N° PC / N° OC<small>cliente · proveedor</small>' in admin.get('/finanzas').get_data(as_text=True)


def test_intercompany_una_fila_por_oc_de_principio_a_fin(zz, admin):
    # Erika 22/10/2026 12:34: en 7.2 una tabla integral por OC entre empresas (OC, PV, cotización, cliente,
    # pago, recepción, despacho, facturas). Antes solo veía facturas de venta y la OC no aparecía.
    agd = _sql("SELECT id, ruc FROM erp_empresas WHERE codigo = 'AGD'")
    if not agd:
        pytest.skip('Falta la empresa AGD en la base de pruebas')
    agd_id, agd_ruc = agd[0]
    kcf_ruc = _sql("SELECT ruc FROM erp_empresas WHERE codigo = 'KCF'")[0][0]
    prov = _sql("""INSERT INTO proveedores (razon_social, ruc, direccion, condicion_pago, activo)
                   VALUES ('AGD GROUP ZZ S.A.C.', %s, 'Breña', 'Crédito 30 días', true) RETURNING id""", (agd_ruc,))[0][0]
    r = admin.post('/compras/api/flujo/ordenes', json=_oc_flujo(zz, proveedor_id=prov, motivo_compra='Stock estratégico',
                                                                  condicion_pago='Crédito', dias_credito=30,
                                                                  items=[{'producto_id': zz['LENTE'], 'cantidad': 4, 'precio_unitario': 10}]))
    assert r.status_code == 200, r.json
    oc_id = r.json['id']
    numero = _sql("SELECT numero_orden FROM ordenes_compra WHERE id = %s", (oc_id,))[0][0]
    _sql("UPDATE ordenes_compra SET estado = 'Aprobada' WHERE id = %s", (oc_id,), fetch=False)

    def fila():
        d = admin.get('/intercompany/api/resumen').json['data']
        return next(o for o in d['operaciones'] if o['oc_id'] == oc_id)
    o = fila()
    assert o['vende'] == 'AGD' and o['compra'] == 'KCF' and o['para_stock'] is True and o['completa'] is False
    assert o['saldo'] > 0 and any('Pagar' in f and 'crédito' in f for f in o['falta'])
    assert any('Recibir la mercadería en KCF' == f for f in o['falta'])
    assert any(f.startswith('Despacho en AGD') for f in o['falta']) and any(f.startswith('Factura de venta de AGD') for f in o['falta'])
    # 22/10/2026 18:00: orden del negocio (a crédito el pago va al final) y un solo siguiente paso con quién lo hace
    assert o['siguiente'] == {'codigo': 'despachar', 'quien': 'AGD', 'texto': 'Despacho en AGD (su stock aún no descuenta)'}
    assert o['falta'][-1].startswith('Pagar') and o['estados'] == {'pago': False, 'recibido': False, 'despachado': False,
                                                                    'facturado': False, 'registrado': False}
    # KCF recibe; AGD hace su PV con "N° PC (Pedido del cliente)" = la OC, despacha y factura
    items = admin.get(f'/compras/api/flujo/ordenes/{oc_id}/para_recibir').json['items']
    r = admin.post(f'/compras/api/flujo/ordenes/{oc_id}/recibir', json={
        'almacen_id': zz['sede'], 'guia_proveedor': 'T001-IC-1', 'traido_por_tipo': 'proveedor',
        'items': [{'oc_item_id': items[0]['id'], 'cantidad_buena': 4, 'cantidad_danada': 0}]})
    assert r.status_code == 200, r.json
    _sql("""INSERT INTO pedido_compra_pc (numero, estado, cliente, ruc, empresa_id, oc_cliente)
            VALUES ('PC-AGD-ZZ1', 'Aprobado', 'KCF ZZ', %s, %s, %s)""", (kcf_ruc, agd_id, numero), fetch=False)
    _sql("""INSERT INTO despachos (numero, estado, pc_numero, cliente, ruc, empresa_id)
            VALUES ('DESP-AGD-ZZ1', 'Despachado', 'PC-AGD-ZZ1', 'KCF ZZ', %s, %s)""", (kcf_ruc, agd_id), fetch=False)
    _sql("""INSERT INTO comprobantes (tipo_comprobante, serie, numero, fecha_emision, cliente_tipo_doc, cliente_numero_doc,
                                      cliente_nombre, subtotal, igv, total, items_json, estado_sunat, empresa_id,
                                      orden_compra_cliente)
            VALUES ('01', 'F001', 777, CURRENT_DATE, '6', %s, 'KCF ZZ', 40, 7.2, 47.2, '[]', 'ACEPTADO', %s, %s)""", (kcf_ruc, agd_id, numero), fetch=False)
    o = fila()
    assert o['recibida'] == 4 and o['pc_vende'] == 'PC-AGD-ZZ1' and o['despachos'] == 'DESP-AGD-ZZ1'
    assert o['factura_venta'].startswith('F001-') and o['factura_venta'].endswith('777')
    assert o['falta'] == ['Registrar la factura en compras de KCF', f"Pagar {o['saldo']:,.2f} a AGD (crédito)"]
    assert o['siguiente']['quien'] == 'KCF' and o['estados']['facturado'] and not o['estados']['registrado']
    # Resumen consolidado por sentido: cuadra con la tabla (falta pagar sale de las OC)
    d = admin.get('/intercompany/api/resumen').json['data']
    c = next(x for x in d['consolidado'] if (x['vende'], x['compra']) == ('AGD', 'KCF'))
    mias = [x for x in d['operaciones'] if (x['vende'], x['compra']) == ('AGD', 'KCF')]
    assert c['ocs'] == len(mias) and c['falta_pagar'] == round(sum(x['saldo'] for x in mias), 2)
    assert c['por_registrar'] == sum(1 for x in mias if not x['estados']['registrado']) >= 1
    # La pantalla tiene la tabla
    html = admin.get('/intercompany').get_data(as_text=True)
    assert 'icOperaciones' in html and 'AGD le vende a KCF' in html


def test_banco_siempre_de_la_lista(admin):
    # Erika 22/10/2026 12:48: el banco con desplegable, para que no se escriba de formas distintas
    from utils import normalizar_banco
    assert normalizar_banco('bcp ') == 'BCP' and normalizar_banco('Banco de Crédito del Perú') == 'BCP'
    assert normalizar_banco('BBVA Continental') == 'BBVA' and normalizar_banco('banco de la nacion') == 'Banco de la Nación'
    assert normalizar_banco('') is None and normalizar_banco('Caja Raíz') == 'Caja Raíz'
    for url in ('/finanzas', '/compras'):
        html = admin.get(url).get_data(as_text=True)
        assert 'id="pagoBanco" data-lista="bancos"' in html and 'lista_bancos.js' in html, url
    js = open('static/js/lista_bancos.js', encoding='utf-8').read()
    assert "'Banco de la Nación'" in js and 'Otro (escribir)' in js


def test_rotulo_con_los_4_numeros_y_nombre_en_una_linea(app, admin):
    # Erika 22/10/2026 12:57: N° despacho, N° PV, N° Guía y N° Factura ("—" si falta); sin URL ni redes; nombre sin E.I.R.L.
    from routes.ventas import _numeros_rotulo
    from pdf_generator import pdf_generator
    _sql("""INSERT INTO despachos (numero, cliente, ruc, estado, pc_numero, guia)
            VALUES ('DSP-ZZ-ROT', 'CLIENTE ROT', '20100070970', 'Pendiente despacho', 'PC-ZZ-ROT', 'T001-000123')""", fetch=False)
    did = _sql("SELECT id FROM despachos WHERE numero = 'DSP-ZZ-ROT'")[0][0]
    with app.app_context():
        n = _numeros_rotulo(despacho={'numero': 'DSP-ZZ-ROT', 'pc_numero': 'PC-ZZ-ROT', 'guia': 'T001-000123', 'comprobante': None})
        assert n == {'nro_despacho': 'DSP-ZZ-ROT', 'nro_pc': 'PC-ZZ-ROT', 'nro_guia': 'T001-000123', 'nro_factura': '—'}
        g = _numeros_rotulo(guia={'serie': 'T001', 'numero': '123', 'factura': 'F001-9'})
        assert g['nro_despacho'] == 'DSP-ZZ-ROT' and g['nro_pc'] == 'PC-ZZ-ROT' and g['nro_factura'] == 'F001-9'
    assert pdf_generator._nombre_rotulo('KCF CORPORACION E.I.R.L.') == 'KCF CORPORACIÓN'
    assert pdf_generator._nombre_rotulo('AGD GROUP S.A.C.') == 'AGD GROUP'
    plantilla = pdf_generator._obtener_template_rotulo_guia()
    assert 'social-icon">' not in plantilla and 'empresa_web' not in plantilla and 'N° Pedido de venta' in plantilla
    r = admin.get(f'/ventas/api/rotulo/despacho/{did}')
    assert r.status_code == 200 and r.data[:4] == b'%PDF'


def test_intercompany_reconoce_proveedor_con_ruc_mal_escrito(zz, admin):
    # Erika 22/10/2026 13:17 "no se actualiza": si el proveedor del grupo tiene el RUC mal escrito, igual aparece y avisa
    agd = _sql("SELECT razon_social, ruc FROM erp_empresas WHERE codigo = 'AGD'")
    if not agd or not agd[0][0]:
        pytest.skip('AGD sin razón social en la base de pruebas')
    prov = _sql("""INSERT INTO proveedores (razon_social, ruc, direccion, condicion_pago, activo)
                   VALUES (%s, '20999999990', 'Breña', 'Contado', true) RETURNING id""", (agd[0][0],))[0][0]
    r = admin.post('/compras/api/flujo/ordenes', json=_oc_flujo(zz, proveedor_id=prov, motivo_compra='Stock estratégico',
                                                                  items=[{'producto_id': zz['LENTE'], 'cantidad': 2, 'precio_unitario': 5}]))
    oc_id = r.json['id']
    o = next(x for x in admin.get('/intercompany/api/resumen').json['data']['operaciones'] if x['oc_id'] == oc_id)
    assert o['vende'] == 'AGD' and o['falta'][0].startswith('Corregir el RUC')
    assert any(f.startswith('Aprobar la OC') for f in o['falta']) or o['estado_oc'] not in ('Borrador', 'Por aprobar')


def test_stock_se_reparte_y_oc_generada_cuenta_como_por_llegar(zz, admin):
    # Erika 22/10/2026 13:21: stock 32, un PV de 18 (más antiguo) y otro de 40 → faltan 26, no 8 ni 58.
    # 13:21 urgente: con la OC ya generada (aunque esté en borrador) debe decir "Comprado, por llegar" con su N° de OC.
    import json
    _sql("""INSERT INTO productos (familia, codigo, descripcion, marca, unidad, costo_unitario, precio_unitario, stock, activo)
            VALUES ('GENERAL', 'ZZ-EST', 'ESTABILIZADOR ZZ 120W', 'ZZ', 'UND', 0, 120, 0, true)""", fetch=False)
    prod = _sql("SELECT id FROM productos WHERE codigo = 'ZZ-EST'")[0][0]
    _sql("INSERT INTO inv_stock (empresa_id, almacen_id, producto_id, cantidad) VALUES (%s, %s, %s, 32)",
         (zz['emp'], zz['sede'], prod), fetch=False)
    ids = []
    for num, cant, dias in (('PC-ZZ-EST-A', 18, 2), ('PC-ZZ-EST-B', 40, 0)):
        items = [{'codigo': 'ZZ-EST', 'producto': 'ESTABILIZADOR ZZ 120W', 'cantidad_pc': cant, 'precio_pc': 120}]
        ids.append(_sql("""INSERT INTO pedido_compra_pc (numero, cliente, ruc, estado, items_json, fecha, empresa_id)
                           VALUES (%s, 'CLIENTE EST', '20100070970', 'Pendiente', %s, NOW() - %s * INTERVAL '1 day', %s) RETURNING id""",
                        (num, json.dumps(items), dias, zz['emp']))[0][0])
    peds = {p['id']: p for p in admin.get('/compras/api/flujo/pedidos', query_string={'todos': '1'}).json['data']}
    a, b = peds[ids[0]]['items'][0], peds[ids[1]]['items'][0]
    assert (a['stock_asignado'], a['comprar_pedido']) == (18, 0)          # el más antiguo usa 18 del stock
    assert (b['stock_asignado'], b['comprar_pedido']) == (14, 26)         # al otro le tocan 14: faltan 26
    d = admin.get('/compras/api/flujo/abastecimiento', query_string={'empresa_id': zz['emp'], 'productos': prod}).json['data'][0]
    assert d['stock'] == 32 and d['por_comprar'] == 26
    assert {p['numero']: p['por_comprar'] for p in d['pedidos']} == {'PC-ZZ-EST-A': 0, 'PC-ZZ-EST-B': 26}
    # Sin OC: pendiente de compra
    assert admin.get('/api/abastecimiento/pc').json['data'][str(ids[1])]['estado'] == 'Pendiente por compra'
    # OC en borrador para el pedido B → "Por llegar" con su N° de OC
    r = admin.post('/compras/api/flujo/ordenes', json=_oc_flujo(zz, items=[{'producto_id': prod, 'cantidad': 26, 'precio_unitario': 100,
                                                                              'pedido_id': ids[1]}]))
    assert r.status_code == 200, r.json
    numero = _sql("SELECT numero_orden FROM ordenes_compra WHERE id = %s", (r.json['id'],))[0][0]
    est = admin.get('/api/abastecimiento/pc').json['data']
    assert est[str(ids[1])]['estado'] == 'Por llegar' and numero in est[str(ids[1])]['ocs']
    assert est[str(ids[0])]['estado'] == 'Con stock'
    # Pedidos por comprar ya no lo pide otra vez
    b = next(p for p in admin.get('/compras/api/flujo/pedidos', query_string={'todos': '1'}).json['data'] if p['id'] == ids[1])['items'][0]
    assert b['comprado'] == 26 and b['comprar_pedido'] == 0
    # Despachar sin stock físico con la OC en camino: mensaje claro con el N° de OC
    from routes.stock_automatico import texto_en_transito
    from main import app as aplicacion
    with aplicacion.app_context():
        t = texto_en_transito([{'producto': 'ESTABILIZADOR ZZ 120W', 'producto_id': prod}])
    assert numero in t and 'Recíbela en Compras' in t


def test_oc_impresa_con_datos_para_la_transferencia(zz, admin):
    # Pedido de Erika 22/10/2026 (pre-producción): banco, N° de cuenta y CCI del proveedor, como texto que se copia
    _sql("UPDATE proveedores SET banco = 'BCP', numero_cuenta = '193-7777777-0-77', cci = '00219300777777707777' WHERE id = %s",
         (zz['prov'],), fetch=False)
    r = admin.post('/compras/api/flujo/ordenes', json=_oc_flujo(zz, motivo_compra='Stock estratégico',
                                                              items=[{'producto_id': zz['LENTE'], 'cantidad': 37, 'precio_unitario': 9}]))
    assert r.status_code == 200, r.json
    oc_id = r.json['id']
    _sql("UPDATE ordenes_compra SET estado = 'Aprobada' WHERE id = %s", (oc_id,), fetch=False)
    html = admin.get(f'/compras/flujo/ordenes/{oc_id}/imprimir').get_data(as_text=True)
    assert 'Datos para la transferencia' in html and 'BCP' in html
    assert '<span class="dato">00219300777777707777</span>' in html and 'user-select:all' in html
    _sql("UPDATE proveedores SET numero_cuenta = NULL, cci = NULL WHERE id = %s", (zz['prov'],), fetch=False)
    html = admin.get(f'/compras/flujo/ordenes/{oc_id}/imprimir').get_data(as_text=True)
    assert 'transfer no-print' in html and 'no tiene cuenta bancaria registrada' in html


def test_monitor_de_errores_en_consola(admin, anonimo):
    for url in ('/compras', '/ventas', '/finanzas'):
        assert 'monitor_consola.js' in admin.get(url).get_data(as_text=True), url
    assert 'monitor_consola.js' in anonimo.get('/login').get_data(as_text=True)
    base = open('templates/base.html', encoding='utf-8').read()
    assert base.index('errores_guardado.js') < base.index('monitor_consola.js')
    js = open('static/js/monitor_consola.js', encoding='utf-8').read()
    assert "addEventListener('unhandledrejection'" in js and 'console.error' in js and 'erpErrores' in js


def test_compras_terminos_y_orden_global(admin):
    # Erika 22/10/2026 18:13: términos de Compras, colores de la OC, columna Ítem y ayudas con "ⓘ Ver más"
    js = open('static/js/compras_flujo.js', encoding='utf-8').read()
    assert 'PV<small>Pedido de venta' in js and 'Stock asignado' in js and 'Compra bajo pedido' in js
    assert 'Stock que le toca' not in js and 'Saldo después de entregar' not in js and 'para PV más antiguos' in js
    html = admin.get('/compras').get_data(as_text=True)
    assert '<th>Forma de pago</th><th>Total (inc. IGV)</th>' in html and 'com-flujo-plegable' in html
    assert 'orden_pantallas.js' in html
    css = open('static/css/compras_flujo.css', encoding='utf-8').read()
    assert '.est-por-aprobar{background:#FF0033' in css and '.est-recibida{background:#0057FF' in css and 'com-barra-100' in css
    g = open('static/js/orden_pantallas.js', encoding='utf-8').read()
    assert "th.textContent = 'Ítem'" in g and 'ⓘ Ver más' in g and '.modal' in g
