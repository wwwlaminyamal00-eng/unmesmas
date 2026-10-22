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
        $('#icAvisos').innerHTML = d.avisos.length
            ? `<div class="ge-aviso-rojo"><b>Para que todo cuadre:</b><ul>${d.avisos.map(a => `<li>${esc(a)}</li>`).join('')}</ul></div>` : '';
        const tarjetas = d.sentidos.map(s => {
            const t = d.totales[s] || { base: 0, n: 0 };
            return kpi(`Ventas ${s.replace('→', ' → ')}`, soles(t.base), `${t.n} factura(s) · sin IGV`, 'ge-kpi-cobro');
        });
        tarjetas.push(kpi('Falta registrar como compra', d.sin_compra, d.sin_compra ? 'Pierde crédito fiscal' : 'Todo registrado', d.sin_compra ? 'ge-kpi-mal' : 'ge-kpi-ok'));
        const neto = d.deudas.netos[0];
        tarjetas.push(kpi('Se deben (neto)', neto ? soles(neto.saldo) : 'S/ 0.00', neto ? `${neto.deudor} le debe a ${neto.acreedor}` : 'No se deben nada', neto ? 'ge-kpi-pago' : 'ge-kpi-ok'));
        tarjetas.push(kpi('Stock del grupo', stock ? soles(stock.valor_grupo) : '...', stock ? `${stock.total_productos} productos con stock` : 'Valorizado', ''));
        $('#icKpis').innerHTML = tarjetas.join('');
        pintarVentas();
        pintarDeudas();
        pintarTendencia();
        pintarIgv();
    }

    function pintarVentas() {
        const v = datos.ventas;
        $('#icTitVentas').textContent = `Ventas entre empresas · ${datos.nombre_periodo}`;
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
        $('#icBuscar').addEventListener('input', () => { clearTimeout(espera); espera = setTimeout(cargarStock, 350); });
        cargar();
    });
})();
