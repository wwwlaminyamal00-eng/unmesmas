"""
Pruebas del pedido de Erika del 15/10/2026:
  - Selector de empresa (KCF / AGD / Todas): cada documento guarda su empresa y las listas se filtran.
  - Con "Todas las empresas" se ve todo, pero para crear hay que elegir una empresa.
  - Los documentos que nacen de otro heredan su empresa; la numeración de facturas es por empresa.
  - Los colores del sistema y el rótulo cambian con la empresa.
  - Inventario muestra todos los productos (también sin stock) y se puede cargar stock inicial al crear un producto.
  - Al reabrir una cotización se recupera lo guardado (transporte, parihuela, nota interna, descuento y precios).
"""
import pytest

from conftest import _login
from tests.test_flujos import sql, nueva_cotizacion, factura


@pytest.fixture(scope='module')
def emp(app):
    sql("""
        INSERT INTO erp_empresas (codigo, nombre_corto, nombre_comercial, razon_social, ruc, direccion_fiscal, estado,
                                  color_primario, color_secundario, color_pastel)
        SELECT 'KCF', 'KCF', 'KCF', 'KCF S.A.C.', '20111111111', 'Av. Perú 123, SMP', 'activo', '#D6243A', '#1D1A1F', '#FDE8EB'
        WHERE NOT EXISTS (SELECT 1 FROM erp_empresas WHERE codigo = 'KCF');
        INSERT INTO erp_empresas (codigo, nombre_corto, nombre_comercial, razon_social, ruc, direccion_fiscal, estado,
                                  color_primario, color_secundario, color_pastel)
        SELECT 'AGD', 'AGD', 'AGD', 'AGD S.A.C.', '20222222222', 'Jr. Breña 456', 'activo', '#1D4ED8', '#1D1A1F', '#DBEAFE'
        WHERE NOT EXISTS (SELECT 1 FROM erp_empresas WHERE codigo = 'AGD');
        INSERT INTO almacenes (codigo, nombre, direccion, activo)
        SELECT 'SMP', 'San Martín de Porres', 'Av. Perú 123, SMP', true WHERE NOT EXISTS (SELECT 1 FROM almacenes WHERE codigo = 'SMP');
    """)
    from routes import multiempresa
    multiempresa.empresas(refrescar=True)
    return {c: str(i) for c, i in sql("SELECT codigo, id FROM erp_empresas WHERE codigo IN ('KCF', 'AGD')")}


def _cliente(app, codigo):
    c = _login(app, 'vendedor', 'Vende#2026!')
    r = c.post('/api/empresa_activa', json={'codigo': codigo})
    assert r.status_code == 200, r.json
    return c


@pytest.fixture(scope='module')
def kcf(app, emp):
    return _cliente(app, 'KCF')


@pytest.fixture(scope='module')
def agd(app, emp):
    return _cliente(app, 'AGD')


@pytest.fixture(scope='module')
def todas(app, emp):
    return _cliente(app, 'TODAS')


def _ids(cliente, url):
    return {f['id'] for f in cliente.get(url).json['data']}


def test_selector_de_empresa(kcf, emp):
    r = kcf.get('/api/empresa_activa').json
    assert r['codigo'] == 'KCF' and r['empresa_id'] == emp['KCF']
    assert {e['codigo'] for e in r['empresas']} >= {'KCF', 'AGD'}
    assert kcf.post('/api/empresa_activa', json={'codigo': 'NOEXISTE'}).status_code == 400


def test_cotizacion_guarda_su_empresa_y_las_listas_se_filtran(kcf, agd, todas, emp):
    c_kcf = nueva_cotizacion(kcf).json['data']['id']
    c_agd = nueva_cotizacion(agd).json['data']['id']
    assert sql("SELECT empresa_id::text FROM cotizaciones WHERE id = %s", (c_agd,))[0][0] == emp['AGD']
    assert sql("SELECT empresa_id::text FROM cotizaciones WHERE id = %s", (c_kcf,))[0][0] == emp['KCF']
    ver_kcf, ver_agd, ver_todas = (_ids(x, '/ventas/api/cotizaciones/listar') for x in (kcf, agd, todas))
    assert c_kcf in ver_kcf and c_agd not in ver_kcf
    assert c_agd in ver_agd and c_kcf not in ver_agd
    assert {c_kcf, c_agd} <= ver_todas


def test_con_todas_no_se_puede_crear(todas):
    r = nueva_cotizacion(todas)
    assert r.status_code == 400 and 'elige arriba la empresa' in r.json['error']


def test_factura_hereda_empresa_y_numera_por_empresa(kcf, agd, todas, emp):
    cot = sql("SELECT numero_cotizacion FROM cotizaciones WHERE empresa_id = %s ORDER BY id DESC LIMIT 1", (emp['AGD'],))[0][0]
    # Se crea desde "Todas": hereda AGD de la cotización
    f1 = factura(todas, serie='F777', cotizacion=cot)
    assert f1.status_code == 200, f1.json
    f2 = factura(kcf, serie='F777')
    assert f1.json['data']['numero'] == '00000001' and f2.json['data']['numero'] == '00000001'  # cada RUC su correlativo
    assert sql("SELECT empresa_id::text FROM comprobantes WHERE id = %s", (f1.json['data']['id'],))[0][0] == emp['AGD']
    assert f1.json['data']['id'] in _ids(agd, '/ventas/api/comprobantes/listar')
    assert f1.json['data']['id'] not in _ids(kcf, '/ventas/api/comprobantes/listar')


def test_finanzas_por_empresa(kcf, agd, emp):
    f = factura(agd, serie='F778', estado='Emitido').json['data']['id']
    sql("UPDATE comprobantes SET estado_sunat = 'Emitido' WHERE id = %s", (f,))
    assert f in {x['id'] for x in agd.get('/finanzas/api/cxc').json['data']}
    assert f not in {x['id'] for x in kcf.get('/finanzas/api/cxc').json['data']}


def test_colores_y_selector_en_la_pagina(agd, todas):
    color = sql("SELECT color_primario FROM erp_empresas WHERE codigo = 'AGD'")[0][0]
    html = agd.get('/index').get_data(as_text=True)
    assert 'data-empresa="AGD"' in html and f'--empresa:{color}' in html
    assert '<option value="AGD" selected' in html and 'Todas las empresas (consolidado)' in html
    html = todas.get('/index').get_data(as_text=True)
    assert 'data-empresa="TODAS"' in html


def test_rotulo_de_despacho_con_una_hoja_por_caja(agd, emp):
    did = sql("""INSERT INTO despachos (numero, cliente, ruc, destino, estado, items_json, empresa_id)
                 VALUES ('DES-ROT-1', 'CLIENTE ROTULO S.A.C.', '20100070970', 'Av. Lima 100', 'Pendiente despacho', '[]', %s)
                 RETURNING id""", (emp['AGD'],))[0][0]
    r = agd.get(f'/ventas/api/rotulo/despacho/{did}?bultos=3')
    assert r.status_code == 200 and r.mimetype == 'application/pdf'
    assert r.data[:4] == b'%PDF'
    pypdf = pytest.importorskip('pypdf')
    import io
    assert len(pypdf.PdfReader(io.BytesIO(r.data)).pages) == 3  # una hoja por caja: 1/3, 2/3, 3/3
    assert agd.get('/ventas/api/rotulo/otro/1').status_code == 400


def test_inventario_muestra_productos_sin_stock_y_pendientes(app, emp):
    admin = _login(app, 'admin', 'Admin#2026!')
    data = admin.get('/inventario/api/consolidado?todos=true').json
    assert any(p['codigo'] == 'PRD-0001' and p['total'] == 0 for p in data['data'])
    assert 'pendientes' in data and 'cantidad' in data['pendientes']


def test_crear_producto_con_stock_inicial(app, emp):
    admin = _login(app, 'admin', 'Admin#2026!')
    sede = sql("SELECT id FROM almacenes ORDER BY id LIMIT 1")[0][0]
    r = admin.post('/productos/api/productos', json={
        'descripcion': 'CONO DE SEGURIDAD', 'modelo': 'C-70', 'marca': 'SEGUSA', 'familia': 'GENERAL', 'unidad': 'UND',
        'transporte': 'auto', 'costo_unitario': 12, 'precio_unitario': 20,
        'stock_inicial_cantidad': 15, 'stock_inicial_empresa': emp['AGD'], 'stock_inicial_almacen': sede})
    assert r.status_code == 200, r.json
    assert 'Stock inicial registrado' in r.json['message']
    pid = r.json['data']['id']
    assert float(sql("SELECT cantidad FROM inv_stock WHERE producto_id = %s AND empresa_id = %s", (pid, emp['AGD']))[0][0]) == 15
    assert float(sql("SELECT stock FROM productos WHERE id = %s", (pid,))[0][0]) == 15
    # Un vendedor (no aprueba): queda pendiente y no suma todavía
    vend = _login(app, 'vendedor', 'Vende#2026!')
    r = vend.post('/productos/api/productos', json={
        'descripcion': 'CINTA SEÑALIZADORA', 'modelo': 'CS-1', 'marca': 'SEGUSA', 'familia': 'GENERAL', 'unidad': 'UND',
        'transporte': 'auto', 'costo_unitario': 5, 'stock_inicial_cantidad': 4,
        'stock_inicial_empresa': emp['KCF'], 'stock_inicial_almacen': sede})
    assert r.status_code == 200 and 'pendiente' in r.json['message']
    assert sql("SELECT estado FROM inv_movimientos WHERE producto_id = %s", (r.json['data']['id'],))[0][0] == 'Pendiente'
    # Sin sede: no se crea nada a medias
    r = admin.post('/productos/api/productos', json={
        'descripcion': 'MAL', 'modelo': 'X', 'marca': 'X', 'familia': 'GENERAL', 'unidad': 'UND', 'transporte': 'auto',
        'stock_inicial_cantidad': 3, 'stock_inicial_empresa': emp['KCF']})
    assert r.status_code == 400 and sql("SELECT COUNT(*) FROM productos WHERE descripcion = 'MAL'")[0][0] == 0


def _texto_pdf(datos):
    pypdf = pytest.importorskip('pypdf')
    import io
    return ' '.join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(datos)).pages)


def test_pdf_de_cotizacion_y_factura_salen_con_su_empresa(kcf, agd, emp):
    ruc_agd, ruc_kcf = (sql("SELECT ruc FROM erp_empresas WHERE codigo = %s", (c,))[0][0] for c in ('AGD', 'KCF'))
    cot = nueva_cotizacion(agd).json['data']['id']
    r = agd.get(f'/ventas/api/cotizaciones/{cot}/pdf')
    assert r.status_code == 200
    texto = _texto_pdf(r.data)
    assert ruc_agd in texto and ruc_kcf not in texto
    assert '0011-0319' not in texto  # la cuenta bancaria de KCF no sale en una cotización de AGD
    f = factura(agd, serie='F779').json['data']['id']
    r = agd.get(f'/ventas/api/comprobantes/{f}/pdf')
    assert r.status_code == 200
    texto = _texto_pdf(r.data)
    assert ruc_agd in texto and ruc_kcf not in texto
    # Una cotización de KCF sigue saliendo con KCF
    cot = nueva_cotizacion(kcf).json['data']['id']
    assert ruc_kcf in _texto_pdf(kcf.get(f'/ventas/api/cotizaciones/{cot}/pdf').data)


def test_reabrir_cotizacion_recupera_lo_guardado(kcf):
    d = nueva_cotizacion(kcf, transporte='Camioneta', parihuela='Sí - estándar', nota_interna='Llamar antes',
                         seguimiento='Ana', motivo='Recompra', descuento_valor=20, descuento_tipo='S/').json['data']
    c = kcf.get(f"/ventas/api/cotizaciones/{d['id']}/completa").json['data']
    assert (c['transporte'], c['parihuela'], c['nota_interna'], c['motivo']) == ('Camioneta', 'Sí - estándar', 'Llamar antes', 'Recompra')
    assert c['descuento_tipo'] == 'S/' and float(c['descuento_monto']) == 20
    # el precio cotizado (no el precio actual del producto)
    assert sorted(p['valorVenta'] for p in c['productos']) == [15.0, 32.5]
    js = kcf.get('/static/js/ventas.js').get_data(as_text=True)
    cargador = js[js.index('async function cargarCotizacionParaEditar'):]
    cargador = cargador[:cargador.index('function updateQuoteStatusBar')]
    for campo in ('fTransporte', 'fParihuela', 'fNotaInterna', 'fDiscountValue', 'fDiscountType'):
        assert campo in cargador


def test_clientes_por_ambito(app, emp):
    sql("""INSERT INTO clientes (tipo_documento, numero_documento, razon_social, direccion_fiscal, codigo_cliente, activo, ambito)
           VALUES ('RUC', '20999999991', 'SOLO AGD S.A.C.', 'Jr. Breña 1', 'CLI-AGD1', true, 'AGD')""")
    kcf, agd = _cliente(app, 'KCF'), _cliente(app, 'AGD')
    nombres = lambda c: {x['razon_social'] for x in c.get('/maestros/api/clientes/listar').json['data']}
    assert 'SOLO AGD S.A.C.' in nombres(agd) and 'SOLO AGD S.A.C.' not in nombres(kcf)
    assert 'CLIENTE INDUSTRIAL S.A.C.' in nombres(kcf) and 'CLIENTE INDUSTRIAL S.A.C.' in nombres(agd)
