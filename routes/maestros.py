from flask import Blueprint, render_template, request, jsonify, session, current_app
from utils import login_required, normalizar_condicion, normalizar_banco
from database import db_query
from routes.multiempresa import visible_por_ambito
from psycopg2.extras import RealDictCursor
import traceback
import psycopg2


def _ordenar_condicion_cliente(data):
    """Condición comercial del cliente coherente (pedido de Erika 19/10/2026): si es crédito, los días son un
    número mayor a 0 (7, 15, 30...); si es contado, los días quedan en 0. Devuelve un mensaje de error o None.
    Acepta también 'Crédito 30 días' (así lo manda la cotización al crear un cliente nuevo)."""
    texto = str(data.get('condicion_pago') or 'Contado').strip()
    try:
        dias = int(float(str(data.get('dias_credito') or 0).strip() or 0))
    except (TypeError, ValueError):
        dias = 0
    dias_texto = normalizar_condicion(texto)
    if dias_texto.startswith('Crédito ') and dias_texto.endswith(' días'):
        texto, dias = 'Crédito aprobado', dias or int(dias_texto.split()[1])
    bajo = texto.lower()
    if 'cr' in bajo and 'dito' in bajo:
        if dias <= 0:
            return 'Si la condición es "Crédito aprobado", elige los días de crédito (7, 15, 30, 60, 90, 120...). "Contado" no vale para un crédito.'
        data['condicion_pago'], data['dias_credito'] = 'Crédito aprobado', dias
    elif normalizar_condicion(texto) == 'Contado' or not texto:
        data['condicion_pago'], data['dias_credito'] = 'Contado', 0
    else:
        data['dias_credito'] = 0 if 'bloque' in bajo else dias
    return None

maestros_bp = Blueprint('maestros', __name__, url_prefix='/maestros')


@maestros_bp.route('/')
@login_required
def index():
    """Página principal de maestros"""
    tab = request.args.get('tab', 'clientes')
    return render_template('maestros/index.html',
                          active_tab=tab,
                          nombre=session.get('nombre_completo', 'Usuario'),
                          empresa=session.get('empresa', 'KCF'))


# ==========================================
# ENDPOINTS CLIENTES
# ==========================================


@maestros_bp.route('/api/clientes/listar', methods=['GET'])
def api_clientes_listar():
    """Listar clientes con sus contactos y puntos de entrega"""
    try:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("📥 Solicitud a /api/clientes/listar")
        
        from database import DATABASE_URL
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        query_clientes = """
            SELECT id, codigo_cliente, razon_social,
                   numero_documento, tipo_documento,
                   nombre_comercial, telefono_contacto, nombre_contacto,
                   email_contacto, direccion_fiscal, activo,
                   condicion_pago, dias_credito, limite_credito, descuento,
                   estado, ambito, observaciones,
                   created_at, updated_at
            FROM clientes
            WHERE activo = true
            ORDER BY id DESC
        """
        cur.execute(query_clientes)
        clientes = [c for c in cur.fetchall() if visible_por_ambito(c.get('ambito'))]  # empresa elegida arriba
        
        if not clientes:
            cur.close()
            conn.close()
            return jsonify({"success": True, "data": []})
        
        for cliente in clientes:
            cliente_id = cliente.get('id')
            
            if not cliente_id:
                continue
            
            cliente['contactos'] = []
            cliente['puntos_entrega'] = []
            
            # Obtener contactos
            try:
                query_contactos = """
                    SELECT id, nombre_contacto as nombre, email, telefono, 
                           cargo, principal, activo
                    FROM clientes_contactos
                    WHERE cliente_id = %s AND activo = true
                    ORDER BY principal DESC, nombre_contacto
                """
                cur.execute(query_contactos, (cliente_id,))
                contactos = cur.fetchall()
                if contactos:
                    cliente['contactos'] = contactos
            except Exception as e:
                logger.error(f"Error en contactos para cliente {cliente_id}: {e}")
                cliente['contactos'] = []
            
            # ✅ Obtener puntos de entrega CON google_maps
            try:
                query_puntos = """
                    SELECT id, nombre_punto as punto, direccion, 
                           telefono_contacto as telefono,
                           responsable as contacto, principal, activo,
                           condicion_pago, tiempo_credito,
                           instrucciones,
                           google_maps as "googleMaps",
                           horario
                    FROM clientes_puntos_entrega
                    WHERE cliente_id = %s AND activo = true
                    ORDER BY principal DESC, nombre_punto
                """
                cur.execute(query_puntos, (cliente_id,))
                puntos = cur.fetchall()
                if puntos:
                    cliente['puntos_entrega'] = puntos
            except Exception as e:
                logger.error(f"Error en puntos para cliente {cliente_id}: {e}")
                cliente['puntos_entrega'] = []
            
            cliente['ruc'] = cliente.get('numero_documento')
            cliente['condicion_pago'] = cliente.get('condicion_pago') or 'Contado'
            cliente['dias_credito'] = cliente.get('dias_credito') or 0
            cliente['limite_credito'] = cliente.get('limite_credito') or ''
            cliente['descuento'] = cliente.get('descuento') or ''
            cliente['estado'] = cliente.get('estado') or 'Activo'
            cliente['ambito'] = cliente.get('ambito') or 'COMPARTIDO'
            cliente['observaciones'] = cliente.get('observaciones') or ''
        
        cur.close()
        conn.close()
        
        return jsonify({"success": True, "data": clientes})
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"❌ Error listando clientes: {error_msg}")
        print(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": error_msg,
            "data": []
        }), 500


@maestros_bp.route('/api/clientes/test', methods=['GET'])
def api_clientes_test():
    """Endpoint de prueba para diagnosticar"""
    try:
        from database import db_query
        # Probar consulta simple
        result = db_query("SELECT 1 as test, NOW() as time")
        return jsonify({
            "success": True,
            "message": "Conexión a base de datos OK",
            "test": result[0] if result else None
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@maestros_bp.route('/api/clientes/guardar', methods=['POST'])
@login_required
def api_clientes_guardar():
    """Guardar cliente (CREAR)"""
    conn = None
    try:
        data = request.get_json(silent=True) or {}
        current_app.logger.info(f"📝 Datos recibidos para guardar cliente: {data}")
        error_cond = _ordenar_condicion_cliente(data)
        if error_cond:
            return jsonify({"success": False, "codigo": "dias_credito", "error": error_cond}), 400

        if not data.get('razon_social'):
            return jsonify({"success": False, "campo": "razon_social", "error": "Falta la razón social del cliente."}), 400

        numero_documento = data.get('numero_documento') or data.get('ruc')
        if not numero_documento:
            return jsonify({"success": False, "campo": "numero_documento", "error": "Falta el RUC/DNI del cliente."}), 400

        from database import DATABASE_URL
        
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        query = """
            INSERT INTO clientes (
                tipo_documento, numero_documento, razon_social,
                nombre_comercial, direccion_fiscal,
                telefono_contacto, nombre_contacto, email_contacto,
                condicion_pago, dias_credito, limite_credito,
                descuento, estado, ambito, observaciones,
                activo, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s,
                %s, NOW(), NOW()
            )
            RETURNING id, codigo_cliente, numero_documento
        """
        
        params = (
            data.get('tipo_documento', 'RUC'),
            numero_documento,
            data.get('razon_social'),
            data.get('nombre_comercial', data.get('razon_social')),
            data.get('direccion_fiscal') or '',   # en la base real es obligatoria (NOT NULL)
            data.get('telefono_contacto') or data.get('telefono'),
            data.get('nombre_contacto') or data.get('contacto'),
            data.get('email_contacto') or data.get('email'),
            data.get('condicion_pago', 'Contado'),
            int(data.get('dias_credito', 0) or 0),
            data.get('limite_credito', ''),
            data.get('descuento', ''),
            data.get('estado', 'Activo'),
            data.get('ambito', 'COMPARTIDO'),
            data.get('observaciones', ''),
            True
        )
        
        cur.execute(query, params)
        result = cur.fetchone()
        cliente_id = result[0]
        if 'pide_migo' in data:  # N° MIGO (Erika 25/10/2026)
            from routes.migo import asegurar_migo
            asegurar_migo()
            cur.execute("UPDATE clientes SET pide_migo = %s WHERE id = %s", (bool(data.get('pide_migo')), cliente_id))

        # ==========================================
        # GUARDAR CONTACTOS
        # ==========================================
        for c in data.get('contactos', []):
            if not (c.get('nombre') or c.get('telefono') or c.get('email')):
                continue
            cur.execute("""
                INSERT INTO clientes_contactos (
                    cliente_id, nombre_contacto, cargo, telefono, email,
                    principal, activo
                ) VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            """, (
                cliente_id, c.get('nombre', ''), c.get('cargo', ''),
                c.get('telefono', ''), c.get('email', ''), bool(c.get('principal', False))
            ))

        # ==========================================
        # GUARDAR PUNTOS DE ENTREGA (CORREGIDO)
        # ==========================================
        puntos_recibidos = data.get('puntos_entrega', [])
        current_app.logger.info(f"📦 Puntos de entrega recibidos: {len(puntos_recibidos)}")
        
        for p in puntos_recibidos:
            # Verificar si tiene AL MENOS UN campo con valor
            tiene_datos = any([
                p.get('punto'),
                p.get('direccion'),
                p.get('instrucciones'),
                p.get('googleMaps'),
                p.get('horario'),
                p.get('contacto'),
                p.get('telefono')
            ])
            
            if not tiene_datos:
                current_app.logger.info(f"⏭️ Punto saltado (sin datos): {p}")
                continue
            
            current_app.logger.info(f"💾 Guardando punto: {p.get('punto') or p.get('direccion')}")
            
            cur.execute("""
                INSERT INTO clientes_puntos_entrega (
                    cliente_id, nombre_punto, direccion, telefono_contacto,
                    responsable, principal, instrucciones,
                    google_maps, horario
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                cliente_id, 
                p.get('punto', ''), 
                p.get('direccion', ''),
                p.get('telefono', ''), 
                p.get('contacto', ''),
                bool(p.get('principal', False)), 
                p.get('instrucciones', ''),
                p.get('googleMaps', ''),
                p.get('horario', '')
            ))

        conn.commit()
        cur.close()
        conn.close()

        if result:
            cliente = {
                'id': cliente_id,
                'codigo_cliente': result[1],
                'numero_documento': result[2]
            }
            cliente['ruc'] = cliente.get('numero_documento')
            
            return jsonify({
                "success": True,
                "data": cliente,
                "message": f"Cliente creado con código {cliente['codigo_cliente']}"
            })

        return jsonify({"success": False, "error": "No se pudo crear el cliente"})

    except psycopg2.Error as e:
        # 22/10/2026: el error de la base llega explicado (RUC repetido, dato vacío, permiso/RLS, contador
        # atrasado...) con el texto exacto en "detalle", y queda en Herramientas ▸ Registro de errores.
        if conn:
            conn.rollback()
        current_app.logger.error(f"❌ Error de BD guardando cliente: {e}")
        from routes.diagnostico import respuesta_error_bd
        return respuesta_error_bd(e, 'el cliente')

    except Exception as e:
        current_app.logger.error(f"❌ Error guardando cliente: {e}")
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": "No se pudo guardar el cliente: " + str(e),
            "detalle": e.__class__.__name__ + ": " + str(e)
        }), 500
    finally:
        if conn:
            conn.close()   # antes quedaba abierta cuando fallaba y Supabase se quedaba sin conexiones

@maestros_bp.route('/api/clientes/<int:id>', methods=['GET'])
@login_required
def api_clientes_obtener(id):
    """Obtener cliente por ID con sus contactos y puntos de entrega"""
    try:
        # 1. Obtener datos del cliente - AHORA CON TODAS LAS COLUMNAS
        query_cliente = """
            SELECT id, codigo_cliente, razon_social,
                   numero_documento, tipo_documento,
                   nombre_comercial, telefono_contacto, nombre_contacto,
                   email_contacto, direccion_fiscal, activo,
                   condicion_pago, dias_credito, limite_credito, descuento,
                   estado, ambito, observaciones,
                   created_at, updated_at
            FROM clientes
            WHERE id = %s
        """
        cliente_result = db_query(query_cliente, (id,))
        
        if not cliente_result or len(cliente_result) == 0:
            return jsonify({"success": False, "error": "Cliente no encontrado"}), 404
        
        cliente = cliente_result[0]
        
        # 2. Obtener contactos del cliente
        try:
            query_contactos = """
                SELECT id, nombre_contacto as nombre, email, telefono, cargo, principal, activo
                FROM clientes_contactos
                WHERE cliente_id = %s AND activo = true
                ORDER BY principal DESC, nombre_contacto
            """
            contactos = db_query(query_contactos, (id,))
            cliente['contactos'] = contactos if contactos else []
        except Exception as e:
            current_app.logger.warning(f"Error obteniendo contactos: {e}")
            cliente['contactos'] = []
        
        # 3. Obtener puntos de entrega del cliente
        try:
            query_puntos = """
                SELECT id, nombre_punto as punto, direccion, telefono_contacto as telefono,
                       responsable as contacto, principal, activo,
                       condicion_pago, tiempo_credito, instrucciones,
                       google_maps as "googleMaps",
                       horario
                FROM clientes_puntos_entrega
                WHERE cliente_id = %s AND activo = true
                ORDER BY principal DESC, nombre_punto
            """
            puntos = db_query(query_puntos, (id,))
            cliente['puntos_entrega'] = puntos if puntos else []
        except Exception as e:
            current_app.logger.warning(f"Error obteniendo puntos de entrega: {e}")
            cliente['puntos_entrega'] = []
        
        # 4. Asegurar valores por defecto
        cliente['condicion_pago'] = cliente.get('condicion_pago') or 'Contado'
        cliente['dias_credito'] = cliente.get('dias_credito') or 0
        cliente['limite_credito'] = cliente.get('limite_credito') or ''
        cliente['descuento'] = cliente.get('descuento') or ''
        cliente['estado'] = cliente.get('estado') or 'Activo'
        cliente['ambito'] = cliente.get('ambito') or 'COMPARTIDO'
        cliente['observaciones'] = cliente.get('observaciones') or ''
        cliente['ruc'] = cliente.get('numero_documento')
        try:
            from routes.migo import leer_pide_migo
            cliente['pide_migo'] = leer_pide_migo(id)
        except Exception as e:
            current_app.logger.warning(f"pide_migo del cliente {id}: {e}")
            cliente['pide_migo'] = False
        
        return jsonify({"success": True, "data": cliente})
        
    except Exception as e:
        current_app.logger.error(f"Error obteniendo cliente {id}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@maestros_bp.route('/api/clientes/<int:id>', methods=['PUT'])
@login_required
def api_clientes_actualizar(id):
    """Actualizar cliente"""
    conn = None
    try:
        data = request.get_json() or {}
        current_app.logger.info(f"📝 Datos recibidos para actualizar cliente {id}: {data}")
        # Bug encontrado el 20/10/2026: el botón "Guardar / Actualizar" de la cotización manda solo unos datos y
        # antes se borraban los contactos, puntos de entrega, días de crédito, límite y observaciones del cliente.
        # Ahora lo que no viene se conserva tal como está.
        actual = db_query("SELECT * FROM clientes WHERE id = %s", (id,))
        if not actual:
            return jsonify({"success": False, "error": "Cliente no encontrado"}), 404
        actual = actual[0]
        vino_condicion = 'condicion_pago' in data or 'dias_credito' in data
        for campo in ('tipo_documento', 'razon_social', 'nombre_comercial', 'direccion_fiscal', 'telefono_contacto',
                      'nombre_contacto', 'email_contacto', 'condicion_pago', 'dias_credito', 'limite_credito',
                      'descuento', 'estado', 'ambito', 'observaciones', 'activo'):
            if campo not in data and campo in actual:
                data[campo] = actual[campo]
        if not data.get('numero_documento') and not data.get('ruc'):
            data['numero_documento'] = actual.get('numero_documento')
        # La condición comercial solo se revisa si la pantalla la cambia (la ficha del cliente); si no, se respeta
        error_cond = _ordenar_condicion_cliente(data) if vino_condicion else None
        if error_cond:
            return jsonify({"success": False, "codigo": "dias_credito", "error": error_cond}), 400

        if not data.get('razon_social'):
            return jsonify({"success": False, "campo": "razon_social", "error": "Falta la razón social del cliente."}), 400

        numero_documento = data.get('numero_documento') or data.get('ruc')
        if not numero_documento:
            return jsonify({"success": False, "campo": "numero_documento", "error": "Falta el RUC/DNI del cliente."}), 400

        from database import DATABASE_URL
        
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        # ✅ VERIFICAR DUPLICADO - EXCLUYENDO EL ID ACTUAL
        cur.execute("""
            SELECT id FROM clientes 
            WHERE numero_documento = %s AND id != %s
        """, (numero_documento, id))
        
        if cur.fetchone():
            cur.close()
            return jsonify({
                "success": False, "campo": "numero_documento",
                "error": "Este RUC ya está registrado en nuestra base de datos. No se puede volver a cargar."
            }), 409

        # 1. Actualizar datos principales del cliente
        query = """
            UPDATE clientes SET
                tipo_documento = %s,
                numero_documento = %s,
                razon_social = %s,
                nombre_comercial = %s,
                direccion_fiscal = %s,
                telefono_contacto = %s,
                nombre_contacto = %s,
                email_contacto = %s,
                condicion_pago = %s,
                dias_credito = %s,
                limite_credito = %s,
                descuento = %s,
                estado = %s,
                ambito = %s,
                observaciones = %s,
                activo = %s,
                updated_at = NOW()
            WHERE id = %s
            RETURNING id, codigo_cliente, numero_documento
        """

        params = (
            data.get('tipo_documento', 'RUC'),
            numero_documento,
            data.get('razon_social'),
            data.get('nombre_comercial', data.get('razon_social')),
            data.get('direccion_fiscal') or '',
            data.get('telefono_contacto') or data.get('telefono'),
            data.get('nombre_contacto') or data.get('contacto'),
            data.get('email_contacto') or data.get('email'),
            data.get('condicion_pago', 'Contado'),
            int(data.get('dias_credito', 0) or 0),
            data.get('limite_credito') if data.get('limite_credito') is not None else '',
            data.get('descuento') if data.get('descuento') is not None else '',
            data.get('estado') or 'Activo',
            data.get('ambito') or 'COMPARTIDO',
            data.get('observaciones') or '',
            data.get('activo', True),
            id
        )

        cur.execute(query, params)
        result = cur.fetchone()

        if 'pide_migo' in data:  # N° MIGO (Erika 25/10/2026)
            from routes.migo import asegurar_migo
            asegurar_migo()
            cur.execute("UPDATE clientes SET pide_migo = %s WHERE id = %s", (bool(data.get('pide_migo')), id))

        # 2. Reemplazar contactos (solo si la pantalla los manda: la cotización no los manda)
        if 'contactos' in data:
            cur.execute("DELETE FROM clientes_contactos WHERE cliente_id = %s", (id,))
        for c in (data.get('contactos') or []):
            if not (c.get('nombre') or c.get('telefono') or c.get('email')):
                continue
            cur.execute("""
                INSERT INTO clientes_contactos (
                    cliente_id, nombre_contacto, cargo, telefono, email,
                    principal, activo
                ) VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            """, (
                id,
                c.get('nombre', ''),
                c.get('cargo', ''),
                c.get('telefono', ''),
                c.get('email', ''),
                bool(c.get('principal', False))
            ))

        # 3. Reemplazar puntos de entrega (solo si la pantalla los manda)
        if 'puntos_entrega' in data:
            cur.execute("DELETE FROM clientes_puntos_entrega WHERE cliente_id = %s", (id,))
        for p in (data.get('puntos_entrega') or []):
            if not (p.get('punto') or p.get('direccion') or p.get('instrucciones')):
                continue
            cur.execute("""
                INSERT INTO clientes_puntos_entrega (
                    cliente_id, nombre_punto, direccion, telefono_contacto,
                    responsable, principal, instrucciones,
                    google_maps, horario
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                id,
                p.get('punto', ''),
                p.get('direccion', ''),
                p.get('telefono', ''),
                p.get('contacto', ''),
                bool(p.get('principal', False)),
                p.get('instrucciones', ''),
                p.get('googleMaps', ''),
                p.get('horario', '')
            ))

        conn.commit()
        cur.close()
        conn.close()

        if result:
            cliente = {
                'id': result[0],
                'codigo_cliente': result[1],
                'numero_documento': result[2]
            }
            cliente['ruc'] = cliente.get('numero_documento')
            return jsonify({
                "success": True,
                "data": cliente,
                "message": "Cliente actualizado correctamente"
            })

        return jsonify({"success": False, "error": "No se pudo actualizar el cliente"})

    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        current_app.logger.error(f"❌ Error de BD actualizando cliente: {e}")
        from routes.diagnostico import respuesta_error_bd
        return respuesta_error_bd(e, 'el cliente')
    except Exception as e:
        current_app.logger.error(f"❌ Error actualizando cliente: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": "No se pudo actualizar el cliente: " + str(e),
                        "detalle": e.__class__.__name__ + ": " + str(e)}), 500
    finally:
        if conn:
            conn.close()


@maestros_bp.route('/api/clientes/<int:id>', methods=['DELETE'])
@login_required
def api_clientes_eliminar(id):
    """Eliminar cliente"""
    try:
        from database import DATABASE_URL

        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        # Verificar que exista
        cur.execute("""
            SELECT id
            FROM clientes
            WHERE id = %s
        """, (id,))

        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({
                "success": False,
                "error": "Cliente no encontrado"
            }), 404

        # Eliminar contactos
        cur.execute("""
            DELETE FROM clientes_contactos
            WHERE cliente_id = %s
        """, (id,))

        # Eliminar puntos de entrega
        cur.execute("""
            DELETE FROM clientes_puntos_entrega
            WHERE cliente_id = %s
        """, (id,))

        # Eliminar cliente
        cur.execute("""
            DELETE FROM clientes
            WHERE id = %s
            RETURNING id
        """, (id,))

        result = cur.fetchone()

        conn.commit()
        cur.close()
        conn.close()

        if result:
            return jsonify({
                "success": True,
                "message": "Cliente eliminado correctamente"
            })

        return jsonify({
            "success": False,
            "error": "No se pudo eliminar el cliente"
        })

    except Exception as e:
        current_app.logger.error(f"❌ Error eliminando cliente: {e}")
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@maestros_bp.route('/api/clientes/<int:id>/toggle', methods=['PUT'])
@login_required
def api_clientes_toggle(id):
    """Activar/Inactivar cliente"""
    try:
        current = db_query("SELECT activo FROM clientes WHERE id = %s", (id,))
        if not current:
            return jsonify({"success": False, "error": "Cliente no encontrado"})

        nuevo_estado = not current[0].get('activo', True)

        from database import DATABASE_URL
        
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        query = """
            UPDATE clientes
            SET activo = %s, updated_at = NOW()
            WHERE id = %s
            RETURNING id, activo
        """
        cur.execute(query, (nuevo_estado, id))
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if result:
            estado_texto = "activado" if nuevo_estado else "inactivado"
            return jsonify({
                "success": True,
                "data": {'id': result[0], 'activo': result[1]},
                "message": f"Cliente {estado_texto} correctamente"
            })

        return jsonify({"success": False, "error": "No se pudo actualizar el estado"})

    except Exception as e:
        current_app.logger.error(f"❌ Error togglando cliente: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ==========================================
# ENDPOINTS PROVEEDORES
# ==========================================

@maestros_bp.route('/api/proveedores/listar', methods=['GET'])
@login_required
def api_proveedores_listar():
    """Listar proveedores con sus contactos y puntos de entrega"""
    try:
        query = """
            SELECT 
                p.*,
                COALESCE(
                    (SELECT json_agg(
                        json_build_object(
                            'id', pc.id,
                            'nombre_contacto', pc.nombre_contacto,
                            'email', pc.email,
                            'telefono', pc.telefono,
                            'cargo', pc.cargo,
                            'principal', pc.principal,
                            'activo', pc.activo
                        )
                    ) FROM proveedores_contactos pc 
                      WHERE pc.proveedor_id = p.id AND pc.activo = true),
                    '[]'::json
                ) as contactos,
                COALESCE(
                    (SELECT json_agg(
                        json_build_object(
                            'id', pe.id,
                            'nombre_punto', pe.nombre_punto,
                            'direccion', pe.direccion,
                            'telefono_contacto', pe.telefono_contacto,
                            'responsable', pe.responsable,
                            'horario_atencion', pe.horario_atencion,
                            'instrucciones', pe.instrucciones,
                            'principal', pe.principal,
                            'activo', pe.activo
                        )
                    ) FROM proveedores_puntos_entrega pe 
                      WHERE pe.proveedor_id = p.id AND pe.activo = true),
                    '[]'::json
                ) as puntos_entrega
            FROM proveedores p
            WHERE p.activo = true
            ORDER BY id DESC
        """
        proveedores = [p for p in db_query(query) if visible_por_ambito(p.get('ambito'))]  # empresa elegida arriba
        
        # Asegurar valores por defecto
        for prov in proveedores:
            prov['condicion_pago'] = prov.get('condicion_pago') or 'Contado'
            prov['tiempo_credito'] = prov.get('tiempo_credito') or ''
            prov['estado'] = prov.get('estado') or 'Activo'
            prov['ambito'] = prov.get('ambito') or 'COMPARTIDO'
            prov['observaciones'] = prov.get('observaciones') or ''
            prov['lugar_recojo'] = prov.get('lugar_recojo') or ''
            prov['banco'] = prov.get('banco') or ''
            prov['numero_cuenta'] = prov.get('numero_cuenta') or ''
            prov['cci'] = prov.get('cci') or ''
        
        return jsonify({"success": True, "data": proveedores})
        
    except Exception as e:
        current_app.logger.error(f"❌ Error listando proveedores: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@maestros_bp.route('/api/proveedores/guardar', methods=['POST'])
@login_required
def api_proveedores_guardar():
    """Guardar proveedor (CREAR) - incluye contacto y punto de recojo"""
    try:
        data = request.get_json()
        current_app.logger.info(f"📝 Datos recibidos para guardar proveedor: {data}")

        if not data.get('razon_social'):
            return jsonify({"success": False, "error": "Razón social obligatoria"})
        if not data.get('ruc'):
            return jsonify({"success": False, "error": "RUC obligatorio"})

        from database import DATABASE_URL
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        # Generar código correlativo
        cur.execute("SELECT codigo_proveedor FROM proveedores WHERE codigo_proveedor LIKE 'PROV-%' ORDER BY id DESC LIMIT 1")
        ultimo = cur.fetchone()
        if ultimo and ultimo[0]:
            numero = int(ultimo[0].split('-')[1]) + 1
        else:
            numero = 1
        codigo = f"PROV-{str(numero).zfill(4)}"

        query = """
            INSERT INTO proveedores (
                codigo_proveedor, razon_social, ruc, razon_comercial,
                telefono, contacto, email, direccion, activo,
                condicion_pago, tiempo_credito, lugar_recojo,
                banco, numero_cuenta, cci,
                estado, ambito, observaciones,
                tipo, tipo_doc, tipo_cuenta, moneda, descuento,
                fecha_creacion
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s,
                NOW()
            )
            RETURNING id, codigo_proveedor
        """
        
        params = (
            codigo,                                    # codigo_proveedor
            data.get('razon_social'),                  # razon_social
            data.get('ruc'),                           # ruc
            data.get('razon_comercial', data.get('razon_social')),  # razon_comercial
            data.get('telefono'),                      # telefono
            data.get('contacto'),                      # contacto
            data.get('email'),                         # email
            data.get('direccion'),                     # direccion
            True,                                      # activo
            data.get('condicion_pago', 'Contado'),     # condicion_pago
            data.get('lineaCredito'),                  # tiempo_credito
            data.get('puntoRecojo'),                   # lugar_recojo
            normalizar_banco(data.get('banco')),       # banco
            data.get('cuenta'),                        # numero_cuenta
            data.get('cci'),                           # cci
            data.get('estado', 'Activo'),              # estado
            data.get('ambito', 'COMPARTIDO'),          # ambito
            data.get('obs', ''),                       # observaciones
            data.get('tipo', 'Recurrente'),            # tipo
            data.get('tipoDoc', 'RUC'),                # tipo_doc
            data.get('tipoCuenta', 'Cuenta corriente'),# tipo_cuenta
            data.get('moneda', 'Soles'),               # moneda
            data.get('descuento', '')                  # descuento
        )
        
        cur.execute(query, params)
        result = cur.fetchone()
        proveedor_id = result[0]

        # 2) INSERT contacto principal
        if data.get('contacto') or data.get('telefono') or data.get('email'):
            cur.execute("""
                INSERT INTO proveedores_contactos (
                    proveedor_id, nombre_contacto, cargo, telefono, email,
                    principal, activo, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, TRUE, TRUE, NOW(), NOW())
            """, (
                proveedor_id,
                data.get('contacto', ''),
                data.get('cargo', ''),
                data.get('telefono', ''),
                data.get('email', '')
            ))

        # 3) INSERT punto de recojo
        if data.get('puntoRecojo') or data.get('direccionRecojo'):
            cur.execute("""
                INSERT INTO proveedores_puntos_entrega (
                    proveedor_id, nombre_punto, direccion, telefono_contacto,
                    responsable, horario_atencion, instrucciones,
                    principal, activo, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, TRUE, NOW(), NOW())
            """, (
                proveedor_id,
                data.get('puntoRecojo', ''),
                data.get('direccionRecojo', ''),
                data.get('telefonoRecojo', ''),
                data.get('contactoRecojo', ''),
                data.get('horarioRecojo', ''),
                data.get('instruccionesRecojo', '')
            ))

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            "success": True,
            "data": {"id": proveedor_id, "codigo_proveedor": result[1]},
            "message": f"Proveedor creado con código {result[1]}"
        })

    except psycopg2.Error as e:
        # 🔥 CAPTURAR ERROR DE PostgreSQL Y DETECTAR QUÉ CAMPO CAUSA EL PROBLEMA
        current_app.logger.error(f"❌ Error de PostgreSQL: {e}")
        
        error_msg = str(e).lower()
        campo_error = None
        
        # Mapeo de nombres de columna a nombres legibles
        mapeo_campos = {
            'codigo_proveedor': 'Código de proveedor',
            'razon_social': 'Razón Social',
            'ruc': 'RUC',
            'razon_comercial': 'Razón Comercial',
            'telefono': 'Teléfono',
            'contacto': 'Contacto',
            'email': 'Email',
            'direccion': 'Dirección',
            'condicion_pago': 'Condición de Pago',
            'tiempo_credito': 'Línea de Crédito',
            'lugar_recojo': 'Punto de Recojo',
            'banco': 'Banco',
            'numero_cuenta': 'N° Cuenta',
            'cci': 'CCI',
            'estado': 'Estado',
            'ambito': 'Ámbito',
            'observaciones': 'Observaciones',
            'tipo': 'Tipo',
            'tipo_doc': 'Tipo de Documento',
            'tipo_cuenta': 'Tipo de Cuenta',
            'moneda': 'Moneda',
            'descuento': 'Descuento',
            'nombre_contacto': 'Nombre de Contacto',
            'cargo': 'Cargo',
            'nombre_punto': 'Punto de Recojo',
            'telefono_contacto': 'Teléfono de Contacto',
            'responsable': 'Responsable',
            'horario_atencion': 'Horario de Atención',
            'instrucciones': 'Instrucciones'
        }
        
        # Verificar si es error de "value too long"
        if 'value too long' in error_msg or 'character varying' in error_msg:
            # Intentar extraer el nombre de la columna del error
            # Ejemplo: "value too long for type character varying(20)" no siempre dice la columna
            # Pero podemos intentar detectar por el contexto
            
            # Revisar cada campo para ver cuál excede el límite
            campos_a_revisar = {
                'codigo_proveedor': 20,
                'ruc': 20,
                'telefono': 20,
                'contacto': 20,
                'email': 50,
                'condicion_pago': 20,
                'tiempo_credito': 20,
                'lugar_recojo': 20,
                'banco': 20,
                'numero_cuenta': 20,
                'cci': 20,
                'estado': 20,
                'ambito': 20,
                'tipo': 20,
                'tipo_doc': 10,
                'tipo_cuenta': 20,
                'moneda': 10,
                'descuento': 20,
                'nombre_contacto': 20,
                'cargo': 20,
                'nombre_punto': 20,
                'telefono_contacto': 20,
                'responsable': 20,
                'horario_atencion': 20
            }
            
            # Verificar cada campo en los datos recibidos
            for campo, limite in campos_a_revisar.items():
                valor = data.get(campo, '')
                if valor and len(str(valor)) > limite:
                    campo_error = mapeo_campos.get(campo, campo)
                    break
            
            # Si no se detectó automáticamente, mostrar mensaje genérico
            if campo_error:
                return jsonify({
                    "success": False,
                    "error": f"El campo '{campo_error}' excede la longitud máxima permitida ({limite} caracteres). Por favor, reduce el texto."
                })
            else:
                return jsonify({
                    "success": False,
                    "error": "Uno de los campos excede la longitud máxima permitida. Verifica que todos los campos tengan menos de 20 caracteres."
                })
        
        # Si es otro error de PostgreSQL
        return jsonify({
            "success": False,
            "error": f"Error en la base de datos: {str(e)}"
        }), 500

    except Exception as e:
        current_app.logger.error(f"❌ Error guardando proveedor: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@maestros_bp.route('/api/proveedores/<int:id>', methods=['GET'])
@login_required
def api_proveedores_obtener(id):
    try:
        from database import DATABASE_URL
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT * FROM proveedores WHERE id = %s", (id,))
        proveedor = cur.fetchone()
        if not proveedor:
            return jsonify({"success": False, "error": "Proveedor no encontrado"}), 404

        proveedor = dict(proveedor)

        cur.execute("SELECT * FROM proveedores_contactos WHERE proveedor_id = %s AND principal = TRUE LIMIT 1", (id,))
        contacto = cur.fetchone()
        cur.execute("SELECT * FROM proveedores_puntos_entrega WHERE proveedor_id = %s AND principal = TRUE LIMIT 1", (id,))
        punto = cur.fetchone()

        # 🔧 NUEVO: aplanar los datos de las 3 tablas al formato que espera fillProveedorForm()
        if contacto:
            proveedor['cargo'] = contacto.get('cargo', '')
        if punto:
            proveedor['puntoRecojo'] = punto.get('nombre_punto', '')
            proveedor['direccionRecojo'] = punto.get('direccion', '')
            proveedor['telefonoRecojo'] = punto.get('telefono_contacto', '')
            proveedor['contactoRecojo'] = punto.get('responsable', '')
            proveedor['horarioRecojo'] = punto.get('horario_atencion', '')
            proveedor['instruccionesRecojo'] = punto.get('instrucciones', '')

        proveedor['lineaCredito'] = proveedor.get('tiempo_credito', '')
        proveedor['cuenta'] = proveedor.get('numero_cuenta', '')
        proveedor['tipoDoc'] = proveedor.get('tipo_doc', 'RUC')
        proveedor['tipoCuenta'] = proveedor.get('tipo_cuenta', 'Cuenta corriente')
        proveedor['obs'] = proveedor.get('observaciones', '')

        cur.close()
        conn.close()
        return jsonify({"success": True, "data": proveedor})

    except Exception as e:
        current_app.logger.error(f"❌ Error obteniendo proveedor: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@maestros_bp.route('/api/proveedores/<int:id>', methods=['DELETE'])
@login_required
def api_proveedores_eliminar(id):
    """Eliminar proveedor.
    Pedido de Erika (19/10/2026): si tiene productos (o compras, facturas, pagos...) NO se borra: se avisa con un
    mensaje claro y se ofrece desactivarlo (queda todo su historial). Solo se borra si nunca se usó."""
    try:
        from database import DATABASE_URL

        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        cur.execute("SELECT id, razon_social FROM proveedores WHERE id = %s", (id,))
        prov = cur.fetchone()
        if not prov:
            cur.close()
            conn.close()
            return jsonify({"success": False, "error": "Proveedor no encontrado"}), 404

        usos = usos_proveedor(cur, id)
        if usos:
            cur.close()
            conn.close()
            n_prod = usos.get('productos', 0)
            if n_prod:
                msg = ("No se puede eliminar el proveedor porque tiene productos asociados. "
                       "Primero reasigne los productos a otro proveedor.")
            else:
                msg = "No se puede eliminar el proveedor porque ya tiene historial (compras, facturas o pagos)."
            detalle = ', '.join(f'{n} {NOMBRES_USO.get(t, t)}' for t, n in usos.items())
            return jsonify({"success": False, "codigo": "proveedor_en_uso", "error": msg, "usos": usos,
                            "detalle": detalle, "puede_desactivar": True,
                            "sugerencia": "Puede desactivarlo: no aparecerá en compras nuevas y se guarda todo su historial."}), 409

        cur.execute("DELETE FROM proveedores_contactos WHERE proveedor_id = %s", (id,))
        cur.execute("DELETE FROM proveedores_puntos_entrega WHERE proveedor_id = %s", (id,))

        cur.execute("""
            DELETE FROM proveedores
            WHERE id = %s
            RETURNING id
        """, (id,))

        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if result:
            return jsonify({
                "success": True,
                "message": "Proveedor eliminado correctamente"
            })

        return jsonify({"success": False, "error": "No se pudo eliminar el proveedor"})

    except Exception as e:
        current_app.logger.error(f"❌ Error eliminando proveedor: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500
 

# Tablas que guardan proveedor_id. Antes de borrar se cuentan todas: solo productos tiene llave foránea en
# Supabase; las órdenes de compra, facturas y pagos quedaban "huérfanas" si se borraba el proveedor.
NOMBRES_USO = {
    'productos': 'productos', 'ordenes_compra': 'órdenes de compra', 'solicitudes_compra': 'solicitudes de compra',
    'comprobantes_proveedor': 'facturas de proveedor', 'com_pagos': 'pagos', 'com_facturas': 'facturas de proveedor',
    'recepciones': 'recepciones', 'cuadros_comparativos': 'cuadros comparativos',
    'costos_productos': 'costos registrados',
}
TABLAS_SIN_HISTORIAL = ('proveedores_contactos', 'proveedores_puntos_entrega')


def usos_proveedor(cur, proveedor_id):
    """{tabla: cantidad} de registros que usan este proveedor (sin contar sus contactos y puntos de entrega)."""
    cur.execute("""SELECT c.table_name FROM information_schema.columns c
                   JOIN information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name
                   WHERE c.table_schema = current_schema() AND c.column_name = 'proveedor_id'
                     AND t.table_type = 'BASE TABLE' ORDER BY c.table_name""")
    tablas = [r[0] if not isinstance(r, dict) else r['table_name'] for r in cur.fetchall()]
    usos = {}
    for t in tablas:
        if t in TABLAS_SIN_HISTORIAL:
            continue
        cur.execute(f'SELECT COUNT(*) FROM "{t}" WHERE proveedor_id = %s', (proveedor_id,))
        r = cur.fetchone()
        n = r[0] if not isinstance(r, dict) else list(r.values())[0]
        if n:
            usos[t] = int(n)
    # productos primero (es lo que Erika pidió explicar)
    return dict(sorted(usos.items(), key=lambda x: x[0] != 'productos'))


@maestros_bp.route('/api/proveedores/<int:id>/desactivar', methods=['PUT', 'POST'])
@login_required
def api_proveedores_desactivar(id):
    """Baja lógica: activo = false y estado Inactivo. No borra nada; se puede reactivar o restaurar desde la Papelera."""
    try:
        from database import DATABASE_URL
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() "
                    "AND table_name = 'proveedores'")
        cols = {r[0] for r in cur.fetchall()}
        sets = ['activo = false']
        if 'estado' in cols:
            sets.append("estado = 'Inactivo'")
        if 'updated_at' in cols:
            sets.append('updated_at = NOW()')
        if 'desactivado_en' in cols:
            sets.append('desactivado_en = NOW()')
        if 'desactivado_por' in cols:
            sets.append('desactivado_por = %s')
        params = ([session.get('nombre_completo') or session.get('usuario') or ''] if 'desactivado_por' in cols else []) + [id]
        cur.execute(f"UPDATE proveedores SET {', '.join(sets)} WHERE id = %s RETURNING id, razon_social", params)
        r = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if not r:
            return jsonify({"success": False, "error": "Proveedor no encontrado"}), 404
        try:
            from routes.auditoria import registrar_auditoria
            registrar_auditoria('desactivar', 'Proveedores', tabla='proveedores', registro_id=id,
                                detalle=f'Desactivó al proveedor {r[1]} (no se borró: se guarda su historial)')
        except Exception:
            pass
        return jsonify({"success": True, "message": "Proveedor desactivado. Ya no aparecerá en compras nuevas; su historial se guarda."})
    except Exception as e:
        current_app.logger.error(f"❌ Error desactivando proveedor: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@maestros_bp.route('/api/proveedores/<int:id>', methods=['PUT'])
@login_required
def api_proveedores_actualizar(id):
    """Actualizar proveedor (EDITAR)"""
    try:
        data = request.get_json()
        from database import DATABASE_URL
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        cur.execute("""
            UPDATE proveedores SET
                razon_social = %s,
                ruc = %s,
                razon_comercial = %s,
                telefono = %s,
                contacto = %s,
                email = %s,
                direccion = %s,
                condicion_pago = %s,
                tiempo_credito = %s,
                lugar_recojo = %s,
                banco = %s,
                numero_cuenta = %s,
                cci = %s,
                estado = %s,
                ambito = %s,
                observaciones = %s,
                tipo = %s,
                tipo_doc = %s,
                tipo_cuenta = %s,
                moneda = %s,
                descuento = %s,
                activo = %s
            WHERE id = %s
        """, (
            data.get('razon_social'),
            data.get('ruc'),
            data.get('razon_comercial', data.get('razon_social')),
            data.get('telefono'),
            data.get('contacto'),
            data.get('email'),
            data.get('direccion'),
            data.get('condicion_pago', 'Contado'),
            data.get('lineaCredito'),
            data.get('puntoRecojo'),
            normalizar_banco(data.get('banco')),
            data.get('cuenta'),
            data.get('cci'),
            data.get('estado', 'Activo'),
            data.get('ambito', 'COMPARTIDO'),
            data.get('obs', ''),
            data.get('tipo', 'Recurrente'),
            data.get('tipoDoc', 'RUC'),
            data.get('tipoCuenta', 'Cuenta corriente'),
            data.get('moneda', 'Soles'),
            data.get('descuento', ''),
            data.get('activo', True),
            id
        ))

        # 2) UPSERT contacto principal
        cur.execute("SELECT id FROM proveedores_contactos WHERE proveedor_id = %s AND principal = TRUE LIMIT 1", (id,))
        contacto_existente = cur.fetchone()
        if contacto_existente:
            cur.execute("""
                UPDATE proveedores_contactos
                SET nombre_contacto = %s, cargo = %s, telefono = %s, email = %s, updated_at = NOW()
                WHERE id = %s
            """, (data.get('contacto', ''), data.get('cargo', ''), data.get('telefono', ''), data.get('email', ''), contacto_existente[0]))
        elif data.get('contacto') or data.get('telefono') or data.get('email'):
            cur.execute("""
                INSERT INTO proveedores_contactos (proveedor_id, nombre_contacto, cargo, telefono, email, principal, activo, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, TRUE, TRUE, NOW(), NOW())
            """, (id, data.get('contacto', ''), data.get('cargo', ''), data.get('telefono', ''), data.get('email', '')))

        # 3) UPSERT punto de recojo
        cur.execute("SELECT id FROM proveedores_puntos_entrega WHERE proveedor_id = %s AND principal = TRUE LIMIT 1", (id,))
        punto_existente = cur.fetchone()
        if punto_existente:
            cur.execute("""
                UPDATE proveedores_puntos_entrega
                SET nombre_punto = %s, direccion = %s, telefono_contacto = %s,
                    responsable = %s, horario_atencion = %s, instrucciones = %s, updated_at = NOW()
                WHERE id = %s
            """, (
                data.get('puntoRecojo', ''),
                data.get('direccionRecojo', ''),
                data.get('telefonoRecojo', ''),
                data.get('contactoRecojo', ''),
                data.get('horarioRecojo', ''),
                data.get('instruccionesRecojo', ''),
                punto_existente[0]
            ))
        elif data.get('puntoRecojo') or data.get('direccionRecojo'):
            cur.execute("""
                INSERT INTO proveedores_puntos_entrega (
                    proveedor_id, nombre_punto, direccion, telefono_contacto,
                    responsable, horario_atencion, instrucciones,
                    principal, activo, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, TRUE, NOW(), NOW())
            """, (
                id,
                data.get('puntoRecojo', ''),
                data.get('direccionRecojo', ''),
                data.get('telefonoRecojo', ''),
                data.get('contactoRecojo', ''),
                data.get('horarioRecojo', ''),
                data.get('instruccionesRecojo', '')
            ))

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"success": True, "message": "Proveedor actualizado correctamente"})

    except psycopg2.Error as e:
        # 🔥 CAPTURAR ERROR DE PostgreSQL Y DETECTAR QUÉ CAMPO CAUSA EL PROBLEMA
        current_app.logger.error(f"❌ Error de PostgreSQL: {e}")
        
        error_msg = str(e).lower()
        campo_error = None
        limite = 20
        
        # Mapeo de nombres de columna a nombres legibles
        mapeo_campos = {
            'codigo_proveedor': 'Código de proveedor',
            'razon_social': 'Razón Social',
            'ruc': 'RUC',
            'razon_comercial': 'Razón Comercial',
            'telefono': 'Teléfono',
            'contacto': 'Contacto',
            'email': 'Email',
            'direccion': 'Dirección',
            'condicion_pago': 'Condición de Pago',
            'tiempo_credito': 'Línea de Crédito',
            'lugar_recojo': 'Punto de Recojo',
            'banco': 'Banco',
            'numero_cuenta': 'N° Cuenta',
            'cci': 'CCI',
            'estado': 'Estado',
            'ambito': 'Ámbito',
            'observaciones': 'Observaciones',
            'tipo': 'Tipo',
            'tipo_doc': 'Tipo de Documento',
            'tipo_cuenta': 'Tipo de Cuenta',
            'moneda': 'Moneda',
            'descuento': 'Descuento'
        }
        
        if 'value too long' in error_msg or 'character varying' in error_msg:
            # Verificar cada campo
            campos_a_revisar = {
                'ruc': 20,
                'telefono': 20,
                'contacto': 20,
                'email': 50,
                'condicion_pago': 20,
                'tiempo_credito': 20,
                'lugar_recojo': 20,
                'banco': 20,
                'numero_cuenta': 20,
                'cci': 20,
                'estado': 20,
                'ambito': 20,
                'tipo': 20,
                'tipo_doc': 10,
                'tipo_cuenta': 20,
                'moneda': 10,
                'descuento': 20
            }
            
            for campo, lim in campos_a_revisar.items():
                valor = data.get(campo, '')
                if valor and len(str(valor)) > lim:
                    campo_error = mapeo_campos.get(campo, campo)
                    limite = lim
                    break
            
            if campo_error:
                return jsonify({
                    "success": False,
                    "error": f"El campo '{campo_error}' excede la longitud máxima permitida ({limite} caracteres). Por favor, reduce el texto."
                })
            else:
                return jsonify({
                    "success": False,
                    "error": "Uno de los campos excede la longitud máxima permitida. Verifica que todos los campos tengan menos de 20 caracteres."
                })
        
        return jsonify({"success": False, "error": str(e)}), 500

    except Exception as e:
        current_app.logger.error(f"❌ Error actualizando proveedor: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@maestros_bp.route('/api/proveedores/<int:id>/toggle', methods=['PUT'])
@login_required
def api_proveedores_toggle(id):
    """Activar/Inactivar proveedor"""
    try:
        current = db_query("SELECT activo FROM proveedores WHERE id = %s", (id,))
        if not current:
            return jsonify({"success": False, "error": "Proveedor no encontrado"})

        nuevo_estado = not current[0].get('activo', True)

        from database import DATABASE_URL
        
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        query = """
            UPDATE proveedores
            SET activo = %s
            WHERE id = %s
            RETURNING id, activo
        """
        cur.execute(query, (nuevo_estado, id))
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if result:
            estado_texto = "activado" if nuevo_estado else "inactivado"
            return jsonify({
                "success": True,
                "data": {'id': result[0], 'activo': result[1]},
                "message": f"Proveedor {estado_texto} correctamente"
            })

        return jsonify({"success": False, "error": "No se pudo actualizar el estado"})
    except Exception as e:
        current_app.logger.error(f"Error togglando proveedor: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ==========================================
# ENDPOINTS ALMACENES
# ==========================================

@maestros_bp.route('/api/almacenes/listar', methods=['GET'])
@login_required
def api_almacenes_listar():
    """Listar almacenes"""
    try:
        query = """
            SELECT id, codigo, nombre, tipo, responsable, telefono,
                   direccion, activo, created_at
            FROM almacenes
            WHERE activo = true
            ORDER BY nombre
        """
        result = db_query(query)
        return jsonify({"success": True, "data": result or []})
    except Exception as e:
        current_app.logger.error(f"Error listando almacenes: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@maestros_bp.route('/api/almacenes/guardar', methods=['POST'])
@login_required
def api_almacenes_guardar():
    """Guardar almacén"""
    try:
        data = request.get_json()
        current_app.logger.info(f"📝 Datos recibidos para guardar almacén: {data}")

        if not data.get('codigo'):
            return jsonify({"success": False, "error": "Código obligatorio"})
        if not data.get('nombre'):
            return jsonify({"success": False, "error": "Nombre obligatorio"})
        if not data.get('responsable'):
            return jsonify({"success": False, "error": "Responsable obligatorio"})

        existing = db_query("SELECT id FROM almacenes WHERE codigo = %s", (data.get('codigo'),))
        if existing:
            return jsonify({"success": False, "error": "Ya existe un almacén con este código"})

        from database import DATABASE_URL
        
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        # 🔥 SIN created_at y updated_at
        query = """
            INSERT INTO almacenes (
                codigo, nombre, tipo, responsable, telefono,
                direccion, activo
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, codigo
        """

        params = (
            data.get('codigo'),
            data.get('nombre'),
            data.get('tipo', 'Principal'),
            data.get('responsable'),
            data.get('telefono'),
            data.get('direccion'),
            data.get('activo', True)
        )

        cur.execute(query, params)
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if result:
            return jsonify({
                "success": True,
                "data": {'id': result[0], 'codigo': result[1]},
                "message": f"Almacén creado con código {result[1]}"
            })

        return jsonify({"success": False, "error": "No se pudo crear el almacén"})
    except Exception as e:
        current_app.logger.error(f"Error guardando almacén: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@maestros_bp.route('/api/almacenes/<int:id>', methods=['GET'])
@login_required
def api_almacenes_obtener(id):
    """Obtener almacén por ID"""
    try:
        query = """
            SELECT id, codigo, nombre, tipo, responsable, telefono,
                   direccion, activo
            FROM almacenes
            WHERE id = %s
        """
        result = db_query(query, (id,))
        if result and len(result) > 0:
            return jsonify({"success": True, "data": result[0]})
        return jsonify({"success": False, "error": "Almacén no encontrado"}), 404
    except Exception as e:
        current_app.logger.error(f"Error obteniendo almacén: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@maestros_bp.route('/api/almacenes/<int:id>', methods=['DELETE'])
@login_required
def api_almacenes_eliminar(id):
    """Eliminar almacén"""
    try:
        from database import DATABASE_URL

        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        cur.execute("""
            DELETE FROM almacenes
            WHERE id = %s
            RETURNING id
        """, (id,))

        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if result:
            return jsonify({
                "success": True,
                "message": "Almacén eliminado correctamente"
            })

        return jsonify({"success": False, "error": "Almacén no encontrado"}), 404

    except Exception as e:
        current_app.logger.error(f"❌ Error eliminando almacén: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@maestros_bp.route('/api/almacenes/<int:id>', methods=['PUT'])
@login_required
def api_almacenes_actualizar(id):
    """Actualizar almacén"""
    try:
        data = request.get_json()
        current_app.logger.info(f"📝 Datos recibidos para actualizar almacén {id}: {data}")

        if not data.get('codigo'):
            return jsonify({"success": False, "error": "Código obligatorio"})
        if not data.get('nombre'):
            return jsonify({"success": False, "error": "Nombre obligatorio"})
        if not data.get('responsable'):
            return jsonify({"success": False, "error": "Responsable obligatorio"})

        from database import DATABASE_URL
        
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        query = """
            UPDATE almacenes SET
                codigo = %s,
                nombre = %s,
                tipo = %s,
                responsable = %s,
                telefono = %s,
                direccion = %s,
                activo = %s
            WHERE id = %s
            RETURNING id, codigo
        """

        params = (
            data.get('codigo'),
            data.get('nombre'),
            data.get('tipo', 'Principal'),
            data.get('responsable'),
            data.get('telefono'),
            data.get('direccion'),
            data.get('activo', True),
            id
        )

        cur.execute(query, params)
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if result:
            return jsonify({
                "success": True,
                "data": {'id': result[0], 'codigo': result[1]},
                "message": "Almacén actualizado correctamente"
            })

        return jsonify({"success": False, "error": "No se pudo actualizar el almacén"})
    except Exception as e:
        current_app.logger.error(f"Error actualizando almacén: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@maestros_bp.route('/api/almacenes/<int:id>/toggle', methods=['PUT'])
@login_required
def api_almacenes_toggle(id):
    """Activar/Inactivar almacén"""
    try:
        current = db_query("SELECT activo FROM almacenes WHERE id = %s", (id,))
        if not current:
            return jsonify({"success": False, "error": "Almacén no encontrado"})

        nuevo_estado = not current[0].get('activo', True)

        from database import DATABASE_URL
        
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        query = """
            UPDATE almacenes
            SET activo = %s
            WHERE id = %s
            RETURNING id, activo
        """
        cur.execute(query, (nuevo_estado, id))
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if result:
            estado_texto = "activado" if nuevo_estado else "inactivado"
            return jsonify({
                "success": True,
                "data": {'id': result[0], 'activo': result[1]},
                "message": f"Almacén {estado_texto} correctamente"
            })

        return jsonify({"success": False, "error": "No se pudo actualizar el estado"})
    except Exception as e:
        current_app.logger.error(f"Error togglando almacén: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ==========================================
# ENDPOINTS CATEGORÍAS
# ==========================================

@maestros_bp.route('/api/categorias/listar', methods=['GET'])
@login_required
def api_categorias_listar():
    """Listar categorías"""
    try:
        query = """
            SELECT id, codigo, nombre, tipo, activo, created_at
            FROM categorias
            WHERE activo = true
            ORDER BY id DESC
        """
        result = db_query(query)
        return jsonify({"success": True, "data": result or []})
    except Exception as e:
        current_app.logger.error(f"Error listando categorías: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@maestros_bp.route('/api/categorias/guardar', methods=['POST'])
@login_required
def api_categorias_guardar():
    """Guardar categoría"""
    try:
        data = request.get_json()
        current_app.logger.info(f"📝 Datos recibidos para guardar categoría: {data}")

        if not data.get('codigo'):
            return jsonify({"success": False, "error": "Código obligatorio"})
        if not data.get('nombre'):
            return jsonify({"success": False, "error": "Nombre obligatorio"})

        existing = db_query("SELECT id FROM categorias WHERE codigo = %s", (data.get('codigo'),))
        if existing:
            return jsonify({"success": False, "error": "Ya existe una categoría con este código"})

        from database import DATABASE_URL
        
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        query = """
            INSERT INTO categorias (
                codigo, nombre, tipo, activo
            ) VALUES (%s, %s, %s, %s)
            RETURNING id, codigo
        """

        params = (
            data.get('codigo'),
            data.get('nombre'),
            data.get('tipo', 'General'),
            data.get('activo', True)
        )

        cur.execute(query, params)
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if result:
            return jsonify({
                "success": True,
                "data": {'id': result[0], 'codigo': result[1]},
                "message": f"Categoría creada con código {result[1]}"
            })

        return jsonify({"success": False, "error": "No se pudo crear la categoría"})
    except Exception as e:
        current_app.logger.error(f"Error guardando categoría: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@maestros_bp.route('/api/categorias/<int:id>', methods=['GET'])
@login_required
def api_categorias_obtener(id):
    """Obtener categoría por ID"""
    try:
        query = """
            SELECT id, codigo, nombre, tipo, activo
            FROM categorias
            WHERE id = %s
        """
        result = db_query(query, (id,))
        if result and len(result) > 0:
            return jsonify({"success": True, "data": result[0]})
        return jsonify({"success": False, "error": "Categoría no encontrada"}), 404
    except Exception as e:
        current_app.logger.error(f"Error obteniendo categoría: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@maestros_bp.route('/api/categorias/<int:id>', methods=['DELETE'])
@login_required
def api_categorias_eliminar(id):
    """Eliminar categoría"""
    try:
        from database import DATABASE_URL

        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        cur.execute("""
            DELETE FROM categorias
            WHERE id = %s
            RETURNING id
        """, (id,))

        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if result:
            return jsonify({
                "success": True,
                "message": "Categoría eliminada correctamente"
            })

        return jsonify({"success": False, "error": "Categoría no encontrada"}), 404

    except Exception as e:
        current_app.logger.error(f"❌ Error eliminando categoría: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@maestros_bp.route('/api/categorias/<int:id>', methods=['PUT'])
@login_required
def api_categorias_actualizar(id):
    """Actualizar categoría"""
    try:
        data = request.get_json()
        current_app.logger.info(f"📝 Datos recibidos para actualizar categoría {id}: {data}")

        if not data.get('codigo'):
            return jsonify({"success": False, "error": "Código obligatorio"})
        if not data.get('nombre'):
            return jsonify({"success": False, "error": "Nombre obligatorio"})

        from database import DATABASE_URL
        
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        query = """
            UPDATE categorias SET
                codigo = %s,
                nombre = %s,
                tipo = %s,
                activo = %s
            WHERE id = %s
            RETURNING id, codigo
        """

        params = (
            data.get('codigo'),
            data.get('nombre'),
            data.get('tipo', 'General'),
            data.get('activo', True),
            id
        )

        cur.execute(query, params)
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if result:
            return jsonify({
                "success": True,
                "data": {'id': result[0], 'codigo': result[1]},
                "message": "Categoría actualizada correctamente"
            })

        return jsonify({"success": False, "error": "No se pudo actualizar la categoría"})
    except Exception as e:
        current_app.logger.error(f"Error actualizando categoría: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500




@maestros_bp.route('/api/categorias/<int:id>/toggle', methods=['PUT'])
@login_required
def api_categorias_toggle(id):
    """Activar/Inactivar categoría"""
    try:
        current = db_query("SELECT activo FROM categorias WHERE id = %s", (id,))
        if not current:
            return jsonify({"success": False, "error": "Categoría no encontrada"})

        nuevo_estado = not current[0].get('activo', True)

        from database import DATABASE_URL
        
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        query = """
            UPDATE categorias
            SET activo = %s
            WHERE id = %s
            RETURNING id, activo
        """
        cur.execute(query, (nuevo_estado, id))
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if result:
            estado_texto = "activada" if nuevo_estado else "inactivada"
            return jsonify({
                "success": True,
                "data": {'id': result[0], 'activo': result[1]},
                "message": f"Categoría {estado_texto} correctamente"
            })

        return jsonify({"success": False, "error": "No se pudo actualizar el estado"})
    except Exception as e:
        current_app.logger.error(f"Error togglando categoría: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ==========================================
# ENDPOINTS MARCAS
# ==========================================

@maestros_bp.route('/api/marcas/listar', methods=['GET'])
@login_required
def api_marcas_listar():
    """Listar marcas"""
    try:
        query = """
            SELECT id, codigo, nombre, tipo, activo, created_at
            FROM marcas
            WHERE activo = true
            ORDER BY id DESC
        """
        result = db_query(query)
        return jsonify({"success": True, "data": result or []})
    except Exception as e:
        current_app.logger.error(f"Error listando marcas: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@maestros_bp.route('/api/marcas/guardar', methods=['POST'])
@login_required
def api_marcas_guardar():
    """Guardar marca"""
    try:
        data = request.get_json()
        current_app.logger.info(f"📝 Datos recibidos para guardar marca: {data}")

        if not data.get('codigo'):
            return jsonify({"success": False, "error": "Código obligatorio"})
        if not data.get('nombre'):
            return jsonify({"success": False, "error": "Nombre obligatorio"})

        existing = db_query("SELECT id FROM marcas WHERE codigo = %s", (data.get('codigo'),))
        if existing:
            return jsonify({"success": False, "error": "Ya existe una marca con este código"})

        from database import DATABASE_URL
        
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        query = """
            INSERT INTO marcas (
                codigo, nombre, tipo, activo
            ) VALUES (%s, %s, %s, %s)
            RETURNING id, codigo
        """

        params = (
            data.get('codigo'),
            data.get('nombre'),
            data.get('tipo', 'General'),
            data.get('activo', True)
        )

        cur.execute(query, params)
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if result:
            return jsonify({
                "success": True,
                "data": {'id': result[0], 'codigo': result[1]},
                "message": f"Marca creada con código {result[1]}"
            })

        return jsonify({"success": False, "error": "No se pudo crear la marca"})
    except Exception as e:
        current_app.logger.error(f"Error guardando marca: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@maestros_bp.route('/api/marcas/<int:id>', methods=['GET'])
@login_required
def api_marcas_obtener(id):
    """Obtener marca por ID"""
    try:
        query = """
            SELECT id, codigo, nombre, tipo, activo
            FROM marcas
            WHERE id = %s
        """
        result = db_query(query, (id,))
        if result and len(result) > 0:
            return jsonify({"success": True, "data": result[0]})
        return jsonify({"success": False, "error": "Marca no encontrada"}), 404
    except Exception as e:
        current_app.logger.error(f"Error obteniendo marca: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@maestros_bp.route('/api/marcas/<int:id>', methods=['DELETE'])
@login_required
def api_marcas_eliminar(id):
    """Eliminar marca"""
    try:
        from database import DATABASE_URL

        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        cur.execute("""
            DELETE FROM marcas
            WHERE id = %s
            RETURNING id
        """, (id,))

        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if result:
            return jsonify({
                "success": True,
                "message": "Marca eliminada correctamente"
            })

        return jsonify({"success": False, "error": "Marca no encontrada"}), 404

    except Exception as e:
        current_app.logger.error(f"❌ Error eliminando marca: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@maestros_bp.route('/api/marcas/<int:id>', methods=['PUT'])
@login_required
def api_marcas_actualizar(id):
    """Actualizar marca"""
    try:
        data = request.get_json()
        current_app.logger.info(f"📝 Datos recibidos para actualizar marca {id}: {data}")

        if not data.get('codigo'):
            return jsonify({"success": False, "error": "Código obligatorio"})
        if not data.get('nombre'):
            return jsonify({"success": False, "error": "Nombre obligatorio"})

        from database import DATABASE_URL
        
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        query = """
            UPDATE marcas SET
                codigo = %s,
                nombre = %s,
                tipo = %s,
                activo = %s
            WHERE id = %s
            RETURNING id, codigo
        """

        params = (
            data.get('codigo'),
            data.get('nombre'),
            data.get('tipo', 'General'),
            data.get('activo', True),
            id
        )

        cur.execute(query, params)
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if result:
            return jsonify({
                "success": True,
                "data": {'id': result[0], 'codigo': result[1]},
                "message": "Marca actualizada correctamente"
            })

        return jsonify({"success": False, "error": "No se pudo actualizar la marca"})
    except Exception as e:
        current_app.logger.error(f"Error actualizando marca: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@maestros_bp.route('/api/marcas/<int:id>/toggle', methods=['PUT'])
@login_required
def api_marcas_toggle(id):
    """Activar/Inactivar marca"""
    try:
        current = db_query("SELECT activo FROM marcas WHERE id = %s", (id,))
        if not current:
            return jsonify({"success": False, "error": "Marca no encontrada"})

        nuevo_estado = not current[0].get('activo', True)

        from database import DATABASE_URL
        
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        query = """
            UPDATE marcas
            SET activo = %s
            WHERE id = %s
            RETURNING id, activo
        """
        cur.execute(query, (nuevo_estado, id))
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if result:
            estado_texto = "activada" if nuevo_estado else "inactivada"
            return jsonify({
                "success": True,
                "data": {'id': result[0], 'activo': result[1]},
                "message": f"Marca {estado_texto} correctamente"
            })

        return jsonify({"success": False, "error": "No se pudo actualizar el estado"})
    except Exception as e:
        current_app.logger.error(f"Error togglando marca: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ==========================================
# ENDPOINTS UNIDADES DE MEDIDA (UM)
# ==========================================

@maestros_bp.route('/api/um/listar', methods=['GET'])
@login_required
def api_um_listar():
    """Listar unidades de medida"""
    try:
        query = """
            SELECT id, codigo, nombre, abreviatura, tipo,
                   decimales, activo, ambito, created_at
            FROM um
            WHERE activo = true
            ORDER BY id DESC
        """
        result = db_query(query)
        return jsonify({"success": True, "data": result or []})
    except Exception as e:
        current_app.logger.error(f"Error listando unidades de medida: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@maestros_bp.route('/api/um/guardar', methods=['POST'])
@login_required
def api_um_guardar():
    """Guardar unidad de medida"""
    try:
        data = request.get_json()
        current_app.logger.info(f"📝 Datos recibidos para guardar unidad: {data}")

        if not data.get('codigo'):
            return jsonify({"success": False, "error": "Código obligatorio"})
        if not data.get('nombre'):
            return jsonify({"success": False, "error": "Nombre obligatorio"})
        if not data.get('abreviatura'):
            return jsonify({"success": False, "error": "Abreviatura obligatoria"})

        existing = db_query("SELECT id FROM um WHERE codigo = %s", (data.get('codigo'),))
        if existing:
            return jsonify({"success": False, "error": "Ya existe una unidad con este código"})

        from database import DATABASE_URL
        
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        query = """
            INSERT INTO um (
                codigo, nombre, abreviatura, tipo,
                decimales, activo, ambito
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, codigo
        """

        params = (
            data.get('codigo'),
            data.get('nombre'),
            data.get('abreviatura'),
            data.get('tipo', 'Cantidad'),
            data.get('decimales', False),
            data.get('activo', True),
            data.get('ambito', 'COMPARTIDO')
        )

        cur.execute(query, params)
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if result:
            return jsonify({
                "success": True,
                "data": {'id': result[0], 'codigo': result[1]},
                "message": f"Unidad creada con código {result[1]}"
            })

        return jsonify({"success": False, "error": "No se pudo crear la unidad"})
    except Exception as e:
        current_app.logger.error(f"Error guardando unidad de medida: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@maestros_bp.route('/api/um/<int:id>', methods=['GET'])
@login_required
def api_um_obtener(id):
    """Obtener unidad de medida por ID"""
    try:
        query = """
            SELECT id, codigo, nombre, abreviatura, tipo,
                   decimales, activo, ambito
            FROM um
            WHERE id = %s
        """
        result = db_query(query, (id,))
        if result and len(result) > 0:
            return jsonify({"success": True, "data": result[0]})
        return jsonify({"success": False, "error": "Unidad no encontrada"}), 404
    except Exception as e:
        current_app.logger.error(f"Error obteniendo unidad: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@maestros_bp.route('/api/um/<int:id>', methods=['DELETE'])
@login_required
def api_um_eliminar(id):
    """Eliminar unidad de medida"""
    try:
        from database import DATABASE_URL

        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        cur.execute("""
            DELETE FROM um
            WHERE id = %s
            RETURNING id
        """, (id,))

        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if result:
            return jsonify({
                "success": True,
                "message": "Unidad eliminada correctamente"
            })

        return jsonify({"success": False, "error": "Unidad no encontrada"}), 404

    except Exception as e:
        current_app.logger.error(f"❌ Error eliminando unidad de medida: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@maestros_bp.route('/api/um/<int:id>', methods=['PUT'])
@login_required
def api_um_actualizar(id):
    """Actualizar unidad de medida"""
    try:
        data = request.get_json()
        current_app.logger.info(f"📝 Datos recibidos para actualizar unidad {id}: {data}")

        if not data.get('codigo'):
            return jsonify({"success": False, "error": "Código obligatorio"})
        if not data.get('nombre'):
            return jsonify({"success": False, "error": "Nombre obligatorio"})
        if not data.get('abreviatura'):
            return jsonify({"success": False, "error": "Abreviatura obligatoria"})

        from database import DATABASE_URL
        
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        query = """
            UPDATE um SET
                codigo = %s,
                nombre = %s,
                abreviatura = %s,
                tipo = %s,
                decimales = %s,
                ambito = %s,
                activo = %s
            WHERE id = %s
            RETURNING id, codigo
        """

        params = (
            data.get('codigo'),
            data.get('nombre'),
            data.get('abreviatura'),
            data.get('tipo', 'Cantidad'),
            data.get('decimales', False),
            data.get('ambito', 'COMPARTIDO'),
            data.get('activo', True),
            id
        )

        cur.execute(query, params)
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if result:
            return jsonify({
                "success": True,
                "data": {'id': result[0], 'codigo': result[1]},
                "message": "Unidad actualizada correctamente"
            })

        return jsonify({"success": False, "error": "No se pudo actualizar la unidad"})
    except Exception as e:
        current_app.logger.error(f"Error actualizando unidad: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@maestros_bp.route('/api/um/<int:id>/toggle', methods=['PUT'])
@login_required
def api_um_toggle(id):
    """Activar/Inactivar unidad de medida"""
    try:
        current = db_query("SELECT activo FROM um WHERE id = %s", (id,))
        if not current:
            return jsonify({"success": False, "error": "Unidad no encontrada"})

        nuevo_estado = not current[0].get('activo', True)

        from database import DATABASE_URL
        
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        query = """
            UPDATE um
            SET activo = %s
            WHERE id = %s
            RETURNING id, activo
        """
        cur.execute(query, (nuevo_estado, id))
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if result:
            estado_texto = "activada" if nuevo_estado else "inactivada"
            return jsonify({
                "success": True,
                "data": {'id': result[0], 'activo': result[1]},
                "message": f"Unidad {estado_texto} correctamente"
            })

        return jsonify({"success": False, "error": "No se pudo actualizar el estado"})
    except Exception as e:
        current_app.logger.error(f"Error togglando unidad de medida: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ==========================================
# ENDPOINT DE PRUEBA
# ==========================================

@maestros_bp.route('/api/test', methods=['GET'])
@login_required
def api_test():
    """Endpoint para probar que la API funciona"""
    return jsonify({"success": True, "message": "API de maestros funcionando correctamente"})


@maestros_bp.route('/api/ruc-registrado', methods=['GET'])
@login_required
def api_ruc_registrado():
    """¿Este RUC ya está registrado? (pedido de Erika 20/10/2026: aviso visible apenas se escribe o carga el RUC).
    tipo=cliente|proveedor · excluir=id del registro que se está editando."""
    ruc = ''.join(ch for ch in (request.args.get('ruc') or '') if ch.isalnum())
    tipo = request.args.get('tipo', 'cliente')
    try:
        excluir = int(request.args.get('excluir') or 0)
    except ValueError:
        excluir = 0
    if len(ruc) < 8:
        return jsonify({'success': True, 'registrado': False})
    if tipo == 'proveedor':
        filas = db_query("""SELECT id, codigo_proveedor AS codigo, razon_social,
                                 COALESCE(to_jsonb(p) ->> 'estado', CASE WHEN COALESCE((to_jsonb(p) ->> 'activo')::boolean, TRUE)
                                          THEN 'Activo' ELSE 'Inactivo' END) AS estado
                            FROM proveedores p WHERE REPLACE(COALESCE(ruc, ''), ' ', '') = %s AND id <> %s
                            ORDER BY id LIMIT 1""", (ruc, excluir))
    else:
        filas = db_query("""SELECT id, codigo_cliente AS codigo, razon_social,
                                 COALESCE(to_jsonb(c) ->> 'estado', 'Activo') AS estado
                            FROM clientes c WHERE REPLACE(COALESCE(numero_documento, ''), ' ', '') = %s AND id <> %s
                            ORDER BY id LIMIT 1""", (ruc, excluir))
    if not filas:
        return jsonify({'success': True, 'registrado': False})
    f = filas[0]
    return jsonify({'success': True, 'registrado': True, 'id': f['id'], 'codigo': f.get('codigo') or '',
                    'razon_social': f.get('razon_social') or '', 'estado': f.get('estado') or ''})


@maestros_bp.route('/api/clientes/buscar', methods=['GET'])
@login_required
def api_clientes_buscar():
    """Buscar clientes por RUC, razón social o nombre comercial (con contactos)"""
    try:
        q = request.args.get('q', '').strip()

        if not q or len(q) < 2:
            return jsonify({'success': True, 'data': []})

        query = """
            SELECT 
                c.id, 
                c.codigo_cliente, 
                c.razon_social, 
                c.numero_documento as ruc,
                c.nombre_comercial, 
                c.nombre_contacto, 
                c.telefono_contacto,
                c.email_contacto, 
                c.direccion_fiscal, 
                c.condicion_pago,
                c.activo,
                COALESCE(
                    (SELECT json_agg(
                        json_build_object(
                            'id', cc.id,
                            'nombre', cc.nombre_contacto,
                            'nombre_contacto', cc.nombre_contacto,
                            'cargo', cc.cargo,
                            'telefono', cc.telefono,
                            'email', cc.email,
                            'principal', cc.principal
                        ) ORDER BY cc.principal DESC, cc.id ASC
                    ) FROM clientes_contactos cc 
                      WHERE cc.cliente_id = c.id AND cc.activo = true),
                    '[]'::json
                ) as contactos,
                COALESCE(
                    (SELECT json_agg(
                        json_build_object(
                            'id', pe.id,
                            'nombre_punto', pe.nombre_punto,
                            'punto', pe.nombre_punto,
                            'direccion', pe.direccion,
                            'telefono_contacto', pe.telefono_contacto,
                            'telefono', pe.telefono_contacto,
                            'responsable', pe.responsable,
                            'contacto', pe.responsable,
                            'condicion_pago', pe.condicion_pago,
                            'tiempo_credito', pe.tiempo_credito,
                            'instrucciones', pe.instrucciones,
                            'google_maps', pe.google_maps,
                            'googleMaps', pe.google_maps,
                            'horario', pe.horario,
                            'principal', pe.principal,
                            'activo', pe.activo
                        )
                    ) FROM clientes_puntos_entrega pe 
                      WHERE pe.cliente_id = c.id AND pe.activo = true),
                    '[]'::json
                ) as puntos_entrega
            FROM clientes c
            WHERE c.activo = TRUE
            AND (
                c.numero_documento ILIKE %s 
                OR c.razon_social ILIKE %s 
                OR c.nombre_comercial ILIKE %s
                OR c.codigo_cliente ILIKE %s
            )
            ORDER BY c.razon_social
            LIMIT 20
        """
        like = f"%{q}%"
        results = db_query(query, (like, like, like, like))

        return jsonify({'success': True, 'data': results})

    except Exception as e:
        print(f"❌ Error en api_clientes_buscar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500