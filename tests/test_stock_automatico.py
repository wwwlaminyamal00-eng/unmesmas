"""
Pruebas del stock automático (pedido de Erika, 15/10/2026):
  - Al despachar se descuenta el stock de la empresa y sede elegidas (kardex: VENTA con el número del despacho).
  - Lo separado para ESE cliente se puede usar; lo separado para otros no.
  - Si falta algo no se despacha nada.
  - Al anular el despacho el stock vuelve y la separación del cliente también.
  - Al anular un comprobante de venta sus cobros en caja se anulan.
"""
import json
import pytest

from tests.test_inventario import _sql
from tests.test_flujos import factura


@pytest.fixture(scope='module')
def sa(app):
    _sql("""
        INSERT INTO erp_empresas (codigo, nombre_corto, nombre_comercial, razon_social, ruc, estado, color_primario, color_secundario, color_pastel)
        SELECT 'KCF', 'KCF', 'KCF', 'KCF S.A.C.', '20111111111', 'activo', '#D6243A', '#1D1A1F', '#FDE8EB' WHERE NOT EXISTS (SELECT 1 FROM erp_empresas WHERE codigo='KCF');
        INSERT INTO erp_empresas (codigo, nombre_corto, nombre_comercial, razon_social, ruc, estado, color_primario, color_secundario, color_pastel)
        SELECT 'AGD', 'AGD', 'AGD', 'AGD S.A.C.', '20222222222', 'activo', '#1D4ED8', '#1D1A1F', '#DBEAFE' WHERE NOT EXISTS (SELECT 1 FROM erp_empresas WHERE codigo='AGD');
        INSERT INTO almacenes (codigo, nombre, direccion, activo)
        SELECT 'SMP', 'San Martín de Porres', 'Av. Perú 123, SMP', true WHERE NOT EXISTS (SELECT 1 FROM almacenes WHERE codigo='SMP');
        INSERT INTO almacenes (codigo, nombre, direccion, activo)
        SELECT 'BRE', 'Breña', 'Jr. Breña 456', true WHERE NOT EXISTS (SELECT 1 FROM almacenes WHERE codigo='BRE');
        INSERT INTO productos (familia, codigo, descripcion, marca, unidad, costo_unitario, precio_unitario, stock, activo) VALUES
            ('GENERAL', 'SA-001', 'CASCO DE SEGURIDAD', 'MSA', 'UND', 30, 50, 0, true),
            ('GENERAL', 'SA-002', 'GUANTE NITRILO', 'ANSELL', 'PAR', 5, 9, 0, true);
    """, fetch=False)
    emp = dict(_sql("SELECT codigo, id FROM erp_empresas WHERE codigo IN ('KCF', 'AGD')"))
    sede = dict(_sql("SELECT codigo, id FROM almacenes WHERE codigo IN ('SMP', 'BRE')"))
    prod = dict(_sql("SELECT codigo, id FROM productos WHERE codigo LIKE 'SA-%'"))
    # Stock: KCF en SMP tiene 10 cascos (4 separados para OTRO cliente) y 20 guantes
    for pid, cant, costo in ((prod['SA-001'], 10, 30), (prod['SA-002'], 20, 5)):
        _sql("""INSERT INTO inv_stock (empresa_id, almacen_id, producto_id, cantidad, costo_promedio, valor)
                VALUES (%s, %s, %s, %s, %s, %s)""", (emp['KCF'], sede['SMP'], pid, cant, costo, cant * costo), fetch=False)
    _sql("""INSERT INTO inv_separaciones (numero, empresa_id, almacen_id, producto_id, cantidad, cantidad_inicial, cliente,
                documento, vence_el) VALUES ('SEP-OTRO', %s, %s, %s, 4, 4, 'OTRO CLIENTE S.A.C.', 'PC-OTRO', CURRENT_DATE + 5)""",
         (emp['KCF'], sede['SMP'], prod['SA-001']), fetch=False)
    _sql("""INSERT INTO inv_separaciones (numero, empresa_id, almacen_id, producto_id, cantidad, cantidad_inicial, cliente,
                documento, vence_el) VALUES ('SEP-MIO', %s, %s, %s, 3, 3, 'CONSTRUCTORA ANDINA S.A.C.', 'PC-SA-0001', CURRENT_DATE + 5)""",
         (emp['KCF'], sede['SMP'], prod['SA-001']), fetch=False)
    items = [{'codigo': 'SA-001', 'producto': 'CASCO DE SEGURIDAD', 'cantidad': 8},
             {'codigo': 'SA-002', 'producto': 'GUANTE NITRILO', 'cantidad': 12}]
    desp = _sql("""INSERT INTO despachos (numero, cliente, ruc, pc_numero, estado, items_json)
                   VALUES ('DES-SA-1', 'CONSTRUCTORA ANDINA S.A.C.', '20555555555', 'PC-SA-0001', 'Pendiente despacho', %s)
                   RETURNING id""", (json.dumps(items),))[0][0]
    return {'emp': emp, 'sede': sede, 'prod': prod, 'desp': desp}


def _stock(sa, codigo):
    f = _sql("SELECT cantidad FROM inv_stock WHERE empresa_id = %s AND almacen_id = %s AND producto_id = %s",
             (sa['emp']['KCF'], sa['sede']['SMP'], sa['prod'][codigo]))
    return float(f[0][0]) if f else 0.0


def test_ubicaciones_dice_donde_alcanza(sa, vendedor):
    r = vendedor.get(f"/ventas/api/despachos/{sa['desp']}/ubicaciones").get_json()
    assert r['success'] and len(r['productos']) == 2
    primera = r['opciones'][0]
    # 10 cascos - 4 de otro cliente = 6 libres para este cliente... pide 8 -> no alcanza en ninguna sede
    assert primera['alcanza'] is False and any(f['producto'] == 'CASCO DE SEGURIDAD' for f in primera['faltan'])


def test_despachar_exige_empresa_y_sede(sa, vendedor):
    r = vendedor.put(f"/ventas/api/despachos/{sa['desp']}/toggle", json={'estado': 'Despachado'})
    assert r.status_code == 400 and r.get_json().get('necesita_ubicacion')


def test_si_falta_stock_no_se_despacha_nada(sa, vendedor):
    r = vendedor.put(f"/ventas/api/despachos/{sa['desp']}/toggle",
                     json={'estado': 'Despachado', 'empresa_id': str(sa['emp']['KCF']), 'almacen_id': sa['sede']['SMP']})
    # 20/10/2026: dice qué producto falta y en qué empresa y sede (para el aviso rojo grande)
    j = r.get_json()
    assert r.status_code == 409 and j['codigo'] == 'falta_stock' and 'No hay stock suficiente' in j['error']
    assert [f['producto'] for f in j['faltan']] == ['CASCO DE SEGURIDAD']
    assert j['faltan'][0]['sede'] and j['faltan'][0]['empresa'] and j['faltan'][0]['pide'] > 0
    assert 'separados para otros clientes' in j['faltan'][0]['detalle']
    # todo o nada: los guantes tampoco salieron y el despacho sigue pendiente
    assert _stock(sa, 'SA-002') == 20 and _stock(sa, 'SA-001') == 10
    assert _sql("SELECT estado FROM despachos WHERE id = %s", (sa['desp'],))[0][0] == 'Pendiente despacho'


def test_despachar_descuenta_y_usa_la_separacion_del_cliente(sa, vendedor):
    # Pide 6 cascos: 3 libres + 3 separados para él (los 4 del otro cliente no se tocan)
    items = [{'codigo': 'SA-001', 'producto': 'CASCO DE SEGURIDAD', 'cantidad': 6},
             {'codigo': 'SA-002', 'producto': 'GUANTE NITRILO', 'cantidad': 12}]
    _sql("UPDATE despachos SET items_json = %s WHERE id = %s", (json.dumps(items), sa['desp']), fetch=False)
    r = vendedor.put(f"/ventas/api/despachos/{sa['desp']}/toggle",
                     json={'estado': 'Despachado', 'empresa_id': str(sa['emp']['KCF']), 'almacen_id': sa['sede']['SMP']})
    assert r.status_code == 200, r.get_json()
    assert 'Se descontó el stock de 2 producto(s)' in r.get_json()['message']
    assert _stock(sa, 'SA-001') == 4 and _stock(sa, 'SA-002') == 8
    assert float(_sql("SELECT stock FROM productos WHERE codigo = 'SA-001'")[0][0]) == 4
    mio = _sql("SELECT cantidad, estado FROM inv_separaciones WHERE numero = 'SEP-MIO'")[0]
    assert float(mio[0]) == 0 and mio[1] == 'Entregada'
    otro = _sql("SELECT cantidad, estado FROM inv_separaciones WHERE numero = 'SEP-OTRO'")[0]
    assert float(otro[0]) == 4 and otro[1] == 'Activa'
    movs = _sql("""SELECT motivo, cantidad, documento_numero, tercero FROM inv_movimientos
                   WHERE despacho_id = %s ORDER BY id""", (sa['desp'],))
    assert [m[0] for m in movs] == ['VENTA', 'VENTA'] and movs[0][2] == 'DES-SA-1'
    assert movs[0][3] == 'CONSTRUCTORA ANDINA S.A.C.'
    d = _sql("SELECT estado, stock_estado FROM despachos WHERE id = %s", (sa['desp'],))[0]
    assert d == ('Despachado', 'Descontado')
    # Pasar a Entregado no vuelve a descontar
    r = vendedor.put(f"/ventas/api/despachos/{sa['desp']}/toggle", json={'estado': 'Entregado'})
    assert r.status_code == 200 and _stock(sa, 'SA-001') == 4


def test_el_kardex_no_deja_corregir_un_movimiento_de_despacho(sa, aprobador):
    mov = _sql("SELECT id FROM inv_movimientos WHERE despacho_id = %s ORDER BY id LIMIT 1", (sa['desp'],))[0][0]
    r = aprobador.post(f'/inventario/api/movimientos/{mov}/revertir', json={'motivo': 'prueba'})
    assert r.status_code == 400 and 'anula el despacho' in r.get_json()['error']


def test_anular_despacho_devuelve_stock_y_separacion(sa, vendedor):
    r = vendedor.delete(f"/ventas/api/despachos/{sa['desp']}", json={'motivo': 'Cliente canceló'})
    assert r.status_code == 200, r.get_json()
    assert 'volvió al inventario' in r.get_json()['message']
    assert _stock(sa, 'SA-001') == 10 and _stock(sa, 'SA-002') == 20
    mio = _sql("SELECT cantidad, estado FROM inv_separaciones WHERE numero = 'SEP-MIO'")[0]
    assert float(mio[0]) == 3 and mio[1] == 'Activa'
    rev = _sql("""SELECT COUNT(*) FROM inv_movimientos WHERE despacho_id = %s AND motivo = 'REVERSA_ENTRADA'""", (sa['desp'],))
    assert rev[0][0] == 2
    assert _sql("SELECT estado, stock_estado FROM despachos WHERE id = %s", (sa['desp'],))[0] == ('Anulado', 'Revertido')
    # Anular otra vez o despachar un anulado no hace nada
    assert vendedor.delete(f"/ventas/api/despachos/{sa['desp']}").status_code == 409
    assert _stock(sa, 'SA-001') == 10


def test_anular_comprobante_anula_sus_cobros_en_caja(vendedor, admin):
    cid = factura(vendedor, total=236, subtotal=200, igv=36).get_json()['data']['id']
    vendedor.put(f'/ventas/api/comprobantes/{cid}/toggle', json={'estado': 'Emitido'})
    r = admin.post('/finanzas/api/movimientos', json={'tipo': 'COBRO', 'documento_id': cid, 'monto': 100,
                                                      'metodo': 'Transferencia', 'fecha_aviso': '2026-10-21'})
    assert r.status_code == 200, r.get_json()
    r = vendedor.put(f'/ventas/api/comprobantes/{cid}/toggle', json={'estado': 'Anulado'})
    assert r.status_code == 200 and '1 cobro(s)' in r.get_json()['message']
    estado, motivo = _sql("SELECT estado, motivo_anulacion FROM finanzas_pagos WHERE documento_id = %s "
                          "AND documento_tabla = 'comprobantes'", (cid,))[0]
    assert estado == 'Anulado' and 'comprobante fue anulado' in motivo
