"""
Pruebas del pedido de Erika del 16/10/2026 (noche) — Ventas:
  - V4: el descuento de la cotización pasa a la PC con el precio por producto ya descontado.
"""
import pytest

from tests.test_inventario import _sql


def _cotizacion(numero, tipo, pct, monto, subtotal):
    cid = _sql("""INSERT INTO cotizaciones (numero_cotizacion, cliente_id, usuario_id, estado, subtotal,
                                            descuento_tipo, descuento_porcentaje, descuento_monto)
                  VALUES (%s, 1, 1, 'Aceptada por Cliente', %s, %s, %s, %s) RETURNING id""",
               (numero, subtotal, tipo, pct, monto))[0][0]
    p1, p2 = [r[0] for r in _sql("SELECT id FROM productos WHERE codigo IN ('PRD-0001','PRD-0002') ORDER BY codigo")]
    _sql("""INSERT INTO cotizacion_detalle (cotizacion_id, producto_id, cantidad, precio_venta_unitario)
            VALUES (%s, %s, 40, 500), (%s, %s, 16, 80)""", (cid, p1, cid, p2))
    return cid


@pytest.mark.parametrize('numero,tipo,pct,monto,neto', [
    ('COT-DESC-S', 'S/', 0, 5000, 16280.00),     # ejemplo real de Erika: S/ 5000 sobre 21280
    ('COT-DESC-P', '%', 10, 2128, 19152.00),     # 10 %
    ('COT-DESC-0', '%', 0, 0, 21280.00),         # sin descuento: no cambia nada
])
def test_descuento_de_cotizacion_pasa_a_la_pc(vendedor, numero, tipo, pct, monto, neto):
    cid = _cotizacion(numero, tipo, pct, monto, 21280)
    r = vendedor.get(f'/ventas/api/cotizaciones/{cid}/completa')
    assert r.status_code == 200, r.json
    d = r.json['data']
    productos = d['productos']
    # El precio de lista se conserva (la edición de la cotización lo usa) ...
    assert sorted(p['valorVenta'] for p in productos) == [80.0, 500.0]
    # ... y la PC recibe el precio ya descontado
    total = sum(p['cantidad'] * p['precio_neto'] for p in productos)
    assert abs(total - neto) < 0.05
    assert abs(d['subtotal_neto'] - neto) < 0.05
    assert abs(d['descuento_total'] - (21280 - neto)) < 0.05


def test_descuento_guardado_desde_pantalla_no_se_aplica_dos_veces(vendedor):
    """Una cotización guardada por el ERP ya trae el precio descontado por línea: la PC lo usa tal cual."""
    from tests.test_flujos import nueva_cotizacion
    d = nueva_cotizacion(vendedor, descuento_valor=10, descuento_tipo='%').json['data']   # 215.00 - 10 %
    c = vendedor.get(f"/ventas/api/cotizaciones/{d['id']}/completa").json['data']
    neto = sum(p['cantidad'] * p['precio_neto'] for p in c['productos'])
    assert abs(neto - 193.50) < 0.05 and abs(c['subtotal_neto'] - 193.50) < 0.05


def test_entrega_por_producto_solo_pendiente_o_entregado(vendedor):
    from tests.test_flujos import nueva_cotizacion
    productos = [{'codigo': 'PRD-0001', 'cantidad': 1, 'valorVenta': 15, 'estado_entrega': 'Entregado'},
                 {'codigo': 'PRD-0002', 'cantidad': 1, 'valorVenta': 32, 'estado_entrega': 'Inmediata'}]
    d = nueva_cotizacion(vendedor, productos=productos).json['data']
    c = vendedor.get(f"/ventas/api/cotizaciones/{d['id']}/completa").json['data']
    estados = {p['codigo']: p['estado_entrega'] for p in c['productos']}
    assert estados == {'PRD-0001': 'Entregado', 'PRD-0002': 'Pendiente'}
