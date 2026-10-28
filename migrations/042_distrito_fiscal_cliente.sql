-- 042 (28/10/2026): distrito fiscal del cliente, para que el "Distrito de entrega" del PV se llene solo.
-- Se llena con SUNAT (si hay clave en Render) o cuando alguien lo elige una vez en un PV que se entrega en la
-- dirección fiscal del cliente. Solo agrega. Respaldo previo: respaldo_20261015.clientes_20261028 (43 filas).
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS distrito_fiscal VARCHAR(80);
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS distrito_fiscal_fuente VARCHAR(20);
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS distrito_fiscal_revisado_en TIMESTAMP;
