-- 037 (27/10/2026, Erika): factura total o parcial por posiciones y cuadre de entregas.
-- comprobantes.facturacion_tipo ('Total' / 'Parcial') y comprobantes.pendientes_json (lo que no se facturó, con
-- motivo y comentario: nota interna que el cliente no ve). despachos.ingreso_cliente: N° de ingreso que el sistema
-- del cliente da al recibir (opcional). Solo agrega columnas vacías; no cambia datos.
-- Respaldos previos: respaldo_20261015.comprobantes_20261027 y respaldo_20261015.despachos_20261027
ALTER TABLE comprobantes ADD COLUMN IF NOT EXISTS facturacion_tipo VARCHAR(10);
ALTER TABLE comprobantes ADD COLUMN IF NOT EXISTS pendientes_json JSONB;
ALTER TABLE despachos ADD COLUMN IF NOT EXISTS ingreso_cliente VARCHAR(60);
