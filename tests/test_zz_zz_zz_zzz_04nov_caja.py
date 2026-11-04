"""
Mejoras de Caja chica (Erika, 04/11/2026). Personas y montos de prueba, solo en la base local.
  - Hora del gasto; descripción en lista y "de dónde a dónde" aparte; observación más larga.
  - Rubros nuevos: "Flete y transporte de mercadería" y "Movilidad operativa del personal" (los nombres anteriores se
    aceptan y se muestran con el nombre nuevo sin tocar la base).
  - Personas en orden alfabético y con mayúscula inicial.
  - Planilla de movilidad numerada por empresa: al emitirla sus pasajes ya no se editan; la gerencia la anula.
"""
import pytest

from tests.test_flujos import sql
from tests.test_permisos_usuarios import base   # noqa: F401  (fixture)
from routes.caja_chica import _ahora

HOY = _ahora().date()


@pytest.fixture(scope='module')
def agd(base):
    return str(base['emp']['AGD'])


@pytest.fixture(scope='module')
def gente4(admin, agd):
    ids = {}
    for nombre, dni in (('MILAGROS SALAZAR', '70000011'), ('adriana villalobos', '70000012'), ('Sebastián Díaz', '70000013')):
        r = admin.post('/caja-chica/api/personas', json={'empresa_id': agd, 'nombre': nombre, 'tipo': 'Practicante', 'dni': dni})
        assert r.status_code == 200, r.json
        ids[nombre.split()[0].lower()] = r.json['id']
    return ids


def _g(cli, agd, quien, **kw):
    d = {'empresa_id': agd, 'fecha': HOY.isoformat(), 'hora': '00:15', 'rubro': 'Movilidad operativa del personal',
         'monto': '3.50', 'quien_id': quien, 'descripcion': 'Entrega a cliente', 'detalle': 'Oficina Breña → Komatsu Lurín',
         'referencia': 'PV-AGD-000001', 'comprobante_tipo': 'Planilla de movilidad'}
    d.update(kw)
    return cli.post('/caja-chica/api/gasto', json=d)


def _movs(cli, agd):
    return cli.get(f'/caja-chica/api/movimientos?empresa_id={agd}').json['data']['filas']


def test_personas_en_orden_y_con_mayuscula(admin, agd, gente4):
    nombres = [p['nombre'] for p in admin.get(f'/caja-chica/api/personas?empresa_id={agd}').json['data']]
    assert nombres.index('Adriana Villalobos') < nombres.index('Milagros Salazar') < nombres.index('Sebastián Díaz')
    html = admin.get('/caja-chica').get_data(as_text=True)
    assert 'Recojo de productos de proveedores' in html and 'Movilidad operativa del personal' in html
    assert 'Movilidad del personal (pasajes)' not in html and 'Taxi' not in html


def test_hora_descripcion_y_detalle(admin, agd, gente4):
    r = _g(admin, agd, gente4['milagros'], detalle='')
    assert r.status_code == 400 and 'de dónde a dónde' in r.json['error']
    r = _g(admin, agd, gente4['milagros'], descripcion='Otro (escribir)')
    assert r.status_code == 400 and 'escríbela' in r.json['error']
    r = _g(admin, agd, gente4['milagros'], hora='25:00')
    assert r.status_code == 400 and 'hora' in r.json['error']
    obs = 'Observación larga. ' * 40
    r = _g(admin, agd, gente4['milagros'], observacion=obs)
    assert r.status_code == 200, r.json
    m = next(x for x in _movs(admin, agd) if x['id'] == r.json['id'])
    assert m['hora'] == '00:15' and m['descripcion'] == 'Entrega a cliente' and m['detalle'] == 'Oficina Breña → Komatsu Lurín'
    assert m['referencia'] == 'PV-AGD-000001' and len(m['observacion']) > 500
    # Nombre anterior del rubro: se acepta y se guarda con el nuevo
    r = _g(admin, agd, gente4['adriana'], rubro='Flete y transporte de carga', comprobante_tipo='Sin comprobante (vale)',
           descripcion='Otro (escribir)', descripcion_otro='Motorizado para llevar guantes', pagado_a='Motorizado Juan')
    assert r.status_code == 200, r.json
    assert sql("SELECT rubro, descripcion FROM caja_chica_movimientos WHERE id = %s", (r.json['id'],))[0] == \
        ('Flete y transporte de mercadería', 'Motorizado para llevar guantes')
    # Un gasto antiguo con el nombre anterior se muestra con el nombre nuevo (la base no se toca)
    sql("UPDATE caja_chica_movimientos SET rubro = 'Movilidad del personal (pasajes)' WHERE id = %s", (r.json['id'],))
    m = next(x for x in _movs(admin, agd) if x['id'] == r.json['id'])
    assert m['rubro'] == 'Movilidad operativa del personal'
    sql("UPDATE caja_chica_movimientos SET rubro = 'Flete y transporte de mercadería' WHERE id = %s", (r.json['id'],))


def test_planilla_de_movilidad_numerada(admin, agd, gente4):
    assert _g(admin, agd, gente4['milagros'], monto='4', hora='00:40', descripcion='Recojo de productos de proveedores').status_code == 200
    assert _g(admin, agd, gente4['sebastián'], monto='5').status_code == 200
    html = admin.get(f'/caja-chica/imprimir/movilidad?empresa_id={agd}&desde={HOY}&hasta={HOY}').get_data(as_text=True)
    assert 'BORRADOR SIN NÚMERO' in html
    r = admin.post('/caja-chica/api/planillas', json={'empresa_id': agd, 'desde': HOY.isoformat(), 'hasta': HOY.isoformat()})
    assert r.status_code == 200, r.json
    emitidas = r.json['data']
    assert [x['quien'] for x in emitidas] == ['Milagros Salazar', 'Sebastián Díaz']
    assert emitidas[1]['numero'] == emitidas[0]['numero'] + 1 and emitidas[0]['total'] == 7.5
    r = admin.post('/caja-chica/api/planillas', json={'empresa_id': agd, 'desde': HOY.isoformat(), 'hasta': HOY.isoformat()})
    assert r.status_code == 400 and 'ya tienen planilla' in r.json['error']
    ids = ','.join(str(x['id']) for x in emitidas)
    html = admin.get(f'/caja-chica/imprimir/movilidad?empresa_id={agd}&ids={ids}').get_data(as_text=True)
    assert 'N° PM-' in html and f"-{emitidas[0]['numero']:06d}" in html and '70000011' in html and 'Komatsu Lurín' in html and '00:40' in html
    assert 'BORRADOR' not in html
    # Sus pasajes ya no se editan
    m = next(x for x in _movs(admin, agd) if x['quien'] == 'Milagros Salazar' and x['comprobante_tipo'] == 'Planilla de movilidad')
    assert m['bloqueado'] and m['planilla_numero'] == emitidas[0]['numero']
    cambio = {'empresa_id': agd, 'fecha': HOY.isoformat(), 'hora': '00:15', 'rubro': 'Movilidad operativa del personal',
              'monto': '9', 'quien_id': gente4['milagros'], 'descripcion': 'Entrega a cliente', 'detalle': 'A → B',
              'comprobante_tipo': 'Planilla de movilidad'}
    r = admin.put(f'/caja-chica/api/gasto/{m["id"]}', json=cambio)
    assert r.status_code == 400 and 'planilla de movilidad N°' in r.json['error']
    # La gerencia la anula: el N° no se reutiliza y los pasajes vuelven a quedar libres
    r = admin.post(f'/caja-chica/api/planillas/{emitidas[0]["id"]}/anular', json={'empresa_id': agd, 'motivo': 'monto mal escrito'})
    assert r.status_code == 200, r.json
    assert admin.put(f'/caja-chica/api/gasto/{m["id"]}', json=cambio).status_code == 200
    r = admin.post('/caja-chica/api/planillas', json={'empresa_id': agd, 'desde': HOY.isoformat(), 'hasta': HOY.isoformat()})
    assert r.status_code == 200 and r.json['data'][0]['numero'] == emitidas[1]['numero'] + 1
    lista = admin.get(f'/caja-chica/api/planillas?empresa_id={agd}').json['data']
    assert {p['estado'] for p in lista} == {'Emitida', 'Anulada'}


def test_solo_gerencia_anula_planilla(app, agd):
    from routes import caja_chica
    with app.test_request_context():
        from flask import session
        session['usuario_id'] = 999999
        session['rol'] = 'vendedor'
        with pytest.raises(caja_chica.ErrorCaja):
            caja_chica.anular_planilla(agd, 1, 'motivo de prueba')


def test_caja_noche_sin_hora_sin_itf_vale_y_flete():
    # Erika 04/11/2026 (noche): quitar la hora, quitar gastos bancarios, "Vale", flete pagado al transportista
    from pathlib import Path
    from routes import caja_chica as cc
    assert 'Gastos bancarios (ITF)' not in cc.RUBROS_FORMULARIO and 'Gastos bancarios (ITF)' in cc.RUBROS
    raiz = Path(__file__).resolve().parent.parent
    js = (raiz / 'static/js/caja_chica.js').read_text(encoding='utf-8')
    assert 'type="hidden" name="hora"' in js and '<label>Hora' not in js
    assert "'Sin comprobante (vale)': 'Vale'" in js and 'data-solo-flete' in js and '<b>Pagado a</b>: el transportista' in js
    src = (raiz / 'routes/caja_chica.py').read_text(encoding='utf-8')
    assert 'En flete, en "Pagado a" elige al transportista' in src


def test_caja_vale_correlativo_factura_con_proveedor_y_solo_hellen(admin, agd, gente4):
    # Erika 04/11/2026 (noche): correlativo propio del vale por empresa, factura con proveedor, solo Hellen y Erika
    cod = sql("SELECT codigo FROM erp_empresas WHERE id::text = %s", (agd,))[0][0]
    q = gente4['milagros']
    r1 = _g(admin, agd, q, rubro='Útiles, impresiones y oficina', comprobante_tipo='Sin comprobante (vale)',
            descripcion='Cinta de embalaje', detalle='', monto='4.00', comprobante_numero='lo-que-sea')
    assert r1.status_code == 200, r1.json
    r2 = _g(admin, agd, q, rubro='Útiles, impresiones y oficina', comprobante_tipo='Sin comprobante (vale)',
            descripcion='Plumones', detalle='', monto='5.00')
    assert r2.status_code == 200, r2.json
    nums = [f[0] for f in sql(
        """SELECT comprobante_numero FROM caja_chica_movimientos WHERE empresa_id::text = %s
           AND comprobante_numero LIKE %s ORDER BY id""", (agd, f'V-{cod}-%'))]
    assert len(nums) >= 2 and nums[-1] == f'V-{cod}-' + str(int(nums[-2][-6:]) + 1).zfill(6), nums
    r = _g(admin, agd, q, rubro='Útiles, impresiones y oficina', comprobante_tipo='Factura', comprobante_numero='F001-9',
           ruc_emisor='20100000001', descripcion='Tóner', detalle='', monto='40.00', pagado_a='')
    assert r.status_code == 400 and 'proveedor' in r.json['error']
    from utils import USUARIOS_CAJA_CHICA
    assert 'hel02kcf' in USUARIOS_CAJA_CHICA and 'eri01kcf' in USUARIOS_CAJA_CHICA
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent
    assert '{% if gestiona_caja %}' in (raiz / 'templates/base.html').read_text(encoding='utf-8')
    js = (raiz / 'static/js/caja_chica.js').read_text(encoding='utf-8')
    assert '<th>Quién gastó</th><th>Pagado a</th>' in js and 'autorizado por Erika' in js and 'PM-' in js
