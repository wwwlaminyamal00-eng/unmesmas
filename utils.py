# utils.py
# Utilidades compartidas: autenticación, roles y cálculos comerciales (IGV, totales).
import os
import re
from decimal import Decimal, ROUND_HALF_UP
from functools import wraps
from flask import session, flash, redirect, url_for, request, jsonify


# ============================================================
# ROLES
# ============================================================
def _lista_env(nombre, por_defecto):
    valor = os.environ.get(nombre, por_defecto)
    return {v.strip().lower() for v in valor.split(',') if v.strip()}


# Roles con acceso total a Configuración y seguridad (empresas, usuarios, correlativos, parámetros)
ROLES_ADMIN = _lista_env('ROLES_ADMIN', 'admin,administrador,superadmin,gerencia_total,gerencia')

# Roles que pueden validar / aceptar / rechazar cotizaciones.
# Se conservan los valores que ya usaba el sistema (hellen, erika) para no romper usuarios actuales.
ROLES_APROBADORES = _lista_env(
    'ROLES_APROBADORES',
    'hellen,erika,admin,superadmin,administrador,gerencia_total,gerencia,supervisor'
)


def rol_actual():
    return (session.get('rol') or '').strip().lower()


def es_admin():
    # Usuario configurado en el ERP: manda su rol ERP (GERENCIA_TOTAL), no usuarios.rol (21/10/2026)
    if 'admin_erp' in session:
        return bool(session.get('admin_erp'))
    return rol_actual() in ROLES_ADMIN


def es_aprobador():
    return rol_actual() in ROLES_APROBADORES or es_admin()


def _es_peticion_api():
    return '/api/' in request.path or request.is_json or \
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario_id' not in session:
            if _es_peticion_api():
                return jsonify({'success': False, 'error': 'Sesión expirada o no autorizada. Inicia sesión.'}), 401
            flash('Por favor, inicia sesión para acceder.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario_id' not in session:
            return login_required(f)(*args, **kwargs)
        if not es_admin():
            if _es_peticion_api():
                return jsonify({'success': False, 'error': 'No tienes permisos de administrador para esta acción.'}), 403
            flash('No tienes permisos para acceder a esa sección.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


# ============================================================
# CÁLCULOS COMERCIALES (IGV PERÚ)
# ============================================================
def tasa_igv():
    """Tasa de IGV vigente (18% por defecto). Se puede cambiar con la variable IGV_TASA."""
    try:
        return Decimal(str(os.environ.get('IGV_TASA', '0.18')))
    except Exception:
        return Decimal('0.18')


def a_decimal(valor, por_defecto='0'):
    """Convierte números o textos ('1,234.50', '', None) a Decimal de forma segura."""
    if valor is None or valor == '':
        return Decimal(por_defecto)
    if isinstance(valor, Decimal):
        return valor
    try:
        return Decimal(str(valor).replace(',', '').strip() or por_defecto)
    except Exception:
        return Decimal(por_defecto)


def redondear(valor, decimales=2):
    q = Decimal(1).scaleb(-decimales)
    return a_decimal(valor).quantize(q, rounding=ROUND_HALF_UP)


def calcular_totales(lineas, descuento_valor=0, descuento_tipo='%'):
    """
    Calcula subtotal, descuento, IGV y total a partir de líneas
    [{'cantidad': x, 'precio': valor_unitario_sin_igv}, ...].
    descuento_tipo: '%' o 'porcentaje' => porcentaje; cualquier otro => monto fijo.
    Devuelve dict con Decimals redondeados a 2 decimales.
    """
    subtotal = sum((a_decimal(l.get('cantidad')) * a_decimal(l.get('precio')) for l in lineas), Decimal('0'))
    dv = a_decimal(descuento_valor)
    if dv < 0:
        dv = Decimal('0')
    if (descuento_tipo or '%') in ('%', 'porcentaje', 'pct'):
        descuento = subtotal * min(dv, Decimal('100')) / Decimal('100')
    else:
        descuento = min(dv, subtotal)
    base = subtotal - descuento
    igv = base * tasa_igv()
    total = base + igv
    return {
        'subtotal': redondear(subtotal),
        'descuento': redondear(descuento),
        'base_imponible': redondear(base),
        'igv': redondear(igv),
        'total': redondear(redondear(base) + redondear(igv)),
    }


def totales_consistentes(subtotal, igv, total, tolerancia='0.05'):
    """Verifica que total = subtotal + igv (con tolerancia de redondeo)."""
    return abs(a_decimal(subtotal) + a_decimal(igv) - a_decimal(total)) <= a_decimal(tolerancia)


# ============================================================
# NUMERACIÓN SEGURA (evita números duplicados)
# ============================================================
def bloquear_numeracion(cur, clave):
    """Bloqueo transaccional para generar correlativos sin duplicados entre usuarios simultáneos."""
    cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (clave,))


# ============================================================
# ID DE EMPRESA (en Supabase es UUID; en bases antiguas, entero)
# ============================================================
_RE_UUID = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')


def columnas_usuario_antiguas(data):
    """Valores para las columnas antiguas de usuarios que en Supabase son obligatorias
    (usuario, nombre_completo, password, rol). Sin contraseña se guarda una clave aleatoria:
    el usuario no puede entrar hasta que un administrador le asigne una."""
    import secrets
    from werkzeug.security import generate_password_hash
    usuario = (data.get('usuario_sistema') or '').strip()
    nombre = (data.get('nombres_apellidos') or '').strip() or usuario
    clave = data.get('password') or secrets.token_urlsafe(24)
    rol = (data.get('rol') or '').strip() or 'usuario'
    return usuario, nombre, generate_password_hash(clave), rol


def id_empresa(valor):
    """Devuelve el id de empresa normalizado (UUID en texto o entero positivo), o None si no es válido."""
    if valor is None or isinstance(valor, bool):
        return None
    texto = str(valor).strip()
    if _RE_UUID.match(texto):
        return texto.lower()
    if texto.isdigit() and int(texto) > 0:
        return int(texto)
    return None


# ============================================================
# CONDICIÓN DE PAGO Y TEXTOS (pedido de Erika 19/10/2026)
# ============================================================
def normalizar_condicion(texto):
    """Escribe la condición de pago siempre igual: 'Contado', 'Contra entrega' o 'Crédito N días'.
    Antes convivían 'Credito 45 Dias', 'Crédito 45 días' y '45', y la factura no los reconocía
    (salía "Contado" aunque el PC fuera a crédito). Devuelve '' si viene vacío."""
    t = (texto or '').strip()
    if not t or t.lower() in ('seleccione', 'personalizado', '--', '-'):
        return ''
    bajo = t.lower().replace('é', 'e').replace('í', 'i')
    numero = re.search(r'(\d+)', bajo)
    if 'contra' in bajo and 'entrega' in bajo:
        return 'Contra entrega'
    if 'contado' in bajo and not numero:
        return 'Contado'
    if numero and 'letra' not in bajo and ('credito' in bajo or 'dia' in bajo or bajo.isdigit()):
        dias = int(numero.group(1))
        return 'Contado' if dias == 0 else f'Crédito {dias} días'
    return t


def dias_de_condicion(texto):
    """Días de crédito de una condición ('Crédito 30 días' -> 30; 'Contado' -> 0)."""
    m = re.search(r'(\d+)', normalizar_condicion(texto))
    return int(m.group(1)) if m else 0


def mayuscula_inicial(texto):
    """Primera letra en mayúscula (observaciones de facturas); el resto se respeta tal cual."""
    t = (texto or '').strip()
    for i, c in enumerate(t):
        if c.isalpha():
            return t[:i] + c.upper() + t[i + 1:]
    return t

# Bancos en una sola lista (Erika 22/10/2026: "si no lo van a escribir con diferentes formas").
# La misma lista está en static/js/lista_bancos.js (desplegables de pago, cobro, proveedores y planilla).
BANCOS_PERU = ('BCP', 'BBVA', 'Interbank', 'Scotiabank', 'BanBif', 'Banco de la Nación', 'Pichincha', 'MiBanco',
               'Banco GNB', 'Banco Falabella', 'Banco Ripley', 'Caja Arequipa', 'Caja Huancayo', 'Caja Piura',
               'Caja Cusco', 'Caja Trujillo', 'Caja Sullana', 'Caja Municipal de Lima')
_ALIAS_BANCO = (('credito', 'BCP'), ('bcp', 'BCP'), ('bbva', 'BBVA'), ('continental', 'BBVA'), ('interbank', 'Interbank'),
                ('ibk', 'Interbank'), ('scotia', 'Scotiabank'), ('banbif', 'BanBif'), ('interamericano', 'BanBif'),
                ('nacion', 'Banco de la Nación'), ('bn', 'Banco de la Nación'), ('pichincha', 'Pichincha'),
                ('mibanco', 'MiBanco'), ('gnb', 'Banco GNB'), ('falabella', 'Banco Falabella'), ('ripley', 'Banco Ripley'),
                ('arequipa', 'Caja Arequipa'), ('huancayo', 'Caja Huancayo'), ('piura', 'Caja Piura'),
                ('cusco', 'Caja Cusco'), ('trujillo', 'Caja Trujillo'), ('sullana', 'Caja Sullana'),
                ('lima', 'Caja Municipal de Lima'))


def normalizar_banco(texto):
    """'bcp ', 'Banco de Credito', 'BBVA Continental' -> 'BCP', 'BBVA'. Lo que no reconoce queda como se escribió."""
    import unicodedata
    original = re.sub(r'\s+', ' ', str(texto or '')).strip()
    if not original:
        return None
    t = unicodedata.normalize('NFKD', original).encode('ascii', 'ignore').decode().lower()
    palabras = set(re.findall(r'[a-z]+', t))
    for clave, nombre in _ALIAS_BANCO:
        if clave in palabras or (len(clave) > 3 and clave in t):
            return nombre
    return original[:80]
