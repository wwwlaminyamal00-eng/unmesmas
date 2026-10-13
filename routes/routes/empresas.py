# routes/empresas.py
from flask import Blueprint, render_template, request, jsonify
from database import db_query, db_tx
from psycopg2.extras import RealDictCursor

# ============================================================
# BLUEPRINT - UN SOLO Blueprint para todo
# ============================================================
empresas_bp = Blueprint('empresas', __name__)

# ============================================================
# RUTA PARA LA PÁGINA HTML
# ============================================================
@empresas_bp.route('/empresas')
def empresas_page():
    """Página de empresas"""
    return render_template('empresas.html')

# ============================================================
# ENDPOINTS API PARA EMPRESAS
# ============================================================

@empresas_bp.route('/api/config/empresas', methods=['GET'])
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


@empresas_bp.route('/api/config/empresas/<empresa_id>', methods=['GET'])
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


@empresas_bp.route('/api/config/empresas', methods=['POST'])
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


@empresas_bp.route('/api/config/empresas/<empresa_id>', methods=['PUT'])
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


@empresas_bp.route('/api/config/empresas/<empresa_id>', methods=['DELETE'])
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