# routes/multiempresa.py - Empresa activa (KCF / AGD / Todas) para todo el ERP (pedido de Erika, 15/10/2026)
#
# Reglas (en simple):
#   1. Arriba a la derecha se elige la empresa: KCF, AGD (o las que se agreguen en erp_empresas) o
#      "Todas las empresas" (consolidado). Al cambiarla la página se recarga y TODO se filtra.
#   2. Cada documento (cotización, PV, despacho, guía, factura, nota de crédito, devolución, OC,
#      recepción, factura de proveedor, cobro/pago) guarda empresa_id (UUID de erp_empresas).
#      Los documentos que nacen de otro heredan su empresa (la guía del despacho, la factura de la guía...).
#   3. Clientes, proveedores y productos son del grupo: empresa_id vacío = "de todas las empresas".
#      Si se les pone empresa, solo se ven en esa empresa.
#   4. Con "Todas las empresas" se puede ver todo, pero para CREAR hay que elegir una empresa arriba.
#   5. Los colores del sistema salen de erp_empresas (color_primario, color_secundario, color_pastel).
# Script equivalente para Supabase: migrations/007_multiempresa.sql
import os
import threading
import time

from flask import Blueprint, g, jsonify, request, session

from database import db_query, db_tx

multiempresa_bp = Blueprint('multiempresa', __name__)

TODAS = 'TODAS'

# Documentos: siempre tienen empresa. Maestros: vacío = compartido por el grupo.
TABLAS_DOCUMENTOS = ('cotizaciones', 'pedido_compra_pc', 'despachos', 'guias_remision', 'comprobantes',
                     'notas_credito', 'devoluciones', 'finanzas_pagos', 'ordenes_compra',
                     'recepciones_mercaderia', 'comprobantes_proveedor', 'solicitudes_compra')
TABLAS_MAESTROS = ('clientes', 'proveedores', 'productos')
COLUMNAS_EMPRESA_NUEVAS = (('erp_empresas', 'pagina_web', 'TEXT'), ('erp_empresas', 'correo_rotulo', 'TEXT'),
                           ('erp_empresas', 'ubigeo', 'TEXT'))

# Colores si una empresa no tiene los suyos (o para "Todas")
TEMA_TODAS = {'color_primario': '#334155', 'color_secundario': '#0F172A', 'color_pastel': '#F1F5F9'}


class ErrorEmpresa(ValueError):
    pass


# ============================================================
# COLUMNAS (solo se crean si faltan; en Supabase ya están por la migración 007)
# ============================================================
_listo = False
_lock = threading.Lock()


def asegurar_columnas_empresa():
    global _listo
    if _listo:
        return
    with _lock:
        if _listo:
            return
        # Primero las tablas que los módulos crean solos (en bases nuevas), para que también lleven empresa_id
        from routes.finanzas import asegurar_tablas_finanzas
        from routes.inventario import asegurar_tablas_inventario
        asegurar_tablas_finanzas()
        asegurar_tablas_inventario()
        with db_tx() as conn:
            cur = conn.cursor()
            cur.execute("""SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a
                           WHERE a.attrelid = to_regclass('erp_empresas') AND a.attname = 'id'""")
            fila = cur.fetchone()
            if fila:
                tipo = 'UUID' if fila[0] == 'uuid' else 'INTEGER'
                cur.execute("""SELECT table_name, column_name FROM information_schema.columns
                               WHERE table_schema = current_schema()
                                 AND column_name IN ('empresa_id', 'pagina_web', 'correo_rotulo', 'ubigeo')""")
                existentes = {(t, c) for t, c in cur.fetchall()}
                faltan = [(t, 'empresa_id', tipo) for t in TABLAS_DOCUMENTOS + TABLAS_MAESTROS
                          if (t, 'empresa_id') not in existentes]
                faltan += [x for x in COLUMNAS_EMPRESA_NUEVAS if (x[0], x[1]) not in existentes]
                faltan = [x for x in faltan if _existe_tabla(cur, x[0])]
                if faltan:
                    cur.execute("SELECT pg_advisory_xact_lock(hashtext('multiempresa_ddl'))")
                    for tabla, col, t in faltan:
                        cur.execute(f'ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS {col} {t}')
                        if col == 'empresa_id':
                            cur.execute(f'CREATE INDEX IF NOT EXISTS idx_{tabla}_empresa_id ON {tabla} (empresa_id)')
            # 16/10: el interruptor "Producto" del PV ahora se guarda (antes al reabrir salía apagado)
            cur.execute("""SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema()
                           AND table_name = 'pedido_compra_pc' AND column_name = 'valida_productos'""")
            if not cur.fetchone() and _existe_tabla(cur, 'pedido_compra_pc'):
                cur.execute('ALTER TABLE pedido_compra_pc ADD COLUMN IF NOT EXISTS valida_productos BOOLEAN')
            # 17/10: estado de entrega por producto de la cotización (solo "Pendiente" o "Entregado")
            cur.execute("""SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema()
                           AND table_name = 'cotizacion_detalle' AND column_name = 'estado_entrega'""")
            if not cur.fetchone() and _existe_tabla(cur, 'cotizacion_detalle'):
                cur.execute("ALTER TABLE cotizacion_detalle ADD COLUMN IF NOT EXISTS estado_entrega VARCHAR(20) DEFAULT 'Pendiente'")
        _listo = True
        _cache['t'] = 0   # releer empresas (pueden haber aparecido columnas nuevas)


def _existe_tabla(cur, tabla):
    cur.execute("SELECT to_regclass(%s) IS NOT NULL", (tabla,))
    return cur.fetchone()[0]


# ============================================================
# EMPRESAS (se leen de erp_empresas; se guardan 60 segundos en memoria)
# ============================================================
_cache = {'t': 0, 'filas': []}


def empresas(refrescar=False):
    if refrescar or time.time() - _cache['t'] > 60:
        try:
            filas = db_query("""
                SELECT id, codigo, COALESCE(NULLIF(nombre_corto, ''), codigo) AS nombre_corto,
                       COALESCE(NULLIF(nombre_comercial, ''), razon_social, codigo) AS nombre_comercial,
                       razon_social, ruc, direccion_fiscal, telefono, correo_documentos, logo_url,
                       color_primario, color_secundario, color_pastel
                FROM erp_empresas
                WHERE COALESCE(LOWER(estado), 'activo') NOT IN ('inactivo', 'inactiva', 'anulado')
                ORDER BY codigo
            """)
            extra = {}
            try:
                extra = {str(f['id']): f for f in db_query("SELECT id, pagina_web, correo_rotulo, ubigeo FROM erp_empresas")}
            except Exception:
                pass
            salida = []
            for f in filas:
                d = dict(f)
                d['id'] = str(d['id'])
                d['codigo'] = (d['codigo'] or '').upper()
                d.update({k: v for k, v in (extra.get(d['id']) or {}).items() if k != 'id'})
                salida.append(d)
            _cache.update(t=time.time(), filas=salida)
        except Exception:
            # Sin tabla de empresas (bases antiguas): el ERP funciona como antes, sin filtro
            _cache.update(t=time.time(), filas=[])
    return _cache['filas']


def empresa_por_codigo(codigo):
    codigo = (codigo or '').upper()
    return next((e for e in empresas() if e['codigo'] == codigo), None)


def empresa_por_id(eid):
    if eid is None:
        return None
    return next((e for e in empresas() if e['id'] == str(eid)), None)


# ============================================================
# EMPRESA ACTIVA (la que se eligió arriba)
# ============================================================
def codigo_activo():
    return (session.get('empresa') or 'KCF').upper()


def es_todas():
    return codigo_activo() == TODAS


def empresa_actual():
    """La empresa elegida arriba (dict) o None si se eligió "Todas" o no existe en erp_empresas."""
    return None if es_todas() else empresa_por_codigo(codigo_activo())


def empresa_filtro():
    """Id para filtrar listas: el de la empresa activa, o None (= todas)."""
    e = empresa_actual()
    return e['id'] if e else None


def empresa_para_crear(heredada=None):
    """Empresa con la que se guarda un documento nuevo.
    heredada: empresa del documento de origen (la guía hereda la del despacho, etc.)."""
    if heredada:
        return str(heredada)
    if es_todas():
        g.error_empresa = True  # para responder 400 aunque la ruta capture la excepción
        raise ErrorEmpresa('Estás viendo "Todas las empresas". Para crear un documento elige arriba la empresa '
                           '(por ejemplo KCF o AGD).')
    e = empresa_actual()
    return e['id'] if e else None


def filtro_sql(columna='empresa_id'):
    """Pedazo de SQL para filtrar por la empresa activa: (sql, parámetros).
    Las filas sin empresa (maestros compartidos o datos antiguos) se ven en todas las empresas."""
    eid = empresa_filtro()
    return f" AND (%s IS NULL OR {columna} IS NULL OR {columna} = %s)", (eid, eid)


def empresa_de(cur, tabla, columna, valor):
    """empresa_id de un documento de origen (ej. empresa_de(cur, 'despachos', 'numero', 'DES-0001'))."""
    if valor in (None, ''):
        return None
    sql = f"SELECT empresa_id FROM {tabla} WHERE {columna} = %s AND empresa_id IS NOT NULL LIMIT 1"
    try:
        if cur is None:
            filas = db_query(sql, (valor,))
            f = filas[0] if filas else None
        else:
            cur.execute(sql, (valor,))
            f = cur.fetchone()
    except Exception:
        if cur is not None:
            raise
        return None
    if not f:
        return None
    v = f['empresa_id'] if isinstance(f, dict) else f[0]
    return str(v) if v is not None else None


# Tablas antiguas que además guardan el código en texto (columna "empresa", por defecto 'KCF')
TABLAS_CON_CODIGO = ('pedido_compra_pc', 'despachos', 'devoluciones', 'notas_credito')


def marcar_empresa(cur, tabla, fila_id, empresa_id):
    """Pone la empresa a un documento recién creado. cur=None abre su propia transacción."""
    if fila_id is None or empresa_id is None:
        return
    if cur is None:
        with db_tx() as conn:
            return marcar_empresa(conn.cursor(), tabla, fila_id, empresa_id)
    cur.execute(f"UPDATE {tabla} SET empresa_id = %s WHERE id = %s", (empresa_id, fila_id))
    e = empresa_por_id(empresa_id)
    if tabla in TABLAS_CON_CODIGO and e and _tiene_columna_empresa(cur, tabla):
        cur.execute(f"UPDATE {tabla} SET empresa = %s WHERE id = %s", (e['codigo'], fila_id))


_col_empresa = {}


def _tiene_columna_empresa(cur, tabla):
    """Bases antiguas no tienen la columna de texto "empresa" (solo empresa_id)."""
    if tabla not in _col_empresa:
        cur.execute("""SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema()
                       AND table_name = %s AND column_name = 'empresa'""", (tabla,))
        _col_empresa[tabla] = cur.fetchone() is not None
    return _col_empresa[tabla]


# ============================================================
# TEMA (colores) PARA LAS PLANTILLAS
# ============================================================
def _mezclar(hex_color, con='#FFFFFF', proporcion=0.85):
    try:
        a = [int(hex_color.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)]
        b = [int(con.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)]
        return '#' + ''.join(f'{round(x + (y - x) * proporcion):02X}' for x, y in zip(a, b))
    except (ValueError, AttributeError):
        return hex_color


def tema(e=None):
    base = e or TEMA_TODAS
    p = base.get('color_primario') or TEMA_TODAS['color_primario']
    s = base.get('color_secundario') or TEMA_TODAS['color_secundario']
    pastel = base.get('color_pastel') or _mezclar(p, proporcion=0.9)
    return {
        '--empresa': p, '--empresa-dark': s, '--empresa-soft': _mezclar(p, proporcion=0.85),
        '--empresa-sidebar': pastel, '--empresa-hover': _mezclar(p, '#000000', 0.15),
        '--topbar-bg': _mezclar(p, proporcion=0.94), '--topbar-border': _mezclar(p, proporcion=0.6),
        '--topbar-text': _mezclar(p, '#000000', 0.45), '--topbar-accent': p,
    }


def contexto_plantillas():
    """Variables para todas las plantillas: empresa activa, opciones del selector y colores."""
    try:
        if 'usuario_id' not in session:
            return {}
        lista = empresas()
        actual = empresa_actual()
        codigo = TODAS if es_todas() else (actual['codigo'] if actual else codigo_activo())
        t = tema(actual)
        return {'emp_ctx': {
            'codigo': codigo,
            'nombre': 'Todas las empresas' if codigo == TODAS else (actual['nombre_comercial'] if actual else codigo),
            'corto': 'TODAS' if codigo == TODAS else (actual['codigo'] if actual else codigo),
            'opciones': [{'codigo': e['codigo'], 'nombre': e['nombre_comercial'], 'corto': e['codigo'],
                          'color': e.get('color_primario')} for e in lista],
            'tema': t,
            'estilo': ';'.join(f'{k}:{v}' for k, v in t.items()),
            # Datos de la empresa activa (remitente de guías, etc.). Vacíos con "Todas".
            'ruc': actual.get('ruc') if actual else None,
            'razon_social': actual.get('razon_social') if actual else None,
            'direccion_fiscal': actual.get('direccion_fiscal') if actual else None,
            'ubigeo': actual.get('ubigeo') if actual else None,
        }}
    except Exception:
        return {}


# ============================================================
# API
# ============================================================
@multiempresa_bp.route('/api/empresa_activa', methods=['GET'])
def api_empresa_activa():
    actual = empresa_actual()
    return jsonify({'success': True, 'codigo': TODAS if es_todas() else codigo_activo(),
                    'empresa_id': actual['id'] if actual else None,
                    'empresas': [{'id': e['id'], 'codigo': e['codigo'], 'nombre': e['nombre_comercial'],
                                  'color': e.get('color_primario')} for e in empresas()]})


@multiempresa_bp.route('/api/empresa_activa', methods=['POST'])
def api_cambiar_empresa():
    d = request.get_json(silent=True) or request.form
    codigo = (d.get('codigo') or d.get('empresa') or '').strip().upper()
    if codigo != TODAS and not empresa_por_codigo(codigo):
        return jsonify({'success': False, 'error': 'Esa empresa no existe o está inactiva.'}), 400
    session['empresa'] = codigo
    return jsonify({'success': True, 'codigo': codigo,
                    'message': 'Ahora ves todas las empresas.' if codigo == TODAS else f'Ahora trabajas en {codigo}.'})


def registrar(app):
    app.register_blueprint(multiempresa_bp)
    app.context_processor(contexto_plantillas)

    @app.errorhandler(ErrorEmpresa)
    def _error_empresa(e):
        return jsonify({'success': False, 'error': str(e)}), 400

    @app.after_request
    def _error_empresa_capturado(resp):
        # Muchas rutas antiguas capturan todo y responden 500; este aviso es del usuario, no del sistema.
        if resp.status_code == 500 and g.get('error_empresa'):
            resp.status_code = 400
        return resp

    @app.before_request
    def _columnas_empresa():
        if 'usuario_id' in session and request.endpoint not in (None, 'static'):
            try:
                asegurar_columnas_empresa()
            except Exception as e:  # nunca bloquear el ERP por esto
                app.logger.warning('No se pudieron revisar las columnas de empresa: %s', e)


def filtrar_filas(tabla, filas, clave='id'):
    """Deja solo las filas de la empresa activa (y las que no tienen empresa). Con "Todas" no filtra."""
    eid = empresa_filtro()
    if eid is None or not filas:
        return filas
    try:
        ids = {f['id'] for f in db_query(f"SELECT id FROM {tabla} WHERE empresa_id IS NULL OR empresa_id = %s", (eid,))}
    except Exception:
        return filas
    return [f for f in filas if (f.get(clave) if isinstance(f, dict) else f[0]) in ids]


def visible_por_ambito(ambito):
    """Clientes y proveedores usan "ámbito": COMPARTIDO (todas las empresas) o el código de una empresa."""
    e = empresa_actual()
    if e is None:
        return True
    a = (ambito or 'COMPARTIDO').strip().upper()
    return a in ('', 'COMPARTIDO', 'TODAS', 'GRUPO') or a == e['codigo']


# ============================================================
# DATOS DE LA EMPRESA PARA PDF Y RÓTULOS
# ============================================================
_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _logo_empresa(e):
    """Logo en base64 (data URI) o '' si no hay archivo. Busca static/img/logo_<codigo>.png y similares."""
    import base64
    codigo = (e.get('codigo') or '').lower()
    nombres = [e.get('logo_url') or '', f'logo_{codigo}.png', f'logo-{codigo}.png']
    carpetas = [os.path.join(_RAIZ, 'static', 'img'), os.path.join(_RAIZ, 'static'), os.path.join(_RAIZ, 'templates', 'pdf')]
    for n in nombres:
        n = os.path.basename(n.strip())
        if not n:
            continue
        for c in carpetas:
            ruta = os.path.join(c, n)
            if os.path.isfile(ruta):
                tipo = 'svg+xml' if ruta.lower().endswith('.svg') else ('jpeg' if ruta.lower().endswith(('.jpg', '.jpeg')) else 'png')
                with open(ruta, 'rb') as f:
                    return f'data:image/{tipo};base64,' + base64.b64encode(f.read()).decode()
    return ''


def datos_empresa_documento(empresa_id=None):
    """Empresa de un documento (o la elegida arriba) con su logo, para PDF y rótulos. {} si no se sabe."""
    e = empresa_por_id(empresa_id) if empresa_id else empresa_actual()
    if not e:
        return {}
    d = dict(e)
    d['logo_src'] = _logo_empresa(e)
    return d


# Datos de KCF que los PDF usaban fijos (se mantienen cuando el documento no tiene empresa o falta el dato)
EMPRESA_KCF_PDF = {
    'nombre': 'KCF CORPORACION E.I.R.L', 'ruc': '20602095704', 'corto': 'KCF',
    'direccion': 'JR. LAS ALMENDRAS VERDES NRO. 284 URB. VIRGEN DEL ROSARIO LIMA - LIMA - SAN MARTIN DE PORRES',
    'telefono': '999 932 051', 'email': 'ventas@kcfcorporacion.com', 'web': 'https://kcfcorporacion.com/',
    'color': '#CC0000',
}


def marca_pdf(empresa_id=None):
    """Empresa que emite un PDF (cotización, factura, guía): nombre, RUC, contacto, color y logo.
    Si el documento no tiene empresa se usan los datos de KCF, como antes del cambio."""
    e = empresa_por_id(empresa_id) if empresa_id else None
    base = EMPRESA_KCF_PDF if (not e or e.get('codigo') == 'KCF') else {}
    if not e:
        e = empresa_por_codigo('KCF') or {}
    web = e.get('pagina_web') or base.get('web', '')
    d = {
        'nombre': e.get('razon_social') or base.get('nombre') or e.get('nombre_comercial') or '',
        'ruc': e.get('ruc') or base.get('ruc', ''),
        'corto': e.get('codigo') or base.get('corto', ''),  # KCF / AGD (el nombre corto de KCF en la base es "KC")
        'direccion': e.get('direccion_fiscal') or base.get('direccion', ''),
        'telefono': e.get('telefono') or base.get('telefono', ''),
        'email': e.get('correo_rotulo') or e.get('correo_documentos') or base.get('email', ''),
        'web': web,
        'web_corta': web.replace('https://', '').replace('http://', '').strip('/'),
        'color': e.get('color_primario') or base.get('color') or '#CC0000',
        'logo_src': _logo_empresa(e) if e else '',
    }
    d['cuentas'] = []
    if e.get('id'):
        try:
            d['cuentas'] = [dict(c) for c in db_query("""
                SELECT banco, tipo_cuenta, moneda, numero_cuenta, cci FROM erp_empresa_cuentas_bancarias
                WHERE empresa_id = %s AND COALESCE(estado, 'activo') = 'activo'
                ORDER BY es_principal DESC NULLS LAST, id""", (e['id'],))]
        except Exception:
            pass
    if d['web_corta'] and not d['web_corta'].startswith('www.'):
        d['web_corta'] = 'www.' + d['web_corta']
    return d


def empresa_id_por_ruc(ruc):
    """Para documentos antiguos sin empresa: la empresa del grupo con ese RUC (ej. el remitente de una guía)."""
    ruc = (ruc or '').strip()
    return next((e['id'] for e in empresas() if ruc and e.get('ruc') == ruc), None)
