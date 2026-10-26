# routes/acceso.py
# ============================================================
# PERMISOS QUE DE VERDAD LIMITAN (pedido de Erika 21/10/2026 16:35)
# Antes el menú solo se escondía en el navegador y el "administrador" salía de usuarios.rol:
# Hellen tiene rol de sistema "administrador" (para validar cotizaciones) y por eso veía todo,
# aunque en "Usuarios y permisos" solo tiene 2-3 permisos.
# Ahora, si el usuario está configurado en el ERP (erp_usuario_empresas):
#   - es administrador solo si su rol ERP es GERENCIA_TOTAL (o un rol marcado es_admin);
#   - ve solo los módulos donde tiene "Ver" en la empresa activa (o en alguna, con TODAS);
#   - si escribe la URL de otro módulo, el servidor lo bloquea.
# Los usuarios sin configuración ERP siguen como antes (según usuarios.rol).
# ============================================================
import time

from flask import session

# Submódulos de cada grupo del menú (los mismos que usa base.html)
MENU_CODIGOS = {
    'configuracion': ['EMPRESAS', 'USUARIOS_PERMISOS', 'CORRELATIVOS', 'PARAMETROS', 'INTEGRACION'],
    'maestros': ['CLIENTES', 'PROVEEDORES', 'ALMACENES', 'CATEGORIAS', 'MARCAS', 'UNIDADES_MEDIDA'],
    'productos': ['PRODUCTOS_LISTADO', 'PRODUCTOS_FICHA'],
    'ventas': ['COTIZACIONES', 'COMPROBANTES_CLIENTE', 'GUIAS_CLIENTE', 'NOTAS_CREDITO'],
    'compras': ['SOLICITUD_COMPRA', 'COMPARATIVO_PROVEEDORES', 'ORDEN_COMPRA', 'COMPROBANTES_PROVEEDOR',
                'RECEPCION_MERCADERIA'],
    'inventario': ['ESTADO_STOCK', 'KARDEX', 'ENTRADAS_SALIDAS', 'TRANSFERENCIAS'],
    'finanzas': ['CUENTAS_COBRAR', 'CUENTAS_PAGAR', 'CAJA_BANCOS', 'FLUJO_CAJA'],
    'reportes': ['REPORTE_VENTAS', 'REPORTE_COMPRAS', 'REPORTE_INVENTARIO', 'REPORTE_FINANZAS'],
    # Módulo propio (pedido de Erika 21/10/2026): ver Reportes no da acceso a los impuestos
    'sunat': ['SUNAT'],
    'bancos': ['CONCILIACION_BANCARIA'],   # Conciliación bancaria (21/10/2026 23:30)
    'intercompany': ['INTERCOMPANY'],       # Intercompany KCF ↔ AGD: solo gerencia y quien Erika marque
    'planilla': ['PLANILLA'],               # Planilla y RRHH: sueldos (datos sensibles), solo quien Erika marque
    'caja_chica': ['CAJA_CHICA'],           # Caja chica (22/10/2026): Hellen registra y rinde; aprueba la gerencia
    'seguimiento': ['SEGUIMIENTO_COMERCIAL'],  # Seguimiento comercial: cotizaciones sin cerrar y tasa de cierre
}

# Rutas de cada módulo. todo=True bloquea también sus APIs; todo=False solo la pantalla
# (sus APIs de consulta las usan otros módulos: buscar clientes, productos, stock...).
RUTAS_MODULO = (
    ('/finanzas', 'finanzas', True),
    ('/reportes', 'reportes', True),
    ('/sunat', 'sunat', True),
    ('/bancos', 'bancos', True),
    ('/intercompany', 'intercompany', True),
    ('/planilla', 'planilla', True),
    ('/caja-chica', 'caja_chica', True),
    ('/seguimiento', 'seguimiento', True),
    ('/ventas', 'ventas', True),
    ('/api/cotizaciones', 'ventas', True),
    ('/comprobantes', 'ventas', True),
    ('/compras', 'compras', True),
    ('/api/abastecimiento', 'compras', False),
    ('/inventario', 'inventario', False),
    ('/maestros', 'maestros', False),
    ('/productos', 'productos', False),
)

NOMBRE_MODULO = {'finanzas': 'Finanzas', 'reportes': 'Reportes', 'sunat': 'SUNAT e impuestos', 'bancos': 'Conciliación bancaria', 'intercompany': 'Intercompany', 'planilla': 'Planilla', 'caja_chica': 'Caja chica', 'seguimiento': 'Seguimiento comercial', 'ventas': 'Ventas', 'compras': 'Compras',
                 'inventario': 'Inventario', 'maestros': 'Maestros', 'productos': 'Productos'}

_cache = {}
_TTL = 30


def limpiar_cache():
    _cache.clear()


def acceso_usuario():
    """{'configurado', 'admin', 'modulos'} del usuario de la sesión (con caché corta)."""
    auth = session.get('auth_user_id')
    empresa = (session.get('empresa') or 'KCF').upper()
    if not auth:
        return {'configurado': False, 'admin': False, 'modulos': set()}
    llave = (str(auth), empresa)
    guardado = _cache.get(llave)
    if guardado and time.time() - guardado[0] < _TTL:
        return guardado[1]
    from routes.configuracion_seguridad import _empresas_del_usuario, _permisos_efectivos
    try:
        accesos = _empresas_del_usuario(auth)
    except Exception:
        accesos = []
    if not accesos:
        info = {'configurado': False, 'admin': False, 'modulos': set()}
    else:
        admin = any(a['rol_codigo'] == 'GERENCIA_TOTAL' or a['rol_es_admin'] for a in accesos)
        if empresa == 'TODAS':
            ids = [a['empresa_id'] for a in accesos if a['empresa_id']]
        else:
            ids = [a['empresa_id'] for a in accesos if (a['empresa_codigo'] or '').upper() == empresa]
        efectivos = _permisos_efectivos(auth, ids)[0] if ids else {}
        modulos = {m for m, codigos in MENU_CODIGOS.items()
                   if any((efectivos.get(c) or {}).get('puede_ver') for c in codigos)}
        # "Acceso total" = Ver + Crear/Editar. Con "Solo lectura" (solo Ver) el servidor no deja grabar (22/10/2026)
        escritura = {m for m, codigos in MENU_CODIGOS.items()
                     if any(nivel_permiso(efectivos.get(c)) == 'total' for c in codigos)}
        if not admin:
            modulos.discard('configuracion')   # empresas, usuarios, correlativos...: solo administrador
        info = {'configurado': True, 'admin': admin, 'modulos': modulos, 'escritura': escritura & modulos}
    _cache[llave] = (time.time(), info)
    return info


def nivel_permiso(p):
    """'sin' | 'lectura' | 'total' de un permiso de submódulo (pantalla de matriz, 22/10/2026)."""
    p = p or {}
    if not p.get('puede_ver'):
        return 'sin'
    return 'total' if (p.get('puede_crear') or p.get('puede_editar')) else 'lectura'


# Grabar en Maestros y Productos también lo hacen Ventas y Compras (crear el cliente desde la cotización,
# el proveedor desde la OC...): basta con Acceso total en cualquiera de ellos.
ESCRITURA_TAMBIEN_DESDE = {'maestros': ('ventas', 'compras'), 'productos': ('ventas', 'compras')}
# POST que solo consultan (no graban nada)
POST_DE_CONSULTA = ('/sunat/api/importar/vista',)
METODOS_DE_LECTURA = ('GET', 'HEAD', 'OPTIONS')


def bloqueo_solo_lectura(ruta, metodo, acceso):
    """Nombre del módulo si el usuario lo tiene en "Solo lectura" y esta petición quiere grabar; si no, None."""
    if metodo in METODOS_DE_LECTURA or acceso.get('admin') or not acceso.get('configurado') or ruta in POST_DE_CONSULTA:
        return None
    for prefijo, modulo, _todo in RUTAS_MODULO:
        if ruta == prefijo or ruta.startswith(prefijo + '/'):
            if modulo not in acceso['modulos']:
                return None          # sin acceso al módulo: lo resuelve el control de "Ver"
            escritura = acceso.get('escritura', set())
            if modulo in escritura or any(m in escritura for m in ESCRITURA_TAMBIEN_DESDE.get(modulo, ())):
                return None
            return modulo
    return None


def modulo_de_ruta(ruta, metodo):
    """Módulo que protege esta ruta, o None si la ruta es libre para cualquier usuario con sesión."""
    for prefijo, modulo, todo in RUTAS_MODULO:
        if ruta == prefijo or ruta.startswith(prefijo + '/') or ruta.startswith(prefijo + '?'):
            if todo or '/api/' not in ruta:
                return modulo
            return None
    return None


_cache_flags = {}


def tiene_permiso(codigo, flag='puede_aprobar'):
    """24/10/2026: un permiso puntual de la matriz (ej. ORDEN_COMPRA + puede_aprobar para que Hellen apruebe OC)."""
    auth = session.get('auth_user_id')
    if not auth:
        return False
    empresa = (session.get('empresa') or 'KCF').upper()
    llave = (str(auth), empresa)
    guardado = _cache_flags.get(llave)
    if not guardado or time.time() - guardado[0] >= _TTL:
        from routes.configuracion_seguridad import _empresas_del_usuario, _permisos_efectivos
        try:
            accesos = _empresas_del_usuario(auth)
            ids = [a['empresa_id'] for a in accesos if a['empresa_id']
                   and (empresa == 'TODAS' or (a['empresa_codigo'] or '').upper() == empresa)]
            efectivos = _permisos_efectivos(auth, ids)[0] if ids else {}
        except Exception:
            efectivos = {}
        guardado = (time.time(), efectivos)
        _cache_flags[llave] = guardado
    return bool((guardado[1].get(codigo) or {}).get(flag))
