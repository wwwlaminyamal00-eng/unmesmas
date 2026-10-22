-- 020_intercompany.sql - Intercompany KCF ↔ AGD (pedido de Erika, 21/10/2026 23:30)
-- El módulo no crea tablas: solo lee Ventas, Compras, Finanzas, Inventario y SUNAT.
-- Este script solo agrega el permiso "Intercompany" (INTERCOMPANY) dentro de Finanzas, para que Erika
-- decida quién lo ve (Configuración ▸ Usuarios y permisos ▸ columna "Intercompany").
-- No modifica ni borra datos. Respaldo previo: respaldo_20261021.erp_submodulos_pre020.
-- APLICADO EN SUPABASE el 22/10/2026.
CREATE SCHEMA IF NOT EXISTS respaldo_20261021;
CREATE TABLE IF NOT EXISTS respaldo_20261021.erp_submodulos_pre020 AS SELECT * FROM public.erp_submodulos;
INSERT INTO erp_submodulos (modulo_id, orden, codigo, nombre, estado)
SELECT m.id, 6, 'INTERCOMPANY', 'Intercompany', 'activo' FROM erp_modulos m
WHERE m.codigo = 'FINANZAS' AND NOT EXISTS (SELECT 1 FROM erp_submodulos WHERE codigo = 'INTERCOMPANY');
