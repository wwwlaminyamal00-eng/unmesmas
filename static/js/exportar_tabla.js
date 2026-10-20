// static/js/exportar_tabla.js - Botón "Exportar" de todas las pantallas (pedido de Erika 19/10/2026)
// Exporta a Excel (.xlsx) la tabla que está a la vista, con los filtros y la búsqueda que estén puestos
// (solo las filas visibles), los mismos nombres de columna de la pantalla y la fecha/hora de Lima.
// Uso: exportarTabla(botón o tabla, 'Título'). exportData('cotizaciones') y bdExportarExcel() lo usan.
(function () {
    'use strict';

    // Nombres claros para los módulos que llaman a exportData('...')
    var TITULOS = {
        cotizaciones: 'Ventas - Cotizaciones', pedido_compra: 'Ventas - Pedidos de compra (PC)',
        validacion: 'Ventas - Validación de PC', despachos: 'Ventas - Despachos', guias: 'Ventas - Guías de remisión',
        comprobantes: 'Ventas - Facturas y boletas', notas_credito: 'Ventas - Notas de crédito',
        devoluciones: 'Ventas - Devoluciones', eliminadas: 'Ventas - Cotizaciones eliminadas', revision: 'Ventas - Revisión',
        solicitud_compra: 'Compras - Solicitudes de compra', comparativo: 'Compras - Cuadros comparativos',
        orden_compra: 'Compras - Órdenes de compra', comprobante_proveedor: 'Compras - Facturas de proveedor',
        recepcion: 'Compras - Recepciones', productos: 'Productos'
    };
    var COLUMNAS_FUERA = /^(acciones?|opciones|acción|ver|editar|\s*)$/i;

    function visible(el) {
        return !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length)) &&
            getComputedStyle(el).visibility !== 'hidden';
    }

    function texto(el) {
        if (!el) return '';
        var campos = el.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, textarea');
        if (campos.length === 1 && !el.innerText.trim()) {
            var c = campos[0];
            return c.tagName === 'SELECT' ? (c.options[c.selectedIndex] || {}).text || '' : c.value;
        }
        return (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
    }

    function tablasVisibles(raiz) {
        return Array.prototype.filter.call((raiz || document).querySelectorAll('table'), function (t) {
            return visible(t) && t.querySelector('th, thead td') && !t.closest('.modal-bg:not(.show), .modal:not(.show)');
        });
    }

    function filasDe(t) {
        return t.tBodies.length ? Array.prototype.reduce.call(t.tBodies, function (a, b) { return a.concat(Array.prototype.slice.call(b.rows)); }, [])
            : Array.prototype.slice.call(t.rows, 1);
    }

    // Busca la tabla más cercana al botón (subiendo por la pantalla); si no, la más grande que se vea.
    function tablaDesde(origen) {
        if (origen && origen.tagName === 'TABLE') return origen;
        if (typeof origen === 'string') return document.querySelector(origen);
        var n = origen && origen.parentElement;
        while (n && n !== document.body) {
            var ts = tablasVisibles(n);
            if (ts.length) return ts.sort(function (a, b) { return filasDe(b).length - filasDe(a).length; })[0];
            n = n.parentElement;
        }
        var todas = tablasVisibles(document);
        return todas.sort(function (a, b) { return filasDe(b).length - filasDe(a).length; })[0] || null;
    }

    function leerTabla(t) {
        var filasEnc = t.tHead ? t.tHead.rows : [t.rows[0]];
        var enc = filasEnc[filasEnc.length - 1];
        var celdasEnc = Array.prototype.slice.call(enc.cells);
        var usar = [], columnas = [];
        celdasEnc.forEach(function (c, i) {
            var nombre = texto(c).replace(/[↑↓⇅▲▼]/g, '').trim();
            if (c.querySelector('input[type=checkbox]') && !nombre) return;
            if (COLUMNAS_FUERA.test(nombre)) return;
            usar.push(i);
            columnas.push(nombre);
        });
        var filas = [];
        filasDe(t).forEach(function (tr) {
            if (!visible(tr) || tr.closest('thead')) return;
            if (tr.cells.length === 1 && tr.cells[0].colSpan > 1) return;   // "No hay datos", "Cargando..."
            filas.push(usar.map(function (i) { return tr.cells[i] ? texto(tr.cells[i]) : ''; }));
        });
        return { columnas: columnas, filas: filas };
    }

    // Filtros puestos en la misma pantalla (buscador, fechas, estado...), para anotarlos en el Excel
    function filtrosCerca(t) {
        var zona = t, salto = 0;
        while (zona.parentElement && salto < 5 && zona.parentElement !== document.body) { zona = zona.parentElement; salto++; }
        var out = [];
        zona.querySelectorAll('input, select').forEach(function (el) {
            if (t.contains(el) || !visible(el) || el.id === 'empresaActiva' || el.closest('.modal-bg, .modal, form[id$="Form"], nav, aside')) return;
            if (/^(hidden|checkbox|radio|button|submit|file)$/i.test(el.type || '')) return;
            var v = el.tagName === 'SELECT' ? ((el.options[el.selectedIndex] || {}).text || '') : el.value;
            if (!String(v).trim() || (el.tagName === 'SELECT' && el.selectedIndex === 0 && /todo|todas|todos|--|selecc/i.test(v))) return;
            var lab = el.getAttribute('aria-label') || el.placeholder || '';
            if (!lab && el.id) { var l = document.querySelector('label[for="' + el.id + '"]'); if (l) lab = texto(l); }
            if (!lab && el.closest('label')) lab = texto(el.closest('label')).replace(v, '').trim();
            out.push([(lab || el.name || el.id || 'Filtro').slice(0, 60), String(v).slice(0, 120)]);
        });
        return out.slice(0, 20);
    }

    function aviso(msg, tipo) {
        if (typeof window.showToast === 'function') return window.showToast(msg, tipo || 'info');
        if (typeof window.mostrarNotificacion === 'function') return window.mostrarNotificacion(tipo || 'info', 'Exportar', msg);
        if (tipo === 'error' || tipo === 'warning') alert(msg);
    }

    function tituloPantalla(t) {
        var tab = document.querySelector('.tab-btn.active[data-tab], .tab-btn.active, .tab.active, .child-btn.active, [aria-selected="true"]');
        var h = document.querySelector('h1, .page-title, .header-title');
        return [h && texto(h), tab && texto(tab)].filter(Boolean).join(' - ').slice(0, 70) || document.title || 'Datos';
    }

    async function exportarTabla(origen, titulo) {
        var t = tablaDesde(origen);
        if (!t) { aviso('⚠️ No hay ninguna tabla a la vista para exportar.', 'warning'); return; }
        var datos = leerTabla(t);
        if (!datos.filas.length) { aviso('⚠️ La tabla está vacía: no hay nada para exportar con estos filtros.', 'warning'); return; }
        aviso('⏳ Preparando el Excel (' + datos.filas.length + ' filas)...', 'info');
        try {
            var r = await fetch('/api/exportar/tabla', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
                body: JSON.stringify({ titulo: titulo || tituloPantalla(t), columnas: datos.columnas, filas: datos.filas, filtros: filtrosCerca(t) })
            });
            if (!r.ok) {
                var e = {}; try { e = await r.json(); } catch (x) { }
                throw new Error(e.error || ('Error ' + r.status));
            }
            var nombre = r.headers.get('X-Nombre-Archivo') || 'exportacion.xlsx';
            var blob = await r.blob();
            var a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = nombre;
            document.body.appendChild(a);
            a.click();
            setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 2000);
            aviso('✅ Descargado: ' + nombre, 'success');
        } catch (err) {
            aviso('❌ No se pudo exportar: ' + err.message, 'error');
        }
    }

    function botonDelEvento() {
        var ev = window.event;
        return ev && ev.target && ev.target.closest ? ev.target.closest('button, a') : null;
    }

    // Pantallas con pestañas y sin botón Exportar propio (Maestros/Proveedores, Inventario, Compras, Finanzas,
    // Reportes, Papelera...): se agrega "⬇ Exportar Excel" al final de la fila de pestañas. Exporta la tabla
    // de la pestaña abierta, con sus filtros.
    function agregarBotonEnPestanas() {
        if (document.querySelector('[onclick*="exportData"], [onclick*="bdExportarExcel"], [onclick*="ccExportarCSV"], .exp-tab-btn')) return;
        var barra = Array.prototype.find.call(document.querySelectorAll('.tabs'), function (x) { return x.querySelector('.tab-btn[data-tab]'); });
        if (!barra) return;
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'btn btn-secondary exp-tab-btn';
        b.textContent = '⬇ Exportar Excel';
        b.title = 'Descarga en Excel la tabla que estás viendo, con los filtros puestos';
        b.style.cssText = 'margin-left:auto;white-space:nowrap;font-weight:800;';
        b.addEventListener('click', function () {
            var activa = barra.querySelector('.tab-btn.active');
            var h = document.querySelector('h1, .page-title, .header-title');
            var titulo = [h && texto(h), activa && texto(activa)].filter(Boolean).join(' - ').replace(/[^\wÁÉÍÓÚÜÑáéíóúüñ° ()\-\/]/g, '').replace(/\s+/g, ' ').trim();
            exportarTabla(barra, titulo || null);
        });
        barra.appendChild(b);
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', agregarBotonEnPestanas);
    else agregarBotonEnPestanas();

    window.exportarTabla = exportarTabla;
    window.exportarModulo = function (modulo) { return exportarTabla(botonDelEvento(), TITULOS[modulo] || null); };
    window.exportData = window.exportarModulo;
    // Productos se ve por páginas: se pintan TODAS las filas filtradas un momento, se exporta y se vuelve a la página
    window.bdExportarExcel = async function () {
        var boton = botonDelEvento();
        var paginado = typeof window.bdRenderProductos === 'function' && Array.isArray(window.bdProductosFiltrados);
        var pp = window.bdPorPagina, pa = window.bdPaginaActual;
        if (paginado) { window.bdPorPagina = 100000; window.bdPaginaActual = 1; window.bdRenderProductos(window.bdProductosFiltrados); }
        try { await exportarTabla(boton, 'Productos'); }
        finally { if (paginado) { window.bdPorPagina = pp; window.bdPaginaActual = pa; window.bdRenderProductos(window.bdProductosFiltrados); } }
    };
})();
