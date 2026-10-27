// static/js/guia_parcial.js
// Guía parcial y guía por saldo (Erika, 27/10/2026 20:34). Un PV puede tener 2 o 3 guías: se entrega lo que hay y,
// cuando llega el resto, se hace la guía por saldo. Encima de los productos de la guía se muestra, por posición,
// cuánto pide el PV, cuánto ya salió con guía, cuánto lleva esta guía y el saldo, con aviso rojo si queda saldo.
// Nunca más de lo que pide el PV: el servidor tampoco lo deja guardar.
(function () {
    'use strict';
    const $ = id => document.getElementById(id);
    const r2 = n => Math.round((Number(n) || 0) * 100) / 100;
    const num = n => { const v = Number(n) || 0; return Number.isInteger(v) ? String(v) : String(r2(v)); };
    const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const st = { doc: '', avance: null, cargando: false, pidio: '' };

    function abierta() {
        const m = $('guiaModal');
        return m && (m.classList.contains('active') || m.classList.contains('show') || getComputedStyle(m).display !== 'none');
    }
    function documento() { return ($('guiaCotizacion')?.value || '').trim(); }
    function idEditando() { return (typeof editingId !== 'undefined' && editingId) ? editingId : ''; }

    function filasGuia() {
        return [...document.querySelectorAll('#guiaProductosBody tr')].map(tr => ({
            tr,
            codigo: String(tr.querySelector('.guia-producto-codigo')?.value || '').trim().toUpperCase(),
            input: tr.querySelector('.guia-producto-cant'),
            cant: Number(tr.querySelector('.guia-producto-cant')?.value || 0)
        })).filter(f => f.codigo && f.input);
    }

    async function cargar() {
        const doc = documento();
        const clave = doc + '|' + idEditando();
        if (st.cargando || clave === st.pidio) return;
        st.pidio = clave;
        st.doc = doc;
        st.avance = null;
        if (!doc || !/^(PV|PC|COT)/i.test(doc)) { pintar(); return; }
        st.cargando = true;
        try {
            const q = new URLSearchParams({ numero: doc });
            if (idEditando()) q.set('excluir_guia', idEditando());
            const r = await fetch('/ventas/api/pv/avance?' + q.toString(), { credentials: 'same-origin' });
            const j = await r.json();
            st.avance = j.success ? j.data : null;
        } catch (e) { st.avance = null; }
        st.cargando = false;
        pintar();
    }

    function caja() {
        let c = $('guiaParcialAviso');
        const body = $('guiaProductosBody');
        const tabla = body && body.closest('table');
        if (!tabla) return null;
        const ancla = tabla.closest('.table-scroll, .table-container') || tabla;
        if (!c) {
            c = document.createElement('div');
            c.id = 'guiaParcialAviso';
            ancla.parentNode.insertBefore(c, ancla);
        } else if (c.nextElementSibling !== ancla) {
            ancla.parentNode.insertBefore(c, ancla);
        }
        return c;
    }

    function pintar() {
        const c = caja();
        if (!c) return;
        const a = st.avance;
        if (!a || !(a.posiciones || []).length) { c.innerHTML = ''; return; }
        const filas = filasGuia();
        const lleva = {};
        filas.forEach(f => { lleva[f.codigo] = (lleva[f.codigo] || 0) + f.cant; });
        // Lo que lleva esta guía se reparte entre las posiciones del mismo producto, en orden
        const resto = { ...lleva };
        let saldoTotal = 0, ya = 0, errores = [];
        const lineas = a.posiciones.map(p => {
            const k = String(p.codigo || '').trim().toUpperCase();
            const disponible = Math.max(Number(p.pedido) - Number(p.guiado), 0);
            const esta = Math.min(resto[k] || 0, disponible);
            resto[k] = (resto[k] || 0) - esta;
            const saldo = r2(disponible - esta);
            saldoTotal += saldo;
            ya += Number(p.guiado) || 0;
            return { p, disponible, esta, saldo };
        });
        Object.entries(resto).forEach(([k, v]) => {
            if (v > 0.0001 && a.posiciones.some(p => String(p.codigo || '').trim().toUpperCase() === k)) {
                const ps = lineas.filter(l => String(l.p.codigo || '').trim().toUpperCase() === k);
                const max = ps.reduce((t, l) => t + l.disponible, 0);
                errores.push(`${esc(k)}: esta guía puede llevar como máximo <b>${num(max)}</b> (el PV pide ${num(ps.reduce((t, l) => t + Number(l.p.pedido), 0))} y ya salió ${num(ps.reduce((t, l) => t + Number(l.p.guiado), 0))} con guía)`);
            }
        });
        // Máximo en cada casilla de cantidad
        filas.forEach(f => {
            const max = lineas.filter(l => String(l.p.codigo || '').trim().toUpperCase() === f.codigo).reduce((t, l) => t + l.disponible, 0);
            if (lineas.some(l => String(l.p.codigo || '').trim().toUpperCase() === f.codigo)) {
                f.input.max = String(max);
                f.input.title = `Máximo ${num(max)}: lo que falta entregar de este producto en el PV`;
                f.input.style.outline = f.cant > max + 0.0001 ? '2px solid #DC2626' : '';
            }
        });
        const detalle = lineas.map(l => `<tr class="${l.saldo > 0.0001 ? 'gp-saldo' : ''}"><td>${l.p.posicion}</td><td>${esc(l.p.codigo || '-')}</td>
            <td class="left">${esc(l.p.producto || '')}</td><td>${num(l.p.pedido)}</td><td>${num(l.p.guiado)}</td><td><b>${num(l.esta)}</b></td>
            <td><b>${num(l.saldo)}</b></td></tr>`).join('');
        let titulo;
        if (errores.length) {
            titulo = `<div class="fp-alerta">⛔ <b>NO SE PODRÁ GUARDAR</b>: ${errores.join('<br>')}</div>`;
        } else if (saldoTotal > 0.0001) {
            const pos = lineas.filter(l => l.saldo > 0.0001).map(l => `posición ${l.p.posicion} (${num(l.saldo)})`).join(', ');
            titulo = `<div class="fp-alerta">🔴 <b>GUÍA PARCIAL</b>: después de esta guía quedan por entregar <b>${pos}</b>.
                Cuando llegue el producto se hace la <b>guía por saldo</b>.${(a.guias || []).length ? ` Guías anteriores de este PV: ${esc(a.guias.join(', '))}.` : ''}</div>`;
        } else if (ya > 0) {
            titulo = `<div class="fp-alerta fp-alerta-ok">✅ <b>GUÍA POR SALDO</b>: con esta guía el PV ${esc(a.pv)} queda entregado completo. Guías anteriores: ${esc((a.guias || []).join(', '))}.</div>`;
        } else {
            titulo = `<div class="fp-alerta fp-alerta-ok">✅ <b>GUÍA COMPLETA</b>: esta guía lleva todo el PV ${esc(a.pv)}.</div>`;
        }
        c.innerHTML = `${titulo}<details class="gp-detalle" ${errores.length || saldoTotal > 0.0001 ? 'open' : ''}><summary>Ver avance del PV ${esc(a.pv)} por posición</summary>
            <table class="master-table gp-tabla"><thead><tr><th>Posición</th><th>Código de producto</th><th>Nombre producto</th><th>Pide el PV</th>
            <th>Ya salió con guía</th><th>Esta guía</th><th>Saldo</th></tr></thead><tbody>${detalle}</tbody></table></details>`;
    }

    let programado = false;
    function revisar() {
        programado = false;
        if (!abierta()) { st.pidio = ''; return; }
        const clave = documento() + '|' + idEditando();
        if (clave !== st.pidio) cargar(); else pintar();
    }
    document.addEventListener('input', e => {
        if (e.target && e.target.closest && e.target.closest('#guiaProductosBody') && !programado) { programado = true; setTimeout(revisar, 150); }
    });
    document.addEventListener('change', e => {
        if (e.target && (e.target.id === 'guiaCotizacion' || (e.target.closest && e.target.closest('#guiaProductosBody'))) && !programado) {
            programado = true; setTimeout(revisar, 150);
        }
    });
    // La tabla y el documento se llenan por código al abrir la guía: se revisa cada medio segundo mientras está abierta
    let firma = '';
    setInterval(() => {
        if (!abierta()) { if (st.pidio) { st.pidio = ''; firma = ''; } return; }
        const f = documento() + '|' + idEditando() + '|' + filasGuia().map(x => x.codigo + ':' + x.cant).join(',');
        if (f !== firma) { firma = f; revisar(); }
    }, 500);
})();
