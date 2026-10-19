# routes/papelera.py - Módulo 10 "Papelera / Auditoría" (pedido de Erika 16/10/2026: "TRAZABILIDAD PARA TODO")
#
# Papelera: todo lo anulado o eliminado de cada módulo en una sola lista (cotizaciones, PC, despachos, guías,
#   facturas, notas de crédito, OC, solicitudes, facturas de proveedor, cobros/pagos, traslados, maestros
#   desactivados y registros borrados que solo quedan en la auditoría).
#   - Restaurar: solo administradores y solo cuando no rompe nada. Guías, facturas y notas de crédito
#     anuladas NO se restauran (son documentos SUNAT): solo se ven.
#   - Borrar definitivamente: solo administradores, con doble confirmación; antes de borrar se guarda
#     todo el registro (y sus líneas) en la auditoría.
# Auditoría: historial de cambios (quién, cuándo, qué, antes/después) con filtros y exportación.
import json
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, render_template, request, session
from psycopg2.extras import RealDictCursor

from database import db_query, db_tx
from utils import es_admin, id_empresa
from routes.auditoria import (registrar_auditoria, marcar_usuario, asegurar_auditoria, TABLAS_AUDITADAS)
from routes.herramientas import columnas, existe_tabla, fecha_txt, respuesta_tabla, _plano

papelera_bp = Blueprint('papelera', __name__)
MODULO = 'Papelera'


@papelera_bp.before_app_request
def _preparar_auditoria():
    """Al primer uso: columnas nuevas de erp_auditoria y disparadores (nunca bloquea el ERP)."""
    if 'usuario_id' in session and request.endpoint not in (None, 'static'):
        try:
            asegurar_auditoria()
        except Exception as e:
            print(f'⚠️ No se pudo preparar la auditoría: {e}')


@papelera_bp.route('/papelera')
def papelera():
    return render_template('papelera.html', es_admin=es_admin(), modulos=[f['modulo'] for f in FUENTES] +
                           ['Registros borrados'])


def _err(msg, codigo=400):
    return jsonify({'success': False, 'error': msg}), codigo


# ============================================================
# FUENTES DE LA PAPELERA
# ============================================================
# Cada fuente: tabla, condición de "anulado/eliminado" y cómo leer número, cliente/proveedor, monto, etc.
# Las expresiones con 'requiere' solo se usan si existen esas columnas/tablas (Supabase y bases antiguas).
NO_FISCAL = 'Documento SUNAT: una vez anulado no se puede reactivar (se emite uno nuevo). Solo se ve.'
FUENTES = [
    {'id': 'cot', 'modulo': 'Cotizaciones', 'tabla': 'cotizaciones',
     'numero': ['numero_cotizacion'], 'tercero': [('(SELECT x.razon_social FROM clientes x WHERE x.id = t.cliente_id)', ['cliente_id'])],
     'monto': ['total'], 'estado': 'estado', 'cond': "t.estado IN ('Anulada', 'Eliminada')",
     'motivo': [("(SELECT ce.motivo_eliminacion FROM cotizaciones_eliminadas ce WHERE ce.cotizacion_id_original = t.id "
                 "ORDER BY ce.id DESC LIMIT 1)", ['@cotizaciones_eliminadas'])],
     'usuario': [("(SELECT COALESCE(NULLIF(u.nombres_apellidos, ''), u.nombre_completo) FROM cotizaciones_eliminadas ce "
                  "JOIN usuarios u ON u.id = ce.eliminado_por WHERE ce.cotizacion_id_original = t.id ORDER BY ce.id DESC LIMIT 1)",
                  ['@cotizaciones_eliminadas'])],
     'fecha': [("(SELECT ce.eliminado_en FROM cotizaciones_eliminadas ce WHERE ce.cotizacion_id_original = t.id "
                "ORDER BY ce.id DESC LIMIT 1)", ['@cotizaciones_eliminadas']), 'updated_at', 'fecha_creacion'],
     'restaurar_a': 'Borrador', 'borrable': True},
    {'id': 'pc', 'modulo': 'Pedidos (PC)', 'tabla': 'pedido_compra_pc', 'numero': ['numero'], 'tercero': ['cliente'],
     'monto': ['monto'], 'estado': 'estado', 'cond': "UPPER(COALESCE(t.estado, '')) LIKE 'ANULAD%%'",
     'fecha': ['updated_at', 'fecha'], 'restaurar_a': 'Pendiente', 'borrable': True},
    {'id': 'desp', 'modulo': 'Despachos', 'tabla': 'despachos', 'numero': ['numero'], 'tercero': ['cliente'],
     'estado': 'estado', 'cond': "UPPER(COALESCE(t.estado, '')) LIKE 'ANULAD%%'", 'fecha': ['updated_at', 'fecha'],
     'restaurar_a': 'Pendiente despacho', 'borrable': True},
    {'id': 'guia', 'modulo': 'Guías de remisión', 'tabla': 'guias_remision',
     'numero': [("t.serie || '-' || t.numero", ['serie', 'numero'])], 'tercero': ['destinatario_nombre'],
     'estado': 'estado_sunat', 'cond': "UPPER(COALESCE(t.estado_sunat, '')) LIKE 'ANULAD%%'",
     'fecha': ['updated_at', 'fecha_emision'], 'no_restaurar': NO_FISCAL},
    {'id': 'fact', 'modulo': 'Facturas y boletas', 'tabla': 'comprobantes',
     'numero': [("t.serie || '-' || LPAD(t.numero::text, 8, '0')", ['serie', 'numero'])], 'tercero': ['cliente_nombre'],
     'monto': ['total'], 'estado': 'estado_sunat', 'cond': "UPPER(COALESCE(t.estado_sunat, '')) LIKE 'ANULAD%%'",
     'fecha': ['updated_at', 'fecha_emision'], 'no_restaurar': NO_FISCAL},
    {'id': 'nc', 'modulo': 'Notas de crédito', 'tabla': 'notas_credito',
     'numero': [("t.serie || '-' || t.numero", ['serie', 'numero'])], 'tercero': ['cliente_nombre'], 'monto': ['monto'],
     'estado': 'estado', 'cond': "UPPER(COALESCE(t.estado, '')) LIKE 'ANULAD%%'", 'motivo': ['motivo'],
     'fecha': ['updated_at', 'fecha_emision'], 'no_restaurar': NO_FISCAL},
    {'id': 'dev', 'modulo': 'Devoluciones', 'tabla': 'devoluciones', 'numero': ['numero'], 'tercero': ['cliente'],
     'monto': ['monto'], 'estado': 'estado', 'cond': "UPPER(COALESCE(t.estado, '')) LIKE 'ANULAD%%'", 'motivo': ['motivo'],
     'fecha': ['updated_at', 'fecha'], 'no_restaurar': 'Una devolución anulada se vuelve a registrar en Ventas.'},
    {'id': 'oc', 'modulo': 'Órdenes de compra', 'tabla': 'ordenes_compra', 'numero': ['numero_orden'],
     'tercero': [('(SELECT x.razon_social FROM proveedores x WHERE x.id = t.proveedor_id)', ['proveedor_id'])],
     'monto': ['total'], 'estado': 'estado', 'cond': "UPPER(COALESCE(t.estado, '')) LIKE 'ANULAD%%'",
     'motivo': ['motivo_anulacion'], 'usuario': ['anulado_por'], 'fecha': ['anulado_en', 'updated_at', 'fecha_creacion'],
     'restaurar_a': 'Borrador', 'borrable': True},
    {'id': 'sol', 'modulo': 'Solicitudes de compra', 'tabla': 'solicitudes_compra', 'numero': ['numero_solicitud'],
     'tercero': ['solicitante'], 'estado': 'estado', 'cond': "UPPER(COALESCE(t.estado, '')) LIKE 'ANULAD%%'",
     'fecha': ['updated_at', 'fecha'], 'restaurar_a': 'Borrador', 'borrable': True},
    {'id': 'fprov', 'modulo': 'Facturas de proveedor', 'tabla': 'comprobantes_proveedor', 'numero': ['numero'],
     'tercero': ['proveedor_nombre'], 'monto': ['monto'], 'estado': 'estado',
     'cond': "UPPER(COALESCE(t.estado, '')) LIKE 'ANULAD%%'", 'fecha': ['updated_at', 'fecha'],
     'no_restaurar': 'La factura del proveedor anulada se vuelve a registrar en Compras (evita pagarla dos veces).'},
    {'id': 'pago', 'modulo': 'Cobros y pagos', 'tabla': 'finanzas_pagos',
     'numero': [("t.tipo || ' ' || COALESCE(t.documento_numero, '')", ['tipo', 'documento_numero'])],
     'tercero': ['tercero_nombre'], 'monto': ['monto'], 'estado': 'estado', 'cond': "t.estado = 'Anulado'",
     'motivo': ['motivo_anulacion'],
     'usuario': [('(SELECT COALESCE(NULLIF(u.nombres_apellidos, \'\'), u.nombre_completo) FROM usuarios u WHERE u.id = t.anulado_por)',
                  ['anulado_por'])],
     'fecha': ['anulado_en', 'updated_at', 'fecha'],
     'no_restaurar': 'Un cobro o pago anulado se vuelve a registrar en Finanzas (evita contar la plata dos veces).'},
    {'id': 'tras', 'modulo': 'Traslados de inventario', 'tabla': 'inv_traslados', 'numero': ['numero'], 'estado': 'estado',
     'cond': "UPPER(COALESCE(t.estado, '')) LIKE 'ANULAD%%'", 'motivo': ['observaciones_recepcion'],
     'fecha': ['updated_at', 'fecha'], 'no_restaurar': 'Al anular, la mercadería volvió a su sede: se registra un traslado nuevo.'},
    {'id': 'mov', 'modulo': 'Movimientos de inventario', 'tabla': 'inv_movimientos',
     'numero': [("COALESCE(t.numero, 'MOV-' || t.id)", ['numero'])], 'tercero': ['tercero'], 'monto': ['costo_total'],
     'estado': 'estado', 'cond': "UPPER(COALESCE(t.estado, '')) LIKE 'ANULAD%%'", 'motivo': ['observaciones'],
     'usuario': ['usuario_nombre'], 'fecha': ['fecha'],
     'no_restaurar': 'El kardex no se modifica: se registra un movimiento nuevo.'},
    {'id': 'cli', 'modulo': 'Clientes desactivados', 'tabla': 'clientes', 'numero': ['numero_documento'],
     'tercero': ['razon_social'], 'cond': 't.activo = false', 'fecha': ['updated_at', 'fecha_creacion'],
     'maestro': True},
    {'id': 'prov', 'modulo': 'Proveedores desactivados', 'tabla': 'proveedores', 'numero': ['ruc'],
     'tercero': ['razon_social'], 'cond': 't.activo = false', 'fecha': ['fecha_creacion'], 'maestro': True},
    {'id': 'prod', 'modulo': 'Productos desactivados', 'tabla': 'productos', 'numero': ['codigo'],
     'tercero': ['descripcion'], 'cond': 't.activo = false', 'fecha': ['updated_at', 'fecha_creacion'], 'maestro': True},
]
FUENTE = {f['id']: f for f in FUENTES}
# Registros borrados de verdad (solo quedan en la auditoría) que se pueden volver a crear tal cual
RESTAURABLES_DESDE_AUDITORIA = {'clientes': 'numero_documento', 'proveedores': 'ruc', 'productos': 'codigo'}
CLAVE_NUMERO = ('numero_cotizacion', 'numero_orden', 'numero_solicitud', 'numero', 'codigo', 'numero_documento', 'ruc',
                'usuario_sistema')
MAX_POR_FUENTE = 500


def _expr(cands, cols, defecto='NULL'):
    """Primera expresión cuyas columnas existen ('@tabla' = requiere esa tabla)."""
    for c in cands or []:
        if isinstance(c, tuple):
            expr, req = c
            if all((existe_tabla(r[1:]) if r.startswith('@') else r in cols) for r in req):
                return expr
        elif c in cols:
            return f't.{c}'
    return defecto


def _expr_todas(cands, cols, tipo):
    """COALESCE de todas las expresiones disponibles (la primera con dato gana)."""
    partes = [e for e in (_expr([c], cols, None) for c in cands or []) if e]
    if not partes:
        return 'NULL'
    return partes[0] + f'::{tipo}' if len(partes) == 1 else 'COALESCE(' + ', '.join(f'{p}::{tipo}' for p in partes) + ')'


def _sql_fuente(f, cols):
    estado = f"t.{f['estado']}" if f.get('estado') in cols else ("'Desactivado'" if f.get('maestro') else 'NULL')
    emp = 't.empresa_id::text' if 'empresa_id' in cols else 'NULL'
    return f"""SELECT t.id, {_expr(f['numero'], cols, "t.id::text")}::text AS numero, {_expr(f.get('tercero'), cols)}::text AS tercero,
                      {_expr(f.get('monto'), cols)}::numeric AS monto, {estado}::text AS estado,
                      {_expr_todas(f.get('fecha'), cols, 'timestamp')} AS fecha, {emp} AS empresa_id,
                      {_expr_todas(f.get('motivo'), cols, 'text')} AS motivo, {_expr_todas(f.get('usuario'), cols, 'text')} AS usuario
               FROM {f['tabla']} t WHERE {f['cond']}"""


def _empresas():
    try:
        return {str(e['id']): e['codigo'] for e in db_query("SELECT id, codigo FROM erp_empresas")}
    except Exception:
        return {}


def _empresa_pedida():
    """Empresa para filtrar: la de la URL (código o 'TODAS') o la elegida arriba."""
    pedida = (request.args.get('empresa') or '').strip().upper()
    if pedida == 'TODAS':
        return None
    if pedida:
        e = next((i for i, c in _empresas().items() if (c or '').upper() == pedida), None)
        return e or id_empresa(pedida)
    from routes.multiempresa import empresa_filtro
    return empresa_filtro()


def _fecha_param(nombre):
    v = (request.args.get(nombre) or '').strip()
    try:
        return datetime.strptime(v, '%Y-%m-%d').date() if v else None
    except ValueError:
        return None


def _quien_anulo(items):
    """Usuario y fecha desde la auditoría cuando el propio documento no lo guarda."""
    if not items:
        return
    pares = {(i['tabla'], str(i['id'])) for i in items}
    tablas = list({p[0] for p in pares})
    try:
        filas = db_query("""SELECT DISTINCT ON (tabla, registro_id::text) tabla, registro_id::text AS rid, usuario_nombre, created_at
                            FROM erp_auditoria WHERE tabla = ANY(%s) AND accion IN ('anular', 'eliminar', 'desactivar')
                            ORDER BY tabla, registro_id::text, created_at DESC""", (tablas,))
    except Exception:
        return
    info = {(f['tabla'], f['rid']): f for f in filas}
    for i in items:
        a = info.get((i['tabla'], str(i['id'])))
        if a:
            i['usuario'] = i.get('usuario') or a['usuario_nombre']
            if a['created_at']:  # la fecha real de la anulación (updated_at puede cambiar después)
                i['_fecha'] = a['created_at']


def items_papelera(modulo=None):
    salida = []
    emp_cod = _empresas()
    for f in FUENTES:
        if modulo and modulo != f['modulo']:
            continue
        cols = columnas(f['tabla'])
        if not cols:
            continue
        try:
            filas = db_query(_sql_fuente(f, cols) + f" ORDER BY t.id DESC LIMIT {MAX_POR_FUENTE}")
        except Exception as e:
            print(f"⚠️ Papelera ({f['tabla']}): {e}")
            continue
        for r in filas:
            item = {'clave': f"{f['id']}:{r['id']}", 'fuente': f['id'], 'modulo': f['modulo'], 'tabla': f['tabla'],
                    'id': r['id'], 'numero': r['numero'], 'tercero': r['tercero'],
                    'monto': float(r['monto']) if r['monto'] is not None else None, 'estado': r['estado'],
                    '_fecha': r['fecha'], 'empresa_id': r['empresa_id'], 'empresa': emp_cod.get(r['empresa_id'] or ''),
                    'motivo': r['motivo'], 'usuario': r['usuario'],
                    'tipo': 'Desactivado' if f.get('maestro') else ('Eliminado' if r['estado'] == 'Eliminada' or
                                                                     (f['id'] == 'cot' and r['motivo']) else 'Anulado')}
            item['puede_restaurar'] = bool(f.get('restaurar_a') or f.get('maestro'))
            item['por_que_no'] = f.get('no_restaurar')
            item['puede_borrar'] = bool(f.get('borrable'))
            salida.append(item)
    if not modulo or modulo in ('Cotizaciones', 'Registros borrados'):
        salida += _respaldos_cotizaciones(emp_cod) if not modulo or modulo == 'Cotizaciones' else []
    if not modulo or modulo == 'Registros borrados':
        vistos = {(i['tabla'], str(i['id'])) for i in salida}
        salida += [i for i in _borrados_auditoria(emp_cod) if (i['tabla'], str(i['id'])) not in vistos]
    _quien_anulo([i for i in salida if i['fuente'] in FUENTE])
    return salida


def _respaldos_cotizaciones(emp_cod):
    """Cotizaciones que se borraron de la tabla pero tienen respaldo en cotizaciones_eliminadas."""
    if not existe_tabla('cotizaciones_eliminadas'):
        return []
    filas = db_query(f"""SELECT ce.id, ce.cotizacion_id_original, ce.numero_cotizacion, ce.cliente_razon_social, ce.total,
                                ce.estado_anterior, ce.eliminado_en, ce.motivo_eliminacion,
                                ce.datos_completos_json->>'empresa_id' AS empresa_id,
                                (SELECT COALESCE(NULLIF(u.nombres_apellidos, ''), u.nombre_completo) FROM usuarios u
                                 WHERE u.id = ce.eliminado_por) AS usuario
                         FROM cotizaciones_eliminadas ce
                         WHERE NOT EXISTS (SELECT 1 FROM cotizaciones c WHERE c.id = ce.cotizacion_id_original)
                         ORDER BY ce.id DESC LIMIT {MAX_POR_FUENTE}""")
    return [{'clave': f"cotresp:{r['id']}", 'fuente': 'cotresp', 'modulo': 'Cotizaciones', 'tabla': 'cotizaciones',
             'id': r['cotizacion_id_original'], 'numero': r['numero_cotizacion'], 'tercero': r['cliente_razon_social'],
             'monto': float(r['total']) if r['total'] is not None else None,
             'estado': f"Borrada (estaba {r['estado_anterior'] or '—'})", '_fecha': r['eliminado_en'],
             'empresa_id': r['empresa_id'], 'empresa': emp_cod.get(r['empresa_id'] or ''), 'motivo': r['motivo_eliminacion'],
             'usuario': r['usuario'], 'tipo': 'Borrado', 'puede_restaurar': False, 'puede_borrar': False,
             'por_que_no': 'Ya no está en la tabla de cotizaciones; queda su respaldo completo (ver detalle).'} for r in filas]


def _borrados_auditoria(emp_cod):
    """Registros borrados de la base (DELETE) que solo quedan en la auditoría."""
    salida = []
    for tabla, (modulo, _) in TABLAS_AUDITADAS.items():
        if not existe_tabla(tabla):
            continue
        try:
            filas = db_query(f"""
                SELECT a.id::text AS aid, a.registro_id::text AS rid, a.data_anterior, a.created_at, a.usuario_nombre,
                       a.empresa_id::text AS empresa_id, a.detalle
                FROM erp_auditoria a
                WHERE a.tabla = %s AND a.accion = 'eliminar' AND a.data_anterior IS NOT NULL
                  AND COALESCE(a.detalle, '') LIKE 'Registro borrado%%'
                  AND NOT EXISTS (SELECT 1 FROM {tabla} x WHERE x.id::text = a.registro_id::text)
                  AND NOT EXISTS (SELECT 1 FROM erp_auditoria b WHERE b.tabla = a.tabla AND b.registro_id::text = a.registro_id::text
                                  AND b.accion IN ('borrar_definitivo', 'restaurar') AND b.created_at >= a.created_at)
                ORDER BY a.created_at DESC LIMIT {MAX_POR_FUENTE}""", (tabla,))
        except Exception as e:
            print(f'⚠️ Papelera borrados ({tabla}): {e}')
            continue
        for r in filas:
            d = r['data_anterior'] or {}
            numero = next((str(d[k]) for k in CLAVE_NUMERO if d.get(k)), r['rid'])
            if tabla in ('comprobantes', 'guias_remision', 'notas_credito') and d.get('serie'):
                numero = f"{d['serie']}-{d.get('numero')}"
            salida.append({
                'clave': f"borrado:{r['aid']}", 'fuente': 'borrado', 'modulo': 'Registros borrados', 'tabla': tabla,
                'id': r['rid'], 'numero': numero,
                'tercero': d.get('razon_social') or d.get('cliente') or d.get('cliente_nombre') or d.get('descripcion')
                or d.get('proveedor_nombre') or d.get('nombres_apellidos'),
                'monto': d.get('total') if isinstance(d.get('total'), (int, float)) else d.get('monto'),
                'estado': f'Borrado de {modulo}', '_fecha': r['created_at'], 'empresa_id': r['empresa_id'] or d.get('empresa_id'),
                'empresa': emp_cod.get(r['empresa_id'] or str(d.get('empresa_id') or '')), 'motivo': None,
                'usuario': r['usuario_nombre'], 'tipo': 'Borrado', 'puede_restaurar': tabla in RESTAURABLES_DESDE_AUDITORIA,
                'por_que_no': None if tabla in RESTAURABLES_DESDE_AUDITORIA else
                'Solo queda en la auditoría (ver detalle). Si hace falta, se vuelve a registrar en su módulo.',
                'puede_borrar': False})
    return salida


def _fecha_de(i):
    v = i.get('_fecha')
    if isinstance(v, datetime):
        return v.replace(tzinfo=None) if v.tzinfo is None else v.astimezone().replace(tzinfo=None)
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    return None


@papelera_bp.route('/papelera/api/lista')
def api_lista():
    modulo = (request.args.get('modulo') or '').strip() or None
    desde, hasta = _fecha_param('desde'), _fecha_param('hasta')
    usuario = (request.args.get('usuario') or '').strip().lower()
    q = (request.args.get('q') or '').strip().lower()
    eid = _empresa_pedida()
    items = items_papelera(modulo)
    salida = []
    for i in items:
        f = _fecha_de(i)
        if eid is not None and i.get('empresa_id') and str(i['empresa_id']) != str(eid):
            continue
        if desde and (not f or f.date() < desde):
            continue
        if hasta and (not f or f.date() > hasta):
            continue
        if usuario and usuario not in (i.get('usuario') or '').lower():
            continue
        if q and q not in ' '.join(str(i.get(k) or '') for k in ('numero', 'tercero', 'motivo', 'estado')).lower():
            continue
        i['fecha'] = f.strftime('%d/%m/%Y %H:%M') if f else ''
        i['_orden'] = f or datetime.min
        salida.append(i)
    salida.sort(key=lambda x: x['_orden'], reverse=True)
    for i in salida:
        i.pop('_orden', None)
        i.pop('_fecha', None)
        if not es_admin():
            i['puede_restaurar'] = i['puede_borrar'] = False
    resumen = {}
    for i in salida:
        resumen[i['modulo']] = resumen.get(i['modulo'], 0) + 1
    return jsonify({'success': True, 'data': salida, 'total': len(salida), 'resumen': resumen, 'es_admin': es_admin()})


def _buscar_item(clave):
    fuente, _, rid = (clave or '').partition(':')
    if fuente in FUENTE:
        f = FUENTE[fuente]
        cols = columnas(f['tabla'])
        if not cols or not rid.isdigit():
            return None, None
        filas = db_query(_sql_fuente(f, cols) + " AND t.id = %s", (int(rid),))
        return f, (filas[0] if filas else None)
    if fuente == 'borrado':
        filas = db_query("""SELECT id::text AS aid, tabla, registro_id::text AS rid, data_anterior FROM erp_auditoria
                            WHERE id::text = %s AND accion = 'eliminar'""", (rid,))
        return {'id': 'borrado'}, (filas[0] if filas else None)
    if fuente == 'cotresp' and rid.isdigit() and existe_tabla('cotizaciones_eliminadas'):
        filas = db_query("SELECT * FROM cotizaciones_eliminadas WHERE id = %s", (int(rid),))
        return {'id': 'cotresp'}, (filas[0] if filas else None)
    return None, None


@papelera_bp.route('/papelera/api/detalle')
def api_detalle():
    """Todo el registro (como está o como quedó en la auditoría) para verlo antes de decidir."""
    f, item = _buscar_item(request.args.get('clave'))
    if not item:
        return _err('No se encontró ese registro.', 404)
    if f['id'] == 'borrado':
        datos = item['data_anterior']
    elif f['id'] == 'cotresp':
        datos = {k: _plano(v) for k, v in item.items()}
    else:
        fila = db_query(f"SELECT * FROM {f['tabla']} WHERE id = %s", (item['id'],))
        datos = {k: _plano(v) for k, v in (fila[0] if fila else {}).items() if 'password' not in k}
    if f['id'] == 'borrado':
        tabla, rid = item['tabla'], item['rid']
    elif f['id'] == 'cotresp':
        tabla, rid = 'cotizaciones', item['cotizacion_id_original']
    else:
        tabla, rid = f['tabla'], item['id']
    historial = db_query("""SELECT created_at, accion, usuario_nombre, detalle FROM erp_auditoria
                            WHERE tabla = %s AND registro_id::text = %s ORDER BY created_at DESC LIMIT 50""",
                         (tabla, str(rid)))
    return jsonify({'success': True, 'datos': datos,
                    'historial': [{'fecha': fecha_txt(h['created_at']), 'accion': h['accion'], 'usuario': h['usuario_nombre'],
                                   'detalle': h['detalle']} for h in historial]})


# ============================================================
# RESTAURAR (solo administradores)
# ============================================================
@papelera_bp.route('/papelera/api/restaurar', methods=['POST'])
def api_restaurar():
    if not es_admin():
        return _err('Solo un administrador puede restaurar.', 403)
    d = request.get_json(silent=True) or {}
    f, item = _buscar_item(d.get('clave'))
    if not item:
        return _err('No se encontró ese registro en la papelera (quizás ya se restauró).', 404)
    if f['id'] == 'borrado':
        return _restaurar_borrado(item)
    if not (f.get('restaurar_a') or f.get('maestro')):
        return _err(f.get('no_restaurar') or 'Este registro no se puede restaurar.', 409)
    tabla = f['tabla']
    cols = columnas(tabla)
    with db_tx() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        marcar_usuario(cur, origen='Restaurado desde la Papelera')
        cur.execute(f"SELECT * FROM {tabla} t WHERE t.id = %s AND {f['cond']} FOR UPDATE", (item['id'],))
        antes = cur.fetchone()
        if not antes:
            return _err('Ese registro ya no está anulado.', 409)
        if f.get('maestro'):
            sets = ['activo = true']
            if 'estado' in cols:
                sets.append("estado = 'Activo'" if tabla != 'productos' else "estado = 'activo'")
            nuevo = 'Activo'
        else:
            sets = [f"{f['estado']} = %(nuevo)s"]
            if tabla == 'ordenes_compra':
                sets += [f"{c} = NULL" for c in ('anulado_por', 'anulado_en', 'motivo_anulacion') if c in cols]
            nuevo = f['restaurar_a']
        if 'updated_at' in cols:
            sets.append('updated_at = NOW()')
        cur.execute(f"UPDATE {tabla} SET {', '.join(sets)} WHERE id = %(id)s RETURNING *", {'nuevo': nuevo, 'id': item['id']})
        despues = cur.fetchone()
        if tabla == 'ordenes_compra' and existe_tabla('com_historial'):
            cur.execute("""INSERT INTO com_historial (orden_compra_id, usuario_id, usuario, accion, detalle)
                           VALUES (%s, %s, %s, 'Restaurada', 'Restaurada desde la Papelera como Borrador')""",
                        (item['id'], session.get('usuario_id'), session.get('nombre_completo')))
        registrar_auditoria('restaurar', MODULO, tabla=tabla, registro_id=item['id'], antes=dict(antes), despues=dict(despues),
                            detalle=f"Restauró {f['modulo']} {item['numero']} ({item['estado']} → {nuevo})", cur=cur)
    return jsonify({'success': True, 'message': f"{item['numero']} restaurado: ahora está en \"{nuevo}\"."})


def _restaurar_borrado(item):
    tabla = item['tabla']
    clave = RESTAURABLES_DESDE_AUDITORIA.get(tabla)
    if not clave:
        return _err('Este tipo de registro borrado no se puede volver a crear desde aquí.', 409)
    datos = item['data_anterior'] or {}
    with db_tx() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        marcar_usuario(cur, origen='Restaurado desde la Papelera')
        cur.execute(f"SELECT 1 FROM {tabla} WHERE id::text = %s", (item['rid'],))
        if cur.fetchone():
            return _err('Ya existe un registro con ese id: no se puede restaurar.', 409)
        if datos.get(clave):
            cur.execute(f"SELECT id FROM {tabla} WHERE UPPER(TRIM({clave}::text)) = UPPER(TRIM(%s))", (str(datos[clave]),))
            otro = cur.fetchone()
            if otro:
                return _err(f'Ya existe otro registro con {clave} {datos[clave]} (id {otro["id"]}): no se duplica.', 409)
        cur.execute(f"INSERT INTO {tabla} SELECT * FROM jsonb_populate_record(NULL::{tabla}, %s::jsonb) RETURNING *",
                    (json.dumps(datos),))
        despues = cur.fetchone()
        registrar_auditoria('restaurar', MODULO, tabla=tabla, registro_id=item['rid'], antes=None, despues=dict(despues),
                            detalle=f'Volvió a crear el registro borrado {tabla} {datos.get(clave) or item["rid"]}', cur=cur)
    return jsonify({'success': True, 'message': 'Registro restaurado tal como estaba antes de borrarse.'})


# ============================================================
# BORRAR DEFINITIVAMENTE (solo administradores, doble confirmación)
# ============================================================
HIJOS = {  # líneas que se borran junto con el documento (y se guardan en la auditoría)
    'cotizaciones': [('cotizacion_detalle', 'cotizacion_id')],
    'despachos': [('despacho_productos', 'despacho_id')],
    'ordenes_compra': [('ordenes_compra_items', 'orden_compra_id'), ('orden_compra_detalle', 'orden_id')],
}
# Documentos que dependen de este: si hay alguno, no se borra (se perdería el rastro)
DEPENDIENTES = {
    'cotizaciones': [("SELECT numero FROM pedido_compra_pc WHERE cotizacion_id = %s", 'pedido_compra_pc', 'PC'),
                     ("SELECT numero FROM despachos WHERE cotizacion_id = %s", 'despachos', 'despacho')],
    'pedido_compra_pc': [("SELECT numero FROM despachos WHERE pc_id = %s", 'despachos', 'despacho'),
                         ("SELECT numero_orden FROM ordenes_compra_items i JOIN ordenes_compra o ON o.id = i.orden_compra_id "
                          "WHERE i.pedido_id = %s", 'ordenes_compra_items', 'orden de compra')],
    'despachos': [("SELECT serie || '-' || numero FROM guias_remision g JOIN despachos d ON d.id = %s "
                   "WHERE g.documento_asociado = d.numero", 'guias_remision', 'guía')],
    'ordenes_compra': [("SELECT numero FROM com_recepciones WHERE orden_compra_id = %s", 'com_recepciones', 'recepción'),
                       ("SELECT numero_recepcion FROM recepciones_mercaderia WHERE orden_compra_id = %s", 'recepciones_mercaderia', 'recepción'),
                       ("SELECT numero FROM comprobantes_proveedor WHERE orden_compra_id = %s", 'comprobantes_proveedor', 'factura de proveedor'),
                       ("SELECT documento_numero FROM finanzas_pagos WHERE documento_tabla = 'ordenes_compra' AND documento_id = %s",
                        'finanzas_pagos', 'pago')],
}


@papelera_bp.route('/papelera/api/borrar', methods=['POST'])
def api_borrar_definitivo():
    if not es_admin():
        return _err('Solo un administrador puede borrar definitivamente.', 403)
    d = request.get_json(silent=True) or {}
    f, item = _buscar_item(d.get('clave'))
    if not item:
        return _err('No se encontró ese registro en la papelera.', 404)
    if f['id'] not in FUENTE or not f.get('borrable'):
        return _err(f.get('no_restaurar') or 'Este registro no se borra: se conserva para la trazabilidad.', 409)
    # Doble confirmación: escribir BORRAR y el número del documento
    if (d.get('confirmacion') or '').strip().upper() != 'BORRAR':
        return _err('Para borrar escribe la palabra BORRAR.')
    if (d.get('numero') or '').strip().upper() != (item['numero'] or '').strip().upper():
        return _err(f'Escribe el número exacto del documento ({item["numero"]}) para confirmar.')
    tabla = f['tabla']
    with db_tx() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        marcar_usuario(cur, origen='Borrado definitivo desde la Papelera')
        cur.execute(f"SELECT * FROM {tabla} t WHERE t.id = %s AND {f['cond']} FOR UPDATE", (item['id'],))
        fila = cur.fetchone()
        if not fila:
            return _err('Ese registro ya no está anulado: no se borra.', 409)
        for sql, req, nombre in DEPENDIENTES.get(tabla, []):
            if not existe_tabla(req):
                continue
            try:
                cur.execute("SAVEPOINT sp_dep")
                cur.execute(sql + " LIMIT 1", (item['id'],))
                dep = cur.fetchone()
                cur.execute("RELEASE SAVEPOINT sp_dep")
            except Exception:
                cur.execute("ROLLBACK TO SAVEPOINT sp_dep")
                dep = None
            if dep:
                return _err(f'No se puede borrar: tiene un {nombre} relacionado ({list(dep.values())[0]}). '
                            'Se deja en la papelera para no perder el rastro.', 409)
        hijos = {}
        for t_hijo, col in HIJOS.get(tabla, []):
            if existe_tabla(t_hijo):
                cur.execute(f"SELECT * FROM {t_hijo} WHERE {col} = %s ORDER BY id", (item['id'],))
                hijos[t_hijo] = [dict(h) for h in cur.fetchall()]
        # Primero la auditoría con TODO lo que se va a borrar
        ok = registrar_auditoria('borrar_definitivo', MODULO, tabla=tabla, registro_id=item['id'],
                                 antes={'registro': dict(fila), 'lineas': hijos}, cur=cur,
                                 detalle=f"Borró definitivamente {f['modulo']} {item['numero']} (estaba {item['estado']})")
        if not ok:
            return _err('No se pudo guardar la auditoría: no se borró nada.', 500)
        for t_hijo, col in HIJOS.get(tabla, []):
            if t_hijo in hijos:
                cur.execute(f"DELETE FROM {t_hijo} WHERE {col} = %s", (item['id'],))
        cur.execute(f"DELETE FROM {tabla} WHERE id = %s", (item['id'],))
    return jsonify({'success': True, 'message': f"{item['numero']} se borró definitivamente. Sus datos quedan en Auditoría."})


# ============================================================
# AUDITORÍA (solo administradores)
# ============================================================
ACCIONES = ['login', 'login_fallido', 'logout', 'crear', 'editar', 'anular', 'aprobar', 'rechazar', 'eliminar',
            'desactivar', 'activar', 'restaurar', 'borrar_definitivo', 'importar', 'exportar', 'herramienta']


def _filtros_auditoria():
    cond, params = ['1=1'], []
    a = request.args
    if a.get('usuario'):
        cond.append("(COALESCE(a.usuario_nombre, u.nombres_apellidos, '') ILIKE %s OR a.usuario_id::text = %s)")
        params += [f"%{a['usuario']}%", a['usuario']]
    if a.get('modulo'):
        cond.append("COALESCE(a.modulo, a.tabla) = %s")
        params.append(a['modulo'])
    if a.get('accion'):
        cond.append("a.accion = %s")
        params.append(a['accion'])
    if a.get('tabla'):
        cond.append("a.tabla = %s")
        params.append(a['tabla'])
    if a.get('registro'):
        cond.append("a.registro_id::text = %s")
        params.append(a['registro'])
    desde, hasta = _fecha_param('desde'), _fecha_param('hasta')
    if desde:
        cond.append("a.created_at >= %s")
        params.append(desde)
    if hasta:
        cond.append("a.created_at < %s")
        params.append(hasta + timedelta(days=1))
    if a.get('q'):
        cond.append("(COALESCE(a.detalle, '') ILIKE %s OR a.registro_id::text = %s OR COALESCE(a.data_nueva::text, a.data_anterior::text, '') ILIKE %s)")
        params += [f"%{a['q']}%", a['q'], f"%{a['q']}%"]
    eid = _empresa_pedida() if a.get('empresa') else None
    if eid is not None:
        cond.append("(a.empresa_id IS NULL OR a.empresa_id::text = %s)")
        params.append(str(eid))
    return ' AND '.join(cond), params


SQL_AUDITORIA = """
    SELECT a.id::text AS id, a.created_at, a.accion, a.tabla, a.registro_id::text AS registro_id,
           COALESCE(a.modulo, a.tabla) AS modulo, a.detalle, a.ip, a.empresa,
           COALESCE(a.usuario_nombre, u.nombres_apellidos, u.usuario_sistema) AS usuario, a.usuario_id,
           a.data_anterior, a.data_nueva
    FROM erp_auditoria a
    LEFT JOIN usuarios u ON u.auth_user_id IS NOT NULL AND a.auth_user_id IS NOT NULL
                         AND u.auth_user_id::text = a.auth_user_id::text
    WHERE {cond}
    ORDER BY a.created_at DESC
"""


def _documento(f):
    d = f.get('data_nueva') or f.get('data_anterior') or {}
    if not isinstance(d, dict):
        return ''
    if d.get('serie') and d.get('numero'):
        return f"{d['serie']}-{d['numero']}"
    return next((str(d[k]) for k in CLAVE_NUMERO if d.get(k)), '')


def cambios(antes, despues):
    """Lista de campos con su valor antes y después (solo los que cambiaron)."""
    antes, despues = antes or {}, despues or {}
    if not isinstance(antes, dict) or not isinstance(despues, dict):
        return []
    salida = []
    for k in sorted(set(antes) | set(despues)):
        if 'password' in k or k in ('updated_at',):
            continue
        a, d = antes.get(k), despues.get(k)
        if a != d and not (a in (None, '') and d in (None, '')):
            salida.append({'campo': k, 'antes': a, 'despues': d})
    return salida


def _solo_admin():
    if not es_admin():
        return _err('Solo un administrador puede ver la auditoría.', 403)
    return None


@papelera_bp.route('/papelera/api/auditoria')
def api_auditoria():
    no = _solo_admin()
    if no:
        return no
    asegurar_auditoria()
    cond, params = _filtros_auditoria()
    try:
        pagina = max(1, int(request.args.get('pagina', 1)))
    except ValueError:
        pagina = 1
    por_pagina = 100
    total = db_query(f"""SELECT COUNT(*) AS n FROM erp_auditoria a LEFT JOIN usuarios u ON u.auth_user_id IS NOT NULL
                         AND a.auth_user_id IS NOT NULL AND u.auth_user_id::text = a.auth_user_id::text WHERE {cond}""",
                     params)[0]['n']
    filas = db_query(SQL_AUDITORIA.format(cond=cond) + " LIMIT %s OFFSET %s", params + [por_pagina, (pagina - 1) * por_pagina])
    data = []
    for f in filas:
        data.append({'id': f['id'], 'fecha': fecha_txt(f['created_at']), 'accion': f['accion'], 'tabla': f['tabla'],
                     'registro_id': f['registro_id'], 'modulo': f['modulo'], 'detalle': f['detalle'], 'ip': f['ip'],
                     'empresa': f['empresa'], 'usuario': f['usuario'] or ('Sistema' if f['accion'] not in ('login_fallido',) else ''),
                     'documento': _documento(f), 'cambios': cambios(f['data_anterior'], f['data_nueva'])[:60],
                     'tiene_datos': bool(f['data_anterior'] or f['data_nueva'])})
    return jsonify({'success': True, 'data': data, 'total': total, 'pagina': pagina, 'paginas': max(1, -(-total // por_pagina))})


@papelera_bp.route('/papelera/api/auditoria/<aid>')
def api_auditoria_detalle(aid):
    no = _solo_admin()
    if no:
        return no
    filas = db_query(SQL_AUDITORIA.format(cond='a.id::text = %s'), (aid,))
    if not filas:
        return _err('No encontrado.', 404)
    f = filas[0]
    return jsonify({'success': True, 'data': {'fecha': fecha_txt(f['created_at']), 'accion': f['accion'], 'usuario': f['usuario'],
                                              'modulo': f['modulo'], 'tabla': f['tabla'], 'registro_id': f['registro_id'],
                                              'detalle': f['detalle'], 'antes': f['data_anterior'], 'despues': f['data_nueva'],
                                              'cambios': cambios(f['data_anterior'], f['data_nueva'])}})


@papelera_bp.route('/papelera/api/auditoria/opciones')
def api_auditoria_opciones():
    no = _solo_admin()
    if no:
        return no
    asegurar_auditoria()
    modulos = [r['m'] for r in db_query("SELECT DISTINCT COALESCE(modulo, tabla) AS m FROM erp_auditoria ORDER BY 1") if r['m']]
    usuarios = [r['u'] for r in db_query("""SELECT DISTINCT usuario_nombre AS u FROM erp_auditoria
                                            WHERE usuario_nombre IS NOT NULL ORDER BY 1""")]
    return jsonify({'success': True, 'modulos': modulos, 'usuarios': usuarios, 'acciones': ACCIONES})


@papelera_bp.route('/papelera/api/auditoria/exportar')
def api_auditoria_exportar():
    no = _solo_admin()
    if no:
        return no
    cond, params = _filtros_auditoria()
    filas = db_query(SQL_AUDITORIA.format(cond=cond) + " LIMIT 20000", params)
    formato = 'xlsx' if request.args.get('formato') == 'xlsx' else 'csv'
    cols = ['Fecha', 'Usuario', 'Acción', 'Módulo', 'Tabla', 'Registro', 'Documento', 'Detalle', 'Empresa', 'IP',
            'Campos cambiados', 'Antes', 'Después']
    datos = [{'Fecha': fecha_txt(f['created_at']), 'Usuario': f['usuario'], 'Acción': f['accion'], 'Módulo': f['modulo'],
              'Tabla': f['tabla'], 'Registro': f['registro_id'], 'Documento': _documento(f), 'Detalle': f['detalle'],
              'Empresa': f['empresa'], 'IP': f['ip'],
              'Campos cambiados': ', '.join(c['campo'] for c in cambios(f['data_anterior'], f['data_nueva'])),
              'Antes': json.dumps(f['data_anterior'], ensure_ascii=False, default=str) if f['data_anterior'] else '',
              'Después': json.dumps(f['data_nueva'], ensure_ascii=False, default=str) if f['data_nueva'] else ''}
             for f in filas]
    registrar_auditoria('exportar', MODULO, tabla='erp_auditoria', detalle=f'Exportó la auditoría ({len(datos)} filas, {formato.upper()})')
    return respuesta_tabla(f'auditoria_{datetime.now():%Y%m%d_%H%M}', cols, datos, formato, 'Auditoria')
