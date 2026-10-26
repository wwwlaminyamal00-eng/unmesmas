"""
Pedido de Erika del 20/10/2026 ("Correcciones de flujo, estética y lógica de negocio"):
  - Cotización: "Entrega" por producto solo Pendiente/Entregado; la fila de la parihuela es obligatoria para validación.
  - Compras: panel de abastecimiento con "Extra para stock"; factura de proveedor que no cuadra no se guarda; botón Ver.
  - RUC duplicado: aviso apenas se escribe o carga el RUC (clientes y proveedores).
  - Guías: "N° Facturas"; Facturas: Cotización > N° PV > N° Guía > N° Factura.
  - "Pendiente por compra" solo con la cotización aceptada por el cliente.
  - Despacho sin stock: dice qué producto falta y en qué sede (ver test_stock_automatico).
  - Bug encontrado: "Guardar / Actualizar" cliente desde la cotización borraba contactos y datos del cliente.
Datos inventados, solo en la base local de pruebas.
"""
from pathlib import Path

from tests.test_inventario import _sql

RAIZ = Path(__file__).resolve().parent.parent
BASE_COT = {'cliente_id': 1, 'productos': [{'codigo': 'PRD-0001', 'cantidad': 2, 'valorVenta': 50}],
            'condicion_pago': 'Crédito 30 días', 'tiempo_entrega': '2 días hábiles', 'transporte': 'Auto', 'parihuela': 'No'}


def _leer(rel):
    return (RAIZ / rel).read_text(encoding='utf-8-sig')


# ---------------------------------------------------------------- Cotización
def test_validacion_exige_la_fila_de_la_parihuela(vendedor):
    r = vendedor.post('/ventas/api/cotizaciones/guardar', json={**BASE_COT, 'estado': 'Por validar', 'nota_interna': ''})
    assert r.status_code == 400 and r.json['codigo'] == 'faltan_campos'
    # La nota interna dejó de ser obligatoria (Erika, 20/10/2026 17:19)
    assert 'Nota interna' not in r.json['faltan'] and 'Seguimiento' in r.json['faltan']
    assert r.json['error'].startswith('Faltan campos obligatorios para enviar a validación')
    # Un borrador sí se guarda sin la nota; con todo completo sí va a validación
    assert vendedor.post('/ventas/api/cotizaciones/guardar', json={**BASE_COT, 'estado': 'Borrador'}).status_code == 200
    r = vendedor.post('/ventas/api/cotizaciones/guardar', json={**BASE_COT, 'estado': 'Por validar', 'seguimiento': 'Hellen',
                                                                'motivo': 'Recompra', 'nota_interna': ''})
    assert r.status_code == 200, r.json


def test_entrega_por_producto_solo_pendiente_o_entregado(vendedor):
    prods = [{'codigo': 'PRD-0001', 'cantidad': 1, 'valorVenta': 50, 'estado_entrega': 'Inmediato'},
             {'codigo': 'PRD-0001', 'cantidad': 1, 'valorVenta': 50, 'estado_entrega': 'Entregado'}]
    r = vendedor.post('/ventas/api/cotizaciones/guardar', json={**BASE_COT, 'productos': prods, 'estado': 'Borrador'})
    assert r.status_code == 200, r.json
    estados = _sql("SELECT estado_entrega FROM cotizacion_detalle WHERE cotizacion_id = %s ORDER BY id", (r.json['data']['id'],))
    assert [e[0] for e in estados] == ['Pendiente', 'Entregado']
    js = _leer('static/js/ventas.js')
    assert '<option value="Pendiente"' in js and '<option value="Entregado"' in js


def test_pendiente_por_compra_solo_con_aceptada_por_cliente(vendedor):
    cid = vendedor.post('/ventas/api/cotizaciones/guardar', json={**BASE_COT, 'estado': 'Borrador'}).json['data']['id']
    _sql("UPDATE cotizaciones SET estado = 'Generada' WHERE id = %s", (cid,), fetch=False)
    assert str(cid) not in vendedor.get('/api/abastecimiento/cotizaciones').get_json()['data']
    _sql("UPDATE cotizaciones SET estado = 'Aceptada por Cliente' WHERE id = %s", (cid,), fetch=False)
    assert str(cid) in vendedor.get('/api/abastecimiento/cotizaciones').get_json()['data']
    js = _leer('static/js/ventas.js')
    assert "cotAceptadaCliente(r) ? abastBadge('cotizaciones', r.id) : ''" in js
    assert "${badgeStatus(r.estado)}${abastBadge('cotizaciones', r.id)}" not in js


# ---------------------------------------------------------------- RUC duplicado
def test_aviso_ruc_ya_registrado(admin):
    base = {'razon_social': 'CLIENTE RUC ZZ', 'numero_documento': '20999000333', 'tipo_documento': 'RUC',
            'direccion_fiscal': 'Av. Prueba 3', 'limite_credito': '0', 'descuento': '0', 'condicion_pago': 'Contado'}
    assert admin.post('/maestros/api/clientes/guardar', json=base).json['success']
    cid = _sql("SELECT id FROM clientes WHERE numero_documento = '20999000333'")[0][0]
    r = admin.get('/maestros/api/ruc-registrado', query_string={'tipo': 'cliente', 'ruc': '20999000333'}).get_json()
    assert r['registrado'] and r['razon_social'] == 'CLIENTE RUC ZZ'
    # Al editar ese mismo cliente no se avisa; un RUC nuevo tampoco
    assert not admin.get('/maestros/api/ruc-registrado', query_string={'tipo': 'cliente', 'ruc': '20999000333', 'excluir': cid}).get_json()['registrado']
    assert not admin.get('/maestros/api/ruc-registrado', query_string={'tipo': 'cliente', 'ruc': '20999000999'}).get_json()['registrado']
    ruc_prov = _sql("SELECT ruc FROM proveedores WHERE COALESCE(ruc, '') <> '' LIMIT 1")
    if ruc_prov:
        assert admin.get('/maestros/api/ruc-registrado', query_string={'tipo': 'proveedor', 'ruc': ruc_prov[0][0]}).get_json()['registrado']
    js = _leer('static/js/maestros.js')
    assert "avisoRucDuplicado('cliente')" in js and "avisoRucDuplicado('proveedor')" in js and 'ya está registrado como' in js


# ---------------------------------------------------------------- Bug: actualizar cliente desde la cotización
def test_actualizar_cliente_desde_cotizacion_no_borra_sus_datos(admin):
    base = {'razon_social': 'CLIENTE CONSERVA ZZ', 'numero_documento': '20999000444', 'tipo_documento': 'RUC',
            'direccion_fiscal': 'Av. Prueba 4', 'limite_credito': '5000', 'descuento': '0', 'observaciones': 'Paga puntual',
            'condicion_pago': 'Crédito aprobado', 'dias_credito': '60',
            'contactos': [{'nombre': 'Ana Ruiz', 'telefono': '999111222', 'principal': True}]}
    assert admin.post('/maestros/api/clientes/guardar', json=base).json['success']
    cid = _sql("SELECT id FROM clientes WHERE numero_documento = '20999000444'")[0][0]
    antes = _sql("SELECT COUNT(*) FROM clientes_contactos WHERE cliente_id = %s", (cid,))[0][0]
    # Lo que manda el botón "Guardar / Actualizar" de la cotización (sin contactos ni condición)
    r = admin.put(f'/maestros/api/clientes/{cid}', json={'tipo_documento': 'RUC', 'numero_documento': '20999000444', 'ruc': '20999000444',
                                                        'razon_social': 'CLIENTE CONSERVA ZZ', 'nombre_comercial': '',
                                                        'direccion_fiscal': 'Av. Nueva 10', 'nombre_contacto': 'Ana Ruiz',
                                                        'telefono_contacto': '999111222', 'email_contacto': '',
                                                        'activo': True, 'estado': 'Activo'})
    assert r.json['success'], r.json
    fila = _sql("SELECT condicion_pago, dias_credito, observaciones, direccion_fiscal FROM clientes WHERE id = %s", (cid,))[0]
    assert fila == ('Crédito aprobado', 60, 'Paga puntual', 'Av. Nueva 10')
    assert _sql("SELECT COUNT(*) FROM clientes_contactos WHERE cliente_id = %s", (cid,))[0][0] == antes
    js = _leer('static/js/ventas.js')
    assert "condicion_pago: document.getElementById('fCondicion')?.value || 'Contado'" not in js


# ---------------------------------------------------------------- Pantallas
def test_pantallas_del_20_de_octubre():
    html = _leer('templates/ventas/index.html')
    guias = html[html.index('<div id="guias"'):html.index('<div id="comprobantes"')]
    assert '<th>N° Facturas</th>' in guias
    assert guias.index('<th>N° cotización</th>') < guias.index('<th>N° PV (Pedido de venta)</th>') < guias.index('<th>N° Facturas</th>')
    fac = html[html.index('<div id="comprobantes"'):]
    fac = fac[:fac.index('</thead>')]
    orden = [fac.index(t) for t in ('<th>N° cotización</th>', '<th>N° PV (Pedido de venta)</th>', '<th>N° Guía</th>', '<th>N° Factura</th>')]
    assert orden == sorted(orden) and '<th>Documento</th>' not in fac
    js = _leer('static/js/ventas.js')
    assert 'function mostrarErrorStockDespacho' in js and "response.codigo === 'falta_stock'" in js
    assert 'function faltanDatosParihuela' in js
    flujo = _leer('templates/compras/flujo.html')
    assert 'id="btnVerUltimaFactura"' in flujo and 'id="facVerModal"' in flujo and 'id="facNoCuadra"' in flujo
    cjs = _leer('static/js/compras_flujo.js')
    assert 'data-extra-pid' in cjs and 'Extra para stock' in cjs and "r.codigo === 'no_cuadra'" in cjs
    css = _leer('static/css/compras_flujo.css')
    assert '.est-aprobada{background:#00C853' in css and '.com-step.actual span{border-color:#E6A800;background:#FFD600' in css
