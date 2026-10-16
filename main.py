import os
import sys
import time
import hmac

# Hora de Perú para todo el ERP (16/10): en Render el servidor está en UTC y datetime.now()
# daba 5 horas más (Kardex, numeraciones por día, fechas de documentos).
os.environ.setdefault('TZ', 'America/Lima')
if hasattr(time, 'tzset'):
    time.tzset()
import logging
from datetime import timedelta
import requests
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for, 
    session, flash, jsonify
)
from werkzeug.security import check_password_hash

try:
    from dotenv import load_dotenv  # carga variables desde .env en desarrollo local
    load_dotenv()
except ImportError:
    pass

from utils import login_required, admin_required, es_admin
from database import (
    verificar_usuario, verificar_usuario_supabase,
    insertar_cliente_completo, obtener_todos_clientes_con_detalles,
    obtener_cliente_completo_por_id, actualizar_cliente_completo,
    eliminar_cliente_db, obtener_ultimo_codigo_cliente,
    buscar_clientes_completo, insertar_proveedor_completo,
    obtener_todos_proveedores, obtener_proveedor_por_id,
    actualizar_proveedor, eliminar_proveedor_db,
    obtener_ultimo_codigo_proveedor, db_query,
    # 🔥 NUEVAS IMPORTACIONES
    obtener_clientes_para_maestros,
    obtener_proveedores_para_maestros,
    toggle_cliente_activo,
    toggle_proveedor_activo,
    actualizar_cliente_simple,
    actualizar_proveedor_simple,
    obtener_almacenes_para_maestros,
    guardar_almacen,
    toggle_almacen_activo,
    obtener_categorias_para_maestros,
    guardar_categoria,
    toggle_categoria_activo,
    obtener_marcas_para_maestros,
    guardar_marca,
    toggle_marca_activo,
    obtener_um_para_maestros,
    guardar_um,
    toggle_um_activo
)

# La conexión a BD se configura con la variable de entorno DATABASE_URL (ver database.py y .env.example)

# ==========================================
# IMPORTS DE BLUEPRINTS
# ==========================================
from routes.empresas import empresas_bp
from routes.usuarios import usuarios_bp
from routes.correlativos import correlativos_bp
from routes.parametros import parametros_bp
from routes.integracion import integracion_bp
from routes.configuracion_seguridad import config_seguridad_bp
from routes.dashboard import dashboard_bp
from routes.productos import productos_bp
from routes.ventas import ventas_bp
from routes.inventario import inventario_bp
from routes.finanzas import finanzas_bp
from routes.reportes import reportes_bp
from routes.herramientas import herramientas_bp
from routes.papelera import papelera_bp
from routes.configuracion import configuracion_bp
from routes.maestros import maestros_bp  # ← Este ya tiene sus propios endpoints
from routes.compras import compras_bp
from routes.compras_flujo import compras_flujo_bp
from routes.abastecimiento import abastecimiento_bp
from routes.stock_automatico import stock_auto_bp


# ==========================================
# APP CONFIGURACIÓN
# ==========================================
app = Flask(__name__)
# Se acepta SECRET_KEY (nombre usado en .env) o FLASK_SECRET_KEY (nombre usado antes en el código)
app.secret_key = os.environ.get("SECRET_KEY") or os.environ.get("FLASK_SECRET_KEY")
if not app.secret_key:
    app.secret_key = os.urandom(32)
    print("⚠️ SECRET_KEY no configurada: se generó una temporal (las sesiones se cerrarán al reiniciar).")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=int(os.environ.get("SESSION_HORAS", "10"))),
)
logging.basicConfig(level=logging.INFO)


# ==========================================
# 🔐 CONTROL DE ACCESO GLOBAL
# ==========================================
# Antes muchas rutas (usuarios, empresas, correlativos, parámetros, inventario...) se podían
# abrir sin iniciar sesión. Ahora toda ruta exige sesión salvo las públicas de esta lista,
# y la configuración del sistema exige rol administrador.
RUTAS_PUBLICAS = {'login', 'root', 'logout', 'static'}
PREFIJOS_SOLO_ADMIN = ('/empresas', '/usuarios', '/correlativos', '/parametros', '/integracion',
                       '/api/config/usuarios', '/api/config/auditoria')
# Lecturas de configuración que el resto de módulos necesita (listas de empresas, correlativos, etc.)
LECTURAS_CONFIG_PERMITIDAS = ('/api/config/session', '/api/config/empresas', '/api/config/correlativos',
                              '/api/config/parametros', '/api/config/roles', '/api/config/modulos',
                              '/api/config/submodulos')


@app.before_request
def control_de_acceso():
    if request.endpoint in RUTAS_PUBLICAS or request.endpoint is None:
        return None
    es_api = '/api/' in request.path
    if 'usuario_id' not in session:
        if es_api:
            return jsonify({'success': False, 'error': 'Sesión expirada o no autorizada. Inicia sesión.'}), 401
        flash('Por favor, inicia sesión para acceder.', 'warning')
        return redirect(url_for('login'))

    ruta = request.path
    requiere_admin = ruta.startswith(PREFIJOS_SOLO_ADMIN)
    if ruta.startswith('/api/config/') and request.method != 'GET' and ruta != '/api/config/correlativos/tomar':
        requiere_admin = True
    if ruta.startswith('/api/config/') and request.method == 'GET' and not ruta.startswith(LECTURAS_CONFIG_PERMITIDAS):
        requiere_admin = True
    # Cada usuario puede leer su propio registro y sus propios permisos (los usa el menú lateral)
    if requiere_admin and request.method == 'GET' and (
            ruta == '/api/config/usuarios' or
            ruta == f"/api/config/usuarios/{session.get('usuario_id')}/permisos"):
        requiere_admin = False
    if requiere_admin and not es_admin():
        if es_api:
            return jsonify({'success': False, 'error': 'No tienes permisos de administrador para esta acción.'}), 403
        flash('No tienes permisos para acceder a esa sección.', 'error')
        return redirect(url_for('index'))
    return None


@app.after_request
def cabeceras_seguridad(resp):
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    resp.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    resp.headers.setdefault('Referrer-Policy', 'same-origin')
    return resp


# ==========================================
# 🔥 CONTEXTO GLOBAL - REQUEST DISPONIBLE EN TODOS LOS TEMPLATES
# ==========================================
@app.context_processor
def inject_request():
    """Inyecta la variable 'request' en todos los templates"""
    from flask import request
    return dict(request=request)

# ==========================================
# REGISTRO DE BLUEPRINTS
# ==========================================
app.register_blueprint(empresas_bp)
app.register_blueprint(usuarios_bp)
app.register_blueprint(correlativos_bp)
app.register_blueprint(parametros_bp)
app.register_blueprint(integracion_bp)
app.register_blueprint(config_seguridad_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(productos_bp)
app.register_blueprint(ventas_bp)
app.register_blueprint(inventario_bp)
app.register_blueprint(finanzas_bp)
app.register_blueprint(reportes_bp)
app.register_blueprint(herramientas_bp)
app.register_blueprint(papelera_bp)
app.register_blueprint(configuracion_bp)
app.register_blueprint(maestros_bp)  
app.register_blueprint(compras_bp)
app.register_blueprint(compras_flujo_bp)
app.register_blueprint(abastecimiento_bp)
app.register_blueprint(stock_auto_bp)
# Empresa activa (KCF / AGD / Todas), filtros y colores por empresa
from routes import multiempresa
multiempresa.registrar(app)

# ==========================================
# HELPERS
# ==========================================
def formato_moneda_soles(valor):
    try:
        if valor is None:
            return "0.00"
        if isinstance(valor, str):
            v = valor.replace(",", "").strip()
            if not v:
                return "0.00"
            numero = float(v)
        else:
            numero = float(valor)
        return "{:,.2f}".format(numero)
    except (ValueError, TypeError):
        return "0.00"

app.jinja_env.filters["formato_soles"] = formato_moneda_soles

# ==========================================
# RUTAS DE AUTENTICACIÓN
# ==========================================
@app.route("/")
def root():
    if 'usuario_id' in session:
        return redirect(url_for('index'))
    return redirect(url_for('login'))

def _verificar_password(stored_password, password):
    """
    Verifica la contraseña contra lo almacenado en la tabla usuarios.
    Soporta hashes werkzeug (scrypt/pbkdf2), bcrypt y, por compatibilidad con datos
    existentes, contraseñas antiguas en texto plano (se recomienda migrarlas con
    scripts/hashear_passwords.py).
    """
    if not stored_password or not password:
        return False
    if stored_password.startswith(('scrypt:', 'pbkdf2:')):
        try:
            return check_password_hash(stored_password, password)
        except Exception:
            return False
    if stored_password.startswith(('$2a$', '$2b$', '$2y$')):
        try:
            import bcrypt
            return bcrypt.checkpw(password.encode('utf-8'), stored_password.encode('utf-8'))
        except Exception:
            return False
    # Contraseña heredada en texto plano: comparación en tiempo constante
    if hmac.compare_digest(stored_password.encode('utf-8'), password.encode('utf-8')):
        app.logger.warning("Usuario con contraseña en texto plano; ejecutar scripts/hashear_passwords.py")
        return True
    return False


@app.route("/login", methods=["GET", "POST"])
def login():
    if 'usuario_id' in session:
        return redirect(url_for('index'))

    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        password = request.form.get("password", "")
        empresa = request.form.get("empresa", "KCF")

        if not usuario or not password:
            flash("Por favor, ingresa usuario y contraseña.", "error")
            return render_template("login.html")

        try:
            user_result = db_query("""
                SELECT id, auth_user_id, usuario_sistema, nombres_apellidos,
                       correo, password, rol, area, estado
                FROM usuarios
                WHERE (usuario_sistema = %s OR LOWER(correo) = LOWER(%s)) AND estado = 'activo'
                ORDER BY (usuario_sistema = %s) DESC
                LIMIT 1
            """, (usuario, usuario, usuario))

            user = user_result[0] if user_result else None
            # Mensaje genérico: no revelar si el usuario existe
            if not user or not _verificar_password(user.get('password') or '', password):
                app.logger.info("Intento de inicio de sesión fallido para '%s'", usuario)
                flash("❌ Usuario o contraseña incorrectos.", "error")
                return render_template("login.html")

            session.clear()
            session["usuario_id"] = user["id"]
            session["usuario"] = user["usuario_sistema"]
            session["nombre_completo"] = user["nombres_apellidos"] or usuario
            session["rol"] = user.get("rol") or "usuario"
            session["empresa"] = empresa
            session["auth_user_id"] = user["auth_user_id"]
            session.permanent = True
            flash(f'✅ Bienvenido/a {session["nombre_completo"]}!', "success")
            return redirect(url_for("index"))

        except Exception as e:
            app.logger.exception("Error en el proceso de login: %s", e)
            flash("Error de autenticación. Intenta nuevamente o contacta al administrador.", "error")
            return render_template("login.html")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Has cerrado sesión correctamente.", "info")
    return redirect(url_for("login"))

# ==========================================
# RUTA INDEX (DASHBOARD)
# ==========================================
@app.route("/index")
@login_required
def index():
    return render_template("index.html",
                          nombre=session.get('nombre_completo', 'Usuario'),
                          usuario=session.get('usuario', ''),
                          empresa=session.get('empresa', 'KCF'),
                          rol=session.get('rol', 'usuario'))

# ==========================================
# ENDPOINTS CLIENTES API (SOLO LOS QUE NO ESTÁN EN MAESTROS)
# ==========================================

# NOTA: Los endpoints básicos CRUD para clientes/proveedores ahora están en maestros.py
# Aquí solo mantenemos endpoints específicos que no están en maestros

@app.route("/api/clientes/buscar", methods=["GET"])
def api_buscar_clientes():
    """Buscar clientes (autocomplete)"""
    try:
        busqueda = request.args.get('q', request.args.get('busqueda', '')).strip()
        if not busqueda or len(busqueda) < 2:
            return jsonify({"success": True, "data": []})
        
        clientes = buscar_clientes_completo(busqueda, limit=50)
        return jsonify({"success": True, "data": clientes})
    except Exception as e:
        app.logger.error(f"Error en api_buscar_clientes: {e}")
        return jsonify({"success": False, "error": str(e), "data": []}), 500

@app.route("/api/clientes/<int:cliente_id>/direcciones", methods=["GET"])
def api_obtener_direcciones_cliente(cliente_id):
    """Obtener puntos de entrega de un cliente"""
    try:
        query = """
            SELECT id, direccion, nombre_punto, principal, telefono_contacto, 
                   responsable, condicion_pago, tiempo_credito
            FROM clientes_puntos_entrega
            WHERE cliente_id = %s AND activo = true
            ORDER BY principal DESC, nombre_punto
        """
        direcciones = db_query(query, (cliente_id,))
        return jsonify({'success': True, 'data': direcciones or []})
    except Exception as e:
        app.logger.error(f"Error al obtener direcciones: {e}")
        return jsonify({'success': False, 'error': str(e), 'data': []}), 500

@app.route("/api/clientes/<int:cliente_id>/contactos", methods=["GET"])
def api_obtener_contactos_cliente(cliente_id):
    """Obtener contactos de un cliente"""
    try:
        query = """
            SELECT id, nombre_contacto, email, telefono, cargo, principal
            FROM clientes_contactos
            WHERE cliente_id = %s AND activo = true
            ORDER BY principal DESC, nombre_contacto
        """
        contactos = db_query(query, (cliente_id,))
        return jsonify({'success': True, 'data': contactos or []})
    except Exception as e:
        app.logger.error(f"Error al obtener contactos: {e}")
        return jsonify({'success': False, 'error': str(e), 'data': []}), 500

@app.route("/api/clientes/ultimo-codigo", methods=["GET"])
def api_ultimo_codigo():
    """Obtener último código de cliente"""
    try:
        codigo = obtener_ultimo_codigo_cliente()
        return jsonify({"success": True, "ultimoCodigo": codigo})
    except Exception as e:
        app.logger.error(f"Error al obtener último código: {e}")
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/proveedores/ultimo-codigo", methods=["GET"])
def api_ultimo_codigo_proveedor():
    """Obtener último código de proveedor"""
    try:
        codigo = obtener_ultimo_codigo_proveedor()
        return jsonify({"success": True, "ultimoCodigo": codigo})
    except Exception as e:
        app.logger.error(f"Error al obtener último código: {e}")
        return jsonify({"success": False, "error": str(e)})

# ==========================================
# ENDPOINT SUNAT
# ==========================================
@app.route("/api/sunat/consulta", methods=["GET"])
def api_consulta_sunat():
    # Primero el ERP (clientes y proveedores ya registrados), luego SUNAT con clave; ver routes/consulta_ruc.py
    from routes.consulta_ruc import consultar_ruc, ErrorConsultaRuc
    try:
        datos = consultar_ruc(request.args.get('ruc', ''))
        return jsonify({'success': True, **datos})
    except ErrorConsultaRuc as e:
        return jsonify({'success': False, 'error': str(e), 'manual': True})
    except Exception as e:
        app.logger.error(f"Error en consulta SUNAT: {e}")
        return jsonify({'success': False, 'error': 'No se pudo consultar el RUC. Escribe los datos a mano.', 'manual': True})

# ==========================================
# ENDPOINTS PRODUCTOS API
# ==========================================
# Antes usaban SQLAlchemy (no instalado y con 'text' sin importar): fallaban siempre con error 500.
@app.route("/api/productos/buscar", methods=["GET"])
def api_buscar_productos():
    try:
        q = request.args.get('q', '').strip()
        if not q:
            return jsonify({'success': True, 'data': []})
        rows = db_query("""
            SELECT id, COALESCE(codigo,'') AS codigo, COALESCE(descripcion,'') AS descripcion,
                   COALESCE(marca,'') AS marca, COALESCE(modelo,'') AS modelo, COALESCE(stock,0) AS stock
            FROM productos WHERE codigo ILIKE %s OR descripcion ILIKE %s
            ORDER BY codigo LIMIT 20
        """, (f'%{q}%', f'%{q}%'))
        return jsonify({'success': True, 'data': rows})
    except Exception as e:
        app.logger.error(f"Error en api_buscar_productos: {e}")
        return jsonify({'success': False, 'error': 'No se pudo buscar productos'}), 500


@app.route("/api/productos", methods=["GET"])
def api_listar_productos():
    try:
        rows = db_query("""
            SELECT id, COALESCE(codigo,'') AS codigo, COALESCE(descripcion,'') AS descripcion,
                   COALESCE(marca,'') AS marca, COALESCE(modelo,'') AS modelo, COALESCE(stock,0) AS stock
            FROM productos ORDER BY codigo LIMIT 100
        """)
        return jsonify({'success': True, 'data': rows})
    except Exception as e:
        app.logger.error(f"Error en api_listar_productos: {e}")
        return jsonify({'success': False, 'error': 'No se pudo listar productos'}), 500


@app.route('/api/test-db')
@admin_required
def test_db():
    """Prueba de conexión a la base de datos (solo administradores, sin exponer la URL)"""
    try:
        rows = db_query("SELECT version() AS version")
        return jsonify({'status': 'success', 'message': '✅ Conexión exitosa a la base de datos',
                        'version': rows[0]['version'] if rows else 'unknown'})
    except Exception as e:
        app.logger.error(f"Error test-db: {e}")
        return jsonify({'status': 'error', 'message': '❌ No se pudo conectar a la base de datos'}), 500


if __name__ == "__main__":
    # ✅ Usar configuración estándar para Render
    port = int(os.environ.get("PORT", 10000))  # Render usa 10000 por defecto
    host = "0.0.0.0"
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

    print("=" * 60)
    print("🚀 SERVIDOR ERP MULTIEMPRESA INICIADO")
    print("=" * 60)
    print(f"📍 Servidor corriendo en:")
    print(f"   👉 http://localhost:{port}")
    print("=" * 60)
    
    app.run(debug=debug, host=host, port=port)