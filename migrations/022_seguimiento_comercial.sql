-- 022_seguimiento_comercial.sql - Seguimiento comercial (pedido de Erika, 21/10/2026 23:30)
-- Crea 1 tabla vacía (ventas_seguimiento: las llamadas a clientes por cotización) y el permiso
-- "Seguimiento comercial" (SEGUIMIENTO_COMERCIAL) dentro de Ventas. No cambia las cotizaciones.
-- La tabla solo la usa el servidor del ERP (RLS activo y sin acceso para anon / authenticated).
-- No modifica ni borra datos. Respaldo previo: respaldo_20261021.erp_submodulos_pre022.
-- APLICADO EN SUPABASE el 22/10/2026.
CREATE SCHEMA IF NOT EXISTS respaldo_20261021;
CREATE TABLE IF NOT EXISTS respaldo_20261021.erp_submodulos_pre022 AS SELECT * FROM public.erp_submodulos;
CREATE TABLE IF NOT EXISTS ventas_seguimiento (
    id SERIAL PRIMARY KEY,
    cotizacion_id INTEGER NOT NULL,
    empresa_id VARCHAR(64),
    medio VARCHAR(20) NOT NULL,
    comentario TEXT NOT NULL,
    proxima_llamada DATE,
    cierre VARCHAR(15) CHECK (cierre IN ('No compró')),
    motivo_cierre VARCHAR(60),
    creado_por VARCHAR(150),
    creado_en TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ventas_seguimiento_cot ON ventas_seguimiento (cotizacion_id, creado_en);
ALTER TABLE ventas_seguimiento ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON ventas_seguimiento FROM anon, authenticated;
INSERT INTO erp_submodulos (modulo_id, orden, codigo, nombre, estado)
SELECT m.id, 5, 'SEGUIMIENTO_COMERCIAL', 'Seguimiento comercial', 'activo' FROM erp_modulos m
WHERE m.codigo = 'VENTAS' AND NOT EXISTS (SELECT 1 FROM erp_submodulos WHERE codigo = 'SEGUIMIENTO_COMERCIAL');
