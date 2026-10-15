CREATE SCHEMA IF NOT EXISTS auth; CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql AS 'select null::uuid'; CREATE TABLE IF NOT EXISTS auth.users(id uuid primary key, email text);
CREATE SEQUENCE IF NOT EXISTS public."proveedores_contactos_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."proveedores_puntos_entrega_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."inv_separaciones_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."clientes_contactos_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."clientes_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."clientes_puntos_entrega_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."cotizacion_detalle_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."cotizaciones_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."listas_precios_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."productos_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."proveedores_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."usuarios_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."movimientos_stock_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."ordenes_compra_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."orden_compra_detalle_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."guias_remision_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."comprobantes_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."comprobantes_compra_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."guias_remision_compra_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."transportistas_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."inventario_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."movimientos_inventario_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."recuentos_inventario_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."revalorizaciones_inventario_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."costos_productos_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."almacenes_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."categorias_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."um_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."seq_codigo_cliente";
CREATE SEQUENCE IF NOT EXISTS public."notas_credito_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."devoluciones_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."pedido_compra_pc_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."despachos_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."despacho_productos_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."marcas_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."inv_conteos_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."solicitudes_compra_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."comparativos_proveedores_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."comprobantes_proveedor_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."recepciones_mercaderia_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."cotizaciones_eliminadas_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."logs_auditoria_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."inv_conteo_items_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."ordenes_compra_items_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."finanzas_pagos_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."com_recepciones_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."com_recepcion_items_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."com_incidencias_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."inv_sede_empresa_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."inv_movimientos_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."inv_traslados_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."inv_traslado_items_id_seq";
CREATE SEQUENCE IF NOT EXISTS public."com_historial_id_seq";
CREATE TABLE public."clientes" (
  "id" integer DEFAULT nextval('clientes_id_seq'::regclass) NOT NULL,
  "tipo_documento" text NOT NULL,
  "numero_documento" text NOT NULL,
  "razon_social" text NOT NULL,
  "direccion_fiscal" text NOT NULL,
  "activo" boolean DEFAULT true,
  "fecha_creacion" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  "codigo_cliente" character varying,
  "nombre_comercial" text,
  "telefono_contacto" character varying,
  "nombre_contacto" character varying,
  "email_contacto" character varying,
  "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  "updated_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  "condicion_pago" character varying DEFAULT 'Contado'::character varying,
  "dias_credito" integer DEFAULT 0,
  "limite_credito" character varying DEFAULT ''::character varying,
  "descuento" character varying DEFAULT ''::character varying,
  "estado" character varying DEFAULT 'Activo'::character varying,
  "ambito" character varying DEFAULT 'COMPARTIDO'::character varying,
  "observaciones" text DEFAULT ''::text
);
CREATE TABLE public."clientes_contactos" (
  "id" integer DEFAULT nextval('clientes_contactos_id_seq'::regclass) NOT NULL,
  "cliente_id" integer NOT NULL,
  "nombre_contacto" text NOT NULL,
  "email" text,
  "telefono" text,
  "cargo" text,
  "principal" boolean DEFAULT false,
  "activo" boolean DEFAULT true,
  "fecha_creacion" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE public."clientes_puntos_entrega" (
  "id" integer DEFAULT nextval('clientes_puntos_entrega_id_seq'::regclass) NOT NULL,
  "cliente_id" integer NOT NULL,
  "nombre_punto" text NOT NULL,
  "direccion" text NOT NULL,
  "telefono_contacto" text,
  "responsable" text,
  "principal" boolean DEFAULT false,
  "activo" boolean DEFAULT true,
  "fecha_creacion" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  "condicion_pago" character varying,
  "tiempo_credito" character varying,
  "instrucciones" text,
  "google_maps" text,
  "horario" text
);
CREATE TABLE public."cotizacion_detalle" (
  "id" integer DEFAULT nextval('cotizacion_detalle_id_seq'::regclass) NOT NULL,
  "cotizacion_id" integer NOT NULL,
  "producto_id" integer NOT NULL,
  "cantidad" numeric NOT NULL,
  "costo_unitario" numeric DEFAULT 0,
  "subtotal_costo" numeric DEFAULT 0,
  "margen_porcentaje" numeric DEFAULT 0,
  "precio_venta_unitario" numeric DEFAULT 0,
  "subtotal_venta" numeric DEFAULT 0,
  "descuento_porcentaje" numeric DEFAULT 0,
  "precio_venta_con_descuento" numeric DEFAULT 0,
  "subtotal_venta_con_descuento" numeric DEFAULT 0,
  "descuento_total" numeric DEFAULT 0,
  "margen_final" numeric DEFAULT 0
);
CREATE TABLE public."cotizaciones" (
  "id" integer DEFAULT nextval('cotizaciones_id_seq'::regclass) NOT NULL,
  "numero_cotizacion" text NOT NULL,
  "cliente_id" integer NOT NULL,
  "fecha_creacion" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  "estado" text NOT NULL,
  "subtotal" numeric DEFAULT 0,
  "igv" numeric DEFAULT 0,
  "total" numeric DEFAULT 0,
  "usuario_id" integer NOT NULL,
  "notas" text,
  "forma_pago" text,
  "tiempo_entrega" text,
  "almacen" text,
  "validez_oferta" text,
  "codigo_cotizacion" character varying,
  "correlativo" integer DEFAULT 0,
  "condicion_pago" character varying DEFAULT 'Contado'::character varying,
  "direccion_entrega" text,
  "requerimiento" character varying,
  "nota_cotizacion" text,
  "descuento_porcentaje" numeric DEFAULT 0,
  "descuento_monto" numeric DEFAULT 0,
  "descuento_tipo" character varying DEFAULT 'porcentaje'::character varying,
  "contacto_cliente" text,
  "telefono_cliente" text,
  "email_cliente" text,
  "seguimiento" character varying DEFAULT 'Asesor'::character varying,
  "motivo" character varying DEFAULT 'Proyecto nuevo'::character varying,
  "transporte" character varying DEFAULT 'Seleccione'::character varying,
  "parihuela" character varying DEFAULT 'Seleccione'::character varying,
  "nota_interna" text DEFAULT ''::text,
  "vendedor" character varying DEFAULT 'Helen Blas Príncipe'::character varying,
  "motivo_eliminacion" text,
  "fecha_eliminacion" timestamp without time zone,
  "eliminado_por" integer,
  "usuario_validacion_id" integer,
  "validado_por_nombre" character varying,
  "fecha_aceptacion" timestamp without time zone,
  "usuario_aceptacion_id" integer,
  "fecha_rechazo" timestamp without time zone,
  "usuario_rechazo_id" integer,
  "motivo_rechazo" text,
  "updated_at" timestamp without time zone DEFAULT now()
);
CREATE TABLE public."listas_precios" (
  "id" integer DEFAULT nextval('listas_precios_id_seq'::regclass) NOT NULL,
  "producto_id" integer NOT NULL,
  "precio_venta" numeric NOT NULL,
  "margen" numeric NOT NULL,
  "vigente_desde" date NOT NULL,
  "vigente_hasta" date,
  "activo" boolean DEFAULT true,
  "fecha_creacion" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE public."productos" (
  "id" integer DEFAULT nextval('productos_id_seq'::regclass) NOT NULL,
  "familia" text NOT NULL,
  "codigo" text NOT NULL,
  "descripcion" text NOT NULL,
  "descripcion_larga" text,
  "marca" text,
  "modelo" text,
  "unidad" text NOT NULL,
  "activo" boolean DEFAULT true,
  "fecha_creacion" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  "peso" text,
  "observaciones" text,
  "transporte" text,
  "costo_unitario" numeric DEFAULT 0.00 NOT NULL,
  "precio_unitario" numeric DEFAULT 0.00 NOT NULL,
  "stock" integer DEFAULT 0 NOT NULL,
  "updated_at" timestamp with time zone DEFAULT now(),
  "volumen" character varying DEFAULT ''::character varying,
  "presentacion_proveedor" character varying,
  "presentacion_venta" character varying,
  "venta_minima" integer DEFAULT 1,
  "codigo_barras" character varying,
  "stock_minimo" integer DEFAULT 0,
  "estado" character varying DEFAULT 'activo'::character varying,
  "categoria_derivada" character varying,
  "origen" character varying,
  "tiempo_entrega" character varying,
  "abastecimiento" character varying,
  "proveedor_id" integer
);
CREATE TABLE public."proveedores" (
  "id" integer DEFAULT nextval('proveedores_id_seq'::regclass) NOT NULL,
  "razon_social" text NOT NULL,
  "ruc" text NOT NULL,
  "direccion" text NOT NULL,
  "telefono" text,
  "contacto" text,
  "email" text,
  "activo" boolean DEFAULT true,
  "fecha_creacion" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  "razon_comercial" character varying,
  "codigo_proveedor" character varying,
  "lugar_recojo" character varying,
  "condicion_pago" character varying,
  "tiempo_credito" character varying,
  "banco" character varying,
  "numero_cuenta" character varying,
  "cci" character varying,
  "estado" character varying DEFAULT 'Activo'::character varying,
  "ambito" character varying DEFAULT 'COMPARTIDO'::character varying,
  "observaciones" text DEFAULT ''::text,
  "tipo" character varying DEFAULT 'Recurrente'::character varying,
  "tipo_doc" character varying DEFAULT 'RUC'::character varying,
  "tipo_cuenta" character varying DEFAULT 'Cuenta corriente'::character varying,
  "moneda" character varying DEFAULT 'Soles'::character varying,
  "descuento" character varying
);
CREATE TABLE public."usuarios" (
  "id" integer DEFAULT nextval('usuarios_id_seq'::regclass) NOT NULL,
  "usuario" text NOT NULL,
  "password" text NOT NULL,
  "rol" text NOT NULL,
  "nombre_completo" text NOT NULL,
  "email" text,
  "activo" boolean DEFAULT true,
  "fecha_creacion" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  "telefono" character varying,
  "codigo_vendedor" character varying,
  "estado" character varying DEFAULT 'activo'::character varying,
  "auth_user_id" uuid,
  "usuario_sistema" text,
  "nombres_apellidos" text,
  "area" text,
  "correo" text,
  "celular" text,
  "created_at" timestamp with time zone DEFAULT now(),
  "updated_at" timestamp with time zone DEFAULT now()
);
CREATE TABLE public."movimientos_stock" (
  "id" bigint DEFAULT nextval('movimientos_stock_id_seq'::regclass) NOT NULL,
  "producto_id" integer,
  "tipo" character varying NOT NULL,
  "cantidad" integer NOT NULL,
  "motivo" character varying,
  "referencia" character varying,
  "usuario_id" integer,
  "created_at" timestamp with time zone DEFAULT now(),
  "costo_unitario" numeric
);
CREATE TABLE public."ordenes_compra" (
  "id" integer DEFAULT nextval('ordenes_compra_id_seq'::regclass) NOT NULL,
  "numero_orden" character varying,
  "codigo_orden" character varying,
  "correlativo" integer DEFAULT 0,
  "proveedor_id" integer,
  "usuario_id" integer,
  "fecha_creacion" timestamp without time zone DEFAULT now(),
  "estado" character varying DEFAULT 'pendiente'::character varying,
  "subtotal" numeric DEFAULT 0,
  "igv" numeric DEFAULT 0,
  "total" numeric DEFAULT 0,
  "condicion_pago" character varying,
  "tiempo_entrega" character varying,
  "fecha_requerida" character varying,
  "lugar_entrega" text,
  "num_cotizacion" character varying,
  "nota_compra" text,
  "notas" text,
  "descuento_porcentaje" numeric DEFAULT 0,
  "descuento_monto" numeric DEFAULT 0,
  "descuento_tipo" character varying DEFAULT 'porcentaje'::character varying,
  "contacto_proveedor" character varying,
  "telefono_proveedor" character varying,
  "email_proveedor" character varying,
  "created_at" timestamp without time zone DEFAULT now(),
  "updated_at" timestamp without time zone DEFAULT now(),
  "flujo" character varying,
  "almacen_entrega_id" integer,
  "modalidad_entrega" character varying,
  "direccion_recojo" text,
  "tipo_compra" character varying,
  "motivo_stock" text,
  "fecha_compromiso" date,
  "dias_credito" integer,
  "creado_por_nombre" character varying,
  "aprobado_por_id" integer,
  "aprobado_por" character varying,
  "aprobado_en" timestamp without time zone,
  "anulado_por" character varying,
  "anulado_en" timestamp without time zone,
  "motivo_anulacion" text,
  "empresa_id" uuid
);
CREATE TABLE public."orden_compra_detalle" (
  "id" integer DEFAULT nextval('orden_compra_detalle_id_seq'::regclass) NOT NULL,
  "orden_id" integer NOT NULL,
  "producto_id" integer,
  "cantidad" numeric DEFAULT 0,
  "costo_unitario" numeric DEFAULT 0,
  "subtotal_costo" numeric DEFAULT 0,
  "margen_porcentaje" numeric DEFAULT 0,
  "precio_venta_unitario" numeric DEFAULT 0,
  "subtotal_venta" numeric DEFAULT 0,
  "descuento_porcentaje" numeric DEFAULT 0,
  "precio_venta_con_descuento" numeric DEFAULT 0,
  "subtotal_venta_con_descuento" numeric DEFAULT 0,
  "descuento_total" numeric DEFAULT 0,
  "margen_final" numeric DEFAULT 0,
  "created_at" timestamp without time zone DEFAULT now()
);
CREATE TABLE public."guias_remision" (
  "id" integer DEFAULT nextval('guias_remision_id_seq'::regclass) NOT NULL,
  "serie" character varying NOT NULL,
  "numero" character varying NOT NULL,
  "fecha_emision" timestamp without time zone,
  "fecha_traslado" timestamp without time zone,
  "ruc_remitente" character varying,
  "remitente_nombre" character varying,
  "remitente_direccion" text,
  "remitente_ubigeo" character varying,
  "ruc_destinatario" character varying NOT NULL,
  "destinatario_nombre" character varying,
  "destinatario_direccion" text,
  "destinatario_ubigeo" character varying,
  "modalidad_transporte" character varying DEFAULT 'PRIVADO'::character varying,
  "placa_vehiculo" character varying,
  "conductor_dni" character varying,
  "conductor_nombre" character varying,
  "licencia_conductor" character varying,
  "transportista_ruc" character varying,
  "transportista_nombre" character varying,
  "motivo_traslado" character varying,
  "documento_asociado" character varying,
  "peso_total" numeric,
  "items_json" jsonb,
  "observaciones" text,
  "estado_sunat" character varying DEFAULT 'BORRADOR'::character varying,
  "cdr_response" text,
  "sunat_response" jsonb,
  "creado_por" integer,
  "created_at" timestamp without time zone DEFAULT now(),
  "updated_at" timestamp without time zone DEFAULT now(),
  "orden_compra_cliente" character varying,
  "factura" character varying
);
CREATE TABLE public."comprobantes" (
  "id" integer DEFAULT nextval('comprobantes_id_seq'::regclass) NOT NULL,
  "tipo_comprobante" character varying NOT NULL,
  "serie" character varying NOT NULL,
  "numero" integer NOT NULL,
  "fecha_emision" timestamp without time zone NOT NULL,
  "moneda" character varying DEFAULT 'PEN'::character varying,
  "cliente_tipo_doc" character varying NOT NULL,
  "cliente_numero_doc" character varying NOT NULL,
  "cliente_nombre" character varying NOT NULL,
  "cliente_direccion" text,
  "cliente_email" character varying,
  "cliente_telefono" character varying,
  "subtotal" numeric NOT NULL,
  "igv" numeric NOT NULL,
  "total" numeric NOT NULL,
  "items_json" jsonb NOT NULL,
  "observaciones" text,
  "estado_sunat" character varying DEFAULT 'BORRADOR'::character varying,
  "sunat_response" text,
  "cdr_response" text,
  "creado_por" integer,
  "created_at" timestamp without time zone DEFAULT now(),
  "updated_at" timestamp without time zone DEFAULT now(),
  "condicion_pago" character varying DEFAULT 'Contado'::character varying,
  "documento_asociado" character varying,
  "guia_vinculada" character varying,
  "pc_vinculado" character varying,
  "estado_credito" character varying DEFAULT 'Pendiente de aprobación'::character varying,
  "fecha_aprobacion" date,
  "fecha_vencimiento" date,
  "dias_credito" integer DEFAULT 30,
  "monto_retenido" numeric DEFAULT 0,
  "obs_retencion" text,
  "es_credito" boolean DEFAULT false,
  "tiene_retencion" boolean DEFAULT false,
  "porcentaje_retencion" numeric DEFAULT 3.00,
  "monto_a_pagar" numeric DEFAULT 0,
  "orden_compra_cliente" character varying
);
CREATE TABLE public."comprobantes_compra" (
  "id" integer DEFAULT nextval('comprobantes_compra_id_seq'::regclass) NOT NULL,
  "tipo_comprobante" character varying NOT NULL,
  "serie" character varying NOT NULL,
  "numero" integer NOT NULL,
  "fecha_emision" date NOT NULL,
  "moneda" character varying DEFAULT 'PEN'::character varying,
  "proveedor_tipo_doc" character varying NOT NULL,
  "proveedor_numero_doc" character varying NOT NULL,
  "proveedor_nombre" character varying NOT NULL,
  "proveedor_direccion" text,
  "proveedor_email" character varying,
  "proveedor_telefono" character varying,
  "subtotal" numeric DEFAULT 0 NOT NULL,
  "igv" numeric DEFAULT 0 NOT NULL,
  "total" numeric DEFAULT 0 NOT NULL,
  "items_json" jsonb DEFAULT '[]'::jsonb NOT NULL,
  "observaciones" text,
  "estado" character varying DEFAULT 'BORRADOR'::character varying,
  "creado_por" integer,
  "created_at" timestamp without time zone DEFAULT now(),
  "updated_at" timestamp without time zone DEFAULT now()
);
CREATE TABLE public."guias_remision_compra" (
  "id" integer DEFAULT nextval('guias_remision_compra_id_seq'::regclass) NOT NULL,
  "serie" character varying NOT NULL,
  "numero" integer NOT NULL,
  "fecha_emision" date NOT NULL,
  "fecha_traslado" date,
  "proveedor_ruc" character varying NOT NULL,
  "proveedor_nombre" character varying NOT NULL,
  "proveedor_direccion" text,
  "proveedor_ubigeo" character varying,
  "ruc_remitente" character varying NOT NULL,
  "remitente_nombre" character varying NOT NULL,
  "remitente_direccion" text,
  "remitente_ubigeo" character varying,
  "modalidad_transporte" character varying DEFAULT 'PRIVADO'::character varying,
  "placa_vehiculo" character varying,
  "conductor_dni" character varying,
  "conductor_nombre" character varying,
  "licencia_conductor" character varying,
  "transportista_ruc" character varying,
  "transportista_nombre" character varying,
  "motivo_traslado" character varying DEFAULT 'COMPRA'::character varying,
  "factura_asociada" character varying,
  "peso_total" numeric DEFAULT 0,
  "items_json" jsonb DEFAULT '[]'::jsonb NOT NULL,
  "observaciones" text,
  "estado" character varying DEFAULT 'BORRADOR'::character varying,
  "creado_por" integer,
  "created_at" timestamp without time zone DEFAULT now(),
  "updated_at" timestamp without time zone DEFAULT now()
);
CREATE TABLE public."transportistas" (
  "id" integer DEFAULT nextval('transportistas_id_seq'::regclass) NOT NULL,
  "nombre_completo" character varying NOT NULL,
  "dni" character varying,
  "placa" character varying,
  "medidas" character varying,
  "licencia" character varying,
  "telefono" character varying,
  "peso_carga" character varying,
  "tipo" character varying DEFAULT 'conductor'::character varying,
  "activo" boolean DEFAULT true,
  "created_at" timestamp without time zone DEFAULT now(),
  "updated_at" timestamp without time zone DEFAULT now()
);
CREATE TABLE public."inventario" (
  "id" integer DEFAULT nextval('inventario_id_seq'::regclass) NOT NULL,
  "producto_id" integer NOT NULL,
  "stock_actual" numeric DEFAULT 0,
  "stock_minimo" numeric DEFAULT 5,
  "stock_maximo" numeric DEFAULT 100,
  "ubicacion_almacen" character varying,
  "created_at" timestamp without time zone DEFAULT now(),
  "updated_at" timestamp without time zone DEFAULT now()
);
CREATE TABLE public."movimientos_inventario" (
  "id" integer DEFAULT nextval('movimientos_inventario_id_seq'::regclass) NOT NULL,
  "producto_id" integer NOT NULL,
  "tipo_movimiento" character varying,
  "cantidad" numeric NOT NULL,
  "costo_unitario" numeric,
  "stock_anterior" numeric,
  "stock_nuevo" numeric,
  "referencia" character varying,
  "motivo" character varying,
  "observaciones" text,
  "usuario_id" integer,
  "fecha_creacion" timestamp without time zone DEFAULT now()
);
CREATE TABLE public."recuentos_inventario" (
  "id" integer DEFAULT nextval('recuentos_inventario_id_seq'::regclass) NOT NULL,
  "producto_id" integer NOT NULL,
  "fecha_recuento" date DEFAULT CURRENT_DATE,
  "cantidad_sistema" numeric NOT NULL,
  "cantidad_fisica" numeric NOT NULL,
  "diferencia" numeric,
  "ubicacion" character varying,
  "observaciones" text,
  "ajuste_aplicado" boolean DEFAULT false,
  "usuario_id" integer,
  "fecha_creacion" timestamp without time zone DEFAULT now()
);
CREATE TABLE public."revalorizaciones_inventario" (
  "id" integer DEFAULT nextval('revalorizaciones_inventario_id_seq'::regclass) NOT NULL,
  "producto_id" integer NOT NULL,
  "costo_anterior" numeric,
  "costo_nuevo" numeric,
  "precio_anterior" numeric,
  "precio_nuevo" numeric,
  "motivo" text,
  "usuario_id" integer,
  "fecha_creacion" timestamp without time zone DEFAULT now()
);
CREATE TABLE public."erp_empresas" (
  "id" uuid DEFAULT gen_random_uuid() NOT NULL,
  "codigo" text NOT NULL,
  "nombre_corto" text NOT NULL,
  "nombre_comercial" text NOT NULL,
  "razon_social" text NOT NULL,
  "ruc" text NOT NULL,
  "direccion_fiscal" text,
  "telefono" text,
  "correo_documentos" text,
  "logo_url" text,
  "color_primario" text NOT NULL,
  "color_secundario" text NOT NULL,
  "color_pastel" text NOT NULL,
  "estado" text DEFAULT 'activo'::text NOT NULL,
  "created_at" timestamp with time zone DEFAULT now(),
  "updated_at" timestamp with time zone DEFAULT now()
);
CREATE TABLE public."erp_empresa_cuentas_bancarias" (
  "id" uuid DEFAULT gen_random_uuid() NOT NULL,
  "empresa_id" uuid NOT NULL,
  "banco" text NOT NULL,
  "tipo_cuenta" text,
  "moneda" text DEFAULT 'PEN'::text NOT NULL,
  "numero_cuenta" text,
  "cci" text,
  "es_principal" boolean DEFAULT false NOT NULL,
  "estado" text DEFAULT 'activo'::text NOT NULL,
  "created_at" timestamp with time zone DEFAULT now(),
  "updated_at" timestamp with time zone DEFAULT now()
);
CREATE TABLE public."erp_modulos" (
  "id" uuid DEFAULT gen_random_uuid() NOT NULL,
  "orden" integer NOT NULL,
  "codigo" text NOT NULL,
  "nombre" text NOT NULL,
  "descripcion" text,
  "estado" text DEFAULT 'activo'::text NOT NULL
);
CREATE TABLE public."erp_submodulos" (
  "id" uuid DEFAULT gen_random_uuid() NOT NULL,
  "modulo_id" uuid NOT NULL,
  "orden" integer NOT NULL,
  "codigo" text NOT NULL,
  "nombre" text NOT NULL,
  "descripcion" text,
  "estado" text DEFAULT 'activo'::text NOT NULL
);
CREATE TABLE public."erp_roles" (
  "id" uuid DEFAULT gen_random_uuid() NOT NULL,
  "codigo" text NOT NULL,
  "nombre" text NOT NULL,
  "descripcion" text,
  "es_admin" boolean DEFAULT false NOT NULL,
  "estado" text DEFAULT 'activo'::text NOT NULL
);
CREATE TABLE public."erp_rol_permisos" (
  "id" uuid DEFAULT gen_random_uuid() NOT NULL,
  "rol_id" uuid NOT NULL,
  "submodulo_id" uuid NOT NULL,
  "puede_ver" boolean DEFAULT false NOT NULL,
  "puede_crear" boolean DEFAULT false NOT NULL,
  "puede_editar" boolean DEFAULT false NOT NULL,
  "puede_aprobar" boolean DEFAULT false NOT NULL,
  "puede_anular" boolean DEFAULT false NOT NULL,
  "puede_eliminar" boolean DEFAULT false NOT NULL,
  "puede_exportar" boolean DEFAULT false NOT NULL,
  "puede_subir_evidencia" boolean DEFAULT false NOT NULL
);
CREATE TABLE public."erp_usuario_empresas" (
  "id" uuid DEFAULT gen_random_uuid() NOT NULL,
  "auth_user_id" uuid NOT NULL,
  "empresa_id" uuid NOT NULL,
  "rol_id" uuid NOT NULL,
  "es_empresa_principal" boolean DEFAULT false NOT NULL,
  "estado" text DEFAULT 'activo'::text NOT NULL,
  "created_at" timestamp with time zone DEFAULT now(),
  "updated_at" timestamp with time zone DEFAULT now()
);
CREATE TABLE public."erp_usuario_permisos" (
  "id" uuid DEFAULT gen_random_uuid() NOT NULL,
  "auth_user_id" uuid NOT NULL,
  "empresa_id" uuid NOT NULL,
  "submodulo_id" uuid NOT NULL,
  "puede_ver" boolean,
  "puede_crear" boolean,
  "puede_editar" boolean,
  "puede_aprobar" boolean,
  "puede_anular" boolean,
  "puede_eliminar" boolean,
  "puede_exportar" boolean,
  "puede_subir_evidencia" boolean,
  "observacion" text,
  "created_at" timestamp with time zone DEFAULT now(),
  "updated_at" timestamp with time zone DEFAULT now()
);
CREATE TABLE public."erp_correlativos" (
  "id" uuid DEFAULT gen_random_uuid() NOT NULL,
  "empresa_id" uuid NOT NULL,
  "documento" text NOT NULL,
  "codigo_documento" text,
  "prefijo" text NOT NULL,
  "anio" integer DEFAULT (EXTRACT(year FROM now()))::integer NOT NULL,
  "ultimo_numero" integer DEFAULT 0 NOT NULL,
  "estado" text DEFAULT 'activo'::text NOT NULL,
  "created_at" timestamp with time zone DEFAULT now(),
  "updated_at" timestamp with time zone DEFAULT now()
);
CREATE TABLE public."erp_parametros" (
  "id" uuid DEFAULT gen_random_uuid() NOT NULL,
  "empresa_id" uuid,
  "grupo" text NOT NULL,
  "codigo" text NOT NULL,
  "nombre" text NOT NULL,
  "valor_bool" boolean,
  "valor_text" text,
  "valor_num" numeric,
  "regla" text,
  "es_critico" boolean DEFAULT false NOT NULL,
  "estado" text DEFAULT 'activo'::text NOT NULL,
  "created_at" timestamp with time zone DEFAULT now(),
  "updated_at" timestamp with time zone DEFAULT now()
);
CREATE TABLE public."erp_alertas" (
  "id" uuid DEFAULT gen_random_uuid() NOT NULL,
  "empresa_id" uuid,
  "submodulo_id" uuid,
  "tipo" text DEFAULT 'info'::text NOT NULL,
  "titulo" text NOT NULL,
  "mensaje" text,
  "estado" text DEFAULT 'pendiente'::text NOT NULL,
  "created_by" uuid,
  "assigned_to" uuid,
  "created_at" timestamp with time zone DEFAULT now(),
  "updated_at" timestamp with time zone DEFAULT now()
);
CREATE TABLE public."erp_auditoria" (
  "id" uuid DEFAULT gen_random_uuid() NOT NULL,
  "empresa_id" uuid,
  "auth_user_id" uuid,
  "tabla" text NOT NULL,
  "registro_id" text,
  "accion" text NOT NULL,
  "data_anterior" jsonb,
  "data_nueva" jsonb,
  "created_at" timestamp with time zone DEFAULT now()
);
CREATE TABLE public."costos_productos" (
  "id" bigint GENERATED BY DEFAULT AS IDENTITY NOT NULL,
  "producto_id" integer NOT NULL,
  "fecha_registro" timestamp with time zone DEFAULT now(),
  "tipo_costo" character varying,
  "monto" numeric NOT NULL,
  "proveedor_id" integer,
  "factura_referencia" character varying,
  "observaciones" text,
  "creado_por" integer
);
CREATE TABLE public."precios_productos" (
  "producto_id" integer NOT NULL,
  "precio_venta" numeric DEFAULT 0.00 NOT NULL,
  "precio_lista" numeric DEFAULT 0.00,
  "margen_preferido" numeric DEFAULT 30.00,
  "actualizado_en" timestamp with time zone DEFAULT now(),
  "creado_en" timestamp with time zone DEFAULT now()
);
CREATE TABLE public."almacenes" (
  "id" integer DEFAULT nextval('almacenes_id_seq'::regclass) NOT NULL,
  "codigo" character varying NOT NULL,
  "nombre" character varying NOT NULL,
  "tipo" character varying,
  "responsable" character varying,
  "telefono" character varying,
  "direccion" text,
  "activo" boolean DEFAULT true,
  "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  "updated_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE public."categorias" (
  "id" integer DEFAULT nextval('categorias_id_seq'::regclass) NOT NULL,
  "codigo" character varying NOT NULL,
  "nombre" character varying NOT NULL,
  "tipo" character varying,
  "activo" boolean DEFAULT true,
  "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  "updated_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE public."um" (
  "id" integer DEFAULT nextval('um_id_seq'::regclass) NOT NULL,
  "codigo" character varying NOT NULL,
  "nombre" character varying NOT NULL,
  "abreviatura" character varying,
  "tipo" character varying DEFAULT 'General'::character varying,
  "decimales" boolean DEFAULT false,
  "activo" boolean DEFAULT true,
  "ambito" character varying DEFAULT 'COMPARTIDO'::character varying,
  "uso" integer DEFAULT 0,
  "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  "updated_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE public."notas_credito" (
  "id" integer DEFAULT nextval('notas_credito_id_seq'::regclass) NOT NULL,
  "serie" character varying DEFAULT 'FC01'::character varying NOT NULL,
  "numero" character varying NOT NULL,
  "fecha_emision" date DEFAULT CURRENT_DATE,
  "fecha_vencimiento" date,
  "cliente_tipo_doc" character varying DEFAULT 'RUC'::character varying,
  "cliente_numero_doc" character varying NOT NULL,
  "cliente_nombre" character varying NOT NULL,
  "cliente_direccion" text,
  "cliente_email" character varying,
  "cliente_telefono" character varying,
  "comprobante_asociado" character varying,
  "motivo" character varying,
  "monto" numeric DEFAULT 0,
  "observaciones" text,
  "estado" character varying DEFAULT 'Borrador'::character varying,
  "pdf_generado" boolean DEFAULT false,
  "fecha_pdf" timestamp without time zone,
  "creado_por" integer,
  "created_at" timestamp without time zone DEFAULT now(),
  "updated_at" timestamp without time zone DEFAULT now(),
  "empresa" character varying DEFAULT 'KCF'::character varying
);
CREATE TABLE public."devoluciones" (
  "id" integer DEFAULT nextval('devoluciones_id_seq'::regclass) NOT NULL,
  "numero" character varying NOT NULL,
  "fecha" timestamp without time zone DEFAULT now(),
  "estado" character varying DEFAULT 'Pendiente'::character varying,
  "ruc" character varying NOT NULL,
  "cliente" character varying NOT NULL,
  "comprobante_id" integer,
  "comprobante_numero" character varying,
  "guia" character varying,
  "motivo" character varying,
  "monto" numeric DEFAULT 0,
  "observaciones" text,
  "creado_por" integer,
  "created_at" timestamp without time zone DEFAULT now(),
  "updated_at" timestamp without time zone DEFAULT now(),
  "empresa" character varying DEFAULT 'KCF'::character varying
);
CREATE TABLE public."pedido_compra_pc" (
  "id" integer DEFAULT nextval('pedido_compra_pc_id_seq'::regclass) NOT NULL,
  "numero" character varying NOT NULL,
  "fecha" timestamp without time zone DEFAULT now(),
  "estado" character varying DEFAULT 'Pendiente'::character varying,
  "cotizacion_id" integer,
  "cotizacion_numero" character varying,
  "cliente" character varying NOT NULL,
  "ruc" character varying NOT NULL,
  "monto" numeric DEFAULT 0,
  "correo_origen" character varying,
  "fecha_recepcion" date,
  "fecha_despacho" date,
  "archivo_oc" character varying,
  "observaciones" text,
  "valida_precios" boolean DEFAULT false,
  "valida_cantidades" boolean DEFAULT false,
  "valida_stock" boolean DEFAULT false,
  "valida_entrega" boolean DEFAULT false,
  "valida_montos" boolean DEFAULT false,
  "responsable" character varying DEFAULT 'Hellen'::character varying,
  "lugar_entrega" text,
  "condicion_atencion" character varying,
  "creado_por" integer,
  "created_at" timestamp without time zone DEFAULT now(),
  "updated_at" timestamp without time zone DEFAULT now(),
  "empresa" character varying DEFAULT 'KCF'::character varying,
  "items_json" jsonb DEFAULT '[]'::jsonb,
  "medio" character varying,
  "entrega" text,
  "req_compra" character varying,
  "guia" character varying,
  "factura" character varying,
  "condicion_pago" character varying,
  "vendedor" character varying,
  "items" jsonb DEFAULT '[]'::jsonb,
  "valida_transporte" boolean DEFAULT false,
  "valida_margen" boolean DEFAULT false,
  "valida_vigencia" boolean DEFAULT false
);
CREATE TABLE public."despachos" (
  "id" integer DEFAULT nextval('despachos_id_seq'::regclass) NOT NULL,
  "numero" character varying NOT NULL,
  "fecha" timestamp without time zone DEFAULT now(),
  "fecha_despacho" timestamp without time zone,
  "estado" character varying DEFAULT 'Pendiente despacho'::character varying,
  "pc_id" integer,
  "pc_numero" character varying,
  "cotizacion_id" integer,
  "cotizacion_numero" character varying,
  "cliente" character varying NOT NULL,
  "ruc" character varying NOT NULL,
  "comprobante" character varying,
  "guia" character varying,
  "origen" character varying DEFAULT 'ALM-SMP'::character varying,
  "destino" text,
  "transportista" character varying,
  "observaciones" text,
  "responsable" character varying,
  "creado_por" integer,
  "created_at" timestamp without time zone DEFAULT now(),
  "updated_at" timestamp without time zone DEFAULT now(),
  "empresa" character varying DEFAULT 'KCF'::character varying,
  "items_json" jsonb DEFAULT '[]'::jsonb
);
CREATE TABLE public."despacho_productos" (
  "id" integer DEFAULT nextval('despacho_productos_id_seq'::regclass) NOT NULL,
  "despacho_id" integer,
  "codigo" character varying,
  "producto" character varying,
  "descripcion" text,
  "marca" character varying,
  "um" character varying,
  "cantidad" integer DEFAULT 1,
  "stock" integer DEFAULT 0,
  "almacen" character varying DEFAULT 'ALM-SMP'::character varying,
  "creado_en" timestamp without time zone DEFAULT now()
);
CREATE TABLE public."marcas" (
  "id" integer DEFAULT nextval('marcas_id_seq'::regclass) NOT NULL,
  "codigo" character varying NOT NULL,
  "nombre" character varying NOT NULL,
  "tipo" character varying DEFAULT 'Original'::character varying,
  "pais_origen" character varying,
  "proveedor_referencia" character varying,
  "web_marca" character varying,
  "ambito" character varying DEFAULT 'COMPARTIDO'::character varying,
  "estado" character varying DEFAULT 'Activo'::character varying,
  "obs" text,
  "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  "updated_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  "activo" boolean DEFAULT true
);
CREATE TABLE public."proveedores_contactos" (
  "id" integer DEFAULT nextval('proveedores_contactos_id_seq'::regclass) NOT NULL,
  "proveedor_id" integer NOT NULL,
  "nombre_contacto" character varying NOT NULL,
  "cargo" character varying,
  "telefono" character varying,
  "email" character varying,
  "principal" boolean DEFAULT false,
  "activo" boolean DEFAULT true,
  "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  "updated_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE public."proveedores_puntos_entrega" (
  "id" integer DEFAULT nextval('proveedores_puntos_entrega_id_seq'::regclass) NOT NULL,
  "proveedor_id" integer NOT NULL,
  "nombre_punto" character varying NOT NULL,
  "direccion" text,
  "telefono_contacto" character varying,
  "responsable" character varying,
  "horario_atencion" character varying,
  "instrucciones" text,
  "principal" boolean DEFAULT false,
  "activo" boolean DEFAULT true,
  "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  "updated_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  "horario" character varying
);
CREATE TABLE public."solicitudes_compra" (
  "id" bigint DEFAULT nextval('solicitudes_compra_id_seq'::regclass) NOT NULL,
  "numero_solicitud" character varying NOT NULL,
  "fecha" timestamp without time zone DEFAULT now(),
  "estado" character varying DEFAULT 'Borrador'::character varying,
  "producto" text NOT NULL,
  "cantidad" numeric DEFAULT 1,
  "unidad" character varying DEFAULT 'UND'::character varying,
  "area" character varying,
  "solicitante" character varying,
  "urgencia" character varying DEFAULT 'Media'::character varying,
  "justificacion" text,
  "creado_por" integer,
  "created_at" timestamp without time zone DEFAULT now(),
  "updated_at" timestamp without time zone DEFAULT now()
);
CREATE TABLE public."comparativos_proveedores" (
  "id" bigint DEFAULT nextval('comparativos_proveedores_id_seq'::regclass) NOT NULL,
  "numero_comparativo" character varying NOT NULL,
  "fecha" timestamp without time zone DEFAULT now(),
  "estado" character varying DEFAULT 'Borrador'::character varying,
  "producto" text NOT NULL,
  "proveedores_json" jsonb DEFAULT '[]'::jsonb,
  "creado_por" integer,
  "created_at" timestamp without time zone DEFAULT now(),
  "updated_at" timestamp without time zone DEFAULT now()
);
CREATE TABLE public."comprobantes_proveedor" (
  "id" bigint DEFAULT nextval('comprobantes_proveedor_id_seq'::regclass) NOT NULL,
  "tipo" character varying DEFAULT 'Factura'::character varying,
  "numero" character varying NOT NULL,
  "fecha" timestamp without time zone DEFAULT now(),
  "monto" numeric DEFAULT 0,
  "ruc_proveedor" character varying,
  "proveedor_nombre" character varying,
  "orden_compra_id" integer,
  "orden_compra_numero" character varying,
  "estado" character varying DEFAULT 'Pendiente'::character varying,
  "observaciones" text,
  "creado_por" integer,
  "created_at" timestamp without time zone DEFAULT now(),
  "updated_at" timestamp without time zone DEFAULT now(),
  "fecha_vencimiento" date,
  "monto_esperado" numeric,
  "cuadra" boolean,
  "empresa_id" uuid
);
CREATE TABLE public."recepciones_mercaderia" (
  "id" bigint DEFAULT nextval('recepciones_mercaderia_id_seq'::regclass) NOT NULL,
  "numero_recepcion" character varying NOT NULL,
  "fecha" timestamp without time zone DEFAULT now(),
  "estado" character varying DEFAULT 'Pendiente'::character varying,
  "orden_compra_id" integer,
  "orden_compra_numero" character varying,
  "proveedor_nombre" character varying,
  "producto" text NOT NULL,
  "cantidad" numeric DEFAULT 1,
  "unidad" character varying DEFAULT 'UND'::character varying,
  "estado_mercaderia" character varying DEFAULT 'Buen estado'::character varying,
  "observaciones" text,
  "creado_por" integer,
  "created_at" timestamp without time zone DEFAULT now(),
  "updated_at" timestamp without time zone DEFAULT now(),
  "producto_id" integer,
  "almacen_id" integer,
  "costo_unitario" numeric,
  "com_recepcion_id" integer,
  "oc_item_id" integer,
  "pedido_id" integer,
  "pedido_numero" character varying,
  "cliente" character varying,
  "guia_proveedor" character varying,
  "lote_serie" character varying,
  "fecha_vencimiento" date,
  "empresa_id" uuid
);
CREATE TABLE public."cotizaciones_eliminadas" (
  "id" integer DEFAULT nextval('cotizaciones_eliminadas_id_seq'::regclass) NOT NULL,
  "cotizacion_id_original" integer,
  "numero_cotizacion" character varying,
  "codigo_cotizacion" character varying,
  "cliente_id" integer,
  "cliente_razon_social" character varying,
  "cliente_ruc" character varying,
  "fecha_creacion" timestamp without time zone,
  "estado_anterior" character varying,
  "subtotal" numeric,
  "igv" numeric,
  "total" numeric,
  "condicion_pago" character varying,
  "tiempo_entrega" character varying,
  "direccion_entrega" text,
  "vendedor" character varying,
  "contacto_cliente" character varying,
  "telefono_cliente" character varying,
  "email_cliente" character varying,
  "nota_cotizacion" text,
  "requerimiento" text,
  "productos_json" jsonb,
  "datos_completos_json" jsonb,
  "motivo_eliminacion" text NOT NULL,
  "eliminado_por" integer,
  "eliminado_en" timestamp without time zone DEFAULT now()
);
CREATE TABLE public."logs_auditoria" (
  "id" integer DEFAULT nextval('logs_auditoria_id_seq'::regclass) NOT NULL,
  "tabla" character varying NOT NULL,
  "registro_id" integer NOT NULL,
  "accion" character varying NOT NULL,
  "usuario_id" integer,
  "detalles" jsonb,
  "fecha" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE public."ordenes_compra_items" (
  "id" integer DEFAULT nextval('ordenes_compra_items_id_seq'::regclass) NOT NULL,
  "orden_compra_id" integer NOT NULL,
  "producto" character varying NOT NULL,
  "cantidad" numeric DEFAULT 1 NOT NULL,
  "precio_unitario" numeric DEFAULT 0,
  "total" numeric DEFAULT 0,
  "created_at" timestamp without time zone DEFAULT now(),
  "producto_id" integer,
  "unidad" character varying,
  "pedido_id" integer,
  "pedido_numero" character varying,
  "cliente" character varying,
  "cantidad_recibida" numeric DEFAULT 0
);
CREATE TABLE public."finanzas_pagos" (
  "id" integer DEFAULT nextval('finanzas_pagos_id_seq'::regclass) NOT NULL,
  "tipo" character varying NOT NULL,
  "documento_tabla" character varying NOT NULL,
  "documento_id" integer NOT NULL,
  "documento_numero" character varying,
  "tercero_nombre" character varying,
  "tercero_documento" character varying,
  "fecha" date DEFAULT CURRENT_DATE NOT NULL,
  "monto" numeric NOT NULL,
  "metodo" character varying,
  "banco" character varying,
  "numero_operacion" character varying,
  "observaciones" text,
  "estado" character varying DEFAULT 'Registrado'::character varying NOT NULL,
  "usuario_id" integer,
  "usuario_nombre" character varying,
  "anulado_por" integer,
  "anulado_en" timestamp without time zone,
  "motivo_anulacion" text,
  "created_at" timestamp without time zone DEFAULT now()
);
CREATE TABLE public."inv_sede_empresa" (
  "id" integer DEFAULT nextval('inv_sede_empresa_id_seq'::regclass) NOT NULL,
  "almacen_id" integer NOT NULL,
  "empresa_id" uuid NOT NULL,
  "registrado_sunat" boolean DEFAULT false NOT NULL,
  "codigo_establecimiento" character varying,
  "es_domicilio_fiscal" boolean DEFAULT false NOT NULL,
  "observaciones" text,
  "updated_at" timestamp without time zone DEFAULT now()
);
CREATE TABLE public."inv_stock" (
  "empresa_id" uuid NOT NULL,
  "almacen_id" integer NOT NULL,
  "producto_id" integer NOT NULL,
  "cantidad" numeric DEFAULT 0 NOT NULL,
  "costo_promedio" numeric DEFAULT 0 NOT NULL,
  "valor" numeric DEFAULT 0 NOT NULL,
  "ultimo_ingreso" timestamp without time zone,
  "ultima_salida" timestamp without time zone,
  "ultimo_movimiento" timestamp without time zone
);
CREATE TABLE public."inv_movimientos" (
  "id" integer DEFAULT nextval('inv_movimientos_id_seq'::regclass) NOT NULL,
  "numero" character varying,
  "fecha" timestamp without time zone DEFAULT now() NOT NULL,
  "empresa_id" uuid NOT NULL,
  "almacen_id" integer NOT NULL,
  "producto_id" integer NOT NULL,
  "tipo" character varying NOT NULL,
  "motivo" character varying NOT NULL,
  "cantidad" numeric NOT NULL,
  "costo_unitario" numeric DEFAULT 0,
  "costo_total" numeric DEFAULT 0,
  "saldo_cantidad" numeric,
  "saldo_costo_promedio" numeric,
  "saldo_valor" numeric,
  "documento_tipo" character varying,
  "documento_numero" character varying,
  "tercero" character varying,
  "lote_serie" character varying,
  "fecha_vencimiento" date,
  "traslado_id" integer,
  "conteo_id" integer,
  "separacion_id" integer,
  "recepcion_id" integer,
  "grupo" character varying,
  "revierte_id" integer,
  "revertido_por_id" integer,
  "estado" character varying DEFAULT 'Registrado'::character varying NOT NULL,
  "observaciones" text,
  "usuario_id" integer,
  "usuario_nombre" character varying,
  "aprobado_por" character varying,
  "aprobado_en" timestamp without time zone,
  "motivo_rechazo" text,
  "created_at" timestamp without time zone DEFAULT now()
);
CREATE TABLE public."inv_traslados" (
  "id" integer DEFAULT nextval('inv_traslados_id_seq'::regclass) NOT NULL,
  "numero" character varying,
  "fecha" timestamp without time zone DEFAULT now() NOT NULL,
  "empresa_id" uuid NOT NULL,
  "origen_id" integer NOT NULL,
  "destino_id" integer NOT NULL,
  "estado" character varying DEFAULT 'En camino'::character varying NOT NULL,
  "guia_remision" character varying,
  "encargado" character varying,
  "observaciones" text,
  "enviado_por_id" integer,
  "enviado_por" character varying,
  "recibido_por_id" integer,
  "recibido_por" character varying,
  "recibido_en" timestamp without time zone,
  "observaciones_recepcion" text,
  "created_at" timestamp without time zone DEFAULT now()
);
CREATE TABLE public."inv_traslado_items" (
  "id" integer DEFAULT nextval('inv_traslado_items_id_seq'::regclass) NOT NULL,
  "traslado_id" integer NOT NULL,
  "producto_id" integer NOT NULL,
  "cantidad" numeric NOT NULL,
  "cantidad_recibida" numeric,
  "costo_unitario" numeric DEFAULT 0
);
CREATE TABLE public."inv_separaciones" (
  "id" integer DEFAULT nextval('inv_separaciones_id_seq'::regclass) NOT NULL,
  "numero" character varying,
  "empresa_id" uuid NOT NULL,
  "almacen_id" integer NOT NULL,
  "producto_id" integer NOT NULL,
  "cantidad" numeric NOT NULL,
  "cantidad_inicial" numeric NOT NULL,
  "cliente" character varying NOT NULL,
  "documento" character varying,
  "vence_el" date NOT NULL,
  "estado" character varying DEFAULT 'Activa'::character varying NOT NULL,
  "observaciones" text,
  "usuario_id" integer,
  "usuario_nombre" character varying,
  "cerrado_por" character varying,
  "cerrado_en" timestamp without time zone,
  "created_at" timestamp without time zone DEFAULT now()
);
CREATE TABLE public."inv_conteos" (
  "id" integer DEFAULT nextval('inv_conteos_id_seq'::regclass) NOT NULL,
  "numero" character varying,
  "fecha" timestamp without time zone DEFAULT now() NOT NULL,
  "empresa_id" uuid NOT NULL,
  "almacen_id" integer NOT NULL,
  "tipo" character varying DEFAULT 'General'::character varying NOT NULL,
  "estado" character varying DEFAULT 'En conteo'::character varying NOT NULL,
  "creado_por" character varying,
  "contado_por_id" integer,
  "contado_por" character varying,
  "contado_en" timestamp without time zone,
  "aprobado_por" character varying,
  "aprobado_en" timestamp without time zone,
  "observaciones" text,
  "created_at" timestamp without time zone DEFAULT now()
);
CREATE TABLE public."inv_conteo_items" (
  "id" integer DEFAULT nextval('inv_conteo_items_id_seq'::regclass) NOT NULL,
  "conteo_id" integer NOT NULL,
  "producto_id" integer NOT NULL,
  "cantidad_contada" numeric,
  "stock_sistema" numeric,
  "costo_promedio" numeric,
  "comentario" text
);
CREATE TABLE public."com_recepciones" (
  "id" integer DEFAULT nextval('com_recepciones_id_seq'::regclass) NOT NULL,
  "numero" character varying,
  "fecha" timestamp without time zone DEFAULT now() NOT NULL,
  "orden_compra_id" integer NOT NULL,
  "almacen_id" integer NOT NULL,
  "guia_proveedor" character varying NOT NULL,
  "traido_por_tipo" character varying NOT NULL,
  "traido_por_id" integer,
  "traido_por" character varying,
  "recibido_por_id" integer,
  "recibido_por" character varying,
  "con_diferencias" boolean DEFAULT false NOT NULL,
  "observaciones" text,
  "created_at" timestamp without time zone DEFAULT now(),
  "empresa_id" uuid
);
CREATE TABLE public."com_recepcion_items" (
  "id" integer DEFAULT nextval('com_recepcion_items_id_seq'::regclass) NOT NULL,
  "recepcion_id" integer NOT NULL,
  "oc_item_id" integer NOT NULL,
  "producto_id" integer,
  "pendiente_antes" numeric,
  "cantidad_buena" numeric DEFAULT 0 NOT NULL,
  "cantidad_danada" numeric DEFAULT 0 NOT NULL,
  "lote_serie" character varying,
  "fecha_vencimiento" date,
  "comentario" text
);
CREATE TABLE public."com_incidencias" (
  "id" integer DEFAULT nextval('com_incidencias_id_seq'::regclass) NOT NULL,
  "numero" character varying,
  "fecha" timestamp without time zone DEFAULT now() NOT NULL,
  "orden_compra_id" integer NOT NULL,
  "recepcion_id" integer,
  "comprobante_id" integer,
  "producto_id" integer,
  "tipo" character varying NOT NULL,
  "cantidad" numeric,
  "monto" numeric,
  "detalle" text,
  "estado" character varying DEFAULT 'Abierta'::character varying NOT NULL,
  "resolucion" text,
  "resuelto_por" character varying,
  "resuelto_en" timestamp without time zone,
  "reportado_por" character varying
);
CREATE TABLE public."com_historial" (
  "id" integer DEFAULT nextval('com_historial_id_seq'::regclass) NOT NULL,
  "orden_compra_id" integer NOT NULL,
  "fecha" timestamp without time zone DEFAULT now() NOT NULL,
  "usuario_id" integer,
  "usuario" character varying,
  "accion" character varying NOT NULL,
  "detalle" text
);
ALTER TABLE clientes_contactos ADD CONSTRAINT "clientes_contactos_pkey" PRIMARY KEY (id);
ALTER TABLE clientes ADD CONSTRAINT "clientes_pkey" PRIMARY KEY (id);
ALTER TABLE clientes_puntos_entrega ADD CONSTRAINT "clientes_puntos_entrega_pkey" PRIMARY KEY (id);
ALTER TABLE cotizacion_detalle ADD CONSTRAINT "cotizacion_detalle_pkey" PRIMARY KEY (id);
ALTER TABLE cotizaciones ADD CONSTRAINT "cotizaciones_pkey" PRIMARY KEY (id);
ALTER TABLE listas_precios ADD CONSTRAINT "listas_precios_pkey" PRIMARY KEY (id);
ALTER TABLE productos ADD CONSTRAINT "productos_pkey" PRIMARY KEY (id);
ALTER TABLE proveedores ADD CONSTRAINT "proveedores_pkey" PRIMARY KEY (id);
ALTER TABLE usuarios ADD CONSTRAINT "usuarios_pkey" PRIMARY KEY (id);
ALTER TABLE movimientos_stock ADD CONSTRAINT "movimientos_stock_pkey" PRIMARY KEY (id);
ALTER TABLE ordenes_compra ADD CONSTRAINT "ordenes_compra_pkey" PRIMARY KEY (id);
ALTER TABLE orden_compra_detalle ADD CONSTRAINT "orden_compra_detalle_pkey" PRIMARY KEY (id);
ALTER TABLE guias_remision ADD CONSTRAINT "guias_remision_pkey" PRIMARY KEY (id);
ALTER TABLE comprobantes ADD CONSTRAINT "comprobantes_pkey" PRIMARY KEY (id);
ALTER TABLE comprobantes_compra ADD CONSTRAINT "comprobantes_compra_pkey" PRIMARY KEY (id);
ALTER TABLE guias_remision_compra ADD CONSTRAINT "guias_remision_compra_pkey" PRIMARY KEY (id);
ALTER TABLE transportistas ADD CONSTRAINT "transportistas_pkey" PRIMARY KEY (id);
ALTER TABLE inventario ADD CONSTRAINT "inventario_pkey" PRIMARY KEY (id);
ALTER TABLE erp_correlativos ADD CONSTRAINT "erp_correlativos_pkey" PRIMARY KEY (id);
ALTER TABLE movimientos_inventario ADD CONSTRAINT "movimientos_inventario_pkey" PRIMARY KEY (id);
ALTER TABLE recuentos_inventario ADD CONSTRAINT "recuentos_inventario_pkey" PRIMARY KEY (id);
ALTER TABLE revalorizaciones_inventario ADD CONSTRAINT "revalorizaciones_inventario_pkey" PRIMARY KEY (id);
ALTER TABLE erp_empresas ADD CONSTRAINT "erp_empresas_pkey" PRIMARY KEY (id);
ALTER TABLE erp_empresa_cuentas_bancarias ADD CONSTRAINT "erp_empresa_cuentas_bancarias_pkey" PRIMARY KEY (id);
ALTER TABLE erp_modulos ADD CONSTRAINT "erp_modulos_pkey" PRIMARY KEY (id);
ALTER TABLE erp_submodulos ADD CONSTRAINT "erp_submodulos_pkey" PRIMARY KEY (id);
ALTER TABLE erp_roles ADD CONSTRAINT "erp_roles_pkey" PRIMARY KEY (id);
ALTER TABLE erp_rol_permisos ADD CONSTRAINT "erp_rol_permisos_pkey" PRIMARY KEY (id);
ALTER TABLE erp_usuario_empresas ADD CONSTRAINT "erp_usuario_empresas_pkey" PRIMARY KEY (id);
ALTER TABLE erp_usuario_permisos ADD CONSTRAINT "erp_usuario_permisos_pkey" PRIMARY KEY (id);
ALTER TABLE inv_conteo_items ADD CONSTRAINT "inv_conteo_items_pkey" PRIMARY KEY (id);
ALTER TABLE erp_parametros ADD CONSTRAINT "erp_parametros_pkey" PRIMARY KEY (id);
ALTER TABLE erp_alertas ADD CONSTRAINT "erp_alertas_pkey" PRIMARY KEY (id);
ALTER TABLE erp_auditoria ADD CONSTRAINT "erp_auditoria_pkey" PRIMARY KEY (id);
ALTER TABLE costos_productos ADD CONSTRAINT "costos_productos_pkey" PRIMARY KEY (id);
ALTER TABLE precios_productos ADD CONSTRAINT "precios_productos_pkey" PRIMARY KEY (producto_id);
ALTER TABLE almacenes ADD CONSTRAINT "almacenes_pkey" PRIMARY KEY (id);
ALTER TABLE categorias ADD CONSTRAINT "categorias_pkey" PRIMARY KEY (id);
ALTER TABLE um ADD CONSTRAINT "um_pkey" PRIMARY KEY (id);
ALTER TABLE notas_credito ADD CONSTRAINT "notas_credito_pkey" PRIMARY KEY (id);
ALTER TABLE devoluciones ADD CONSTRAINT "devoluciones_pkey" PRIMARY KEY (id);
ALTER TABLE pedido_compra_pc ADD CONSTRAINT "pedido_compra_pc_pkey" PRIMARY KEY (id);
ALTER TABLE despachos ADD CONSTRAINT "despachos_pkey" PRIMARY KEY (id);
ALTER TABLE despacho_productos ADD CONSTRAINT "despacho_productos_pkey" PRIMARY KEY (id);
ALTER TABLE marcas ADD CONSTRAINT "marcas_pkey" PRIMARY KEY (id);
ALTER TABLE proveedores_contactos ADD CONSTRAINT "proveedores_contactos_pkey" PRIMARY KEY (id);
ALTER TABLE proveedores_puntos_entrega ADD CONSTRAINT "proveedores_puntos_entrega_pkey" PRIMARY KEY (id);
ALTER TABLE solicitudes_compra ADD CONSTRAINT "solicitudes_compra_pkey" PRIMARY KEY (id);
ALTER TABLE comparativos_proveedores ADD CONSTRAINT "comparativos_proveedores_pkey" PRIMARY KEY (id);
ALTER TABLE comprobantes_proveedor ADD CONSTRAINT "comprobantes_proveedor_pkey" PRIMARY KEY (id);
ALTER TABLE recepciones_mercaderia ADD CONSTRAINT "recepciones_mercaderia_pkey" PRIMARY KEY (id);
ALTER TABLE cotizaciones_eliminadas ADD CONSTRAINT "cotizaciones_eliminadas_pkey" PRIMARY KEY (id);
ALTER TABLE logs_auditoria ADD CONSTRAINT "logs_auditoria_pkey" PRIMARY KEY (id);
ALTER TABLE ordenes_compra_items ADD CONSTRAINT "ordenes_compra_items_pkey" PRIMARY KEY (id);
ALTER TABLE finanzas_pagos ADD CONSTRAINT "finanzas_pagos_pkey" PRIMARY KEY (id);
ALTER TABLE inv_movimientos ADD CONSTRAINT "inv_movimientos_pkey" PRIMARY KEY (id);
ALTER TABLE inv_traslados ADD CONSTRAINT "inv_traslados_pkey" PRIMARY KEY (id);
ALTER TABLE inv_traslado_items ADD CONSTRAINT "inv_traslado_items_pkey" PRIMARY KEY (id);
ALTER TABLE inv_separaciones ADD CONSTRAINT "inv_separaciones_pkey" PRIMARY KEY (id);
ALTER TABLE inv_conteos ADD CONSTRAINT "inv_conteos_pkey" PRIMARY KEY (id);
ALTER TABLE inv_sede_empresa ADD CONSTRAINT "inv_sede_empresa_pkey" PRIMARY KEY (id);
ALTER TABLE inv_stock ADD CONSTRAINT "inv_stock_pkey" PRIMARY KEY (empresa_id, almacen_id, producto_id);
ALTER TABLE com_recepciones ADD CONSTRAINT "com_recepciones_pkey" PRIMARY KEY (id);
ALTER TABLE com_recepcion_items ADD CONSTRAINT "com_recepcion_items_pkey" PRIMARY KEY (id);
ALTER TABLE com_incidencias ADD CONSTRAINT "com_incidencias_pkey" PRIMARY KEY (id);
ALTER TABLE com_historial ADD CONSTRAINT "com_historial_pkey" PRIMARY KEY (id);
ALTER TABLE proveedores ADD CONSTRAINT "proveedores_ruc_key" UNIQUE (ruc);
ALTER TABLE usuarios ADD CONSTRAINT "usuarios_codigo_vendedor_key" UNIQUE (codigo_vendedor);
ALTER TABLE clientes ADD CONSTRAINT "clientes_numero_documento_key" UNIQUE (numero_documento);
ALTER TABLE cotizaciones ADD CONSTRAINT "cotizaciones_codigo_cotizacion_key" UNIQUE (codigo_cotizacion);
ALTER TABLE cotizaciones ADD CONSTRAINT "cotizaciones_numero_cotizacion_key" UNIQUE (numero_cotizacion);
ALTER TABLE productos ADD CONSTRAINT "productos_codigo_key" UNIQUE (codigo);
ALTER TABLE usuarios ADD CONSTRAINT "usuarios_usuario_key" UNIQUE (usuario);
ALTER TABLE ordenes_compra ADD CONSTRAINT "ordenes_compra_numero_orden_key" UNIQUE (numero_orden);
ALTER TABLE ordenes_compra ADD CONSTRAINT "ordenes_compra_codigo_orden_key" UNIQUE (codigo_orden);
ALTER TABLE inventario ADD CONSTRAINT "inventario_producto_id_key" UNIQUE (producto_id);
ALTER TABLE usuarios ADD CONSTRAINT "usuarios_auth_user_id_key" UNIQUE (auth_user_id);
ALTER TABLE erp_empresas ADD CONSTRAINT "erp_empresas_codigo_key" UNIQUE (codigo);
ALTER TABLE erp_empresas ADD CONSTRAINT "erp_empresas_ruc_key" UNIQUE (ruc);
ALTER TABLE erp_modulos ADD CONSTRAINT "erp_modulos_codigo_key" UNIQUE (codigo);
ALTER TABLE erp_submodulos ADD CONSTRAINT "erp_submodulos_codigo_key" UNIQUE (codigo);
ALTER TABLE erp_roles ADD CONSTRAINT "erp_roles_codigo_key" UNIQUE (codigo);
ALTER TABLE erp_rol_permisos ADD CONSTRAINT "erp_rol_permisos_rol_id_submodulo_id_key" UNIQUE (rol_id, submodulo_id);
ALTER TABLE erp_usuario_empresas ADD CONSTRAINT "erp_usuario_empresas_auth_user_id_empresa_id_key" UNIQUE (auth_user_id, empresa_id);
ALTER TABLE erp_usuario_permisos ADD CONSTRAINT "erp_usuario_permisos_auth_user_id_empresa_id_submodulo_id_key" UNIQUE (auth_user_id, empresa_id, submodulo_id);
ALTER TABLE erp_correlativos ADD CONSTRAINT "erp_correlativos_empresa_id_documento_anio_key" UNIQUE (empresa_id, documento, anio);
ALTER TABLE erp_parametros ADD CONSTRAINT "erp_parametros_empresa_id_codigo_key" UNIQUE (empresa_id, codigo);
ALTER TABLE almacenes ADD CONSTRAINT "almacenes_codigo_key" UNIQUE (codigo);
ALTER TABLE categorias ADD CONSTRAINT "categorias_codigo_key" UNIQUE (codigo);
ALTER TABLE um ADD CONSTRAINT "um_codigo_key" UNIQUE (codigo);
ALTER TABLE notas_credito ADD CONSTRAINT "notas_credito_numero_key" UNIQUE (numero);
ALTER TABLE devoluciones ADD CONSTRAINT "devoluciones_numero_key" UNIQUE (numero);
ALTER TABLE pedido_compra_pc ADD CONSTRAINT "pedido_compra_pc_numero_key" UNIQUE (numero);
ALTER TABLE despachos ADD CONSTRAINT "despachos_numero_key" UNIQUE (numero);
ALTER TABLE marcas ADD CONSTRAINT "marcas_codigo_key" UNIQUE (codigo);
ALTER TABLE solicitudes_compra ADD CONSTRAINT "solicitudes_compra_numero_solicitud_key" UNIQUE (numero_solicitud);
ALTER TABLE comparativos_proveedores ADD CONSTRAINT "comparativos_proveedores_numero_comparativo_key" UNIQUE (numero_comparativo);
ALTER TABLE recepciones_mercaderia ADD CONSTRAINT "recepciones_mercaderia_numero_recepcion_key" UNIQUE (numero_recepcion);
ALTER TABLE inv_movimientos ADD CONSTRAINT "inv_movimientos_numero_key" UNIQUE (numero);
ALTER TABLE inv_traslados ADD CONSTRAINT "inv_traslados_numero_key" UNIQUE (numero);
ALTER TABLE inv_separaciones ADD CONSTRAINT "inv_separaciones_numero_key" UNIQUE (numero);
ALTER TABLE inv_conteos ADD CONSTRAINT "inv_conteos_numero_key" UNIQUE (numero);
ALTER TABLE inv_sede_empresa ADD CONSTRAINT "inv_sede_empresa_almacen_id_empresa_id_key" UNIQUE (almacen_id, empresa_id);
ALTER TABLE com_recepciones ADD CONSTRAINT "com_recepciones_numero_key" UNIQUE (numero);
ALTER TABLE com_incidencias ADD CONSTRAINT "com_incidencias_numero_key" UNIQUE (numero);
ALTER TABLE clientes ADD CONSTRAINT "clientes_tipo_documento_check" CHECK ((tipo_documento = ANY (ARRAY['RUC'::text, 'DNI'::text])));
ALTER TABLE movimientos_stock ADD CONSTRAINT "movimientos_stock_tipo_check" CHECK (((tipo)::text = ANY ((ARRAY['ENTRADA'::character varying, 'SALIDA'::character varying, 'AJUSTE'::character varying])::text[])));
ALTER TABLE movimientos_inventario ADD CONSTRAINT "movimientos_inventario_tipo_movimiento_check" CHECK (((tipo_movimiento)::text = ANY ((ARRAY['ENTRADA'::character varying, 'SALIDA'::character varying, 'TRANSFERENCIA'::character varying, 'AJUSTE'::character varying])::text[])));
ALTER TABLE costos_productos ADD CONSTRAINT "costos_productos_tipo_costo_check" CHECK (((tipo_costo)::text = ANY ((ARRAY['costo_compra'::character varying, 'costo_almacenaje'::character varying, 'costo_transporte'::character varying, 'costo_manufactura'::character varying, 'otros'::character varying])::text[])));
ALTER TABLE cotizaciones ADD CONSTRAINT "cotizaciones_estado_check" CHECK ((estado = ANY (ARRAY['Borrador'::text, 'En Proceso'::text, 'En revisión'::text, 'Por validar'::text, 'Validado por Hellen'::text, 'Generada'::text, 'Aceptada por Cliente'::text, 'Aceptada'::text, 'Rechazada'::text, 'No concretada'::text, 'Anulada'::text, 'Eliminada'::text])));
ALTER TABLE finanzas_pagos ADD CONSTRAINT "finanzas_pagos_tipo_check" CHECK (((tipo)::text = ANY ((ARRAY['COBRO'::character varying, 'PAGO'::character varying])::text[])));
ALTER TABLE finanzas_pagos ADD CONSTRAINT "finanzas_pagos_monto_check" CHECK ((monto > (0)::numeric));
ALTER TABLE inv_movimientos ADD CONSTRAINT "inv_movimientos_cantidad_check" CHECK ((cantidad > (0)::numeric));
ALTER TABLE inv_traslado_items ADD CONSTRAINT "inv_traslado_items_cantidad_check" CHECK ((cantidad > (0)::numeric));
ALTER TABLE inv_separaciones ADD CONSTRAINT "inv_separaciones_cantidad_check" CHECK ((cantidad >= (0)::numeric));
ALTER TABLE inv_stock ADD CONSTRAINT "inv_stock_cantidad_check" CHECK ((cantidad >= (0)::numeric));
ALTER TABLE inv_movimientos ADD CONSTRAINT "inv_movimientos_tipo_check" CHECK (((tipo)::text = ANY ((ARRAY['ENTRADA'::character varying, 'SALIDA'::character varying])::text[])));
ALTER TABLE com_recepcion_items ADD CONSTRAINT "com_recepcion_items_cantidad_buena_check" CHECK ((cantidad_buena >= (0)::numeric));
ALTER TABLE com_recepcion_items ADD CONSTRAINT "com_recepcion_items_cantidad_danada_check" CHECK ((cantidad_danada >= (0)::numeric));
CREATE INDEX idx_comprobantes_compra_proveedor ON public.comprobantes_compra USING btree (proveedor_numero_doc);
CREATE INDEX idx_guias_remision_compra_proveedor ON public.guias_remision_compra USING btree (proveedor_ruc);
CREATE INDEX idx_comprobantes_estado_credito ON public.comprobantes USING btree (estado_credito);
CREATE INDEX idx_comprobantes_es_credito ON public.comprobantes USING btree (es_credito);
CREATE INDEX idx_comprobantes_fecha_vencimiento ON public.comprobantes USING btree (fecha_vencimiento);
CREATE INDEX idx_guias_ruc_destinatario ON public.guias_remision USING btree (ruc_destinatario);
CREATE INDEX idx_guias_estado ON public.guias_remision USING btree (estado_sunat);
CREATE INDEX idx_guias_serie_numero ON public.guias_remision USING btree (serie, numero);
CREATE INDEX idx_guias_fecha_emision ON public.guias_remision USING btree (fecha_emision);
CREATE INDEX idx_finanzas_pagos_doc ON public.finanzas_pagos USING btree (documento_tabla, documento_id);
CREATE INDEX idx_orden_detalle_orden_id ON public.orden_compra_detalle USING btree (orden_id);
CREATE INDEX idx_orden_detalle_producto_id ON public.orden_compra_detalle USING btree (producto_id);
CREATE INDEX idx_logs_auditoria_registro ON public.logs_auditoria USING btree (tabla, registro_id);
CREATE INDEX idx_logs_auditoria_fecha ON public.logs_auditoria USING btree (fecha DESC);
CREATE INDEX idx_cotizaciones_codigo ON public.cotizaciones USING btree (codigo_cotizacion);
CREATE INDEX idx_cotizaciones_estado ON public.cotizaciones USING btree (estado);
CREATE INDEX idx_cotizaciones_usuario_corr ON public.cotizaciones USING btree (usuario_id, correlativo);
CREATE INDEX idx_cotizaciones_fecha ON public.cotizaciones USING btree (fecha_creacion);
CREATE INDEX idx_usuario_permisos_auth_user_id ON public.erp_usuario_permisos USING btree (auth_user_id);
CREATE INDEX idx_usuario_permisos_empresa_id ON public.erp_usuario_permisos USING btree (empresa_id);
CREATE INDEX idx_usuario_permisos_submodulo_id ON public.erp_usuario_permisos USING btree (submodulo_id);
CREATE INDEX idx_usuarios_codigo_vendedor ON public.usuarios USING btree (codigo_vendedor);
CREATE INDEX idx_usuarios_estado ON public.usuarios USING btree (estado);
CREATE INDEX idx_usuarios_auth_user_id ON public.usuarios USING btree (auth_user_id);
CREATE INDEX idx_bancos_empresa ON public.erp_empresa_cuentas_bancarias USING btree (empresa_id);
CREATE INDEX idx_costos_producto_id ON public.costos_productos USING btree (producto_id);
CREATE INDEX idx_costos_fecha_registro ON public.costos_productos USING btree (fecha_registro DESC);
CREATE INDEX idx_costos_tipo_costo ON public.costos_productos USING btree (tipo_costo);
CREATE INDEX idx_costos_producto_tipo ON public.costos_productos USING btree (producto_id, tipo_costo);
CREATE INDEX idx_precios_producto_id ON public.precios_productos USING btree (producto_id);
CREATE INDEX idx_precios_venta ON public.precios_productos USING btree (precio_venta);
CREATE INDEX idx_proveedores_puntos_entrega_proveedor_id ON public.proveedores_puntos_entrega USING btree (proveedor_id);
CREATE INDEX idx_proveedores_puntos_entrega_activo ON public.proveedores_puntos_entrega USING btree (activo);
CREATE INDEX idx_proveedores_contactos_proveedor_id ON public.proveedores_contactos USING btree (proveedor_id);
CREATE INDEX idx_proveedores_contactos_activo ON public.proveedores_contactos USING btree (activo);
CREATE INDEX idx_devoluciones_numero ON public.devoluciones USING btree (numero);
CREATE INDEX idx_devoluciones_estado ON public.devoluciones USING btree (estado);
CREATE INDEX idx_devoluciones_cliente ON public.devoluciones USING btree (ruc);
CREATE INDEX idx_devoluciones_empresa ON public.devoluciones USING btree (empresa);
CREATE INDEX idx_despachos_numero ON public.despachos USING btree (numero);
CREATE INDEX idx_despachos_estado ON public.despachos USING btree (estado);
CREATE INDEX idx_despachos_cliente ON public.despachos USING btree (ruc);
CREATE INDEX idx_despachos_pc ON public.despachos USING btree (pc_numero);
CREATE INDEX idx_despachos_cotizacion ON public.despachos USING btree (cotizacion_numero);
CREATE INDEX idx_despachos_empresa ON public.despachos USING btree (empresa);
CREATE INDEX idx_despacho_productos_despacho ON public.despacho_productos USING btree (despacho_id);
CREATE INDEX idx_notas_credito_numero ON public.notas_credito USING btree (numero);
CREATE INDEX idx_notas_credito_estado ON public.notas_credito USING btree (estado);
CREATE INDEX idx_notas_credito_cliente ON public.notas_credito USING btree (cliente_numero_doc);
CREATE INDEX idx_notas_credito_empresa ON public.notas_credito USING btree (empresa);
CREATE INDEX idx_pc_numero ON public.pedido_compra_pc USING btree (numero);
CREATE INDEX idx_pc_estado ON public.pedido_compra_pc USING btree (estado);
CREATE INDEX idx_pc_cliente ON public.pedido_compra_pc USING btree (ruc);
CREATE INDEX idx_pc_cotizacion ON public.pedido_compra_pc USING btree (cotizacion_numero);
CREATE INDEX idx_pc_empresa ON public.pedido_compra_pc USING btree (empresa);
CREATE INDEX idx_solicitudes_numero ON public.solicitudes_compra USING btree (numero_solicitud);
CREATE INDEX idx_solicitudes_estado ON public.solicitudes_compra USING btree (estado);
CREATE INDEX idx_solicitudes_fecha ON public.solicitudes_compra USING btree (fecha);
CREATE INDEX idx_comparativos_numero ON public.comparativos_proveedores USING btree (numero_comparativo);
CREATE INDEX idx_comparativos_estado ON public.comparativos_proveedores USING btree (estado);
CREATE INDEX idx_inv_mov_prod ON public.inv_movimientos USING btree (producto_id, empresa_id, almacen_id, id);
CREATE INDEX idx_inv_mov_estado ON public.inv_movimientos USING btree (estado);
CREATE INDEX idx_inv_mov_recepcion ON public.inv_movimientos USING btree (recepcion_id);
CREATE INDEX idx_inv_sep_activa ON public.inv_separaciones USING btree (producto_id, empresa_id, almacen_id) WHERE ((estado)::text = 'Activa'::text);
CREATE INDEX idx_ordenes_items_orden ON public.ordenes_compra_items USING btree (orden_compra_id);
CREATE INDEX idx_oci_pedido ON public.ordenes_compra_items USING btree (pedido_id, producto_id);
CREATE INDEX idx_ordenes_compra_proveedor_id ON public.ordenes_compra USING btree (proveedor_id);
CREATE INDEX idx_ordenes_compra_estado ON public.ordenes_compra USING btree (estado);
CREATE INDEX idx_ordenes_compra_fecha_creacion ON public.ordenes_compra USING btree (fecha_creacion);
CREATE INDEX idx_ordenes_numero ON public.ordenes_compra USING btree (numero_orden);
CREATE INDEX idx_ordenes_estado ON public.ordenes_compra USING btree (estado);
CREATE INDEX idx_ordenes_proveedor ON public.ordenes_compra USING btree (proveedor_id);
CREATE INDEX idx_ordenes_fecha ON public.ordenes_compra USING btree (fecha_creacion);
CREATE INDEX idx_recepciones_numero ON public.recepciones_mercaderia USING btree (numero_recepcion);
CREATE INDEX idx_recepciones_estado ON public.recepciones_mercaderia USING btree (estado);
CREATE INDEX idx_recepciones_orden ON public.recepciones_mercaderia USING btree (orden_compra_id);
CREATE INDEX idx_rm_com ON public.recepciones_mercaderia USING btree (com_recepcion_id);
CREATE INDEX idx_cp_numero ON public.comprobantes_proveedor USING btree (numero);
CREATE INDEX idx_cp_estado ON public.comprobantes_proveedor USING btree (estado);
CREATE INDEX idx_cp_orden ON public.comprobantes_proveedor USING btree (orden_compra_id);
CREATE INDEX idx_com_inc_oc ON public.com_incidencias USING btree (orden_compra_id);
CREATE INDEX idx_com_hist_oc ON public.com_historial USING btree (orden_compra_id, id);
ALTER TABLE clientes_puntos_entrega ADD CONSTRAINT "clientes_puntos_entrega_cliente_id_fkey" FOREIGN KEY (cliente_id) REFERENCES clientes(id);
ALTER TABLE cotizacion_detalle ADD CONSTRAINT "cotizacion_detalle_cotizacion_id_fkey" FOREIGN KEY (cotizacion_id) REFERENCES cotizaciones(id);
ALTER TABLE cotizacion_detalle ADD CONSTRAINT "cotizacion_detalle_producto_id_fkey" FOREIGN KEY (producto_id) REFERENCES productos(id);
ALTER TABLE cotizaciones ADD CONSTRAINT "cotizaciones_cliente_id_fkey" FOREIGN KEY (cliente_id) REFERENCES clientes(id);
ALTER TABLE cotizaciones ADD CONSTRAINT "cotizaciones_usuario_id_fkey" FOREIGN KEY (usuario_id) REFERENCES usuarios(id);
ALTER TABLE listas_precios ADD CONSTRAINT "listas_precios_producto_id_fkey" FOREIGN KEY (producto_id) REFERENCES productos(id);
ALTER TABLE movimientos_stock ADD CONSTRAINT "movimientos_stock_producto_id_fkey" FOREIGN KEY (producto_id) REFERENCES productos(id) ON DELETE CASCADE;
ALTER TABLE orden_compra_detalle ADD CONSTRAINT "fk_orden_detalle_orden" FOREIGN KEY (orden_id) REFERENCES ordenes_compra(id) ON DELETE CASCADE;
ALTER TABLE inventario ADD CONSTRAINT "inventario_producto_id_fkey" FOREIGN KEY (producto_id) REFERENCES productos(id) ON DELETE CASCADE;
ALTER TABLE erp_usuario_permisos ADD CONSTRAINT "erp_usuario_permisos_empresa_id_fkey" FOREIGN KEY (empresa_id) REFERENCES erp_empresas(id) ON DELETE CASCADE;
ALTER TABLE erp_usuario_permisos ADD CONSTRAINT "erp_usuario_permisos_submodulo_id_fkey" FOREIGN KEY (submodulo_id) REFERENCES erp_submodulos(id) ON DELETE CASCADE;
ALTER TABLE movimientos_inventario ADD CONSTRAINT "movimientos_inventario_producto_id_fkey" FOREIGN KEY (producto_id) REFERENCES productos(id) ON DELETE CASCADE;
ALTER TABLE recuentos_inventario ADD CONSTRAINT "recuentos_inventario_producto_id_fkey" FOREIGN KEY (producto_id) REFERENCES productos(id) ON DELETE CASCADE;
ALTER TABLE revalorizaciones_inventario ADD CONSTRAINT "revalorizaciones_inventario_producto_id_fkey" FOREIGN KEY (producto_id) REFERENCES productos(id) ON DELETE CASCADE;
ALTER TABLE usuarios ADD CONSTRAINT "usuarios_auth_user_id_fkey" FOREIGN KEY (auth_user_id) REFERENCES auth.users(id) ON DELETE SET NULL;
ALTER TABLE erp_empresa_cuentas_bancarias ADD CONSTRAINT "erp_empresa_cuentas_bancarias_empresa_id_fkey" FOREIGN KEY (empresa_id) REFERENCES erp_empresas(id) ON DELETE CASCADE;
ALTER TABLE erp_submodulos ADD CONSTRAINT "erp_submodulos_modulo_id_fkey" FOREIGN KEY (modulo_id) REFERENCES erp_modulos(id) ON DELETE CASCADE;
ALTER TABLE erp_rol_permisos ADD CONSTRAINT "erp_rol_permisos_rol_id_fkey" FOREIGN KEY (rol_id) REFERENCES erp_roles(id) ON DELETE CASCADE;
ALTER TABLE erp_rol_permisos ADD CONSTRAINT "erp_rol_permisos_submodulo_id_fkey" FOREIGN KEY (submodulo_id) REFERENCES erp_submodulos(id) ON DELETE CASCADE;
ALTER TABLE erp_usuario_empresas ADD CONSTRAINT "erp_usuario_empresas_auth_user_id_fkey" FOREIGN KEY (auth_user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
ALTER TABLE erp_usuario_empresas ADD CONSTRAINT "erp_usuario_empresas_empresa_id_fkey" FOREIGN KEY (empresa_id) REFERENCES erp_empresas(id) ON DELETE CASCADE;
ALTER TABLE erp_usuario_empresas ADD CONSTRAINT "erp_usuario_empresas_rol_id_fkey" FOREIGN KEY (rol_id) REFERENCES erp_roles(id);
ALTER TABLE erp_usuario_permisos ADD CONSTRAINT "erp_usuario_permisos_auth_user_id_fkey" FOREIGN KEY (auth_user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
ALTER TABLE erp_correlativos ADD CONSTRAINT "erp_correlativos_empresa_id_fkey" FOREIGN KEY (empresa_id) REFERENCES erp_empresas(id) ON DELETE CASCADE;
ALTER TABLE erp_parametros ADD CONSTRAINT "erp_parametros_empresa_id_fkey" FOREIGN KEY (empresa_id) REFERENCES erp_empresas(id) ON DELETE CASCADE;
ALTER TABLE erp_alertas ADD CONSTRAINT "erp_alertas_empresa_id_fkey" FOREIGN KEY (empresa_id) REFERENCES erp_empresas(id) ON DELETE CASCADE;
ALTER TABLE erp_alertas ADD CONSTRAINT "erp_alertas_submodulo_id_fkey" FOREIGN KEY (submodulo_id) REFERENCES erp_submodulos(id) ON DELETE SET NULL;
ALTER TABLE erp_alertas ADD CONSTRAINT "erp_alertas_created_by_fkey" FOREIGN KEY (created_by) REFERENCES auth.users(id) ON DELETE SET NULL;
ALTER TABLE erp_alertas ADD CONSTRAINT "erp_alertas_assigned_to_fkey" FOREIGN KEY (assigned_to) REFERENCES auth.users(id) ON DELETE SET NULL;
ALTER TABLE erp_auditoria ADD CONSTRAINT "erp_auditoria_empresa_id_fkey" FOREIGN KEY (empresa_id) REFERENCES erp_empresas(id) ON DELETE SET NULL;
ALTER TABLE erp_auditoria ADD CONSTRAINT "erp_auditoria_auth_user_id_fkey" FOREIGN KEY (auth_user_id) REFERENCES auth.users(id) ON DELETE SET NULL;
ALTER TABLE precios_productos ADD CONSTRAINT "precios_productos_producto_id_fkey" FOREIGN KEY (producto_id) REFERENCES productos(id) ON DELETE CASCADE;
ALTER TABLE despacho_productos ADD CONSTRAINT "despacho_productos_despacho_id_fkey" FOREIGN KEY (despacho_id) REFERENCES despachos(id) ON DELETE CASCADE;
ALTER TABLE proveedores_contactos ADD CONSTRAINT "proveedores_contactos_proveedor_id_fkey" FOREIGN KEY (proveedor_id) REFERENCES proveedores(id) ON DELETE CASCADE;
ALTER TABLE proveedores_puntos_entrega ADD CONSTRAINT "proveedores_puntos_entrega_proveedor_id_fkey" FOREIGN KEY (proveedor_id) REFERENCES proveedores(id) ON DELETE CASCADE;
ALTER TABLE productos ADD CONSTRAINT "productos_proveedor_id_fkey" FOREIGN KEY (proveedor_id) REFERENCES proveedores(id);
ALTER TABLE cotizaciones ADD CONSTRAINT "cotizaciones_usuario_validacion_id_fkey" FOREIGN KEY (usuario_validacion_id) REFERENCES usuarios(id);
ALTER TABLE cotizaciones ADD CONSTRAINT "cotizaciones_usuario_aceptacion_id_fkey" FOREIGN KEY (usuario_aceptacion_id) REFERENCES usuarios(id);
ALTER TABLE cotizaciones ADD CONSTRAINT "cotizaciones_usuario_rechazo_id_fkey" FOREIGN KEY (usuario_rechazo_id) REFERENCES usuarios(id);
ALTER TABLE ordenes_compra_items ADD CONSTRAINT "ordenes_compra_items_orden_compra_id_fkey" FOREIGN KEY (orden_compra_id) REFERENCES ordenes_compra(id) ON DELETE CASCADE;
ALTER TABLE inv_conteo_items ADD CONSTRAINT "inv_conteo_items_conteo_id_fkey" FOREIGN KEY (conteo_id) REFERENCES inv_conteos(id) ON DELETE CASCADE;
ALTER TABLE inv_traslado_items ADD CONSTRAINT "inv_traslado_items_traslado_id_fkey" FOREIGN KEY (traslado_id) REFERENCES inv_traslados(id) ON DELETE CASCADE;
ALTER TABLE com_recepcion_items ADD CONSTRAINT "com_recepcion_items_recepcion_id_fkey" FOREIGN KEY (recepcion_id) REFERENCES com_recepciones(id);
ALTER TABLE clientes_contactos ADD CONSTRAINT "clientes_contactos_cliente_id_fkey" FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE CASCADE;CREATE SEQUENCE IF NOT EXISTS seq_codigo_cliente;
CREATE OR REPLACE FUNCTION public.generar_codigo_cliente() RETURNS trigger LANGUAGE plpgsql AS $f$ BEGIN IF NEW.codigo_cliente IS NULL OR NEW.codigo_cliente = '' THEN NEW.codigo_cliente := 'CLI-' || LPAD(CAST(NEXTVAL('seq_codigo_cliente') AS TEXT), 6, '0'); END IF; RETURN NEW; END; $f$;
CREATE OR REPLACE FUNCTION public.generar_codigo_proveedor() RETURNS trigger LANGUAGE plpgsql AS $f$ DECLARE n INTEGER; BEGIN SELECT COALESCE(MAX(CAST(SUBSTRING(codigo_proveedor FROM '[0-9]+') AS INTEGER)), 0) INTO n FROM proveedores WHERE codigo_proveedor IS NOT NULL; NEW.codigo_proveedor := 'PROV-' || LPAD((n + 1)::TEXT, 6, '0'); RETURN NEW; END; $f$;
CREATE OR REPLACE FUNCTION public.actualizar_updated_at_column() RETURNS trigger LANGUAGE plpgsql AS $f$ BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $f$;
CREATE OR REPLACE FUNCTION public.update_updated_at_column() RETURNS trigger LANGUAGE plpgsql AS $f$ BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $f$;
CREATE OR REPLACE FUNCTION public.erp_touch_updated_at() RETURNS trigger LANGUAGE plpgsql AS $f$ BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $f$;
CREATE OR REPLACE FUNCTION public.actualizar_stock_kardex() RETURNS trigger LANGUAGE plpgsql AS $f$ BEGIN IF NEW.tipo IN ('ENTRADA','AJUSTE') THEN UPDATE productos SET stock = stock + NEW.cantidad, updated_at = NOW() WHERE id = NEW.producto_id; ELSIF NEW.tipo = 'SALIDA' THEN UPDATE productos SET stock = stock - NEW.cantidad, updated_at = NOW() WHERE id = NEW.producto_id; END IF; RETURN NEW; END; $f$;
CREATE OR REPLACE FUNCTION public.erp_tomar_correlativo(p_empresa_codigo text, p_documento text, p_anio integer DEFAULT (EXTRACT(year FROM now()))::integer) RETURNS text LANGUAGE plpgsql AS $f$ DECLARE v_id uuid; v_codigo text; BEGIN SELECT c.id INTO v_id FROM erp_correlativos c JOIN erp_empresas e ON e.id = c.empresa_id WHERE e.codigo = p_empresa_codigo AND c.documento = p_documento AND c.anio = p_anio AND c.estado = 'activo' FOR UPDATE; IF v_id IS NULL THEN RAISE EXCEPTION 'No existe correlativo activo para %, %, %', p_empresa_codigo, p_documento, p_anio; END IF; UPDATE erp_correlativos SET ultimo_numero = ultimo_numero + 1, updated_at = NOW() WHERE id = v_id RETURNING prefijo || '-' || anio::text || '-' || LPAD(ultimo_numero::text, 4, '0') INTO v_codigo; RETURN v_codigo; END; $f$;
CREATE TRIGGER trg_generar_codigo_cliente BEFORE INSERT ON public.clientes FOR EACH ROW EXECUTE FUNCTION generar_codigo_cliente();
CREATE TRIGGER trigger_actualizar_stock AFTER INSERT ON public.movimientos_stock FOR EACH ROW EXECUTE FUNCTION actualizar_stock_kardex();
CREATE TRIGGER trigger_generar_codigo_proveedor BEFORE INSERT ON public.proveedores FOR EACH ROW EXECUTE FUNCTION generar_codigo_proveedor();
CREATE TRIGGER tr_ordenes_compra_updated_at BEFORE UPDATE ON public.ordenes_compra FOR EACH ROW EXECUTE FUNCTION actualizar_updated_at_column();
CREATE TRIGGER update_guias_remision_updated_at BEFORE UPDATE ON public.guias_remision FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
