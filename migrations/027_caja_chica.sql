-- 027_caja_chica.sql - Caja chica con fondo fijo (pedido de Erika, 22/10/2026 18:24)
-- Crea 6 tablas nuevas (caja_chica_config, _personas, _rendiciones, _movimientos, _fotos, _arqueos) y el permiso
-- "Caja chica" (CAJA_CHICA) dentro de Finanzas. No modifica ni borra datos existentes.
-- Las tablas solo las usa el servidor del ERP (RLS activo y sin acceso para anon / authenticated).
-- Las reposiciones aprobadas se registran en finanzas_pagos (documento_tabla = 'caja_chica_rendiciones' o
-- 'caja_chica_movimientos') para que Conciliación bancaria las encuentre en el extracto.
-- Respaldo previo: respaldo_20261022.erp_submodulos_pre027.
CREATE SCHEMA IF NOT EXISTS respaldo_20261022;
CREATE TABLE IF NOT EXISTS respaldo_20261022.erp_submodulos_pre027 AS SELECT * FROM public.erp_submodulos;
ALTER TABLE respaldo_20261022.erp_submodulos_pre027 ENABLE ROW LEVEL SECURITY;
CREATE TABLE IF NOT EXISTS caja_chica_config (
    empresa_id VARCHAR(64) PRIMARY KEY,
    fondo_fijo NUMERIC(12,2) NOT NULL DEFAULT 600 CHECK (fondo_fijo > 0),
    responsable VARCHAR(150),
    responsable_dni VARCHAR(15),
    cuenta VARCHAR(150),
    rmv NUMERIC(10,2) NOT NULL DEFAULT 1230,
    actualizado_por VARCHAR(150),
    actualizado_en TIMESTAMP DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS caja_chica_personas (
    id SERIAL PRIMARY KEY,
    empresa_id VARCHAR(64) NOT NULL,
    nombre VARCHAR(150) NOT NULL,
    dni VARCHAR(15),
    ruc VARCHAR(11),
    tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('Trabajador', 'Practicante', 'Transportista', 'Otro')),
    activo BOOLEAN NOT NULL DEFAULT true,
    creado_por VARCHAR(150),
    creado_en TIMESTAMP DEFAULT NOW(),
    actualizado_por VARCHAR(150),
    actualizado_en TIMESTAMP DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_caja_chica_persona ON caja_chica_personas (empresa_id, LOWER(nombre));
CREATE TABLE IF NOT EXISTS caja_chica_rendiciones (
    id SERIAL PRIMARY KEY,
    empresa_id VARCHAR(64) NOT NULL,
    numero INTEGER NOT NULL,
    desde DATE NOT NULL,
    hasta DATE NOT NULL,
    total_gastado NUMERIC(12,2) NOT NULL DEFAULT 0,
    sin_sustento NUMERIC(12,2) NOT NULL DEFAULT 0,
    estado VARCHAR(15) NOT NULL DEFAULT 'Por aprobar' CHECK (estado IN ('Por aprobar', 'Observada', 'Aprobada')),
    enviada_por VARCHAR(150),
    enviada_en TIMESTAMP DEFAULT NOW(),
    revisada_por VARCHAR(150),
    revisada_en TIMESTAMP,
    observacion TEXT,
    monto_repuesto NUMERIC(12,2),
    fecha_reposicion DATE,
    numero_operacion VARCHAR(80),
    finanzas_pago_id INTEGER,
    historial JSONB NOT NULL DEFAULT '[]'::jsonb
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_caja_chica_rendicion ON caja_chica_rendiciones (empresa_id, numero);
CREATE TABLE IF NOT EXISTS caja_chica_movimientos (
    id SERIAL PRIMARY KEY,
    empresa_id VARCHAR(64) NOT NULL,
    numero INTEGER NOT NULL,
    fecha DATE NOT NULL,
    tipo VARCHAR(15) NOT NULL CHECK (tipo IN ('Gasto', 'Reposición', 'Devolución', 'Saldo inicial')),
    empresa_gasto VARCHAR(10),
    rubro VARCHAR(60),
    quien VARCHAR(150),
    quien_id INTEGER REFERENCES caja_chica_personas(id),
    pagado_a VARCHAR(150),
    descripcion TEXT NOT NULL,
    referencia VARCHAR(150),
    comprobante_tipo VARCHAR(30),
    comprobante_numero VARCHAR(40),
    ruc_emisor VARCHAR(11),
    autorizado_por VARCHAR(150),
    ingreso NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (ingreso >= 0),
    egreso NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (egreso >= 0),
    rendicion_id INTEGER REFERENCES caja_chica_rendiciones(id),
    origen VARCHAR(12) NOT NULL DEFAULT 'ERP' CHECK (origen IN ('ERP', 'Histórico')),
    estado VARCHAR(10) NOT NULL DEFAULT 'Activo' CHECK (estado IN ('Activo', 'Anulado')),
    motivo_anulacion TEXT,
    observacion TEXT,
    creado_por VARCHAR(150),
    creado_en TIMESTAMP DEFAULT NOW(),
    actualizado_por VARCHAR(150),
    actualizado_en TIMESTAMP DEFAULT NOW(),
    historial JSONB NOT NULL DEFAULT '[]'::jsonb,
    CHECK ((ingreso > 0 AND egreso = 0) OR (egreso > 0 AND ingreso = 0) OR tipo = 'Saldo inicial')
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_caja_chica_mov ON caja_chica_movimientos (empresa_id, numero);
CREATE INDEX IF NOT EXISTS idx_caja_chica_mov_fecha ON caja_chica_movimientos (empresa_id, fecha);
CREATE TABLE IF NOT EXISTS caja_chica_fotos (
    id SERIAL PRIMARY KEY,
    movimiento_id INTEGER NOT NULL REFERENCES caja_chica_movimientos(id),
    nombre VARCHAR(150),
    mime VARCHAR(40) NOT NULL,
    datos BYTEA NOT NULL,
    bytes INTEGER NOT NULL,
    subido_por VARCHAR(150),
    subido_en TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_caja_chica_fotos_mov ON caja_chica_fotos (movimiento_id);
CREATE TABLE IF NOT EXISTS caja_chica_arqueos (
    id SERIAL PRIMARY KEY,
    empresa_id VARCHAR(64) NOT NULL,
    fecha DATE NOT NULL,
    saldo_sistema NUMERIC(12,2) NOT NULL,
    efectivo NUMERIC(12,2) NOT NULL DEFAULT 0,
    saldo_cuenta NUMERIC(12,2) NOT NULL DEFAULT 0,
    vales NUMERIC(12,2) NOT NULL DEFAULT 0,
    diferencia NUMERIC(12,2) NOT NULL,
    explicacion TEXT,
    hecho_por VARCHAR(150),
    hecho_en TIMESTAMP DEFAULT NOW()
);
ALTER TABLE caja_chica_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE caja_chica_personas ENABLE ROW LEVEL SECURITY;
ALTER TABLE caja_chica_rendiciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE caja_chica_movimientos ENABLE ROW LEVEL SECURITY;
ALTER TABLE caja_chica_fotos ENABLE ROW LEVEL SECURITY;
ALTER TABLE caja_chica_arqueos ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON caja_chica_config, caja_chica_personas, caja_chica_rendiciones, caja_chica_movimientos, caja_chica_fotos,
    caja_chica_arqueos FROM anon, authenticated;
INSERT INTO erp_submodulos (modulo_id, orden, codigo, nombre, estado)
SELECT m.id, 8, 'CAJA_CHICA', 'Caja chica', 'activo' FROM erp_modulos m
WHERE m.codigo = 'FINANZAS' AND NOT EXISTS (SELECT 1 FROM erp_submodulos WHERE codigo = 'CAJA_CHICA');
