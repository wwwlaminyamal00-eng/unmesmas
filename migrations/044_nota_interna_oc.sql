-- 044 (28/10/2026): "Nota interna (No la ve el proveedor)" en la Orden de compra (Proveedor). Pedido de Erika 17:34.
-- Nunca sale en la OC impresa ni en el PDF. Solo agrega una columna; no toca datos.
-- (La columna antigua nota_compra no se usa en el flujo actual y está vacía: se deja como está.)
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS nota_interna TEXT;
