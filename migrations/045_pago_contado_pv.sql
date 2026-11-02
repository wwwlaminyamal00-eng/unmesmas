-- 045 (02/11/2026): pago al contado del PV con historial para auditoría (Erika 02/11/2026 13:17).
-- Antes el N° de operación, el banco y el CCI se escribían en el PV pero no se guardaban.
-- Solo agrega columnas y una tabla nueva. Respaldo previo: respaldo_20261015.pedido_compra_pc_20261102.
ALTER TABLE pedido_compra_pc ADD COLUMN IF NOT EXISTS pago_num_operacion VARCHAR(40);
ALTER TABLE pedido_compra_pc ADD COLUMN IF NOT EXISTS pago_banco VARCHAR(80);
ALTER TABLE pedido_compra_pc ADD COLUMN IF NOT EXISTS pago_cci VARCHAR(40);
ALTER TABLE pedido_compra_pc ADD COLUMN IF NOT EXISTS pago_registrado_por VARCHAR(120);
ALTER TABLE pedido_compra_pc ADD COLUMN IF NOT EXISTS pago_registrado_en TIMESTAMP;
CREATE TABLE IF NOT EXISTS pv_pago_contado_historial (
    id SERIAL PRIMARY KEY,
    pedido_id INTEGER NOT NULL,
    pv_numero VARCHAR(40),
    accion VARCHAR(20) NOT NULL,
    num_operacion VARCHAR(40),
    banco VARCHAR(80),
    cci VARCHAR(40),
    usuario_id INTEGER,
    usuario_nombre VARCHAR(120),
    creado_en TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'America/Lima')
);
CREATE INDEX IF NOT EXISTS idx_pv_pago_contado_hist_pedido ON pv_pago_contado_historial (pedido_id);
-- Como las demás tablas públicas: RLS activo (la app entra por la conexión directa del servidor).
ALTER TABLE pv_pago_contado_historial ENABLE ROW LEVEL SECURITY;
