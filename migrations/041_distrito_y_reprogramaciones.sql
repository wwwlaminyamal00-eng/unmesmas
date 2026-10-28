-- 041 (28/10/2026): distrito de entrega del PV, primera cita y reprogramaciones de Entregas.
-- Solo agrega. Respaldo previo: respaldo_20261015.pedido_compra_pc_20261028 y respaldo_20261015.despachos_20261028.
ALTER TABLE pedido_compra_pc ADD COLUMN IF NOT EXISTS distrito_entrega VARCHAR(80);
ALTER TABLE despachos ADD COLUMN IF NOT EXISTS fecha_cita_inicial DATE;
CREATE TABLE IF NOT EXISTS despacho_reprogramaciones (
    id SERIAL PRIMARY KEY,
    despacho_id INTEGER NOT NULL,
    fecha_anterior DATE,
    fecha_nueva DATE,
    motivo VARCHAR(60) NOT NULL,
    comentario VARCHAR(200),
    usuario VARCHAR(120),
    creado_en TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'America/Lima'));
CREATE INDEX IF NOT EXISTS idx_desp_reprog_despacho ON despacho_reprogramaciones (despacho_id);
-- La primera cita de las entregas que ya tienen cita queda como "cita inicial" (para medir el cumplimiento).
UPDATE despachos SET fecha_cita_inicial = fecha_cita::date WHERE fecha_cita_inicial IS NULL AND fecha_cita IS NOT NULL;
-- Igual que las demás tablas públicas: sin acceso por la API pública (el ERP entra con su propio usuario).
ALTER TABLE despacho_reprogramaciones ENABLE ROW LEVEL SECURITY;
