-- ============================================================================
-- SUPABASE ERP_KCF - TODOS LOS CAMBIOS APLICADOS EL 15/10/2026 (respaldo completo)
-- Autorización: SUPABASE.txt de Erika (por escrito).
-- Orden en que se aplicaron:
--   PASO 0. Respaldo de las 66 tablas (esquema respaldo_20261015)
--   PASO 1. Migración 005 (seguridad y rendimiento) -> en Supabase: 005a ... 005f
--   PASO 2. Migración 006 (stock automático)          -> en Supabase: 006_stock_automatico
-- Ningún paso borró datos. Conteos verificados antes y después (ver INFORME_CAMBIOS.md sección 11).
-- ============================================================================

-- ============================================================================
-- PASO 0. RESPALDO (equivale a "CREATE TABLE backup_[tabla]_[fecha] AS SELECT * FROM [tabla]",
-- pero dentro de un esquema aparte que la API de Supabase no publica)
-- ============================================================================
CREATE SCHEMA IF NOT EXISTS respaldo_20261015;
CREATE TABLE respaldo_20261015.almacenes AS SELECT * FROM public.almacenes;
CREATE TABLE respaldo_20261015.categorias AS SELECT * FROM public.categorias;
CREATE TABLE respaldo_20261015.clientes AS SELECT * FROM public.clientes;
CREATE TABLE respaldo_20261015.clientes_contactos AS SELECT * FROM public.clientes_contactos;
CREATE TABLE respaldo_20261015.clientes_puntos_entrega AS SELECT * FROM public.clientes_puntos_entrega;
CREATE TABLE respaldo_20261015.com_historial AS SELECT * FROM public.com_historial;
CREATE TABLE respaldo_20261015.com_incidencias AS SELECT * FROM public.com_incidencias;
CREATE TABLE respaldo_20261015.com_recepcion_items AS SELECT * FROM public.com_recepcion_items;
CREATE TABLE respaldo_20261015.com_recepciones AS SELECT * FROM public.com_recepciones;
CREATE TABLE respaldo_20261015.comparativos_proveedores AS SELECT * FROM public.comparativos_proveedores;
CREATE TABLE respaldo_20261015.comprobantes AS SELECT * FROM public.comprobantes;
CREATE TABLE respaldo_20261015.comprobantes_compra AS SELECT * FROM public.comprobantes_compra;
CREATE TABLE respaldo_20261015.comprobantes_proveedor AS SELECT * FROM public.comprobantes_proveedor;
CREATE TABLE respaldo_20261015.costos_productos AS SELECT * FROM public.costos_productos;
CREATE TABLE respaldo_20261015.cotizacion_detalle AS SELECT * FROM public.cotizacion_detalle;
CREATE TABLE respaldo_20261015.cotizaciones AS SELECT * FROM public.cotizaciones;
CREATE TABLE respaldo_20261015.cotizaciones_eliminadas AS SELECT * FROM public.cotizaciones_eliminadas;
CREATE TABLE respaldo_20261015.despacho_productos AS SELECT * FROM public.despacho_productos;
CREATE TABLE respaldo_20261015.despachos AS SELECT * FROM public.despachos;
CREATE TABLE respaldo_20261015.devoluciones AS SELECT * FROM public.devoluciones;
CREATE TABLE respaldo_20261015.erp_alertas AS SELECT * FROM public.erp_alertas;
CREATE TABLE respaldo_20261015.erp_auditoria AS SELECT * FROM public.erp_auditoria;
CREATE TABLE respaldo_20261015.erp_correlativos AS SELECT * FROM public.erp_correlativos;
CREATE TABLE respaldo_20261015.erp_empresa_cuentas_bancarias AS SELECT * FROM public.erp_empresa_cuentas_bancarias;
CREATE TABLE respaldo_20261015.erp_empresas AS SELECT * FROM public.erp_empresas;
CREATE TABLE respaldo_20261015.erp_modulos AS SELECT * FROM public.erp_modulos;
CREATE TABLE respaldo_20261015.erp_parametros AS SELECT * FROM public.erp_parametros;
CREATE TABLE respaldo_20261015.erp_rol_permisos AS SELECT * FROM public.erp_rol_permisos;
CREATE TABLE respaldo_20261015.erp_roles AS SELECT * FROM public.erp_roles;
CREATE TABLE respaldo_20261015.erp_submodulos AS SELECT * FROM public.erp_submodulos;
CREATE TABLE respaldo_20261015.erp_usuario_empresas AS SELECT * FROM public.erp_usuario_empresas;
CREATE TABLE respaldo_20261015.erp_usuario_permisos AS SELECT * FROM public.erp_usuario_permisos;
CREATE TABLE respaldo_20261015.finanzas_pagos AS SELECT * FROM public.finanzas_pagos;
CREATE TABLE respaldo_20261015.guias_remision AS SELECT * FROM public.guias_remision;
CREATE TABLE respaldo_20261015.guias_remision_compra AS SELECT * FROM public.guias_remision_compra;
CREATE TABLE respaldo_20261015.inv_conteo_items AS SELECT * FROM public.inv_conteo_items;
CREATE TABLE respaldo_20261015.inv_conteos AS SELECT * FROM public.inv_conteos;
CREATE TABLE respaldo_20261015.inv_movimientos AS SELECT * FROM public.inv_movimientos;
CREATE TABLE respaldo_20261015.inv_sede_empresa AS SELECT * FROM public.inv_sede_empresa;
CREATE TABLE respaldo_20261015.inv_separaciones AS SELECT * FROM public.inv_separaciones;
CREATE TABLE respaldo_20261015.inv_stock AS SELECT * FROM public.inv_stock;
CREATE TABLE respaldo_20261015.inv_traslado_items AS SELECT * FROM public.inv_traslado_items;
CREATE TABLE respaldo_20261015.inv_traslados AS SELECT * FROM public.inv_traslados;
CREATE TABLE respaldo_20261015.inventario AS SELECT * FROM public.inventario;
CREATE TABLE respaldo_20261015.listas_precios AS SELECT * FROM public.listas_precios;
CREATE TABLE respaldo_20261015.logs_auditoria AS SELECT * FROM public.logs_auditoria;
CREATE TABLE respaldo_20261015.marcas AS SELECT * FROM public.marcas;
CREATE TABLE respaldo_20261015.movimientos_inventario AS SELECT * FROM public.movimientos_inventario;
CREATE TABLE respaldo_20261015.movimientos_stock AS SELECT * FROM public.movimientos_stock;
CREATE TABLE respaldo_20261015.notas_credito AS SELECT * FROM public.notas_credito;
CREATE TABLE respaldo_20261015.orden_compra_detalle AS SELECT * FROM public.orden_compra_detalle;
CREATE TABLE respaldo_20261015.ordenes_compra AS SELECT * FROM public.ordenes_compra;
CREATE TABLE respaldo_20261015.ordenes_compra_items AS SELECT * FROM public.ordenes_compra_items;
CREATE TABLE respaldo_20261015.pedido_compra_pc AS SELECT * FROM public.pedido_compra_pc;
CREATE TABLE respaldo_20261015.precios_productos AS SELECT * FROM public.precios_productos;
CREATE TABLE respaldo_20261015.productos AS SELECT * FROM public.productos;
CREATE TABLE respaldo_20261015.proveedores AS SELECT * FROM public.proveedores;
CREATE TABLE respaldo_20261015.proveedores_contactos AS SELECT * FROM public.proveedores_contactos;
CREATE TABLE respaldo_20261015.proveedores_puntos_entrega AS SELECT * FROM public.proveedores_puntos_entrega;
CREATE TABLE respaldo_20261015.recepciones_mercaderia AS SELECT * FROM public.recepciones_mercaderia;
CREATE TABLE respaldo_20261015.recuentos_inventario AS SELECT * FROM public.recuentos_inventario;
CREATE TABLE respaldo_20261015.revalorizaciones_inventario AS SELECT * FROM public.revalorizaciones_inventario;
CREATE TABLE respaldo_20261015.solicitudes_compra AS SELECT * FROM public.solicitudes_compra;
CREATE TABLE respaldo_20261015.transportistas AS SELECT * FROM public.transportistas;
CREATE TABLE respaldo_20261015.um AS SELECT * FROM public.um;
CREATE TABLE respaldo_20261015.usuarios AS SELECT * FROM public.usuarios;
REVOKE ALL ON SCHEMA respaldo_20261015 FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA respaldo_20261015 FROM PUBLIC, anon, authenticated;
-- Para recuperar una tabla:  INSERT INTO public.<tabla> SELECT * FROM respaldo_20261015.<tabla> WHERE ...;
-- Para borrar el respaldo cuando ya no haga falta (dentro de unas semanas):  DROP SCHEMA respaldo_20261015 CASCADE;

-- ============================================================================
-- PASO 1. MIGRACIÓN 005
-- ============================================================================
-- ============================================================================
-- 005 - Seguridad y rendimiento para Supabase (ERP_KCF)
-- ============================================================================
-- ESTADO: APLICADO en Supabase el 15/10/2026 con la autorización escrita de Erika (SUPABASE.txt),
-- en 6 partes (005a ... 005f en supabase_migrations). Respaldo previo de las 66 tablas (datos completos):
-- esquema respaldo_20261015 (no expuesto a la API).
-- DIFERENCIA con la propuesta: la herramienta de Supabase no deja ejecutar DROP sin una confirmación
-- manual, así que los 2 disparadores repetidos se DESACTIVARON (mismo efecto, más fácil de revertir)
-- y los 3 índices duplicados quedan PENDIENTES (ver final del punto E: Erika puede ejecutarlos en el
-- SQL Editor de Supabase; no afectan datos, solo ocupan espacio).
-- Extra (G): la vista vista_comparativo_costos dejaba leer costos saltándose el candado; ahora respeta RLS.
--
-- Qué hace y por qué (en simple):
--   A. Pone "candado" (RLS) a 5 tablas que hoy cualquiera con la anon key puede leer y cambiar
--      (pagos y recepciones de Compras). El ERP NO se ve afectado: se conecta como dueño de la base.
--   B. Quita a usuarios anónimos (sin iniciar sesión) el permiso de ejecutar 5 funciones internas
--      (una de ellas, erp_link_usuario, crea administradores con contraseña fija).
--   C. Fija el search_path de las funciones (recomendación de seguridad de Supabase).
--   D. Agrega 4 índices que usan las pantallas nuevas (abastecimiento, guías, cotizaciones).
--   E. Quita 2 disparadores repetidos en clientes y 3 índices duplicados en ordenes_compra.
--   F. Corrige erp_link_usuario: ya no crea ADMINISTRADORES con contraseña 123456 ni pisa la
--      contraseña y el rol de un usuario que ya existe. El usuario nuevo queda como vendedor,
--      INACTIVO y sin contraseña usable, hasta que un administrador lo active desde el ERP.
-- Nada de esto borra ni cambia datos. Todo se puede deshacer (ver el final del archivo).
-- ============================================================================

BEGIN;

-- A. RLS (candado) en las 5 tablas que no lo tienen
ALTER TABLE public.finanzas_pagos      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.com_recepciones     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.com_recepcion_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.com_incidencias     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.com_historial       ENABLE ROW LEVEL SECURITY;

-- B. Funciones SECURITY DEFINER: nadie de afuera (anon / authenticated) las ejecuta por la API
REVOKE EXECUTE ON FUNCTION public.erp_link_usuario(text, text, text, text)        FROM anon, authenticated, public;
REVOKE EXECUTE ON FUNCTION public.erp_tomar_correlativo(text, text, integer)       FROM anon, public;
REVOKE EXECUTE ON FUNCTION public.erp_has_perm(uuid, text, text)                   FROM anon, public;
REVOKE EXECUTE ON FUNCTION public.erp_has_empresa_access(uuid)                     FROM anon, public;
REVOKE EXECUTE ON FUNCTION public.erp_is_super_admin()                             FROM anon, public;

-- C. search_path fijo
ALTER FUNCTION public.generar_codigo_proveedor()      SET search_path = public;
ALTER FUNCTION public.actualizar_stock_kardex()       SET search_path = public;
ALTER FUNCTION public.generar_numero_orden()          SET search_path = public;
ALTER FUNCTION public.actualizar_updated_at_column()  SET search_path = public;
ALTER FUNCTION public.generar_codigo_orden_oficial(integer) SET search_path = public;
ALTER FUNCTION public.generar_codigo_cliente()        SET search_path = public;
ALTER FUNCTION public.update_updated_at_column()      SET search_path = public;
ALTER FUNCTION public.erp_touch_updated_at()          SET search_path = public;
ALTER FUNCTION public.erp_siguiente_correlativo(uuid) SET search_path = public;

-- D. Índices para las consultas nuevas
CREATE INDEX IF NOT EXISTS idx_oci_producto           ON public.ordenes_compra_items (producto_id);
CREATE INDEX IF NOT EXISTS idx_cot_detalle_cotizacion ON public.cotizacion_detalle (cotizacion_id);
CREATE INDEX IF NOT EXISTS idx_cot_detalle_producto   ON public.cotizacion_detalle (producto_id);
CREATE INDEX IF NOT EXISTS idx_comprobantes_guia      ON public.comprobantes (guia_vinculada);

-- E. Repetidos (la misma función se ejecutaba 3 veces al crear un cliente)
ALTER TABLE public.clientes DISABLE TRIGGER tr_generar_codigo_cliente;   -- queda activo trigger_generar_codigo
ALTER TABLE public.clientes DISABLE TRIGGER trg_generar_codigo_cliente;
-- PENDIENTE (requiere confirmación manual en Supabase; ejecutar en el SQL Editor si se desea):
-- DROP INDEX IF EXISTS public.idx_ordenes_estado;      -- igual a idx_ordenes_compra_estado
-- DROP INDEX IF EXISTS public.idx_ordenes_fecha;       -- igual a idx_ordenes_compra_fecha_creacion
-- DROP INDEX IF EXISTS public.idx_ordenes_proveedor;   -- igual a idx_ordenes_compra_proveedor_id

-- F. erp_link_usuario seguro
CREATE OR REPLACE FUNCTION public.erp_link_usuario(p_email text, p_usuario_sistema text, p_nombres text, p_area text DEFAULT NULL::text)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
    v_auth_user_id uuid;
BEGIN
    SELECT id INTO v_auth_user_id FROM auth.users WHERE lower(email) = lower(p_email) LIMIT 1;
    IF v_auth_user_id IS NULL THEN
        RAISE EXCEPTION 'No existe usuario en Supabase Auth con email: %', p_email;
    END IF;

    -- Usuario nuevo: rol mínimo, inactivo y con una contraseña aleatoria que nadie conoce.
    -- Un administrador le asigna rol, contraseña y lo activa desde Configuración del ERP.
    INSERT INTO public.usuarios (auth_user_id, usuario, password, rol, usuario_sistema, nombres_apellidos,
                                 area, email, correo, telefono, activo, estado, created_at, updated_at, fecha_creacion)
    VALUES (v_auth_user_id, p_usuario_sistema, 'SIN-CLAVE-' || gen_random_uuid()::text, 'vendedor', p_usuario_sistema,
            p_nombres, p_area, p_email, p_email, '', FALSE, 'inactivo', NOW(), NOW(), NOW())
    ON CONFLICT (auth_user_id) DO UPDATE SET
        -- Si ya existía: solo se actualizan datos de contacto. Contraseña, rol y estado NO se tocan.
        usuario_sistema = EXCLUDED.usuario_sistema,
        nombres_apellidos = EXCLUDED.nombres_apellidos,
        area = EXCLUDED.area,
        email = EXCLUDED.email,
        correo = EXCLUDED.correo,
        updated_at = NOW();

    RETURN v_auth_user_id;
END;
$function$;
REVOKE EXECUTE ON FUNCTION public.erp_link_usuario(text, text, text, text) FROM anon, authenticated, public;

-- G. Vista que se saltaba el candado (aviso ERROR del asesor de seguridad de Supabase)
ALTER VIEW public.vista_comparativo_costos SET (security_invoker = on);

COMMIT;

-- ============================================================================
-- CÓMO DESHACER (solo si hiciera falta)
-- ============================================================================
-- ALTER TABLE public.finanzas_pagos DISABLE ROW LEVEL SECURITY;   (igual para las otras 4 tablas)
-- GRANT EXECUTE ON FUNCTION public.erp_link_usuario(text, text, text, text) TO anon, authenticated;  (igual para las otras)
-- ALTER TABLE public.clientes ENABLE TRIGGER tr_generar_codigo_cliente;
-- ALTER TABLE public.clientes ENABLE TRIGGER trg_generar_codigo_cliente;
-- (si se borraron los índices) CREATE INDEX idx_ordenes_estado ON public.ordenes_compra USING btree (estado);
--   CREATE INDEX idx_ordenes_fecha ON public.ordenes_compra USING btree (fecha_creacion);
--   CREATE INDEX idx_ordenes_proveedor ON public.ordenes_compra USING btree (proveedor_id);
-- ALTER VIEW public.vista_comparativo_costos RESET (security_invoker);
-- ALTER FUNCTION public.<función> RESET search_path;
-- DROP INDEX public.idx_oci_producto, public.idx_cot_detalle_cotizacion, public.idx_cot_detalle_producto, public.idx_comprobantes_guia;
-- erp_link_usuario: la versión anterior está en migrations/005_anterior_erp_link_usuario.sql e INFORME sección 11 (no se recomienda volver a ella).
-- Datos: todas las tablas están copiadas en el esquema respaldo_20261015.

-- ============================================================================
-- PASO 2. MIGRACIÓN 006
-- ============================================================================
-- ============================================================================
-- 006 - Stock automático: Ventas ↔ Inventario ↔ Compras ↔ Caja (ERP_KCF)
-- ============================================================================
-- ESTADO: APLICADO en Supabase el 15/10/2026 con la autorización escrita de Erika (SUPABASE.txt).
--
-- Qué hace (en simple): solo AGREGA columnas vacías. No borra ni cambia datos.
--   despachos.stock_empresa_id / stock_almacen_id : de qué empresa y sede salió la mercadería
--   despachos.stock_estado   : 'Descontado' cuando el stock salió, 'Revertido' si se anuló
--   despachos.stock_detalle  : qué movimientos del kardex y qué separaciones usó (para poder devolverlo)
--   despachos.stock_fecha    : cuándo
--   inv_movimientos.despacho_id : cada salida del kardex sabe de qué despacho es
-- La lógica está en el código (routes/stock_automatico.py). El ERP también crea estas columnas solo
-- si no existen, así que este script es el respaldo.
-- ============================================================================

ALTER TABLE public.despachos ADD COLUMN IF NOT EXISTS stock_empresa_id UUID;   -- mismo tipo que erp_empresas.id
ALTER TABLE public.despachos ADD COLUMN IF NOT EXISTS stock_almacen_id INTEGER;
ALTER TABLE public.despachos ADD COLUMN IF NOT EXISTS stock_estado VARCHAR(20);
ALTER TABLE public.despachos ADD COLUMN IF NOT EXISTS stock_detalle JSONB;
ALTER TABLE public.despachos ADD COLUMN IF NOT EXISTS stock_fecha TIMESTAMP;
ALTER TABLE public.inv_movimientos ADD COLUMN IF NOT EXISTS despacho_id INTEGER;
CREATE INDEX IF NOT EXISTS idx_inv_mov_despacho ON public.inv_movimientos (despacho_id);

-- ============================================================================
-- CÓMO DESHACER (solo si hiciera falta; antes respaldar despachos e inv_movimientos)
-- ============================================================================
-- DROP INDEX public.idx_inv_mov_despacho;
-- ALTER TABLE public.inv_movimientos DROP COLUMN despacho_id;
-- ALTER TABLE public.despachos DROP COLUMN stock_empresa_id, DROP COLUMN stock_almacen_id,
--     DROP COLUMN stock_estado, DROP COLUMN stock_detalle, DROP COLUMN stock_fecha;
-- Y volver a la versión anterior del ERP (pruebasweb_corregido_anterior_15oct.zip).

-- ============================================================================
-- ANEXO. erp_link_usuario ANTES del cambio (solo como registro; NO ejecutar)
-- ============================================================================
-- -- Versión ANTERIOR de erp_link_usuario (tal como estaba en Supabase antes del 15/10/2026).
-- -- Problema: crea usuarios ADMINISTRADORES activos con contraseña fija '123456' y, si el usuario ya existe,
-- -- le pisa la contraseña y el rol. NO se recomienda volver a ella.
-- CREATE OR REPLACE FUNCTION public.erp_link_usuario(p_email text, p_usuario_sistema text, p_nombres text, p_area text DEFAULT NULL::text)
--  RETURNS uuid
--  LANGUAGE plpgsql
--  SECURITY DEFINER
--  SET search_path TO 'public'
-- AS $function$
-- DECLARE
--     v_auth_user_id uuid;
-- BEGIN
--     SELECT id INTO v_auth_user_id FROM auth.users WHERE lower(email) = lower(p_email) LIMIT 1;
--     IF v_auth_user_id IS NULL THEN
--         RAISE EXCEPTION 'No existe usuario en Supabase Auth con email: %', p_email;
--     END IF;
--     INSERT INTO public.usuarios (auth_user_id, usuario, password, rol, usuario_sistema, nombres_apellidos,
--         area, email, correo, telefono, activo, estado, created_at, updated_at, fecha_creacion)
--     VALUES (v_auth_user_id, p_usuario_sistema, '123456', 'administrador', p_usuario_sistema, p_nombres,
--         p_area, p_email, p_email, '', TRUE, 'activo', NOW(), NOW(), NOW())
--     ON CONFLICT (auth_user_id) DO UPDATE SET
--         usuario = EXCLUDED.usuario, password = EXCLUDED.password, rol = EXCLUDED.rol,
--         usuario_sistema = EXCLUDED.usuario_sistema, nombres_apellidos = EXCLUDED.nombres_apellidos,
--         area = EXCLUDED.area, email = EXCLUDED.email, correo = EXCLUDED.correo, telefono = EXCLUDED.telefono,
--         estado = 'activo', activo = TRUE, updated_at = NOW();
--     RETURN v_auth_user_id;
-- END;
-- $function$;
