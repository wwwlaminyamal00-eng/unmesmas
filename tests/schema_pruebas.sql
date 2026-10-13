-- ESQUEMA RECONSTRUIDO SOLO PARA PRUEBAS LOCALES (no ejecutar en producción).
-- Generado a partir de las consultas SQL del código; los tipos son aproximados.
CREATE TABLE IF NOT EXISTS almacenes (
  id serial primary key,
  activo boolean default true,
  codigo text,
  direccion text,
  nombre text,
  responsable text,
  telefono text,
  tipo text,
  updated_at timestamp default now(),
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS categorias (
  id serial primary key,
  activo boolean default true,
  codigo text,
  nombre text,
  tipo text,
  updated_at timestamp default now(),
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS clientes (
  id serial primary key,
  activo boolean default true,
  ambito text,
  condicion_pago text,
  created_at timestamp default now(),
  descuento numeric(14,4),
  dias_credito integer,
  direccion_fiscal text,
  email_contacto text,
  estado text,
  limite_credito numeric(14,4),
  nombre_comercial text,
  nombre_contacto text,
  numero_documento text,
  observaciones text,
  razon_social text,
  telefono_contacto text,
  tipo_documento text,
  updated_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS clientes_contactos (
  id serial primary key,
  activo boolean default true,
  cargo text,
  cliente_id integer,
  email text,
  nombre text,
  nombre_contacto text,
  principal boolean default false,
  telefono text,
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS clientes_puntos_entrega (
  id serial primary key,
  cliente_id integer,
  condicion_pago text,
  departamento text,
  direccion text,
  distrito text,
  google_maps text,
  horario text,
  instrucciones text,
  nombre_punto text,
  principal boolean default false,
  provincia text,
  responsable text,
  telefono_contacto text,
  tiempo_credito text,
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS comparativos_proveedores (
  id serial primary key,
  creado_por text,
  estado text,
  fecha timestamp default now(),
  numero_comparativo text,
  producto text,
  proveedores_json jsonb,
  updated_at timestamp default now(),
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS comprobantes (
  id serial primary key,
  cdr_response jsonb,
  cliente_direccion text,
  cliente_email text,
  cliente_nombre text,
  cliente_numero_doc text,
  cliente_telefono text,
  cliente_tipo_doc text,
  condicion_pago text,
  creado_por text,
  dias_credito integer,
  documento_asociado text,
  es_credito boolean default false,
  estado_credito text,
  estado_sunat text,
  fecha_aprobacion timestamp,
  fecha_emision timestamp,
  fecha_vencimiento timestamp,
  guia_vinculada text,
  igv numeric(14,4),
  items_json jsonb,
  moneda text,
  monto_a_pagar numeric(14,4),
  monto_retenido numeric(14,4),
  numero text,
  obs_retencion text,
  observaciones text,
  orden_compra_cliente text,
  pc_vinculado text,
  porcentaje_retencion numeric(14,4),
  serie text,
  subtotal numeric(14,4),
  sunat_response jsonb,
  tiene_retencion boolean default false,
  tipo_comprobante text,
  total numeric(14,4),
  updated_at timestamp default now(),
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS comprobantes_compra (
  id serial primary key,
  creado_por text,
  estado text,
  fecha_emision timestamp,
  igv numeric(14,4),
  items_json jsonb,
  moneda text,
  numero text,
  observaciones text,
  proveedor_direccion text,
  proveedor_email text,
  proveedor_nombre text,
  proveedor_numero_doc text,
  proveedor_telefono text,
  proveedor_tipo_doc text,
  serie text,
  subtotal numeric(14,4),
  tipo_comprobante text,
  total numeric(14,4),
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS comprobantes_proveedor (
  id serial primary key,
  creado_por text,
  estado text,
  fecha timestamp default now(),
  monto numeric(14,4),
  numero text,
  observaciones text,
  orden_compra text,
  orden_compra_id integer,
  orden_compra_numero text,
  proveedor_nombre text,
  ruc_proveedor text,
  tipo text,
  updated_at timestamp default now(),
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS costos_productos (
  id serial primary key,
  creado_por text,
  factura_referencia text,
  monto numeric(14,4),
  observaciones text,
  producto_id integer,
  proveedor_id integer,
  tipo_costo text,
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS cotizacion_detalle (
  id serial primary key,
  cantidad numeric(14,4),
  costo_unitario numeric(14,4),
  cotizacion_id integer,
  descuento_porcentaje numeric(14,4),
  descuento_total numeric(14,4),
  margen_final numeric(14,4),
  margen_porcentaje numeric(14,4),
  precio_venta_con_descuento numeric(14,4),
  precio_venta_unitario numeric(14,4),
  producto_id integer,
  subtotal_costo numeric(14,4),
  subtotal_venta numeric(14,4),
  subtotal_venta_con_descuento numeric(14,4),
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS cotizaciones (
  id serial primary key,
  almacen text,
  cliente_id integer,
  codigo_cotizacion text,
  condicion_pago text,
  contacto_cliente text,
  correlativo integer,
  descuento_monto numeric(14,4),
  descuento_porcentaje numeric(14,4),
  descuento_tipo text,
  direccion_entrega text,
  email_cliente text,
  estado text,
  fecha_aceptacion timestamp,
  fecha_creacion timestamp default now(),
  fecha_rechazo timestamp,
  forma_pago text,
  igv numeric(14,4),
  motivo text,
  motivo_rechazo text,
  nota_cotizacion text,
  nota_interna text,
  notas text,
  numero_cotizacion text,
  parihuela text,
  requerimiento text,
  seguimiento text,
  subtotal numeric(14,4),
  telefono_cliente text,
  tiempo_entrega text,
  total numeric(14,4),
  transporte text,
  updated_at timestamp default now(),
  usuario_aceptacion_id integer,
  usuario_id integer,
  usuario_rechazo_id integer,
  usuario_validacion_id integer,
  validado_por_nombre text,
  validez_oferta text,
  vendedor text,
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS despachos (
  id serial primary key,
  cliente text,
  comprobante text,
  cotizacion_id integer,
  cotizacion_numero text,
  creado_por text,
  destino text,
  estado text,
  fecha timestamp default now(),
  fecha_despacho timestamp,
  guia text,
  items_json jsonb,
  numero text,
  observaciones text,
  origen text,
  pc_id integer,
  pc_numero text,
  responsable text,
  ruc text,
  transportista text,
  updated_at timestamp default now(),
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS devoluciones (
  id serial primary key,
  cliente text,
  comprobante_id integer,
  comprobante_numero text,
  creado_por text,
  estado text,
  fecha timestamp default now(),
  guia text,
  monto numeric(14,4),
  motivo text,
  numero text,
  observaciones text,
  ruc text,
  updated_at timestamp default now(),
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS erp_auditoria (
  id serial primary key,
  accion text,
  auth_user_id text,
  data_anterior jsonb,
  data_nueva jsonb,
  empresa_id integer,
  registro_id integer,
  tabla text,
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS erp_correlativos (
  id serial primary key,
  anio integer,
  codigo_documento text,
  documento text,
  empresa_id integer,
  estado text,
  prefijo text,
  ultimo_numero integer,
  updated_at timestamp default now(),
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS erp_empresa_cuentas_bancarias (
  id serial primary key,
  banco text,
  cci text,
  empresa_id integer,
  es_principal boolean default false,
  estado text,
  moneda text,
  numero_cuenta text,
  tipo_cuenta text,
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS erp_empresas (
  id serial primary key,
  codigo text,
  color_pastel text,
  color_primario text,
  color_secundario text,
  correo_documentos text,
  direccion_fiscal text,
  estado text,
  logo_url text,
  nombre_comercial text,
  nombre_corto text,
  razon_social text,
  ruc text,
  telefono text,
  updated_at timestamp default now(),
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS erp_parametros (
  id serial primary key,
  codigo text,
  empresa_id integer,
  es_critico boolean default false,
  estado text,
  grupo text,
  nombre text,
  regla text,
  updated_at timestamp default now(),
  valor_bool boolean default false,
  valor_num numeric(14,4),
  valor_text text,
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS erp_usuario_empresas (
  id serial primary key,
  auth_user_id text,
  empresa_id integer,
  es_empresa_principal boolean default false,
  estado text,
  rol_id integer,
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS erp_usuario_permisos (
  id serial primary key,
  auth_user_id text,
  empresa_id integer,
  observacion text,
  puede_anular boolean default false,
  puede_aprobar boolean default false,
  puede_crear boolean default false,
  puede_editar boolean default false,
  puede_eliminar boolean default false,
  puede_exportar boolean default false,
  puede_subir_evidencia boolean default false,
  puede_ver boolean default false,
  submodulo_id integer,
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS guias_remision (
  id serial primary key,
  conductor_dni text,
  conductor_nombre text,
  creado_por text,
  created_at timestamp default now(),
  destinatario_direccion text,
  destinatario_nombre text,
  destinatario_ubigeo text,
  documento_asociado text,
  estado_sunat text,
  factura text,
  fecha_emision timestamp,
  fecha_traslado timestamp,
  items_json jsonb,
  licencia_conductor text,
  modalidad_transporte text,
  motivo_traslado text,
  numero text,
  observaciones text,
  orden_compra_cliente text,
  peso_total numeric(14,4),
  placa_vehiculo text,
  remitente_direccion text,
  remitente_nombre text,
  remitente_ubigeo text,
  ruc_destinatario text,
  ruc_remitente text,
  serie text,
  transportista_nombre text,
  transportista_ruc text,
  updated_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS marcas (
  id serial primary key,
  activo boolean default true,
  codigo text,
  nombre text,
  tipo text,
  updated_at timestamp default now(),
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS notas_credito (
  id serial primary key,
  cliente_direccion text,
  cliente_email text,
  cliente_nombre text,
  cliente_numero_doc text,
  cliente_telefono text,
  cliente_tipo_doc text,
  comprobante_asociado text,
  creado_por text,
  estado text,
  fecha_emision timestamp,
  fecha_vencimiento timestamp,
  monto numeric(14,4),
  motivo text,
  numero text,
  observaciones text,
  serie text,
  updated_at timestamp default now(),
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS orden_compra_detalle (
  id serial primary key,
  cantidad numeric(14,4),
  costo_unitario numeric(14,4),
  descuento_porcentaje numeric(14,4),
  descuento_total numeric(14,4),
  margen_final numeric(14,4),
  margen_porcentaje numeric(14,4),
  orden_id integer,
  precio_venta_con_descuento numeric(14,4),
  precio_venta_unitario numeric(14,4),
  producto_id integer,
  subtotal_costo numeric(14,4),
  subtotal_venta numeric(14,4),
  subtotal_venta_con_descuento numeric(14,4),
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS ordenes_compra (
  id serial primary key,
  codigo_orden text,
  condicion_pago text,
  contacto_proveedor text,
  correlativo integer,
  descuento_monto numeric(14,4),
  descuento_porcentaje numeric(14,4),
  descuento_tipo text,
  email_proveedor text,
  estado text,
  fecha_creacion timestamp default now(),
  fecha_requerida timestamp,
  igv numeric(14,4),
  lugar_entrega text,
  nota_compra text,
  notas text,
  num_cotizacion text,
  numero_orden text,
  proveedor_id integer,
  subtotal numeric(14,4),
  telefono_proveedor text,
  tiempo_entrega text,
  total numeric(14,4),
  updated_at timestamp default now(),
  usuario_id integer,
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS ordenes_compra_items (
  id serial primary key,
  cantidad numeric(14,4),
  orden_compra_id integer,
  precio_unitario numeric(14,4),
  producto text,
  total numeric(14,4),
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS pedido_compra_pc (
  id serial primary key,
  archivo_oc text,
  cliente text,
  condicion_atencion text,
  condicion_pago text,
  correo_origen text,
  cotizacion_id integer,
  cotizacion_numero text,
  creado_por text,
  entrega text,
  estado text,
  fecha timestamp default now(),
  fecha_despacho timestamp,
  fecha_recepcion timestamp,
  items_json jsonb,
  lugar_entrega text,
  medio text,
  monto numeric(14,4),
  numero text,
  observaciones text,
  req_compra text,
  responsable text,
  ruc text,
  updated_at timestamp default now(),
  valida_cantidades boolean default false,
  valida_entrega boolean default false,
  valida_margen boolean default false,
  valida_montos boolean default false,
  valida_precios boolean default false,
  valida_stock boolean default false,
  valida_transporte boolean default false,
  valida_vigencia boolean default false,
  vendedor text,
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS precios_productos (
  id serial primary key,
  actualizado_en timestamp,
  margen_preferido numeric(14,4),
  precio_lista numeric(14,4),
  precio_venta numeric(14,4),
  producto_id integer,
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS productos (
  id serial primary key,
  abastecimiento text,
  activo boolean default true,
  categoria_derivada text,
  codigo text,
  codigo_barras text,
  costo_unitario numeric(14,4),
  descripcion text,
  descripcion_larga text,
  estado text,
  familia text,
  marca text,
  modelo text,
  observaciones text,
  origen text,
  peso numeric(14,4),
  precio_unitario numeric(14,4),
  presentacion_proveedor text,
  presentacion_venta text,
  proveedor_id integer,
  stock numeric(14,4),
  stock_minimo numeric(14,4),
  tiempo_entrega text,
  transporte text,
  unidad text,
  updated_at timestamp default now(),
  venta_minima numeric(14,4),
  volumen numeric(14,4),
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS proveedores (
  id serial primary key,
  activo boolean default true,
  ambito text,
  banco text,
  cci text,
  codigo_proveedor text,
  condicion_pago text,
  contacto text,
  descuento numeric(14,4),
  direccion text,
  email text,
  estado text,
  fecha_creacion timestamp default now(),
  lugar_recojo text,
  moneda text,
  numero_cuenta text,
  observaciones text,
  razon_comercial text,
  razon_social text,
  ruc text,
  telefono text,
  tiempo_credito text,
  tipo text,
  tipo_cuenta text,
  tipo_doc text,
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS proveedores_contactos (
  id serial primary key,
  activo boolean default true,
  cargo text,
  created_at timestamp default now(),
  email text,
  nombre_contacto text,
  principal boolean default false,
  proveedor_id integer,
  telefono text,
  updated_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS proveedores_puntos_entrega (
  id serial primary key,
  activo boolean default true,
  created_at timestamp default now(),
  direccion text,
  horario_atencion text,
  instrucciones text,
  nombre_punto text,
  principal boolean default false,
  proveedor_id integer,
  responsable text,
  telefono_contacto text,
  updated_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS recepciones_mercaderia (
  id serial primary key,
  cantidad numeric(14,4),
  creado_por text,
  estado text,
  estado_mercaderia text,
  fecha timestamp default now(),
  numero_recepcion text,
  observaciones text,
  orden_compra text,
  orden_compra_id integer,
  orden_compra_numero text,
  producto text,
  proveedor_nombre text,
  unidad text,
  updated_at timestamp default now(),
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS solicitudes_compra (
  id serial primary key,
  area text,
  cantidad numeric(14,4),
  creado_por text,
  estado text,
  fecha timestamp default now(),
  justificacion text,
  numero_solicitud text,
  producto text,
  solicitante text,
  unidad text,
  updated_at timestamp default now(),
  urgencia text,
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS transportistas (
  id serial primary key,
  activo boolean default true,
  creado_por text,
  dni text,
  licencia text,
  medidas text,
  nombre_completo text,
  peso_carga numeric(14,4),
  placa text,
  telefono text,
  tipo text,
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS um (
  id serial primary key,
  abreviatura text,
  activo boolean default true,
  ambito text,
  codigo text,
  decimales integer,
  nombre text,
  tipo text,
  updated_at timestamp default now(),
  created_at timestamp default now()
);

CREATE TABLE IF NOT EXISTS usuarios (
  id serial primary key,
  activo boolean default true,
  area text,
  auth_user_id text,
  celular text,
  correo text,
  email text,
  estado text,
  nombre_completo text,
  nombres_apellidos text,
  password text,
  rol text,
  telefono text,
  updated_at timestamp default now(),
  usuario text,
  usuario_sistema text,
  created_at timestamp default now()
);
CREATE TABLE IF NOT EXISTS erp_roles (id serial primary key, codigo text, nombre text, descripcion text, es_admin boolean default false, estado text default 'activo', created_at timestamp default now(), updated_at timestamp default now());
CREATE TABLE IF NOT EXISTS erp_modulos (id serial primary key, orden int default 0, codigo text, nombre text, descripcion text, icono text, ruta text, estado text default 'activo', created_at timestamp default now(), updated_at timestamp default now());
CREATE TABLE IF NOT EXISTS erp_submodulos (id serial primary key, modulo_id int, orden int default 0, codigo text, nombre text, descripcion text, ruta text, estado text default 'activo', created_at timestamp default now(), updated_at timestamp default now());
CREATE TABLE IF NOT EXISTS guias_remision_compra (id serial primary key, serie text, numero text, proveedor_nombre text, proveedor_ruc text, fecha_emision timestamp, fecha_traslado timestamp, placa_vehiculo text, peso_total numeric(14,4), estado text, items_json jsonb, created_at timestamp default now());
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS codigo_cliente text;
ALTER TABLE productos ADD COLUMN IF NOT EXISTS fecha_creacion timestamp default now();
ALTER TABLE transportistas ADD COLUMN IF NOT EXISTS updated_at timestamp default now();
ALTER TABLE guias_remision ADD COLUMN IF NOT EXISTS cdr_response jsonb;
ALTER TABLE guias_remision ADD COLUMN IF NOT EXISTS sunat_response jsonb;
ALTER TABLE guias_remision ADD COLUMN IF NOT EXISTS estado text default 'Emitida';
ALTER TABLE pedido_compra_pc ADD COLUMN IF NOT EXISTS guia text;
ALTER TABLE pedido_compra_pc ADD COLUMN IF NOT EXISTS factura text;
ALTER TABLE comprobantes ADD COLUMN IF NOT EXISTS estado text default 'Emitido';
ALTER TABLE cotizaciones ADD COLUMN IF NOT EXISTS created_at timestamp default now();
ALTER TABLE clientes_puntos_entrega ADD COLUMN IF NOT EXISTS activo boolean default true;
ALTER TABLE costos_productos ADD COLUMN IF NOT EXISTS fecha_registro timestamp default now();
ALTER TABLE productos ADD COLUMN IF NOT EXISTS categoria text;
ALTER TABLE productos ADD COLUMN IF NOT EXISTS subcategoria text;
CREATE OR REPLACE VIEW vista_comparativo_costos AS
SELECT p.id AS producto_id, p.codigo, p.descripcion AS nombre_producto, p.modelo, p.marca,
       p.categoria, p.subcategoria, p.costo_unitario AS costo_actual, p.precio_unitario AS precio_actual,
       p.stock, p.stock_minimo, p.estado, p.activo,
       pp.precio_venta, pp.precio_lista, pp.margen_preferido,
       COUNT(cp.id) AS total_registros_costos,
       AVG(cp.monto) AS costo_promedio_historico, MIN(cp.monto) AS costo_minimo_historico, MAX(cp.monto) AS costo_maximo_historico,
       AVG(cp.monto) FILTER (WHERE cp.tipo_costo='compra') AS costo_compra_promedio,
       AVG(cp.monto) FILTER (WHERE cp.tipo_costo='transporte') AS costo_transporte_promedio,
       AVG(cp.monto) FILTER (WHERE cp.tipo_costo='almacenaje') AS costo_almacenaje_promedio,
       AVG(cp.monto) FILTER (WHERE cp.tipo_costo='manufactura') AS costo_manufactura_promedio,
       (ARRAY_AGG(cp.monto ORDER BY cp.fecha_registro DESC))[1] AS ultimo_costo_registrado,
       MAX(cp.fecha_registro) AS fecha_ultimo_costo,
       CASE WHEN p.costo_unitario > 0 THEN (p.precio_unitario - p.costo_unitario)/p.costo_unitario*100 END AS margen_actual_porcentaje,
       NULL::numeric AS margen_historico_porcentaje, NULL::numeric AS diferencia_margen_preferido
FROM productos p
LEFT JOIN precios_productos pp ON pp.producto_id = p.id
LEFT JOIN costos_productos cp ON cp.producto_id = p.id
GROUP BY p.id, pp.precio_venta, pp.precio_lista, pp.margen_preferido;
CREATE OR REPLACE VIEW vista_resumen_costos AS
SELECT COUNT(DISTINCT producto_id) AS total_productos_con_costos, AVG(monto) AS promedio_general_costos,
       AVG(monto) FILTER (WHERE tipo_costo='compra') AS promedio_costo_compra,
       MIN(monto) AS costo_minimo_registrado, MAX(monto) AS costo_maximo_registrado,
       COUNT(DISTINCT tipo_costo) AS tipos_costo_utilizados
FROM costos_productos;
