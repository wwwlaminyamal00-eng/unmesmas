-- Versión ANTERIOR de erp_link_usuario (tal como estaba en Supabase antes del 15/10/2026).
-- Problema: crea usuarios ADMINISTRADORES activos con contraseña fija '123456' y, si el usuario ya existe,
-- le pisa la contraseña y el rol. NO se recomienda volver a ella.
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
    INSERT INTO public.usuarios (auth_user_id, usuario, password, rol, usuario_sistema, nombres_apellidos,
        area, email, correo, telefono, activo, estado, created_at, updated_at, fecha_creacion)
    VALUES (v_auth_user_id, p_usuario_sistema, '123456', 'administrador', p_usuario_sistema, p_nombres,
        p_area, p_email, p_email, '', TRUE, 'activo', NOW(), NOW(), NOW())
    ON CONFLICT (auth_user_id) DO UPDATE SET
        usuario = EXCLUDED.usuario, password = EXCLUDED.password, rol = EXCLUDED.rol,
        usuario_sistema = EXCLUDED.usuario_sistema, nombres_apellidos = EXCLUDED.nombres_apellidos,
        area = EXCLUDED.area, email = EXCLUDED.email, correo = EXCLUDED.correo, telefono = EXCLUDED.telefono,
        estado = 'activo', activo = TRUE, updated_at = NOW();
    RETURN v_auth_user_id;
END;
$function$;
