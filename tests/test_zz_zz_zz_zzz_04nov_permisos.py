"""
04/11/2026: "Hellen y los otros usuarios no tienen acceso a recibir mercadería; dice Acceso total pero no tiene acceso".
Compras leía solo el rol (almacén, compras...), no la matriz de Usuarios y permisos. Ahora "Acceso total" (crear) en
Recibir mercadería / Órdenes de compra / Facturas de proveedores también habilita ese paso. Aprobar OC sigue igual.
Además arriba a la derecha sale el nombre real de quien entró (no "Usuario").
"""
import re

from tests.test_flujos import sql
from tests.test_permisos_usuarios import base, _usuario, _guardar   # noqa: F401


def _datos(cli):
    r = cli.get('/compras')
    html = r.get_data(as_text=True)
    assert r.status_code == 200, (r.status_code, r.headers.get('Location'))
    return {k: v == 'true' for k, v in re.findall(r'data-(comprar|recibir|facturar|aprobar)="(true|false)"', html)}, html


def test_acceso_total_en_la_matriz_habilita_recibir(app, admin, base):
    from werkzeug.security import generate_password_hash
    from conftest import _login
    from routes.acceso import limpiar_cache
    sql("""INSERT INTO erp_modulos (orden, codigo, nombre, estado) SELECT 4, 'COMPRAS', 'Compras', 'activo'
           WHERE NOT EXISTS (SELECT 1 FROM erp_modulos WHERE codigo = 'COMPRAS')""")
    for i, (cod, nom) in enumerate((('ORDEN_COMPRA', 'Órdenes de compra'), ('RECEPCION_MERCADERIA', 'Recibir mercadería'),
                                    ('COMPROBANTES_PROVEEDOR', 'Facturas de proveedores')), 1):
        sql("""INSERT INTO erp_submodulos (modulo_id, orden, codigo, nombre, estado)
               SELECT m.id, %s, %s, %s, 'activo' FROM erp_modulos m WHERE m.codigo = 'COMPRAS'
               AND NOT EXISTS (SELECT 1 FROM erp_submodulos WHERE codigo = %s)""", (i, cod, nom, cod))
    uid, _ = _usuario(base, 'recibe_matriz', empresas=('KCF',))
    sql("UPDATE usuarios SET password = %s, nombres_apellidos = 'Hellen Prueba Blas' WHERE id = %s",
        (generate_password_hash('Recibe#2026!'), uid))
    r = _guardar(admin, uid, base['emp']['KCF'], [{'submodulo_codigo': 'ORDEN_COMPRA', 'puede_ver': True}])
    assert r.status_code == 200, r.json
    limpiar_cache()
    h = _login(app, 'recibe_matriz', 'Recibe#2026!')
    puede, html = _datos(h)
    assert not puede['recibir'] and not puede['comprar']
    assert '"Hellen Prueba Blas"' in html                      # nombre real arriba a la derecha
    full = {'puede_ver': True, 'puede_crear': True, 'puede_editar': True, 'puede_aprobar': False}
    _guardar(admin, uid, base['emp']['KCF'], [dict(full, submodulo_codigo=c) for c in
                                              ('RECEPCION_MERCADERIA', 'ORDEN_COMPRA', 'COMPROBANTES_PROVEEDOR')])
    limpiar_cache()
    from routes import acceso
    acceso._cache_flags.clear()
    puede, _ = _datos(h)
    # Erika 04/11/2026 (tarde): Recibir mercadería pasó a ser solo de Erika, Hellen y Estrella (por usuario)
    assert not puede['recibir'] and puede['comprar'] and puede['facturar']
    assert not puede['aprobar']                                  # aprobar OC no se regala con "crear"


def test_oc_credito_y_pagos_solo_erika_y_hellen(app):
    import utils
    from flask import session
    with app.test_request_context():
        for usuario, esperado in (('eri01kcf', True), ('HEL02KCF', True), ('mil01kcf', False), ('admin_otro', False), ('', False)):
            session['usuario'] = usuario
            assert utils.paga_proveedores() is esperado
    assert 'hel02kcf' in utils._lista_env('X', 'eri01kcf,hel02kcf')
