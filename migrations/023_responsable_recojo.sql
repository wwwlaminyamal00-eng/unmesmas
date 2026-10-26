-- 023_responsable_recojo.sql - Responsable de recojo en las órdenes de compra (pedido de Erika, 22/10/2026)
-- Compras ▸ Recibir mercadería: cada OC que "Nosotros recogemos" tiene quién la recoge (Luis, Sebastián...),
-- con quién lo asignó y la fecha y hora (Lima). Con eso sale el "Programa de transporte".
-- Solo AGREGA 4 columnas vacías a ordenes_compra. No modifica ni borra datos, por eso no necesita respaldo.
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS responsable_recojo_id INTEGER;
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS responsable_recojo VARCHAR(150);
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS responsable_recojo_por VARCHAR(150);
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS responsable_recojo_en TIMESTAMP;
