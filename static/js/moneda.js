// moneda.js - Soles y dólares con tipo de cambio (pedido de Erika, 24/10/2026 18:17)
//
// Uso en un formulario:
//   contenedor.innerHTML = Moneda.campos('oc');        // crea #ocMoneda, #ocTC y el texto del equivalente en soles
//   Moneda.enlazar('oc', { fecha: () => '2026-10-24', total: () => 118 });
//   Moneda.poner('oc', 'USD', 3.75);  ...  const { moneda, tipo_cambio } = Moneda.leer('oc');
// El TC se propone con el TC SUNAT (venta) del día y siempre se puede cambiar.
(function () {
    if (window.Moneda) return;
    const cacheTC = {};
    const $ = id => document.getElementById(id);
    const num = n => Number(n || 0).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

    function codigo(m) {
        const v = String(m || '').toUpperCase();
        return (v.includes('$') && !v.includes('S/')) || v.includes('USD') || v.includes('DÓLAR') || v.includes('DOLAR') ? 'USD' : 'PEN';
    }
    const simbolo = m => codigo(m) === 'USD' ? 'US$' : 'S/';
    const fmt = (m, n) => simbolo(m) + ' ' + num(n);

    async function tcSunat(fecha) {
        const f = String(fecha || '').slice(0, 10) || new Date(Date.now() - 5 * 3600000).toISOString().slice(0, 10);
        if (f in cacheTC) return cacheTC[f];
        try {
            const r = await fetch('/api/tipo_cambio?fecha=' + encodeURIComponent(f), { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
            const j = await r.json();
            cacheTC[f] = j && j.venta ? Number(j.venta) : null;
        } catch (e) { cacheTC[f] = null; }
        return cacheTC[f];
    }

    // Campos estándar: moneda + TC (solo si es dólares) + equivalente en soles
    function campos(p, opciones = {}) {
        const etiqueta = opciones.etiqueta || 'Moneda';
        return `<label class="mon-campo">${etiqueta}
                <select id="${p}Moneda"><option value="PEN">Soles (S/)</option><option value="USD">Dólares (US$)</option></select></label>
            <label class="mon-campo" id="${p}TCWrap" style="display:none">Tipo de cambio (S/ por US$)
                <input type="number" id="${p}TC" min="2.5" max="6" step="0.001" placeholder="Ej. 3.750">
                <small class="mon-info" id="${p}TCInfo"></small></label>`;
    }

    function leer(p) {
        const sel = $(p + 'Moneda');
        const m = codigo(sel ? (sel.value || (sel.selectedOptions[0] || {}).textContent) : '');
        return { moneda: m, tipo_cambio: m === 'USD' ? ($(p + 'TC')?.value || '') : null };
    }

    function equivalente(p) {
        const o = enlaces[p] || {};
        const info = $(p + 'TCInfo');
        if (!info) return;
        const { moneda, tipo_cambio } = leer(p);
        const total = o.total ? Number(o.total()) : 0;
        if (moneda !== 'USD') { info.textContent = ''; return; }
        const base = o.origenTC ? o.origenTC + ' · ' : '';
        info.textContent = base + (Number(tipo_cambio) > 0 && total ? `≈ ${fmt('PEN', total * Number(tipo_cambio))}` : '');
    }

    async function proponerTC(p, forzar) {
        const o = enlaces[p] || {};
        const inp = $(p + 'TC');
        if (!inp || (inp.value && !forzar)) { equivalente(p); return; }
        const tc = await tcSunat(o.fecha ? o.fecha() : '');
        if (tc && (!inp.value || forzar)) { inp.value = tc.toFixed(3); o.origenTC = 'TC SUNAT del día'; }
        else if (!tc) o.origenTC = 'Escribe el TC (no se pudo traer el de SUNAT)';
        equivalente(p);
        if (o.alCambiar) o.alCambiar();
    }

    function mostrar(p) {
        const usd = leer(p).moneda === 'USD';
        const w = $(p + 'TCWrap');
        if (w) w.style.display = usd ? '' : 'none';
        if (usd) proponerTC(p); else equivalente(p);
        const o = enlaces[p] || {};
        if (o.alCambiar) o.alCambiar();
    }

    const enlaces = {};
    function enlazar(p, opciones = {}) {
        enlaces[p] = Object.assign(enlaces[p] || {}, opciones);
        const sel = $(p + 'Moneda'), inp = $(p + 'TC');
        if (sel && !sel.dataset.monEnlazado) {
            sel.dataset.monEnlazado = '1';
            sel.addEventListener('change', () => mostrar(p));
        }
        if (inp && !inp.dataset.monEnlazado) {
            inp.dataset.monEnlazado = '1';
            inp.addEventListener('input', () => { (enlaces[p] || {}).origenTC = 'TC escrito a mano'; equivalente(p); const o = enlaces[p] || {}; if (o.alCambiar) o.alCambiar(); });
        }
    }

    function poner(p, moneda, tc) {
        const sel = $(p + 'Moneda'), inp = $(p + 'TC');
        if (sel) {   // los selects antiguos de Ventas usan textos ("Soles (S/)", "Dólares ($)"): se elige la opción equivalente
            const c = codigo(moneda), op = [...sel.options].find(o => codigo(o.value || o.textContent) === c);
            if (op) sel.value = op.value;
        }
        if (inp) inp.value = tc ? Number(tc).toFixed(3) : '';
        if (enlaces[p]) enlaces[p].origenTC = tc ? 'TC guardado' : '';
        mostrar(p);
    }

    // Formularios que se dibujan después (Ventas): cualquier <select id="xMoneda"> con su #xTCWrap funciona solo
    document.addEventListener('change', e => {
        const id = (e.target && e.target.id) || '';
        if (!id.endsWith('Moneda') || e.target.dataset.monEnlazado) return;
        const p = id.slice(0, -6);
        if (!$(p + 'TCWrap')) return;
        enlazar(p);
        mostrar(p);
    });

    window.Moneda = { codigo, simbolo, fmt, tcSunat, campos, enlazar, poner, leer, equivalente, proponerTC };
})();
