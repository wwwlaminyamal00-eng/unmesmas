// Papelera / Auditoría. Todo dentro de una función para no chocar con el código global de base.html.
(function () {
    'use strict';
    const $ = (id) => document.getElementById(id);
    const app = $('papApp');
    const ES_ADMIN = app.dataset.admin === 'true';
    const esc = (v) => String(v === null || v === undefined ? '' : v)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    const soles = (n) => n === null || n === undefined ? '—' : 'S/ ' + Number(n).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

    function aviso(msg, tipo) {
        const t = $('papToast');
        t.textContent = msg;
        t.className = 'hr-toast show ' + (tipo || 'ok');
        clearTimeout(aviso._t);
        aviso._t = setTimeout(() => t.classList.remove('show'), 5500);
    }
    async function api(url, opciones) {
        const r = await fetch(url, Object.assign({ credentials: 'same-origin' }, opciones || {}));
        let d = {};
        try { d = await r.json(); } catch (e) { d = { success: false, error: 'Respuesta no válida del servidor (' + r.status + ')' }; }
        if (!r.ok || d.success === false) throw new Error(d.error || ('Error ' + r.status));
        return d;
    }
    const post = (url, cuerpo) => api(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cuerpo) });

    function modal(titulo, html, textoSi, peligro) {
        return new Promise((resolve) => {
            $('papConfirmTitulo').textContent = titulo;
            $('papConfirmTexto').innerHTML = html;
            const si = $('papConfirmSi');
            si.textContent = textoSi || 'Sí';
            si.style.background = peligro ? '#FF0033' : '';
            si.style.borderColor = peligro ? '#FF0033' : '';
            const m = $('papConfirm');
            m.classList.add('show');
            const fin = (v) => { m.classList.remove('show'); si.onclick = null; $('papConfirmNo').onclick = null; resolve(v); };
            si.onclick = () => fin(true);
            $('papConfirmNo').onclick = () => fin(false);
            const primero = m.querySelector('input');
            if (primero) setTimeout(() => primero.focus(), 50);
        });
    }
    document.querySelectorAll('[data-cerrar]').forEach(b => b.addEventListener('click', () => $(b.dataset.cerrar).classList.remove('show')));

    // ---------- Pestañas ----------
    function abrirTab(tab) {
        document.querySelectorAll('#papTabs .tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
        document.querySelectorAll('#papApp > .section').forEach(s => s.classList.toggle('active', s.id === 'ptab-' + tab));
        if (tab === 'auditoria' && !abrirTab.audCargada) { abrirTab.audCargada = true; opcionesAuditoria(); cargarAuditoria(1); }
    }
    document.querySelectorAll('#papTabs .tab-btn').forEach(b => b.addEventListener('click', () => abrirTab(b.dataset.tab)));

    // ---------- PAPELERA ----------
    let filas = [];
    let chip = '';
    function semEstado(i) {
        if (i.tipo === 'Desactivado') return 'sem-atencion';
        return 'sem-peligro';
    }
    function pintarPapelera() {
        const lista = chip ? filas.filter(i => i.modulo === chip) : filas;
        $('papFilas').innerHTML = lista.map(i => {
            const acciones = [];
            acciones.push('<button class="hr-btn sec" data-ver="' + esc(i.clave) + '" title="Ver todo el registro">👁 Ver</button>');
            if (i.puede_restaurar) acciones.push('<button class="hr-btn" data-restaurar="' + esc(i.clave) + '" title="Restaurar">♻️ Restaurar</button>');
            if (i.puede_borrar) acciones.push('<button class="btn-tachito" data-borrar="' + esc(i.clave) + '" title="Borrar definitivamente">🗑️</button>');
            const nota = !i.puede_restaurar && i.por_que_no ? '<small title="' + esc(i.por_que_no) + '">🔒 ' + esc(i.por_que_no.length > 60 ? i.por_que_no.slice(0, 58) + '…' : i.por_que_no) + '</small>' : '';
            return '<tr><td style="white-space:nowrap">' + esc(i.fecha || '—') + '</td>' +
                '<td class="left"><b>' + esc(i.modulo) + '</b><small>' + esc(i.tipo) + '</small></td>' +
                '<td class="hr-mono"><b>' + esc(i.numero) + '</b></td>' +
                '<td class="left">' + esc(i.tercero || '—') + '</td>' +
                '<td class="num">' + (i.monto !== null && i.monto !== undefined ? soles(i.monto) : '—') + '</td>' +
                '<td><span class="hr-sem ' + semEstado(i) + '">' + esc(i.estado || i.tipo) + '</span></td>' +
                '<td class="left">' + esc(i.motivo || '—') + '</td>' +
                '<td>' + esc(i.usuario || '—') + '</td>' +
                '<td>' + esc(i.empresa || '—') + '</td>' +
                '<td><span class="hr-acc">' + acciones.join('') + '</span>' + nota + '</td></tr>';
        }).join('') || '<tr><td colspan="10" class="hr-vacio"><span class="hr-sem sem-ok">✔ La papelera está vacía con estos filtros</span></td></tr>';
        $('papTotal').textContent = lista.length + ' registro(s)' + (chip ? ' en ' + chip : '');
    }
    function pintarChips(resumen) {
        const total = Object.values(resumen).reduce((a, b) => a + b, 0);
        $('papChips').innerHTML = '<button class="hr-chip' + (chip ? '' : ' activa') + '" data-chip="">Todo <b>' + total + '</b></button>' +
            Object.entries(resumen).map(([m, n]) => '<button class="hr-chip' + (chip === m ? ' activa' : '') + '" data-chip="' + esc(m) + '">' + esc(m) + ' <b>' + n + '</b></button>').join('');
        $('papChips').querySelectorAll('[data-chip]').forEach(b => b.addEventListener('click', () => { chip = b.dataset.chip; pintarChips(resumen); pintarPapelera(); }));
    }
    async function cargarPapelera() {
        const p = new URLSearchParams();
        [['modulo', 'papModulo'], ['desde', 'papDesde'], ['hasta', 'papHasta'], ['usuario', 'papUsuario'], ['empresa', 'papEmpresa'], ['q', 'papBuscar']]
            .forEach(([k, id]) => { if ($(id).value) p.set(k, $(id).value); });
        $('papFilas').innerHTML = '<tr><td colspan="10" class="hr-vacio">⏳ Cargando...</td></tr>';
        try {
            const d = await api('/papelera/api/lista?' + p.toString());
            filas = d.data;
            if (chip && !d.resumen[chip]) chip = '';
            pintarChips(d.resumen);
            pintarPapelera();
        } catch (e) {
            $('papFilas').innerHTML = '<tr><td colspan="10"><div class="hr-aviso danger">' + esc(e.message) + '</div></td></tr>';
        }
    }
    $('papActualizar').onclick = cargarPapelera;
    ['papModulo', 'papEmpresa', 'papDesde', 'papHasta'].forEach(id => $(id).addEventListener('change', cargarPapelera));
    ['papUsuario', 'papBuscar'].forEach(id => $(id).addEventListener('keydown', (e) => { if (e.key === 'Enter') cargarPapelera(); }));

    function tablaDatos(datos) {
        const filasDato = Object.entries(datos || {}).filter(([, v]) => v !== null && v !== '' && !(Array.isArray(v) && !v.length));
        return '<table class="hr-table"><tbody>' + filasDato.map(([k, v]) =>
            '<tr><td class="left hr-mono" style="width:32%">' + esc(k) + '</td><td class="left">' +
            esc(typeof v === 'object' ? JSON.stringify(v) : v) + '</td></tr>').join('') + '</tbody></table>';
    }

    $('papFilas').addEventListener('click', async (ev) => {
        const b = ev.target.closest('button');
        if (!b) return;
        const item = filas.find(i => i.clave === (b.dataset.ver || b.dataset.restaurar || b.dataset.borrar));
        if (!item) return;
        if (b.dataset.ver) {
            try {
                const d = await api('/papelera/api/detalle?clave=' + encodeURIComponent(item.clave));
                $('papDetalleTitulo').textContent = item.modulo + ' · ' + item.numero;
                $('papDetalleCuerpo').innerHTML =
                    (item.por_que_no ? '<div class="hr-aviso info">' + esc(item.por_que_no) + '</div>' : '') +
                    (d.historial.length ? '<h4 style="margin:0 0 6px">Historial</h4><table class="hr-table" style="margin-bottom:12px"><thead><tr><th>Fecha</th><th>Acción</th><th>Usuario</th><th>Detalle</th></tr></thead><tbody>' +
                        d.historial.map(h => '<tr><td>' + esc(h.fecha) + '</td><td><b>' + esc(h.accion) + '</b></td><td>' + esc(h.usuario || '—') + '</td><td class="left">' + esc(h.detalle || '') + '</td></tr>').join('') + '</tbody></table>' : '') +
                    '<h4 style="margin:0 0 6px">Datos completos</h4>' + tablaDatos(d.datos);
                $('papDetalle').classList.add('show');
            } catch (e) { aviso(e.message, 'error'); }
        } else if (b.dataset.restaurar) {
            const ok = await modal('♻️ Restaurar ' + item.numero,
                '<b>' + esc(item.modulo) + ' ' + esc(item.numero) + '</b> (' + esc(item.tercero || '') + ') volverá a estar activo.' +
                (item.fuente === 'cot' ? '<br>La cotización vuelve como <b>Borrador</b>.' : '') +
                (item.fuente === 'oc' || item.fuente === 'sol' ? '<br>Vuelve como <b>Borrador</b>.' : '') +
                (item.fuente === 'desp' ? '<br>Vuelve como <b>Pendiente despacho</b> (el stock no se mueve hasta despacharlo).' : '') +
                '<br>Queda registrado en Auditoría.', 'Sí, restaurar');
            if (!ok) return;
            try { const d = await post('/papelera/api/restaurar', { clave: item.clave }); aviso(d.message); cargarPapelera(); } catch (e) { aviso(e.message, 'error'); }
        } else if (b.dataset.borrar) {
            // Confirmación 1
            const paso1 = await modal('🗑️ Borrar definitivamente',
                '<div class="hr-aviso danger"><b>Esto no se puede deshacer.</b> ' + esc(item.modulo) + ' <b>' + esc(item.numero) +
                '</b> desaparecerá del sistema. Sus datos completos quedarán guardados en Auditoría.</div>¿Quieres continuar?', 'Continuar', true);
            if (!paso1) return;
            // Confirmación 2: escribir BORRAR y el número
            const paso2 = await modal('🗑️ Confirmación final',
                'Escribe <b>BORRAR</b>:<input id="papConfPalabra" autocomplete="off">' +
                '<div style="margin-top:10px">y el número del documento <b class="hr-mono">' + esc(item.numero) + '</b>:</div><input id="papConfNumero" autocomplete="off">',
                'Borrar para siempre', true);
            if (!paso2) return;
            try {
                const d = await post('/papelera/api/borrar', { clave: item.clave, confirmacion: $('papConfPalabra').value, numero: $('papConfNumero').value });
                aviso(d.message);
                cargarPapelera();
            } catch (e) { aviso(e.message, 'error'); }
        }
    });

    // ---------- AUDITORÍA ----------
    const ACC = {
        crear: 'sem-ok', aprobar: 'sem-ok', restaurar: 'sem-ok', activar: 'sem-ok', login: 'hr-sem-azul', logout: 'hr-sem-gris',
        editar: 'sem-atencion', importar: 'sem-atencion', desactivar: 'sem-atencion', rechazar: 'sem-atencion',
        anular: 'sem-peligro', eliminar: 'sem-peligro', borrar_definitivo: 'sem-peligro', login_fallido: 'sem-peligro',
        exportar: 'hr-sem-azul', herramienta: 'hr-sem-azul',
    };
    const NOMBRE_ACC = { borrar_definitivo: 'borrado definitivo', login_fallido: 'login fallido', herramienta: 'uso de herramienta' };
    let pagina = 1, audFilas = [];

    function filtrosAud() {
        const p = new URLSearchParams();
        [['usuario', 'audUsuario'], ['modulo', 'audModulo'], ['accion', 'audAccion'], ['desde', 'audDesde'], ['hasta', 'audHasta'], ['q', 'audBuscar']]
            .forEach(([k, id]) => { if ($(id) && $(id).value) p.set(k, $(id).value); });
        return p;
    }
    async function opcionesAuditoria() {
        try {
            const d = await api('/papelera/api/auditoria/opciones');
            $('audModulo').innerHTML = '<option value="">Todos</option>' + d.modulos.map(m => '<option>' + esc(m) + '</option>').join('');
            $('audAccion').innerHTML = '<option value="">Todas</option>' + d.acciones.map(a => '<option value="' + a + '">' + esc(NOMBRE_ACC[a] || a) + '</option>').join('');
            $('audUsuarios').innerHTML = d.usuarios.map(u => '<option value="' + esc(u) + '">').join('');
        } catch (e) { aviso(e.message, 'error'); }
    }
    function resumenCambios(f) {
        if (!f.cambios || !f.cambios.length) return '';
        const c = f.cambios.slice(0, 3).map(x => '<small><span class="hr-mono">' + esc(x.campo) + '</span>: ' +
            '<span style="color:#C80028;text-decoration:line-through">' + esc(String(x.antes ?? '—').slice(0, 30)) + '</span> → <b>' + esc(String(x.despues ?? '—').slice(0, 30)) + '</b></small>').join('');
        return ['editar', 'anular', 'aprobar', 'rechazar', 'restaurar', 'desactivar', 'activar'].includes(f.accion) ? c : '';
    }
    async function cargarAuditoria(p) {
        pagina = p || 1;
        const q = filtrosAud();
        q.set('pagina', pagina);
        $('audFilas').innerHTML = '<tr><td colspan="8" class="hr-vacio">⏳ Cargando...</td></tr>';
        try {
            const d = await api('/papelera/api/auditoria?' + q.toString());
            audFilas = d.data;
            $('audFilas').innerHTML = d.data.map((f, n) =>
                '<tr><td style="white-space:nowrap">' + esc(f.fecha) + '</td><td><b>' + esc(f.usuario || '—') + '</b>' + (f.ip ? '<small>' + esc(f.ip) + '</small>' : '') + '</td>' +
                '<td><span class="hr-sem ' + (ACC[f.accion] || 'hr-sem-gris') + '">' + esc(NOMBRE_ACC[f.accion] || f.accion) + '</span></td>' +
                '<td class="left">' + esc(f.modulo || '') + '</td><td class="hr-mono">' + esc(f.documento || (f.registro_id ? '#' + f.registro_id : '')) + '</td>' +
                '<td class="left">' + esc(f.detalle || '') + resumenCambios(f) + '</td><td>' + esc(f.empresa || '—') + '</td>' +
                '<td>' + (f.tiene_datos ? '<button class="hr-btn sec" data-aud="' + n + '">Antes / después</button>' : '') + '</td></tr>').join('') ||
                '<tr><td colspan="8" class="hr-vacio">No hay movimientos con estos filtros.</td></tr>';
            $('audTotal').textContent = d.total.toLocaleString('es-PE') + ' movimiento(s)';
            $('audPagina').textContent = 'Página ' + d.pagina + ' de ' + d.paginas;
            $('audAnt').disabled = d.pagina <= 1;
            $('audSig').disabled = d.pagina >= d.paginas;
        } catch (e) { $('audFilas').innerHTML = '<tr><td colspan="8"><div class="hr-aviso danger">' + esc(e.message) + '</div></td></tr>'; }
    }
    async function verCambios(f) {
        try {
            const d = (await api('/papelera/api/auditoria/' + encodeURIComponent(f.id))).data;
            const val = (v) => v === null || v === undefined || v === '' ? '—' : (typeof v === 'object' ? JSON.stringify(v) : v);
            let html = '<div class="hr-aviso info"><b>' + esc(d.usuario || 'Sistema') + '</b> · ' + esc(d.fecha) + ' · <b>' + esc(NOMBRE_ACC[d.accion] || d.accion) +
                '</b> · ' + esc(d.modulo || '') + ' · ' + esc(d.tabla) + ' #' + esc(d.registro_id || '') + (d.detalle ? '<br>' + esc(d.detalle) : '') + '</div>';
            if (d.accion === 'editar' || d.accion === 'anular' || d.accion === 'aprobar' || d.accion === 'restaurar' || d.accion === 'rechazar' ||
                d.accion === 'desactivar' || d.accion === 'activar') {
                html += '<table class="hr-table"><thead><tr><th>Campo</th><th>Antes</th><th>Después</th></tr></thead><tbody>' +
                    (d.cambios.map(c => '<tr><td class="hr-mono left">' + esc(c.campo) + '</td><td class="hr-antes">' + esc(val(c.antes)) + '</td><td class="hr-despues">' + esc(val(c.despues)) + '</td></tr>').join('') ||
                        '<tr><td colspan="3" class="hr-vacio">Sin cambios de datos visibles.</td></tr>') + '</tbody></table>';
            } else {
                const datos = d.despues || d.antes;
                html += '<h4 style="margin:0 0 6px">' + (d.despues ? 'Datos guardados' : 'Datos antes de borrar') + '</h4>' + tablaDatos(datos);
            }
            $('papDetalleTitulo').textContent = 'Cambio en ' + (d.modulo || d.tabla);
            $('papDetalleCuerpo').innerHTML = html;
            $('papDetalle').classList.add('show');
        } catch (e) { aviso(e.message, 'error'); }
    }
    if (ES_ADMIN && $('audFilas')) {
        $('audFilas').addEventListener('click', (ev) => { const b = ev.target.closest('[data-aud]'); if (b) verCambios(audFilas[+b.dataset.aud]); });
        $('audActualizar').onclick = () => cargarAuditoria(1);
        ['audModulo', 'audAccion', 'audDesde', 'audHasta'].forEach(id => $(id).addEventListener('change', () => cargarAuditoria(1)));
        ['audUsuario', 'audBuscar'].forEach(id => $(id).addEventListener('keydown', (e) => { if (e.key === 'Enter') cargarAuditoria(1); }));
        $('audAnt').onclick = () => cargarAuditoria(pagina - 1);
        $('audSig').onclick = () => cargarAuditoria(pagina + 1);
        const exportar = (fmt) => { const p = filtrosAud(); p.set('formato', fmt); location.href = '/papelera/api/auditoria/exportar?' + p.toString(); };
        $('audExcel').onclick = () => exportar('xlsx');
        $('audCsv').onclick = () => exportar('csv');
    }

    cargarPapelera();
    if ((location.hash || '') === '#auditoria' && ES_ADMIN) abrirTab('auditoria');
})();
