"""
Caja chica con fondo fijo (pedido de Erika del 22/10/2026). Personas y montos de prueba, solo en la base local.
  - Solo gerencia o quien tenga el permiso "Caja chica". Aprobar y reponer: solo gerencia.
  - Gastos con rubro, quién gastó, comprobante y foto; planilla de movilidad solo para el personal con DNI.
  - Rendición semanal: bloquea los gastos enviados; observar los libera; aprobar repone lo que falta para el fondo
    y deja el pago en Finanzas (para la conciliación bancaria).
  - Arqueo con diferencia pide explicación. Importar el histórico desde la plantilla Excel, una sola vez.
"""
import io
from datetime import timedelta

import pytest

from tests.test_flujos import sql
from tests.test_permisos_usuarios import base, _usuario, _guardar   # noqa: F401  (base es fixture)
from routes.caja_chica import _ahora

HOY = _ahora().date()


@pytest.fixture(scope='module')
def kcf(base):
    return str(base['emp']['KCF'])


@pytest.fixture(scope='module')
def gente(admin, kcf):
    ids = {}
    for nombre, tipo, dni in (('Luis Prueba', 'Practicante', '70000001'), ('Hellen Prueba', 'Trabajador', '40000002'),
                              ('Sin Dni Prueba', 'Practicante', ''), ('Franklin Prueba', 'Transportista', '')):
        r = admin.post('/caja-chica/api/personas', json={'empresa_id': kcf, 'nombre': nombre, 'tipo': tipo, 'dni': dni})
        assert r.status_code == 200, r.json
        ids[nombre.split()[0]] = r.json['id']
    r = admin.post('/caja-chica/api/config', json={'empresa_id': kcf, 'fondo_fijo': 600, 'responsable': 'Hellen Prueba',
                                                   'responsable_dni': '40000002', 'cuenta': 'BCP 191-000 (solo caja chica)', 'rmv': 1230})
    assert r.status_code == 200, r.json
    return ids


def _gasto(cli, kcf, quien, **kw):
    d = {'empresa_id': kcf, 'fecha': HOY.isoformat(), 'rubro': 'Movilidad del personal (pasajes)', 'monto': '3.50',
         'quien_id': quien, 'descripcion': 'Pasaje de Oficina a Malvinas', 'comprobante_tipo': 'Planilla de movilidad'}
    d.update(kw)
    return cli.post('/caja-chica/api/gasto', json=d)


def _resumen(cli, kcf):
    r = cli.get(f'/caja-chica/api/resumen?empresa_id={kcf}')
    assert r.status_code == 200, r.json
    return r.json['data']


def test_permiso_propio(app, admin, vendedor, base):
    assert admin.get('/caja-chica').status_code == 200
    assert 'data-modulo="caja_chica"' in admin.get('/caja-chica').get_data(as_text=True)
    r = vendedor.get('/caja-chica/api/resumen')
    assert r.status_code == 403 and r.json['codigo'] == 'sin_permiso'
    sql("""INSERT INTO erp_modulos (orden, codigo, nombre, estado) SELECT 7, 'FINANZAS', 'Finanzas', 'activo'
           WHERE NOT EXISTS (SELECT 1 FROM erp_modulos WHERE codigo = 'FINANZAS')""")
    sql("""INSERT INTO erp_submodulos (modulo_id, orden, codigo, nombre, estado)
           SELECT m.id, 8, 'CAJA_CHICA', 'Caja chica', 'activo' FROM erp_modulos m
           WHERE m.codigo = 'FINANZAS' AND NOT EXISTS (SELECT 1 FROM erp_submodulos WHERE codigo = 'CAJA_CHICA')""")
    from werkzeug.security import generate_password_hash
    from conftest import _login
    from routes.acceso import limpiar_cache
    uid, _ = _usuario(base, 'caja_usuaria', empresas=('KCF',))
    sql("UPDATE usuarios SET password = %s WHERE id = %s", (generate_password_hash('Caja#2026!'), uid))
    _guardar(admin, uid, base['emp']['KCF'], [{'submodulo_codigo': 'CUENTAS_PAGAR', 'puede_ver': True}])
    limpiar_cache()
    h = _login(app, 'caja_usuaria', 'Caja#2026!')
    assert h.get('/caja-chica/api/resumen').status_code == 403          # ver Finanzas no basta
    _guardar(admin, uid, base['emp']['KCF'], [{'submodulo_codigo': 'CAJA_CHICA', 'puede_ver': True, 'puede_crear': True,
                                              'puede_editar': True}])
    limpiar_cache()
    assert h.get('/caja-chica').status_code == 200
    assert h.post('/caja-chica/api/config', json={'fondo_fijo': 900, 'responsable': 'X'}).status_code == 403


def test_validaciones_del_gasto(admin, kcf, gente):
    r = _gasto(admin, kcf, gente['Luis'], monto='3.555')
    assert r.status_code == 400 and '2 decimales' in r.json['error']
    r = _gasto(admin, kcf, gente['Luis'], fecha=(HOY + timedelta(days=1)).isoformat())
    assert r.status_code == 400 and 'futura' in r.json['error']
    r = _gasto(admin, kcf, gente['Sin'])
    assert r.status_code == 400 and 'DNI' in r.json['error']
    r = _gasto(admin, kcf, gente['Franklin'])
    assert r.status_code == 400 and 'transportistas' in r.json['error']
    r = _gasto(admin, kcf, gente['Luis'], rubro='Taxi')
    assert r.status_code == 400 and 'solo para pasajes' in r.json['error']
    r = _gasto(admin, kcf, gente['Luis'], rubro='Flete y transporte de carga', comprobante_tipo='Factura', monto='50')
    assert r.status_code == 400 and 'N° de la factura' in r.json['error']
    r = _gasto(admin, kcf, gente['Luis'], rubro='Flete y transporte de carga', comprobante_tipo='Factura', monto='50',
               comprobante_numero='E001-12')
    assert r.status_code == 400 and 'RUC' in r.json['error']
    r = _gasto(admin, kcf, gente['Hellen'], rubro='Útiles, impresiones y oficina', comprobante_tipo='Boleta',
               comprobante_numero='B001-9', monto='150')
    assert r.status_code == 400 and 'autorizó' in r.json['error']
    r = _gasto(admin, kcf, None)
    assert r.status_code == 400 and 'quién gastó' in r.json['error']


def test_gastos_saldo_tope_y_foto(admin, kcf, gente):
    r = admin.post('/caja-chica/api/ingreso', json={'empresa_id': kcf, 'tipo': 'Reposición', 'fecha': HOY.isoformat(),
                                                    'monto': 600, 'descripcion': 'Fondo inicial', 'numero_operacion': '111'})
    assert r.status_code == 200, r.json
    pago = sql("SELECT monto, documento_tabla, empresa_id::text FROM finanzas_pagos WHERE documento_tabla = 'caja_chica_movimientos'")
    assert pago and float(pago[0][0]) == 600 and pago[0][2] == kcf
    r = _gasto(admin, kcf, gente['Luis'], monto='30')
    assert r.status_code == 200 and not r.json['avisos']
    r = _gasto(admin, kcf, gente['Luis'], monto='25')                   # 55 > 49.20 en el día
    assert r.status_code == 200 and any('tope' in a for a in r.json['avisos'])
    r = _gasto(admin, kcf, gente['Hellen'], rubro='Flete y transporte de carga', comprobante_tipo='Factura', monto='120',
               comprobante_numero='E001-45', ruc_emisor='10456789012', pagado_a='Franklin Prueba',
               autorizado_por='Erika por WhatsApp', referencia='PC-KCF-000010')
    assert r.status_code == 200, r.json
    mid = r.json['id']
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (2400, 1600), 'white').save(buf, 'PNG')
    buf.seek(0)
    r = admin.post(f'/caja-chica/api/movimiento/{mid}/foto', data={'empresa_id': kcf, 'foto': (buf, 'voucher.png')},
                   content_type='multipart/form-data')
    assert r.status_code == 200, r.json
    fotos = admin.get(f'/caja-chica/api/movimiento/{mid}/fotos?empresa_id={kcf}').json['data']
    assert len(fotos) == 1 and fotos[0]['mime'] == 'image/jpeg' and fotos[0]['bytes'] < 200_000
    assert admin.get(f'/caja-chica/foto/{fotos[0]["id"]}').status_code == 200
    d = _resumen(admin, kcf)
    assert d['saldo'] == 600 - 30 - 25 - 120 and d['pendientes']['n'] == 3 and d['pendientes']['sin_foto'] == 0
    assert d['mes']['sin_sustento'] == 0
    assert admin.get(f'/caja-chica/imprimir/vale/{mid}?empresa_id={kcf}').status_code == 200
    html = admin.get(f'/caja-chica/imprimir/movilidad?empresa_id={kcf}&desde={HOY}&hasta={HOY}').get_data(as_text=True)
    assert 'PLANILLA DE GASTOS DE MOVILIDAD' in html and '70000001' in html and 'pasan el tope' in html


def test_rendicion_observar_y_aprobar(admin, kcf, gente):
    r = admin.post('/caja-chica/api/rendicion', json={'empresa_id': kcf, 'hasta': HOY.isoformat()})
    assert r.status_code == 200, r.json
    rid = sql("SELECT id FROM caja_chica_rendiciones WHERE empresa_id = %s ORDER BY id DESC LIMIT 1", (kcf,))[0][0]
    assert admin.post('/caja-chica/api/rendicion', json={'empresa_id': kcf}).status_code == 400   # ya hay una por aprobar
    movs = admin.get(f'/caja-chica/api/movimientos?empresa_id={kcf}').json['data']['filas']
    gasto = next(m for m in movs if m['tipo'] == 'Gasto')
    r = admin.put(f'/caja-chica/api/gasto/{gasto["id"]}', json={'empresa_id': kcf, 'fecha': HOY.isoformat(),
                  'rubro': 'Movilidad del personal (pasajes)', 'monto': '20', 'quien_id': gente['Luis'],
                  'descripcion': 'Cambio', 'comprobante_tipo': 'Planilla de movilidad'})
    assert r.status_code == 400 and 'ya no se cambia' in r.json['error']
    # Observar: los gastos vuelven a quedar libres y se pueden corregir
    r = admin.post(f'/caja-chica/api/rendicion/{rid}/observar', json={'empresa_id': kcf, 'motivo': 'Falta la foto del taxi'})
    assert r.status_code == 200
    r = admin.put(f'/caja-chica/api/gasto/{gasto["id"]}', json={'empresa_id': kcf, 'fecha': HOY.isoformat(),
                  'rubro': 'Movilidad del personal (pasajes)', 'monto': '19', 'quien_id': gente['Luis'],
                  'descripcion': 'Pasaje corregido', 'comprobante_tipo': 'Planilla de movilidad'})
    assert r.status_code == 200, r.json
    r = admin.post('/caja-chica/api/rendicion', json={'empresa_id': kcf, 'hasta': HOY.isoformat()})
    assert r.status_code == 200
    rid = sql("SELECT id FROM caja_chica_rendiciones WHERE empresa_id = %s ORDER BY id DESC LIMIT 1", (kcf,))[0][0]
    det = admin.get(f'/caja-chica/api/rendicion/{rid}?empresa_id={kcf}').json['data']
    assert det['rendicion']['total_gastado'] == 19 + 25 + 120 and len(det['gastos']) == 3
    r = admin.post(f'/caja-chica/api/rendicion/{rid}/aprobar', json={'empresa_id': kcf, 'numero_operacion': '987654',
                                                                     'fecha_reposicion': HOY.isoformat()})
    assert r.status_code == 200, r.json
    d = _resumen(admin, kcf)
    assert d['saldo'] == 600 and d['por_reponer'] == 0
    pago = sql("SELECT monto, numero_operacion FROM finanzas_pagos WHERE documento_tabla = 'caja_chica_rendiciones' AND documento_id = %s", (rid,))
    assert float(pago[0][0]) == 164 and pago[0][1] == '987654'
    # Semana cerrada: no se registra con fecha de esa semana
    r = _gasto(admin, kcf, gente['Luis'])
    assert r.status_code == 400 and 'cerrada' in r.json['error']
    assert admin.get(f'/caja-chica/imprimir/rendicion/{rid}?empresa_id={kcf}').status_code == 200
    assert admin.get(f'/caja-chica/imprimir/acta?empresa_id={kcf}').status_code == 200


def test_arqueo_y_anular(admin, kcf, gente):
    r = admin.post('/caja-chica/api/arqueo', json={'empresa_id': kcf, 'efectivo': 100, 'saldo_cuenta': 495})
    assert r.status_code == 400 and 'diferencia' in r.json['error']
    r = admin.post('/caja-chica/api/arqueo', json={'empresa_id': kcf, 'efectivo': 100, 'saldo_cuenta': 500})
    assert r.status_code == 200 and 'cuadra' in r.json['message']
    movs = admin.get(f'/caja-chica/api/movimientos?empresa_id={kcf}').json['data']['filas']
    repo = next(m for m in movs if m['tipo'] == 'Reposición' and m['rendicion_id'])
    r = admin.post(f'/caja-chica/api/movimiento/{repo["id"]}/anular', json={'empresa_id': kcf, 'motivo': 'prueba de candado'})
    assert r.status_code == 400


def test_importar_historico(admin, base):
    import openpyxl
    agd = str(base['emp']['AGD'])
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Movimientos'
    ws.append(['CAJA CHICA'])
    ws.append([])
    ws.append(['N°', 'Fecha', 'Periodo', 'Empresa del gasto', 'Tipo', 'Rubro', 'Quién gastó', 'Pagado a',
               'Descripción (de dónde a dónde / para qué)', 'N° PC / OC / despacho', 'Tipo de comprobante', 'N° comprobante',
               '¿Foto?', 'Ingreso (S/)', 'Egreso (S/)', 'Saldo (S/)', 'N° rendición', 'Observación'])
    from datetime import datetime
    ws.append([1, datetime(2025, 12, 29), None, 'AGD', 'Reposición de fondo', None, None, None, 'Saldo inicial', None, None, None, None, 134.61])
    ws.append([2, datetime(2026, 1, 5), None, 'AGD', 'Gasto', 'Flete y transporte de carga', None, 'Felipe Varas',
               'Entrega a Neuma', 'PC 2040329157', 'No registrado (histórico)', None, 'No', None, 20])
    ws.append([3, datetime(2026, 1, 6), None, 'AGD', 'Reposición de fondo', None, None, None, 'Ingreso a caja', None, None, None, None, 500])
    buf = io.BytesIO()
    wb.save(buf)
    datos = buf.getvalue()
    r = admin.post('/caja-chica/api/importar', data={'empresa_id': agd, 'archivo': (io.BytesIO(datos), 'caja.xlsx')},
                   content_type='multipart/form-data')
    assert r.status_code == 200, r.json
    assert r.json['data']['filas'] == 2 and r.json['data']['saldo_final'] == 614.61
    assert sql("SELECT COUNT(*) FROM caja_chica_movimientos WHERE empresa_id = %s", (agd,))[0][0] == 0   # solo vista previa
    r = admin.post('/caja-chica/api/importar', data={'empresa_id': agd, 'archivo': (io.BytesIO(datos), 'caja.xlsx'), 'confirmar': '1'},
                   content_type='multipart/form-data')
    assert r.status_code == 200
    d = admin.get(f'/caja-chica/api/resumen?empresa_id={agd}').json['data']
    assert d['saldo'] == 614.61 and d['historico']['n'] == 3
    r = admin.post('/caja-chica/api/importar', data={'empresa_id': agd, 'archivo': (io.BytesIO(datos), 'caja.xlsx'), 'confirmar': '1'},
                   content_type='multipart/form-data')
    assert r.status_code == 400 and 'una vez' in r.json['error']
    hist = next(m for m in admin.get(f'/caja-chica/api/movimientos?empresa_id={agd}').json['data']['filas'] if m['tipo'] == 'Gasto')
    r = admin.put(f'/caja-chica/api/gasto/{hist["id"]}', json={'empresa_id': agd})
    assert r.status_code == 400
