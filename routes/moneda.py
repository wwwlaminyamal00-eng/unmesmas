# routes/moneda.py - Soles y dólares con tipo de cambio (pedido de Erika, 24/10/2026 18:17)
#
# "A veces vendo y compro en dólares". KCF tiene cuenta solo en soles; AGD en soles y en dólares.
# Los proveedores venden en dólares y dan su propio tipo de cambio para que se les pague en soles.
#
# Reglas:
#   - Cada documento guarda su moneda (PEN o USD) y su tipo de cambio (TC).
#     Cotización, PV, factura de venta, OC y factura del proveedor.
#   - El TC del documento se propone con el TC SUNAT (venta) del día y se puede cambiar.
#   - Los montos del documento quedan en su moneda. Lo que reduce la deuda (finanzas_pagos.monto) también.
#     El pago real se guarda aparte: moneda_pago, tipo_cambio y monto_pagado.
#     Ejemplo: deuda US$ 100, el proveedor da TC 3.80 y se pagan S/ 380.00 → monto 100, monto_pagado 380.
#   - SUNAT y los totales en soles usan monto × TC del documento.
import logging
import threading
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import requests
from flask import Blueprint, jsonify, request

from database import db_query, db_tx

log = logging.getLogger(__name__)
moneda_bp = Blueprint('moneda', __name__)

TC_MIN, TC_MAX = Decimal('2.5'), Decimal('6')   # rango sano para soles por dólar


class ErrorMoneda(ValueError):
    """Dato de moneda o tipo de cambio mal escrito: mensaje claro para el usuario."""

SQL_DDL_MONEDA = """
    CREATE TABLE IF NOT EXISTS tipo_cambio_dia (
        fecha DATE PRIMARY KEY,
        compra NUMERIC(10,4),
        venta NUMERIC(10,4) NOT NULL,
        fuente VARCHAR(40),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    ALTER TABLE cotizaciones ADD COLUMN IF NOT EXISTS moneda VARCHAR(3) DEFAULT 'PEN';
    ALTER TABLE cotizaciones ADD COLUMN IF NOT EXISTS tipo_cambio NUMERIC(10,4);
    ALTER TABLE pedido_compra_pc ADD COLUMN IF NOT EXISTS moneda VARCHAR(3) DEFAULT 'PEN';
    ALTER TABLE pedido_compra_pc ADD COLUMN IF NOT EXISTS tipo_cambio NUMERIC(10,4);
    ALTER TABLE comprobantes ADD COLUMN IF NOT EXISTS tipo_cambio NUMERIC(10,4);
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS moneda VARCHAR(3) DEFAULT 'PEN';
    ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS tipo_cambio NUMERIC(10,4);
    ALTER TABLE comprobantes_proveedor ADD COLUMN IF NOT EXISTS moneda VARCHAR(3) DEFAULT 'PEN';
    ALTER TABLE comprobantes_proveedor ADD COLUMN IF NOT EXISTS tipo_cambio NUMERIC(10,4);
    ALTER TABLE finanzas_pagos ADD COLUMN IF NOT EXISTS moneda_pago VARCHAR(3);
    ALTER TABLE finanzas_pagos ADD COLUMN IF NOT EXISTS tipo_cambio NUMERIC(10,4);
    ALTER TABLE finanzas_pagos ADD COLUMN IF NOT EXISTS monto_pagado NUMERIC(14,2);
"""

_listo = False
_lock = threading.Lock()


def asegurar_moneda():
    """Columnas de moneda y tipo de cambio (migración 030; en la base de pruebas se crean aquí). No borra nada."""
    global _listo
    if _listo:
        return
    with _lock:
        if _listo:
            return
        with db_tx() as conn:
            cur = conn.cursor()
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('moneda_ddl'))")
            for sentencia in SQL_DDL_MONEDA.split(';'):
                # Solo las tablas que existen (la base reconstruida de pruebas puede no tener alguna)
                s = sentencia.strip()
                if not s:
                    continue
                if s.upper().startswith('ALTER TABLE'):
                    tabla = s.split()[2]
                    cur.execute("SELECT to_regclass(%s)", (tabla,))
                    if cur.fetchone()[0] is None:
                        continue
                cur.execute(s)
        _listo = True


def codigo_moneda(valor):
    """'Dólares ($)', '$', 'USD', 'US$' → 'USD'; todo lo demás (S/, Soles, PEN, vacío) → 'PEN'."""
    v = str(valor or '').upper()
    return 'USD' if ('$' in v and 'S/' not in v) or 'USD' in v or 'DÓLAR' in v or 'DOLAR' in v else 'PEN'


def simbolo(moneda):
    return 'US$' if codigo_moneda(moneda) == 'USD' else 'S/'


def leer_tc(valor, obligatorio=False, nombre='el tipo de cambio'):
    """Valida un TC escrito por el usuario. Devuelve Decimal(4 decimales) o None si viene vacío."""
    texto = str(valor if valor is not None else '').strip().replace(',', '.')
    if not texto:
        if obligatorio:
            raise ErrorMoneda(f'Escribe {nombre} (soles por dólar, por ejemplo 3.75).')
        return None
    try:
        tc = Decimal(texto).quantize(Decimal('0.0001'))
    except InvalidOperation:
        raise ErrorMoneda(f'{nombre.capitalize()} no es un número válido.')
    if not (TC_MIN <= tc <= TC_MAX):
        raise ErrorMoneda(f'{nombre.capitalize()} debe estar entre {TC_MIN} y {TC_MAX} soles por dólar (escribiste {tc}).')
    return tc


def moneda_y_tc(datos, obligatorio_si_usd=True):
    """Lee moneda y tipo_cambio de un formulario. En soles el TC no se guarda."""
    mon = codigo_moneda(datos.get('moneda'))
    if mon == 'PEN':
        return 'PEN', None
    tc = leer_tc(datos.get('tipo_cambio'), obligatorio=obligatorio_si_usd,
                 nombre='el tipo de cambio del documento en dólares')
    return 'USD', tc


def en_soles(monto, moneda, tc):
    """Equivalente en soles. Si es dólar sin TC devuelve None (no se inventa)."""
    m = Decimal(str(monto or 0))
    if codigo_moneda(moneda) == 'PEN':
        return m
    if not tc:
        return None
    return (m * Decimal(str(tc))).quantize(Decimal('0.01'))


# ---------------------------------------------------------------- TC SUNAT del día
def _consultar_externo(fecha):
    """TC SUNAT (compra, venta) de una fecha. Intenta varias fuentes; si ninguna responde, None."""
    from routes.consulta_ruc import _token
    token = _token()
    intentos = []
    if token:
        intentos += [('https://api.decolecta.com/v1/tipo-cambio/sunat', {'date': fecha.isoformat()},
                      {'Authorization': f'Bearer {token}'}),
                     ('https://api.apis.net.pe/v2/sunat/tipo-cambio', {'date': fecha.isoformat()},
                      {'Authorization': f'Bearer {token}'})]
    intentos.append(('https://api.apis.net.pe/v1/tipo-cambio-sunat', {'fecha': fecha.isoformat()}, {}))
    for url, params, extra in intentos:
        try:
            r = requests.get(url, params=params, timeout=5,
                             headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json', **extra})
            if r.status_code != 200:
                continue
            j = r.json() or {}
            venta = j.get('venta') or j.get('sell_price') or j.get('precioVenta')
            compra = j.get('compra') or j.get('buy_price') or j.get('precioCompra')
            if venta:
                return Decimal(str(compra)) if compra else None, Decimal(str(venta)), url.split('/')[2]
        except Exception as e:
            log.info("TC SUNAT %s no respondió: %s", url, e)
    # Página oficial de SUNAT: solo trae el TC de hoy ("dd/mm/aaaa|compra|venta|")
    if fecha == date.today():
        try:
            r = requests.get('https://www.sunat.gob.pe/a/txt/tipoCambio.txt', timeout=5,
                             headers={'User-Agent': 'Mozilla/5.0'})
            partes = r.text.strip().split('|') if r.status_code == 200 else []
            if len(partes) >= 3:
                return Decimal(partes[1]), Decimal(partes[2]), 'sunat.gob.pe'
        except Exception as e:
            log.info("TC SUNAT oficial no respondió: %s", e)
    return None


def tc_sunat(fecha, consultar=True):
    """TC SUNAT venta guardado para la fecha; si no está y se puede, lo consulta y lo guarda."""
    asegurar_moneda()
    fila = db_query("SELECT compra, venta, fuente FROM tipo_cambio_dia WHERE fecha = %s", (fecha,))
    if fila:
        return {'compra': fila[0]['compra'], 'venta': fila[0]['venta'], 'fuente': fila[0]['fuente']}
    if not consultar:
        return None
    externo = _consultar_externo(fecha)
    if not externo:
        return None
    compra, venta, fuente = externo
    try:
        venta = leer_tc(venta)
    except ErrorMoneda:
        return None
    db_query("""INSERT INTO tipo_cambio_dia (fecha, compra, venta, fuente) VALUES (%s, %s, %s, %s)
                ON CONFLICT (fecha) DO NOTHING RETURNING fecha""", (fecha, compra, venta, fuente))
    return {'compra': compra, 'venta': venta, 'fuente': fuente}


@moneda_bp.route('/api/tipo_cambio', methods=['GET'])
def api_tipo_cambio():
    """TC SUNAT (venta) de una fecha para proponerlo en el formulario. Si no se pudo obtener, se escribe a mano."""
    try:
        fecha = date.fromisoformat((request.args.get('fecha') or date.today().isoformat())[:10])
    except ValueError:
        fecha = date.today()
    try:
        tc = tc_sunat(fecha)
    except Exception as e:
        log.warning("TC SUNAT: %s", e)
        tc = None
    if not tc:
        return jsonify({'success': True, 'fecha': fecha.isoformat(), 'venta': None,
                        'mensaje': 'No se pudo traer el tipo de cambio de SUNAT: escríbelo a mano.'})
    return jsonify({'success': True, 'fecha': fecha.isoformat(), 'venta': float(tc['venta']),
                    'compra': float(tc['compra']) if tc.get('compra') else None, 'fuente': tc.get('fuente')})


def monedas_de_cuentas(empresa_id):
    """Monedas de las cuentas bancarias activas de la empresa (KCF: solo PEN; AGD: PEN y USD)."""
    try:
        filas = db_query("""SELECT DISTINCT UPPER(COALESCE(moneda, 'PEN')) AS m FROM erp_empresa_cuentas_bancarias
                            WHERE empresa_id::text = %s AND COALESCE(LOWER(estado), 'activo') <> 'inactivo'""",
                         (str(empresa_id),))
    except Exception:
        return ['PEN']
    monedas = sorted({codigo_moneda(f['m']) for f in filas}) or ['PEN']
    return monedas


def pago_en_moneda(doc_moneda, datos, empresa_id=None):
    """Convierte lo que se pagó a la moneda del documento.
    datos: monto_pagado (o monto), moneda_pago, tipo_cambio. Devuelve (monto_doc, moneda_pago, tc, monto_pagado)."""
    from utils import redondear
    doc_moneda = codigo_moneda(doc_moneda)
    moneda_pago = codigo_moneda(datos.get('moneda_pago') or doc_moneda)
    pagado = redondear(datos.get('monto_pagado') if datos.get('monto_pagado') not in (None, '') else datos.get('monto'))
    if moneda_pago == 'USD' and empresa_id is not None and 'USD' not in monedas_de_cuentas(empresa_id):
        raise ErrorMoneda('Esta empresa no tiene cuenta en dólares registrada (Configuración ▸ Empresa ▸ Cuentas bancarias). '
                         'Registra el pago en soles con el tipo de cambio.')
    if moneda_pago == doc_moneda:
        return pagado, moneda_pago, None, pagado
    tc = leer_tc(datos.get('tipo_cambio'), obligatorio=True, nombre='el tipo de cambio del pago')
    if doc_moneda == 'USD':      # deuda en dólares, se paga en soles: S/ ÷ TC
        monto_doc = redondear(pagado / tc)
    else:                        # deuda en soles, se paga en dólares: US$ × TC
        monto_doc = redondear(pagado * tc)
    return monto_doc, moneda_pago, tc, pagado


def tc_referencia(fecha=None):
    """TC para pasar a soles un saldo en dólares que no guardó su TC: el último TC SUNAT guardado hasta esa fecha."""
    try:
        fila = db_query("SELECT venta FROM tipo_cambio_dia WHERE fecha <= %s ORDER BY fecha DESC LIMIT 1",
                        (fecha or date.today(),))
    except Exception:
        return None
    return fila[0]['venta'] if fila else None


def sql_monto_soles(a='fp'):
    """Expresión SQL: lo pagado de verdad pasado a soles (pagos antiguos sin moneda = soles)."""
    return f"""(CASE WHEN COALESCE({a}.moneda_pago, 'PEN') = 'PEN' THEN COALESCE({a}.monto_pagado, {a}.monto)
                ELSE COALESCE({a}.monto_pagado, {a}.monto) * COALESCE({a}.tipo_cambio,
                     (SELECT t.venta FROM tipo_cambio_dia t WHERE t.fecha <= {a}.fecha ORDER BY t.fecha DESC LIMIT 1), 1) END)"""


def moneda_documento(datos, fecha=None, respaldo=None, tc_sunat_por_defecto=False):
    """Moneda y TC de un documento de venta. Si el formulario no trae moneda, usa la del documento de origen
    (respaldo: la cotización o el PV). En dólares sin TC escrito: el del origen o, si tc_sunat_por_defecto,
    el TC SUNAT de la fecha (factura). Si no hay ninguno, pide escribirlo."""
    respaldo = respaldo or {}
    moneda = codigo_moneda(datos.get('moneda') or respaldo.get('moneda'))
    if moneda == 'PEN':
        return 'PEN', None
    tc = leer_tc(datos.get('tipo_cambio'), nombre='el tipo de cambio')
    if tc is None and tc_sunat_por_defecto:
        try:
            t = tc_sunat(date.fromisoformat(fecha) if fecha else date.today())
            tc = leer_tc(t['venta']) if t else None
        except Exception:
            tc = None
    if tc is None and respaldo.get('tipo_cambio'):
        tc = leer_tc(respaldo.get('tipo_cambio'))
    if tc is None:
        raise ErrorMoneda('El documento es en dólares: escribe el tipo de cambio (soles por dólar, por ejemplo 3.75).')
    return 'USD', tc
