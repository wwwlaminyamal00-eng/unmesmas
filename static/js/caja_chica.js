// static/js/caja_chica.js - Caja chica con fondo fijo (pedido de Erika 22/10/2026)
(function () {
    'use strict';
    const $ = (s, r = document) => r.querySelector(s);
    const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
    const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const num = v => Number(v || 0);
    const soles = v => (num(v) < 0 ? '-' : '') + 'S/ ' + Math.abs(num(v)).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const TABS = ['gastos', 'rendicion', 'arqueo', 'personas'];
    const OPC = window.CC_OPCIONES || { rubros: [], comprobantes: [], tiposPersona: [], conNumero: [], sustenta: [], topeAviso: 100 };
    const hoy = () => new Date().toLocaleDateString('en-CA', { timeZone: 'America/Lima' });
    let APP = null;
    let tab = 'gastos';
    let R = null;          // resumen
    let movs = [];
    let gente = [];
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
    const empresa = () => $('#ccEmpresa').value;
    const empCodigo = () => ($('#ccEmpresa').selectedOptions[0] || {}).textContent || '';
    const esAdmin = () => APP.dataset.admin === 'true';
    const kpi = (titulo, valor, pie, clase) => `<div class="inv-kpi ${clase || ''}"><small>${titulo}</small><b>${valor}</b><span>${pie || ''}</span></div>`;
    const opciones = (lista, actual, vacio) => (vacio ? `<option value="">${esc(vacio)}</option>` : '') +
        lista.map(x => `<option value="${esc(x)}" ${x === actual ? 'selected' : ''}>${esc(x)}</option>`).join('');
    const imprimir = (ruta, extra) => window.open(`${ruta}?${new URLSearchParams(Object.assign({ empresa_id: empresa() }, extra || {}))}`, '_blank');

    // ============================================================
    // PESTAÑAS Y CARGA
    // ============================================================
    function irA(t) {
        tab = TABS.includes(t) ? t : 'gastos';
        $$('#ccTabs .tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
        TABS.forEach(x => $('#cc-sec-' + x).classList.toggle('active', x === tab));
        try { history.replaceState(null, '', '/caja-chica?tab=' + tab); } catch (e) { /* nada */ }
        if (window.abrirMenuModulo) window.abrirMenuModulo();
    }

    async function cargar() {
        $('#ccKpis').innerHTML = '<div class="inv-vacio">Cargando...</div>';
        try {
            const e = encodeURIComponent(empresa());
            const [r, p] = await Promise.all([api('/caja-chica/api/resumen?empresa_id=' + e), api('/caja-chica/api/personas?empresa_id=' + e)]);
            R = r.data;
            gente = p.data;
        } catch (e) {
            $('#ccKpis').innerHTML = `<div class="inv-vacio">⚠ ${esc(e.message)}</div>`;
            return;
        }
        pintarResumen();
        pintarRendicion();
        pintarArqueo();
        pintarPersonas();
        await cargarMovs();
    }

    async function cargarMovs() {
        const q = new URLSearchParams({ empresa_id: empresa(), desde: $('#ccDesde').value, hasta: $('#ccHasta').value,
            q: $('#ccBuscar').value.trim(), anulados: $('#ccAnulados').checked ? '1' : '0' });
        try {
            const j = await api('/caja-chica/api/movimientos?' + q);
            movs = j.data.filas;
            pintarMovs(j.data.saldo_anterior);
        } catch (e) {
            $('#ccMovs').innerHTML = `<div class="inv-vacio">⚠ ${esc(e.message)}</div>`;
        }
    }

    function pintarResumen() {
        const c = R.config;
        $('#ccFondo').innerHTML = `Fondo fijo ${soles(c.fondo_fijo)} · Responsable: ${esc(c.responsable || 'sin definir')}`;
        const avisos = [];
        if (!c.configurado) avisos.push('Define el fondo fijo, la responsable y la cuenta de la caja en <b>Personas y datos</b>' + (esAdmin() ? '.' : ' (lo hace la gerencia).'));
        if (R.saldo < 0) avisos.push(`El saldo está en <b>${soles(R.saldo)}</b>: alguien adelantó dinero propio. Envía la rendición para que se reponga.`);
        if (R.pendientes.sin_foto) avisos.push(`${R.pendientes.sin_foto} gasto(s) sin foto del voucher. Súbela con el botón 📷 de cada fila.`);
        const porAprobar = R.rendiciones.find(x => x.estado === 'Por aprobar');
        if (porAprobar && esAdmin()) avisos.push(`La rendición N° ${porAprobar.numero} (${soles(porAprobar.total_gastado)}) espera tu aprobación: pestaña <b>Rendición y reposición</b>.`);
        const obs = R.rendiciones.find(x => x.estado === 'Observada' && !R.rendiciones.some(y => y.numero > x.numero));
        if (obs) avisos.push(`Erika observó la rendición N° ${obs.numero}: "${esc(obs.observacion)}". Corrige y vuelve a enviarla.`);
        $('#ccAvisos').innerHTML = avisos.length ? `<div class="ge-aviso-rojo"><b>Revisa:</b><ul>${avisos.map(a => `<li>${a}</li>`).join('')}</ul></div>` : '';
        const pctSin = R.mes.total ? Math.round(R.mes.sin_sustento / R.mes.total * 100) : 0;
        $('#ccKpis').innerHTML = [
            kpi('Saldo de la caja', soles(R.saldo), `Fondo fijo ${soles(c.fondo_fijo)}`, R.saldo < 0 ? 'ge-kpi-mal' : 'ge-kpi-ok'),
            kpi('Por reponer', soles(R.por_reponer), 'Para completar el fondo', R.por_reponer > 0 ? 'ge-kpi-pago' : 'ge-kpi-ok'),
            kpi('Gastos sin rendir', soles(R.pendientes.total), `${R.pendientes.n} gasto(s)`, R.pendientes.n ? '' : 'ge-kpi-gris'),
            kpi('Gastado este mes', soles(R.mes.total), (R.mes.por_rubro[0] ? `Más en: ${esc(R.mes.por_rubro[0].rubro)}` : 'Sin gastos'), ''),
            kpi('Sin sustento SUNAT (mes)', soles(R.mes.sin_sustento), `${pctSin}% del gasto del mes`, R.mes.sin_sustento ? 'ge-kpi-mal' : 'ge-kpi-ok')
        ].join('');
    }

    // ============================================================
    // MOVIMIENTOS
    // ============================================================
    function estadoComprobante(m) {
        if (m.tipo !== 'Gasto') return '<span class="ge-cero">—</span>';
        if (m.comprobante_tipo === 'No registrado (histórico)') return '<span class="ge-estado gris">No registrado</span>';
        const clase = m.sustenta ? 'verde' : 'rojo';
        return `<span class="ge-estado ${clase}">${esc(m.comprobante_tipo)}</span>` +
            (m.comprobante_numero ? `<span class="ge-sub">N° ${esc(m.comprobante_numero)}</span>` : '');
    }
    function estadoFila(m) {
        if (m.estado === 'Anulado') return `<span class="ge-estado gris">Anulado</span><span class="ge-sub">${esc(m.motivo_anulacion || '')}</span>`;
        if (m.origen === 'Histórico') return '<span class="ge-estado gris">Histórico</span>';
        if (m.tipo !== 'Gasto') return '<span class="ge-estado verde">✔ Ingreso</span>';
        if (!m.rendicion_id) return '<span class="ge-estado rojo">⏳ Por rendir</span>';
        if (m.rendicion_estado === 'Aprobada') return `<span class="ge-estado verde">✔ Rendido N° ${m.rendicion_numero}</span>`;
        return `<span class="ge-estado amarillo">Enviado N° ${m.rendicion_numero}</span>`;
    }
    function pintarMovs(saldoAnterior) {
        if (!movs.length) {
            $('#ccMovs').innerHTML = R.historico.n || R.saldo
                ? '<div class="inv-vacio">No hay movimientos con ese filtro.</div>'
                : `<div class="inv-vacio">La caja de ${esc(empCodigo())} está vacía. Usa <b>+ Registrar gasto</b>, o carga tu Excel histórico en <b>Personas y datos</b>.</div>`;
            return;
        }
        const filtrado = $('#ccBuscar').value.trim() !== '';
        const lista = movs.slice().reverse();          // lo más reciente arriba
        const foto = m => m.tipo !== 'Gasto' || m.origen === 'Histórico' ? ''
            : m.fotos ? `<button type="button" class="ge-btn" data-fotos="${m.id}">Ver foto (${m.fotos})</button>`
            : (m.comprobante_tipo === 'Planilla de movilidad' ? '<span class="ge-sub">Se firma en la planilla</span>' : '<span class="ge-sin">Falta foto</span>');
        $('#ccMovs').innerHTML = `<table class="inv-table ge-tabla"><thead><tr><th>N°</th><th>Fecha</th><th>Rubro</th><th>Quién gastó / pagado a</th>
            <th>Descripción y N° PV / OC</th><th>Comprobante y foto</th><th>Monto (S/)</th>${filtrado ? '' : '<th>Saldo (S/)</th>'}<th>Estado</th><th>Acciones</th></tr></thead><tbody>
            ${lista.map(m => `<tr class="${m.estado === 'Anulado' ? 'cc-anulado' : m.origen === 'Histórico' ? 'cc-hist' : (m.tipo === 'Gasto' && !m.rendicion_id ? 'ge-fila-pend' : '')}">
                <td>${m.numero}</td><td class="ge-nw">${fecha(m.fecha)}</td>
                <td>${esc(m.rubro || m.tipo)}${m.empresa_gasto && m.empresa_gasto !== empCodigo() ? `<span class="ge-sub">Gasto de ${esc(m.empresa_gasto)}</span>` : ''}</td>
                <td>${esc(m.quien || '')}${m.pagado_a ? `<span class="ge-sub">Pagado a: ${esc(m.pagado_a)}</span>` : ''}</td>
                <td style="text-align:left">${esc(m.descripcion)}${m.referencia ? `<span class="ge-sub">${esc(m.referencia)}</span>` : ''}${m.autorizado_por ? `<span class="ge-sub">Autorizó: ${esc(m.autorizado_por)}</span>` : ''}${m.observacion ? `<span class="ge-sub">${esc(m.observacion)}</span>` : ''}</td>
                <td>${estadoComprobante(m)}${foto(m) ? `<div>${foto(m)}</div>` : ''}</td>
                <td class="ge-nw">${num(m.ingreso) ? `<b style="color:#0D9488">+ ${soles(m.ingreso)}</b>` : `<b style="color:#7C3AED">− ${soles(m.egreso)}</b>`}</td>
                ${filtrado ? '' : `<td class="ge-nw"><b style="color:${num(m.saldo) < 0 ? '#E60023' : 'inherit'}">${m.saldo == null ? '' : soles(m.saldo)}</b></td>`}
                <td>${estadoFila(m)}<span class="ge-sub">${esc(m.creado_por || '')} · ${fecha(m.creado_en)}</span>${(m.historial || []).length > 1 ? `<button type="button" class="ge-btn" data-historial="${m.id}">Historial</button>` : ''}</td>
                <td>${m.estado === 'Anulado' ? '' : [
                    m.tipo === 'Gasto' && m.origen !== 'Histórico' ? `<button type="button" class="ge-btn" data-foto="${m.id}">Subir foto</button>` : '',
                    !m.bloqueado ? `<button type="button" class="ge-btn" data-editar="${m.id}">Editar</button>` : '',
                    m.tipo === 'Gasto' ? `<button type="button" class="ge-btn" data-vale="${m.id}">Vale</button>` : '',
                    (!m.bloqueado || (esAdmin() && (m.origen === 'Histórico' || (m.tipo !== 'Gasto' && !m.rendicion_id)))) ? `<button type="button" class="ge-btn" data-anular="${m.id}">Anular</button>` : ''
                ].join('')}</td></tr>`).join('')}
            </tbody></table>
            ${saldoAnterior && $('#ccDesde').value ? `<div class="ge-sub">Saldo antes del ${fecha($('#ccDesde').value)}: ${soles(saldoAnterior)}</div>` : ''}`;
    }

    // ============================================================
    // VENTANA (modal)
    // ============================================================
    function abrirModal(titulo, detalle, campos, textoOk, fn) {
        $('#ccModalTit').textContent = titulo;
        $('#ccModalDet').innerHTML = detalle || '';
        $('#ccModalCampos').innerHTML = campos;
        $('#ccModalOk').textContent = textoOk || 'Guardar';
        $('#ccModalOk').hidden = !fn;
        alGuardar = fn;
        $('#ccModal').hidden = false;
        const primero = $('#ccModalCampos input:not([type=hidden]), #ccModalCampos select');
        if (primero) primero.focus();
        ajustarForm();
    }
    const cerrarModal = () => { $('#ccModal').hidden = true; alGuardar = null; };
    function leerForm() {
        const d = { empresa_id: empresa() };
        $$('input, select, textarea', $('#ccModalForm')).forEach(el => {
            if (!el.name || el.type === 'file') return;
            d[el.name] = el.type === 'checkbox' ? el.checked : el.value;
        });
        return d;
    }
    async function enviar(url, metodo, body) {
        const j = await api(url, { method: metodo, body: Object.assign({ empresa_id: empresa() }, body) });
        aviso(j.message || 'Listo', 'success');
        (j.avisos || []).forEach(a => aviso(a, 'warning'));
        cerrarModal();
        await cargar();
        return j;
    }

    function formGasto(m) {
        m = m || { fecha: hoy(), empresa_gasto: empCodigo() };
        const personal = gente.filter(p => p.activo && p.tipo !== 'Transportista' || (m.quien_id && p.id === m.quien_id));
        const transportistas = gente.filter(p => p.activo && p.tipo === 'Transportista');
        const empresas = $$('#ccEmpresa option').map(o => o.textContent);
        return `<label>Fecha<input type="date" name="fecha" required max="${hoy()}" value="${esc(m.fecha)}"></label>
            <label>Empresa dueña del gasto<select name="empresa_gasto">${opciones(empresas, m.empresa_gasto || empCodigo())}</select></label>
            <label>Rubro<select name="rubro" required>${opciones(OPC.rubros, m.rubro, 'Elige...')}</select></label>
            <label>Monto (S/)<input type="number" name="monto" required min="0.01" step="0.01" value="${m.egreso ?? ''}"></label>
            <label>Quién gastó<select name="quien_id" required><option value="">Elige...</option>${personal.map(p => `<option value="${p.id}" ${p.id === m.quien_id ? 'selected' : ''}>${esc(p.nombre)} (${esc(p.tipo)})</option>`).join('')}</select></label>
            <label>Pagado a <small>(transportista, tienda...)</small><input name="pagado_a" maxlength="150" list="ccListaPagados" value="${esc(m.pagado_a || '')}">
                <datalist id="ccListaPagados">${transportistas.map(p => `<option value="${esc(p.nombre)}">`).join('')}</datalist></label>
            <label style="grid-column:1/-1">Descripción <small>(de dónde a dónde, o para qué)</small><input name="descripcion" required maxlength="500" value="${esc(m.descripcion || '')}" placeholder="Ej.: Pasaje de Oficina a Malvinas para recoger guantes de Prosinfer"></label>
            <label>N° PV / OC / despacho <small>(si es de un pedido)</small><input name="referencia" maxlength="150" value="${esc(m.referencia || '')}" placeholder="Ej.: PV-KCF-000123"></label>
            <label>Tipo de comprobante<select name="comprobante_tipo" required>${opciones(OPC.comprobantes, m.comprobante_tipo, 'Elige...')}</select></label>
            <label data-cc="numero">N° de comprobante<input name="comprobante_numero" maxlength="40" value="${esc(m.comprobante_numero || '')}" placeholder="Ej.: F001-000123"></label>
            <label data-cc="ruc">RUC de quien emitió<input name="ruc_emisor" maxlength="11" inputmode="numeric" value="${esc(m.ruc_emisor || '')}"></label>
            <label data-cc="autoriza">Autorizado por <small>(gasto mayor a S/ ${OPC.topeAviso})</small><input name="autorizado_por" maxlength="150" value="${esc(m.autorizado_por || '')}" placeholder="Ej.: Erika por WhatsApp"></label>
            <label>Observación <small>(opcional)</small><input name="observacion" maxlength="500" value="${esc(m.observacion || '')}"></label>
            ${m.id ? '' : '<label style="grid-column:1/-1">Foto del voucher o comprobante <small>(puedes subirla después)</small><input type="file" name="foto" accept="image/*,.pdf" capture="environment"></label>'}
            <div class="ge-sub" data-cc="tip" style="grid-column:1/-1"></div>`;
    }
    function ajustarForm() {
        const f = $('#ccModalForm');
        if (!f.comprobante_tipo) return;
        const tipo = f.comprobante_tipo.value;
        const monto = num(f.monto && f.monto.value);
        const n = $('[data-cc=numero]', f); if (n) n.hidden = !OPC.conNumero.includes(tipo);
        const r = $('[data-cc=ruc]', f); if (r) r.hidden = tipo !== 'Factura';
        const a = $('[data-cc=autoriza]', f); if (a) a.hidden = monto <= OPC.topeAviso;
        const tip = $('[data-cc=tip]', f);
        if (tip) {
            const rubro = f.rubro.value;
            tip.innerHTML = tipo === 'Sin comprobante (vale)' ? '⚠ Sin comprobante el gasto no se descuenta ante SUNAT. Imprime el vale y que lo firme quien recibió el dinero.'
                : tipo === 'Planilla de movilidad' ? `Solo pasajes del personal. Tope: ${soles(R.config.tope_movilidad)} por persona al día. Cada persona firma su planilla con su DNI.`
                : (rubro === 'Movilidad del personal (pasajes)' ? 'Para pasajes del personal elige "Planilla de movilidad".'
                : (rubro === 'Flete y transporte de carga' && tipo !== 'Factura' ? 'Pide factura al transportista (con RUC): recuperas IGV y descuentas renta.' : ''));
        }
    }
    function abrirGasto(m) {
        const det = m ? `Gasto N° ${m.numero} · creado por ${esc(m.creado_por || '')} el ${fecha(m.creado_en)}` + (m.actualizado_en !== m.creado_en ? ` · modificado por ${esc(m.actualizado_por || '')} el ${fecha(m.actualizado_en)}` : '')
            : `Caja de <b>${esc(empCodigo())}</b> · saldo ${soles(R.saldo)}`;
        abrirModal(m ? `Editar gasto N° ${m.numero}` : 'Registrar gasto', det, formGasto(m), 'Guardar', async () => {
            const d = leerForm();
            const archivo = $('#ccModalForm input[name=foto]');
            if (m) return enviar('/caja-chica/api/gasto/' + m.id, 'PUT', d);
            const j = await api('/caja-chica/api/gasto', { method: 'POST', body: d });
            if (archivo && archivo.files[0]) {
                try { await subirFoto(j.id, archivo.files[0]); } catch (e) { aviso('El gasto se guardó, pero la foto no: ' + e.message, 'error'); }
            }
            aviso(j.message, 'success');
            (j.avisos || []).forEach(a => aviso(a, 'warning'));
            cerrarModal();
            await cargar();
        });
    }
    async function subirFoto(mid, archivo) {
        const fd = new FormData();
        fd.append('empresa_id', empresa());
        fd.append('foto', archivo);
        return api(`/caja-chica/api/movimiento/${mid}/foto`, { method: 'POST', body: fd });
    }
    function abrirSubirFoto(m) {
        abrirModal(`Foto del gasto N° ${m.numero}`, `${esc(m.descripcion)} · ${soles(m.egreso)}`,
            '<label style="grid-column:1/-1">Foto o PDF<input type="file" name="foto" accept="image/*,.pdf" capture="environment" required></label>', 'Subir',
            async () => {
                const a = $('#ccModalForm input[name=foto]');
                if (!a.files[0]) throw new Error('Elige la foto.');
                const j = await subirFoto(m.id, a.files[0]);
                aviso(j.message, 'success');
                cerrarModal();
                await cargar();
            });
    }
    async function verFotos(m) {
        const j = await api(`/caja-chica/api/movimiento/${m.id}/fotos?empresa_id=${encodeURIComponent(empresa())}`);
        abrirModal(`Fotos del gasto N° ${m.numero}`, `${esc(m.descripcion)} · ${soles(m.egreso)}`,
            `<div class="cc-fotos" style="grid-column:1/-1">${j.data.map(f => f.mime === 'application/pdf'
                ? `<a href="/caja-chica/foto/${f.id}" target="_blank">📄 ${esc(f.nombre)}</a>`
                : `<a href="/caja-chica/foto/${f.id}" target="_blank"><img src="/caja-chica/foto/${f.id}" alt="Foto"></a>`).join('')}</div>
             <div class="ge-sub" style="grid-column:1/-1">${j.data.map(f => `${esc(f.subido_por)} · ${fecha(f.subido_en)}`).join(' | ')}</div>`, null, null);
    }
    function abrirAnular(m) {
        abrirModal(`Anular movimiento N° ${m.numero}`, `${esc(m.descripcion)} · ${soles(num(m.egreso) || num(m.ingreso))}`,
            '<label style="grid-column:1/-1">¿Por qué se anula?<input name="motivo" required maxlength="500" placeholder="Ej.: se registró dos veces"></label>', 'Anular',
            async () => { const d = leerForm(); await enviar(`/caja-chica/api/movimiento/${m.id}/anular`, 'POST', d); });
    }
    function verHistorial(m) {
        abrirModal(`Historial del movimiento N° ${m.numero}`, '', `<ul class="ge-vac-lista" style="grid-column:1/-1">${m.historial.slice().reverse().map(h =>
            `<li>${fecha(h.fecha)} · ${esc(h.usuario)}: <b>${esc(h.accion)}</b>${h.motivo ? ' · ' + esc(h.motivo) : ''}${(h.cambios || []).length ? ' · ' + esc(h.cambios.join('; ')) : ''}</li>`).join('')}</ul>`, null, null);
    }
    function abrirIngreso() {
        const tipos = esAdmin() ? ['Reposición', 'Devolución'] : ['Devolución'];
        abrirModal('Depósito o devolución a la caja', esAdmin()
            ? 'Usa <b>Reposición</b> para un depósito de la empresa fuera de la rendición (por ejemplo, para completar el fondo la primera vez). Queda como pago en Finanzas para la conciliación bancaria.'
            : 'Usa <b>Devolución</b> cuando alguien devuelve dinero que sobró.',
            `<label>Tipo<select name="tipo">${opciones(tipos, tipos[0])}</select></label>
             <label>Fecha<input type="date" name="fecha" required max="${hoy()}" value="${hoy()}"></label>
             <label>Monto (S/)<input type="number" name="monto" required min="0.01" step="0.01"></label>
             <label>N° de operación <small>(si fue transferencia)</small><input name="numero_operacion" maxlength="80"></label>
             <label style="grid-column:1/-1">Descripción<input name="descripcion" required maxlength="500" placeholder="Ej.: Depósito para completar el fondo fijo de S/ 600"></label>`, 'Registrar',
            async () => { const d = leerForm(); await enviar('/caja-chica/api/ingreso', 'POST', d); });
    }
    function abrirMovilidad() {
        const h = hoy();
        const lunes = new Date(h + 'T12:00:00'); lunes.setDate(lunes.getDate() - ((lunes.getDay() + 6) % 7));
        abrirModal('Imprimir planilla de movilidad', 'Sale una planilla por persona con sus pasajes del periodo. Cada uno la firma con su nombre y DNI reales.',
            `<label>Desde<input type="date" name="desde" required value="${lunes.toISOString().slice(0, 10)}"></label>
             <label>Hasta<input type="date" name="hasta" required value="${h}"></label>`, 'Abrir para imprimir',
            async () => { const d = leerForm(); imprimir('/caja-chica/imprimir/movilidad', { desde: d.desde, hasta: d.hasta }); cerrarModal(); });
    }

    // ============================================================
    // RENDICIÓN
    // ============================================================
    function pintarRendicion() {
        const p = R.pendientes;
        const porAprobar = R.rendiciones.find(x => x.estado === 'Por aprobar');
        $('#ccRendir').innerHTML = porAprobar
            ? `<div class="ge-todo-ok">La rendición N° ${porAprobar.numero} (${soles(porAprobar.total_gastado)}) está enviada y espera la aprobación de Erika.</div>`
            : `<p>Hay <b>${p.n}</b> gasto(s) sin rendir por <b>${soles(p.total)}</b>${p.sin_foto ? ` · <span class="ge-rojo">${p.sin_foto} sin foto</span>` : ''}.
                Saldo actual ${soles(R.saldo)} · para completar el fondo faltan <b>${soles(R.por_reponer)}</b>.</p>
               <div class="cc-pie"><label>Rendir gastos hasta el <input type="date" id="ccRendirHasta" max="${hoy()}" value="${hoy()}"></label>
               <button type="button" class="btn btn-primary" id="ccEnviarRendicion" ${p.n ? '' : 'disabled'}>📤 Enviar rendición a Erika</button></div>`;
        const filas = R.rendiciones;
        $('#ccRendiciones').innerHTML = !filas.length ? '<div class="inv-vacio">Todavía no hay rendiciones.</div>'
            : `<table class="inv-table ge-tabla"><thead><tr><th>N°</th><th>Periodo</th><th>Total gastado (S/)</th><th>Sin sustento SUNAT (S/)</th>
                <th>Estado</th><th>Reposición</th><th>Enviada</th><th>Revisada</th><th>Acciones</th></tr></thead><tbody>
                ${filas.map(r => `<tr class="${r.estado === 'Aprobada' ? 'ge-fila-ok' : r.estado === 'Por aprobar' ? 'ge-fila-pend' : ''}">
                    <td>${r.numero}</td><td class="ge-nw">${fecha(r.desde)} al ${fecha(r.hasta)}</td><td>${soles(r.total_gastado)}</td>
                    <td>${num(r.sin_sustento) ? `<span class="ge-rojo">${soles(r.sin_sustento)}</span>` : soles(0)}</td>
                    <td><span class="ge-estado ${r.estado === 'Aprobada' ? 'verde' : r.estado === 'Por aprobar' ? 'rojo' : 'amarillo'}">${r.estado === 'Aprobada' ? '✔ ' : r.estado === 'Por aprobar' ? '⏳ ' : ''}${esc(r.estado)}</span>
                        ${r.estado === 'Observada' ? `<span class="ge-sub">${esc(r.observacion || '')}</span>` : ''}</td>
                    <td>${r.monto_repuesto != null ? `${soles(r.monto_repuesto)}<span class="ge-sub">${fecha(r.fecha_reposicion)}${r.numero_operacion ? ' · N° op. ' + esc(r.numero_operacion) : ''}</span>` : ''}</td>
                    <td><span class="ge-sub">${esc(r.enviada_por || '')} · ${fecha(r.enviada_en)}</span></td>
                    <td><span class="ge-sub">${r.revisada_por ? `${esc(r.revisada_por)} · ${fecha(r.revisada_en)}` : ''}</span></td>
                    <td class="ge-nw"><button type="button" class="ge-btn" data-ver-rend="${r.id}">Ver</button>
                        <button type="button" class="ge-btn" data-imp-rend="${r.id}">Imprimir</button>
                        ${r.estado === 'Por aprobar' && esAdmin() ? `<button type="button" class="ge-btn" data-aprobar="${r.id}">Aprobar y reponer</button><button type="button" class="ge-btn" data-observar="${r.id}">Observar</button>` : ''}</td>
                </tr>`).join('')}</tbody></table>`;
    }
    async function verRendicion(rid, paraAprobar) {
        const j = await api(`/caja-chica/api/rendicion/${rid}?empresa_id=${encodeURIComponent(empresa())}`);
        const { rendicion: r, gastos, por_rubro: rubros } = j.data;
        const sugerido = Math.max(j.data.fondo_fijo - j.data.saldo, 0);
        const tabla = `<div style="grid-column:1/-1">
            <table class="inv-table ge-tabla"><thead><tr><th>Rubro</th><th>N°</th><th>Total (S/)</th><th>Sin sustento (S/)</th></tr></thead><tbody>
            ${rubros.map(x => `<tr><td>${esc(x.rubro)}</td><td>${x.n}</td><td>${soles(x.total)}</td><td>${num(x.sin_sustento) ? soles(x.sin_sustento) : '—'}</td></tr>`).join('')}
            </tbody></table>
            <details><summary>Ver los ${gastos.length} gastos</summary><table class="inv-table ge-tabla"><thead><tr><th>N°</th><th>Fecha</th><th>Quién</th><th>Descripción</th><th>Comprobante</th><th>Foto</th><th>S/</th></tr></thead><tbody>
            ${gastos.map(g => `<tr><td>${g.numero}</td><td>${fecha(g.fecha)}</td><td>${esc(g.quien || '')}</td><td style="text-align:left">${esc(g.descripcion)}</td>
                <td>${esc(g.comprobante_tipo || '')}</td><td>${g.fotos ? '✔' : (g.comprobante_tipo === 'Planilla de movilidad' ? 'Planilla' : '<span class="ge-sin">Falta</span>')}</td><td>${soles(g.egreso)}</td></tr>`).join('')}
            </tbody></table></details></div>`;
        if (!paraAprobar) return abrirModal(`Rendición N° ${r.numero}`, `${fecha(r.desde)} al ${fecha(r.hasta)} · ${esc(r.estado)} · total ${soles(r.total_gastado)}`, tabla, null, null);
        abrirModal(`Aprobar rendición N° ${r.numero}`,
            `Gastado: <b>${soles(r.total_gastado)}</b> · saldo de la caja ${soles(j.data.saldo)} · para completar el fondo de ${soles(j.data.fondo_fijo)} hay que reponer <b>${soles(sugerido)}</b>.
             La reposición queda como pago en Finanzas ▸ Cobros y pagos (para la conciliación bancaria).`,
            tabla + `<label>Monto a reponer (S/)<input type="number" name="monto" min="0" step="0.01" value="${sugerido.toFixed(2)}"></label>
             <label>Fecha de la transferencia<input type="date" name="fecha_reposicion" max="${hoy()}" value="${hoy()}"></label>
             <label>N° de operación<input name="numero_operacion" maxlength="80"></label>
             <label>Banco de la empresa <small>(de donde sale)</small><input name="banco" maxlength="80"></label>
             <label style="grid-column:1/-1">Comentario <small>(opcional)</small><input name="observacion" maxlength="500"></label>`, 'Aprobar y reponer',
            async () => { const d = leerForm(); await enviar(`/caja-chica/api/rendicion/${rid}/aprobar`, 'POST', d); });
    }
    function abrirObservar(rid) {
        const r = R.rendiciones.find(x => x.id === rid);
        abrirModal(`Observar rendición N° ${r.numero}`, 'Sus gastos vuelven a Hellen para corregirlos y enviarlos de nuevo.',
            '<label style="grid-column:1/-1">¿Qué hay que corregir?<input name="motivo" required maxlength="500" placeholder="Ej.: falta la foto del taxi del martes"></label>', 'Observar',
            async () => { const d = leerForm(); await enviar(`/caja-chica/api/rendicion/${rid}/observar`, 'POST', d); });
    }

    // ============================================================
    // ARQUEO
    // ============================================================
    function pintarArqueo() {
        $('#ccArqueo').innerHTML = `<p>Cuenta el efectivo y mira el saldo de la cuenta de caja chica. El sistema dice <b>${soles(R.saldo)}</b> hoy.</p>
            <div class="ge-form" id="ccArqueoForm">
                <label>Fecha<input type="date" id="ccArqFecha" max="${hoy()}" value="${hoy()}"></label>
                <label>Efectivo contado (S/)<input type="number" id="ccArqEfectivo" min="0" step="0.01" value="0"></label>
                <label>Saldo en la cuenta de caja (S/)<input type="number" id="ccArqCuenta" min="0" step="0.01" value="0"></label>
                <label>Vales por rendir (S/)<input type="number" id="ccArqVales" min="0" step="0.01" value="0"></label>
                <label style="grid-column:1/-1">Explicación <small>(obligatoria si hay diferencia)</small><input id="ccArqExpl" maxlength="500"></label>
            </div>
            <div class="cc-pie"><span id="ccArqDif" class="ge-chip"></span><button type="button" class="btn btn-primary" id="ccArqGuardar">Guardar arqueo</button></div>
            ${R.arqueos.length ? `<table class="inv-table ge-tabla" style="margin-top:12px"><thead><tr><th>Fecha</th><th>Sistema (S/)</th><th>Real (S/)</th><th>Diferencia (S/)</th><th>Explicación</th><th>Hecho por</th></tr></thead><tbody>
                ${R.arqueos.map(a => `<tr class="${num(a.diferencia) === 0 ? 'ge-fila-ok' : 'ge-fila-pend'}"><td>${fecha(a.fecha)}</td><td>${soles(a.saldo_sistema)}</td>
                    <td>${soles(num(a.efectivo) + num(a.saldo_cuenta) + num(a.vales))}</td>
                    <td>${num(a.diferencia) === 0 ? '<span class="ge-estado verde">✔ Cuadra</span>' : `<span class="ge-estado rojo">${soles(a.diferencia)}</span>`}</td>
                    <td>${esc(a.explicacion || '')}</td><td><span class="ge-sub">${esc(a.hecho_por)} · ${fecha(a.hecho_en)}</span></td></tr>`).join('')}</tbody></table>` : ''}`;
        calcularDif();
    }
    function calcularDif() {
        const real = num($('#ccArqEfectivo').value) + num($('#ccArqCuenta').value) + num($('#ccArqVales').value);
        const fechaArq = $('#ccArqFecha').value;
        const dif = Math.round((real - R.saldo) * 100) / 100;
        $('#ccArqDif').innerHTML = fechaArq !== hoy() ? 'La diferencia se calcula al guardar (saldo a esa fecha).'
            : dif === 0 ? '✔ Cuadra con el sistema' : `Diferencia: ${soles(dif)} ${dif < 0 ? '(falta dinero)' : '(sobra dinero)'}`;
    }

    // ============================================================
    // PERSONAS Y CONFIGURACIÓN
    // ============================================================
    function pintarPersonas() {
        $('#ccPersonas').innerHTML = !gente.length ? '<div class="inv-vacio">Agrega al personal (con DNI, para la planilla de movilidad) y a los transportistas.</div>'
            : `<table class="inv-table ge-tabla"><thead><tr><th>Nombre</th><th>Tipo</th><th>DNI</th><th>RUC</th><th>Estado</th><th>Acciones</th></tr></thead><tbody>
                ${gente.map(p => `<tr class="${p.activo ? '' : 'ge-fila-cesado'}"><td><b>${esc(p.nombre)}</b></td><td>${esc(p.tipo)}</td>
                    <td>${p.dni ? esc(p.dni) : (p.tipo === 'Trabajador' || p.tipo === 'Practicante' ? '<span class="ge-sin">Falta</span>' : '')}</td>
                    <td>${p.ruc ? esc(p.ruc) : (p.tipo === 'Transportista' ? '<span class="ge-sin">Sin RUC: pídele que saque</span>' : '')}</td>
                    <td>${p.activo ? '<span class="ge-estado verde">Activo</span>' : '<span class="ge-estado gris">Inactivo</span>'}</td>
                    <td><button type="button" class="ge-btn" data-persona="${p.id}">Editar</button></td></tr>`).join('')}</tbody></table>`;
        const c = R.config;
        $('#ccConfig').innerHTML = `<table class="inv-table ge-tabla"><tbody>
            <tr><td>Fondo fijo</td><td><b>${soles(c.fondo_fijo)}</b></td></tr>
            <tr><td>Responsable de la caja</td><td>${esc(c.responsable || '—')}${c.responsable_dni ? ' · DNI ' + esc(c.responsable_dni) : ''}</td></tr>
            <tr><td>Cuenta de la caja chica</td><td>${esc(c.cuenta || '—')}</td></tr>
            <tr><td>Tope de movilidad por persona y día</td><td>${soles(c.tope_movilidad)} (4% del sueldo mínimo de ${soles(c.rmv)})</td></tr>
            ${c.actualizado_por ? `<tr><td>Modificado</td><td><span class="ge-sub">${esc(c.actualizado_por)} · ${fecha(c.actualizado_en)}</span></td></tr>` : ''}
            </tbody></table>
            <div class="cc-pie">${esAdmin() ? '<button type="button" class="btn btn-secondary" id="ccEditarConfig">Cambiar datos de la caja</button>' : ''}
            <button type="button" class="btn btn-secondary" id="ccActa">🖨 Acta de entrega del fondo fijo</button></div>`;
        $('#ccImportarPanel').hidden = !esAdmin();
        $('#ccImportar').innerHTML = R.historico.n
            ? `<div class="ge-todo-ok">Histórico cargado: ${R.historico.n} movimientos del ${fecha(R.historico.desde)} al ${fecha(R.historico.hasta)}. Se ven en gris en la lista y no se editan.</div>`
            : `<p>Sube la plantilla <b>Caja_Chica_KCF_plantilla_2026.xlsx</b> (hoja Movimientos). Primero verás un resumen y luego confirmas. Solo se puede hacer una vez, con la caja vacía.</p>
               <div class="cc-pie"><input type="file" id="ccImportarArchivo" accept=".xlsx"><button type="button" class="btn btn-secondary" id="ccImportarVer">Ver resumen</button></div>
               <div id="ccImportarVista"></div>`;
    }
    function abrirPersona(p) {
        p = p || { tipo: 'Practicante', activo: true };
        abrirModal(p.id ? `Editar a ${p.nombre}` : 'Agregar persona', `Empresa: <b>${esc(empCodigo())}</b>. El DNI es obligatorio para la planilla de movilidad.`,
            `<label>Nombre completo<input name="nombre" required maxlength="150" value="${esc(p.nombre || '')}"></label>
             <label>Tipo<select name="tipo">${opciones(OPC.tiposPersona, p.tipo)}</select></label>
             <label>DNI o carné de extranjería<input name="dni" maxlength="15" inputmode="numeric" value="${esc(p.dni || '')}"></label>
             <label>RUC <small>(transportistas)</small><input name="ruc" maxlength="11" inputmode="numeric" value="${esc(p.ruc || '')}"></label>
             <label class="ge-check"><input type="checkbox" name="activo" ${p.activo ? 'checked' : ''}> Activo (sale en las listas)</label>`, 'Guardar',
            async () => { const d = leerForm(); if (p.id) await enviar('/caja-chica/api/personas/' + p.id, 'PUT', d); else await enviar('/caja-chica/api/personas', 'POST', d); });
    }
    function abrirConfig() {
        const c = R.config;
        abrirModal(`Datos de la caja chica de ${empCodigo()}`, 'El fondo fijo es el monto con el que la caja empieza cada semana.',
            `<label>Fondo fijo (S/)<input type="number" name="fondo_fijo" required min="1" step="0.01" value="${c.fondo_fijo}"></label>
             <label>Responsable<input name="responsable" required maxlength="150" value="${esc(c.responsable || 'Hellen Blas')}"></label>
             <label>DNI de la responsable<input name="responsable_dni" maxlength="15" value="${esc(c.responsable_dni || '')}"></label>
             <label>Cuenta de la caja chica <small>(banco y N°)</small><input name="cuenta" maxlength="150" value="${esc(c.cuenta || '')}" placeholder="Ej.: BCP ahorros 191-... (solo caja chica)"></label>
             <label>Sueldo mínimo vigente (S/)<input type="number" name="rmv" min="900" step="0.01" value="${c.rmv}"></label>`, 'Guardar',
            async () => { const d = leerForm(); await enviar('/caja-chica/api/config', 'POST', d); });
    }
    async function importar(confirmar) {
        const a = $('#ccImportarArchivo');
        if (!a || !a.files[0]) return aviso('Elige el Excel.', 'error');
        const fd = new FormData();
        fd.append('empresa_id', empresa());
        fd.append('archivo', a.files[0]);
        fd.append('confirmar', confirmar ? '1' : '0');
        try {
            const j = await api('/caja-chica/api/importar', { method: 'POST', body: fd });
            const v = j.data;
            if (confirmar) { aviso(`Histórico cargado: ${v.filas} movimientos. Saldo final ${soles(v.saldo_final)}.`, 'success'); return cargar(); }
            $('#ccImportarVista').innerHTML = `<div class="ge-todo-ok">${v.filas} movimientos del ${fecha(v.desde)} al ${fecha(v.hasta)} ·
                saldo inicial ${soles(v.saldo_inicial)} · ingresos ${soles(v.ingresos)} · gastos ${soles(v.gastos)} · <b>saldo final ${soles(v.saldo_final)}</b>.</div>
                <button type="button" class="btn btn-primary" id="ccImportarOk">Confirmar y cargar</button>`;
        } catch (e) { aviso(e.message, 'error'); }
    }

    // ============================================================
    // EVENTOS
    // ============================================================
    document.addEventListener('DOMContentLoaded', () => {
        APP = $('#ccApp');
        if (!APP) return;
        $$('#ccTabs .tab-btn').forEach(b => b.addEventListener('click', () => irA(b.dataset.tab)));
        irA(new URLSearchParams(location.search).get('tab') || 'gastos');
        $('#ccEmpresa').addEventListener('change', cargar);
        $('#ccNuevoGasto').addEventListener('click', () => abrirGasto(null));
        $('#ccIngreso').addEventListener('click', abrirIngreso);
        $('#ccMovilidad').addEventListener('click', abrirMovilidad);
        $('#ccNuevaPersona').addEventListener('click', () => abrirPersona(null));
        ['#ccDesde', '#ccHasta', '#ccAnulados'].forEach(s => $(s).addEventListener('change', cargarMovs));
        let t = null;
        $('#ccBuscar').addEventListener('input', () => { clearTimeout(t); t = setTimeout(cargarMovs, 350); });
        $('#ccModalCancelar').addEventListener('click', cerrarModal);
        $('#ccModalForm').addEventListener('change', ajustarForm);
        $('#ccModalForm').addEventListener('input', ajustarForm);
        $('#ccModalForm').addEventListener('submit', async ev => {
            ev.preventDefault();
            if (!alGuardar) return cerrarModal();
            const ok = $('#ccModalOk');
            ok.disabled = true;
            try { await alGuardar(); } catch (e) { aviso(e.message, 'error'); } finally { ok.disabled = false; }
        });
        APP.addEventListener('input', ev => { if (ev.target.closest('#ccArqueoForm')) calcularDif(); });
        APP.addEventListener('click', async ev => {
            const b = ev.target.closest('button');
            if (!b) return;
            const mov = id => movs.find(m => String(m.id) === String(id));
            try {
                if (b.dataset.editar) abrirGasto(mov(b.dataset.editar));
                else if (b.dataset.foto) abrirSubirFoto(mov(b.dataset.foto));
                else if (b.dataset.fotos) await verFotos(mov(b.dataset.fotos));
                else if (b.dataset.anular) abrirAnular(mov(b.dataset.anular));
                else if (b.dataset.historial) verHistorial(mov(b.dataset.historial));
                else if (b.dataset.vale) imprimir('/caja-chica/imprimir/vale/' + b.dataset.vale);
                else if (b.dataset.verRend) await verRendicion(+b.dataset.verRend, false);
                else if (b.dataset.impRend) imprimir('/caja-chica/imprimir/rendicion/' + b.dataset.impRend);
                else if (b.dataset.aprobar) await verRendicion(+b.dataset.aprobar, true);
                else if (b.dataset.observar) abrirObservar(+b.dataset.observar);
                else if (b.dataset.persona) abrirPersona(gente.find(p => String(p.id) === b.dataset.persona));
                else if (b.id === 'ccEditarConfig') abrirConfig();
                else if (b.id === 'ccActa') imprimir('/caja-chica/imprimir/acta');
                else if (b.id === 'ccImportarVer') await importar(false);
                else if (b.id === 'ccImportarOk') await importar(true);
                else if (b.id === 'ccEnviarRendicion') {
                    b.disabled = true;
                    try {
                        const j = await api('/caja-chica/api/rendicion', { method: 'POST', body: { empresa_id: empresa(), hasta: $('#ccRendirHasta').value } });
                        aviso(j.message, 'success');
                        await cargar();
                    } finally { b.disabled = false; }
                } else if (b.id === 'ccArqGuardar') {
                    const j = await api('/caja-chica/api/arqueo', { method: 'POST', body: { empresa_id: empresa(), fecha: $('#ccArqFecha').value,
                        efectivo: $('#ccArqEfectivo').value, saldo_cuenta: $('#ccArqCuenta').value, vales: $('#ccArqVales').value, explicacion: $('#ccArqExpl').value } });
                    aviso(j.message, 'success');
                    await cargar();
                }
            } catch (e) { aviso(e.message, 'error'); }
        });
        cargar();
    });
})();
