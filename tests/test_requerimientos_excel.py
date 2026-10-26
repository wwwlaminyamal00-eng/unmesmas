"""
Pruebas de los 5 requerimientos obligatorios del Excel de pendientes (14/10/2026).
  1. Despacho del PV destacado (letras negras, fondo azulito)   -> el PV informa el estado de su despacho
  2. Rechazo de Hellen = "Rechazada"                             -> ver tests/test_flujos.py::test_rechazo_requiere_motivo
  3. Orden de botones en Cotizaciones                            -> ver static/js/ventas.js (showCotizacionMenu)
  4. "Pendiente por compra" / "Pendiente por recojo"              -> /api/abastecimiento/*
  5. "Crear factura" desde Guías de Remisión                      -> ver static/js/ventas.js (crearFacturaDesdeGuia)
"""
import json
import pytest

from tests.test_inventario import _sql


@pytest.fixture(scope='module')
def ab(app):
    _sql("""
        INSERT INTO erp_empresas (codigo, nombre_corto, nombre_comercial, razon_social, ruc, estado, color_primario, color_secundario, color_pastel)
        SELECT 'KCF', 'KCF', 'KCF', 'KCF S.A.C.', '20111111111', 'activo', '#D6243A', '#1D1A1F', '#FDE8EB' WHERE NOT EXISTS (SELECT 1 FROM erp_empresas WHERE codigo='KCF');
        INSERT INTO almacenes (codigo, nombre, direccion, activo)
        SELECT 'SMP', 'San Martín de Porres', 'Av. Perú 123, SMP', true WHERE NOT EXISTS (SELECT 1 FROM almacenes WHERE codigo='SMP');
        INSERT INTO productos (familia, codigo, descripcion, marca, unidad, costo_unitario, precio_unitario, stock, activo) VALUES
            ('GENERAL', 'ABA-001', 'ZAPATO DE SEGURIDAD T42', 'CAT', 'PAR', 80, 120, 0, true),
            ('GENERAL', 'ABA-002', 'CHALECO REFLECTIVO', 'GENERICO', 'UND', 8, 15, 0, true);
    """, fetch=False)
    prod = dict(_sql("SELECT codigo, id FROM productos WHERE codigo LIKE 'ABA-%'"))
    items = [{'codigo': 'ABA-001', 'producto': 'ZAPATO DE SEGURIDAD T42', 'cantidad_pc': 3, 'precio_pc': 120}]
    pc = _sql("""INSERT INTO pedido_compra_pc (numero, cliente, ruc, estado, items_json, fecha)
                 VALUES ('PC-ABAST-0001', 'MINERA DEL SUR S.A.C.', '20777777777', 'PC conforme', %s, NOW()) RETURNING id""",
              (json.dumps(items),))[0][0]
    desp = _sql("""INSERT INTO despachos (numero, cliente, ruc, pc_id, pc_numero, estado)
                   VALUES ('DES-ABAST-1', 'MINERA DEL SUR S.A.C.', '20777777777', %s, 'PC-ABAST-0001', 'Pendiente despacho')
                   RETURNING id""", (pc,))[0][0]
    emp = _sql("SELECT id FROM erp_empresas WHERE codigo = 'KCF'")[0][0]
    sede = _sql("SELECT id FROM almacenes WHERE codigo = 'SMP'")[0][0]
    return {'pc': pc, 'desp': desp, 'zap': prod['ABA-001'], 'cha': prod['ABA-002'], 'emp': emp, 'sede': sede}


def _estado_pc(cliente, ab):
    r = cliente.get('/api/abastecimiento/pc')
    assert r.status_code == 200, r.get_json()
    return r.get_json()['data'][str(ab['pc'])]['estado']


def test_requiere_sesion(anonimo):
    assert anonimo.get('/api/abastecimiento/pc').status_code == 401


def test_sin_stock_ni_compra_es_pendiente_por_compra(ab, vendedor):
    assert _estado_pc(vendedor, ab) == 'Pendiente por compra'
    d = vendedor.get('/api/abastecimiento/despachos').get_json()['data'][str(ab['desp'])]
    assert d['estado'] == 'Pendiente por compra' and d['faltan'] == 1
    prods = vendedor.get('/api/abastecimiento/productos').get_json()['data']
    assert prods[str(ab['zap'])]['estado'] == 'Pendiente por compra'
    # Nadie pidió el chaleco: es bajo pedido, no se marca como "por comprar"
    assert prods[str(ab['cha'])]['estado'] == 'Sin stock'


def test_comprado_y_lo_recogemos_es_pendiente_por_recojo(ab, vendedor):
    oc = _sql("""INSERT INTO ordenes_compra (numero_orden, estado, modalidad_entrega)
                 VALUES ('OC-ABAST-1', 'Aprobada', 'Nosotros recogemos') RETURNING id""")[0][0]
    _sql("""INSERT INTO ordenes_compra_items (orden_compra_id, producto, producto_id, cantidad, pedido_id)
            VALUES (%s, 'ZAPATO DE SEGURIDAD T42', %s, 3, %s)""", (oc, ab['zap'], ab['pc']), fetch=False)
    assert _estado_pc(vendedor, ab) == 'Pendiente por recojo'
    # si el proveedor lo trae a la sede, ya no hay que ir a recoger
    _sql("UPDATE ordenes_compra SET modalidad_entrega = 'Proveedor entrega' WHERE id = %s", (oc,), fetch=False)
    assert _estado_pc(vendedor, ab) == 'Por llegar'
    # 22/10/2026 (Erika): una OC ya generada, aunque esté por aprobar o en borrador, cuenta como "comprado, por llegar"
    _sql("UPDATE ordenes_compra SET estado = 'Por aprobar' WHERE id = %s", (oc,), fetch=False)
    assert _estado_pc(vendedor, ab) == 'Por llegar'
    assert 'OC-ABAST-1' in vendedor.get('/api/abastecimiento/pc').get_json()['data'][str(ab['pc'])]['ocs']
    _sql("UPDATE ordenes_compra SET estado = 'Anulada' WHERE id = %s", (oc,), fetch=False)
    assert _estado_pc(vendedor, ab) == 'Pendiente por compra'
    _sql("UPDATE ordenes_compra SET estado = 'Anulada' WHERE id = %s", (oc,), fetch=False)


def test_con_stock_libre_ya_no_esta_pendiente(ab, vendedor):
    _sql("""INSERT INTO inv_stock (empresa_id, almacen_id, producto_id, cantidad, costo_promedio, valor)
            VALUES (%s, %s, %s, 3, 80, 240)""", (ab['emp'], ab['sede'], ab['zap']), fetch=False)
    assert _estado_pc(vendedor, ab) == 'Con stock'
    assert str(ab['desp']) not in vendedor.get('/api/abastecimiento/despachos').get_json()['data'] or \
        vendedor.get('/api/abastecimiento/despachos').get_json()['data'][str(ab['desp'])]['estado'] == 'Con stock'
    _sql("DELETE FROM inv_stock WHERE producto_id = %s", (ab['zap'],), fetch=False)


def test_pc_informa_estado_de_su_despacho(ab, vendedor):
    """Requerimiento 1: la lista de PV sabe si su despacho ya salió, para pintarlo azulito."""
    pcs = vendedor.get('/ventas/api/pedido-compra/listar').get_json()
    lista = pcs.get('data', pcs) if isinstance(pcs, dict) else pcs
    fila = next(p for p in lista if p['id'] == ab['pc'])
    assert fila['despacho_estado'] == 'Pendiente despacho'
    _sql("UPDATE despachos SET estado = 'Despachado' WHERE id = %s", (ab['desp'],), fetch=False)
    pcs = vendedor.get('/ventas/api/pedido-compra/listar').get_json()
    lista = pcs.get('data', pcs) if isinstance(pcs, dict) else pcs
    assert next(p for p in lista if p['id'] == ab['pc'])['despacho_estado'] == 'Despachado'


def test_vista_de_ventas_tiene_los_cambios_del_excel(vendedor):
    js = vendedor.get('/static/js/ventas.js').get_data(as_text=True)
    # 3. Orden exacto en el menú de la cotización: Despacho, Guía, Factura en KCF
    menu = js[js.rindex('function showCotizacionMenu'):]
    menu = menu[:menu.index('createMenuWithClose')]
    pos = [menu.index("'despacho'"), menu.index("'guia'"), menu.index("'factura'")]
    assert pos == sorted(pos) and 'Crear factura en KCF' in menu
    # 5. Guías de remisión: "Crear factura" va DENTRO del menú ⋮ (pedido de Erika del 15/10), no afuera
    assert 'crearFacturaDesdeGuia' not in js[js.index('function renderGuias'):js.index('function renderComprobantes')]
    menu_guia = js[js.index('function showGuiaMenu'):]
    assert 'crearFacturaDesdeGuia' in menu_guia[:menu_guia.index('createMenuWithClose') if 'createMenuWithClose' in menu_guia else 4000]
    # 1. Despacho destacado en negro sobre azulito
    css = vendedor.get('/static/css/ventas.css').get_data(as_text=True)
    assert '.fila-despachada' in css
