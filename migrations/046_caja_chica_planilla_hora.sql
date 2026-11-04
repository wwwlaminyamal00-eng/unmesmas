-- 046_caja_chica_planilla_hora.sql - Mejoras de Caja chica (pedido de Erika, 04/11/2026)
-- 1. Hora del gasto (caja_chica_movimientos.hora).
-- 2. "De dónde a dónde" separado de la descripción (caja_chica_movimientos.detalle).
-- 3. Planilla de movilidad con N° automático por empresa (tabla caja_chica_planillas + caja_chica_movimientos.planilla_id).
-- Solo agrega columnas y una tabla nueva. No cambia ni borra datos existentes: los gastos ya guardados con los
-- nombres de rubro anteriores ("Flete y transporte de carga", "Movilidad del personal (pasajes)") se muestran con
-- el nombre nuevo desde el ERP, sin tocar la base.
-- Respaldo previo: respaldo_20261015.caja_chica_movimientos_pre046.
CREATE SCHEMA IF NOT EXISTS respaldo_20261015;
CREATE TABLE IF NOT EXISTS respaldo_20261015.caja_chica_movimientos_pre046 AS SELECT * FROM public.caja_chica_movimientos;
CREATE TABLE IF NOT EXISTS respaldo_20261015.caja_chica_personas_pre046 AS SELECT * FROM public.caja_chica_personas;
ALTER TABLE respaldo_20261015.caja_chica_movimientos_pre046 ENABLE ROW LEVEL SECURITY;
ALTER TABLE respaldo_20261015.caja_chica_personas_pre046 ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS caja_chica_planillas (
    id SERIAL PRIMARY KEY,
    empresa_id VARCHAR(64) NOT NULL,
    numero INTEGER NOT NULL,
    quien_id INTEGER REFERENCES caja_chica_personas(id),
    quien VARCHAR(150) NOT NULL,
    dni VARCHAR(15),
    tipo_persona VARCHAR(20),
    desde DATE NOT NULL,
    hasta DATE NOT NULL,
    total NUMERIC(12,2) NOT NULL DEFAULT 0,
    estado VARCHAR(10) NOT NULL DEFAULT 'Emitida' CHECK (estado IN ('Emitida', 'Anulada')),
    motivo_anulacion TEXT,
    emitida_por VARCHAR(150),
    emitida_en TIMESTAMP DEFAULT NOW(),
    historial JSONB NOT NULL DEFAULT '[]'::jsonb
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_caja_chica_planilla ON caja_chica_planillas (empresa_id, numero);
ALTER TABLE caja_chica_planillas ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON caja_chica_planillas FROM anon, authenticated;

ALTER TABLE caja_chica_movimientos ADD COLUMN IF NOT EXISTS hora TIME;
ALTER TABLE caja_chica_movimientos ADD COLUMN IF NOT EXISTS detalle VARCHAR(300);
ALTER TABLE caja_chica_movimientos ADD COLUMN IF NOT EXISTS planilla_id INTEGER REFERENCES caja_chica_planillas(id);
