-- 030 · Soles y dólares con tipo de cambio (Erika 24/10/2026 18:17)
-- "en el registro de compra y ventas se debe colocar el tipo de cambio y ordenes de compra debe estar en tipo de cambio
--  porque a veces vendo y compro en dolares".
-- Solo agrega columnas y una tabla nueva. NO borra ni cambia datos: lo existente queda en soles (PEN), que es lo que es
-- (revisado 24/10: 0 cotizaciones, PC, OC o facturas en dólares en la base real).
-- tipo_cambio = soles por 1 dólar del documento. finanzas_pagos.monto sigue en la moneda del documento;
-- moneda_pago / tipo_cambio / monto_pagado guardan lo que realmente se pagó (por ejemplo soles con el TC del proveedor).

CREATE TABLE IF NOT EXISTS public.tipo_cambio_dia (
    fecha DATE PRIMARY KEY,
    compra NUMERIC(10,4),
    venta NUMERIC(10,4) NOT NULL,
    fuente VARCHAR(40),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE public.tipo_cambio_dia IS 'TC SUNAT del día (sugerencia); cada documento guarda su propio TC editable.';
ALTER TABLE public.tipo_cambio_dia ENABLE ROW LEVEL SECURITY;   -- solo el servidor del ERP
REVOKE ALL ON public.tipo_cambio_dia FROM anon, authenticated;

ALTER TABLE public.cotizaciones ADD COLUMN IF NOT EXISTS moneda VARCHAR(3) DEFAULT 'PEN';
ALTER TABLE public.cotizaciones ADD COLUMN IF NOT EXISTS tipo_cambio NUMERIC(10,4);
ALTER TABLE public.pedido_compra_pc ADD COLUMN IF NOT EXISTS moneda VARCHAR(3) DEFAULT 'PEN';
ALTER TABLE public.pedido_compra_pc ADD COLUMN IF NOT EXISTS tipo_cambio NUMERIC(10,4);
ALTER TABLE public.comprobantes ADD COLUMN IF NOT EXISTS tipo_cambio NUMERIC(10,4);
ALTER TABLE public.ordenes_compra ADD COLUMN IF NOT EXISTS moneda VARCHAR(3) DEFAULT 'PEN';
ALTER TABLE public.ordenes_compra ADD COLUMN IF NOT EXISTS tipo_cambio NUMERIC(10,4);
ALTER TABLE public.comprobantes_proveedor ADD COLUMN IF NOT EXISTS moneda VARCHAR(3) DEFAULT 'PEN';
ALTER TABLE public.comprobantes_proveedor ADD COLUMN IF NOT EXISTS tipo_cambio NUMERIC(10,4);
ALTER TABLE public.finanzas_pagos ADD COLUMN IF NOT EXISTS moneda_pago VARCHAR(3);
ALTER TABLE public.finanzas_pagos ADD COLUMN IF NOT EXISTS tipo_cambio NUMERIC(10,4);
ALTER TABLE public.finanzas_pagos ADD COLUMN IF NOT EXISTS monto_pagado NUMERIC(14,2);

-- Para deshacer (solo si hiciera falta; no hay datos en dólares que perder hoy):
-- ALTER TABLE public.finanzas_pagos DROP COLUMN IF EXISTS monto_pagado, DROP COLUMN IF EXISTS tipo_cambio, DROP COLUMN IF EXISTS moneda_pago;
-- (y lo mismo con las demás columnas nuevas y DROP TABLE public.tipo_cambio_dia)
