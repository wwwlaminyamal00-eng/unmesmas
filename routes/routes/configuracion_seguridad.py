# ============================================================
# CONFIGURACIÓN Y SEGURIDAD - Módulo 1 del ERP
# ============================================================
# Este módulo maneja:
#   - Empresas (KCF, AGD)
#   - Usuarios y permisos
#   - Correlativos por empresa
#   - Parámetros generales
#   - Integración ERP
# ============================================================

from flask import Blueprint, request, jsonify, session, render_template
from datetime import datetime
import json
from database import db_query, db_execute, db_tx, get_connection
from psycopg2.extras import RealDictCursor

# ============================================================
# BLUEPRINT
# ============================================================
config_seguridad_bp = Blueprint('config_seguridad', __name__, url_prefix='/api/config')

# ============================================================
# 1. EMPRESAS
# ============================================================

@config_seguridad_bp.route('/empresas', methods=['GET'])
def get_empresas():
    """Obtener todas las empresas activas con sus cuentas bancarias"""
    try:
        empresas = db_query("""
            SELECT 
                e.id,
                e.codigo,
                e.nombre_corto,
                e.nombre_comercial,
                e.razon_social,
                e.ruc,
                e.direccion_fiscal,
                e.telefono,
                e.correo_documentos,
                e.logo_url,
                e.color_primario,
                e.color_secundario,
                e.color_pastel,
                e.estado,
                e.created_at,
                e.updated_at,
                (
                    SELECT json_agg(
                        json_build_object(
                            'id', cb.id,
                            'banco', cb.banco,
                            'tipo_cuenta', cb.tipo_cuenta,
                            'moneda', cb.moneda,
                            'numero_cuenta', cb.numero_cuenta,
                            'cci', cb.cci,
                            'es_principal', cb.es_principal,
                            'estado', cb.estado
                        )
                    )
                    FROM erp_empresa_cuentas_bancarias cb
                    WHERE cb.empresa_id = e.id
                    AND cb.estado = 'activo'
                ) as cuentas_bancarias
            FROM erp_empresas e
            WHERE e.estado = 'activo'
            ORDER BY e.codigo
        """)
        
        return jsonify({
            'success': True,
            'data': empresas,
            'total': len(empresas)
        })
        
    except Exception as e:
        print(f"❌ Error en get_empresas: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@config_seguridad_bp.route('/empresas/<empresa_id>', methods=['GET'])
def get_empresa(empresa_id):
    """Obtener una empresa específica con sus cuentas"""
    try:
        empresa = db_query("""
            SELECT 
                e.id,
                e.codigo,
                e.nombre_corto,
                e.nombre_comercial,
                e.razon_social,
                e.ruc,
                e.direccion_fiscal,
                e.telefono,
                e.correo_documentos,
                e.logo_url,
                e.color_primario,
                e.color_secundario,
                e.color_pastel,
                e.estado,
                e.created_at,
                e.updated_at,
                (
                    SELECT json_agg(
                        json_build_object(
                            'id', cb.id,
                            'banco', cb.banco,
                            'tipo_cuenta', cb.tipo_cuenta,
                            'moneda', cb.moneda,
                            'numero_cuenta', cb.numero_cuenta,
                            'cci', cb.cci,
                            'es_principal', cb.es_principal,
                            'estado', cb.estado
                        )
                    )
                    FROM erp_empresa_cuentas_bancarias cb
                    WHERE cb.empresa_id = e.id
                    AND cb.estado = 'activo'
                ) as cuentas_bancarias
            FROM erp_empresas e
            WHERE e.id = %s AND e.estado = 'activo'
        """, (empresa_id,))
        
        if not empresa:
            return jsonify({'success': False, 'error': 'Empresa no encontrada'}), 404
        
        return jsonify({
            'success': True,
            'data': empresa[0]
        })
        
    except Exception as e:
        print(f"❌ Error en get_empresa: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@config_seguridad_bp.route('/empresas', methods=['POST'])
def create_empresa():
    """Crear una nueva empresa"""
    try:
        data = request.get_json()
        
        required = ['codigo', 'nombre_corto', 'nombre_comercial', 'razon_social', 'ruc']
        for field in required:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'Campo {field} es requerido'}), 400
        
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            cur.execute("""
                INSERT INTO erp_empresas (
                    codigo, nombre_corto, nombre_comercial, razon_social,
                    ruc, direccion_fiscal, telefono, correo_documentos,
                    logo_url, color_primario, color_secundario, color_pastel,
                    estado
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                data.get('codigo'),
                data.get('nombre_corto'),
                data.get('nombre_comercial'),
                data.get('razon_social'),
                data.get('ruc'),
                data.get('direccion_fiscal', ''),
                data.get('telefono', ''),
                data.get('correo_documentos', ''),
                data.get('logo_url', ''),
                data.get('color_primario', '#EF233C'),
                data.get('color_secundario', '#1F1F1F'),
                data.get('color_pastel', '#FFECEF'),
                data.get('estado', 'activo')
            ))
            
            empresa_id = cur.fetchone()['id']
            
            cuentas = data.get('cuentas_bancarias', [])
            for cuenta in cuentas:
                if cuenta.get('banco'):
                    cur.execute("""
                        INSERT INTO erp_empresa_cuentas_bancarias (
                            empresa_id, banco, tipo_cuenta, moneda,
                            numero_cuenta, cci, es_principal, estado
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        empresa_id,
                        cuenta.get('banco'),
                        cuenta.get('tipo_cuenta'),
                        cuenta.get('moneda', 'PEN'),
                        cuenta.get('numero_cuenta'),
                        cuenta.get('cci'),
                        cuenta.get('es_principal', False),
                        cuenta.get('estado', 'activo')
                    ))
            
            return jsonify({
                'success': True,
                'data': {'id': empresa_id},
                'message': 'Empresa creada exitosamente'
            })
            
    except Exception as e:
        print(f"❌ Error en create_empresa: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@config_seguridad_bp.route('/empresas/<empresa_id>', methods=['PUT'])
def update_empresa(empresa_id):
    """Actualizar una empresa existente"""
    try:
        data = request.get_json()
        
        with db_tx() as conn:
            cur = conn.cursor()
            
            cur.execute("""
                UPDATE erp_empresas SET
                    codigo = %s,
                    nombre_corto = %s,
                    nombre_comercial = %s,
                    razon_social = %s,
                    ruc = %s,
                    direccion_fiscal = %s,
                    telefono = %s,
                    correo_documentos = %s,
                    logo_url = %s,
                    color_primario = %s,
                    color_secundario = %s,
                    color_pastel = %s,
                    estado = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (
                data.get('codigo'),
                data.get('nombre_corto'),
                data.get('nombre_comercial'),
                data.get('razon_social'),
                data.get('ruc'),
                data.get('direccion_fiscal', ''),
                data.get('telefono', ''),
                data.get('correo_documentos', ''),
                data.get('logo_url', ''),
                data.get('color_primario', '#EF233C'),
                data.get('color_secundario', '#1F1F1F'),
                data.get('color_pastel', '#FFECEF'),
                data.get('estado', 'activo'),
                empresa_id
            ))
            
            return jsonify({
                'success': True,
                'message': 'Empresa actualizada exitosamente'
            })
            
    except Exception as e:
        print(f"❌ Error en update_empresa: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@config_seguridad_bp.route('/empresas/<empresa_id>', methods=['DELETE'])
def delete_empresa(empresa_id):
    """Eliminar empresa (borrado lógico)"""
    try:
        db_execute("""
            UPDATE erp_empresas SET estado = 'inactivo', updated_at = NOW()
            WHERE id = %s
        """, (empresa_id,))
        
        return jsonify({
            'success': True,
            'message': 'Empresa desactivada exitosamente'
        })
        
    except Exception as e:
        print(f"❌ Error en delete_empresa: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# 2. USUARIOS Y PERMISOS
# ============================================================

@config_seguridad_bp.route('/usuarios', methods=['GET'])
def get_usuarios():
    """Obtener todos los usuarios con sus empresas y roles"""
    try:
        usuarios = db_query("""
            SELECT 
                u.id,
                u.auth_user_id,
                u.usuario_sistema,
                u.nombres_apellidos,
                u.area,
                u.correo,
                u.celular,
                u.estado,
                u.created_at,
                u.updated_at,
                (
                    SELECT json_agg(
                        json_build_object(
                            'id', ue.id,
                            'empresa_id', ue.empresa_id,
                            'empresa_codigo', e.codigo,
                            'empresa_nombre', e.nombre_comercial,
                            'es_principal', ue.es_empresa_principal,
                            'estado', ue.estado,
                            'rol_id', ue.rol_id,
                            'rol_codigo', r.codigo,
                            'rol_nombre', r.nombre,
                            'rol_es_admin', r.es_admin
                        )
                    )
                    FROM erp_usuario_empresas ue
                    LEFT JOIN erp_empresas e ON e.id = ue.empresa_id
                    LEFT JOIN erp_roles r ON r.id = ue.rol_id
                    WHERE ue.auth_user_id = u.auth_user_id
                    AND ue.estado = 'activo'
                ) as empresas_acceso
            FROM usuarios u
            WHERE u.estado = 'activo'
            ORDER BY u.usuario_sistema
        """)
        
        return jsonify({
            'success': True,
            'data': usuarios,
            'total': len(usuarios)
        })
        
    except Exception as e:
        print(f"❌ Error en get_usuarios: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@config_seguridad_bp.route('/usuarios/<usuario_id>', methods=['GET'])
def get_usuario(usuario_id):
    """Obtener un usuario específico"""
    try:
        usuario = db_query("""
            SELECT 
                u.id,
                u.auth_user_id,
                u.usuario_sistema,
                u.nombres_apellidos,
                u.area,
                u.correo,
                u.celular,
                u.estado,
                u.created_at,
                u.updated_at
            FROM usuarios u
            WHERE u.id = %s AND u.estado = 'activo'
        """, (usuario_id,))
        
        if not usuario:
            return jsonify({'success': False, 'error': 'Usuario no encontrado'}), 404
        
        return jsonify({
            'success': True,
            'data': usuario[0]
        })
        
    except Exception as e:
        print(f"❌ Error en get_usuario: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@config_seguridad_bp.route('/usuarios', methods=['POST'])
def create_usuario():
    """Crear un nuevo usuario con sus asignaciones de empresa y rol"""
    try:
        data = request.get_json()
        
        if not data.get('auth_user_id'):
            return jsonify({'success': False, 'error': 'auth_user_id es requerido'}), 400
        
        if not data.get('usuario_sistema'):
            return jsonify({'success': False, 'error': 'usuario_sistema es requerido'}), 400
        
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            cur.execute("""
                INSERT INTO usuarios (
                    auth_user_id, usuario_sistema, nombres_apellidos,
                    area, correo, celular, estado
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                data.get('auth_user_id'),
                data.get('usuario_sistema'),
                data.get('nombres_apellidos'),
                data.get('area'),
                data.get('correo'),
                data.get('celular'),
                data.get('estado', 'activo')
            ))
            
            usuario_id = cur.fetchone()['id']
            
            empresas_acceso = data.get('empresas_acceso', [])
            for acceso in empresas_acceso:
                if acceso.get('empresa_id') and acceso.get('rol_id'):
                    cur.execute("""
                        INSERT INTO erp_usuario_empresas (
                            auth_user_id, empresa_id, rol_id,
                            es_empresa_principal, estado
                        ) VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (auth_user_id, empresa_id) 
                        DO UPDATE SET rol_id = EXCLUDED.rol_id, estado = EXCLUDED.estado
                    """, (
                        data.get('auth_user_id'),
                        acceso.get('empresa_id'),
                        acceso.get('rol_id'),
                        acceso.get('es_empresa_principal', False),
                        acceso.get('estado', 'activo')
                    ))
            
            return jsonify({
                'success': True,
                'data': {'id': usuario_id},
                'message': 'Usuario creado exitosamente'
            })
            
    except Exception as e:
        print(f"❌ Error en create_usuario: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@config_seguridad_bp.route('/usuarios/<usuario_id>', methods=['PUT'])
def update_usuario(usuario_id):
    """Actualizar un usuario existente"""
    try:
        data = request.get_json()
        
        with db_tx() as conn:
            cur = conn.cursor()
            
            cur.execute("""
                UPDATE usuarios SET
                    usuario_sistema = %s,
                    nombres_apellidos = %s,
                    area = %s,
                    correo = %s,
                    celular = %s,
                    estado = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (
                data.get('usuario_sistema'),
                data.get('nombres_apellidos'),
                data.get('area'),
                data.get('correo'),
                data.get('celular'),
                data.get('estado', 'activo'),
                usuario_id
            ))
            
            return jsonify({
                'success': True,
                'message': 'Usuario actualizado exitosamente'
            })
            
    except Exception as e:
        print(f"❌ Error en update_usuario: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@config_seguridad_bp.route('/usuarios/<usuario_id>', methods=['DELETE'])
def delete_usuario(usuario_id):
    """Eliminar usuario (borrado lógico)"""
    try:
        db_execute("""
            UPDATE usuarios SET estado = 'inactivo', updated_at = NOW()
            WHERE id = %s
        """, (usuario_id,))
        
        return jsonify({
            'success': True,
            'message': 'Usuario desactivado exitosamente'
        })
        
    except Exception as e:
        print(f"❌ Error en delete_usuario: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@config_seguridad_bp.route('/roles', methods=['GET'])
def get_roles():
    """Obtener todos los roles"""
    try:
        roles = db_query("""
            SELECT 
                r.id,
                r.codigo,
                r.nombre,
                r.descripcion,
                r.es_admin,
                r.estado,
                r.created_at,
                r.updated_at
            FROM erp_roles r
            WHERE r.estado = 'activo'
            ORDER BY r.nombre
        """)
        
        if roles:
            return jsonify({
                'success': True,
                'data': roles,
                'total': len(roles)
            })
        else:
            # Si no hay datos, devolver roles por defecto
            return jsonify({
                'success': True,
                'data': [
                    {'codigo': 'GERENCIA_TOTAL', 'nombre': 'Gerencia total', 'es_admin': True},
                    {'codigo': 'OPERATIVO_COMERCIAL_LOGISTICA', 'nombre': 'Operativo comercial/logística', 'es_admin': False},
                    {'codigo': 'LECTURA_TI', 'nombre': 'Practicante TI / lectura', 'es_admin': False}
                ],
                'total': 3,
                'message': 'Usando roles por defecto'
            })
        
    except Exception as e:
        print(f"❌ Error en get_roles: {e}")
        return jsonify({
            'success': True,
            'data': [
                {'codigo': 'GERENCIA_TOTAL', 'nombre': 'Gerencia total', 'es_admin': True},
                {'codigo': 'OPERATIVO_COMERCIAL_LOGISTICA', 'nombre': 'Operativo comercial/logística', 'es_admin': False},
                {'codigo': 'LECTURA_TI', 'nombre': 'Practicante TI / lectura', 'es_admin': False}
            ],
            'total': 3,
            'message': 'Usando roles por defecto'
        }), 200



# ============================================================
# 3. CORRELATIVOS - VERSIÓN CORREGIDA CON UUID
# ============================================================

@config_seguridad_bp.route('/correlativos', methods=['GET'])
def get_correlativos():
    """Obtener todos los correlativos"""
    try:
        correlativos = db_query("""
            SELECT 
                c.id,
                c.empresa_id,
                e.codigo as empresa_codigo,
                e.nombre_comercial as empresa_nombre,
                c.documento,
                c.codigo_documento,
                c.prefijo,
                c.anio,
                c.ultimo_numero,
                c.estado,
                c.created_at,
                c.updated_at
            FROM erp_correlativos c
            JOIN erp_empresas e ON e.id = c.empresa_id
            ORDER BY e.codigo, c.documento
        """)
        
        # Convertir estado a formato legible para el frontend
        for c in correlativos:
            c['estado'] = 'Activo' if c.get('estado') == 'activo' else 'Inactivo'
        
        return jsonify({
            'success': True,
            'data': correlativos,
            'total': len(correlativos)
        })
        
    except Exception as e:
        print(f"❌ Error en get_correlativos: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@config_seguridad_bp.route('/correlativos/<correlativo_id>', methods=['GET'])
def get_correlativo(correlativo_id):
    """Obtener un correlativo específico por ID (UUID)"""
    try:
        correlativo = db_query("""
            SELECT 
                c.id,
                c.empresa_id,
                e.codigo as empresa_codigo,
                e.nombre_comercial as empresa_nombre,
                c.documento,
                c.codigo_documento,
                c.prefijo,
                c.anio,
                c.ultimo_numero,
                c.estado,
                c.created_at,
                c.updated_at
            FROM erp_correlativos c
            JOIN erp_empresas e ON e.id = c.empresa_id
            WHERE c.id = %s
        """, (correlativo_id,))
        
        if not correlativo:
            return jsonify({'success': False, 'error': 'Correlativo no encontrado'}), 404
        
        c = correlativo[0]
        c['estado'] = 'Activo' if c.get('estado') == 'activo' else 'Inactivo'
        
        return jsonify({
            'success': True,
            'data': c
        })
        
    except Exception as e:
        print(f"❌ Error en get_correlativo: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@config_seguridad_bp.route('/correlativos', methods=['POST'])
def create_correlativo():
    """Crear un nuevo correlativo o reactivar uno existente"""
    try:
        data = request.get_json()
        print(f"📝 Creando correlativo - Datos recibidos: {data}")
        
        # Validar campos requeridos
        required = ['empresa_id', 'documento', 'prefijo']
        for field in required:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'Campo {field} es requerido'}), 400
        
        # Verificar que la empresa existe
        empresa = db_query("SELECT id, codigo FROM erp_empresas WHERE id = %s AND estado = 'activo'", (data.get('empresa_id'),))
        if not empresa:
            return jsonify({'success': False, 'error': 'Empresa no encontrada o inactiva'}), 404
        
        anio = data.get('anio', 2026)
        documento = data.get('documento')
        empresa_id = data.get('empresa_id')
        
        # Verificar si ya existe (activo o inactivo)
        existente = db_query("""
            SELECT id, estado, ultimo_numero, prefijo 
            FROM erp_correlativos 
            WHERE empresa_id = %s AND documento = %s AND anio = %s
        """, (empresa_id, documento, anio))
        
        if existente:
            existing = existente[0]
            # Si existe y está inactivo, lo reactivamos con los nuevos datos
            if existing['estado'] == 'inactivo':
                estado_db = 'activo' if data.get('estado') == 'Activo' else 'inactivo'
                db_execute("""
                    UPDATE erp_correlativos SET
                        prefijo = %s,
                        ultimo_numero = %s,
                        estado = %s,
                        updated_at = NOW()
                    WHERE id = %s
                """, (
                    data.get('prefijo'),
                    data.get('ultimo_numero', 0),
                    estado_db,
                    existing['id']
                ))
                
                return jsonify({
                    'success': True,
                    'data': {'id': existing['id']},
                    'message': f'Correlativo "{documento}" reactivado exitosamente'
                })
            else:
                # Ya existe activo
                return jsonify({
                    'success': False, 
                    'error': f'Ya existe un correlativo activo para "{documento}" en el año {anio}'
                }), 400
        
        # Determinar estado
        estado_db = 'activo' if data.get('estado') == 'Activo' else 'inactivo'
        
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            cur.execute("""
                INSERT INTO erp_correlativos (
                    empresa_id, documento, codigo_documento,
                    prefijo, anio, ultimo_numero, estado
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                empresa_id,
                documento,
                data.get('codigo_documento', documento.upper().replace(' ', '')),
                data.get('prefijo'),
                anio,
                data.get('ultimo_numero', 0),
                estado_db
            ))
            
            correlativo_id = cur.fetchone()['id']
            
            return jsonify({
                'success': True,
                'data': {'id': correlativo_id},
                'message': f'Correlativo "{documento}" creado exitosamente'
            })
            
    except Exception as e:
        print(f"❌ Error en create_correlativo: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@config_seguridad_bp.route('/correlativos/<correlativo_id>', methods=['PUT'])
def update_correlativo(correlativo_id):
    """Actualizar un correlativo existente (UUID)"""
    try:
        data = request.get_json()
        print(f"📝 Actualizando correlativo {correlativo_id}: {data}")
        
        # Verificar que el correlativo existe
        existente = db_query("SELECT id, empresa_id, documento FROM erp_correlativos WHERE id = %s", (correlativo_id,))
        if not existente:
            return jsonify({'success': False, 'error': 'Correlativo no encontrado'}), 404
        
        # Verificar duplicados (excepto el actual) - SOLO para registros activos
        empresa_id = data.get('empresa_id') or existente[0]['empresa_id']
        documento = data.get('documento') or existente[0]['documento']
        anio = data.get('anio', 2026)
        
        duplicado = db_query("""
            SELECT id FROM erp_correlativos 
            WHERE empresa_id = %s AND documento = %s AND anio = %s 
            AND id != %s AND estado = 'activo'
        """, (empresa_id, documento, anio, correlativo_id))
        
        if duplicado:
            return jsonify({
                'success': False, 
                'error': f'Ya existe otro correlativo activo para "{documento}" en el año {anio}'
            }), 400
        
        # Determinar estado
        estado_db = 'activo' if data.get('estado') == 'Activo' else 'inactivo'
        
        db_execute("""
            UPDATE erp_correlativos SET
                documento = %s,
                codigo_documento = %s,
                prefijo = %s,
                anio = %s,
                ultimo_numero = %s,
                estado = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (
            data.get('documento'),
            data.get('codigo_documento', data.get('documento', '').upper().replace(' ', '')),
            data.get('prefijo'),
            data.get('anio'),
            data.get('ultimo_numero', 0),
            estado_db,
            correlativo_id
        ))
        
        return jsonify({
            'success': True,
            'message': f'Correlativo "{data.get("documento")}" actualizado exitosamente'
        })
        
    except Exception as e:
        print(f"❌ Error en update_correlativo: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@config_seguridad_bp.route('/correlativos/<correlativo_id>', methods=['DELETE'])
def delete_correlativo(correlativo_id):
    """Eliminar correlativo (borrado lógico) - UUID"""
    try:
        print(f"🗑️ Eliminando correlativo con ID: {correlativo_id}")
        
        # Verificar que existe
        existente = db_query("SELECT id, documento FROM erp_correlativos WHERE id = %s", (correlativo_id,))
        if not existente:
            return jsonify({'success': False, 'error': 'Correlativo no encontrado'}), 404
        
        documento = existente[0]['documento']
        
        db_execute("""
            UPDATE erp_correlativos SET estado = 'inactivo', updated_at = NOW()
            WHERE id = %s
        """, (correlativo_id,))
        
        return jsonify({
            'success': True,
            'message': f'Correlativo "{documento}" desactivado exitosamente'
        })
        
    except Exception as e:
        print(f"❌ Error en delete_correlativo: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@config_seguridad_bp.route('/correlativos/tomar', methods=['POST'])
def tomar_correlativo():
    """Tomar un correlativo (incrementar y devolver el siguiente número)"""
    try:
        data = request.get_json()
        empresa_codigo = data.get('empresa_codigo')
        documento = data.get('documento')
        anio = data.get('anio', 2026)
        
        print(f"📝 Tomando correlativo - empresa: {empresa_codigo}, documento: {documento}, año: {anio}")
        
        if not empresa_codigo or not documento:
            return jsonify({'success': False, 'error': 'empresa_codigo y documento son requeridos'}), 400
        
        # Buscar la empresa
        empresa = db_query("SELECT id, codigo FROM erp_empresas WHERE codigo = %s AND estado = 'activo'", (empresa_codigo,))
        if not empresa:
            return jsonify({'success': False, 'error': f'Empresa "{empresa_codigo}" no encontrada'}), 404
        
        empresa_id = empresa[0]['id']
        
        # Buscar el correlativo (solo activos)
        correlativo = db_query("""
            SELECT id, ultimo_numero, prefijo, documento
            FROM erp_correlativos 
            WHERE empresa_id = %s AND documento = %s AND anio = %s AND estado = 'activo'
        """, (empresa_id, documento, anio))
        
        if not correlativo:
            # Verificar si existe inactivo para reactivar
            inactivo = db_query("""
                SELECT id, prefijo FROM erp_correlativos 
                WHERE empresa_id = %s AND documento = %s AND anio = %s AND estado = 'inactivo'
            """, (empresa_id, documento, anio))
            
            if inactivo:
                # Reactivar y resetear contador
                prefijo = inactivo[0]['prefijo']
                db_execute("""
                    UPDATE erp_correlativos 
                    SET ultimo_numero = 0, estado = 'activo', updated_at = NOW()
                    WHERE id = %s
                """, (inactivo[0]['id'],))
                
                codigo = f"{prefijo}-{anio}-0001"
                return jsonify({
                    'success': True,
                    'data': {'codigo': codigo, 'id': inactivo[0]['id']}
                })
            
            # Crear correlativo por defecto
            prefijo = f"{documento[:3].upper()}-{empresa_codigo}"
            with db_tx() as conn:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                cur.execute("""
                    INSERT INTO erp_correlativos (
                        empresa_id, documento, codigo_documento,
                        prefijo, anio, ultimo_numero, estado
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (empresa_id, documento, documento.upper().replace(' ', ''), prefijo, anio, 0, 'activo'))
                nuevo_id = cur.fetchone()['id']
                
                codigo = f"{prefijo}-{anio}-0001"
                return jsonify({
                    'success': True,
                    'data': {'codigo': codigo, 'id': nuevo_id}
                })
        
        # Incrementar el correlativo
        correlativo_id = correlativo[0]['id']
        nuevo_numero = correlativo[0]['ultimo_numero'] + 1
        prefijo = correlativo[0]['prefijo']
        
        db_execute("""
            UPDATE erp_correlativos 
            SET ultimo_numero = %s, updated_at = NOW()
            WHERE id = %s
        """, (nuevo_numero, correlativo_id))
        
        codigo = f"{prefijo}-{anio}-{str(nuevo_numero).zfill(4)}"
        
        return jsonify({
            'success': True,
            'data': {'codigo': codigo, 'numero': nuevo_numero}
        })
        
    except Exception as e:
        print(f"❌ Error en tomar_correlativo: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# 4. PARÁMETROS GENERALES
# ============================================================

@config_seguridad_bp.route('/parametros', methods=['GET'])
def get_parametros():
    """Obtener todos los parámetros generales"""
    try:
        empresa_id = request.args.get('empresa_id')
        
        query = """
            SELECT 
                id,
                empresa_id,
                grupo,
                codigo,
                nombre,
                valor_bool,
                valor_text,
                valor_num,
                regla,
                es_critico,
                estado,
                created_at,
                updated_at
            FROM erp_parametros
            WHERE estado = 'activo'
        """
        params = []
        
        if empresa_id:
            query += " AND (empresa_id = %s OR empresa_id IS NULL)"
            params.append(empresa_id)
        
        query += " ORDER BY grupo, codigo"
        
        parametros = db_query(query, params if params else None)
        
        return jsonify({
            'success': True,
            'data': parametros,
            'total': len(parametros)
        })
        
    except Exception as e:
        print(f"❌ Error en get_parametros: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@config_seguridad_bp.route('/parametros', methods=['POST'])
def create_parametro():
    """Crear un nuevo parámetro"""
    try:
        data = request.get_json()
        
        if not data.get('codigo') or not data.get('grupo') or not data.get('nombre'):
            return jsonify({'success': False, 'error': 'codigo, grupo y nombre son requeridos'}), 400
        
        db_execute("""
            INSERT INTO erp_parametros (
                empresa_id, grupo, codigo, nombre,
                valor_bool, valor_text, valor_num, regla,
                es_critico, estado
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (empresa_id, codigo) DO UPDATE SET
                valor_bool = EXCLUDED.valor_bool,
                valor_text = EXCLUDED.valor_text,
                valor_num = EXCLUDED.valor_num,
                regla = EXCLUDED.regla,
                es_critico = EXCLUDED.es_critico,
                updated_at = NOW()
        """, (
            data.get('empresa_id'),
            data.get('grupo'),
            data.get('codigo'),
            data.get('nombre'),
            data.get('valor_bool'),
            data.get('valor_text'),
            data.get('valor_num'),
            data.get('regla'),
            data.get('es_critico', False),
            data.get('estado', 'activo')
        ))
        
        return jsonify({
            'success': True,
            'message': 'Parámetro guardado exitosamente'
        })
        
    except Exception as e:
        print(f"❌ Error en create_parametro: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@config_seguridad_bp.route('/parametros/<parametro_id>', methods=['DELETE'])
def delete_parametro(parametro_id):
    """Eliminar parámetro (borrado lógico)"""
    try:
        db_execute("""
            UPDATE erp_parametros SET estado = 'inactivo', updated_at = NOW()
            WHERE id = %s
        """, (parametro_id,))
        
        return jsonify({
            'success': True,
            'message': 'Parámetro desactivado exitosamente'
        })
        
    except Exception as e:
        print(f"❌ Error en delete_parametro: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# 5. MÓDULOS Y SUBMÓDULOS
# ============================================================

@config_seguridad_bp.route('/modulos', methods=['GET'])
def get_modulos():
    """Obtener todos los módulos con sus submódulos"""
    try:
        modulos = db_query("""
            SELECT 
                m.id,
                m.orden,
                m.codigo,
                m.nombre,
                m.descripcion,
                m.estado,
                m.created_at,
                m.updated_at,
                (
                    SELECT json_agg(
                        json_build_object(
                            'id', s.id,
                            'orden', s.orden,
                            'codigo', s.codigo,
                            'nombre', s.nombre,
                            'descripcion', s.descripcion,
                            'estado', s.estado
                        ) ORDER BY s.orden
                    )
                    FROM erp_submodulos s
                    WHERE s.modulo_id = m.id
                    AND s.estado = 'activo'
                ) as submodulos
            FROM erp_modulos m
            WHERE m.estado = 'activo'
            ORDER BY m.orden
        """)
        
        return jsonify({
            'success': True,
            'data': modulos,
            'total': len(modulos)
        })
        
    except Exception as e:
        print(f"❌ Error en get_modulos: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# 6. PERMISOS DE USUARIO POR EMPRESA Y SUBMÓDULOS
# ============================================================

@config_seguridad_bp.route('/submodulos', methods=['GET'])
def get_submodulos():
    """Obtener todos los submódulos"""
    try:
        submodulos = db_query("""
            SELECT 
                s.id,
                s.codigo,
                s.nombre,
                s.descripcion,
                m.codigo as modulo_codigo,
                m.nombre as modulo_nombre,
                m.orden as modulo_orden
            FROM erp_submodulos s
            JOIN erp_modulos m ON m.id = s.modulo_id
            WHERE s.estado = 'activo' AND m.estado = 'activo'
            ORDER BY m.orden, s.orden
        """)
        
        return jsonify({
            'success': True,
            'data': submodulos
        })
        
    except Exception as e:
        print(f"❌ Error en get_submodulos: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# PERMISOS DE USUARIO - VERSIÓN CORREGIDA (ACEPTA NÚMEROS)
# ============================================================

@config_seguridad_bp.route('/usuarios/<usuario_id>/permisos', methods=['GET'])
def get_usuario_permisos(usuario_id):
    """Obtener los permisos de un usuario en una empresa específica"""
    try:
        empresa_id = request.args.get('empresa_id')
        
        if not empresa_id:
            return jsonify({'success': False, 'error': 'empresa_id es requerido'}), 400
        
        usuario = db_query("""
            SELECT auth_user_id FROM usuarios WHERE id = %s
        """, (usuario_id,))
        
        if not usuario:
            return jsonify({'success': False, 'error': 'Usuario no encontrado'}), 404
        
        auth_user_id = usuario[0]['auth_user_id']
        
        permisos = db_query("""
            SELECT 
                up.id,
                up.auth_user_id,
                up.empresa_id,
                up.submodulo_id,
                s.codigo as submodulo_codigo,
                s.nombre as submodulo_nombre,
                m.codigo as modulo_codigo,
                m.nombre as modulo_nombre,
                up.puede_ver,
                up.puede_crear,
                up.puede_editar,
                up.puede_aprobar,
                up.puede_anular,
                up.puede_eliminar,
                up.puede_exportar,
                up.puede_subir_evidencia,
                up.observacion,
                up.created_at,
                up.updated_at
            FROM erp_usuario_permisos up
            JOIN erp_submodulos s ON s.id = up.submodulo_id
            JOIN erp_modulos m ON m.id = s.modulo_id
            WHERE up.auth_user_id = %s
            AND up.empresa_id = %s
            ORDER BY m.orden, s.orden
        """, (auth_user_id, empresa_id))
        
        # ✅ Devolver el submodulo_id como número (para que coincida con el frontend)
        for p in permisos:
            if p.get('submodulo_id'):
                # Intentar obtener el ID numérico
                try:
                    # Buscar el submódulo por UUID
                    sub = db_query("SELECT id FROM erp_submodulos WHERE id = %s", (p['submodulo_id'],))
                    if sub:
                        # Ya es el ID, lo dejamos igual
                        pass
                except:
                    pass
        
        submodulos = db_query("""
            SELECT 
                s.id,
                s.codigo,
                s.nombre,
                m.codigo as modulo_codigo,
                m.nombre as modulo_nombre
            FROM erp_submodulos s
            JOIN erp_modulos m ON m.id = s.modulo_id
            WHERE s.estado = 'activo'
            ORDER BY m.orden, s.orden
        """)
        
        return jsonify({
            'success': True,
            'data': {
                'permisos': permisos,
                'submodulos': submodulos
            }
        })
        
    except Exception as e:
        print(f"❌ Error en get_usuario_permisos: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# PERMISOS DE USUARIO - VERSIÓN ÚNICA Y CORREGIDA
# ============================================================

@config_seguridad_bp.route('/usuarios/<usuario_id>/permisos', methods=['GET'])
def obtener_permisos_usuario(usuario_id):
    """Obtener los permisos de un usuario en una empresa específica"""
    try:
        empresa_id = request.args.get('empresa_id')
        
        if not empresa_id:
            return jsonify({'success': False, 'error': 'empresa_id es requerido'}), 400
        
        usuario = db_query("""
            SELECT auth_user_id FROM usuarios WHERE id = %s
        """, (usuario_id,))
        
        if not usuario:
            return jsonify({'success': False, 'error': 'Usuario no encontrado'}), 404
        
        auth_user_id = usuario[0]['auth_user_id']
        
        permisos = db_query("""
            SELECT 
                up.id,
                up.auth_user_id,
                up.empresa_id,
                up.submodulo_id,
                s.codigo as submodulo_codigo,
                s.nombre as submodulo_nombre,
                m.codigo as modulo_codigo,
                m.nombre as modulo_nombre,
                up.puede_ver,
                up.puede_crear,
                up.puede_editar,
                up.puede_aprobar,
                up.puede_anular,
                up.puede_eliminar,
                up.puede_exportar,
                up.puede_subir_evidencia,
                up.observacion,
                up.created_at,
                up.updated_at
            FROM erp_usuario_permisos up
            JOIN erp_submodulos s ON s.id = up.submodulo_id
            JOIN erp_modulos m ON m.id = s.modulo_id
            WHERE up.auth_user_id = %s
            AND up.empresa_id = %s
            ORDER BY m.orden, s.orden
        """, (auth_user_id, empresa_id))
        
        submodulos = db_query("""
            SELECT 
                s.id,
                s.codigo,
                s.nombre,
                m.codigo as modulo_codigo,
                m.nombre as modulo_nombre
            FROM erp_submodulos s
            JOIN erp_modulos m ON m.id = s.modulo_id
            WHERE s.estado = 'activo'
            ORDER BY m.orden, s.orden
        """)
        
        return jsonify({
            'success': True,
            'data': {
                'permisos': permisos,
                'submodulos': submodulos
            }
        })
        
    except Exception as e:
        print(f"❌ Error en obtener_permisos_usuario: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500



@config_seguridad_bp.route('/usuarios/<usuario_id>/permisos', methods=['POST'])
def actualizar_permisos_usuario(usuario_id):
    """Actualizar los permisos de un usuario en una empresa"""
    try:
        data = request.get_json()
        print(f"📝 Datos recibidos en POST: {data}")
        
        empresa_id = data.get('empresa_id')
        permisos = data.get('permisos', [])
        
        if not empresa_id:
            return jsonify({'success': False, 'error': 'empresa_id es requerido'}), 400
        
        usuario = db_query("""
            SELECT auth_user_id FROM usuarios WHERE id = %s AND estado = 'activo'
        """, (usuario_id,))
        
        if not usuario:
            return jsonify({'success': False, 'error': 'Usuario no encontrado'}), 404
        
        auth_user_id = usuario[0]['auth_user_id']
        
        # Mapeo de IDs numéricos a códigos (según el frontend)
        codigos_por_id = {
            '1': 'EMPRESAS', '2': 'USUARIOS_PERMISOS', '3': 'CORRELATIVOS',
            '4': 'PARAMETROS', '5': 'INTEGRACION', '6': 'CLIENTES',
            '7': 'PROVEEDORES', '8': 'ALMACENES', '9': 'CATEGORIAS',
            '10': 'MARCAS', '11': 'UNIDADES_MEDIDA', '12': 'PRODUCTOS_LISTADO',
            '13': 'PRODUCTOS_FICHA', '14': 'COTIZACIONES', '15': 'COMPROBANTES_CLIENTE',
            '16': 'GUIAS_CLIENTE', '17': 'NOTAS_CREDITO', '18': 'SOLICITUD_COMPRA',
            '19': 'COMPARATIVO_PROVEEDORES', '20': 'ORDEN_COMPRA', '21': 'COMPROBANTES_PROVEEDOR',
            '22': 'RECEPCION_MERCADERIA', '23': 'ESTADO_STOCK', '24': 'KARDEX',
            '25': 'ENTRADAS_SALIDAS', '26': 'TRANSFERENCIAS', '27': 'CUENTAS_COBRAR',
            '28': 'CUENTAS_PAGAR', '29': 'CAJA_BANCOS', '30': 'FLUJO_CAJA',
            '31': 'REPORTE_VENTAS', '32': 'REPORTE_COMPRAS', '33': 'REPORTE_INVENTARIO',
            '34': 'REPORTE_FINANZAS', '35': 'SUNAT'
        }
        
        with db_tx() as conn:
            cur = conn.cursor()
            
            # Eliminar permisos existentes
            cur.execute("""
                DELETE FROM erp_usuario_permisos 
                WHERE auth_user_id = %s AND empresa_id = %s
            """, (auth_user_id, empresa_id))
            
            # Insertar nuevos permisos
            for idx, permiso in enumerate(permisos):
                submodulo_id = permiso.get('submodulo_id')
                if not submodulo_id:
                    continue
                
                # Si es un número, buscar por código
                if isinstance(submodulo_id, int) or (isinstance(submodulo_id, str) and submodulo_id.isdigit()):
                    codigo = codigos_por_id.get(str(submodulo_id))
                    if codigo:
                        # Buscar el UUID por el código
                        uuid_result = db_query(
                            "SELECT id FROM erp_submodulos WHERE codigo = %s", 
                            (codigo,)
                        )
                        if uuid_result:
                            submodulo_id = uuid_result[0]['id']
                            print(f"   ✅ Convertido a UUID: {submodulo_id}")
                        else:
                            print(f"   ❌ No se encontró submódulo con código: {codigo}")
                            continue
                    else:
                        print(f"   ❌ No se encontró código para ID: {submodulo_id}")
                        continue
                
                # Si es un string que parece UUID, verificar que existe
                elif isinstance(submodulo_id, str) and '-' in submodulo_id:
                    uuid_result = db_query(
                        "SELECT id FROM erp_submodulos WHERE id = %s::uuid", 
                        (submodulo_id,)
                    )
                    if not uuid_result:
                        print(f"   ❌ No se encontró submódulo con UUID: {submodulo_id}")
                        continue
                
                # Insertar el permiso
                cur.execute("""
                    INSERT INTO erp_usuario_permisos (
                        auth_user_id, empresa_id, submodulo_id,
                        puede_ver, puede_crear, puede_editar,
                        puede_aprobar, puede_anular, puede_eliminar,
                        puede_exportar, puede_subir_evidencia,
                        observacion
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    auth_user_id,
                    empresa_id,
                    submodulo_id,
                    permiso.get('puede_ver', False),
                    permiso.get('puede_crear', False),
                    permiso.get('puede_editar', False),
                    permiso.get('puede_aprobar', False),
                    permiso.get('puede_anular', False),
                    permiso.get('puede_eliminar', False),
                    permiso.get('puede_exportar', False),
                    permiso.get('puede_subir_evidencia', False),
                    permiso.get('observacion', '')
                ))
        
        return jsonify({
            'success': True,
            'message': 'Permisos actualizados exitosamente'
        })
        
    except Exception as e:
        print(f"❌ Error en actualizar_permisos_usuario: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# 7. AUDITORÍA
# ============================================================

@config_seguridad_bp.route('/auditoria', methods=['GET'])
def get_auditoria():
    """Obtener registros de auditoría"""
    try:
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        empresa_id = request.args.get('empresa_id')
        tabla = request.args.get('tabla')
        accion = request.args.get('accion')
        
        query = """
            SELECT 
                a.id,
                a.empresa_id,
                e.codigo as empresa_codigo,
                a.auth_user_id,
                u.usuario_sistema,
                u.nombres_apellidos,
                a.tabla,
                a.registro_id,
                a.accion,
                a.data_anterior,
                a.data_nueva,
                a.created_at
            FROM erp_auditoria a
            LEFT JOIN erp_empresas e ON e.id = a.empresa_id
            LEFT JOIN usuarios u ON u.auth_user_id = a.auth_user_id
            WHERE 1=1
        """
        params = []
        
        if empresa_id:
            query += " AND a.empresa_id = %s"
            params.append(empresa_id)
        
        if tabla:
            query += " AND a.tabla = %s"
            params.append(tabla)
        
        if accion:
            query += " AND a.accion = %s"
            params.append(accion)
        
        query += " ORDER BY a.created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        auditoria = db_query(query, params)
        
        return jsonify({
            'success': True,
            'data': auditoria,
            'total': len(auditoria),
            'limit': limit,
            'offset': offset
        })
        
    except Exception as e:
        print(f"❌ Error en get_auditoria: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def registrar_auditoria(empresa_id, auth_user_id, tabla, registro_id, accion, data_anterior=None, data_nueva=None):
    """Función auxiliar para registrar auditoría"""
    try:
        db_execute("""
            INSERT INTO erp_auditoria (
                empresa_id, auth_user_id, tabla, registro_id,
                accion, data_anterior, data_nueva
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            empresa_id,
            auth_user_id,
            tabla,
            registro_id,
            accion,
            json.dumps(data_anterior) if data_anterior else None,
            json.dumps(data_nueva) if data_nueva else None
        ))
    except Exception as e:
        print(f"❌ Error en registrar_auditoria: {e}")
        # No lanzar excepción para no interrumpir la operación principal


# ============================================================
# 8. INFORMACIÓN DE LA SESIÓN (para el frontend)
# ============================================================

@config_seguridad_bp.route('/session', methods=['GET'])
def get_session_info():
    """Obtener información de la sesión actual"""
    try:
        user_id = session.get('user_id') or session.get('usuario_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'No autenticado'}), 401
        
        usuario = db_query("""
            SELECT 
                u.id,
                u.auth_user_id,
                u.usuario_sistema,
                u.nombres_apellidos,
                u.area,
                u.correo,
                (
                    SELECT json_agg(
                        json_build_object(
                            'empresa_id', ue.empresa_id,
                            'empresa_codigo', e.codigo,
                            'empresa_nombre', e.nombre_comercial,
                            'rol_id', ue.rol_id,
                            'rol_codigo', r.codigo,
                            'rol_nombre', r.nombre,
                            'es_admin', r.es_admin,
                            'es_principal', ue.es_empresa_principal
                        )
                    )
                    FROM erp_usuario_empresas ue
                    LEFT JOIN erp_empresas e ON e.id = ue.empresa_id
                    LEFT JOIN erp_roles r ON r.id = ue.rol_id
                    WHERE ue.auth_user_id = u.auth_user_id
                    AND ue.estado = 'activo'
                ) as empresas_acceso
            FROM usuarios u
            WHERE u.id = %s AND u.estado = 'activo'
        """, (user_id,))
        
        if not usuario:
            return jsonify({'success': False, 'error': 'Usuario no encontrado'}), 404
        
        return jsonify({
            'success': True,
            'data': usuario[0]
        })
        
    except Exception as e:
        print(f"❌ Error en get_session_info: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500