-- 040 (27/10/2026, Erika): cerrar las sesiones abiertas al cambiar contraseñas.
-- Toda sesión iniciada antes de usuarios.sesion_valida_desde se cierra en el siguiente clic (routes/sesiones.py).
-- Solo agrega una columna vacía. Ya aplicada en Supabase el 27/10/2026 19:05; respaldo previo:
-- respaldo_20261027.usuarios_pre_cambio_claves
ALTER TABLE public.usuarios ADD COLUMN IF NOT EXISTS sesion_valida_desde timestamptz;
