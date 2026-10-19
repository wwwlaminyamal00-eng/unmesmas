// static/js/finanzas.js - Módulo Finanzas (Vanilla JS)
(function () {
    'use strict';

    const app = document.getElementById('finanzasApp');
    if (!app) return;
    const PUEDE_OPERAR = app.dataset.puedeOperar === 'true';
    const datos = { cxc: [], cxp: [] };

    // ---------- utilidades ----------
    const soles = n => 'S/ ' + Number(n || 0).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const fecha = v => v ? String(v).slice(0, 10).split('-').reverse().join('/') : '—';
    const hoyISO = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    const semClase = s => 'sem sem-' + String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/\s+/g, '-');

    function aviso(msg, tipo) {
        if (typeof window.showToast === 'function') { window.showToast(msg, tipo || 'info'); return; }
        alert(msg);
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

    // ---------- KPIs ----------
    async function cargarResumen() {
        try {
            const { data } = await api('/finanzas/api/resumen');
            const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
            set('kpiPorCobrar', soles(data.por_cobrar));
            set('kpiPorCobrarDocs', `${data.documentos_por_cobrar} documentos · ${soles(data.por_cobrar_7dias)} vence en 7 días`);
            set('kpiCobrarVencido', soles(data.por_cobrar_vencido));
            set('kpiPorPagar', soles(data.por_pagar));
            set('kpiPorPagarDocs', `${data.documentos_por_pagar} documentos · ${soles(data.por_pagar_7dias)} vence en 7 días`);
            set('kpiPagarVencido', soles(data.por_pagar_vencido));
            set('kpiCobradoMes', soles(data.cobrado_mes));
            set('kpiPagadoMes', 'Pagado: ' + soles(data.pagado_mes));
            set('kpiNeta', soles(data.posicion_neta));
        } catch (e) { console.error('Resumen finanzas:', e); }
    }

    // ---------- CxC / CxP ----------
    async function cargarCuentas(tipo) {
        const body = document.getElementById(tipo + 'Body');
        const estado = document.getElementById(tipo + 'Estado').value;
        const q = document.getElementById(tipo + 'Buscar').value.trim();
        const params = new URLSearchParams({ estado, q });
        if (tipo === 'cxc') params.set('incluir_borradores', document.getElementById('cxcBorradores').checked);
        body.innerHTML = '<tr><td colspan="12">Cargando...</td></tr>';
        try {
            const { data, totales } = await api(`/finanzas/api/${tipo}?${params}`);
            datos[tipo] = data;   // CxP ya viene ordenado del servidor (vencido > por vencer > al día): no se reordena
            if (tipo === 'cxp') pintarTotalesCxp(totales);
            renderCuentas(tipo);
        } catch (e) {
            body.innerHTML = `<tr><td colspan="12" class="neg">No se pudo cargar: ${esc(e.message)}</td></tr>`;
        }
    }

    // Totales arriba de Cuentas por pagar (sobre todo lo pendiente, sin importar el filtro)
    function pintarTotalesCxp(t) {
        if (!t) return;
        const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
        set('cxpTotVencido', soles(t.vencido));
        set('cxpDocsVencido', `${t.docs_vencidos || 0} documento(s)`);
        set('cxpTotPorVencer', soles(t.por_vencer));
        set('cxpDocsPorVencer', `${t.docs_por_vencer || 0} documento(s)`);
        set('cxpTotAlDia', soles(t.al_dia));
        set('cxpTotTotal', soles(t.total));
    }

    // Chip de semáforo de CxP con días de atraso o días que faltan
    function chipCxp(x) {
        const n = x.dias_para_vencer;
        if (x.semaforo === 'Vencido') {
            const d = x.dias_vencido || 0;
            return `<span class="sem-chip sem-peligro">VENCIDO · ${d} día${d === 1 ? '' : 's'} de atraso</span>`;
        }
        if (x.semaforo === 'Por vencer') {
            return `<span class="sem-chip sem-atencion">POR VENCER · ${n === 0 ? 'vence hoy' : `faltan ${n} día${n === 1 ? '' : 's'}`}</span>`;
        }
        if (x.semaforo === 'Al día') {
            return `<span class="sem-chip sem-ok">AL DÍA${n !== null && n !== undefined ? ` · faltan ${n} días` : ''}</span>`;
        }
        return `<span class="${semClase(x.semaforo)}">${esc(x.semaforo)}</span>`;
    }

    function renderCuentas(tipo) {
        const body = document.getElementById(tipo + 'Body');
        const lista = datos[tipo];
        const esCxc = tipo === 'cxc';
        if (!lista.length) {
            body.innerHTML = `<tr><td colspan="12">No hay documentos para este filtro.</td></tr>`;
        } else {
            body.innerHTML = lista.map(x => {
                const accion = x.saldo > 0
                    ? `<button class="btn-mini" ${PUEDE_OPERAR ? '' : 'disabled title="Sin permiso"'} data-pagar="${tipo}:${x.id}">${esCxc ? 'Registrar cobro' : 'Registrar pago'}</button>`
                    : '<span class="sem sem-pagado">Pagado</span>';
                const venc = esCxc ? '' : (PUEDE_OPERAR ? ` <button class="btn-mini sec" title="Cambiar vencimiento" data-venc="${x.id}">📅</button>` : '');
                const chip = esCxc
                    ? `<span class="${semClase(x.semaforo)}">${esc(x.semaforo)}${x.dias_vencido ? ' · ' + x.dias_vencido + ' d' : ''}</span>`
                    : chipCxp(x);
                return `<tr class="${!esCxc && x.semaforo === 'Vencido' ? 'cxp-fila-vencida' : ''}">
                    <td>${chip}</td>
                    <td>${esc(x.tipo_comprobante || '')} ${esc(x.documento)}</td>
                    <td class="left">${esc(x.tercero)}</td>
                    <td>${esc(x.ruc)}</td>
                    <td>${fecha(x.fecha_emision)}</td>
                    <td>${fecha(x.fecha_vencimiento)}${venc}</td>
                    <td class="num">${soles(x.total)}</td>
                    ${esCxc ? `<td class="num">${soles(x.retencion)}</td><td class="num">${soles(x.notas_credito)}</td>` : ''}
                    <td class="num">${soles(x.abonado)}</td>
                    <td class="num saldo">${soles(x.saldo)}</td>
                    <td>${accion}</td>
                </tr>`;
            }).join('');
        }
        const total = lista.reduce((s, x) => s + x.saldo, 0);
        document.getElementById(tipo + 'Foot').textContent = `${lista.length} documentos · Saldo total: ${soles(total)}`;
    }

    // ---------- Movimientos ----------
    async function cargarMovimientos() {
        const body = document.getElementById('movBody');
        const tipo = document.getElementById('movTipo').value;
        try {
            const { data } = await api('/finanzas/api/movimientos' + (tipo ? `?tipo=${tipo}` : ''));
            body.innerHTML = data.length ? data.map(m => `<tr>
                <td>${fecha(m.fecha)}</td>
                <td><span class="badge ${m.tipo === 'COBRO' ? 'badge-ok' : 'badge-danger'}">${m.tipo === 'COBRO' ? 'Cobro' : 'Pago'}</span></td>
                <td>${esc(m.documento_numero)}</td>
                <td class="left">${esc(m.tercero_nombre)}</td>
                <td class="num">${soles(m.monto)}</td>
                <td>${esc(m.metodo)}</td>
                <td>${esc([m.banco, m.numero_operacion].filter(Boolean).join(' · ')) || '—'}</td>
                <td>${esc(m.usuario_nombre || '')}</td>
                <td>${m.estado === 'Anulado' ? `<span class="badge badge-gray" title="${esc(m.motivo_anulacion)}">Anulado</span>` : '<span class="badge badge-info">Registrado</span>'}</td>
                <td>${m.estado !== 'Anulado' && PUEDE_OPERAR ? `<button class="btn-mini danger" data-anular="${m.id}">Anular</button>` : ''}</td>
            </tr>`).join('') : '<tr><td colspan="10">Aún no hay cobros ni pagos registrados.</td></tr>';
        } catch (e) {
            body.innerHTML = `<tr><td colspan="10" class="neg">No se pudo cargar: ${esc(e.message)}</td></tr>`;
        }
    }

    // ---------- Flujo de caja ----------
    async function cargarFlujo() {
        const body = document.getElementById('flujoBody');
        try {
            const { data } = await api('/finanzas/api/flujo?semanas=' + document.getElementById('flujoSemanas').value);
            const max = Math.max(1, ...data.map(f => Math.max(f.ingresos, f.egresos)));
            body.innerHTML = data.map(f => `<tr>
                <td class="left">${esc(f.periodo)}</td>
                <td class="num">${soles(f.ingresos)}</td>
                <td class="num">${soles(f.egresos)}</td>
                <td class="num ${f.neto < 0 ? 'neg' : ''}">${soles(f.neto)}</td>
                <td class="num ${f.acumulado < 0 ? 'neg' : ''}">${soles(f.acumulado)}</td>
                <td class="left"><div class="bar-wrap">
                    <div class="bar bar-in" style="width:${(f.ingresos / max * 100).toFixed(1)}%"></div>
                    <div class="bar bar-out" style="width:${(f.egresos / max * 100).toFixed(1)}%"></div>
                </div></td>
            </tr>`).join('');
        } catch (e) {
            body.innerHTML = `<tr><td colspan="6" class="neg">No se pudo cargar: ${esc(e.message)}</td></tr>`;
        }
    }

    // ---------- Modales ----------
    const abrir = id => document.getElementById(id).classList.add('show');
    const cerrar = id => document.getElementById(id).classList.remove('show');

    function abrirPago(tipo, id) {
        const doc = datos[tipo].find(x => String(x.id) === String(id));
        if (!doc) return;
        const esCxc = tipo === 'cxc';
        document.getElementById('pagoTitulo').textContent = esCxc ? 'Registrar cobro' : 'Registrar pago';
        document.getElementById('pagoTipo').value = esCxc ? 'COBRO' : 'PAGO';
        document.getElementById('pagoDocId').value = doc.id;
        document.getElementById('pagoDoc').innerHTML =
            `${esc(doc.tipo_comprobante || '')} <b>${esc(doc.documento)}</b> · ${esc(doc.tercero)}<br>` +
            `Total ${soles(doc.total)} · Saldo pendiente <b>${soles(doc.saldo)}</b>`;
        document.getElementById('pagoMonto').value = doc.saldo.toFixed(2);
        document.getElementById('pagoMonto').max = doc.saldo.toFixed(2);
        document.getElementById('pagoFecha').value = hoyISO();
        ['pagoBanco', 'pagoOperacion', 'pagoObs'].forEach(i => { document.getElementById(i).value = ''; });
        abrir('pagoModal');
    }

    async function guardarPago() {
        const btn = document.getElementById('pagoGuardar');
        const monto = parseFloat(document.getElementById('pagoMonto').value);
        const max = parseFloat(document.getElementById('pagoMonto').max);
        if (!(monto > 0)) { aviso('Ingresa un monto mayor a 0', 'warning'); return; }
        if (monto > max + 0.001) { aviso('El monto no puede superar el saldo pendiente', 'warning'); return; }
        btn.disabled = true;
        try {
            const r = await api('/finanzas/api/movimientos', {
                method: 'POST',
                body: JSON.stringify({
                    tipo: document.getElementById('pagoTipo').value,
                    documento_id: document.getElementById('pagoDocId').value,
                    monto,
                    fecha: document.getElementById('pagoFecha').value,
                    metodo: document.getElementById('pagoMetodo').value,
                    banco: document.getElementById('pagoBanco').value,
                    numero_operacion: document.getElementById('pagoOperacion').value,
                    observaciones: document.getElementById('pagoObs').value
                })
            });
            aviso('✅ ' + r.message, 'success');
            cerrar('pagoModal');
            refrescarTodo();
        } catch (e) {
            aviso('❌ ' + e.message, 'error');
        } finally {
            btn.disabled = false;
        }
    }

    async function anularMovimiento(id) {
        const motivo = prompt('Motivo de la anulación (obligatorio):');
        if (motivo === null) return;
        if (!motivo.trim()) { aviso('El motivo es obligatorio', 'warning'); return; }
        try {
            await api(`/finanzas/api/movimientos/${id}/anular`, { method: 'POST', body: JSON.stringify({ motivo }) });
            aviso('Movimiento anulado', 'success');
            refrescarTodo();
        } catch (e) { aviso('❌ ' + e.message, 'error'); }
    }

    async function guardarVencimiento() {
        try {
            await api(`/finanzas/api/cxp/${document.getElementById('vencId').value}/vencimiento`, {
                method: 'PUT', body: JSON.stringify({ fecha_vencimiento: document.getElementById('vencFecha').value })
            });
            cerrar('vencModal');
            aviso('Fecha de vencimiento actualizada', 'success');
            cargarCuentas('cxp'); cargarResumen(); cargarFlujo();
        } catch (e) { aviso('❌ ' + e.message, 'error'); }
    }

    function exportarCSV(tipo) {
        const filas = datos[tipo];
        if (!filas.length) { aviso('No hay datos para exportar', 'warning'); return; }
        const cols = ['semaforo', 'tipo_comprobante', 'documento', 'tercero', 'ruc', 'fecha_emision', 'fecha_vencimiento', 'total', 'abonado', 'saldo'];
        const csv = [cols.join(';')].concat(filas.map(f => cols.map(c => `"${String(f[c] ?? '').replace(/"/g, '""')}"`).join(';'))).join('\n');
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' }));
        a.download = `${tipo}_${hoyISO()}.csv`;
        a.click();
        URL.revokeObjectURL(a.href);
    }

    function refrescarTodo() {
        cargarResumen(); cargarCuentas('cxc'); cargarCuentas('cxp'); cargarMovimientos(); cargarFlujo();
    }

    function activarTab(tab) {
        document.querySelectorAll('#finTabs .tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
        document.querySelectorAll('#finanzasApp > .section').forEach(s => s.classList.toggle('active', s.id === 'sec-' + tab));
    }

    // ---------- eventos ----------
    document.getElementById('finTabs').addEventListener('click', e => {
        const b = e.target.closest('.tab-btn');
        if (b) activarTab(b.dataset.tab);
    });
    ['cxc', 'cxp'].forEach(t => {
        let espera;
        document.getElementById(t + 'Buscar').addEventListener('input', () => { clearTimeout(espera); espera = setTimeout(() => cargarCuentas(t), 300); });
        document.getElementById(t + 'Estado').addEventListener('change', () => cargarCuentas(t));
    });
    document.getElementById('cxcBorradores').addEventListener('change', () => cargarCuentas('cxc'));
    document.getElementById('movTipo').addEventListener('change', cargarMovimientos);
    document.getElementById('flujoSemanas').addEventListener('change', cargarFlujo);
    document.getElementById('pagoGuardar').addEventListener('click', guardarPago);
    document.getElementById('vencGuardar').addEventListener('click', guardarVencimiento);
    document.addEventListener('click', e => {
        const t = e.target;
        if (t.dataset.close) cerrar(t.dataset.close);
        if (t.dataset.export) exportarCSV(t.dataset.export);
        if (t.dataset.pagar && !t.disabled) { const [tipo, id] = t.dataset.pagar.split(':'); abrirPago(tipo, id); }
        if (t.dataset.anular) anularMovimiento(t.dataset.anular);
        if (t.dataset.venc) {
            const doc = datos.cxp.find(x => String(x.id) === t.dataset.venc);
            document.getElementById('vencId').value = t.dataset.venc;
            document.getElementById('vencFecha').value = doc && doc.fecha_vencimiento ? String(doc.fecha_vencimiento).slice(0, 10) : hoyISO();
            abrir('vencModal');
        }
    });

    const tabInicial = new URLSearchParams(location.search).get('tab');
    if (['cxc', 'cxp', 'movimientos', 'flujo'].includes(tabInicial)) activarTab(tabInicial);
    refrescarTodo();
})();
