-- 036 (27/10/2026, Erika): la orden de compra guarda el "Adelanto (%)" que pide el proveedor aunque dé crédito
-- (ej. 50% antes de la entrega y 50% a crédito 30 días). Solo agrega una columna; 0 = sin adelanto.
-- Respaldo previo: respaldo_20261015.ordenes_compra_20261027
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS adelanto_pct NUMERIC(5,2) DEFAULT 0;
