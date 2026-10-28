"""
Lote del 27-28/10/2026 (Erika): distrito automático del PV, cita con reprogramaciones, N° de despacho corto,
reporte de cumplimiento, sin "Rechazado por el cliente" ni "N° de ingreso" en Entregas, y recepción con diferencia
que exige explicar qué pasó. Datos inventados, solo en la base local.
"""
import json
from pathlib import Path

from tests.test_inventario import _sql

RAIZ = Path(__file__).resolve().parent.parent
PV = 'PV-KCF-ZZ2810'


def _pv(lugar, distrito=None):
    _sql("DELETE FROM despachos WHERE pc_numero = %s", (PV,), fetch=False)
    _sql("DELETE FROM pedido_compra_pc WHERE numero = %s", (PV,), fetch=False)
    _sql("""INSERT INTO pedido_compra_pc (numero, cliente, ruc, estado, items_json, fecha, lugar_entrega)
            VALUES (%s, 'CLIENTE ZZ 2810', '20100070970', 'Pendiente', %s, NOW() - INTERVAL '5 days', %s)""",
         (PV, json.dumps([{'codigo': 'ZZ2810', 'producto': 'Guante ZZ', 'cantidad_pc': 3, 'precio_pc': 10}]), lugar), fetch=False)
    if distrito is not None:
        from routes import distrito_entrega
        distrito_entrega.asegurar_columna()
        _sql("UPDATE pedido_compra_pc SET distrito_entrega = %s WHERE numero = %s", (distrito, PV), fetch=False)
    return _sql("SELECT id FROM pedido_compra_pc WHERE numero = %s", (PV,))[0][0]


def test_distrito_sale_solo(app):
    from routes import distrito_entrega as de
    with app.app_context():
        assert de.resolver({'lugar_entrega': 'Recoge el cliente en nuestro local', 'numero': 'PV-KCF-000001'})['origen'] == 'recojo'
        assert de.resolver({'lugar_entrega': 'Recoge el cliente en nuestro local', 'numero': 'PV-AGD-000001'})['distrito'] == 'Breña'
        r = de.resolver({'lugar_entrega': 'Av. Argentina 123, Lima', 'distrito_entrega': 'Callao'})
        assert r['distrito'] == 'Callao' and r['origen'] == 'escrito'
        assert de.resolver({'lugar_entrega': 'Calle sin nada 45'})['distrito'] == ''


def test_distrito_en_entregas_no_se_escribe_a_mano(admin):
    _pv('Av. Siempre Viva 742', 'Ate')
    _sql("""INSERT INTO despachos (numero, cliente, ruc, estado, items_json, pc_numero)
            VALUES ('DESP-ZZ-2810', 'CLIENTE ZZ 2810', '20100070970', 'Pendiente', '[]', %s)""", (PV,), fetch=False)
    did = _sql("SELECT id FROM despachos WHERE numero = 'DESP-ZZ-2810'")[0][0]
    r = admin.post(f'/ventas/api/despachos/{did}/dato', json={'campo': 'distrito', 'valor': 'Miraflores'})
    assert r.status_code == 400 and 'PV' in r.get_json()['error']
    filas = admin.get('/ventas/api/despachos/listar').get_json()['data']
    fila = next(x for x in filas if x['numero'] == 'DESP-ZZ-2810')
    assert fila['distrito'] == 'Ate' and fila['ingreso_cliente'] == ''


def test_cita_reprogramada_con_motivo_e_historial(admin):
    _pv('Av. Siempre Viva 742', 'Ate')
    _sql("""INSERT INTO despachos (numero, cliente, ruc, estado, items_json, pc_numero)
            VALUES ('DESP-ZZ-2811', 'CLIENTE ZZ 2810', '20100070970', 'Despachado', '[]', %s)""", (PV,), fetch=False)
    did = _sql("SELECT id FROM despachos WHERE numero = 'DESP-ZZ-2811'")[0][0]
    assert admin.post(f'/ventas/api/despachos/{did}/cita', json={'fecha_cita': '2026-11-03'}).status_code == 200
    # Cambiarla sin motivo no se puede; segunda y tercera cita con motivo sí
    assert admin.post(f'/ventas/api/despachos/{did}/cita', json={'fecha_cita': '2026-11-05'}).status_code == 400
    assert admin.post(f'/ventas/api/despachos/{did}/cita', json={'fecha_cita': '2026-11-05', 'motivo': 'No hubo transporte'}).status_code == 200
    assert admin.post(f'/ventas/api/despachos/{did}/cita', json={'fecha_cita': '2026-11-10', 'motivo': 'Otro'}).status_code == 400
    r = admin.post(f'/ventas/api/despachos/{did}/cita', json={'fecha_cita': '2026-11-10', 'motivo': 'Otro', 'comentario': 'Feriado'})
    assert r.status_code == 200
    h = admin.get(f'/ventas/api/despachos/{did}/reprogramaciones').get_json()['data']
    assert h['fecha_cita_inicial'] == '03/11/2026' and len(h['historial']) == 2
    assert h['historial'][0]['motivo'] == 'No hubo transporte' and h['historial'][1]['comentario'] == 'Feriado'


def test_entregas_sin_rechazo_ni_ingreso_y_dos_columnas():
    js = (RAIZ / 'static/js/ventas.js').read_text(encoding='utf-8')
    html = (RAIZ / 'templates/ventas/index.html').read_text(encoding='utf-8')
    assert "abrirEntregaDespacho(${r.id}, 'rechazar')" not in js
    assert 'entregaIngreso' not in js
    assert 'Fecha programada (cita)' in html and 'Fecha real de entrega' in html


def test_numero_de_despacho_corto(app):
    from routes.ventas import numero_despacho_nuevo
    with app.test_request_context():
        n = numero_despacho_nuevo('PV-KCF-000029')
        assert n.startswith('DESP-KCF-') and len(n) == len('DESP-KCF-000001')
        assert numero_despacho_nuevo('PV-AGD-000003').startswith('DESP-AGD-')


def test_reporte_cumplimiento_solo_erika(admin, vendedor):
    _pv('Av. Siempre Viva 742', 'Ate')
    pid = _sql("SELECT id FROM pedido_compra_pc WHERE numero = %s", (PV,))[0][0]
    _sql("""INSERT INTO despachos (numero, cliente, ruc, estado, items_json, pc_numero, pc_id, fecha_cita, fecha_entrega_real)
            VALUES ('DESP-ZZ-2812', 'CLIENTE ZZ 2810', '20100070970', 'Entregado', '[]', %s, %s, NOW() - INTERVAL '2 days',
                    (NOW() - INTERVAL '1 day')::date)""", (PV, pid), fetch=False)
    assert admin.post('/api/empresa_activa', json={'codigo': 'TODAS'}).status_code == 200
    r = admin.get('/reportes/api/reporte/cumplimiento?cliente=ZZ%202810&desde=2026-01-01&hasta=2030-12-31')
    assert r.status_code == 200, r.get_data(as_text=True)
    filas = r.get_json()['data']['filas']
    fila = next(x for x in filas if PV in json.dumps(x, default=str))
    assert 'Tarde' in json.dumps(fila, default=str)
    assert vendedor.get('/reportes/api/reporte/cumplimiento').status_code in (302, 403)


def test_avisos_en_vinetas_en_todos_los_modulos():
    base = (RAIZ / 'templates/base.html').read_text(encoding='utf-8')
    assert 'js/avisos.js' in base
    for f in ('ventas.js', 'compras.js', 'herramientas.js', 'maestros.js', 'compras_flujo.js'):
        assert 'Aviso.' in (RAIZ / 'static/js' / f).read_text(encoding='utf-8'), f
    cf = (RAIZ / 'static/js/compras_flujo.js').read_text(encoding='utf-8')
    assert 'La OC fue emitida por' in cf and 'avisa a tu jefe inmediato' in cf and '(obligatorio)' in cf


def _cliente_zz(ruc, direccion):
    from routes import distrito_entrega
    distrito_entrega.asegurar_columna()
    _sql("DELETE FROM clientes WHERE numero_documento = %s", (ruc,), fetch=False)
    _sql("""INSERT INTO clientes (tipo_documento, numero_documento, razon_social, direccion_fiscal)
            VALUES ('RUC', %s, 'CLIENTE ZZ DISTRITO', %s)""", (ruc, direccion), fetch=False)


def test_distrito_se_llena_solo_con_lo_ya_elegido(admin):
    """Erika 28/10/2026 12:03: el distrito se elige una sola vez y luego se llena solo."""
    from routes import distrito_entrega
    ruc, dire = '20999000281', 'MZA. B LOTE 17 URB. ZZ COBIAN'
    _cliente_zz(ruc, dire)
    _sql("DELETE FROM pedido_compra_pc WHERE numero IN ('PV-KCF-ZZD1', 'PV-KCF-ZZD2')", fetch=False)
    for n in ('PV-KCF-ZZD1', 'PV-KCF-ZZD2'):
        _sql("""INSERT INTO pedido_compra_pc (numero, cliente, ruc, estado, items_json, fecha, lugar_entrega)
                VALUES (%s, 'CLIENTE ZZ DISTRITO', %s, 'Pendiente', '[]', NOW(), %s)""", (n, ruc, dire), fetch=False)
    # Antes de elegirlo: no se sabe
    r = admin.get('/ventas/api/pv/distrito_sugerido', query_string={'lugar': dire, 'ruc': ruc}).get_json()['data']
    assert r['distrito'] == ''
    # Se elige una vez en el primer PV: queda en el cliente (la entrega es su dirección fiscal)
    pid = _sql("SELECT id FROM pedido_compra_pc WHERE numero = 'PV-KCF-ZZD1'")[0][0]
    distrito_entrega.guardar(pid, 'el agustino')
    assert _sql("SELECT distrito_fiscal, distrito_fiscal_fuente FROM clientes WHERE numero_documento = %s", (ruc,))[0] == ('El Agustino', 'elegido')
    r = admin.get('/ventas/api/pv/distrito_sugerido', query_string={'lugar': dire, 'ruc': ruc}).get_json()['data']
    assert r['distrito'] == 'El Agustino' and r['origen'] == 'cliente_guardado'
    # Otro cliente que entrega en esa misma dirección: sale del PV anterior
    distrito_entrega._hist['t'] = 0
    r = distrito_entrega.sugerir(dire.lower(), '20111111111')
    assert r['distrito'] == 'El Agustino' and r['origen'] == 'historial' and 'PV-KCF-ZZD1' in r['texto']
    # El segundo PV, sin tocarlo, ya no sale en rojo en la lista
    filas = [{'numero': 'PV-KCF-ZZD2', 'ruc': ruc, 'lugar_entrega': dire}]
    distrito_entrega.completar_lista(filas)
    assert filas[0]['distrito_entrega_ver'] == 'El Agustino'


def test_distrito_de_sunat_solo_si_entrega_en_domicilio_fiscal(app, monkeypatch):
    from routes import distrito_entrega, consulta_ruc
    ruc, dire = '20999000282', 'CAL. ZZ NRO 10 URB. SIN NOMBRE'
    _cliente_zz(ruc, dire)
    monkeypatch.setattr(consulta_ruc, '_token', lambda: 'x')
    monkeypatch.setattr(consulta_ruc, 'consultar_ruc_externo',
                        lambda r: {'razon_social': 'ZZ', 'direccion': dire, 'distrito': 'SAN JUAN DE LURIGANCHO'})
    with app.app_context():
        # Entrega en otra dirección: no se usa el distrito fiscal
        assert distrito_entrega.sugerir('Obra en Av. Desconocida 1', ruc)['distrito'] == ''
        r = distrito_entrega.sugerir(dire, ruc)
        assert r['distrito'] == 'San Juan de Lurigancho' and r['origen'] == 'sunat'
    assert _sql("SELECT distrito_fiscal_fuente FROM clientes WHERE numero_documento = %s", (ruc,))[0][0] == 'sunat'


def test_formulario_pv_pide_distrito_al_servidor():
    js = (RAIZ / 'static/js/distrito_pv.js').read_text(encoding='utf-8')
    assert '/ventas/api/pv/distrito_sugerido' in js and "$('pcRuc')" in js


def test_compras_documentos_en_orden_y_ya_pedido_al_proveedor():
    js = (RAIZ / 'static/js/compras_flujo.js').read_text(encoding='utf-8')
    i = js.index('function docsPedido')
    bloque = js[i:i + 800]
    assert bloque.index('PV (Pedido de venta)') < bloque.index('PC (Pedido del cliente)') < bloque.index('Cotización') < bloque.index('N° despacho')
    assert 'Ya pedido al proveedor' in js and 'Ya en órdenes' not in js and 'comprado_por_aprobar' in js
