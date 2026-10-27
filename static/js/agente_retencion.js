// static/js/agente_retencion.js
// "Agente de retención: Sí / No" del cliente en la factura (Erika, 27/10/2026 20:34).
// Se consulta solo en el padrón de SUNAT. Si el cliente NO es agente, la factura no lleva retención (el botón queda
// bloqueado); si SÍ es, la retención se activa sola. Si SUNAT no responde, un aprobador lo marca a mano.
(function () {
    'use strict';
    const $ = id => document.getElementById(id);
    const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const st = { ruc: '', dato: null, cargando: false };

    function caja() {
        const label = $('retencionStatusLabel');
        const sec = label && label.closest('.ficha-section');
        if (!sec) return null;
        let c = $('agenteRetBox');
        if (!c) {
            c = document.createElement('div');
            c.id = 'agenteRetBox';
            const titulo = sec.querySelector('.ficha-section-title');
            if (titulo && titulo.nextSibling) sec.insertBefore(c, titulo.nextSibling); else sec.appendChild(c);
        }
        return c;
    }

    function retencionActiva() {
        const content = $('retencionContent');
        return !!content && content.style.display !== 'none';
    }

    function aplicar() {
        const d = st.dato;
        const btn = $('btnToggleRetencion');
        if (!btn || !d) return;
        if (d.agente === false) {
            if (retencionActiva() && typeof toggleRetencion === 'function') toggleRetencion();
            btn.disabled = true;
            btn.style.opacity = '0.45';
            btn.title = 'El cliente NO es agente de retención: esta factura no lleva retención';
        } else {
            btn.disabled = false;
            btn.style.opacity = '';
            btn.title = '';
            if (d.agente === true && !retencionActiva() && typeof toggleRetencion === 'function') toggleRetencion();
        }
        if (typeof actualizarEstadoRetencion === 'function') actualizarEstadoRetencion();
    }

    function pintar() {
        const c = caja();
        if (!c) return;
        const d = st.dato;
        if (!st.ruc) { c.innerHTML = ''; return; }
        if (st.cargando) { c.className = 'agret agret-nd'; c.innerHTML = '⏳ Consultando en SUNAT si el cliente es agente de retención…'; return; }
        if (!d) { c.innerHTML = ''; return; }
        const clase = d.agente === true ? 'agret-si' : d.agente === false ? 'agret-no' : 'agret-nd';
        const valor = d.agente === true ? 'SÍ' : d.agente === false ? 'NO' : 'Sin dato';
        const fuente = d.fuente === 'SUNAT' ? `Padrón SUNAT${d.desde ? ' (desde ' + esc(d.desde) + ')' : ''}`
            : d.fuente === 'Manual' ? `Marcado a mano${d.revisado_por ? ' por ' + esc(d.revisado_por) : ''}` : '';
        const efecto = d.agente === true ? 'La factura lleva retención del 3% si pasa de S/ 700.'
            : d.agente === false ? 'Esta factura NO lleva retención.' : 'Consulta SUNAT o márcalo para saber si va retención.';
        c.className = 'agret ' + clase;
        c.innerHTML = `<span>Agente de retención: <b>${valor}</b></span>
            ${fuente ? `<small>${fuente}${d.revisado_en ? ' · revisado ' + esc(d.revisado_en) : ''}</small>` : ''}
            <small class="agret-efecto">${efecto}</small>
            ${d.aviso ? `<small class="agret-aviso">⚠ ${esc(d.aviso)}</small>` : ''}
            <span class="agret-botones">
                <button type="button" data-agret="sunat">🔄 Consultar SUNAT</button>
                <button type="button" data-agret="si">Marcar Sí</button>
                <button type="button" data-agret="no">Marcar No</button>
            </span>`;
    }

    async function cargar(forzar) {
        const ruc = ($('compRuc')?.value || '').replace(/\D/g, '');
        st.ruc = ruc.length === 11 ? ruc : '';
        st.dato = null;
        if (!st.ruc) { pintar(); return; }
        st.cargando = true; pintar();
        try {
            const r = await fetch(`/ventas/api/agente-retencion?ruc=${st.ruc}${forzar ? '&forzar=1' : ''}`, { credentials: 'same-origin' });
            const j = await r.json();
            if (st.ruc === ruc) st.dato = j.success ? j.data : null;
        } catch (e) { st.dato = { agente: null, aviso: 'No se pudo consultar.' }; }
        st.cargando = false;
        pintar();
        aplicar();
    }

    async function marcar(valor) {
        if (!st.ruc) return;
        if (!confirm(`¿Marcar a mano que el cliente ${valor ? 'SÍ' : 'NO'} es agente de retención? Queda en la auditoría.`)) return;
        try {
            const r = await fetch('/ventas/api/agente-retencion/manual', {
                method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ruc: st.ruc, agente: valor })
            });
            const j = await r.json();
            if (!j.success) { if (window.showToast) showToast('⚠️ ' + (j.error || 'No se pudo guardar'), 'error'); return; }
            st.dato = j.data;
            pintar();
            aplicar();
            if (window.showToast) showToast('✅ Guardado en el cliente', 'success');
        } catch (e) { if (window.showToast) showToast('⚠️ No se pudo guardar', 'error'); }
    }

    document.addEventListener('click', e => {
        const b = e.target && e.target.closest && e.target.closest('[data-agret]');
        if (!b) return;
        const a = b.dataset.agret;
        if (a === 'sunat') cargar(true); else marcar(a === 'si');
    });

    // El RUC de la factura se llena por código (desde el PV, la guía o la cotización): se revisa cada medio segundo
    let firma = '';
    setInterval(() => {
        const ruc = $('compRuc');
        if (!ruc || !ruc.offsetParent) { firma = ''; return; }
        const f = (ruc.value || '').replace(/\D/g, '') + '|' + (!!$('agenteRetBox'));
        if (f !== firma) { firma = f; cargar(false); }
    }, 600);
})();
