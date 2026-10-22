-- 019_conciliacion_bancaria.sql - Conciliación bancaria (pedido de Erika, 21/10/2026 23:30)
-- Crea 2 tablas NUEVAS y agrega el permiso "Conciliación bancaria" (CONCILIACION_BANCARIA) dentro de Finanzas.
-- No modifica ni borra ninguna tabla ni dato existente. El ERP también crea las tablas solo al abrir el módulo.
--   bancos_extractos    cada archivo subido (banco, cuenta, fechas, quién y cuándo)
--   bancos_movimientos  cada línea del extracto, su estado y con qué cobro / pago de Finanzas se concilió
-- Respaldo previo de la única tabla que recibe una fila: respaldo_20261021.erp_submodulos_pre019.
-- APLICADO EN SUPABASE el 21/10/2026.
CREATE SCHEMA IF NOT EXISTS respaldo_20261021;
CREATE TABLE IF NOT EXISTS respaldo_20261021.erp_submodulos_pre019 AS SELECT * FROM public.erp_submodulos;
CREATE TABLE IF NOT EXISTS bancos_extractos (
    id SERIAL PRIMARY KEY,
    empresa_id VARCHAR(64) NOT NULL,
    banco VARCHAR(40) NOT NULL,
    cuenta VARCHAR(60),
    moneda VARCHAR(5) NOT NULL DEFAULT 'PEN',
    archivo VARCHAR(255),
    desde DATE,
    hasta DATE,
    filas INTEGER NOT NULL DEFAULT 0,
    nuevas INTEGER NOT NULL DEFAULT 0,
    repetidas INTEGER NOT NULL DEFAULT 0,
    creado_por VARCHAR(150),
    creado_en TIMESTAMP DEFAULT NOW(),
    anulado_por VARCHAR(150),
    anulado_en TIMESTAMP,
    motivo_anulacion TEXT
);
CREATE TABLE IF NOT EXISTS bancos_movimientos (
    id SERIAL PRIMARY KEY,
    extracto_id INTEGER NOT NULL REFERENCES bancos_extractos(id) ON DELETE CASCADE,
    empresa_id VARCHAR(64) NOT NULL,
    banco VARCHAR(40) NOT NULL,
    cuenta VARCHAR(60),
    moneda VARCHAR(5) NOT NULL DEFAULT 'PEN',
    fecha DATE NOT NULL,
    descripcion TEXT,
    numero_operacion VARCHAR(80),
    monto NUMERIC(14,2) NOT NULL,
    saldo NUMERIC(14,2),
    clave VARCHAR(64) NOT NULL UNIQUE,
    estado VARCHAR(20) NOT NULL DEFAULT 'Pendiente'
           CHECK (estado IN ('Pendiente', 'Conciliado', 'Gasto del banco', 'Revisado')),
    finanzas_pago_id INTEGER,
    forma VARCHAR(40),
    nota TEXT,
    conciliado_por VARCHAR(150),
    conciliado_en TIMESTAMP,
    historial JSONB NOT NULL DEFAULT '[]'::jsonb,
    creado_en TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bancos_mov_empresa ON bancos_movimientos (empresa_id, fecha);
CREATE UNIQUE INDEX IF NOT EXISTS uq_bancos_mov_pago ON bancos_movimientos (finanzas_pago_id)
    WHERE finanzas_pago_id IS NOT NULL;
ALTER TABLE bancos_extractos ENABLE ROW LEVEL SECURITY;
ALTER TABLE bancos_movimientos ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON bancos_extractos, bancos_movimientos FROM anon, authenticated;

-- Permiso propio (Configuración ▸ Usuarios y permisos ▸ columna "Bancos")
INSERT INTO erp_submodulos (modulo_id, orden, codigo, nombre, estado)
SELECT m.id, 5, 'CONCILIACION_BANCARIA', 'Bancos', 'activo' FROM erp_modulos m
WHERE m.codigo = 'FINANZAS' AND NOT EXISTS (SELECT 1 FROM erp_submodulos WHERE codigo = 'CONCILIACION_BANCARIA');
