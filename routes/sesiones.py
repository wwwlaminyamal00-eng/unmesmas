"""
Cierre de sesiones abiertas (pedido de Erika 27/10/2026).

Al cambiar la contraseña de un usuario se guarda usuarios.sesion_valida_desde = NOW(). Toda sesión
iniciada antes de esa hora se cierra en el siguiente clic, aunque la persona tenga el ERP abierto en
otra computadora. Las sesiones sin hora de inicio (las de antes de este cambio) también se cierran.
Migración 040.
"""
import threading
import time

from flask import session

from database import db_query, db_tx

SQL_DDL = "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS sesion_valida_desde TIMESTAMPTZ"
CACHE_SEGUNDOS = 30

_listo = False
_lock = threading.Lock()
_cache = {}


def asegurar_columna():
    global _listo
    if _listo:
        return
    with _lock:
        if _listo:
            return
        with db_tx() as conn:
            cur = conn.cursor()
            cur.execute("""SELECT COUNT(*) FROM information_schema.columns
                           WHERE table_name = 'usuarios' AND column_name = 'sesion_valida_desde'""")
            if cur.fetchone()[0] < 1:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext('sesion_valida_ddl'))")
                cur.execute(SQL_DDL)
        _listo = True


def marcar_inicio():
    """Se llama al iniciar sesión."""
    session['login_ts'] = time.time()


def _valida_desde(usuario_id):
    ahora = time.time()
    guardado = _cache.get(usuario_id)
    if guardado and ahora - guardado[0] < CACHE_SEGUNDOS:
        return guardado[1]
    asegurar_columna()
    filas = db_query("""SELECT EXTRACT(EPOCH FROM sesion_valida_desde) AS desde, estado
                        FROM usuarios WHERE id = %s""", (usuario_id,))
    if not filas or (filas[0].get('estado') or 'activo') != 'activo':
        desde = float('inf')   # usuario borrado o desactivado: fuera
    else:
        desde = float(filas[0]['desde']) if filas[0].get('desde') is not None else 0.0
    _cache[usuario_id] = (ahora, desde)
    return desde


def sesion_vigente():
    """False si la sesión actual debe cerrarse."""
    inicio = session.get('login_ts')
    if not inicio:
        return False
    try:
        return float(inicio) >= _valida_desde(session.get('usuario_id'))
    except Exception:
        return True   # si la base no responde no se expulsa a nadie; el resto de la petición fallará igual


def cerrar_sesiones(usuario_id, cur=None):
    """Cierra todas las sesiones abiertas del usuario (por ejemplo, al cambiarle la contraseña)."""
    asegurar_columna()
    sql = "UPDATE usuarios SET sesion_valida_desde = NOW() WHERE id = %s"
    if cur is not None:
        cur.execute(sql, (usuario_id,))
    else:
        from database import db_execute
        db_execute(sql, (usuario_id,))
    _cache.pop(usuario_id, None)
    try:
        if session.get('usuario_id') == usuario_id:
            session['login_ts'] = time.time() + 2   # quien cambia su propia contraseña sigue dentro
    except RuntimeError:
        pass
