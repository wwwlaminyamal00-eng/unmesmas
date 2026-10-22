"""
Pedido de Erika del 21/10/2026 16:35: Configuración ▸ Correlativos, permisos que de verdad limitan el menú
y las URL, botones de Entregas sin emojis y pedidos con OC ya generada. Datos inventados, solo en la base local.
"""
from datetime import date
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
    # 22/10/2026: doble confirmación, sin escribir otra vez el número no se cambia nada
    r = admin.post('/correlativos/api/fijar', json={'documento': 'COT', 'clave': '', 'siguiente': cot['ultimo'] + 10})
    assert r.status_code == 400 and r.json['codigo'] == 'falta_confirmar'
    r = admin.post('/correlativos/api/fijar', json={'documento': 'COT', 'clave': '', 'siguiente': cot['ultimo'] + 10,
                                                    'confirmacion': str(cot['ultimo'] + 11)})
    assert r.status_code == 400 and r.json['codigo'] == 'falta_confirmar'


def test_correlativo_fijado_se_usa_en_guia_y_factura_nuevas(admin, vendedor):
    _guia(vendedor)   # asegura que exista la serie T001
    g = _fila(admin, 'GUIA', 'T001')
    nuevo = g['ultimo'] + 500
    r = admin.post('/correlativos/api/fijar', json={'documento': 'GUIA', 'clave': g['clave'], 'siguiente': nuevo, 'confirmacion': str(nuevo)})
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
                                                       'siguiente': nuevo, 'confirmacion': str(nuevo)}).json['success']
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
    assert 'fin-cobros' in fin and 'fin-pagos' in fin
    # 22/10/2026: sin las 6 tarjetas ni la leyenda; una fila de resumen por pestaña, sin números repetidos
    assert 'fin-kpis' not in fin and 'fin-leyenda' not in fin and 'cxp-orden' not in fin and 'cxp-totales' not in fin
    assert 'id="{{ t[0] }}Resumen"' in fin
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


def _hoy_lima():
    # Fecha de Lima (la del ERP), no CURRENT_DATE de la base, que puede estar en UTC
    from zoneinfo import ZoneInfo
    from datetime import datetime
    return datetime.now(ZoneInfo('America/Lima')).date()


def test_cuentas_con_detalle_oc_pc_productos_estado_y_comentario(admin):
    """18:38: cada factura dice su OC, su PC, sus productos, si está pendiente / parcial / pagada,
    la fecha real de pago y un comentario de Finanzas."""
    prov = _sql("""INSERT INTO proveedores (razon_social, ruc, direccion, condicion_pago, activo)
                   VALUES ('PROVEEDOR DETALLE ZZ', '20555000111', 'Lima', 'Contado', true) RETURNING id""")[0][0]
    oc = _sql("""INSERT INTO ordenes_compra (numero_orden, proveedor_id, estado, subtotal, igv, total, fecha_creacion,
                                             pc_numeros, tipo_compra)
                 VALUES ('OC-ZZDET-1', %s, 'Aprobada', 100, 18, 118, NOW(), 'PC-ZZDET-1', 'Bajo pedido') RETURNING id""", (prov,))[0][0]
    _sql("""INSERT INTO ordenes_compra_items (orden_compra_id, producto, cantidad, precio_unitario, total)
            VALUES (%s, 'GUANTE ZZDET', 10, 5, 50), (%s, 'CASCO ZZDET', 5, 10, 50)""", (oc, oc), fetch=False)
    cp = _sql("""INSERT INTO comprobantes_proveedor (tipo, numero, fecha, monto, ruc_proveedor, proveedor_nombre,
                                                     orden_compra_id, orden_compra_numero, estado, created_at, fecha_vencimiento)
                 VALUES ('Factura', 'F001-ZZDET1', CURRENT_DATE, 118, '20555000111', 'PROVEEDOR DETALLE ZZ', %s,
                         'OC-ZZDET-1', 'Pendiente', NOW(), CURRENT_DATE + 30) RETURNING id""", (oc,))[0][0]
    # adelanto pagado en Compras antes de registrar la factura
    _sql("""INSERT INTO finanzas_pagos (tipo, documento_tabla, documento_id, documento_numero, tercero_nombre, fecha, monto,
                                        estado, created_at)
            VALUES ('PAGO', 'comprobantes_proveedor', %s, 'F001-ZZDET1', 'PROVEEDOR DETALLE ZZ', CURRENT_DATE - 2, 50,
                    'Registrado', NOW() - INTERVAL '2 days')""", (cp,), fetch=False)
    fila = next(x for x in admin.get('/finanzas/api/cxp?estado=todos').json['data'] if x['id'] == cp)
    assert fila['oc_numero'] == 'OC-ZZDET-1' and fila['pc_numero'] == 'PC-ZZDET-1'
    assert [p['producto'] for p in fila['productos']] == ['GUANTE ZZDET', 'CASCO ZZDET']
    assert fila['estado_pago'] == 'Pago parcial' and fila['adelanto'] == 50 and fila['saldo'] == 68
    assert fila['fecha_pago_real'] is None
    # se completa el pago: Pagado con su fecha real
    _sql("""INSERT INTO finanzas_pagos (tipo, documento_tabla, documento_id, documento_numero, tercero_nombre, fecha, monto, estado)
            VALUES ('PAGO', 'comprobantes_proveedor', %s, 'F001-ZZDET1', 'PROVEEDOR DETALLE ZZ', %s, 68, 'Registrado')""",
         (cp, _hoy_lima()), fetch=False)
    fila = next(x for x in admin.get('/finanzas/api/cxp?estado=todos').json['data'] if x['id'] == cp)
    assert fila['estado_pago'] == 'Pagado' and fila['fecha_pago_real'] == _hoy_lima().isoformat() and fila['adelanto'] == 50
    # comentario de Finanzas
    r = admin.post('/finanzas/api/comentario', json={'tipo': 'cxp', 'id': cp, 'comentario': 'pagar con la caja de AGD'})
    assert r.status_code == 200 and r.json['comentario'] == 'Pagar con la caja de AGD'
    fila = next(x for x in admin.get('/finanzas/api/cxp?estado=todos').json['data'] if x['id'] == cp)
    assert fila['comentario'] == 'Pagar con la caja de AGD'
    assert admin.post('/finanzas/api/comentario', json={'tipo': 'otro', 'id': cp, 'comentario': 'x'}).status_code == 400
    # cuentas por cobrar: N° PC y productos de la factura de venta
    cxc = admin.get('/finanzas/api/cxc?estado=todos').json['data']
    assert all({'estado_pago', 'pc_numero', 'oc_cliente', 'productos', 'fecha_pago_real'} <= set(x) for x in cxc)
    assert all(x['estado_pago'] in ('Por cobrar', 'Cobro parcial', 'Cobrado') for x in cxc)


def test_vencimiento_absurdo_no_se_acepta(admin):
    """18:38: una factura vencía el 25/04/2136 por una OC con 'Crédito 40000 días'."""
    cp = _sql("""INSERT INTO comprobantes_proveedor (tipo, numero, fecha, monto, ruc_proveedor, proveedor_nombre, estado)
                 VALUES ('Factura', 'F001-ZZVENC', '2026-10-19', 100, '20555000111', 'PROVEEDOR DETALLE ZZ', 'Pendiente')
                 RETURNING id""")[0][0]
    r = admin.put(f'/finanzas/api/cxp/{cp}/vencimiento', json={'fecha_vencimiento': '2136-04-25'})
    assert r.status_code == 400 and 'Revisa el año' in r.json['error']
    assert admin.put(f'/finanzas/api/cxp/{cp}/vencimiento', json={'fecha_vencimiento': '2026-10-01'}).status_code == 400
    assert admin.put(f'/finanzas/api/cxp/{cp}/vencimiento', json={'fecha_vencimiento': '2026-11-18'}).status_code == 200
    emp = _sql("SELECT id FROM erp_empresas ORDER BY id LIMIT 1")
    prov = _sql("SELECT id FROM proveedores WHERE activo ORDER BY id LIMIT 1")
    sede = _sql("SELECT id FROM almacenes ORDER BY id LIMIT 1")
    if emp and prov and sede:
        r = admin.post('/compras/api/flujo/ordenes', json={
            'empresa_id': emp[0][0], 'proveedor_id': prov[0][0], 'almacen_entrega_id': sede[0][0],
            'condicion_pago': 'Crédito', 'dias_credito': 40000, 'modalidad_entrega': 'Proveedor entrega',
            'fecha_compromiso': '2026-10-30', 'motivo_compra': 'Stock estratégico', 'items': []})
        assert r.status_code == 400 and 'entre 1 y 360' in r.json['error']


def test_resumen_compacto_cxc_y_cxp(admin):
    """22/10/2026: CxC y CxP traen sus totales (vencido, por vencer, al día, total) para la fila de resumen."""
    for tipo in ('cxc', 'cxp'):
        r = admin.get(f'/finanzas/api/{tipo}', query_string={'estado': 'todos'})
        assert r.status_code == 200, r.json
        t = r.json['totales']
        assert {'vencido', 'por_vencer', 'al_dia', 'total', 'docs_vencidos', 'docs_por_vencer', 'docs_al_dia', 'docs_total'} <= set(t)
        assert round(t['vencido'] + t['por_vencer'] + t['al_dia'], 2) <= round(t['total'], 2) + 0.01


def test_solo_lectura_mira_pero_no_graba(app, admin, base):
    """22/10/2026: matriz de permisos. "Solo lectura" (solo Ver) entra al módulo pero el servidor no deja grabar."""
    uid = _usuaria_finanzas(base, 'perm_lectura')
    sql("UPDATE usuarios SET password = %s WHERE id = %s", (generate_password_hash('Lectu#2026!'), uid))
    _guardar(admin, uid, base['emp']['KCF'], [{'submodulo_codigo': c, 'puede_ver': True, 'puede_crear': False,
                                               'puede_editar': False, 'puede_exportar': True}
                                              for c in ('CUENTAS_COBRAR', 'CAJA_BANCOS')])
    from routes.acceso import limpiar_cache
    limpiar_cache()
    h = _login(app, 'perm_lectura', 'Lectu#2026!')
    assert h.get('/finanzas').status_code == 200
    assert h.get('/finanzas/api/cxc').status_code == 200
    r = h.post('/finanzas/api/comentario', json={'tipo': 'cxp', 'documento_id': 1, 'comentario': 'x'})
    assert r.status_code == 403 and r.json['codigo'] == 'solo_lectura' and 'Solo lectura' in r.json['error']
    # Acceso total: ya no lo bloquea el control de permisos
    _guardar(admin, uid, base['emp']['KCF'], [{'submodulo_codigo': 'CAJA_BANCOS', 'puede_ver': True, 'puede_crear': True,
                                               'puede_editar': True}])
    r = h.post('/finanzas/api/comentario', json={'tipo': 'cxp', 'documento_id': 1, 'comentario': 'x'})
    assert r.json.get('codigo') != 'solo_lectura'


def test_matriz_de_permisos_en_la_pantalla(admin):
    html = admin.get('/usuarios').get_data(as_text=True)
    assert 'id="pmModal"' in html and 'permisos_matriz.js' in html and 'Solo lectura' in html and 'Acceso total' in html
    r = admin.get('/api/config/modulos')
    assert r.status_code == 200 and r.json['success'] and r.json['data']
