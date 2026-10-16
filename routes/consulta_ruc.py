# ============================================================
# CONSULTA DE RUC (16/10/2026)
# Antes se llamaba a https://api.apis.net.pe/v1/ruc sin clave. Ese servicio ahora cobra y responde
# "402 Payment Required", y el ERP mostraba "Error en la consulta: Código 402".
# Ahora:
#   1. Primero busca el RUC en los clientes y proveedores que ya están en el ERP (no gasta consultas).
#   2. Si hay una clave configurada en Render (variable DECOLECTA_TOKEN, APIS_NET_PE_TOKEN o
#      SUNAT_API_TOKEN), consulta el servicio nuevo con esa clave.
#   3. Si no se puede consultar, devuelve un mensaje claro y la pantalla deja escribir los datos a mano.
# ============================================================
import os
import logging

import requests

from database import db_query

log = logging.getLogger(__name__)


class ErrorConsultaRuc(Exception):
    pass


def _token():
    for nombre in ('DECOLECTA_TOKEN', 'APIS_NET_PE_TOKEN', 'SUNAT_API_TOKEN'):
        valor = (os.environ.get(nombre) or '').strip()
        if valor:
            return valor
    return ''


def buscar_ruc_local(ruc):
    """Datos del RUC si ya es cliente o proveedor del ERP (de cualquier empresa)."""
    try:
        filas = db_query("""
            SELECT razon_social, COALESCE(nombre_comercial, '') AS nombre_comercial,
                   COALESCE(direccion_fiscal, '') AS direccion, 'cliente' AS origen
            FROM clientes WHERE numero_documento = %s AND COALESCE(razon_social, '') <> ''
            ORDER BY id DESC LIMIT 1
        """, (ruc,))
        if not filas:
            filas = db_query("""
                SELECT razon_social, COALESCE(razon_comercial, '') AS nombre_comercial,
                       COALESCE(direccion, '') AS direccion, 'proveedor' AS origen
                FROM proveedores WHERE ruc = %s AND COALESCE(razon_social, '') <> ''
                ORDER BY id DESC LIMIT 1
            """, (ruc,))
        if filas:
            f = filas[0]
            return {'razon_social': f['razon_social'], 'nombre_comercial': f['nombre_comercial'] or f['razon_social'],
                    'direccion': f['direccion'], 'estado': '', 'condicion': '', 'fuente': 'erp_' + f['origen']}
    except Exception as e:
        log.warning("No se pudo buscar el RUC en el ERP: %s", e)
    return None


def _normalizar(data):
    razon = data.get('razon_social') or data.get('razonSocial') or data.get('nombre') or ''
    return {
        'razon_social': razon,
        'nombre_comercial': data.get('nombre_comercial') or data.get('nombreComercial') or razon,
        'direccion': data.get('direccion') or '',
        'estado': data.get('estado') or '',
        'condicion': data.get('condicion') or '',
    }


def consultar_ruc_externo(ruc):
    token = _token()
    intentos = []
    if token:
        intentos = [
            ('https://api.decolecta.com/v1/sunat/ruc', {'Authorization': f'Bearer {token}'}),
            ('https://api.apis.net.pe/v2/sunat/ruc', {'Authorization': f'Bearer {token}'}),
        ]
    intentos.append(('https://api.apis.net.pe/v1/ruc', {}))
    ultimo = None
    for url, extra in intentos:
        try:
            r = requests.get(url, params={'numero': ruc}, timeout=10,
                             headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json', **extra})
        except requests.Timeout:
            ultimo = 'La consulta a SUNAT tardó demasiado.'
            continue
        except Exception as e:
            log.warning("Consulta RUC %s falló: %s", url, e)
            ultimo = 'No se pudo conectar con el servicio de consulta de RUC.'
            continue
        if r.status_code == 200:
            try:
                datos = _normalizar(r.json() or {})
            except ValueError:
                datos = {}
            if datos.get('razon_social'):
                datos['fuente'] = 'sunat'
                return datos
            ultimo = 'SUNAT no tiene datos para este RUC. Revisa el número.'
        elif r.status_code in (401, 402, 403, 429):
            ultimo = ('La consulta automática a SUNAT necesita una clave de pago (token) que no está configurada '
                      'o se terminó. Escribe la razón social y la dirección a mano.')
        elif r.status_code in (404, 422):
            ultimo = 'SUNAT no tiene datos para este RUC. Revisa el número.'
        else:
            ultimo = f'El servicio de consulta de RUC no respondió bien (código {r.status_code}).'
    raise ErrorConsultaRuc(ultimo or 'No se pudo consultar el RUC.')


def consultar_ruc(ruc):
    """Devuelve dict con razon_social, nombre_comercial, direccion, estado, condicion y fuente."""
    ruc = (ruc or '').strip()
    if len(ruc) != 11 or not ruc.isdigit():
        raise ErrorConsultaRuc('RUC inválido, debe tener 11 dígitos')
    return buscar_ruc_local(ruc) or consultar_ruc_externo(ruc)
