// monitor_consola.js - Monitor de errores en la consola de Chrome (F12) (pedido de Erika, 22/10/2026)
//
// Abre F12 ▸ Consola y cada error aparece en ROJO con lo que falló:
//   1. Errores de JavaScript de la pantalla (archivo, línea y mensaje).
//   2. Promesas que fallaron sin que nadie las atienda.
//   3. Guardados o consultas al servidor (/api/...) que respondieron con error o con success:false,
//      con el método, la ruta, el código HTTP y el mensaje exacto del servidor.
//   4. Lo que se muestra en la ventana roja de "No se pudo guardar".
//   5. Archivos (scripts, estilos, imágenes) que no cargaron.
// Escribe en la consola erpErrores() para ver la lista de todos los errores de esta pantalla.
(function () {
    if (window.__monitorConsola) return;
    window.__monitorConsola = true;

    const ESTILO_TITULO = 'background:#DC2626;color:#fff;font-weight:900;font-size:14px;padding:4px 10px;border-radius:4px';
    const ESTILO_TEXTO = 'color:#B91C1C;font-weight:700;font-size:13px';
    const ESTILO_OK = 'background:#16A34A;color:#fff;font-weight:700;padding:2px 8px;border-radius:4px';
    const lista = [];
    // Al cambiar de pantalla el navegador corta las consultas que estaban cargando: eso no es un error
    let saliendo = false;
    window.addEventListener('beforeunload', function () { saliendo = true; });
    window.addEventListener('pagehide', function () { saliendo = true; });

    function hora() {
        try {
            return new Date().toLocaleTimeString('es-PE', { timeZone: 'America/Lima', hour12: false });
        } catch (e) { return new Date().toLocaleTimeString(); }
    }

    function registrar(tipo, mensaje, detalle) {
        const item = { hora: hora(), tipo: tipo, mensaje: String(mensaje || 'Error desconocido'), detalle: detalle || '', pantalla: location.pathname };
        lista.push(item);
        if (lista.length > 200) lista.shift();
        try {
            console.error('%c⛔ ERP · ' + tipo + ' (' + item.hora + ')%c\n' + item.mensaje + (item.detalle ? '\n↳ ' + item.detalle : ''),
                ESTILO_TITULO, ESTILO_TEXTO);
        } catch (e) { /* nada */ }
    }
    window.registrarErrorConsola = registrar;
    window.erpErrores = function () {
        if (!lista.length) { console.log('%c✔ Sin errores en esta pantalla', ESTILO_OK); return []; }
        console.table(lista);
        return lista.slice();
    };

    // 1 y 5. Errores de JavaScript y archivos que no cargaron (fase de captura para ver los <script>/<img> rotos)
    window.addEventListener('error', function (ev) {
        const t = ev.target;
        if (t && t !== window && (t.src || t.href)) {
            const ruta = t.src || t.href;
            const externo = ruta.indexOf(location.origin) !== 0;
            registrar('No cargó un archivo', (t.tagName || '').toLowerCase() + ': ' + ruta,
                externo ? 'Es un archivo de internet (letras o íconos): revisa la conexión; el sistema sigue funcionando.'
                        : 'Si es un .js o .css del ERP, puede que en Render esté un ZIP incompleto o antiguo.');
            return;
        }
        const donde = ev.filename ? ev.filename.replace(location.origin, '') + ':' + ev.lineno + ':' + ev.colno : '';
        registrar('Error de JavaScript', ev.message, donde + (ev.error && ev.error.stack ? '\n' + ev.error.stack : ''));
    }, true);

    // 2. Promesas sin atender
    window.addEventListener('unhandledrejection', function (ev) {
        const r = ev.reason;
        registrar('Error sin atender', (r && r.message) || String(r), (r && (r.detalle || r.stack)) || '');
    });

    // 3. Respuestas con error del servidor (se envuelve el fetch ya preparado por errores_guardado.js)
    if (window.fetch) {
        const fetchPrevio = window.fetch;
        window.fetch = async function (recurso, opciones) {
            const url = typeof recurso === 'string' ? recurso : (recurso && recurso.url) || '';
            const metodo = String((opciones && opciones.method) || (recurso && recurso.method) || 'GET').toUpperCase();
            const esApi = url.indexOf('/api/') !== -1 && url.indexOf('/api/diagnostico/') === -1;
            let r;
            try {
                r = await fetchPrevio.apply(window, arguments);
            } catch (e) {
                if (esApi && !saliendo) registrar(metodo === 'GET' ? 'Falló una consulta' : 'No se pudo guardar', metodo + ' ' + url + ' → ' + (e.message || e), e.detalle || '');
                throw e;
            }
            if (esApi) {
                const tipo = r.headers.get('Content-Type') || '';
                if (!r.ok || tipo.indexOf('application/json') !== -1) {
                    r.clone().json().then(function (j) {
                        if (!r.ok || (j && j.success === false)) {
                            registrar(metodo === 'GET' ? 'Falló una consulta' : 'No se pudo guardar',
                                metodo + ' ' + url + ' → HTTP ' + r.status + ': ' + ((j && (j.error || j.message || j.mensaje)) || 'sin mensaje'),
                                (j && j.detalle) || '');
                        }
                    }).catch(function () {
                        if (!r.ok) registrar('Error del servidor', metodo + ' ' + url + ' → HTTP ' + r.status, '');
                    });
                }
            }
            return r;
        };
    }

    // 4. Lo que aparece en la ventana roja
    function envolverVentana() {
        const original = window.mostrarErrorGuardado;
        if (typeof original !== 'function' || original.__monitor) return;
        const envuelta = function (titulo, mensaje, detalle) {
            registrar('Ventana roja: ' + (titulo || 'No se pudo guardar'), mensaje, detalle);
            return original.apply(this, arguments);
        };
        envuelta.__monitor = true;
        window.mostrarErrorGuardado = envuelta;
    }
    envolverVentana();
    document.addEventListener('DOMContentLoaded', envolverVentana);

    try {
        console.log('%c✔ Monitor de errores del ERP activo%c  Los errores saldrán aquí en rojo. Escribe erpErrores() para ver la lista.',
            ESTILO_OK, 'color:#166534;font-weight:600');
    } catch (e) { /* nada */ }
})();
