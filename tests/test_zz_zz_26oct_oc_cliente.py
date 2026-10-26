"""26/10/2026: el N° OC del cliente se ve completo bajo el N° PC, en PC y en Entregas."""
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _leer(ruta):
    with open(os.path.join(BASE, ruta), encoding='utf-8') as f:
        return f.read()


def test_pc_y_entregas_usan_el_mismo_rotulo():
    js = _leer('static/js/ventas.js')
    assert 'function ocClienteHTML(v)' in js
    assert '<span>N° OC del cliente</span>' in js
    assert '${sd(r.pc_numero)}${ocClienteHTML(r.oc_cliente)}' in js
    assert "${r.numero || '-'}</b>${ocClienteHTML(r.oc_cliente)}" in js
    assert 'OC cliente: ${esc(r.oc_cliente)}' not in js


def test_entregas_trae_oc_cliente_del_pc():
    py = _leer('routes/ventas.py')
    assert "WHERE p.numero = d.pc_numero ORDER BY p.id DESC LIMIT 1) AS oc_cliente" in py
    assert "'oc_cliente': row.get('oc_cliente') or ''," in py


def test_rotulo_no_se_sale_de_la_celda():
    css = _leer('static/css/compacto.css')
    assert '.oc-cliente-celda{' in css and 'overflow-wrap:anywhere' in css
