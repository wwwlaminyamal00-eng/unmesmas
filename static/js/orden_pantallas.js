// orden_pantallas.js - Reglas globales de orden (pedido de Erika, 22/10/2026 18:13)
//
// 1. Ítem: toda tabla de datos lleva una primera columna "Ítem" (1, 2, 3...) para poder decir
//    "revisa el ítem 5" en vez de dictar un número de documento largo. Se numera lo que se ve, en orden.
//    No se toca: tablas dentro de ventanas (modales), tablas donde se escribe (con casillas de texto o listas)
//    y tablas marcadas con data-sin-item.
// 2. Ayudas cortas: los textos de explicación largos muestran solo la primera frase y un botón "ⓘ Ver más"
//    que despliega el resto en el mismo lugar (no se esconde en otra pantalla).
(function () {
    if (window.__ordenPantallas) return;
    window.__ordenPantallas = true;

    // ---------- 1. Columna Ítem ----------
    const YA_NUMERADA = /^(#|ítems?|items?|n°|nº|no\.?)$/i;  // "Items" también (Erika 26/10/2026: salía doble)

    function editable(tabla) {
        // Una lista desplegable sola (p. ej. "quién recoge" en Recibir mercadería) no la vuelve tabla de escribir (26/10/2026)
        return !!tabla.querySelector('tbody input:not([type=checkbox]):not([type=radio]):not([type=hidden]), tbody textarea');
    }

    function aplica(tabla) {
        if (tabla.dataset.sinItem !== undefined || tabla.closest('[data-sin-item], .modal, .modal-content, [role=dialog], .no-print')) return false;
        const cab = tabla.tHead;
        if (!cab || !cab.rows.length || !cab.rows[0].cells.length) return false;
        if (tabla.dataset.item === 'si') {
            if (!editable(tabla)) return true;
            // Se volvió tabla de escribir: se quita la columna Ítem puesta antes para que no queden columnas corridas
            tabla.querySelectorAll('[data-item]').forEach(c => { if (c.dataset.item === 'span') { c.colSpan = Math.max(1, c.colSpan - 1); delete c.dataset.item; } else c.remove(); });
            delete tabla.dataset.item;
            tabla.classList.remove('con-item');
            return false;
        }
        const primera = cab.rows[0].cells[0];
        if (YA_NUMERADA.test((primera.textContent || '').trim())) {
            // Ya tiene su numeración (#, Item, N°): solo se le pone el mismo nombre en todo el sistema
            if (primera.textContent.trim() !== 'Ítem' && !primera.children.length) primera.textContent = 'Ítem';
            return false;
        }
        return !editable(tabla);
    }

    function filaDeAviso(tr, columnas) {
        // "Cargando...", "No hay datos", detalle desplegado: una sola celda que ocupa toda la fila
        return tr.cells.length === 1 && (tr.cells[0].colSpan > 1 || columnas <= 1);
    }

    function numerar(tabla) {
        if (!aplica(tabla)) return;
        const cab = tabla.tHead;
        if (tabla.dataset.item !== 'si') {
            tabla.dataset.item = 'si';
            tabla.classList.add('con-item');
        }
        const filaCab = cab.rows[0];
        if (!filaCab.querySelector(':scope > [data-item]')) {
            const th = document.createElement('th');
            th.dataset.item = '1';
            th.className = 'col-item';
            th.textContent = 'Ítem';
            if (cab.rows.length > 1) th.rowSpan = cab.rows.length;
            filaCab.insertBefore(th, filaCab.firstChild);
        }
        const columnas = Array.from(filaCab.cells).reduce((s, c) => s + (c.colSpan || 1), 0);
        let n = 0;
        Array.from(tabla.tBodies).forEach(cuerpo => {
            Array.from(cuerpo.rows).forEach(tr => {
                const marcada = tr.cells[0] && tr.cells[0].dataset.item;
                if (marcada === 'span') return;
                if (!marcada && filaDeAviso(tr, columnas - 1)) {
                    tr.cells[0].colSpan = (tr.cells[0].colSpan || 1) + 1;
                    tr.cells[0].dataset.item = 'span';
                    return;
                }
                let td = marcada ? tr.cells[0] : null;
                if (!td) {
                    td = document.createElement('td');
                    td.dataset.item = '1';
                    td.className = 'col-item';
                    tr.insertBefore(td, tr.firstChild);
                }
                const visible = !tr.hidden && tr.style.display !== 'none';
                const txt = visible ? String(++n) : '';
                if (td.textContent !== txt) td.textContent = txt;
            });
        });
        if (tabla.tFoot) {
            Array.from(tabla.tFoot.rows).forEach(tr => {
                if (tr.cells[0] && tr.cells[0].dataset.item) return;
                const td = document.createElement('td');
                td.dataset.item = 'pie';
                td.className = 'col-item';
                tr.insertBefore(td, tr.firstChild);
            });
        }
    }

    // ---------- 2. Ayudas cortas con "ⓘ Ver más" ----------
    const AYUDAS = '.inv-help, .panel-help, .hr-help, .ge-sub, .fin-help, .help-box, .mini-help';
    const LARGO = 110;

    function primeraFrase(texto) {
        const m = texto.match(/^.{20,}?[.:!?](\s|$)/);
        let corta = m ? m[0].trim() : texto;
        if (corta.length > LARGO) corta = corta.slice(0, LARGO).replace(/\s+\S*$/, '') + '…';
        return corta;
    }

    function compactar(el) {
        if (el.dataset.ayuda) return;
        const texto = (el.textContent || '').replace(/\s+/g, ' ').trim();
        if (texto.length <= LARGO || el.querySelector('input, select, button, textarea')) { el.dataset.ayuda = 'corta'; return; }
        el.dataset.ayuda = 'larga';
        const completo = el.innerHTML;
        const corta = primeraFrase(texto);
        if (corta.length >= texto.length - 5) { el.dataset.ayuda = 'corta'; return; }
        const pintar = abierta => {
            el.innerHTML = (abierta ? completo : escapar(corta)) +
                ` <button type="button" class="ayuda-mas" aria-expanded="${abierta}">${abierta ? 'ⓘ Ver menos' : 'ⓘ Ver más'}</button>`;
            el.querySelector('.ayuda-mas').onclick = e => { e.preventDefault(); e.stopPropagation(); pintar(!abierta); };
        };
        pintar(false);
    }

    function escapar(s) {
        return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }

    // ---------- Pasada sobre la pantalla (también lo que se dibuja después) ----------
    let pendiente = false;
    function pasar() {
        pendiente = false;
        try {
            document.querySelectorAll('table').forEach(numerar);
            document.querySelectorAll(AYUDAS).forEach(compactar);
        } catch (e) {
            if (window.registrarErrorConsola) window.registrarErrorConsola('Orden de pantallas', e.message, e.stack || '');
        }
    }
    function programar() {
        if (pendiente) return;
        pendiente = true;
        requestAnimationFrame(pasar);
    }
    window.numerarTablas = pasar;

    function iniciar() {
        pasar();
        new MutationObserver(muts => {
            // Solo vuelve a pasar si cambió algo que no es la propia columna Ítem
            for (const m of muts) {
                if (m.type === 'childList' && !(m.target.dataset && m.target.dataset.item)) { programar(); return; }
                // Filtros que esconden filas: se vuelve a numerar lo que se ve
                if (m.type === 'attributes' && m.target.tagName === 'TR') { programar(); return; }
            }
        }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['hidden', 'style'] });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
    else iniciar();
})();
