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
    rec = {'almacen_id': zz['sede'], 'guia_proveedor': 'T001-ZZ-22', 'traido_por_tipo': 'externo', 'traido_por_nombre': 'Chofer AGD',
           'items': [{'oc_item_id': items[0]['id'], 'cantidad_buena': 23, 'cantidad_danada': 0}]}
    r = zz['compra'].post(f'/compras/api/flujo/ordenes/{oc_id}/recibir', json=rec)
    assert 'pago' not in (r.json.get('error') or ''), r.json
    # Una OC al contado de un proveedor de afuera sigue bloqueada hasta el pago
    otra = admin.post('/compras/api/flujo/ordenes', json=_oc_flujo(zz, motivo_compra='Stock estratégico',
                                                                    items=[{'producto_id': zz['LENTE'], 'cantidad': 29, 'precio_unitario': 7}])).json['id']
    _sql("UPDATE ordenes_compra SET estado = 'Aprobada' WHERE id = %s", (otra,), fetch=False)
    fila = next(o for o in admin.get('/compras/api/flujo/por_recibir').json['data'] if o['id'] == otra)
    assert fila['paso']['codigo'] == 'pagar' and fila['falta_pago_intercompany'] is False
