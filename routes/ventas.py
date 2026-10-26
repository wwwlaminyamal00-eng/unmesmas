# routes/ventas.py - INICIO CORREGIDO

import sys
import os

# Asegurar que la raíz del proyecto esté en el path de Python
# Esto permite importar módulos desde la carpeta principal
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from functools import wraps
from datetime import datetime
import json
import re

# Importar el generador de PDF desde la raíz del proyecto
from pdf_generator import pdf_generator

# Importar desde database.py
from database import db_query, db_execute, db_tx, get_connection, buscar_cliente_por_ruc
from routes.multiempresa import (filtrar_filas, filtro_sql, empresa_para_crear, empresa_de, marcar_empresa,
                                 empresa_por_id, empresas, datos_empresa_documento, empresa_id_por_ruc,
                                 empresa_por_codigo, marca_pdf)
from routes.moneda import asegurar_moneda, moneda_documento, codigo_moneda, ErrorMoneda
from routes.migo import asegurar_migo, guardar_numero_migo, limpiar_migo
import psycopg2
from psycopg2.extras import RealDictCursor
from routes.numeracion import con_piso, clave_pc, clave_guia, clave_comprobante
from utils import (es_aprobador, calcular_totales, a_decimal, redondear, tasa_igv,
                   totales_consistentes, bloquear_numeracion, normalizar_condicion, dias_de_condicion,
                   mayuscula_inicial)

ventas_bp = Blueprint('ventas', __name__)

# ============================================================
# FUNCIÓN LOGIN REQUIRED
# ============================================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session:
            if request.path.startswith('/ventas/api/'):
                return jsonify({'error': 'Sesión expirada o no autorizado. Inicia sesión.'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def _siguiente_numero(cur, tabla, serie, ancho=8, columna_serie='serie', extra_where='', extra_params=()):
    """Siguiente correlativo numérico de una serie (con bloqueo para evitar duplicados)."""
    bloquear_numeracion(cur, f"{tabla}:{serie}{':' + str(extra_params) if extra_params else ''}")
    cur.execute(f"""
        SELECT COALESCE(MAX(NULLIF(regexp_replace(numero::text, '\\D', '', 'g'), '')::bigint), 0) + 1 AS siguiente
        FROM {tabla} WHERE COALESCE({columna_serie}, '') = COALESCE(%s, '') {extra_where}
    """, (serie,) + tuple(extra_params))
    fila = cur.fetchone()
    siguiente = fila['siguiente'] if isinstance(fila, dict) else fila[0]
    return str(siguiente).zfill(ancho)

# ============================================================
# FLUJO DE ESTADOS DE COTIZACIÓN
# ============================================================
# Borrador -> En revisión / Por validar -> Validado por Hellen -> Generada -> Aceptada por Cliente
ESTADOS_VALIDADOS = ('Validado por Hellen', 'Validada', 'Validado')
ESTADOS_QUE_REQUIEREN_APROBADOR = ESTADOS_VALIDADOS
ESTADOS_BLOQUEADOS = ('Generada', 'Aceptada por Cliente', 'Aceptada', 'Facturada', 'Anulada')
ESTADOS_ACEPTADA = ('Aceptada por Cliente', 'Aceptada')


def _requiere_validacion_previa():
    # Si se pone COTIZACION_REQUIERE_VALIDACION=false, un vendedor puede generar sin validación previa
    return os.environ.get('COTIZACION_REQUIERE_VALIDACION', 'true').lower() != 'false'


def validar_transicion_cotizacion(estado_actual, estado_nuevo):
    """Devuelve None si el cambio de estado es válido, o un mensaje de error."""
    estado_actual = (estado_actual or '').strip()
    estado_nuevo = (estado_nuevo or '').strip()
    if not estado_nuevo or estado_actual == estado_nuevo:
        return None
    if estado_actual in ESTADOS_ACEPTADA or estado_actual == 'Facturada':
        return f'La cotización ya está "{estado_actual}" y no puede cambiar de estado.'
    if estado_actual == 'Anulada':
        if estado_nuevo == 'Borrador' and es_aprobador():
            return None
        return 'La cotización está anulada. Solo un aprobador puede reactivarla como Borrador.'
    if estado_nuevo in ESTADOS_QUE_REQUIEREN_APROBADOR and not es_aprobador():
        return 'Solo un usuario aprobador puede validar cotizaciones.'
    if estado_nuevo == 'Generada' and not es_aprobador():
        # 24/10/2026 (equipo de Erika): el vendedor solo guarda borrador o solicita validación; genera Hellen o un admin
        return 'Solo Hellen o un administrador puede generar la cotización. Usa "Solicitar validación".'
    if estado_nuevo in ESTADOS_ACEPTADA and estado_actual not in ('Generada', 'Enviada'):
        return 'Solo una cotización generada puede marcarse como aceptada por el cliente.'
    if estado_actual == 'Generada' and estado_nuevo in ('Borrador', 'En revisión', 'Por validar') and not es_aprobador():
        return 'Una cotización generada no puede volver a borrador (duplícala para modificarla).'
    return None

# ============================================================
# FUNCIONES DE AYUDA PARA COTIZACIONES - VERSIÓN CORREGIDA
# ============================================================

def crear_tabla_cotizaciones_eliminadas_si_no_existe():
    """Crea la tabla de respaldo de cotizaciones eliminadas si no existe"""
    try:
        query = """
            CREATE TABLE IF NOT EXISTS cotizaciones_eliminadas (
                id SERIAL PRIMARY KEY,
                cotizacion_id_original INTEGER,
                numero_cotizacion VARCHAR(50),
                codigo_cotizacion VARCHAR(50),
                cliente_id INTEGER,
                cliente_razon_social VARCHAR(255),
                cliente_ruc VARCHAR(20),
                fecha_creacion TIMESTAMP,
                estado_anterior VARCHAR(50),
                subtotal NUMERIC(12,2),
                igv NUMERIC(12,2),
                total NUMERIC(12,2),
                condicion_pago VARCHAR(100),
                tiempo_entrega VARCHAR(100),
                direccion_entrega TEXT,
                vendedor VARCHAR(150),
                contacto_cliente VARCHAR(150),
                telefono_cliente VARCHAR(50),
                email_cliente VARCHAR(150),
                nota_cotizacion TEXT,
                requerimiento TEXT,
                productos_json JSONB,
                datos_completos_json JSONB,
                motivo_eliminacion TEXT NOT NULL,
                eliminado_por INTEGER,
                eliminado_en TIMESTAMP DEFAULT NOW()
            )
        """
        with db_tx() as conn:
            cur = conn.cursor()
            # Evita el error de creación simultánea cuando varias pantallas consultan a la vez
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('cotizaciones_eliminadas_ddl'))")
            cur.execute(query)
    except Exception as e:
        print(f"❌ Error creando tabla cotizaciones_eliminadas: {e}")
        raise

def _tiempos(row, creado='created_at'):
    """Fecha y hora de creación y de la última modificación (pedido de Erika 19/10/2026), en hora de Lima."""
    def txt(v):
        if isinstance(v, datetime):
            return v.strftime('%Y-%m-%d %H:%M:%S')
        return v
    return {'creado_en': txt(row.get(creado) or row.get('created_at') or row.get('fecha_creacion')),
            'modificado_en': txt(row.get('updated_at'))}


def obtener_cotizaciones_db():
    """Obtiene todas las cotizaciones con datos del cliente"""
    try:
        query = """
            SELECT 
                c.id, 
                c.numero_cotizacion, 
                c.cliente_id, 
                c.fecha_creacion, c.updated_at,
                c.estado,
                c.subtotal, 
                c.igv, 
                c.total, 
                c.usuario_id, 
                c.notas,
                c.forma_pago, 
                c.tiempo_entrega, 
                c.almacen, 
                c.validez_oferta,
                c.codigo_cotizacion, 
                c.correlativo, 
                c.condicion_pago,
                c.direccion_entrega,
                c.requerimiento, 
                c.nota_cotizacion,
                c.descuento_porcentaje, 
                c.descuento_monto, 
                c.descuento_tipo,
                c.contacto_cliente, 
                c.telefono_cliente, 
                c.email_cliente,
                c.seguimiento,
                c.motivo,
                c.transporte,
                c.parihuela,
                c.nota_interna,
                c.vendedor,
                cl.id as cliente_id,
                cl.razon_social as cliente_razon_social,
                cl.numero_documento as cliente_ruc,
                cl.nombre_comercial as cliente_nombre_comercial,
                cl.direccion_fiscal as cliente_direccion,
                cl.telefono_contacto as cliente_telefono,
                cl.nombre_contacto as cliente_contacto,
                cl.email_contacto as cliente_email,
                cl.codigo_cliente as cod_cliente,
                (
                    SELECT p.descripcion
                    FROM cotizacion_detalle d
                    LEFT JOIN productos p ON p.id = d.producto_id
                    WHERE d.cotizacion_id = c.id
                    ORDER BY d.id ASC
                    LIMIT 1
                ) AS primer_producto_descripcion
            FROM cotizaciones c
            LEFT JOIN clientes cl ON cl.id = c.cliente_id::integer
            WHERE c.estado != 'Anulada'
            ORDER BY c.id DESC
        """
        results = db_query(query)
        print(f"✅ Cotizaciones encontradas: {len(results)}")
        return results
    except Exception as e:
        print(f"❌ Error en obtener_cotizaciones_db: {e}")
        import traceback
        traceback.print_exc()
        return []

def obtener_cotizacion_por_id_db(cotizacion_id):
    """Obtiene una cotización por su ID"""
    try:
        query = """
            SELECT 
                id, numero_cotizacion, cliente_id, fecha_creacion, estado,
                subtotal, igv, total, usuario_id, notas,
                forma_pago, tiempo_entrega, almacen, validez_oferta,
                codigo_cotizacion, correlativo, condicion_pago,
                direccion_entrega, requerimiento, nota_cotizacion,
                descuento_porcentaje, descuento_monto, descuento_tipo,
                contacto_cliente, telefono_cliente, email_cliente
            FROM cotizaciones
            WHERE id = %s
        """
        result = db_query(query, (cotizacion_id,))
        return result[0] if result else None
    except Exception as e:
        print(f"❌ Error en obtener_cotizacion_por_id_db: {e}")
        return None


def guardar_cotizacion_db(data):
    try:
        query = """
            INSERT INTO cotizaciones (
                numero_cotizacion, cliente_id, fecha_creacion, estado,
                subtotal, igv, total, usuario_id, notas,
                forma_pago, tiempo_entrega, almacen, validez_oferta,
                codigo_cotizacion, correlativo, condicion_pago,
                direccion_entrega, requerimiento, nota_cotizacion,
                descuento_porcentaje, descuento_monto, descuento_tipo,
                contacto_cliente, telefono_cliente, email_cliente,
                seguimiento, motivo, transporte, parihuela, nota_interna,
                vendedor
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            )
            RETURNING id, numero_cotizacion
        """
        params = (
            data.get('numero_cotizacion'),
            data.get('cliente_id'),
            data.get('fecha_creacion') or datetime.now().isoformat(),
            data.get('estado', 'Borrador'),
            float(data.get('subtotal', 0)),
            float(data.get('igv', 0)),
            float(data.get('total', 0)),
            data.get('usuario_id'),
            data.get('notas', ''),
            data.get('forma_pago'),
            data.get('tiempo_entrega'),
            data.get('almacen'),
            data.get('validez_oferta'),
            data.get('codigo_cotizacion'),
            data.get('correlativo'),
            data.get('condicion_pago'),
            data.get('direccion_entrega'),
            data.get('requerimiento'),  # ← REQUERIMIENTO
            data.get('nota_cotizacion', ''),
            float(data.get('descuento_porcentaje', 0)),
            float(data.get('descuento_monto', 0)),
            data.get('descuento_tipo', 'porcentaje'),
            data.get('contacto_cliente'),
            data.get('telefono_cliente'),
            data.get('email_cliente'),
            data.get('seguimiento', 'Asesor'),
            data.get('motivo', 'Proyecto nuevo'),
            data.get('transporte', 'Seleccione'),
            data.get('parihuela', 'Seleccione'),
            data.get('nota_interna', ''),
            data.get('vendedor', 'Helen Blas Príncipe')
        )
        
        result = db_query(query, params)
        return result[0] if result else None
    except Exception as e:
        print(f"❌ Error en guardar_cotizacion_db: {e}")
        raise


def actualizar_cotizacion_db(cotizacion_id, data):
    """Actualiza una cotización existente"""
    try:
        query = """
            UPDATE cotizaciones SET
                cliente_id = %s,
                estado = %s,
                subtotal = %s,
                igv = %s,
                total = %s,
                usuario_id = %s,
                notas = %s,
                forma_pago = %s,
                tiempo_entrega = %s,
                almacen = %s,
                validez_oferta = %s,
                condicion_pago = %s,
                direccion_entrega = %s,
                requerimiento = %s,
                nota_cotizacion = %s,
                descuento_porcentaje = %s,
                descuento_monto = %s,
                descuento_tipo = %s,
                contacto_cliente = %s,
                telefono_cliente = %s,
                email_cliente = %s,
                -- 🔽 NUEVOS CAMPOS
                seguimiento = %s,
                motivo = %s,
                transporte = %s,
                parihuela = %s,
                nota_interna = %s,
                vendedor = %s,
                updated_at = NOW()
            WHERE id = %s
            RETURNING id, numero_cotizacion
        """
        params = (
            data.get('cliente_id'),
            data.get('estado', 'Borrador'),
            float(data.get('subtotal', 0)),
            float(data.get('igv', 0)),
            float(data.get('total', 0)),
            data.get('usuario_id'),
            data.get('notas', ''),
            data.get('forma_pago'),
            data.get('tiempo_entrega'),
            data.get('almacen'),
            data.get('validez_oferta'),
            data.get('condicion_pago'),
            data.get('direccion_entrega'),
            data.get('requerimiento'),
            data.get('nota_cotizacion', ''),
            float(data.get('descuento_porcentaje', 0)),
            float(data.get('descuento_monto', 0)),
            data.get('descuento_tipo', 'porcentaje'),
            data.get('contacto_cliente'),
            data.get('telefono_cliente'),
            data.get('email_cliente'),
            # 🔽 NUEVOS CAMPOS
            data.get('seguimiento', 'Asesor'),
            data.get('motivo', 'Proyecto nuevo'),
            data.get('transporte', 'Seleccione'),
            data.get('parihuela', 'Seleccione'),
            data.get('nota_interna', ''),
            data.get('vendedor', 'Helen Blas Príncipe'),
            cotizacion_id
        )
        result = db_query(query, params)
        return result[0] if result else None
    except Exception as e:
        print(f"❌ Error en actualizar_cotizacion_db: {e}")
        raise


def actualizar_estado_cotizacion_db(cotizacion_id, nuevo_estado):
    """Actualiza el estado de una cotización"""
    try:
        query = """
            UPDATE cotizaciones 
            SET estado = %s
            WHERE id = %s
            RETURNING id, estado
        """
        result = db_query(query, (nuevo_estado, cotizacion_id))
        return result[0] if result else None
    except Exception as e:
        print(f"❌ Error en actualizar_estado_cotizacion_db: {e}")
        raise


# ============================================================
# FUNCIONES DE AYUDA PARA GUÍAS
# ============================================================

def obtener_guias_db():
    """Obtiene todas las guías"""
    try:
        query = """
            SELECT 
                id, serie, numero, fecha_emision, fecha_traslado,
                ruc_remitente, remitente_nombre, remitente_direccion,
                remitente_ubigeo, ruc_destinatario, destinatario_nombre,
                destinatario_direccion, destinatario_ubigeo,
                modalidad_transporte, placa_vehiculo, conductor_dni,
                conductor_nombre, licencia_conductor, transportista_ruc,
                transportista_nombre, motivo_traslado, documento_asociado,
                orden_compra_cliente, factura,
                peso_total, items_json, observaciones, estado_sunat,
                cdr_response, sunat_response, creado_por, created_at, updated_at,
                COALESCE(NULLIF(factura, ''),
                         (SELECT c.serie || '-' || c.numero FROM comprobantes c
                          WHERE c.guia_vinculada = guias_remision.serie || '-' || guias_remision.numero
                            AND COALESCE(UPPER(c.estado_sunat), '') NOT IN ('ANULADO', 'ANULADA')
                          ORDER BY c.id DESC LIMIT 1)) AS factura_vinculada,
                -- N° PV (19/10/2026): la PV de la misma cotización
                (SELECT string_agg(DISTINCT p.numero, ', ') FROM pedido_compra_pc p
                  WHERE p.cotizacion_numero = guias_remision.documento_asociado
                    AND NULLIF(p.numero, '') IS NOT NULL
                    AND COALESCE(UPPER(p.estado), '') NOT IN ('ANULADO', 'ANULADA', 'RECHAZADO', 'RECHAZADA')) AS pc_numero
            FROM guias_remision
            ORDER BY id DESC
        """
        return db_query(query)
    except Exception as e:
        print(f"❌ Error en obtener_guias_db: {e}")
        return []

def obtener_guia_por_id_db(guia_id):
    """Obtiene una guía por su ID"""
    try:
        query = """
            SELECT 
                id, serie, numero, fecha_emision, fecha_traslado,
                ruc_remitente, remitente_nombre, remitente_direccion,
                remitente_ubigeo, ruc_destinatario, destinatario_nombre,
                destinatario_direccion, destinatario_ubigeo,
                modalidad_transporte, placa_vehiculo, conductor_dni,
                conductor_nombre, licencia_conductor, transportista_ruc,
                transportista_nombre, motivo_traslado, documento_asociado,
                orden_compra_cliente, factura,
                peso_total, items_json, observaciones, estado_sunat,
                cdr_response, sunat_response, creado_por
            FROM guias_remision
            WHERE id = %s
        """
        result = db_query(query, (guia_id,))
        return result[0] if result else None
    except Exception as e:
        print(f"❌ Error en obtener_guia_por_id_db: {e}")
        return None

def guardar_guia_db(data):
    """Guarda una nueva guía con fecha y hora correcta - IGUAL QUE COMPROBANTES"""
    try:
        from datetime import datetime
        
        # ============================================================
        # 🔽 USAR EXACTAMENTE EL MISMO CÓDIGO QUE EN COMPROBANTES
        # ============================================================
        fecha_emision = data.get('fecha_emision')
        if not fecha_emision:
            fecha_emision = datetime.now().isoformat()
        else:
            # Si la fecha NO tiene hora (solo YYYY-MM-DD), usar ahora
            if isinstance(fecha_emision, str) and len(fecha_emision) == 10 and '-' in fecha_emision:
                fecha_emision = datetime.now().isoformat()
        
        fecha_traslado = data.get('fecha_traslado') or datetime.now().date().isoformat()
        
        print(f"📅 Fecha emisión guardando: {fecha_emision}")
        print(f"📅 Fecha traslado guardando: {fecha_traslado}")
        
        query = """
            INSERT INTO guias_remision (
                serie, numero, fecha_emision, fecha_traslado,
                ruc_remitente, remitente_nombre, remitente_direccion,
                remitente_ubigeo, ruc_destinatario, destinatario_nombre,
                destinatario_direccion, destinatario_ubigeo,
                modalidad_transporte, placa_vehiculo, conductor_dni,
                conductor_nombre, licencia_conductor, transportista_ruc,
                transportista_nombre, motivo_traslado, documento_asociado,
                orden_compra_cliente, factura,
                peso_total, items_json, observaciones, estado_sunat,
                creado_por
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,%s,%s
            )
            RETURNING id, numero
        """
        params = (
            data.get('serie', 'T001'),
            data.get('numero'),
            fecha_emision,  # ← IGUAL QUE EN COMPROBANTES
            fecha_traslado,
            data.get('ruc_remitente'),
            data.get('remitente_nombre'),
            data.get('remitente_direccion'),
            data.get('remitente_ubigeo'),
            data.get('ruc_destinatario'),
            data.get('destinatario_nombre'),
            data.get('destinatario_direccion'),
            data.get('destinatario_ubigeo'),
            data.get('modalidad_transporte', 'PRIVADO'),
            data.get('placa_vehiculo'),
            data.get('conductor_dni'),
            data.get('conductor_nombre'),
            data.get('licencia_conductor'),
            data.get('transportista_ruc'),
            data.get('transportista_nombre'),
            data.get('motivo_traslado', 'VENTA'),
            data.get('documento_asociado'),
            data.get('orden_compra_cliente'),
            data.get('factura'),
            float(data.get('peso_total', 0)),
            data.get('items_json'),
            data.get('observaciones'),
            data.get('estado_sunat', 'BORRADOR'),
            data.get('creado_por')
        )
        result = db_query(query, params)
        return result[0] if result else None
    except Exception as e:
        print(f"❌ Error en guardar_guia_db: {e}")
        raise


def actualizar_guia_db(guia_id, data):
    """Actualiza una guía existente"""
    try:
        query = """
            UPDATE guias_remision SET
                fecha_traslado = %s,
                ruc_destinatario = %s,
                destinatario_nombre = %s,
                destinatario_direccion = %s,
                destinatario_ubigeo = %s,
                placa_vehiculo = %s,
                conductor_dni = %s,
                conductor_nombre = %s,
                licencia_conductor = %s,
                transportista_ruc = %s,
                transportista_nombre = %s,
                motivo_traslado = %s,
                documento_asociado = %s,
                orden_compra_cliente = %s,
                factura = %s,
                peso_total = %s,
                items_json = %s,
                observaciones = %s,
                estado_sunat = %s,
                updated_at = NOW()
            WHERE id = %s
            RETURNING id, numero
        """
        params = (
            data.get('fecha_traslado'),
            data.get('ruc_destinatario'),
            data.get('destinatario_nombre'),
            data.get('destinatario_direccion'),
            data.get('destinatario_ubigeo'),
            data.get('placa_vehiculo'),
            data.get('conductor_dni'),
            data.get('conductor_nombre'),
            data.get('licencia_conductor'),
            data.get('transportista_ruc'),
            data.get('transportista_nombre'),
            data.get('motivo_traslado', 'VENTA'),
            data.get('documento_asociado'),
            data.get('orden_compra_cliente'),
            data.get('factura'),
            float(data.get('peso_total', 0)),
            data.get('items_json'),
            data.get('observaciones'),
            data.get('estado_sunat', 'BORRADOR'),
            guia_id
        )
        result = db_query(query, params)
        return result[0] if result else None
    except Exception as e:
        print(f"❌ Error en actualizar_guia_db: {e}")
        raise

# ============================================================
# FUNCIONES DE AYUDA PARA COMPROBANTES
# ============================================================
def obtener_comprobantes_db():
    """Obtiene todos los comprobantes con los campos de retención y orden de compra"""
    try:
        query = """
            SELECT 
                id, tipo_comprobante, serie, numero, fecha_emision,
                moneda, cliente_tipo_doc, cliente_numero_doc,
                cliente_nombre, cliente_direccion, cliente_email,
                cliente_telefono, subtotal, igv, total,
                items_json, observaciones, estado_sunat, 
                documento_asociado, condicion_pago,
                guia_vinculada, pc_vinculado,
                -- 🔽 NUEVO CAMPO: ORDEN DE COMPRA
                orden_compra_cliente,
                -- 🔽 NUEVOS CAMPOS DE RETENCIÓN
                es_credito, estado_credito, fecha_aprobacion,
                fecha_vencimiento, dias_credito, monto_retenido,
                obs_retencion,
                sunat_response, cdr_response, creado_por,
                created_at, updated_at,
                -- Monto a pagar y N° MIGO en la lista (Erika 26/10/2026)
                to_jsonb(comprobantes) ->> 'tiene_retencion' AS tiene_retencion,
                to_jsonb(comprobantes) ->> 'porcentaje_retencion' AS porcentaje_retencion,
                to_jsonb(comprobantes) ->> 'monto_a_pagar' AS monto_a_pagar,
                to_jsonb(comprobantes) ->> 'numero_migo' AS numero_migo,
                (SELECT MAX(a.id) FROM comprobante_archivos a
                  WHERE a.comprobante_id = comprobantes.id AND a.tipo = 'XML') AS xml_id,
                -- N° cotización: la guardada; si falta, la del PV vinculado o la de la guía (26/10/2026)
                COALESCE(NULLIF(documento_asociado, ''),
                         (SELECT p.cotizacion_numero FROM pedido_compra_pc p
                           WHERE p.numero = comprobantes.pc_vinculado AND NULLIF(p.cotizacion_numero, '') IS NOT NULL
                           ORDER BY p.id DESC LIMIT 1),
                         (SELECT g.documento_asociado FROM guias_remision g
                           WHERE (g.serie || '-' || g.numero) = comprobantes.guia_vinculada
                             AND g.documento_asociado LIKE 'COT%%' ORDER BY g.id DESC LIMIT 1)) AS cotizacion_numero,
                -- N° PV y N° Guía (19/10/2026): lo guardado en la factura; si está vacío, por la misma cotización
                COALESCE(NULLIF(pc_vinculado, ''),
                         (SELECT string_agg(DISTINCT p.numero, ', ') FROM pedido_compra_pc p
                           WHERE p.cotizacion_numero = comprobantes.documento_asociado
                             AND NULLIF(p.numero, '') IS NOT NULL
                             AND COALESCE(UPPER(p.estado), '') NOT IN ('ANULADO', 'ANULADA', 'RECHAZADO', 'RECHAZADA'))) AS pc_numero,
                COALESCE(NULLIF(guia_vinculada, ''),
                         (SELECT g.serie || '-' || g.numero FROM guias_remision g
                           WHERE NULLIF(g.factura, '') IS NOT NULL
                             AND g.factura IN (comprobantes.serie || '-' || comprobantes.numero,
                                               comprobantes.serie || '-' || LPAD(comprobantes.numero::text, 8, '0'))
                           ORDER BY g.id DESC LIMIT 1),
                         (SELECT MIN(g.serie || '-' || g.numero) FROM guias_remision g
                           WHERE g.documento_asociado = comprobantes.documento_asociado
                             AND COALESCE(UPPER(g.estado_sunat), '') NOT IN ('ANULADO', 'ANULADA')
                           HAVING COUNT(*) = 1)) AS guia_numero
            FROM comprobantes
            ORDER BY id DESC
        """
        return db_query(query)
    except Exception as e:
        print(f"❌ Error en obtener_comprobantes_db: {e}")
        return []

def guardar_comprobante_db(data):
    """Guarda un nuevo comprobante con fecha y hora correcta, incluyendo orden de compra"""
    try:
        from datetime import datetime
        
        # ✅ OBTENER FECHA Y HORA COMPLETA (mantiene la hora del frontend)
        fecha_emision = data.get('fecha_emision')
        if not fecha_emision:
            fecha_emision = datetime.now().isoformat()
        
        print(f"📅 Fecha emisión guardando: {fecha_emision}")
        
        query = """
            INSERT INTO comprobantes (
                tipo_comprobante, serie, numero, fecha_emision,
                moneda, cliente_tipo_doc, cliente_numero_doc,
                cliente_nombre, cliente_direccion, cliente_email,
                cliente_telefono, subtotal, igv, total,
                items_json, observaciones, estado_sunat,
                condicion_pago, documento_asociado, guia_vinculada,
                pc_vinculado, creado_por,
                -- 🔽 NUEVO CAMPO: ORDEN DE COMPRA MANUAL
                orden_compra_cliente,
                -- 🔽 CAMPOS DE RETENCIÓN
                tiene_retencion, es_credito, estado_credito,
                fecha_aprobacion, fecha_vencimiento, dias_credito,
                porcentaje_retencion, monto_retenido, monto_a_pagar,
                obs_retencion
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s,
                %s, -- orden_compra_cliente
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING id, serie, numero
        """
        
        params = (
            data.get('tipo_comprobante', 'FACTURA'),
            str(data.get('serie') or 'E001').strip().upper(),
            data.get('numero'),
            fecha_emision,
            data.get('moneda', 'PEN'),
            data.get('cliente_tipo_doc', 'RUC'),
            data.get('cliente_numero_doc'),
            data.get('cliente_nombre'),
            data.get('cliente_direccion'),
            data.get('cliente_email'),
            data.get('cliente_telefono'),
            float(data.get('subtotal', 0)),
            float(data.get('igv', 0)),
            float(data.get('total', 0)),
            data.get('items_json'),
            data.get('observaciones'),
            data.get('estado_sunat', 'BORRADOR'),
            data.get('condicion_pago', 'Contado'),
            data.get('documento_asociado'),
            data.get('guia_vinculada'),
            data.get('pc_vinculado'),
            data.get('creado_por'),
            # 🔽 ORDEN DE COMPRA MANUAL
            data.get('orden_compra_cliente', '') or '',
            # 🔽 CAMPOS DE RETENCIÓN
            data.get('tiene_retencion', False),
            data.get('es_credito', False),
            data.get('estado_credito'),
            data.get('fecha_aprobacion'),
            data.get('fecha_vencimiento'),
            data.get('dias_credito'),
            data.get('porcentaje_retencion', 3.00),
            data.get('monto_retenido', 0),
            data.get('monto_a_pagar', 0),
            data.get('obs_retencion')
        )
        
        result = db_query(query, params)
        return result[0] if result else None
    except Exception as e:
        print(f"❌ Error en guardar_comprobante_db: {e}")
        raise


def actualizar_estado_comprobante_db(comp_id, nuevo_estado):
    """Actualiza el estado de un comprobante. Si se anula, sus cobros en caja se anulan en la misma operación."""
    try:
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                UPDATE comprobantes 
                SET estado_sunat = %s, updated_at = NOW()
                WHERE id = %s
                RETURNING id, estado_sunat
            """, (nuevo_estado, comp_id))
            fila = cur.fetchone()
            if fila and (nuevo_estado or '').upper() in ('ANULADO', 'ANULADA'):
                from routes.stock_automatico import anular_cobros_comprobante
                fila['cobros_anulados'] = anular_cobros_comprobante(cur, comp_id, 'Anulación automática: el comprobante fue anulado')
        return dict(fila) if fila else None
    except Exception as e:
        print(f"❌ Error en actualizar_estado_comprobante_db: {e}")
        raise


# ============================================================
# FUNCIONES DE AYUDA PARA NOTAS DE CRÉDITO
# ============================================================

def obtener_notas_credito_db():
    """Obtiene todas las notas de crédito"""
    try:
        query = """
            SELECT 
                id, serie, numero, fecha_emision, fecha_vencimiento,
                cliente_tipo_doc, cliente_numero_doc, cliente_nombre,
                cliente_direccion, cliente_email, cliente_telefono,
                comprobante_asociado, motivo, monto, observaciones,
                estado, creado_por, created_at, updated_at
            FROM notas_credito
            ORDER BY id DESC
        """
        return db_query(query)
    except Exception as e:
        print(f"❌ Error en obtener_notas_credito_db: {e}")
        return []

def guardar_nota_credito_db(data):
    """Guarda una nueva nota de crédito"""
    try:
        query = """
            INSERT INTO notas_credito (
                serie, numero, fecha_emision, fecha_vencimiento,
                cliente_tipo_doc, cliente_numero_doc, cliente_nombre,
                cliente_direccion, cliente_email, cliente_telefono,
                comprobante_asociado, motivo, monto, observaciones,
                estado, creado_por
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            )
            RETURNING id, serie, numero
        """
        params = (
            data.get('serie', 'FC01'),
            data.get('numero'),
            data.get('fecha_emision') or datetime.now().date().isoformat(),
            data.get('fecha_vencimiento'),
            data.get('cliente_tipo_doc', 'RUC'),
            data.get('cliente_numero_doc'),
            data.get('cliente_nombre'),
            data.get('cliente_direccion'),
            data.get('cliente_email'),
            data.get('cliente_telefono'),
            data.get('comprobante_asociado'),
            data.get('motivo'),
            float(data.get('monto', 0)),
            data.get('observaciones'),
            data.get('estado', 'Borrador'),
            data.get('creado_por')
        )
        result = db_query(query, params)
        return result[0] if result else None
    except Exception as e:
        print(f"❌ Error en guardar_nota_credito_db: {e}")
        raise
def obtener_pc_db():
    """Obtiene todos los pedidos de venta con manejo correcto de items"""
    try:
        query = """
            SELECT 
                id, numero, fecha, estado, cliente, ruc, monto,
                cotizacion_id, cotizacion_numero, correo_origen,
                fecha_recepcion, fecha_despacho, archivo_oc,
                observaciones, valida_precios, valida_cantidades,
                valida_stock, valida_entrega, valida_montos,
                valida_transporte, valida_margen, valida_vigencia,
                responsable, lugar_entrega, condicion_atencion,
                medio, entrega, req_compra, guia, factura,
                condicion_pago, vendedor,
                created_at, updated_at,
                items_json,
                to_jsonb(pedido_compra_pc) -> 'valida_productos' AS valida_productos,
                to_jsonb(pedido_compra_pc) ->> 'oc_cliente' AS oc_cliente,
                (SELECT d.estado FROM despachos d WHERE d.pc_id = pedido_compra_pc.id
                 ORDER BY d.id DESC LIMIT 1) AS despacho_estado
            FROM pedido_compra_pc
            ORDER BY id DESC
        """
        results = db_query(query)
        
        for row in results:
            # ============================================================
            # 🔽 CONVERTIR FECHAS A STRING SIN ZONA HORARIA
            # ============================================================
            campos_fecha = ['fecha', 'fecha_recepcion', 'fecha_despacho', 'created_at', 'updated_at']
            for campo in campos_fecha:
                if row.get(campo):
                    valor = row[campo]
                    if isinstance(valor, datetime):
                        row[campo] = valor.strftime('%Y-%m-%d %H:%M:%S')
            
            # ============================================================
            # 🔽 PROCESAR ITEMS_JSON CORRECTAMENTE
            # ============================================================
            items_json_raw = row.get('items_json')
            items = []
            
            if items_json_raw:
                try:
                    if isinstance(items_json_raw, str):
                        # Es string, parsear JSON
                        parsed = json.loads(items_json_raw)
                        if isinstance(parsed, list):
                            items = parsed
                        elif isinstance(parsed, dict) and 'items' in parsed:
                            items = parsed['items']
                        else:
                            items = parsed if isinstance(parsed, list) else []
                    elif isinstance(items_json_raw, list):
                        # Ya es una lista
                        items = items_json_raw
                    elif isinstance(items_json_raw, dict):
                        # Es un diccionario, buscar la lista de items
                        if 'items' in items_json_raw:
                            items = items_json_raw['items']
                        else:
                            items = list(items_json_raw.values()) if items_json_raw else []
                    else:
                        items = []
                except Exception as e:
                    print(f"⚠️ Error parseando items_json para PV {row.get('id')}: {e}")
                    items = []
            else:
                # Si items_json es None o está vacío
                print(f"⚠️ PV {row.get('id')} no tiene items_json")
            
            # ============================================================
            # 🔽 INTENTAR OBTENER PRODUCTOS DE LA COTIZACIÓN ASOCIADA
            # ============================================================
            cotizacion_id = row.get('cotizacion_id')
            if not items and cotizacion_id:
                try:
                    query_cot_items = """
                        SELECT 
                            d.producto_id, d.cantidad, d.precio_venta_unitario,
                            p.codigo, p.descripcion, p.marca, p.modelo, p.unidad,
                            p.stock
                        FROM cotizacion_detalle d
                        LEFT JOIN productos p ON p.id = d.producto_id
                        WHERE d.cotizacion_id = %s
                    """
                    cot_items = db_query(query_cot_items, (cotizacion_id,))
                    
                    if cot_items:
                        for item in cot_items:
                            items.append({
                                'codigo': item.get('codigo', ''),
                                'producto': item.get('descripcion', ''),
                                'marca': item.get('marca', ''),
                                'modelo': item.get('modelo', ''),
                                'cantidad_cotizada': float(item.get('cantidad', 0)),
                                'cantidad_pc': float(item.get('cantidad', 1)),
                                'precio_cotizado': float(item.get('precio_venta_unitario', 0)),
                                'precio_pc': float(item.get('precio_venta_unitario', 0)),
                                'stock': float(item.get('stock', 0))
                            })
                        print(f"✅ Items cargados desde cotización {cotizacion_id} para PV {row.get('id')}")
                except Exception as e:
                    print(f"⚠️ Error obteniendo items de cotización: {e}")
            
            # ============================================================
            # 🔽 SI AÚN NO HAY ITEMS, CREAR UNO POR DEFECTO PARA VALIDACIÓN
            # ============================================================
            if not items:
                # Crear un item genérico para que la validación no falle
                items = [{
                    'codigo': 'GEN-001',
                    'producto': 'Producto genérico (sin items)',
                    'marca': '',
                    'modelo': '',
                    'cantidad_cotizada': 1,
                    'cantidad_pc': 1,
                    'precio_cotizado': float(row.get('monto') or 0) if row.get('monto') else 0,
                    'precio_pc': float(row.get('monto') or 0) if row.get('monto') else 0,
                    'stock': 0
                }]
                print(f"⚠️ PV {row.get('id')} sin items, usando item genérico")
            
            row['items'] = items
            # Limpiar el campo original para evitar duplicados
            row['items_json'] = None
            
            # Campos por defecto
            if not row.get('medio') and row.get('correo_origen'):
                row['medio'] = 'Correo'
            elif not row.get('medio'):
                row['medio'] = 'No especificado'
            
            if not row.get('entrega') and row.get('lugar_entrega'):
                row['entrega'] = row['lugar_entrega']
            
            if not row.get('condicion_pago') and row.get('condicion_atencion'):
                row['condicion_pago'] = row['condicion_atencion']
            row['condicion_pago'] = normalizar_condicion(row.get('condicion_pago')) or row.get('condicion_pago')
            
            if not row.get('req_compra'):
                if row.get('estado') == 'PC observado':
                    row['req_compra'] = 'Bloqueado'
                elif row.get('estado') in ['Listo para despacho', 'PC atendido']:
                    row['req_compra'] = 'No'
                else:
                    row['req_compra'] = 'Sí'
        
        print(f"✅ {len(results)} PVs cargados correctamente")
        return results
        
    except Exception as e:
        print(f"❌ Error en obtener_pc_db: {e}")
        import traceback
        traceback.print_exc()
        return []

def guardar_pc_db(data):
    """Guarda o actualiza un pedido de venta"""
    try:
        print("📝 Guardando PV en BD...")
        
        from datetime import datetime
        
        # ============================================================
        # 🔽 PROCESAR FECHA CORRECTAMENTE - SIN CONVERSIONES
        # ============================================================
        fecha = data.get('fecha')
        
        # Si la fecha viene como objeto datetime, convertir a string
        if isinstance(fecha, datetime):
            fecha = fecha.strftime('%Y-%m-%d %H:%M:%S')
            print(f"📅 Fecha era datetime, convertida a string: {fecha}")
        
        # Si la fecha es un string, usarla tal cual
        if isinstance(fecha, str):
            # Si tiene 'T', reemplazar por espacio (formato ISO)
            if 'T' in fecha:
                fecha = fecha.replace('T', ' ')
                # Si termina con Z o tiene zona horaria, quitarlo
                if 'Z' in fecha:
                    fecha = fecha.replace('Z', '')
                if '+' in fecha:
                    fecha = fecha.split('+')[0]
                if '-' in fecha and len(fecha.split('-')) > 3:
                    # Si tiene zona horaria con + o -
                    partes = fecha.split('+')
                    if len(partes) > 1:
                        fecha = partes[0]
            print(f"📅 Fecha recibida como string (sin modificar): {fecha}")
        
        # Si no hay fecha, usar ahora
        if not fecha:
            ahora = datetime.now()
            fecha = ahora.strftime('%Y-%m-%d %H:%M:%S')
            print(f"📅 Fecha generada automáticamente: {fecha}")
        
        print(f"📅 FECHA FINAL A GUARDAR: {fecha}")
        
        items_json = json.dumps(data.get('items', []))
        
        # ============================================================
        # VALIDACIONES
        # ============================================================
        valida_precios = data.get('valida_precios', False)
        valida_cantidades = data.get('valida_cantidades', False)
        valida_stock = data.get('valida_stock', False)
        valida_entrega = data.get('valida_entrega', False)
        valida_montos = data.get('valida_montos', False)
        # Transporte ya no es parte de la validación comercial del PV (pedido de Erika 20/10/2026)
        valida_transporte = data.get('valida_transporte', True)
        # La pantalla no tiene interruptor de margen: si no se manda, no debe dejar el PV siempre "observado"
        valida_margen = data.get('valida_margen', True)
        valida_vigencia = data.get('valida_vigencia', False)
        
        # NO BLOQUEAR POR STOCK
        validacion_ok = all([
            valida_precios,
            valida_cantidades,
            valida_entrega,
            valida_montos,
            valida_margen,
            valida_vigencia
        ])
        
        if not validacion_ok:
            estado = 'PC observado'
            req_compra = 'Bloqueado'
        else:
            estado = data.get('estado', 'PC conforme')
            req_compra = data.get('req_compra', 'Sí')
        
        pc_id = data.get('id')
        
        # ============================================================
        # SI HAY ID, ACTUALIZAR
        # ============================================================
        if pc_id:
            print(f"🔄 Actualizando PV ID: {pc_id}")
            
            query = """
                UPDATE pedido_compra_pc SET
                    numero = %s,
                    fecha = %s,
                    estado = %s,
                    cliente = %s,
                    ruc = %s,
                    monto = %s,
                    cotizacion_id = %s,
                    cotizacion_numero = %s,
                    correo_origen = %s,
                    fecha_recepcion = %s,
                    fecha_despacho = %s,
                    archivo_oc = %s,
                    observaciones = %s,
                    valida_precios = %s,
                    valida_cantidades = %s,
                    valida_stock = %s,
                    valida_entrega = %s,
                    valida_montos = %s,
                    valida_transporte = %s,
                    valida_margen = %s,
                    valida_vigencia = %s,
                    responsable = %s,
                    lugar_entrega = %s,
                    condicion_atencion = %s,
                    items_json = %s,
                    medio = %s,
                    entrega = %s,
                    condicion_pago = %s,
                    vendedor = %s,
                    req_compra = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING id, numero
            """
            
            params = (
                data.get('numero'),
                fecha,  # ← USAR LA FECHA PROCESADA
                estado,
                data.get('cliente') or '',
                data.get('ruc') or '',
                float(data.get('monto', 0)),
                data.get('cotizacion_id'),
                data.get('cotizacion_numero') or '',
                data.get('correo_origen') or data.get('medio') or '',
                data.get('fecha_recepcion') or data.get('fecha'),
                data.get('fecha_despacho'),
                data.get('archivo_oc'),
                data.get('observaciones') or '',
                valida_precios,
                valida_cantidades,
                valida_stock,
                valida_entrega,
                valida_montos,
                valida_transporte,
                valida_margen,
                valida_vigencia,
                data.get('responsable') or data.get('vendedor') or 'Hellen',
                data.get('lugar_entrega') or data.get('entrega') or '',
                data.get('condicion_atencion') or data.get('condicion_pago') or '',
                items_json,
                data.get('medio') or data.get('correo_origen') or 'Correo',
                data.get('entrega') or data.get('lugar_entrega') or '',
                data.get('condicion_pago') or data.get('condicion_atencion') or '',
                data.get('vendedor') or data.get('responsable') or 'Helen Blas Príncipe',
                req_compra,
                pc_id
            )
            
            result = db_query(query, params)
            print(f"✅ Resultado UPDATE: {result}")
            return result[0] if result else None
        
        # ============================================================
        # SI NO HAY ID, INSERTAR
        # ============================================================
        print("➕ Insertando nuevo PV...")
        
        cotizacion_id = data.get('cotizacion_id')
        if cotizacion_id is None or cotizacion_id == '':
            cotizacion_id = None
        # El PV queda en la empresa de su cotización (o en la elegida arriba)
        empresa_pc = empresa_para_crear(empresa_de(None, 'cotizaciones', 'id', cotizacion_id)
                                        or empresa_de(None, 'cotizaciones', 'numero_cotizacion', data.get('cotizacion_numero')))
        
        query = """
            INSERT INTO pedido_compra_pc (
                numero, fecha, estado, cliente, ruc, monto,
                cotizacion_id, cotizacion_numero, correo_origen,
                fecha_recepcion, fecha_despacho, archivo_oc,
                observaciones, 
                valida_precios, valida_cantidades, valida_stock, 
                valida_entrega, valida_montos, valida_transporte,
                valida_margen, valida_vigencia,
                responsable, lugar_entrega, condicion_atencion,
                creado_por, items_json, medio, entrega,
                condicion_pago, vendedor, req_compra
            ) VALUES (
                %s, %s, %s, %s, %s, %s, 
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s
            ) RETURNING id, numero
        """
        
        params = (
            data.get('numero'),
            fecha,  # ← USAR LA FECHA PROCESADA
            estado,
            data.get('cliente') or '',
            data.get('ruc') or '',
            float(data.get('monto', 0)),
            cotizacion_id,
            data.get('cotizacion_numero') or '',
            data.get('correo_origen') or data.get('medio') or '',
            data.get('fecha_recepcion') or data.get('fecha'),
            data.get('fecha_despacho'),
            data.get('archivo_oc'),
            data.get('observaciones') or '',
            valida_precios,
            valida_cantidades,
            valida_stock,
            valida_entrega,
            valida_montos,
            valida_transporte,
            valida_margen,
            valida_vigencia,
            data.get('responsable') or data.get('vendedor') or 'Hellen',
            data.get('lugar_entrega') or data.get('entrega') or '',
            data.get('condicion_atencion') or data.get('condicion_pago') or '',
            data.get('creado_por'),
            items_json,
            data.get('medio') or data.get('correo_origen') or 'Correo',
            data.get('entrega') or data.get('lugar_entrega') or '',
            data.get('condicion_pago') or data.get('condicion_atencion') or '',
            data.get('vendedor') or data.get('responsable') or 'Helen Blas Príncipe',
            req_compra
        )
        
        numero_pedido = str(data.get('numero') or '')
        if numero_pedido.startswith(('PC-', 'PV-')) and numero_pedido.endswith('-'):
            # N° interno por empresa: se calcula y se guarda en la MISMA transacción con bloqueo,
            # así dos PV creadas al mismo tiempo nunca reciben el mismo número.
            with db_tx() as conn:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                bloquear_numeracion(cur, 'pedido_compra_pc:' + numero_pedido)
                cur.execute("""SELECT COALESCE(MAX(NULLIF(regexp_replace(SUBSTRING(numero FROM %s), '\\D', '', 'g'), '')::bigint), 0) + 1 AS sig
                               FROM pedido_compra_pc WHERE numero ~ %s""",
                            # 26/10/2026: PV-KCF-… sigue la numeración de los PC-KCF-… antiguos (mismo largo de prefijo)
                            (len(numero_pedido) + 1, '^P[CV]' + re.escape(numero_pedido[2:]) + '[0-9]+$'))
                sig = con_piso(cur, 'PC', clave_pc(numero_pedido[3:-1]), cur.fetchone()['sig'])
                params = (numero_pedido + str(sig).zfill(6),) + tuple(params[1:])
                cur.execute(query, params)
                result = cur.fetchall()
        else:
            result = db_query(query, params)
        print(f"✅ Resultado INSERT: {result}")
        if result:
            marcar_empresa(None, 'pedido_compra_pc', result[0]['id'], empresa_pc)
        return result[0] if result else None
        
    except Exception as e:
        print(f"❌ Error en guardar_pc_db: {e}")
        import traceback
        traceback.print_exc()
        raise

def obtener_despachos_db():
    """Obtiene todos los despachos con sus items"""
    try:
        query = """
            SELECT 
                id, numero, fecha, fecha_despacho, estado,
                pc_id, pc_numero, cotizacion_id, cotizacion_numero,
                cliente, ruc, comprobante, guia, origen, destino,
                transportista, observaciones, responsable,
                items_json, created_at, updated_at
            FROM despachos
            ORDER BY id DESC
        """
        results = db_query(query)
        
        # Parsear items_json para cada despacho
        for row in results:
            if row.get('items_json'):
                try:
                    row['items'] = json.loads(row['items_json'])
                except:
                    row['items'] = []
            else:
                row['items'] = []
        
        return results
    except Exception as e:
        print(f"❌ Error en obtener_despachos_db: {e}")
        return []

def guardar_despacho_db(data):
    """Guarda un nuevo despacho con hora local correcta"""
    try:
        from datetime import datetime
        import pytz  # Necesitas instalar pytz: pip install pytz
        
        # ============================================================
        # 🔽 OBTENER HORA LOCAL DE PERÚ (UTC-5)
        # ============================================================
        # Definir zona horaria de Perú
        zona_peru = pytz.timezone('America/Lima')
        ahora = datetime.now(zona_peru)
        fecha_actual = ahora.strftime('%Y-%m-%d %H:%M:%S')
        
        # Si no hay fecha, usar la actual
        fecha_despacho = data.get('fecha_despacho')
        if fecha_despacho:
            try:
                # Si es string con formato YYYY-MM-DD o YYYY-MM-DD HH:MM:SS
                if isinstance(fecha_despacho, str):
                    # Intentar parsear la fecha
                    if ' ' in fecha_despacho:
                        dt = datetime.strptime(fecha_despacho, '%Y-%m-%d %H:%M:%S')
                    else:
                        dt = datetime.strptime(fecha_despacho, '%Y-%m-%d')
                    # Asegurar que la fecha sea naive (sin zona horaria)
                    if dt.tzinfo:
                        dt = dt.astimezone(zona_peru)
                        fecha_despacho = dt.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        fecha_despacho = fecha_despacho
                elif isinstance(fecha_despacho, datetime):
                    # Si es datetime, convertir a zona Perú
                    if fecha_despacho.tzinfo:
                        fecha_despacho = fecha_despacho.astimezone(zona_peru)
                    else:
                        fecha_despacho = zona_peru.localize(fecha_despacho)
                    fecha_despacho = fecha_despacho.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    fecha_despacho = fecha_actual
            except Exception as e:
                print(f"⚠️ Error procesando fecha_despacho: {e}")
                fecha_despacho = fecha_actual
        else:
            fecha_despacho = fecha_actual
        
        print(f"📅 Fecha despacho FINAL: {fecha_despacho}")
        
        # ============================================================
        # GENERAR NÚMERO DE DESPACHO SI NO TIENE
        # ============================================================
        if not data.get('numero'):
            from datetime import datetime
            now = datetime.now(zona_peru)
            data['numero'] = f"DESP-{now.strftime('%Y%m%d')}-{str(now.timestamp()).split('.')[0][-4:]}"
        
        # ============================================================
        # GUARDAR ITEMS COMO JSON
        # ============================================================
        items_json = json.dumps(data.get('items', []))
        
        # ============================================================
        # GUARDAR DESPACHO
        # ============================================================
        query = """
            INSERT INTO despachos (
                numero, fecha, fecha_despacho, estado,
                pc_id, pc_numero, cotizacion_id, cotizacion_numero,
                cliente, ruc, comprobante, guia, origen, destino,
                transportista, observaciones, responsable,
                items_json, creado_por
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s
            ) RETURNING id, numero
        """
        
        params = (
            data.get('numero'),
            fecha_actual,  # ← FECHA CON HORA LOCAL CORRECTA
            fecha_despacho,
            data.get('estado', 'Pendiente despacho'),
            data.get('pc_id'),
            data.get('pc_numero'),
            data.get('cotizacion_id'),
            data.get('cotizacion_numero'),
            data.get('cliente') or '',
            data.get('ruc') or '',
            data.get('comprobante'),
            data.get('guia'),
            data.get('origen', 'ALM-SMP'),
            data.get('destino') or '',
            data.get('transportista'),
            data.get('observaciones') or '',
            data.get('responsable') or 'Hellen',
            items_json,
            data.get('creado_por') or session.get('usuario_id')
        )
        
        result = db_query(query, params)
        print(f"✅ Resultado: {result}")
        
        if result:
            return jsonify({'success': True, 'message': 'Despacho guardado', 'data': result})
        
        return jsonify({'success': False, 'error': 'No se pudo guardar'}), 400
            
    except Exception as e:
        print(f"❌ Error en api_despachos_guardar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# FUNCIONES DE AYUDA PARA DEVOLUCIONES
# ============================================================

def obtener_devoluciones_db():
    """Obtiene todas las devoluciones"""
    try:
        query = """
            SELECT 
                id, numero, fecha, estado, ruc, cliente,
                comprobante_id, comprobante_numero, guia, motivo,
                monto, observaciones, creado_por, created_at, updated_at
            FROM devoluciones
            ORDER BY id DESC
        """
        return db_query(query)
    except Exception as e:
        print(f"❌ Error en obtener_devoluciones_db: {e}")
        return []

def guardar_devolucion_db(data):
    """Guarda una nueva devolución"""
    try:
        query = """
            INSERT INTO devoluciones (
                numero, fecha, estado, ruc, cliente,
                comprobante_id, comprobante_numero, guia, motivo,
                monto, observaciones, creado_por
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING id, numero
        """
        params = (
            data.get('numero'),
           data.get('fecha') or datetime.now().strftime('%Y-%m-%d %H:%M:%S') ,
            data.get('estado', 'Pendiente'),
            data.get('ruc'),
            data.get('cliente'),
            data.get('comprobante_id'),
            data.get('comprobante_numero'),
            data.get('guia'),
            data.get('motivo'),
            float(data.get('monto', 0)),
            data.get('observaciones'),
            data.get('creado_por')
        )
        result = db_query(query, params)
        return result[0] if result else None
    except Exception as e:
        print(f"❌ Error en guardar_devolucion_db: {e}")
        raise

# ============================================================
# RUTAS PRINCIPALES
# ============================================================

@ventas_bp.route('/ventas')
@login_required
def ventas():
    tab = request.args.get('tab', 'cotizaciones')
    # 24/10/2026: Revisión y Validación solo para Hellen y administradores (también si escriben la dirección)
    if tab in ('revision', 'validacion') and not es_aprobador():
        flash('La revisión y validación de cotizaciones es solo para Hellen y los administradores.', 'warning')
        tab = 'cotizaciones'
    return render_template('ventas/index.html', 
                         active_tab=tab,
                         usuario=session.get('usuario'),
                         nombre=session.get('nombre'),
                         empresa=session.get('empresa'))
@ventas_bp.route('/ventas/api/cotizaciones/listar', methods=['GET'])
@login_required
def api_cotizaciones_listar():
    try:
        print("🔍 API COTIZACIONES LLAMADA")
        
        data = obtener_cotizaciones_db()
        data = filtrar_filas('cotizaciones', data)  # solo la empresa elegida arriba
        print(f"📊 Cotizaciones encontradas: {len(data)}")
        
        formatted_data = []
        for row in data:
            formatted_data.append({
                'id': row.get('id'),
                'numero': row.get('numero_cotizacion') or row.get('codigo_cotizacion'),
                'fecha': row.get('fecha_creacion'),
                'estado': row.get('estado'),
                'ruc': row.get('cliente_ruc') or str(row.get('cliente_id', '')),
                'razon': row.get('cliente_razon_social') or row.get('cliente_nombre_comercial') or f"Cliente {row.get('cliente_id', '')}",
                'descripcion': row.get('nota_cotizacion') or row.get('notas') or '',
                'primer_producto': row.get('primer_producto_descripcion') or '',
                'monto': float(row.get('total') or 0),
                'subtotal': float(row.get('subtotal') or 0),
                'igv': float(row.get('igv') or 0),
                'condicion': row.get('condicion_pago') or row.get('forma_pago'),
                'vendedor': row.get('vendedor') or str(row.get('usuario_id', '')),
                'vencimiento': row.get('validez_oferta'),
                'cod_cliente': str(row.get('cliente_id', '')),
                'direccion_entrega': row.get('direccion_entrega'),
                'requerimiento': row.get('requerimiento'),
                'nota': row.get('nota_cotizacion'),
                'descuento_porcentaje': float(row.get('descuento_porcentaje') or 0),
                'descuento_monto': float(row.get('descuento_monto') or 0),
                'descuento_tipo': row.get('descuento_tipo'),
                'contacto': row.get('contacto_cliente'),
                'telefono': row.get('telefono_cliente'),
                'email': row.get('email_cliente'),
                'tiempo_entrega': row.get('tiempo_entrega'),
                'validez_oferta': row.get('validez_oferta'),
                'nota_comercial': row.get('nota_cotizacion'),
                'seguimiento': row.get('seguimiento', 'Helen Blas Príncipe'),
                'motivo': row.get('motivo', 'Proyecto nuevo'),
                'transporte': row.get('transporte', 'Seleccione'),
                'parihuela': row.get('parihuela', 'Seleccione'),
                'nota_interna': row.get('nota_interna', ''),
                **_tiempos(row, 'fecha_creacion')
            })
        
        print(f"✅ Datos formateados: {len(formatted_data)} cotizaciones")
        return jsonify({'success': True, 'data': formatted_data})
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@ventas_bp.route('/ventas/api/cotizaciones/guardar', methods=['POST'])
@login_required
def api_cotizaciones_guardar():
    """
    Crea o actualiza una cotización con su detalle en UNA sola transacción.
    - Los totales (subtotal, descuento, IGV, total) se recalculan en el servidor.
    - Valida cliente, productos, cantidades y precios.
    - Respeta el flujo de estados (validación/aprobación).
    - El número se genera sin duplicados aunque dos usuarios guarden a la vez.
    """
    try:
        data = request.get_json(silent=True) or {}
        usuario_id = session.get('usuario_id')

        # ------------------------------------------------------------
        # 1. Datos básicos y validaciones
        # ------------------------------------------------------------
        try:
            cotizacion_id = int(data.get('id') or 0) or None
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'id de cotización inválido'}), 400
        es_edicion = cotizacion_id is not None

        try:
            cliente_id = int(data.get('cliente_id') or 0)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'cliente_id debe ser un número'}), 400
        if not cliente_id:
            return jsonify({'success': False, 'error': 'cliente_id es requerido'}), 400

        cliente = db_query("SELECT id, razon_social FROM clientes WHERE id = %s", (cliente_id,))
        if not cliente:
            return jsonify({'success': False, 'error': f'Cliente con ID {cliente_id} no encontrado'}), 400

        productos = data.get('productos') or []
        if not productos:
            return jsonify({'success': False, 'error': 'Agrega al menos un producto a la cotización'}), 400

        estado_nuevo = (data.get('estado') or 'Borrador').strip()

        # Puntos críticos (audio de Erika 19/10/2026): sin estos 4 datos la cotización no se guarda
        data['condicion_pago'] = normalizar_condicion(data.get('condicion_pago') or data.get('forma_pago'))
        faltan = [nombre for nombre, valor in (
            ('Condición de pago', data.get('condicion_pago')),
            ('Tiempo de entrega', data.get('tiempo_entrega')),
            ('Transporte', data.get('transporte')),
            ('Parihuela (si incluye o no)', data.get('parihuela')),
        ) if str(valor or '').strip() in ('', 'Seleccione', 'Personalizado')]
        # Pedido de Erika 20/10/2026: para "Solicitar validación" también seguimiento y motivo.
        # La nota interna NO es obligatoria (lo corrigió el mismo 20/10 a las 17:19).
        if estado_nuevo in ('Por validar', 'En revisión'):
            faltan += [nombre for nombre, valor in (
                ('Seguimiento', data.get('seguimiento')),
                ('Motivo', data.get('motivo')),
            ) if str(valor or '').strip() in ('', 'Seleccione')]
        if faltan:
            titulo = ('Faltan campos obligatorios para enviar a validación'
                      if estado_nuevo in ('Por validar', 'En revisión') else 'Faltan campos obligatorios')
            return jsonify({'success': False, 'codigo': 'faltan_campos', 'faltan': faltan,
                            'error': f"{titulo}: {', '.join(faltan)}."}), 400

        # El frontend envía algunos campos con otro nombre: se aceptan ambos
        contacto = data.get('contacto_cliente') or data.get('contacto')
        telefono = data.get('telefono_cliente') or data.get('telefono')
        email = data.get('email_cliente') or data.get('email')
        validez = data.get('validez_oferta') or data.get('validez')
        descuento_tipo = data.get('descuento_tipo') or '%'
        descuento_valor = data.get('descuento_valor', data.get('descuento_porcentaje', 0))
        if descuento_tipo in ('%', 'porcentaje'):
            descuento_porcentaje = a_decimal(descuento_valor)
            if descuento_porcentaje < 0 or descuento_porcentaje > 100:
                return jsonify({'success': False, 'error': 'El descuento debe estar entre 0% y 100%'}), 400
        else:
            descuento_porcentaje = a_decimal(0)
            if a_decimal(descuento_valor) < 0:
                return jsonify({'success': False, 'error': 'El descuento no puede ser negativo'}), 400
        requerimiento = data.get('requerimiento') or ''
        vendedor = data.get('vendedor') or session.get('nombre_completo') or ''

        asegurar_moneda()   # columnas moneda / tipo_cambio (migración 030)
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            # ------------------------------------------------------------
            # 2. Flujo de estados (edición)
            # ------------------------------------------------------------
            estado_actual = None
            if es_edicion:
                cur.execute("SELECT id, estado, numero_cotizacion FROM cotizaciones WHERE id = %s FOR UPDATE",
                            (cotizacion_id,))
                existente = cur.fetchone()
                if not existente:
                    return jsonify({'success': False, 'error': 'La cotización a editar no existe'}), 404
                estado_actual = existente['estado']
                if estado_actual in ESTADOS_BLOQUEADOS and not (estado_actual == 'Generada' and es_aprobador()):
                    return jsonify({'success': False,
                                    'error': f'La cotización está "{estado_actual}" y ya no se puede editar. '
                                             f'Usa "Duplicar" para crear una nueva versión.'}), 409
            error_flujo = validar_transicion_cotizacion(estado_actual or 'Borrador', estado_nuevo)
            if error_flujo:
                return jsonify({'success': False, 'error': error_flujo}), 409

            # ------------------------------------------------------------
            # 3. Resolver productos y calcular importes en el servidor
            # ------------------------------------------------------------
            lineas = []
            no_encontrados = []
            for idx, producto in enumerate(productos, start=1):
                codigo_producto = (producto.get('codigo') or '').strip()
                producto_id = producto.get('producto_id')
                producto_bd = None
                if producto_id:
                    cur.execute("SELECT id, codigo, costo_unitario, precio_unitario FROM productos WHERE id = %s",
                                (producto_id,))
                    producto_bd = cur.fetchone()
                if not producto_bd and codigo_producto:
                    cur.execute("SELECT id, codigo, costo_unitario, precio_unitario FROM productos "
                                "WHERE TRIM(codigo) = TRIM(%s) ORDER BY id LIMIT 1", (codigo_producto,))
                    producto_bd = cur.fetchone()
                if not producto_bd:
                    no_encontrados.append(codigo_producto or f'línea {idx}')
                    continue

                cantidad = a_decimal(producto.get('cantidad'), '1')
                # Máximo 2 decimales en precios (pedido de Erika 19/10/2026)
                precio = redondear(producto.get('valorVenta', producto_bd.get('precio_unitario') or 0))
                if cantidad <= 0:
                    return jsonify({'success': False, 'error': f'Cantidad inválida en la línea {idx} ({codigo_producto})'}), 400
                if precio < 0:
                    return jsonify({'success': False, 'error': f'Precio inválido en la línea {idx} ({codigo_producto})'}), 400
                lineas.append({'producto_id': producto_bd['id'], 'cantidad': cantidad, 'precio': precio,
                               'costo': a_decimal(producto_bd.get('costo_unitario') or 0),
                               'entrega': estado_entrega_valido(producto.get('estado_entrega'))})

            if no_encontrados:
                # Antes se omitían en silencio y la cotización quedaba incompleta
                return jsonify({'success': False,
                                'error': 'Productos no encontrados en la base de datos: ' + ', '.join(no_encontrados)}), 400

            totales = calcular_totales(lineas, descuento_valor, descuento_tipo)
            try:
                moneda_cot = moneda_documento(data)
            except ErrorMoneda as em:
                return jsonify({'success': False, 'error': str(em)}), 400
            if data.get('total') is not None and abs(a_decimal(data.get('total')) - totales['total']) > a_decimal('0.05'):
                print(f"⚠️ Total enviado por el navegador ({data.get('total')}) difiere del calculado "
                      f"({totales['total']}); se guarda el calculado en el servidor.")

            # ------------------------------------------------------------
            # 4. Cabecera
            # ------------------------------------------------------------
            valores = (
                cliente_id, estado_nuevo, totales['subtotal'], totales['igv'], totales['total'], usuario_id,
                data.get('notas', ''), data.get('forma_pago') or data.get('condicion_pago'),
                data.get('tiempo_entrega'), validez, data.get('condicion_pago'), data.get('direccion_entrega'),
                requerimiento, data.get('nota_cotizacion', ''), descuento_porcentaje, totales['descuento'],
                descuento_tipo, contacto, telefono, email,
                data.get('seguimiento', 'Asesor'), data.get('motivo', 'Proyecto nuevo'),
                data.get('transporte', 'Seleccione'), data.get('parihuela', 'Seleccione'),
                data.get('nota_interna', ''), vendedor,
            )
            if es_edicion:
                cur.execute("""
                    UPDATE cotizaciones SET
                        cliente_id = %s, estado = %s, subtotal = %s, igv = %s, total = %s, usuario_id = %s,
                        notas = %s, forma_pago = %s, tiempo_entrega = %s, validez_oferta = %s,
                        condicion_pago = %s, direccion_entrega = %s, requerimiento = %s, nota_cotizacion = %s,
                        descuento_porcentaje = %s, descuento_monto = %s, descuento_tipo = %s,
                        contacto_cliente = %s, telefono_cliente = %s, email_cliente = %s,
                        seguimiento = %s, motivo = %s, transporte = %s, parihuela = %s,
                        nota_interna = %s, vendedor = %s, updated_at = NOW()
                    WHERE id = %s
                    RETURNING id, numero_cotizacion
                """, valores + (cotizacion_id,))
                fila = cur.fetchone()
                numero = fila['numero_cotizacion']
                cur.execute("DELETE FROM cotizacion_detalle WHERE cotizacion_id = %s", (cotizacion_id,))
            else:
                # Numeración sin duplicados: bloqueo + máximo correlativo existente
                bloquear_numeracion(cur, 'cotizaciones')
                cur.execute("""SELECT COALESCE(MAX(NULLIF(regexp_replace(correlativo::text, '\\D', '', 'g'), '')::bigint), 0) + 1
                               AS siguiente FROM cotizaciones""")
                correlativo = con_piso(cur, 'COT', '', cur.fetchone()['siguiente'])
                numero = f"COT-{str(correlativo).zfill(6)}"
                codigo = f"COT-{datetime.now().strftime('%Y%m%d')}-{str(correlativo).zfill(4)}"
                cur.execute("""
                    INSERT INTO cotizaciones (
                        cliente_id, estado, subtotal, igv, total, usuario_id,
                        notas, forma_pago, tiempo_entrega, validez_oferta,
                        condicion_pago, direccion_entrega, requerimiento, nota_cotizacion,
                        descuento_porcentaje, descuento_monto, descuento_tipo,
                        contacto_cliente, telefono_cliente, email_cliente,
                        seguimiento, motivo, transporte, parihuela, nota_interna, vendedor,
                        numero_cotizacion, codigo_cotizacion, correlativo, fecha_creacion
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    RETURNING id, numero_cotizacion
                """, valores + (numero, codigo, correlativo))
                fila = cur.fetchone()
                cotizacion_id = fila['id']
                marcar_empresa(cur, 'cotizaciones', cotizacion_id, empresa_para_crear())

            # 24/10/2026 (Erika): cotización en soles o dólares, con su tipo de cambio
            cur.execute("UPDATE cotizaciones SET moneda = %s, tipo_cambio = %s WHERE id = %s",
                        moneda_cot + (cotizacion_id,))

            # Registro de quién validó (cuando el aprobador guarda con estado validado)
            if estado_nuevo in ESTADOS_VALIDADOS and estado_actual not in ESTADOS_VALIDADOS:
                cur.execute("""UPDATE cotizaciones SET usuario_validacion_id = %s, validado_por_nombre = %s
                               WHERE id = %s""", (usuario_id, session.get('nombre_completo'), cotizacion_id))

            # ------------------------------------------------------------
            # 5. Detalle
            # ------------------------------------------------------------
            factor = (totales['base_imponible'] / totales['subtotal']) if totales['subtotal'] else a_decimal(1)
            for l in lineas:
                subtotal_costo = l['cantidad'] * l['costo']
                subtotal_venta = l['cantidad'] * l['precio']
                margen = ((l['precio'] - l['costo']) / l['costo'] * 100) if l['costo'] > 0 else a_decimal(0)
                precio_desc = l['precio'] * factor
                margen_final = ((precio_desc - l['costo']) / l['costo'] * 100) if l['costo'] > 0 else a_decimal(0)
                cur.execute("""
                    INSERT INTO cotizacion_detalle (
                        cotizacion_id, producto_id, cantidad, costo_unitario, subtotal_costo, margen_porcentaje,
                        precio_venta_unitario, subtotal_venta, descuento_porcentaje, precio_venta_con_descuento,
                        subtotal_venta_con_descuento, descuento_total, margen_final, estado_entrega
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (cotizacion_id, l['producto_id'], l['cantidad'], l['costo'], redondear(subtotal_costo),
                      redondear(margen), l['precio'], redondear(subtotal_venta),
                      redondear((1 - factor) * 100), redondear(precio_desc),
                      redondear(subtotal_venta * factor), redondear(subtotal_venta * (1 - factor)),
                      redondear(margen_final), l['entrega']))

        accion = 'actualizada' if es_edicion else 'creada'
        return jsonify({
            'success': True,
            'message': f'Cotización {accion} correctamente con {len(lineas)} productos',
            'data': {
                'id': cotizacion_id,
                'numero': numero,
                'estado': estado_nuevo,
                'subtotal': float(totales['subtotal']),
                'descuento': float(totales['descuento']),
                'igv': float(totales['igv']),
                'total': float(totales['total']),
                'productos_guardados': len(lineas),
                'productos_fallidos': 0
            }
        })

    except psycopg2.Error as e:
        # 22/10/2026: error de la base explicado en español + texto exacto en "detalle" + registro de fallos
        print(f"❌ Error de BD en api_cotizaciones_guardar: {e}")
        from routes.diagnostico import respuesta_error_bd
        return respuesta_error_bd(e, 'la cotización')
    except Exception as e:
        print(f"❌ Error general en api_cotizaciones_guardar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': 'No se pudo guardar la cotización: ' + str(e),
                        'detalle': e.__class__.__name__ + ': ' + str(e)}), 500


@ventas_bp.route('/ventas/api/cotizaciones/<int:id>', methods=['GET'])
@login_required
def api_cotizaciones_obtener(id):
    try:
        data = obtener_cotizacion_por_id_db(id)
        if data:
            return jsonify({'success': True, 'data': data})
        return jsonify({'success': False, 'error': 'Cotización no encontrada'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@ventas_bp.route('/ventas/api/cotizaciones/<int:id>/toggle', methods=['PUT'])
@login_required
def api_cotizaciones_toggle(id):
    try:
        data = request.get_json(silent=True) or {}
        nuevo_estado = (data.get('estado') or '').strip()
        if not nuevo_estado:
            return jsonify({'success': False, 'error': 'Estado requerido'}), 400

        actual = db_query("SELECT estado FROM cotizaciones WHERE id = %s", (id,))
        if not actual:
            return jsonify({'success': False, 'error': 'Cotización no encontrada'}), 404
        error_flujo = validar_transicion_cotizacion(actual[0]['estado'], nuevo_estado)
        if error_flujo:
            return jsonify({'success': False, 'error': error_flujo}), 409
        
        result = actualizar_estado_cotizacion_db(id, nuevo_estado)
        if result:
            return jsonify({'success': True, 'message': f'Estado actualizado a {nuevo_estado}'})
        return jsonify({'success': False, 'error': 'No se pudo actualizar'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



@ventas_bp.route('/ventas/api/cotizaciones/<int:id>', methods=['DELETE'])
@login_required
def api_cotizaciones_eliminar(id):
    """Elimina (anula) una cotización - guarda respaldo con motivo y cambia estado a Anulada"""
    try:
        print(f"🗑️ Eliminando cotización ID: {id}")

        data = request.get_json(silent=True) or {}
        motivo = (data.get('motivo') or '').strip()

        if not motivo:
            return jsonify({'success': False, 'error': 'El motivo de eliminación es obligatorio'}), 400

        # 1. Obtener datos completos de la cotización + cliente
        query_cabecera = """
            SELECT 
                c.*, 
                cl.razon_social as cliente_razon_social,
                cl.numero_documento as cliente_ruc
            FROM cotizaciones c
            LEFT JOIN clientes cl ON cl.id = c.cliente_id::integer
            WHERE c.id = %s
        """
        result_check = db_query(query_cabecera, (id,))

        if not result_check:
            return jsonify({'success': False, 'error': 'Cotización no encontrada'}), 404

        cot = result_check[0]
        estado_actual = cot.get('estado')
        print(f"📊 Estado actual de la cotización: {estado_actual}")

        if estado_actual == 'Anulada':
            return jsonify({
                'success': True,
                'message': 'La cotización ya estaba anulada',
                'data': {'id': id, 'estado': 'Anulada'}
            })

        if estado_actual in ('Generada',) + ESTADOS_ACEPTADA + ('Facturada',) and not es_aprobador():
            return jsonify({'success': False,
                            'error': f'Solo un aprobador puede anular una cotización en estado "{estado_actual}"'}), 403

        # 2. Obtener productos de la cotización
        query_productos = """
            SELECT 
                d.id, d.producto_id, d.cantidad,
                d.costo_unitario, d.subtotal_costo, d.margen_porcentaje,
                d.precio_venta_unitario, d.subtotal_venta,
                d.descuento_porcentaje, d.precio_venta_con_descuento,
                d.subtotal_venta_con_descuento, d.descuento_total, d.margen_final,
                p.codigo, p.descripcion, p.modelo, p.marca, p.unidad
            FROM cotizacion_detalle d
            LEFT JOIN productos p ON p.id = d.producto_id
            WHERE d.cotizacion_id = %s
        """
        productos = db_query(query_productos, (id,))

        # 3. Asegurar que la tabla de respaldo exista
        crear_tabla_cotizaciones_eliminadas_si_no_existe()

        usuario_id = session.get('usuario_id')

        # 4. Serializar valores no compatibles con JSON (fechas, Decimal)
        from decimal import Decimal

        def _serializar(v):
            if isinstance(v, datetime):
                return v.isoformat()
            if isinstance(v, Decimal):
                return float(v)
            return v

        datos_completos = {k: _serializar(v) for k, v in cot.items()}
        productos_snapshot = [{k: _serializar(v) for k, v in p.items()} for p in (productos or [])]

        # 5. Guardar el respaldo ANTES de anular
        query_insert = """
            INSERT INTO cotizaciones_eliminadas (
                cotizacion_id_original, numero_cotizacion, codigo_cotizacion,
                cliente_id, cliente_razon_social, cliente_ruc,
                fecha_creacion, estado_anterior, subtotal, igv, total,
                condicion_pago, tiempo_entrega, direccion_entrega, vendedor,
                contacto_cliente, telefono_cliente, email_cliente,
                nota_cotizacion, requerimiento,
                productos_json, datos_completos_json,
                motivo_eliminacion, eliminado_por
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s
            )
        """
        params_insert = (
            id,
            cot.get('numero_cotizacion'),
            cot.get('codigo_cotizacion'),
            cot.get('cliente_id'),
            cot.get('cliente_razon_social'),
            cot.get('cliente_ruc'),
            cot.get('fecha_creacion'),
            estado_actual,
            cot.get('subtotal'),
            cot.get('igv'),
            cot.get('total'),
            cot.get('condicion_pago'),
            cot.get('tiempo_entrega'),
            cot.get('direccion_entrega'),
            cot.get('vendedor'),
            cot.get('contacto_cliente'),
            cot.get('telefono_cliente'),
            cot.get('email_cliente'),
            cot.get('nota_cotizacion'),
            cot.get('requerimiento'),
            json.dumps(productos_snapshot),
            json.dumps(datos_completos),
            motivo,
            usuario_id
        )
        # 6. Respaldo + anulación en una sola transacción (antes podía quedar el respaldo sin anular)
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(query_insert, params_insert)
            cur.execute("""
                UPDATE cotizaciones 
                SET estado = 'Anulada', updated_at = NOW()
                WHERE id = %s
                RETURNING id, estado
            """, (id,))
            fila = cur.fetchone()
        result_update = [dict(fila)] if fila else []
        print(f"✅ Cotización {id} respaldada y anulada")

        if result_update:
            return jsonify({
                'success': True,
                'message': 'Cotización anulada y respaldada correctamente',
                'data': result_update[0]
            })

        return jsonify({'success': False, 'error': 'No se pudo anular la cotización'}), 400

    except Exception as e:
        print(f"❌ Error en api_cotizaciones_eliminar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500




# ============================================================
# RÓTULO DE GUÍA DE REMISIÓN - GENERAR PDF
# ============================================================

@ventas_bp.route('/ventas/api/guias/<int:guia_id>/rotulo', methods=['GET'])
@login_required
def generar_rotulo_guia(guia_id):
    """Genera el PDF del rótulo para una guía de remisión (solo si está Generada/Emitida)"""
    try:
        print(f"📄 Generando rótulo para guía ID: {guia_id}")
        
        # 1. Obtener la guía con todos sus datos
        query = """
            SELECT 
                id, serie, numero, fecha_emision, fecha_traslado,
                ruc_remitente, remitente_nombre, remitente_direccion,
                remitente_ubigeo, ruc_destinatario, destinatario_nombre,
                destinatario_direccion, destinatario_ubigeo,
                modalidad_transporte, placa_vehiculo, conductor_dni,
                conductor_nombre, licencia_conductor, transportista_ruc,
                transportista_nombre, motivo_traslado, documento_asociado,
                orden_compra_cliente, factura,
                peso_total, items_json, observaciones, estado_sunat,
                creado_por, created_at, updated_at, empresa_id
            FROM guias_remision
            WHERE id = %s
        """
        guia_result = db_query(query, (guia_id,))
        
        if not guia_result:
            return jsonify({'error': 'Guía no encontrada'}), 404
        
        guia = guia_result[0]
        
        # 2. Validar que la guía esté en estado "Generada" o "Emitida"
        estado = (guia.get('estado_sunat') or '').upper()
        estados_permitidos = ('GENERADA', 'EMITIDA', 'EMITIDO', 'ACEPTADA', 'ACEPTADO')
        
        if estado not in estados_permitidos:
            return jsonify({
                'error': f'La guía debe estar en estado "Generada" o "Emitida" para descargar el rótulo. Estado actual: {guia.get("estado_sunat")}'
            }), 400
        
        print(f"✅ Guía válida: {guia.get('serie')}-{guia.get('numero')} (Estado: {estado})")
        
        # 3. Preparar items
        items = []
        items_json = guia.get('items_json')
        if items_json:
            try:
                if isinstance(items_json, str):
                    items = json.loads(items_json)
                elif isinstance(items_json, (list, dict)):
                    items = items_json
            except Exception as e:
                print(f"⚠️ Error parseando items_json: {e}")
                items = []
        
        # 4. Preparar datos para el rótulo
               # ============================================================
        # 4. Preparar datos para el rótulo
        # ============================================================
        from pdf_generator import pdf_generator
        
        # Formatear fecha de emisión
        fecha_emision = guia.get('fecha_emision')
        if fecha_emision and isinstance(fecha_emision, datetime):
            fecha_emision = fecha_emision.strftime('%d/%m/%Y')
        elif fecha_emision and isinstance(fecha_emision, str):
            try:
                if 'T' in fecha_emision:
                    dt = datetime.fromisoformat(fecha_emision.replace('Z', '+00:00'))
                    fecha_emision = dt.strftime('%d/%m/%Y')
                elif '-' in fecha_emision and len(fecha_emision) >= 10:
                    fecha_emision = datetime.strptime(fecha_emision[:10], '%Y-%m-%d').strftime('%d/%m/%Y')
            except:
                pass
        
        print("=" * 60)
        print("📦 DATOS DE LA GUÍA PARA EL RÓTULO:")
        print(f"  - Conductor: {guia.get('conductor_nombre')}")
        print(f"  - DNI: {guia.get('conductor_dni')}")
        print(f"  - Transportista: {guia.get('transportista_nombre')}")
        print(f"  - RUC Transportista: {guia.get('transportista_ruc')}")
        print(f"  - Factura: {guia.get('factura')}")
        print("=" * 60)
        
        datos_rotulo = {
            'tipo_documento': 'rotulo_guia',
            'empresa': datos_empresa_documento(guia.get('empresa_id') or empresa_id_por_ruc(guia.get('ruc_remitente'))),   # logo, datos y color de la empresa
            'serie': guia.get('serie', 'T001'),
            'numero': guia.get('numero', ''),
            'fecha_emision': fecha_emision,
            'destinatario_nombre': guia.get('destinatario_nombre', ''),
            'ruc_destinatario': guia.get('ruc_destinatario', ''),
            'destinatario_direccion': guia.get('destinatario_direccion', ''),
            # 🔽 CONDUCTOR / CONSIGNADO (¡ESTOS FALTABAN!)
            'conductor_nombre': guia.get('conductor_nombre') or '',
            'conductor_dni': guia.get('conductor_dni') or '',
            # 🔽 TRANSPORTISTA (también para fallback)
            'transportista_nombre': guia.get('transportista_nombre') or '',
            'transportista_ruc': guia.get('transportista_ruc') or '',
            # 🔽 VEHÍCULO
            'placa_vehiculo': guia.get('placa_vehiculo') or '',
            'licencia_conductor': guia.get('licencia_conductor') or '',
            # 🔽 DOCUMENTOS
            'factura': guia.get('factura') or '',
            'documento_asociado': guia.get('documento_asociado') or '',
            'orden_compra_cliente': guia.get('orden_compra_cliente') or '',
            # 🔽 OTROS
            'peso_total': float(guia.get('peso_total', 0) or 0),
            'numero_bultos': int(guia.get('numero_bultos', 1) or 1),
            'observaciones': guia.get('observaciones', '') or '',
            'items': items
        }
        # 5. Generar el PDF del rótulo
        datos_rotulo.update(_numeros_rotulo(guia=guia))
        pdf_path = pdf_generator._generar_rotulo_guia(datos_rotulo)
        
        if not pdf_path:
            return jsonify({'error': 'Error al generar el rótulo'}), 500
        
        # 6. Retornar el PDF
        from flask import send_file
        filename = f"Rotulo_{guia.get('serie', 'T001')}_{guia.get('numero', '0001')}.pdf"
        
        return send_file(
            pdf_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        print(f"❌ Error generando rótulo de guía: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@ventas_bp.route('/ventas/api/guias/<int:guia_id>/rotulo/preview', methods=['GET'])
@login_required
def preview_rotulo_guia(guia_id):
    """Vista previa del rótulo de una guía de remisión"""
    try:
        print(f"👁️ Vista previa de rótulo para guía ID: {guia_id}")
        
        # Misma lógica que generar_rotulo_guia pero sin as_attachment
        query = """
            SELECT 
                id, serie, numero, fecha_emision, fecha_traslado,
                ruc_remitente, remitente_nombre, remitente_direccion,
                remitente_ubigeo, ruc_destinatario, destinatario_nombre,
                destinatario_direccion, destinatario_ubigeo,
                modalidad_transporte, placa_vehiculo, conductor_dni,
                conductor_nombre, licencia_conductor, transportista_ruc,
                transportista_nombre, motivo_traslado, documento_asociado,
                orden_compra_cliente, factura,
                peso_total, items_json, observaciones, estado_sunat,
                creado_por, created_at, updated_at, empresa_id
            FROM guias_remision
            WHERE id = %s
        """
        guia_result = db_query(query, (guia_id,))
        
        if not guia_result:
            return jsonify({'error': 'Guía no encontrada'}), 404
        
        guia = guia_result[0]
        
        # Validar estado
        estado = (guia.get('estado_sunat') or '').upper()
        estados_permitidos = ('GENERADA', 'EMITIDA', 'EMITIDO', 'ACEPTADA', 'ACEPTADO')
        
        if estado not in estados_permitidos:
            return jsonify({
                'error': f'La guía debe estar en estado "Generada" o "Emitida" para ver el rótulo. Estado actual: {guia.get("estado_sunat")}'
            }), 400
        
        # Preparar items
        items = []
        items_json = guia.get('items_json')
        if items_json:
            try:
                if isinstance(items_json, str):
                    items = json.loads(items_json)
                elif isinstance(items_json, (list, dict)):
                    items = items_json
            except:
                items = []
        
              # ============================================================
        # 4. Preparar datos para el rótulo
        # ============================================================
        from pdf_generator import pdf_generator
        
        # Formatear fecha de emisión
        fecha_emision = guia.get('fecha_emision')
        if fecha_emision and isinstance(fecha_emision, datetime):
            fecha_emision = fecha_emision.strftime('%d/%m/%Y')
        elif fecha_emision and isinstance(fecha_emision, str):
            try:
                if 'T' in fecha_emision:
                    dt = datetime.fromisoformat(fecha_emision.replace('Z', '+00:00'))
                    fecha_emision = dt.strftime('%d/%m/%Y')
                elif '-' in fecha_emision and len(fecha_emision) >= 10:
                    fecha_emision = datetime.strptime(fecha_emision[:10], '%Y-%m-%d').strftime('%d/%m/%Y')
            except:
                pass
        
        print("=" * 60)
        print("📦 DATOS DE LA GUÍA PARA EL RÓTULO:")
        print(f"  - Conductor: {guia.get('conductor_nombre')}")
        print(f"  - DNI: {guia.get('conductor_dni')}")
        print(f"  - Transportista: {guia.get('transportista_nombre')}")
        print(f"  - RUC Transportista: {guia.get('transportista_ruc')}")
        print(f"  - Factura: {guia.get('factura')}")
        print("=" * 60)
        
        datos_rotulo = {
            'tipo_documento': 'rotulo_guia',
            'empresa': datos_empresa_documento(guia.get('empresa_id') or empresa_id_por_ruc(guia.get('ruc_remitente'))),   # logo, datos y color de la empresa
            'serie': guia.get('serie', 'T001'),
            'numero': guia.get('numero', ''),
            'fecha_emision': fecha_emision,
            'destinatario_nombre': guia.get('destinatario_nombre', ''),
            'ruc_destinatario': guia.get('ruc_destinatario', ''),
            'destinatario_direccion': guia.get('destinatario_direccion', ''),
            # 🔽 CONDUCTOR / CONSIGNADO (¡ESTOS FALTABAN!)
            'conductor_nombre': guia.get('conductor_nombre') or '',
            'conductor_dni': guia.get('conductor_dni') or '',
            # 🔽 TRANSPORTISTA (también para fallback)
            'transportista_nombre': guia.get('transportista_nombre') or '',
            'transportista_ruc': guia.get('transportista_ruc') or '',
            # 🔽 VEHÍCULO
            'placa_vehiculo': guia.get('placa_vehiculo') or '',
            'licencia_conductor': guia.get('licencia_conductor') or '',
            # 🔽 DOCUMENTOS
            'factura': guia.get('factura') or '',
            'documento_asociado': guia.get('documento_asociado') or '',
            'orden_compra_cliente': guia.get('orden_compra_cliente') or '',
            # 🔽 OTROS
            'peso_total': float(guia.get('peso_total', 0) or 0),
            'numero_bultos': int(guia.get('numero_bultos', 1) or 1),
            'observaciones': guia.get('observaciones', '') or '',
            'items': items
        }
        
        datos_rotulo.update(_numeros_rotulo(guia=guia))
        pdf_path = pdf_generator._generar_rotulo_guia(datos_rotulo)
        
        if not pdf_path:
            return jsonify({'error': 'Error al generar el rótulo'}), 500
        
        from flask import send_file
        return send_file(
            pdf_path,
            mimetype='application/pdf',
            as_attachment=False
        )
        
    except Exception as e:
        print(f"❌ Error generando vista previa de rótulo: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


def _numeros_rotulo(guia=None, despacho=None, pc=None):
    """Los 4 números del rótulo (Erika 22/10/2026): N° despacho, N° PV, N° Guía y N° Factura. '—' si falta."""
    def unir(*vals):
        vistos = []
        for v in vals:
            for x in re.split(r'\s*,\s*', str(v or '').strip()):
                if x and x not in vistos:
                    vistos.append(x)
        return ', '.join(vistos)
    desp, pcs, guias, facts = [], [], [], []
    if guia:
        num = f"{guia.get('serie') or ''}-{guia.get('numero') or ''}".strip('-')
        guias.append(num)
        facts.append(guia.get('factura'))
        n = str(guia.get('numero') or '').strip()
        if n:
            for d in db_query("""SELECT numero, pc_numero, comprobante FROM despachos
                                 WHERE COALESCE(guia, '') ~ %s ORDER BY id DESC LIMIT 3""", (r'(^|[^0-9])0*' + re.escape(n.lstrip('0') or '0') + r'([^0-9]|$)',)):
                desp.append(d['numero'])
                pcs.append(d['pc_numero'])
        asociado = str(guia.get('documento_asociado') or '')
        if asociado.upper().startswith(('PC', 'PV')):
            pcs.append(asociado)
    if despacho:
        desp.append(despacho.get('numero'))
        pcs.append(despacho.get('pc_numero'))
        guias.append(despacho.get('guia'))
        facts.append(despacho.get('comprobante') or despacho.get('factura'))
    if pc:
        pcs.append(pc.get('numero'))
        guias.append(pc.get('guia'))
        facts.append(pc.get('factura'))
        for d in db_query("SELECT numero, guia, comprobante FROM despachos WHERE pc_numero = %s ORDER BY id", (pc.get('numero'),)):
            desp.append(d['numero'])
            guias.append(d['guia'])
            facts.append(d['comprobante'])
    return {'nro_despacho': unir(*desp) or '—', 'nro_pc': unir(*pcs) or '—',
            'nro_guia': unir(*guias) or '—', 'nro_factura': unir(*facts) or '—'}

# ============================================================
# RÓTULO DE PV Y DE DESPACHO (pedido de Erika, 15/10/2026)
# Mismo diseño que el rótulo de la guía, con el logo, datos y color de la empresa del documento.
# ============================================================
@ventas_bp.route('/ventas/api/rotulo/<tipo>/<int:doc_id>', methods=['GET'])
@login_required
def rotulo_documento(tipo, doc_id):
    try:
        if tipo == 'pc':
            filas = db_query("SELECT * FROM pedido_compra_pc WHERE id = %s", (doc_id,))
        elif tipo == 'despacho':
            filas = db_query("SELECT * FROM despachos WHERE id = %s", (doc_id,))
        else:
            return jsonify({'success': False, 'error': 'Tipo de documento no válido'}), 400
        if not filas:
            return jsonify({'success': False, 'error': 'Documento no encontrado'}), 404
        d = filas[0]
        items = d.get('items_json') or d.get('items') or []
        if isinstance(items, str):
            try:
                items = json.loads(items)
            except ValueError:
                items = []
        direccion = d.get('destino') or d.get('lugar_entrega') or d.get('entrega') or ''
        if not direccion and d.get('cotizacion_numero'):
            cot = db_query("SELECT direccion_entrega FROM cotizaciones WHERE numero_cotizacion = %s", (d['cotizacion_numero'],))
            direccion = (cot[0].get('direccion_entrega') if cot else '') or ''
        total = min(max(request.args.get('bultos', 1, type=int) or 1, 1), 99)   # cuántas cajas (una hoja por caja)
        datos = {
            'empresa': datos_empresa_documento(d.get('empresa_id') or (empresa_por_codigo(d.get('empresa')) or {}).get('id')),
            'doc_label': 'N° PEDIDO:' if tipo == 'pc' else 'N° DESPACHO:',
            'doc_valor': d.get('numero') or '',
            'serie': '', 'numero': d.get('numero') or '',
            'fecha_emision': d.get('fecha_despacho') or d.get('fecha'),
            'destinatario_nombre': d.get('cliente') or '',
            'ruc_destinatario': d.get('ruc') or '',
            'destinatario_direccion': direccion,
            'conductor_nombre': d.get('transportista') or d.get('responsable') or '',
            'factura': d.get('factura') or d.get('comprobante') or '',
            'documento_asociado': d.get('cotizacion_numero') or '',
            'numero_bultos': 1, 'total_bultos': total, 'una_hoja_por_bulto': True,
            'observaciones': d.get('observaciones') or '',
            'items': items,
        }
        datos.update(_numeros_rotulo(despacho=d if tipo == 'despacho' else None, pc=d if tipo == 'pc' else None))
        pdf_path = pdf_generator._generar_rotulo_guia(datos)
        if not pdf_path:
            return jsonify({'success': False, 'error': 'No se pudo generar el rótulo'}), 500
        from flask import send_file
        import io
        with open(pdf_path, 'rb') as f:
            contenido = io.BytesIO(f.read())
        try:
            os.remove(pdf_path)  # no dejar PDFs acumulados en el servidor
        except OSError:
            pass
        return send_file(contenido, mimetype='application/pdf', as_attachment=False,
                         download_name=f"Rotulo_{d.get('numero') or doc_id}.pdf")
    except Exception as e:
        print(f"❌ Error generando rótulo de {tipo}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# GUÍAS - API
# ============================================================

@ventas_bp.route('/ventas/api/guias/listar', methods=['GET'])
@login_required
def api_guias_listar():
    try:
        data = obtener_guias_db()
        data = filtrar_filas('guias_remision', data)  # solo la empresa elegida arriba
        formatted_data = []
        for row in data:
            items = []
            try:
                crudo = row.get('items_json')
                # items_json es JSONB en Supabase: llega ya como lista (antes json.loads fallaba y la guía salía sin productos)
                if isinstance(crudo, list):
                    items = crudo
                elif crudo:
                    items = json.loads(crudo)
            except:
                pass
            
            # 🔽 OBTENER FECHA COMO STRING SIN MODIFICAR ZONA HORARIA
            fecha_emision = row.get('fecha_emision')
            if fecha_emision:
                # Si es datetime, convertir a string ISO sin zona horaria
                if isinstance(fecha_emision, datetime):
                    fecha_emision = fecha_emision.strftime('%Y-%m-%d %H:%M:%S')
                elif isinstance(fecha_emision, date):
                    fecha_emision = fecha_emision.strftime('%Y-%m-%d')
            
            formatted_data.append({
                'id': row.get('id'),
                'serie': row.get('serie'),
                'numero': row.get('numero'),
                'fecha': fecha_emision,  # ← ENVIAR COMO STRING SIN ZONA
                'fecha_traslado': row.get('fecha_traslado'),
                'estado': row.get('estado_sunat') or row.get('estado'),
                'ruc': row.get('ruc_destinatario'),
                'cliente': row.get('destinatario_nombre'),
                'cotizacion': row.get('documento_asociado'),
                # Antes mostraba la cotización como si fuera el comprobante: ahora es la factura de verdad
                'comprobante': row.get('factura_vinculada') or '',
                'pc_numero': row.get('pc_numero') or '',
                'origen': row.get('remitente_direccion'),
                'destino': row.get('destinatario_direccion'),
                'motivo': row.get('motivo_traslado'),
                'observaciones': row.get('observaciones'),
                'items': items,
                'placa': row.get('placa_vehiculo'),
                'conductor': row.get('conductor_nombre'),
                'transportista': row.get('transportista_nombre'),
                **_tiempos(row)
            })
        return jsonify({'success': True, 'data': formatted_data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# PREVENCIÓN DE DUPLICADOS (pedido de Erika 20/10/2026 22:54): el servidor es el "policía".
# Lo anulado no cuenta. Las entregas y facturas parciales de un PV siguen permitidas:
# solo se bloquea cuando lo nuevo pasaría lo que pidió el PV y ya hay otro documento con ese producto.
# ============================================================
ANULADOS = ('ANULADO', 'ANULADA')


def _cantidades_por_producto(items_json):
    from routes.compras_flujo import _items_pedido, _resolver_productos
    items = _resolver_productos(_items_pedido({'items_json': items_json}))
    out, nombres = {}, {}
    for it in items:
        clave = it['producto_id'] or (it['codigo'] or '').strip().upper() or (it['descripcion'] or '').strip().upper()
        if clave and it['cantidad'] > 0:
            out[clave] = out.get(clave, a_decimal(0)) + it['cantidad']
            nombres.setdefault(clave, it['descripcion'] or it['codigo'])
    return out, nombres


def _pasa_lo_pedido(pc_items_json, docs, items_nuevos):
    """Primer producto en que lo ya documentado + lo nuevo pasa lo que pidió el PV (solo si ya había algo)."""
    pide, _ = _cantidades_por_producto(pc_items_json)
    ya = {}
    for d in docs:
        for k, c in _cantidades_por_producto(d.get('items_json'))[0].items():
            ya[k] = ya.get(k, a_decimal(0)) + c
    nuevo, nombres = _cantidades_por_producto(items_nuevos)
    for k, c in nuevo.items():
        if k in pide and ya.get(k, 0) > 0 and ya[k] + c > pide[k] + a_decimal('0.001'):
            return {'producto': nombres.get(k), 'pide': float(pide[k]), 'ya': float(ya[k]), 'nuevo': float(c)}
    return None


def _pc_activo(*numeros):
    numeros = [str(n).strip() for n in numeros if n and str(n).strip()]
    if not numeros:
        return None
    filas = db_query("""SELECT numero, cotizacion_numero, items_json FROM pedido_compra_pc
                        WHERE numero = ANY(%s) AND UPPER(COALESCE(estado, '')) NOT IN ('ANULADO', 'ANULADA')
                        ORDER BY id DESC LIMIT 1""", (numeros,))
    return filas[0] if filas else None


def _guia_duplicada(data):
    """Mensaje de bloqueo si la guía nueva repite una guía activa del mismo despacho o PV."""
    desp = str(data.get('despacho_numero') or '').strip()
    if desp:
        f = db_query("""SELECT g.serie || '-' || g.numero::text AS num FROM despachos d
                        JOIN guias_remision g ON d.guia IN (g.serie || '-' || g.numero::text, g.numero::text)
                        WHERE d.numero = %s AND UPPER(COALESCE(g.estado_sunat, '')) NOT IN ('ANULADO', 'ANULADA')
                        LIMIT 1""", (desp,))
        if f:
            return (f"⛔ ERROR: El despacho {desp} ya tiene la guía {f[0]['num']}. No se puede duplicar. "
                    "Si esa guía está mal, anúlala primero.")
    pc = _pc_activo(data.get('pc_numero'), data.get('documento_asociado'))
    if not pc:
        pc = db_query("""SELECT p.numero, p.cotizacion_numero, p.items_json FROM despachos d JOIN pedido_compra_pc p ON p.numero = d.pc_numero
                         WHERE d.numero = %s LIMIT 1""", (desp,)) if desp else None
        pc = pc[0] if pc else None
    if not pc:
        return None
    cot = pc.get('cotizacion_numero') or ''
    guias = db_query("""SELECT g.serie || '-' || g.numero::text AS num, g.items_json FROM guias_remision g
                        WHERE UPPER(COALESCE(g.estado_sunat, '')) NOT IN ('ANULADO', 'ANULADA')
                          AND (g.documento_asociado = %s OR (%s <> '' AND g.documento_asociado = %s)
                               OR g.serie || '-' || g.numero::text IN (SELECT guia FROM despachos WHERE pc_numero = %s AND guia IS NOT NULL)
                               OR g.numero::text IN (SELECT guia FROM despachos WHERE pc_numero = %s AND guia IS NOT NULL))""",
                     (pc['numero'], cot, cot, pc['numero'], pc['numero']))
    pasa = _pasa_lo_pedido(pc['items_json'], guias, data.get('items') or [])
    if pasa:
        nums = ', '.join(sorted({g['num'] for g in guias}))
        return (f"⛔ ERROR: El PV {pc['numero']} ya tiene guía ({nums}). \"{pasa['producto']}\": pidió {pasa['pide']:g}, "
                f"ya hay {pasa['ya']:g} en guías y esta guía agrega {pasa['nuevo']:g}. No se puede duplicar.")
    return None


def _despacho_duplicado(data):
    """Mensaje de bloqueo si el despacho nuevo repite lo que otro despacho activo del mismo PV ya cubre."""
    pc = _pc_activo(data.get('pc_numero'))
    if not pc:
        return None
    desps = db_query("""SELECT numero AS num, items_json FROM despachos
                         WHERE pc_numero = %s AND COALESCE(estado, '') NOT ILIKE 'anulad%%'""", (pc['numero'],))
    pasa = _pasa_lo_pedido(pc['items_json'], desps, data.get('items') or [])
    if pasa:
        nums = ', '.join(sorted({d['num'] for d in desps}))
        return (f"⛔ ERROR: El PV {pc['numero']} ya tiene despacho ({nums}). \"{pasa['producto']}\": pidió {pasa['pide']:g}, "
                f"ya hay {pasa['ya']:g} en despachos y este agrega {pasa['nuevo']:g}. No se puede duplicar. "
                "Búscalo en Ventas ▸ Entregas.")
    return None


def _factura_duplicada(data, pc_origen):
    """Mensaje de bloqueo si la factura nueva repite una factura activa de la misma guía o PV."""
    guia = str(data.get('guia') or '').strip()
    if guia:
        f = db_query("""SELECT serie || '-' || LPAD(numero::text, 8, '0') AS num FROM comprobantes
                        WHERE guia_vinculada = %s AND UPPER(COALESCE(estado_sunat, '')) NOT IN ('ANULADO', 'ANULADA')
                        LIMIT 1""", (guia,))
        if f:
            return (f"⛔ ERROR: La guía {guia} ya fue facturada ({f[0]['num']}). No se puede duplicar. "
                    "Si esa factura está mal, emite una nota de crédito o anúlala primero.")
    pc = _pc_activo(pc_origen.get('numero')) if pc_origen else None
    if not pc:
        return None
    cot = pc.get('cotizacion_numero') or ''
    facs = db_query("""SELECT serie || '-' || LPAD(numero::text, 8, '0') AS num, items_json FROM comprobantes
                       WHERE UPPER(COALESCE(estado_sunat, '')) NOT IN ('ANULADO', 'ANULADA')
                         AND (pc_vinculado = %s OR (COALESCE(pc_vinculado, '') = '' AND %s <> '' AND documento_asociado = %s))""",
                    (pc['numero'], cot, cot))
    pasa = _pasa_lo_pedido(pc['items_json'], facs, data.get('items') or [])
    if pasa:
        nums = ', '.join(sorted({f['num'] for f in facs}))
        return (f"⛔ ERROR: El PV {pc['numero']} ya fue facturado ({nums}). \"{pasa['producto']}\": pidió {pasa['pide']:g}, "
                f"ya hay {pasa['ya']:g} facturado y esta factura agrega {pasa['nuevo']:g}. No se puede duplicar.")
    return None


def _faltantes_stock_guia(data, empresa_id):
    """Productos de una guía de venta nueva que no tienen stock en la empresa (todas sus sedes).
    Si su despacho ya salió (Despachado/Entregado), el stock ya se descontó: no se revisa."""
    motivo = str(data.get('motivo_traslado') or '01').strip().upper()
    if motivo not in ('01', 'VENTA'):
        return []
    claves = [str(data.get(k) or '').strip() for k in ('despacho_numero', 'pc_numero', 'documento_asociado', 'cotizacion_numero')]
    claves = [c for c in claves if c]
    if claves and db_query("""SELECT 1 FROM despachos WHERE COALESCE(estado, '') IN ('Despachado', 'Entregado')
                               AND (numero = ANY(%s) OR pc_numero = ANY(%s) OR cotizacion_numero = ANY(%s)) LIMIT 1""",
                            (claves, claves, claves)):
        return []
    from routes.compras_flujo import _resolver_productos
    items = _resolver_productos([{'producto_id': it.get('producto_id'), 'codigo': str(it.get('codigo') or '').strip(),
                                  'descripcion': it.get('producto') or it.get('descripcion') or '',
                                  'cantidad': a_decimal(it.get('cantidad') or 0)}
                                 for it in (data.get('items') or []) if isinstance(it, dict)])
    pide = {}
    for it in items:
        if it['producto_id'] and it['cantidad'] > 0:  # producto escrito a mano: no se puede saber su stock
            p = pide.setdefault(it['producto_id'], {'producto': it['descripcion'] or it['codigo'], 'cantidad': a_decimal(0)})
            p['cantidad'] += it['cantidad']
    if not pide:
        return []
    ids = list(pide)
    if empresa_id is not None:
        filas = db_query("""SELECT producto_id, COALESCE(SUM(cantidad), 0) AS hay FROM inv_stock
                             WHERE producto_id = ANY(%s) AND empresa_id = %s GROUP BY producto_id""", (ids, empresa_id))
        emp = empresa_por_id(empresa_id) or {}
        nombre_emp = emp.get('nombre_corto') or emp.get('codigo') or emp.get('razon_social') or 'la empresa'
    else:
        filas = db_query("""SELECT producto_id, COALESCE(SUM(cantidad), 0) AS hay FROM inv_stock
                             WHERE producto_id = ANY(%s) GROUP BY producto_id""", (ids,))
        nombre_emp = 'el grupo'
    hay = {f['producto_id']: a_decimal(f['hay']) for f in filas}
    return [{'producto': p['producto'], 'producto_id': pid, 'empresa': nombre_emp, 'sede': 'todas las sedes',
             'pide': float(p['cantidad']), 'hay': float(max(hay.get(pid, a_decimal(0)), a_decimal(0)))}
            for pid, p in pide.items() if hay.get(pid, a_decimal(0)) < p['cantidad']]


@ventas_bp.route('/ventas/api/guias/guardar', methods=['POST'])
@login_required
def api_guias_guardar():
    try:
        data = request.get_json()
        usuario_id = session.get('usuario_id')
        
        print("=" * 80)
        print("📦 API GUIAS GUARDAR - INICIO")
        print(f"  - Usuario ID: {usuario_id}")
        print("=" * 80)
        
        from datetime import datetime
        
        # ============================================================
        # ORIGEN FIJO - DATOS DEL REMITENTE
        # ============================================================
        ORIGEN_FIJO = {
            'ruc': '20602095704',
            'nombre': 'KCF CORPORACION E.I.R.L',
            'direccion': 'JR. LAS ALMENDRAS VERDES NRO. 284 URB. VIRGEN DEL ROSARIO LIMA - LIMA - SAN MARTIN DE PORRES',
            'ubigeo': '150139'
        }
        
        # ============================================================
        # 🔽 RECIBIR FECHA CON HORA DEL FRONTEND
        # ============================================================
        # El frontend ya envía fecha_emision con hora completa
        fecha_emision = data.get('fecha_emision')
        if not fecha_emision:
            # Fallback: usar ahora
            fecha_emision = datetime.now().isoformat()
        
        # Fecha de traslado
        fecha_traslado = data.get('fecha_traslado')
        if not fecha_traslado:
            fecha_traslado = datetime.now().date().isoformat()
        
        print(f"📅 fecha_emision recibida: {fecha_emision}")
        print(f"📅 fecha_traslado: {fecha_traslado}")
        
        # ============================================================
        # CONSULTA
        # ============================================================
        query = """
            INSERT INTO guias_remision (
                serie, numero, fecha_emision, fecha_traslado,
                ruc_remitente, remitente_nombre, remitente_direccion,
                remitente_ubigeo, ruc_destinatario, destinatario_nombre,
                destinatario_direccion, destinatario_ubigeo,
                modalidad_transporte, placa_vehiculo, conductor_dni,
                conductor_nombre, licencia_conductor, transportista_ruc,
                transportista_nombre, motivo_traslado, documento_asociado,
                orden_compra_cliente, factura,
                peso_total, items_json, observaciones, estado_sunat,
                creado_por, created_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, NOW()
            )
            RETURNING id, numero
        """
        
        pc_guia = _pc_de_comprobante({'pc': data.get('pc') or data.get('pc_numero') or data.get('pc_vinculado'),
                                      'cotizacion': data.get('documento_asociado') or data.get('cotizacion')})
        items_json = json.dumps(_completar_desc_cliente(data.get('items', []), pc_guia.get('numero') if pc_guia else None))
        serie = (data.get('serie') or 'T001').strip()
        numero = str(data.get('numero') or '').strip()

        # ------------------------------------------------------------
        # EDICIÓN: antes cada edición creaba una guía nueva (duplicados)
        # ------------------------------------------------------------
        if data.get('id'):
            actual = db_query("SELECT id, estado_sunat FROM guias_remision WHERE id = %s", (data['id'],))
            if not actual:
                return jsonify({'success': False, 'error': 'Guía no encontrada'}), 404
            if (actual[0].get('estado_sunat') or '').upper() in ('EMITIDA', 'EMITIDO', 'ACEPTADA', 'ACEPTADO', 'ANULADA', 'ANULADO'):
                return jsonify({'success': False,
                                'error': f'La guía está "{actual[0].get("estado_sunat")}" y ya no se puede modificar'}), 409
            datos_upd = dict(data)
            datos_upd['items_json'] = items_json
            datos_upd['estado_sunat'] = data.get('estado', 'BORRADOR')
            datos_upd['fecha_traslado'] = fecha_traslado
            fila = actualizar_guia_db(data['id'], datos_upd)
            if fila:
                return jsonify({'success': True, 'message': 'Guía actualizada correctamente',
                                'data': {'id': fila['id'], 'numero': fila['numero']}})
            return jsonify({'success': False, 'error': 'No se pudo actualizar la guía'}), 400

        # La guía queda en la empresa de su despacho / PV / cotización (o la elegida arriba).
        # El remitente es esa empresa (antes siempre salía KCF) y la numeración es por empresa (cada RUC tiene la suya).
        doc = (data.get('documento_asociado') or '').strip()
        empresa_guia = empresa_para_crear(empresa_de(None, 'despachos', 'numero', data.get('despacho_numero'))
                                          or empresa_de(None, 'pedido_compra_pc', 'numero', data.get('pc_numero'))
                                          or empresa_de(None, 'cotizaciones', 'numero_cotizacion', doc)
                                          or empresa_de(None, 'pedido_compra_pc', 'numero', doc))
        emp = empresa_por_id(empresa_guia)
        if emp:
            rucs_grupo = {e['ruc'] for e in empresas()}
            if not data.get('ruc_remitente') or (data.get('ruc_remitente') in rucs_grupo and data.get('ruc_remitente') != emp['ruc']):
                data['ruc_remitente'] = emp['ruc']
                data['remitente_nombre'] = emp['razon_social']
                data['remitente_direccion'] = emp.get('direccion_fiscal') or ''
                if emp.get('ubigeo'):
                    data['remitente_ubigeo'] = emp['ubigeo']
        # No se repite una guía del mismo despacho o PV (pedido de Erika 20/10/2026 22:54)
        duplicada = _guia_duplicada(data)
        if duplicada:
            return jsonify({'success': False, 'codigo': 'duplicado', 'titulo': 'GUÍA DUPLICADA: NO SE CREÓ', 'error': duplicada}), 409
        # Pedido de Erika 20/10/2026: la guía es para entregar, así que sin stock no se crea (la factura sí).
        faltan_guia = _faltantes_stock_guia(data, empresa_guia)
        from routes.stock_automatico import texto_en_transito
        if faltan_guia:
            nombres = ', '.join(f"{f['producto']} (pide {f['pide']:g}, hay {f['hay']:g})" for f in faltan_guia[:5])
            return jsonify({'success': False, 'codigo': 'falta_stock', 'faltan': faltan_guia,
                            'titulo': 'NO SE PUEDE CREAR LA GUÍA: FALTA STOCK',
                            'error': f'No se puede crear la guía: falta stock de {nombres}.'
                                     + (texto_en_transito(faltan_guia) or ' Primero compra o recibe la mercadería.')
                                     + ' La factura sí se puede hacer sin stock.'}), 409
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            if numero:
                bloquear_numeracion(cur, f"guias_remision:{serie}")
                cur.execute("SELECT 1 FROM guias_remision WHERE serie = %s AND numero = %s AND empresa_id IS NOT DISTINCT FROM %s",
                            (serie, numero, empresa_guia))
                if cur.fetchone():
                    return jsonify({'success': False,
                                    'error': f'Ya existe la guía {serie}-{numero}. Deja el número vacío para asignarlo automáticamente.'}), 409
            else:
                numero = _siguiente_numero(cur, 'guias_remision', serie, extra_where='AND empresa_id IS NOT DISTINCT FROM %s',
                                           extra_params=(empresa_guia,))
                # Configuración ▸ Correlativos: el administrador puede fijar desde qué número sigue
                numero = str(con_piso(cur, 'GUIA', clave_guia(empresa_guia, serie), numero)).zfill(8)
            data['numero'] = numero
            # La guía se guarda dentro de la misma transacción del número: dos guías al mismo tiempo
            # ya no pueden recibir el mismo correlativo (antes el bloqueo se soltaba antes de guardar).
            params = (
                serie,
                data.get('numero'),
                fecha_emision,  # ← YA VIENE CON HORA DEL FRONTEND
                fecha_traslado,
                data.get('ruc_remitente') or ORIGEN_FIJO['ruc'],
                data.get('remitente_nombre') or ORIGEN_FIJO['nombre'],
                data.get('remitente_direccion') or ORIGEN_FIJO['direccion'],
                data.get('remitente_ubigeo') or ORIGEN_FIJO['ubigeo'],
                data.get('ruc_destinatario', ''),
                data.get('destinatario_nombre', ''),
                data.get('destinatario_direccion', ''),
                data.get('destinatario_ubigeo', ''),
                data.get('modalidad_transporte', 'PRIVADO'),
                data.get('placa_vehiculo', ''),
                data.get('conductor_dni', ''),
                data.get('conductor_nombre', ''),
                data.get('licencia_conductor', ''),
                data.get('transportista_ruc', ''),
                data.get('transportista_nombre', ''),
                data.get('motivo_traslado', '01'),
                data.get('documento_asociado', ''),
                data.get('orden_compra_cliente',''),
                data.get('factura',''),
                float(data.get('peso_total', 0)),
                items_json,
                data.get('observaciones', ''),
                data.get('estado', 'BORRADOR'),
                usuario_id
            )
            cur.execute(query, params)
            result = cur.fetchall()
            if result:
                marcar_empresa(cur, 'guias_remision', result[0]['id'], empresa_guia)
            if result and data.get('despacho_numero'):
                # El despacho queda con su guía (antes quedaba vacío y no se sabía qué guía era de qué despacho)
                cur.execute("""UPDATE despachos SET guia = %s
                               WHERE numero = %s AND COALESCE(guia, '') = ''""",
                            (f"{serie}-{result[0]['numero']}", data['despacho_numero']))
        
        if result and len(result) > 0:
            row = result[0]
            if isinstance(row, dict):
                guia_id = row.get('id')
                guia_numero = row.get('numero')
            else:
                guia_id = row[0] if len(row) > 0 else None
                guia_numero = row[1] if len(row) > 1 else None
            
            if guia_id:
                marcar_empresa(None, 'guias_remision', guia_id, empresa_guia)
                return jsonify({
                    'success': True,
                    'message': 'Guía creada correctamente',
                    'data': {
                        'id': guia_id,
                        'serie': serie,
                        'numero': guia_numero
                    }
                })
        
        return jsonify({'success': False, 'error': 'No se pudo crear la guía'}), 400
            
    except Exception as e:
        print(f"❌ Error en api_guias_guardar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@ventas_bp.route('/ventas/api/guias/<int:id>', methods=['GET'])
@login_required
def api_guias_obtener(id):
    try:
        data = obtener_guia_por_id_db(id)
        if data:
            return jsonify({'success': True, 'data': data})
        return jsonify({'success': False, 'error': 'Guía no encontrada'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@ventas_bp.route('/ventas/api/guias/<int:id>', methods=['DELETE'])
@login_required
def api_guias_eliminar(id):
    try:
        # Antes se usaba actualizar_guia_db con un dict vacío y se borraban todos los datos de la guía
        result = db_query("UPDATE guias_remision SET estado_sunat = 'ANULADA', updated_at = NOW() "
                          "WHERE id = %s RETURNING id", (id,))
        if result:
            return jsonify({'success': True, 'message': 'Guía anulada'})
        return jsonify({'success': False, 'error': 'No se pudo anular'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# GUÍAS - ELIMINACIÓN FÍSICA
# ============================================================

@ventas_bp.route('/ventas/api/guias/<int:id>/permanente', methods=['DELETE'])
@login_required
def api_guias_eliminar_permanente(id):
    """Elimina físicamente una guía de la base de datos (solo si ya está anulada)"""
    try:
        print(f"🗑️ Eliminando físicamente guía ID: {id}")

        query_check = "SELECT id, numero, estado_sunat FROM guias_remision WHERE id = %s"
        result_check = db_query(query_check, (id,))

        if not result_check:
            return jsonify({'success': False, 'error': 'Guía no encontrada'}), 404

        estado = (result_check[0].get('estado_sunat') or '').upper()
        if estado not in ('ANULADA', 'ANULADO'):
            return jsonify({
                'success': False,
                'error': f'Solo se pueden eliminar guías en estado "Anulada". Estado actual: {result_check[0].get("estado_sunat")}'
            }), 400

        query_delete = "DELETE FROM guias_remision WHERE id = %s RETURNING id"
        result_delete = db_query(query_delete, (id,))

        if result_delete:
            return jsonify({'success': True, 'message': 'Guía eliminada correctamente', 'data': {'id': id}})

        return jsonify({'success': False, 'error': 'No se pudo eliminar la guía'}), 400

    except Exception as e:
        print(f"❌ Error en api_guias_eliminar_permanente: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# COMPROBANTES - API
# ============================================================

@ventas_bp.route('/ventas/api/comprobantes/listar', methods=['GET'])
@login_required
def api_comprobantes_listar():
    try:
        try:
            from routes.archivos_factura import asegurar_archivos_factura
            asegurar_archivos_factura()  # la lista pregunta si la factura ya tiene su XML de SUNAT
            asegurar_migo()
        except Exception as e:
            print(f"⚠️ tablas de la lista de facturas: {e}")
        data = obtener_comprobantes_db()
        data = filtrar_filas('comprobantes', data)  # solo la empresa elegida arriba
        formatted_data = []
        for row in data:
            items = []
            try:
                if row.get('items_json'):
                    items = json.loads(row.get('items_json'))
            except:
                pass
            formatted_data.append({
                'id': row.get('id'),
                'tipo': row.get('tipo_comprobante'),
                'serie': row.get('serie'),
                'numero': row.get('numero'),
                'fecha': row.get('fecha_emision'),
                'estado': row.get('estado_sunat') or 'Borrador',
                'ruc': row.get('cliente_numero_doc'),
                'cliente': row.get('cliente_nombre'),
                'cotizacion': row.get('cotizacion_numero') or row.get('documento_asociado'),
                'pc_numero': row.get('pc_numero') or '',
                'guia_numero': row.get('guia_numero') or '',
                'monto': float(row.get('total') or 0),
                'monto_retenido': float(row.get('monto_retenido') or 0),
                'monto_a_pagar': float(row.get('monto_a_pagar') or 0),
                'numero_migo': row.get('numero_migo') or '',
                'xml_id': row.get('xml_id'),
                'subtotal': float(row.get('subtotal') or 0),
                'igv': float(row.get('igv') or 0),
                # Antes decía siempre 'Contado' aunque la factura fuera a crédito (bug visto por Erika 19/10/2026)
                'condicion': normalizar_condicion(row.get('condicion_pago')) or 'Contado',
                'dias_credito': row.get('dias_credito'),
                'estado_credito': row.get('estado_credito'),
                'tiene_retencion': str(row.get('tiene_retencion')).lower() == 'true',
                'porcentaje_retencion': float(row.get('porcentaje_retencion') or 3),
                'observaciones': row.get('observaciones'),
                'items': items,
                **_tiempos(row)
            })
        return jsonify({'success': True, 'data': formatted_data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _numero_8(fila):
    """Número de comprobante con 8 dígitos (en Supabase la columna es numérica y se pierde el relleno)."""
    fila = dict(fila)
    if fila.get('numero') is not None and str(fila['numero']).isdigit():
        fila['numero'] = str(fila['numero']).zfill(8)
    return fila


_SQL_INSERT_COMPROBANTE = """
    INSERT INTO comprobantes (
        tipo_comprobante, serie, numero, fecha_emision,
        moneda, cliente_tipo_doc, cliente_numero_doc,
        cliente_nombre, cliente_direccion, cliente_email,
        cliente_telefono, subtotal, igv, total,
        items_json, observaciones, estado_sunat,
        condicion_pago, documento_asociado, guia_vinculada,
        pc_vinculado, creado_por,
        -- 🔽 NUEVO CAMPO: ORDEN DE COMPRA MANUAL
        orden_compra_cliente,
        tiene_retencion, es_credito, estado_credito,
        fecha_aprobacion, fecha_vencimiento, dias_credito,
        porcentaje_retencion, monto_retenido, monto_a_pagar,
        obs_retencion
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        %s, %s,
        %s, -- orden_compra_cliente
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
    )
    RETURNING id, serie, numero
"""


def _params_insert_comprobante(comprobante_data):
    return (
        comprobante_data['tipo_comprobante'],
        comprobante_data['serie'],
        comprobante_data['numero'],
        comprobante_data['fecha_emision'],
        comprobante_data['moneda'],
        comprobante_data['cliente_tipo_doc'],
        comprobante_data['cliente_numero_doc'],
        comprobante_data['cliente_nombre'],
        comprobante_data['cliente_direccion'],
        comprobante_data['cliente_email'],
        comprobante_data['cliente_telefono'],
        comprobante_data['subtotal'],
        comprobante_data['igv'],
        comprobante_data['total'],
        comprobante_data['items_json'],
        comprobante_data['observaciones'],
        comprobante_data['estado_sunat'],
        comprobante_data['condicion_pago'],
        comprobante_data['documento_asociado'],
        comprobante_data['guia_vinculada'],
        comprobante_data['pc_vinculado'],
        comprobante_data['creado_por'],
        # 🔽 ORDEN DE COMPRA MANUAL
        comprobante_data['orden_compra_cliente'],
        comprobante_data['tiene_retencion'],
        comprobante_data['es_credito'],
        comprobante_data['estado_credito'],
        comprobante_data['fecha_aprobacion'],
        comprobante_data['fecha_vencimiento'],
        comprobante_data['dias_credito'],
        comprobante_data['porcentaje_retencion'],
        comprobante_data['monto_retenido'],
        comprobante_data['monto_a_pagar'],
        comprobante_data['obs_retencion']
    )


def _completar_desc_cliente(items, pc_numero):
    """24/10/2026 (caso Komatsu): la descripción que el cliente pide en su OC se escribe por línea en el PV.
    Si la guía o la factura llega sin ella, se toma del PV por código de producto. El catálogo no cambia."""
    if not pc_numero or not isinstance(items, list):
        return items
    try:
        filas = db_query("SELECT items_json FROM pedido_compra_pc WHERE numero = %s ORDER BY id DESC LIMIT 1", (pc_numero,))
        pc_items = filas[0]['items_json'] if filas else []
        if isinstance(pc_items, str):
            pc_items = json.loads(pc_items or '[]')
    except Exception:
        return items
    mapa = {str(i.get('codigo') or '').strip().upper(): (i.get('descripcion_cliente') or '').strip()
            for i in pc_items or [] if isinstance(i, dict) and (i.get('descripcion_cliente') or '').strip()}
    for it in items:
        if isinstance(it, dict) and not (it.get('descripcion_cliente') or '').strip():
            d = mapa.get(str(it.get('codigo') or '').strip().upper())
            if d:
                it['descripcion_cliente'] = d
    return items


def _pc_de_comprobante(data):
    """PV de origen de una factura: la vinculada; si no, la de su guía (por la PV anotada en la guía
    o por el despacho de la guía)."""
    pc = (data.get('pc') or data.get('pc_vinculado') or '').strip()
    filas = []
    if pc:
        filas = db_query("""SELECT numero, condicion_pago, to_jsonb(p) ->> 'oc_cliente' AS oc_cliente,
                   to_jsonb(p) ->> 'moneda' AS moneda, to_jsonb(p) ->> 'tipo_cambio' AS tipo_cambio
                            FROM pedido_compra_pc p WHERE numero = %s ORDER BY id DESC LIMIT 1""", (pc,))
    guia = (data.get('guia') or data.get('guia_vinculada') or '').strip()
    if not filas and guia:
        # La guía guarda su cotización (documento_asociado) y el despacho guarda su PV
        filas = db_query("""
            SELECT p.numero, p.condicion_pago, to_jsonb(p) ->> 'oc_cliente' AS oc_cliente,
                   to_jsonb(p) ->> 'moneda' AS moneda, to_jsonb(p) ->> 'tipo_cambio' AS tipo_cambio
            FROM guias_remision g
            JOIN pedido_compra_pc p ON p.id IN (
                     SELECT d.pc_id FROM despachos d
                     WHERE d.guia IN (g.numero, g.serie || '-' || g.numero))
                 OR (p.cotizacion_numero = g.documento_asociado AND COALESCE(g.documento_asociado, '') <> ''
                     AND COALESCE(p.estado, '') NOT IN ('Anulado', 'Anulada'))
            WHERE (g.serie || '-' || g.numero) = %s OR g.numero = %s
            ORDER BY p.id DESC LIMIT 1""", (guia, guia))
    cot = (data.get('cotizacion') or data.get('cotizacion_numero') or '').strip()
    if not filas and cot:
        filas = db_query("""SELECT numero, condicion_pago, to_jsonb(p) ->> 'oc_cliente' AS oc_cliente,
                   to_jsonb(p) ->> 'moneda' AS moneda, to_jsonb(p) ->> 'tipo_cambio' AS tipo_cambio
                            FROM pedido_compra_pc p WHERE cotizacion_numero = %s
                              AND COALESCE(estado, '') NOT IN ('Anulado', 'Anulada')
                            ORDER BY id DESC LIMIT 1""", (cot,))
    return filas[0] if filas else None


def _condicion_del_cliente(ruc):
    ruc = (ruc or '').strip()
    if not ruc:
        return ''
    filas = db_query("""SELECT to_jsonb(c) ->> 'condicion_pago' AS condicion, to_jsonb(c) ->> 'dias_credito' AS dias
                        FROM clientes c
                        WHERE numero_documento = %s OR to_jsonb(c) ->> 'ruc' = %s LIMIT 1""", (ruc, ruc))
    if not filas:
        return ''
    texto = (filas[0].get('condicion') or '').strip()
    try:
        dias = int(float(filas[0].get('dias') or 0))
    except (TypeError, ValueError):
        dias = 0
    # En la ficha del cliente la condición es "Contado" / "Crédito aprobado" / "Bloqueado" y los días van aparte
    if 'bloque' in texto.lower():
        return ''
    if 'cr' in texto.lower() and 'dito' in texto.lower() and dias > 0:
        return f'Crédito {dias} días'
    cond = normalizar_condicion(texto)
    return cond if cond in ('Contado', 'Contra entrega') or cond.startswith('Crédito ') and cond.endswith(' días') else ''


def condicion_fija_factura(pc_origen, ruc):
    """Condición de pago que manda en la factura: la del PV; si no hay PV, la de la ficha del cliente.
    Devuelve (condición, fuente) o ('', '') si no hay ninguna."""
    if pc_origen and normalizar_condicion(pc_origen.get('condicion_pago')):
        return normalizar_condicion(pc_origen.get('condicion_pago')), f"PV {pc_origen.get('numero')}"
    cond = _condicion_del_cliente(ruc)
    return (cond, 'ficha del cliente') if cond else ('', '')


def _auditar_cambio_condicion(cambio, fila):
    """Si Erika puso una condición distinta a la del PV o del cliente, queda registrado con fecha y hora."""
    if not cambio or not fila:
        return
    fija, nueva, fuente = cambio
    from routes.auditoria import registrar_auditoria
    registrar_auditoria('ACTUALIZAR', 'Ventas', 'comprobantes', fila.get('id'),
                        antes={'condicion_pago': fija}, despues={'condicion_pago': nueva},
                        detalle=f"Factura {fila.get('serie')}-{fila.get('numero')}: condición cambiada por Erika de "
                                f"'{fija}' ({fuente}) a '{nueva}'")


def _datos_extra_factura_pdf(comp):
    """PDF de la factura (26/10/2026): "OC:" es el N° PC (Pedido del cliente) (antes salía el N° de cotización) y, si lo
    tiene, el N° MIGO de la conformidad. La cotización sale aparte en "COTIZACIÓN"."""
    try:
        fila = db_query("""SELECT to_jsonb(c) ->> 'orden_compra_cliente' AS oc, to_jsonb(c) ->> 'numero_migo' AS migo,
                                  to_jsonb(c) ->> 'pc_vinculado' AS pc
                           FROM comprobantes c WHERE id = %s""", (comp.get('id'),))
        f = fila[0] if fila else {}
        oc = (f.get('oc') or '').strip()
        if not oc and f.get('pc'):
            p = db_query("SELECT to_jsonb(p) ->> 'oc_cliente' AS oc FROM pedido_compra_pc p WHERE numero = %s "
                         "ORDER BY id DESC LIMIT 1", (f.get('pc'),))
            oc = (p[0].get('oc') or '').strip() if p else ''
        return {'orden_compra_cliente': oc or '—', 'numero_migo': (f.get('migo') or '').strip()}
    except Exception as e:
        print(f"⚠️ datos extra del PDF: {e}")
        return {}


def _pide_migo_seguro(ruc):
    """¿El cliente pide N° MIGO para pagar? (Erika 25/10/2026). Si algo falla, no estorba a la factura."""
    try:
        from routes.migo import cliente_pide_migo
        return cliente_pide_migo(ruc)
    except Exception as e:
        print(f"⚠️ pide_migo: {e}")
        return False


@ventas_bp.route('/ventas/api/comprobantes/condicion-origen', methods=['GET'])
@login_required
def api_condicion_origen_factura():
    """Condición de pago que le corresponde a una factura: la de su PV (o la de la PV de su guía o
    cotización) y, si no hay PV, la del cliente. Lo usa la pantalla de la factura para llenarla sola."""
    try:
        args = request.args
        pc = _pc_de_comprobante({'pc': args.get('pc'), 'guia': args.get('guia'), 'cotizacion': args.get('cotizacion')})
        if pc and normalizar_condicion(pc.get('condicion_pago')):
            return jsonify({'success': True, 'data': {
                'condicion': normalizar_condicion(pc.get('condicion_pago')), 'fuente': f"PV {pc.get('numero')}",
                'pc': pc.get('numero'), 'oc_cliente': pc.get('oc_cliente') or '',
                'pide_migo': _pide_migo_seguro(args.get('ruc'))}})
        cond = _condicion_del_cliente(args.get('ruc'))
        return jsonify({'success': True, 'data': {'condicion': cond, 'fuente': 'cliente' if cond else '',
                                                  'pc': None, 'oc_cliente': '', 'pide_migo': _pide_migo_seguro(args.get('ruc'))}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@ventas_bp.route('/ventas/api/comprobantes/guardar', methods=['POST'])
@login_required
def api_comprobantes_guardar():
    try:
        data = request.get_json()
        usuario_id = session.get('usuario_id')
        
        items_json = data.get('items', [])
        
        # ============================================================
        # 🔽 OBTENER DATOS DE RETENCIÓN DEL IGV (3%)
        # ============================================================
        tiene_retencion = data.get('tiene_retencion', False)
        es_credito = data.get('es_credito', False)
        estado_credito = data.get('estado_credito')
        fecha_aprobacion = data.get('fecha_aprobacion')
        fecha_vencimiento = data.get('fecha_vencimiento')
        dias_credito = data.get('dias_credito')
        porcentaje_retencion = float(data.get('porcentaje_retencion', 3.00))
        monto_retenido = float(data.get('monto_retenido', 0))
        monto_a_pagar = float(data.get('monto_a_pagar', 0))
        obs_retencion = data.get('obs_retencion')

        # Condición de pago (pedido de Erika 19/10/2026): la que se elige en la factura; si viene vacía, la del
        # PV de origen, luego la de la guía (su PV) y al final la del cliente. Nunca la de la cotización.
        pc_origen = _pc_de_comprobante(data)
        items_json = _completar_desc_cliente(items_json, pc_origen.get('numero') if pc_origen else None)
        # 24/10/2026 (Erika): factura en dólares -> TC SUNAT de la fecha de emisión (lo usa el registro de ventas)
        try:
            asegurar_moneda()
            asegurar_migo()
            moneda_comp, tc_comp = moneda_documento(
                data, fecha=str(data.get('fecha_emision') or '')[:10] or None,
                respaldo=pc_origen, tc_sunat_por_defecto=True)
        except ErrorMoneda as em:
            return jsonify({'success': False, 'error': str(em)}), 400
        # REGLA (Erika 26/10/2026): la condición es FIJA, la del PV (Pedido de venta) interno; sin PV, la de la
        # ficha del cliente. Nadie la cambia (para que nadie ponga 6 meses), solo Erika, y queda en auditoría.
        condicion_pedida = normalizar_condicion(data.get('condicion') or data.get('condicion_pago'))
        condicion_fija, fuente_condicion = condicion_fija_factura(pc_origen, data.get('ruc'))
        cambio_condicion_erika = None
        if condicion_fija:
            condicion_pago = condicion_fija
            if condicion_pedida and condicion_pedida != condicion_fija:
                from utils import es_duena_reportes
                if es_duena_reportes():
                    condicion_pago = condicion_pedida
                    cambio_condicion_erika = (condicion_fija, condicion_pedida, fuente_condicion)
        else:
            condicion_pago = condicion_pedida or 'Contado'
        dias_condicion = dias_de_condicion(condicion_pago)
        if dias_condicion > 0:
            es_credito = True
            dias_credito = dias_condicion
        elif condicion_pago == 'Contado':
            es_credito = False
            dias_credito = None
        
        # 🔽 NUEVO CAMPO: ORDEN DE COMPRA MANUAL (si no se escribe, sale de la PV: N° PC (Pedido del cliente))
        orden_compra_cliente = data.get('orden_compra_cliente', '') or ''
        if not orden_compra_cliente and pc_origen:
            orden_compra_cliente = pc_origen.get('oc_cliente') or ''
        
        # ============================================================
        # 🔽 VALIDACIONES DE FACTURACIÓN (cliente, documento, importes, IGV)
        # ============================================================
        tipo_comp = (data.get('tipo') or 'FACTURA').strip()
        ruc_cliente = (data.get('ruc') or '').strip()
        if not (data.get('cliente') or '').strip():
            return jsonify({'success': False, 'error': 'El nombre o razón social del cliente es obligatorio'}), 400
        if tipo_comp.upper() in ('FACTURA', '01') and not (len(ruc_cliente) == 11 and ruc_cliente.isdigit()):
            return jsonify({'success': False, 'error': 'Para una factura el RUC del cliente debe tener 11 dígitos'}), 400

        # Importes: total = subtotal + IGV (18%). Si el navegador envía valores inconsistentes,
        # se recalculan a partir del total para que el comprobante siempre cuadre.
        total_dec = redondear(data.get('total', data.get('monto', 0)))
        subtotal_dec = redondear(data.get('subtotal', 0))
        igv_dec = redondear(data.get('igv', 0))
        if total_dec <= 0:
            # Si no se envió total pero sí items, se calcula desde los items
            lineas = [{'cantidad': it.get('cantidad'), 'precio': it.get('valorVenta', it.get('precio_unitario', 0))}
                      for it in (items_json or []) if isinstance(it, dict)]
            if lineas:
                t = calcular_totales(lineas)
                subtotal_dec, igv_dec, total_dec = t['subtotal'], t['igv'], t['total']
        if total_dec <= 0:
            return jsonify({'success': False, 'error': 'El monto total del comprobante debe ser mayor a 0'}), 400
        igv_esperado = redondear(subtotal_dec * tasa_igv())
        if not totales_consistentes(subtotal_dec, igv_dec, total_dec) or abs(igv_dec - igv_esperado) > a_decimal('0.05'):
            subtotal_dec = redondear(total_dec / (1 + tasa_igv()))
            igv_dec = total_dec - subtotal_dec

        # Calcular totales
        monto_total = float(total_dec)
        subtotal = float(subtotal_dec)
        igv = float(igv_dec)
        
        # ============================================================
        # 🔽 OBTENER FECHA Y HORA ACTUAL CORRECTA
        # ============================================================
        from datetime import datetime
        fecha_emision = datetime.now().isoformat()
        print(f"📅 Fecha emisión guardando: {fecha_emision}")
        
        # ============================================================
        # 🔽 VALIDAR Y RECALCULAR LA RETENCIÓN
        # ============================================================
        # REGLA (Erika 26/10/2026): la retención es SOLO retención y nadie la escribe a mano. El % es 3 (solo Erika
        # lo cambia), el retenido y el monto a pagar se calculan y la observación se arma sola. Estado de crédito,
        # fecha de aprobación, vencimiento y días ya no vienen del formulario: salen de la condición fija del PV.
        from utils import es_duena_reportes
        if not es_duena_reportes():
            porcentaje_retencion = 3.00
        porcentaje_retencion = min(max(float(porcentaje_retencion or 0), 0.0), 100.0)
        estado_credito = None
        fecha_aprobacion = None
        if tiene_retencion and monto_total > 700:
            monto_retenido = round(monto_total * porcentaje_retencion / 100, 2)
            monto_a_pagar = round(monto_total - monto_retenido, 2)
            pct_txt = f'{porcentaje_retencion:.2f}'.rstrip('0').rstrip('.')
            obs_retencion = (f'Retención del {pct_txt}% del IGV: monto S/ {monto_total:.2f}, '
                             f'retenido S/ {monto_retenido:.2f}, a pagar S/ {monto_a_pagar:.2f}.')
        else:
            if tiene_retencion:
                estado_credito = 'No aplica (monto < S/ 700)'
            tiene_retencion = False
            monto_retenido = 0
            monto_a_pagar = monto_total
            obs_retencion = None
        # Vencimiento = emisión + días de la condición fija (nadie lo edita)
        from datetime import timedelta
        if es_credito and dias_credito:
            fecha_vencimiento = (datetime.now() + timedelta(days=int(dias_credito))).date().isoformat()
        else:
            fecha_vencimiento = None
        
        # Preparar datos para guardar
        comprobante_data = {
            'tipo_comprobante': data.get('tipo', 'FACTURA'),
            'serie': str(data.get('serie') or 'E001').strip().upper(),  # serie electrónica de SUNAT (Erika 25/10/2026)
            'numero': data.get('numero'),
            'fecha_emision': data.get('fecha_emision') or datetime.now().isoformat(), 
            'moneda': moneda_comp,
            'cliente_tipo_doc': data.get('cliente_tipo_doc', 'RUC'),
            'cliente_numero_doc': data.get('ruc'),
            'cliente_nombre': data.get('cliente'),
            'cliente_direccion': data.get('direccion') or '',
            'cliente_email': data.get('email') or '',
            'cliente_telefono': data.get('telefono') or '',
            'subtotal': subtotal,
            'igv': igv,
            'total': monto_total,
            'items_json': json.dumps(items_json),
            'observaciones': mayuscula_inicial(data.get('observaciones', '')),
            'estado_sunat': data.get('estado', 'BORRADOR'),
            'condicion_pago': condicion_pago,
            'documento_asociado': data.get('cotizacion') or data.get('cotizacion_numero') or '',
            'guia_vinculada': data.get('guia') or '',
            'pc_vinculado': data.get('pc') or '',
            # 🔽 NUEVO CAMPO: ORDEN DE COMPRA MANUAL
            'orden_compra_cliente': orden_compra_cliente,
            # 🔽 CAMPOS DE RETENCIÓN
            'tiene_retencion': tiene_retencion,
            'es_credito': es_credito,
            'estado_credito': estado_credito,
            'fecha_aprobacion': fecha_aprobacion,
            'fecha_vencimiento': fecha_vencimiento,
            'dias_credito': dias_credito,
            'porcentaje_retencion': porcentaje_retencion,
            'monto_retenido': monto_retenido,
            'monto_a_pagar': monto_a_pagar,
            'obs_retencion': obs_retencion,
            'creado_por': usuario_id
        }

        # El número del comprobante es solo dígitos (en Supabase la columna es numérica)
        numero_txt = str(comprobante_data['numero'] or '').strip()
        if numero_txt and not numero_txt.isdigit():
            return jsonify({'success': False, 'error': 'El número del comprobante solo debe tener dígitos (sin la serie).'}), 400
        comprobante_data['numero'] = numero_txt.zfill(8) if numero_txt else None
        
        # ============================================================
        # SI TIENE ID, ACTUALIZAR
        # ============================================================
        if data.get('id'):
            actual = db_query("SELECT estado_sunat, tipo_comprobante, serie, numero FROM comprobantes WHERE id = %s", (data['id'],))
            if not actual:
                return jsonify({'success': False, 'error': 'Comprobante no encontrado'}), 404
            estado_previo = (actual[0].get('estado_sunat') or '').upper()
            if estado_previo in ('EMITIDO', 'ENVIADO', 'ACEPTADO', 'PAGADO', 'ANULADO'):
                return jsonify({'success': False,
                                'error': f'El comprobante está "{actual[0].get("estado_sunat")}" y ya no se puede modificar. '
                                         f'Para corregirlo emite una nota de crédito.'}), 409
            if not comprobante_data['numero']:
                comprobante_data['numero'] = actual[0].get('numero')
            if comprobante_data['numero'] and db_query(
                    "SELECT 1 FROM comprobantes WHERE tipo_comprobante = %s AND serie = %s "
                    "AND NULLIF(regexp_replace(numero::text, '\\D', '', 'g'), '')::bigint = %s::bigint AND id <> %s",
                    (comprobante_data['tipo_comprobante'], comprobante_data['serie'], comprobante_data['numero'], data['id'])):
                return jsonify({'success': False, 'error': f"Ya existe el comprobante {comprobante_data['serie']}-{comprobante_data['numero']}"}), 409
            query = """
                UPDATE comprobantes SET
                    tipo_comprobante = %s, serie = %s, numero = %s,
                    fecha_emision = %s, moneda = %s,
                    cliente_tipo_doc = %s, cliente_numero_doc = %s,
                    cliente_nombre = %s, cliente_direccion = %s,
                    cliente_email = %s, cliente_telefono = %s,
                    subtotal = %s, igv = %s, total = %s,
                    items_json = %s, observaciones = %s,
                    estado_sunat = %s, condicion_pago = %s,
                    documento_asociado = %s, guia_vinculada = %s,
                    pc_vinculado = %s,
                    -- 🔽 NUEVO CAMPO: ORDEN DE COMPRA MANUAL
                    orden_compra_cliente = %s,
                    tiene_retencion = %s, es_credito = %s,
                    estado_credito = %s, fecha_aprobacion = %s,
                    fecha_vencimiento = %s, dias_credito = %s,
                    porcentaje_retencion = %s, monto_retenido = %s,
                    monto_a_pagar = %s, obs_retencion = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING id, serie, numero
            """
            params = (
                comprobante_data['tipo_comprobante'],
                comprobante_data['serie'],
                comprobante_data['numero'],
                comprobante_data['fecha_emision'],
                comprobante_data['moneda'],
                comprobante_data['cliente_tipo_doc'],
                comprobante_data['cliente_numero_doc'],
                comprobante_data['cliente_nombre'],
                comprobante_data['cliente_direccion'],
                comprobante_data['cliente_email'],
                comprobante_data['cliente_telefono'],
                comprobante_data['subtotal'],
                comprobante_data['igv'],
                comprobante_data['total'],
                comprobante_data['items_json'],
                comprobante_data['observaciones'],
                comprobante_data['estado_sunat'],
                comprobante_data['condicion_pago'],
                comprobante_data['documento_asociado'],
                comprobante_data['guia_vinculada'],
                comprobante_data['pc_vinculado'],
                # 🔽 ORDEN DE COMPRA MANUAL
                comprobante_data['orden_compra_cliente'],
                comprobante_data['tiene_retencion'],
                comprobante_data['es_credito'],
                comprobante_data['estado_credito'],
                comprobante_data['fecha_aprobacion'],
                comprobante_data['fecha_vencimiento'],
                comprobante_data['dias_credito'],
                comprobante_data['porcentaje_retencion'],
                comprobante_data['monto_retenido'],
                comprobante_data['monto_a_pagar'],
                comprobante_data['obs_retencion'],
                data['id']
            )
            result = db_query(query, params)
            
            if result:
                db_execute("UPDATE comprobantes SET tipo_cambio = %s WHERE id = %s", (tc_comp, data['id']))
                if 'numero_migo' in data:
                    guardar_numero_migo(data['id'], data.get('numero_migo'))
                _auditar_cambio_condicion(cambio_condicion_erika, result[0])
                return jsonify({'success': True, 'message': 'Comprobante actualizado', 'data': _numero_8(result[0])})
            return jsonify({'success': False, 'error': 'No se pudo actualizar'}), 400
        
        # ============================================================
        # CREAR NUEVO COMPROBANTE
        # ============================================================
        numero_enviado = str(comprobante_data['numero'] or '').strip()
        # No se repite una factura de la misma guía o PV (pedido de Erika 20/10/2026 22:54)
        duplicada = _factura_duplicada(data, pc_origen)
        if duplicada:
            return jsonify({'success': False, 'codigo': 'duplicado', 'titulo': 'FACTURA DUPLICADA: NO SE CREÓ', 'error': duplicada}), 409
        # La factura queda en la empresa de su guía / PV / cotización (o la elegida arriba).
        # La numeración es por empresa: cada RUC tiene su propia serie F001.
        empresa_comp = empresa_para_crear(
            empresa_de(None, 'guias_remision', "serie || '-' || numero", comprobante_data.get('guia_vinculada'))
            or empresa_de(None, 'pedido_compra_pc', 'numero', comprobante_data.get('pc_vinculado'))
            or empresa_de(None, 'cotizaciones', 'numero_cotizacion', comprobante_data.get('documento_asociado')))
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            # Numeración correlativa por tipo y serie, sin duplicados aunque se guarde en simultáneo
            bloquear_numeracion(cur, f"comprobantes:{comprobante_data['tipo_comprobante']}:{comprobante_data['serie']}")
            if numero_enviado:
                cur.execute("SELECT 1 FROM comprobantes WHERE tipo_comprobante = %s AND serie = %s "
                            "AND NULLIF(regexp_replace(numero::text, '\\D', '', 'g'), '')::bigint = %s::bigint "
                            "AND empresa_id IS NOT DISTINCT FROM %s",
                            (comprobante_data['tipo_comprobante'], comprobante_data['serie'], numero_enviado, empresa_comp))
                if cur.fetchone():
                    return jsonify({'success': False,
                                    'error': f"Ya existe el comprobante {comprobante_data['serie']}-{numero_enviado}. "
                                             f"Deja el número vacío para asignar el siguiente automáticamente."}), 409
                comprobante_data['numero'] = numero_enviado
            else:
                cur.execute("""
                    SELECT COALESCE(MAX(NULLIF(regexp_replace(numero::text, '\\D', '', 'g'), '')::bigint), 0) + 1 AS siguiente
                    FROM comprobantes WHERE tipo_comprobante = %s AND serie = %s AND empresa_id IS NOT DISTINCT FROM %s
                """, (comprobante_data['tipo_comprobante'], comprobante_data['serie'], empresa_comp))
                comprobante_data['numero'] = str(con_piso(
                    cur, 'COMPROBANTE', clave_comprobante(comprobante_data['tipo_comprobante'], empresa_comp,
                                                          comprobante_data['serie']),
                    cur.fetchone()['siguiente'])).zfill(8)
            cur.execute(_SQL_INSERT_COMPROBANTE, _params_insert_comprobante(comprobante_data))
            fila = cur.fetchone()
            if fila:
                marcar_empresa(cur, 'comprobantes', fila['id'], empresa_comp)
                cur.execute("UPDATE comprobantes SET tipo_cambio = %s WHERE id = %s", (tc_comp, fila['id']))
                if 'numero_migo' in data:
                    cur.execute("UPDATE comprobantes SET numero_migo = %s WHERE id = %s",
                                (limpiar_migo(data.get('numero_migo')), fila['id']))
        result = [_numero_8(dict(fila))] if fila else []
        if result:
            _auditar_cambio_condicion(cambio_condicion_erika, result[0])
            return jsonify({
                'success': True,
                'message': 'Comprobante creado correctamente',
                'data': result[0]
            })
        return jsonify({'success': False, 'error': 'No se pudo crear'}), 400
        
    except Exception as e:
        print(f"❌ Error en api_comprobantes_guardar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@ventas_bp.route('/ventas/api/comprobantes/<int:id>', methods=['GET'])
@login_required
def api_comprobantes_obtener(id):
    """Obtiene un comprobante específico por su ID"""
    try:
        print(f"🔍 Buscando comprobante ID: {id}")
        
        query = """
            SELECT 
                id, tipo_comprobante, serie, numero, fecha_emision,
                moneda, cliente_tipo_doc, cliente_numero_doc,
                cliente_nombre, cliente_direccion, cliente_email,
                cliente_telefono, subtotal, igv, total,
                items_json, observaciones, estado_sunat,
                condicion_pago, documento_asociado, guia_vinculada,
                pc_vinculado, 
                -- 🔽 NUEVO CAMPO
                orden_compra_cliente,
                tiene_retencion, 
                es_credito, estado_credito, fecha_aprobacion,
                fecha_vencimiento, dias_credito, 
                porcentaje_retencion, monto_retenido, monto_a_pagar,
                obs_retencion, numero_migo,
                sunat_response, cdr_response, creado_por,
                created_at, updated_at
            FROM comprobantes
            WHERE id = %s
        """
        asegurar_migo()
        result = db_query(query, (id,))
        
        print(f"📊 Resultado de consulta: {result}")
        
        if not result:
            print(f"❌ No se encontró comprobante con ID: {id}")
            return jsonify({'success': False, 'error': 'Comprobante no encontrado'}), 404
        
        if not isinstance(result, list) or len(result) == 0:
            print(f"❌ Resultado vacío o no es lista: {type(result)}")
            return jsonify({'success': False, 'error': 'Comprobante no encontrado'}), 404
        
        comp = result[0]
        
        if not isinstance(comp, dict):
            print(f"⚠️ Resultado no es un diccionario: {type(comp)}")
            if isinstance(comp, (tuple, list)):
                columns = [
                    'id', 'tipo_comprobante', 'serie', 'numero', 'fecha_emision',
                    'moneda', 'cliente_tipo_doc', 'cliente_numero_doc',
                    'cliente_nombre', 'cliente_direccion', 'cliente_email',
                    'cliente_telefono', 'subtotal', 'igv', 'total',
                    'items_json', 'observaciones', 'estado_sunat',
                    'condicion_pago', 'documento_asociado', 'guia_vinculada',
                    'pc_vinculado', 'orden_compra_cliente',
                    'tiene_retencion', 'es_credito',
                    'estado_credito', 'fecha_aprobacion', 'fecha_vencimiento',
                    'dias_credito', 'porcentaje_retencion', 'monto_retenido',
                    'monto_a_pagar', 'obs_retencion', 'sunat_response',
                    'cdr_response', 'creado_por', 'created_at', 'updated_at'
                ]
                comp = dict(zip(columns, comp))

        # Parsear items_json de forma segura
        try:
            raw_val = comp.get('items_json')
            if raw_val:
                if isinstance(raw_val, str):
                    comp['items_json'] = json.loads(raw_val)
                else:
                    comp['items_json'] = raw_val
            else:
                comp['items_json'] = []
        except Exception as e:
            print(f"⚠️ Error parseando items_json de comprobante: {e}")
            comp['items_json'] = []

        print(f"✅ Comprobante encontrado: ID {comp.get('id')}, Serie {comp.get('serie')}-{comp.get('numero')}")
        return jsonify({'success': True, 'data': comp})
        
    except Exception as e:
        print(f"❌ Error en api_comprobantes_obtener: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@ventas_bp.route('/ventas/api/comprobantes/<int:id>', methods=['DELETE'])
@login_required
def api_comprobantes_eliminar(id):
    try:
        result = actualizar_estado_comprobante_db(id, 'ANULADO')
        if result:
            mensaje = 'Comprobante anulado'
            if result.get('cobros_anulados'):
                mensaje += f". Se anularon {result['cobros_anulados']} cobro(s) en caja"
            return jsonify({'success': True, 'message': mensaje})
        return jsonify({'success': False, 'error': 'No se pudo anular'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



# ============================================================
# COMPROBANTES - ELIMINACIÓN FÍSICA
# ============================================================

@ventas_bp.route('/ventas/api/comprobantes/<int:id>/permanente', methods=['DELETE'])
@login_required
def api_comprobantes_eliminar_permanente(id):
    """Elimina físicamente un comprobante de la base de datos (solo si ya está anulado)"""
    try:
        print(f"🗑️ Eliminando físicamente comprobante ID: {id}")

        query_check = "SELECT id, numero, estado_sunat FROM comprobantes WHERE id = %s"
        result_check = db_query(query_check, (id,))

        if not result_check:
            return jsonify({'success': False, 'error': 'Comprobante no encontrado'}), 404

        estado = (result_check[0].get('estado_sunat') or '').upper()
        if estado not in ('ANULADO', 'ANULADA'):
            return jsonify({
                'success': False,
                'error': f'Solo se pueden eliminar comprobantes en estado "Anulado". Estado actual: {result_check[0].get("estado_sunat")}'
            }), 400

        query_delete = "DELETE FROM comprobantes WHERE id = %s RETURNING id"
        result_delete = db_query(query_delete, (id,))

        if result_delete:
            return jsonify({'success': True, 'message': 'Comprobante eliminado correctamente', 'data': {'id': id}})

        return jsonify({'success': False, 'error': 'No se pudo eliminar el comprobante'}), 400

    except Exception as e:
        print(f"❌ Error en api_comprobantes_eliminar_permanente: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# NOTAS DE CRÉDITO - API
# ============================================================

@ventas_bp.route('/ventas/api/notas-credito/listar', methods=['GET'])
@login_required
def api_notas_credito_listar():
    try:
        data = obtener_notas_credito_db()
        data = filtrar_filas('notas_credito', data)  # solo la empresa elegida arriba
        formatted_data = []
        for row in data:
            formatted_data.append({
                'id': row.get('id'),
                'serie': row.get('serie'),
                'numero': row.get('numero'),
                'fecha': row.get('fecha_emision'),
                'estado': row.get('estado'),
                'ruc': row.get('cliente_numero_doc'),
                'cliente': row.get('cliente_nombre'),
                'comprobante': row.get('comprobante_asociado'),
                'motivo': row.get('motivo'),
                'monto': float(row.get('monto') or 0),
                'observaciones': row.get('observaciones'),
                **_tiempos(row)
            })
        return jsonify({'success': True, 'data': formatted_data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@ventas_bp.route('/ventas/api/notas-credito/guardar', methods=['POST'])
@login_required
def api_notas_credito_guardar():
    try:
        data = request.get_json()
        usuario_id = session.get('usuario_id')
        data['creado_por'] = usuario_id
        
        monto = a_decimal(data.get('monto'))
        if monto <= 0:
            return jsonify({'success': False, 'error': 'El monto de la nota de crédito debe ser mayor a 0'}), 400
        if not (data.get('motivo') or '').strip():
            return jsonify({'success': False, 'error': 'El motivo de la nota de crédito es obligatorio'}), 400

        # La nota de crédito no puede superar el saldo del comprobante que corrige
        asociado = (data.get('comprobante_asociado') or '').strip()
        empresa_nc = None
        if asociado:
            sql_emp, par_emp = filtro_sql('empresa_id')
            comp = db_query("""
                SELECT id, total, cliente_tipo_doc, cliente_numero_doc, cliente_nombre, empresa_id FROM comprobantes
                WHERE (numero::text = %s OR LPAD(numero::text, 8, '0') = %s
                   OR (serie || '-' || numero::text) = %s
                   OR (serie || '-' || LTRIM(numero::text, '0')) = %s
                   OR (serie || '-' || LPAD(numero::text, 8, '0')) = %s)""" + sql_emp + """
                ORDER BY id DESC LIMIT 1
            """, (asociado,) * 5 + par_emp)
            if comp:
                empresa_nc = comp[0].get('empresa_id')
                # Los datos del cliente salen del comprobante si no vinieron (en Supabase son obligatorios)
                if not str(data.get('cliente_numero_doc') or '').strip():
                    data['cliente_numero_doc'] = comp[0].get('cliente_numero_doc')
                    data['cliente_tipo_doc'] = data.get('cliente_tipo_doc') or comp[0].get('cliente_tipo_doc')
                if not str(data.get('cliente_nombre') or '').strip():
                    data['cliente_nombre'] = comp[0].get('cliente_nombre')
                ya_emitido = db_query("""
                    SELECT COALESCE(SUM(monto), 0) AS total FROM notas_credito
                    WHERE comprobante_asociado = %s AND COALESCE(UPPER(estado), '') NOT IN ('ANULADA', 'ANULADO')
                """, (asociado,))[0]['total']
                saldo = a_decimal(comp[0]['total']) - a_decimal(ya_emitido)
                if monto > saldo + a_decimal('0.01'):
                    return jsonify({'success': False,
                                    'error': f'El monto (S/ {monto:.2f}) supera el saldo del comprobante {asociado} '
                                             f'(S/ {saldo:.2f})'}), 400

        if not str(data.get('cliente_numero_doc') or '').strip() or not str(data.get('cliente_nombre') or '').strip():
            return jsonify({'success': False, 'error': 'Indica el cliente y su RUC o DNI, o el comprobante que corrige.'}), 400

        if not str(data.get('numero') or '').strip():
            with db_tx() as conn:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                data['numero'] = _siguiente_numero(cur, 'notas_credito', data.get('serie') or 'FC01')
        
        empresa_nc = empresa_para_crear(empresa_nc)   # la de la factura que corrige
        result = guardar_nota_credito_db(data)
        if result:
            marcar_empresa(None, 'notas_credito', result['id'], empresa_nc)
            return jsonify({'success': True, 'message': 'Nota de crédito creada', 'data': result})
        return jsonify({'success': False, 'error': 'No se pudo crear'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# NOTAS DE CRÉDITO - ELIMINACIÓN FÍSICA
# ============================================================

@ventas_bp.route('/ventas/api/notas-credito/<int:id>/permanente', methods=['DELETE'])
@login_required
def api_notas_credito_eliminar_permanente(id):
    """Elimina físicamente una nota de crédito de la base de datos (solo si ya está anulada)"""
    try:
        print(f"🗑️ Eliminando físicamente nota de crédito ID: {id}")

        query_check = "SELECT id, numero, estado FROM notas_credito WHERE id = %s"
        result_check = db_query(query_check, (id,))

        if not result_check:
            return jsonify({'success': False, 'error': 'Nota de crédito no encontrada'}), 404

        estado = (result_check[0].get('estado') or '').lower()
        if estado != 'anulada':
            return jsonify({
                'success': False,
                'error': f'Solo se pueden eliminar notas de crédito en estado "Anulada". Estado actual: {result_check[0].get("estado")}'
            }), 400

        query_delete = "DELETE FROM notas_credito WHERE id = %s RETURNING id"
        result_delete = db_query(query_delete, (id,))

        if result_delete:
            return jsonify({'success': True, 'message': 'Nota de crédito eliminada correctamente', 'data': {'id': id}})

        return jsonify({'success': False, 'error': 'No se pudo eliminar la nota de crédito'}), 400

    except Exception as e:
        print(f"❌ Error en api_notas_credito_eliminar_permanente: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# PEDIDO COMPRA (PV) - API
# ============================================================

@ventas_bp.route('/ventas/api/pedido-compra/listar', methods=['GET'])
@login_required
def api_pedido_compra_listar():
    try:
        data = obtener_pc_db()
        data = filtrar_filas('pedido_compra_pc', data)  # solo la empresa elegida arriba
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

_OC_CLIENTE_LISTA = False


def _asegurar_columna_oc_cliente():
    """N° de la orden de compra del cliente en la PV (migración 011; aquí por si la base aún no la tiene)."""
    global _OC_CLIENTE_LISTA
    if not _OC_CLIENTE_LISTA:
        if not db_query("""SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'pedido_compra_pc' AND column_name = 'oc_cliente'"""):
            db_execute("ALTER TABLE pedido_compra_pc ADD COLUMN IF NOT EXISTS oc_cliente VARCHAR(60)")
        _OC_CLIENTE_LISTA = True


@ventas_bp.route('/ventas/api/pedido-compra/guardar', methods=['POST'])
@login_required
def api_pedido_compra_guardar():
    try:
        data = request.get_json()
        usuario_id = session.get('usuario_id')
        data['creado_por'] = usuario_id

        # Condición de pago: SIEMPRE la escribe la persona leyendo la PC (Pedido del cliente) (pedido de Erika 19/10/2026).
        # No se copia de la cotización: el cliente cotizado a 7 días a veces manda su OC a 120 días.
        condicion = normalizar_condicion(data.get('condicion_pago') or data.get('condicion_atencion'))
        if not condicion:
            return jsonify({'success': False, 'codigo': 'falta_condicion',
                            'error': 'Elige la condición de pago leyendo la orden de compra del cliente '
                                     '(no se copia de la cotización).'}), 400
        data['condicion_pago'] = data['condicion_atencion'] = condicion
        if 'oc_cliente' in data:
            data['oc_cliente'] = str(data.get('oc_cliente') or '').strip()[:60]
        
        print("=" * 80)
        print("📦 API PEDIDO COMPRA GUARDAR")
        print(f"  - ID: {data.get('id')}")
        print(f"  - Número: {data.get('numero')}")
        print(f"  - Cliente: {data.get('cliente')}")
        print(f"  - Estado: {data.get('estado')}")
        print(f"  - Items: {len(data.get('items', []))}")
        print(f"  - Cotización ID: {data.get('cotizacion_id')}")
        print("=" * 80)
        
        # ============================================================
        # SI HAY ID, ES EDICIÓN - VERIFICAR QUE EXISTA
        # ============================================================
        pc_id = data.get('id')
        if pc_id:
            check_query = "SELECT id, numero FROM pedido_compra_pc WHERE id = %s"
            check_result = db_query(check_query, (pc_id,))
            
            if not check_result:
                return jsonify({'success': False, 'error': f'PV con ID {pc_id} no encontrado'}), 404
            
            print(f"✅ PV existente encontrado: {check_result[0]['numero']}")
        
        # ============================================================
        # SI VIENE DE UNA COTIZACIÓN, OBTENER DATOS ADICIONALES
        # ============================================================
        cotizacion_id = data.get('cotizacion_id')
        cotizacion_numero = data.get('cotizacion_numero')
        
        # Si no hay cotizacion_id pero hay cotizacion_numero, buscar el ID
        if not cotizacion_id and cotizacion_numero and cotizacion_numero != 'SIN COTIZACIÓN':
            try:
                cot_query = """
                    SELECT id FROM cotizaciones 
                    WHERE numero_cotizacion = %s OR codigo_cotizacion = %s
                    LIMIT 1
                """
                cot_result = db_query(cot_query, (cotizacion_numero, cotizacion_numero))
                if cot_result:
                    cotizacion_id = cot_result[0]['id']
                    data['cotizacion_id'] = cotizacion_id
                    print(f"✅ Cotización encontrada por número: {cotizacion_numero} -> ID: {cotizacion_id}")
            except Exception as e:
                print(f"⚠️ Error buscando cotización por número: {e}")
        
        advertencia = None
        if cotizacion_id and not pc_id:
            estado_cot = db_query("SELECT estado FROM cotizaciones WHERE id = %s", (cotizacion_id,))
            if not estado_cot:
                return jsonify({'success': False, 'error': 'La cotización vinculada no existe'}), 400
            estado_cot = estado_cot[0]['estado'] or ''
            if estado_cot in ('Anulada', 'Rechazada'):
                return jsonify({'success': False,
                                'error': f'No se puede registrar un PV sobre una cotización "{estado_cot}"'}), 409
            if estado_cot in ('Borrador', 'En revisión', 'Por validar') and _requiere_validacion_previa():
                return jsonify({'success': False,
                                'error': f'La cotización está en "{estado_cot}". Debe validarse/generarse antes de registrar el pedido del cliente.'}), 409
            previos = db_query("""SELECT numero FROM pedido_compra_pc
                                  WHERE cotizacion_id = %s AND COALESCE(estado, '') NOT IN ('Anulado', 'Anulada')""",
                               (cotizacion_id,))
            if previos:
                advertencia = ('Atención: esta cotización ya tiene el/los PV ' +
                               ', '.join(p['numero'] or '' for p in previos) +
                               '. Verifica que no sea un pedido duplicado.')

        if cotizacion_id and not pc_id:  # Solo si es nuevo
            cot_query = """
                SELECT 
                    c.id, c.numero_cotizacion, c.fecha_creacion,
                    c.condicion_pago, c.direccion_entrega, c.tiempo_entrega,
                    c.vendedor, c.total,
                    cl.razon_social as cliente_razon_social,
                    cl.numero_documento as cliente_ruc,
                    cl.nombre_contacto as cliente_contacto
                FROM cotizaciones c
                LEFT JOIN clientes cl ON cl.id = c.cliente_id::integer
                WHERE c.id = %s
            """
            cot_data = db_query(cot_query, (cotizacion_id,))
            if cot_data:
                cot = cot_data[0]
                if not data.get('cliente'):
                    data['cliente'] = cot.get('cliente_razon_social')
                if not data.get('ruc'):
                    data['ruc'] = cot.get('cliente_ruc')
                if not data.get('cotizacion_numero'):
                    data['cotizacion_numero'] = cot.get('numero_cotizacion')
                if not data.get('lugar_entrega'):
                    data['lugar_entrega'] = cot.get('direccion_entrega')

                if 'monto' not in data or not data['monto']:
                 data['monto'] = 0.0
        
        # ============================================================
        # GENERAR NÚMERO SI ES NUEVO Y NO TIENE
        # ============================================================
        if not pc_id and data.get('numero') and db_query("SELECT 1 FROM pedido_compra_pc WHERE numero = %s", (data['numero'],)):
            print(f"⚠️ Número de PV {data['numero']} ya existe; se asigna uno nuevo")
            data['numero'] = None
        if not pc_id and not data.get('numero'):
            # N° interno correlativo por empresa: PC-KCF-000001, PC-AGD-000001... (pedido de Erika 19/10/2026).
            # El número de la PC (Pedido del cliente) (Komatsu: IT40...) va aparte en oc_cliente. Las PV antiguas no se renumeran.
            empresa_pc = empresa_para_crear(empresa_de(None, 'cotizaciones', 'id', cotizacion_id)
                                            or empresa_de(None, 'cotizaciones', 'numero_cotizacion', cotizacion_numero))
            codigo_emp = ((empresa_por_id(empresa_pc) or {}).get('codigo') or 'KCF').upper()
            prefijo = f"PV-{codigo_emp}-"  # PV = Pedido de venta (Erika 26/10/2026)
            data['numero'] = prefijo   # guardar_pc_db pone el correlativo dentro de la transacción
        
        # Fecha si no tiene
        if not data.get('fecha'):
            data['fecha'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # ============================================================
        # GUARDAR EL PV (INSERT O UPDATE)
        # ============================================================
        # 24/10/2026 (Erika): el PV lleva la moneda y el TC de su cotización (o los que se escriban en el PV)
        try:
            asegurar_moneda()
            cot_m = db_query("SELECT moneda, tipo_cambio FROM cotizaciones WHERE id = %s", (cotizacion_id,)) if cotizacion_id else []
            moneda_pc = moneda_documento(data, respaldo=cot_m[0] if cot_m else None)
        except ErrorMoneda as em:
            return jsonify({'success': False, 'error': str(em)}), 400
        result = guardar_pc_db(data)
        
        if result and 'valida_productos' in data:
            try:
                db_query("UPDATE pedido_compra_pc SET valida_productos = %s WHERE id = %s RETURNING id",
                         (bool(data.get('valida_productos')), result['id']))
            except Exception as e:
                print(f"⚠️ No se pudo guardar valida_productos: {e}")

        if result and 'oc_cliente' in data:
            _asegurar_columna_oc_cliente()
            db_execute("UPDATE pedido_compra_pc SET oc_cliente = %s WHERE id = %s",
                       (data['oc_cliente'] or None, result['id']))

        if result:
            # 24/10/2026 (Erika): el PV lleva la moneda y el TC de su cotización (o los que se escriban en el PV)
            db_execute("UPDATE pedido_compra_pc SET moneda = %s, tipo_cambio = %s WHERE id = %s", moneda_pc + (result['id'],))

        if result:
            # Si tiene cotizacion_id y es NUEVO, actualizar estado de la cotización
            if cotizacion_id and not pc_id:
                try:
                    update_cot = """
                        UPDATE cotizaciones 
                        SET estado = 'Aceptada por Cliente', 
                            updated_at = NOW()
                        WHERE id = %s
                        RETURNING id
                    """
                    db_query(update_cot, (cotizacion_id,))
                except Exception as e:
                    print(f"⚠️ No se pudo actualizar estado de cotización: {e}")
            
            return jsonify({
                'success': True, 
                'message': 'PV guardado correctamente', 
                'data': result,
                'advertencia': advertencia
            })
        
        return jsonify({'success': False, 'error': 'No se pudo guardar'}), 400
            
    except Exception as e:
        print(f"❌ Error en api_pedido_compra_guardar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

_cita_lista = False


def _asegurar_fecha_cita():
    """Columna "Fecha de cita del cliente" en despachos (migración 013; en la base de pruebas se crea aquí)."""
    global _cita_lista
    if _cita_lista:
        return
    if not db_query("SELECT 1 FROM information_schema.columns WHERE table_name = 'despachos' AND column_name = 'fecha_cita'"):
        with db_tx() as conn:
            conn.cursor().execute("ALTER TABLE despachos ADD COLUMN IF NOT EXISTS fecha_cita TIMESTAMP")
    _cita_lista = True


@ventas_bp.route('/ventas/api/despachos/<int:did>/cita', methods=['POST'])
@login_required
def api_despacho_cita(did):
    """Pone o cambia la fecha de la cita con el cliente para la entrega (solo fecha, sin hora). Vacío la quita."""
    try:
        _asegurar_fecha_cita()
        texto = str((request.get_json(silent=True) or {}).get('fecha_cita') or '').strip()
        nueva = None
        if texto:
            try:
                nueva = datetime.fromisoformat(texto.replace('Z', '')[:10])
            except ValueError:
                return jsonify({'success': False, 'error': 'Fecha de cita no válida'}), 400
        antes = db_query("SELECT id, numero, fecha_cita FROM despachos WHERE id = %s", (did,))
        if not antes:
            return jsonify({'success': False, 'error': 'Despacho no encontrado'}), 404
        db_execute("UPDATE despachos SET fecha_cita = %s, updated_at = NOW() WHERE id = %s", (nueva, did))
        from routes.auditoria import registrar_auditoria
        registrar_auditoria('ACTUALIZAR', 'Ventas', 'despachos', did,
                            antes={'fecha_cita': antes[0].get('fecha_cita')}, despues={'fecha_cita': nueva},
                            detalle=f"Fecha de cita del despacho {antes[0].get('numero') or did}: "
                                    f"{nueva.strftime('%d/%m/%Y') if nueva else 'sin cita'}")
        return jsonify({'success': True, 'data': {'id': did, 'fecha_cita': nueva.strftime('%Y-%m-%d') if nueva else None}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ---------- Entregas: distrito y comentario en la fila (Erika 23/10/2026 04:35: "aqui es un si") ----------
_entrega_cols_listas = False

# Distritos de Lima Metropolitana y Callao, con el nombre que se muestra en pantalla
DISTRITOS_LIMA = [
    'Ancón', 'Ate', 'Barranco', 'Breña', 'Carabayllo', 'Cercado de Lima', 'Chaclacayo', 'Chorrillos', 'Cieneguilla',
    'Comas', 'El Agustino', 'Independencia', 'Jesús María', 'La Molina', 'La Victoria', 'Lince', 'Los Olivos',
    'Lurigancho', 'Lurín', 'Magdalena del Mar', 'Miraflores', 'Pachacámac', 'Pucusana', 'Pueblo Libre',
    'Puente Piedra', 'Punta Hermosa', 'Punta Negra', 'Rímac', 'San Bartolo', 'San Borja', 'San Isidro',
    'San Juan de Lurigancho', 'San Juan de Miraflores', 'San Luis', 'San Martín de Porres', 'San Miguel',
    'Santa Anita', 'Santa María del Mar', 'Santa Rosa', 'Santiago de Surco', 'Surquillo', 'Villa El Salvador',
    'Villa María del Triunfo', 'Callao', 'Bellavista', 'Carmen de la Legua Reynoso', 'La Perla', 'La Punta',
    'Mi Perú', 'Ventanilla',
]
_ALIAS_DISTRITO = {
    'SMP': 'San Martín de Porres', 'S.M.P.': 'San Martín de Porres', 'CERCADO': 'Cercado de Lima',
    'LIMA CERCADO': 'Cercado de Lima', 'SURCO': 'Santiago de Surco', 'SJL': 'San Juan de Lurigancho',
    'SJM': 'San Juan de Miraflores', 'VES': 'Villa El Salvador', 'VMT': 'Villa María del Triunfo',
    'MAGDALENA': 'Magdalena del Mar', 'CHOSICA': 'Lurigancho',
}


def _sin_tildes(texto):
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFD', str(texto or '').upper()) if unicodedata.category(c) != 'Mn')


_MAPA_DISTRITO = {_sin_tildes(d): d for d in DISTRITOS_LIMA}
_MAPA_DISTRITO.update({_sin_tildes(a): d for a, d in _ALIAS_DISTRITO.items()})
_RE_DISTRITO = re.compile(r'(?<![A-Z0-9])(' + '|'.join(re.escape(k) for k in sorted(_MAPA_DISTRITO, key=len, reverse=True)) + r')(?![A-Z0-9])')


def adivinar_distrito(direccion):
    """Saca el distrito del texto de la dirección. El distrito suele ir al final, así que gana el último que aparece
    (en "AV. INDEPENDENCIA 123 - SAN ISIDRO" es San Isidro). Si no hay ninguno, devuelve ''."""
    halla = list(_RE_DISTRITO.finditer(_sin_tildes(direccion)))
    return _MAPA_DISTRITO[halla[-1].group(1)] if halla else ''


def _asegurar_columnas_entrega():
    """Columnas distrito y comentario (migración 028) y fechas de salida, entrega real y rechazo (migración 032)
    en despachos; en la base de pruebas se crean aquí."""
    global _entrega_cols_listas
    if _entrega_cols_listas:
        return
    hay = {r['column_name'] for r in db_query(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'despachos' "
        "AND column_name IN ('distrito', 'comentario', 'fecha_salida', 'fecha_entrega_real', 'motivo_rechazo', 'fecha_rechazo')")}
    if len(hay) < 6:
        with db_tx() as conn:
            cur = conn.cursor()
            cur.execute("ALTER TABLE despachos ADD COLUMN IF NOT EXISTS distrito VARCHAR(80)")
            cur.execute("ALTER TABLE despachos ADD COLUMN IF NOT EXISTS comentario VARCHAR(200)")
            cur.execute("ALTER TABLE despachos ADD COLUMN IF NOT EXISTS fecha_salida TIMESTAMP")
            cur.execute("ALTER TABLE despachos ADD COLUMN IF NOT EXISTS fecha_entrega_real DATE")
            cur.execute("ALTER TABLE despachos ADD COLUMN IF NOT EXISTS motivo_rechazo VARCHAR(200)")
            cur.execute("ALTER TABLE despachos ADD COLUMN IF NOT EXISTS fecha_rechazo TIMESTAMP")
    _entrega_cols_listas = True


ESTADO_RECHAZADO = 'Rechazado por el cliente'
MOTIVO_RECHAZO_MAX = 200


@ventas_bp.route('/ventas/api/despachos/<int:did>/entrega', methods=['POST'])
@login_required
def api_despacho_entrega(did):
    """Después de "Despachado" (salió del almacén), Erika 26/10/2026:
    - accion 'entregar': fecha real en que el cliente recibió → "Entregado". Con la fecha vacía vuelve a "Despachado".
    - accion 'rechazar': el cliente no lo recibió → "Rechazado por el cliente" con motivo; el stock vuelve al
      inventario y se puede volver a despachar."""
    try:
        _asegurar_columnas_entrega()
        datos = request.get_json(silent=True) or {}
        accion = datos.get('accion')
        filas = db_query("SELECT id, numero, estado, fecha_salida, fecha_entrega_real, motivo_rechazo "
                         "FROM despachos WHERE id = %s", (did,))
        if not filas:
            return jsonify({'success': False, 'error': 'Despacho no encontrado'}), 404
        d = filas[0]
        estado = d.get('estado') or ''
        if estado not in ('Despachado', 'Entregado'):
            return jsonify({'success': False, 'error': 'Primero hay que confirmar el despacho (que salga del almacén).'}), 409
        from routes.auditoria import registrar_auditoria
        numero = d.get('numero') or did
        if accion == 'entregar':
            texto = str(datos.get('fecha_entrega') or '').strip()
            if not texto:
                if estado != 'Entregado':
                    return jsonify({'success': False, 'error': 'Elige la fecha real de entrega'}), 400
                db_execute("UPDATE despachos SET estado = 'Despachado', fecha_entrega_real = NULL, updated_at = NOW() "
                           "WHERE id = %s", (did,))
                registrar_auditoria('ACTUALIZAR', 'Ventas', 'despachos', did,
                                    antes={'estado': estado, 'fecha_entrega_real': d.get('fecha_entrega_real')},
                                    despues={'estado': 'Despachado', 'fecha_entrega_real': None},
                                    detalle=f"Despacho {numero}: se quitó la fecha real de entrega (vuelve a Despachado)")
                return jsonify({'success': True, 'data': {'id': did, 'estado': 'Despachado', 'fecha_entrega_real': None}})
            try:
                fecha = datetime.fromisoformat(texto[:10]).date()
            except ValueError:
                return jsonify({'success': False, 'error': 'Fecha real de entrega no válida'}), 400
            from routes.exportar import ahora_lima
            hoy = ahora_lima().date()
            if fecha > hoy:
                return jsonify({'success': False, 'error': 'La fecha real de entrega no puede ser futura'}), 400
            salida = d.get('fecha_salida')
            if salida and fecha < salida.date():
                return jsonify({'success': False, 'error': f"La entrega no puede ser antes de la salida del almacén "
                                                           f"({salida.strftime('%d/%m/%Y')})"}), 400
            db_execute("UPDATE despachos SET estado = 'Entregado', fecha_entrega_real = %s, updated_at = NOW() "
                       "WHERE id = %s", (fecha, did))
            registrar_auditoria('ACTUALIZAR', 'Ventas', 'despachos', did,
                                antes={'estado': estado, 'fecha_entrega_real': d.get('fecha_entrega_real')},
                                despues={'estado': 'Entregado', 'fecha_entrega_real': fecha},
                                detalle=f"Despacho {numero}: entregado al cliente el {fecha.strftime('%d/%m/%Y')}")
            return jsonify({'success': True, 'data': {'id': did, 'estado': 'Entregado',
                                                      'fecha_entrega_real': fecha.isoformat()}})
        if accion == 'rechazar':
            motivo = re.sub(r'\s+', ' ', str(datos.get('motivo') or '')).strip()
            if not motivo:
                return jsonify({'success': False, 'error': 'Escribe por qué el cliente lo rechazó'}), 400
            if len(motivo) > MOTIVO_RECHAZO_MAX:
                return jsonify({'success': False, 'error': f'El motivo es corto: máximo {MOTIVO_RECHAZO_MAX} letras'}), 400
            from routes.stock_automatico import cambiar_estado_despacho
            respuesta, codigo = cambiar_estado_despacho(did, ESTADO_RECHAZADO, motivo=f'rechazado por el cliente: {motivo}')
            if codigo != 200:
                return jsonify(respuesta), codigo
            db_execute("UPDATE despachos SET motivo_rechazo = %s, fecha_rechazo = (NOW() AT TIME ZONE 'America/Lima'), fecha_entrega_real = NULL "
                       "WHERE id = %s", (motivo, did))
            registrar_auditoria('ACTUALIZAR', 'Ventas', 'despachos', did,
                                antes={'estado': estado}, despues={'estado': ESTADO_RECHAZADO, 'motivo_rechazo': motivo},
                                detalle=f"Despacho {numero}: rechazado por el cliente. Motivo: {motivo}")
            respuesta['message'] = 'Rechazo registrado.' + respuesta.get('message', '').replace(
                f'Despacho actualizado a {ESTADO_RECHAZADO}.', '')
            return jsonify(respuesta), 200
        return jsonify({'success': False, 'error': 'Acción no válida'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


COMENTARIO_ENTREGA_MAX = 120


@ventas_bp.route('/ventas/api/despachos/<int:did>/dato', methods=['POST'])
@login_required
def api_despacho_dato(did):
    """Guarda desde la fila de Entregas el distrito o el comentario corto. Vacío lo borra."""
    try:
        _asegurar_columnas_entrega()
        datos = request.get_json(silent=True) or {}
        campo = datos.get('campo')
        if campo not in ('distrito', 'comentario'):
            return jsonify({'success': False, 'error': 'Solo se puede cambiar el distrito o el comentario'}), 400
        valor = re.sub(r'\s+', ' ', str(datos.get('valor') or '')).strip()
        if campo == 'comentario' and len(valor) > COMENTARIO_ENTREGA_MAX:
            return jsonify({'success': False, 'error': f'El comentario es corto: máximo {COMENTARIO_ENTREGA_MAX} letras '
                                                       f'(tiene {len(valor)})'}), 400
        if campo == 'distrito' and valor:
            valor = adivinar_distrito(valor) or valor[:80]
        antes = db_query(f"SELECT id, numero, {campo} FROM despachos WHERE id = %s", (did,))
        if not antes:
            return jsonify({'success': False, 'error': 'Despacho no encontrado'}), 404
        db_execute(f"UPDATE despachos SET {campo} = %s, updated_at = NOW() WHERE id = %s", (valor or None, did))
        from routes.auditoria import registrar_auditoria
        registrar_auditoria('ACTUALIZAR', 'Ventas', 'despachos', did,
                            antes={campo: antes[0].get(campo)}, despues={campo: valor or None},
                            detalle=f"{'Distrito' if campo == 'distrito' else 'Comentario'} del despacho "
                                    f"{antes[0].get('numero') or did}: {valor or '(vacío)'}")
        return jsonify({'success': True, 'data': {'id': did, campo: valor or None}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@ventas_bp.route('/ventas/api/despachos/listar', methods=['GET'])
@login_required
def api_despachos_listar():
    try:
        print("🚚 API DESPACHOS LISTAR - INICIO")
        _asegurar_fecha_cita()
        _asegurar_columnas_entrega()
        
        query = """
            SELECT 
                d.id, d.numero, d.fecha, d.fecha_despacho, d.estado,
                d.pc_id, d.pc_numero, d.cotizacion_id, d.cotizacion_numero,
                d.cliente, d.ruc, d.comprobante, d.guia, d.origen, d.destino,
                d.transportista, d.observaciones, d.responsable,
                d.items_json, d.created_at, d.updated_at, d.fecha_cita,
                d.distrito, d.comentario, d.fecha_salida, d.fecha_entrega_real, d.motivo_rechazo, d.fecha_rechazo,
                (SELECT to_jsonb(p) ->> 'oc_cliente' FROM pedido_compra_pc p
                  WHERE p.numero = d.pc_numero ORDER BY p.id DESC LIMIT 1) AS oc_cliente
            FROM despachos d
            ORDER BY d.id DESC
        """
        data = db_query(query)
        data = filtrar_filas('despachos', data)  # solo la empresa elegida arriba
        print(f"📊 Despachos encontrados: {len(data) if data else 0}")

        # ============================================================
        # 🔽 BUSCAR GUÍAS Y FACTURAS VINCULADAS POR "cotizacion_numero"
        #     (NO por RUC ni por ID) - últimos 4 registros de cada una
        # ============================================================
        cotizacion_numeros = list({
            row.get('cotizacion_numero') for row in data if row.get('cotizacion_numero')
        })

        guias_por_cotizacion = {}
        comprobantes_por_cotizacion = {}

        if cotizacion_numeros:
            try:
                guias_query = """
                    SELECT documento_asociado, numero
                    FROM guias_remision
                    WHERE documento_asociado = ANY(%s)
                    ORDER BY id DESC
                """
                guias_rows = db_query(guias_query, (cotizacion_numeros,))
                for g in guias_rows:
                    key = g.get('documento_asociado')
                    guias_por_cotizacion.setdefault(key, [])
                    if len(guias_por_cotizacion[key]) < 4:
                        guias_por_cotizacion[key].append(g.get('numero'))
            except Exception as e:
                print(f"⚠️ Error buscando guías vinculadas por cotizacion_numero: {e}")

            try:
                comprobantes_query = """
                    SELECT documento_asociado, serie, numero
                    FROM comprobantes
                    WHERE documento_asociado = ANY(%s)
                    ORDER BY id DESC
                """
                comp_rows = db_query(comprobantes_query, (cotizacion_numeros,))
                for c in comp_rows:
                    key = c.get('documento_asociado')
                    comprobantes_por_cotizacion.setdefault(key, [])
                    if len(comprobantes_por_cotizacion[key]) < 4:
                        comprobantes_por_cotizacion[key].append(f"{c.get('serie')}-{c.get('numero')}")
            except Exception as e:
                print(f"⚠️ Error buscando comprobantes vinculados por cotizacion_numero: {e}")

        # ============================================================
        # 🔽 FORMATEAR FECHAS CON HORA
        # ============================================================
        formatted_data = []
        for row in data:
            try:
                # Formatear fecha_despacho
                fecha_despacho = row.get('fecha_despacho')
                fecha_despacho_formateada = None

                if fecha_despacho:
                    try:
                        from datetime import datetime

                        if isinstance(fecha_despacho, str):
                            if 'T' in fecha_despacho:
                                dt = datetime.fromisoformat(fecha_despacho.replace('Z', '+00:00'))
                                fecha_despacho_formateada = dt.strftime('%d/%m/%Y %H:%M')
                            elif '-' in fecha_despacho and len(fecha_despacho) == 10:
                                dt = datetime.strptime(fecha_despacho, '%Y-%m-%d')
                                fecha_despacho_formateada = dt.strftime('%d/%m/%Y')
                            elif '/' in fecha_despacho:
                                fecha_despacho_formateada = fecha_despacho
                            else:
                                fecha_despacho_formateada = fecha_despacho
                        elif isinstance(fecha_despacho, datetime):
                            fecha_despacho_formateada = fecha_despacho.strftime('%d/%m/%Y %H:%M')
                        else:
                            fecha_despacho_formateada = str(fecha_despacho)
                    except Exception as e:
                        print(f"⚠️ Error formateando fecha: {e}")
                        fecha_despacho_formateada = str(fecha_despacho)

                created_at = row.get('created_at')
                created_at_formateada = None
                if created_at:
                    try:
                        from datetime import datetime
                        if isinstance(created_at, str) and 'T' in created_at:
                            dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                            created_at_formateada = dt.strftime('%d/%m/%Y %H:%M')
                        else:
                            created_at_formateada = str(created_at)
                    except:
                        created_at_formateada = str(created_at)

                # 🔽 Resolver guía(s) y comprobante(s) vinculados por cotizacion_numero
                cot_num = row.get('cotizacion_numero')
                guias_vinculadas = guias_por_cotizacion.get(cot_num, [])
                comprobantes_vinculados = comprobantes_por_cotizacion.get(cot_num, [])

                guia_display = ', '.join(guias_vinculadas) if guias_vinculadas else row.get('guia')
                comprobante_display = ', '.join(comprobantes_vinculados) if comprobantes_vinculados else row.get('comprobante')

                # 🔽 Manejar items_json de forma segura
                items = []
                items_json_raw = row.get('items_json')
                if items_json_raw:
                    try:
                        if isinstance(items_json_raw, str):
                            items = json.loads(items_json_raw)
                        elif isinstance(items_json_raw, (list, dict)):
                            items = items_json_raw
                        else:
                            items = []
                    except Exception as e:
                        print(f"⚠️ Error parseando items_json: {e}")
                        items = []

                formatted_data.append({
                    'id': row.get('id'),
                    'numero': row.get('numero'),
                    'fecha': row.get('fecha'),
                    'fecha_despacho': fecha_despacho_formateada or row.get('fecha_despacho'),
                    'estado': row.get('estado'),
                    'pc_id': row.get('pc_id'),
                    'pc_numero': row.get('pc_numero'),
                    # N° de la orden de compra del cliente, debajo del N° PV en Entregas (26/10/2026)
                    'oc_cliente': row.get('oc_cliente') or '',
                    'cotizacion_id': row.get('cotizacion_id'),
                    'cotizacion_numero': row.get('cotizacion_numero'),
                    'cliente': row.get('cliente'),
                    'ruc': row.get('ruc'),
                    'comprobante': comprobante_display,
                    'guia': guia_display,
                    'origen': row.get('origen'),
                    'destino': row.get('destino'),
                    'transportista': row.get('transportista'),
                    'observaciones': row.get('observaciones'),
                    'responsable': row.get('responsable'),
                    'items': items,  # ← Agregar items al objeto
                    'created_at': created_at_formateada,
                    'updated_at': row.get('updated_at'),
                    # Fecha de cita con el cliente (Entregas, 20/10/2026); texto ISO sin zona para la pantalla
                    'fecha_cita': row['fecha_cita'].strftime('%Y-%m-%d') if row.get('fecha_cita') else None,
                    # Distrito: el que escribió el usuario o, si no, el que se lee en la dirección (23/10/2026)
                    'distrito': row.get('distrito') or adivinar_distrito(row.get('destino')),
                    'distrito_escrito': bool(row.get('distrito')),
                    'comentario': row.get('comentario') or '',
                    # Salida del almacén, entrega real y rechazo (Erika 26/10/2026)
                    'fecha_salida': row['fecha_salida'].strftime('%Y-%m-%dT%H:%M:%S') if row.get('fecha_salida') else None,
                    'fecha_entrega_real': row['fecha_entrega_real'].isoformat() if row.get('fecha_entrega_real') else None,
                    'motivo_rechazo': row.get('motivo_rechazo') or '',
                    'fecha_rechazo': row['fecha_rechazo'].strftime('%Y-%m-%dT%H:%M:%S') if row.get('fecha_rechazo') else None
                })
            except Exception as e:
                print(f"❌ Error procesando fila de despacho: {e}")
                import traceback
                traceback.print_exc()
                # Continuar con la siguiente fila en lugar de fallar todo
                continue

        print(f"✅ Despachos formateados: {len(formatted_data)}")
        return jsonify({'success': True, 'data': formatted_data})
        
    except Exception as e:
        print(f"❌ Error en api_despachos_listar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

def _vincular_despacho_con_pc(data):
    """Completa pc_id / pc_numero / cotización / items del despacho a partir de su PV o su cotización."""
    try:
        pc = None
        if data.get('pc_id'):
            pc = db_query("SELECT * FROM pedido_compra_pc WHERE id = %s", (data['pc_id'],))
        elif data.get('pc_numero'):
            pc = db_query("SELECT * FROM pedido_compra_pc WHERE numero = %s ORDER BY id DESC LIMIT 1", (data['pc_numero'],))
        elif data.get('cotizacion_id') or data.get('cotizacion_numero'):
            pc = db_query("""SELECT * FROM pedido_compra_pc
                             WHERE ((%s::int IS NOT NULL AND cotizacion_id = %s::int) OR (%s <> '' AND cotizacion_numero = %s))
                               AND COALESCE(estado, '') NOT IN ('Anulado', 'Anulada')
                             ORDER BY id DESC LIMIT 1""",
                          (data.get('cotizacion_id'), data.get('cotizacion_id'),
                           data.get('cotizacion_numero') or '', data.get('cotizacion_numero') or ''))
        if not pc:
            if data.get('cotizacion_numero') and not data.get('cotizacion_id'):
                cot = db_query("SELECT id FROM cotizaciones WHERE numero_cotizacion = %s LIMIT 1", (data['cotizacion_numero'],))
                if cot:
                    data['cotizacion_id'] = cot[0]['id']
            return
        pc = pc[0]
        data['pc_id'] = data.get('pc_id') or pc['id']
        data['pc_numero'] = data.get('pc_numero') or pc.get('numero')
        data['cotizacion_id'] = data.get('cotizacion_id') or pc.get('cotizacion_id')
        data['cotizacion_numero'] = data.get('cotizacion_numero') or pc.get('cotizacion_numero')
        data['cliente'] = data.get('cliente') or pc.get('cliente')
        data['ruc'] = data.get('ruc') or pc.get('ruc')
        data['destino'] = data.get('destino') or pc.get('lugar_entrega') or pc.get('entrega')
        if not data.get('items') and not data.get('id'):
            items = pc.get('items_json') or pc.get('items') or []
            if isinstance(items, str):
                items = json.loads(items or '[]')
            data['items'] = [{
                'codigo': i.get('codigo') or '',
                'producto': i.get('producto') or i.get('descripcion') or '',
                'descripcion_cliente': i.get('descripcion_cliente') or '',   # 24/10/2026: como en la PC (Pedido del cliente)
                'marca': i.get('marca') or '', 'modelo': i.get('modelo') or '',
                'cantidad': float(i.get('cantidad_pc') or i.get('cantidad') or 0),
                'um': i.get('um') or 'NIU',
            } for i in items if isinstance(i, dict)]
    except Exception as e:
        print(f"⚠️ No se pudo vincular el despacho con su PV: {e}")


def _actualizar_despacho(data, fecha_despacho):
    """Editar un despacho existente (antes 'guardar' siempre creaba uno nuevo)."""
    actual = db_query("SELECT id, estado FROM despachos WHERE id = %s", (data['id'],))
    if not actual:
        return jsonify({'success': False, 'error': 'Despacho no encontrado'}), 404
    result = db_query("""
        UPDATE despachos SET
            fecha_despacho = %s, pc_id = COALESCE(%s, pc_id), pc_numero = COALESCE(NULLIF(%s, ''), pc_numero),
            cotizacion_id = COALESCE(%s, cotizacion_id),
            cotizacion_numero = COALESCE(NULLIF(%s, ''), cotizacion_numero),
            cliente = COALESCE(NULLIF(%s, ''), cliente), ruc = COALESCE(NULLIF(%s, ''), ruc),
            origen = COALESCE(NULLIF(%s, ''), origen), destino = COALESCE(NULLIF(%s, ''), destino),
            transportista = COALESCE(%s, transportista), observaciones = COALESCE(%s, observaciones),
            updated_at = NOW()
        WHERE id = %s RETURNING id, numero
    """, (fecha_despacho, data.get('pc_id'), data.get('pc_numero') or '', data.get('cotizacion_id'),
          data.get('cotizacion_numero') or '', data.get('cliente') or '', data.get('ruc') or '',
          data.get('origen') or '', data.get('destino') or '', data.get('transportista'),
          data.get('observaciones'), data['id']))
    return jsonify({'success': True, 'message': 'Despacho actualizado', 'data': result})


@ventas_bp.route('/ventas/api/despachos/guardar', methods=['POST'])
@login_required
def api_despachos_guardar():
    try:
        data = request.get_json()
        usuario_id = session.get('usuario_id')
        
        print("=" * 80)
        print("🚚 API DESPACHOS GUARDAR")
        print(f"  - PV ID: {data.get('pc_id')}")
        print(f"  - PV Número: {data.get('pc_numero')}")
        print("=" * 80)
        
        from datetime import datetime, timedelta
        
        # ============================================================
        # 🔽 HORA LOCAL DE PERÚ (UTC-5)
        # ============================================================
        ahora_utc = datetime.utcnow()
        ahora_peru = ahora_utc - timedelta(hours=5)
        fecha_actual = ahora_peru.strftime('%Y-%m-%d %H:%M:%S')
        
        # Número: correlativo del día DESP-AAAAMMDD-NNNN (antes eran 4 cifras de la hora y podían repetirse)
        if not data.get('id') and data.get('numero') and db_query("SELECT 1 FROM despachos WHERE numero = %s", (data['numero'],)):
            data['numero'] = None
        if not data.get('id') and not data.get('numero'):
            prefijo = f"DESP-{ahora_peru.strftime('%Y%m%d')}-"
            with db_tx() as conn:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                bloquear_numeracion(cur, 'despachos:' + prefijo)
                cur.execute("""SELECT COALESCE(MAX(NULLIF(regexp_replace(SUBSTRING(numero FROM %s), '\\D', '', 'g'), '')::int), 0) + 1 AS sig
                               FROM despachos WHERE numero LIKE %s""", (len(prefijo) + 1, prefijo + '%'))
                data['numero'] = prefijo + str(cur.fetchone()['sig']).zfill(4)
        
        if not data.get('fecha'):
            data['fecha'] = fecha_actual
        
        # ============================================================
        # PROCESAR FECHA DESPACHO CON HORA LOCAL
        # ============================================================
        fecha_despacho = data.get('fecha_despacho')
        
        if fecha_despacho:
            try:
                if isinstance(fecha_despacho, str) and ' ' in fecha_despacho:
                    # Ya tiene hora, mantenerla
                    dt = datetime.strptime(fecha_despacho, '%Y-%m-%d %H:%M:%S')
                    fecha_despacho = dt.strftime('%Y-%m-%d %H:%M:%S')
                elif isinstance(fecha_despacho, str) and 'T' in fecha_despacho:
                    # Formato ISO
                    dt = datetime.fromisoformat(fecha_despacho.replace('Z', '+00:00'))
                    # Convertir a hora Perú
                    dt_peru = dt - timedelta(hours=5) if dt.tzinfo else dt
                    fecha_despacho = dt_peru.strftime('%Y-%m-%d %H:%M:%S')
                elif isinstance(fecha_despacho, str) and '-' in fecha_despacho and len(fecha_despacho) == 10:
                    # Solo fecha, agregar hora actual
                    dt = datetime.strptime(fecha_despacho, '%Y-%m-%d')
                    dt_peru = dt.replace(hour=ahora_peru.hour, minute=ahora_peru.minute, second=ahora_peru.second)
                    fecha_despacho = dt_peru.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    fecha_despacho = fecha_actual
            except Exception as e:
                print(f"⚠️ Error procesando fecha: {e}")
                fecha_despacho = fecha_actual
        else:
            fecha_despacho = fecha_actual
        
        print(f"📅 Fecha despacho FINAL: {fecha_despacho}")
        
        # ============================================================
        # GUARDAR ITEMS COMO JSON
        # ============================================================
        # ============================================================
        # VINCULAR CON SU PV (orden: Cotización → PV → Despacho → Guía → Factura)
        # Si llega solo la cotización (despacho hecho desde Cotizaciones), se busca su PV
        # para que el despacho lleve PV, productos y empresa, y la guía y la factura lo encuentren.
        # ============================================================
        _vincular_despacho_con_pc(data)

        if data.get('id'):
            return _actualizar_despacho(data, fecha_despacho)

        # No se repite un despacho del mismo PV (20/10/2026: PC-KCF-000002 quedó con dos despachos de 10 por 10 pedidos)
        duplicado = _despacho_duplicado(data)
        if duplicado:
            return jsonify({'success': False, 'codigo': 'duplicado', 'titulo': 'DESPACHO DUPLICADO: NO SE CREÓ', 'error': duplicado}), 409

        items_json = json.dumps(data.get('items', []))
        # El despacho queda en la empresa de su PV (o de la cotización, o la elegida arriba)
        empresa_desp = empresa_para_crear(empresa_de(None, 'pedido_compra_pc', 'id', data.get('pc_id'))
                                          or empresa_de(None, 'pedido_compra_pc', 'numero', data.get('pc_numero'))
                                          or empresa_de(None, 'cotizaciones', 'id', data.get('cotizacion_id')))
        
        # ============================================================
        # GUARDAR DESPACHO CON ITEMS
        # ============================================================
        query = """
            INSERT INTO despachos (
                numero, fecha, fecha_despacho, estado,
                pc_id, pc_numero, cotizacion_id, cotizacion_numero,
                cliente, ruc, comprobante, guia, origen, destino,
                transportista, observaciones, responsable,
                items_json, creado_por
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s
            ) RETURNING id, numero
        """
        
        params = (
            data.get('numero'),
            fecha_actual,  # ← FECHA CON HORA LOCAL
            fecha_despacho,
            data.get('estado', 'Pendiente despacho'),
            data.get('pc_id'),
            data.get('pc_numero'),
            data.get('cotizacion_id'),
            data.get('cotizacion_numero'),
            data.get('cliente') or '',
            data.get('ruc') or '',
            data.get('comprobante'),
            data.get('guia'),
            data.get('origen', 'ALM-SMP'),
            data.get('destino') or '',
            data.get('transportista'),
            data.get('observaciones') or '',
            data.get('responsable') or 'Hellen',
            items_json,
            data.get('creado_por') or session.get('usuario_id')
        )
        
        result = db_query(query, params)
        print(f"✅ Resultado: {result}")
        
        if result:
            marcar_empresa(None, 'despachos', result[0]['id'], empresa_desp)
            return jsonify({'success': True, 'message': 'Despacho guardado', 'data': result})
        
        return jsonify({'success': False, 'error': 'No se pudo guardar'}), 400
            
    except Exception as e:
        print(f"❌ Error en api_despachos_guardar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# DEVOLUCIONES - API
# ============================================================

@ventas_bp.route('/ventas/api/devoluciones/listar', methods=['GET'])
@login_required
def api_devoluciones_listar():
    try:
        data = obtener_devoluciones_db()
        data = filtrar_filas('devoluciones', data)  # solo la empresa elegida arriba
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@ventas_bp.route('/ventas/api/devoluciones/guardar', methods=['POST'])
@login_required
def api_devoluciones_guardar():
    try:
        data = request.get_json()
        usuario_id = session.get('usuario_id')
        data['creado_por'] = usuario_id
        
        if not data.get('numero'):
            data['numero'] = f"DEV-{datetime.now().strftime('%Y%m%d')}-{str(datetime.now().timestamp()).split('.')[0][-4:]}"
        
        empresa_dev = empresa_para_crear(empresa_de(None, 'comprobantes', 'id', data.get('comprobante_id')))
        result = guardar_devolucion_db(data)
        if result:
            marcar_empresa(None, 'devoluciones', result['id'], empresa_dev)
            return jsonify({'success': True, 'message': 'Devolución guardada', 'data': result})
        return jsonify({'success': False, 'error': 'No se pudo guardar'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# EXPORTAR DATOS
# ============================================================

@ventas_bp.route('/ventas/api/exportar/<tipo>', methods=['GET'])
@login_required
def api_exportar(tipo):
    try:
        return jsonify({'success': True, 'message': f'Exportación de {tipo} preparada'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# CONSULTAR SUNAT
# ============================================================

@ventas_bp.route('/ventas/api/sunat/consulta', methods=['GET'])
@login_required
def api_sunat_consulta():
    """Consultar RUC en SUNAT"""
    try:
        ruc = request.args.get('ruc', '').strip()
        
        if not ruc or len(ruc) != 11:
            return jsonify({'success': False, 'error': 'RUC inválido, debe tener 11 dígitos'}), 400
        
        # Primero, buscar en la base de datos
        cliente = buscar_cliente_por_ruc(ruc)
        
        if cliente:
            # Cliente encontrado en la base de datos
            return jsonify({
                'success': True,
                'encontrado': True,
                'origen': 'base_datos',
                'mensaje': '✅ Cliente encontrado en sistema',
                'data': {
                    'ruc': cliente.get('numero_documento'),
                    'razon_social': cliente.get('razon_social'),
                    'nombre_comercial': cliente.get('nombre_comercial'),
                    'direccion': cliente.get('direccion_fiscal'),
                    'telefono': cliente.get('telefono_contacto'),
                    'contacto': cliente.get('nombre_contacto'),
                    'email': cliente.get('email_contacto'),
                    'codigo_cliente': cliente.get('codigo_cliente'),
                    'tipo_documento': cliente.get('tipo_documento', 'RUC'),
                    'estado': cliente.get('estado', 'Activo')
                }
            })
        
        # Si no existe en BD, consultar SUNAT (simulado por ahora)
        # En producción, aquí iría la llamada a la API de SUNAT
        datos_sunat = {
            'ruc': ruc,
            'razon_social': f'EMPRESA CON RUC {ruc}',
            'nombre_comercial': f'EMPRESA {ruc[-4:]}',
            'direccion': 'Dirección fiscal consultada en SUNAT',
            'telefono': '',
            'contacto': '',
            'email': '',
            'estado': 'ACTIVO'
        }
        
        return jsonify({
            'success': True,
            'encontrado': False,
            'origen': 'sunat',
            'mensaje': '🌞 Cliente consultado en SUNAT - datos cargados',
            'data': datos_sunat
        })
        
    except Exception as e:
        print(f"❌ Error en api_sunat_consulta: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# DESPACHOS - ENDPOINTS ADICIONALES
# ============================================================

@ventas_bp.route('/ventas/api/despachos/<int:id>/toggle', methods=['PUT'])
@login_required
def api_despachos_toggle(id):
    """Cambia el estado de un despacho (ej: Pendiente -> Despachado)"""
    try:
        data = request.get_json()
        nuevo_estado = data.get('estado')
        
        if not nuevo_estado:
            return jsonify({'success': False, 'error': 'Estado requerido'}), 400
        
        # Validar que el estado sea válido
        # "Entregado" y "Rechazado por el cliente" se ponen con su fecha o motivo en /entrega (26/10/2026)
        estados_validos = ['Pendiente despacho', 'En preparación', 'Despachado']
        if nuevo_estado not in estados_validos:
            return jsonify({'success': False, 'error': f'Estado inválido. Permitidos: {", ".join(estados_validos)}'}), 400
        
        _asegurar_columnas_entrega()
        antes = db_query("SELECT estado FROM despachos WHERE id = %s", (id,))
        # Al despachar se descuenta el stock de la empresa y sede elegidas (routes/stock_automatico.py)
        from routes.stock_automatico import cambiar_estado_despacho
        respuesta, codigo = cambiar_estado_despacho(id, nuevo_estado, data.get('empresa_id'), data.get('almacen_id'))
        # Fecha y hora en que salió del almacén (también al volver a despachar algo rechazado)
        if codigo == 200 and nuevo_estado == 'Despachado' and antes and antes[0].get('estado') not in ('Despachado', 'Entregado'):
            db_execute("UPDATE despachos SET fecha_salida = (NOW() AT TIME ZONE 'America/Lima'), fecha_entrega_real = NULL WHERE id = %s", (id,))
        return jsonify(respuesta), codigo
        
    except Exception as e:
        print(f"❌ Error en api_despachos_toggle: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@ventas_bp.route('/ventas/api/despachos/<int:id>', methods=['DELETE'])
@login_required
def api_despachos_eliminar(id):
    """Elimina (anula) un despacho. Si ya había salido, el stock vuelve al inventario."""
    try:
        from routes.stock_automatico import cambiar_estado_despacho
        data = request.get_json(silent=True) or {}
        respuesta, codigo = cambiar_estado_despacho(id, 'Anulado', motivo=(data.get('motivo') or '').strip() or 'despacho anulado')
        return jsonify(respuesta), codigo
        
    except Exception as e:
        print(f"❌ Error en api_despachos_eliminar: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@ventas_bp.route('/ventas/api/despachos/<int:id>', methods=['GET'])
@login_required
def api_despachos_obtener(id):
    """Obtiene un despacho por su ID"""
    try:
        query = """
            SELECT 
                id, numero, fecha, fecha_despacho, estado,
                pc_id, pc_numero, cotizacion_id, cotizacion_numero,
                cliente, ruc, comprobante, guia, origen, destino,
                transportista, observaciones, responsable,
                created_at, updated_at
            FROM despachos
            WHERE id = %s
        """
        result = db_query(query, (id,))
        
        if result:
            return jsonify({'success': True, 'data': result[0]})
        
        return jsonify({'success': False, 'error': 'Despacho no encontrado'}), 404
        
    except Exception as e:
        print(f"❌ Error en api_despachos_obtener: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# PEDIDO COMPRA - ENDPOINTS ADICIONALES
# ============================================================

@ventas_bp.route('/ventas/api/pedido-compra/<int:id>/toggle', methods=['PUT'])
@login_required
def api_pedido_compra_toggle(id):
    """Cambia el estado de un pedido de venta"""
    try:
        data = request.get_json()
        nuevo_estado = data.get('estado')
        
        if not nuevo_estado:
            return jsonify({'success': False, 'error': 'Estado requerido'}), 400
        
        # 🔽 Actualizar la lista de estados válidos
        estados_validos = [
            'Pendiente', 
            'Recibido por correo', 
            'En revisión interna', 
            'Validado por Hellen', 
            'Listo para despacho', 
            'Anulado',
            'PC observado',        # ← Agregar este
            'PC conforme',          # ← Agregar este
            'Bloqueado'             # ← Agregar este
        ]
        
        if nuevo_estado not in estados_validos:
            return jsonify({'success': False, 'error': f'Estado inválido. Permitidos: {", ".join(estados_validos)}'}), 400
        
        query = """
            UPDATE pedido_compra_pc 
            SET estado = %s, updated_at = NOW()
            WHERE id = %s
            RETURNING id, estado
        """
        result = db_query(query, (nuevo_estado, id))
        
        if result:
            return jsonify({
                'success': True, 
                'message': f'PV actualizado a {nuevo_estado}',
                'data': result[0]
            })
        
        return jsonify({'success': False, 'error': 'PV no encontrado'}), 404
        
    except Exception as e:
        print(f"❌ Error en api_pedido_compra_toggle: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# GUÍAS - ENDPOINTS ADICIONALES
# ============================================================

@ventas_bp.route('/ventas/api/guias/<int:id>/toggle', methods=['PUT'])
@login_required
def api_guias_toggle(id):
    """Cambia el estado de una guía"""
    try:
        data = request.get_json()
        nuevo_estado = data.get('estado')
        
        if not nuevo_estado:
            return jsonify({'success': False, 'error': 'Estado requerido'}), 400
        
        estados_validos = ['Borrador', 'Pendiente despacho', 'Emitida', 'Entregada', 'Anulada']
        if nuevo_estado not in estados_validos:
            return jsonify({'success': False, 'error': f'Estado inválido'}), 400
        
        query = """
            UPDATE guias_remision 
            SET estado_sunat = %s, updated_at = NOW()
            WHERE id = %s
            RETURNING id, estado_sunat as estado
        """
        result = db_query(query, (nuevo_estado, id))
        
        if result:
            return jsonify({
                'success': True, 
                'message': f'Guía actualizada a {nuevo_estado}',
                'data': result[0]
            })
        
        return jsonify({'success': False, 'error': 'Guía no encontrada'}), 404
        
    except Exception as e:
        print(f"❌ Error en api_guias_toggle: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# COMPROBANTES - ENDPOINTS ADICIONALES
# ============================================================

@ventas_bp.route('/ventas/api/comprobantes/<int:id>/toggle', methods=['PUT'])
@login_required
def api_comprobantes_toggle(id):
    """Cambia el estado de un comprobante"""
    try:
        data = request.get_json()
        nuevo_estado = data.get('estado')
        
        if not nuevo_estado:
            return jsonify({'success': False, 'error': 'Estado requerido'}), 400
        
        estados_validos = ['Borrador', 'Emitido', 'Enviado', 'Pagado', 'Anulado']
        if nuevo_estado not in estados_validos:
            return jsonify({'success': False, 'error': f'Estado inválido'}), 400
        actual = db_query("SELECT estado_sunat FROM comprobantes WHERE id = %s", (id,))
        if not actual:
            return jsonify({'success': False, 'error': 'Comprobante no encontrado'}), 404
        estado_actual = (actual[0].get('estado_sunat') or 'Borrador').capitalize()
        transiciones = {
            'Borrador': ('Emitido', 'Anulado'),
            'Emitido': ('Enviado', 'Pagado', 'Anulado'),
            'Enviado': ('Pagado', 'Anulado'),
            'Aceptado': ('Pagado', 'Anulado'),
            'Pagado': (),
            'Anulado': (),
        }
        permitidos = transiciones.get(estado_actual, estados_validos)
        if nuevo_estado != estado_actual and nuevo_estado not in permitidos:
            return jsonify({'success': False,
                            'error': f'No se puede pasar un comprobante de "{estado_actual}" a "{nuevo_estado}"'}), 409

        fila = actualizar_estado_comprobante_db(id, nuevo_estado)
        result = [{'id': fila['id'], 'estado': fila['estado_sunat']}] if fila else None
        
        if result:
            mensaje = f'Comprobante actualizado a {nuevo_estado}'
            if fila.get('cobros_anulados'):
                mensaje += f". Se anularon {fila['cobros_anulados']} cobro(s) en caja"
            return jsonify({
                'success': True, 
                'message': mensaje,
                'data': result[0]
            })
        
        return jsonify({'success': False, 'error': 'Comprobante no encontrado'}), 404
        
    except Exception as e:
        print(f"❌ Error en api_comprobantes_toggle: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# NOTAS DE CRÉDITO - ENDPOINTS ADICIONALES
# ============================================================

@ventas_bp.route('/ventas/api/notas-credito/<int:id>/toggle', methods=['PUT'])
@login_required
def api_notas_credito_toggle(id):
    """Cambia el estado de una nota de crédito"""
    try:
        data = request.get_json()
        nuevo_estado = data.get('estado')
        
        if not nuevo_estado:
            return jsonify({'success': False, 'error': 'Estado requerido'}), 400
        
        estados_validos = ['Borrador', 'Emitida', 'Enviada', 'Aplicada', 'Anulada']
        if nuevo_estado not in estados_validos:
            return jsonify({'success': False, 'error': f'Estado inválido'}), 400
        
        query = """
            UPDATE notas_credito 
            SET estado = %s, updated_at = NOW()
            WHERE id = %s
            RETURNING id, estado
        """
        result = db_query(query, (nuevo_estado, id))
        
        if result:
            return jsonify({
                'success': True, 
                'message': f'Nota de crédito actualizada a {nuevo_estado}',
                'data': result[0]
            })
        
        return jsonify({'success': False, 'error': 'Nota de crédito no encontrada'}), 404
        
    except Exception as e:
        print(f"❌ Error en api_notas_credito_toggle: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@ventas_bp.route('/ventas/api/notas-credito/<int:id>', methods=['GET'])
@login_required
def api_notas_credito_obtener(id):
    """Obtiene una nota de crédito específica por su ID"""
    try:
        query = """
            SELECT 
                id, serie, numero, fecha_emision, fecha_vencimiento,
                cliente_tipo_doc, cliente_numero_doc, cliente_nombre,
                cliente_direccion, cliente_email, cliente_telefono,
                comprobante_asociado, motivo, monto, observaciones,
                estado, creado_por, created_at, updated_at
            FROM notas_credito
            WHERE id = %s
        """
        result = db_query(query, (id,))
        if not result:
            return jsonify({'success': False, 'error': 'Nota de crédito no encontrada'}), 404

        return jsonify({'success': True, 'data': result[0]})
    except Exception as e:
        print(f"❌ Error en api_notas_credito_obtener: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# DEVOLUCIONES - ENDPOINTS ADICIONALES
# ============================================================

@ventas_bp.route('/ventas/api/devoluciones/<int:id>/toggle', methods=['PUT'])
@login_required
def api_devoluciones_toggle(id):
    """Cambia el estado de una devolución"""
    try:
        data = request.get_json()
        nuevo_estado = data.get('estado')
        
        if not nuevo_estado:
            return jsonify({'success': False, 'error': 'Estado requerido'}), 400
        
        estados_validos = ['Pendiente', 'En revisión', 'Aprobada', 'Rechazada', 'Procesada']
        if nuevo_estado not in estados_validos:
            return jsonify({'success': False, 'error': f'Estado inválido'}), 400
        
        query = """
            UPDATE devoluciones 
            SET estado = %s, updated_at = NOW()
            WHERE id = %s
            RETURNING id, estado
        """
        result = db_query(query, (nuevo_estado, id))
        
        if result:
            return jsonify({
                'success': True, 
                'message': f'Devolución actualizada a {nuevo_estado}',
                'data': result[0]
            })
        
        return jsonify({'success': False, 'error': 'Devolución no encontrada'}), 404
        
    except Exception as e:
        print(f"❌ Error en api_devoluciones_toggle: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================

@ventas_bp.route('/ventas/api/cotizaciones/<int:id>/completa', methods=['GET'])
@login_required
def api_cotizaciones_obtener_completa(id):
    """Obtiene una cotización con sus productos para edición o para crear PV"""
    try:
        # Obtener cabecera
        query_cabecera = """
            SELECT 
                c.id, c.numero_cotizacion, c.fecha_creacion, c.estado,
                c.subtotal, c.igv, c.total, c.usuario_id, c.notas,
                c.forma_pago, c.tiempo_entrega, c.almacen, c.validez_oferta,
                c.codigo_cotizacion, c.correlativo, c.condicion_pago,
                c.direccion_entrega, c.requerimiento, c.nota_cotizacion,
                c.descuento_porcentaje, c.descuento_monto, c.descuento_tipo,
                c.contacto_cliente, c.telefono_cliente, c.email_cliente,
                c.seguimiento, c.motivo, c.transporte, c.parihuela, c.nota_interna,
                c.vendedor,
                cl.id as cliente_id,
                cl.razon_social as cliente_razon_social,
                cl.numero_documento as cliente_ruc,
                cl.nombre_comercial as cliente_nombre_comercial,
                cl.codigo_cliente as cod_cliente,
                cl.direccion_fiscal as cliente_direccion,
                cl.telefono_contacto as cliente_telefono,
                cl.nombre_contacto as cliente_contacto,
                cl.email_contacto as cliente_email
            FROM cotizaciones c
            LEFT JOIN clientes cl ON cl.id = c.cliente_id::integer
            WHERE c.id = %s
        """
        cabecera = db_query(query_cabecera, (id,))
        
        if not cabecera:
            return jsonify({'success': False, 'error': 'Cotización no encontrada'}), 404
        
        # 🔽 OBTENER PRODUCTOS - VERIFICAR QUE ESTE QUERY FUNCIONE
        query_productos = """
            SELECT 
                d.id, d.producto_id, d.cantidad,
                d.precio_venta_unitario as valorVenta,
                d.subtotal_venta,
                d.descuento_porcentaje,
                d.precio_venta_con_descuento,
                d.subtotal_venta_con_descuento,
                d.costo_unitario,
                d.margen_porcentaje,
                d.estado_entrega,
                p.codigo, 
                p.descripcion as producto, 
                p.descripcion_larga,
                p.modelo, 
                p.marca, 
                p.unidad as um, 
                p.stock,
                p.precio_unitario,
                p.costo_unitario as costo
            FROM cotizacion_detalle d
            LEFT JOIN productos p ON p.id = d.producto_id
            WHERE d.cotizacion_id = %s
        """
        productos = db_query(query_productos, (id,))
        
        print(f"📦 Productos encontrados: {len(productos) if productos else 0}")
        
        # Combinar datos
        result = dict(cabecera[0])
        
        # Asegurar nombres consistentes para el frontend
        result['cliente_razon_social'] = result.get('cliente_razon_social') or result.get('cliente_nombre_comercial') or f"Cliente {result.get('cliente_id', '')}"
        result['cliente_ruc'] = result.get('cliente_ruc') or str(result.get('cliente_id', ''))
        result['cod_cliente'] = result.get('cod_cliente') or f"CLI-{str(result.get('cliente_id', '')).zfill(6)}"
        result['cliente_direccion'] = result.get('cliente_direccion') or result.get('direccion_entrega', '')
        result['cliente_email'] = result.get('cliente_email') or result.get('email_cliente', '')
        result['cliente_telefono'] = result.get('cliente_telefono') or result.get('telefono_cliente', '')
        
        # 🔽 ASEGURAR QUE PRODUCTOS SE DEVUELVAN CORRECTAMENTE
        result['productos'] = []
        for p in (productos or []):
            result['productos'].append({
                'id': p.get('producto_id'),
                'codigo': p.get('codigo') or '',
                'producto': p.get('producto') or p.get('descripcion_larga') or 'Producto sin nombre',
                'descripcion': p.get('descripcion_larga') or p.get('producto') or '',
                'modelo': p.get('modelo') or '',
                'marca': p.get('marca') or '',
                'um': p.get('um') or 'NIU',
                'cantidad': float(p.get('cantidad') or 1),
                # PostgreSQL devuelve el alias en minúsculas (valorventa): antes se perdía el precio cotizado
                # y se mostraba el precio actual del producto
                'valorVenta': float(p.get('valorventa') or p.get('valorVenta') or p.get('precio_unitario') or 0),
                'stock': int(p.get('stock') or 0),
                'costo_unitario': float(p.get('costo_unitario') or p.get('costo') or 0),
                'subtotal_venta': float(p.get('subtotal_venta') or 0),
                'descuento_porcentaje': float(p.get('descuento_porcentaje') or 0),
                'precio_venta_con_descuento': float(p.get('precio_venta_con_descuento') or 0),
                'estado_entrega': estado_entrega_valido(p.get('estado_entrega'))
            })
        
        _aplicar_descuento_cotizacion(result)
        print(f"📦 Productos en respuesta: {len(result['productos'])}")
        
        return jsonify({'success': True, 'data': result})
        
    except Exception as e:
        print(f"❌ Error en api_cotizaciones_obtener_completa: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


def estado_entrega_valido(valor):
    """Estado de entrega de un producto de la cotización: solo 'Pendiente' o 'Entregado'."""
    return 'Entregado' if str(valor or '').strip().lower().startswith('entregad') else 'Pendiente'


def _aplicar_descuento_cotizacion(result):
    """Reparte el descuento de la cotización en el precio de cada producto (para la PV).

    El descuento se guarda en la cabecera (descuento_tipo '%' o 'S/', descuento_porcentaje,
    descuento_monto) y, a veces, por línea (descuento_porcentaje / precio_venta_con_descuento).
    La PV trabaja con precio por producto, así que se le entrega el precio YA descontado en
    precio_neto (valorVenta sigue siendo el precio de lista, que usa la edición de la cotización).
    La suma de cantidad x precio_neto da el subtotal descontado de la cotización (sin IGV).
    """
    productos = result.get('productos') or []
    for p in productos:
        p['precio_lista'] = float(p.get('valorVenta') or 0)
    base = sum(float(p.get('cantidad') or 0) * p['precio_lista'] for p in productos)
    tipo = str(result.get('descuento_tipo') or '').strip()
    pct = float(result.get('descuento_porcentaje') or 0)
    monto = float(result.get('descuento_monto') or 0)
    if tipo == '%' and pct > 0:
        factor = 1 - pct / 100.0
    elif monto > 0 and base > 0:
        factor = (base - monto) / base
    else:
        factor = 1.0
    factor = min(max(factor, 0.0), 1.0)
    # Desde el 15/10 el guardado ya deja el precio descontado de cada línea (precio_venta_con_descuento,
    # el mismo descuento de la cabecera repartido); si está, se usa tal cual. Si no (cotizaciones
    # antiguas), se reparte el descuento de la cabecera.
    por_linea = factor < 1 and productos and all(
        float(p.get('precio_venta_con_descuento') or 0) > 0 and float(p.get('descuento_porcentaje') or 0) > 0
        for p in productos)
    for p in productos:
        if por_linea:
            p['precio_neto'] = round(float(p['precio_venta_con_descuento']), 2)
        else:
            p['precio_neto'] = round(p['precio_lista'] * factor, 2)
    neto = round(sum(float(p.get('cantidad') or 0) * p['precio_neto'] for p in productos), 2)
    result['descuento_factor'] = factor
    result['descuento_total'] = round(base - neto, 2) if productos else round(monto, 2)
    result['subtotal_neto'] = neto if productos else float(result.get('subtotal') or 0) - monto
    result['subtotal_lista'] = round(base, 2)
    return result


@ventas_bp.route('/ventas/api/cotizaciones/descuento', methods=['GET'])
@login_required
def api_cotizacion_descuento():
    """Descuento de una cotización por su número, para mostrarlo en el resumen de la PV (pedido de Erika 19/10/2026):
    precio de lista y precio con descuento de cada producto, tipo (% o S/) y total descontado."""
    numero = (request.args.get('numero') or '').strip()
    if not numero:
        return jsonify({'success': False, 'error': 'Falta el número de cotización'}), 400
    fila = db_query("SELECT id FROM cotizaciones WHERE numero_cotizacion = %s OR codigo_cotizacion = %s ORDER BY id DESC LIMIT 1",
                    (numero, numero))
    if not fila:
        return jsonify({'success': True, 'data': None})
    resp = api_cotizaciones_obtener_completa(fila[0]['id'])
    resp = resp[0] if isinstance(resp, tuple) else resp
    d = (resp.get_json() or {}).get('data')
    if not d:
        return jsonify({'success': True, 'data': None})
    lista = {}
    for p in d.get('productos') or []:
        if p.get('codigo'):
            lista[p['codigo']] = {'lista': p.get('precio_lista'), 'neto': p.get('precio_neto')}
    return jsonify({'success': True, 'data': {
        'numero': d.get('numero_cotizacion'), 'descuento_tipo': d.get('descuento_tipo'),
        'descuento_porcentaje': float(d.get('descuento_porcentaje') or 0), 'descuento_monto': float(d.get('descuento_monto') or 0),
        'descuento_total': d.get('descuento_total'), 'subtotal_lista': d.get('subtotal_lista'),
        'subtotal_neto': d.get('subtotal_neto'), 'productos': lista}})


@ventas_bp.route('/ventas/api/cotizaciones/<int:id>/duplicar', methods=['POST'])
@login_required
def api_cotizaciones_duplicar(id):
    """Duplica una cotización existente con nuevo número"""
    try:
        print(f"📋 Duplicando cotización ID: {id}")
        
        # 1. Obtener la cotización original con sus productos
        query_cabecera = """
            SELECT 
                c.cliente_id, c.estado, c.subtotal, c.igv, c.total,
                c.notas, c.forma_pago, c.tiempo_entrega, c.almacen, 
                c.validez_oferta, c.condicion_pago, c.direccion_entrega,
                c.requerimiento, c.nota_cotizacion, c.descuento_porcentaje,
                c.descuento_monto, c.descuento_tipo, c.contacto_cliente,
                c.telefono_cliente, c.email_cliente,
                cl.razon_social as cliente_razon_social,
                cl.numero_documento as cliente_ruc
            FROM cotizaciones c
            LEFT JOIN clientes cl ON cl.id = c.cliente_id::integer
            WHERE c.id = %s
        """
        cabecera = db_query(query_cabecera, (id,))
        
        if not cabecera:
            return jsonify({'success': False, 'error': 'Cotización original no encontrada'}), 404
        
        # 2. Obtener los productos de la cotización original
        query_productos = """
            SELECT 
                d.producto_id, d.cantidad, d.costo_unitario,
                d.subtotal_costo, d.margen_porcentaje,
                d.precio_venta_unitario, d.subtotal_venta,
                d.descuento_porcentaje, d.precio_venta_con_descuento,
                d.subtotal_venta_con_descuento, d.descuento_total, d.margen_final,
                p.codigo, p.descripcion, p.marca, p.modelo, p.unidad,
                p.precio_unitario as valorVenta, p.stock
            FROM cotizacion_detalle d
            LEFT JOIN productos p ON p.id = d.producto_id
            WHERE d.cotizacion_id = %s
        """
        productos = db_query(query_productos, (id,))
        
        if not productos:
            return jsonify({'success': False, 'error': 'La cotización original no tiene productos'}), 400
        
        print(f"📦 Productos a duplicar: {len(productos)}")
        
        # 3. Generar nuevo número de cotización
        from datetime import datetime
        usuario_id = session.get('usuario_id')
        cliente_id = cabecera[0].get('cliente_id')
        
        print(f"👤 Usuario: {usuario_id}")
        print(f"🏢 Cliente ID: {cliente_id}")
        
        # 4. Insertar nueva cotización
        with db_tx() as conn:
            from psycopg2.extras import RealDictCursor
            cur = conn.cursor(cursor_factory=RealDictCursor)
            # Mismo número que una cotización nueva (antes contaba filas y podía repetir un N°)
            bloquear_numeracion(cur, 'cotizaciones')
            cur.execute("""SELECT COALESCE(MAX(NULLIF(regexp_replace(correlativo::text, '\\D', '', 'g'), '')::bigint), 0) + 1
                           AS siguiente FROM cotizaciones""")
            count = con_piso(cur, 'COT', '', cur.fetchone()['siguiente'])
            nuevo_numero = f"COT-{str(count).zfill(6)}"
            codigo = f"COT-{datetime.now().strftime('%Y%m%d')}-{str(count).zfill(4)}"
            print(f"📋 Nuevo número: {nuevo_numero}")
            
            # Insertar cabecera
            cur.execute("""
                INSERT INTO cotizaciones (
                    numero_cotizacion, cliente_id, fecha_creacion, estado,
                    subtotal, igv, total, usuario_id, notas,
                    forma_pago, tiempo_entrega, almacen, validez_oferta,
                    codigo_cotizacion, correlativo, condicion_pago,
                    direccion_entrega, requerimiento, nota_cotizacion,
                    descuento_porcentaje, descuento_monto, descuento_tipo,
                    contacto_cliente, telefono_cliente, email_cliente
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                RETURNING id, numero_cotizacion
            """, (
                nuevo_numero,
                cliente_id,
                datetime.now().isoformat(),
                'Borrador',  # Siempre empieza como borrador
                float(cabecera[0].get('subtotal', 0)),
                float(cabecera[0].get('igv', 0)),
                float(cabecera[0].get('total', 0)),
                usuario_id,
                cabecera[0].get('notas', '') + ' (Duplicado)',
                cabecera[0].get('forma_pago'),
                cabecera[0].get('tiempo_entrega'),
                cabecera[0].get('almacen'),
                cabecera[0].get('validez_oferta'),
                codigo,
                count,
                cabecera[0].get('condicion_pago'),
                cabecera[0].get('direccion_entrega'),
                cabecera[0].get('requerimiento'),
                cabecera[0].get('nota_cotizacion', '') + ' (Duplicado)',
                float(cabecera[0].get('descuento_porcentaje', 0)),
                float(cabecera[0].get('descuento_monto', 0)),
                cabecera[0].get('descuento_tipo', 'porcentaje'),
                cabecera[0].get('contacto_cliente'),
                cabecera[0].get('telefono_cliente'),
                cabecera[0].get('email_cliente')
            ))
            
            result = cur.fetchone()
            nueva_cotizacion_id = result['id']
            nuevo_numero = result['numero_cotizacion']
            # La copia queda en la misma empresa que la original
            marcar_empresa(cur, 'cotizaciones', nueva_cotizacion_id,
                           empresa_para_crear(empresa_de(cur, 'cotizaciones', 'id', id)))
            
            print(f"✅ Nueva cotización creada con ID: {nueva_cotizacion_id}")
            
            # 5. Insertar productos duplicados
            productos_guardados = 0
            for producto in productos:
                try:
                    producto_id = producto.get('producto_id')
                    if not producto_id:
                        continue
                    
                    cantidad = float(producto.get('cantidad', 1))
                    precio_venta = float(producto.get('precio_venta_unitario') or producto.get('valorVenta', 0))
                    costo_unitario = float(producto.get('costo_unitario', 0))
                    
                    cur.execute("""
                        INSERT INTO cotizacion_detalle (
                            cotizacion_id, producto_id, cantidad,
                            costo_unitario, subtotal_costo, margen_porcentaje,
                            precio_venta_unitario, subtotal_venta,
                            descuento_porcentaje, precio_venta_con_descuento,
                            subtotal_venta_con_descuento, descuento_total, margen_final
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                    """, (
                        nueva_cotizacion_id,
                        producto_id,
                        cantidad,
                        costo_unitario,
                        cantidad * costo_unitario,
                        float(producto.get('margen_porcentaje', 0)),
                        precio_venta,
                        cantidad * precio_venta,
                        float(producto.get('descuento_porcentaje', 0)),
                        precio_venta,
                        cantidad * precio_venta,
                        0,
                        float(producto.get('margen_final', 0))
                    ))
                    productos_guardados += 1
                    
                except Exception as e:
                    print(f"⚠️ Error guardando producto {producto.get('codigo')}: {e}")
                    continue
            
            print(f"📊 Productos duplicados: {productos_guardados}")
            
            return jsonify({
                'success': True,
                'message': f'Cotización duplicada correctamente con {productos_guardados} productos',
                'data': {
                    'id': nueva_cotizacion_id,
                    'numero': nuevo_numero,
                    'productos_guardados': productos_guardados,
                    'estado': 'Borrador'
                }
            })
            
    except Exception as e:
        print(f"❌ Error en api_cotizaciones_duplicar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    
@ventas_bp.route('/ventas/api/cotizaciones/<int:id>/pdf', methods=['GET'])
@login_required
def api_cotizaciones_generar_pdf(id):
    """Genera el PDF de una cotización para descarga"""
    try:
        print(f"📄 Generando PDF para cotización ID: {id}")
        
        from datetime import datetime
        from flask import render_template_string, send_file
        from weasyprint import HTML
        import tempfile
        import base64
        import os
        
        # ============================================================
        # FUNCIÓN PARA OBTENER LOGO EN BASE64 - MÚLTIPLES RUTAS
        # ============================================================
        def obtener_logo_base64_para_pdf():
            """Busca el logo en múltiples rutas y lo devuelve en base64"""
            posibles_rutas = [
                os.path.join('templates', 'pdf', 'logo-kcf.png'),
                os.path.join('templates', 'logo-kcf.png'),
                os.path.join('static', 'img', 'logo-kcf.png'),
                os.path.join('static', 'logo-kcf.png'),
                'logo-kcf.png',
                os.path.join('app', 'static', 'img', 'logo-kcf.png'),
                os.path.join('app', 'static', 'logo-kcf.png'),
                os.path.join('static', 'images', 'logo-kcf.png'),
                os.path.join('templates', 'cotizacion_oc', 'logo-kcf.png'),
                os.path.join('..', 'static', 'img', 'logo-kcf.png'),
                os.path.join('..', 'static', 'logo-kcf.png'),
            ]
            
            for logo_path in posibles_rutas:
                if os.path.exists(logo_path):
                    try:
                        with open(logo_path, 'rb') as f:
                            logo_data = f.read()
                            logo_base64 = base64.b64encode(logo_data).decode('utf-8')
                            print(f"✅ Logo cargado desde: {logo_path}")
                            return logo_base64
                    except Exception as e:
                        print(f"⚠️ Error leyendo {logo_path}: {e}")
                        continue
                else:
                    print(f"🔍 Logo no encontrado: {logo_path}")
            
            print("❌ No se encontró el logo en ninguna ruta")
            return None
        
        # 1. Obtener cabecera de la cotización
        query_cabecera = """
            SELECT 
                c.id, c.empresa_id, c.numero_cotizacion, c.codigo_cotizacion,
                c.cliente_id, c.fecha_creacion, c.estado,
                c.subtotal, c.igv, c.total, c.notas,
                c.forma_pago, c.tiempo_entrega, c.almacen, c.validez_oferta,
                c.codigo_cotizacion, c.correlativo, c.condicion_pago,
                c.direccion_entrega, c.requerimiento, c.nota_cotizacion,
                c.descuento_porcentaje, c.descuento_monto, c.descuento_tipo,
                c.contacto_cliente, c.telefono_cliente, c.email_cliente,
                to_jsonb(c) ->> 'moneda' AS moneda, to_jsonb(c) ->> 'tipo_cambio' AS tipo_cambio,
                cl.id as cliente_id,
                cl.razon_social as cliente_razon_social,
                cl.numero_documento as cliente_ruc,
                cl.nombre_comercial as cliente_nombre_comercial,
                cl.codigo_cliente as cod_cliente,
                cl.direccion_fiscal as cliente_direccion,
                cl.telefono_contacto as cliente_telefono,
                cl.nombre_contacto as cliente_contacto,
                cl.email_contacto as cliente_email
            FROM cotizaciones c
            LEFT JOIN clientes cl ON cl.id = c.cliente_id::integer
            WHERE c.id = %s
        """
        cabecera = db_query(query_cabecera, (id,))
        
        if not cabecera:
            return jsonify({'success': False, 'error': 'Cotización no encontrada'}), 404
        
        c = cabecera[0]
        
        # 2. Obtener productos de la cotización
        query_productos = """
            SELECT 
                d.id, d.producto_id, d.cantidad,
                d.precio_venta_unitario, d.subtotal_venta,
                d.descuento_porcentaje, d.precio_venta_con_descuento,
                d.subtotal_venta_con_descuento,
                p.codigo, p.descripcion, p.descripcion_larga,
                p.modelo, p.marca, p.unidad as um
            FROM cotizacion_detalle d
            LEFT JOIN productos p ON p.id = d.producto_id
            WHERE d.cotizacion_id = %s
        """
        productos = db_query(query_productos, (id,))
        
        # 3. Preparar datos para el PDF
        from decimal import Decimal
        
        # Datos del cliente
        cliente_razon_social = c.get('cliente_razon_social') or c.get('cliente_nombre_comercial') or 'Cliente'
        cliente_ruc = c.get('cliente_ruc') or '---'
        cliente_direccion = c.get('cliente_direccion') or c.get('direccion_entrega') or '---'
        
        # Calcular totales
        subtotal = float(c.get('subtotal', 0))
        igv = float(c.get('igv', 0))
        total = float(c.get('total', 0))
        descuento_monto = float(c.get('descuento_monto', 0))
        
        # Preparar productos
        productos_list = []
        for idx, p in enumerate(productos or [], 1):
            precio_unitario = float(p.get('precio_venta_unitario', 0))
            cantidad = float(p.get('cantidad', 1))
            subtotal_producto = float(p.get('subtotal_venta', 0))
            descuento_pct = float(p.get('descuento_porcentaje', 0))
            subtotal_desc = float(p.get('subtotal_venta_con_descuento', subtotal_producto))
            
            productos_list.append({
                'item': idx,
                'codigo': p.get('codigo', '---'),
                'descripcion': p.get('descripcion') or p.get('descripcion_larga') or 'Producto sin descripción',
                'modelo': p.get('modelo') or '-',
                'marca': p.get('marca', ''),
                'unidad': p.get('um', 'NIU'),
                'cantidad': cantidad,
                'precio_venta_unitario': precio_unitario,
                'subtotal_venta': subtotal_producto,
                'descuento_porcentaje': descuento_pct,
                'subtotal_venta_desc': subtotal_desc
            })
        
        # Calcular si hay descuentos
        hay_descuentos = any(p.get('descuento_porcentaje', 0) > 0 for p in productos_list) or descuento_monto > 0
        
        # Fechas
        fecha_actual = datetime.now().strftime('%d/%m/%Y')
        hora_actual = datetime.now().strftime('%H:%M')
        
        # Obtener logo en base64
        emp = marca_pdf(c.get('empresa_id'))
        logo_base64 = emp['logo_src'].split('base64,', 1)[1] if 'base64,' in emp['logo_src'] else None
        print(f"📷 Logo cargado: {'Sí' if logo_base64 else 'No'}")
        
        # 4. Preparar datos para el template
        datos_pdf = {
            'codigo_cotizacion': c.get('codigo_cotizacion') or c.get('numero_cotizacion', 'COT-000001'),
            'fecha_actual': fecha_actual,
            'hora_actual': hora_actual,
            'logo_base64': logo_base64,
            'logo_mime': emp['logo_src'][5:emp['logo_src'].find(';')] if logo_base64 else 'image/png',
            'emp_nombre': emp['nombre'], 'emp_ruc': emp['ruc'], 'emp_corto': emp['corto'],
            'emp_telefono': emp['telefono'], 'emp_email': emp['email'], 'emp_web': emp['web'],
            'emp_web_corta': emp['web_corta'], 'emp_color': emp['color'], 'emp_cuentas': [cb for cb in (emp.get('cuentas') or []) if codigo_moneda(cb.get('moneda')) == 'PEN'],  # Erika 25/10: la cuenta en dólares no va en la cotización
            # 24/10/2026 (Erika): cotización en dólares -> US$ en el PDF
            'sim': 'US$' if codigo_moneda(c.get('moneda')) == 'USD' else 'S/',
            'cliente_razon_social': cliente_razon_social,
            'cliente_ruc': cliente_ruc,
            'cliente_direccion': cliente_direccion,
            'cliente_contacto': c.get('cliente_contacto') or c.get('contacto_cliente') or '---',
            'email_contacto_cliente': c.get('cliente_email') or c.get('email_cliente') or '---',
            'telefono_contacto': c.get('cliente_telefono') or c.get('telefono_cliente') or '---',
            'numero_requerimiento': c.get('requerimiento') or '---',
            'asesor_comercial': 'Helen Blas Príncipe',
            'email_contacto': emp['email'],
            'telefono_contacto_user': '999932051',
            'condicion_pago': c.get('condicion_pago') or c.get('forma_pago') or 'Contado',
            'tiempo_entrega': c.get('tiempo_entrega') or '5 días hábiles',
            'direccion_entrega': c.get('direccion_entrega') or cliente_direccion,
            'validez_oferta': c.get('validez_oferta') or '15 días',
            'productos': productos_list,
            'total_subtotal_venta': subtotal,
            'total_descuento_subtotal': descuento_monto,
            'total_subtotal_venta_desc': subtotal - descuento_monto,
            'summary_igv': igv,
            'summary_total_venta': total,
            'hay_descuentos': hay_descuentos
        }
        
        print(f"📊 Datos preparados: {len(productos_list)} productos, Total: {total}")
        
        # 5. Template HTML - CON FONDO ROJO SUAVE EN ENCABEZADO Y TOTAL EN AZUL CHIYÓN
        template_html = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Cotización - {{ emp_nombre }}</title>
    <style>
        @page {
            size: A4;
            margin: 1.2cm;
        }
        * { 
            margin: 0; 
            padding: 0; 
            box-sizing: border-box; 
        }
        body { 
            font-family: 'Helvetica', Arial, sans-serif;
            font-size: 9.5px; 
            color: #333333;
            line-height: 1.6; 
            background: #ffffff; 
        }
        
        /* ===== COLORES CORPORATIVOS ===== */
        .color-rojo { color: {{ emp_color }}; }
        .color-rojo-oscuro { color: #990000; }
        .color-azul-chiyon { color: #0033A0; }
        .border-rojo { border-color: {{ emp_color }}; }
        
        /* ===== HEADER CON BORDE ROJO ===== */
        .header-superior {
            display: flex;
            justify-content: space-between;
            align-items: stretch;
            margin-bottom: 12px;
            gap: 20px;
            padding-bottom: 8px;
            border-bottom: 2px solid {{ emp_color }};
        }
        .empresa-izquierda {
            flex: 1;
            display: flex;
            align-items: center;
            gap: 18px;
        }
        .empresa-izquierda .logo-container {
            flex-shrink: 0;
            width: 90px;
            height: 65px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .empresa-izquierda .logo-container img {
            max-height: 60px;
            max-width: 100px;
            object-fit: contain;
        }
        .empresa-izquierda .info-texto {
            font-size: 8px;
            line-height: 1.5;
            color: #444444;
        }
        .empresa-izquierda .info-texto .nombre {
            font-size: 13px;
            font-weight: bold;
            text-transform: uppercase;
            color: #990000;
            letter-spacing: 0.5px;
            margin-bottom: 1px;
        }
        .empresa-izquierda .info-texto .ruc-line {
            font-size: 9px;
            font-weight: bold;
            color: #333333;
            margin-bottom: 1px;
        }
        .empresa-izquierda .info-texto .slogan {
            font-size: 8px;
            color: #666666;
            font-style: italic;
            margin-bottom: 1px;
        }
        .empresa-izquierda .info-texto .contacto-line {
            font-size: 7.5px;
            color: #555555;
        }
        
        .recuadro-derecha {
            flex-shrink: 0;
            border: 2px solid {{ emp_color }};
            border-radius: 10px;
            padding: 6px 18px;
            text-align: center;
            min-width: 180px;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }
        .recuadro-derecha .ruc {
            font-size: 9px;
            font-weight: bold;
            color: #333333;
        }
        .recuadro-derecha .titulo {
            font-size: 11px;
            font-weight: bold;
            letter-spacing: 1px;
            margin: 2px 0;
            color: #990000;
        }
        .recuadro-derecha .numero {
            font-size: 14px;
            font-weight: bold;
            color: {{ emp_color }};
        }
        
        /* ===== LAYOUT PRINCIPAL ===== */
        .layout-principal { 
            display: flex; 
            gap: 15px; 
            margin-bottom: 10px; 
        }
        .seccion-cliente, .seccion-condiciones { 
            flex: 1; 
            border: 1px solid #d5d5d5;
            border-radius: 8px;
            padding: 8px 12px; 
        }
        .seccion-cliente h3, .seccion-condiciones h3 { 
            color: #990000;
            border-bottom: 2px solid {{ emp_color }};
            padding-bottom: 3px; 
            font-size: 9.5px; 
            margin-top: 0; 
            margin-bottom: 6px; 
            font-weight: bold; 
            text-transform: uppercase;
        }
        .info-line, .condicion-line { 
            display: flex; 
            margin-bottom: 2px; 
            font-size: 8.5px; 
        }
        .info-label, .condicion-label { 
            width: 100px; 
            font-weight: bold; 
            color: #555555;
        }
        .info-value, .condicion-value { 
            flex: 1; 
            color: #333333;
        }
        
        /* ===== TEXTO INTRODUCTORIO ===== */
        .texto-introductorio { 
            margin: 8px 0; 
            padding: 6px 12px; 
            font-size: 8.5px; 
            line-height: 1.4; 
            text-align: justify; 
            border: 1px solid #e5e7eb;
            border-radius: 6px;
        }
        .texto-introductorio .saludo { 
            font-size: 9px; 
            font-weight: bold; 
            margin-bottom: 3px; 
            color: #990000;
        }
        
        /* ===== TABLA DE PRODUCTOS ===== */
        .tabla-productos { 
            width: 100%; 
            border-collapse: collapse; 
            margin: 8px 0; 
            font-size: 8px; 
        }
        
        /* 🔴 ENCABEZADO CON FONDO ROJO SUAVE */
        .tabla-productos th { 
            color: #333333;
            padding: 5px 4px; 
            border: 1px solid {{ emp_color }};
            font-weight: bold; 
            text-align: center; 
            vertical-align: middle; 
            background-color: #F8C8C8; /* Fondo rojo suave en todo el encabezado */
        }
        .tabla-productos td { 
            padding: 4px 4px; 
            border: 1px solid #d5d5d5; 
            vertical-align: middle; 
            color: #333333;
        }
        .tabla-productos tr:nth-child(even) td {
            background: #f9f9f9;
        }
        
        .col-item { text-align: center; width: 30px; }
        .col-codigo { text-align: left; width: 70px; }
        .col-descripcion { text-align: left; }
        .col-modelo { text-align: left; width: 55px; }
        .col-marca { text-align: left; width: 60px; }
        .col-unidad-medida { text-align: center; width: 50px; }
        .col-cantidad { text-align: center; width: 40px; }
        .col-valor-unitario { text-align: right; width: 80px; }
        .col-valor-total { 
            text-align: right; 
            width: 85px; 
            font-weight: bold; 
            color: #333333;
        }
        
        .numero-formateado { 
            text-align: right; 
            font-family: 'Courier New', monospace; 
            font-weight: bold; 
        }
        .text-center { text-align: center; }
        .text-left { text-align: left; }
        .text-right { text-align: right; }
        .fw-bold { font-weight: bold; }
        
        /* ===== SECCIÓN TOTALES ===== */
        .seccion-totales { 
            width: 280px; 
            margin-left: auto; 
            margin-right: 0; 
            margin-top: 8px; 
            margin-bottom: 10px; 
            border: 2px solid {{ emp_color }};
            border-radius: 8px;
            padding: 8px 12px; 
        }
        .total-line { 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            margin-bottom: 3px; 
            font-size: 8.5px; 
            gap: 8px; 
        }
        .total-line span:first-child { 
            white-space: nowrap; 
            color: #555555; 
        }
        .total-line .numero-formateado { 
            font-weight: bold; 
            white-space: nowrap; 
            color: #333333;
        }
        
        /* 🔵 TOTAL A PAGAR - AZUL CHIYÓN */
        .total-final { 
            border-top: 3px solid {{ emp_color }}; 
            padding-top: 8px; 
            margin-top: 6px; 
            font-weight: bold; 
            font-size: 14px;
            color: #0033A0;
        }
        .total-final .numero-formateado {
            font-size: 18px;
            color: #0033A0;
        }
        
        /* ===== NOTA ACLARATORIA ===== */
        .seccion-aclaratoria { 
            margin: 10px 0; 
            padding: 10px 16px; 
            border: 2px solid {{ emp_color }};
            border-radius: 8px;
            font-size: 8.5px; 
            text-align: justify;
            line-height: 1.6; 
        }
        .seccion-aclaratoria .titulo { 
            font-weight: bold; 
            font-size: 9.5px; 
            margin-bottom: 4px; 
            color: #990000; 
            text-align: center;
            text-transform: uppercase;
        }
        .seccion-aclaratoria .web-link { 
            color: #990000; 
            text-decoration: underline; 
            font-weight: bold; 
        }
        
        /* ===== CUENTAS BANCARIAS ===== */
        .cuentas-bancarias { 
            margin-top: 8px; 
            padding: 8px 14px; 
            border: 2px solid {{ emp_color }};
            border-radius: 8px;
            font-size: 8px; 
        }
        .cuentas-bancarias h3 { 
            color: #990000;
            border-bottom: 2px solid {{ emp_color }};
            padding-bottom: 3px; 
            font-size: 9.5px; 
            margin-top: 0; 
            margin-bottom: 6px; 
            text-transform: uppercase;
            text-align: center;
        }
        .cuenta-line { 
            margin-bottom: 4px;
            padding: 4px 0;
            text-align: center;
        }
        .cuenta-line .banco { 
            font-weight: bold; 
            color: #990000; 
            font-size: 10px;
        }
        .cuenta-line .tipo { 
            font-size: 8.5px; 
            color: #555555; 
        }
        .cuenta-line .numero { 
            font-size: 11px;
            color: #333333; 
            font-weight: bold; 
            letter-spacing: 0.5px;
        }
        .cuenta-line .cci { 
            font-size: 10px;
            color: #555555; 
            font-weight: bold;
            letter-spacing: 0.5px;
        }
        
        /* ===== CONTACTO FINAL ===== */
        .seccion-contacto { 
            margin-top: 12px; 
            border-top: 2px solid {{ emp_color }};
            padding-top: 10px; 
            text-align: left; 
            font-size: 8.5px; 
        }
        .contacto-nombre { 
            font-size: 10px; 
            font-weight: bold; 
            color: #990000;
            margin-bottom: 3px; 
        }
        .contacto-line { margin-bottom: 2px; color: #555555; }
        .web-link { color: #990000; text-decoration: underline; }
        
        .seccion-totales, .cuentas-bancarias, .seccion-aclaratoria, .seccion-contacto { 
            page-break-inside: avoid; 
            break-inside: avoid; 
        }
        .tabla-productos { page-break-inside: avoid; }
    </style>
</head>
<body>
    <!-- ============================================================ -->
    <!-- HEADER CON BORDE ROJO                                       -->
    <!-- ============================================================ -->
    <div class="header-superior">
        <div class="empresa-izquierda">
            <div class="logo-container">
                {% if logo_base64 %}
                <img src="data:{{ logo_mime }};base64,{{ logo_base64 }}" alt="Logo {{ emp_corto }}">
                {% else %}
                <div style="font-size:26px;font-weight:900;color:{{ emp_color }};padding-top:12px;">{{ emp_corto }}</div>
                {% endif %}
            </div>
            <div class="info-texto">
                <div class="nombre">{{ emp_nombre }}</div>
                <div class="ruc-line">RUC: {{ emp_ruc }}</div>
                <div class="slogan">Soluciones integrales en abastecimientos</div>
                <div class="contacto-line">{% if emp_telefono %}Telf: {{ emp_telefono }} | {% endif %}Email: {{ emp_email }}</div>
                {% if emp_web %}<div class="contacto-line">Web: {{ emp_web }}</div>{% endif %}
            </div>
        </div>
        <div class="recuadro-derecha">
            <div class="ruc">R.U.C. Nº {{ emp_ruc }}</div>
            <div class="titulo">COTIZACIÓN</div>
            <div class="numero">{{ codigo_cotizacion }}</div>
        </div>
    </div>

    <!-- ============================================================ -->
    <!-- CLIENTE Y CONDICIONES                                        -->
    <!-- ============================================================ -->
    <div class="layout-principal">
        <div class="seccion-cliente">
            <h3>INFORMACIÓN DEL CLIENTE</h3>
            <div class="info-line"><span class="info-label">Cliente:</span><span class="info-value">{{ cliente_razon_social }}</span></div>
            <div class="info-line"><span class="info-label">RUC / DNI:</span><span class="info-value">{{ cliente_ruc }}</span></div>
            <div class="info-line"><span class="info-label">Dirección:</span><span class="info-value">{{ cliente_direccion }}</span></div>
            <div class="info-line"><span class="info-label">Teléfono:</span><span class="info-value">{{ telefono_contacto|default('-') }}</span></div>
            <div class="info-line"><span class="info-label">Atención:</span><span class="info-value">{{ cliente_contacto|default('-') }}</span></div>
            <div class="info-line"><span class="info-label">Correo:</span><span class="info-value">{{ email_contacto_cliente|default('-') }}</span></div>
            <div class="info-line"><span class="info-label">N° Requerimiento:</span><span class="info-value">{{ numero_requerimiento|default('-') }}</span></div>
        </div>
        <div class="seccion-condiciones">
            <h3>CONDICIONES COMERCIALES</h3>
            <!-- ✅ CAMBIO 1: "Ejecutiva Comercial:" -->
            <div class="condicion-line"><span class="condicion-label">Ejecutiva Comercial:</span><span class="condicion-value">{{ asesor_comercial }}</span></div>
            <div class="condicion-line"><span class="condicion-label">E-mail:</span><span class="condicion-value">{{ email_contacto }}</span></div>
            <div class="condicion-line"><span class="condicion-label">Teléfono:</span><span class="condicion-value">{{ telefono_contacto_user }}</span></div>
            <div class="condicion-line"><span class="condicion-label">Condición Pago:</span><span class="condicion-value">{{ condicion_pago }}</span></div>
            <div class="condicion-line"><span class="condicion-label">Tiempo Entrega:</span><span class="condicion-value">{{ tiempo_entrega }}</span></div>
            <div class="condicion-line"><span class="condicion-label">Dirección Entrega:</span><span class="condicion-value">{{ direccion_entrega }}</span></div>
            <div class="condicion-line"><span class="condicion-label">Validez Oferta:</span><span class="condicion-value">{{ validez_oferta }}</span></div>
            <div class="condicion-line"><span class="condicion-label">Fecha:</span><span class="condicion-value">{{ fecha_actual }}</span></div>
            <div class="condicion-line"><span class="condicion-label">Hora:</span><span class="condicion-value">{{ hora_actual|default('00:00') }}</span></div>
        </div>
    </div>

    <!-- ============================================================ -->
    <!-- TEXTO INTRODUCTORIO                                          -->
    <!-- ============================================================ -->
    <div class="texto-introductorio">
        <div class="saludo">Estimado Cliente,</div>
        La presente tiene como objeto poner a su consideración nuestra oferta detallada según su requerimiento, agradecemos por confiar en nuestros productos:
    </div>

    <!-- ============================================================ -->
    <!-- TABLA DE PRODUCTOS - ENCABEZADO CON FONDO ROJO SUAVE        -->
    <!-- ============================================================ -->
    <table class="tabla-productos">
        <thead>
            <tr>
                <th class="col-item">Item</th>
                <th class="col-codigo">Código Producto</th>
                <th class="col-descripcion">Descripción</th>
                <th class="col-modelo">Modelo</th>
                <th class="col-marca">Marca</th>
                <th class="col-unidad-medida">Unidad Medida</th>
                <th class="col-cantidad">Cantidad</th>
                <th class="col-valor-unitario">Valor Venta Unit {{ sim }}</th>
                <th class="col-valor-total">Valor Venta Total {{ sim }}</th>
            </tr>
        </thead>
        <tbody>
            {% if productos %}
                {% for producto in productos %}
                <tr>
                    <td class="text-center">{{ producto.item }}</td>
                    <td>{{ producto.codigo|default('-') }}</td>
                    <td class="descripcion">{{ producto.descripcion }}</td>
                    <td>{{ producto.modelo|default('-') }}</td>
                    <td>{{ producto.marca|default('-') }}</td>
                    <td class="text-center">{{ producto.unidad|default('Unid') }}</td>
                    <td class="text-center">{{ "%.0f"|format(producto.cantidad|default(0)) }}</td>
                    <td class="numero-formateado">{{ "%.2f"|format(producto.precio_venta_unitario|default(0)) }}</td>
                    <td class="numero-formateado fw-bold">{{ "%.2f"|format(producto.subtotal_venta_desc|default(producto.subtotal_venta|default(0))) }}</td>
                </tr>
                {% endfor %}
            {% else %}
                <tr><td colspan="9" class="text-center" style="padding: 15px;">No hay productos registrados en esta cotización</td></tr>
            {% endif %}
        </tbody>
    </table>

    <!-- ============================================================ -->
    <!-- NOTA ACLARATORIA                                             -->
    <!-- ============================================================ -->
    <div class="seccion-aclaratoria">
        <div class="titulo">📌 NOTA ACLARATORIA</div>
        La validez de esta oferta está sujeta a la disponibilidad de inventario en el momento de la confirmación del pedido.<br>
        {% if hay_descuentos %}<strong>Esta oferta incluye un descuento de {{ sim }} {{ '%.2f'|format(total_descuento_subtotal|float) }} aplicado en el valor de venta.</strong><br>{% endif %}
        {% if emp_web %}Para más información visítanos en 
        <a href="{{ emp_web }}" class="web-link">{{ emp_web_corta }}</a>{% endif %}
    </div>

    <!-- ============================================================ -->
    <!-- TOTALES - TOTAL A PAGAR EN AZUL CHIYÓN                      -->
    <!-- ============================================================ -->
    <div class="seccion-totales">
        <div class="total-line"><span>Subtotal ({{ sim }}):</span><span class="numero-formateado">{{ sim }} {{ "%.2f"|format(total_subtotal_venta|default(0)) }}</span></div>
        {% if hay_descuentos %}
        <div class="total-line"><span>Descuentos aplicados ({{ sim }}):</span><span class="numero-formateado" style="color:{{ emp_color }};">- {{ sim }} {{ "%.2f"|format(total_descuento_subtotal|default(0)) }}</span></div>
        {% endif %}
        <div class="total-line"><span>Subtotal con descuento ({{ sim }}):</span><span class="numero-formateado">{{ sim }} {{ "%.2f"|format(total_subtotal_venta_desc|default(0)) }}</span></div>
        <div class="total-line"><span>IGV (18%):</span><span class="numero-formateado">{{ sim }} {{ "%.2f"|format(summary_igv|default(0)) }}</span></div>
        <!-- ✅ CAMBIO 2: TOTAL A PAGAR en azul chiyón -->
        <div class="total-line total-final"><span><strong>TOTAL A PAGAR:</strong></span><span class="numero-formateado"><strong>{{ sim }} {{ "%.2f"|format(summary_total_venta|default(0)) }}</strong></span></div>
    </div>

    <!-- ============================================================ -->
    <!-- CUENTAS BANCARIAS                                            -->
    <!-- ============================================================ -->
    <div class="cuentas-bancarias">
        <h3>💰 CUENTAS BANCARIAS</h3>
        {% for cb in emp_cuentas %}
        <div class="cuenta-line">
            <span class="banco">🏛️ {{ cb.banco }}</span>
            <span class="tipo">| {% if cb.moneda %}{{ 'Dólares' if cb.moneda|upper in ('USD', 'US$', 'DOLARES', 'DÓLARES') else 'Soles' }}{% endif %}</span><br>
            <span class="numero">Cuenta Corriente N° {{ cb.numero_cuenta }}</span><br>
            {% if cb.cci %}<span class="cci">CCI: {{ cb.cci }}</span>{% endif %}
        </div>
        {% else %}{% if emp_ruc == '20602095704' %}
        <div class="cuenta-line">
            <span class="banco">🏛️ BBVA</span>
            <span class="tipo">| Soles</span><br>
            <span class="numero">Cuenta Corriente N° 0011-0319-1601-00022197</span><br>
            <span class="cci">CCI: 011-319-000100022197-16</span>
        </div>
        {% endif %}{% endfor %}
    </div>

    <!-- ============================================================ -->
    <!-- CONTACTO FINAL                                              -->
    <!-- ============================================================ -->
    <div class="seccion-contacto">
        <div class="contacto-nombre">Cordialmente,</div>
        <div class="contacto-nombre">HELLEN BLAS PRINCIPE</div>
        <div class="contacto-line">Ejecutiva Comercial</div>
        <div class="contacto-line">{{ emp_corto }}</div>
        {% if emp_telefono %}<div class="contacto-line">📞 (+51) {{ emp_telefono }}</div>{% endif %}
        <div class="contacto-line">✉ {{ emp_email }}</div>
        {% if emp_web %}<div class="contacto-line">🌐 {{ emp_web_corta }}</div>{% endif %}
    </div>

</body>
</html>'''
        
        # Renderizar el HTML con los datos
        html_content = render_template_string(template_html, **datos_pdf)
        
        # 6. Generar el PDF con WeasyPrint
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            pdf_path = tmp_file.name
        
        # Generar el PDF
        HTML(string=html_content).write_pdf(pdf_path)
        
        print(f"✅ PDF generado: {pdf_path}")
        
        # 7. Devolver el PDF como descarga
        nombre_archivo = f"cotizacion_{c.get('codigo_cotizacion', 'sin_numero')}_{datetime.now().strftime('%Y%m%d')}.pdf"
        
        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=nombre_archivo,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        print(f"❌ Error generando PDF: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
# ventas.py - Reemplazar la función generar_pdf_guia_endpoint

@ventas_bp.route('/ventas/api/guias/<int:guia_id>/pdf', methods=['GET'])
@login_required
def generar_pdf_guia_endpoint(guia_id):
    """Genera el PDF de una Guía de Remisión usando PDFGenerator"""
    try:
        print(f"📄 Generando PDF para guía ID: {guia_id}")
        
        # 1. Obtener la guía con TODOS los campos
        query = """
            SELECT 
                id, serie, numero, fecha_emision, fecha_traslado,
                ruc_remitente, remitente_nombre, remitente_direccion,
                remitente_ubigeo, ruc_destinatario, destinatario_nombre,
                destinatario_direccion, destinatario_ubigeo,
                modalidad_transporte, placa_vehiculo, conductor_dni,
                conductor_nombre, licencia_conductor, transportista_ruc,
                transportista_nombre, motivo_traslado, documento_asociado,
                orden_compra_cliente, factura,
                peso_total, items_json, observaciones, estado_sunat,
                creado_por, created_at, updated_at, empresa_id
            FROM guias_remision
            WHERE id = %s
        """
        guia_result = db_query(query, (guia_id,))
        
        if not guia_result:
            return jsonify({'error': 'Guía no encontrada'}), 404
        
        guia = guia_result[0]
        print(f"✅ Guía encontrada: {guia.get('serie')}-{guia.get('numero')}")
        
        # 2. Parsear items_json correctamente
        items = []
        items_json = guia.get('items_json')
        if items_json:
            try:
                if isinstance(items_json, str):
                    items = json.loads(items_json)
                elif isinstance(items_json, (list, dict)):
                    items = items_json
                else:
                    items = []
            except Exception as e:
                print(f"⚠️ Error parseando items_json: {e}")
                items = []
        
        print(f"📦 Items encontrados: {len(items)}")
        
        # 3. Obtener datos del cliente desde la base de datos (si es necesario)
        cliente_data = {}
        ruc_destinatario = guia.get('ruc_destinatario')
        if ruc_destinatario:
            try:
                query_cliente = """
                    SELECT razon_social, direccion_fiscal, telefono_contacto, 
                           nombre_contacto, email_contacto
                    FROM clientes 
                    WHERE numero_documento = %s
                    LIMIT 1
                """
                cliente_result = db_query(query_cliente, (ruc_destinatario,))
                if cliente_result:
                    cliente_data = cliente_result[0]
            except Exception as e:
                print(f"⚠️ Error obteniendo datos del cliente: {e}")
        
        # 4. Preparar datos para el PDFGenerator
        from pdf_generator import pdf_generator
        
        # Fechas
        fecha_emision = guia.get('fecha_emision')
        if fecha_emision and isinstance(fecha_emision, datetime):
            fecha_emision = fecha_emision.strftime('%d/%m/%Y %H:%M')
        elif fecha_emision and isinstance(fecha_emision, str):
            try:
                dt = datetime.fromisoformat(fecha_emision.replace('Z', '+00:00'))
                fecha_emision = dt.strftime('%d/%m/%Y %H:%M')
            except:
                pass
        
        fecha_traslado = guia.get('fecha_traslado')
        if fecha_traslado and isinstance(fecha_traslado, datetime):
            fecha_traslado = fecha_traslado.strftime('%d/%m/%Y')
        elif fecha_traslado and isinstance(fecha_traslado, str):
            try:
                dt = datetime.fromisoformat(fecha_traslado.replace('Z', '+00:00'))
                fecha_traslado = dt.strftime('%d/%m/%Y')
            except:
                pass
        
        # Formatear items para el PDF
        items_formateados = []
        for idx, item in enumerate(items, 1):
            if isinstance(item, dict):
                items_formateados.append({
                    'item': idx,
                    'codigo': item.get('codigo', ''),
                    'descripcion': item.get('producto', item.get('descripcion', '')),
                    'marca': item.get('marca', ''),
                    'modelo': item.get('modelo', ''),
                    'unidad': item.get('um', 'NIU'),
                    'cantidad': float(item.get('cantidad', 1)),
                    'peso': float(item.get('peso_unitario', 0))
                })
            elif isinstance(item, list):
                # Si es un array [codigo, descripcion, marca, modelo, cantidad, um, peso]
                items_formateados.append({
                    'item': idx,
                    'codigo': item[0] if len(item) > 0 else '',
                    'descripcion': item[1] if len(item) > 1 else '',
                    'marca': item[2] if len(item) > 2 else '',
                    'modelo': item[3] if len(item) > 3 else '',
                    'unidad': item[4] if len(item) > 4 else 'NIU',
                    'cantidad': float(item[5]) if len(item) > 5 else 1,
                    'peso': float(item[6]) if len(item) > 6 else 0
                })
        
        # Datos completos para el PDF
        datos_guia = {
            'tipo_documento': 'guia_remision',
            'serie': guia.get('serie', 'T001'),
            'numero': guia.get('numero', ''),
            'orden_compra_cliente': guia.get('orden_compra_cliente', ''),  # <--- IMPORTANTE
    'factura': guia.get('factura', ''),                            # <--- IMPORTANTE
    'nro_cotizacion': guia.get('documento_asociado', guia.get('cotizacion_numero', '')), 
            # ============================================================
            # REMITENTE (DATOS FIJOS)
            # ============================================================
            'ruc_remitente': guia.get('ruc_remitente', '20602095704'),
            'remitente_nombre': guia.get('remitente_nombre', 'KCF CORPORACION E.I.R.L'),
            'remitente_direccion': guia.get('remitente_direccion', 'JR. LAS ALMENDRAS VERDES NRO. 284 URB. VIRGEN DEL ROSARIO LIMA - LIMA - SAN MARTIN DE PORRES'),
            'remitente_ubigeo': guia.get('remitente_ubigeo', '150139'),
            'remitente_departamento': 'LIMA',
            'remitente_provincia': 'LIMA',
            'remitente_distrito': 'SAN MARTIN DE PORRES',
            
            # ============================================================
            # DESTINATARIO (DATOS DEL CLIENTE)
            # ============================================================
            'ruc_destinatario': guia.get('ruc_destinatario', ''),
            'destinatario_nombre': guia.get('destinatario_nombre', ''),
            'destinatario_direccion': guia.get('destinatario_direccion', ''),
            'destinatario_ubigeo': guia.get('destinatario_ubigeo', ''),
            'destinatario_departamento': guia.get('destinatario_departamento', ''),
            'destinatario_provincia': guia.get('destinatario_provincia', ''),
            'destinatario_distrito': guia.get('destinatario_distrito', ''),
            
            # ============================================================
            # DATOS DE TRANSPORTE
            # ============================================================
            'modalidad_transporte': guia.get('modalidad_transporte', 'PRIVADO'),
            'transportista_nombre': guia.get('transportista_nombre', ''),
            'transportista_ruc': guia.get('transportista_ruc', ''),
            'transportista_direccion': guia.get('transportista_direccion', ''),
            
            # ============================================================
            # DATOS DEL VEHÍCULO Y CONDUCTOR
            # ============================================================
            'placa_vehiculo': guia.get('placa_vehiculo', ''),
            'conductor_nombre': guia.get('conductor_nombre', ''),
            'conductor_dni': guia.get('conductor_dni', ''),
            'licencia_conductor': guia.get('licencia_conductor', ''),
            'telefono_conductor': guia.get('telefono_conductor', ''),
            
            # ============================================================
            # DATOS DEL TRASLADO
            # ============================================================
            'fecha_emision': fecha_emision,
            'fecha_traslado': fecha_traslado,
            'fecha_inicio_traslado': fecha_traslado,
            'motivo_traslado': guia.get('motivo_traslado', '01'),
            'motivo_descripcion': obtener_descripcion_motivo(guia.get('motivo_traslado', '01')),
            'peso_total': float(guia.get('peso_total', 0)),
            'numero_bultos': int(guia.get('numero_bultos', 1)),
            'unidad_peso': guia.get('unidad_peso_bruto', 'KGM'),
            'orden_compra_cliente': guia.get('orden_compra_cliente', ''),
            'documento_asociado': guia.get('documento_asociado', ''),
            'orden_compra_cliente': guia.get('orden_compra_cliente',''),
            'factura': guia.get('factura',''),
            'observaciones': guia.get('observaciones', ''),
            
            # ============================================================
            # PRODUCTOS
            # ============================================================
            'items': items_formateados
        }
        
        # 5. Generar el PDF
        datos_guia['empresa_pdf'] = marca_pdf(guia.get('empresa_id') or empresa_id_por_ruc(guia.get('ruc_remitente')))
        pdf_path = pdf_generator.generar_pdf_universal(datos_guia)
        
        if not pdf_path:
            return jsonify({'error': 'Error al generar el PDF'}), 500
        
        # 6. Retornar el PDF
        from flask import send_file
        filename = f"Guia_{guia.get('serie', 'T001')}_{guia.get('numero', '0001')}.pdf"
        
        return send_file(
            pdf_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        print(f"❌ Error generando PDF de guía: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


def obtener_descripcion_motivo(codigo):
    """Obtiene la descripción del motivo de traslado según el código SUNAT"""
    motivos = {
        '01': 'VENTA',
        '02': 'COMPRA',
        '03': 'TRASLADO ENTRE ESTABLECIMIENTOS',
        '04': 'CONSIGNACIÓN',
        '05': 'DEVOLUCIÓN',
        '06': 'EXPORTACIÓN',
        '07': 'IMPORTACIÓN',
        '08': 'DONACIÓN',
        '09': 'TRASLADO POR CUENTA DE TERCEROS',
        '10': 'TRASLADO PARA TRANSFORMACIÓN',
        '11': 'TRASLADO POR REPARACIÓN',
        '12': 'TRASLADO POR GARANTÍA',
        '13': 'TRASLADO POR CONSIGNACIÓN PARA VENTA',
        '14': 'TRASLADO POR CONSIGNACIÓN PARA TRANSFORMACIÓN',
        '15': 'TRASLADO POR CONSIGNACIÓN PARA REPARACIÓN',
        '16': 'TRASLADO POR DEVOLUCIÓN DE CONSIGNACIÓN',
        '17': 'TRASLADO POR PERMUTA',
        '18': 'TRASLADO POR COMODATO',
        '19': 'TRASLADO POR ARRENDAMIENTO',
        '20': 'TRASLADO POR ANTICIPO DE VENTA',
        '21': 'TRASLADO POR ANTICIPO DE COMPRA',
        '22': 'TRASLADO POR MAQUILA',
        '23': 'TRASLADO POR CONSIGNACIÓN PARA MAQUILA',
        '24': 'TRASLADO POR DEVOLUCIÓN DE MAQUILA'
    }
    return motivos.get(codigo, codigo)



@ventas_bp.route('/ventas/api/guias/<int:guia_id>/pdf/preview', methods=['GET'])
@login_required
def preview_pdf_guia(guia_id):
    """Vista previa del PDF de guía"""
    try:
        print(f"👁️ Vista previa PDF para guía ID: {guia_id}")
        
        # Usar la misma lógica que generar_pdf_guia_endpoint pero sin forzar descarga
        # Reutilizar la función de generación
        from flask import send_file
        from pdf_generator import pdf_generator
        
        query = """
            SELECT 
                id, serie, numero, fecha_emision, fecha_traslado,
                ruc_remitente, remitente_nombre, remitente_direccion,
                remitente_ubigeo, ruc_destinatario, destinatario_nombre,
                destinatario_direccion, destinatario_ubigeo,
                modalidad_transporte, placa_vehiculo, conductor_dni,
                conductor_nombre, licencia_conductor, transportista_ruc,
                transportista_nombre, motivo_traslado, documento_asociado,
                orden_compra_cliente, factura,
                peso_total, items_json, observaciones, estado_sunat,
                creado_por, created_at, updated_at, empresa_id
            FROM guias_remision
            WHERE id = %s
        """
        guia_result = db_query(query, (guia_id,))
        
        if not guia_result:
            return jsonify({'error': 'Guía no encontrada'}), 404
        
        guia = guia_result[0]
        
        # Preparar datos (misma lógica que la función principal)
        # ... (código para preparar datos_guia igual que arriba)
        
        # Generar PDF
        from pdf_generator import pdf_generator
        datos_guia = preparar_datos_guia_pdf(guia)  # Función auxiliar
        
        datos_guia['empresa_pdf'] = marca_pdf(guia.get('empresa_id') or empresa_id_por_ruc(guia.get('ruc_remitente')))
        pdf_path = pdf_generator.generar_pdf_universal(datos_guia)
        
        if not pdf_path:
            return jsonify({'error': 'Error al generar el PDF'}), 500
        
        return send_file(
            pdf_path,
            mimetype='application/pdf',
            as_attachment=False  # Vista previa
        )
        
    except Exception as e:
        print(f"❌ Error generando vista previa: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def preparar_datos_guia_pdf(guia):
    """Prepara los datos de la guía para el PDFGenerator"""
    from datetime import datetime
    
    # Parsear items
    items = []
    items_json = guia.get('items_json')
    if items_json:
        try:
            if isinstance(items_json, str):
                items = json.loads(items_json)
            elif isinstance(items_json, (list, dict)):
                items = items_json
        except:
            items = []
    
    # Formatear items
    items_formateados = []
    for idx, item in enumerate(items, 1):
        if isinstance(item, dict):
            items_formateados.append({
                'item': idx,
                'codigo': item.get('codigo', ''),
                'descripcion': item.get('producto', item.get('descripcion', '')),
                'marca': item.get('marca', ''),
                'modelo': item.get('modelo', ''),
                'unidad': item.get('um', 'NIU'),
                'cantidad': float(item.get('cantidad', 1)),
                'peso': float(item.get('peso_unitario', 0))
            })
        elif isinstance(item, list):
            items_formateados.append({
                'item': idx,
                'codigo': item[0] if len(item) > 0 else '',
                'descripcion': item[1] if len(item) > 1 else '',
                'marca': item[2] if len(item) > 2 else '',
                'modelo': item[3] if len(item) > 3 else '',
                'unidad': item[4] if len(item) > 4 else 'NIU',
                'cantidad': float(item[5]) if len(item) > 5 else 1,
                'peso': float(item[6]) if len(item) > 6 else 0
            })
    
    # Fechas
    fecha_emision = guia.get('fecha_emision')
    if fecha_emision and isinstance(fecha_emision, datetime):
        fecha_emision = fecha_emision.strftime('%d/%m/%Y %H:%M')
    elif fecha_emision and isinstance(fecha_emision, str):
        try:
            dt = datetime.fromisoformat(fecha_emision.replace('Z', '+00:00'))
            fecha_emision = dt.strftime('%d/%m/%Y %H:%M')
        except:
            pass
    
    return {
        'tipo_documento': 'guia_remision',
        'serie': guia.get('serie', 'T001'),
        'numero': guia.get('numero', ''),
        'ruc_remitente': guia.get('ruc_remitente', '20602095704'),
        'remitente_nombre': guia.get('remitente_nombre', 'KCF CORPORACION E.I.R.L'),
        'remitente_direccion': guia.get('remitente_direccion', 'JR. LAS ALMENDRAS VERDES NRO. 284 URB. VIRGEN DEL ROSARIO LIMA - LIMA - SAN MARTIN DE PORRES'),
        'remitente_ubigeo': guia.get('remitente_ubigeo', '150139'),
        'ruc_destinatario': guia.get('ruc_destinatario', ''),
        'destinatario_nombre': guia.get('destinatario_nombre', ''),
        'destinatario_direccion': guia.get('destinatario_direccion', ''),
        'destinatario_ubigeo': guia.get('destinatario_ubigeo', ''),
        'modalidad_transporte': guia.get('modalidad_transporte', 'PRIVADO'),
        'transportista_nombre': guia.get('transportista_nombre', ''),
        'transportista_ruc': guia.get('transportista_ruc', ''),
        'placa_vehiculo': guia.get('placa_vehiculo', ''),
        'conductor_nombre': guia.get('conductor_nombre', ''),
        'conductor_dni': guia.get('conductor_dni', ''),
        'licencia_conductor': guia.get('licencia_conductor', ''),
        'fecha_emision': fecha_emision,
        'fecha_traslado': guia.get('fecha_traslado'),
        'motivo_traslado': guia.get('motivo_traslado', '01'),
        'peso_total': float(guia.get('peso_total', 0)),
        'numero_bultos': int(guia.get('numero_bultos', 1)),
        'unidad_peso': guia.get('unidad_peso_bruto', 'KGM'),
        'documento_asociado': guia.get('documento_asociado', ''),
        'orden_compra_cliente' : guia.get('orden_compra_cliente',''),
        'factura' : guia.get('factura',''),
        'observaciones': guia.get('observaciones', ''),
        'items': items_formateados
    }
# ============================================================
# CLIENTES - BUSCAR POR RUC (para ventas)
# ============================================================

@ventas_bp.route('/ventas/api/clientes/buscar', methods=['GET'])
@login_required
def api_clientes_buscar_por_ruc():
    """Busca un cliente por su RUC en la base de datos"""
    try:
        ruc = request.args.get('ruc', '').strip()
        
        if not ruc or len(ruc) != 11:
            return jsonify({'success': False, 'error': 'RUC inválido, debe tener 11 dígitos'}), 400
        
        # Usar la función de database.py
        from database import buscar_cliente_por_ruc
        
        cliente = buscar_cliente_por_ruc(ruc)
        
        if cliente:
            # Obtener contactos adicionales si es necesario
            contactos = db_query("""
                SELECT nombre_contacto, email, telefono, cargo, principal
                FROM clientes_contactos 
                WHERE cliente_id = %s
                ORDER BY principal DESC
            """, (cliente['id'],))
            
            # Obtener puntos de entrega
            puntos = db_query("""
                SELECT nombre_punto, direccion, condicion_pago, responsable, telefono_contacto, principal
                FROM clientes_puntos_entrega 
                WHERE cliente_id = %s
            """, (cliente['id'],))
            
            return jsonify({
                'success': True,
                'data': {
                    'id': cliente['id'],
                    'tipo_documento': cliente.get('tipo_documento', 'RUC'),
                    'numero_documento': cliente.get('numero_documento'),
                    'razon_social': cliente.get('razon_social'),
                    'nombre_comercial': cliente.get('nombre_comercial'),
                    'direccion_fiscal': cliente.get('direccion_fiscal'),
                    'codigo_cliente': cliente.get('codigo_cliente'),
                    'nombre_contacto': cliente.get('nombre_contacto'),
                    'telefono_contacto': cliente.get('telefono_contacto'),
                    'email_contacto': cliente.get('email_contacto'),
                    'estado': cliente.get('estado', 'Activo'),
                    'contactos': contactos,
                    'puntos_entrega': puntos
                }
            })
        
        return jsonify({'success': False, 'error': 'Cliente no encontrado'}), 404
        
    except Exception as e:
        print(f"❌ Error en api_clientes_buscar_por_ruc: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 
        
@ventas_bp.route('/ventas/api/cotizaciones/buscar', methods=['GET'])
@login_required
def api_cotizaciones_buscar():
    """Busca cotizaciones por texto (N° cotización, RUC, razón social) para el buscador del modal PV"""
    try:
        q = request.args.get('q', '').strip()
        if not q or len(q) < 2:
            return jsonify({'success': True, 'data': []})
        
        # Buscar en la base de datos
        query = """
            SELECT 
                c.id, c.numero_cotizacion, c.fecha_creacion, c.estado,
                c.total, c.subtotal, c.igv, c.condicion_pago,
                c.direccion_entrega, c.tiempo_entrega, c.validez_oferta,
                c.vendedor,
                cl.id as cliente_id,
                cl.razon_social as cliente_razon_social,
                cl.numero_documento as cliente_ruc,
                cl.nombre_comercial as cliente_nombre_comercial,
                cl.codigo_cliente as cod_cliente,
                cl.direccion_fiscal as cliente_direccion,
                cl.telefono_contacto as cliente_telefono,
                cl.nombre_contacto as cliente_contacto,
                cl.email_contacto as cliente_email
            FROM cotizaciones c
            LEFT JOIN clientes cl ON cl.id = c.cliente_id::integer
            WHERE c.estado != 'Anulada'
            AND (
                LOWER(c.numero_cotizacion) LIKE LOWER(%s) OR
                LOWER(cl.razon_social) LIKE LOWER(%s) OR
                LOWER(cl.numero_documento) LIKE LOWER(%s) OR
                LOWER(cl.nombre_comercial) LIKE LOWER(%s) OR
                LOWER(c.codigo_cotizacion) LIKE LOWER(%s)
            )
            ORDER BY c.fecha_creacion DESC
            LIMIT 20
        """
        search_pattern = f'%{q}%'
        results = db_query(query, (search_pattern, search_pattern, search_pattern, search_pattern, search_pattern))
        results = filtrar_filas('cotizaciones', results)
        
        # Formatear respuesta
        formatted_data = []
        for row in results:
            formatted_data.append({
                'id': row.get('id'),
                'numero': row.get('numero_cotizacion'),
                'fecha': row.get('fecha_creacion'),
                'estado': row.get('estado'),
                'total': float(row.get('total') or 0),
                'subtotal': float(row.get('subtotal') or 0),
                'igv': float(row.get('igv') or 0),
                'ruc': row.get('cliente_ruc'),
                'razon': row.get('cliente_razon_social') or row.get('cliente_nombre_comercial'),
                'cod_cliente': row.get('cod_cliente'),
                'direccion': row.get('cliente_direccion'),
                'telefono': row.get('cliente_telefono'),
                'contacto': row.get('cliente_contacto'),
                'email': row.get('cliente_email'),
                'condicion_pago': row.get('condicion_pago'),
                'direccion_entrega': row.get('direccion_entrega'),
                'tiempo_entrega': row.get('tiempo_entrega'),
                'validez_oferta': row.get('validez_oferta'),
                'vendedor': row.get('vendedor')
            })
        
        return jsonify({'success': True, 'data': formatted_data})
        
    except Exception as e:
        print(f"❌ Error en api_cotizaciones_buscar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# ventas.py - Agregar al final del archivo

# ============================================================
# VALIDACIÓN DE PV - ENDPOINT
# ============================================================

@ventas_bp.route('/ventas/api/pedido-compra/<int:id>/validar', methods=['POST'])
@login_required
def api_pedido_compra_validar(id):
    """
    Valida un PV contra su cotización asociada.
    ⚠️ EL STOCK NO BLOQUEA - SOLO INFORMATIVO
    """
    try:
        data = request.get_json()
        print(f"🔍 Validando PV ID: {id}")
        
        # 1. Obtener el PV
        query_pc = """
            SELECT 
                id, numero, cliente, ruc, monto,
                cotizacion_id, cotizacion_numero,
                valida_precios, valida_cantidades, valida_stock,
                valida_entrega, valida_montos,
                valida_transporte, valida_margen, valida_vigencia,
                items_json, estado, req_compra
            FROM pedido_compra_pc
            WHERE id = %s
        """
        pc_result = db_query(query_pc, (id,))
        
        if not pc_result:
            return jsonify({'success': False, 'error': 'PV no encontrado'}), 404
        
        pc = pc_result[0]
        
        # 2. Obtener la cotización asociada
        cotizacion_id = pc.get('cotizacion_id')
        if not cotizacion_id:
            return jsonify({'success': False, 'error': 'PV no tiene cotización asociada'}), 400
        
        query_cot = """
            SELECT 
                c.id, c.numero_cotizacion, c.subtotal, c.total,
                c.condicion_pago, c.direccion_entrega, c.tiempo_entrega,
                c.transporte, c.margen, c.validez_oferta,
                cl.razon_social as cliente_razon_social,
                cl.numero_documento as cliente_ruc
            FROM cotizaciones c
            LEFT JOIN clientes cl ON cl.id = c.cliente_id::integer
            WHERE c.id = %s
        """
        cot_result = db_query(query_cot, (cotizacion_id,))
        
        if not cot_result:
            return jsonify({'success': False, 'error': 'Cotización no encontrada'}), 404
        
        cotizacion = cot_result[0]
        
        # 3. Obtener items del PV
        pc_items = []
        if pc.get('items_json'):
            try:
                pc_items = json.loads(pc['items_json'])
            except:
                pc_items = []
        
        # 4. Obtener items de la cotización
        query_items_cot = """
            SELECT 
                d.producto_id, d.cantidad, d.precio_venta_unitario,
                p.codigo, p.descripcion, p.unidad,
                p.stock, p.precio_unitario
            FROM cotizacion_detalle d
            LEFT JOIN productos p ON p.id = d.producto_id
            WHERE d.cotizacion_id = %s
        """
        cot_items = db_query(query_items_cot, (cotizacion_id,))
        
        # 5. Realizar validaciones
        # ⚠️ STOCK NO BLOQUEA - solo informativo
        validaciones = {
            'precios': True,
            'cantidades': True,
            'stock': True,  # ← Se guarda pero NO bloquea
            'entrega': True,
            'moneda': True,
            'transporte': True,
            'margen': True,
            'vigencia': True
        }
        
        detalles_validacion = []
        stock_insuficiente = False
        productos_faltantes = []
        
        # Validar cada item
        for pc_item in pc_items:
            # Soporte para formato de lista o diccionario
            if isinstance(pc_item, dict):
                codigo = pc_item.get('codigo', '')
                cantidad_pc = float(pc_item.get('cantidad_pc', pc_item.get('cantidad', 0)))
                precio_pc = float(pc_item.get('precio_pc', pc_item.get('precio', 0)))
            else:
                codigo = pc_item[0] if len(pc_item) > 0 else ''
                cantidad_pc = float(pc_item[3]) if len(pc_item) > 3 else 0
                precio_pc = float(pc_item[5]) if len(pc_item) > 5 else 0
            
            # Buscar item correspondiente en cotización
            cot_item = next(
                (i for i in cot_items if i.get('codigo') == codigo),
                None
            )
            
            if cot_item:
                cantidad_cot = float(cot_item.get('cantidad', 0))
                precio_cot = float(cot_item.get('precio_venta_unitario', 0))
                stock = float(cot_item.get('stock', 0))
                
                # Validar cantidad
                if cantidad_pc != cantidad_cot:
                    validaciones['cantidades'] = False
                
                # Validar precio (tolerancia 5%)
                if precio_pc != 0 and precio_cot != 0:
                    diff_pct = abs(precio_pc - precio_cot) / precio_cot * 100
                    if diff_pct > 5:
                        validaciones['precios'] = False
                
                # ⚠️ STOCK: solo informativo, NO BLOQUEA
                if cantidad_pc > stock:
                    stock_insuficiente = True
                    productos_faltantes.append({
                        'codigo': codigo,
                        'producto': cot_item.get('descripcion', ''),
                        'stock': stock,
                        'requerido': cantidad_pc,
                        'faltante': cantidad_pc - stock
                    })
                    validaciones['stock'] = False
                
                detalles_validacion.append({
                    'codigo': codigo,
                    'producto': cot_item.get('descripcion', ''),
                    'cantidad_cot': cantidad_cot,
                    'cantidad_pc': cantidad_pc,
                    'precio_cot': precio_cot,
                    'precio_pc': precio_pc,
                    'stock': stock,
                    'faltante': max(cantidad_pc - stock, 0),
                    'validaciones': {
                        'cantidad': cantidad_pc == cantidad_cot,
                        'precio': abs(precio_pc - precio_cot) / precio_cot * 100 <= 5 if precio_cot != 0 else True,
                        'stock': cantidad_pc <= stock  # ← SOLO INFORMATIVO
                    }
                })
        
        # Validar entrega
        pc_entrega = pc.get('lugar_entrega') or pc.get('entrega') or ''
        cot_entrega = cotizacion.get('direccion_entrega') or ''
        if pc_entrega.strip().lower() != cot_entrega.strip().lower():
            validaciones['entrega'] = False
        
        # Validar transporte
        pc_transporte = pc.get('transporte') or ''
        cot_transporte = cotizacion.get('transporte') or ''
        if pc_transporte.strip().lower() != cot_transporte.strip().lower():
            validaciones['transporte'] = False
        
        # Validar moneda (si hay campo)
        pc_moneda = pc.get('moneda') or ''
        cot_moneda = cotizacion.get('moneda') or 'Soles (S/)'
        if pc_moneda and cot_moneda and codigo_moneda(pc_moneda) != codigo_moneda(cot_moneda):
            validaciones['moneda'] = False
        
        # Validar vigencia
        pc_vigencia = pc.get('vigencia') or ''
        cot_vigencia = cotizacion.get('validez_oferta') or ''
        if pc_vigencia and cot_vigencia and pc_vigencia.strip().lower() != cot_vigencia.strip().lower():
            validaciones['vigencia'] = False
        
        # 6. Determinar resultado final
        # ⚠️ STOCK NO BLOQUEA - solo informativo
        validaciones_para_estado = {
            'precios': validaciones['precios'],
            'cantidades': validaciones['cantidades'],
            'entrega': validaciones['entrega'],
            'moneda': validaciones['moneda'],
            'transporte': validaciones['transporte'],
            'margen': validaciones['margen'],
            'vigencia': validaciones['vigencia']
            # 'stock' NO incluido para bloqueo
        }
        
        todas_validas = all(validaciones_para_estado.values())
        
        if not todas_validas:
            estado = 'PC observado'
            req_compra = 'Bloqueado'
            mensaje = 'PV con observaciones - requiere corrección'
        else:
            # ✅ Todas las validaciones OK (excepto stock)
            estado = 'PC conforme'
            if stock_insuficiente:
                req_compra = 'Sí'  # Requiere compra por falta de stock
                mensaje = 'PV conforme - requiere compra por falta de stock'
            else:
                req_compra = 'No'
                mensaje = 'PV conforme - listo para despacho'
        
        # 7. Actualizar PV
        query_update = """
            UPDATE pedido_compra_pc 
            SET 
                estado = %s,
                req_compra = %s,
                valida_precios = %s,
                valida_cantidades = %s,
                valida_stock = %s,
                valida_entrega = %s,
                valida_montos = %s,
                valida_transporte = %s,
                valida_margen = %s,
                valida_vigencia = %s,
                updated_at = NOW()
            WHERE id = %s
            RETURNING id, estado, req_compra
        """
        
        result = db_query(query_update, (
            estado,
            req_compra,
            validaciones['precios'],
            validaciones['cantidades'],
            validaciones['stock'],  # ← Se guarda para referencia
            validaciones['entrega'],
            validaciones['moneda'],
            validaciones['transporte'],
            validaciones['margen'],
            validaciones['vigencia'],
            id
        ))
        
        if result:
            return jsonify({
                'success': True,
                'message': mensaje,
                'data': {
                    'id': result[0]['id'],
                    'estado': estado,
                    'req_compra': req_compra,
                    'validaciones': validaciones,
                    'stock_insuficiente': stock_insuficiente,
                    'productos_faltantes': productos_faltantes,
                    'detalles': detalles_validacion,
                    'resumen': {
                        'total_items': len(detalles_validacion),
                        'ok': todas_validas,
                        'observaciones': [k for k, v in validaciones_para_estado.items() if not v],
                        'stock_ok': not stock_insuficiente
                    }
                }
            })
        
        return jsonify({'success': False, 'error': 'No se pudo actualizar'}), 400
        
    except Exception as e:
        print(f"❌ Error en api_pedido_compra_validar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@ventas_bp.route('/ventas/api/pedido-compra/<int:id>', methods=['GET'])
@login_required
def api_pedido_compra_obtener(id):
    """Obtiene un pedido de venta por su ID con items formateados"""
    try:
        query = """
            SELECT 
                id, numero, fecha, estado, cliente, ruc, monto,
                cotizacion_id, cotizacion_numero, correo_origen,
                fecha_recepcion, fecha_despacho, archivo_oc,
                observaciones, valida_precios, valida_cantidades,
                valida_stock, valida_entrega, valida_montos,
                valida_transporte, valida_margen, valida_vigencia,
                responsable, lugar_entrega, condicion_atencion,
                medio, entrega, req_compra, guia, factura,
                condicion_pago, vendedor, items_json,
                created_at, updated_at,
                to_jsonb(pedido_compra_pc) -> 'valida_productos' AS valida_productos,
                to_jsonb(pedido_compra_pc) ->> 'oc_cliente' AS oc_cliente
            FROM pedido_compra_pc
            WHERE id = %s
        """
        result = db_query(query, (id,))
        
        if not result:
            return jsonify({'success': False, 'error': 'PV no encontrado'}), 404
        
        pc = result[0]
        
        # ============================================================
        # 🔽 PROCESAR ITEMS CORRECTAMENTE
        # ============================================================
        items = []
        items_json_raw = pc.get('items_json')
        
        if items_json_raw:
            try:
                if isinstance(items_json_raw, str):
                    raw_items = json.loads(items_json_raw)
                else:
                    raw_items = items_json_raw
                
                if isinstance(raw_items, list) and len(raw_items) > 0:
                    if isinstance(raw_items[0], list):
                        # Formato: [[codigo, descripcion, ...]]
                        for item in raw_items:
                            if len(item) >= 9:
                                items.append({
                                    'codigo': item[0] or '',
                                    'producto': item[1] or '',
                                    'marca': item[2] or '',
                                    'modelo': item[3] or '',
                                    'cantidad_cotizada': float(item[4] or 0),
                                    'cantidad_pc': float(item[5] or 1),
                                    'precio_cotizado': float(item[6] or 0),
                                    'precio_pc': float(item[7] or 0),
                                    'stock': float(item[8] or 0)
                                })
                            elif len(item) >= 7:
                                items.append({
                                    'codigo': item[0] or '',
                                    'producto': item[1] or '',
                                    'marca': '',
                                    'modelo': '',
                                    'cantidad_cotizada': float(item[2] or 0),
                                    'cantidad_pc': float(item[3] or 1),
                                    'precio_cotizado': float(item[4] or 0),
                                    'precio_pc': float(item[5] or 0),
                                    'stock': float(item[6] or 0)
                                })
                            else:
                                # Mínimo: codigo y descripcion
                                items.append({
                                    'codigo': item[0] or '',
                                    'producto': item[1] or '',
                                    'marca': '',
                                    'modelo': '',
                                    'cantidad_cotizada': 0,
                                    'cantidad_pc': 1,
                                    'precio_cotizado': 0,
                                    'precio_pc': 0,
                                    'stock': 0
                                })
                    else:
                        # Ya es una lista de objetos
                        for item in raw_items:
                            if isinstance(item, dict):
                                items.append({
                                    'codigo': item.get('codigo', ''),
                                    'producto': item.get('producto', item.get('descripcion', '')),
                                    'descripcion_cliente': item.get('descripcion_cliente') or '',   # 24/10/2026: como en la PC (Pedido del cliente)
                                    'marca': item.get('marca', ''),
                                    'modelo': item.get('modelo', ''),
                                    'cantidad_cotizada': float(item.get('cantidad_cotizada', item.get('cantidad_cot', 0))),
                                    'cantidad_pc': float(item.get('cantidad_pc', item.get('cantidad', 1))),
                                    'precio_cotizado': float(item.get('precio_cotizado', item.get('precio_cot', 0))),
                                    'precio_pc': float(item.get('precio_pc', item.get('precio', 0))),
                                    'stock': float(item.get('stock', 0))
                                })
            except Exception as e:
                print(f"⚠️ Error parseando items_json: {e}")
                items = []
        
        # ============================================================
        # 🔽 SI NO HAY ITEMS, INTENTAR OBTENER DE LA COTIZACIÓN
        # ============================================================
        if not items and pc.get('cotizacion_id'):
            try:
                query_cot_items = """
                    SELECT 
                        d.producto_id, d.cantidad, d.precio_venta_unitario,
                        p.codigo, p.descripcion, p.marca, p.modelo, p.unidad,
                        p.stock
                    FROM cotizacion_detalle d
                    LEFT JOIN productos p ON p.id = d.producto_id
                    WHERE d.cotizacion_id = %s
                """
                cot_items = db_query(query_cot_items, (pc['cotizacion_id'],))
                
                for item in cot_items:
                    items.append({
                        'codigo': item.get('codigo', ''),
                        'producto': item.get('descripcion', ''),
                        'marca': item.get('marca', ''),
                        'modelo': item.get('modelo', ''),
                        'cantidad_cotizada': float(item.get('cantidad', 0)),
                        'cantidad_pc': float(item.get('cantidad', 1)),
                        'precio_cotizado': float(item.get('precio_venta_unitario', 0)),
                        'precio_pc': float(item.get('precio_venta_unitario', 0)),
                        'stock': float(item.get('stock', 0))
                    })
                print(f"✅ Items cargados desde cotización {pc['cotizacion_id']}")
            except Exception as e:
                print(f"⚠️ Error obteniendo items de cotización: {e}")
        
        # ============================================================
        # 🔽 SI AÚN NO HAY ITEMS, CREAR UNO GENÉRICO
        # ============================================================
        if not items:
            items = [{
                'codigo': 'GEN-001',
                'producto': 'Producto genérico (sin items)',
                'marca': '',
                'modelo': '',
                'cantidad_cotizada': 1,
                'cantidad_pc': 1,
                'precio_cotizado': float(pc.get('monto', 0)) if pc.get('monto') else 0,
                'precio_pc': float(pc.get('monto', 0)) if pc.get('monto') else 0,
                'stock': 0
            }]
            print(f"⚠️ PV {id} sin items, usando item genérico")
        
        # ============================================================
        # 🔽 FORMATEAR MONTO A 2 DECIMALES
        # ============================================================
        if pc.get('monto'):
            pc['monto'] = round(float(pc['monto']), 2)
        
        # 🔽 FORMATEAR FECHA PARA DATETIME-LOCAL
        def formatear_fecha(fecha):
            if not fecha:
                return ''
            try:
                if isinstance(fecha, str):
                    # Si tiene formato ISO, convertirlo
                    if 'T' in fecha:
                        return fecha[:16]  # YYYY-MM-DDTHH:MM
                    if ' ' in fecha:
                        return fecha.replace(' ', 'T')[:16]
                    if len(fecha) == 10 and '-' in fecha:
                        return fecha + 'T00:00'
                    return fecha
                return str(fecha)
            except:
                return str(fecha)
        
        # Aplicar formateo a fechas
        campos_fecha = ['fecha', 'fecha_recepcion', 'fecha_despacho', 'created_at', 'updated_at']
        for campo in campos_fecha:
            if pc.get(campo):
                pc[campo] = formatear_fecha(pc[campo])
        
        # Agregar items al objeto
        pc['items'] = items
        pc['items_json'] = None  # No devolver el JSON crudo
        
        return jsonify({'success': True, 'data': pc})
        
    except Exception as e:
        print(f"❌ Error en api_pedido_compra_obtener: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@ventas_bp.route('/ventas/api/cotizaciones/<int:id>/pdf/preview', methods=['GET'])
@login_required
def api_cotizaciones_preview_pdf(id):
    """Genera y muestra el PDF de una cotización en el navegador (vista previa)"""
    try:
        print(f"📄 Generando vista previa PDF para cotización ID: {id}")
        
        from datetime import datetime, timedelta
        from flask import send_file, render_template_string
        from weasyprint import HTML
        
        # ============================================================
        # 🔽 FUNCIÓN PARA OBTENER HORA DE PERÚ (UTC-5)
        # ============================================================
        def obtener_hora_peru():
            """Retorna fecha y hora actual en zona horaria de Perú (UTC-5)"""
            now_utc = datetime.utcnow()
            now_peru = now_utc - timedelta(hours=5)
            return now_peru
        
        # ============================================================
        # FUNCIÓN PARA OBTENER LOGO EN BASE64
        # ============================================================
        def obtener_logo_base64_para_pdf():
            import base64
            import os
            
            posibles_rutas = [
                os.path.join('templates', 'pdf', 'logo-kcf.png'),
                os.path.join('templates', 'logo-kcf.png'),
                os.path.join('static', 'img', 'logo-kcf.png'),
                os.path.join('static', 'logo-kcf.png'),
                'logo-kcf.png',
                os.path.join('app', 'static', 'img', 'logo-kcf.png'),
                os.path.join('app', 'static', 'logo-kcf.png'),
                os.path.join('static', 'images', 'logo-kcf.png'),
                os.path.join('templates', 'cotizacion_oc', 'logo-kcf.png'),
                os.path.join('..', 'static', 'img', 'logo-kcf.png'),
                os.path.join('..', 'static', 'logo-kcf.png'),
            ]
            
            for logo_path in posibles_rutas:
                if os.path.exists(logo_path):
                    try:
                        with open(logo_path, 'rb') as f:
                            logo_data = f.read()
                            logo_base64 = base64.b64encode(logo_data).decode('utf-8')
                            print(f"✅ Logo cargado desde: {logo_path}")
                            return logo_base64
                    except Exception as e:
                        print(f"⚠️ Error leyendo {logo_path}: {e}")
                        continue
                else:
                    print(f"🔍 Logo no encontrado: {logo_path}")
            
            print("❌ No se encontró el logo en ninguna ruta")
            return None
        
        # 1. Obtener cabecera
        query_cabecera = """
            SELECT 
                c.id, c.empresa_id, c.numero_cotizacion, c.codigo_cotizacion,
                c.cliente_id, c.fecha_creacion, c.estado,
                c.subtotal, c.igv, c.total, c.notas,
                c.forma_pago, c.tiempo_entrega, c.almacen, c.validez_oferta,
                c.codigo_cotizacion, c.correlativo, c.condicion_pago,
                c.direccion_entrega, c.requerimiento, c.nota_cotizacion,
                c.descuento_porcentaje, c.descuento_monto, c.descuento_tipo,
                c.contacto_cliente, c.telefono_cliente, c.email_cliente,
                to_jsonb(c) ->> 'moneda' AS moneda, to_jsonb(c) ->> 'tipo_cambio' AS tipo_cambio,
                cl.id as cliente_id,
                cl.razon_social as cliente_razon_social,
                cl.numero_documento as cliente_ruc,
                cl.nombre_comercial as cliente_nombre_comercial,
                cl.codigo_cliente as cod_cliente,
                cl.direccion_fiscal as cliente_direccion,
                cl.telefono_contacto as cliente_telefono,
                cl.nombre_contacto as cliente_contacto,
                cl.email_contacto as cliente_email
            FROM cotizaciones c
            LEFT JOIN clientes cl ON cl.id = c.cliente_id::integer
            WHERE c.id = %s
        """
        cabecera = db_query(query_cabecera, (id,))
        
        if not cabecera:
            return jsonify({'success': False, 'error': 'Cotización no encontrada'}), 404
        
        c = cabecera[0]
        
        # 2. Obtener productos
        query_productos = """
            SELECT 
                d.id, d.producto_id, d.cantidad,
                d.precio_venta_unitario, d.subtotal_venta,
                d.descuento_porcentaje, d.precio_venta_con_descuento,
                d.subtotal_venta_con_descuento,
                p.codigo, p.descripcion, p.descripcion_larga,
                p.modelo, p.marca, p.unidad as um
            FROM cotizacion_detalle d
            LEFT JOIN productos p ON p.id = d.producto_id
            WHERE d.cotizacion_id = %s
        """
        productos = db_query(query_productos, (id,))
        
        # 3. Preparar datos
        cliente_razon_social = c.get('cliente_razon_social') or c.get('cliente_nombre_comercial') or 'Cliente'
        cliente_ruc = c.get('cliente_ruc') or '---'
        cliente_direccion = c.get('cliente_direccion') or c.get('direccion_entrega') or '---'
        
        subtotal = float(c.get('subtotal', 0))
        igv = float(c.get('igv', 0))
        total = float(c.get('total', 0))
        descuento_monto = float(c.get('descuento_monto', 0))
        
        productos_list = []
        for idx, p in enumerate(productos or [], 1):
            precio_unitario = float(p.get('precio_venta_unitario', 0))
            cantidad = float(p.get('cantidad', 1))
            subtotal_producto = float(p.get('subtotal_venta', 0))
            descuento_pct = float(p.get('descuento_porcentaje', 0))
            subtotal_desc = float(p.get('subtotal_venta_con_descuento', subtotal_producto))
            
            productos_list.append({
                'item': idx,
                'codigo': p.get('codigo', '---'),
                'descripcion': p.get('descripcion') or p.get('descripcion_larga') or 'Producto sin descripción',
                'modelo': p.get('modelo') or '-',
                'marca': p.get('marca', ''),
                'unidad': p.get('um', 'NIU'),
                'cantidad': cantidad,
                'precio_venta_unitario': precio_unitario,
                'subtotal_venta': subtotal_producto,
                'descuento_porcentaje': descuento_pct,
                'subtotal_venta_desc': subtotal_desc
            })
        
        hay_descuentos = any(p.get('descuento_porcentaje', 0) > 0 for p in productos_list) or descuento_monto > 0
        
        # 🔽 USAR HORA DE PERÚ (UTC-5)
        now_peru = obtener_hora_peru()
        fecha_actual = now_peru.strftime('%d/%m/%Y')
        hora_actual = now_peru.strftime('%H:%M')
        print(f"📅 Hora Perú: {fecha_actual} {hora_actual}")
        
        emp = marca_pdf(c.get('empresa_id'))
        logo_base64 = emp['logo_src'].split('base64,', 1)[1] if 'base64,' in emp['logo_src'] else None
        print(f"📷 Logo cargado: {'Sí' if logo_base64 else 'No'}")
        
        # 🔽 OBTENER REQUERIMIENTO
        requerimiento = c.get('requerimiento') or '---'
        print(f"📋 Requerimiento: {requerimiento}")
        
        datos_pdf = {
            'codigo_cotizacion': c.get('codigo_cotizacion') or c.get('numero_cotizacion', 'COT-000001'),
            'fecha_actual': fecha_actual,
            'hora_actual': hora_actual,
            'logo_base64': logo_base64,
            'logo_mime': emp['logo_src'][5:emp['logo_src'].find(';')] if logo_base64 else 'image/png',
            'emp_nombre': emp['nombre'], 'emp_ruc': emp['ruc'], 'emp_corto': emp['corto'],
            'emp_telefono': emp['telefono'], 'emp_email': emp['email'], 'emp_web': emp['web'],
            'emp_web_corta': emp['web_corta'], 'emp_color': emp['color'], 'emp_cuentas': [cb for cb in (emp.get('cuentas') or []) if codigo_moneda(cb.get('moneda')) == 'PEN'],  # Erika 25/10: la cuenta en dólares no va en la cotización
            # 24/10/2026 (Erika): cotización en dólares -> US$ en el PDF
            'sim': 'US$' if codigo_moneda(c.get('moneda')) == 'USD' else 'S/',
            'cliente_razon_social': cliente_razon_social,
            'cliente_ruc': cliente_ruc,
            'cliente_direccion': cliente_direccion,
            'cliente_contacto': c.get('cliente_contacto') or c.get('contacto_cliente') or '---',
            'email_contacto_cliente': c.get('cliente_email') or c.get('email_cliente') or '---',
            'telefono_contacto': c.get('cliente_telefono') or c.get('telefono_cliente') or '---',
            'numero_requerimiento': requerimiento,
            'asesor_comercial': 'Helen Blas Príncipe',
            'email_contacto': emp['email'],
            'telefono_contacto_user': '999932051',
            'condicion_pago': c.get('condicion_pago') or c.get('forma_pago') or 'Contado',
            'tiempo_entrega': c.get('tiempo_entrega') or '5 días hábiles',
            'direccion_entrega': c.get('direccion_entrega') or cliente_direccion,
            'validez_oferta': c.get('validez_oferta') or '15 días',
            'productos': productos_list,
            'total_subtotal_venta': subtotal,
            'total_descuento_subtotal': descuento_monto,
            'total_subtotal_venta_desc': subtotal - descuento_monto,
            'summary_igv': igv,
            'summary_total_venta': total,
            'hay_descuentos': hay_descuentos
        }

        # 4. Template HTML - CON COLORES SUAVES Y SOLO ROJO PARA COTIZACIÓN Y NÚMERO
        template_html = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Cotización - {{ emp_nombre }}</title>
    <style>
        @page {
            size: A4;
            margin: 1.2cm;
        }
        * { 
            margin: 0; 
            padding: 0; 
            box-sizing: border-box; 
        }
        body { 
            font-family: 'Helvetica', Arial, sans-serif;
            font-size: 9.5px; 
            color: #333333;
            line-height: 1.6; 
            background: #ffffff; 
        }
        
        /* ===== COLORES ===== */
        .color-rojo { color: {{ emp_color }}; }
        .color-gris { color: #555555; }
        .color-gris-oscuro { color: #333333; }
        
        /* ===== HEADER ===== */
        .header-superior {
            display: flex;
            justify-content: space-between;
            align-items: stretch;
            margin-bottom: 12px;
            gap: 20px;
            padding-bottom: 8px;
            border-bottom: 2px solid #CCCCCC;
        }
        .empresa-izquierda {
            flex: 1;
            display: flex;
            align-items: center;
            gap: 18px;
        }
        .empresa-izquierda .logo-container {
            flex-shrink: 0;
            width: 90px;
            height: 65px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .empresa-izquierda .logo-container img {
            max-height: 60px;
            max-width: 100px;
            object-fit: contain;
        }
        .empresa-izquierda .info-texto {
            font-size: 8px;
            line-height: 1.5;
            color: #444444;
        }
        .empresa-izquierda .info-texto .nombre {
            font-size: 13px;
            font-weight: bold;
            text-transform: uppercase;
            color: #333333;
            letter-spacing: 0.5px;
            margin-bottom: 1px;
        }
        .empresa-izquierda .info-texto .ruc-line {
            font-size: 9px;
            font-weight: bold;
            color: #333333;
            margin-bottom: 1px;
        }
        .empresa-izquierda .info-texto .slogan {
            font-size: 8px;
            color: #666666;
            font-style: italic;
            margin-bottom: 1px;
        }
        .empresa-izquierda .info-texto .contacto-line {
            font-size: 7.5px;
            color: #555555;
        }
        
        .recuadro-derecha {
            flex-shrink: 0;
            border: 2px solid #CCCCCC;
            border-radius: 10px;
            padding: 6px 18px;
            text-align: center;
            min-width: 180px;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }
        .recuadro-derecha .ruc {
            font-size: 9px;
            font-weight: bold;
            color: #555555;
        }
        .recuadro-derecha .titulo {
            font-size: 11px;
            font-weight: bold;
            letter-spacing: 1px;
            margin: 2px 0;
            color: {{ emp_color }};
        }
        .recuadro-derecha .numero {
            font-size: 14px;
            font-weight: bold;
            color: {{ emp_color }};
        }
        
        /* ===== LAYOUT PRINCIPAL ===== */
        .layout-principal { 
            display: flex; 
            gap: 15px; 
            margin-bottom: 10px; 
        }
        .seccion-cliente, .seccion-condiciones { 
            flex: 1; 
            border: 1px solid #d5d5d5;
            border-radius: 8px;
            padding: 8px 12px; 
        }
        .seccion-cliente h3, .seccion-condiciones h3 { 
            color: #333333;
            border-bottom: 2px solid #CCCCCC;
            padding-bottom: 3px; 
            font-size: 9.5px; 
            margin-top: 0; 
            margin-bottom: 6px; 
            font-weight: bold; 
            text-transform: uppercase;
        }
        .info-line, .condicion-line { 
            display: flex; 
            margin-bottom: 2px; 
            font-size: 8.5px; 
        }
        .info-label, .condicion-label { 
            width: 100px; 
            font-weight: bold; 
            color: #555555;
        }
        .info-value, .condicion-value { 
            flex: 1; 
            color: #333333;
        }
        
        /* ===== TEXTO INTRODUCTORIO ===== */
        .texto-introductorio { 
            margin: 8px 0; 
            padding: 6px 12px; 
            font-size: 8.5px; 
            line-height: 1.4; 
            text-align: justify; 
            border: 1px solid #e5e7eb;
            border-radius: 6px;
        }
        .texto-introductorio .saludo { 
            font-size: 9px; 
            font-weight: bold; 
            margin-bottom: 3px; 
            color: #333333;
        }
        
        /* ===== TABLA DE PRODUCTOS ===== */
        .tabla-productos { 
            width: 100%; 
            border-collapse: collapse; 
            margin: 8px 0; 
            font-size: 8px; 
        }
        .tabla-productos th { 
    color: #333333;
    padding: 5px 4px; 
    border: 1px solid #CCCCCC;
    font-weight: bold; 
    text-align: center; 
    vertical-align: middle; 
    background-color: #F8C8C8; /* 🔴 Fondo rojo suave para todo el encabezado */
}
        .tabla-productos td { 
            padding: 4px 4px; 
            border: 1px solid #d5d5d5; 
            vertical-align: middle; 
            color: #333333;
        }
        .tabla-productos tr:nth-child(even) td {
            background: #f9f9f9;
        }
        
        .col-item { text-align: center; width: 30px; }
        .col-codigo { text-align: left; width: 70px; }
        .col-descripcion { text-align: left; }
        .col-modelo { text-align: left; width: 55px; }
        .col-marca { text-align: left; width: 60px; }
        .col-unidad-medida { text-align: center; width: 50px; }
        .col-cantidad { text-align: center; width: 40px; }
        .col-valor-unitario { text-align: right; width: 80px; }
        
        /* 🔴 VALOR VENTA TOTAL - ROJO SUAVE (encabezado) */
        .col-valor-total { 
            text-align: right; 
            width: 85px; 
            font-weight: bold; 
            color: #E57373;
        }
        
        .numero-formateado { 
            text-align: right; 
            font-family: 'Courier New', monospace; 
            font-weight: bold; 
        }
        .text-center { text-align: center; }
        .text-left { text-align: left; }
        .text-right { text-align: right; }
        .fw-bold { font-weight: bold; }
        
    
        
        /* ===== SECCIÓN TOTALES ===== */
        .seccion-totales { 
            width: 280px; 
            margin-left: auto; 
            margin-right: 0; 
            margin-top: 8px; 
            margin-bottom: 10px; 
            border: 2px solid #CCCCCC;
            border-radius: 8px;
            padding: 8px 12px; 
        }
        .total-line { 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            margin-bottom: 3px; 
            font-size: 8.5px; 
            gap: 8px; 
        }
        .total-line span:first-child { 
            white-space: nowrap; 
            color: #555555; 
        }
        .total-line .numero-formateado { 
            font-weight: bold; 
            white-space: nowrap; 
            color: #333333;
        }
        
        /* 🔵 TOTAL A PAGAR - AZUL CHIYÓN */
        .total-final { 
            border-top: 2px solid #CCCCCC; 
            padding-top: 8px; 
            margin-top: 6px; 
            font-weight: bold; 
            font-size: 14px;
            color: #0033A0;
        }
        .total-final .numero-formateado {
            font-size: 18px;
            color: #0033A0;
        }
        
        /* ===== NOTA ACLARATORIA ===== */
        .seccion-aclaratoria { 
            margin: 10px 0; 
            padding: 10px 16px; 
            border: 2px solid #CCCCCC;
            border-radius: 8px;
            font-size: 8.5px; 
            text-align: justify;
            line-height: 1.6; 
        }
        .seccion-aclaratoria .titulo { 
            font-weight: bold; 
            font-size: 9.5px; 
            margin-bottom: 4px; 
            color: #333333; 
            text-align: center;
            text-transform: uppercase;
        }
        .seccion-aclaratoria .web-link { 
            color: #333333; 
            text-decoration: underline; 
            font-weight: bold; 
        }
        
        /* ===== CUENTAS BANCARIAS ===== */
        .cuentas-bancarias { 
            margin-top: 8px; 
            padding: 8px 14px; 
            border: 2px solid #CCCCCC;
            border-radius: 8px;
            font-size: 8px; 
        }
        .cuentas-bancarias h3 { 
            color: #333333;
            border-bottom: 2px solid #CCCCCC;
            padding-bottom: 3px; 
            font-size: 9.5px; 
            margin-top: 0; 
            margin-bottom: 6px; 
            text-transform: uppercase;
            text-align: center;
        }
        .cuenta-line { 
            margin-bottom: 4px;
            padding: 4px 0;
            text-align: center;
        }
        .cuenta-line .banco { 
            font-weight: bold; 
            color: #333333; 
            font-size: 10px;
        }
        .cuenta-line .tipo { 
            font-size: 8.5px; 
            color: #555555; 
        }
        .cuenta-line .numero { 
            font-size: 11px;
            color: #333333; 
            font-weight: bold; 
            letter-spacing: 0.5px;
        }
        .cuenta-line .cci { 
            font-size: 10px;
            color: #555555; 
            font-weight: bold;
            letter-spacing: 0.5px;
        }
        
        /* ===== CONTACTO FINAL ===== */
        .seccion-contacto { 
            margin-top: 12px; 
            border-top: 2px solid #CCCCCC;
            padding-top: 10px; 
            text-align: left; 
            font-size: 8.5px; 
        }
        .contacto-nombre { 
            font-size: 10px; 
            font-weight: bold; 
            color: #333333;
            margin-bottom: 3px; 
        }
        .contacto-line { margin-bottom: 2px; color: #555555; }
        .web-link { color: #333333; text-decoration: underline; }
        
        .seccion-totales, .cuentas-bancarias, .seccion-aclaratoria, .seccion-contacto { 
            page-break-inside: avoid; 
            break-inside: avoid; 
        }
        .tabla-productos { page-break-inside: avoid; }
    </style>
</head>
<body>
    <!-- ============================================================ -->
    <!-- HEADER CON BORDE GRIS                                        -->
    <!-- ============================================================ -->
    <div class="header-superior">
        <div class="empresa-izquierda">
            <div class="logo-container">
                {% if logo_base64 %}
                <img src="data:{{ logo_mime }};base64,{{ logo_base64 }}" alt="Logo {{ emp_corto }}">
                {% else %}
                <div style="font-size:26px;font-weight:900;color:{{ emp_color }};padding-top:12px;">{{ emp_corto }}</div>
                {% endif %}
            </div>
            <div class="info-texto">
                <div class="nombre">{{ emp_nombre }}</div>
                <div class="ruc-line">RUC: {{ emp_ruc }}</div>
                <div class="slogan">Soluciones integrales en abastecimientos</div>
                <div class="contacto-line">{% if emp_telefono %}Telf: {{ emp_telefono }} | {% endif %}Email: {{ emp_email }}</div>
                {% if emp_web %}<div class="contacto-line">Web: {{ emp_web }}</div>{% endif %}
            </div>
        </div>
        <div class="recuadro-derecha">
            <div class="ruc">RUC: Nº {{ emp_ruc }}</div>
            <div class="titulo">COTIZACIÓN</div>
            <div class="numero">{{ codigo_cotizacion }}</div>
        </div>
    </div>

    <!-- ============================================================ -->
    <!-- CLIENTE Y CONDICIONES                                        -->
    <!-- ============================================================ -->
    <div class="layout-principal">
        <div class="seccion-cliente">
            <h3>INFORMACIÓN DEL CLIENTE</h3>
            <div class="info-line"><span class="info-label">Cliente:</span><span class="info-value">{{ cliente_razon_social }}</span></div>
            <div class="info-line"><span class="info-label">RUC / DNI:</span><span class="info-value">{{ cliente_ruc }}</span></div>
            <div class="info-line"><span class="info-label">Dirección:</span><span class="info-value">{{ cliente_direccion }}</span></div>
            <div class="info-line"><span class="info-label">Teléfono:</span><span class="info-value">{{ telefono_contacto|default('-') }}</span></div>
            <div class="info-line"><span class="info-label">Atención:</span><span class="info-value">{{ cliente_contacto|default('-') }}</span></div>
            <div class="info-line"><span class="info-label">Correo:</span><span class="info-value">{{ email_contacto_cliente|default('-') }}</span></div>
            <div class="info-line"><span class="info-label">N° Requerimiento:</span><span class="info-value">{{ numero_requerimiento|default('-') }}</span></div>
        </div>
        <div class="seccion-condiciones">
            <h3>CONDICIONES COMERCIALES</h3>
            <!-- ✅ CAMBIO 1: "Ejecutiva Comercial:" -->
            <div class="condicion-line"><span class="condicion-label">Ejecutiva Comercial:</span><span class="condicion-value">{{ asesor_comercial }}</span></div>
            <div class="condicion-line"><span class="condicion-label">E-mail:</span><span class="condicion-value">{{ email_contacto }}</span></div>
            <div class="condicion-line"><span class="condicion-label">Teléfono:</span><span class="condicion-value">{{ telefono_contacto_user }}</span></div>
            <div class="condicion-line"><span class="condicion-label">Condición Pago:</span><span class="condicion-value">{{ condicion_pago }}</span></div>
            <div class="condicion-line"><span class="condicion-label">Tiempo Entrega:</span><span class="condicion-value">{{ tiempo_entrega }}</span></div>
            <div class="condicion-line"><span class="condicion-label">Dirección Entrega:</span><span class="condicion-value">{{ direccion_entrega }}</span></div>
            <div class="condicion-line"><span class="condicion-label">Validez Oferta:</span><span class="condicion-value">{{ validez_oferta }}</span></div>
            <div class="condicion-line"><span class="condicion-label">Fecha:</span><span class="condicion-value">{{ fecha_actual }}</span></div>
            <div class="condicion-line"><span class="condicion-label">Hora:</span><span class="condicion-value">{{ hora_actual|default('00:00') }}</span></div>
        </div>
    </div>

    <!-- ============================================================ -->
    <!-- TEXTO INTRODUCTORIO                                         -->
    <!-- ============================================================ -->
    <div class="texto-introductorio">
        <div class="saludo">Estimado Cliente,</div>
        La presente tiene como objeto poner a su consideración nuestra oferta detallada según su requerimiento, agradecemos por confiar en nuestros productos:
    </div>

    <!-- ============================================================ -->
    <!-- TABLA DE PRODUCTOS - CABECERA GRIS                          -->
    <!-- ============================================================ -->
    <table class="tabla-productos">
        <thead>
            <tr>
                <th class="col-item">Item</th>
                <th class="col-codigo">Código Producto</th>
                <th class="col-descripcion">Descripción</th>
                <th class="col-modelo">Modelo</th>
                <th class="col-marca">Marca</th>
                <th class="col-unidad-medida">Unidad Medida</th>
                <th class="col-cantidad">Cantidad</th>
                <th class="col-valor-unitario">Valor Venta Unit {{ sim }}</th>
                <!-- ✅ CAMBIO 3: encabezado en rojo suave -->
                <th class="col-valor-total">Valor Venta Total {{ sim }}</th>
            </tr>
        </thead>
        <tbody>
            {% if productos %}
                {% for producto in productos %}
                <tr>
                    <td class="text-center">{{ producto.item }}</td>
                    <td>{{ producto.codigo|default('-') }}</td>
                    <td class="descripcion">{{ producto.descripcion }}</td>
                    <td>{{ producto.modelo|default('-') }}</td>
                    <td>{{ producto.marca|default('-') }}</td>
                    <td class="text-center">{{ producto.unidad|default('Unid') }}</td>
                    <td class="text-center">{{ "%.0f"|format(producto.cantidad|default(0)) }}</td>
                    <td class="numero-formateado">{{ "%.2f"|format(producto.precio_venta_unitario|default(0)) }}</td>
                    <!-- ✅ CAMBIO 3: celda en rojo suave -->
                    <td class="numero-formateado celda-valor-total">{{ "%.2f"|format(producto.subtotal_venta_desc|default(producto.subtotal_venta|default(0))) }}</td>
                </tr>
                {% endfor %}
            {% else %}
                <tr><td colspan="9" class="text-center" style="padding: 15px;">No hay productos registrados en esta cotización</td></tr>
            {% endif %}
        </tbody>
    </table>

    <!-- ============================================================ -->
    <!-- NOTA ACLARATORIA - BORDE GRIS                              -->
    <!-- ============================================================ -->
    <div class="seccion-aclaratoria">
        <div class="titulo">📌 NOTA ACLARATORIA</div>
        La validez de esta oferta está sujeta a la disponibilidad de inventario en el momento de la confirmación del pedido.<br>
        {% if hay_descuentos %}<strong>Esta oferta incluye un descuento de {{ sim }} {{ '%.2f'|format(total_descuento_subtotal|float) }} aplicado en el valor de venta.</strong><br>{% endif %}
        {% if emp_web %}Para más información visítanos en 
        <a href="{{ emp_web }}" class="web-link">{{ emp_web_corta }}</a>{% endif %}
    </div>

    <!-- ============================================================ -->
    <!-- TOTALES - TOTAL A PAGAR EN AZUL CHIYÓN                     -->
    <!-- ============================================================ -->
    <div class="seccion-totales">
        <div class="total-line"><span>Subtotal ({{ sim }}):</span><span class="numero-formateado">{{ sim }} {{ "%.2f"|format(total_subtotal_venta|default(0)) }}</span></div>
        {% if hay_descuentos %}
        <div class="total-line"><span>Descuentos aplicados ({{ sim }}):</span><span class="numero-formateado" style="color:#555555;">- {{ sim }} {{ "%.2f"|format(total_descuento_subtotal|default(0)) }}</span></div>
        {% endif %}
        <div class="total-line"><span>Subtotal con descuento ({{ sim }}):</span><span class="numero-formateado">{{ sim }} {{ "%.2f"|format(total_subtotal_venta_desc|default(0)) }}</span></div>
        <div class="total-line"><span>IGV (18%):</span><span class="numero-formateado">{{ sim }} {{ "%.2f"|format(summary_igv|default(0)) }}</span></div>
        <!-- ✅ CAMBIO 2: TOTAL A PAGAR en azul chiyón -->
        <div class="total-line total-final"><span><strong>TOTAL A PAGAR:</strong></span><span class="numero-formateado"><strong>{{ sim }} {{ "%.2f"|format(summary_total_venta|default(0)) }}</strong></span></div>
    </div>

    <!-- ============================================================ -->
    <!-- CUENTAS BANCARIAS - BORDE GRIS                             -->
    <!-- ============================================================ -->
    <div class="cuentas-bancarias">
        <h3>💰 CUENTAS BANCARIAS</h3>
        {% for cb in emp_cuentas %}
        <div class="cuenta-line">
            <span class="banco">🏛️ {{ cb.banco }}</span>
            <span class="tipo">| {% if cb.moneda %}{{ 'Dólares' if cb.moneda|upper in ('USD', 'US$', 'DOLARES', 'DÓLARES') else 'Soles' }}{% endif %}</span><br>
            <span class="numero">Cuenta Corriente N° {{ cb.numero_cuenta }}</span><br>
            {% if cb.cci %}<span class="cci">CCI: {{ cb.cci }}</span>{% endif %}
        </div>
        {% else %}{% if emp_ruc == '20602095704' %}
        <div class="cuenta-line">
            <span class="banco">🏛️ BBVA</span>
            <span class="tipo">| Soles</span><br>
            <span class="numero">Cuenta Corriente N° 0011-0319-1601-00022197</span><br>
            <span class="cci">CCI: 011-319-000100022197-16</span>
        </div>
        {% endif %}{% endfor %}
    </div>

    <!-- ============================================================ -->
    <!-- CONTACTO FINAL - TODOS LOS TEXTOS EN NEGRO                 -->
    <!-- ============================================================ -->
    <div class="seccion-contacto">
        <div class="contacto-nombre">Cordialmente,</div>
        <div class="contacto-nombre">HELLEN BLAS PRINCIPE</div>
        <div class="contacto-line">Ejecutiva Comercial</div>
        <div class="contacto-line">{{ emp_corto }}</div>
        {% if emp_telefono %}<div class="contacto-line">📞 (+51) {{ emp_telefono }}</div>{% endif %}
        <div class="contacto-line">✉ {{ emp_email }}</div>
        {% if emp_web %}<div class="contacto-line">🌐 {{ emp_web_corta }}</div>{% endif %}
    </div>

</body>
</html>'''
        html_content = render_template_string(template_html, **datos_pdf)
        
        # 5. Generar PDF en memoria
        import io
        pdf_buffer = io.BytesIO()
        HTML(string=html_content).write_pdf(pdf_buffer)
        pdf_buffer.seek(0)
        
        nombre_archivo = f"cotizacion_{c.get('codigo_cotizacion', 'sin_numero')}_{datetime.now().strftime('%Y%m%d')}.pdf"
        
        return send_file(
            pdf_buffer,
            as_attachment=False,
            download_name=nombre_archivo,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        print(f"❌ Error generando vista previa PDF: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@ventas_bp.route('/ventas/api/pedido-compra/<int:id>', methods=['DELETE'])
@login_required
def api_pedido_compra_eliminar(id):
    """Elimina físicamente un pedido de venta de la base de datos"""
    try:
        print(f"🗑️ Eliminando físicamente PV ID: {id}")
        
        # Verificar que el PV existe
        query_check = "SELECT id, numero, estado FROM pedido_compra_pc WHERE id = %s"
        result_check = db_query(query_check, (id,))
        
        if not result_check:
            return jsonify({'success': False, 'error': 'PV no encontrado'}), 404
        
        pc = result_check[0]
        estado = pc.get('estado')
        
        # Opcional: Permitir eliminar solo si está anulado
        # Si quieres permitir eliminar cualquier PV, comenta esta validación
        if estado != 'Anulado':
            return jsonify({
                'success': False, 
                'error': f'Solo se pueden eliminar PVs en estado "Anulado". Estado actual: {estado}'
            }), 400
        
        # Eliminar el PV
        query_delete = "DELETE FROM pedido_compra_pc WHERE id = %s RETURNING id"
        result_delete = db_query(query_delete, (id,))
        
        if result_delete:
            return jsonify({
                'success': True, 
                'message': f'PV eliminado correctamente',
                'data': {'id': id}
            })
        
        return jsonify({'success': False, 'error': 'No se pudo eliminar el PV'}), 400
        
    except Exception as e:
        print(f"❌ Error en api_pedido_compra_eliminar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

def obtener_despacho_por_id_db(despacho_id):
    """Obtiene un despacho con sus items desde el PV asociado"""
    try:
        query = """
            SELECT 
                d.id, d.numero, d.fecha, d.fecha_despacho, d.estado,
                d.pc_id, d.pc_numero, d.cotizacion_id, d.cotizacion_numero,
                d.cliente, d.ruc, d.comprobante, d.guia, d.origen, d.destino,
                d.transportista, d.observaciones, d.responsable,
                p.items_json as pc_items
            FROM despachos d
            LEFT JOIN pedido_compra_pc p ON p.id = d.pc_id
            WHERE d.id = %s
        """
        result = db_query(query, (despacho_id,))
        
        if result:
            despacho = result[0]
            # Obtener items del PV si existen
            if despacho.get('pc_items'):
                try:
                    despacho['items'] = json.loads(despacho['pc_items'])
                except:
                    despacho['items'] = []
            else:
                despacho['items'] = []
            return despacho
        
        return None
    except Exception as e:
        print(f"❌ Error en obtener_despacho_por_id_db: {e}")
        return None


# ============================================================
# GENERAR PDF DE COMPROBANTE (FACTURA / BOLETA)
# ============================================================

@ventas_bp.route('/ventas/api/comprobantes/<int:comp_id>/pdf/preview', methods=['GET'])
@login_required
def preview_pdf_comprobante(comp_id):
    """Vista previa del PDF de comprobante"""
    try:
        print(f"👁️ Vista previa PDF para comprobante ID: {comp_id}")
        
        query = """
            SELECT 
                id, tipo_comprobante, serie, numero, fecha_emision,
                moneda, cliente_tipo_doc, cliente_numero_doc,
                cliente_nombre, cliente_direccion, cliente_email,
                cliente_telefono, subtotal, igv, total,
                items_json, observaciones, estado_sunat,
                documento_asociado, empresa_id
            FROM comprobantes
            WHERE id = %s
        """
        comp_result = db_query(query, (comp_id,))
        
        if not comp_result:
            return jsonify({'error': 'Comprobante no encontrado'}), 404
        
        comp = comp_result[0]
        
        from pdf_generator import pdf_generator
        
        items = []
        
        # 🔽 OBTENER ITEMS CON MARCA Y MODELO
        if comp.get('items_json'):
            try:
                raw_items = json.loads(comp.get('items_json'))
                for idx, item in enumerate(raw_items, 1):
                    if isinstance(item, dict):
                        items.append({
                            'item': idx,
                            'codigo': item.get('codigo', ''),
                            'descripcion': (item.get('descripcion_cliente') or '').strip() or item.get('producto', item.get('descripcion', 'Sin descripción')),
                            'marca': item.get('marca', ''),          # ← IMPORTANTE
                            'modelo': item.get('modelo', ''),        # ← IMPORTANTE
                            'unidad': item.get('um', 'NIU'),
                            'cantidad': float(item.get('cantidad', 1)),
                            'precio_unitario': float(item.get('valorVenta', item.get('precio', 0))),
                            'total_item': float(item.get('cantidad', 1)) * float(item.get('valorVenta', item.get('precio', 0)))
                        })
                    elif isinstance(item, list):
                        items.append({
                            'item': idx,
                            'codigo': item[0] if len(item) > 0 else '',
                            'descripcion': item[1] if len(item) > 1 else 'Sin descripción',
                            'marca': item[2] if len(item) > 2 else '',   # ← IMPORTANTE
                            'modelo': item[3] if len(item) > 3 else '',  # ← IMPORTANTE
                            'unidad': item[4] if len(item) > 4 else 'NIU',
                            'cantidad': float(item[5]) if len(item) > 5 else 1,
                            'precio_unitario': float(item[6]) if len(item) > 6 else 0,
                            'total_item': float(item[5]) * float(item[6]) if len(item) > 6 else 0
                        })
            except Exception as e:
                print(f"⚠️ Error parseando items: {e}")
        
        # Si no hay items, buscar en cotización
        if not items and comp.get('documento_asociado'):
            try:
                cot_numero = comp.get('documento_asociado')
                query_cot_items = """
                    SELECT 
                        d.cantidad, d.precio_venta_unitario,
                        p.codigo, p.descripcion, p.marca, p.modelo, p.unidad
                    FROM cotizacion_detalle d
                    LEFT JOIN productos p ON p.id = d.producto_id
                    LEFT JOIN cotizaciones c ON c.id = d.cotizacion_id
                    WHERE c.codigo_cotizacion = %s OR c.numero_cotizacion = %s
                """
                cot_items = db_query(query_cot_items, (cot_numero, cot_numero))
                for idx, item in enumerate(cot_items, 1):
                    items.append({
                        'item': idx,
                        'codigo': item.get('codigo', ''),
                        'descripcion': item.get('descripcion', 'Sin descripción'),
                        'marca': item.get('marca', ''),
                        'modelo': item.get('modelo', ''),
                        'unidad': item.get('unidad', 'NIU'),
                        'cantidad': float(item.get('cantidad', 1)),
                        'precio_unitario': float(item.get('precio_venta_unitario', 0)),
                        'total_item': float(item.get('cantidad', 1)) * float(item.get('precio_venta_unitario', 0))
                    })
            except Exception as e:
                print(f"⚠️ Error obteniendo items de cotización: {e}")
        
        subtotal = float(comp.get('subtotal', 0))
        igv = float(comp.get('igv', 0))
        total = float(comp.get('total', 0))
        
        if subtotal == 0 and items:
            subtotal = sum(item['total_item'] for item in items)
            igv = subtotal * 0.18
            total = subtotal + igv
        
        total_letras = pdf_generator.numero_a_letras(total)
        
        datos_comprobante = {
            'tipo_documento': 'comprobante',
            'tipo': comp.get('tipo_comprobante', 'FACTURA'),
            'serie': str(comp.get('serie') or 'E001').upper(),
            'numero': str(comp.get('numero') or '').zfill(8) if str(comp.get('numero') or '').isdigit() else comp.get('numero', ''),  # E001-00002319 (Erika 25/10)
            'fecha_emision': comp.get('fecha_emision'),
            'moneda': comp.get('moneda') or 'PEN',
            'condicion_pago': 'Contado',
            'fecha_vencimiento': comp.get('fecha_vencimiento', ''),
            'guia_vinculada': comp.get('guia_vinculada', '—'),
             'cliente_ruc': comp.get('cliente_numero_doc', ''),
            'cliente_nombre': comp.get('cliente_nombre', ''),
            'cliente_direccion': comp.get('cliente_direccion', ''),
            'cliente_telefono': comp.get('cliente_telefono', ''),
            'cliente_email': comp.get('cliente_email', ''),
            'subtotal': f"{subtotal:.2f}",
            'igv': f"{igv:.2f}",
            'total': f"{total:.2f}",
            'total_letras': total_letras,
            'descuento': "0.00",
            'op_inafecta': "0.00",
            'op_exonerada': "0.00",
            'op_gratuita': "0.00",
            'observaciones': comp.get('observaciones', ''),
            'orden_compra_cliente': comp.get('documento_asociado', '—'),
            'factura': f"{comp.get('serie', '')}-{comp.get('numero', '')}",
            'nro_cotizacion': comp.get('documento_asociado', '—'),
            'items': items,
            'qr_base64': ''
        }
        
        datos_comprobante.update(_datos_extra_factura_pdf(comp))
        datos_comprobante['empresa_pdf'] = marca_pdf(comp.get('empresa_id'))
        pdf_path = pdf_generator.generar_pdf_universal(datos_comprobante)
        
        if not pdf_path:
            return jsonify({'error': 'Error al generar el PDF'}), 500
        
        from flask import send_file
        return send_file(
            pdf_path,
            mimetype='application/pdf',
            as_attachment=False
        )
        
    except Exception as e:
        print(f"❌ Error generando vista previa: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@ventas_bp.route('/ventas/api/comprobantes/<int:comp_id>/pdf', methods=['GET'])
@login_required
def generar_pdf_comprobante(comp_id):
    """Genera el PDF de un comprobante (Factura o Boleta) para descarga"""
    try:
        print(f"📄 Generando PDF para comprobante ID: {comp_id}")
        
        # Obtener el comprobante
        query = """
            SELECT 
                id, tipo_comprobante, serie, numero, fecha_emision,
                moneda, cliente_tipo_doc, cliente_numero_doc,
                cliente_nombre, cliente_direccion, cliente_email,
                cliente_telefono, subtotal, igv, total,
                items_json, observaciones, estado_sunat,
                creado_por, documento_asociado, guia_vinculada,
                fecha_vencimiento, condicion_pago, empresa_id
            FROM comprobantes
            WHERE id = %s
        """
        comp_result = db_query(query, (comp_id,))
        
        if not comp_result:
            return jsonify({'error': 'Comprobante no encontrado'}), 404
        
        comp = comp_result[0]
        print(f"✅ Comprobante encontrado: {comp.get('serie')}-{comp.get('numero')}")
        
        # Preparar datos para el PDFGenerator
        from pdf_generator import pdf_generator
        
        items = []
        
        # Obtener items desde items_json
        if comp.get('items_json'):
            try:
                raw_items = json.loads(comp.get('items_json'))
                print(f"📦 Items desde items_json: {len(raw_items)}")
                
                for idx, item in enumerate(raw_items, 1):
                    if isinstance(item, dict):
                        items.append({
                            'item': idx,
                            'codigo': item.get('codigo', ''),
                            'descripcion': (item.get('descripcion_cliente') or '').strip() or item.get('producto', item.get('descripcion', 'Sin descripción')),
                            'marca': item.get('marca', ''),
                            'modelo': item.get('modelo', ''),
                            'unidad': item.get('um', 'NIU'),
                            'cantidad': float(item.get('cantidad', 1)),
                            'precio_unitario': float(item.get('valorVenta', item.get('precio', 0))),
                            'total_item': float(item.get('cantidad', 1)) * float(item.get('valorVenta', item.get('precio', 0)))
                        })
                    elif isinstance(item, list):
                        items.append({
                            'item': idx,
                            'codigo': item[0] if len(item) > 0 else '',
                            'descripcion': item[1] if len(item) > 1 else 'Sin descripción',
                            'marca': item[2] if len(item) > 2 else '',
                            'modelo': item[3] if len(item) > 3 else '',
                            'unidad': item[4] if len(item) > 4 else 'NIU',
                            'cantidad': float(item[5]) if len(item) > 5 else 1,
                            'precio_unitario': float(item[6]) if len(item) > 6 else 0,
                            'total_item': float(item[5]) * float(item[6]) if len(item) > 6 else 0
                        })
            except Exception as e:
                print(f"⚠️ Error parseando items_json: {e}")
        
        # Si no hay items, buscar en cotización asociada
        if not items and comp.get('documento_asociado'):
            try:
                cot_numero = comp.get('documento_asociado')
                print(f"🔍 Buscando items en cotización: {cot_numero}")
                
                query_cot_items = """
                    SELECT 
                        d.cantidad, d.precio_venta_unitario,
                        p.codigo, p.descripcion, p.marca, p.modelo, p.unidad
                    FROM cotizacion_detalle d
                    LEFT JOIN productos p ON p.id = d.producto_id
                    LEFT JOIN cotizaciones c ON c.id = d.cotizacion_id
                    WHERE c.codigo_cotizacion = %s OR c.numero_cotizacion = %s
                """
                cot_items = db_query(query_cot_items, (cot_numero, cot_numero))
                
                for idx, item in enumerate(cot_items, 1):
                    items.append({
                        'item': idx,
                        'codigo': item.get('codigo', ''),
                        'descripcion': item.get('descripcion', 'Sin descripción'),
                        'marca': item.get('marca', ''),
                        'modelo': item.get('modelo', ''),
                        'unidad': item.get('unidad', 'NIU'),
                        'cantidad': float(item.get('cantidad', 1)),
                        'precio_unitario': float(item.get('precio_venta_unitario', 0)),
                        'total_item': float(item.get('cantidad', 1)) * float(item.get('precio_venta_unitario', 0))
                    })
                print(f"📦 Items desde cotización: {len(items)}")
            except Exception as e:
                print(f"⚠️ Error obteniendo items de cotización: {e}")
        
        # Si aún no hay items, crear uno genérico
        if not items:
            items = [{
                'item': 1,
                'codigo': 'GEN-001',
                'descripcion': 'Producto sin detalle',
                'marca': '',
                'modelo': '',
                'unidad': 'NIU',
                'cantidad': 1,
                'precio_unitario': 0,
                'total_item': 0
            }]
            print("⚠️ No se encontraron items, usando genérico")
        
        # Calcular totales
        subtotal = float(comp.get('subtotal', 0))
        igv = float(comp.get('igv', 0))
        total = float(comp.get('total', 0))
        
        if subtotal == 0 and items:
            subtotal = sum(item['total_item'] for item in items)
            igv = subtotal * 0.18
            total = subtotal + igv
        
        # Convertir total a letras
        total_letras = pdf_generator.numero_a_letras(total)
        
        datos_comprobante = {
            'tipo_documento': 'comprobante',
            'tipo': comp.get('tipo_comprobante', 'FACTURA'),
            'serie': str(comp.get('serie') or 'E001').upper(),
            'numero': str(comp.get('numero') or '').zfill(8) if str(comp.get('numero') or '').isdigit() else comp.get('numero', ''),  # E001-00002319 (Erika 25/10)
            'fecha_emision': comp.get('fecha_emision'),
            'fecha_vencimiento': comp.get('fecha_vencimiento', ''),
            'moneda': comp.get('moneda', 'S/'),
            'condicion_pago': comp.get('condicion_pago', 'Contado'),
            'cliente_ruc': comp.get('cliente_numero_doc', ''),
            'cliente_nombre': comp.get('cliente_nombre', ''),
            'cliente_direccion': comp.get('cliente_direccion', ''),
            'cliente_telefono': comp.get('cliente_telefono', ''),
            'cliente_email': comp.get('cliente_email', ''),
            'subtotal': f"{subtotal:.2f}",
            'igv': f"{igv:.2f}",
            'total': f"{total:.2f}",
            'total_letras': total_letras,
            'descuento': "0.00",
            'op_inafecta': "0.00",
            'op_exonerada': "0.00",
            'op_gratuita': "0.00",
            'observaciones': comp.get('observaciones', ''),
            'orden_compra_cliente': comp.get('documento_asociado', '—'),
            'guia_vinculada': comp.get('guia_vinculada', '—'),
            'factura': f"{comp.get('serie', '')}-{comp.get('numero', '')}",
            'nro_cotizacion': comp.get('documento_asociado', '—'),
            'items': items,
            'qr_base64': ''
        }
        
        # Generar el PDF
        datos_comprobante.update(_datos_extra_factura_pdf(comp))
        datos_comprobante['empresa_pdf'] = marca_pdf(comp.get('empresa_id'))
        pdf_path = pdf_generator.generar_pdf_universal(datos_comprobante)
        
        if not pdf_path:
            return jsonify({'error': 'Error al generar el PDF'}), 500
        
        # Retornar el PDF
        from flask import send_file
        filename = f"{comp.get('tipo_comprobante', 'FACTURA')}_{comp.get('serie', 'F001')}_{comp.get('numero', '0001')}.pdf"
        
        return send_file(
            pdf_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        print(f"❌ Error generando PDF de comprobante: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
# ============================================================
# TRANSPORTISTAS - API (integrado en ventas)
# ============================================================

@ventas_bp.route('/ventas/api/transportistas/listar', methods=['GET'])
@login_required
def api_transportistas_listar():
    """Listar todos los transportistas para usar en ventas"""
    try:
        print("🔍 Listando transportistas...")
        
        query = """
            SELECT 
                id, nombre_completo, dni, placa, 
                medidas, licencia, telefono, peso_carga, tipo,
                activo, created_at, updated_at
            FROM transportistas
            WHERE activo = true
            ORDER BY nombre_completo
        """
        result = db_query(query)
        print(f"✅ {len(result)} transportistas encontrados")
        
        # Formatear los datos para el frontend
        formatted_data = []
        for row in result:
            formatted_data.append({
                'id': row.get('id'),
                'nombre_completo': row.get('nombre_completo') or '',
                'dni': row.get('dni') or '',
                'placa': row.get('placa') or '',
                'medidas': row.get('medidas') or '',
                'licencia': row.get('licencia') or '',
                'telefono': row.get('telefono') or '',
                'peso_carga': row.get('peso_carga') or '',
                'tipo': row.get('tipo') or 'conductor',
                'activo': row.get('activo', True)
            })
        
        return jsonify({'success': True, 'data': formatted_data})
        
    except Exception as e:
        print(f"❌ Error en api_transportistas_listar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@ventas_bp.route('/ventas/api/transportistas/<int:id>', methods=['GET'])
@login_required
def api_transportistas_obtener(id):
    """Obtener un transportista por ID"""
    try:
        query = """
            SELECT 
                id, nombre_completo, dni, placa, 
                medidas, licencia, telefono, peso_carga, tipo,
                activo
            FROM transportistas
            WHERE id = %s AND activo = true
        """
        result = db_query(query, (id,))
        if result:
            row = result[0]
            return jsonify({
                'success': True, 
                'data': {
                    'id': row.get('id'),
                    'nombre_completo': row.get('nombre_completo') or '',
                    'dni': row.get('dni') or '',
                    'placa': row.get('placa') or '',
                    'medidas': row.get('medidas') or '',
                    'licencia': row.get('licencia') or '',
                    'telefono': row.get('telefono') or '',
                    'peso_carga': row.get('peso_carga') or '',
                    'tipo': row.get('tipo') or 'conductor'
                }
            })
        return jsonify({'success': False, 'error': 'Transportista no encontrado'}), 404
    except Exception as e:
        print(f"❌ Error en api_transportistas_obtener: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@ventas_bp.route('/ventas/api/transportistas/guardar', methods=['POST'])
@login_required
def api_transportistas_guardar():
    """Guardar un nuevo transportista desde ventas"""
    try:
        data = request.get_json()
        usuario_id = session.get('usuario_id')
        
        print(f"📦 Guardando transportista desde ventas: {data}")
        
        query = """
            INSERT INTO transportistas (
                nombre_completo, dni, placa, 
                medidas, licencia, telefono, peso_carga, tipo,
                activo, creado_por
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) RETURNING id
        """
        params = (
            data.get('nombre_completo', '').strip(),
            data.get('dni', '').strip(),
            data.get('placa', '').strip().upper(),
            data.get('medidas', '').strip(),
            data.get('licencia', '').strip(),
            data.get('telefono', '').strip(),
            data.get('peso_carga', '').strip(),
            data.get('tipo', 'conductor'),
            True,
            usuario_id
        )
        
        result = db_query(query, params)
        print(f"✅ Resultado: {result}")
        
        if result:
            return jsonify({
                'success': True,
                'message': 'Transportista guardado correctamente',
                'data': {'id': result[0]['id']}
            })
        return jsonify({'success': False, 'error': 'No se pudo guardar'}), 400
        
    except Exception as e:
        print(f"❌ Error en api_transportistas_guardar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500



@ventas_bp.route('/api/cotizaciones/eliminadas', methods=['GET'])
@login_required
def api_cotizaciones_eliminadas():
    """Obtiene el historial de cotizaciones eliminadas/anuladas"""
    try:
        print("🔍 Consultando cotizaciones eliminadas...")
        crear_tabla_cotizaciones_eliminadas_si_no_existe()
        
        # ✅ CON JOIN CON LA COLUMNA CORRECTA
        query = """
            SELECT 
                ce.id,
                ce.cotizacion_id_original,
                ce.numero_cotizacion as numero,
                ce.cliente_razon_social as cliente,
                ce.cliente_ruc as ruc,
                ce.motivo_eliminacion as motivo,
                ce.eliminado_en as fecha_eliminacion,
                ce.eliminado_por,
                ce.total,
                ce.estado_anterior as estado,
                u.nombre_completo as usuario_elimino
            FROM cotizaciones_eliminadas ce
            LEFT JOIN usuarios u ON u.id = ce.eliminado_por
            ORDER BY ce.eliminado_en DESC
        """
        
        eliminadas = db_query(query)
        
        print(f"📊 {len(eliminadas)} cotizaciones eliminadas encontradas")
        
        # Formatear fechas
        for item in eliminadas:
            if item.get('fecha_eliminacion'):
                if hasattr(item['fecha_eliminacion'], 'strftime'):
                    item['fecha_eliminacion'] = item['fecha_eliminacion'].strftime('%d/%m/%Y %H:%M')
            
            # Si no tiene usuario, poner 'Sistema'
            if not item.get('usuario_elimino'):
                item['usuario_elimino'] = 'Sistema'
        
        return jsonify({
            'success': True,
            'data': eliminadas,
            'total': len(eliminadas)
        })
        
    except Exception as e:
        print(f"❌ Error obteniendo cotizaciones eliminadas: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@ventas_bp.route('/ventas/api/transportistas/buscar', methods=['GET'])
@login_required
def api_transportistas_buscar():
    """Buscar transportistas por texto (nombre, dni, placa)"""
    try:
        q = request.args.get('q', '').strip()
        if not q or len(q) < 2:
            return jsonify({'success': True, 'data': []})
        
        search_pattern = f'%{q}%'
        query = """
            SELECT 
                id, nombre_completo, dni, placa, 
                medidas, licencia, telefono, peso_carga, tipo
            FROM transportistas
            WHERE activo = true
            AND (
                LOWER(nombre_completo) LIKE LOWER(%s) OR
                LOWER(dni) LIKE LOWER(%s) OR
                LOWER(placa) LIKE LOWER(%s) OR
                LOWER(telefono) LIKE LOWER(%s)
            )
            ORDER BY nombre_completo
            LIMIT 20
        """
        result = db_query(query, (search_pattern, search_pattern, search_pattern, search_pattern))
        return jsonify({'success': True, 'data': result})
        
    except Exception as e:
        print(f"❌ Error en api_transportistas_buscar: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@ventas_bp.route('/api/cotizaciones/eliminadas/<int:id>', methods=['GET'])
@login_required
def api_ver_eliminada(id):
    """Obtiene el detalle de una cotización eliminada"""
    try:
        # Antes consultaba columnas inexistentes en "cotizaciones" (siempre error 500).
        # El respaldo con motivo y usuario está en cotizaciones_eliminadas.
        crear_tabla_cotizaciones_eliminadas_si_no_existe()
        query = """
            SELECT 
                ce.id,
                ce.cotizacion_id_original,
                ce.numero_cotizacion as numero,
                ce.fecha_creacion as fecha,
                ce.estado_anterior as estado,
                ce.motivo_eliminacion as motivo,
                ce.eliminado_en as fecha_eliminacion,
                ce.eliminado_por,
                ce.cliente_razon_social as cliente,
                ce.cliente_ruc as ruc,
                ce.contacto_cliente as contacto,
                ce.telefono_cliente as telefono,
                ce.email_cliente as email,
                ce.condicion_pago,
                ce.tiempo_entrega,
                ce.direccion_entrega,
                ce.subtotal,
                ce.igv,
                ce.total,
                ce.productos_json,
                u.nombre_completo as usuario_elimino
            FROM cotizaciones_eliminadas ce
            LEFT JOIN usuarios u ON u.id = ce.eliminado_por
            WHERE ce.id = %s OR ce.cotizacion_id_original = %s
            ORDER BY (ce.id = %s) DESC, ce.eliminado_en DESC
            LIMIT 1
        """
        
        registro = db_query(query, (id, id, id))
        
        if not registro:
            return jsonify({'success': False, 'error': 'Registro no encontrado'}), 404
        
        return jsonify({
            'success': True,
            'data': registro[0]
        })
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# REVISIÓN - API (COMPLETO)
# ============================================================

@ventas_bp.route('/ventas/api/cotizaciones/revision', methods=['GET'])
@login_required
def api_cotizaciones_revision():
    try:
        if not es_aprobador():
            return jsonify({'success': True, 'data': [], 'message': 'No autorizado'})
        
        # 🔽 Incluir "Por validar" y "Validado por Hellen"
        query = """
            SELECT 
                c.id, 
                c.numero_cotizacion as numero,
                c.codigo_cotizacion as codigo,
                c.fecha_creacion as fecha,
                c.estado,
                c.subtotal,
                c.igv,
                c.total,
                c.condicion_pago,
                c.vendedor,
                c.requerimiento,
                c.direccion_entrega,
                c.nota_cotizacion as notas,
                c.tiempo_entrega,
                c.validez_oferta,
                c.seguimiento,
                c.motivo,
                c.transporte,
                c.parihuela,
                c.nota_interna,
                cl.id as cliente_id,
                cl.razon_social as cliente,
                cl.numero_documento as ruc,
                cl.codigo_cliente as cod_cliente,
                cl.direccion_fiscal as direccion,
                cl.telefono_contacto as telefono,
                cl.nombre_contacto as contacto,
                cl.email_contacto as email,
                c.usuario_validacion_id,
                c.validado_por_nombre as validado_por,
                c.motivo_rechazo,
                c.fecha_creacion as created_at,
                u.nombre_completo as validador_nombre
            FROM cotizaciones c
            LEFT JOIN clientes cl ON cl.id = c.cliente_id::integer
            LEFT JOIN usuarios u ON u.id = c.usuario_validacion_id
            WHERE c.estado IN ('Por validar', 'Validado por Hellen', 'Aceptada', 'Rechazada')
            ORDER BY c.fecha_creacion DESC
        """
        
        results = filtrar_filas('cotizaciones', db_query(query))
        
        formatted_data = []
        for row in results:
            formatted_data.append({
                'id': row.get('id'),
                'numero': row.get('numero'),
                'codigo': row.get('codigo'),
                'fecha': row.get('fecha'),
                'estado': row.get('estado'),
                'subtotal': float(row.get('subtotal') or 0),
                'igv': float(row.get('igv') or 0),
                'total': float(row.get('total') or 0),
                'condicion_pago': row.get('condicion_pago'),
                'vendedor': row.get('vendedor', '--'),
                'requerimiento': row.get('requerimiento'),
                'direccion_entrega': row.get('direccion_entrega'),
                'notas': row.get('notas'),
                'tiempo_entrega': row.get('tiempo_entrega'),
                'validez_oferta': row.get('validez_oferta'),
                'seguimiento': row.get('seguimiento'),
                'motivo': row.get('motivo'),
                'transporte': row.get('transporte'),
                'parihuela': row.get('parihuela'),
                'nota_interna': row.get('nota_interna'),
                'cliente_id': row.get('cliente_id'),
                'cliente': row.get('cliente'),
                'ruc': row.get('ruc'),
                'cod_cliente': row.get('cod_cliente'),
                'direccion': row.get('direccion'),
                'telefono': row.get('telefono'),
                'contacto': row.get('contacto'),
                'email': row.get('email'),
                'validado_por': row.get('validado_por') or row.get('validador_nombre') or '--',
                'motivo_rechazo': row.get('motivo_rechazo'),
                'created_at': row.get('created_at')
            })
        
        return jsonify({'success': True, 'data': formatted_data})
        
    except Exception as e:
        print(f"❌ Error en api_cotizaciones_revision: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@ventas_bp.route('/ventas/api/cotizaciones/<int:id>/validar', methods=['POST'])
@login_required
def api_cotizaciones_validar(id):
    """Registra quién validó una cotización"""
    try:
        if not es_aprobador():
            return jsonify({'success': False, 'error': 'No tienes permisos para validar cotizaciones'}), 403
        usuario_id = session.get('usuario_id')
        nombre = session.get('nombre_completo') or session.get('usuario') or ''
        
        query = """
            UPDATE cotizaciones 
            SET 
                usuario_validacion_id = %s,
                validado_por_nombre = %s,
                updated_at = NOW()
            WHERE id = %s
            RETURNING id
        """
        result = db_query(query, (usuario_id, nombre, id))
        
        if result:
            return jsonify({
                'success': True, 
                'message': f'Validación registrada por {nombre}',
                'data': {'id': id, 'validado_por': nombre}
            })
        return jsonify({'success': False, 'error': 'No se pudo registrar la validación'}), 400
        
    except Exception as e:
        print(f"❌ Error en api_cotizaciones_validar: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# routes/ventas.py - Reemplazar la función api_cotizaciones_aceptar

@ventas_bp.route('/ventas/api/cotizaciones/<int:id>/aceptar', methods=['POST'])
@login_required
def api_cotizaciones_aceptar(id):
    """Acepta una cotización en revisión y la pasa a estado 'Generada'"""
    try:
        # Verificar que el usuario tenga permisos
        if not es_aprobador():
            return jsonify({
                'success': False, 
                'error': 'No tienes permisos para aceptar cotizaciones'
            }), 403
        
        # Verificar que la cotización existe y está en estado "Validado por Hellen"
        query_check = """
            SELECT id, estado FROM cotizaciones 
            WHERE id = %s AND estado IN ('Validado por Hellen', 'Validado', 'Por validar')
        """
        check = db_query(query_check, (id,))
        
        if not check:
            return jsonify({
                'success': False, 
                'error': 'Cotización no encontrada o no está en estado "Validado por Hellen"'
            }), 404
        
        # 🔽 CAMBIAR A "Generada" (NO "Aceptada por Cliente")
        query_update = """
            UPDATE cotizaciones 
            SET 
                estado = 'Generada',
                fecha_aceptacion = NOW(),
                usuario_aceptacion_id = %s,
                updated_at = NOW()
            WHERE id = %s
            RETURNING id, estado
        """
        
        usuario_id = session.get('usuario_id')
        result = db_query(query_update, (usuario_id, id))
        
        if result:
            return jsonify({
                'success': True, 
                'message': '✅ Cotización generada correctamente',
                'data': result[0]
            })
        
        return jsonify({'success': False, 'error': 'No se pudo generar la cotización'}), 400
        
    except Exception as e:
        print(f"❌ Error en api_cotizaciones_aceptar: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500





@ventas_bp.route('/ventas/api/cotizaciones/<int:id>/rechazar', methods=['POST'])
@login_required
def api_cotizaciones_rechazar(id):
    """Rechaza una cotización en revisión con motivo"""
    try:
        # Verificar que el usuario tenga permisos
        if not es_aprobador():
            return jsonify({
                'success': False, 
                'error': 'No tienes permisos para rechazar cotizaciones'
            }), 403
        
        data = request.get_json(silent=True) or {}
        motivo = (data.get('motivo_rechazo') or '').strip()
        
        if not motivo:
            return jsonify({
                'success': False, 
                'error': 'El motivo de rechazo es obligatorio'
            }), 400
        
        # Verificar que la cotización existe y está en estado correcto
        query_check = """
            SELECT id, estado FROM cotizaciones 
            WHERE id = %s AND estado IN ('Validado por Hellen', 'Validado', 'Por validar')
        """
        check = db_query(query_check, (id,))
        
        if not check:
            return jsonify({
                'success': False, 
                'error': 'Cotización no encontrada o no está en estado "Validado por Hellen"'
            }), 404
        
        # Queda "Rechazada" (no "Observada" ni "Borrador"): se ve clara en la lista y el vendedor
        # la corrige directamente y la vuelve a enviar a validación.
        query_update = """
            UPDATE cotizaciones 
            SET 
                estado = 'Rechazada',
                motivo_rechazo = %s,
                fecha_rechazo = NOW(),
                usuario_rechazo_id = %s,
                updated_at = NOW()
            WHERE id = %s
            RETURNING id, estado
        """
        
        usuario_id = session.get('usuario_id')
        result = db_query(query_update, (motivo, usuario_id, id))
        
        if result:
            return jsonify({
                'success': True, 
                'message': 'Cotización RECHAZADA. El vendedor puede corregirla y volver a enviarla a validación.',
                'data': result[0]
            })
        
        return jsonify({'success': False, 'error': 'No se pudo rechazar la cotización'}), 400
        
    except Exception as e:
        print(f"❌ Error en api_cotizaciones_rechazar: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ---------- XML / PDF de SUNAT en la factura (Erika 26/10/2026) ----------
@ventas_bp.route('/ventas/api/comprobantes/<int:comp_id>/archivos', methods=['GET', 'POST'])
@login_required
def api_comprobante_archivos(comp_id):
    from routes.archivos_factura import asegurar_archivos_factura, guardar_archivo, listar_archivos, ErrorArchivo
    try:
        asegurar_archivos_factura()
        comp = db_query("SELECT id, serie, numero FROM comprobantes WHERE id = %s", (comp_id,))
        if not comp:
            return jsonify({'success': False, 'error': 'Factura no encontrada'}), 404
        if request.method == 'POST':
            info = guardar_archivo(comp[0], request.files.get('archivo'), session.get('usuario') or '')
            from routes.auditoria import registrar_auditoria
            registrar_auditoria('CREAR', 'Ventas', 'comprobante_archivos', info['id'],
                                detalle=f"{info['tipo']} de SUNAT subido a la factura {comp[0]['serie']}-{comp[0]['numero']}: "
                                        f"{info['nombre']}")
            return jsonify({'success': True, 'data': info})
        filas = [{**f, 'created_at': f['created_at'].strftime('%d/%m/%Y %H:%M') if f.get('created_at') else ''}
                 for f in listar_archivos(comp_id)]
        return jsonify({'success': True, 'data': filas})
    except ErrorArchivo as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@ventas_bp.route('/ventas/api/comprobantes/archivos/<int:aid>/descargar', methods=['GET'])
@login_required
def api_comprobante_archivo_descargar(aid):
    from flask import Response
    from routes.archivos_factura import asegurar_archivos_factura, leer_archivo
    asegurar_archivos_factura()
    f = leer_archivo(aid)
    if not f:
        return jsonify({'success': False, 'error': 'Archivo no encontrado'}), 404
    nombre = re.sub(r'[^A-Za-z0-9._-]', '_', f['nombre'])
    return Response(bytes(f['datos']), mimetype=f['mime'],
                    headers={'Content-Disposition': f'attachment; filename="{nombre}"'})
