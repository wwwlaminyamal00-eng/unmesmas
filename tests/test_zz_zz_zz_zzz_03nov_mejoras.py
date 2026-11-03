"""
Erika 03/11/2026:
  1. Despachar: si hay stock libre en la empresa del despacho, deja; si no, dice POR QUÉ (hay 0, separado para otro
     cliente, la mercadería es de la otra empresa). Un despacho de KCF no saca mercadería de AGD sin venta entre empresas.
     La empresa se muestra con su código (KCF), nunca "KC".
  2. Guía de remisión: los 11 motivos de traslado de SUNAT.
  3. Ningún traslado sin guía de remisión: se genera sola o se vincula una válida; uno antiguo sin guía no se recibe.
Datos inventados, solo en la base local de pruebas.
"""
import json
from pathlib import Path

import pytest

from tests.test_inventario import _sql
from utils import normalizar_motivo_traslado, es_motivo_venta, MOTIVOS_TRASLADO_SUNAT

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture(scope='module')
def d3(app):
    _sql("""
        INSERT INTO erp_empresas (codigo, nombre_corto, nombre_comercial, razon_social, ruc, estado, color_primario, color_secundario, color_pastel)
        SELECT 'KCF', 'KCF', 'KCF', 'KCF S.A.C.', '20111111111', 'activo', '#D6243A', '#1D1A1F', '#FDE8EB' WHERE NOT EXISTS (SELECT 1 FROM erp_empresas WHERE codigo='KCF');
        INSERT INTO erp_empresas (codigo, nombre_corto, nombre_comercial, razon_social, ruc, estado, color_primario, color_secundario, color_pastel)
        SELECT 'AGD', 'AGD', 'AGD', 'AGD S.A.C.', '20222222222', 'activo', '#1D4ED8', '#1D1A1F', '#DBEAFE' WHERE NOT EXISTS (SELECT 1 FROM erp_empresas WHERE codigo='AGD');
        INSERT INTO almacenes (codigo, nombre, direccion, activo)
        SELECT 'SMP', 'San Martín de Porres', 'Av. Perú 123, SMP', true WHERE NOT EXISTS (SELECT 1 FROM almacenes WHERE codigo='SMP');
        INSERT INTO almacenes (codigo, nombre, direccion, activo)
        SELECT 'BRE', 'Breña', 'Jr. Breña 456', true WHERE NOT EXISTS (SELECT 1 FROM almacenes WHERE codigo='BRE');
        INSERT INTO productos (familia, codigo, descripcion, marca, unidad, costo_unitario, precio_unitario, stock, activo)
        VALUES ('GENERAL', 'Z3-001', 'LAPIZ ZZ', 'ZZ', 'NIU', 3, 19, 0, true);
    """, fetch=False)
    emp = dict(_sql("SELECT codigo, id FROM erp_empresas WHERE codigo IN ('KCF', 'AGD')"))
    sede = dict(_sql("SELECT codigo, id FROM almacenes WHERE codigo IN ('SMP', 'BRE')"))
    pid = _sql("SELECT id FROM productos WHERE codigo = 'Z3-001'")[0][0]
    # Las 50 son de AGD en Breña (como en el caso real); KCF no tiene
    _sql("INSERT INTO inv_stock (empresa_id, almacen_id, producto_id, cantidad, costo_promedio, valor) VALUES (%s,%s,%s,50,3,150)",
         (emp['AGD'], sede['BRE'], pid), fetch=False)
    items = [{'codigo': 'Z3-001', 'producto': 'LAPIZ ZZ', 'cantidad': 50}]
    desp = _sql("""INSERT INTO despachos (numero, cliente, ruc, pc_numero, estado, items_json, empresa_id)
                   VALUES ('DES-Z3-1', 'TRANSPORTES ZZ S.R.L.', '20555000111', 'PV-Z3-0001', 'Pendiente despacho', %s, %s)
                   RETURNING id""", (json.dumps(items), emp['KCF']))[0][0]
    return {'emp': emp, 'sede': sede, 'pid': pid, 'desp': desp}


def _opcion(r, cod, sede_id):
    return next(o for o in r['opciones'] if o['empresa'] == cod and o['almacen_id'] == sede_id)


def test_despacho_dice_por_que_no_alcanza_y_usa_el_codigo(d3, vendedor):
    _sql("UPDATE erp_empresas SET nombre_corto = 'KC' WHERE codigo = 'KCF'", fetch=False)
    try:
        r = vendedor.get(f"/ventas/api/despachos/{d3['desp']}/ubicaciones").get_json()
    finally:
        _sql("UPDATE erp_empresas SET nombre_corto = 'KCF' WHERE codigo = 'KCF'", fetch=False)
    assert all(o['empresa'] in ('KCF', 'AGD') for o in r['opciones'])  # nunca "KC"
    kcf = _opcion(r, 'KCF', d3['sede']['SMP'])
    assert not kcf['alcanza'] and 'hay 0' in kcf['motivo'] and 'LAPIZ ZZ' in kcf['motivo']
    agd = _opcion(r, 'AGD', d3['sede']['BRE'])
    assert agd['hay_todo'] and agd['otra_empresa'] and not agd['alcanza']
    assert 'venta entre empresas' in agd['motivo'] and 'KCF' in agd['motivo']


def test_despacho_no_saca_mercaderia_de_la_otra_empresa(d3, vendedor):
    r = vendedor.put(f"/ventas/api/despachos/{d3['desp']}/toggle",
                     json={'estado': 'Despachado', 'empresa_id': str(d3['emp']['AGD']), 'almacen_id': d3['sede']['BRE']})
    j = r.get_json()
    assert r.status_code == 409 and j['codigo'] == 'otra_empresa'
    assert 'es de AGD' in j['error'] and 'despacho es de KCF' in j['error']
    assert float(_sql("SELECT cantidad FROM inv_stock WHERE empresa_id=%s AND almacen_id=%s AND producto_id=%s",
                      (d3['emp']['AGD'], d3['sede']['BRE'], d3['pid']))[0][0]) == 50


def test_despacho_dice_para_quien_esta_separado(d3, vendedor):
    _sql("""INSERT INTO inv_stock (empresa_id, almacen_id, producto_id, cantidad, costo_promedio, valor)
            VALUES (%s,%s,%s,50,3,150)""", (d3['emp']['KCF'], d3['sede']['SMP'], d3['pid']), fetch=False)
    _sql("""INSERT INTO inv_separaciones (numero, empresa_id, almacen_id, producto_id, cantidad, cantidad_inicial, cliente,
                documento, vence_el) VALUES ('SEP-Z3', %s, %s, %s, 20, 20, 'EMBAJADA ZZ', 'PV-Z3-OTRO', CURRENT_DATE + 3)""",
         (d3['emp']['KCF'], d3['sede']['SMP'], d3['pid']), fetch=False)
    r = vendedor.get(f"/ventas/api/despachos/{d3['desp']}/ubicaciones").get_json()
    kcf = _opcion(r, 'KCF', d3['sede']['SMP'])
    assert not kcf['alcanza'] and 'hay 50 pero están separados' in kcf['motivo'] and 'EMBAJADA ZZ' in kcf['motivo']
    # La separación vence: el stock queda libre y ya se puede despachar
    _sql("UPDATE inv_separaciones SET vence_el = CURRENT_DATE - 1 WHERE numero = 'SEP-Z3'", fetch=False)
    r = vendedor.get(f"/ventas/api/despachos/{d3['desp']}/ubicaciones").get_json()
    assert r['opciones'][0]['empresa'] == 'KCF' and r['opciones'][0]['alcanza']
    js = (RAIZ / 'static/js/ventas.js').read_text(encoding='utf-8')
    assert 'o.otra_empresa' in js and 'No alcanza el stock para despachar' in js


def test_motivos_de_traslado_como_sunat():
    textos = [t for _, t in MOTIVOS_TRASLADO_SUNAT]
    assert len(textos) == 11 and textos[3] == 'Traslado entre establecimientos de la misma empresa'
    assert normalizar_motivo_traslado('VENTA') == 'Venta' and normalizar_motivo_traslado('01') == 'Venta'
    assert normalizar_motivo_traslado('TRANSFERENCIA ENTRE ALMACENES') == textos[3]
    assert normalizar_motivo_traslado('OTRO') == 'Otros (no especificados en los anteriores)'
    assert normalizar_motivo_traslado('') == 'Venta'
    assert es_motivo_venta('Venta con entrega a terceros') and not es_motivo_venta('Compra')
    modal = (RAIZ / 'templates/ventas/modales/guia_modal.html').read_text(encoding='utf-8')
    js = (RAIZ / 'static/js/ventas.js').read_text(encoding='utf-8')
    for t in textos:
        assert f'<option value="{t}">{t}</option>' in modal and f"'{t}'" in js
    assert 'TRANSFERENCIA ENTRE ALMACENES</option>' not in modal


def test_guia_guarda_motivo_sunat(d3, admin):
    assert admin.post('/api/empresa_activa', json={'codigo': 'KCF'}).status_code == 200
    r = admin.post('/ventas/api/guias/guardar', json={
        'serie': 'T099', 'motivo_traslado': 'TRANSFERENCIA ENTRE ALMACENES', 'destinatario_nombre': 'ZZ',
        'ruc_destinatario': '20111111111', 'items': []})
    admin.post('/api/empresa_activa', json={'codigo': 'TODAS'})
    assert r.status_code == 200, r.get_json()
    gid = r.get_json()['data']['id']
    assert _sql("SELECT motivo_traslado FROM guias_remision WHERE id = %s", (gid,))[0][0] == \
        'Traslado entre establecimientos de la misma empresa'


def test_traslado_antiguo_sin_guia_no_se_recibe_hasta_generarla(d3, admin):
    r = admin.post('/inventario/api/traslados', json={
        'empresa_id': d3['emp']['AGD'], 'origen_id': d3['sede']['BRE'], 'destino_id': d3['sede']['SMP'],
        'encargado': 'Arturo ZZ', 'items': [{'producto_id': d3['pid'], 'cantidad': 5}]})
    assert r.status_code == 200, r.get_json()
    numero = r.get_json()['numero']
    tid, item = _sql("SELECT t.id, i.id FROM inv_traslados t JOIN inv_traslado_items i ON i.traslado_id = t.id "
                     "WHERE t.numero = %s", (numero,))[0]
    # Así quedaron los traslados de antes (sin guía)
    _sql("UPDATE inv_traslados SET guia_remision = NULL WHERE id = %s", (tid,), fetch=False)
    r = admin.post(f'/inventario/api/traslados/{tid}/recibir', json={'recibido': {str(item): 5}})
    assert r.status_code == 400 and 'Generar guía' in r.get_json()['error']
    r = admin.post(f'/inventario/api/traslados/{tid}/guia', json={})
    assert r.status_code == 200, r.get_json()
    guia = r.get_json()['guia']
    assert _sql("SELECT guia_remision FROM inv_traslados WHERE id = %s", (tid,))[0][0] == guia
    # Una guía ya usada no sirve para otro traslado
    r2 = admin.post('/inventario/api/traslados', json={
        'empresa_id': d3['emp']['AGD'], 'origen_id': d3['sede']['BRE'], 'destino_id': d3['sede']['SMP'],
        'encargado': 'Arturo ZZ', 'guia_remision': guia, 'items': [{'producto_id': d3['pid'], 'cantidad': 1}]})
    assert r2.status_code == 400 and 'ya es el sustento' in r2.get_json()['error']
    assert admin.post(f'/inventario/api/traslados/{tid}/recibir', json={'recibido': {str(item): 5}}).status_code == 200
    js = (RAIZ / 'static/js/inventario.js').read_text(encoding='utf-8')
    assert 'data-guia-tra' in js and 'Generar guía' in js


def test_pv_lista_trae_el_pago_y_pv_nuevo_empieza_vacio(vendedor):
    """Erika 03/11/2026 (tarde): el pago al contado sale en la vista completa y en el Excel; un PV nuevo no trae
    el N° de operación, banco ni CCI del anterior."""
    from tests.test_zz_zz_19oct_noche import _pc
    r = _pc(vendedor, numero='', condicion_pago='Contado', pago_num_operacion='77441', pago_banco='Caja Piura',
            pago_cci='80000000000000000077')
    assert r.status_code == 200, r.json
    fila = next(p for p in vendedor.get('/ventas/api/pedido-compra/listar').get_json()['data'] if p['id'] == r.json['data']['id'])
    assert fila['pago_num_operacion'] == '77441' and fila['pago_cci'] == '80000000000000000077' and fila['pago_registrado_por']
    js = (RAIZ / 'static/js/ventas.js').read_text(encoding='utf-8')
    assert 'limpiarPagoContadoPV();' in js and 'function pagoContadoCeldaPV' in js
    assert js.count('<th class="solo-excel" style="display:none">') == 5
    from routes.herramientas import EXPORTABLES
    assert 'pv_pago_contado_historial' in EXPORTABLES


def test_aviso_de_movimientos_pendientes_en_palabras_simples():
    js = (RAIZ / 'static/js/inventario.js').read_text(encoding='utf-8')
    assert 'NO suman ni restan stock' in js and 'reportó ${esc(p.usuario_nombre)}' not in js
