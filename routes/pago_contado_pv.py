"""Pago al contado del PV: N° de operación, banco y CCI (Erika, 02/11/2026).

"Cuando damos la opción del contado, se coloca número de operación, banco y el CCI, pero esa data no se está
guardando... se debe actualizar la base de datos para tenerlo como un historial en el caso de auditoría o seguimiento."

- El dato vigente queda en el PV (pedido_compra_pc.pago_num_operacion / pago_banco / pago_cci, con quién y cuándo).
- Cada vez que se registra o se corrige, queda una fila en pv_pago_contado_historial (no se borra).
- Si el PV deja de ser al contado, el dato no se borra: queda en el historial.
Migración 045; en la base de pruebas las columnas y la tabla se crean aquí.
"""
import threading

from flask import session

from database import db_query, db_execute
from utils import normalizar_banco

_listo = False
_lock = threading.Lock()


def asegurar():
    global _listo
    if _listo:
        return
    with _lock:
        if _listo:
            return
        db_execute("""
            ALTER TABLE pedido_compra_pc ADD COLUMN IF NOT EXISTS pago_num_operacion VARCHAR(40);
            ALTER TABLE pedido_compra_pc ADD COLUMN IF NOT EXISTS pago_banco VARCHAR(80);
            ALTER TABLE pedido_compra_pc ADD COLUMN IF NOT EXISTS pago_cci VARCHAR(40);
            ALTER TABLE pedido_compra_pc ADD COLUMN IF NOT EXISTS pago_registrado_por VARCHAR(120);
            ALTER TABLE pedido_compra_pc ADD COLUMN IF NOT EXISTS pago_registrado_en TIMESTAMP;
            CREATE TABLE IF NOT EXISTS pv_pago_contado_historial (
                id SERIAL PRIMARY KEY,
                pedido_id INTEGER NOT NULL,
                pv_numero VARCHAR(40),
                accion VARCHAR(20) NOT NULL,
                num_operacion VARCHAR(40),
                banco VARCHAR(80),
                cci VARCHAR(40),
                usuario_id INTEGER,
                usuario_nombre VARCHAR(120),
                creado_en TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'America/Lima')
            );
            CREATE INDEX IF NOT EXISTS idx_pv_pago_contado_hist_pedido ON pv_pago_contado_historial (pedido_id);
        """)
        _listo = True


def _limpio(v, largo):
    t = ' '.join(str(v or '').split())
    return t[:largo] or None


def guardar(pedido_id, data):
    """Guarda el pago al contado si el PV es al contado y llegó algún dato. Devuelve True si cambió algo."""
    asegurar()
    if not str(data.get('condicion_pago') or '').strip().lower().startswith('contado'):
        return False
    nuevo = (_limpio(data.get('pago_num_operacion'), 40), normalizar_banco(data.get('pago_banco')),
             _limpio(data.get('pago_cci'), 40))
    filas = db_query("SELECT numero, pago_num_operacion, pago_banco, pago_cci FROM pedido_compra_pc WHERE id = %s", (pedido_id,))
    if not filas:
        return False
    actual = (filas[0]['pago_num_operacion'], filas[0]['pago_banco'], filas[0]['pago_cci'])
    if nuevo == actual or (not any(nuevo) and not any(actual)):
        return False
    if not any(nuevo):
        # Nadie borra el pago registrado desde el formulario: queda como estaba (y en el historial)
        return False
    uid = session.get('usuario_id')
    unom = session.get('nombre_completo') or session.get('usuario') or 'Usuario'
    db_execute("""UPDATE pedido_compra_pc SET pago_num_operacion = %s, pago_banco = %s, pago_cci = %s,
                      pago_registrado_por = %s, pago_registrado_en = (NOW() AT TIME ZONE 'America/Lima')
                  WHERE id = %s""", nuevo + (unom, pedido_id))
    db_execute("""INSERT INTO pv_pago_contado_historial (pedido_id, pv_numero, accion, num_operacion, banco, cci,
                      usuario_id, usuario_nombre) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
               (pedido_id, filas[0]['numero'], 'Corregido' if any(actual) else 'Registrado') + nuevo + (uid, unom))
    return True


def datos(pedido_id):
    """Dato vigente e historial del pago al contado para la ficha del PV."""
    asegurar()
    fila = db_query("""SELECT pago_num_operacion, pago_banco, pago_cci, pago_registrado_por,
                              to_char(pago_registrado_en, 'YYYY-MM-DD HH24:MI') AS pago_registrado_en
                       FROM pedido_compra_pc WHERE id = %s""", (pedido_id,))
    out = dict(fila[0]) if fila else {}
    out['pago_historial'] = [dict(h) for h in db_query("""
        SELECT accion, num_operacion, banco, cci, usuario_nombre, to_char(creado_en, 'YYYY-MM-DD HH24:MI') AS creado_en
        FROM pv_pago_contado_historial WHERE pedido_id = %s ORDER BY id DESC""", (pedido_id,))]
    return out
