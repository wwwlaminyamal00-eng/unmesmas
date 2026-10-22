"""
Conciliación bancaria (pedido de Erika del 21/10/2026). Datos inventados, solo en la base local.
  - Lee extractos de distintos bancos (CSV con líneas de título, Monto con signo, Cargo/Abono, Excel).
  - Concilia solo por N° de operación + monto, o por monto + fecha cuando hay una sola opción.
  - ITF y comisiones quedan como gasto del banco.
  - Muestra lo que está en el banco y falta en el ERP, y lo registrado en el ERP que el banco no muestra.
  - Subir dos veces el mismo archivo no duplica. Deshacer pide motivo y no se vuelve a unir solo.
  - Solo gerencia o quien tenga el permiso "Conciliación bancaria".
"""
import io
from datetime import date
from decimal import Decimal

import openpyxl
import pytest

from tests.test_flujos import sql
from tests.test_permisos_usuarios import base, _usuario, _guardar   # noqa: F401  (base es fixture)

MES = '2026-09'


@pytest.fixture(scope='module')
def datos(base, admin):
    eid = base['emp']['KCF']
    ids = {}
    for n, total, cliente in ((1, 1180, 'CLIENTE ALFA S.A.C.'), (2, 590, 'CLIENTE BETA S.A.C.'),
                              (3, 236, 'COMERCIAL GAMMA S.A.C.'), (4, 50, 'CLIENTE DELTA S.A.C.')):
        ids[n] = sql("""INSERT INTO comprobantes (tipo_comprobante, serie, numero, fecha_emision, cliente_tipo_doc,
                            cliente_numero_doc, cliente_nombre, subtotal, igv, total, items_json, estado_sunat, empresa_id)
                        VALUES ('Factura', 'F950', %s, '2026-09-01', 'RUC', '2010007097' || %s, %s, %s, 0, %s, '[]',
                                'Emitido', %s) RETURNING id""", (n, n, cliente, total, total, eid))[0][0]
    ids['cp'] = sql("""INSERT INTO comprobantes_proveedor (tipo, numero, fecha, monto, ruc_proveedor, proveedor_nombre, estado, empresa_id)
                       VALUES ('Factura', 'FP-77', '2026-09-02', 354, '20600011111', 'PROVEEDOR ACEROS S.A.C.', 'Pendiente', %s)
                       RETURNING id""", (eid,))[0][0]

    def mov(**d):
        r = admin.post('/finanzas/api/movimientos', json=d)
        assert r.status_code == 200, r.json
        return r.json['data']['id']
    ids['c1'] = mov(tipo='COBRO', documento_id=ids[1], monto=1180, fecha='2026-09-10', metodo='Transferencia',
                    banco='BCP', numero_operacion='00123456')
    ids['c2'] = mov(tipo='COBRO', documento_id=ids[2], monto=590, fecha='2026-09-12', metodo='Depósito',
                    banco='BCP', fecha_aviso='2026-09-12')
    ids['c4'] = mov(tipo='COBRO', documento_id=ids[4], monto=50, fecha='2026-09-14', metodo='Transferencia',
                    banco='BCP', numero_operacion='4444')
    ids['p1'] = mov(tipo='PAGO', documento_id=ids['cp'], monto=354, fecha='2026-09-15', metodo='Transferencia',
                    banco='BCP', numero_operacion='777001')
    ids['eid'] = eid
    return ids


# Como lo baja la banca por internet del BCP: líneas de título, separador ";", Monto con signo y miles con coma
CSV_BCP = """Movimientos de la cuenta;;;;;;;
Cuenta: 194-0000000-0-00;;;;;;;
;;;;;;;
Fecha;Fecha valuta;Descripción operación;Monto;Saldo;Sucursal - agencia;Operación - Número;Operación - Hora
10/09/2026;10/09/2026;TRAN.CTAS.TERC CLIENTE ALFA;1,180.00;6,180.00;193 - Via BCP;123456;10:15
13/09/2026;13/09/2026;DEPOSITO EN EFECTIVO;590.00;6,770.00;111 - SMP;000555;11:00
15/09/2026;15/09/2026;PAGO A PROVEEDOR;-354.00;6,416.00;193 - Via BCP;777001;09:30
16/09/2026;16/09/2026;IMPUESTO ITF;-0.05;6,415.95;;;
18/09/2026;18/09/2026;ABONO COMERCIAL GAMMA;236.00;6,651.95;193 - Via BCP;000888;16:20
20/09/2026;20/09/2026;ABONO VARIOS;999.99;7,651.94;193 - Via BCP;000999;17:00
"""


def _subir(cliente, eid, contenido, nombre='extracto_bcp.csv', banco='BCP'):
    return cliente.post('/bancos/api/subir', data={'empresa_id': eid, 'banco': banco, 'cuenta': '194-0000000-0-00',
                                                   'archivo': (io.BytesIO(contenido), nombre)},
                        content_type='multipart/form-data')


def _resumen(cliente, eid):
    r = cliente.get(f'/bancos/api/resumen?empresa_id={eid}&mes={MES}')
    assert r.status_code == 200, r.json
    return r.json['data']


def test_leer_montos_y_fechas():
    from routes.bancos import leer_monto, leer_fecha
    assert leer_monto('1,180.00') == Decimal('1180.00')
    assert leer_monto('-1.234,56') == Decimal('-1234.56')
    assert leer_monto('(150.00)') == Decimal('-150.00')
    assert leer_monto('S/ 12,50') == Decimal('12.50')
    assert leer_monto('') is None and leer_monto(354) == Decimal('354.00')
    assert leer_fecha('10/09/2026') == date(2026, 9, 10)
    assert leer_fecha('2026-09-10 10:23') == date(2026, 9, 10)
    assert leer_fecha('10-09-26') == date(2026, 9, 10)
    assert leer_fecha('Saldo inicial') is None


def test_formatos_cargo_abono_y_excel():
    from routes.bancos import leer_extracto
    # Interbank / Scotiabank: columnas Cargo y Abono separadas
    txt = ('Fecha de operación,Fecha de proceso,Nro. de operación,Movimiento,Descripción,Cargo,Abono,Saldo contable\n'
           '01/09/2026,01/09/2026,111,TRANSF,PAGO LUZ,"1,000.00",,5000\n'
           '02/09/2026,02/09/2026,222,TRANSF,COBRO CLIENTE,,250.5,5250.5\n')
    m = leer_extracto('interbank.csv', txt.encode('utf-8'))
    assert [x['monto'] for x in m] == [Decimal('-1000.00'), Decimal('250.50')]
    assert m[0]['numero_operacion'] == '111' and 'PAGO LUZ' in m[0]['descripcion']
    # BBVA en Excel: títulos en la fila 3 y montos como número
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['BBVA - Movimientos'])
    ws.append([])
    ws.append(['F. Operación', 'F. Valor', 'Código', 'Nº. Doc.', 'Concepto', 'Importe', 'Oficina'])
    ws.append([date(2026, 9, 3), date(2026, 9, 3), '123', 456789, 'ABONO CLIENTE', 300.0, '0011'])
    ws.append([date(2026, 9, 4), date(2026, 9, 4), '124', 456790, 'COMISION MANTENIMIENTO', -12.5, '0011'])
    buf = io.BytesIO()
    wb.save(buf)
    m = leer_extracto('bbva.xlsx', buf.getvalue())
    assert len(m) == 2 and m[0]['fecha'] == date(2026, 9, 3) and m[0]['numero_operacion'] == '456789'
    assert m[1]['monto'] == Decimal('-12.50')


def test_solo_gerencia_o_permiso(app, admin, vendedor, base):
    assert admin.get('/bancos').status_code == 200
    html = admin.get('/bancos').get_data(as_text=True)
    assert 'Conciliación bancaria' in html and 'data-modulo="bancos"' in html
    r = vendedor.get('/bancos/api/resumen')
    assert r.status_code == 403 and r.json['codigo'] == 'sin_permiso'
    sql("""INSERT INTO erp_modulos (orden, codigo, nombre, estado) SELECT 7, 'FINANZAS', 'Finanzas', 'activo'
           WHERE NOT EXISTS (SELECT 1 FROM erp_modulos WHERE codigo = 'FINANZAS')""")
    sql("""INSERT INTO erp_submodulos (modulo_id, orden, codigo, nombre, estado)
           SELECT m.id, 5, 'CONCILIACION_BANCARIA', 'Bancos', 'activo' FROM erp_modulos m
           WHERE m.codigo = 'FINANZAS' AND NOT EXISTS (SELECT 1 FROM erp_submodulos WHERE codigo = 'CONCILIACION_BANCARIA')""")
    from werkzeug.security import generate_password_hash
    from conftest import _login
    from routes.acceso import limpiar_cache
    uid, _ = _usuario(base, 'bancos_hellen', empresas=('KCF',))
    sql("UPDATE usuarios SET password = %s WHERE id = %s", (generate_password_hash('Banco#2026!'), uid))
    _guardar(admin, uid, base['emp']['KCF'], [{'submodulo_codigo': 'CLIENTES', 'puede_ver': True}])
    limpiar_cache()
    h = _login(app, 'bancos_hellen', 'Banco#2026!')
    assert h.get('/bancos/api/resumen').status_code == 403
    _guardar(admin, uid, base['emp']['KCF'], [{'submodulo_codigo': 'CONCILIACION_BANCARIA', 'puede_ver': True}])
    limpiar_cache()
    assert h.get('/bancos').status_code == 200


def test_subir_y_conciliar_solo(admin, datos):
    eid = datos['eid']
    r = _subir(admin, eid, CSV_BCP.encode('utf-8'))
    assert r.status_code == 200, r.json
    assert r.json['data']['nuevas'] == 6 and r.json['data']['conciliados'] == 3
    d = _resumen(admin, eid)
    por_op = {m['numero_operacion']: m for m in d['movimientos']}
    assert por_op['123456']['estado'] == 'Conciliado' and por_op['123456']['finanzas_pago_id'] == datos['c1']
    assert 'N° de operación' in por_op['123456']['forma']
    assert por_op['000555']['estado'] == 'Conciliado' and por_op['000555']['finanzas_pago_id'] == datos['c2']
    assert 'monto y fecha' in por_op['000555']['forma']
    assert por_op['777001']['finanzas_pago_id'] == datos['p1']
    itf = next(m for m in d['movimientos'] if 'ITF' in m['descripcion'])
    assert itf['estado'] == 'Gasto del banco'
    # En el banco y falta en el ERP: el abono de GAMMA (con su factura sugerida) y el abono desconocido
    pend = {m['numero_operacion']: m for m in d['movimientos'] if m['estado'] == 'Pendiente'}
    assert set(pend) == {'000888', '000999'}
    sug = pend['000888']['sugerencias']
    assert sug and sug[0]['tipo'] == 'factura' and sug[0]['documento'].startswith('F950-') and sug[0]['monto'] == 236
    assert pend['000999']['sugerencias'] == []
    # En el ERP y no está en el banco: el cobro de DELTA (S/ 50)
    assert [p['id'] for p in d['sin_banco']] == [datos['c4']]
    t = d['tarjetas']
    assert t['pendientes_banco'] == 2 and t['pendientes_erp'] == 1 and t['conciliados'] == 3
    assert t['pendientes_banco_entradas'] == 1235.99 and t['gastos_banco'] == -0.05


def test_subir_otra_vez_no_duplica(admin, datos):
    r = _subir(admin, datos['eid'], CSV_BCP.encode('utf-8'))
    assert r.status_code == 200 and r.json['data']['nuevas'] == 0 and r.json['data']['repetidas'] == 6
    assert sql("SELECT COUNT(*) FROM bancos_movimientos WHERE empresa_id = %s", (datos['eid'],))[0][0] == 6


def test_registrar_cobro_desde_el_banco_y_unir(admin, datos):
    eid = datos['eid']
    d = _resumen(admin, eid)
    m = next(x for x in d['movimientos'] if x['numero_operacion'] == '000888')
    r = admin.post('/finanzas/api/movimientos', json={'tipo': 'COBRO', 'documento_id': datos[3], 'monto': 236,
                                                       'fecha': m['fecha'], 'metodo': 'Transferencia', 'banco': 'BCP',
                                                       'numero_operacion': '000888'})
    assert r.status_code == 200, r.json
    # Basta con volver a abrir: se une solo por N° de operación
    d = _resumen(admin, eid)
    m = next(x for x in d['movimientos'] if x['numero_operacion'] == '000888')
    assert m['estado'] == 'Conciliado' and m['tercero_nombre'] == 'COMERCIAL GAMMA S.A.C.'


def test_unir_a_mano_valida_signo_y_diferencia(admin, datos):
    eid = datos['eid']
    d = _resumen(admin, eid)
    m = next(x for x in d['movimientos'] if x['numero_operacion'] == '000999')
    r = admin.post('/bancos/api/conciliar', json={'empresa_id': eid, 'movimiento_id': m['id'], 'pago_id': datos['p1']})
    assert r.status_code == 400 and 'abono' in r.json['error']          # un abono no se une a un pago
    r = admin.post('/bancos/api/conciliar', json={'empresa_id': eid, 'movimiento_id': m['id'], 'pago_id': datos['c4']})
    assert r.status_code == 400 and 'nota' in r.json['error']           # montos distintos sin nota
    r = admin.post('/bancos/api/explicar', json={'empresa_id': eid, 'movimiento_id': m['id'], 'estado': 'Revisado', 'nota': ''})
    assert r.status_code == 400
    r = admin.post('/bancos/api/explicar', json={'empresa_id': eid, 'movimiento_id': m['id'], 'estado': 'Revisado',
                                                 'nota': 'Préstamo de socio'})
    assert r.status_code == 200
    d = _resumen(admin, eid)
    assert d['tarjetas']['pendientes_banco'] == 0


def test_deshacer_pide_motivo_y_no_se_une_solo(admin, datos):
    eid = datos['eid']
    d = _resumen(admin, eid)
    m = next(x for x in d['movimientos'] if x['numero_operacion'] == '123456')
    assert admin.post('/bancos/api/deshacer', json={'empresa_id': eid, 'movimiento_id': m['id'], 'motivo': ''}).status_code == 400
    r = admin.post('/bancos/api/deshacer', json={'empresa_id': eid, 'movimiento_id': m['id'], 'motivo': 'Revisar con Erika'})
    assert r.status_code == 200
    d = _resumen(admin, eid)
    m = next(x for x in d['movimientos'] if x['numero_operacion'] == '123456')
    assert m['estado'] == 'Pendiente' and m['historial'][-1]['accion'] == 'Deshecho'
    assert m['sugerencias'][0]['id'] == datos['c1'] and m['sugerencias'][0]['exacto']
    r = admin.post('/bancos/api/conciliar', json={'empresa_id': eid, 'movimiento_id': m['id'], 'pago_id': datos['c1']})
    assert r.status_code == 200
    m = next(x for x in _resumen(admin, eid)['movimientos'] if x['numero_operacion'] == '123456')
    assert m['estado'] == 'Conciliado' and m['forma'] == 'Manual'


def test_quitar_extracto_solo_admin(admin, vendedor, datos):
    eid = datos['eid']
    ext = _resumen(admin, eid)['extractos']
    vacio = [x for x in ext if x['nuevas'] == 0][0]
    assert admin.post(f'/bancos/api/extracto/{vacio["id"]}/quitar', json={'empresa_id': eid, 'motivo': ''}).status_code == 400
    r = admin.post(f'/bancos/api/extracto/{vacio["id"]}/quitar', json={'empresa_id': eid, 'motivo': 'Subido dos veces'})
    assert r.status_code == 200
    assert len(_resumen(admin, eid)['extractos']) == len(ext) - 1
    # Los cobros y pagos de Finanzas no se tocan
    assert sql("SELECT COUNT(*) FROM finanzas_pagos WHERE id IN %s AND estado <> 'Anulado'",
               ((datos['c1'], datos['c2'], datos['c4'], datos['p1']),))[0][0] == 4
