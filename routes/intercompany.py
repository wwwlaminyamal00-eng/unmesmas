# routes/intercompany.py - Intercompany KCF ↔ AGD (pedido de Erika, 21/10/2026 23:30)
#
# Qué muestra (en simple), por mes:
#   1. Ventas entre las empresas del grupo: quién le vendió a quién, cuánto y con qué factura.
#   2. Control cruzado: cada venta entre empresas debe estar registrada como COMPRA en la otra
#      (si no, esa empresa pierde el crédito fiscal). Lo que falta sale en rojo.
#   3. Lo que se deben entre ellas (facturas intercompany con saldo).
#   4. IGV del mes de cada empresa (el mismo cálculo del módulo SUNAT) y una sugerencia LEGAL de desde qué
#      empresa facturar para no pagar IGV de más cuando una tiene saldo a favor o retenciones sin usar.
#   5. Stock del grupo: cuánto tiene cada empresa de cada producto y el total.
#
# Reglas:
#   - No crea tablas ni cambia datos: solo LEE ventas, compras, Finanzas, Inventario y SUNAT.
#   - Acceso: administrador (Gerencia total) o quien tenga "Ver" en "Intercompany". Se valida en el servidor.
#   - Las ventas se reconocen solas: cliente (o proveedor) con el RUC de otra empresa del grupo.
import re
from collections import defaultdict
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal

from flask import Blueprint, render_template, request, jsonify, session

from database import db_query
from utils import a_decimal, redondear, es_admin, tasa_igv
from routes.multiempresa import empresas as lista_empresas

intercompany_bp = Blueprint('intercompany', __name__)


def _ahora():
    """Fecha y hora de Lima (el servidor de Render está en UTC)."""
    return datetime.now(ZoneInfo('America/Lima')).replace(tzinfo=None)
CERO = Decimal('0')


class ErrorIntercompany(Exception):
    pass


# ============================================================
# PERMISO (en el servidor)
# ============================================================
def puede_ver_intercompany():
    if es_admin():
        return True
    try:
        from routes.acceso import acceso_usuario
        acc = acceso_usuario()
    except Exception:
        return False
    return bool(acc.get('configurado') and 'intercompany' in acc.get('modulos', set()))


@intercompany_bp.before_request
def _proteger():
    if 'usuario_id' not in session:
        return None
    if not puede_ver_intercompany():
        msg = ('No tienes permiso para entrar a Intercompany. Lo ve solo la gerencia y quien tenga el permiso '
               '"Intercompany" en Configuración ▸ Usuarios y permisos.')
        if '/api/' in request.path:
            return jsonify({'success': False, 'error': msg, 'codigo': 'sin_permiso'}), 403
        from flask import flash, redirect, url_for
        flash(msg, 'error')
        return redirect(url_for('index'))
    from routes.sunat import asegurar_tablas
    asegurar_tablas()
    return None


# ============================================================
# AYUDAS
# ============================================================
def _n(v):
    return float(redondear(v or 0, 2))


def _rucs(txt):
    return re.sub(r'\D', '', str(txt or ''))


def _num_doc(numero):
    d = re.sub(r'\D', '', str(numero or ''))
    return str(int(d)) if d else str(numero or '').strip().upper()


def _clave_doc(serie, numero):
    return ((serie or '').strip().upper(), _num_doc(numero))


def _grupo():
    """Empresas del grupo con RUC (solo esas pueden venderse entre ellas)."""
    emps = [e for e in lista_empresas() if _rucs(e.get('ruc'))]
    if len(emps) < 2:
        raise ErrorIntercompany('Hacen falta al menos 2 empresas con RUC en Configuración ▸ Empresas.')
    return emps


def _periodo(txt):
    m = re.match(r'^(\d{4})-(\d{2})$', (txt or '').strip())
    if m and 1 <= int(m.group(2)) <= 12:
        return int(m.group(1)), int(m.group(2))
    h = _ahora().date()
    return h.year, h.month


def _mes_mas(anio, mes, n):
    t = anio * 12 + (mes - 1) + n
    return t // 12, t % 12 + 1


def _rango(anio, mes):
    a2, m2 = _mes_mas(anio, mes, 1)
    return date(anio, mes, 1), date(a2, m2, 1) - timedelta(days=1)


MESES_CORTO = ('Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Set', 'Oct', 'Nov', 'Dic')


# ============================================================
# VENTAS Y COMPRAS ENTRE EMPRESAS
# ============================================================
def _ventas(e, desde, hasta):
    """Ventas del ERP + lo importado del SIRE/Excel (sin contar dos veces), igual que el módulo SUNAT."""
    from routes.sunat import ventas_erp, importados, combinar
    erp, _ = ventas_erp(e['id'], desde, hasta)
    imp = []
    a, m = desde.year, desde.month
    while (a, m) <= (hasta.year, hasta.month):
        imp += [r for r in importados(e['id'], f'{a:04d}-{m:02d}', 'VENTAS')
                if not r['fecha'] or desde <= r['fecha'] <= hasta]
        a, m = _mes_mas(a, m, 1)
    return combinar('VENTAS', erp, imp)[0]


def _compras(e, desde, hasta):
    from routes.sunat import compras_erp, importados, combinar
    erp = compras_erp(e['id'], desde, hasta)
    imp = []
    a, m = desde.year, desde.month
    while (a, m) <= (hasta.year, hasta.month):
        imp += importados(e['id'], f'{a:04d}-{m:02d}', 'COMPRAS')
        a, m = _mes_mas(a, m, 1)
    return combinar('COMPRAS', erp, imp)[0]


def ventas_entre_empresas(emps, desde, hasta):
    """[{vende, compra, fecha, documento, base, igv, total, fuente, registrada_en_compras}]"""
    por_ruc = {_rucs(e['ruc']): e for e in emps}
    salida = []
    # Compras de cada empresa, desde el inicio del mes hasta 2 meses después (la compra puede registrarse tarde)
    compras_de = {}
    fin_compras = _rango(*_mes_mas(hasta.year, hasta.month, 2))[1]
    for e in emps:
        compras_de[e['id']] = {(_rucs(c['ruc']),) + _clave_doc(c['serie'], c['numero']): c
                               for c in _compras(e, desde, fin_compras)}
    for e in emps:
        for v in _ventas(e, desde, hasta):
            otra = por_ruc.get(_rucs(v['ruc']))
            if not otra or otra['id'] == e['id']:
                continue
            compra = compras_de[otra['id']].get((_rucs(e['ruc']),) + _clave_doc(v['serie'], v['numero']))
            salida.append({
                'vende': e['codigo'], 'vende_id': e['id'], 'compra': otra['codigo'], 'compra_id': otra['id'],
                'fecha': v['fecha'].isoformat() if v.get('fecha') else None,
                'documento': f"{v['serie']}-{v['numero']}", 'tipo': v['tipo'],
                'base': _n(v['base']), 'igv': _n(v['igv']), 'total': _n(v['total']), 'fuente': v.get('fuente'),
                'registrada_en_compras': bool(compra),
                'compra_registrada_el': compra['fecha'].isoformat() if compra and compra.get('fecha') else None,
            })
    salida.sort(key=lambda x: (x['fecha'] or '', x['documento']), reverse=True)
    return salida


def tendencia(emps, anio, mes, meses=6):
    """Ventas entre empresas (base) de los últimos meses, por sentido."""
    sentidos = [(a['codigo'], b['codigo']) for a in emps for b in emps if a['id'] != b['id']]
    filas = []
    for i in range(meses - 1, -1, -1):
        a, m = _mes_mas(anio, mes, -i)
        desde, hasta = _rango(a, m)
        docs = ventas_entre_empresas(emps, desde, hasta)
        fila = {'periodo': f'{a:04d}-{m:02d}', 'nombre': f'{MESES_CORTO[m - 1]} {a}', 'sentidos': {}}
        for s in sentidos:
            fila['sentidos'][f'{s[0]}→{s[1]}'] = _n(sum((a_decimal(d['base']) for d in docs
                                                         if (d['vende'], d['compra']) == s), CERO))
        filas.append(fila)
    return [f'{a}→{b}' for a, b in sentidos], filas


# ============================================================
# LO QUE SE DEBEN
# ============================================================
def deudas(emps):
    """Facturas entre empresas con saldo por cobrar (lo que una le debe a la otra), con lo vencido."""
    from routes.finanzas import SQL_CXC, asegurar_tablas_finanzas
    asegurar_tablas_finanzas()
    hoy = _ahora().date()
    salida = []
    for e in emps:
        otros = {_rucs(x['ruc']): x for x in emps if x['id'] != e['id']}
        filas = db_query(SQL_CXC + """ AND COALESCE(UPPER(c.estado_sunat), 'BORRADOR') <> 'BORRADOR'
                                       AND (c.empresa_id IS NULL OR c.empresa_id::text = %s)
                                       AND regexp_replace(COALESCE(c.cliente_numero_doc, ''), '\\D', '', 'g') = ANY(%s)""",
                         (str(e['id']), list(otros)))
        for f in filas:
            saldo = redondear(a_decimal(f['importe_cobrar']) - a_decimal(f['cobrado']) - a_decimal(f['notas_credito']))
            if saldo <= 0:
                continue
            venc = f.get('fecha_vencimiento')
            venc = venc.date() if hasattr(venc, 'date') and not isinstance(venc, date) else venc
            deudor = otros[_rucs(f['ruc'])]
            salida.append({'acreedor': e['codigo'], 'deudor': deudor['codigo'], 'documento': f['documento'],
                           'fecha': f['fecha_emision'].isoformat()[:10] if f.get('fecha_emision') else None,
                           'vence': venc.isoformat() if venc else None,
                           'dias_vencido': (hoy - venc).days if venc and venc < hoy else 0,
                           'total': _n(f['importe_cobrar']), 'saldo': _n(saldo)})
    pares = defaultdict(lambda: {'saldo': CERO, 'vencido': CERO, 'n': 0})
    for d in salida:
        p = pares[(d['deudor'], d['acreedor'])]
        p['saldo'] += a_decimal(d['saldo'])
        p['n'] += 1
        if d['dias_vencido'] > 0:
            p['vencido'] += a_decimal(d['saldo'])
    resumen = [{'deudor': k[0], 'acreedor': k[1], 'saldo': _n(v['saldo']), 'vencido': _n(v['vencido']), 'facturas': v['n']}
               for k, v in pares.items()]
    # Neto entre cada par: si las dos se deben, se ve quién le debe a quién al final
    netos = []
    vistos = set()
    for r in resumen:
        par = tuple(sorted((r['deudor'], r['acreedor'])))
        if par in vistos:
            continue
        vistos.add(par)
        ida = sum((a_decimal(x['saldo']) for x in resumen if (x['deudor'], x['acreedor']) == par), CERO)
        vuelta = sum((a_decimal(x['saldo']) for x in resumen if (x['deudor'], x['acreedor']) == par[::-1]), CERO)
        neto = ida - vuelta
        if neto != 0:
            netos.append({'deudor': par[0] if neto > 0 else par[1], 'acreedor': par[1] if neto > 0 else par[0],
                          'saldo': _n(abs(neto))})
    salida.sort(key=lambda x: (-x['dias_vencido'], x['fecha'] or ''))
    return {'detalle': salida, 'resumen': resumen, 'netos': netos}


# ============================================================
# IGV Y SUGERENCIA (desde qué empresa facturar)
# ============================================================
def igv_del_mes(emps, anio, mes):
    from routes.sunat import calcular
    salida = []
    for e in emps:
        try:
            r = calcular(e, anio, mes)
        except Exception as ex:   # sin datos de SUNAT: no se rompe la pantalla
            salida.append({'codigo': e['codigo'], 'id': e['id'], 'error': str(ex)})
            continue
        liq = r['liq']
        credito_libre = liq['saldo_favor_siguiente'] + liq['saldo_retenciones_siguiente'] + liq['saldo_percepciones_siguiente']
        salida.append({'codigo': e['codigo'], 'id': e['id'], 'igv_ventas': _n(r['sv']['igv']), 'igv_compras': _n(r['sc']['igv']),
                       'igv_pagar': _n(liq['igv_pagar']), 'saldo_favor': _n(liq['saldo_favor_siguiente']),
                       'retenciones_libres': _n(liq['saldo_retenciones_siguiente'] + liq['saldo_percepciones_siguiente']),
                       'credito_libre': _n(credito_libre),
                       'vencimiento': r['vencimiento'].isoformat() if r.get('vencimiento') else None})
    return salida


def sugerencias(igv):
    """Reglas simples y legales. Monto sugerido = IGV que la otra empresa puede absorber con su saldo."""
    tasa = tasa_igv()
    ok = [x for x in igv if 'error' not in x]
    pagan = sorted([x for x in ok if x['igv_pagar'] > 0], key=lambda x: -x['igv_pagar'])
    con_saldo = sorted([x for x in ok if x['credito_libre'] > 0], key=lambda x: -x['credito_libre'])
    salida = []
    if not pagan:
        salida.append({'nivel': 'verde', 'titulo': 'Este mes ninguna empresa paga IGV',
                       'texto': 'No hace falta mover ventas entre empresas.'})
        return salida
    if not con_saldo:
        salida.append({'nivel': 'info', 'titulo': 'Las dos empresas pagan IGV',
                       'texto': 'Mover ventas entre ellas no ahorra IGV. Lo único que baja el IGV es comprar antes del '
                                'cierre lo que ya necesitas (SUNAT ▸ Plan de acción).'})
        return salida
    for p in pagan:
        for s in con_saldo:
            if s['id'] == p['id']:
                continue
            igv_mov = min(a_decimal(p['igv_pagar']), a_decimal(s['credito_libre']))
            base = redondear(igv_mov / tasa)
            salida.append({
                'nivel': 'amarillo',
                'titulo': f"Las próximas ventas de {p['codigo']} a clientes: factúralas desde {s['codigo']}",
                'texto': (f"{p['codigo']} paga S/ {p['igv_pagar']:,.2f} de IGV y {s['codigo']} tiene S/ {s['credito_libre']:,.2f} "
                          f"de saldo sin usar. Si {s['codigo']} factura hasta S/ {base:,.2f} (sin IGV) de esas ventas, "
                          f"{p['codigo']} paga hasta S/ {igv_mov:,.2f} menos y {s['codigo']} no paga más, porque lo cubre su saldo."),
                'vende': s['codigo'], 'base': _n(base), 'igv': _n(igv_mov)})
            salida.append({
                'nivel': 'info',
                'titulo': f"O que {s['codigo']} le venda a {p['codigo']} mercadería que {p['codigo']} necesita",
                'texto': (f"Hasta S/ {base:,.2f} (sin IGV) a valor de mercado: {p['codigo']} paga S/ {igv_mov:,.2f} "
                          f"menos de IGV y {s['codigo']} no paga más (usa su saldo). Solo si la mercadería es real y "
                          f"con guía."),
                'vende': s['codigo'], 'compra': p['codigo'], 'base': _n(base), 'igv': _n(igv_mov)})
    return salida


# ============================================================
# STOCK DEL GRUPO Y PREPARACIÓN
# ============================================================
def stock_grupo(emps, q=''):
    from routes.inventario import asegurar_tablas_inventario, _consolidado
    asegurar_tablas_inventario()
    datos = _consolidado(q=q)
    por_emp = {e['id']: {'codigo': e['codigo'], 'unidades': 0.0, 'valor': 0.0, 'productos': 0} for e in emps}
    filas = []
    for p in datos:
        if p['total'] <= 0:
            continue
        fila = {'codigo': p['codigo'], 'descripcion': p['descripcion'], 'unidad': p['unidad'], 'total': round(p['total'], 2),
                'valor': p['valor'], 'empresas': {}}
        for eid, cant in p['por_empresa'].items():
            if eid in por_emp:
                fila['empresas'][por_emp[eid]['codigo']] = round(cant, 2)
                por_emp[eid]['unidades'] += cant
                por_emp[eid]['productos'] += 1 if cant > 0 else 0
        for celda_k, c in p['celdas'].items():
            eid = celda_k.rsplit('-', 1)[0]
            if eid in por_emp:
                por_emp[eid]['valor'] += c['valor']
        filas.append(fila)
    filas.sort(key=lambda x: -x['valor'])
    return {'productos': filas[:300], 'total_productos': len(filas),
            'por_empresa': [{**v, 'unidades': round(v['unidades'], 2), 'valor': round(v['valor'], 2)} for v in por_emp.values()],
            'valor_grupo': round(sum(v['valor'] for v in por_emp.values()), 2)}


def preparacion(emps):
    """Lo que hace falta para que las ventas entre empresas se registren bien (una línea por pantalla a revisar)."""
    def falta(tabla, col):
        return [f"{e['codigo']} (RUC {e['ruc']})" for e in emps
                if not db_query(f"SELECT 1 FROM {tabla} WHERE regexp_replace(COALESCE({col}, ''), '\\D', '', 'g') = %s LIMIT 1",
                                (_rucs(e['ruc']),))]
    avisos = []
    cli, prov = falta('clientes', 'numero_documento'), falta('proveedores', 'ruc')
    if cli:
        avisos.append('Maestros ▸ Clientes: crea a ' + ' y '.join(cli) + ' para poder facturarle desde la otra empresa.')
    if prov:
        avisos.append('Maestros ▸ Proveedores: crea a ' + ' y '.join(prov) + ' para registrar sus facturas en Compras.')
    try:
        sin_factura = db_query("""SELECT COUNT(DISTINCT grupo) AS n FROM inv_movimientos
                                  WHERE motivo = 'INTERCOMPANY_SALIDA' AND estado = 'Registrado'
                                    AND COALESCE(documento_numero, '') = ''""")[0]['n']
    except Exception:
        sin_factura = 0
    if sin_factura:
        avisos.append(f"Inventario ▸ Intercompany: {sin_factura} venta(s) entre empresas sin N° de factura.")
    return avisos


# ============================================================
# RUTAS
# ============================================================
def _err(ex, codigo=400):
    return jsonify({'success': False, 'error': str(ex)}), codigo


@intercompany_bp.route('/intercompany')
def pagina():
    return render_template('intercompany.html')


@intercompany_bp.route('/intercompany/api/resumen')
def api_resumen():
    try:
        emps = _grupo()
        anio, mes = _periodo(request.args.get('periodo'))
        desde, hasta = _rango(anio, mes)
        ventas = ventas_entre_empresas(emps, desde, hasta)
        sentidos, tend = tendencia(emps, anio, mes)
        igv = igv_del_mes(emps, anio, mes)
        deb = deudas(emps)
        totales = defaultdict(lambda: {'base': CERO, 'igv': CERO, 'total': CERO, 'n': 0})
        for v in ventas:
            t = totales[f"{v['vende']}→{v['compra']}"]
            t['base'] += a_decimal(v['base'])
            t['igv'] += a_decimal(v['igv'])
            t['total'] += a_decimal(v['total'])
            t['n'] += 1
        return jsonify({'success': True, 'data': {
            'periodo': f'{anio:04d}-{mes:02d}', 'nombre_periodo': f'{MESES_CORTO[mes - 1]} {anio}',
            'empresas': [{'id': e['id'], 'codigo': e['codigo'], 'ruc': e['ruc']} for e in emps],
            'sentidos': sentidos,
            'totales': {k: {'base': _n(v['base']), 'igv': _n(v['igv']), 'total': _n(v['total']), 'n': v['n']}
                        for k, v in totales.items()},
            'ventas': ventas, 'sin_compra': sum(1 for v in ventas if not v['registrada_en_compras']),
            'tendencia': tend, 'igv': igv, 'sugerencias': sugerencias(igv),
            'deudas': deb, 'avisos': preparacion(emps)}})
    except ErrorIntercompany as ex:
        return _err(ex)


@intercompany_bp.route('/intercompany/api/stock')
def api_stock():
    try:
        return jsonify({'success': True, 'data': stock_grupo(_grupo(), (request.args.get('q') or '').strip())})
    except ErrorIntercompany as ex:
        return _err(ex)
