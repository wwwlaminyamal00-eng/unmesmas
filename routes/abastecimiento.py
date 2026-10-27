# routes/abastecimiento.py - "¿Hay stock o falta comprar/recoger?" para productos, cotizaciones, PV y despachos
#
# Regla (requerimiento obligatorio del Excel de pendientes):
#   Cuando un producto falta (stock 0 o insuficiente) se muestra solo:
#     - "Pendiente por compra": todavía no hay una orden de compra aprobada que cubra lo que falta.
#     - "Pendiente por recojo": ya se compró (OC aprobada) y nosotros debemos recogerlo del proveedor.
#     - "Por llegar": ya se compró y el proveedor lo trae a la sede.
#   Stock que cuenta = stock de todo el grupo (todas las empresas y sedes) menos lo separado para otros clientes.
#   Para un PV solo cuentan las OC hechas para ese PV; para cotizaciones y productos cuentan todas las OC abiertas.
# 22/10/2026 (Erika, urgente "sigue diciendo que falta stock después de generar la OC"):
#   - Una OC cuenta como "comprado, por llegar" desde que se genera (Borrador, Por aprobar o Aprobada), no solo
#     aprobada. Antes solo contaban las aprobadas, por eso seguía saliendo "Pendiente de compra".
#   - El stock libre se reparte entre los pedidos (el más antiguo primero) y no se cuenta dos veces: con 32 en stock,
#     un PV de 18 y otro de 40, al primero le tocan 18 y al segundo 14 (faltan 26), no 32 a cada uno.
#   - Cada estado trae el N° de la OC que lo cubre.
# 27/10/2026 (Erika y Hellen, "ya recibí la mercadería y sigue diciendo Pendiente de compra"):
#   - Lo que se RECIBIÓ con una OC hecha para un PV queda para ese PV: se le asigna primero, antes de repartir el
#     resto del stock por antigüedad. Antes entraba al stock común y se lo llevaba un PV más antiguo.
#     OJO: no basta con "hay stock" (podría ser de otro pedido y se vendería dos veces): cuenta lo de ese PV.
#   - Lo ya despachado de un PV se descuenta de lo que el PV necesita (esas unidades ya salieron del almacén).
#   - Cotización con PV: muestra el estado de su PV; si ya se despachó o entregó, dice "Despachado" o "Entregado"
#     y nunca "Pendiente de compra".
# No crea tablas ni columnas: solo lee lo que ya registran Inventario, Compras y Despachos.
from collections import defaultdict
from decimal import Decimal

from flask import Blueprint, jsonify

from database import db_query
from utils import a_decimal

abastecimiento_bp = Blueprint('abastecimiento', __name__, url_prefix='/api/abastecimiento')

CON_STOCK = 'Con stock'
DESPACHADO = 'Despachado'
ENTREGADO = 'Entregado'
ESTADOS_SALIDA = (DESPACHADO, ENTREGADO)
SIN_STOCK = 'Sin stock'
POR_COMPRA = 'Pendiente por compra'
POR_RECOJO = 'Pendiente por recojo'
POR_LLEGAR = 'Por llegar'
# Del más urgente al menos urgente: un documento muestra el estado de su producto más atrasado
PRIORIDAD = (POR_COMPRA, POR_RECOJO, POR_LLEGAR, CON_STOCK)
RECOGEMOS = 'Nosotros recogemos'
OC_ABIERTAS = ('Aprobada', 'Recibida parcial')     # (antes) solo estas contaban como compradas
OC_FUERA = ('Anulada', 'Anulado', 'Cancelada', 'Rechazada')   # el resto, con algo por recibir, cuenta como "por llegar"


def _preparar():
    from routes.inventario import asegurar_tablas_inventario
    from routes.compras_flujo import asegurar_tablas_compras
    asegurar_tablas_inventario()
    asegurar_tablas_compras()


def _en_camino(producto_ids, pedido_id=None):
    """Lo comprado (OC generada, no anulada) que aún no se recibe, separado en 'recojo' y 'llega', con sus N° de OC.
    Devuelve {(pedido_id o None, producto_id): {'recojo': x, 'llega': y, 'ocs': [...]}}."""
    if not producto_ids:
        return {}
    filas = db_query("""
        SELECT oci.pedido_id, oci.producto_id, oc.modalidad_entrega, oc.numero_orden,
               SUM(GREATEST(oci.cantidad - COALESCE(oci.cantidad_recibida, 0), 0)) AS pendiente
        FROM ordenes_compra_items oci JOIN ordenes_compra oc ON oc.id = oci.orden_compra_id
        WHERE COALESCE(oc.estado, '') <> ALL(%s) AND oci.producto_id = ANY(%s)
          AND (%s::int IS NULL OR oci.pedido_id = %s::int)
        GROUP BY oci.pedido_id, oci.producto_id, oc.modalidad_entrega, oc.numero_orden
        HAVING SUM(GREATEST(oci.cantidad - COALESCE(oci.cantidad_recibida, 0), 0)) > 0
    """, (list(OC_FUERA), list(producto_ids), pedido_id, pedido_id))
    res = defaultdict(lambda: {'recojo': Decimal('0'), 'llega': Decimal('0'), 'ocs': []})
    for f in filas:
        clave = 'recojo' if f['modalidad_entrega'] == RECOGEMOS else 'llega'
        r = res[(f['pedido_id'], f['producto_id'])]
        r[clave] += a_decimal(f['pendiente'])
        if f['numero_orden'] and f['numero_orden'] not in r['ocs']:
            r['ocs'].append(f['numero_orden'])
    return res


def _recibido_por_pedido(producto_ids):
    """{(pedido_id, producto_id): cantidad ya recibida en almacén con OC (no anuladas) hechas para ese PV}."""
    if not producto_ids:
        return {}
    filas = db_query("""
        SELECT oci.pedido_id, oci.producto_id, SUM(COALESCE(oci.cantidad_recibida, 0)) AS recibido
        FROM ordenes_compra_items oci JOIN ordenes_compra oc ON oc.id = oci.orden_compra_id
        WHERE COALESCE(oc.estado, '') <> ALL(%s) AND oci.producto_id = ANY(%s) AND oci.pedido_id IS NOT NULL
        GROUP BY oci.pedido_id, oci.producto_id
        HAVING SUM(COALESCE(oci.cantidad_recibida, 0)) > 0
    """, (list(OC_FUERA), list(producto_ids)))
    return {(f['pedido_id'], f['producto_id']): a_decimal(f['recibido']) for f in filas}


def _separado_por_pedido(producto_ids):
    """{(pedido_id, producto_id): cantidad} separada (vigente) en el inventario para ese PV. Ese stock ya no está en
    el "stock libre", así que se le da a su PV sin restarlo otra vez (27/10/2026, PV-KCF-000026: salía
    "Pendiente de compra" con 21 en stock porque lo separado para otros PV se descontaba dos veces)."""
    if not producto_ids:
        return {}
    filas = db_query("""
        SELECT p.id AS pedido_id, s.producto_id, SUM(s.cantidad) AS c
        FROM inv_separaciones s JOIN pedido_compra_pc p ON p.numero = s.documento
        WHERE s.estado = 'Activa' AND s.vence_el >= CURRENT_DATE AND s.producto_id = ANY(%s)
        GROUP BY p.id, s.producto_id
    """, (list(producto_ids),))
    return {(f['pedido_id'], f['producto_id']): a_decimal(f['c']) for f in filas}


def _salidas_por_pedido(pedido_ids=None):
    """Lo que ya salió del almacén por PV: ({(pc_id, producto_id): cantidad}, {pc_id: 'Despachado'|'Entregado'}).
    El estado es 'Entregado' solo si todos sus despachos que salieron ya se entregaron."""
    from routes.compras_flujo import _items_pedido, _resolver_productos
    filas = db_query("""
        SELECT d.pc_id, d.estado, COALESCE(NULLIF(d.items_json::text, '[]'), pc.items_json::text) AS items_json
        FROM despachos d LEFT JOIN pedido_compra_pc pc ON pc.id = d.pc_id
        WHERE d.pc_id IS NOT NULL AND COALESCE(d.estado, '') = ANY(%s)
          AND (%s::int[] IS NULL OR d.pc_id = ANY(%s::int[]))
    """, (list(ESTADOS_SALIDA), pedido_ids, pedido_ids))
    cantidades = defaultdict(Decimal)
    estado = {}
    for f in filas:
        items = _items_pedido(f)
        _resolver_productos(items)
        for it in items:
            if it['producto_id']:
                cantidades[(f['pc_id'], it['producto_id'])] += a_decimal(it['cantidad'])
        if f['estado'] == DESPACHADO or estado.get(f['pc_id']) == DESPACHADO:
            estado[f['pc_id']] = DESPACHADO
        else:
            estado[f['pc_id']] = ENTREGADO
    return dict(cantidades), estado


def _restar_salidas(items, pedido_id, salidas):
    """Items del PV menos lo ya despachado. Devuelve la lista con lo que aún falta entregar (sin los que ya salieron)."""
    from routes.compras_flujo import _resolver_productos
    _resolver_productos(items)
    usado = defaultdict(Decimal)
    quedan = []
    for it in items:
        pid = it['producto_id']
        if pid:
            salio = max(salidas.get((pedido_id, pid), Decimal('0')) - usado[pid], Decimal('0'))
            toma = min(salio, a_decimal(it['cantidad']))
            usado[pid] += toma
            resto = a_decimal(it['cantidad']) - toma
            if resto <= 0:
                continue
            it = dict(it, cantidad=resto)
        quedan.append(it)
    return quedan


def ocs_en_transito(producto_ids):
    """{producto_id: ['OC-...', ...]} de las OC generadas (no anuladas) que aún no se reciben."""
    salida = defaultdict(list)
    for (_, pid), v in _en_camino(list(producto_ids)).items():
        for n in v['ocs']:
            if n not in salida[pid]:
                salida[pid].append(n)
    return dict(salida)


def _sumar_global(en_camino):
    total = defaultdict(lambda: {'recojo': Decimal('0'), 'llega': Decimal('0'), 'ocs': []})
    for (_, prod), v in en_camino.items():
        total[prod]['recojo'] += v['recojo']
        total[prod]['llega'] += v['llega']
        total[prod]['ocs'] += [n for n in v.get('ocs', []) if n not in total[prod]['ocs']]
    return total


def estado_item(cantidad, libre, recojo, llega):
    """Estado de un producto dentro de un documento."""
    cantidad, libre = a_decimal(cantidad), max(a_decimal(libre), Decimal('0'))
    if cantidad <= 0 or libre >= cantidad:
        return CON_STOCK
    if libre + recojo + llega < cantidad:
        return POR_COMPRA
    return POR_RECOJO if recojo > 0 else POR_LLEGAR


def _peor(estados):
    for e in PRIORIDAD:
        if e in estados:
            return e
    return CON_STOCK


def _resumen(items_estado):
    faltan = [i for i in items_estado if i['estado'] != CON_STOCK]
    ocs = []
    for i in items_estado:
        ocs += [n for n in i.get('ocs', []) if n not in ocs]
    return {'estado': _peor({i['estado'] for i in items_estado}) if items_estado else None,
            'faltan': len(faltan), 'ocs': ocs[:5],
            'detalle': [f"{i['descripcion'] or i['codigo']}: {i['estado'].lower()}"
                        + (f" ({', '.join(i['ocs'])})" if i.get('ocs') and i['estado'] != CON_STOCK else '')
                        for i in faltan][:6]}


def evaluar_documentos(docs, por_pedido=False):
    """docs: {doc_id: {'pedido_id': int|None, 'items': [{producto_id, codigo, descripcion, cantidad}]}}"""
    from routes.compras_flujo import _resolver_productos, _stock_libre_grupo
    ids = set()
    for d in docs.values():
        _resolver_productos(d['items'])
        ids.update(i['producto_id'] for i in d['items'] if i['producto_id'])
    libre = _stock_libre_grupo(ids)
    camino = _en_camino(ids)
    camino_global = _sumar_global(camino)
    vacio = {'recojo': Decimal('0'), 'llega': Decimal('0'), 'ocs': []}
    # Pedidos: el stock libre se reparte, el pedido más antiguo primero, y no se cuenta dos veces.
    # Lo que ya está en una OC de ese pedido no necesita stock. Varios despachos del mismo PV comparten su parte.
    restante = dict(libre)
    asignado = {}
    if por_pedido:
        # 1) Primero, a cada PV lo que llegó con SUS órdenes de compra (27/10/2026)
        recibido = _recibido_por_pedido(ids)
        separado = _separado_por_pedido(ids)
        for doc_id in sorted(docs, key=lambda k: (docs[k].get('pedido_id') or 10 ** 12, k)):
            d = docs[doc_id]
            if not d.get('pedido_id'):
                continue
            llave_doc = ('pc', d['pedido_id'])
            for it in d['items']:
                pid = it['producto_id']
                if not pid or (llave_doc, pid) in asignado:
                    continue
                c = camino.get((d['pedido_id'], pid), vacio)
                necesita = max(a_decimal(it['cantidad']) - c['recojo'] - c['llega'], Decimal('0'))
                # a) Lo separado para este PV (ya está fuera del stock libre: no se resta de nuevo)
                sep = separado.get((d['pedido_id'], pid), Decimal('0'))
                de_sep = min(necesita, sep)
                # b) Lo recibido con sus OC que no quedó separado, tomado del stock libre
                propio = recibido.get((d['pedido_id'], pid), Decimal('0')) - d.get('salido', {}).get(pid, Decimal('0')) - sep
                toca = min(max(restante.get(pid, Decimal('0')), Decimal('0')), necesita - de_sep, max(propio, Decimal('0')))
                toca = max(toca, Decimal('0'))
                if toca > 0:
                    restante[pid] = restante.get(pid, Decimal('0')) - toca
                if de_sep + toca > 0:
                    asignado[(llave_doc, pid)] = de_sep + toca
        # 2) Luego, el resto del stock libre por antigüedad
        for doc_id in sorted(docs, key=lambda k: (docs[k].get('pedido_id') or 10 ** 12, k)):
            d = docs[doc_id]
            llave_doc = ('pc', d['pedido_id']) if d.get('pedido_id') else ('doc', doc_id)
            for it in d['items']:
                pid = it['producto_id']
                if not pid or (llave_doc, pid, 'general') in asignado:
                    continue
                c = camino.get((d.get('pedido_id'), pid), vacio) if d.get('pedido_id') else vacio
                ya = asignado.get((llave_doc, pid), Decimal('0'))
                necesita = max(a_decimal(it['cantidad']) - c['recojo'] - c['llega'] - ya, Decimal('0'))
                toca = min(max(restante.get(pid, Decimal('0')), Decimal('0')), necesita)
                restante[pid] = restante.get(pid, Decimal('0')) - toca
                asignado[(llave_doc, pid)] = ya + toca
                asignado[(llave_doc, pid, 'general')] = True
    salida = {}
    for doc_id, d in docs.items():
        evaluados = []
        llave_doc = ('pc', d['pedido_id']) if d.get('pedido_id') else ('doc', doc_id)
        for it in d['items']:
            if not it['producto_id']:
                continue  # producto escrito a mano (sin código del catálogo): no se puede saber su stock
            if por_pedido and d.get('pedido_id'):
                c = camino.get((d['pedido_id'], it['producto_id']), vacio)
            else:
                c = camino_global.get(it['producto_id'], vacio)
            stock_doc = asignado.get((llave_doc, it['producto_id']), Decimal('0')) if por_pedido \
                else libre.get(it['producto_id'], 0)
            evaluados.append({'codigo': it['codigo'], 'descripcion': it.get('descripcion'), 'ocs': c.get('ocs', []),
                              'estado': estado_item(it['cantidad'], stock_doc, c['recojo'], c['llega'])})
        if evaluados:
            salida[doc_id] = _resumen(evaluados)
    return salida


# ============================================================
# API
# ============================================================
def estados_pv():
    """{pv_id: resumen} de los PV abiertos. Lo ya despachado no cuenta; un PV que ya salió entero dice
    'Despachado' o 'Entregado' (nunca 'Pendiente por compra')."""
    from routes.compras_flujo import _items_pedido, ESTADOS_PC_FUERA
    filas = db_query("""
        SELECT id, items_json FROM pedido_compra_pc
        WHERE COALESCE(UPPER(estado), '') <> ALL(%s) ORDER BY id DESC LIMIT 500
    """, (list(ESTADOS_PC_FUERA),))
    salidas, estado_salida = _salidas_por_pedido([f['id'] for f in filas])
    docs, salieron = {}, {}
    for f in filas:
        items = _items_pedido(f)
        quedan = _restar_salidas(items, f['id'], salidas)
        if f['id'] in estado_salida and not quedan:
            salieron[f['id']] = {'estado': estado_salida[f['id']], 'faltan': 0, 'ocs': [], 'detalle': []}
            continue
        docs[f['id']] = {'pedido_id': f['id'], 'items': quedan,
                         'salido': {pid: c for (pv, pid), c in salidas.items() if pv == f['id']}}
    data = evaluar_documentos(docs, por_pedido=True)
    data.update(salieron)
    return data


@abastecimiento_bp.route('/pc')
def api_pc():
    """Estado de abastecimiento de cada pedido de venta (PV) abierto."""
    _preparar()
    return jsonify({'success': True, 'data': estados_pv()})


@abastecimiento_bp.route('/cotizaciones')
def api_cotizaciones():
    """Estado de abastecimiento de las cotizaciones aceptadas por el cliente (informativo para el vendedor).
    Pedido de Erika 20/10/2026: en "Generada" (o antes) no se muestra "Pendiente por compra"."""
    _preparar()
    filas = db_query("""
        SELECT d.cotizacion_id, d.producto_id, p.codigo, p.descripcion, SUM(d.cantidad) AS cantidad
        FROM cotizacion_detalle d JOIN cotizaciones c ON c.id = d.cotizacion_id
        LEFT JOIN productos p ON p.id = d.producto_id
        WHERE COALESCE(c.estado, '') IN ('Aceptada por Cliente', 'Aceptada')
        GROUP BY d.cotizacion_id, d.producto_id, p.codigo, p.descripcion
    """)
    docs = defaultdict(lambda: {'pedido_id': None, 'items': []})
    for f in filas:
        docs[f['cotizacion_id']]['items'].append({'producto_id': f['producto_id'], 'codigo': f['codigo'] or '',
                                                  'descripcion': f['descripcion'], 'cantidad': a_decimal(f['cantidad'])})
    # 27/10/2026: la cotización que ya tiene PV toma el estado de su PV (despachado/entregado o lo que falte)
    from routes.compras_flujo import ESTADOS_PC_FUERA
    pv_de = {}
    if docs:
        for f in db_query("""
            SELECT c.id AS cot_id, MAX(pc.id) AS pv_id
            FROM cotizaciones c JOIN pedido_compra_pc pc
              ON pc.cotizacion_numero IN (c.codigo_cotizacion, c.numero_cotizacion)
             AND COALESCE(UPPER(pc.estado), '') NOT IN ('ANULADO', 'ANULADA', 'RECHAZADO', 'RECHAZADA')
            WHERE c.id = ANY(%s) GROUP BY c.id
        """, (list(docs),)):
            pv_de[f['cot_id']] = f['pv_id']
    data = evaluar_documentos({k: v for k, v in docs.items() if k not in pv_de})
    if pv_de:
        pvs = estados_pv()
        # PV cerrado (ya no está entre los abiertos): solo se muestra si salió del almacén
        _, salida_cerrados = _salidas_por_pedido([v for v in pv_de.values() if v not in pvs])
        for cot_id, pv_id in pv_de.items():
            if pv_id in pvs:
                data[cot_id] = pvs[pv_id]
            elif pv_id in salida_cerrados:
                data[cot_id] = {'estado': salida_cerrados[pv_id], 'faltan': 0, 'ocs': [], 'detalle': []}
    return jsonify({'success': True, 'data': data})


@abastecimiento_bp.route('/despachos')
def api_despachos():
    """Despachos por salir: usan el estado de su PV (o sus propios productos si no tienen PV)."""
    from routes.compras_flujo import _items_pedido
    _preparar()
    filas = db_query("""
        SELECT d.id, d.pc_id, COALESCE(NULLIF(d.items_json::text, '[]'), pc.items_json::text) AS items_json,
               COALESCE(d.items_json::text, '[]') = '[]' AS usa_items_pv
        FROM despachos d LEFT JOIN pedido_compra_pc pc ON pc.id = d.pc_id
        WHERE COALESCE(d.estado, '') NOT IN ('Despachado', 'Entregado', 'Anulado')
        ORDER BY d.id DESC LIMIT 500
    """)
    # 27/10/2026: lo que el PV ya despachó en otros despachos no se vuelve a pedir
    salidas, _ = _salidas_por_pedido([f['pc_id'] for f in filas if f['pc_id']] or [0])
    docs = {}
    for f in filas:
        items = _items_pedido(f)
        if f['pc_id'] and f['usa_items_pv']:
            items = _restar_salidas(items, f['pc_id'], salidas)
        docs[f['id']] = {'pedido_id': f['pc_id'], 'items': items,
                         'salido': {pid: c for (pv, pid), c in salidas.items() if pv == f['pc_id']}}
    return jsonify({'success': True, 'data': evaluar_documentos(docs, por_pedido=True)})


@abastecimiento_bp.route('/productos')
def api_productos():
    """Por producto: stock libre, lo que piden los PV abiertos y si falta comprar o recoger."""
    from routes.compras_flujo import _pedidos_por_comprar, _stock_libre_grupo
    _preparar()
    demanda = defaultdict(Decimal)
    for pc in _pedidos_por_comprar(todos=True):
        for it in pc['items']:
            if it['producto_id']:
                demanda[it['producto_id']] += a_decimal(it['cantidad'])
    filas = db_query("SELECT id FROM productos WHERE COALESCE(activo, true)")
    ids = [f['id'] for f in filas]
    libre = _stock_libre_grupo(ids)
    camino = _sumar_global(_en_camino(ids))
    data = {}
    for pid in ids:
        lib = libre.get(pid, Decimal('0'))
        c = camino.get(pid, {'recojo': Decimal('0'), 'llega': Decimal('0')})
        pedido = demanda.get(pid, Decimal('0'))
        if pedido > 0:
            estado = estado_item(pedido, lib, c['recojo'], c['llega'])
        elif lib > 0:
            estado = CON_STOCK
        elif c['recojo'] > 0:
            estado = POR_RECOJO
        elif c['llega'] > 0:
            estado = POR_LLEGAR
        else:
            estado = SIN_STOCK  # nadie lo ha pedido: bajo pedido, no hace falta comprarlo
        data[pid] = {'estado': estado, 'libre': float(lib), 'pedido': float(pedido),
                     'por_recoger': float(c['recojo']), 'por_llegar': float(c['llega'])}
    return jsonify({'success': True, 'data': data})
