-- =====================================================================================
-- SUPABASE 010 · Proveedores (no borrar con historial) + vencimientos + fecha de modificación
-- Aplicado en Supabase (ERP_KCF) el 19/10/2026 por Claude, con la autorización escrita de Erika
-- ("AUTORIZACIÓN TOTAL SUPABASE", 19/10/2026).
-- SOLO AGREGA: 2 columnas, 1 función, 9 disparadores, 2 llaves foráneas (RESTRICT) y 3 índices.
-- No borra ni cambia ningún dato. No toca 005, 006, 007, 008 ni 009. Se puede correr varias veces.
--
-- RESPALDO tomado ANTES de aplicar (esquema respaldo_20261015):
--   proveedores_pre010 (49 filas), productos_pre010 (29), ordenes_compra_pre010 (10), costos_productos_pre010 (17).
--
-- VERIFICADO DESPUÉS: conteos iguales antes y después (38 cotizaciones, 48 clientes, 49 proveedores, 29 productos,
--   20 PC, 21 despachos, 18 guías, 22 comprobantes, 2 NC, 10 OC, 18 stock, 33 movimientos, 7 usuarios, 17 costos),
--   stock cuadrado (0 diferencias), 2 llaves validadas (0 registros huérfanos), 9 disparadores.
--   Prueba del disparador dentro de una transacción deshecha: al modificar un proveedor, updated_at quedó con la hora de Lima.
-- =====================================================================================
BEGIN;

-- ============================================================
-- 1) PRODUCTOS: fecha de vencimiento (consumibles, químicos). Vacía = no vence.
--    El ERP avisa en Inventario ▸ Vencimientos: amarillo 6 meses antes, rojo 3 meses antes.
--    (Cada lote ya podía tener su fecha en inv_movimientos.fecha_vencimiento; esta es la de la ficha.)
-- ============================================================
ALTER TABLE public.productos ADD COLUMN IF NOT EXISTS fecha_vencimiento DATE;
COMMENT ON COLUMN public.productos.fecha_vencimiento IS 'Fecha de vencimiento del producto (19/10/2026). NULL = no vence.';
CREATE INDEX IF NOT EXISTS idx_productos_fecha_vencimiento ON public.productos (fecha_vencimiento) WHERE fecha_vencimiento IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_inv_mov_fecha_vencimiento ON public.inv_movimientos (producto_id, fecha_vencimiento) WHERE fecha_vencimiento IS NOT NULL;

-- ============================================================
-- 2) PROVEEDORES: fecha y hora de la última modificación (no la tenía).
-- ============================================================
-- Los proveedores que ya existen quedan con la columna vacía (se llena en su próxima modificación):
-- así no se inventa una fecha ni se llena la auditoría con 49 cambios falsos.
ALTER TABLE public.proveedores ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;
ALTER TABLE public.proveedores ALTER COLUMN updated_at SET DEFAULT NOW();

-- ============================================================
-- 3) "Última modificación" siempre al día: al cambiar un registro, la base pone updated_at = ahora (hora de Lima).
--    Solo en tablas que tienen updated_at y que aún no tenían este disparador.
--    (guias_remision y ordenes_compra ya tenían el suyo; productos no se toca porque su stock cambia solo.)
-- ============================================================
CREATE OR REPLACE FUNCTION public.fn_tocar_updated_at() RETURNS trigger
LANGUAGE plpgsql SET search_path = public AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['clientes', 'proveedores', 'cotizaciones', 'pedido_compra_pc', 'despachos', 'comprobantes',
                             'notas_credito', 'solicitudes_compra', 'comprobantes_proveedor'] LOOP
        IF EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = t AND column_name = 'updated_at') THEN
            IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_tocar_updated_at'
                           AND tgrelid = format('public.%I', t)::regclass) THEN
            EXECUTE format('CREATE TRIGGER trg_tocar_updated_at BEFORE UPDATE ON public.%I '
                           'FOR EACH ROW EXECUTE FUNCTION public.fn_tocar_updated_at()', t);
            END IF;
        END IF;
    END LOOP;
END $$;

-- ============================================================
-- 4) INTEGRIDAD: un proveedor que tiene órdenes de compra o costos registrados ya no se puede borrar
--    por error (antes solo productos lo impedía y las OC quedaban "huérfanas").
--    ON DELETE RESTRICT = la base no deja borrar; el ERP muestra el mensaje y ofrece "Desactivar proveedor".
--    Se revisó antes: 0 órdenes y 0 costos con proveedor inexistente, así que se validan completas.
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ordenes_compra_proveedor_id_fkey') THEN
        ALTER TABLE public.ordenes_compra ADD CONSTRAINT ordenes_compra_proveedor_id_fkey
            FOREIGN KEY (proveedor_id) REFERENCES public.proveedores(id) ON DELETE RESTRICT NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.ordenes_compra o WHERE o.proveedor_id IS NOT NULL
                   AND NOT EXISTS (SELECT 1 FROM public.proveedores p WHERE p.id = o.proveedor_id)) THEN
        ALTER TABLE public.ordenes_compra VALIDATE CONSTRAINT ordenes_compra_proveedor_id_fkey;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'costos_productos_proveedor_id_fkey') THEN
        ALTER TABLE public.costos_productos ADD CONSTRAINT costos_productos_proveedor_id_fkey
            FOREIGN KEY (proveedor_id) REFERENCES public.proveedores(id) ON DELETE RESTRICT NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.costos_productos c WHERE c.proveedor_id IS NOT NULL
                   AND NOT EXISTS (SELECT 1 FROM public.proveedores p WHERE p.id = c.proveedor_id)) THEN
        ALTER TABLE public.costos_productos VALIDATE CONSTRAINT costos_productos_proveedor_id_fkey;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_costos_productos_proveedor ON public.costos_productos (proveedor_id);

COMMIT;

-- =====================================================================================
-- CÓMO DESHACER (en el SQL Editor de Supabase; no borra datos de negocio):
--   DROP TRIGGER IF EXISTS trg_tocar_updated_at ON public.clientes;            -- repetir para: proveedores, cotizaciones,
--     pedido_compra_pc, despachos, comprobantes, notas_credito, solicitudes_compra, comprobantes_proveedor
--   DROP FUNCTION IF EXISTS public.fn_tocar_updated_at();
--   ALTER TABLE public.ordenes_compra DROP CONSTRAINT IF EXISTS ordenes_compra_proveedor_id_fkey;
--   ALTER TABLE public.costos_productos DROP CONSTRAINT IF EXISTS costos_productos_proveedor_id_fkey;
--   DROP INDEX IF EXISTS idx_productos_fecha_vencimiento, idx_inv_mov_fecha_vencimiento, idx_costos_productos_proveedor;
--   -- Las columnas nuevas se pueden dejar (el ERP anterior no las usa). Si igual se quieren quitar:
--   -- ALTER TABLE public.productos DROP COLUMN IF EXISTS fecha_vencimiento;   (se pierden las fechas que hayan anotado)
--   -- ALTER TABLE public.proveedores DROP COLUMN IF EXISTS updated_at;
-- =====================================================================================
