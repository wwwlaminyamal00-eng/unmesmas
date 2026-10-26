-- 033 · XML / PDF / ZIP de SUNAT guardados en la factura (Erika 26/10/2026: "descargar el XML que piden los clientes").
-- Tabla nueva; no cambia ni borra datos. RLS activo como el resto (la app entra con su usuario de base).
CREATE TABLE IF NOT EXISTS comprobante_archivos (
    id SERIAL PRIMARY KEY,
    comprobante_id INTEGER NOT NULL,
    tipo VARCHAR(10) NOT NULL,              -- XML, ZIP o PDF
    nombre VARCHAR(150) NOT NULL,
    mime VARCHAR(80) NOT NULL,
    datos BYTEA NOT NULL,
    bytes INTEGER NOT NULL,
    subido_por VARCHAR(80),
    created_at TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'America/Lima')
);
CREATE INDEX IF NOT EXISTS idx_comprobante_archivos_comp ON comprobante_archivos (comprobante_id);
ALTER TABLE comprobante_archivos ENABLE ROW LEVEL SECURITY;
