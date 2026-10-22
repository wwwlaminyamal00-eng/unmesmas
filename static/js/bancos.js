// static/js/bancos.js - Conciliación bancaria (pedido de Erika 21/10/2026)
(function () {
    'use strict';
    const $ = (s, r = document) => r.querySelector(s);
    const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
    const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const num = v => Number(v || 0);
    const soles = v => 'S/ ' + num(v).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const TABS = ['revisar', 'conciliados', 'extracto', 'archivos'];
    const APP = $('#banApp');
    const ADMIN = APP?.dataset.admin === 'true';
    const FINANZAS = APP?.dataset.finanzas === 'true';
    let tab = 'revisar';
    let datos = null;
    let alGuardar = null;

    function fecha(v) {
        if (!v) return '';
        const m = String(v).match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/);
        return m ? `${m[3]}/${m[2]}/${m[1]}` + (m[4] ? ` ${m[4]}:${m[5]}` : '') : esc(v);
    }
    function aviso(msg, tipo) {
        if (typeof window.showToast === 'function') return window.showToast(msg, tipo || 'info');
        alert(msg);
    }
    async function api(url, opciones) {
        const o = Object.assign({ headers: { 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin' }, opciones || {});
        if (o.body && !(o.body instanceof FormData)) { o.headers['Content-Type'] = 'application/json'; o.body = JSON.stringify(o.body); }
        const r = await fetch(url, o);
        let j = {};
        try { j = await r.json(); } catch (e) { /* sin JSON */ }
        if (!r.ok || j.success === false) throw new Error(j.error || `Error ${r.status}`);
        return j;
    }
    const empresa = () => $('#banEmpresa').value;

    // ============================================================
    // PESTAÑAS
    // ============================================================
    function irA(t) {
        tab = TABS.includes(t) ? t : 'revisar';
        $$('#banTabs .tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
        TABS.forEach(x => $('#ban-sec-' + x).classList.toggle('active', x === tab));
        try { history.replaceState(null, '', '/bancos?tab=' + tab); } catch (e) { /* nada */ }
        if (window.abrirMenuModulo) window.abrirMenuModulo();
    }

    async function cargar() {
        const q = new URLSearchParams({ empresa_id: empresa(), mes: $('#banMes').value || '', banco: $('#banBanco').value || '' });
        try {
            datos = (await api('/bancos/api/resumen?' + q)).data;
        } catch (e) {
            $('#banKpis').innerHTML = `<div class="inv-vacio">⚠ ${esc(e.message)}</div>`;
            return;
        }
        if (!$('#banMes').value) $('#banMes').value = datos.mes;
        const sel = $('#banBanco'), actual = sel.value;
        sel.innerHTML = '<option value="">Todos</option>' + datos.bancos_usados.map(b => `<option ${b === actual ? 'selected' : ''}>${esc(b)}</option>`).join('');
        pintar();
    }

    // ============================================================
    // TARJETAS (una fila, mismo tamaño)
    // ============================================================
    function kpi(titulo, valor, pie, clase) {
        return `<div class="inv-kpi ${clase || ''}"><small>${titulo}</small><b>${valor}</b><span>${pie || ''}</span></div>`;
    }
    function pintar() {
        const t = datos.tarjetas;
        $('#banKpis').innerHTML = [
            kpi('Movimientos del banco', t.movimientos, 'En el mes elegido'),
            kpi('✔ Conciliados', t.conciliados, t.movimientos ? Math.round(100 * (t.conciliados + t.gastos_banco_n) / t.movimientos) + '% revisado' : '', 'ge-kpi-ok'),
            kpi('⚠ En el banco, falta en el ERP', t.pendientes_banco, `Entra ${soles(t.pendientes_banco_entradas)} · Sale ${soles(Math.abs(t.pendientes_banco_salidas))}`, t.pendientes_banco ? 'ge-kpi-mal' : 'ge-kpi-ok'),
            kpi('⚠ En el ERP, no está en el banco', t.pendientes_erp, soles(t.pendientes_erp_monto), t.pendientes_erp ? 'ge-kpi-mal' : 'ge-kpi-ok'),
            kpi('Gastos del banco', soles(Math.abs(t.gastos_banco)), `${t.gastos_banco_n} (ITF, comisiones)`, 'ge-kpi-gris'),
        ].join('');
        pintarPendBanco();
        pintarPendErp();
        pintarConciliados();
        pintarTodo();
        pintarArchivos();
    }

    const entra = m => m.monto > 0 ? soles(m.monto) : '';
    const sale = m => m.monto < 0 ? soles(-m.monto) : '';

    function opcion(m, o) {
        const lado = m.monto > 0 ? 'cobro' : 'pago';
        if (o.tipo === 'movimiento') {
            return `<div class="ge-op ${o.exacto ? 'exacta' : ''}">
                <span><b>${lado === 'cobro' ? 'Cobro' : 'Pago'} registrado</b> · ${esc(o.tercero || '')} · N° factura ${esc(o.documento || '—')} · ${soles(o.monto)}${o.numero_operacion ? ' · N° op. ' + esc(o.numero_operacion) : ''} · ${fecha(o.fecha)}</span>
                <button type="button" class="ge-btn verde" data-unir="${m.id}" data-pago="${o.id}">Unir</button></div>`;
        }
        const boton = FINANZAS ? `<button type="button" class="ge-btn amarillo" data-registrar="${m.id}" data-doc="${o.id}">Registrar ${lado}</button>` : '';
        return `<div class="ge-op">
            <span><b>Factura por ${lado === 'cobro' ? 'cobrar' : 'pagar'}</b> · ${esc(o.tercero || '')} · N° factura ${esc(o.documento)} · saldo ${soles(o.monto)}</span>${boton}</div>`;
    }

    function pintarPendBanco() {
        const filas = datos.movimientos.filter(m => m.estado === 'Pendiente');
        if (!filas.length) {
            $('#banPendBanco').innerHTML = `<div class="ge-todo-ok">✔ Todo lo del banco está registrado en el ERP</div>`;
            return;
        }
        $('#banPendBanco').innerHTML = `<table class="inv-table ge-tabla"><thead><tr>
            <th>Fecha</th><th>Banco</th><th>N° operación</th><th>Descripción del banco</th><th>Entra (S/)</th><th>Sale (S/)</th>
            <th class="ge-col-ancha">Posible coincidencia</th><th>Acciones</th></tr></thead><tbody>
            ${filas.map(m => `<tr class="ge-fila-pend">
                <td class="ge-nw">${fecha(m.fecha)}</td><td>${esc(m.banco)}</td><td>${esc(m.numero_operacion || '—')}</td>
                <td class="ge-desc">${esc(m.descripcion || '')}</td>
                <td class="ge-entra">${entra(m)}</td><td class="ge-sale">${sale(m)}</td>
                <td class="ge-col-ancha">${(m.sugerencias || []).length ? m.sugerencias.map(o => opcion(m, o)).join('') : '<span class="ge-sin">Sin coincidencia en el ERP</span>'}</td>
                <td><button type="button" class="ge-btn" data-explicar="${m.id}">Explicar</button></td></tr>`).join('')}
            </tbody></table>`;
    }

    function pintarPendErp() {
        const filas = datos.sin_banco;
        if (!filas.length) {
            $('#banPendErp').innerHTML = `<div class="ge-todo-ok">✔ Todos los cobros y pagos registrados aparecen en el banco</div>`;
            return;
        }
        $('#banPendErp').innerHTML = `<table class="inv-table ge-tabla"><thead><tr>
            <th>Fecha</th><th>Cliente / Proveedor</th><th>RUC / DNI</th><th>N° factura</th><th>Tipo</th><th>Banco</th>
            <th>N° operación</th><th>Monto (S/)</th><th>Registrado por</th></tr></thead><tbody>
            ${filas.map(p => `<tr class="ge-fila-pend">
                <td class="ge-nw">${fecha(p.fecha)}</td><td>${esc(p.tercero || '')}</td><td class="ge-nw">${esc(p.ruc || '')}</td><td>${esc(p.documento || '')}</td>
                <td><span class="ge-tipo ${p.tipo === 'COBRO' ? 'cobro' : 'pago'}">${p.tipo === 'COBRO' ? 'Cobro' : 'Pago'}</span></td>
                <td>${esc(p.banco || '—')}</td><td>${esc(p.numero_operacion || '—')}</td><td><b>${soles(p.monto)}</b></td>
                <td>${esc(p.usuario || '')}<small class="ge-nw">${fecha(p.registrado)}</small></td></tr>`).join('')}
            </tbody></table>`;
    }

    function estadoChip(m) {
        const c = { 'Pendiente': 'rojo', 'Conciliado': 'verde', 'Revisado': 'verde', 'Gasto del banco': 'gris' }[m.estado] || 'gris';
        const txt = { 'Pendiente': '⏳ Pendiente', 'Conciliado': '✔ Conciliado', 'Revisado': '✔ Revisado', 'Gasto del banco': 'Gasto del banco' }[m.estado] || m.estado;
        return `<span class="ge-estado ${c}">${txt}</span>`;
    }

    function pintarConciliados() {
        const filas = datos.movimientos.filter(m => m.estado !== 'Pendiente');
        if (!filas.length) { $('#banConciliados').innerHTML = '<div class="inv-vacio">Aún no hay movimientos conciliados en este mes.</div>'; return; }
        $('#banConciliados').innerHTML = `<table class="inv-table ge-tabla"><thead><tr>
            <th>Fecha</th><th>Banco</th><th>N° operación</th><th>Descripción del banco</th><th>Entra (S/)</th><th>Sale (S/)</th>
            <th>Cliente / Proveedor</th><th>RUC / DNI</th><th>N° factura</th><th>Estado</th><th>Por</th><th>Acciones</th></tr></thead><tbody>
            ${filas.map(m => `<tr class="ge-fila-ok">
                <td class="ge-nw">${fecha(m.fecha)}</td><td>${esc(m.banco)}</td><td>${esc(m.numero_operacion || '—')}</td>
                <td class="ge-desc">${esc(m.descripcion || '')}</td><td class="ge-entra">${entra(m)}</td><td class="ge-sale">${sale(m)}</td>
                <td>${esc(m.tercero_nombre || '—')}</td><td class="ge-nw">${esc(m.tercero_documento || '—')}</td><td class="ge-nw">${esc(m.documento_numero || '—')}</td>
                <td>${estadoChip(m)}<small>${esc(m.forma || '')}${m.nota ? ' · ' + esc(m.nota) : ''}</small></td>
                <td>${esc(m.conciliado_por || '')}<small class="ge-nw">${fecha(m.conciliado_en)}</small></td>
                <td><button type="button" class="ge-btn" data-deshacer="${m.id}">Deshacer</button></td></tr>`).join('')}
            </tbody></table>`;
    }

    function pintarTodo() {
        const filas = datos.movimientos;
        if (!filas.length) { $('#banTodo').innerHTML = '<div class="inv-vacio">No hay movimientos del banco en este mes. Sube el extracto con el botón de arriba.</div>'; return; }
        $('#banTodo').innerHTML = `<table class="inv-table ge-tabla"><thead><tr>
            <th>Fecha</th><th>Banco</th><th>N° operación</th><th>Descripción del banco</th><th>Entra (S/)</th><th>Sale (S/)</th><th>Saldo (S/)</th><th>Estado</th></tr></thead><tbody>
            ${filas.map(m => `<tr class="${m.estado === 'Pendiente' ? 'ge-fila-pend' : 'ge-fila-ok'}">
                <td class="ge-nw">${fecha(m.fecha)}</td><td>${esc(m.banco)}</td><td>${esc(m.numero_operacion || '—')}</td><td class="ge-desc">${esc(m.descripcion || '')}</td>
                <td class="ge-entra">${entra(m)}</td><td class="ge-sale">${sale(m)}</td><td class="ge-nw">${m.saldo == null ? '' : soles(m.saldo)}</td><td>${estadoChip(m)}</td></tr>`).join('')}
            </tbody></table>`;
    }

    function pintarArchivos() {
        const filas = datos.extractos;
        if (!filas.length) { $('#banArchivos').innerHTML = '<div class="inv-vacio">Todavía no se subió ningún extracto de esta empresa.</div>'; return; }
        $('#banArchivos').innerHTML = `<table class="inv-table ge-tabla"><thead><tr>
            <th>Banco</th><th>N° de cuenta</th><th>Archivo</th><th>Desde</th><th>Hasta</th><th>Movimientos</th><th>Nuevos</th><th>Ya estaban</th><th>Subido por</th>${ADMIN ? '<th>Acciones</th>' : ''}</tr></thead><tbody>
            ${filas.map(x => `<tr><td>${esc(x.banco)}</td><td>${esc(x.cuenta || '—')}</td><td>${esc(x.archivo || '')}</td>
                <td class="ge-nw">${fecha(x.desde)}</td><td class="ge-nw">${fecha(x.hasta)}</td><td>${x.filas}</td><td>${x.nuevas}</td><td>${x.repetidas}</td>
                <td>${esc(x.creado_por || '')}<small class="ge-nw">${fecha(x.creado_en)}</small></td>
                ${ADMIN ? `<td><button type="button" class="ge-btn rojo" data-quitar="${x.id}">Quitar</button></td>` : ''}</tr>`).join('')}
            </tbody></table>`;
    }

    // ============================================================
    // VENTANA PEQUEÑA
    // ============================================================
    function abrirModal(titulo, detalle, campos, okTexto, fn) {
        $('#banModalTit').textContent = titulo;
        $('#banModalDet').innerHTML = detalle || '';
        $('#banModalCampos').innerHTML = campos;
        $('#banModalOk').textContent = okTexto || 'Guardar';
        alGuardar = fn;
        $('#banModal').hidden = false;
        const primero = $('#banModalCampos input, #banModalCampos select, #banModalCampos textarea');
        if (primero) primero.focus();
    }
    const cerrarModal = () => { $('#banModal').hidden = true; alGuardar = null; };
    const mov = id => datos.movimientos.find(m => String(m.id) === String(id));
    const detalleMov = m => `${fecha(m.fecha)} · ${esc(m.banco)} · ${esc(m.descripcion || '')} · <b>${soles(m.monto)}</b>`;

    async function enviar(url, body, msgOk) {
        const j = await api(url, { method: 'POST', body: Object.assign({ empresa_id: empresa() }, body) });
        aviso(j.message || msgOk || 'Listo', 'success');
        cerrarModal();
        await cargar();
    }

    document.addEventListener('click', async ev => {
        const b = ev.target.closest('button');
        if (!b || !APP.contains(b)) return;
        try {
            if (b.dataset.unir) {
                const m = mov(b.dataset.unir);
                const o = (m.sugerencias || []).find(x => x.tipo === 'movimiento' && String(x.id) === b.dataset.pago);
                if (o && o.exacto) return await enviar('/bancos/api/conciliar', { movimiento_id: m.id, pago_id: o.id });
                abrirModal('Unir con montos distintos', detalleMov(m) + `<br>ERP: ${esc(o?.tercero || '')} · ${soles(o?.monto)}`,
                    '<label>¿Por qué no es el mismo monto?<input name="nota" required maxlength="300" placeholder="Ej.: el banco cobró comisión"></label>', 'Unir',
                    f => enviar('/bancos/api/conciliar', { movimiento_id: m.id, pago_id: o.id, nota: f.nota.value }));
            } else if (b.dataset.registrar) {
                const m = mov(b.dataset.registrar);
                const o = (m.sugerencias || []).find(x => x.tipo === 'factura' && String(x.id) === b.dataset.doc);
                const tipo = m.monto > 0 ? 'COBRO' : 'PAGO';
                abrirModal(`Registrar ${tipo === 'COBRO' ? 'cobro' : 'pago'} y conciliar`,
                    `<div class="ge-ficha"><span>Cliente / Proveedor: <b>${esc(o.tercero)}</b></span><span>RUC / DNI: <b>${esc(o.ruc || '—')}</b></span>
                     <span>N° factura: <b>${esc(o.documento)}</b></span><span>Saldo de la factura: <b>${soles(o.monto)}</b></span>
                     <span>En el banco: <b>${fecha(m.fecha)} · ${esc(m.banco)} · ${soles(Math.abs(m.monto))}</b></span></div>`,
                    `<label>Monto (S/)<input name="monto" type="number" step="0.01" min="0.01" value="${Math.min(Math.abs(m.monto), o.monto).toFixed(2)}" required></label>
                     <label>N° de operación<input name="op" maxlength="80" value="${esc(m.numero_operacion || '')}" placeholder="Del extracto"></label>`,
                    'Registrar y conciliar', async f => {
                        const r = await api('/finanzas/api/movimientos', { method: 'POST', body: {
                            tipo, documento_id: o.id, monto: Number(f.monto.value), fecha: m.fecha, metodo: 'Transferencia',
                            banco: m.banco, numero_operacion: f.op.value || null, fecha_aviso: f.op.value ? null : m.fecha,
                            observaciones: 'Registrado desde Conciliación bancaria' } });
                        const nota = Math.abs(Math.abs(m.monto) - Number(f.monto.value)) > 0.01 ? 'Pago parcial de la factura' : null;
                        await enviar('/bancos/api/conciliar', { movimiento_id: m.id, pago_id: r.data.id, nota }, 'Registrado y conciliado');
                    });
            } else if (b.dataset.explicar) {
                const m = mov(b.dataset.explicar);
                abrirModal('¿Qué es este movimiento?', detalleMov(m),
                    `<label>Es
                        <select name="estado"><option value="Revisado">Otro movimiento revisado (préstamo, aporte, entre cuentas...)</option>
                        <option value="Gasto del banco">Gasto del banco (ITF, comisión, mantenimiento)</option></select></label>
                     <label>Explícalo en una línea<input name="nota" required maxlength="300" placeholder="Ej.: transferencia de KCF a AGD"></label>`,
                    'Guardar', f => enviar('/bancos/api/explicar', { movimiento_id: m.id, estado: f.estado.value, nota: f.nota.value }));
            } else if (b.dataset.deshacer) {
                const m = mov(b.dataset.deshacer);
                abrirModal('Deshacer', detalleMov(m), '<label>Motivo<input name="motivo" required maxlength="300"></label>', 'Deshacer',
                    f => enviar('/bancos/api/deshacer', { movimiento_id: m.id, motivo: f.motivo.value }));
            } else if (b.dataset.quitar) {
                abrirModal('Quitar extracto', 'Se quitan todos sus movimientos y lo conciliado con ellos. Tus cobros y pagos de Finanzas no cambian.',
                    '<label>Motivo<input name="motivo" required maxlength="300" placeholder="Ej.: subí el archivo de otra cuenta"></label>', 'Quitar',
                    f => enviar(`/bancos/api/extracto/${b.dataset.quitar}/quitar`, { motivo: f.motivo.value }));
            }
        } catch (e) { aviso('⚠ ' + e.message, 'error'); }
    });

    // ============================================================
    // INICIO
    // ============================================================
    document.addEventListener('DOMContentLoaded', () => {
        if (!APP) return;
        $$('#banTabs .tab-btn').forEach(b => b.addEventListener('click', () => irA(b.dataset.tab)));
        irA(new URLSearchParams(location.search).get('tab') || 'revisar');
        $('#banEmpresa').addEventListener('change', () => { $('#banMes').value = ''; $('#banBanco').value = ''; cargar(); });
        $('#banBanco').addEventListener('change', cargar);
        $('#banMes').addEventListener('change', cargar);
        $('#banAbrirSubir').addEventListener('click', () => { const f = $('#banFormSubir'); f.hidden = !f.hidden; });
        $('#banModalCancelar').addEventListener('click', cerrarModal);
        $('#banModalForm').addEventListener('submit', async ev => {
            ev.preventDefault();
            if (!alGuardar) return;
            const boton = $('#banModalOk');
            boton.disabled = true;
            try { await alGuardar(ev.target.elements); } catch (e) { aviso('⚠ ' + e.message, 'error'); } finally { boton.disabled = false; }
        });
        $('#banFormSubir').addEventListener('submit', async ev => {
            ev.preventDefault();
            const fd = new FormData(ev.target);
            fd.append('empresa_id', empresa());
            const boton = ev.target.querySelector('button[type=submit]');
            boton.disabled = true;
            try {
                const j = await api('/bancos/api/subir', { method: 'POST', body: fd });
                aviso('✔ ' + j.message, 'success');
                ev.target.reset();
                ev.target.hidden = true;
                $('#banMes').value = j.data.mes;
                await cargar();
                irA('revisar');
            } catch (e) { aviso('⚠ ' + e.message, 'error'); } finally { boton.disabled = false; }
        });
        cargar();
    });
})();
