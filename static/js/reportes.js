// static/js/reportes.js - Módulo 8: Reportes (tablero de ventas + visor de reportes con exportación)
(function () {
    'use strict';
    const CAT = window.REP_CATALOGO || {};
    const $ = (s, r = document) => r.querySelector(s);
    const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
    const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const soles = v => 'S/ ' + Number(v || 0).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const numero = v => Number(v || 0).toLocaleString('es-PE', { maximumFractionDigits: 2 });
    const pct = v => (v === null || v === undefined) ? '—' : Number(v).toLocaleString('es-PE', { maximumFractionDigits: 1 }) + '%';
    const PESTANAS = { ventas: 'ventas', compras: 'compras', inventario: 'stock', cxc: 'cxc', cxp: 'cxp', kpi: 'kpi' };
    let catalogos = null;
    let tabActual = 'tablero';
    let repActual = null;
    let ultimo = null;
    let pedido = 0;

    function fecha(v, conHora) {
        if (!v) return '';
        if (typeof window.fechaHoraLima === 'function') return esc(window.fechaHoraLima(v, !!conHora));
        const m = String(v).match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/);
        if (!m) return esc(v);
        return `${m[3]}/${m[2]}/${m[1]}` + (conHora && m[4] ? ` ${m[4]}:${m[5]}` : '');
    }

    function aviso(msg, tipo) {
        if (typeof window.showToast === 'function') return window.showToast(msg, tipo || 'info');
        let d = $('#repAvisoFlot');
        if (!d) {
            d = document.createElement('div');
            d.id = 'repAvisoFlot';
            d.className = 'inv-aviso-flot';
            document.body.appendChild(d);
        }
        d.className = 'inv-aviso-flot show ' + (tipo || '');
        d.textContent = msg;
        clearTimeout(d._t);
        d._t = setTimeout(() => d.classList.remove('show'), 4500);
    }

    async function api(url) {
        const r = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin' });
        let j = {};
        try { j = await r.json(); } catch (e) { /* respuesta no JSON */ }
        if (!r.ok || j.success === false) throw new Error(j.error || `Error ${r.status}`);
        return j;
    }

    // ============================================================
    // PESTAÑAS
    // ============================================================
    function irA(tab, rep) {
        tabActual = tab;
        $$('#repTabs .tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
        try { history.replaceState(null, '', '/reportes?tab=' + encodeURIComponent(tab)); } catch (e) { /* nada */ }
        if (window.abrirMenuModulo) window.abrirMenuModulo();   // el menú lateral marca el reporte abierto
        $('#rep-sec-tablero').classList.toggle('active', tab === 'tablero');
        $('#rep-sec-visor').classList.toggle('active', tab !== 'tablero');
        if (tab === 'tablero') return cargarTablero();
        const lista = Object.entries(CAT).filter(([, v]) => v.tab === tab).sort((a, b) => a[1].orden - b[1].orden);
        $('#repChips').innerHTML = lista.length > 1 ? lista.map(([k, v]) =>
            `<button type="button" class="rep-chip" data-rep="${k}"><b>${esc(v.titulo)}</b><small>${esc(v.ayuda)}</small></button>`).join('') : '';
        elegirReporte(rep && CAT[rep] ? rep : PESTANAS[tab]);
    }

    function elegirReporte(rep) {
        repActual = rep;
        const info = CAT[rep];
        $$('#repChips .rep-chip').forEach(c => c.classList.toggle('activo', c.dataset.rep === rep));
        $('#repTitulo').textContent = info.titulo;
        $('#repAyuda').textContent = info.ayuda;
        const f = $('#repFiltros');
        const usa = new Set(info.filtros.concat(info.agrupar && info.agrupar.length ? ['agrupar'] : []));
        $$('label[data-f]', f).forEach(l => { l.hidden = !usa.has(l.dataset.f); });
        $('#repAgrupar').innerHTML = (info.agrupar || []).map(([k, t]) => `<option value="${k}">${esc(t)}</option>`).join('');
        if (info.dias) f.dias.value = info.dias;
        cargarReporte();
    }

    // ============================================================
    // CATÁLOGOS (listas para los filtros)
    // ============================================================
    async function cargarCatalogos() {
        if (catalogos) return catalogos;
        const j = await api('/reportes/api/catalogos');
        catalogos = j;
        const emp = $('#repEmpresa');
        if (j.empresa_fija) {
            emp.innerHTML = `<option value="${esc(j.empresa_fija.id)}">${esc(j.empresa_fija.codigo)}</option>`;
            emp.disabled = true;
            emp.title = 'Para ver otra empresa cámbiala arriba a la derecha (o elige "Todas las empresas").';
        } else {
            emp.innerHTML = '<option value="">Todas</option>' + j.empresas.map(e => `<option value="${esc(e.id)}">${esc(e.codigo)}</option>`).join('');
        }
        $('#repSede').innerHTML = '<option value="">Todas</option>' + j.sedes.map(s => `<option value="${s.id}">${esc(s.nombre)}</option>`).join('');
        $('#repUsuario').innerHTML = '<option value="">Todos</option>' + j.usuarios.map(u => `<option value="${u.id}">${esc(u.nombre)}</option>`).join('');
        $('#repListaClientes').innerHTML = j.clientes.map(c => `<option value="${esc(c)}">`).join('');
        $('#repListaProveedores').innerHTML = j.proveedores.map(c => `<option value="${esc(c)}">`).join('');
        $('#repListaProductos').innerHTML = j.productos.map(c => `<option value="${esc(c)}">`).join('');
        const f = $('#repFiltros');
        f.desde.value = j.inicio_mes;
        f.hasta.value = j.hoy;
        return j;
    }

    function parametros() {
        const f = $('#repFiltros');
        const p = new URLSearchParams();
        $$('label[data-f]', f).forEach(l => {
            if (l.hidden) return;
            $$('input[name],select[name]', l).forEach(el => {
                let v = (el.value || '').trim();
                // "COD · Descripción" del autocompletado: se busca por el código
                if (el.name === 'producto' && v.includes(' · ')) v = v.split(' · ')[0];
                if (v) p.set(el.name, v);
            });
        });
        return p;
    }

    function rango(tipo) {
        const hoy = new Date(catalogos ? catalogos.hoy + 'T12:00:00' : Date.now());
        const iso = d => d.toISOString().slice(0, 10);
        let desde = new Date(hoy), hasta = new Date(hoy);
        if (tipo === 'mes') desde.setDate(1);
        else if (tipo === 'mes_ant') { desde = new Date(hoy.getFullYear(), hoy.getMonth() - 1, 1, 12); hasta = new Date(hoy.getFullYear(), hoy.getMonth(), 0, 12); }
        else if (tipo === '30' || tipo === '90') desde.setDate(desde.getDate() - Number(tipo) + 1);
        else if (tipo === 'anio') desde = new Date(hoy.getFullYear(), 0, 1, 12);
        else if (tipo === '12m') desde = new Date(hoy.getFullYear(), hoy.getMonth() - 11, 1, 12);
        else return;
        const f = $('#repFiltros');
        f.desde.value = iso(desde);
        f.hasta.value = iso(hasta);
    }

    // ============================================================
    // VISOR
    // ============================================================
    function celda(v, c) {
        if (v === null || v === undefined || v === '') return '<td class="cero">—</td>';
        switch (c.tipo) {
            case 'dinero': return `<td class="num${v < 0 ? ' neg' : ''}">${soles(v)}</td>`;
            case 'num': return `<td class="num">${numero(v)}</td>`;
            case 'dias1': return `<td class="num">${numero(v)} días</td>`;
            case 'pct': return `<td class="num">${pct(v)}</td>`;
            case 'margen': {
                const cls = v < 0 ? 'rep-mal sem-peligro' : v < 15 ? 'rep-medio sem-atencion' : 'rep-bien sem-ok';
                return `<td class="num"><span class="rep-pill ${cls}">${pct(v)}</span></td>`;
            }
            case 'semaforo': {
                const cls = v >= 50 ? 'rep-bien sem-ok' : v >= 25 ? 'rep-medio sem-atencion' : 'rep-mal sem-peligro';
                return `<td class="num"><span class="rep-pill ${cls}">${pct(v)}</span></td>`;
            }
            case 'fecha': return `<td>${fecha(v)}</td>`;
            case 'fechahora': return `<td>${fecha(v, true)}</td>`;
            case 'estado': {
                const cls = { 'Vencido': 'rep-mal sem-peligro', 'Por vencer': 'rep-medio sem-atencion', 'Al día': 'rep-bien sem-ok' }[v] || '';
                const ico = { 'Vencido': '🔴', 'Por vencer': '🟡', 'Al día': '🟢' }[v] || '';
                return `<td><span class="rep-pill ${cls}">${ico} ${esc(v)}</span></td>`;
            }
            case 'atraso':
                if (typeof v === 'string') return `<td><span class="rep-pill rep-medio sem-atencion">${esc(v)}</span></td>`;
                return v > 0 ? `<td class="num"><b class="rep-atraso">${numero(v)} días</b></td>` : '<td class="cero">—</td>';
            case 'rot': {
                const cls = 'rot-' + String(v).toLowerCase().replace(/\s+/g, '-');
                return `<td><span class="rot ${cls}">${esc(v)}</span></td>`;
            }
            default: return `<td class="left">${esc(v)}</td>`;
        }
    }

    function pintarResumen(cont, items) {
        cont.innerHTML = (items || []).map(x => {
            const val = x.tipo === 'dinero' ? soles(x.v) : x.tipo === 'pct' ? pct(x.v) : numero(x.v);
            const cls = x.color === 'danger' ? 'inv-kpi-danger' : x.color === 'warn' ? 'inv-kpi-warn' : x.color === 'ok' ? 'rep-kpi-ok' : x.color === 'cobro' ? 'rep-kpi-cobro' : x.color === 'pago' ? 'rep-kpi-pago' : '';
            return `<div class="inv-kpi ${cls}"><small>${esc(x.t)}</small><b>${val}</b>${x.sub ? `<span>${esc(x.sub)}</span>` : ''}</div>`;
        }).join('');
    }

    function pintarTabla(t) {
        if (!t.filas.length) {
            $('#repTabla').innerHTML = '<div class="inv-vacio">No hay datos con estos filtros. Prueba con otras fechas o quita filtros.</div>';
            return;
        }
        const cab = t.columnas.map(c => `<th>${esc(c.t)}</th>`).join('');
        const filas = t.filas.map(r => {
            const cls = r.estado === 'Vencido' ? ' class="rep-fila-vencida"' : '';
            return `<tr${cls}>` + t.columnas.map(c => celda(r[c.k], c)).join('') + '</tr>';
        }).join('');
        let pie = '';
        if (Object.keys(t.totales || {}).length) {
            pie = '<tfoot><tr>' + t.columnas.map((c, i) => {
                if (c.k in t.totales) return celda(t.totales[c.k], c).replace('<td', '<td data-total');
                return i === 0 ? '<td class="left"><b>TOTAL</b></td>' : '<td></td>';
            }).join('') + '</tr></tfoot>';
        }
        $('#repTabla').innerHTML = `<table class="inv-table rep-table"><thead><tr>${cab}</tr></thead><tbody>${filas}</tbody>${pie}</table>`;
    }

    // Barras horizontales simples (una sola serie, sin librerías)
    function barrasH(cont, filas, etiqueta, valor, esDinero) {
        const datos = filas.filter(r => Number(r[valor]) > 0).slice(0, 12);
        if (datos.length < 2) { cont.hidden = true; return; }
        const max = Math.max(...datos.map(r => Number(r[valor])));
        cont.hidden = false;
        cont.innerHTML = datos.map(r => {
            const w = Math.max(1, Math.round(Number(r[valor]) * 100 / max));
            const txt = esDinero ? soles(r[valor]) : numero(r[valor]);
            return `<div class="rep-barra" title="${esc(r[etiqueta])}: ${txt}">
                <span class="rep-barra-txt">${esc(r[etiqueta])}</span>
                <span class="rep-barra-fondo"><span class="rep-barra-val" style="width:${w}%"></span></span>
                <b>${txt}</b></div>`;
        }).join('');
    }

    async function cargarReporte() {
        if (!repActual) return;
        const p = parametros();
        const turno = ++pedido;
        $('#repTabla').innerHTML = '<div class="inv-vacio">Calculando...</div>';
        $('#repPie').textContent = '';
        try {
            const j = await api(`/reportes/api/reporte/${repActual}?${p}`);
            if (turno !== pedido) return;   // llegó la respuesta de un reporte anterior
            const t = j.data;
            ultimo = t;
            $('#repTitulo').textContent = t.titulo;
            pintarResumen($('#repResumen'), t.resumen);
            pintarTabla(t);
            const g = t.grafico;
            const col = g && t.columnas.find(c => c.k === g.valor);
            if (g && col) barrasH($('#repGrafico'), t.filas, g.etiqueta, g.valor, col.tipo === 'dinero');
            else $('#repGrafico').hidden = true;
            $('#repPie').innerHTML = `${t.filas.length} fila(s) · ${esc(t.filtros_texto)}` + (t.nota ? `<br>ℹ️ ${esc(t.nota)}` : '');
        } catch (e) {
            if (turno !== pedido) return;
            $('#repResumen').innerHTML = '';
            $('#repGrafico').hidden = true;
            $('#repTabla').innerHTML = `<div class="inv-alerta danger" style="margin:12px">${esc(e.message)}</div>`;
        }
    }

    function exportar(formato) {
        if (!repActual) return;
        const p = parametros();
        p.set('formato', formato);
        window.location.href = `/reportes/api/reporte/${repActual}/exportar?${p}`;
        aviso('Preparando el archivo... se descargará en unos segundos.', 'success');
    }

    // ============================================================
    // TABLERO
    // ============================================================
    function variacion(v, texto) {
        if (v === null || v === undefined) return `<span>${texto}: sin ventas para comparar</span>`;
        const sube = v >= 0;
        return `<span class="${sube ? 'rep-sube' : 'rep-baja'}">${sube ? '▲' : '▼'} ${pct(Math.abs(v))} ${texto}</span>`;
    }

    function graficoMeses(cont, datos) {
        const W = 640, H = 230, izq = 8, abajo = 26, arriba = 22;
        const max = Math.max(1, ...datos.map(d => d.total));
        const ancho = (W - izq * 2) / datos.length;
        const barras = datos.map((d, i) => {
            const h = Math.round((H - abajo - arriba) * d.total / max);
            const x = izq + i * ancho + ancho * 0.18;
            const y = H - abajo - h;
            const ult = i === datos.length - 1;
            const etiqueta = d.total > 0 && (ult || d.total === max)
                ? `<text x="${x + ancho * 0.32}" y="${y - 6}" text-anchor="middle" class="rep-svg-val">${(d.total / 1000).toLocaleString('es-PE', { maximumFractionDigits: 1 })} mil</text>` : '';
            return `<g class="rep-svg-bar${ult ? ' actual' : ''}"><title>${esc(d.mes)}: ${soles(d.total)} (${d.documentos} comprobantes)</title>
                <rect x="${x - ancho * 0.12}" y="${arriba}" width="${ancho * 0.88}" height="${H - abajo - arriba}" fill="transparent"></rect>
                <path d="M${x},${H - abajo} V${y + Math.min(4, h)} q0,-4 4,-4 h${ancho * 0.64 - 8} q4,0 4,4 V${H - abajo} Z"></path>
                ${etiqueta}
                <text x="${x + ancho * 0.32}" y="${H - 8}" text-anchor="middle" class="rep-svg-eje">${esc(d.mes)}</text></g>`;
        }).join('');
        cont.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Ventas por mes">
            <line x1="${izq}" x2="${W - izq}" y1="${H - abajo}" y2="${H - abajo}" class="rep-svg-base"></line>${barras}</svg>`;
    }

    async function cargarTablero() {
        try {
            const j = await api('/reportes/api/tablero');
            const d = j.data;
            $('#tabCargando').hidden = true;
            $('#tabContenido').hidden = false;
            const margen = d.margen_mes === null ? '—' : pct(d.margen_mes);
            $('#tabKpis').innerHTML = `
                <div class="inv-kpi rep-kpi-ok rep-kpi-xl"><small>Ventas de ${esc(d.mes_nombre)} (con IGV)</small><b>${soles(d.venta_mes)}</b>
                    ${variacion(d.variacion_avance, `vs. ${esc(d.mes_anterior_nombre)} al día ${d.dia_avance}`)}
                    <span>Mes anterior completo: ${soles(d.venta_mes_anterior)} ${d.variacion === null ? '' : '(' + (d.variacion >= 0 ? '+' : '') + pct(d.variacion) + ')'}</span></div>
                <div class="inv-kpi"><small>Margen del mes</small><b>${margen}</b><span>Utilidad bruta ${soles(d.utilidad_mes)} sobre ${soles(d.venta_mes_sub)} sin IGV</span></div>
                <div class="inv-kpi"><small>Comprobantes del mes</small><b>${numero(d.documentos_mes)}</b><span>Ticket promedio ${soles(d.ticket_mes)} · ${d.clientes_mes} clientes</span></div>
                <div class="inv-kpi"><small>Cotizaciones del mes</small><b>${numero(d.cotizaciones_mes)}</b><span>${d.cotizaciones_conv} aceptadas · ${soles(d.cotizado_mes)} cotizado</span></div>
                <div class="inv-kpi ${d.cxc_vencido > 0 ? 'inv-kpi-danger' : 'rep-kpi-ok'}"><small>Por cobrar VENCIDO</small><b>${soles(d.cxc_vencido)}</b><span>${d.cxc_vencido_docs} documentos · por vencer ${soles(d.cxc_por_vencer)}</span></div>
                <div class="inv-kpi ${d.cxp_vencido > 0 ? 'inv-kpi-warn' : 'rep-kpi-ok'}"><small>Por pagar vencido</small><b>${soles(d.cxp_vencido)}</b><span>Por vencer (7 días) ${soles(d.cxp_por_vencer)}</span></div>
                ${d.notas_credito_mes > 0 ? `<div class="inv-kpi inv-kpi-warn"><small>Notas de crédito del mes</small><b>${soles(d.notas_credito_mes)}</b><span>Venta neta ${soles(d.venta_mes - d.notas_credito_mes)}</span></div>` : ''}`;
            graficoMeses($('#tabGrafico'), d.por_mes);
            const lista = (filas, fn, vacio) => filas.length
                ? `<table class="inv-table rep-table">${filas.map(fn).join('')}</table>` : `<div class="inv-vacio">${vacio}</div>`;
            $('#tabCxc').innerHTML = lista(d.cxc_peores, x => `<tr class="rep-fila-vencida"><td class="left"><b>${esc(x.cliente)}</b><small>${esc(x.documento)}</small></td>
                <td class="num"><b class="rep-atraso">${x.dias} días</b></td><td class="num"><b>${soles(x.saldo)}</b></td></tr>`, '🟢 No hay cobranzas vencidas.');
            $('#tabTop').innerHTML = lista(d.top_clientes, (x, i) => `<tr><td class="num">${i + 1}</td><td class="left"><b>${esc(x.cliente)}</b><small>${x.documentos} compras · última ${esc(x.ultima)}</small></td>
                <td class="num"><b>${soles(x.total)}</b></td></tr>`, 'Aún no hay ventas en los últimos 12 meses.');
            $('#tabPerdidos').innerHTML = lista(d.perdidos, x => `<tr><td class="left"><b>${esc(x.cliente)}</b><small>Compró ${soles(x.total)} en total</small></td>
                <td class="num"><span class="rep-pill rep-medio sem-atencion">${x.dias} días sin comprar</span></td></tr>`, '🟢 Ningún cliente dejó de comprar.')
                + (d.perdidos_total > 5 ? `<div class="inv-foot">Y ${d.perdidos_total - 5} más.</div>` : '');
        } catch (e) {
            $('#tabCargando').hidden = false;
            $('#tabCargando').innerHTML = `<div class="inv-alerta danger">${esc(e.message)}</div>`;
        }
    }

    // ============================================================
    // EVENTOS
    // ============================================================
    document.addEventListener('click', ev => {
        const t = ev.target;
        const tab = t.closest('#repTabs .tab-btn');
        if (tab) return irA(tab.dataset.tab);
        const chip = t.closest('.rep-chip');
        if (chip) return elegirReporte(chip.dataset.rep);
        const ir = t.closest('[data-ir]');
        if (ir) return irA(ir.dataset.ir, ir.dataset.rep);
        const exp = t.closest('[data-exp]');
        if (exp) return exportar(exp.dataset.exp);
    });
    document.addEventListener('DOMContentLoaded', init);
    if (document.readyState !== 'loading') init();

    let iniciado = false;
    async function init() {
        if (iniciado || !$('#repApp')) return;
        iniciado = true;
        $('#repFiltros').addEventListener('submit', ev => { ev.preventDefault(); cargarReporte(); });
        $('#repRango').addEventListener('change', ev => { rango(ev.target.value); });
        $('#repAgrupar').addEventListener('change', cargarReporte);
        $('#repLimpiar').addEventListener('click', () => {
            const f = $('#repFiltros');
            ['cliente', 'proveedor', 'producto', 'estado'].forEach(n => { f[n].value = ''; });
            ['almacen_id', 'usuario_id'].forEach(n => { f[n].value = ''; });
            if (!$('#repEmpresa').disabled) f.empresa_id.value = '';
            f.desde.value = catalogos.inicio_mes;
            f.hasta.value = catalogos.hoy;
            $('#repRango').value = '';
            cargarReporte();
        });
        try {
            await cargarCatalogos();
        } catch (e) {
            aviso(e.message, 'error');
        }
        const params = new URLSearchParams(location.search);
        let tab = params.get('tab');
        if (!tab || !$(`#repTabs .tab-btn[data-tab="${tab}"]`)) tab = 'tablero';
        irA(tab, params.get('reporte'));
    }
})();
