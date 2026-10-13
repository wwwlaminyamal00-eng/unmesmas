"""
Configuración de pruebas.
Las pruebas usan una base PostgreSQL LOCAL y VACÍA (nunca la de producción):
    export TEST_DATABASE_URL="postgresql://postgres@localhost:5432/erp_pruebas"
    pytest -q tests
La base se recrea desde tests/schema_pruebas.sql en cada ejecución.
"""
import os
import sys
import pytest
import psycopg2

TEST_DB = os.environ.get('TEST_DATABASE_URL')
if not TEST_DB:
    pytest.exit("Define TEST_DATABASE_URL con una base PostgreSQL local de pruebas (no la de producción).", 2)
if 'supabase' in TEST_DB:
    pytest.exit("TEST_DATABASE_URL apunta a Supabase: las pruebas solo deben ejecutarse en una base local.", 2)

os.environ['DATABASE_URL'] = TEST_DB
os.environ.setdefault('SECRET_KEY', 'clave-solo-para-pruebas')
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)


def _recrear_esquema():
    conn = psycopg2.connect(TEST_DB)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    with open(os.path.join(RAIZ, 'tests', 'schema_pruebas.sql'), encoding='utf-8') as f:
        cur.execute(f.read())
    from werkzeug.security import generate_password_hash
    cur.execute("""
        INSERT INTO usuarios (usuario_sistema, nombres_apellidos, correo, password, rol, estado) VALUES
        ('admin', 'Admin Pruebas', 'admin@test.pe', %s, 'administrador', 'activo'),
        ('vendedor', 'Vendedor Pruebas', 'vend@test.pe', %s, 'vendedor', 'activo'),
        ('hellen', 'Hellen Validadora', 'hellen@test.pe', %s, 'hellen', 'activo'),
        ('legado', 'Usuario Antiguo', 'legado@test.pe', 'clave-plana-123', 'vendedor', 'activo'),
        ('inactivo', 'Usuario Inactivo', 'inac@test.pe', %s, 'vendedor', 'inactivo')
    """, (generate_password_hash('Admin#2026!'), generate_password_hash('Vende#2026!'),
          generate_password_hash('Valida#2026!'), generate_password_hash('Inac#2026!')))
    cur.execute("""
        INSERT INTO clientes (tipo_documento, numero_documento, razon_social, direccion_fiscal, codigo_cliente, activo)
        VALUES ('RUC', '20100070970', 'CLIENTE INDUSTRIAL S.A.C.', 'Av. Principal 123, Lima', 'CLI-0001', true);
        INSERT INTO proveedores (razon_social, ruc, direccion, codigo_proveedor, activo)
        VALUES ('PROVEEDOR ACEROS S.A.C.', '20600011111', 'Av. Industrial 1', 'PROV-0001', true);
        INSERT INTO productos (codigo, descripcion, marca, unidad, costo_unitario, precio_unitario, stock, activo)
        VALUES ('PRD-0001', 'GUANTE DE NITRILO', 'ANSELL', 'PAR', 10, 15, 0, true),
               ('PRD-0002', 'CASCO DE SEGURIDAD', '3M', 'UND', 20, 32, 0, true);
    """)
    cur.close()
    conn.close()


@pytest.fixture(scope='session')
def app():
    _recrear_esquema()
    import main
    main.app.config['TESTING'] = True
    return main.app


def _login(app, usuario, password):
    c = app.test_client()
    r = c.post('/login', data={'usuario': usuario, 'password': password, 'empresa': 'KCF'})
    assert r.status_code == 302 and '/index' in r.headers['Location'], f'login falló para {usuario}'
    return c


@pytest.fixture(scope='session')
def admin(app):
    return _login(app, 'admin', 'Admin#2026!')


@pytest.fixture(scope='session')
def vendedor(app):
    return _login(app, 'vendedor', 'Vende#2026!')


@pytest.fixture(scope='session')
def aprobador(app):
    return _login(app, 'hellen', 'Valida#2026!')


@pytest.fixture()
def anonimo(app):
    return app.test_client()
