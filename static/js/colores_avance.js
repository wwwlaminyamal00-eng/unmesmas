// static/js/colores_avance.js
// REGLA DE ORO de colores por avance (Erika, 26/10/2026), igual en TODOS los módulos:
//   100% (pagado, entregado, cerrado, atendido…)  -> AZUL ELÉCTRICO
//    80% (despachado, aprobado, emitido…)          -> VERDE FLUORESCENTE
//    50% (pago parcial, en preparación…)           -> AMARILLO
//  0-25% (pendiente, por despachar, borrador…)     -> ROJO
// Se aplica por el TEXTO del estado, así cubre las pastillas de cada módulo sin tocar cada pantalla.
(function () {
    'use strict';
    const NIVELES = {
        'av-100': ['pagado', 'pagada', 'cobrado', 'cobrada', 'entregado', 'entregada', 'cerrado', 'cerrada',
            'completado', 'completada', 'completo', 'completa', 'atendido', 'atendida', 'pv atendido', 'pc atendido',
            'recibido', 'recibida', 'recibido completo', 'recibida completa', 'facturado', 'facturada', 'conciliado',
            'conciliada', 'finalizado', 'finalizada', 'terminado', 'terminada', 'cumplido', 'pagado total',
            'liquidado', 'liquidada', 'rendido', 'rendida', 'devuelto', 'stock completo', 'cubierto', 'oc ya generada', 'en portal', 'subido al portal', 'comprado', 'compra completa',
            'stock asignado', 'en stock', 'comprado en stock',
            // Erika 27/10/2026: la cotización aceptada por el cliente está cerrada al 100% -> azul eléctrico
            'aceptada por cliente', 'aceptado por cliente', 'aceptada por el cliente'],
        'av-80': ['despachado', 'despachada', 'aprobado', 'aprobada', 'emitido', 'emitida', 'aceptado', 'aceptada',
            'aceptada en credito', 'pv conforme', 'pc conforme', 'conforme', 'validado', 'validada', 'listo', 'lista',
            'en camino', 'en transito', 'enviado', 'enviada', 'registrado', 'registrada', 'confirmado', 'confirmada',
            'ganada', 'ganado', 'oc generada', 'por entregar', 'con cita', 'en compra', 'oc emitida',
            'oc enviada', 'compra generada', 'comprado por llegar', 'comprado por recoger'],
        'av-50': ['pago parcial', 'parcial', 'cobro parcial', 'parcialmente pagado', 'pagado parcial', 'en preparacion',
            'en proceso', 'en revision', 'recibido parcial', 'recibida parcial', 'entrega parcial', 'despacho parcial',
            'atendido parcial', 'en curso', 'a medias', 'stock parcial', 'en negociacion', 'seguimiento', 'compra parcial'],
        'av-0': ['pendiente', 'pendientes', 'por despachar', 'pendiente despacho', 'pendiente de despacho', 'borrador',
            'por pagar', 'por cobrar', 'vencido', 'vencida', 'pv observado', 'pc observado', 'observado', 'observada',
            'rechazado', 'rechazada', 'rechazado por el cliente', 'por aprobar', 'pendiente de aprobacion', 'sin pagar',
            'falta pagar', 'falta cobrar', 'por comprar', 'sin stock', 'por recibir', 'no pagado', 'impago',
            'por hacer', 'sin cita', 'pendiente de pago', 'pendiente de cobro', 'por facturar', 'sin facturar', 'por validar',
            'falta migo', 'falta portal', 'falta xml', 'pendiente de compra',
            'compra pendiente']
    };
    const MAPA = new Map();
    Object.entries(NIVELES).forEach(([clase, lista]) => lista.forEach(t => MAPA.set(t, clase)));
    const CLAVES = [...MAPA.keys()].sort((a, b) => b.length - a.length);

    const norm = t => (t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
        .replace(/[^a-z0-9ñ\s]/g, ' ').replace(/\s+/g, ' ').trim();

    function nivelDe(texto) {
        const n = norm(texto);
        if (!n || n.length > 40) return null;
        if (MAPA.has(n)) return MAPA.get(n);
        for (const k of CLAVES) {
            // "Despachado 26/10/2026" o "Pago parcial S/ 50": el resto no puede tener otra palabra
            if (n.startsWith(k + ' ') && !/[a-zñ]{3,}/.test(n.slice(k.length).replace(/\bs\b/g, ''))) return MAPA.get(k);
        }
        return null;
    }

    const SELECTOR = '.badge, .badge-estado, .badge-val, [class*="estado"], [class*="chip"], [class*="pill"], ' +
        '[class*="desp-"], .status-badge, .estado-badge, .tag-estado, .compra-est';
    const PROHIBIDO = 'button, input, select, option, textarea, label, th, h1, h2, h3, h4, a.btn, .btn, .tab-btn, .nav-link, ' +
        '.status-card, .status-board, .master-status-card, .kpi, [class*="status-filter"]';

    function pintar(el) {
        if (!(el instanceof HTMLElement) || el.matches(PROHIBIDO) || el.closest('button, select, .btn, th, .modal-foot')) return;
        if (el.children.length > 3) return;
        const clase = nivelDe(el.textContent);
        el.classList.remove('av-100', 'av-80', 'av-50', 'av-0');
        if (clase) el.classList.add('av-pill', clase);
        else el.classList.remove('av-pill');
    }
    function recorrer(raiz) {
        if (!raiz || !raiz.querySelectorAll) return;
        if (raiz.matches && raiz.matches(SELECTOR)) pintar(raiz);
        raiz.querySelectorAll(SELECTOR).forEach(pintar);
    }

    let pendientes = new Set(), programado = false;
    function procesar() {
        programado = false;
        const lista = [...pendientes]; pendientes.clear();
        lista.forEach(recorrer);
    }
    function encolar(n) {
        pendientes.add(n.nodeType === 3 ? n.parentElement : n);
        if (!programado) { programado = true; requestAnimationFrame(procesar); }
    }
    function iniciar() {
        recorrer(document.body);
        new MutationObserver(muts => muts.forEach(m => {
            if (m.type === 'characterData') encolar(m.target);
            m.addedNodes.forEach(n => (n.nodeType === 1 || n.nodeType === 3) && encolar(n.nodeType === 3 ? n : (n.parentElement || n)));
        })).observe(document.body, { childList: true, subtree: true, characterData: true });
    }
    window.nivelAvance = nivelDe;
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar); else iniciar();
})();
