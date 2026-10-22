# routes/bancos.py - Conciliación bancaria (pedido de Erika, 21/10/2026 23:30)
#
# Qué hace (en simple):
#   1. Se sube el extracto del banco tal como lo descarga la banca por internet (BCP, BBVA, Interbank,
#      Scotiabank, BanBif, Banco de la Nación...): Excel (.xlsx / .xls) o CSV / TXT. Las columnas se reconocen solas.
#   2. Cada movimiento del banco se cruza AUTOMÁTICAMENTE con los cobros y pagos registrados en Finanzas:
#        - mismo monto y mismo N° de operación          -> conciliado
#        - mismo monto, fecha cercana y una sola opción  -> conciliado
#        - ITF, comisiones, mantenimiento                -> "Gasto del banco"
#   3. Quedan en rojo las dos cosas que importan para evitar robos o errores:
#        - "En el banco, falta en el ERP": entró o salió plata y nadie la registró.
#        - "En el ERP, no está en el banco": alguien registró un cobro o pago que el banco no muestra.
#   4. Lo que no se cruza solo se resuelve con un clic: conciliar con la opción sugerida, registrar el cobro o pago
#      de la factura que coincide (queda conciliado al instante) o explicarlo con una nota.
#
# Reglas:
#   - Solo LEE ventas, compras y Finanzas. Escribe únicamente en sus tablas bancos_* (y, si el usuario lo pide con el
#     botón "Registrar cobro / pago", usa la misma API de Finanzas, con sus mismas validaciones).
#   - Acceso: administrador (Gerencia total) o quien tenga "Ver" en "Conciliación bancaria". Se valida en el servidor.
#   - Subir el mismo extracto dos veces no duplica nada (cada movimiento tiene una clave única).
#   - Todo queda con usuario y fecha y hora de Lima; deshacer pide motivo y queda en el historial.
import csv
import hashlib
import io
import re
import threading
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal, InvalidOperation

from flask import Blueprint, render_template, request, jsonify, session
from psycopg2.extras import RealDictCursor, Json

from database import db_query, db_tx
from utils import a_decimal, redondear, es_admin, id_empresa
from routes.multiempresa import empresas as lista_empresas, empresa_actual, empresa_por_id

bancos_bp = Blueprint('bancos', __name__)


def _ahora():
    """Fecha y hora de Lima (el servidor de Render está en UTC)."""
    return datetime.now(ZoneInfo('America/Lima')).replace(tzinfo=None)

BANCOS = ('BCP', 'BBVA', 'Interbank', 'Scotiabank', 'BanBif', 'Banco de la Nación', 'Pichincha', 'Caja / otro')
ESTADOS = ('Pendiente', 'Conciliado', 'Gasto del banco', 'Revisado')
DIAS_VENTANA = 5               # fecha del banco vs fecha registrada en Finanzas (± días)
TOLERANCIA = Decimal('0.01')
# Descripciones que son gastos del propio banco (no son cobros ni pagos de clientes / proveedores)
PALABRAS_GASTO = ('itf', 'comision', 'comis ', 'mantenimiento', 'mant cta', 'portes', 'cargo por', 'impuesto',
                  'interes', 'seguro desgr', 'cuota manejo', 'membresia', 'gasto bancario', 'cobro de servicio')


class ErrorBancos(Exception):
    pass


# ============================================================
# PERMISO (en el servidor)
# ============================================================
def puede_ver_bancos():
    if es_admin():
        return True
    try:
        from routes.acceso import acceso_usuario
        acc = acceso_usuario()
    except Exception:
        return False
    return bool(acc.get('configurado') and 'bancos' in acc.get('modulos', set()))


@bancos_bp.before_request
def _proteger():
    if 'usuario_id' not in session:
        return None   # main.control_de_acceso ya responde
    if not puede_ver_bancos():
        msg = ('No tienes permiso para entrar a Conciliación bancaria. Pídeselo al administrador en '
               'Configuración ▸ Usuarios y permisos.')
        if '/api/' in request.path:
            return jsonify({'success': False, 'error': msg, 'codigo': 'sin_permiso'}), 403
        from flask import flash, redirect, url_for
        flash(msg, 'error')
        return redirect(url_for('index'))
    asegurar_tablas()
    return None


# ============================================================
# TABLAS PROPIAS (equivalente: migrations/019_conciliacion_bancaria.sql)
# ============================================================
SQL_DDL_BANCOS = """
    CREATE TABLE IF NOT EXISTS bancos_extractos (
        id SERIAL PRIMARY KEY,
        empresa_id VARCHAR(64) NOT NULL,
        banco VARCHAR(40) NOT NULL,
        cuenta VARCHAR(60),
        moneda VARCHAR(5) NOT NULL DEFAULT 'PEN',
        archivo VARCHAR(255),
        desde DATE,
        hasta DATE,
        filas INTEGER NOT NULL DEFAULT 0,
        nuevas INTEGER NOT NULL DEFAULT 0,
        repetidas INTEGER NOT NULL DEFAULT 0,
        creado_por VARCHAR(150),
        creado_en TIMESTAMP DEFAULT NOW(),
        anulado_por VARCHAR(150),
        anulado_en TIMESTAMP,
        motivo_anulacion TEXT
    );
    CREATE TABLE IF NOT EXISTS bancos_movimientos (
        id SERIAL PRIMARY KEY,
        extracto_id INTEGER NOT NULL REFERENCES bancos_extractos(id) ON DELETE CASCADE,
        empresa_id VARCHAR(64) NOT NULL,
        banco VARCHAR(40) NOT NULL,
        cuenta VARCHAR(60),
        moneda VARCHAR(5) NOT NULL DEFAULT 'PEN',
        fecha DATE NOT NULL,
        descripcion TEXT,
        numero_operacion VARCHAR(80),
        monto NUMERIC(14,2) NOT NULL,
        saldo NUMERIC(14,2),
        clave VARCHAR(64) NOT NULL UNIQUE,
        estado VARCHAR(20) NOT NULL DEFAULT 'Pendiente'
               CHECK (estado IN ('Pendiente', 'Conciliado', 'Gasto del banco', 'Revisado')),
        finanzas_pago_id INTEGER,
        forma VARCHAR(40),
        nota TEXT,
        conciliado_por VARCHAR(150),
        conciliado_en TIMESTAMP,
        historial JSONB NOT NULL DEFAULT '[]'::jsonb,
        creado_en TIMESTAMP DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_bancos_mov_empresa ON bancos_movimientos (empresa_id, fecha);
    CREATE UNIQUE INDEX IF NOT EXISTS uq_bancos_mov_pago ON bancos_movimientos (finanzas_pago_id)
        WHERE finanzas_pago_id IS NOT NULL;
    ALTER TABLE bancos_extractos ENABLE ROW LEVEL SECURITY;
    ALTER TABLE bancos_movimientos ENABLE ROW LEVEL SECURITY;
"""
_tablas = {'ok': False}
_lock = threading.Lock()


def asegurar_tablas():
    if _tablas['ok']:
        return
    with _lock:
        if _tablas['ok']:
            return
        from routes.finanzas import asegurar_tablas_finanzas
        asegurar_tablas_finanzas()
        with db_tx() as conn:
            cur = conn.cursor()
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('bancos_ddl'))")
            cur.execute(SQL_DDL_BANCOS)
        _tablas['ok'] = True


# ============================================================
# AYUDAS
# ============================================================
def _usuario():
    return session.get('nombre_completo') or session.get('usuario') or f"Usuario {session.get('usuario_id')}"


def _n(v):
    return float(redondear(v or 0, 2))


def _f(v):
    if isinstance(v, datetime):
        return v.strftime('%Y-%m-%d %H:%M')
    if isinstance(v, date):
        return v.isoformat()
    return v


def _norm(txt):
    t = unicodedata.normalize('NFKD', str(txt or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9]+', ' ', t)).strip()


def _digitos(txt):
    d = re.sub(r'\D', '', str(txt or ''))
    return d.lstrip('0') or ('0' if d else '')


def _misma_operacion(a, b):
    """N° de operación del banco vs el escrito en Finanzas: iguales sin ceros a la izquierda o uno termina en el otro."""
    x, y = _digitos(a), _digitos(b)
    if len(x) < 4 or len(y) < 4:
        return False
    return x == y or x.endswith(y) or y.endswith(x)


def _empresa(eid_txt=None):
    eid = id_empresa(eid_txt) if eid_txt else None
    e = empresa_por_id(eid) if eid else None
    e = e or empresa_actual()
    if not e:
        lista = lista_empresas()
        e = lista[0] if lista else None
    if not e:
        raise ErrorBancos('No hay empresas configuradas (Configuración ▸ Empresas).')
    return e


def _historial(cur, mov_id, accion, detalle=None):
    cur.execute("""UPDATE bancos_movimientos SET historial = historial || %s::jsonb WHERE id = %s""",
                (Json([{'accion': accion, 'detalle': detalle, 'usuario': _usuario(),
                        'fecha': _ahora().strftime('%Y-%m-%d %H:%M')}]), mov_id))


def es_gasto_bancario(descripcion):
    d = ' ' + _norm(descripcion) + ' '
    return any((' ' + p) in d for p in PALABRAS_GASTO)


# ============================================================
# LECTURA DEL EXTRACTO (columnas reconocidas solas)
# ============================================================
def _filas_archivo(nombre, contenido):
    """Lista de filas (listas de celdas) de un Excel, CSV o TXT."""
    ext = (nombre or '').lower().rsplit('.', 1)[-1]
    if ext in ('xlsx', 'xlsm'):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
        mejor = []
        for ws in wb.worksheets:
            filas = [list(f) for f in ws.iter_rows(values_only=True)]
            if len(filas) > len(mejor):
                mejor = filas
        return mejor
    if ext == 'xls':
        cabeza = contenido[:2048].lower()
        if b'<table' in cabeza or b'<html' in cabeza or b'<!doctype' in cabeza:
            return _filas_html(contenido)          # algunos bancos bajan "xls" que en realidad son páginas web
        try:
            import xlrd
        except ImportError:
            raise ErrorBancos('Para archivos .xls antiguos falta instalar "xlrd". Ábrelo en Excel y guárdalo como .xlsx.')
        libro = xlrd.open_workbook(file_contents=contenido)
        mejor = []
        for hoja in libro.sheets():
            filas = []
            for i in range(hoja.nrows):
                fila = []
                for c in hoja.row(i):
                    if c.ctype == xlrd.XL_CELL_DATE:
                        fila.append(datetime(*xlrd.xldate_as_tuple(c.value, libro.datemode)))
                    else:
                        fila.append(c.value)
                filas.append(fila)
            if len(filas) > len(mejor):
                mejor = filas
        return mejor
    if ext in ('htm', 'html'):
        return _filas_html(contenido)
    # CSV / TXT: separador ; , | o tabulador
    texto = None
    for cod in ('utf-8-sig', 'latin-1'):
        try:
            texto = contenido.decode(cod)
            break
        except UnicodeDecodeError:
            continue
    muestra = texto[:4000]
    sep = max((';', ',', '|', '\t'), key=lambda s: muestra.count(s))
    return [fila for fila in csv.reader(io.StringIO(texto), delimiter=sep)]


def _filas_html(contenido):
    from bs4 import BeautifulSoup
    sopa = BeautifulSoup(contenido, 'html.parser')
    mejor = []
    for tabla in sopa.find_all('table'):
        filas = [[c.get_text(' ', strip=True) for c in tr.find_all(['td', 'th'])] for tr in tabla.find_all('tr')]
        if len(filas) > len(mejor):
            mejor = filas
    return mejor


def _tipo_columna(cab):
    c = _norm(cab)
    if not c:
        return None
    palabras = c.split()
    if 'saldo' in palabras:
        return 'saldo'
    if 'fecha' in palabras or c.startswith('f ') or c == 'f operacion':
        if any(p in c for p in ('valuta', 'valor', 'proceso', 'contable')):
            return 'fecha2'
        return 'fecha'
    if 'hora' in palabras or 'moneda' in palabras:
        return None
    if any(p in palabras for p in ('cargo', 'cargos', 'debito', 'debitos', 'retiro', 'retiros', 'egreso', 'egresos', 'salida')):
        return 'cargo'
    if any(p in palabras for p in ('abono', 'abonos', 'credito', 'creditos', 'deposito', 'depositos', 'ingreso', 'ingresos')):
        return 'abono'
    if any(p in palabras for p in ('monto', 'importe', 'montos', 'importes')):
        return 'monto'
    if 'operacion' in palabras and any(p in palabras for p in ('n', 'no', 'nro', 'num', 'numero')):
        return 'operacion'
    if c in ('operacion numero', 'n operacion', 'nro operacion', 'numero operacion', 'operacion', 'n doc', 'no doc',
             'nro doc', 'numero de documento', 'n documento', 'referencia', 'nro de operacion', 'n de operacion',
             'numero de operacion', 'n de documento', 'cod operacion', 'codigo operacion'):
        return 'operacion'
    if any(p in palabras for p in ('descripcion', 'concepto', 'detalle', 'glosa', 'movimiento', 'referencia2',
                                   'beneficiario', 'ordenante')):
        return 'descripcion'
    return None


def _encontrar_cabecera(filas):
    """(índice de la fila de títulos, {tipo: [columnas]}). Busca en las primeras 40 filas."""
    for i, fila in enumerate(filas[:40]):
        tipos = defaultdict(list)
        for j, celda in enumerate(fila):
            t = _tipo_columna(celda)
            if t:
                tipos[t].append(j)
        tiene_monto = 'monto' in tipos or 'cargo' in tipos or 'abono' in tipos
        if ('fecha' in tipos or 'fecha2' in tipos) and tiene_monto:
            if 'fecha' not in tipos:
                tipos['fecha'] = tipos.pop('fecha2')
            return i, dict(tipos)
    raise ErrorBancos('No encontré las columnas del extracto (Fecha y Monto, o Cargo y Abono). '
                      'Sube el archivo tal como lo descargas de la banca por internet.')


def leer_monto(v):
    """'S/ 1,234.56', '-1.234,56', '(150.00)', 1234.5 -> Decimal (None si está vacío)."""
    if v is None or v == '':
        return None
    if isinstance(v, (int, float, Decimal)):
        return redondear(v)
    t = str(v).strip()
    negativo = t.startswith('(') and t.endswith(')') or t.startswith('-') or t.endswith('-')
    t = re.sub(r'[^\d,.]', '', t)
    if not t or not re.search(r'\d', t):
        return None
    if ',' in t and '.' in t:
        if t.rfind(',') > t.rfind('.'):
            t = t.replace('.', '').replace(',', '.')
        else:
            t = t.replace(',', '')
    elif ',' in t:
        partes = t.split(',')
        t = t.replace(',', '') if len(partes[-1]) == 3 and len(partes) >= 2 and len(partes[0]) <= 3 else t.replace(',', '.')
    elif t.count('.') > 1:
        t = t.replace('.', '')
    try:
        d = Decimal(t)
    except InvalidOperation:
        return None
    return redondear(-d if negativo else d)


def leer_fecha(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)) and 20000 < v < 80000:     # número de serie de Excel
        return date(1899, 12, 30) + timedelta(days=int(v))
    t = str(v or '').strip()
    m = re.match(r'^(\d{4})[-/](\d{1,2})[-/](\d{1,2})', t)
    if m:
        a, mes, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.match(r'^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})', t)
        if not m:
            return None
        d, mes, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if a < 100:
            a += 2000
    try:
        return date(a, mes, d)
    except ValueError:
        return None


def leer_extracto(nombre, contenido):
    """Movimientos del archivo: [{'fecha', 'descripcion', 'numero_operacion', 'monto', 'saldo'}].
    monto > 0 = abono (entra plata), monto < 0 = cargo (sale plata)."""
    filas = _filas_archivo(nombre, contenido)
    if not filas:
        raise ErrorBancos('El archivo está vacío.')
    i, cols = _encontrar_cabecera(filas)

    def celda(fila, tipo, n=0):
        idx = cols.get(tipo) or []
        return fila[idx[n]] if len(idx) > n and idx[n] < len(fila) else None

    salida = []
    for fila in filas[i + 1:]:
        if not fila or all(c in (None, '') for c in fila):
            continue
        fecha = leer_fecha(celda(fila, 'fecha'))
        if not fecha:
            continue                         # filas de totales, subtítulos o saldo inicial sin fecha
        if 'monto' in cols:
            monto = leer_monto(celda(fila, 'monto'))
        else:
            cargo = leer_monto(celda(fila, 'cargo')) if 'cargo' in cols else None
            abono = leer_monto(celda(fila, 'abono')) if 'abono' in cols else None
            monto = (abs(abono) if abono else Decimal('0')) - (abs(cargo) if cargo else Decimal('0'))
        if monto is None or monto == 0:
            continue
        textos = []
        for j in cols.get('descripcion', []):
            v = fila[j] if j < len(fila) else None
            if v not in (None, '') and str(v).strip() not in textos:
                textos.append(str(v).strip())
        op = celda(fila, 'operacion')
        if isinstance(op, float) and op.is_integer():
            op = int(op)
        salida.append({'fecha': fecha, 'descripcion': ' · '.join(textos)[:500],
                       'numero_operacion': (str(op).strip() if op not in (None, '') else '')[:80] or None,
                       'monto': redondear(monto), 'saldo': leer_monto(celda(fila, 'saldo'))})
    if not salida:
        raise ErrorBancos('El archivo no tiene movimientos con fecha y monto.')
    return salida


def _clave(eid, banco, cuenta, mov, n):
    base = '|'.join([str(eid), banco, cuenta or '', mov['fecha'].isoformat(), f"{mov['monto']:.2f}",
                     _digitos(mov['numero_operacion']), _norm(mov['descripcion']), str(n)])
    return hashlib.sha256(base.encode()).hexdigest()


def guardar_extracto(e, banco, cuenta, moneda, archivo, movimientos):
    """Guarda los movimientos nuevos (los repetidos de un extracto anterior se saltan) y concilia."""
    eid = str(e['id'])
    vistos = defaultdict(int)
    with db_tx() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""INSERT INTO bancos_extractos (empresa_id, banco, cuenta, moneda, archivo, desde, hasta, filas, creado_por)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    (eid, banco, cuenta, moneda, archivo, min(m['fecha'] for m in movimientos),
                     max(m['fecha'] for m in movimientos), len(movimientos), _usuario()))
        ext_id = cur.fetchone()['id']
        nuevas = 0
        for m in movimientos:
            firma = (m['fecha'], m['monto'], _digitos(m['numero_operacion']), _norm(m['descripcion']))
            vistos[firma] += 1
            estado = 'Gasto del banco' if es_gasto_bancario(m['descripcion']) else 'Pendiente'
            cur.execute("""
                INSERT INTO bancos_movimientos (extracto_id, empresa_id, banco, cuenta, moneda, fecha, descripcion,
                    numero_operacion, monto, saldo, clave, estado, forma, conciliado_por, conciliado_en)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (clave) DO NOTHING RETURNING id""",
                        (ext_id, eid, banco, cuenta, moneda, m['fecha'], m['descripcion'], m['numero_operacion'],
                         m['monto'], m['saldo'], _clave(eid, banco, cuenta, m, vistos[firma]), estado,
                         'Automático (ITF / comisión)' if estado != 'Pendiente' else None,
                         'Sistema' if estado != 'Pendiente' else None, _ahora() if estado != 'Pendiente' else None))
            if cur.fetchone():
                nuevas += 1
        cur.execute("UPDATE bancos_extractos SET nuevas = %s, repetidas = %s WHERE id = %s",
                    (nuevas, len(movimientos) - nuevas, ext_id))
    auto = conciliar_automatico(eid)
    return {'id': ext_id, 'filas': len(movimientos), 'nuevas': nuevas, 'repetidas': len(movimientos) - nuevas,
            'conciliados': auto}


# ============================================================
# CRUCE CON FINANZAS
# ============================================================
def _pagos_libres(eid):
    """Cobros y pagos de Finanzas (no anulados, no en efectivo) que aún no están unidos a un movimiento del banco."""
    return db_query("""
        SELECT f.id, f.tipo, f.fecha, f.fecha_aviso, f.monto, f.metodo, f.banco, f.numero_operacion,
               f.documento_tabla, f.documento_id, f.documento_numero, f.tercero_nombre, f.tercero_documento,
               f.usuario_nombre, f.created_at
        FROM finanzas_pagos f
        WHERE f.estado <> 'Anulado' AND COALESCE(f.metodo, '') <> 'Efectivo'
          AND (f.empresa_id IS NULL OR f.empresa_id::text = %s)
          AND NOT EXISTS (SELECT 1 FROM bancos_movimientos b WHERE b.finanzas_pago_id = f.id)
    """, (eid,))


def _cerca(fecha_banco, pago):
    fechas = [x for x in (pago.get('fecha'), pago.get('fecha_aviso')) if x]
    return any(abs((fecha_banco - (x.date() if isinstance(x, datetime) else x)).days) <= DIAS_VENTANA for x in fechas)


def _signo_ok(monto, pago):
    return (monto > 0 and pago['tipo'] == 'COBRO') or (monto < 0 and pago['tipo'] == 'PAGO')


def _mismo_banco(mov, pago):
    b = _norm(pago.get('banco'))
    return not b or _norm(mov['banco']) in b or b in _norm(mov['banco'])


def conciliar_automatico(eid):
    """Une solo lo seguro. Devuelve cuántos movimientos se conciliaron."""
    pendientes = db_query("""SELECT id, fecha, monto, numero_operacion, banco, descripcion FROM bancos_movimientos
                             WHERE empresa_id = %s AND estado = 'Pendiente'
                               AND NOT historial @> '[{"accion": "Deshecho"}]'::jsonb
                             ORDER BY fecha, id""", (eid,))
    if not pendientes:
        return 0
    libres = _pagos_libres(eid)
    usados, pares = set(), []
    # 1) Mismo monto y mismo N° de operación
    for m in pendientes:
        for p in libres:
            if p['id'] in usados or not _signo_ok(m['monto'], p):
                continue
            if abs(abs(m['monto']) - p['monto']) <= TOLERANCIA and _misma_operacion(m['numero_operacion'], p['numero_operacion']):
                pares.append((m['id'], p['id'], 'Automático: monto y N° de operación'))
                usados.add(p['id'])
                m['_listo'] = True
                break
    # 2) Mismo monto, fecha cercana, mismo banco y una sola opción de cada lado
    candidatos = {}
    for m in pendientes:
        if m.get('_listo'):
            continue
        candidatos[m['id']] = [p for p in libres if p['id'] not in usados and _signo_ok(m['monto'], p)
                               and abs(abs(m['monto']) - p['monto']) <= TOLERANCIA and _cerca(m['fecha'], p)
                               and _mismo_banco(m, p)]
    por_pago = defaultdict(list)
    for mid, lista in candidatos.items():
        for p in lista:
            por_pago[p['id']].append(mid)
    for mid, lista in candidatos.items():
        if len(lista) == 1 and len(por_pago[lista[0]['id']]) == 1 and lista[0]['id'] not in usados:
            pares.append((mid, lista[0]['id'], 'Automático: monto y fecha'))
            usados.add(lista[0]['id'])
    if not pares:
        return 0
    with db_tx() as conn:
        cur = conn.cursor()
        for mid, pid, forma in pares:
            cur.execute("""UPDATE bancos_movimientos SET estado = 'Conciliado', finanzas_pago_id = %s, forma = %s,
                           conciliado_por = 'Sistema', conciliado_en = NOW()
                           WHERE id = %s AND estado = 'Pendiente'
                             AND NOT EXISTS (SELECT 1 FROM bancos_movimientos x WHERE x.finanzas_pago_id = %s)""",
                        (pid, forma, mid, pid))
            if cur.rowcount:
                _historial(cur, mid, 'Conciliado', forma)
    return len(pares)


def _facturas_con_saldo(eid, tipo):
    """CxC (tipo COBRO) o CxP (tipo PAGO) de la empresa con saldo pendiente, para sugerir 'Registrar cobro/pago'."""
    from routes.finanzas import SQL_CXC, SQL_CXP
    if tipo == 'COBRO':
        sql = SQL_CXC + (" AND COALESCE(UPPER(c.estado_sunat), 'BORRADOR') <> 'BORRADOR'"
                         " AND (c.empresa_id IS NULL OR c.empresa_id::text = %s)")
    else:
        sql = SQL_CXP + " AND (cp.empresa_id IS NULL OR cp.empresa_id::text = %s)"
    salida = []
    for f in db_query(sql, (eid,)):
        saldo = redondear(a_decimal(f['importe_cobrar']) - a_decimal(f['cobrado']) - a_decimal(f['notas_credito']))
        if saldo > 0:
            salida.append({'id': f['id'], 'documento': f['documento'], 'tercero': f['tercero'], 'ruc': f['ruc'],
                           'saldo': saldo, 'total': redondear(f['importe_cobrar'])})
    return salida


def _parecido_nombre(descripcion, nombre):
    d = set(w for w in _norm(descripcion).split() if len(w) > 3)
    n = set(w for w in _norm(nombre).split() if len(w) > 3 and w not in ('s', 'sac', 'eirl', 'srl'))
    return len(d & n)


def sugerencias(eid, mov, libres, facturas):
    """Opciones para un movimiento pendiente: cobros/pagos de Finanzas y facturas con el mismo monto."""
    monto = abs(a_decimal(mov['monto']))
    opciones = []
    for p in libres:
        if not _signo_ok(mov['monto'], p):
            continue
        dif = abs(monto - p['monto'])
        if dif > max(TOLERANCIA, monto * Decimal('0.02')):
            continue
        puntos = (3 if dif <= TOLERANCIA else 0) + (2 if _cerca(mov['fecha'], p) else 0) + \
                 (3 if _misma_operacion(mov['numero_operacion'], p['numero_operacion']) else 0) + \
                 _parecido_nombre(mov['descripcion'], p['tercero_nombre'])
        opciones.append({'tipo': 'movimiento', 'id': p['id'], 'puntos': puntos, 'fecha': _f(p['fecha']),
                         'tercero': p['tercero_nombre'], 'ruc': p['tercero_documento'], 'documento': p['documento_numero'],
                         'monto': _n(p['monto']), 'numero_operacion': p['numero_operacion'], 'banco': p['banco'],
                         'exacto': dif <= TOLERANCIA})
    lado = 'COBRO' if mov['monto'] > 0 else 'PAGO'
    for f in facturas.get(lado, []):
        if abs(monto - f['saldo']) <= TOLERANCIA or abs(monto - f['total']) <= TOLERANCIA:
            opciones.append({'tipo': 'factura', 'id': f['id'], 'puntos': 1 + _parecido_nombre(mov['descripcion'], f['tercero']),
                             'tercero': f['tercero'], 'ruc': f['ruc'], 'documento': f['documento'], 'monto': _n(f['saldo']),
                             'exacto': abs(monto - f['saldo']) <= TOLERANCIA})
    opciones.sort(key=lambda o: (-o['puntos'], o['tipo']))
    return opciones[:4]


# ============================================================
# RESUMEN
# ============================================================
def _mes(txt):
    m = re.match(r'^(\d{4})-(\d{2})$', (txt or '').strip())
    if not m or not 1 <= int(m.group(2)) <= 12:
        return None
    a, mm = int(m.group(1)), int(m.group(2))
    fin = (date(a + (mm == 12), mm % 12 + 1, 1) - timedelta(days=1))
    return date(a, mm, 1), fin


def resumen(e, mes_txt=None, banco=None):
    eid = str(e['id'])
    conciliar_automatico(eid)
    if not mes_txt:
        ult = db_query("SELECT MAX(fecha) AS f FROM bancos_movimientos WHERE empresa_id = %s", (eid,))
        f = ult[0]['f'] if ult and ult[0]['f'] else _ahora().date()
        mes_txt = f.strftime('%Y-%m')
    rango = _mes(mes_txt) or _mes(_ahora().date().strftime('%Y-%m'))
    desde, hasta = rango
    filtro_banco = " AND b.banco = %s" if banco else ""
    params = [eid, desde, hasta] + ([banco] if banco else [])
    movs = db_query(f"""
        SELECT b.*, f.tipo AS pago_tipo, f.fecha AS pago_fecha, f.tercero_nombre, f.tercero_documento,
               f.documento_numero, f.numero_operacion AS pago_operacion, f.monto AS pago_monto, f.usuario_nombre AS pago_usuario
        FROM bancos_movimientos b
        LEFT JOIN finanzas_pagos f ON f.id = b.finanzas_pago_id
        WHERE b.empresa_id = %s AND b.fecha BETWEEN %s AND %s {filtro_banco}
        ORDER BY b.fecha DESC, b.id DESC""", params)

    libres = _pagos_libres(eid)
    facturas = {'COBRO': _facturas_con_saldo(eid, 'COBRO'), 'PAGO': _facturas_con_saldo(eid, 'PAGO')}
    filas = []
    for m in movs:
        item = {k: _f(v) for k, v in m.items() if k not in ('historial', 'clave')}
        item['monto'] = _n(m['monto'])
        item['saldo'] = _n(m['saldo']) if m['saldo'] is not None else None
        item['historial'] = m['historial'] or []
        if m['estado'] == 'Pendiente':
            item['sugerencias'] = sugerencias(eid, m, libres, facturas)
        filas.append(item)

    # Cobros y pagos del ERP que el banco no muestra (solo dentro de las fechas que cubren los extractos subidos)
    cubiertos = db_query(f"""SELECT banco, MIN(fecha) AS desde, MAX(fecha) AS hasta FROM bancos_movimientos b
                             WHERE empresa_id = %s AND fecha BETWEEN %s AND %s {filtro_banco} GROUP BY banco""", params)
    sin_banco = []
    for p in libres:
        fp = p['fecha']
        for c in cubiertos:
            if c['desde'] <= fp <= c['hasta'] and _mismo_banco({'banco': c['banco']}, p):
                sin_banco.append({'id': p['id'], 'tipo': p['tipo'], 'fecha': _f(fp), 'tercero': p['tercero_nombre'],
                                  'ruc': p['tercero_documento'], 'documento': p['documento_numero'], 'monto': _n(p['monto']),
                                  'metodo': p['metodo'], 'banco': p['banco'], 'numero_operacion': p['numero_operacion'],
                                  'usuario': p['usuario_nombre'], 'registrado': _f(p['created_at'])})
                break
    sin_banco.sort(key=lambda x: x['fecha'], reverse=True)

    def suma(lista, cond=lambda x: True):
        return _n(sum((a_decimal(x['monto']) for x in lista if cond(x)), Decimal('0')))

    pend = [x for x in filas if x['estado'] == 'Pendiente']
    tarjetas = {
        'movimientos': len(filas),
        'conciliados': sum(1 for x in filas if x['estado'] in ('Conciliado', 'Revisado')),
        'pendientes_banco': len(pend),
        'pendientes_banco_entradas': suma(pend, lambda x: x['monto'] > 0),
        'pendientes_banco_salidas': suma(pend, lambda x: x['monto'] < 0),
        'pendientes_erp': len(sin_banco),
        'pendientes_erp_monto': suma(sin_banco),
        'gastos_banco': suma(filas, lambda x: x['estado'] == 'Gasto del banco'),
        'gastos_banco_n': sum(1 for x in filas if x['estado'] == 'Gasto del banco'),
    }
    extractos = db_query("""SELECT id, banco, cuenta, moneda, archivo, desde, hasta, filas, nuevas, repetidas, creado_por, creado_en
                            FROM bancos_extractos WHERE empresa_id = %s AND anulado_en IS NULL
                            ORDER BY creado_en DESC LIMIT 30""", (eid,))
    bancos_usados = [r['banco'] for r in db_query("SELECT DISTINCT banco FROM bancos_movimientos WHERE empresa_id = %s ORDER BY 1", (eid,))]
    return {'empresa': {'id': eid, 'codigo': e['codigo']}, 'mes': mes_txt, 'desde': desde.isoformat(),
            'hasta': hasta.isoformat(), 'banco': banco, 'tarjetas': tarjetas, 'movimientos': filas,
            'sin_banco': sin_banco, 'extractos': [{k: _f(v) for k, v in x.items()} for x in extractos],
            'bancos_usados': bancos_usados}


# ============================================================
# ACCIONES
# ============================================================
def _mov(cur, mov_id, eid):
    cur.execute("SELECT * FROM bancos_movimientos WHERE id = %s AND empresa_id = %s FOR UPDATE", (mov_id, eid))
    m = cur.fetchone()
    if not m:
        raise ErrorBancos('Movimiento no encontrado en esta empresa.')
    return m


def conciliar_manual(eid, mov_id, pago_id, nota=None):
    with db_tx() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        m = _mov(cur, mov_id, eid)
        if m['estado'] != 'Pendiente':
            raise ErrorBancos(f"Este movimiento ya está como «{m['estado']}». Deshazlo primero si quieres cambiarlo.")
        cur.execute("""SELECT * FROM finanzas_pagos WHERE id = %s AND estado <> 'Anulado'
                       AND (empresa_id IS NULL OR empresa_id::text = %s) FOR UPDATE""", (pago_id, eid))
        p = cur.fetchone()
        if not p:
            raise ErrorBancos('El cobro o pago de Finanzas no existe, está anulado o es de otra empresa.')
        if not _signo_ok(m['monto'], p):
            raise ErrorBancos('No coincide: un abono del banco solo se une a un cobro, y un cargo solo a un pago.')
        cur.execute("SELECT id FROM bancos_movimientos WHERE finanzas_pago_id = %s", (pago_id,))
        if cur.fetchone():
            raise ErrorBancos('Ese cobro o pago ya está unido a otro movimiento del banco.')
        diferencia = abs(abs(m['monto']) - p['monto'])
        if diferencia > TOLERANCIA and not (nota or '').strip():
            raise ErrorBancos(f'Los montos no son iguales (diferencia S/ {diferencia:.2f}). Escribe una nota para explicarlo.')
        forma = 'Manual' + (f' (diferencia S/ {diferencia:.2f})' if diferencia > TOLERANCIA else '')
        cur.execute("""UPDATE bancos_movimientos SET estado = 'Conciliado', finanzas_pago_id = %s, forma = %s, nota = %s,
                       conciliado_por = %s, conciliado_en = NOW() WHERE id = %s""",
                    (pago_id, forma, (nota or '').strip() or None, _usuario(), mov_id))
        _historial(cur, mov_id, 'Conciliado', forma + (f' · {nota.strip()}' if (nota or '').strip() else ''))


def explicar(eid, mov_id, estado, nota):
    if estado not in ('Gasto del banco', 'Revisado'):
        raise ErrorBancos('Estado inválido.')
    if not (nota or '').strip():
        raise ErrorBancos('Escribe en una línea qué es este movimiento (por ejemplo: "Transferencia entre cuentas de KCF").')
    with db_tx() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        m = _mov(cur, mov_id, eid)
        if m['estado'] != 'Pendiente':
            raise ErrorBancos(f"Este movimiento ya está como «{m['estado']}».")
        cur.execute("""UPDATE bancos_movimientos SET estado = %s, forma = 'Manual', nota = %s, conciliado_por = %s,
                       conciliado_en = NOW() WHERE id = %s""", (estado, nota.strip(), _usuario(), mov_id))
        _historial(cur, mov_id, estado, nota.strip())


def deshacer(eid, mov_id, motivo):
    if not (motivo or '').strip():
        raise ErrorBancos('Escribe el motivo para deshacer.')
    with db_tx() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        m = _mov(cur, mov_id, eid)
        if m['estado'] == 'Pendiente':
            raise ErrorBancos('Este movimiento ya está pendiente.')
        cur.execute("""UPDATE bancos_movimientos SET estado = 'Pendiente', finanzas_pago_id = NULL, forma = NULL, nota = NULL,
                       conciliado_por = NULL, conciliado_en = NULL WHERE id = %s""", (mov_id,))
        _historial(cur, mov_id, 'Deshecho', f"Estaba «{m['estado']}». Motivo: {motivo.strip()}")
    # Un movimiento deshecho ya no se une solo (conciliar_automatico lo salta): queda para revisión manual
    return True


def quitar_extracto(eid, ext_id, motivo):
    if not es_admin():
        raise ErrorBancos('Solo el administrador puede quitar un extracto subido.')
    if not (motivo or '').strip():
        raise ErrorBancos('Escribe el motivo.')
    with db_tx() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM bancos_extractos WHERE id = %s AND empresa_id = %s AND anulado_en IS NULL FOR UPDATE",
                    (ext_id, eid))
        if not cur.fetchone():
            raise ErrorBancos('Extracto no encontrado.')
        # Los movimientos son copia del archivo del banco (no son ventas, compras ni cobros): se quitan con el archivo.
        cur.execute("DELETE FROM bancos_movimientos WHERE extracto_id = %s", (ext_id,))
        cur.execute("""UPDATE bancos_extractos SET anulado_por = %s, anulado_en = NOW(), motivo_anulacion = %s
                       WHERE id = %s""", (_usuario(), motivo.strip(), ext_id))


# ============================================================
# RUTAS
# ============================================================
def _err(ex, codigo=400):
    return jsonify({'success': False, 'error': str(ex)}), codigo


@bancos_bp.route('/bancos')
def pagina():
    emps = [{'id': x['id'], 'codigo': x['codigo'], 'ruc': x.get('ruc')} for x in lista_empresas()]
    activa = empresa_actual()
    # "Registrar cobro / pago" usa la API de Finanzas: solo se ofrece a quien puede entrar y operar en Finanzas
    from routes.finanzas import puede_operar_finanzas
    from routes.acceso import acceso_usuario
    acc = acceso_usuario()
    entra_finanzas = es_admin() or not acc['configurado'] or 'finanzas' in acc['modulos']
    return render_template('bancos.html', empresas=emps, empresa_activa=activa['id'] if activa else None,
                           bancos=BANCOS, es_admin=es_admin(), puede_finanzas=puede_operar_finanzas() and entra_finanzas)


@bancos_bp.route('/bancos/api/resumen')
def api_resumen():
    try:
        e = _empresa(request.args.get('empresa_id'))
        return jsonify({'success': True, 'data': resumen(e, request.args.get('mes'), request.args.get('banco') or None)})
    except ErrorBancos as ex:
        return _err(ex)


@bancos_bp.route('/bancos/api/subir', methods=['POST'])
def api_subir():
    try:
        e = _empresa(request.form.get('empresa_id'))
        banco = (request.form.get('banco') or '').strip()
        if banco not in BANCOS:
            raise ErrorBancos('Elige el banco.')
        moneda = 'USD' if request.form.get('moneda') == 'USD' else 'PEN'
        cuenta = (request.form.get('cuenta') or '').strip()[:60] or None
        archivo = request.files.get('archivo')
        if not archivo or not archivo.filename:
            raise ErrorBancos('Elige el archivo del extracto.')
        contenido = archivo.read()
        if len(contenido) > 8 * 1024 * 1024:
            raise ErrorBancos('El archivo pesa más de 8 MB.')
        movimientos = leer_extracto(archivo.filename, contenido)
        r = guardar_extracto(e, banco, cuenta, moneda, archivo.filename[:255], movimientos)
        r['mes'] = max(m['fecha'] for m in movimientos).strftime('%Y-%m')
        return jsonify({'success': True, 'data': r,
                        'message': f"Listo: {r['nuevas']} movimientos nuevos"
                                   + (f", {r['repetidas']} ya estaban" if r['repetidas'] else '')
                                   + f", {r['conciliados']} conciliados solos."})
    except ErrorBancos as ex:
        return _err(ex)


@bancos_bp.route('/bancos/api/conciliar', methods=['POST'])
def api_conciliar():
    try:
        d = request.get_json(silent=True) or {}
        e = _empresa(d.get('empresa_id'))
        conciliar_manual(str(e['id']), int(d.get('movimiento_id') or 0), int(d.get('pago_id') or 0), d.get('nota'))
        return jsonify({'success': True, 'message': 'Conciliado.'})
    except (ValueError, TypeError):
        return _err('Datos inválidos.')
    except ErrorBancos as ex:
        return _err(ex)


@bancos_bp.route('/bancos/api/explicar', methods=['POST'])
def api_explicar():
    try:
        d = request.get_json(silent=True) or {}
        e = _empresa(d.get('empresa_id'))
        explicar(str(e['id']), int(d.get('movimiento_id') or 0), d.get('estado'), d.get('nota'))
        return jsonify({'success': True, 'message': 'Guardado.'})
    except (ValueError, TypeError):
        return _err('Datos inválidos.')
    except ErrorBancos as ex:
        return _err(ex)


@bancos_bp.route('/bancos/api/deshacer', methods=['POST'])
def api_deshacer():
    try:
        d = request.get_json(silent=True) or {}
        e = _empresa(d.get('empresa_id'))
        deshacer(str(e['id']), int(d.get('movimiento_id') or 0), d.get('motivo'))
        return jsonify({'success': True, 'message': 'Deshecho: el movimiento vuelve a pendiente.'})
    except (ValueError, TypeError):
        return _err('Datos inválidos.')
    except ErrorBancos as ex:
        return _err(ex)


@bancos_bp.route('/bancos/api/extracto/<int:ext_id>/quitar', methods=['POST'])
def api_quitar_extracto(ext_id):
    try:
        d = request.get_json(silent=True) or {}
        e = _empresa(d.get('empresa_id'))
        quitar_extracto(str(e['id']), ext_id, d.get('motivo'))
        return jsonify({'success': True, 'message': 'Extracto quitado.'})
    except ErrorBancos as ex:
        return _err(ex)
