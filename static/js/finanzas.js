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
            // 22/10/2026: solo lo que no está en la fila de resumen de cada pestaña
            set('cxcResMes', soles(data.cobrado_mes));
            set('cxpResMes', soles(data.pagado_mes));
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
        body.innerHTML = '<tr><td colspan="15">Cargando...</td></tr>';
        try {
            const { data, totales } = await api(`/finanzas/api/${tipo}?${params}`);
            datos[tipo] = data;   // CxP ya viene ordenado del servidor (vencido > por vencer > al día): no se reordena
            pintarResumen(tipo, totales);
            renderCuentas(tipo);
        } catch (e) {
            body.innerHTML = `<tr><td colspan="12" class="neg">No se pudo cargar: ${esc(e.message)}</td></tr>`;
        }
    }

    // Fila de resumen arriba de cada tabla (sobre todo lo pendiente, sin importar el filtro). 22/10/2026
    function pintarResumen(tipo, t) {
        if (!t) return;
        const set = (id, v) => { const el = document.getElementById(tipo + id); if (el) el.textContent = v; };
        const n = c => `(${c || 0})`;
        set('ResVencido', soles(t.vencido)); set('ResVencidoN', n(t.docs_vencidos));
        set('ResPorVencer', soles(t.por_vencer)); set('ResPorVencerN', n(t.docs_por_vencer));
        set('ResAlDia', soles(t.al_dia)); set('ResAlDiaN', n(t.docs_al_dia));
        set('ResTotal', soles(t.total)); set('ResTotalN', n(t.docs_total));
        const caja = document.getElementById(tipo + 'Resumen');
        caja.querySelector('.res-vencido').classList.toggle('res-cero', !(t.vencido > 0));
        caja.querySelector('.res-porvencer').classList.toggle('res-cero', !(t.por_vencer > 0));
        const filtro = document.getElementById(tipo + 'Estado').value;
        caja.querySelectorAll('.res-item').forEach(b => b.classList.toggle('res-activo', b.dataset.filtro === filtro));
    }
    document.addEventListener('click', e => {
        const b = e.target.closest('.fin-resumen .res-item');
        if (!b) return;
        const tipo = b.closest('.fin-resumen').id.replace('Resumen', '');
        document.getElementById(tipo + 'Estado').value = b.dataset.filtro;
        cargarCuentas(tipo);
    });

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
            return `<span class="sem-chip sem-aldia">AL DÍA${n !== null && n !== undefined ? ` · faltan ${n} días` : ''}</span>`;
        }
        return `<span class="${semClase(x.semaforo)}">${esc(x.semaforo)}</span>`;
    }

    // Días para vencer / de atraso calculados en el navegador (sirve para cobrar y pagar)
    function chipDias(x) {
        if (x.saldo <= 0 || !x.fecha_vencimiento) return '';
        const hoy = new Date(hoyISO() + 'T00:00:00');
        const ven = new Date(String(x.fecha_vencimiento).slice(0, 10) + 'T00:00:00');
        const n = Math.round((ven - hoy) / 86400000);
        if (n < 0) return `<span class="sem-chip sem-peligro">${-n} día${n === -1 ? '' : 's'} de atraso</span>`;
        if (n === 0) return '<span class="sem-chip sem-atencion">vence hoy</span>';
        if (n <= 7) return `<span class="sem-chip sem-atencion">faltan ${n} día${n === 1 ? '' : 's'}</span>`;
        return `<span class="sem-chip sem-aldia">faltan ${n} días</span>`;
    }

    // Monto con su moneda (S/ o $), como en el Excel de Erika
    const dinero = (x, v) => x.moneda === 'USD' ? 'US$ ' + Number(v || 0).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',') : soles(v);
    const dineroM = (m, v) => dinero({ moneda: m }, v);

    function celdaProductos(x) {
        const p = x.productos || [];
        if (!p.length) return '<span class="fin-gris">—</span>';
        const linea = it => `${it.cantidad !== null && it.cantidad !== undefined ? `<b>${Number(it.cantidad)}</b> × ` : ''}${esc(it.producto)}`;
        if (p.length === 1) return `<span class="fin-prod">${linea(p[0])}</span>`;
        return `<span class="fin-prod">${linea(p[0])}</span><details class="fin-mas"><summary>+${p.length - 1} más</summary>
            <ul>${p.slice(1).map(it => `<li>${linea(it)}</li>`).join('')}</ul></details>`;
    }

    function chipEstado(x) {
        const e = x.estado_pago || '';
        const cls = /^(Pagado|Cobrado)$/.test(e) ? 'est-terminado' : /parcial/i.test(e) ? 'est-parcial' : 'est-pendiente';
        const ico = cls === 'est-terminado' ? '✔ ' : cls === 'est-parcial' ? '◐ ' : '⏳ ';
        return `<span class="est-chip ${cls}">${ico}${esc(e)}</span>`;
    }

    // Seguimiento del cobro (Erika 23/10/2026, de su Excel): portal del cliente, fecha programada y retención del 3%
    function celdaSeguimiento(x) {
        const l = [];
        if (x.portal_ingresado) {
            l.push(`<span class="seg-chip seg-ok" title="Ingresada en el portal de proveedores del cliente${x.portal_fecha ? ' el ' + fecha(x.portal_fecha) : ''}">✔ En portal</span>`);
        } else if (x.saldo > 0) {
            l.push('<span class="seg-chip seg-falta" title="Falta ingresar la factura en el portal de proveedores del cliente">✖ Falta portal</span>');
        }
        // N° MIGO (Erika 25/10/2026): solo para clientes que lo piden (check en su ficha)
        if (x.numero_migo) {
            l.push(`<small title="N° MIGO / conformidad del cliente">MIGO <b>${esc(x.numero_migo)}</b></small>`);
        } else if (x.pide_migo && x.saldo > 0) {
            l.push('<span class="seg-chip seg-falta" title="Este cliente no paga sin el N° MIGO de su conformidad: pídelo y anótalo con ✏️">✖ Falta MIGO</span>');
        }
        if (x.fecha_programada) l.push(`<small title="Fecha en que el cliente programó el pago">Pago programado <b>${fecha(x.fecha_programada)}</b></small>`);
        if (x.retencion_numero) {
            l.push(`<small title="Comprobante de retención del cliente: ${esc(x.retencion_numero)} por ${dinero(x, x.retencion)}">Retención <b>${esc(x.retencion_numero)}</b></small>`);
        } else if (x.retencion > 0) {
            l.push('<small class="seg-pend" title="Esta factura tiene retención del 3%: anota el N° del comprobante de retención cuando el cliente lo envíe">Retención 3%: falta N°</small>');
        }
        if (PUEDE_OPERAR) l.push(`<button class="btn-mini sec" title="Portal, N° MIGO, fecha programada de pago y retención" data-seg="${x.id}">✏️</button>`);
        return l.length ? l.join('') : '<span class="fin-gris">—</span>';
    }

    function abrirSeguimiento(id) {
        const x = datos.cxc.find(d => String(d.id) === String(id));
        if (!x) return;
        document.getElementById('segModal')?.remove();
        const tres = Math.round(Number(x.total || 0) * 3) / 100;
        const monto = x.retencion_anotada ?? (x.retencion > 0 ? x.retencion : '');
        const d = document.createElement('div');
        d.id = 'segModal';
        d.className = 'seg-modal-bg';
        d.innerHTML = `<div class="seg-modal">
            <div class="seg-titulo">Seguimiento del cobro</div>
            <div class="seg-sub">${esc(x.documento)} · ${esc(x.tercero)} · ${dinero(x, x.total)}</div>
            <label class="seg-check"><input type="checkbox" id="segPortal" ${x.portal_ingresado ? 'checked' : ''}> Ingresada en el portal del cliente</label>
            <label class="seg-campo" id="segPortalFechaCaja">Fecha de ingreso al portal<input type="date" id="segPortalFecha" value="${x.portal_fecha ? String(x.portal_fecha).slice(0, 10) : ''}"></label>
            ${x.pide_migo || x.numero_migo ? `<label class="seg-campo">N° MIGO / conformidad<input type="text" id="segMigo" maxlength="40" placeholder="El que envía el cliente" value="${esc(x.numero_migo || '')}"></label>` : ''}
            <label class="seg-campo">Fecha programada de pago<input type="date" id="segProgramada" value="${x.fecha_programada ? String(x.fecha_programada).slice(0, 10) : ''}"></label>
            <div class="seg-grupo">Retención del 3% (comprobante que envía el cliente)</div>
            <label class="seg-campo">N° comprobante de retención<input type="text" id="segRetNum" maxlength="40" placeholder="Ej. R001-00006805" value="${esc(x.retencion_numero || '')}"></label>
            <label class="seg-campo">Monto retenido (S/)<input type="number" id="segRetMonto" min="0" step="0.01" value="${monto}"></label>
            <div class="seg-ayuda">3% de esta factura = ${dinero(x, tres)}. Este monto es el que usa SUNAT ▸ Retenciones del mes. Vacío = el de la factura.</div>
            <div class="seg-botones">
              <button type="button" class="btn btn-secondary" data-seg-cerrar="1">Cancelar</button>
              <button type="button" class="btn btn-primary" id="segGuardar">💾 Guardar</button>
            </div></div>`;
        document.body.appendChild(d);
        const caja = d.querySelector('#segPortalFechaCaja');
        const chk = d.querySelector('#segPortal');
        const verFecha = () => { caja.style.display = chk.checked ? '' : 'none'; };
        chk.addEventListener('change', () => { if (chk.checked && !d.querySelector('#segPortalFecha').value) d.querySelector('#segPortalFecha').value = hoyISO(); verFecha(); });
        verFecha();
        d.addEventListener('click', e => { if (e.target === d || e.target.dataset.segCerrar) d.remove(); });
        d.querySelector('#segGuardar').addEventListener('click', async () => {
            try {
                await api('/finanzas/api/seguimiento_cobro', { method: 'POST', body: JSON.stringify({
                    id: x.id, portal_ingresado: chk.checked, portal_fecha: d.querySelector('#segPortalFecha').value,
                    fecha_programada: d.querySelector('#segProgramada').value, retencion_numero: d.querySelector('#segRetNum').value,
                    retencion_monto: d.querySelector('#segRetMonto').value,
                    ...(d.querySelector('#segMigo') ? { numero_migo: d.querySelector('#segMigo').value } : {}) }) });
                d.remove();
                aviso('Seguimiento guardado', 'success');
                cargarCuentas('cxc');
            } catch (e) { aviso(e.message, 'error'); }
        });
    }

    // "Ver cobro" desde Ventas ▸ Entregas: la factura de esa entrega sale sombreada (23/10/2026)
    const facturaBuscada = new URLSearchParams(location.search).get('factura');
    const claveDoc = s => {
        const m = String(s || '').trim().toUpperCase().match(/^([A-Z0-9]+)-0*(\d+)$/);
        return m ? m[1] + '-' + m[2] : String(s || '').trim().toUpperCase();
    };
    const buscadas = new Set(String(facturaBuscada || '').split(',').map(claveDoc).filter(Boolean));
    let yaSeBajo = false;

    function renderCuentas(tipo) {
        const body = document.getElementById(tipo + 'Body');
        const lista = datos[tipo];
        const esCxc = tipo === 'cxc';
        if (!lista.length) {
            body.innerHTML = `<tr><td colspan="${esCxc ? 15 : 14}">No hay documentos para este filtro.</td></tr>`;
        } else {
            body.innerHTML = lista.map((x, i) => {
                const accion = x.saldo > 0
                    ? `<button class="btn-mini" ${PUEDE_OPERAR ? '' : 'disabled title="Sin permiso"'} data-pagar="${tipo}:${x.id}" title="${esCxc ? 'Registrar cobro' : 'Registrar pago'}">${esCxc ? '⬇ Cobrar' : '⬆ Pagar'}</button>`
                    : '<span class="fin-gris">—</span>';
                const venc = esCxc ? '' : (PUEDE_OPERAR ? ` <button class="btn-mini sec" title="Cambiar vencimiento" data-venc="${x.id}">📅</button>` : '');
                const vinculo = esCxc
                    ? `<b>${esc(x.pc_numero || '—')}</b>${x.oc_cliente ? `<small>N° OC del cliente: ${esc(x.oc_cliente)}</small>` : ''}`
                    : `<b>${esc(x.oc_numero || '—')}</b>${x.pc_numero ? `<small>${esc(x.pc_numero)}</small>` : ''}`;
                // Cobrar: la retención y la nota de crédito van debajo del monto. Pagar: el adelanto va debajo de lo pagado.
                const extraMonto = esCxc ? [x.retencion ? `Retención ${dinero(x, x.retencion)}` : '', x.notas_credito ? `N. crédito ${dinero(x, x.notas_credito)}` : '']
                    .filter(Boolean).map(t => `<small>${t}</small>`).join('') : '';
                const extraPagado = !esCxc && x.adelanto ? `<small title="Pagado en Compras antes de registrar la factura">Adelanto ${dinero(x, x.adelanto)}</small>` : '';
                const comentario = `<span class="fin-coment">${esc(x.comentario || '')}</span>`
                    + (x.nota_registro ? `<small class="fin-gris" title="Observación al registrar la factura en Compras">Compras: ${esc(x.nota_registro)}</small>` : '')
                    + (PUEDE_OPERAR ? `<button class="btn-mini sec" title="Escribir comentario" data-coment="${tipo}:${x.id}">✏️</button>` : '');
                const resaltada = esCxc && buscadas.has(claveDoc(x.documento));
                const filaCls = (x.saldo <= 0 ? 'fin-fila-ok' : x.semaforo === 'Vencido' ? 'cxp-fila-vencida' : '') + (resaltada ? ' fin-fila-resaltada' : '');
                return `<tr class="${filaCls}">
                    <td>${i + 1}</td>
                    <td class="left"><b>${esc(x.tercero)}</b></td>
                    <td>${esc(x.ruc || '—')}</td>
                    <td><b>${esc(x.documento)}</b><small>${esc(x.tipo_comprobante || '')} · ${fecha(x.fecha_emision)}</small></td>
                    <td>${vinculo}</td>
                    <td class="left">${celdaProductos(x)}</td>
                    <td>${fecha(x.fecha_vencimiento)}${venc}${chipDias(x) ? '<br>' + chipDias(x) : ''}</td>
                    <td class="num">${dinero(x, x.total)}${extraMonto}</td>
                    <td class="num">${dinero(x, x.abonado)}${extraPagado}</td>
                    <td class="num saldo">${dinero(x, x.saldo)}</td>
                    <td>${chipEstado(x)}</td>
                    <td>${x.fecha_pago_real ? `<b>${fecha(x.fecha_pago_real)}</b>` : x.ultimo_abono ? `<small>Último abono ${fecha(x.ultimo_abono)}</small>` : '<span class="fin-gris">—</span>'}</td>
                    ${esCxc ? `<td class="seg-celda">${celdaSeguimiento(x)}</td>` : ''}
                    <td class="fin-coment-celda">${comentario}</td>
                    <td>${accion}</td>
                </tr>`;
            }).join('');
        }
        if (esCxc && buscadas.size && !yaSeBajo) {
            const fila = body.querySelector('.fin-fila-resaltada');
            if (fila) {
                yaSeBajo = true;
                setTimeout(() => fila.scrollIntoView({ block: 'center', behavior: 'smooth' }), 150);
            } else if (!document.getElementById('cxcBorradores').checked) {
                // Puede ser un borrador: se vuelve a buscar incluyéndolos
                document.getElementById('cxcBorradores').checked = true;
                cargarCuentas('cxc');
            } else {
                yaSeBajo = true;
                aviso(`No se encontró la factura ${facturaBuscada} en Cuentas por cobrar`, 'warning');
            }
        }
        const total = lista.reduce((s, x) => s + x.saldo, 0);
        document.getElementById(tipo + 'Foot').textContent = `${lista.length} documentos · Saldo total: ${soles(total)}`;
    }

    // ---------- Movimientos ----------
    async function cargarMovimientos() {
        const body = document.getElementById('movBody');
        const tipo = document.getElementById('movTipo').value;
        try {
            const q = (document.getElementById('movBuscar')?.value || '').trim();
            const params = new URLSearchParams();
            if (tipo) params.set('tipo', tipo);
            if (q) params.set('q', q);
            const { data } = await api('/finanzas/api/movimientos' + (params.toString() ? '?' + params : ''));
            body.innerHTML = data.length ? data.map(m => `<tr class="${m.tipo === 'COBRO' ? 'fila-cobro' : 'fila-pago'}">
                <td>${fecha(m.fecha)}</td>
                <td><span class="fin-tipo ${m.tipo === 'COBRO' ? 'fin-tipo-cobro' : 'fin-tipo-pago'}">${m.tipo === 'COBRO' ? '⬇ Cobro' : '⬆ Pago'}</span></td>
                <td>${esc(m.documento_numero)}</td>
                <td class="fin-ocpc">${ocPcMovimiento(m)}</td>
                <td class="left">${esc(m.tercero_nombre)}</td>
                <td class="num">${m.moneda_pago && m.moneda_pago !== 'PEN' || (m.monto_pagado && Number(m.monto_pagado) !== Number(m.monto))
                    ? `${dineroM(m.moneda_pago, m.monto_pagado)}${m.tipo_cambio ? `<small>TC ${Number(m.tipo_cambio).toFixed(3)}</small>` : ''}` : soles(m.monto)}</td>
                <td>${esc(m.metodo)}</td>
                <td>${esc([m.banco, m.numero_operacion ? 'Op. ' + m.numero_operacion : '', m.fecha_aviso ? 'Avisó ' + fecha(m.fecha_aviso) : ''].filter(Boolean).join(' · ')) || '—'}</td>
                <td>${esc(m.usuario_nombre || '')}</td>
                <td>${m.estado === 'Anulado' ? `<span class="badge badge-gray" title="${esc(m.motivo_anulacion)}">Anulado</span>` : '<span class="badge badge-info">Registrado</span>'}</td>
                <td>${m.estado !== 'Anulado' && PUEDE_OPERAR ? `<button class="btn-mini danger" data-anular="${m.id}">Anular</button>` : ''}</td>
            </tr>`).join('') : '<tr><td colspan="11">Aún no hay cobros ni pagos registrados.</td></tr>';
        } catch (e) {
            body.innerHTML = `<tr><td colspan="11" class="neg">No se pudo cargar: ${esc(e.message)}</td></tr>`;
        }
    }

    // N° OC y N° PC de cada cobro/pago, en dos líneas (Erika 22/10/2026: trazabilidad)
    function ocPcMovimiento(m) {
        const linea = (et, v) => v ? `<div><small>${et}</small> <b>${esc(v)}</b></div>` : '';
        const html = m.tipo === 'COBRO'
            ? linea('N° PC (Pedido de compra)', m.pc_numero) + linea('N° OC del cliente', m.oc_cliente)
            : linea('N° OC (Proveedor)', m.oc_numero) + linea(/^(Compra a stock|Sin PC)/.test(m.pc_numero || '') ? '' : 'N° PC (Pedido de compra)', m.pc_numero);
        return html || '<span class="fin-sin">—</span>';
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

    // Cuentas escritas "de relleno" al registrar al proveedor (1111..., 5555444488889999, 123123...)
    function cuentaDeRelleno(...nums) {
        return nums.some(n => { const d = String(n || '').replace(/\D/g, '');
            return d && (/(\d)\1{5,}/.test(d) || /(\d{2,4})\1{3,}/.test(d) || d === '5555444488889999'); });
    }

    function abrirPago(tipo, id) {
        const doc = datos[tipo].find(x => String(x.id) === String(id));
        if (!doc) return;
        const esCxc = tipo === 'cxc';
        document.getElementById('pagoTitulo').textContent = esCxc ? 'Registrar cobro' : 'Registrar pago';
        document.getElementById('pagoTipo').value = esCxc ? 'COBRO' : 'PAGO';
        document.getElementById('pagoDocId').value = doc.id;
        // Un dato por línea y siempre en el mismo orden (pedido de Erika 21/10 17:22)
        const fila = (et, val, cls = '') => `<div class="fd-et">${et}</div><div class="fd-val ${cls}">${val}</div>`;
        let ficha = `<div class="fd-titulo">${esCxc ? 'Cobrar a' : 'Pagar a'}</div>` +
            fila(esCxc ? 'Cliente' : 'Proveedor', esc(doc.tercero || '—')) +
            fila('RUC / DNI', esc(doc.ruc || '—'), 'fd-num');
        if (!esCxc) {
            ficha += fila('Banco', esc(doc.banco || '—')) +
                fila('N° de cuenta', esc(doc.numero_cuenta || '—'), 'fd-num') +
                fila('CCI', esc(doc.cci || '—'), 'fd-num');
        }
        ficha += fila(`N° ${esc((doc.tipo_comprobante || 'documento').toLowerCase())}`, esc(doc.documento || '—'), 'fd-num') +
            fila(esCxc ? 'Total (incluye IGV)' : 'Monto a pagar (incluye IGV)', dinero(doc, doc.total), 'fd-monto');
        if (esCxc && doc.retencion) ficha += fila('Retención', dinero(doc, doc.retencion));
        if (doc.notas_credito) ficha += fila('Nota de crédito', dinero(doc, doc.notas_credito));
        ficha += fila(esCxc ? 'Falta cobrar' : 'Falta pagar', dinero(doc, doc.saldo), 'fd-monto ' + (doc.saldo > 0 ? 'fd-falta' : 'fd-ok'));
        if (doc.moneda === 'USD' && doc.tipo_cambio) ficha += fila('Tipo de cambio del documento', Number(doc.tipo_cambio).toFixed(3), 'fd-num');
        if (!esCxc) {
            if (cuentaDeRelleno(doc.numero_cuenta, doc.cci)) {
                ficha += '<div class="fd-nota fd-alerta">⚠️ La cuenta o el CCI parecen de relleno (números repetidos). Confírmalos con el proveedor y corrígelos en Maestros ▸ Proveedores antes de pagar.</div>';
            }
            ficha += (doc.numero_cuenta || doc.cci)
                ? '<div class="fd-nota">Paga solo a esta cuenta. Si el proveedor te pide pagar a otra, consulta con tu supervisora.</div>'
                : '<div class="fd-nota fd-alerta">⚠️ El proveedor no tiene cuenta registrada. Regístrala en Maestros ▸ Proveedores antes de pagar.</div>';
        }
        const cajaDoc = document.getElementById('pagoDoc');
        cajaDoc.className = 'ficha-datos ' + (esCxc ? 'fd-cobro' : 'fd-pago');
        cajaDoc.innerHTML = ficha;
        document.getElementById('pagoMonto').value = doc.saldo.toFixed(2);
        document.getElementById('pagoMonto').max = doc.saldo.toFixed(2);
        // 24/10/2026 (Erika): factura en dólares que se paga o cobra en soles con el tipo de cambio
        pagoDoc = { moneda: doc.moneda === 'USD' ? 'USD' : 'PEN', saldo: doc.saldo };
        document.getElementById('pagoMonedaWrap').style.display = pagoDoc.moneda === 'USD' ? '' : 'none';
        document.getElementById('pagoMonedaPago').value = pagoDoc.moneda;
        document.getElementById('pagoMonedaInfo').textContent = pagoDoc.moneda === 'USD'
            ? 'Solo AGD tiene cuenta en dólares. Si se paga en soles, escribe el tipo de cambio (el del proveedor, si te dio uno).' : '';
        document.getElementById('pagoTC').value = doc.tipo_cambio ? Number(doc.tipo_cambio).toFixed(3) : '';
        pintarMonedaPago();
        document.getElementById('pagoFecha').value = hoyISO();
        ['pagoBanco', 'pagoOperacion', 'pagoAviso', 'pagoObs'].forEach(i => { document.getElementById(i).value = ''; });
        document.getElementById('pagoAvisoTip').style.display = esCxc ? '' : 'none';
        // La fecha de aviso es solo de cobros (el cliente avisa); en un pago basta el N.º de operación
        document.getElementById('pagoAviso').closest('label').style.display = esCxc ? '' : 'none';
        document.getElementById('pagoOperacion').placeholder = esCxc ? 'Si el cliente lo envió' : 'Está en la constancia del banco';
        document.getElementById('pagoBanco').placeholder = esCxc ? 'Banco donde entró el dinero (Ej. BCP)' : 'Banco desde el que se pagó (Ej. BCP)';
        abrir('pagoModal');
    }

    let pagoDoc = { moneda: 'PEN', saldo: 0 };
    const monPago = () => pagoDoc.moneda === 'USD' ? document.getElementById('pagoMonedaPago').value : 'PEN';
    function montoEnDoc() {
        const m = parseFloat(document.getElementById('pagoMonto').value), tc = parseFloat(document.getElementById('pagoTC').value);
        if (monPago() === pagoDoc.moneda) return m;
        return tc > 0 ? Math.round(m / tc * 100) / 100 : NaN;
    }
    function equivPago() {
        const eq = document.getElementById('pagoEquiv');
        if (monPago() === pagoDoc.moneda) { eq.textContent = ''; return; }
        const v = montoEnDoc();
        eq.textContent = v > 0 ? `Se descuenta ${dineroM('USD', v)} del saldo en dólares.` : 'Escribe el tipo de cambio.';
    }
    async function pintarMonedaPago(cambio) {
        const otra = monPago() !== pagoDoc.moneda;
        document.getElementById('pagoTCWrap').style.display = otra ? '' : 'none';
        document.getElementById('pagoMontoEt').textContent = `Monto (${monPago() === 'USD' ? 'US$' : 'S/'})`;
        const inpTC = document.getElementById('pagoTC'), inpM = document.getElementById('pagoMonto');
        if (otra && !inpTC.value && window.Moneda) {
            const tc = await Moneda.tcSunat(document.getElementById('pagoFecha').value || hoyISO());
            if (tc && !inpTC.value) inpTC.value = tc.toFixed(3);
        }
        const tc = parseFloat(inpTC.value);
        if (cambio !== false) {
            inpM.value = (otra ? (tc > 0 ? pagoDoc.saldo * tc : 0) : pagoDoc.saldo).toFixed(2);
            inpM.max = otra ? (tc > 0 ? (pagoDoc.saldo * tc + 0.05).toFixed(2) : '') : pagoDoc.saldo.toFixed(2);
        }
        equivPago();
    }
    document.addEventListener('change', e => { if (e.target.id === 'pagoMonedaPago') pintarMonedaPago(); });
    document.addEventListener('input', e => {
        if (e.target.id === 'pagoTC') pintarMonedaPago();
        else if (e.target.id === 'pagoMonto') equivPago();
    });

    async function guardarPago() {
        const btn = document.getElementById('pagoGuardar');
        const monto = parseFloat(document.getElementById('pagoMonto').value);
        const max = parseFloat(document.getElementById('pagoMonto').max);
        const otra = monPago() !== pagoDoc.moneda;
        if (!(monto > 0)) { aviso('Ingresa un monto mayor a 0', 'warning'); return; }
        if (otra && !(parseFloat(document.getElementById('pagoTC').value) > 0)) { aviso('Escribe el tipo de cambio', 'warning'); return; }
        if (!otra && monto > max + 0.001) { aviso('El monto no puede superar el saldo pendiente', 'warning'); return; }
        if (otra && montoEnDoc() > pagoDoc.saldo + 0.02) { aviso('El monto no puede superar el saldo pendiente', 'warning'); return; }
        const conBanco = ['Transferencia', 'Depósito', 'Yape/Plin'].includes(document.getElementById('pagoMetodo').value);
        if (document.getElementById('pagoTipo').value === 'COBRO' && conBanco &&
            !document.getElementById('pagoOperacion').value.trim() && !document.getElementById('pagoAviso').value) {
            aviso('Escribe el N.º de operación o la fecha de aviso de pago (lo que haya mandado el cliente).', 'warning');
            return;
        }
        btn.disabled = true;
        try {
            const r = await api('/finanzas/api/movimientos', {
                method: 'POST',
                body: JSON.stringify({
                    tipo: document.getElementById('pagoTipo').value,
                    documento_id: document.getElementById('pagoDocId').value,
                    monto: otra ? montoEnDoc() : monto, monto_pagado: monto, moneda_pago: monPago(),
                    tipo_cambio: otra ? document.getElementById('pagoTC').value : null,
                    fecha: document.getElementById('pagoFecha').value,
                    metodo: document.getElementById('pagoMetodo').value,
                    banco: document.getElementById('pagoBanco').value,
                    numero_operacion: document.getElementById('pagoOperacion').value,
                    fecha_aviso: document.getElementById('pagoAviso').value,
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
        const cols = ['tercero', 'ruc', 'tipo_comprobante', 'documento', 'fecha_emision', tipo === 'cxc' ? 'pc_numero' : 'oc_numero',
            tipo === 'cxc' ? 'oc_cliente' : 'pc_numero', 'productos', 'fecha_vencimiento', 'semaforo', 'moneda', 'total',
            tipo === 'cxc' ? 'retencion' : 'adelanto', 'abonado', 'saldo', 'estado_pago', 'fecha_pago_real', 'comentario'];
        const csv = [cols.join(';')].concat(filas.map(f => cols.map(c => `"${String(c === 'productos' ? (f.productos || []).map(p => `${p.cantidad ?? ''} ${p.producto}`.trim()).join(' | ') : (f[c] ?? '')).replace(/"/g, '""')}"`).join(';'))).join('\n');
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
        try { history.replaceState(null, '', '/finanzas?tab=' + tab); } catch (e) { /* nada */ }
        if (window.abrirMenuModulo) window.abrirMenuModulo();   // el menú lateral marca la pestaña abierta
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
    let esperaMov;
    document.getElementById('movBuscar').addEventListener('input', () => { clearTimeout(esperaMov); esperaMov = setTimeout(cargarMovimientos, 300); });
    document.getElementById('flujoSemanas').addEventListener('change', cargarFlujo);
    document.getElementById('pagoGuardar').addEventListener('click', guardarPago);
    document.getElementById('vencGuardar').addEventListener('click', guardarVencimiento);
    // Comentario de Finanzas en la fila (no cambia la factura)
    async function escribirComentario(clave) {
        const [tipo, id] = clave.split(':');
        const doc = datos[tipo].find(x => String(x.id) === id);
        if (!doc) return;
        const texto = prompt(`Comentario para ${doc.documento} (${doc.tercero}).\nDéjalo vacío para borrarlo.`, doc.comentario || '');
        if (texto === null) return;
        try {
            const r = await api('/finanzas/api/comentario', { method: 'POST', body: JSON.stringify({ tipo, id, comentario: texto }) });
            doc.comentario = r.comentario;
            renderCuentas(tipo);
        } catch (e) { aviso(e.message, 'error'); }
    }

    document.addEventListener('click', e => {
        const t = e.target;
        if (t.dataset.close) cerrar(t.dataset.close);
        if (t.dataset.export) exportarCSV(t.dataset.export);
        if (t.dataset.pagar && !t.disabled) { const [tipo, id] = t.dataset.pagar.split(':'); abrirPago(tipo, id); }
        if (t.dataset.anular) anularMovimiento(t.dataset.anular);
        if (t.dataset.coment) escribirComentario(t.dataset.coment);
        if (t.dataset.seg) abrirSeguimiento(t.dataset.seg);
        if (t.dataset.venc) {
            const doc = datos.cxp.find(x => String(x.id) === t.dataset.venc);
            document.getElementById('vencId').value = t.dataset.venc;
            document.getElementById('vencFecha').value = doc && doc.fecha_vencimiento ? String(doc.fecha_vencimiento).slice(0, 10) : hoyISO();
            abrir('vencModal');
        }
    });

    // Viene de "Ver cobro": se muestran todas (también las ya cobradas) para que la factura aparezca
    if (facturaBuscada) document.getElementById('cxcEstado').value = 'todos';
    const tabInicial = new URLSearchParams(location.search).get('tab');
    const tabArranque = ['cxc', 'cxp', 'movimientos', 'flujo'].includes(tabInicial) ? tabInicial : 'cxc';
    activarTab(tabArranque);
    // El menú general quita el resaltado de las pestañas al cargar: se vuelve a marcar la pestaña abierta
    window.addEventListener('load', () => setTimeout(() => {
        const abierta = document.querySelector('#finanzasApp > .section.active');
        activarTab(abierta ? abierta.id.replace('sec-', '') : tabArranque);
    }, 50));
    refrescarTodo();
})();
