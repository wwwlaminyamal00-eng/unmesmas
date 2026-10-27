-- 038 (27/10/2026, Erika y Hellen, caso Komatsu): descripción y código del cliente por línea.
-- Cada producto lleva el Nombre producto del maestro y, debajo, cómo lo pide el cliente en su pedido.
-- Nace en la cotización; el PV, despachos, guías, facturas y notas de crédito ya lo guardan dentro de items_json.
-- Solo agrega columnas vacías y una tabla nueva. No cambia ni borra datos.
-- Respaldo previo: respaldo_20261015.cotizacion_detalle_20261027
ALTER TABLE cotizacion_detalle ADD COLUMN IF NOT EXISTS descripcion_cliente TEXT;
ALTER TABLE cotizacion_detalle ADD COLUMN IF NOT EXISTS codigo_cliente VARCHAR(60);

-- Memoria: cómo llama cada cliente a cada producto (se sugiere en su próxima cotización)
CREATE TABLE IF NOT EXISTS cliente_producto_descripcion (
    id SERIAL PRIMARY KEY,
    cliente_id INTEGER NOT NULL,
    producto_codigo VARCHAR(60) NOT NULL,
    descripcion_cliente TEXT,
    codigo_cliente VARCHAR(60),
    actualizado_por INTEGER,
    actualizado_en TIMESTAMP DEFAULT NOW(),
    UNIQUE (cliente_id, producto_codigo)
);
