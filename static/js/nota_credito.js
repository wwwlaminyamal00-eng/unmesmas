// static/js/nota_credito.js - Notas de crédito con aprobación (REGLA DE ORO de Erika, 26/10/2026)
// Solo Hellen crea y envía; solo Erika aprueba o rechaza. El monto nunca se escribe: sale de la factura.
// Reemplaza las funciones antiguas de ventas.js (formulario, lista y menú de notas de crédito).
(function () {
    'use strict';
    const IGV = 0.18;
    let permisos = { puede_crear: false, puede_aprobar: false, por_aprobar: 0, tipos: {}, causas: [] };
    let origenNC = null;      // datos de la factura afectada
    let notaNC = null;        // nota abierta (si se edita o revisa)
    let usuariosNC = [];
    const h = v => String(v ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    const m2 = n => (Math.round((Number(n) || 0) * 100) / 100).toFixed(2);
    const simbolo = mon => (mon === 'USD' ? 'US$' : 'S/');

    async function cargarPermisos() {
        try {
            const r = await apiFetch('/ventas/api/nc/permisos');
            if (r.success) permisos = r.data;
        } catch (e) { /* sin permisos: solo lectura */ }
        const btn = document.querySelector('#notas_credito .btn-create');
        if (btn) btn.style.display = permisos.puede_crear ? '' : 'none';
        const tab = document.querySelector('.tab-btn[data-tab="notas_credito"]');
        if (tab) {
            tab.querySelector('.nc-pend')?.remove();
            if (permisos.puede_aprobar && permisos.por_aprobar > 0)
                tab.insertAdjacentHTML('beforeend', `<span class="nc-pend" title="Notas de crédito por aprobar">${permisos.por_aprobar}</span>`);
        }
        return permisos;
    }

    // ------------------------------------------------------------------ lista
    function trazaCelda(r) {
        const filas = [['PV', r.pv], ['PC (Pedido del cliente)', r.pc_cliente], ['Guía', r.guia], ['Cotización', r.cotizacion]]
            .filter(x => x[1]).map(x => `<div class="nc-traza-linea"><small>${x[0]}</small> ${h(x[1])}</div>`);
        return filas.length ? filas.join('') : '<span style="color:#94A3B8">—</span>';
    }
    function quienCelda(r) {
        const a = r.creado_por_usuario ? `<div><small>Creó</small> ${h(r.creado_por_usuario)}</div>` : '';
        const b = r.aprobado_por ? `<div><small>${r.estado === 'Rechazada' ? 'Rechazó' : 'Aprobó'}</small> ${h(r.aprobado_por)}</div>` : '';
        const c = r.estado === 'Rechazada' && r.motivo_rechazo ? `<div class="nc-rechazo">${h(r.motivo_rechazo)}</div>` : '';
        return (a + b + c) || '<span style="color:#94A3B8">—</span>';
    }
    function renderNotasNC() {
        const q = document.getElementById('notaSearch')?.value?.toLowerCase() || '';
        const st = document.getElementById('notaStatus')?.value || '';
        const list = (window.notasData || notasData || []).filter(r => {
            const s = `${r.numero || ''} ${r.serie || ''} ${r.cliente || ''} ${r.ruc || ''} ${r.comprobante || ''} ${r.pv || ''} ${r.pc_cliente || ''}`.toLowerCase();
            return (!q || s.includes(q)) && (!st || r.estado === st);
        });
        const aviso = document.getElementById('ncAvisoAprobar');
        const pend = (notasData || []).filter(r => r.estado === 'Por aprobar').length;
        if (aviso) {
            aviso.style.display = permisos.puede_aprobar && pend ? 'flex' : 'none';
            aviso.querySelector('b').textContent = pend === 1 ? '1 nota de crédito' : `${pend} notas de crédito`;
        }
        const tbody = document.getElementById('notaRows');
        if (!tbody) return;
        if (!list.length) {
            tbody.innerHTML = `<tr><td colspan="12" style="text-align:center;color:#94A3B8;padding:40px;">📭 No hay notas de crédito registradas</td></tr>`;
            return;
        }
        const fecha = v => { const m = String(v || '').match(/^(\d{4})-(\d{2})-(\d{2})/); return m ? `${m[3]}/${m[2]}/${m[1]}` : sd(v); };
        tbody.innerHTML = list.map((r, i) => `
            <tr class="${r.estado === 'Por aprobar' ? 'nc-fila-pend' : ''}">
                <td>${i + 1}</td>
                <td class="date-cell"><b>${fecha(r.fecha)}</b>${tiemposHTML(r)}</td>
                <td>${badgeStatus(r.estado)}</td>
                <td>${numDocCelda(numDoc(r.serie, r.numero))}${badgeNuevo(r, 'fecha')}</td>
                <td>${r.comprobante ? numDocCelda(fmtNumDoc(r.comprobante), 'span') : '-'}${r.factura_fecha ? `<small class="nc-sub">${fecha(r.factura_fecha)}</small>` : ''}</td>
                <td class="left">${sd(r.cliente)}</td>
                <td>${sd(r.ruc)}</td>
                <td class="nc-traza">${trazaCelda(r)}</td>
                <td>${r.tipo_nota ? `<small class="nc-sub">${h(r.tipo_nota)}</small>` : ''}${sd(r.motivo)}</td>
                <td><b>${money(r.monto)}</b></td>
                <td class="nc-quien">${quienCelda(r)}</td>
                <td><button class="kebab" onclick="showNotaMenu(event, ${r.id})">⋮</button></td>
            </tr>`).join('');
    }

    function showNotaMenuNC(event, id) {
        event.stopPropagation();
        document.querySelectorAll('.menu-pop').forEach(el => el.remove());
        const r = (notasData || []).find(n => n.id === id) || {};
        const pop = document.createElement('div');
        pop.className = 'menu-pop';
        pop.style.left = Math.max(10, event.clientX - 250) + 'px';
        pop.style.top = Math.min(window.innerHeight - 300, event.clientY + 8) + 'px';
        const editable = permisos.puede_crear && ['Borrador', 'Por aprobar', 'Rechazada'].includes(r.estado);
        pop.innerHTML = `
            <button onclick="openNotaCreditoModal(${id});this.closest('.menu-pop').remove()">${editable ? '✏ Ver / Corregir' : '👁 Ver'}</button>
            ${permisos.puede_aprobar && r.estado === 'Por aprobar' ? `<button style="color:#0057FF;font-weight:900" onclick="openNotaCreditoModal(${id});this.closest('.menu-pop').remove()">✅ Revisar y aprobar / rechazar</button>` : ''}
            <button onclick="generateNotaPdf(${id});this.closest('.menu-pop').remove()">📄 Ver documento / PDF</button>
            ${permisos.puede_aprobar && r.estado === 'Emitida' ? `<div style="height:1px;background:#E5E7EB;margin:4px 0;"></div><button class="danger" onclick="anularNotaNC(${id});this.closest('.menu-pop').remove()">⛔ Anular</button>` : ''}`;
        document.body.appendChild(pop);
    }

    function anularNotaNC(id) {
        showConfirmModal('⛔ ¿Anular nota de crédito?', 'La nota deja de restar del saldo de la factura.', 'Solo Erika puede hacerlo.',
            async () => {
                try {
                    await apiFetch(`/ventas/api/notas-credito/${id}/toggle`, { method: 'PUT', body: JSON.stringify({ estado: 'Anulada' }) });
                    showToast('Nota de crédito anulada', 'success');
                    await loadNotas();
                } catch (e) { showToast('❌ ' + e.message, 'error'); }
            }, 'Sí, anular');
    }

    // ------------------------------------------------------------------ formulario
    function facturasElegibles() {
        return (comprobantesData || []).filter(c => {
            const e = String(c.estado || '').toUpperCase();
            return !['BORRADOR', 'ANULADO', 'ANULADA'].includes(e);
        });
    }

    function tarjeta(t, v, cls = '') {
        return `<div class="nc-dato ${cls}"><span>${t}</span><b>${v ? h(v) : '—'}</b></div>`;
    }

    function htmlTraza() {
        if (!origenNC) return '<div class="nc-vacio">Elige la factura afectada: la guía, el PV, el PC (Pedido del cliente) y la cotización se llenan solos.</div>';
        const o = origenNC, s = simbolo(o.moneda);
        const fecha = o.factura_fecha ? o.factura_fecha.split('-').reverse().join('/') : '';
        return `<div class="nc-datos">
            ${tarjeta('Factura afectada', o.factura + (fecha ? ' · ' + fecha : ''))}
            ${tarjeta('Cliente', o.cliente)}${tarjeta('RUC', o.ruc)}
            ${tarjeta('N° guía', o.guia)}${tarjeta('N° PV (Pedido de venta)', o.pv)}
            ${tarjeta('N° PC (Pedido del cliente)', o.pc_cliente)}${tarjeta('N° cotización', o.cotizacion)}
            ${tarjeta('Total de la factura', s + ' ' + m2(o.total))}
            ${tarjeta('Saldo que se puede acreditar', s + ' ' + m2(o.saldo), 'nc-saldo')}
        </div>`;
    }

    function htmlItems(soloLectura) {
        const tipo = document.getElementById('ncTipo')?.value || notaNC?.tipo_nota || '';
        if (!origenNC) return '';
        if (tipo === '07') {
            const dev = {};
            (notaNC?.items_json || []).forEach(it => { dev[it.idx] = it.cantidad; });
            return `<table class="nc-items"><thead><tr><th>Nombre producto</th><th>Cantidad facturada</th><th>Valor unitario (sin IGV)</th><th>Cantidad devuelta</th><th>Total (con IGV)</th></tr></thead><tbody>
                ${origenNC.items.map(it => `<tr><td class="left">${h(it.producto)}${typeof window.lineaClienteHTML === 'function' ? window.lineaClienteHTML(it) : ''}</td><td>${it.cantidad}</td><td>${m2(it.valor_unitario)}</td>
                    <td><input type="number" class="nc-cant" data-idx="${it.idx}" min="0" max="${it.cantidad}" step="1" value="${dev[it.idx] ?? 0}" ${soloLectura ? 'disabled' : ''} oninput="ncRecalcular()"></td>
                    <td class="nc-item-total" data-idx="${it.idx}">0.00</td></tr>`).join('')}
            </tbody></table>`;
        }
        if (tipo === '04') {
            return `<div class="form-field col-3" style="max-width:260px"><label>% de descuento global</label>
                <input id="ncPorcentaje" type="number" min="0.01" max="100" step="0.01" value="${notaNC?.porcentaje ?? ''}" ${soloLectura ? 'disabled' : ''} oninput="ncRecalcular()"></div>`;
        }
        if (['01', '02', '06'].includes(tipo)) {
            return `<div class="nc-nota-tipo">Esta nota acredita <b>todo el saldo</b> de la factura (${origenNC.items.length} producto(s)).</div>`;
        }
        return '';
    }

    function calcularLocal() {
        if (!origenNC) return 0;
        const tipo = document.getElementById('ncTipo')?.value || '';
        let monto = 0;
        if (['01', '02', '06'].includes(tipo)) monto = origenNC.saldo;
        else if (tipo === '07') {
            document.querySelectorAll('.nc-cant').forEach(inp => {
                const it = origenNC.items.find(x => String(x.idx) === inp.dataset.idx);
                const c = Math.min(Math.max(parseFloat(inp.value) || 0, 0), it ? it.cantidad : 0);
                const t = it ? Math.round(c * it.valor_unitario * (1 + IGV) * 100) / 100 : 0;
                const celda = document.querySelector(`.nc-item-total[data-idx="${inp.dataset.idx}"]`);
                if (celda) celda.textContent = m2(t);
                monto += t;
            });
        } else if (tipo === '04') monto = Math.round(origenNC.total * (parseFloat(document.getElementById('ncPorcentaje')?.value) || 0)) / 100;
        return Math.round(monto * 100) / 100;
    }

    function ncRecalcular() {
        const monto = calcularLocal();
        const s = simbolo(origenNC?.moneda);
        const sub = Math.round(monto / (1 + IGV) * 100) / 100;
        const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
        set('ncSub', `${s} ${m2(sub)}`); set('ncIgv', `${s} ${m2(monto - sub)}`); set('ncTotal', `${s} ${m2(monto)}`);
        const alerta = document.getElementById('ncAlertaSaldo');
        if (alerta) alerta.style.display = origenNC && monto > origenNC.saldo + 0.001 ? 'block' : 'none';
        const tipo = document.getElementById('ncTipo')?.value || '';
        const gd = document.getElementById('ncGuiaDevCaja');
        if (gd) gd.style.display = ['06', '07'].includes(tipo) ? '' : 'none';
        const resp = document.getElementById('ncRespCaja');
        if (resp) resp.querySelector('label').innerHTML = 'Responsable del error' + (document.getElementById('ncCausa')?.value === 'Error operativo' ? ' <b style="color:#DC2626">(obligatorio)</b>' : ' <small>(si aplica)</small>');
    }

    async function elegirFacturaNC(ref) {
        origenNC = null;
        if (ref) {
            try {
                const r = await apiFetch(`/ventas/api/nc/origen?comprobante=${encodeURIComponent(ref)}${notaNC ? '&excluir=' + notaNC.id : ''}`);
                origenNC = r.data;
            } catch (e) { showToast('❌ ' + e.message, 'error'); }
        }
        document.getElementById('ncTraza').innerHTML = htmlTraza();
        pintarItems();
    }

    function pintarItems() {
        const caja = document.getElementById('ncItems');
        if (caja) caja.innerHTML = htmlItems(!editable());
        ncRecalcular();
    }

    function editable() {
        return permisos.puede_crear && (!notaNC || ['Borrador', 'Por aprobar', 'Rechazada'].includes(notaNC.estado));
    }

    function htmlFormulario() {
        const ro = !editable();
        const dis = ro ? 'disabled' : '';
        const n = notaNC || {};
        const tipos = Object.entries(permisos.tipos || {}).map(([k, v]) => `<option value="${k}" ${n.tipo_nota === k ? 'selected' : ''}>${k} · ${h(v)}</option>`).join('');
        const causas = (permisos.causas || []).map(c => `<option ${n.causa_interna === c ? 'selected' : ''}>${h(c)}</option>`).join('');
        const usuarios = usuariosNC.map(u => `<option value="${h(u.nombre)}" ${n.responsable_error === u.nombre ? 'selected' : ''}>${h(u.nombre)} (${h(u.usuario)})</option>`).join('');
        const facturas = facturasElegibles().map(c => {
            const ref = `${c.serie}-${c.numero}`;
            const sel = n.comprobante_asociado && (fmtNumDoc(n.comprobante_asociado) === fmtNumDoc(ref) || n.comprobante_id === c.id) ? 'selected' : '';
            return `<option value="${c.id}" ${sel}>${h(fmtNumDoc(ref))} · ${h(c.cliente || '')} · ${money(c.monto)}</option>`;
        }).join('');
        const estadoTxt = n.estado ? `<div class="nc-estado-linea">Estado: ${badgeStatus(n.estado)}${n.serie ? ` · N° ${h(n.serie)}-${h(n.numero)}` : ''}
            ${n.estado === 'Rechazada' && n.motivo_rechazo ? `<div class="nc-rechazo">Erika la rechazó: ${h(n.motivo_rechazo)}</div>` : ''}</div>` : '';
        const regla = `<div class="nc-regla">🔒 <b>Regla de oro:</b> solo Hellen crea notas de crédito y solo Erika las aprueba. La nota no resta de la factura hasta que Erika la aprueba.</div>`;
        return `${regla}${estadoTxt}
        <div class="ficha-section">
            <div class="ficha-section-title">1. Factura afectada</div>
            <div class="ficha-grid"><div class="form-field col-6"><label>Factura o boleta emitida</label>
                <select id="ncFactura" ${dis} onchange="ncElegirFactura(this.value)"><option value="">-- Elige la factura --</option>${facturas}</select></div></div>
            <div id="ncTraza">${htmlTraza()}</div>
        </div>
        <div class="ficha-section">
            <div class="ficha-section-title">2. Tipo de nota (catálogo 09 de SUNAT) y sustento</div>
            <div class="ficha-grid">
                <div class="form-field col-6"><label>Tipo de nota</label>
                    <select id="ncTipo" ${dis} onchange="ncPintarItems()"><option value="">-- Elige el tipo --</option>${tipos}</select></div>
                <div class="form-field col-6" id="ncGuiaDevCaja" style="display:none"><label>N° guía de devolución / N° devolución <b style="color:#DC2626">(obligatorio)</b></label>
                    <input id="ncGuiaDev" ${dis} value="${h(n.guia_devolucion || '')}" placeholder="Con la que la mercadería regresó al almacén"></div>
                <div class="form-field col-12" id="ncItems"></div>
                <div class="form-field col-12"><label>Sustento para SUNAT <b style="color:#DC2626">(obligatorio)</b> <small>sale en el documento</small></label>
                    <textarea id="ncSustento" ${dis} placeholder="Ej.: El cliente devolvió 5 unidades por defecto de fábrica según su correo del 26/10/2026">${h(n.sustento || '')}</textarea></div>
            </div>
        </div>
        <div class="ficha-section">
            <div class="ficha-section-title">3. Importe (calculado, nadie lo escribe)</div>
            <div class="nc-importe">
                <div><span>Valor de venta (sin IGV)</span><b id="ncSub">—</b></div>
                <div><span>IGV 18%</span><b id="ncIgv">—</b></div>
                <div class="nc-total"><span>Total nota de crédito 🔒</span><b id="ncTotal">—</b></div>
            </div>
            <div id="ncAlertaSaldo" class="nc-rechazo" style="display:none">⚠️ Supera el saldo de la factura: el sistema no la dejará guardar.</div>
        </div>
        <div class="ficha-section">
            <div class="ficha-section-title">4. Observaciones <small>(salen en el documento, las ve el cliente)</small></div>
            <div class="ficha-grid"><div class="form-field col-12"><textarea id="ncObs" ${dis} placeholder="Opcional">${h(n.observaciones || '')}</textarea></div></div>
        </div>
        ${'nota_interna' in n || !notaNC ? `
        <div class="ficha-section nc-interna">
            <div class="ficha-section-title">5. 🔒 Nota interna <small>(NUNCA sale en el documento; solo la ven Hellen y Erika)</small></div>
            <div class="ficha-grid">
                <div class="form-field col-4"><label>Causa <b style="color:#DC2626">(obligatorio)</b></label>
                    <select id="ncCausa" ${dis} onchange="ncRecalcular()"><option value="">-- Elige la causa --</option>${causas}</select></div>
                <div class="form-field col-8" id="ncRespCaja"><label>Responsable del error</label>
                    <select id="ncResp" ${dis}><option value="">-- Nadie / no aplica --</option>${usuarios}</select></div>
                <div class="form-field col-12"><label>Qué pasó <b style="color:#DC2626">(obligatorio)</b></label>
                    <textarea id="ncInterna" ${dis} placeholder="Ej.: María puso S/ 150 en vez de S/ 100; Komatsu rechazó la factura en su portal">${h(n.nota_interna || '')}</textarea></div>
            </div>
        </div>` : ''}
        ${notaNC ? `<div class="ficha-section"><div class="ficha-section-title">6. Evidencias para SUNAT <small>(carta o correo del cliente, PDF/XML de la nota emitida en SOL)</small></div>
            <div class="nc-evid">${(n.archivos || []).map(a => `<a href="/ventas/api/nc/archivos/${a.id}">📎 ${h(a.nombre)}</a>`).join('') || '<span style="color:#94A3B8">Sin evidencias todavía</span>'}
            ${permisos.puede_crear || permisos.puede_aprobar ? `<button type="button" class="btn btn-soft" onclick="ncAdjuntar(${notaNC.id})">📎 Adjuntar evidencia</button>` : ''}</div></div>` : ''}`;
    }

    function pintarPie() {
        const pie = document.querySelector('#notaCreditoModal .modal-foot');
        if (!pie) return;
        let botones = `<button class="btn btn-secondary" onclick="closeModal('notaCreditoModal')">Cerrar</button>`;
        if (editable()) {
            botones += `<button class="btn btn-soft" onclick="ncGuardar(false)">💾 Guardar como borrador</button>
                        <button class="btn btn-green" onclick="ncGuardar(true)">📨 Enviar a Erika para aprobar</button>`;
        }
        if (permisos.puede_aprobar && notaNC && notaNC.estado === 'Por aprobar') {
            botones += `<button class="btn nc-btn-rechazar" onclick="ncDecidir('rechazar')">✖ Rechazar</button>
                        <button class="btn nc-btn-aprobar" onclick="ncDecidir('aprobar')">✔ Aprobar</button>`;
        }
        pie.innerHTML = botones;
    }

    async function openNotaCreditoModalNC(id = null) {
        editingId = id;
        notaNC = null; origenNC = null;
        await cargarPermisos();
        if (!id && !permisos.puede_crear) {
            showToast('🔒 Solo Hellen crea notas de crédito. Erika las aprueba.', 'warning');
            return;
        }
        if (!usuariosNC.length) {
            try { usuariosNC = (await apiFetch('/ventas/api/nc/usuarios')).data || []; } catch (e) { usuariosNC = []; }
        }
        if (!comprobantesData || !comprobantesData.length) { try { await loadComprobantes(); } catch (e) { /* sigue */ } }
        if (id) {
            try { notaNC = (await apiFetch(`/ventas/api/nc/${id}`)).data; } catch (e) { showToast('❌ ' + e.message, 'error'); return; }
        }
        document.getElementById('notaCreditoModalTitle').textContent =
            !id ? 'Nueva nota de crédito' : (permisos.puede_aprobar && notaNC.estado === 'Por aprobar' ? 'Revisar nota de crédito' : 'Nota de crédito');
        document.getElementById('notaCreditoForm').innerHTML = htmlFormulario();
        pintarPie();
        document.getElementById('notaCreditoModal').classList.add('show');
        if (notaNC) {
            const ref = notaNC.comprobante_id || notaNC.comprobante_asociado;
            try { origenNC = (await apiFetch(`/ventas/api/nc/origen?comprobante=${encodeURIComponent(ref)}&excluir=${notaNC.id}`)).data; }
            catch (e) { origenNC = null; }
            document.getElementById('ncTraza').innerHTML = htmlTraza();
        }
        pintarItems();
    }

    function datosFormulario(enviar) {
        const val = id => document.getElementById(id)?.value || '';
        return {
            id: notaNC?.id || null, enviar,
            comprobante_id: val('ncFactura') || notaNC?.comprobante_id,
            tipo_nota: val('ncTipo'), porcentaje: val('ncPorcentaje'),
            items: [...document.querySelectorAll('.nc-cant')].map(i => ({ idx: i.dataset.idx, cantidad: i.value })),
            sustento: val('ncSustento'), guia_devolucion: val('ncGuiaDev'), observaciones: val('ncObs'),
            causa_interna: val('ncCausa'), responsable_error: val('ncResp'), nota_interna: val('ncInterna')
        };
    }

    async function ncGuardar(enviar) {
        const go = async () => {
            try {
                const r = await apiFetch('/ventas/api/nc/guardar', { method: 'POST', body: JSON.stringify(datosFormulario(enviar)) });
                showToast(enviar ? `📨 Nota ${r.data.serie}-${r.data.numero} enviada a Erika para aprobar` : '💾 Borrador guardado', 'success');
                closeModal('notaCreditoModal');
                await loadNotas();
            } catch (e) { showToast('❌ ' + e.message, 'error'); }
        };
        if (!enviar) return go();
        showConfirmModal('📨 ¿Enviar a Erika?', `La nota de <b>${h(origenNC?.cliente || '')}</b> por <b>${document.getElementById('ncTotal')?.textContent}</b> queda "Por aprobar".`,
            'No resta de la factura hasta que Erika la apruebe.', go, 'Sí, enviar');
    }

    async function ncDecidir(decision) {
        const enviar = async motivo => {
            try {
                await apiFetch(`/ventas/api/nc/${notaNC.id}/decidir`, { method: 'POST', body: JSON.stringify({ decision, motivo }) });
                showToast(decision === 'aprobar' ? '✔ Nota de crédito aprobada' : '✖ Nota de crédito rechazada', 'success');
                closeModal('notaCreditoModal');
                await loadNotas();
            } catch (e) { showToast('❌ ' + e.message, 'error'); }
        };
        if (decision === 'aprobar') {
            showConfirmModal('✔ ¿Aprobar nota de crédito?', `Se emite por <b>${document.getElementById('ncTotal')?.textContent}</b> y resta del saldo de la factura <b>${h(origenNC?.factura || '')}</b>.`,
                'Queda registrado que la aprobaste tú, con fecha y hora.', () => enviar(''), 'Sí, aprobar');
        } else {
            const motivo = window.prompt('¿Por qué la rechazas? (Hellen lo verá para corregirla)');
            if (motivo !== null) enviar(motivo);
        }
    }

    function ncAdjuntar(id) {
        const inp = document.createElement('input');
        inp.type = 'file';
        inp.accept = '.pdf,.xml,.zip,.png,.jpg,.jpeg,.eml,.msg';
        inp.onchange = async () => {
            const f = inp.files && inp.files[0];
            if (!f) return;
            const fd = new FormData(); fd.append('archivo', f);
            const r = await fetch(`/ventas/api/nc/${id}/archivos`, { method: 'POST', body: fd });
            const j = await r.json().catch(() => ({ success: false, error: 'HTTP ' + r.status }));
            if (!r.ok || !j.success) { showToast('❌ ' + (j.error || 'No se pudo adjuntar'), 'error'); return; }
            showToast('📎 Evidencia adjuntada', 'success');
            openNotaCreditoModalNC(id);
        };
        inp.click();
    }

    // ------------------------------------------------------------------ reporte para Erika
    async function verReporteNC() {
        try {
            const d = (await apiFetch('/ventas/api/nc/reporte')).data;
            const filas = (lista, col) => lista.length ? lista.map(x => `<tr><td class="left">${h(x[col] || '—')}</td><td>${x.n}</td><td>${money(x.monto)}</td>${'ultima' in x ? `<td>${h(x.ultima || '')}</td>` : ''}</tr>`).join('')
                : `<tr><td colspan="4" style="color:#94A3B8">Sin datos</td></tr>`;
            showConfirmModal('📊 Notas de crédito: causas y responsables',
                `<table class="nc-items"><thead><tr><th>Causa</th><th>Cantidad</th><th>Monto</th></tr></thead><tbody>${filas(d.por_causa, 'causa')}</tbody></table>
                 <div style="margin-top:10px;font-weight:900">Errores operativos por responsable</div>
                 <table class="nc-items"><thead><tr><th>Responsable</th><th>Cantidad</th><th>Monto</th><th>Última</th></tr></thead><tbody>${filas(d.por_responsable, 'responsable')}</tbody></table>`,
                'Para saber qué pasó y a quién llamar la atención.', () => {}, 'Cerrar');
        } catch (e) { showToast('❌ ' + e.message, 'error'); }
    }

    function prepararPestana() {
        const head = document.querySelector('#notas_credito .clean-actions');
        if (head && !document.getElementById('ncBtnReporte')) {
            head.insertAdjacentHTML('afterbegin', `<button id="ncBtnReporte" class="btn btn-secondary" style="display:none" onclick="ncVerReporte()">📊 Causas y responsables</button>`);
        }
        const panel = document.querySelector('#notas_credito .panel');
        if (panel && !document.getElementById('ncAvisoAprobar')) {
            panel.insertAdjacentHTML('afterbegin', `<div id="ncAvisoAprobar" class="nc-aviso" style="display:none">⏳ Tienes <b></b> por aprobar. Ábrelas con ⋮ ▸ Revisar.</div>`);
        }
        const sel = document.getElementById('notaStatus');
        if (sel && !sel.querySelector('option[value="Por aprobar"]')) {
            sel.innerHTML = ['', 'Borrador', 'Por aprobar', 'Emitida', 'Rechazada', 'Anulada']
                .map(v => `<option value="${v}">${v || 'Todos los estados'}</option>`).join('');
        }
        cargarPermisos().then(p => {
            const b = document.getElementById('ncBtnReporte');
            if (b) b.style.display = p.puede_aprobar ? '' : 'none';
            renderNotasNC();
        });
    }

    window.renderNotas = renderNotasNC;
    window.showNotaMenu = showNotaMenuNC;
    window.openNotaCreditoModal = openNotaCreditoModalNC;
    window.saveNotaCredito = enviar => ncGuardar(enviar === 'Emitida');
    window.generateNotaPdf = id => window.open(`/ventas/nc/${id}/imprimir`, '_blank');
    window.markNotaEmitida = id => openNotaCreditoModalNC(id);
    window.anularNotaNC = anularNotaNC;
    window.ncElegirFactura = elegirFacturaNC;
    window.ncPintarItems = pintarItems;
    window.ncRecalcular = ncRecalcular;
    window.ncGuardar = ncGuardar;
    window.ncDecidir = ncDecidir;
    window.ncAdjuntar = ncAdjuntar;
    window.ncVerReporte = verReporteNC;
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', prepararPestana); else prepararPestana();
})();
