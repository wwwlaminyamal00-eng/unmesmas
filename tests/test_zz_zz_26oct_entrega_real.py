"""
Entregas (Erika 26/10/2026): primero la fecha de cita, luego "Despachado" (salió del almacén, verde) y recién con la
fecha real de entrega pasa a "Entregado" (azul fuerte). Si el cliente lo rechaza, queda "Rechazado por el cliente"
con su motivo y se puede volver a despachar. Datos inventados, solo en la base local.
"""
from datetime import date, timedelta
from pathlib import Path

from tests.test_inventario import _sql

RAIZ = Path(__file__).resolve().parent.parent


def _despacho(numero, estado):
    _sql("""INSERT INTO despachos (numero, cliente, ruc, estado, items_json)
            VALUES (%s, 'CLIENTE ZZ', '20100070970', %s, '[]')""", (numero, estado), fetch=False)
    return _sql("SELECT id FROM despachos WHERE numero = %s", (numero,))[0][0]


def _fila(cliente, did):
    return next(d for d in cliente.get('/ventas/api/despachos/listar').json['data'] if d['id'] == did)


def test_entregado_con_fecha_real(vendedor):
    vendedor.get('/ventas/api/despachos/listar')  # crea las columnas nuevas si faltan
    did = _despacho('DSP-ZZR-1', 'Despachado')
    url = f'/ventas/api/despachos/{did}/entrega'
    # Sin fecha no pasa; fecha futura tampoco
    assert vendedor.post(url, json={'accion': 'entregar', 'fecha_entrega': ''}).status_code == 400
    manana = (date.today() + timedelta(days=2)).isoformat()
    assert vendedor.post(url, json={'accion': 'entregar', 'fecha_entrega': manana}).status_code == 400
    ayer = (date.today() - timedelta(days=1)).isoformat()
    r = vendedor.post(url, json={'accion': 'entregar', 'fecha_entrega': ayer})
    assert r.status_code == 200 and r.json['data']['estado'] == 'Entregado'
    f = _fila(vendedor, did)
    assert f['estado'] == 'Entregado' and f['fecha_entrega_real'] == ayer
    # Con el lápiz se quita la fecha y vuelve a "Despachado"
    r = vendedor.post(url, json={'accion': 'entregar', 'fecha_entrega': ''})
    assert r.status_code == 200 and _fila(vendedor, did)['estado'] == 'Despachado'
    assert _fila(vendedor, did)['fecha_entrega_real'] is None


def test_no_se_entrega_lo_que_no_salio(vendedor):
    vendedor.get('/ventas/api/despachos/listar')
    did = _despacho('DSP-ZZR-2', 'Pendiente despacho')
    r = vendedor.post(f'/ventas/api/despachos/{did}/entrega', json={'accion': 'entregar', 'fecha_entrega': date.today().isoformat()})
    assert r.status_code == 409
    # "Entregado" ya no se pone a mano por el cambio de estado: necesita su fecha real
    assert vendedor.put(f'/ventas/api/despachos/{did}/toggle', json={'estado': 'Entregado'}).status_code == 400
    assert vendedor.post('/ventas/api/despachos/999999/entrega', json={'accion': 'entregar'}).status_code == 404


def test_rechazado_por_el_cliente(vendedor):
    vendedor.get('/ventas/api/despachos/listar')
    did = _despacho('DSP-ZZR-3', 'Despachado')
    url = f'/ventas/api/despachos/{did}/entrega'
    assert vendedor.post(url, json={'accion': 'rechazar', 'motivo': '  '}).status_code == 400
    assert vendedor.post(url, json={'accion': 'rechazar', 'motivo': 'x' * 201}).status_code == 400
    r = vendedor.post(url, json={'accion': 'rechazar', 'motivo': ' Caja  dañada '})
    assert r.status_code == 200, r.json
    f = _fila(vendedor, did)
    assert f['estado'] == 'Rechazado por el cliente' and f['motivo_rechazo'] == 'Caja dañada' and f['fecha_rechazo']
    # Ya no está "en la calle": no se puede marcar entregado sin volver a despachar
    assert vendedor.post(url, json={'accion': 'entregar', 'fecha_entrega': date.today().isoformat()}).status_code == 409
    assert vendedor.post(url, json={'accion': 'otra'}).status_code == 409


def test_pantalla_de_entregas_26oct():
    html = (RAIZ / 'templates/ventas/index.html').read_text(encoding='utf-8')
    assert 'Fecha programada (cita)</th>' in html and 'Fecha real de entrega</th>' in html
    assert '<option value="Entregado">Entregado</option>' in html
    assert '<option value="Rechazado por el cliente">Rechazado por el cliente</option>' in html
    assert '.desp-entregado{' in html and 'background:#1D4ED8' in html
    js = (RAIZ / 'static/js/ventas.js').read_text(encoding='utf-8')
    for t in ('function abrirEntregaDespacho', 'function fechasEntregaHTML', 'function entregaRealHTML',
              'Confirmar entrega</button>', "'Volver a despachar'",
              'Primero pon la fecha de cita con el cliente', "`/ventas/api/despachos/${id}/entrega`"):
        assert t in js, t
    # 28/10/2026: el botón "Rechazado por el cliente" ya no sale en Acción (casos raros: se reprograma la cita)
    assert 'Rechazado por el cliente</button>' not in js
