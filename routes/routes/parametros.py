# routes/parametros.py
from flask import Blueprint, render_template, request, jsonify
from database import db_query, db_execute
from psycopg2.extras import RealDictCursor

# ============================================================
# BLUEPRINT - UN SOLO Blueprint para todo
# ============================================================
parametros_bp = Blueprint('parametros', __name__)

# ============================================================
# RUTA PARA LA PÁGINA HTML
# ============================================================
@parametros_bp.route('/parametros')
def parametros_page():
    """Página de parámetros"""
    return render_template('parametros.html')

# ============================================================
# ENDPOINTS API PARA PARÁMETROS
# ============================================================

@parametros_bp.route('/api/config/parametros', methods=['GET'])
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


@parametros_bp.route('/api/config/parametros', methods=['POST'])
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


@parametros_bp.route('/api/config/parametros/<parametro_id>', methods=['DELETE'])
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