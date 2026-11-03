"""Guía de remisión obligatoria para todo traslado entre sedes (Erika, 03/11/2026).

"No debería permitir el traslado sin guía, prohibido. Debe haber un sustento."

- Al crear un traslado se usa una guía ya hecha (de la misma empresa, motivo "Traslado entre establecimientos de la
  misma empresa", no anulada y sin otro traslado) o, si se deja vacío, el ERP la genera sola en Ventas ▸ Guías con
  los datos del traslado (remitente y destinatario = la misma empresa, partida = sede origen, llegada = sede destino).
- Un traslado antiguo sin guía no se puede recibir hasta que se le genere (botón "Generar guía").
"""
import json

from utils import MOTIVO_TRASLADO_ESTABLECIMIENTOS, normalizar_motivo_traslado

SERIE_TRASLADO = 'T001'


class ErrorGuiaTraslado(Exception):
    pass


def _texto(serie, numero):
    return f"{serie}-{numero}"


def validar_guia_existente(cur, empresa_id, texto, traslado_id=None):
    """Comprueba que la guía escrita sirve como sustento del traslado. Devuelve 'SERIE-NUMERO'."""
    t = ' '.join(str(texto or '').split()).upper()
    if '-' not in t:
        raise ErrorGuiaTraslado('Escribe la guía como SERIE-NÚMERO (ej. T001-00000123) o déjala vacía para que el ERP la genere.')
    serie, numero = t.split('-', 1)
    cur.execute("""SELECT id, serie, numero, motivo_traslado, estado_sunat FROM guias_remision
                   WHERE UPPER(serie) = %s AND LTRIM(numero::text, '0') = LTRIM(%s, '0')
                     AND empresa_id IS NOT DISTINCT FROM %s
                   ORDER BY id DESC LIMIT 1""", (serie.strip(), numero.strip(), empresa_id))
    g = cur.fetchone()
    if not g:
        raise ErrorGuiaTraslado(f'La guía {t} no existe en Ventas ▸ Guías de esta empresa. '
                                'Déjala vacía y el ERP la genera con los datos del traslado.')
    if str(g.get('estado_sunat') or '').upper().startswith('ANULAD'):
        raise ErrorGuiaTraslado(f'La guía {t} está anulada: no sirve de sustento.')
    if normalizar_motivo_traslado(g.get('motivo_traslado')) != MOTIVO_TRASLADO_ESTABLECIMIENTOS:
        raise ErrorGuiaTraslado(f'La guía {t} tiene motivo "{normalizar_motivo_traslado(g.get("motivo_traslado"))}". '
                                f'Para un traslado el motivo debe ser "{MOTIVO_TRASLADO_ESTABLECIMIENTOS}".')
    texto_guia = _texto(g['serie'], g['numero'])
    cur.execute("""SELECT numero FROM inv_traslados WHERE UPPER(guia_remision) = UPPER(%s) AND estado <> 'Anulado'
                   AND id IS DISTINCT FROM %s LIMIT 1""", (texto_guia, traslado_id))
    otro = cur.fetchone()
    if otro:
        raise ErrorGuiaTraslado(f'La guía {texto_guia} ya es el sustento del traslado {otro["numero"]}.')
    return texto_guia


def generar_guia(cur, traslado, items, usuario_id=None):
    """Crea la guía de remisión del traslado en Ventas ▸ Guías y devuelve 'SERIE-NUMERO'.
    traslado: dict con id, numero, empresa_id, origen_id, destino_id, encargado.
    items: lista de {producto_id, cantidad}."""
    from routes.multiempresa import empresa_por_id, marcar_empresa
    from routes.numeracion import con_piso, clave_guia
    from routes.ventas import _siguiente_numero
    empresa_id = traslado['empresa_id']
    emp = empresa_por_id(empresa_id) or {}
    cur.execute("SELECT id, nombre, direccion FROM almacenes WHERE id IN (%s, %s)",
                (traslado['origen_id'], traslado['destino_id']))
    sedes = {f['id']: f for f in cur.fetchall()}
    origen, destino = sedes.get(traslado['origen_id']) or {}, sedes.get(traslado['destino_id']) or {}
    ids = [int(i['producto_id']) for i in items]
    cur.execute("SELECT id, codigo, descripcion, unidad FROM productos WHERE id = ANY(%s)", (ids,))
    prods = {f['id']: f for f in cur.fetchall()}
    lineas = []
    for n, it in enumerate(items, 1):
        p = prods.get(int(it['producto_id'])) or {}
        lineas.append({'item': n, 'codigo': p.get('codigo') or '', 'producto': p.get('descripcion') or '',
                       'descripcion': p.get('descripcion') or '', 'um': p.get('unidad') or 'NIU',
                       'cantidad': float(it['cantidad'])})
    numero = _siguiente_numero(cur, 'guias_remision', SERIE_TRASLADO,
                               extra_where='AND empresa_id IS NOT DISTINCT FROM %s', extra_params=(empresa_id,))
    numero = str(con_piso(cur, 'GUIA', clave_guia(empresa_id, SERIE_TRASLADO), numero)).zfill(8)
    partida = ' - '.join(x for x in (origen.get('nombre'), origen.get('direccion')) if x)
    llegada = ' - '.join(x for x in (destino.get('nombre'), destino.get('direccion')) if x)
    cur.execute("""
        INSERT INTO guias_remision (serie, numero, fecha_emision, fecha_traslado, ruc_remitente, remitente_nombre,
            remitente_direccion, remitente_ubigeo, ruc_destinatario, destinatario_nombre, destinatario_direccion,
            destinatario_ubigeo, modalidad_transporte, conductor_nombre, motivo_traslado, documento_asociado,
            items_json, observaciones, estado_sunat, creado_por, created_at)
        VALUES (%s, %s, (NOW() AT TIME ZONE 'America/Lima'), (NOW() AT TIME ZONE 'America/Lima')::date, %s, %s,
                %s, %s, %s, %s, %s, %s, 'PRIVADO', %s, %s, %s, %s, %s, 'BORRADOR', %s, NOW())
        RETURNING id
    """, (SERIE_TRASLADO, numero, emp.get('ruc') or '', emp.get('razon_social') or emp.get('codigo') or '',
          partida, emp.get('ubigeo') or '', emp.get('ruc') or '', emp.get('razon_social') or emp.get('codigo') or '',
          llegada, '', traslado.get('encargado') or '', MOTIVO_TRASLADO_ESTABLECIMIENTOS, traslado['numero'],
          json.dumps(lineas), f"Traslado {traslado['numero']}: de {origen.get('nombre') or 'origen'} a "
                              f"{destino.get('nombre') or 'destino'}. Lleva: {traslado.get('encargado') or '—'}.",
          usuario_id))
    gid = cur.fetchone()['id']
    marcar_empresa(cur, 'guias_remision', gid, empresa_id)
    return _texto(SERIE_TRASLADO, numero)
