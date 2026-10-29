"""
Erika 29/10/2026 (pedido de Abdiel): crear un usuario desde la pantalla, entrar con la contraseña generada,
y desactivarlo sin borrar nada. Solo Erika ('admin' hace de Erika en las pruebas). Datos inventados, base local.
"""
from tests.test_inventario import _sql


def _entrar(app, usuario, password):
    return app.test_client().post('/login', data={'usuario': usuario, 'password': password, 'empresa': 'KCF'})


def test_crear_entrar_y_desactivar(app, admin):
    _sql("INSERT INTO erp_empresas (codigo, razon_social) SELECT 'KCF', 'KCF PRUEBA' WHERE NOT EXISTS (SELECT 1 FROM erp_empresas WHERE codigo = 'KCF')", fetch=False)
    _sql("INSERT INTO erp_roles (codigo, nombre) SELECT 'OPERATIVO_COMERCIAL_LOGISTICA', 'Operativo' WHERE NOT EXISTS (SELECT 1 FROM erp_roles WHERE codigo = 'OPERATIVO_COMERCIAL_LOGISTICA')", fetch=False)
    r = admin.post('/api/config/usuarios/nuevo', json={'usuario_sistema': 'zzprueba01', 'nombres_apellidos': 'Prueba Nueva',
                                                       'empresas': ['KCF'], 'generar_password': True})
    assert r.status_code == 200, r.get_json()
    datos = r.get_json()['data']
    clave = datos['password_generada']
    fila = _sql("SELECT estado, auth_user_id, password FROM usuarios WHERE id = %s", (datos['id'],))[0]
    assert fila[0] == 'activo' and fila[1] and fila[2].startswith(('scrypt:', 'pbkdf2:'))   # cifrada
    assert _sql("SELECT COUNT(*) FROM erp_usuario_empresas WHERE auth_user_id = %s", (fila[1],))[0][0] == 1
    # Empieza sin ningún módulo, aunque su rol tenga permisos
    assert not _sql("SELECT 1 FROM erp_usuario_permisos WHERE auth_user_id = %s AND puede_ver", (fila[1],))
    assert _sql("SELECT COUNT(*) FROM erp_usuario_permisos WHERE auth_user_id = %s", (fila[1],))[0][0] > 0
    # El mismo usuario no se puede crear dos veces
    assert admin.post('/api/config/usuarios/nuevo', json={'usuario_sistema': 'ZZPRUEBA01', 'nombres_apellidos': 'Otra',
                                                          'empresas': ['KCF'], 'generar_password': True}).status_code == 400
    # Entra con la contraseña generada
    r = _entrar(app, 'zzprueba01', clave)
    assert r.status_code == 302 and '/index' in r.headers['Location']
    c = app.test_client()
    c.post('/login', data={'usuario': 'zzprueba01', 'password': clave, 'empresa': 'KCF'})
    assert c.get('/index').status_code == 200
    # Desactivar: sale en el siguiente clic, ya no entra, y no se borra nada
    from routes import sesiones
    r = admin.post(f"/api/config/usuarios/{datos['id']}/desactivar", json={'motivo': 'prueba'})
    assert r.get_json()['success']
    sesiones._cache.clear()
    assert c.get('/index').status_code == 302
    assert '/index' not in _entrar(app, 'zzprueba01', clave).headers.get('Location', '')
    assert _sql("SELECT estado FROM usuarios WHERE id = %s", (datos['id'],))[0][0] == 'inactivo'
    assert _sql("SELECT COUNT(*) FROM erp_auditoria WHERE accion IN ('crear_usuario', 'desactivar_usuario') AND registro_id = %s",
                (str(datos['id']),))[0][0] == 2


def test_solo_erika_crea_y_desactiva(app, aprobador):
    assert aprobador.post('/api/config/usuarios/nuevo', json={'usuario_sistema': 'zzintruso', 'nombres_apellidos': 'X',
                                                              'empresas': ['KCF'], 'generar_password': True}).status_code == 403
    uid = _sql("SELECT id FROM usuarios WHERE usuario_sistema = 'vendedor'")[0][0]
    assert aprobador.post(f'/api/config/usuarios/{uid}/desactivar').status_code == 403
    assert not _sql("SELECT 1 FROM usuarios WHERE usuario_sistema = 'zzintruso'")


def test_no_se_desactiva_a_si_misma(app, admin):
    uid = _sql("SELECT id FROM usuarios WHERE usuario_sistema = 'admin'")[0][0]
    assert admin.post(f'/api/config/usuarios/{uid}/desactivar').status_code == 400
