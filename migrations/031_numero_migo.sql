-- 031: N° MIGO / conformidad (Erika 25/10/2026: "sí, entonces agregar para evitar cualquier incidencia")
-- Algunos clientes (Komatsu-Mitsui, RUC 20302241598) no pagan la factura sin el N° MIGO de su conformidad.
-- Solo agrega columnas y marca a ese cliente. No borra nada.
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS pide_migo BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE comprobantes ADD COLUMN IF NOT EXISTS numero_migo VARCHAR(40);
UPDATE clientes SET pide_migo = true WHERE numero_documento = '20302241598';
