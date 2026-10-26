-- 035 (26/10/2026, Erika): Finanzas ▸ Cuentas por cobrar guarda la fecha de emisión del comprobante
-- de retención que envía el cliente (además del N° y el monto que ya existían). Solo agrega una columna.
ALTER TABLE finanzas_seguimiento_cobro ADD COLUMN IF NOT EXISTS retencion_fecha DATE;
