"""
Erika 04/11/2026: "una data de todas las oc al credito ... tengo miedo que pidan mercaderia al credito sin mi
aprobación y luego tenga una deuda de 10 mil soles ... esa oc debe tener una firma".
Pestaña "OC al crédito" (deuda por proveedor, quién hizo y quién aprobó), sello de aprobación en la OC impresa,
marca "NO APROBADA" y aviso de movimientos de stock en viñetas + tabla. Datos inventados, solo en la base local.
"""
from pathlib import Path

from tests.test_inventario import _sql
from tests.test_zz_zz_27oct_flujos import _producto

RAIZ = Path(__file__).resolve().parent.parent


def _oc(admin, dias, precio, cantidad=1, enviar=True):
    emp = _sql("SELECT id FROM erp_empresas ORDER BY id LIMIT 1")[0][0]
    alm = _sql("SELECT id FROM almacenes WHERE COALESCE(activo, true) ORDER BY id LIMIT 1")[0][0]
    _sql("""INSERT INTO proveedores (razon_social, ruc, direccion, condicion_pago, activo)
            SELECT 'CREDITO ZZ04 S.A.C.', '20599990411', 'Av. Lima 4', 'Crédito', true
            WHERE NOT EXISTS (SELECT 1 FROM proveedores WHERE ruc = '20599990411')""", fetch=False)
    prov = _sql("SELECT id FROM proveedores WHERE ruc = '20599990411'")[0][0]
    body = {'empresa_id': emp, 'proveedor_id': prov, 'almacen_entrega_id': alm, 'condicion_pago': 'Crédito',
            'dias_credito': dias, 'modalidad_entrega': 'Proveedor entrega', 'fecha_compromiso': '2026-11-30',
            'motivo_compra': 'Stock estratégico', 'motivo_stock': 'Stock estratégico', 'enviar': enviar,
            'items': [{'producto_id': _producto('ZZ04-CRED'), 'cantidad': cantidad, 'precio_unitario': precio}]}
    r = admin.post('/compras/api/flujo/ordenes', json=body)
    assert r.status_code == 200, r.get_json()
    return r.get_json()['id']


def test_lista_oc_credito_deuda_y_sin_aprobar(admin):
    aprobada = _oc(admin, 30, 1000)
    sin = _oc(admin, 60, 250, cantidad=2)
    if _sql("SELECT estado FROM ordenes_compra WHERE id = %s", (aprobada,))[0][0] == 'Por aprobar':
        assert admin.post(f'/compras/api/flujo/ordenes/{aprobada}/aprobar', json={'aprobar': True}).status_code == 200
    _sql("UPDATE ordenes_compra SET estado = 'Por aprobar', aprobado_por = NULL, aprobado_en = NULL WHERE id = %s", (sin,), fetch=False)
    r = admin.get('/compras/api/flujo/credito').get_json()
    assert r['success']
    filas = {f['id']: f for f in r['data']}
    a, s = filas[aprobada], filas[sin]
    assert a['aprobada'] and a['aprobado_por'] and a['aprobado_en'] and a['saldo'] == 1180
    assert a['vence_estimado'] and a['vence'] and a['dias_credito'] == 30
    assert not s['aprobada'] and s['saldo'] == 0 and s['aprobado_por'] is None
    prov = next(p for p in r['proveedores'] if p['ruc'] == '20599990411')
    assert prov['deuda'] >= 1180 and prov['sin_aprobar'] >= 590 and prov['n_sin_aprobar'] >= 1
    assert r['totales']['PEN']['n_sin_aprobar'] >= 1
    # OC impresa: sello con nombre y hora; la no aprobada solo sale como borrador con la marca
    html = admin.get(f'/compras/flujo/ordenes/{aprobada}/imprimir').get_data(as_text=True)
    assert 'APROBADO por' in html and '(hora de Lima)' in html and 'NO APROBADA' not in html
    assert admin.get(f'/compras/flujo/ordenes/{sin}/imprimir').status_code == 409
    html = admin.get(f'/compras/flujo/ordenes/{sin}/imprimir?hoja=borrador').get_data(as_text=True)
    assert 'NO APROBADA' in html and 'solo Erika o Hellen' in html and 'APROBADO por' not in html


def test_pantallas_credito_y_aviso_stock():
    html = (RAIZ / 'templates/compras/flujo.html').read_text(encoding='utf-8')
    js = (RAIZ / 'static/js/compras_flujo.js').read_text(encoding='utf-8')
    assert 'data-tab="credito"' in html and 'id="sec-credito"' in html and "'Compras - OC al crédito'" in html
    assert 'credito: cargarCredito' in js and '/compras/api/flujo/credito' in js
    inv = (RAIZ / 'static/js/inventario.js').read_text(encoding='utf-8')
    assert 'inv-pend-tabla' in inv and 'no existe físicamente' in inv and 'No se borra nada' in inv


def test_ventana_diferencias_recepcion_en_tabla():
    # Erika 04/11/2026: "más claro y ordenado, sin mucho floro, mejor colorimetría"
    js = (RAIZ / 'static/js/compras_flujo.js').read_text(encoding='utf-8')
    i = js.index('function ventanaDiferencias')
    v = js[i:js.index('async function guardarRecepcion', i)]
    assert 'Lo contado no coincide con la OC' in v and '>Pedido</th>' in v and '>Contado</th>' in v and '>Diferencia</th>' in v
    assert 'no se grabó nada' in v and 'data-motivo' in v and 'Aviso.rojo' not in v


def test_pdf_oc_ordenado_y_distinto_por_empresa():
    # Erika 04/11/2026: tiempo de entrega, "Ítems", "Emitir factura a:" en puntos, datos bancarios solo internos, KCF ≠ AGD
    t = (RAIZ / 'templates/compras/imprimir_oc.html').read_text(encoding='utf-8')
    assert 'Tiempo de entrega' in t and '>Ítems</div>' in t and 'Emitir factura a:' in t
    assert '<div class="transfer no-print">' in t and "== 'AGD'" in t


def test_recibir_solo_erika_hellen_estrella(app):
    import utils
    from flask import session
    with app.test_request_context():
        for usuario, esperado in (('eri01kcf', True), ('HEL02KCF', True), ('est01kcf', True), ('luis01kcf', False), ('mil01kcf', False)):
            session['usuario'] = usuario
            assert utils.recibe_mercaderia() is esperado, usuario
    js = (RAIZ / 'static/js/compras_flujo.js').read_text(encoding='utf-8')
    assert '💸 Registrar pago' in js and 'Reciben solo Erika, Hellen o Estrella' in js


def test_firma_agd_como_gerencia_en_pdf():
    # Erika 04/11/2026: "Aprobado por: Gerencia Compras AGD GROUP SAC" (por dentro se guarda el usuario real)
    from routes.compras_flujo import FIRMA_APROBACION_PDF
    assert FIRMA_APROBACION_PDF == {'AGD': 'Gerencia Compras AGD GROUP SAC'}
    t = (RAIZ / 'templates/compras/imprimir_oc.html').read_text(encoding='utf-8')
    assert 'aprobador_pdf or o.aprobado_por' in t and 'Aprobado por:' in t


def test_contado_recibido_sin_pago_plazo_5_dias():
    # Erika 04/11/2026: los proveedores al contado entregan antes del pago; se recibe y queda "Recibido · falta pagar"
    from datetime import datetime, timedelta, date
    from routes.compras_flujo import _paso, _vence_pago_contado, DIAS_PAGO_CONTADO
    assert DIAS_PAGO_CONTADO == 5
    base = {'estado': 'Recibida', 'total': 100, 'pagado': 0, 'condicion_pago': 'Contado', 'flujo': 'v2', 'ruc': '20000000001',
            'incidencias': 0, 'facturas': 0, 'facturado': 0, 'adelanto_pct': 0}
    hace = datetime.now() - timedelta(days=7)
    p = _paso(dict(base, primera_recepcion=hace))
    assert p['codigo'] == 'pagar' and 'VENCIDO' in p['texto'] and 'Recibido · falta pagar' in p['texto']
    assert _vence_pago_contado({'primera_recepcion': hace}) == hace.date() + timedelta(days=5)
    p = _paso(dict(base, primera_recepcion=datetime.now()))
    assert p['codigo'] == 'pagar' and 'VENCIDO' not in p['texto']
    assert _paso(dict(base, estado='Aprobada'))['codigo'] == 'recibir'          # antes de llegar: ya se puede recibir
    assert date.today()
