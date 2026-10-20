-- =====================================================================================
-- SUPABASE 011 · N° OC del cliente en la PC + condición de pago escrita igual en todo el ERP
--               + contraseña de eri01kcf cifrada
-- Aplicado en Supabase (ERP_KCF) el 19/10/2026 por Claude, con la autorización escrita de Erika
-- ("Autorización total Supabase", 19/10/2026 19:53: no borrar datos reales; si hay dudas, respaldar y luego actuar).
-- NO BORRA NADA. No toca 005-010. Se puede correr varias veces (solo cambia lo que aún no está cambiado).
--
-- RESPALDO tomado ANTES de aplicar (esquema respaldo_20261015), solo de las columnas que cambian:
--   cotizaciones_pre011, cotizaciones_eliminadas_pre011, pedido_compra_pc_pre011, clientes_pre011.
--   (La contraseña de eri01kcf NO se respalda a propósito: no se guarda una copia en texto plano.
--    La contraseña sigue siendo la misma; solo queda cifrada. Se entra igual que antes.)
--
-- VERIFICADO DESPUÉS (19/10/2026 ~20:35): conteos iguales antes y después (43 cotizaciones, 10 eliminadas, 51 clientes,
--   29 productos, 22 PC, 25 despachos, 21 guías, 26 comprobantes, 11 OC, 7 usuarios, 50 proveedores); la fecha de
--   "Modificado" más reciente de cotizaciones, PC y clientes no cambió; los 9 disparadores siguen encendidos;
--   eri01kcf quedó cifrada con bcrypt; columna oc_cliente creada.
--
-- Qué cambia:
--   1) pedido_compra_pc.oc_cliente: N° de la orden de compra del cliente (opcional). El N° PC interno lo pone el ERP.
--   2) "Credito 30 Dias" → "Crédito 30 días" (mismo significado, solo la forma de escribirlo) en cotizaciones,
--      cotizaciones eliminadas y PC. Así la factura reconoce la condición y no cae en "Contado".
--   3) Clientes que tenían "Credito 30 Dias" como condición (creados desde una cotización) pasan a
--      "Crédito aprobado" con 30 días de crédito (lo que la ficha del cliente sabe mostrar).
--   4) eri01kcf: la contraseña guardada sin cifrar pasa a bcrypt (pgcrypto), sin leerla ni mostrarla.
--   La fecha de "Modificado" de esas filas NO cambia (se apaga el disparador de updated_at solo durante el arreglo).
--   Las facturas ya emitidas NO se tocan (ver INFORME sección 17).
-- =====================================================================================
BEGIN;
SET LOCAL lock_timeout = '8s';

-- 1) N° OC del cliente en la PC
ALTER TABLE public.pedido_compra_pc ADD COLUMN IF NOT EXISTS oc_cliente VARCHAR(60);
COMMENT ON COLUMN public.pedido_compra_pc.oc_cliente IS 'N° de la orden de compra del cliente (opcional, 19/10/2026). El N° PC interno es numero.';

-- Respaldo (solo la primera vez)
CREATE SCHEMA IF NOT EXISTS respaldo_20261015;
CREATE TABLE IF NOT EXISTS respaldo_20261015.cotizaciones_pre011 AS
    SELECT id, condicion_pago, forma_pago, updated_at FROM public.cotizaciones;
CREATE TABLE IF NOT EXISTS respaldo_20261015.cotizaciones_eliminadas_pre011 AS
    SELECT id, condicion_pago FROM public.cotizaciones_eliminadas;
CREATE TABLE IF NOT EXISTS respaldo_20261015.pedido_compra_pc_pre011 AS
    SELECT id, condicion_pago, condicion_atencion, updated_at FROM public.pedido_compra_pc;
CREATE TABLE IF NOT EXISTS respaldo_20261015.clientes_pre011 AS
    SELECT id, condicion_pago, dias_credito, updated_at FROM public.clientes;

-- 2) y 3) Condición escrita igual
ALTER TABLE public.cotizaciones DISABLE TRIGGER trg_tocar_updated_at;
ALTER TABLE public.pedido_compra_pc DISABLE TRIGGER trg_tocar_updated_at;
ALTER TABLE public.clientes DISABLE TRIGGER trg_tocar_updated_at;

UPDATE public.cotizaciones
   SET condicion_pago = regexp_replace(condicion_pago, '^\s*cr[eé]dito\s+(a\s+)?(\d+)\s*d[ií]as?\s*$', 'Crédito \2 días', 'i')
 WHERE condicion_pago ~* '^\s*cr[eé]dito\s+(a\s+)?\d+\s*d[ií]as?\s*$' AND condicion_pago !~ '^Crédito \d+ días$';
UPDATE public.cotizaciones
   SET forma_pago = regexp_replace(forma_pago, '^\s*cr[eé]dito\s+(a\s+)?(\d+)\s*d[ií]as?\s*$', 'Crédito \2 días', 'i')
 WHERE forma_pago ~* '^\s*cr[eé]dito\s+(a\s+)?\d+\s*d[ií]as?\s*$' AND forma_pago !~ '^Crédito \d+ días$';
UPDATE public.cotizaciones_eliminadas
   SET condicion_pago = regexp_replace(condicion_pago, '^\s*cr[eé]dito\s+(a\s+)?(\d+)\s*d[ií]as?\s*$', 'Crédito \2 días', 'i')
 WHERE condicion_pago ~* '^\s*cr[eé]dito\s+(a\s+)?\d+\s*d[ií]as?\s*$' AND condicion_pago !~ '^Crédito \d+ días$';
UPDATE public.pedido_compra_pc
   SET condicion_pago = regexp_replace(condicion_pago, '^\s*cr[eé]dito\s+(a\s+)?(\d+)\s*d[ií]as?\s*$', 'Crédito \2 días', 'i')
 WHERE condicion_pago ~* '^\s*cr[eé]dito\s+(a\s+)?\d+\s*d[ií]as?\s*$' AND condicion_pago !~ '^Crédito \d+ días$';
UPDATE public.pedido_compra_pc
   SET condicion_atencion = regexp_replace(condicion_atencion, '^\s*cr[eé]dito\s+(a\s+)?(\d+)\s*d[ií]as?\s*$', 'Crédito \2 días', 'i')
 WHERE condicion_atencion ~* '^\s*cr[eé]dito\s+(a\s+)?\d+\s*d[ií]as?\s*$' AND condicion_atencion !~ '^Crédito \d+ días$';
UPDATE public.clientes
   SET dias_credito = (regexp_match(condicion_pago, '(\d+)'))[1]::int,
       condicion_pago = 'Crédito aprobado'
 WHERE condicion_pago ~* '^\s*cr[eé]dito\s+(a\s+)?\d+\s*d[ií]as?\s*$' AND COALESCE(dias_credito, 0) = 0;

ALTER TABLE public.cotizaciones ENABLE TRIGGER trg_tocar_updated_at;
ALTER TABLE public.pedido_compra_pc ENABLE TRIGGER trg_tocar_updated_at;
ALTER TABLE public.clientes ENABLE TRIGGER trg_tocar_updated_at;

-- 4) eri01kcf: contraseña cifrada (la misma contraseña; no se lee ni se muestra)
UPDATE public.usuarios
   SET password = extensions.crypt(password, extensions.gen_salt('bf', 12))
 WHERE id = 10 AND usuario = 'eri01kcf'
   AND password IS NOT NULL AND password <> ''
   AND password !~ '^(\$2[aby]\$|scrypt:|pbkdf2:)';

COMMIT;

-- =====================================================================================
-- CÓMO DESHACER (copiar y correr en el SQL Editor de Supabase):
--   BEGIN;
--   ALTER TABLE public.cotizaciones DISABLE TRIGGER trg_tocar_updated_at;
--   ALTER TABLE public.pedido_compra_pc DISABLE TRIGGER trg_tocar_updated_at;
--   ALTER TABLE public.clientes DISABLE TRIGGER trg_tocar_updated_at;
--   UPDATE public.cotizaciones c SET condicion_pago = r.condicion_pago, forma_pago = r.forma_pago
--     FROM respaldo_20261015.cotizaciones_pre011 r WHERE r.id = c.id;
--   UPDATE public.cotizaciones_eliminadas c SET condicion_pago = r.condicion_pago
--     FROM respaldo_20261015.cotizaciones_eliminadas_pre011 r WHERE r.id = c.id;
--   UPDATE public.pedido_compra_pc p SET condicion_pago = r.condicion_pago, condicion_atencion = r.condicion_atencion
--     FROM respaldo_20261015.pedido_compra_pc_pre011 r WHERE r.id = p.id;
--   UPDATE public.clientes c SET condicion_pago = r.condicion_pago, dias_credito = r.dias_credito
--     FROM respaldo_20261015.clientes_pre011 r WHERE r.id = c.id;
--   ALTER TABLE public.cotizaciones ENABLE TRIGGER trg_tocar_updated_at;
--   ALTER TABLE public.pedido_compra_pc ENABLE TRIGGER trg_tocar_updated_at;
--   ALTER TABLE public.clientes ENABLE TRIGGER trg_tocar_updated_at;
--   -- La columna oc_cliente se puede dejar (vacía no molesta). Para quitarla:
--   -- ALTER TABLE public.pedido_compra_pc DROP COLUMN IF EXISTS oc_cliente;
--   COMMIT;
--   (La contraseña cifrada de eri01kcf no se deshace: si hiciera falta, el administrador le pone una nueva
--    con el botón "🔑 Nueva contraseña" en Configuración ▸ Usuarios.)
-- =====================================================================================
