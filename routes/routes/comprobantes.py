# routes/comprobantes.py
from flask import Blueprint, render_template, request, jsonify, session, send_file
from functools import wraps
import sys
import os
import json
from datetime import datetime, date
from io import BytesIO

sys.dont_write_bytecode = True

# Agregar el directorio padre al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db_insert, db_query, db_update

comprobantes_bp = Blueprint('comprobantes', __name__, url_prefix='/comprobantes')

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session:
            return jsonify({'success': False, 'error': 'No autorizado'}), 401
        return f(*args, **kwargs)
    return decorated_function


# ==========================================
# RUTAS DE VISTAS (HTML)
# ==========================================

@comprobantes_bp.route('/')
def index():
    """Listado de comprobantes emitidos"""
    try:
        query = """
            SELECT id, tipo_comprobante, serie, numero, 
                   cliente_nombre, cliente_numero_doc, fecha_emision, 
                   subtotal, igv, total, estado_sunat, created_at
            FROM comprobantes
            ORDER BY created_at DESC
        """
        comprobantes = db_query(query)
        return render_template('comprobantes/lista.html', comprobantes=comprobantes or [])
    except Exception as e:
        print(f"Error: {e}")
        return render_template('comprobantes/lista.html', comprobantes=[])


@comprobantes_bp.route('/crear')
def crear():
    """Formulario para crear un nuevo comprobante"""
    return render_template('comprobantes/crear.html')


@comprobantes_bp.route('/editar/<int:comp_id>')
def editar(comp_id):
    """Formulario para editar un comprobante"""
    try:
        query = "SELECT * FROM comprobantes WHERE id = %s"
        comprobante = db_query(query, (comp_id,))
        
        if not comprobante:
            return "Comprobante no encontrado", 404
        
        # Convertir el objeto Row a diccionario
        comprobante_dict = dict(comprobante[0])
        
        # Convertir datetime a string para evitar errores en el template
        if comprobante_dict.get('created_at'):
            if isinstance(comprobante_dict['created_at'], (datetime, date)):
                comprobante_dict['created_at'] = comprobante_dict['created_at'].strftime('%Y-%m-%d %H:%M:%S')
        
        if comprobante_dict.get('updated_at'):
            if isinstance(comprobante_dict['updated_at'], (datetime, date)):
                comprobante_dict['updated_at'] = comprobante_dict['updated_at'].strftime('%Y-%m-%d %H:%M:%S')
        
        if comprobante_dict.get('fecha_emision'):
            if isinstance(comprobante_dict['fecha_emision'], (datetime, date)):
                comprobante_dict['fecha_emision'] = comprobante_dict['fecha_emision'].strftime('%Y-%m-%d')
        
        # Asegurar que items_json sea un string JSON válido
        if comprobante_dict.get('items_json') and isinstance(comprobante_dict['items_json'], (dict, list)):
            comprobante_dict['items_json'] = json.dumps(comprobante_dict['items_json'])
        
        return render_template('comprobantes/editar.html', comprobante=comprobante_dict)
    except Exception as e:
        print(f"Error en editar: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"Error: {e}", 500


@comprobantes_bp.route('/ver/<int:comp_id>')
def ver(comp_id):
    """Ver detalle de un comprobante"""
    try:
        query = "SELECT * FROM comprobantes WHERE id = %s"
        comprobante = db_query(query, (comp_id,))
        
        if not comprobante:
            return "Comprobante no encontrado", 404
        
        # Convertir a diccionario
        comprobante_dict = dict(comprobante[0])
        
        # Convertir fechas a string
        if comprobante_dict.get('created_at'):
            if isinstance(comprobante_dict['created_at'], (datetime, date)):
                comprobante_dict['created_at'] = comprobante_dict['created_at'].strftime('%Y-%m-%d %H:%M:%S')
        
        if comprobante_dict.get('fecha_emision'):
            if isinstance(comprobante_dict['fecha_emision'], (datetime, date)):
                comprobante_dict['fecha_emision'] = comprobante_dict['fecha_emision'].strftime('%Y-%m-%d')
        
        return render_template('comprobantes/ver.html', comprobante=comprobante_dict)
    except Exception as e:
        print(f"Error en ver: {str(e)}")
        return f"Error: {e}", 500


# ==========================================
# API ENDPOINTS
# ==========================================

@comprobantes_bp.route('/api/guardar', methods=['POST'])
@login_required
def guardar_comprobante():
    """Guardar comprobante (Factura o Boleta) como borrador"""
    try:
        data = request.get_json()
        
        # Validaciones SUNAT (campos obligatorios)
        tipo = data.get('tipo_comprobante')
        if tipo not in ['FACTURA', 'BOLETA']:
            return jsonify({'success': False, 'error': 'Tipo de comprobante inválido'})
        
        if not data.get('cliente', {}).get('numero_documento'):
            return jsonify({'success': False, 'error': 'El documento del cliente es obligatorio'})
        
        if not data.get('cliente', {}).get('nombre'):
            return jsonify({'success': False, 'error': 'El nombre/razón social del cliente es obligatorio'})
        
        if not data.get('items') or len(data.get('items')) == 0:
            return jsonify({'success': False, 'error': 'Debe agregar al menos un producto'})
        
        # Generar número de comprobante automático
        serie = data.get('serie', 'F001' if tipo == 'FACTURA' else 'B001')
        
        query_max = """
            SELECT COALESCE(MAX(numero), 0) + 1 as next_num
            FROM comprobantes 
            WHERE serie = %s
        """
        result = db_query(query_max, (serie,))
        numero = result[0]['next_num'] if result else 1
        
        # Calcular totales (ya vienen del frontend, pero validamos)
        subtotal = data.get('subtotal', 0)
        igv = data.get('igv', subtotal * 0.18)
        total = data.get('total', subtotal + igv)
        
        items_json = json.dumps(data['items'], default=str)
        
        # Guardar en BD
        insert_query = """
            INSERT INTO comprobantes (
                tipo_comprobante, serie, numero, fecha_emision, moneda,
                cliente_tipo_doc, cliente_numero_doc, cliente_nombre, 
                cliente_direccion, cliente_email, cliente_telefono,
                subtotal, igv, total, items_json, observaciones, 
                estado_sunat, creado_por
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        
        params = (
            tipo, serie, numero, data.get('fecha_emision'), data.get('moneda', 'PEN'),
            data.get('cliente', {}).get('tipo_documento', 'RUC'),
            data.get('cliente', {}).get('numero_documento', ''),
            data.get('cliente', {}).get('nombre', ''),
            data.get('cliente', {}).get('direccion', ''),
            data.get('cliente', {}).get('email', ''),
            data.get('cliente', {}).get('telefono', ''),
            subtotal, igv, total, items_json,
            data.get('observaciones', ''),
            'BORRADOR',
            session.get('usuario_id')
        )
        
        result = db_insert(insert_query, params)
        
        if result:
            return jsonify({
                'success': True,
                'comprobante_id': result,
                'numero': f"{serie}-{numero}",
                'message': f'{tipo} guardada como borrador'
            })
        else:
            return jsonify({'success': False, 'error': 'Error al guardar'})
            
    except Exception as e:
        print(f"Error guardando comprobante: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@comprobantes_bp.route('/api/enviar-sunat', methods=['POST'])
@login_required
def enviar_sunat():
    """Enviar comprobante a SUNAT (modo demo - pendiente integración real)"""
    try:
        data = request.get_json()
        
        # Validaciones
        tipo = data.get('tipo_comprobante')
        if tipo not in ['FACTURA', 'BOLETA']:
            return jsonify({'success': False, 'error': 'Tipo de comprobante inválido'})
        
        if not data.get('cliente', {}).get('numero_documento'):
            return jsonify({'success': False, 'error': 'El documento del cliente es obligatorio'})
        
        if not data.get('items') or len(data.get('items')) == 0:
            return jsonify({'success': False, 'error': 'Debe agregar al menos un producto'})
        
        # Generar número de comprobante
        serie = data.get('serie', 'F001' if tipo == 'FACTURA' else 'B001')
        
        query_max = """
            SELECT COALESCE(MAX(numero), 0) + 1 as next_num
            FROM comprobantes 
            WHERE serie = %s
        """
        result = db_query(query_max, (serie,))
        numero = result[0]['next_num'] if result else 1
        
        subtotal = data.get('subtotal', 0)
        igv = data.get('igv', subtotal * 0.18)
        total = data.get('total', subtotal + igv)
        
        items_json = json.dumps(data['items'], default=str)
        
        # Guardar con estado PROCESANDO
        insert_query = """
            INSERT INTO comprobantes (
                tipo_comprobante, serie, numero, fecha_emision, moneda,
                cliente_tipo_doc, cliente_numero_doc, cliente_nombre, 
                cliente_direccion, cliente_email, cliente_telefono,
                subtotal, igv, total, items_json, observaciones, 
                estado_sunat, creado_por
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        
        params = (
            tipo, serie, numero, data.get('fecha_emision'), data.get('moneda', 'PEN'),
            data.get('cliente', {}).get('tipo_documento', 'RUC'),
            data.get('cliente', {}).get('numero_documento', ''),
            data.get('cliente', {}).get('nombre', ''),
            data.get('cliente', {}).get('direccion', ''),
            data.get('cliente', {}).get('email', ''),
            data.get('cliente', {}).get('telefono', ''),
            subtotal, igv, total, items_json,
            data.get('observaciones', ''),
            'PROCESANDO',
            session.get('usuario_id')
        )
        
        comp_id = db_insert(insert_query, params)
        
        if not comp_id:
            return jsonify({'success': False, 'error': 'Error al guardar'})
        
        # TODO: Aquí se conectará con SUNAT (próximo paso)
        # Por ahora, simulamos que se envió correctamente
        update_query = """
            UPDATE comprobantes 
            SET estado_sunat = 'ACEPTADA',
                sunat_response = %s,
                cdr_response = 'Envío exitoso (modo demo - pendiente conexión SUNAT)'
            WHERE id = %s
        """
        demo_response = json.dumps({
            'code': '0',
            'message': 'Aceptada (modo demo)',
            'sunat_date': datetime.now().isoformat()
        })
        db_update(update_query, (demo_response, comp_id))
        
        return jsonify({
            'success': True,
            'comprobante_id': comp_id,
            'numero': f"{serie}-{numero}",
            'message': f'{tipo} enviada a SUNAT exitosamente (modo demo)'
        })
        
    except Exception as e:
        print(f"Error enviando a SUNAT: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@comprobantes_bp.route('/api/listar', methods=['GET'])
@login_required
def listar_comprobantes():
    """Listar todos los comprobantes"""
    try:
        query = """
            SELECT id, tipo_comprobante, serie, numero, cliente_nombre, 
                   cliente_numero_doc, fecha_emision, subtotal, igv, total, 
                   estado_sunat, created_at
            FROM comprobantes
            ORDER BY created_at DESC
        """
        comprobantes = db_query(query)
        
        return jsonify({
            'success': True,
            'data': comprobantes or []
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@comprobantes_bp.route('/api/obtener/<int:comp_id>', methods=['GET'])
@login_required
def obtener_comprobante(comp_id):
    """Obtener un comprobante por ID"""
    try:
        query = "SELECT * FROM comprobantes WHERE id = %s"
        comprobante = db_query(query, (comp_id,))
        
        if not comprobante:
            return jsonify({'success': False, 'error': 'Comprobante no encontrado'})
        
        return jsonify({
            'success': True,
            'data': comprobante[0]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@comprobantes_bp.route('/api/actualizar/<int:comp_id>', methods=['PUT'])
@login_required
def actualizar_comprobante(comp_id):
    """Actualizar un comprobante existente (solo si está en BORRADOR)"""
    try:
        data = request.get_json()
        
        # Verificar estado actual
        check_query = "SELECT estado_sunat FROM comprobantes WHERE id = %s"
        check_result = db_query(check_query, (comp_id,))
        
        if not check_result:
            return jsonify({'success': False, 'error': 'Comprobante no encontrado'})
        
        if check_result[0]['estado_sunat'] != 'BORRADOR':
            return jsonify({'success': False, 'error': 'Solo se pueden editar comprobantes en estado BORRADOR'})
        
        # Validaciones
        if not data.get('cliente', {}).get('numero_documento'):
            return jsonify({'success': False, 'error': 'El documento del cliente es obligatorio'})
        
        if not data.get('items') or len(data.get('items')) == 0:
            return jsonify({'success': False, 'error': 'Debe agregar al menos un producto'})
        
        subtotal = data.get('subtotal', 0)
        igv = data.get('igv', subtotal * 0.18)
        total = data.get('total', subtotal + igv)
        
        items_json = json.dumps(data['items'], default=str)
        
        update_query = """
            UPDATE comprobantes SET
                fecha_emision = %s,
                cliente_tipo_doc = %s,
                cliente_numero_doc = %s,
                cliente_nombre = %s,
                cliente_direccion = %s,
                cliente_email = %s,
                cliente_telefono = %s,
                subtotal = %s,
                igv = %s,
                total = %s,
                items_json = %s,
                observaciones = %s,
                updated_at = NOW()
            WHERE id = %s
            RETURNING id
        """
        
        params = (
            data.get('fecha_emision'),
            data.get('cliente', {}).get('tipo_documento', 'RUC'),
            data.get('cliente', {}).get('numero_documento', ''),
            data.get('cliente', {}).get('nombre', ''),
            data.get('cliente', {}).get('direccion', ''),
            data.get('cliente', {}).get('email', ''),
            data.get('cliente', {}).get('telefono', ''),
            subtotal, igv, total, items_json,
            data.get('observaciones', ''),
            comp_id
        )
        
        result = db_update(update_query, params)
        
        if result:
            return jsonify({
                'success': True,
                'comprobante_id': comp_id,
                'message': 'Comprobante actualizado exitosamente'
            })
        else:
            return jsonify({'success': False, 'error': 'Error al actualizar'})
            
    except Exception as e:
        print(f"Error actualizando comprobante: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})


@comprobantes_bp.route('/api/eliminar/<int:comp_id>', methods=['DELETE'])
@login_required
def eliminar_comprobante(comp_id):
    """Eliminar un comprobante (solo si está en estado BORRADOR)"""
    try:
        # Verificar que exista y esté en estado BORRADOR
        check_query = "SELECT estado_sunat FROM comprobantes WHERE id = %s"
        check_result = db_query(check_query, (comp_id,))
        
        if not check_result:
            return jsonify({'success': False, 'error': 'Comprobante no encontrado'}), 404
        
        if check_result[0]['estado_sunat'] != 'BORRADOR':
            return jsonify({'success': False, 'error': 'Solo se pueden eliminar comprobantes en estado BORRADOR'}), 400
        
        # Eliminar el comprobante
        delete_query = "DELETE FROM comprobantes WHERE id = %s"
        db_update(delete_query, (comp_id,))
        
        return jsonify({
            'success': True,
            'message': 'Comprobante eliminado exitosamente'
        })
        
    except Exception as e:
        print(f"Error eliminando comprobante: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@comprobantes_bp.route('/api/pdf/<int:comp_id>', methods=['GET'])
@login_required
def descargar_pdf(comp_id):
    """Generar y descargar PDF del comprobante"""
    try:
        # Obtener datos del comprobante
        query = "SELECT * FROM comprobantes WHERE id = %s"
        comprobante = db_query(query, (comp_id,))
        
        if not comprobante:
            return jsonify({'success': False, 'error': 'Comprobante no encontrado'}), 404
        
        comp_data = comprobante[0]
        
        # Procesar items
        items = []
        if comp_data.get('items_json'):
            if isinstance(comp_data['items_json'], str):
                items = json.loads(comp_data['items_json'])
            else:
                items = comp_data['items_json']
        
        # Generar HTML para el PDF
        html_content = generar_html_pdf(comp_data, items)
        
        # Generar PDF con weasyprint
        try:
            from weasyprint import HTML
        except ImportError:
            # Fallback si no está instalado weasyprint
            return jsonify({'success': False, 'error': 'Módulo weasyprint no instalado'}), 500
        
        pdf_file = BytesIO()
        HTML(string=html_content).write_pdf(pdf_file)
        pdf_file.seek(0)
        
        # Enviar como descarga
        tipo_abrev = 'F' if comp_data['tipo_comprobante'] == 'FACTURA' else 'B'
        nombre_archivo = f"{tipo_abrev}{comp_data['serie']}-{comp_data['numero']}.pdf"
        
        return send_file(
            pdf_file,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=nombre_archivo
        )
        
    except Exception as e:
        print(f"Error generando PDF: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


def generar_html_pdf(comp_data, items):
    """Genera el HTML para el PDF del comprobante"""
    
    # Convertir a diccionario si es necesario (para manejar objetos tipo Row)
    if not isinstance(comp_data, dict):
        if hasattr(comp_data, 'items'):
            comp_data = dict(comp_data)
        else:
            comp_data = {}
    
    # Obtener valores de forma segura
    tipo_comprobante = comp_data.get('tipo_comprobante', 'FACTURA')
    serie = comp_data.get('serie', 'F001')
    numero = comp_data.get('numero', 1)
    cliente_tipo_doc = comp_data.get('cliente_tipo_doc', 'RUC')
    cliente_numero_doc = comp_data.get('cliente_numero_doc', '-')
    cliente_nombre = comp_data.get('cliente_nombre', '-')
    cliente_direccion = comp_data.get('cliente_direccion', '-')
    moneda = comp_data.get('moneda', 'PEN')
    estado_sunat = comp_data.get('estado_sunat', 'BORRADOR')
    observaciones = comp_data.get('observaciones', '')
    
    # Convertir fechas
    fecha_emision = comp_data.get('fecha_emision', '')
    if fecha_emision:
        try:
            if isinstance(fecha_emision, (datetime, date)):
                fecha_emision = fecha_emision.strftime('%d/%m/%Y')
            else:
                fecha_emision = datetime.strptime(str(fecha_emision), '%Y-%m-%d').strftime('%d/%m/%Y')
        except:
            fecha_emision = str(fecha_emision)
    else:
        fecha_emision = ''
    
    # Obtener totales como floats
    subtotal = float(comp_data.get('subtotal', 0))
    igv = float(comp_data.get('igv', 0))
    total = float(comp_data.get('total', 0))
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>{tipo_comprobante} {serie}-{numero}</title>
        <style>
            @page {{
                size: A4;
                margin: 1.5cm;
            }}
            body {{
                font-family: 'Helvetica', Arial, sans-serif;
                font-size: 11px;
                line-height: 1.4;
                color: #333;
            }}
            .header {{
                text-align: center;
                margin-bottom: 20px;
                border-bottom: 2px solid #333;
                padding-bottom: 10px;
            }}
            .header h1 {{
                font-size: 18px;
                margin: 0;
                color: #1a1a2e;
            }}
            .info-grid {{
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 15px;
                margin-bottom: 20px;
            }}
            .info-box {{
                border: 1px solid #ddd;
                padding: 10px;
                border-radius: 5px;
                background: #f9f9f9;
            }}
            .info-box h3 {{
                font-size: 12px;
                margin: 0 0 8px 0;
                padding-bottom: 5px;
                border-bottom: 1px solid #ddd;
                color: #2563eb;
            }}
            .info-row {{
                margin-bottom: 5px;
            }}
            .info-label {{
                font-weight: bold;
                font-size: 10px;
                color: #666;
            }}
            .products-table {{
                width: 100%;
                border-collapse: collapse;
                margin: 15px 0;
            }}
            .products-table th {{
                background: #1e293b;
                color: white;
                padding: 8px;
                font-size: 10px;
                text-align: center;
                border: 1px solid #333;
            }}
            .products-table td {{
                padding: 6px;
                border: 1px solid #ddd;
                text-align: center;
                font-size: 10px;
            }}
            .summary {{
                margin-top: 15px;
                text-align: right;
            }}
            .summary-row {{
                padding: 5px;
            }}
            .summary-row.total {{
                font-size: 14px;
                font-weight: bold;
                border-top: 2px solid #333;
                padding-top: 8px;
            }}
            .footer {{
                margin-top: 30px;
                text-align: center;
                font-size: 9px;
                color: #999;
                border-top: 1px solid #ddd;
                padding-top: 10px;
            }}
            .observaciones {{
                margin-top: 15px;
                padding: 10px;
                background: #fef3c7;
                border-left: 3px solid #f59e0b;
                font-size: 10px;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>{tipo_comprobante} ELECTRÓNICA</h1>
            <p>N° {serie}-{numero}</p>
        </div>
        
        <div class="info-grid">
            <div class="info-box">
                <h3>📦 EMPRESA EMISORA</h3>
                <div class="info-row"><span class="info-label">RUC:</span> 20123456789</div>
                <div class="info-row"><span class="info-label">Razón Social:</span> KCF CORPORACION SAC</div>
            </div>
            <div class="info-box">
                <h3>🎯 CLIENTE</h3>
                <div class="info-row"><span class="info-label">{cliente_tipo_doc}:</span> {cliente_numero_doc}</div>
                <div class="info-row"><span class="info-label">Razón Social:</span> {cliente_nombre}</div>
                <div class="info-row"><span class="info-label">Dirección:</span> {cliente_direccion}</div>
            </div>
        </div>
        
        <div class="info-grid">
            <div class="info-box">
                <h3>📄 DATOS DEL COMPROBANTE</h3>
                <div class="info-row"><span class="info-label">Fecha Emisión:</span> {fecha_emision}</div>
                <div class="info-row"><span class="info-label">Moneda:</span> {moneda}</div>
            </div>
            <div class="info-box">
                <h3>🚚 DATOS ADICIONALES</h3>
                <div class="info-row"><span class="info-label">Estado SUNAT:</span> {estado_sunat}</div>
            </div>
        </div>
        
        <h3 style="margin: 15px 0 10px 0;">📋 DETALLE DE PRODUCTOS</h3>
        <table class="products-table">
            <thead>
                <tr>
                    <th>Item</th>
                    <th>Código</th>
                    <th>Descripción</th>
                    <th>Unidad</th>
                    <th>Cantidad</th>
                    <th>Precio Unit.</th>
                    <th>Subtotal</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for idx, item in enumerate(items, 1):
        if isinstance(item, dict):
            cantidad = float(item.get('cantidad', 0))
            precio = float(item.get('precio_unitario', 0))
            subtotal_item = cantidad * precio
            codigo = item.get('codigo', '-')
            descripcion = item.get('descripcion', '-')
            unidad = item.get('unidad', 'NIU')
        else:
            cantidad = precio = subtotal_item = 0
            codigo = descripcion = '-'
            unidad = 'NIU'
        
        html += f"""
                <tr>
                    <td>{idx}</td>
                    <td>{codigo}</td>
                    <td style="text-align: left;">{descripcion}</td>
                    <td>{unidad}</td>
                    <td>{cantidad:.2f}</td>
                    <td>S/ {precio:.2f}</td>
                    <td>S/ {subtotal_item:.2f}</td>
                </tr>
        """
    
    html += f"""
            </tbody>
        </table>
        
        <div class="summary">
            <div class="summary-row"><strong>SUBTOTAL:</strong> S/ {subtotal:.2f}</div>
            <div class="summary-row"><strong>IGV (18%):</strong> S/ {igv:.2f}</div>
            <div class="summary-row total"><strong>TOTAL:</strong> S/ {total:.2f}</div>
        </div>
    """
    
    if observaciones:
        html += f"""
        <div class="observaciones">
            <strong>📝 Observaciones:</strong><br>
            {observaciones}
        </div>
        """
    
    html += """
        <div class="footer">
            <p>Documento emitido electrónicamente por KCF CORPORACION - Sistema ERP</p>
            <p>Este documento es una representación impresa de un comprobante electrónico</p>
        </div>
    </body>
    </html>
    """
    
    return html