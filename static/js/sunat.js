// static/js/sunat.js - Módulo SUNAT e impuestos (pedido de Erika 21/10/2026)
(function () {
    'use strict';
    const $ = (s, r = document) => r.querySelector(s);
    const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
    const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const num = v => Number(v || 0);
    const soles = v => 'S/ ' + num(v).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const r2 = v => Math.round(num(v) * 100) / 100;
    const TABS = ['resumen', 'plan', 'contador', 'pagos', 'completar'];
    const ADMIN = $('#sunApp')?.dataset.admin === 'true';
    let tab = 'resumen';
    let datos = null;
    let vistaImp = null;

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
        if (o.body && !(o.body instanceof FormData)) o.headers['Content-Type'] = 'application/json';
        const r = await fetch(url, o);
        let j = {};
        try { j = await r.json(); } catch (e) { /* no JSON */ }
        if (!r.ok || j.success === false) throw new Error(j.error || `Error ${r.status}`);
        return j;
    }

    const empresa = () => $('#sunEmpresa').value;
    const periodo = () => $('#sunPeriodo').value;
    const qs = extra => new URLSearchParams(Object.assign({ empresa_id: empresa(), periodo: periodo() }, extra || {})).toString();

    // ============================================================
    // PESTAÑAS
    // ============================================================
    function irA(t) {
        tab = TABS.includes(t) ? t : 'resumen';
        $$('#sunTabs .tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
        TABS.forEach(x => $('#sun-sec-' + x).classList.toggle('active', x === tab));
        try { history.replaceState(null, '', '/sunat?tab=' + tab); } catch (e) { /* nada */ }
        if (window.abrirMenuModulo) window.abrirMenuModulo();
        cargar();
    }

    function cargar() {
        if (tab === 'pagos') return cargarPagos();
        if (tab === 'completar') return cargarImportados();
        return cargarResumen();
    }

    // ============================================================
    // RESUMEN
    // ============================================================
    async function cargarResumen() {
        $('#resCargando').hidden = false;
        try {
            const j = await api('/sunat/api/resumen?' + qs());
            datos = j.data;
            pintarResumen();
            pintarPlan();
            pintarContador();
        } catch (e) {
            $('#resCargando').textContent = '⚠ ' + e.message;
            $('#planLista').innerHTML = `<div class="inv-vacio">⚠ ${esc(e.message)}</div>`;
            return;
        }
        $('#resCargando').hidden = true;
        $('#resContenido').hidden = false;
    }

    // Mismo orden que el PDT 621 (igual que routes/sunat.py: liquidar)
    function liquidar(deb, cred, m) {
        const sf = Math.abs(num(m.saldo_favor_anterior));
        const tributo = deb - cred - sf;
        const perc = Math.abs(num(m.percepciones_mes)) + Math.abs(num(m.saldo_percepciones_anterior));
        const ret = Math.abs(num(m.retenciones_mes)) + Math.abs(num(m.saldo_retenciones_anterior));
        if (tributo <= 0) return { tributo, pagar: 0, ret, perc, retUsada: 0, saldoRet: ret, saldoFavor: -tributo };
        const pu = Math.min(perc, tributo), ru = Math.min(ret, tributo - pu);
        return { tributo, pagar: tributo - pu - ru, ret, perc, retUsada: ru, saldoRet: ret - ru, saldoFavor: 0 };
    }

    function proyeccionActual() {
        const p = datos.proyeccion.partes;
        let dv = 0, dc = 0, bv = 0, bc = 0;
        p.forEach((x, i) => {
            const marcado = $(`#proy_${i}`) ? $(`#proy_${i}`).checked : x.incluir;
            if (!marcado) return;
            if (x.tipo === 'venta') { dv += num(x.igv); bv += num(x.base); } else { dc += num(x.igv); bc += num(x.base); }
        });
        const deb = num(datos.sv.igv) + dv, cred = num(datos.sc.igv) + dc;
        const liq = liquidar(deb, cred, datos.manual_calculo);
        const renta = Math.round(Math.max(num(datos.sv.base) + bv, 0) * num(datos.renta.tasa) / 100);
        return { deb, cred, liq, renta, ventasBase: num(datos.sv.base) + bv, comprasBase: num(datos.sc.base) + bc };
    }

    function kpi(titulo, valor, pie, clase) {
        return `<div class="inv-kpi ${clase || ''}"><small>${titulo}</small><b>${valor}</b><span>${pie || ''}</span></div>`;
    }

    const CORTO = { guias: 'Guías entregadas sin factura', despachos: 'Despachos por salir', oc: 'OC sin factura del proveedor',
                    pc: 'Pedidos (PC) por comprar', ventas_extra: 'Otras ventas (a mano)', compras_extra: 'Compra para stock (a mano)' };

    function pintarResumen() {
        const d = datos, sv = d.sv, sc = d.sc, liq = d.liq;
        const pr = proyeccionActual();
        const actual = d.es_mes_actual;
        const sinArchivo = (sv.n_archivo + sv.n_ambos === 0) || (sc.n_archivo + sc.n_ambos === 0);
        const av = $('#resAvisoDatos');
        av.hidden = !sinArchivo;
        av.innerHTML = sinArchivo ? `🔴 Faltan facturas en el ERP (siguen en Excel). <button class="btn-link" data-ir="completar">Subirlas →</button>` : '';
        const otrosPlame = num(d.plame.essalud) + num(d.plame.onp) + num(d.plame.renta_5ta) + num(d.plame.renta_4ta);
        const totalProy = pr.liq.pagar + pr.renta + otrosPlame;
        const igvFin = actual ? pr.liq.pagar : liq.igv_pagar;
        const notas = [sv.n_nc + sc.n_nc ? `${sv.n_nc + sc.n_nc} NC` : '', sv.n_nd + sc.n_nd ? `${sv.n_nd + sc.n_nd} ND` : ''].filter(Boolean).join(' · ');
        $('#resKpis').innerHTML = [
            kpi('Ventas', sv.n_facturas + sv.n_boletas, soles(sv.base) + (notas ? ' · ' + notas : '')),
            kpi('Compras', sc.n_facturas, soles(sc.base)),
            kpi('IGV hoy', soles(liq.igv_pagar), fecha(d.corte), liq.igv_pagar > 0 ? 'inv-kpi-danger' : 'sun-kpi-ok'),
            kpi(actual ? 'IGV al 31' : 'IGV del mes', soles(igvFin), actual ? 'Proyección' : 'Mes cerrado', igvFin > 0 ? 'inv-kpi-danger' : 'sun-kpi-ok'),
            kpi('Total SUNAT', soles(actual ? totalProy : d.total_sunat), d.vencimiento ? 'Vence ' + fecha(d.vencimiento) : '', 'inv-kpi-warn')
        ].join('');

        // Estado de cuenta del IGV: de arriba hacia abajo, cada línea suma o resta (orden del PDT 621)
        const m = d.manual_calculo, vo = d.voucher || {};
        const neg = v => num(v) < 0 ? `−${soles(-num(v))}` : soles(v);
        const sec = (txt) => `<tr class="sun-e-sec"><td colspan="${actual ? 3 : 2}" style="text-align:left">${txt}</td></tr>`;
        const ln = (txt, a, b, o) => {
            o = o || {};
            const nota = o.nota ? `<span class="sun-e-nota">${o.nota}</span>` : '';
            const vac = o.vacio ? ' sun-e-vacio' : '';
            return `<tr class="${o.clase || 'sun-e-linea'}${vac}"><td class="sun-e-txt">${txt}${nota}</td><td class="sun-e-num">${a === null ? '' : neg(a)}</td>${actual ? `<td class="sun-e-num">${b === null ? '' : neg(b)}</td>` : ''}</tr>`;
        };
        // Ventas: facturas y boletas, menos notas de crédito, más notas de débito
        const vFact = num(sv.igv) - num(sv.nc_igv) - num(sv.nd_igv), vFact31 = pr.deb - num(sv.nc_igv) - num(sv.nd_igv);
        const cFact = num(sc.igv) - num(sc.nc_igv) - num(sc.nd_igv), cFact31 = pr.cred - num(sc.nc_igv) - num(sc.nd_igv);
        const baseV = `Base imponible: ${soles(sv.base)}${actual ? ` hoy · ${soles(pr.ventasBase)} al 31` : ''}`;
        const baseC = `Base imponible: ${soles(sc.base)}${actual ? ` hoy · ${soles(pr.comprasBase)} al 31` : ''}`;
        const sf = num(liq.saldo_favor_anterior);
        const percU = num(liq.percepciones_usadas), percU31 = Math.min(pr.liq.perc, Math.max(pr.liq.tributo, 0));
        const retDisp = num(m.retenciones_mes) + num(m.saldo_retenciones_anterior);
        const pagar = num(liq.igv_pagar), pagar31 = pr.liq.pagar;
        const clavePagar = (actual ? pagar31 : pagar) > 0 ? 'sun-e-clave' : 'sun-e-clave cero';
        $('#resTablaIgv').innerHTML = `<thead><tr><th class="sun-e-txt">Concepto</th><th class="sun-e-num">Hoy ${fecha(d.corte).slice(0, 5)}</th>${actual ? '<th class="sun-e-num">Al 31</th>' : ''}</tr></thead><tbody>
            ${sec('1 · IGV de tus ventas')}
            ${ln('IGV de facturas y boletas emitidas', vFact, vFact31, { nota: baseV })}
            ${ln(`(−) Notas de crédito emitidas · ${sv.n_nc}`, sv.nc_igv, sv.nc_igv, { vacio: !sv.n_nc, nota: 'Devoluciones o descuentos a clientes: bajan tu IGV' })}
            ${ln(`(+) Notas de débito emitidas · ${sv.n_nd}`, sv.nd_igv, sv.nd_igv, { vacio: !sv.n_nd, nota: 'Cobros extra a clientes: suben tu IGV' })}
            ${ln('= IGV de ventas', sv.igv, pr.deb, { clase: 'sun-e-sub', nota: 'Casilla 101 · el IGV que cobraste a tus clientes' })}
            ${sec('2 · IGV de tus compras (crédito fiscal)')}
            ${ln('(−) IGV de facturas de compra', -cFact, -cFact31, { nota: baseC })}
            ${ln(`(+) Notas de crédito recibidas · ${sc.n_nc}`, -num(sc.nc_igv), -num(sc.nc_igv), { vacio: !sc.n_nc, nota: 'Un proveedor te descontó: baja tu crédito' })}
            ${ln(`(−) Notas de débito recibidas · ${sc.n_nd}`, -num(sc.nd_igv), -num(sc.nd_igv), { vacio: !sc.n_nd })}
            ${ln('= IGV de compras', -sc.igv, -pr.cred, { clase: 'sun-e-sub', nota: 'Casilla 108 · el IGV que pagaste a tus proveedores: se descuenta' })}
            ${sec('3 · Cálculo del IGV del mes')}
            ${ln('Impuesto resultante (ventas − compras)', liq.resultante, pr.deb - pr.cred, { nota: 'Casilla 140' })}
            ${ln('(−) Saldo a favor del mes anterior', -sf, -sf, { vacio: !sf, nota: 'Casilla 145 · si el mes pasado salió a favor' })}
            ${ln('= IGV del mes, sin retenciones', liq.tributo, pr.liq.tributo, { clase: 'sun-e-sub sun-e-184', nota: 'Casilla 184 · lo que pagarías si no tuvieras retenciones' })}
            ${num(liq.percepciones) || pr.liq.perc ? ln('(−) Percepciones', -percU, -percU31) : ''}
            ${ln('(−) Retenciones que se usan', -num(liq.retenciones_usadas), -pr.liq.retUsada, { nota: `Tienes ${soles(retDisp)}: ${soles(m.retenciones_mes)} de este mes + ${soles(m.saldo_retenciones_anterior)} de meses anteriores` })}
            <tr class="${clavePagar}"><td class="sun-e-txt">IGV A PAGAR, DESPUÉS DE RETENCIONES</td><td class="sun-e-num">${soles(pagar)}</td>${actual ? `<td class="sun-e-num">${soles(pagar31)}</td>` : ''}</tr>
            ${ln('Retenciones que quedan para el próximo mes', liq.saldo_retenciones_siguiente, pr.liq.saldoRet, { clase: 'sun-e-pie', vacio: !num(liq.saldo_retenciones_siguiente) && !pr.liq.saldoRet })}
            ${num(liq.saldo_favor_siguiente) || pr.liq.saldoFavor ? ln('Saldo a favor de IGV para el próximo mes', liq.saldo_favor_siguiente, pr.liq.saldoFavor, { clase: 'sun-e-pie' }) : ''}
        </tbody>`;

        // Proyección
        $('#resPanelProy').hidden = !actual;
        if (actual) {
            $('#resProyeccion').innerHTML = `<table class="inv-table"><thead><tr><th>Sumar</th><th>Qué falta</th><th>N°</th><th>IGV (S/)</th></tr></thead><tbody>
                ${d.proyeccion.partes.map((p, i) => `<tr class="${p.tipo === 'venta' ? 'sun-fila-debe' : 'sun-fila-haber'}">
                    <td><input type="checkbox" id="proy_${i}" ${p.incluir ? 'checked' : ''}></td>
                    <td class="left" title="${esc(p.texto)}">${p.tipo === 'venta' ? '⬆' : '⬇'} ${esc(CORTO[p.clave] || p.texto)}</td>
                    <td>${p.n || ''}</td><td class="num">${soles(p.igv)}</td></tr>`).join('')}
            </tbody></table>`;
            $$('#resProyeccion input[type=checkbox]').forEach(c => c.addEventListener('change', pintarResumen));
        }

        // Total a SUNAT y caja necesaria
        const reg = d.config;
        $('#resTituloOtros').innerHTML = `Total a pagar a SUNAT <small class="sun-chip">vence ${d.vencimiento ? fecha(d.vencimiento) : '—'}</small>`;
        const rentaHoy = num(d.renta.monto), renta31 = actual ? pr.renta : rentaHoy;
        const plame = num(d.plame.essalud) + num(d.plame.onp) + num(d.plame.renta_5ta) + num(d.plame.renta_4ta);
        const totHoy = pagar + rentaHoy + plame, tot31 = (actual ? pagar31 : pagar) + renta31 + plame;
        const afp = num(d.plame.afp);
        const est = k => vo[k] && vo[k].estado === 'Pagado' ? `<span class="sun-e-ok">✔ Pagado ${soles(vo[k].monto)}</span>` : '';
        const t = (txt, a, b, o) => ln(txt + (o && o.est ? ' ' + o.est : ''), a, b, o);
        $('#resTablaOtros').innerHTML = `<thead><tr><th class="sun-e-txt">Concepto</th><th class="sun-e-num">Hoy</th>${actual ? '<th class="sun-e-num">Al 31</th>' : ''}</tr></thead><tbody>
            ${t('IGV a pagar', pagar, actual ? pagar31 : null, { est: est('IGV') })}
            ${t(`Renta mensual (${num(d.renta.tasa)}% de ventas)`, rentaHoy, actual ? renta31 : null, { est: est('RENTA_3RA'), nota: `${esc(reg.regimen === 'RMT' ? 'Régimen MYPE' : reg.regimen_nombre)}${reg.configurado ? '' : ' · sin confirmar con el contador'}` })}
            ${ln('EsSalud (9% de sueldos)', d.plame.essalud, actual ? d.plame.essalud : null)}
            ${ln('ONP (13%)', d.plame.onp, actual ? d.plame.onp : null)}
            ${num(d.plame.renta_5ta) ? ln('Renta de 5.ª', d.plame.renta_5ta, actual ? d.plame.renta_5ta : null) : ''}
            ${num(d.plame.renta_4ta) ? ln('Renta de 4.ª', d.plame.renta_4ta, actual ? d.plame.renta_4ta : null) : ''}
            ${ln('= Total a SUNAT', totHoy, actual ? tot31 : null, { clase: 'sun-e-sub' })}
            ${afp ? ln('(+) AFP (se paga en AFPnet)', afp, actual ? afp : null) : ''}
            <tr class="sun-e-caja"><td class="sun-e-txt">Caja que necesitas${d.vencimiento ? ' al ' + fecha(d.vencimiento) : ''}</td><td class="sun-e-num">${soles(totHoy + afp)}</td>${actual ? `<td class="sun-e-num">${soles(tot31 + afp)}</td>` : ''}</tr>
        </tbody>` + (reg.regimen === 'RMT' && num(d.renta.acumulado_anio) > num(d.renta.tope_rmt) ? `<div class="sun-obs">Las ventas del año pasan 300 UIT: la renta sube. Habla con el contador.</div>` : '');

        pintarFormManual();
    }

    const CAMPOS = [
        ['manual', 'saldo_retenciones_anterior', 'Retenciones del mes anterior', 'Sale solo del mes anterior. Escríbelo solo para corregirlo'],
        ['manual', 'saldo_favor_anterior', 'Saldo a favor anterior', 'Saldo a favor de IGV del mes anterior'],
        ['manual', 'percepciones_mes', 'Percepciones del mes', 'Casi nunca hay'],
        ['manual', 'saldo_percepciones_anterior', 'Percepciones anteriores', 'Saldo de percepciones del mes anterior'],
        ['manual', 'detracciones_saldo_bn', 'Detracciones (Banco de la Nación)', 'Saldo de la cuenta de detracciones: sirve para pagar impuestos'],
        ['manual', 'tipo_cambio', 'Tipo de cambio', 'Solo si hay facturas en dólares'],
        ['manual', 'ventas_extra', 'Otras ventas del mes (base)', 'Para la proyección al 31'],
        ['manual', 'compras_extra', 'Compra para stock (base)', 'Para la proyección al 31'],
        ['planilla', 'base_essalud', 'Sueldos (base EsSalud)', 'Total de remuneraciones del mes'],
        ['planilla', 'base_onp', 'Sueldos de trabajadores ONP', 'Remuneraciones de quienes están en ONP'],
        ['planilla', 'afp', 'AFP a pagar', 'Lo dice AFPnet'],
        ['planilla', 'remuneraciones', 'Sueldos netos', 'Para el checklist de pagos'],
        ['planilla', 'renta_5ta', 'Renta 5.ª', 'Si aplica'],
        ['planilla', 'renta_4ta', 'Renta 4.ª', 'Si aplica']
    ];

    // Lo único que se escribe a mano: las retenciones del mes (todo lo demás sale de Ventas y Compras)
    function pintarFormRet() {
        const d = datos, v = d.manual.retenciones_mes;
        const tiene = v !== undefined && v !== null && v !== '';
        $('#resFormRet').innerHTML = `<label for="retMes">✍ Retenciones del mes <small class="sun-chip">lo único que escribes</small></label>
            <div class="sun-ret-fila"><input id="retMes" type="text" inputmode="decimal" value="${tiene ? esc(v) : ''}" placeholder="Sugerido ${soles(d.retenciones_sugeridas)}">
            <button type="submit" class="btn btn-primary">Guardar</button></div>
            <span class="sun-ret-ayuda">${tiene ? '✔ Guardado' : `Míralas en SUNAT ▸ Comprobantes de retención. El ERP sugiere ${soles(d.retenciones_sugeridas)} (${d.retenciones_sugeridas_n} facturas cobradas con retención).`}</span>`;
    }

    async function guardarRet(ev) {
        ev.preventDefault();
        try {
            const j = await api('/sunat/api/periodo', { method: 'POST', body: JSON.stringify({ empresa_id: empresa(), periodo: periodo(),
                manual: { retenciones_mes: $('#retMes').value.trim() }, planilla: {} }) });
            aviso(j.mensaje, 'success');
            cargarResumen();
        } catch (e) { aviso(e.message, 'error'); }
    }

    function pintarFormManual() {
        const d = datos;
        pintarFormRet();
        const sug = { retenciones_mes: d.retenciones_sugeridas };
        const calc = d.manual_calculo || {};
        $('#resFormManual').innerHTML = CAMPOS.map(([g, k, txt, ayuda]) => {
            const v = (g === 'manual' ? d.manual : d.planilla)[k];
            let ph = '';
            if (g === 'manual' && (v === undefined || v === null || v === '') && calc[k] !== undefined && calc[k] !== null && num(calc[k])) ph = `Se usa ${soles(calc[k])}`;
            return `<label title="${esc(ayuda)}">${txt}<input type="text" inputmode="decimal" data-g="${g}" data-k="${k}" value="${v === undefined || v === null ? '' : esc(v)}" placeholder="${esc(ph)}"></label>`;
        }).join('') + `<div class="sun-form-pie"><button type="submit" class="btn btn-primary">Guardar</button></div>`;
    }

    async function guardarManual(ev) {
        ev.preventDefault();
        const body = { empresa_id: empresa(), periodo: periodo(), manual: {}, planilla: {} };
        $$('#resFormManual input').forEach(i => { body[i.dataset.g][i.dataset.k] = i.value.trim(); });
        try {
            const j = await api('/sunat/api/periodo', { method: 'POST', body: JSON.stringify(body) });
            aviso(j.mensaje, 'success');
            cargarResumen();
        } catch (e) { aviso(e.message, 'error'); }
    }

    async function verDetalle(libro) {
        $('#resDetalle').innerHTML = '<div class="sun-cargando">Cargando...</div>';
        try {
            const j = await api('/sunat/api/documentos?' + qs({ libro }));
            const filas = j.data;
            if (!filas.length) { $('#resDetalle').innerHTML = '<div class="inv-vacio">No hay comprobantes en este mes.</div>'; return; }
            const tot = k => filas.reduce((s, f) => s + num(f[k]), 0);
            $('#resDetalle').innerHTML = `<div class="sun-tabla-wrap"><table class="inv-table"><thead><tr><th>N°</th><th>${libro === 'VENTAS' ? 'Cliente' : 'Proveedor'}</th><th>RUC / DNI</th><th>Tipo</th><th>N° comprobante</th><th>Fecha de emisión</th><th>Base (S/)</th><th>IGV (S/)</th><th>Total (S/)</th><th>Fuente</th></tr></thead><tbody>
                ${filas.map((f, i) => `<tr><td>${i + 1}</td><td class="left">${esc(f.tercero)}</td><td>${esc(f.ruc)}</td><td>${esc(f.tipo)}</td><td>${esc(f.documento)}</td><td>${fecha(f.fecha)}</td><td class="num">${soles(f.base)}</td><td class="num">${soles(f.igv)}</td><td class="num">${soles(f.total)}</td><td><span class="sun-fuente ${f.fuente === 'Solo ERP' ? 'erp' : f.fuente === 'Solo archivo' ? 'arch' : 'ambos'}">${esc(f.fuente)}</span></td></tr>`).join('')}
            </tbody><tfoot><tr><td colspan="6">Total (${filas.length})</td><td class="num">${soles(tot('base'))}</td><td class="num">${soles(tot('igv'))}</td><td class="num">${soles(tot('total'))}</td><td></td></tr></tfoot></table></div>`;
        } catch (e) { $('#resDetalle').innerHTML = `<div class="inv-vacio">⚠ ${esc(e.message)}</div>`; }
    }

    // ============================================================
    // PLAN DE ACCIÓN
    // ============================================================
    const IR = { completar: ['/sunat?tab=completar', 'Completar datos'], ventas: ['/ventas?tab=despachar', 'Ir a Entregas'], compras: ['/compras?tab=facturas', 'Ir a Pagos y facturas'],
                 oc: ['/compras?tab=pedidos', 'Ir a Pedidos por comprar'], detalle: [null, 'Ver detalle'], resumen: [null, 'Ir a datos del mes'] };

    function pintarPlan() {
        const todo = datos.plan || [];
        const reglas = todo.filter(x => x.grupo === 'Reglas de oro');
        const p = todo.filter(x => x.grupo !== 'Reglas de oro');
        const etiqueta = { rojo: 'Hazlo ya', amarillo: 'Antes del cierre', info: 'Para decidir', verde: 'Bien' };
        $('#planLista').innerHTML = p.length ? p.map(x => {
            const ir = IR[x.ir];
            const montos = [x.monto !== undefined ? soles(x.monto) : '', x.igv !== undefined ? `IGV ${soles(x.igv)}` : ''].filter(Boolean).join(' · ');
            const det = x.detalle || (x.items && x.items.length);
            return `<div class="sun-accion ${x.nivel}">
                <span class="sun-etq ${x.nivel}">${etiqueta[x.nivel] || ''}</span>
                <div class="sun-accion-tit">${esc(x.titulo)}</div>
                ${montos ? `<div class="sun-accion-montos"><b>${montos}</b></div>` : ''}
                ${det ? `<details class="sun-mini-det"><summary>Ver detalle</summary>${x.detalle ? `<div class="sun-accion-txt">${esc(x.detalle)}</div>` : ''}${x.items && x.items.length ? `<ul>${x.items.map(i => `<li>${esc(i)}</li>`).join('')}</ul>` : ''}</details>` : ''}
                ${ir ? (ir[0] ? `<a class="btn-mini" href="${ir[0]}">${ir[1]} →</a>` : `<button class="btn-mini" data-ir="resumen">${ir[1]} →</button>`) : ''}
            </div>`;
        }).join('') : '<div class="inv-vacio">Sin sugerencias.</div>';
        const top = p.filter(x => x.nivel !== 'verde').slice(0, 3);
        if ($('#resPlan')) $('#resPlan').innerHTML = top.length ? top.map(x => `<div class="sun-plan-fila ${x.nivel}"><span class="sun-etq ${x.nivel}">${etiqueta[x.nivel]}</span><b>${esc(x.titulo)}</b>${x.igv !== undefined ? `<span class="num">IGV ${soles(x.igv)}</span>` : ''}</div>`).join('') + `<button class="btn-mini" data-ir="plan">Ver plan completo →</button>`
            : '<div class="inv-vacio">✔ Nada urgente este mes.</div>';
        $('#planReglas').innerHTML = reglas.map(x => `<details class="inv-panel sun-det"><summary>📌 ${esc(x.titulo)}</summary><ul class="sun-reglas">${(x.items || []).map(i => `<li>${esc(i)}</li>`).join('')}</ul></details>`).join('');
    }

    // ============================================================
    // PRELIMINAR VS CONTADOR
    // ============================================================
    function pintarContador() {
        const d = datos;
        $('#conDescargar').href = '/sunat/api/preliminar.xlsx?' + qs();
        $('#conNota').innerHTML = d.tiene_contador
            ? `✔ ${esc(d.contador_archivo || '')} · ${fecha(d.contador_cargado_en)}`
            : `Falta subir la hoja del contador de ${esc(d.nombre_periodo)}.`;
        $('#conObs').innerHTML = (d.observaciones_contador || []).map(o => `<div class="sun-obs">❓ ${esc(o)}</div>`).join('');
        const sec = { igv: 'PDT 621 · IGV', renta: 'PDT 621 · Renta', plame: 'PDT 601 · PLAME', total: 'Total' };
        let ultima = '';
        $('#conTabla').innerHTML = `<thead><tr><th>Concepto</th><th>Preliminar ERP</th><th>Contador</th><th>Diferencia</th></tr></thead><tbody>
            ${d.preliminar.map(f => {
                const cab = f.seccion !== ultima ? `<tr class="sun-fila-seccion"><td colspan="4">${sec[f.seccion]}</td></tr>` : '';
                ultima = f.seccion;
                const dif = f.diferencia === null ? '' : (f.alerta ? `<span class="sun-dif-mal">${soles(f.diferencia)}</span>` : '<span class="sun-dif-ok">✔ Cuadra</span>');
                return cab + `<tr class="${f.alerta ? 'sun-fila-alerta' : ''} ${f.seccion === 'total' ? 'sun-fila-pagar' : ''}"><td class="left">${esc(f.texto)}</td><td class="num">${soles(f.erp)}</td><td class="num">${f.contador === null ? '—' : soles(f.contador)}</td><td>${dif}</td></tr>`;
            }).join('')}
        </tbody>`;
    }

    async function subirContador(ev) {
        const f = ev.target.files[0];
        if (!f) return;
        const fd = new FormData();
        fd.append('archivo', f);
        fd.append('empresa_id', empresa());
        fd.append('periodo', periodo());
        try {
            const j = await api('/sunat/api/contador', { method: 'POST', body: fd });
            aviso(j.mensaje, 'success');
            cargarResumen();
        } catch (e) { aviso(e.message, 'error'); }
        ev.target.value = '';
    }

    // ============================================================
    // PAGOS DEL MES
    // ============================================================
    async function cargarPagos() {
        if (!$('#pagMes').value) $('#pagMes').value = mesHoy();
        $('#pagTabla').innerHTML = '<div class="sun-cargando">Cargando...</div>';
        try {
            const j = await api('/sunat/api/pagos?' + new URLSearchParams({ empresa_id: empresa(), mes: $('#pagMes').value }));
            pintarPagos(j.data);
        } catch (e) { $('#pagTabla').innerHTML = `<div class="inv-vacio">⚠ ${esc(e.message)}</div>`; }
    }

    function pintarPagos(d) {
        const r = d.resumen;
        $('#pagTitulo').textContent = `✅ Pagos de ${d.nombre_mes} · ${d.empresa.codigo}`;
        $('#pagKpis').innerHTML = [
            kpi('Pendientes', r.pendientes, soles(r.monto_pendiente), r.pendientes ? 'inv-kpi-danger' : 'sun-kpi-ok'),
            kpi('Vencidos', r.vencidos, r.vencidos ? '¡Pagar hoy!' : 'Ninguno', r.vencidos ? 'inv-kpi-danger' : 'sun-kpi-ok'),
            kpi('Pagados', r.pagados, soles(r.monto_pagado), 'sun-kpi-ok'),
            kpi('No aplica', r.no_aplica, 'Este mes')
        ].join('');
        $('#pagTabla').innerHTML = `<table class="inv-table sun-pagos"><thead><tr><th>N°</th><th>Qué pagar</th><th>Periodo</th><th>Dónde</th><th>Vence</th><th>Monto (S/)</th><th>Estado</th><th>Pagado el · N° operación · por</th><th>Acciones</th></tr></thead><tbody>
            ${d.filas.map((f, i) => `<tr class="sun-pago ${f.semaforo}" data-i="${i}">
                <td>${i + 1}</td>
                <td class="left" title="${esc(f.ayuda)}"><b>${esc(f.nombre)}</b></td>
                <td>${esc(f.nombre_periodo)}</td>
                <td>${esc(f.donde)}</td>
                <td>${f.vencimiento ? fecha(f.vencimiento) : '<small>Revisar</small>'}</td>
                <td class="num">${f.monto === null ? '<small>Escríbelo</small>' : soles(f.monto)}</td>
                <td><span class="sun-estado ${f.semaforo}">${esc(f.texto_estado)}</span></td>
                <td class="sun-traza" title="${f.marcado_en ? 'Marcado el ' + esc(fecha(f.marcado_en)) : ''}">${f.estado === 'Pagado' ? `${f.fecha_pago ? fecha(f.fecha_pago) : '—'} · ${f.numero_operacion ? 'N° ' + esc(f.numero_operacion) : '<span class="sun-rojo">sin N° operación</span>'} · ${esc(f.marcado_por || '')}` : f.estado === 'No aplica' && f.marcado_por ? esc(f.marcado_por) : ''}</td>
                <td class="sun-acciones">${f.estado === 'Pendiente'
                    ? `<button class="sun-btn verde" data-acc="pagar" data-i="${i}">Marcar pagado</button><button class="sun-btn gris" data-acc="noaplica" data-i="${i}">No aplica</button>`
                    : `<button class="sun-btn gris" data-acc="pendiente" data-i="${i}">Volver a pendiente</button>`}</td>
            </tr>`).join('')}
        </tbody></table>`;
        $$('#pagTabla [data-acc]').forEach(b => b.addEventListener('click', () => accionPago(d, d.filas[+b.dataset.i], b.dataset.acc, b)));
    }

    function accionPago(d, f, acc, boton) {
        const tr = boton.closest('tr');
        const previo = tr.nextElementSibling;
        if (previo && previo.classList.contains('sun-pago-form')) { previo.remove(); return; }
        const form = document.createElement('tr');
        form.className = 'sun-pago-form';
        const titulo = { pagar: `Marcar "${f.nombre}" como pagado`, noaplica: `"${f.nombre}" no aplica este mes`, pendiente: `Volver "${f.nombre}" a pendiente` }[acc];
        form.innerHTML = `<td colspan="9"><div class="sun-form sun-form-linea"><b>${esc(titulo)}</b>
            ${acc === 'pagar' ? `<label>Monto pagado (S/)<input name="monto" inputmode="decimal" value="${f.monto === null ? '' : r2(f.monto)}"></label>
            <label>Fecha de pago<input type="date" name="fecha_pago" value="${new Date().toISOString().slice(0, 10)}"></label>
            <label>N° de operación / NPS (del voucher)<input name="numero_operacion" maxlength="80" required></label>` : ''}
            <label class="sun-ancho">${acc === 'pendiente' ? 'Motivo (obligatorio)' : 'Observación'}<input name="observacion" maxlength="500"></label>
            <button class="btn btn-primary" type="button">Guardar</button></div></td>`;
        tr.after(form);
        form.querySelector('button').addEventListener('click', async () => {
            const val = n => form.querySelector(`[name=${n}]`)?.value || '';
            try {
                const j = await api('/sunat/api/pagos/marcar', { method: 'POST', body: JSON.stringify({
                    empresa_id: empresa(), periodo: f.periodo, codigo: f.codigo,
                    estado: acc === 'pagar' ? 'Pagado' : acc === 'noaplica' ? 'No aplica' : 'Pendiente',
                    monto: val('monto'), fecha_pago: val('fecha_pago'), numero_operacion: val('numero_operacion'), observacion: val('observacion') }) });
                aviso(j.mensaje, 'success');
                cargarPagos();
            } catch (e) { aviso(e.message, 'error'); }
        });
    }

    // ============================================================
    // COMPLETAR DATOS (importar SIRE / Excel)
    // ============================================================
    async function verImportacion(ev) {
        ev.preventDefault();
        const fd = new FormData(ev.target);
        fd.append('empresa_id', empresa());
        fd.append('periodo', periodo());
        $('#impVista').innerHTML = '<div class="sun-cargando">Leyendo el archivo...</div>';
        try {
            const j = await api('/sunat/api/importar/vista', { method: 'POST', body: fd });
            vistaImp = Object.assign(j.data, { libro: fd.get('libro'), origen: fd.get('origen') });
            const r = vistaImp.resumen;
            $('#impVista').innerHTML = `<div class="sun-vista">
                <div class="inv-kpis">${kpi('Comprobantes', r.n, esc(vistaImp.archivo))}${kpi('Ya están en el ERP', r.en_erp, 'No se cuentan dos veces')}${kpi('Base', soles(r.base))}${kpi('IGV', soles(r.igv))}${kpi('Total', soles(r.total))}</div>
                ${vistaImp.avisos.map(a => `<div class="sun-obs">⚠ ${esc(a)}</div>`).join('')}
                <div class="sun-tabla-wrap"><table class="inv-table"><thead><tr><th>N°</th><th>${vistaImp.libro === 'VENTAS' ? 'Cliente' : 'Proveedor'}</th><th>RUC / DNI</th><th>Tipo</th><th>N° comprobante</th><th>Fecha de emisión</th><th>Base (S/)</th><th>IGV (S/)</th><th>Total (S/)</th><th>¿En el ERP?</th></tr></thead><tbody>
                ${vistaImp.filas.slice(0, 200).map((f, i) => `<tr><td>${i + 1}</td><td class="left">${esc(f.nombre)}</td><td>${esc(f.ruc)}</td><td>${esc(f.tipo_cp)}</td><td>${esc(f.serie)}-${esc(f.numero)}</td><td>${fecha(f.fecha)}</td><td class="num">${soles(f.base)}</td><td class="num">${soles(f.igv)}</td><td class="num">${soles(f.total)}</td><td>${f.en_erp ? '<span class="sun-fuente ambos">Sí</span>' : '<span class="sun-fuente arch">No</span>'}</td></tr>`).join('')}
                </tbody></table></div>
                ${vistaImp.filas.length > 200 ? `<div class="inv-foot">Se muestran 200 de ${vistaImp.filas.length}.</div>` : ''}
                <div class="sun-form-pie"><label class="inv-check"><input type="checkbox" id="impReemplazar" ${r.ya_importados ? 'checked' : ''}> Reemplazar lo importado antes de ${vistaImp.libro.toLowerCase()} en este mes</label>
                <button class="btn btn-primary" id="impGuardar">📥 Importar ${r.n} comprobantes</button></div></div>`;
            $('#impGuardar').addEventListener('click', guardarImportacion);
        } catch (e) { $('#impVista').innerHTML = `<div class="sun-obs">⚠ ${esc(e.message)}</div>`; }
    }

    async function guardarImportacion() {
        if (!vistaImp) return;
        try {
            const j = await api('/sunat/api/importar/guardar', { method: 'POST', body: JSON.stringify({
                empresa_id: empresa(), periodo: periodo(), libro: vistaImp.libro, origen: vistaImp.origen, archivo: vistaImp.archivo,
                reemplazar: $('#impReemplazar').checked, filas: vistaImp.filas }) });
            aviso(j.mensaje, 'success');
            vistaImp = null;
            $('#impVista').innerHTML = '';
            $('#impForm').reset();
            cargarImportados();
        } catch (e) { aviso(e.message, 'error'); }
    }

    async function cargarImportados() {
        try {
            const j = await api('/sunat/api/importados?' + qs());
            const f = j.data;
            $('#impLista').innerHTML = f.length ? `<table class="inv-table"><thead><tr><th>Libro</th><th>Viene de</th><th>Archivo</th><th>N° comprobantes</th><th>Base (S/)</th><th>IGV (S/)</th><th>Subido por</th><th>Fecha y hora</th><th>Acciones</th></tr></thead><tbody>
                ${f.map(x => `<tr><td>${esc(x.libro === 'VENTAS' ? 'Ventas' : 'Compras')}</td><td>${esc(x.origen)}</td><td class="left">${esc(x.archivo)}</td><td>${x.n}</td><td class="num">${soles(x.base)}</td><td class="num">${soles(x.igv)}</td><td>${esc(x.creado_por)}</td><td>${fecha(x.creado_en)}</td><td><button class="sun-btn gris" data-lote="${esc(x.lote)}">Quitar</button></td></tr>`).join('')}
            </tbody></table>` : '<div class="inv-vacio">Todavía no se importó nada en este mes.</div>';
            $$('#impLista [data-lote]').forEach(b => b.addEventListener('click', async () => {
                if (!confirm('¿Quitar esta importación? Las ventas y compras del ERP no cambian.')) return;
                try {
                    const r = await api('/sunat/api/importados/quitar', { method: 'POST', body: JSON.stringify({ empresa_id: empresa(), lote: b.dataset.lote }) });
                    aviso(r.mensaje, 'success');
                    cargarImportados();
                } catch (e) { aviso(e.message, 'error'); }
            }));
        } catch (e) { $('#impLista').innerHTML = `<div class="inv-vacio">⚠ ${esc(e.message)}</div>`; }
        if (ADMIN && $('#cfgForm')) cargarConfig();
    }

    async function cargarConfig() {
        try {
            const j = await api('/sunat/api/config?' + new URLSearchParams({ empresa_id: empresa() }));
            const c = j.data, f = $('#cfgForm');
            f.regimen.value = c.regimen; f.tasa_renta.value = c.tasa_renta; f.es_agente_retencion.checked = !!c.es_agente_retencion; f.notas.value = c.notas || '';
        } catch (e) { /* sin permiso */ }
    }

    async function guardarConfig(ev) {
        ev.preventDefault();
        const f = ev.target;
        try {
            const j = await api('/sunat/api/config', { method: 'POST', body: JSON.stringify({ empresa_id: empresa(), regimen: f.regimen.value,
                tasa_renta: f.tasa_renta.value, es_agente_retencion: f.es_agente_retencion.checked, notas: f.notas.value }) });
            aviso(j.mensaje, 'success');
        } catch (e) { aviso(e.message, 'error'); }
    }

    // ============================================================
    // INICIO
    // ============================================================
    function mesHoy() {
        const h = new Date();
        return `${h.getFullYear()}-${String(h.getMonth() + 1).padStart(2, '0')}`;
    }

    document.addEventListener('DOMContentLoaded', () => {
        if (!$('#sunApp')) return;
        $('#sunPeriodo').value = new URLSearchParams(location.search).get('periodo') || mesHoy();
        $$('#sunTabs .tab-btn').forEach(b => b.addEventListener('click', () => irA(b.dataset.tab)));
        $('#sunEmpresa').addEventListener('change', cargar);
        $('#sunPeriodo').addEventListener('change', cargar);
        $('#pagMes').addEventListener('change', cargarPagos);
        $('#resFormManual').addEventListener('submit', guardarManual);
        $('#resFormRet').addEventListener('submit', guardarRet);
        $$('[data-libro]').forEach(b => b.addEventListener('click', () => verDetalle(b.dataset.libro)));
        $('#conArchivo').addEventListener('change', subirContador);
        $('#impForm').addEventListener('submit', verImportacion);
        if ($('#cfgForm')) $('#cfgForm').addEventListener('submit', guardarConfig);
        document.addEventListener('click', ev => {
            const b = ev.target.closest('[data-ir]');
            if (b && $('#sunApp').contains(b)) irA(b.dataset.ir);
        });
        irA(new URLSearchParams(location.search).get('tab') || 'resumen');
    });
})();
