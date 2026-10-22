-- 017_sunat_impuestos.sql - Módulo "SUNAT e impuestos" (pedido de Erika, 21/10/2026)
-- Crea 4 tablas NUEVAS. No modifica ni borra ninguna tabla existente (por eso no hace falta respaldo de datos).
-- El ERP también las crea solo al abrir el módulo (routes/sunat.py: asegurar_tablas), así que este script es opcional.
--   sunat_config        régimen tributario y % de renta mensual por empresa
--   sunat_periodos      datos del mes escritos a mano (retenciones, saldos, planilla) y cifras de la hoja del contador
--   sunat_registros     comprobantes importados del SIRE (RVIE/RCE) o del Excel; no cambian ventas ni compras
--   sunat_obligaciones  checklist de pagos del mes (AFP, EsSalud, ONP, renta, IGV...) con historial
-- empresa_id es texto (guarda el UUID de erp_empresas) para funcionar también con bases antiguas.

CREATE TABLE IF NOT EXISTS sunat_config (
    empresa_id VARCHAR(64) PRIMARY KEY,
    regimen VARCHAR(20) NOT NULL DEFAULT 'RMT',
    tasa_renta NUMERIC(6,3) NOT NULL DEFAULT 1.0,
    es_agente_retencion BOOLEAN NOT NULL DEFAULT false,
    es_buen_contribuyente BOOLEAN NOT NULL DEFAULT false,
    notas TEXT,
    actualizado_por VARCHAR(150),
    actualizado_en TIMESTAMP DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS sunat_periodos (
    id SERIAL PRIMARY KEY,
    empresa_id VARCHAR(64) NOT NULL,
    periodo VARCHAR(7) NOT NULL,
    manual JSONB NOT NULL DEFAULT '{}'::jsonb,
    planilla JSONB NOT NULL DEFAULT '{}'::jsonb,
    contador JSONB NOT NULL DEFAULT '{}'::jsonb,
    contador_archivo VARCHAR(255),
    contador_cargado_en TIMESTAMP,
    actualizado_por VARCHAR(150),
    actualizado_en TIMESTAMP DEFAULT NOW(),
    creado_en TIMESTAMP DEFAULT NOW(),
    UNIQUE (empresa_id, periodo)
);
CREATE TABLE IF NOT EXISTS sunat_registros (
    id SERIAL PRIMARY KEY,
    empresa_id VARCHAR(64) NOT NULL,
    periodo VARCHAR(7) NOT NULL,
    libro VARCHAR(10) NOT NULL CHECK (libro IN ('VENTAS', 'COMPRAS')),
    lote VARCHAR(40) NOT NULL,
    origen VARCHAR(30) NOT NULL,
    archivo VARCHAR(255),
    tipo_cp VARCHAR(4),
    serie VARCHAR(20),
    numero VARCHAR(30),
    fecha DATE,
    ruc VARCHAR(20),
    nombre VARCHAR(255),
    base NUMERIC(14,2) NOT NULL DEFAULT 0,
    igv NUMERIC(14,2) NOT NULL DEFAULT 0,
    no_gravado NUMERIC(14,2) NOT NULL DEFAULT 0,
    total NUMERIC(14,2) NOT NULL DEFAULT 0,
    moneda VARCHAR(5) DEFAULT 'PEN',
    tipo_cambio NUMERIC(10,4),
    creado_por VARCHAR(150),
    creado_en TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sunat_registros_periodo ON sunat_registros (empresa_id, periodo, libro);
CREATE TABLE IF NOT EXISTS sunat_obligaciones (
    id SERIAL PRIMARY KEY,
    empresa_id VARCHAR(64) NOT NULL,
    periodo VARCHAR(7) NOT NULL,
    codigo VARCHAR(30) NOT NULL,
    estado VARCHAR(15) NOT NULL DEFAULT 'Pendiente' CHECK (estado IN ('Pendiente', 'Pagado', 'No aplica')),
    monto NUMERIC(14,2),
    vencimiento DATE,
    fecha_pago DATE,
    numero_operacion VARCHAR(80),
    observacion TEXT,
    marcado_por VARCHAR(150),
    marcado_en TIMESTAMP,
    historial JSONB NOT NULL DEFAULT '[]'::jsonb,
    UNIQUE (empresa_id, periodo, codigo)
);
-- Datos tributarios: nadie entra por la API pública de Supabase (el ERP usa su propia conexión)
ALTER TABLE sunat_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE sunat_periodos ENABLE ROW LEVEL SECURITY;
ALTER TABLE sunat_registros ENABLE ROW LEVEL SECURITY;
ALTER TABLE sunat_obligaciones ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON sunat_config, sunat_periodos, sunat_registros, sunat_obligaciones FROM anon, authenticated;
