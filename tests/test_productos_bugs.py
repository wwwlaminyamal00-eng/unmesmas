"""
Pruebas de los bugs 9, 10 y 11 de Productos:
  - BUG 9: el "Tipo de operación" (Venta / Compra / Inventariable) se guarda y vuelve al reabrir.
  - BUG 10: una marca o categoría escrita a mano se guarda, sale seleccionada al reabrir
            y queda en las tablas marcas / categorias para la próxima vez.
  - BUG 11: al editar un producto también se puede "Agregar stock inicial" (empresa + sede);
            solo se registra si la cantidad es mayor a 0 y no se duplica si ya hay stock ahí.
"""
import re
import psycopg2
import pytest

from tests.conftest import TEST_DB, _login


def _sql(q, params=None):
    conn = psycopg2.connect(TEST_DB)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(q, params)
    filas = cur.fetchall() if cur.description else None
    conn.close()
    return filas


@pytest.fixture(scope='module')
def esc(app):
    _sql("""
        INSERT INTO erp_empresas (codigo, nombre_corto, nombre_comercial, razon_social, ruc, estado,
                                  color_primario, color_secundario, color_pastel)
        SELECT 'KCF', 'KCF', 'KCF', 'KCF S.A.C.', '20111111111', 'activo', '#D6243A', '#1D1A1F', '#FDE8EB'
        WHERE NOT EXISTS (SELECT 1 FROM erp_empresas WHERE codigo = 'KCF');
        INSERT INTO almacenes (codigo, nombre, direccion, activo)
        SELECT 'PRB', 'Sede Pruebas Productos', 'Av. Prueba 1', true
        WHERE NOT EXISTS (SELECT 1 FROM almacenes WHERE codigo = 'PRB');
    """)
    from routes import multiempresa
    multiempresa.empresas(refrescar=True)
    return {
        'KCF': str(_sql("SELECT id FROM erp_empresas WHERE codigo = 'KCF'")[0][0]),
        'SEDE': _sql("SELECT id FROM almacenes WHERE codigo = 'PRB'")[0][0],
        'admin': _login(app, 'admin', 'Admin#2026!'),
        'vendedor': _login(app, 'vendedor', 'Vende#2026!'),
    }


def _nuevo(cliente, **extra):
    body = {'descripcion': 'PRODUCTO BUGS', 'modelo': 'PB-1', 'marca': 'Nike', 'familia': 'Ferretería',
            'unidad': 'NIU', 'transporte': 'auto', 'costo_unitario': 10, 'precio_unitario': 15}
    body.update(extra)
    r = cliente.post('/productos/api/productos', json=body)
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.json['data']['id']


def _api(cliente, pid):
    r = cliente.get(f'/productos/api/productos/{pid}')
    assert r.status_code == 200
    return r.json['data']


def _pagina_editar(cliente, pid):
    r = cliente.get(f'/productos/editar/{pid}')
    assert r.status_code == 200
    return r.get_data(as_text=True)


def _seleccionado(html, valor):
    return re.search(r'<option value="%s"\s+selected>' % re.escape(valor), html) is not None


def _casilla_marcada(html, valor):
    return re.search(r'name="operation" value="%s"\s+checked' % valor, html) is not None


def test_tipo_operacion_marca_y_categoria_personalizadas_vuelven_al_reabrir(esc):
    admin = esc['admin']
    pid = _nuevo(admin, marca='Marca Rara XYZ', familia='Categoría Nueva ZZ', tipo_operacion='compra,inventariable')

    datos = _api(admin, pid)
    assert datos['tipo_operacion'] == 'compra,inventariable'
    assert datos['marca'] == 'Marca Rara XYZ'
    assert datos['categoria'] == 'Categoría Nueva ZZ'

    html = _pagina_editar(admin, pid)
    assert _seleccionado(html, 'Marca Rara XYZ')
    assert _seleccionado(html, 'Categoría Nueva ZZ')
    assert _casilla_marcada(html, 'compra') and _casilla_marcada(html, 'inventariable')
    assert not _casilla_marcada(html, 'venta')

    # Quedan en las tablas maestras (una sola vez) y salen en la lista de un producto nuevo
    assert _sql("SELECT COUNT(*) FROM marcas WHERE nombre = 'Marca Rara XYZ'")[0][0] == 1
    assert _sql("SELECT COUNT(*) FROM categorias WHERE nombre = 'Categoría Nueva ZZ'")[0][0] == 1
    assert _sql("SELECT codigo FROM marcas WHERE nombre = 'Marca Rara XYZ'")[0][0].startswith('MAR-')
    nuevo = admin.get('/productos/nuevo').get_data(as_text=True)
    assert '<option value="Marca Rara XYZ"' in nuevo and '<option value="Categoría Nueva ZZ"' in nuevo
    assert any(m['nombre'] == 'Marca Rara XYZ' for m in admin.get('/maestros/api/marcas/listar').json['data'])

    # Editar como lo hace el formulario: otra marca/categoría escrita a mano y otras casillas
    datos = dict(datos, marca='Otra Marca Propia', familia='Otra Categoría Propia', tipo_operacion='venta')
    r = admin.put(f'/productos/api/productos/{pid}', json=datos)
    assert r.status_code == 200, r.get_data(as_text=True)
    datos = _api(admin, pid)
    assert (datos['marca'], datos['categoria'], datos['tipo_operacion']) == \
        ('Otra Marca Propia', 'Otra Categoría Propia', 'venta')
    html = _pagina_editar(admin, pid)
    assert _seleccionado(html, 'Otra Marca Propia') and _seleccionado(html, 'Otra Categoría Propia')
    assert _casilla_marcada(html, 'venta') and not _casilla_marcada(html, 'compra')
    assert _sql("SELECT COUNT(*) FROM marcas WHERE nombre = 'Otra Marca Propia'")[0][0] == 1

    # Ninguna casilla marcada se guarda como vacío; si otra pantalla no envía el dato, se conserva
    r = admin.put(f'/productos/api/productos/{pid}', json=dict(datos, tipo_operacion=''))
    assert r.status_code == 200 and _api(admin, pid)['tipo_operacion'] == ''
    sin_dato = {k: v for k, v in datos.items() if k != 'tipo_operacion'}
    admin.put(f'/productos/api/productos/{pid}', json=dict(sin_dato, operation=['compra', 'venta']))
    assert _api(admin, pid)['tipo_operacion'] == 'venta,compra'
    admin.put(f'/productos/api/productos/{pid}', json=sin_dato)
    assert _api(admin, pid)['tipo_operacion'] == 'venta,compra'

    # La marca ya existente (en otra escritura) no se duplica
    _nuevo(admin, marca='marca rara xyz')
    assert _sql("SELECT COUNT(*) FROM marcas WHERE LOWER(nombre) = 'marca rara xyz'")[0][0] == 1


def test_producto_nuevo_sin_tipo_operacion_queda_como_venta(esc):
    pid = _nuevo(esc['admin'])
    assert _api(esc['admin'], pid)['tipo_operacion'] == 'venta'


def test_editar_producto_agrega_stock_inicial(esc):
    admin = esc['admin']
    pid = _nuevo(admin, descripcion='PRODUCTO STOCK AL EDITAR')
    html = _pagina_editar(admin, pid)
    assert 'Agregar stock inicial' in html and 'name="stock_inicial_cantidad"' in html

    datos = _api(admin, pid)
    base = dict(datos, familia=datos['categoria'])

    # Sin cantidad (o 0): no crea movimientos
    for cantidad in ('', 0, None):
        r = admin.put(f'/productos/api/productos/{pid}', json=dict(
            base, stock_inicial_cantidad=cantidad, stock_inicial_empresa=esc['KCF'], stock_inicial_almacen=esc['SEDE']))
        assert r.status_code == 200, r.get_data(as_text=True)
    assert _sql("SELECT COUNT(*) FROM inv_movimientos WHERE producto_id = %s", (pid,))[0][0] == 0

    # Con cantidad: queda en Inventario con su empresa y sede
    r = admin.put(f'/productos/api/productos/{pid}', json=dict(
        base, stock_inicial_cantidad=7, stock_inicial_empresa=esc['KCF'], stock_inicial_almacen=esc['SEDE']))
    assert r.status_code == 200, r.get_data(as_text=True)
    assert 'Stock inicial registrado' in r.json['message']
    fila = _sql("SELECT cantidad FROM inv_stock WHERE producto_id = %s AND empresa_id::text = %s AND almacen_id = %s",
                (pid, esc['KCF'], esc['SEDE']))
    assert fila and float(fila[0][0]) == 7
    movs = _sql("SELECT motivo, cantidad, estado FROM inv_movimientos WHERE producto_id = %s", (pid,))
    assert len(movs) == 1 and movs[0][0] == 'STOCK_INICIAL' and float(movs[0][1]) == 7
    assert float(_sql("SELECT stock FROM productos WHERE id = %s", (pid,))[0][0]) == 7

    # La página de edición avisa que ya tiene stock ahí
    html = _pagina_editar(admin, pid)
    assert 'Ya tiene stock en' in html

    # No se duplica: si ya hay stock en esa empresa + sede, se rechaza y no cambia nada
    r = admin.put(f'/productos/api/productos/{pid}', json=dict(
        base, descripcion='NO DEBE GUARDARSE', stock_inicial_cantidad=5,
        stock_inicial_empresa=esc['KCF'], stock_inicial_almacen=esc['SEDE']))
    assert r.status_code == 400 and 'Inventario' in r.json['error']
    assert _sql("SELECT COUNT(*) FROM inv_movimientos WHERE producto_id = %s", (pid,))[0][0] == 1
    assert _sql("SELECT descripcion FROM productos WHERE id = %s", (pid,))[0][0] == 'PRODUCTO STOCK AL EDITAR'

    # Sin sede: error claro y nada a medias
    r = admin.put(f'/productos/api/productos/{pid}', json=dict(
        base, descripcion='TAMPOCO', stock_inicial_cantidad=2, stock_inicial_empresa=esc['KCF']))
    assert r.status_code == 400
    assert _sql("SELECT descripcion FROM productos WHERE id = %s", (pid,))[0][0] == 'PRODUCTO STOCK AL EDITAR'


def test_editar_stock_inicial_de_quien_no_aprueba_queda_pendiente(esc):
    vend = esc['vendedor']
    pid = _nuevo(esc['admin'], descripcion='PRODUCTO STOCK PENDIENTE')
    datos = _api(vend, pid)
    cuerpo = dict(datos, familia=datos['categoria'], stock_inicial_cantidad=4,
                  stock_inicial_empresa=esc['KCF'], stock_inicial_almacen=esc['SEDE'])
    r = vend.put(f'/productos/api/productos/{pid}', json=cuerpo)
    assert r.status_code == 200 and 'pendiente' in r.json['message']
    assert _sql("SELECT estado FROM inv_movimientos WHERE producto_id = %s", (pid,))[0][0] == 'Pendiente'
    assert not _sql("SELECT 1 FROM inv_stock WHERE producto_id = %s AND cantidad > 0", (pid,))
    # Un segundo intento mientras espera aprobación no crea otro movimiento
    r = vend.put(f'/productos/api/productos/{pid}', json=cuerpo)
    assert r.status_code == 400 and 'aprobación' in r.json['error']
    assert _sql("SELECT COUNT(*) FROM inv_movimientos WHERE producto_id = %s", (pid,))[0][0] == 1


def test_stock_en_productos_es_el_total_del_grupo(app, esc):
    """BUG 8: Productos muestra siempre el stock de todo el grupo (todas las empresas y sedes),
    con el detalle por empresa y sin ceros de más (25, no 25.0000)."""
    from routes import multiempresa
    _sql("""
        INSERT INTO erp_empresas (codigo, nombre_corto, nombre_comercial, razon_social, ruc, estado,
                                  color_primario, color_secundario, color_pastel)
        SELECT 'AGD', 'AGD', 'AGD', 'AGD S.A.C.', '20222222222', 'activo', '#1D4ED8', '#1D1A1F', '#DBEAFE'
        WHERE NOT EXISTS (SELECT 1 FROM erp_empresas WHERE codigo = 'AGD');
    """)
    multiempresa.empresas(refrescar=True)
    agd = str(_sql("SELECT id FROM erp_empresas WHERE codigo = 'AGD'")[0][0])
    admin = _login(app, 'admin', 'Admin#2026!')
    pid = _nuevo(admin, descripcion='PRODUCTO STOCK GRUPO', modelo='SG-1')
    _sql("""INSERT INTO inv_stock (empresa_id, almacen_id, producto_id, cantidad) VALUES
            (%s, %s, %s, 25), (%s, %s, %s, 0)""", (esc['KCF'], esc['SEDE'], pid, agd, esc['SEDE'], pid))

    def fila(cliente, empresa):
        assert cliente.post('/api/empresa_activa', json={'codigo': empresa}).status_code == 200
        lista = cliente.get('/productos/api/productos?q=PRODUCTO STOCK GRUPO').json['data']
        return [p for p in lista if p['id'] == pid][0]

    # Con AGD arriba: igual se ve el total del grupo (25), y aparte lo de AGD (0)
    p = fila(admin, 'AGD')
    assert p['stock'] == 25 and isinstance(p['stock'], int)
    assert p['stock_empresa'] == 0
    assert p['stock_detalle'] == 'AGD 0 · KCF 25'
    p = fila(admin, 'KCF')
    assert p['stock'] == 25 and p['stock_empresa'] == 25
    p = fila(admin, multiempresa.TODAS)
    assert p['stock'] == 25 and p['stock_empresa'] is None
    # El detalle de un producto y la búsqueda dan lo mismo
    assert _api(admin, pid)['stock'] == 25
    assert [x for x in admin.get('/productos/api/productos/buscar?q=STOCK GRUPO').json['data'] if x['id'] == pid][0]['stock'] == 25

    # Decimales: se muestran sin ceros de más
    _sql("UPDATE inv_stock SET cantidad = 2.5 WHERE producto_id = %s AND empresa_id::text = %s", (pid, agd))
    p = fila(admin, 'KCF')
    assert p['stock'] == 27.5 and p['stock_detalle'] == 'AGD 2.5 · KCF 25'

    # Producto sin filas en Inventario: usa productos.stock
    pid2 = _nuevo(admin, descripcion='PRODUCTO STOCK GRUPO ANTIGUO', modelo='SG-2')
    _sql("UPDATE productos SET stock = 3 WHERE id = %s", (pid2,))
    lista = admin.get('/productos/api/productos?q=PRODUCTO STOCK GRUPO ANTIGUO').json['data']
    p2 = [x for x in lista if x['id'] == pid2][0]
    assert p2['stock'] == 3 and p2['stock_detalle'] is None
