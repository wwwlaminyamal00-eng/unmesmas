"""
Pedido de Erika del 21/10/2026 16:35: Configuración ▸ Correlativos, permisos que de verdad limitan el menú
y las URL, botones de Entregas sin emojis y pedidos con OC ya generada. Datos inventados, solo en la base local.
"""
from tests.test_inventario import _sql
from tests.test_zz_zz_20oct_zduplicados import _guia, _factura


def _fila(admin, documento, empezar=''):
    r = admin.get('/correlativos/api/lista')
    assert r.status_code == 200 and r.json['success'], r.json
    return next(f for f in r.json['data'] if f['documento'] == documento and f['serie'].startswith(empezar))


def test_correlativos_lista_y_solo_admin(admin, vendedor):
    r = admin.get('/correlativos')
    assert r.status_code == 200 and 'Correlativos' in r.get_data(as_text=True)
    docs = {f['documento'] for f in admin.get('/correlativos/api/lista').json['data']}
    assert {'COT', 'OC'} <= docs
    oc = _fila(admin, 'OC')
    assert oc['editable'] is False
    assert vendedor.get('/correlativos/api/lista').status_code in (302, 403)
    assert vendedor.post('/correlativos/api/fijar', json={'documento': 'COT', 'clave': '', 'siguiente': 9999}).status_code in (302, 403)


def test_correlativo_no_acepta_numero_menor_o_igual(admin):
    cot = _fila(admin, 'COT')
    r = admin.post('/correlativos/api/fijar', json={'documento': 'COT', 'clave': '', 'siguiente': cot['ultimo']})
    assert r.status_code == 400 and 'mayor que el último emitido' in r.json['error']
    r = admin.post('/correlativos/api/fijar', json={'documento': 'OC', 'clave': '', 'siguiente': 99})
    assert r.status_code == 400


def test_correlativo_fijado_se_usa_en_guia_y_factura_nuevas(admin, vendedor):
    _guia(vendedor)   # asegura que exista la serie T001
    g = _fila(admin, 'GUIA', 'T001')
    nuevo = g['ultimo'] + 500
    r = admin.post('/correlativos/api/fijar', json={'documento': 'GUIA', 'clave': g['clave'], 'siguiente': nuevo})
    assert r.status_code == 200 and r.json['success'], r.json
    r = _guia(vendedor, numero='')
    assert r.status_code == 200, r.json
    assert int(r.json['data']['numero']) == nuevo
    # Las guías ya emitidas no cambian
    assert _sql("SELECT COUNT(*) FROM guias_remision WHERE numero = %s", (str(g['ultimo']).zfill(8),))[0][0] <= 1
    assert _sql("SELECT COUNT(*) FROM erp_auditoria WHERE tabla = 'erp_numeracion'")[0][0] >= 1

    _factura(vendedor)
    f = _fila(admin, 'COMPROBANTE', 'Factura F001')
    nuevo = f['ultimo'] + 50
    assert admin.post('/correlativos/api/fijar', json={'documento': 'COMPROBANTE', 'clave': f['clave'],
                                                       'siguiente': nuevo}).json['success']
    r = _factura(vendedor, ruc='20999999991', cliente='OTRO CLIENTE S.A.C.')
    assert r.status_code == 200, r.json
    assert _fila(admin, 'COMPROBANTE', 'Factura F001')['ultimo'] == nuevo


# ------------------------------------------------------------
# Permisos: el caso de Hellen (rol de sistema "administrador" pero solo 2 permisos en el ERP)
# ------------------------------------------------------------
from werkzeug.security import generate_password_hash

from conftest import _login
from tests.test_flujos import sql
from tests.test_permisos_usuarios import base, _usuario, _guardar   # noqa: F401  (base es fixture)


def _usuaria_finanzas(base, nombre):
    sql("""INSERT INTO erp_modulos (orden, codigo, nombre, estado) SELECT 9, 'FINANZAS', 'Finanzas', 'activo'
           WHERE NOT EXISTS (SELECT 1 FROM erp_modulos WHERE codigo = 'FINANZAS')""")
    for i, cod in enumerate(('CUENTAS_COBRAR', 'CAJA_BANCOS'), 1):
        sql("""INSERT INTO erp_submodulos (modulo_id, orden, codigo, nombre, estado)
               SELECT m.id, %s, %s, %s, 'activo' FROM erp_modulos m
               WHERE m.codigo = 'FINANZAS' AND NOT EXISTS (SELECT 1 FROM erp_submodulos WHERE codigo = %s)""",
            (i, cod, cod.title(), cod))
    sql("""INSERT INTO erp_roles (codigo, nombre, es_admin, estado) SELECT 'FINANZAS', 'Finanzas', false, 'activo'
           WHERE NOT EXISTS (SELECT 1 FROM erp_roles WHERE codigo = 'FINANZAS')""")
    base['roles']['FINANZAS'] = str(sql("SELECT id FROM erp_roles WHERE codigo = 'FINANZAS'")[0][0])
    uid, auth = _usuario(base, nombre, rol_erp='FINANZAS', empresas=('KCF',))
    sql("UPDATE usuarios SET rol = 'administrador', password = %s WHERE id = %s",
        (generate_password_hash('Hellen#2026!'), uid))
    return uid


def test_usuaria_con_dos_permisos_solo_ve_finanzas(app, admin, base):
    uid = _usuaria_finanzas(base, 'perm_hellen')
    r = _guardar(admin, uid, base['emp']['KCF'], [{'submodulo_codigo': 'CUENTAS_COBRAR', 'puede_ver': True},
                                                  {'submodulo_codigo': 'CAJA_BANCOS', 'puede_ver': True}])
    assert r.status_code == 200, r.json
    from routes.acceso import limpiar_cache
    limpiar_cache()
    h = _login(app, 'perm_hellen', 'Hellen#2026!')
    html = h.get('/finanzas').get_data(as_text=True)
    assert 'menuPermisosServidor' in html and ':not([data-modulo="finanzas"])' in html
    assert ':not([data-modulo="ventas"])' not in html
    assert 'id="usuarioEsAdmin" value="0"' in html
    # URL directa a otro módulo: bloqueada en el servidor
    r = h.get('/ventas')
    assert r.status_code == 302 and '/index' in r.headers['Location'] or r.headers['Location'].endswith('/')
    r = h.get('/ventas/api/cotizaciones/listar')
    assert r.status_code == 403 and r.json['codigo'] == 'sin_permiso' and 'Ventas' in r.json['error']
    assert h.get('/compras/api/flujo/pedidos').status_code == 403
    assert h.get('/reportes').status_code == 302
    # Ya no es administradora: configuración y herramientas cerradas
    assert h.get('/usuarios').status_code == 302
    assert h.get('/correlativos/api/lista').status_code == 403
    # Las consultas comunes (buscar clientes) siguen funcionando
    assert h.get('/maestros/api/clientes/listar').status_code == 200
    # Si el administrador le da Cotizaciones, entra a Ventas (sin volver a iniciar sesión)
    _guardar(admin, uid, base['emp']['KCF'], [{'submodulo_codigo': 'COTIZACIONES', 'puede_ver': True}])
    assert h.get('/ventas').status_code == 200


def test_gerencia_total_sigue_viendo_todo(app, admin, base):
    uid, _ = _usuario(base, 'perm_gerencia2', rol_erp='GERENCIA_TOTAL', empresas=('KCF',))
    sql("UPDATE usuarios SET password = %s WHERE id = %s", (generate_password_hash('Geren#2026!'), uid))
    g = _login(app, 'perm_gerencia2', 'Geren#2026!')
    html = g.get('/ventas').get_data(as_text=True)
    assert 'menuPermisosServidor' not in html and 'id="usuarioEsAdmin" value="1"' in html
    assert g.get('/correlativos/api/lista').status_code == 200


def test_pedido_con_oc_activa_dice_cual_y_no_se_marca(admin):
    import pytest
    from pathlib import Path
    pedidos = {p['numero']: p for p in admin.get('/compras/api/flujo/pedidos?todos=1').json['data']}
    if 'PC-ZZD-CUB' not in pedidos:
        pytest.skip('el pedido de prueba lo crea test_zz_zz_20oct_zduplicados')
    it = pedidos['PC-ZZD-CUB']['items'][0]
    assert it['ocs'].startswith('OC-')
    cjs = (Path(__file__).resolve().parent.parent / 'static/js/compras_flujo.js').read_text(encoding='utf-8')
    assert 'OC ya generada' in cjs and 'cubiertaYa' in cjs


def test_entregas_botones_sin_emojis():
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent
    vjs = (raiz / 'static/js/ventas.js').read_text(encoding='utf-8')
    for texto in ('>Generar compra</button>', '>Confirmar despacho</button>', '>Generar factura</button>', '>Generar rótulo</button>'):
        assert texto in vjs
    for viejo in ('>🛒 Generar compra<', '>🚚 Confirmar despacho<', '>🧾 Generar factura<', '>🏷 Generar rótulo<'):
        assert viejo not in vjs
    css = (raiz / 'templates/ventas/index.html').read_text(encoding='utf-8')
    assert 'white-space:nowrap!important' in css and '#despachoRows td .acc-col' in css


def test_tablas_centradas_y_colores_finanzas():
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent
    base = (raiz / 'templates/base.html').read_text(encoding='utf-8')
    assert 'text-align:center!important' in base
    fin = (raiz / 'templates/finanzas.html').read_text(encoding='utf-8')
    assert 'fin-kpi-cobro' in fin and 'fin-kpi-pago' in fin and 'fin-cobros' in fin and 'fin-pagos' in fin
    pdf = (raiz / 'pdf_generator.py').read_text(encoding='utf-8')
    assert '.footer .item .sep { color: {{ color }}; font-weight: 900; margin: 0 2px; }' in pdf


def test_cobro_con_fecha_de_aviso_y_buscador(admin, vendedor):
    """17:12: el cliente manda N.º de operación o solo avisa con una fecha: basta con uno."""
    from tests.test_flujos import factura
    cid = factura(vendedor, total=118, subtotal=100, igv=18, cliente='CLIENTE AVISO ZZ', ruc='20100070971').json['data']['id']
    vendedor.put(f'/ventas/api/comprobantes/{cid}/toggle', json={'estado': 'Emitido'})
    base = {'tipo': 'COBRO', 'documento_id': cid, 'monto': 10, 'metodo': 'Transferencia'}
    r = admin.post('/finanzas/api/movimientos', json=base)
    assert r.status_code == 400 and 'fecha de aviso' in r.json['error']
    r = admin.post('/finanzas/api/movimientos', json={**base, 'fecha_aviso': '2026-10-20'})
    assert r.status_code == 200, r.json
    assert admin.post('/finanzas/api/movimientos', json={**base, 'numero_operacion': 'OPZZ-123'}).status_code == 200
    assert admin.post('/finanzas/api/movimientos', json={**base, 'metodo': 'Efectivo'}).status_code == 200
    movs = admin.get('/finanzas/api/movimientos?q=OPZZ-123').json['data']
    assert len(movs) == 1 and movs[0]['numero_operacion'] == 'OPZZ-123'
    movs = admin.get('/finanzas/api/movimientos?q=CLIENTE AVISO ZZ').json['data']
    assert len(movs) == 3 and any(m['fecha_aviso'] for m in movs)


def test_pagar_a_un_dato_por_linea(admin):
    """17:22: Proveedor, RUC, Banco, N° de cuenta, CCI y Monto a pagar (incluye IGV), cada uno en su línea."""
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent
    r = admin.get('/finanzas/api/cxp?estado=todos')
    assert r.status_code == 200
    for fila in r.json['data']:
        assert {'banco', 'numero_cuenta', 'cci'} <= set(fila)
    assert '.ficha-datos' in (raiz / 'templates/base.html').read_text(encoding='utf-8')
    for js in ('static/js/compras_flujo.js', 'static/js/finanzas.js'):
        txt = (raiz / js).read_text(encoding='utf-8')
        for etiqueta in ("'Proveedor'", "'RUC / DNI'", "'Banco'", "'N° de cuenta'", "'CCI'", 'Monto a pagar (incluye IGV)'):
            assert etiqueta in txt, (js, etiqueta)
        assert 'cuentaDeRelleno' in txt
