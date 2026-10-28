# Informe de corrección del ERP (pruebasweb)

Fecha: 12/10/2026, actualizado el 13/10/2026 con el módulo de Inventario (sección 7) y el de Compras bajo pedido (sección 8); 14/10/2026 ajustado a la base real de Supabase (sección 9) y unido con tu ZIP del 14/10 + los 5 requerimientos del Excel (sección 10); 15/10/2026 cambios aplicados en tu Supabase y stock automático (sección 11); 15/10/2026 noche: 4 errores, multiempresa, colores y rótulos por empresa (sección 12) · Fuente: `pruebasweb 2.zip` (el ZIP original no se modificó).

## Qué se entrega

| Archivo | Contenido |
|---|---|
| `pruebasweb_corregido.zip` | Proyecto corregido, listo para ejecutar (ver sección 6). |
| `.env.example` | Plantilla de variables de entorno, sin credenciales. |
| `cambios_vs_original.patch` | Diferencias línea por línea contra el código original (las credenciales antiguas aparecen tachadas como `[CREDENCIAL RETIRADA]`). |
| `SUPABASE_CAMBIOS_15OCT_COMPLETO.sql` | Todo el SQL aplicado en tu Supabase el 15/10 (respaldo, seguridad, stock automático), con cómo deshacer cada parte. |
| `pruebasweb_corregido_anterior_15oct.zip` | La entrega del 14/10 con los 5 requerimientos, antes del stock automático. |
| `pruebasweb_corregido_anterior_14oct_supabase.zip` | La entrega del 14/10 ajustada a Supabase, antes de unir tu ZIP nuevo y los 5 requerimientos. |
| `pruebasweb_corregido_anterior_14oct_compras.zip` | La entrega con Compras, antes del ajuste a la base real (14/10). |
| `pruebasweb_corregido_anterior_13oct_inventario.zip` | La entrega con Inventario, antes de Compras, por si necesitas volver a ella. |
| `pruebasweb_corregido_anterior_12oct.zip` | La entrega del 12/10, sin Inventario, por si necesitas volver a ella. |
| `INFORME_CAMBIOS.md` | Este informe. |

**Fuera del ZIP corregido, a propósito:** `.env` (tiene tus credenciales reales: copia el tuyo a la carpeta), `.venv` (es de Windows; se recrea con `pip install`), la carpeta `.git` (estaba dañada), `app.log`, los 4 PDF de muestra y `erp_db.backup`. Todo eso sigue intacto en el ZIP original.

Cambios: 30 archivos, unas 3.600 líneas añadidas y 1.100 modificadas o retiradas. No se eliminó ningún módulo ni ninguna pantalla. Hasta el 14/10 no se ejecutó ninguna operación sobre la base de Supabase; el 15/10, con tu autorización escrita, se aplicaron los cambios de la sección 11 (sin tocar datos) y, esa noche, los de la sección 12 (columnas de empresa y la empresa de cada documento; sin borrar nada).

---

## 1. Errores encontrados y cómo se solucionaron

### Seguridad (críticos)
| # | Problema | Solución |
|---|---|---|
| 1 | La contraseña de la base de Supabase estaba escrita dentro de `database.py`, `main.py` y `render.yaml`. | Se retiró. La conexión se toma solo de `DATABASE_URL` (archivo `.env` o variables de Render). |
| 2 | La *anon key* de Supabase estaba escrita en `database.py`. | Se retiró. Ahora se lee de `SUPABASE_URL`/`SUPABASE_KEY`. |
| 3 | El login tenía una "puerta trasera": aceptaba contraseñas comunes (admin123, erika123, etc.) para cualquier usuario. | Se eliminó. Solo se acepta la contraseña real del usuario. |
| 4 | La consola del servidor mostraba las contraseñas y los parámetros SQL. | Se quitaron esos `print`. |
| 5 | Las contraseñas se guardaban en texto plano. | Las nuevas se guardan cifradas (hash). Las antiguas siguen funcionando, y `scripts/hashear_passwords.py --aplicar` las convierte sin que el usuario tenga que cambiarlas. |
| 6 | `/debug/session` mostraba la sesión a cualquiera, y `/debug/db-test` y `/api/test-db` eran públicas. | Se eliminó la primera y las otras dos quedaron solo para el administrador. |
| 7 | Casi todas las rutas `/api/...` respondían sin haber iniciado sesión. | Se añadió un control global: sin sesión no se accede a nada, salvo al login y a los archivos estáticos. |
| 8 | Cualquier usuario podía cambiar empresas, usuarios, correlativos y parámetros. | Ahora solo el administrador (roles en `ROLES_ADMIN`). Los demás usuarios solo pueden leer su propio registro y sus permisos. |
| 9 | La clave de sesión era fija. | Se lee de `SECRET_KEY`, y las cookies van con HttpOnly, SameSite y Secure configurable. Se añadieron cabeceras de seguridad. |

### Errores que hacían fallar páginas o APIs (error 500)
| # | Problema | Solución |
|---|---|---|
| 10 | `db_query` fallaba en cualquier consulta con `%` literal (por ejemplo `LIKE 'PRD-%'`), lo que rompía la numeración de productos. | Si la consulta no lleva parámetros, se ejecuta sin ellos. |
| 11 | `db_query` no devolvía filas en consultas `WITH ... RETURNING`. | Ahora devuelve filas siempre que la consulta las produce. |
| 12 | La tabla `clientes_punto_entrega` no existe; la real es `clientes_puntos_entrega`. | Nombre corregido. |
| 13 | `/api/productos` y `/api/productos/buscar` usaban SQLAlchemy, que no estaba configurado. | Ahora usan la misma conexión que el resto del sistema. |
| 14 | `/dashboard` pedía la plantilla `dashboard.html`, que no existe. | Redirige al inicio. |
| 15 | Las cotizaciones eliminadas daban error: el listado fallaba si no existía la tabla y el detalle consultaba la tabla equivocada. | La tabla se crea si falta (de forma segura) y el detalle lee `cotizaciones_eliminadas`. |
| 16 | `reportes.html`, `herramientas.html`, `papelera.html` y `configuracion.html` contenían solo la palabra "True". | Ahora son páginas normales con el menú y el aviso "Módulo en construcción". |
| 17 | `get_session_info` buscaba `usuario_id`, pero el login guarda `user_id`. | Acepta ambos. |
| 18 | Faltaban dependencias en `requirements.txt` (psycopg2, dotenv, pytz, bcrypt) y había otras sin uso que no instalaban bien. | Lista corregida. |

### Ventas y cotizaciones
| # | Problema | Solución |
|---|---|---|
| 19 | Los totales y el IGV se aceptaban tal como llegaban del navegador, y se podían manipular o quedar mal redondeados. | El servidor recalcula subtotal, descuento (en monto o en %), base imponible, IGV y total con decimales exactos. La tasa sale de `IGV_TASA` (18% por defecto). |
| 20 | Se podían guardar cotizaciones sin productos, con productos inexistentes o con cantidades negativas. | Se rechazan con un mensaje claro. |
| 21 | El correlativo COT podía duplicarse si dos personas guardaban a la vez. | Numeración bajo bloqueo en la base. Probado con 8 guardados simultáneos: sin duplicados. |
| 22 | No se guardaban contacto, teléfono, email ni validez. | Ahora se guardan. |
| 23 | Cualquier usuario podía validar, aceptar o rechazar, y se usaba el usuario 8 como responsable fijo. | Solo los aprobadores (`ROLES_APROBADORES`, que incluye hellen y erika), y se registra el usuario real de la sesión. |
| 24 | Los cambios de estado se hacían sin orden: se podía pasar de Borrador a Aceptada. | Se aplica el flujo **Borrador → En revisión/Por validar → Validado → Generada → Aceptada por Cliente**. El rechazo exige motivo y no se puede editar una cotización Generada, Aceptada, Rechazada o Anulada. Con `COTIZACION_REQUIERE_VALIDACION=false` el vendedor puede generar directamente. |
| 25 | Anular una cotización podía perder datos si fallaba a mitad del proceso. | El respaldo y la anulación se hacen en una sola transacción. Anular una cotización Generada o Aceptada requiere aprobador. |
| 26 | El pedido del cliente (PC) se podía crear desde cotizaciones anuladas o rechazadas, y su número podía repetirse. | Se rechaza en esos casos (y también si la cotización no está validada, cuando se exige). Avisa si la cotización ya tiene otro PC. Correlativo `PC-AAAAMMDD-NNNN` sin duplicados. |
| 27 | Al cargar un PC desde una cotización se aplicaba el IGV dos veces: el monto "sin IGV" mostraba el total con IGV y el monto "con IGV" lo multiplicaba otra vez por 1,18. | El monto sin IGV es el total menos el IGV y el monto con IGV es el total de la cotización. |
| 40 | El PDF de la cotización decía siempre "Este producto cuenta con un descuento del 10%", aunque la cotización no tuviera descuento, y mostraba "None" en la columna Modelo. | La frase solo aparece si hay descuento y muestra el monto real (por ejemplo "descuento de S/ 32.00"). Sin modelo se muestra "-". |

### Facturación (comprobantes, guías y notas de crédito)
| # | Problema | Solución |
|---|---|---|
| 28 | Los números de factura, boleta, guía y nota se generaban en el navegador con `Date.now()`, lo que daba números enormes y sin orden. | Los asigna el servidor de forma correlativa por tipo y serie (por ejemplo F001-00000001). En el formulario aparece "Automático". |
| 29 | Se podía emitir una factura sin RUC válido, con total 0 o con un IGV que no cuadraba. | La factura exige un RUC de 11 dígitos y un total mayor que 0. Si el IGV no cuadra, se recalcula. |
| 30 | `monto_a_pagar` quedaba vacío cuando no había retención. | Es igual al total (o al total menos el 3% cuando aplica retención). A crédito se calcula la fecha de vencimiento. |
| 31 | Se podía editar un comprobante ya emitido o pagado, y repetir un número. | Bloqueado: el número es único por tipo y serie, y los estados siguen un orden permitido. |
| 32 | Editar una guía creaba una guía nueva (duplicado) y anularla **borraba todos sus datos**. | Editar actualiza la misma guía y anular solo cambia su estado. |
| 33 | Una nota de crédito podía superar el monto del comprobante o no tener motivo. | Validado: monto mayor que 0, motivo obligatorio y sin superar el saldo. |

### Compras bajo pedido
| # | Problema | Solución |
|---|---|---|
| 34 | Editar una orden de compra creaba otra nueva (duplicado). | El formulario envía el id y el servidor actualiza la misma OC y reemplaza sus items. |
| 35 | El proveedor se perdía: el formulario enviaba el nombre y la base esperaba el id. | El proveedor se resuelve por id, RUC o nombre. Si no se encuentra, la OC se guarda y se avisa. |
| 36 | El número de OC lo inventaba el navegador. | Lo asigna el servidor (`OC-AAAAMMDD-NNNN`) sin duplicados. |
| 37 | Los totales de la OC venían del navegador, y el precio unitario se perdía según el nombre del campo. | Se recalculan en el servidor y se aceptan ambos nombres del campo. |
| 38 | Se podían editar órdenes ya Confirmadas, Recibidas o Anuladas, y al eliminar una OC quedaban sus items huérfanos. | Ambos casos están corregidos. |
| 39 | El comprobante del proveedor se podía registrar repetido, sin número o con RUC inválido. | Se valida el número, el RUC y el monto. Un duplicado se rechaza con un mensaje claro y la OC se vincula por su número. |

### Finanzas (el menú existía, pero el módulo no)
Se creó el módulo **Finanzas** (`/finanzas`), que antes era solo un enlace sin página:
- **Cuentas por cobrar:** comprobantes de venta con su saldo (total menos retención, notas de crédito y cobros) y un semáforo Vencido / Por vencer (7 días) / Al día / Pagado.
- **Cuentas por pagar:** comprobantes de proveedores, con el vencimiento calculado según la condición de pago de la OC y editable.
- **Cobros y pagos:** registro de pagos parciales, sin superar nunca el saldo. El documento pasa a "Pagado" al llegar a saldo 0. Se pueden anular movimientos, y la anulación revierte el estado. Queda registrado el usuario responsable.
- **Flujo de caja proyectado** a 4, 8 o 12 semanas, con exportación a CSV.
- Usa la tabla nueva `finanzas_pagos`, que se crea sola la primera vez (también está en `migrations/001_finanzas.sql`). No toca los datos existentes.

---

## 2. Resultados de las pruebas (ejecutadas de verdad)

Entorno de pruebas: PostgreSQL 16 local con un esquema **reconstruido a partir de las consultas del código**, porque no tengo el esquema real de Supabase. Nunca se conectó a Supabase.

| Prueba | Resultado |
|---|---|
| Pruebas automáticas (`pytest tests`, 37 pruebas iniciales + 17 de Inventario = **54/54 pasan** al 13/10: login, permisos, cotizaciones, IGV, descuentos, numeración en paralelo, PC, facturas, retención, guías, notas de crédito, OC, comprobantes de proveedor, cobros y pagos, flujo de caja) | **37/37 pasan**. También pasan al descomprimir el ZIP entregado. |
| Las mismas 37 pruebas sobre el código original | Solo pasan 6. Algunas fallan porque el código original no tenía esa función (Finanzas, por ejemplo), así que no equivalen a 31 errores distintos. |
| Recorrido de 125 rutas GET con sesión de administrador | Ningún error 500. Los 400/404 restantes se deben a parámetros faltantes o a que no hay datos (respuesta correcta). |
| Navegador real (Chromium), 23 páginas como administrador y como vendedor | Sin errores de JavaScript en consola. Solo fallan las fuentes y CDN externas, bloqueadas en mi entorno sin internet. El vendedor no puede abrir Configuración (redirige). |
| Flujos en el navegador | Cotización creada desde el formulario: total S/ 118,00 sobre 100 + IGV, con contacto, teléfono y validez guardados. OC creada y luego editada: no se duplica. Cobro registrado y anulado en Finanzas. Flujo de caja visible. |
| Flujo completo de una cotización en el navegador (13/10/2026) | Vendedor crea la cotización (40 × 145 + 80 × 16 = S/ 7.080,00 + IGV S/ 1.274,40 = S/ 8.354,40) y la envía a validar. Hellen rechaza otra con motivo (vuelve a Borrador) y genera esta. Al pasar a PC, el monto sin IGV es S/ 7.080,00 y con IGV S/ 8.354,40. PDF generado. Sin errores de JavaScript. |
| Conversión de contraseñas antiguas con `hashear_passwords.py` | El usuario sigue entrando con su misma contraseña. |

**No probado:**
- La generación de PDF solo se probó con datos de prueba.
- La consulta de RUC externa (sin internet en mi entorno).
- El envío a SUNAT, que no existe en el sistema.
- Nada se probó contra los datos reales de Supabase.

---

## 3. Pendientes y lo que necesito de ti

1. **Rota ya la contraseña de la base de datos de Supabase y la anon key.** Estuvieron escritas en el código y en el historial de git; quitarlas del código no las vuelve secretas otra vez. Después pon los valores nuevos en tu `.env` y en Render.
2. **Necesito el esquema real de la base** (Supabase > Database > Backups, o `pg_dump --schema-only`) o una copia de prueba. Mis pruebas usan un esquema reconstruido, así que conviene probar con una copia antes de desplegar.
3. **Multiempresa KCF / AGD:** hoy los datos no se separan por empresa. Para hacerlo necesito que decidas si cada empresa ve solo lo suyo y que tenga el esquema real.
4. Reportes, Herramientas y Papelera siguen sin funciones (no existían en el original). Inventario ya está hecho (sección 7).
5. Hay rutas de configuración duplicadas entre dos archivos (`configuracion_seguridad.py` y los de empresas, usuarios, etc.). Funciona, pero conviene unificarlas.
6. No hay integración real con SUNAT: el estado del comprobante se marca a mano.
7. `static/js/ventas.js` (750 KB) tiene funciones repetidas. Solo se corrigió lo necesario; reorganizarlo es un trabajo aparte.
8. Antes de crear índices únicos en producción, revisa los duplicados históricos con `migrations/002_revision_duplicados.sql` (solo lectura).

---

## 4. Cambios importantes que debes conocer

- **Sin `.env` el sistema no arranca.** Es intencional, para no conectarse con credenciales escritas en el código. Copia `.env.example` como `.env` y complétalo.
- **Los roles importan:** el rol de cada usuario (columna `usuarios.rol`) define quién es administrador, aprobador o de finanzas (ver `.env.example`). Revisa que tus usuarios tengan el rol correcto.
- **Los números de documento los pone el sistema,** no la persona que llena el formulario.
- **Las contraseñas comunes ya no abren ninguna cuenta.**

## 5. Archivos nuevos
`routes/finanzas.py` (antes solo mostraba una página vacía), `templates/finanzas.html`, `static/js/finanzas.js`, `static/css/finanzas.css`, `.env.example`, `.gitignore`, `README.md`, `migrations/001_finanzas.sql`, `migrations/002_revision_duplicados.sql`, `scripts/hashear_passwords.py`, `tests/conftest.py`, `tests/test_flujos.py`, `tests/schema_pruebas.sql`.

## 6. Instalación
```bash
# 1. Descomprimir pruebasweb_corregido.zip y entrar a la carpeta
cd pruebasweb
# 2. Entorno virtual
python -m venv .venv
.venv\Scripts\activate          # Windows  (Mac/Linux: source .venv/bin/activate)
# 3. Dependencias
pip install -r requirements.txt
# 4. Configuración: copiar .env.example como .env y completar DATABASE_URL y SECRET_KEY
# 5. Ejecutar
python main.py                  # http://localhost:5000
```
En Render, carga las mismas variables en *Environment*; `render.yaml` ya no lleva credenciales. Más detalle (roles, migraciones, pruebas) en el `README.md` del proyecto.


---

## 7. Inventario multiempresa y multisede (13/10/2026)

Antes era solo una pantalla vacía. Ahora el stock se lleva **por empresa (dueña legal) y por sede física**. Empresas y sedes son datos: se agregan en Configuración ▸ Empresas y Maestros ▸ Almacenes, así que una tercera o cuarta empresa entra sin tocar el código.

**Pestañas:** Qué revisar hoy · Stock consolidado · ¿Dónde está? · Entradas y salidas · Traslados y ventas entre empresas · Separaciones · Conteos · Kardex · Sedes y SUNAT.

| Necesidad | Cómo lo resuelve el sistema |
|---|---|
| Consolidado del grupo | Tabla por producto: cada empresa en cada sede, total por empresa, total del grupo, separado y disponible. Exporta a CSV. |
| Saber dónde recoger | "¿Dónde está?" calcula si alcanza, qué traer de otra sede y qué vender entre empresas, y crea los traslados con un clic. |
| Productos revendidos | Separaciones por cliente con fecha límite. Una salida de venta no puede usar unidades separadas para otro cliente. |
| Pérdidas y robos | Nada se borra ni se edita. Pérdida, robo, merma, vencido y stock inicial quedan pendientes hasta que otra persona (supervisora) los aprueba. Los errores se corrigen con un movimiento contrario. |
| Logística no debe contar | Roles: `ROLES_ALMACEN` registra movimientos; `ROLES_CONTROL_INVENTARIO` cuenta. Conteo a ciegas y conteo sorpresa. Quien cuenta no aprueba, quien envía un traslado no lo recibe. |
| Traslados Breña ↔ SMP | Quedan "En camino" hasta que otra persona los recibe y cuenta. El faltante se registra con quién llevó la mercadería. Alerta si pasan 24 h o si no tienen guía. |
| Ventas intercompany | La mercadería cambia de dueño sin moverse (salida en una empresa, entrada en la otra). Alerta si falta la factura. |
| Stock que no se mueve | Rotación por producto: "Se mueve", "Lento" (30 días sin venta) e "Inmovilizado" (90 días); valor inmovilizado. Lotes con vencimiento avisan 30 días antes. |
| Kardex | Valorizado con costo promedio ponderado, por empresa y sede, con documento y responsable. Exportación con la estructura del formato 13.1 de SUNAT y el código de tipo de operación. |
| SUNAT | Pestaña para marcar, por empresa, qué sede es domicilio fiscal o establecimiento anexo. Alerta si una empresa guarda mercadería en una sede no declarada. |

**Cambios en otros módulos (importante):**
- **Compras ▸ Recepción ya no suma stock por su cuenta.** Antes sumaba buscando el nombre del producto con un parecido de texto (podía afectar a varios productos) y sumaba dos veces al pasar de "Aprobada" a "Almacenada". Ahora la recepción aprobada aparece en Inventario ▸ Entradas y salidas para ingresarla con un clic indicando empresa y sede, una sola vez.
- **Productos:** si un producto ya está en Inventario, su stock no se cambia desde la ficha del producto (solo con movimientos). `productos.stock` se mantiene como la suma de todas las empresas y sedes, para que Ventas siga funcionando igual.
- **Stock antiguo:** los productos que ya tenían stock antes de este módulo aparecen en "Qué revisar hoy" y deben registrarse con "Stock inicial" (empresa + sede) antes de moverlos.

**Tablas nuevas** (se crean solas; script en `migrations/003_inventario.sql`; no tocan datos existentes): `inv_stock`, `inv_movimientos`, `inv_traslados`, `inv_traslado_items`, `inv_separaciones`, `inv_conteos`, `inv_conteo_items`, `inv_sede_empresa`.

**Variables nuevas** (ver `.env.example`): `ROLES_ALMACEN`, `ROLES_CONTROL_INVENTARIO`, `INV_DIAS_LENTO`, `INV_DIAS_INMOVILIZADO`, `INV_DIAS_SEPARACION`, `INV_DIAS_AVISO_VENCIMIENTO`, `INV_PRODUCTOS_CONTEO_SORPRESA`.

**Archivos:** `routes/inventario.py`, `templates/inventario/index.html`, `static/js/inventario.js` y `static/css/inventario.css` (reescritos), `tests/test_inventario.py` y `migrations/003_inventario.sql` (nuevos); ajustes en `templates/base.html` (menú), `routes/compras.py`, `routes/productos.py`, `README.md` y `.env.example`.

**Pruebas:** 17 pruebas nuevas (costo promedio, stock nunca negativo incluso con 5 ventas simultáneas, separaciones, traslado con faltante, quien envía no recibe, intercompany, aprobación de pérdidas, conteo a ciegas, stock antiguo, recepción ingresada una sola vez, corrección por reversa, alerta SUNAT). Total **54/54**. Además se recorrieron las 9 pestañas en Chromium con 6 usuarios de ejemplo, sin errores de JavaScript.

**Recomendación SUNAT** (confirmar con el contador): declarar la sede de San Martín de Porres como establecimiento anexo de AGD (y Breña para KCF si guardará algo ahí), con un contrato de cesión en uso como sustento; guía de remisión electrónica con motivo "Traslado entre establecimientos de la misma empresa" en cada traslado; factura con IGV a valor de mercado en cada venta entre empresas; denuncia policial o informe en cada robo, merma o vencido.

**No probado:** con los datos reales de Supabase (sigo sin el esquema real) ni la emisión de guías electrónicas (no hay integración con SUNAT).

### 7.1 ZIP solo del módulo de Inventario (13/10/2026)

`modulo_inventario_erp.zip` trae solo los archivos del Inventario, para copiarlos en el proyecto: ruta, pantalla, JS, CSS, `migrations/003_inventario.sql`, `migrations/001_finanzas.sql`, `.env.example`, pruebas, `README_INVENTARIO.md`, `INSTRUCCIONES_SUPABASE.md` y una carpeta `integracion/` con los 3 archivos de otros módulos que también cambiaron (`base.html`, `compras.py`, `productos.py`). Se probó copiándolo sobre una copia limpia: 54/54 pruebas. El SQL se ejecutó dos veces seguidas en una base vacía sin errores.

**Aviso (13/10/2026, tarde):** después de este ZIP se hizo el módulo de Compras (sección 8), que cambió otra vez `routes/inventario.py`, `static/js/inventario.js`, `templates/inventario/index.html`, `routes/compras.py` y `base.html`. Usa `pruebasweb_corregido.zip` completo; `modulo_inventario_erp.zip` quedó como versión anterior.

---

## 8. Compras bajo pedido (13/10/2026)

Pensado para comprar casi todo para un cliente (solo ~5% es stock), con varios proveedores, pago al contado (90%) o crédito, y entrega en SMP o Breña. Página nueva en `/compras`; la anterior sigue en `/compras/anterior` (menú Compras ▸ Pantallas anteriores). No se quitó nada.

**El camino de una compra (7 pasos, cada uno lo hace una persona distinta):**

1. **Pedido del cliente** → la pestaña "Pedidos por comprar" muestra qué falta comprar de cada pedido y si hay stock libre en el grupo (para no comprar de más).
2. **Orden de compra** por empresa compradora y sede de llegada (SMP o Breña). Avisa si el precio es más de 10% mayor que la última compra y si la sede no está declarada en SUNAT para esa empresa. Comprar para stock (sin cliente) pide un motivo.
3. **Aprobación** por otra persona (quien crea no aprueba).
4. **Pago** por Finanzas, solo a la cuenta registrada del proveedor. Al contado: hay que pagar antes de recoger.
5. **Recepción a ciegas** en la sede: quien recibe no ve las cantidades pedidas, cuenta y escribe lo que llegó. No puede recibir quien creó la orden ni quien recogió la mercadería. Guía del proveedor obligatoria y sin repetir. Faltantes, sobrantes y dañados se vuelven "incidencias" con responsable.
6. **Factura del proveedor** con cruce de 3 vías (orden, recibido, factura). Si no cuadra, se crea una incidencia.
7. **Ingreso a Inventario** con un clic (empresa, sede, costo y producto ya vienen fijos) y la mercadería queda **separada automáticamente para el cliente** del pedido, para que no se revenda.

**Pestañas:** Hoy en Compras · Pedidos por comprar · Órdenes de compra · Recibir mercadería · Pagos y facturas · Precios por producto. Imprime la orden para el proveedor y una "Hoja de recojo" con firmas.

**Historial:** cada paso queda en un historial que no se borra (quién, cuándo, qué). Un administrador puede saltarse la separación de funciones, pero queda registrado.

**Tablas nuevas** (se crean solas; script en `migrations/004_compras.sql`, probado dos veces seguidas sin errores): `com_recepciones`, `com_recepcion_items`, `com_incidencias`, `com_historial`, y columnas nuevas en `ordenes_compra`, `ordenes_compra_items`, `recepciones_mercaderia` y `comprobantes_proveedor`. No se borra ni se cambia ningún dato existente.

**Variables nuevas** (ver `.env.example`): `ROLES_COMPRAS`, `COMPRAS_MONTO_SIN_APROBACION` (0 = toda orden se aprueba), `COMPRAS_ALERTA_PRECIO_PCT` (10), `COMPRAS_TOLERANCIA_FACTURA` (S/ 1.00), `COMPRAS_DIAS_AVISO` (3).

**Archivos:** nuevos `routes/compras_flujo.py`, `templates/compras/flujo.html`, `templates/compras/imprimir_oc.html`, `static/js/compras_flujo.js`, `static/css/compras_flujo.css`, `migrations/004_compras.sql`, `tests/test_modulo_compras.py`. Ajustes en `main.py`, `routes/compras.py` (las órdenes nuevas no se editan desde la pantalla anterior), `routes/inventario.py` y su pantalla (ingreso desde Compras con datos fijos y separación automática), `templates/base.html` (menú) y `.env.example`.

**Error corregido de paso:** en Finanzas, anular un pago podía reabrir una factura que no tenía nada que ver; ahora solo afecta a la factura del pago.

**Pruebas:** 8 nuevas (flujo completo, permisos, recepción a ciegas, quien recoge no recibe, ingreso con separación, factura que no cuadra, cierre con faltante, alerta de precio, anulación, exportar e imprimir). Total **62/62**. Además se recorrió todo en Chromium con 6 usuarios de ejemplo, sin errores de JavaScript.

**Lo que falta de tu lado:** asignar roles (compras, finanzas, almacén), registrar la cuenta bancaria de cada proveedor, marcar las sedes en Inventario ▸ Sedes y SUNAT, y confirmar con el contador.

**Tener en cuenta:** los adelantos pagados a una orden se ven en Compras y pasan a Cuentas por pagar cuando se registra la factura. **No probado** con los datos reales de Supabase.

---

## 9. Ajuste a la base real de Supabase (14/10/2026)

Se revisó la estructura real de tu base (proyecto ERP_KCF) solo leyendo, sin cambiar nada (ver `/mnt/project-files/revision-supabase/`). Con esa estructura, 29 de las 62 pruebas fallaban. Ahora pasan **62/62 con tu estructura real** y también con el esquema anterior. **No se tocó tu base ni se aplicó ninguna migración.**

| Problema en tu base real | Qué se corrigió en el código |
|---|---|
| El id de empresa es UUID, el código esperaba un número: Inventario y Compras nuevos no dejaban elegir empresa. | El código acepta UUID (y números en bases antiguas): `utils.id_empresa`, `routes/inventario.py`, `routes/compras_flujo.py`, `static/js/inventario.js` y `static/js/compras_flujo.js` (comparaciones y el resumen "1 AGD en San Martín de Porres"). Las tablas nuevas toman el mismo tipo que `erp_empresas.id`. |
| `comprobantes.numero` es numérico: no se podían guardar facturas nuevas. | Numeración, control de duplicados y búsqueda del comprobante en notas de crédito funcionan con número o texto. El número se muestra con 8 dígitos (00000001). Si alguien escribe letras en el número, se avisa. |
| Cuentas por cobrar y flujo de caja salían vacíos. | `routes/finanzas.py` ya no mezcla texto con el número del comprobante. |
| La lista de recepciones en Inventario no cargaba (columna `orden_compra` no existe). | Usa `orden_compra_numero`. |
| Crear usuarios desde Configuración fallaba (ya pasaba en el sistema original). | Se llenan también `usuario`, `nombre_completo`, `password` (siempre cifrada) y `rol`. Si el usuario no existe antes en Supabase Auth, sale un mensaje claro en vez del error técnico. |
| Notas de crédito: RUC del cliente obligatorio en la base real. | Si no se escribe, se toma del comprobante que corrige. |
| Editar un producto sin enviar familia o unidad fallaba. | Se conserva la familia y la unidad que ya tenía. |
| `numero_recepcion` es único en tu base: una recepción con 2 productos fallaba. | Cada producto queda como RC-…-1, RC-…-2. |
| `creado_por` es numérico en tu base. | Compras guarda el id del usuario, no su nombre. |

**Pruebas:** `tests/schema_supabase_real.sql` es la estructura real (sin datos ni credenciales) y ahora es la de las pruebas por defecto. Con `TEST_ESQUEMA=reconstruido` se usa la anterior. Además se recorrió Compras e Inventario en el navegador sobre la estructura real (con empresas UUID), sin errores de JavaScript.

**Migraciones:** `003_inventario.sql` y `004_compras.sql` ahora dicen `empresa_id UUID` para coincidir con Supabase. **No hace falta ejecutarlas:** esas tablas ya existen en tu base.

**Pendiente que requiere tu autorización (no aplicado):** activar la seguridad por filas (RLS) en 5 tablas que hoy cualquiera con la anon key puede leer y cambiar (`finanzas_pagos`, `com_recepciones`, `com_recepcion_items`, `com_incidencias`, `com_historial`), rotar la contraseña de la base y la anon key, y revisar la función `erp_link_usuario` (crea usuarios con contraseña fija). Detalle en `/mnt/project-files/revision-supabase/HALLAZGOS_TECNICOS.md`.

**Sin cambio:** `database.insertar_cliente_completo` usa columnas que no existen en tu base, pero ninguna pantalla la llama.

---

## 10. Tu ZIP del 14/10 + los 5 requerimientos obligatorios del Excel (14/10/2026)

**De qué versión partí.** Tu ZIP nuevo (`pruebasweb (1).zip`) era nuestra entrega del 13/10 (con Compras) más tus cambios del 14/10. Lo comparé archivo por archivo con lo último entregado y uní las dos cosas:

| En tu ZIP | Qué hice |
|---|---|
| **Rótulo de la guía de remisión** (PDF con cliente, dirección, consignado, N° de guía y factura) en `routes/ventas.py`, `static/js/ventas.js`, `templates/ventas/index.html` y `pdf_generator.py`. | **Se conservó completo.** Probado: genera el PDF de una guía emitida. |
| Ajuste de empresa a UUID en Inventario y Compras. | Ya estaba hecho en la entrega del 14/10 (sección 9) y de forma más completa: se quedó esa versión. |
| En `routes/inventario.py` se había perdido la **separación automática** de lo comprado bajo pedido (evita que se revenda lo que llega para un cliente) y el control "no ingresar más de lo recibido en Compras". | **Se mantuvieron** (no se quita nada sin tu permiso). |
| Carpeta `integracion/` (copias viejas de `compras.py`, `productos.py`, `base.html`). | No va en el ZIP: el sistema no la usa y son versiones antiguas. Sigue en tu ZIP. |
| `.env` (igual al original, con la contraseña antigua), `app.log`, 4 PDF de muestra, `erp_db.backup`. | Fuera del ZIP, como siempre. **La contraseña de la base todavía no se ha cambiado.** |

**Los 5 requerimientos obligatorios**

| # | Requerimiento | Estado | Cómo funciona |
|---|---|---|---|
| 1 | Al despachar el PC: letras negras con fondo azulito | ✅ Hecho | En **Entregas**, el despacho que ya salió se pinta entero en azulito con letras negras y la etiqueta "🚚 Despachado". En **PC Pedido Compras**, el PC cuyo despacho ya salió se pinta igual. |
| 2 | Hellen rechaza → "RECHAZADO" (no observado) | ✅ Hecho | Al rechazar, la cotización queda **Rechazada** (antes volvía a "Borrador" sin aviso), en rojo, con el motivo guardado. El vendedor la corrige directamente y la vuelve a enviar a validación. Nuevo contador "Rechazadas" y filtro. La base ya aceptaba ese estado: no hizo falta cambiarla. |
| 3 | Botones: 1) Crear Despacho 2) Crear Guía 3) Crear Factura en KCF | ✅ Hecho | En el menú (⋮) de la cotización, en ese orden. Guía y factura aparecen cuando la cotización está aceptada por el cliente (como antes). |
| 4 | Producto que falta → "Pendiente por compra" / "Pendiente por recojo" | ✅ Hecho | Se calcula solo, con el stock libre de todo el grupo (Inventario) y las OC aprobadas (Compras): **Pendiente por compra** = falta y no hay OC aprobada; **Pendiente por recojo** = ya se compró y nosotros lo recogemos; **Por llegar** = ya se compró y el proveedor lo trae. Se ve en Productos, Cotizaciones, PC y Entregas. Pasando el mouse se ve qué producto falta. En Productos, un producto sin stock que nadie pidió sale "Sin stock" (no "por comprar"), porque se trabaja bajo pedido. |
| 5 | Botón "Crear Facturas" en Guías de Remisión | ✅ Hecho | Botón azul **🧾 Crear factura** en cada guía que aún no tiene factura (y en su menú ⋮). Abre la factura con la guía vinculada, el cliente, el RUC y los productos ya llenos; solo se revisa y se guarda. |

**Errores que aparecieron al probar y se corrigieron:** la columna "Comprobante" de Guías mostraba la cotización como si fuera la factura (ahora muestra la factura real); y la lista de guías perdía los productos porque en Supabase vienen como JSON (al crear la factura desde la guía salía vacía).

**Pruebas:** 6 pruebas nuevas en `tests/test_requerimientos_excel.py` y la de rechazo actualizada. **68/68** con tu estructura real y con la reconstruida. Además se recorrieron las pantallas en Chromium con datos de demostración en una base local (nunca en Supabase), sin errores de JavaScript.

**Archivos:** nuevo `routes/abastecimiento.py` (solo lee, no crea tablas); cambios en `main.py`, `routes/ventas.py`, `static/js/ventas.js`, `static/css/ventas.css`, `templates/ventas/index.html`, `templates/base_datos_producto.html`, `pdf_generator.py` (tu rótulo). Se mantuvieron los saltos de línea CRLF.

### 10.1 Revisión de Supabase (solo lectura) y lo que necesita tu autorización

Nada se cambió en tu base. Encontré:

- ✅ 61 de 66 tablas con RLS activo. El ERP entra como dueño de la base, así que el RLS no lo bloquea.
- ❌ **Crítico:** 5 tablas sin RLS (`finanzas_pagos`, `com_recepciones`, `com_recepcion_items`, `com_incidencias`, `com_historial`): cualquiera con la anon key puede leerlas y cambiarlas.
- ❌ **Crítico:** `erp_link_usuario` la puede ejecutar cualquiera sin iniciar sesión y crea administradores con contraseña fija.
- ⚠️ La contraseña de la base y la anon key siguen siendo las del ZIP original (el `.env` de tu ZIP nuevo es el mismo).
- ⚠️ Medio: 9 funciones sin `search_path` fijo, el mismo disparador puesto 3 veces en `clientes`, 3 índices duplicados en `ordenes_compra`, 4 índices útiles que faltan.
- ℹ️ La vista `vista_comparativo_costos` es SECURITY DEFINER (el ERP no la usa desde fuera; se puede revisar después).

Todo eso está en **`migrations/005_propuesta_seguridad_y_rendimiento.sql`**, probado en una copia y con instrucciones para deshacer. **No borra ni cambia datos.** Se aplica solo con tu "sí" por escrito. **→ Aplicado el 15/10 con tu autorización (sección 11); el archivo ahora se llama `migrations/005_seguridad_y_rendimiento.sql`.**

### 10.2 Lo que pide el prompt y no hice, y por qué

| Pedido | Por qué no | Propuesta |
|---|---|---|
| **Venta descuenta stock sola** al despachar y **compra suma stock sola** al recibir. | Hoy el stock real está en Inventario por empresa y sede, y la salida se registra ahí. Si el despacho descontara solo, primero hay que saber de qué empresa y sede sale, y la base real tiene casi todo el stock aún sin cargar: los despachos se bloquearían o el stock quedaría negativo. | Paso siguiente: al "Despachar", elegir empresa y sede y que se registre la salida en el kardex en el mismo clic; y al recibir en Compras, que entre directo a Inventario. Lo hago si me dices que sí. **→ Hecho el 15/10 (sección 11.3).** |
| Disparadores (triggers) en la base para el stock. | El sistema ya calcula el stock en un solo lugar (Inventario, con bloqueo para ventas simultáneas). Un trigger además contaría doble. | Mantener un solo lugar. |
| RLS "por rol" (vendedor, Hellen, almacén…). | Los roles se controlan en el ERP (Flask), no en la base: la app entra con un solo usuario de base. RLS por rol no tendría efecto. | Mantener roles en el ERP + candado RLS para que nadie entre por fuera. |
| **Borrar datos de prueba e insertar datos "reales" inventados** (fase 5). | No se borran tus datos ni se inventan clientes, productos o ventas en tu base real: confundiría a tu equipo y a SUNAT. | Usé datos de demostración solo en una base local para probar y para las capturas. |
| Cambiar "PC observado" de la validación automática del PC. | El requerimiento habla del rechazo de **cotizaciones** por Hellen; "PC observado" es cuando el PC no coincide con la cotización. | Si también quieres "Rechazado" ahí, dímelo. |

---

## 11. Cambios aplicados en tu Supabase + stock automático (15/10/2026)

Con tu autorización por escrito (`SUPABASE.txt`). **No se borró ni se cambió ningún dato**: solo estructura. El SQL completo de todo lo aplicado está en **`SUPABASE_CAMBIOS_15OCT_COMPLETO.sql`** (y dentro del ZIP en `migrations/`).

### 11.1 Respaldo previo

Antes de tocar nada copié **las 66 tablas completas** al esquema **`respaldo_20261015`** (es lo mismo que `CREATE TABLE backup_[tabla]_[fecha] AS SELECT * FROM [tabla]`, pero en un esquema aparte que la API de Supabase no publica y que nadie de afuera puede leer).
Para recuperar algo: `INSERT INTO public.<tabla> SELECT * FROM respaldo_20261015.<tabla> WHERE ...;`. Cuando ya no lo necesites (en unas semanas) se borra con `DROP SCHEMA respaldo_20261015 CASCADE;`.

### 11.2 Qué cambió en Supabase (antes → después)

| # | Qué cambié | Antes | Después | Por qué | Cómo revertirlo |
|---|---|---|---|---|---|
| 1 | Candado (RLS) en `finanzas_pagos`, `com_recepciones`, `com_recepcion_items`, `com_incidencias`, `com_historial` | Sin RLS: cualquiera con la anon key podía leer y cambiar pagos y recepciones | RLS activo. El ERP sigue igual (entra como dueño de la base, que no lo usa) | Era el aviso crítico de Supabase | `ALTER TABLE public.<tabla> DISABLE ROW LEVEL SECURITY;` |
| 2 | `erp_link_usuario` | Creaba usuarios **administradores activos con contraseña 123456**, y a uno existente le pisaba contraseña y rol. La podía ejecutar cualquiera sin iniciar sesión | Crea el usuario como **vendedor, inactivo y sin contraseña usable**; a uno existente solo le actualiza nombre, área y correo. Nadie de afuera la puede ejecutar | Era la puerta más peligrosa de la base | Versión anterior guardada en `migrations/005_anterior_erp_link_usuario.sql` (no se recomienda volver) |
| 3 | Permiso de ejecutar `erp_tomar_correlativo`, `erp_has_perm`, `erp_has_empresa_access`, `erp_is_super_admin` | Cualquiera (anon) | Solo usuarios con sesión de Supabase (las usan las reglas de acceso) | Usuarios anónimos no deben usarlas | `GRANT EXECUTE ON FUNCTION ... TO anon;` |
| 4 | `search_path` fijo en 9 funciones (`generar_codigo_proveedor`, `actualizar_stock_kardex`, `generar_numero_orden`, `actualizar_updated_at_column`, `generar_codigo_orden_oficial`, `generar_codigo_cliente`, `update_updated_at_column`, `erp_touch_updated_at`, `erp_siguiente_correlativo`) | Sin fijar | `search_path = public` | Recomendación de seguridad de Supabase | `ALTER FUNCTION public.<función> RESET search_path;` |
| 5 | Disparador de código de cliente repetido | 3 disparadores hacían lo mismo al crear un cliente | Quedan `tr_generar_codigo_cliente` y `trg_generar_codigo_cliente` **desactivados**; sigue activo `trigger_generar_codigo` | Se ejecutaba 3 veces | `ALTER TABLE public.clientes ENABLE TRIGGER <nombre>;` |
| 6 | 4 índices nuevos: `idx_oci_producto`, `idx_cot_detalle_cotizacion`, `idx_cot_detalle_producto`, `idx_comprobantes_guia` | No existían | Creados | Aceleran Abastecimiento, Cotizaciones y Guías → Factura | `DROP INDEX public.<índice>;` |
| 7 | Vista `vista_comparativo_costos` | Se saltaba el candado (aviso ERROR de Supabase): mostraba costos a quien tuviera la anon key | Respeta el candado (`security_invoker`) | Los costos no deben salir por la API pública | `ALTER VIEW public.vista_comparativo_costos RESET (security_invoker);` |
| 8 | Columnas nuevas para el stock automático: en `despachos` (`stock_empresa_id`, `stock_almacen_id`, `stock_estado`, `stock_detalle`, `stock_fecha`) y en `inv_movimientos` (`despacho_id`) + índice `idx_inv_mov_despacho` | No existían | Creadas, vacías | Para saber de qué empresa y sede salió cada despacho y poder devolverlo si se anula | Ver final de `migrations/006_stock_automatico.sql` |

En Supabase quedaron registradas como `005a_rls_cinco_tablas`, `005b_permisos_y_search_path`, `005c_indices_nuevos`, `005d_desactivar_disparadores_repetidos`, `005e_erp_link_usuario_seguro`, `005f_vista_costos_security_invoker` y `006_stock_automatico`.

**Lo único que no se pudo hacer desde aquí:** borrar los 3 índices duplicados de `ordenes_compra` (`idx_ordenes_estado`, `idx_ordenes_fecha`, `idx_ordenes_proveedor`). La herramienta de Supabase exige una confirmación manual para todo `DROP` y no la puedo dar yo. No afectan datos ni el funcionamiento (solo ocupan un poco de espacio). Si quieres quitarlos, pega estas 3 líneas en el **SQL Editor** de Supabase:

```sql
DROP INDEX IF EXISTS public.idx_ordenes_estado;
DROP INDEX IF EXISTS public.idx_ordenes_fecha;
DROP INDEX IF EXISTS public.idx_ordenes_proveedor;
```

**Asesor de seguridad de Supabase después de los cambios:** desaparecieron los avisos de "tabla sin RLS" (crítico), de la vista (ERROR) y de las funciones sin `search_path`. Quedan:
- 53 tablas "con RLS sin reglas" (informativo): está bien así, significa que **nadie** entra por la API pública; el ERP entra como dueño.
- 4 funciones que pueden usar los usuarios con sesión de Supabase: es a propósito, las usan las reglas de acceso.
- "Protección de contraseñas filtradas" apagada: se activa en Supabase ▸ Authentication ▸ Settings (solo tú puedes).

### 11.3 Stock automático: Ventas ↔ Inventario ↔ Compras ↔ Caja

| Acción | Qué pasa ahora |
|---|---|
| **Despachar** (Ventas ▸ Entregas ▸ 🚚 Despachar) | Se abre la ventana de siempre con una lista nueva: **"¿De qué empresa y sede sale?"**. Ya viene elegida la que tiene todo (✅) y marca con ⚠️ las que no alcanzan. Al confirmar, cada producto sale del stock de esa empresa y sede y queda en el **kardex** como "Entrega a cliente (venta)" con el número del despacho y el cliente. Puede usar lo **separado para ese cliente**; lo separado para otros clientes no se toca. Si falta algo, **no se despacha nada** y dice qué falta. |
| **Anular un despacho** (botón nuevo ↩️ Anular, pide motivo) | El stock vuelve a la misma empresa y sede (movimiento "Corrección (reversa)" en el kardex) y lo que estaba separado para el cliente vuelve a quedar separado. |
| **Recibir una compra** (Compras ▸ Recibir mercadería) | Lo que llega en buen estado **entra solo** al inventario de la empresa de la OC, en la sede donde se recibió y con el costo de la OC (sin IGV). Si la compra era para un pedido de cliente, **queda separado para ese cliente**. Ya no hay que ingresarlo a mano en Inventario. Lo dañado no entra (queda como incidencia, como antes). |
| **Anular una factura o boleta** (Ventas ▸ Facturas) | Sus **cobros en caja se anulan solos** (con el motivo "Anulación automática: el comprobante fue anulado") y deja de aparecer en Cuentas por cobrar. |
| Kardex | Una salida hecha por un despacho no se puede "corregir" desde el kardex: se devuelve anulando el despacho (así no queda descuadrado). |

**Importante para tu equipo:**
- Para despachar, el producto **tiene que estar en Inventario** en esa empresa y sede. Hoy tu base tiene 10 productos con stock ubicado; lo que llegue por Compras entrará solo.
- Los **9 despachos que ya estaban en "Despachado"** antes de hoy no descontaron stock (el sistema anterior no lo hacía). No se tocaron; si se anula uno de ellos, no mueve stock.
- No se usaron disparadores (triggers) de base de datos para el stock: todo pasa por el mismo lugar que ya usa Inventario (con bloqueo para que dos ventas a la vez no saquen lo mismo).

**Archivos:** nuevo `routes/stock_automatico.py`; cambios en `routes/ventas.py` (despachar, anular despacho, anular comprobante), `routes/compras_flujo.py` (recibir), `routes/inventario.py` (bloqueo en kardex), `main.py`, `static/js/ventas.js`, `static/css/ventas.css`; migraciones `005_seguridad_y_rendimiento.sql`, `005_anterior_erp_link_usuario.sql`, `006_stock_automatico.sql` y `SUPABASE_CAMBIOS_15OCT_COMPLETO.sql`. Se mantuvieron los saltos de línea CRLF.

### 11.4 Verificación

**Tus datos, antes y después (conteo real en Supabase):**

| Tabla | Antes (respaldo) | Después |
|---|---|---|
| clientes | 41 | 41 |
| proveedores | 41 | 41 |
| productos | 21 | 21 |
| cotizaciones / detalle | 28 / 48 | 28 / 48 |
| pedidos (PC) | 12 | 12 |
| despachos | 15 | 15 |
| guías | 13 | 13 |
| comprobantes | 15 | 15 |
| órdenes de compra | 3 | 3 |
| usuarios | 6 | 6 |
| empresas | 2 | 2 |
| stock / kardex | 10 / 14 | 10 / 14 |
| cobros y pagos | 1 | 1 |

**Checklist por módulo**

| Módulo | Estado | Cómo se comprobó |
|---|---|---|
| Base de datos (datos intactos, candado activo) | ✅ | Conteos de arriba y consultas en Supabase; el usuario del ERP sigue leyendo las 5 tablas con candado |
| Login | ✅ | Navegador (Chromium) + pruebas |
| Ventas ▸ Cotizaciones (crear, validar, rechazar, aceptar) | ✅ | Pruebas + navegador |
| Ventas ▸ PC Pedido Compras | ✅ | Pruebas + navegador |
| Ventas ▸ Entregas / Despachos (con descuento de stock y anulación) | ✅ | 7 pruebas nuevas + navegador: despachar, ver kardex, anular, ver reversa |
| Ventas ▸ Guías de remisión (se crea al despachar, botón Crear factura) | ✅ | Pruebas + navegador |
| Ventas ▸ Facturas (anular anula cobros) | ✅ | Prueba nueva |
| Compras (OC, aprobación, pago, recepción con ingreso automático) | ✅ | Prueba del flujo completo actualizada |
| Inventario (stock, kardex, separaciones) | ✅ | Pruebas + navegador |
| Finanzas (cuentas por cobrar/pagar, cobros, anulación) | ✅ | Pruebas + navegador |
| Productos (estado de abastecimiento) | ✅ | Navegador |
| Borrar los 3 índices duplicados | ❌ | Requiere tu confirmación en el SQL Editor (ver 11.2). No afecta el funcionamiento |

**Pruebas automáticas: 75/75** con la estructura real de tu Supabase y 75/75 con la reconstruida (7 pruebas nuevas en `tests/test_stock_automatico.py` y la de Compras actualizada). El recorrido en el navegador se hizo con el ERP corriendo sobre una **copia local con la misma estructura de tu Supabase y datos de demostración**, sin errores de JavaScript; no se probó despachando sobre tu base real para no crear movimientos falsos en ella.

**Los 5 requerimientos del Excel siguen OK:**

| # | Requerimiento | Estado |
|---|---|---|
| 1 | Despacho del PC en negro sobre azulito | ✅ (y ahora además descuenta stock) |
| 2 | Rechazo de Hellen → RECHAZADA | ✅ |
| 3 | Botones Despacho → Guía → Factura en KCF | ✅ |
| 4 | "Pendiente por compra" / "Pendiente por recojo" | ✅ |
| 5 | Guías ▸ "Crear factura" | ✅ |

### 11.5 Lo que queda en tus manos

1. **Cambiar la contraseña de la base y la anon key** en Supabase (siguen siendo las del ZIP original) y ponerlas en tu `.env` y en Render. Solo tú puedes hacerlo.
2. Opcional: borrar los 3 índices duplicados (11.2) y activar "Protección de contraseñas filtradas".
3. Subir este ZIP a donde corre el ERP (Render). Mientras tanto, la versión que tienes funcionando sigue andando con la base ya cambiada (todo es compatible), pero el stock no se moverá solo hasta que subas el ZIP nuevo.

## 12. Corrección de 4 errores + multiempresa + colores + rótulos por empresa (15/10/2026, noche)

Pedido: tu mensaje "🚨 CORRECCIÓN DE BUGS + MULTIEMPRESA + COLORES + RÓTULOS + AUTORIZACIÓN TOTAL SUPABASE".
Lo aplicado en Supabase está en **`SUPABASE_007_MULTIEMPRESA.sql`** (y dentro del ZIP en `migrations/007_multiempresa.sql`), con su parte de **cómo deshacer** al final.

### 12.1 Confirmaciones

| | Qué | Cómo lo comprobé |
|---|---|---|
| ✅ | **Error 1:** el punto "Información adicional" (transporte, parihuela, nota interna, seguimiento y motivo) se guarda y vuelve a salir al reabrir la cotización | Prueba automática + captura: se guardó "Camioneta / Sí - estándar / Llamar al almacén antes de ir" y al reabrir aparecen los tres |
| ✅ | **Error 2:** el descuento (en S/ o en %) se guarda, vuelve a salir al reabrir y el total se recalcula | Prueba + captura: descuento S/ 20 → total S/ 708.00. También se corrigió que al reabrir mostraba el precio **actual** del producto en vez del precio cotizado |
| ✅ | **Error 3:** "🧾 Crear factura" de Guías ahora está **dentro del menú ⋮** (se quitó el botón de afuera) | Prueba + captura del menú |
| ✅ | **Error 4:** el stock se ve en Inventario | Ahora salen **todos** los productos (también los que tienen 0), con un aviso de los movimientos "por aprobar" y un botón **➕ Stock inicial** en los que no tienen stock. Al crear un producto se puede cargar su stock inicial con empresa y sede |
| ✅ | **Datos reales intactos** | En Supabase, antes y después: 29 cotizaciones, 43 clientes, 43 proveedores, 21 productos, 6 usuarios, 13 PC, 15 despachos, 13 guías, 15 facturas, 1 NC, 3 OC, 10 filas de stock, 14 movimientos de kardex. **No se borró nada.** (Tu mensaje decía 28 cotizaciones y 41 clientes; en la base hay 29 y 43.) |
| ✅ | **Multiempresa funcionando** | Selector arriba con KCF / AGD / Todas. Pruebas: una cotización de AGD no se ve en KCF y viceversa; en "Todas" se ven las dos; una factura hecha desde una cotización de AGD queda en AGD y su número empieza en 00000001 (cada RUC tiene su propio correlativo); la caja (cuentas por cobrar) sale por empresa |
| ✅ | **Los colores cambian con la empresa** | KCF rojo (#EF233C), AGD naranja (#FC6200), Todas gris. Salen de Configuración ▸ Empresas: si cambias el color allí, cambia en todo el sistema |
| ✅ | **Rótulos por empresa** | Botón "🏷️ Rótulo" en PC, Despachos y Guías. Sale con logo (o el nombre de la empresa si no hay logo), razón social, RUC, teléfono, correo, web, cliente, dirección, N° de pedido/despacho/guía, factura, QR y el color de la empresa. Pregunta cuántas cajas y saca una hoja por caja (1/3, 2/3, 3/3) |
| ✅ | **ZIP arranca en Render** | Lo descomprimí en una carpeta limpia y lo arranqué con el mismo comando de Render (`gunicorn main:app`): abre el login sin errores |
| ✅ | **Pruebas** | **87 de 87** pasan con la estructura real de tu Supabase y 87 de 87 con la otra estructura. Antes eran 75; se agregaron 12 de este pedido (`tests/test_multiempresa.py`) |

**Extra que encontré y arreglé:** la cotización, la factura y la guía en PDF tenían los datos de KCF escritos fijos (RUC, nombre, teléfono, web y **la cuenta del BBVA de KCF**). Una cotización de AGD habría salido con el RUC y la cuenta bancaria de KCF. Ahora cada PDF sale con los datos y las cuentas bancarias de su empresa (de Configuración ▸ Empresas ▸ Cuentas bancarias).

### 12.2 Dónde vive el stock (fuente de verdad)

```
                 PRODUCTOS (catálogo, uno para todo el grupo)
                          │
                          ▼
   inv_stock  ◄── LA FUENTE DE VERDAD: una fila por EMPRESA + SEDE + PRODUCTO
   ┌──────────┬──────────────────────┬──────────┬──────────┐
   │ Empresa  │ Sede                 │ Producto │ Cantidad │
   ├──────────┼──────────────────────┼──────────┼──────────┤
   │ KCF      │ San Martín de Porres │ Casco    │    25    │
   │ AGD      │ Breña                │ Casco    │    12    │
   └──────────┴──────────────────────┴──────────┴──────────┘
          ▲                                        │
          │ cada entrada/salida                    │ suma automática
   inv_movimientos (KARDEX: compra, venta,          ▼
   traslado, ajuste, stock inicial...)     productos.stock = 37
                                           (solo un total de referencia)
```

- **Se mueve solo:** comprar/recibir (entra), despachar (sale), anular despacho (vuelve), traslados entre sedes o empresas, ajustes y conteos.
- **Stock inicial de un producto nuevo:** Productos ▸ Nuevo producto ▸ tarjeta **"Stock inicial (opcional)"**: cantidad, empresa y sede. Si el producto ya existe y tiene 0: Inventario ▸ Stock consolidado ▸ botón **➕ Stock inicial**.
- **Si lo registra alguien que no aprueba** (vendedor, logística), queda **"por aprobar"** y no suma hasta que un supervisor lo apruebe en Inventario ▸ Qué revisar hoy. Así nadie "crea" mercadería sin control. En tu base hay **4 entradas de stock pendientes de aprobar**: por eso parecía que "no había stock".
- **Tablas viejas de stock unificadas:** `inventario`, `movimientos_inventario`, `movimientos_stock`, `recuentos_inventario` y `revalorizaciones_inventario` están **vacías (0 filas)** y el ERP ya no las usa, así que **no hubo nada que migrar**. No las borré (la herramienta de Supabase no deja borrar sin confirmación manual); están respaldadas y, si quieres quitarlas, el `DROP` está en el SQL. `inv_sede_empresa` también está vacía pero **sí se usa**: no borrarla.

### 12.3 Cómo funciona la multiempresa

```
   Selector arriba:  [ KCF ]   [ AGD ]   [ Todas las empresas ]
                        │          │              │
           cada lista muestra solo lo de esa      muestra todo junto
           empresa + lo compartido                (solo para mirar: para
                                                   crear hay que elegir una)

   Cada documento guarda su empresa (empresa_id) y la pasa al siguiente:
   Cotización ──► PC ──► Despacho ──► Guía ──► Factura ──► Cobro en caja
      AGD          AGD       AGD         AGD       AGD           AGD
   (aunque estés viendo otra empresa, el documento hijo hereda la del padre)

   Compartido por las dos empresas: productos, proveedores y clientes
   "COMPARTIDO". Un cliente marcado solo "KCF" se ve solo en KCF.
```

Módulos que filtran por empresa: Ventas (cotizaciones, revisión, PC, despachos, guías, facturas, NC, devoluciones), Compras (pedidos por comprar, órdenes de compra, cuentas por pagar), Inventario (consolidado, kardex, traslados, separaciones, conteos, resumen), Finanzas (cobrar, pagar, movimientos, resumen), Productos (stock de la empresa), Clientes y Proveedores (por ámbito).

### 12.4 Qué cambió en Supabase

Respaldo previo: copié las 12 tablas que iba a tocar al esquema `respaldo_20261015` con el nombre `<tabla>_pre007` (por ejemplo `respaldo_20261015.cotizaciones_pre007`, 29 filas). No se tocó nada de lo del 15/10 en la mañana (RLS, stock automático).

| # | Qué | Antes | Después | Cómo deshacer |
|---|---|---|---|---|
| 1 | Columna `empresa_id` (UUID) en `cotizaciones`, `pedido_compra_pc`, `despachos`, `guias_remision`, `comprobantes`, `notas_credito`, `devoluciones`, `finanzas_pagos`, `solicitudes_compra`, `clientes`, `proveedores`, `productos` | No existía (OC, recepciones y facturas de proveedor ya la tenían) | Creada, con índice `idx_<tabla>_empresa_id` | `ALTER TABLE public.<tabla> DROP COLUMN empresa_id;` |
| 2 | `erp_empresas`: `pagina_web`, `correo_rotulo`, `ubigeo` | No existían | KCF: web, correo de rótulo y ubigeo 150139; AGD: ubigeo 150105 (Breña) | `ALTER TABLE public.erp_empresas DROP COLUMN ...;` |
| 3 | Empresa de lo que ya existía | Sin empresa | **Todo a KCF**, porque todo apunta a KCF: PC, despachos y NC tenían "KCF" escrito; las 13 guías tienen el RUC de KCF; las 15 facturas son F001 de KCF. Las 3 OC y las 2 facturas de proveedor no tenían empresa → KCF. El cobro de caja toma la de su factura | Copiar desde `respaldo_20261015.<tabla>_pre007` (en el SQL) |
| 4 | Clientes | — | 1 cliente marcado "KCF" → KCF; los 42 "COMPARTIDO" quedan sin empresa (los ven las dos). Proveedores y productos: compartidos | — |

Registradas en Supabase como `007a_respaldo_pre_multiempresa` y `007b_multiempresa`.

**Borrado:** nada. No encontré duplicados, huérfanos ni datos de prueba que hiciera falta borrar para este pedido; ante la duda, no se borra.

### 12.5 Archivos cambiados

Nuevos: `routes/multiempresa.py` (empresa activa, filtros, colores, datos de empresa para PDF y rótulos), `static/css/tema_empresa.css` (colores por empresa), `migrations/007_multiempresa.sql`, `tests/test_multiempresa.py`.
Cambiados: `main.py`, `pdf_generator.py`, `routes/ventas.py`, `routes/compras_flujo.py`, `routes/finanzas.py`, `routes/inventario.py`, `routes/productos.py`, `routes/maestros.py`, `static/js/ventas.js`, `static/js/inventario.js`, `static/css/ventas.css`, `templates/base.html`, `templates/inventario/index.html`, `templates/nuevo_producto.html`, `tests/test_requerimientos_excel.py`.

### 12.6 Lo que necesito de ti

1. **Logos:** no hay archivos de logo de AGD (y el de KCF solo existe en un tamaño). Mándame `logo_kcf.png` y `logo_agd.png`, o súbelos tú a `static/img/` con esos nombres. Mientras tanto el rótulo y los PDF de AGD muestran "AGD" en su color.
2. **Ubigeo de KCF:** el sistema usaba `150139` para la dirección de San Martín de Porres. Revisa con tu contador si es el correcto (SMP podría ser `150135`). Se cambia en Configuración ▸ Empresas o te lo cambio yo.
3. **Página web y correo de rótulo de AGD:** están vacíos (sale el correo de documentos). Llénalos en Configuración ▸ Empresas si quieres que salgan.
4. **Asesora en la cotización:** la firma "Hellen Blas Príncipe" está fija para las dos empresas (no la cambié). Dime si AGD lleva otra persona.
5. Subir este ZIP a Render y, como siempre, **cambiar la contraseña de la base y la anon key**.

## 13. Corrección de 13 errores en producción + usuarios de Supabase (16/10/2026)

Pedido: tu mensaje "CORRECCIÓN DE 13 BUGS EN PRODUCCIÓN".
Lo aplicado en Supabase está en **`SUPABASE_008_CORRECCION_13_ERRORES.sql`** (y en el ZIP en `migrations/008_correccion_13_errores.sql`), con **cómo deshacer** al final.

### 13.1 Confirmaciones

| | Qué | Cómo lo comprobé |
|---|---|---|
| ✅ | **Los 13 errores corregidos** | Detalle de cada uno en 13.2. Prueba automática y captura para cada uno |
| ✅ | **Datos reales intactos** | En Supabase, antes y después: 34 cotizaciones, 45 clientes, 44 proveedores, 26 productos, 17 PC, 19 despachos, 16 guías, 21 facturas, 2 NC, 4 OC, 14 filas de stock, 21 movimientos de kardex, 245 permisos. Usuarios: 6 → 7 (el de Armando). **No se borró nada** |
| ✅ | **Stock igual en los 3 módulos** | `productos.stock` = suma de `inv_stock` en los 26 productos (0 descuadres; total 197 = 197). Ahora lo mantiene la propia base con dos disparadores, aunque alguien escriba el número a mano |
| ✅ | **Usuarios y permisos funcionando** | Las casillas se guardan por empresa y se ven igual al reabrir (10 pruebas nuevas). Usuario de Armando creado, inactivo, con contraseña entregada en el hilo |
| ✅ | **ZIP arranca en Render** | Lo descomprimí en una carpeta limpia y lo arranqué con `gunicorn main:app`: abre el login sin errores |
| ✅ | **Pruebas** | **110 de 110** pasan con la estructura real de tu Supabase (108 + 2 que no aplican con la otra estructura). Antes eran 87; se agregaron 23 de este pedido |

### 13.2 Los 13 errores: causa y arreglo

| # | Error | Por qué pasaba | Qué cambié |
|---|---|---|---|
| 1 | Stock con decimales (15.0000) | `inv_stock` guarda 4 decimales y la pantalla lo mostraba tal cual | El stock sale como número entero cuando no tiene decimales (15), en Productos, Ventas e Inventario. No se cambió el tipo de la columna para no tocar lo del 15/10 |
| 2 | Al editar una PC no se guardan la fecha ni la condición | Al guardar se mandaba siempre la fecha de hoy, y el campo fecha se llenaba en un formato que el navegador no entiende (salía vacío). La condición "Credito 30 Dias" no coincidía con la opción "Crédito 30 días" | Se guarda la fecha que escribes. La condición se reconoce sin importar tildes ni mayúsculas, y si no está en la lista va a "Personalizado" |
| 3 | Editar una PC pide "seleccionar cotización" | Al abrir la ventana se borraba el modo "editar" y quedaba como PC nueva (incluso creaba otra PC) | Editar abre la misma PC con todo cargado y guarda sobre la misma fila |
| 4 | "Validación de productos" falla aunque haya stock | El stock se leía de la columna **Valor total** en vez de **Stock** (por eso había PC guardadas con stock 20000), y el interruptor de margen nunca se enviaba, así que **todas** las PC quedaban "PC observado" / "Bloqueado" | Se lee la columna correcta y con el stock vivo del producto; el margen se valida bien. Las PC antiguas siguen como estaban: al volver a guardarlas se corrigen |
| 5 | "No hay productos" aunque los haya | Solo se revisaba la primera fila | Se revisan todas las filas; una fila sirve si tiene código o descripción |
| 6 | Despacho desde Cotizaciones no jala PC, guía ni factura | Ver 13.4 | Desde Cotizaciones ahora busca la PC de esa cotización y abre el mismo despacho que desde PC. Si no hay PC, te lleva a crearla |
| 7 | Consulta RUC: error 402 | El servicio gratuito apis.net.pe v1 ahora pide pago (402) | Primero busca el RUC en tus clientes y proveedores. Si no está, consulta afuera; si el servicio pide pago, sale un mensaje claro para escribir los datos a mano. Si contratas un token (decolecta / apis.net.pe), se pone en Render como `DECOLECTA_TOKEN` y funciona solo |
| 8 | Stock distinto en Productos, Inventario y Ventas | Productos mostraba `productos.stock` (copia manual), Inventario `inv_stock` por empresa y Ventas solo la empresa elegida (todo el stock real es de KCF, por eso en AGD salía 0) | Ver 13.3. Una sola fuente (`inv_stock`) y la base mantiene `productos.stock` como su suma |
| 9 | Tipo de operación no se guarda | No existía la columna | Columna `productos.tipo_operacion` (Venta / Compra / Inventariable) |
| 10 | Marca/categoría escrita a mano no se guarda | Solo se aceptaban las de la lista | Las nuevas se agregan solas a Marcas y Categorías (código MAR-/CAT-) |
| 11 | Al editar un producto no sale la tarjeta de stock inicial | Solo salía al crear | Sale también al editar si el producto no tiene stock ni movimientos pendientes |
| 12 | El Kardex muestra hora UTC (5 h adelantada) | La base y Render trabajaban en UTC | La base trabaja en hora de Lima, el ERP también (`TZ=America/Lima`) y las horas ya guardadas se pasaron a hora de Lima (-5 h). Como el cambio es en la base y en el servidor, vale para todos los módulos (probado en Kardex) |
| 13 | Casillas de permisos no se guardan bien | Una parte se guardaba solo en el navegador (localStorage) y no en la base; al guardar se reemplazaba todo y al reabrir no se veía lo guardado | Se guardan en la base por usuario y por empresa (KCF/AGD), cada columna por separado; al reabrir se ve lo guardado. El menú usa esos permisos |

### 13.3 Diagrama del stock (BUG 8)

```
                       PRODUCTOS (catálogo, uno para todo el grupo)
                                   │
                                   ▼
   inv_stock  ◄── ÚNICA FUENTE DE VERDAD: una fila por EMPRESA + SEDE + PRODUCTO
   ┌─────────┬──────────────────────┬──────────┬──────────┐
   │ Empresa │ Sede                 │ Producto │ Cantidad │
   ├─────────┼──────────────────────┼──────────┼──────────┤
   │ KCF     │ San Martín de Porres │ Casco    │    60    │
   │ AGD     │ Breña                │ Casco    │    30    │
   └─────────┴──────────────────────┴──────────┴──────────┘
        ▲                                │
        │ cada entrada/salida            │ disparador en la base (automático)
   inv_movimientos (KARDEX)              ▼
   compra, despacho, traslado,     productos.stock = 90  (suma de todas las filas)
   ajuste, stock inicial

   Qué muestra cada pantalla:
   • Productos  → total del grupo (90) y el detalle "AGD 30 · KCF 60"
   • Inventario → por empresa y por sede (KCF·SMP 60 | AGD·Breña 30 | total 90)
   • Ventas     → el stock de la empresa elegida arriba (KCF 60 / AGD 30 / Todas 90)
```

Regla de oro: el stock solo cambia con un movimiento del kardex. Si alguien escribe `productos.stock` a mano en un producto que ya está en Inventario, la base lo devuelve a la suma.

### 13.4 Flujo del despacho (BUG 6)

```
Cotización ──► PC del cliente ──► Despacho ──► Guía de remisión ──► Factura
 (precios)     (lo que el cliente   (qué sale,     (lleva la         (se crea
               confirma: cantida-   de dónde,      mercadería)       desde la guía)
               des, entrega)        a quién)
```

**Por qué funcionaba desde PC y no desde Cotización:** el despacho se arma con los datos de la **PC** (número, cliente, dirección, productos y cantidades). Desde PC el botón le pasaba todo eso. Desde Cotizaciones el botón abría un despacho **vacío**, sin PC ni productos, y al guardarlo quedaba suelto: por eso después no podía jalar la guía ni la factura. Además, guardar un despacho existente creaba otro nuevo.

**Ahora:** desde Cotizaciones el ERP busca la PC de esa cotización y abre exactamente el mismo despacho que desde PC. Si la cotización todavía no tiene PC, avisa y te lleva a crearla con la cotización ya elegida. Por seguridad, el servidor también completa el despacho con la PC y sus productos si llegaran vacíos, y editar un despacho guarda sobre el mismo. El número de despacho es correlativo por día: `DESP-AAAAMMDD-0001`.

### 13.5 Cuentas de acceso de Supabase (auth.users) y usuarios del ERP

| Cuenta de acceso | Usuario del ERP | Estado | Nota |
|---|---|---|---|
| admin@kcf.com | admin (administrador) | activo | enlazada |
| erika@kcf.com | eri01kcf (administrador) | activo | enlazada |
| hellen@kcf.com | hel02kcf (administrador) | activo | enlazada |
| estrella@kcf.com | est01kcf (usuario) | activo | enlazada |
| luis@kcf.com | luis01kcf | activo | enlazada, pero **sin contraseña del ERP**: no puede entrar hasta que le pongas una |
| despacho@kcf.com | desp01kcf | activo | enlazada, **sin contraseña del ERP** (igual que Luis) |
| armando@kcf.com | **arm01kcf (vendedor) – NUEVO** | **inactivo** | creado hoy; contraseña temporal entregada en el hilo (no va en este informe). Se activa en Configuración ▸ Usuarios |
| eri01kcf@kcf.com | — | — | **¿duplicada?** No creé usuario. Tiene 70 permisos guardados |
| est01kcf@kcf.com | — | — | **¿duplicada?** No creé usuario. Tiene 36 permisos |
| hel02kcf | — | — | **¿duplicada?** No creé usuario. Tiene 36 permisos |

- Para los próximos: Configuración ▸ Usuarios ▸ **"Cuentas de acceso sin usuario del ERP"** ▸ Crear. Queda inactivo, rol vendedor, y la contraseña se muestra **una sola vez** (o escribes tú la que quieras).
- **Aviso de seguridad:** el usuario `eri01kcf` tiene su contraseña del ERP guardada **en texto normal** (sin cifrar). Funciona, pero conviene cambiarla desde Configuración ▸ Usuarios para que quede cifrada. No la toqué.
- Los permisos de `eri01kcf` están guardados en la cuenta duplicada `eri01kcf@kcf.com`, no en `erika@kcf.com`. Como eres administradora igual lo ves todo; si confirmas cuál es la real, los paso.
- Importante: las casillas de permisos controlan **qué ve cada uno en el menú**. Lo que el servidor bloquea de verdad sigue dependiendo del **rol** del usuario (administrador, vendedor, etc.).

### 13.6 Qué cambió en Supabase

Respaldo previo: **46 tablas** copiadas a `respaldo_20261015.<tabla>_pre008` (todas las que tienen fechas-hora que se movieron, más `erp_usuario_permisos` y `erp_rol_permisos`). No se tocó nada de lo del 15/10.

| # | Qué | Cómo deshacer |
|---|---|---|
| 1 | Columnas `pedido_compra_pc.valida_productos` y `productos.tipo_operacion` | `DROP COLUMN` (en el SQL) |
| 2 | Funciones `fn_recalcular_stock_producto`, `fn_inv_stock_sync_productos`, `fn_productos_stock_desde_inventario` y sus 2 disparadores. Sincronización: ya estaba cuadrado, 0 productos cambiados | `DROP TRIGGER` / `DROP FUNCTION` (en el SQL) |
| 3 | La base trabaja en hora de Lima (`ALTER ROLE postgres SET timezone`) | `ALTER ROLE postgres RESET timezone;` |
| 4 | Fechas-hora ya guardadas pasadas de UTC a Lima (-5 h) en 44 tablas: columnas de creación/modificación y todas las de inventario. Las fechas sin hora no se tocaron. Solo se puede hacer una vez (marca `respaldo_20261015.marca_hora_lima_008`) | Sumar 5 h (bloque en el SQL) |
| 5 | Usuario `arm01kcf` (id 46) para armando@kcf.com, inactivo, vendedor | `DELETE FROM usuarios WHERE usuario_sistema='arm01kcf';` |

Registradas en Supabase como `008a_respaldo_pre008` y `008b_stock_hora_lima_columnas`.

**Borrado:** nada. No hacía falta borrar nada para corregir estos errores, y ante la duda no se borra (las 3 cuentas que parecen duplicadas esperan tu respuesta).

**Ojo con la hora mientras subes el ZIP:** hasta que subas el ZIP nuevo, el ERP viejo de Render puede guardar alguna hora en UTC. Lo que se registre entre ahora y la subida podría verse 5 h adelantado; dime si pasa y lo corrijo.

### 13.7 Archivos cambiados

Nuevos: `routes/consulta_ruc.py` (consulta de RUC local + externa con mensaje claro), `migrations/008_correccion_13_errores.sql`, `tests/test_ventas_bugs_16oct.py`, `tests/test_productos_bugs.py`, `tests/test_permisos_usuarios.py`.
Cambiados: `main.py` (hora de Lima, consulta RUC), `database.py` (hora de Lima en cada conexión), `render.yaml` (`TZ` y `DECOLECTA_TOKEN` opcional), `routes/ventas.py` (PC, despacho), `routes/inventario.py` (sincronización de stock), `routes/productos.py` (tipo de operación, marcas/categorías, stock inicial, stock total), `routes/multiempresa.py`, `routes/compras.py` (RUC), `routes/configuracion_seguridad.py` (permisos, cuentas de acceso), `static/js/ventas.js`, `templates/base.html` (permisos), `templates/base_datos_producto.html` (columna Stock), `templates/nuevo_producto.html`.

### 13.8 Lo que necesito de ti

1. **Sube este ZIP a Render.** En Render agrega la variable `TZ` = `America/Lima` (ya va en `render.yaml`, pero si el servicio se creó a mano hay que ponerla en Environment).
2. **Las 3 cuentas que parecen duplicadas** (`eri01kcf@kcf.com`, `est01kcf@kcf.com`, `hel02kcf`): ¿son de prueba o de alguien? Si son duplicadas, paso sus permisos a la cuenta real y las dejo sin uso.
3. **Consulta RUC automática:** ¿quieres contratar un token (decolecta o apis.net.pe)? Sin token, el ERP busca en tus clientes/proveedores y si no está pide escribir los datos.
4. **Luis y Despacho** no tienen contraseña del ERP: pónsela en Configuración ▸ Usuarios si deben entrar.
5. **Activa a Armando** cuando corresponda y cambia su contraseña temporal en su primer ingreso.
6. Sigue pendiente: cambiar la contraseña de la base y la anon key; logos `logo_kcf.png` / `logo_agd.png`; ubigeo de KCF.

---

## 14. Compras (7 errores) + Ventas (4) + 3 módulos finales + mejoras globales (16/10/2026, noche)

Pedido: tu mensaje "CORRECCIÓN DE MÓDULO COMPRAS + 3 MÓDULOS FINALES + MEJORAS GLOBALES", más tu audio.
Lo aplicado en Supabase está en **`SUPABASE_009_COMPRAS_MODULOS_FINALES.sql`** (y en el ZIP en `migrations/009_compras_reportes_auditoria.sql`), con **cómo deshacer** al final.
Las capturas están en `capturas-17oct/` y se tomaron con datos inventados en una copia local, nunca en tu base real.

### 14.1 Confirmaciones

| | Qué | Cómo lo comprobé |
|---|---|---|
| ✅ | **7 errores de Compras corregidos** | Detalle en 14.2. 10 pruebas automáticas nuevas y revisión en el navegador de los 7 |
| ✅ | **4 puntos de Ventas** | V1 "Valor Total", V2 hora de Lima, V3 Pendiente/Entregado, V4 descuento heredado por la PC (detalle en 14.3). 5 pruebas nuevas |
| ✅ | **Tachito 🗑️ en vez de X** | En las filas que se borran: productos de cotización y guía, comparativo de costos, cuentas bancarias, líneas de OC, recepción, papelera. Las X de **cerrar ventana** y **limpiar filtro** se dejaron como X, porque no borran nada |
| ✅ | **Fecha y hora de Lima en todo** | El servidor ahora manda las fechas ya en hora de Lima (antes salían en "GMT" y el navegador les restaba 5 horas). Todas las pantallas usan la misma función: `DD/MM/AAAA HH:MM`. También se corrigió que, después de las 7 p. m., la fecha por defecto saliera con el día siguiente |
| ✅ | **3 módulos terminados** | 8 Reportes, 9 Herramientas y 10 Papelera/Auditoría ya funcionan (antes decían "en construcción"). Diagramas en 14.4 |
| ✅ | **Datos reales intactos** | En Supabase, antes y después: 36 cotizaciones, 45 clientes, 46 proveedores, 26 productos, 18 PC, 20 despachos, 17 guías, 21 facturas, 2 NC, 5 OC, 14 filas de stock, 25 movimientos, 245 permisos, 7 usuarios. Stock cuadrado (0 diferencias). **No se borró nada** |
| ✅ | **ZIP arranca en Render** | Lo descomprimí en una carpeta limpia y lo arranqué con `gunicorn main:app` sobre una base con la estructura real: login, Ventas, Compras, Reportes, Herramientas, Papelera, Inventario y Finanzas abren sin errores |
| ✅ | **Pruebas** | **153 de 153** pasan con la estructura real de tu Supabase (antes 110; 43 nuevas de este pedido) |

### 14.2 Compras: los 7 errores

| # | Error | Por qué pasaba | Qué cambié |
|---|---|---|---|
| 1 | Los filtros de "Pantallas anteriores" no actualizan la tabla | Las cajas de búsqueda, estado y fecha no estaban conectadas a nada | Se conectaron; la tabla se filtra al escribir o elegir |
| 2 | "+ Nueva solicitud" abre la última ventana | No se limpiaba el formulario y quedaba guardado el número de la anterior | Siempre abre vacía |
| 3 | La lupa borra "Unidad" | La unidad del producto (ej. PAR) no estaba en la lista y quedaba en blanco | Si no está, se agrega sola; la lupa también busca por nombre |
| 4 | La X del filtro de fecha no limpia | El botón llamaba a funciones que no existían | Se crearon; la X limpia la fecha |
| 5 | No hay acceso directo a la OC | No había enlace, y "Crear orden" solo mostraba una orden de mentira | Barra con "Órdenes de compra", "+ Nueva orden" y "Solo compras sin pedido". También está en el menú. En Ventas, "Generar compra" ahora lleva a Compras → Pedidos por comprar |
| 6 | La OC no llena los datos del proveedor | Teléfono y contacto están en otra tabla (`proveedores_contactos`) que nadie leía | Al elegir el proveedor se llenan razón social, RUC, dirección fiscal, contacto, teléfono y correo |
| 7 | "+ Nueva orden" trae la OC anterior | Solo se limpiaban fecha y número, y una función repetida rompía los totales | Siempre abre vacía; se quitó la función repetida |

**Además (tu audio):**
- **Tabla resumen al comprar:**
  - Columnas: Pedido del cliente | Ya en órdenes | En stock de la empresa | Comprar para pedido | Comprar para stock | Total a comprar | Saldo después de entregar.
  - "Comprar para stock" empieza en 0. Si pones más, va en una línea aparte y pide motivo.
  - Ejemplo: 40 pedidos y 10 en stock → comprar 30. Si además compras 100 para stock, el total es 130 y el saldo después de entregar es 100.
- **Compra sin pedido:** motivo obligatorio de una lista: Stock estratégico, Crédito fiscal / IGV, Reposición de stock mínimo u Otro (con texto). Se marca "SIN PEDIDO" en la lista.
- **OC enlazada:** la OC guarda la PC, la cotización, el cliente y el motivo. Se ven en un bloque **"Solo interno"**. **La hoja que se manda al proveedor nunca muestra el cliente, la PC ni la cotización** (hay una prueba que lo revisa).
- **Candados:**
  - Anular o eliminar OC, solicitudes y facturas de proveedor: **solo administrador**, con **motivo obligatorio**. El servidor lo bloquea aunque alguien intente saltarse la pantalla.
  - Cada anulación guarda quién, cuándo, por qué y una copia del documento (tabla `com_anulaciones`).
  - Una factura de proveedor ya no se borra: queda "Anulado".
- **Cuentas por pagar ordenadas:**
  - Orden: primero las **vencidas** (la más atrasada arriba), luego **por vencer** (la más próxima arriba) y al final **al día**.
  - Arriba van los totales en rojo, ámbar y verde, y cada fila dice "VENCIDO · N días de atraso" o "POR VENCER · faltan N días".

### 14.3 Ventas

| # | Pedido | Qué cambié |
|---|---|---|
| V1 | "Valor Total" con T mayúscula | Corregido en la cotización |
| V2 | Horas en hora de Lima | Ver ✅ de fecha y hora arriba. Vale para todos los módulos |
| V3 | "Inmediato en entrega": solo Pendiente / Entregado | Las capturas que mandaste no me llegaron, así que lo interpreté así: la columna **Entrega** de cada producto de la cotización ahora es una lista con solo **Pendiente** (ámbar) o **Entregado** (verde fluorescente), y se guarda en la base (`cotizacion_detalle.estado_entrega`). Las líneas antiguas quedan en Pendiente. El campo "Tiempo de entrega" de la cabecera no se tocó. Si te referías a otro campo, dime cuál y lo cambio |
| V4 | **El descuento se pierde al pasar a PC** (crítico) | El descuento sí se guardaba en la cotización. Lo que fallaba era que la PC tomaba los precios **sin** descuento. Ejemplo real: COT-000042 tenía S/ 5,000 de descuento y su PC 59 salió por S/ 21,280. Ahora la PC, la guía y la factura reciben los **precios con descuento** y el **total con descuento**, sea en % o en soles, y avisan "descuento de S/ X ya aplicado". Al reabrir la cotización para editarla, el descuento no se aplica dos veces |

Para PC ya creadas antes de este arreglo (como la 59): al abrirlas y volver a guardarlas desde la cotización se recalculan. No se cambió ninguna PC existente sin tu permiso.

### 14.4 Diagramas de los 3 módulos nuevos

**8 · Reportes** (solo lectura, no cambia nada en la base)

```
  Elige: empresa (KCF / AGD / Todas) · fechas · cliente / proveedor / vendedor
                                │
     ┌──────────┬──────────┬────┴─────┬──────────┬──────────┬───────────────┐
     ▼          ▼          ▼          ▼          ▼          ▼               ▼
  TABLERO    VENTAS     COMPRAS   INVENTARIO  POR COBRAR  POR PAGAR   COLABORADORES
  ventas del por mes,   por        stock,      vencido /   vencido /   quién vende más,
  mes, top   utilidad,  proveedor  kardex      por vencer  por vencer  cuánto y en
  clientes,  más        y por      valorizado, / al día    / al día    cuántos días
  por cobrar vendidos,  producto   rotación,                           (solo usuarios
  y pagar    mejores               inmovili-                            reales del ERP)
             clientes,             zado
             DEJARON DE
             COMPRAR
                                │
                    Exportar: Excel · CSV · PDF
  Quién ve: montos → administración y finanzas · Colaboradores → solo administrador
```

**9 · Herramientas** (solo administrador; cada uso queda en Auditoría)

```
  IMPORTAR (productos / clientes / proveedores)
     plantilla Excel → subir → VISTA PREVIA (nuevo · se actualiza · ya existe · error)
     → confirmar → se guarda todo junto o nada. Nunca borra. El stock va por Inventario.
  EXPORTAR        cualquier tabla de negocio a Excel/CSV (sin contraseñas)
  NUMERACIONES    detecta huecos y repetidos en COT, PC, guías, facturas, NC, OC
                  → SOLO AVISA. Nunca renumera documentos emitidos.
  INTEGRIDAD      21 revisiones: huérfanos, duplicados, stock descuadrado → solo avisa
  RECALCULAR STOCK  vuelve a sumar inv_stock → productos.stock (muestra antes/después)
  CACHÉ · LOGS · CONEXIÓN   limpiar memoria, ver errores, estado de la base (sin mostrar claves)
```

**10 · Papelera / Auditoría**

```
  Cualquier cambio en 17 tablas (cotizaciones, PC, despachos, guías, facturas, NC, devoluciones,
  OC, solicitudes, facturas de proveedor, productos, clientes, proveedores, kardex, usuarios,
  permisos, cobros/pagos)
        │  disparador en la base (automático, aunque el cambio no venga del ERP)
        ▼
  erp_auditoria:  fecha y hora Lima · usuario · módulo · acción · ANTES · DESPUÉS
        │         (crear / editar / anular / aprobar / rechazar / eliminar / restaurar / login)
        │         Las contraseñas nunca se guardan.
        ▼
  PAPELERA (la ven todos, filtrada por empresa)
     todo lo anulado, eliminado, desactivado y borrado
        ├── RESTAURAR (solo administrador): cotización → Borrador, PC → Pendiente,
        │       OC/solicitud → Borrador, cliente/proveedor/producto → activo
        │       Guías, facturas, NC, cobros y kardex anulados: SOLO SE VEN (SUNAT / no cobrar dos veces)
        └── BORRAR DEFINITIVO (solo administrador): doble confirmación + escribir BORRAR y el número.
                Se niega si el documento tiene otros que dependen de él. Antes guarda copia en Auditoría.
  AUDITORÍA (solo administrador): filtros por usuario, módulo, acción y fechas · ver antes/después · Excel
```

### 14.5 Mejoras globales

- **Tachito 🗑️:** ver ✅ arriba.
- **Fecha y hora:** el servidor manda la hora de Lima a todas las pantallas. Cotizaciones, PC, guías, facturas, compras, CxP, maestros, productos, kardex, papelera y auditoría muestran `DD/MM/AAAA HH:MM`.
- **Letra por empresa:** KCF usa **Montserrat** (rojo) y AGD **Roboto Slab** (naranja), para que no se confundan.
- **Colores semáforo fuertes** en todo el sistema: verde fluorescente para OK, ámbar para atención y rojo intenso para vencido o peligro.
- **Kardex:** la última fila de cada producto dice **SALDO FINAL**, con fondo verde y el número grande en azul eléctrico.

### 14.6 Cambios en tu Supabase (009)

Antes de tocar nada saqué un respaldo en `respaldo_20261015`: `ordenes_compra_pre009`, `ordenes_compra_items_pre009`, `cotizacion_detalle_pre009` y `erp_auditoria_pre009`. Todo lo del 009 **solo agrega**:

| Tabla | Qué se agregó | Para qué |
|---|---|---|
| `cotizacion_detalle` | `estado_entrega` (Pendiente por defecto) | V3 |
| `ordenes_compra` | `pedido_id`, `pc_numeros`, `cotizaciones_cliente`, `clientes_pedido`, `motivo_compra` | OC enlazada a PC/cotización/cliente y motivo sin pedido |
| `ordenes_compra_items` | `cotizacion_numero` | Igual, por línea |
| `com_anulaciones` (nueva, con RLS) | quién, cuándo, motivo y copia | Candados de Compras |
| `erp_auditoria` | `usuario_id`, `usuario_nombre`, `modulo`, `empresa`, `ip`, `detalle` + 3 índices | Auditoría |
| función `fn_erp_auditoria` + 17 disparadores `trg_erp_auditoria` | — | Auditoría automática |

- Probé el disparador en tu base dentro de una transacción que luego se deshizo: registró "editar · Maestros · Clientes" con el usuario, y no quedó nada guardado.
- **Pendiente para ti (opcional):** borrar 3 índices repetidos de `ordenes_compra`. Desde aquí la orden se cuelga, como pasó el 15/10. Está al final del SQL para pegarla en el SQL Editor, junto con cómo deshacerla.

### 14.7 Archivos

- **Nuevos:**
  - `routes/json_lima.py`: fechas en hora de Lima.
  - `routes/auditoria.py`.
  - `static/js/herramientas.js`, `static/js/papelera.js`, `static/js/reportes.js`.
  - `static/css/herramientas.css`, `static/css/reportes.css`.
  - `migrations/009_compras_reportes_auditoria.sql`.
  - 4 archivos de pruebas `tests/test_zz_*.py`.
- **Reescritos:** `routes/reportes.py`, `routes/herramientas.py`, `routes/papelera.py`, y sus pantallas `templates/reportes.html`, `herramientas.html`, `papelera.html`.
- **Cambiados:**
  - `main.py`: fechas, y login/logout en la auditoría.
  - `database.py`: el usuario que hace el cambio llega a la auditoría.
  - `routes/ventas.py`, `routes/compras.py`, `routes/compras_flujo.py`, `routes/finanzas.py`, `routes/multiempresa.py`.
  - `static/js/ventas.js`, `compras.js`, `compras_flujo.js`, `finanzas.js`, `inventario.js`, `maestros.js`.
  - Sus hojas de estilo, `tema_empresa.css`, `base.html` (menú, letras y fecha), y las ventanas de Compras.

### 14.8 Decisiones que tomé (dime si quieres otra cosa)

- **Quién ve Reportes:** administración y finanzas ven montos, y Colaboradores lo ve solo el administrador. **Hellen (aprobadora) hoy no entra a Reportes.** ¿Quieres que lo vea?
- **Anular en el flujo nuevo de Compras:** administrador o supervisor (Hellen). Las pantallas anteriores: solo administrador.
- **Papelera:** la ven todos (es solo mirar). Restaurar, borrar definitivo y la pestaña Auditoría: solo administrador.
- **Stock en la tabla de compras:** si dos PC piden el mismo producto, cada una ve el stock completo de la empresa (no se reparte entre pedidos).
- **Documentos antiguos sin empresa:** salen en las dos empresas en Reportes.
- **Usuario en la auditoría:** el usuario de la sesión llega a la base solo durante esa operación. Tu Supabase usa el "pooler" compartido, así que nunca queda pegado a otra persona.

---

## 15. Panel de abastecimiento en la OC, colores de Compras y columnas de Guías y Facturas (19/10/2026)

Pedido: tu mensaje "MEJORAS DE INTERFAZ, LÓGICA DE COMPRAS Y TABLAS EN VENTAS".
**No hizo falta tocar tu Supabase.** Todo se calcula con las tablas que ya existen (`inv_stock`, `pedido_compra_pc`, `ordenes_compra`, `guias_remision`, `comprobantes`), así que no hay SQL nuevo. Las capturas están en `capturas-19oct/` y se tomaron con datos inventados en una copia local.

### 15.1 Confirmaciones

| | Qué | Cómo lo comprobé |
|---|---|---|
| ✅ | **Panel Stock / Pedido / A comprar en el formulario de OC** | 3 pruebas automáticas y capturas: con stock 10 y pedido 40 sugiere 30, descuenta lo que ya está en otras OC y se recalcula al cambiar la cantidad |
| ✅ | **Paso 2 en amarillo fuerte** | Paso actual del seguimiento de la OC y etiqueta "Por aprobar" en `#FFD600` |
| ✅ | **"Aprobada" en verde fuerte** | En la lista nueva y en las pantallas anteriores (`#00C853`) |
| ✅ | **Guías: "Nr° PC" después de Cotización y "Comprobante" → "Nr° factura"** | Prueba automática y captura |
| ✅ | **Facturas: "Documento" → "Nr° factura", más "Nr° PC" y "Nr° guía" después de Cotización** | Prueba automática y captura |
| ✅ | **Datos reales intactos** | No se escribió nada en tu base. Solo probé las consultas de lectura: 16 de 17 guías y 17 de 21 facturas ya muestran su PC (las que faltan no tienen PC registrada para su cotización) |
| ✅ | **ZIP arranca en Render** | Lo arranqué con `gunicorn main:app` en una carpeta limpia. Ventas, Compras, Reportes y Papelera abren sin errores |
| ✅ | **Pruebas** | **158 de 158** pasan con la estructura real de tu Supabase (5 nuevas) |

### 15.2 Panel "Resumen de abastecimiento" (MEJORA 1)

**Dónde:** Compras ▸ Nueva orden de compra ▸ bloque 3 "Productos", debajo de la lista. Sale siempre: al crear la OC desde "Pedidos por comprar", con "+ Nueva orden" y al corregir una OC.

**Qué muestra:** una fila por producto, para la empresa que compra:

| Columna | De dónde sale |
|---|---|
| **Stock actual** | Lo disponible en `inv_stock` de esa empresa (todas sus sedes), menos lo separado para clientes. Si en otra empresa o sede del grupo hay más, lo avisa ("Grupo: 37") |
| **Pedido del cliente** | Lo que falta cubrir de todas las PC abiertas de esa empresa: lo pedido menos lo que ya está en otras OC. Dice cuántos pedidos son y cuánto ya se pidió en otras OC |
| **Sugerido** | Pedido del cliente − stock actual. Con el botón **Usar**, esa cantidad pasa a la línea |
| **A comprar** | Lo que estás poniendo en esta orden (suma de las líneas de ese producto) |
| **Resultado** | 🟢 "Cubre el pedido" (y cuánto queda en stock) · 🔴 "Faltan N" · 🟡 "Para stock, quedarán N" |

Se recalcula al elegir un producto, al cambiar una cantidad y al cambiar la empresa. Al corregir una OC no se descuenta lo que ya trae esa misma orden.

La tabla de "Pedidos por comprar" que entregué el 16/10 sigue igual. Ahora la misma información también está dentro del formulario, que es donde la buscabas.

### 15.3 Colores (MEJORAS 2 y 3)

- **Paso 2:** en el detalle de la OC, el paso actual del seguimiento (cuando está "Por aprobar" es el 2, "Aprobada") y la etiqueta "Por aprobar" pasan de amarillo pálido a **amarillo fuerte** con letra oscura. También los avisos de "Siguiente paso" que piden acción.
- **Aprobada:** pasa de azul pálido (lista nueva) y verde pálido (pantallas anteriores) a **verde fuerte** con letra blanca.

### 15.4 Guías y Facturas (MEJORAS 4 y 5)

- **Guías:** … | Cotización | **Nr° PC** | **Nr° factura** | Origen | …
- **Facturas:** … | **Nr° factura** | RUC | Cliente | Cotización | **Nr° PC** | **Nr° guía** | Monto | …
- **De dónde salen los números:**
  - Primero se usa lo que se guardó al crear la factura (PC y guía vinculadas).
  - Si está vacío, la PC se busca por la misma cotización.
  - La guía se busca por la factura anotada en la guía o, si la cotización tiene **una sola** guía, esa. Si tiene varias, no se adivina y sale "-".
- **Búsqueda:** el buscador de cada tabla también encuentra por N° de PC y N° de guía.

### 15.5 Archivos cambiados

- `templates/compras/flujo.html`: el panel y la columna "A comprar al proveedor".
- `static/js/compras_flujo.js`: el panel, el botón "Usar" y el recálculo.
- `static/css/compras_flujo.css`: colores fuertes y estilos del panel.
- `templates/compras/index.html`: verde fuerte en las pantallas anteriores.
- `routes/compras_flujo.py`: nueva consulta `/compras/api/flujo/abastecimiento`.
- `routes/ventas.py`: Nr° PC y Nr° guía en las listas.
- `templates/ventas/index.html` y `static/js/ventas.js`: columnas y nombres.
- `tests/test_zz_zz_19oct.py`: 5 pruebas nuevas.

### 15.6 Notas

- **Tu Render parece seguir con un ZIP anterior al del 16/10 (noche).** En tu base no hay ningún registro de ingreso o salida en la Auditoría, y ese ZIP los anota. Es una deducción, no lo vi en Render. Con este ZIP nuevo tienes todo junto: lo del 16/10 y lo de hoy.
- **Encontré, sin arreglar:** el botón "📥 Exportar" de las tablas de Ventas solo muestra un aviso y no descarga nada. Si lo quieres, lo hago.

## 16. Crédito en la OC, proveedores con productos, Exportar, descuento en la PC + revisión integral (19/10/2026, tarde)

Pedido: "CORRECCIÓN DE BUGS EN COMPRAS, PROVEEDORES, PC Y EXPORTACIÓN + REVISIÓN INTEGRAL" (19/10 15:56) y el audio (fecha y hora en todo, nombres claros, vencimientos).

### 16.1 Los 4 errores

| # | Error | Estado | Cómo quedó |
|---|---|---|---|
| 1 | Compras ▸ OC: el crédito mostraba mal los días | ✅ Corregido | "Condición de pago" ahora es Contado / Contra entrega / Crédito. Solo con **Crédito** aparece el campo **"Número de días de crédito"** (obligatorio) y debajo se lee en verde **"Crédito a 30 días"**. Con Contado el campo se oculta y se vacía. Lo mismo en la ficha del proveedor y en las pantallas anteriores de Compras. En las listas se lee "Crédito a 30 días". |
| 2 | Proveedores ▸ Eliminar daba error de la base | ✅ Corregido | Antes de borrar, el ERP revisa si el proveedor se usa en alguna tabla. Si tiene productos sale el mensaje exacto: *"No se puede eliminar el proveedor porque tiene productos asociados. Primero reasigne los productos a otro proveedor."* y cuántos productos, OC, costos o facturas tiene. Ofrece el botón **"Desactivar proveedor"**: deja de salir en compras nuevas y se guarda todo su historial (queda en Papelera ▸ Proveedores desactivados, de donde se puede reactivar). Un proveedor sin uso se sigue borrando normal. |
| 3 | El botón Exportar no hacía nada | ✅ Corregido | Un solo exportador para todo el ERP: descarga **Excel (.xlsx)** de la tabla que se está viendo, **solo las filas que dejan los filtros y la búsqueda**, con los mismos nombres de columna de la pantalla. Arriba del Excel: título, "Descargado el DD/MM/AAAA a las HH:MM (hora de Lima) por (usuario) · Empresa", los filtros usados y el número de filas. El nombre del archivo lleva la fecha y hora (ej. `ventas_cotizaciones_2026-10-19_1145.xlsx`). Montos como número (se pueden sumar); RUC, DNI, códigos y Nr° como texto (no se pierden ceros). Las pantallas con pestañas que no tenían botón (Maestros, Inventario, Compras, Finanzas, Reportes, Papelera…) ahora tienen **"⬇ Exportar Excel"** junto a las pestañas. Cada descarga queda en la Auditoría. |
| 4 | El resumen de la PC no mostraba el descuento | ✅ Corregido | Resumen PC: **Subtotal (precio de lista)** → **Descuento (10%)** en rojo → **Valor venta (con descuento)** → IGV → **Total**. Debajo, una nota verde: "El precio de la PC ya viene con el descuento de la cotización COT-…". Si la PC tiene precios sin descuento pero la cotización sí tenía, la nota sale en naranja para revisar. Comprobado en tu base: COT-000044 (2%) → PC por S/ 1,293.60 = 1,320 − 2%. |

### 16.2 Lo del audio

- **Fecha y hora de creación y modificación:**
  - Ventas: cotizaciones, PC, despachos, guías, facturas, notas de crédito, devoluciones.
  - Compras: OC ("Modificada …").
  - Maestros: clientes y proveedores, columna "Creado / modificado".
  - Ficha de producto: "Creado el … · Última modificación …".
  - Todo en hora de Lima. La base ahora pone sola la "última modificación" al cambiar un registro (migración 010).
- **Nombres claros:**
  - Códigos: "Código de producto", "Código de cliente", "Código de proveedor".
  - Números de documento: "Nr° cotización", "Nr° PC (pedido de compra)", "Nr° orden de compra", "Nr° guía", "Nr° factura", "Nr° nota de crédito", "Nr° de documento (RUC / DNI)".
  - Se quitaron los "Comprobante" y "Documento" sueltos. Donde una columna mezcla tipos dice "Documento (tipo y Nr°)".
- **Vencimientos:**
  - **Ficha del producto:** nuevo campo "Fecha de vencimiento" (opcional; vacío = no vence).
  - **Inventario ▸ ⏳ Vencimientos:** semáforo por lote, usando la fecha del lote si se registró al ingresar; si no, la de la ficha.
    - **Amarillo:** vence en 6 meses o menos.
    - **Rojo:** 3 meses o menos.
    - **Vencido:** ya venció.
  - La pantalla tiene filtro, buscador y exportar a Excel.
  - "Qué revisar hoy" avisa cuántos hay en cada color.

### 16.3 Revisión integral

| Revisión | Resultado |
|---|---|
| Pruebas automáticas (base igual a la tuya) | ✅ **170 de 170** |
| Pruebas automáticas (base reconstruida desde cero) | ✅ **168 de 168** (2 omitidas porque esa base no tiene esas tablas) |
| Pruebas nuevas de hoy | 12 (los 4 errores, vencimientos, fechas y la prueba de 2+ OC al mismo tiempo) |
| Recorrido de **20 pantallas y 50 pestañas** | ✅ Sin errores 500 ni errores de JavaScript |
| Botón Exportar en cada pestaña | ✅ Descarga Excel en todas las que tienen datos; si la tabla está vacía avisa "no hay nada para exportar" |
| Ver PDF / Imprimir / Rótulo (26 enlaces) | ✅ Todos responden. 3 se niegan **a propósito**: rótulo de una guía en BORRADOR e imprimir una OC sin aprobar |
| Stock: `productos.stock` = suma por sede | ✅ 0 diferencias en tu base |
| Descuentos guardados | ✅ Cotización → PC → guía → factura heredan el precio con descuento (PC desde el 16/10 noche; las antiguas conservan su precio) |
| Fechas en hora de Lima | ✅ La conexión del ERP usa America/Lima; un cambio de prueba en tu base (deshecho al instante) quedó con la hora de Lima correcta |
| Prueba de estrés: 4 OC creadas **al mismo tiempo** | ✅ 4 números distintos, ninguno repetido |
| Arranque del ZIP como en Render (`gunicorn main:app`, base vacía) | ✅ Arranca y responde |

**Errores extra encontrados y corregidos en la revisión:**
1. La lista de cotizaciones se caía (error 500) si una cotización tenía el total vacío. En tu base no hay ninguna así hoy, pero podía pasar. Ahora se lee como 0 (17 lugares en Ventas).
2. Los botones Exportar de Ventas, Compras y Productos solo mostraban un aviso o devolvían texto JSON. Ahora todos descargan Excel.
3. Productos exportaba solo la página que se veía (10 filas). Ahora exporta todas las filas filtradas.
4. Una OC o un costo podían quedar apuntando a un proveedor borrado (no había candado en la base). Ahora la base lo impide (migración 010) y el ERP ofrece desactivar.
5. Nombres de columna ambiguos ("N°", "Documento", "Comprobante", "Código"). Ver 16.2.
6. Excel: los RUC y los códigos ya no se convierten en número.

### 16.4 Supabase: migración 010 (aplicada hoy)

Archivo: `SUPABASE_010_PROVEEDORES_VENCIMIENTOS_FECHAS.sql` (también `migrations/010_...` en el ZIP). Solo **agrega**; no toca 005 a 009.
- **Respaldo previo** en `respaldo_20261015`: `proveedores_pre010` (49), `productos_pre010` (29), `ordenes_compra_pre010` (10), `costos_productos_pre010` (17).
- **Cambios:**
  - `productos.fecha_vencimiento` (fecha, vacía por defecto) e índices.
  - `proveedores.updated_at`. Los 49 proveedores quedan vacíos hasta su próxima modificación: no se inventó una fecha.
  - Disparador `trg_tocar_updated_at` en 9 tablas: clientes, proveedores, cotizaciones, pedido_compra_pc, despachos, comprobantes, notas_credito, solicitudes_compra, comprobantes_proveedor.
  - Candados `ON DELETE RESTRICT` de `ordenes_compra` y `costos_productos` hacia proveedores. Se revisó antes que hubiera 0 huérfanos, y se validaron.
- **Nada borrado.** Conteos iguales antes y después: 38 cotizaciones, 48 clientes, 49 proveedores, 29 productos, 20 PC, 21 despachos, 18 guías, 22 comprobantes, 2 NC, 10 OC, 18 stock, 33 movimientos, 7 usuarios, 17 costos.
- **Cómo deshacer:** está al final del archivo SQL ("CÓMO DESHACER"). Se quitan los candados y los disparadores, y se dejan las columnas (no estorban).

### 16.5 Archivos cambiados

- **Nuevos:**
  - `routes/exportar.py`
  - `static/js/exportar_tabla.js`
  - `migrations/010_proveedores_vencimientos_fechas.sql`
  - `tests/test_zz_zz_19oct_bugs.py`
- **Cambiados:**
  - `main.py` (registra el exportador).
  - `routes/maestros.py` (eliminar/desactivar proveedor).
  - `routes/ventas.py` (descuento para la PC, fechas, totales vacíos).
  - `routes/productos.py` y `routes/inventario.py` (vencimientos).
  - `routes/compras_flujo.py` (fecha de modificación de la OC).
  - `templates/base.html` (ayudas de crédito y fechas, menú Vencimientos).
  - Pantallas de Compras, Ventas, Inventario, Maestros, Productos, Finanzas y Papelera, con sus `.js` y `.css`.

### 16.6 Notas

- **Corrección a lo que dije en 15.6:** hoy tu Auditoría sí tiene registros nuevos (movimientos, productos, OC y PC desde las 10:26). Parece que tu Render ya tiene un ZIP reciente. Igual hay que subir **este** ZIP para ver lo de hoy.
- Después de subir el ZIP no hay que correr nada en Supabase: la 010 ya está aplicada.
- Las PC hechas antes del 16/10 (noche) tienen precio sin descuento. El resumen lo marca en naranja si la cotización tenía descuento.


## 17. Ayudas paso a paso, N° de PC, condición de pago, 2 decimales, contraseñas + auditoría integral (19/10/2026, noche)

Pedido de Erika del 19/10 19:53 (prompt de Adriel + audio), más dos capturas sueltas (Crear cliente y COT-000049).
Donde el prompt y el audio no coincidían, se siguió el audio.

### 17.1 Qué se hizo

| # | Pedido | Estado | Cómo quedó |
|---|---|---|---|
| 1 | Ayuda visual en Entregas | ✅ | Al despachar sale la ventana verde **"✅ ¡Guía creada con éxito!"** con "¿Qué hacer ahora?", **Paso 1: Ve al menú "Guías de Remisión"** y **Paso 2: Busca tu guía y haz clic en "Crear Factura"**. El botón azul **"Ir a Guías de Remisión"** abre la lista y deja la guía marcada en verde. "Crear Factura" sigue dentro de los 3 puntos ⋮ (así lo pidió el 15/10), y el paso lo dice. |
| 1b | Ayuda visual en Guías → Facturas | ✅ | Al guardar la factura sale **"✅ ¡Factura creada con éxito!"** con el N° y el botón **"Ir a Facturas"**, que abre la lista con la factura marcada en verde. |
| 2 | Decimales en Productos PC | ✅ | Precio cotizado y precio PC salen con 2 decimales (62.6087 → 62.61). |
| 2b | N° de PC | ✅ | Cada PC recibe un **N° PC interno automático por empresa** (PC-KCF-000001, PC-AGD-000001…), que no se repite aunque dos personas guarden a la vez. Hay un campo nuevo, **"N° OC del cliente (opcional)"** (ej. IT40… de Komatsu), que queda vacío si el cliente no emite OC. Se ve en la lista de PC debajo del N° y se copia a la factura. Las PC que ya existen conservan su número. |
| 2c | Condición de pago en la PC | ✅ | La condición de pago empieza en blanco ("— Elegir (leer OC) —") y es obligatoria. Ya **no se copia de la cotización**: debajo aparece "Cotizado: Crédito 30 días. Elige la de la OC del cliente". |
| 3 | Cotización: 4 campos obligatorios | ✅ | Sin **condición de pago, tiempo de entrega, transporte y parihuela** la cotización no se guarda ni se envía (lo revisan la pantalla y el servidor). "Solicitar validación" muestra **"Faltan campos obligatorios para enviar a validación"**. Si falta el resto de la información adicional (seguimiento, nota interna, dirección de entrega) solo sale el aviso amarillo **"Ojo: No has llenado la información adicional. ¿Seguro que deseas continuar?"**. Antes la condición venía marcada como "Personalizado" y el tiempo como "Personalizado": ahora empiezan en "-- Elegir --". |
| 3b | Condición de pago de la factura | ✅ | La factura toma la condición del **PC de origen**. Si no hay PC, la toma del PC de la guía, y si tampoco hay, de la ficha del cliente. **Nunca de la cotización.** Debajo se ve "✔ Tomada del PC …". |
| 3c | Observaciones de la factura | ✅ | Se guardan con la primera letra en mayúscula. |
| 4 | Contraseñas | ✅ | Ver `CONTRASENAS_USUARIOS.md` (solo en la carpeta del proyecto). Botón **"🔑 Nueva contraseña"** para el administrador en Configuración ▸ Usuarios. |
| 5 | Fila "Descuento" en Resumen PC | ✅ | El orden es el de su ejemplo: **Subtotal, Valor venta, Descuento, IGV 18%, Total**. Cuando no hay descuento sale **S/ 0.00**. Ejemplo de la demo: 270.00 / 243.00 / − 27.00 / 43.74 / **286.74**. |
| 6 | Auditoría integral | ✅ | Ver 17.4. |
| Audio | Máximo 2 decimales en todo | ✅ | Ver 17.3. |
| Captura | Crear cliente: "Crédito aprobado" con días "Contado" | ✅ | Si la condición es "Crédito aprobado", hay que elegir los días (7, 15, 30, 45, 60, 90, 120 o el lápiz para otro número) y "Contado" ya no aparece como día. Con "Contado" o "Bloqueado" los días se ocultan y quedan en 0. El servidor también lo exige. |
| Captura | Condición escrita distinta en cada pantalla | ✅ | Ahora se escribe igual en todo el sistema: **"Contado"**, **"Contra entrega"** o **"Crédito 30 días"**, sin "Credito 30 Dias" ni "Crédito a 30 días". |

### 17.2 Por qué una PC a 30 días terminaba en factura "al contado"

En su base (revisado el 19/10 sin tocar nada) pasan dos cosas:

1. **Al crear la factura desde la guía, la pantalla no ponía ninguna condición** y quedaba la primera opción, "Contado". Ejemplos reales de hoy:
   - **F001-88187491**: COT-000043, PC-20260720-495500 a **Crédito 90 días**, guía T001-G-20261019-7384, 09:39. Quedó **Contado**.
   - **F001-88187493**: COT-000045, PC-20261019-0001 a **Credito 45 Dias**, guía T001-G-20261019-2664, 12:47. Quedó **Contado**.
   - En las otras tres de hoy (F001-88187492, 94 y 95) la condición se eligió a mano y quedó bien.
2. **La lista de Facturas mostraba "Contado" en todas**, aunque la factura estuviera guardada a crédito (estaba escrito fijo en el programa). Por eso F001-88187494 y 95, guardadas a "Crédito 30 días", también se veían como contado.
3. Además, "Credito 30 Dias" (cotización y PC) no coincidía con "Crédito 30 días" (factura), y el programa no las reconocía como iguales.

Las tres causas están corregidas (17.1 #3b y 17.6).

**COT-000049** (EMP. DE TRANS. FLORES HNOS. SRL, Credito 30 Dias, Generada 15:12) todavía **no tiene PC, despacho, guía ni factura** en la base (se buscó por número y por id). Su condición quedó escrita como "Crédito 30 días". Cuando se haga su PC, la condición se elige leyendo la OC del cliente y la factura la tomará de esa PC.

**No se cambió ninguna factura ya hecha.** Las que tienen la condición equivocada (F001-88187491, F001-88187493 y las del informe anterior: 50, 48, 47, 42, 37, 28, 21 y 19) se pueden corregir si me dice cuáles.

### 17.3 Dos decimales

- **Cotización:** el precio unitario y los totales se calculan y se muestran con 2 decimales. El servidor también redondea el precio de cada línea a 2 decimales (62.6087 → 62.61).
- **PC:** precios, valor por línea y resumen con 2 decimales.
- **En todas las pantallas:** las casillas de dinero (paso 0.01) no aceptan más de 2 decimales, ni al mostrarse ni al escribir. Costo en Inventario, precio de factura del proveedor y precio de la OC pasaron de 4 decimales a 2.
- **Kardex:** el costo promedio se muestra con 2 decimales. Por dentro la base lo sigue guardando con más precisión para que el valor del inventario no se descuadre con el tiempo.
- **Nota:** al redondear cada precio a 2 decimales, el total puede diferir en algún céntimo del cálculo antiguo con 4 decimales. Lo que manda ahora es el precio de 2 decimales.
- En su base hay 6 líneas antiguas de cotización con más de 2 decimales en el precio con descuento. No se tocaron.

### 17.4 Resultados de Auditoría y Test Integral

| Revisión | Resultado |
|---|---|
| Pruebas automáticas (esquema real de Supabase) | **182 de 182 pasan** (12 nuevas en `tests/test_zz_zz_19oct_noche.py`) |
| Pruebas automáticas (esquema reconstruido) | **180 pasan**, 2 no aplican a ese esquema |
| Recorrido en el navegador: 20 pantallas y todas sus pestañas | **0 errores 500**, 0 errores de JavaScript, 0 enlaces rotos (PDF, imprimir, exportar) |
| Botones sin función | Se encontró 1: "Entendido"/× del aviso del comparativo, en todas las pantallas. **Corregido.** |
| Montos con más de 2 decimales en pantalla | **0** después de la corrección |
| Flujo completo probado en pantalla | Crear PC sin condición (bloquea), con condición y OC del cliente (queda **PC-KCF-000001**, luego -000002). Cotización sin los 4 campos (bloquea) y aviso amarillo. Despachar (sale "¡Guía creada con éxito!", el botón lleva a Guías con la guía marcada). Crear factura desde la guía (**Crédito 60 días tomada del PC**). Guardar (sale "¡Factura creada con éxito!", el botón lleva a Facturas con la factura marcada y la condición correcta en la lista). Nueva contraseña de usuario. |
| ZIP | Arranca con gunicorn (como en Render), /login 200 |
| Errores encontrados y corregidos en la auditoría | 1) La lista de Facturas decía siempre "Contado". 2) Al guardar la factura, la ventana de confirmación quedaba detrás de la factura; antes por eso se cerraba la factura primero, y si cancelaba se perdía lo escrito. 3) Si la factura no se guardaba, el aviso no decía por qué (ahora dice, por ejemplo, "El monto total del comprobante debe ser mayor a 0"). 4) "Solicitar validación" decía "enviada" aunque no se hubiera guardado. 5) La guía hecha desde un despacho no quedaba anotada en el despacho (el campo guía siempre estaba vacío). 6) Dos guías guardadas a la vez podían tomar el mismo número. 7) El botón sin función del punto anterior. |

### 17.5 Contraseñas (resumen, sin contraseñas)

- 6 de 7 usuarios ya tenían la contraseña cifrada. Cifrada quiere decir que nadie puede leerla, ni siquiera el administrador.
- **eri01kcf** la tenía sin cifrar. Ahora está cifrada y es **la misma contraseña**, así que se entra igual.
- Además, cualquier contraseña antigua sin cifrar se cifra sola la próxima vez que esa persona entra.
- Si alguien olvida la suya, el administrador le pone una nueva con **"🔑 Nueva contraseña"**. Puede escribirla o pulsar "Generar". Se guarda cifrada y queda en la Auditoría, sin la contraseña.
- El detalle está en `CONTRASENAS_USUARIOS.md`, que está en la carpeta del proyecto y no en la página.

### 17.6 Cambios en Supabase: migración 011 (aplicada el 19/10 ~20:35)

Archivo: `SUPABASE_011_oc_cliente_condicion_pago.sql`. Tiene el respaldo, la verificación y **cómo deshacer**.

- **Nuevo:** columna `pedido_compra_pc.oc_cliente` (N° OC del cliente).
- **Condición escrita igual:** "Credito N Dias" pasó a "Crédito N días" en las cotizaciones, las cotizaciones eliminadas y las PC que lo tenían escrito así. Solo cambia la forma de escribirlo, no el significado.
- **Clientes:** los 5 que tenían "Credito N Dias" (creados desde una cotización: CLI-000211, 212, 213, 216, 228) pasaron a "Crédito aprobado" con N días.
- **Contraseña:** eri01kcf quedó cifrada.
- **Respaldo:** en `respaldo_20261015.*_pre011`.
- **Nada borrado:** conteos iguales antes y después, y la fecha de "Modificado" de esas filas no cambió.
- **No se tocaron las facturas.**

**Clientes con datos que no cuadran** (no se cambiaron; corríjalos en Maestros ▸ Clientes o dígame qué poner):

- "Crédito aprobado" con 0 días: **CLI-000150 METROCOLOR S.A.**
- "Contado" pero con días guardados:
  - CLI-000142 EJERCITO PERUANO (160)
  - CLI-000146 SUPERMERCADOS PERUANOS (1)
  - CLI-000173 IMPORTACIONES HIRAOKA (15)
  - CLI-000174 CYBERTEL (45)
  - CLI-000180 DEVIDA (45)
  - CLI-000182 SNACKS AMERICA LATINA (15)
  - CLI-000203 PROTECCION VIP (30)
  - CLI-000214 EXPRESO ANTEZANA (30)
  - CLI-000225 FINI PERU (45)
- "Personalizado" con 0 días: CLI-000229 SOLSAME.

Mientras tanto, la factura toma "Contado" para esos clientes, porque es lo que dice su condición.

### 17.7 Lo que tiene que hacer

1. Subir **este** ZIP (`pruebasweb_corregido.zip`) a Render. La migración 011 ya está aplicada: no hay que correr nada en Supabase.
2. Elegir con sus chicas la condición correcta de los clientes de la lista anterior.
3. Decir si quiere que corrija la condición de las facturas antiguas que salieron "Contado".

## 18. Correcciones de flujo, estética y lógica + facturas antiguas corregidas (20/10/2026)

Pedido de Erika del 20/10 14:19 ("CORRECCIONES DE FLUJO, ESTÉTICA Y LÓGICA DE NEGOCIO") y su confirmación escrita
("si corregir", 14:44) para corregir las facturas antiguas que salieron al contado. Pruebas: **188/188**.
Capturas en `capturas-20oct/`.

### 18.1 Qué se hizo

| # | Pedido | Estado | Cómo quedó |
|---|---|---|---|
| Cot 1 | "Inmediato en entrega" solo Pendiente / Entregado | ✅ ya estaba | La columna **Entrega** de cada producto (Crear cotización ▸ 4. Productos cotizados) solo tiene **Pendiente** y **Entregado** desde el 16/10. Ahora además la base lo exige (migración 012) y el servidor convierte cualquier otro valor en Pendiente. |
| Cot 2 | Datos de la parihuela obligatorios para validar | ✅ | Para **"Solicitar validación"** tiene que estar llena toda la fila de la parihuela (sección 5): Seguimiento, Motivo, Transporte, Parihuela y **Nota interna** (si no hay nada, escribir "Ninguna"). Si falta algo, se bloquea con "Faltan campos obligatorios para enviar a validación" y el campo se marca en rojo. Un borrador sí se puede guardar sin la nota. Lo revisan la pantalla y el servidor. |
| Com 1 | "Aprobada" en verde fuerte | ✅ ya estaba (19/10) | Compras ▸ Órdenes de compra. Si en Render se ve en otro color, su Render tiene un ZIP anterior al 19/10. |
| Com 2 | Paso 2 en amarillo más fuerte | ✅ ya estaba (19/10) | Al abrir una OC "Por aprobar", el paso 2 "Aprobada" sale en amarillo fuerte (#FFD600) con halo. |
| Com 3 | Panel de abastecimiento + pedir de más | ✅ completado | El panel "📊 Resumen de abastecimiento" (dentro de Nueva orden de compra, debajo de los productos) muestra stock actual, pedido del cliente, sugerido y total a comprar. **Nuevo: columna "Extra para stock"**: se escribe cuánto más se quiere comprar y el sistema agrega una línea aparte "Para stock · sin pedido" (así lo del cliente y lo de más no se mezclan, y la compra extra pide motivo). En "Pedidos por comprar" sigue la columna "Comprar para stock". |
| Com 4 | Aviso de RUC duplicado | ✅ | En Maestros ▸ Crear cliente y Crear proveedor, apenas se escribe el RUC (o se carga con SUNAT) sale un **aviso rojo grande**: "⛔ Este RUC ya está registrado como cliente: CLI-0001 · NOMBRE (Activo). No lo vuelvas a crear: búscalo en la lista y edítalo." Al editar ese mismo cliente no sale. El servidor igual impide guardarlo dos veces. |
| Com 5 | Factura de proveedor que no cuadra | ✅ | En Compras ▸ Pagos y facturas, si el total no cuadra con lo recibido **no se guarda**: sale un cuadro rojo "La factura NO cuadra. No se guardó", con lo que escribió, lo que debería ser y la diferencia; el total queda marcado para corregirlo ahí mismo. Solo si la factura física de verdad dice ese monto, se marca la casilla y se escribe el motivo: entonces se registra **dentro de su OC** como diferencia por resolver (nunca suelta). Además, la pantalla anterior de comprobantes ya no acepta facturas de órdenes nuevas (se saltaba la revisión). |
| Com 6 | Botón "Ver la factura registrada recientemente" | ✅ | En Pagos y facturas, arriba a la derecha de "Facturas de proveedores por registrar". Abre la última factura que registró ese usuario (N°, OC, proveedor, total, fechas, si cuadra, quién y cuándo) y tiene "Ver la orden de compra". Después de guardar se pone verde con el N° de la factura. |
| Guías 1 | Columna Nr° PC después de Cotización | ✅ ya estaba (19/10) | |
| Guías 2 | "Comprobante" → "Nr° Facturas" | ✅ | |
| Fact 1 | "Documento" → "Nr° factura" | ✅ | |
| Fact 2 | Orden Cotización > Nr° PC > Nr° Guía > Nr° Factura | ✅ | La columna Nr° factura ahora va después de Nr° guía. |
| PC 1 | "Pendiente por compra" solo con "Aceptada por Cliente" | ✅ | En la lista de cotizaciones la etiqueta de abastecimiento ya no sale en "Generada" ni antes; solo cuando el cliente aceptó. Lo filtran la pantalla y el servidor. |
| Mejora | Error grande al despachar sin stock | ✅ | Ventana roja grande **"⛔ NO SE PUEDE DESPACHAR: FALTA STOCK"** con una tabla: producto, empresa · sede, cuánto pide, cuánto hay y cuánto falta. Lista **todos** los productos que faltan (antes se detenía en el primero y no decía la sede). Sale antes de intentar si la sede elegida no alcanza, y también si el servidor lo detecta. No se descuenta nada. |
| Card | Corregir facturas antiguas "Contado" | ✅ aplicado | Ver 18.2. |

### 18.2 Facturas antiguas corregidas (migración 012, aplicada en Supabase el 20/10/2026)

Respaldo previo: `respaldo_20261015.comprobantes_pre012` (las 26 facturas). Cada cambio quedó en Papelera / Auditoría
como "CORRECCION_CONDICION_PAGO" con el antes y el después. Solo cambió la condición, los días, "es crédito" y el
vencimiento (fecha de emisión + días). No se tocó el total, los productos, el estado SUNAT ni el estado del crédito.

| Factura | PC | Antes | Ahora | Vence |
|---|---|---|---|---|
| F001-52860405 | PC-20260720-4955 | Contado | Crédito 30 días | 19/09/2026 |
| F001-22960633 (boleta) | PC-20260717-2000 | Contado | Crédito 15 días | 05/09/2026 |
| F001-69427205 | PC-20260826-5555 | Contado | Crédito 15 días | 10/09/2026 |
| F001-48252945 | PC-20260826-5555 (de su guía T001-48193830) | Contado | Crédito 15 días | 12/09/2026 |
| F001-88187485 | PC-20260826-555510 | Contado | Crédito 30 días | 15/11/2026 |
| F001-88187486 | PC-20261016-00001 | Contado | Crédito 45 días | 30/11/2026 |
| F001-88187490 | 2040808080 | Contado | Crédito 30 días | 15/11/2026 |
| F001-88187491 | PC-20260720-495500 | Contado | Crédito 90 días | 17/01/2027 |
| F001-88187493 | PC-20261019-0001 | Contado | Crédito 45 días | 03/12/2026 |

**No se tocaron (no tienen un PC claro), para que Erika decida:**
- F001-86773596: su PC vinculado (30 días) y el de su cotización COT-000003 (15 días) no coinciden.
- F001-87021168, F001-87039526, F001-71235956: sin PC ni guía.
- F001-87373429, F001-87709785, F001-88095381, F001-88187484, F001-20484920, F001-20639564: solo tienen la cotización (sin PC ni guía vinculada). F001-20639564 ya dice 90 días y "Aceptada en Crédito" pero la condición quedó "Contado".
- F001-32079376: su cotización COT-000015 tiene dos PC (120 y 90 días).

Nota: esto corrige el ERP (Cuentas por cobrar y vencimientos). Si esas facturas ya se enviaron a SUNAT, el documento
enviado no cambia.

Cómo deshacer: está al final de `SUPABASE_012_facturas_condicion_desde_pc.sql`.

### 18.3 Error escondido que se corrigió

- **"💾 Guardar / Actualizar" cliente desde la cotización borraba datos del cliente**: mandaba solo unos datos y el
  servidor dejaba vacíos los contactos, puntos de entrega, días de crédito, límite, descuento y observaciones, y además
  le ponía al cliente la condición de la cotización (un vendedor podía darle crédito al cliente solo cotizando). Ahora lo
  que no se manda se conserva, y la condición del cliente solo se cambia en Maestros ▸ Clientes. Un cliente nuevo
  creado desde la cotización nace "Contado". En la auditoría (desde el 19/10) no se ve ningún cliente dañado por esto.
- La búsqueda de la última factura de proveedor funcionaba distinto según el tipo de columna; quedó igual en las dos bases.

### 18.4 Base de datos (migración 012)

- `cotizacion_detalle.estado_entrega` solo acepta Pendiente o Entregado (hoy las 76 filas dicen Pendiente).
- Corrección de las 9 facturas (18.2). No se borró nada. Verificado después: 26 facturas antes y después, 9 corregidas
  con su fila de auditoría, 11 siguen "Contado" (las de la lista de arriba).

### 18.5 Pruebas y revisión

- 188 pruebas con la estructura real y 186 + 2 omitidas con la reconstruida. Pruebas nuevas en `tests/test_zz_zz_20oct.py`.
- Revisión de 21 pantallas y pestañas en el navegador: sin errores (solo /comprobantes da 404, que no está enlazada).

## 19. Macro-actualización: condición de pago en Facturas + Resultados de Auditoría (20/10/2026, tarde)

Pedido de Erika del 20/10 16:47 ("MACRO-ACTUALIZACIÓN: CONTRASEÑAS, AUDITORÍA, MEJORAS UX, FLUJOS Y BUGS").
Pruebas: **190/190** (base real reconstruida: 188 + 2 omitidas). Capturas nuevas en `capturas-20oct/` (12 a 15).
**Supabase: no se cambió nada** (ver 19.4).

### 19.1 Bug crítico: condición de pago en Facturas, RESUELTO

**Qué pasaba.** La condición se llenaba sola solo si se elegía la guía o el PC dentro de la factura. En otros tres caminos
quedaba la primera opción de la lista, **"Contado"**, sin avisar:
1. **Crear factura desde la cotización** (menú ⋮ de la cotización ▸ Factura).
2. Factura nueva eligiendo **solo la cotización** en "Cotización vinculada".
3. Factura nueva escribiendo **el RUC a mano**, sin guía ni PC.

**Cómo quedó.**
- La factura nueva empieza con la condición **vacía**: "— Se llena sola: elige PC, guía, cotización o RUC —".
- En los 5 caminos (guía, PC, cotización, crear desde la cotización y RUC a mano) se llena sola: primero la del **PC** (también el PC de la guía o de la cotización), y si no hay PC, la de la **ficha del cliente**. Debajo dice de dónde salió: "✔ Tomada del PC PC-…" o "✔ Tomada de la ficha del cliente".
- Si no hay PC y el cliente no tiene condición, sale en rojo "⚠ Elige la condición…" y **no deja guardar** la factura sin condición.
- Al guardar, el servidor pone los días y el vencimiento según la condición ("Crédito 30 días" → 30 días). Esto ya estaba bien desde el 19/10.
- Al abrir una factura ya guardada se muestra la condición que tiene guardada; no se cambia sola.

Probado en el sistema de prueba con cada camino (capturas 12 a 15) y con dos pruebas automáticas nuevas
(`tests/test_zz_zz_20oct_tarde.py`).

**Su base real.** La última factura en Supabase es del **19/10 a las 14:04**, y las tres últimas tienen bien la condición
de su PC. Las 9 facturas antiguas que decían "Contado" ya se corrigieron hoy con la migración 012 (sección 18.2).
**Para que el arreglo se vea en Render hay que subir este ZIP nuevo.** Si en Render la condición sigue sin llenarse, es que
está corriendo un ZIP anterior.

### 19.2 Resultados de Auditoría: qué de la lista YA ESTABA HECHO

Revisé cada punto en el código y en el sistema de prueba. **No los volví a hacer**, porque ya funcionan:

| # | Pedido | Estado | Desde | Dónde verlo |
|---|---|---|---|---|
| 1 | Condición de pago en Facturas | 🔧 **Corregido hoy** | 20/10 tarde | Ver 19.1 |
| 2.1 | "Inmediato en entrega" solo Pendiente / Entregado | ✅ ya estaba | 16/10 (y la base lo exige desde la 012, hoy 15:00) | Crear cotización ▸ 4. Productos cotizados ▸ columna Entrega |
| 2.2 | Parihuela obligatoria antes de validar | ✅ ya estaba | 20/10 15:00 (sección 18) | Crear cotización ▸ 5. Seguimiento, motivo, transporte, parihuela y nota interna |
| 2.3 | "Faltan campos obligatorios" al solicitar validación | ✅ ya estaba | 19/10 noche + 20/10 | Bloquea y marca en rojo; el servidor también lo bloquea |
| 2.4 | Alerta amarilla "Ojo: No has llenado la información adicional…" | ✅ ya estaba | 19/10 noche | No bloquea; pregunta si desea continuar |
| 2.5 | Ayuda "✅ ¡Guía creada! 👉 Paso 1… Paso 2…" con botones "Ir a Guías de Remisión" / "Ir a Facturas" | ✅ ya estaba | 19/10 noche | Al entregar en Despachos, al crear la guía y al crear la factura |
| 3.1 | "Aprobada" en verde fuerte | ✅ ya estaba | 19/10 | Compras ▸ Órdenes de compra |
| 3.2 | Paso 2 en amarillo fuerte | ✅ ya estaba | 19/10 | Al abrir una OC por aprobar |
| 3.3 | Panel de abastecimiento + campo para pedir más stock | ✅ ya estaba | 19/10 + "Extra para stock" 20/10 15:00 | Nueva orden de compra, debajo de los productos |
| 3.4 | Aviso de RUC duplicado | ✅ ya estaba | 20/10 15:00 | Maestros ▸ Crear cliente / Crear proveedor |
| 3.5 | Factura de proveedor que no cuadra no se guarda suelta | ✅ ya estaba | 20/10 15:00 | Compras ▸ Pagos y facturas |
| 3.6 | Botón "Ver la factura registrada recientemente" | ✅ ya estaba | 20/10 15:00 | Pagos y facturas, arriba a la derecha |
| 4.1 | Guías: "Nr° PC" después de Cotización | ✅ ya estaba | 19/10 | Ventas ▸ Guías de remisión |
| 4.2 | Guías: "Comprobante" → "Nr° Facturas" | ✅ ya estaba | 20/10 15:00 | |
| 4.3 | Facturas: "Documento" → "Nr° factura" | ✅ ya estaba | 20/10 15:00 | |
| 4.4 | Facturas: orden Cotización > Nr° PC > Nr° Guía > Nr° Factura | ✅ ya estaba | 20/10 15:00 | |
| 4.5 | Observaciones de la factura con la primera letra en mayúscula | ✅ ya estaba | 19/10 noche | Se corrige al salir del campo y otra vez al guardar (también en el servidor) |
| 5.1 | Quitar "Pendiente por comprar" en cotizaciones "Generada" | ✅ ya estaba | 20/10 15:00 | Solo sale con "Aceptada por Cliente" |
| 5.2 | Precios del PC con 2 decimales (62.61) | ✅ ya estaba | 19/10 noche | Crear PC ▸ 3. Productos PC; en todo el sistema máximo 2 decimales |
| 5.3 | Checkbox "Generar N° de PC Automático" | ⏸️ **no se hizo, a propósito** | — | Ver 19.3 |
| 5.4 | Condición de pago del PC en blanco | ✅ ya estaba | 19/10 noche | Crear PC ▸ 2. Datos PC: empieza vacía y es obligatoria; nunca se copia de la cotización |
| 5.5 | Línea "Descuento" en el Resumen PC | ✅ ya estaba | 19/10 tarde | Subtotal → Valor venta → **Descuento** (S/ 0.00 si no hubo) → IGV → Total |
| 6.1 | Error rojo grande al despachar sin stock, con producto y sede | ✅ ya estaba | 20/10 15:00 | Ventana "⛔ NO SE PUEDE DESPACHAR: FALTA STOCK" |
| 6.2 | Listado de contraseñas | ✅ ya estaba | 19/10 noche | Están cifradas: no se pueden leer. Ver `CONTRASENAS_USUARIOS.md` y 19.5 |
| 6.3 | Botón del administrador para poner contraseña nueva sin la anterior | ✅ ya estaba | 19/10 noche | Configuración ▸ Usuarios y permisos ▸ "🔑 Nueva contraseña" |

### 19.3 Checkbox "Generar N° de PC Automático": por qué no se hizo

Choca con lo que Erika pidió por audio el 19/10: **el N° de PC interno es siempre automático por empresa**, y aparte
está el campo **"N° OC del cliente"** para el número que manda el cliente (por ejemplo, Komatsu). Así no se repiten
números y no se escriben a mano. Por eso se mantiene así. La tarjeta "¿Cómo se numera el PC?" sigue abierta en el chat
principal: si Erika elige **"Con check"**, se agrega el checkbox.

### 19.4 Supabase

**No se cambió nada en la base.** El error estaba en la pantalla, no en la base. Archivo de entrega:
`SUPABASE_SIN_CAMBIOS_20oct_tarde.sql`. Dice esto mismo y trae solo consultas de lectura para comprobarlo en el SQL Editor.
La próxima migración, cuando haga falta, será la 013.

### 19.5 Hallazgo en la auditoría: Luis y Despacho no pueden entrar

Los usuarios **luis01kcf** y **desp01kcf** tienen la contraseña **incompleta** en la base desde que se crearon (25/06/2026).
Lo guardado es un pedazo de cifrado y no una contraseña completa. Por eso **ninguna contraseña les funciona** y nunca han entrado.
No se puede leer ni recuperar. No les puse una contraseña nueva, porque nunca creo contraseñas que Erika no sepa.

**Solución (1 minuto):** un administrador entra a Configuración ▸ Usuarios y permisos ▸ "🔑 Nueva contraseña" en cada uno.

### 19.6 Qué se probó

| Prueba | Resultado |
|---|---|
| Pruebas automáticas (pytest), base de prueba | **190 de 190** pasan |
| Pruebas automáticas con la estructura real de Supabase | **188 pasan, 2 omitidas** (no aplican a esa estructura) |
| Recorrido de 21 pantallas con navegador real (todas las pestañas, botones Exportar y enlaces PDF) | **0 errores 500, 0 enlaces rotos.** Solo /comprobantes da 404, que es esperado: Facturas está en Ventas. |
| Condición de pago en la factura: guía, PC, cotización, crear desde la cotización, RUC a mano, cliente sin condición, editar factura guardada | Todos correctos (capturas 12 a 15) |
| ZIP | Se descomprime y arranca con gunicorn como en Render (HTTP 200 en /login) |
| Base real (solo lectura) | Última factura del 19/10 14:04, con su condición bien; 7 usuarios: 5 cifrados y 2 incompletos (19.5) |

### 19.7 Archivos que cambiaron

- `static/js/ventas.js`: condición vacía al crear la factura, llenado automático en los 5 caminos, aviso rojo y bloqueo al guardar sin condición.
- `tests/test_zz_zz_20oct_tarde.py`: 2 pruebas nuevas.

## 20. Validaciones más livianas, tablas sin scroll, Entregas en colores (20/10/2026, 17:19 y 17:24)

Pedidos de Erika del 20/10 a las 17:19 (texto + audio + 3 capturas) y 17:24 (audio + captura de Entregas).
Pruebas: **192/192** (estructura real reconstruida: 190 + 2 omitidas). Recorrido de 21 pantallas: **0 errores 500**.
Capturas en `capturas-20oct-noche/`. **Supabase: no se cambió nada** (no hay restricciones que quitar; ver 20.4).

### 20.1 Qué se hizo

| # | Pedido | Estado | Cómo quedó |
|---|---|---|---|
| 1.1 | Nota interna no obligatoria | ✅ | Se puede guardar y **Solicitar validación** con la nota interna vacía (pantalla y servidor). Si está vacía solo sale la alerta amarilla suave, que no bloquea. Siguen obligatorios Seguimiento, Motivo, Transporte y Parihuela. |
| 1.2 | Transporte fuera de la validación comercial | ✅ | Según el audio: en **Editar PC ▸ 4. Validación comercial** quedan 6 interruptores: Precio, **Nombre producto**, **Lugar entrega**, Cantidad, Moneda y Vigencia. **Transporte se eliminó** y ya no puede dejar el PC "observado". En la **cotización** el Transporte sigue obligatorio (regla de su audio del 19/10). Si también lo quiere opcional ahí, es un cambio de una línea. |
| 1.3 | "Generada" sin "Pendiente por compra" / "Falta stock" | ✅ ya estaba (hoy 15:00) | En Cotizaciones la etiqueta solo sale con "Aceptada por Cliente". Si en Render sale en "Generada", Render tiene un ZIP anterior. **En Entregas sí se sigue mostrando** a propósito: avisa que ese despacho no tiene stock completo para salir. |
| 2.1 | Tablas sin scroll lateral | ✅ | Regla general para todas las tablas de las pantallas: las columnas se acomodan al ancho y el texto largo baja de línea. Los montos ya no se parten ("S/" y el número quedan juntos). Medido con navegador en 34 pantallas y pestañas: **0 tablas con scroll lateral** en pantallas de 1366 px o más (laptop normal) y en 1920 px. Antes había 15 a 1366 px. Las ventanas de cotización (productos) mantienen su tabla ancha a propósito. |
| 2.2 | "Producto" → "Nombre producto"; "Entrega" → "Lugar entrega" | ✅ | 41 títulos de columna en Ventas, Compras, Inventario y Herramientas. La columna "Entrega" de **Productos cotizados** es el **estado** (Pendiente / Entregado), no un lugar: ahí ahora dice **"Estado entrega"** para no confundir. Los PDF no cambian. |
| 3.1 | Crear Despacho desde el PC lleva a Entregas | ✅ | Al pulsar **⋮ ▸ Crear despacho** en un PC (y "Enviar a Entregas" en Revisión), el sistema abre **Entregas** y resalta en verde la fila del despacho recién creado. |
| 17:24 | Entregas: colores y nombres | ✅ | **Estado**: lo pendiente dice **"⏳ Por despachar"** en rojo encendido; lo terminado **"✔ Despachado"** en verde fluorescente. **Acción**: el botón dice **"🚚 Confirmar despacho"** en rojo (se pulsa cuando la mercadería ya salió); cuando está hecho dice **"✔ Despachado"** en verde fluorescente. En Revisión, el botón que crea el despacho ahora dice **"Enviar a Entregas"** para no confundirlo. En la base el estado sigue guardado igual, así que filtros, reportes y datos antiguos no cambian. |

### 20.2 Errores escondidos corregidos

- Al crear un despacho desde el PC, el aviso decía **"Despacho undefined creado"**. Ahora dice el número (por ejemplo, DESP-20261020-0002).
- Los montos en tablas angostas se partían en dos líneas ("S/" arriba y el número abajo).

### 20.3 Sobre la captura de Entregas

- La etiqueta "Pendiente por compra" debajo de "Por despachar" es correcta: ese despacho todavía no tiene stock completo.
- El Nr° PC **2040808089** de la fila 2 es un número de PC escrito a mano antes del 19/10 (parece un RUC). Desde el 19/10 el N° de PC es automático (PC-KCF-000001…), así que no se repetirá. No lo cambié porque es un dato real.

### 20.4 Supabase

No se cambió nada. Revisé que la base no obligue la nota interna ni el transporte (todas esas columnas aceptan vacío). Tampoco hay PC que hayan quedado "observados" solo por el transporte. Archivo: `SUPABASE_SIN_CAMBIOS_20oct_noche.sql`, solo con consultas de lectura. La próxima migración real era la 013 (se usó después para la fecha de cita, sección 21).

### 20.5 Archivos que cambiaron

- `routes/ventas.py`: nota interna opcional y transporte fuera de la validación del PC.
- `static/js/ventas.js`: validaciones, Entregas, crear despacho, nombres de columnas y montos.
- `templates/base.html`: regla de tablas sin scroll.
- `templates/ventas/index.html`: colores de Entregas y nombres.
- `templates/ventas/modales/pedido_compra_modal.html`: 6 interruptores.
- Títulos de columnas en `templates/compras/*`, `templates/inventario/index.html`, `static/js/{inventario,compras_flujo,herramientas}.js`.
- Pruebas: `tests/test_zz_zz_20oct.py` (actualizada) y `tests/test_zz_zz_20oct_tarde.py` (2 nuevas).

## 21. Entregas: filas de color, Estado compra, Fecha de cita, Generar compra y guía sin stock (20/10/2026, 18:09)

Pedido por audio de Erika sobre la tabla de Ventas ▸ Entregas.

### 21.1 Qué cambió en Entregas

- **Fila completa sombreada**: rosado claro si está "⏳ Por despachar" y verde claro si está "✔ Despachado". La etiqueta de estado sigue en rojo encendido (pendiente) y verde fluorescente (despachado).
- **Columnas nuevas y nombres**: Item, Fecha / Hora, Estado, Nr° despacho, Nr° PC, **Nr° cotización** (al lado del PC), Cliente, Nr° guía / Nr° factura, **Lugar entrega** (antes "Destino"), **Estado compra**, **Fecha de cita**, Acción.
- Nr° guía y Nr° factura van **en una sola columna** (uno debajo del otro) para que la tabla entre sin scroll lateral.
- **Estado compra**: "✔ Comprado / en stock", "📦 Comprado, por llegar", "🚚 Comprado, por recoger" o "🛒 Pendiente de compra" (en rojo). Si ya se despachó: "✔ Comprado".
- **Fecha de cita del cliente**: botón "📅 Poner cita" en cada fila pendiente. Se guarda con fecha y hora y queda en Auditoría. Se puede cambiar o quitar.
- **Botón amarillo "🛒 Generar compra"**: aparece cuando el despacho está "Pendiente de compra". Abre Compras ▸ Generar OC con ese pedido ya marcado y la OC lista para completar.
- **Botón "🧾 Generar factura"**: abre Facturas con el PC, el cliente, los productos y la condición de pago ya llenos.

### 21.2 Guía y factura sin stock

- **La guía de venta no se puede crear si falta stock.** Sale el mensaje "NO SE PUEDE CREAR LA GUÍA: FALTA STOCK" con el producto, cuánto pide y cuánto hay. Primero hay que comprar o recibir la mercadería.
- **La factura sí se puede hacer sin stock** (clientes que piden factura antes de pagar).
- Excepciones: guías de traslado (no son venta) y guías de un despacho que ya figura como Despachado (el stock ya salió).

### 21.3 Supabase (migración 013, aplicada)

- Antes: respaldo de la tabla despachos en `respaldo_20261015.despachos_pre013` (27 filas, igual que la tabla).
- Cambio: columna nueva `despachos.fecha_cita` (fecha y hora, vacía por defecto). No se borró ni cambió ningún dato.
- Cómo revertir: `ALTER TABLE public.despachos DROP COLUMN IF EXISTS fecha_cita;`
- Archivo: `SUPABASE_013_despachos_fecha_cita.sql`. La próxima migración será la 014.

### 21.4 Pruebas

- 195/195 pruebas correctas (3 nuevas: guía sin stock bloqueada y factura permitida, fecha de cita, pantalla de Entregas).
- Probado en pantalla: tabla sin scroll lateral, cita guardada, factura llenada desde Entregas, guía sin stock bloqueada, "Generar compra" abre la OC. Capturas en `capturas-20oct-1809/`.

### 21.5 Sobre la captura de Erika

Su captura muestra "Pendiente despacho" y el botón verde "Despachar": es un ZIP anterior. Hay que subir este ZIP nuevo a Render para ver los cambios de las secciones 20 y 21.

### 21.6 Archivos que cambiaron

- `routes/ventas.py`: bloqueo de guía sin stock, fecha de cita (guardar y listar).
- `static/js/ventas.js`: tabla de Entregas, Estado compra, cita, Generar compra, Generar factura, aviso de falta de stock.
- `static/js/compras_flujo.js`: abrir Generar OC con el pedido cargado.
- `templates/ventas/index.html`: columnas y colores.
- `migrations/013_despachos_fecha_cita.sql`.
- Pruebas: `tests/test_flujos.py`, `tests/test_zz_zz_19oct_noche.py`, `tests/test_zz_zz_20oct_tarde.py`.

## 22. Orden en tablas, ayudas en Compras, OC con su PC y bloqueo de duplicados (20/10/2026, 22:54, 22:56 y 22:59)

Pedidos de Erika: el prompt "MEJORAS DE ORDEN, AYUDAS VISUALES EN COMPRAS Y PREVENCIÓN DE DUPLICADOS" con sus líneas finales, la captura de las tarjetas (22:56) y la captura de Entregas (22:59).

### 22.1 Orden y nombres

- **"N°" en vez de "Nr°"** en todas las tablas, estados y pantallas (reemplaza la regla del 19/10).
- **Primero el cliente o proveedor, después el RUC** en todas las tablas: Cotizaciones (las dos vistas), Revisión, PC Pedido Compras (las dos vistas), Guías, Facturas, Notas de crédito, Devoluciones, Facturas de proveedor (Compras) y la vista completa de Clientes y Proveedores en Maestros. Las demás tablas ya estaban así. En los formularios el RUC sigue arriba porque al escribirlo se llena solo el nombre (consulta SUNAT).
- **Tarjetas de resumen en una sola fila**, todas del mismo ancho, en todos los módulos (Ventas, Compras, Inventario, Maestros, Finanzas, Reportes). En pantallas menores de 1100 px pueden bajar a otra línea para que se lean.
- Botón **"🏷️ Generar rótulo"** (antes "Rótulo").

### 22.2 Ayudas en Compras ("¿Ahora qué?")

Después de cada acción sale un cartel verde grande con lo que se hizo, el siguiente paso y un botón que lleva ahí:

| Acción | El cartel dice | Botón |
|---|---|---|
| Guardar OC (borrador) | Revísala y pulsa "Enviar a aprobar" | Ir a Órdenes de compra |
| Enviar a aprobar | La supervisora debe aprobarla (estado "Por aprobar") | Ir a Órdenes de compra |
| Aprobar (contado) | Ve a Pagos y facturas y pulsa "Pagar" | Ir a Pagos y facturas |
| Aprobar (crédito) / Pago registrado | Cuando llegue, ve a Recibir mercadería | Ir a Recibir mercadería |
| Mercadería recibida | Ve a Compras ▸ Pagos y facturas para registrar la factura del proveedor; además "Ingresar" en Inventario | Ir a Pagos y facturas / Ir a Inventario |
| Factura del proveedor registrada | Pagar (si es crédito) o compra completa | Según el paso |
| Devolver, anular, cerrar con faltante | Qué sigue en cada caso | Según el paso |

El cartel siempre pregunta al servidor el paso real de la orden, así que no se equivoca de pantalla.

- La lista de Órdenes de compra tiene las columnas **N° PC** y **N° cotización** ("Sin PC" si es compra para stock).
- En "Pedidos por comprar" cada pedido muestra su **N° cotización**.

### 22.3 La OC dice a qué PC pertenece

- En la pantalla de la orden: "🔗 Relacionado al PC: PC-…" (con su N° cotización) o "📦 Compra directa a stock (Sin PC)".
- En la OC impresa / PDF: "Relacionado al PC: PC-…" o "Compra directa a stock (Sin PC)".
- Antes la OC del proveedor no mostraba el PC (regla del 16/10). Ahora muestra **solo el número de PC**; el nombre del cliente, la cotización del cliente y el motivo interno siguen sin salir en lo que ve el proveedor.

### 22.4 Bloqueo de duplicados (lo valida el servidor)

Lo anulado no cuenta. Las entregas y facturas **parciales** siguen permitidas: se bloquea solo cuando ya existe el documento.

- **Orden de compra**: no se crea si ya hay una OC activa (Borrador, Por aprobar, Aprobada o Recibida parcial) del **mismo proveedor para el mismo PC**, ni una OC **idéntica** (mismo proveedor, mismos productos y mismas cantidades). Mensaje: "⛔ ERROR: Ya existe una Orden de Compra activa para este pedido (OC-…). No se puede duplicar." Para el mismo PC con **otro proveedor** sí se puede.
- **Guía de remisión**: no se crea una segunda guía activa para el mismo despacho. Para un PC, se bloquea si ya hay guía y la nueva pasaría lo que pidió el PC.
- **Factura**: no se crea una segunda factura activa para la misma guía. Para un PC, se bloquea si ya está facturado y la nueva pasaría lo que pidió. La factura sin guía y sin stock sigue permitida (regla de las 18:09).
- **Despacho** (nuevo, por su captura): no se crea otro despacho de un PC cuyos productos ya están cubiertos por otros despachos activos.
- El aviso sale en una ventana roja grande que dice qué documento ya existe.
- Si dos personas guardan a la vez, la base no deja repetir el número de factura ni de guía (migración 014).

### 22.5 Supabase (migración 014, aplicada)

- Antes: respaldo en `respaldo_20261015.comprobantes_pre014` (27 filas) y `respaldo_20261015.guias_remision_pre014` (21 filas), iguales a las tablas.
- Cambio: 2 índices únicos (mismo tipo + serie + número + empresa no se repite). Revisé antes que no hubiera números repetidos. Los números de despacho y de OC ya eran únicos. No se borró ni cambió ningún dato.
- Cómo revertir: `DROP INDEX IF EXISTS public.ux_comprobantes_numero_por_empresa; DROP INDEX IF EXISTS public.ux_guias_numero_por_empresa;`
- Archivo: `SUPABASE_014_documentos_sin_duplicados.sql`. La próxima migración será la 015.
- No puse índices de "una factura por guía" o "un despacho por PC" en la base porque ya hay datos repetidos de antes (22.6). El servidor ya los bloquea desde ahora.

### 22.6 Duplicados que ya estaban en tu base (no toqué nada, decides tú)

| Qué | Documentos | Comentario |
|---|---|---|
| 2 despachos del PC-KCF-000002 | DESP-20261020-0001 (12:15) y DESP-20261020-0002 (13:33), ambos "Pendiente despacho", 10 cartuchos cada uno | El PC pide 10. El segundo parece repetido. Sugiero anular DESP-20261020-0002 (botón Anular). La factura F001-88187496 es una sola, del PC. |
| Despachos repetidos de PC antiguos | PC 1942000000 (3), 202020202020 (2), 2040346000 (4) | De agosto/septiembre, con números de PC manuales. |
| 2 facturas de la misma guía | F001-52860405 y F001-22960633 (guía T001-G-20260820-0383), ambas Emitidas | Revisar si una debe ir con nota de crédito. |
| 2 facturas del mismo PC | F001-52860405 (Emitida) y F001-86773596 (Borrador), S/ 47.20 cada una, PC-20260720-4955 | La de borrador parece repetida. |
| Varias guías de la misma cotización | COT-000003 (4), COT-000020 (4), COT-000008 (2), COT-000028 (2) | Pueden ser entregas parciales; revisar las que están en Borrador. |

### 22.7 Sobre las capturas de las 22:59

Su captura de Entregas sigue mostrando "Pendiente despacho", el botón verde "Despachar" y la columna "Destino": es un ZIP anterior. Los estados distintos (rojo "⏳ Por despachar" / verde fluorescente "✔ Despachado") y el botón amarillo "🛒 Generar compra" ya venían en el ZIP de las 18:31 (sección 21). Hay que subir este ZIP a Render.

### 22.8 Pruebas

- 200/200 pruebas correctas (5 nuevas: guía, factura, OC y despacho duplicados, y pantallas).
- Probado en pantalla: tarjetas en una fila, columnas cliente → RUC, despacho duplicado bloqueado, OC con N° PC / N° cotización, OC impresa con el PC, cartel "¿Ahora qué?". Capturas en `capturas-20oct-2254/`.

### 22.9 Archivos que cambiaron

- `routes/ventas.py`: bloqueos de guía, factura y despacho duplicados.
- `routes/compras_flujo.py`: bloqueo de OC duplicada y PC en la OC impresa.
- `static/js/compras_flujo.js`: carteles "¿Ahora qué?", PC en la orden, columnas N° PC / N° cotización.
- `static/js/ventas.js`, `static/js/compras.js`, `static/js/maestros.js`: orden cliente → RUC, "Generar rótulo", ventana roja de duplicado.
- `templates/base.html`: tarjetas en una fila.
- `templates/compras/imprimir_oc.html`, `templates/compras/flujo.html`, `templates/compras/index.html`, `templates/ventas/index.html`, `static/css/compras_flujo.css`.
- "Nr°" → "N°" en todos los templates y JS.
- `migrations/014_documentos_sin_duplicados.sql`.
- Pruebas: `tests/test_zz_zz_20oct_zduplicados.py` (nueva), `tests/test_zz_compras.py`, `tests/test_zz_zz_19oct_bugs.py`.

## 23. Pedidos por comprar: por defecto solo lo pendiente (21/10/2026)

Pregunta de Erika: en Compras ▸ Pedidos por comprar aparecían pedidos que ya tenían orden de compra (ej. PC-KCF-000004, Protector solar: pide 50, 25 ya en orden y 25 en stock), y el comprador podía pensar que faltaba comprar.

**Por qué estaba así:**
- La lista mostraba todo pedido al que le faltara orden de compra, pero no restaba el stock al decidir si mostrarlo. El PC-KCF-000004 salía aunque la orden (25) y el stock (25) ya cubrían los 50.
- Además, en la captura estaba marcado "Ver también los ya comprados", que muestra todo a propósito.
- La columna "Ya en órdenes" existe para no comprar dos veces lo mismo: resta lo que ya está pedido al proveedor antes de calcular "Comprar para pedido".

**Cambio:**
- Por defecto solo salen las líneas que de verdad falta comprar (ni en orden ni en stock). Las cubiertas se ocultan y el pedido dice "✔ N producto(s) ya están cubiertos (con orden de compra o stock) y no se muestran".
- El check ahora dice "Ver también lo ya cubierto (con orden o stock)". Viene desmarcado y el navegador no lo recuerda marcado. Sirve solo para consultar, y las líneas cubiertas muestran "✔ Cubierto".
- "Hoy en Compras" cuenta solo los pedidos con algo por comprar.
- Sin cambios en Supabase. 201/201 pruebas.
- Archivos: `routes/compras_flujo.py`, `static/js/compras_flujo.js`, `templates/compras/flujo.html`, `static/css/compras_flujo.css`, `tests/test_zz_zz_20oct_zduplicados.py`.


## 24. Correlativos, permisos reales, limpieza de datos de prueba, Finanzas por colores y menú en acordeón (21/10/2026, 16:35, 17:12 y 17:22)

### 24.1 Lo que tienes que hacer tú
1. Subir este ZIP a Render (reemplaza al de las 16:05).
2. **Hellen ahora ve solo lo que tiene marcado.** En KCF tiene Cuentas por cobrar y Caja/Bancos, así que solo ve Finanzas. Si debe validar cotizaciones o ver Ventas, márcale "Cotizaciones" en Configuración ▸ Usuarios y permisos.
3. Corregir las cuentas bancarias de relleno de 12 proveedores (lista en 24.8).
4. Decidir lo que quedó sin borrar (24.4).

### 24.2 Entregas y Pedidos por comprar
- Botones de acción de Entregas sin emojis, delgados y en una sola línea.
- Pedidos por comprar: si la línea ya tiene una OC activa, dice "✅ OC ya generada: OC-…" y su casilla queda bloqueada para no comprar dos veces.

### 24.3 Configuración ▸ Correlativos (nuevo)
- Muestra el último número emitido y el siguiente de: Cotización (una sola numeración para KCF y AGD), PC (por empresa), Guía y Factura/Boleta (por empresa y serie). La OC se muestra pero no se edita: se numera por día (OC-AAAAMMDD-NNNN).
- Solo el administrador entra. Al cambiar, el sistema pide confirmación.
- El número debe ser **mayor** que el último emitido. Si no, sale en rojo: "El número debe ser mayor que el último emitido". Los documentos ya emitidos nunca se renumeran; el cambio solo afecta a los nuevos.
- Cada cambio queda en Papelera ▸ Historial de cambios con quién, cuándo, antes y después.
- Ojo con las guías: las guías se generan con número por fecha (G-AAAAMMDD-NNNN). El correlativo de guías solo se aplica si alguien guarda una guía con el N° vacío.
- Bug escondido corregido: al duplicar una cotización, el número se sacaba contando filas (podía repetir un número). Ahora toma el mayor número y respeta el correlativo.

### 24.4 Permisos que de verdad limitan (bug crítico)
- **Causa:** Hellen (hel02kcf) tiene en la tabla `usuarios` el rol de sistema "administrador" (para poder aprobar cotizaciones). El ERP tomaba ese rol para decidir quién es administrador y por eso le mostraba todo, aunque en Usuarios y permisos tenía solo 2-3 casillas.
- **Ahora:** administrador = solo quien tiene el rol ERP "GERENCIA_TOTAL" (o un rol marcado como administrador). Los demás ven en el menú solo los módulos con "Ver" en la empresa activa.
- Si alguien escribe la dirección de otro módulo, el servidor lo devuelve al inicio con un aviso rojo; si es una consulta interna, responde "sin permiso" (403). Configuración queda solo para administradores.
- Hellen sigue pudiendo aprobar lo que aprobaba (su rol de sistema no cambió).
- Luis (luis01kcf) y Despacho (desp01kcf) también verán solo lo marcado.
- No se cambió ningún permiso en Supabase: se corrigió cómo el ERP los lee.

### 24.5 Limpieza de Supabase (con tu autorización escrita de las 16:35)
**Respaldo previo:** esquema `respaldo_20261021`, con copia completa de cada tabla tocada (ordenes_compra, orden_compra_detalle, comprobantes_proveedor, finanzas_pagos, proveedores, proveedores_contactos, proveedores_puntos_entrega) y de las 7 tablas vacías.

**Borrado (19 filas en total):**

| Tabla | Filas | Cuáles y por qué |
|---|---|---|
| ordenes_compra | 2 | id 5 "OC-TEST-001" e id 7 "OC-20260713-0001": nota "Orden de compra de prueba", sin productos ni recepciones |
| orden_compra_detalle | 1 | id 3: el detalle de la OC-TEST-001 |
| comprobantes_proveedor | 2 | id 1 y 2: "PROVEEDOR DE PRUEBA S.A.C." F001-00000001 |
| finanzas_pagos | 3 | id 1 y 4: pagos a ese proveedor de prueba; id 3: cobro ya anulado de una factura que ya no existe (huérfano) |
| proveedores_contactos | 3 | id 3, 18, 19: contactos de los proveedores de prueba |
| proveedores_puntos_entrega | 4 | id 3, 4, 19, 20: direcciones de los proveedores de prueba |
| proveedores | 4 | id 10 "EMPRESA TEST PROVEEDOR" (RUC 12345678901), id 22 "xxxxxxxxxxxxx", id 34 y 35 "PROVEEDOR TEST OK". Los 4 inactivos y sin compras |

**No se borró (tú decides):**
- Duplicados de la sección 22.6: tienen número, stock o documentos enlazados. En especial PC-KCF-000002 tiene dos despachos de 10 (DESP-20261020-0001 y -0002) y el PC pide 10: se recomienda anular el -0002 desde Entregas.
- Comparativo CMP-20260713-0001 (laptops): parece de ejemplo, pero no dice "prueba".
- Guía T001-32132995: cliente real con textos "prueba1" y "prueba 2".
- 3 cuentas de acceso sin ficha de usuario (est01kcf@kcf.com, eri01kcf@kcf.com y hel02kcf) y sus 142 filas de permisos: pueden ser de prueba, pero son accesos.
- Documentos anulados: no se borran, son el historial de auditoría.
- 7 tablas vacías que el ERP no usa (erp_alertas, listas_precios, logs_auditoria, movimientos_inventario, movimientos_stock, recuentos_inventario, revalorizaciones_inventario). Ya están respaldadas; la conexión se cuelga con DROP. **Opcional**, en el SQL Editor:
  `DROP TABLE IF EXISTS public.erp_alertas, public.listas_precios, public.logs_auditoria, public.movimientos_inventario, public.movimientos_stock, public.recuentos_inventario, public.revalorizaciones_inventario;`

**Agregado en Supabase:** tabla `erp_numeracion` (migración 015) y columna `finanzas_pagos.fecha_aviso` (migración 016), las dos con respaldo previo.

### 24.6 Finanzas con colores que se entienden
- Cobros (dinero que entra, clientes) en **verde azulado**; pagos (dinero que sale, proveedores) en **morado**; vencido en rojo encendido; cobrado/pagado en verde fluorescente. Hay una leyenda de colores arriba.
- Tarjetas, pestañas, encabezados de tabla, tipo de movimiento y barras del flujo de caja usan esos mismos colores.
- Montos y botones no se parten en dos líneas.
- Todas las tablas del ERP quedan centradas.
- Pie del rótulo con el CSS exacto que mandaste.

### 24.7 Pedido de las 17:12
- **Registrar cobro:** nuevo campo "Fecha de aviso de pago". Si el cobro es por transferencia, depósito o Yape/Plin, basta con el N.º de operación **o** la fecha de aviso (lo que mande el cliente). En efectivo no pide ninguno.
- **Cobros y pagos:** buscador por N° de documento, cliente/proveedor, RUC, N.º de operación o banco.
- **Cuentas por pagar:** las 4 tarjetas (Vencido, Por vencer, Al día, Total) ahora tienen el mismo tamaño y estilo que las de arriba.
- **"N. crédito":** no era un error. Es el monto de **notas de crédito** que bajan el saldo de esa factura. La columna se llama ahora "Nota de crédito (S/)" y al pasar el mouse lo explica. La de retención se llama "Retención (S/)".
- **Menú lateral en acordeón (prompt de Adriel):** Finanzas, Reportes, Herramientas y Papelera se abren como Compras, con iconos, el módulo activo en rosado con línea roja y la opción activa marcada. Después de recargar la página sigue abierto en la misma opción. Sin cambios en Supabase.

### 24.8 Pedido de las 17:22: "Pagar a" un dato por línea
- En Compras ▸ Registrar pago y en Finanzas ▸ Registrar pago/cobro, el recuadro ahora es una ficha con un dato por línea y siempre en el mismo orden: **Proveedor, RUC / DNI, Banco, N° de cuenta, CCI, Monto a pagar (incluye IGV)** y Falta pagar (rojo si falta, verde si ya está). En cobros: Cliente, RUC / DNI, N° factura, Total (incluye IGV) y Falta cobrar.
- En pagos ya no se pide "fecha de aviso" (eso es de cobros).
- **Cuentas de relleno:** si la cuenta o el CCI tienen números repetidos, la ficha muestra un aviso rojo para confirmarlos antes de pagar. Estos 12 proveedores tienen cuentas que parecen de relleno; **no se tocaron** (los proveedores son reales). Corrígelos en Maestros ▸ Proveedores:
  ALIMENTOS POLAR PERU S.A.C. (cuenta 11111111111111000000, CCI 222222222222200000), COMPARTAMOS BANCO S.A., STEAM PERU SERVICIOS GENERALES E.I.R.L., COMPAÑIA CERVECERA AMBEV PERU S.A.C., SAN FERNANDO S.A., DIRECCIÓN DE ECONOMÍA Y FINANZAS PNP, LECHE GLORIA S.A., CONFECCION TEXTIL SOTO S.A.C. y FRANQUICIAS ALIMENTARIAS S.A. (cuenta 5555444488889999 y/o CCI 111111111111111), CENFER PERU A & G S.A.C. (cuenta 122222222222222), NYTRO STORE S.A.C. (CCI 111111111111111) y SNACKS AMERICA LATINA S.R.L. (cuenta 122222222222222, CCI 123123123123123).

### 24.9 Pruebas y archivos
- Pruebas automáticas: 211 pasan en la base principal; en la base reconstruida 209 pasan y 2 se saltan (no tienen datos de ejemplo).
- Probado en el navegador: menú de Hellen, URL directa bloqueada, Correlativos (cambio y rechazo de número menor), Entregas, Pedidos con OC, Finanzas por colores, Registrar cobro y pago, menú en acordeón con recarga.
- SQL: `SUPABASE_015_correlativos_y_limpieza_prueba.sql` y `SUPABASE_016_finanzas_fecha_aviso_pago.sql` (ya aplicados). La próxima migración es la 017.
- Archivos: `main.py`, `utils.py`, `pdf_generator.py`, `routes/acceso.py` (nuevo), `routes/numeracion.py` (nuevo), `routes/correlativos.py`, `routes/ventas.py`, `routes/finanzas.py`, `routes/compras_flujo.py`, `templates/base.html`, `templates/correlativos.html`, `templates/finanzas.html`, `templates/ventas/index.html`, `static/css/finanzas.css`, `static/css/compras_flujo.css`, `static/js/finanzas.js`, `static/js/ventas.js`, `static/js/compras_flujo.js`, `static/js/herramientas.js`, `static/js/papelera.js`, `static/js/reportes.js`, `migrations/015_…sql`, `migrations/016_…sql`, `tests/test_zz_zz_21oct.py` (nuevo), `tests/test_flujos.py`, `tests/test_stock_automatico.py`.

### 24.10 Cuentas por pagar y por cobrar con detalle (21/10/2026, 18:38)
**Lo que tienes que hacer tú:** corregir el vencimiento de la factura **F001-000003 de CONFECCION TEXTIL SOTO S.A.C.** Vence el 25/04/2136 porque su orden **OC-20261019-0004** se registró con "Crédito 40000 días". No lo cambié porque es un dato real. Se corrige con el botón 📅 de esa fila en Cuentas por pagar.

**Cada fila ahora dice a qué compra o venta pertenece.** Todo se toma de Compras y Ventas, sin escribir nada dos veces.

| Cuentas por pagar | Cuentas por cobrar |
|---|---|
| N°, Proveedor, RUC / DNI | N°, Cliente, RUC / DNI |
| N° factura del proveedor (con tipo y fecha de emisión) | N° factura de venta (con tipo y fecha de emisión) |
| N° OC y debajo el N° PC relacionado ("Compra a stock" o "Sin PC vinculado" si no tiene) | N° PC y debajo el N° OC del cliente |
| Nombre producto: el primero con su cantidad y "+N más" desplegable | Igual, con los productos de la factura |
| Vencimiento con los días de atraso o los que faltan (📅 para cambiarlo) | Vencimiento con los días |
| Monto a pagar (S/ o $ según la moneda) | Monto a cobrar, y debajo la retención y la nota de crédito |
| Pagado, y debajo el **adelanto**: lo pagado en Compras antes de registrar la factura | Cobrado |
| Saldo | Saldo |
| **Estado:** ⏳ Pendiente (rojo), ◐ Pago parcial (amarillo), ✔ Pagado (verde fluorescente) | ⏳ Por cobrar, ◐ Cobro parcial, ✔ Cobrado |
| **Fecha real de pago**: el día del último pago, cuando ya se pagó todo. Si falta, dice "Último abono" | Fecha real de cobro |
| **Comentario** de Finanzas (✏️ para escribirlo). Debajo, en gris, la observación con la que Compras registró la factura | Comentario |

- Ejemplo real: YATAKI (F001-00155547) tiene S/ 900 pagados de S/ 983. Ahora dice "◐ Pago parcial" y no solo "Al día".
- La fila se pinta rosada si está vencida y verde clara si ya está pagada o cobrada. La tabla entra completa en la pantalla, sin barra para mover a los lados.
- El CSV exportado trae las mismas columnas.
- Moneda: las órdenes de compra y las facturas de proveedor no guardan moneda en la base, así que Cuentas por pagar sale en S/. En ventas se usa la moneda de la factura.
- El comentario se guarda aparte y no cambia la factura ni lo que se imprime.

**Vencimientos absurdos bloqueados:**
- Al crear una OC, los días de crédito deben estar entre 1 y 360.
- No se registra la factura de una OC que tenga más de 360 días de crédito.
- El 📅 de Cuentas por pagar no acepta un vencimiento anterior a la emisión ni más de 400 días después de ella.

**Supabase:** migración `SUPABASE_018_finanzas_comentarios.sql`, ya aplicada. Solo agrega la tabla `finanzas_comentarios`; no cambia ni borra datos. La 017 queda para el módulo SUNAT.

**Pruebas:** pasan 213 en la base principal; en la reconstruida pasan 211 y se saltan 2. La prueba vieja que ponía un vencimiento al 2030 ahora espera el rechazo.

**Archivos:** `routes/finanzas.py`, `routes/compras_flujo.py`, `templates/finanzas.html`, `static/js/finanzas.js`, `static/css/finanzas.css`, `migrations/018_finanzas_comentarios.sql`, `tests/test_zz_zz_21oct.py`, `tests/test_flujos.py`.

---

## 25. Módulo nuevo "8.1 ─ SUNAT e impuestos" (21/10/2026, pedido de Erika de las 18:21)

> **Todo lo que muestra es un cálculo preliminar.** Sirve para planificar y para revisar la hoja del contador. Quien declara y paga es el contador.

### 25.1 ¿Dónde va? Es un módulo aparte, no va dentro de Reportes
- Los impuestos son información delicada: solo los ve el administrador o quien tenga marcado **SUNAT** en Configuración ▸ Usuarios y permisos. Antes, quien veía Reportes veía también SUNAT. Ahora no.
- Tiene datos que se escriben a mano (retenciones, saldos, planilla) y pagos con check. Eso no es un reporte, es un módulo de trabajo.
- **Para que Hellen lo vea:** márcale "SUNAT" (Ver) en KCF y AGD. No se lo di yo.

### 25.2 Las 5 pestañas
1. **Resumen de impuestos.** Por empresa y por mes. Muestra:
   - cuántas facturas de venta y de compra, notas de crédito y notas de débito
   - la base y el IGV de ventas
   - el crédito fiscal
   - saldo a favor, percepciones y retenciones (del mes y del mes anterior)
   - IGV a pagar **a hoy** y **al cierre** (como si hoy fuera 31)
   - renta mensual (1 % en el Régimen MYPE), EsSalud y ONP
   - total a SUNAT y fecha de vencimiento

   La parte "Si hoy fuera fin de mes" suma lo que falta: guías sin factura, despachos por salir, OC sin factura del proveedor, PC por comprar, y ventas y compras escritas a mano. Cada línea tiene un check para sumarla o no.
2. **Plan de acción.** Va de lo más urgente a lo menos urgente:
   - rojo = hazlo ya
   - amarillo = antes del cierre
   - celeste = para decidir

   Cubre: guías entregadas sin factura (se facturan sí o sí), compras recibidas sin factura, pagos en efectivo de S/ 2,000 o más (bancarización), qué PC comprar y qué OC facturar antes del 31, entregas que se pueden pasar al día 1 (solo si aún no salieron), si conviene comprar para stock (con cuánto dinero sale de caja), la devolución de retenciones, las ventas intercompany y las reglas para que el crédito fiscal valga. Solo sugiere cosas legales: lo ya entregado se factura, y las ventas entre empresas van a valor de mercado.
3. **Preliminar vs contador.** Tiene las mismas filas que la hoja del contador (PDT 621 y PLAME, con notas de crédito y de débito). Se sube su Excel y el ERP marca en rojo lo que no cuadra. Se puede descargar en Excel.
4. **Pagos del mes.** Lista AFP, detracciones, EsSalud, ONP, renta de 5.ª y 4.ª, renta mensual, IGV, PDT 621, sueldos, y CTS o gratificación cuando tocan. Las fechas salen del cronograma SUNAT 2026 según el último dígito del RUC (KCF 4, AGD 1). La AFP vence el 5.º día hábil. Cada línea tiene "Marcar pagado" y "No aplica". Para desmarcar algo pagado hay que escribir un motivo, y queda registrado quién y cuándo.
   - Si la hoja del contador del mes ya está subida, los montos salen de su hoja.
   - Si no está, el ERP no pone "No aplica" por su cuenta: un cero puede ser solo que faltan datos.
5. **Completar datos.** Sirve para subir la propuesta SIRE (RVIE y RCE en .txt o .zip) o el Excel de las chicas con la plantilla. Primero se ve una vista previa. Lo que ya está en el ERP no se cuenta dos veces. Lo importado no cambia las ventas ni las compras del ERP. Si subiste un archivo equivocado, se puede quitar.

### 25.3 Lo que encontré en la hoja del contador (SET 2026, KCF)
- **Su total (S/ 1,428) no incluye la ONP (S/ 1,105).** La ONP también se paga en el PLAME. Pregúntale si la paga aparte.
- **KCF tiene S/ 13,780.63 de retenciones sin usar.** Si ese saldo se mantiene 3 meses seguidos, se puede pedir la devolución (Formulario 1649). SUNAT responde en hasta 45 días hábiles.
- Su tabla de vencimientos es la de 2025. Para setiembre la fecha coincide (21/10), pero para octubre diría 18/11 y la fecha real es **19/11/2026**.
- En el arrastre de abril a mayo hay una diferencia de S/ 1.36 (11,993.36 contra 11,992).
- **Vencimientos de setiembre:** KCF vence **hoy, 21/10**. AGD venció el **19/10**.

### 25.4 Por qué AGD paga IGV y KCF casi nunca
Las ventas entre las dos empresas pasan el IGV de una a otra. KCF acumula retenciones que no llega a usar, y AGD paga IGV en efectivo. Una opción legal, para revisar con el contador y siempre a valor de mercado, es ordenar las ventas intercompany para que KCF use sus retenciones.

### 25.5 Datos incompletos
Hoy el ERP tiene apenas una parte de las facturas. En setiembre, KCF tiene una base de S/ 120 en el ERP y S/ 54,564.32 en la hoja del contador. El módulo lo dice en rojo arriba. Lo más exacto es subir cada mes la propuesta del SIRE en "Completar datos".

### 25.6 Corregido al probar con una copia local de los datos reales
- El plan de AGD mostraba guías, OC y despachos de KCF porque el filtro por empresa no se aplicaba a esas consultas. Ya está corregido y tiene su prueba.
- En "Completar datos" no se veía el botón para elegir el archivo, por un estilo general del ERP. Ya se ve.
- AGD salía "IGV: No aplica" en setiembre solo porque el ERP no tiene sus facturas. Ahora queda Pendiente hasta que se suba la hoja del contador o se escriba el monto.

### 25.7 Para después
- **Compensaciones:** quedó para otro pedido, como dijiste.
- Confirmar con el contador el régimen de AGD. Hoy se asume Régimen MYPE (1 %). Se cambia en Completar datos ▸ Régimen.

### 25.8 Supabase, pruebas y archivos
- **Supabase:** `SUPABASE_017_sunat_impuestos.sql`, **ya aplicada**. Solo crea 4 tablas nuevas (`sunat_config`, `sunat_periodos`, `sunat_registros`, `sunat_obligaciones`), con RLS y sin acceso para anon/authenticated. No cambia ni borra datos. La app también crea las tablas sola si faltan.
- **Pruebas:** pasan 225 en la base principal (las 213 de antes más 12 nuevas). En la base reconstruida pasan 223 y se saltan 2.
- **Archivos nuevos:** `routes/sunat.py`, `templates/sunat.html`, `static/js/sunat.js`, `static/css/sunat.css`, `migrations/017_sunat_impuestos.sql`, `tests/test_zz_zz_zz_sunat.py`.
- **Archivos cambiados:** `main.py` (registra el módulo), `routes/acceso.py` (permiso propio), `templates/base.html` (menú, migas y permiso).

### 25.9 SUNAT más limpio, con el orden del cuadro del contador (21/10/2026, 22:02, 22:06 y 22:12)
- **Menos texto.** Se quitaron los párrafos de ayuda. Arriba quedan 5 tarjetas del mismo tamaño: Ventas, Compras, IGV hoy, IGV al 31 y Total SUNAT con su vencimiento. Lo que es opcional (saldos, percepciones, planilla y la lista de comprobantes) está plegado y se abre con un clic.
- **Resumen IGV y renta en el orden y con los colores del cuadro del contador:**
  - gris: Ventas y Compras (base), 101 IGV ventas y 108 IGV compras
  - rojo: 140 Impuesto resultante, 145 Saldo a favor anterior y 184 Tributo del mes
  - gris oscuro: 10 Retenciones del periodo, 5 Retenciones de periodos anteriores y 20 Saldo de retenciones no aplicadas
  - verde o rojo: IGV a pagar
  - celeste: Renta proyectada y Pago real de renta (voucher)
  - turquesa: IGV pagado (voucher)

  Cada fila tiene la columna "Hoy" y la columna "Al 31 (proyección)".
- **Lo único que se escribe a mano son las retenciones del mes,** en un recuadro al lado del total. Todo lo demás sale solo de Ventas y Compras. El saldo de retenciones del mes anterior también se calcula solo.
- **Plan de acción al final del resumen.** Muestra las 3 acciones más urgentes. En su pestaña, cada tarjeta lleva título, monto, IGV y botón; la explicación está en "Ver detalle".
- **Trazabilidad de pagos.** Para marcar un pago como "Pagado" ahora se pide el monto y el N° de operación o NPS del voucher (en sueldos, CTS y gratificación el N° es opcional). La tabla muestra en una columna la fecha de pago, el N° de operación y quién lo marcó. El candado para desmarcar sigue igual. El resumen muestra el monto pagado del IGV y de la renta, o "Falta pagar" con su fecha de vencimiento.
- **Pruebas:** pasan 226 (2 nuevas: el N° de operación es obligatorio y el resumen trae el voucher). En la base reconstruida pasan 224 y se saltan 2.

---

### 25.10 Cuadro de IGV paso a paso y total a pagar a SUNAT (22/10/2026, pedido de Erika de las 23:04)

- **"IGV del mes, paso a paso"** reemplaza al cuadro de colores. Es blanco, sobrio y alineado a la izquierda, con montos a la derecha y dos columnas: "Hoy" y "Al 31".
  1. **IGV de tus ventas:**
     - IGV de facturas y boletas, con la base imponible debajo
     - (−) Notas de crédito emitidas
     - (+) Notas de débito emitidas
     - **= IGV de ventas**: casilla 101, "el IGV que cobraste a tus clientes".
  2. **IGV de tus compras (crédito fiscal), en negativo:**
     - (−) IGV de facturas de compra
     - (+) Notas de crédito recibidas
     - (−) Notas de débito recibidas
     - **= IGV de compras**: casilla 108.
  3. **Cálculo del IGV del mes:**
     - Impuesto resultante: casilla 140
     - (−) Saldo a favor anterior: casilla 145
     - **= IGV del mes, sin retenciones**: casilla 184, la única fila sombreada en rojo, "lo que pagarías si no tuvieras retenciones"
     - (−) Percepciones, que solo aparecen si hay
     - (−) Retenciones que se usan. La nota dice cuántas tienes, del mes y de meses anteriores.
     - **IGV A PAGAR, DESPUÉS DE RETENCIONES**: la cifra clave. Va en rojo si hay que pagar y en verde fluorescente si sale 0.
     - Retenciones y saldo a favor que quedan para el próximo mes.
  - Las líneas en 0 se ven en gris claro, para que resalte lo que tiene monto.
- **"Total a pagar a SUNAT"** (con la fecha de vencimiento según el último dígito del RUC):
  - IGV a pagar (con "✔ Pagado" si ya hay voucher)
  - Renta mensual, con su tasa y régimen
  - EsSalud y ONP (y 5.ª o 4.ª categoría, si hay)
  - **= Total a SUNAT**
  - (+) AFP, si hay
  - **Caja que necesitas** a la fecha de vencimiento, hoy y al 31.
- Todo sale de Ventas, Compras y Planilla y se actualiza al registrar una factura o nota. Solo las retenciones se escriben a mano, en el recuadro de abajo.
- **SIRE:**
  - En "Completar datos" ya se pueden subir las propuestas de SIRE (RVIE de ventas y RCE de compras) para comparar con el ERP.
  - La descarga automática desde SUNAT es posible con la API del SIRE. Para eso Erika tendría que generar credenciales de API en Menú SOL, sin compartir su clave SOL por chat. Queda como paso siguiente si ella lo pide.
  - Las retenciones que te hacen tus clientes no vienen en el RVIE ni en el RCE, y no hay una consulta automática sencilla. Siguen siendo **un número al mes**, que se saca de SUNAT ▸ Consulta de comprobantes de retención. El ERP sugiere un monto con los cobros que tuvieron retención.
- El cuadro y el total llevan `data-sin-item`: son un cálculo paso a paso y no una lista, así que no llevan la columna "Ítem".
- Solo cambiaron templates/sunat.html, static/js/sunat.js y static/css/sunat.css. No hay migración nueva ni cambios en la base.

## 26. Módulo nuevo "7.1 ─ Conciliación bancaria" (21/10/2026, pedido de Erika de las 23:30)

### 25.11 Regímenes confirmados y notita mensual (22/10/2026, mensaje de Erika de las 19:00)

- **Regímenes que confirmó Erika.** Quedaron guardados en Supabase como configuración nueva, sin borrar ni cambiar ningún dato existente:
  - Tributario: **Régimen MYPE Tributario** en KCF y AGD, con renta mensual de 1% (tabla `sunat_config`). Con esto el resumen ya no dice "sin confirmar con el contador".
  - Laboral: **KCF = pequeña empresa** y **AGD = microempresa** (tabla `rrhh_config`). Antes la planilla tomaba "Régimen general" por defecto.
- **Pagos del mes:** debajo de la lista hay una notita fija, "📌 Cada mes, apenas cierra el mes", con 3 tareas:
  1. Subir la propuesta del SIRE (RVIE y RCE).
  2. Subir la hoja del contador.
  3. Escribir las retenciones.
  - Cada tarea lleva el enlace a su pestaña.
- **Pasos para el practicante** (subir a Render y dar el permiso SUNAT a Hellen en las dos empresas): ver `erp-entrega/PASOS_PRACTICANTE_23OCT.md`.
- **Compensaciones:** Erika las verá en otro lado. No se hizo nada en el ERP.

### 25.12 Cuadro de IGV en 3 bloques y casillas opcionales (25/10/2026, pedido de Erika de las 13:45)

- Erika no entendía las casillas (101, 108, 140...) y pidió más orden. El cuadro "IGV del mes, paso a paso" quedó en 3 bloques con nombres simples:
  1. **Lo que cobraste de IGV al vender:**
     - IGV de tus facturas y boletas (con el 18% de las ventas sin IGV debajo)
     - (−) Notas de crédito
     - (+) Notas de débito
     - **= IGV que cobraste**
  2. **Lo que pagaste de IGV al comprar:**
     - (−) IGV de tus facturas de compra
     - Notas de crédito y de débito de proveedores
     - **= IGV que pagaste (se descuenta)**
  3. **Lo que pagas a SUNAT por IGV:**
     - IGV que cobraste
     - (−) IGV que pagaste
     - (−) Saldo a favor del mes pasado, que solo aparece si hay
     - **= IGV del mes, sin retenciones**: fila en rojo claro
     - (−) Percepciones, que solo aparecen si hay
     - (−) Retenciones de tus clientes
     - **IGV A PAGAR**, con "Hasta el dd/mm, con el PDT 621" debajo
     - Retenciones o saldo a favor que sobran, solo si hay
- Arriba hay una línea de ayuda: "Pagas a SUNAT la diferencia entre el IGV que cobraste al vender y el que pagaste al comprar, menos lo que tus clientes ya te retuvieron."
- **Casillas del PDT 621:** ya no salen en el texto. Con la casilla "Ver casillas del PDT 621" aparece una columna gris con 101, 108, 140 · 184, 145, 171 y 179, para hablar con el contador. La elección se recuerda en ese navegador.
- Solo cambiaron templates/sunat.html, static/js/sunat.js y static/css/sunat.css. Sin migración ni cambios en la base. Pasan 301 pruebas, y 299 + 2 omitidas en el esquema reconstruido.
- 26/10/2026: SUNAT usa los nombres de todo el sistema: "Órdenes de compra (Proveedor) sin factura" y "PC (Pedido de compra) por comprar", en "Si hoy fuera 31" y en el plan de acción. Solo cambiaron textos en static/js/sunat.js y routes/sunat.py.

### 26.1 Para qué sirve
Saber quién pagó de verdad y detectar plata que entró o salió sin registrar. Se compara el extracto del banco con los cobros y pagos de Finanzas.

### 26.2 Cómo se usa (3 pasos)
1. En la banca por internet, baja los movimientos del mes en Excel o CSV.
2. En **7.1 ─ Conciliación bancaria**, pulsa **⬆ Subir extracto del banco**, elige el banco y el archivo.
3. Revisa lo que queda en rojo en **⚠ Por revisar**.

### 26.3 Qué hace solo
- **Lee el archivo tal como lo da el banco:** BCP, BBVA, Interbank, Scotiabank, BanBif, Banco de la Nación... Reconoce solo las columnas (Fecha, Descripción, N° de operación, Monto o Cargo/Abono, Saldo), aunque el archivo tenga títulos arriba. Acepta .xlsx, .xls, .csv y .txt.
- **No duplica:** si subes el mismo extracto dos veces, o dos extractos que se cruzan en fechas, cada movimiento entra una sola vez.
- **Concilia solo lo seguro:**
  - mismo monto y mismo N° de operación → ✔ Conciliado
  - mismo monto, fecha cercana (± 5 días) y una sola opción → ✔ Conciliado
  - ITF, comisiones y mantenimiento → "Gasto del banco"
- **Vuelve a intentar cada vez que abres la pantalla.** Si alguien registra después el cobro en Finanzas, se une solo.

### 26.4 Qué queda en rojo
- **🏦 En el banco, falta en el ERP:** plata que entró o salió y nadie registró. Al lado sale la posible coincidencia:
  - un cobro o pago ya registrado con monto parecido → botón **Unir**
  - una factura por cobrar o por pagar con ese saldo → botón **Registrar cobro / Registrar pago**. Registra el cobro en Finanzas con la fecha y el N° de operación del banco y lo deja conciliado en un clic.
  - nada → **Explicar** (por ejemplo "préstamo de socio" o "transferencia entre cuentas"). La nota es obligatoria.
- **🧾 En el ERP, no está en el banco:** cobros y pagos registrados (que no son en efectivo) que el banco no muestra en las fechas del extracto. Es la alerta principal contra robos o errores.

### 26.5 Controles
- **Permiso propio:** lo ve la gerencia y quien tenga marcada la columna **"Bancos"** en Configuración ▸ Usuarios y permisos. El botón "Registrar cobro / pago" solo sale a quien también puede operar en Finanzas.
- **Unir** un abono solo a un cobro, y un cargo solo a un pago. Si los montos no son iguales, pide una nota.
- **Deshacer** pide motivo. Lo deshecho ya no se une solo: queda para revisión manual.
- Todo guarda quién y cuándo (hora de Lima) y un historial por movimiento.
- **Quitar un extracto** subido por error: solo el administrador y con motivo. No toca los cobros ni pagos de Finanzas.

### 26.6 Supabase, pruebas y archivos
- **Supabase:** `SUPABASE_019_conciliacion_bancaria.sql`, **ya aplicada** el 21/10/2026. Crea 2 tablas nuevas (`bancos_extractos`, `bancos_movimientos`) con RLS y sin acceso para anon/authenticated, y agrega el permiso `CONCILIACION_BANCARIA` (1 fila en `erp_submodulos`). Respaldo previo: `respaldo_20261021.erp_submodulos_pre019`. No cambia ni borra datos.
- **Render:** se agregó `xlrd` a `requirements.txt` (para los .xls antiguos del banco). Render lo instala solo al subir el ZIP.
- **Pruebas:** pasan 235 (las 226 de antes más 9 nuevas: formatos de banco, permisos, conciliación automática, no duplicar, registrar desde el banco, unir a mano, deshacer y quitar extracto).
- **Archivos nuevos:** `routes/bancos.py`, `templates/bancos.html`, `static/js/bancos.js`, `static/css/gestion.css`, `migrations/019_conciliacion_bancaria.sql`, `tests/test_zz_zz_zz_zbancos.py`.
- **Archivos cambiados:** `main.py` (registra el módulo), `routes/acceso.py` y `routes/configuracion_seguridad.py` (permiso propio), `templates/base.html` (menú, migas y columna "Bancos" en permisos), `requirements.txt`.

---

## 27. Módulo nuevo "7.2 ─ Intercompany KCF ↔ AGD" (22/10/2026, pedido de Erika del 21/10 23:30)

### 27.1 Para qué sirve
Ver en una sola pantalla las ventas entre KCF y AGD, lo que se deben, el IGV de cada una con una sugerencia de desde qué empresa facturar, y el stock del grupo.

### 27.2 Qué muestra (todo sale solo, no se escribe nada)
- **Tarjetas:** ventas KCF → AGD y AGD → KCF del mes (sin IGV), facturas que faltan registrar como compra, lo que se deben (neto) y el stock del grupo valorizado.
- **📊 Ventas y deudas:**
  - cada venta entre empresas del mes: fecha, quién vende, quién compra, N° factura, montos. Se reconoce sola porque el cliente tiene el RUC de la otra empresa. Toma Ventas y también lo subido del SIRE en el módulo SUNAT, sin contar dos veces.
  - **control cruzado:** cada venta debe estar registrada como compra en la otra empresa. Si no está: "⏳ Falta en compras de AGD" en rojo, porque esa empresa pierde el crédito fiscal. Busca la compra hasta 2 meses después y reconoce "F001-00000201" igual que "F001-201".
  - **lo que se deben:** facturas entre empresas con saldo, con su vencimiento, y el neto ("AGD le debe a KCF S/ ...").
  - los últimos 6 meses por sentido.
- **🧮 IGV: desde dónde facturar:** el IGV del mes de cada empresa (el mismo cálculo del módulo SUNAT): IGV de ventas, de compras, a pagar, saldo a favor y retenciones sin usar. Debajo, la sugerencia:
  - si una empresa paga IGV y la otra tiene saldo sin usar: facturar desde la que tiene saldo las próximas ventas, hasta el monto que su saldo cubre; o que la que tiene saldo le venda a la otra mercadería que necesita, a valor de mercado.
  - si las dos pagan: mover ventas no ahorra nada.
  - si ninguna paga: no hace falta mover nada.
  - Las reglas legales (valor de mercado, guía, bancarización, devolución de retenciones) están plegadas.
- **📦 Stock del grupo:** por producto, cuánto tiene KCF, cuánto AGD y el total, con su valor. Buscador por código o nombre.
- **Aviso rojo arriba** si falta algo para que cuadre: KCF o AGD sin crear como cliente o proveedor en Maestros, o ventas entre empresas de Inventario sin N° de factura.

### 27.3 Lo que encontré en tu base real
- Todavía **no hay ninguna factura entre KCF y AGD en el ERP** (ni en Ventas ni en Compras ni en lo subido del SIRE).
- **KCF y AGD no están creadas como clientes ni como proveedores** en Maestros. Hay que crearlas para poder facturarse entre ellas desde el ERP. El módulo lo dice en el aviso rojo.

### 27.4 Permiso
Lo ve la gerencia y quien tenga marcada la columna **"Intercompany"** en Configuración ▸ Usuarios y permisos. Ver Finanzas no basta.

### 27.5 Supabase, pruebas y archivos
- **Supabase:** `SUPABASE_020_intercompany.sql`, **ya aplicada**. El módulo no crea tablas; solo se agregó el permiso `INTERCOMPANY` (1 fila en `erp_submodulos`). Respaldo previo: `respaldo_20261021.erp_submodulos_pre020`.
- **Pruebas:** pasan 242 (7 nuevas: permiso, ventas y control cruzado, deudas y neto, sugerencia de IGV, IGV en el resumen, stock del grupo y avisos). En la base reconstruida pasan 240 y se saltan 2.
- Nota para las pruebas: entre las 19:00 y las 24:00 de Lima, la prueba antigua `test_cuentas_por_cobrar_vencido_primero` falla por un día si la base de pruebas está en UTC. Con `PGTZ=America/Lima` pasan todas. No afecta al ERP.
- **Archivos nuevos:** `routes/intercompany.py`, `templates/intercompany.html`, `static/js/intercompany.js`, `migrations/020_intercompany.sql`, `tests/test_zz_zz_zz_zintercompany.py`. Estilos en `static/css/gestion.css`.
- **Archivos cambiados:** `main.py`, `routes/acceso.py`, `routes/configuracion_seguridad.py` (id 37), `templates/base.html` (menú 7.2, migas, columna "Intercompany").

## 28. Módulo nuevo "7.3 ─ Planilla y RRHH" (22/10/2026, pedido de Erika del 21/10 23:30)

### 28.1 Para qué sirve
Saber cada mes cuánto se le paga a cada persona (sueldo, subvención o recibo), qué falta pagar, las vacaciones, la próxima CTS y gratificación, y que todo eso llegue solo al módulo SUNAT.

### 28.2 Qué hace
- **El ERP no inventa sueldos.** Tú agregas a cada persona una sola vez con **+ Agregar persona**: nombre, DNI, tipo (Planilla / Practicante / Recibo por honorarios), cargo, fecha de ingreso, sueldo o subvención, ONP o AFP (con su %), asignación familiar, banco y N° de cuenta. La base real está **vacía**: no se cargó a nadie.
  - Valida que el sueldo no sea menor al mínimo (S/ 1,130), salvo que marques "Jornada parcial". Si es AFP, pide el % total.
  - Cada cambio queda en un historial con usuario y fecha y hora de Lima ("sueldo: 2000.00 → 2500.00").
- **💵 Pagos del mes:** una fila por pago. Bruto, descuento (ONP 13% o AFP), neto a pagar, EsSalud de la empresa (9%, nunca sobre menos del mínimo), banco y cuenta. Si entró o salió a mitad de mes, se calcula por días.
  - Practicantes: subvención sin descuentos; cada 6 meses, media subvención adicional.
  - Recibo por honorarios: retención de 8% si el recibo pasa de S/ 1,500.
  - En julio y diciembre aparece la **gratificación** (+ 9% de bonificación). En mayo y noviembre, la **CTS**.
  - Lo que falta pagar sale **"⏳ Por pagar" en rojo**. Con **Marcar pagado** se escribe el N° de operación (obligatorio), la fecha y el monto: queda **"✔ Pagado" verde fluorescente**. Desmarcar pide motivo.
- **Se conecta solo con SUNAT:** al abrir los pagos del mes actual o del anterior, la base de EsSalud, la base de ONP, la AFP, los sueldos y la renta de 4.ª se pasan a **SUNAT ▸ Pagos del mes** (la renta de 5.ª la sigue poniendo el contador). Los meses más antiguos no se tocan, porque ya los declaró el contador.
- **👥 Personal y vacaciones:** días ganados, tomados y pendientes (30 por año en régimen general; 15 en REMYPE y practicantes). Si pasó el año para tomarlas, sale en rojo ("vacaciones vencidas"). El botón **Vacaciones** registra las fechas y no deja cruzarlas.
- **🎁 CTS y gratificaciones:** cuánto toca a cada uno en la próxima CTS y gratificación, y qué practicante cumple 6 meses.
- **Avisos en rojo arriba:** régimen laboral sin confirmar, vacaciones vencidas, y personas que ganan más de 7 UIT al año (pedir al contador la renta de 5.ª).

### 28.3 Lo que falta de tu lado
1. **Confirmar el régimen laboral** de KCF y de AGD (general, pequeña o microempresa) con el contador y elegirlo en "cambiar". Por ahora se calcula como régimen general.
2. Agregar a cada persona con su sueldo real y su cuenta.
3. Darle el permiso **"Planilla"** solo a quien deba ver sueldos.

### 28.4 Permiso
Lo ve la gerencia y quien tenga marcada la columna **"Planilla"** en Configuración ▸ Usuarios y permisos. Ver Finanzas no basta. El régimen laboral solo lo cambia el administrador.

### 28.5 Supabase, pruebas y archivos
- **Supabase:** `SUPABASE_021_planilla.sql`, **ya aplicada**. Crea 4 tablas vacías (`rrhh_config`, `rrhh_personal`, `rrhh_vacaciones`, `rrhh_pagos`) con RLS y sin acceso público, más el permiso `PLANILLA`. Respaldo previo: `respaldo_20261021.erp_submodulos_pre021`. No se cargó ningún dato.
- **Pruebas:** pasan 249 (7 nuevas: permiso, cálculo del sueldo, gratificación/CTS/media subvención, validaciones, pagos y envío a SUNAT, marcar y desmarcar, vacaciones e historial). En la base reconstruida pasan 247 y se saltan 2. Las capturas usan personas y sueldos **inventados**, solo en una base local.
- **Hora de Lima:** Planilla, Conciliación bancaria e Intercompany ahora usan la fecha y hora de Lima aunque el servidor esté en UTC.
- **Archivos nuevos:** `routes/planilla.py`, `templates/planilla.html`, `static/js/planilla.js`, `migrations/021_planilla.sql`, `tests/test_zz_zz_zz_zplanilla.py`. Estilos en `static/css/gestion.css`.
- **Archivos cambiados:** `main.py`, `routes/acceso.py`, `routes/configuracion_seguridad.py` (id 38), `templates/base.html` (menú 7.3, migas, columna "Planilla"), `routes/bancos.py` y `routes/intercompany.py` (hora de Lima).

## 29. Módulo nuevo "4.1 ─ Seguimiento comercial" (22/10/2026, pedido de Erika del 21/10 23:30)

### 29.1 Para qué sirve
Que ninguna cotización enviada se quede sin respuesta: a quién llamar hoy, qué dijo el cliente la última vez, y cuánto cierra cada vendedora.

### 29.2 Qué hace (todo sale de Ventas)
- **Tarjetas:** llamar hoy (rojo), sin cerrar, monto sin cerrar, vigencia vencida, tasa de cierre del periodo y ganado este mes.
- **📞 Sin cerrar:** las cotizaciones **Generadas** (ya mandadas al cliente) sin respuesta, primero las que toca llamar. Cada fila: cliente, RUC, N° cotización (abre el PDF), fecha y vigencia, total, vendedora, contacto con teléfono, última llamada y próxima llamada.
  - Si nunca se llamó, la primera llamada es **3 días** después de hecha. Hoy o atrasada sale en **rojo**.
  - **Registrar llamada:** cómo (llamada, WhatsApp, correo, visita), qué dijo el cliente (obligatorio) y cuándo volver a llamar (por defecto en 3 días, no en el pasado).
  - Si el cliente no va a comprar: se marca **"No compró"** con motivo (precio alto, compró a otro, tiempo de entrega, ya no lo necesita, no responde, otro). La cotización en Ventas **no cambia**.
  - Plegadas abajo: las cotizaciones que aún no se mandan al cliente (borrador o por validar).
- **📊 Tasa de cierre:** por vendedora (enviadas, ganadas, perdidas, sin cerrar, tasa en %, monto cotizado y ganado, días promedio para cerrar), los últimos 6 meses y las perdidas con su motivo. Periodo: 30 días, 90 días, 6 meses o 1 año.
- **🗂 Historial de llamadas:** cada llamada con fecha y hora de Lima y quién la registró.
- **Reglas:** ganada = aceptada por el cliente, facturada o con PC. Perdida = rechazada o "No compró". Las anuladas no cuentan. Cuando el cliente acepta, se marca en Ventas o se crea el PC y sale sola de la lista.

### 29.3 Lo que encontré en tu base real
- Hay **6 cotizaciones sin cerrar**: 4 de KCF y 2 de AGD. Hay una séptima Generada de KCF, pero ya tiene PC y cuenta como ganada.
- Las 4 de KCF no tienen teléfono en la cotización. El módulo usa el teléfono del cliente en Maestros si existe; si no, dice "Sin teléfono".
- Todas las cotizaciones tienen como vendedora "Helen Blas Príncipe" (es el valor por defecto). Para ver la tasa por vendedora, cada cotización debe llevar su vendedora real.

### 29.4 Permiso
Lo ve la gerencia y quien tenga marcada la columna **"Seguimiento"** en Configuración ▸ Usuarios y permisos. Ver Cotizaciones no basta.

### 29.5 Supabase, pruebas y archivos
- **Supabase:** `SUPABASE_022_seguimiento_comercial.sql`, **ya aplicada**. Crea 1 tabla vacía (`ventas_seguimiento`) con RLS y sin acceso público, y el permiso `SEGUIMIENTO_COMERCIAL` en Ventas. Respaldo previo: `respaldo_20261021.erp_submodulos_pre022`. No cambia ninguna cotización.
- **Pruebas:** pasan 254 (5 nuevas: permiso, vigencia, situación y llamar hoy, tasa por vendedora, registrar llamada y "No compró"). En la base reconstruida pasan 252 y se saltan 2. Las capturas usan clientes y cotizaciones **inventados**, solo en una base local.
- **Archivos nuevos:** `routes/seguimiento.py`, `templates/seguimiento.html`, `static/js/seguimiento.js`, `migrations/022_seguimiento_comercial.sql`, `tests/test_zz_zz_zz_zseguimiento.py`. Estilos en `static/css/gestion.css`.
- **Archivos cambiados:** `main.py`, `routes/acceso.py`, `routes/configuracion_seguridad.py` (id 39), `templates/base.html` (menú 4.1, migas, columna "Seguimiento").

### 24.11 Pruebas automáticas con la hora de Lima (22/10/2026, 00:50)
- Entre las 19:00 y las 24:00 de Lima fallaban 3 pruebas: Reportes, filtros de Compras y Cuentas por pagar con detalle. El ERP sí trabaja con la hora de Lima (database.py hace SET TIME ZONE), pero las conexiones directas de las pruebas usaban UTC y caían en el día siguiente.
- Arreglo solo en las pruebas: `tests/conftest.py` fija PGTZ=America/Lima, y `test_zz_reportes.py` y `test_zz_zz_21oct.py` usan la fecha de Lima. El código del ERP no cambia y Supabase tampoco.
- Pasan 254 pruebas en la base principal. En la reconstruida pasan 252 y se saltan 2. Las corrí a las 19:50 de Lima.

### 24.12 Órdenes de compra: columnas, hoja para el proveedor y programa de transporte (22/10/2026, pedidos de Erika de las 09:01, 09:06 y 09:13)
- **Compras ▸ Órdenes de compra:** las últimas columnas ahora van en este orden: **Estado** (Por aprobar, Aprobada...), **Llegó mercadería** (barra con el %) y **Siguiente paso**.
- **Orden de compra impresa / PDF** (`templates/compras/imprimir_oc.html`):
  - La hoja es vertical (A4).
  - El título "ORDEN DE COMPRA" y su número salen más grandes.
  - Todo va en fondo blanco: se quitó el amarillo de la nota. Solo el encabezado de la tabla va en gris.
  - **Ya no sale el recuadro "Relacionado al PC" ni ningún N° interno** (PC, cotización del cliente). Esto reemplaza el pedido del 20/10 22:54, porque el proveedor podría ser también proveedor del cliente. Esos números siguen viéndose dentro del sistema, en la lista y en el detalle de la OC.
  - Tabla: Producto, Modelo, Marca, Unidad de medida, Cantidad, Precio unit. sin IGV y Total. Modelo y marca salen del catálogo de productos; si el producto no los tiene, la celda queda vacía.
  - Las condiciones y el texto "Facturar a... / guía... / Pagamos únicamente..." no cambian.
- **Compras ▸ Recibir mercadería:**
  - "🚚 Recogemos" sale en azul y resaltado.
  - Debajo hay una lista "¿Quién recoge?" (en rojo mientras no tiene responsable). Al elegir a alguien se guarda quién lo asignó y la fecha y hora de Lima.
  - Pueden asignar Compras, Almacén y la supervisora.
  - Si la OC la entrega el proveedor, el sistema no deja asignar.
- **Botón "🚚 Programa de transporte"** (`/compras/flujo/programa_transporte`):
  - Junta las OC aprobadas que nosotros recogemos y que aún no llegan completas, ordenadas por fecha prometida.
  - Cada fila trae: responsable (o SIN ASIGNAR en rojo), proveedor con RUC y teléfono, N° OC, dirección de recojo, productos y cantidades que faltan recoger, sede donde se lleva, estado y una columna para la firma.
  - Las OC al contado sin pagar dicen "🔒 Falta el pago: no recoger".
  - Se imprime o se guarda como PDF (hoja horizontal), o se descarga en Excel (CSV).
  - El cliente no sale en el programa.
- **Base de datos:** migración `023_responsable_recojo.sql`, **aplicada en Supabase el 22/10/2026**. Solo agrega 4 columnas vacías a `ordenes_compra` (responsable_recojo_id, responsable_recojo, responsable_recojo_por, responsable_recojo_en). No cambia ni borra datos.
- **Hoy en la base real:**
  - Hay 2 OC aprobadas por recoger: OC-20261019-0008 (PROMPERU) y OC-20261021-0003. Las dos aparecen en el programa.
  - OC-20261021-0005 sale cuando la aprueben.
  - Sus productos sí tienen modelo y marca.
- **Pruebas:** pasan 255 en la base principal. En la reconstruida pasan 253 y se saltan 2. Hay una prueba nueva para el responsable y el programa, y se actualizaron las 2 que pedían "Relacionado al PC" en la hoja.

### 24.13 Finanzas más compacta: un solo resumen por pestaña (22/10/2026, pedido de Erika de las 09:42)
- Se quitaron las 6 tarjetas grandes de arriba (Por cobrar, Cobranza vencida, Por pagar, Pagos vencidos, Cobrado este mes, Posición neta). También se quitaron la fila de leyenda de colores, las 4 tarjetas de Cuentas por pagar y el texto "Orden: primero lo vencido...".
- En su lugar, **Cuentas por cobrar** y **Cuentas por pagar** tienen cada una **una sola fila delgada** encima de la tabla:
  - Muestra 🔴 Vencido · Por vencer (7 días) · Al día · Total, con el monto y entre paréntesis cuántos documentos son.
  - Cada número sale una sola vez.
  - Al final de la fila: "Cobrado este mes" o "Pagado este mes".
  - **Al hacer clic en un estado, la tabla muestra solo esos documentos.**
- Colores:
  - El rojo solo aparece si de verdad hay algo vencido; si está en cero, queda gris.
  - El total va en verde azulado (cobros) o morado (pagos).
- La "Posición neta" pasó a la pestaña Flujo de caja.
- Las explicaciones que se quitaron siguen disponibles al pasar el mouse: pestañas, título y columna Vencimiento.
- El servidor ahora también manda los totales de Cuentas por cobrar (`/finanzas/api/cxc` → `totales`). No hay cambios en Supabase.
- Ahora la tabla empieza unos 300 px más arriba.
- Pasan 256 pruebas en la base principal. En la reconstruida pasan 254 y se saltan 2.

### 24.14 Matriz de permisos, correlativos con doble confirmación y estados de Compras (22/10/2026, pedidos de Erika de las 10:26 y 10:32)
- **Configuración ▸ Usuarios y permisos:**
  - La tabla de usuarios ya no tiene 17 columnas de checks. Cada usuario muestra un resumen de los módulos a los que entra, con chips de color:
    - verde: Acceso total;
    - azul: Solo lectura;
    - amarillo: tiene solo una parte del módulo.
  - El botón **🛡 Permisos** abre la **matriz**: una fila por módulo y 3 columnas (Sin acceso, Solo lectura, Acceso total).
    - Marcar el módulo aplica el mismo nivel a todas sus funciones. Con ▸ se ajusta cada función por separado; si quedan distintas, el módulo dice "Personalizado".
    - Los módulos salen de la base (`erp_modulos` / `erp_submodulos`), así que un módulo nuevo aparece solo en la matriz.
  - Dashboard, Configuración, Herramientas y Papelera aparecen como filas fijas que explican quién las ve:
    - Dashboard lo ven todos.
    - Configuración y Herramientas solo el administrador.
    - En la Papelera cada uno ve lo que borró; restaurar e historial son solo del administrador.
  - **Qué hace cada nivel:**
    - Sin acceso: no ve el módulo, y el servidor bloquea la URL (como con Hellen).
    - **Solo lectura: ve y exporta. El servidor ahora no deja grabar** (`routes/acceso.py` → `bloqueo_solo_lectura`, mensaje "Tienes ... en «Solo lectura»").
    - Acceso total: ve, crea, edita, aprueba y anula. Los candados de rol (aprobar OC, anular, ajustar stock) siguen igual.
  - Para grabar en Maestros y Productos basta con Acceso total en Ventas o Compras, porque se crean clientes y proveedores desde allí.
  - Se arregló `/api/config/modulos`, que fallaba porque pedía columnas `created_at` que no existen en Supabase.
- **Supabase, migración `024_matriz_permisos.sql`** (aplicada el 22/10/2026, respaldo en `respaldo_20261022`):
  - Corrige 37 nombres de funciones; antes varias se llamaban igual: "Configuración", "Compras", "Reportes".
  - Hasta hoy, "Ver" igual dejaba grabar. Para que nadie se quede bloqueado de golpe, los permisos que tenían solo "Ver" pasaron a Acceso total. Eso afecta a hel02kcf y est01kcf en AGD (Finanzas y Reportes), y al rol OPERATIVO en Inventario y Productos.
  - Desde ahora, "Solo lectura" se marca a propósito en la matriz.
- **Configuración ▸ Correlativos:** ya existía (21/10) y cubre COT, PC, Guía y Factura/Boleta. Lo que cambia hoy:
  - Al guardar se pide **doble confirmación**: primero "¿Confirmas?" y después escribir otra vez el número.
  - El servidor también lo exige: sin el número repetido no cambia nada.
  - La OC se sigue mostrando solo para consulta, porque su número reinicia cada día con la fecha (OC-AAAAMMDD-NNNN).
  - Los documentos ya emitidos nunca se renumeran.
- **Compras, estados de la OC** (solo cambia lo que se ve; en la base siguen igual):

  | Antes | Ahora | Color |
  |---|---|---|
  | Por aprobar | Por aprobar | amarillo claro |
  | Aprobada | Aprobada · falta llegar | azul |
  | Recibida parcial | Llegó una parte | lila |
  | Recibida | Mercadería recibida | verde agua |
  | Cerrada | ✔ Completa | verde fluorescente |
  | Borrador y Anulada | sin cambio de nombre | gris |

  - El amarillo de "Siguiente paso" ahora también es amarillo claro, no naranja.
- **Recibir mercadería:**
  - Ya no se muestra "Asignado por ... fecha/hora". Se sigue guardando en la base.
  - La lista "¿Quién recoge?" es más chica.
- **Pruebas:** pasan 258 en la base principal. En la reconstruida pasan 256 y se saltan 2. Hay pruebas nuevas de Solo lectura, de la matriz y de la doble confirmación.
- El informe de infraestructura (hosting, red, PC) lo hace otro hilo.

### 24.15 Errores que ya no pasan en silencio, buscador de la OC, OC intercompany y pestañas sombreadas (22/10/2026, pedidos urgentes de Erika de las 11:05 y 11:26)
- **Qué causaba los problemas:**
  - **Buscador de productos de la nueva OC:** sí buscaba, pero la lista de resultados se abría debajo de la casilla y la ventana la cortaba. Quedaba escondida detrás del pie "Cancelar / Guardar borrador", sobre todo en pantallas de laptop. Además, si la búsqueda fallaba, el error se escondía.
  - **Clientes y cotizaciones "no hacen nada":**
    1. Si el servidor no contestaba con un mensaje del ERP, la pantalla no podía leer la respuesta y no mostraba nada. Pasa cuando Render está dormido o reiniciándose (plan gratis), cuando la sesión venció, o cuando hay un error 500 en HTML.
    2. Si había un error, salía solo un aviso pequeño abajo a la derecha que se iba solo a los 3 segundos.
    3. El servidor atendía un solo pedido a la vez. Si alguien abría un reporte pesado, guardar quedaba en cola y parecía colgado.
    4. Si un guardado de cliente fallaba, la conexión a Supabase quedaba abierta. Con varios fallos, Supabase se quedaba sin conexiones y los siguientes guardados se colgaban.
    5. En la base real la dirección fiscal del cliente es obligatoria (NOT NULL). Si no llegaba, fallaba con un mensaje técnico.
  - **Permisos (RLS):** el ERP entra a Supabase con el usuario dueño de las tablas, así que RLS no bloquea sus INSERT/UPDATE. "Solo lectura" (24.14) sí bloquea, pero con un mensaje claro y solo a quien se le marcó así. La migración 024 convirtió los "Ver" antiguos en Acceso total para que nadie se quedara bloqueado.
- **Qué se cambió:**
  - `static/js/errores_guardado.js` (nuevo, cargado en todas las pantallas desde `base.html`):
    - Convierte cualquier respuesta rara del servidor en un mensaje claro: "Tu sesión expiró", "El servidor no respondió a tiempo (Render puede estar despertando)", "Sin internet", etc.
    - Si un guardado tarda más de 6 segundos, sale arriba "⏳ Guardando... no cierres ni vuelvas a presionar".
    - Ofrece `mostrarErrorGuardado`, una ventana roja grande con el motivo, el detalle técnico y el botón "Copiar detalle", y `botonCargando`.
  - **Clientes** (Maestros y desde la cotización): el botón dice "⏳ Guardando...". Si falla, sale la ventana roja con el motivo exacto y el campo marcado en rojo (RUC/DNI, razón social, días de crédito...).
  - **Cotizaciones:** "Guardar borrador" también dice "Guardando..." (Solicitar validación y Generar ya lo hacían). Si el servidor dice qué campo falta, se marca en rojo y se abre la lista de faltantes. Cualquier otro error sale en la ventana roja con el detalle.
  - **Servidor:**
    - `routes/diagnostico.py` (nuevo) traduce los errores de Supabase a español: RUC repetido, dato obligatorio vacío, valor no aceptado, permiso/RLS, columna que falta, base que no responde. También envía el texto exacto en `detalle`.
    - Si el error es "el contador de ids está atrasado" (pasa al cargar datos desde Excel con su número), lo corrige solo y pide volver a presionar Guardar.
    - Cualquier error inesperado en una ruta `/api/` ahora responde JSON con el mensaje, nunca una página HTML.
    - La conexión a Supabase se cierra siempre, aunque falle.
    - Si Supabase no contesta, se espera hasta 15 s (`PGCONNECT_TIMEOUT`) y luego sale un error claro.
  - **`gunicorn.conf.py` (nuevo):** Render lo lee solo. Ahora corre 1 proceso con 8 hilos, así que atiende varios pedidos a la vez sin usar más memoria.
  - **Registro de fallos:** cada guardado que falla, en el servidor o en el navegador, queda en la tabla `erp_log_errores` con usuario, empresa, fecha/hora, pantalla y mensaje exacto. Se ve arriba en **Herramientas ▸ Registro de errores** y no se pierde cuando Render se reinicia.
  - **Buscador de la OC:**
    - La lista flota sobre la ventana y, si abajo no hay espacio, se abre hacia arriba.
    - Mientras busca dice "⏳ Buscando...".
    - Si falla, dice en rojo "⛔ No se pudo buscar: motivo". Lo mismo se aplicó al buscador de proveedor.
- **OC intercompany** (el proveedor es otra empresa del grupo, por ejemplo AGD GROUP → KCF):
  - Antes, al ser "Contado", Recibir mercadería mostraba "🔒 Falta el pago", igual que con un proveedor de afuera. La regla de pagar antes de recoger es para no perder dinero con terceros.
  - Ahora una OC intercompany se puede **recibir antes del pago**. Debajo del botón Recibir sale en pequeño "Intercompany: falta el pago", y el pago sigue pendiente en Finanzas.
  - Una OC al contado de un proveedor de afuera sigue bloqueada, ahora con la explicación "Es al contado: Finanzas paga primero y luego se recoge".
  - Se reconoce como intercompany si el RUC del proveedor es el de una empresa de Configuración ▸ Empresas.
- **Pestañas sombreadas:** la pestaña donde estás se pinta con el color de la empresa en Compras, Inventario, Conciliación bancaria, Intercompany, Planilla y Seguimiento. Antes, un código del menú lateral las apagaba. Finanzas, Reportes, SUNAT, Papelera, Ventas y Maestros ya se sombreaban.
- **Supabase:**
  - `migrations/025_diagnostico_errores.sql` es **opcional**, porque el sistema crea la tabla solo y corrige el contador al fallar. Crea `erp_log_errores` y adelanta los contadores de id de clientes, cotizaciones, proveedores, productos y OC que estén atrasados. No borra ni cambia datos.
  - No se pudo aplicar hoy, porque el conector de Supabase de este hilo está caído (error 503).
- **Pruebas:** pasan 265 en la base principal. En la reconstruida pasan 263 y se saltan 2. Las pruebas nuevas están en `tests/test_zz_zz_22oct_errores.py`.

### 24.16 Recibir mercadería avisa diferencias antes de grabar y Cobros y pagos con N° OC / N° PC (22/10/2026, pedidos de Erika de las 12:21 y 12:26)
- **Recibir mercadería:** se sigue contando a ciegas: mientras se cuenta no se ve cuánto pidió la OC.
  - Al pulsar Guardar, si lo contado no coincide, **no se graba** y sale una ventana amarilla. Por ejemplo: "LENTE...: la OC pide 5 UND, estás registrando 50 → sobran 45". También avisa lo que falta, lo dañado y los productos sin registrar.
  - La ventana tiene dos botones: **🔁 Volver a contar** y **Confirmar con diferencia**, con un motivo opcional.
  - Queda en el historial de la OC, con usuario y fecha/hora de Lima:
    - cada vez que se mostró el aviso ("Aviso de diferencia al recibir ... aún no se grabó");
    - lo que se confirmó ("Recibió confirmando diferencias ... Motivo").
  - Lo sobrante sigue creando su incidencia para la supervisora.
  - Se quitó el texto "ve a Inventario e Ingresar" cuando el stock ya entró solo.
- **Finanzas ▸ Cobros y pagos:** nueva columna **N° OC / N° PC**, en dos líneas y sin scroll horizontal. Se busca también por esos números.
  - Pagos: N° OC y N° PC, o "Compra a stock" / "Sin PC vinculado".
  - Cobros: N° PC y N° OC del cliente.
  - Usa el mismo criterio que Cuentas por cobrar y por pagar.
- **Pruebas:** pasan 267 en la base principal. En la reconstruida pasan 265 y se saltan 2.

### 24.17 Intercompany 7.2: una tabla por OC, pantalla simple, y Banco con lista desplegable (22/10/2026, pedidos de Erika de las 12:34, 12:48 y 12:50)
- **Qué faltaba y por qué "no se actualizaba":** el módulo 7.2 solo leía **facturas de venta** entre empresas. Una OC de KCF a AGD GROUP (pagada o a crédito) no aparecía hasta que AGD emitía su factura.
- **Ahora, "Operaciones entre empresas (una fila por OC)"** es lo primero de la pantalla. Cada OC hecha a otra empresa del grupo muestra:
  - N° OC y fecha; quién vende y quién compra (OC hecha en KCF con AGD como proveedor = **AGD → KCF**);
  - para qué se compró: N° PC y cliente (la cotización al pasar el mouse), o "Stock";
  - monto y condición; pago (✔ Pagado o "Falta S/ ..." en rojo);
  - mercadería: recibida en la que compra y despachada por la que vende (el despacho es lo que descuenta su stock);
  - facturas: factura de venta de la que vende y si está registrada en compras de la que compra;
  - **siguiente paso** en rojo (y "y N pasos más" con el detalle al pasar el mouse), o ✔ Completa en verde.
- Filtro "Todas / Solo con pendientes / Solo completas" y buscador por N° OC, N° PC, cliente o factura.
- La empresa que vende enlaza su PC con la OC escribiendo el N° de la OC en "N° OC del cliente". Su factura se reconoce por ese N° OC, por el PC o por el mismo N° de factura registrado en compras.
- **Inventario sin doble conteo:** sale con el despacho de la que vende y entra con "Recibir mercadería" de la que compra. La ayuda avisa no usar además Inventario ▸ Intercompany para lo mismo.
- **Pantalla más simple (12:50 "muy cargado"):**
  - las tarjetas grandes pasan a una fila delgada (como Finanzas), contada desde la tabla: operaciones abiertas, falta pagar, falta recibir o despachar, falta facturar o registrar, lo que se deben y stock del grupo. Al hacer clic filtra "Solo con pendientes";
  - el cartel rojo grande pasa a una línea pequeña;
  - el mes pasa a la fila de pestañas; "Lo que se deben", "Facturas entre empresas" y "Últimos 6 meses" quedan plegados;
  - la pestaña se llama "🔁 Operaciones".
- **Banco con lista desplegable (12:48):**
  - Registrar pago y Registrar cobro (Finanzas), Pagar OC (Compras), ficha del proveedor, PC y Planilla usan la misma lista: BCP, BBVA, Interbank, Scotiabank, BanBif, Banco de la Nación, Pichincha, MiBanco, Banco GNB, Falabella, Ripley y las cajas municipales, más "Otro (escribir)".
  - Un dato antiguo escrito distinto ("bcp ", "Banco de Crédito", "BBVA Continental") se muestra como el nombre de la lista.
  - El servidor también lo guarda normalizado (`utils.normalizar_banco`), aunque llegue escrito a mano.
  - **No se cambió ningún dato ya guardado** en Supabase. Normalizar los bancos antiguos queda para cuando Erika lo autorice.
- **Supabase:** no hay migración nueva (no hace falta).

### 24.18 Fecha de cita sin hora, rótulo nuevo y "Generar compra" con líneas sombreadas (22/10/2026, pedidos de Erika de las 12:54, 12:57 y 12:59)
- **Ventas ▸ Entregas ▸ Fecha de cita con el cliente:** se elige solo la fecha. En la columna sale dd/mm/aaaa. Las citas ya guardadas se conservan y su hora se ignora.
- **Rótulo** (KCF y AGD; vale para el de guía, PC y despacho):
  - el nombre de la empresa va en una sola línea, sin E.I.R.L. / S.A.C. ("KCF CORPORACIÓN");
  - se quitaron las bolitas de redes sociales y la página web del pie (quedan teléfono y correo);
  - el nombre del consignado va en letra grande, con el DNI debajo; N° de bultos en letra grande;
  - cuatro casillas: **N° despacho, N° pedido de compra, N° guía y N° factura**. Si falta alguno sale "—". El rótulo de una guía busca su despacho y su PC.
- **"Generar compra" (Ventas ▸ Entregas):**
  - ya no abre la orden de compra de golpe. Lleva a **Compras ▸ Pedidos por comprar**, con la pestaña sombreada;
  - sombrea en amarillo **ese pedido y sus líneas**, se desplaza hasta ellas y las deja marcadas. Dice "Este es el pedido PC-... del despacho DESP-...";
  - se marca por línea del PC, no por producto: si el mismo producto está en otro PC (Lima y Arequipa), ese otro no se marca;
  - la persona revisa y pulsa "Crear orden de compra".
- **Pruebas:** pasan 270 en la base principal. En la reconstruida pasan 268 y se saltan 2.

### 24.19 Intercompany 7.2: más OC reconocidas (22/10/2026, Erika 13:17 "no se actualiza")
- Antes solo entraban las OC del flujo nuevo de Compras ya aprobadas. Ahora entran todas las OC no anuladas, también las de las pantallas anteriores y las que están en Borrador o Por aprobar. Para estas últimas el siguiente paso es "Aprobar la OC".
- El proveedor del grupo se reconoce por su RUC y también por su razón social. Si el RUC del proveedor en Maestros ▸ Proveedores no es el de la empresa del grupo, la fila sale igual, con el paso "Corregir el RUC de ... (debe ser ...)".
- **Pruebas:** pasan 271 en la base principal. En la reconstruida pasan 269 y se saltan 2.

### 24.20 Compras: stock repartido entre pedidos, resumen de abastecimiento por pedido y "Comprado, por llegar" desde que se genera la OC (22/10/2026, pedidos de Erika de las 13:21)
- **Qué estaba fallando:**
  1. **El stock se contaba dos veces.** Cada pedido usaba todo el stock de la empresa. Ejemplo de Erika: stock 32, PC-KCF-000011 pide 40 y otro PC abierto pide 18.
     - Pedidos por comprar decía "comprar 8" para el de 40 y "cubierto con stock" para el de 18 (oculto), pero en total faltan 58 − 32 = 26.
     - El resumen de abastecimiento sí sumaba los dos (58) y por eso decía "Faltan 18" sin explicar de dónde salía.
  2. **Solo contaban las OC aprobadas.** Con la OC en Borrador o Por aprobar, Entregas, PC y Cotizaciones seguían diciendo "Pendiente de compra".
     - Pedidos por comprar sí la restaba ("Ya en órdenes"), así que no se generaba una OC doble; la compra duplicada además la frena el control de OC repetida del 20/10.
- **Ahora:**
  - **El stock se reparte entre los pedidos, el más antiguo primero, y no se cuenta dos veces.** En el ejemplo: al PC de 18 (más antiguo) le tocan 18 y al de 40 le tocan 14 → comprar 26. La columna se llama "Stock que le toca" y dice "de 32 en la empresa".
  - **Resumen de abastecimiento** (formulario de la OC), por producto:
    - arriba, lo que hace ESTA orden: "✔ Esta orden cubre 26 de PC-KCF-000011", o en rojo "✖ A PC-KCF-000011 le faltan 18: pide 40, ya en otras OC 0, stock que le toca 14";
    - una fila por pedido: Pide · Ya en otras OC · Stock que le toca · Falta comprar · En esta orden · Resultado;
    - los pedidos de esta orden van arriba y sombreados. Los otros salen en gris como "Otro pedido sin comprar", con el botón "Sumarlo aquí"; "Usar N" pone lo que falta;
    - el rojo solo sale cuando a un pedido de esta orden le falta.
  - **"Comprado, por llegar"** sale desde que la OC se genera (Borrador, Por aprobar, Aprobada, Recibida parcial) y muestra el N° de OC en Entregas (columna Estado compra), PC y Cotizaciones. Cuando se recibe, el stock entra y pasa a "Comprado / en stock".
  - **Despachar o hacer la guía sin stock físico con la OC en camino:** el mensaje dice "No hay stock físico, pero la mercadería ya está comprada y en tránsito (OC-...). Recíbela en Compras ▸ Recibir mercadería para poder despachar."
- **Supabase:** no hace falta cambiar vistas ni datos; todo se calcula en el sistema.
- **Pruebas:** pasan 272 en la base principal. En la reconstruida pasan 270 y se saltan 2.

### 24.21 Pre-producción (pedido de Erika, 22/10/2026 15:33)
- **PDF de la OC: "Datos para la transferencia".**
  - Es un recuadro nuevo, debajo de las indicaciones de facturación.
  - Muestra el titular y su RUC, el banco, el N° de cuenta y el CCI.
  - El N° de cuenta y el CCI son texto: un clic los selecciona enteros para copiar y pegar.
  - Los datos son los del **proveedor**, porque la OC va al proveedor y a esa cuenta se le paga (la hoja ya decía "Pagamos únicamente a la cuenta bancaria registrada del proveedor").
  - Si el proveedor no tiene cuenta registrada, sale un aviso rojo solo en pantalla, que no se imprime.
  - Si Erika prefiere la cuenta de KCF o AGD, se cambia en `templates/compras/imprimir_oc.html` (las cuentas de la empresa están en `erp_empresa_cuentas_bancarias`).
- **Monitor de errores en la consola (F12).**
  - Archivo nuevo `static/js/monitor_consola.js`. Se carga en todas las pantallas (base.html), en el login, en las de Maestros que tienen su propia página y en el programa de transporte.
  - Escribe en rojo, con hora de Lima:
    - los errores de JavaScript, con archivo y línea;
    - los errores que nadie atendió;
    - cada consulta o guardado a `/api/` que falla o responde `success:false`, con el método, la ruta, el código HTTP y el mensaje del servidor;
    - lo que sale en la ventana roja;
    - los archivos que no cargaron.
  - `erpErrores()` en la consola muestra la tabla de errores de la pantalla.
  - No avisa de las consultas que se cortan al cambiar de pantalla.
- **Auditoría.**
  - Recorrí las 22 pantallas del menú con el monitor encendido: ningún error de JavaScript ni de servidor.
  - En el entorno de pruebas solo fallan las letras e íconos de internet, porque allí internet está cerrado.
  - Pruebas: las 272 de la base principal, más 2 nuevas (PDF con datos bancarios y monitor).
- **Limpieza de la base.**
  - Queda preparada en `SUPABASE_026_respaldo_y_vista_previa_limpieza.sql`:
    - respaldo completo en el esquema `respaldo_pre_produccion`;
    - vista previa de clientes, proveedores y productos que parecen de prueba;
    - lista de los stocks que bajarían a 5;
    - tamaño de las tablas.
  - Probado en la base local.
  - No se ejecutó en Supabase porque el conector está desconectado.
  - El borrado se arma con esa vista previa y con el OK escrito de Erika.

### 24.22 Intercompany consolidado (Erika, 22/10/2026 18:00: "más ordenado, más claro, consolidado")
- **Arriba, una sola línea con quién le debe a quién al final.** La cifra sale de las OC sin pagar de los dos sentidos. Antes "Falta pagar S/ 2,271.50" salía junto a "Se deben S/ 0.00", porque esa cifra solo miraba facturas.
- **Un recuadro por sentido** ("KCF le vende a AGD" y "AGD le vende a KCF"):
  - va primero el sentido en que vende la empresa activa, con la nota "lo que te deben" o "lo que debes";
  - muestra N° de OC, total, pagado y falta pagar;
  - los pendientes van en rojo con su cantidad y quién los hace: por despachar, por recibir, por facturar (con el monto), por registrar en compras y por pagar (con el monto);
  - un clic en un pendiente filtra la tabla. Si no hay pendientes, sale "✔ Todo al día" en verde;
  - si la que vende aún tiene facturas por cobrar en Finanzas, lo dice y recuerda registrar el cobro.
- **Una tabla por sentido.**
  - Columnas: Despachado, Recibido, Facturado, Registrado y Pagado, cada una con ✔ o ⏳ y quién lo hace en el encabezado.
  - Un solo "Siguiente paso", con la empresa que lo hace; los demás pasos se ven al pasar el mouse.
  - Filtros: Sentido y Ver (falta pagar, despachar, recibir, facturar, registrar o completas).
- **Orden de los pasos.** Despacho → recepción → factura → registro en compras → pago. Al contado, el pago va primero.
- **Aviso de clientes.** Ya no está arriba. Sale dentro del paso "Factura de venta", y solo cuando hace falta crear a la otra empresa como cliente.
- **Paneles plegados.** "¿Cómo funciona?" pasó abajo y está plegado, igual que Facturas por cobrar, Facturas del mes y Últimos 6 meses.
- **Pruebas:** pasan 274; en la base reconstruida pasan 272 y se saltan 2.
- **Supabase (pre-producción):**
  - Respaldo completo hecho en el esquema `respaldo_pre_produccion`: 80 tablas, con los conteos verificados.
  - Lo claramente falso, sin ningún documento que lo use: 4 proveedores (fsafsafsfsafs, sdfggsgsdgsdgdsgdsgdsgd, sdsdbxdbvcxbcxbcxb y tfrdhydfhdfhdf, con su contacto y su punto de entrega) y el producto PRD-0027 "producto de prubea".
  - Su borrado quedó sin confirmar: el conector se cortó y el permiso de esta sesión bloqueó seguir borrando.

### 24.23 Compras más claro y reglas para todos los módulos (Erika, 22/10/2026 18:13)
- **Hoy en Compras.**
  - El flujo de 7 pasos se despliega con "ⓘ ¿Cómo es una compra?".
  - Las tarjetas quedan en una fila.
  - "Qué hacer hoy" tiene filas más delgadas.
- **Pedidos por comprar.**
  - "Pedido del cliente" pasa a "PC (Pedido de Compra del cliente)".
  - "Stock que le toca" pasa a **"Stock asignado"** (a este PC). Debajo dice de dónde sale, por ejemplo "32 en la empresa · 18 para PC más antiguos".
  - "Comprar para pedido" pasa a **"Compra bajo pedido"**.
  - "Comprar para stock" y "Total a comprar" no cambian.
  - **"Saldo después de entregar" se quitó.** Siempre era igual a "Comprar para stock": lo que se compra de más es lo que queda en almacén. Repetía un número y confundía.
- **Órdenes de compra.**
  - "Pago" pasa a "Forma de pago" y "Total" pasa a "Total (inc. IGV)".
  - "Para (cliente)" muestra solo el cliente: el N° PC y el N° cotización ya tienen su propia columna.
  - Colores, que reemplazan los de las 11:00:
    - Por aprobar: rojo.
    - Aprobada: verde.
    - Mercadería recibida: azul eléctrico.
    - Barra "Llegó mercadería": línea roja en 0 %, ámbar a medio camino y verde fluorescente en 100 %.
- **Todos los módulos: columna "Ítem".**
  - Archivo nuevo `static/js/orden_pantallas.js`, cargado en todas las pantallas.
  - Pone "Ítem" (1, 2, 3...) como primera columna de cada tabla de datos y numera lo que se ve, en orden. Así se puede decir "revisa el ítem 5".
  - Las tablas que ya numeraban (#, Item, N°) solo cambian el nombre a "Ítem".
  - No toca las tablas dentro de ventanas ni las tablas donde se escribe (cotización, PC), porque esas leen sus celdas por posición. Una tabla se excluye con `data-sin-item`.
- **Todos los módulos: ayudas cortas.** Los textos de ayuda largos (.inv-help, .panel-help, .hr-help, .ge-sub, .fin-help) muestran solo la primera frase y el botón "ⓘ Ver más", que despliega el resto en el mismo lugar.
- **Pruebas:**
  - 1 prueba nueva.
  - Recorrí las 22 pantallas del menú sin errores en la consola.

## 30. Módulo nuevo "7.4 ─ Caja chica" (22/10/2026, pedido de Erika de las 18:24)

Erika aprobó un fondo fijo de S/ 600 para KCF, administrado por Hellen, y pidió conservar el histórico de su Excel.

### 30.1 Qué hace
- **Gastos:** cada gasto con fecha, rubro (11 fijos), quién gastó o a quién se pagó, N° PC/OC/despacho, comprobante y hasta 3 fotos (se guardan comprimidas en la base porque el disco de Render se borra).
- **Reglas al registrar:**
  - Fecha no futura, no más de 120 días atrás y no dentro de una semana ya aprobada.
  - Máximo 2 decimales.
  - Factura/boleta/RxH piden N°; la factura pide RUC.
  - Más de S/ 100 pide "Autorizado por".
  - Planilla de movilidad: solo rubro Movilidad, solo Trabajador o Practicante, con DNI. Avisa si la persona pasa el tope diario (4 % de la RMV = S/ 49.20 con RMV S/ 1,230 desde el 01/10/2026).
- **Rendición semanal:** Hellen la envía; el administrador la aprueba (reposición = fondo − saldo) u observa (los gastos vuelven a poder editarse). Un gasto enviado ya no se cambia.
- **Reposición:** al aprobar se crea el movimiento de ingreso y un PAGO en `finanzas_pagos` (`documento_tabla` = 'caja_chica_rendiciones' o 'caja_chica_movimientos'), así Conciliación bancaria lo encuentra.
- **Arqueo:** efectivo + saldo en cuenta + vales contra el saldo del sistema; si hay diferencia, la explicación es obligatoria.
- **Imprimibles:** vale de caja (marcado "documento interno"), planilla de movilidad por persona (con firma y DNI), rendición y acta de fondo fijo.
- **Histórico:** importación solo con la caja vacía, con vista previa y confirmación.
- **Permiso:** "Caja chica" (CAJA_CHICA, id 40) dentro de Finanzas; el administrador lo ve siempre.

### 30.2 Archivos
- Nuevos: `routes/caja_chica.py`, `templates/caja_chica.html`, `templates/caja_chica_imprimir.html`, `static/js/caja_chica.js`, `migrations/027_caja_chica.sql`, `tests/test_zz_zz_zz_zzcaja_chica.py`.
- Cambiados: `main.py` (blueprint), `routes/acceso.py`, `routes/configuracion_seguridad.py`, `static/js/permisos_matriz.js`, `templates/base.html` (menú 7.4 con Gastos, Rendición y reposición, Arqueo, Personas y datos).

### 30.3 Supabase (hecho el 22/10/2026)
- Migración 027 aplicada, con respaldo previo `respaldo_20261022.erp_submodulos_pre027`. Crea 6 tablas `caja_chica_*` (RLS activo, sin acceso anon/authenticated) y el permiso CAJA_CHICA. No toca datos existentes.
- Histórico cargado en KCF: 831 movimientos (saldo inicial S/ 134.61 + 830 del Excel ene–oct 2026), saldo final S/ 7.26, igual al Excel. Comprobado fila por fila (huella md5 igual a la del archivo).
- Configuración: fondo S/ 600, responsable Hellen Blas, RMV S/ 1,230. Personas: Hellen (Trabajador), Luis, Sebastián y Estrella (Practicante), Franklin, Ever y Felipe (Transportista), Himer (inactivo, ex colaborador). DNIs por llenar.
- La próxima migración libre es la 028.

### 30.4 Pruebas
- 6 pruebas nuevas; suite completa en verde.
- Nota: Planilla usa RMV por defecto S/ 1,130; desde el 01/10/2026 es S/ 1,230.

### 30.5 Corrección del taxi del 08/05/2026 (Erika, 23/10/2026: "sí, un gasto")
- Es solo un cambio de datos. El código no cambia, así que no hay que tocar archivos del ZIP. Solo hay que agregar esta sección al INFORME.
- Supabase: el movimiento N° 298 de KCF (taxi de la Oficina al Venezuela Chifa, Himer Castillo, S/ 23.10) estaba como "Devolución" (+23.10). Ahora es "Gasto", rubro Taxi, egreso 23.10, con observación e historial.
- Respaldo previo: `respaldo_20261022.caja_chica_mov_298_pre_correccion`.
- Saldo de la caja: pasa de S/ 7.26 a −S/ 38.94. Es decir, Hellen puso S/ 38.94 de su dinero. La primera reposición para dejar el fondo en S/ 600 es S/ 638.94, no S/ 592.74.
- Plantilla Excel `/mnt/project-files/caja-chica/Caja_Chica_KCF_plantilla_2026.xlsx`: la misma fila quedó corregida. Se recalculó con 0 errores y el saldo final es −38.94.

### 24.24 Remuneración mínima vital S/ 1,230 (23/10/2026)
- **Planilla.** El valor por defecto de la RMV pasa de S/ 1,130 a **S/ 1,230**, vigente desde el 01/10/2026 (D.S. 015-2026-TR).
- **Lo que cambia con eso:**
  - La asignación familiar sube a S/ 123.
  - El control de "sueldo menor a la RMV" usa el nuevo monto.
  - Si en Planilla ▸ Configuración se guardó otra RMV, manda la que esté guardada.
- **Pruebas.** El ZIP integra la Caja chica (sección 30). Pasan 281; en la base reconstruida pasan 279 y se saltan 2.

### 24.25 Ventas ▸ Entregas más simple (Erika, 23/10/2026 04:35: "aqui es un si")
- **Cantidad y producto** en una sola casilla, una línea por producto (por ejemplo "30 × LENTE DE SEGURIDAD").
- **Distrito** en vez de la dirección completa. La dirección sale al pasar el mouse sobre el distrito.
  - El distrito se lee de la dirección (Lima y Callao; también "SMP", "Cercado", "Surco", "SJL"...).
  - Si la dirección no lo dice, sale el botón "📍 Poner distrito". Se escribe en la misma fila, con la lista de distritos.
  - Con ✏ se cambia. Si se borra, vuelve a leerse de la dirección.
- **Comentario corto** en la fila: clic, escribir y Enter (máximo 120 letras). Esc cancela. Queda en auditoría.
- **Filtros nuevos:** por distrito (incluye "Sin distrito") y por fecha de cita (hoy, mañana, próximos 7 días, sin cita o una fecha elegida). El ✕ limpia todos los filtros.
- El buscador también encuentra por producto, distrito y comentario.
- **Estado compra** sigue en su columna.
- La tabla se ajustó para entrar sin scroll lateral en pantallas de 1366 y 1500 de ancho.
- **Supabase:** migración **028** aplicada (`SUPABASE_028_entregas_distrito_comentario.sql`). Solo agrega dos columnas vacías a `despachos` (distrito y comentario); no toca datos. La próxima libre es la 029.
- **Pruebas:** 3 nuevas en `tests/test_zz_zz_23oct_entregas.py`. Pasan 284; en la base reconstruida pasan 282 y se saltan 2.

### 24.26 Seguimiento del cobro en Cuentas por cobrar y "Ver cobro" en Entregas (Erika, 23/10/2026: "genial estoy de acuerdo")
Sale de su Excel de seguimiento (portal de proveedores, fecha programada de pago, comprobante de retención). Para que nada se vea saturado:
- **Entregas** se queda solo con lo logístico.
  - Cada entrega que ya tiene factura muestra el botón **"Ver cobro"** (verde azulado, el color de los cobros).
  - El botón abre Finanzas ▸ Cuentas por cobrar con esa factura **sombreada en amarillo**, como hace "Generar compra".
  - Si la factura es borrador, se buscan también los borradores.
- **Cuentas por cobrar** tiene una sola columna nueva, "Portal y pago / retención 3%". En cada fila muestra:
  - "✔ En portal" (verde) o "✖ Falta portal" (rojo; solo si falta cobrar);
  - "Pago prog. dd/mm/aaaa", si el cliente ya programó el pago;
  - "Ret. R001-…", o "Ret. 3%: falta N°" en ámbar si la factura tiene retención y aún no llega el comprobante.
  - Con ✏ se abre una ventanita para llenar: ingresada en el portal y su fecha, fecha programada de pago, N° del comprobante de retención y monto retenido. Debajo dice cuánto es el 3% de la factura.
- **Retención:**
  - El monto anotado manda sobre el calculado en la factura: el saldo por cobrar es el total menos la retención anotada.
  - **Cuadra con SUNAT:** en el mes del primer cobro, "Retenciones del mes" suma ese mismo monto.
  - Si el monto se deja vacío, vuelve el de la factura.
- El buscador de Cuentas por cobrar también encuentra por N° de comprobante de retención.
- Solo pueden escribir quienes operan Finanzas. Queda en auditoría con usuario y hora.
- La tabla entra sin scroll lateral en pantallas de 1366 y 1500.
- **Supabase:** migración **029** aplicada (`SUPABASE_029_seguimiento_cobro.sql`). Es una tabla nueva y vacía `finanzas_seguimiento_cobro` con RLS activo; no toca datos. La próxima libre es la 030.
- **Pruebas:** 2 nuevas. Pasan 286; en la base reconstruida pasan 284 y se saltan 2.

### 24.27 Soles y dólares con tipo de cambio (Erika, 24/10/2026 18:17)
Pedido: "en el registro de compra y ventas se debe colocar el tipo de cambio y ordenes de compra debe estar en tipo de cambio porque a veces vendo y compro en dolares / en kcf tengo cuenta soles / en agd tengo cuenta en soles y dolares / los proveedores venden en dolares y me dan su tipo de cambio para pagar en soles".

- **Cotización, PC, Factura y Orden de compra** tienen "Moneda" (Soles / Dólares). Si es en dólares aparece el casillero **"Tipo de cambio"**: se propone el TC SUNAT del día y se puede corregir (el del proveedor o el pactado). Se ve el total equivalente en soles.
- El PC copia la moneda de la cotización; la factura la del PC (o se elige). El PDF dice "US$" y el total en letras "… DÓLARES AMERICANOS".
- **Pagos (Compras y Finanzas):** una deuda en dólares se puede pagar en soles con el TC que da el proveedor. Se guarda lo que realmente salió del banco (moneda, TC y monto) y el saldo baja en dólares. Diferencias de redondeo hasta 2 céntimos se cierran solas.
- **Cuentas por cobrar / pagar, Reportes y Panel:** cada fila muestra su moneda; los totales de arriba van en soles con el TC de cada documento.
- **SUNAT (registros de compras y ventas):** todo se pasa a soles con el TC del documento (antes: el TC del mes).
- **KCF solo tiene cuenta en soles; AGD en soles y dólares.** El ERP solo deja pagar en dólares desde una empresa con cuenta en dólares registrada. Hoy **AGD no tiene registrada su cuenta en dólares**: hay que agregarla en Configuración ▸ Empresa ▸ Cuentas bancarias (no la inventamos).
- **Base de datos: migración 030** (`migrations/030_moneda_tipo_cambio.sql`), aplicada en Supabase el 24/10. Solo agrega columnas `moneda` / `tipo_cambio` (cotizaciones, pedido_compra_pc, comprobantes, ordenes_compra, comprobantes_proveedor), `moneda_pago` / `tipo_cambio` / `monto_pagado` (finanzas_pagos) y la tabla `tipo_cambio_dia` (con RLS). No borra ni cambia datos: lo existente queda en soles (se revisó: 0 documentos en dólares). Próxima libre: 031.
- Pruebas: `tests/test_zz_zz_24oct_moneda.py`.

### 24.28 Mejoras del prompt de Adriel (Erika, 24/10/2026 18:30)
1. **Descripción del cliente en el PC:** cada línea del PC tiene un recuadro "Descripción del cliente" (lo que pide su OC, por ejemplo Komatsu). Pasa a Despacho, Guía y Factura y sale en sus PDF. La OC al proveedor sigue con la descripción del catálogo. El catálogo no cambia.
2. **PDF de la cotización:** las cuentas dicen "Cuenta Corriente N° …" y la moneda (Soles o Dólares).
3. **Nuevo producto ▸ Marca:** opción "- (sin marca, lo fabrica el proveedor)".
4. **OC con "Adelanto 50%":** primero se paga la mitad (el paso "Pagar" lo pide y la recepción espera ese pago); el saldo queda en Finanzas como cuenta por pagar. La OC impresa muestra Adelanto y Saldo.
   4.1 **Hellen puede aprobar OC**: además de los administradores, aprueba quien tenga el permiso "Aprobar" de Orden de compra (Hellen lo tiene en KCF y AGD). Se mantiene el control "no puedes aprobar una OC que tú misma hiciste" para quien no es administrador: si Hellen hizo la OC, la aprueba Erika (o se decide cambiar esta regla).
5. **Vendedores:** ya no ven "Generar"; solo guardan borrador o "Solicitar validación". La pestaña "Revisión / Validación" y el enlace del menú solo los ven Hellen y los administradores; si alguien escribe la dirección, vuelve a Cotizaciones. El servidor también bloquea "Generada" a quien no es aprobador.
6. **Orden de columnas** en la tabla de productos de la cotización: Ítem | Código de producto | Nombre producto | Modelo | Marca | Unidad | Stock | Precio (sin IGV) | Cantidad | Valor total | Estado entrega | Acciones. El selector de productos del PC pasa a Modelo antes de Marca, igual que el de la cotización.
7. El punto 7 no venía en el prompt: queda pendiente que Erika o Adriel lo manden.
- Pruebas: `tests/test_zz_zz_24oct_adriel.py`; `tests/test_flujos.py` se ajustó (el vendedor ya no genera).

### 24.29 Revisión de todos los módulos y permisos (24/10/2026, punto 8 del prompt)
- Se abrieron las 165 pantallas y consultas del ERP con tres tipos de usuario (administrador, Hellen y vendedor). **Único error 500 real:** el resumen de "Comparativo de costos" pedía una vista que no existe en Supabase (`vista_resumen_costos`); ahora responde el resumen en cero en vez de fallar.
- **Permisos reales (revisados en Supabase, sin cambiar nada):** admin y eri01kcf ven todo (Gerencia total). **hel02kcf (Hellen)** ve Compras, Cotizaciones, Caja chica, SUNAT, Bancos, Intercompany, Planilla y Seguimiento en KCF y AGD, y puede aprobar OC y cotizaciones. No hay ningún vendedor activo hoy (arm01kcf está inactivo); cuando se cree uno, darle el rol de vendedor con solo Ventas y Clientes en Configuración ▸ Usuarios y permisos.
- Pruebas: 297 correctas (base normal) y 295 + 2 omitidas (base reconstruida).

### 24.30 Limpieza de la base: NO hecha, espera la respuesta de Erika
El prompt pedía dejar como máximo 5 registros por tabla y el stock en 5. No se borró nada. Erika debe escribir en el chat:
- **A (recomendado):** borrar solo lo que es claramente de prueba, con respaldo, sin tocar el stock.
- **B:** respaldo completo y luego dejar 5 registros por tabla y stock en 5.

### 24.31 Bancos con soles y dólares (24/10/2026, hilo de Bancos)
- La conciliación compara el extracto con lo que realmente salió o entró del banco (`monto_pagado`, en su moneda). Una deuda de US$ 100 pagada con S/ 380 se concilia con el cargo de S/ 380.
- Un movimiento de la cuenta en dólares solo se une a pagos o facturas en dólares (y soles con soles). La unión manual con monedas distintas avisa con un mensaje claro.
- Pruebas: 298 correctas (base normal) y 296 + 2 omitidas (base reconstruida).

### 24.32 Aprobación de OC a crédito y cuenta en dólares (Erika, 25/10/2026)
Pedido: "Si Hellen puede aprobar sus propias OC, pero aquellas que el proveedor nos da al crédito debe pasar por mi aprobación caso contrario no tienen validez" y "Los datos de la cuenta en dólares de AGD no se colocarán en la cotización de AGD".
- Hellen (y quien tenga "Aprobar" en Orden de compra) ya puede aprobar las OC que ella misma hizo.
- **OC a crédito:** solo la aprueba una administradora (Erika). Para los demás, la orden muestra "A crédito: la aprueba Erika" en lugar del botón Aprobar, y el servidor también lo bloquea. Hasta que Erika la apruebe, la OC no avanza (no se envía ni se recibe).
- **PDF de la cotización:** solo muestra las cuentas en soles. Si se registra la cuenta en dólares de AGD, no aparecerá en la cotización.
- Pruebas: 300 correctas.

### 24.33 Pantallas más compactas en todos los módulos (Erika, 25/10/2026: "quisiera más comprimido y ordenado para que suba más y se vea la data ... aplica para todos los módulos")
- Hoja nueva `static/css/compacto.css`, cargada al final de `base.html`, así vale para todos los módulos. Solo cambia alturas, márgenes y tamaño de letra; los colores y las reglas de armonía no cambian.
- Cabecera: el título y la ruta van en una línea, con la descripción corta debajo. "Empresa activa" queda en una sola línea.
- Pestañas, título de cada tarjeta y filtros: más bajos (casilleros de 28 px).
- Tarjetas de resumen: franja delgada, todas del mismo alto (nombre arriba; monto y cantidad en una línea). Las tarjetas de Herramientas también se achicaron.
- Ejemplo en Reportes ▸ Por cobrar (pantalla de 1600×900): la tabla empezaba a 401 px y ahora empieza a 283 px. En Seguimiento pasó de 518 a 425 px y en SUNAT de 399 a 308 px.
- Capturas de antes y después en `capturas/compacto_*.png`.

### 24.34 "Recalcular stock" pasa a "Revisar stock", solo lectura (Erika, 25/10/2026: "me parece peligroso ... y más aún que no estoy físicamente ahí")
- Antes: solo los administradores podían usarlo, y quedaba en Auditoría. Copiaba en Productos la suma de Inventario y no tocaba el conteo físico ni el kardex.
- Ahora solo compara el stock de Productos con el de Inventario y muestra las diferencias. **No cambia ningún stock.** La ruta que escribía se eliminó.
- La base ya los mantiene iguales sola (trigger `trg_inv_stock_sync_productos`). Revisado el 25/10 en Supabase: los 32 productos cuadran, y el botón antiguo nunca se usó (0 registros en Auditoría).
- El conteo físico se corrige únicamente en Inventario ▸ Conteos.

### 24.35 Reportes solo para Erika (REGLA DE ORO, 25/10/2026: "este módulo debe tener acceso únicamente Erika, nadie más ... nadie puede modificar y ver")
- El módulo 8 Reportes queda bloqueado para todos menos Erika (usuario `eri01kcf`): el menú, la pantalla (también escribiendo la dirección) y todas las consultas y exportaciones.
- El acceso va por usuario, no por rol ni por la matriz de permisos. Por eso otro administrador (por ejemplo `admin`, Antony Gamonal) tampoco entra.
- Solo se cambia con la variable de entorno `USUARIOS_REPORTES` (por defecto `eri01kcf`).
- Quiénes pierden acceso: Hellen y `admin`. Hellen sigue viendo cuentas por cobrar y por pagar en 7 Finanzas, que no cambia.
- Pruebas: 301 correctas (base normal) y 299 + 2 omitidas (base reconstruida).

### 24.36 Nombre visible de Erika (Erika, 25/10/2026: "actualizar mi nombre de usuario para ambas empresas ERIKA DE LA CRUZ por Erika")
- En Supabase, `usuarios` id 10 (`eri01kcf`): `nombre_completo` y `nombres_apellidos` pasan de "ERIKA DE LA CRUZ" a "Erika". El usuario sigue siendo `eri01kcf` (Reportes depende de él). Es un solo usuario para las dos empresas.
- Respaldo previo: `respaldo_20261025.usuarios_nombre_eri01kcf`. Lo ya registrado antes (historial, auditoría) conserva el nombre de ese momento. Se ve al volver a iniciar sesión.

### 24.37 Ventas y Finanzas: código de cliente, Entregas y colores (Erika, 25/10/2026)
- **Código de cliente** en Cotizaciones va solo en negrita, sin la pastilla azul. Pedido: "código de cliente solo en negrita mas no de color azul".
- **Entregas (Despachar) más compacto.** Pedido: "aquí debe estar más comprimido, más orden".
  - El título y todos los filtros van en una sola fila alineada: buscador, fechas, distrito, cita, estado y Exportar.
  - Pasa lo mismo en Cotizaciones, Guías, Facturas y las demás pestañas de Ventas.
  - En pantallas angostas (menos de 1300 px) los filtros bajan a una segunda línea.
- **N° guía y N° factura en columnas separadas.** Pedido: "esto debe estar en cada columna para poder filtrar y ordenar". Esto reemplaza la columna juntada del 20/10.
  - Los encabezados ordenan con un clic, y un segundo clic invierte el orden: Fecha, Estado, N° despacho, N° PC, N° cotización, Cliente, N° guía, N° factura, Distrito y Fecha de cita.
  - El buscador también encuentra por N° guía, N° factura y N° cotización.
  - La tabla sigue sin desplazamiento horizontal en 1600 px.
- **Colores de Finanzas.** Pedido: "en finanzas debe haber una colorimetría según lo solicitado".
  - Las pastillas de resumen tienen fondo suave y borde fuerte: Vencido en rojo (solo si hay), Por vencer en ámbar, Al día en verde, y el total en verde azulado en Cobrar y en morado en Pagar.
  - Un estado en cero queda gris.
  - Reportes ▸ Por cobrar / Por pagar usa la misma paleta.
- Capturas: `capturas/entregas_compacto.png` y `capturas/finanzas_colores.png`.
- Pruebas: 301 correctas (base normal) y 299 + 2 omitidas (base reconstruida). Se ajustaron 3 pruebas que buscaban la columna juntada.

### 24.38 Numeración de facturas E001, "N° Guía" / "N° Factura" y Monto con IGV (Erika, 25/10/2026)
- Pedido: "mis facturas tienen esta numeración E001-00002319 / N° guía en mayúscula G / N° factura F con mayúscula / Monto precisar si incluye o no IGV / en la segunda imagen comprimir".
- **Serie por defecto E001** en facturas nuevas (antes F001). La serie siempre se guarda en mayúscula.
- **Número con 8 dígitos**: se muestra E001-00002319 en Entregas, Facturas y el PDF.
- **Números ya emitidos**: no se cambió ningún número en la base. Las facturas antiguas F001 solo se ven rellenadas con ceros (F001-00000002).
- **Campo Número**: dice "El que dio SUNAT (vacío = siguiente)". Si la factura se emite en el portal de SUNAT, se escribe ese número.
- **Etiquetas**: "N° Guía" y "N° Factura" con mayúscula en todas las tablas, estados y PDF.
- **Monto**: la columna de Facturas dice "Monto (inc. IGV)".
- **Formulario de factura más compacto**:
  - el N° OC del cliente pasa a la fila de Documentos vinculados;
  - casillas y márgenes más bajos.
- Capturas: `capturas/facturas_e001.png` y `capturas/factura_form_compacto.png`.

### 24.39 Seguimiento comercial: WhatsApp y "Cantidad y producto" (Erika, 25/10/2026)
- Pedido: "cuando le dan clic en el número de tel le llame al WhatsApp para que le escriba la vendedora / agregar columna de la descripción y cantidad del producto todo en una columna para filtrar".
- **Contacto**:
  - Si es celular (9 dígitos que empiezan en 9, con o sin 51), el número sale en verde con 🟢. Abre WhatsApp con el mensaje: "Hola <contacto>, le escribimos por la cotización N° … ¿Pudo revisarla? Quedamos atentos."
  - Si no es celular, queda la llamada normal con la nota "No es celular: sin WhatsApp".
  - Sin número: "Sin teléfono".
- **Nueva columna "Cantidad y producto"**, una línea por producto ("10 × ZAPATO DE SEGURIDAD T42").
- **Buscador** encima de la tabla: filtra por cliente, producto, N° cotización, vendedora o cualquier dato de la fila, y muestra "N de M".
- La tabla sigue sin desplazamiento horizontal. El botón "Registrar llamada" ahora puede ocupar dos líneas.
- Captura: `capturas/seguimiento_whatsapp.png`.
- Pruebas: 303 correctas (base normal) y 301 + 2 omitidas (base reconstruida).

### 24.40 N° MIGO / conformidad (Erika, 25/10/2026: "sí, entonces agregar para evitar cualquier incidencia")
- Para clientes que no pagan la factura sin el N° MIGO de su conformidad (Komatsu-Mitsui).
- **Ficha del cliente** (Maestros ▸ Clientes): check "Pide N° MIGO para pagar", junto a Descuento autorizado.
- **Factura**:
  - solo si el RUC es de un cliente con el check, aparece el campo opcional "N° MIGO / conformidad", al lado de Condición de pago;
  - si el cliente aún no lo envía, se deja vacío.
- **Cuentas por cobrar**, columna "Portal y pago":
  - si el cliente lo pide y la factura tiene saldo sin MIGO, sale "✖ Falta MIGO" en rojo;
  - con el número anotado sale "MIGO 5000…";
  - se anota o corrige después con el lápiz ✏️, en la misma ventana del portal y la retención. Queda en auditoría.
- **Migración 031** (aplicada en Supabase el 25/10/2026):
  - agrega `clientes.pide_migo` y `comprobantes.numero_migo`;
  - marca a KOMATSU-MITSUI MAQUINARIAS PERU S.A. (RUC 20302241598);
  - no borra nada; hoy no hay facturas de ese RUC en la base.
- Archivos: `routes/migo.py` (nuevo), maestros.py, cliente_modal.html, maestros.js, ventas.py, ventas.js, finanzas.py, finanzas.js y bancos.py.
- Capturas: `capturas/migo_cxc.png`, `capturas/migo_factura.png` y `capturas/migo_seguimiento.png`.
- Pruebas: 305 correctas (base normal) y 303 + 2 omitidas (base reconstruida).

### 24.41 Pedidos de Erika del 26/10/2026 (mañana)
- **Palabras completas, sin abreviaturas** ("el estatus debe estar con letras completas"):
  - Maestros: Activos, Observados, Bloqueados, Total.
  - Resto del sistema: Condición de pago, Cantidad, Precio unitario, Costo unitario y Costo promedio, Código de cliente, Código de anexo, Tipo de documento, Pago programado, Retención y "unidades".
- **PC (Pedido de compra)**:
  - Las filas despachadas pasan de celeste a verde bajito, el mismo de Entregas, con raya gris entre todas las filas. La pastilla "Despachado" es verde fluorescente.
  - La columna Descripción muestra cantidad y producto en una casilla ("40 × Estabilizador"), con "+N más" si hay más de 3. La nota del PC va debajo en gris y el buscador encuentra productos.
- **Sin carrito** en "Pendiente de compra" (Entregas y PC).
- **REGLA DE ORO, columnas de N° de documento**:
  - Ancho justo al número. E001-00002319 va en una línea; los números internos largos se parten en el guion.
  - Celdas y relleno más compactos en Ventas, Finanzas, Inventario y Reportes.
  - Sin desplazamiento horizontal en 1600 px. En 1366 px Entregas aún se pasa unos 20 px.
- **Notas de crédito**:
  - un solo "Ítem" (la columna "Items" ya no se duplica, en ninguna tabla);
  - fecha dd/mm/aaaa y hora;
  - sin la columna "Tipo" vacía;
  - orden: Ítem, Fecha/Hora, Estado, N° nota de crédito, N° Factura o boleta, Cliente, RUC, Motivo, Monto (inc. IGV) y Acciones.
- **Seguimiento comercial**:
  - más compacto: filtros en una línea, tarjetas delgadas y filas más bajas;
  - el botón "Registrar llamada y plan" ya se ve en cada fila. Ahí se anota cómo se contactó, qué dijo el cliente, cuándo volver a llamar o "No va a comprar", y queda en Historial con fecha y hora.
- **Compras ▸ Hoy en Compras ▸ "Ver"**: abre la lista solo con las órdenes de esa alerta (por aprobar, atrasadas, recibidas sin factura...), con el aviso amarillo "Mostrando solo: …" y el botón "Quitar filtro".
- **Compras ▸ Recibir mercadería**: el "Ítem" estaba corrido (mostraba el N° de OC). Una lista desplegable ya no saca la tabla de la numeración automática y las columnas cuadran.
- **REGLA DE ORO de nombres**:
  - "Orden de compra (Proveedor)" y "N° OC (Proveedor)" para el documento al proveedor. Incluye menús, pestañas, Reportes, Papelera y la impresión de la OC.
  - "PC (Pedido de compra)" y "N° PC (Pedido de compra)" para el pedido del cliente ya vendido.
  - "N° OC del cliente" se mantiene: es el número que pone el cliente en su documento.
- Capturas en `capturas/26oct_*.png`.
- Pruebas: 305 correctas (base normal) y 303 + 2 omitidas (base reconstruida). Se ajustaron 6 pruebas que buscaban los nombres viejos.

### 24.42 OC impresa con "Adelanto 50%" (Erika, 26/10/2026: "debajo del total debería decir adelanto y pago total al final por 50%")
- Debajo de TOTAL salen dos líneas en amarillo: "Adelanto 50% (antes de la entrega)" y "Pago al final 50% (con la factura)", cada una con su monto.
- Solo aparecen cuando la condición de pago es "Adelanto 50%". La pantalla de la OC ya mostraba "Adelanto · Saldo".
- Captura: `capturas/26oct_oc_adelanto.png`.

### 24.43 "N° OC del cliente" en PC y en Entregas (capturas de Erika, 26/10/2026 18:11)
- PC (Pedido de compra): debajo del N° PC decía "OC cliente: …" en azul, en una sola línea, y se salía de la celda. Ahora dice "N° OC del cliente" en gris y debajo el número, que nunca se sale de la celda.
- Entregas ▸ Despachar: debajo del N° PC sale el mismo "N° OC del cliente", leído del PC.
- Cuentas por cobrar usa el mismo nombre.
- Capturas: `capturas/26oct_pc_oc_cliente.png` y `capturas/26oct_entregas_oc_cliente.png`.
- Pruebas: 308 correctas (base normal) y 306 + 2 omitidas (base reconstruida) al entregar 24.43.

### 24.44 Entregas: cita → Despachado → Entregado o Rechazado (Erika, 26/10/2026 18:14)
- Orden del trabajo:
  1. **Fecha de cita** con el cliente, con lápiz ✏ para ponerla o cambiarla. "Confirmar despacho" ya no deja seguir sin cita: abre la ventana de la cita.
  2. **Confirmar despacho**: sale del almacén → **✔ Despachado** en verde, y se guarda la fecha y hora de salida ("Salió dd/mm/aaaa hh:mm").
  3. **Confirmar entrega** (botón azul): se pone la fecha real en que el cliente recibió → **✔ Entregado** en azul fuerte y fila celeste. La fecha se corrige o se quita con el lápiz (si se quita, vuelve a Despachado). No puede ser futura ni anterior a la salida.
  4. **Rechazado por el cliente** (botón naranja): pide el motivo, el stock vuelve al inventario y la fila queda "↩ Rechazado por el cliente" con su motivo y el botón **Volver a despachar**. Si ya se hizo la guía, hay que revisar si se anula.
- Columna "Fecha de cita y entrega real": arriba la cita y debajo la entrega real (en una sola columna para que la tabla entre en pantalla).
- Filtro de estados: se agregan "Entregado" y "Rechazado por el cliente".
- "Entregado" ya no se puede poner con el cambio de estado simple: siempre lleva su fecha real.
- Los 23 despachos que hoy dicen "Despachado" se quedan así; logística les pone la fecha real con "Confirmar entrega".
- Base: migración `032_entrega_real.sql` aplicada en Supabase el 26/10/2026, con respaldo previo `respaldo_20261026_despachos` (40 filas). Solo agrega 4 columnas vacías: fecha_salida, fecha_entrega_real, motivo_rechazo y fecha_rechazo.
- Pantalla: a 1600 px entra completa; a 1366 px quedan unos 14 px de más (antes eran unos 20).
- Capturas: `capturas/26oct_entregas_flujo.png`, `capturas/26oct_entregas_confirmar.png` y `capturas/26oct_entregas_rechazo.png`.

### 24.45 Facturas: monto a pagar, condición fija, cotización automática, N° MIGO y XML (Erika, 26/10/2026 18:32-18:36)
- **Monto a pagar**: columna nueva en la lista (verde), con "Retención 3%: S/ …" debajo si la tiene. En "Editar comprobante" hay un campo "Monto a pagar" junto a la condición de pago, que se recalcula solo. Antes la lista no traía ese dato y, sin retención, se guardaba 0. Ahora se guarda el total.
- **Condición de pago FIJA**: sale del PC (Pedido de compra) vinculado; si no hay PC, de la ficha del cliente. Aparece bloqueada con "🔒 Fija, tomada del PC …. Solo Erika la puede cambiar." El servidor también la impone: aunque alguien mande otra (por ejemplo 180 días), se guarda la del PC. Solo el usuario de Erika (eri01kcf) puede poner otra, y queda en Auditoría con la condición anterior y la nueva.
- **Cotización automática**: al elegir la guía o el PC (o cuando la condición encuentra el PC), se llena sola la cotización vinculada (y el PC de la guía). En la lista, si la factura no tenía cotización, se muestra la del PC o la de la guía.
- **N° MIGO**: el campo se ve siempre en la factura. Si el cliente lo pide, el rótulo sale en rojo: "(este cliente lo pide)". En el PDF sale "N° MIGO" junto a OC, Guía y Cotización. En la lista sale "MIGO …" debajo del N° de factura.
- **PDF de la factura**: "OC:" ahora muestra el N° OC del cliente (antes mostraba el N° de cotización por error).
- **XML de SUNAT**: la factura se emite en SUNAT, que da el XML firmado. El ERP no puede firmarlo, así que se guarda ahí:
  - ⋮ ▸ "Subir XML / PDF de SUNAT" acepta .xml, .zip o .pdf de hasta 5 MB. Si el XML es de otra factura, lo rechaza y dice de cuál es.
  - Luego ⋮ ▸ "Descargar XML (SUNAT)" lo baja para mandarlo al cliente. En la lista sale "XML ✔".
- **Retención**: con el panel apagado ya no dice "Activa"; dice "Inactiva (podría aplicar …)".
- Base: migración `033_archivos_factura.sql` aplicada en Supabase. Es una tabla nueva, `comprobante_archivos`, con RLS; no toca datos.
- Capturas: `capturas/26oct_facturas_lista.png`, `capturas/26oct_facturas_menu.png` y `capturas/26oct_facturas_editar.png`.
- Pruebas (24.44 y 24.45 juntas): 317 correctas (base normal) y 315 + 2 omitidas (base reconstruida). Se ajustaron 4 pruebas viejas (Entregado ahora lleva fecha real; sin PC manda la ficha del cliente).

### 24.46 Facturas: sin la pastilla "Pendiente de aprobación" (Erika, 26/10/2026 20:03)
- Era el "Estado del crédito" antiguo: toda factura a crédito nacía "Pendiente de aprobación" y nadie la aprobaba nunca. No lo usa ningún otro módulo.
- Como la condición ya viene fija del PC aprobado, la lista ya no lo muestra. Solo aparece si alguien marca el crédito como "Rechazada".

### 24.47 Regla de oro de nombres: PV, PC y OC (Erika, 26/10/2026 20:26 y 20:41)
- **PV (Pedido de venta)**: lo que antes se llamaba "PC (Pedido de compra)". Es el pedido interno de cada empresa, con número automático: PV-KCF-000012, PV-AGD-000103… La numeración sigue desde el último PC, sin saltos.
- **PC (Pedido del cliente)**: el número que manda el cliente (antes "N° OC del cliente"). Es opcional. Si el cliente no manda número, se ve "—". Sale en la factura, en Entregas y en el PDF ("PC (PEDIDO DEL CLIENTE):").
- **OC (Orden de compra) = solo Proveedor**. Ya no se usa "OC" para nada del cliente.
- Cambiado en todos los módulos: Ventas, Entregas, Facturas, Compras, Inventario, Herramientas, Caja chica, Configuración ▸ Correlativos y los PDF.
- Configuración ▸ Correlativos: "Pedido de venta (PV)" con serie PV-KCF / PV-AGD, y "Orden de compra (Proveedor)".
- Los estados guardados ("PC conforme", "PC observado", "PC atendido") siguen igual en la base y se muestran como "PV …".
- Los números ya emitidos (PC-KCF-000011, etc.) NO se cambiaron en la base: falta la respuesta escrita de Erika. Los nuevos salen como PV.
- Caja chica: el importador acepta la columna "N° PC" (plantilla vieja) y "N° PV" (nueva).

### 24.48 Facturas: retención con candado y pie ordenado (Erika, 26/10/2026 20:38 y 20:40)
- El bloque "Retención del IGV" ya no tiene Estado del crédito, Fecha aprobación, Fecha vencimiento ni Días de crédito.
- Ahora son 4 tarjetas: Monto total (incluye IGV), % de retención (3%, con 🔒), Monto retenido y Monto a pagar. Debajo, una observación que se escribe sola.
- Nadie escribe montos a mano. El servidor recalcula todo: % = 3 (solo Erika puede cambiarlo), retenido = total × 3%, a pagar = total − retenido.
- Vencimiento = fecha de emisión + días de la condición fija del PV. El formulario ya no puede mandar otra fecha ni otros días.
- Pie de la factura: a la izquierda "Para el portal del cliente: ⬇ Descargar PDF | ⬇ Descargar XML". A la derecha: Cancelar | 💾 Guardar como borrador | 📄 Emitir comprobante.
- Si la factura aún no tiene el XML de SUNAT, el botón dice "📎 Adjuntar XML de SUNAT". En ⋮ ya no dice "Subir", dice "Adjuntar XML descargado de SUNAT".
- Observaciones: sección propia "📝 Observaciones" (opcional, sale en el PDF).
- Capturas: `capturas/26oct_retencion.png`, `capturas/26oct_factura_pie.png` y `capturas/26oct_correlativos_pv.png`.
- Pruebas: 318 correctas (base normal) y 316 + 2 omitidas (reconstruida). Prueba nueva: `test_retencion_calculada_y_con_candado`.

### 24.49 REGLA DE ORO de colores por avance (Erika, 26/10/2026 20:43)
Igual en todos los módulos. Lo aplica `static/js/colores_avance.js` según el texto de cada estado, y los colores están en `compacto.css`.

| Avance | Color | Estados |
|---|---|---|
| 100% (cerrado) | Azul eléctrico #0057FF | Pagado, Cobrado, Entregado, Cerrado, Completado, Atendido / PV atendido, Recibido, Facturado, Conciliado, Liquidado, Rendido, Comprado / en stock, En portal |
| 80% (casi listo) | Verde fluorescente #39FF14 | Despachado, Aprobado, Emitido/Emitida, Aceptado, PV conforme, Validado, Enviado, Registrado, Confirmado, Aceptada por cliente, Comprado por llegar / por recoger, OC generada |
| 50% (a medias) | Amarillo #FFD60A | Pago parcial, Parcial, En preparación, En proceso, En revisión, Recibido parcial, Entrega parcial, Compra parcial |
| 0-25% (pendiente) | Rojo #FF1E1E | Pendiente, Por despachar, Borrador, Por pagar, Por cobrar, Vencido, PV observado, Rechazado, Por aprobar, Por validar, Pendiente de compra, Falta MIGO / portal / XML |

- Esta regla reemplaza "terminado = verde". Lo anulado y lo informativo (Activo, KCF/AGD, etc.) no cambian de color.
- Captura: `capturas/26oct_colores_avance.png`.

### 24.50 Notas de crédito: solo Hellen crea, solo Erika aprueba (Erika, 26/10/2026 20:49, 20:54 y 20:57)
- **Quién**: solo Hellen crea, corrige y envía (variable `USUARIOS_NOTA_CREDITO`, por defecto `hel02kcf`). Solo Erika aprueba o rechaza (`USUARIOS_REPORTES` = `eri01kcf`). Nadie más, ni el administrador. Lo controla el servidor.
- **Flujo**: Hellen la guarda como borrador o la envía → "Por aprobar" → Erika la aprueba (queda "Emitida") o la rechaza con motivo. Si la rechaza, Hellen la corrige y la vuelve a enviar.
- **Cuándo cuenta**: no resta de Cuentas por cobrar, Reportes ni SUNAT hasta que Erika la aprueba. Todo queda en Auditoría con fecha y hora.
- **Monto solo lectura** (nadie lo escribe):
  - 01 Anulación, 02 Error en RUC y 06 Devolución total: todo el saldo de la factura.
  - 07 Devolución por ítem: cantidad devuelta × precio de la factura.
  - 04 Descuento global: % del total.
  - Nunca supera el saldo de la factura. Se desglosa en valor de venta, IGV y total.
- **Trazabilidad automática** al elegir la factura: N° factura y fecha, N° guía, N° PV, N° PC (Pedido del cliente) y N° cotización. Se ve en el formulario, en la lista y en el documento.
- **Para SUNAT**:
  - Tipo de nota del catálogo 09 y sustento obligatorio.
  - Detalle de productos y moneda igual a la de la factura.
  - En devoluciones, N° de guía de devolución obligatorio.
  - Evidencias adjuntas: carta o correo del cliente, PDF/XML de la nota emitida en SOL.
- **Serie**: si la factura es E… (portal SOL), la nota sale E001; si no, FC01. Las 3 notas FC01 existentes no se tocaron.
- **Observaciones**: salen en el documento.
- **Nota interna**: nunca sale en el documento; solo la ven Hellen y Erika. Lleva causa (Error operativo / Pedido del cliente / Devolución / Descuento comercial / Otro), responsable del error (obligatorio si es error operativo) y qué pasó.
- **Reporte para Erika**: botón "📊 Causas y responsables" (notas por causa y errores por responsable). En la pestaña sale el aviso "Tienes N por aprobar" y un número rojo.
- Documento para imprimir o PDF: ⋮ ▸ "Ver documento / PDF". El camino antiguo, que dejaba escribir el monto, quedó cerrado.
- Base: migración `034_nota_credito_aprobacion.sql` aplicada en Supabase. Solo agrega columnas vacías y una tabla de evidencias, con RLS; no cambia datos.
- Capturas: `capturas/26oct_nc_formulario.png`, `26oct_nc_lista.png`, `26oct_nc_revisar.png` y `26oct_nc_documento.png`.
- Pruebas: 323 correctas (base normal) y 321 + 2 omitidas (reconstruida). Prueba nueva: `test_zz_zz_26oct_nota_credito.py`.

### 24.51 Sin N° MIGO en ningún módulo (Erika, 26/10/2026 21:27)
- Quitado de la vista: formulario y lista de Facturas, PDF de la factura, ficha del cliente ("Pide N° MIGO") y Finanzas ▸ Cuentas por cobrar ("Falta MIGO" y el campo del ✏️).
- No se borró nada de la base. Las columnas `numero_migo` y `pide_migo` y sus datos siguen ahí, y las pantallas ya no las tocan al guardar.
- Pruebas: 323 correctas (base normal) y 321 + 2 omitidas (reconstruida).

### 24.52 Finanzas ▸ Cuentas por cobrar, Registrar cobro y Cobros y pagos (Erika, 26/10/2026 21:31-21:49)
- **Tabla de Cuentas por cobrar**: "N° PV (Pedido de venta)" y "N° PC (Pedido del cliente)" en columnas separadas; "—" si el cliente no mandó número. Valores de relleno ("*****") o un N° de OC de proveedor escrito por error (OC-AAAAMMDD-NNNN) se ven como "—" sin tocar la base; al volver a guardar la factura quedan en blanco.
- **Columna "Retención 3%"**: N° del comprobante de retención del cliente, su fecha de emisión y el monto real retenido. "Falta N°" en rojo si la factura tiene retención y aún no se anota; "—" si no aplica.
- La fecha real de cobro va debajo de "Cobrado". Portal y pago programado van debajo del Estado. Comentario va con la acción. La tabla entra sin scroll horizontal.
- **Fecha real de pago** = la fecha de aviso de pago del cliente; si no la hay, la fecha de registro.
- **Ventana "Registrar cobro"**: arriba N° PV, N° PC, Retención 3% y Monto a cobrar neto. Campos en orden: Monto, Fecha de registro, Método, Banco, N° de operación (si lo hay), Fecha real de pago (aviso de pago), bloque Retención (N° comprobante, fecha de emisión, monto REAL retenido) y Observaciones / comentarios.
- El monto real retenido puede ser distinto al 3%: se muestra el sugerido y la diferencia en ámbar, y el monto a cobrar se ajusta solo. La retención se guarda antes del cobro (`/finanzas/api/retencion_cobro`) con auditoría.
- **Un comprobante de retención puede cubrir varias facturas** (ej. R001-00010077 de Cummins con 2 facturas E001): se anota el mismo N° en cada factura con su monto. No se bloquea como duplicado.
- **Pastillas de arriba** (Cobrar y Pagar): Vencido rojo, Por vencer (7 días) amarillo, Al día y Total azul eléctrico; en cero conservan su color más suave.
- **Cobros y pagos**: resumen arriba (cobros azul, pagos morado, anulados rojo); columnas "Fecha de registro / fecha real de pago", "Banco / N° de operación" y "Retención (N° · fecha · monto)".
- Base: migración `035_retencion_fecha_cobro.sql` aplicada en Supabase (agrega la columna vacía `retencion_fecha`); respaldo previo `respaldo_20261015.finanzas_seguimiento_cobro_20261026` (la tabla tenía 0 filas). No se cambiaron datos.
- Pruebas: 328 correctas (base normal) y 326 + 2 omitidas (reconstruida). Prueba nueva: `test_zz_zz_26oct_cxc_retencion.py`.

### 24.53 Finanzas ▸ Cobros y pagos con montos claros (Erika, 26/10/2026 22:15)
- Columnas separadas: "N° PV (Pedido de venta)" y "N° PC / N° OC" (en cobros, el N° PC del cliente o "—"; en pagos, el N° OC del proveedor).
- Montos en tres columnas: "Monto factura (incluye IGV)", "Retención" (N°, fecha y monto; si aún no se anota la real, sale la de la factura con "Falta N°") y "Monto real cobrado / pagado" (lo que entró o salió del banco, ya sin la retención).
- Método, banco y N° de operación en una sola columna. La tabla entra sin scroll horizontal.
- Términos: "Tipo" sigue como Cobro / Pago (el movimiento). El estado dice **Cobrado** o **Pagado** en azul eléctrico, y **Anulado** en rojo.
- Resumen de arriba: "Cobrado real" (azul) y "Pagado real" (morado) suman el monto real.
- Pruebas: 328 correctas (base normal) y 326 + 2 omitidas (reconstruida).

### 24.54 Prompt de Adriel (7 puntos) y adelanto en la OC a crédito (Erika, 27/10/2026 16:40-16:53)
- **Cotización ▸ ventana "Cotización guardada"**: N° real de la cotización, cantidad real de ítems, línea "Descuento" y totales leídos de la base. Botones sin emojis.
- **Lo recibido para un PV queda para ese PV**: lo que llega con una OC hecha para el PV ya no se reparte a otros pedidos más antiguos. A cada PV se le resta lo que ya salió en despachos (Despachado / Entregado). Compras ▸ Pedidos por comprar ya no pide de nuevo lo despachado. Botón "Ver OC" cuando el producto está por llegar o pendiente de recojo.
- **Estados con avance**: una cotización cuyo PV ya salió dice "Despachado" (verde) o "Entregado" (azul) y nunca "Pendiente de compra".
- **Guía de remisión**: el PDF muestra el N° PV, el N° PC del cliente y la cotización actuales. La descripción editada en el PV ("descripción para el cliente") pasa a despacho, guía y factura creados desde ese momento. Los documentos ya emitidos no se cambian.
- **Factura desde una guía** (desde el menú de la guía o al vincular la guía en Facturas): carga cliente, RUC, PV, PC, cantidades de la guía y precios del PV. La guía no tiene precios, por eso se toman del PV. Si un ítem no tiene precio, avisa.
- **Compras ▸ Qué hacer hoy**: una sola alerta "sin factura del proveedor". Se quitaron las alertas de control que no eran tareas. Solo cuentan diferencias de OC no anuladas. El aviso de "para stock" solo sale si pasa del 10%.
- **Adelanto (%) en la OC** (pedido de Erika con la OC de PROTENCO "Crédito 30 días"): campo nuevo, junto a la condición, para Crédito o Contra entrega (0% a 100%). Debajo del TOTAL, la OC impresa muestra "Adelanto 50% (antes de la entrega)" y "Saldo 50% a crédito 30 días (desde la factura)". Finanzas paga primero el adelanto desde la OC. En Cuentas por pagar ese pago sale como "Adelanto" debajo de lo pagado, y el saldo vence según los días de crédito. Una OC a crédito la sigue aprobando solo Erika. No se recibe la mercadería sin el adelanto pagado.
- **Ventas ▸ pestaña "Revisión" ahora se llama "Validar"** (Erika, 27/10/2026 17:12), con su título "Validar cotizaciones" y sus mensajes.
- **"Aceptada por Cliente" en azul eléctrico** (Erika, 27/10/2026 17:18): la cotización aceptada está cerrada al 100%, así que pasa del verde al azul en todas las pantallas (colores_avance.js).
- Base: migración `036_adelanto_oc.sql` aplicada en Supabase (agrega la columna `adelanto_pct`, 0 por defecto). Respaldo previo: `respaldo_20261015.ordenes_compra_20261027` (44 filas). No se cambiaron datos.
- Pruebas: 335 correctas (base normal) y 333 + 2 omitidas (reconstruida). Prueba nueva: `test_zz_zz_27oct_flujos.py`.

### 24.55 Factura parcial por posiciones, cuadre de entregas y buscador del PV (Erika, 27/10/2026 17:07-17:26)
- **Factura total o parcial** (caso Komatsu: PV de 5 posiciones, se entregan 4). En "Nueva factura / Boleta", al elegir el PV aparece "¿Vas a facturar todo el pedido o solo una parte?".
  - En **Factura parcial**, cada posición tiene su check y su cantidad. Muestra lo pedido, lo que tiene guía y lo ya facturado. Solo se factura lo entregado con guía y nunca más de lo pedido; el servidor también lo bloquea.
  - Lo que no se factura lleva **motivo obligatorio** (En importación / En fabricación / Falta ingreso del cliente / Otro) y un **comentario**. Es nota interna: no sale en el PDF ni la ve el cliente. Queda guardado con quién lo escribió y cuándo.
  - Una "Factura total" de un PV que ya tuvo una parcial lleva solo lo que falta. Si no cubre todo, pide elegir "Factura parcial".
  - La "Factura total" sigue permitida antes de la entrega, para los clientes que pagan primero.
- **Subtotal, IGV (18%) y TOTAL** debajo de los productos de la factura. Antes solo salía el TOTAL.
- **Ventas ▸ PV**: debajo del estado sale "Entregado X%" y "Facturado Y%" con los colores de avance, y en rojo "Falta facturar: posición N". Al pasar el mouse se ve el motivo.
- **Inicio de Erika (Dashboard) ▸ "Control de hoy: facturación y entregas"** (solo gerencia):
  - los PV con posiciones entregadas sin facturar o pendientes, con su motivo y los días desde el PV;
  - los despachos que salieron del almacén y no cuadran: sin guía, guía anulada o inexistente, cantidad del kardex distinta a la de la guía, o Entregado sin fecha real. Muestra quién despachó.
  - En Supabase hoy hay 8 despachos que descontaron stock y no tienen guía.
- **Entregas ▸ Confirmar entrega**: nuevo campo opcional "N° de ingreso del cliente", el número que su sistema da al recibir. Se ve debajo de la fecha de entrega y queda en auditoría.
- **Crear PV (Pedido de venta)** (antes "Crear PV Cliente"). El buscador de cotizaciones:
  - la lista va encima de todo, con su propio scroll, y ya no queda tapada;
  - pone primero la coincidencia exacta del número ("17" → COT-000017);
  - muestra solo las "Aceptada por Cliente" sin PV, y avisa por qué no salen las demás (ya tienen PV, o están en otro estado).
- Base: migración `037_factura_parcial.sql` aplicada en Supabase. Agrega columnas vacías: `comprobantes.facturacion_tipo`, `comprobantes.pendientes_json` y `despachos.ingreso_cliente`. Respaldos previos: `respaldo_20261015.comprobantes_20261027` (37 filas) y `respaldo_20261015.despachos_20261027` (45 filas). No se cambiaron datos.
- Pruebas: 339 correctas (base normal) y 337 + 2 omitidas (reconstruida). Prueba nueva: `test_zz_zz_27oct_parcial.py`.

### 24.56 "Cubierto con stock", columnas N° PV y N° PC separadas, N° PC en Guías (Erika, 27/10/2026 17:37-17:45)
- PV-KCF-000026 decía "Pendiente de compra" aunque había stock. Causa: el stock separado para otros pedidos se restaba dos veces (`routes/abastecimiento.py`, `_separado_por_pedido`). Ahora lo separado para ese PV cuenta para él y el resto sale del stock libre. La pastilla dice "✔ Cubierto con stock".
- Ventas: el N° PV (Pedido de venta) y el N° PC (Pedido del cliente) van en dos columnas separadas en PV (vista principal y completa), Entregas, Guías y Facturas. Si el cliente no mandó PC: "—".
- Guías: las guías se guardaban con el PC del cliente vacío. La columna "N° PC (Pedido del cliente)" ahora toma el número vigente del PV (por cotización o por N° PV), igual que el PDF de la guía. El PDF ya mostraba "PV (PEDIDO DE VENTA)" y "PC (PEDIDO DEL CLIENTE)" en "Documentos relacionados".
- Sin cambios en la base.

### 24.57 Descripción del cliente por línea: los dos nombres en todo (Erika y Hellen, 27/10/2026 20:23, caso Komatsu)
- Por qué "no se guardaba": en la base sí se guardaba (PV-KCF-000028 la llevó al despacho, la guía y la factura). Lo que fallaba era lo que se veía:
  - Entregas y Guías mostraban solo el nombre del catálogo;
  - los PDF ponían la descripción del cliente EN LUGAR del nombre del maestro;
  - lo corregido en el PV después de crear el despacho no llegaba;
  - la cotización no tenía el campo.
- Ahora cada línea lleva los dos nombres. Arriba va el "Nombre producto" del maestro y debajo "Según su pedido: … · Código del cliente: …". Se ve así en:
  - Cotización, PV, Entregas, Guía, Factura (total y parcial) y Nota de crédito;
  - los PDF de cotización, guía, factura y nota de crédito.
- Cotización: cada producto tiene "✏ Descripción del cliente" y "Código del cliente" (opcionales), que se guardan en `cotizacion_detalle`.
- Memoria por cliente y producto (tabla `cliente_producto_descripcion`): al guardar se recuerda cómo llama ese cliente a cada producto. En su próxima cotización se sugiere solo ("💡 Sugerido") y se puede cambiar.
- PV: además de la descripción, tiene "Código del cliente". Al guardar el PV, lo corregido pasa a lo que aún no se emitió: despachos sin guía, guías en Borrador y facturas en Borrador. Lo emitido no se toca.
- Base: migración `038_descripcion_cliente.sql` aplicada en Supabase. Agrega 2 columnas vacías y 1 tabla nueva. Respaldo previo en `respaldo_20261015.cotizacion_detalle_20261027` (116 filas). No borra datos.
- Pruebas: 343 correctas (base normal) y 341 + 2 omitidas (reconstruida). Prueba nueva: `test_zz_zz_27oct_desc_cliente.py`.

### 24.58 Factura parcial por cantidad, guía por saldo, agente de retención, sin "Crear despacho" (Erika, 27/10/2026 20:34-20:48)
- Por qué no aparecía la factura parcial: el PV se elige por código y la pantalla miraba si el modal estaba "visible" con un método que en ventanas fijas siempre dice "no". Ahora mira el campo del PV y el selector "Factura total / Factura parcial" sale siempre que hay PV, aunque tenga 1 solo producto.
- Factura parcial: se elige por posición y por cantidad (por ejemplo 8 de 10). El máximo es lo que falta facturar del PV; nunca más de lo que pide el PV (el servidor también lo bloquea).
  - Aviso rojo "FACTURA PARCIAL: esta factura lleva X de Y unidades del PV…", con lo que queda por facturar y el motivo.
  - Si se factura algo que aún no salió con guía: "⚠ X sin guía" en la fila y aviso en rojo (se permite, como en la regla "factura sí sin stock").
- Guía parcial y guía por saldo: un PV puede tener 2 o 3 guías. Encima de los productos de la guía:
  - 🔴 "GUÍA PARCIAL": qué posición queda con saldo;
  - ✅ "GUÍA POR SALDO" (completa el PV) o "GUÍA COMPLETA";
  - ⛔ "NO SE PODRÁ GUARDAR" si pasa de lo que pide el PV;
  - tabla por posición: Pide el PV, Ya salió con guía, Esta guía, Saldo. Funciona aunque la guía se haya hecho desde la cotización.
- La guía ahora guarda la cantidad escrita en la tabla (antes guardaba la cantidad original de la cotización).
- Agente de retención del cliente (Sí / No): se consulta en el padrón público de SUNAT (se baja una vez al día y cada cliente se revisa cada 30 días). En la factura:
  - NO es agente: no hay retención, el botón queda bloqueado y el servidor la quita;
  - SÍ es agente: la retención se activa sola;
  - sin dato: sigue como antes.
  - Si SUNAT no responde, un aprobador lo marca a mano ("Marcar Sí / Marcar No"), con auditoría (quién y cuándo, hora de Lima). Lo marcado a mano no se cambia solo.
- Cotizaciones ▸ ⋮: se quitó "Crear despacho" (el despacho nace del PV).
- Entregas ▸ Estado compra: si falta stock dice "🔴 Sin stock: proceder a comprar" (antes "Pendiente por compra"). Si el despacho es nuevo y aún no tenía dato, lo revisa solo en vez de mostrar "-".
- Base: migración `039_agente_retencion.sql` aplicada en Supabase. Agrega 5 columnas vacías a `clientes`. Respaldo previo en `respaldo_20261015.clientes_20261027` (42 filas). No borra datos.
- Pruebas: 348 correctas (base normal) y 346 + 2 omitidas (reconstruida). Prueba nueva: `test_zz_zz_27oct_retencion_guia.py`.

### 24.59 Distrito automático, citas reprogramadas, KPI de cumplimiento, avisos en viñetas, sin barra horizontal (Erika, 27/10/2026 23:48 - 28/10/2026 00:31)
- **PV ▸ Lugar entrega** y **Entregas ▸ Distrito**: salen solos, solo el distrito. Si el cliente recoge ("🏬 Recoge en nuestro local" en el formulario del PV): KCF = San Martín de Porres, AGD = Breña. Si no se lee el distrito, sale en rojo "⚠ Falta distrito: corrígelo en el PV". En Entregas ya nadie lo escribe a mano (el servidor lo rechaza). Nuevo campo "Distrito de entrega" en el formulario del PV, con lista. Lo escrito antes a mano en Entregas queda guardado en la base, pero ya no se muestra.
- **PV-KCF-000029**: Entregas decía "Cubierto con stock" y el PV "Pendiente de compra". Ahora Entregas sigue el estado del PV. Lo correcto es "Pendiente de compra": hay 8 separados de 20, y PV más antiguos piden 58 más.
- **N° de despacho corto**: DESP-KCF-000008 / DESP-AGD-000001, con el piso de Configuración ▸ Correlativos (nueva fila DESP por empresa). Los despachos antiguos NO se renombraron (falta el "sí" escrito de Erika).
- **Entregas, dos columnas**: "Fecha programada (cita)" y "Fecha real de entrega".
  - La cita se puede cambiar las veces que haga falta (2.ª, 3.ª, 4.ª…), pidiendo el motivo: No hubo transporte, No llegó el producto, El cliente pidió otro día, El cliente no recibió u Otro (con comentario).
  - Queda el historial con fecha, hora de Lima y usuario. Botones "Próximo martes / jueves". La primera cita queda guardada.
  - La fecha real de entrega es una sola.
- **Quitado el botón "Rechazado por el cliente"** de Acción (Erika 28/10 00:13): si no se entrega, se reprograma la cita. Si la mercadería vuelve al almacén, "Anular" devuelve el stock. Los despachos antiguos con ese estado se siguen viendo.
- **Reportes ▸ Colaboradores ▸ Cumplimiento de entregas** (solo Erika):
  - días desde que llega el PV hasta la entrega real, a tiempo o tarde contra la primera cita, reprogramaciones y atrasados;
  - por pedido, cliente, mes o responsable, con promedio mensual.
- **Avisos de confirmación en viñetas** en todos los módulos (componente `static/js/avisos.js`):
  - datos del documento en azul (Despacho, PV, PC del cliente, Cotización, Cliente) y productos;
  - lo importante en rojo.
  - Aplicado en Ventas (despachar, entregar, anular, eliminar, confirmaciones), Compras, Maestros y Herramientas.
- **Recibir mercadería con diferencia** (Erika 28/10 00:31): aviso contundente. Dice "La OC fue emitida por 50 PAR. Estás registrando 1. Diferencia: 49 FALTAN", y pregunta "¿Estás seguro de que contaste bien?". Si llegó así: coordinar con el proveedor y avisar al jefe inmediato. La explicación es **obligatoria**. El conteo sigue siendo a ciegas. En "Hoy en Compras" sale en rojo "Órdenes recibidas con diferencia" durante 7 días.
- **"N° de ingreso del cliente"** quitado de todas las pantallas. La columna y sus datos siguen en Supabase. "Control de hoy" no depende de ese dato.
- **Sin abreviaturas de empresa**: "KC" pasa a "KCF" en todo el ERP (se usa el código de la empresa).
- **Ninguna tabla con barra horizontal**: medido con navegador en 1366 px y 1920 px en todos los módulos y pestañas (Ventas, Compras, Finanzas, SUNAT, etc.). Los textos largos bajan de línea.
- **Migración 041** aplicada en Supabase el 28/10/2026. Solo agrega:
  - pedido_compra_pc.distrito_entrega;
  - despachos.fecha_cita_inicial (copiada de la cita actual);
  - tabla despacho_reprogramaciones (con RLS).
  - Respaldo previo: respaldo_20261015.pedido_compra_pc_20261028 (53 filas) y respaldo_20261015.despachos_20261028 (50 filas). No se borró nada.
- Se conservan los cambios del PR #15 (sesiones y contraseñas, migración 040).
- Pruebas: 357 bien en la base de prueba y 355 bien + 2 omitidas en la copia con la estructura real.

### 24.60 Distrito que se llena solo, Compras con documentos en orden y columnas alineadas (Erika, 28/10/2026 12:03-12:16)
- **Distrito de entrega del PV se llena solo**. Se busca en este orden:
  1. el cliente recoge en nuestro local;
  2. se lee en la dirección de entrega;
  3. si la entrega es en la dirección fiscal del cliente, el distrito fiscal guardado en el cliente;
  4. el que ya se eligió antes para esa misma dirección en otro PV (el más reciente);
  5. si hay clave de SUNAT en Render (DECOLECTA_TOKEN), el distrito del domicilio fiscal del RUC. Solo se usa si la entrega es en esa dirección, y se guarda en el cliente.
  - Si nada lo da, se elige UNA sola vez: queda guardado para ese cliente y esa dirección.
  - Las listas de PV y Entregas usan lo mismo, así que los rojos se van llenando solos.
  - Con la clave de SUNAT, una vez cada 12 horas se completan los clientes con PV que no tienen distrito (cada RUC se consulta una sola vez).
- **Sin la clave de SUNAT**, las direcciones como "MZA. B LOTE 17 URB. ALFONSO COBIAN" no traen distrito y hay que elegirlo la primera vez. La clave la pone Adriel en Render.
- **Compras ▸ Pedidos por comprar**:
  - documentos siempre en este orden: PV (Pedido de venta), PC (Pedido del cliente), Cotización, N° despacho, con los N° en azul;
  - "Ya en órdenes" pasa a "Ya pedido al proveedor (en OC (Proveedor))". Cuenta las OC aprobadas y por aprobar; las anuladas no cuentan. Si una parte aún no está aprobada, sale debajo en rojo "N por aprobar";
  - todas las tablas con las mismas columnas y anchos fijos ("Nombre producto" 30 %); los nombres largos bajan de línea;
  - el resaltado usa amarillo claro estándar;
  - la pastilla dice "PV conforme" (solo cambia lo que se ve; el dato guardado no cambia).
- **Migración 042** (aplicada el 28/10/2026): clientes.distrito_fiscal, distrito_fiscal_fuente y distrito_fiscal_revisado_en. Solo agrega. Respaldo: respaldo_20261015.clientes_20261028 (43 filas).
- Se incluye el PR #17 de main (solo Erika crea o elimina usuarios y ve Planilla).
- Pruebas: 364 bien.

### 24.61 Hasta 3 cuentas por proveedor con regla de ahorro, y arreglos de la OC (Erika, 28/10/2026 17:23-17:34)
- **Maestros ▸ Proveedores ▸ Datos bancarios**: Cuenta 1, 2 y 3, cada una con banco, tipo, moneda, N° de cuenta y CCI. Cada cuenta con número necesita su banco.
- **Regla de ahorro** (routes/cuentas_proveedor.py): al pagar, **KCF usa la cuenta BBVA** del proveedor y **AGD su cuenta BCP** (el banco sale de Configuración ▸ Empresas). Si hay dos del mismo banco, gana la de la moneda del documento. Si no tiene, se usa la siguiente cuenta registrada con **aviso en rojo** ("el banco puede cobrar comisión").
  - Se aplica en: ficha de la OC al crearla, detalle de la OC, "Pagar a" de Compras, "Pagar a" de Finanzas (CxP) y la OC impresa para el proveedor.
- **Migración 043** (aplicada): proveedores.moneda_cuenta y banco/tipo_cuenta/moneda_cuenta/numero_cuenta/cci 2 y 3. La cuenta que ya existía queda como Cuenta 1 sin mover nada. Respaldo: respaldo_20261015.proveedores_20261028 (59 filas).
- Botón rojo: **"Crear OC - Orden de compra (Proveedor)"** (también en la ayuda y los avisos).
- Pastilla de la línea para stock: **"Para stock - Sin PC (Pedido del cliente)"**. El Total de cada línea queda en una sola línea ("S/ 70.00").
- Aviso "Compra para stock": amarillo claro estándar con borde rojo a la izquierda, título rojo y viñetas cortas.
- **Nota interna (No la ve el proveedor)** en la OC, debajo de "Notas para el proveedor". Se ve en el detalle con 🔒 y nunca sale en la OC impresa ni en el PDF. **Migración 044** (aplicada): ordenes_compra.nota_interna. Solo agrega.
- Alta de proveedor: el código PROV-0000 ya no falla si existe un código escrito distinto.
- Pruebas: 368 bien (y 366 + 2 omitidas en el esquema reconstruido).

### 24.62 Columna "Ítem" en las ventanas de Compras (Erika, 28/10/2026 18:35)
- **Recibir mercadería**: primera columna "Ítem" (1, 2, 3...) y nueva columna "Para": el PV y el cliente, o "Para stock - Sin PC (Pedido del cliente)". Debajo dice cuánto falta llegar. Así se distinguen dos líneas del mismo producto (una para un PV y otra para stock).
- "Ítem" también en: líneas de la nueva OC, Productos y Diferencias del detalle de la OC, y el resultado de la recepción.
- En el detalle de la OC, la línea para stock dice "Para stock - Sin PC (Pedido del cliente)" (antes "Stock").
- Sin cambios en la base. Pruebas: 368 bien.
