"""
Pruebas de los módulos 9 "Herramientas" y 10 "Papelera / Auditoría" (pedido de Erika 16/10/2026):
  - La auditoría registra crear / editar / anular / eliminar (disparadores) y login / logout, sin contraseñas.
  - La papelera lista anulados y eliminados; restaurar y borrar definitivo solo administradores (y con doble confirmación).
  - Importar detecta duplicados y no duplica; exportar nunca saca contraseñas.
  - Integridad detecta un huérfano; revisar numeraciones avisa huecos y NO renumera.
"""
import io
import json

import pytest

from conftest import _login
from tests.test_flujos import sql, nueva_cotizacion, factura


@pytest.fixture(scope='module')
def adm(app):
    return _login(app, 'admin', 'Admin#2026!')


@pytest.fixture(scope='module')
def vend(app):
    return _login(app, 'vendedor', 'Vende#2026!')


def auditoria(tabla, registro_id, accion=None):
    q = "SELECT accion, data_anterior, data_nueva, usuario_nombre, detalle FROM erp_auditoria WHERE tabla = %s AND registro_id::text = %s"
    p = [tabla, str(registro_id)]
    if accion:
        q += " AND accion = %s"
        p.append(accion)
    return sql(q + " ORDER BY created_at, ctid", p)


# ============================================================
# AUDITORÍA
# ============================================================
def test_auditoria_crear_editar_eliminar(adm):
    adm.get('/papelera')  # primer uso: crea columnas y disparadores
    pid = sql("""INSERT INTO productos (familia, codigo, descripcion, unidad, costo_unitario, precio_unitario, stock, activo)
                 VALUES ('GENERAL', 'AUD-001', 'PRODUCTO AUDITADO', 'UND', 1, 2, 0, true) RETURNING id""")[0][0]
    sql("UPDATE productos SET descripcion = 'PRODUCTO AUDITADO 2' WHERE id = %s", (pid,))
    sql("UPDATE productos SET stock = 5 WHERE id = %s", (pid,))   # solo stock calculado: no cuenta como edición
    sql("DELETE FROM productos WHERE id = %s", (pid,))
    filas = auditoria('productos', pid)
    assert [f[0] for f in filas] == ['crear', 'editar', 'eliminar']
    assert filas[1][1]['descripcion'] == 'PRODUCTO AUDITADO' and filas[1][2]['descripcion'] == 'PRODUCTO AUDITADO 2'
    assert filas[2][1]['codigo'] == 'AUD-001' and filas[2][2] is None  # datos completos antes de borrar


def test_auditoria_anular_y_aprobar_por_estado(adm, vend, aprobador):
    cid = nueva_cotizacion(vend).json['data']['id']
    r = vend.delete(f'/ventas/api/cotizaciones/{cid}', json={'motivo': 'Cliente desistió'})
    assert r.status_code == 200, r.json
    acciones = [f[0] for f in auditoria('cotizaciones', cid)]
    assert 'crear' in acciones and 'anular' in acciones


def test_auditoria_nunca_guarda_password(adm):
    uid = sql("SELECT id FROM usuarios WHERE usuario_sistema = 'legado'")[0][0]
    sql("UPDATE usuarios SET password = 'otra-clave-plana' WHERE id = %s", (uid,))
    sql("UPDATE usuarios SET telefono = '999111222' WHERE id = %s", (uid,))
    filas = auditoria('usuarios', uid)
    assert filas and all('password' not in json.dumps([f[1], f[2]]) for f in filas)
    assert any('contraseña' in (f[4] or '') for f in filas)
    sql("UPDATE usuarios SET password = 'clave-plana-123' WHERE id = %s", (uid,))


def test_usuario_llega_al_disparador_desde_get_connection(adm):
    """database.get_connection marca el usuario de la sesión solo para la transacción (pooler de Supabase)."""
    import database
    from routes import multiempresa
    multiempresa._cache['t'] = 0  # caché vencida: no debe entrar en bucle (get_connection no consulta la base)
    with adm.application.test_request_context():
        from flask import session
        session['usuario_id'] = sql("SELECT id FROM usuarios WHERE usuario_sistema = 'admin'")[0][0]
        session['nombre_completo'] = 'Admin Pruebas'
        conn = database.get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE clientes SET observaciones = 'auditado' WHERE numero_documento = '20100070970' RETURNING id")
        cli = cur.fetchone()[0]
        conn.commit()
        conn.close()
    filas = auditoria('clientes', cli, 'editar')
    assert filas[-1][3] == 'Admin Pruebas'
    # Una conexión sin petición web no hereda a nadie (el ajuste es solo de esa transacción)
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT current_setting('erp.usuario_nombre', true)")
    assert (cur.fetchone()[0] or '') == ''
    conn.close()


def test_login_y_logout_quedan_en_auditoria(app):
    c = _login(app, 'hellen', 'Valida#2026!')
    c.get('/logout')
    app.test_client().post('/login', data={'usuario': 'hellen', 'password': 'mala', 'empresa': 'KCF'})
    acciones = [f[0] for f in sql("""SELECT accion FROM erp_auditoria WHERE accion IN ('login', 'logout', 'login_fallido')
                                     AND (usuario_nombre ILIKE 'hellen%%') ORDER BY created_at""")]
    assert acciones[-3:] == ['login', 'logout', 'login_fallido']
    assert not sql("SELECT 1 FROM erp_auditoria WHERE detalle ILIKE '%%mala%%' OR data_nueva::text ILIKE '%%mala%%'")


def test_auditoria_solo_admin_filtros_y_exportar(adm, vend):
    assert vend.get('/papelera/api/auditoria').status_code == 403
    r = adm.get('/papelera/api/auditoria?accion=eliminar&modulo=Maestros · Productos')
    assert r.status_code == 200 and r.json['total'] >= 1
    assert all(f['accion'] == 'eliminar' for f in r.json['data'])
    r = adm.get('/papelera/api/auditoria/exportar?formato=csv&accion=login')
    assert r.status_code == 200 and 'Usuario' in r.get_data(as_text=True).splitlines()[0]
    assert adm.get('/papelera/api/auditoria/exportar?formato=xlsx').data[:2] == b'PK'


# ============================================================
# PAPELERA
# ============================================================
def _items(cliente, **filtros):
    q = '&'.join(f'{k}={v}' for k, v in filtros.items())
    r = cliente.get('/papelera/api/lista?empresa=TODAS&' + q)
    assert r.status_code == 200, r.json
    return r.json['data']


@pytest.fixture(scope='module')
def anulados(adm, vend):
    cid = nueva_cotizacion(vend).json['data']['id']
    assert vend.delete(f'/ventas/api/cotizaciones/{cid}', json={'motivo': 'Precio alto'}).status_code == 200
    pc = sql("""INSERT INTO pedido_compra_pc (numero, cliente, ruc, estado) VALUES ('PC-PAP-0001', 'CLIENTE X', '20100070970', 'Anulado')
                RETURNING id""")[0][0]
    f = factura(vend, serie='F901').json['data']['id']
    sql("UPDATE comprobantes SET estado_sunat = 'ANULADO' WHERE id = %s", (f,))
    return {'cot': cid, 'pc': pc, 'fact': f}


def test_papelera_lista_anulados_y_eliminados(vend, anulados):
    items = {i['clave']: i for i in _items(vend)}
    cot = items[f"cot:{anulados['cot']}"]
    assert cot['motivo'] == 'Precio alto' and cot['modulo'] == 'Cotizaciones' and cot['usuario']
    assert f"pc:{anulados['pc']}" in items
    fact = items[f"fact:{anulados['fact']}"]
    assert not fact['puede_restaurar'] and 'SUNAT' in fact['por_que_no']
    # vendedor ve, pero no puede restaurar ni borrar
    assert not cot['puede_restaurar'] and not cot['puede_borrar']
    assert [i for i in _items(vend, modulo='Pedidos (PC)')] and all(i['modulo'] == 'Pedidos (PC)' for i in _items(vend, modulo='Pedidos (PC)'))


def test_restaurar_solo_admin(adm, vend, anulados):
    clave = f"cot:{anulados['cot']}"
    assert vend.post('/papelera/api/restaurar', json={'clave': clave}).status_code == 403
    assert sql("SELECT estado FROM cotizaciones WHERE id = %s", (anulados['cot'],))[0][0] == 'Anulada'
    r = adm.post('/papelera/api/restaurar', json={'clave': clave})
    assert r.status_code == 200, r.json
    assert sql("SELECT estado FROM cotizaciones WHERE id = %s", (anulados['cot'],))[0][0] == 'Borrador'
    assert auditoria('cotizaciones', anulados['cot'], 'restaurar')
    # facturas anuladas no se restauran
    r = adm.post('/papelera/api/restaurar', json={'clave': f"fact:{anulados['fact']}"})
    assert r.status_code == 409
    assert sql("SELECT estado_sunat FROM comprobantes WHERE id = %s", (anulados['fact'],))[0][0] == 'ANULADO'


def test_borrar_definitivo_solo_admin_con_doble_confirmacion(adm, vend, anulados):
    clave = f"pc:{anulados['pc']}"
    ok = {'clave': clave, 'confirmacion': 'BORRAR', 'numero': 'PC-PAP-0001'}
    assert vend.post('/papelera/api/borrar', json=ok).status_code == 403
    assert adm.post('/papelera/api/borrar', json={'clave': clave, 'confirmacion': 'si', 'numero': 'PC-PAP-0001'}).status_code == 400
    assert adm.post('/papelera/api/borrar', json={'clave': clave, 'confirmacion': 'BORRAR', 'numero': 'PC-OTRO'}).status_code == 400
    assert sql("SELECT 1 FROM pedido_compra_pc WHERE id = %s", (anulados['pc'],))
    r = adm.post('/papelera/api/borrar', json=ok)
    assert r.status_code == 200, r.json
    assert not sql("SELECT 1 FROM pedido_compra_pc WHERE id = %s", (anulados['pc'],))
    fila = auditoria('pedido_compra_pc', anulados['pc'], 'borrar_definitivo')
    assert fila and fila[0][1]['registro']['numero'] == 'PC-PAP-0001'  # datos completos antes de borrar
    # ya no aparece en la papelera (queda en auditoría)
    assert clave not in {i['clave'] for i in _items(adm)}
    # una factura anulada nunca se borra desde aquí
    r = adm.post('/papelera/api/borrar', json={'clave': f"fact:{anulados['fact']}", 'confirmacion': 'BORRAR', 'numero': 'x'})
    assert r.status_code == 409


def test_borrados_fisicos_aparecen_y_se_restauran(adm):
    cid = sql("""INSERT INTO clientes (tipo_documento, numero_documento, razon_social, direccion_fiscal, activo)
                 VALUES ('RUC', '20999888777', 'CLIENTE BORRADO S.A.C.', 'Jr. Uno 1', true) RETURNING id""")[0][0]
    sql("DELETE FROM clientes WHERE id = %s", (cid,))
    item = next(i for i in _items(adm, modulo='Registros borrados') if i['tabla'] == 'clientes' and str(i['id']) == str(cid))
    assert item['puede_restaurar']
    r = adm.post('/papelera/api/restaurar', json={'clave': item['clave']})
    assert r.status_code == 200, r.json
    assert sql("SELECT razon_social FROM clientes WHERE id = %s", (cid,))[0][0] == 'CLIENTE BORRADO S.A.C.'


# ============================================================
# HERRAMIENTAS
# ============================================================
def test_herramientas_solo_admin(vend, adm):
    assert vend.get('/herramientas').status_code == 302
    for url in ('/herramientas/api/salud', '/herramientas/api/integridad', '/herramientas/api/exportar?tabla=clientes'):
        assert vend.get(url).status_code == 403
    assert vend.get('/herramientas/api/revisar_stock').status_code == 403
    assert adm.get('/herramientas').status_code == 200


def _csv(texto):
    return {'archivo': (io.BytesIO(texto.encode('utf-8')), 'carga.csv')}


def test_importar_con_duplicados(adm):
    texto = ('Código;Descripción;Familia;Unidad;Marca;Costo unitario sin IGV\n'
             'PRD-0001;GUANTE CAMBIADO;GENERAL;PAR;ANSELL;11\n'      # ya existe
             'IMP-0001;LENTE DE SEGURIDAD;EPP;UND;3M;8.5\n'          # nuevo
             'IMP-0001;LENTE REPETIDO;EPP;UND;3M;9\n'                # repetido en el archivo
             'IMP-0002;;EPP;UND;3M;abc\n'                            # sin descripción y costo inválido
             'IMP-0003;BOTA PUNTA ACERO;;;CAT;\n')                   # familia/unidad por defecto
    r = adm.post('/herramientas/api/importar/productos', data={**_csv(texto), 'confirmar': '0'})
    assert r.status_code == 200, r.json
    assert r.json['resumen'] == {'nuevo': 2, 'actualizar': 0, 'existe': 1, 'error': 2}
    assert not sql("SELECT 1 FROM productos WHERE codigo LIKE 'IMP-%%'")  # la vista previa no guarda
    r = adm.post('/herramientas/api/importar/productos', data={**_csv(texto), 'confirmar': '1'})
    assert r.status_code == 200 and r.json['nuevos'] == 2
    assert sql("SELECT COUNT(*) FROM productos WHERE codigo = 'IMP-0001'")[0][0] == 1
    assert sql("SELECT familia, unidad FROM productos WHERE codigo = 'IMP-0003'")[0] == ('GENERAL', 'UND')
    assert sql("SELECT descripcion FROM productos WHERE codigo = 'PRD-0001'")[0][0] == 'GUANTE DE NITRILO'  # no se tocó
    # Actualizar existentes solo si se marca
    r = adm.post('/herramientas/api/importar/productos', data={**_csv('Código;Marca\nIMP-0001;3M PERU\n'), 'confirmar': '1', 'actualizar': '1'})
    assert r.json['actualizados'] == 1
    assert sql("SELECT marca, descripcion FROM productos WHERE codigo = 'IMP-0001'")[0] == ('3M PERU', 'LENTE DE SEGURIDAD')
    assert sql("SELECT 1 FROM erp_auditoria WHERE accion = 'importar' AND tabla = 'productos'")


def test_importar_clientes_y_proveedores(adm):
    r = adm.post('/herramientas/api/importar/clientes', data={**_csv(
        'RUC o DNI;Razón social;Dirección fiscal\n20100070970;DUPLICADO;Av. X\n20555666777;NUEVO CLIENTE SAC;Av. Y 1\n12345;MAL;Av\n'),
        'confirmar': '1'})
    assert r.status_code == 200, r.json
    assert r.json['resumen'] == {'nuevo': 1, 'actualizar': 0, 'existe': 1, 'error': 1}
    assert sql("SELECT tipo_documento FROM clientes WHERE numero_documento = '20555666777'")[0][0] == 'RUC'
    r = adm.post('/herramientas/api/importar/proveedores', data={**_csv('RUC;Razón social;Dirección\n20600011111;YA;X\n20611122233;PROV NUEVO;Z\n'),
                                                                  'confirmar': '1'})
    assert r.json['nuevos'] == 1 and r.json['resumen']['existe'] == 1
    plantilla = adm.get('/herramientas/api/plantilla/clientes?formato=xlsx')
    assert plantilla.status_code == 200 and plantilla.data[:2] == b'PK'


def test_exportar_sin_password(adm):
    r = adm.get('/herramientas/api/exportar?tabla=usuarios&formato=csv')
    assert r.status_code == 200
    texto = r.get_data(as_text=True)
    assert 'password' not in texto.lower() and 'scrypt:' not in texto and 'pbkdf2:' not in texto
    assert 'admin' in texto
    assert adm.get('/herramientas/api/exportar?tabla=pg_authid').status_code == 400
    r = adm.get('/herramientas/api/exportar?tabla=productos&formato=xlsx')
    assert r.status_code == 200 and r.data[:2] == b'PK'


def test_integridad_detecta_huerfano(adm):
    did = sql("""INSERT INTO despachos (numero, cliente, ruc, estado, pc_id, pc_numero)
                 VALUES ('DESP-HUERFANO-1', 'CLIENTE X', '20100070970', 'Pendiente despacho', 999999, 'PC-NO-EXISTE') RETURNING id""")[0][0]
    r = adm.get('/herramientas/api/integridad')
    assert r.status_code == 200
    chk = {c['codigo']: c for c in r.json['data']}
    assert chk['desp_sin_pc']['cantidad'] >= 1
    assert any(e['id'] == did for e in chk['desp_sin_pc']['ejemplos'])
    sql("DELETE FROM despachos WHERE id = %s", (did,))


def test_revisar_numeraciones_no_renumera(adm, vend):
    a = factura(vend, serie='F950').json['data']
    sql("UPDATE comprobantes SET numero = 5 WHERE id = %s", (a['id'],))  # deja un hueco 1..4 (simulado)
    factura(vend, serie='F950')                                           # sale el 6
    antes = sql("SELECT id, numero FROM comprobantes ORDER BY id")
    r = adm.get('/herramientas/api/correlativos')
    assert r.status_code == 200
    facturas = next(n for n in r.json['data'] if n['codigo'] == 'facturas')
    serie = next(s for s in facturas['series'] if 'F950' in s['serie'])
    assert serie['desde'] == 5 and serie['hasta'] == 6 and serie['total_huecos'] == 0
    assert sql("SELECT id, numero FROM comprobantes ORDER BY id") == antes  # nada se renumeró
    sql("UPDATE comprobantes SET numero = 9 WHERE id = (SELECT MAX(id) FROM comprobantes WHERE serie = 'F950')")
    r = adm.get('/herramientas/api/correlativos')
    serie = next(s for n in r.json['data'] if n['codigo'] == 'facturas' for s in n['series'] if 'F950' in s['serie'])
    assert serie['huecos'] == [6, 7, 8]
    assert sql("SELECT numero::int FROM comprobantes WHERE serie = 'F950' ORDER BY id") == [(5,), (9,)]


def test_revisar_stock_cache_logs_y_salud(adm):
    # 25/10/2026: "Revisar stock" solo mira; ya no existe la ruta que escribía
    antes = sql("SELECT id, COALESCE(stock, 0) FROM productos ORDER BY id")
    r = adm.get('/herramientas/api/revisar_stock')
    assert r.status_code == 200, r.json
    assert 'diferencias' in r.json and sql("SELECT id, COALESCE(stock, 0) FROM productos ORDER BY id") == antes
    assert adm.get('/herramientas/api/revisar_stock?codigo=NO-EXISTE').json['revisados'] == 0
    assert adm.post('/herramientas/api/recalcular_stock', json={}).status_code in (404, 405)
    r = adm.post('/herramientas/api/cache/limpiar')
    assert r.status_code == 200 and r.json['limpiado']
    assert adm.get('/index').status_code == 200  # el sistema sigue funcionando tras limpiar
    import logging
    logging.getLogger('prueba').error('Error de prueba para el registro')
    r = adm.get('/herramientas/api/logs?nivel=ERROR&n=50')
    assert any('Error de prueba' in f['mensaje'] for f in r.json['data'])
    assert adm.post('/herramientas/api/logs/rotar').status_code == 200
    assert not any('Error de prueba' in f['mensaje'] for f in adm.get('/herramientas/api/logs?nivel=ERROR').json['data'])
    r = adm.get('/herramientas/api/salud')
    assert r.status_code == 200 and r.json['ok'] and r.json['latencia_ms'] >= 0
    texto = r.get_data(as_text=True)
    assert 'postgresql://' not in texto and ':pg@' not in texto and 'password' not in texto.lower()
