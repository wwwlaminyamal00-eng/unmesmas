"""
Intercompany KCF ↔ AGD (pedido de Erika del 21/10/2026). Datos inventados, solo en la base local.
  - Reconoce solas las ventas entre empresas (cliente con el RUC de la otra empresa).
  - Control cruzado: cada venta debe estar registrada como compra en la otra; si no, sale en rojo.
  - Lo que se deben entre ellas (bruto y neto).
  - Sugerencia legal de desde qué empresa facturar según el IGV del mes.
  - Stock por empresa y total del grupo.
  - Solo gerencia o quien tenga el permiso "Intercompany".
"""
from decimal import Decimal

import pytest

from tests.test_flujos import sql
from tests.test_permisos_usuarios import base, _usuario, _guardar   # noqa: F401  (base es fixture)

PERIODO = '2026-08'
KCF_RUC, AGD_RUC = '20602095704', '20610910671'


@pytest.fixture(scope='module')
def ic(base, admin):
    sql("UPDATE erp_empresas SET ruc = %s WHERE codigo = 'KCF'", (KCF_RUC,))
    sql("UPDATE erp_empresas SET ruc = %s WHERE codigo = 'AGD'", (AGD_RUC,))
    from routes import multiempresa
    multiempresa.empresas(refrescar=True)
    kcf, agd = base['emp']['KCF'], base['emp']['AGD']
    sql("""INSERT INTO comprobantes (tipo_comprobante, serie, numero, fecha_emision, cliente_tipo_doc, cliente_numero_doc,
               cliente_nombre, subtotal, igv, total, items_json, estado_sunat, empresa_id, dias_credito)
           VALUES ('Factura', 'F960', 1, '2026-08-05', 'RUC', %s, 'AGD S.A.C.', 1000, 180, 1180, '[]', 'Emitido', %s, 30),
                  ('Factura', 'F960', 2, '2026-08-10', 'RUC', %s, 'AGD S.A.C.', 500, 90, 590, '[]', 'Emitido', %s, 30),
                  ('Factura', 'E960', 5, '2026-08-12', 'RUC', %s, 'KCF S.A.C.', 200, 36, 236, '[]', 'Emitido', %s, 30),
                  ('Factura', 'F960', 3, '2026-08-15', 'RUC', '20100070970', 'CLIENTE INDUSTRIAL S.A.C.', 300, 54, 354,
                   '[]', 'Emitido', %s, 0)""",
        (AGD_RUC, kcf, AGD_RUC, kcf, KCF_RUC, agd, kcf))
    # AGD registró en Compras solo la F960-1; KCF registró la E960-5 de AGD
    sql("""INSERT INTO comprobantes_proveedor (tipo, numero, fecha, monto, ruc_proveedor, proveedor_nombre, estado, empresa_id)
           VALUES ('Factura', 'F960-00000001', '2026-08-06', 1180, %s, 'KCF S.A.C.', 'Pendiente', %s),
                  ('Factura', 'E960-5', '2026-08-13', 236, %s, 'AGD S.A.C.', 'Pendiente', %s)""",
        (KCF_RUC, agd, AGD_RUC, kcf))
    # Stock: el mismo producto en las dos empresas
    alm = sql("INSERT INTO almacenes (codigo, nombre, activo) VALUES ('IC-SMP', 'SMP intercompany', true) RETURNING id")[0][0]
    prod = sql("SELECT id FROM productos WHERE codigo = 'PRD-0002'")[0][0]
    from routes.inventario import asegurar_tablas_inventario
    asegurar_tablas_inventario()
    sql("""INSERT INTO inv_stock (empresa_id, almacen_id, producto_id, cantidad, costo_promedio, valor)
           VALUES (%s, %s, %s, 10, 20, 200), (%s, %s, %s, 4, 20, 80)
           ON CONFLICT (empresa_id, almacen_id, producto_id) DO UPDATE SET cantidad = inv_stock.cantidad + EXCLUDED.cantidad,
               valor = inv_stock.valor + EXCLUDED.valor""", (kcf, alm, prod, agd, alm, prod))
    return {'kcf': kcf, 'agd': agd}


def _resumen(cliente):
    r = cliente.get(f'/intercompany/api/resumen?periodo={PERIODO}')
    assert r.status_code == 200, r.json
    return r.json['data']


def test_solo_gerencia_o_permiso(app, admin, vendedor, base):
    assert admin.get('/intercompany').status_code == 200
    assert 'data-modulo="intercompany"' in admin.get('/intercompany').get_data(as_text=True)
    r = vendedor.get('/intercompany/api/resumen')
    assert r.status_code == 403 and r.json['codigo'] == 'sin_permiso'
    sql("""INSERT INTO erp_modulos (orden, codigo, nombre, estado) SELECT 7, 'FINANZAS', 'Finanzas', 'activo'
           WHERE NOT EXISTS (SELECT 1 FROM erp_modulos WHERE codigo = 'FINANZAS')""")
    sql("""INSERT INTO erp_submodulos (modulo_id, orden, codigo, nombre, estado)
           SELECT m.id, 6, 'INTERCOMPANY', 'Intercompany', 'activo' FROM erp_modulos m
           WHERE m.codigo = 'FINANZAS' AND NOT EXISTS (SELECT 1 FROM erp_submodulos WHERE codigo = 'INTERCOMPANY')""")
    from werkzeug.security import generate_password_hash
    from conftest import _login
    from routes.acceso import limpiar_cache
    uid, _ = _usuario(base, 'ic_usuario', empresas=('KCF',))
    sql("UPDATE usuarios SET password = %s WHERE id = %s", (generate_password_hash('Inter#2026!'), uid))
    _guardar(admin, uid, base['emp']['KCF'], [{'submodulo_codigo': 'CUENTAS_COBRAR', 'puede_ver': True}])
    limpiar_cache()
    h = _login(app, 'ic_usuario', 'Inter#2026!')
    assert h.get('/intercompany/api/resumen').status_code == 403      # ver Finanzas no basta
    _guardar(admin, uid, base['emp']['KCF'], [{'submodulo_codigo': 'INTERCOMPANY', 'puede_ver': True}])
    limpiar_cache()
    assert h.get('/intercompany').status_code == 200


def test_ventas_entre_empresas_y_control_cruzado(admin, ic):
    d = _resumen(admin)
    docs = {v['documento']: v for v in d['ventas']}
    assert set(docs) == {'F960-1', 'F960-2', 'E960-5'}                    # la venta a un tercero no cuenta
    assert docs['F960-1']['vende'] == 'KCF' and docs['F960-1']['compra'] == 'AGD'
    assert docs['F960-1']['registrada_en_compras'] is True               # "F960-00000001" = "F960-1"
    assert docs['F960-2']['registrada_en_compras'] is False
    assert docs['E960-5']['registrada_en_compras'] is True
    assert d['sin_compra'] == 1
    assert d['totales']['KCF→AGD'] == {'base': 1500.0, 'igv': 270.0, 'total': 1770.0, 'n': 2}
    assert d['totales']['AGD→KCF']['base'] == 200.0
    ago = next(f for f in d['tendencia'] if f['periodo'] == PERIODO)
    assert ago['sentidos'] == {'KCF→AGD': 1500.0, 'AGD→KCF': 200.0}
    assert len(d['tendencia']) == 6


def test_lo_que_se_deben(admin, ic):
    deb = _resumen(admin)['deudas']
    res = {(r['deudor'], r['acreedor']): r for r in deb['resumen']}
    assert res[('AGD', 'KCF')]['saldo'] == 1770.0 and res[('AGD', 'KCF')]['facturas'] == 2
    assert res[('KCF', 'AGD')]['saldo'] == 236.0
    assert deb['netos'] == [{'deudor': 'AGD', 'acreedor': 'KCF', 'saldo': 1534.0}]
    assert all(x['dias_vencido'] > 0 for x in deb['detalle'])            # vencieron en setiembre


def test_sugerencia_desde_donde_facturar():
    from routes.intercompany import sugerencias
    igv = [{'codigo': 'KCF', 'id': 'k', 'igv_pagar': 0, 'credito_libre': 13780.63},
           {'codigo': 'AGD', 'id': 'a', 'igv_pagar': 3000, 'credito_libre': 0}]
    s = sugerencias(igv)
    assert s[0]['vende'] == 'KCF' and s[0]['igv'] == 3000.0 and s[0]['base'] == 16666.67
    assert s[1]['vende'] == 'KCF' and s[1]['compra'] == 'AGD'
    # Las dos pagan: no hay ahorro moviendo ventas
    s = sugerencias([dict(igv[0], igv_pagar=10, credito_libre=0), igv[1]])
    assert len(s) == 1 and s[0]['nivel'] == 'info'
    # Ninguna paga
    s = sugerencias([dict(igv[0]), dict(igv[1], igv_pagar=0)])
    assert s[0]['nivel'] == 'verde'
    # El saldo de una solo cubre parte del IGV de la otra
    s = sugerencias([dict(igv[0], credito_libre=900), igv[1]])
    assert s[0]['igv'] == 900.0 and s[0]['base'] == 5000.0


def test_igv_del_mes_en_resumen(admin, ic):
    d = _resumen(admin)
    igv = {x['codigo']: x for x in d['igv']}
    assert set(igv) == {'KCF', 'AGD'} and 'error' not in igv['KCF']
    assert igv['KCF']['igv_ventas'] >= 324.0                              # 180 + 90 + 54 de agosto
    assert d['sugerencias']


def test_stock_del_grupo(admin, ic):
    r = admin.get('/intercompany/api/stock?q=CASCO')
    assert r.status_code == 200, r.json
    s = r.json['data']
    p = next(x for x in s['productos'] if x['codigo'] == 'PRD-0002')
    assert p['empresas']['KCF'] >= 10 and p['empresas']['AGD'] >= 4
    assert p['total'] == p['empresas']['KCF'] + p['empresas']['AGD']
    emp = {e['codigo']: e for e in s['por_empresa']}
    assert emp['KCF']['valor'] >= 200 and s['valor_grupo'] >= 280


def test_avisos_de_preparacion(admin, ic):
    avisos = _resumen(admin)['avisos']
    assert any(a.startswith('Maestros ▸ Clientes') and 'AGD (RUC 20610910671)' in a for a in avisos)
    assert any(a.startswith('Maestros ▸ Proveedores') and 'KCF (RUC 20602095704)' in a for a in avisos)
