-- =====================================================================================
-- SUPABASE 009 · Compras + Reportes + Herramientas + Papelera/Auditoría + entrega por producto
-- Aplicado en Supabase (ERP_KCF) el 16/10/2026 por Claude, con la autorización escrita de Erika.
-- SOLO AGREGA: columnas, una tabla (com_anulaciones), índices, una función y 17 disparadores de auditoría.
-- No borra ni cambia ningún dato. No toca lo de 005, 006, 007 ni 008. Se puede correr varias veces.
--
-- RESPALDO tomado ANTES de aplicar (esquema respaldo_20261015):
--   ordenes_compra_pre009 (5 filas), ordenes_compra_items_pre009 (4), cotizacion_detalle_pre009 (63),
--   erp_auditoria_pre009 (0).
--
-- VERIFICADO DESPUÉS: 17 disparadores, 13 columnas nuevas, conteos iguales (36 cotizaciones, 45 clientes,
--   46 proveedores, 26 productos, 18 PC, 20 despachos, 17 guías, 21 comprobantes, 2 NC, 5 OC, 14 stock,
--   25 movimientos, 245 permisos, 7 usuarios), stock cuadrado (0 diferencias).
--   Prueba del disparador dentro de una transacción deshecha: guardó "editar / Maestros · Clientes" con el usuario.
--
-- Reportes no necesitó cambios en la base (solo lee).
-- =====================================================================================

BEGIN;

-- Ventas (17/10/2026): estado de entrega por producto de la cotización.
-- Solo dos valores: 'Pendiente' (por defecto) o 'Entregado'. No cambia datos existentes
-- (las líneas antiguas quedan en 'Pendiente').
ALTER TABLE public.cotizacion_detalle ADD COLUMN IF NOT EXISTS estado_entrega VARCHAR(20) DEFAULT 'Pendiente';


-- ============================================================
-- mig009 / COMPRAS  (16/10/2026)
-- Lo mismo que hace solo el ERP al arrancar (routes/compras_flujo.py, asegurar_tablas_compras()).
-- Solo AGREGA columnas y una tabla. No borra ni cambia datos. Se puede correr varias veces.
-- ============================================================

-- 1) La OC guarda para qué pedido del cliente (PC), cotización y cliente es (solo vista interna;
--    la hoja que se manda al proveedor NUNCA muestra estos datos).
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS pedido_id INTEGER;              -- primer PC de la OC
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS pc_numeros TEXT;                -- PC-... (si hay varios, separados por coma)
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS cotizaciones_cliente TEXT;      -- cotización al cliente (COT-...)
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS clientes_pedido TEXT;           -- nombre del cliente
ALTER TABLE ordenes_compra_items ADD COLUMN IF NOT EXISTS cotizacion_numero VARCHAR(60);

-- 2) Compra SIN pedido: motivo obligatorio elegido de una lista
--    (Stock estratégico, Crédito fiscal / IGV, Reposición de stock mínimo, Otro). El detalle va en motivo_stock (ya existe).
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS motivo_compra VARCHAR(60);

-- 3) Candados: cada anulación o eliminación en Compras queda registrada con quién, cuándo, por qué
--    y una copia (respaldo) del documento.
CREATE TABLE IF NOT EXISTS com_anulaciones (
    id SERIAL PRIMARY KEY,
    fecha TIMESTAMP NOT NULL DEFAULT NOW(),
    tabla VARCHAR(40) NOT NULL,          -- ordenes_compra, solicitudes_compra, comprobantes_proveedor
    registro_id INTEGER NOT NULL,
    numero VARCHAR(60),
    accion VARCHAR(20) NOT NULL,         -- Anulada / Anulado / Eliminada
    motivo TEXT NOT NULL,
    usuario_id INTEGER,
    usuario VARCHAR(150),
    respaldo JSONB
);
CREATE INDEX IF NOT EXISTS idx_com_anul_tabla ON com_anulaciones (tabla, registro_id);


-- ============================================================
-- CÓMO DESHACER (solo si hiciera falta; primero saca un respaldo).
-- Ojo: borrar estas columnas borra la información de PC/cliente/motivo de las OC y el registro de anulaciones.
-- ============================================================
-- BEGIN;
-- DROP INDEX IF EXISTS idx_com_anul_tabla;
-- DROP TABLE IF EXISTS com_anulaciones;
-- ALTER TABLE ordenes_compra DROP COLUMN IF EXISTS motivo_compra;
-- ALTER TABLE ordenes_compra_items DROP COLUMN IF EXISTS cotizacion_numero;
-- ALTER TABLE ordenes_compra DROP COLUMN IF EXISTS clientes_pedido;
-- ALTER TABLE ordenes_compra DROP COLUMN IF EXISTS cotizaciones_cliente;
-- ALTER TABLE ordenes_compra DROP COLUMN IF EXISTS pc_numeros;
-- ALTER TABLE ordenes_compra DROP COLUMN IF EXISTS pedido_id;
-- COMMIT;

ALTER TABLE public.com_anulaciones ENABLE ROW LEVEL SECURITY;

-- =====================================================================================
-- mig009 / auditoria_papelera.sql  —  Módulos 9 "Herramientas" y 10 "Papelera / Auditoría"
-- (pedido de Erika, 16/10/2026: "TRAZABILIDAD PARA TODO")
--
-- QUÉ HACE (en simple):
--   1. A la tabla de auditoría que YA existe (erp_auditoria) le agrega 6 columnas:
--      usuario_id, usuario_nombre, modulo, empresa, ip, detalle. No borra ni cambia nada de lo que ya hay.
--   2. Crea la función fn_erp_auditoria(): cada vez que alguien crea, edita, anula, aprueba o borra un registro
--      en las tablas de negocio, guarda una línea en erp_auditoria con cómo estaba ANTES y cómo quedó DESPUÉS.
--      - Las contraseñas (columna password) NUNCA se guardan.
--      - Si guardar la auditoría falla, la operación del usuario sigue normal (no se bloquea nada).
--      - El usuario sale de set_config('erp.usuario_id' / 'erp.usuario_nombre') que pone la aplicación;
--        si no viene, se usa el que el propio registro tenga (usuario_id, creado_por, eliminado_por...).
--   3. Pone el disparador trg_erp_auditoria en 17 tablas (solo las que existan).
--
-- La aplicación hace lo mismo sola al primer uso (routes/auditoria.py, asegurar_auditoria()).
-- Se puede ejecutar varias veces sin problema. Antes de aplicarlo en Supabase: sacar respaldo.
-- Requiere PostgreSQL 14 o más (CREATE OR REPLACE TRIGGER). Supabase usa 15.
-- =====================================================================================


-- 1) Tabla y columnas nuevas (solo si faltan)
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

    ALTER TABLE erp_auditoria ADD COLUMN IF NOT EXISTS usuario_id INTEGER;
    ALTER TABLE erp_auditoria ADD COLUMN IF NOT EXISTS usuario_nombre TEXT;
    ALTER TABLE erp_auditoria ADD COLUMN IF NOT EXISTS modulo TEXT;
    ALTER TABLE erp_auditoria ADD COLUMN IF NOT EXISTS empresa TEXT;
    ALTER TABLE erp_auditoria ADD COLUMN IF NOT EXISTS ip TEXT;
    ALTER TABLE erp_auditoria ADD COLUMN IF NOT EXISTS detalle TEXT;
    CREATE INDEX IF NOT EXISTS idx_erp_auditoria_fecha ON erp_auditoria (created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_erp_auditoria_registro ON erp_auditoria (tabla, registro_id);
    CREATE INDEX IF NOT EXISTS idx_erp_auditoria_accion ON erp_auditoria (accion);

-- 2) Función de auditoría (registro_id es TEXT en Supabase)
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
                TG_TABLE_NAME, v_id, v_accion, v_old, v_new,
                v_uid::integer, v_unom, v_modulo,
                (SELECT upper(e.codigo) FROM erp_empresas e WHERE e.id::text = v_emp LIMIT 1),
                NULLIF(current_setting('erp.ip', true), ''), v_detalle);
    EXCEPTION WHEN OTHERS THEN
        -- La auditoría nunca bloquea la operación del usuario
        RAISE WARNING 'auditoria (%): %', TG_TABLE_NAME, SQLERRM;
    END;
    RETURN NULL;
END $f$;

-- 3) Disparadores en las tablas de negocio (solo las que existen)
DO $do$
BEGIN
    IF to_regclass('public.cotizaciones') IS NOT NULL THEN
        EXECUTE $t$CREATE OR REPLACE TRIGGER trg_erp_auditoria AFTER INSERT OR UPDATE OR DELETE ON cotizaciones FOR EACH ROW EXECUTE FUNCTION fn_erp_auditoria('Ventas · Cotizaciones', 'updated_at');$t$;
    END IF;
    IF to_regclass('public.pedido_compra_pc') IS NOT NULL THEN
        EXECUTE $t$CREATE OR REPLACE TRIGGER trg_erp_auditoria AFTER INSERT OR UPDATE OR DELETE ON pedido_compra_pc FOR EACH ROW EXECUTE FUNCTION fn_erp_auditoria('Ventas · Pedidos (PC)', 'updated_at');$t$;
    END IF;
    IF to_regclass('public.despachos') IS NOT NULL THEN
        EXECUTE $t$CREATE OR REPLACE TRIGGER trg_erp_auditoria AFTER INSERT OR UPDATE OR DELETE ON despachos FOR EACH ROW EXECUTE FUNCTION fn_erp_auditoria('Ventas · Despachos', 'updated_at');$t$;
    END IF;
    IF to_regclass('public.guias_remision') IS NOT NULL THEN
        EXECUTE $t$CREATE OR REPLACE TRIGGER trg_erp_auditoria AFTER INSERT OR UPDATE OR DELETE ON guias_remision FOR EACH ROW EXECUTE FUNCTION fn_erp_auditoria('Ventas · Guías', 'updated_at');$t$;
    END IF;
    IF to_regclass('public.comprobantes') IS NOT NULL THEN
        EXECUTE $t$CREATE OR REPLACE TRIGGER trg_erp_auditoria AFTER INSERT OR UPDATE OR DELETE ON comprobantes FOR EACH ROW EXECUTE FUNCTION fn_erp_auditoria('Ventas · Facturas', 'updated_at');$t$;
    END IF;
    IF to_regclass('public.notas_credito') IS NOT NULL THEN
        EXECUTE $t$CREATE OR REPLACE TRIGGER trg_erp_auditoria AFTER INSERT OR UPDATE OR DELETE ON notas_credito FOR EACH ROW EXECUTE FUNCTION fn_erp_auditoria('Ventas · Notas de crédito', 'updated_at');$t$;
    END IF;
    IF to_regclass('public.devoluciones') IS NOT NULL THEN
        EXECUTE $t$CREATE OR REPLACE TRIGGER trg_erp_auditoria AFTER INSERT OR UPDATE OR DELETE ON devoluciones FOR EACH ROW EXECUTE FUNCTION fn_erp_auditoria('Ventas · Devoluciones', 'updated_at');$t$;
    END IF;
    IF to_regclass('public.ordenes_compra') IS NOT NULL THEN
        EXECUTE $t$CREATE OR REPLACE TRIGGER trg_erp_auditoria AFTER INSERT OR UPDATE OR DELETE ON ordenes_compra FOR EACH ROW EXECUTE FUNCTION fn_erp_auditoria('Compras · Órdenes de compra', 'updated_at');$t$;
    END IF;
    IF to_regclass('public.solicitudes_compra') IS NOT NULL THEN
        EXECUTE $t$CREATE OR REPLACE TRIGGER trg_erp_auditoria AFTER INSERT OR UPDATE OR DELETE ON solicitudes_compra FOR EACH ROW EXECUTE FUNCTION fn_erp_auditoria('Compras · Solicitudes', 'updated_at');$t$;
    END IF;
    IF to_regclass('public.comprobantes_proveedor') IS NOT NULL THEN
        EXECUTE $t$CREATE OR REPLACE TRIGGER trg_erp_auditoria AFTER INSERT OR UPDATE OR DELETE ON comprobantes_proveedor FOR EACH ROW EXECUTE FUNCTION fn_erp_auditoria('Compras · Facturas de proveedor', 'updated_at');$t$;
    END IF;
    IF to_regclass('public.productos') IS NOT NULL THEN
        EXECUTE $t$CREATE OR REPLACE TRIGGER trg_erp_auditoria AFTER INSERT OR UPDATE OR DELETE ON productos FOR EACH ROW EXECUTE FUNCTION fn_erp_auditoria('Maestros · Productos', 'updated_at,stock');$t$;
    END IF;
    IF to_regclass('public.clientes') IS NOT NULL THEN
        EXECUTE $t$CREATE OR REPLACE TRIGGER trg_erp_auditoria AFTER INSERT OR UPDATE OR DELETE ON clientes FOR EACH ROW EXECUTE FUNCTION fn_erp_auditoria('Maestros · Clientes', 'updated_at');$t$;
    END IF;
    IF to_regclass('public.proveedores') IS NOT NULL THEN
        EXECUTE $t$CREATE OR REPLACE TRIGGER trg_erp_auditoria AFTER INSERT OR UPDATE OR DELETE ON proveedores FOR EACH ROW EXECUTE FUNCTION fn_erp_auditoria('Maestros · Proveedores', 'updated_at');$t$;
    END IF;
    IF to_regclass('public.inv_movimientos') IS NOT NULL THEN
        EXECUTE $t$CREATE OR REPLACE TRIGGER trg_erp_auditoria AFTER INSERT OR UPDATE OR DELETE ON inv_movimientos FOR EACH ROW EXECUTE FUNCTION fn_erp_auditoria('Inventario · Movimientos', 'updated_at');$t$;
    END IF;
    IF to_regclass('public.usuarios') IS NOT NULL THEN
        EXECUTE $t$CREATE OR REPLACE TRIGGER trg_erp_auditoria AFTER INSERT OR UPDATE OR DELETE ON usuarios FOR EACH ROW EXECUTE FUNCTION fn_erp_auditoria('Configuración · Usuarios', 'updated_at');$t$;
    END IF;
    IF to_regclass('public.erp_usuario_permisos') IS NOT NULL THEN
        EXECUTE $t$CREATE OR REPLACE TRIGGER trg_erp_auditoria AFTER INSERT OR UPDATE OR DELETE ON erp_usuario_permisos FOR EACH ROW EXECUTE FUNCTION fn_erp_auditoria('Configuración · Permisos', 'updated_at');$t$;
    END IF;
    IF to_regclass('public.finanzas_pagos') IS NOT NULL THEN
        EXECUTE $t$CREATE OR REPLACE TRIGGER trg_erp_auditoria AFTER INSERT OR UPDATE OR DELETE ON finanzas_pagos FOR EACH ROW EXECUTE FUNCTION fn_erp_auditoria('Finanzas · Cobros y pagos', 'updated_at');$t$;
    END IF;
END
$do$;


-- =====================================================================================
-- CÓMO DESHACER (no borra los datos de auditoría ya guardados)
-- =====================================================================================
-- Para dejar de auditar (quitar los disparadores y la función):
--   DO $do$ DECLARE t text; BEGIN
--     FOREACH t IN ARRAY ARRAY['cotizaciones', 'pedido_compra_pc', 'despachos', 'guias_remision', 'comprobantes', 'notas_credito', 'devoluciones', 'ordenes_compra', 'solicitudes_compra', 'comprobantes_proveedor', 'productos', 'clientes', 'proveedores', 'inv_movimientos', 'usuarios', 'erp_usuario_permisos', 'finanzas_pagos'] LOOP
--       IF to_regclass('public.' || t) IS NOT NULL THEN
--         EXECUTE format('DROP TRIGGER IF EXISTS trg_erp_auditoria ON %I', t);
--       END IF;
--     END LOOP; END $do$;
--   DROP FUNCTION IF EXISTS fn_erp_auditoria();
-- Para apagar la auditoría solo en una sesión (por ejemplo, una carga masiva):  SET erp.auditoria_off = '1';
-- Las columnas nuevas de erp_auditoria (usuario_id, usuario_nombre, modulo, empresa, ip, detalle) se pueden dejar:
-- no molestan. Si de verdad hay que quitarlas (se pierde esa información):
--   ALTER TABLE erp_auditoria DROP COLUMN IF EXISTS usuario_id, DROP COLUMN IF EXISTS usuario_nombre,
--     DROP COLUMN IF EXISTS modulo, DROP COLUMN IF EXISTS empresa, DROP COLUMN IF EXISTS ip, DROP COLUMN IF EXISTS detalle;
-- Los índices nuevos: DROP INDEX IF EXISTS idx_erp_auditoria_fecha, idx_erp_auditoria_registro, idx_erp_auditoria_accion;

COMMIT;


-- =====================================================================================
-- CÓMO DESHACER TODO EL 009 (en este orden; los datos de negocio no se tocan)
-- =====================================================================================
-- 1) Quitar la auditoría automática (lo ya auditado se puede conservar):
-- DO $do$ DECLARE t text; BEGIN
--   FOREACH t IN ARRAY ARRAY['cotizaciones','pedido_compra_pc','despachos','guias_remision','comprobantes','notas_credito',
--     'devoluciones','ordenes_compra','solicitudes_compra','comprobantes_proveedor','productos','clientes','proveedores',
--     'inv_movimientos','usuarios','erp_usuario_permisos','finanzas_pagos'] LOOP
--     IF to_regclass('public.' || t) IS NOT NULL THEN EXECUTE format('DROP TRIGGER IF EXISTS trg_erp_auditoria ON %I', t); END IF;
--   END LOOP; END $do$;
-- DROP FUNCTION IF EXISTS fn_erp_auditoria();
-- 2) (Opcional, se pierde esa información) columnas nuevas de erp_auditoria:
-- ALTER TABLE erp_auditoria DROP COLUMN IF EXISTS usuario_id, DROP COLUMN IF EXISTS usuario_nombre, DROP COLUMN IF EXISTS modulo,
--   DROP COLUMN IF EXISTS empresa, DROP COLUMN IF EXISTS ip, DROP COLUMN IF EXISTS detalle;
-- DROP INDEX IF EXISTS idx_erp_auditoria_fecha, idx_erp_auditoria_registro, idx_erp_auditoria_accion;
-- 3) Compras (se pierde el PC/cliente/motivo de las OC y el registro de anulaciones):
-- DROP TABLE IF EXISTS com_anulaciones;
-- ALTER TABLE ordenes_compra DROP COLUMN IF EXISTS motivo_compra, DROP COLUMN IF EXISTS clientes_pedido,
--   DROP COLUMN IF EXISTS cotizaciones_cliente, DROP COLUMN IF EXISTS pc_numeros, DROP COLUMN IF EXISTS pedido_id;
-- ALTER TABLE ordenes_compra_items DROP COLUMN IF EXISTS cotizacion_numero;
-- 4) Ventas: ALTER TABLE cotizacion_detalle DROP COLUMN IF EXISTS estado_entrega;
-- 5) Los respaldos *_pre009 se pueden borrar cuando todo esté bien:
-- DROP TABLE respaldo_20261015.ordenes_compra_pre009, respaldo_20261015.ordenes_compra_items_pre009,
--   respaldo_20261015.cotizacion_detalle_pre009, respaldo_20261015.erp_auditoria_pre009;

-- =====================================================================================
-- OPCIONAL, PARA PEGAR EN EL SQL EDITOR DE SUPABASE (desde aquí la herramienta se cuelga con DROP):
-- 3 índices repetidos en ordenes_compra (hacen lo mismo que idx_ordenes_compra_estado,
-- idx_ordenes_compra_fecha_creacion e idx_ordenes_compra_proveedor_id). No borra datos.
-- =====================================================================================
-- DROP INDEX IF EXISTS public.idx_ordenes_estado, public.idx_ordenes_fecha, public.idx_ordenes_proveedor;
-- Para deshacerlo:
-- CREATE INDEX idx_ordenes_estado ON public.ordenes_compra (estado);
-- CREATE INDEX idx_ordenes_fecha ON public.ordenes_compra (fecha_creacion);
-- CREATE INDEX idx_ordenes_proveedor ON public.ordenes_compra (proveedor_id);
