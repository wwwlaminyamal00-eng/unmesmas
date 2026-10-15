-- ============================================================================
-- 007 - Multiempresa (KCF / AGD / Todas), datos de empresa para rótulos y PDF (ERP_KCF)
-- ============================================================================
-- ESTADO: APLICADO en Supabase el 15/10/2026 con la autorización escrita de Erika
--         (mensaje "CORRECCIÓN DE BUGS + MULTIEMPRESA + COLORES + RÓTULOS").
--
-- Qué hace (en simple):
--   1. RESPALDA las tablas que se van a tocar (copias en el esquema respaldo_20261015, sufijo _pre007).
--   2. AGREGA la columna empresa_id (UUID, igual que erp_empresas.id) a los documentos y maestros
--      que no la tenían, con su índice.
--   3. AGREGA a erp_empresas: pagina_web, correo_rotulo, ubigeo (para rótulos y PDF).
--   4. RELLENA empresa_id de los documentos que ya existen. Toda la evidencia dice KCF:
--      columna "empresa" = 'KCF' en PC, despachos y NC; guías con RUC remitente de KCF;
--      facturas F001 de KCF; OC y facturas de proveedor sin empresa -> KCF.
--      Clientes: ambito 'KCF' -> KCF; 'COMPARTIDO' queda sin empresa (= lo ven las dos).
--      Proveedores y productos quedan sin empresa (compartidos). Solicitudes de compra: sin empresa.
--   NO borra nada. NO toca lo aplicado en 005 y 006 (RLS, stock automático).
--   El stock NO se mueve: la tabla oficial ya es inv_stock (por empresa + sede); las tablas
--   antiguas de stock están vacías (ver el final).
-- ============================================================================

-- 1) RESPALDO ----------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS respaldo_20261015;
CREATE TABLE IF NOT EXISTS respaldo_20261015.cotizaciones_pre007          AS SELECT * FROM public.cotizaciones;
CREATE TABLE IF NOT EXISTS respaldo_20261015.pedido_compra_pc_pre007      AS SELECT * FROM public.pedido_compra_pc;
CREATE TABLE IF NOT EXISTS respaldo_20261015.despachos_pre007             AS SELECT * FROM public.despachos;
CREATE TABLE IF NOT EXISTS respaldo_20261015.guias_remision_pre007        AS SELECT * FROM public.guias_remision;
CREATE TABLE IF NOT EXISTS respaldo_20261015.comprobantes_pre007          AS SELECT * FROM public.comprobantes;
CREATE TABLE IF NOT EXISTS respaldo_20261015.notas_credito_pre007         AS SELECT * FROM public.notas_credito;
CREATE TABLE IF NOT EXISTS respaldo_20261015.devoluciones_pre007          AS SELECT * FROM public.devoluciones;
CREATE TABLE IF NOT EXISTS respaldo_20261015.finanzas_pagos_pre007        AS SELECT * FROM public.finanzas_pagos;
CREATE TABLE IF NOT EXISTS respaldo_20261015.ordenes_compra_pre007        AS SELECT * FROM public.ordenes_compra;
CREATE TABLE IF NOT EXISTS respaldo_20261015.comprobantes_proveedor_pre007 AS SELECT * FROM public.comprobantes_proveedor;
CREATE TABLE IF NOT EXISTS respaldo_20261015.clientes_pre007              AS SELECT * FROM public.clientes;
CREATE TABLE IF NOT EXISTS respaldo_20261015.erp_empresas_pre007          AS SELECT * FROM public.erp_empresas;

-- 2) COLUMNAS NUEVAS -----------------------------------------------------------
ALTER TABLE public.cotizaciones       ADD COLUMN IF NOT EXISTS empresa_id UUID;
ALTER TABLE public.pedido_compra_pc   ADD COLUMN IF NOT EXISTS empresa_id UUID;
ALTER TABLE public.despachos          ADD COLUMN IF NOT EXISTS empresa_id UUID;
ALTER TABLE public.guias_remision     ADD COLUMN IF NOT EXISTS empresa_id UUID;
ALTER TABLE public.comprobantes       ADD COLUMN IF NOT EXISTS empresa_id UUID;
ALTER TABLE public.notas_credito      ADD COLUMN IF NOT EXISTS empresa_id UUID;
ALTER TABLE public.devoluciones       ADD COLUMN IF NOT EXISTS empresa_id UUID;
ALTER TABLE public.finanzas_pagos     ADD COLUMN IF NOT EXISTS empresa_id UUID;
ALTER TABLE public.solicitudes_compra ADD COLUMN IF NOT EXISTS empresa_id UUID;
ALTER TABLE public.clientes           ADD COLUMN IF NOT EXISTS empresa_id UUID;
ALTER TABLE public.proveedores        ADD COLUMN IF NOT EXISTS empresa_id UUID;
ALTER TABLE public.productos          ADD COLUMN IF NOT EXISTS empresa_id UUID;
-- (ordenes_compra, recepciones_mercaderia y comprobantes_proveedor ya la tenían)

CREATE INDEX IF NOT EXISTS idx_cotizaciones_empresa_id           ON public.cotizaciones (empresa_id);
CREATE INDEX IF NOT EXISTS idx_pedido_compra_pc_empresa_id       ON public.pedido_compra_pc (empresa_id);
CREATE INDEX IF NOT EXISTS idx_despachos_empresa_id              ON public.despachos (empresa_id);
CREATE INDEX IF NOT EXISTS idx_guias_remision_empresa_id         ON public.guias_remision (empresa_id);
CREATE INDEX IF NOT EXISTS idx_comprobantes_empresa_id           ON public.comprobantes (empresa_id);
CREATE INDEX IF NOT EXISTS idx_notas_credito_empresa_id          ON public.notas_credito (empresa_id);
CREATE INDEX IF NOT EXISTS idx_devoluciones_empresa_id           ON public.devoluciones (empresa_id);
CREATE INDEX IF NOT EXISTS idx_finanzas_pagos_empresa_id         ON public.finanzas_pagos (empresa_id);
CREATE INDEX IF NOT EXISTS idx_solicitudes_compra_empresa_id     ON public.solicitudes_compra (empresa_id);
CREATE INDEX IF NOT EXISTS idx_clientes_empresa_id               ON public.clientes (empresa_id);
CREATE INDEX IF NOT EXISTS idx_proveedores_empresa_id            ON public.proveedores (empresa_id);
CREATE INDEX IF NOT EXISTS idx_productos_empresa_id              ON public.productos (empresa_id);
CREATE INDEX IF NOT EXISTS idx_ordenes_compra_empresa_id         ON public.ordenes_compra (empresa_id);
CREATE INDEX IF NOT EXISTS idx_recepciones_mercaderia_empresa_id ON public.recepciones_mercaderia (empresa_id);
CREATE INDEX IF NOT EXISTS idx_comprobantes_proveedor_empresa_id ON public.comprobantes_proveedor (empresa_id);

ALTER TABLE public.erp_empresas ADD COLUMN IF NOT EXISTS pagina_web TEXT;
ALTER TABLE public.erp_empresas ADD COLUMN IF NOT EXISTS correo_rotulo TEXT;
ALTER TABLE public.erp_empresas ADD COLUMN IF NOT EXISTS ubigeo TEXT;

-- 3) DATOS DE EMPRESA PARA RÓTULOS / PDF (solo si están vacíos) -----------------
UPDATE public.erp_empresas SET pagina_web = 'https://kcfcorporacion.com/'   WHERE codigo = 'KCF' AND pagina_web IS NULL;
UPDATE public.erp_empresas SET correo_rotulo = 'ventas@kcfcorporacion.com' WHERE codigo = 'KCF' AND correo_rotulo IS NULL;
UPDATE public.erp_empresas SET ubigeo = '150139' WHERE codigo = 'KCF' AND ubigeo IS NULL;  -- el que usaba el ERP (revisar: SMP podría ser 150135)
UPDATE public.erp_empresas SET ubigeo = '150105' WHERE codigo = 'AGD' AND ubigeo IS NULL;  -- Breña

-- 4) RELLENAR LA EMPRESA DE LO QUE YA EXISTE (solo filas sin empresa) ----------
UPDATE public.pedido_compra_pc d SET empresa_id = e.id FROM public.erp_empresas e
 WHERE d.empresa_id IS NULL AND UPPER(COALESCE(d.empresa, 'KCF')) = e.codigo;
UPDATE public.despachos d SET empresa_id = e.id FROM public.erp_empresas e
 WHERE d.empresa_id IS NULL AND UPPER(COALESCE(d.empresa, 'KCF')) = e.codigo;
UPDATE public.notas_credito d SET empresa_id = e.id FROM public.erp_empresas e
 WHERE d.empresa_id IS NULL AND UPPER(COALESCE(d.empresa, 'KCF')) = e.codigo;
UPDATE public.devoluciones d SET empresa_id = e.id FROM public.erp_empresas e
 WHERE d.empresa_id IS NULL AND UPPER(COALESCE(d.empresa, 'KCF')) = e.codigo;
UPDATE public.guias_remision g SET empresa_id = e.id FROM public.erp_empresas e
 WHERE g.empresa_id IS NULL AND e.ruc = g.ruc_remitente;
UPDATE public.guias_remision SET empresa_id = (SELECT id FROM public.erp_empresas WHERE codigo = 'KCF') WHERE empresa_id IS NULL;
UPDATE public.cotizaciones          SET empresa_id = (SELECT id FROM public.erp_empresas WHERE codigo = 'KCF') WHERE empresa_id IS NULL;
UPDATE public.comprobantes          SET empresa_id = (SELECT id FROM public.erp_empresas WHERE codigo = 'KCF') WHERE empresa_id IS NULL;
UPDATE public.ordenes_compra        SET empresa_id = (SELECT id FROM public.erp_empresas WHERE codigo = 'KCF') WHERE empresa_id IS NULL;
UPDATE public.comprobantes_proveedor SET empresa_id = (SELECT id FROM public.erp_empresas WHERE codigo = 'KCF') WHERE empresa_id IS NULL;
-- Cobros y pagos: la empresa de su documento
UPDATE public.finanzas_pagos p SET empresa_id = c.empresa_id FROM public.comprobantes c
 WHERE p.empresa_id IS NULL AND p.documento_tabla = 'comprobantes' AND c.id = p.documento_id;
UPDATE public.finanzas_pagos p SET empresa_id = c.empresa_id FROM public.comprobantes_proveedor c
 WHERE p.empresa_id IS NULL AND p.documento_tabla = 'comprobantes_proveedor' AND c.id = p.documento_id;
UPDATE public.finanzas_pagos p SET empresa_id = o.empresa_id FROM public.ordenes_compra o
 WHERE p.empresa_id IS NULL AND p.documento_tabla = 'ordenes_compra' AND o.id = p.documento_id;
-- Clientes solo de una empresa
UPDATE public.clientes c SET empresa_id = e.id FROM public.erp_empresas e
 WHERE c.empresa_id IS NULL AND UPPER(c.ambito) = e.codigo;

-- ============================================================================
-- TABLAS ANTIGUAS DE STOCK (NO se borraron)
-- ============================================================================
-- inventario, movimientos_inventario, movimientos_stock, recuentos_inventario y
-- revalorizaciones_inventario están VACÍAS (0 filas) y el ERP ya no las usa. La fuente de verdad
-- del stock es inv_stock (empresa + sede + producto) y el kardex es inv_movimientos.
-- Ya están respaldadas en respaldo_20261015. Si quieres borrarlas, en el SQL Editor de Supabase:
--   DROP TABLE public.revalorizaciones_inventario, public.recuentos_inventario,
--              public.movimientos_stock, public.movimientos_inventario, public.inventario;
-- (inv_sede_empresa también está vacía pero el ERP SÍ la usa: NO borrarla.)

-- ============================================================================
-- CÓMO DESHACER (en el SQL Editor de Supabase)
-- ============================================================================
-- a) Volver a dejar la empresa como estaba (las columnas nuevas quedan vacías):
--    UPDATE public.ordenes_compra o SET empresa_id = r.empresa_id
--      FROM respaldo_20261015.ordenes_compra_pre007 r WHERE r.id = o.id;
--    UPDATE public.comprobantes_proveedor o SET empresa_id = r.empresa_id
--      FROM respaldo_20261015.comprobantes_proveedor_pre007 r WHERE r.id = o.id;
-- b) Quitar las columnas nuevas (y sus índices se van con ellas):
--    ALTER TABLE public.cotizaciones DROP COLUMN empresa_id;      -- igual para pedido_compra_pc,
--    despachos, guias_remision, comprobantes, notas_credito, devoluciones, finanzas_pagos,
--    solicitudes_compra, clientes, proveedores, productos
--    ALTER TABLE public.erp_empresas DROP COLUMN pagina_web, DROP COLUMN correo_rotulo, DROP COLUMN ubigeo;
--    DROP INDEX public.idx_ordenes_compra_empresa_id, public.idx_recepciones_mercaderia_empresa_id,
--               public.idx_comprobantes_proveedor_empresa_id;
-- c) Volver a la versión anterior del ERP (pruebasweb_corregido_anterior_15oct_stock.zip).
-- Los respaldos *_pre007 se pueden borrar cuando todo esté probado.
