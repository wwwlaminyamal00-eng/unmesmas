// static/js/compras_flujo.js - Compras bajo pedido, multiempresa y multisede (Vanilla JS)
(function () {
    'use strict';

    const app = document.getElementById('comApp');
    if (!app) return;
    const PUEDE = {
        comprar: app.dataset.comprar === 'true', aprobar: app.dataset.aprobar === 'true',
        pagar: app.dataset.pagar === 'true', recibir: app.dataset.recibir === 'true',
        facturar: app.dataset.facturar === 'true', admin: app.dataset.admin === 'true'
    };
    const cat = { empresas: [], sedes: [], proveedores: [], usuarios: [], registro: [], empresaDefecto: null, usuarioId: null, metodos: [] };
    let tabActual = 'hoy';
    let pedidosCache = [];
    let ordenesCache = [];
    let lineas = [];           // líneas del formulario de OC
    let provElegido = null;    // proveedor elegido en el formulario
    let detalleActual = null;
    const extrasStock = {};    // "Comprar para stock" que escribe el usuario en la tabla de pedidos (clave pedido_item)

    // ---------- utilidades ----------
    const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const soles = n => 'S/ ' + Number(n || 0).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const cant = n => Number(n || 0).toLocaleString('es-PE', { maximumFractionDigits: 2 });
    // Fechas del servidor: "2026-10-16" o "2026-10-16T14:47:48" (hora de Lima) -> DD/MM/YYYY [HH:MM]
    const fecha = (v, conHora = true) => {
        if (!v) return '—';
        if (window.fechaHoraLima) return window.fechaHoraLima(v, conHora);
        const m = String(v).match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/);
        if (!m) return String(v);
        return `${m[3]}/${m[2]}/${m[1]}` + (m[4] && conHora ? ` ${m[4]}:${m[5]}` : '');
    };
    const hoyISO = (masDias = 0) => {
        const d = new Date(Date.now() - new Date().getTimezoneOffset() * 60000 + masDias * 86400000);
        return d.toISOString().slice(0, 10);
    };
    const $ = id => document.getElementById(id);
    const IGV = 0.18;
    const claseEstado = e => 'est est-' + String(e || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/\s+/g, '-');

    function aviso(msg, tipo) {
        let caja = document.getElementById('comAviso');
        if (!caja) {
            caja = document.createElement('div');
            caja.id = 'comAviso';
            document.body.appendChild(caja);
        }
        const icono = { success: '✔', error: '✖', warning: '⏳' }[tipo] || 'ℹ';
        caja.className = 'inv-aviso-flot ' + (tipo || 'info');
        caja.innerHTML = `<b>${icono}</b><span>${esc(msg)}</span><button type="button" aria-label="Cerrar">✕</button>`;
        caja.querySelector('button').onclick = () => caja.classList.remove('show');
        requestAnimationFrame(() => caja.classList.add('show'));
        clearTimeout(caja._t);
        caja._t = setTimeout(() => caja.classList.remove('show'), tipo === 'error' ? 10000 : 6000);
    }

    async function api(url, opciones = {}) {
        const resp = await fetch(url, {
            ...opciones,
            headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest', ...(opciones.headers || {}) }
        });
        const json = await resp.json().catch(() => ({}));
        if (resp.status === 401) { window.location.href = '/login'; throw new Error('Sesión expirada'); }
        if (!resp.ok || json.success === false) throw new Error(json.error || `Error ${resp.status}`);
        return json;
    }
    const post = (url, body) => api(url, { method: 'POST', body: JSON.stringify(body || {}) });

    const abrir = id => $(id).classList.add('show');
    const cerrar = id => $(id).classList.remove('show');
    document.addEventListener('click', e => {
        const c = e.target.closest('[data-close]');
        if (c) cerrar(c.dataset.close);
    });

    async function guardarCon(btn, fn) {
        if (btn) { btn.disabled = true; btn.dataset.txt = btn.textContent; btn.textContent = 'Guardando...'; }
        try { await fn(); } catch (e) { aviso(e.message, 'error'); }
        finally { if (btn) { btn.disabled = false; btn.textContent = btn.dataset.txt; } }
    }

    function pedirMotivo(titulo, ayuda, alConfirmar) {
        $('motivoTituloCom').textContent = titulo;
        $('motivoAyudaCom').innerHTML = ayuda;
        $('motivoTextoCom').value = '';
        $('motivoOkCom').onclick = () => guardarCon($('motivoOkCom'), async () => {
            await alConfirmar($('motivoTextoCom').value.trim());
            cerrar('motivoModalCom');
        });
        abrir('motivoModalCom');
        setTimeout(() => $('motivoTextoCom').focus(), 50);
    }

    // ---------- catálogos ----------
    async function cargarCatalogos() {
        const r = await api('/compras/api/flujo/catalogos');
        Object.assign(cat, { empresas: r.empresas, sedes: r.sedes, proveedores: r.proveedores, usuarios: r.usuarios,
            registro: r.registro_sunat, empresaDefecto: r.empresa_defecto, usuarioId: r.usuario_id, metodos: r.metodos,
            motivos: r.motivos_sin_pedido || [] });
        document.querySelectorAll('select[data-empresas]').forEach(s => {
            s.innerHTML = (s.dataset.todas ? `<option value="">${esc(s.dataset.todas)}</option>` : '')
                + cat.empresas.map(e => `<option value="${e.id}">${esc(e.nombre)} · ${esc(e.razon_social || '')}</option>`).join('');
        });
        document.querySelectorAll('select[data-sedes]').forEach(s => {
            s.innerHTML = cat.sedes.map(x => `<option value="${x.id}">${esc(x.nombre)}</option>`).join('');
        });
        $('ocEmpresa').querySelectorAll('option').forEach(o => { if (o.value) o.textContent = o.textContent.split(' · ')[0]; });
        $('pagoMetodo').innerHTML = cat.metodos.map(m => `<option>${esc(m)}</option>`).join('');
        $('recUsuario').innerHTML = '<option value="">Elige a la persona...</option>'
            + cat.usuarios.filter(u => u.id !== cat.usuarioId).map(u => `<option value="${u.id}">${esc(u.nombre)}</option>`).join('');
        if (!PUEDE.comprar) $('btnNuevaOC').style.display = 'none';
    }

    // ========================================================
    // HOY EN COMPRAS
    // ========================================================
    async function cargarHoy() {
        try {
            const r = await api('/compras/api/flujo/resumen');
            $('kpiPedidos').textContent = r.kpis.pedidos;
            $('kpiAprobar').textContent = r.kpis.por_aprobar;
            $('kpiPagar').textContent = soles(r.kpis.por_pagar);
            $('kpiRecibir').textContent = r.kpis.por_recibir;
            $('kpiInc').textContent = r.kpis.incidencias;
            $('hoyAlertas').innerHTML = r.alertas.map(a => `<div class="inv-alerta ${a.nivel}">
                <div>${a.texto}</div>${a.ir ? `<button class="btn-mini sec" data-ir="${a.ir}">Ver ➜</button>` : ''}</div>`).join('');
        } catch (e) { $('hoyAlertas').innerHTML = `<div class="inv-alerta danger">${esc(e.message)}</div>`; }
    }

    // ========================================================
    // PEDIDOS POR COMPRAR
    // ========================================================
    async function cargarPedidos() {
        try {
            const { data } = await api('/compras/api/flujo/pedidos' + ($('pedTodos').checked ? '?todos=1' : ''));
            pedidosCache = data;
            pintarPedidos();
        } catch (e) { $('pedLista').innerHTML = `<div class="inv-vacio">${esc(e.message)}</div>`; }
    }

    function pintarPedidos() {
        const q = $('pedBuscar').value.trim().toLowerCase();
        const lista = pedidosCache.filter(p => !q || [p.numero, p.cliente, p.ruc, ...p.items.map(i => i.descripcion + ' ' + i.codigo)]
            .join(' ').toLowerCase().includes(q));
        $('pedLista').innerHTML = lista.length ? lista.map(p => `
            <div class="com-pedido">
                <div class="com-pedido-head">
                    <div><b>${esc(p.numero)}</b> · ${esc(p.cliente || 'Sin cliente')} <small>${esc(p.ruc || '')}</small></div>
                    <div class="com-pedido-meta">${fecha(p.fecha)} · <span class="${claseEstado(p.estado)}">${esc(p.estado || 'Pendiente')}</span>
                        ${p.lugar_entrega ? ` · Entrega: ${esc(p.lugar_entrega)}` : ''}</div>
                </div>
                <div class="table-wrap"><table class="inv-table inv-mini com-resumen">
                    <thead><tr><th></th><th class="left">Producto</th><th>Pedido del cliente</th><th>Ya en órdenes</th><th>En stock (empresa)</th>
                        <th>Comprar para pedido</th><th>Comprar para stock</th><th>Total a comprar</th><th>Saldo después de entregar</th></tr></thead>
                    <tbody>${p.items.map((it, i) => {
                        const sinProducto = !it.producto_id;
                        const marcable = PUEDE.comprar && it.falta > 0 && !sinProducto;
                        const r = calcResumen(p, i);
                        const clave = `${p.id}_${i}`;
                        return `<tr class="${it.falta <= 0 ? 'com-ok' : ''}" data-res="${clave}">
                            <td>${marcable ? `<input type="checkbox" class="ped-check" data-ped="${p.id}" data-i="${i}">` : (it.falta <= 0 ? '✔' : '')}</td>
                            <td class="left"><b>${esc(it.codigo)}</b> ${esc(it.descripcion)}${sinProducto ? '<small class="neg">Este producto no está en el catálogo: créalo en Productos para poder comprarlo.</small>' : ''}
                                ${it.stock_libre > r.stock && it.falta > 0 ? `<small class="com-stock-si" title="Stock sin separar en otras empresas/sedes del grupo">Hay ${cant(it.stock_libre)} libres en el grupo</small>` : ''}</td>
                            <td class="num">${cant(it.cantidad)} ${esc(it.unidad || '')}</td>
                            <td class="num">${cant(it.comprado)}</td>
                            <td class="num">${r.stock > 0 ? `<span class="com-stock-si">${cant(r.stock)}</span>` : '<span class="com-stock-no">0</span>'}</td>
                            <td class="num"><b>${cant(r.pedido)}</b></td>
                            <td>${marcable ? `<input type="number" class="inp-num ped-extra" min="0" step="any" value="${r.extra}" data-ped="${p.id}" data-i="${i}" title="0 por defecto: comprar de más es una decisión y pide motivo">` : ''}</td>
                            <td class="num"><b data-res-total>${cant(r.total)}</b></td>
                            <td class="num"><span data-res-saldo class="${r.saldo > 0 ? 'com-saldo' : ''}">${cant(r.saldo)}</span></td></tr>`;
                    }).join('')}</tbody>
                </table></div>
            </div>`).join('') : '<div class="inv-vacio">No hay pedidos de clientes pendientes de compra. 👍</div>';
        contarMarcados();
    }

    // Pedido 40, stock 10 -> comprar para pedido 30; + 100 para stock -> total 130, saldo después de entregar 100
    function calcResumen(p, i) {
        const it = p.items[i];
        const falta = Math.max(Number(it.falta) || 0, 0);
        const stock = Math.max(Number(it.stock_empresa) || 0, 0);
        const pedido = it.comprar_pedido !== undefined && it.comprar_pedido !== null ? Number(it.comprar_pedido) : Math.max(falta - stock, 0);
        const extra = Math.max(Number(extrasStock[`${p.id}_${i}`]) || 0, 0);
        const total = pedido + extra;
        return { stock, pedido, extra, total, saldo: Math.max(stock + total - falta, 0) };
    }

    function actualizarResumen(input) {
        const p = pedidosCache.find(x => String(x.id) === input.dataset.ped);
        if (!p) return;
        const i = Number(input.dataset.i);
        extrasStock[`${p.id}_${i}`] = Math.max(Number(input.value) || 0, 0);
        const r = calcResumen(p, i);
        const tr = input.closest('tr');
        tr.querySelector('[data-res-total]').textContent = cant(r.total);
        const s = tr.querySelector('[data-res-saldo]');
        s.textContent = cant(r.saldo);
        s.classList.toggle('com-saldo', r.saldo > 0);
        const chk = tr.querySelector('.ped-check');
        if (chk && r.extra > 0 && !chk.checked) { chk.checked = true; contarMarcados(); }
    }

    function contarMarcados() {
        const n = document.querySelectorAll('.ped-check:checked').length;
        $('pedMarcados').textContent = n;
        $('btnCrearDesdePedidos').disabled = n === 0;
    }

    function crearDesdePedidos() {
        const elegidos = [...document.querySelectorAll('.ped-check:checked')].map(c => {
            const p = pedidosCache.find(x => String(x.id) === c.dataset.ped);
            const i = Number(c.dataset.i);
            const it = p.items[i];
            const r = calcResumen(p, i);
            const texto = `${it.codigo} · ${it.descripcion}`;
            const out = [];
            if (r.pedido > 0) out.push({ producto_id: it.producto_id, texto, cantidad: r.pedido, precio_unitario: '',
                pedido_id: p.id, para: `${p.numero} · ${p.cliente || ''}`, max: it.falta });
            if (r.extra > 0) out.push({ producto_id: it.producto_id, texto, cantidad: r.extra, precio_unitario: '', pedido_id: null, para: '' });
            return out;
        }).flat();
        if (!elegidos.length) {
            aviso('Lo marcado ya está cubierto con el stock de la empresa. Si igual quieres comprar, escribe la cantidad en "Comprar para stock".', 'warning');
            return;
        }
        abrirNuevaOC(elegidos);
    }

    // ========================================================
    // ÓRDENES DE COMPRA (lista)
    // ========================================================
    function pasoHtml(o) {
        const c = o.paso.codigo;
        const color = { aprobar: 'warn', pagar: 'warn', pagar_credito: 'warn', recibir: 'info', incidencia: 'danger',
                        factura: 'warn', enviar: 'gris', listo: 'ok', anulada: 'gris', antigua: 'gris' }[c] || 'info';
        return `<span class="com-paso com-paso-${color}">${esc(o.paso.texto)}</span><small>${esc(o.paso.quien)}</small>`;
    }

    function paraHtml(o) {
        const motivo = o.motivo_compra ? `<small class="com-motivo">Motivo: ${esc(o.motivo_compra)}${o.motivo_stock && o.motivo_stock !== o.motivo_compra ? ' · ' + esc(o.motivo_stock) : ''}</small>` : '';
        if (o.sin_pedido || (o.tipo_compra === 'Para stock' && !o.clientes)) return `<span class="badge-sin-pedido">SIN PEDIDO</span>${motivo}`;
        const cot = o.cotizaciones || o.cotizaciones_cliente;
        return `${esc(o.clientes || o.clientes_pedido || '')}<small>${esc(o.pedidos || o.pc_numeros || '')}${cot ? ' · Cot. ' + esc(cot) : ''}${o.tipo_compra === 'Para stock' ? ' + stock' : ''}</small>${o.tipo_compra === 'Para stock' ? motivo : ''}`;
    }

    async function cargarOrdenes() {
        try {
            const params = new URLSearchParams({ estado: $('ocPaso').value === 'anulada' || $('ocPaso').value === 'listo' ? '' : 'abiertas' });
            if ($('ocEmpresa').value) params.set('empresa_id', $('ocEmpresa').value);
            if ($('ocPaso').value) params.set('paso', $('ocPaso').value);
            if ($('ocBuscar').value.trim()) params.set('q', $('ocBuscar').value.trim());
            if ($('ocSinPedido') && $('ocSinPedido').checked) params.set('sin_pedido', '1');
            const { data } = await api('/compras/api/flujo/ordenes?' + params);
            ordenesCache = data;
            $('ocBody').innerHTML = data.length ? data.map(o => `<tr class="com-fila" data-ver="${o.id}">
                <td><b>${esc(o.numero)}</b>${o.atrasada ? '<small class="neg">ATRASADA</small>' : ''}</td>
                <td>${fecha(o.created_at || o.fecha)}</td>
                <td><b>${esc(o.empresa || '—')}</b></td>
                <td class="left">${esc(o.proveedor || '')}<small>${esc(o.ruc || '')}</small></td>
                <td class="left">${paraHtml(o)}</td>
                <td>${esc(o.sede || '—')}<small>${o.modalidad_entrega === 'Nosotros recogemos' ? '🚚 Recogemos' : 'Proveedor entrega'}</small></td>
                <td>${esc(o.condicion_pago || '')}</td>
                <td class="num">${soles(o.total)}${o.pagado > 0 ? `<small>Pagado ${soles(o.pagado)}</small>` : ''}</td>
                <td><div class="com-barra"><i style="width:${o.avance_recepcion}%"></i></div><small>${Math.round(o.avance_recepcion)}%</small></td>
                <td><span class="${claseEstado(o.estado)}">${esc(o.estado)}</span>${o.incidencias ? `<small class="neg">${o.incidencias} diferencia(s)</small>` : ''}</td>
                <td class="left">${pasoHtml(o)}</td>
                <td><button class="btn-mini sec" data-ver="${o.id}">Ver</button></td></tr>`).join('')
                : '<tr><td colspan="12">No hay órdenes con este filtro.</td></tr>';
            const total = data.filter(o => o.estado !== 'Anulada').reduce((s, o) => s + Number(o.total), 0);
            $('ocFoot').textContent = `${data.length} orden(es) · Total ${soles(total)}`;
        } catch (e) { $('ocBody').innerHTML = `<tr><td colspan="12">${esc(e.message)}</td></tr>`; }
    }

    // ========================================================
    // FORMULARIO DE ORDEN DE COMPRA
    // ========================================================
    function sedeDeclarada(empresaId, sedeId) {
        const r = cat.registro.find(x => String(x.empresa_id) === String(empresaId) && Number(x.almacen_id) === Number(sedeId));
        if (!r) return null;
        return !!(r.registrado_sunat || r.es_domicilio_fiscal);
    }

    function avisoSunat() {
        const ok = sedeDeclarada($('ocEmp').value, $('ocSede').value);
        const emp = (cat.empresas.find(e => String(e.id) === String($('ocEmp').value)) || {}).nombre || '';
        const sede = (cat.sedes.find(s => s.id === Number($('ocSede').value)) || {}).nombre || '';
        $('ocSunat').innerHTML = ok === false
            ? `<div class="inv-aviso">⚠️ ${esc(sede)} no está declarada en SUNAT como establecimiento de ${esc(emp)}. La guía del proveedor debe llegar a un local de la empresa que compra. Pide a contabilidad que la declare (Inventario ▸ Sedes y SUNAT) o elige otra sede.</div>`
            : '';
    }

    function abrirNuevaOC(precargadas = [], oc = null) {
        if (!PUEDE.comprar) { aviso('Tu usuario no puede preparar órdenes de compra.', 'error'); return; }
        $('ocId').value = oc ? oc.id : '';
        $('ocTitulo').textContent = oc ? `Corregir ${oc.numero}` : 'Nueva orden de compra';
        $('ocEmp').value = oc ? oc.empresa_id : (cat.empresaDefecto || '');
        provElegido = oc && oc.proveedor_id ? cat.proveedores.find(p => p.id === oc.proveedor_id) || null : null;
        $('ocProv').querySelector('.pp-input').value = provElegido ? `${provElegido.ruc || ''} · ${provElegido.razon_social}` : '';
        $('ocProv').classList.toggle('pp-ok', !!provElegido);
        const cond = oc ? (String(oc.condicion_pago || '').startsWith('Crédito') ? 'Crédito' : oc.condicion_pago) : 'Contado';
        $('ocCondicion').value = cond || 'Contado';
        $('ocDias').value = oc && oc.dias_credito ? oc.dias_credito : '';
        $('ocModalidad').value = oc ? (oc.modalidad_entrega || 'Proveedor entrega') : 'Proveedor entrega';
        $('ocRecojo').value = oc ? (oc.direccion_recojo || '') : '';
        const smp = cat.sedes[0];
        $('ocSede').value = oc ? oc.almacen_entrega_id : (smp ? smp.id : '');
        $('ocFecha').value = oc ? (oc.fecha_compromiso || '') : hoyISO(2);
        $('ocCotizacion').value = oc ? (oc.num_cotizacion || '') : '';
        $('ocNotas').value = oc ? (oc.notas || '') : '';
        $('ocMotivo').value = oc ? (oc.motivo_stock || '') : '';
        $('ocMotivoCompra').value = oc && oc.motivo_compra ? oc.motivo_compra : '';
        $('ocProv').querySelector('.pp-lista').style.display = 'none';
        lineas = oc ? oc.items.map(i => ({ producto_id: i.producto_id, texto: `${i.codigo || ''} · ${i.producto}`, cantidad: i.cantidad,
            precio_unitario: i.precio_unitario, pedido_id: i.pedido_id, para: i.pedido_id ? `${i.pedido_numero} · ${i.cliente || ''}` : '' }))
            : precargadas;
        if (!lineas.length) lineas.push(lineaVacia());
        ajustarForm();
        pintarLineas();
        pintarProveedor();
        abrir('ocModal');
    }

    const lineaVacia = () => ({ producto_id: null, texto: '', cantidad: '', precio_unitario: '', pedido_id: null, para: '' });

    function ajustarForm() {
        $('ocDiasWrap').style.display = $('ocCondicion').value === 'Crédito' ? '' : 'none';
        $('ocRecojoWrap').style.display = $('ocModalidad').value === 'Nosotros recogemos' ? '' : 'none';
        if ($('ocModalidad').value === 'Nosotros recogemos' && !$('ocRecojo').value && provElegido)
            $('ocRecojo').value = provElegido.lugar_recojo || provElegido.direccion || '';
        const conProducto = lineas.filter(l => l.producto_id);
        const sinPedido = conProducto.filter(l => !l.pedido_id);
        $('ocMotivoWrap').style.display = sinPedido.length ? '' : 'none';
        $('ocSinPedidoTxt').textContent = sinPedido.length && sinPedido.length === conProducto.length
            ? 'COMPRA SIN PEDIDO' : 'Compra para stock (además del pedido)';
        $('ocMotivoReq').textContent = $('ocMotivoCompra').value === 'Otro' ? '(obligatorio: escribe el motivo)' : '(opcional)';
        $('ocMotivoReq').classList.toggle('neg', $('ocMotivoCompra').value === 'Otro');
        avisoSunat();
        pedirAbastecimiento();
    }

    // ========================================================
    // RESUMEN DE ABASTECIMIENTO (pedido de Erika, 19/10/2026)
    // Por producto: stock actual de la empresa que compra · pedido del cliente que falta cubrir · a comprar
    // ========================================================
    let abastDatos = {}, abastClave = '', abastTimer = null;

    function pedirAbastecimiento() {
        clearTimeout(abastTimer);
        abastTimer = setTimeout(async () => {
            const ids = [...new Set(lineas.filter(l => l.producto_id).map(l => l.producto_id))].sort((a, b) => a - b);
            const clave = $('ocEmp').value + '|' + ids.join(',') + '|' + ($('ocId').value || '');
            if (clave !== abastClave) {
                abastClave = clave;
                if (!ids.length) { abastDatos = {}; }
                else {
                    try {
                        const params = new URLSearchParams({ empresa_id: $('ocEmp').value, productos: ids.join(',') });
                        if ($('ocId').value) params.set('oc_id', $('ocId').value);
                        const { data } = await api('/compras/api/flujo/abastecimiento?' + params);
                        if (clave !== abastClave) return;   // llegó tarde: ya se pidió otra cosa
                        abastDatos = Object.fromEntries(data.map(d => [d.producto_id, d]));
                    } catch (e) { abastDatos = {}; }
                }
            }
            pintarAbastecimiento();
        }, 150);
    }

    function pintarAbastecimiento() {
        const caja = $('ocAbast');
        if (!caja) return;
        const ids = [...new Set(lineas.filter(l => l.producto_id).map(l => l.producto_id))];
        const emp = (cat.empresas.find(e => String(e.id) === String($('ocEmp').value)) || {});
        if (!ids.length) {
            caja.innerHTML = `<div class="com-abast-tit">📊 Resumen de abastecimiento</div><div class="com-abast-vacio">Elige un producto y aquí verás el stock, lo que pide el cliente y cuánto comprar.</div>`;
            return;
        }
        const filas = ids.map(pid => {
            const d = abastDatos[pid];
            const comprar = lineas.filter(l => l.producto_id === pid).reduce((s, l) => s + (Number(l.cantidad) || 0), 0);
            if (!d) return `<tr><td class="left">${esc((lineas.find(l => l.producto_id === pid) || {}).texto || '')}</td><td colspan="5">Calculando...</td></tr>`;
            const saldo = d.stock + comprar - d.pedido_cliente;
            const usar = d.sugerido > 0 && Math.abs(comprar - d.sugerido) > 1e-9
                ? `<button type="button" class="btn-mini sec" data-sugerido="${pid}" title="Poner esta cantidad en la línea del producto">Usar</button>` : '';
            const estado = saldo < 0
                ? `<span class="com-abast-sem rojo">✖ Faltan ${cant(-saldo)}</span>`
                : (d.pedido_cliente > 0
                    ? `<span class="com-abast-sem verde">✔ Cubre el pedido${saldo > 0 ? ` · quedan ${cant(saldo)} en stock` : ''}</span>`
                    : `<span class="com-abast-sem ambar">Para stock · quedarán ${cant(saldo)}</span>`);
            const pcs = d.pedidos.map(p => `${p.numero} (${cant(p.falta)})`).join(', ');
            return `<tr>
                <td class="left"><b>${esc(d.codigo || '')}</b> ${esc(d.descripcion || '')}</td>
                <td class="num"><span class="com-abast-num ${d.stock > 0 ? 'hay' : 'cero'}">${cant(d.stock)}</span>
                    ${d.stock_grupo > d.stock ? `<small title="Stock libre en todo el grupo (otras empresas o sedes)">Grupo: ${cant(d.stock_grupo)}</small>` : ''}</td>
                <td class="num"><span class="com-abast-num ped">${cant(d.pedido_cliente)}</span>
                    ${pcs ? `<small title="${esc(pcs)}">${d.pedidos.length} pedido(s)${d.ya_en_ordenes > 0 ? ` · ya hay ${cant(d.ya_en_ordenes)} en otras OC` : ''}</small>` : '<small>Sin pedidos pendientes</small>'}</td>
                <td class="num"><span class="com-abast-num sug">${cant(d.sugerido)}</span>${usar}</td>
                <td class="num"><span class="com-abast-num comp">${cant(comprar)}</span></td>
                <td>${estado}</td></tr>`;
        }).join('');
        caja.innerHTML = `<div class="com-abast-tit">📊 Resumen de abastecimiento <small>${esc(emp.nombre || 'Empresa')} · se recalcula solo</small></div>
            <div class="table-wrap"><table class="inv-table com-abast-tabla">
                <thead><tr><th class="left">Producto</th><th>Stock actual<small>disponible en ${esc(emp.codigo || emp.nombre || 'la empresa')}</small></th>
                    <th>Pedido del cliente<small>lo que falta cubrir</small></th><th>Sugerido<small>pedido − stock</small></th>
                    <th>A comprar<small>en esta orden</small></th><th class="left">Resultado</th></tr></thead>
                <tbody>${filas}</tbody></table></div>`;
    }

    function usarSugerido(pid) {
        const d = abastDatos[pid];
        if (!d) return;
        const idx = lineas.map((l, i) => [l, i]).filter(([l]) => l.producto_id === pid);
        if (!idx.length) return;
        // La cantidad sugerida va a la línea del pedido (o a la primera); las demás líneas del mismo producto se respetan
        const [, i] = idx.find(([l]) => l.pedido_id) || idx[0];
        const otras = idx.filter(([, j]) => j !== i).reduce((s, [l]) => s + (Number(l.cantidad) || 0), 0);
        lineas[i].cantidad = Math.max(d.sugerido - otras, 0);
        const inp = document.querySelector(`tr[data-linea="${i}"] [data-campo="cantidad"]`);
        if (inp) inp.value = lineas[i].cantidad;
        $('tot-' + i).textContent = soles((Number(lineas[i].cantidad) || 0) * (Number(lineas[i].precio_unitario) || 0));
        totales();
        pintarAbastecimiento();
    }

    function pintarProveedor() {
        const p = provElegido;
        // Datos del proveedor (proveedores + contacto principal de proveedores_contactos), solo lectura
        const campos = { ocProvRazon: 'razon_social', ocProvRuc: 'ruc', ocProvDireccion: 'direccion', ocProvContacto: 'contacto',
                         ocProvTelefono: 'telefono', ocProvEmail: 'email' };
        Object.entries(campos).forEach(([id, k]) => { if ($(id)) $(id).value = p ? (p[k] || '') : ''; });
        if (!p) { $('ocProvInfo').innerHTML = ''; return; }
        const cuenta = p.numero_cuenta || p.cci;
        $('ocProvInfo').innerHTML = `<div class="com-prov-card">
            <b>${esc(p.razon_social)}</b> · RUC ${esc(p.ruc || '—')}<br>
            ${esc(p.direccion || '')}${p.contacto ? ' · ' + esc(p.contacto) : ''}${p.telefono ? ' · ' + esc(p.telefono) : ''}<br>
            ${cuenta ? `🏦 Cuenta registrada: ${esc(p.banco || '')} ${esc(p.numero_cuenta || '')} ${p.cci ? 'CCI ' + esc(p.cci) : ''}`
                     : '<span class="neg">⚠️ Este proveedor no tiene cuenta bancaria registrada. Pídela y regístrala en Maestros ▸ Proveedores antes de pagar.</span>'}
        </div>`;
    }

    function crearPickerProveedor() {
        const el = $('ocProv');
        const input = el.querySelector('.pp-input');
        const lista = el.querySelector('.pp-lista');
        input.addEventListener('input', () => {
            provElegido = null;
            el.classList.remove('pp-ok');
            pintarProveedor();
            const q = input.value.trim().toLowerCase();
            if (q.length < 2) { lista.style.display = 'none'; return; }
            const res = cat.proveedores.filter(p => [p.ruc, p.razon_social, p.razon_comercial].join(' ').toLowerCase().includes(q)).slice(0, 20);
            lista.innerHTML = res.length ? res.map(p => `<div class="pp-op" data-id="${p.id}"><b>${esc(p.ruc || '')}</b> ${esc(p.razon_social)}</div>`).join('')
                : '<div class="pp-nada">No está registrado. Créalo en Maestros ▸ Proveedores.</div>';
            lista.style.display = 'block';
        });
        lista.addEventListener('click', e => {
            const op = e.target.closest('.pp-op');
            if (!op) return;
            provElegido = cat.proveedores.find(p => p.id === Number(op.dataset.id));
            input.value = `${provElegido.ruc || ''} · ${provElegido.razon_social}`;
            el.classList.add('pp-ok');
            lista.style.display = 'none';
            const cp = String(provElegido.condicion_pago || '').toLowerCase();
            if (cp.includes('crédito') || cp.includes('credito')) {
                $('ocCondicion').value = 'Crédito';
                const dias = parseInt(String(provElegido.tiempo_credito || '').replace(/\D/g, ''), 10);
                if (dias) $('ocDias').value = dias;
            }
            pintarProveedor();
            ajustarForm();
        });
        document.addEventListener('click', e => { if (!el.contains(e.target)) lista.style.display = 'none'; });
    }

    function pintarLineas() {
        $('ocLineas').innerHTML = lineas.map((l, i) => `<tr data-linea="${i}">
            <td class="left">${l.pedido_id
                ? `<b>${esc(l.texto)}</b>`
                : `<div class="prod-picker com-pp" data-linea-pp="${i}"><input type="search" class="pp-input" value="${esc(l.texto)}" placeholder="Buscar producto..." autocomplete="off"><div class="pp-lista"></div></div>`}
                <div class="com-info-linea" id="info-${i}"></div></td>
            <td class="left">${l.pedido_id ? `<span class="com-para">${esc(l.para)}</span>` : '<span class="badge-sin-pedido">Para stock · sin pedido</span>'}</td>
            <td><input type="number" class="inp-num" data-campo="cantidad" min="0" step="any" value="${esc(l.cantidad)}">${l.max ? `<small>máx. ${cant(l.max)}</small>` : ''}</td>
            <td><input type="number" class="inp-num" data-campo="precio_unitario" min="0" step="0.0001" value="${esc(l.precio_unitario)}"></td>
            <td class="num" id="tot-${i}">${soles((Number(l.cantidad) || 0) * (Number(l.precio_unitario) || 0))}</td>
            <td><button class="btn-mini btn-tachito" data-quitar="${i}" title="Quitar" aria-label="Quitar">🗑️</button></td></tr>`).join('');
        lineas.forEach((l, i) => {
            const el = document.querySelector(`[data-linea-pp="${i}"]`);
            if (el) pickerLinea(el, i);
            if (l.producto_id) infoProducto(i);
        });
        if (lineas.some(l => l.producto_id && l.pedido_id === null && l.texto)) ajustarForm();
        totales();
        pedirAbastecimiento();
    }

    function pickerLinea(el, i) {
        const input = el.querySelector('.pp-input');
        const lista = el.querySelector('.pp-lista');
        if (lineas[i].producto_id) el.classList.add('pp-ok');
        let t;
        input.addEventListener('input', () => {
            lineas[i].producto_id = null;
            el.classList.remove('pp-ok');
            clearTimeout(t);
            t = setTimeout(async () => {
                const q = input.value.trim();
                if (q.length < 2) { lista.style.display = 'none'; return; }
                try {
                    const { data } = await api('/inventario/api/productos?q=' + encodeURIComponent(q));
                    lista.innerHTML = data.length ? data.map(x => `<div class="pp-op" data-id="${x.id}" data-txt="${esc((x.codigo || '') + ' · ' + x.descripcion)}">
                        <b>${esc(x.codigo || '')}</b> ${esc(x.descripcion)} <small>${esc([x.marca, x.modelo, x.unidad].filter(Boolean).join(' · '))}</small></div>`).join('')
                        : '<div class="pp-nada">No se encontró. Créalo en Productos.</div>';
                    lista.style.display = 'block';
                } catch (e) { lista.style.display = 'none'; }
            }, 250);
        });
        lista.addEventListener('click', e => {
            const op = e.target.closest('.pp-op');
            if (!op) return;
            lineas[i].producto_id = Number(op.dataset.id);
            lineas[i].texto = op.dataset.txt;
            input.value = op.dataset.txt;
            el.classList.add('pp-ok');
            lista.style.display = 'none';
            infoProducto(i);
            ajustarForm();
        });
        document.addEventListener('click', e => { if (!el.contains(e.target)) lista.style.display = 'none'; });
    }

    async function infoProducto(i) {
        const l = lineas[i];
        const caja = $('info-' + i);
        if (!caja || !l.producto_id) return;
        try {
            const r = await api('/compras/api/flujo/producto/' + l.producto_id);
            const u = r.compras[0];
            const partes = [];
            if (u) {
                partes.push(`Última compra: <b>${soles(u.precio_unitario)}</b> a ${esc(u.proveedor || '—')} (${fecha(String(u.fecha).slice(0, 10))})`);
                l.ultimo = Number(u.precio_unitario);
            }
            if (r.stock_libre.length) partes.push(`<span class="com-stock-si">Stock libre: ${r.stock_libre.map(s => `${esc(s.empresa)}-${esc(s.sede)} ${cant(s.libre)}`).join(', ')}</span>`);
            caja.innerHTML = partes.join(' · ');
            revisarPrecio(i);
        } catch (e) { caja.innerHTML = ''; }
    }

    function revisarPrecio(i) {
        const l = lineas[i];
        const fila = document.querySelector(`tr[data-linea="${i}"]`);
        if (!fila) return;
        const caro = l.ultimo && Number(l.precio_unitario) > l.ultimo * 1.10;
        fila.classList.toggle('com-caro', !!caro);
        const caja = $('info-' + i);
        if (caja) {
            caja.querySelectorAll('.com-alerta-precio').forEach(x => x.remove());
            if (caro) caja.insertAdjacentHTML('beforeend', ` <span class="com-alerta-precio">⚠️ ${Math.round((Number(l.precio_unitario) / l.ultimo - 1) * 100)}% más caro que la última vez</span>`);
        }
    }

    function totales() {
        const sub = lineas.reduce((s, l) => s + (Number(l.cantidad) || 0) * (Number(l.precio_unitario) || 0), 0);
        const igv = Math.round(sub * IGV * 100) / 100;
        $('ocSub').textContent = soles(sub);
        $('ocIgv').textContent = soles(igv);
        $('ocTot').textContent = soles(Math.round(sub * 100) / 100 + igv);
    }

    async function guardarOC(enviar, btn) {
        if (!provElegido) { aviso('Elige el proveedor de la lista.', 'error'); return; }
        const items = lineas.filter(l => l.producto_id || l.texto).map(l => ({ producto_id: l.producto_id, cantidad: l.cantidad,
            precio_unitario: l.precio_unitario, pedido_id: l.pedido_id }));
        if (items.some(i => !i.producto_id)) { aviso('Hay un producto escrito a mano. Elígelo de la lista que aparece al escribir.', 'error'); return; }
        const body = {
            id: $('ocId').value || null, empresa_id: $('ocEmp').value, proveedor_id: provElegido.id,
            condicion_pago: $('ocCondicion').value, dias_credito: $('ocDias').value, modalidad_entrega: $('ocModalidad').value,
            direccion_recojo: $('ocRecojo').value, almacen_entrega_id: $('ocSede').value, fecha_compromiso: $('ocFecha').value,
            num_cotizacion: $('ocCotizacion').value, notas: $('ocNotas').value,
            motivo_compra: $('ocMotivoCompra').value, motivo_stock: $('ocMotivo').value.trim(), items, enviar
        };
        if (items.some(i => !i.pedido_id)) {
            if (!body.motivo_compra) { aviso('Hay productos SIN pedido de cliente: elige el motivo de la compra.', 'error'); $('ocMotivoCompra').focus(); return; }
            if (body.motivo_compra === 'Otro' && body.motivo_stock.length < 5) { aviso('Elegiste "Otro": escribe el motivo.', 'error'); $('ocMotivo').focus(); return; }
        }
        await guardarCon(btn, async () => {
            const r = await post('/compras/api/flujo/ordenes', body);
            aviso(r.message, r.alertas && r.alertas.length ? 'warning' : 'success');
            cerrar('ocModal');
            document.querySelectorAll('.ped-check:checked').forEach(c => { c.checked = false; });
            refrescar();
            verOrden(r.id);
        });
    }

    // ========================================================
    // DETALLE DE LA ORDEN
    // ========================================================
    const PASOS = [
        { k: 'creada', t: 'Orden hecha' }, { k: 'aprobada', t: 'Aprobada' }, { k: 'pagada', t: 'Pagada' },
        { k: 'recibida', t: 'Recibida' }, { k: 'facturada', t: 'Factura' }, { k: 'cerrada', t: 'Completa' }
    ];

    function estadoPasos(o) {
        const aprob = !['Borrador', 'Por aprobar', 'Anulada'].includes(o.estado) || (o.estado === 'Anulada' && o.aprobado_en);
        const contado = String(o.condicion_pago || '').startsWith('Contado');
        const pagada = Number(o.pagado) >= Number(o.total) - 0.01;
        return {
            creada: o.estado === 'Borrador' ? 'actual' : 'hecho',
            aprobada: aprob ? 'hecho' : (o.estado === 'Por aprobar' ? 'actual' : ''),
            pagada: pagada ? 'hecho' : (aprob && (contado || ['Recibida', 'Cerrada'].includes(o.estado)) ? 'actual' : (contado ? '' : 'luego')),
            recibida: ['Recibida', 'Cerrada'].includes(o.estado) ? 'hecho' : (o.estado === 'Recibida parcial' ? 'actual' : (aprob && (!contado || pagada) ? 'actual' : '')),
            facturada: o.facturas > 0 ? (o.cuadra === false ? 'error' : 'hecho') : (['Recibida', 'Recibida parcial'].includes(o.estado) ? 'actual' : ''),
            cerrada: o.estado === 'Cerrada' ? 'hecho' : ''
        };
    }

    async function verOrden(id) {
        try {
            const { data: o } = await api('/compras/api/flujo/ordenes/' + id);
            detalleActual = o;
            const ep = estadoPasos(o);
            $('detTitulo').innerHTML = `${esc(o.numero)} <span class="${claseEstado(o.estado)}">${esc(o.estado)}</span>`;
            const pd = o.proveedor_datos || {};
            $('detCuerpo').innerHTML = `
                ${o.flujo === 'v2' ? `<div class="com-stepper">${PASOS.map((p, i) => `<div class="com-step ${o.estado === 'Anulada' ? 'anulada' : ep[p.k]}"><span>${ep[p.k] === 'hecho' ? '✓' : i + 1}</span><b>${p.t}</b></div>`).join('')}</div>` : ''}
                <div class="com-siguiente com-paso-${o.paso.codigo}">👉 <b>Siguiente paso:</b> ${esc(o.paso.texto)} <small>(${esc(o.paso.quien)})</small></div>
                ${(o.avisos || []).map(a => `<div class="inv-aviso">⚠️ ${esc(a)}</div>`).join('')}
                ${o.motivo_anulacion ? `<div class="inv-alerta danger">Anulada: ${esc(o.motivo_anulacion)}</div>` : ''}
                ${o.motivo_compra ? `<div class="com-sin-pedido"><div class="com-sin-pedido-tit">⚠️ ${o.items.every(i => !i.pedido_id) ? 'COMPRA SIN PEDIDO' : 'Incluye compra para stock'} · Motivo: ${esc(o.motivo_compra)}${o.motivo_stock && o.motivo_stock !== o.motivo_compra ? ' · ' + esc(o.motivo_stock) : ''}</div></div>` : ''}
                ${o.pc_numeros || o.clientes_pedido ? `<div class="inv-tip com-interno">🔒 <b>Solo interno</b> (no sale en la orden del proveedor): corresponde a
                    <b>${esc(o.pc_numeros || '')}</b>${o.cotizaciones_cliente ? ` · Cotización ${esc(o.cotizaciones_cliente)}` : ''}${o.clientes_pedido ? ` · Cliente ${esc(o.clientes_pedido)}` : ''}</div>` : ''}
                <div class="com-datos">
                    <div><small>Empresa que compra</small><b>${esc(o.empresa || '—')}</b></div>
                    <div><small>Proveedor</small><b>${esc(o.proveedor || '')}</b><span>RUC ${esc(o.ruc || '—')}</span></div>
                    <div><small>Condición de pago</small><b>${esc(o.condicion_pago || '')}</b></div>
                    <div><small>Cómo llega</small><b>${esc(o.modalidad_entrega || '')}</b><span>${esc(o.direccion_recojo || '')}</span></div>
                    <div><small>Debe quedar en</small><b>${esc(o.sede || '—')}</b><span>Fecha prometida ${fecha(o.fecha_compromiso)}${o.atrasada ? ' · <b class="neg">ATRASADA</b>' : ''}</span></div>
                    <div><small>Tipo</small><b>${esc(o.tipo_compra || '')}</b><span>${esc(o.motivo_stock || '')}</span></div>
                    <div><small>Hizo la orden</small><b>${esc(o.creado_por_nombre || '—')}</b><span>${fecha(o.fecha)}</span></div>
                    <div><small>Aprobó</small><b>${esc(o.aprobado_por || '—')}</b><span>${fecha(o.aprobado_en)}</span></div>
                    <div><small>Total</small><b>${soles(o.total)}</b><span>Pagado ${soles(o.pagado)} · Facturado ${soles(o.facturado)}</span></div>
                </div>
                ${o.notas ? `<div class="inv-tip">📝 ${esc(o.notas)}</div>` : ''}
                <div class="inv-subtitulo">Productos</div>
                <div class="table-wrap"><table class="inv-table inv-mini">
                    <thead><tr><th>Código</th><th class="left">Producto</th><th class="left">Para</th><th>Pedido</th><th>Llegó</th><th>Precio sin IGV</th><th>Total</th></tr></thead>
                    <tbody>${o.items.map(i => `<tr class="${Number(i.cantidad_recibida) < Number(i.cantidad) && o.estado === 'Recibida parcial' ? 'fila-dif' : ''}">
                        <td>${esc(i.codigo || '')}</td><td class="left">${esc(i.producto)}</td>
                        <td class="left">${i.pedido_id ? `${esc(i.cliente || '')}<small>${esc(i.pedido_numero || '')}${i.cotizacion_numero ? ' · Cot. ' + esc(i.cotizacion_numero) : ''}</small>` : '<span class="badge-sin-pedido">Stock</span>'}</td>
                        <td class="num">${cant(i.cantidad)} ${esc(i.unidad || '')}</td><td class="num">${cant(i.cantidad_recibida)}</td>
                        <td class="num">${soles(i.precio_unitario)}</td><td class="num">${soles(i.total)}</td></tr>`).join('')}</tbody>
                    <tfoot><tr><td colspan="6" class="num">Subtotal ${soles(o.subtotal)} · IGV ${soles(o.igv)} · <b>Total</b></td><td class="num"><b>${soles(o.total)}</b></td></tr></tfoot>
                </table></div>
                ${o.incidencias.length ? `<div class="inv-subtitulo">Diferencias</div><div class="table-wrap"><table class="inv-table inv-mini">
                    <thead><tr><th>N°</th><th>Tipo</th><th class="left">Detalle</th><th>Monto</th><th>Estado</th><th class="left">Cómo se resolvió</th><th></th></tr></thead>
                    <tbody>${o.incidencias.map(i => `<tr><td>${esc(i.numero)}</td><td><b>${esc(i.tipo)}</b></td><td class="left">${esc(i.detalle)}<small>Reportó ${esc(i.reportado_por || '')} · ${fecha(i.fecha)}</small></td>
                        <td class="num">${i.monto ? soles(i.monto) : ''}</td><td><span class="${claseEstado(i.estado === 'Abierta' ? 'pendiente' : 'registrado')}">${esc(i.estado)}</span></td>
                        <td class="left">${esc(i.resolucion || '')}${i.resuelto_por ? `<small>${esc(i.resuelto_por)}</small>` : ''}</td>
                        <td>${i.estado === 'Abierta' && PUEDE.aprobar ? `<button class="btn-mini" data-resolver="${i.id}">Resolver</button>` : ''}</td></tr>`).join('')}</tbody></table></div>` : ''}
                <div class="com-columnas">
                    <div><div class="inv-subtitulo">Pagos</div>${o.pagos.length ? o.pagos.map(p => `<div class="com-mov">💸 <b>${soles(p.monto)}</b> · ${esc(p.metodo || '')} ${esc(p.banco || '')} · Op. ${esc(p.numero_operacion || '—')}<small>${fecha(p.fecha)} · ${esc(p.usuario_nombre || '')}</small></div>`).join('') : '<div class="inv-tip">Sin pagos.</div>'}
                        ${pd.numero_cuenta || pd.cci ? `<div class="inv-tip">🏦 Cuenta del proveedor: ${esc(pd.banco || '')} ${esc(pd.numero_cuenta || '')} ${pd.cci ? 'CCI ' + esc(pd.cci) : ''}</div>` : ''}</div>
                    <div><div class="inv-subtitulo">Recepciones</div>${o.recepciones.length ? o.recepciones.map(r => `<div class="com-mov">📦 <b>${esc(r.numero)}</b> · Guía ${esc(r.guia_proveedor)} · ${esc(r.sede || '')}${r.con_diferencias ? ' · <b class="neg">con diferencias</b>' : ''}<small>Trajo: ${esc(r.traido_por || '')} · Recibió: ${esc(r.recibido_por || '')} · ${fecha(r.fecha)}</small></div>`).join('') : '<div class="inv-tip">Todavía no llega nada.</div>'}</div>
                    <div><div class="inv-subtitulo">Facturas</div>${o.facturas.length ? o.facturas.map(f => `<div class="com-mov">🧾 <b>${esc(f.tipo)} ${esc(f.numero)}</b> · ${soles(f.monto)} ${f.cuadra === false ? '<b class="neg">no cuadra</b>' : '✔'}<small>${fecha(f.fecha)} · vence ${fecha(f.fecha_vencimiento)} · ${esc(f.estado || '')}</small></div>`).join('') : '<div class="inv-tip">Sin factura.</div>'}</div>
                </div>
                <div class="inv-subtitulo">Historial (no se puede borrar)</div>
                <div class="com-historial">${o.historial.map(h => `<div><b>${fecha(h.fecha)}</b> · ${esc(h.usuario || '')} · <b>${esc(h.accion)}</b>${h.detalle ? ' · ' + esc(h.detalle) : ''}</div>`).join('') || '<div class="inv-tip">Orden del sistema anterior: sin historial.</div>'}</div>`;
            pintarAcciones(o);
            abrir('detModal');
        } catch (e) { aviso(e.message, 'error'); }
    }

    function pintarAcciones(o) {
        const b = [];
        const v2 = o.flujo === 'v2';
        const c = o.paso.codigo;
        if (v2 && o.estado === 'Borrador' && PUEDE.comprar) {
            b.push(`<button class="btn btn-secondary" data-accion="editar">✏️ Corregir</button>`);
            b.push(`<button class="btn btn-primary" data-accion="enviar">Enviar a aprobar ➜</button>`);
        }
        if (v2 && o.estado === 'Por aprobar' && PUEDE.aprobar) {
            b.push(`<button class="btn btn-secondary" data-accion="devolver">↩ Devolver para corregir</button>`);
            b.push(`<button class="btn btn-primary" data-accion="aprobar">✔ Aprobar</button>`);
        }
        if (v2 && ['pagar', 'pagar_credito'].includes(c) && PUEDE.pagar) b.push(`<button class="btn btn-primary" data-accion="pagar">💸 Registrar pago</button>`);
        if (v2 && c === 'recibir' && PUEDE.recibir) b.push(`<button class="btn btn-primary" data-accion="recibir">📦 Recibir mercadería</button>`);
        if (v2 && ['Aprobada', 'Recibida parcial', 'Recibida'].includes(o.estado) && PUEDE.facturar) b.push(`<button class="btn btn-secondary" data-accion="factura">🧾 Registrar factura</button>`);
        if (v2 && o.estado === 'Recibida parcial' && PUEDE.aprobar) b.push(`<button class="btn btn-secondary" data-accion="faltante">Ya no llegará lo que falta</button>`);
        if (v2 && !['Borrador', 'Por aprobar', 'Anulada'].includes(o.estado)) {
            b.push(`<a class="btn btn-secondary" target="_blank" href="/compras/flujo/ordenes/${o.id}/imprimir">🖨 OC para el proveedor</a>`);
            if (o.modalidad_entrega === 'Nosotros recogemos') b.push(`<a class="btn btn-secondary" target="_blank" href="/compras/flujo/ordenes/${o.id}/imprimir?hoja=recojo">🚚 Hoja de recojo</a>`);
        }
        if (v2 && !['Anulada', 'Cerrada', 'Recibida', 'Recibida parcial'].includes(o.estado) && (PUEDE.aprobar || (o.estado === 'Borrador' && o.soy_creador)))
            b.push(`<button class="btn btn-secondary com-btn-danger" data-accion="anular">Anular</button>`);
        b.push(`<button class="btn btn-secondary" data-close="detModal">Cerrar</button>`);
        $('detAcciones').innerHTML = b.join('');
    }

    async function accionDetalle(accion, btn) {
        const o = detalleActual;
        if (!o) return;
        if (accion === 'editar') { cerrar('detModal'); abrirNuevaOC([], o); }
        else if (accion === 'enviar') {
            await guardarCon(btn, async () => { const r = await post(`/compras/api/flujo/ordenes/${o.id}/enviar`); aviso(r.message, 'success'); refrescar(); verOrden(o.id); });
        } else if (accion === 'aprobar') {
            await guardarCon(btn, async () => { const r = await post(`/compras/api/flujo/ordenes/${o.id}/aprobar`, { aprobar: true }); aviso(r.message, 'success'); refrescar(); verOrden(o.id); });
        } else if (accion === 'devolver') {
            pedirMotivo('Devolver para corregir', 'Escribe qué hay que corregir. La orden vuelve a Borrador.', async m => {
                const r = await post(`/compras/api/flujo/ordenes/${o.id}/aprobar`, { aprobar: false, motivo: m }); aviso(r.message, 'success'); refrescar(); verOrden(o.id);
            });
        } else if (accion === 'anular') {
            pedirMotivo('Anular orden', 'La orden queda anulada (no se borra) y los pedidos de sus clientes vuelven a "por comprar".', async m => {
                const r = await post(`/compras/api/flujo/ordenes/${o.id}/anular`, { motivo: m }); aviso(r.message, 'success'); refrescar(); verOrden(o.id);
            });
        } else if (accion === 'faltante') {
            pedirMotivo('Cerrar con faltante', 'Lo que falta quedará como diferencia por resolver (nota de crédito o devolución del dinero). Explica qué dijo el proveedor.', async m => {
                const r = await post(`/compras/api/flujo/ordenes/${o.id}/cerrar_faltante`, { motivo: m }); aviso(r.message, 'success'); refrescar(); verOrden(o.id);
            });
        } else if (accion === 'pagar') { cerrar('detModal'); abrirPago(o); }
        else if (accion === 'recibir') { cerrar('detModal'); abrirRecepcion(o.id); }
        else if (accion === 'factura') { cerrar('detModal'); abrirFactura(o); }
    }

    // ========================================================
    // PAGO
    // ========================================================
    function abrirPago(o) {
        $('pagoOc').value = o.id;
        $('pagoTitulo').textContent = `Registrar pago · ${o.numero}`;
        const p = cat.proveedores.find(x => x.id === o.proveedor_id) || o.proveedor_datos || {};
        const falta = Math.max(Number(o.total) - Number(o.pagado), 0);
        $('pagoCuenta').innerHTML = `<div class="com-cuenta">
            <small>Pagar a</small><b>${esc(o.proveedor)}</b><span>RUC ${esc(o.ruc || '—')}</span>
            ${p.numero_cuenta || p.cci ? `<div class="com-cuenta-num">🏦 ${esc(p.banco || '')} · Cuenta ${esc(p.numero_cuenta || '—')}${p.cci ? ' · CCI ' + esc(p.cci) : ''}</div>
                <span>Paga solo a esta cuenta. Si el proveedor te pide pagar a otra, consulta con tu supervisora.</span>`
                : '<div class="inv-aviso">⚠️ El proveedor no tiene cuenta registrada. Regístrala en Maestros ▸ Proveedores antes de pagar.</div>'}
            <div class="com-cuenta-falta">Falta pagar: <b>${soles(falta)}</b> de ${soles(o.total)}</div></div>`;
        $('pagoMonto').value = falta.toFixed(2);
        $('pagoFecha').value = hoyISO();
        $('pagoMetodo').value = 'Transferencia';
        ['pagoBanco', 'pagoOperacion', 'pagoObs'].forEach(i => { $(i).value = ''; });
        abrir('pagoModal');
    }

    // ========================================================
    // RECEPCIÓN A CIEGAS
    // ========================================================
    async function cargarRecibir() {
        try {
            const { data } = await api('/compras/api/flujo/por_recibir');
            $('recBodyCom').innerHTML = data.length ? data.map(o => {
                let accion;
                if (o.estado === 'Por aprobar') accion = '<span class="inv-tip">Falta aprobar</span>';
                else if (o.paso.codigo === 'pagar') accion = '<span class="inv-tip">🔒 Falta el pago</span>';
                else if (!PUEDE.recibir) accion = '—';
                else if (o.usuario_id === cat.usuarioId && !PUEDE.admin) accion = '<span class="inv-tip">Tú hiciste la orden: la recibe otra persona</span>';
                else accion = `<button class="btn-mini" data-recibir="${o.id}">📦 Recibir</button>`;
                return `<tr><td><button class="btn-link" data-ver="${o.id}">${esc(o.numero)}</button></td><td><b>${esc(o.empresa || '')}</b></td><td class="left">${esc(o.proveedor || '')}</td>
                    <td>${o.modalidad_entrega === 'Nosotros recogemos' ? `🚚 Recogemos<small>${esc(o.direccion_recojo || '')}</small>` : 'Proveedor entrega'}</td>
                    <td>${esc(o.sede || '')}</td><td>${fecha(o.fecha_compromiso)}${o.atrasada ? '<small class="neg">ATRASADA</small>' : ''}</td>
                    <td class="left">${esc(o.clientes || 'Stock')}</td><td><span class="${claseEstado(o.estado)}">${esc(o.estado)}</span></td><td>${accion}</td></tr>`;
            }).join('') : '<tr><td colspan="9">No hay mercadería por llegar.</td></tr>';
        } catch (e) { $('recBodyCom').innerHTML = `<tr><td colspan="9">${esc(e.message)}</td></tr>`; }
    }

    async function abrirRecepcion(id) {
        try {
            const r = await api(`/compras/api/flujo/ordenes/${id}/para_recibir`);
            const o = r.orden;
            $('recOc').value = o.id;
            $('recTitulo').textContent = `Recibir mercadería · ${o.numero}`;
            $('recInfo').innerHTML = `<b>${esc(o.proveedor || '')}</b> → <b>${esc(o.empresa || '')}</b>. Debe quedar en <b>${esc(o.sede || '')}</b>.<br>
                Cuenta cada producto y escribe lo que contaste. <b>Si no llegó, escribe 0.</b> Lo dañado va aparte (no entra al inventario).`;
            $('recSede').value = o.almacen_entrega_id || '';
            $('recGuia').value = '';
            $('recTraidoTipo').value = o.modalidad_entrega === 'Nosotros recogemos' ? 'usuario' : 'proveedor';
            $('recUsuario').value = '';
            $('recCourier').value = '';
            $('recObs').value = '';
            $('recItems').innerHTML = r.items.map(i => `<tr data-item="${i.id}">
                <td>${esc(i.codigo || '')}</td><td class="left"><b>${esc(i.producto)}</b><small>${esc([i.marca, i.modelo, i.unidad].filter(Boolean).join(' · '))}</small></td>
                <td><input type="number" class="inp-num com-inp-grande" data-c="buena" min="0" step="any" placeholder="?"></td>
                <td><input type="number" class="inp-num" data-c="danada" min="0" step="any" value="0"></td>
                <td><input type="text" class="inp-txt" data-c="lote" maxlength="120"></td>
                <td><input type="date" class="inp-txt" data-c="venc"></td>
                <td><input type="text" class="inp-txt" data-c="com" maxlength="200"></td></tr>`).join('');
            $('recCuerpo').style.display = '';
            $('recResultado').style.display = 'none';
            $('recPie').innerHTML = `<button class="btn btn-secondary" data-close="recModal">Cancelar</button><button class="btn btn-primary" id="recGuardar">✔ Registrar lo que conté</button>`;
            ajustarTraido();
            abrir('recModal');
        } catch (e) { aviso(e.message, 'error'); }
    }

    function ajustarTraido() {
        $('recUsuarioWrap').style.display = $('recTraidoTipo').value === 'usuario' ? '' : 'none';
        $('recCourierWrap').style.display = $('recTraidoTipo').value === 'courier' ? '' : 'none';
    }

    async function guardarRecepcion(btn) {
        const items = [...document.querySelectorAll('#recItems tr')].map(tr => ({
            oc_item_id: Number(tr.dataset.item),
            cantidad_buena: tr.querySelector('[data-c="buena"]').value,
            cantidad_danada: tr.querySelector('[data-c="danada"]').value || 0,
            lote_serie: tr.querySelector('[data-c="lote"]').value,
            fecha_vencimiento: tr.querySelector('[data-c="venc"]').value || null,
            comentario: tr.querySelector('[data-c="com"]').value
        }));
        const vacio = items.find(i => i.cantidad_buena === '');
        if (vacio) { aviso('Escribe cuántos llegaron de cada producto. Si no llegó, escribe 0.', 'error'); return; }
        const body = { almacen_id: $('recSede').value, guia_proveedor: $('recGuia').value, traido_por_tipo: $('recTraidoTipo').value,
            traido_por_id: $('recUsuario').value || null, traido_por: $('recCourier').value, observaciones: $('recObs').value, items };
        await guardarCon(btn, async () => {
            const r = await post(`/compras/api/flujo/ordenes/${$('recOc').value}/recibir`, body);
            $('recCuerpo').style.display = 'none';
            const res = $('recResultado');
            res.style.display = '';
            const color = { Completo: 'ok', Faltante: 'danger', Sobrante: 'warn', 'Con dañados': 'warn' };
            res.innerHTML = `<div class="inv-alerta ${r.resultado.some(x => x.estado !== 'Completo') ? 'warn' : 'ok'}"><div>${esc(r.message)}</div></div>
                <div class="inv-subtitulo">Ahora sí: lo que se esperaba y lo que contaste</div>
                <table class="inv-table"><thead><tr><th class="left">Producto</th><th>Se esperaba</th><th>Contaste (buenos)</th><th>Dañados</th><th>Resultado</th></tr></thead>
                <tbody>${r.resultado.map(x => `<tr><td class="left">${esc(x.producto)}</td><td class="num">${cant(x.esperado)}</td><td class="num">${cant(x.buena)}</td>
                    <td class="num">${cant(x.danada)}</td><td><span class="com-paso com-paso-${color[x.estado] || 'info'}">${esc(x.estado)}</span></td></tr>`).join('')}</tbody></table>
                <div class="inv-paso">Siguiente: ve a <b>Inventario ▸ Entradas y salidas</b> y pulsa "Ingresar" en esta recepción. Si es de un pedido, quedará separada para ese cliente.</div>`;
            $('recPie').innerHTML = `<a class="btn btn-secondary" href="/inventario?tab=entradas_salidas">Ir a Inventario ➜</a><button class="btn btn-primary" data-close="recModal">Listo</button>`;
            refrescar();
        });
    }

    // ========================================================
    // PAGOS Y FACTURAS
    // ========================================================
    async function cargarFacturas() {
        try {
            const { data } = await api('/compras/api/flujo/ordenes?estado=abiertas');
            const porPagar = data.filter(o => ['pagar', 'pagar_credito'].includes(o.paso.codigo));
            $('pagBody').innerHTML = porPagar.length ? porPagar.map(o => `<tr>
                <td><button class="btn-link" data-ver="${o.id}">${esc(o.numero)}</button></td><td><b>${esc(o.empresa || '')}</b></td>
                <td class="left">${esc(o.proveedor || '')}</td><td>${esc(o.condicion_pago || '')}</td>
                <td class="num">${soles(o.total)}</td><td class="num">${soles(o.pagado)}</td><td class="num"><b>${soles(o.saldo_pago)}</b></td>
                <td>${PUEDE.pagar ? `<button class="btn-mini" data-pagar="${o.id}">💸 Pagar</button>` : '—'}</td></tr>`).join('')
                : '<tr><td colspan="8">No hay órdenes por pagar. 👍</td></tr>';
            // Se espera factura cuando ya llegó mercadería o ya se pagó algo
            const sinFactura = data.filter(o => (['Recibida', 'Recibida parcial'].includes(o.estado) || Number(o.pagado) > 0)
                && (o.facturas === 0 || o.cuadra === false || Number(o.facturado) + 0.5 < Number(o.valor_recibido) * 1.18));
            $('facBody').innerHTML = sinFactura.length ? sinFactura.map(o => `<tr>
                <td><button class="btn-link" data-ver="${o.id}">${esc(o.numero)}</button></td><td><b>${esc(o.empresa || '')}</b></td>
                <td class="left">${esc(o.proveedor || '')}</td><td><span class="${claseEstado(o.estado)}">${esc(o.estado)}</span></td>
                <td><div class="com-barra"><i style="width:${o.avance_recepcion}%"></i></div><small>${Math.round(o.avance_recepcion)}%</small></td>
                <td>${o.facturas ? `${o.facturas} · ${soles(o.facturado)}${o.cuadra === false ? '<small class="neg">no cuadra</small>' : ''}` : '<span class="inv-tip">Ninguna</span>'}</td>
                <td>${PUEDE.facturar ? `<button class="btn-mini" data-factura="${o.id}">🧾 Registrar factura</button>` : '—'}</td></tr>`).join('')
                : '<tr><td colspan="7">No hay facturas pendientes de registrar. 👍</td></tr>';
            ordenesCache = data;
        } catch (e) { $('pagBody').innerHTML = `<tr><td colspan="8">${esc(e.message)}</td></tr>`; }
    }

    function abrirFactura(o) {
        $('facOc').value = o.id;
        $('facTitulo').textContent = `Factura del proveedor · ${o.numero}`;
        $('facTipo').value = 'Factura';
        ['facNumero', 'facMonto', 'facObs'].forEach(i => { $(i).value = ''; });
        $('facFecha').value = hoyISO();
        abrir('facModal');
    }

    // ========================================================
    // PRECIOS
    // ========================================================
    let tPre;
    async function cargarPrecios() {
        try {
            const { data } = await api('/compras/api/flujo/precios?q=' + encodeURIComponent($('preBuscar').value.trim()));
            $('preBody').innerHTML = data.length ? data.map(p => `<tr><td>${esc(p.codigo || '')}</td><td class="left">${esc(p.descripcion)}</td>
                <td class="left">${esc(p.proveedor || '—')}</td><td>${p.compras}</td><td class="num"><b>${soles(p.ultimo)}</b></td>
                <td class="num">${soles(p.minimo)}</td><td class="num">${soles(p.maximo)}</td><td>${fecha(String(p.ultima_fecha).slice(0, 10))}</td></tr>`).join('')
                : '<tr><td colspan="8">Todavía no hay compras aprobadas con este filtro.</td></tr>';
        } catch (e) { $('preBody').innerHTML = `<tr><td colspan="8">${esc(e.message)}</td></tr>`; }
    }

    // ========================================================
    // NAVEGACIÓN Y EVENTOS
    // ========================================================
    const cargadores = { hoy: cargarHoy, pedidos: cargarPedidos, ordenes: cargarOrdenes, recibir: cargarRecibir, facturas: cargarFacturas, precios: cargarPrecios };

    function cambiarTab(tab, push = true) {
        if (!cargadores[tab]) tab = 'hoy';
        tabActual = tab;
        document.querySelectorAll('#tabsRowCom .tab-btn[data-tab]').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
        document.querySelectorAll('#comApp > .section').forEach(s => s.classList.toggle('active', s.id === 'sec-' + tab));
        if (push) {
            const url = new URL(window.location);
            url.searchParams.set('tab', tab);
            window.history.replaceState({}, '', url);
        }
        document.querySelectorAll('.child-btn[data-screen]').forEach(b => {
            if (b.getAttribute('href') && b.getAttribute('href').startsWith('/compras?')) b.classList.toggle('active', b.dataset.screen === tab);
        });
        cargadores[tab]();
    }
    const refrescar = () => { cargadores[tabActual](); if (tabActual !== 'hoy') cargarHoy(); };

    document.addEventListener('click', async e => {
        const t = e.target;
        const tab = t.closest('#tabsRowCom .tab-btn[data-tab]');
        if (tab) { cambiarTab(tab.dataset.tab); return; }
        const ir = t.closest('[data-ir]');
        if (ir) {
            if (ir.dataset.paso) $('ocPaso').value = ir.dataset.paso;
            cambiarTab(ir.dataset.ir);
            return;
        }
        const b = t.closest('button, a, tr');
        if (!b) return;
        const d = b.dataset;
        if (d.accion) { accionDetalle(d.accion, b); return; }
        if (d.quitar !== undefined && b.tagName === 'BUTTON') {
            lineas.splice(Number(d.quitar), 1);
            if (!lineas.length) lineas.push(lineaVacia());
            pintarLineas(); ajustarForm(); return;
        }
        if (d.resolver) {
            pedirMotivo('Resolver diferencia', 'Escribe cómo se resolvió: por ejemplo "el proveedor repuso 2 unidades con guía EG01-55", "nota de crédito F001-123" o "se devolvió el sobrante".', async m => {
                const r = await post(`/compras/api/flujo/incidencias/${d.resolver}/resolver`, { resolucion: m }); aviso(r.message, 'success'); refrescar(); verOrden(detalleActual.id);
            });
            return;
        }
        if (d.recibir) { abrirRecepcion(Number(d.recibir)); return; }
        if (d.pagar) { const { data: o } = await api('/compras/api/flujo/ordenes/' + d.pagar); abrirPago(o); return; }
        if (d.factura) { const { data: o } = await api('/compras/api/flujo/ordenes/' + d.factura); abrirFactura(o); return; }
        if (d.ver && !t.closest('input')) { verOrden(Number(d.ver)); return; }
        if (b.id === 'recGuardar') guardarRecepcion(b);
    });

    document.addEventListener('change', e => {
        if (e.target.classList.contains('ped-check')) contarMarcados();
    });
    document.addEventListener('input', e => {
        if (e.target.classList.contains('ped-extra')) actualizarResumen(e.target);
    });

    $('ocLineas').addEventListener('input', e => {
        const tr = e.target.closest('tr[data-linea]');
        if (!tr || !e.target.dataset.campo) return;
        const i = Number(tr.dataset.linea);
        lineas[i][e.target.dataset.campo] = e.target.value;
        $('tot-' + i).textContent = soles((Number(lineas[i].cantidad) || 0) * (Number(lineas[i].precio_unitario) || 0));
        if (e.target.dataset.campo === 'precio_unitario') revisarPrecio(i);
        totales();
        if (e.target.dataset.campo === 'cantidad') pintarAbastecimiento();
    });
    document.addEventListener('click', e => {
        const b = e.target.closest('[data-sugerido]');
        if (b) usarSugerido(Number(b.dataset.sugerido));
    });

    function iniciarEventos() {
        crearPickerProveedor();
        $('btnRefrescarHoy').onclick = cargarHoy;
        $('btnRefrescarRecibir').onclick = cargarRecibir;
        $('btnNuevaOC').onclick = () => abrirNuevaOC();
        $('btnCrearDesdePedidos').onclick = crearDesdePedidos;
        $('btnLineaStock').onclick = () => { lineas.push(lineaVacia()); pintarLineas(); ajustarForm(); };
        $('pedTodos').onchange = cargarPedidos;
        $('pedBuscar').oninput = pintarPedidos;
        ['ocEmpresa', 'ocPaso', 'ocSinPedido'].forEach(i => { if ($(i)) $(i).onchange = cargarOrdenes; });
        $('ocMotivoCompra').onchange = ajustarForm;
        let tOc;
        $('ocBuscar').oninput = () => { clearTimeout(tOc); tOc = setTimeout(cargarOrdenes, 300); };
        $('preBuscar').oninput = () => { clearTimeout(tPre); tPre = setTimeout(cargarPrecios, 300); };
        ['ocCondicion', 'ocModalidad', 'ocEmp', 'ocSede'].forEach(i => { $(i).onchange = ajustarForm; });
        $('ocGuardar').onclick = () => guardarOC(false, $('ocGuardar'));
        $('ocEnviar').onclick = () => guardarOC(true, $('ocEnviar'));
        $('recTraidoTipo').onchange = ajustarTraido;
        $('pagoGuardar').onclick = () => guardarCon($('pagoGuardar'), async () => {
            const r = await post(`/compras/api/flujo/ordenes/${$('pagoOc').value}/pago`, {
                monto: $('pagoMonto').value, fecha: $('pagoFecha').value, metodo: $('pagoMetodo').value, banco: $('pagoBanco').value,
                numero_operacion: $('pagoOperacion').value, observaciones: $('pagoObs').value });
            aviso(r.message, 'success'); cerrar('pagoModal'); refrescar();
        });
        $('facGuardar').onclick = () => guardarCon($('facGuardar'), async () => {
            const r = await post(`/compras/api/flujo/ordenes/${$('facOc').value}/factura`, {
                tipo: $('facTipo').value, numero: $('facNumero').value, fecha: $('facFecha').value, monto: $('facMonto').value,
                observaciones: $('facObs').value });
            aviso(r.message, r.cuadra ? 'success' : 'warning'); cerrar('facModal'); refrescar();
        });
    }

    (async function iniciar() {
        try {
            await cargarCatalogos();
            iniciarEventos();
            if (!cat.empresas.length || !cat.sedes.length)
                aviso('Faltan datos: registra las empresas (Configuración ▸ Empresas) y las sedes (Maestros ▸ Almacenes).', 'error');
            const qs = new URLSearchParams(location.search);
            cambiarTab(app.dataset.tab || qs.get('tab') || 'hoy', false);
            // Acceso directo "+ Nueva orden": /compras?tab=ordenes&nueva=1
            if (app.dataset.nueva === 'true' || qs.get('nueva') === '1') {
                if (tabActual !== 'ordenes') cambiarTab('ordenes');
                abrirNuevaOC();
                const url = new URL(window.location); url.searchParams.delete('nueva'); window.history.replaceState({}, '', url);
            }
        } catch (e) { aviso('No se pudo cargar Compras: ' + e.message, 'error'); }
    })();
})();
