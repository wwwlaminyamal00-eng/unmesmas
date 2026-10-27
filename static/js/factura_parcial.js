// static/js/factura_parcial.js
// Factura TOTAL o PARCIAL por posiciones (Erika, 27/10/2026, caso Komatsu: pedido de 5 posiciones, se entregan 4).
//  - Parcial: se marca con check cada posición y su cantidad. Solo va lo entregado con guía y nunca más de lo pedido.
//  - Lo que no se factura lleva motivo y comentario: nota interna, no sale en el PDF ni la ve el cliente.
//  - Debajo de la tabla: Subtotal, IGV y TOTAL (antes solo salía el TOTAL).
// Se engancha a la tabla de productos de la ventana "Nueva factura / Boleta" sin cambiar cómo se llena.
(function () {
    'use strict';
    const IGV = 0.18;
    const MOTIVOS = ['En importación', 'En fabricación', 'Falta ingreso del cliente', 'Otro'];
    const st = { base: [], avance: null, pv: '', modo: 'Total', sel: {}, pend: {}, cargando: false, editId: null, guardado: null };

    const $ = id => document.getElementById(id);
    const r2 = n => Math.round((Number(n) || 0) * 100) / 100;
    const num = n => { const v = Number(n) || 0; return Number.isInteger(v) ? String(v) : String(r2(v)); };
    const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const sim = () => ($('compMoneda')?.value === 'USD' ? 'US$' : 'S/');
    const dinero = n => `${sim()} ${r2(n).toFixed(2)}`;
    const editando = () => (typeof editingId !== 'undefined' ? editingId : null);

    function posiciones() { return (st.avance && st.avance.posiciones) || []; }
    function hayParcial() { return posiciones().length > 0; }

    // Precio de una posición: el del PV; si el PV no lo tiene, el de la tabla que ya estaba
    function precioDe(p) {
        if (Number(p.precio) > 0) return Number(p.precio);
        const b = st.base.find(x => String(x.codigo || '').trim().toUpperCase() === String(p.codigo || '').trim().toUpperCase());
        return b ? Number(b.valorVenta || b.precio_unitario || 0) : 0;
    }

    // 27/10/2026 (caso Komatsu): debajo del Nombre producto, cómo lo pide el cliente
    function lineaCli(p) {
        return typeof window.lineaClienteHTML === 'function' ? window.lineaClienteHTML(p) : '';
    }

    function itemDePosicion(p, cantidad) {
        const b = st.base.find(x => String(x.codigo || '').trim().toUpperCase() === String(p.codigo || '').trim().toUpperCase()) || {};
        return { ...b, codigo: p.codigo, producto: p.producto, um: p.unidad || b.um || 'NIU', marca: p.marca || b.marca || '',
                 descripcion_cliente: p.descripcion_cliente || b.descripcion_cliente || '',
                 codigo_cliente: p.codigo_cliente || b.codigo_cliente || '',
                 modelo: p.modelo || b.modelo || '', cantidad: r2(cantidad), valorVenta: precioDe(p), posicion: p.posicion };
    }

    // Productos que lleva la factura según el modo
    function itemsFactura() {
        if (st.modo === 'Parcial' && hayParcial()) {
            return posiciones().filter(p => st.sel[p.posicion]?.on && Number(st.sel[p.posicion].cant) > 0)
                .map(p => itemDePosicion(p, st.sel[p.posicion].cant));
        }
        // Total: si ya hubo facturas parciales del PV, la "total" lleva solo lo que falta facturar
        if (hayParcial() && posiciones().some(p => Number(p.facturado) > 0)) {
            return posiciones().filter(p => Number(p.por_facturar) > 0).map(p => itemDePosicion(p, p.por_facturar));
        }
        return st.base;
    }

    // Lo que queda sin facturar después de esta factura (necesita motivo en la parcial)
    function quedan() {
        if (st.modo !== 'Parcial') return [];
        return posiciones().map(p => {
            const s = st.sel[p.posicion] || {};
            const esta = s.on ? Math.min(Number(s.cant) || 0, Number(p.por_facturar)) : 0;
            return { p, falta: r2(Number(p.por_facturar) - esta) };
        }).filter(x => x.falta > 0.0001);
    }

    function totales(items) {
        const sub = r2(items.reduce((s, it) => s + r2((Number(it.cantidad) || 0) * (Number(it.valorVenta) || 0)), 0));
        const igv = r2(sub * IGV);
        return { sub, igv, total: r2(sub + igv) };
    }

    function pie(t, cols) {
        const izq = `colspan="${cols - 1}" style="text-align:right;font-weight:900;background:#F8FAFC"`;
        return `<tfoot>
            <tr><td ${izq}>Subtotal</td><td class="fp-num" style="font-weight:800">${dinero(t.sub)}</td></tr>
            <tr><td ${izq}>IGV (18%)</td><td class="fp-num" style="font-weight:800">${dinero(t.igv)}</td></tr>
            <tr><td ${izq}>TOTAL</td><td class="fp-num" style="font-weight:900;font-size:14px;color:#EF233C;background:#FFF1F2">${dinero(t.total)}</td></tr>
        </tfoot>`;
    }

    function selectorModo() {
        if (!hayParcial()) {
            return st.pv ? '' : `<div class="fp-aviso">Para facturar por partes (solo lo entregado), primero elige el PV (Pedido de venta).</div>`;
        }
        const a = st.avance;
        return `<div class="fp-modo">
            <div class="fp-pregunta">¿Vas a facturar todo el pedido o solo una parte?</div>
            <label class="fp-op ${st.modo === 'Total' ? 'on' : ''}"><input type="radio" name="fpModo" value="Total" ${st.modo === 'Total' ? 'checked' : ''}> Factura total</label>
            <label class="fp-op ${st.modo === 'Parcial' ? 'on' : ''}"><input type="radio" name="fpModo" value="Parcial" ${st.modo === 'Parcial' ? 'checked' : ''}> Factura parcial (por posición o por cantidad)</label>
            <div class="fp-avance">PV ${esc(a.pv)} · Entregado ${num(a.entregado_pct)}% · Con guía ${num(a.guiado_pct)}% · Facturado ${num(a.facturado_pct)}%${(a.guias || []).length ? ' · Guías: ' + esc(a.guias.join(', ')) : ''}</div>
        </div>${avisoRojo()}`;
    }

    // 27/10/2026 20:34 (Erika): aviso rojo claro cuando la factura no cubre todo o lleva algo sin guía
    function avisoRojo() {
        const ps = posiciones();
        if (!ps.length) return '';
        const pedido = ps.reduce((t, p) => t + Number(p.pedido || 0), 0);
        if (st.modo !== 'Parcial') {
            const sinGuia = ps.filter(p => Number(p.guiado) < Number(p.pedido) - 0.0001);
            return sinGuia.length && ps.some(p => Number(p.por_facturar) > 0) ? `<div class="fp-alerta fp-alerta-amb">⚠ Ojo: el PV todavía no sale completo con guía
                (${sinGuia.map(p => 'posición ' + p.posicion).join(', ')}). La factura total se permite (el cliente paga antes), pero revisa que sea lo acordado.</div>` : '';
        }
        let lleva = 0, sinGuiaCant = 0;
        const faltan = [];
        ps.forEach(p => {
            const s = st.sel[p.posicion] || {};
            const c = s.on ? Number(s.cant) || 0 : 0;
            lleva += c;
            sinGuiaCant += Math.max(c - Number(p.facturable || 0), 0);
            const queda = Number(p.por_facturar) - c;
            if (queda > 0.0001) faltan.push(`posición ${p.posicion} (${num(queda)} ${esc(p.unidad || 'NIU')})`);
        });
        const ya = ps.reduce((t, p) => t + Number(p.facturado || 0), 0);
        return `<div class="fp-alerta">🔴 <b>FACTURA PARCIAL</b>: esta factura lleva <b>${num(lleva)}</b> de <b>${num(pedido)}</b> unidades del PV ${esc(st.avance && st.avance.pv || st.pv)}${ya > 0 ? ` (antes ya se facturaron ${num(ya)})` : ''}.
            ${faltan.length ? `<br>Quedan por facturar: <b>${faltan.join(', ')}</b>. Escribe abajo el motivo.` : '<br>Con esta factura el PV queda facturado completo.'}
            ${sinGuiaCant > 0.0001 ? `<br>⚠ <b>${num(sinGuiaCant)}</b> de lo que facturas todavía <b>no salió con guía</b> (no se entregó). Confirma que el cliente lo aceptó así.` : ''}
        </div>`;
    }

    function tablaTotal(items) {
        const t = totales(items);
        return `<div class="table-scroll"><table class="master-table fp-tabla" style="font-size:11px">
            <thead><tr><th>Ítem</th><th>Código de producto</th><th>Nombre producto</th><th>Marca</th><th>Modelo</th><th>Unidad</th><th>Cantidad</th><th>Precio unitario</th><th>Total</th></tr></thead>
            <tbody>${items.map((p, i) => `<tr>
                <td>${p.posicion || i + 1}</td><td>${esc(p.codigo || '-')}</td><td class="left">${esc(p.producto || p.descripcion || 'Sin nombre')}${lineaCli(p)}</td>
                <td>${esc(p.marca || '-')}</td><td>${esc(p.modelo || '-')}</td><td>${esc(p.um || 'NIU')}</td><td>${num(p.cantidad || 0)}</td>
                <td class="fp-num">${dinero(p.valorVenta)}</td><td class="fp-num" style="font-weight:900;color:#059669">${dinero((Number(p.cantidad) || 0) * (Number(p.valorVenta) || 0))}</td>
            </tr>`).join('')}</tbody>${pie(t, 9)}</table></div>`;
    }

    function tablaParcial() {
        const items = itemsFactura();
        const t = totales(items);
        const filas = posiciones().map(p => {
            const s = st.sel[p.posicion] || { on: false, cant: 0 };
            const max = Number(p.por_facturar);
            const bloqueada = max <= 0;
            const motivoNoSe = bloqueada ? 'Ya facturada' : '';
            const cant = s.on ? Number(s.cant) || 0 : 0;
            const sinGuia = Math.max(cant - Number(p.facturable || 0), 0);
            return `<tr class="${s.on ? 'fp-on' : 'fp-off'}">
                <td><input type="checkbox" class="fp-check" data-pos="${p.posicion}" ${s.on ? 'checked' : ''} ${bloqueada ? 'disabled' : ''} title="${bloqueada ? esc(motivoNoSe) : 'Facturar esta posición'}"></td>
                <td><b>${p.posicion}</b></td><td>${esc(p.codigo || '-')}</td><td class="left">${esc(p.producto)}${lineaCli(p)}</td><td>${esc(p.unidad || 'NIU')}</td>
                <td class="fp-av">Pedido <b>${num(p.pedido)}</b><br>Con guía <b>${num(p.guiado)}</b><br>Facturado <b>${num(p.facturado)}</b></td>
                <td>${bloqueada ? `<span class="fp-no">${esc(motivoNoSe)}</span>` :
                    `<input type="number" class="fp-cant" data-pos="${p.posicion}" min="0" max="${max}" step="any" value="${s.on ? num(s.cant) : ''}" ${s.on ? '' : 'disabled'}><small class="fp-max">máx. ${num(max)} (lo que falta del PV)</small>${sinGuia > 0.0001 ? `<small class="fp-sin-guia">⚠ ${num(sinGuia)} sin guía</small>` : ''}`}</td>
                <td class="fp-num">${dinero(precioDe(p))}</td>
                <td class="fp-num" style="font-weight:900;color:#059669">${dinero(cant * precioDe(p))}</td>
            </tr>`;
        }).join('');
        const q = quedan();
        const pend = q.length ? `<div class="fp-pend">
            <div class="fp-pend-tit">Lo que NO se factura ahora <small>(nota interna: el cliente no la ve y no sale en el PDF)</small></div>
            ${q.map(({ p, falta }) => {
                const m = st.pend[p.posicion] || {};
                return `<div class="fp-pend-fila">
                    <div class="fp-pend-pos"><b>Posición ${p.posicion}</b> · ${esc(p.producto)} · falta facturar <b>${num(falta)}</b></div>
                    <select class="fp-motivo" data-pos="${p.posicion}"><option value="">Motivo…</option>${MOTIVOS.map(x => `<option ${m.motivo === x ? 'selected' : ''}>${x}</option>`).join('')}</select>
                    <input type="text" class="fp-coment" data-pos="${p.posicion}" maxlength="300" placeholder="Comentario (ej. llega de importación el 20/11)" value="${esc(m.comentario || '')}">
                </div>`;
            }).join('')}</div>` : '';
        return `<div class="table-scroll"><table class="master-table fp-tabla" style="font-size:11px">
            <thead><tr><th>Facturar</th><th>Posición</th><th>Código de producto</th><th>Nombre producto</th><th>Unidad</th><th>Avance</th><th>Cantidad a facturar</th><th>Precio unitario</th><th>Total</th></tr></thead>
            <tbody>${filas}</tbody>${pie(t, 9)}</table></div>${pend}`;
    }

    function pintar() {
        const cont = $('compProducts');
        if (!cont) return;
        const items = itemsFactura();
        const html = `<div data-fp="1">${selectorModo()}${st.modo === 'Parcial' && hayParcial() ? tablaParcial()
            : (items.length ? tablaTotal(items) : '<div style="padding:20px;text-align:center;color:#94A3B8">📭 No hay productos disponibles.</div>')}</div>`;
        st.pintando = true;
        try { cont.innerHTML = html; }
        catch (e) { setTimeout(pintar, 0); }   // la casilla que se estaba dejando (blur) aún no se soltó: se repinta enseguida
        st.pintando = false;
        // La factura guarda lo que se ve
        if (items.length || st.modo === 'Parcial') window._compProductos = items;
        const monto = $('compMonto');
        if (monto && items.length) {
            const t = totales(items).total.toFixed(2);
            if (monto.value !== t) { monto.value = t; monto.dispatchEvent(new Event('input', { bubbles: true })); monto.dispatchEvent(new Event('change', { bubbles: true })); }
        }
    }

    async function cargarAvance() {
        const pv = ($('compPC')?.value || '').trim();
        st.pv = pv;
        if (!pv) { st.avance = null; pintar(); return; }
        st.cargando = true;
        try {
            const ex = editando();
            const r = await fetch(`/ventas/api/pv/avance?numero=${encodeURIComponent(pv)}${ex ? '&excluir=' + ex : ''}`, { credentials: 'same-origin' });
            const j = await r.json();
            if (($('compPC')?.value || '').trim() !== pv) { st.cargando = false; return; }   // cambió mientras cargaba
            st.avance = j.success ? j.data : null;
        } catch (e) { st.avance = null; }
        st.cargando = false;
        prepararSeleccion();
        pintar();
    }

    // Por defecto: se marca lo que tiene guía y falta facturar. Al editar una parcial, lo que ya tenía.
    function prepararSeleccion() {
        st.sel = {}; st.pend = {};
        const g = st.guardado;
        if (g && g.facturacion_tipo) st.modo = g.facturacion_tipo;
        posiciones().forEach(p => {
            const enFactura = g && g.facturacion_tipo === 'Parcial' ? st.base.filter(b => String(b.codigo || '').toUpperCase() === String(p.codigo || '').toUpperCase())
                .reduce((s, b) => s + (Number(b.cantidad) || 0), 0) : null;
            const cant = enFactura !== null ? Math.min(enFactura, Number(p.facturable)) : Number(p.facturable);
            st.sel[p.posicion] = { on: cant > 0, cant: r2(cant) };
            if (p.motivo) st.pend[p.posicion] = { motivo: p.motivo.motivo, comentario: p.motivo.comentario };
        });
        ((g && g.pendientes_json) || []).forEach(m => { st.pend[m.posicion] = { motivo: m.motivo, comentario: m.comentario }; });
    }

    // ---------- eventos ----------
    document.addEventListener('change', e => {
        const t = e.target;
        if (!t || !t.closest || !t.closest('#compProducts, #compPC')) {
            if (t && t.id === 'compPC') cargarAvance();
            return;
        }
        if (t.id === 'compPC') { cargarAvance(); return; }
        if (t.name === 'fpModo') { st.modo = t.value; pintar(); return; }
        const pos = Number(t.dataset.pos);
        if (t.classList.contains('fp-check')) {
            const p = posiciones().find(x => x.posicion === pos);
            st.sel[pos] = { on: t.checked, cant: t.checked ? (Number(st.sel[pos]?.cant) || Number(p?.facturable) || Number(p?.por_facturar) || 0) : 0 };
            pintar();
        } else if (t.classList.contains('fp-cant')) {
            const p = posiciones().find(x => x.posicion === pos);
            let v = Math.max(Number(t.value) || 0, 0);
            if (p && v > Number(p.por_facturar)) { v = Number(p.por_facturar); if (window.showToast) showToast(`Posición ${pos}: el PV pide ${num(p.pedido)} y ya se facturó ${num(p.facturado)}. Máximo ${num(v)}.`, 'warning'); }
            st.sel[pos] = { on: v > 0, cant: r2(v) };
            pintar();
        } else if (t.classList.contains('fp-motivo')) {
            st.pend[pos] = { ...(st.pend[pos] || {}), motivo: t.value };
        }
    });
    document.addEventListener('input', e => {
        const t = e.target;
        if (t && t.classList && t.classList.contains('fp-coment')) st.pend[Number(t.dataset.pos)] = { ...(st.pend[Number(t.dataset.pos)] || {}), comentario: t.value };
    });

    // Otra parte del sistema volvió a llenar la tabla (al elegir guía, PV o cotización): se toma como base y se repinta
    let programado = false;
    function revisar() {
        programado = false;
        const cont = $('compProducts');
        if (!cont || st.pintando) return;
        if (cont.querySelector('[data-fp]')) return;
        st.base = Array.isArray(window._compProductos) ? window._compProductos.map(x => ({ ...x })) : [];
        const ed = editando();
        if (ed && st.editId !== ed) {
            st.editId = ed;
            st.guardado = null;
            fetch(`/ventas/api/comprobantes/${ed}`, { credentials: 'same-origin' }).then(r => r.json()).then(j => {
                if (j.success && j.data) {
                    const d = j.data;
                    let pend = d.pendientes_json;
                    if (typeof pend === 'string') { try { pend = JSON.parse(pend); } catch (e) { pend = []; } }
                    st.guardado = { facturacion_tipo: d.facturacion_tipo, pendientes_json: pend || [] };
                }
            }).catch(() => {}).finally(cargarAvance);
            return;
        }
        if (!ed) { st.editId = null; st.guardado = null; }
        const pv = ($('compPC')?.value || '').trim();
        if (pv && st.avance && st.avance.pv === pv) { prepararSeleccionSiVacia(); pintar(); } else cargarAvance();
    }
    function prepararSeleccionSiVacia() { if (!Object.keys(st.sel).length) prepararSeleccion(); }

    const obs = new MutationObserver(() => { if (!programado && !st.pintando) { programado = true; setTimeout(revisar, 60); } });
    function enganchar() {
        const f = $('comprobanteForm');
        if (f) obs.observe(f, { childList: true, subtree: true });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', enganchar); else enganchar();
    // El PV a veces se pone por código (desde la guía o la cotización) sin aviso de cambio: se revisa cada medio segundo
    setInterval(() => {
        // El modal es position:fixed (su offsetParent siempre es null): se mira el campo del PV, que sí está dentro
        const c = $('compPC');
        if (!c || !c.offsetParent) return;
        const pv = ($('compPC')?.value || '').trim();
        if (pv !== st.pv && !st.cargando) cargarAvance();
    }, 500);

    // Al abrir una factura nueva se empieza en "Factura total"
    document.addEventListener('click', e => {
        const b = e.target && e.target.closest && e.target.closest('[onclick*="openComprobanteModal"], [onclick*="createDocFromCotizacion"]');
        if (b) { st.modo = 'Total'; st.sel = {}; st.pend = {}; st.avance = null; st.editId = null; st.guardado = null; }
    }, true);

    // ---------- Ventas ▸ PV: "Entregado X% · Facturado Y% · Falta: posición N" debajo del estado ----------
    const cacheAvance = {};
    let pvProgramado = false;
    // Mismos colores de avance (regla de oro), con clases propias para que no se repinten por el texto
    function claseAvance(p) { return p >= 100 ? 'pvav-100' : p >= 80 ? 'pvav-80' : p > 0 ? 'pvav-50' : 'pvav-0'; }
    async function pintarAvancePV() {
        pvProgramado = false;
        const tb = $('pcRows');
        if (!tb) return;
        const filas = [...tb.querySelectorAll('tr')].map(tr => {
            const tds = tr.querySelectorAll('td');
            if (tds.length < 5 || tr.querySelector('.pv-avance')) return null;
            const m = (tds[3].textContent || '').match(/P[VC]-[A-Z0-9]+-\d+/i);
            return m ? { tr, td: tds[2], pv: m[0].toUpperCase() } : null;
        }).filter(Boolean);
        if (!filas.length) return;
        const faltan = [...new Set(filas.map(f => f.pv))].filter(n => !(n in cacheAvance));
        if (faltan.length) {
            try {
                const r = await fetch('/ventas/api/pv/avance-lista?numeros=' + encodeURIComponent(faltan.join(',')), { credentials: 'same-origin' });
                const j = await r.json();
                faltan.forEach(n => { cacheAvance[n] = (j.success && j.data && j.data[n]) || null; });
            } catch (e) { return; }
        }
        filas.forEach(({ td, pv }) => {
            const a = cacheAvance[pv];
            // Sin entregas ni facturas todavía no se muestra nada (evita llenar la tabla de rojos)
            if (!a || td.querySelector('.pv-avance') || (!a.entregado_pct && !a.facturado_pct && !a.facturas)) return;
            const s = document.createElement('span');
            s.className = 'pv-avance';
            const falta = a.faltan_facturar && a.faltan_facturar.length && a.facturas > 0
                ? `<br><span class="pv-falta">Falta facturar: posición ${a.faltan_facturar.join(', ')}</span>` : '';
            s.innerHTML = `<span class="pvav ${claseAvance(a.entregado_pct)}">Entregado ${num(a.entregado_pct)}%</span> ` +
                `<span class="pvav ${claseAvance(a.facturado_pct)}">Facturado ${num(a.facturado_pct)}%</span>${falta}`;
            s.title = (a.motivos || []).join(' · ');
            td.appendChild(s);
        });
    }
    const obsPV = new MutationObserver(() => { if (!pvProgramado) { pvProgramado = true; setTimeout(pintarAvancePV, 150); } });
    function engancharPV() { const tb = $('pcRows'); if (tb) obsPV.observe(tb, { childList: true }); pintarAvancePV(); }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', engancharPV); else engancharPV();
    // Después de guardar una factura, el avance cambia
    window.addEventListener('focus', () => { Object.keys(cacheAvance).forEach(k => delete cacheAvance[k]); });

    window.FacturaParcial = {
        modo: () => (hayParcial() ? st.modo : undefined),
        pendientes: () => quedan().map(({ p, falta }) => ({ posicion: p.posicion, falta, motivo: st.pend[p.posicion]?.motivo || '',
                                                              comentario: st.pend[p.posicion]?.comentario || '' })),
        listaParaGuardar() {
            if (st.cargando) { window.showToast && showToast('⏳ Revisando lo entregado del PV, intenta en un momento.', 'info'); return false; }
            if (st.modo !== 'Parcial' || !hayParcial()) return true;
            if (!itemsFactura().length) { window.showToast && showToast('⚠️ Marca al menos una posición para facturar.', 'error'); return false; }
            const falta = quedan().find(({ p }) => !st.pend[p.posicion]?.motivo || String(st.pend[p.posicion]?.comentario || '').trim().length < 5);
            if (falta) {
                window.showToast && showToast(`⚠️ Posición ${falta.p.posicion}: elige el motivo y escribe un comentario de por qué no se factura.`, 'error');
                document.querySelector(`.fp-motivo[data-pos="${falta.p.posicion}"]`)?.focus();
                return false;
            }
            return true;
        },
        _estado: st
    };
})();
