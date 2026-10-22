-- =====================================================================================
-- SUPABASE 018 · Comentario de Finanzas por factura (21/10/2026, pedido de Erika 18:38)
-- Cuentas por cobrar / por pagar: cada factura puede llevar un comentario de Finanzas
-- (no cambia la factura ni lo que se imprime). La app también crea la tabla sola si falta.
-- Solo AGREGA una tabla nueva: no modifica ni borra datos. (La 017 es del módulo SUNAT.)
-- APLICADO EN SUPABASE el 21/10/2026.
-- =====================================================================================
CREATE TABLE IF NOT EXISTS public.finanzas_comentarios (
    documento_tabla VARCHAR(40) NOT NULL,      -- 'comprobantes' (venta) o 'comprobantes_proveedor' (compra)
    documento_id INTEGER NOT NULL,
    comentario TEXT,
    usuario_nombre VARCHAR(150),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (documento_tabla, documento_id)
);
ALTER TABLE public.finanzas_comentarios ENABLE ROW LEVEL SECURITY;
