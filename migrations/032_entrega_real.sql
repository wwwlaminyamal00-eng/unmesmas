-- 032 · Entregas (Erika 26/10/2026): salida del almacén, fecha real de entrega y rechazo del cliente.
-- Solo agrega columnas vacías; no cambia ni borra datos. Respaldo previo: respaldo_20261026_despachos.
CREATE TABLE IF NOT EXISTS respaldo_20261026_despachos AS SELECT * FROM despachos;
ALTER TABLE despachos ADD COLUMN IF NOT EXISTS fecha_salida TIMESTAMP;          -- hora de Lima en que salió del almacén
ALTER TABLE despachos ADD COLUMN IF NOT EXISTS fecha_entrega_real DATE;         -- día en que el cliente recibió → "Entregado"
ALTER TABLE despachos ADD COLUMN IF NOT EXISTS motivo_rechazo VARCHAR(200);     -- por qué el cliente lo rechazó
ALTER TABLE despachos ADD COLUMN IF NOT EXISTS fecha_rechazo TIMESTAMP;         -- hora de Lima del rechazo
COMMENT ON COLUMN despachos.fecha_entrega_real IS 'Fecha real en que el cliente recibió (Entregado). Erika 26/10/2026';
