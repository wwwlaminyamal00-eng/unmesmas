"""
Pedido de Erika del 20/10/2026 22:54: el sistema es un "policía" que no deja crear documentos duplicados
(guía, factura y orden de compra), validado en el servidor. También: N° en vez de Nr°, cliente antes del RUC,
tarjetas en una fila, avisos "¿Ahora qué?" en Compras y el PV en la OC. Datos inventados, solo en la base local.
"""
import json
from pathlib import Path

from tests.test_inventario import _sql
from tests.test_zz_zz_19oct_noche import _pc

RAIZ = Path(__file__).resolve().parent.parent


def _guia(http, **extra):
    data = {'serie': 'T001', 'destinatario_nombre': 'CLIENTE INDUSTRIAL S.A.C.', 'ruc_destinatario': '20100070970',
            'motivo_traslado': '04', 'estado': 'Borrador',
            'items': [{'codigo': 'PRD-0001', 'producto': 'GUANTE DE NITRILO', 'cantidad': 2}]}
    data.update(extra)
    return http.post('/ventas/api/guias/guardar', json=data)


def _factura(http, **extra):
    data = {'tipo': 'FACTURA', 'serie': 'F001', 'cliente': 'CLIENTE INDUSTRIAL S.A.C.', 'ruc': '20100070970',
            'total': 118, 'subtotal': 100, 'igv': 18, 'condicion': 'Contado', 'estado': 'Borrador',
            'items': [{'codigo': 'PRD-0001', 'descripcion': 'GUANTE DE NITRILO', 'cantidad': 2}]}
    data.update(extra)
    return http.post('/ventas/api/comprobantes/guardar', json=data)


def test_guia_duplicada_por_despacho_y_por_pc(vendedor):
    assert _pc(vendedor, numero='PC-ZZD-G').status_code == 200          # pide 2 guantes
    _sql("INSERT INTO despachos (numero, cliente, ruc, estado, pc_numero) VALUES ('DSP-ZZD-1', 'CLIENTE', '20100070970', 'Pendiente despacho', 'PC-ZZD-G')", fetch=False)
    # Parcial: 1 de 2 se puede
    r = _guia(vendedor, despacho_numero='DSP-ZZD-1', pc_numero='PC-ZZD-G', items=[{'codigo': 'PRD-0001', 'cantidad': 1}])
    assert r.status_code == 200, r.json
    # Otra guía para el mismo despacho: bloqueada y dice cuál existe
    r2 = _guia(vendedor, despacho_numero='DSP-ZZD-1', pc_numero='PC-ZZD-G', items=[{'codigo': 'PRD-0001', 'cantidad': 1}])
    assert r2.status_code == 409 and r2.json['codigo'] == 'duplicado'
    assert f"T001-{r.json['data']['numero']}" in r2.json['error'] and '⛔ ERROR' in r2.json['error']
    # El resto del PV (1) sí se puede; pasarse del PV (ya hay 1, +2 > 2) no
    assert _guia(vendedor, pc_numero='PC-ZZD-G', items=[{'codigo': 'PRD-0001', 'cantidad': 2}]).status_code == 409
    assert _guia(vendedor, pc_numero='PC-ZZD-G', items=[{'codigo': 'PRD-0001', 'cantidad': 1}]).status_code == 200
    # Anulada no cuenta: anulo la del despacho y se puede volver a hacer
    vendedor.delete(f"/ventas/api/guias/{r.json['data']['id']}")
    assert _guia(vendedor, despacho_numero='DSP-ZZD-1', pc_numero='PC-ZZD-G',
                 items=[{'codigo': 'PRD-0001', 'cantidad': 1}]).status_code == 200


def test_factura_duplicada_por_guia_y_por_pc(vendedor):
    assert _pc(vendedor, numero='PC-ZZD-F').status_code == 200          # pide 2 guantes
    f1 = _factura(vendedor, pc='PC-ZZD-F', guia='T001-ZZD-99', items=[{'codigo': 'PRD-0001', 'cantidad': 1}])
    assert f1.status_code == 200, f1.json
    r = _factura(vendedor, guia='T001-ZZD-99', items=[{'codigo': 'PRD-0001', 'cantidad': 1}])
    assert r.status_code == 409 and r.json['codigo'] == 'duplicado' and 'ya fue facturada' in r.json['error']
    # Parcial: el otro guante sí; un tercero no (el PV ya quedó facturado completo)
    assert _factura(vendedor, pc='PC-ZZD-F', items=[{'codigo': 'PRD-0001', 'cantidad': 1}]).status_code == 200
    r = _factura(vendedor, pc='PC-ZZD-F', items=[{'codigo': 'PRD-0001', 'cantidad': 1}])
    assert r.status_code == 409 and 'PC-ZZD-F ya fue facturado' in r.json['error']
    # Sin guía ni PV (factura sin stock, regla de las 18:09) sigue permitida
    assert _factura(vendedor, items=[{'codigo': 'PRD-0001', 'cantidad': 50}]).status_code == 200


def test_oc_duplicada(admin):
    _sql("""INSERT INTO proveedores (razon_social, ruc, direccion, condicion_pago, activo) VALUES
              ('PROVEEDOR UNO ZZD', '20999999101', 'Av. Uno 1', 'Contado', true), ('PROVEEDOR DOS ZZD', '20999999102', 'Av. Dos 2', 'Contado', true)""", fetch=False)
    p1, p2 = [f[0] for f in _sql("SELECT id FROM proveedores WHERE ruc IN ('20999999101', '20999999102') ORDER BY ruc")]
    prod = _sql("SELECT id FROM productos WHERE codigo = 'PRD-0001'")[0][0]
    emp = _sql("SELECT id FROM erp_empresas ORDER BY id LIMIT 1")[0][0]
    sede = _sql("SELECT id FROM almacenes WHERE COALESCE(activo, true) ORDER BY id LIMIT 1")[0][0]
    pc = _sql("""INSERT INTO pedido_compra_pc (numero, cliente, ruc, estado, items_json, fecha, cotizacion_numero)
                 VALUES ('PC-ZZD-OC', 'CLIENTE', '20100070970', 'Pendiente', %s, NOW(), 'COT-ZZD-OC') RETURNING id""",
              (json.dumps([{'codigo': 'PRD-0001', 'producto': 'GUANTE', 'cantidad_pc': 10}]),))[0][0]

    def oc(prov, cant, pedido=None, **extra):
        body = {'empresa_id': emp, 'proveedor_id': prov, 'almacen_entrega_id': sede, 'condicion_pago': 'Contado',
                'modalidad_entrega': 'Proveedor entrega', 'fecha_compromiso': '2026-10-30',
                'items': [{'producto_id': prod, 'cantidad': cant, 'precio_unitario': 5, 'pedido_id': pedido}]}
        if not pedido:
            body['motivo_compra'] = 'Stock estratégico'
        body.update(extra)
        return admin.post('/compras/api/flujo/ordenes', json=body)

    a = oc(p1, 4, pc)
    assert a.status_code == 200, a.json
    # Mismo PV y mismo proveedor: bloqueada y nombra la OC que ya existe
    r = oc(p1, 3, pc)
    assert r.status_code >= 400 and 'Ya existe una Orden de Compra activa para este pedido' in r.json['error']
    assert a.json['numero'] in r.json['error']
    # Mismo PV con otro proveedor: permitido (el resto del pedido)
    assert oc(p2, 3, pc).status_code == 200
    # Para stock: idéntica (mismo proveedor, producto y cantidad) bloqueada; otra cantidad sí
    assert oc(p1, 7).status_code == 200
    r = oc(p1, 7)
    assert r.status_code >= 400 and 'idéntica' in r.json['error']
    assert oc(p1, 8).status_code == 200
    # Anulada no cuenta
    admin.post(f"/compras/api/flujo/ordenes/{a.json['id']}/anular", json={'motivo': 'prueba de duplicado'})
    assert oc(p1, 4, pc).status_code == 200
    # 22/10/2026: la OC impresa ya no muestra el N° PV (el proveedor no ve numeración interna)
    html = admin.get(f"/compras/flujo/ordenes/{a.json['id']}/imprimir", query_string={'hoja': 'borrador'}).get_data(as_text=True)
    assert 'PC-ZZD-OC' not in html and 'Relacionado al PV' not in html and 'Sin PV' not in html


def test_pantallas_ordenadas_y_ayudas_en_compras():
    todo = ''.join(p.read_text(encoding='utf-8-sig') for p in list((RAIZ / 'templates').rglob('*.html')) + list((RAIZ / 'static/js').glob('*.js')))
    assert 'Nr°' not in todo
    vi = (RAIZ / 'templates/ventas/index.html').read_text(encoding='utf-8')
    assert '<th>RUC</th>\r\n                        <th>Cliente</th>' not in vi and '<th>RUC</th>\n                        <th>Cliente</th>' not in vi
    js = (RAIZ / 'static/js/ventas.js').read_text(encoding='utf-8')
    assert '>Generar rótulo</button>' in js and "['falta_stock', 'duplicado'].includes(errorData.codigo)" in js
    base = (RAIZ / 'templates/base.html').read_text(encoding='utf-8')
    assert 'grid-auto-flow:column!important' in base
    cjs = (RAIZ / 'static/js/compras_flujo.js').read_text(encoding='utf-8')
    for t in ('👉 ¿Ahora qué?', "cartelSiguiente($('recOc').value, '✅ ¡Mercadería recibida!'", 'Compra directa a stock (Sin PV)',
              'Relacionado al PV:', "cartelSiguiente($('pagoOc').value"):
        assert t in cjs, t
    fl = (RAIZ / 'templates/compras/flujo.html').read_text(encoding='utf-8')
    assert '<th>N° PV (Pedido de venta)</th><th>N° cotización</th>' in fl


def test_despacho_duplicado_del_mismo_pc(vendedor):
    assert _pc(vendedor, numero='PC-ZZD-D').status_code == 200          # pide 2 guantes
    base = {'pc_numero': 'PC-ZZD-D', 'cliente': 'CLIENTE INDUSTRIAL S.A.C.', 'ruc': '20100070970',
            'items': [{'codigo': 'PRD-0001', 'producto': 'GUANTE DE NITRILO', 'cantidad': 2}]}
    assert vendedor.post('/ventas/api/despachos/guardar', json=base).status_code == 200
    r = vendedor.post('/ventas/api/despachos/guardar', json=base)
    assert r.status_code == 409 and r.json['codigo'] == 'duplicado' and 'PC-ZZD-D ya tiene despacho' in r.json['error']


def test_pedidos_por_comprar_por_defecto_solo_lo_pendiente(admin):
    """21/10/2026: un pedido ya cubierto por una orden de compra no sale por defecto (confundía al comprador)."""
    _sql("""INSERT INTO productos (familia, codigo, descripcion, unidad, costo_unitario, precio_unitario, stock, activo)
            VALUES ('GENERAL', 'ZZD-CUB', 'PRODUCTO SIN STOCK ZZD', 'UND', 0, 10, 0, true)""", fetch=False)
    pc = _sql("""INSERT INTO pedido_compra_pc (numero, cliente, ruc, estado, items_json, fecha)
                 VALUES ('PC-ZZD-CUB', 'CLIENTE', '20100070970', 'Pendiente', %s, NOW()) RETURNING id""",
              (json.dumps([{'codigo': 'ZZD-CUB', 'producto': 'PRODUCTO SIN STOCK ZZD', 'cantidad_pc': 5}]),))[0][0]

    def numeros(q=''):
        return {p['numero']: p for p in admin.get('/compras/api/flujo/pedidos' + q).json['data']}
    assert numeros()['PC-ZZD-CUB']['por_comprar'] == 1          # falta comprar: sale
    prov = _sql("SELECT id FROM proveedores WHERE ruc = '20999999102'")[0][0]
    prod = _sql("SELECT id FROM productos WHERE codigo = 'ZZD-CUB'")[0][0]
    emp = _sql("SELECT id FROM erp_empresas ORDER BY id LIMIT 1")[0][0]
    sede = _sql("SELECT id FROM almacenes WHERE COALESCE(activo, true) ORDER BY id LIMIT 1")[0][0]
    r = admin.post('/compras/api/flujo/ordenes', json={
        'empresa_id': emp, 'proveedor_id': prov, 'almacen_entrega_id': sede, 'condicion_pago': 'Contado',
        'modalidad_entrega': 'Proveedor entrega', 'fecha_compromiso': '2026-10-30',
        'items': [{'producto_id': prod, 'cantidad': 5, 'precio_unitario': 5, 'pedido_id': pc}]})
    assert r.status_code == 200, r.json
    assert 'PC-ZZD-CUB' not in numeros()                          # ya tiene orden: por defecto no sale
    assert numeros('?todos=1')['PC-ZZD-CUB']['items'][0]['comprado'] == 5   # con el check sí, para consultar
    fl = (RAIZ / 'templates/compras/flujo.html').read_text(encoding='utf-8')
    assert 'id="pedTodos" autocomplete="off"' in fl and 'Ver también lo ya cubierto' in fl
    cjs = (RAIZ / 'static/js/compras_flujo.js').read_text(encoding='utf-8')
    assert "if (cubierto && !$('pedTodos').checked) return '';" in cjs
