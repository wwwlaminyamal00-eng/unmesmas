-- 047 (04/11/2026): borradores de gastos de Luis, Sebastián y Estrella que Hellen valida. Solo agrega.
-- Aplicada en Supabase ERP_KCF el 04/11/2026 con respaldo previo respaldo_20261104_caja_chica_movimientos (840 filas).
CREATE TABLE IF NOT EXISTS respaldo_20261104_caja_chica_movimientos AS SELECT * FROM caja_chica_movimientos;
ALTER TABLE respaldo_20261104_caja_chica_movimientos ENABLE ROW LEVEL SECURITY;
ALTER TABLE caja_chica_movimientos DROP CONSTRAINT IF EXISTS caja_chica_movimientos_estado_check;
ALTER TABLE caja_chica_movimientos ADD CONSTRAINT caja_chica_movimientos_estado_check
    CHECK (estado IN ('Activo', 'Anulado', 'Borrador', 'Rechazado'));
ALTER TABLE caja_chica_movimientos ADD COLUMN IF NOT EXISTS creado_usuario VARCHAR(60);
ALTER TABLE caja_chica_movimientos ADD COLUMN IF NOT EXISTS validado_por VARCHAR(150);
ALTER TABLE caja_chica_movimientos ADD COLUMN IF NOT EXISTS validado_en TIMESTAMP;
