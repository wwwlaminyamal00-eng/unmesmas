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
        $('#icKpis').innerHTML = '<div class="inv-vacio">Calculando...</div>';
        try {
            datos = await api('/intercompany/api/resumen?periodo=' + encodeURIComponent($('#icMes').value || ''));
        } catch (e) {
            $('#icKpis').innerHTML = `<div class="inv-vacio">⚠ ${esc(e.message)}</div>`;
            return;
        }
        if (!$('#icMes').value) $('#icMes').value = datos.periodo;
        pintar();
        if (!stock) cargarStock();
    }

    function pintar() {
        const d = datos;
        // Un solo aviso pequeño si falta preparar algo (antes era un cartel rojo grande)
        $('#icAvisos').innerHTML = d.avisos.length
            ? `<div class="ic-aviso" title="${esc(d.avisos.join('\n'))}">⚠ Para que todo cuadre: ${esc(d.avisos[0])}${d.avisos.length > 1 ? ` (y ${d.avisos.length - 1} más)` : ''}</div>` : '';
        // Fila de estado delgada, contada desde la tabla de operaciones (una fila por OC entre empresas)
        const ops = d.operaciones || [];
        const abiertas = ops.filter(o => !o.completa).length;
        const porPagar = ops.reduce((s, o) => s + num(o.saldo), 0);
        const sinMercaderia = ops.filter(o => o.recibida < o.pedida || !o.despachos).length;
        const sinFactura = ops.filter(o => !o.factura_venta || !o.factura_compra).length;
        const neto = d.deudas.netos[0];
        const pill = (texto, valor, mal, filtro) => `<${filtro ? 'button type="button" data-filtro="pend"' : 'span'} class="res-item ${mal ? 'res-mal' : 'res-ok'}">${texto} <b>${valor}</b></${filtro ? 'button' : 'span'}>`;
        $('#icKpis').innerHTML = [
            pill('Operaciones abiertas', `${abiertas} de ${ops.length}`, abiertas, true),
            pill('Falta pagar', soles(porPagar), porPagar > 0, true),
            pill('Falta recibir o despachar', sinMercaderia, sinMercaderia, true),
            pill('Falta facturar o registrar', sinFactura, sinFactura, true),
            pill(neto ? `${esc(neto.deudor)} le debe a ${esc(neto.acreedor)}` : 'Se deben', neto ? soles(neto.saldo) : 'S/ 0.00', false, false),
            `<span class="res-item">Stock del grupo <b>${stock ? soles(stock.valor_grupo) : '...'}</b></span>`,
        ].join('');
        $('#icDeudasResumen').textContent = neto ? `· ${neto.deudor} le debe a ${neto.acreedor} ${soles(neto.saldo)}` : '· no se deben nada';
        pintarOperaciones();
        pintarVentas();
        pintarDeudas();
        pintarTendencia();
        pintarIgv();
    }

    function pintarOperaciones() {
        const filtro = $('#icFiltroOps').value;
        const q = $('#icBuscarOps').value.trim().toUpperCase();
        const todas = datos.operaciones || [];
        const ops = todas.filter(o => (filtro === 'todas' || (filtro === 'pend' ? !o.completa : o.completa))
            && (!q || [o.oc, o.pc, o.cotizacion, o.cliente, o.pc_vende, o.despachos, o.factura_venta, o.factura_compra, o.vende, o.compra]
                .join(' ').toUpperCase().includes(q)));
        if (!todas.length) {
            $('#icOperaciones').innerHTML = `<div class="inv-vacio">Todavía no hay órdenes de compra hechas a la otra empresa del grupo.
                Para crear una: Compras ▸ Nueva OC y elige como proveedor a la otra empresa (por su RUC).</div>`;
            return;
        }
        if (!ops.length) { $('#icOperaciones').innerHTML = '<div class="inv-vacio">Ninguna operación coincide con el filtro.</div>'; return; }
        const ok = (c, si, no, titulo) => `<span class="ic-linea ${c ? 'ic-ok' : 'ic-mal'}"${titulo ? ` title="${esc(titulo)}"` : ''}>${c ? '✔ ' + si : '⏳ ' + no}</span>`;
        $('#icOperaciones').innerHTML = `<table class="inv-table ge-tabla ic-ops"><thead><tr><th>N° OC</th><th>Vende → Compra</th>
            <th>Para qué</th><th>Monto</th><th>Pago</th><th>Mercadería</th><th>Facturas</th><th>Siguiente paso</th></tr></thead><tbody>
            ${ops.map(o => `<tr class="${o.completa ? 'ge-fila-ok' : 'ge-fila-pend'}">
                <td><b class="ge-nw">${esc(o.oc)}</b><small>${fecha(o.fecha)}</small></td>
                <td><b class="ge-nw">${esc(o.vende)} → ${esc(o.compra)}</b></td>
                <td>${o.para_stock ? 'Stock' : `<span class="ic-linea" title="${esc([o.cotizacion && 'N° cotización: ' + o.cotizacion, o.cliente && 'Cliente: ' + o.cliente].filter(Boolean).join('\n'))}"><b>${esc(o.pc)}</b></span><small>${esc(o.cliente || '')}</small>`}</td>
                <td><b class="ge-nw">${soles(o.total)}</b><small>${esc(o.condicion || '-')}</small></td>
                <td>${num(o.saldo) > 0 ? `<span class="ge-estado rojo">Falta ${soles(o.saldo)}</span>` : '<span class="ge-estado verde">✔ Pagado</span>'}</td>
                <td>${ok(o.recibida >= o.pedida, 'Recibida', `Por recibir (${cant(o.recibida)} de ${cant(o.pedida)})`, `Recibido en ${o.compra}: ${cant(o.recibida)} de ${cant(o.pedida)}`)}
                    ${ok(!!o.despachos, 'Despachada', 'Sin despacho', o.despachos ? `Despacho de ${o.vende}: ${o.despachos}` : (o.pc_vende ? `PC de ${o.vende}: ${o.pc_vende}` : `${o.vende} aún no tiene PC con esta OC`))}</td>
                <td>${ok(!!o.factura_venta, o.factura_venta, 'Sin factura', `Factura de venta de ${o.vende}`)}
                    ${ok(!!o.factura_compra, 'En compras', 'Sin registrar', `Registrada en compras de ${o.compra}`)}</td>
                <td>${o.completa ? '<span class="ge-estado verde">✔ Completa</span>'
                    : `<span class="ic-linea ic-mal">${esc(o.falta[0])}</span>${o.falta.length > 1
                        ? `<span class="ic-mas" title="${esc(o.falta.slice(1).join('\n'))}">y ${o.falta.length - 1} paso(s) más</span>` : ''}`}</td></tr>`).join('')}
            </tbody></table>`;
    }

    function pintarVentas() {
        const v = datos.ventas;
        $('#icTitVentas').textContent = `🧾 Facturas entre empresas · ${datos.nombre_periodo} (${datos.ventas.length})`;
        if (!v.length) {
            $('#icVentas').innerHTML = '<div class="inv-vacio">No hay ventas entre las empresas en este mes (ni en Ventas ni en lo subido del SIRE).</div>';
            return;
        }
        $('#icVentas').innerHTML = `<table class="inv-table ge-tabla"><thead><tr><th>Fecha</th><th>Vende</th><th>Compra</th><th>N° factura</th>
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
        $('#icDeudas').innerHTML = netos + `<table class="inv-table ge-tabla"><thead><tr><th>Debe</th><th>A</th><th>N° factura</th><th>Fecha</th>
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
        $('#icKpis').addEventListener('click', e => {
            if (!e.target.closest('[data-filtro]') || !datos) return;
            $('#icFiltroOps').value = 'pend';
            pintarOperaciones();
            $('#icOperaciones').scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
        $('#icBuscar').addEventListener('input', () => { clearTimeout(espera); espera = setTimeout(cargarStock, 350); });
        cargar();
    });
})();
