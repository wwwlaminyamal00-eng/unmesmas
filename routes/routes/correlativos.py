# routes/correlativos.py
from flask import Blueprint, render_template, request, jsonify
from database import db_query, db_execute, db_tx
from psycopg2.extras import RealDictCursor

# ============================================================
# BLUEPRINT - UN SOLO Blueprint para todo
# ============================================================
correlativos_bp = Blueprint('correlativos', __name__)

# ============================================================
# RUTA PARA LA PÁGINA HTML
# ============================================================
@correlativos_bp.route('/correlativos')
def correlativos_page():
    """Página de correlativos"""
    return render_template('correlativos.html')

# ============================================================
# ENDPOINTS API PARA CORRELATIVOS
# ============================================================

@correlativos_bp.route('/api/config/correlativos', methods=['GET'])
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


@correlativos_bp.route('/api/config/correlativos/<correlativo_id>', methods=['GET'])
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


@correlativos_bp.route('/api/config/correlativos', methods=['POST'])
def create_correlativo():
    """Crear un nuevo correlativo o reactivar uno existente"""
    try:
        data = request.get_json()
        print(f"📝 Creando correlativo - Datos recibidos: {data}")
        
        required = ['empresa_id', 'documento', 'prefijo']
        for field in required:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'Campo {field} es requerido'}), 400
        
        empresa = db_query("SELECT id, codigo FROM erp_empresas WHERE id = %s AND estado = 'activo'", (data.get('empresa_id'),))
        if not empresa:
            return jsonify({'success': False, 'error': 'Empresa no encontrada o inactiva'}), 404
        
        anio = data.get('anio', 2026)
        documento = data.get('documento')
        empresa_id = data.get('empresa_id')
        
        existente = db_query("""
            SELECT id, estado, ultimo_numero, prefijo 
            FROM erp_correlativos 
            WHERE empresa_id = %s AND documento = %s AND anio = %s
        """, (empresa_id, documento, anio))
        
        if existente:
            existing = existente[0]
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
                return jsonify({
                    'success': False, 
                    'error': f'Ya existe un correlativo activo para "{documento}" en el año {anio}'
                }), 400
        
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


@correlativos_bp.route('/api/config/correlativos/<correlativo_id>', methods=['PUT'])
def update_correlativo(correlativo_id):
    """Actualizar un correlativo existente (UUID)"""
    try:
        data = request.get_json()
        print(f"📝 Actualizando correlativo {correlativo_id}: {data}")
        
        existente = db_query("SELECT id, empresa_id, documento FROM erp_correlativos WHERE id = %s", (correlativo_id,))
        if not existente:
            return jsonify({'success': False, 'error': 'Correlativo no encontrado'}), 404
        
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


@correlativos_bp.route('/api/config/correlativos/<correlativo_id>', methods=['DELETE'])
def delete_correlativo(correlativo_id):
    """Eliminar correlativo (borrado lógico) - UUID"""
    try:
        print(f"🗑️ Eliminando correlativo con ID: {correlativo_id}")
        
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


@correlativos_bp.route('/api/config/correlativos/tomar', methods=['POST'])
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
        
        empresa = db_query("SELECT id, codigo FROM erp_empresas WHERE codigo = %s AND estado = 'activo'", (empresa_codigo,))
        if not empresa:
            return jsonify({'success': False, 'error': f'Empresa "{empresa_codigo}" no encontrada'}), 404
        
        empresa_id = empresa[0]['id']
        
        correlativo = db_query("""
            SELECT id, ultimo_numero, prefijo, documento
            FROM erp_correlativos 
            WHERE empresa_id = %s AND documento = %s AND anio = %s AND estado = 'activo'
        """, (empresa_id, documento, anio))
        
        if not correlativo:
            inactivo = db_query("""
                SELECT id, prefijo FROM erp_correlativos 
                WHERE empresa_id = %s AND documento = %s AND anio = %s AND estado = 'inactivo'
            """, (empresa_id, documento, anio))
            
            if inactivo:
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