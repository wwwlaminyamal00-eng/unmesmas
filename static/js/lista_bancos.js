// lista_bancos.js - Banco siempre elegido de una lista (pedido de Erika, 22/10/2026)
// "Si no, lo van a escribir con diferentes formas y va a generar una observación."
// Todo campo con data-lista="bancos" (input o select) se vuelve un desplegable con la misma lista
// (la misma de utils.BANCOS_PERU). Si un registro antiguo trae "bcp " o "Banco de Crédito", se muestra como "BCP".
// "Otro (escribir)" pide el nombre una sola vez y lo agrega a la lista.
(function () {
    'use strict';
    const BANCOS = ['BCP', 'BBVA', 'Interbank', 'Scotiabank', 'BanBif', 'Banco de la Nación', 'Pichincha', 'MiBanco',
        'Banco GNB', 'Banco Falabella', 'Banco Ripley', 'Caja Arequipa', 'Caja Huancayo', 'Caja Piura',
        'Caja Cusco', 'Caja Trujillo', 'Caja Sullana', 'Caja Municipal de Lima'];
    const ALIAS = [['credito', 'BCP'], ['bcp', 'BCP'], ['bbva', 'BBVA'], ['continental', 'BBVA'], ['interbank', 'Interbank'],
        ['ibk', 'Interbank'], ['scotia', 'Scotiabank'], ['banbif', 'BanBif'], ['interamericano', 'BanBif'],
        ['nacion', 'Banco de la Nación'], ['bn', 'Banco de la Nación'], ['pichincha', 'Pichincha'], ['mibanco', 'MiBanco'],
        ['gnb', 'Banco GNB'], ['falabella', 'Banco Falabella'], ['ripley', 'Banco Ripley'], ['arequipa', 'Caja Arequipa'],
        ['huancayo', 'Caja Huancayo'], ['piura', 'Caja Piura'], ['cusco', 'Caja Cusco'], ['trujillo', 'Caja Trujillo'],
        ['sullana', 'Caja Sullana'], ['lima', 'Caja Municipal de Lima']];
    const OTRO = '__otro__';
    const desc = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value');

    function normalizar(texto) {
        const original = String(texto || '').replace(/\s+/g, ' ').trim();
        if (!original) return '';
        const t = original.normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase();
        const palabras = new Set(t.match(/[a-z]+/g) || []);
        for (const [clave, nombre] of ALIAS) {
            if (palabras.has(clave) || (clave.length > 3 && t.includes(clave))) return nombre;
        }
        return original.slice(0, 80);
    }
    window.normalizarBanco = normalizar;
    window.BANCOS_PERU = BANCOS.slice();

    function poner(sel, valor) {
        const v = normalizar(valor);
        if (v && !Array.from(sel.options).some(o => o.value === v)) {
            const o = new Option(v, v);
            sel.insertBefore(o, sel.querySelector(`option[value="${OTRO}"]`));
        }
        desc.set.call(sel, v);
    }

    function convertir(el) {
        if (el.dataset.listaLista) return;
        let sel = el;
        const valor = el.value;
        if (el.tagName !== 'SELECT') {
            sel = document.createElement('select');
            for (const a of el.attributes) {
                if (!['type', 'maxlength', 'placeholder', 'value', 'list', 'autocomplete'].includes(a.name)) sel.setAttribute(a.name, a.value);
            }
            el.replaceWith(sel);
        }
        sel.dataset.listaLista = '1';
        sel.innerHTML = '<option value="">Elige el banco</option>' + BANCOS.map(b => `<option value="${b}">${b}</option>`).join('')
            + `<option value="${OTRO}">Otro (escribir)</option>`;
        // Los formularios ponen el valor con .value = '...': se normaliza y, si es un banco nuevo, se agrega
        Object.defineProperty(sel, 'value', {
            configurable: true,
            get() { const v = desc.get.call(this); return v === OTRO ? '' : v; },
            set(v) { poner(this, v); }
        });
        poner(sel, valor);
        sel.addEventListener('change', () => {
            if (desc.get.call(sel) !== OTRO) return;
            const nombre = window.prompt('Escribe el nombre del banco o caja:');
            poner(sel, nombre || '');
        });
    }

    function aplicar(raiz) {
        (raiz || document).querySelectorAll('[data-lista="bancos"]').forEach(convertir);
    }
    window.aplicarListaBancos = aplicar;
    function iniciar() {
        aplicar(document);
        new MutationObserver(cambios => {
            for (const c of cambios) for (const n of c.addedNodes) {
                if (n.nodeType !== 1) continue;
                if (n.matches && n.matches('[data-lista="bancos"]')) convertir(n);
                else if (n.querySelector && n.querySelector('[data-lista="bancos"]')) aplicar(n);
            }
        }).observe(document.body, { childList: true, subtree: true });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
    else iniciar();
})();
