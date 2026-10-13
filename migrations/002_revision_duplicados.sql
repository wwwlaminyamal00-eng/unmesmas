-- ============================================================
-- Migración 002 (OPCIONAL) - Revisión de duplicados e índices únicos
-- El código ya evita nuevos duplicados. Estas consultas solo LEEN datos para
-- detectar duplicados históricos. Los índices únicos del final están comentados:
-- créalos solo cuando las consultas de revisión devuelvan 0 filas.
-- ============================================================

-- Cotizaciones con número repetido
SELECT numero_cotizacion, COUNT(*) FROM cotizaciones GROUP BY 1 HAVING COUNT(*) > 1;

-- Comprobantes de venta repetidos por tipo + serie + número
SELECT tipo_comprobante, serie, numero, COUNT(*) FROM comprobantes GROUP BY 1, 2, 3 HAVING COUNT(*) > 1;

-- Guías repetidas por serie + número
SELECT serie, numero, COUNT(*) FROM guias_remision GROUP BY 1, 2 HAVING COUNT(*) > 1;

-- Órdenes de compra repetidas
SELECT numero_orden, COUNT(*) FROM ordenes_compra GROUP BY 1 HAVING COUNT(*) > 1;

-- Facturas de proveedor registradas dos veces
SELECT ruc_proveedor, numero, COUNT(*) FROM comprobantes_proveedor
WHERE COALESCE(estado, '') NOT IN ('Anulado', 'Anulada') GROUP BY 1, 2 HAVING COUNT(*) > 1;

-- Items de órdenes de compra huérfanos (de órdenes eliminadas antes de esta versión)
SELECT COUNT(*) FROM ordenes_compra_items i LEFT JOIN ordenes_compra o ON o.id = i.orden_compra_id WHERE o.id IS NULL;

-- Índices únicos recomendados (ejecutar solo si no hay duplicados):
-- CREATE UNIQUE INDEX IF NOT EXISTS ux_cotizaciones_numero ON cotizaciones (numero_cotizacion);
-- CREATE UNIQUE INDEX IF NOT EXISTS ux_comprobantes_doc ON comprobantes (tipo_comprobante, serie, numero);
-- CREATE UNIQUE INDEX IF NOT EXISTS ux_guias_doc ON guias_remision (serie, numero);
-- CREATE UNIQUE INDEX IF NOT EXISTS ux_ordenes_compra_numero ON ordenes_compra (numero_orden);
