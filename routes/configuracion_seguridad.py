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
from utils import columnas_usuario_antiguas

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
            
            usuario_id = _insertar_usuario(cur, data)
            
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
# PERMISOS DE USUARIO (una sola versión)
# ============================================================
# Reglas (se explican también en la pantalla "Usuarios y permisos"):
#   1. Rol GERENCIA_TOTAL (o un rol ERP marcado es_admin) en la empresa  -> ve todo.
#   2. Permiso individual (erp_usuario_permisos) del submódulo           -> manda ese (aunque sea "no").
#   3. Si no tiene permiso individual, se usa el del rol (erp_rol_permisos).
#   4. Sin ninguno de los anteriores: el submódulo queda sin permiso explícito
#      (el menú usa sus valores por defecto: los módulos operativos se ven).
# La base de datos es la única fuente: la pantalla ya no guarda permisos en el navegador.

FLAGS_PERMISO = ('puede_ver', 'puede_crear', 'puede_editar', 'puede_aprobar',
                 'puede_anular', 'puede_eliminar', 'puede_exportar', 'puede_subir_evidencia')

# IDs numéricos que usaba la pantalla antigua (submodulosData en base.html) -> código del submódulo
CODIGOS_POR_ID_ANTIGUO = {
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
    '34': 'REPORTE_FINANZAS', '35': 'SUNAT',
    '36': 'CONCILIACION_BANCARIA', '37': 'INTERCOMPANY', '38': 'PLANILLA', '39': 'SEGUIMIENTO_COMERCIAL'
}

_cache_upsert = {}


def _existe_tabla(nombre):
    try:
        r = db_query("SELECT to_regclass(%s) IS NOT NULL AS existe", (nombre,))
        return bool(r and r[0]['existe'])
    except Exception:
        return False


def _tiene_unique_permisos():
    """True si erp_usuario_permisos tiene UNIQUE(auth_user_id, empresa_id, submodulo_id) (Supabase sí la tiene)."""
    if 'unique' not in _cache_upsert:
        try:
            r = db_query("""
                SELECT 1 FROM pg_index i
                JOIN pg_class c ON c.oid = i.indrelid
                WHERE c.relname = 'erp_usuario_permisos' AND i.indisunique
                  AND (SELECT array_agg(a.attname::text ORDER BY a.attname::text) FROM pg_attribute a
                       WHERE a.attrelid = c.oid AND a.attnum = ANY(i.indkey))
                      = ARRAY['auth_user_id', 'empresa_id', 'submodulo_id']
                LIMIT 1
            """)
            _cache_upsert['unique'] = bool(r)
        except Exception:
            _cache_upsert['unique'] = False
    return _cache_upsert['unique']


def _usuario_por_id(usuario_id):
    try:
        uid = int(str(usuario_id))
    except (TypeError, ValueError):
        return None
    filas = db_query("SELECT id, auth_user_id, usuario_sistema, estado FROM usuarios WHERE id = %s", (uid,))
    return filas[0] if filas else None


def _empresas_del_usuario(auth_user_id):
    """Empresas a las que el usuario tiene acceso (erp_usuario_empresas activo) con su rol ERP."""
    if not auth_user_id:
        return []
    return db_query("""
        SELECT ue.empresa_id::text AS empresa_id, e.codigo AS empresa_codigo,
               ue.rol_id::text AS rol_id, r.codigo AS rol_codigo, COALESCE(r.es_admin, false) AS rol_es_admin
        FROM erp_usuario_empresas ue
        LEFT JOIN erp_empresas e ON e.id = ue.empresa_id
        LEFT JOIN erp_roles r ON r.id = ue.rol_id
        WHERE ue.auth_user_id::text = %s AND COALESCE(ue.estado, 'activo') = 'activo'
        ORDER BY ue.es_empresa_principal DESC NULLS LAST, e.codigo
    """, (str(auth_user_id),))


def _resolver_empresas(auth_user_id, empresa_id=None, empresa_codigo=None):
    """Devuelve la lista de ids de empresa (texto) a consultar.
    empresa_codigo = 'TODAS' (o vacío y sin empresa_id) -> todas las empresas del usuario."""
    if empresa_id and str(empresa_id).upper() != 'TODAS':
        return [str(empresa_id)]
    codigo = (empresa_codigo or '').strip().upper()
    if codigo and codigo != 'TODAS':
        e = db_query("SELECT id::text AS id FROM erp_empresas WHERE UPPER(codigo) = %s", (codigo,))
        return [e[0]['id']] if e else []
    return [e['empresa_id'] for e in _empresas_del_usuario(auth_user_id) if e['empresa_id']]


def _submodulos_activos():
    return db_query("""
        SELECT s.id::text AS id, s.codigo, s.nombre, m.codigo AS modulo_codigo, m.nombre AS modulo_nombre
        FROM erp_submodulos s
        JOIN erp_modulos m ON m.id = s.modulo_id
        WHERE COALESCE(s.estado, 'activo') = 'activo'
        ORDER BY m.orden, s.orden
    """)


def _permisos_efectivos(auth_user_id, empresa_ids):
    """Calcula los permisos que realmente aplican por código de submódulo (ver reglas arriba).
    Con varias empresas (modo TODAS) se suman: basta con tenerlo en una."""
    submodulos = _submodulos_activos()
    codigo_por_id = {s['id']: s['codigo'] for s in submodulos}
    accesos = [e for e in _empresas_del_usuario(auth_user_id) if e['empresa_id'] in set(empresa_ids)]
    individuales = []
    if auth_user_id and empresa_ids:
        individuales = db_query("""
            SELECT empresa_id::text AS empresa_id, submodulo_id::text AS submodulo_id,
                   puede_ver, puede_crear, puede_editar, puede_aprobar, puede_anular,
                   puede_eliminar, puede_exportar, puede_subir_evidencia
            FROM erp_usuario_permisos
            WHERE auth_user_id::text = %s AND empresa_id::text = ANY(%s)
        """, (str(auth_user_id), list(empresa_ids)))
    por_rol = {}
    rol_ids = sorted({a['rol_id'] for a in accesos if a['rol_id']})
    if rol_ids and _existe_tabla('erp_rol_permisos'):
        for f in db_query("""
            SELECT rol_id::text AS rol_id, submodulo_id::text AS submodulo_id,
                   puede_ver, puede_crear, puede_editar, puede_aprobar, puede_anular,
                   puede_eliminar, puede_exportar, puede_subir_evidencia
            FROM erp_rol_permisos WHERE rol_id::text = ANY(%s)
        """, (rol_ids,)):
            por_rol.setdefault(f['rol_id'], {})[f['submodulo_id']] = f

    efectivos = {}

    def sumar(codigo, fila, origen):
        if not codigo:
            return
        actual = efectivos.setdefault(codigo, dict({k: False for k in FLAGS_PERMISO}, origen=origen))
        for k in FLAGS_PERMISO:
            if fila.get(k):
                actual[k] = True
        if fila.get('puede_ver') and actual['origen'] != 'gerencia':
            actual['origen'] = origen

    gerencia = False
    for emp in empresa_ids:
        acceso = next((a for a in accesos if a['empresa_id'] == emp), None)
        if acceso and (acceso['rol_codigo'] == 'GERENCIA_TOTAL' or acceso['rol_es_admin']):
            gerencia = True
            for s in submodulos:
                sumar(s['codigo'], {k: True for k in FLAGS_PERMISO}, 'gerencia')
            continue
        propios = {f['submodulo_id']: f for f in individuales if f['empresa_id'] == emp}
        del_rol = por_rol.get(acceso['rol_id'], {}) if acceso else {}
        for sid in set(propios) | set(del_rol):
            if sid in propios:
                sumar(codigo_por_id.get(sid), propios[sid], 'usuario')
            else:
                sumar(codigo_por_id.get(sid), del_rol[sid], 'rol')
    return efectivos, gerencia, accesos, submodulos


@config_seguridad_bp.route('/usuarios/<usuario_id>/permisos', methods=['GET'])
def obtener_permisos_usuario(usuario_id):
    """Permisos de un usuario en una empresa (empresa_id o empresa_codigo; 'TODAS' = suma de sus empresas).
    Devuelve:
      permisos   -> filas individuales (erp_usuario_permisos), con submodulo_codigo
      efectivos  -> {codigo: {puede_ver, ..., origen: usuario|rol|gerencia}} = lo que realmente aplica
      es_gerencia_total, empresas (accesos del usuario), submodulos"""
    try:
        empresa_id = request.args.get('empresa_id')
        empresa_codigo = request.args.get('empresa_codigo')
        if not empresa_id and not empresa_codigo:
            return jsonify({'success': False, 'error': 'Falta la empresa (empresa_id o empresa_codigo).'}), 400

        usuario = _usuario_por_id(usuario_id)
        if not usuario:
            return jsonify({'success': False, 'error': 'Usuario no encontrado'}), 404
        auth_user_id = usuario['auth_user_id']
        empresa_ids = _resolver_empresas(auth_user_id, empresa_id, empresa_codigo)

        permisos = []
        if auth_user_id and empresa_ids:
            permisos = db_query("""
                SELECT up.id, up.auth_user_id, up.empresa_id, up.submodulo_id,
                       s.codigo AS submodulo_codigo, s.nombre AS submodulo_nombre,
                       m.codigo AS modulo_codigo, m.nombre AS modulo_nombre,
                       up.puede_ver, up.puede_crear, up.puede_editar, up.puede_aprobar,
                       up.puede_anular, up.puede_eliminar, up.puede_exportar,
                       up.puede_subir_evidencia, up.observacion, up.created_at
                FROM erp_usuario_permisos up
                JOIN erp_submodulos s ON s.id = up.submodulo_id
                JOIN erp_modulos m ON m.id = s.modulo_id
                WHERE up.auth_user_id::text = %s AND up.empresa_id::text = ANY(%s)
                ORDER BY m.orden, s.orden
            """, (str(auth_user_id), empresa_ids))

        efectivos, gerencia, accesos, submodulos = _permisos_efectivos(auth_user_id, empresa_ids)
        return jsonify({
            'success': True,
            'data': {
                'permisos': permisos,
                'efectivos': efectivos,
                'es_gerencia_total': gerencia,
                'empresa_ids': empresa_ids,
                'empresas': accesos,
                'submodulos': submodulos,
                'sin_cuenta_auth': not auth_user_id,
            }
        })
    except Exception as e:
        print(f"❌ Error en obtener_permisos_usuario: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def _resolver_submodulo(permiso, submodulos):
    """Acepta submodulo_codigo (preferido), el id real (UUID) o el id numérico antiguo de la pantalla."""
    por_codigo = {s['codigo'].upper(): s['id'] for s in submodulos if s.get('codigo')}
    por_id = {s['id']: s['id'] for s in submodulos}
    codigo = (permiso.get('submodulo_codigo') or '').strip().upper()
    if codigo:
        return por_codigo.get(codigo)
    sid = permiso.get('submodulo_id')
    if sid is None or sid == '':
        return None
    sid = str(sid).strip()
    if sid.isdigit() and CODIGOS_POR_ID_ANTIGUO.get(sid) in por_codigo:
        return por_codigo[CODIGOS_POR_ID_ANTIGUO[sid]]
    return por_id.get(sid)


@config_seguridad_bp.route('/usuarios/<usuario_id>/permisos', methods=['POST'])
def actualizar_permisos_usuario(usuario_id):
    """Guarda permisos de un usuario en UNA empresa.
    Por defecto solo toca los submódulos enviados (los demás se quedan como estaban).
    Cada permiso puede traer solo algunas banderas (p. ej. solo puede_ver): las que no vienen no cambian.
    Para reemplazar todo (borrar lo que no se envía) mandar "reemplazar_todo": true."""
    try:
        data = request.get_json(silent=True) or {}
        permisos = data.get('permisos') or []
        if not isinstance(permisos, list):
            return jsonify({'success': False, 'error': 'permisos debe ser una lista'}), 400

        usuario = _usuario_por_id(usuario_id)
        if not usuario:
            return jsonify({'success': False, 'error': 'Usuario no encontrado'}), 404
        auth_user_id = usuario['auth_user_id']
        if not auth_user_id:
            return jsonify({'success': False, 'error': 'Este usuario no tiene cuenta de acceso (auth_user_id) '
                                                       'y no se le pueden asignar permisos.'}), 400

        empresa_codigo = (data.get('empresa_codigo') or '').strip().upper()
        if (str(data.get('empresa_id') or '').upper() == 'TODAS') or (empresa_codigo == 'TODAS' and not data.get('empresa_id')):
            return jsonify({'success': False, 'error': 'Elige una empresa (KCF o AGD) para guardar permisos.'}), 400
        empresa_ids = _resolver_empresas(auth_user_id, data.get('empresa_id'), empresa_codigo)
        if len(empresa_ids) != 1:
            return jsonify({'success': False, 'error': 'Falta la empresa o no existe.'}), 400
        empresa_id = empresa_ids[0]

        submodulos = _submodulos_activos()
        filas, no_encontrados = [], []
        for p in permisos:
            if not isinstance(p, dict):
                continue
            sid = _resolver_submodulo(p, submodulos)
            if not sid:
                no_encontrados.append(str(p.get('submodulo_codigo') or p.get('submodulo_id')))
                continue
            banderas = {k: bool(p[k]) for k in FLAGS_PERMISO if k in p and p[k] is not None}
            filas.append((sid, banderas, p.get('observacion')))
        if no_encontrados:
            return jsonify({'success': False,
                            'error': 'No existe el submódulo: ' + ', '.join(no_encontrados) + '. No se guardó nada.'}), 400
        reemplazar = bool(data.get('reemplazar_todo'))
        if not filas and not reemplazar:
            return jsonify({'success': False, 'error': 'No se envió ningún permiso para guardar.'}), 400

        usar_on_conflict = _tiene_unique_permisos()
        with db_tx() as conn:
            cur = conn.cursor()
            if reemplazar:
                cur.execute("""
                    DELETE FROM erp_usuario_permisos
                    WHERE auth_user_id::text = %s AND empresa_id::text = %s
                """, (str(auth_user_id), empresa_id))
            for sid, banderas, observacion in filas:
                valores_insert = [banderas.get(k, False) for k in FLAGS_PERMISO]
                actualizar = list(banderas.keys())
                if observacion is not None:
                    actualizar_obs = True
                else:
                    actualizar_obs = False
                if usar_on_conflict:
                    sets = [f"{k} = EXCLUDED.{k}" for k in actualizar]
                    if actualizar_obs:
                        sets.append("observacion = EXCLUDED.observacion")
                    sets.append("updated_at = NOW()")
                    cur.execute(f"""
                        INSERT INTO erp_usuario_permisos (auth_user_id, empresa_id, submodulo_id,
                            {', '.join(FLAGS_PERMISO)}, observacion)
                        VALUES (%s, %s, %s, {', '.join(['%s'] * len(FLAGS_PERMISO))}, %s)
                        ON CONFLICT (auth_user_id, empresa_id, submodulo_id)
                        DO UPDATE SET {', '.join(sets)}
                    """, [auth_user_id, empresa_id, sid] + valores_insert + [observacion or ''])
                else:
                    # Esquema sin la restricción UNIQUE: actualizar y, si no existía, insertar.
                    sets = [f"{k} = %s" for k in actualizar] + (["observacion = %s"] if actualizar_obs else [])
                    filas_afectadas = 0
                    if sets:
                        cur.execute(f"""
                            UPDATE erp_usuario_permisos SET {', '.join(sets)}
                            WHERE auth_user_id::text = %s AND empresa_id::text = %s AND submodulo_id::text = %s
                        """, [banderas[k] for k in actualizar] + ([observacion] if actualizar_obs else [])
                            + [str(auth_user_id), empresa_id, sid])
                        filas_afectadas = cur.rowcount
                    else:
                        cur.execute("""
                            SELECT 1 FROM erp_usuario_permisos
                            WHERE auth_user_id::text = %s AND empresa_id::text = %s AND submodulo_id::text = %s
                        """, (str(auth_user_id), empresa_id, sid))
                        filas_afectadas = cur.rowcount
                    if not filas_afectadas:
                        cur.execute(f"""
                            INSERT INTO erp_usuario_permisos (auth_user_id, empresa_id, submodulo_id,
                                {', '.join(FLAGS_PERMISO)}, observacion)
                            VALUES (%s, %s, %s, {', '.join(['%s'] * len(FLAGS_PERMISO))}, %s)
                        """, [auth_user_id, empresa_id, sid] + valores_insert + [observacion or ''])

        efectivos, gerencia, _, _ = _permisos_efectivos(auth_user_id, [empresa_id])
        return jsonify({
            'success': True,
            'message': f'Permisos guardados ({len(filas)} submódulo(s)).',
            'data': {'efectivos': efectivos, 'es_gerencia_total': gerencia, 'empresa_id': empresa_id}
        })
    except Exception as e:
        print(f"❌ Error en actualizar_permisos_usuario: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# CUENTAS DE ACCESO (Supabase Auth) SIN USUARIO DEL ERP
# ============================================================
# Cada usuario del ERP (tabla usuarios) se enlaza con su cuenta de Supabase Auth por usuarios.auth_user_id.
# Aquí se listan las cuentas de auth.users que todavía no tienen usuario del ERP, y se crea el usuario
# enlazado (inactivo hasta que un administrador lo active).

def _solo_admin():
    from utils import es_admin
    if 'usuario_id' not in session or not es_admin():
        return jsonify({'success': False, 'error': 'Solo un administrador puede hacer esto.'}), 403
    return None


def _es_uuid(valor):
    import re
    return bool(re.match(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$', str(valor or '')))


def _password_temporal(largo=14):
    """Contraseña temporal aleatoria: letras mayúsculas y minúsculas, números y un símbolo."""
    import secrets
    import string
    largo = max(12, largo)
    simbolos = '#$%&*+-=?@'
    alfabeto = string.ascii_letters + string.digits
    while True:
        base = [secrets.choice(alfabeto) for _ in range(largo - 1)] + [secrets.choice(simbolos)]
        secrets.SystemRandom().shuffle(base)
        clave = ''.join(base)
        if (any(c.islower() for c in clave) and any(c.isupper() for c in clave)
                and any(c.isdigit() for c in clave)):
            return clave


def _password_aceptable(clave):
    return isinstance(clave, str) and len(clave) >= 8 and any(c.isalpha() for c in clave) and any(c.isdigit() for c in clave)


_SQL_AUTH_SIN_VINCULAR = """
    SELECT u.id::text AS id, u.email,
           to_jsonb(u)->>'created_at' AS created_at,
           to_jsonb(u)->>'last_sign_in_at' AS last_sign_in_at
    FROM auth.users u
    WHERE NOT EXISTS (SELECT 1 FROM usuarios x WHERE x.auth_user_id::text = u.id::text)
      AND (to_jsonb(u)->>'deleted_at') IS NULL
"""


@config_seguridad_bp.route('/auth-sin-vincular', methods=['GET'])
def listar_auth_sin_vincular():
    """Cuentas de Supabase Auth (auth.users) que ningún usuario del ERP tiene enlazadas."""
    error = _solo_admin()
    if error:
        return error
    if not _existe_tabla('auth.users'):
        return jsonify({'success': True, 'data': [], 'total': 0,
                        'aviso': 'Esta base de datos no tiene la tabla auth.users (Supabase Auth).'})
    try:
        filas = db_query(_SQL_AUTH_SIN_VINCULAR + " ORDER BY created_at DESC NULLS LAST, u.email")
        return jsonify({'success': True, 'data': filas, 'total': len(filas)})
    except Exception as e:
        print(f"❌ Error en listar_auth_sin_vincular: {e}")
        if 'permission denied' in str(e).lower():
            return jsonify({'success': False, 'error': 'La base de datos no deja leer auth.users con este usuario '
                                                       'de conexión. Pide a TI que dé permiso de lectura.'}), 500
        return jsonify({'success': False, 'error': str(e)}), 500


def _insertar_usuario(cur, data):
    """INSERT en usuarios (columnas nuevas + antiguas obligatorias). Devuelve el id.
    La contraseña se guarda con hash (columnas_usuario_antiguas usa generate_password_hash)."""
    cur.execute("""
        INSERT INTO usuarios (
            auth_user_id, usuario_sistema, nombres_apellidos,
            area, correo, celular, estado,
            usuario, nombre_completo, password, rol
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        data.get('auth_user_id'),
        data.get('usuario_sistema'),
        data.get('nombres_apellidos'),
        data.get('area'),
        data.get('correo'),
        data.get('celular'),
        data.get('estado', 'activo')
    ) + columnas_usuario_antiguas(data))
    fila = cur.fetchone()
    return fila['id'] if isinstance(fila, dict) else fila[0]


@config_seguridad_bp.route('/auth-sin-vincular/<auth_id>/crear', methods=['POST'])
def crear_usuario_desde_auth(auth_id):
    """Crea un usuario del ERP enlazado a una cuenta de auth.users.
    Body: usuario_sistema (obligatorio), nombres_apellidos, area, rol (por defecto 'vendedor'),
          password (mín. 8, letras y números) o generar_password: true,
          empresas: ['KCF', 'AGD'] y rol_erp (código de erp_roles) para darle acceso a empresas.
    El usuario queda INACTIVO hasta que un administrador lo active."""
    error = _solo_admin()
    if error:
        return error
    try:
        if not _es_uuid(auth_id):
            return jsonify({'success': False, 'error': 'El ID de la cuenta no es válido.'}), 400
        if not _existe_tabla('auth.users'):
            return jsonify({'success': False, 'error': 'Esta base de datos no tiene auth.users.'}), 400
        data = request.get_json(silent=True) or {}
        cuenta = db_query(_SQL_AUTH_SIN_VINCULAR + " AND u.id::text = %s", (auth_id.lower(),))
        if not cuenta:
            ya = db_query("SELECT usuario_sistema FROM usuarios WHERE auth_user_id::text = %s", (auth_id.lower(),))
            if ya:
                return jsonify({'success': False, 'error': f"Esa cuenta ya está enlazada al usuario '{ya[0]['usuario_sistema']}'."}), 400
            return jsonify({'success': False, 'error': 'No existe esa cuenta de acceso.'}), 404
        cuenta = cuenta[0]

        usuario_sistema = (data.get('usuario_sistema') or '').strip()
        if not usuario_sistema:
            return jsonify({'success': False, 'error': 'Escribe el nombre de usuario (usuario del sistema).'}), 400
        if len(usuario_sistema) < 3 or ' ' in usuario_sistema:
            return jsonify({'success': False, 'error': 'El nombre de usuario debe tener al menos 3 letras y sin espacios.'}), 400
        if db_query("SELECT 1 FROM usuarios WHERE LOWER(usuario_sistema) = LOWER(%s) OR LOWER(usuario) = LOWER(%s)",
                    (usuario_sistema, usuario_sistema)):
            return jsonify({'success': False, 'error': f"Ya existe el usuario '{usuario_sistema}'. Elige otro nombre."}), 400

        generada = None
        password = data.get('password') or ''
        if not password and data.get('generar_password'):
            password = generada = _password_temporal()
        if not password:
            return jsonify({'success': False, 'error': 'Escribe una contraseña o pulsa "Generar".'}), 400
        if not _password_aceptable(password):
            return jsonify({'success': False, 'error': 'La contraseña debe tener al menos 8 caracteres, con letras y números.'}), 400

        nombres = (data.get('nombres_apellidos') or '').strip() or usuario_sistema
        rol = (data.get('rol') or 'vendedor').strip().lower() or 'vendedor'
        nuevo = {
            'auth_user_id': cuenta['id'],
            'usuario_sistema': usuario_sistema,
            'nombres_apellidos': nombres,
            'area': (data.get('area') or '').strip() or None,
            'correo': cuenta.get('email'),
            'celular': None,
            'estado': 'inactivo',
            'password': password,
            'rol': rol,
        }
        empresas_pedidas = [str(c).strip().upper() for c in (data.get('empresas') or []) if str(c).strip()]
        rol_erp = (data.get('rol_erp') or '').strip()
        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            usuario_id = _insertar_usuario(cur, nuevo)
            if empresas_pedidas:
                if not rol_erp:
                    raise ValueError('Elige el rol ERP para las empresas marcadas.')
                cur.execute("SELECT id FROM erp_roles WHERE codigo = %s LIMIT 1", (rol_erp,))
                rol_row = cur.fetchone()
                if not rol_row:
                    raise ValueError(f"No existe el rol ERP '{rol_erp}'.")
                for codigo in empresas_pedidas:
                    cur.execute("SELECT id FROM erp_empresas WHERE UPPER(codigo) = %s", (codigo,))
                    emp = cur.fetchone()
                    if not emp:
                        raise ValueError(f"No existe la empresa '{codigo}'.")
                    cur.execute("""
                        INSERT INTO erp_usuario_empresas (auth_user_id, empresa_id, rol_id, es_empresa_principal, estado)
                        VALUES (%s, %s, %s, %s, 'activo')
                    """, (cuenta['id'], emp['id'], rol_row['id'], codigo == empresas_pedidas[0]))

        respuesta = {'id': usuario_id, 'usuario_sistema': usuario_sistema, 'correo': cuenta.get('email'),
                     'estado': 'inactivo'}
        if generada:
            # Solo se devuelve una vez; en la base queda guardada con hash.
            respuesta['password_generada'] = generada
        return jsonify({'success': True, 'data': respuesta,
                        'message': 'Usuario creado e INACTIVO. Actívalo cuando esté listo para entrar.'})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        print(f"❌ Error en crear_usuario_desde_auth: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@config_seguridad_bp.route('/usuarios/<int:usuario_id>/password', methods=['POST'])
def asignar_password_usuario(usuario_id):
    """El administrador asigna una contraseña NUEVA a cualquier usuario, sin pedir la anterior
    (pedido de Erika 19/10/2026). Body: password (mín. 8, letras y números) o generar: true.
    Se guarda cifrada; la generada se muestra una sola vez. Queda en la Auditoría (sin la contraseña)."""
    error = _solo_admin()
    if error:
        return error
    try:
        data = request.get_json(silent=True) or {}
        filas = db_query("SELECT id, usuario_sistema FROM usuarios WHERE id = %s", (usuario_id,))
        if not filas:
            return jsonify({'success': False, 'error': 'Usuario no encontrado'}), 404
        generada = None
        password = data.get('password') or ''
        if not password and data.get('generar'):
            password = generada = _password_temporal()
        if not password:
            return jsonify({'success': False, 'error': 'Escribe la nueva contraseña o pulsa "Generar".'}), 400
        if not _password_aceptable(password):
            return jsonify({'success': False, 'error': 'La contraseña debe tener al menos 8 caracteres, con letras y números.'}), 400
        from werkzeug.security import generate_password_hash
        db_execute("UPDATE usuarios SET password = %s, updated_at = NOW() WHERE id = %s",
                   (generate_password_hash(password), usuario_id))
        from routes.auditoria import registrar_auditoria
        registrar_auditoria('cambiar_contraseña', 'Usuarios', tabla='usuarios', registro_id=usuario_id,
                            detalle=f"El administrador asignó una contraseña nueva a '{filas[0]['usuario_sistema']}'")
        respuesta = {'id': usuario_id, 'usuario_sistema': filas[0]['usuario_sistema']}
        if generada:
            respuesta['password_generada'] = generada   # solo esta vez; en la base queda cifrada
        return jsonify({'success': True, 'data': respuesta,
                        'message': f"Contraseña nueva asignada a '{filas[0]['usuario_sistema']}'. "
                                   f"Desde ahora entra con esa contraseña."})
    except Exception as e:
        print(f"❌ Error en asignar_password_usuario: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@config_seguridad_bp.route('/usuarios-inactivos', methods=['GET'])
def listar_usuarios_inactivos():
    """Usuarios del ERP con estado distinto de 'activo' (la lista principal solo muestra activos)."""
    error = _solo_admin()
    if error:
        return error
    try:
        filas = db_query("""
            SELECT u.id, u.auth_user_id::text AS auth_user_id, u.usuario_sistema, u.nombres_apellidos,
                   u.correo, u.area, u.rol, u.estado, u.created_at
            FROM usuarios u
            WHERE COALESCE(u.estado, '') <> 'activo'
            ORDER BY u.created_at DESC NULLS LAST, u.usuario_sistema
        """)
        return jsonify({'success': True, 'data': filas, 'total': len(filas)})
    except Exception as e:
        print(f"❌ Error en listar_usuarios_inactivos: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@config_seguridad_bp.route('/usuarios/<int:usuario_id>/activar', methods=['POST'])
def activar_usuario(usuario_id):
    """Activa un usuario (desde ese momento puede iniciar sesión)."""
    error = _solo_admin()
    if error:
        return error
    try:
        filas = db_query("SELECT id, usuario_sistema, password FROM usuarios WHERE id = %s", (usuario_id,))
        if not filas:
            return jsonify({'success': False, 'error': 'Usuario no encontrado'}), 404
        if not filas[0].get('password'):
            return jsonify({'success': False, 'error': 'El usuario no tiene contraseña. Asígnale una antes de activarlo.'}), 400
        db_execute("UPDATE usuarios SET estado = 'activo', updated_at = NOW() WHERE id = %s", (usuario_id,))
        return jsonify({'success': True, 'message': f"Usuario '{filas[0]['usuario_sistema']}' activado. Ya puede entrar."})
    except Exception as e:
        print(f"❌ Error en activar_usuario: {e}")
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