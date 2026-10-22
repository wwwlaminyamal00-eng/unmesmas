-- 025_diagnostico_errores.sql - Errores que ya no pasan en silencio (pedido urgente de Erika, 22/10/2026)
-- NO es obligatoria: el sistema crea la tabla solo y corrige un contador atrasado en el momento en que falla.
-- Correrla en Supabase ▸ SQL Editor deja todo listo de antemano. No borra ni cambia ningún dato de negocio.
--
-- 1. Tabla erp_log_errores: cada guardado que falla (en el servidor o en el navegador), con usuario, empresa,
--    fecha/hora, pantalla y el mensaje exacto. Se ve en Herramientas ▸ Registro de errores.
CREATE TABLE IF NOT EXISTS erp_log_errores (
    id bigserial PRIMARY KEY,
    fecha timestamptz NOT NULL DEFAULT now(),
    origen text NOT NULL DEFAULT 'servidor',
    usuario text,
    empresa text,
    metodo text,
    ruta text,
    estado integer,
    mensaje text,
    detalle text,
    navegador text
);
CREATE INDEX IF NOT EXISTS idx_erp_log_errores_fecha ON erp_log_errores (fecha DESC);
ALTER TABLE erp_log_errores ENABLE ROW LEVEL SECURITY;   -- solo la usa el servidor del ERP (dueño de la tabla)

-- 2. Contadores de id: si se cargaron filas con su número (Excel / a mano) el contador queda atrasado y el
--    siguiente "Guardar" falla con "duplicate key ... _pkey". Aquí se adelanta al id más alto existente.
--    Solo adelanta (nunca retrocede) y no toca ninguna fila.
DO $$
DECLARE
    t text;
    seq text;
    maximo bigint;
    actual bigint;
BEGIN
    FOREACH t IN ARRAY ARRAY['clientes', 'clientes_contactos', 'clientes_puntos_entrega', 'cotizaciones',
                             'cotizacion_detalle', 'proveedores', 'productos', 'ordenes_compra', 'ordenes_compra_items']
    LOOP
        IF to_regclass('public.' || t) IS NULL THEN CONTINUE; END IF;
        seq := pg_get_serial_sequence('public.' || t, 'id');
        IF seq IS NULL THEN
            SELECT substring(column_default FROM 'nextval\(''([^'']+)''') INTO seq
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = t AND column_name = 'id';
        END IF;
        IF seq IS NULL THEN CONTINUE; END IF;
        EXECUTE format('SELECT COALESCE(MAX(id), 0) FROM public.%I', t) INTO maximo;
        EXECUTE format('SELECT last_value FROM %s', seq) INTO actual;
        IF maximo > actual THEN
            PERFORM setval(seq, maximo);
            RAISE NOTICE 'Contador de % adelantado de % a %', t, actual, maximo;
        END IF;
    END LOOP;
END $$;
