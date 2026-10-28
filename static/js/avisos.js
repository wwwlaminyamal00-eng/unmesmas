// static/js/avisos.js
// Avisos claros en todo el ERP (Erika, 27/10/2026 18:58): viñetas, oraciones cortas, negritas, en AZUL los datos del
// documento (N° despacho, PV, PC del cliente, cotización…) y en ROJO lo importante (lo que no se deshace, el stock que
// se descuenta). Nada de párrafos largos. Se usa en las ventanas de confirmación de todos los módulos.
(function () {
    'use strict';
    const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const tieneHTML = t => /<[a-z][\s\S]*>/i.test(String(t || ''));

    // "Se descontará el stock. Se creará la guía." → ['Se descontará el stock', 'Se creará la guía']
    function oraciones(texto) {
        if (Array.isArray(texto)) return texto.filter(Boolean);
        const t = String(texto || '').replace(/^\s*[⚠️❗🔴]+\s*/u, '').trim();
        if (!t) return [];
        if (tieneHTML(t)) return [t];
        return t.split(/(?<=[.!])\s+(?=[A-ZÁÉÍÓÚÑ¿¡0-9"])/u).map(x => x.replace(/[.]\s*$/, '').trim()).filter(Boolean);
    }

    function lista(items, clase, crudo) {
        const xs = (items || []).filter(Boolean);
        if (!xs.length) return '';
        return `<ul class="aviso-lista ${clase || ''}">${xs.map(x => `<li>${crudo ? x : esc(x)}</li>`).join('')}</ul>`;
    }

    // Datos del documento en azul: [['Despacho', 'DESP-KCF-000008'], ['PV', 'PV-KCF-000029'], …]
    function docs(pares) {
        const xs = (pares || []).filter(p => p && p[1] !== undefined && p[1] !== null && String(p[1]).trim() !== '' && String(p[1]).trim() !== '-');
        if (!xs.length) return '';
        return `<ul class="aviso-lista aviso-docs">${xs.map(([k, v]) => `<li>${esc(k)}: <b class="aviso-azul">${esc(v)}</b></li>`).join('')}</ul>`;
    }

    // Los documentos de un despacho / PV / cotización, en el orden de siempre
    function docsDe(r) {
        r = r || {};
        return [['Despacho', r.numero && /^DESP/i.test(r.numero) ? r.numero : ''],
                ['PV (Pedido de venta)', r.pc_numero || (/^P[VC]-/i.test(r.numero || '') ? r.numero : '')],
                ['PC (Pedido del cliente)', r.oc_cliente || ''],
                ['Cotización', r.cotizacion_numero || ''],
                ['Cliente', r.cliente || '']];
    }

    function productos(items) {
        const xs = (items || []).map(it => {
            const n = Number(it.cantidad ?? it.cantidad_pc ?? 0);
            const cant = isNaN(n) ? esc(it.cantidad) : n.toLocaleString('es-PE', { maximumFractionDigits: 2 });
            return `<b>${cant}</b> × ${esc(it.producto || it.descripcion || it.nombre || '')}`;
        }).filter(Boolean);
        if (!xs.length) return '';
        const max = 6;
        const mas = xs.length > max ? [`<i>y ${xs.length - max} producto(s) más</i>`] : [];
        return `<div class="aviso-sub">Productos</div>` + lista(xs.slice(0, max).concat(mas), 'aviso-prod', true);
    }

    function rojo(texto) {
        const xs = oraciones(texto);
        if (!xs.length) return '';
        return `<div class="aviso-rojo">${lista(xs.map(x => tieneHTML(x) ? x : esc(x)), '', true)}</div>`;
    }

    // Arma el cuerpo completo: docs (azul), puntos (negro), productos y rojo
    function html(o) {
        o = o || {};
        return `<div class="aviso-cuerpo">${docs(o.docs)}${o.puntos ? lista(o.puntos.map(x => tieneHTML(x) ? x : esc(x)), '', true) : ''}` +
            `${o.productos ? productos(o.productos) : ''}${o.extra || ''}${o.rojo ? rojo(o.rojo) : ''}</div>`;
    }

    // Texto suelto de un aviso antiguo (un párrafo): se parte en viñetas por oración
    function cuerpoDesdeTexto(texto) {
        if (!texto) return '';
        if (tieneHTML(texto) && /<(ul|div|table|select|input)/i.test(texto)) return `<div class="aviso-cuerpo">${texto}</div>`;
        const xs = oraciones(texto);
        return `<div class="aviso-cuerpo">${lista(xs, '', tieneHTML(texto))}</div>`;
    }

    window.Aviso = { html, docs, docsDe, productos, rojo, lista, oraciones, cuerpoDesdeTexto, esc };
})();
