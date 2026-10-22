# routes/diagnostico.py - Errores que ya no pasan en silencio (pedido urgente de Erika, 22/10/2026)
#
#   1. explicar_error_bd(e): traduce un error de PostgreSQL/Supabase a un mensaje claro en español
#      (RUC repetido, dato obligatorio vacío, valor que la base no acepta, permiso/RLS, base que no responde)
#      y devuelve también el texto exacto de la base para poder copiarlo.
#   2. Si el error es "el número interno (id) ya existe" (contador de la tabla atrasado, pasa cuando se
#      cargan datos a mano o desde Excel con su id), se corrige el contador solo. NUNCA borra ni cambia datos.
#   3. Cada guardado que falla (en el servidor o en el navegador) queda en la tabla erp_log_errores, que se ve
#      en Herramientas ▸ Registro de errores y no se pierde cuando Render se reinicia.
import logging
import re
import traceback

import psycopg2
from flask import Blueprint, g, jsonify, request, session

from database import get_connection

diagnostico_bp = Blueprint('diagnostico', __name__)
log = logging.getLogger('erp.diagnostico')

DDL = """
CREATE TABLE IF NOT EXISTS erp_log_errores (
    id bigserial PRIMARY KEY,
    fecha timestamptz NOT NULL DEFAULT now(),
    origen text NOT NULL DEFAULT 'servidor',
    usuario text,
    empresa text,
    metodo text,
    ruta text,
    estado integer,
    mensaje text,
    detalle text,
    navegador text
);
CREATE INDEX IF NOT EXISTS idx_erp_log_errores_fecha ON erp_log_errores (fecha DESC);
"""
_tabla_lista = False

NOMBRE_TABLA = {'clientes': 'Clientes', 'cotizaciones': 'Cotizaciones', 'cotizacion_detalle': 'Detalle de cotización',
                'clientes_contactos': 'Contactos del cliente', 'clientes_puntos_entrega': 'Puntos de entrega del cliente',
                'proveedores': 'Proveedores', 'productos': 'Productos', 'ordenes_compra': 'Órdenes de compra'}
NOMBRE_CAMPO = {'razon_social': 'Razón social', 'numero_documento': 'RUC/DNI', 'tipo_documento': 'Tipo de documento',
                'direccion_fiscal': 'Dirección fiscal', 'nombre_contacto': 'Nombre del contacto', 'cliente_id': 'Cliente',
                'producto_id': 'Producto', 'vendedor_id': 'Vendedor', 'empresa_id': 'Empresa'}
# Restricciones conocidas de la base real (tests/schema_supabase_real.sql)
MENSAJE_RESTRICCION = {
    'clientes_tipo_documento_check': 'La base solo acepta RUC o DNI como tipo de documento del cliente.',
    'clientes_numero_documento_key': 'Este RUC/DNI ya está registrado en Clientes. Búscalo en la lista en lugar de crearlo otra vez.',
}


def _asegurar_tabla():
    global _tabla_lista
    if _tabla_lista:
        return True
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(DDL)
            conn.commit()
        finally:
            conn.close()
        _tabla_lista = True
    except Exception as e:  # sin la tabla igual queda el registro en memoria
        log.warning('No se pudo crear erp_log_errores: %s', e)
    return _tabla_lista


def registrar_fallo(mensaje, detalle='', origen='servidor', estado=None, ruta=None, metodo=None, navegador=None):
    """Guarda un fallo de guardado. Nunca lanza error (si la base no responde, queda solo en memoria)."""
    usuario = empresa = None
    try:
        usuario = session.get('usuario')
        empresa = session.get('empresa')
        ruta = ruta or request.path
        metodo = metodo or request.method
    except Exception:
        pass
    fila = (origen, usuario, empresa, metodo, (ruta or '')[:300], estado, str(mensaje or '')[:2000],
            str(detalle or '')[:6000], (navegador or '')[:300])
    try:
        if _asegurar_tabla():
            conn = get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("""INSERT INTO erp_log_errores (origen, usuario, empresa, metodo, ruta, estado, mensaje,
                                   detalle, navegador) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""", fila)
                conn.commit()
            finally:
                conn.close()
            return
    except Exception as e:
        log.warning('No se pudo guardar el fallo en erp_log_errores: %s', e)
    log.warning('Fallo al guardar [%s] %s %s (%s): %s | %s', origen, metodo, ruta, usuario, mensaje, detalle)


def ultimos_fallos(n=200):
    if not _asegurar_tabla():
        return []
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT to_char(fecha AT TIME ZONE 'America/Lima', 'DD/MM/YYYY HH24:MI:SS'), origen, usuario,
                                  empresa, metodo, ruta, estado, mensaje, detalle
                           FROM erp_log_errores ORDER BY fecha DESC LIMIT %s""", (n,))
            filas = cur.fetchall()
    finally:
        conn.close()
    return [{'fecha': f[0], 'nivel': 'ERROR', 'origen': f"Fallo al guardar ({f[1]})",
             'mensaje': f"{f[2] or '-'} · {f[3] or '-'} · {f[4] or ''} {f[5] or ''} [{f[6] or '-'}] {f[7] or ''}"
                        + (f" | Detalle: {f[8]}" if f[8] else '')} for f in filas]


def reparar_contador(tabla):
    """Pone el contador del id de la tabla en el id más alto que ya existe. No toca ningún dato."""
    if not re.fullmatch(r'[a-z_][a-z0-9_]*', tabla or ''):
        return False
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_get_serial_sequence(%s, 'id')", ('public.' + tabla,))
            fila = cur.fetchone()
            secuencia = fila[0] if fila else None
            if not secuencia:
                # Columnas con DEFAULT nextval('...') que no son "serial" (así está la base real)
                cur.execute("""SELECT column_default FROM information_schema.columns
                               WHERE table_schema = 'public' AND table_name = %s AND column_name = 'id'""", (tabla,))
                fila = cur.fetchone()
                m = re.search(r"nextval\('([^']+)'", (fila[0] or '') if fila else '')
                secuencia = m.group(1) if m else None
            if not secuencia:
                return False
            cur.execute(f"SELECT setval(%s, GREATEST((SELECT COALESCE(MAX(id), 0) FROM public.{tabla}), 1))", (secuencia,))
        conn.commit()
        log.warning('Contador de %s corregido (estaba atrasado)', tabla)
        return True
    except Exception as e:
        log.warning('No se pudo corregir el contador de %s: %s', tabla, e)
        return False
    finally:
        conn.close()


def explicar_error_bd(e, que='el registro'):
    """(mensaje claro, detalle exacto, campo) de un error de la base."""
    detalle = (getattr(e, 'pgerror', None) or str(e) or e.__class__.__name__).strip()
    diag = getattr(e, 'diag', None)
    tabla = getattr(diag, 'table_name', None) or ''
    columna = getattr(diag, 'column_name', None) or ''
    restriccion = getattr(diag, 'constraint_name', None) or ''
    codigo = getattr(e, 'pgcode', None) or ''
    nombre_tabla = NOMBRE_TABLA.get(tabla, tabla)
    campo = columna or None
    if restriccion in MENSAJE_RESTRICCION:
        mensaje = MENSAJE_RESTRICCION[restriccion]
        if restriccion == 'clientes_numero_documento_key':
            campo = 'numero_documento'
        elif restriccion == 'clientes_tipo_documento_check':
            campo = 'tipo_documento'
    elif codigo == '23505' and restriccion.endswith('_pkey'):
        arreglado = reparar_contador(tabla)
        mensaje = (f"No se pudo guardar {que}: el contador interno de {nombre_tabla} estaba atrasado "
                   f"(pasa cuando se cargan datos desde Excel con su número). "
                   + ("Ya lo corregí: vuelve a presionar Guardar." if arreglado else
                      "Avísale al administrador (Herramientas ▸ Registro de errores)."))
    elif codigo == '23505':
        mensaje = f"No se pudo guardar {que}: ya existe otro registro con ese mismo dato ({restriccion or 'dato único'})."
    elif codigo == '23502':
        mensaje = f"No se pudo guardar {que}: falta el dato obligatorio «{NOMBRE_CAMPO.get(columna, columna)}»."
    elif codigo == '23503':
        mensaje = (f"No se pudo guardar {que}: hace referencia a un registro que no existe o fue eliminado "
                   f"({NOMBRE_CAMPO.get(columna, columna) or restriccion}).")
    elif codigo == '23514':
        mensaje = f"No se pudo guardar {que}: la base no acepta uno de los valores ({restriccion})."
    elif codigo in ('22P02', '22003', '22001', '22007', '22008'):
        mensaje = f"No se pudo guardar {que}: un dato tiene un formato que la base no acepta (número, fecha o texto muy largo)."
    elif codigo == '42501' or 'row-level security' in detalle.lower():
        mensaje = (f"No se pudo guardar {que}: la base de datos lo bloqueó por permisos (RLS) en {nombre_tabla or 'la tabla'}. "
                   f"Avísale al administrador.")
    elif codigo in ('42703', '42P01'):
        mensaje = f"No se pudo guardar {que}: a la base le falta una columna o tabla que el sistema necesita (falta una migración)."
    elif codigo == '57014' or isinstance(e, psycopg2.OperationalError):
        mensaje = f"No se pudo guardar {que}: la base de datos no respondió a tiempo. Espera unos segundos y vuelve a intentar."
    else:
        mensaje = f"No se pudo guardar {que}: {detalle.splitlines()[0] if detalle else 'error desconocido'}"
    return mensaje, detalle, campo


def respuesta_error_bd(e, que='el registro', estado=None):
    """Respuesta JSON lista para devolver, con el error explicado y registrado."""
    mensaje, detalle, campo = explicar_error_bd(e, que)
    if estado is None:
        codigo = getattr(e, 'pgcode', None) or ''
        estado = 409 if codigo.startswith('23') else 500
    traceback.print_exc()
    registrar_fallo(mensaje, detalle, estado=estado)
    try:
        g.fallo_registrado = True
    except Exception:
        pass
    cuerpo = {'success': False, 'error': mensaje, 'detalle': detalle, 'codigo': 'error_bd'}
    if campo:
        cuerpo['campo'] = campo
    return jsonify(cuerpo), estado


@diagnostico_bp.route('/api/diagnostico/fallo', methods=['POST'])
def api_fallo_navegador():
    """El navegador avisa un guardado que falló sin respuesta clara del servidor (sin conexión, Render dormido...)."""
    if 'usuario_id' not in session:
        return jsonify({'success': False}), 401
    d = request.get_json(silent=True) or {}
    try:
        estado = int(d.get('estado') or 0) or None
    except (TypeError, ValueError):
        estado = None
    registrar_fallo(d.get('mensaje'), d.get('detalle'), origen='navegador', estado=estado,
                    ruta=str(d.get('ruta') or '')[:300], metodo=str(d.get('metodo') or '')[:10],
                    navegador=request.headers.get('User-Agent', ''))
    return jsonify({'success': True})
