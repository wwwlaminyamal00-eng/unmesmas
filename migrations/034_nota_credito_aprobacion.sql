-- 034 · Notas de crédito con aprobación (REGLA DE ORO de Erika, 26/10/2026): solo Hellen crea, solo Erika aprueba.
-- Solo AGREGA columnas (vacías) y una tabla nueva de evidencias. No cambia ni borra datos: las 3 notas FC01 existentes quedan igual.
-- Monto calculado, trazabilidad (guía, PV, PC del cliente, cotización), sustento, nota interna (causa y responsable) y quién aprobó.
ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS tipo_nota VARCHAR(2);
ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS sustento TEXT;
ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS nota_interna TEXT;
ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS causa_interna VARCHAR(40);
ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS responsable_error VARCHAR(120);
ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS comprobante_id INTEGER;
ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS factura_fecha DATE;
ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS guia_numero VARCHAR(40);
ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS pv_numero VARCHAR(40);
ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS pc_cliente VARCHAR(60);
ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS cotizacion_numero VARCHAR(40);
ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS guia_devolucion VARCHAR(60);
ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS porcentaje NUMERIC(6,2);
ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS items_json JSONB;
ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS subtotal NUMERIC(14,2);
ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS igv NUMERIC(14,2);
ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS moneda VARCHAR(3);
ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS creado_por_usuario VARCHAR(60);
ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS enviado_por VARCHAR(60);
ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS enviado_en TIMESTAMP;
ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS aprobado_por VARCHAR(60);
ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS aprobado_en TIMESTAMP;
ALTER TABLE notas_credito ADD COLUMN IF NOT EXISTS motivo_rechazo TEXT;
CREATE TABLE IF NOT EXISTS nota_credito_archivos (
        id SERIAL PRIMARY KEY,
        nota_id INTEGER NOT NULL,
        nombre VARCHAR(150) NOT NULL,
        mime VARCHAR(80) NOT NULL,
        datos BYTEA NOT NULL,
        bytes INTEGER NOT NULL,
        subido_por VARCHAR(80),
        created_at TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'America/Lima'));
CREATE INDEX IF NOT EXISTS idx_nota_credito_archivos_nota ON nota_credito_archivos (nota_id);
ALTER TABLE nota_credito_archivos ENABLE ROW LEVEL SECURITY;
