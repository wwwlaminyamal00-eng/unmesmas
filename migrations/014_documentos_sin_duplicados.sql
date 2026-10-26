-- =====================================================================================
-- SUPABASE 014 · Números de factura/boleta y de guía que no se pueden repetir
-- Pedido de Erika del 20/10/2026 22:54 ("El sistema debe ser un Policía"): "Te autorizo a crear índices únicos
--   (constraints) en la base de datos si es necesario para evitar duplicados ... Haz respaldos previos".
-- NO BORRA NI CAMBIA NINGÚN DATO. Solo agrega 2 índices únicos. Se puede correr varias veces.
-- Antes de aplicarlo se revisó que no hubiera números repetidos (0 en comprobantes y 0 en guías).
-- Los números de despacho (despachos_numero_key) y de OC (ordenes_compra_numero_orden_key) ya eran únicos.
-- Lo demás (una guía por despacho, una factura por guía, no pasarse del PC, OC repetida) lo valida el servidor,
--   porque en la base ya hay documentos repetidos de antes (INFORME sección 22) y Erika decide qué hacer con ellos.
-- RESPALDO tomado ANTES: respaldo_20261015.comprobantes_pre014 y respaldo_20261015.guias_remision_pre014.
-- =====================================================================================
BEGIN;
SET LOCAL lock_timeout = '8s';

CREATE SCHEMA IF NOT EXISTS respaldo_20261015;
CREATE TABLE IF NOT EXISTS respaldo_20261015.comprobantes_pre014 AS SELECT * FROM public.comprobantes;
CREATE TABLE IF NOT EXISTS respaldo_20261015.guias_remision_pre014 AS SELECT * FROM public.guias_remision;

-- Misma empresa + mismo tipo + misma serie + mismo número = el mismo comprobante: no puede haber dos
CREATE UNIQUE INDEX IF NOT EXISTS ux_comprobantes_numero_por_empresa
    ON public.comprobantes (tipo_comprobante, serie, numero, (COALESCE(empresa_id::text, '')))
    WHERE numero IS NOT NULL;

-- Misma empresa + misma serie + mismo número de guía: no puede haber dos
CREATE UNIQUE INDEX IF NOT EXISTS ux_guias_numero_por_empresa
    ON public.guias_remision (serie, numero, (COALESCE(empresa_id::text, '')))
    WHERE numero IS NOT NULL;

COMMIT;

-- =====================================================================================
-- CÓMO DESHACER (quita solo los índices; los datos no cambian):
--   DROP INDEX IF EXISTS public.ux_comprobantes_numero_por_empresa;
--   DROP INDEX IF EXISTS public.ux_guias_numero_por_empresa;
-- =====================================================================================
