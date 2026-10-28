"""
Cierre de sesiones al cambiar la contraseña (Erika 27/10/2026): quien tenía el ERP abierto con la
contraseña vieja sale en el siguiente clic. Usa el usuario 'legado' para no tocar las sesiones de las demás pruebas.
"""
from tests.test_inventario import _sql


def _entrar(app, usuario, password):
    c = app.test_client()
    r = c.post('/login', data={'usuario': usuario, 'password': password, 'empresa': 'KCF'})
    assert r.status_code == 302 and '/index' in r.headers['Location']
    return c


def test_sesion_sin_hora_de_inicio_se_cierra(app):
    c = _entrar(app, 'legado', 'clave-plana-123')
    with c.session_transaction() as s:
        s.pop('login_ts')          # sesión iniciada antes de este cambio
    r = c.get('/api/config/session')
    assert r.status_code == 401 and r.get_json()['codigo'] == 'sesion_cerrada'


def test_cambiar_contrasena_cierra_sesiones_abiertas(app, admin):
    from routes import sesiones
    c = _entrar(app, 'legado', 'clave-plana-123')
    assert c.get('/index').status_code == 200
    uid = _sql("SELECT id FROM usuarios WHERE usuario_sistema = 'legado'")[0][0]
    r = admin.post(f'/api/config/usuarios/{uid}/password', json={'password': 'Nueva2026clave'})
    assert r.get_json()['success']
    sesiones._cache.clear()        # en producción otro proceso lo nota en 30 segundos como máximo
    r = c.get('/index')
    assert r.status_code == 302 and '/login' in r.headers['Location']
    # La contraseña vieja ya no entra y la nueva sí
    viejo = app.test_client().post('/login', data={'usuario': 'legado', 'password': 'clave-plana-123'})
    assert '/index' not in viejo.headers.get('Location', '')
    nuevo = _entrar(app, 'legado', 'Nueva2026clave')
    assert nuevo.get('/index').status_code == 200
    # El administrador sigue dentro
    assert admin.get('/index').status_code == 200
