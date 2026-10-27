"""Descripción del cliente por línea (Erika y Hellen, 27/10/2026, caso Komatsu).

Cada producto lleva dos nombres:
  - "Nombre producto": el del maestro de productos (con el que cotizamos);
  - "Descripción del cliente": tal cual la escribe el pedido del cliente (por ejemplo "bloqueador solar" o
    "guacha 5/8"), más el "Código del cliente" (su N° de material), ambos opcionales.
Los dos nacen en la cotización y viajan al PV, Entregas, Guía, Factura, Nota de crédito y sus PDF, para que el
almacén del cliente no rechace la mercadería. El sistema recuerda cómo llama cada cliente a cada producto y lo
sugiere la próxima vez. Si se corrige en el PV, se pasa a lo que aún no se emitió (despachos sin guía, guías y
facturas en Borrador); lo emitido no se toca.
Migración 038 (en la base de pruebas las columnas se crean aquí). No borra datos.
"""
import html
import json
import threading

from flask import Blueprint, jsonify, request, session

from database import db_query, db_tx

descripcion_cliente_bp = Blueprint('descripcion_cliente', __name__)

MAX_DESC = 300
MAX_CODIGO = 60

SQL_DDL = """
    ALTER TABLE cotizacion_detalle ADD COLUMN IF NOT EXISTS descripcion_cliente TEXT;
    ALTER TABLE cotizacion_detalle ADD COLUMN IF NOT EXISTS codigo_cliente VARCHAR(60);
    CREATE TABLE IF NOT EXISTS cliente_producto_descripcion (
        id SERIAL PRIMARY KEY,
        cliente_id INTEGER NOT NULL,
        producto_codigo VARCHAR(60) NOT NULL,
        descripcion_cliente TEXT,
        codigo_cliente VARCHAR(60),
        actualizado_por INTEGER,
        actualizado_en TIMESTAMP DEFAULT NOW(),
        UNIQUE (cliente_id, producto_codigo)
    )
"""

_listo = False
_lock = threading.Lock()


def asegurar_columnas():
    global _listo
    if _listo:
        return
    with _lock:
        if _listo:
            return
        with db_tx() as conn:
            cur = conn.cursor()
            cur.execute("""SELECT (SELECT COUNT(*) FROM information_schema.columns
                                   WHERE table_name = 'cotizacion_detalle'
                                     AND column_name IN ('descripcion_cliente', 'codigo_cliente'))
                                + (SELECT COUNT(*) FROM information_schema.tables
                                   WHERE table_name = 'cliente_producto_descripcion')""")
            if cur.fetchone()[0] < 3:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext('desc_cliente_ddl'))")
                for s in (x.strip() for x in SQL_DDL.split(';')):
                    if s:
                        cur.execute(s)
        _listo = True


def limpiar_desc(valor):
    return str(valor or '').replace('\r', '').strip()[:MAX_DESC]


def limpiar_codigo(valor):
    return str(valor or '').strip()[:MAX_CODIGO]


def linea_cliente(item):
    """Texto de la segunda línea en PDF y pantallas: 'Según su pedido: … · Código del cliente: …' ('' si no hay)."""
    if not isinstance(item, dict):
        return ''
    desc = limpiar_desc(item.get('descripcion_cliente'))
    cod = limpiar_codigo(item.get('codigo_cliente'))
    partes = []
    if desc:
        partes.append('Según su pedido: ' + desc)
    if cod:
        partes.append('Código del cliente: ' + cod)
    return ' · '.join(partes)


def linea_cliente_html(item, estilo='display:block;font-size:7.5px;font-weight:600;color:#334155;margin-top:1px'):
    texto = linea_cliente(item)
    return f'<span style="{estilo}">{html.escape(texto)}</span>' if texto else ''


def nombre_maestro(item):
    """Nombre producto del maestro (nunca la descripción del cliente)."""
    if not isinstance(item, dict):
        return ''
    return item.get('producto') or item.get('descripcion') or item.get('nombre') or item.get('name') or ''


# ------------------------------------------------------------
# Memoria: cómo llama cada cliente a cada producto
# ------------------------------------------------------------
def recordar(cliente_id, lineas, usuario_id=None):
    """Guarda la descripción y el código del cliente de cada línea que los tenga. No borra lo recordado."""
    if not cliente_id:
        return
    asegurar_columnas()
    for it in lineas or []:
        if not isinstance(it, dict):
            continue
        codigo = str(it.get('codigo') or '').strip()[:60]
        desc = limpiar_desc(it.get('descripcion_cliente'))
        cod = limpiar_codigo(it.get('codigo_cliente'))
        if not codigo or not (desc or cod):
            continue
        db_query("""INSERT INTO cliente_producto_descripcion
                        (cliente_id, producto_codigo, descripcion_cliente, codigo_cliente, actualizado_por, actualizado_en)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (cliente_id, producto_codigo) DO UPDATE
                    SET descripcion_cliente = COALESCE(NULLIF(EXCLUDED.descripcion_cliente, ''),
                                                       cliente_producto_descripcion.descripcion_cliente),
                        codigo_cliente = COALESCE(NULLIF(EXCLUDED.codigo_cliente, ''),
                                                  cliente_producto_descripcion.codigo_cliente),
                        actualizado_por = EXCLUDED.actualizado_por, actualizado_en = NOW()
                    RETURNING id""",
                 (int(cliente_id), codigo, desc or None, cod or None, usuario_id))


def sugerencias(cliente_id, codigos):
    asegurar_columnas()
    codigos = [str(c or '').strip() for c in codigos or [] if str(c or '').strip()]
    if not cliente_id or not codigos:
        return {}
    filas = db_query("""SELECT producto_codigo, descripcion_cliente, codigo_cliente
                        FROM cliente_producto_descripcion
                        WHERE cliente_id = %s AND producto_codigo = ANY(%s)""", (int(cliente_id), codigos))
    return {f['producto_codigo']: {'descripcion_cliente': f.get('descripcion_cliente') or '',
                                   'codigo_cliente': f.get('codigo_cliente') or ''} for f in filas or []}


@descripcion_cliente_bp.route('/ventas/api/descripcion-cliente/sugerencias', methods=['GET'])
def api_sugerencias():
    if not session.get('usuario_id'):
        return jsonify({'success': False, 'error': 'Inicia sesión'}), 401
    try:
        cliente_id = int(request.args.get('cliente_id') or 0)
    except ValueError:
        cliente_id = 0
    if not cliente_id:
        ruc = (request.args.get('ruc') or '').strip()
        if ruc:
            fila = db_query("SELECT id FROM clientes WHERE numero_documento = %s ORDER BY id LIMIT 1", (ruc,))
            cliente_id = fila[0]['id'] if fila else 0
    codigos = (request.args.get('codigos') or '').split(',')
    return jsonify({'success': True, 'data': sugerencias(cliente_id, codigos)})


# ------------------------------------------------------------
# Pasar al resto lo corregido en el PV (solo lo que no está emitido)
# ------------------------------------------------------------
def _lista(crudo):
    if isinstance(crudo, str):
        try:
            crudo = json.loads(crudo)
        except ValueError:
            return []
    return crudo if isinstance(crudo, list) else []


def _mapa(items):
    m = {}
    for it in items or []:
        if isinstance(it, dict) and str(it.get('codigo') or '').strip():
            m[str(it['codigo']).strip().upper()] = (limpiar_desc(it.get('descripcion_cliente')),
                                                     limpiar_codigo(it.get('codigo_cliente')))
    return m


def _aplicar(items, mapa):
    cambio = False
    for it in items:
        if not isinstance(it, dict):
            continue
        par = mapa.get(str(it.get('codigo') or '').strip().upper())
        if par is None:
            continue
        if (it.get('descripcion_cliente') or '') != par[0] or (it.get('codigo_cliente') or '') != par[1]:
            it['descripcion_cliente'], it['codigo_cliente'] = par
            cambio = True
    return cambio


def propagar_pv(numero_pv, items_pv, cotizacion_numero=None):
    """Lleva la descripción y el código del cliente del PV a sus despachos sin guía y a sus guías y facturas en
    Borrador. Devuelve cuántos documentos cambió."""
    numero_pv = str(numero_pv or '').strip()
    mapa = _mapa(items_pv)
    if not numero_pv or not mapa:
        return 0
    cambiados = 0
    docs = [('despachos', db_query("""SELECT id, items_json FROM despachos WHERE pc_numero = %s
                                       AND COALESCE(guia, '') = '' AND COALESCE(UPPER(estado), '') NOT LIKE 'ANULAD%%'""",
                                    (numero_pv,)))]
    asociados = [numero_pv] + ([cotizacion_numero] if cotizacion_numero else [])
    docs.append(('guias_remision', db_query("""SELECT id, items_json FROM guias_remision WHERE documento_asociado = ANY(%s)
                                                AND UPPER(COALESCE(estado_sunat, '')) = 'BORRADOR'""", (asociados,))))
    docs.append(('comprobantes', db_query("""SELECT id, items_json FROM comprobantes WHERE pc_vinculado = %s
                                              AND UPPER(COALESCE(estado_sunat, '')) = 'BORRADOR'""", (numero_pv,))))
    for tabla, filas in docs:
        for f in filas or []:
            items = _lista(f.get('items_json'))
            if items and _aplicar(items, mapa):
                db_query(f"UPDATE {tabla} SET items_json = %s WHERE id = %s RETURNING id",
                         (json.dumps(items, ensure_ascii=False), f['id']))
                cambiados += 1
    return cambiados
