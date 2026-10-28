"""Hasta 3 cuentas bancarias por proveedor y regla de ahorro (Erika, 28/10/2026 17:23).

"Cuando esté en el módulo de KCF, que jale preferentemente las cuentas solo y únicamente del BBVA... en el caso de AGD
que jale únicamente su cuenta BCP. Si el proveedor no tuviera, ya que jale la siguiente cuenta. Con su número de cuenta
y su CCI... que sea una regla porque no quisiera estar pagando una comisión en el banco."

- Cuenta 1 = las columnas de siempre (banco, tipo_cuenta, numero_cuenta, cci) + moneda_cuenta.
- Cuenta 2 y 3 = banco2/tipo_cuenta2/moneda_cuenta2/numero_cuenta2/cci2 y lo mismo con 3 (migración 043).
- El banco de cada empresa sale de Configuración ▸ Empresas (cuenta principal); si no hay, KCF = BBVA y AGD = BCP.
- Se elige la primera cuenta del mismo banco que la empresa que paga (si hay varias, la de la moneda del documento);
  si no tiene, la siguiente cuenta registrada, con aviso en rojo de que el banco puede cobrar comisión.
"""
import threading
import time

from database import db_query, db_execute
from utils import normalizar_banco

BANCO_POR_DEFECTO = {'KCF': 'BBVA', 'AGD': 'BCP'}
EXTRA = ('banco', 'tipo_cuenta', 'moneda_cuenta', 'numero_cuenta', 'cci')
COLUMNAS_NUEVAS = ['moneda_cuenta'] + [f'{c}{n}' for n in (2, 3) for c in EXTRA]
# Para los SELECT: todas las columnas de las 3 cuentas
COLUMNAS_SQL = ', '.join(['banco', 'tipo_cuenta', 'numero_cuenta', 'cci'] + COLUMNAS_NUEVAS)

_listo = False
_lock = threading.Lock()
_bancos = {'t': 0, 'por_id': {}, 'por_codigo': {}, 'codigo': {}}


def asegurar():
    """En la base real las columnas vienen de la migración 043; en la de pruebas se crean aquí."""
    global _listo
    if _listo:
        return
    with _lock:
        if _listo:
            return
        hay = {r['column_name'] for r in db_query(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'proveedores'")}
        for c in COLUMNAS_NUEVAS:
            if c not in hay:
                largo = 80 if c.startswith('banco') else 40 if not c.startswith('moneda') else 20
                db_execute(f"ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS {c} VARCHAR({largo})")
        _listo = True


def moneda(texto):
    t = str(texto or '').strip().lower()
    return 'USD' if t.startswith(('usd', 'dol', 'dól', '$', 'us')) else 'PEN'


def cuentas(p):
    """Las cuentas registradas del proveedor, en orden (1, 2, 3). Solo las que tienen N° de cuenta o CCI."""
    p = p or {}
    salida = []
    for n, suf in ((1, ''), (2, '2'), (3, '3')):
        num = str(p.get('numero_cuenta' + suf) or '').strip()
        cci = str(p.get('cci' + suf) or '').strip()
        if not (num or cci):
            continue
        # Cuenta 1 sin moneda (registros antiguos): la moneda comercial del proveedor
        mon = p.get('moneda_cuenta' + suf) or ((p.get('prov_moneda') or p.get('moneda')) if n == 1 else None)
        salida.append({'orden': n, 'banco': normalizar_banco(p.get('banco' + suf)) or '',
                       'tipo': p.get('tipo_cuenta' + suf) or '', 'moneda': moneda(mon),
                       'numero_cuenta': num, 'cci': cci})
    return salida


def _cargar_bancos():
    if time.time() - _bancos['t'] < 60:
        return
    por_id, por_codigo, codigo = {}, {}, {}
    try:
        for f in db_query("""
                SELECT e.id::text AS id, UPPER(e.codigo) AS codigo, cb.banco
                FROM erp_empresas e
                LEFT JOIN LATERAL (
                    SELECT banco FROM erp_empresa_cuentas_bancarias c
                    WHERE c.empresa_id = e.id AND COALESCE(c.estado, 'activo') = 'activo'
                    ORDER BY c.es_principal DESC NULLS LAST, c.id LIMIT 1
                ) cb ON TRUE"""):
            banco = normalizar_banco(f['banco']) or BANCO_POR_DEFECTO.get(f['codigo'])
            por_id[f['id']] = banco
            por_codigo[f['codigo']] = banco
            codigo[f['id']] = f['codigo']
    except Exception:
        # Base sin cuentas de empresa: el banco por defecto de cada código (KCF BBVA, AGD BCP)
        try:
            for f in db_query("SELECT id::text AS id, UPPER(codigo) AS codigo FROM erp_empresas"):
                por_id[f['id']] = BANCO_POR_DEFECTO.get(f['codigo'])
                por_codigo[f['codigo']] = BANCO_POR_DEFECTO.get(f['codigo'])
                codigo[f['id']] = f['codigo']
        except Exception:
            pass
    # Si todavía no hay empresas (base nueva) no se guarda en memoria: se vuelve a leer en la siguiente consulta
    _bancos.update(t=time.time() if por_id else 0, por_id=por_id, por_codigo=por_codigo, codigo=codigo)


def banco_empresa(empresa):
    """Banco de la empresa que paga: por id (uuid) o por código (KCF / AGD)."""
    if not empresa:
        return None
    _cargar_bancos()
    e = str(empresa)
    return _bancos['por_id'].get(e) or _bancos['por_codigo'].get(e.upper()) or BANCO_POR_DEFECTO.get(e.upper())


def bancos_por_empresa():
    _cargar_bancos()
    return dict(_bancos['por_id'])


def cuenta_preferida(p, empresa=None, moneda_doc=None):
    """La cuenta a la que se paga. None si el proveedor no tiene ninguna."""
    lista = cuentas(p)
    if not lista:
        return None
    banco = banco_empresa(empresa)
    nombre = _bancos['codigo'].get(str(empresa)) or str(empresa or '').upper() or 'la empresa'
    mon = moneda(moneda_doc) if moneda_doc else None

    def primera(cands):
        if mon:
            for c in cands:
                if c['moneda'] == mon:
                    return c
        return cands[0] if cands else None

    mismas = [c for c in lista if banco and c['banco'].upper() == banco.upper()]
    elegida = dict(primera(mismas) or primera(lista))
    elegida['banco_empresa'] = banco or ''
    elegida['mismo_banco'] = bool(mismas)
    elegida['total_cuentas'] = len(lista)
    if not banco:
        elegida['aviso'] = ''
    elif mismas:
        elegida['aviso'] = f'✅ Cuenta {banco}: mismo banco que {nombre}, sin comisión.'
    else:
        elegida['aviso'] = (f'⚠️ El proveedor no tiene cuenta {banco} (banco de {nombre}): se paga a su cuenta '
                            f'{elegida["banco"] or "de otro banco"}. El banco puede cobrar comisión.')
    return elegida


def aplicar(p, empresa=None, moneda_doc=None):
    """Pone en p (dict) banco / numero_cuenta / cci / tipo_cuenta de la cuenta elegida y el aviso.
    Así las pantallas que ya leían esas claves muestran la cuenta correcta sin más cambios."""
    if p is None:
        return p
    c = cuenta_preferida(p, empresa, moneda_doc)
    p['cuentas'] = cuentas(p)
    if c:
        p.update(banco=c['banco'], numero_cuenta=c['numero_cuenta'], cci=c['cci'], tipo_cuenta=c['tipo'],
                 cuenta_orden=c['orden'], cuenta_moneda=c['moneda'], cuenta_mismo_banco=c['mismo_banco'],
                 cuenta_aviso=c['aviso'], banco_empresa=c['banco_empresa'])
    for k in COLUMNAS_NUEVAS:
        p.pop(k, None)
    return p


def datos_formulario(data):
    """Columnas de las cuentas 2 y 3 (y la moneda de la cuenta 1) desde el formulario de Maestros."""
    data = data or {}
    vals = {'moneda_cuenta': (data.get('monedaCuenta') or '').strip() or None}
    for n in (2, 3):
        vals[f'banco{n}'] = normalizar_banco(data.get(f'banco{n}'))
        vals[f'tipo_cuenta{n}'] = (data.get(f'tipoCuenta{n}') or '').strip() or None
        vals[f'moneda_cuenta{n}'] = (data.get(f'monedaCuenta{n}') or '').strip() or None
        vals[f'numero_cuenta{n}'] = (data.get(f'cuenta{n}') or '').strip() or None
        vals[f'cci{n}'] = (data.get(f'cci{n}') or '').strip() or None
    return vals


def guardar(cur, proveedor_id, data):
    """Guarda las cuentas 2 y 3 en la misma transacción del alta o la edición del proveedor.
    Llamar antes a asegurar(), fuera de la transacción."""
    vals = datos_formulario(data)
    cur.execute('UPDATE proveedores SET ' + ', '.join(f'{k} = %s' for k in vals) + ' WHERE id = %s',
                list(vals.values()) + [proveedor_id])


def para_formulario(p):
    """Claves que espera fillProveedorForm() para las cuentas 2 y 3."""
    p = p or {}
    out = {'monedaCuenta': p.get('moneda_cuenta') or ''}
    for n in (2, 3):
        out.update({f'banco{n}': p.get(f'banco{n}') or '', f'tipoCuenta{n}': p.get(f'tipo_cuenta{n}') or '',
                    f'monedaCuenta{n}': p.get(f'moneda_cuenta{n}') or '', f'cuenta{n}': p.get(f'numero_cuenta{n}') or '',
                    f'cci{n}': p.get(f'cci{n}') or ''})
    return out
