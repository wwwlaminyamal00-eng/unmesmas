-- 039 (27/10/2026, Erika): "Agente de retención: Sí / No" del cliente.
-- La factura lleva retención del 3% del IGV solo si el cliente es agente de retención (padrón SUNAT o marcado a mano
-- por un aprobador, con auditoría). Solo agrega columnas vacías a clientes; no cambia datos.
-- Respaldo previo: respaldo_20261015.clientes_20261027
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS agente_retencion BOOLEAN;
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS agente_retencion_fuente VARCHAR(20);
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS agente_retencion_desde VARCHAR(20);
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS agente_retencion_revisado_en TIMESTAMP;
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS agente_retencion_revisado_por VARCHAR(120);
