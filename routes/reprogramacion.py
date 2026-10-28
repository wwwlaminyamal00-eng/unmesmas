"""Fecha programada (cita) y reprogramaciones de una entrega (Erika, 27/10/2026 18:57).

En Entregas van dos columnas: "Fecha programada (cita)" y "Fecha real de entrega".
  - La primera cita queda guardada (fecha_cita_inicial) para medir el cumplimiento.
  - Si la cita se cambia (no hubo transporte, no llegó el producto, el cliente pidió otro día…), se pide el motivo y
    queda el historial con fecha, hora de Lima y usuario. Nada se borra.
  - La fecha real de entrega se pone a mano al confirmar la entrega (ya existía).
Migración 041 (en la base de pruebas la tabla y la columna se crean aquí).
"""
import threading

from flask import Blueprint, jsonify

from database import db_query, db_execute
from utils import login_required

reprogramacion_bp = Blueprint('reprogramacion', __name__)

MOTIVOS = ('No hubo transporte', 'No llegó el producto', 'El cliente pidió otro día', 'El cliente no recibió', 'Otro')
COMENTARIO_MAX = 200

_listo = False
_lock = threading.Lock()


def asegurar():
    global _listo
    if _listo:
        return
    with _lock:
        if _listo:
            return
        hay_tabla = db_query("SELECT 1 FROM information_schema.tables WHERE table_name = 'despacho_reprogramaciones'")
        hay_col = db_query("""SELECT 1 FROM information_schema.columns
                              WHERE table_name = 'despachos' AND column_name = 'fecha_cita_inicial'""")
        if not hay_tabla:
            db_execute("""CREATE TABLE IF NOT EXISTS despacho_reprogramaciones (
                id SERIAL PRIMARY KEY,
                despacho_id INTEGER NOT NULL,
                fecha_anterior DATE,
                fecha_nueva DATE,
                motivo VARCHAR(60) NOT NULL,
                comentario VARCHAR(200),
                usuario VARCHAR(120),
                creado_en TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'America/Lima'))""")
            db_execute("CREATE INDEX IF NOT EXISTS idx_desp_reprog_despacho ON despacho_reprogramaciones (despacho_id)")
        if not hay_col:
            db_execute("ALTER TABLE despachos ADD COLUMN IF NOT EXISTS fecha_cita_inicial DATE")
        _listo = True


def registrar(despacho_id, anterior, nueva, motivo, comentario, usuario):
    db_execute("""INSERT INTO despacho_reprogramaciones (despacho_id, fecha_anterior, fecha_nueva, motivo, comentario, usuario)
                  VALUES (%s, %s, %s, %s, %s, %s)""",
               (despacho_id, anterior, nueva, motivo, (comentario or '')[:COMENTARIO_MAX] or None, (usuario or '')[:120] or None))


def conteos(ids):
    """{despacho_id: {'veces': n, 'ultimo_motivo': '...'}}"""
    asegurar()
    if not ids:
        return {}
    filas = db_query("""SELECT DISTINCT ON (despacho_id) despacho_id, motivo,
                               COUNT(*) OVER (PARTITION BY despacho_id) AS veces
                        FROM despacho_reprogramaciones WHERE despacho_id = ANY(%s)
                        ORDER BY despacho_id, id DESC""", (list(ids),))
    return {f['despacho_id']: {'veces': int(f['veces']), 'ultimo_motivo': f['motivo']} for f in filas}


@reprogramacion_bp.route('/ventas/api/despachos/<int:did>/reprogramaciones', methods=['GET'])
@login_required
def api_historial(did):
    asegurar()
    filas = db_query("""SELECT fecha_anterior, fecha_nueva, motivo, comentario, usuario, creado_en
                        FROM despacho_reprogramaciones WHERE despacho_id = %s ORDER BY id""", (did,))
    ini = db_query("SELECT fecha_cita_inicial FROM despachos WHERE id = %s", (did,))
    f = lambda d: d.strftime('%d/%m/%Y') if d else ''
    return jsonify({'success': True, 'data': {
        'fecha_cita_inicial': f(ini[0]['fecha_cita_inicial']) if ini else '',
        'motivos': list(MOTIVOS),
        'historial': [{'antes': f(x['fecha_anterior']) or 'Sin cita', 'despues': f(x['fecha_nueva']) or 'Sin cita',
                       'motivo': x['motivo'], 'comentario': x['comentario'] or '', 'usuario': x['usuario'] or '',
                       'cuando': x['creado_en'].strftime('%d/%m/%Y %H:%M') if x['creado_en'] else ''} for x in filas]}})
