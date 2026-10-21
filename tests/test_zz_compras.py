"""
Pruebas de los arreglos de Compras (16/10): filtros de las listas, compra sin pedido con motivo obligatorio,
la OC guarda su PC / cotización / cliente / motivo, la orden del proveedor no muestra al cliente,
Cuentas por pagar ordenadas (vencido > por vencer > al día), candados de anular/eliminar (solo admin y con motivo),
autollenado del proveedor desde proveedores_contactos y la tabla resumen pedido / stock / comprar.
Datos inventados, solo en la base local de pruebas.
"""
import json
from datetime import date, timedelta

import pytest
from werkzeug.security import generate_password_hash

from tests.conftest import _login
from tests.test_inventario import _sql

CLIENTE = 'CLIENTE CONFIDENCIAL ZZ S.A.C.'
PC_NUM = 'PC-ZZ-20261016-0001'
COT_NUM = 'COT-ZZ-0077'


@pytest.fixture(scope='module')
def zz(app, admin):
    _sql("""
        INSERT INTO erp_empresas (codigo, nombre_corto, nombre_comercial, razon_social, ruc, estado, color_primario, color_secundario, color_pastel)
        SELECT 'KCF', 'KCF', 'KCF', 'KCF S.A.C.', '20111111111', 'activo', '#D6243A', '#1D1A1F', '#FDE8EB'
        WHERE NOT EXISTS (SELECT 1 FROM erp_empresas WHERE codigo = 'KCF');
        INSERT INTO almacenes (codigo, nombre, direccion, activo)
        SELECT 'SMP', 'San Martín de Porres', 'Av. Perú 123, SMP', true WHERE NOT EXISTS (SELECT 1 FROM almacenes WHERE codigo = 'SMP');
        INSERT INTO productos (familia, codigo, descripcion, marca, unidad, costo_unitario, precio_unitario, stock, activo) VALUES
            ('GENERAL', 'ZZC-001', 'BOTA DE SEGURIDAD ZZ', 'ZZ', 'PAR', 0, 120, 0, true),
            ('GENERAL', 'ZZC-002', 'LENTE DE SEGURIDAD ZZ', 'ZZ', 'UND', 0, 15, 0, true);
        INSERT INTO proveedores (razon_social, ruc, direccion, condicion_pago, activo)
        VALUES ('DISTRIBUIDORA ZZ S.A.C.', '20777777777', 'Av. Fiscal 777, Lima', 'Contado', true);
    """, fetch=False)
    prov = _sql("SELECT id FROM proveedores WHERE ruc = '20777777777'")[0][0]
    _sql("""INSERT INTO proveedores_contactos (proveedor_id, nombre_contacto, cargo, telefono, email, principal, activo) VALUES
            (%s, 'Contacto Secundario', 'Almacén', '011111111', 'otro@zz.pe', false, true),
            (%s, 'Rosa Ventas', 'Ventas', '987654321', 'rosa@zz.pe', true, true)""", (prov, prov), fetch=False)
    _sql("""INSERT INTO usuarios (usuario_sistema, usuario, nombres_apellidos, nombre_completo, correo, password, rol, estado)
            VALUES ('compra7', 'compra7', 'Compradora Siete', 'Compradora Siete', 'c7@t.pe', %s, 'compras', 'activo')""",
         (generate_password_hash('Clave#2026!'),), fetch=False)
    prod = dict(_sql("SELECT codigo, id FROM productos WHERE codigo LIKE 'ZZC-%'"))
    items = [{'codigo': 'ZZC-001', 'producto': 'BOTA DE SEGURIDAD ZZ', 'cantidad_pc': 40, 'precio_pc': 120}]
    pc = _sql("""INSERT INTO pedido_compra_pc (numero, cliente, ruc, estado, items_json, fecha, cotizacion_numero)
                 VALUES (%s, %s, '20888888888', 'Pendiente', %s, NOW(), %s) RETURNING id""",
              (PC_NUM, CLIENTE, json.dumps(items), COT_NUM))[0][0]
    emp = _sql("SELECT id FROM erp_empresas WHERE codigo = 'KCF'")[0][0]
    sede = _sql("SELECT id FROM almacenes WHERE codigo = 'SMP'")[0][0]
    return {'prov': prov, 'pc': pc, 'BOTA': prod['ZZC-001'], 'LENTE': prod['ZZC-002'], 'emp': emp, 'sede': sede,
            'compra': _login(app, 'compra7', 'Clave#2026!')}


def _oc_flujo(zz, **extra):
    body = {'empresa_id': zz['emp'], 'proveedor_id': zz['prov'], 'almacen_entrega_id': zz['sede'],
            'condicion_pago': 'Contado', 'modalidad_entrega': 'Proveedor entrega', 'fecha_compromiso': '2026-10-20',
            'items': [{'producto_id': zz['LENTE'], 'cantidad': 10, 'precio_unitario': 9}]}
    body.update(extra)
    return body


def _oc_legacy(admin, **extra):
    payload = {'proveedor': 'DISTRIBUIDORA ZZ S.A.C.', 'ruc': '20777777777', 'estado': 'Borrador',
               'condicion_pago': 'Contado', 'items': [{'producto': 'LENTE DE SEGURIDAD ZZ', 'cantidad': 3, 'precioUnitario': 9}]}
    payload.update(extra)
    return admin.post('/compras/api/ordenes/guardar', json=payload)


# ---------- Bug 1: filtros de las pantallas anteriores (API) ----------
def test_filtros_de_las_listas_anteriores(zz, admin):
    a = _oc_legacy(admin, motivo_compra='Stock estratégico').json['data']
    b = _oc_legacy(admin, motivo_compra='Crédito fiscal / IGV', estado='Emitida').json['data']
    todas = admin.get('/compras/api/ordenes/listar').json['data']
    fila = next(o for o in todas if o['id'] == a['id'])
    assert len(fila['fecha']) == 10 and fila['fecha'][4] == '-'           # AAAA-MM-DD, sin zona horaria
    assert len(fila['creado']) == 16 and fila['creado'][2] == '/'        # DD/MM/YYYY HH:MM
    r = admin.get('/compras/api/ordenes/listar', query_string={'q': a['numero_orden']}).json['data']
    assert [o['id'] for o in r] == [a['id']]
    r = admin.get('/compras/api/ordenes/listar', query_string={'estado': 'Emitida'}).json['data']
    assert b['id'] in [o['id'] for o in r] and all(o['estado'] == 'Emitida' for o in r)
    hoy = fila['fecha']
    manana = (date.fromisoformat(hoy) + timedelta(days=1)).isoformat()
    assert a['id'] in [o['id'] for o in admin.get('/compras/api/ordenes/listar', query_string={'desde': hoy, 'hasta': hoy}).json['data']]
    assert admin.get('/compras/api/ordenes/listar', query_string={'desde': manana}).json['data'] == []
    # solicitudes: búsqueda por texto
    admin.post('/compras/api/solicitudes/guardar', json={'producto': 'TORNILLO ZZ UNICO', 'cantidad': 2, 'area': 'Almacén', 'solicitante': 'Prueba'})
    r = admin.get('/compras/api/solicitudes/listar', query_string={'q': 'tornillo zz unico'}).json['data']
    assert len(r) == 1 and r[0]['producto'] == 'TORNILLO ZZ UNICO'


# ---------- Compra sin pedido: motivo obligatorio de la lista ----------
def test_oc_sin_pedido_exige_motivo(zz, admin):
    assert _oc_legacy(admin).status_code == 400
    assert _oc_legacy(admin, motivo_compra='Me dio la gana').status_code == 400       # no está en la lista
    assert _oc_legacy(admin, motivo_compra='Otro').status_code == 400                 # "Otro" pide texto
    assert _oc_legacy(admin, motivo_compra='Otro', motivo_stock='Oferta del proveedor').status_code == 200
    r = admin.post('/compras/api/flujo/ordenes', json=_oc_flujo(zz))
    assert r.status_code == 400 and 'motivo' in r.json['error']
    r = admin.post('/compras/api/flujo/ordenes', json=_oc_flujo(zz, motivo_compra='Reposición de stock mínimo'))
    assert r.status_code == 200, r.json
    det = admin.get(f"/compras/api/flujo/ordenes/{r.json['id']}").json['data']
    assert det['motivo_compra'] == 'Reposición de stock mínimo' and det['sin_pedido'] is True
    lista = admin.get('/compras/api/flujo/ordenes', query_string={'sin_pedido': '1', 'estado': ''}).json['data']
    assert r.json['id'] in [o['id'] for o in lista] and all(o['sin_pedido'] for o in lista)


# ---------- La OC guarda su PC, cotización, cliente y motivo ----------
def test_oc_guarda_pc_cotizacion_cliente(zz, admin):
    r = _oc_legacy(admin, pedido_id=zz['pc'])
    assert r.status_code == 200, r.json
    fila = next(o for o in admin.get('/compras/api/ordenes/listar').json['data'] if o['id'] == r.json['data']['id'])
    assert fila['pc_numeros'] == PC_NUM and fila['clientes_pedido'] == CLIENTE and fila['cotizaciones_cliente'] == COT_NUM
    assert not fila['sin_pedido'] and not fila['motivo_compra']
    # pantalla nueva: línea del pedido + línea para stock (motivo)
    body = _oc_flujo(zz, motivo_compra='Stock estratégico', items=[
        {'producto_id': zz['BOTA'], 'cantidad': 30, 'precio_unitario': 80, 'pedido_id': zz['pc']},
        {'producto_id': zz['BOTA'], 'cantidad': 100, 'precio_unitario': 80}])
    r = admin.post('/compras/api/flujo/ordenes', json=body)
    assert r.status_code == 200, r.json
    zz['oc_pedido'] = r.json['id']
    det = admin.get(f"/compras/api/flujo/ordenes/{r.json['id']}").json['data']
    assert PC_NUM in det['pc_numeros'] and CLIENTE in det['clientes_pedido'] and COT_NUM in det['cotizaciones_cliente']
    assert det['motivo_compra'] == 'Stock estratégico'
    assert any(i['cotizacion_numero'] == COT_NUM for i in det['items'] if i['pedido_id'])


# ---------- La orden que se manda al proveedor no muestra al cliente ----------
def test_impresion_para_proveedor_sin_cliente(zz, admin):
    oc_id = zz.get('oc_pedido')
    assert oc_id, 'depende de test_oc_guarda_pc_cotizacion_cliente'
    assert admin.get(f'/compras/flujo/ordenes/{oc_id}/imprimir').status_code == 409    # sin aprobar no se envía
    r = admin.get(f'/compras/flujo/ordenes/{oc_id}/imprimir', query_string={'hoja': 'borrador'})
    assert r.status_code == 200
    html = r.data.decode('utf-8')
    assert 'BOTA DE SEGURIDAD ZZ' in html and 'DISTRIBUIDORA ZZ' in html
    # 20/10/2026 22:54 Erika pidió que la OC diga a qué PC pertenece: el N° de PC sí sale, el cliente nunca
    assert f'Relacionado al PC: <b>{PC_NUM}</b>' in html
    for secreto in (CLIENTE, COT_NUM, 'Stock estratégico'):
        assert secreto not in html, secreto
    # vista previa de una OC de la pantalla anterior con pedido
    oc = _oc_legacy(admin, pedido_id=zz['pc']).json['data']
    r = admin.get(f"/compras/orden/{oc['id']}/preview")
    assert r.status_code == 200
    html = r.data.decode('utf-8')
    assert 'LENTE DE SEGURIDAD ZZ' in html and CLIENTE not in html and f'Relacionado al PC: <b>{PC_NUM}</b>' in html


# ---------- Cuentas por pagar ordenadas y con totales ----------
def test_cxp_ordenada_vencido_por_vencer_al_dia(zz, admin):
    hoy = date.today()
    casos = {'ZZ-V20': -20, 'ZZ-V3': -3, 'ZZ-P2': 2, 'ZZ-P5': 5, 'ZZ-A30': 30}
    for num, dias in casos.items():
        r = admin.post('/compras/api/comprobantes-proveedor/guardar', json={
            'tipo': 'Factura', 'numero': num, 'monto': 100, 'ruc': '20777777777',
            'proveedor': 'DISTRIBUIDORA ZZ S.A.C.', 'fecha': (hoy - timedelta(days=30)).isoformat()})
        assert r.status_code == 200, r.json
        _sql("UPDATE comprobantes_proveedor SET fecha_vencimiento = %s WHERE numero = %s",
             (hoy + timedelta(days=dias), num), fetch=False)
    r = admin.get('/finanzas/api/cxp', query_string={'estado': 'pendientes'}).json
    docs = [x['documento'] for x in r['data'] if x['documento'] in casos]
    assert docs == ['ZZ-V20', 'ZZ-V3', 'ZZ-P2', 'ZZ-P5', 'ZZ-A30']
    por = {x['documento']: x for x in r['data']}
    assert por['ZZ-V20']['semaforo'] == 'Vencido' and por['ZZ-V20']['dias_vencido'] == 20
    assert por['ZZ-P2']['semaforo'] == 'Por vencer' and por['ZZ-P2']['dias_para_vencer'] == 2
    assert por['ZZ-A30']['semaforo'] == 'Al día'
    sem = [x['semaforo'] for x in r['data']]
    assert sem == sorted(sem, key=['Vencido', 'Por vencer', 'Al día', 'Pagado'].index)   # todo el listado en ese orden
    t = r['totales']
    assert t['vencido'] >= 200 and t['por_vencer'] >= 200 and t['al_dia'] >= 100 and t['docs_vencidos'] >= 2
    assert t['total'] == pytest.approx(t['vencido'] + t['por_vencer'] + t['al_dia'])


# ---------- Candados: anular / eliminar solo admin y con motivo ----------
def test_eliminar_solicitud_solo_admin_con_motivo(zz, admin, vendedor):
    sid = admin.post('/compras/api/solicitudes/guardar', json={'producto': 'SOLICITUD A BORRAR ZZ', 'cantidad': 1}).json['data']['id']
    assert vendedor.delete(f'/compras/api/solicitudes/{sid}', json={'motivo': 'ya no se necesita'}).status_code == 403
    assert admin.delete(f'/compras/api/solicitudes/{sid}', json={}).status_code == 400
    assert admin.delete(f'/compras/api/solicitudes/{sid}', json={'motivo': 'duplicada por error'}).status_code == 200
    assert _sql("SELECT COUNT(*) FROM solicitudes_compra WHERE id = %s", (sid,))[0][0] == 0
    anul = _sql("SELECT motivo, accion, respaldo FROM com_anulaciones WHERE tabla = 'solicitudes_compra' AND registro_id = %s", (sid,))
    assert anul and anul[0][0] == 'duplicada por error' and anul[0][1] == 'Eliminada' and anul[0][2]   # queda respaldo


def test_anular_y_eliminar_oc_solo_admin(zz, admin, vendedor):
    oc = _oc_legacy(admin, motivo_compra='Stock estratégico', estado='Emitida').json['data']
    assert vendedor.put(f"/compras/api/ordenes/{oc['id']}/toggle", json={'estado': 'Anulada', 'motivo': 'error de precio'}).status_code == 403
    assert admin.put(f"/compras/api/ordenes/{oc['id']}/toggle", json={'estado': 'Anulada'}).status_code == 400
    assert admin.put(f"/compras/api/ordenes/{oc['id']}/toggle", json={'estado': 'Anulada', 'motivo': 'error de precio'}).status_code == 200
    assert _sql("SELECT estado, motivo_anulacion FROM ordenes_compra WHERE id = %s", (oc['id'],))[0] == ('Anulada', 'error de precio')
    assert vendedor.delete(f"/compras/api/ordenes/{oc['id']}", json={'motivo': 'limpieza'}).status_code == 403
    assert admin.delete(f"/compras/api/ordenes/{oc['id']}", json={'motivo': 'limpieza de prueba'}).status_code == 200
    assert _sql("SELECT COUNT(*) FROM com_anulaciones WHERE tabla = 'ordenes_compra' AND registro_id = %s", (oc['id'],))[0][0] == 2
    # pantalla nueva: Compras (no supervisora/admin) no puede anular
    # cantidad distinta: una OC idéntica a otra activa ya no se puede crear (20/10/2026 22:54)
    oc2 = admin.post('/compras/api/flujo/ordenes', json=_oc_flujo(zz, motivo_compra='Stock estratégico',
                     items=[{'producto_id': zz['LENTE'], 'cantidad': 13, 'precio_unitario': 9}])).json['id']
    assert zz['compra'].post(f'/compras/api/flujo/ordenes/{oc2}/anular', json={'motivo': 'ya no va'}).status_code == 403
    assert admin.post(f'/compras/api/flujo/ordenes/{oc2}/anular', json={'motivo': 'ya no va'}).status_code == 200
    assert _sql("SELECT COUNT(*) FROM com_anulaciones WHERE tabla = 'ordenes_compra' AND registro_id = %s", (oc2,))[0][0] == 1


def test_anular_comprobante_solo_admin_con_motivo(zz, admin, vendedor):
    r = admin.post('/compras/api/comprobantes-proveedor/guardar', json={
        'tipo': 'Factura', 'numero': 'ZZ-ANUL-1', 'monto': 50, 'ruc': '20777777777',
        'proveedor': 'DISTRIBUIDORA ZZ S.A.C.', 'fecha': '2026-10-01'})
    cid = _sql("SELECT id FROM comprobantes_proveedor WHERE numero = 'ZZ-ANUL-1'")[0][0]
    assert vendedor.delete(f'/compras/api/comprobantes-proveedor/{cid}', json={'motivo': 'mal registrado'}).status_code == 403
    assert vendedor.put(f'/compras/api/comprobantes-proveedor/{cid}/toggle', json={'estado': 'Anulado', 'motivo': 'mal registrado'}).status_code == 403
    assert admin.delete(f'/compras/api/comprobantes-proveedor/{cid}', json={}).status_code == 400
    assert admin.delete(f'/compras/api/comprobantes-proveedor/{cid}', json={'motivo': 'mal registrado'}).status_code == 200
    assert _sql("SELECT estado FROM comprobantes_proveedor WHERE id = %s", (cid,))[0][0] == 'Anulado'   # no se borra
    assert all(x['id'] != cid for x in admin.get('/finanzas/api/cxp', query_string={'estado': 'todos'}).json['data'])


# ---------- Autollenado del proveedor (proveedores + proveedores_contactos) ----------
def test_proveedor_autollena_con_contacto_principal(zz, admin):
    r = admin.get('/compras/api/proveedores/buscar', query_string={'q': '20777777777'}).json['data']
    p = r[0]
    assert p['razon_social'] == 'DISTRIBUIDORA ZZ S.A.C.' and p['direccion'] == 'Av. Fiscal 777, Lima'
    assert p['telefono'] == '987654321' and p['contacto'] == 'Rosa Ventas' and p['email'] == 'rosa@zz.pe'
    cat = admin.get('/compras/api/flujo/catalogos').json
    p = next(x for x in cat['proveedores'] if x['id'] == zz['prov'])
    assert p['telefono'] == '987654321' and p['contacto'] == 'Rosa Ventas' and p['direccion'] == 'Av. Fiscal 777, Lima'
    assert cat['motivos_sin_pedido'] == ['Stock estratégico', 'Crédito fiscal / IGV', 'Reposición de stock mínimo', 'Otro']


# ---------- Tabla resumen: comprar para pedido = pedido − stock de la empresa ----------
def test_pedido_resumen_descuenta_stock_de_la_empresa(zz, admin):
    pc = next(p for p in admin.get('/compras/api/flujo/pedidos', query_string={'todos': '1'}).json['data'] if p['id'] == zz['pc'])
    emp = pc['empresa_id'] or zz['emp']   # UUID o entero según el esquema
    _sql("""INSERT INTO inv_stock (empresa_id, almacen_id, producto_id, cantidad) VALUES (%s, %s, %s, 10)
            ON CONFLICT (empresa_id, almacen_id, producto_id) DO UPDATE SET cantidad = 10""",
         (emp, zz['sede'], zz['BOTA']), fetch=False)
    # Se crea otro pedido de 40 para no depender de lo ya comprado en las pruebas anteriores
    items = [{'codigo': 'ZZC-001', 'producto': 'BOTA DE SEGURIDAD ZZ', 'cantidad_pc': 40, 'precio_pc': 120}]
    pc2 = _sql("""INSERT INTO pedido_compra_pc (numero, cliente, ruc, estado, items_json, fecha)
                  VALUES ('PC-ZZ-20261016-0002', 'OTRO CLIENTE ZZ', '20999999999', 'Pendiente', %s, NOW()) RETURNING id""",
               (json.dumps(items),))[0][0]
    p = next(x for x in admin.get('/compras/api/flujo/pedidos').json['data'] if x['id'] == pc2)
    it = p['items'][0]
    assert it['cantidad'] == 40 and it['falta'] == 40
    assert it['stock_empresa'] == 10 and it['comprar_pedido'] == 30          # ejemplo de Erika: 40 / 10 / 30
