-- 043 (28/10/2026): hasta 3 cuentas bancarias por proveedor (Erika, 28/10 17:23).
-- Regla de ahorro: KCF paga a la cuenta BBVA del proveedor y AGD a la BCP (mismo banco, sin comisión);
-- si no tiene, se usa la siguiente cuenta registrada.
-- La cuenta que ya existía (banco, numero_cuenta, cci, tipo_cuenta) queda como Cuenta 1: no se mueve ni se borra nada.
-- Solo agrega columnas. Respaldo previo: respaldo_20261015.proveedores_20261028 (59 filas).
ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS moneda_cuenta VARCHAR(20);
ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS banco2 VARCHAR(80);
ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS tipo_cuenta2 VARCHAR(40);
ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS moneda_cuenta2 VARCHAR(20);
ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS numero_cuenta2 VARCHAR(40);
ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS cci2 VARCHAR(40);
ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS banco3 VARCHAR(80);
ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS tipo_cuenta3 VARCHAR(40);
ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS moneda_cuenta3 VARCHAR(20);
ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS numero_cuenta3 VARCHAR(40);
ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS cci3 VARCHAR(40);
