-- 021_planilla.sql - Planilla y RRHH simple (pedido de Erika, 21/10/2026 23:30)
-- Crea 4 tablas vacías (rrhh_config, rrhh_personal, rrhh_vacaciones, rrhh_pagos) y el permiso "Planilla" (PLANILLA)
-- dentro de Finanzas. Los sueldos los escribe Erika desde la pantalla: este script NO carga personas ni montos.
-- Las tablas solo las usa el servidor del ERP (RLS activo y sin acceso para anon / authenticated).
-- No modifica ni borra datos. Respaldo previo: respaldo_20261021.erp_submodulos_pre021.
-- APLICADO EN SUPABASE el 22/10/2026.
CREATE SCHEMA IF NOT EXISTS respaldo_20261021;
CREATE TABLE IF NOT EXISTS respaldo_20261021.erp_submodulos_pre021 AS SELECT * FROM public.erp_submodulos;
CREATE TABLE IF NOT EXISTS rrhh_config (
    empresa_id VARCHAR(64) PRIMARY KEY,
    regimen_laboral VARCHAR(10) NOT NULL DEFAULT 'GENERAL' CHECK (regimen_laboral IN ('GENERAL', 'PEQUENA', 'MICRO')),
    rmv NUMERIC(10,2) NOT NULL DEFAULT 1130,
    actualizado_por VARCHAR(150),
    actualizado_en TIMESTAMP DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS rrhh_personal (
    id SERIAL PRIMARY KEY,
    empresa_id VARCHAR(64) NOT NULL,
    nombres VARCHAR(150) NOT NULL,
    documento VARCHAR(20),
    tipo VARCHAR(25) NOT NULL CHECK (tipo IN ('Planilla', 'Practicante', 'Recibo por honorarios')),
    cargo VARCHAR(100),
    fecha_ingreso DATE NOT NULL,
    fecha_cese DATE,
    sueldo NUMERIC(12,2) NOT NULL CHECK (sueldo >= 0),
    pension VARCHAR(10) NOT NULL DEFAULT 'Ninguno' CHECK (pension IN ('ONP', 'AFP', 'Ninguno')),
    afp_porcentaje NUMERIC(5,2),
    asignacion_familiar BOOLEAN NOT NULL DEFAULT false,
    banco VARCHAR(60),
    cuenta VARCHAR(60),
    observaciones TEXT,
    jornada_parcial BOOLEAN NOT NULL DEFAULT false,
    creado_por VARCHAR(150),
    creado_en TIMESTAMP DEFAULT NOW(),
    actualizado_por VARCHAR(150),
    actualizado_en TIMESTAMP DEFAULT NOW(),
    historial JSONB NOT NULL DEFAULT '[]'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_rrhh_personal_empresa ON rrhh_personal (empresa_id);
CREATE TABLE IF NOT EXISTS rrhh_vacaciones (
    id SERIAL PRIMARY KEY,
    personal_id INTEGER NOT NULL REFERENCES rrhh_personal(id),
    desde DATE NOT NULL,
    hasta DATE NOT NULL,
    dias INTEGER NOT NULL CHECK (dias > 0),
    nota TEXT,
    creado_por VARCHAR(150),
    creado_en TIMESTAMP DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS rrhh_pagos (
    id SERIAL PRIMARY KEY,
    empresa_id VARCHAR(64) NOT NULL,
    personal_id INTEGER NOT NULL REFERENCES rrhh_personal(id),
    periodo VARCHAR(7) NOT NULL,
    concepto VARCHAR(40) NOT NULL,
    monto NUMERIC(12,2) NOT NULL,
    fecha_pago DATE,
    numero_operacion VARCHAR(80),
    estado VARCHAR(15) NOT NULL DEFAULT 'Pagado' CHECK (estado IN ('Pagado', 'Desmarcado')),
    marcado_por VARCHAR(150),
    marcado_en TIMESTAMP DEFAULT NOW(),
    historial JSONB NOT NULL DEFAULT '[]'::jsonb
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_rrhh_pago ON rrhh_pagos (personal_id, periodo, concepto) WHERE estado = 'Pagado';
ALTER TABLE rrhh_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE rrhh_personal ENABLE ROW LEVEL SECURITY;
ALTER TABLE rrhh_vacaciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE rrhh_pagos ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON rrhh_config, rrhh_personal, rrhh_vacaciones, rrhh_pagos FROM anon, authenticated;
INSERT INTO erp_submodulos (modulo_id, orden, codigo, nombre, estado)
SELECT m.id, 7, 'PLANILLA', 'Planilla', 'activo' FROM erp_modulos m
WHERE m.codigo = 'FINANZAS' AND NOT EXISTS (SELECT 1 FROM erp_submodulos WHERE codigo = 'PLANILLA');
