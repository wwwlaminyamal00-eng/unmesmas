"""
Erika 28/10/2026: solo ella crea, elimina o reactiva usuarios, y solo ella ve Planilla (sueldos).
Otro administrador tampoco. En pruebas 'admin' hace de Erika (USUARIOS_REPORTES) y 'hellen' es aprobadora.
"""
from tests.test_inventario import _sql


def test_otro_usuario_no_crea_ni_elimina_usuarios(app, aprobador, vendedor):
    uid = _sql("SELECT id FROM usuarios WHERE usuario_sistema = 'vendedor'")[0][0]
    for c in (aprobador, vendedor):
        r = c.post('/api/config/usuarios', json={'usuario_sistema': 'intruso', 'auth_user_id': 'x'})
        assert r.status_code == 403
        assert c.delete(f'/api/config/usuarios/{uid}').status_code == 403
        assert c.post(f'/api/config/usuarios/{uid}/activar').status_code == 403
    assert _sql("SELECT estado FROM usuarios WHERE id = %s", (uid,))[0][0] == 'activo'


def test_cambiar_estado_por_editar_tambien_es_solo_de_erika(app, admin):
    from main import _crea_o_elimina_usuario
    uid = _sql("SELECT id FROM usuarios WHERE usuario_sistema = 'vendedor'")[0][0]
    with app.test_request_context(f'/api/config/usuarios/{uid}', method='PUT', json={'estado': 'inactivo'}):
        assert _crea_o_elimina_usuario(f'/api/config/usuarios/{uid}', 'PUT')
    with app.test_request_context(f'/api/config/usuarios/{uid}', method='PUT', json={'estado': 'activo', 'area': 'X'}):
        assert not _crea_o_elimina_usuario(f'/api/config/usuarios/{uid}', 'PUT')


def test_planilla_solo_erika(app, admin, aprobador):
    assert aprobador.get('/planilla/api/pagos').status_code == 403
    r = aprobador.get('/index')
    assert b'data-modulo="planilla"' not in r.data
    assert admin.get('/planilla/api/pagos').status_code != 403
    assert b'data-modulo="planilla"' in admin.get('/index').data
