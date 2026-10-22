"""
Pedido de Erika del 20/10/2026 (tarde, "Macro-actualización"): la condición de pago de la factura no cargaba sola.
Faltaban dos caminos: "Crear factura" desde la cotización y la factura hecha a mano (elegir cotización o escribir el
RUC). Ahí quedaba "Contado". Ahora empieza vacía, se llena del PC (o del cliente) y no se guarda vacía.
Datos inventados, solo en la base local de pruebas.
"""
from pathlib import Path

from tests.test_inventario import _sql
from tests.test_zz_zz_19oct_noche import _pc

RAIZ = Path(__file__).resolve().parent.parent


def test_factura_desde_cotizacion_toma_la_condicion_de_su_pc(vendedor):
    assert _pc(vendedor, numero='PC-ZZT-COT', cotizacion_numero='COT-ZZT-1', condicion_pago='Crédito 60 días').status_code == 200
    if not _sql("SELECT 1 FROM pedido_compra_pc WHERE numero = 'PC-ZZT-COT' AND cotizacion_numero = 'COT-ZZT-1'"):
        _sql("UPDATE pedido_compra_pc SET cotizacion_numero = 'COT-ZZT-1' WHERE numero = 'PC-ZZT-COT'", fetch=False)
    d = vendedor.get('/ventas/api/comprobantes/condicion-origen?cotizacion=COT-ZZT-1&ruc=20100070970').json['data']
    assert d['condicion'] == 'Crédito 60 días' and d['pc'] == 'PC-ZZT-COT'
    r = vendedor.post('/ventas/api/comprobantes/guardar', json={
        'tipo': 'FACTURA', 'serie': 'F001', 'cliente': 'CLIENTE INDUSTRIAL S.A.C.', 'ruc': '20100070970',
        'total': 118, 'subtotal': 100, 'igv': 18, 'condicion': '', 'cotizacion': 'COT-ZZT-1',
        'estado': 'Borrador', 'items': []})
    assert r.status_code == 200, r.json
    fila = _sql("SELECT condicion_pago, dias_credito, es_credito FROM comprobantes WHERE id = %s", (r.json['data']['id'],))[0]
    assert fila == ('Crédito 60 días', 60, True)


def test_pantalla_de_factura_llena_la_condicion_en_todos_los_caminos():
    js = (RAIZ / 'static/js/ventas.js').read_text(encoding='utf-8')
    # Factura nueva: empieza vacía (antes "Contado" sin avisar) y no se guarda vacía
    assert '— Se llena sola: elige PC, guía, cotización o RUC —' in js
    assert '⚠️ Falta la condición de pago' in js and 'await aplicarCondicionFactura(true)' in js
    # Desde la cotización, al elegir la cotización y al escribir el RUC
    assert "'cargarProductosComprobanteDesdeCotizacion'].forEach" in js
    ini = js.index('async function openComprobanteModalWithData')
    assert 'setTimeout(aplicarCondicionFactura, 50)' in js[ini:js.index('function closeComprobanteModal')]
    assert "id === 'compRuc'" in js


# ---------------------------------------------------------------- Pedido de las 17:19 y 17:24
def test_pc_conforme_sin_validar_transporte(vendedor):
    from tests.test_zz_zz_19oct_noche import _pc
    r = _pc(vendedor, numero='PC-ZZT-TRA', valida_transporte=False)
    assert r.status_code == 200, r.json
    assert _sql("SELECT estado FROM pedido_compra_pc WHERE numero = 'PC-ZZT-TRA'")[0][0] == 'PC conforme'
    html = (RAIZ / 'templates/ventas/modales/pedido_compra_modal.html').read_text(encoding='utf-8')
    bloque = html[html.index('4. Validación comercial'):html.index('<!-- FOOTER -->')]
    assert 'id="vTransporte"' not in bloque and 'Nombre producto' in bloque and 'Lugar entrega' in bloque


def test_nombres_de_columnas_y_entregas_en_colores():
    js = (RAIZ / 'static/js/ventas.js').read_text(encoding='utf-8')
    assert '<th>Producto</th>' not in js and '<th>Lugar de Entrega</th>' not in js
    assert "'<span class=\"desp-por\">⏳ Por despachar</span>'" in js and '>Confirmar despacho</button>' in js
    assert "irAPestanaYResaltar('despachar', 'despachoSearch', [nuevoDesp.numero, pc.numero]" in js
    html = (RAIZ / 'templates/ventas/index.html').read_text(encoding='utf-8')
    assert '.desp-hecho{' in html and 'background:#00E676' in html and '.desp-por{' in html
    base = (RAIZ / 'templates/base.html').read_text(encoding='utf-8')
    assert 'Tablas de las pantallas sin scroll lateral' in base
    for rel in ('templates/compras/index.html', 'templates/inventario/index.html', 'static/js/compras_flujo.js'):
        assert '>Producto</th>' not in (RAIZ / rel).read_text(encoding='utf-8'), rel


# ---------------------------------------------------------------- Entregas (18:09)
def test_guia_de_venta_sin_stock_no_se_crea_pero_la_factura_si(vendedor):
    base = {'serie': 'T001', 'destinatario_nombre': 'CLIENTE', 'ruc_destinatario': '20100070970', 'motivo_traslado': 'VENTA',
            'items': [{'codigo': 'PRD-0001', 'producto': 'GUANTE', 'cantidad': 999999}], 'estado': 'Borrador',
            'documento_asociado': 'COT-ZZT-SIN'}
    r = vendedor.post('/ventas/api/guias/guardar', json=base)
    assert r.status_code == 409 and r.json['codigo'] == 'falta_stock' and r.json['faltan'][0]['pide'] == 999999
    assert 'La factura sí se puede hacer sin stock' in r.json['error']
    # La factura del mismo pedido sí se guarda sin stock
    f = vendedor.post('/ventas/api/comprobantes/guardar', json={
        'tipo': 'FACTURA', 'serie': 'F001', 'cliente': 'CLIENTE INDUSTRIAL S.A.C.', 'ruc': '20100070970', 'total': 118,
        'subtotal': 100, 'igv': 18, 'condicion': 'Contado', 'cotizacion': 'COT-ZZT-SIN', 'estado': 'Borrador',
        'items': [{'codigo': 'PRD-0001', 'cantidad': 999999}]})
    assert f.status_code == 200, f.json
    # Si su despacho ya salió (stock ya descontado), la guía sí se crea
    _sql("INSERT INTO despachos (numero, cliente, ruc, estado, cotizacion_numero) VALUES ('DSP-ZZT-OK', 'CLIENTE', '20100070970', 'Despachado', 'COT-ZZT-SIN')", fetch=False)
    assert vendedor.post('/ventas/api/guias/guardar', json=base).status_code == 200


def test_fecha_de_cita_del_despacho(vendedor):
    _sql("INSERT INTO despachos (numero, cliente, ruc, estado) VALUES ('DSP-ZZT-CITA', 'CLIENTE', '20100070970', 'Pendiente despacho')", fetch=False)
    did = _sql("SELECT id FROM despachos WHERE numero = 'DSP-ZZT-CITA'")[0][0]
    r = vendedor.post(f'/ventas/api/despachos/{did}/cita', json={'fecha_cita': '2026-10-22T10:30'})
    assert r.status_code == 200, r.json
    fila = next(d for d in vendedor.get('/ventas/api/despachos/listar').json['data'] if d['id'] == did)
    # 22/10/2026: la cita es solo fecha; si llega con hora (dato antiguo) la hora se ignora
    assert fila['fecha_cita'] == '2026-10-22'
    assert vendedor.post(f'/ventas/api/despachos/{did}/cita', json={'fecha_cita': '2026-10-23'}).json['data']['fecha_cita'] == '2026-10-23'
    assert vendedor.post(f'/ventas/api/despachos/{did}/cita', json={'fecha_cita': 'mañana'}).status_code == 400
    assert vendedor.post(f'/ventas/api/despachos/{did}/cita', json={'fecha_cita': ''}).status_code == 200
    assert _sql("SELECT fecha_cita FROM despachos WHERE id = %s", (did,))[0][0] is None


def test_pantalla_de_entregas_18h():
    js = (RAIZ / 'static/js/ventas.js').read_text(encoding='utf-8')
    for t in ('ent-pendiente', 'ent-despachado', 'function estadoCompraHTML', '🛒 Pendiente de compra', '>Generar compra</button>',
              "'/compras?tab=pedidos&pc='", '>Generar factura</button>', 'function ponerCitaDespacho', 'N° guía / N° factura' if False else 'guiaFacturaDespachoHTML'):
        assert t in js, t
    html = (RAIZ / 'templates/ventas/index.html').read_text(encoding='utf-8')
    tabla = html[html.index('<div id="despachar"'):]
    tabla = tabla[:tabla.index('</thead>')]
    orden = [tabla.index(f'<th>{t}</th>') for t in ('N° PC', 'N° cotización', 'Cliente', 'N° guía / N° factura', 'Lugar entrega',
                                                   'Estado compra', 'Fecha de cita', 'Acción')]
    assert orden == sorted(orden) and '<th>Destino</th>' not in tabla
    cjs = (RAIZ / 'static/js/compras_flujo.js').read_text(encoding='utf-8')
    assert "qs.get('pc')" in cjs and 'async function abrirCompraDePedido' in cjs
