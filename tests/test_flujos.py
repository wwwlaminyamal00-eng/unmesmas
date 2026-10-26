"""Pruebas de los flujos principales: seguridad, ventas, facturación, compras y finanzas."""
import threading
from datetime import date, timedelta
from decimal import Decimal

import psycopg2
import pytest

from conftest import TEST_DB, _login


def sql(q, params=None):
    conn = psycopg2.connect(TEST_DB)
    cur = conn.cursor()
    cur.execute(q, params)
    filas = cur.fetchall() if cur.description else None
    conn.commit()
    conn.close()
    return filas


PRODUCTOS = [
    {'codigo': 'PRD-0001', 'cantidad': 10, 'valorVenta': 15},   # 150.00
    {'codigo': 'PRD-0002', 'cantidad': 2, 'valorVenta': 32.5},  # 65.00
]


def nueva_cotizacion(cliente, estado='Borrador', **extra):
    payload = {'cliente_id': 1, 'estado': estado, 'productos': PRODUCTOS,
               'subtotal': 1, 'igv': 1, 'total': 99999,  # importes manipulados: el servidor los recalcula
               'contacto': 'Ana Compras', 'telefono': '999888777', 'email': 'ana@cliente.pe',
               'validez': '15 días', 'descuento_valor': 0, 'descuento_tipo': '%',
               # 4 campos obligatorios desde el 19/10/2026
               'condicion_pago': 'Crédito 30 días', 'tiempo_entrega': '2 días hábiles',
               'transporte': 'Auto', 'parihuela': 'No',
               'seguimiento': 'Hellen', 'motivo': 'Recompra', 'nota_interna': 'Ninguna'}
    payload.update(extra)
    return cliente.post('/ventas/api/cotizaciones/guardar', json=payload)


# ============================================================
# SEGURIDAD
# ============================================================
class TestSeguridad:
    def test_rutas_exigen_sesion(self, anonimo):
        assert anonimo.get('/ventas').status_code == 302
        assert anonimo.get('/api/config/usuarios').status_code == 401
        assert anonimo.get('/api/config/empresas').status_code == 401
        assert anonimo.post('/inventario/api/nuevo_movimiento', json={}).status_code == 401
        assert anonimo.get('/finanzas/api/cxc').status_code == 401

    def test_ruta_depuracion_de_sesion_eliminada(self, admin):
        assert admin.get('/debug/session').status_code == 404

    def test_login_puerta_trasera_eliminada(self, anonimo):
        # Antes "admin123" entraba con cualquier usuario existente
        r = anonimo.post('/login', data={'usuario': 'admin', 'password': 'admin123'})
        assert r.status_code == 200 and b'incorrectos' in r.data

    def test_login_password_incorrecta_e_inactivo(self, anonimo):
        assert anonimo.post('/login', data={'usuario': 'admin', 'password': 'mala'}).status_code == 200
        assert anonimo.post('/login', data={'usuario': 'inactivo', 'password': 'Inac#2026!'}).status_code == 200

    def test_login_password_heredada_texto_plano(self, app):
        _login(app, 'legado', 'clave-plana-123')

    def test_login_por_correo(self, app):
        _login(app, 'vend@test.pe', 'Vende#2026!')

    def test_configuracion_solo_admin(self, vendedor, admin):
        propios = vendedor.get('/api/config/usuarios').json['data']  # solo su propio registro
        assert [u['usuario_sistema'] for u in propios] == ['vendedor']
        assert vendedor.get('/api/config/usuarios/1/permisos?empresa_id=1').status_code == 403
        assert vendedor.put('/api/config/usuarios/1', json={'rol': 'administrador'}).status_code == 403
        assert vendedor.post('/api/config/empresas', json={}).status_code == 403
        assert vendedor.get('/usuarios').status_code == 302
        assert admin.get('/api/config/usuarios').status_code == 200
        assert vendedor.get('/api/config/empresas').status_code == 200  # lectura permitida

    def test_crear_usuario_guarda_hash(self, admin, app):
        # En Supabase el usuario debe existir antes en Auth (auth.users)
        sql("""DO $$ BEGIN IF to_regclass('auth.users') IS NOT NULL THEN
                 INSERT INTO auth.users (id, email) VALUES ('0a6f1c2e-1b2c-4d3e-8f90-123456789abc', 'nuevo@test.pe')
                 ON CONFLICT DO NOTHING; END IF; END $$""")
        r = admin.post('/api/config/usuarios', json={'auth_user_id': '0a6f1c2e-1b2c-4d3e-8f90-123456789abc', 'usuario_sistema': 'nuevo',
                                                     'nombres_apellidos': 'Nuevo', 'password': 'Nuevo#2026!',
                                                     'rol': 'vendedor'})
        assert r.status_code == 200, r.json
        pwd = sql("SELECT password FROM usuarios WHERE usuario_sistema = 'nuevo'")[0][0]
        assert pwd.startswith(('scrypt:', 'pbkdf2:'))
        _login(app, 'nuevo', 'Nuevo#2026!')
        dup = admin.post('/api/config/usuarios', json={'auth_user_id': 'b', 'usuario_sistema': 'nuevo'})
        assert dup.status_code == 400

    def test_session_info(self, vendedor):
        r = vendedor.get('/api/config/session')
        assert r.status_code == 200 and r.json['data']['usuario_sistema'] == 'vendedor'

    def test_cabeceras_seguridad(self, admin):
        r = admin.get('/index')
        assert r.headers.get('X-Content-Type-Options') == 'nosniff'


# ============================================================
# VENTAS - COTIZACIONES
# ============================================================
class TestCotizaciones:
    def test_crear_recalcula_igv_y_guarda_campos(self, vendedor):
        r = nueva_cotizacion(vendedor)
        assert r.status_code == 200, r.json
        d = r.json['data']
        assert d['subtotal'] == 215.0 and d['igv'] == 38.7 and d['total'] == 253.7
        fila = sql("SELECT total, contacto_cliente, telefono_cliente, email_cliente, validez_oferta FROM cotizaciones WHERE id = %s", (d['id'],))[0]
        assert fila[0] == Decimal('253.7') or float(fila[0]) == 253.7
        assert fila[1:] == ('Ana Compras', '999888777', 'ana@cliente.pe', '15 días')
        assert sql("SELECT COUNT(*) FROM cotizacion_detalle WHERE cotizacion_id = %s", (d['id'],))[0][0] == 2

    def test_descuento_porcentaje(self, vendedor):
        d = nueva_cotizacion(vendedor, descuento_valor=10).json['data']
        assert d['descuento'] == 21.5 and d['igv'] == 34.83 and d['total'] == 228.33

    def test_producto_inexistente_rechazado(self, vendedor):
        r = nueva_cotizacion(vendedor, productos=[{'codigo': 'NO-EXISTE', 'cantidad': 1, 'valorVenta': 5}])
        assert r.status_code == 400 and 'NO-EXISTE' in r.json['error']

    def test_cantidad_negativa_rechazada(self, vendedor):
        r = nueva_cotizacion(vendedor, productos=[{'codigo': 'PRD-0001', 'cantidad': -3, 'valorVenta': 5}])
        assert r.status_code == 400

    def test_sin_productos_rechazada(self, vendedor):
        assert nueva_cotizacion(vendedor, productos=[]).status_code == 400

    def test_vendedor_no_puede_validar_ni_generar_sin_validacion(self, vendedor):
        assert nueva_cotizacion(vendedor, estado='Validado por Hellen').status_code == 409
        assert nueva_cotizacion(vendedor, estado='Generada').status_code == 409

    def test_flujo_completo_validacion_y_generacion(self, vendedor, aprobador):
        cid = nueva_cotizacion(vendedor, estado='Por validar').json['data']['id']
        assert vendedor.post(f'/ventas/api/cotizaciones/{cid}/validar').status_code == 403
        assert aprobador.get('/ventas/api/cotizaciones/revision').json['data']
        r = aprobador.post(f'/ventas/api/cotizaciones/{cid}/validar')
        assert r.status_code == 200
        # el aprobador la marca validada; desde el 24/10 solo Hellen o un administrador la genera (pedido de Adriel)
        assert aprobador.put(f'/ventas/api/cotizaciones/{cid}/toggle', json={'estado': 'Validado por Hellen'}).status_code == 200
        assert vendedor.put(f'/ventas/api/cotizaciones/{cid}/toggle', json={'estado': 'Generada'}).status_code == 409
        assert aprobador.put(f'/ventas/api/cotizaciones/{cid}/toggle', json={'estado': 'Generada'}).status_code == 200
        # una cotización generada ya no se edita
        r = nueva_cotizacion(vendedor, id=cid)
        assert r.status_code == 409
        # aceptada por el cliente solo desde generada y es irreversible
        assert vendedor.put(f'/ventas/api/cotizaciones/{cid}/toggle', json={'estado': 'Aceptada por Cliente'}).status_code == 200
        assert vendedor.put(f'/ventas/api/cotizaciones/{cid}/toggle', json={'estado': 'Borrador'}).status_code == 409

    def test_aceptar_no_acepta_desde_borrador(self, vendedor):
        cid = nueva_cotizacion(vendedor).json['data']['id']
        assert vendedor.put(f'/ventas/api/cotizaciones/{cid}/toggle', json={'estado': 'Aceptada por Cliente'}).status_code == 409

    def test_rechazo_requiere_motivo(self, vendedor, aprobador):
        cid = nueva_cotizacion(vendedor, estado='Por validar').json['data']['id']
        assert aprobador.post(f'/ventas/api/cotizaciones/{cid}/rechazar', json={}).status_code == 400
        r = aprobador.post(f'/ventas/api/cotizaciones/{cid}/rechazar', json={'motivo_rechazo': 'Precio bajo'})
        # Requerimiento del Excel: el rechazo de Hellen deja la cotización RECHAZADA (no observada ni borrador)
        assert r.status_code == 200 and r.json['data']['estado'] == 'Rechazada'
        assert sql("SELECT motivo_rechazo FROM cotizaciones WHERE id = %s", (cid,))[0][0] == 'Precio bajo'
        # el vendedor la corrige directamente y la vuelve a enviar a validación
        r = nueva_cotizacion(vendedor, id=cid, estado='Por validar')
        assert r.status_code == 200, r.json
        assert sql("SELECT estado FROM cotizaciones WHERE id = %s", (cid,))[0][0] == 'Por validar'

    def test_numeracion_sin_duplicados_en_paralelo(self, app):
        clientes = [_login(app, 'vendedor', 'Vende#2026!') for _ in range(8)]
        resultados = []

        def crear(c):
            resultados.append(nueva_cotizacion(c).json)
        hilos = [threading.Thread(target=crear, args=(c,)) for c in clientes]
        [h.start() for h in hilos]
        [h.join() for h in hilos]
        assert all(r['success'] for r in resultados)
        dup = sql("SELECT numero_cotizacion, COUNT(*) FROM cotizaciones GROUP BY 1 HAVING COUNT(*) > 1")
        assert dup == []

    def test_editar_borrador_reemplaza_detalle(self, vendedor):
        cid = nueva_cotizacion(vendedor).json['data']['id']
        r = nueva_cotizacion(vendedor, id=cid, productos=[{'codigo': 'PRD-0001', 'cantidad': 1, 'valorVenta': 100}])
        assert r.status_code == 200 and r.json['data']['total'] == 118.0
        assert sql("SELECT COUNT(*) FROM cotizacion_detalle WHERE cotizacion_id = %s", (cid,))[0][0] == 1

    def test_anular_guarda_respaldo_y_se_puede_consultar(self, vendedor):
        cid = nueva_cotizacion(vendedor).json['data']['id']
        assert vendedor.delete(f'/ventas/api/cotizaciones/{cid}', json={}).status_code == 400
        r = vendedor.delete(f'/ventas/api/cotizaciones/{cid}', json={'motivo': 'Cliente desistió'})
        assert r.status_code == 200
        lista = vendedor.get('/api/cotizaciones/eliminadas').json['data']
        assert any(x['cotizacion_id_original'] == cid for x in lista)
        det = vendedor.get(f'/api/cotizaciones/eliminadas/{cid}')
        assert det.status_code == 200 and det.json['data']['motivo'] == 'Cliente desistió'

    def test_listado_y_pdf(self, vendedor):
        assert vendedor.get('/ventas/api/cotizaciones/listar').json['success']
        cid = nueva_cotizacion(vendedor).json['data']['id']
        r = vendedor.get(f'/ventas/api/cotizaciones/{cid}/completa')
        assert r.status_code == 200


# ============================================================
# PEDIDO DEL CLIENTE (PV)
# ============================================================
class TestPedidoCliente:
    def test_pc_requiere_cotizacion_validada(self, vendedor, aprobador):
        cid = nueva_cotizacion(vendedor).json['data']['id']
        r = vendedor.post('/ventas/api/pedido-compra/guardar', json={'cotizacion_id': cid, 'items': [], 'condicion_pago': 'Crédito 30 días'})
        assert r.status_code == 409
        aprobador.put(f'/ventas/api/cotizaciones/{cid}/toggle', json={'estado': 'Validado por Hellen'})
        aprobador.put(f'/ventas/api/cotizaciones/{cid}/toggle', json={'estado': 'Generada'})
        r1 = vendedor.post('/ventas/api/pedido-compra/guardar', json={'cotizacion_id': cid, 'items': [], 'monto': 253.7, 'condicion_pago': 'Crédito 30 días'})
        assert r1.status_code == 200, r1.json
        assert r1.json['advertencia'] is None
        r2 = vendedor.post('/ventas/api/pedido-compra/guardar', json={'cotizacion_id': cid, 'items': [], 'monto': 10, 'condicion_pago': 'Crédito 30 días'})
        assert r2.status_code == 200 and 'ya tiene' in r2.json['advertencia']
        n1, n2 = r1.json['data']['numero'], r2.json['data']['numero']
        assert n1 != n2 and n1.startswith('PV-')


# ============================================================
# FACTURACIÓN
# ============================================================
def factura(http, **extra):
    payload = {'tipo': 'FACTURA', 'serie': 'F001', 'cliente': 'CLIENTE INDUSTRIAL S.A.C.', 'ruc': '20100070970',
               'total': 118, 'subtotal': 100, 'igv': 18, 'condicion': 'Crédito 30 días', 'es_credito': True,
               'estado': 'Borrador', 'items': []}
    payload.update(extra)
    return http.post('/ventas/api/comprobantes/guardar', json=payload)


class TestFacturacion:
    def test_numeracion_correlativa_por_serie(self, vendedor):
        a = factura(vendedor).json['data']['numero']
        b = factura(vendedor).json['data']['numero']
        assert int(b) == int(a) + 1 and len(a) == 8
        otra = factura(vendedor, serie='F002').json['data']['numero']
        assert otra == '00000001'

    def test_numero_duplicado_rechazado(self, vendedor):
        factura(vendedor, numero='00000500')
        assert factura(vendedor, numero='00000500').status_code == 409

    def test_ruc_invalido_rechazado(self, vendedor):
        assert factura(vendedor, ruc='123').status_code == 400
        assert factura(vendedor, cliente='').status_code == 400
        assert factura(vendedor, total=0, subtotal=0, igv=0).status_code == 400

    def test_igv_inconsistente_se_corrige(self, vendedor):
        cid = factura(vendedor, total=236, subtotal=150, igv=10).json['data']['id']
        sub, igv, tot, pagar = sql("SELECT subtotal, igv, total, monto_a_pagar FROM comprobantes WHERE id = %s", (cid,))[0]
        assert float(sub) == 200.0 and float(igv) == 36.0 and float(tot) == 236.0
        assert float(pagar) == 236.0  # antes quedaba en 0 si no había retención

    def test_retencion_3_por_ciento(self, vendedor):
        cid = factura(vendedor, total=1180, subtotal=1000, igv=180, tiene_retencion=True).json['data']['id']
        ret, pagar = sql("SELECT monto_retenido, monto_a_pagar FROM comprobantes WHERE id = %s", (cid,))[0]
        assert float(ret) == 35.4 and float(pagar) == 1144.6

    def test_no_editar_emitido_y_transiciones(self, vendedor):
        cid = factura(vendedor).json['data']['id']
        assert vendedor.put(f'/ventas/api/comprobantes/{cid}/toggle', json={'estado': 'Pagado'}).status_code == 409
        assert vendedor.put(f'/ventas/api/comprobantes/{cid}/toggle', json={'estado': 'Emitido'}).status_code == 200
        assert factura(vendedor, id=cid, total=500).status_code == 409
        assert vendedor.put(f'/ventas/api/comprobantes/{cid}/toggle', json={'estado': 'Anulado'}).status_code == 200
        assert vendedor.put(f'/ventas/api/comprobantes/{cid}/toggle', json={'estado': 'Emitido'}).status_code == 409

    def test_nota_credito_camino_antiguo_cerrado(self, vendedor):
        # 26/10/2026: el camino antiguo dejaba escribir cualquier monto; ahora solo Hellen por /ventas/api/nc (ver test_zz_zz_26oct_nota_credito)
        r = factura(vendedor).json['data']
        base = {'comprobante_asociado': f"{r['serie']}-{r['numero']}", 'motivo': 'Devolución', 'cliente_nombre': 'X'}
        assert vendedor.post('/ventas/api/notas-credito/guardar', json={**base, 'monto': 18}).status_code == 403


class TestGuias:
    def test_editar_no_duplica_y_anular_conserva_datos(self, vendedor):
        # Traslado (no venta): la regla "sin stock no hay guía de venta" (20/10/2026) no aplica aquí
        payload = {'serie': 'T001', 'destinatario_nombre': 'CLIENTE', 'ruc_destinatario': '20100070970',
                   'items': [{'codigo': 'PRD-0001', 'cantidad': 2}], 'estado': 'Borrador', 'motivo_traslado': '04'}
        r = vendedor.post('/ventas/api/guias/guardar', json=payload)
        assert r.status_code == 200, r.json
        gid, numero = r.json['data']['id'], r.json['data']['numero']
        total_antes = sql("SELECT COUNT(*) FROM guias_remision")[0][0]
        r2 = vendedor.post('/ventas/api/guias/guardar', json={**payload, 'id': gid, 'destinatario_nombre': 'CLIENTE EDITADO'})
        assert r2.status_code == 200
        assert sql("SELECT COUNT(*) FROM guias_remision")[0][0] == total_antes
        assert vendedor.delete(f'/ventas/api/guias/{gid}').status_code == 200
        fila = sql("SELECT destinatario_nombre, estado_sunat, numero FROM guias_remision WHERE id = %s", (gid,))[0]
        assert fila == ('CLIENTE EDITADO', 'ANULADA', numero)
        assert vendedor.post('/ventas/api/guias/guardar', json={**payload, 'id': gid}).status_code == 409


# ============================================================
# COMPRAS
# ============================================================
class TestCompras:
    def test_orden_compra_completa(self, vendedor):
        payload = {'proveedor': 'PROVEEDOR ACEROS S.A.C.', 'ruc': '20600011111', 'estado': 'Borrador',
                   'condicion_pago': 'Crédito 30 días',
                   # compra sin pedido de cliente: el motivo es obligatorio (regla de Compras)
                   'motivo_compra': 'Stock estratégico',
                   'items': [{'producto': 'GUANTE DE NITRILO', 'cantidad': 100, 'precioUnitario': 8.5}]}
        r = vendedor.post('/compras/api/ordenes/guardar', json=payload)
        assert r.status_code == 200, r.json
        d = r.json['data']
        assert d['proveedor_id'] == 1 and d['total'] == 1003.0 and d['numero_orden'].startswith('OC-')
        precio = sql("SELECT precio_unitario FROM ordenes_compra_items WHERE orden_compra_id = %s", (d['id'],))[0][0]
        assert float(precio) == 8.5
        # editar por id no crea otra orden y reemplaza items
        r2 = vendedor.post('/compras/api/ordenes/guardar', json={**payload, 'id': d['id'],
                                                                  'items': [{'producto': 'CASCO', 'cantidad': 2, 'precioUnitario': 50}]})
        assert r2.status_code == 200 and r2.json['data']['numero_orden'] == d['numero_orden']
        assert sql("SELECT COUNT(*) FROM ordenes_compra")[0][0] == 1
        assert sql("SELECT COUNT(*) FROM ordenes_compra_items WHERE orden_compra_id = %s", (d['id'],))[0][0] == 1
        lista = vendedor.get('/compras/api/ordenes/listar').json['data']
        assert lista[0]['ruc'] == '20600011111' and lista[0]['items'][0]['precioUnitario'] == 50.0
        assert vendedor.post('/compras/api/ordenes/guardar', json={**payload, 'items': []}).status_code == 400

    def test_comprobante_proveedor_sin_duplicados(self, vendedor):
        p = {'tipo': 'Factura', 'numero': 'F001-123', 'monto': 1003, 'ruc': '20600011111',
             'proveedor': 'PROVEEDOR ACEROS S.A.C.', 'fecha': '2026-10-01'}
        assert vendedor.post('/compras/api/comprobantes-proveedor/guardar', json=p).status_code == 200
        assert vendedor.post('/compras/api/comprobantes-proveedor/guardar', json=p).status_code == 409
        assert vendedor.post('/compras/api/comprobantes-proveedor/guardar', json={**p, 'numero': 'X', 'monto': 0}).status_code == 400


# ============================================================
# FINANZAS
# ============================================================
class TestFinanzas:
    def test_cobros_parciales_y_anulacion(self, vendedor, admin):
        r = factura(vendedor, total=590, subtotal=500, igv=90).json['data']
        cid = r['id']
        cxc = admin.get('/finanzas/api/cxc').json['data']
        assert not any(x['id'] == cid for x in cxc)  # borrador no es cuenta por cobrar
        vendedor.put(f'/ventas/api/comprobantes/{cid}/toggle', json={'estado': 'Emitido'})
        doc = next(x for x in admin.get('/finanzas/api/cxc').json['data'] if x['id'] == cid)
        assert doc['saldo'] == 590.0
        # el vendedor no tiene rol de finanzas
        assert vendedor.post('/finanzas/api/movimientos', json={'tipo': 'COBRO', 'documento_id': cid, 'monto': 10}).status_code == 403
        mov = {'tipo': 'COBRO', 'documento_id': cid, 'metodo': 'Transferencia', 'banco': 'BCP', 'numero_operacion': '0001'}
        assert admin.post('/finanzas/api/movimientos', json={**mov, 'monto': 600}).status_code == 400
        r1 = admin.post('/finanzas/api/movimientos', json={**mov, 'monto': 290})
        assert r1.status_code == 200 and r1.json['data']['saldo'] == 300.0
        r2 = admin.post('/finanzas/api/movimientos', json={**mov, 'monto': 300})
        assert r2.json['data']['saldo'] == 0.0
        assert sql("SELECT estado_sunat FROM comprobantes WHERE id = %s", (cid,))[0][0] == 'Pagado'
        assert admin.post('/finanzas/api/movimientos', json={**mov, 'monto': 1}).status_code == 409
        assert admin.post(f"/finanzas/api/movimientos/{r2.json['data']['id']}/anular", json={}).status_code == 400
        assert admin.post(f"/finanzas/api/movimientos/{r2.json['data']['id']}/anular", json={'motivo': 'Error'}).status_code == 200
        assert sql("SELECT estado_sunat FROM comprobantes WHERE id = %s", (cid,))[0][0] == 'Emitido'
        doc = next(x for x in admin.get('/finanzas/api/cxc?estado=todos').json['data'] if x['id'] == cid)
        assert doc['saldo'] == 300.0

    def test_cuentas_por_pagar_y_flujo(self, admin):
        cxp = admin.get('/finanzas/api/cxp').json['data']
        assert cxp and cxp[0]['saldo'] == 1003.0
        # 21/10/2026: el vencimiento debe ser razonable (no antes de la emisión ni más de 400 días después)
        emision = date.fromisoformat(str(cxp[0]['fecha_emision'])[:10])
        assert admin.put(f"/finanzas/api/cxp/{cxp[0]['id']}/vencimiento", json={'fecha_vencimiento': '2030-01-31'}).status_code == 400
        assert admin.put(f"/finanzas/api/cxp/{cxp[0]['id']}/vencimiento",
                         json={'fecha_vencimiento': (emision + timedelta(days=60)).isoformat()}).status_code == 200
        r = admin.post('/finanzas/api/movimientos', json={'tipo': 'PAGO', 'documento_id': cxp[0]['id'], 'monto': 1003})
        assert r.status_code == 200
        assert sql("SELECT estado FROM comprobantes_proveedor WHERE id = %s", (cxp[0]['id'],))[0][0] == 'Pagado'
        flujo = admin.get('/finanzas/api/flujo?semanas=4').json['data']
        assert len(flujo) == 6 and 'acumulado' in flujo[-1]
        res = admin.get('/finanzas/api/resumen').json['data']
        assert res['pagado_mes'] >= 1003.0

    def test_pagina_finanzas(self, admin):
        r = admin.get('/finanzas')
        assert r.status_code == 200 and b'finanzas.js' in r.data
