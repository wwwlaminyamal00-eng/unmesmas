// static/js/caja_chica.js - Caja chica con fondo fijo (pedido de Erika 22/10/2026)
(function () {
    'use strict';
    const $ = (s, r = document) => r.querySelector(s);
    const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
    const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const num = v => Number(v || 0);
    const soles = v => (num(v) < 0 ? '-' : '') + 'S/ ' + Math.abs(num(v)).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const TABS = ['gastos', 'rendicion', 'arqueo', 'personas'];
    const OPC = Object.assign({ rubros: [], comprobantes: [], tiposPersona: [], conNumero: [], sustenta: [], topeAviso: 100, descripciones: [], pidenDetalle: [] }, window.CC_OPCIONES || {});
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
    // Erika 04/11/2026: "falta VALE": se muestra como "Vale" (en la base sigue "Sin comprobante (vale)", igual que lo ya registrado)
    const NOMBRE_COMPROBANTE = { 'Sin comprobante (vale)': 'Vale' };
    const nomComp = t => NOMBRE_COMPROBANTE[t] || t || '';
    const opciones = (lista, actual, vacio) => (vacio ? `<option value="">${esc(vacio)}</option>` : '') +
        lista.map(x => `<option value="${esc(x)}" ${x === actual ? 'selected' : ''}>${esc(nomComp(x))}</option>`).join('');
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
        return `<span class="ge-estado ${clase}">${esc(nomComp(m.comprobante_tipo))}</span>` +
            (m.comprobante_numero ? `<span class="ge-sub">N° ${esc(m.comprobante_numero)}</span>` : '') +
            (m.comprobante_tipo === 'Planilla de movilidad' ? (m.planilla_numero && m.planilla_estado === 'Emitida'
                ? `<span class="ge-sub">Planilla N° ${String(m.planilla_numero).padStart(6, '0')}</span>` : '<span class="ge-sub ge-rojo">Planilla sin emitir</span>') : '');
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
            <th>Descripción</th><th>N° PV / PC</th><th>Comprobante y foto</th><th>Monto (S/)</th>${filtrado ? '' : '<th>Saldo (S/)</th>'}<th>Estado</th><th>Acciones</th></tr></thead><tbody>
            ${lista.map(m => `<tr class="${m.estado === 'Anulado' ? 'cc-anulado' : m.origen === 'Histórico' ? 'cc-hist' : (m.tipo === 'Gasto' && !m.rendicion_id ? 'ge-fila-pend' : '')}">
                <td>${m.numero}</td><td class="ge-nw">${fecha(m.fecha)}</td>
                <td>${esc(m.rubro || m.tipo)}${m.empresa_gasto && m.empresa_gasto !== empCodigo() ? `<span class="ge-sub">Gasto de ${esc(m.empresa_gasto)}</span>` : ''}</td>
                <td>${esc(m.quien || '')}${m.pagado_a ? `<span class="ge-sub">Pagado a: ${esc(m.pagado_a)}</span>` : ''}</td>
                <td style="text-align:left">${esc(m.descripcion)}${m.detalle ? `<span class="ge-sub">${esc(m.detalle)}</span>` : ''}${m.autorizado_por ? `<span class="ge-sub">Autorizó: ${esc(m.autorizado_por)}</span>` : ''}${m.observacion ? `<span class="ge-sub">Obs.: ${esc(m.observacion)}</span>` : ''}</td>
                <td class="ge-nw">${m.referencia ? esc(m.referencia) : '<span class="ge-cero">—</span>'}</td>
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
            ${$('#ccDesde').value ? `<div class="ge-sub">Se ve desde el ${fecha($('#ccDesde').value)}${saldoAnterior ? ` · saldo antes de esa fecha: ${soles(saldoAnterior)}` : ''}. Lo anterior sigue guardado: pulsa <b>📚 Ver todo (histórico)</b>.</div>` : ''}`;
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

    const horaAhora = () => new Date().toLocaleTimeString('en-GB', { timeZone: 'America/Lima', hour: '2-digit', minute: '2-digit', hour12: false });
    function formGasto(m) {
        m = m || { fecha: hoy(), hora: horaAhora(), empresa_gasto: empCodigo() };
        const personal = gente.filter(p => (p.activo && p.tipo !== 'Transportista') || (m.quien_id && p.id === m.quien_id));
        const pagables = gente.filter(p => p.activo || p.nombre === m.pagado_a);
        const enLista = !m.pagado_a || pagables.some(p => p.nombre === m.pagado_a);
        const grupo = (titulo, lista) => lista.length ? `<optgroup label="${esc(titulo)}">${lista.map(p => `<option value="${esc(p.nombre)}" ${p.nombre === m.pagado_a ? 'selected' : ''}>${esc(p.nombre)}</option>`).join('')}</optgroup>` : '';
        const descEnLista = !m.descripcion || OPC.descripciones.includes(m.descripcion);
        const empresas = $$('#ccEmpresa option').map(o => o.textContent);
        return `<label>Fecha<input type="date" name="fecha" required max="${hoy()}" value="${esc(m.fecha)}"></label>
            <input type="hidden" name="hora" value="${esc(m.hora || '')}">
            <input type="hidden" name="_rubro_anterior" value="${esc(m.rubro || '')}">
            <label>Empresa dueña del gasto<select name="empresa_gasto">${opciones(empresas, m.empresa_gasto || empCodigo())}</select></label>
            <label>Rubro<select name="rubro" required>${opciones(m.rubro && !OPC.rubros.includes(m.rubro) ? OPC.rubros.concat([m.rubro]) : OPC.rubros, m.rubro, 'Elige...')}</select></label>
            <label>Monto (S/)<input type="number" name="monto" required min="0.01" step="0.01" value="${m.egreso ?? ''}"></label>
            <label>Quién gastó<select name="quien_id" required><option value="">Elige...</option>${personal.map(p => `<option value="${p.id}" ${p.id === m.quien_id ? 'selected' : ''}>${esc(p.nombre)} (${esc(p.tipo)})</option>`).join('')}</select></label>
            <label>Pagado a<select name="pagado_a"><option value="" data-no-flete>— No aplica —</option>
                ${grupo('Transportistas', pagables.filter(p => p.tipo === 'Transportista'))}<optgroup label="Personal" data-no-flete>${pagables.filter(p => p.tipo !== 'Transportista' && p.tipo !== 'Otro').map(p => `<option value="${esc(p.nombre)}" ${p.nombre === m.pagado_a ? 'selected' : ''}>${esc(p.nombre)}</option>`).join('')}</optgroup>${grupo('Otros', pagables.filter(p => p.tipo === 'Otro'))}
                ${(OPC.proveedores || []).length ? `<optgroup label="Proveedores registrados (con RUC)" data-solo-flete>${OPC.proveedores.map(p => `<option value="${esc(p.nombre)}" data-ruc="${esc(p.ruc)}" ${p.nombre === m.pagado_a ? 'selected' : ''}>${esc(p.nombre)}${p.ruc ? ' · RUC ' + esc(p.ruc) : ''}</option>`).join('')}</optgroup>` : ''}
                <option value="__otro" ${enLista || (OPC.proveedores || []).some(p => p.nombre === m.pagado_a) ? '' : 'selected'}>Otro (escribir: transportista, tienda...)</option></select></label>
            <div class="ge-sub" data-cc="ayuda-flete" style="grid-column:1/-1" hidden>🚚 <b>Quién gastó</b>: quien dio el dinero. <b>Pagado a</b>: el transportista.</div>
            <label data-cc="pagado-otro">Escribe a quién se pagó<input name="pagado_a_otro" maxlength="150" value="${enLista ? '' : esc(m.pagado_a)}" placeholder="Ej.: Tienda Sodimac"></label>
            <label>Descripción<select name="descripcion" required>${opciones(OPC.descripciones, descEnLista ? m.descripcion : 'Otro (escribir)', 'Elige...')}</select></label>
            <label data-cc="desc-otro">Escribe la descripción<input name="descripcion_otro" maxlength="500" value="${descEnLista ? '' : esc(m.descripcion)}"></label>
            <label data-cc="detalle" style="grid-column:1/-1">De dónde a dónde <small>(lo pide la planilla de movilidad)</small><input name="detalle" maxlength="300" value="${esc(m.detalle || '')}" placeholder="Ej.: Oficina SMP → Komatsu Lurín → Oficina SMP"></label>
            <label>N° PV / PC <small>(si es de un pedido)</small><input name="referencia" maxlength="150" value="${esc(m.referencia || '')}" placeholder="Ej.: PV-KCF-000123"></label>
            <label>Tipo de comprobante<select name="comprobante_tipo" required>${opciones(OPC.comprobantes, m.comprobante_tipo, 'Elige...')}</select></label>
            <label data-cc="numero">N° de comprobante<input name="comprobante_numero" maxlength="40" value="${esc(m.comprobante_numero || '')}" placeholder="Ej.: F001-000123"></label>
            <label data-cc="ruc">RUC de quien emitió<input name="ruc_emisor" maxlength="11" inputmode="numeric" value="${esc(m.ruc_emisor || '')}"></label>
            <label data-cc="autoriza">Autorizado por <small>(gasto mayor a S/ ${OPC.topeAviso})</small><input name="autorizado_por" maxlength="150" value="${esc(m.autorizado_por || '')}" placeholder="Ej.: Erika por WhatsApp"></label>
            <label style="grid-column:1/-1">Observación <small>(opcional)</small><textarea name="observacion" maxlength="1000" rows="3">${esc(m.observacion || '')}</textarea></label>
            ${m.id ? '' : '<label style="grid-column:1/-1">Foto del voucher o comprobante <small>(puedes subirla después)</small><input type="file" name="foto" accept="image/*,.pdf" capture="environment"></label>'}
            <div class="ge-sub" data-cc="tip" style="grid-column:1/-1"></div>`;
    }
    function leerGasto() {
        const d = leerForm();
        if (d.pagado_a === '__otro') d.pagado_a = (d.pagado_a_otro || '').trim();
        delete d.pagado_a_otro;
        return d;
    }
    function ajustarForm() {
        const f = $('#ccModalForm');
        if (!f.comprobante_tipo) return;
        const tipo = f.comprobante_tipo.value;
        const monto = num(f.monto && f.monto.value);
        const n = $('[data-cc=numero]', f); if (n) n.hidden = !OPC.conNumero.includes(tipo);
        const r = $('[data-cc=ruc]', f); if (r) r.hidden = tipo !== 'Factura';
        const a = $('[data-cc=autoriza]', f); if (a) a.hidden = monto <= OPC.topeAviso;
        // Erika 04/11/2026: en flete "Pagado a" es el transportista contratado: sin "No aplica" ni el personal
        const esFlete = f.rubro && f.rubro.value === 'Flete y transporte de mercadería';
        if (f.pagado_a) {
            $$('[data-no-flete], [data-no-flete] option', f.pagado_a).forEach(o => { o.hidden = esFlete; o.disabled = esFlete; });
            $$('[data-solo-flete], [data-solo-flete] option', f.pagado_a).forEach(o => { o.hidden = !esFlete; o.disabled = !esFlete; });
            const sel = f.pagado_a.selectedOptions[0];
            const apagada = o => !o || o.disabled || (o.parentElement && o.parentElement.disabled);
            if (esFlete && apagada(sel)) f.pagado_a.value = '__otro';
            if (!esFlete && sel && apagada(sel)) f.pagado_a.value = '';
            const elegida = f.pagado_a.selectedOptions[0];
            const ruc = elegida && elegida.dataset ? elegida.dataset.ruc : '';
            if (ruc && f.ruc_emisor && !f.ruc_emisor.value) f.ruc_emisor.value = ruc;
        }
        const af = $('[data-cc=ayuda-flete]', f); if (af) af.hidden = !esFlete;
        if (f.pagado_a_otro) f.pagado_a_otro.placeholder = esFlete ? 'Ej.: Ever Alfaro (transportista)' : 'Ej.: Tienda Sodimac';
        const po = $('[data-cc=pagado-otro]', f); if (po) po.hidden = !f.pagado_a || f.pagado_a.value !== '__otro';
        const dot = $('[data-cc=desc-otro]', f); if (dot) dot.hidden = !f.descripcion || f.descripcion.value !== 'Otro (escribir)';
        const det = $('[data-cc=detalle]', f); if (det) det.hidden = !OPC.pidenDetalle.includes(f.rubro.value);
        const tip = $('[data-cc=tip]', f);
        if (tip) {
            const rubro = f.rubro.value;
            tip.innerHTML = tipo === 'Sin comprobante (vale)' ? '⚠ Vale = gasto sin comprobante (gaseosa, recarga, comisión del banco...). <b>No se descuenta ante SUNAT.</b> Si puedes, pide boleta o factura. Imprime el vale y que lo firme quien recibió el dinero.'
                : tipo === 'Planilla de movilidad' ? `Solo pasajes del personal (bus, colectivo, taxi, Yango). Tope: <b>${soles(R.config.tope_movilidad)}</b> por persona al día. Al final de la semana pulsa <b>🧾 Planillas de movilidad ▸ Emitir</b>: sale numerada y la firma quien viajó.`
                : (rubro === 'Movilidad operativa del personal' ? 'Para pasajes del personal sin factura elige <b>"Planilla de movilidad"</b>. Si el taxi o la app te da factura al RUC de la empresa, mejor: elige "Factura".'
                : (rubro === 'Flete y transporte de mercadería' && tipo !== 'Factura' ? '💰 Pide <b>factura</b> al transportista (con RUC): recuperas el 18% de IGV y descuentas renta.' : ''));
        }
    }
    function abrirGasto(m) {
        const det = m ? `Gasto N° ${m.numero} · creado por ${esc(m.creado_por || '')} el ${fecha(m.creado_en)}` + (m.actualizado_en !== m.creado_en ? ` · modificado por ${esc(m.actualizado_por || '')} el ${fecha(m.actualizado_en)}` : '')
            : `Caja de <b>${esc(empCodigo())}</b> · saldo ${soles(R.saldo)}`;
        abrirModal(m ? `Editar gasto N° ${m.numero}` : 'Registrar gasto', det, formGasto(m), 'Guardar', async () => {
            const d = leerGasto();
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
    async function abrirMovilidad() {
        const h = hoy();
        const lunes = new Date(h + 'T12:00:00'); lunes.setDate(lunes.getDate() - ((lunes.getDay() + 6) % 7));
        let lista = [];
        try { lista = (await api('/caja-chica/api/planillas?empresa_id=' + encodeURIComponent(empresa()))).data; } catch (e) { aviso(e.message, 'error'); }
        const pend = movs.filter(m => m.estado === 'Activo' && m.comprobante_tipo === 'Planilla de movilidad' && !(m.planilla_numero && m.planilla_estado === 'Emitida'));
        const tabla = lista.length ? `<table class="inv-table ge-tabla"><thead><tr><th>N° planilla</th><th>Persona</th><th>Periodo</th><th>Pasajes</th><th>Total (S/)</th><th>Estado</th><th>Emitida</th><th>Acciones</th></tr></thead><tbody>
            ${lista.map(p => `<tr class="${p.estado === 'Anulada' ? 'cc-anulado' : ''}"><td><b>${String(p.numero).padStart(6, '0')}</b></td><td>${esc(p.quien)}</td>
                <td class="ge-nw">${fecha(p.desde)} al ${fecha(p.hasta)}</td><td>${p.pasajes}</td><td>${soles(p.total)}</td>
                <td>${p.estado === 'Emitida' ? '<span class="ge-estado verde">✔ Emitida</span>' : `<span class="ge-estado gris">Anulada</span><span class="ge-sub">${esc(p.motivo_anulacion || '')}</span>`}</td>
                <td><span class="ge-sub">${esc(p.emitida_por || '')} · ${fecha(p.emitida_en)}</span></td>
                <td class="ge-nw">${p.estado === 'Emitida' ? `<button type="button" class="ge-btn" data-imp-planilla="${p.id}">🖨 Imprimir</button>${esAdmin() ? `<button type="button" class="ge-btn" data-anular-planilla="${p.id}">Anular</button>` : ''}` : ''}</td></tr>`).join('')}
            </tbody></table>` : '<div class="inv-vacio">Todavía no hay planillas emitidas.</div>';
        abrirModal('🧾 Planillas de movilidad', `<ul class="ge-vac-lista">
                <li>Cada persona tiene <b>su propia planilla</b> con <b>N° automático</b> (000001, 000002...).</li>
                <li>Al <b>emitir</b>, sus pasajes quedan amarrados a ese N° y <b style="color:#E60023">ya no se editan</b>.</li>
                <li>Imprime y que <b>la persona que viajó</b> la firme con su nombre y DNI. Sube la foto de la hoja firmada.</li>
                ${pend.length ? `<li style="color:#E60023"><b>${pend.length} pasaje(s) sin planilla</b> en la lista.</li>` : ''}</ul>`,
            `<label>Desde<input type="date" name="desde" required value="${lunes.toISOString().slice(0, 10)}"></label>
             <label>Hasta<input type="date" name="hasta" required max="${h}" value="${h}"></label>
             <div style="grid-column:1/-1">${tabla}</div>`, 'Emitir planillas de esas fechas',
            async () => {
                const d = leerForm();
                const j = await api('/caja-chica/api/planillas', { method: 'POST', body: d });
                aviso(j.message, 'success');
                imprimir('/caja-chica/imprimir/movilidad', { ids: j.data.map(x => x.id).join(',') });
                cerrarModal();
                await cargar();
            });
    }
    function abrirAnularPlanilla(pid) {
        abrirModal('Anular planilla de movilidad', 'El N° no se vuelve a usar. Sus pasajes quedan libres para corregirlos y emitir otra planilla.',
            '<label style="grid-column:1/-1">¿Por qué se anula?<input name="motivo" required maxlength="500" placeholder="Ej.: monto del pasaje del martes mal escrito"></label>', 'Anular',
            async () => { const d = leerForm(); await enviar(`/caja-chica/api/planillas/${pid}/anular`, 'POST', d); });
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
            ${gastos.map(g => `<tr><td>${g.numero}</td><td>${fecha(g.fecha)}</td><td>${esc(g.quien || '')}</td><td style="text-align:left">${esc(g.descripcion)}${g.detalle ? `<span class="ge-sub">${esc(g.detalle)}</span>` : ''}</td>
                <td>${esc(nomComp(g.comprobante_tipo))}</td><td>${g.fotos ? '✔' : (g.comprobante_tipo === 'Planilla de movilidad' ? 'Planilla' : '<span class="ge-sin">Falta</span>')}</td><td>${soles(g.egreso)}</td></tr>`).join('')}
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
        $('#ccMovilidad').addEventListener('click', () => abrirMovilidad().catch(e => aviso(e.message, 'error')));
        $('#ccNuevaPersona').addEventListener('click', () => abrirPersona(null));
        ['#ccDesde', '#ccHasta', '#ccAnulados'].forEach(s => $(s).addEventListener('change', cargarMovs));
        // Erika 04/11/2026: "el ERP está muy saturado". Por defecto se ven los últimos 30 días; lo anterior sigue
        // guardado (sustento ante SUNAT por 5 años) y se ve con "📚 Ver todo".
        const hace30 = new Date(hoy() + 'T12:00:00'); hace30.setDate(hace30.getDate() - 30);
        $('#ccDesde').value = hace30.toISOString().slice(0, 10);
        $('#ccVerTodo').addEventListener('click', () => {
            const todo = $('#ccDesde').value !== '';
            $('#ccDesde').value = todo ? '' : hace30.toISOString().slice(0, 10);
            $('#ccHasta').value = '';
            $('#ccVerTodo').textContent = todo ? '🗓 Ver solo últimos 30 días' : '📚 Ver todo (histórico)';
            cargarMovs();
        });
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
                else if (b.dataset.impPlanilla) imprimir('/caja-chica/imprimir/movilidad', { ids: b.dataset.impPlanilla });
                else if (b.dataset.anularPlanilla) abrirAnularPlanilla(+b.dataset.anularPlanilla);
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
