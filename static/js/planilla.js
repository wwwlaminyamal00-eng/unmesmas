// static/js/planilla.js - Planilla y RRHH simple (pedido de Erika 21/10/2026)
(function () {
    'use strict';
    const $ = (s, r = document) => r.querySelector(s);
    const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
    const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const num = v => Number(v || 0);
    const soles = v => 'S/ ' + num(v).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const dias = v => num(v).toLocaleString('es-PE', { maximumFractionDigits: 1 });
    const TABS = ['pagos', 'personal', 'beneficios'];
    const OPC = window.PLA_OPCIONES || { regimenes: {}, tipos: [], pensiones: [] };
    let APP = null;
    let tab = 'pagos';
    let pagos = null;
    let gente = null;
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
        if (o.body) { o.headers['Content-Type'] = 'application/json'; o.body = JSON.stringify(o.body); }
        const r = await fetch(url, o);
        let j = {};
        try { j = await r.json(); } catch (e) { /* sin JSON */ }
        if (!r.ok || j.success === false) throw new Error(j.error || `Error ${r.status}`);
        return j;
    }
    const empresa = () => $('#plaEmpresa').value;
    const empCodigo = () => ($('#plaEmpresa').selectedOptions[0] || {}).textContent || '';
    const kpi = (titulo, valor, pie, clase) => `<div class="inv-kpi ${clase || ''}"><small>${titulo}</small><b>${valor}</b><span>${pie || ''}</span></div>`;

    // ============================================================
    // PESTAÑAS Y CARGA
    // ============================================================
    function irA(t) {
        tab = TABS.includes(t) ? t : 'pagos';
        $$('#plaTabs .tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
        TABS.forEach(x => $('#pla-sec-' + x).classList.toggle('active', x === tab));
        try { history.replaceState(null, '', '/planilla?tab=' + tab); } catch (e) { /* nada */ }
        if (window.abrirMenuModulo) window.abrirMenuModulo();
    }

    async function cargar() {
        $('#plaKpis').innerHTML = '<div class="inv-vacio">Calculando...</div>';
        try {
            const q = new URLSearchParams({ empresa_id: empresa(), periodo: $('#plaMes').value || '' });
            const [p, g] = await Promise.all([api('/planilla/api/pagos?' + q), api('/planilla/api/personal?empresa_id=' + encodeURIComponent(empresa()))]);
            pagos = p.data;
            gente = g.data;
        } catch (e) {
            $('#plaKpis').innerHTML = `<div class="inv-vacio">⚠ ${esc(e.message)}</div>`;
            return;
        }
        if (!$('#plaMes').value) $('#plaMes').value = pagos.periodo;
        pintar();
    }

    function pintar() {
        const c = gente.config;
        $('#plaRegimen').innerHTML = `${esc(c.regimen_nombre)} · Sueldo mínimo ${soles(c.rmv)}` +
            (APP.dataset.admin === 'true' ? ' · <a href="#" id="plaCambiarRegimen">cambiar</a>' : '');
        const avisos = [];
        if (!c.configurado) avisos.push(`Confirma el régimen laboral de ${esc(gente.empresa.codigo)} (general, pequeña o microempresa): cambia las vacaciones, la CTS y las gratificaciones.` +
            (APP.dataset.admin === 'true' ? ' Usa "cambiar", arriba.' : ' Lo hace el administrador.'));
        const acum = gente.personal.filter(p => p.activo && p.vacaciones && p.vacaciones.acumulado);
        if (acum.length) avisos.push(`Vacaciones vencidas (pasó el año para tomarlas): ${acum.map(p => `${esc(p.nombres)} (${p.vacaciones.vencidos} días)`).join(', ')}. Prográmalas pronto.`);
        const r5 = gente.personal.filter(p => p.activo && p.renta_5ta);
        if (r5.length) avisos.push(`Pide al contador la retención de renta de 5.ª de: ${r5.map(p => esc(p.nombres)).join(', ')} (gana más de 7 UIT al año).`);
        $('#plaAvisos').innerHTML = avisos.length ? `<div class="ge-aviso-rojo"><b>Revisa:</b><ul>${avisos.map(a => `<li>${a}</li>`).join('')}</ul></div>` : '';

        const cu = gente.cuenta;
        const activos = Object.values(cu).reduce((a, b) => a + b, 0);
        const vac = gente.personal.filter(p => p.activo && p.vacaciones).reduce((a, p) => a + Math.max(p.vacaciones.pendientes, 0), 0);
        $('#plaKpis').innerHTML = [
            kpi('Personas activas', activos, `${cu['Planilla'] || 0} en planilla · ${cu['Practicante'] || 0} practicantes · ${cu['Recibo por honorarios'] || 0} con recibo`, ''),
            kpi(`Falta pagar · ${esc(pagos.nombre_periodo)}`, soles(pagos.por_pagar), pagos.por_pagar_n ? `${pagos.por_pagar_n} pago(s) pendientes` : 'Todo pagado',
                pagos.por_pagar_n ? 'ge-kpi-mal' : 'ge-kpi-ok'),
            kpi('Pagado', soles(pagos.pagado), 'Con N° de operación', pagos.pagado ? 'ge-kpi-ok' : 'ge-kpi-gris'),
            kpi('EsSalud (lo paga la empresa)', soles(pagos.totales.essalud), 'Se paga a SUNAT', 'ge-kpi-pago'),
            kpi('Costo del mes', soles(pagos.costo_empresa), 'Sueldos + EsSalud', ''),
            kpi('Vacaciones pendientes', dias(vac) + ' días', acum.length ? `${acum.length} con días vencidos` : 'Del personal activo', acum.length ? 'ge-kpi-mal' : '')
        ].join('');
        pintarPagos();
        pintarPersonal();
        pintarBeneficios();
    }

    // ============================================================
    // PAGOS DEL MES
    // ============================================================
    function pintarPagos() {
        $('#plaTitPagos').textContent = `Pagos de ${pagos.nombre_periodo} · ${pagos.empresa.codigo}`;
        if (!pagos.filas.length) {
            $('#plaPagos').innerHTML = gente.personal.length
                ? '<div class="inv-vacio">Nadie trabajaba en este mes.</div>'
                : `<div class="inv-vacio">Todavía no hay personal en ${esc(empCodigo())}. Usa <b>+ Agregar persona</b> con su sueldo real.</div>`;
            $('#plaSunat').innerHTML = '';
            return;
        }
        $('#plaPagos').innerHTML = `<table class="inv-table ge-tabla"><thead><tr><th>Persona</th><th>DNI</th><th>Tipo</th><th>Concepto</th>
            <th>Bruto (S/)</th><th>Descuento (S/)</th><th>Neto a pagar (S/)</th><th>EsSalud empresa (S/)</th><th>Banco y N° de cuenta</th>
            <th>Estado</th><th>Acciones</th></tr></thead><tbody>
            ${pagos.filas.map((f, i) => `<tr class="${f.pagado ? 'ge-fila-ok' : 'ge-fila-pend'}">
                <td><b>${esc(f.nombres)}</b>${f.cargo ? `<span class="ge-sub">${esc(f.cargo)}</span>` : ''}</td>
                <td class="ge-nw">${esc(f.documento || '')}</td><td>${esc(f.tipo)}</td>
                <td><b>${esc(f.concepto)}</b><span class="ge-sub">${esc(f.detalle)}</span></td>
                <td class="ge-nw">${soles(f.bruto)}</td><td class="ge-nw">${f.descuento ? soles(f.descuento) : '<span class="ge-cero">—</span>'}</td>
                <td class="ge-nw"><b>${soles(f.neto)}</b></td><td class="ge-nw">${f.essalud ? soles(f.essalud) : '<span class="ge-cero">—</span>'}</td>
                <td>${f.banco || f.cuenta ? `${esc(f.banco || '')}<span class="ge-sub">${esc(f.cuenta || '')}</span>` : '<span class="ge-sin">Falta la cuenta</span>'}</td>
                <td>${f.pagado ? `<span class="ge-estado verde">✔ Pagado</span><span class="ge-sub">N° operación ${esc(f.numero_operacion)} · ${fecha(f.fecha_pago)}</span><span class="ge-sub">${esc(f.marcado_por || '')} · ${fecha(f.marcado_en)}</span>`
                    : '<span class="ge-estado rojo">⏳ Por pagar</span>'}</td>
                <td>${f.pagado ? `<button type="button" class="ge-btn" data-desmarcar="${i}">Desmarcar</button>`
                    : `<button type="button" class="ge-btn verde" data-marcar="${i}">Marcar pagado</button>`}</td></tr>`).join('')}
            </tbody><tfoot><tr><td colspan="4"><b>Total</b></td><td class="ge-nw"><b>${soles(pagos.totales.bruto)}</b></td>
                <td class="ge-nw"><b>${soles(pagos.totales.descuento)}</b></td><td class="ge-nw"><b>${soles(pagos.totales.neto)}</b></td>
                <td class="ge-nw"><b>${soles(pagos.totales.essalud)}</b></td><td colspan="3"></td></tr></tfoot></table>`;
        const s = pagos.enviado_sunat;
        $('#plaSunat').innerHTML = s
            ? `<div class="ge-sunat">✔ Enviado a <a href="/sunat?tab=pagos">SUNAT ▸ Pagos del mes</a>: base EsSalud ${soles(s.base_essalud)} · base ONP ${soles(s.base_onp)} · AFP ${soles(s.afp)} · sueldos ${soles(s.remuneraciones)} · renta 4.ª ${soles(s.renta_4ta)}</div>`
            : (pagos.mes_reciente ? '' : '<div class="ge-sunat">Este mes ya pasó: no se envía a SUNAT (lo declaró el contador).</div>');
    }

    // ============================================================
    // PERSONAL
    // ============================================================
    function pintarPersonal() {
        const lista = gente.personal;
        if (!lista.length) {
            $('#plaPersonal').innerHTML = `<div class="inv-vacio">Todavía no hay personal en ${esc(empCodigo())}. Usa <b>+ Agregar persona</b>.</div>`;
            return;
        }
        $('#plaPersonal').innerHTML = `<table class="inv-table ge-tabla"><thead><tr><th>Persona</th><th>DNI</th><th>Tipo</th><th>Ingreso</th>
            <th>Sueldo o subvención (S/)</th><th>Pensión</th><th>Banco y N° de cuenta</th><th>Vacaciones</th><th>Estado</th>
            <th>Creado / modificado</th><th>Acciones</th></tr></thead><tbody>
            ${lista.map(p => {
                const v = p.vacaciones;
                const vac = !v ? '<span class="ge-cero">No aplica</span>'
                    : `<span class="ge-estado ${v.acumulado ? 'rojo' : v.pendientes > 0 ? 'amarillo' : 'verde'}">${dias(v.pendientes)} días pendientes</span>
                       <span class="ge-sub">${dias(v.ganados)} ganados · ${v.tomados} tomados · ${v.por_anio} por año</span>`;
                return `<tr class="${p.activo ? '' : 'ge-fila-cesado'}">
                <td><b>${esc(p.nombres)}</b>${p.cargo ? `<span class="ge-sub">${esc(p.cargo)}</span>` : ''}</td>
                <td class="ge-nw">${esc(p.documento || '')}</td><td>${esc(p.tipo)}${p.jornada_parcial ? '<span class="ge-sub">Jornada parcial</span>' : ''}</td>
                <td class="ge-nw">${fecha(p.fecha_ingreso)}</td>
                <td class="ge-nw"><b>${soles(p.sueldo)}</b>${p.asignacion_familiar ? '<span class="ge-sub">+ asignación familiar</span>' : ''}</td>
                <td>${p.tipo === 'Planilla' ? esc(p.pension) + (p.pension === 'AFP' ? ` ${num(p.afp_porcentaje)}%` : '') : '<span class="ge-cero">—</span>'}</td>
                <td>${p.banco || p.cuenta ? `${esc(p.banco || '')}<span class="ge-sub">${esc(p.cuenta || '')}</span>` : '<span class="ge-sin">Falta</span>'}</td>
                <td>${vac}</td>
                <td>${p.activo ? '<span class="ge-estado verde">Activo</span>' : `<span class="ge-estado gris">Cesó ${fecha(p.fecha_cese)}</span>`}</td>
                <td><span class="ge-sub">${esc(p.creado_por || '')} · ${fecha(p.creado_en)}</span><span class="ge-sub">${esc(p.actualizado_por || '')} · ${fecha(p.actualizado_en)}</span></td>
                <td><button type="button" class="ge-btn" data-editar="${p.id}">Editar</button>${v && p.activo ? `<button type="button" class="ge-btn amarillo" data-vacaciones="${p.id}">Vacaciones</button>` : ''}</td></tr>`;
            }).join('')}
            </tbody></table>`;
    }

    // ============================================================
    // CTS Y GRATIFICACIONES
    // ============================================================
    function pintarBeneficios() {
        const b = gente.beneficios;
        $('#plaBeneficios').innerHTML = `<div class="ge-benef">${b.map(x => {
            let cuerpo;
            if (!x.aplica) cuerpo = '<div class="inv-vacio">En microempresa no corresponde.</div>';
            else if (!x.personas.length) cuerpo = '<div class="inv-vacio">Nadie en planilla con meses completos para este pago.</div>';
            else cuerpo = `<table class="inv-table ge-tabla"><thead><tr><th>Persona</th><th>Meses</th><th>Monto (S/)</th></tr></thead><tbody>
                ${x.personas.map(p => `<tr><td><b>${esc(p.nombres)}</b><span class="ge-sub">${esc(p.detalle)}</span></td><td>${p.meses}</td><td class="ge-nw"><b>${soles(p.monto)}</b></td></tr>`).join('')}
                </tbody><tfoot><tr><td colspan="2"><b>Total</b></td><td class="ge-nw"><b>${soles(x.total)}</b></td></tr></tfoot></table>`;
            const prac = x.practicantes.length ? `<div class="inv-head"><div class="inv-title">🎓 Media subvención de practicantes</div></div>
                <table class="inv-table ge-tabla"><thead><tr><th>Practicante</th><th>Mes</th><th>Monto (S/)</th></tr></thead><tbody>
                ${x.practicantes.map(p => `<tr><td><b>${esc(p.nombres)}</b></td><td>${esc(p.mes)}</td><td class="ge-nw"><b>${soles(p.monto)}</b></td></tr>`).join('')}</tbody></table>` : '';
            return `<div class="inv-panel"><div class="inv-head"><div class="inv-title">${x.tipo === 'CTS' ? '🏦' : '🎁'} ${esc(x.nombre)}</div>
                <small class="ge-chip">Se paga hasta el ${fecha(x.vence)}</small></div>${cuerpo}${prac}</div>`;
        }).join('')}</div>
        <details class="ge-ayuda"><summary>¿Cómo se calcula?</summary><ul>
            <li><b>Gratificación</b> (julio y diciembre): un sueldo por semestre completo, más 9% de bonificación. En pequeña empresa, la mitad.</li>
            <li><b>CTS</b> (mayo y noviembre): medio sueldo por semestre (sueldo + 1/6 de la gratificación). En pequeña empresa, la mitad. Se deposita en su cuenta CTS.</li>
            <li><b>Practicantes</b>: media subvención cada 6 meses. No tienen CTS ni gratificación.</li>
            <li>Solo cuentan los meses completos. Es un estimado: el monto final lo confirma el contador.</li>
        </ul></details>`;
    }

    // ============================================================
    // VENTANA
    // ============================================================
    function abrirModal(titulo, detalle, campos, okTexto, fn) {
        $('#plaModalTit').textContent = titulo;
        $('#plaModalDet').innerHTML = detalle || '';
        $('#plaModalCampos').innerHTML = campos;
        $('#plaModalOk').textContent = okTexto || 'Guardar';
        alGuardar = fn;
        $('#plaModal').hidden = false;
        const primero = $('#plaModalCampos input, #plaModalCampos select');
        if (primero) primero.focus();
        ajustarForm();
    }
    const cerrarModal = () => { $('#plaModal').hidden = true; alGuardar = null; };
    const opciones = (lista, actual) => lista.map(x => `<option value="${esc(x)}" ${x === actual ? 'selected' : ''}>${esc(x)}</option>`).join('');

    function formPersona(p) {
        p = p || { tipo: 'Planilla', pension: 'ONP' };
        return `<label>Nombre completo<input name="nombres" required maxlength="150" value="${esc(p.nombres || '')}"></label>
            <label>DNI<input name="documento" maxlength="12" inputmode="numeric" value="${esc(p.documento || '')}"></label>
            <label>Tipo<select name="tipo" required>${opciones(OPC.tipos, p.tipo)}</select></label>
            <label>Cargo <small>(opcional)</small><input name="cargo" maxlength="100" value="${esc(p.cargo || '')}" placeholder="Ej.: Logística"></label>
            <label>Fecha de ingreso<input type="date" name="fecha_ingreso" required value="${esc(p.fecha_ingreso || '')}"></label>
            <label>Fecha de cese <small>(solo si ya no trabaja)</small><input type="date" name="fecha_cese" value="${esc(p.fecha_cese || '')}"></label>
            <label><span data-etiqueta-sueldo>Sueldo mensual (S/)</span><input type="number" name="sueldo" required min="0.01" step="0.01" value="${p.sueldo ?? ''}"></label>
            <label data-solo="Planilla">Pensión<select name="pension">${opciones(OPC.pensiones, p.pension)}</select></label>
            <label data-solo="AFP">% total de la AFP <small>(aporte + seguro + comisión)</small><input type="number" name="afp_porcentaje" min="0.01" max="19.99" step="0.01" value="${p.afp_porcentaje ?? ''}" placeholder="Ej.: 11.37"></label>
            <label>Banco<input name="banco" data-lista="bancos" value="${esc(p.banco || '')}"></label>
            <label>N° de cuenta<input name="cuenta" maxlength="60" value="${esc(p.cuenta || '')}"></label>
            <label class="ge-check" data-solo="Planilla"><input type="checkbox" name="asignacion_familiar" ${p.asignacion_familiar ? 'checked' : ''}> Asignación familiar (tiene hijos menores)</label>
            <label class="ge-check" data-solo="Jornada"><input type="checkbox" name="jornada_parcial" ${p.jornada_parcial ? 'checked' : ''}> Jornada parcial (menos de 4 horas diarias)</label>
            <label>Observaciones <small>(opcional)</small><input name="observaciones" maxlength="500" value="${esc(p.observaciones || '')}"></label>`;
    }
    function ajustarForm() {
        const f = $('#plaModalForm');
        const tipo = f.tipo ? f.tipo.value : null;
        if (!tipo) return;
        const pension = f.pension ? f.pension.value : '';
        $$('[data-solo]', f).forEach(el => {
            const s = el.dataset.solo;
            el.hidden = s === 'Planilla' ? tipo !== 'Planilla' : s === 'AFP' ? (tipo !== 'Planilla' || pension !== 'AFP') : tipo === 'Recibo por honorarios';
        });
        $('[data-etiqueta-sueldo]', f).textContent = tipo === 'Practicante' ? 'Subvención mensual (S/)' : tipo === 'Planilla' ? 'Sueldo mensual (S/)' : 'Monto mensual del recibo (S/)';
    }
    function leerForm() {
        const f = $('#plaModalForm');
        const d = { empresa_id: empresa() };
        $$('input, select', f).forEach(el => {
            if (!el.name) return;
            d[el.name] = el.type === 'checkbox' ? el.checked : el.value;
        });
        return d;
    }

    async function enviar(url, metodo, body) {
        const j = await api(url, { method: metodo, body: Object.assign({ empresa_id: empresa() }, body) });
        aviso(j.message || 'Listo', 'success');
        cerrarModal();
        await cargar();
    }

    function abrirPersona(p) {
        const det = p ? `Creado por ${esc(p.creado_por || '')} el ${fecha(p.creado_en)} · modificado por ${esc(p.actualizado_por || '')} el ${fecha(p.actualizado_en)}` +
            ((p.historial || []).length ? `<details><summary>Historial de cambios</summary><ul class="ge-vac-lista">${p.historial.slice().reverse().map(h => `<li>${fecha(h.fecha)} · ${esc(h.usuario)}: ${esc((h.cambios || []).join('; ') || 'sin cambios')}</li>`).join('')}</ul></details>` : '')
            : `Empresa: <b>${esc(empCodigo())}</b>. Escribe el sueldo real: el ERP no inventa sueldos.`;
        abrirModal(p ? `Editar a ${p.nombres}` : 'Agregar persona', det, formPersona(p), 'Guardar', async () => {
            const d = leerForm();
            if (p) await enviar('/planilla/api/personal/' + p.id, 'PUT', d);
            else await enviar('/planilla/api/personal', 'POST', d);
        });
    }

    function abrirVacaciones(p) {
        const v = p.vacaciones;
        const regs = v.registros.length ? `<ul class="ge-vac-lista">${v.registros.map(r => `<li>${fecha(r.desde)} al ${fecha(r.hasta)} · ${r.dias} días${r.nota ? ' · ' + esc(r.nota) : ''}</li>`).join('')}</ul>` : '';
        abrirModal(`Vacaciones de ${p.nombres}`, `Le quedan <b>${dias(v.pendientes)} días</b> (${dias(v.ganados)} ganados, ${v.tomados} tomados).${regs}`,
            `<label>Desde<input type="date" name="desde" required></label><label>Hasta<input type="date" name="hasta" required></label>
             <label>Nota <small>(opcional)</small><input name="nota" maxlength="300"></label>`, 'Registrar',
            async () => { const d = leerForm(); await enviar(`/planilla/api/personal/${p.id}/vacaciones`, 'POST', d); });
    }

    function abrirMarcar(f) {
        abrirModal('Marcar pagado', `${esc(f.nombres)} · ${esc(f.concepto)} · <b>${soles(f.neto)}</b>`,
            `<label>N° de operación del banco<input name="numero_operacion" required maxlength="80"></label>
             <label>Fecha de pago<input type="date" name="fecha_pago" required value="${new Date().toLocaleDateString('en-CA', { timeZone: 'America/Lima' })}"></label>
             <label>Monto pagado (S/)<input type="number" name="monto" step="0.01" min="0.01" required value="${num(f.neto).toFixed(2)}"></label>`, 'Marcar pagado',
            async () => { const d = leerForm(); await enviar('/planilla/api/pagos/marcar', 'POST', Object.assign(d, { personal_id: f.personal_id, concepto: f.concepto, periodo: pagos.periodo })); });
    }

    function abrirDesmarcar(f) {
        abrirModal('Desmarcar pago', `${esc(f.nombres)} · ${esc(f.concepto)} · N° operación ${esc(f.numero_operacion)}`,
            '<label>¿Por qué se desmarca?<input name="motivo" required maxlength="300" placeholder="Ej.: el banco rechazó la transferencia"></label>', 'Desmarcar',
            async () => { const d = leerForm(); await enviar('/planilla/api/pagos/desmarcar', 'POST', Object.assign(d, { personal_id: f.personal_id, concepto: f.concepto, periodo: pagos.periodo })); });
    }

    function abrirRegimen() {
        const c = gente.config;
        abrirModal(`Régimen laboral de ${gente.empresa.codigo}`, 'Pregúntale al contador si la empresa está en el REMYPE (pequeña o microempresa).',
            `<label>Régimen<select name="regimen_laboral">${Object.entries(OPC.regimenes).map(([k, v]) => `<option value="${k}" ${k === c.regimen_laboral ? 'selected' : ''}>${esc(v)}</option>`).join('')}</select></label>
             <label>Sueldo mínimo (S/)<input type="number" name="rmv" step="0.01" min="900" value="${c.rmv}"></label>`, 'Guardar',
            async () => { const d = leerForm(); await enviar('/planilla/api/config', 'POST', d); });
    }

    document.addEventListener('DOMContentLoaded', () => {
        APP = $('#plaApp');
        if (!APP) return;
        $$('#plaTabs .tab-btn').forEach(b => b.addEventListener('click', () => irA(b.dataset.tab)));
        irA(new URLSearchParams(location.search).get('tab') || 'pagos');
        $('#plaMes').addEventListener('change', cargar);
        $('#plaEmpresa').addEventListener('change', () => { $('#plaMes').value = ''; cargar(); });
        $('#plaAgregar').addEventListener('click', () => abrirPersona(null));
        $('#plaModalCancelar').addEventListener('click', cerrarModal);
        $('#plaModalForm').addEventListener('change', ajustarForm);
        $('#plaModalForm').addEventListener('submit', async ev => {
            ev.preventDefault();
            if (!alGuardar) return;
            const ok = $('#plaModalOk');
            ok.disabled = true;
            try { await alGuardar(); } catch (e) { aviso(e.message, 'error'); } finally { ok.disabled = false; }
        });
        APP.addEventListener('click', ev => {
            if (ev.target.id === 'plaCambiarRegimen') { ev.preventDefault(); return abrirRegimen(); }
            const b = ev.target.closest('button');
            if (!b) return;
            if (b.dataset.marcar) abrirMarcar(pagos.filas[+b.dataset.marcar]);
            else if (b.dataset.desmarcar) abrirDesmarcar(pagos.filas[+b.dataset.desmarcar]);
            else if (b.dataset.editar) abrirPersona(gente.personal.find(p => String(p.id) === b.dataset.editar));
            else if (b.dataset.vacaciones) abrirVacaciones(gente.personal.find(p => String(p.id) === b.dataset.vacaciones));
        });
        cargar();
    });
})();
