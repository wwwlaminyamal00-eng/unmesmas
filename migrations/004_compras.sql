-- migrations/004_compras.sql - Compras bajo pedido (multiempresa y multisede)
-- Se ejecuta solo al abrir Compras por primera vez; este script es para hacerlo a mano en Supabase.
-- Requiere antes 001_finanzas.sql y 003_inventario.sql.
-- Seguro de ejecutar varias veces: solo AGREGA columnas y tablas (IF NOT EXISTS). No borra ni cambia datos.
BEGIN;
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS flujo VARCHAR(10);
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS empresa_id INTEGER;
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS almacen_entrega_id INTEGER;
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS modalidad_entrega VARCHAR(30);
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS direccion_recojo TEXT;
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS tipo_compra VARCHAR(20);
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS motivo_stock TEXT;
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS fecha_compromiso DATE;
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS dias_credito INTEGER;
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS creado_por_nombre VARCHAR(150);
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS aprobado_por_id INTEGER;
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS aprobado_por VARCHAR(150);
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS aprobado_en TIMESTAMP;
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS anulado_por VARCHAR(150);
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS anulado_en TIMESTAMP;
ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS motivo_anulacion TEXT;
ALTER TABLE ordenes_compra_items ADD COLUMN IF NOT EXISTS producto_id INTEGER;
ALTER TABLE ordenes_compra_items ADD COLUMN IF NOT EXISTS unidad VARCHAR(20);
ALTER TABLE ordenes_compra_items ADD COLUMN IF NOT EXISTS pedido_id INTEGER;
ALTER TABLE ordenes_compra_items ADD COLUMN IF NOT EXISTS pedido_numero VARCHAR(40);
ALTER TABLE ordenes_compra_items ADD COLUMN IF NOT EXISTS cliente VARCHAR(255);
ALTER TABLE ordenes_compra_items ADD COLUMN IF NOT EXISTS cantidad_recibida NUMERIC(14,4) DEFAULT 0;
ALTER TABLE recepciones_mercaderia ADD COLUMN IF NOT EXISTS producto_id INTEGER;
ALTER TABLE recepciones_mercaderia ADD COLUMN IF NOT EXISTS empresa_id INTEGER;
ALTER TABLE recepciones_mercaderia ADD COLUMN IF NOT EXISTS almacen_id INTEGER;
ALTER TABLE recepciones_mercaderia ADD COLUMN IF NOT EXISTS costo_unitario NUMERIC(16,6);
ALTER TABLE recepciones_mercaderia ADD COLUMN IF NOT EXISTS com_recepcion_id INTEGER;
ALTER TABLE recepciones_mercaderia ADD COLUMN IF NOT EXISTS oc_item_id INTEGER;
ALTER TABLE recepciones_mercaderia ADD COLUMN IF NOT EXISTS pedido_id INTEGER;
ALTER TABLE recepciones_mercaderia ADD COLUMN IF NOT EXISTS pedido_numero VARCHAR(40);
ALTER TABLE recepciones_mercaderia ADD COLUMN IF NOT EXISTS cliente VARCHAR(255);
ALTER TABLE recepciones_mercaderia ADD COLUMN IF NOT EXISTS guia_proveedor VARCHAR(60);
ALTER TABLE recepciones_mercaderia ADD COLUMN IF NOT EXISTS lote_serie VARCHAR(120);
ALTER TABLE recepciones_mercaderia ADD COLUMN IF NOT EXISTS fecha_vencimiento DATE;
ALTER TABLE comprobantes_proveedor ADD COLUMN IF NOT EXISTS empresa_id INTEGER;
ALTER TABLE comprobantes_proveedor ADD COLUMN IF NOT EXISTS fecha_vencimiento DATE;
ALTER TABLE comprobantes_proveedor ADD COLUMN IF NOT EXISTS monto_esperado NUMERIC(14,2);
ALTER TABLE comprobantes_proveedor ADD COLUMN IF NOT EXISTS cuadra BOOLEAN;
CREATE TABLE IF NOT EXISTS com_recepciones (
    id SERIAL PRIMARY KEY,
    numero VARCHAR(30) UNIQUE,
    fecha TIMESTAMP NOT NULL DEFAULT NOW(),
    orden_compra_id INTEGER NOT NULL,
    empresa_id INTEGER,
    almacen_id INTEGER NOT NULL,
    guia_proveedor VARCHAR(60) NOT NULL,
    traido_por_tipo VARCHAR(20) NOT NULL,
    traido_por_id INTEGER,
    traido_por VARCHAR(150),
    recibido_por_id INTEGER,
    recibido_por VARCHAR(150),
    con_diferencias BOOLEAN NOT NULL DEFAULT false,
    observaciones TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS com_recepcion_items (
    id SERIAL PRIMARY KEY,
    recepcion_id INTEGER NOT NULL REFERENCES com_recepciones(id),
    oc_item_id INTEGER NOT NULL,
    producto_id INTEGER,
    pendiente_antes NUMERIC(14,4),
    cantidad_buena NUMERIC(14,4) NOT NULL DEFAULT 0 CHECK (cantidad_buena >= 0),
    cantidad_danada NUMERIC(14,4) NOT NULL DEFAULT 0 CHECK (cantidad_danada >= 0),
    lote_serie VARCHAR(120),
    fecha_vencimiento DATE,
    comentario TEXT
);
CREATE TABLE IF NOT EXISTS com_incidencias (
    id SERIAL PRIMARY KEY,
    numero VARCHAR(30) UNIQUE,
    fecha TIMESTAMP NOT NULL DEFAULT NOW(),
    orden_compra_id INTEGER NOT NULL,
    recepcion_id INTEGER,
    comprobante_id INTEGER,
    producto_id INTEGER,
    tipo VARCHAR(30) NOT NULL,
    cantidad NUMERIC(14,4),
    monto NUMERIC(14,2),
    detalle TEXT,
    estado VARCHAR(20) NOT NULL DEFAULT 'Abierta',
    resolucion TEXT,
    resuelto_por VARCHAR(150),
    resuelto_en TIMESTAMP,
    reportado_por VARCHAR(150)
);
CREATE TABLE IF NOT EXISTS com_historial (
    id SERIAL PRIMARY KEY,
    orden_compra_id INTEGER NOT NULL,
    fecha TIMESTAMP NOT NULL DEFAULT NOW(),
    usuario_id INTEGER,
    usuario VARCHAR(150),
    accion VARCHAR(60) NOT NULL,
    detalle TEXT
);
CREATE INDEX IF NOT EXISTS idx_oci_pedido ON ordenes_compra_items (pedido_id, producto_id);
CREATE INDEX IF NOT EXISTS idx_com_hist_oc ON com_historial (orden_compra_id, id);
CREATE INDEX IF NOT EXISTS idx_com_inc_oc ON com_incidencias (orden_compra_id);
CREATE INDEX IF NOT EXISTS idx_rm_com ON recepciones_mercaderia (com_recepcion_id);
COMMIT;
