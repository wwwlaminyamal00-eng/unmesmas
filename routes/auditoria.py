# routes/auditoria.py - Auditoría del ERP (pedido de Erika: "TRAZABILIDAD PARA TODO", 16/10/2026)
#
# En simple:
#   - Todo queda en la tabla erp_auditoria (la que ya existía): quién, cuándo, qué tabla, qué registro,
#     qué acción (crear, editar, anular, aprobar, eliminar, login, logout...) y cómo estaba antes y después.
#   - La base de datos registra sola los cambios de las tablas de negocio (disparadores / triggers).
#     Si el registro de auditoría falla, la operación del usuario NO se bloquea.
#   - Las contraseñas nunca se guardan en la auditoría.
#   - El usuario que hizo el cambio llega a la base con set_config('erp.usuario_id', ...).
#     Mientras database.get_connection no lo haga (ver informe), el disparador usa el usuario
#     que el propio registro tenga (usuario_id, creado_por, eliminado_por...).
# Script equivalente para Supabase: mig009/auditoria_papelera.sql
import json
import threading
from datetime import date, datetime
from decimal import Decimal

from flask import has_request_context, request, session

from database import db_tx

# Tablas de negocio con auditoría automática: tabla -> (módulo, columnas que no cuentan como cambio)
# (updated_at cambia solo; productos.stock lo recalcula Inventario en cada movimiento)
TABLAS_AUDITADAS = {
    'cotizaciones': ('Ventas · Cotizaciones', 'updated_at'),
    'pedido_compra_pc': ('Ventas · Pedidos (PC)', 'updated_at'),
    'despachos': ('Ventas · Despachos', 'updated_at'),
    'guias_remision': ('Ventas · Guías', 'updated_at'),
    'comprobantes': ('Ventas · Facturas', 'updated_at'),
    'notas_credito': ('Ventas · Notas de crédito', 'updated_at'),
    'devoluciones': ('Ventas · Devoluciones', 'updated_at'),
    'ordenes_compra': ('Compras · Órdenes de compra', 'updated_at'),
    'solicitudes_compra': ('Compras · Solicitudes', 'updated_at'),
    'comprobantes_proveedor': ('Compras · Facturas de proveedor', 'updated_at'),
    'productos': ('Maestros · Productos', 'updated_at,stock'),
    'clientes': ('Maestros · Clientes', 'updated_at'),
    'proveedores': ('Maestros · Proveedores', 'updated_at'),
    'inv_movimientos': ('Inventario · Movimientos', 'updated_at'),
    'usuarios': ('Configuración · Usuarios', 'updated_at'),
    'erp_usuario_permisos': ('Configuración · Permisos', 'updated_at'),
    'finanzas_pagos': ('Finanzas · Cobros y pagos', 'updated_at'),
}

COLUMNAS_NUEVAS = (('usuario_id', 'INTEGER'), ('usuario_nombre', 'TEXT'), ('modulo', 'TEXT'),
                   ('empresa', 'TEXT'), ('ip', 'TEXT'), ('detalle', 'TEXT'))

SQL_TABLA = """
    CREATE TABLE IF NOT EXISTS erp_auditoria (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        empresa_id UUID,
        auth_user_id UUID,
        tabla TEXT NOT NULL,
        registro_id TEXT,
        accion TEXT NOT NULL,
        data_anterior JSONB,
        data_nueva JSONB,
        created_at TIMESTAMPTZ DEFAULT now()
    );
""" + ''.join(f"\n    ALTER TABLE erp_auditoria ADD COLUMN IF NOT EXISTS {c} {t};" for c, t in COLUMNAS_NUEVAS) + """
    CREATE INDEX IF NOT EXISTS idx_erp_auditoria_fecha ON erp_auditoria (created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_erp_auditoria_registro ON erp_auditoria (tabla, registro_id);
    CREATE INDEX IF NOT EXISTS idx_erp_auditoria_accion ON erp_auditoria (accion);
"""

# Disparador genérico. {REGISTRO} se cambia según el tipo de erp_auditoria.registro_id
# (TEXT en Supabase; INTEGER en bases antiguas).
SQL_FUNCION = r"""
CREATE OR REPLACE FUNCTION fn_erp_auditoria() RETURNS trigger
LANGUAGE plpgsql SET search_path = public AS $f$
DECLARE
    v_old jsonb; v_new jsonb; v_cmp_old jsonb; v_cmp_new jsonb;
    v_ign text[]; v_accion text; v_id text; v_emp text; v_uid text; v_unom text;
    v_est_old text; v_est_new text; v_detalle text; v_modulo text; k text; v_cambios text[] := '{}';
BEGIN
    BEGIN
        IF COALESCE(current_setting('erp.auditoria_off', true), '') = '1' THEN
            RETURN NULL;
        END IF;
        v_modulo := COALESCE(TG_ARGV[0], TG_TABLE_NAME);
        v_ign := string_to_array(COALESCE(TG_ARGV[1], 'updated_at'), ',');
        IF TG_OP <> 'INSERT' THEN v_old := to_jsonb(OLD) - 'password'; END IF;
        IF TG_OP <> 'DELETE' THEN v_new := to_jsonb(NEW) - 'password'; END IF;
        v_id := COALESCE(v_new->>'id', v_old->>'id');
        v_emp := COALESCE(v_new->>'empresa_id', v_old->>'empresa_id', NULLIF(current_setting('erp.empresa_id', true), ''));
        v_uid := NULLIF(current_setting('erp.usuario_id', true), '');
        v_unom := NULLIF(current_setting('erp.usuario_nombre', true), '');

        IF TG_OP = 'INSERT' THEN
            v_accion := 'crear';
            v_uid := COALESCE(v_uid, v_new->>'usuario_id', v_new->>'creado_por');
            v_unom := COALESCE(v_unom, v_new->>'usuario_nombre', v_new->>'creado_por_nombre');
        ELSIF TG_OP = 'DELETE' THEN
            v_accion := 'eliminar';
            v_detalle := 'Registro borrado de la base';
        ELSE
            v_cmp_old := v_old - v_ign;
            v_cmp_new := v_new - v_ign;
            IF v_cmp_old = v_cmp_new THEN
                IF (to_jsonb(OLD)->>'password') IS DISTINCT FROM (to_jsonb(NEW)->>'password') THEN
                    v_accion := 'editar';
                    v_detalle := 'Cambio de contraseña (la contraseña no se guarda)';
                ELSE
                    RETURN NULL;  -- solo cambió la fecha de actualización o el stock calculado
                END IF;
            ELSE
                FOR k IN SELECT jsonb_object_keys(v_cmp_new) LOOP
                    IF (v_cmp_new->k) IS DISTINCT FROM (v_cmp_old->k) THEN
                        v_cambios := v_cambios || k;
                    END IF;
                END LOOP;
                v_detalle := 'Cambió: ' || array_to_string(v_cambios, ', ');
                v_est_old := COALESCE(v_old->>'estado', v_old->>'estado_sunat');
                v_est_new := COALESCE(v_new->>'estado', v_new->>'estado_sunat');
                v_accion := 'editar';
                IF v_est_new IS DISTINCT FROM v_est_old AND v_est_new IS NOT NULL THEN
                    v_detalle := 'Estado: ' || COALESCE(v_est_old, '—') || ' → ' || v_est_new;
                    IF upper(v_est_new) LIKE 'ANULAD%' THEN v_accion := 'anular';
                    ELSIF upper(v_est_new) LIKE 'ELIMINAD%' THEN v_accion := 'eliminar';
                    ELSIF upper(v_est_new) ~ '(APROBAD|VALIDAD|ACEPTAD|AUTORIZAD)' THEN v_accion := 'aprobar';
                    ELSIF upper(v_est_new) LIKE 'RECHAZAD%' THEN v_accion := 'rechazar';
                    ELSIF upper(COALESCE(v_est_old, '')) LIKE 'ANULAD%' THEN v_accion := 'restaurar';
                    END IF;
                ELSIF (v_old->>'activo') = 'true' AND (v_new->>'activo') = 'false' THEN
                    v_accion := 'desactivar';
                ELSIF (v_old->>'activo') = 'false' AND (v_new->>'activo') = 'true' THEN
                    v_accion := 'activar';
                END IF;
                -- Quien anuló / aprobó / eliminó, si el propio registro lo dice
                v_uid := COALESCE(v_uid,
                    CASE WHEN (v_new->>'eliminado_por') IS DISTINCT FROM (v_old->>'eliminado_por') THEN v_new->>'eliminado_por' END,
                    CASE WHEN (v_new->>'usuario_validacion_id') IS DISTINCT FROM (v_old->>'usuario_validacion_id') THEN v_new->>'usuario_validacion_id' END,
                    CASE WHEN (v_new->>'usuario_aceptacion_id') IS DISTINCT FROM (v_old->>'usuario_aceptacion_id') THEN v_new->>'usuario_aceptacion_id' END,
                    CASE WHEN (v_new->>'usuario_rechazo_id') IS DISTINCT FROM (v_old->>'usuario_rechazo_id') THEN v_new->>'usuario_rechazo_id' END,
                    CASE WHEN (v_new->>'aprobado_por_id') IS DISTINCT FROM (v_old->>'aprobado_por_id') THEN v_new->>'aprobado_por_id' END);
                v_unom := COALESCE(v_unom,
                    CASE WHEN (v_new->>'anulado_por') IS DISTINCT FROM (v_old->>'anulado_por') AND (v_new->>'anulado_por') !~ '^\d+$'
                         THEN v_new->>'anulado_por' END,
                    CASE WHEN (v_new->>'aprobado_por') IS DISTINCT FROM (v_old->>'aprobado_por') THEN v_new->>'aprobado_por' END,
                    CASE WHEN (v_new->>'validado_por_nombre') IS DISTINCT FROM (v_old->>'validado_por_nombre') THEN v_new->>'validado_por_nombre' END);
            END IF;
        END IF;

        IF NULLIF(current_setting('erp.origen', true), '') IS NOT NULL THEN
            v_detalle := current_setting('erp.origen', true) || COALESCE(' · ' || v_detalle, '');
        END IF;
        IF v_uid !~ '^\d+$' THEN v_uid := NULL; END IF;
        IF v_unom IS NULL AND v_uid IS NOT NULL THEN
            SELECT COALESCE(NULLIF(u.nombres_apellidos, ''), u.usuario_sistema) INTO v_unom
            FROM usuarios u WHERE u.id = v_uid::integer;
        END IF;

        INSERT INTO erp_auditoria (empresa_id, tabla, registro_id, accion, data_anterior, data_nueva,
                                   usuario_id, usuario_nombre, modulo, empresa, ip, detalle)
        VALUES ((SELECT e.id FROM erp_empresas e WHERE e.id::text = v_emp LIMIT 1),
                TG_TABLE_NAME, {REGISTRO}, v_accion, v_old, v_new,
                v_uid::integer, v_unom, v_modulo,
                (SELECT upper(e.codigo) FROM erp_empresas e WHERE e.id::text = v_emp LIMIT 1),
                NULLIF(current_setting('erp.ip', true), ''), v_detalle);
    EXCEPTION WHEN OTHERS THEN
        -- La auditoría nunca bloquea la operación del usuario
        RAISE WARNING 'auditoria (%): %', TG_TABLE_NAME, SQLERRM;
    END;
    RETURN NULL;
END $f$;
"""

REGISTRO_TEXTO = 'v_id'
REGISTRO_ENTERO = "CASE WHEN v_id ~ '^\\d+$' THEN v_id::integer END"


def sql_trigger(tabla):
    modulo, ignorar = TABLAS_AUDITADAS[tabla]
    return (f"CREATE OR REPLACE TRIGGER trg_erp_auditoria AFTER INSERT OR UPDATE OR DELETE ON {tabla} "
            f"FOR EACH ROW EXECUTE FUNCTION fn_erp_auditoria('{modulo}', '{ignorar}');")


_listo = False
_lock = threading.Lock()
_tipo_registro = {}


def asegurar_auditoria():
    """Columnas nuevas de erp_auditoria + disparadores en las tablas de negocio. No borra nada."""
    global _listo
    if _listo:
        return
    with _lock:
        if _listo:
            return
        try:  # primero las tablas que los módulos crean solos (finanzas_pagos, inv_movimientos...)
            from routes.multiempresa import asegurar_columnas_empresa
            asegurar_columnas_empresa()
        except Exception:
            pass
        with db_tx() as conn:
            cur = conn.cursor()
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('auditoria_ddl'))")
            cur.execute(SQL_TABLA)
            tipo = _tipo_columna_registro(cur)
            cur.execute(SQL_FUNCION.replace('{REGISTRO}', REGISTRO_TEXTO if tipo == 'text' else REGISTRO_ENTERO))
            for tabla in TABLAS_AUDITADAS:
                cur.execute("SELECT to_regclass(%s) IS NOT NULL", (tabla,))
                if cur.fetchone()[0]:
                    cur.execute(sql_trigger(tabla))
        _listo = True


def _tipo_columna_registro(cur):
    if 'registro_id' not in _tipo_registro:
        cur.execute("""SELECT data_type FROM information_schema.columns WHERE table_schema = current_schema()
                       AND table_name = 'erp_auditoria' AND column_name = 'registro_id'""")
        f = cur.fetchone()
        _tipo_registro['registro_id'] = 'text' if not f or f[0] in ('text', 'character varying') else 'integer'
    return _tipo_registro['registro_id']


# ============================================================
# USUARIO DE LA SESIÓN (para la auditoría y para la base)
# ============================================================
def ip_cliente():
    if not has_request_context():
        return ''
    reenviada = (request.headers.get('X-Forwarded-For') or '').split(',')[0].strip()
    return (reenviada or request.remote_addr or '')[:60]


def usuario_sesion(sin_bd=False):
    """(usuario_id, nombre, empresa_id, empresa_codigo) del usuario conectado, o vacíos.
    sin_bd=True: no consulta la base (se usa DENTRO de get_connection; consultar ahí sería un bucle)."""
    if not has_request_context():
        return None, None, None, None
    uid = session.get('usuario_id')
    nombre = session.get('nombre_completo') or session.get('usuario')
    eid, ecod = None, None
    try:
        from routes import multiempresa
        codigo = (session.get('empresa') or '').upper()
        if sin_bd:
            e = next((x for x in multiempresa._cache.get('filas') or [] if x['codigo'] == codigo), None)
        else:
            e = multiempresa.empresa_actual()
        if e:
            eid, ecod = e['id'], e['codigo']
    except Exception:
        pass
    return uid, nombre, eid, ecod


def datos_usuario_para_bd():
    """Valores para set_config('erp.usuario_id' / 'erp.usuario_nombre' / 'erp.ip' / 'erp.empresa_id').
    Pensado para database.get_connection (ver informe): vacíos si no hay petición web."""
    uid, nombre, eid, _ = usuario_sesion(sin_bd=True)
    return (str(uid or ''), str(nombre or ''), ip_cliente(), str(eid or ''))


SQL_SET_USUARIO = ("SELECT set_config('erp.usuario_id', %s, {l}), set_config('erp.usuario_nombre', %s, {l}), "
                   "set_config('erp.ip', %s, {l}), set_config('erp.empresa_id', %s, {l})")


def marcar_usuario(cur, origen=None):
    """Dentro de una transacción: los disparadores sabrán quién hace el cambio (solo esta transacción)."""
    cur.execute(SQL_SET_USUARIO.format(l='true'), datos_usuario_para_bd())
    if origen:
        cur.execute("SELECT set_config('erp.origen', %s, true)", (origen,))


# ============================================================
# REGISTRO MANUAL (login, logout, herramientas, papelera...)
# ============================================================
def _json(v):
    if v is None:
        return None

    def conv(o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, Decimal):
            return float(o)
        return str(o)
    if isinstance(v, dict):
        v = {k: x for k, x in v.items() if 'password' not in str(k).lower()}
    return json.dumps(v, default=conv, ensure_ascii=False)


def registrar_auditoria(accion, modulo, tabla=None, registro_id=None, antes=None, despues=None, detalle=None,
                        usuario_id=None, usuario_nombre=None, cur=None):
    """Guarda una línea de auditoría. Nunca lanza error (la auditoría no debe romper la operación).
    Con cur= se guarda dentro de la misma transacción (si la operación falla, tampoco queda la auditoría)."""
    try:
        uid, nombre, eid, ecod = usuario_sesion()
        uid = usuario_id if usuario_id is not None else uid
        nombre = usuario_nombre if usuario_nombre is not None else nombre
        params = (str(eid) if eid else None, tabla or modulo, None, accion, _json(antes), _json(despues),
                  uid, nombre, modulo, ecod, ip_cliente() or None, (detalle or '')[:4000] or None)

        def _insertar(c):
            reg = None if registro_id is None else str(registro_id)
            if reg is not None and _tipo_columna_registro(c) != 'text' and not reg.isdigit():
                reg = None
            c.execute("""INSERT INTO erp_auditoria (empresa_id, tabla, registro_id, accion, data_anterior, data_nueva,
                                                    usuario_id, usuario_nombre, modulo, empresa, ip, detalle)
                         VALUES ((SELECT id FROM erp_empresas WHERE id::text = %s LIMIT 1), %s, %s, %s, %s, %s,
                                 %s, %s, %s, %s, %s, %s)""", params[:2] + (reg,) + params[3:])
        if cur is not None:
            cur.execute("SAVEPOINT sp_auditoria")
            try:
                _insertar(cur)
                cur.execute("RELEASE SAVEPOINT sp_auditoria")
            except Exception:
                cur.execute("ROLLBACK TO SAVEPOINT sp_auditoria")
                raise
            return True
        asegurar_auditoria()
        with db_tx() as conn:
            _insertar(conn.cursor())
        return True
    except Exception as e:
        print(f'⚠️ No se pudo registrar la auditoría ({accion}): {e}')
        return False
