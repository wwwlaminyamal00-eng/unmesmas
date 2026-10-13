-- ============================================================
-- Migración 001 - Módulo Finanzas (cobros y pagos)
-- NO destructiva: solo crea la tabla finanzas_pagos y agrega una columna opcional.
-- La aplicación la ejecuta automáticamente la primera vez que se abre Finanzas;
-- este archivo sirve para aplicarla manualmente desde el SQL Editor de Supabase.
-- ============================================================
CREATE TABLE IF NOT EXISTS finanzas_pagos (
    id SERIAL PRIMARY KEY,
    tipo VARCHAR(10) NOT NULL CHECK (tipo IN ('COBRO', 'PAGO')),
    documento_tabla VARCHAR(40) NOT NULL,
    documento_id INTEGER NOT NULL,
    documento_numero VARCHAR(60),
    tercero_nombre VARCHAR(255),
    tercero_documento VARCHAR(20),
    fecha DATE NOT NULL DEFAULT CURRENT_DATE,
    monto NUMERIC(14,2) NOT NULL CHECK (monto > 0),
    metodo VARCHAR(40),
    banco VARCHAR(80),
    numero_operacion VARCHAR(80),
    observaciones TEXT,
    estado VARCHAR(20) NOT NULL DEFAULT 'Registrado',
    usuario_id INTEGER,
    usuario_nombre VARCHAR(150),
    anulado_por INTEGER,
    anulado_en TIMESTAMP,
    motivo_anulacion TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_finanzas_pagos_doc ON finanzas_pagos (documento_tabla, documento_id);
ALTER TABLE comprobantes_proveedor ADD COLUMN IF NOT EXISTS fecha_vencimiento DATE;
