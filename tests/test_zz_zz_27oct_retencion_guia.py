"""
Erika 27/10/2026 20:34-20:45:
  - "Agente de retención: Sí / No" del cliente: si NO es agente, la factura no lleva retención; si SÍ, se aplica.
    Se consulta en el padrón de SUNAT o lo marca a mano un aprobador (con auditoría).
  - Guía parcial y guía por saldo: nunca más de lo que pide el PV; el avance del PV se consulta también por la cotización.
  - Sin "Crear despacho" en el menú de la cotización.
Datos inventados, solo en la base local.
"""
import io
import json
import zipfile
from pathlib import Path

from tests.test_inventario import _sql

RAIZ = Path(__file__).resolve().parent.parent
RUC = '20999888777'


def _factura(cliente, **extra):
    datos = {'tipo': 'FACTURA', 'serie': 'F001', 'cliente': 'CLIENTE ZZ RET', 'ruc': RUC,
             'total': 1180, 'subtotal': 1000, 'igv': 180, 'estado': 'Borrador', 'items': []}
    datos.update(extra)
    return cliente.post('/ventas/api/comprobantes/guardar', json=datos)


def test_leer_padron_sunat():
    from routes.agente_retencion import leer_padron
    lineas = ['RUC|NOMBRE O RAZON SOCIAL|A PARTIR DEL|RESOLUCION|'] + \
             [f'20{i:09d}|EMPRESA {i}|01/06/2002|R.S. 037-2002|' for i in range(150)] + ['20999888777|CLIENTE ZZ|01/02/2015|R.S. 001|']
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('AgenRet_TXT.txt', '\r\n'.join(lineas).encode('latin-1'))
    datos = leer_padron(buf.getvalue())
    assert datos[RUC] == '01/02/2015' and len(datos) == 151


def test_cliente_no_agente_factura_sin_retencion(admin, vendedor, monkeypatch):
    import routes.agente_retencion as ar
    _sql("UPDATE clientes SET agente_retencion = NULL, agente_retencion_fuente = NULL WHERE numero_documento = %s", (RUC,), fetch=False) \
        if _sql("SELECT 1 FROM information_schema.columns WHERE table_name = 'clientes' AND column_name = 'agente_retencion'") else None
    # SUNAT dice que NO está en el padrón
    monkeypatch.setattr(ar, 'padron', lambda: {f'20{i:09d}': '' for i in range(200)})
    d = admin.get(f'/ventas/api/agente-retencion?ruc={RUC}').json['data']
    assert d['agente'] is False and d['fuente'] == 'SUNAT'
    r = _factura(vendedor, tiene_retencion=True, monto_retenido=35.4, monto_a_pagar=1144.6)
    assert r.status_code == 200, r.json
    fila = _sql("SELECT tiene_retencion, monto_retenido, monto_a_pagar FROM comprobantes WHERE id = %s", (r.json['data']['id'],))[0]
    assert fila[0] is False and float(fila[1] or 0) == 0 and float(fila[2]) == 1180
    # Un vendedor no puede marcarlo a mano; un aprobador sí, y queda en la auditoría
    assert vendedor.post('/ventas/api/agente-retencion/manual', json={'ruc': RUC, 'agente': True}).status_code == 403
    r = admin.post('/ventas/api/agente-retencion/manual', json={'ruc': RUC, 'agente': True})
    assert r.status_code == 200 and r.json['data']['agente'] is True and r.json['data']['fuente'] == 'Manual'
    assert _sql("SELECT 1 FROM erp_auditoria WHERE tabla = 'clientes' AND detalle LIKE 'Agente de retención%%'")
    # Marcado a mano: la consulta automática no lo cambia
    assert admin.get(f'/ventas/api/agente-retencion?ruc={RUC}').json['data']['agente'] is True
    # Ahora SÍ es agente: la factura lleva retención aunque no la marquen
    r = _factura(vendedor, tiene_retencion=False)
    fila = _sql("SELECT tiene_retencion, monto_retenido, monto_a_pagar FROM comprobantes WHERE id = %s", (r.json['data']['id'],))[0]
    assert fila[0] is True and float(fila[1]) == 35.4 and float(fila[2]) == 1144.6
    _sql("UPDATE clientes SET agente_retencion = NULL, agente_retencion_fuente = NULL WHERE numero_documento = %s", (RUC,), fetch=False)


def test_sunat_caido_no_cambia_nada(admin, monkeypatch):
    import routes.agente_retencion as ar

    def falla():
        raise ar.ErrorPadron('No se pudo conectar con SUNAT.')
    monkeypatch.setattr(ar, 'padron', falla)
    d = admin.get(f'/ventas/api/agente-retencion?ruc={RUC}').json['data']
    assert d['agente'] is None and 'a mano' in d['aviso']


def test_guia_por_saldo_y_avance_por_cotizacion(admin):
    pv = 'PV-ZZGS-1'
    _sql("DELETE FROM guias_remision WHERE documento_asociado IN (%s, 'COT-ZZGS-1')", (pv,), fetch=False)
    _sql("DELETE FROM pedido_compra_pc WHERE numero = %s", (pv,), fetch=False)
    _sql("""INSERT INTO pedido_compra_pc (numero, cliente, ruc, estado, items_json, fecha, condicion_pago, cotizacion_numero)
            VALUES (%s, 'KOMATSU ZZ', '20100070970', 'Pendiente', %s, NOW(), 'Contado', 'COT-ZZGS-1')""",
         (pv, json.dumps([{'codigo': 'PRD-0001', 'producto': 'Protector solar', 'cantidad_pc': 10, 'precio_pc': 10}])), fetch=False)
    # Primera guía parcial: 8 de 10 (hecha desde la cotización)
    _sql("""INSERT INTO guias_remision (serie, numero, ruc_destinatario, destinatario_nombre, documento_asociado, items_json, estado_sunat)
            VALUES ('T001', '00099701', '20100070970', 'KOMATSU ZZ', 'COT-ZZGS-1', %s, 'Emitida')""",
         (json.dumps([{'codigo': 'PRD-0001', 'cantidad': 8}]),), fetch=False)
    a = admin.get('/ventas/api/pv/avance', query_string={'numero': 'COT-ZZGS-1'}).json['data']
    assert a['pv'] == pv and a['posiciones'][0]['guiado'] == 8 and a['guias'] == ['T001-00099701'] and a['faltan_guia'] == [1]
    # La guía por saldo no puede llevar más de 2
    from routes.ventas import _guia_duplicada
    msg = _guia_duplicada({'pc_numero': pv, 'items': [{'codigo': 'PRD-0001', 'cantidad': 3}]})
    assert msg and 'como máximo 2' in msg
    assert _guia_duplicada({'pc_numero': pv, 'items': [{'codigo': 'PRD-0001', 'cantidad': 2}]}) is None


def test_pantallas():
    js = (RAIZ / 'static/js/ventas.js').read_text(encoding='utf-8-sig')
    assert "createDocFromCotizacion(${id},'despacho')" not in js
    # La guía guarda la cantidad escrita en la tabla (antes guardaba la original de la cotización)
    assert 'productos.push({ ...base, codigo, producto: base.producto || descripcion, um, cantidad });' in js
    gp = (RAIZ / 'static/js/guia_parcial.js').read_text(encoding='utf-8')
    assert 'GUÍA PARCIAL' in gp and 'GUÍA POR SALDO' in gp
    fp = (RAIZ / 'static/js/factura_parcial.js').read_text(encoding='utf-8')
    assert 'FACTURA PARCIAL' in fp and 'no salió con guía' in fp
    # El modal es position:fixed: mirar su offsetParent dejaba la factura parcial sin aparecer nunca
    assert "const c = $('compPC');" in fp and "$('comprobanteModal') || $('comprobanteForm')" not in fp
    html = (RAIZ / 'templates/ventas/index.html').read_text(encoding='utf-8-sig')
    assert 'js/guia_parcial.js' in html and 'js/agente_retencion.js' in html
