-- 024_matriz_permisos.sql - Matriz de permisos (pedido de Erika, 22/10/2026 10:26)
-- Configuración ▸ Usuarios y permisos ahora asigna por módulo: Sin acceso / Solo lectura / Acceso total.
-- "Solo lectura" (solo Ver) ahora SÍ lo respeta el servidor: no deja grabar en ese módulo.
-- Esta migración:
--   1) Respalda las 3 tablas de permisos en respaldo_20261022.
--   2) Pone nombres claros a cada función (antes varias se llamaban igual: "Configuración", "Compras", "Reportes").
--   3) Para que nadie se quede bloqueado de un día para otro: los permisos que tenían solo "Ver" fuera de
--      Configuración (antes igual dejaban grabar) pasan a "Acceso total". Desde hoy, "Solo lectura" se marca
--      a propósito en la matriz. (Afecta: hel02kcf y est01kcf en AGD ▸ Finanzas; rol OPERATIVO ▸ Inventario y Productos.)
-- Resultado al aplicarlo: 37 nombres corregidos; 193 filas de permisos de usuario y 6 del rol OPERATIVO pasaron de
-- solo Ver a Ver + Crear + Editar. De esas, las que importan son hel02kcf y est01kcf en AGD; el resto son del
-- usuario admin (Gerencia total: ya veía todo) y de 2 cuentas de acceso sin usuario del ERP (no pueden entrar).
-- No toca datos de negocio (ventas, compras, stock, clientes...). APLICADO EN SUPABASE el 22/10/2026.
CREATE SCHEMA IF NOT EXISTS respaldo_20261022;
CREATE TABLE IF NOT EXISTS respaldo_20261022.erp_submodulos_pre024 AS SELECT * FROM public.erp_submodulos;
CREATE TABLE IF NOT EXISTS respaldo_20261022.erp_usuario_permisos_pre024 AS SELECT * FROM public.erp_usuario_permisos;
CREATE TABLE IF NOT EXISTS respaldo_20261022.erp_rol_permisos_pre024 AS SELECT * FROM public.erp_rol_permisos;
ALTER TABLE respaldo_20261022.erp_submodulos_pre024 ENABLE ROW LEVEL SECURITY;
ALTER TABLE respaldo_20261022.erp_usuario_permisos_pre024 ENABLE ROW LEVEL SECURITY;
ALTER TABLE respaldo_20261022.erp_rol_permisos_pre024 ENABLE ROW LEVEL SECURITY;

UPDATE erp_submodulos s SET nombre = v.nombre
FROM (VALUES
    ('EMPRESAS', 'Empresas'),
    ('USUARIOS_PERMISOS', 'Usuarios y permisos'),
    ('CORRELATIVOS', 'Correlativos'),
    ('PARAMETROS', 'Parámetros'),
    ('INTEGRACION', 'Integración ERP'),
    ('CLIENTES', 'Clientes'),
    ('PROVEEDORES', 'Proveedores'),
    ('ALMACENES', 'Almacenes / sedes'),
    ('CATEGORIAS', 'Categorías'),
    ('MARCAS', 'Marcas'),
    ('UNIDADES_MEDIDA', 'Unidades de medida'),
    ('PRODUCTOS_LISTADO', 'Lista de productos'),
    ('PRODUCTOS_FICHA', 'Ficha de producto'),
    ('COTIZACIONES', 'Cotizaciones'),
    ('COMPROBANTES_CLIENTE', 'Pedidos (PC), despachos y facturas'),
    ('GUIAS_CLIENTE', 'Guías de remisión'),
    ('NOTAS_CREDITO', 'Notas de crédito'),
    ('SEGUIMIENTO_COMERCIAL', 'Seguimiento comercial'),
    ('SOLICITUD_COMPRA', 'Pedidos por comprar'),
    ('COMPARATIVO_PROVEEDORES', 'Comparativo y precios de proveedores'),
    ('ORDEN_COMPRA', 'Órdenes de compra'),
    ('COMPROBANTES_PROVEEDOR', 'Facturas de proveedores'),
    ('RECEPCION_MERCADERIA', 'Recibir mercadería (logística)'),
    ('ESTADO_STOCK', 'Stock'),
    ('KARDEX', 'Kardex'),
    ('ENTRADAS_SALIDAS', 'Entradas y salidas'),
    ('TRANSFERENCIAS', 'Traslados entre sedes'),
    ('CUENTAS_COBRAR', 'Cuentas por cobrar'),
    ('CUENTAS_PAGAR', 'Cuentas por pagar'),
    ('CAJA_BANCOS', 'Cobros y pagos'),
    ('FLUJO_CAJA', 'Flujo de caja'),
    ('CONCILIACION_BANCARIA', 'Conciliación bancaria'),
    ('INTERCOMPANY', 'Intercompany KCF ↔ AGD'),
    ('PLANILLA', 'Planilla y RRHH (sueldos)'),
    ('REPORTE_VENTAS', 'Reporte de ventas'),
    ('REPORTE_COMPRAS', 'Reporte de compras'),
    ('REPORTE_INVENTARIO', 'Reporte de inventario'),
    ('REPORTE_FINANZAS', 'Reporte de finanzas'),
    ('SUNAT', 'SUNAT e impuestos')
) AS v(codigo, nombre)
WHERE s.codigo = v.codigo AND s.nombre IS DISTINCT FROM v.nombre;

UPDATE erp_usuario_permisos up SET puede_crear = true, puede_editar = true, puede_exportar = true, updated_at = NOW()
WHERE up.puede_ver AND NOT COALESCE(up.puede_crear, false) AND NOT COALESCE(up.puede_editar, false)
  AND up.submodulo_id IN (SELECT s.id FROM erp_submodulos s JOIN erp_modulos m ON m.id = s.modulo_id WHERE m.codigo <> 'CONFIG_SEGURIDAD');

UPDATE erp_rol_permisos rp SET puede_crear = true, puede_editar = true, puede_exportar = true
WHERE rp.puede_ver AND NOT COALESCE(rp.puede_crear, false) AND NOT COALESCE(rp.puede_editar, false)
  AND rp.submodulo_id IN (SELECT s.id FROM erp_submodulos s JOIN erp_modulos m ON m.id = s.modulo_id WHERE m.codigo <> 'CONFIG_SEGURIDAD');
