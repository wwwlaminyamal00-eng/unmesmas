-- ============================================================================
-- 006 - Stock automático: Ventas ↔ Inventario ↔ Compras ↔ Caja (ERP_KCF)
-- ============================================================================
-- ESTADO: APLICADO en Supabase el 15/10/2026 con la autorización escrita de Erika (SUPABASE.txt).
--
-- Qué hace (en simple): solo AGREGA columnas vacías. No borra ni cambia datos.
--   despachos.stock_empresa_id / stock_almacen_id : de qué empresa y sede salió la mercadería
--   despachos.stock_estado   : 'Descontado' cuando el stock salió, 'Revertido' si se anuló
--   despachos.stock_detalle  : qué movimientos del kardex y qué separaciones usó (para poder devolverlo)
--   despachos.stock_fecha    : cuándo
--   inv_movimientos.despacho_id : cada salida del kardex sabe de qué despacho es
-- La lógica está en el código (routes/stock_automatico.py). El ERP también crea estas columnas solo
-- si no existen, así que este script es el respaldo.
-- ============================================================================

ALTER TABLE public.despachos ADD COLUMN IF NOT EXISTS stock_empresa_id UUID;   -- mismo tipo que erp_empresas.id
ALTER TABLE public.despachos ADD COLUMN IF NOT EXISTS stock_almacen_id INTEGER;
ALTER TABLE public.despachos ADD COLUMN IF NOT EXISTS stock_estado VARCHAR(20);
ALTER TABLE public.despachos ADD COLUMN IF NOT EXISTS stock_detalle JSONB;
ALTER TABLE public.despachos ADD COLUMN IF NOT EXISTS stock_fecha TIMESTAMP;
ALTER TABLE public.inv_movimientos ADD COLUMN IF NOT EXISTS despacho_id INTEGER;
CREATE INDEX IF NOT EXISTS idx_inv_mov_despacho ON public.inv_movimientos (despacho_id);

-- ============================================================================
-- CÓMO DESHACER (solo si hiciera falta; antes respaldar despachos e inv_movimientos)
-- ============================================================================
-- DROP INDEX public.idx_inv_mov_despacho;
-- ALTER TABLE public.inv_movimientos DROP COLUMN despacho_id;
-- ALTER TABLE public.despachos DROP COLUMN stock_empresa_id, DROP COLUMN stock_almacen_id,
--     DROP COLUMN stock_estado, DROP COLUMN stock_detalle, DROP COLUMN stock_fecha;
-- Y volver a la versión anterior del ERP (pruebasweb_corregido_anterior_15oct.zip).
