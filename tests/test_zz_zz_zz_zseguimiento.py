"""
Seguimiento comercial (pedido de Erika del 21/10/2026). Cotizaciones inventadas, solo en la base local.
  - Solo gerencia o quien tenga el permiso "Seguimiento".
  - Sin cerrar = Generada / Enviada sin respuesta; ganada = aceptada, facturada o con PC; perdida = rechazada o "No compró".
  - Primera llamada a los 3 días; lo que toca hoy o está atrasado sale primero.
  - Tasa de cierre por vendedora.
  - Registrar llamada pide qué dijo el cliente y cuándo volver a llamar; "No compró" pide motivo.
"""
from datetime import timedelta

import pytest

from tests.test_flujos import sql
from tests.test_permisos_usuarios import base, _usuario, _guardar   # noqa: F401  (base es fixture)
from routes.seguimiento import _ahora

HOY = _ahora().date()


@pytest.fixture(scope='module')
def cots(base):
    kcf = base['emp']['KCF']
    cli = sql("SELECT id FROM clientes ORDER BY id LIMIT 1")[0][0]
    uid = sql("SELECT id FROM usuarios WHERE usuario = 'admin'")[0][0]

    def cot(num, vend, estado, total, dias, validez=None, aceptada=None):
        return sql("""INSERT INTO cotizaciones (numero_cotizacion, cliente_id, usuario_id, estado, total, vendedor, validez_oferta,
                          fecha_creacion, fecha_aceptacion, empresa_id, telefono_cliente, contacto_cliente)
                      VALUES (%s, %s, %s, %s, %s, %s, %s, NOW() - %s * INTERVAL '1 day', %s, %s, '999 888 777', 'Juan Compras')
                      RETURNING id""",
                   (num, cli, uid, estado, total, vend, validez, dias,
                    (HOY - timedelta(days=aceptada)) if aceptada is not None else None, kcf))[0][0]
    ids = {
        'A1': cot('COT-SEG-A1', 'Vendedora Seg A', 'Generada', 1000, 1),
        'A2': cot('COT-SEG-A2', 'Vendedora Seg A', 'Generada', 2000, 10, '15 días'),
        'A3': cot('COT-SEG-A3', 'Vendedora Seg A', 'Aceptada por Cliente', 3000, 20, None, 16),
        'A4': cot('COT-SEG-A4', 'Vendedora Seg A', 'Generada', 4000, 12),
        'A5': cot('COT-SEG-A5', 'Vendedora Seg A', 'Generada', 500, 40, '30 días'),
        'B1': cot('COT-SEG-B1', 'Vendedora Seg B', 'Rechazada', 700, 5),
        'B2': cot('COT-SEG-B2', 'Vendedora Seg B', 'Borrador', 800, 2),
        'B3': cot('COT-SEG-B3', 'Vendedora Seg B', 'Anulada', 9999, 2),
    }
    sql("""INSERT INTO pedido_compra_pc (numero, cliente, ruc, monto, cotizacion_id, cotizacion_numero, estado, fecha)
           VALUES ('PC-SEG-1', 'CLIENTE', '20100070970', 4000, %s, 'COT-SEG-A4', 'PC conforme', NOW())""", (ids['A4'],))
    return {'ids': ids, 'kcf': kcf}


def _resumen(cliente, kcf, dias=90):
    r = cliente.get(f'/seguimiento/api/resumen?empresa_id={kcf}&dias={dias}')
    assert r.status_code == 200, r.json
    return r.json['data']


def _mias(lista):
    return {c['numero'][-2:]: c for c in lista if c['numero'].startswith('COT-SEG-')}


def test_solo_gerencia_o_permiso(app, admin, vendedor, base):
    assert admin.get('/seguimiento').status_code == 200
    assert 'data-modulo="seguimiento"' in admin.get('/seguimiento').get_data(as_text=True)
    r = vendedor.get('/seguimiento/api/resumen')
    assert r.status_code == 403 and r.json['codigo'] == 'sin_permiso'
    sql("""INSERT INTO erp_submodulos (modulo_id, orden, codigo, nombre, estado)
           SELECT m.id, 5, 'SEGUIMIENTO_COMERCIAL', 'Seguimiento comercial', 'activo' FROM erp_modulos m
           WHERE m.codigo = 'VENTAS' AND NOT EXISTS (SELECT 1 FROM erp_submodulos WHERE codigo = 'SEGUIMIENTO_COMERCIAL')""")
    from werkzeug.security import generate_password_hash
    from conftest import _login
    from routes.acceso import limpiar_cache
    uid, _ = _usuario(base, 'seg_usuario', empresas=('KCF',))
    sql("UPDATE usuarios SET password = %s WHERE id = %s", (generate_password_hash('Segui#2026!'), uid))
    _guardar(admin, uid, base['emp']['KCF'], [{'submodulo_codigo': 'COTIZACIONES', 'puede_ver': True}])
    limpiar_cache()
    h = _login(app, 'seg_usuario', 'Segui#2026!')
    assert h.get('/seguimiento/api/resumen').status_code == 403         # ver Cotizaciones no basta
    _guardar(admin, uid, base['emp']['KCF'], [{'submodulo_codigo': 'SEGUIMIENTO_COMERCIAL', 'puede_ver': True}])
    limpiar_cache()
    assert h.get('/seguimiento').status_code == 200


def test_vigencia():
    from routes.seguimiento import dias_vigencia
    assert dias_vigencia('15 días') == 15
    assert dias_vigencia('1 mes') == 30
    assert dias_vigencia('2 semanas') == 14
    assert dias_vigencia('') is None and dias_vigencia('Según stock') is None


def test_situacion_y_llamar_hoy(admin, cots):
    d = _resumen(admin, cots['kcf'])
    ab = _mias(d['abiertas'])
    assert set(ab) == {'A1', 'A2', 'A5'}                                 # A3 aceptada, A4 con PC, B* no
    assert ab['A1']['llamar_hoy'] is False and ab['A1']['proxima_llamada'] == (HOY + timedelta(days=2)).isoformat()
    assert ab['A2']['llamar_hoy'] is True and ab['A2']['atraso'] == 7 and ab['A2']['vencida'] is False
    assert ab['A5']['vencida'] is True
    assert ab['A2']['telefono'] == '999 888 777'
    orden = [c['numero'] for c in d['abiertas'] if c['numero'].startswith('COT-SEG-')]
    assert orden.index('COT-SEG-A5') < orden.index('COT-SEG-A2') < orden.index('COT-SEG-A1')   # el más atrasado primero
    assert 'B2' in _mias(d['por_enviar'])
    assert not any(c['numero'] == 'COT-SEG-B3' for c in d['abiertas'] + d['por_enviar'])     # anulada no cuenta


def test_tasa_de_cierre_por_vendedora(admin, cots):
    d = _resumen(admin, cots['kcf'])
    v = {x['vendedor']: x for x in d['vendedoras']}
    a = v['Vendedora Seg A']
    assert (a['enviadas'], a['ganadas'], a['perdidas'], a['abiertas']) == (5, 2, 0, 3)
    assert a['tasa'] == 40.0 and a['monto_ganado'] == 7000.0 and a['dias'] == 4.0
    b = v['Vendedora Seg B']
    assert (b['enviadas'], b['perdidas'], b['tasa']) == (1, 1, 0.0)        # el borrador no cuenta como enviada
    d30 = _resumen(admin, cots['kcf'], 30)
    assert {x['vendedor']: x for x in d30['vendedoras']}['Vendedora Seg A']['enviadas'] == 4   # A5 es de hace 40 días


def test_registrar_llamada_y_no_compro(admin, cots):
    ids = cots['ids']
    url = f"/seguimiento/api/cotizacion/{ids['A2']}/gestion"
    manana = (HOY + timedelta(days=1)).isoformat()
    r = admin.post(url, json={'medio': 'Llamada', 'comentario': '', 'proxima_llamada': manana})
    assert r.status_code == 400 and 'qué dijo' in r.json['error']
    r = admin.post(url, json={'medio': 'Llamada', 'comentario': 'Llamar luego', 'proxima_llamada': (HOY - timedelta(days=1)).isoformat()})
    assert r.status_code == 400 and 'pasado' in r.json['error']
    assert admin.post(url, json={'medio': 'Fax', 'comentario': 'hola', 'proxima_llamada': manana}).status_code == 400
    r = admin.post(url, json={'medio': 'WhatsApp', 'comentario': 'lo revisa con su jefe', 'proxima_llamada': manana})
    assert r.status_code == 200, r.json
    a2 = _mias(_resumen(admin, cots['kcf'])['abiertas'])['A2']
    assert a2['llamar_hoy'] is False and a2['proxima_llamada'] == manana
    assert a2['ultima']['comentario'] == 'Lo revisa con su jefe' and a2['ultima']['medio'] == 'WhatsApp'
    # Solo a lo que ya se mandó al cliente
    r = admin.post(f"/seguimiento/api/cotizacion/{ids['B2']}/gestion", json={'medio': 'Llamada', 'comentario': 'hola', 'proxima_llamada': manana})
    assert r.status_code == 400 and 'Borrador' in r.json['error']
    # No compró
    url5 = f"/seguimiento/api/cotizacion/{ids['A5']}/gestion"
    r = admin.post(url5, json={'medio': 'Llamada', 'comentario': 'Compró a otro', 'no_compro': True})
    assert r.status_code == 400 and 'por qué' in r.json['error']
    assert admin.post(url5, json={'medio': 'Llamada', 'comentario': 'Compró a otro', 'no_compro': True,
                                  'motivo_cierre': 'Precio alto'}).status_code == 200
    assert admin.post(url5, json={'medio': 'Llamada', 'comentario': 'otra vez', 'no_compro': True,
                                  'motivo_cierre': 'Precio alto'}).status_code == 400
    d = _resumen(admin, cots['kcf'], 365)
    assert 'A5' not in _mias(d['abiertas'])
    assert _mias(d['perdidas'])['A5']['motivo_perdida'] == 'Precio alto'
    assert sql("SELECT estado FROM cotizaciones WHERE id = %s", (ids['A5'],))[0][0] == 'Generada'   # Ventas no cambia
    h = admin.get(f"/seguimiento/api/historial?empresa_id={cots['kcf']}").json['data']
    mios = [x for x in h if (x['numero'] or '').startswith('COT-SEG-')]
    assert len(mios) == 2 and mios[0]['cierre'] == 'No compró' and mios[0]['creado_por']
