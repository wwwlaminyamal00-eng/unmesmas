-- =====================================================================================
-- SUPABASE 013 · Fecha de cita del cliente en Entregas (despachos)
-- Pedido de Erika del 20/10/2026 18:09 (audio): en Ventas ▸ Entregas, columna "Fecha de cita" del cliente.
-- Autorización: su mensaje del 20/10/2026 17:19 ("Te autorizo a modificar la base de datos Supabase si es
--   necesario para estos cambios ... Haz respaldos previos de lo que toques").
-- NO BORRA NADA. Solo agrega una columna vacía. Se puede correr varias veces.
-- RESPALDO tomado ANTES: respaldo_20261015.despachos_pre013 (copia completa de despachos).
-- =====================================================================================
BEGIN;
SET LOCAL lock_timeout = '8s';

CREATE SCHEMA IF NOT EXISTS respaldo_20261015;
CREATE TABLE IF NOT EXISTS respaldo_20261015.despachos_pre013 AS SELECT * FROM public.despachos;

ALTER TABLE public.despachos ADD COLUMN IF NOT EXISTS fecha_cita TIMESTAMP;
COMMENT ON COLUMN public.despachos.fecha_cita IS 'Fecha y hora de la cita con el cliente para la entrega (Ventas > Entregas)';

COMMIT;

-- =====================================================================================
-- CÓMO DESHACER (borra solo la columna nueva; el respaldo queda):
--   ALTER TABLE public.despachos DROP COLUMN IF EXISTS fecha_cita;
-- =====================================================================================
