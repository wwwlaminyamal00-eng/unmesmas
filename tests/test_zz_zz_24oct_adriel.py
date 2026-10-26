"""
Mejoras del prompt de Adriel (24/10/2026 18:30): descripción del cliente en el PC, "Cuenta Corriente" en la
cotización, marca "-", OC con adelanto 50%, vendedores sin "Generar" ni "Revisión / Validación" y orden de columnas.
"""
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def test_adelanto_50():
    from routes.compras_flujo import CONDICIONES, es_adelanto, monto_adelanto
    assert 'Adelanto 50%' in CONDICIONES
    assert es_adelanto('Adelanto 50%') and not es_adelanto('Contado')
    assert monto_adelanto('1000.01') == Decimal('500.01') or monto_adelanto('1000.01') == Decimal('500.00')
    assert monto_adelanto(236) == Decimal('118.00')


def test_descripcion_del_cliente_sale_del_pc(monkeypatch):
    import routes.ventas as v
    monkeypatch.setattr(v, 'db_query', lambda *a, **k: [{'items_json': [
        {'codigo': 'p-01', 'descripcion_cliente': 'Polo azul talla M según OC 4500'}]}])
    items = [{'codigo': 'P-01'}, {'codigo': 'P-02'}, {'codigo': 'P-01', 'descripcion_cliente': 'ya escrita'}]
    v._completar_desc_cliente(items, 'PC-0001')
    assert items[0]['descripcion_cliente'] == 'Polo azul talla M según OC 4500'
    assert 'descripcion_cliente' not in items[1]
    assert items[2]['descripcion_cliente'] == 'ya escrita'
    assert v._completar_desc_cliente(items, '') is items


def test_marca_guion_y_cuenta_corriente():
    assert 'value="-"' in (RAIZ / 'templates/nuevo_producto.html').read_text(encoding='utf-8')
    assert 'Cuenta Corriente N°' in (RAIZ / 'routes/ventas.py').read_text(encoding='utf-8')


def test_orden_de_columnas_cotizacion():
    js = (RAIZ / 'static/js/ventas.js').read_text(encoding='utf-8')
    cab = js[js.rindex('<thead>', 0, js.index('<tbody id="quoteProductRows">')):js.index('<tbody id="quoteProductRows">')]
    orden = ['Ítem', 'Código de producto', 'Nombre producto', 'Modelo', 'Marca', 'Unidad', 'Stock', 'Precio', 'Cantidad']
    pos = [cab.index('>' + t) for t in orden]
    assert pos == sorted(pos)
    fila = js[js.index('function renderQuoteProducts'):js.index('function calcQuote')]
    celdas = ['col-item', 'col-code', 'col-model', 'col-brand', 'col-unit', 'col-stock', 'col-price', 'col-qty']
    pos = [fila.index('class="' + c) for c in celdas]
    assert pos == sorted(pos)


def test_vendedor_no_ve_revision(vendedor, aprobador):
    # Aunque escriba la dirección, el vendedor vuelve a Cotizaciones y no ve la pestaña ni el botón Generar
    html = vendedor.get('/ventas?tab=revision').get_data(as_text=True)
    assert 'data-tab="revision"' not in html and 'window.PUEDE_VALIDAR_COT = false' in html
    html = aprobador.get('/ventas?tab=revision').get_data(as_text=True)
    assert 'data-tab="revision"' in html and 'window.PUEDE_VALIDAR_COT = true' in html


def test_oc_a_credito_solo_la_aprueba_erika():
    # Erika 25/10/2026: Hellen aprueba sus propias OC, pero las de crédito solo Erika
    from routes.compras_flujo import es_credito
    assert es_credito('Crédito') and es_credito('Credito 30 dias') and not es_credito('Contado')
    src = (RAIZ / 'routes/compras_flujo.py').read_text(encoding='utf-8')
    assert 'No puedes aprobar una orden que tú misma hiciste' not in src
    assert "es_credito(oc['condicion_pago']) and not es_admin()" in src


def test_cotizacion_no_muestra_cuenta_en_dolares():
    src = (RAIZ / 'routes/ventas.py').read_text(encoding='utf-8')
    assert src.count("if codigo_moneda(cb.get('moneda')) == 'PEN']") == 2


def test_reportes_solo_para_erika(admin, aprobador, vendedor):
    # REGLA DE ORO (Erika 25/10/2026): Reportes solo para ella; ni Hellen ni otro usuario lo ven ni exportan
    assert admin.get('/reportes').status_code == 200
    assert 'data-modulo="reportes"' in admin.get('/index').get_data(as_text=True)
    for c in (aprobador, vendedor):
        assert c.get('/reportes').status_code == 302
        assert c.get('/reportes/api/tablero').status_code == 403
        assert c.get('/reportes/api/reporte/cxc/exportar?formato=xlsx').status_code == 403
        assert 'data-modulo="reportes"' not in c.get('/index').get_data(as_text=True)
    import utils
    assert utils._lista_env('X_NO_EXISTE', 'eri01kcf') == {'eri01kcf'}   # por defecto, solo Erika
