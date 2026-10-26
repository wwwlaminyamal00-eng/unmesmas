# pdf_generator.py - VERSIÓN CORREGIDA CON RÓTULO DE GUÍA (ROJO)

import os
from jinja2 import Template
from weasyprint import HTML
from datetime import datetime
import json
import base64
import re


class PDFGenerator:
    def __init__(self):
        self.templates_dir = 'templates/cotizacion_oc/'
        self.logo_base64 = None
        # Colores corporativos
        self.COLOR_ROJO = '#CC0000'
        self.COLOR_GRIS = '#999999'
        self.COLOR_GRIS_CLARO = '#cccccc'
        self.COLOR_FONDO_GRIS = '#f5f5f5'
        # Función db_query inyectable (se asigna desde app.py)
        self.db_query = None

    # ============================================================
    # OBTENER LOGO EN BASE64
    # ============================================================
    def _obtener_logo_base64(self):
        if self.logo_base64:
            return self.logo_base64
        
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
                        self.logo_base64 = base64.b64encode(logo_data).decode('utf-8')
                        print(f"✅ Logo cargado desde: {logo_path}")
                        return self.logo_base64
                except Exception as e:
                    print(f"⚠️ Error: {e}")
                    continue
            else:
                print(f"🔍 Logo no encontrado: {logo_path}")
        
        print("❌ No se encontró el logo")
        return None

    # ============================================================
    # BUSCAR GUÍA DE REMISIÓN VINCULADA A UNA FACTURA
    # ============================================================
    def _emisora(self, datos):
        """Empresa que emite el documento. La ruta la manda en datos['empresa_pdf'] (KCF, AGD...);
        si no la manda, se usan los datos de KCF como siempre."""
        e = (datos or {}).get('empresa_pdf')
        if e:
            return e
        logo_base64 = self._obtener_logo_base64()
        return {
            'ruc': '20602095704', 'nombre': 'KCF CORPORACION E.I.R.L', 'corto': 'KCF',
            'direccion': 'JR. LAS ALMENDRAS VERDES NRO. 284 URB. VIRGEN DEL ROSARIO LIMA - LIMA - SAN MARTIN DE PORRES',
            'telefono': '999 932 051', 'email': 'ventas@kcfcorporacion.com', 'web': 'https://kcfcorporacion.com/',
            'color': '#CC0000', 'logo_src': f"data:image/png;base64,{logo_base64}" if logo_base64 else "",
        }

    def _buscar_guia_vinculada(self, serie_factura, numero_factura):
        if not self.db_query:
            return ''
        
        try:
            referencia = f"{serie_factura}-{numero_factura}"
            query = """
                SELECT serie, numero
                FROM guias_remision
                WHERE factura = %s
                   OR documento_asociado = %s
                ORDER BY id DESC
                LIMIT 1
            """
            resultado = self.db_query(query, (referencia, referencia))
            
            if resultado:
                guia = resultado[0]
                guia_str = f"{guia.get('serie', '')}-{guia.get('numero', '')}"
                print(f"✅ Guía vinculada encontrada: {guia_str}")
                return guia_str
        except Exception as e:
            print(f"⚠️ Error buscando guía vinculada: {e}")
        
        return ''

    # ============================================================
    # MÉTODO PRINCIPAL
    # ============================================================
    def generar_pdf_universal(self, datos):
        print(f"📄 Generando PDF universal...")
        tipo = datos.get('tipo_documento', '')
        
        if tipo == 'guia_remision' or ('serie' in datos and 'numero' in datos and 'destinatario_nombre' in datos):
            return self._generar_guia_remision(datos)
        elif tipo in ['factura', 'boleta', 'comprobante']:
            return self._generar_comprobante(datos)
        elif tipo == 'cotizacion' or 'numero_cotizacion' in datos or 'cliente_nombre' in datos:
            return self._generar_cotizacion(datos)
        else:
            return self._generar_cotizacion(datos)

    # ============================================================
    # FUNCIÓN PARA CONVERTIR NÚMEROS A LETRAS
    # ============================================================
    @staticmethod
    def _simbolo(datos):
        """US$ si el documento es en dólares (24/10/2026); si no, S/."""
        v = str((datos or {}).get('moneda') or '').upper()
        return 'US$' if ('$' in v and 'S/' not in v) or 'USD' in v or 'DÓLAR' in v or 'DOLAR' in v else 'S/'

    def numero_a_letras(self, numero):
        try:
            numero = float(numero)
            if numero == 0:
                return "CERO"
            
            unidades = ["", "UN", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE"]
            decenas = ["", "DIEZ", "VEINTE", "TREINTA", "CUARENTA", "CINCUENTA", 
                      "SESENTA", "SETENTA", "OCHENTA", "NOVENTA"]
            centenas = ["", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS", 
                       "QUINIENTOS", "SEISCIENTOS", "SETECIENTOS", "OCHOCIENTOS", "NOVECIENTOS"]
            
            entero = int(numero)
            decimal = int(round((numero - entero) * 100, 2))
            
            def convertir_grupo(n):
                if n == 0:
                    return ""
                if n == 100:
                    return "CIEN"
                
                texto = ""
                if n >= 100:
                    c = n // 100
                    texto += centenas[c]
                    n = n % 100
                    if n > 0:
                        texto += " "
                
                if n >= 10:
                    d = n // 10
                    u = n % 10
                    if d == 1 and u > 0:
                        especiales = {11: "ONCE", 12: "DOCE", 13: "TRECE", 14: "CATORCE", 
                                     15: "QUINCE", 16: "DIECISÉIS", 17: "DIECISIETE", 
                                     18: "DIECIOCHO", 19: "DIECINUEVE"}
                        texto += especiales.get(n, "")
                    else:
                        texto += decenas[d]
                        if u > 0:
                            if d == 2:
                                especiales = {1: "UN", 2: "DOS", 3: "TRES", 4: "CUATRO", 
                                             5: "CINCO", 6: "SEIS", 7: "SIETE", 8: "OCHO", 9: "NUEVE"}
                                texto += "Y" + especiales[u]
                            else:
                                texto += " Y " + unidades[u]
                elif n > 0:
                    texto += unidades[n]
                
                return texto.strip()
            
            texto_final = ""
            
            millones = entero // 1000000
            if millones > 0:
                if millones == 1:
                    texto_final += "UN MILLÓN"
                else:
                    texto_final += convertir_grupo(millones) + " MILLONES"
                entero = entero % 1000000
                if entero > 0:
                    texto_final += " "
            
            miles = entero // 1000
            if miles > 0:
                if miles == 1:
                    texto_final += "MIL"
                else:
                    texto_final += convertir_grupo(miles) + " MIL"
                entero = entero % 1000
                if entero > 0:
                    texto_final += " "
            
            if entero > 0:
                texto_final += convertir_grupo(entero)
            
            if decimal > 0:
                texto_final += f" CON {decimal:02d}/100"
            else:
                texto_final += " CON 00/100"
            
            return texto_final.upper()
            
        except Exception as e:
            print(f"⚠️ Error convirtiendo número a letras: {e}")
            return str(numero)

    # ============================================================
    # GENERAR FACTURA / BOLETA
    # ============================================================
    def _generar_comprobante(self, datos_comprobante):
        try:
            print("📄 Generando PDF de comprobante...")

            EMPRESA = self._emisora(datos_comprobante)
            logo_src = EMPRESA.get('logo_src', '')

            items = datos_comprobante.get('items', [])
            
            if not items and 'items_json' in datos_comprobante:
                items_json = datos_comprobante['items_json']
                if isinstance(items_json, str):
                    try:
                        items = json.loads(items_json)
                    except:
                        items = []
                elif isinstance(items_json, list):
                    items = items_json

            if not items and 'productos' in datos_comprobante:
                items = datos_comprobante['productos']
            
            if not items and 'detalle' in datos_comprobante:
                items = datos_comprobante['detalle']

            if not items:
                items = [
                    {'codigo': 'PRD-001', 'producto': 'Producto de ejemplo 1', 'cantidad': 2, 'valorVenta': 100.00},
                    {'codigo': 'PRD-002', 'producto': 'Producto de ejemplo 2', 'cantidad': 1, 'valorVenta': 250.00}
                ]

            items_formateados = []
            for idx, item in enumerate(items, 1):
                try:
                    if isinstance(item, dict):
                        cantidad = float(item.get('cantidad', item.get('cant', item.get('qty', 1))))
                        precio = float(item.get('valorVenta', item.get('precio', item.get('precio_unitario', item.get('price', 0)))))
                        total_item = cantidad * precio
                        
                        descripcion = (item.get('descripcion_cliente') or '').strip() or item.get('producto', item.get('descripcion', item.get('nombre', item.get('name', 'Sin descripción'))))
                        
                        items_formateados.append({
                            'item': idx,
                            'codigo': item.get('codigo', item.get('code', '')),
                            'descripcion': descripcion,
                            'marca': item.get('marca', item.get('brand', '')),
                            'modelo': item.get('modelo', item.get('model', '')),
                            'unidad': item.get('um', item.get('unidad', item.get('unit', 'NIU'))),
                            'cantidad': cantidad,
                            'precio_unitario': precio,
                            'total_item': total_item
                        })
                    elif isinstance(item, (list, tuple)):
                        codigo = item[0] if len(item) > 0 else ''
                        descripcion = item[1] if len(item) > 1 else 'Sin descripción'
                        cantidad = float(item[2] if len(item) > 2 else 1)
                        precio = float(item[3] if len(item) > 3 else 0)
                        total_item = cantidad * precio
                        
                        items_formateados.append({
                            'item': idx,
                            'codigo': codigo,
                            'descripcion': descripcion,
                            'marca': item[4] if len(item) > 4 else '',
                            'modelo': item[5] if len(item) > 5 else '',
                            'unidad': 'NIU',
                            'cantidad': cantidad,
                            'precio_unitario': precio,
                            'total_item': total_item
                        })
                except Exception as e:
                    print(f"❌ Error procesando item {idx}: {e}")
                    continue

            subtotal = float(datos_comprobante.get('subtotal', 0))
            igv = float(datos_comprobante.get('igv', 0))
            total = float(datos_comprobante.get('total', datos_comprobante.get('monto', 0)))
            
            descuento = float(datos_comprobante.get('descuento', 0))
            op_inafecta = float(datos_comprobante.get('op_inafecta', 0))
            op_exonerada = float(datos_comprobante.get('op_exonerada', 0))
            op_gratuita = float(datos_comprobante.get('op_gratuita', 0))
            
            if subtotal == 0 and items_formateados:
                subtotal = sum(item['total_item'] for item in items_formateados)
                igv = subtotal * 0.18
                total = subtotal + igv

            total_letras = self.numero_a_letras(total) + (' DÓLARES AMERICANOS' if self._simbolo(datos_comprobante) == 'US$' else ' SOLES')

            orden_compra_cliente = datos_comprobante.get('orden_compra_cliente', '').strip()
            
            if not orden_compra_cliente:
                orden_compra_cliente = datos_comprobante.get('documento_asociado', '') or '—'
                print(f"📋 Orden de Compra (auto desde documento asociado): {orden_compra_cliente}")
            else:
                print(f"📋 Orden de Compra (manual): {orden_compra_cliente}")
            
            factura = datos_comprobante.get('factura', '—')
            nro_cotizacion = datos_comprobante.get('nro_cotizacion', '—')
            
            if nro_cotizacion == '—':
                nro_cotizacion = (
                    datos_comprobante.get('documento_asociado', '') or
                    datos_comprobante.get('cotizacion', '') or
                    datos_comprobante.get('cotizacion_numero', '') or
                    datos_comprobante.get('numero_cotizacion', '') or
                    '—'
                )

            guia_vinculada = datos_comprobante.get('guia_vinculada', '')
            
            if not guia_vinculada:
                serie_fact = datos_comprobante.get('serie', 'F001')
                numero_fact = datos_comprobante.get('numero', '')
                if numero_fact:
                    guia_vinculada = self._buscar_guia_vinculada(serie_fact, numero_fact)
            
            if not guia_vinculada:
                guia_vinculada = '—'

            qr_base64 = self._generar_qr_comprobante(datos_comprobante)

            tipo_doc = datos_comprobante.get('tipo', datos_comprobante.get('tipo_comprobante', 'Factura'))
            if tipo_doc.lower() == 'factura':
                tipo_doc = 'FACTURA ELECTRÓNICA'
            elif tipo_doc.lower() == 'boleta':
                tipo_doc = 'BOLETA ELECTRÓNICA'

            datos_mapeados = {
                'logo_src': logo_src,
                'empresa_corto': EMPRESA.get('corto', ''),
                'color_empresa': EMPRESA.get('color') or '#CC0000',
                'empresa_ruc': EMPRESA['ruc'],
                'empresa_nombre': EMPRESA['nombre'],
                'empresa_telefono': EMPRESA['telefono'],
                'empresa_email': EMPRESA['email'],
                'empresa_web': EMPRESA['web'],
                'tipo': tipo_doc,
                'serie': datos_comprobante.get('serie', 'F001'),
                'numero': datos_comprobante.get('numero', ''),
                'fecha_emision': self._formatear_fecha(datos_comprobante.get('fecha_emision', datos_comprobante.get('fecha'))),
                'cliente_nombre': datos_comprobante.get('cliente_nombre', datos_comprobante.get('cliente', '')),
                'cliente_ruc': datos_comprobante.get('cliente_ruc', datos_comprobante.get('ruc', '')),
                'cliente_direccion': datos_comprobante.get('cliente_direccion', datos_comprobante.get('direccion', '')),
                'cliente_email': datos_comprobante.get('cliente_email', datos_comprobante.get('email', '')),
                'cliente_telefono': datos_comprobante.get('cliente_telefono', datos_comprobante.get('telefono', '')),
                'moneda': self._simbolo(datos_comprobante),
                'subtotal': f"{subtotal:.2f}",
                'igv': f"{igv:.2f}",
                'total': f"{total:.2f}",
                'total_letras': total_letras,
                'descuento': f"{descuento:.2f}",
                'op_inafecta': f"{op_inafecta:.2f}",
                'op_exonerada': f"{op_exonerada:.2f}",
                'op_gratuita': f"{op_gratuita:.2f}",
                'condicion_pago': datos_comprobante.get('condicion_pago', datos_comprobante.get('condicion', 'Contado')),
                'estado': datos_comprobante.get('estado', 'Borrador'),
                'observaciones': datos_comprobante.get('observaciones', ''),
                'orden_compra_cliente': orden_compra_cliente if orden_compra_cliente else '—',
                'factura': factura if factura else '—',
                'nro_cotizacion': nro_cotizacion if nro_cotizacion else '—',
                'guia_vinculada': guia_vinculada,
                'numero_migo': (datos_comprobante.get('numero_migo') or '').strip(),
                'fecha_vencimiento': datos_comprobante.get('fecha_vencimiento', ''),
                'items': items_formateados,
                'qr_base64': qr_base64
            }

            template_content = self._obtener_template_comprobante()
            html_content = self._reemplazar_variables_template_comprobante(template_content, datos_mapeados)

            fecha = datetime.now().strftime('%Y%m%d_%H%M%S')
            nombre_archivo = f"factura_{datos_mapeados['serie']}_{datos_mapeados['numero']}_{fecha}.pdf"
            
            base_url = f"file://{os.getcwd()}/"
            HTML(string=html_content, base_url=base_url).write_pdf(nombre_archivo)

            print(f"✅ PDF generado: {nombre_archivo}")
            return nombre_archivo

        except Exception as e:
            print(f"❌ Error en _generar_comprobante: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _obtener_template_comprobante(self):
        return """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{{ tipo }} {{ serie }}-{{ numero }}</title>
    <style>
        @page { size: A4; margin: 1.0cm 1.3cm; }
        body { 
            font-family: 'Helvetica', Arial, sans-serif; 
            font-size: 9px; 
            color: #333333;
            line-height: 1.5; 
            background: #ffffff;
        }
        .color-rojo { color: {{ color_empresa }}; }
        .color-gris { color: #555555; }
        .color-gris-oscuro { color: #333333; }
        .header-superior { 
            display: flex; 
            justify-content: space-between; 
            align-items: stretch; 
            margin-bottom: 8px; 
            gap: 18px; 
            border-bottom: 2px solid #999999;
            padding-bottom: 6px;
        }
        .empresa-izquierda { flex: 1; display: flex; align-items: center; gap: 15px; }
        .empresa-izquierda .logo-container { 
            flex-shrink: 0; width: 110px; height: 70px; 
            display: flex; align-items: center; justify-content: center; 
        }
        .empresa-izquierda .logo-container img { 
            max-height: 65px; max-width: 120px; object-fit: contain; 
        }
        .empresa-izquierda .info-texto { font-size: 8px; line-height: 1.4; color: #444444; }
        .empresa-izquierda .info-texto .nombre { 
            font-size: 12px; font-weight: bold; text-transform: uppercase; 
            color: #333333; letter-spacing: 0.5px; margin-bottom: 1px;
        }
        .empresa-izquierda .info-texto .ruc-line {
            font-size: 8.5px; font-weight: bold; color: #333333; margin-bottom: 1px;
        }
        .empresa-izquierda .info-texto .slogan {
            font-size: 7.5px; color: #666666; font-style: italic; margin-bottom: 1px;
        }
        .empresa-izquierda .info-texto .contacto-line {
            font-size: 7px; color: #555555;
        }
        .recuadro-derecha { 
            flex-shrink: 0; border: 2px solid #999999;
            border-radius: 10px; padding: 8px 18px; text-align: center; 
            min-width: 180px; display: flex; flex-direction: column; justify-content: center;
        }
        .recuadro-derecha .ruc { font-size: 9px; font-weight: bold; color: #333333; }
        .recuadro-derecha .titulo { 
            font-size: 12px; font-weight: bold; letter-spacing: 1px; 
            margin: 2px 0; color: {{ color_empresa }};
        }
        .recuadro-derecha .numero { font-size: 14px; font-weight: bold; color: {{ color_empresa }}; }
        .layout-dos-columnas { display: flex; gap: 12px; margin-bottom: 5px; }
        .layout-dos-columnas .columna {
            flex: 1; border: 1px solid #cccccc; border-radius: 5px; padding: 4px 10px;
        }
        .layout-dos-columnas .columna .seccion-titulo {
            font-weight: bold; font-size: 8.5px; margin-bottom: 3px; text-transform: uppercase;
            border-bottom: 1.5px solid #999999; padding-bottom: 1px; color: #333333;
        }
        .layout-dos-columnas .columna .fila {
            display: flex; padding: 0.5px 0; align-items: baseline; font-size: 8px; line-height: 1.35;
        }
        .layout-dos-columnas .columna .fila .label {
            font-weight: bold; min-width: 95px; flex-shrink: 0; color: #555555;
        }
        .layout-dos-columnas .columna .fila .value {
            flex: 1; text-align: left; padding-left: 4px; color: #333333;
        }
        .seccion { margin-bottom: 5px; }
        .seccion-titulo { 
            font-weight: bold; font-size: 9px; margin-bottom: 3px; text-transform: uppercase; 
            border-bottom: 2px solid #999999; padding-bottom: 2px; color: #333333;
        }
        .info-linea-unica {
            display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 14px;
            padding: 5px 10px; border: 1px solid #cccccc; border-radius: 5px;
            background: #ffffff; font-size: 8px; margin-top: 4px; margin-bottom: 4px;
            width: 100%; box-sizing: border-box;
        }
        .info-linea-unica .info-item { display: inline-flex; align-items: baseline; gap: 3px; }
        .info-linea-unica .info-label {
            font-weight: bold; color: #555555; text-transform: uppercase; font-size: 7.5px;
        }
        .info-linea-unica .info-value { font-weight: 600; color: #333333; font-size: 8px; }
        .info-linea-unica .info-titulo {
            font-weight: bold; color: #333333; font-size: 8px; text-transform: uppercase; margin-right: 4px;
        }
        .products-table { width: 100%; border-collapse: collapse; margin: 4px 0; font-size: 8px; }
        .products-table th { 
            color: #333333; padding: 4px 5px; text-align: center; 
            border: 1px solid #cccccc; font-weight: bold; background: #f5f5f5;
        }
        .products-table td { 
            padding: 3px 5px; border: 1px solid #cccccc; 
            text-align: center; color: #333333;
        }
        .products-table td.descripcion { text-align: left; }
        .products-table tr:nth-child(even) td { background: #f9f9f9; }
        .totales-wrapper {
            display: flex; justify-content: space-between; align-items: flex-end;
            margin-top: 6px; gap: 15px;
        }
        .total-letras {
            flex: 1; font-size: 8px; color: #333333; font-style: italic;
            padding-bottom: 6px; line-height: 1.4;
        }
        .total-letras strong { font-style: normal; color: #555555; }
        .totales-box { 
            border: 2px solid #999999; border-radius: 6px; padding: 6px 12px; 
            display: flex; flex-direction: column; align-items: flex-start;
            width: 100%; max-width: 300px; flex-shrink: 0;
        }
        .totales-box .linea {
            display: flex; justify-content: space-between; width: 100%; padding: 1px 0;
            font-size: 7.5px; color: #444444; border-bottom: 1px dotted #e8e8e8;
        }
        .totales-box .linea .label-total {
            font-weight: normal; color: #555555; font-size: 7.5px;
        }
        .totales-box .linea .value-total {
            font-weight: bold; color: #333333; text-align: right; font-size: 7.5px;
        }
        .totales-box .linea.total {
            font-weight: bold; font-size: 11px; border-top: 2px solid #999999;
            border-bottom: none; padding-top: 4px; margin-top: 2px; color: #333333;
        }
        .totales-box .linea.total .label-total { font-weight: bold; font-size: 11px; color: #333333; }
        .totales-box .linea.total .value-total { font-weight: bold; font-size: 14px; color: #333333; }
        .qr-container { 
            text-align: center; margin: 5px 0 3px 0; padding: 4px; 
            border: 2px solid #999999; border-radius: 8px; 
        }
        .qr-container img { width: 75px; height: 75px; }
        .qr-container .qr-text { font-size: 6.5px; color: #888888; margin-top: 2px; }
        .footer { 
            margin-top: 8px; text-align: center; font-size: 7px; 
            color: #888888; padding-top: 4px; 
        }
    </style>
</head>
<body>
    <div class="header-superior">
        <div class="empresa-izquierda">
            <div class="logo-container">{% if logo_src %}<img src="{{ logo_src }}" alt="Logo">{% else %}<div style="font-size:26px;font-weight:900;color:{{ color_empresa }};padding-top:12px;">{{ empresa_corto }}</div>{% endif %}</div>
            <div class="info-texto">
                <div class="nombre">{{ empresa_nombre }}</div>
                <div class="ruc-line">RUC: {{ empresa_ruc }}</div>
                <div class="slogan">Soluciones integrales en abastecimientos</div>
                <div class="contacto-line">Telf: {{ empresa_telefono }} | Email: {{ empresa_email }}</div>
                <div class="contacto-line">Web: {{ empresa_web }}</div>
            </div>
        </div>
        <div class="recuadro-derecha">
            <div class="ruc">RUC Nº {{ empresa_ruc }}</div>
            <div class="titulo">{{ tipo }}</div>
            <div class="numero">{{ serie }}-{{ numero }}</div>
        </div>
    </div>

    <div class="layout-dos-columnas">
        <div class="columna">
            <div class="seccion-titulo">DATOS DEL CLIENTE</div>
            <div class="fila"><span class="label">CLIENTE:</span><span class="value">{{ cliente_nombre }}</span></div>
            <div class="fila"><span class="label">RUC:</span><span class="value">{{ cliente_ruc }}</span></div>
            <div class="fila"><span class="label">DIRECCIÓN:</span><span class="value">{{ cliente_direccion }}</span></div>
            <div class="fila"><span class="label">EMAIL:</span><span class="value">{{ cliente_email }}</span></div>
            <div class="fila"><span class="label">TELÉFONO:</span><span class="value">{{ cliente_telefono }}</span></div>
        </div>
        <div class="columna">
            <div class="seccion-titulo">DATOS DEL COMPROBANTE</div>
            <div class="fila"><span class="label">FECHA EMISIÓN:</span><span class="value">{{ fecha_emision }}</span></div>
            <div class="fila"><span class="label">FECHA VENCIMIENTO:</span><span class="value">{{ fecha_vencimiento or '—' }}</span></div>
            <div class="fila"><span class="label">FORMA DE PAGO:</span><span class="value">{{ condicion_pago }}</span></div>
            <div class="fila"><span class="label">MONEDA:</span><span class="value">{{ moneda }}</span></div>
            <div class="fila"><span class="label">VENDEDOR:</span><span class="value">Hellen Blas Príncipe</span></div>
            <div class="fila"><span class="label">TELÉFONO:</span><span class="value">999932051</span></div>
        </div>
    </div>

    <div class="info-linea-unica">
        <span class="info-titulo">Documentos relacionados:</span>
        <div class="info-item">
            <span class="info-label">PC (PEDIDO DEL CLIENTE):</span>
            <span class="info-value">{{ orden_compra_cliente or '—' }}</span>
        </div>
        <div class="info-item">
            <span class="info-label">GUÍA:</span>
            <span class="info-value">{{ guia_vinculada or '—' }}</span>
        </div>
        <div class="info-item">
            <span class="info-label">COTIZACIÓN:</span>
            <span class="info-value">{{ nro_cotizacion or '—' }}</span>
        </div>
    </div>

    <div class="seccion">
        <div class="seccion-titulo">DETALLE DE PRODUCTOS</div>
        <table class="products-table">
            <thead>
                <tr>
                    <th style="width:5%">Item</th>
                    <th style="width:12%">Código</th>
                    <th style="width:28%">Descripción</th>
                    <th style="width:10%">Modelo</th>
                    <th style="width:10%">Marca</th>
                    <th style="width:6%">Cant.</th>
                    <th style="width:6%">UM</th>
                    <th style="width:11%">Precio Unit.</th>
                    <th style="width:12%">Total</th>
                </tr>
            </thead>
            <tbody>
                {% for item in items %}
                <tr>
                    <td>{{ item.item }}</td>
                    <td>{{ item.codigo }}</td>
                    <td class="descripcion">{{ item.descripcion }}</td>
                    <td>{{ item.modelo }}</td>
                    <td>{{ item.marca }}</td>
                    <td>{{ item.cantidad }}</td>
                    <td>{{ item.unidad }}</td>
                    <td>{{ moneda }} {{ "%.2f"|format(item.precio_unitario) }}</td>
                    <td>{{ moneda }} {{ "%.2f"|format(item.total_item) }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <div class="totales-wrapper">
        <div class="total-letras">
            <strong>SON:</strong> {{ total_letras }}
        </div>
        <div class="totales-box">
            <div class="linea">
                <span class="label-total">OP. GRAVADA</span>
                <span class="value-total">{{ moneda }} {{ subtotal }}</span>
            </div>
            <div class="linea">
                <span class="label-total">IGV (18%)</span>
                <span class="value-total">{{ moneda }} {{ igv }}</span>
            </div>
            <div class="linea">
                <span class="label-total">OP. DESCUENTO</span>
                <span class="value-total">{{ moneda }} {{ descuento }}</span>
            </div>
            <div class="linea">
                <span class="label-total">OP. INAFECTA</span>
                <span class="value-total">{{ moneda }} {{ op_inafecta }}</span>
            </div>
            <div class="linea">
                <span class="label-total">OP. EXONERADA</span>
                <span class="value-total">{{ moneda }} {{ op_exonerada }}</span>
            </div>
            <div class="linea">
                <span class="label-total">TOTAL OP. GRATUITA</span>
                <span class="value-total">{{ moneda }} {{ op_gratuita }}</span>
            </div>
            <div class="linea total">
                <span class="label-total">TOTAL VENTA</span>
                <span class="value-total">{{ moneda }} {{ total }}</span>
            </div>
        </div>
    </div>

    {% if observaciones %}
    <div class="info-linea-unica" style="margin-top: 6px;">
        <div class="info-item">
            <span class="info-label">Observaciones:</span>
            <span class="info-value">{{ observaciones }}</span>
        </div>
    </div>
    {% endif %}

    <div class="qr-container">
        <img src="{{ qr_base64 }}" alt="QR">
        <div class="qr-text">Representación impresa del {{ tipo }}</div>
    </div>

    <div class="footer">
        <div>Pag. 1 de 1</div>
        <div>Powered by {{ empresa_corto or 'KCF' }}</div>
    </div>
</body>
</html>"""

    def _reemplazar_variables_template_comprobante(self, template, datos):
        try:
            return Template(template).render(**datos)
        except Exception as e:
            print(f"❌ Error renderizando template Jinja2 de comprobante: {e}")
            html = template
            
            variables = {
                'logo_src': datos.get('logo_src', ''),
                'empresa_ruc': '20602095704',
                'empresa_nombre': 'KCF CORPORACION E.I.R.L',
                'empresa_telefono': '999 932 051',
                'empresa_email': 'ventas@kcfcorporacion.com',
                'empresa_web': 'https://kcfcorporacion.com/',
                'tipo': datos.get('tipo', 'FACTURA ELECTRÓNICA'),
                'serie': datos.get('serie', 'F001'),
                'numero': datos.get('numero', ''),
                'fecha_emision': datos.get('fecha_emision', ''),
                'cliente_nombre': datos.get('cliente_nombre', ''),
                'cliente_ruc': datos.get('cliente_ruc', ''),
                'cliente_direccion': datos.get('cliente_direccion', ''),
                'cliente_email': datos.get('cliente_email', ''),
                'cliente_telefono': datos.get('cliente_telefono', ''),
                'moneda': self._simbolo(datos),
                'subtotal': datos.get('subtotal', '0.00'),
                'igv': datos.get('igv', '0.00'),
                'total': datos.get('total', '0.00'),
                'total_letras': datos.get('total_letras', ''),
                'descuento': datos.get('descuento', '0.00'),
                'op_inafecta': datos.get('op_inafecta', '0.00'),
                'op_exonerada': datos.get('op_exonerada', '0.00'),
                'op_gratuita': datos.get('op_gratuita', '0.00'),
                'condicion_pago': datos.get('condicion_pago', 'Contado'),
                'estado': datos.get('estado', 'Borrador'),
                'observaciones': datos.get('observaciones', ''),
                'orden_compra_cliente': datos.get('orden_compra_cliente', '—'),
                'factura': datos.get('factura', '—'),
                'nro_cotizacion': datos.get('nro_cotizacion', '—'),
                'guia_vinculada': datos.get('guia_vinculada', '—'),
                'fecha_vencimiento': datos.get('fecha_vencimiento', ''),
                'qr_base64': datos.get('qr_base64', ''),
            }
            
            for key, value in variables.items():
                html = html.replace(f"{{{{ {key} }}}}", str(value))
            
            items_html = ""
            for item in datos.get('items', []):
                items_html += f"""
                <tr>
                    <td>{item.get('item', '')}</td>
                    <td>{item.get('codigo', '')}</td>
                    <td class="descripcion">{item.get('descripcion', '')}</td>
                    <td>{item.get('modelo', '')}</td>
                    <td>{item.get('marca', '')}</td>
                    <td>{item.get('cantidad', 0)}</td>
                    <td>{item.get('unidad', 'NIU')}</td>
                    <td>{item.get('precio_unitario', 0):.2f}</td>
                    <td>{item.get('total_item', 0):.2f}</td>
                </tr>
                """
            html = html.replace("{% for item in items %}", items_html)
            html = html.replace("{% endfor %}", "")
            
            html = re.sub(r'{%.*?%}', '', html, flags=re.DOTALL)
            html = re.sub(r'{{.*?}}', '', html, flags=re.DOTALL)
            
            return html

    def _generar_qr_comprobante(self, datos_comprobante):
        try:
            import qrcode
            from io import BytesIO
            
            qr_data = {
                'tipo': datos_comprobante.get('tipo', 'FACTURA'),
                'serie': datos_comprobante.get('serie', 'F001'),
                'numero': datos_comprobante.get('numero', ''),
                'ruc_emisor': (datos_comprobante.get('empresa_pdf') or {}).get('ruc') or '20602095704',
                'ruc_cliente': datos_comprobante.get('ruc', ''),
                'fecha_emision': self._formatear_fecha(datos_comprobante.get('fecha_emision')),
                'total': str(datos_comprobante.get('total', 0))
            }
            
            qr = qrcode.QRCode(version=2, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=4, border=2)
            qr.add_data(json.dumps(qr_data))
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode()
            return f"data:image/png;base64,{img_base64}"
        except:
            return ""

    def _formatear_fecha(self, fecha):
        if not fecha:
            return datetime.now().strftime('%d/%m/%Y')
        try:
            if isinstance(fecha, str):
                if '/' in fecha:
                    return fecha
                dt = datetime.fromisoformat(fecha.replace('Z', '+00:00'))
                return dt.strftime('%d/%m/%Y')
            elif isinstance(fecha, datetime):
                return fecha.strftime('%d/%m/%Y')
            return str(fecha)
        except:
            return str(fecha)

    # ============================================================
    # GUÍA DE REMISIÓN
    # ============================================================
    def _generar_guia_remision(self, datos_guia):
        try:
            print("📄 Generando PDF de Guía de Remisión...")
            
            datos_mapeados = self._mapear_datos_guia(datos_guia)
            template_content = self._obtener_template_guia()
            filas_productos = self._generar_filas_productos_guia(datos_mapeados.get('items', []))
            datos_mapeados['filas_productos'] = filas_productos
            html_content = self._reemplazar_variables_template_guia(template_content, datos_mapeados)
            
            fecha = datetime.now().strftime('%Y%m%d_%H%M%S')
            pdf_file = f"guia_{datos_mapeados.get('serie', 'T001')}_{datos_mapeados.get('numero', 'sin_numero')}_{fecha}.pdf"
            
            base_url = f"file://{os.getcwd()}/"
            HTML(string=html_content, base_url=base_url).write_pdf(pdf_file)
            
            print(f"✅ PDF generado: {pdf_file}")
            return pdf_file
        except Exception as e:
            print(f"❌ Error en _generar_guia_remision: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _obtener_template_guia(self):
        return """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Guía de Remisión {{ serie }}-{{ numero }}</title>
    <style>
        @page { size: A4; margin: 1.3cm 1.5cm; }
        body { 
            font-family: 'Helvetica', Arial, sans-serif; 
            font-size: 9px; 
            color: #333333;
            line-height: 1.5; 
            margin-top: 10px;
            background: #ffffff;
        }
        .header-superior { 
            display: flex; justify-content: space-between; align-items: stretch; 
            margin-bottom: 10px; gap: 18px; padding-top: 5px;
            border-bottom: 1px solid #999999; padding-bottom: 6px;
        }
        .empresa-izquierda { flex: 1; display: flex; align-items: center; gap: 15px; }
        .empresa-izquierda .logo-container { 
            flex-shrink: 0; width: 110px; height: 70px; 
            display: flex; align-items: center; justify-content: center; 
        }
        .empresa-izquierda .logo-container img { 
            max-height: 65px; max-width: 120px; object-fit: contain; 
        }
        .empresa-izquierda .info-texto { font-size: 8px; line-height: 1.4; color: #444444; }
        .empresa-izquierda .info-texto .nombre { 
            font-size: 12px; font-weight: bold; text-transform: uppercase; 
            color: #000000; letter-spacing: 0.5px; margin-bottom: 1px;
        }
        .empresa-izquierda .info-texto .ruc-line {
            font-size: 8.5px; font-weight: bold; color: #333333; margin-bottom: 1px;
        }
        .empresa-izquierda .info-texto .slogan {
            font-size: 7.5px; color: #666666; font-style: italic; margin-bottom: 1px;
        }
        .empresa-izquierda .info-texto .contacto-line { font-size: 7px; color: #555555; }
        .recuadro-derecha { 
            flex-shrink: 0; border: 1px solid #999999; border-radius: 4px; 
            padding: 6px 16px; text-align: center; min-width: 170px; 
            display: flex; flex-direction: column; justify-content: center;
        }
        .recuadro-derecha .ruc { font-size: 9px; font-weight: bold; color: #333333; }
        .recuadro-derecha .titulo { 
            font-size: 10px; font-weight: bold; letter-spacing: 0.5px; 
            margin: 2px 0; color: #000000;
        }
        .recuadro-derecha .numero { 
            font-size: 15px; font-weight: bold; color: {{ color_empresa }}; letter-spacing: 1px;
        }
        .seccion { margin-bottom: 5px; }
        .seccion-con-borde {
            border: 1px solid #cccccc; border-radius: 4px; padding: 0; 
            margin-bottom: 4px; overflow: hidden;
        }
        .seccion-con-borde .seccion-titulo {
            font-weight: bold; font-size: 8px; text-transform: uppercase; 
            color: #000000; padding: 2px 10px; margin: 0; 
            border-bottom: 1px solid #cccccc; letter-spacing: 0.3px; background: #f5f5f5;
        }
        .seccion-con-borde .seccion-contenido {
            padding: 3px 10px; background: #ffffff;
        }
        .fila { 
            display: flex; padding: 0.5px 0; align-items: baseline; font-size: 8px;
        }
        .fila .label { 
            font-weight: bold; min-width: 190px; flex-shrink: 0; color: #555555;
        }
        .fila .value { 
            flex: 1; text-align: left; padding-left: 5px; color: #333333;
        }
        .products-table { 
            width: 100%; border-collapse: collapse; margin: 3px 0; font-size: 7.5px; 
        }
        .products-table th { 
            color: #000000; padding: 3px 5px; text-align: center; 
            border: 1px solid #cccccc; font-weight: bold; background: #f5f5f5;
        }
        .products-table td { 
            padding: 2px 5px; border: 1px solid #cccccc; 
            text-align: center; color: #333333;
        }
        .products-table td.descripcion { text-align: left; }
        .products-table tr:nth-child(even) td { background: #f9f9f9; }
        .qr-container { 
            text-align: center; margin: 6px 0 4px 0; padding: 5px; 
            border: 1px solid #999999; border-radius: 4px; 
        }
        .qr-container img { width: 75px; height: 75px; }
        .qr-container .qr-text { font-size: 6.5px; color: #666666; margin-top: 2px; }
        .footer { 
            margin-top: 10px; text-align: center; font-size: 7px; 
            color: #888888; padding-top: 5px; 
        }
        .info-linea-unica {
            display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 14px;
            padding: 5px 10px; border: 1px solid #cccccc; border-radius: 4px;
            background: #ffffff; font-size: 8px; margin-bottom: 4px; 
            width: 100%; box-sizing: border-box;
        }
        .info-linea-unica .info-item { display: inline-flex; align-items: baseline; gap: 3px; }
        .info-linea-unica .info-label {
            font-weight: bold; color: #555555; text-transform: uppercase; font-size: 7.5px;
        }
        .info-linea-unica .info-value { font-weight: 600; color: #333333; font-size: 8px; }
        .info-linea-unica .info-titulo {
            font-weight: bold; color: #333333; font-size: 8px; 
            text-transform: uppercase; margin-right: 4px;
        }
    </style>
</head>
<body>
    <div class="header-superior">
        <div class="empresa-izquierda">
            <div class="logo-container">{% if logo_src %}<img src="{{ logo_src }}" alt="Logo" style="max-height:65px;">{% else %}<div style="font-size:26px;font-weight:900;color:{{ color_empresa }};padding-top:12px;">{{ empresa_corto }}</div>{% endif %}</div>
            <div class="info-texto">
                <div class="nombre">{{ remitente_nombre }}</div>
                <div class="ruc-line">RUC: {{ ruc_remitente }}</div>
                <div class="slogan">Soluciones integrales en abastecimientos</div>
                <div class="contacto-line">Telf: {{ telefono }} | Email: {{ email }}</div>
                <div class="contacto-line">Web: {{ web }}</div>
            </div>
        </div>
        <div class="recuadro-derecha">
            <div class="ruc">RUC Nº {{ ruc_remitente }}</div>
            <div class="titulo" style="color: {{ color_empresa }};">GUIA DE REMISIÓN REMITENTE</div>
            <div class="numero">{{ serie }}-{{ numero }}</div>
        </div>
    </div>
    
    <div class="seccion seccion-con-borde">
        <div class="seccion-titulo">DESTINATARIO</div>
        <div class="seccion-contenido">
            <div class="fila"><span class="label">RUC.:</span><span class="value">{{ ruc_destinatario }}</span></div>
            <div class="fila"><span class="label">DENOMINACIÓN:</span><span class="value">{{ destinatario_nombre }}</span></div>
        </div>
    </div>
    
    <div class="seccion seccion-con-borde">
        <div class="seccion-titulo">DATOS DEL TRASLADO</div>
        <div class="seccion-contenido">
            <div class="fila"><span class="label">FECHA EMISIÓN:</span><span class="value">{{ fecha_emision }}</span></div>
            <div class="fila"><span class="label">FECHA INICIO TRASLADO:</span><span class="value">{{ fecha_inicio_traslado }}</span></div>
            <div class="fila"><span class="label">MOTIVO DE TRASLADO:</span><span class="value">{{ motivo_texto }}</span></div>
            <div class="fila"><span class="label">MODALIDAD DE TRANSPORTE:</span><span class="value">{{ modalidad_texto }}</span></div>
            <div class="fila"><span class="label">PESO BRUTO TOTAL (KGM):</span><span class="value">{{ peso_bruto_total }}</span></div>
            <div class="fila"><span class="label">NÚMERO DE BULTOS:</span><span class="value">{{ numero_bultos }}</span></div>
        </div>
    </div>
    
    <div class="seccion seccion-con-borde">
        <div class="seccion-titulo">DATOS DE RUTA</div>
        <div class="seccion-contenido">
            <div class="fila">
                <span class="label">PUNTO DE PARTIDA:</span>
                <span class="value">{{ remitente_direccion }}</span>
            </div>
            <div class="fila">
                <span class="label">PUNTO DE LLEGADA:</span>
                <span class="value">{{ destinatario_direccion }}</span>
            </div>
        </div>
    </div>
    
    <div class="seccion seccion-con-borde">
        <div class="seccion-titulo">DATOS DEL TRANSPORTE</div>
        <div class="seccion-contenido">
            <div class="fila"><span class="label">TRANSPORTISTA:</span><span class="value">{{ transportista_nombre }}</span></div>
            <div class="fila"><span class="label">CONDUCTOR:</span><span class="value">{{ conductor_nombre }}</span></div>
            <div class="fila"><span class="label">DNI:</span><span class="value">{{ conductor_dni }}</span></div>
            <div class="fila"><span class="label">PLACA:</span><span class="value">{{ placa_vehiculo }}</span></div>
            <div class="fila"><span class="label">LICENCIA:</span><span class="value">{{ licencia_conductor }}</span></div>
        </div>
    </div>
    
    <div class="seccion seccion-con-borde">
        <div class="seccion-titulo">PRODUCTOS</div>
        <div class="seccion-contenido" style="padding: 3px 6px;">
            <table class="products-table">
                <thead><tr><th style="width:8%">ITEM</th><th style="width:15%">CODIGO</th><th style="width:40%">PRODUCTO</th><th style="width:15%">UM</th><th style="width:15%">CANTIDAD</th></tr></thead>
                <tbody>{{ filas_productos }}</tbody>
            </table>
        </div>
    </div>
    
    <div class="info-linea-unica">
        <span class="info-titulo">Documentos relacionados:</span>
        <div class="info-item">
            <span class="info-label">PC (PEDIDO DEL CLIENTE):</span>
            <span class="info-value">{{ orden_compra_cliente or '—' }}</span>
        </div>
        <div class="info-item">
            <span class="info-label">FACTURA:</span>
            <span class="info-value">{{ factura or '—' }}</span>
        </div>
        <div class="info-item">
            <span class="info-label">COTIZACIÓN:</span>
            <span class="info-value">{{ nro_cotizacion or '—' }}</span>
        </div>
        <div class="info-item">
            <span class="info-label">Observaciones:</span>
            <span class="info-value">{{ observaciones or '—' }}</span>
        </div>
    </div>
    
    <div class="qr-container">
        <img src="{{ qr_base64 }}" alt="QR">
        <div class="qr-text">Representación impresa de la GUIA DE REMISIÓN REMITENTE ELECTRÓNICA</div>
    </div>
    
    <div class="footer">
        <div>Pag. 1 de 1</div>
        <div>Powered by {{ empresa_corto or 'KCF' }}</div>
    </div>
</body>
</html>"""

    def _mapear_datos_guia(self, datos_guia):
        EMPRESA = self._emisora(datos_guia)
        logo_src = EMPRESA.get('logo_src', '')
        
        items = datos_guia.get('items', [])
        if isinstance(items, str):
            try:
                items = json.loads(items)
            except:
                items = []
        
        items_formateados = []
        for idx, item in enumerate(items, 1):
            if isinstance(item, dict):
                items_formateados.append({
                    'item': idx,
                    'codigo': item.get('codigo', ''),
                    'descripcion': (item.get('descripcion_cliente') or '').strip() or item.get('producto', item.get('descripcion', '')),
                    'unidad': item.get('um', 'NIU'),
                    'cantidad': float(item.get('cantidad', 1))
                })
            elif isinstance(item, (list, tuple)):
                items_formateados.append({
                    'item': idx,
                    'codigo': item[0] if len(item) > 0 else '',
                    'descripcion': item[1] if len(item) > 1 else '',
                    'unidad': 'NIU',
                    'cantidad': float(item[2] if len(item) > 2 else 1)
                })
        
        peso_total = float(datos_guia.get('peso_total', 0))
        if peso_total == 0 and items_formateados:
            peso_total = sum(float(item['cantidad']) * 0.5 for item in items_formateados)
        
        return {
            'logo_src': logo_src,
            'empresa_corto': EMPRESA.get('corto', ''),
            'color_empresa': EMPRESA.get('color') or '#CC0000',
            'ruc_remitente': datos_guia.get('ruc_remitente', EMPRESA['ruc']),
            'remitente_nombre': datos_guia.get('remitente_nombre', EMPRESA['nombre']),
            'remitente_direccion': datos_guia.get('remitente_direccion', EMPRESA['direccion']),
            'remitente_ubigeo': datos_guia.get('remitente_ubigeo', '150101'),
            'telefono': EMPRESA['telefono'],
            'email': EMPRESA['email'],
            'web': EMPRESA.get('web', ''),
            'ruc_destinatario': datos_guia.get('ruc_destinatario', datos_guia.get('ruc', '')),
            'destinatario_nombre': datos_guia.get('destinatario_nombre', datos_guia.get('cliente', '')),
            'destinatario_direccion': datos_guia.get('destinatario_direccion', datos_guia.get('destino', '')),
            'destinatario_ubigeo': datos_guia.get('destinatario_ubigeo', '150101'),
            'serie': datos_guia.get('serie', 'T001'),
            'numero': datos_guia.get('numero', ''),
            'fecha_emision': self._formatear_fecha(datos_guia.get('fecha_emision')),
            'fecha_traslado': self._formatear_fecha(datos_guia.get('fecha_traslado')),
            'fecha_inicio_traslado': self._formatear_fecha(datos_guia.get('fecha_inicio_traslado')),
            'motivo_traslado': datos_guia.get('motivo_traslado', '01'),
            'motivo_texto': self._get_motivo_texto(datos_guia.get('motivo_traslado', '01')),
            'modalidad_transporte': datos_guia.get('modalidad_transporte', 'PRIVADO'),
            'modalidad_texto': 'Transporte privado' if datos_guia.get('modalidad_transporte') == 'PRIVADO' else 'Transporte público',
            'peso_bruto_total': f"{peso_total:.1f}",
            'numero_bultos': datos_guia.get('numero_bultos', 1),
            'unidad_peso_texto': 'KGM',
            'transportista_nombre': datos_guia.get('transportista_nombre', '---'),
            'conductor_nombre': datos_guia.get('conductor_nombre', '---'),
            'conductor_dni': datos_guia.get('conductor_dni', '---'),
            'placa_vehiculo': datos_guia.get('placa_vehiculo', '---'),
            'licencia_conductor': datos_guia.get('licencia_conductor', '---'),
            'orden_compra_cliente': datos_guia.get('orden_compra_cliente', ''),
            'factura': datos_guia.get('factura', ''),
            'nro_cotizacion': datos_guia.get('nro_cotizacion', datos_guia.get('documento_asociado', '')),
            'items': items_formateados,
            'observaciones': datos_guia.get('observaciones', ''),
            'qr_base64': self._generar_qr_guia(datos_guia)
        }

    def _generar_qr_guia(self, datos_guia):
        try:
            import qrcode
            from io import BytesIO
            qr_data = {
                'serie': datos_guia.get('serie', ''),
                'numero': datos_guia.get('numero', ''),
                'ruc_remitente': datos_guia.get('ruc_remitente', ''),
                'ruc_destinatario': datos_guia.get('ruc_destinatario', ''),
                'fecha_emision': self._formatear_fecha(datos_guia.get('fecha_emision')),
                'total_peso': str(datos_guia.get('peso_total', 0))
            }
            qr = qrcode.QRCode(version=2, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=4, border=2)
            qr.add_data(json.dumps(qr_data))
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode()
            return f"data:image/png;base64,{img_base64}"
        except:
            return ""

    def _generar_filas_productos_guia(self, productos):
        filas = ""
        for prod in productos:
            filas += f"""<tr><td>{prod.get('item', '')}</td><td>{prod.get('codigo', '')}</td><td class="descripcion">{prod.get('descripcion', '')}</td><td>{prod.get('unidad', 'NIU')}</td><td>{prod.get('cantidad', 0)}</td></tr>"""
        return filas

    def _reemplazar_variables_template_guia(self, template, datos):
        try:
            return Template(template).render(**datos)
        except Exception as e:
            print(f"❌ Error renderizando template Jinja2 de guía: {e}")
            return template

    def _get_motivo_texto(self, codigo):
        motivos = {
            '01': 'Venta', '02': 'Compra', '03': 'Traslado entre establecimientos',
            '04': 'Consignación', '05': 'Devolución', '06': 'Exportación',
            '07': 'Importación', '08': 'Donación', '09': 'Traslado por cuenta de terceros'
        }
        return motivos.get(codigo, codigo or 'Venta')

    # ============================================================
    # GENERAR RÓTULO DE GUÍA DE REMISIÓN (DISEÑO ROJO)
    # ============================================================
    def _generar_rotulo_guia(self, datos_guia):
        """Genera el PDF del rótulo para pegar en el paquete/mercadería"""
        try:
            print("📄 Generando PDF de Rótulo de Guía de Remisión...")
            
            # Empresa dueña del documento (multiempresa). Sin datos: KCF como antes.
            emp = datos_guia.get('empresa') or {}
            if emp:
                logo_src = emp.get('logo_src') or ""
            else:
                logo_base64 = self._obtener_logo_base64()
                logo_src = f"data:image/png;base64,{logo_base64}" if logo_base64 else ""
            
            # Procesar items
            items = datos_guia.get('items', [])
            if isinstance(items, str):
                try:
                    items = json.loads(items)
                except:
                    items = []
            
            items_formateados = []
            for item in items:
                if isinstance(item, dict):
                    items_formateados.append({
                        'codigo': item.get('codigo', ''),
                        'descripcion': (item.get('descripcion_cliente') or '').strip() or item.get('producto', item.get('descripcion', '')),
                        'marca': item.get('marca', ''),
                        'modelo': item.get('modelo', ''),
                        'unidad': item.get('um', 'NIU'),
                        'cantidad': float(item.get('cantidad', 1))
                    })
                elif isinstance(item, (list, tuple)):
                    items_formateados.append({
                        'codigo': item[0] if len(item) > 0 else '',
                        'descripcion': item[1] if len(item) > 1 else '',
                        'marca': item[2] if len(item) > 2 else '',
                        'modelo': item[3] if len(item) > 3 else '',
                        'unidad': 'NIU',
                        'cantidad': float(item[4] if len(item) > 4 else 1)
                    })
            
            # Formatear fecha
            fecha_emision = datos_guia.get('fecha_emision')
            if fecha_emision:
                if isinstance(fecha_emision, datetime):
                    fecha_emision = fecha_emision.strftime('%d/%m/%Y')
                elif isinstance(fecha_emision, str):
                    try:
                        if 'T' in fecha_emision:
                            dt = datetime.fromisoformat(fecha_emision.replace('Z', '+00:00'))
                            fecha_emision = dt.strftime('%d/%m/%Y')
                        elif '-' in fecha_emision and len(fecha_emision) >= 10:
                            fecha_emision = datetime.strptime(fecha_emision[:10], '%Y-%m-%d').strftime('%d/%m/%Y')
                    except:
                        pass
            

         
                            # ============================================================
            # DATOS PARA EL TEMPLATE DEL RÓTULO
            # ============================================================
            # Consignado = Conductor de la guía (mismo campo que usa el PDF de guías)
            consignado_nombre = (
                datos_guia.get('conductor_nombre') 
                or datos_guia.get('transportista_nombre')
                or '—'
            )
            consignado_dni = (
                datos_guia.get('conductor_dni')
                or datos_guia.get('transportista_ruc')
                or '—'
            )
            
            # N° Factura vinculada
            factura_numero = (
                datos_guia.get('factura')
                or datos_guia.get('factura_numero')
                or datos_guia.get('numero_factura')
                or '—'
            )
            
            # N° BLTS: formato 01/02
            num_bultos = int(datos_guia.get('numero_bultos', 1) or 1)
            total_bultos = int(datos_guia.get('total_bultos', num_bultos) or num_bultos)
            bultos_formato = f"{str(num_bultos).zfill(2)}/{str(total_bultos).zfill(2)}"
            
            print(f"📦 Rótulo - Consignado: {consignado_nombre} | DNI: {consignado_dni}")
            print(f"📦 Rótulo - Factura: {factura_numero} | Bultos: {bultos_formato}")
            
            datos_rotulo = {
                'logo_src': logo_src,
                # Nombre en una línea, sin E.I.R.L. / S.A.C. (Erika 22/10/2026: "debería ser KCF Corporación")
                'empresa_nombre': self._nombre_rotulo(emp.get('nombre_comercial') or emp.get('razon_social') or 'KCF CORPORACION E.I.R.L'),
                'empresa_corto': emp.get('codigo') or emp.get('nombre_corto') or 'KCF',
                'empresa_ruc': emp.get('ruc') or '20602095704',
                'empresa_telefono': emp.get('telefono') or ('' if emp else '999 932 051'),
                'empresa_email': (emp.get('correo_rotulo') or emp.get('correo_documentos')) if emp else 'ventas@kcfcorporacion.com',
                'empresa_web': emp.get('pagina_web') if emp else 'https://kcfcorporacion.com/',
                'color': emp.get('color_primario') or '#CC0000',
                # Rótulo de PV o despacho: el documento que se muestra en lugar del N° de guía
                'doc_label': datos_guia.get('doc_label') or 'N° GUÍA:',
                'doc_valor': datos_guia.get('doc_valor') or f"{datos_guia.get('serie', 'T001')}-{datos_guia.get('numero', '')}",
                'serie': datos_guia.get('serie', 'T001'),
                'numero': datos_guia.get('numero', ''),
                'fecha_emision': fecha_emision or '',
                'cliente_nombre': datos_guia.get('destinatario_nombre', datos_guia.get('cliente', '')),
                'cliente_ruc': datos_guia.get('ruc_destinatario', datos_guia.get('ruc', '')),
                'cliente_direccion': datos_guia.get('destinatario_direccion', datos_guia.get('destino', '')),
                # 🔽 CONSIGNADO
                'consignado_nombre': consignado_nombre,
                'consignado_dni': consignado_dni,
                # 🔽 FACTURA
                'factura': factura_numero,
                # Los 4 números (Erika 22/10/2026): despacho, PV, guía y factura; "—" si falta
                'nro_despacho': datos_guia.get('nro_despacho') or '—',
                'nro_pc': datos_guia.get('nro_pc') or '—',
                'nro_guia': datos_guia.get('nro_guia') or (f"{datos_guia.get('serie')}-{datos_guia.get('numero')}" if datos_guia.get('serie') else '—'),
                'nro_factura': datos_guia.get('nro_factura') or factura_numero or '—',
                # 🔽 BLTS
                'numero_bultos': bultos_formato,
                # Extras
                'orden_compra': datos_guia.get('orden_compra_cliente', '—'),
                'cotizacion': datos_guia.get('documento_asociado', datos_guia.get('nro_cotizacion', '—')),
                'transportista': datos_guia.get('transportista_nombre', '—'),
                'conductor': consignado_nombre,
                'placa': datos_guia.get('placa_vehiculo', '—'),
                'peso_total': datos_guia.get('peso_total', 0),
                'bultos': num_bultos,
                'observaciones': datos_guia.get('observaciones', ''),
                'items': items_formateados,
                'total_items': len(items_formateados),
                'qr_base64': self._generar_qr_rotulo_guia(datos_guia)
            }

            # Generar HTML del rótulo
            plantilla = self._obtener_template_rotulo_guia()
            
            # Generar PDF
            fecha = datetime.now().strftime('%Y%m%d_%H%M%S')
            nombre_archivo = f"rotulo_{datos_rotulo['serie']}_{datos_rotulo['numero']}_{fecha}.pdf"
            
            base_url = f"file://{os.getcwd()}/"
            if datos_guia.get('una_hoja_por_bulto') and total_bultos > 1:
                # Una hoja por bulto: 01/03, 02/03, 03/03 (para pegar una en cada caja)
                primero, paginas = None, []
                for k in range(1, total_bultos + 1):
                    datos_rotulo['numero_bultos'] = f"{str(k).zfill(2)}/{str(total_bultos).zfill(2)}"
                    doc = HTML(string=Template(plantilla).render(**datos_rotulo), base_url=base_url).render()
                    primero = primero or doc
                    paginas.extend(doc.pages)
                primero.copy(paginas).write_pdf(nombre_archivo)
            else:
                try:
                    html_content = Template(plantilla).render(**datos_rotulo)
                except Exception as e:
                    print(f"❌ Error renderizando template de rótulo: {e}")
                    html_content = plantilla
                HTML(string=html_content, base_url=base_url).write_pdf(nombre_archivo)
            
            print(f"✅ Rótulo generado: {nombre_archivo}")
            return nombre_archivo
            
        except Exception as e:
            print(f"❌ Error en _generar_rotulo_guia: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _generar_qr_rotulo_guia(self, datos_guia):
        """Genera un QR simple para el rótulo con datos de la guía"""
        try:
            import qrcode
            from io import BytesIO
            
            qr_data = {
                'guia': f"{datos_guia.get('serie', '')}-{datos_guia.get('numero', '')}",
                'cliente': datos_guia.get('destinatario_nombre', ''),
                'ruc': datos_guia.get('ruc_destinatario', ''),
                'factura': datos_guia.get('factura', ''),
                'fecha': str(datos_guia.get('fecha_emision', ''))
            }
            
            qr = qrcode.QRCode(
                version=2,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=6,
                border=1
            )
            qr.add_data(json.dumps(qr_data))
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode()
            return f"data:image/png;base64,{img_base64}"
        except Exception as e:
            print(f"⚠️ Error generando QR de rótulo: {e}")
            return ""

    @staticmethod
    def _nombre_rotulo(nombre):
        n = re.sub(r'[\s,.]*\b(E\.?\s?I\.?\s?R\.?\s?L|S\.?\s?A\.?\s?C|S\.?\s?R\.?\s?L|S\.?\s?A\.?\s?A|S\.?\s?A)\.?\s*$', '',
                   str(nombre or '').strip(), flags=re.I).strip()
        n = (n or str(nombre or '')).upper()
        return re.sub(r'\bCORPORACION\b', 'CORPORACIÓN', n)

    def _obtener_template_rotulo_guia(self):
        """Template HTML para el rótulo de guía de remisión (A5 horizontal - diseño ROJO)"""
        return """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Rótulo {{ serie }}-{{ numero }}</title>
    <style>
        @page { 
            size: A5 landscape; 
            margin: 0.4cm; 
        }
        * { 
            margin: 0; 
            padding: 0; 
            box-sizing: border-box; 
        }
        body { 
            font-family: 'Helvetica', Arial, sans-serif; 
            font-size: 9px; 
            color: #1a1a1a;
            background: #ffffff;
            line-height: 1.25;
        }
        
        .rotulo-wrapper {
            border: 3px solid {{ color }};
            border-radius: 6px;
            padding: 10px 12px;
            background: #ffffff;
            height: calc(148mm - 0.8cm - 6px);
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        
        /* ===== HEADER ===== */
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
            gap: 10px;
        }
        .header-left {
            display: flex;
            align-items: center;
            gap: 10px;
            flex-shrink: 0;
        }
        .header-left .logo {
            width: 65px;
            height: 55px;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }
        .header-left .logo img {
            max-height: 55px;
            max-width: 65px;
            object-fit: contain;
        }
        .header-left .empresa-info {
            line-height: 1.15;
        }
        .header-left .empresa-info .nombre {
            font-size: 20px;
            font-weight: 900;
            color: #1a1a1a;
            letter-spacing: 0.2px;
            text-transform: uppercase;
            white-space: nowrap;
        }
        .header-left .empresa-info .ruc {
            font-size: 12px;
            font-weight: 800;
            color: #1a1a1a;
        }
        
        .header-center {
            display: flex;
            align-items: center;
            gap: 6px;
            flex-shrink: 0;
        }
        .social-icon {
            width: 24px;
            height: 24px;
            border-radius: 50%;
            background: #1a1a1a;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }
        .social-icon svg {
            width: 12px;
            height: 12px;
            fill: #ffffff;
        }
        
        /* 🔽 QR CORREGIDO - tamaño fijo y centrado */
        .header-right {
            flex-shrink: 0;
            display: flex;
            align-items: center;
            justify-content: flex-end;
        }
        .qr-box {
            width: 60px;
            height: 60px;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
        }
        .qr-box img {
            width: 60px;
            height: 60px;
            display: block;
            object-fit: contain;
        }
        
        /* ===== SECCIONES ===== */
        .seccion-cliente {
            border: 2px solid {{ color }};
            border-radius: 8px;
            padding: 5px 12px;
            margin-bottom: 6px;
            display: flex;
            align-items: center;
            gap: 8px;
            min-height: 34px;
        }
        .seccion-cliente .label {
            font-size: 15px;
            font-weight: 900;
            color: #1a1a1a;
            text-transform: uppercase;
            flex-shrink: 0;
        }
        .seccion-cliente .valor {
            font-size: 15px;
            font-weight: 600;
            color: #1a1a1a;
            flex: 1;
        }
        
        .seccion-direccion {
            border: 2px solid {{ color }};
            border-radius: 8px;
            padding: 5px 12px;
            margin-bottom: 6px;
            display: flex;
            align-items: center;
            gap: 8px;
            min-height: 44px;
        }
        .seccion-direccion .label {
            font-size: 15px;
            font-weight: 900;
            color: #1a1a1a;
            text-transform: uppercase;
            line-height: 1.05;
            flex-shrink: 0;
        }
        .seccion-direccion .valor {
            font-size: 15px;
            font-weight: 600;
            color: #1a1a1a;
            flex: 1;
            line-height: 1.15;
        }
        
        .seccion-doble {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 6px;
            margin-bottom: 6px;
        }
        .caja-consignados {
            border: 2px solid {{ color }};
            border-radius: 8px;
            padding: 4px 12px;
            display: flex;
            align-items: center;
            gap: 8px;
            min-height: 44px;
        }
        .caja-consignados .label {
            font-size: 14px;
            font-weight: 900;
            color: #1a1a1a;
            text-transform: uppercase;
            flex-shrink: 0;
        }
        .caja-consignados .datos {
            flex: 1;
            line-height: 1.2;
        }
        .caja-consignados .datos .nombre {
            font-size: 19px;
            font-weight: 900;
            color: #1a1a1a;
        }
        .caja-consignados .datos .dni {
            font-size: 12px;
            font-weight: 600;
            color: #1a1a1a;
        }
        
        .caja-blts {
            border: 2px solid {{ color }};
            border-radius: 8px;
            padding: 4px 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            min-height: 44px;
        }
        .caja-blts .label {
            font-size: 16px;
            font-weight: 900;
            color: #1a1a1a;
            text-transform: uppercase;
        }
        .caja-blts .valor {
            font-size: 30px;
            font-weight: 900;
            color: #1a1a1a;
            font-style: italic;
        }
        
        .seccion-cuatro { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin-bottom: 8px; }
        .caja-num { border: 2px solid {{ color }}; border-radius: 8px; padding: 4px 8px; min-height: 42px; text-align: center; }
        .caja-num .label { font-size: 11px; font-weight: 900; color: #1a1a1a; text-transform: uppercase; }
        .caja-num .valor { font-size: 15px; font-weight: 900; color: #1a1a1a; word-break: break-word; }
        .seccion-doble-2 {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 6px;
            margin-bottom: 8px;
        }
        .caja-guia, .caja-factura {
            border: 2px solid {{ color }};
            border-radius: 8px;
            padding: 5px 12px;
            display: flex;
            align-items: center;
            gap: 8px;
            min-height: 42px;
        }
        .caja-guia .label, .caja-factura .label {
            font-size: 15px;
            font-weight: 900;
            color: #1a1a1a;
            text-transform: uppercase;
            flex-shrink: 0;
        }
        .caja-guia .valor, .caja-factura .valor {
            font-size: 15px;
            font-weight: 600;
            color: #1a1a1a;
            font-style: italic;
        }
        
        /* Pie del rótulo: CSS indicado por Erika (21/10/2026) */
        .footer { margin-top: auto; display: flex; justify-content: center; align-items: center; flex-wrap: wrap; gap: 6px 22px; padding: 6px 4px 0; font-size: 12px; color: #1a1a1a; font-weight: 700; }
        .footer .item { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; line-height: 1; }
        .footer .item svg { width: 17px; height: 17px; fill: #1a1a1a; flex-shrink: 0; }
        .footer .item .sep { color: {{ color }}; font-weight: 900; margin: 0 2px; }
        
        .info-extra {
            margin-top: 4px;
            padding: 4px 10px;
            border: 1.5px solid {{ color }};
            border-radius: 6px;
            font-size: 9px;
            color: #333;
            background: #FFF5F5;
        }
        .info-extra strong {
            color: {{ color }};
            font-weight: 900;
        }
    </style>
</head>
<body>
    <div class="rotulo-wrapper">

        <div class="header">
            <div class="header-left">
                <div class="logo">
                    {% if logo_src %}
                    <img src="{{ logo_src }}" alt="Logo {{ empresa_corto }}">
                    {% else %}
                    <div style="width:65px;height:55px;border-radius:8px;background:{{ color }};color:#fff;font-weight:900;font-size:18px;display:flex;align-items:center;justify-content:center;">{{ empresa_corto }}</div>
                    {% endif %}
                </div>
                <div class="empresa-info">
                    <div class="nombre">{{ empresa_nombre }}</div>
                    <div class="ruc">RUC: {{ empresa_ruc }}</div>
                </div>
            </div>

            <div class="header-center"></div>

            <div class="header-right">
                <div class="qr-box">
                    <img src="{{ qr_base64 }}" alt="QR">
                </div>
            </div>
        </div>

        <div class="seccion-cliente">
            <span class="label">CLIENTE:</span>
            <span class="valor">{{ cliente_nombre }}</span>
        </div>

        <div class="seccion-direccion">
            <span class="label">DIRECCIÓN<br>DE ENTREGA:</span>
            <span class="valor">{{ cliente_direccion }}</span>
        </div>

        <div class="seccion-doble">
            <div class="caja-consignados">
                <span class="label">CONSIGNADOS:</span>
                <div class="datos">
                    <div class="nombre">{{ consignado_nombre or '—' }}</div>
                    <div class="dni">DNI: {{ consignado_dni or '—' }}</div>
                </div>
            </div>
            <div class="caja-blts">
                <span class="label">N° BLTS:</span>
                <span class="valor">{{ numero_bultos }}</span>
            </div>
        </div>

        <div class="seccion-cuatro">
            <div class="caja-num"><div class="label">N° Despacho</div><div class="valor">{{ nro_despacho }}</div></div>
            <div class="caja-num"><div class="label">N° Pedido de venta</div><div class="valor">{{ nro_pc }}</div></div>
            <div class="caja-num"><div class="label">N° Guía</div><div class="valor">{{ nro_guia }}</div></div>
            <div class="caja-num"><div class="label">N° Factura</div><div class="valor">{{ nro_factura }}</div></div>
        </div>

        <div class="footer">
            <div class="item">
                <svg viewBox="0 0 24 24"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z"/></svg>
                <span>{{ empresa_telefono }}</span>
            </div>
            <div class="item">
                <span class="sep">|</span>
                <svg viewBox="0 0 24 24"><path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg>
                <span>{{ empresa_email }}</span>
            </div>
        </div>

        {% if observaciones %}
        <div class="info-extra">
            <strong>Observaciones:</strong> {{ observaciones }}
        </div>
        {% endif %}

    </div>
</body>
</html>"""

    # ============================================================
    # GENERAR COTIZACIÓN
    # ============================================================
    def _generar_cotizacion(self, datos):
        try:
            print("📄 Generando PDF de cotización...")
            
            EMPRESA = self._emisora(datos)
            logo_src = EMPRESA.get('logo_src', '')
            
            items = datos.get('items', [])
            if isinstance(items, str):
                try:
                    items = json.loads(items)
                except:
                    items = []
            
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
                        'precio_unitario': float(item.get('valorVenta', item.get('precio', 0))),
                        'total_item': float(item.get('cantidad', 1)) * float(item.get('valorVenta', item.get('precio', 0)))
                    })
                elif isinstance(item, (list, tuple)):
                    items_formateados.append({
                        'item': idx,
                        'codigo': item[0] if len(item) > 0 else '',
                        'descripcion': item[1] if len(item) > 1 else '',
                        'marca': item[4] if len(item) > 4 else '',
                        'modelo': item[5] if len(item) > 5 else '',
                        'unidad': 'NIU',
                        'cantidad': float(item[2] if len(item) > 2 else 1),
                        'precio_unitario': float(item[3] if len(item) > 3 else 0),
                        'total_item': float(item[2] if len(item) > 2 else 1) * float(item[3] if len(item) > 3 else 0)
                    })
            
            subtotal = float(datos.get('subtotal', 0))
            igv = float(datos.get('igv', 0))
            total = float(datos.get('total', datos.get('monto', 0)))
            
            if subtotal == 0 and items_formateados:
                subtotal = sum(item['total_item'] for item in items_formateados)
                igv = subtotal * 0.18
                total = subtotal + igv
            
            orden_compra_cliente = datos.get('orden_compra_cliente', '—')
            nro_cotizacion = datos.get('nro_cotizacion', datos.get('numero_cotizacion', '—'))
            
            datos_template = {
                'logo_src': logo_src,
                'empresa_corto': EMPRESA.get('corto', ''),
                'color_empresa': EMPRESA.get('color') or '#CC0000',
                'empresa_ruc': EMPRESA['ruc'],
                'empresa_nombre': EMPRESA['nombre'],
                'empresa_telefono': EMPRESA['telefono'],
                'empresa_email': EMPRESA['email'],
                'empresa_web': EMPRESA['web'],
                'tipo': datos.get('tipo_documento', 'COTIZACIÓN'),
                'serie': datos.get('serie', 'COT'),
                'numero': datos.get('numero', datos.get('numero_cotizacion', '')),
                'fecha_emision': self._formatear_fecha(datos.get('fecha_emision', datos.get('fecha'))),
                'cliente_nombre': datos.get('cliente_nombre', datos.get('razon', datos.get('cliente', ''))),
                'cliente_ruc': datos.get('cliente_ruc', datos.get('ruc', '')),
                'cliente_direccion': datos.get('cliente_direccion', datos.get('direccion', '')),
                'cliente_email': datos.get('cliente_email', datos.get('email', '')),
                'cliente_telefono': datos.get('cliente_telefono', datos.get('telefono', '')),
                'moneda': self._simbolo(datos),
                'subtotal': f"{subtotal:.2f}",
                'igv': f"{igv:.2f}",
                'total': f"{total:.2f}",
                'condicion_pago': datos.get('condicion_pago', datos.get('condicion', 'Contado')),
                'tiempo_entrega': datos.get('tiempo_entrega', datos.get('entrega', '')),
                'validez': datos.get('validez', datos.get('validez_oferta', '15 días')),
                'observaciones': datos.get('observaciones', ''),
                'orden_compra_cliente': orden_compra_cliente if orden_compra_cliente else '—',
                'nro_cotizacion': nro_cotizacion if nro_cotizacion else '—',
                'items': items_formateados,
                'qr_base64': self._generar_qr_cotizacion(datos)
            }
            
            template_content = self._obtener_template_cotizacion()
            
            try:
                html_content = Template(template_content).render(**datos_template)
            except Exception as e:
                print(f"❌ Error renderizando template de cotización: {e}")
                html_content = template_content
            
            fecha = datetime.now().strftime('%Y%m%d_%H%M%S')
            nombre_archivo = f"cotizacion_{datos_template['serie']}_{datos_template['numero']}_{fecha}.pdf"
            
            base_url = f"file://{os.getcwd()}/"
            HTML(string=html_content, base_url=base_url).write_pdf(nombre_archivo)
            
            print(f"✅ PDF generado: {nombre_archivo}")
            return nombre_archivo
            
        except Exception as e:
            print(f"❌ Error generando cotización: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _obtener_template_cotizacion(self):
        return """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{{ tipo }} {{ serie }}-{{ numero }}</title>
    <style>
        @page { size: A4; margin: 1.2cm 1.5cm; }
        body {
            font-family: 'Helvetica', Arial, sans-serif;
            font-size: 9.5px;
            color: #333333;
            line-height: 1.8;
            background: #ffffff;
        }
        .color-rojo { color: {{ color_empresa }}; }
        .color-gris { color: #555555; }
        .header-superior {
            display: flex;
            justify-content: space-between;
            align-items: stretch;
            margin-bottom: 10px;
            gap: 20px;
            border-bottom: 2px solid #999999;
            padding-bottom: 8px;
        }
        .empresa-izquierda { flex: 1; display: flex; align-items: center; gap: 18px; }
        .empresa-izquierda .logo-container {
            flex-shrink: 0; width: 100px; height: 70px;
            display: flex; align-items: center; justify-content: center;
        }
        .empresa-izquierda .logo-container img {
            max-height: 65px; max-width: 110px; object-fit: contain;
        }
        .empresa-izquierda .info-texto { font-size: 8.5px; line-height: 1.5; color: #444444; }
        .empresa-izquierda .info-texto .nombre {
            font-size: 13px; font-weight: bold; text-transform: uppercase;
            color: #333333; letter-spacing: 0.5px; margin-bottom: 2px;
        }
        .empresa-izquierda .info-texto .ruc-line {
            font-size: 9px; font-weight: bold; color: #333333; margin-bottom: 1px;
        }
        .empresa-izquierda .info-texto .slogan {
            font-size: 8px; color: #666666; font-style: italic; margin-bottom: 1px;
        }
        .empresa-izquierda .info-texto .contacto-line { font-size: 7.5px; color: #555555; }
        .recuadro-derecha {
            flex-shrink: 0; border: 2px solid #999999; border-radius: 12px;
            padding: 10px 20px; text-align: center; min-width: 200px;
            display: flex; flex-direction: column; justify-content: center;
        }
        .recuadro-derecha .ruc { font-size: 10px; font-weight: bold; color: #333333; }
        .recuadro-derecha .titulo {
            font-size: 13px; font-weight: bold; letter-spacing: 1px;
            margin: 2px 0; color: {{ color_empresa }};
        }
        .recuadro-derecha .numero { font-size: 15px; font-weight: bold; color: {{ color_empresa }}; }
        .seccion { margin-bottom: 8px; }
        .seccion-titulo {
            font-weight: bold; font-size: 9.5px; margin-bottom: 3px;
            text-transform: uppercase; border-bottom: 2px solid #999999;
            padding-bottom: 2px; color: #333333;
        }
        .info-cliente {
            border: 1px solid #cccccc; border-radius: 8px;
            padding: 6px 12px; margin-bottom: 6px;
        }
        .fila { display: flex; padding: 1px 0; align-items: baseline; }
        .fila .label {
            font-weight: bold; min-width: 120px; flex-shrink: 0; color: #555555;
        }
        .fila .value {
            flex: 1; text-align: left; padding-left: 5px; color: #333333;
        }
        .products-table {
            width: 100%; border-collapse: collapse; margin: 4px 0; font-size: 8.5px;
        }
        .products-table th {
            color: #333333; padding: 4px 5px; text-align: center;
            border: 1px solid #cccccc; background: #f5f5f5;
        }
        .products-table td {
            padding: 3px 5px; border: 1px solid #cccccc;
            text-align: center; color: #333333;
        }
        .products-table td.descripcion { text-align: left; }
        .products-table tr:nth-child(even) td { background: #f9f9f9; }
        .totales-box {
            border: 2px solid #999999; border-radius: 8px; padding: 8px 12px;
            margin-top: 6px; display: flex; flex-direction: column; align-items: flex-end;
        }
        .totales-box .linea {
            display: flex; justify-content: space-between; width: 220px;
            padding: 2px 0; color: #444444;
        }
        .totales-box .linea.total {
            font-weight: bold; font-size: 12px; border-top: 2px solid #999999;
            padding-top: 4px; margin-top: 4px; color: #333333;
        }
        .totales-box .linea.total .value-total { color: #333333; font-size: 14px; }
        .referencias {
            border: 1px solid #cccccc; border-radius: 8px;
            padding: 6px 12px; margin-bottom: 6px;
        }
        .referencias-grid {
            display: grid; grid-template-columns: 1fr 1fr 1fr;
            gap: 8px; padding: 6px 0;
        }
        .ref-item { text-align: center; }
        .ref-item .ref-label {
            font-weight: bold; display: block; font-size: 7.5px;
            color: #777777; text-transform: uppercase; letter-spacing: 0.3px;
        }
        .ref-item .ref-value { font-size: 9px; font-weight: 600; color: #333333; }
        .qr-container {
            text-align: center; margin: 8px 0 5px 0; padding: 6px;
            border: 2px solid #999999; border-radius: 8px;
        }
        .qr-container img { width: 90px; height: 90px; }
        .qr-container .qr-text { font-size: 7px; color: #888888; margin-top: 2px; }
        .footer {
            margin-top: 12px; text-align: center; font-size: 7.5px;
            color: #888888; padding-top: 6px;
        }
        .footer .condicion-pago {
            margin: 4px 0; font-size: 8.5px; font-weight: bold; color: #333333;
        }
        .observaciones {
            margin-top: 6px; padding: 6px 10px;
            border: 1px solid #e5e7eb; border-radius: 6px;
            font-size: 8.5px; color: #555555;
        }
        .condiciones {
            display: grid; grid-template-columns: 1fr 1fr;
            gap: 4px 20px; padding: 4px 0;
        }
        .condiciones .cond-item {
            display: flex; gap: 4px; font-size: 8.5px;
        }
        .condiciones .cond-label { font-weight: bold; color: #555555; }
        .condiciones .cond-value { font-weight: 600; color: #333333; }
    </style>
</head>
<body>
    <div class="header-superior">
        <div class="empresa-izquierda">
            <div class="logo-container">
                {% if logo_src %}<img src="{{ logo_src }}" alt="Logo" style="max-height:65px;">{% else %}<div style="font-size:26px;font-weight:900;color:{{ color_empresa }};padding-top:12px;">{{ empresa_corto }}</div>{% endif %}
            </div>
            <div class="info-texto">
                <div class="nombre">{{ empresa_nombre }}</div>
                <div class="ruc-line">RUC: {{ empresa_ruc }}</div>
                <div class="slogan">Soluciones integrales en abastecimientos</div>
                <div class="contacto-line">Telf: {{ empresa_telefono }} | Email: {{ empresa_email }}</div>
                <div class="contacto-line">Web: {{ empresa_web }}</div>
            </div>
        </div>
        <div class="recuadro-derecha">
            <div class="ruc">RUC Nº {{ empresa_ruc }}</div>
            <div class="titulo">{{ tipo }}</div>
            <div class="numero">{{ serie }}-{{ numero }}</div>
        </div>
    </div>

    <div class="seccion">
        <div class="seccion-titulo">DATOS DEL CLIENTE</div>
        <div class="info-cliente">
            <div class="fila"><span class="label">RUC.:</span><span class="value">{{ cliente_ruc }}</span></div>
            <div class="fila"><span class="label">RAZÓN SOCIAL:</span><span class="value">{{ cliente_nombre }}</span></div>
            <div class="fila"><span class="label">DIRECCIÓN:</span><span class="value">{{ cliente_direccion }}</span></div>
            <div class="fila"><span class="label">EMAIL:</span><span class="value">{{ cliente_email }}</span></div>
            <div class="fila"><span class="label">TELÉFONO:</span><span class="value">{{ cliente_telefono }}</span></div>
        </div>
    </div>

    <div class="seccion">
        <div class="seccion-titulo">DOCUMENTOS RELACIONADOS</div>
        <div class="referencias">
            <div class="referencias-grid">
                <div class="ref-item">
                    <span class="ref-label">NRO ORDEN DE COMPRA</span>
                    <span class="ref-value">{{ orden_compra_cliente or '—' }}</span>
                </div>
                <div class="ref-item">
                    <span class="ref-label">NRO DE COTIZACION</span>
                    <span class="ref-value">{{ nro_cotizacion or '—' }}</span>
                </div>
                <div class="ref-item">
                    <span class="ref-label">FECHA EMISIÓN</span>
                    <span class="ref-value">{{ fecha_emision or '—' }}</span>
                </div>
            </div>
        </div>
    </div>

    <div class="seccion">
        <div class="seccion-titulo">DETALLE DE PRODUCTOS</div>
        <table class="products-table">
            <thead>
                <tr>
                    <th style="width:5%">Item</th>
                    <th style="width:12%">Código</th>
                    <th style="width:33%">Descripción</th>
                    <th style="width:10%">Marca</th>
                    <th style="width:8%">Modelo</th>
                    <th style="width:6%">UM</th>
                    <th style="width:6%">Cant.</th>
                    <th style="width:10%">Precio Unit.</th>
                    <th style="width:10%">Total</th>
                </tr>
            </thead>
            <tbody>
                {% for item in items %}
                <tr>
                    <td>{{ item.item }}</td>
                    <td>{{ item.codigo }}</td>
                    <td class="descripcion">{{ item.descripcion }}</td>
                    <td>{{ item.marca }}</td>
                    <td>{{ item.modelo }}</td>
                    <td>{{ item.unidad }}</td>
                    <td>{{ item.cantidad }}</td>
                    <td>{{ moneda }} {{ "%.2f"|format(item.precio_unitario) }}</td>
                    <td>{{ moneda }} {{ "%.2f"|format(item.total_item) }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <div class="totales-box">
        <div class="linea"><span>Subtotal:</span><span>{{ moneda }} {{ subtotal }}</span></div>
        <div class="linea"><span>IGV (18%):</span><span>{{ moneda }} {{ igv }}</span></div>
        <div class="linea total">
            <span>TOTAL:</span>
            <span class="value-total">{{ moneda }} {{ total }}</span>
        </div>
    </div>

    <div class="seccion">
        <div class="seccion-titulo">CONDICIONES COMERCIALES</div>
        <div class="info-cliente" style="padding:4px 12px;">
            <div class="condiciones">
                <div class="cond-item">
                    <span class="cond-label">Condición de Pago:</span>
                    <span class="cond-value">{{ condicion_pago }}</span>
                </div>
                <div class="cond-item">
                    <span class="cond-label">Tiempo de Entrega:</span>
                    <span class="cond-value">{{ tiempo_entrega or '—' }}</span>
                </div>
                <div class="cond-item">
                    <span class="cond-label">Validez de Oferta:</span>
                    <span class="cond-value">{{ validez or '—' }}</span>
                </div>
                <div class="cond-item">
                    <span class="cond-label">Fecha Emisión:</span>
                    <span class="cond-value">{{ fecha_emision }}</span>
                </div>
            </div>
        </div>
    </div>

    {% if observaciones %}
    <div class="observaciones">
        <strong>Observaciones:</strong> {{ observaciones }}
    </div>
    {% endif %}

    <div class="qr-container">
        <img src="{{ qr_base64 }}" alt="QR">
        <div class="qr-text">Representación impresa de la COTIZACIÓN</div>
    </div>

    <div class="footer">
        <div>Pag. 1 de 1</div>
        <div class="condicion-pago">** {{ condicion_pago }} **</div>
        <div>Powered by {{ empresa_corto or 'KCF' }}</div>
    </div>
</body>
</html>"""

    def _generar_qr_cotizacion(self, datos):
        try:
            import qrcode
            from io import BytesIO
            
            qr_data = {
                'tipo': datos.get('tipo_documento', 'COTIZACIÓN'),
                'serie': datos.get('serie', 'COT'),
                'numero': datos.get('numero', datos.get('numero_cotizacion', '')),
                'ruc_emisor': (datos.get('empresa_pdf') or {}).get('ruc') or '20602095704',
                'ruc_cliente': datos.get('cliente_ruc', datos.get('ruc', '')),
                'fecha_emision': self._formatear_fecha(datos.get('fecha_emision', datos.get('fecha'))),
                'total': str(datos.get('total', datos.get('monto', 0)))
            }
            
            qr = qrcode.QRCode(version=2, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=4, border=2)
            qr.add_data(json.dumps(qr_data))
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode()
            return f"data:image/png;base64,{img_base64}"
        except ImportError:
            print("⚠️ qrcode no instalado, QR no generado")
            return ""
        except Exception as e:
            print(f"⚠️ Error generando QR: {e}")
            return ""


# ============================================================
# INSTANCIA GLOBAL
# ============================================================
pdf_generator = PDFGenerator()