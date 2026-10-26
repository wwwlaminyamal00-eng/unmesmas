// static/js/seguimiento.js - Seguimiento comercial (pedido de Erika 21/10/2026)
(function () {
    'use strict';
    const $ = (s, r = document) => r.querySelector(s);
    const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
    const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const num = v => Number(v || 0);
    const soles = v => 'S/ ' + num(v).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const pct = v => v === null || v === undefined ? '—' : num(v).toLocaleString('es-PE', { maximumFractionDigits: 2 }) + '%';
    const MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Setiembre', 'Octubre', 'Noviembre', 'Diciembre'];
    const TABS = ['llamar', 'cierre', 'historial'];
    let tab = 'llamar';
    let datos = null;
    let actual = null;

    function fecha(v) {
        if (!v) return '';
        const m = String(v).match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/);
        return m ? `${m[3]}/${m[2]}/${m[1]}` + (m[4] ? ` ${m[4]}:${m[5]}` : '') : esc(v);
    }
    function sumarDias(iso, n) {
        const d = new Date(iso + 'T12:00:00');
        d.setDate(d.getDate() + n);
        return d.toISOString().slice(0, 10);
    }
    function aviso(msg, tipo) {
        if (typeof window.showToast === 'function') return window.showToast(msg, tipo || 'info');
        alert(msg);
    }
    async function api(url, opciones) {
        const o = Object.assign({ headers: { 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin' }, opciones || {});
        if (o.body) { o.headers['Content-Type'] = 'application/json'; o.body = JSON.stringify(o.body); }
        const r = await fetch(url, o);
        let j = {};
        try { j = await r.json(); } catch (e) { /* sin JSON */ }
        if (!r.ok || j.success === false) throw new Error(j.error || `Error ${r.status}`);
        return j;
    }
    const kpi = (titulo, valor, pie, clase) => `<div class="inv-kpi ${clase || ''}"><small>${titulo}</small><b>${valor}</b><span>${pie || ''}</span></div>`;
    const empresa = () => $('#segEmpresa').value;
    const verTodas = () => empresa() === 'todas';

    function irA(t) {
        tab = TABS.includes(t) ? t : 'llamar';
        $$('#segTabs .tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
        TABS.forEach(x => $('#seg-sec-' + x).classList.toggle('active', x === tab));
        try { history.replaceState(null, '', '/seguimiento?tab=' + tab); } catch (e) { /* nada */ }
        if (window.abrirMenuModulo) window.abrirMenuModulo();
        if (tab === 'historial') cargarHistorial();
    }

    async function cargar() {
        $('#segKpis').innerHTML = '<div class="inv-vacio">Calculando...</div>';
        try {
            const q = new URLSearchParams({ empresa_id: empresa(), dias: $('#segDias').value });
            datos = (await api('/seguimiento/api/resumen?' + q)).data;
        } catch (e) {
            $('#segKpis').innerHTML = `<div class="inv-vacio">⚠ ${esc(e.message)}</div>`;
            return;
        }
        pintar();
        if (tab === 'historial') cargarHistorial();
    }

    function pintar() {
        const k = datos.kpis;
        $('#segKpis').innerHTML = [
            kpi('Llamar hoy', k.llamar_hoy, k.atrasadas ? `${k.atrasadas} atrasada(s)` : 'Al día', k.llamar_hoy ? 'ge-kpi-mal' : 'ge-kpi-ok'),
            kpi('Sin cerrar', k.abiertas, 'Esperando respuesta del cliente', k.abiertas ? 'ge-kpi-cobro' : 'ge-kpi-ok'),
            kpi('Monto sin cerrar', soles(k.monto_abierto), 'Con IGV', 'ge-kpi-cobro'),
            kpi('Vigencia vencida', k.vencidas, k.vencidas ? 'Confirmar precio antes de cerrar' : 'Todas vigentes', k.vencidas ? 'ge-kpi-mal' : 'ge-kpi-ok'),
            kpi(`Tasa de cierre · ${datos.dias_periodo} días`, pct(k.tasa), `${k.ganadas} ganadas de ${k.enviadas}`, k.tasa === null ? 'ge-kpi-gris' : 'ge-kpi-ok'),
            kpi('Ganado este mes', soles(k.ganado_mes), 'Aceptadas o con PC', 'ge-kpi-ok')
        ].join('');
        pintarAbiertas();
        pintarPorEnviar();
        pintarCierre();
    }

    const colEmpresa = () => verTodas() ? '<th>Empresa</th>' : '';
    const celEmpresa = c => verTodas() ? `<td><b>${esc(c.empresa)}</b></td>` : '';
    const linkPdf = c => `<a href="/ventas/api/cotizaciones/${c.id}/pdf/preview" target="_blank" rel="noopener">${esc(c.numero)}</a>`;
    // Celular peruano (9 dígitos que empiezan en 9, con o sin 51) -> número para WhatsApp; si no, null.
    function celularWhatsapp(t) {
        let d = String(t || '').replace(/\D/g, '');
        if (d.length === 11 && d.startsWith('51')) d = d.slice(2);
        return /^9\d{8}$/.test(d) ? '51' + d : null;
    }
    function contacto(c) {
        const wa = celularWhatsapp(c.telefono);
        const texto = `Hola${c.contacto ? ' ' + c.contacto : ''}, le escribimos por la cotización N° ${c.numero}. ¿Pudo revisarla? Quedamos atentos.`;
        const tel = !c.telefono ? '<span class="ge-sin ge-nw">Sin teléfono</span>'
            : wa ? `<a class="ge-nw ge-wa" href="https://wa.me/${wa}?text=${encodeURIComponent(texto)}" target="_blank" rel="noopener" title="Abrir WhatsApp con un mensaje sobre esta cotización">🟢 ${esc(c.telefono)}</a>`
            : `<a class="ge-nw" href="tel:${esc(String(c.telefono).replace(/[^\d+]/g, ''))}">${esc(c.telefono)}</a><span class="ge-sub ge-nw">No es celular: sin WhatsApp</span>`;
        return `${c.contacto ? `<b>${esc(c.contacto)}</b><span class="ge-sub">${tel}</span>` : tel}`;
    }

    const cantidad = v => num(v).toLocaleString('es-PE', { maximumFractionDigits: 2 });
    const celProductos = c => !(c.productos || []).length ? '<span class="ge-sin">Sin productos</span>'
        : c.productos.map(p => `<span class="ge-prod">${cantidad(p.cantidad)} × ${esc(p.descripcion)}</span>`).join('');

    function filtrarAbiertas() {
        const q = ($('#segBuscar')?.value || '').trim().toLowerCase();
        let vistas = 0;
        $$('#segAbiertas tbody tr').forEach(tr => {
            const ok = !q || tr.textContent.toLowerCase().includes(q);
            tr.hidden = !ok;
            if (ok) vistas++;
        });
        const n = $('#segBuscarN');
        if (n) n.textContent = q ? `${vistas} de ${datos.abiertas.length}` : '';
    }

    function pintarAbiertas() {
        const l = datos.abiertas;
        if (!l.length) { $('#segAbiertas').innerHTML = '<div class="ge-todo-ok">✔ No hay cotizaciones esperando respuesta</div>'; return; }
        $('#segAbiertas').innerHTML = `<table class="inv-table ge-tabla"><thead><tr>${colEmpresa()}<th>Cliente</th><th>RUC</th><th>N° cotización</th><th>Cantidad y producto</th><th>Fecha</th>
            <th>Total (S/)</th><th>Vendedora</th><th>Contacto</th><th>Última llamada</th><th>Próxima llamada</th><th>Acciones</th></tr></thead><tbody>
            ${l.map(c => `<tr class="${c.llamar_hoy ? 'ge-fila-pend' : ''}">${celEmpresa(c)}
                <td><b>${esc(c.cliente)}</b></td><td class="ge-nw">${esc(c.ruc || '')}</td><td class="ge-nw">${linkPdf(c)}</td>
                <td class="ge-desc ge-prods">${celProductos(c)}</td>
                <td>${fecha(c.fecha)}<span class="ge-sub">hace ${c.dias} días</span>${c.vence ? (c.vencida ? `<span class="ge-estado rojo">Vencida</span><span class="ge-sub">el ${fecha(c.vence)}</span>` : `<span class="ge-sub">Vence ${fecha(c.vence)}</span>`) : ''}</td>
                <td class="ge-nw"><b>${soles(c.total)}</b></td><td>${esc(c.vendedor)}</td><td>${contacto(c)}</td>
                <td class="ge-ultima">${c.ultima ? `<b>${esc(c.ultima.medio)}</b> · ${fecha(String(c.ultima.en).slice(0, 10))} · ${esc(c.ultima.por)}<span class="ge-sub">${esc(c.ultima.comentario)}</span>`
                    : '<span class="ge-sin ge-nw">Nunca se llamó</span>'}</td>
                <td>${c.llamar_hoy ? `<span class="ge-estado rojo">${c.atraso ? 'Atrasada' : 'Hoy'}</span><span class="ge-sub">${c.atraso ? `desde ${fecha(c.proxima_llamada)} (${c.atraso} días)` : fecha(c.proxima_llamada)}</span>`
                    : `<span class="ge-estado amarillo">${fecha(c.proxima_llamada)}</span>`}</td>
                <td><button type="button" class="ge-btn verde" data-llamar="${c.id}">Registrar llamada</button></td></tr>`).join('')}
            </tbody></table>`;
        filtrarAbiertas();
    }

    function pintarPorEnviar() {
        const l = datos.por_enviar;
        $('#segPorEnviarTit').textContent = `Cotizaciones que aún no se mandan al cliente (${l.length})`;
        $('#segPorEnviar').innerHTML = !l.length ? '<div class="inv-vacio">Ninguna.</div>'
            : `<table class="inv-table ge-tabla"><thead><tr>${colEmpresa()}<th>Cliente</th><th>N° cotización</th><th>Fecha</th><th>Total (S/)</th><th>Vendedora</th><th>Estado en Ventas</th></tr></thead><tbody>
            ${l.map(c => `<tr>${celEmpresa(c)}<td><b>${esc(c.cliente)}</b></td><td class="ge-nw">${linkPdf(c)}</td><td class="ge-nw">${fecha(c.fecha)}</td>
                <td class="ge-nw">${soles(c.total)}</td><td>${esc(c.vendedor)}</td><td><span class="ge-estado gris">${esc(c.estado)}</span></td></tr>`).join('')}</tbody></table>`;
    }

    function pintarCierre() {
        $('#segTitVend').textContent = `👩‍💼 Por vendedora · desde el ${fecha(datos.desde)}`;
        const v = datos.vendedoras;
        $('#segVendedoras').innerHTML = !v.length ? '<div class="inv-vacio">No hay cotizaciones enviadas en este periodo.</div>'
            : `<table class="inv-table ge-tabla"><thead><tr><th>Vendedora</th><th>Enviadas</th><th>Ganadas</th><th>Perdidas</th><th>Sin cerrar</th>
                <th>Tasa de cierre</th><th>Monto cotizado (S/)</th><th>Monto ganado (S/)</th><th>Días para cerrar (promedio)</th></tr></thead><tbody>
            ${v.map(x => `<tr><td><b>${esc(x.vendedor)}</b></td><td>${x.enviadas}</td><td><b>${x.ganadas}</b></td><td>${x.perdidas}</td><td>${x.abiertas}</td>
                <td><span class="ge-estado ${x.tasa >= 50 ? 'verde' : x.tasa >= 25 ? 'amarillo' : 'rojo'}">${pct(x.tasa)}</span></td>
                <td class="ge-nw">${soles(x.monto_enviado)}</td><td class="ge-nw"><b>${soles(x.monto_ganado)}</b></td><td>${x.dias ?? '—'}</td></tr>`).join('')}
            </tbody></table>`;
        $('#segMeses').innerHTML = `<table class="inv-table ge-tabla"><thead><tr><th>Mes</th><th>Enviadas</th><th>Ganadas</th><th>Perdidas</th><th>Tasa de cierre</th><th>Monto ganado (S/)</th></tr></thead><tbody>
            ${datos.meses.map(m => `<tr><td><b>${MESES[+m.periodo.slice(5) - 1]} ${m.periodo.slice(0, 4)}</b></td><td>${m.enviadas}</td><td>${m.ganadas}</td><td>${m.perdidas}</td>
                <td>${pct(m.tasa)}</td><td class="ge-nw">${m.monto_ganado ? soles(m.monto_ganado) : '<span class="ge-cero">—</span>'}</td></tr>`).join('')}</tbody></table>`;
        const p = datos.perdidas;
        $('#segPerdidas').innerHTML = !p.length ? '<div class="inv-vacio">Ninguna perdida en este periodo.</div>'
            : `<table class="inv-table ge-tabla"><thead><tr>${colEmpresa()}<th>Cliente</th><th>N° cotización</th><th>Fecha</th><th>Total (S/)</th><th>Vendedora</th><th>Motivo</th></tr></thead><tbody>
            ${p.map(c => `<tr>${celEmpresa(c)}<td><b>${esc(c.cliente)}</b></td><td class="ge-nw">${linkPdf(c)}</td><td class="ge-nw">${fecha(c.fecha)}</td>
                <td class="ge-nw">${soles(c.total)}</td><td>${esc(c.vendedor)}</td><td>${esc(c.motivo_perdida || '')}</td></tr>`).join('')}</tbody></table>`;
    }

    async function cargarHistorial() {
        try {
            const h = (await api('/seguimiento/api/historial?empresa_id=' + encodeURIComponent(empresa()))).data;
            $('#segHistorial').innerHTML = !h.length ? '<div class="inv-vacio">Todavía no se registró ninguna llamada.</div>'
                : `<table class="inv-table ge-tabla"><thead><tr><th>Fecha y hora</th><th>Cliente</th><th>RUC</th><th>N° cotización</th><th>Medio</th><th>Qué dijo el cliente</th><th>Próxima llamada</th><th>Registró</th></tr></thead><tbody>
                ${h.map(x => `<tr class="${x.cierre ? 'ge-fila-pend' : ''}"><td class="ge-nw">${fecha(x.creado_en)}</td><td><b>${esc(x.cliente || '')}</b></td><td class="ge-nw">${esc(x.ruc || '')}</td>
                    <td class="ge-nw">${esc(x.numero || '')}</td><td>${esc(x.medio)}</td><td class="ge-desc">${esc(x.comentario)}</td>
                    <td>${x.cierre ? `<span class="ge-estado rojo">No compró</span><span class="ge-sub">${esc(x.motivo_cierre || '')}</span>` : fecha(x.proxima_llamada)}</td>
                    <td>${esc(x.creado_por || '')}</td></tr>`).join('')}</tbody></table>`;
        } catch (e) {
            $('#segHistorial').innerHTML = `<div class="inv-vacio">⚠ ${esc(e.message)}</div>`;
        }
    }

    // ============================================================
    // REGISTRAR LLAMADA
    // ============================================================
    function ajustar() {
        const f = $('#segModalForm');
        const perdida = f.no_compro.checked;
        $('[data-si-perdida]', f).hidden = !perdida;
        $('[data-si-sigue]', f).hidden = perdida;
        f.motivo_cierre.required = perdida;
        f.proxima_llamada.required = !perdida;
        $('#segModalOk').textContent = perdida ? 'Marcar "No compró"' : 'Guardar llamada';
        $('#segModalOk').className = perdida ? 'btn btn-danger' : 'btn btn-primary';
    }
    function abrirLlamada(c) {
        actual = c;
        const f = $('#segModalForm');
        f.reset();
        f.proxima_llamada.min = datos.hoy;
        f.proxima_llamada.value = sumarDias(datos.hoy, 3);
        $('#segModalTit').textContent = `Registrar llamada · ${c.numero}`;
        $('#segModalDet').innerHTML = `<b>${esc(c.cliente)}</b> · ${soles(c.total)} · ${contacto(c)}`;
        ajustar();
        $('#segModal').hidden = false;
        f.comentario.focus();
    }
    const cerrar = () => { $('#segModal').hidden = true; actual = null; };

    document.addEventListener('DOMContentLoaded', () => {
        const app = $('#segApp');
        if (!app) return;
        $$('#segTabs .tab-btn').forEach(b => b.addEventListener('click', () => irA(b.dataset.tab)));
        irA(new URLSearchParams(location.search).get('tab') || 'llamar');
        $('#segEmpresa').addEventListener('change', cargar);
        $('#segDias').addEventListener('change', cargar);
        $('#segBuscar').addEventListener('input', filtrarAbiertas);
        $('#segModalCancelar').addEventListener('click', cerrar);
        $('#segModalForm').no_compro.addEventListener('change', ajustar);
        $('#segModalForm').addEventListener('submit', async ev => {
            ev.preventDefault();
            if (!actual) return;
            const f = ev.target;
            const ok = $('#segModalOk');
            ok.disabled = true;
            try {
                const j = await api(`/seguimiento/api/cotizacion/${actual.id}/gestion`, { method: 'POST', body: {
                    medio: f.medio.value, comentario: f.comentario.value, proxima_llamada: f.proxima_llamada.value,
                    no_compro: f.no_compro.checked, motivo_cierre: f.motivo_cierre.value } });
                aviso(j.message, 'success');
                cerrar();
                await cargar();
            } catch (e) { aviso(e.message, 'error'); } finally { ok.disabled = false; }
        });
        app.addEventListener('click', ev => {
            const b = ev.target.closest('button[data-llamar]');
            if (b) abrirLlamada(datos.abiertas.find(c => String(c.id) === b.dataset.llamar));
        });
        cargar();
    });
})();
