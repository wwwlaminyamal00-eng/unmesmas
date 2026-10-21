"""
Pedido de Erika del 19/10/2026 (noche, prompt de Adriel + audio):
  - PC: N° interno automático por empresa + "N° OC del cliente" opcional; condición de pago en blanco y obligatoria.
  - Cotización: no se guarda sin condición de pago, tiempo de entrega, transporte y parihuela.
  - Factura: la condición sale del PC (luego guía, luego cliente), nunca de la cotización; observaciones con mayúscula.
  - Clientes: "Crédito aprobado" exige días; "Contado" deja los días en 0.
  - Contraseñas: el administrador asigna una nueva sin pedir la anterior; las antiguas sin cifrar se cifran al entrar.
  - Guía creada desde un despacho queda vinculada a ese despacho.
  - Ventanas de "¿Qué hacer ahora?" y máximo 2 decimales.
Datos inventados, solo en la base local de pruebas.
"""
import re
import threading

import pytest
from werkzeug.security import generate_password_hash

from tests.conftest import _login
from tests.test_inventario import _sql
from utils import normalizar_condicion, mayuscula_inicial


def _pc(http, **extra):
    data = {'fecha': '2026-10-19 09:30:00', 'cliente': 'CLIENTE INDUSTRIAL S.A.C.', 'ruc': '20100070970',
            'monto': 100, 'condicion_pago': 'Crédito 45 días', 'lugar_entrega': 'Av. Lima 1',
            'items': [{'codigo': 'PRD-0001', 'producto': 'GUANTE DE NITRILO', 'cantidad_pc': 2, 'precio_pc': 50, 'stock': 0}],
            'valida_precios': True, 'valida_cantidades': True, 'valida_entrega': True, 'valida_montos': True,
            'valida_transporte': True, 'valida_vigencia': True, 'valida_productos': True,
            'estado': 'PC conforme', 'req_compra': 'Sí'}
    data.update(extra)
    return http.post('/ventas/api/pedido-compra/guardar', json=data)


def test_normalizar_condicion_escribe_igual_en_todo():
    assert normalizar_condicion('Credito 30 Dias') == 'Crédito 30 días'
    assert normalizar_condicion('Crédito a 30 días') == 'Crédito 30 días'
    assert normalizar_condicion('CONTADO') == 'Contado'
    assert normalizar_condicion('contra entrega') == 'Contra entrega'
    assert normalizar_condicion('') == '' and normalizar_condicion('Seleccione') == ''
    assert normalizar_condicion('Personalizado') == ''
    assert mayuscula_inicial('  pago parcial') == 'Pago parcial'


# ---------------------------------------------------------------- PC
def test_pc_sin_condicion_de_pago_no_se_guarda(vendedor):
    r = _pc(vendedor, numero='PC-ZZN-SINCOND', condicion_pago='')
    assert r.status_code == 400 and r.json['codigo'] == 'falta_condicion'
    assert 'orden de compra del cliente' in r.json['error']
    assert _sql("SELECT COUNT(*) FROM pedido_compra_pc WHERE numero = 'PC-ZZN-SINCOND'")[0][0] == 0


def test_pc_numero_interno_automatico_y_oc_del_cliente(vendedor):
    a = _pc(vendedor, numero='', oc_cliente='IT40-123456')
    assert a.status_code == 200, a.json
    na = a.json['data']['numero']
    assert re.fullmatch(r'PC-[A-Z0-9]+-\d{6}', na), na
    b = _pc(vendedor, numero='', oc_cliente='')
    nb = b.json['data']['numero']
    assert nb.rsplit('-', 1)[0] == na.rsplit('-', 1)[0] and int(nb[-6:]) == int(na[-6:]) + 1
    fila = _sql("SELECT oc_cliente, condicion_pago FROM pedido_compra_pc WHERE numero = %s", (na,))[0]
    assert fila == ('IT40-123456', 'Crédito 45 días')
    lista = vendedor.get('/ventas/api/pedido-compra/listar').get_json()
    lista = lista.get('data', lista) if isinstance(lista, dict) else lista
    assert next(p for p in lista if p['numero'] == na)['oc_cliente'] == 'IT40-123456'
    # La condición de la cotización NO se copia: si no se manda, la PC no se guarda (ya probado arriba)


def test_pc_numero_no_se_repite_si_se_guardan_a_la_vez(app):
    clientes = [_login(app, 'vendedor', 'Vende#2026!') for _ in range(4)]
    numeros, errores = [], []

    def guardar(c):
        r = _pc(c, numero='')
        (numeros if r.status_code == 200 else errores).append(r.json.get('data', {}).get('numero') if r.status_code == 200 else r.json)

    hilos = [threading.Thread(target=guardar, args=(c,)) for c in clientes]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert not errores and len(set(numeros)) == 4, (numeros, errores)


# ---------------------------------------------------------------- Cotización
def test_cotizacion_exige_los_4_campos(vendedor):
    base = {'cliente_id': 1, 'productos': [{'codigo': 'PRD-0001', 'cantidad': 1, 'valorVenta': 62.6087}],
            'condicion_pago': 'Crédito 30 días', 'tiempo_entrega': '2 días hábiles', 'transporte': 'Auto', 'parihuela': 'No'}
    for campo, nombre in [('condicion_pago', 'Condición de pago'), ('tiempo_entrega', 'Tiempo de entrega'),
                          ('transporte', 'Transporte'), ('parihuela', 'Parihuela')]:
        r = vendedor.post('/ventas/api/cotizaciones/guardar', json={**base, campo: 'Seleccione', 'estado': 'Borrador'})
        assert r.status_code == 400 and r.json['codigo'] == 'faltan_campos'
        assert any(f.startswith(nombre) for f in r.json['faltan']), r.json
    r = vendedor.post('/ventas/api/cotizaciones/guardar', json={**base, 'transporte': '', 'estado': 'Por validar'})
    assert r.status_code == 400 and r.json['error'].startswith('Faltan campos obligatorios para enviar a validación')
    # Con los 4 campos se guarda, y el precio queda con 2 decimales
    r = vendedor.post('/ventas/api/cotizaciones/guardar', json={**base, 'estado': 'Borrador', 'condicion_pago': 'Credito 30 Dias'})
    assert r.status_code == 200, r.json
    cid = r.json['data']['id']
    assert _sql("SELECT condicion_pago FROM cotizaciones WHERE id = %s", (cid,))[0][0] == 'Crédito 30 días'
    precio = _sql("SELECT precio_venta_unitario FROM cotizacion_detalle WHERE cotizacion_id = %s", (cid,))[0][0]
    assert float(precio) == 62.61


# ---------------------------------------------------------------- Factura
def test_factura_toma_la_condicion_del_pc_no_de_la_cotizacion(vendedor):
    assert _pc(vendedor, numero='PC-ZZN-FAC', condicion_pago='Crédito 45 días', oc_cliente='OC-CLI-77').status_code == 200
    origen = vendedor.get('/ventas/api/comprobantes/condicion-origen?pc=PC-ZZN-FAC').json['data']
    assert origen['condicion'] == 'Crédito 45 días' and origen['pc'] == 'PC-ZZN-FAC' and origen['oc_cliente'] == 'OC-CLI-77'
    r = vendedor.post('/ventas/api/comprobantes/guardar', json={
        'tipo': 'FACTURA', 'serie': 'F001', 'cliente': 'CLIENTE INDUSTRIAL S.A.C.', 'ruc': '20100070970',
        'total': 118, 'subtotal': 100, 'igv': 18, 'condicion': '', 'pc': 'PC-ZZN-FAC',
        'observaciones': 'entrega parcial', 'estado': 'Borrador', 'items': []})
    assert r.status_code == 200, r.json
    fila = _sql("SELECT condicion_pago, es_credito, dias_credito, observaciones, orden_compra_cliente FROM comprobantes WHERE id = %s",
                (r.json['data']['id'],))[0]
    assert fila[0] == 'Crédito 45 días' and fila[1] is True and fila[2] == 45
    assert fila[3] == 'Entrega parcial' and fila[4] == 'OC-CLI-77'
    # La lista de Facturas muestra la condición real (antes decía siempre "Contado")
    lista = vendedor.get('/ventas/api/comprobantes/listar').json['data']
    assert next(c for c in lista if c['id'] == r.json['data']['id'])['condicion'] == 'Crédito 45 días'
    # "Credito 30 Dias" escrito distinto ya no cae en "Contado"
    r = vendedor.post('/ventas/api/comprobantes/guardar', json={
        'tipo': 'FACTURA', 'serie': 'F001', 'cliente': 'CLIENTE INDUSTRIAL S.A.C.', 'ruc': '20100070970',
        'total': 118, 'subtotal': 100, 'igv': 18, 'condicion': 'Credito 30 Dias', 'estado': 'Borrador', 'items': []})
    assert _sql("SELECT condicion_pago, dias_credito FROM comprobantes WHERE id = %s", (r.json['data']['id'],))[0] == ('Crédito 30 días', 30)


def test_factura_sin_pc_toma_la_condicion_del_cliente(vendedor, admin):
    _sql("UPDATE clientes SET condicion_pago = 'Crédito aprobado', dias_credito = 60 WHERE numero_documento = '20100070970'", fetch=False)
    try:
        d = vendedor.get('/ventas/api/comprobantes/condicion-origen?ruc=20100070970').json['data']
        assert d['condicion'] == 'Crédito 60 días' and d['fuente'] == 'cliente'
    finally:
        _sql("UPDATE clientes SET condicion_pago = 'Contado', dias_credito = 0 WHERE numero_documento = '20100070970'", fetch=False)


# ---------------------------------------------------------------- Clientes
def test_cliente_credito_exige_dias_y_contado_los_pone_en_cero(admin):
    base = {'razon_social': 'CLIENTE DIAS ZZ', 'numero_documento': '20999000111', 'tipo_documento': 'RUC', 'direccion_fiscal': 'Av. Prueba 1',
            'limite_credito': '0', 'descuento': '0'}
    r = admin.post('/maestros/api/clientes/guardar', json={**base, 'condicion_pago': 'Crédito aprobado', 'dias_credito': '0'})
    assert r.status_code == 400 and r.json['codigo'] == 'dias_credito'
    r = admin.post('/maestros/api/clientes/guardar', json={**base, 'condicion_pago': 'Contado', 'dias_credito': '45'})
    assert r.json['success'], r.json
    assert _sql("SELECT condicion_pago, dias_credito FROM clientes WHERE numero_documento = '20999000111'")[0] == ('Contado', 0)
    cid = _sql("SELECT id FROM clientes WHERE numero_documento = '20999000111'")[0][0]
    r = admin.put(f'/maestros/api/clientes/{cid}', json={**base, 'condicion_pago': 'Crédito aprobado', 'dias_credito': '30'})
    assert r.json['success'], r.json
    assert _sql("SELECT condicion_pago, dias_credito FROM clientes WHERE id = %s", (cid,))[0] == ('Crédito aprobado', 30)
    # La cotización crea clientes con "Crédito 15 días": queda como Crédito aprobado + 15
    r = admin.post('/maestros/api/clientes/guardar', json={'razon_social': 'CLIENTE COT ZZ', 'numero_documento': '20999000222', 'direccion_fiscal': 'Av. Prueba 2', 'limite_credito': '0', 'descuento': '0',
                                                          'condicion_pago': 'Credito 15 Dias'})
    assert r.json['success'], r.json
    assert _sql("SELECT condicion_pago, dias_credito FROM clientes WHERE numero_documento = '20999000222'")[0] == ('Crédito aprobado', 15)


# ---------------------------------------------------------------- Contraseñas
def test_admin_asigna_contrasena_nueva_sin_pedir_la_anterior(app, admin, vendedor):
    uid = _sql("""INSERT INTO usuarios (usuario_sistema, usuario, nombres_apellidos, nombre_completo, correo, password, rol, estado)
                  VALUES ('clavezz', 'clavezz', 'Clave ZZ', 'Clave ZZ', 'clavezz@test.pe', %s, 'vendedor', 'activo') RETURNING id""",
               (generate_password_hash('Vieja#2026!'),))[0][0]
    assert vendedor.post(f'/api/config/usuarios/{uid}/password', json={'password': 'Nueva#2026!'}).status_code in (401, 403)
    assert admin.post(f'/api/config/usuarios/{uid}/password', json={'password': 'corta'}).status_code == 400
    r = admin.post(f'/api/config/usuarios/{uid}/password', json={'password': 'Nueva#2026!'})
    assert r.status_code == 200 and r.json['success'] and 'password_generada' not in r.json['data']
    guardada = _sql("SELECT password FROM usuarios WHERE id = %s", (uid,))[0][0]
    assert guardada.startswith(('scrypt:', 'pbkdf2:')) and 'Nueva#2026!' not in guardada
    _login(app, 'clavezz', 'Nueva#2026!')
    r = admin.post(f'/api/config/usuarios/{uid}/password', json={'generar': True})
    gen = r.json['data']['password_generada']
    _login(app, 'clavezz', gen)
    aud = _sql("SELECT COUNT(*), bool_or(COALESCE(detalle,'') LIKE %s) FROM erp_auditoria WHERE accion = 'cambiar_contraseña'",
               ('%' + gen + '%',))[0]
    assert aud[0] >= 2 and aud[1] is False      # queda en auditoría, sin la contraseña


def test_contrasena_sin_cifrar_se_cifra_al_entrar(app):
    _sql("""INSERT INTO usuarios (usuario_sistema, usuario, nombres_apellidos, nombre_completo, correo, password, rol, estado)
            VALUES ('planozz', 'planozz', 'Plano ZZ', 'Plano ZZ', 'planozz@test.pe', 'Plano#2026!', 'vendedor', 'activo')""", fetch=False)
    _login(app, 'planozz', 'Plano#2026!')
    guardada = _sql("SELECT password FROM usuarios WHERE usuario = 'planozz'")[0][0]
    assert guardada != 'Plano#2026!' and guardada.startswith(('scrypt:', 'pbkdf2:'))
    _login(app, 'planozz', 'Plano#2026!')        # sigue entrando con la misma contraseña


# ---------------------------------------------------------------- Guía ↔ despacho
def test_guia_creada_desde_despacho_queda_vinculada(vendedor):
    # La guía se hace cuando el despacho ya salió (desde el 20/10/2026 sin stock no hay guía de venta)
    _sql("INSERT INTO despachos (numero, cliente, ruc, estado) VALUES ('DSP-ZZN-1', 'CLIENTE', '20100070970', 'Despachado')", fetch=False)
    r = vendedor.post('/ventas/api/guias/guardar', json={
        'serie': 'T001', 'destinatario_nombre': 'CLIENTE', 'ruc_destinatario': '20100070970',
        'items': [{'codigo': 'PRD-0001', 'cantidad': 1}], 'estado': 'Borrador', 'despacho_numero': 'DSP-ZZN-1'})
    assert r.status_code == 200, r.json
    g = r.json['data']
    assert _sql("SELECT guia FROM despachos WHERE numero = 'DSP-ZZN-1'")[0][0] == f"{g['serie']}-{g['numero']}"


# ---------------------------------------------------------------- Pantallas
def test_pantallas_tienen_las_ayudas_y_los_cambios(vendedor):
    js = vendedor.get('/static/js/ventas.js').get_data(as_text=True)
    html = vendedor.get('/ventas').get_data(as_text=True)
    assert '✅ ¡Guía creada con éxito!' in js and 'Paso 1: Ve al menú <b>"Guías de Remisión"</b>' in js
    assert 'Ir a Guías de Remisión' in js and 'Ir a Facturas' in js and "irAPestanaYResaltar('comprobantes'" in js
    assert 'Faltan campos obligatorios para enviar a validación' in js
    assert 'Ojo: No has llenado la información adicional. ¿Seguro que deseas continuar?' in js
    assert "'/ventas/api/comprobantes/condicion-origen?'" in js and 'aplicarCondicionFactura' in js
    # La condición del modal de factura desde cotización ya no se llena con la de la cotización
    assert "cotizacion.condicion_pago === 'Contado' ? 'selected'" not in js
    # PC: N° interno automático, N° OC del cliente, condición en blanco y obligatoria
    assert 'id="pcOcCliente"' in html and 'N° PC interno' in html and '— Elegir (leer OC) —' in html
    assert 'function pcAvisoCondicion' in html
    assert "numeroPC = 'PC-' + isoLima()" not in js
    base = vendedor.get('/index').get_data(as_text=True)
    assert 'window.mostrarPasos' in base and 'window.redondear2' in base and 'abrirNuevaPassword' in base
    assert "'Crédito ' + n + ' días'" in base
