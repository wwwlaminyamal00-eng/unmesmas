"""Agente de retención del cliente (Erika, 27/10/2026 20:34).

La retención del 3% del IGV solo la hace un cliente que SUNAT designó "agente de retención" (y en facturas de más
de S/ 700). Por eso cada cliente lleva "Agente de retención: Sí / No":
  - se consulta solo en el padrón público de SUNAT (archivo de agentes de retención, se baja una vez al día);
  - si SUNAT no responde, se puede marcar a mano (solo aprobadores), con auditoría: quién, cuándo y por qué.
En la factura: si el cliente NO es agente, no hay retención (el servidor la quita); si SÍ es, se aplica.
Sin dato, la factura sigue como antes. Migración 039 (en la base de pruebas las columnas se crean aquí).
"""
import io
import re
import threading
import time
import zipfile

from flask import Blueprint, jsonify, request, session

from database import db_query, db_tx

agente_retencion_bp = Blueprint('agente_retencion', __name__)

URL_PADRON = 'https://www.sunat.gob.pe/descargaPRR/agenRet_TXT.zip'
VIGENCIA_PADRON = 24 * 3600      # se vuelve a bajar una vez al día
REVISAR_CADA_DIAS = 30           # un cliente se vuelve a consultar cada 30 días

SQL_DDL = """
    ALTER TABLE clientes ADD COLUMN IF NOT EXISTS agente_retencion BOOLEAN;
    ALTER TABLE clientes ADD COLUMN IF NOT EXISTS agente_retencion_fuente VARCHAR(20);
    ALTER TABLE clientes ADD COLUMN IF NOT EXISTS agente_retencion_desde VARCHAR(20);
    ALTER TABLE clientes ADD COLUMN IF NOT EXISTS agente_retencion_revisado_en TIMESTAMP;
    ALTER TABLE clientes ADD COLUMN IF NOT EXISTS agente_retencion_revisado_por VARCHAR(120)
"""

_listo = False
_lock = threading.Lock()
_padron = {'datos': None, 'cuando': 0.0}
_lock_padron = threading.Lock()


class ErrorPadron(Exception):
    pass


def asegurar_columnas():
    global _listo
    if _listo:
        return
    with _lock:
        if _listo:
            return
        with db_tx() as conn:
            cur = conn.cursor()
            cur.execute("""SELECT COUNT(*) FROM information_schema.columns
                           WHERE table_name = 'clientes' AND column_name LIKE 'agente_retencion%%'""")
            if cur.fetchone()[0] < 5:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext('agente_ret_ddl'))")
                for s in (x.strip() for x in SQL_DDL.split(';')):
                    if s:
                        cur.execute(s)
        _listo = True


# ------------------------------------------------------------
# Padrón de SUNAT
# ------------------------------------------------------------
def leer_padron(contenido):
    """{ruc: 'desde'} a partir del ZIP (o del TXT) del padrón: líneas 'RUC|RAZÓN SOCIAL|A PARTIR DEL|RESOLUCIÓN|'."""
    if contenido[:2] == b'PK':
        with zipfile.ZipFile(io.BytesIO(contenido)) as z:
            nombre = next((n for n in z.namelist() if n.lower().endswith('.txt')), None)
            if not nombre:
                raise ErrorPadron('El archivo de SUNAT no trae el padrón.')
            contenido = z.read(nombre)
    texto = contenido.decode('latin-1', errors='replace')
    datos = {}
    for linea in texto.splitlines():
        partes = linea.split('|')
        ruc = partes[0].strip() if partes else ''
        if re.fullmatch(r'\d{11}', ruc):
            datos[ruc] = partes[2].strip() if len(partes) > 2 else ''
    if len(datos) < 100:
        raise ErrorPadron('El padrón de SUNAT llegó incompleto.')
    return datos


def _bajar_padron():
    import requests
    try:
        r = requests.get(URL_PADRON, timeout=40, headers={'User-Agent': 'Mozilla/5.0 (ERP KCF)'})
    except Exception as e:
        raise ErrorPadron(f'No se pudo conectar con SUNAT ({type(e).__name__}).')
    if r.status_code != 200 or not r.content:
        raise ErrorPadron(f'SUNAT no entregó el padrón (respuesta {r.status_code}).')
    return leer_padron(r.content)


def padron():
    with _lock_padron:
        if _padron['datos'] is None or time.time() - _padron['cuando'] > VIGENCIA_PADRON:
            _padron['datos'] = _bajar_padron()
            _padron['cuando'] = time.time()
        return _padron['datos']


# ------------------------------------------------------------
# Cliente
# ------------------------------------------------------------
def _cliente(ruc):
    asegurar_columnas()
    filas = db_query("""SELECT id, razon_social, agente_retencion, agente_retencion_fuente, agente_retencion_desde,
                               agente_retencion_revisado_en, agente_retencion_revisado_por
                        FROM clientes WHERE numero_documento = %s ORDER BY id LIMIT 1""", (ruc,))
    return filas[0] if filas else None


def _formato(c, ruc, aviso=None):
    if not c:
        return {'ruc': ruc, 'agente': None, 'fuente': None, 'desde': None, 'revisado_en': None, 'aviso': aviso}
    rev = c.get('agente_retencion_revisado_en')
    return {'ruc': ruc, 'cliente_id': c['id'], 'agente': c.get('agente_retencion'),
            'fuente': c.get('agente_retencion_fuente'), 'desde': c.get('agente_retencion_desde'),
            'revisado_en': rev.strftime('%d/%m/%Y %H:%M') if hasattr(rev, 'strftime') else rev,
            'revisado_por': c.get('agente_retencion_revisado_por'), 'aviso': aviso}


def _guardar(c, valor, fuente, desde, quien):
    db_query("""UPDATE clientes SET agente_retencion = %s, agente_retencion_fuente = %s, agente_retencion_desde = %s,
                       agente_retencion_revisado_en = (NOW() AT TIME ZONE 'America/Lima'), agente_retencion_revisado_por = %s
                WHERE id = %s RETURNING id""", (valor, fuente, desde or None, (quien or '')[:120] or None, c['id']))
    if c.get('agente_retencion') != valor:
        try:
            from routes.auditoria import registrar_auditoria
            registrar_auditoria('ACTUALIZAR', 'Maestros', 'clientes', c['id'],
                                antes={'agente_retencion': c.get('agente_retencion')},
                                despues={'agente_retencion': valor, 'fuente': fuente},
                                detalle=f"Agente de retención de {c.get('razon_social') or c['id']}: "
                                        f"{'Sí' if valor else 'No'} ({fuente})")
        except Exception as e:
            print(f"⚠️ Auditoría de agente de retención: {e}")


def consultar(ruc, forzar=False):
    """Estado del cliente; si no tiene dato o está viejo, lo consulta en el padrón de SUNAT y lo guarda.
    Lo marcado a mano no se cambia solo."""
    ruc = re.sub(r'\D', '', str(ruc or ''))
    if len(ruc) != 11:
        return _formato(None, ruc, 'RUC inválido')
    c = _cliente(ruc)
    if c and c.get('agente_retencion_fuente') == 'Manual' and not forzar:
        return _formato(c, ruc)
    rev = c.get('agente_retencion_revisado_en') if c else None
    viejo = rev is None or not hasattr(rev, 'timestamp') or time.time() - rev.timestamp() > REVISAR_CADA_DIAS * 86400
    if c and c.get('agente_retencion') is not None and not viejo and not forzar:
        return _formato(c, ruc)
    try:
        datos = padron()
    except ErrorPadron as e:
        return _formato(c, ruc, f'{e} Puedes marcarlo a mano.')
    es = ruc in datos
    if not c:
        return {'ruc': ruc, 'agente': es, 'fuente': 'SUNAT', 'desde': datos.get(ruc), 'revisado_en': None, 'aviso': None}
    _guardar(c, es, 'SUNAT', datos.get(ruc), 'Padrón SUNAT')
    return _formato(_cliente(ruc), ruc)


def agente_de_ruc(ruc):
    """True / False / None (sin dato) según lo guardado en el cliente. No consulta SUNAT (es para guardar facturas)."""
    ruc = re.sub(r'\D', '', str(ruc or ''))
    if len(ruc) != 11:
        return None
    try:
        c = _cliente(ruc)
    except Exception:
        return None
    return c.get('agente_retencion') if c else None


@agente_retencion_bp.route('/ventas/api/agente-retencion', methods=['GET'])
def api_consultar():
    if not session.get('usuario_id'):
        return jsonify({'success': False, 'error': 'Inicia sesión'}), 401
    return jsonify({'success': True, 'data': consultar(request.args.get('ruc'), request.args.get('forzar') == '1')})


@agente_retencion_bp.route('/ventas/api/agente-retencion/manual', methods=['POST'])
def api_manual():
    if not session.get('usuario_id'):
        return jsonify({'success': False, 'error': 'Inicia sesión'}), 401
    from utils import es_aprobador
    if not es_aprobador():
        return jsonify({'success': False, 'error': 'Solo un aprobador puede marcar a mano si el cliente es agente de retención.'}), 403
    d = request.get_json(silent=True) or {}
    ruc = re.sub(r'\D', '', str(d.get('ruc') or ''))
    valor = d.get('agente')
    if len(ruc) != 11 or valor not in (True, False):
        return jsonify({'success': False, 'error': 'Indica el RUC y si es agente de retención (Sí o No).'}), 400
    c = _cliente(ruc)
    if not c:
        return jsonify({'success': False, 'error': 'Primero registra al cliente en Maestros ▸ Clientes.'}), 404
    quien = session.get('nombre_completo') or session.get('nombre') or session.get('usuario') or ''
    _guardar(c, bool(valor), 'Manual', None, quien)
    return jsonify({'success': True, 'data': _formato(_cliente(ruc), ruc)})
