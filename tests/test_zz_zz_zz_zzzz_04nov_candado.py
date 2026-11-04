"""
Candados de Caja chica (Erika, 04/11/2026 noche). Datos de prueba, solo en la base local.
  - Aprobada la rendición, sus gastos no se editan ni se anulan (nadie, tampoco la gerencia).
  - Un error se corrige con "Ajuste": línea nueva con motivo que entra en la siguiente rendición.
  - Los cambios hechos antes de aprobar se ven en la rendición; el saldo aprobado queda como "saldo validado".
"""
import pytest

from tests.test_flujos import sql
from tests.test_permisos_usuarios import base   # noqa: F401  (fixture)
from routes.caja_chica import _ahora

HOY = _ahora().date()


@pytest.fixture(scope='module')
def emp(base, admin):
    eid = str(base['emp']['AGD'])
    # Base local de pruebas: deja libre la semana de hoy (otras pruebas ya aprobaron rendiciones con fecha de hoy)
    sql("UPDATE caja_chica_rendiciones SET desde = desde - 40, hasta = hasta - 40 WHERE empresa_id = %s", (eid,))
    for (rid,) in sql("SELECT id FROM caja_chica_rendiciones WHERE empresa_id = %s AND estado = 'Por aprobar'", (eid,)):
        assert admin.post(f'/caja-chica/api/rendicion/{rid}/aprobar', json={'empresa_id': eid, 'monto': 0}).status_code == 200
    r = admin.post('/caja-chica/api/personas', json={'empresa_id': eid, 'nombre': 'Candado Prueba', 'tipo': 'Trabajador', 'dni': '40000099'})
    assert r.status_code == 200, r.json
    return eid, r.json['id']


def _g(cli, eid, quien, monto, desc):
    r = cli.post('/caja-chica/api/gasto', json={
        'empresa_id': eid, 'fecha': HOY.isoformat(), 'rubro': 'Útiles, impresiones y oficina', 'monto': monto,
        'quien_id': quien, 'descripcion': desc, 'comprobante_tipo': 'Sin comprobante (vale)'})
    assert r.status_code == 200, r.json
    return r.json['id']


def _mov(cli, eid, mid):
    lista = cli.get(f'/caja-chica/api/movimientos?empresa_id={eid}').json['data']['filas']
    return next(m for m in lista if m['id'] == mid)


def _rendir_y_aprobar(cli, eid):
    r = cli.post('/caja-chica/api/rendicion', json={'empresa_id': eid, 'hasta': HOY.isoformat()})
    assert r.status_code == 200, r.json
    rid = sql("SELECT id FROM caja_chica_rendiciones WHERE empresa_id = %s AND estado = 'Por aprobar'", (eid,))[0][0]
    return rid


def test_candado_despues_de_aprobar_y_ajuste(admin, emp):
    eid, quien = emp
    a = _g(admin, eid, quien, '5.00', 'Lapiceros candado')
    b = _g(admin, eid, quien, '20.00', 'Cinta candado')
    # antes de enviar se puede editar, y queda el cambio a la vista de Erika
    m = _mov(admin, eid, b)
    cambio = {'empresa_id': eid, 'fecha': HOY.isoformat(), 'rubro': 'Útiles, impresiones y oficina', 'monto': '25.00',
              'quien_id': quien, 'descripcion': 'Cinta candado', 'comprobante_tipo': 'Sin comprobante (vale)'}
    assert admin.put(f'/caja-chica/api/gasto/{b}', json=cambio).status_code == 200
    assert _mov(admin, eid, b)['editado'] == 1 and m['editado'] == 0
    rid = _rendir_y_aprobar(admin, eid)
    det = admin.get(f'/caja-chica/api/rendicion/{rid}?empresa_id={eid}').json['data']['gastos']
    assert any(g['id'] == b and g['cambios'] and '25' in ' '.join(g['cambios'][0]['cambios']) for g in det)
    r = admin.post(f'/caja-chica/api/rendicion/{rid}/aprobar', json={'empresa_id': eid})
    assert r.status_code == 200, r.json
    res = admin.get(f'/caja-chica/api/resumen?empresa_id={eid}').json['data']
    assert res['validado']['numero'] and res['validado']['saldo'] == res['saldo']
    # aprobado: nadie edita ni anula (tampoco la gerencia)
    m = _mov(admin, eid, a)
    assert m['bloqueado'] and not m['anulable'] and m['ajustable'] and m['aprobado']
    r = admin.put(f'/caja-chica/api/gasto/{a}', json=dict(cambio, monto='6.00', descripcion='Lapiceros candado'))
    assert r.status_code == 400 and 'Ajustar' in r.json['error']
    r = admin.post(f'/caja-chica/api/movimiento/{a}/anular', json={'empresa_id': eid, 'motivo': 'quiero cambiarlo'})
    assert r.status_code == 400 and 'Ajustar' in r.json['error']
    r = admin.post('/caja-chica/api/ingreso', json={'empresa_id': eid, 'tipo': 'Devolución', 'fecha': HOY.isoformat(),
                                                   'monto': '1.00', 'descripcion': 'devolución a fecha cerrada'})
    assert r.status_code == 400 and 'cerrada' in r.json['error']
    # ajuste: motivo obligatorio, 5 → 6 deja un gasto de 1.00; 25 → 20 deja una devolución de 5.00
    assert admin.post(f'/caja-chica/api/movimiento/{a}/ajuste', json={'empresa_id': eid, 'monto_nuevo': '6'}).status_code == 400
    r = admin.post(f'/caja-chica/api/movimiento/{a}/ajuste', json={'empresa_id': eid, 'monto_nuevo': '6.00',
                                                                  'motivo': 'El pasaje fue 6, se escribió 5'})
    assert r.status_code == 200, r.json
    r = admin.post(f'/caja-chica/api/movimiento/{b}/ajuste', json={'empresa_id': eid, 'monto_nuevo': '20.00',
                                                                  'motivo': 'Se infló el monto de la cinta'})
    assert r.status_code == 200, r.json
    r = admin.post(f'/caja-chica/api/movimiento/{a}/ajuste', json={'empresa_id': eid, 'monto_nuevo': '6.00',
                                                                  'motivo': 'otra vez el mismo monto'})
    assert r.status_code == 400 and 'igual' in r.json['error']
    lista = admin.get(f'/caja-chica/api/movimientos?empresa_id={eid}').json['data']['filas']
    aj = [m for m in lista if m['es_ajuste']]
    assert sorted((m['tipo'], m['egreso'] or m['ingreso']) for m in aj[-2:]) == [('Devolución', 5.0), ('Gasto', 1.0)]
    assert all(m['bloqueado'] and m['anulable'] and not m['ajustable'] for m in aj[-2:])
    # los ajustes entran en la siguiente rendición, con el total neto (1.00 − 5.00)
    sql("UPDATE caja_chica_rendiciones SET desde = desde - 40, hasta = hasta - 40 WHERE empresa_id = %s", (eid,))
    r = admin.post('/caja-chica/api/rendicion', json={'empresa_id': eid, 'hasta': HOY.isoformat()})
    assert r.status_code == 200, r.json
    tot = sql("SELECT total_gastado FROM caja_chica_rendiciones WHERE empresa_id = %s AND estado = 'Por aprobar'", (eid,))[0][0]
    assert float(tot) == -4.0
    html = admin.get('/caja-chica/imprimir/rendicion/' + str(sql(
        "SELECT id FROM caja_chica_rendiciones WHERE empresa_id = %s AND estado = 'Por aprobar'", (eid,))[0][0]) + f'?empresa_id={eid}').get_data(as_text=True)
    assert '− 5.00' in html and 'Ajuste del gasto' in html
