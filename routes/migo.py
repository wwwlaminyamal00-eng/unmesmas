"""N° MIGO / conformidad (Erika 25/10/2026): algunos clientes (p. ej. Komatsu-Mitsui) no pagan la factura
sin el N° MIGO de su conformidad. El cliente lleva el check "Pide N° MIGO"; la factura guarda el número y
Cuentas por cobrar avisa "Falta MIGO". Migración 031 (en la base de pruebas las columnas se crean aquí)."""
import threading

from database import db_query, db_execute, db_tx

SQL_DDL_MIGO = """
    ALTER TABLE clientes ADD COLUMN IF NOT EXISTS pide_migo BOOLEAN NOT NULL DEFAULT false;
    ALTER TABLE comprobantes ADD COLUMN IF NOT EXISTS numero_migo VARCHAR(40)
"""

_listo = False
_lock = threading.Lock()


def asegurar_migo():
    """Crea las dos columnas si faltan. No borra nada."""
    global _listo
    if _listo:
        return
    with _lock:
        if _listo:
            return
        with db_tx() as conn:
            cur = conn.cursor()
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('migo_ddl'))")
            for s in (x.strip() for x in SQL_DDL_MIGO.split(';')):
                if s:
                    cur.execute("SELECT to_regclass(%s)", (s.split()[2],))
                    if cur.fetchone()[0] is not None:
                        cur.execute(s)
        _listo = True


def limpiar_migo(valor):
    """Texto del N° MIGO: sin espacios de más, en mayúscula y hasta 40 caracteres. Vacío = None."""
    return ' '.join(str(valor or '').split()).upper()[:40] or None


def cliente_pide_migo(ruc):
    ruc = str(ruc or '').strip()
    if not ruc:
        return False
    asegurar_migo()
    fila = db_query("SELECT bool_or(COALESCE(pide_migo, false)) AS si FROM clientes WHERE numero_documento = %s", (ruc,))
    return bool(fila and fila[0]['si'])


def guardar_pide_migo(cliente_id, valor):
    asegurar_migo()
    db_execute("UPDATE clientes SET pide_migo = %s WHERE id = %s", (bool(valor), cliente_id))


def leer_pide_migo(cliente_id):
    asegurar_migo()
    fila = db_query("SELECT COALESCE(pide_migo, false) AS si FROM clientes WHERE id = %s", (cliente_id,))
    return bool(fila and fila[0]['si'])


def guardar_numero_migo(comprobante_id, valor):
    asegurar_migo()
    db_execute("UPDATE comprobantes SET numero_migo = %s WHERE id = %s", (limpiar_migo(valor), comprobante_id))
