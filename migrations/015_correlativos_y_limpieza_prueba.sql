-- =====================================================================================
-- SUPABASE 015 · Correlativos editables + limpieza de datos de PRUEBA (21/10/2026)
-- Pedido de Erika del 21/10/2026 16:35: "Te autorizo expresamente a BORRAR DATOS VIEJOS O DE PRUEBA ...
--   1. BACKUP PREVIO (respaldo_20261021) 2. REPORTE DETALLADO 3. SI DUDA, PREGUNTA".
-- Se borra SOLO lo que es claramente de prueba (dice PRUEBA / TEST / xxxx, RUC inventado) y no tiene
-- movimientos de stock, guías, facturas a clientes, recepciones ni otros documentos enlazados.
-- NO se tocan ventas, compras, clientes, productos, stock ni usuarios reales. Los documentos duplicados
-- de la sección 22.6 del informe NO se borran (tienen número, stock o vínculos): Erika decide.
--
-- APLICADO EN SUPABASE el 21/10/2026 (respaldo + borrado verificados). RESUMEN DE LO BORRADO (19 filas):
--   ordenes_compra ............ 2  (id 5 "OC-TEST-001" y id 7 "OC-20260713-0001": "Orden de compra de prueba", sin productos ni recepciones)
--   orden_compra_detalle ...... 1  (id 3, el detalle de la OC-TEST-001)
--   comprobantes_proveedor .... 2  (id 1 y 2: "PROVEEDOR DE PRUEBA S.A.C." F001-00000001, "Registro de prueba")
--   finanzas_pagos ............ 3  (id 1 y 4: pagos a ese proveedor de prueba; id 3: cobro ya ANULADO de una factura que ya no existe)
--   proveedores_contactos ..... 3  (id 3, 18, 19: contactos de los proveedores de prueba de abajo)
--   proveedores_puntos_entrega  4  (id 3, 4, 19, 20: direcciones de los proveedores de prueba)
--   proveedores ............... 4  (id 10 "EMPRESA TEST PROVEEDOR" RUC 12345678901; id 22 "xxxxxxxxxxxxx";
--                                   id 34 y 35 "PROVEEDOR TEST OK"; los 4 inactivos y sin compras)
--   Tablas vacías (0 filas) que el ERP no usa: erp_alertas, listas_precios, logs_auditoria, movimientos_inventario,
--   movimientos_stock, recuentos_inventario, revalorizaciones_inventario. Ya están respaldadas, pero NO se quitaron:
--   la herramienta de conexión se cuelga con DROP. Es OPCIONAL: Erika puede correr el bloque 5 en el SQL Editor.
--
-- AGREGA: tabla erp_numeracion (Configuración ▸ Correlativos: desde qué número siguen los documentos NUEVOS).
-- RESPALDO tomado ANTES en el esquema respaldo_20261021 (copia completa de cada tabla tocada).
-- Para deshacer: INSERT INTO public.<tabla> SELECT * FROM respaldo_20261021.<tabla> WHERE id IN (...);
--               y para una tabla vacía: CREATE TABLE public.<tabla> (LIKE respaldo_20261021.<tabla> INCLUDING ALL);
-- =====================================================================================
BEGIN;
SET LOCAL lock_timeout = '8s';

CREATE SCHEMA IF NOT EXISTS respaldo_20261021;
CREATE TABLE IF NOT EXISTS respaldo_20261021.ordenes_compra AS SELECT * FROM public.ordenes_compra;
CREATE TABLE IF NOT EXISTS respaldo_20261021.orden_compra_detalle AS SELECT * FROM public.orden_compra_detalle;
CREATE TABLE IF NOT EXISTS respaldo_20261021.comprobantes_proveedor AS SELECT * FROM public.comprobantes_proveedor;
CREATE TABLE IF NOT EXISTS respaldo_20261021.finanzas_pagos AS SELECT * FROM public.finanzas_pagos;
CREATE TABLE IF NOT EXISTS respaldo_20261021.proveedores AS SELECT * FROM public.proveedores;
CREATE TABLE IF NOT EXISTS respaldo_20261021.proveedores_contactos AS SELECT * FROM public.proveedores_contactos;
CREATE TABLE IF NOT EXISTS respaldo_20261021.proveedores_puntos_entrega AS SELECT * FROM public.proveedores_puntos_entrega;
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['erp_alertas','listas_precios','logs_auditoria','movimientos_inventario',
                           'movimientos_stock','recuentos_inventario','revalorizaciones_inventario'] LOOP
    IF to_regclass('public.' || t) IS NOT NULL AND to_regclass('respaldo_20261021.' || t) IS NULL THEN
      EXECUTE format('CREATE TABLE respaldo_20261021.%I (LIKE public.%I INCLUDING ALL)', t, t);
      EXECUTE format('INSERT INTO respaldo_20261021.%I SELECT * FROM public.%I', t, t);
    END IF;
  END LOOP;
END $$;

-- 1) OC de prueba (sin productos en ordenes_compra_items, sin recepciones, sin movimientos)
DELETE FROM public.orden_compra_detalle WHERE id = 3 AND orden_id = 5;
DELETE FROM public.ordenes_compra
 WHERE id IN (5, 7) AND nota_compra = 'Orden de compra de prueba'
   AND NOT EXISTS (SELECT 1 FROM public.ordenes_compra_items i WHERE i.orden_compra_id = ordenes_compra.id);

-- 2) Factura de proveedor de prueba y sus pagos de prueba
DELETE FROM public.finanzas_pagos
 WHERE id IN (1, 4) AND documento_tabla = 'comprobantes_proveedor' AND tercero_nombre = 'PROVEEDOR DE PRUEBA S.A.C.';
DELETE FROM public.comprobantes_proveedor WHERE id IN (1, 2) AND proveedor_nombre = 'PROVEEDOR DE PRUEBA S.A.C.';

-- 3) Cobro anulado que apunta a una factura que ya no existe (huérfano)
DELETE FROM public.finanzas_pagos f
 WHERE f.id = 3 AND f.estado = 'Anulado' AND f.documento_tabla = 'comprobantes'
   AND NOT EXISTS (SELECT 1 FROM public.comprobantes c WHERE c.id = f.documento_id);

-- 4) Proveedores de prueba inactivos (con sus contactos y direcciones), sin ninguna compra
DELETE FROM public.proveedores_contactos WHERE proveedor_id IN (10, 22, 34, 35);
DELETE FROM public.proveedores_puntos_entrega WHERE proveedor_id IN (10, 22, 34, 35);
DELETE FROM public.proveedores p
 WHERE p.id IN (10, 22, 34, 35) AND p.activo = false
   AND NOT EXISTS (SELECT 1 FROM public.ordenes_compra o WHERE o.proveedor_id = p.id)
   AND NOT EXISTS (SELECT 1 FROM public.productos x WHERE x.proveedor_id = p.id)
   AND NOT EXISTS (SELECT 1 FROM public.costos_productos x WHERE x.proveedor_id = p.id);

-- 5) OPCIONAL (NO aplicado): quitar las tablas vacías que el ERP no usa. Para hacerlo, copiar y correr en el SQL Editor:
-- DROP TABLE IF EXISTS public.erp_alertas, public.listas_precios, public.logs_auditoria, public.movimientos_inventario,
--                      public.movimientos_stock, public.recuentos_inventario, public.revalorizaciones_inventario;

-- 6) Configuración ▸ Correlativos (la app también la crea sola si falta)
CREATE TABLE IF NOT EXISTS public.erp_numeracion (
    documento VARCHAR(20) NOT NULL,
    clave VARCHAR(120) NOT NULL DEFAULT '',
    siguiente BIGINT NOT NULL CHECK (siguiente > 0),
    actualizado_por VARCHAR(120),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (documento, clave)
);
ALTER TABLE public.erp_numeracion ENABLE ROW LEVEL SECURITY;

COMMIT;
