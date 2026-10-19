// Herramientas (solo administradores). Todo en una función para no chocar con el código global de base.html.
(function () {
    'use strict';
    const $ = (id) => document.getElementById(id);
    const esc = (v) => String(v === null || v === undefined ? '' : v)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

    function aviso(msg, tipo) {
        const t = $('herrToast');
        t.textContent = msg;
        t.className = 'hr-toast show ' + (tipo || 'ok');
        clearTimeout(aviso._t);
        aviso._t = setTimeout(() => t.classList.remove('show'), 5000);
    }

    function confirmar(titulo, html, textoSi) {
        return new Promise((resolve) => {
            $('herrConfirmTitulo').textContent = titulo;
            $('herrConfirmTexto').innerHTML = html;
            $('herrConfirmSi').textContent = textoSi || 'Sí, continuar';
            const m = $('herrConfirm');
            m.classList.add('show');
            const fin = (v) => { m.classList.remove('show'); $('herrConfirmSi').onclick = null; $('herrConfirmNo').onclick = null; resolve(v); };
            $('herrConfirmSi').onclick = () => fin(true);
            $('herrConfirmNo').onclick = () => fin(false);
        });
    }

    async function api(url, opciones) {
        const r = await fetch(url, Object.assign({ credentials: 'same-origin' }, opciones || {}));
        let d = {};
        try { d = await r.json(); } catch (e) { d = { success: false, error: 'Respuesta no válida del servidor (' + r.status + ')' }; }
        if (!r.ok || d.success === false) throw new Error(d.error || ('Error ' + r.status));
        return d;
    }

    function cargando(el, texto) { el.innerHTML = '<div class="hr-vacio">⏳ ' + esc(texto || 'Revisando...') + '</div>'; }

    // ---------- Navegación ----------
    function abrir(sec) {
        document.querySelectorAll('#herrCards .hr-card').forEach(b => b.classList.toggle('activa', b.dataset.sec === sec));
        document.querySelectorAll('.hr-section').forEach(s => s.classList.toggle('active', s.id === 'hsec-' + sec));
        try { localStorage.setItem('herr_sec', sec); } catch (e) { /* sin almacenamiento */ }
    }
    document.querySelectorAll('#herrCards .hr-card').forEach(b => b.addEventListener('click', () => abrir(b.dataset.sec)));
    try { const s = localStorage.getItem('herr_sec'); if (s && $('hsec-' + s)) abrir(s); } catch (e) { /* nada */ }
    const hash = (location.hash || '').replace('#', '');
    if (hash && $('hsec-' + hash)) abrir(hash);

    // ---------- 1. Importar ----------
    let ultimaRevision = null;
    function notaImport() {
        const cfg = (window.HERR_NOTAS || {})[$('impTipo').value] || {};
        $('impNota').textContent = cfg.nota || '';
        $('impResultado').style.display = 'none';
    }
    $('impTipo').addEventListener('change', notaImport);
    notaImport();
    $('impPlantillaXlsx').onclick = () => { location.href = '/herramientas/api/plantilla/' + $('impTipo').value + '?formato=xlsx'; };
    $('impPlantillaCsv').onclick = () => { location.href = '/herramientas/api/plantilla/' + $('impTipo').value + '?formato=csv'; };

    async function enviarImport(confirmarAhora) {
        const f = $('impArchivo').files[0];
        if (!f) { aviso('Primero elige el archivo Excel o CSV.', 'error'); return null; }
        const fd = new FormData();
        fd.append('archivo', f);
        fd.append('actualizar', $('impActualizar').checked ? '1' : '0');
        fd.append('confirmar', confirmarAhora ? '1' : '0');
        return api('/herramientas/api/importar/' + $('impTipo').value, { method: 'POST', body: fd });
    }

    const ETIQ = {
        nuevo: ['sem-ok', '✚ Nuevo'], actualizar: ['sem-atencion', '✎ Se actualiza'],
        existe: ['hr-sem-gris', '= Ya existe (no se toca)'], error: ['sem-peligro', '✖ Error (no se carga)'],
    };
    function pintarImport(d) {
        const r = d.resumen || {};
        $('impResultado').style.display = '';
        $('impColumnas').innerHTML = 'Columnas reconocidas: <b>' + esc((d.columnas || []).join(', ')) + '</b>' +
            ((d.ignoradas || []).length ? ' · Ignoradas: ' + esc(d.ignoradas.join(', ')) : '');
        $('impResumen').innerHTML =
            '<div class="hr-kpi ok"><small>Nuevos</small><b>' + (r.nuevo || 0) + '</b><span>Se van a crear</span></div>' +
            '<div class="hr-kpi warn"><small>Se actualizan</small><b>' + (r.actualizar || 0) + '</b><span>Ya existían</span></div>' +
            '<div class="hr-kpi"><small>Ya existen</small><b>' + (r.existe || 0) + '</b><span>No se tocan</span></div>' +
            '<div class="hr-kpi danger"><small>Con error</small><b>' + (r.error || 0) + '</b><span>No se cargan</span></div>';
        $('impFilas').innerHTML = (d.filas || []).map(f => {
            const e = ETIQ[f.estado] || ['hr-sem-gris', f.estado];
            const clase = f.estado === 'error' ? 'fila-error' : (f.estado === 'nuevo' ? 'fila-ok' : (f.estado === 'actualizar' ? 'fila-warn' : ''));
            const datos = Object.entries(f.datos || {}).filter(([k, v]) => String(v) !== String(f.clave))
                .map(([k, v]) => '<small>' + esc(k) + ': <b>' + esc(v) + '</b></small>').join('');
            return '<tr class="' + clase + '"><td>' + f.fila + '</td><td><span class="hr-sem ' + e[0] + '">' + e[1] + '</span></td>' +
                '<td class="hr-mono"><b>' + esc(f.clave || '—') + '</b></td><td class="left">' + datos + '</td>' +
                '<td class="left">' + (f.mensajes || []).map(m => '<small>• ' + esc(m) + '</small>').join('') + '</td></tr>';
        }).join('') || '<tr><td colspan="5" class="hr-vacio">El archivo no tiene filas.</td></tr>';
        const cargables = (r.nuevo || 0) + (r.actualizar || 0);
        $('impConfirmar').disabled = !cargables;
        $('impConfirmar').textContent = cargables ? '✅ Importar ' + cargables + ' registro(s)' : 'Nada para importar';
    }

    $('impRevisar').onclick = async () => {
        try {
            $('impRevisar').disabled = true;
            ultimaRevision = await enviarImport(false);
            if (ultimaRevision) pintarImport(ultimaRevision);
        } catch (e) { aviso(e.message, 'error'); } finally { $('impRevisar').disabled = false; }
    };
    $('impConfirmar').onclick = async () => {
        if (!ultimaRevision) return;
        const r = ultimaRevision.resumen;
        const ok = await confirmar('¿Importar ahora?',
            'Se crearán <b>' + r.nuevo + '</b> registro(s) nuevos' + (r.actualizar ? ' y se actualizarán <b>' + r.actualizar + '</b>' : '') +
            '.<br>Las filas con error no se cargan. No se borra nada.', 'Sí, importar');
        if (!ok) return;
        try {
            $('impConfirmar').disabled = true;
            const d = await enviarImport(true);
            aviso(d.message || 'Importación terminada');
            $('impResultado').style.display = 'none';
            $('impArchivo').value = '';
            ultimaRevision = null;
        } catch (e) { aviso(e.message, 'error'); $('impConfirmar').disabled = false; }
    };

    // ---------- 2. Exportar ----------
    $('expBuscar').addEventListener('input', () => {
        const q = $('expBuscar').value.trim().toLowerCase();
        document.querySelectorAll('#expTablas tr').forEach(tr => { tr.style.display = !q || tr.dataset.buscar.includes(q) ? '' : 'none'; });
    });
    document.querySelectorAll('[data-exportar]').forEach(b => b.addEventListener('click', () => {
        location.href = '/herramientas/api/exportar?tabla=' + encodeURIComponent(b.dataset.exportar) + '&formato=' + b.dataset.formato;
        aviso('Descargando ' + b.dataset.exportar + '...');
    }));

    // ---------- 3. Numeraciones ----------
    async function revisarCorrelativos() {
        const el = $('corResultado');
        cargando(el);
        try {
            const d = await api('/herramientas/api/correlativos');
            let html = d.data.map(n => {
                const malo = n.duplicados ? 'danger' : (n.huecos ? 'warn' : (n.documentos ? 'ok' : 'gris'));
                const sem = n.duplicados ? '<span class="hr-sem sem-peligro">' + n.duplicados + ' repetido(s)</span>' :
                    (n.huecos ? '<span class="hr-sem sem-atencion">' + n.huecos + ' número(s) faltan</span>' :
                        (n.documentos ? '<span class="hr-sem sem-ok">✔ Todo en orden</span>' : '<span class="hr-sem hr-sem-gris">Sin documentos</span>'));
                const series = (n.series || []).filter(s => s.total_huecos || s.duplicados.length).map(s =>
                    '<li><b>' + esc(s.serie) + '</b> (del ' + s.desde + ' al ' + s.hasta + ', ' + s.documentos + ' doc.)' +
                    (s.total_huecos ? ' · faltan: ' + esc(s.huecos.join(', ')) + (s.total_huecos > s.huecos.length ? ' y ' + (s.total_huecos - s.huecos.length) + ' más' : '') : '') +
                    (s.duplicados.length ? ' · <b style="color:#C80028">repetidos: ' + esc(s.duplicados.map(x => x.numero + ' (' + x.veces + ' veces)').join(', ')) + '</b>' : '') + '</li>').join('');
                return '<div class="hr-rev ' + malo + '"><div class="hr-rev-top"><b>' + esc(n.titulo) + (n.fiscal ? ' 🧾' : '') + '</b>' + sem + '</div>' +
                    '<p>' + n.documentos + ' documento(s) en ' + (n.series || []).length + ' serie(s)' +
                    (n.series_ocultas ? ' (+' + n.series_ocultas + ' series diarias sin problemas)' : '') +
                    (n.fiscal ? '. Documento SUNAT: un hueco puede ser normal si se anuló o rechazó; nunca se renumera.' : '') +
                    (n.nota ? '. ' + esc(n.nota) : '') + '</p>' + (series ? '<ul>' + series + '</ul>' : '') + '</div>';
            }).join('');
            const atrasados = (d.contadores || []).filter(c => c.atrasado);
            if ((d.contadores || []).length) {
                html += '<div class="hr-rev ' + (atrasados.length ? 'warn' : 'ok') + '"><div class="hr-rev-top"><b>Contadores de Configuración ▸ Correlativos</b>' +
                    (atrasados.length ? '<span class="hr-sem sem-atencion">' + atrasados.length + ' atrasado(s)</span>' : '<span class="hr-sem sem-ok">✔ Al día</span>') + '</div>' +
                    '<p>Si un contador quedó por debajo del último número usado, el próximo documento saldría repetido. Puedes subirlo (nunca se baja).</p><ul>' +
                    d.contadores.map(c => '<li>' + esc((c.empresa || '') + ' ' + c.documento) + ' (' + esc(c.prefijo + '-' + c.anio) + '): contador ' + c.ultimo_numero +
                        ', máximo usado ' + c.maximo_usado + (c.atrasado ? ' <button class="hr-btn" data-ajustar="' + esc(c.id) + '">Subir a ' + c.maximo_usado + '</button>' : ' ✔') + '</li>').join('') + '</ul></div>';
            }
            el.innerHTML = html;
            el.querySelectorAll('[data-ajustar]').forEach(b => b.addEventListener('click', async () => {
                if (!await confirmar('¿Ajustar el contador?', 'El próximo número continuará después del último ya usado. No cambia ningún documento.')) return;
                try { const r = await api('/herramientas/api/correlativos/ajustar', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: b.dataset.ajustar }) }); aviso(r.message); revisarCorrelativos(); } catch (e) { aviso(e.message, 'error'); }
            }));
        } catch (e) { el.innerHTML = '<div class="hr-aviso danger">' + esc(e.message) + '</div>'; }
    }
    $('corRevisar').onclick = revisarCorrelativos;

    // ---------- 4. Integridad ----------
    $('intRevisar').onclick = async () => {
        const el = $('intResultado');
        cargando(el);
        $('intResumen').innerHTML = '';
        try {
            const d = await api('/herramientas/api/integridad');
            const conProblema = d.data.filter(c => c.cantidad);
            const revisados = d.data.filter(c => !c.omitido).length;
            $('intResumen').innerHTML =
                '<div class="hr-kpi ' + (conProblema.length ? 'danger' : 'ok') + '"><small>Con problemas</small><b>' + conProblema.length + '</b><span>de ' + revisados + ' revisiones</span></div>' +
                '<div class="hr-kpi ok"><small>En orden</small><b>' + (revisados - conProblema.length) + '</b><span>Sin observaciones</span></div>';
            const orden = { alta: 0, media: 1, baja: 2 };
            el.innerHTML = d.data.slice().sort((a, b) => (b.cantidad ? 1 : 0) - (a.cantidad ? 1 : 0) || orden[a.gravedad] - orden[b.gravedad]).map(c => {
                if (c.omitido) return '<div class="hr-rev gris"><div class="hr-rev-top"><b>' + esc(c.titulo) + '</b><span class="hr-sem hr-sem-gris">No aplica</span></div><p>' + esc(c.omitido) + '</p></div>';
                const clase = !c.cantidad ? 'ok' : (c.gravedad === 'alta' ? 'danger' : 'warn');
                const sem = !c.cantidad ? '<span class="hr-sem sem-ok">✔ En orden</span>' :
                    '<span class="hr-sem ' + (c.gravedad === 'alta' ? 'sem-peligro' : 'sem-atencion') + '">' + c.cantidad + ' caso(s)</span>';
                const ej = c.ejemplos.length ? '<details' + (c.cantidad <= 5 ? ' open' : '') + '><summary>Ver casos</summary><ul>' +
                    c.ejemplos.map(x => '<li>' + esc(x.texto) + '</li>').join('') + (c.cantidad > c.ejemplos.length ? '<li>… y ' + (c.cantidad - c.ejemplos.length) + ' más</li>' : '') + '</ul></details>' : '';
                return '<div class="hr-rev ' + clase + '"><div class="hr-rev-top"><b>' + esc(c.titulo) + '</b>' + sem + '</div><p>' + esc(c.ayuda) + '</p>' + ej + '</div>';
            }).join('');
        } catch (e) { el.innerHTML = '<div class="hr-aviso danger">' + esc(e.message) + '</div>'; }
    };

    // ---------- 5. Stock ----------
    async function recalcular(cuerpo, texto) {
        if (!await confirmar('Recalcular stock', texto, 'Sí, recalcular')) return;
        const el = $('stkResultado');
        cargando(el, 'Recalculando...');
        try {
            const d = await api('/herramientas/api/recalcular_stock', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cuerpo) });
            el.innerHTML = '<div class="hr-aviso ' + (d.cambiados.length ? 'warn' : 'ok') + '">' + esc(d.message) + '</div>' +
                (d.cambiados.length ? '<table class="hr-table"><thead><tr><th>Producto</th><th>Stock antes</th><th>Stock ahora</th></tr></thead><tbody>' +
                    d.cambiados.map(c => '<tr><td class="hr-mono">' + esc(c.codigo) + '</td><td class="num">' + c.antes + '</td><td class="num"><b>' + c.despues + '</b></td></tr>').join('') + '</tbody></table>' : '');
        } catch (e) { el.innerHTML = '<div class="hr-aviso danger">' + esc(e.message) + '</div>'; }
    }
    $('stkTodos').onclick = () => recalcular({}, 'Se revisarán todos los productos que están en Inventario.');
    $('stkUno').onclick = () => {
        const c = $('stkCodigo').value.trim();
        if (!c) { aviso('Escribe el código del producto.', 'error'); return; }
        recalcular({ codigo: c }, 'Se recalculará el producto <b>' + esc(c) + '</b>.');
    };

    // ---------- 6. Caché ----------
    $('cacheLimpiar').onclick = async () => {
        try {
            const d = await api('/herramientas/api/cache/limpiar', { method: 'POST' });
            $('cacheResultado').innerHTML = '<div class="hr-aviso ok"><b>Listo.</b> Se limpió:<ul>' + d.limpiado.map(x => '<li>' + esc(x) + '</li>').join('') + '</ul></div>';
            aviso('Caché limpiada');
        } catch (e) { aviso(e.message, 'error'); }
    };

    // ---------- 7. Logs ----------
    const NIVEL = { ERROR: 'sem-peligro', CRITICAL: 'sem-peligro', WARNING: 'sem-atencion', INFO: 'hr-sem-azul' };
    async function verLogs() {
        try {
            const d = await api('/herramientas/api/logs?n=' + $('logN').value + '&nivel=' + $('logNivel').value);
            $('logNota').textContent = 'En memoria: ' + d.total_memoria + ' mensaje(s)' + (d.anterior ? ' · archivados en la última rotación: ' + d.anterior : '') +
                (d.archivo ? ' · también se guardan en el archivo erp.log' : '') + '. ' + (d.nota || '');
            $('logFilas').innerHTML = d.data.map(f => '<tr><td style="white-space:nowrap">' + esc(f.fecha) + '</td><td><span class="hr-sem ' + (NIVEL[f.nivel] || 'hr-sem-gris') + '">' + esc(f.nivel) + '</span></td>' +
                '<td class="hr-mono">' + esc(f.origen) + '</td><td class="hr-log">' + esc(f.mensaje) + '</td></tr>').join('') ||
                '<tr><td colspan="4" class="hr-vacio"><span class="hr-sem sem-ok">✔ Sin errores registrados</span></td></tr>';
        } catch (e) { aviso(e.message, 'error'); }
    }
    $('logVer').onclick = verLogs;
    $('logRotar').onclick = async () => {
        if (!await confirmar('Rotar el registro', 'Los mensajes actuales se archivan y la lista empieza de cero.', 'Sí, rotar')) return;
        try { const d = await api('/herramientas/api/logs/rotar', { method: 'POST' }); aviso(d.message); verLogs(); } catch (e) { aviso(e.message, 'error'); }
    };

    // ---------- 8. Salud ----------
    $('salRevisar').onclick = async () => {
        $('salKpis').innerHTML = '';
        cargando($('salDatos'), 'Probando la conexión...');
        try {
            const d = await api('/herramientas/api/salud');
            const cl = d.latencia_ms < 150 ? 'ok' : (d.latencia_ms < 800 ? 'warn' : 'danger');
            $('salKpis').innerHTML =
                '<div class="hr-kpi ok"><small>Conexión</small><b>✔ Conectado</b><span>La base responde</span></div>' +
                '<div class="hr-kpi ' + cl + '"><small>Velocidad</small><b>' + d.latencia_ms + ' ms</b><span>' + esc(d.estado) + '</span></div>' +
                '<div class="hr-kpi"><small>Tamaño</small><b>' + esc(d.tamano) + '</b><span>' + d.conexiones + ' conexión(es) abiertas</span></div>' +
                '<div class="hr-kpi ' + (d.zona_horaria === 'America/Lima' ? 'ok' : 'warn') + '"><small>Zona horaria</small><b style="font-size:16px">' + esc(d.zona_horaria) + '</b><span>Base: ' + esc(d.hora_base) + ' · Servidor: ' + esc(d.hora_servidor) + '</span></div>';
            $('salDatos').innerHTML = '<div class="hr-panel" style="grid-column:1/-1;margin:0"><table class="hr-table"><thead><tr><th>Tabla</th><th>Registros</th></tr></thead><tbody>' +
                d.conteos.map(c => '<tr><td class="hr-mono left">' + esc(c.tabla) + '</td><td class="num"><b>' + Number(c.filas).toLocaleString('es-PE') + '</b></td></tr>').join('') +
                '</tbody></table><div class="hr-foot"><span>' + esc(d.version) + ' · Python ' + esc(d.python) + '</span></div></div>';
        } catch (e) {
            $('salKpis').innerHTML = '<div class="hr-kpi danger"><small>Conexión</small><b>✖ Sin conexión</b><span>' + esc(e.message) + '</span></div>';
            $('salDatos').innerHTML = '';
        }
    };
})();
