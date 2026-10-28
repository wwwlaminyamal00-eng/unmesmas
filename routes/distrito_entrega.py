"""Distrito de entrega del PV (Erika, 27/10/2026 18:48 y 18:53; 28/10/2026 12:03 "que se autocomplete").

En PV ("Lugar entrega") y en Entregas ("Distrito") sale solo el distrito, en automático y sin escribirlo en la lista;
la dirección completa sale al pasar el mouse. Se busca en este orden:
  1. Si el cliente viene a recoger: el distrito del local de la empresa del PV (KCF: San Martín de Porres; AGD: Breña),
     leído de su dirección fiscal en Configuración ▸ Empresas.
  2. El "Distrito de entrega" guardado en el PV.
  3. El que se lee en la dirección de entrega.
  4. Si la entrega es en la dirección del cliente (o dice "Dirección cliente" o está vacía): el distrito fiscal del
     cliente guardado en el ERP (de SUNAT o elegido una vez en un PV) o el que se lee en su dirección fiscal.
  5. El que ya se eligió antes para esa misma dirección en otro PV (primero del mismo cliente; gana el más reciente).
  6. En el formulario del PV, si hay clave de SUNAT en Render: el distrito del domicilio fiscal del RUC en SUNAT
     (se guarda en el cliente para no volver a consultar).
  Si nada lo dice, sale en rojo "Falta distrito: corrígelo en el PV". Nadie lo escribe en Entregas.
  Cuando alguien elige el distrito en un PV cuya entrega es la dirección fiscal del cliente, queda guardado en el
  cliente: los siguientes PV de ese cliente se llenan solos.
Migraciones 041 (pedido_compra_pc.distrito_entrega) y 042 (clientes.distrito_fiscal); en la base de pruebas las
columnas se crean aquí.
"""
import re
import threading
import time

from database import db_query, db_execute

_listo = False
_lock = threading.Lock()
_empresas = {}
_hist = {'t': 0, 'por_dir': {}, 'por_cli': {}}
HIST_SEG = 30

# Por si la dirección fiscal de la empresa no se puede leer
DISTRITO_LOCAL = {'KCF': 'San Martín de Porres', 'AGD': 'Breña'}
_RE_RECOJO = re.compile(r'RECOJO|RECOG|EN TIENDA|EN ALMACEN|EN NUESTRO LOCAL|EN LOCAL|EN OFICINA')
_SIN_DIRECCION = ('', 'DIRECCION CLIENTE', 'DIRECCION DEL CLIENTE', 'SELECCIONE', '-')
TEXTO_ORIGEN = {
    'recojo': '🏬 El cliente recoge: distrito de nuestro local',
    'escrito': '✅ Elegido en el PV',
    'direccion': '✅ Leído de la dirección de entrega',
    'cliente': '✅ Leído de la dirección fiscal del cliente',
    'cliente_guardado': '✅ Distrito fiscal del cliente guardado en el ERP',
    'sunat': '✅ Distrito del domicilio fiscal en SUNAT',
    'historial': '✅ Ya se eligió para esta misma dirección',
}


def asegurar_columna():
    global _listo
    if _listo:
        return
    with _lock:
        if _listo:
            return
        hay = {r['column_name'] for r in db_query("""
            SELECT column_name FROM information_schema.columns
            WHERE (table_name = 'pedido_compra_pc' AND column_name = 'distrito_entrega')
               OR (table_name = 'clientes' AND column_name IN ('distrito_fiscal', 'distrito_fiscal_fuente',
                                                               'distrito_fiscal_revisado_en'))""")}
        if 'distrito_entrega' not in hay:
            db_execute("ALTER TABLE pedido_compra_pc ADD COLUMN IF NOT EXISTS distrito_entrega VARCHAR(80)")
        if len(hay) < 4:
            db_execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS distrito_fiscal VARCHAR(80)")
            db_execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS distrito_fiscal_fuente VARCHAR(20)")
            db_execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS distrito_fiscal_revisado_en TIMESTAMP")
        _listo = True


def _norm(texto):
    from routes.ventas import _sin_tildes
    return re.sub(r'\s+', ' ', _sin_tildes(texto)).strip()


def _clave(texto):
    """Dirección comparable: sin tildes, mayúsculas, sin espacios ni signos."""
    return re.sub(r'[^A-Z0-9]', '', _norm(texto))


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


def historial(forzar=False):
    """Distritos ya elegidos en los PV: {clave de dirección: (distrito, N° PV)} y por cliente {(ruc, clave): ...}.
    Gana el más reciente. Se guarda en memoria unos segundos para no consultar en cada fila."""
    if not forzar and time.time() - _hist['t'] < HIST_SEG:
        return _hist
    por_dir, por_cli = {}, {}
    try:
        asegurar_columna()
        for p in db_query("""SELECT numero, ruc, lugar_entrega, distrito_entrega FROM pedido_compra_pc
                             WHERE COALESCE(TRIM(distrito_entrega), '') <> '' AND COALESCE(TRIM(lugar_entrega), '') <> ''
                             ORDER BY id"""):
            k = _clave(p['lugar_entrega'])
            if not k or es_recojo(p['lugar_entrega']) or _norm(p['lugar_entrega']) in _SIN_DIRECCION:
                continue
            por_dir[k] = (p['distrito_entrega'].strip(), p['numero'])
            por_cli[(str(p.get('ruc') or ''), k)] = (p['distrito_entrega'].strip(), p['numero'])
    except Exception as e:
        print(f"⚠️ Historial de distritos: {e}")
    _hist.update({'t': time.time(), 'por_dir': por_dir, 'por_cli': por_cli})
    return _hist


def _de_historial(lugar, ruc):
    k = _clave(lugar)
    if not k:
        return None
    h = historial()
    return h['por_cli'].get((str(ruc or ''), k)) or h['por_dir'].get(k)


def resolver(pv, direccion_cliente='', distrito_cliente=''):
    """{'distrito', 'origen', 'detalle'}: origen es recojo, escrito, direccion, cliente, cliente_guardado,
    historial o '' (sin dato)."""
    from routes.ventas import adivinar_distrito
    lugar = pv.get('lugar_entrega') or pv.get('entrega') or ''
    if es_recojo(lugar):
        d = distrito_local(_codigo_empresa(pv.get('empresa_id'), pv.get('numero')))
        if d:
            return {'distrito': d, 'origen': 'recojo', 'detalle': ''}
    if (pv.get('distrito_entrega') or '').strip():
        return {'distrito': pv['distrito_entrega'].strip(), 'origen': 'escrito', 'detalle': ''}
    d = adivinar_distrito(lugar)
    if d:
        return {'distrito': d, 'origen': 'direccion', 'detalle': ''}
    en_fiscal = _norm(lugar) in _SIN_DIRECCION or (direccion_cliente and _clave(lugar) == _clave(direccion_cliente))
    if en_fiscal:
        if (distrito_cliente or '').strip():
            return {'distrito': distrito_cliente.strip(), 'origen': 'cliente_guardado', 'detalle': ''}
        d = adivinar_distrito(direccion_cliente)
        if d:
            return {'distrito': d, 'origen': 'cliente', 'detalle': ''}
    h = _de_historial(lugar if _norm(lugar) not in _SIN_DIRECCION else direccion_cliente, pv.get('ruc'))
    if h:
        return {'distrito': h[0], 'origen': 'historial', 'detalle': h[1]}
    return {'distrito': '', 'origen': '', 'detalle': ''}


def _datos_clientes(rucs):
    out = {}
    if not rucs:
        return out
    for c in db_query("""SELECT numero_documento, direccion_fiscal, to_jsonb(c) ->> 'distrito_fiscal' AS distrito_fiscal
                         FROM clientes c WHERE numero_documento = ANY(%s) ORDER BY id""", (list(rucs),)):
        out.setdefault(c['numero_documento'], c)
    return out


def completar_lista(filas):
    """Agrega distrito_entrega (el del formulario), distrito_entrega_ver y distrito_origen a cada PV de la lista."""
    asegurar_columna()
    relleno_en_segundo_plano()
    if not filas:
        return
    rucs = {str(f.get('ruc') or '') for f in filas if f.get('ruc')}
    numeros = [f.get('numero') for f in filas if f.get('numero')]
    cli, extra = {}, {}
    try:
        cli = _datos_clientes(rucs)
        if numeros:
            for p in db_query("""SELECT numero, distrito_entrega, to_jsonb(p)->>'empresa_id' AS empresa_id
                                 FROM pedido_compra_pc p WHERE numero = ANY(%s)""", (numeros,)):
                extra[p['numero']] = p
    except Exception as e:
        print(f"⚠️ Distrito de entrega: {e}")
    for f in filas:
        x = extra.get(f.get('numero')) or {}
        c = cli.get(str(f.get('ruc') or '')) or {}
        pv = {**f, 'distrito_entrega': x.get('distrito_entrega'), 'empresa_id': x.get('empresa_id')}
        r = resolver(pv, c.get('direccion_fiscal') or '', c.get('distrito_fiscal') or '')
        f['distrito_entrega_ver'] = r['distrito']
        f['distrito_origen'] = r['origen']
        f['distrito_entrega'] = x.get('distrito_entrega') or ''


def _guardar_en_cliente(ruc, distrito, fuente):
    """El distrito fiscal queda en el cliente solo si aún no tiene uno (no se pisa lo que ya está)."""
    if not ruc or not distrito:
        return
    db_execute("""UPDATE clientes SET distrito_fiscal = %s, distrito_fiscal_fuente = %s,
                         distrito_fiscal_revisado_en = NOW() AT TIME ZONE 'America/Lima'
                  WHERE numero_documento = %s AND COALESCE(TRIM(distrito_fiscal), '') = ''""",
               (distrito[:80], fuente, ruc))


def _distrito_sunat(ruc):
    """(distrito, dirección) del domicilio fiscal en SUNAT. Solo si hay clave (token) en Render; si no, ('', '')."""
    from routes.consulta_ruc import _token, consultar_ruc_externo
    from routes.ventas import adivinar_distrito
    if not _token():
        return '', ''
    try:
        datos = consultar_ruc_externo(ruc)
    except Exception as e:
        print(f"⚠️ Distrito en SUNAT de {ruc}: {e}")
        return '', ''
    texto = datos.get('distrito') or ''
    return (adivinar_distrito(texto) or texto.strip().title()), (datos.get('direccion') or '')


def sugerir(lugar, ruc='', numero='', empresa_id=None):
    """Para el formulario del PV: el distrito que se llena solo y de dónde salió."""
    asegurar_columna()
    ruc = re.sub(r'\D', '', str(ruc or ''))
    c = _datos_clientes({ruc}).get(ruc, {}) if ruc else {}
    r = resolver({'lugar_entrega': lugar, 'ruc': ruc, 'numero': numero, 'empresa_id': empresa_id},
                 c.get('direccion_fiscal') or '', c.get('distrito_fiscal') or '')
    en_fiscal = _norm(lugar) in _SIN_DIRECCION or (c.get('direccion_fiscal') and _clave(lugar) == _clave(c['direccion_fiscal']))
    if not r['distrito'] and ruc and len(ruc) == 11 and (en_fiscal or not c.get('direccion_fiscal')):
        d, direccion = _distrito_sunat(ruc)
        # El distrito de SUNAT es el del domicilio fiscal: sirve solo si la entrega es en esa dirección
        if d and (en_fiscal or _clave(direccion) == _clave(lugar)):
            _guardar_en_cliente(ruc, d, 'sunat')
            r = {'distrito': d, 'origen': 'sunat', 'detalle': ''}
    texto = TEXTO_ORIGEN.get(r['origen'], '')
    if r['origen'] == 'historial' and r['detalle']:
        texto += f" (en el {r['detalle']})"
    return {**r, 'texto': texto}


_relleno = {'t': 0}
RELLENO_SEG = 12 * 3600


def completar_clientes_sunat(maximo=60):
    """Busca en SUNAT el distrito fiscal de los clientes con PV que aún no lo tienen (solo con clave en Render).
    Así los PV y Entregas que salían en rojo se llenan solos. Cada cliente se consulta una sola vez."""
    from routes.consulta_ruc import _token
    if not _token():
        return 0
    asegurar_columna()
    hechos = 0
    filas = db_query("""SELECT DISTINCT c.numero_documento FROM clientes c
                        JOIN pedido_compra_pc p ON p.ruc = c.numero_documento
                        WHERE COALESCE(TRIM(c.distrito_fiscal), '') = '' AND c.distrito_fiscal_revisado_en IS NULL
                          AND length(c.numero_documento) = 11
                        LIMIT %s""", (maximo,))
    for f in filas:
        ruc = f['numero_documento']
        d, _ = _distrito_sunat(ruc)
        if d:
            _guardar_en_cliente(ruc, d, 'sunat')
            hechos += 1
        else:   # no se vuelve a consultar ese RUC (se marca revisado aunque SUNAT no dé distrito)
            db_execute("""UPDATE clientes SET distrito_fiscal_revisado_en = NOW() AT TIME ZONE 'America/Lima'
                          WHERE numero_documento = %s AND distrito_fiscal_revisado_en IS NULL""", (ruc,))
        time.sleep(0.3)
    return hechos


def relleno_en_segundo_plano():
    """Una vez cada 12 horas, sin hacer esperar a nadie."""
    from routes.consulta_ruc import _token
    if not _token() or time.time() - _relleno['t'] < RELLENO_SEG:
        return
    _relleno['t'] = time.time()

    def _correr():
        try:
            n = completar_clientes_sunat()
            if n:
                print(f"✅ Distrito fiscal de {n} cliente(s) tomado de SUNAT")
        except Exception as e:
            print(f"⚠️ Relleno de distritos con SUNAT: {e}")
    threading.Thread(target=_correr, daemon=True).start()


def guardar(pv_id, valor, usuario=''):
    """Guarda el "Distrito de entrega" que viene del formulario del PV (vacío lo borra). Con auditoría si cambia.
    Si la entrega es en la dirección fiscal del cliente, también queda como distrito fiscal del cliente."""
    from routes.ventas import adivinar_distrito
    asegurar_columna()
    valor = re.sub(r'\s+', ' ', str(valor or '')).strip()
    if valor:
        valor = adivinar_distrito(valor) or valor[:80]
    filas = db_query("SELECT id, numero, ruc, lugar_entrega, distrito_entrega FROM pedido_compra_pc WHERE id = %s", (pv_id,))
    if not filas:
        return valor
    f = filas[0]
    if valor and f.get('ruc') and not es_recojo(f.get('lugar_entrega')):
        c = _datos_clientes({str(f['ruc'])}).get(str(f['ruc']), {})
        if _norm(f.get('lugar_entrega')) in _SIN_DIRECCION or (
                c.get('direccion_fiscal') and _clave(f.get('lugar_entrega')) == _clave(c['direccion_fiscal'])):
            try:
                _guardar_en_cliente(str(f['ruc']), valor, 'elegido')
            except Exception as e:
                print(f"⚠️ Distrito fiscal del cliente: {e}")
    if (f.get('distrito_entrega') or '') == valor:
        return valor
    db_execute("UPDATE pedido_compra_pc SET distrito_entrega = %s WHERE id = %s", (valor or None, pv_id))
    _hist['t'] = 0
    try:
        from routes.auditoria import registrar_auditoria
        registrar_auditoria('ACTUALIZAR', 'Ventas', 'pedido_compra_pc', pv_id,
                            antes={'distrito_entrega': f.get('distrito_entrega')}, despues={'distrito_entrega': valor or None},
                            detalle=f"Distrito de entrega del {f.get('numero') or pv_id}: {valor or '(vacío)'}")
    except Exception as e:
        print(f"⚠️ Auditoría del distrito de entrega: {e}")
    return valor
