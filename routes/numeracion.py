# routes/numeracion.py
# ============================================================
# CONFIGURACIÓN ▸ CORRELATIVOS (pedido de Erika 21/10/2026 16:35)
# El administrador ve el último número emitido de cada documento y puede fijar
# desde qué número siguen los NUEVOS documentos (COT, PV, Guía, Factura/Boleta).
# Nunca se renumera un documento ya emitido y nunca se acepta un número igual o
# menor al último emitido (chocaría con los índices únicos de la migración 014).
# La OC se numera por día (OC-AAAAMMDD-NNNN) y solo se muestra.
# ============================================================
from datetime import datetime

from flask import Blueprint, render_template, request, jsonify, session
from psycopg2.extras import RealDictCursor

from database import db_query, db_tx
from routes.multiempresa import empresas
from utils import bloquear_numeracion

numeracion_bp = Blueprint('numeracion', __name__)

SQL_TABLA = """
    CREATE TABLE IF NOT EXISTS erp_numeracion (
        documento VARCHAR(20) NOT NULL,
        clave VARCHAR(120) NOT NULL DEFAULT '',
        siguiente BIGINT NOT NULL CHECK (siguiente > 0),
        actualizado_por VARCHAR(120),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (documento, clave)
    )
"""

NOMBRES = {'COT': 'Cotización', 'PC': 'Pedido de venta (PV)', 'GUIA': 'Guía de remisión',
           'COMPROBANTE': 'Factura / Boleta', 'OC': 'Orden de compra (Proveedor)'}

_NUM = "NULLIF(regexp_replace({c}::text, '\\D', '', 'g'), '')::bigint"


def _empresa_txt(eid):
    return '' if eid is None else str(eid)


def clave_pc(codigo_empresa):
    return (codigo_empresa or '').upper()


def clave_guia(empresa_id, serie):
    return f"{_empresa_txt(empresa_id)}|{serie or ''}"


def clave_comprobante(tipo, empresa_id, serie):
    return f"{(tipo or '').upper()}|{_empresa_txt(empresa_id)}|{serie or ''}"


def piso(cur, documento, clave=''):
    """Número desde el que debe seguir la numeración nueva (0 si nadie lo fijó)."""
    cur.execute("SELECT to_regclass('public.erp_numeracion') IS NOT NULL AS hay")
    fila = cur.fetchone()
    if not (fila['hay'] if isinstance(fila, dict) else fila[0]):
        return 0
    cur.execute("SELECT siguiente FROM erp_numeracion WHERE documento = %s AND clave = %s", (documento, clave))
    fila = cur.fetchone()
    if not fila:
        return 0
    return int(fila['siguiente'] if isinstance(fila, dict) else fila[0])


def con_piso(cur, documento, clave, calculado):
    """El mayor entre el siguiente calculado (máximo emitido + 1) y el número fijado por el administrador."""
    return max(int(calculado), piso(cur, documento, clave))


# ============================================================
# LECTURA: último emitido por documento / empresa / serie
# ============================================================
def _cod_empresa(eid):
    if eid in (None, ''):
        return 'Sin empresa'
    e = next((x for x in empresas() if x['id'] == str(eid)), None)
    return e['codigo'] if e else str(eid)[:8]


def listar(cur):
    cur.execute(SQL_TABLA)
    cur.execute("SELECT documento, clave, siguiente, actualizado_por, updated_at FROM erp_numeracion")
    pisos = {(f['documento'], f['clave']): f for f in cur.fetchall()}
    filas = []

    def agregar(documento, clave, empresa, serie, formato, ultimo, ultimo_txt, editable=True, nota=''):
        p = pisos.pop((documento, clave), None)
        ultimo = int(ultimo or 0)
        siguiente = max(ultimo + 1, int(p['siguiente']) if p else 0)
        filas.append({
            'documento': documento, 'nombre': NOMBRES[documento], 'clave': clave, 'empresa': empresa,
            'serie': serie, 'formato': formato, 'ultimo': ultimo, 'ultimo_txt': ultimo_txt or '—',
            'siguiente': siguiente, 'siguiente_txt': formato.replace('{n}', str(siguiente).zfill(
                6 if documento in ('COT', 'PC') else 8)),
            'fijado': bool(p and int(p['siguiente']) > ultimo + 1),
            'actualizado_por': p['actualizado_por'] if p else None,
            'actualizado': p['updated_at'].strftime('%d/%m/%Y %H:%M') if p and p.get('updated_at') else None,
            'editable': editable, 'nota': nota})

    cur.execute(f"""SELECT COALESCE(MAX({_NUM.format(c='correlativo')}), 0) AS ultimo,
                           (SELECT numero_cotizacion FROM cotizaciones
                             ORDER BY {_NUM.format(c='correlativo')} DESC NULLS LAST LIMIT 1) AS txt
                    FROM cotizaciones""")
    f = cur.fetchone()
    agregar('COT', '', 'Todas', 'COT', 'COT-{n}', f['ultimo'], f['txt'],
            nota='Una sola numeración para KCF y AGD.')

    codigos = [e['codigo'].upper() for e in empresas()]
    cur.execute(f"""SELECT substring(numero FROM '^P[CV]-([A-Za-z0-9]+)-[0-9]+$') AS cod,
                           MAX({_NUM.format(c="substring(numero FROM '-([0-9]+)$')")}) AS ultimo
                    FROM pedido_compra_pc WHERE numero ~ '^P[CV]-[A-Za-z0-9]+-[0-9]+$' GROUP BY 1""")
    ult_pc = {(r['cod'] or '').upper(): r['ultimo'] for r in cur.fetchall()}
    for cod in sorted(set(codigos) | set(ult_pc)):
        u = ult_pc.get(cod) or 0
        agregar('PC', clave_pc(cod), cod, f'PV-{cod}', f'PV-{cod}-{{n}}', u,
                f"PV-{cod}-{str(u).zfill(6)}" if u else None, nota='Número interno por empresa (PV = Pedido de venta).')

    cur.execute(f"""SELECT DISTINCT ON (empresa_id, serie) empresa_id, serie, {_NUM.format(c='numero')} AS ultimo,
                           numero::text AS txt
                    FROM guias_remision WHERE serie IS NOT NULL
                    ORDER BY empresa_id, serie, {_NUM.format(c='numero')} DESC NULLS LAST""")
    for r in cur.fetchall():
        agregar('GUIA', clave_guia(r['empresa_id'], r['serie']), _cod_empresa(r['empresa_id']), r['serie'],
                f"{r['serie']}-{{n}}", r['ultimo'], f"{r['serie']}-{r['txt']}",
                nota='Se aplica cuando la guía se guarda con el N° vacío.')

    cur.execute(f"""SELECT DISTINCT ON (UPPER(tipo_comprobante), empresa_id, serie) UPPER(tipo_comprobante) AS tipo,
                           empresa_id, serie, {_NUM.format(c='numero')} AS ultimo
                    FROM comprobantes WHERE serie IS NOT NULL
                    ORDER BY UPPER(tipo_comprobante), empresa_id, serie, {_NUM.format(c='numero')} DESC NULLS LAST""")
    for r in cur.fetchall():
        agregar('COMPROBANTE', clave_comprobante(r['tipo'], r['empresa_id'], r['serie']),
                _cod_empresa(r['empresa_id']), f"{r['tipo'].capitalize()} {r['serie']}",
                f"{r['serie']}-{{n}}", r['ultimo'], f"{r['serie']}-{str(r['ultimo'] or 0).zfill(8)}")

    # Series fijadas a mano que aún no tienen documentos (por ejemplo una serie nueva)
    for (documento, clave) in list(pisos):
        if documento not in NOMBRES:
            continue
        partes = clave.split('|')
        serie = partes[-1] if documento in ('GUIA', 'COMPROBANTE') else clave
        empresa = _cod_empresa(partes[-2] or None) if len(partes) >= 2 else 'Todas'
        agregar(documento, clave, empresa, serie, f"{serie}-{{n}}", 0, None)

    cur.execute("""SELECT numero_orden FROM ordenes_compra WHERE numero_orden ~ '^OC-[0-9]{8}-[0-9]+$'
                   ORDER BY COALESCE(fecha_creacion, created_at) DESC NULLS LAST, id DESC LIMIT 1""")
    f = cur.fetchone()
    hoy = datetime.now().strftime('%Y%m%d')
    filas.append({'documento': 'OC', 'nombre': NOMBRES['OC'], 'clave': '', 'empresa': 'Todas', 'serie': 'OC',
                  'formato': f'OC-{hoy}-NNNN', 'ultimo': 0, 'ultimo_txt': f['numero_orden'] if f else '—',
                  'siguiente': None, 'siguiente_txt': f'OC-{hoy}-0001 en adelante', 'fijado': False,
                  'actualizado_por': None, 'actualizado': None, 'editable': False,
                  'nota': 'Se numera por día (fecha + correlativo). No se edita.'})
    return filas


@numeracion_bp.route('/correlativos')
def correlativos_page():
    return render_template('correlativos.html', active_tab='correlativos')


@numeracion_bp.route('/correlativos/api/lista')
def api_lista():
    try:
        with db_tx() as conn:
            filas = listar(conn.cursor(cursor_factory=RealDictCursor))
        return jsonify({'success': True, 'data': filas})
    except Exception as e:
        print(f"❌ Error listando correlativos: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@numeracion_bp.route('/correlativos/api/fijar', methods=['POST'])
def api_fijar():
    from routes.auditoria import registrar_auditoria
    data = request.get_json(silent=True) or {}
    documento = str(data.get('documento') or '').upper()
    clave = str(data.get('clave') or '')
    if documento not in ('COT', 'PC', 'GUIA', 'COMPROBANTE'):
        return jsonify({'success': False, 'error': 'Ese documento no se puede editar aquí.'}), 400
    try:
        siguiente = int(str(data.get('siguiente') if data.get('siguiente') is not None else '').strip())
    except ValueError:
        return jsonify({'success': False, 'error': 'Escribe un número entero (por ejemplo 1500).'}), 400
    usuario = session.get('nombre') or session.get('usuario') or 'admin'
    with db_tx() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(SQL_TABLA)
        bloquear_numeracion(cur, 'erp_numeracion')
        fila = next((f for f in listar(cur) if f['documento'] == documento and f['clave'] == clave), None)
        if not fila:
            return jsonify({'success': False, 'error': 'No se encontró esa numeración.'}), 404
        if siguiente <= fila['ultimo']:
            return jsonify({'success': False, 'error':
                            f"El número debe ser mayor que el último emitido ({fila['ultimo_txt']}). "
                            f"Los documentos ya emitidos no se renumeran."}), 400
        # Doble confirmación (22/10/2026): la pantalla pide escribir el número otra vez y el servidor lo exige
        if str(data.get('confirmacion') or '').strip() != str(siguiente):
            return jsonify({'success': False, 'codigo': 'falta_confirmar',
                            'error': 'Para confirmar, escribe otra vez el mismo número. No se cambió nada.'}), 400
        antes = fila['siguiente']
        cur.execute("""INSERT INTO erp_numeracion (documento, clave, siguiente, actualizado_por, updated_at)
                       VALUES (%s, %s, %s, %s, NOW())
                       ON CONFLICT (documento, clave) DO UPDATE
                       SET siguiente = EXCLUDED.siguiente, actualizado_por = EXCLUDED.actualizado_por,
                           updated_at = NOW()""", (documento, clave, siguiente, usuario))
        registrar_auditoria('editar', 'Correlativos', tabla='erp_numeracion', registro_id=f"{documento}:{clave}",
                            antes={'siguiente': antes}, despues={'siguiente': siguiente},
                            detalle=f"{fila['nombre']} {fila['empresa']} {fila['serie']}: siguiente {antes} → {siguiente}",
                            cur=cur)
    return jsonify({'success': True, 'message': f"Listo. El próximo documento {fila['serie']} saldrá con el N° {siguiente}."})
