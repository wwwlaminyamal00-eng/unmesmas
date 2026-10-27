"""Facturación parcial por posiciones y cuadre de entregas (Erika, 27/10/2026 17:07, caso Komatsu).

Un cliente manda un pedido de 5 posiciones, se le entregan 4 (la 5 está en importación) y hay que facturar ya
lo entregado porque el crédito es a 90 días. Reglas aprobadas por Erika:
  1. Factura parcial = solo lo que ya salió con guía: se marca con check cada posición y su cantidad. No se
     factura más de lo que dice la guía ni más de lo pedido en el PV (Pedido de venta).
  2. Lo que no se factura lleva motivo (En importación / En fabricación / Falta ingreso del cliente / Otro) y un
     comentario. Es nota interna: nunca sale en el PDF ni en lo que ve el cliente.
  3. El PV muestra "Entregado X% · Facturado Y% · Falta: posición N" y el inicio avisa los PV con posiciones
     pendientes y cuántos días van.
  4. Cuadre de 3 por despacho: salida del almacén (kardex) vs guía vs confirmación del cliente (N° de ingreso del
     cliente y fecha real de entrega). Si no cuadra, alerta roja con quién despachó.
La "Factura total" sigue como antes (se puede emitir antes de la entrega cuando el cliente paga primero).
Migración 037 (en la base de pruebas las columnas se crean aquí). No borra ni cambia datos.
"""
import json
import threading
from datetime import date, datetime
from decimal import Decimal

from flask import Blueprint, jsonify, request, session

from database import db_query, db_tx
from utils import a_decimal, redondear

facturacion_parcial_bp = Blueprint('facturacion_parcial', __name__)

MOTIVOS_PENDIENTE = ('En importación', 'En fabricación', 'Falta ingreso del cliente', 'Otro')
ESTADOS_SALIDA = ('Despachado', 'Entregado')
ANULADOS = ('ANULADO', 'ANULADA')
CERO = Decimal('0')
TOL = Decimal('0.001')

SQL_DDL = """
    ALTER TABLE comprobantes ADD COLUMN IF NOT EXISTS facturacion_tipo VARCHAR(10);
    ALTER TABLE comprobantes ADD COLUMN IF NOT EXISTS pendientes_json JSONB;
    ALTER TABLE despachos ADD COLUMN IF NOT EXISTS ingreso_cliente VARCHAR(60)
"""

_listo = False
_lock = threading.Lock()


class ErrorFacturaParcial(Exception):
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
                           WHERE (table_name = 'comprobantes' AND column_name IN ('facturacion_tipo', 'pendientes_json'))
                              OR (table_name = 'despachos' AND column_name = 'ingreso_cliente')""")
            if cur.fetchone()[0] < 3:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext('fact_parcial_ddl'))")
                for s in (x.strip() for x in SQL_DDL.split(';')):
                    if s:
                        cur.execute(s)
        _listo = True


# ------------------------------------------------------------
# Posiciones del PV y lo que ya tiene cada una
# ------------------------------------------------------------
def _lista(crudo):
    if isinstance(crudo, str):
        try:
            crudo = json.loads(crudo)
        except ValueError:
            return []
    if isinstance(crudo, dict):
        crudo = crudo.get('items') or list(crudo.values())
    return [x for x in (crudo or []) if isinstance(x, dict)]


def _clave(it):
    return it['producto_id'] or (it['codigo'] or '').strip().upper() or (it['descripcion'] or '').strip().upper()


def _por_clave(items_json):
    """{clave: cantidad} de una lista de productos (factura, guía o despacho)."""
    from routes.compras_flujo import _items_pedido, _resolver_productos
    out = {}
    for it in _resolver_productos(_items_pedido({'items_json': items_json})):
        k = _clave(it)
        if k and it['cantidad'] > 0:
            out[k] = out.get(k, CERO) + it['cantidad']
    return out


def _sumar(destino, origen):
    for k, c in origen.items():
        destino[k] = destino.get(k, CERO) + c


def pv_por_numero(numero):
    numero = str(numero or '').strip()
    if not numero:
        return None
    filas = db_query("""SELECT id, numero, cotizacion_numero, cliente AS cliente_nombre, items_json, created_at
                        FROM pedido_compra_pc WHERE numero = %s AND UPPER(COALESCE(estado, '')) NOT IN ('ANULADO', 'ANULADA')
                        ORDER BY id DESC LIMIT 1""", (numero,))
    return filas[0] if filas else None


def _facturas_del_pv(pv, excluir_id=None):
    cot = pv.get('cotizacion_numero') or ''
    return db_query("""SELECT id, serie, numero, items_json, pendientes_json, facturacion_tipo, created_at
                       FROM comprobantes
                       WHERE UPPER(COALESCE(estado_sunat, '')) NOT IN ('ANULADO', 'ANULADA')
                         AND id <> COALESCE(%s, -1)
                         AND (pc_vinculado = %s OR (COALESCE(pc_vinculado, '') = '' AND %s <> '' AND documento_asociado = %s))
                       ORDER BY id""", (excluir_id, pv['numero'], cot, cot))


def _despachos_del_pv(pv):
    return db_query("""SELECT id, numero, estado, guia, items_json, stock_estado, stock_detalle, fecha_entrega_real,
                              ingreso_cliente, responsable, creado_por, updated_at, created_at
                       FROM despachos WHERE (pc_numero = %s OR pc_id = %s) AND COALESCE(estado, '') <> 'Anulado'
                       ORDER BY id""", (pv['numero'], pv['id']))


def _guias_del_pv(pv):
    return db_query("""
        SELECT g.id, g.serie, g.numero, g.items_json FROM guias_remision g
        WHERE UPPER(COALESCE(g.estado_sunat, '')) NOT IN ('ANULADO', 'ANULADA')
          AND (g.documento_asociado = %s OR EXISTS (
                SELECT 1 FROM despachos d WHERE (d.pc_numero = %s OR d.pc_id = %s) AND COALESCE(d.estado, '') <> 'Anulado'
                  AND COALESCE(d.guia, '') <> ''
                  AND regexp_replace(d.guia, '^.*-', '') ~ '^[0-9]+$'
                  AND split_part(d.guia, '-', 1) IN (COALESCE(g.serie, ''), d.guia)
                  AND NULLIF(regexp_replace(regexp_replace(d.guia, '^.*-', ''), '\\D', '', 'g'), '')::bigint
                      = NULLIF(regexp_replace(g.numero::text, '\\D', '', 'g'), '')::bigint))
        ORDER BY g.id""", (pv['numero'], pv['numero'], pv['id']))


def _repartir(posiciones, total_por_clave, campo):
    """Reparte lo de cada producto entre sus posiciones, en orden (la última se queda con lo que sobre)."""
    resto = dict(total_por_clave)
    ultima = {}
    for p in posiciones:
        ultima[p['clave']] = p
    for p in posiciones:
        k = p['clave']
        dar = min(resto.get(k, CERO), p['pedido']) if ultima[k] is not p else resto.get(k, CERO)
        p[campo] = max(dar, CERO)
        resto[k] = resto.get(k, CERO) - p[campo]


def avance_pv(pv, excluir_factura=None):
    """Posiciones del PV con lo entregado, lo que tiene guía y lo ya facturado."""
    from routes.compras_flujo import _items_pedido, _resolver_productos
    crudo = _lista(pv.get('items_json'))
    norm = _resolver_productos(_items_pedido({'items_json': crudo}))
    posiciones = []
    for i, (it, raw) in enumerate(zip(norm, crudo), start=1):
        if it['cantidad'] <= 0:
            continue
        precio = a_decimal(raw.get('precio_pc') or raw.get('precio_cotizado') or raw.get('valorVenta')
                           or raw.get('precio_unitario') or 0)
        posiciones.append({'posicion': i, 'clave': _clave(it), 'codigo': it['codigo'],
                           'producto': (raw.get('descripcion_cliente') or '').strip() or it['descripcion'],
                           'unidad': it['unidad'] or 'NIU', 'marca': raw.get('marca') or '', 'modelo': raw.get('modelo') or '',
                           'producto_id': it['producto_id'], 'precio': precio, 'pedido': it['cantidad']})
    entregado, guiado, facturado = {}, {}, {}
    despachos = _despachos_del_pv(pv)
    for d in despachos:
        if (d.get('estado') or '') in ESTADOS_SALIDA:
            _sumar(entregado, _por_clave(d.get('items_json') if _lista(d.get('items_json')) else crudo))
    for g in _guias_del_pv(pv):
        _sumar(guiado, _por_clave(g.get('items_json')))
    facturas = _facturas_del_pv(pv, excluir_factura)
    for f in facturas:
        _sumar(facturado, _por_clave(f.get('items_json')))
    _repartir(posiciones, entregado, 'entregado')
    _repartir(posiciones, guiado, 'guiado')
    _repartir(posiciones, facturado, 'facturado')
    # Motivo vigente de lo que falta: el de la última factura parcial que lo explicó
    motivos = {}
    for f in facturas:
        for m in _lista(f.get('pendientes_json')):
            motivos[int(m.get('posicion') or 0)] = {'motivo': m.get('motivo'), 'comentario': m.get('comentario'),
                                                    'factura': f"{f.get('serie') or ''}-{f.get('numero') or ''}",
                                                    'fecha': str(f.get('created_at') or '')[:10]}
    for p in posiciones:
        p['por_facturar'] = max(p['pedido'] - p['facturado'], CERO)
        p['facturable'] = max(min(p['guiado'], p['pedido']) - p['facturado'], CERO)
        p['motivo'] = motivos.get(p['posicion']) if p['por_facturar'] > 0 else None
    return posiciones, despachos, facturas


def _pct(posiciones, campo):
    total = sum((p['pedido'] * (p['precio'] or 1) for p in posiciones), CERO)
    if total <= 0:
        return 0.0
    hecho = sum((min(p[campo], p['pedido']) * (p['precio'] or 1) for p in posiciones), CERO)
    return float(redondear(hecho * 100 / total))


def resumen_pv(pv, excluir_factura=None):
    posiciones, despachos, facturas = avance_pv(pv, excluir_factura)
    faltan = [p['posicion'] for p in posiciones if p['por_facturar'] > 0]
    return {
        'pv': pv['numero'], 'cliente': pv.get('cliente_nombre'),
        'entregado_pct': _pct(posiciones, 'entregado'), 'guiado_pct': _pct(posiciones, 'guiado'),
        'facturado_pct': _pct(posiciones, 'facturado'),
        'faltan_facturar': faltan, 'facturas': len(facturas),
        'posiciones': [{k: (float(v) if isinstance(v, Decimal) else v) for k, v in p.items() if k != 'clave'}
                       for p in posiciones],
    }


# ------------------------------------------------------------
# Validación al guardar la factura
# ------------------------------------------------------------
def validar_factura(data, pc_origen, excluir_id=None):
    """Devuelve (facturacion_tipo, pendientes) o lanza ErrorFacturaParcial.
    Sin facturacion_tipo (pantallas antiguas) no cambia nada: (None, None)."""
    tipo = str(data.get('facturacion_tipo') or '').strip().capitalize()
    if tipo not in ('Total', 'Parcial'):
        return None, None
    pv = pv_por_numero((pc_origen or {}).get('numero')) if pc_origen else None
    if not pv:
        if tipo == 'Parcial':
            raise ErrorFacturaParcial('Para una factura parcial elige el PV (Pedido de venta): así se sabe qué posiciones '
                                      'ya se entregaron con guía.')
        return 'Total', None
    posiciones, _, _ = avance_pv(pv, excluir_id)
    nuevo = _por_clave(data.get('items') or [])
    por_clave = {}
    for p in posiciones:
        por_clave.setdefault(p['clave'], []).append(p)
    for k, c in nuevo.items():
        if k not in por_clave:
            raise ErrorFacturaParcial('Hay un producto que no está en el PV. En una factura solo van productos del pedido.')
        ps = por_clave[k]
        pedido = sum((p['pedido'] for p in ps), CERO)
        ya = sum((p['facturado'] for p in ps), CERO)
        nombre = ps[0]['producto'] or ps[0]['codigo']
        num = ', '.join(str(p['posicion']) for p in ps)
        if ya + c > pedido + TOL:
            raise ErrorFacturaParcial(f'Posición {num} "{nombre}": el PV pide {pedido:g}, ya se facturó {ya:g} y esta '
                                      f'factura agrega {c:g}. No se puede facturar más de lo pedido.')
        if tipo == 'Parcial':
            guia = sum((min(p['guiado'], p['pedido']) for p in ps), CERO)
            if ya + c > guia + TOL:
                raise ErrorFacturaParcial(
                    f'Posición {num} "{nombre}": con guía hay {guia:g} y ya se facturó {ya:g}. En una factura parcial '
                    f'solo va lo entregado con guía: puedes facturar hasta {max(guia - ya, CERO):g}.')
    # Lo que queda sin facturar después de esta factura
    quedan = []
    resto = dict(nuevo)
    for p in posiciones:
        dar = min(resto.get(p['clave'], CERO), max(p['pedido'] - p['facturado'], CERO))
        resto[p['clave']] = resto.get(p['clave'], CERO) - dar
        falta = p['pedido'] - p['facturado'] - dar
        if falta > TOL:
            quedan.append((p, dar, falta))
    if tipo == 'Total':
        if quedan and any(p['facturado'] > 0 or dar > 0 for p, dar, _ in quedan) and nuevo:
            # "Total" que no cubre todo: es parcial y necesita el motivo de lo que falta
            p = quedan[0][0]
            raise ErrorFacturaParcial(f'Esta factura no cubre todo el PV (falta la posición {p["posicion"]} "{p["producto"]}"). '
                                      'Elige "Factura parcial" y escribe por qué no se factura lo que falta.')
        return 'Total', None
    if not nuevo:
        raise ErrorFacturaParcial('Marca al menos una posición para facturar.')
    dados = {}
    for m in data.get('pendientes') or []:
        if isinstance(m, dict):
            try:
                dados[int(m.get('posicion'))] = m
            except (TypeError, ValueError):
                continue
    pendientes = []
    for p, dar, falta in quedan:
        m = dados.get(p['posicion']) or {}
        motivo = str(m.get('motivo') or '').strip()
        comentario = ' '.join(str(m.get('comentario') or '').split())[:300]
        if motivo not in MOTIVOS_PENDIENTE:
            raise ErrorFacturaParcial(f'Posición {p["posicion"]} "{p["producto"]}": elige por qué no se factura '
                                      f'({", ".join(MOTIVOS_PENDIENTE)}).')
        if len(comentario) < 5:
            raise ErrorFacturaParcial(f'Posición {p["posicion"]} "{p["producto"]}": escribe un comentario que sustente '
                                      'por qué no se factura (nota interna, el cliente no la ve).')
        pendientes.append({'posicion': p['posicion'], 'codigo': p['codigo'], 'producto': p['producto'],
                           'pedido': float(p['pedido']), 'facturado_antes': float(p['facturado']),
                           'en_esta_factura': float(dar), 'falta': float(falta), 'motivo': motivo,
                           'comentario': comentario[:1].upper() + comentario[1:],
                           'registrado_por': session.get('nombre_completo') or session.get('usuario'),
                           'registrado_en': datetime.now().strftime('%Y-%m-%d %H:%M')})
    return 'Parcial', pendientes


def guardar_tipo(comp_id, tipo, pendientes):
    if not tipo:
        return
    asegurar_columnas()
    db_query("UPDATE comprobantes SET facturacion_tipo = %s, pendientes_json = %s WHERE id = %s RETURNING id",
             (tipo, json.dumps(pendientes, ensure_ascii=False) if pendientes else None, comp_id))


# ------------------------------------------------------------
# Cuadre de 3: almacén (kardex) vs guía vs confirmación del cliente
# ------------------------------------------------------------
def cuadre_despacho(d, guias_por_numero):
    """Diferencias de un despacho que ya salió. Lista vacía = todo cuadra."""
    problemas = []
    salida = {}
    for x in _lista(d.get('stock_detalle')):
        k = x.get('producto_id')
        if k:
            salida[int(k)] = salida.get(int(k), CERO) + a_decimal(x.get('cantidad'))
    guia_txt = str(d.get('guia') or '').strip()
    if not guia_txt:
        problemas.append('Salió del almacén sin guía de remisión')
    else:
        g = guias_por_numero.get(_num_guia(guia_txt))
        if g is None:
            problemas.append(f'La guía {guia_txt} no existe o está anulada')
        elif salida:
            en_guia = {k: v for k, v in _por_clave(g.get('items_json')).items() if isinstance(k, int)}
            for k in set(salida) | set(en_guia):
                if abs(salida.get(k, CERO) - en_guia.get(k, CERO)) > TOL:
                    problemas.append(f'Almacén sacó {salida.get(k, CERO):g} y la guía dice {en_guia.get(k, CERO):g} '
                                     f'({_nombre_producto(k)})')
    if (d.get('estado') or '') == 'Entregado' and not d.get('fecha_entrega_real'):
        problemas.append('Entregado sin fecha real de entrega')
    return problemas


def _num_guia(txt):
    txt = str(txt or '').strip().upper()
    serie, _, num = txt.rpartition('-')
    digitos = ''.join(ch for ch in num if ch.isdigit())
    return (serie, int(digitos)) if digitos else (serie, None)


_nombres = {}


def _nombre_producto(pid):
    if pid not in _nombres:
        f = db_query("SELECT descripcion, codigo FROM productos WHERE id = %s", (pid,))
        _nombres[pid] = (f[0].get('descripcion') or f[0].get('codigo')) if f else str(pid)
    return _nombres[pid]


def alertas_cuadre(limite=60):
    asegurar_columnas()
    despachos = db_query("""SELECT d.id, d.numero, d.estado, d.guia, d.pc_numero, d.cliente, d.stock_detalle,
                                   d.fecha_entrega_real, d.ingreso_cliente, d.responsable,
                                   COALESCE(u.nombre_completo, u.usuario, '') AS creado_por_nombre,
                                   COALESCE(d.fecha_salida, d.fecha_despacho, d.updated_at) AS fecha_salida
                            FROM despachos d LEFT JOIN usuarios u ON u.id::text = d.creado_por::text
                            -- Solo lo que de verdad salió del almacén (descontó stock en el kardex)
                            WHERE d.estado IN ('Despachado', 'Entregado') AND d.stock_estado = 'Descontado'
                            ORDER BY d.id DESC LIMIT 500""")
    guias = {}
    for g in db_query("""SELECT serie, numero, items_json FROM guias_remision
                         WHERE UPPER(COALESCE(estado_sunat, '')) NOT IN ('ANULADO', 'ANULADA')"""):
        n = _num_guia(f"{g.get('serie') or ''}-{g.get('numero') or ''}")
        guias[n] = g
        guias.setdefault(('', n[1]), g)
    out = []
    for d in despachos:
        clave = _num_guia(d.get('guia'))
        if clave not in guias and clave[1] is not None:
            # La guía guardada sin serie también vale
            alt = next((g for (s, n), g in guias.items() if n == clave[1]), None)
            if alt is not None:
                guias[clave] = alt
        problemas = cuadre_despacho(d, guias)
        if problemas:
            out.append({'despacho': d['numero'], 'pv': d.get('pc_numero'), 'cliente': d.get('cliente'),
                        'estado': d.get('estado'), 'guia': d.get('guia') or '—',
                        'despacho_por': d.get('responsable') or d.get('creado_por_nombre') or '—',
                        'fecha': str(d.get('fecha_salida') or '')[:16], 'problemas': problemas})
        if len(out) >= limite:
            break
    return out


def alertas_por_facturar(limite=60):
    """PV con posiciones entregadas sin facturar o con facturación parcial pendiente."""
    asegurar_columnas()
    pvs = db_query("""SELECT DISTINCT p.id, p.numero, p.cotizacion_numero, p.cliente AS cliente_nombre, p.items_json, p.created_at
                      FROM pedido_compra_pc p
                      WHERE UPPER(COALESCE(p.estado, '')) NOT IN ('ANULADO', 'ANULADA')
                        AND (EXISTS (SELECT 1 FROM despachos d WHERE (d.pc_numero = p.numero OR d.pc_id = p.id)
                                     AND d.estado IN ('Despachado', 'Entregado'))
                             OR EXISTS (SELECT 1 FROM comprobantes c WHERE c.pc_vinculado = p.numero
                                        AND c.facturacion_tipo = 'Parcial'
                                        AND UPPER(COALESCE(c.estado_sunat, '')) NOT IN ('ANULADO', 'ANULADA')))
                      ORDER BY p.id DESC LIMIT 300""")
    hoy = date.today()
    out = []
    for pv in pvs:
        r = resumen_pv(pv)
        if not r['faltan_facturar'] or r['facturas'] == 0 and r['entregado_pct'] == 0:
            continue
        sin_facturar_entregado = [p for p in r['posiciones'] if p['entregado'] > p['facturado'] + 0.001]
        if r['facturas'] == 0 and not sin_facturar_entregado:
            continue
        desde = pv.get('created_at')
        dias = (hoy - desde.date()).days if hasattr(desde, 'date') else None
        out.append({'pv': pv['numero'], 'cliente': pv.get('cliente_nombre'), 'dias': dias,
                    'entregado_pct': r['entregado_pct'], 'facturado_pct': r['facturado_pct'],
                    'faltan': r['faltan_facturar'],
                    'motivos': [f"Posición {p['posicion']}: {p['motivo']['motivo']}" for p in r['posiciones'] if p.get('motivo')],
                    'entregado_sin_factura': [p['posicion'] for p in sin_facturar_entregado]})
        if len(out) >= limite:
            break
    return out


# ------------------------------------------------------------
# API
# ------------------------------------------------------------
def _sesion():
    return bool(session.get('usuario_id'))


@facturacion_parcial_bp.route('/ventas/api/pv/avance')
def api_avance_pv():
    if not _sesion():
        return jsonify({'success': False, 'error': 'Inicia sesión.'}), 401
    asegurar_columnas()
    pv = pv_por_numero(request.args.get('numero'))
    if not pv:
        return jsonify({'success': False, 'error': 'No se encontró el PV.'}), 404
    excluir = request.args.get('excluir')
    try:
        excluir = int(excluir) if excluir else None
    except ValueError:
        excluir = None
    r = resumen_pv(pv, excluir)
    r['motivos_lista'] = list(MOTIVOS_PENDIENTE)
    return jsonify({'success': True, 'data': r})


@facturacion_parcial_bp.route('/ventas/api/pv/avance-lista')
def api_avance_lista():
    """Entregado % y Facturado % de varios PV (para la tabla de PV)."""
    if not _sesion():
        return jsonify({'success': False, 'error': 'Inicia sesión.'}), 401
    asegurar_columnas()
    numeros = [n.strip() for n in (request.args.get('numeros') or '').split(',') if n.strip()][:200]
    out = {}
    if numeros:
        for pv in db_query("""SELECT DISTINCT ON (numero) id, numero, cotizacion_numero, cliente AS cliente_nombre, items_json, created_at
                              FROM pedido_compra_pc WHERE numero = ANY(%s)
                                AND UPPER(COALESCE(estado, '')) NOT IN ('ANULADO', 'ANULADA')
                              ORDER BY numero, id DESC""", (numeros,)):
            r = resumen_pv(pv)
            out[pv['numero']] = {k: r[k] for k in ('entregado_pct', 'facturado_pct', 'faltan_facturar', 'facturas')}
            out[pv['numero']]['motivos'] = [f"{p['posicion']}: {p['motivo']['motivo']}" for p in r['posiciones'] if p.get('motivo')]
    return jsonify({'success': True, 'data': out})


@facturacion_parcial_bp.route('/ventas/api/control/alertas')
def api_alertas_control():
    """Inicio de Erika: PV por facturar y despachos que no cuadran (almacén vs guía vs cliente)."""
    if not _sesion():
        return jsonify({'success': False, 'error': 'Inicia sesión.'}), 401
    from utils import es_admin, es_duena_reportes
    if not (es_admin() or es_duena_reportes()):
        return jsonify({'success': True, 'por_facturar': [], 'cuadre': [], 'solo_gerencia': True})
    try:
        return jsonify({'success': True, 'por_facturar': alertas_por_facturar(), 'cuadre': alertas_cuadre()})
    except Exception as e:
        print(f'❌ Alertas de control: {e}')
        return jsonify({'success': False, 'error': 'No se pudieron revisar las alertas.'}), 500
