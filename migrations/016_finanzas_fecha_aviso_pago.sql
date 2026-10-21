-- =====================================================================================
-- SUPABASE 016 · Fecha de aviso de pago en cobros (pedido de Erika 21/10/2026 17:12)
-- "en cuentas por cobrar ... debe figurar campo fecha aviso de pago o el número de operación, va a depender del cliente".
-- Solo AGREGA una columna opcional. No borra ni cambia datos. APLICADO en Supabase el 21/10/2026.
-- Respaldo previo: respaldo_20261021.finanzas_pagos_pre016.
-- =====================================================================================
BEGIN;
CREATE SCHEMA IF NOT EXISTS respaldo_20261021;
CREATE TABLE IF NOT EXISTS respaldo_20261021.finanzas_pagos_pre016 AS SELECT * FROM public.finanzas_pagos;
ALTER TABLE public.finanzas_pagos ADD COLUMN IF NOT EXISTS fecha_aviso DATE;
COMMENT ON COLUMN public.finanzas_pagos.fecha_aviso IS 'Fecha en que el cliente avisó el pago (cuando no envía N.º de operación). 21/10/2026';
COMMIT;
