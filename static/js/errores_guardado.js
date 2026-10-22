// errores_guardado.js - Ningún guardado falla en silencio (pedido urgente de Erika, 22/10/2026)
//
// Por qué "no hacía nada": cuando el servidor no contestaba con un mensaje del ERP (Render dormido o reiniciado,
// sesión vencida, error 500 en HTML, sin internet), la pantalla intentaba leer la respuesta, fallaba por dentro
// y no mostraba nada, o mostraba un aviso pequeño que se iba solo. Este archivo, cargado en todas las pantallas:
//   1. Convierte esas respuestas en un mensaje claro ("Tu sesión expiró", "El servidor no respondió...").
//   2. Si un guardado tarda, muestra "⏳ Guardando..." para que no se vuelva a presionar.
//   3. Ofrece una ventana roja grande con el error exacto y un botón para copiarlo (mostrarErrorGuardado).
//   4. Ofrece botonCargando(btn): pone "Guardando..." y devuelve con qué restaurarlo.
//   5. Avisa al servidor cada fallo para verlo en Herramientas ▸ Registro de errores.
(function () {
    if (window.__erroresGuardado) return;
    window.__erroresGuardado = true;
    const fetchOriginal = window.fetch.bind(window);

    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }

    function avisarServidor(info) {
        try {
            fetchOriginal('/api/diagnostico/fallo', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(info)
            }).catch(() => {});
        } catch (e) { /* nada */ }
    }

    function explicarEstado(estado) {
        if (estado === 401) return 'Tu sesión expiró. Vuelve a iniciar sesión (tus datos no se guardaron).';
        if (estado === 403) return 'No tienes permiso para esta acción. Pídeselo al administrador en Configuración ▸ Usuarios y permisos.';
        if (estado === 404) return 'El sistema no encontró esta función en el servidor. Puede que en Render esté una versión antigua: sube el ZIP vigente.';
        if (estado === 413) return 'Lo que intentas guardar es demasiado grande (por ejemplo, un archivo pesado).';
        if (estado === 502 || estado === 503 || estado === 504) return 'El servidor no respondió a tiempo (Render puede estar despertando o reiniciándose). Espera 30 segundos y vuelve a intentar.';
        if (estado >= 500) return 'Error en el servidor (' + estado + ').';
        return 'El servidor respondió con un error (' + estado + ').';
    }

    function respuestaJson(cuerpo, estado) {
        return new Response(JSON.stringify(cuerpo), { status: estado, headers: { 'Content-Type': 'application/json' } });
    }

    // ---------- Aviso "Guardando..." si tarda ----------
    let pendientes = 0, temporizador = null;
    function aviso(mostrar) {
        let el = document.getElementById('avisoGuardandoLento');
        if (!mostrar) { if (el) el.remove(); return; }
        if (el || !document.body) return;
        el = document.createElement('div');
        el.id = 'avisoGuardandoLento';
        el.style.cssText = 'position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:100000010;background:#FEF9C3;color:#713F12;border:2px solid #EAB308;border-radius:12px;padding:10px 18px;font-weight:800;font-size:14px;box-shadow:0 10px 30px rgba(0,0,0,.25);max-width:92vw;text-align:center';
        el.textContent = '⏳ Guardando... el servidor está tardando (si estuvo dormido puede tardar hasta 1 minuto). No cierres ni vuelvas a presionar.';
        document.body.appendChild(el);
    }

    window.fetch = async function (recurso, opciones) {
        const url = typeof recurso === 'string' ? recurso : (recurso && recurso.url) || '';
        const metodo = String((opciones && opciones.method) || (recurso && recurso.method) || 'GET').toUpperCase();
        const esApi = url.indexOf('/api/') !== -1 && url.indexOf('/api/diagnostico/') === -1;
        if (!esApi) return fetchOriginal(recurso, opciones);
        const graba = metodo !== 'GET';
        if (graba) {
            pendientes++;
            if (!temporizador) temporizador = setTimeout(() => aviso(true), 6000);
        }
        try {
            let r;
            try {
                r = await fetchOriginal(recurso, opciones);
            } catch (e) {
                const msg = navigator.onLine === false
                    ? 'No hay internet en esta computadora. Revisa la conexión y vuelve a intentar.'
                    : 'No hubo respuesta del servidor (puede estar reiniciándose). Espera unos segundos y vuelve a intentar.';
                if (graba) avisarServidor({ mensaje: msg, detalle: String(e), ruta: url, metodo: metodo });
                const err = new Error(msg);
                err.detalle = String(e);
                throw err;
            }
            // La sesión venció y el servidor mandó a la página de inicio de sesión
            if (r.redirected && /\/login(\?|$)/.test(r.url)) {
                return respuestaJson({ success: false, codigo: 'sesion', error: explicarEstado(401) }, 401);
            }
            const tipo = r.headers.get('Content-Type') || '';
            if (!r.ok && tipo.indexOf('application/json') === -1) {
                const texto = await r.text().catch(() => '');
                const limpio = texto.replace(/<style[\s\S]*?<\/style>|<script[\s\S]*?<\/script>/gi, '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 600);
                const cuerpo = { success: false, codigo: 'http_' + r.status, error: explicarEstado(r.status), detalle: 'HTTP ' + r.status + (limpio ? ': ' + limpio : '') };
                if (graba) avisarServidor({ mensaje: cuerpo.error, detalle: cuerpo.detalle, ruta: url, metodo: metodo, estado: r.status });
                return respuestaJson(cuerpo, r.status);
            }
            return r;
        } finally {
            if (graba) {
                pendientes = Math.max(0, pendientes - 1);
                if (!pendientes) { clearTimeout(temporizador); temporizador = null; aviso(false); }
            }
        }
    };

    // ---------- Ventana roja con el error exacto ----------
    window.mostrarErrorGuardado = function (titulo, mensaje, detalle) {
        document.getElementById('ventanaErrorGuardado')?.remove();
        const f = document.createElement('div');
        f.id = 'ventanaErrorGuardado';
        f.style.cssText = 'position:fixed;inset:0;background:rgba(15,23,42,.55);z-index:100000020;display:flex;align-items:center;justify-content:center;padding:16px';
        f.innerHTML = '<div role="alertdialog" style="background:#FEF2F2;border:4px solid #DC2626;border-radius:14px;max-width:560px;width:100%;padding:20px;box-shadow:0 20px 60px rgba(0,0,0,.35);color:#7F1D1D">' +
            '<div style="font-size:20px;font-weight:900;margin-bottom:8px">⛔ ' + esc(titulo || 'No se pudo guardar') + '</div>' +
            '<div style="font-size:15px;font-weight:700;margin-bottom:12px;color:#991B1B">' + esc(mensaje || 'Error desconocido') + '</div>' +
            (detalle ? '<details style="margin-bottom:12px"><summary style="cursor:pointer;font-weight:700">Ver detalle técnico (para soporte)</summary>' +
                '<pre id="ventanaErrorDetalle" style="white-space:pre-wrap;word-break:break-word;background:#fff;border:1px solid #FCA5A5;border-radius:8px;padding:8px;font-size:12px;max-height:200px;overflow:auto;margin-top:6px">' + esc(detalle) + '</pre></details>' : '') +
            '<div style="display:flex;gap:10px;justify-content:flex-end;flex-wrap:wrap">' +
            (detalle ? '<button type="button" data-copiar style="padding:9px 14px;border-radius:10px;border:2px solid #DC2626;background:#fff;color:#991B1B;font-weight:800;cursor:pointer">Copiar detalle</button>' : '') +
            '<button type="button" data-cerrar style="padding:9px 18px;border-radius:10px;border:0;background:#DC2626;color:#fff;font-weight:900;cursor:pointer">Entendido</button></div></div>';
        document.body.appendChild(f);
        f.querySelector('[data-cerrar]').onclick = () => f.remove();
        const copiar = f.querySelector('[data-copiar]');
        if (copiar) copiar.onclick = () => {
            const txt = (titulo || '') + '\n' + (mensaje || '') + '\n' + (detalle || '');
            (navigator.clipboard ? navigator.clipboard.writeText(txt) : Promise.reject()).then(
                () => { copiar.textContent = '✔ Copiado'; }, () => { copiar.textContent = 'Selecciona y copia el texto'; });
        };
        f.querySelector('[data-cerrar]').focus();
    };

    // Resalta en rojo un campo del formulario que el servidor dijo que falta o está mal
    window.marcarCampoError = function (id) {
        const el = id && document.getElementById(id);
        if (!el) return;
        el.style.borderColor = '#DC2626';
        el.style.boxShadow = '0 0 0 3px rgba(220,38,38,0.25)';
        try { el.focus(); } catch (e) { /* nada */ }
        setTimeout(() => { el.style.borderColor = ''; el.style.boxShadow = ''; }, 6000);
    };

    // ---------- Botón "Guardando..." ----------
    window.botonCargando = function (btn, texto) {
        if (!btn) return () => {};
        const antes = btn.innerHTML, deshabilitado = btn.disabled;
        btn.disabled = true;
        btn.innerHTML = '⏳ ' + (texto || 'Guardando...');
        btn.style.cursor = 'wait';
        return () => { btn.innerHTML = antes; btn.disabled = deshabilitado; btn.style.cursor = ''; };
    };
})();
