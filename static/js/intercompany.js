// static/js/intercompany.js - Intercompany KCF ↔ AGD (pedido de Erika 21/10/2026)
(function () {
    'use strict';
    const $ = (s, r = document) => r.querySelector(s);
    const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
    const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const num = v => Number(v || 0);
    const soles = v => 'S/ ' + num(v).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const cant = v => num(v).toLocaleString('es-PE', { maximumFractionDigits: 2 });
    const TABS = ['resumen', 'igv', 'stock'];
    let tab = 'resumen';
    let datos = null;
    let stock = null;
    let espera = null;

    function fecha(v) {
        if (!v) return '';
        const m = String(v).match(/^(\d{4})-(\d{2})-(\d{2})/);
        return m ? `${m[3]}/${m[2]}/${m[1]}` : esc(v);
    }
    async function api(url) {
        const r = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin' });
        let j = {};
        try { j = await r.json(); } catch (e) { /* sin JSON */ }
        if (!r.ok || j.success === false) throw new Error(j.error || `Error ${r.status}`);
        return j.data;
    }
    const kpi = (titulo, valor, pie, clase) => `<div class="inv-kpi ${clase || ''}"><small>${titulo}</small><b>${valor}</b><span>${pie || ''}</span></div>`;

    function irA(t) {
        tab = TABS.includes(t) ? t : 'resumen';
        $$('#icTabs .tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
        TABS.forEach(x => $('#ic-sec-' + x).classList.toggle('active', x === tab));
        try { history.replaceState(null, '', '/intercompany?tab=' + tab); } catch (e) { /* nada */ }
        if (window.abrirMenuModulo) window.abrirMenuModulo();
        if (tab === 'stock' && !stock) cargarStock();
    }

    async function cargar() {
        $('#icConsol').innerHTML = '<div class="inv-vacio">Calculando...</div>';
        try {
            datos = await api('/intercompany/api/resumen?periodo=' + encodeURIComponent($('#icMes').value || ''));
        } catch (e) {
            $('#icConsol').innerHTML = `<div class="inv-vacio">⚠ ${esc(e.message)}</div>`;
            return;
        }
        if (!$('#icMes').value) $('#icMes').value = datos.periodo;
        pintar();
        if (!stock) cargarStock();
    }

    // Pasos en el orden del negocio: quién lo hace y cómo se dice cuando falta
    const PASOS = [
        ['despachado', 'vende', 'Despachado', 'por despachar'],
        ['recibido', 'compra', 'Recibido', 'por recibir'],
        ['facturado', 'vende', 'Facturado', 'por facturar'],
        ['registrado', 'compra', 'Registrado', 'por registrar en compras'],
        ['pago', 'compra', 'Pagado', 'por pagar'],
    ];
    const CAMPO_CUENTA = { despachado: 'por_despachar', recibido: 'por_recibir', facturado: 'por_facturar', registrado: 'por_registrar', pago: 'por_pagar' };
    const activa = () => ((window.EMPRESA_ACTIVA || {}).corto || '').toUpperCase();

    function pintar() {
        const d = datos;
        $('#icAvisos').innerHTML = d.avisos.length ? `<div class="ic-aviso">⚠ ${d.avisos.map(esc).join('<br>⚠ ')}</div>` : '';
        const yo = activa();
        // Primero el sentido en que vende la empresa activa (lo que me deben), luego en el que compra (lo que debo)
        const cons = (d.consolidado || []).slice().sort((a, b) => (b.vende === yo) - (a.vende === yo));
        const sel = $('#icSentido');
        if (sel.options.length === 1) cons.forEach(c => sel.insertAdjacentHTML('beforeend', `<option value="${esc(c.vende)}>${esc(c.compra)}">${esc(c.vende)} vende a ${esc(c.compra)}</option>`));
        // Una sola cifra final: quién le debe a quién por las OC sin pagar
        const [a, b] = cons.length >= 2 ? [cons[0], cons[1]] : [null, null];
        if (a) {
            const neto = num(a.falta_pagar) - num(b.falta_pagar);
            $('#icNeto').innerHTML = neto === 0
                ? `<span class="ge-estado verde">✔ ${esc(a.vende)} y ${esc(a.compra)} no se deben nada por las OC</span>`
                : `Al final, <b>${esc(neto > 0 ? a.compra : a.vende)}</b> le debe a <b>${esc(neto > 0 ? a.vende : a.compra)}</b>
                   <span class="ge-estado rojo">${soles(Math.abs(neto))}</span>
                   <small>(${esc(a.compra)} debe ${soles(a.falta_pagar)} · ${esc(b.compra)} debe ${soles(b.falta_pagar)})</small>`;
        } else $('#icNeto').innerHTML = '';
        $('#icConsol').innerHTML = cons.map(c => {
            const para = c.vende === yo ? `Para ${esc(yo)}: lo que te deben` : (c.compra === yo ? `Para ${esc(yo)}: lo que debes` : '');
            const chips = PASOS.map(p => {
                const n = c[CAMPO_CUENTA[p[0]]];
                if (!n) return '';
                const extra = p[0] === 'facturado' ? ` · ${soles(c.monto_por_facturar)}` : (p[0] === 'pago' ? ` · ${soles(c.falta_pagar)}` : '');
                return `<button type="button" class="ic-chip mal" data-sentido="${esc(c.vende)}>${esc(c.compra)}" data-paso="${p[0]}">
                    <span>⏳ <b>${n}</b> ${p[3]}${extra}</span><small>lo hace ${esc(p[1] === 'vende' ? c.vende : c.compra)}</small></button>`;
            }).join('');
            return `<div class="ic-card${c.abiertas ? '' : ' ok'}">
                <div class="ic-card-tit"><b>${esc(c.vende)} le vende a ${esc(c.compra)}</b><small>${para}</small></div>
                <div class="ic-cifras"><span>OC <b>${c.ocs}</b></span><span>Total <b>${soles(c.total)}</b></span>
                    <span>Pagado <b class="ic-ok">${soles(c.pagado)}</b></span>
                    <span>Falta pagar <b class="${num(c.falta_pagar) > 0 ? 'ic-mal' : 'ic-ok'}">${soles(c.falta_pagar)}</b></span></div>
                <div class="ic-chips">${c.ocs ? (chips || '<span class="ic-chip ok">✔ Todo al día</span>') : '<span class="ic-chip gris">Sin operaciones</span>'}</div>
                ${c.facturas_por_cobrar ? `<div class="ic-pie">🧾 ${esc(c.vende)} aún tiene <b>${c.facturas_por_cobrar}</b> factura(s) por cobrar en Finanzas · ${soles(c.saldo_facturas)}${c.facturas_vencidas ? ` · <span class="ic-mal">${c.facturas_vencidas} vencida(s)</span>` : ''}
                    <small>Si ${esc(c.compra)} ya pagó, registra el cobro en Finanzas de ${esc(c.vende)}.</small></div>` : ''}
            </div>`;
        }).join('');
        const neto = d.deudas.netos[0];
        $('#icDeudasResumen').textContent = neto ? `· ${neto.deudor} le debe a ${neto.acreedor} ${soles(neto.saldo)}` : '· ninguna pendiente';
        pintarOperaciones();
        pintarVentas();
        pintarDeudas();
        pintarTendencia();
        pintarIgv();
    }

    function pintarOperaciones() {
        const filtro = $('#icFiltroOps').value;
        const sentido = $('#icSentido').value;
        const q = $('#icBuscarOps').value.trim().toUpperCase();
        const todas = datos.operaciones || [];
        if (!todas.length) {
            $('#icOperaciones').innerHTML = `<div class="inv-vacio">Todavía no hay órdenes de compra hechas a la otra empresa del grupo.
                Para crear una: Compras ▸ Nueva OC y elige como proveedor a la otra empresa (por su RUC).</div>`;
            return;
        }
        const pasa = o => (filtro === 'todas' || (filtro === 'pend' ? !o.completa : filtro === 'ok' ? o.completa : !o.estados[filtro]))
            && (!sentido || `${o.vende}>${o.compra}` === sentido)
            && (!q || [o.oc, o.pc, o.cotizacion, o.cliente, o.pc_vende, o.despachos, o.factura_venta, o.factura_compra]
                .join(' ').toUpperCase().includes(q));
        const yo = activa();
        const sentidos = (datos.consolidado || []).slice().sort((a, b) => (b.vende === yo) - (a.vende === yo));
        const celda = (o, p) => {
            const ok = o.estados[p[0]];
            const quien = p[1] === 'vende' ? o.vende : o.compra;
            const det = {
                despachado: ok ? o.despachos : (o.pc_vende ? `PC ${o.pc_vende}` : 'sin PC con esta OC'),
                recibido: `${cant(o.recibida)} de ${cant(o.pedida)}`,
                facturado: ok ? o.factura_venta : '',
                registrado: ok ? o.factura_compra : '',
                pago: ok ? '' : `falta ${soles(o.saldo)}`,
            }[p[0]];
            return `<td title="${esc(`${p[2]} (lo hace ${quien})`)}"><span class="ic-linea ${ok ? 'ic-ok' : 'ic-mal'}">${ok ? '✔' : '⏳'}</span>${det ? `<small>${esc(det)}</small>` : ''}</td>`;
        };
        let html = '';
        sentidos.forEach(c => {
            const ops = todas.filter(o => o.vende === c.vende && o.compra === c.compra && pasa(o));
            if (sentido && sentido !== `${c.vende}>${c.compra}`) return;
            html += `<div class="ic-sentido-tit">${esc(c.vende)} → ${esc(c.compra)} <small>${esc(c.vende)} vende · ${esc(c.compra)} compra · ${ops.length} OC</small></div>`;
            if (!ops.length) { html += `<div class="inv-vacio">${c.ocs ? 'Ninguna operación de este sentido con el filtro elegido.' : 'Sin operaciones en este sentido.'}</div>`; return; }
            html += `<table class="inv-table ge-tabla ic-ops"><thead><tr><th>N° OC</th><th>Para qué</th><th>Monto</th>
                ${PASOS.map(p => `<th>${p[2]}<small>${esc(p[1] === 'vende' ? c.vende : c.compra)}</small></th>`).join('')}<th>Siguiente paso</th></tr></thead><tbody>
                ${ops.map(o => `<tr class="${o.completa ? 'ge-fila-ok' : 'ge-fila-pend'}">
                    <td><b class="ge-nw">${esc(o.oc)}</b><small>${fecha(o.fecha)}</small></td>
                    <td>${o.para_stock ? 'Stock' : `<b>${esc(o.pc)}</b><small>${esc(o.cliente || '')}</small>`}</td>
                    <td><b class="ge-nw">${soles(o.total)}</b><small>${esc(o.condicion || '-')}</small></td>
                    ${PASOS.map(p => celda(o, p)).join('')}
                    <td>${o.completa ? '<span class="ge-estado verde">✔ Completa</span>'
                        : `<span class="ic-quien">${esc(o.siguiente.quien)}</span><span class="ic-linea ic-mal"${o.falta.length > 1 ? ` title="${esc('Después:\n' + o.falta.slice(1).join('\n'))}"` : ''}>${esc(o.siguiente.texto)}</span>`}</td></tr>`).join('')}
                </tbody></table>`;
        });
        $('#icOperaciones').innerHTML = html;
    }

    function pintarVentas() {
        const v = datos.ventas;
        $('#icTitVentas').textContent = `🧾 Facturas entre empresas · ${datos.nombre_periodo} (${datos.ventas.length})`;
        if (!v.length) {
            $('#icVentas').innerHTML = '<div class="inv-vacio">No hay ventas entre las empresas en este mes (ni en Ventas ni en lo subido del SIRE).</div>';
            return;
        }
        $('#icVentas').innerHTML = `<table class="inv-table ge-tabla"><thead><tr><th>Fecha</th><th>Vende</th><th>Compra</th><th>N° Factura</th>
            <th>Sin IGV (S/)</th><th>IGV (S/)</th><th>Total (S/)</th><th>Registrada como compra</th></tr></thead><tbody>
            ${v.map(x => `<tr class="${x.registrada_en_compras ? 'ge-fila-ok' : 'ge-fila-pend'}">
                <td class="ge-nw">${fecha(x.fecha)}</td><td><b>${esc(x.vende)}</b></td><td><b>${esc(x.compra)}</b></td><td class="ge-nw">${esc(x.documento)}</td>
                <td class="ge-nw">${soles(x.base)}</td><td class="ge-nw">${soles(x.igv)}</td><td class="ge-nw"><b>${soles(x.total)}</b></td>
                <td>${x.registrada_en_compras ? `<span class="ge-estado verde">✔ Registrada en ${esc(x.compra)}</span>`
                    : `<span class="ge-estado rojo">⏳ Falta en compras de ${esc(x.compra)}</span>`}</td></tr>`).join('')}
            </tbody></table>`;
    }

    function pintarDeudas() {
        const d = datos.deudas;
        if (!d.detalle.length) { $('#icDeudas').innerHTML = '<div class="ge-todo-ok">✔ Las empresas no se deben nada</div>'; return; }
        const netos = d.netos.map(n => `<div class="ge-neto"><b>${esc(n.deudor)}</b> le debe a <b>${esc(n.acreedor)}</b>: <span>${soles(n.saldo)}</span></div>`).join('');
        $('#icDeudas').innerHTML = netos + `<table class="inv-table ge-tabla"><thead><tr><th>Debe</th><th>A</th><th>N° Factura</th><th>Fecha</th>
            <th>Vence</th><th>Total (S/)</th><th>Saldo (S/)</th><th>Estado</th></tr></thead><tbody>
            ${d.detalle.map(x => `<tr class="${x.dias_vencido ? 'ge-fila-pend' : ''}"><td><b>${esc(x.deudor)}</b></td><td><b>${esc(x.acreedor)}</b></td>
                <td class="ge-nw">${esc(x.documento)}</td><td class="ge-nw">${fecha(x.fecha)}</td><td class="ge-nw">${fecha(x.vence)}</td>
                <td class="ge-nw">${soles(x.total)}</td><td class="ge-nw"><b>${soles(x.saldo)}</b></td>
                <td>${x.dias_vencido ? `<span class="ge-estado rojo">Vencida hace ${x.dias_vencido} días</span>` : '<span class="ge-estado amarillo">Por cobrar</span>'}</td></tr>`).join('')}
            </tbody></table>`;
    }

    function pintarTendencia() {
        const s = datos.sentidos;
        $('#icTendencia').innerHTML = `<table class="inv-table ge-tabla"><thead><tr><th>Mes</th>${s.map(x => `<th>${esc(x.replace('→', ' → '))} (S/)</th>`).join('')}</tr></thead><tbody>
            ${datos.tendencia.map(f => `<tr${f.periodo === datos.periodo ? ' class="ge-fila-actual"' : ''}><td><b>${esc(f.nombre)}</b></td>
                ${s.map(x => `<td class="ge-nw">${f.sentidos[x] ? soles(f.sentidos[x]) : '<span class="ge-cero">—</span>'}</td>`).join('')}</tr>`).join('')}
            </tbody></table>`;
    }

    function pintarIgv() {
        $('#icTitIgv').textContent = `IGV de ${datos.nombre_periodo}`;
        const filas = datos.igv;
        $('#icIgv').innerHTML = `<table class="inv-table ge-tabla"><thead><tr><th>Empresa</th><th>IGV de ventas (S/)</th><th>IGV de compras (S/)</th>
            <th>IGV a pagar (S/)</th><th>Saldo a favor (S/)</th><th>Retenciones sin usar (S/)</th><th>Vence</th></tr></thead><tbody>
            ${filas.map(x => x.error ? `<tr><td><b>${esc(x.codigo)}</b></td><td colspan="6">⚠ ${esc(x.error)}</td></tr>` : `<tr>
                <td><b>${esc(x.codigo)}</b></td><td class="ge-nw">${soles(x.igv_ventas)}</td><td class="ge-nw">${soles(x.igv_compras)}</td>
                <td>${x.igv_pagar > 0 ? `<span class="ge-estado rojo">${soles(x.igv_pagar)}</span>` : '<span class="ge-estado verde">S/ 0.00</span>'}</td>
                <td class="ge-nw">${soles(x.saldo_favor)}</td><td class="ge-nw">${soles(x.retenciones_libres)}</td><td class="ge-nw">${fecha(x.vencimiento)}</td></tr>`).join('')}
            </tbody></table>`;
        $('#icSugerencias').innerHTML = datos.sugerencias.map(s => `<div class="ge-sug ${s.nivel}"><b>${esc(s.titulo)}</b><p>${esc(s.texto)}</p></div>`).join('');
    }

    async function cargarStock() {
        try {
            stock = await api('/intercompany/api/stock?q=' + encodeURIComponent($('#icBuscar').value.trim()));
        } catch (e) {
            $('#icStock').innerHTML = `<div class="inv-vacio">⚠ ${esc(e.message)}</div>`;
            return;
        }
        pintarStock();
        if (datos) pintar();
    }

    function pintarStock() {
        const emps = (datos ? datos.empresas.map(e => e.codigo) : stock.por_empresa.map(e => e.codigo));
        $('#icStockKpis').innerHTML = stock.por_empresa.map(e => kpi(`Stock ${esc(e.codigo)}`, soles(e.valor), `${cant(e.unidades)} unidades · ${e.productos} productos`, ''))
            .concat([kpi('Total del grupo', soles(stock.valor_grupo), `${stock.total_productos} productos con stock`, 'ge-kpi-ok')]).join('');
        if (!stock.productos.length) { $('#icStock').innerHTML = '<div class="inv-vacio">No hay productos con stock.</div>'; return; }
        $('#icStock').innerHTML = `<table class="inv-table ge-tabla"><thead><tr><th>Código de producto</th><th>Nombre producto</th><th>Unidad</th>
            ${emps.map(c => `<th>${esc(c)}</th>`).join('')}<th>Total grupo</th><th>Valor (S/)</th></tr></thead><tbody>
            ${stock.productos.map(p => `<tr><td class="ge-nw">${esc(p.codigo)}</td><td>${esc(p.descripcion)}</td><td>${esc(p.unidad || '')}</td>
                ${emps.map(c => `<td>${p.empresas[c] ? cant(p.empresas[c]) : '<span class="ge-cero">0</span>'}</td>`).join('')}
                <td><b>${cant(p.total)}</b></td><td class="ge-nw">${soles(p.valor)}</td></tr>`).join('')}
            </tbody></table>${stock.total_productos > stock.productos.length ? `<div class="inv-vacio">Se muestran los ${stock.productos.length} de mayor valor. Usa el buscador para ver otros.</div>` : ''}`;
    }

    document.addEventListener('DOMContentLoaded', () => {
        if (!$('#icApp')) return;
        $$('#icTabs .tab-btn').forEach(b => b.addEventListener('click', () => irA(b.dataset.tab)));
        irA(new URLSearchParams(location.search).get('tab') || 'resumen');
        $('#icMes').addEventListener('change', cargar);
        $('#icFiltroOps').addEventListener('change', () => datos && pintarOperaciones());
        $('#icBuscarOps').addEventListener('input', () => datos && pintarOperaciones());
        $('#icSentido').addEventListener('change', () => datos && pintarOperaciones());
        // Clic en un pendiente del resumen: filtra la tabla por ese sentido y ese paso
        $('#icConsol').addEventListener('click', e => {
            const b = e.target.closest('[data-paso]');
            if (!b || !datos) return;
            $('#icSentido').value = b.dataset.sentido;
            $('#icFiltroOps').value = b.dataset.paso;
            pintarOperaciones();
            $('#icOperaciones').scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
        $('#icBuscar').addEventListener('input', () => { clearTimeout(espera); espera = setTimeout(cargarStock, 350); });
        cargar();
    });
})();
