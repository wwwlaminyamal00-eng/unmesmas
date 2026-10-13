-- 003_inventario.sql - Inventario multiempresa y multisede
-- El sistema crea estas tablas solo la primera vez que alguien abre Inventario.
-- Este script es el equivalente por si prefieres crearlas a mano en Supabase (SQL Editor).
-- Solo CREA tablas e índices nuevos. No modifica ni borra datos existentes.
-- Empresas: tabla erp_empresas (Configuración ▸ Empresas). Sedes: tabla almacenes (Maestros ▸ Almacenes).

CREATE TABLE IF NOT EXISTS inv_sede_empresa (
    id SERIAL PRIMARY KEY,
    almacen_id INTEGER NOT NULL,
    empresa_id INTEGER NOT NULL,
    registrado_sunat BOOLEAN NOT NULL DEFAULT false,
    codigo_establecimiento VARCHAR(10),
    es_domicilio_fiscal BOOLEAN NOT NULL DEFAULT false,
    observaciones TEXT,
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (almacen_id, empresa_id)
);
CREATE TABLE IF NOT EXISTS inv_stock (
    empresa_id INTEGER NOT NULL,
    almacen_id INTEGER NOT NULL,
    producto_id INTEGER NOT NULL,
    cantidad NUMERIC(14,4) NOT NULL DEFAULT 0 CHECK (cantidad >= 0),
    costo_promedio NUMERIC(16,6) NOT NULL DEFAULT 0,
    valor NUMERIC(16,4) NOT NULL DEFAULT 0,
    ultimo_ingreso TIMESTAMP,
    ultima_salida TIMESTAMP,
    ultimo_movimiento TIMESTAMP,
    PRIMARY KEY (empresa_id, almacen_id, producto_id)
);
CREATE TABLE IF NOT EXISTS inv_movimientos (
    id SERIAL PRIMARY KEY,
    numero VARCHAR(30) UNIQUE,
    fecha TIMESTAMP NOT NULL DEFAULT NOW(),
    empresa_id INTEGER NOT NULL,
    almacen_id INTEGER NOT NULL,
    producto_id INTEGER NOT NULL,
    tipo VARCHAR(10) NOT NULL CHECK (tipo IN ('ENTRADA', 'SALIDA')),
    motivo VARCHAR(30) NOT NULL,
    cantidad NUMERIC(14,4) NOT NULL CHECK (cantidad > 0),
    costo_unitario NUMERIC(16,6) DEFAULT 0,
    costo_total NUMERIC(16,4) DEFAULT 0,
    saldo_cantidad NUMERIC(14,4),
    saldo_costo_promedio NUMERIC(16,6),
    saldo_valor NUMERIC(16,4),
    documento_tipo VARCHAR(30),
    documento_numero VARCHAR(60),
    tercero VARCHAR(255),
    lote_serie VARCHAR(120),
    fecha_vencimiento DATE,
    traslado_id INTEGER,
    conteo_id INTEGER,
    separacion_id INTEGER,
    recepcion_id INTEGER,
    grupo VARCHAR(30),
    revierte_id INTEGER,
    revertido_por_id INTEGER,
    estado VARCHAR(20) NOT NULL DEFAULT 'Registrado',
    observaciones TEXT,
    usuario_id INTEGER,
    usuario_nombre VARCHAR(150),
    aprobado_por VARCHAR(150),
    aprobado_en TIMESTAMP,
    motivo_rechazo TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_inv_mov_prod ON inv_movimientos (producto_id, empresa_id, almacen_id, id);
CREATE INDEX IF NOT EXISTS idx_inv_mov_estado ON inv_movimientos (estado);
CREATE INDEX IF NOT EXISTS idx_inv_mov_recepcion ON inv_movimientos (recepcion_id);
CREATE TABLE IF NOT EXISTS inv_traslados (
    id SERIAL PRIMARY KEY,
    numero VARCHAR(30) UNIQUE,
    fecha TIMESTAMP NOT NULL DEFAULT NOW(),
    empresa_id INTEGER NOT NULL,
    origen_id INTEGER NOT NULL,
    destino_id INTEGER NOT NULL,
    estado VARCHAR(30) NOT NULL DEFAULT 'En camino',
    guia_remision VARCHAR(40),
    encargado VARCHAR(150),
    observaciones TEXT,
    enviado_por_id INTEGER,
    enviado_por VARCHAR(150),
    recibido_por_id INTEGER,
    recibido_por VARCHAR(150),
    recibido_en TIMESTAMP,
    observaciones_recepcion TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS inv_traslado_items (
    id SERIAL PRIMARY KEY,
    traslado_id INTEGER NOT NULL REFERENCES inv_traslados(id),
    producto_id INTEGER NOT NULL,
    cantidad NUMERIC(14,4) NOT NULL CHECK (cantidad > 0),
    cantidad_recibida NUMERIC(14,4),
    costo_unitario NUMERIC(16,6) DEFAULT 0
);
CREATE TABLE IF NOT EXISTS inv_separaciones (
    id SERIAL PRIMARY KEY,
    numero VARCHAR(30) UNIQUE,
    empresa_id INTEGER NOT NULL,
    almacen_id INTEGER NOT NULL,
    producto_id INTEGER NOT NULL,
    cantidad NUMERIC(14,4) NOT NULL CHECK (cantidad >= 0),
    cantidad_inicial NUMERIC(14,4) NOT NULL,
    cliente VARCHAR(255) NOT NULL,
    documento VARCHAR(60),
    vence_el DATE NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'Activa',
    observaciones TEXT,
    usuario_id INTEGER,
    usuario_nombre VARCHAR(150),
    cerrado_por VARCHAR(150),
    cerrado_en TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_inv_sep_activa ON inv_separaciones (producto_id, empresa_id, almacen_id) WHERE estado = 'Activa';
CREATE TABLE IF NOT EXISTS inv_conteos (
    id SERIAL PRIMARY KEY,
    numero VARCHAR(30) UNIQUE,
    fecha TIMESTAMP NOT NULL DEFAULT NOW(),
    empresa_id INTEGER NOT NULL,
    almacen_id INTEGER NOT NULL,
    tipo VARCHAR(20) NOT NULL DEFAULT 'General',
    estado VARCHAR(20) NOT NULL DEFAULT 'En conteo',
    creado_por VARCHAR(150),
    contado_por_id INTEGER,
    contado_por VARCHAR(150),
    contado_en TIMESTAMP,
    aprobado_por VARCHAR(150),
    aprobado_en TIMESTAMP,
    observaciones TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS inv_conteo_items (
    id SERIAL PRIMARY KEY,
    conteo_id INTEGER NOT NULL REFERENCES inv_conteos(id),
    producto_id INTEGER NOT NULL,
    cantidad_contada NUMERIC(14,4),
    stock_sistema NUMERIC(14,4),
    costo_promedio NUMERIC(16,6),
    comentario TEXT
);
