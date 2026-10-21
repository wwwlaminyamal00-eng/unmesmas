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
    'reportes': ['REPORTE_VENTAS', 'REPORTE_COMPRAS', 'REPORTE_INVENTARIO', 'REPORTE_FINANZAS', 'SUNAT'],
}

# Rutas de cada módulo. todo=True bloquea también sus APIs; todo=False solo la pantalla
# (sus APIs de consulta las usan otros módulos: buscar clientes, productos, stock...).
RUTAS_MODULO = (
    ('/finanzas', 'finanzas', True),
    ('/reportes', 'reportes', True),
    ('/ventas', 'ventas', True),
    ('/api/cotizaciones', 'ventas', True),
    ('/comprobantes', 'ventas', True),
    ('/compras', 'compras', True),
    ('/api/abastecimiento', 'compras', False),
    ('/inventario', 'inventario', False),
    ('/maestros', 'maestros', False),
    ('/productos', 'productos', False),
)

NOMBRE_MODULO = {'finanzas': 'Finanzas', 'reportes': 'Reportes', 'ventas': 'Ventas', 'compras': 'Compras',
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
        if not admin:
            modulos.discard('configuracion')   # empresas, usuarios, correlativos...: solo administrador
        info = {'configurado': True, 'admin': admin, 'modulos': modulos}
    _cache[llave] = (time.time(), info)
    return info


def modulo_de_ruta(ruta, metodo):
    """Módulo que protege esta ruta, o None si la ruta es libre para cualquier usuario con sesión."""
    for prefijo, modulo, todo in RUTAS_MODULO:
        if ruta == prefijo or ruta.startswith(prefijo + '/') or ruta.startswith(prefijo + '?'):
            if todo or '/api/' not in ruta:
                return modulo
            return None
    return None
