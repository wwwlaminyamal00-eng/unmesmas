-- =====================================================================================
-- SUPABASE 012 · Facturas antiguas que salieron "Contado" aunque su PC era a crédito
--               + "Entrega" por producto de la cotización: solo Pendiente o Entregado
-- Aplicado en Supabase (ERP_KCF) el 20/10/2026 por Claude.
-- Autorización: Erika eligió "Corregir" en la tarjeta "¿Corrijo la condición de pago de las facturas antiguas
--   que salieron Contado?" (20/10/2026 14:19): "Cada factura toma la condición de su PC, con respaldo previo y
--   anotado en la auditoría". Y su pedido del 20/10/2026 14:19 ("Te autorizo a modificar la base de datos...").
-- NO BORRA NADA. No toca 005-011. Se puede correr varias veces (solo cambia lo que todavía dice "Contado").
--
-- RESPALDO tomado ANTES de aplicar: respaldo_20261015.comprobantes_pre012
--   (id, serie, numero, condicion_pago, dias_credito, es_credito, fecha_vencimiento, estado_credito, updated_at).
--
-- Qué cambia:
--   1) 9 facturas/boletas cuyo PC está claro (vinculado en la factura, o el único PC de su guía) toman la
--      condición de ese PC: condicion_pago "Crédito N días", dias_credito N, es_credito true y
--      fecha_vencimiento = fecha de emisión + N días (así Cuentas por cobrar calcula bien el vencimiento).
--      NO se toca el total, los productos, el estado SUNAT ni el estado del crédito.
--      Cada cambio queda en Papelera / Auditoría (erp_auditoria) con el antes y el después.
--   2) cotizacion_detalle.estado_entrega solo acepta 'Pendiente' o 'Entregado' (hoy todas dicen Pendiente).
--
-- Facturas que NO se tocan por no tener un PC claro (lista en INFORME sección 18):
--   F001-86773596 (su PC vinculado y el de su cotización no coinciden), F001-87021168, F001-87039526, F001-71235956
--   (sin PC), F001-87373429, F001-87709785, F001-88095381, F001-88187484, F001-20484920, F001-20639564 (solo
--   tienen cotización, sin PC ni guía), F001-32079376 (su cotización tiene dos PC: 120 y 90 días).
-- =====================================================================================
BEGIN;
SET LOCAL lock_timeout = '8s';

CREATE SCHEMA IF NOT EXISTS respaldo_20261015;
CREATE TABLE IF NOT EXISTS respaldo_20261015.comprobantes_pre012 AS
    SELECT id, serie, numero, condicion_pago, dias_credito, es_credito, fecha_vencimiento, estado_credito, updated_at
      FROM public.comprobantes;

-- 1) Condición desde el PC (id + número, para no tocar otra factura por error)
CREATE TEMP TABLE _cond012 (id int, nro text, pc text, dias int) ON COMMIT DROP;
INSERT INTO _cond012 VALUES
    (18, 'F001-52860405', 'PC-20260720-4955',   30),
    (19, 'F001-22960633', 'PC-20260717-2000',   15),
    (28, 'F001-69427205', 'PC-20260826-5555',   15),
    (30, 'F001-48252945', 'PC-20260826-5555',   15),   -- PC de su guía T001-48193830
    (37, 'F001-88187485', 'PC-20260826-555510', 30),
    (42, 'F001-88187486', 'PC-20261016-00001',  45),
    (47, 'F001-88187490', '2040808080',         30),
    (48, 'F001-88187491', 'PC-20260720-495500', 90),
    (50, 'F001-88187493', 'PC-20261019-0001',   45);

-- Solo si el PC sigue diciendo esos días y la factura todavía dice Contado
CREATE TEMP TABLE _hacer012 ON COMMIT DROP AS
SELECT c.id, x.nro, x.pc, x.dias, to_jsonb(c) AS antes
  FROM public.comprobantes c
  JOIN _cond012 x ON x.id = c.id AND (c.serie || '-' || c.numero) = x.nro
  JOIN public.pedido_compra_pc p ON p.numero = x.pc
 WHERE COALESCE(c.condicion_pago, '') ~* '^\s*(contado)?\s*$'
   AND p.condicion_pago = 'Crédito ' || x.dias || ' días';

UPDATE public.comprobantes c
   SET condicion_pago = 'Crédito ' || h.dias || ' días',
       dias_credito = h.dias,
       es_credito = TRUE,
       fecha_vencimiento = c.fecha_emision::date + h.dias
  FROM _hacer012 h
 WHERE c.id = h.id;

INSERT INTO public.erp_auditoria (empresa_id, tabla, registro_id, accion, data_anterior, data_nueva,
                                  usuario_nombre, modulo, detalle)
SELECT c.empresa_id, 'comprobantes', c.id::text, 'CORRECCION_CONDICION_PAGO',
       jsonb_build_object('condicion_pago', h.antes ->> 'condicion_pago', 'dias_credito', h.antes -> 'dias_credito',
                          'es_credito', h.antes -> 'es_credito', 'fecha_vencimiento', h.antes -> 'fecha_vencimiento'),
       jsonb_build_object('condicion_pago', c.condicion_pago, 'dias_credito', c.dias_credito,
                          'es_credito', c.es_credito, 'fecha_vencimiento', c.fecha_vencimiento),
       'Claude (migración 012, autorizado por Erika el 20/10/2026)', 'Ventas',
       'Factura ' || h.nro || ': decía Contado; toma la condición de su PC ' || h.pc || ' (Crédito ' || h.dias || ' días).'
  FROM _hacer012 h JOIN public.comprobantes c ON c.id = h.id;

-- 2) Entrega por producto: solo Pendiente o Entregado (se crea una sola vez)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_cotizacion_detalle_estado_entrega') THEN
        ALTER TABLE public.cotizacion_detalle ADD CONSTRAINT chk_cotizacion_detalle_estado_entrega
            CHECK (estado_entrega IS NULL OR estado_entrega IN ('Pendiente', 'Entregado'));
    END IF;
END $$;

COMMIT;

-- =====================================================================================
-- CÓMO DESHACER (devuelve las facturas a como estaban; el respaldo queda):
--   BEGIN;
--   UPDATE public.comprobantes c
--      SET condicion_pago = r.condicion_pago, dias_credito = r.dias_credito, es_credito = r.es_credito,
--          fecha_vencimiento = r.fecha_vencimiento
--     FROM respaldo_20261015.comprobantes_pre012 r
--    WHERE r.id = c.id AND c.id IN (18, 19, 28, 30, 37, 42, 47, 48, 50);
--   ALTER TABLE public.cotizacion_detalle DROP CONSTRAINT IF EXISTS chk_cotizacion_detalle_estado_entrega;
--   COMMIT;
-- =====================================================================================
