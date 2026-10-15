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
