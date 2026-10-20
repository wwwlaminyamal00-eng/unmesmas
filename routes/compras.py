# routes/compras.py - Módulo de Compras

import sys
import os

# Asegurar que la raíz del proyecto esté en el path de Python
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
from datetime import datetime
import json

# Importar desde database.py
from database import db_query, db_execute, db_tx, get_connection
from psycopg2.extras import RealDictCursor
from utils import calcular_totales, a_decimal, redondear, bloquear_numeracion, es_admin
from datetime import date

# ============================================================
# CREAR EL BLUEPRINT
# ============================================================
compras_bp = Blueprint('compras', __name__)


@compras_bp.before_request
def _asegurar_columnas():
    # Columnas nuevas (motivo de compra sin pedido, PC/cotización/cliente de la OC, registro de anulaciones)
    if request.path.startswith('/compras') and 'usuario' in session:
        try:
            from routes.compras_flujo import asegurar_tablas_compras
            asegurar_tablas_compras()
        except Exception as e:
            print(f'⚠️ Compras: no se pudieron asegurar las tablas: {e}')


# ============================================================
# AYUDAS: FECHAS, FILTROS DE LISTAS Y CANDADOS
# ============================================================
def _fecha_iso(v):
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return str(v or '')[:10]


def _fecha_hora(v):
    """DD/MM/YYYY HH:MM para las listas."""
    if isinstance(v, datetime):
        return v.strftime('%d/%m/%Y %H:%M')
    if isinstance(v, date):
        return v.strftime('%d/%m/%Y')
    return ''


def _filtrar_api(datos, campos):
    """Filtros de las listas (los mismos de la pantalla): ?q= texto, ?estado=, ?desde=AAAA-MM-DD, ?hasta=AAAA-MM-DD.
    La fecha se compara como texto AAAA-MM-DD (sin zona horaria) para que "hoy" incluya lo de hoy."""
    q = (request.args.get('q') or '').strip().lower()
    estado = (request.args.get('estado') or '').strip()
    desde = (request.args.get('desde') or '').strip()[:10]
    hasta = (request.args.get('hasta') or '').strip()[:10]
    res = []
    for d in datos:
        if q and not any(q in str(d.get(c) or '').lower() for c in campos):
            continue
        if estado and (d.get('estado') or '') != estado:
            continue
        f = d.get('fecha') or ''
        if desde and (not f or f < desde):
            continue
        if hasta and (not f or f > hasta):
            continue
        res.append(d)
    return res


def _exigir_admin_y_motivo():
    """Candado de Erika: anular o eliminar en Compras solo lo hace un administrador y con motivo.
    Devuelve (motivo, None) o (None, respuesta_de_error)."""
    if not es_admin():
        return None, (jsonify({'success': False, 'error': 'Solo un administrador puede anular o eliminar en Compras.'}), 403)
    datos = request.get_json(silent=True) or {}
    motivo = (datos.get('motivo') or request.args.get('motivo') or '').strip()
    if len(motivo) < 5:
        return None, (jsonify({'success': False, 'error': 'Escribe el motivo (obligatorio, mínimo 5 letras).'}), 400)
    return motivo, None


def _registrar_anulacion(cur, tabla, registro_id, numero, accion, motivo, respaldo=None):
    from routes.compras_flujo import registrar_anulacion
    registrar_anulacion(cur, tabla, registro_id, numero, accion, motivo, respaldo)

# ============================================================
# FUNCIÓN LOGIN REQUIRED
# ============================================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session:
            if request.path.startswith('/compras/api/'):
                return jsonify({'error': 'Sesión expirada o no autorizada. Inicia sesión.'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# ============================================================
# FUNCIONES DE AYUDA PARA SOLICITUDES DE COMPRA
# ============================================================

def obtener_solicitudes_db():
    """Obtiene todas las solicitudes de compra"""
    try:
        query = """
            SELECT 
                id, numero_solicitud, fecha, estado,
                producto, cantidad, unidad, area, solicitante,
                urgencia, justificacion,
                created_at, updated_at
            FROM solicitudes_compra
            ORDER BY id DESC
        """
        return db_query(query)
    except Exception as e:
        print(f"❌ Error en obtener_solicitudes_db: {e}")
        return []


def obtener_solicitud_por_id_db(solicitud_id):
    """Obtiene una solicitud de compra por su ID"""
    try:
        query = """
            SELECT 
                id, numero_solicitud, fecha, estado,
                producto, cantidad, unidad, area, solicitante,
                urgencia, justificacion,
                created_at, updated_at
            FROM solicitudes_compra
            WHERE id = %s
        """
        result = db_query(query, (solicitud_id,))
        return result[0] if result else None
    except Exception as e:
        print(f"❌ Error en obtener_solicitud_por_id_db: {e}")
        return None


def guardar_solicitud_db(data):
    """Guarda una nueva solicitud de compra"""
    try:
        query = """
            INSERT INTO solicitudes_compra (
                numero_solicitud, fecha, estado,
                producto, cantidad, unidad, area, solicitante,
                urgencia, justificacion,
                creado_por
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING id, numero_solicitud
        """
        params = (
            data.get('numero_solicitud'),
            data.get('fecha') or datetime.now().isoformat(),
            data.get('estado', 'Borrador'),
            data.get('producto'),
            float(data.get('cantidad', 1)),
            data.get('unidad', 'UND'),
            data.get('area'),
            data.get('solicitante'),
            data.get('urgencia', 'Media'),
            data.get('justificacion', ''),
            session.get('usuario_id')
        )
        result = db_query(query, params)
        return result[0] if result else None
    except Exception as e:
        print(f"❌ Error en guardar_solicitud_db: {e}")
        raise


def actualizar_solicitud_db(solicitud_id, data):
    """Actualiza una solicitud de compra existente"""
    try:
        query = """
            UPDATE solicitudes_compra SET
                producto = %s,
                cantidad = %s,
                unidad = %s,
                area = %s,
                solicitante = %s,
                urgencia = %s,
                justificacion = %s,
                estado = %s,
                updated_at = NOW()
            WHERE id = %s
            RETURNING id, numero_solicitud
        """
        params = (
            data.get('producto'),
            float(data.get('cantidad', 1)),
            data.get('unidad', 'UND'),
            data.get('area'),
            data.get('solicitante'),
            data.get('urgencia', 'Media'),
            data.get('justificacion', ''),
            data.get('estado', 'Borrador'),
            solicitud_id
        )
        result = db_query(query, params)
        return result[0] if result else None
    except Exception as e:
        print(f"❌ Error en actualizar_solicitud_db: {e}")
        raise


# ============================================================
# FUNCIONES DE AYUDA PARA COMPARATIVOS DE PROVEEDORES
# ============================================================

def obtener_comparativos_db():
    """Obtiene todos los comparativos de proveedores"""
    try:
        query = """
            SELECT 
                id, numero_comparativo, fecha, estado,
                producto, proveedores_json,
                created_at, updated_at
            FROM comparativos_proveedores
            ORDER BY id DESC
        """
        results = db_query(query)
        for row in results:
            if row.get('proveedores_json'):
                try:
                    row['proveedores'] = json.loads(row['proveedores_json'])
                except:
                    row['proveedores'] = []
            else:
                row['proveedores'] = []
        return results
    except Exception as e:
        print(f"❌ Error en obtener_comparativos_db: {e}")
        return []


def guardar_comparativo_db(data):
    """Guarda un nuevo comparativo de proveedores"""
    try:
        proveedores_json = json.dumps(data.get('proveedores', []))
        
        query = """
            INSERT INTO comparativos_proveedores (
                numero_comparativo, fecha, estado,
                producto, proveedores_json,
                creado_por
            ) VALUES (
                %s, %s, %s, %s, %s, %s
            )
            RETURNING id, numero_comparativo
        """
        params = (
            data.get('numero_comparativo'),
            data.get('fecha') or datetime.now().isoformat(),
            data.get('estado', 'Borrador'),
            data.get('producto'),
            proveedores_json,
            session.get('usuario_id')
        )
        result = db_query(query, params)
        return result[0] if result else None
    except Exception as e:
        print(f"❌ Error en guardar_comparativo_db: {e}")
        raise


# ============================================================
# FUNCIONES DE AYUDA PARA ÓRDENES DE COMPRA
# ============================================================

def obtener_ordenes_db():
    """Obtiene todas las órdenes de compra usando tu estructura real"""
    try:
        query = """
            SELECT 
                id, numero_orden, codigo_orden, correlativo,
                proveedor_id, usuario_id, fecha_creacion, estado,
                subtotal, igv, total, condicion_pago, tiempo_entrega,
                fecha_requerida, lugar_entrega, num_cotizacion,
                nota_compra, notas,
                descuento_porcentaje, descuento_monto, descuento_tipo,
                contacto_proveedor, telefono_proveedor, email_proveedor,
                created_at, updated_at, flujo, motivo_compra, motivo_stock, pedido_id,
                pc_numeros, cotizaciones_cliente, clientes_pedido, motivo_anulacion
            FROM ordenes_compra
            ORDER BY id DESC
        """
        results = db_query(query)
        
        # Obtener items para cada orden
        for row in results:
            row['items'] = []
            if row.get('id'):
                try:
                    items_query = """
                        SELECT producto, cantidad, precio_unitario, total
                        FROM ordenes_compra_items
                        WHERE orden_compra_id = %s
                    """
                    items = db_query(items_query, (row['id'],))
                    row['items'] = items if items else []
                except Exception as e:
                    print(f"⚠️ Error obteniendo items para orden {row['id']}: {e}")
                    row['items'] = []
        
        return results
    except Exception as e:
        print(f"❌ Error en obtener_ordenes_db: {e}")
        import traceback
        traceback.print_exc()
        return []


def _resolver_proveedor_id(cur, data):
    """Obtiene el proveedor_id a partir del id, RUC o razón social que envía el formulario."""
    if data.get('proveedor_id'):
        return data.get('proveedor_id')
    ruc = (data.get('ruc') or '').strip()
    if ruc:
        cur.execute("SELECT id FROM proveedores WHERE ruc = %s ORDER BY id LIMIT 1", (ruc,))
        fila = cur.fetchone()
        if fila:
            return fila['id']
    nombre = (data.get('proveedor') or '').strip()
    if nombre:
        cur.execute("""SELECT id FROM proveedores
                       WHERE UPPER(razon_social) = UPPER(%s) OR UPPER(razon_comercial) = UPPER(%s)
                       ORDER BY id LIMIT 1""", (nombre, nombre))
        fila = cur.fetchone()
        if fila:
            return fila['id']
    return None


def _normalizar_items_orden(items):
    """Acepta precio_unitario o precioUnitario (el formulario usa este último) y recalcula el total."""
    normalizados = []
    for it in items or []:
        cantidad = a_decimal(it.get('cantidad'))
        precio = a_decimal(it.get('precio_unitario', it.get('precioUnitario', 0)))
        producto = (it.get('producto') or '').strip()
        if not producto or producto == 'Sin producto':
            continue
        if cantidad <= 0:
            raise ValueError(f'La cantidad de "{producto}" debe ser mayor a 0')
        if precio < 0:
            raise ValueError(f'El precio de "{producto}" no puede ser negativo')
        normalizados.append({'producto': producto, 'cantidad': cantidad, 'precio': precio,
                             'total': redondear(cantidad * precio)})
    return normalizados


ESTADOS_OC_CERRADOS = ('Confirmada', 'Recibida', 'Anulada')


def _es_oc_nueva(orden_id):
    """True si la OC pertenece al nuevo flujo de Compras (routes/compras_flujo.py)."""
    try:
        f = db_query("SELECT flujo FROM ordenes_compra WHERE id = %s", (orden_id,))
        return bool(f and f[0].get('flujo') == 'v2')
    except Exception:
        return False  # la columna aún no existe: no hay OC nuevas


def guardar_orden_db(data):
    """
    Guarda (crea o actualiza) una orden de compra y sus items en UNA transacción.
    Antes: los items no se guardaban al editar, los errores de items se ignoraban,
    el precio llegaba en 0 (precioUnitario vs precio_unitario) y la OC quedaba sin proveedor.
    """
    items = _normalizar_items_orden(data.get('items'))
    if not items:
        raise ValueError('La orden de compra debe tener al menos un producto')
    pedido = _pedido_de_orden(data)
    totales = calcular_totales([{'cantidad': i['cantidad'], 'precio': i['precio']} for i in items],
                               data.get('descuento_porcentaje', 0), '%')

    with db_tx() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        proveedor_id = _resolver_proveedor_id(cur, data)
        orden_id = data.get('id')

        if orden_id:
            cur.execute("SELECT * FROM ordenes_compra WHERE id = %s FOR UPDATE", (orden_id,))
            fila = cur.fetchone()
            if not fila:
                raise ValueError('La orden de compra no existe')
            if fila.get('flujo') == 'v2':
                raise PermissionError('Esta orden se hizo en la nueva pantalla de Compras: corrígela allí.')
            if fila['estado'] in ESTADOS_OC_CERRADOS:
                raise PermissionError(f'La orden está "{fila["estado"]}" y ya no se puede modificar')
            cur.execute("""
                UPDATE ordenes_compra SET
                    proveedor_id = COALESCE(%s, proveedor_id), estado = %s,
                    subtotal = %s, igv = %s, total = %s, descuento_monto = %s,
                    condicion_pago = %s, tiempo_entrega = %s, fecha_requerida = %s,
                    lugar_entrega = %s, num_cotizacion = %s, nota_compra = %s, notas = %s,
                    contacto_proveedor = %s, telefono_proveedor = %s, email_proveedor = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING id, numero_orden
            """, (proveedor_id, data.get('estado', 'Borrador'), totales['subtotal'], totales['igv'],
                  totales['total'], totales['descuento'], data.get('condicion_pago', 'Contado'),
                  data.get('tiempo_entrega', '5 días hábiles'), data.get('fecha_requerida') or None,
                  data.get('lugar_entrega'), data.get('num_cotizacion'), data.get('nota_compra'),
                  data.get('notas'), data.get('contacto_proveedor') or data.get('proveedor'),
                  data.get('telefono_proveedor'), data.get('email_proveedor'), orden_id))
            resultado = cur.fetchone()
            cur.execute("DELETE FROM ordenes_compra_items WHERE orden_compra_id = %s", (orden_id,))
            _guardar_pedido_orden(cur, orden_id, pedido)
        else:
            prefijo = f"OC-{datetime.now().strftime('%Y%m%d')}-"
            bloquear_numeracion(cur, 'ordenes_compra:' + prefijo)
            numero = (data.get('numero_orden') or '').strip()
            if numero:
                cur.execute("SELECT 1 FROM ordenes_compra WHERE numero_orden = %s", (numero,))
                if cur.fetchone():
                    numero = ''  # el número propuesto por el navegador ya existe: se genera otro
            if not numero:
                cur.execute("""SELECT COALESCE(MAX(NULLIF(regexp_replace(SUBSTRING(numero_orden FROM %s), '\\D', '', 'g'), '')::int), 0) + 1 AS sig
                               FROM ordenes_compra WHERE numero_orden LIKE %s""", (len(prefijo) + 1, prefijo + '%'))
                numero = prefijo + str(cur.fetchone()['sig']).zfill(4)
            cur.execute("""
                INSERT INTO ordenes_compra (
                    numero_orden, codigo_orden, correlativo, proveedor_id, usuario_id, estado,
                    subtotal, igv, total, condicion_pago, tiempo_entrega, fecha_requerida,
                    lugar_entrega, num_cotizacion, nota_compra, notas,
                    descuento_porcentaje, descuento_monto, descuento_tipo,
                    contacto_proveedor, telefono_proveedor, email_proveedor
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, numero_orden
            """, (numero, numero, numero[-4:], proveedor_id, session.get('usuario_id'),
                  data.get('estado', 'Borrador'), totales['subtotal'], totales['igv'], totales['total'],
                  data.get('condicion_pago', 'Contado'), data.get('tiempo_entrega', '5 días hábiles'),
                  data.get('fecha_requerida') or None, data.get('lugar_entrega'), data.get('num_cotizacion'),
                  data.get('nota_compra'), data.get('notas'), a_decimal(data.get('descuento_porcentaje', 0)),
                  totales['descuento'], data.get('descuento_tipo', 'porcentaje'),
                  data.get('contacto_proveedor') or data.get('proveedor'),
                  data.get('telefono_proveedor'), data.get('email_proveedor')))
            resultado = cur.fetchone()
            orden_id = resultado['id']
            _guardar_pedido_orden(cur, orden_id, pedido)

        for it in items:
            cur.execute("""
                INSERT INTO ordenes_compra_items (orden_compra_id, producto, cantidad, precio_unitario, total)
                VALUES (%s, %s, %s, %s, %s)
            """, (orden_id, it['producto'], it['cantidad'], it['precio'], it['total']))

        resultado = dict(resultado)
        resultado.update({'subtotal': float(totales['subtotal']), 'igv': float(totales['igv']),
                          'total': float(totales['total']), 'proveedor_id': proveedor_id})
        return resultado


def _pedido_de_orden(data):
    """La OC dice para qué pedido del cliente (PC) es. Sin PC es una "Compra sin pedido" y el motivo es obligatorio."""
    from routes.compras_flujo import motivo_sin_pedido, ErrorCompras
    pedido_id = data.get('pedido_id') or None
    if pedido_id:
        try:
            pedido_id = int(pedido_id)
        except (TypeError, ValueError):
            raise ValueError('El pedido del cliente no es válido')
        pc = db_query("""SELECT id, numero, cliente, cotizacion_numero, estado FROM pedido_compra_pc WHERE id = %s""", (pedido_id,))
        if not pc:
            raise ValueError('El pedido del cliente no existe')
        pc = pc[0]
        return {'pedido_id': pc['id'], 'pc_numeros': pc['numero'], 'cotizaciones_cliente': pc.get('cotizacion_numero'),
                'clientes_pedido': pc.get('cliente'), 'motivo_compra': None, 'motivo_stock': None}
    try:
        motivo, detalle = motivo_sin_pedido(data)
    except ErrorCompras as e:
        raise ValueError(str(e))
    return {'pedido_id': None, 'pc_numeros': None, 'cotizaciones_cliente': None, 'clientes_pedido': None,
            'motivo_compra': motivo, 'motivo_stock': detalle}


def _guardar_pedido_orden(cur, orden_id, p):
    cur.execute("""UPDATE ordenes_compra SET pedido_id = %s, pc_numeros = %s, cotizaciones_cliente = %s, clientes_pedido = %s,
                          motivo_compra = %s, motivo_stock = %s, tipo_compra = %s WHERE id = %s""",
                (p['pedido_id'], p['pc_numeros'], p['cotizaciones_cliente'], p['clientes_pedido'], p['motivo_compra'],
                 p['motivo_stock'], 'Bajo pedido' if p['pedido_id'] else 'Para stock', orden_id))


def actualizar_orden_db(orden_id, data):
    """Actualiza una orden de compra existente"""
    try:
        query = """
            UPDATE ordenes_compra SET
                estado = %s,
                condicion_pago = %s,
                tiempo_entrega = %s,
                fecha_requerida = %s,
                lugar_entrega = %s,
                nota_compra = %s,
                notas = %s,
                updated_at = NOW()
            WHERE id = %s
            RETURNING id, numero_orden
        """
        params = (
            data.get('estado', 'pendiente'),
            data.get('condicion_pago', 'Contado'),
            data.get('tiempo_entrega', '5 días hábiles'),
            data.get('fecha_requerida'),
            data.get('lugar_entrega'),
            data.get('nota_compra'),
            data.get('notas'),
            orden_id
        )
        result = db_query(query, params)
        return result[0] if result else None
    except Exception as e:
        print(f"❌ Error en actualizar_orden_db: {e}")
        raise


# ============================================================
# FUNCIONES DE AYUDA PARA COMPROBANTES DE PROVEEDOR
# ============================================================

def obtener_comprobantes_proveedor_db():
    """Obtiene todos los comprobantes de proveedor"""
    try:
        query = """
            SELECT 
                id,
                tipo,
                numero,
                fecha,
                monto,
                ruc_proveedor,
                proveedor_nombre,
                orden_compra_id,
                orden_compra_numero,
                estado,
                observaciones,
                creado_por,
                created_at,
                updated_at
            FROM comprobantes_proveedor
            ORDER BY id DESC
        """
        rows = db_query(query) or []

        normalized = []
        for r in rows:
            normalized.append({
                'id': r.get('id'),
                'tipo': r.get('tipo') or 'Factura',
                'numero': r.get('numero') or '',
                'fecha': r.get('fecha'),
                'monto': float(r.get('monto') or 0),
                'ruc_proveedor': r.get('ruc_proveedor') or '',
                'ruc': r.get('ruc_proveedor') or '',
                'proveedor_nombre': r.get('proveedor_nombre') or '',
                'proveedor': r.get('proveedor_nombre') or '',
                'orden_compra_id': r.get('orden_compra_id'),
                'orden_compra_numero': r.get('orden_compra_numero') or '',
                'orden_compra': r.get('orden_compra_numero') or '',
                'estado': r.get('estado') or 'Pendiente',
                'observaciones': r.get('observaciones') or '',
                'created_at': r.get('created_at'),
                'updated_at': r.get('updated_at'),
            })

        return normalized

    except Exception as e:
        print(f"❌ Error en obtener_comprobantes_proveedor_db: {e}")
        import traceback
        traceback.print_exc()
        return []


def guardar_comprobante_proveedor_db(data):
    """Guarda un nuevo comprobante de proveedor"""
    try:
        query = """
            INSERT INTO comprobantes_proveedor (
                tipo, numero, fecha, monto,
                ruc_proveedor, proveedor_nombre,
                orden_compra_id, orden_compra_numero,
                estado, observaciones,
                creado_por
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING id, numero
        """
        params = (
            data.get('tipo', 'Factura'),
            data.get('numero'),
            data.get('fecha') or datetime.now().isoformat(),
            float(data.get('monto', 0)),
            data.get('ruc') or data.get('ruc_proveedor') or '',
            data.get('proveedor') or data.get('proveedor_nombre') or '',
            data.get('orden_compra_id'),
            data.get('orden_compra') or data.get('orden_compra_numero') or '',
            data.get('estado', 'Pendiente'),
            data.get('observaciones', ''),
            session.get('usuario_id')
        )
        result = db_query(query, params)
        return result[0] if result else None
    except Exception as e:
        print(f"❌ Error en guardar_comprobante_proveedor_db: {e}")
        import traceback
        traceback.print_exc()
        raise


# ============================================================
# FUNCIONES DE AYUDA PARA RECEPCIÓN DE MERCADERÍA
# ============================================================

def obtener_recepciones_db():
    """Obtiene todas las recepciones de mercadería"""
    try:
        query = """
            SELECT 
                id,
                numero_recepcion,
                fecha,
                estado,
                orden_compra_id,
                orden_compra_numero,
                proveedor_nombre,
                producto,
                cantidad,
                unidad,
                estado_mercaderia,
                observaciones,
                creado_por,
                created_at,
                updated_at
            FROM recepciones_mercaderia
            ORDER BY id DESC
        """
        rows = db_query(query) or []

        normalized = []
        for r in rows:
            normalized.append({
                'id': r.get('id'),
                'numero': r.get('numero_recepcion') or '',
                'numero_recepcion': r.get('numero_recepcion') or '',
                'fecha': r.get('fecha'),
                'estado': r.get('estado') or 'Pendiente',
                'orden_compra_id': r.get('orden_compra_id'),
                'orden_compra': r.get('orden_compra_numero') or '',
                'orden': r.get('orden_compra_numero') or '',
                'orden_compra_numero': r.get('orden_compra_numero') or '',
                'proveedor': r.get('proveedor_nombre') or '',
                'proveedor_nombre': r.get('proveedor_nombre') or '',
                'producto': r.get('producto') or '',
                'cantidad': float(r.get('cantidad') or 0),
                'unidad': r.get('unidad') or 'UND',
                'estado_mercaderia': r.get('estado_mercaderia') or '',
                'observaciones': r.get('observaciones') or '',
                'created_at': r.get('created_at'),
                'updated_at': r.get('updated_at'),
            })

        return normalized

    except Exception as e:
        print(f"❌ Error en obtener_recepciones_db: {e}")
        import traceback
        traceback.print_exc()
        return []


def guardar_recepcion_db(data):
    """Guarda una nueva recepción de mercadería"""
    try:
        query = """
            INSERT INTO recepciones_mercaderia (
                numero_recepcion, fecha, estado,
                orden_compra_id, orden_compra_numero, proveedor_nombre,
                producto, cantidad, unidad,
                estado_mercaderia, observaciones,
                creado_por
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING id, numero_recepcion
        """
        params = (
            data.get('numero_recepcion'),
            data.get('fecha') or datetime.now().isoformat(),
            data.get('estado', 'Pendiente'),
            data.get('orden_compra_id'),
            data.get('orden_compra') or data.get('orden_compra_numero') or '',
            data.get('proveedor') or data.get('proveedor_nombre') or '',
            data.get('producto'),
            float(data.get('cantidad', 1)),
            data.get('unidad', 'UND'),
            data.get('estado_mercaderia', 'Buen estado'),
            data.get('observaciones', ''),
            session.get('usuario_id')
        )
        result = db_query(query, params)
        return result[0] if result else None
    except Exception as e:
        print(f"❌ Error en guardar_recepcion_db: {e}")
        import traceback
        traceback.print_exc()
        raise


# ============================================================
# RUTAS PRINCIPALES
# ============================================================

@compras_bp.route('/compras/anterior')
@login_required
def compras():
    """Pantallas anteriores de Compras (se conservan). La nueva pantalla está en routes/compras_flujo.py (/compras)."""
    tab = request.args.get('tab', 'solicitud_compra')
    from routes.compras_flujo import MOTIVOS_SIN_PEDIDO
    return render_template('compras/index.html',
                         active_tab=tab, es_admin=es_admin(), motivos=MOTIVOS_SIN_PEDIDO,
                         usuario=session.get('usuario'),
                         nombre=session.get('nombre_completo'),
                         empresa=session.get('empresa'))


# ============================================================
# API - SOLICITUDES DE COMPRA
# ============================================================

@compras_bp.route('/compras/api/solicitudes/listar', methods=['GET'])
@login_required
def api_solicitudes_listar():
    """Lista todas las solicitudes de compra"""
    try:
        data = obtener_solicitudes_db()
        
        formatted_data = []
        for row in data:
            formatted_data.append({
                'id': row.get('id'),
                'numero': row.get('numero_solicitud'),
                'fecha': _fecha_iso(row.get('fecha') or row.get('created_at')),
                'creado': _fecha_hora(row.get('created_at') or row.get('fecha')),
                'estado': row.get('estado'),
                'producto': row.get('producto'),
                'cantidad': float(row.get('cantidad', 0)),
                'unidad': row.get('unidad', 'UND'),
                'area': row.get('area'),
                'solicitante': row.get('solicitante'),
                'urgencia': row.get('urgencia', 'Media'),
                'justificacion': row.get('justificacion', '')
            })
        formatted_data = _filtrar_api(formatted_data, ('numero', 'producto', 'solicitante', 'area'))
        return jsonify({'success': True, 'data': formatted_data})
    except Exception as e:
        print(f"❌ Error en api_solicitudes_listar: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@compras_bp.route('/compras/api/solicitudes/guardar', methods=['POST'])
@login_required
def api_solicitudes_guardar():
    """Guarda una solicitud de compra"""
    try:
        data = request.get_json()
        print(f"📦 Guardando solicitud: {data}")
        
        if not data.get('numero_solicitud'):
            count_data = db_query("SELECT COUNT(*) as total FROM solicitudes_compra")
            count = count_data[0]['total'] + 1 if count_data else 1
            data['numero_solicitud'] = f"SOL-{datetime.now().strftime('%Y%m%d')}-{str(count).zfill(4)}"
        
        if data.get('id'):
            print(f"✏️ Actualizando solicitud ID: {data['id']}")
            existing = obtener_solicitud_por_id_db(data['id'])
            if not existing:
                return jsonify({'success': False, 'error': 'Solicitud no encontrada'}), 404
            
            query = """
                UPDATE solicitudes_compra SET
                    producto = %s,
                    cantidad = %s,
                    unidad = %s,
                    area = %s,
                    solicitante = %s,
                    urgencia = %s,
                    justificacion = %s,
                    estado = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING id, numero_solicitud
            """
            params = (
                data.get('producto'),
                float(data.get('cantidad', 1)),
                data.get('unidad', 'UND'),
                data.get('area'),
                data.get('solicitante'),
                data.get('urgencia', 'Media'),
                data.get('justificacion', ''),
                data.get('estado', 'Borrador'),
                data['id']
            )
            result = db_query(query, params)
            
            if result:
                return jsonify({'success': True, 'message': 'Solicitud actualizada', 'data': result[0]})
            return jsonify({'success': False, 'error': 'No se pudo actualizar'}), 400
        
        print(f"🆕 Creando nueva solicitud")
        result = guardar_solicitud_db(data)
        if result:
            return jsonify({'success': True, 'message': 'Solicitud creada', 'data': result})
        return jsonify({'success': False, 'error': 'No se pudo crear'}), 400
        
    except Exception as e:
        print(f"❌ Error en api_solicitudes_guardar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@compras_bp.route('/compras/api/solicitudes/<int:id>/toggle', methods=['PUT'])
@login_required
def api_solicitudes_toggle(id):
    """Cambia el estado de una solicitud de compra"""
    try:
        data = request.get_json()
        nuevo_estado = data.get('estado')
        
        if not nuevo_estado:
            return jsonify({'success': False, 'error': 'Estado requerido'}), 400
        
        estados_validos = ['Borrador', 'Pendiente', 'Aprobada', 'Rechazada', 'Ordenada']
        if nuevo_estado not in estados_validos:
            return jsonify({'success': False, 'error': f'Estado inválido'}), 400
        
        query = """
            UPDATE solicitudes_compra 
            SET estado = %s, updated_at = NOW()
            WHERE id = %s
            RETURNING id, estado
        """
        result = db_query(query, (nuevo_estado, id))
        
        if result:
            return jsonify({
                'success': True,
                'message': f'Solicitud actualizada a {nuevo_estado}',
                'data': result[0]
            })
        
        return jsonify({'success': False, 'error': 'Solicitud no encontrada'}), 404
        
    except Exception as e:
        print(f"❌ Error en api_solicitudes_toggle: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@compras_bp.route('/compras/api/solicitudes/<int:id>', methods=['DELETE'])
@login_required
def api_solicitudes_eliminar(id):
    """Elimina una solicitud de compra (solo administrador, con motivo; queda un respaldo en com_anulaciones)"""
    try:
        motivo, error = _exigir_admin_y_motivo()
        if error:
            return error
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM solicitudes_compra WHERE id = %s FOR UPDATE", (id,))
            fila = cur.fetchone()
            if not fila:
                return jsonify({'success': False, 'error': 'Solicitud no encontrada'}), 404
            _registrar_anulacion(cur, 'solicitudes_compra', id, fila.get('numero_solicitud'), 'Eliminada', motivo, dict(fila))
            cur.execute("DELETE FROM solicitudes_compra WHERE id = %s", (id,))
        return jsonify({'success': True, 'message': 'Solicitud eliminada (queda registrada con tu motivo)'})
        
    except Exception as e:
        print(f"❌ Error en api_solicitudes_eliminar: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# API - COMPARATIVOS DE PROVEEDORES
# ============================================================

@compras_bp.route('/compras/api/comparativos/listar', methods=['GET'])
@login_required
def api_comparativos_listar():
    """Lista todos los comparativos de proveedores"""
    try:
        data = obtener_comparativos_db()
        
        formatted_data = []
        for row in data:
            proveedores = row.get('proveedores', [])
            mejor = None
            if proveedores:
                mejor = min(proveedores, key=lambda p: float(p.get('precio', 0))) if proveedores else None
            
            formatted_data.append({
                'id': row.get('id'),
                'numero': row.get('numero_comparativo'),
                'fecha': _fecha_iso(row.get('fecha') or row.get('created_at')),
                'creado': _fecha_hora(row.get('created_at') or row.get('fecha')),
                'estado': row.get('estado'),
                'producto': row.get('producto'),
                'proveedores': proveedores,
                'mejor_proveedor': mejor.get('nombre') if mejor else None,
                'mejor_precio': float(mejor.get('precio', 0)) if mejor else 0,
                'mejor_plazo': mejor.get('plazo') if mejor else None
            })
        formatted_data = _filtrar_api(formatted_data, ('numero', 'producto', 'mejor_proveedor'))
        return jsonify({'success': True, 'data': formatted_data})
    except Exception as e:
        print(f"❌ Error en api_comparativos_listar: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@compras_bp.route('/compras/api/comparativos/guardar', methods=['POST'])
@login_required
def api_comparativos_guardar():
    """Guarda un comparativo de proveedores"""
    try:
        data = request.get_json()
        print(f"📊 Guardando comparativo: {data}")
        
        if not data.get('numero_comparativo'):
            count_data = db_query("SELECT COUNT(*) as total FROM comparativos_proveedores")
            count = count_data[0]['total'] + 1 if count_data else 1
            data['numero_comparativo'] = f"CMP-{datetime.now().strftime('%Y%m%d')}-{str(count).zfill(4)}"
        
        result = guardar_comparativo_db(data)
        if result:
            return jsonify({'success': True, 'message': 'Comparativo guardado', 'data': result})
        return jsonify({'success': False, 'error': 'No se pudo guardar'}), 400
        
    except Exception as e:
        print(f"❌ Error en api_comparativos_guardar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@compras_bp.route('/compras/api/comparativos/<int:id>/toggle', methods=['PUT'])
@login_required
def api_comparativos_toggle(id):
    """Cambia el estado de un comparativo"""
    try:
        data = request.get_json()
        nuevo_estado = data.get('estado')
        
        if not nuevo_estado:
            return jsonify({'success': False, 'error': 'Estado requerido'}), 400
        
        estados_validos = ['Borrador', 'En evaluación', 'Seleccionado', 'Rechazado']
        if nuevo_estado not in estados_validos:
            return jsonify({'success': False, 'error': f'Estado inválido'}), 400
        
        query = """
            UPDATE comparativos_proveedores 
            SET estado = %s, updated_at = NOW()
            WHERE id = %s
            RETURNING id, estado
        """
        result = db_query(query, (nuevo_estado, id))
        
        if result:
            return jsonify({
                'success': True,
                'message': f'Comparativo actualizado a {nuevo_estado}',
                'data': result[0]
            })
        
        return jsonify({'success': False, 'error': 'Comparativo no encontrado'}), 404
        
    except Exception as e:
        print(f"❌ Error en api_comparativos_toggle: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# API - ÓRDENES DE COMPRA
# ============================================================

@compras_bp.route('/compras/api/ordenes/listar', methods=['GET'])
@login_required
def api_ordenes_listar():
    """Lista todas las órdenes de compra"""
    try:
        data = obtener_ordenes_db()
        
        formatted_data = []
        for row in data:
            proveedor_nombre = None
            proveedor_ruc = None
            proveedor_dir = ''
            if row.get('proveedor_id'):
                try:
                    prov_result = db_query("SELECT razon_social, ruc, direccion FROM proveedores WHERE id = %s", (row['proveedor_id'],))
                    if prov_result:
                        proveedor_nombre = prov_result[0].get('razon_social')
                        proveedor_ruc = prov_result[0].get('ruc')
                        proveedor_dir = prov_result[0].get('direccion') or ''
                except Exception as e:
                    print(f"⚠️ No se pudo obtener el proveedor {row.get('proveedor_id')}: {e}")
            for it in row.get('items', []):
                # el formulario de edición lee precioUnitario
                it['precioUnitario'] = float(it.get('precio_unitario') or 0)
            
            formatted_data.append({
                'id': row.get('id'),
                'numero': row.get('numero_orden'),
                'fecha': _fecha_iso(row.get('fecha_creacion') or row.get('created_at')),
                'creado': _fecha_hora(row.get('fecha_creacion') or row.get('created_at')),
                'flujo': row.get('flujo'),
                'sin_pedido': not row.get('pc_numeros'),
                'pedido_id': row.get('pedido_id'),
                'pc_numeros': row.get('pc_numeros') or '',
                'cotizaciones_cliente': row.get('cotizaciones_cliente') or '',
                'clientes_pedido': row.get('clientes_pedido') or '',
                'motivo_compra': row.get('motivo_compra') or '',
                'motivo_stock': row.get('motivo_stock') or '',
                'motivo_anulacion': row.get('motivo_anulacion') or '',
                'direccion': proveedor_dir,
                'contacto_proveedor': row.get('contacto_proveedor') or '',
                'telefono_proveedor': row.get('telefono_proveedor') or '',
                'email_proveedor': row.get('email_proveedor') or '',
                'tiempo_entrega': row.get('tiempo_entrega') or '',
                'lugar_entrega': row.get('lugar_entrega') or '',
                'fecha_requerida': row.get('fecha_requerida') or '',
                'descuento_porcentaje': float(row.get('descuento_porcentaje') or 0),
                'estado': row.get('estado'),
                'proveedor': proveedor_nombre or row.get('contacto_proveedor') or f"Proveedor ID: {row.get('proveedor_id')}",
                'ruc': proveedor_ruc or '',
                'condicion_pago': row.get('condicion_pago'),
                'moneda': 'Soles (S/)',
                'subtotal': float(row.get('subtotal') or 0),
                'igv': float(row.get('igv') or 0),
                'total': float(row.get('total') or 0),
                'items': row.get('items', []),
                'nota_compra': row.get('nota_compra', ''),
                'notas': row.get('notas', '')
            })
        formatted_data = _filtrar_api(formatted_data, ('numero', 'proveedor', 'ruc', 'pc_numeros', 'clientes_pedido', 'motivo_compra'))
        if request.args.get('sin_pedido') == '1':
            formatted_data = [o for o in formatted_data if o['sin_pedido']]
        return jsonify({'success': True, 'data': formatted_data})
    except Exception as e:
        print(f"❌ Error en api_ordenes_listar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@compras_bp.route('/compras/api/ordenes/guardar', methods=['POST'])
@login_required
def api_ordenes_guardar():
    """Guarda una orden de compra"""
    try:
        data = request.get_json(silent=True) or {}
        try:
            result = guardar_orden_db(data)
        except PermissionError as e:
            return jsonify({'success': False, 'error': str(e)}), 409
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        if result:
            advertencia = None if result.get('proveedor_id') else \
                'La orden se guardó sin proveedor registrado: verifica el RUC en Maestros > Proveedores.'
            return jsonify({'success': True, 'message': f"Orden de compra {result.get('numero_orden')} guardada",
                            'data': result, 'advertencia': advertencia})
        return jsonify({'success': False, 'error': 'No se pudo guardar'}), 400
        
    except Exception as e:
        print(f"❌ Error en api_ordenes_guardar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@compras_bp.route('/compras/api/ordenes/<int:id>/toggle', methods=['PUT'])
@login_required
def api_ordenes_toggle(id):
    """Cambia el estado de una orden de compra"""
    try:
        data = request.get_json()
        nuevo_estado = data.get('estado')
        
        if not nuevo_estado:
            return jsonify({'success': False, 'error': 'Estado requerido'}), 400
        
        estados_validos = ['Borrador', 'Emitida', 'Enviada', 'Confirmada', 'Anulada']
        if nuevo_estado not in estados_validos:
            return jsonify({'success': False, 'error': f'Estado inválido'}), 400
        if _es_oc_nueva(id):
            return jsonify({'success': False, 'error': 'Esta orden se maneja en la nueva pantalla de Compras (aprobación, pago y recepción).'}), 409
        if nuevo_estado == 'Anulada':
            motivo, error = _exigir_admin_y_motivo()
            if error:
                return error
            with db_tx() as conn:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                cur.execute("""UPDATE ordenes_compra SET estado = 'Anulada', motivo_anulacion = %s, anulado_por = %s,
                               anulado_en = NOW(), updated_at = NOW() WHERE id = %s RETURNING id, estado, numero_orden""",
                            (motivo, session.get('nombre_completo') or session.get('usuario'), id))
                fila = cur.fetchone()
                if not fila:
                    return jsonify({'success': False, 'error': 'Orden no encontrada'}), 404
                _registrar_anulacion(cur, 'ordenes_compra', id, fila['numero_orden'], 'Anulada', motivo)
            return jsonify({'success': True, 'message': 'Orden anulada', 'data': {'id': id, 'estado': 'Anulada'}})
        
        query = """
            UPDATE ordenes_compra 
            SET estado = %s, updated_at = NOW()
            WHERE id = %s
            RETURNING id, estado
        """
        result = db_query(query, (nuevo_estado, id))
        
        if result:
            return jsonify({
                'success': True,
                'message': f'Orden actualizada a {nuevo_estado}',
                'data': result[0]
            })
        
        return jsonify({'success': False, 'error': 'Orden no encontrada'}), 404
        
    except Exception as e:
        print(f"❌ Error en api_ordenes_toggle: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@compras_bp.route('/compras/api/ordenes/<int:id>', methods=['DELETE'])
@login_required
def api_ordenes_eliminar(id):
    """Elimina una orden de compra (solo si está en Borrador o Anulada)"""
    try:
        check_query = "SELECT id, estado FROM ordenes_compra WHERE id = %s"
        check_result = db_query(check_query, (id,))
        
        if not check_result:
            return jsonify({'success': False, 'error': 'Orden no encontrada'}), 404
        
        estado = check_result[0].get('estado')
        if _es_oc_nueva(id):
            return jsonify({'success': False, 'error': 'Las órdenes de la nueva pantalla de Compras no se eliminan: se anulan con motivo.'}), 409
        if estado not in ['Borrador', 'Anulada']:
            return jsonify({
                'success': False,
                'error': f'Solo se pueden eliminar órdenes en estado "Borrador" o "Anulada". Estado actual: {estado}'
            }), 400
        motivo, error = _exigir_admin_y_motivo()
        if error:
            return error
        
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM ordenes_compra WHERE id = %s", (id,))
            respaldo = dict(cur.fetchone() or {})
            cur.execute("SELECT producto, cantidad, precio_unitario, total FROM ordenes_compra_items WHERE orden_compra_id = %s", (id,))
            respaldo['items'] = [dict(x) for x in cur.fetchall()]
            _registrar_anulacion(cur, 'ordenes_compra', id, respaldo.get('numero_orden'), 'Eliminada', motivo, respaldo)
            cur.execute("DELETE FROM ordenes_compra_items WHERE orden_compra_id = %s", (id,))
            cur.execute("DELETE FROM ordenes_compra WHERE id = %s RETURNING id", (id,))
            result = cur.fetchall()
        
        if result:
            return jsonify({'success': True, 'message': 'Orden eliminada'})
        
        return jsonify({'success': False, 'error': 'No se pudo eliminar'}), 400
        
    except Exception as e:
        print(f"❌ Error en api_ordenes_eliminar: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# API - COMPROBANTES DE PROVEEDOR
# ============================================================

@compras_bp.route('/compras/api/comprobantes-proveedor/listar', methods=['GET'])
@login_required
def api_comprobantes_proveedor_listar():
    """Lista todos los comprobantes de proveedor"""
    try:
        data = obtener_comprobantes_proveedor_db()

        formatted_data = []
        for row in data:
            formatted_data.append({
                'id': row.get('id'),
                'tipo': row.get('tipo') or 'Factura',
                'numero': row.get('numero') or '',
                'fecha': _fecha_iso(row.get('fecha') or row.get('created_at')),
                'creado': _fecha_hora(row.get('created_at') or row.get('fecha')),
                'monto': float(row.get('monto') or 0),
                'ruc': row.get('ruc_proveedor') or '',
                'ruc_proveedor': row.get('ruc_proveedor') or '',
                'proveedor': row.get('proveedor_nombre') or '',
                'proveedor_nombre': row.get('proveedor_nombre') or '',
                'orden_compra': row.get('orden_compra_numero') or '',
                'orden_compra_numero': row.get('orden_compra_numero') or '',
                'estado': row.get('estado') or 'Pendiente',
                'observaciones': row.get('observaciones') or ''
            })
        formatted_data = _filtrar_api(formatted_data, ('numero', 'proveedor', 'ruc', 'orden_compra'))
        return jsonify({'success': True, 'data': formatted_data})

    except Exception as e:
        print(f"❌ Error en api_comprobantes_proveedor_listar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e), 'data': []}), 200


@compras_bp.route('/compras/api/comprobantes-proveedor/guardar', methods=['POST'])
@login_required
def api_comprobantes_proveedor_guardar():
    """Guarda un comprobante de proveedor"""
    try:
        data = request.get_json(silent=True) or {}
        numero = (data.get('numero') or '').strip()
        ruc = (data.get('ruc') or data.get('ruc_proveedor') or '').strip()
        tipo = data.get('tipo', 'Factura')
        if not numero:
            return jsonify({'success': False, 'error': 'El número del comprobante del proveedor es obligatorio'}), 400
        if ruc and not (len(ruc) == 11 and ruc.isdigit()):
            return jsonify({'success': False, 'error': 'El RUC del proveedor debe tener 11 dígitos'}), 400
        if a_decimal(data.get('monto')) <= 0:
            return jsonify({'success': False, 'error': 'El monto debe ser mayor a 0'}), 400
        # Evita registrar dos veces la misma factura del proveedor (afectaría cuentas por pagar)
        if db_query("""SELECT 1 FROM comprobantes_proveedor
                       WHERE numero = %s AND COALESCE(ruc_proveedor, '') = %s AND COALESCE(tipo, 'Factura') = %s
                         AND COALESCE(estado, '') NOT IN ('Anulado', 'Anulada')""", (numero, ruc, tipo)):
            return jsonify({'success': False, 'error': f'El comprobante {numero} de este proveedor ya está registrado'}), 409
        # Vincula la OC por número si no viene el id
        if not data.get('orden_compra_id') and (data.get('orden_compra') or data.get('orden_compra_numero')):
            oc = db_query("SELECT id FROM ordenes_compra WHERE numero_orden = %s",
                          (data.get('orden_compra') or data.get('orden_compra_numero'),))
            if oc:
                data['orden_compra_id'] = oc[0]['id']
        # 20/10/2026: la factura de una OC nueva se registra en Compras ▸ Pagos y facturas, donde se compara con lo
        # recibido; aquí se saltaba esa revisión y quedaba como factura aparte.
        if data.get('orden_compra_id') and db_query("SELECT 1 FROM ordenes_compra WHERE id = %s AND flujo = 'v2'",
                                                    (data['orden_compra_id'],)):
            return jsonify({'success': False, 'error': 'Esta orden es del flujo nuevo: registra su factura en Compras ▸ '
                                                       'Pagos y facturas ("🧾 Registrar factura"), así se revisa si cuadra.'}), 409

        result = guardar_comprobante_proveedor_db(data)
        if result:
            return jsonify({'success': True, 'message': 'Comprobante registrado', 'data': result})
        return jsonify({'success': False, 'error': 'No se pudo guardar'}), 400

    except Exception as e:
        print(f"❌ Error en api_comprobantes_proveedor_guardar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@compras_bp.route('/compras/api/comprobantes-proveedor/<int:id>/toggle', methods=['PUT'])
@login_required
def api_comprobantes_proveedor_toggle(id):
    """Cambia el estado de un comprobante de proveedor"""
    try:
        data = request.get_json()
        nuevo_estado = data.get('estado')
        
        if not nuevo_estado:
            return jsonify({'success': False, 'error': 'Estado requerido'}), 400
        
        estados_validos = ['Pendiente', 'Registrado', 'Pagado', 'Anulado']
        if nuevo_estado not in estados_validos:
            return jsonify({'success': False, 'error': f'Estado inválido'}), 400
        if nuevo_estado == 'Anulado':
            return _anular_comprobante_proveedor(id)
        
        query = """
            UPDATE comprobantes_proveedor 
            SET estado = %s, updated_at = NOW()
            WHERE id = %s
            RETURNING id, estado
        """
        result = db_query(query, (nuevo_estado, id))
        
        if result:
            return jsonify({
                'success': True,
                'message': f'Comprobante actualizado a {nuevo_estado}',
                'data': result[0]
            })
        
        return jsonify({'success': False, 'error': 'Comprobante no encontrado'}), 404
        
    except Exception as e:
        print(f"❌ Error en api_comprobantes_proveedor_toggle: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def _anular_comprobante_proveedor(id):
    """Anula (no borra) un comprobante de proveedor: solo administrador, con motivo y sin pagos vigentes."""
    motivo, error = _exigir_admin_y_motivo()
    if error:
        return error
    with db_tx() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM comprobantes_proveedor WHERE id = %s FOR UPDATE", (id,))
        fila = cur.fetchone()
        if not fila:
            return jsonify({'success': False, 'error': 'Comprobante no encontrado'}), 404
        if (fila.get('estado') or '').upper() in ('ANULADO', 'ANULADA'):
            return jsonify({'success': False, 'error': 'El comprobante ya está anulado'}), 400
        cur.execute("""SELECT COALESCE(SUM(monto), 0) AS p FROM finanzas_pagos WHERE documento_tabla = 'comprobantes_proveedor'
                       AND documento_id = %s AND tipo = 'PAGO' AND estado <> 'Anulado'""", (id,))
        if a_decimal(cur.fetchone()['p']) > 0:
            return jsonify({'success': False, 'error': 'Tiene pagos registrados: primero Finanzas debe anular el pago.'}), 400
        cur.execute("""UPDATE comprobantes_proveedor SET estado = 'Anulado', updated_at = NOW(),
                       observaciones = TRIM(COALESCE(observaciones, '') || ' [ANULADO: ' || %s || ']') WHERE id = %s""",
                    (motivo, id))
        _registrar_anulacion(cur, 'comprobantes_proveedor', id, fila.get('numero'), 'Anulado', motivo, dict(fila))
    return jsonify({'success': True, 'message': 'Comprobante anulado (queda registrado con tu motivo)',
                    'data': {'id': id, 'estado': 'Anulado'}})


@compras_bp.route('/compras/api/comprobantes-proveedor/<int:id>', methods=['DELETE'])
@login_required
def api_comprobantes_proveedor_eliminar(id):
    """La pantalla tenía "Eliminar" sin ruta: ahora anula el comprobante (no se borra, por control)."""
    try:
        return _anular_comprobante_proveedor(id)
    except Exception as e:
        print(f"❌ Error anulando comprobante proveedor: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# API - RECEPCIÓN DE MERCADERÍA
# ============================================================

@compras_bp.route('/compras/api/recepciones/listar', methods=['GET'])
@login_required
def api_recepciones_listar():
    """Lista todas las recepciones de mercadería"""
    try:
        data = obtener_recepciones_db()

        formatted_data = []
        for row in data:
            formatted_data.append({
                'id': row.get('id'),
                'numero': row.get('numero_recepcion') or '',
                'numero_recepcion': row.get('numero_recepcion') or '',
                'fecha': _fecha_iso(row.get('fecha') or row.get('created_at')),
                'creado': _fecha_hora(row.get('created_at') or row.get('fecha')),
                'estado': row.get('estado') or 'Pendiente',
                'orden_compra': row.get('orden_compra_numero') or '',
                'orden': row.get('orden_compra_numero') or '',
                'proveedor': row.get('proveedor_nombre') or '',
                'producto': row.get('producto') or '',
                'cantidad': float(row.get('cantidad') or 0),
                'unidad': row.get('unidad') or 'UND',
                'estado_mercaderia': row.get('estado_mercaderia') or '',
                'observaciones': row.get('observaciones') or ''
            })
        formatted_data = _filtrar_api(formatted_data, ('numero', 'orden', 'proveedor', 'producto'))
        return jsonify({'success': True, 'data': formatted_data})

    except Exception as e:
        print(f"❌ Error en api_recepciones_listar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e), 'data': []}), 200


@compras_bp.route('/compras/api/recepciones/guardar', methods=['POST'])
@login_required
def api_recepciones_guardar():
    """Guarda una recepción de mercadería"""
    try:
        data = request.get_json()
        print(f"📦 Guardando recepción: {data}")

        if not data.get('numero_recepcion'):
            count_data = db_query("SELECT COUNT(*) as total FROM recepciones_mercaderia")
            count = count_data[0]['total'] + 1 if count_data else 1
            data['numero_recepcion'] = f"REC-{datetime.now().strftime('%Y%m%d')}-{str(count).zfill(4)}"

        result = guardar_recepcion_db(data)
        if result:
            # El stock ya no se suma aquí (antes se sumaba buscando el nombre con ILIKE, lo que podía
            # afectar a varios productos y sumar dos veces al pasar de Aprobada a Almacenada).
            # Ahora la recepción aprobada aparece en Inventario ▸ Entradas y salidas para ingresarla
            # indicando la empresa dueña y la sede donde quedó.
            return jsonify({'success': True, 'message': 'Recepción guardada', 'data': result})
        return jsonify({'success': False, 'error': 'No se pudo guardar'}), 200

    except Exception as e:
        print(f"❌ Error en api_recepciones_guardar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 200


@compras_bp.route('/compras/api/recepciones/<int:id>/toggle', methods=['PUT'])
@login_required
def api_recepciones_toggle(id):
    """Cambia el estado de una recepción"""
    try:
        data = request.get_json()
        nuevo_estado = data.get('estado')
        
        if not nuevo_estado:
            return jsonify({'success': False, 'error': 'Estado requerido'}), 400
        
        estados_validos = ['Pendiente', 'En inspección', 'Aprobada', 'Rechazada', 'Almacenada']
        if nuevo_estado not in estados_validos:
            return jsonify({'success': False, 'error': f'Estado inválido'}), 400
        
        query = """
            UPDATE recepciones_mercaderia 
            SET estado = %s, updated_at = NOW()
            WHERE id = %s
            RETURNING id, estado
        """
        result = db_query(query, (nuevo_estado, id))
        
        if result:
            # El stock se ingresa desde Inventario ▸ Entradas y salidas (ver api_recepciones_guardar).
            return jsonify({
                'success': True,
                'message': f'Recepción actualizada a {nuevo_estado}',
                'data': result[0]
            })
        
        return jsonify({'success': False, 'error': 'Recepción no encontrada'}), 404
        
    except Exception as e:
        print(f"❌ Error en api_recepciones_toggle: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# API - EXPORTACIÓN DE DATOS
# ============================================================

@compras_bp.route('/compras/api/exportar/<tipo>', methods=['GET'])
@login_required
def api_exportar(tipo):
    """Exporta datos en formato JSON"""
    try:
        data = []
        filename = f"compras_{tipo}_{datetime.now().strftime('%Y%m%d')}.json"
        
        if tipo == 'solicitud_compra':
            data = obtener_solicitudes_db()
        elif tipo == 'comparativo':
            data = obtener_comparativos_db()
        elif tipo == 'orden_compra':
            data = obtener_ordenes_db()
        elif tipo == 'comprobante_proveedor':
            data = obtener_comprobantes_proveedor_db()
        elif tipo == 'recepcion':
            data = obtener_recepciones_db()
        else:
            return jsonify({'success': False, 'error': 'Tipo no válido'}), 400
        
        from flask import Response
        import json
        
        json_data = json.dumps(data, default=str, indent=2)
        
        return Response(
            json_data,
            mimetype='application/json',
            headers={
                'Content-Disposition': f'attachment; filename={filename}'
            }
        )
        
    except Exception as e:
        print(f"❌ Error en api_exportar: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# API - BUSCAR PROVEEDOR POR RUC / NOMBRE
# ============================================================

@compras_bp.route('/compras/api/proveedores/buscar', methods=['GET'])
@login_required
def api_proveedores_buscar():
    """
    Busca proveedores por RUC exacto, o por razón social/contacto.
    Devuelve TODOS los campos útiles para autocompletar formularios.
    """
    try:
        q = (request.args.get('q') or '').strip()

        if not q or len(q) < 2:
            return jsonify({'success': True, 'data': [], 'source': 'empty'})

        es_ruc = q.isdigit() and len(q) == 11

        select_str = """
            id,
            ruc,
            razon_social,
            razon_comercial,
            codigo_proveedor,
            direccion,
            telefono,
            contacto,
            email,
            condicion_pago,
            tiempo_credito,
            moneda,
            descuento,
            banco,
            numero_cuenta,
            cci,
            tipo_cuenta,
            lugar_recojo,
            ambito,
            estado,
            activo
        """

        # Teléfono y contacto: si el proveedor no los tiene, se toman de su contacto principal (proveedores_contactos)
        select_str = select_str.replace('telefono,', "COALESCE(NULLIF(proveedores.telefono, ''), pcx.telefono) AS telefono,") \
                               .replace('contacto,', "COALESCE(NULLIF(proveedores.contacto, ''), pcx.nombre_contacto) AS contacto,") \
                               .replace('email,', "COALESCE(NULLIF(proveedores.email, ''), pcx.email) AS email,")
        desde_sql = """proveedores LEFT JOIN LATERAL (
                SELECT c.nombre_contacto, c.telefono, c.email FROM proveedores_contactos c
                WHERE c.proveedor_id = proveedores.id AND COALESCE(c.activo, true) = true
                ORDER BY COALESCE(c.principal, false) DESC, c.id LIMIT 1) pcx ON true"""
        if es_ruc:
            query = f"""
                SELECT {select_str}
                FROM {desde_sql}
                WHERE ruc = %s
                LIMIT 5
            """
            params = (q,)
        else:
            pattern = f"%{q}%"
            query = f"""
                SELECT {select_str}
                FROM {desde_sql}
                WHERE ruc ILIKE %s
                   OR razon_social ILIKE %s
                   OR COALESCE(razon_comercial, '') ILIKE %s
                   OR COALESCE(proveedores.contacto, '') ILIKE %s
                ORDER BY razon_social
                LIMIT 20
            """
            params = (pattern, pattern, pattern, pattern)

        try:
            rows = db_query(query, params) or []
        except Exception as e:
            print(f"⚠️ Error consultando proveedores: {e}")
            return _fallback_sunat_compras(q)

        if not rows and es_ruc:
            return _fallback_sunat_compras(q)

        data = []
        for r in rows:
            data.append({
                'id': r.get('id'),
                'ruc': r.get('ruc') or '',
                'razon_social': r.get('razon_social') or '',
                'razon_comercial': r.get('razon_comercial') or '',
                'codigo_proveedor': r.get('codigo_proveedor') or '',
                'direccion': r.get('direccion') or '',
                'telefono': r.get('telefono') or '',
                'contacto': r.get('contacto') or '',
                'email': r.get('email') or '',
                'condicion_pago': r.get('condicion_pago') or '',
                'tiempo_credito': r.get('tiempo_credito') or '',
                'moneda': r.get('moneda') or '',
                'descuento': r.get('descuento') or '',
                'banco': r.get('banco') or '',
                'numero_cuenta': r.get('numero_cuenta') or '',
                'cci': r.get('cci') or '',
                'tipo_cuenta': r.get('tipo_cuenta') or '',
                'lugar_recojo': r.get('lugar_recojo') or '',
                'ambito': r.get('ambito') or '',
                'estado': r.get('estado') or '',
                'activo': bool(r.get('activo')) if r.get('activo') is not None else True
            })

        return jsonify({'success': True, 'data': data, 'source': 'bd'})

    except Exception as e:
        print(f"❌ Error CRÍTICO en api_proveedores_buscar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': True, 'data': [], 'source': 'error', 'warning': str(e)})


def _fallback_sunat_compras(ruc):
    """Fallback: consulta SUNAT y devuelve formato compatible."""
    try:
        if not ruc.isdigit() or len(ruc) != 11:
            return jsonify({'success': True, 'data': [], 'source': 'invalid_ruc'})

        # Mismo servicio que Ventas (routes/consulta_ruc.py): el antiguo sin clave ahora responde 402
        from routes.consulta_ruc import consultar_ruc_externo, ErrorConsultaRuc
        try:
            data_sunat = consultar_ruc_externo(ruc)
        except ErrorConsultaRuc as e:
            return jsonify({'success': True, 'data': [], 'source': 'sunat_error', 'warning': str(e)})

        razon = data_sunat.get('razon_social') or ''
        direccion = data_sunat.get('direccion') or ''

        if razon:
            return jsonify({
                'success': True,
                'source': 'sunat',
                'data': [{
                    'id': None,
                    'ruc': ruc,
                    'razon_social': razon,
                    'razon_comercial': '',
                    'codigo_proveedor': '',
                    'direccion': direccion,
                    'telefono': '',
                    'contacto': '',
                    'email': '',
                    'condicion_pago': '',
                    'tiempo_credito': '',
                    'moneda': 'Soles (S/)',
                    'descuento': '',
                    'banco': '',
                    'numero_cuenta': '',
                    'cci': '',
                    'tipo_cuenta': '',
                    'lugar_recojo': '',
                    'ambito': '',
                    'estado': 'Activo',
                    'activo': True
                }]
            })

        return jsonify({'success': True, 'data': [], 'source': 'sunat_empty'})

    except Exception as e:
        print(f"❌ Error en _fallback_sunat_compras: {e}")
        return jsonify({'success': True, 'data': [], 'source': 'error'})


# ============================================================
# API - BUSCAR ÓRDENES DE COMPRA (autocomplete)
# ============================================================

@compras_bp.route('/compras/api/ordenes/buscar', methods=['GET'])
@login_required
def api_ordenes_buscar():
    """Busca órdenes de compra para autocomplete"""
    try:
        q = request.args.get('q', '').strip()
        
        if not q or len(q) < 2:
            return jsonify({'success': True, 'data': []})
        
        query = """
            SELECT id, numero_orden, contacto_proveedor as proveedor, 
                   email_proveedor as ruc, total, estado
            FROM ordenes_compra
            WHERE numero_orden ILIKE %s
               OR contacto_proveedor ILIKE %s
            ORDER BY id DESC
            LIMIT 20
        """
        search_pattern = f'%{q}%'
        results = db_query(query, (search_pattern, search_pattern))
        
        return jsonify({'success': True, 'data': results})
        
    except Exception as e:
        print(f"❌ Error en api_ordenes_buscar: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# RUTA PARA VISTA PREVIA DE ORDEN DE COMPRA
# ============================================================

@compras_bp.route('/compras/orden/<int:id>/preview', methods=['GET'])
@login_required
def orden_preview(id):
    """Vista previa / impresión de una orden de compra PARA EL PROVEEDOR (sin cliente, PC ni cotización del cliente).
    Antes buscaba la plantilla compras/orden_preview.html, que no existe; ahora usa la misma hoja de la nueva pantalla."""
    try:
        from routes.compras_flujo import orden_imprimir
        if not request.args.get('hoja'):
            from werkzeug.datastructures import ImmutableMultiDict
            request.args = ImmutableMultiDict({'hoja': 'borrador'})
        return orden_imprimir(id)
    except Exception as e:
        print(f"❌ Error en orden_preview: {e}")
        return f"Error: {e}", 500
    try:
        query = """
            SELECT 
                id, numero_orden, fecha_creacion, estado,
                proveedor_id, condicion_pago,
                subtotal, igv, total,
                contacto_proveedor, telefono_proveedor, email_proveedor,
                nota_compra, notas,
                created_at, updated_at
            FROM ordenes_compra
            WHERE id = %s
        """
        result = db_query(query, (id,))
        
        if not result:
            return "Orden de compra no encontrada", 404
        
        orden = result[0]
        
        # Cargar items
        try:
            items_query = """
                SELECT producto, cantidad, precio_unitario, total
                FROM ordenes_compra_items
                WHERE orden_compra_id = %s
            """
            orden['items'] = db_query(items_query, (id,)) or []
        except:
            orden['items'] = []
        
        return render_template('compras/orden_preview.html', orden=orden)
        
    except Exception as e:
        print(f"❌ Error en orden_preview: {e}")
        return f"Error: {e}", 500