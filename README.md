# ERP Multiempresa (KCF / AGD)

ERP web para empresas B2B que compran y venden **bajo pedido**: cotizaciones, pedidos del cliente (PC),
guías, facturación con IGV, compras a proveedores y finanzas (cuentas por cobrar/pagar y flujo de caja).

Tecnología: Python 3.11 + Flask, PostgreSQL (Supabase), HTML/CSS/JavaScript sin frameworks.

## 1. Instalación local

```bash
# 1) Entrar a la carpeta del proyecto
cd pruebasweb

# 2) Crear y activar un entorno virtual
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Mac / Linux:
source .venv/bin/activate

# 3) Instalar dependencias
pip install -r requirements.txt
```

> WeasyPrint (PDF) en Windows necesita GTK. Si falla la instalación, ver
> https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows. El resto del ERP funciona igual.

## 2. Configuración

1. Copia `.env.example` como `.env`.
2. Completa `DATABASE_URL` (Supabase > Settings > Database > Connection string > URI) y `SECRET_KEY`.
3. **No subas `.env` a GitHub** (ya está en `.gitignore`).

En Render las variables se configuran en *Environment* (ver `render.yaml`).

## 3. Ejecutar

```bash
python main.py            # abre http://localhost:5000  (o el PORT del .env)
# Producción:
gunicorn main:app
```

## 4. Base de datos

- El sistema usa las tablas que ya existen en Supabase. **No se borra ni se modifica ningún dato existente.**
- El módulo Finanzas crea automáticamente (la primera vez que se abre) la tabla `finanzas_pagos`
  y la columna opcional `comprobantes_proveedor.fecha_vencimiento`. El mismo SQL está en
  `migrations/001_finanzas.sql` por si se prefiere ejecutarlo a mano.
- `migrations/002_revision_duplicados.sql` contiene consultas de solo lectura para revisar duplicados
  históricos e índices únicos opcionales (comentados).
- Contraseñas antiguas en texto plano: siguen funcionando, pero se recomienda convertirlas a hash:
  ```bash
  python scripts/hashear_passwords.py           # muestra cuántas hay (no cambia nada)
  python scripts/hashear_passwords.py --aplicar # las convierte (los usuarios usan la misma contraseña)
  ```

## 5. Roles

El rol sale de la columna `usuarios.rol` y se agrupa con variables de entorno:

| Variable | Qué permite | Valor por defecto |
|---|---|---|
| `ROLES_ADMIN` | Configuración y seguridad (empresas, usuarios, correlativos, parámetros) | admin, administrador, superadmin, gerencia_total, gerencia |
| `ROLES_APROBADORES` | Validar, aceptar, rechazar y generar cotizaciones | hellen, erika, admin, … |
| `ROLES_FINANZAS` | Registrar y anular cobros/pagos | finanzas, contabilidad, tesoreria, gerencia (+ admin y aprobadores) |
| `ROLES_ALMACEN` | Inventario: entradas, salidas, traslados, ventas entre empresas | almacen, almacenero, logistica, logistico (+ admin y aprobadores) |
| `ROLES_CONTROL_INVENTARIO` | Inventario: conteos físicos (logística no cuenta) | control, inventario, auditor, contabilidad, finanzas (+ admin y aprobadores) |

Flujo de cotización: **Borrador → En revisión / Por validar → Validado → Generada → Aceptada por Cliente**.
Con `COTIZACION_REQUIERE_VALIDACION=false` un vendedor puede generar sin validación previa.

## 6. Pruebas automáticas

Las pruebas usan una base PostgreSQL **local y vacía** (nunca la de producción; el script se niega a usar Supabase):

```bash
pip install pytest
createdb erp_pruebas
# Windows (PowerShell): $env:TEST_DATABASE_URL="postgresql://postgres:clave@localhost:5432/erp_pruebas"
export TEST_DATABASE_URL="postgresql://postgres:clave@localhost:5432/erp_pruebas"
pytest -q tests
```

`tests/schema_pruebas.sql` es un esquema reconstruido a partir del código solo para pruebas.

## Inventario (multiempresa y multisede)

- Empresas: tabla `erp_empresas` (Configuración ▸ Empresas). Sedes físicas: tabla `almacenes` (Maestros ▸ Almacenes). Se pueden agregar más sin tocar el código.
- El stock se guarda por empresa + sede + producto (`inv_stock`). Cada cambio es un movimiento del kardex (`inv_movimientos`) con costo promedio ponderado. Nada se edita ni se borra; los errores se corrigen con un movimiento de reversa.
- `productos.stock` se mantiene como la suma de todas las empresas y sedes, para que Ventas y Productos sigan funcionando. Si un producto ya está en Inventario, su stock no se puede cambiar desde la ficha de Productos.
- Las tablas se crean solas la primera vez (script equivalente: `migrations/003_inventario.sql`).
- Las recepciones aprobadas en Compras ya no suman stock por su cuenta: se ingresan desde Inventario ▸ Entradas y salidas indicando empresa y sede.

