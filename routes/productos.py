# routes/productos.py
from flask import Blueprint, render_template, request, jsonify, session, flash, redirect, url_for, Response
from utils import login_required
from routes.multiempresa import empresa_filtro
from database import db_query, db_execute, db_tx
from psycopg2.extras import RealDictCursor
from datetime import datetime

# ============================================================
# BLUEPRINT - CON url_prefix
# ============================================================
productos_bp = Blueprint('productos', __name__, url_prefix='/productos')

# ============================================================
# FUNCIONES DE UTILIDAD
# ============================================================

def sincronizar_secuencia_productos(cur):
    """
    🔧 Auto-sanación: Sincroniza la secuencia de la primary key `id`
    con el MAX(id) actual. Evita el error:
    'duplicate key value violates unique constraint "productos_pkey"'.
    """
    try:
        cur.execute("""
            SELECT setval(
                pg_get_serial_sequence('productos', 'id'),
                (SELECT COALESCE(MAX(id), 0) + 1 FROM productos),
                false
            )
        """)
    except Exception as e:
        print(f"⚠️ No se pudo sincronizar la secuencia: {e}")


def generar_codigo_con_lock(cur):
    """
    Genera el siguiente código de forma ATÓMICA dentro de la transacción actual.
    El advisory lock evita que dos peticiones simultáneas calculen el mismo número.
    """
    # 🔒 Bloqueo: cualquier otra transacción que intente esto mismo esperará aquí
    cur.execute("SELECT pg_advisory_xact_lock(hashtext('productos_codigo_lock'))")

    cur.execute("""
        SELECT MAX(CAST(REPLACE(codigo, 'PRD-', '') AS INTEGER)) as max_num
        FROM productos 
        WHERE codigo LIKE 'PRD-%' 
        AND codigo ~ '^PRD-[0-9]+$'
    """)
    row = cur.fetchone()
    max_num = row['max_num'] if row and row['max_num'] is not None else 0
    nuevo_num = max_num + 1
    return f"PRD-{str(nuevo_num).zfill(4)}"


# ============================================================
# COLUMNAS NUEVAS (se crean solas; script equivalente en migrations/008_correccion_13_errores.sql)
# ============================================================
import threading
SQL_DDL_PRODUCTOS = """
    ALTER TABLE productos ADD COLUMN IF NOT EXISTS tipo_operacion VARCHAR(60);
"""
_columnas_listas = False
_lock_columnas = threading.Lock()


def asegurar_columnas_productos():
    """Crea las columnas que el formulario de productos necesita y que la base antigua no tenía."""
    global _columnas_listas
    if _columnas_listas:
        return
    with _lock_columnas:
        if _columnas_listas:
            return
        with db_tx() as conn:
            cur = conn.cursor()
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('productos_ddl'))")
            cur.execute(SQL_DDL_PRODUCTOS)
        _columnas_listas = True


# Tipo de operación: casillas Venta / Compra / Inventariable. Se guarda como texto "venta,compra".
TIPOS_OPERACION = ('venta', 'compra', 'inventariable')


def normalizar_tipo_operacion(data, defecto=None):
    """Lee 'tipo_operacion' (texto "venta,compra" o lista) o 'operation' (nombre de las casillas del formulario).
    Devuelve el texto ordenado, '' si no marcó ninguna, o `defecto` si el dato no vino."""
    if 'tipo_operacion' in data:
        valor = data.get('tipo_operacion')
    elif 'operation' in data:
        valor = data.get('operation')
    else:
        return defecto
    if valor is None:
        return defecto
    if isinstance(valor, str):
        valor = valor.split(',')
    elegidos = {str(v).strip().lower() for v in valor}
    return ','.join(t for t in TIPOS_OPERACION if t in elegidos)


# Listas que el formulario ofrece siempre (antes estaban escritas a mano en la plantilla)
MARCAS_BASE = [
    'Nike', 'Adidas', 'Puma', 'Reebok', 'New Balance', 'Under Armour', 'Columbia', 'The North Face', 'Patagonia',
    'Dickies', 'Carhartt', '3M', 'Honeywell', 'DuPont', 'Samsung', 'LG', 'Sony', 'Panasonic', 'HP', 'Dell', 'Lenovo',
    'Apple', 'Xiaomi', 'Huawei', 'Caterpillar', 'Bosch', 'Makita', 'DeWalt', 'Stanley', 'Ferretería Industrial',
    'Casa de Herramientas', 'Otros',
]
CATEGORIAS_BASE = [
    'Seguridad Industrial', 'Mobiliario de Oficina', 'Tecnología', 'Ferretería', 'Limpieza', 'Cuidado Personal',
    'Iluminación', 'Herramientas Eléctricas', 'Herramientas Manuales', 'Equipos de Protección', 'Señalización',
    'Materiales de Construcción', 'Pinturas y Acabados', 'Fijaciones y Anclajes', 'Jardinería', 'Automotriz',
    'Electrónica', 'Papelería',
]

# tabla maestra -> (columna en productos, prefijo del código)
_MAESTROS = {'marcas': ('marca', 'MAR'), 'categorias': ('familia', 'CAT')}


def registrar_en_maestro(cur, tabla, nombre):
    """Si el usuario escribió una marca/categoría nueva, la agrega a su tabla maestra para que salga en la lista.
    Nunca hace fallar el guardado del producto (usa un SAVEPOINT)."""
    nombre = (nombre or '').strip()
    if tabla not in _MAESTROS or not nombre:
        return
    prefijo = _MAESTROS[tabla][1]
    cur.execute("SAVEPOINT sp_maestro")
    try:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f'maestro_{tabla}',))
        cur.execute(f"SELECT 1 FROM {tabla} WHERE LOWER(TRIM(nombre)) = LOWER(%s) LIMIT 1", (nombre,))
        if not cur.fetchone():
            cur.execute(f"""SELECT COALESCE(MAX(CAST(SUBSTRING(codigo FROM %s) AS INTEGER)), 0) AS n
                            FROM {tabla} WHERE codigo ~ %s""", (f'^{prefijo}-([0-9]+)$', f'^{prefijo}-[0-9]+$'))
            fila = cur.fetchone()
            n = (fila['n'] if isinstance(fila, dict) else fila[0]) or 0
            cur.execute(f"INSERT INTO {tabla} (codigo, nombre, tipo, activo) VALUES (%s, %s, %s, TRUE)",
                        (f'{prefijo}-{n + 1:04d}', nombre, 'General'))
        cur.execute("RELEASE SAVEPOINT sp_maestro")
    except Exception as e:
        cur.execute("ROLLBACK TO SAVEPOINT sp_maestro")
        print(f"⚠️ No se pudo registrar '{nombre}' en {tabla}: {e}")


def opciones_maestro(tabla, base, actual=None):
    """Opciones del desplegable: la lista base + lo que hay en la tabla maestra + lo ya usado en productos
    + el valor actual del producto (así una marca/categoría personalizada nunca desaparece al reabrir)."""
    columna = _MAESTROS[tabla][0]
    opciones = list(base)
    vistos = {o.lower() for o in opciones}
    extra = []
    for consulta in (f"SELECT nombre AS v FROM {tabla} WHERE COALESCE(activo, true) = true",
                     f"SELECT DISTINCT {columna} AS v FROM productos WHERE COALESCE(activo, true) = true"):
        try:
            extra += [(f.get('v') or '').strip() for f in (db_query(consulta) or [])]
        except Exception as e:
            print(f"⚠️ No se pudieron leer opciones de {tabla}: {e}")
    if actual:
        extra.append(str(actual).strip())
    for v in sorted(extra, key=str.lower):
        if v and v.lower() not in vistos:
            vistos.add(v.lower())
            opciones.append(v)
    return opciones


def stock_por_sede(producto_id):
    """Stock que el producto ya tiene en Inventario, por empresa y sede (para la tarjeta 'Agregar stock inicial')."""
    try:
        from routes.inventario import asegurar_tablas_inventario
        asegurar_tablas_inventario()
        filas = db_query("""
            SELECT s.empresa_id, s.almacen_id, s.cantidad,
                   COALESCE(NULLIF(e.nombre_corto, ''), e.codigo, '') AS empresa, COALESCE(a.nombre, '') AS sede
            FROM inv_stock s
            LEFT JOIN erp_empresas e ON e.id = s.empresa_id
            LEFT JOIN almacenes a ON a.id = s.almacen_id
            WHERE s.producto_id = %s AND s.cantidad > 0
            ORDER BY empresa, sede
        """, (producto_id,)) or []
        return [{'empresa_id': str(f['empresa_id']), 'almacen_id': str(f['almacen_id']),
                 'cantidad': float(f['cantidad']), 'empresa': f['empresa'], 'sede': f['sede']} for f in filas]
    except Exception as e:
        print(f"⚠️ No se pudo leer el stock por sede: {e}")
        return []


def _contexto_formulario(producto=None):
    producto = producto or {}
    return dict(
        marcas_opciones=opciones_maestro('marcas', MARCAS_BASE, producto.get('marca')),
        categorias_opciones=opciones_maestro('categorias', CATEGORIAS_BASE, producto.get('familia')),
    )


# Stock en Productos: SIEMPRE el total del grupo (todas las empresas y sedes = SUM(inv_stock.cantidad)).
# Si el producto aún no tiene filas en inv_stock se usa productos.stock (dato antiguo).
# stock_empresa = solo la empresa elegida arriba (NULL con "Todas"); stock_detalle = "KCF 25 · AGD 0".
SQL_STOCK_PRODUCTO = """
    COALESCE((SELECT SUM(s.cantidad) FROM inv_stock s WHERE s.producto_id = p.id), p.stock) AS stock,
    COALESCE((SELECT SUM(s.cantidad) FROM inv_stock s WHERE s.producto_id = p.id), p.stock) AS stock_grupo,
    CASE WHEN %s IS NULL THEN NULL
         ELSE COALESCE((SELECT SUM(s.cantidad) FROM inv_stock s WHERE s.producto_id = p.id AND s.empresa_id = %s), 0)
    END AS stock_empresa,
    (SELECT string_agg(x.cod || ' ' || CASE WHEN x.c = TRUNC(x.c) THEN TRUNC(x.c)::bigint::text
                                            ELSE RTRIM(RTRIM(x.c::text, '0'), '.') END, ' · ' ORDER BY x.cod)
       FROM (SELECT COALESCE(e.codigo, '?') AS cod, SUM(s.cantidad) AS c
               FROM inv_stock s LEFT JOIN erp_empresas e ON e.id = s.empresa_id
              WHERE s.producto_id = p.id GROUP BY 1) x) AS stock_detalle,
"""


def numero_limpio(v):
    """25.0000 -> 25 ; 2.5000 -> 2.5 (el stock se muestra sin ceros de más en todas las pantallas)."""
    if v is None or isinstance(v, (bool, int)):
        return v
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    return int(f) if f.is_integer() else f


def _limpiar_stock(filas):
    for f in filas or []:
        for k in ('stock', 'stock_grupo', 'stock_empresa', 'stock_minimo'):
            if k in f:
                f[k] = numero_limpio(f[k])
    return filas


def safe_float(value, default=0):
    """Convierte a float de forma segura"""
    if value is None or value == '':
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value, default=0):
    """Convierte a int de forma segura"""
    if value is None or value == '':
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def obtener_ultimo_codigo_producto():
    """Obtiene el último código de producto para generar el siguiente"""
    try:
        # Obtener el número más alto
        result = db_query("""
            SELECT MAX(CAST(REPLACE(codigo, 'PRD-', '') AS INTEGER)) as max_num
            FROM productos 
            WHERE codigo LIKE 'PRD-%' 
            AND codigo ~ '^PRD-[0-9]+$'
        """)

        print(f"📋 Resultado de MAX: {result}")

        max_num = 0
        if result and result[0].get('max_num') is not None:
            max_num = int(result[0]['max_num'])
            print(f"📊 Máximo número encontrado: {max_num}")
        else:
            print("⚠️ No se encontraron códigos PRD-XXXX")

        nuevo_num = max_num + 1
        nuevo_codigo = f"PRD-{str(nuevo_num).zfill(4)}"

        print(f"✅ Nuevo código generado: {nuevo_codigo}")
        return nuevo_codigo

    except Exception as e:
        print(f"❌ Error generando código: {e}")
        import traceback
        traceback.print_exc()
        # Fallback: obtener el último ID y sumar 1
        try:
            result = db_query("SELECT MAX(id) as max_id FROM productos")
            if result and result[0].get('max_id'):
                nuevo_num = int(result[0]['max_id']) + 1
                return f"PRD-{str(nuevo_num).zfill(4)}"
        except:
            pass
        return "PRD-0011"


# ============================================================
# RUTAS PARA PÁGINAS HTML
# ============================================================

@productos_bp.route('/')
@login_required
def productos():
    """Página principal de productos - Redirige a nuevo producto"""
    codigo_auto = obtener_ultimo_codigo_producto()
    return render_template('nuevo_producto.html',
                           active_tab='nuevo',
                           codigo_auto=codigo_auto,
                           editando=False,
                           producto=None,
                           tipos_operacion=['venta'],
                           stock_sedes=[],
                           **_contexto_formulario())


@productos_bp.route('/nuevo')
@login_required
def productos_nuevo():
    """Página de nuevo producto con código automático"""
    codigo_auto = obtener_ultimo_codigo_producto()
    return render_template('nuevo_producto.html',
                           active_tab='nuevo',
                           codigo_auto=codigo_auto,
                           editando=False,
                           producto=None,
                           tipos_operacion=['venta'],
                           stock_sedes=[],
                           **_contexto_formulario())


@productos_bp.route('/base-datos')
@login_required
def productos_base_datos():
    """Página de base de datos de productos"""
    return render_template('base_datos_producto.html',
                           active_tab='base-datos',
                           producto=None,
                           editando=False)


@productos_bp.route('/comparativo')
@login_required
def productos_comparativo():
    """Página de comparativo de costos"""
    return render_template('comparativo_costos.html',
                           active_tab='comparativo',
                           producto=None,
                           editando=False)


@productos_bp.route('/editar/<int:producto_id>')
@login_required
def productos_editar(producto_id):
    try:
        asegurar_columnas_productos()
        producto = db_query("""
            SELECT 
                id, codigo, descripcion, descripcion_larga,
                modelo, marca, familia, categoria_derivada,
                unidad, peso, volumen, observaciones, transporte,
                costo_unitario, precio_unitario, stock, stock_minimo,
                estado, presentacion_proveedor, presentacion_venta,
                venta_minima, codigo_barras, origen, tiempo_entrega,
                abastecimiento, activo, proveedor_id, tipo_operacion
            FROM productos
            WHERE id = %s AND activo = TRUE
        """, (producto_id,))

        if not producto:
            flash('Producto no encontrado', 'error')
            return redirect(url_for('productos.productos_base_datos'))

        producto_dict = dict(producto[0])
        print(f"📝 Producto encontrado: {producto_dict}")

        codigo_auto = obtener_ultimo_codigo_producto()

        # Productos antiguos (sin tipo de operación guardado) se muestran como "Venta", igual que uno nuevo
        tipo_op = producto_dict.get('tipo_operacion')
        tipos_operacion = ['venta'] if tipo_op is None else [t for t in tipo_op.split(',') if t]

        return render_template('nuevo_producto.html',
                               active_tab='nuevo',
                               codigo_auto=codigo_auto,
                               producto=producto_dict,
                               editando=True,
                               tipos_operacion=tipos_operacion,
                               stock_sedes=stock_por_sede(producto_id),
                               **_contexto_formulario(producto_dict))

    except Exception as e:
        print(f"❌ Error en productos_editar: {e}")
        import traceback
        traceback.print_exc()
        flash('Error al cargar el producto', 'error')
        return redirect(url_for('productos.productos_base_datos'))


# ============================================================
# ENDPOINTS API PARA PRODUCTOS
# ============================================================

@productos_bp.route('/api/productos', methods=['GET'])
@login_required
def get_productos():
    """Obtener todos los productos con filtros opcionales"""
    try:
        busqueda = request.args.get('q', '').strip()
        categoria = request.args.get('categoria', '').strip()
        marca = request.args.get('marca', '').strip()
        modelo = request.args.get('modelo', '').strip()
        from routes.inventario import asegurar_tablas_inventario
        asegurar_tablas_inventario()

        query = """
            SELECT 
                p.id, p.codigo, p.descripcion, p.descripcion_larga,
                p.modelo, p.marca, p.familia as categoria,
                p.categoria_derivada as subcategoria,
                p.unidad, p.peso, p.volumen, p.observaciones, p.transporte,
                p.costo_unitario, p.precio_unitario,
                """ + SQL_STOCK_PRODUCTO + """
                p.stock_minimo,
                p.estado, p.presentacion_proveedor, p.presentacion_venta,
                p.venta_minima, p.codigo_barras, p.origen, p.tiempo_entrega,
                p.abastecimiento, p.activo, p.fecha_creacion, p.updated_at,
                p.proveedor_id, pv.razon_social as proveedor_nombre
            FROM productos p
            LEFT JOIN proveedores pv ON pv.id = p.proveedor_id
            WHERE p.activo = TRUE
        """
        ef = empresa_filtro()
        params = [ef, ef]
        # Productos del grupo (sin empresa) o de la empresa elegida
        condiciones = ["(%s IS NULL OR p.empresa_id IS NULL OR p.empresa_id = %s)"]
        params += [ef, ef]

        if busqueda:
            condiciones.append("(p.codigo ILIKE %s OR p.descripcion ILIKE %s OR p.modelo ILIKE %s OR p.marca ILIKE %s)")
            params.extend([f'%{busqueda}%'] * 4)
        if categoria:
            condiciones.append("p.familia = %s")
            params.append(categoria)
        if marca:
            condiciones.append("p.marca = %s")
            params.append(marca)
        if modelo:
            condiciones.append("p.modelo = %s")
            params.append(modelo)

        if condiciones:
            query += " AND " + " AND ".join(condiciones)

        query += " ORDER BY fecha_creacion DESC"

        productos = _limpiar_stock(db_query(query, params))

        return jsonify({
            'success': True,
            'data': productos,
            'total': len(productos)
        })

    except Exception as e:
        print(f"❌ Error en get_productos: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@productos_bp.route('/api/productos/<int:producto_id>', methods=['GET'])
@login_required
def get_producto(producto_id):
    """Obtener un producto específico"""
    try:
        asegurar_columnas_productos()
        from routes.inventario import asegurar_tablas_inventario
        asegurar_tablas_inventario()
        ef = empresa_filtro()
        producto = db_query("""
            SELECT 
                p.id, p.codigo, p.descripcion, p.descripcion_larga,
                p.modelo, p.marca, p.familia as categoria, p.familia, p.tipo_operacion,
                p.categoria_derivada as subcategoria,
                p.unidad, p.peso, p.volumen, p.observaciones, p.transporte,
                p.costo_unitario, p.precio_unitario,
                """ + SQL_STOCK_PRODUCTO + """
                p.stock_minimo,
                p.estado, p.presentacion_proveedor, p.presentacion_venta,
                p.venta_minima, p.codigo_barras, p.origen, p.tiempo_entrega,
                p.abastecimiento, p.activo, p.fecha_creacion, p.updated_at,
                p.proveedor_id, pv.razon_social as proveedor_nombre
            FROM productos p
            LEFT JOIN proveedores pv ON pv.id = p.proveedor_id
            WHERE p.id = %s AND p.activo = TRUE
        """, (ef, ef, producto_id))

        if not producto:
            return jsonify({'success': False, 'error': 'Producto no encontrado'}), 404
        _limpiar_stock(producto)

        return jsonify({
            'success': True,
            'data': producto[0]
        })

    except Exception as e:
        print(f"❌ Error en get_producto: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@productos_bp.route('/api/productos', methods=['POST'])
@login_required
def create_producto():
    """Crear un nuevo producto"""
    try:
        print("📥 Recibiendo solicitud POST /api/productos")

        if request.content_type and 'application/json' in request.content_type:
            data = request.get_json()
        else:
            data = request.form.to_dict()
            foto = request.files.get('foto')
            if foto and foto.filename:
                data['foto'] = foto.filename

        print(f"📦 Datos recibidos: {data}")

        required_fields = ['descripcion', 'modelo', 'marca', 'familia', 'unidad', 'transporte']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'error': f'El campo "{field}" es requerido'
                }), 400

        asegurar_columnas_productos()
        tipo_operacion = normalizar_tipo_operacion(data, defecto='venta')

        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            # 🔧 PASO 1: Sincronizar secuencia de la PK (evita duplicate key)
            sincronizar_secuencia_productos(cur)

            # 🔧 PASO 2: Generar código (con advisory lock)
            codigo = generar_codigo_con_lock(cur)
            print(f"🆕 Código generado de forma segura: {codigo}")

            proveedor_id = data.get('proveedor_id') or None
            if proveedor_id == '':
                proveedor_id = None

            cur.execute("""
                INSERT INTO productos (
                    codigo, descripcion, descripcion_larga,
                    modelo, marca, familia, categoria_derivada,
                    unidad, peso, volumen,
                    observaciones, transporte,
                    costo_unitario, precio_unitario, stock,
                    stock_minimo, estado,
                    presentacion_proveedor, presentacion_venta,
                    venta_minima, codigo_barras,
                    origen, tiempo_entrega, abastecimiento,
                    proveedor_id, tipo_operacion,
                    activo
                ) VALUES (
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    TRUE
                )
                RETURNING id, codigo
            """, (
                codigo,
                data.get('descripcion'),
                data.get('descripcion_larga', ''),
                data.get('modelo'),
                data.get('marca'),
                data.get('familia'),
                data.get('categoria_derivada', '') or data.get('subcategoria', ''),
                data.get('unidad'),
                safe_float(data.get('peso')),
                safe_float(data.get('volumen')),
                data.get('observaciones', ''),
                data.get('transporte'),
                safe_float(data.get('costo_unitario')),
                safe_float(data.get('precio_unitario')),
                safe_int(data.get('stock')),
                safe_int(data.get('stock_minimo')),
                data.get('estado', 'activo'),
                data.get('presentacion_proveedor', ''),
                data.get('presentacion_venta', ''),
                safe_int(data.get('venta_minima'), 1),
                data.get('codigo_barras', ''),
                data.get('origen', ''),
                data.get('tiempo_entrega', ''),
                data.get('abastecimiento', ''),
                proveedor_id,
                tipo_operacion
            ))

            resultado = cur.fetchone()

            # Marca / categoría escritas a mano: quedan en sus tablas maestras para la próxima vez
            registrar_en_maestro(cur, 'marcas', data.get('marca'))
            registrar_en_maestro(cur, 'categorias', data.get('familia'))
            print(f"✅ Producto insertado: ID={resultado['id']}, Código={resultado['codigo']}")

            # Stock inicial (opcional): queda en el inventario con empresa y sede, como cualquier movimiento
            mensaje_stock = ''
            if safe_float(data.get('stock_inicial_cantidad')) > 0:
                from routes.inventario import registrar_stock_inicial, ErrorInventario, asegurar_tablas_inventario
                asegurar_tablas_inventario()
                try:
                    mov, pendiente = registrar_stock_inicial(
                        cur, producto_id=resultado['id'], empresa_id=data.get('stock_inicial_empresa'),
                        almacen_id=data.get('stock_inicial_almacen'), cantidad=data.get('stock_inicial_cantidad'),
                        costo_unitario=safe_float(data.get('costo_unitario')))
                except ErrorInventario as e:
                    raise ValueError(f'Stock inicial: {e}')
                mensaje_stock = (f" Stock inicial {mov['numero']}: queda pendiente hasta que un supervisor lo apruebe."
                                 if pendiente else f" Stock inicial registrado ({mov['numero']}).")

            return jsonify({
                'success': True,
                'data': {
                    'id': resultado['id'],
                    'codigo': resultado['codigo']
                },
                'message': f'Producto creado exitosamente con código {resultado["codigo"]}.' + mensaje_stock
            })

    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        print(f"❌ Error en create_producto: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@productos_bp.route('/api/productos/<int:producto_id>', methods=['PUT'])
@login_required
def update_producto(producto_id):
    """Actualizar un producto existente"""
    try:
        data = request.get_json()

        existente = db_query("SELECT id, codigo FROM productos WHERE id = %s AND activo = TRUE", (producto_id,))
        if not existente:
            return jsonify({'success': False, 'error': 'Producto no encontrado'}), 404

        codigo_existente = existente[0]['codigo']

        proveedor_id = data.get('proveedor_id') or None
        if proveedor_id == '':
            proveedor_id = None

        # Si el producto ya está en el nuevo Inventario, el stock solo cambia con movimientos del kardex
        # (así nadie puede "corregir" el stock a mano sin dejar rastro).
        from routes.inventario import asegurar_tablas_inventario
        asegurar_tablas_inventario()
        asegurar_columnas_productos()
        # None = el dato no vino (p. ej. otra pantalla que edita el producto): se conserva lo guardado
        tipo_operacion = normalizar_tipo_operacion(data)

        with db_tx() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
              UPDATE productos SET
                  descripcion = %s, descripcion_larga = %s,
                  modelo = %s, marca = %s, familia = COALESCE(NULLIF(%s, ''), familia), categoria_derivada = %s,
                  unidad = COALESCE(NULLIF(%s, ''), unidad), peso = %s, volumen = %s,
                  observaciones = %s, transporte = %s,
                  costo_unitario = %s, precio_unitario = %s,
                  stock = CASE WHEN EXISTS (SELECT 1 FROM inv_stock WHERE producto_id = productos.id)
                               THEN stock ELSE %s END,
                  stock_minimo = %s,
                  estado = %s,
                  presentacion_proveedor = %s, presentacion_venta = %s,
                  venta_minima = %s, codigo_barras = %s,
                  origen = %s, tiempo_entrega = %s, abastecimiento = %s,
                  proveedor_id = %s,
                  tipo_operacion = COALESCE(%s, tipo_operacion),
                  updated_at = NOW()
              WHERE id = %s
          """, (
              data.get('descripcion'),
              data.get('descripcion_larga', ''),
              data.get('modelo'),
              data.get('marca'),
              data.get('familia') or data.get('categoria'),
              data.get('categoria_derivada', '') or data.get('subcategoria', ''),
              data.get('unidad'),
              safe_float(data.get('peso')),
              safe_float(data.get('volumen')),
              data.get('observaciones', ''),
              data.get('transporte'),
              safe_float(data.get('costo_unitario')),
              safe_float(data.get('precio_unitario')),
              safe_int(data.get('stock')),
              safe_int(data.get('stock_minimo')),
              data.get('estado', 'activo'),
              data.get('presentacion_proveedor', ''),
              data.get('presentacion_venta', ''),
              safe_int(data.get('venta_minima'), 1),
              data.get('codigo_barras', ''),
              data.get('origen', ''),
              data.get('tiempo_entrega', ''),
              data.get('abastecimiento', ''),
              proveedor_id,
              tipo_operacion,
              producto_id
            ))

            registrar_en_maestro(cur, 'marcas', data.get('marca'))
            registrar_en_maestro(cur, 'categorias', data.get('familia') or data.get('categoria'))

            # Agregar stock inicial al editar: solo si escribió una cantidad mayor a 0
            mensaje_stock = ''
            if safe_float(data.get('stock_inicial_cantidad')) > 0:
                from routes.inventario import registrar_stock_inicial, ErrorInventario
                empresa_id, almacen_id = data.get('stock_inicial_empresa'), data.get('stock_inicial_almacen')
                if empresa_id and almacen_id:
                    # Evita duplicar: si ya hay stock (o un stock inicial esperando aprobación) en esa empresa y sede,
                    # cualquier corrección se hace en Inventario, con su motivo.
                    try:
                        cur.execute("""
                            SELECT
                              (SELECT cantidad FROM inv_stock WHERE producto_id = %s
                                 AND empresa_id::text = %s AND almacen_id::text = %s AND cantidad > 0) AS cantidad,
                              EXISTS (SELECT 1 FROM inv_movimientos WHERE producto_id = %s AND motivo = 'STOCK_INICIAL'
                                 AND estado = 'Pendiente' AND empresa_id::text = %s AND almacen_id::text = %s) AS pendiente
                        """, (producto_id, str(empresa_id), str(almacen_id), producto_id, str(empresa_id), str(almacen_id)))
                        ya = cur.fetchone()
                    except Exception:
                        raise ValueError('Stock inicial: revisa la empresa y la sede elegidas.')
                    if ya and ya['cantidad']:
                        raise ValueError(f"Este producto ya tiene {float(ya['cantidad']):g} unidades en esa empresa y sede. "
                                         "Para cambiar ese stock usa Inventario (ingreso o ajuste).")
                    if ya and ya['pendiente']:
                        raise ValueError('Ya hay un stock inicial de este producto en esa empresa y sede esperando '
                                         'aprobación. Pide a un supervisor que lo revise en Inventario.')
                try:
                    mov, pendiente = registrar_stock_inicial(
                        cur, producto_id=producto_id, empresa_id=empresa_id, almacen_id=almacen_id,
                        cantidad=data.get('stock_inicial_cantidad'), costo_unitario=safe_float(data.get('costo_unitario')),
                        observaciones='Stock inicial agregado al editar el producto')
                except ErrorInventario as e:
                    raise ValueError(f'Stock inicial: {e}')
                mensaje_stock = (f" Stock inicial {mov['numero']}: queda pendiente hasta que un supervisor lo apruebe."
                                 if pendiente else f" Stock inicial registrado ({mov['numero']}).")

        return jsonify({
            'success': True,
            'message': 'Producto actualizado exitosamente.' + mensaje_stock,
            'data': {'codigo': codigo_existente}
        })

    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        print(f"❌ Error en update_producto: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@productos_bp.route('/api/productos/<int:producto_id>', methods=['DELETE'])
@login_required
def delete_producto(producto_id):
    """Eliminar producto (borrado lógico)"""
    try:
        existente = db_query("SELECT id FROM productos WHERE id = %s AND activo = TRUE", (producto_id,))
        if not existente:
            return jsonify({'success': False, 'error': 'Producto no encontrado'}), 404

        db_execute("""
            UPDATE productos SET activo = FALSE, updated_at = NOW()
            WHERE id = %s
        """, (producto_id,))

        return jsonify({
            'success': True,
            'message': 'Producto desactivado exitosamente'
        })

    except Exception as e:
        print(f"❌ Error en delete_producto: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@productos_bp.route('/api/productos/buscar', methods=['GET'])
@login_required
def buscar_productos():
    """Buscar productos por código o descripción"""
    try:
        q = request.args.get('q', '').strip()
        if not q or len(q) < 2:
            return jsonify({'success': True, 'data': []})

        from routes.inventario import asegurar_tablas_inventario
        asegurar_tablas_inventario()
        ef = empresa_filtro()
        productos = _limpiar_stock(db_query("""
            SELECT p.id, p.codigo, p.descripcion, p.modelo, p.marca, p.precio_unitario,
                """ + SQL_STOCK_PRODUCTO + """
                p.unidad
            FROM productos p
            WHERE p.activo = TRUE
            AND (p.codigo ILIKE %s OR p.descripcion ILIKE %s OR p.modelo ILIKE %s OR p.marca ILIKE %s)
            ORDER BY p.codigo
            LIMIT 20
        """, (ef, ef, f'%{q}%', f'%{q}%', f'%{q}%', f'%{q}%')))

        return jsonify({
            'success': True,
            'data': productos
        })

    except Exception as e:
        print(f"❌ Error en buscar_productos: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@productos_bp.route('/api/productos/filtros', methods=['GET'])
@login_required
def get_filtros_productos():
    """Obtener opciones de filtros para productos"""
    try:
        categorias = db_query("""
            SELECT DISTINCT familia as categoria
            FROM productos WHERE activo = TRUE AND familia IS NOT NULL AND familia != ''
            ORDER BY familia
        """)

        marcas = db_query("""
            SELECT DISTINCT marca
            FROM productos WHERE activo = TRUE AND marca IS NOT NULL AND marca != ''
            ORDER BY marca
        """)

        modelos = db_query("""
            SELECT DISTINCT modelo
            FROM productos WHERE activo = TRUE AND modelo IS NOT NULL AND modelo != ''
            ORDER BY modelo
        """)

        return jsonify({
            'success': True,
            'data': {
                'categorias': [c['categoria'] for c in categorias] if categorias else [],
                'marcas': [m['marca'] for m in marcas] if marcas else [],
                'modelos': [m['modelo'] for m in modelos] if modelos else []
            }
        })

    except Exception as e:
        print(f"❌ Error en get_filtros_productos: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@productos_bp.route('/api/productos/ultimo-codigo', methods=['GET'])
@login_required
def get_ultimo_codigo():
    """Obtener el último código de producto generado"""
    try:
        codigo = obtener_ultimo_codigo_producto()
        print(f"📝 Código generado por backend: {codigo}")
        return jsonify({
            'success': True,
            'data': {'codigo': codigo}
        })
    except Exception as e:
        print(f"❌ Error en get_ultimo_codigo: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ENDPOINTS PARA COMPARATIVO DE COSTOS
# ============================================================

@productos_bp.route('/api/comparativo-costos', methods=['GET'])
@login_required
def get_comparativo_costos():
    """API: Obtener datos del comparativo de costos"""
    try:
        categoria = request.args.get('categoria', '').strip()
        marca = request.args.get('marca', '').strip()
        min_margen = request.args.get('min_margen', '').strip()
        max_margen = request.args.get('max_margen', '').strip()
        busqueda = request.args.get('q', '').strip()
        producto_id = request.args.get('producto_id', '').strip()

        query = """
            SELECT 
                producto_id, codigo, nombre_producto, modelo, marca,
                categoria, subcategoria, costo_actual, precio_actual,
                stock, stock_minimo, estado, activo, precio_venta,
                precio_lista, margen_preferido, total_registros_costos,
                costo_promedio_historico, costo_minimo_historico,
                costo_maximo_historico, costo_compra_promedio,
                costo_transporte_promedio, costo_almacenaje_promedio,
                costo_manufactura_promedio, ultimo_costo_registrado,
                fecha_ultimo_costo, margen_actual_porcentaje,
                margen_historico_porcentaje, diferencia_margen_preferido
            FROM vista_comparativo_costos
            WHERE 1=1
        """
        params = []

        if producto_id:
            query += " AND producto_id = %s"
            params.append(int(producto_id))

        if categoria:
            query += " AND categoria ILIKE %s"
            params.append(f'%{categoria}%')

        if marca:
            query += " AND marca ILIKE %s"
            params.append(f'%{marca}%')

        if busqueda:
            query += """ AND (
                codigo ILIKE %s OR 
                nombre_producto ILIKE %s OR 
                modelo ILIKE %s OR 
                marca ILIKE %s
            )"""
            params.extend([f'%{busqueda}%'] * 4)

        if min_margen:
            query += " AND margen_actual_porcentaje >= %s"
            params.append(float(min_margen))

        if max_margen:
            query += " AND margen_actual_porcentaje <= %s"
            params.append(float(max_margen))

        query += " ORDER BY nombre_producto"

        resultados = db_query(query, params)

        return jsonify({
            'success': True,
            'data': resultados,
            'total': len(resultados),
            'filtros_aplicados': {
                'categoria': categoria if categoria else None,
                'marca': marca if marca else None,
                'min_margen': float(min_margen) if min_margen else None,
                'max_margen': float(max_margen) if max_margen else None,
                'busqueda': busqueda if busqueda else None
            }
        })

    except Exception as e:
        print(f"❌ Error en get_comparativo_costos: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@productos_bp.route('/api/comparativo-costos/resumen', methods=['GET'])
@login_required
def get_resumen_costos():
    """API: Obtener resumen del dashboard de costos"""
    try:
        resultado = db_query("SELECT * FROM vista_resumen_costos")

        if not resultado:
            return jsonify({
                'success': True,
                'data': {
                    'total_productos_con_costos': 0,
                    'total_registros_costos': 0,
                    'tipos_costo_utilizados': 0,
                    'promedio_general_costos': 0,
                    'costo_minimo_registrado': 0,
                    'costo_maximo_registrado': 0,
                    'promedio_costo_compra': 0,
                    'promedio_costo_transporte': 0,
                    'promedio_costo_almacenaje': 0,
                    'promedio_costo_manufactura': 0,
                    'registros_ultimos_30_dias': 0,
                    'promedio_ultimos_30_dias': 0
                }
            })

        return jsonify({
            'success': True,
            'data': resultado[0]
        })

    except Exception as e:
        print(f"❌ Error en get_resumen_costos: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@productos_bp.route('/api/productos/<int:producto_id>/costos-historicos', methods=['GET'])
@login_required
def get_costos_historicos(producto_id):
    """API: Obtener el historial de costos de un producto específico"""
    try:
        producto = db_query("""
            SELECT id, codigo, descripcion 
            FROM productos 
            WHERE id = %s AND activo = TRUE
        """, (producto_id,))

        if not producto:
            return jsonify({
                'success': False,
                'error': 'Producto no encontrado'
            }), 404

        historial = db_query("""
            SELECT id, fecha_registro, tipo_costo, monto, observaciones
            FROM costos_productos
            WHERE producto_id = %s
            ORDER BY fecha_registro DESC
        """, (producto_id,))

        return jsonify({
            'success': True,
            'data': {
                'producto': producto[0],
                'historial': historial,
                'total_registros': len(historial)
            }
        })

    except Exception as e:
        print(f"❌ Error en get_costos_historicos: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@productos_bp.route('/api/comparativo-costos/filtros', methods=['GET'])
@login_required
def get_filtros_comparativo():
    """API: Obtener opciones de filtros para el comparativo"""
    try:
        categorias = db_query("""
            SELECT DISTINCT categoria 
            FROM vista_comparativo_costos 
            WHERE categoria IS NOT NULL AND categoria != ''
            ORDER BY categoria
        """)

        marcas = db_query("""
            SELECT DISTINCT marca 
            FROM vista_comparativo_costos 
            WHERE marca IS NOT NULL AND marca != ''
            ORDER BY marca
        """)

        productos = db_query("""
            SELECT DISTINCT producto_id, codigo, nombre_producto
            FROM vista_comparativo_costos
            ORDER BY nombre_producto
            LIMIT 100
        """)

        return jsonify({
            'success': True,
            'data': {
                'categorias': [c['categoria'] for c in categorias] if categorias else [],
                'marcas': [m['marca'] for m in marcas] if marcas else [],
                'productos': productos if productos else []
            }
        })

    except Exception as e:
        print(f"❌ Error en get_filtros_comparativo: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@productos_bp.route('/api/comparativo-costos/exportar', methods=['GET'])
@login_required
def exportar_comparativo_csv():
    """API: Exportar datos del comparativo a CSV"""
    try:
        resultados = db_query("""
            SELECT 
                codigo, nombre_producto, modelo, marca, categoria,
                costo_actual, precio_actual, costo_promedio_historico,
                margen_actual_porcentaje, margen_historico_porcentaje,
                total_registros_costos, fecha_ultimo_costo
            FROM vista_comparativo_costos
            ORDER BY nombre_producto
        """)

        import csv
        from io import StringIO

        output = StringIO()
        writer = csv.writer(output)

        writer.writerow([
            'Código', 'Producto', 'Modelo', 'Marca', 'Categoría',
            'Costo Actual (S/)', 'Precio Venta (S/)',
            'Costo Promedio Histórico (S/)', 'Margen Actual (%)',
            'Margen Histórico (%)', 'N° Registros Costos', 'Fecha Último Costo'
        ])

        for row in resultados:
            writer.writerow([
                row.get('codigo', ''),
                row.get('nombre_producto', ''),
                row.get('modelo', ''),
                row.get('marca', ''),
                row.get('categoria', ''),
                f"{float(row.get('costo_actual', 0)):.2f}",
                f"{float(row.get('precio_actual', 0)):.2f}",
                f"{float(row.get('costo_promedio_historico', 0)):.2f}",
                f"{float(row.get('margen_actual_porcentaje', 0)):.2f}",
                f"{float(row.get('margen_historico_porcentaje', 0)):.2f}",
                row.get('total_registros_costos', 0),
                row.get('fecha_ultimo_costo', '')
            ])

        csv_content = output.getvalue()
        output.close()

        return Response(
            csv_content,
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename=comparativo_costos_{datetime.now().strftime("%Y%m%d")}.csv'
            }
        )

    except Exception as e:
        print(f"❌ Error en exportar_comparativo_csv: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@productos_bp.route('/api/comparativo-costos/mejor-producto', methods=['GET'])
@login_required
def get_mejor_producto():
    """API: Obtener el producto con mejor margen"""
    try:
        resultado = db_query("""
            SELECT 
                producto_id, codigo, nombre_producto, marca, modelo,
                categoria, precio_actual, costo_actual,
                margen_actual_porcentaje, costo_promedio_historico,
                total_registros_costos
            FROM vista_comparativo_costos
            WHERE margen_actual_porcentaje = (
                SELECT MAX(margen_actual_porcentaje) 
                FROM vista_comparativo_costos
            )
            LIMIT 1
        """)

        if not resultado:
            return jsonify({
                'success': True,
                'data': None,
                'message': 'No hay productos con datos de costos'
            })

        return jsonify({
            'success': True,
            'data': resultado[0]
        })

    except Exception as e:
        print(f"❌ Error en get_mejor_producto: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500