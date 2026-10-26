"""
Pruebas del pedido de Erika del 16/10/2026 ("CORRECCIÓN DE 13 BUGS EN PRODUCCIÓN"), parte Ventas / Inventario:
  - PV: editar guarda sobre el MISMO PV (fecha, condición de pago, interruptor "Producto") y ya no queda
    siempre "PC observado" porque la pantalla no manda el margen.
  - Despacho hecho desde Cotizaciones: se vincula solo a su PV y lleva sus productos.
  - Editar un despacho no crea otro.
  - productos.stock = suma de inv_stock, mantenido por la base (trigger).
  - Hora de Perú en la base y en Python.
  - Consulta de RUC: primero el ERP; si el servicio externo pide pago (402) el mensaje es claro.
"""
import json
from datetime import datetime

import pytest
import requests

from tests.test_inventario import _sql


def _pc(http, **extra):
    data = {'numero': 'PC-BUG-' + extra.pop('sufijo', '1'), 'fecha': '2026-10-10 09:30:00', 'cliente': 'CLIENTE PRUEBA SAC',
            'ruc': '20100070970', 'monto': 100, 'condicion_pago': 'Crédito 30 días', 'lugar_entrega': 'Av. Lima 1',
            'items': [{'codigo': 'PRD-0001', 'producto': 'GUANTE DE NITRILO', 'cantidad_pc': 5, 'precio_pc': 15, 'stock': 0}],
            'valida_precios': True, 'valida_cantidades': True, 'valida_entrega': True, 'valida_montos': True,
            'valida_transporte': True, 'valida_vigencia': True, 'valida_productos': True,
            'estado': 'PC conforme', 'req_compra': 'Sí'}
    data.update(extra)
    return http.post('/ventas/api/pedido-compra/guardar', json=data)


def test_pc_conforme_sin_interruptor_de_margen(vendedor):
    r = _pc(vendedor, sufijo='M1')
    assert r.status_code == 200, r.json
    estado, req = _sql("SELECT estado, req_compra FROM pedido_compra_pc WHERE id = %s", (r.json['data']['id'],))[0]
    assert estado == 'PC conforme' and req == 'Sí'


def test_editar_pc_guarda_sobre_el_mismo(vendedor):
    r = _pc(vendedor, sufijo='E1')
    pid = r.json['data']['id']
    antes = _sql("SELECT count(*) FROM pedido_compra_pc")[0][0]
    r2 = _pc(vendedor, sufijo='E1', id=pid, fecha='2026-10-12 16:45:00', fecha_recepcion='2026-10-12',
             condicion_pago='Crédito 60 días', valida_productos=False)
    assert r2.status_code == 200, r2.json
    assert _sql("SELECT count(*) FROM pedido_compra_pc")[0][0] == antes
    fecha, frec, cond, vprod = _sql("""SELECT fecha, fecha_recepcion, condicion_pago, valida_productos
                                       FROM pedido_compra_pc WHERE id = %s""", (pid,))[0]
    assert fecha == datetime(2026, 10, 12, 16, 45) and str(frec)[:10] == '2026-10-12'
    assert cond == 'Crédito 60 días' and vprod is False
    d = vendedor.get(f'/ventas/api/pedido-compra/{pid}').json['data']
    assert d['valida_productos'] is False and d['condicion_pago'] == 'Crédito 60 días'


def test_despacho_desde_cotizacion_se_vincula_a_su_pc(vendedor):
    cid = _sql("""INSERT INTO cotizaciones (numero_cotizacion, cliente_id, usuario_id, estado, total)
                  VALUES ('COT-BUG-0001', '1', 1, 'Aceptada por Cliente', 100) RETURNING id""")[0][0]
    r = _pc(vendedor, sufijo='D1', cotizacion_id=cid, cotizacion_numero='COT-BUG-0001')
    pc_id = r.json['data']['id']
    # Así guardaba la pantalla de "Crear despacho" desde Cotizaciones: sin PV ni productos
    d = vendedor.post('/ventas/api/despachos/guardar', json={'cotizacion_numero': 'COT-BUG-0001',
                                                             'cliente': 'CLIENTE PRUEBA SAC', 'estado': 'Pendiente despacho'})
    assert d.status_code == 200, d.json
    did = d.json['data'][0]['id']
    pc_id2, pc_num, cot_id, items = _sql("SELECT pc_id, pc_numero, cotizacion_id, items_json FROM despachos WHERE id = %s", (did,))[0]
    assert pc_id2 == pc_id and pc_num == 'PC-BUG-D1' and cot_id == cid
    items = items if isinstance(items, list) else json.loads(items)
    assert items[0]['codigo'] == 'PRD-0001' and items[0]['cantidad'] == 5


def test_editar_despacho_no_crea_otro(vendedor):
    d = vendedor.post('/ventas/api/despachos/guardar', json={'cliente': 'X SAC', 'ruc': '20100070970', 'destino': 'A'})
    did = d.json['data'][0]['id']
    antes = _sql("SELECT count(*) FROM despachos")[0][0]
    r = vendedor.post('/ventas/api/despachos/guardar', json={'id': did, 'destino': 'Nuevo destino', 'transportista': 'T1'})
    assert r.status_code == 200, r.json
    assert _sql("SELECT count(*) FROM despachos")[0][0] == antes
    assert _sql("SELECT destino, transportista FROM despachos WHERE id = %s", (did,))[0] == ('Nuevo destino', 'T1')


def test_stock_producto_es_suma_de_inventario(app, admin):
    admin.get('/inventario/api/kardex')   # crea las tablas y los triggers del inventario
    _sql("""INSERT INTO erp_empresas (codigo, nombre_corto, nombre_comercial, razon_social, ruc, estado, color_primario, color_secundario, color_pastel)
            SELECT 'KCF', 'KCF', 'KCF', 'KCF S.A.C.', '20111111111', 'activo', '#D6243A', '#1D1A1F', '#FDE8EB' WHERE NOT EXISTS (SELECT 1 FROM erp_empresas WHERE codigo='KCF');
            INSERT INTO erp_empresas (codigo, nombre_corto, nombre_comercial, razon_social, ruc, estado, color_primario, color_secundario, color_pastel)
            SELECT 'AGD', 'AGD', 'AGD', 'AGD S.A.C.', '20222222222', 'activo', '#1D4ED8', '#1D1A1F', '#DBEAFE' WHERE NOT EXISTS (SELECT 1 FROM erp_empresas WHERE codigo='AGD');
            INSERT INTO almacenes (codigo, nombre, direccion, activo)
            SELECT 'SMP', 'San Martín de Porres', 'Av. Perú 123', true WHERE NOT EXISTS (SELECT 1 FROM almacenes WHERE codigo='SMP');
            INSERT INTO productos (familia, codigo, descripcion, unidad, stock, activo) VALUES ('GENERAL', 'TRG-001', 'PRUEBA TRIGGER', 'UND', 0, true);""",
         fetch=False)
    emp = dict(_sql("SELECT codigo, id FROM erp_empresas WHERE codigo IN ('KCF', 'AGD')"))
    sede = _sql("SELECT id FROM almacenes WHERE codigo = 'SMP'")[0][0]
    pid = _sql("SELECT id FROM productos WHERE codigo = 'TRG-001'")[0][0]
    _sql("INSERT INTO inv_stock (empresa_id, almacen_id, producto_id, cantidad) VALUES (%s, %s, %s, 25)", (emp['KCF'], sede, pid), fetch=False)
    _sql("INSERT INTO inv_stock (empresa_id, almacen_id, producto_id, cantidad) VALUES (%s, %s, %s, 7)", (emp['AGD'], sede, pid), fetch=False)
    assert _sql("SELECT stock FROM productos WHERE id = %s", (pid,))[0][0] == 32
    _sql("UPDATE inv_stock SET cantidad = 5 WHERE producto_id = %s AND empresa_id = %s", (pid, emp['AGD']), fetch=False)
    assert _sql("SELECT stock FROM productos WHERE id = %s", (pid,))[0][0] == 30
    # Escribirlo a mano no lo descuadra: la base vuelve a poner la suma
    _sql("UPDATE productos SET stock = 999 WHERE id = %s", (pid,), fetch=False)
    assert _sql("SELECT stock FROM productos WHERE id = %s", (pid,))[0][0] == 30
    _sql("DELETE FROM inv_stock WHERE producto_id = %s AND empresa_id = %s", (pid, emp['AGD']), fetch=False)
    assert _sql("SELECT stock FROM productos WHERE id = %s", (pid,))[0][0] == 25
    # Y lo que ve Ventas / Productos es ese mismo total, sin decimales
    filas = admin.get('/productos/api/productos').json['data']
    fila = next(p for p in filas if p['codigo'] == 'TRG-001')
    assert fila['stock'] == 25 and isinstance(fila['stock'], int)


def test_hora_de_peru(app):
    from database import get_connection
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT current_setting('TimeZone')")
    assert cur.fetchone()[0] == 'America/Lima'
    conn.close()
    import time
    assert time.strftime('%z') == '-0500'


def test_ruc_primero_busca_en_el_erp(admin, monkeypatch):
    def no_llamar(*a, **k):
        raise AssertionError('no debía consultar afuera')
    monkeypatch.setattr(requests, 'get', no_llamar)
    r = admin.get('/api/sunat/consulta?ruc=20100070970').json
    assert r['success'] and r['razon_social'] == 'CLIENTE INDUSTRIAL S.A.C.' and r['fuente'] == 'erp_cliente'


def test_ruc_servicio_pide_pago_mensaje_claro(admin, monkeypatch):
    class R:
        status_code = 402
        def json(self):
            return {}
    monkeypatch.setattr(requests, 'get', lambda *a, **k: R())
    r = admin.get('/api/sunat/consulta?ruc=20999999999').json
    assert r['success'] is False and r['manual'] is True
    assert 'Código 402' not in r['error'] and 'a mano' in r['error']
