-- ============================================================================
-- 008 - Corrección de los 13 errores (16/10/2026) - ERP_KCF
-- ============================================================================
-- ESTADO: YA APLICADA en Supabase el 16/10/2026 (migraciones 008a_respaldo_pre008 y
--         008b_stock_hora_lima_columnas). Este archivo es la copia documentada.
--
-- Qué hace (en simple). Solo AGREGA; no toca lo del 15/10 (RLS, stock automático, multiempresa):
--   1. Columna pedido_compra_pc.valida_productos (el interruptor "Valida productos" de la PC
--      no se guardaba) y productos.tipo_operacion (Venta / Compra / Inventariable).
--   2. productos.stock pasa a ser SIEMPRE la suma de inv_stock (todas las empresas y sedes),
--      con dos disparadores: cuando cambia inv_stock se recalcula el producto, y si alguien
--      escribe productos.stock a mano en un producto que está en Inventario, se corrige solo.
--   3. La base trabaja en hora de Lima (America/Lima) en vez de UTC.
--   4. Las fechas-hora ya guardadas (columnas de auditoría y todas las de inventario/kardex)
--      se pasan de UTC a hora de Lima restando 5 horas. Solo se hace UNA vez (marca en
--      respaldo_20261015.marca_hora_lima_008).
--   NO borra nada.
--
-- RESPALDO PREVIO (008a): 46 tablas copiadas a respaldo_20261015.<tabla>_pre008
--   (todas las que tienen fechas-hora que se movieron, más erp_usuario_permisos y erp_rol_permisos).
-- ============================================================================

-- 0) Respaldo (008a)
DO $$
DECLARE t text;
BEGIN
  FOR t IN
    SELECT DISTINCT c.table_name FROM information_schema.columns c
    JOIN information_schema.tables tb ON tb.table_schema=c.table_schema AND tb.table_name=c.table_name AND tb.table_type='BASE TABLE'
    WHERE c.table_schema='public' AND c.data_type='timestamp without time zone'
      AND (c.column_name IN ('created_at','updated_at','fecha_creacion','creado_en','eliminado_en') OR c.table_name LIKE 'inv\_%')
    UNION SELECT 'erp_usuario_permisos' UNION SELECT 'erp_rol_permisos'
  LOOP
    IF to_regclass('respaldo_20261015.'||t||'_pre008') IS NULL THEN
      EXECUTE format('CREATE TABLE respaldo_20261015.%I AS TABLE public.%I', t||'_pre008', t);
    END IF;
  END LOOP;
END $$;

-- 1..4) Cambios (008b)
-- 1) Columnas nuevas (solo AGREGA)
ALTER TABLE public.pedido_compra_pc ADD COLUMN IF NOT EXISTS valida_productos BOOLEAN;
ALTER TABLE public.productos ADD COLUMN IF NOT EXISTS tipo_operacion VARCHAR(60);

-- 2) productos.stock = suma de inv_stock (siempre)
CREATE OR REPLACE FUNCTION fn_recalcular_stock_producto(p_id INTEGER) RETURNS void
LANGUAGE sql SET search_path = public AS $f$
    UPDATE productos SET stock = (SELECT COALESCE(SUM(cantidad), 0) FROM inv_stock WHERE producto_id = p_id)
    WHERE id = p_id;
$f$;
CREATE OR REPLACE FUNCTION fn_inv_stock_sync_productos() RETURNS trigger
LANGUAGE plpgsql SET search_path = public AS $f$
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        PERFORM fn_recalcular_stock_producto(OLD.producto_id);
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        PERFORM fn_recalcular_stock_producto(NEW.producto_id);
    END IF;
    RETURN NULL;
END $f$;
CREATE OR REPLACE TRIGGER trg_inv_stock_sync_productos
    AFTER INSERT OR UPDATE OF cantidad, producto_id OR DELETE ON inv_stock
    FOR EACH ROW EXECUTE FUNCTION fn_inv_stock_sync_productos();
CREATE OR REPLACE FUNCTION fn_productos_stock_desde_inventario() RETURNS trigger
LANGUAGE plpgsql SET search_path = public AS $f$
BEGIN
    -- Si el producto ya está en Inventario, su stock no se escribe a mano: es la suma de inv_stock
    IF EXISTS (SELECT 1 FROM inv_stock WHERE producto_id = NEW.id) THEN
        NEW.stock := (SELECT COALESCE(SUM(cantidad), 0) FROM inv_stock WHERE producto_id = NEW.id);
    END IF;
    RETURN NEW;
END $f$;
CREATE OR REPLACE TRIGGER trg_productos_stock_desde_inventario
    BEFORE INSERT OR UPDATE OF stock ON productos
    FOR EACH ROW EXECUTE FUNCTION fn_productos_stock_desde_inventario();
UPDATE public.productos p SET stock = s.total
  FROM (SELECT producto_id, COALESCE(SUM(cantidad),0) total FROM public.inv_stock GROUP BY producto_id) s
 WHERE s.producto_id = p.id AND COALESCE(p.stock,0) <> s.total;

-- 3) Hora de Lima: las conexiones nuevas trabajan en America/Lima
ALTER ROLE postgres SET timezone = 'America/Lima';

-- 4) Pasar a hora de Lima (-5 h) las fechas-hora guardadas en UTC
--    (columnas de auditoría y todas las de inventario/kardex; las de tipo DATE no se tocan,
--     las de tipo "timestamp with time zone" tampoco porque ya guardan la zona)
DO $$
DECLARE r record; cols text;
BEGIN
  -- Solo una vez: si ya se hizo, existe la marca y no se vuelve a restar
  IF to_regclass('respaldo_20261015.marca_hora_lima_008') IS NOT NULL THEN
    RAISE NOTICE 'Las horas ya estaban en hora de Lima; no se cambia nada.';
    RETURN;
  END IF;
  CREATE TABLE respaldo_20261015.marca_hora_lima_008 (hecho_en timestamptz DEFAULT now());
  INSERT INTO respaldo_20261015.marca_hora_lima_008 DEFAULT VALUES;
  FOR r IN
    SELECT c.table_name, array_agg(c.column_name::text ORDER BY c.column_name) cs
      FROM information_schema.columns c
      JOIN information_schema.tables t ON t.table_schema=c.table_schema AND t.table_name=c.table_name AND t.table_type='BASE TABLE'
     WHERE c.table_schema='public' AND c.data_type='timestamp without time zone'
       AND (c.column_name IN ('created_at','updated_at','fecha_creacion','creado_en','eliminado_en') OR c.table_name LIKE 'inv\_%')
     GROUP BY c.table_name
  LOOP
    SELECT string_agg(format('%I = %I - interval ''5 hours''', x, x), ', ') INTO cols FROM unnest(r.cs) x;
    EXECUTE format('ALTER TABLE public.%I DISABLE TRIGGER USER', r.table_name);
    EXECUTE format('UPDATE public.%I SET %s', r.table_name, cols);
    EXECUTE format('ALTER TABLE public.%I ENABLE TRIGGER USER', r.table_name);
  END LOOP;
END $$;


-- 5) Usuario del ERP para la cuenta de acceso armando@kcf.com (se hizo aparte, 16/10/2026):
--    usuario arm01kcf, rol vendedor, INACTIVO (id 46). La contraseña temporal se entregó a Erika
--    por el hilo y aquí NO aparece. Para crear otros, usar Configuración ▸ Usuarios ▸
--    "Cuentas de acceso sin usuario del ERP" (genera la contraseña y la muestra una sola vez).

-- ============================================================================
-- CÓMO DESHACER (en el SQL Editor de Supabase, en este orden)
-- ============================================================================
-- a) Volver las horas a UTC (sumar 5 h) - solo si se quiere regresar a como estaba:
-- DO $$ DECLARE r record; cols text; BEGIN
--   FOR r IN SELECT c.table_name, array_agg(c.column_name::text) cs FROM information_schema.columns c
--     JOIN information_schema.tables t ON t.table_schema=c.table_schema AND t.table_name=c.table_name AND t.table_type='BASE TABLE'
--     WHERE c.table_schema='public' AND c.data_type='timestamp without time zone'
--       AND (c.column_name IN ('created_at','updated_at','fecha_creacion','creado_en','eliminado_en') OR c.table_name LIKE 'inv\_%')
--     GROUP BY c.table_name
--   LOOP
--     SELECT string_agg(format('%I = %I + interval ''5 hours''', x, x), ', ') INTO cols FROM unnest(r.cs) x;
--     EXECUTE format('ALTER TABLE public.%I DISABLE TRIGGER USER', r.table_name);
--     EXECUTE format('UPDATE public.%I SET %s', r.table_name, cols);
--     EXECUTE format('ALTER TABLE public.%I ENABLE TRIGGER USER', r.table_name);
--   END LOOP;
--   DROP TABLE respaldo_20261015.marca_hora_lima_008;
-- END $$;
-- b) ALTER ROLE postgres RESET timezone;
-- c) DROP TRIGGER trg_productos_stock_desde_inventario ON public.productos;
--    DROP TRIGGER trg_inv_stock_sync_productos ON public.inv_stock;
--    DROP FUNCTION fn_productos_stock_desde_inventario(); DROP FUNCTION fn_inv_stock_sync_productos();
--    DROP FUNCTION fn_recalcular_stock_producto(integer);
--    (el ERP los vuelve a crear al arrancar; para quitarlos del todo hay que usar el ZIP anterior)
-- d) ALTER TABLE public.pedido_compra_pc DROP COLUMN valida_productos;
--    ALTER TABLE public.productos DROP COLUMN tipo_operacion;
-- e) Usuario arm01kcf: DELETE FROM public.usuarios WHERE usuario_sistema = 'arm01kcf';
-- f) Cualquier tabla se puede devolver tal cual estaba con su copia:
--    respaldo_20261015.<tabla>_pre008
-- ============================================================================
