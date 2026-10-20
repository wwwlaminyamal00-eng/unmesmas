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
    assert "'<span class=\"desp-por\">⏳ Por despachar</span>'" in js and '🚚 Confirmar despacho' in js
    assert "irAPestanaYResaltar('despachar', 'despachoSearch', [nuevoDesp.numero, pc.numero]" in js
    html = (RAIZ / 'templates/ventas/index.html').read_text(encoding='utf-8')
    assert '.desp-hecho{' in html and 'background:#00E676' in html and '.desp-por{' in html
    base = (RAIZ / 'templates/base.html').read_text(encoding='utf-8')
    assert 'Tablas de las pantallas sin scroll lateral' in base
    for rel in ('templates/compras/index.html', 'templates/inventario/index.html', 'static/js/compras_flujo.js'):
        assert '>Producto</th>' not in (RAIZ / rel).read_text(encoding='utf-8'), rel
