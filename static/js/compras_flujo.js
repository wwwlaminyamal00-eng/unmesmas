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
    let pedidoResaltado = null;   // PV que llegó desde Ventas ▸ Entregas ▸ Generar compra (se sombrea)
    let ordenesCache = [];
    let lineas = [];           // líneas del formulario de OC
    let provElegido = null;    // proveedor elegido en el formulario
    let detalleActual = null;
    const extrasStock = {};    // "Comprar para stock" que escribe el usuario en la tabla de pedidos (clave pedido_item)

    // ---------- utilidades ----------
    const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const soles = n => 'S/ ' + Number(n || 0).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    // 24/10/2026 (Erika): compras en dólares. Muestra US$ o S/ según la moneda del documento
    const dinero = (m, n) => (window.Moneda && Moneda.codigo(m) === 'USD' ? 'US$ ' : 'S/ ') + Number(n || 0).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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
    // 22/10/2026 (Erika): "Aprobada" y "Recibida" se confundían. Solo cambia lo que se ve; en la base sigue igual.
    const NOMBRE_ESTADO_OC = {
        'Borrador': 'Borrador', 'Por aprobar': 'Por aprobar', 'Aprobada': 'Aprobada · falta llegar',
        'Recibida parcial': 'Llegó una parte', 'Recibida': 'Mercadería recibida', 'Cerrada': '✔ Completa', 'Anulada': 'Anulada'
    };
    const estadoOC = e => `<span class="${claseEstado(e)}">${esc(NOMBRE_ESTADO_OC[e] || e || '')}</span>`;

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
        if (!resp.ok || json.success === false) {
            const err = new Error(json.error || `Error ${resp.status}`);
            err.data = json;
            err.status = resp.status;
            throw err;
        }
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

    // ========================================================
    // CARTEL "¿AHORA QUÉ?" (pedido de Erika 20/10/2026 22:54): después de cada acción
    // se dice en grande a dónde ir y qué buscar, con un botón que lleva ahí.
    // ========================================================
    const SIGUIENTE = {
        enviar: { tab: 'ordenes', ir: 'Órdenes de compra (Proveedor)', txt: 'Revisa la orden y pulsa <b>"Enviar a aprobar"</b>. Está en <b>Compras ▸ Órdenes de compra (Proveedor)</b>.' },
        aprobar: { tab: 'ordenes', ir: 'Órdenes de compra (Proveedor)', txt: 'Ahora la <b>supervisora</b> debe aprobarla en <b>Compras ▸ Órdenes de compra (Proveedor)</b> (búscala con el estado "Por aprobar").' },
        pagar: { tab: 'facturas', ir: 'Pagos y facturas', txt: 'Es al contado: ve a <b>Compras ▸ Pagos y facturas</b> y pulsa <b>"💸 Pagar"</b> en esta orden.' },
        recibir: { tab: 'recibir', ir: 'Recibir mercadería', txt: 'Cuando llegue la mercadería, ve a <b>Compras ▸ Recibir mercadería</b> y pulsa <b>"📦 Recibir"</b> en esta orden.' },
        factura: { tab: 'facturas', ir: 'Pagos y facturas', txt: 'Ve a <b>Compras ▸ Pagos y facturas</b> para registrar la <b>factura del proveedor</b> (botón "🧾 Registrar factura").' },
        pagar_credito: { tab: 'facturas', ir: 'Pagos y facturas', txt: 'Es a crédito: ve a <b>Compras ▸ Pagos y facturas</b> y paga la factura antes de que venza.' },
        incidencia: { tab: 'ordenes', ir: 'Órdenes de compra (Proveedor)', txt: 'Hay <b>diferencias</b> (faltó o sobró algo): la supervisora las revisa en <b>Compras ▸ Órdenes de compra (Proveedor)</b>.' },
        listo: { tab: 'ordenes', ir: 'Órdenes de compra (Proveedor)', txt: 'La compra está <b>completa</b>. No falta nada. 🎉' },
        anulada: { tab: 'pedidos', ir: 'Pedidos por comprar', txt: 'Los pedidos de los clientes de esta orden vuelven a <b>Compras ▸ Pedidos por comprar</b>.' }
    };

    function cartel(titulo, texto, botones) {
        if (!document.getElementById('comCartelCss')) {
            const st = document.createElement('style');
            st.id = 'comCartelCss';
            st.textContent = `#comCartel{position:fixed;inset:0;background:rgba(15,23,42,.45);z-index:99999;display:flex;align-items:center;justify-content:center;padding:16px}
                #comCartel .cc-caja{background:#fff;border:4px solid #00C853;border-radius:16px;max-width:560px;width:100%;box-shadow:0 20px 50px rgba(0,0,0,.3);overflow:hidden}
                #comCartel .cc-tit{background:#00E676;color:#003D1A;font-size:22px;font-weight:900;padding:16px 20px}
                #comCartel .cc-txt{padding:16px 20px;font-size:16px;line-height:1.5;color:#0F172A}
                #comCartel .cc-txt .cc-ahora{display:block;font-size:18px;font-weight:900;margin-bottom:6px}
                #comCartel .cc-pie{display:flex;gap:10px;flex-wrap:wrap;justify-content:flex-end;padding:0 20px 18px}
                #comCartel .cc-pie button{font-size:15px;font-weight:800;padding:10px 16px;border-radius:10px;cursor:pointer;border:2px solid #0F172A;background:#fff}
                #comCartel .cc-pie button.cc-ir{background:#0F172A;color:#fff}`;
            document.head.appendChild(st);
        }
        document.getElementById('comCartel')?.remove();
        const div = document.createElement('div');
        div.id = 'comCartel';
        div.innerHTML = `<div class="cc-caja" role="dialog" aria-modal="true"><div class="cc-tit">${titulo}</div>
            <div class="cc-txt"><span class="cc-ahora">👉 ¿Ahora qué?</span>${texto}</div>
            <div class="cc-pie">${(botones || []).map((b, i) => `<button type="button" class="${b.ir ? 'cc-ir' : ''}" data-i="${i}">${b.t}</button>`).join('')}
                <button type="button" data-i="x">Seguir aquí</button></div></div>`;
        div.addEventListener('click', e => {
            const b = e.target.closest('button[data-i]');
            if (!b && e.target !== div) return;
            div.remove();
            const accion = b && b.dataset.i !== 'x' ? botones[Number(b.dataset.i)] : null;
            if (accion && accion.tab) { document.querySelectorAll('.modal.show').forEach(m => m.classList.remove('show')); cambiarTab(accion.tab); }
            if (accion && accion.href) window.location.href = accion.href;
        });
        document.body.appendChild(div);
        div.querySelector('.cc-ir')?.focus();
    }

    // Cartel según el siguiente paso real de la orden (se pregunta al servidor)
    async function cartelSiguiente(ocId, titulo, extra) {
        try {
            const { data: o } = await api('/compras/api/flujo/ordenes/' + ocId);
            const s = SIGUIENTE[o.paso.codigo] || SIGUIENTE.listo;
            const botones = [{ t: `Ir a ${s.ir} ➜`, tab: s.tab, ir: true }, ...(extra && extra.botones || [])];
            cartel(titulo, s.txt + (extra && extra.texto ? `<br><br>${extra.texto}` : ''), botones);
        } catch (e) { /* si falla la consulta queda el aviso normal */ }
    }

    // ---------- catálogos ----------
    async function cargarCatalogos() {
        const r = await api('/compras/api/flujo/catalogos');
        Object.assign(cat, { empresas: r.empresas, sedes: r.sedes, proveedores: r.proveedores, usuarios: r.usuarios,
            registro: r.registro_sunat, empresaDefecto: r.empresa_defecto, usuarioId: r.usuario_id, metodos: r.metodos,
            motivos: r.motivos_sin_pedido || [], monedasCuenta: r.monedas_cuenta || {}, bancosEmpresa: r.bancos_empresa || {} });
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
            alertasHoy = r.alertas;
            $('hoyAlertas').innerHTML = r.alertas.map((a, i) => `<div class="inv-alerta ${a.nivel}">
                <div>${a.texto}</div>${a.ir ? `<button class="btn-mini sec" data-ir="${a.ir}" data-alerta="${i}">Ver ➜</button>` : ''}</div>`).join('');
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

    // Erika 28/10/2026 12:10: en Compras los documentos van siempre en este orden: PV, PC, Cotización, N° despacho
    function docsPedido(p, desp) {
        const az = v => `<b class="aviso-azul">${esc(v)}</b>`;
        const partes = [`PV (Pedido de venta) ${az(p.numero)}`, `PC (Pedido del cliente) ${p.pc_cliente ? az(p.pc_cliente) : '—'}`,
                        `Cotización ${p.cotizacion ? az(p.cotizacion) : '—'}`];
        if (desp !== undefined) partes.push(`N° despacho ${desp ? az(desp) : '—'}`);
        return partes.join(' · ');
    }

    function pintarPedidos() {
        const q = $('pedBuscar').value.trim().toLowerCase();
        const lista = pedidosCache.filter(p => !q || [p.numero, p.cliente, p.ruc, ...p.items.map(i => i.descripcion + ' ' + i.codigo)]
            .join(' ').toLowerCase().includes(q));
        $('pedLista').innerHTML = lista.length ? lista.map(p => `
            <div class="com-pedido${pedidoResaltado && pedidoResaltado.id === p.id ? ' com-pedido-resaltado' : ''}" data-pedido="${p.id}">
                ${pedidoResaltado && pedidoResaltado.id === p.id ? `<div class="com-resaltado-nota">👉 <b>Este es el pedido:</b> ${docsPedido(p, pedidoResaltado.desp)}<br>Sus líneas por comprar ya están marcadas. Revisa y pulsa <b>Crear OC - Orden de compra (Proveedor)</b>.</div>` : ''}
                <div class="com-pedido-head">
                    <div>${docsPedido(p)} · ${esc(p.cliente || 'Sin cliente')} <small>${esc(p.ruc || '')}</small></div>
                    <div class="com-pedido-meta">${fecha(p.fecha)} · <span class="${claseEstado(p.estado)}">${esc(String(p.estado || 'Pendiente').replace(/^PC\b/, 'PV'))}</span>
                        ${p.lugar_entrega ? ` · Entrega: ${esc(p.lugar_entrega)}` : ''}</div>
                </div>
                <div class="table-wrap"><table class="inv-table inv-mini com-resumen">
                    <colgroup><col class="c-chk"><col class="c-prod"><col class="c-pv"><col class="c-oc"><col class="c-stock"><col class="c-bajo"><col class="c-para"><col class="c-total"></colgroup>
                    <thead><tr><th></th><th class="left">Nombre producto</th><th>PV<small>Pedido de venta</small></th><th title="Cantidad que ya está en órdenes de compra al proveedor (aprobadas o por aprobar). Las anuladas no cuentan.">Ya pedido al proveedor<small>en OC (Proveedor)</small></th><th>Stock asignado<small>a este PV</small></th>
                        <th>Compra bajo pedido</th><th>Comprar para stock</th><th>Total a comprar</th></tr></thead>
                    <tbody>${p.items.map((it, i) => {
                        const sinProducto = !it.producto_id;
                        // Por defecto solo lo que falta comprar: lo cubierto por una orden o por stock no se muestra (21/10/2026)
                        const cubierto = !sinProducto && (Number(it.falta) <= 0 || Number(it.comprar_pedido) <= 0);
                        if (cubierto && !$('pedTodos').checked) return '';
                        // Con OC activa que ya cubre la línea (o stock) la casilla no se puede marcar (21/10/2026)
                        const cubiertaYa = !sinProducto && (Number(it.falta) <= 0 || Number(it.comprar_pedido) <= 0);
                        const marcable = PUEDE.comprar && it.falta > 0 && !sinProducto && !cubiertaYa;
                        const r = calcResumen(p, i);
                        const clave = `${p.id}_${i}`;
                        const resaltar = marcable && pedidoResaltado && pedidoResaltado.id === p.id;
                        return `<tr class="${cubierto ? 'com-ok' : ''}${resaltar ? ' com-fila-resaltada' : ''}" data-res="${clave}">
                            <td>${marcable ? `<input type="checkbox" class="ped-check" data-ped="${p.id}" data-i="${i}">` : (cubierto ? '<input type="checkbox" disabled title="Ya cubierto: no hace falta comprar">' : '')}${cubierto ? `<small class="com-cubierto">${it.ocs ? '✅ OC ya generada' : '✔ Cubierto con stock'}</small>` : ''}</td>
                            <td class="left"><b>${esc(it.codigo)}</b> ${esc(it.descripcion)}${it.ocs ? `<small class="com-oc-generada">✅ OC ya generada: ${esc(it.ocs)}${cubierto ? '' : ` · falta comprar ${cant(it.comprar_pedido)}`}</small>` : ''}${sinProducto ? '<small class="neg">Este producto no está en el catálogo: créalo en Productos para poder comprarlo.</small>' : ''}
                                ${it.stock_libre > r.stock && it.falta > 0 ? `<small class="com-stock-si" title="Stock sin separar en otras empresas/sedes del grupo">Hay ${cant(it.stock_libre)} libres en el grupo</small>` : ''}</td>
                            <td class="num">${cant(it.cantidad)} ${esc(it.unidad || '')}</td>
                            <td class="num">${cant(it.comprado)}${Number(it.comprado_por_aprobar) > 0 ? `<small class="com-por-aprobar" title="Esa parte está en una OC que todavía no se aprueba">${cant(it.comprado_por_aprobar)} por aprobar</small>` : ''}</td>
                            <td class="num">${r.stock > 0 ? `<span class="com-stock-si">${cant(r.stock)}</span>` : '<span class="com-stock-no">0</span>'}${Number(it.stock_empresa) > r.stock ? `<small title="El stock se reparte entre los PV: el más antiguo primero">${cant(it.stock_empresa)} en la empresa · ${cant(Number(it.stock_empresa) - r.stock)} para PV más antiguos</small>` : ''}</td>
                            <td class="num"><b>${cant(r.pedido)}</b></td>
                            <td>${marcable ? `<input type="number" class="inp-num ped-extra" min="0" step="any" value="${r.extra}" data-ped="${p.id}" data-i="${i}" title="0 por defecto: comprar de más es una decisión y pide motivo">` : ''}</td>
                            <td class="num"><b data-res-total>${cant(r.total)}</b></td></tr>`;
                    }).join('')}</tbody>
                </table></div>
                ${!$('pedTodos').checked && p.items.length > p.por_comprar ? `<div class="inv-tip com-ocultos">✔ ${p.items.length - p.por_comprar} producto(s) de este pedido ya están cubiertos (con orden de compra o stock) y no se muestran.</div>` : ''}
            </div>`).join('') : '<div class="inv-vacio">No hay pedidos de clientes pendientes de compra. 👍</div>';
        contarMarcados();
    }

    // PV 40, stock asignado 10 -> compra bajo pedido 30; + 100 para stock -> total a comprar 130
    function calcResumen(p, i) {
        const it = p.items[i];
        const falta = Math.max(Number(it.falta) || 0, 0);
        // Stock asignado a ESTE pedido: el stock se reparte entre pedidos, el más antiguo primero (22/10/2026)
        const stock = Math.max(Number(it.stock_asignado ?? it.stock_empresa) || 0, 0);
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
        const chk = tr.querySelector('.ped-check');
        if (chk && r.extra > 0 && !chk.checked) { chk.checked = true; contarMarcados(); }
    }

    function contarMarcados() {
        const n = document.querySelectorAll('.ped-check:checked').length;
        $('pedMarcados').textContent = n;
        $('btnCrearDesdePedidos').disabled = n === 0;
    }

    // "Generar compra" de Ventas ▸ Entregas (Erika 22/10/2026): ya no abre la orden de golpe. Lleva a Pedidos por comprar,
    // sombrea el pedido y SUS líneas (por línea del PV, no por producto: el mismo producto puede ir a Lima y a Arequipa),
    // las deja marcadas y se desplaza hasta ellas. La persona revisa y pulsa "Crear OC - Orden de compra (Proveedor)".
    async function abrirCompraDePedido(numero, despacho) {
        const url = new URL(window.location); url.searchParams.delete('pc'); url.searchParams.delete('desp'); window.history.replaceState({}, '', url);
        if (tabActual !== 'pedidos') cambiarTab('pedidos');
        await cargarPedidos();
        const p = pedidosCache.find(x => String(x.numero || '').trim() === String(numero).trim());
        if (!p) {
            aviso(`El pedido ${numero} ya no tiene nada pendiente de compra (o es de otra empresa: revisa la empresa activa arriba).`, 'warning');
            return;
        }
        pedidoResaltado = { id: p.id, numero: p.numero, desp: despacho || '' };
        $('pedBuscar').value = '';
        pintarPedidos();
        document.querySelectorAll('.ped-check:checked').forEach(c => { c.checked = false; });
        const marcas = [...document.querySelectorAll(`.ped-check[data-ped="${p.id}"]`)];
        const tarjeta = document.querySelector(`.com-pedido[data-pedido="${p.id}"]`);
        if (tarjeta) tarjeta.scrollIntoView({ behavior: 'smooth', block: 'center' });
        if (!marcas.length) {
            aviso(`El pedido ${numero} no tiene productos por comprar (ya está cubierto o sus productos no están en el catálogo).`, 'warning');
            return;
        }
        marcas.forEach(c => { c.checked = true; });
        contarMarcados();
        aviso(`Pedido ${numero}: ${marcas.length} línea(s) marcadas y sombreadas. Revisa y pulsa "Crear OC - Orden de compra (Proveedor)".`, 'success');
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
        // 22/10/2026 (Erika): solo el cliente; el N° PV y el N° cotización ya tienen su propia columna
        return `${esc(o.clientes || o.clientes_pedido || '')}${o.tipo_compra === 'Para stock' ? `<small>+ stock</small>${motivo}` : ''}`;
    }

    // "Ver" de Hoy en Compras: la lista sale solo con las órdenes de esa alerta (Erika 26/10/2026)
    let alertasHoy = [];
    let filtroVer = null;   // { tab, ids:Set, filtro }
    function aplicarFiltroVer(tab, data) {
        const caja = $('filtroVer-' + tab);
        if (!filtroVer || filtroVer.tab !== tab) { if (caja) caja.remove(); return data; }
        const lista = data.filter(o => filtroVer.ids.has(o.id));
        const seccion = $('sec-' + tab);
        let c = caja;
        if (!c && seccion) {
            c = document.createElement('div');
            c.id = 'filtroVer-' + tab;
            c.className = 'com-filtro-ver';
            seccion.insertBefore(c, seccion.firstChild);
        }
        if (c) c.innerHTML = `<span>🔎 Mostrando solo: <b>${esc(filtroVer.filtro)}</b> (${filtroVer.ids.size})</span>
            <button type="button" class="btn-mini sec" data-quitar-filtro="1">✖ Quitar filtro</button>`;
        return lista;
    }
    async function cargarOrdenes() {
        try {
            const conFiltro = filtroVer && filtroVer.tab === 'ordenes';
            // Al buscar un N° se busca en todas (también las ya recibidas), 27/10/2026
            const params = new URLSearchParams({ estado: conFiltro || $('ocBuscar').value.trim() || $('ocPaso').value === 'anulada' || $('ocPaso').value === 'listo' ? '' : 'abiertas' });
            if ($('ocEmpresa').value) params.set('empresa_id', $('ocEmpresa').value);
            if ($('ocPaso').value && !conFiltro) params.set('paso', $('ocPaso').value);
            if ($('ocBuscar').value.trim()) params.set('q', $('ocBuscar').value.trim());
            if ($('ocSinPedido') && $('ocSinPedido').checked) params.set('sin_pedido', '1');
            const data = aplicarFiltroVer('ordenes', (await api('/compras/api/flujo/ordenes?' + params)).data);
            ordenesCache = data;
            $('ocBody').innerHTML = data.length ? data.map(o => `<tr class="com-fila" data-ver="${o.id}">
                <td><b>${esc(o.numero)}</b>${o.atrasada ? '<small class="neg">ATRASADA</small>' : ''}</td>
                <td>${fecha(o.created_at || o.fecha)}${o.updated_at && fecha(o.updated_at) !== fecha(o.created_at || o.fecha) ? `<small>Modificada ${fecha(o.updated_at)}</small>` : ''}</td>
                <td><b>${esc(o.empresa || '—')}</b></td>
                <td class="left">${esc(o.proveedor || '')}<small>${esc(o.ruc || '')}</small></td>
                <td class="left">${paraHtml(o)}</td>
                <td>${o.sin_pedido ? '<span class="badge-sin-pedido">Sin PV</span>' : esc(o.pc_numeros || o.pedidos || '—')}</td>
                <td>${esc(o.cotizaciones_cliente || o.cotizaciones || '—')}</td>
                <td>${esc(o.sede || '—')}<small>${o.modalidad_entrega === 'Nosotros recogemos' ? '🚚 Recogemos' : 'Proveedor entrega'}</small></td>
                <td>${esc(condPagoMostrar(o.condicion_pago, o.dias_credito))}</td>
                <td class="num">${dinero(o.moneda, o.total)}${o.moneda === 'USD' && o.tipo_cambio ? `<small>TC ${Number(o.tipo_cambio).toFixed(3)}</small>` : ''}${o.pagado > 0 ? `<small>Pagado ${dinero(o.moneda, o.pagado)}</small>` : ''}</td>
                <td>${estadoOC(o.estado)}${o.incidencias ? `<small class="neg">${o.incidencias} diferencia(s)</small>` : ''}</td>
                <td><div class="com-barra ${Number(o.avance_recepcion) <= 0 ? 'com-barra-0' : (Number(o.avance_recepcion) >= 100 ? 'com-barra-100' : '')}"><i style="width:${o.avance_recepcion}%"></i></div><small>${Math.round(o.avance_recepcion)}%</small></td>
                <td class="left">${pasoHtml(o)}</td>
                <td><button class="btn-mini sec" data-ver="${o.id}">Ver</button></td></tr>`).join('')
                : '<tr><td colspan="14">No hay órdenes con este filtro.</td></tr>';
            const vivas = data.filter(o => o.estado !== 'Anulada');
            const total = vivas.filter(o => o.moneda !== 'USD').reduce((s, o) => s + Number(o.total), 0);
            const totalUsd = vivas.filter(o => o.moneda === 'USD').reduce((s, o) => s + Number(o.total), 0);
            $('ocFoot').textContent = `${data.length} orden(es) · Total ${soles(total)}${totalUsd ? ' + ' + dinero('USD', totalUsd) : ''}`;
        } catch (e) { $('ocBody').innerHTML = `<tr><td colspan="14">${esc(e.message)}</td></tr>`; }
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
        const cp = oc ? condPagoPartes(oc.condicion_pago, oc.dias_credito) : { tipo: 'Contado', dias: 0 };
        $('ocCondicion').value = cp.tipo || 'Contado';
        $('ocDias').value = cp.dias || '';
        $('ocAdelantoPct').value = String(Math.round((Number(oc && oc.adelanto_pct) || 0) / 10) * 10);
        $('ocModalidad').value = oc ? (oc.modalidad_entrega || 'Proveedor entrega') : 'Proveedor entrega';
        $('ocRecojo').value = oc ? (oc.direccion_recojo || '') : '';
        const smp = cat.sedes[0];
        $('ocSede').value = oc ? oc.almacen_entrega_id : (smp ? smp.id : '');
        $('ocFecha').value = oc ? (oc.fecha_compromiso || '') : hoyISO(2);
        $('ocCotizacion').value = oc ? (oc.num_cotizacion || '') : '';
        $('ocNotas').value = oc ? (oc.notas || '') : '';
        $('ocNotaInterna').value = oc ? (oc.nota_interna || '') : '';
        $('ocMotivo').value = oc ? (oc.motivo_stock || '') : '';
        $('ocMotivoCompra').value = oc && oc.motivo_compra ? oc.motivo_compra : '';
        Moneda.enlazar('oc', { fecha: () => hoyISO(), total: totalOC, alCambiar: totales });
        Moneda.poner('oc', oc ? (oc.moneda || 'PEN') : 'PEN', oc ? oc.tipo_cambio : null);
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
        const credito = $('ocCondicion').value === 'Crédito';
        $('ocDiasWrap').style.display = credito ? '' : 'none';
        if (!credito) $('ocDias').value = '';
        const ct = $('ocCondTexto');
        if (ct) ct.textContent = credito ? condPagoTexto('Crédito', $('ocDias').value) : '';
        // Adelanto (%) solo con Crédito o Contra entrega ("Adelanto 50%" ya trae su 50%; Contado es todo antes)
        const conAdel = credito || $('ocCondicion').value === 'Contra entrega';
        $('ocAdelWrap').style.display = conAdel ? '' : 'none';
        if (!conAdel) $('ocAdelantoPct').value = '0';
        textoAdelanto();
        $('ocRecojoWrap').style.display = $('ocModalidad').value === 'Nosotros recogemos' ? '' : 'none';
        if ($('ocModalidad').value === 'Nosotros recogemos' && !$('ocRecojo').value && provElegido)
            $('ocRecojo').value = provElegido.lugar_recojo || provElegido.direccion || '';
        const conProducto = lineas.filter(l => l.producto_id);
        const sinPedido = conProducto.filter(l => !l.pedido_id);
        $('ocMotivoWrap').style.display = sinPedido.length ? '' : 'none';
        $('ocSinPedidoTxt').textContent = sinPedido.length && sinPedido.length === conProducto.length
            ? 'Compra solo para stock' : 'Compra para stock (además del PV)';
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

    // 22/10/2026 (Erika: "que sea una ayuda, no una confusión"): primero lo de ESTA orden, pedido por pedido.
    // Antes se sumaban todos los pedidos abiertos del producto (40 + 18 = 58) en una sola cifra y no se sabía
    // de dónde salía "Faltan 18". Ahora: una fila por pedido (PV) con lo que pide, lo que ya está en otras OC,
    // el stock que le toca (el stock se reparte, el pedido más antiguo primero) y lo que falta comprar.
    // Los pedidos de esta orden van arriba y sombreados; los demás salen aparte como "otro pedido sin comprar".
    function pintarAbastecimiento() {
        const caja = $('ocAbast');
        if (!caja) return;
        const ids = [...new Set(lineas.filter(l => l.producto_id).map(l => l.producto_id))];
        const emp = (cat.empresas.find(e => String(e.id) === String($('ocEmp').value)) || {});
        const nomEmp = emp.codigo || emp.nombre || 'la empresa';
        if (!ids.length) {
            caja.innerHTML = `<div class="com-abast-tit">📊 Resumen de abastecimiento</div><div class="com-abast-vacio">Elige un producto y aquí verás el stock, lo que pide cada cliente y cuánto comprar.</div>`;
            return;
        }
        const bloques = ids.map(pid => {
            const d = abastDatos[pid];
            const mias = lineas.filter(l => l.producto_id === pid);
            const nombre = esc((mias[0] || {}).texto || '');
            if (!d) return `<div class="com-ab-prod"><div class="com-ab-head">${nombre} · Calculando...</div></div>`;
            const enOrden = idp => mias.filter(l => String(l.pedido_id || '') === String(idp || '')).reduce((s, l) => s + (Number(l.cantidad) || 0), 0);
            const pedidosOrden = new Set(mias.filter(l => l.pedido_id).map(l => String(l.pedido_id)));
            const pcs = d.pedidos || [];
            const deEsta = pcs.filter(p => pedidosOrden.has(String(p.pedido_id)));
            const otros = pcs.filter(p => !pedidosOrden.has(String(p.pedido_id)));
            const paraStock = enOrden(null);
            const filaPc = (p, esta) => {
                const va = esta ? enOrden(p.pedido_id) : 0;
                let res;
                if (!esta) res = p.por_comprar > 0
                    ? `<span class="com-abast-sem gris">Otro pedido sin comprar: ${cant(p.por_comprar)}</span>
                       <button type="button" class="btn-mini sec" data-sumar-pc="${pid}|${p.pedido_id}" title="Agrega a esta orden lo que le falta a ese pedido">Sumarlo aquí</button>`
                    : '<span class="com-abast-sem gris">Cubierto con stock</span>';
                else if (Math.abs(va - p.por_comprar) < 1e-9) res = `<span class="com-abast-sem verde">✔ Cubre lo que falta</span>`;
                else if (va < p.por_comprar) res = `<span class="com-abast-sem rojo">✖ Faltan ${cant(p.por_comprar - va)}</span>
                       <button type="button" class="btn-mini sec" data-usar-pc="${pid}|${p.pedido_id}" title="Poner ${cant(p.por_comprar)} en la línea de este pedido">Usar ${cant(p.por_comprar)}</button>`;
                else res = `<span class="com-abast-sem ambar">Compra de más: ${cant(va - p.por_comprar)}</span>`;
                return `<tr class="${esta ? 'com-ab-esta' : 'com-ab-otro'}">
                    <td class="left"><b>${esc(p.numero)}</b><small>${esc(p.cliente || '')}</small></td>
                    <td class="num">${cant(p.pide)}</td>
                    <td class="num">${p.en_oc > 0 ? `${cant(p.en_oc)}<small title="${esc(p.ocs || '')}">${esc(p.ocs || '')}</small>` : '0'}</td>
                    <td class="num">${cant(p.stock_asignado)}</td>
                    <td class="num"><b>${cant(p.por_comprar)}</b></td>
                    <td class="num">${esta ? `<span class="com-abast-num comp">${cant(va)}</span>` : '—'}</td>
                    <td class="left">${res}</td></tr>`;
            };
            // Frase de arriba: lo que hace ESTA orden, en simple
            const frases = deEsta.map(p => {
                const va = enOrden(p.pedido_id);
                return va >= p.por_comprar - 1e-9
                    ? `<span class="com-ab-ok">✔ Esta orden cubre ${cant(va)} de ${esc(p.numero)}${va > p.por_comprar + 1e-9 ? ` (${cant(va - p.por_comprar)} de más)` : ''}</span>`
                    : `<span class="com-ab-mal">✖ A ${esc(p.numero)} le faltan ${cant(p.por_comprar - va)}: pide ${cant(p.pide)}, ya en otras OC ${cant(p.en_oc)}, stock asignado ${cant(p.stock_asignado)}</span>`;
            });
            if (paraStock > 0) frases.push(`<span class="com-ab-stock">Para stock - Sin PC (Pedido del cliente): ${cant(paraStock)}</span>`);
            if (!deEsta.length && !paraStock) frases.push('<span class="com-ab-stock">Esta línea no está unida a un pedido.</span>');
            const otrosTxt = otros.filter(p => p.por_comprar > 0);
            return `<div class="com-ab-prod">
                <div class="com-ab-head"><b>${esc(d.codigo || '')}</b> ${esc(d.descripcion || '')}
                    <span class="com-ab-stocktot">Stock libre en ${esc(nomEmp)}: <b>${cant(d.stock)}</b>${d.stock_grupo > d.stock ? ` · grupo ${cant(d.stock_grupo)}` : ''}</span></div>
                <div class="com-ab-frases">${frases.join('')}</div>
                ${pcs.length ? `<div class="table-wrap"><table class="inv-table com-abast-tabla">
                    <thead><tr><th class="left">N° PV · cliente</th><th>Pide</th><th>Ya en otras OC</th><th>Stock asignado<small>se reparte, el PV más antiguo primero</small></th>
                        <th>Falta comprar</th><th>En esta orden</th><th class="left">Resultado</th></tr></thead>
                    <tbody>${deEsta.map(p => filaPc(p, true)).join('')}${otros.map(p => filaPc(p, false)).join('')}</tbody></table></div>` : ''}
                ${otrosTxt.length ? `<div class="com-ab-nota">Hay ${otrosTxt.length} pedido(s) más de este producto sin comprar (${otrosTxt.map(p => `${esc(p.numero)}: ${cant(p.por_comprar)}`).join(', ')}). Haz otra orden o pulsa "Sumarlo aquí".</div>` : ''}
                <div class="com-ab-extra">Extra para stock (opcional, pide motivo):
                    <input type="number" class="inp-num com-abast-extra" min="0" step="any" value="${paraStock || ''}" placeholder="0" data-extra-pid="${pid}"
                        title="Si quieres comprar más de lo que piden los clientes, escribe aquí cuánto más (queda en stock y pide motivo)"></div>
            </div>`;
        }).join('');
        caja.innerHTML = `<div class="com-abast-tit">📊 Resumen de abastecimiento <small>${esc(emp.nombre || 'Empresa')} · se recalcula solo</small></div>${bloques}`;
    }

    // Botones del resumen: "Usar N" (pone lo que falta en la línea de ese pedido) y "Sumarlo aquí" (agrega otro pedido)
    function usarPedidoAbast(pid, pedidoId, agregar) {
        const d = abastDatos[pid];
        const p = d && (d.pedidos || []).find(x => String(x.pedido_id) === String(pedidoId));
        if (!p) return;
        const i = lineas.findIndex(l => l.producto_id === pid && String(l.pedido_id || '') === String(pedidoId));
        if (i >= 0) lineas[i].cantidad = p.por_comprar;
        else if (agregar) {
            const base = lineas.find(l => l.producto_id === pid) || {};
            lineas.push({ producto_id: pid, texto: base.texto || `${d.codigo} · ${d.descripcion}`, cantidad: p.por_comprar,
                          precio_unitario: base.precio_unitario || '', pedido_id: p.pedido_id, para: `${p.numero} · ${p.cliente || ''}`, max: p.falta });
        }
        pintarLineas();
        ajustarForm();
    }

    // "Extra para stock" del panel (pedido de Erika 20/10/2026): una línea aparte "Para stock · sin pedido"
    // del mismo producto, así lo del cliente y lo de más quedan separados y la compra extra pide motivo.
    function ponerExtraStock(pid, valor) {
        const extra = Math.max(Number(valor) || 0, 0);
        const base = lineas.find(l => l.producto_id === pid);
        if (!base) return;
        const deStock = lineas.map((l, i) => [l, i]).filter(([l]) => l.producto_id === pid && !l.pedido_id);
        const conPedido = lineas.some(l => l.producto_id === pid && l.pedido_id);
        if (!conPedido && deStock.length && extra === 0) {
            aviso('Esta línea no es de un pedido de cliente: cambia la cantidad en la tabla de productos.', 'warning');
            pintarAbastecimiento();
            return;
        }
        if (deStock.length) {
            const [, i0] = deStock[0];
            const otras = deStock.slice(1).reduce((s, [l]) => s + (Number(l.cantidad) || 0), 0);
            if (extra === 0 && conPedido) {
                lineas = lineas.filter(l => !(l.producto_id === pid && !l.pedido_id));
            } else {
                lineas[i0].cantidad = Math.max(extra - otras, 0);
            }
        } else if (extra > 0) {
            lineas.push({ producto_id: pid, texto: base.texto, cantidad: extra, precio_unitario: base.precio_unitario || '',
                          pedido_id: null, para: '' });
        }
        pintarLineas();
        ajustarForm();
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

    // Regla de ahorro (Erika 28/10/2026): KCF paga a la cuenta BBVA del proveedor y AGD a la BCP (mismo banco, sin
    // comisión). Si no tiene, la siguiente cuenta registrada, con aviso en rojo. Igual que routes/cuentas_proveedor.py
    function cuentaPreferida(p, empresaId, moneda) {
        const lista = (p && p.cuentas) || [];
        if (!lista.length) return null;
        const emp = cat.empresas.find(e => String(e.id) === String(empresaId)) || {};
        const nombre = emp.nombre || emp.codigo || 'la empresa';
        const banco = (cat.bancosEmpresa || {})[String(empresaId)] || '';
        const primera = cands => (moneda && cands.find(c => c.moneda === moneda)) || cands[0];
        const mismas = banco ? lista.filter(c => String(c.banco || '').toUpperCase() === banco.toUpperCase()) : [];
        const c = Object.assign({}, primera(mismas.length ? mismas : lista), { mismo_banco: mismas.length > 0, total: lista.length });
        c.aviso = !banco ? '' : mismas.length ? `✅ Cuenta ${banco}: mismo banco que ${nombre}, sin comisión.`
            : `⚠️ El proveedor no tiene cuenta ${banco} (banco de ${nombre}): se paga a su cuenta ${c.banco || 'de otro banco'}. El banco puede cobrar comisión.`;
        return c;
    }

    function pintarProveedor() {
        const p = provElegido;
        // Datos del proveedor (proveedores + contacto principal de proveedores_contactos), solo lectura
        const campos = { ocProvRazon: 'razon_social', ocProvRuc: 'ruc', ocProvDireccion: 'direccion', ocProvContacto: 'contacto',
                         ocProvTelefono: 'telefono', ocProvEmail: 'email' };
        Object.entries(campos).forEach(([id, k]) => { if ($(id)) $(id).value = p ? (p[k] || '') : ''; });
        if (!p) { $('ocProvInfo').innerHTML = ''; return; }
        const c = cuentaPreferida(p, $('ocEmp').value, Moneda.leer('oc').moneda);
        $('ocProvInfo').innerHTML = `<div class="com-prov-card">
            <b>${esc(p.razon_social)}</b> · RUC ${esc(p.ruc || '—')}<br>
            ${esc(p.direccion || '')}${p.contacto ? ' · ' + esc(p.contacto) : ''}${p.telefono ? ' · ' + esc(p.telefono) : ''}<br>
            ${c ? `🏦 Se pagará a: <b>${esc(c.banco || '')}</b> ${esc(c.numero_cuenta || '')} ${c.cci ? 'CCI ' + esc(c.cci) : ''}
                   <small>(cuenta ${c.orden} de ${c.total})</small>
                   ${c.aviso ? `<div class="${c.mismo_banco ? 'com-cuenta-ok' : 'com-cuenta-otra'}">${esc(c.aviso)}</div>` : ''}`
                : '<span class="neg">⚠️ Este proveedor no tiene cuenta bancaria registrada. Pídela y regístrala en Maestros ▸ Proveedores antes de pagar.</span>'}
        </div>`;
    }

    // 22/10/2026 (buscador "no hace nada"): la lista de resultados se abría DEBAJO de la casilla y la
    // ventana la cortaba (quedaba escondida detrás del pie "Cancelar / Guardar borrador"). Ahora flota
    // sobre todo y, si abajo no hay espacio, se abre hacia arriba.
    function mostrarLista(input, lista) {
        const r = input.getBoundingClientRect();
        const abajo = window.innerHeight - r.bottom, alto = Math.min(260, Math.max(abajo, r.top) - 16);
        lista.style.position = 'fixed';
        lista.style.left = r.left + 'px';
        lista.style.width = Math.max(r.width, 320) + 'px';
        lista.style.right = 'auto';
        lista.style.maxHeight = alto + 'px';
        lista.style.zIndex = '100000';
        if (abajo >= Math.min(260, lista.scrollHeight + 8) || abajo >= r.top) {
            lista.style.top = (r.bottom + 2) + 'px'; lista.style.bottom = 'auto';
        } else {
            lista.style.top = 'auto'; lista.style.bottom = (window.innerHeight - r.top + 2) + 'px';
        }
        lista.style.display = 'block';
    }
    document.addEventListener('scroll', e => {
        if (e.target && e.target.closest && e.target.closest('#ocModal')) {
            document.querySelectorAll('#ocModal .pp-lista').forEach(l => { l.style.display = 'none'; });
        }
    }, true);

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
            mostrarLista(input, lista);
        });
        lista.addEventListener('click', e => {
            const op = e.target.closest('.pp-op');
            if (!op) return;
            provElegido = cat.proveedores.find(p => p.id === Number(op.dataset.id));
            input.value = `${provElegido.ruc || ''} · ${provElegido.razon_social}`;
            el.classList.add('pp-ok');
            lista.style.display = 'none';
            const cp = condPagoPartes(provElegido.condicion_pago);
            if (cp.tipo === 'Crédito') {
                $('ocCondicion').value = 'Crédito';
                const dias = cp.dias || parseInt(String(provElegido.tiempo_credito || '').replace(/\D/g, ''), 10);
                if (dias) $('ocDias').value = dias;
            }
            pintarProveedor();
            ajustarForm();
        });
        document.addEventListener('click', e => { if (!el.contains(e.target)) lista.style.display = 'none'; });
    }

    function pintarLineas() {
        $('ocLineas').innerHTML = lineas.map((l, i) => `<tr data-linea="${i}">
            <td class="com-item">${i + 1}</td>
            <td class="left">${l.pedido_id
                ? `<b>${esc(l.texto)}</b>`
                : `<div class="prod-picker com-pp" data-linea-pp="${i}"><input type="search" class="pp-input" value="${esc(l.texto)}" placeholder="Buscar producto..." autocomplete="off"><div class="pp-lista"></div></div>`}
                <div class="com-info-linea" id="info-${i}"></div></td>
            <td class="left">${l.pedido_id ? `<span class="com-para">${esc(l.para)}</span>` : '<span class="badge-sin-pedido">Para stock - Sin PC (Pedido del cliente)</span>'}</td>
            <td><input type="number" class="inp-num" data-campo="cantidad" min="0" step="any" value="${esc(l.cantidad)}">${l.max ? `<small>máx. ${cant(l.max)}</small>` : ''}</td>
            <td><input type="number" class="inp-num" data-campo="precio_unitario" min="0" step="0.01" value="${esc(l.precio_unitario)}"></td>
            <td class="num com-tot-linea" id="tot-${i}">${soles((Number(l.cantidad) || 0) * (Number(l.precio_unitario) || 0))}</td>
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
                lista.innerHTML = '<div class="pp-nada">⏳ Buscando...</div>';
                mostrarLista(input, lista);
                try {
                    const { data } = await api('/inventario/api/productos?q=' + encodeURIComponent(q));
                    if (input.value.trim() !== q) return;   // ya escribió otra cosa
                    lista.innerHTML = (data || []).length ? data.map(x => `<div class="pp-op" data-id="${x.id}" data-txt="${esc((x.codigo || '') + ' · ' + x.descripcion)}">
                        <b>${esc(x.codigo || '')}</b> ${esc(x.descripcion)} <small>${esc([x.marca, x.modelo, x.unidad].filter(Boolean).join(' · '))}</small></div>`).join('')
                        : '<div class="pp-nada">No se encontró. Créalo en Productos.</div>';
                    mostrarLista(input, lista);
                } catch (e) {
                    // Antes el error se escondía y parecía que el buscador "no hacía nada"
                    lista.innerHTML = `<div class="pp-nada" style="color:#B91C1C;font-weight:700">⛔ No se pudo buscar: ${esc(e.message)}</div>`;
                    mostrarLista(input, lista);
                }
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

    function totalOC() {
        const sub = lineas.reduce((s, l) => s + (Number(l.cantidad) || 0) * (Number(l.precio_unitario) || 0), 0);
        return Math.round(sub * 100) / 100 + Math.round(sub * IGV * 100) / 100;
    }

    // Adelanto (24/10 y 27/10/2026): cuánto se paga antes y cuánto queda para Finanzas
    function textoAdelanto() {
        const t = $('ocAdelantoTxt');
        if (!t) return;
        const cond = $('ocCondicion').value;
        const pct = cond === 'Adelanto 50%' ? 50 : (Number($('ocAdelantoPct').value) || 0);
        if (!pct) { t.textContent = ''; return; }
        const m = Moneda.leer('oc').moneda, tot = totalOC(), adel = Math.round(tot * pct) / 100;
        const dias = Number($('ocDias').value) || 0;
        const cuando = cond === 'Crédito' && dias ? ` a crédito ${dias} días` : (cond === 'Contra entrega' ? ' con la entrega' : '');
        t.textContent = `Adelanto ${pct}%: ${dinero(m, adel)} · Saldo ${100 - pct}%${cuando}: ${dinero(m, Math.round((tot - adel) * 100) / 100)}`;
    }

    function totales() {
        const sub = lineas.reduce((s, l) => s + (Number(l.cantidad) || 0) * (Number(l.precio_unitario) || 0), 0);
        const igv = Math.round(sub * IGV * 100) / 100;
        const { moneda, tipo_cambio } = Moneda.leer('oc');
        $('ocSub').textContent = dinero(moneda, sub);
        $('ocIgv').textContent = dinero(moneda, igv);
        $('ocTot').textContent = dinero(moneda, Math.round(sub * 100) / 100 + igv);
        textoAdelanto();
        $('ocTotSoles').textContent = moneda === 'USD' && Number(tipo_cambio) > 0
            ? `≈ ${soles((Math.round(sub * 100) / 100 + igv) * Number(tipo_cambio))} (TC ${Number(tipo_cambio).toFixed(3)})` : '';
    }

    async function guardarOC(enviar, btn) {
        if (!provElegido) { aviso('Elige el proveedor de la lista.', 'error'); return; }
        const items = lineas.filter(l => l.producto_id || l.texto).map(l => ({ producto_id: l.producto_id, cantidad: l.cantidad,
            precio_unitario: l.precio_unitario, pedido_id: l.pedido_id }));
        if (items.some(i => !i.producto_id)) { aviso('Hay un producto escrito a mano. Elígelo de la lista que aparece al escribir.', 'error'); return; }
        const mon = Moneda.leer('oc');
        if (mon.moneda === 'USD' && !(Number(mon.tipo_cambio) > 0)) { aviso('La orden es en dólares: escribe el tipo de cambio.', 'error'); $('ocTC').focus(); return; }
        const body = {
            id: $('ocId').value || null, empresa_id: $('ocEmp').value, proveedor_id: provElegido.id,
            condicion_pago: $('ocCondicion').value, dias_credito: $('ocDias').value, adelanto_pct: $('ocAdelantoPct').value, modalidad_entrega: $('ocModalidad').value,
            direccion_recojo: $('ocRecojo').value, almacen_entrega_id: $('ocSede').value, fecha_compromiso: $('ocFecha').value,
            num_cotizacion: $('ocCotizacion').value, notas: $('ocNotas').value, nota_interna: $('ocNotaInterna').value,
            motivo_compra: $('ocMotivoCompra').value, motivo_stock: $('ocMotivo').value.trim(), items, enviar,
            moneda: mon.moneda, tipo_cambio: mon.tipo_cambio
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
            await verOrden(r.id);
            cartelSiguiente(r.id, `✅ ¡Orden ${esc(r.numero || '')} ${enviar ? 'enviada' : 'guardada'}!`);
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
            $('detTitulo').innerHTML = `${esc(o.numero)} ${estadoOC(o.estado)}`;
            const pd = o.proveedor_datos || {};
            $('detCuerpo').innerHTML = `
                ${o.flujo === 'v2' ? `<div class="com-stepper">${PASOS.map((p, i) => `<div class="com-step ${o.estado === 'Anulada' ? 'anulada' : ep[p.k]}"><span>${ep[p.k] === 'hecho' ? '✓' : i + 1}</span><b>${p.t}</b></div>`).join('')}</div>` : ''}
                <div class="com-relacion-pc">${o.pc_numeros ? `🔗 Relacionado al PV: <b>${esc(o.pc_numeros)}</b>${o.cotizaciones_cliente ? ` · N° cotización <b>${esc(o.cotizaciones_cliente)}</b>` : ''}` : '📦 Compra directa a stock (Sin PV)'}</div>
                <div class="com-siguiente com-paso-${o.paso.codigo}">👉 <b>Siguiente paso:</b> ${esc(o.paso.texto)} <small>(${esc(o.paso.quien)})</small></div>
                ${(o.avisos || []).map(a => `<div class="inv-aviso">⚠️ ${esc(a)}</div>`).join('')}
                ${o.motivo_anulacion ? `<div class="inv-alerta danger">Anulada: ${esc(o.motivo_anulacion)}</div>` : ''}
                ${o.motivo_compra ? `<div class="com-sin-pedido"><div class="com-sin-pedido-tit">⚠️ ${o.items.every(i => !i.pedido_id) ? 'Compra solo para stock (sin PC del cliente)' : 'Incluye compra para stock'} · Motivo: ${esc(o.motivo_compra)}${o.motivo_stock && o.motivo_stock !== o.motivo_compra ? ' · ' + esc(o.motivo_stock) : ''}</div></div>` : ''}
                ${o.pc_numeros || o.clientes_pedido ? `<div class="inv-tip com-interno">🔒 <b>Solo interno</b> (no sale en la orden del proveedor): corresponde a
                    <b>${esc(o.pc_numeros || '')}</b>${o.cotizaciones_cliente ? ` · Cotización ${esc(o.cotizaciones_cliente)}` : ''}${o.clientes_pedido ? ` · Cliente ${esc(o.clientes_pedido)}` : ''}</div>` : ''}
                <div class="com-datos">
                    <div><small>Empresa que compra</small><b>${esc(o.empresa || '—')}</b></div>
                    <div><small>Proveedor</small><b>${esc(o.proveedor || '')}</b><span>RUC ${esc(o.ruc || '—')}</span></div>
                    <div><small>Condición de pago</small><b>${esc(condPagoMostrar(o.condicion_pago, o.dias_credito))}</b>${Number(o.adelanto_pct) > 0 && !/adelanto/i.test(o.condicion_pago || '') ? `<span>Adelanto ${Number(o.adelanto_pct)}% antes de la entrega: ${dinero(o.moneda, o.adelanto)}</span>` : ''}</div>
                    <div><small>Cómo llega</small><b>${esc(o.modalidad_entrega || '')}</b><span>${esc(o.direccion_recojo || '')}</span></div>
                    <div><small>Debe quedar en</small><b>${esc(o.sede || '—')}</b><span>Fecha prometida ${fecha(o.fecha_compromiso)}${o.atrasada ? ' · <b class="neg">ATRASADA</b>' : ''}</span></div>
                    <div><small>Tipo</small><b>${esc(o.tipo_compra || '')}</b><span>${esc(o.motivo_stock || '')}</span></div>
                    <div><small>Hizo la orden</small><b>${esc(o.creado_por_nombre || '—')}</b><span>${fecha(o.fecha)}</span></div>
                    <div><small>Aprobó</small><b>${esc(o.aprobado_por || '—')}</b><span>${fecha(o.aprobado_en)}</span></div>
                    <div><small>Total</small><b>${dinero(o.moneda, o.total)}</b><span>Pagado ${dinero(o.moneda, o.pagado)} · Facturado ${dinero(o.moneda, o.facturado)}${o.moneda === 'USD' && o.tipo_cambio ? ` · TC ${Number(o.tipo_cambio).toFixed(3)} ≈ ${soles(Number(o.total) * Number(o.tipo_cambio))}` : ''}</span></div>
                </div>
                ${o.notas ? `<div class="inv-tip">📝 <b>Nota para el proveedor:</b> ${esc(o.notas)}</div>` : ''}
                ${o.nota_interna ? `<div class="inv-tip com-nota-interna">🔒 <b>Nota interna (no la ve el proveedor):</b> ${esc(o.nota_interna)}</div>` : ''}
                <div class="inv-subtitulo">Productos</div>
                <div class="table-wrap"><table class="inv-table inv-mini">
                    <thead><tr><th class="com-item">Ítem</th><th>Código de producto</th><th class="left">Nombre producto</th><th class="left">Para</th><th>Pedido</th><th>Llegó</th><th>Precio sin IGV</th><th>Total</th></tr></thead>
                    <tbody>${o.items.map((i, n) => `<tr class="${Number(i.cantidad_recibida) < Number(i.cantidad) && o.estado === 'Recibida parcial' ? 'fila-dif' : ''}">
                        <td class="com-item">${n + 1}</td><td>${esc(i.codigo || '')}</td><td class="left">${esc(i.producto)}</td>
                        <td class="left">${i.pedido_id ? `${esc(i.cliente || '')}<small>${esc(i.pedido_numero || '')}${i.cotizacion_numero ? ' · Cot. ' + esc(i.cotizacion_numero) : ''}</small>` : '<span class="badge-sin-pedido">Para stock - Sin PC (Pedido del cliente)</span>'}</td>
                        <td class="num">${cant(i.cantidad)} ${esc(i.unidad || '')}</td><td class="num">${cant(i.cantidad_recibida)}</td>
                        <td class="num">${dinero(o.moneda, i.precio_unitario)}</td><td class="num">${dinero(o.moneda, i.total)}</td></tr>`).join('')}</tbody>
                    <tfoot><tr><td colspan="7" class="num">Subtotal ${dinero(o.moneda, o.subtotal)} · IGV ${dinero(o.moneda, o.igv)} · <b>Total</b></td><td class="num"><b>${dinero(o.moneda, o.total)}</b></td></tr></tfoot>
                </table></div>
                ${o.incidencias.length ? `<div class="inv-subtitulo">Diferencias</div><div class="table-wrap"><table class="inv-table inv-mini">
                    <thead><tr><th class="com-item">Ítem</th><th>N° diferencia</th><th>Tipo</th><th class="left">Detalle</th><th>Monto</th><th>Estado</th><th class="left">Cómo se resolvió</th><th></th></tr></thead>
                    <tbody>${o.incidencias.map((i, n) => `<tr><td class="com-item">${n + 1}</td><td>${esc(i.numero)}</td><td><b>${esc(i.tipo)}</b></td><td class="left">${esc(i.detalle)}<small>Reportó ${esc(i.reportado_por || '')} · ${fecha(i.fecha)}</small></td>
                        <td class="num">${i.monto ? soles(i.monto) : ''}</td><td><span class="${claseEstado(i.estado === 'Abierta' ? 'pendiente' : 'registrado')}">${esc(i.estado)}</span></td>
                        <td class="left">${esc(i.resolucion || '')}${i.resuelto_por ? `<small>${esc(i.resuelto_por)}</small>` : ''}</td>
                        <td>${i.estado === 'Abierta' && PUEDE.aprobar ? `<button class="btn-mini" data-resolver="${i.id}">Resolver</button>` : ''}</td></tr>`).join('')}</tbody></table></div>` : ''}
                <div class="com-columnas">
                    <div><div class="inv-subtitulo">Pagos</div>${o.pagos.length ? o.pagos.map(p => `<div class="com-mov">💸 <b>${dinero(o.moneda, p.monto)}</b>${p.moneda_pago && p.moneda_pago !== (o.moneda || 'PEN') ? ` (pagado ${dinero(p.moneda_pago, p.monto_pagado)} · TC ${Number(p.tipo_cambio).toFixed(3)})` : ''} · ${esc(p.metodo || '')} ${esc(p.banco || '')} · Op. ${esc(p.numero_operacion || '—')}<small>${fecha(p.fecha)} · ${esc(p.usuario_nombre || '')}</small></div>`).join('') : '<div class="inv-tip">Sin pagos.</div>'}
                        ${pd.numero_cuenta || pd.cci ? `<div class="inv-tip">🏦 Se paga a: ${esc(pd.banco || '')} ${esc(pd.numero_cuenta || '')} ${pd.cci ? 'CCI ' + esc(pd.cci) : ''}${pd.cuenta_aviso ? `<div class="${pd.cuenta_mismo_banco ? 'com-cuenta-ok' : 'com-cuenta-otra'}">${esc(pd.cuenta_aviso)}</div>` : ''}</div>` : ''}</div>
                    <div><div class="inv-subtitulo">Recepciones</div>${o.recepciones.length ? o.recepciones.map(r => `<div class="com-mov">📦 <b>${esc(r.numero)}</b> · Guía ${esc(r.guia_proveedor)} · ${esc(r.sede || '')}${r.con_diferencias ? ' · <b class="neg">con diferencias</b>' : ''}<small>Trajo: ${esc(r.traido_por || '')} · Recibió: ${esc(r.recibido_por || '')} · ${fecha(r.fecha)}</small></div>`).join('') : '<div class="inv-tip">Todavía no llega nada.</div>'}</div>
                    <div><div class="inv-subtitulo">Facturas</div>${o.facturas.length ? o.facturas.map(f => `<div class="com-mov">🧾 <b>${esc(f.tipo)} ${esc(f.numero)}</b> · ${dinero(f.moneda, f.monto)}${f.moneda === 'USD' && f.tipo_cambio ? ` · TC ${Number(f.tipo_cambio).toFixed(3)}` : ''} ${f.cuadra === false ? '<b class="neg">no cuadra</b>' : '✔'}<small>${fecha(f.fecha)} · vence ${fecha(f.fecha_vencimiento)} · ${esc(f.estado || '')}</small></div>`).join('') : '<div class="inv-tip">Sin factura.</div>'}</div>
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
            // Erika 25/10/2026: las OC a crédito solo las aprueba la administradora
            if (!o.solo_admin_aprueba || PUEDE.admin) b.push(`<button class="btn btn-primary" data-accion="aprobar">✔ Aprobar</button>`);
            else b.push(`<span class="inv-tip">A crédito: la aprueba Erika</span>`);
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
            await guardarCon(btn, async () => { const r = await post(`/compras/api/flujo/ordenes/${o.id}/enviar`); aviso(r.message, 'success'); refrescar(); await verOrden(o.id); cartelSiguiente(o.id, `✅ ¡Orden ${esc(o.numero)} enviada a aprobar!`); });
        } else if (accion === 'aprobar') {
            await guardarCon(btn, async () => { const r = await post(`/compras/api/flujo/ordenes/${o.id}/aprobar`, { aprobar: true }); aviso(r.message, 'success'); refrescar(); await verOrden(o.id); cartelSiguiente(o.id, `✅ ¡Orden ${esc(o.numero)} aprobada!`); });
        } else if (accion === 'devolver') {
            pedirMotivo('Devolver para corregir', 'Escribe qué hay que corregir. La orden vuelve a Borrador.', async m => {
                const r = await post(`/compras/api/flujo/ordenes/${o.id}/aprobar`, { aprobar: false, motivo: m }); aviso(r.message, 'success'); refrescar(); await verOrden(o.id); cartelSiguiente(o.id, `↩ Orden ${esc(o.numero)} devuelta para corregir`, { texto: 'Quien la hizo debe pulsar <b>"✏️ Corregir"</b> en la orden y volver a enviarla.' });
            });
        } else if (accion === 'anular') {
            pedirMotivo('Anular orden', 'La orden queda anulada (no se borra) y los pedidos de sus clientes vuelven a "por comprar".', async m => {
                const r = await post(`/compras/api/flujo/ordenes/${o.id}/anular`, { motivo: m }); aviso(r.message, 'success'); refrescar(); await verOrden(o.id); cartelSiguiente(o.id, `✔ Orden ${esc(o.numero)} anulada`);
            });
        } else if (accion === 'faltante') {
            pedirMotivo('Cerrar con faltante', 'Lo que falta quedará como diferencia por resolver (nota de crédito o devolución del dinero). Explica qué dijo el proveedor.', async m => {
                const r = await post(`/compras/api/flujo/ordenes/${o.id}/cerrar_faltante`, { motivo: m }); aviso(r.message, 'success'); refrescar(); await verOrden(o.id); cartelSiguiente(o.id, `✔ Orden ${esc(o.numero)} cerrada con faltante`);
            });
        } else if (accion === 'pagar') { cerrar('detModal'); abrirPago(o); }
        else if (accion === 'recibir') { cerrar('detModal'); abrirRecepcion(o.id); }
        else if (accion === 'factura') { cerrar('detModal'); abrirFactura(o); }
    }

    // ========================================================
    // PAGO
    // ========================================================
    // Cuentas escritas "de relleno" al registrar al proveedor (1111..., 5555444488889999, 123123...)
    function cuentaDeRelleno(...nums) {
        return nums.some(n => { const d = String(n || '').replace(/\D/g, '');
            return d && (/(\d)\1{5,}/.test(d) || /(\d{2,4})\1{3,}/.test(d) || d === '5555444488889999'); });
    }

    function abrirPago(o) {
        $('pagoOc').value = o.id;
        $('pagoTitulo').textContent = `Registrar pago · ${o.numero}`;
        // 28/10/2026: la cuenta ya viene elegida por el servidor según la empresa de la OC (KCF BBVA, AGD BCP)
        const p = (o.proveedor_datos && Object.keys(o.proveedor_datos).length ? o.proveedor_datos : null)
            || cat.proveedores.find(x => x.id === o.proveedor_id) || {};
        let falta = Math.max(Number(o.total) - Number(o.pagado), 0);
        // Adelanto: primero se sugiere solo lo que falta del adelanto; el saldo se paga con la factura
        const conAdelanto = Number(o.adelanto_pct) > 0 && Number(o.falta_adelanto) > 0;
        if (conAdelanto) falta = Number(o.falta_adelanto);
        // Un dato por línea y siempre en el mismo orden (pedido de Erika 21/10 17:22)
        const fila = (et, val, cls = '') => `<div class="fd-et">${et}</div><div class="fd-val ${cls}">${val}</div>`;
        const tieneCuenta = p.numero_cuenta || p.cci;
        $('pagoCuenta').innerHTML = `<div class="ficha-datos fd-pago">
            <div class="fd-titulo">Pagar a</div>
            ${fila('Proveedor', esc(o.proveedor || '—'))}
            ${fila('RUC / DNI', esc(o.ruc || '—'), 'fd-num')}
            ${fila('Banco', esc(p.banco || '—'))}
            ${fila('N° de cuenta', esc(p.numero_cuenta || '—'), 'fd-num')}
            ${fila('CCI', esc(p.cci || '—'), 'fd-num')}
            ${p.cuenta_aviso ? `<div class="fd-nota ${p.cuenta_mismo_banco ? 'fd-ok-nota' : 'fd-alerta fd-comision'}">${esc(p.cuenta_aviso)}</div>` : ''}
            ${fila('Monto a pagar (incluye IGV)', dinero(o.moneda, o.total), 'fd-monto')}
            ${conAdelanto ? fila(`Adelanto ${Number(o.adelanto_pct)}% (pagar ahora)`, dinero(o.moneda, o.adelanto), 'fd-monto') : ''}
            ${fila(conAdelanto ? 'Falta del adelanto' : 'Falta pagar', dinero(o.moneda, falta), 'fd-monto ' + (falta > 0 ? 'fd-falta' : 'fd-ok'))}
            ${cuentaDeRelleno(p.numero_cuenta, p.cci) ? '<div class="fd-nota fd-alerta">⚠️ La cuenta o el CCI parecen de relleno (números repetidos). Confírmalos con el proveedor y corrígelos en Maestros ▸ Proveedores antes de pagar.</div>' : ''}
            ${tieneCuenta ? '<div class="fd-nota">Paga solo a esta cuenta. Si el proveedor te pide pagar a otra, consulta con tu supervisora.</div>'
                : '<div class="fd-nota fd-alerta">⚠️ El proveedor no tiene cuenta registrada. Regístrala en Maestros ▸ Proveedores antes de pagar.</div>'}
        </div>`;
        $('pagoMonto').value = falta.toFixed(2);
        prepararMonedaPago(o, falta);
        $('pagoFecha').value = hoyISO();
        $('pagoMetodo').value = 'Transferencia';
        ['pagoBanco', 'pagoOperacion', 'pagoObs'].forEach(i => { $(i).value = ''; });
        abrir('pagoModal');
    }

    // Pago de una OC en dólares (pedido de Erika 24/10/2026): el proveedor da su tipo de cambio para pagarle en soles.
    // Solo se puede pagar en dólares si la empresa tiene cuenta en dólares (KCF solo soles; AGD soles y dólares).
    let pagoDoc = { moneda: 'PEN', falta: 0 };
    function prepararMonedaPago(o, falta) {
        const doc = Moneda.codigo(o.moneda);
        const cuentas = (cat.monedasCuenta || {})[String(o.empresa_id)] || ['PEN'];
        pagoDoc = { moneda: doc, falta };
        $('pagoMonedaWrap').style.display = doc === 'USD' ? '' : 'none';
        const sel = $('pagoMonedaPago');
        sel.querySelector('option[value="USD"]').disabled = !cuentas.includes('USD');
        sel.value = 'PEN';
        $('pagoMonedaInfo').textContent = doc === 'USD' && !cuentas.includes('USD')
            ? 'Esta empresa no tiene cuenta en dólares: se paga en soles con el TC del proveedor.' : '';
        $('pagoTC').value = '';
        pintarMonedaPago(true);
    }
    async function pintarMonedaPago(nuevo) {
        const doc = pagoDoc.moneda, pago = doc === 'USD' ? $('pagoMonedaPago').value : doc;
        const conTC = pago !== doc;
        $('pagoTCWrap').style.display = conTC ? '' : 'none';
        $('pagoMontoEt').textContent = `Monto pagado (${pago === 'USD' ? 'US$' : 'S/'})`;
        if (conTC && !$('pagoTC').value) {
            const tc = await Moneda.tcSunat($('pagoFecha').value || hoyISO());
            if (tc && !$('pagoTC').value) $('pagoTC').value = tc.toFixed(3);
            nuevo = true;
        }
        const tc = Number($('pagoTC').value);
        if (nuevo) $('pagoMonto').value = (conTC ? (tc > 0 ? pagoDoc.falta * tc : 0) : pagoDoc.falta).toFixed(2);
        equivPago();
    }
    function equivPago() {
        const doc = pagoDoc.moneda, pago = doc === 'USD' ? $('pagoMonedaPago').value : doc;
        const tc = Number($('pagoTC').value), m = Number($('pagoMonto').value);
        $('pagoEquiv').textContent = pago !== doc
            ? (tc > 0 ? `Se descuenta ${dinero(doc, doc === 'USD' ? m / tc : m * tc)} de la deuda en ${doc === 'USD' ? 'dólares' : 'soles'}.` : 'Escribe el tipo de cambio que te dio el proveedor.')
            : '';
    }
    function montoPagoDoc() {
        const doc = pagoDoc.moneda, pago = doc === 'USD' ? $('pagoMonedaPago').value : doc;
        const tc = Number($('pagoTC').value), m = Number($('pagoMonto').value);
        if (pago === doc) return m;
        return tc > 0 ? Math.round((doc === 'USD' ? m / tc : m * tc) * 100) / 100 : 0;
    }

    // ========================================================
    // RECEPCIÓN A CIEGAS
    // ========================================================
    // 22/10/2026 (Erika): cada recojo tiene responsable, para que no se olvide; se guarda con fecha y hora
    function celdaResponsable(o) {
        // 22/10/2026 (Erika): quién asignó y cuándo se guarda en la base, pero no se muestra (no sobrecargar)
        const quien = '';
        if (!(PUEDE.comprar || PUEDE.recibir || PUEDE.admin)) {
            return o.responsable_recojo ? `<small class="com-resp-nombre">Recoge: ${esc(o.responsable_recojo)}</small>` : '<small class="neg">Sin responsable</small>';
        }
        const ops = cat.usuarios.map(u => `<option value="${u.id}"${Number(u.id) === Number(o.responsable_recojo_id) ? ' selected' : ''}>${esc(u.nombre)}</option>`).join('');
        return `<select class="com-resp${o.responsable_recojo_id ? '' : ' com-resp-falta'}" data-resp-oc="${o.id}"><option value="">¿Quién recoge?</option>${ops}</select>${quien}`;
    }

    async function guardarResponsable(sel) {
        sel.disabled = true;
        try {
            const r = await post(`/compras/api/flujo/ordenes/${sel.dataset.respOc}/responsable_recojo`, { usuario_id: sel.value ? Number(sel.value) : null });
            aviso(r.mensaje, 'success');
            cargarRecibir();
        } catch (e) { aviso(e.message, 'error'); sel.disabled = false; }
    }

    async function cargarRecibir() {
        try {
            const data = aplicarFiltroVer('recibir', (await api('/compras/api/flujo/por_recibir')).data);
            $('recBodyCom').innerHTML = data.length ? data.map(o => {
                let accion;
                if (o.estado === 'Por aprobar') accion = '<span class="inv-tip">Falta aprobar</span>';
                else if (o.paso.codigo === 'pagar') accion = '<span class="inv-tip">🔒 Falta el pago</span><small class="com-pago-nota">Es al contado: Finanzas paga primero y luego se recoge</small>';
                else if (!PUEDE.recibir) accion = '—';
                else if (o.usuario_id === cat.usuarioId && !PUEDE.admin) accion = '<span class="inv-tip">Tú hiciste la orden: la recibe otra persona</span>';
                else accion = `<button class="btn-mini" data-recibir="${o.id}">📦 Recibir</button>`;
                // Intercompany (el proveedor es otra empresa del grupo): se recibe aunque falte el pago (22/10/2026)
                if (o.falta_pago_intercompany && o.paso.codigo === 'recibir') accion += '<small class="com-pago-nota">Intercompany: falta el pago</small>';
                return `<tr><td><button class="btn-link" data-ver="${o.id}">${esc(o.numero)}</button></td><td><b>${esc(o.empresa || '')}</b></td><td class="left">${esc(o.proveedor || '')}</td>
                    <td>${o.modalidad_entrega === 'Nosotros recogemos' ? `<span class="com-recojo">🚚 Recogemos</span><small>${esc(o.direccion_recojo || '')}</small>${celdaResponsable(o)}` : 'Proveedor entrega'}</td>
                    <td>${esc(o.sede || '')}</td><td>${fecha(o.fecha_compromiso)}${o.atrasada ? '<small class="neg">ATRASADA</small>' : ''}</td>
                    <td class="left">${esc(o.clientes || 'Stock')}</td><td>${estadoOC(o.estado)}</td><td>${accion}</td></tr>`;
            }).join('') : '<tr><td colspan="9">No hay mercadería por llegar.</td></tr>';
        } catch (e) { $('recBodyCom').innerHTML = `<tr><td colspan="9">${esc(e.message)}</td></tr>`; }
    }

    // A qué va cada línea: PV y cliente, o para stock (sin PC del cliente)
    function paraLinea(i) {
        return i.pedido_id || i.pedido_numero
            ? `<span class="com-para">${esc(i.pedido_numero || '')}${i.cliente ? ' · ' + esc(i.cliente) : ''}</span>`
            : '<span class="badge-sin-pedido">Para stock - Sin PC (Pedido del cliente)</span>';
    }

    async function abrirRecepcion(id) {
        try {
            const r = await api(`/compras/api/flujo/ordenes/${id}/para_recibir`);
            const o = r.orden;
            window._recOrden = o;
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
            // Erika 28/10/2026: "Ítem" primero y "Para" (a qué PV va o si es para stock), para no confundir líneas del mismo producto
            $('recItems').innerHTML = r.items.map((i, n) => `<tr data-item="${i.id}">
                <td class="com-item">${n + 1}</td>
                <td>${esc(i.codigo || '')}</td><td class="left"><b>${esc(i.producto)}</b><small>${esc([i.marca, i.modelo, i.unidad].filter(Boolean).join(' · '))}</small></td>
                <td class="left">${paraLinea(i)}<small>Faltan llegar: <b>${cant(i.falta)}</b> ${esc(i.unidad || '')}</small></td>
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

    // Pedido de Erika 22/10/2026 12:21: lo contado no coincide con la OC → ventana clara ANTES de grabar
    function ventanaDiferencias(difs) {
        return new Promise(resolve => {
            document.getElementById('ventanaDifRec')?.remove();
            const f = document.createElement('div');
            f.id = 'ventanaDifRec';
            f.style.cssText = 'position:fixed;inset:0;background:rgba(15,23,42,.55);z-index:100000;display:flex;align-items:center;justify-content:center;padding:16px';
            // Erika 28/10/2026 00:31: aviso contundente, en viñetas, azul = datos de la OC, rojo = la diferencia
            const o = window._recOrden || {};
            const uni = (u) => (!u || /^(ZZ|NIU|UND|UNIDAD|UNIDADES)$/i.test(u)) ? 'unidades' : u;
            const n = (x) => Number(x || 0).toLocaleString('es-PE', { maximumFractionDigits: 2 });
            const filas = difs.map(x => {
                const u = uni(x.unidad);
                if (x.tipo === 'Dañado') return `<li><b>${esc(x.producto)}</b>: <b class="aviso-rojo-txt">${n(x.danada)} ${esc(u)} dañados</b></li>`;
                const reg = Number(x.registras || 0) + Number(x.danada || 0);
                const dif = Math.abs(Number(x.pide || 0) - reg);
                return `<li><b>${esc(x.producto)}</b><ul class="aviso-lista">
                    <li>La OC fue emitida por <b class="aviso-azul">${n(x.pide)} ${esc(u)}</b>.</li>
                    <li>Estás registrando <b class="aviso-azul">${n(reg)} ${esc(u)}</b>.</li>
                    <li><b class="aviso-rojo-txt">Diferencia: ${n(dif)} ${esc(u)} ${x.tipo === 'Sobra' ? 'de MÁS' : 'FALTAN'}</b></li></ul></li>`;
            }).join('');
            f.innerHTML = `<div role="alertdialog" style="background:#fff;border:4px solid #DC2626;border-radius:14px;max-width:620px;width:100%;max-height:92vh;overflow:auto;padding:20px;box-shadow:0 20px 60px rgba(0,0,0,.35);color:#0F172A">
                <div style="font-size:20px;font-weight:900;margin-bottom:8px;color:#B91C1C">⛔ Lo que contaste NO coincide con la orden de compra</div>
                <ul class="aviso-lista aviso-docs">
                    ${o.numero ? `<li>Orden de compra (Proveedor): <b class="aviso-azul">${esc(o.numero)}</b></li>` : ''}
                    ${o.proveedor ? `<li>Proveedor: <b class="aviso-azul">${esc(o.proveedor)}</b></li>` : ''}
                    ${o.empresa ? `<li>Empresa: <b class="aviso-azul">${esc(o.empresa)}</b></li>` : ''}</ul>
                <ul class="aviso-lista" style="font-size:14.5px;line-height:1.5">${filas}</ul>
                <div style="font-size:16px;font-weight:900;margin:10px 0 6px">¿Estás seguro de que contaste bien?</div>
                ${Aviso.rojo(['Todavía <b>NO se grabó nada</b>. Si fue un error al escribir, pulsa <b>Volver a contar</b>.',
                              'Si de verdad llegó así: <b>coordina con el proveedor</b> y <b>avisa a tu jefe inmediato</b>.',
                              'Al confirmar, queda en el historial con tu nombre, fecha y hora, y le <b>sale el aviso a la jefa</b> en Hoy en Compras.'])}
                <label style="display:block;font-size:13px;font-weight:800;margin:12px 0">Explica qué pasó <span style="color:#DC2626">(obligatorio)</span>
                    <input type="text" data-motivo maxlength="300" placeholder="Ej. el proveedor mandó 8; dice que manda 12 el viernes" style="width:100%;margin-top:4px;padding:8px;border:2px solid #DC2626;border-radius:8px"></label>
                <div style="display:flex;gap:10px;justify-content:flex-end;flex-wrap:wrap">
                    <button type="button" data-r="0" style="padding:10px 18px;border-radius:10px;border:0;background:#16A34A;color:#fff;font-weight:900;cursor:pointer">🔁 Volver a contar</button>
                    <button type="button" data-r="1" disabled style="padding:10px 18px;border-radius:10px;border:2px solid #B91C1C;background:#fff;color:#B91C1C;font-weight:800;cursor:pointer;opacity:.45">Confirmar con diferencia</button></div></div>`;
            document.body.appendChild(f);
            const inp = f.querySelector('[data-motivo]'), si = f.querySelector('button[data-r="1"]');
            inp.oninput = () => { const ok = inp.value.trim().length >= 5; si.disabled = !ok; si.style.opacity = ok ? '1' : '.45'; };
            f.querySelectorAll('button[data-r]').forEach(b => b.onclick = () => {
                const motivo = inp.value.trim();
                if (b.dataset.r === '1' && motivo.length < 5) { inp.focus(); return; }
                f.remove();
                resolve(b.dataset.r === '1' ? { motivo } : null);
            });
            f.querySelector('button[data-r="0"]').focus();
        });
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
            let r;
            try {
                r = await post(`/compras/api/flujo/ordenes/${$('recOc').value}/recibir`, body);
            } catch (e) {
                if (!(e.data && e.data.codigo === 'diferencias')) throw e;
                const ok = await ventanaDiferencias(e.data.diferencias || []);
                if (!ok) { aviso('No se grabó. Vuelve a contar y corrige las cantidades.', 'info'); return; }
                r = await post(`/compras/api/flujo/ordenes/${$('recOc').value}/recibir`,
                               { ...body, confirmar_diferencias: true, motivo_diferencias: ok.motivo });
            }
            $('recCuerpo').style.display = 'none';
            const res = $('recResultado');
            res.style.display = '';
            const color = { Completo: 'ok', Faltante: 'danger', Sobrante: 'warn', 'Con dañados': 'warn' };
            res.innerHTML = `<div class="inv-alerta ${r.resultado.some(x => x.estado !== 'Completo') ? 'warn' : 'ok'}"><div>${esc(r.message)}</div></div>
                <div class="inv-subtitulo">Ahora sí: lo que se esperaba y lo que contaste</div>
                <table class="inv-table"><thead><tr><th class="com-item">Ítem</th><th class="left">Nombre producto</th><th>Se esperaba</th><th>Contaste (buenos)</th><th>Dañados</th><th>Resultado</th></tr></thead>
                <tbody>${r.resultado.map((x, n) => `<tr><td class="com-item">${n + 1}</td><td class="left">${esc(x.producto)}</td><td class="num">${cant(x.esperado)}</td><td class="num">${cant(x.buena)}</td>
                    <td class="num">${cant(x.danada)}</td><td><span class="com-paso com-paso-${color[x.estado] || 'info'}">${esc(x.estado)}</span></td></tr>`).join('')}</tbody></table>
                ${(r.pendientes_inventario || []).length ? '<div class="inv-paso">Siguiente: ve a <b>Inventario ▸ Entradas y salidas</b> y pulsa "Ingresar" en esta recepción. Si es de un pedido, quedará separada para ese cliente.</div>' : ''}`;
            $('recPie').innerHTML = `<a class="btn btn-secondary" href="/inventario?tab=entradas_salidas">Ir a Inventario ➜</a><button class="btn btn-primary" data-close="recModal">Listo</button>`;
            refrescar();
            cartelSiguiente($('recOc').value, '✅ ¡Mercadería recibida!', (r.pendientes_inventario || []).length ? {
                texto: 'También: en <b>Inventario ▸ Entradas y salidas</b> pulsa <b>"Ingresar"</b> en esta recepción para que entre al stock.',
                botones: [{ t: 'Ir a Inventario ➜', href: '/inventario?tab=entradas_salidas' }] } : undefined);
        });
    }

    // ========================================================
    // PAGOS Y FACTURAS
    // ========================================================
    async function cargarFacturas() {
        try {
            const conFiltro = filtroVer && filtroVer.tab === 'facturas';
            const data = aplicarFiltroVer('facturas', (await api('/compras/api/flujo/ordenes' + (conFiltro ? '' : '?estado=abiertas'))).data);
            const porPagar = data.filter(o => ['pagar', 'pagar_credito'].includes(o.paso.codigo));
            $('pagBody').innerHTML = porPagar.length ? porPagar.map(o => `<tr>
                <td><button class="btn-link" data-ver="${o.id}">${esc(o.numero)}</button></td><td><b>${esc(o.empresa || '')}</b></td>
                <td class="left">${esc(o.proveedor || '')}</td><td>${esc(condPagoMostrar(o.condicion_pago, o.dias_credito))}</td>
                <td class="num">${dinero(o.moneda, o.total)}</td><td class="num">${dinero(o.moneda, o.pagado)}</td><td class="num"><b>${dinero(o.moneda, o.saldo_pago)}</b></td>
                <td>${PUEDE.pagar ? `<button class="btn-mini" data-pagar="${o.id}">💸 Pagar</button>` : '—'}</td></tr>`).join('')
                : '<tr><td colspan="8">No hay órdenes por pagar. 👍</td></tr>';
            // Se espera factura cuando ya llegó mercadería o ya se pagó algo
            const sinFactura = data.filter(o => (['Recibida', 'Recibida parcial'].includes(o.estado) || Number(o.pagado) > 0)
                && (o.facturas === 0 || o.cuadra === false || Number(o.facturado) + 0.5 < Number(o.valor_recibido) * 1.18));
            $('facBody').innerHTML = sinFactura.length ? sinFactura.map(o => `<tr>
                <td><button class="btn-link" data-ver="${o.id}">${esc(o.numero)}</button></td><td><b>${esc(o.empresa || '')}</b></td>
                <td class="left">${esc(o.proveedor || '')}</td><td>${estadoOC(o.estado)}</td>
                <td><div class="com-barra ${Number(o.avance_recepcion) <= 0 ? 'com-barra-0' : (Number(o.avance_recepcion) >= 100 ? 'com-barra-100' : '')}"><i style="width:${o.avance_recepcion}%"></i></div><small>${Math.round(o.avance_recepcion)}%</small></td>
                <td>${o.facturas ? `${o.facturas} · ${dinero(o.moneda, o.facturado)}${o.cuadra === false ? '<small class="neg">no cuadra</small>' : ''}` : '<span class="inv-tip">Ninguna</span>'}</td>
                <td>${PUEDE.facturar ? `<button class="btn-mini" data-factura="${o.id}">🧾 Registrar factura</button>` : '—'}</td></tr>`).join('')
                : '<tr><td colspan="7">No hay facturas pendientes de registrar. 👍</td></tr>';
            ordenesCache = data;
        } catch (e) { $('pagBody').innerHTML = `<tr><td colspan="8">${esc(e.message)}</td></tr>`; }
    }

    function abrirFactura(o) {
        $('facOc').value = o.id;
        $('facTitulo').textContent = `Factura del proveedor · ${o.numero}`;
        $('facTipo').value = 'Factura';
        ['facNumero', 'facMonto', 'facObs', 'facMotivoDif'].forEach(i => { $(i).value = ''; });
        $('facFecha').value = hoyISO();
        // 24/10/2026: factura de una OC en dólares -> total en US$ y TC SUNAT de la fecha de emisión (registro de compras)
        facMoneda = Moneda.codigo(o.moneda);
        $('facMontoEt').textContent = `Total de la factura con IGV (${facMoneda === 'USD' ? 'US$' : 'S/'})`;
        $('facTCWrap').style.display = facMoneda === 'USD' ? '' : 'none';
        $('facTC').value = '';
        if (facMoneda === 'USD') proponerTCFactura();
        limpiarNoCuadra();
        abrir('facModal');
    }
    let facMoneda = 'PEN';
    async function proponerTCFactura() {
        const tc = await Moneda.tcSunat($('facFecha').value);
        $('facTCInfo').textContent = tc ? 'TC SUNAT de esa fecha. Es el que va al registro de compras.' : 'No se pudo traer el TC SUNAT: escríbelo (va al registro de compras).';
        if (tc) $('facTC').value = tc.toFixed(3);
    }

    // Factura que no cuadra (pedido de Erika 20/10/2026): no se guarda; aviso rojo y a corregir en el momento
    function limpiarNoCuadra() {
        $('facNoCuadra').style.display = 'none';
        $('facNoCuadra').innerHTML = '';
        $('facDifWrap').style.display = 'none';
        $('facAceptarDif').checked = false;
        $('facMonto').classList.remove('com-fac-mal');
    }
    function mostrarNoCuadra(r) {
        $('facNoCuadra').innerHTML = `⛔ <b>La factura NO cuadra. No se guardó.</b><br>
            Escribiste <b>${dinero(facMoneda, r.monto)}</b> y según lo recibido debería ser <b>${dinero(facMoneda, r.esperado)}</b>
            (diferencia ${dinero(facMoneda, r.diferencia)}).<br>Revisa el total que copiaste y corrígelo aquí mismo.`;
        $('facNoCuadra').style.display = '';
        $('facDifWrap').style.display = '';
        $('facMonto').classList.add('com-fac-mal');
        $('facMonto').focus();
        $('facMonto').select();
        aviso('La factura no cuadra: corrígela antes de guardar.', 'error');
    }

    async function guardarFactura(btn) {
        if (btn) { btn.disabled = true; btn.dataset.txt = btn.textContent; btn.textContent = 'Guardando...'; }
        try {
            const body = { tipo: $('facTipo').value, numero: $('facNumero').value, fecha: $('facFecha').value, monto: $('facMonto').value,
                           observaciones: $('facObs').value, aceptar_diferencia: $('facAceptarDif').checked,
                           motivo_diferencia: $('facMotivoDif').value, tipo_cambio: facMoneda === 'USD' ? $('facTC').value : null };
            if (facMoneda === 'USD' && !(Number(body.tipo_cambio) > 0)) throw new Error('La factura es en dólares: escribe el tipo de cambio.');
            const resp = await fetch(`/compras/api/flujo/ordenes/${$('facOc').value}/factura`, {
                method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                body: JSON.stringify(body) });
            const r = await resp.json().catch(() => ({}));
            if (resp.status === 401) { window.location.href = '/login'; return; }
            if (r.codigo === 'no_cuadra') { mostrarNoCuadra(r); return; }
            if (!resp.ok || r.success === false) throw new Error(r.error || `Error ${resp.status}`);
            aviso(r.message, r.cuadra ? 'success' : 'warning');
            cerrar('facModal');
            cartelSiguiente($('facOc').value, `✅ ¡Factura ${esc(body.numero.trim().toUpperCase())} registrada!`);
            ultimaFacturaId = r.id || null;
            const b = $('btnVerUltimaFactura');
            if (b && r.id) { b.classList.add('com-recien'); b.textContent = `👁 Ver la factura registrada recientemente (${body.numero.trim().toUpperCase()})`; }
            refrescar();
        } catch (e) { aviso(e.message, 'error'); }
        finally { if (btn) { btn.disabled = false; btn.textContent = btn.dataset.txt; } }
    }

    let ultimaFacturaId = null;
    async function verUltimaFactura() {
        try {
            const r = ultimaFacturaId ? await api('/compras/api/flujo/facturas/' + ultimaFacturaId) : await api('/compras/api/flujo/facturas/ultima');
            if (!r.data) { aviso('Todavía no registraste ninguna factura de proveedor.', 'warning'); return; }
            verFacturaProveedor(r.data);
        } catch (e) { aviso(e.message, 'error'); }
    }
    function verFacturaProveedor(f) {
        $('facVerTitulo').textContent = `${f.tipo || 'Factura'} ${f.numero} · ${f.proveedor_nombre || ''}`;
        const cuadra = f.cuadra !== false;
        $('facVerCuerpo').innerHTML = `
            <div class="com-fac-estado ${cuadra ? 'ok' : 'mal'}">${cuadra ? '✔ Cuadra con lo recibido' : `⚠️ Registrada con diferencia: debía ser ${dinero(f.moneda, f.monto_esperado)}`}</div>
            <div class="com-fac-ver">
                <div><small>N° Factura</small><b>${esc(f.numero)}</b></div>
                <div><small>N° OC (Proveedor)</small><b>${esc(f.orden_compra_numero || '—')}</b></div>
                <div><small>Proveedor</small><b>${esc(f.proveedor_nombre || '')}</b><br><span>RUC ${esc(f.ruc_proveedor || '—')}</span></div>
                <div><small>Total con IGV</small><b>${dinero(f.moneda, f.monto)}</b>${f.moneda === 'USD' && f.tipo_cambio ? `<br><span>TC ${Number(f.tipo_cambio).toFixed(3)} ≈ ${soles(Number(f.monto) * Number(f.tipo_cambio))}</span>` : ''}</div>
                <div><small>Fecha de emisión</small><b>${fecha(String(f.fecha || '').slice(0, 10), false)}</b></div>
                <div><small>Vence</small><b>${f.fecha_vencimiento ? fecha(String(f.fecha_vencimiento).slice(0, 10), false) : '—'}</b></div>
                <div><small>Estado</small><b>${esc(f.estado || '')}</b></div>
                <div><small>Registrada</small><b>${f.created_at ? esc(new Date(f.created_at).toLocaleString('es-PE', { timeZone: 'America/Lima' })) : '—'}</b><br><span>${esc(f.registrado_por || '')}</span></div>
                ${f.observaciones ? `<div style="grid-column:1/-1"><small>Observaciones</small>${esc(f.observaciones)}</div>` : ''}
            </div>`;
        $('facVerOrden').style.display = f.orden_compra_id ? '' : 'none';
        $('facVerOrden').onclick = () => { cerrar('facVerModal'); verOrden(f.orden_compra_id); };
        abrir('facVerModal');
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
        if (tab) { filtroVer = null; cambiarTab(tab.dataset.tab); return; }
        if (t.closest('[data-quitar-filtro]')) { filtroVer = null; cargadores[tabActual](); return; }
        const ir = t.closest('[data-ir]');
        if (ir) {
            const al = ir.dataset.alerta !== undefined ? alertasHoy[Number(ir.dataset.alerta)] : null;
            filtroVer = al && Array.isArray(al.ids) ? { tab: ir.dataset.ir, ids: new Set(al.ids), filtro: al.filtro || 'Alerta' } : null;
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
        const u = e.target.closest('[data-usar-pc], [data-sumar-pc]');
        if (u) {
            const [pid, ped] = (u.dataset.usarPc || u.dataset.sumarPc).split('|');
            usarPedidoAbast(Number(pid), ped, !!u.dataset.sumarPc);
        }
    });
    document.addEventListener('change', e => {
        if (e.target.dataset && e.target.dataset.extraPid) ponerExtraStock(Number(e.target.dataset.extraPid), e.target.value);
        if (e.target.dataset && e.target.dataset.respOc) guardarResponsable(e.target);
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
        $('ocEmp').addEventListener('change', () => { if (provElegido) pintarProveedor(); });
        $('ocDias').oninput = () => { $('ocCondTexto').textContent = condPagoTexto('Crédito', $('ocDias').value); textoAdelanto(); };
        $('ocAdelantoPct').onchange = textoAdelanto;
        $('ocGuardar').onclick = () => guardarOC(false, $('ocGuardar'));
        $('ocEnviar').onclick = () => guardarOC(true, $('ocEnviar'));
        $('recTraidoTipo').onchange = ajustarTraido;
        $('pagoGuardar').onclick = () => guardarCon($('pagoGuardar'), async () => {
            const monPago = pagoDoc.moneda === 'USD' ? $('pagoMonedaPago').value : pagoDoc.moneda;
            if (monPago !== pagoDoc.moneda && !(Number($('pagoTC').value) > 0)) throw new Error('Escribe el tipo de cambio que te dio el proveedor.');
            const r = await post(`/compras/api/flujo/ordenes/${$('pagoOc').value}/pago`, {
                monto: montoPagoDoc(), monto_pagado: $('pagoMonto').value, moneda_pago: monPago,
                tipo_cambio: monPago !== pagoDoc.moneda ? $('pagoTC').value : null, fecha: $('pagoFecha').value, metodo: $('pagoMetodo').value, banco: $('pagoBanco').value,
                numero_operacion: $('pagoOperacion').value, observaciones: $('pagoObs').value });
            aviso(r.message, 'success'); cerrar('pagoModal'); refrescar();
            cartelSiguiente($('pagoOc').value, '✅ ¡Pago registrado!');
        });
        $('facGuardar').onclick = () => guardarFactura($('facGuardar'));
        $('pagoMonedaPago').onchange = () => { $('pagoTC').value = ''; pintarMonedaPago(true); };
        $('pagoTC').oninput = () => { $('pagoMonto').value = (pagoDoc.falta * (Number($('pagoTC').value) || 0)).toFixed(2); equivPago(); };
        $('pagoMonto').addEventListener('input', equivPago);
        $('facFecha').addEventListener('change', () => { if (facMoneda === 'USD') proponerTCFactura(); });
        $('facMonto').addEventListener('input', () => $('facMonto').classList.remove('com-fac-mal'));
        $('btnVerUltimaFactura').onclick = verUltimaFactura;
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
            // Botón "Generar compra" de Ventas ▸ Entregas: /compras?tab=pedidos&pc=PC-... abre la orden con ese pedido
            if (qs.get('pc')) await abrirCompraDePedido(qs.get('pc'), qs.get('desp'));
            // Botón "Ver OC" de Ventas ▸ Entregas (27/10/2026): /compras?tab=ordenes&oc=OC-... busca esa orden
            if (qs.get('oc')) {
                if (tabActual !== 'ordenes') cambiarTab('ordenes');
                $('ocBuscar').value = qs.get('oc');
                cargarOrdenes();
            }
        } catch (e) { aviso('No se pudo cargar Compras: ' + e.message, 'error'); }
    })();
})();
