// static/js/distrito_pv.js
// "Distrito de entrega" en el formulario del PV (Erika, 27/10/2026 18:48 y 18:53). En las listas de PV y Entregas
// sale solo el distrito y nadie lo escribe allí: se llena solo con la dirección de entrega (que viene de la
// cotización aceptada) y, si la dirección no lo dice, se elige aquí. "🏬 Recoge en nuestro local": en las listas sale
// el distrito del local de la empresa (KCF: San Martín de Porres; AGD: Breña).
(function () {
    'use strict';
    const $ = id => document.getElementById(id);
    const TEXTO_RECOJO = 'Recoge el cliente en nuestro local';
    const ALIAS = { 'SMP': 'San Martín de Porres', 'S.M.P.': 'San Martín de Porres', 'CERCADO': 'Cercado de Lima', 'LIMA CERCADO': 'Cercado de Lima',
        'SURCO': 'Santiago de Surco', 'SJL': 'San Juan de Lurigancho', 'SJM': 'San Juan de Miraflores', 'VES': 'Villa El Salvador',
        'VMT': 'Villa María del Triunfo', 'MAGDALENA': 'Magdalena del Mar', 'CHOSICA': 'Lurigancho' };
    const norm = t => String(t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase();
    const esRecojo = t => /RECOJO|RECOG|EN TIENDA|EN ALMACEN|EN NUESTRO LOCAL|EN LOCAL|EN OFICINA/.test(norm(t));

    function mapa() {
        const m = {};
        (window.DISTRITOS_LIMA || (typeof DISTRITOS_LIMA !== 'undefined' ? DISTRITOS_LIMA : [])).forEach(d => { m[norm(d)] = d; });
        Object.entries(ALIAS).forEach(([a, d]) => { m[norm(a)] = d; });
        return m;
    }
    // Igual que en el servidor: el distrito suele ir al final, gana el último que aparece
    function adivinar(texto) {
        const m = mapa(), t = norm(texto);
        let mejor = '', pos = -1;
        Object.keys(m).forEach(k => {
            const re = new RegExp('(^|[^A-Z0-9])' + k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(?![A-Z0-9])', 'g');
            let r;
            while ((r = re.exec(t))) {
                const p = r.index + r[1].length;
                if (p > pos || (p === pos && k.length > norm(mejor).length)) { pos = p; mejor = m[k]; }
            }
        });
        return mejor;
    }

    function armar() {
        const ent = $('pcEntrega');
        if (!ent || $('pcDistrito')) return;
        const caja = document.createElement('div');
        caja.className = 'pv-dist-caja';
        caja.innerHTML = `<button type="button" class="pv-btn-recojo" title="El cliente viene a recoger: en las listas sale el distrito de nuestro local">🏬 Recoge en nuestro local</button>
            <label class="pv-dist-label">Distrito de entrega
                <input id="pcDistrito" list="listaDistritosPv" maxlength="80" placeholder="Se llena solo con la dirección" autocomplete="off"></label>
            <small id="pcDistritoAviso"></small>`;
        ent.insertAdjacentElement('afterend', caja);
        if (!$('listaDistritosPv')) {
            const dl = document.createElement('datalist');
            dl.id = 'listaDistritosPv';
            dl.innerHTML = Object.values(mapa()).filter((v, i, a) => a.indexOf(v) === i).map(d => `<option value="${d}"></option>`).join('');
            document.body.appendChild(dl);
        }
        caja.querySelector('.pv-btn-recojo').addEventListener('click', () => {
            ent.value = TEXTO_RECOJO;
            ent.dispatchEvent(new Event('input', { bubbles: true }));
            ent.dispatchEvent(new Event('change', { bubbles: true }));
            revisar(true);
        });
        $('pcDistrito').addEventListener('input', () => { $('pcDistrito').dataset.auto = ''; pintarAviso(); });
    }

    function pintarAviso() {
        const ent = $('pcEntrega'), dis = $('pcDistrito'), av = $('pcDistritoAviso');
        if (!ent || !dis || !av) return;
        if (esRecojo(ent.value)) {
            dis.value = ''; dis.disabled = true; dis.placeholder = 'Distrito de nuestro local';
            av.className = 'pv-dist-ok'; av.textContent = '🏬 El cliente recoge: sale el distrito de nuestro local (KCF: San Martín de Porres; AGD: Breña).';
            return;
        }
        dis.disabled = false; dis.placeholder = 'Se llena solo con la dirección';
        if (dis.value.trim()) { av.className = 'pv-dist-ok'; av.textContent = dis.dataset.auto ? '✅ Leído de la dirección de entrega' : '✅ Elegido en el PV'; }
        else { av.className = 'pv-dist-falta'; av.textContent = '⚠ No se lee el distrito en la dirección: elígelo aquí (si no, saldrá en rojo en PV y Entregas).'; }
    }

    let firma = '', abierto = false;
    function revisar(forzar) {
        const ent = $('pcEntrega');
        const visible = !!(ent && ent.offsetParent);
        if (!visible) { abierto = false; return; }
        armar();
        const dis = $('pcDistrito');
        if (!abierto) {   // se acaba de abrir el formulario: vacío para que se llene solo con la dirección
            abierto = true; firma = '';
            dis.value = ''; dis.dataset.auto = '1';
        }
        if (window._pvDistritoCargado !== undefined) {   // al editar: el distrito guardado en el PV
            const cargado = window._pvDistritoCargado;
            window._pvDistritoCargado = undefined;
            firma = '';
            dis.value = cargado || '';
            dis.dataset.auto = cargado ? '' : '1';
        }
        const f = ent.value;
        if (f !== firma || forzar) {
            firma = f;
            if (dis.dataset.auto || !dis.value.trim()) {
                const d = adivinar(f);
                if (d || dis.dataset.auto) { dis.value = d; dis.dataset.auto = '1'; }
            }
        }
        pintarAviso();
    }
    setInterval(() => revisar(false), 500);
    window.adivinarDistritoPv = adivinar;
})();
