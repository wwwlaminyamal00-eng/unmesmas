"""25/10: Seguimiento comercial con WhatsApp en el teléfono y columna "Cantidad y producto" con buscador."""
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _leer(ruta):
    with open(os.path.join(RAIZ, ruta), encoding='utf-8') as f:
        return f.read()


def test_js_abre_whatsapp_y_muestra_productos():
    js = _leer('static/js/seguimiento.js')
    assert 'https://wa.me/' in js and 'celularWhatsapp' in js
    assert 'Sin teléfono' in js and 'No es celular: sin WhatsApp' in js
    assert '<th>Cantidad y producto</th>' in js and 'filtrarAbiertas' in js
    assert 'id="segBuscar"' in _leer('templates/seguimiento.html')


def test_productos_por_cotizacion(monkeypatch):
    from routes import seguimiento as s
    monkeypatch.setattr(s, 'db_query', lambda q, p=None: [
        {'cotizacion_id': 7, 'cantidad': 10, 'descripcion': 'TAPETE'},
        {'cotizacion_id': 7, 'cantidad': 2.5, 'descripcion': 'GUANTE'}])
    assert s._productos([7]) == {7: [{'cantidad': 10.0, 'descripcion': 'TAPETE'}, {'cantidad': 2.5, 'descripcion': 'GUANTE'}]}
    assert s._productos([]) == {}
