"""
Erika 28/10/2026 17:23: hasta 3 cuentas por proveedor y regla de ahorro (KCF paga a BBVA, AGD a BCP; si el proveedor
no tiene, la siguiente cuenta con aviso en rojo). Botón "Crear OC - Orden de compra (Proveedor)". Datos inventados,
solo en la base local.
"""
from pathlib import Path

from tests.test_inventario import _sql

RAIZ = Path(__file__).resolve().parent.parent
RUC = '20999281028'


def _limpiar():
    _sql("DELETE FROM proveedores_contactos WHERE proveedor_id IN (SELECT id FROM proveedores WHERE ruc = %s)", (RUC,), fetch=False)
    _sql("DELETE FROM proveedores_puntos_entrega WHERE proveedor_id IN (SELECT id FROM proveedores WHERE ruc = %s)", (RUC,), fetch=False)
    _sql("DELETE FROM proveedores WHERE ruc = %s", (RUC,), fetch=False)


def test_regla_kcf_bbva_agd_bcp_y_siguiente(app):
    from routes import cuentas_proveedor as cp
    p = {'banco': 'Interbank', 'numero_cuenta': '111', 'cci': '0031', 'moneda': 'Soles',
         'banco2': 'BCP', 'numero_cuenta2': '222', 'cci2': '0022', 'moneda_cuenta2': 'PEN',
         'banco3': 'bbva continental', 'numero_cuenta3': '333', 'cci3': '0011', 'moneda_cuenta3': 'PEN'}
    with app.app_context():
        kcf = cp.cuenta_preferida(p, 'KCF')
        assert kcf['banco'] == 'BBVA' and kcf['numero_cuenta'] == '333' and kcf['mismo_banco']
        agd = cp.cuenta_preferida(p, 'AGD')
        assert agd['banco'] == 'BCP' and agd['cci'] == '0022' and '✅' in agd['aviso']
        # Sin cuenta del banco de la empresa: la siguiente (la 1), con aviso de comisión
        solo = {'banco': 'Interbank', 'numero_cuenta': '111', 'banco2': 'Scotiabank', 'numero_cuenta2': '444'}
        r = cp.cuenta_preferida(solo, 'KCF')
        assert r['orden'] == 1 and not r['mismo_banco'] and 'comisión' in r['aviso'] and 'BBVA' in r['aviso']
        # Dos cuentas BBVA: gana la de la moneda del documento
        dos = {'banco': 'BBVA', 'numero_cuenta': '1', 'moneda_cuenta': 'PEN', 'banco2': 'BBVA', 'numero_cuenta2': '2',
               'moneda_cuenta2': 'USD'}
        assert cp.cuenta_preferida(dos, 'KCF', 'USD')['numero_cuenta'] == '2'
        assert cp.cuenta_preferida(dos, 'KCF', 'PEN')['numero_cuenta'] == '1'
        assert cp.cuenta_preferida({'banco': 'BCP'}, 'KCF') is None


def test_maestros_guarda_y_devuelve_tres_cuentas(admin):
    _limpiar()
    datos = {'razon_social': 'PROVEEDOR ZZ CUENTAS', 'ruc': RUC, 'direccion': 'Av. ZZ 123', 'descuento': '0', 'banco': 'Interbank', 'tipoCuenta': 'Cuenta corriente',
             'cuenta': '200-1', 'cci': '003-200', 'monedaCuenta': 'PEN',
             'banco2': 'BBVA', 'tipoCuenta2': 'Cuenta de ahorros', 'monedaCuenta2': 'PEN', 'cuenta2': '0011-22', 'cci2': '011-22',
             'banco3': 'bcp', 'tipoCuenta3': 'Cuenta corriente', 'monedaCuenta3': 'USD', 'cuenta3': '191-33', 'cci3': '002-33'}
    r = admin.post('/maestros/api/proveedores/guardar', json=datos).get_json()
    assert r['success'], r
    pid = r['data']['id']
    d = admin.get(f'/maestros/api/proveedores/{pid}').get_json()['data']
    assert d['banco2'] == 'BBVA' and d['cuenta2'] == '0011-22' and d['banco3'] == 'BCP' and d['monedaCuenta3'] == 'USD'
    assert d['cuenta'] == '200-1'  # la cuenta 1 sigue en sus columnas de siempre
    datos.update(activo=True, cuenta3='', cci3='', banco3='')
    assert admin.put(f'/maestros/api/proveedores/{pid}', json=datos).get_json()['success']
    d = admin.get(f'/maestros/api/proveedores/{pid}').get_json()['data']
    assert d['cuenta3'] == '' and d['cuenta2'] == '0011-22'
    # En Compras cada proveedor trae sus cuentas y el banco de cada empresa
    cat = admin.get('/compras/api/flujo/catalogos').get_json()
    prov = next(p for p in cat['proveedores'] if p['id'] == pid)
    assert [c['banco'] for c in prov['cuentas']] == ['Interbank', 'BBVA']
    assert 'bancos_empresa' in cat
    for e in cat['empresas']:
        esperado = {'KCF': 'BBVA', 'AGD': 'BCP'}.get((e.get('codigo') or '').upper())
        if esperado and str(e['id']) in cat['bancos_empresa']:
            assert cat['bancos_empresa'][str(e['id'])] == esperado
    _limpiar()


def test_pantallas_muestran_cuenta_elegida_y_boton_crear_oc():
    js = (RAIZ / 'static/js/compras_flujo.js').read_text(encoding='utf-8')
    assert 'function cuentaPreferida' in js and 'cuenta_aviso' in js
    assert 'cuenta_aviso' in (RAIZ / 'static/js/finanzas.js').read_text(encoding='utf-8')
    modal = (RAIZ / 'templates/modales/proveedor_modal.html').read_text(encoding='utf-8')
    for campo in ('prov_banco2', 'prov_cuenta2', 'prov_cci2', 'prov_banco3', 'prov_cci3', 'prov_monedaCuenta'):
        assert f'id="{campo}"' in modal
    flujo = (RAIZ / 'templates/compras/flujo.html').read_text(encoding='utf-8')
    assert 'Crear OC - Orden de compra (Proveedor)' in flujo and '>🛒 Crear orden de compra' not in flujo


def test_nota_interna_nunca_sale_al_proveedor():
    from routes.compras_flujo import CAMPOS_CONFIDENCIALES
    assert 'nota_interna' in CAMPOS_CONFIDENCIALES
    assert 'nota_interna' not in (RAIZ / 'templates/compras/imprimir_oc.html').read_text(encoding='utf-8')
    flujo = (RAIZ / 'templates/compras/flujo.html').read_text(encoding='utf-8')
    assert 'id="ocNotaInterna"' in flujo and 'No la ve el proveedor' in flujo
    js = (RAIZ / 'static/js/compras_flujo.js').read_text(encoding='utf-8')
    assert "nota_interna: $('ocNotaInterna').value" in js
