"""
Pruebas de la pantalla "Usuarios y permisos" (bug 13) y de las cuentas de Supabase Auth sin usuario del ERP.
  - Marcar/desmarcar UN submódulo no borra los demás permisos (antes se borraba todo).
  - Al recargar se ve lo guardado (la base de datos es la única fuente).
  - El modal guarda las 6 banderas (ver, crear, editar, aprobar, anular, eliminar) de un submódulo.
  - Con la empresa "TODAS" en la cabecera no se rompe: se leen los permisos sumando sus empresas
    y para guardar se pide elegir KCF o AGD.
  - Regla: permiso individual > permiso del rol > nada; GERENCIA_TOTAL ve todo.
  - auth-sin-vincular: lista las cuentas de auth.users sin usuario, crea el usuario enlazado e inactivo,
    y solo puede entrar después de activarlo, con la contraseña mostrada una vez.
"""
import uuid
import pytest

from conftest import _login, ESQUEMA
from tests.test_flujos import sql

SUBMODULOS = [('CONFIG', 'Configuración', 1, [('EMPRESAS', 'Empresas'), ('USUARIOS_PERMISOS', 'Usuarios y permisos')]),
              ('MAESTROS', 'Maestros', 2, [('CLIENTES', 'Clientes'), ('PROVEEDORES', 'Proveedores')]),
              ('VENTAS', 'Ventas', 3, [('COTIZACIONES', 'Cotizaciones'), ('COMPROBANTES_CLIENTE', 'Comprobantes cliente')])]
HAY_AUTH = ESQUEMA != 'reconstruido'


def _auth_user(email):
    """Crea la cuenta en auth.users (solo existe en el esquema real) y devuelve su id."""
    uid = str(uuid.uuid4())
    if HAY_AUTH:
        sql("INSERT INTO auth.users (id, email) VALUES (%s, %s)", (uid, email))
    return uid


@pytest.fixture(scope='module')
def base(app):
    sql("""
        INSERT INTO erp_empresas (codigo, nombre_corto, nombre_comercial, razon_social, ruc, direccion_fiscal, estado,
                                  color_primario, color_secundario, color_pastel)
        SELECT 'KCF', 'KCF', 'KCF', 'KCF S.A.C.', '20111111111', 'Av. Perú 123, SMP', 'activo', '#D6243A', '#1D1A1F', '#FDE8EB'
        WHERE NOT EXISTS (SELECT 1 FROM erp_empresas WHERE codigo = 'KCF');
        INSERT INTO erp_empresas (codigo, nombre_corto, nombre_comercial, razon_social, ruc, direccion_fiscal, estado,
                                  color_primario, color_secundario, color_pastel)
        SELECT 'AGD', 'AGD', 'AGD', 'AGD S.A.C.', '20222222222', 'Jr. Breña 456', 'activo', '#1D4ED8', '#1D1A1F', '#DBEAFE'
        WHERE NOT EXISTS (SELECT 1 FROM erp_empresas WHERE codigo = 'AGD');
        INSERT INTO erp_roles (codigo, nombre, es_admin, estado)
        SELECT 'GERENCIA_TOTAL', 'Gerencia total', true, 'activo' WHERE NOT EXISTS (SELECT 1 FROM erp_roles WHERE codigo = 'GERENCIA_TOTAL');
        INSERT INTO erp_roles (codigo, nombre, es_admin, estado)
        SELECT 'OPERATIVO_COMERCIAL_LOGISTICA', 'Operativo', false, 'activo'
        WHERE NOT EXISTS (SELECT 1 FROM erp_roles WHERE codigo = 'OPERATIVO_COMERCIAL_LOGISTICA');
    """)
    for mcod, mnom, orden, subs in SUBMODULOS:
        sql("""INSERT INTO erp_modulos (orden, codigo, nombre, estado) SELECT %s, %s, %s, 'activo'
               WHERE NOT EXISTS (SELECT 1 FROM erp_modulos WHERE codigo = %s)""", (orden, mcod, mnom, mcod))
        for i, (scod, snom) in enumerate(subs, 1):
            sql("""INSERT INTO erp_submodulos (modulo_id, orden, codigo, nombre, estado)
                   SELECT m.id, %s, %s, %s, 'activo' FROM erp_modulos m
                   WHERE m.codigo = %s AND NOT EXISTS (SELECT 1 FROM erp_submodulos WHERE codigo = %s)""",
                (i, scod, snom, mcod, scod))
    from routes import multiempresa
    multiempresa.empresas(refrescar=True)
    emp = {c: str(i) for c, i in sql("SELECT codigo, id FROM erp_empresas WHERE codigo IN ('KCF', 'AGD')")}
    roles = {c: str(i) for c, i in sql("SELECT codigo, id FROM erp_roles")}
    subs = {c: str(i) for c, i in sql("SELECT codigo, id FROM erp_submodulos")}
    return {'emp': emp, 'roles': roles, 'subs': subs}


def _usuario(base, nombre, rol_erp='OPERATIVO_COMERCIAL_LOGISTICA', empresas=('KCF', 'AGD')):
    auth = _auth_user(f'{nombre}@test.pe')
    uid = sql("""INSERT INTO usuarios (usuario_sistema, usuario, nombres_apellidos, nombre_completo, correo,
                                       password, rol, estado, auth_user_id)
                 VALUES (%s, %s, %s, %s, %s, 'x', 'vendedor', 'activo', %s) RETURNING id""",
              (nombre, nombre, nombre, nombre, f'{nombre}@test.pe', auth))[0][0]
    for i, cod in enumerate(empresas):
        sql("""INSERT INTO erp_usuario_empresas (auth_user_id, empresa_id, rol_id, es_empresa_principal, estado)
               VALUES (%s, %s, %s, %s, 'activo')""", (auth, base['emp'][cod], base['roles'][rol_erp], i == 0))
    return uid, auth


def _guardar(cliente, uid, empresa_id, permisos, **extra):
    return cliente.post(f'/api/config/usuarios/{uid}/permisos', json=dict(empresa_id=empresa_id, permisos=permisos, **extra))


def _leer(cliente, uid, **params):
    r = cliente.get(f'/api/config/usuarios/{uid}/permisos', query_string=params)
    assert r.status_code == 200, r.json
    return r.json['data']


def test_marcar_un_submodulo_no_borra_los_demas(admin, base):
    uid, _ = _usuario(base, 'perm_uno')
    kcf = base['emp']['KCF']
    r = _guardar(admin, uid, kcf, [{'submodulo_codigo': 'CLIENTES', 'puede_ver': True, 'puede_crear': True},
                                   {'submodulo_codigo': 'COTIZACIONES', 'puede_ver': True}])
    assert r.status_code == 200 and r.json['success'], r.json
    # Como hace el check de la tabla: se envía SOLO un submódulo
    r = _guardar(admin, uid, kcf, [{'submodulo_codigo': 'EMPRESAS', 'puede_ver': True}])
    assert r.status_code == 200, r.json
    ef = _leer(admin, uid, empresa_id=kcf)['efectivos']
    assert ef['CLIENTES']['puede_ver'] and ef['CLIENTES']['puede_crear']
    assert ef['COTIZACIONES']['puede_ver'] and ef['EMPRESAS']['puede_ver']
    # Desmarcar uno solo
    _guardar(admin, uid, kcf, [{'submodulo_codigo': 'COTIZACIONES', 'puede_ver': False}])
    ef = _leer(admin, uid, empresa_id=kcf)['efectivos']
    assert ef['COTIZACIONES']['puede_ver'] is False and ef['CLIENTES']['puede_ver'] and ef['EMPRESAS']['puede_ver']
    # Solo cambiar puede_ver no toca puede_crear
    _guardar(admin, uid, kcf, [{'submodulo_codigo': 'CLIENTES', 'puede_ver': True}])
    assert _leer(admin, uid, empresa_id=kcf)['efectivos']['CLIENTES']['puede_crear'] is True
    # AGD no se ve afectado
    assert _leer(admin, uid, empresa_id=base['emp']['AGD'])['efectivos'] == {}
    # Ids numéricos antiguos (pantalla vieja) y UUID siguen funcionando
    assert _guardar(admin, uid, kcf, [{'submodulo_id': 7, 'puede_ver': True}]).status_code == 200
    assert _guardar(admin, uid, kcf, [{'submodulo_id': base['subs']['USUARIOS_PERMISOS'], 'puede_ver': True}]).status_code == 200
    ef = _leer(admin, uid, empresa_id=kcf)['efectivos']
    assert ef['PROVEEDORES']['puede_ver'] and ef['USUARIOS_PERMISOS']['puede_ver'] and ef['CLIENTES']['puede_ver']
    filas = sql("SELECT COUNT(*) FROM erp_usuario_permisos WHERE auth_user_id::text = (SELECT auth_user_id::text FROM usuarios WHERE id = %s)", (uid,))
    assert filas[0][0] == 5  # sin duplicados


def test_submodulo_inexistente_no_guarda_nada_y_avisa(admin, base):
    uid, _ = _usuario(base, 'perm_error')
    r = _guardar(admin, uid, base['emp']['KCF'], [{'submodulo_codigo': 'CLIENTES', 'puede_ver': True},
                                                  {'submodulo_codigo': 'NO_EXISTE', 'puede_ver': True}])
    assert r.status_code == 400 and not r.json['success'] and 'NO_EXISTE' in r.json['error']
    assert _leer(admin, uid, empresa_id=base['emp']['KCF'])['permisos'] == []


def test_reemplazar_todo_solo_con_bandera_explicita(admin, base):
    uid, _ = _usuario(base, 'perm_reemp')
    kcf = base['emp']['KCF']
    _guardar(admin, uid, kcf, [{'submodulo_codigo': 'CLIENTES', 'puede_ver': True},
                               {'submodulo_codigo': 'EMPRESAS', 'puede_ver': True}])
    _guardar(admin, uid, kcf, [{'submodulo_codigo': 'COTIZACIONES', 'puede_ver': True}], reemplazar_todo=True)
    assert set(_leer(admin, uid, empresa_id=kcf)['efectivos']) == {'COTIZACIONES'}


def test_modal_guarda_las_seis_banderas_y_se_recargan(admin, base):
    uid, _ = _usuario(base, 'perm_modal')
    kcf = base['emp']['KCF']
    seis = {'puede_ver': True, 'puede_crear': False, 'puede_editar': True,
            'puede_aprobar': True, 'puede_anular': False, 'puede_eliminar': True}
    r = _guardar(admin, uid, kcf, [dict(submodulo_codigo='PROVEEDORES', **seis),
                                   dict(submodulo_codigo='CLIENTES', **{k: False for k in seis})])
    assert r.status_code == 200, r.json
    datos = _leer(admin, uid, empresa_codigo='KCF')  # también por código de empresa
    fila = next(p for p in datos['permisos'] if p['submodulo_codigo'] == 'PROVEEDORES')
    assert {k: fila[k] for k in seis} == seis
    assert {k: datos['efectivos']['PROVEEDORES'][k] for k in seis} == seis
    assert datos['efectivos']['PROVEEDORES']['origen'] == 'usuario'
    # Cambiar de nuevo y recargar
    seis2 = {k: not v for k, v in seis.items()}
    _guardar(admin, uid, kcf, [dict(submodulo_codigo='PROVEEDORES', **seis2)])
    fila = next(p for p in _leer(admin, uid, empresa_id=kcf)['permisos'] if p['submodulo_codigo'] == 'PROVEEDORES')
    assert {k: fila[k] for k in seis} == seis2


def test_con_todas_en_la_cabecera_no_se_rompe(app, base):
    uid, _ = _usuario(base, 'perm_todas')
    c = _login(app, 'admin', 'Admin#2026!')
    assert c.post('/api/empresa_activa', json={'codigo': 'TODAS'}).status_code == 200
    _guardar(c, uid, base['emp']['KCF'], [{'submodulo_codigo': 'CLIENTES', 'puede_ver': True}])
    _guardar(c, uid, base['emp']['AGD'], [{'submodulo_codigo': 'COTIZACIONES', 'puede_ver': True}])
    datos = _leer(c, uid, empresa_codigo='TODAS')
    assert datos['efectivos']['CLIENTES']['puede_ver'] and datos['efectivos']['COTIZACIONES']['puede_ver']
    assert len(datos['empresa_ids']) == 2
    # Para guardar hay que elegir una empresa
    r = c.post(f'/api/config/usuarios/{uid}/permisos', json={'empresa_codigo': 'TODAS',
                                                             'permisos': [{'submodulo_codigo': 'CLIENTES', 'puede_ver': True}]})
    assert r.status_code == 400 and 'KCF o AGD' in r.json['error']
    assert c.get('/usuarios').status_code == 200


def test_regla_individual_rol_y_gerencia(admin, base):
    uid, _ = _usuario(base, 'perm_gerente', rol_erp='GERENCIA_TOTAL', empresas=('KCF',))
    datos = _leer(admin, uid, empresa_codigo='KCF')
    assert datos['es_gerencia_total'] and all(v['puede_ver'] and v['origen'] == 'gerencia' for v in datos['efectivos'].values())
    assert set(datos['efectivos']) >= {'EMPRESAS', 'CLIENTES', 'COTIZACIONES'}
    if ESQUEMA == 'reconstruido':
        return  # el esquema reconstruido no tiene erp_rol_permisos
    uid2, _ = _usuario(base, 'perm_rol', empresas=('KCF',))
    sql("""INSERT INTO erp_rol_permisos (rol_id, submodulo_id, puede_ver, puede_crear)
           VALUES (%s, %s, true, true), (%s, %s, true, false)
           ON CONFLICT (rol_id, submodulo_id) DO UPDATE SET puede_ver = EXCLUDED.puede_ver""",
        (base['roles']['OPERATIVO_COMERCIAL_LOGISTICA'], base['subs']['COMPROBANTES_CLIENTE'],
         base['roles']['OPERATIVO_COMERCIAL_LOGISTICA'], base['subs']['PROVEEDORES']))
    ef = _leer(admin, uid2, empresa_codigo='KCF')['efectivos']
    assert ef['COMPROBANTES_CLIENTE']['puede_ver'] and ef['COMPROBANTES_CLIENTE']['origen'] == 'rol'
    # El permiso individual gana aunque sea "no"
    _guardar(admin, uid2, base['emp']['KCF'], [{'submodulo_codigo': 'PROVEEDORES', 'puede_ver': False}])
    ef = _leer(admin, uid2, empresa_codigo='KCF')['efectivos']
    assert ef['PROVEEDORES']['puede_ver'] is False and ef['PROVEEDORES']['origen'] == 'usuario'
    assert ef['COMPROBANTES_CLIENTE']['origen'] == 'rol'


def test_usuario_lee_sus_permisos_pero_no_los_de_otros(app, admin, base):
    uid, _ = _usuario(base, 'perm_propio')
    vend = _login(app, 'vendedor', 'Vende#2026!')
    vid = sql("SELECT id FROM usuarios WHERE usuario_sistema = 'vendedor'")[0][0]
    assert vend.get(f'/api/config/usuarios/{vid}/permisos?empresa_codigo=KCF').status_code == 200
    assert vend.get(f'/api/config/usuarios/{uid}/permisos?empresa_codigo=KCF').status_code == 403
    assert _guardar(vend, uid, base['emp']['KCF'], [{'submodulo_codigo': 'CLIENTES', 'puede_ver': True}]).status_code == 403
    assert vend.get('/api/config/auth-sin-vincular').status_code == 403
    assert vend.get('/api/config/usuarios-inactivos').status_code == 403


@pytest.mark.skipif(not HAY_AUTH, reason='El esquema reconstruido no tiene auth.users')
def test_cuenta_auth_sin_usuario_se_crea_inactiva_y_entra_al_activar(app, admin, base):
    auth_id = _auth_user('nueva.persona@test.pe')
    r = admin.get('/api/config/auth-sin-vincular')
    assert r.status_code == 200, r.json
    fila = next(f for f in r.json['data'] if f['id'] == auth_id)
    assert fila['email'] == 'nueva.persona@test.pe' and 'last_sign_in_at' in fila and 'created_at' in fila
    # Validaciones
    url = f'/api/config/auth-sin-vincular/{auth_id}/crear'
    assert admin.post(url, json={'usuario_sistema': 'npersona'}).status_code == 400              # sin contraseña
    assert admin.post(url, json={'usuario_sistema': 'npersona', 'password': 'corta'}).status_code == 400
    assert admin.post(url, json={'usuario_sistema': 'admin', 'generar_password': True}).status_code == 400  # ya existe
    r = admin.post(url, json={'usuario_sistema': 'npersona', 'nombres_apellidos': 'Nueva Persona',
                              'generar_password': True, 'empresas': ['KCF'], 'rol_erp': 'OPERATIVO_COMERCIAL_LOGISTICA'})
    assert r.status_code == 200, r.json
    clave = r.json['data']['password_generada']
    assert len(clave) >= 12 and any(c.isdigit() for c in clave) and any(c.isalpha() for c in clave) \
        and any(not c.isalnum() for c in clave)
    nuevo_id = r.json['data']['id']
    fila = sql("""SELECT auth_user_id::text, correo, estado, rol, password FROM usuarios WHERE id = %s""", (nuevo_id,))[0]
    assert fila[0] == auth_id and fila[1] == 'nueva.persona@test.pe' and fila[2] == 'inactivo' and fila[3] == 'vendedor'
    assert fila[4] != clave and fila[4].startswith(('scrypt:', 'pbkdf2:'))  # guardada con hash
    assert sql("SELECT COUNT(*) FROM erp_usuario_empresas WHERE auth_user_id::text = %s", (auth_id,))[0][0] == 1
    # Ya no aparece como "sin vincular" y no se puede crear dos veces
    assert auth_id not in {f['id'] for f in admin.get('/api/config/auth-sin-vincular').json['data']}
    assert admin.post(url, json={'usuario_sistema': 'otro', 'generar_password': True}).status_code == 400
    # Aparece en la lista de inactivos
    assert nuevo_id in {f['id'] for f in admin.get('/api/config/usuarios-inactivos').json['data']}
    # No puede entrar hasta que lo activen
    c = app.test_client()
    r = c.post('/login', data={'usuario': 'npersona', 'password': clave, 'empresa': 'KCF'})
    assert r.status_code != 302
    r = admin.post(f'/api/config/usuarios/{nuevo_id}/activar')
    assert r.status_code == 200, r.json
    assert sql("SELECT estado FROM usuarios WHERE id = %s", (nuevo_id,))[0][0] == 'activo'
    c2 = _login(app, 'npersona', clave)
    assert c2.get('/api/config/auth-sin-vincular').status_code == 403   # es vendedor, no administrador


@pytest.mark.skipif(not HAY_AUTH, reason='El esquema reconstruido no tiene auth.users')
def test_cuenta_auth_con_contrasena_escrita_por_el_admin(app, admin, base):
    auth_id = _auth_user('escrita@test.pe')
    r = admin.post(f'/api/config/auth-sin-vincular/{auth_id}/crear',
                   json={'usuario_sistema': 'escrita', 'password': 'Escrita#2026'})
    assert r.status_code == 200, r.json
    assert 'password_generada' not in r.json['data']
    admin.post(f"/api/config/usuarios/{r.json['data']['id']}/activar")
    _login(app, 'escrita@test.pe', 'Escrita#2026')  # también entra con su correo


def test_auth_sin_vincular_sin_tabla_auth_no_falla(admin, base):
    r = admin.get('/api/config/auth-sin-vincular')
    assert r.status_code == 200 and r.json['success']
    assert admin.post('/api/config/auth-sin-vincular/no-es-uuid/crear', json={}).status_code == 400
