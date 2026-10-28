"""
Planilla y RRHH simple (pedido de Erika del 21/10/2026). Personas y sueldos inventados, solo en la base local.
  - Solo gerencia o quien tenga el permiso "Planilla".
  - El ERP no inventa sueldos: los escribe Erika; se valida el sueldo mínimo y el % de AFP.
  - Cálculos: sueldo con ONP / AFP, EsSalud, recibo por honorarios, gratificación, CTS, media subvención, vacaciones.
  - Los pagos se marcan con N° de operación y se desmarcan con motivo.
  - Las bases de EsSalud, ONP, AFP y sueldos se pasan solas a SUNAT ▸ Pagos del mes.
"""
from datetime import date
from decimal import Decimal

import pytest

from tests.test_flujos import sql
from tests.test_permisos_usuarios import base, _usuario, _guardar   # noqa: F401  (base es fixture)

from routes.planilla import _ahora
HOY = _ahora().date()
PERIODO = f'{HOY.year:04d}-{HOY.month:02d}'
CONF = {'regimen_laboral': 'GENERAL', 'rmv': Decimal('1130'), 'configurado': True}


def _p(**kw):
    p = {'id': 0, 'tipo': 'Planilla', 'sueldo': Decimal('2000'), 'pension': 'ONP', 'afp_porcentaje': None,
         'asignacion_familiar': False, 'fecha_ingreso': date(2025, 1, 1), 'fecha_cese': None}
    p.update(kw)
    return p


@pytest.fixture(scope='module')
def kcf(base):
    return str(base['emp']['KCF'])


def _nueva(admin, kcf, **kw):
    d = {'empresa_id': kcf, 'nombres': 'Persona Prueba', 'documento': '40000001', 'tipo': 'Planilla',
         'fecha_ingreso': '2025-01-01', 'sueldo': 2000, 'pension': 'ONP', 'banco': 'BCP', 'cuenta': '191-000'}
    d.update(kw)
    return admin.post('/planilla/api/personal', json=d)


def test_solo_erika_aunque_tenga_permiso(app, admin, vendedor, base):
    assert admin.get('/planilla').status_code == 200
    assert 'data-modulo="planilla"' in admin.get('/planilla').get_data(as_text=True)
    r = vendedor.get('/planilla/api/pagos')
    assert r.status_code == 403 and r.json['codigo'] == 'sin_permiso'
    sql("""INSERT INTO erp_modulos (orden, codigo, nombre, estado) SELECT 7, 'FINANZAS', 'Finanzas', 'activo'
           WHERE NOT EXISTS (SELECT 1 FROM erp_modulos WHERE codigo = 'FINANZAS')""")
    sql("""INSERT INTO erp_submodulos (modulo_id, orden, codigo, nombre, estado)
           SELECT m.id, 7, 'PLANILLA', 'Planilla', 'activo' FROM erp_modulos m
           WHERE m.codigo = 'FINANZAS' AND NOT EXISTS (SELECT 1 FROM erp_submodulos WHERE codigo = 'PLANILLA')""")
    from werkzeug.security import generate_password_hash
    from conftest import _login
    from routes.acceso import limpiar_cache
    uid, _ = _usuario(base, 'pla_usuario', empresas=('KCF',))
    sql("UPDATE usuarios SET password = %s WHERE id = %s", (generate_password_hash('Plani#2026!'), uid))
    _guardar(admin, uid, base['emp']['KCF'], [{'submodulo_codigo': 'CUENTAS_PAGAR', 'puede_ver': True}])
    limpiar_cache()
    h = _login(app, 'pla_usuario', 'Plani#2026!')
    assert h.get('/planilla/api/pagos').status_code == 403            # ver Finanzas no basta
    _guardar(admin, uid, base['emp']['KCF'], [{'submodulo_codigo': 'PLANILLA', 'puede_ver': True}])
    limpiar_cache()
    # Erika 28/10/2026: "Hellen y nadie debe ver planilla": ni con el permiso Planilla de la matriz
    assert h.get('/planilla/api/pagos').status_code == 403


def test_calculos_del_sueldo():
    from routes.planilla import lineas_del_mes, meses_completos
    assert meses_completos(date(2026, 1, 1), date(2026, 6, 30)) == 6
    assert meses_completos(date(2026, 1, 15), date(2026, 6, 30)) == 5
    assert meses_completos(date(2026, 1, 1), date(2026, 6, 10)) == 5
    onp = lineas_del_mes(_p(), CONF, 2026, 9)[0]
    assert (onp['bruto'], onp['descuento'], onp['neto'], onp['essalud']) == (Decimal('2000'), Decimal('260'), Decimal('1740'), Decimal('180'))
    afp = lineas_del_mes(_p(pension='AFP', afp_porcentaje=Decimal('11.37'), asignacion_familiar=True), CONF, 2026, 9)[0]
    assert afp['bruto'] == Decimal('2113') and afp['descuento'] == Decimal('240.25') and afp['afp'] == Decimal('240.25')
    # EsSalud nunca sobre menos del sueldo mínimo
    parcial = lineas_del_mes(_p(sueldo=Decimal('600')), CONF, 2026, 9)[0]
    assert parcial['essalud'] == Decimal('101.70')
    # Ingresó a mitad de mes: proporcional
    medio = lineas_del_mes(_p(fecha_ingreso=date(2026, 9, 16)), CONF, 2026, 9)[0]
    assert medio['bruto'] == Decimal('1000') and '15 días' in medio['detalle']
    rxh = lineas_del_mes(_p(tipo='Recibo por honorarios', sueldo=Decimal('2000')), CONF, 2026, 9)[0]
    assert rxh['descuento'] == Decimal('160') and rxh['renta_4ta'] == Decimal('160')
    assert lineas_del_mes(_p(tipo='Recibo por honorarios', sueldo=Decimal('1500')), CONF, 2026, 9)[0]['descuento'] == 0
    prac = lineas_del_mes(_p(tipo='Practicante', sueldo=Decimal('1130')), CONF, 2026, 9)
    assert prac[0]['descuento'] == 0 and prac[0]['essalud'] == 0
    assert lineas_del_mes(_p(fecha_cese=date(2026, 8, 31)), CONF, 2026, 9) == []


def test_gratificacion_cts_y_media_subvencion():
    from routes.planilla import gratificacion, cts, subvencion_adicional, lineas_del_mes
    g = gratificacion(_p(), CONF, 2026, 7)
    assert g['grati'] == Decimal('2000') and g['bonificacion'] == Decimal('180') and g['meses'] == 6
    assert gratificacion(_p(fecha_ingreso=date(2026, 3, 1)), CONF, 2026, 7)['grati'] == Decimal('1333.33')
    assert gratificacion(_p(), dict(CONF, regimen_laboral='PEQUENA'), 2026, 7)['grati'] == Decimal('1000')
    assert gratificacion(_p(), dict(CONF, regimen_laboral='MICRO'), 2026, 7) is None
    assert gratificacion(_p(tipo='Practicante'), CONF, 2026, 7) is None
    assert gratificacion(_p(), CONF, 2026, 8) is None
    c = cts(_p(), CONF, 2026, 11)
    assert c['total'] == Decimal('1166.67')                   # (2000 + 333.33) / 2
    assert cts(_p(), dict(CONF, regimen_laboral='PEQUENA'), 2026, 11)['total'] == Decimal('541.67')     # (2000 + 1000/6) · 0.5 · 6/12
    assert [x['concepto'] for x in lineas_del_mes(_p(), CONF, 2026, 12)] == ['Sueldo', 'Gratificación']
    prac = _p(tipo='Practicante', sueldo=Decimal('1200'), fecha_ingreso=date(2026, 3, 10))
    assert subvencion_adicional(prac, 2026, 9)['total'] == Decimal('600')
    assert subvencion_adicional(prac, 2026, 8) is None


def test_no_inventa_sueldos_y_valida(admin, kcf):
    r = _nueva(admin, kcf, sueldo='')
    assert r.status_code == 400 and 'sueldo' in r.json['error']
    r = _nueva(admin, kcf, sueldo=800)
    assert r.status_code == 400 and 'mínima' in r.json['error']
    assert _nueva(admin, kcf, nombres='Medio Tiempo Prueba', sueldo=800, jornada_parcial=True).status_code == 200
    r = _nueva(admin, kcf, pension='AFP')
    assert r.status_code == 400 and 'AFP' in r.json['error']
    r = _nueva(admin, kcf, fecha_ingreso='2026-05-01', fecha_cese='2026-04-01')
    assert r.status_code == 400
    # Personal vacío de AGD: nada inventado
    from routes.planilla import asegurar_tablas
    asegurar_tablas()


def test_pagos_del_mes_y_sunat(admin, kcf):
    assert _nueva(admin, kcf, nombres='Ana Planilla Prueba').status_code == 200
    assert _nueva(admin, kcf, nombres='Beto Practicante Prueba', tipo='Practicante', sueldo=1230)   # RMV desde 01/10/2026.status_code == 200
    r = admin.get(f'/planilla/api/pagos?empresa_id={kcf}&periodo={PERIODO}')
    assert r.status_code == 200, r.json
    d = r.json['data']
    ana = next(f for f in d['filas'] if f['nombres'] == 'Ana Planilla Prueba' and f['concepto'] == 'Sueldo')
    assert ana['neto'] == 1740.0 and ana['essalud'] == 180.0 and not ana['pagado']
    assert d['por_pagar'] > 0 and d['enviado_sunat']
    from routes.sunat import leer_periodo
    plan = leer_periodo(kcf, PERIODO)['planilla']
    assert Decimal(plan['base_essalud']) == Decimal(str(d['enviado_sunat']['base_essalud']))
    assert Decimal(plan['base_onp']) >= Decimal('2000')
    # Meses viejos no pisan lo que declaró el contador
    viejo = admin.get(f'/planilla/api/pagos?empresa_id={kcf}&periodo=2025-06').json['data']
    assert viejo['enviado_sunat'] is None and viejo['mes_reciente'] is False


def test_marcar_y_desmarcar_pago(admin, kcf):
    d = admin.get(f'/planilla/api/pagos?empresa_id={kcf}&periodo={PERIODO}').json['data']
    ana = next(f for f in d['filas'] if f['nombres'] == 'Ana Planilla Prueba')
    cuerpo = {'empresa_id': kcf, 'periodo': PERIODO, 'personal_id': ana['personal_id'], 'concepto': 'Sueldo'}
    r = admin.post('/planilla/api/pagos/marcar', json=cuerpo)
    assert r.status_code == 400 and 'N° de operación' in r.json['error']
    assert admin.post('/planilla/api/pagos/marcar', json=dict(cuerpo, numero_operacion='OP-123')).status_code == 200
    assert admin.post('/planilla/api/pagos/marcar', json=dict(cuerpo, numero_operacion='OP-124')).status_code == 400
    d = admin.get(f'/planilla/api/pagos?empresa_id={kcf}&periodo={PERIODO}').json['data']
    ana = next(f for f in d['filas'] if f['nombres'] == 'Ana Planilla Prueba')
    assert ana['pagado'] and ana['numero_operacion'] == 'OP-123' and ana['marcado_por']
    assert admin.post('/planilla/api/pagos/desmarcar', json=cuerpo).status_code == 400            # sin motivo
    assert admin.post('/planilla/api/pagos/desmarcar', json=dict(cuerpo, motivo='Rechazado')).status_code == 200
    hist = sql("SELECT historial FROM rrhh_pagos WHERE personal_id = %s AND estado = 'Desmarcado'", (ana['personal_id'],))
    assert hist and hist[0][0][0]['motivo'] == 'Rechazado'


def test_vacaciones_e_historial(admin, kcf):
    r = _nueva(admin, kcf, nombres='Caro Vacaciones Prueba', fecha_ingreso='2024-01-01')
    pid = r.json['id']
    url = f'/planilla/api/personal/{pid}/vacaciones'
    assert admin.post(url, json={'empresa_id': kcf, 'desde': '2025-02-01', 'hasta': '2025-02-10'}).status_code == 200
    r = admin.post(url, json={'empresa_id': kcf, 'desde': '2025-02-05', 'hasta': '2025-02-06'})
    assert r.status_code == 400 and 'cruzan' in r.json['error']
    gente = admin.get(f'/planilla/api/personal?empresa_id={kcf}').json['data']
    caro = next(p for p in gente['personal'] if p['id'] == pid)
    v = caro['vacaciones']
    assert v['tomados'] == 10 and v['por_anio'] == 30 and v['registros'][0]['dias'] == 10
    assert v['acumulado'] is True and v['vencidos'] == 20             # el 1.er año (30 días) ya debió gozarse
    r = admin.put(f'/planilla/api/personal/{pid}', json={'empresa_id': kcf, 'nombres': 'Caro Vacaciones Prueba',
                                                        'tipo': 'Planilla', 'fecha_ingreso': '2024-01-01', 'sueldo': 2500,
                                                        'pension': 'ONP'})
    assert r.status_code == 200
    h = sql("SELECT historial FROM rrhh_personal WHERE id = %s", (pid,))[0][0]
    assert any('sueldo: 2000.00 → 2500.00' in c for c in h[-1]['cambios'])
    assert {b['tipo'] for b in gente['beneficios']} == {'CTS', 'Gratificación'}
