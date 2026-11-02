"""
Erika 02/11/2026: (1) la factura con hora de Perú; (3) el PV al contado guarda N° de operación, banco y CCI con
historial para auditoría. Datos inventados, solo en la base local.
"""
from pathlib import Path

from tests.test_inventario import _sql
from tests.test_zz_zz_19oct_noche import _pc
from utils import fecha_hora_lima

RAIZ = Path(__file__).resolve().parent.parent


def test_fecha_hora_lima_convierte_utc():
    assert fecha_hora_lima('2026-11-02T23:15:00Z') == '2026-11-02T18:15:00'
    assert fecha_hora_lima('2026-11-03T02:10:00.000Z') == '2026-11-02T21:10:00'  # no se pasa al día siguiente
    assert fecha_hora_lima('2026-11-02T18:15:00-05:00') == '2026-11-02T18:15:00'
    assert fecha_hora_lima('2026-11-02 18:15:00') == '2026-11-02 18:15:00'  # ya es hora local
    assert fecha_hora_lima('2026-11-02') == '2026-11-02'
    assert len(fecha_hora_lima()) >= 19
    js = (RAIZ / 'static/js/ventas.js').read_text(encoding='utf-8')
    assert "timeZone:'America/Lima'" in js.replace(' ', '')


def test_pv_contado_guarda_pago_con_historial(vendedor, admin):
    r = _pc(vendedor, numero='', condicion_pago='Contado', pago_num_operacion=' 00123456 ', pago_banco='bcp',
            pago_cci='00219100123456789012')
    assert r.status_code == 200, r.json
    pid = r.json['data']['id']
    fila = _sql("SELECT pago_num_operacion, pago_banco, pago_cci, pago_registrado_por FROM pedido_compra_pc WHERE id = %s", (pid,))[0]
    assert fila[0] == '00123456' and fila[1] == 'BCP' and fila[2] == '00219100123456789012' and fila[3]
    d = admin.get(f'/ventas/api/pedido-compra/{pid}').get_json()['data']
    assert d['pago_num_operacion'] == '00123456' and len(d['pago_historial']) == 1
    assert d['pago_historial'][0]['accion'] == 'Registrado'
    # Guardar igual no duplica; corregir deja historial; vacío no borra
    from routes import pago_contado_pv
    with admin.application.test_request_context():
        assert not pago_contado_pv.guardar(pid, {'condicion_pago': 'Contado', 'pago_num_operacion': '00123456',
                                                 'pago_banco': 'BCP', 'pago_cci': '00219100123456789012'})
        assert pago_contado_pv.guardar(pid, {'condicion_pago': 'Contado', 'pago_num_operacion': '00999999',
                                             'pago_banco': 'BBVA', 'pago_cci': '01100000000000000001'})
        assert not pago_contado_pv.guardar(pid, {'condicion_pago': 'Contado'})
        assert not pago_contado_pv.guardar(pid, {'condicion_pago': 'Crédito 30 días', 'pago_num_operacion': 'X'})
    h = _sql("SELECT accion, num_operacion FROM pv_pago_contado_historial WHERE pedido_id = %s ORDER BY id", (pid,))
    assert h == [('Registrado', '00123456'), ('Corregido', '00999999')]
    assert _sql("SELECT pago_num_operacion FROM pedido_compra_pc WHERE id = %s", (pid,))[0][0] == '00999999'


def test_pantalla_dice_cci_y_muestra_historial():
    modal = (RAIZ / 'templates/ventas/modales/pedido_compra_modal.html').read_text(encoding='utf-8')
    assert 'Cuenta OCCI' not in modal and 'id="pcPagoHistorial"' in modal and '>CCI<' in modal.replace(' ', '')
    js = (RAIZ / 'static/js/ventas.js').read_text(encoding='utf-8')
    assert 'pago_cci:' in js and 'function pintarPagoContadoPV' in js
    assert 'Pago al contado (del PV)' in (RAIZ / 'static/js/finanzas.js').read_text(encoding='utf-8')
