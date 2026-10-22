# routes/planilla.py - Planilla y RRHH simple (pedido de Erika, 21/10/2026 23:30)
#
# Qué hace (en simple):
#   1. Personal: quién trabaja en cada empresa, si está en planilla, es practicante o emite recibo por honorarios,
#      su sueldo o subvención (lo escribe Erika: el ERP nunca inventa sueldos), su pensión (ONP / AFP) y su banco.
#   2. Pagos del mes: cuánto se le paga a cada uno (bruto, descuentos, neto), el EsSalud de la empresa,
#      y en julio/diciembre la gratificación, en mayo/noviembre la CTS y cada 6 meses la media subvención
#      de los practicantes. Cada pago se marca con su N° de operación.
#   3. Vacaciones: días ganados, tomados y pendientes (rojo si se acumula más de un año).
#   4. CTS y gratificaciones: cuánto toca en el próximo depósito, según el régimen laboral de la empresa.
#   5. Se conecta solo con SUNAT ▸ Pagos del mes: la base de EsSalud, ONP, AFP, sueldos y renta de 4.ª
#      se envían al módulo SUNAT (sunat_periodos.planilla) cada vez que se abren los pagos del mes.
#
# Reglas:
#   - Cálculos de referencia según la ley peruana (D. Leg. 713, Ley 27735, D. Leg. 650, Ley 32353/REMYPE, Ley 28518).
#     Montos finos (renta de 5.ª, comisiones exactas de AFP) los confirma el contador.
#   - Acceso: solo administrador (Gerencia total) o quien tenga "Ver" en "Planilla". Datos sensibles.
#   - Todo queda con usuario y fecha y hora de Lima; desmarcar un pago pide motivo.
import calendar
import re
import threading
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal, ROUND_HALF_UP

from flask import Blueprint, render_template, request, jsonify, session
from psycopg2.extras import RealDictCursor, Json

from database import db_query, db_tx
from utils import a_decimal, redondear, es_admin, id_empresa
from routes.multiempresa import empresas as lista_empresas, empresa_actual, empresa_por_id

planilla_bp = Blueprint('planilla', __name__)


def _ahora():
    """Fecha y hora de Lima (el servidor de Render está en UTC)."""
    return datetime.now(ZoneInfo('America/Lima')).replace(tzinfo=None)

CERO = Decimal('0')
RMV_POR_DEFECTO = Decimal('1130')          # Remuneración mínima vital (D.S. 006-2024-TR). Se cambia en Configuración.
UIT_2026 = Decimal('5500')
TIPOS = ('Planilla', 'Practicante', 'Recibo por honorarios')
PENSIONES = ('ONP', 'AFP', 'Ninguno')
REGIMENES = {
    'GENERAL': {'nombre': 'Régimen general', 'vacaciones': 30, 'factor_beneficios': Decimal('1')},
    'PEQUENA': {'nombre': 'Pequeña empresa (REMYPE)', 'vacaciones': 15, 'factor_beneficios': Decimal('0.5')},
    'MICRO': {'nombre': 'Microempresa (REMYPE)', 'vacaciones': 15, 'factor_beneficios': Decimal('0')},
}
MESES = ('Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Setiembre', 'Octubre',
         'Noviembre', 'Diciembre')


class ErrorPlanilla(Exception):
    pass


# ============================================================
# PERMISO (en el servidor)
# ============================================================
def puede_ver_planilla():
    if es_admin():
        return True
    try:
        from routes.acceso import acceso_usuario
        acc = acceso_usuario()
    except Exception:
        return False
    return bool(acc.get('configurado') and 'planilla' in acc.get('modulos', set()))


@planilla_bp.before_request
def _proteger():
    if 'usuario_id' not in session:
        return None
    if not puede_ver_planilla():
        msg = ('No tienes permiso para entrar a Planilla. Lo ve solo la gerencia y quien tenga el permiso '
               '"Planilla" en Configuración ▸ Usuarios y permisos.')
        if '/api/' in request.path:
            return jsonify({'success': False, 'error': msg, 'codigo': 'sin_permiso'}), 403
        from flask import flash, redirect, url_for
        flash(msg, 'error')
        return redirect(url_for('index'))
    asegurar_tablas()
    return None


# ============================================================
# TABLAS PROPIAS (equivalente: migrations/021_planilla.sql)
# ============================================================
SQL_DDL_PLANILLA = """
    CREATE TABLE IF NOT EXISTS rrhh_config (
        empresa_id VARCHAR(64) PRIMARY KEY,
        regimen_laboral VARCHAR(10) NOT NULL DEFAULT 'GENERAL' CHECK (regimen_laboral IN ('GENERAL', 'PEQUENA', 'MICRO')),
        rmv NUMERIC(10,2) NOT NULL DEFAULT 1130,
        actualizado_por VARCHAR(150),
        actualizado_en TIMESTAMP DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS rrhh_personal (
        id SERIAL PRIMARY KEY,
        empresa_id VARCHAR(64) NOT NULL,
        nombres VARCHAR(150) NOT NULL,
        documento VARCHAR(20),
        tipo VARCHAR(25) NOT NULL CHECK (tipo IN ('Planilla', 'Practicante', 'Recibo por honorarios')),
        cargo VARCHAR(100),
        fecha_ingreso DATE NOT NULL,
        fecha_cese DATE,
        sueldo NUMERIC(12,2) NOT NULL CHECK (sueldo >= 0),
        pension VARCHAR(10) NOT NULL DEFAULT 'Ninguno' CHECK (pension IN ('ONP', 'AFP', 'Ninguno')),
        afp_porcentaje NUMERIC(5,2),
        asignacion_familiar BOOLEAN NOT NULL DEFAULT false,
        banco VARCHAR(60),
        cuenta VARCHAR(60),
        observaciones TEXT,
        jornada_parcial BOOLEAN NOT NULL DEFAULT false,
        creado_por VARCHAR(150),
        creado_en TIMESTAMP DEFAULT NOW(),
        actualizado_por VARCHAR(150),
        actualizado_en TIMESTAMP DEFAULT NOW(),
        historial JSONB NOT NULL DEFAULT '[]'::jsonb
    );
    CREATE INDEX IF NOT EXISTS idx_rrhh_personal_empresa ON rrhh_personal (empresa_id);
    CREATE TABLE IF NOT EXISTS rrhh_vacaciones (
        id SERIAL PRIMARY KEY,
        personal_id INTEGER NOT NULL REFERENCES rrhh_personal(id),
        desde DATE NOT NULL,
        hasta DATE NOT NULL,
        dias INTEGER NOT NULL CHECK (dias > 0),
        nota TEXT,
        creado_por VARCHAR(150),
        creado_en TIMESTAMP DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS rrhh_pagos (
        id SERIAL PRIMARY KEY,
        empresa_id VARCHAR(64) NOT NULL,
        personal_id INTEGER NOT NULL REFERENCES rrhh_personal(id),
        periodo VARCHAR(7) NOT NULL,
        concepto VARCHAR(40) NOT NULL,
        monto NUMERIC(12,2) NOT NULL,
        fecha_pago DATE,
        numero_operacion VARCHAR(80),
        estado VARCHAR(15) NOT NULL DEFAULT 'Pagado' CHECK (estado IN ('Pagado', 'Desmarcado')),
        marcado_por VARCHAR(150),
        marcado_en TIMESTAMP DEFAULT NOW(),
        historial JSONB NOT NULL DEFAULT '[]'::jsonb
    );
    CREATE UNIQUE INDEX IF NOT EXISTS uq_rrhh_pago ON rrhh_pagos (personal_id, periodo, concepto) WHERE estado = 'Pagado';
    ALTER TABLE rrhh_config ENABLE ROW LEVEL SECURITY;
    ALTER TABLE rrhh_personal ENABLE ROW LEVEL SECURITY;
    ALTER TABLE rrhh_vacaciones ENABLE ROW LEVEL SECURITY;
    ALTER TABLE rrhh_pagos ENABLE ROW LEVEL SECURITY;
"""
_tablas = {'ok': False}
_lock = threading.Lock()


def asegurar_tablas():
    if _tablas['ok']:
        return
    with _lock:
        if _tablas['ok']:
            return
        from routes.sunat import asegurar_tablas as asegurar_sunat
        asegurar_sunat()
        with db_tx() as conn:
            cur = conn.cursor()
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('planilla_ddl'))")
            cur.execute(SQL_DDL_PLANILLA)
        _tablas['ok'] = True


# ============================================================
# AYUDAS
# ============================================================
def _usuario():
    return session.get('nombre_completo') or session.get('usuario') or f"Usuario {session.get('usuario_id')}"


def _r(v):
    return redondear(v or 0, 2)


def _n(v):
    return float(_r(v))


def _f(v):
    if isinstance(v, datetime):
        return v.strftime('%Y-%m-%d %H:%M')
    if isinstance(v, date):
        return v.isoformat()
    return v


def _fecha(txt, campo, obligatorio=True):
    t = (txt or '').strip()[:10]
    if not t:
        if obligatorio:
            raise ErrorPlanilla(f'Falta la {campo}.')
        return None
    try:
        return datetime.strptime(t, '%Y-%m-%d').date()
    except ValueError:
        raise ErrorPlanilla(f'La {campo} no es válida.')


def _periodo(txt):
    m = re.match(r'^(\d{4})-(\d{2})$', (txt or '').strip())
    if m and 1 <= int(m.group(2)) <= 12:
        return int(m.group(1)), int(m.group(2))
    h = _ahora().date()
    return h.year, h.month


def _fin_mes(anio, mes):
    return date(anio, mes, calendar.monthrange(anio, mes)[1])


def _empresa(eid_txt=None):
    eid = id_empresa(eid_txt) if eid_txt else None
    e = empresa_por_id(eid) if eid else None
    e = e or empresa_actual()
    if not e:
        lista = lista_empresas()
        e = lista[0] if lista else None
    if not e:
        raise ErrorPlanilla('No hay empresas configuradas (Configuración ▸ Empresas).')
    return e


def leer_config(eid):
    f = db_query("SELECT * FROM rrhh_config WHERE empresa_id = %s", (str(eid),))
    if f:
        c = f[0]
        return {'regimen_laboral': c['regimen_laboral'], 'rmv': a_decimal(c['rmv']), 'configurado': True,
                'actualizado_por': c['actualizado_por'], 'actualizado_en': _f(c['actualizado_en'])}
    return {'regimen_laboral': 'GENERAL', 'rmv': RMV_POR_DEFECTO, 'configurado': False}


def meses_completos(desde, hasta):
    """Meses calendario completos trabajados entre dos fechas (como se cuentan para CTS y gratificación)."""
    if hasta < desde:
        return 0
    meses = (hasta.year - desde.year) * 12 + (hasta.month - desde.month)
    if desde.day > 1:
        meses -= 1                      # el mes de ingreso cuenta solo si entró el día 1
    if hasta.day < calendar.monthrange(hasta.year, hasta.month)[1]:
        pass                            # el mes en curso no se completó: ya está excluido por la resta
    else:
        meses += 1
    return max(meses, 0)


def activo_en(p, d):
    return p['fecha_ingreso'] <= d and (p['fecha_cese'] is None or p['fecha_cese'] >= d)


# ============================================================
# CÁLCULOS
# ============================================================
def remuneracion_computable(p, conf):
    asig = conf['rmv'] * Decimal('0.10') if p['asignacion_familiar'] and p['tipo'] == 'Planilla' else CERO
    return _r(a_decimal(p['sueldo']) + asig), _r(asig)


def gratificacion(p, conf, anio, mes):
    """Gratificación de julio (ene-jun) o diciembre (jul-dic) + bonificación extraordinaria de 9% (Ley 30334)."""
    reg = REGIMENES[conf['regimen_laboral']]
    if p['tipo'] != 'Planilla' or reg['factor_beneficios'] == 0 or mes not in (7, 12):
        return None
    ini = date(anio, 1 if mes == 7 else 7, 1)
    fin = date(anio, 6, 30) if mes == 7 else date(anio, 12, 31)
    desde = max(ini, p['fecha_ingreso'])
    hasta = min(fin, p['fecha_cese']) if p['fecha_cese'] else fin
    meses = min(meses_completos(desde, hasta), 6)
    if meses <= 0:
        return None
    comp, _ = remuneracion_computable(p, conf)
    grati = _r(comp * reg['factor_beneficios'] * meses / 6)
    bono = _r(grati * Decimal('0.09'))
    return {'concepto': 'Gratificación', 'meses': meses, 'grati': grati, 'bonificacion': bono, 'total': grati + bono,
            'detalle': f'{meses} de 6 meses · incluye bonificación de 9% (S/ {bono:,.2f})'}


def cts(p, conf, anio, mes):
    """CTS de mayo (nov-abr) o noviembre (may-oct): (remuneración + 1/6 de la gratificación) / 12 por mes."""
    reg = REGIMENES[conf['regimen_laboral']]
    if p['tipo'] != 'Planilla' or reg['factor_beneficios'] == 0 or mes not in (5, 11):
        return None
    if mes == 5:
        ini, fin = date(anio - 1, 11, 1), date(anio, 4, 30)
    else:
        ini, fin = date(anio, 5, 1), date(anio, 10, 31)
    desde = max(ini, p['fecha_ingreso'])
    hasta = min(fin, p['fecha_cese']) if p['fecha_cese'] else fin
    meses = min(meses_completos(desde, hasta), 6)
    if meses <= 0:
        return None
    comp, _ = remuneracion_computable(p, conf)
    sexto = _r(comp * reg['factor_beneficios'] / 6)       # 1/6 de la última gratificación (completa)
    monto = _r((comp + sexto) * reg['factor_beneficios'] * meses / 12)
    return {'concepto': 'CTS', 'meses': meses, 'total': monto,
            'detalle': f'{meses} de 6 meses · depósito en la cuenta CTS hasta el 15'}


def subvencion_adicional(p, anio, mes):
    """Practicantes: media subvención cada 6 meses continuos (Ley 28518, art. 47)."""
    if p['tipo'] != 'Practicante':
        return None
    ing = p['fecha_ingreso']
    meses = (anio - ing.year) * 12 + (mes - ing.month)
    if meses <= 0 or meses % 6 != 0 or not activo_en(p, _fin_mes(anio, mes)):
        return None
    monto = _r(a_decimal(p['sueldo']) / 2)
    return {'concepto': 'Subvención adicional', 'total': monto, 'detalle': f'Cumple {meses} meses: media subvención'}


def lineas_del_mes(p, conf, anio, mes):
    """Pagos de una persona en el mes: [{concepto, bruto, descuento, neto, essalud, detalle}]."""
    fin = _fin_mes(anio, mes)
    ini = date(anio, mes, 1)
    if p['fecha_ingreso'] > fin or (p['fecha_cese'] and p['fecha_cese'] < ini):
        return []
    lineas = []
    dias_mes = calendar.monthrange(anio, mes)[1]
    desde, hasta = max(ini, p['fecha_ingreso']), min(fin, p['fecha_cese'] or fin)
    dias = (hasta - desde).days + 1
    proporcion = Decimal('1') if dias >= dias_mes else Decimal(dias) / Decimal('30')
    sueldo = _r(a_decimal(p['sueldo']) * proporcion)
    nota = '' if proporcion == 1 else f'{dias} días del mes'
    if p['tipo'] == 'Planilla':
        comp, asig = remuneracion_computable(p, conf)
        bruto = _r(sueldo + asig * proporcion)
        pct = Decimal('13') if p['pension'] == 'ONP' else a_decimal(p['afp_porcentaje']) if p['pension'] == 'AFP' else CERO
        desc = _r(bruto * pct / 100)
        essalud = _r(max(bruto, conf['rmv']) * Decimal('0.09'))
        det = ', '.join(x for x in (nota, f'asignación familiar S/ {asig * proporcion:,.2f}' if asig else '',
                                    f"{p['pension']} {pct:g}%" if pct else 'sin pensión') if x)
        lineas.append({'concepto': 'Sueldo', 'bruto': bruto, 'descuento': desc, 'neto': bruto - desc, 'essalud': essalud,
                       'onp': desc if p['pension'] == 'ONP' else CERO, 'afp': desc if p['pension'] == 'AFP' else CERO,
                       'renta_4ta': CERO, 'detalle': det})
        for extra in (gratificacion(p, conf, anio, mes), cts(p, conf, anio, mes)):
            if extra:
                lineas.append({'concepto': extra['concepto'], 'bruto': extra['total'], 'descuento': CERO,
                               'neto': extra['total'], 'essalud': CERO, 'onp': CERO, 'afp': CERO, 'renta_4ta': CERO,
                               'detalle': extra['detalle']})
    elif p['tipo'] == 'Practicante':
        lineas.append({'concepto': 'Subvención', 'bruto': sueldo, 'descuento': CERO, 'neto': sueldo, 'essalud': CERO,
                       'onp': CERO, 'afp': CERO, 'renta_4ta': CERO, 'detalle': nota or 'Sin descuentos'})
        extra = subvencion_adicional(p, anio, mes)
        if extra:
            lineas.append({'concepto': extra['concepto'], 'bruto': extra['total'], 'descuento': CERO, 'neto': extra['total'],
                           'essalud': CERO, 'onp': CERO, 'afp': CERO, 'renta_4ta': CERO, 'detalle': extra['detalle']})
    else:
        ret = _r(sueldo * Decimal('0.08')) if sueldo > 1500 else CERO
        lineas.append({'concepto': 'Recibo por honorarios', 'bruto': sueldo, 'descuento': ret, 'neto': sueldo - ret,
                       'essalud': CERO, 'onp': CERO, 'afp': CERO, 'renta_4ta': ret,
                       'detalle': 'Retención de 4.ª de 8% (recibo mayor a S/ 1,500)' if ret else 'Sin retención (hasta S/ 1,500)'})
    return lineas


def vacaciones(p, conf, hoy=None):
    hoy = hoy or _ahora().date()
    por_anio = 15 if p['tipo'] == 'Practicante' else REGIMENES[conf['regimen_laboral']]['vacaciones']
    if p['tipo'] == 'Recibo por honorarios':
        return None
    fin = min(hoy, p['fecha_cese']) if p['fecha_cese'] else hoy
    meses = meses_completos(p['fecha_ingreso'], fin) if fin >= p['fecha_ingreso'] else 0
    ganados = (Decimal(por_anio) * meses / 12).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
    regs = db_query("SELECT desde, hasta, dias, nota, creado_por FROM rrhh_vacaciones WHERE personal_id = %s ORDER BY desde DESC",
                    (p['id'],))
    tomados = sum((r['dias'] for r in regs), 0)
    pendientes = ganados - tomados
    # Al año de trabajo se gana el derecho y hay un año más para gozarlo (si no, "triple vacacional" en régimen general).
    # "Acumulado" = días de un año cuyo plazo para gozarlos ya venció y aún no se tomaron.
    vencidos = max(meses // 12 - 1, 0) * por_anio - tomados
    return {'por_anio': por_anio, 'meses': meses, 'ganados': float(ganados), 'tomados': tomados,
            'pendientes': float(pendientes), 'acumulado': vencidos > 0, 'vencidos': max(vencidos, 0),
            'registros': [{k: _f(v) for k, v in r.items()} for r in regs]}


def personal(eid, solo_activos=False):
    filas = db_query("SELECT * FROM rrhh_personal WHERE empresa_id = %s ORDER BY (fecha_cese IS NOT NULL), tipo, nombres",
                     (str(eid),))
    hoy = _ahora().date()
    if solo_activos:
        filas = [p for p in filas if p['fecha_cese'] is None or p['fecha_cese'] >= hoy.replace(day=1)]
    return filas


def pagos_del_mes(e, anio, mes, sincronizar=True):
    eid = str(e['id'])
    conf = leer_config(eid)
    periodo = f'{anio:04d}-{mes:02d}'
    marcados = {(r['personal_id'], r['concepto']): r for r in db_query(
        "SELECT * FROM rrhh_pagos WHERE empresa_id = %s AND periodo = %s AND estado = 'Pagado'", (eid, periodo))}
    filas, tot = [], {k: CERO for k in ('bruto', 'descuento', 'neto', 'essalud', 'onp', 'afp', 'renta_4ta')}
    base_essalud, base_onp, sueldos_netos = CERO, CERO, CERO
    for p in personal(eid):
        for ln in lineas_del_mes(p, conf, anio, mes):
            pag = marcados.get((p['id'], ln['concepto']))
            filas.append({'personal_id': p['id'], 'nombres': p['nombres'], 'documento': p['documento'], 'tipo': p['tipo'],
                          'cargo': p['cargo'], 'banco': p['banco'], 'cuenta': p['cuenta'],
                          'concepto': ln['concepto'], 'detalle': ln['detalle'],
                          'bruto': _n(ln['bruto']), 'descuento': _n(ln['descuento']), 'neto': _n(ln['neto']),
                          'essalud': _n(ln['essalud']), 'pagado': bool(pag),
                          'fecha_pago': _f(pag['fecha_pago']) if pag else None,
                          'numero_operacion': pag['numero_operacion'] if pag else None,
                          'marcado_por': pag['marcado_por'] if pag else None, 'marcado_en': _f(pag['marcado_en']) if pag else None})
            for k in tot:
                tot[k] += ln[k]
            if ln['concepto'] == 'Sueldo':
                base_essalud += max(ln['bruto'], conf['rmv'])
                if p['pension'] == 'ONP':
                    base_onp += ln['bruto']
            if ln['concepto'] in ('Sueldo', 'Subvención'):
                sueldos_netos += ln['neto']
    enviado = None
    hoy = _ahora().date()
    reciente = (anio * 12 + mes) >= (hoy.year * 12 + hoy.month - 1)   # meses viejos ya los declaró el contador
    if sincronizar and filas and reciente:
        enviado = enviar_a_sunat(eid, periodo, base_essalud, base_onp, tot['afp'], sueldos_netos, tot['renta_4ta'])
    pend = [f for f in filas if not f['pagado']]
    return {'empresa': {'id': eid, 'codigo': e['codigo']}, 'periodo': periodo, 'nombre_periodo': f'{MESES[mes - 1]} {anio}',
            'config': {**conf, 'rmv': float(conf['rmv']), 'regimen_nombre': REGIMENES[conf['regimen_laboral']]['nombre']},
            'filas': filas, 'totales': {k: _n(v) for k, v in tot.items()},
            'por_pagar': _n(sum((a_decimal(f['neto']) for f in pend), CERO)), 'por_pagar_n': len(pend),
            'pagado': _n(sum((a_decimal(f['neto']) for f in filas if f['pagado']), CERO)),
            'costo_empresa': _n(tot['bruto'] + tot['essalud']), 'enviado_sunat': enviado, 'mes_reciente': reciente}


def enviar_a_sunat(eid, periodo, base_essalud, base_onp, afp, remuneraciones, renta_4ta):
    """Pasa la planilla del mes al módulo SUNAT (Pagos del mes / PLAME). Solo escribe si cambió."""
    from routes.sunat import leer_periodo, guardar_periodo
    nuevo = {'base_essalud': str(_r(base_essalud)), 'base_onp': str(_r(base_onp)), 'afp': str(_r(afp)),
             'remuneraciones': str(_r(remuneraciones)), 'renta_4ta': str(_r(renta_4ta))}
    actual = leer_periodo(eid, periodo)['planilla'] or {}
    if any(str(actual.get(k) or '') != v for k, v in nuevo.items()):
        guardar_periodo(eid, periodo, 'planilla', nuevo)
    return {k: float(v) for k, v in nuevo.items()}


def proximos_beneficios(e, hoy=None):
    """Próxima gratificación y próxima CTS de cada persona en planilla (estimado a hoy)."""
    hoy = hoy or _ahora().date()
    conf = leer_config(str(e['id']))
    eventos = []
    for anio in (hoy.year, hoy.year + 1):
        for mes, tipo in ((5, 'CTS'), (7, 'Gratificación'), (11, 'CTS'), (12, 'Gratificación')):
            vence = date(anio, mes, 15)
            if vence >= hoy:
                eventos.append((vence, tipo, anio, mes))
    eventos.sort()
    salida = []
    vistos = set()
    for vence, tipo, anio, mes in eventos:
        if tipo in vistos:
            continue
        vistos.add(tipo)
        filas = []
        for p in personal(str(e['id']), solo_activos=True):
            calc = gratificacion(p, conf, anio, mes) if tipo == 'Gratificación' else cts(p, conf, anio, mes)
            if calc:
                filas.append({'nombres': p['nombres'], 'meses': calc['meses'], 'monto': _n(calc['total']), 'detalle': calc['detalle']})
        practicantes = []
        if tipo == 'Gratificación':
            for p in personal(str(e['id']), solo_activos=True):
                if p['tipo'] == 'Practicante':
                    for k in range(0, 7):
                        a, m = (hoy.year * 12 + hoy.month - 1 + k) // 12, (hoy.year * 12 + hoy.month - 1 + k) % 12 + 1
                        extra = subvencion_adicional(p, a, m)
                        if extra:
                            practicantes.append({'nombres': p['nombres'], 'mes': f'{MESES[m - 1]} {a}', 'monto': _n(extra['total'])})
                            break
        salida.append({'tipo': tipo, 'vence': vence.isoformat(), 'nombre': f'{tipo} de {MESES[mes - 1].lower()} {anio}',
                       'personas': filas, 'total': _n(sum((Decimal(str(f['monto'])) for f in filas), CERO)),
                       'aplica': REGIMENES[conf['regimen_laboral']]['factor_beneficios'] > 0,
                       'practicantes': practicantes})
    return salida


# ============================================================
# ESCRITURA
# ============================================================
def guardar_persona(eid, d, pid=None):
    nombres = (d.get('nombres') or '').strip()
    if len(nombres) < 3:
        raise ErrorPlanilla('Escribe el nombre completo.')
    tipo = d.get('tipo')
    if tipo not in TIPOS:
        raise ErrorPlanilla('Elige si está en planilla, es practicante o emite recibo por honorarios.')
    ingreso = _fecha(d.get('fecha_ingreso'), 'fecha de ingreso')
    cese = _fecha(d.get('fecha_cese'), 'fecha de cese', obligatorio=False)
    if cese and cese < ingreso:
        raise ErrorPlanilla('La fecha de cese no puede ser antes del ingreso.')
    if d.get('sueldo') in (None, ''):
        raise ErrorPlanilla('Escribe el sueldo o la subvención mensual.')
    sueldo = _r(d.get('sueldo'))
    if sueldo <= 0:
        raise ErrorPlanilla('El sueldo o la subvención debe ser mayor a 0.')
    conf = leer_config(eid)
    parcial = bool(d.get('jornada_parcial'))
    if tipo in ('Planilla', 'Practicante') and sueldo < conf['rmv'] and not parcial:
        raise ErrorPlanilla(f"No puede ser menor a la remuneración mínima (S/ {conf['rmv']:,.2f}). "
                            f"Si trabaja medio tiempo, marca \"Jornada parcial\".")
    pension = d.get('pension') if tipo == 'Planilla' else 'Ninguno'
    if pension not in PENSIONES:
        raise ErrorPlanilla('Elige ONP, AFP o Ninguno.')
    afp = None
    if pension == 'AFP':
        if d.get('afp_porcentaje') in (None, ''):
            raise ErrorPlanilla('Escribe el % total que descuenta la AFP (aporte + seguro + comisión), por ejemplo 11.37.')
        afp = _r(d.get('afp_porcentaje'))
        if not 0 < afp < 20:
            raise ErrorPlanilla('El % de AFP no es válido.')
    doc = re.sub(r'\D', '', d.get('documento') or '')[:20] or None
    valores = (nombres[:150], doc, tipo, (d.get('cargo') or '').strip()[:100] or None, ingreso, cese, sueldo, pension, afp,
               bool(d.get('asignacion_familiar')) and tipo == 'Planilla', (d.get('banco') or '').strip()[:60] or None,
               (d.get('cuenta') or '').strip()[:60] or None, (d.get('observaciones') or '').strip()[:500] or None,
               parcial and tipo != 'Recibo por honorarios')
    with db_tx() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if pid:
            cur.execute("SELECT * FROM rrhh_personal WHERE id = %s AND empresa_id = %s FOR UPDATE", (pid, eid))
            antes = cur.fetchone()
            if not antes:
                raise ErrorPlanilla('Persona no encontrada en esta empresa.')
            cambios = []
            for campo, nuevo in zip(('nombres', 'documento', 'tipo', 'cargo', 'fecha_ingreso', 'fecha_cese', 'sueldo',
                                     'pension', 'afp_porcentaje', 'asignacion_familiar', 'banco', 'cuenta', 'observaciones',
                                     'jornada_parcial'), valores):
                if str(antes[campo] if antes[campo] is not None else '') != str(nuevo if nuevo is not None else ''):
                    cambios.append(f'{campo}: {_f(antes[campo])} → {_f(nuevo)}')
            cur.execute("""UPDATE rrhh_personal SET nombres = %s, documento = %s, tipo = %s, cargo = %s, fecha_ingreso = %s,
                           fecha_cese = %s, sueldo = %s, pension = %s, afp_porcentaje = %s, asignacion_familiar = %s,
                           banco = %s, cuenta = %s, observaciones = %s, jornada_parcial = %s, actualizado_por = %s, actualizado_en = NOW(),
                           historial = historial || %s::jsonb WHERE id = %s""",
                        valores + (_usuario(), Json([{'usuario': _usuario(), 'fecha': _ahora().strftime('%Y-%m-%d %H:%M'),
                                                     'cambios': cambios}]), pid))
            return pid
        cur.execute("""INSERT INTO rrhh_personal (nombres, documento, tipo, cargo, fecha_ingreso, fecha_cese, sueldo, pension,
                       afp_porcentaje, asignacion_familiar, banco, cuenta, observaciones, jornada_parcial, empresa_id,
                       creado_por, actualizado_por)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    valores + (eid, _usuario(), _usuario()))
        return cur.fetchone()['id']


def registrar_vacaciones(eid, pid, d):
    desde = _fecha(d.get('desde'), 'fecha de inicio')
    hasta = _fecha(d.get('hasta'), 'fecha de fin')
    if hasta < desde:
        raise ErrorPlanilla('La fecha de fin no puede ser antes del inicio.')
    dias = (hasta - desde).days + 1
    p = db_query("SELECT id FROM rrhh_personal WHERE id = %s AND empresa_id = %s", (pid, eid))
    if not p:
        raise ErrorPlanilla('Persona no encontrada en esta empresa.')
    choque = db_query("SELECT 1 FROM rrhh_vacaciones WHERE personal_id = %s AND desde <= %s AND hasta >= %s",
                      (pid, hasta, desde))
    if choque:
        raise ErrorPlanilla('Esas fechas se cruzan con vacaciones ya registradas.')
    db_query("""INSERT INTO rrhh_vacaciones (personal_id, desde, hasta, dias, nota, creado_por)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
             (pid, desde, hasta, dias, (d.get('nota') or '').strip()[:300] or None, _usuario()))
    return dias


def marcar_pago(e, d):
    eid = str(e['id'])
    anio, mes = _periodo(d.get('periodo'))
    pid = int(d.get('personal_id') or 0)
    concepto = d.get('concepto')
    op = (d.get('numero_operacion') or '').strip()[:80]
    if not op:
        raise ErrorPlanilla('Escribe el N° de operación del pago (lo da el banco).')
    fecha_pago = _fecha(d.get('fecha_pago') or _ahora().date().isoformat(), 'fecha de pago')
    pagos = pagos_del_mes(e, anio, mes, sincronizar=False)
    fila = next((f for f in pagos['filas'] if f['personal_id'] == pid and f['concepto'] == concepto), None)
    if not fila:
        raise ErrorPlanilla('Ese pago no corresponde a este mes.')
    if fila['pagado']:
        raise ErrorPlanilla('Ese pago ya está marcado.')
    monto = _r(d.get('monto') if d.get('monto') not in (None, '') else fila['neto'])
    db_query("""INSERT INTO rrhh_pagos (empresa_id, personal_id, periodo, concepto, monto, fecha_pago, numero_operacion,
                marcado_por) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
             (eid, pid, pagos['periodo'], concepto, monto, fecha_pago, op, _usuario()))


def desmarcar_pago(e, d):
    motivo = (d.get('motivo') or '').strip()
    if not motivo:
        raise ErrorPlanilla('Escribe el motivo para desmarcar.')
    anio, mes = _periodo(d.get('periodo'))
    filas = db_query("""UPDATE rrhh_pagos SET estado = 'Desmarcado', historial = historial || %s::jsonb
                        WHERE empresa_id = %s AND personal_id = %s AND periodo = %s AND concepto = %s AND estado = 'Pagado'
                        RETURNING id""",
                     (Json([{'accion': 'Desmarcado', 'motivo': motivo, 'usuario': _usuario(),
                             'fecha': _ahora().strftime('%Y-%m-%d %H:%M')}]),
                      str(e['id']), int(d.get('personal_id') or 0), f'{anio:04d}-{mes:02d}', d.get('concepto')))
    if not filas:
        raise ErrorPlanilla('Ese pago no estaba marcado.')


# ============================================================
# RUTAS
# ============================================================
def _err(ex, codigo=400):
    return jsonify({'success': False, 'error': str(ex)}), codigo


@planilla_bp.route('/planilla')
def pagina():
    emps = [{'id': x['id'], 'codigo': x['codigo']} for x in lista_empresas()]
    activa = empresa_actual()
    return render_template('planilla.html', empresas=emps, empresa_activa=activa['id'] if activa else None,
                           es_admin=es_admin(), regimenes={k: v['nombre'] for k, v in REGIMENES.items()},
                           tipos=TIPOS, pensiones=PENSIONES)


@planilla_bp.route('/planilla/api/personal')
def api_personal():
    try:
        e = _empresa(request.args.get('empresa_id'))
        conf = leer_config(str(e['id']))
        salida = []
        for p in personal(str(e['id'])):
            item = {k: _f(v) for k, v in p.items() if k != 'historial'}
            item['sueldo'] = _n(p['sueldo'])
            item['afp_porcentaje'] = float(p['afp_porcentaje']) if p['afp_porcentaje'] is not None else None
            item['activo'] = p['fecha_cese'] is None or p['fecha_cese'] >= _ahora().date()
            item['vacaciones'] = vacaciones(p, conf)
            item['historial'] = p['historial'] or []
            item['renta_5ta'] = p['tipo'] == 'Planilla' and a_decimal(p['sueldo']) * 14 > UIT_2026 * 7
            salida.append(item)
        cuenta = {t: sum(1 for x in salida if x['tipo'] == t and x['activo']) for t in TIPOS}
        return jsonify({'success': True, 'data': {
            'empresa': {'id': str(e['id']), 'codigo': e['codigo']}, 'personal': salida, 'cuenta': cuenta,
            'config': {**conf, 'rmv': float(conf['rmv']), 'regimen_nombre': REGIMENES[conf['regimen_laboral']]['nombre']},
            'beneficios': proximos_beneficios(e)}})
    except ErrorPlanilla as ex:
        return _err(ex)


@planilla_bp.route('/planilla/api/personal', methods=['POST'])
@planilla_bp.route('/planilla/api/personal/<int:pid>', methods=['PUT'])
def api_guardar_persona(pid=None):
    try:
        d = request.get_json(silent=True) or {}
        e = _empresa(d.get('empresa_id'))
        nuevo = guardar_persona(str(e['id']), d, pid)
        return jsonify({'success': True, 'id': nuevo, 'message': 'Guardado.'})
    except ErrorPlanilla as ex:
        return _err(ex)


@planilla_bp.route('/planilla/api/personal/<int:pid>/vacaciones', methods=['POST'])
def api_vacaciones(pid):
    try:
        d = request.get_json(silent=True) or {}
        e = _empresa(d.get('empresa_id'))
        dias = registrar_vacaciones(str(e['id']), pid, d)
        return jsonify({'success': True, 'message': f'Vacaciones registradas: {dias} días.'})
    except ErrorPlanilla as ex:
        return _err(ex)


@planilla_bp.route('/planilla/api/pagos')
def api_pagos():
    try:
        e = _empresa(request.args.get('empresa_id'))
        anio, mes = _periodo(request.args.get('periodo'))
        return jsonify({'success': True, 'data': pagos_del_mes(e, anio, mes)})
    except ErrorPlanilla as ex:
        return _err(ex)


@planilla_bp.route('/planilla/api/pagos/marcar', methods=['POST'])
def api_marcar():
    try:
        d = request.get_json(silent=True) or {}
        marcar_pago(_empresa(d.get('empresa_id')), d)
        return jsonify({'success': True, 'message': 'Pago marcado.'})
    except (ValueError, TypeError):
        return _err('Datos inválidos.')
    except ErrorPlanilla as ex:
        return _err(ex)


@planilla_bp.route('/planilla/api/pagos/desmarcar', methods=['POST'])
def api_desmarcar():
    try:
        d = request.get_json(silent=True) or {}
        desmarcar_pago(_empresa(d.get('empresa_id')), d)
        return jsonify({'success': True, 'message': 'Pago desmarcado.'})
    except (ValueError, TypeError):
        return _err('Datos inválidos.')
    except ErrorPlanilla as ex:
        return _err(ex)


@planilla_bp.route('/planilla/api/config', methods=['POST'])
def api_config():
    if not es_admin():
        return _err('Solo el administrador cambia el régimen laboral.', 403)
    try:
        d = request.get_json(silent=True) or {}
        e = _empresa(d.get('empresa_id'))
        reg = d.get('regimen_laboral')
        if reg not in REGIMENES:
            raise ErrorPlanilla('Elige el régimen laboral.')
        rmv = _r(d.get('rmv') or RMV_POR_DEFECTO)
        if not Decimal('900') <= rmv <= Decimal('3000'):
            raise ErrorPlanilla('La remuneración mínima no es válida.')
        db_query("""INSERT INTO rrhh_config (empresa_id, regimen_laboral, rmv, actualizado_por, actualizado_en)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (empresa_id) DO UPDATE SET regimen_laboral = EXCLUDED.regimen_laboral, rmv = EXCLUDED.rmv,
                        actualizado_por = EXCLUDED.actualizado_por, actualizado_en = NOW() RETURNING empresa_id""",
                 (str(e['id']), reg, rmv, _usuario()))
        return jsonify({'success': True, 'message': 'Régimen guardado.'})
    except ErrorPlanilla as ex:
        return _err(ex)
