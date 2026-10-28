"""Distrito de entrega del PV (Erika, 27/10/2026 18:48 y 18:53).

En PV ("Lugar entrega") y en Entregas ("Distrito") sale solo el distrito, en automático y sin escribirlo en la lista;
la dirección completa sale al pasar el mouse.
  - Si el cliente viene a recoger: el distrito del local de la empresa del PV (KCF: San Martín de Porres; AGD: Breña),
    leído de su dirección fiscal en Configuración ▸ Empresas.
  - Si no: el "Distrito de entrega" del formulario del PV (se llena solo con la dirección de la cotización); si no hay,
    el que se lee en la dirección de entrega; si dice "Dirección cliente" o está vacío, el de la dirección del cliente.
  - Si nada lo dice, sale en rojo "Falta distrito: corrígelo en el PV". Nadie lo escribe en Entregas.
Migración 041 (en la base de pruebas la columna se crea aquí).
"""
import re
import threading

from database import db_query, db_execute

_listo = False
_lock = threading.Lock()
_empresas = {}

# Por si la dirección fiscal de la empresa no se puede leer
DISTRITO_LOCAL = {'KCF': 'San Martín de Porres', 'AGD': 'Breña'}
_RE_RECOJO = re.compile(r'RECOJO|RECOG|EN TIENDA|EN ALMACEN|EN NUESTRO LOCAL|EN LOCAL|EN OFICINA')
_SIN_DIRECCION = ('', 'DIRECCION CLIENTE', 'DIRECCION DEL CLIENTE', 'SELECCIONE', '-')


def asegurar_columna():
    global _listo
    if _listo:
        return
    with _lock:
        if _listo:
            return
        if not db_query("""SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'pedido_compra_pc' AND column_name = 'distrito_entrega'"""):
            db_execute("ALTER TABLE pedido_compra_pc ADD COLUMN IF NOT EXISTS distrito_entrega VARCHAR(80)")
        _listo = True


def _norm(texto):
    from routes.ventas import _sin_tildes
    return re.sub(r'\s+', ' ', _sin_tildes(texto)).strip()


def es_recojo(lugar):
    return bool(_RE_RECOJO.search(_norm(lugar)))


def _codigo_empresa(empresa_id, numero):
    """KCF / AGD a partir de la empresa del PV o, si no la tiene, de su número (PV-KCF-…)."""
    if empresa_id:
        for cod, e in _datos_empresas().items():
            if str(e.get('id')) == str(empresa_id):
                return cod
    m = re.match(r'^P[VC]-([A-Z]+)-', str(numero or '').upper())
    return m.group(1) if m else ''


def _datos_empresas():
    if not _empresas:
        try:
            for e in db_query("SELECT id, codigo, direccion_fiscal FROM erp_empresas"):
                _empresas[str(e.get('codigo') or '').upper()] = e
        except Exception:
            pass
    return _empresas


def distrito_local(codigo):
    from routes.ventas import adivinar_distrito
    e = _datos_empresas().get(str(codigo or '').upper())
    return (adivinar_distrito(e.get('direccion_fiscal')) if e else '') or DISTRITO_LOCAL.get(str(codigo or '').upper(), '')


def resolver(pv, direccion_cliente=''):
    """{'distrito', 'origen'}: origen es recojo, escrito, direccion, cliente o '' (sin dato)."""
    from routes.ventas import adivinar_distrito
    lugar = pv.get('lugar_entrega') or pv.get('entrega') or ''
    if es_recojo(lugar):
        d = distrito_local(_codigo_empresa(pv.get('empresa_id'), pv.get('numero')))
        if d:
            return {'distrito': d, 'origen': 'recojo'}
    if (pv.get('distrito_entrega') or '').strip():
        return {'distrito': pv['distrito_entrega'].strip(), 'origen': 'escrito'}
    d = adivinar_distrito(lugar)
    if d:
        return {'distrito': d, 'origen': 'direccion'}
    if _norm(lugar) in _SIN_DIRECCION or _norm(lugar) == _norm(direccion_cliente):
        d = adivinar_distrito(direccion_cliente)
        if d:
            return {'distrito': d, 'origen': 'cliente'}
    return {'distrito': '', 'origen': ''}


def completar_lista(filas):
    """Agrega distrito_entrega (el del formulario), distrito_entrega_ver y distrito_origen a cada PV de la lista."""
    asegurar_columna()
    if not filas:
        return
    rucs = list({str(f.get('ruc') or '') for f in filas if f.get('ruc')})
    numeros = [f.get('numero') for f in filas if f.get('numero')]
    dir_cli, extra = {}, {}
    try:
        if rucs:
            for c in db_query("SELECT numero_documento, direccion_fiscal FROM clientes WHERE numero_documento = ANY(%s)", (rucs,)):
                dir_cli.setdefault(c['numero_documento'], c.get('direccion_fiscal') or '')
        if numeros:
            for p in db_query("""SELECT numero, distrito_entrega, to_jsonb(p)->>'empresa_id' AS empresa_id
                                 FROM pedido_compra_pc p WHERE numero = ANY(%s)""", (numeros,)):
                extra[p['numero']] = p
    except Exception as e:
        print(f"⚠️ Distrito de entrega: {e}")
    for f in filas:
        x = extra.get(f.get('numero')) or {}
        pv = {**f, 'distrito_entrega': x.get('distrito_entrega'), 'empresa_id': x.get('empresa_id')}
        r = resolver(pv, dir_cli.get(str(f.get('ruc') or ''), ''))
        f['distrito_entrega_ver'] = r['distrito']
        f['distrito_origen'] = r['origen']
        f['distrito_entrega'] = x.get('distrito_entrega') or ''


def guardar(pv_id, valor, usuario=''):
    """Guarda el "Distrito de entrega" que viene del formulario del PV (vacío lo borra). Con auditoría si cambia."""
    from routes.ventas import adivinar_distrito
    asegurar_columna()
    valor = re.sub(r'\s+', ' ', str(valor or '')).strip()
    if valor:
        valor = adivinar_distrito(valor) or valor[:80]
    filas = db_query("SELECT id, numero, distrito_entrega FROM pedido_compra_pc WHERE id = %s", (pv_id,))
    if not filas or (filas[0].get('distrito_entrega') or '') == valor:
        return valor
    db_execute("UPDATE pedido_compra_pc SET distrito_entrega = %s WHERE id = %s", (valor or None, pv_id))
    try:
        from routes.auditoria import registrar_auditoria
        registrar_auditoria('ACTUALIZAR', 'Ventas', 'pedido_compra_pc', pv_id,
                            antes={'distrito_entrega': filas[0].get('distrito_entrega')}, despues={'distrito_entrega': valor or None},
                            detalle=f"Distrito de entrega del {filas[0].get('numero') or pv_id}: {valor or '(vacío)'}")
    except Exception as e:
        print(f"⚠️ Auditoría del distrito de entrega: {e}")
    return valor
