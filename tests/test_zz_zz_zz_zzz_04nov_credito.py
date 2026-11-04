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
    assert 'APROBADA por' in html and '(hora de Lima)' in html and 'NO APROBADA' not in html
    assert admin.get(f'/compras/flujo/ordenes/{sin}/imprimir').status_code == 409
    html = admin.get(f'/compras/flujo/ordenes/{sin}/imprimir?hoja=borrador').get_data(as_text=True)
    assert 'NO APROBADA' in html and 'solo Erika o Hellen' in html and 'APROBADA por' not in html


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
