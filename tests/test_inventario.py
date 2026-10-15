"""
Pruebas del módulo de Inventario multiempresa / multisede.
Escenario: dos empresas (KCF y AGD) y dos sedes (San Martín de Porres y Breña).
"""
import threading
import psycopg2
import pytest
from werkzeug.security import generate_password_hash

from tests.conftest import TEST_DB, _login


def _sql(q, params=None, fetch=True):
    conn = psycopg2.connect(TEST_DB)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(q, params)
    r = cur.fetchall() if fetch and cur.description else None
    conn.close()
    return r


@pytest.fixture(scope='module')
def esc(app):
    """Crea empresas, sedes, productos y usuarios de almacén y de control."""
    _sql("""
        INSERT INTO erp_empresas (codigo, nombre_corto, nombre_comercial, razon_social, ruc, estado, color_primario, color_secundario, color_pastel) VALUES
            ('KCF', 'KCF', 'KCF', 'KCF S.A.C.', '20111111111', 'activo', '#D6243A', '#1D1A1F', '#FDE8EB'),
            ('AGD', 'AGD', 'AGD', 'AGD S.A.C.', '20222222222', 'activo', '#1E3A8A', '#1D1A1F', '#DBEAFE');
        INSERT INTO almacenes (codigo, nombre, direccion, activo) VALUES
            ('SMP', 'San Martín de Porres', 'Av. Perú 123, SMP', true),
            ('BRE', 'Breña', 'Jr. Huaraz 456, Breña', true);
        INSERT INTO productos (familia, codigo, descripcion, marca, unidad, costo_unitario, precio_unitario, stock, activo) VALUES
            ('GENERAL', 'INV-001', 'IPHONE 17 PRO MAX NARANJA', 'APPLE', 'UND', 5000, 6500, 0, true),
            ('GENERAL', 'INV-002', 'GUANTE ANTICORTE', '3M', 'PAR', 10, 18, 0, true),
            ('GENERAL', 'INV-003', 'LENTE DE SEGURIDAD', 'STEELPRO', 'UND', 5, 9, 7, true);
    """, fetch=False)
    _sql("""INSERT INTO usuarios (usuario_sistema, usuario, nombres_apellidos, nombre_completo, correo, password, rol, estado) VALUES
            ('alm1', 'alm1', 'Almacén Uno', 'Almacén Uno', 'a1@t.pe', %s, 'almacen', 'activo'),
            ('alm2', 'alm2', 'Almacén Dos', 'Almacén Dos', 'a2@t.pe', %s, 'almacen', 'activo'),
            ('ctrl', 'ctrl', 'Control Inventario', 'Control Inventario', 'c@t.pe', %s, 'control', 'activo')""",
         (generate_password_hash('Alm#2026!'), generate_password_hash('Alm#2026!'), generate_password_hash('Ctrl#2026!')),
         fetch=False)
    emp = dict(_sql("SELECT codigo, id FROM erp_empresas"))
    sede = dict(_sql("SELECT codigo, id FROM almacenes WHERE codigo IN ('SMP', 'BRE')"))
    prod = dict(_sql("SELECT codigo, id FROM productos WHERE codigo LIKE 'INV-%'"))
    return {'KCF': emp['KCF'], 'AGD': emp['AGD'], 'SMP': sede['SMP'], 'BRE': sede['BRE'],
            'IPHONE': prod['INV-001'], 'GUANTE': prod['INV-002'], 'LENTE': prod['INV-003'],
            'alm1': _login(app, 'alm1', 'Alm#2026!'), 'alm2': _login(app, 'alm2', 'Alm#2026!'),
            'ctrl': _login(app, 'ctrl', 'Ctrl#2026!')}


def _stock(e, emp, sede, prod):
    r = _sql("SELECT cantidad, costo_promedio FROM inv_stock WHERE empresa_id=%s AND almacen_id=%s AND producto_id=%s",
             (e[emp], e[sede], e[prod]))
    return (float(r[0][0]), float(r[0][1])) if r else (0.0, 0.0)


def _mov(cliente, e, motivo, emp, sede, prod, cantidad, **extra):
    body = {'motivo': motivo, 'empresa_id': e[emp], 'almacen_id': e[sede], 'producto_id': e[prod], 'cantidad': cantidad}
    body.update(extra)
    return cliente.post('/inventario/api/movimientos', json=body)


def test_pagina_y_permisos(esc, admin, vendedor, anonimo):
    assert admin.get('/inventario/').status_code == 200
    assert anonimo.get('/inventario/api/consolidado').status_code == 401
    # Un vendedor no registra entradas, pero sí puede separar stock
    r = _mov(vendedor, esc, 'COMPRA', 'KCF', 'SMP', 'IPHONE', 1, costo_unitario=5000, documento_numero='F001-1')
    assert r.status_code == 403


def test_entrada_costo_promedio_y_documento_obligatorio(esc):
    a = esc['alm1']
    r = _mov(a, esc, 'COMPRA', 'KCF', 'SMP', 'IPHONE', 5, costo_unitario=5000)
    assert r.status_code == 400 and 'documento' in r.get_json()['error']
    assert _mov(a, esc, 'COMPRA', 'KCF', 'SMP', 'IPHONE', 5, costo_unitario=5000, documento_numero='GR-1').status_code == 200
    assert _mov(a, esc, 'COMPRA', 'KCF', 'SMP', 'IPHONE', 5, costo_unitario=5200, documento_numero='GR-2').status_code == 200
    assert _stock(esc, 'KCF', 'SMP', 'IPHONE') == (10.0, 5100.0)
    assert _mov(a, esc, 'COMPRA', 'KCF', 'BRE', 'IPHONE', 5, costo_unitario=5100, documento_numero='GR-3').status_code == 200
    assert _mov(a, esc, 'COMPRA', 'AGD', 'SMP', 'IPHONE', 5, costo_unitario=5000, documento_numero='GR-4').status_code == 200
    assert _mov(a, esc, 'COMPRA', 'AGD', 'BRE', 'IPHONE', 5, costo_unitario=5000, documento_numero='GR-5').status_code == 200
    # productos.stock (lo usa Ventas) = suma de todas las empresas y sedes
    assert float(_sql("SELECT stock FROM productos WHERE id=%s", (esc['IPHONE'],))[0][0]) == 25


def test_consolidado_por_empresa_y_sede(esc, admin):
    data = admin.get('/inventario/api/consolidado?q=IPHONE').get_json()['data']
    p = data[0]
    assert p['total'] == 25
    assert p['por_empresa'] == {str(esc['KCF']): 15, str(esc['AGD']): 10}
    assert p['celdas'][f"{esc['KCF']}-{esc['SMP']}"]['cantidad'] == 10
    assert p['celdas'][f"{esc['AGD']}-{esc['BRE']}"]['cantidad'] == 5
    csv = admin.get('/inventario/api/consolidado/exportar').get_data(as_text=True)
    assert 'IPHONE 17 PRO MAX' in csv and 'KCF - Breña' in csv


def test_no_hay_stock_negativo(esc):
    r = _mov(esc['alm1'], esc, 'VENTA', 'KCF', 'BRE', 'IPHONE', 6, documento_numero='T001-9')
    assert r.status_code == 400 and 'No hay stock suficiente' in r.get_json()['error']


def test_salidas_simultaneas_no_dejan_negativo(esc):
    resultados = []

    def vender():
        c = _login(esc['alm1'].application, 'alm1', 'Alm#2026!')
        resultados.append(_mov(c, esc, 'VENTA', 'AGD', 'BRE', 'IPHONE', 2, documento_numero='T001-X').status_code)

    hilos = [threading.Thread(target=vender) for _ in range(5)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert resultados.count(200) == 2  # 5 en stock: solo caben 2 ventas de 2
    assert _stock(esc, 'AGD', 'BRE', 'IPHONE')[0] == 1


def test_separacion_evita_revender(esc, vendedor):
    # El vendedor separa 8 de los 10 de KCF en SMP para el cliente A
    r = vendedor.post('/inventario/api/separaciones', json={
        'empresa_id': esc['KCF'], 'almacen_id': esc['SMP'], 'producto_id': esc['IPHONE'], 'cantidad': 8,
        'cliente': 'CLIENTE A', 'documento': 'PC-1'})
    assert r.status_code == 200
    # No se puede separar más de lo libre
    r = vendedor.post('/inventario/api/separaciones', json={
        'empresa_id': esc['KCF'], 'almacen_id': esc['SMP'], 'producto_id': esc['IPHONE'], 'cantidad': 3, 'cliente': 'B'})
    assert r.status_code == 400
    # Entregar 3 a otro cliente sin separación: solo hay 2 libres
    r = _mov(esc['alm1'], esc, 'VENTA', 'KCF', 'SMP', 'IPHONE', 3, documento_numero='T001-10', tercero='CLIENTE B')
    assert r.status_code == 400 and 'separados' in r.get_json()['error']
    # Entregar al cliente A usando su separación
    sep_id = _sql("SELECT id FROM inv_separaciones WHERE cliente='CLIENTE A'")[0][0]
    r = _mov(esc['alm1'], esc, 'VENTA', 'KCF', 'SMP', 'IPHONE', 8, documento_numero='T001-11', separacion_id=sep_id)
    assert r.status_code == 200
    assert _sql("SELECT estado, cantidad FROM inv_separaciones WHERE id=%s", (sep_id,))[0][0] == 'Entregada'
    assert _stock(esc, 'KCF', 'SMP', 'IPHONE')[0] == 2


def test_traslado_quien_envia_no_recibe_y_faltante(esc):
    r = esc['alm1'].post('/inventario/api/traslados', json={
        'empresa_id': esc['KCF'], 'origen_id': esc['BRE'], 'destino_id': esc['SMP'], 'encargado': 'Motorizado Juan',
        'guia_remision': 'T001-500', 'items': [{'producto_id': esc['IPHONE'], 'cantidad': 5}]})
    assert r.status_code == 200
    assert _stock(esc, 'KCF', 'BRE', 'IPHONE')[0] == 0
    tid, item = _sql("SELECT t.id, i.id FROM inv_traslados t JOIN inv_traslado_items i ON i.traslado_id=t.id "
                     "WHERE t.numero=%s", (r.get_json()['numero'],))[0]
    r = esc['alm1'].post(f'/inventario/api/traslados/{tid}/recibir', json={'recibido': {str(item): 5}})
    assert r.status_code == 400 and 'otra persona' in r.get_json()['error']
    # Llegaron 4: sin explicación no se acepta
    r = esc['alm2'].post(f'/inventario/api/traslados/{tid}/recibir', json={'recibido': {str(item): 4}})
    assert r.status_code == 400
    r = esc['alm2'].post(f'/inventario/api/traslados/{tid}/recibir',
                         json={'recibido': {str(item): 4}, 'observaciones': 'Caja abierta'})
    assert r.status_code == 200
    assert _stock(esc, 'KCF', 'SMP', 'IPHONE')[0] == 6
    assert _sql("SELECT estado FROM inv_traslados WHERE id=%s", (tid,))[0][0] == 'Recibido con faltante'
    assert _sql("SELECT cantidad FROM inv_movimientos WHERE traslado_id=%s AND motivo='FALTANTE_TRASLADO'", (tid,))[0][0] == 1


def test_ubicar_y_juntar(esc, admin):
    r = admin.get(f"/inventario/api/ubicar?producto_id={esc['IPHONE']}&cantidad=9"
                  f"&empresa_id={esc['AGD']}&almacen_id={esc['SMP']}").get_json()
    assert r['alcanza']
    # Primero AGD en SMP (5), luego AGD en Breña (1), luego KCF en SMP (3: intercompany)
    assert [(p['empresa_id'], p['almacen_id'], p['tomar']) for p in r['plan']] == [
        (esc['AGD'], esc['SMP'], 5), (esc['AGD'], esc['BRE'], 1), (esc['KCF'], esc['SMP'], 3)]
    assert r['plan'][1]['pasos'] == ['traslado'] and r['plan'][2]['pasos'] == ['intercompany']
    j = esc['alm1'].post('/inventario/api/juntar', json={'producto_id': esc['IPHONE'], 'almacen_id': esc['SMP'],
                                                          'encargado': 'Pedro', 'plan': r['plan']})
    assert j.status_code == 200 and len(j.get_json()['numeros']) == 1


def test_intercompany_cambia_de_dueno(esc, admin):
    r = esc['alm1'].post('/inventario/api/intercompany', json={
        'empresa_vende_id': esc['KCF'], 'empresa_compra_id': esc['AGD'], 'almacen_id': esc['SMP'],
        'producto_id': esc['IPHONE'], 'cantidad': 3, 'precio_unitario': 5300})
    assert r.status_code == 200
    assert _stock(esc, 'KCF', 'SMP', 'IPHONE')[0] == 3
    assert _stock(esc, 'AGD', 'SMP', 'IPHONE')[0] == 8
    assert admin.get('/inventario/api/resumen').get_json()['data']['intercompany_sin_factura'] == 1
    grupo = r.get_json()['grupo']
    assert esc['alm1'].post(f'/inventario/api/intercompany/{grupo}/factura', json={'factura': 'F001-77'}).status_code == 200
    assert admin.get('/inventario/api/resumen').get_json()['data']['intercompany_sin_factura'] == 0
    r2 = esc['alm1'].post('/inventario/api/intercompany', json={
        'empresa_vende_id': esc['AGD'], 'empresa_compra_id': esc['KCF'], 'almacen_id': esc['SMP'],
        'producto_id': esc['IPHONE'], 'cantidad': 1, 'factura': 'F002-1'})
    assert r2.get_json()['grupo'] != grupo


def test_perdida_requiere_aprobacion_de_otro(esc, admin, aprobador):
    antes = _stock(esc, 'AGD', 'SMP', 'IPHONE')[0]
    r = _mov(esc['alm1'], esc, 'PERDIDA_ROBO', 'AGD', 'SMP', 'IPHONE', 1)
    assert r.status_code == 400  # sin explicación
    r = _mov(esc['alm1'], esc, 'PERDIDA_ROBO', 'AGD', 'SMP', 'IPHONE', 1, observaciones='No aparece en el estante')
    assert r.status_code == 200 and r.get_json()['pendiente']
    assert _stock(esc, 'AGD', 'SMP', 'IPHONE')[0] == antes
    mid = _sql("SELECT id FROM inv_movimientos WHERE numero=%s", (r.get_json()['numero'],))[0][0]
    assert esc['alm2'].post(f'/inventario/api/movimientos/{mid}/aprobar', json={}).status_code == 403
    assert aprobador.post(f'/inventario/api/movimientos/{mid}/aprobar', json={'aprobar': True}).status_code == 200
    assert _stock(esc, 'AGD', 'SMP', 'IPHONE')[0] == antes - 1
    res = admin.get('/inventario/api/resumen').get_json()['data']
    assert res['valor_perdidas_mes'] > 0


def test_conteo_a_ciegas_y_aprobacion(esc, aprobador):
    # Logística no cuenta
    r = esc['alm1'].post('/inventario/api/conteos', json={'empresa_id': esc['AGD'], 'almacen_id': esc['SMP']})
    assert r.status_code == 403
    r = esc['ctrl'].post('/inventario/api/conteos', json={'empresa_id': esc['AGD'], 'almacen_id': esc['SMP']})
    assert r.status_code == 200
    cid = r.get_json()['id']
    det = esc['ctrl'].get(f'/inventario/api/conteos/{cid}').get_json()
    assert all('stock_sistema' not in i for i in det['items'])  # a ciegas
    sistema = _stock(esc, 'AGD', 'SMP', 'IPHONE')[0]
    item = det['items'][0]['id']
    r = esc['ctrl'].post(f'/inventario/api/conteos/{cid}/guardar',
                         json={'contado': {str(item): sistema - 2}, 'comentarios': {str(item): 'faltan 2'}, 'terminar': True})
    assert r.status_code == 200
    assert esc['ctrl'].post(f'/inventario/api/conteos/{cid}/aprobar', json={}).status_code == 403
    r = aprobador.post(f'/inventario/api/conteos/{cid}/aprobar', json={'accion': 'aprobar'})
    assert r.status_code == 200
    assert _stock(esc, 'AGD', 'SMP', 'IPHONE')[0] == sistema - 2


def test_conteo_sorpresa_elige_productos(esc):
    _mov(esc['alm1'], esc, 'COMPRA', 'KCF', 'SMP', 'GUANTE', 50, costo_unitario=10, documento_numero='GR-9')
    r = esc['ctrl'].post('/inventario/api/conteos', json={'empresa_id': esc['KCF'], 'almacen_id': esc['SMP'], 'tipo': 'Sorpresa'})
    assert r.status_code == 200
    assert _sql("SELECT COUNT(*) FROM inv_conteo_items WHERE conteo_id=%s", (r.get_json()['id'],))[0][0] >= 1


def test_stock_antiguo_debe_ubicarse_primero(esc, admin):
    r = _mov(esc['alm1'], esc, 'COMPRA', 'KCF', 'SMP', 'LENTE', 1, costo_unitario=5, documento_numero='GR-10')
    assert r.status_code == 400 and 'Stock inicial' in r.get_json()['error']
    sin_ubicar = admin.get('/inventario/api/resumen').get_json()['data']['sin_ubicar']
    assert any(s['id'] == esc['LENTE'] for s in sin_ubicar)
    r = _mov(esc['alm1'], esc, 'STOCK_INICIAL', 'KCF', 'SMP', 'LENTE', 7, costo_unitario=5)
    assert r.get_json()['pendiente']
    # Mientras está pendiente, productos.stock conserva el valor antiguo
    assert float(_sql("SELECT stock FROM productos WHERE id=%s", (esc['LENTE'],))[0][0]) == 7
    mid = _sql("SELECT id FROM inv_movimientos WHERE numero=%s", (r.get_json()['numero'],))[0][0]
    assert admin.post(f'/inventario/api/movimientos/{mid}/aprobar', json={}).status_code == 200
    assert _stock(esc, 'KCF', 'SMP', 'LENTE')[0] == 7


def test_editar_producto_no_cambia_stock_de_inventario(esc, admin):
    p = admin.get(f"/productos/api/productos/{esc['GUANTE']}").get_json()
    datos = p.get('data') or p.get('producto') or p
    datos = dict(datos, stock=999, descripcion='GUANTE ANTICORTE')
    r = admin.put(f"/productos/api/productos/{esc['GUANTE']}", json=datos)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert float(_sql("SELECT stock FROM productos WHERE id=%s", (esc['GUANTE'],))[0][0]) == 50


def test_reversa_y_kardex(esc, admin):
    r = _mov(esc['alm1'], esc, 'COMPRA', 'AGD', 'BRE', 'GUANTE', 10, costo_unitario=12, documento_numero='GR-ERR')
    mid = _sql("SELECT id FROM inv_movimientos WHERE numero=%s", (r.get_json()['numero'],))[0][0]
    assert esc['alm1'].post(f'/inventario/api/movimientos/{mid}/revertir', json={'motivo': 'x'}).status_code == 403
    assert admin.post(f'/inventario/api/movimientos/{mid}/revertir', json={'motivo': 'Era de KCF'}).status_code == 200
    assert _stock(esc, 'AGD', 'BRE', 'GUANTE')[0] == 0
    assert admin.post(f'/inventario/api/movimientos/{mid}/revertir', json={'motivo': 'otra vez'}).status_code == 400
    k = admin.get(f"/inventario/api/kardex?producto_id={esc['IPHONE']}&empresa_id={esc['KCF']}&almacen_id={esc['SMP']}").get_json()['data']
    assert k[0]['saldo_cantidad'] == _stock(esc, 'KCF', 'SMP', 'IPHONE')[0]
    csv = admin.get(f"/inventario/api/kardex/exportar?empresa_id={esc['KCF']}").get_data(as_text=True)
    assert 'Tipo operación SUNAT' in csv and ';02;' in csv


def test_recepcion_de_compras_se_ingresa_una_sola_vez(esc, admin):
    _sql("""INSERT INTO recepciones_mercaderia (numero_recepcion, producto, cantidad, unidad, proveedor_nombre,
            orden_compra_numero, estado) VALUES ('REC-T-1', 'INV-002', 20, 'PAR', 'PROV', 'OC-1', 'Aprobada')""", fetch=False)
    pend = admin.get('/inventario/api/recepciones_pendientes').get_json()['data']
    rec = next(r for r in pend if r['numero_recepcion'] == 'REC-T-1')
    assert rec['producto_id_sugerido'] == esc['GUANTE']
    body = dict(recepcion_id=rec['id'], costo_unitario=10, documento_numero='OC-1')
    assert _mov(esc['alm1'], esc, 'COMPRA', 'KCF', 'SMP', 'GUANTE', 20, **body).status_code == 200
    assert _mov(esc['alm1'], esc, 'COMPRA', 'KCF', 'SMP', 'GUANTE', 20, **body).status_code == 400
    # Cambiar el estado en Compras ya no suma stock por su cuenta
    antes = float(_sql("SELECT stock FROM productos WHERE id=%s", (esc['GUANTE'],))[0][0])
    admin.put(f"/compras/api/recepciones/{rec['id']}/toggle", json={'estado': 'Almacenada'})
    assert float(_sql("SELECT stock FROM productos WHERE id=%s", (esc['GUANTE'],))[0][0]) == antes


def test_resumen_alerta_sede_no_declarada(esc, admin):
    d = admin.get('/inventario/api/resumen').get_json()['data']
    assert any(s['empresa'] == 'AGD' and s['sede'] == 'San Martín de Porres' for s in d['sedes_no_declaradas'])
    r = admin.post('/inventario/api/sedes_empresas', json={'filas': [
        {'almacen_id': esc['SMP'], 'empresa_id': esc['AGD'], 'registrado_sunat': True, 'codigo_establecimiento': '0001'}]})
    assert r.status_code == 200
    d = admin.get('/inventario/api/resumen').get_json()['data']
    assert not any(s['empresa'] == 'AGD' and s['sede'] == 'San Martín de Porres' for s in d['sedes_no_declaradas'])
    assert esc['alm1'].post('/inventario/api/sedes_empresas', json={'filas': []}).status_code == 403
