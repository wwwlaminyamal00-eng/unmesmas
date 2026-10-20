// static/js/inventario.js - Módulo de Inventario multiempresa / multisede (Vanilla JS)
(function () {
    'use strict';

    const app = document.getElementById('invApp');
    if (!app) return;
    const PUEDE = {
        operar: app.dataset.operar === 'true',
        contar: app.dataset.contar === 'true',
        aprobar: app.dataset.aprobar === 'true',
        admin: app.dataset.admin === 'true'
    };
    const DIAS_SEP = parseInt(app.dataset.diasSeparacion || '7', 10);
    const cat = { empresas: [], sedes: [], registro: [], empresaDefecto: null, usuarioId: null, empresaActiva: null };
    // Empresas que se ven según la empresa elegida arriba (todas si se eligió "Todas las empresas")
    const empresasVista = () => cat.empresaActiva ? cat.empresas.filter(e => String(e.id) === String(cat.empresaActiva)) : cat.empresas;
    const pickers = {};
    let trasladoItems = [];
    let trasladosCache = [];
    let ultimoPlan = null;

    // ---------- utilidades ----------
    const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const soles = n => 'S/ ' + Number(n || 0).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const cant = n => Number(n || 0).toLocaleString('es-PE', { maximumFractionDigits: 2 });
    const num4 = n => n === null || n === undefined || n === '' ? '' : Number(n).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); // máximo 2 decimales (Erika 19/10)
    const fecha = v => {
        if (!v) return '—';
        const [d, h] = String(v).split(' ');
        return d.split('-').reverse().join('/') + (h ? ' ' + h.slice(0, 5) : '');   // DD/MM/AAAA HH:MM (hora de Lima)
    };
    const hoyISO = (masDias = 0) => {
        const d = new Date(Date.now() - new Date().getTimezoneOffset() * 60000 + masDias * 86400000);
        return d.toISOString().slice(0, 10);
    };
    const $ = id => document.getElementById(id);
    const nombreEmpresa = id => (cat.empresas.find(e => String(e.id) === String(id)) || {}).nombre || '?';
    const nombreSede = id => (cat.sedes.find(s => s.id === Number(id)) || {}).nombre || '?';

    // Aviso grande y claro (verde = listo, rojo = no se pudo, amarillo = queda pendiente)
    function aviso(msg, tipo) {
        let caja = document.getElementById('invAviso');
        if (!caja) {
            caja = document.createElement('div');
            caja.id = 'invAviso';
            document.body.appendChild(caja);
        }
        const icono = { success: '✔', error: '✖', warning: '⏳' }[tipo] || 'ℹ';
        caja.className = 'inv-aviso-flot ' + (tipo || 'info');
        caja.innerHTML = `<b>${icono}</b><span>${esc(msg)}</span><button type="button" aria-label="Cerrar">✕</button>`;
        caja.querySelector('button').onclick = () => caja.classList.remove('show');
        requestAnimationFrame(() => caja.classList.add('show'));
        clearTimeout(caja._t);
        caja._t = setTimeout(() => caja.classList.remove('show'), tipo === 'error' ? 9000 : 5000);
    }

    async function api(url, opciones = {}) {
        const resp = await fetch(url, {
            ...opciones,
            headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest', ...(opciones.headers || {}) }
        });
        const json = await resp.json().catch(() => ({}));
        if (resp.status === 401) { window.location.href = '/login'; throw new Error('Sesión expirada'); }
        if (!resp.ok || json.success === false) throw new Error(json.error || `Error ${resp.status}`);
        return json;
    }
    const post = (url, body) => api(url, { method: 'POST', body: JSON.stringify(body || {}) });

    const abrir = id => $(id).classList.add('show');
    const cerrar = id => $(id).classList.remove('show');
    document.addEventListener('click', e => {
        const c = e.target.closest('[data-close]');
        if (c) cerrar(c.dataset.close);
    });

    function bloquear(btn, si) {
        if (!btn) return;
        btn.disabled = si;
        if (si) { btn.dataset.txt = btn.textContent; btn.textContent = 'Guardando...'; }
        else if (btn.dataset.txt) btn.textContent = btn.dataset.txt;
    }

    async function guardarCon(btn, fn) {
        bloquear(btn, true);
        try { await fn(); } catch (e) { aviso(e.message, 'error'); } finally { bloquear(btn, false); }
    }

    // ---------- selector de producto (buscar y elegir) ----------
    function crearPicker(el) {
        const id = el.dataset.picker;
        el.innerHTML = `<input type="search" class="pp-input" placeholder="Escribe código, nombre, marca o modelo..." autocomplete="off">
                        <div class="pp-lista"></div>`;
        const input = el.querySelector('.pp-input');
        const lista = el.querySelector('.pp-lista');
        const p = { valor: null, texto: '', onChange: null };
        let t;
        input.addEventListener('input', () => {
            p.valor = null;
            el.classList.remove('pp-ok');
            clearTimeout(t);
            t = setTimeout(async () => {
                const q = input.value.trim();
                if (q.length < 2) { lista.innerHTML = ''; lista.style.display = 'none'; return; }
                try {
                    const { data } = await api('/inventario/api/productos?q=' + encodeURIComponent(q));
                    lista.innerHTML = data.length
                        ? data.map(x => `<div class="pp-op" data-id="${x.id}" data-txt="${esc(x.codigo + ' · ' + x.descripcion)}" data-costo="${x.costo_unitario || 0}">
                              <b>${esc(x.codigo || '')}</b> ${esc(x.descripcion)} <small>${esc([x.marca, x.modelo, x.unidad].filter(Boolean).join(' · '))}</small></div>`).join('')
                        : '<div class="pp-nada">No se encontró. Revisa el nombre o créalo en Productos.</div>';
                    lista.style.display = 'block';
                } catch (e) { lista.innerHTML = ''; }
            }, 250);
        });
        lista.addEventListener('click', e => {
            const op = e.target.closest('.pp-op');
            if (!op) return;
            p.set(Number(op.dataset.id), op.dataset.txt, Number(op.dataset.costo));
            lista.style.display = 'none';
        });
        document.addEventListener('click', e => { if (!el.contains(e.target)) lista.style.display = 'none'; });
        p.set = (valor, texto, costo) => {
            p.valor = valor; p.texto = texto || ''; p.costo = costo;
            input.value = texto || '';
            el.classList.toggle('pp-ok', !!valor);
            if (p.onChange) p.onChange(p);
        };
        p.limpiar = () => p.set(null, '');
        pickers[id] = p;
    }

    // ---------- catálogos (empresas y sedes configurables) ----------
    function llenarSelects() {
        document.querySelectorAll('select[data-empresas]').forEach(s => {
            const todas = s.dataset.todas === 'true';
            // Filtros: si arriba se eligió una empresa, solo se ve esa (con "Todas las empresas" se ve el grupo)
            const lista = todas && cat.empresaActiva ? empresasVista() : cat.empresas;
            s.innerHTML = (todas && !cat.empresaActiva ? '<option value="">Todas las empresas</option>' : '') +
                lista.map(e => `<option value="${e.id}">${esc(e.nombre)}</option>`).join('');
            if (!todas && cat.empresaDefecto) s.value = cat.empresaDefecto;
        });
        document.querySelectorAll('select[data-sedes]').forEach(s => {
            const todas = s.dataset.todas === 'true';
            s.innerHTML = (todas ? '<option value="">Todas las sedes</option>' : '') +
                cat.sedes.map(x => `<option value="${x.id}">${esc(x.nombre)}</option>`).join('');
        });
        if (cat.sedes.length > 1 && $('traDestino')) $('traDestino').value = cat.sedes[1].id;
        if (cat.empresas.length > 1 && $('icCompra')) $('icCompra').value = cat.empresas.find(e => String(e.id) !== String($('icVende').value))?.id || '';
    }

    async function cargarCatalogos() {
        const r = await api('/inventario/api/catalogos');
        cat.empresas = r.empresas; cat.sedes = r.sedes; cat.registro = r.registro_sunat;
        cat.empresaDefecto = r.empresa_defecto; cat.usuarioId = r.usuario_id; cat.empresaActiva = r.empresa_activa || null;
        llenarSelects();
        if (!cat.empresas.length || !cat.sedes.length) {
            $('resAlertas').innerHTML = `<div class="inv-alerta danger"><b>Falta configurar.</b> Crea las empresas en Configuración ▸ Empresas
                y las sedes (almacenes) en Maestros ▸ Almacenes. Sin eso no se puede registrar stock.</div>`;
        }
    }

    // ========================================================
    // QUÉ REVISAR HOY
    // ========================================================
    async function cargarResumen() {
        try {
            const { data } = await api('/inventario/api/resumen');
            $('kpiValor').textContent = soles(data.valor_total);
            $('kpiProductos').textContent = `${data.productos_con_stock} productos con stock`;
            $('kpiLento').textContent = data.lento;
            $('kpiLentoTxt').textContent = `Sin venta entre ${data.dias_lento} y ${data.dias_inmovilizado} días`;
            $('kpiInmovil').textContent = data.inmovilizado;
            $('kpiInmovilTxt').textContent = `${soles(data.valor_inmovilizado)} sin venta hace +${data.dias_inmovilizado} días`;
            $('kpiPerdidas').textContent = soles(data.valor_perdidas_mes);
            $('kpiPendientes').textContent = data.pendientes.length;

            // Tarjetas por empresa y sede
            const porEmpresa = {};
            data.por_ubicacion.forEach(u => { (porEmpresa[u.empresa] = porEmpresa[u.empresa] || []).push(u); });
            $('resUbicaciones').innerHTML = Object.entries(porEmpresa).map(([emp, us]) => `
                <div class="inv-ubic">
                    <div class="inv-ubic-emp">${esc(emp)} <span>${soles(us.reduce((a, u) => a + u.valor, 0))}</span></div>
                    ${us.map(u => `<div class="inv-ubic-sede"><span>📍 ${esc(u.sede)}</span><b>${cant(u.unidades)} und · ${soles(u.valor)}</b></div>`).join('')}
                </div>`).join('');

            const al = [];
            const item = (nivel, titulo, detalle, accion) => al.push(`<div class="inv-alerta ${nivel}"><div><b>${titulo}</b><div>${detalle}</div></div>${accion || ''}</div>`);

            if (data.pendientes.length) {
                item('warn', `🕒 ${data.pendientes.length} movimiento(s) esperan aprobación`,
                    data.pendientes.map(p => `${esc(p.numero)} · ${esc(p.motivo_texto)} · ${cant(p.cantidad)} ${esc(p.descripcion)} (${esc(p.empresa)} / ${esc(p.sede)}) — reportó ${esc(p.usuario_nombre)}: <i>${esc(p.observaciones || '')}</i>
                        ${PUEDE.aprobar ? `<span class="inv-acc"><button class="btn-mini" data-aprobar="${p.id}">Aprobar</button><button class="btn-mini danger" data-rechazar="${p.id}">Rechazar</button></span>` : ''}`).join('<br>'));
            }
            if (data.sin_ubicar.length) {
                item('danger', `📦 ${data.sin_ubicar.length} producto(s) con stock antiguo sin empresa ni sede`,
                    'Se registraron antes del nuevo inventario. Hay que decir de qué empresa son y dónde están: ' +
                    data.sin_ubicar.slice(0, 8).map(s => `<button class="btn-link" data-ubicar='${esc(JSON.stringify({ id: s.id, txt: s.codigo + ' · ' + s.descripcion, stock: s.stock, costo: s.costo_unitario }))}'>${esc(s.descripcion)} (${cant(s.stock)})</button>`).join(', ') +
                    (data.sin_ubicar.length > 8 ? ` y ${data.sin_ubicar.length - 8} más.` : ''));
            }
            if (data.traslados_demorados.length) {
                item('danger', `🚚 ${data.traslados_demorados.length} traslado(s) en camino hace más de 24 horas`,
                    data.traslados_demorados.map(t => `${esc(t.numero)}: ${esc(t.origen)} → ${esc(t.destino)} (lleva ${esc(t.encargado)})`).join('<br>'),
                    '<button class="btn-mini sec" data-ir="transferencias">Ver traslados</button>');
            }
            if (data.perdidas_mes.length) {
                item('danger', `🚨 Pérdidas y faltantes este mes: ${soles(data.valor_perdidas_mes)}`,
                    data.perdidas_mes.map(p => `${fecha(p.fecha)} · ${esc(p.descripcion)} · ${cant(p.cantidad)} und · ${esc(p.empresa)} / ${esc(p.sede)} · ${esc(p.observaciones || '')}`).join('<br>'));
            }
            const vs = data.vencimientos_semaforo || {};
            if (vs.vencido || vs.rojo || vs.amarillo) {
                item(vs.vencido || vs.rojo ? 'danger' : 'warn', `⏳ Por vencer: ${vs.vencido} vencido(s) · ${vs.rojo} en rojo (3 meses) · ${vs.amarillo} en amarillo (6 meses)`,
                    'Planea campañas para venderlos antes de que se pierdan.',
                    '<button class="btn-mini sec" data-ir="vencimientos">Ver vencimientos</button>');
            }
            if (data.vencimientos.length) {
                item('warn', `⏳ ${data.vencimientos.length} lote(s) vencidos o por vencer`,
                    data.vencimientos.map(v => `${v.vencido ? '<b class="neg">VENCIDO</b>' : 'Vence'} ${fecha(v.fecha_vencimiento)} · ${esc(v.descripcion)} · ${cant(v.cantidad)} und · lote ${esc(v.lote_serie || '-')} · ${esc(nombreEmpresa(v.empresa_id))} / ${esc(nombreSede(v.almacen_id))}`).join('<br>'));
            }
            if (data.separaciones_vencidas.length) {
                item('warn', `🔓 ${data.separaciones_vencidas.length} separación(es) vencida(s)`,
                    'Ya no bloquean stock. Confirma con el cliente o libéralas: ' + data.separaciones_vencidas.map(s => `${esc(s.numero)} (${esc(s.cliente)})`).join(', '),
                    '<button class="btn-mini sec" data-ir="separaciones">Ver separaciones</button>');
            }
            if (data.intercompany_sin_factura) {
                item('warn', `🧾 ${data.intercompany_sin_factura} venta(s) entre empresas sin número de factura`,
                    'SUNAT exige la factura en cada venta entre empresas del grupo.', '<button class="btn-mini sec" data-ir="transferencias">Completar</button>');
            }
            if (data.sedes_no_declaradas.length) {
                item('warn', '🏛️ Mercadería en una sede no declarada en SUNAT para esa empresa',
                    data.sedes_no_declaradas.map(s => `${esc(s.empresa)} tiene ${cant(s.unidades)} und (${soles(s.valor)}) en ${esc(s.sede)}`).join('<br>') +
                    '<br><small>Recomendación: declarar esa dirección como establecimiento anexo (consúltalo con tu contador). Ver pestaña "Sedes y SUNAT".</small>');
            }
            if (data.sin_conteo_30_dias.length) {
                item('info', '✅ Sedes sin conteo en los últimos 30 días',
                    data.sin_conteo_30_dias.map(s => `${esc(s.empresa)} / ${esc(s.sede)} (último: ${s.ultimo ? fecha(s.ultimo) : 'nunca'})`).join('<br>'),
                    PUEDE.contar ? '<button class="btn-mini sec" data-ir="conteos">Programar conteo</button>' : '');
            }
            if (data.conteos_abiertos.length) {
                item('info', `📝 Conteos abiertos: ${data.conteos_abiertos.map(c => `${esc(c.numero)} (${esc(c.estado)})`).join(', ')}`, '',
                    '<button class="btn-mini sec" data-ir="conteos">Ir a conteos</button>');
            }
            if (data.inmovilizado) {
                item('info', `🐢 ${data.inmovilizado} producto(s) inmovilizado(s) por ${soles(data.valor_inmovilizado)}`,
                    'Ofrécelos a clientes o revisa por qué no salen. En "Stock consolidado" filtra por "Inmovilizado".',
                    '<button class="btn-mini sec" data-ir="estado_stock" data-rot="Inmovilizado">Ver lista</button>');
            }
            $('resAlertas').innerHTML = al.length ? al.join('') : '<div class="inv-alerta ok"><b>✔ Todo en orden.</b><div>No hay nada pendiente por revisar.</div></div>';
        } catch (e) {
            $('resAlertas').innerHTML = `<div class="inv-alerta danger">No se pudo cargar: ${esc(e.message)}</div>`;
        }
    }

    // ========================================================
    // STOCK CONSOLIDADO
    // ========================================================
    async function cargarConsolidado() {
        const params = new URLSearchParams({ q: $('conBuscar').value.trim(), rotacion: $('conRotacion').value, todos: $('conTodos').checked });
        $('conExportar').href = '/inventario/api/consolidado/exportar?q=' + encodeURIComponent($('conBuscar').value.trim());
        const E = empresasVista(), S = cat.sedes;
        $('conHead').innerHTML = `
            <tr><th rowspan="2" class="left">Producto</th>
                ${E.map(e => `<th colspan="${S.length + 1}" class="emp-col">${esc(e.nombre)}</th>`).join('')}
                <th rowspan="2" class="tot-col">TOTAL<br>GRUPO</th><th rowspan="2">Separado</th><th rowspan="2" class="disp-col">Disponible</th>
                <th rowspan="2">Valor</th><th rowspan="2">Rotación</th><th rowspan="2">Ver</th></tr>
            <tr>${E.map(() => S.map(s => `<th class="sede-col">${esc(s.nombre)}</th>`).join('') + '<th class="emp-tot">Total</th>').join('')}</tr>`;
        const ncols = 7 + E.length * (S.length + 1);
        $('conBody').innerHTML = `<tr><td colspan="${ncols}">Cargando...</td></tr>`;
        try {
            const r = await api('/inventario/api/consolidado?' + params);
            const data = r.data;
            const pend = r.pendientes || { cantidad: 0 };
            $('conPendientes').innerHTML = pend.cantidad ? `<div class="inv-alerta warn"><div><b>🕒 ${pend.cantidad} movimiento(s) esperan aprobación (${cant(pend.unidades)} und)</b>
                <div>Todavía NO suman al stock. Un supervisor debe aprobarlos en "Resumen".</div></div>
                <button class="btn-mini sec" data-ir="resumen">Ver y aprobar</button></div>` : '';
            if (!data.length) {
                $('conBody').innerHTML = `<tr><td colspan="${ncols}">${$('conTodos').checked ? 'No hay productos para este filtro.' : 'No hay productos con stock para este filtro. Marca "Ver también sin stock" para ver todos los productos.'}</td></tr>`;
                $('conFoot').textContent = '';
                return;
            }
            $('conBody').innerHTML = data.map(p => {
                const celdas = E.map(e => S.map(s => {
                    const c = p.celdas[`${e.id}-${s.id}`];
                    if (!c || !c.cantidad) return '<td class="num cero">0</td>';
                    return `<td class="num" title="Disponible ${cant(c.disponible)} · separado ${cant(c.separado)}">${cant(c.cantidad)}${c.separado ? `<small class="sep">(${cant(c.separado)} sep.)</small>` : ''}</td>`;
                }).join('') + `<td class="num emp-tot">${cant(p.por_empresa[e.id] || 0)}</td>`).join('');
                const dondeTxt = Object.entries(p.celdas).filter(([, c]) => c.cantidad > 0)
                    .map(([k, c]) => { const i = k.lastIndexOf('-'), e = k.slice(0, i), s = k.slice(i + 1); return `${cant(c.cantidad)} ${nombreEmpresa(e)} en ${nombreSede(s)}`; }).join(' · ');
                const bajo = p.stock_minimo > 0 && p.total < p.stock_minimo;
                return `<tr>
                    <td class="left"><b>${esc(p.codigo || '')}</b> ${esc(p.descripcion)}<div class="inv-donde-linea">📍 ${esc(dondeTxt || 'Sin stock')}</div></td>
                    ${celdas}
                    <td class="num tot-col">${cant(p.total)} ${esc(p.unidad || '')}${bajo ? '<small class="neg"> bajo mínimo</small>' : ''}</td>
                    <td class="num">${p.separado ? cant(p.separado) : '—'}</td>
                    <td class="num disp-col">${cant(p.disponible)}</td>
                    <td class="num">${soles(p.valor)}</td>
                    <td><span class="rot rot-${(p.rotacion || '').toLowerCase().replace(/\s+/g, '-')}">${esc(p.rotacion)}</span>${p.dias_sin_vender != null && p.total > 0 ? `<small class="dias">${p.dias_sin_vender} días sin vender</small>` : ''}</td>
                    <td><button class="btn-mini sec" data-kardex="${p.producto_id}" data-txt="${esc(p.codigo + ' · ' + p.descripcion)}">Kardex</button>
                        <button class="btn-mini sec" data-donde="${p.producto_id}" data-txt="${esc(p.codigo + ' · ' + p.descripcion)}">¿Dónde?</button>
                        ${!p.total && PUEDE.operar ? `<button class="btn-mini" data-stock-inicial="${p.producto_id}" data-txt="${esc(p.codigo + ' · ' + p.descripcion)}">➕ Stock inicial</button>` : ''}</td>
                </tr>`;
            }).join('');
            const tot = data.reduce((a, p) => ({ u: a.u + p.total, v: a.v + p.valor }), { u: 0, v: 0 });
            const conStock = data.filter(p => p.total > 0).length;
            $('conFoot').textContent = `${data.length} productos (${conStock} con stock) · ${cant(tot.u)} unidades · ${soles(tot.v)} al costo promedio`;
        } catch (e) {
            $('conBody').innerHTML = `<tr><td colspan="${ncols}" class="neg">No se pudo cargar: ${esc(e.message)}</td></tr>`;
        }
    }

    // ========================================================
    // ¿DÓNDE ESTÁ?
    // ========================================================
    async function ubicar() {
        const p = pickers.donde;
        if (!p.valor) { aviso('Elige un producto de la lista.', 'error'); return; }
        const params = new URLSearchParams({ producto_id: p.valor, cantidad: $('dondeCantidad').value || 0,
            empresa_id: $('dondeEmpresa').value, almacen_id: $('dondeSede').value });
        try {
            const r = await api('/inventario/api/ubicar?' + params);
            const sedeDesp = nombreSede($('dondeSede').value), empVenta = nombreEmpresa($('dondeEmpresa').value);
            const total = r.lugares.reduce((a, l) => a + l.disponible, 0);
            let html = `<div class="inv-subtitulo">${esc(p.texto)}: ${cant(total)} disponibles en todo el grupo</div>
                <div class="inv-lugares">${r.lugares.length ? r.lugares.map(l => `
                    <div class="inv-lugar ${Number(l.almacen_id) === Number($('dondeSede').value) ? 'aqui' : ''}">
                        <small>${esc(l.empresa)}</small><b>📍 ${esc(l.sede)}</b>
                        <span>${cant(l.disponible)} disponibles</span>${l.separado ? `<em>${cant(l.separado)} separados</em>` : ''}
                    </div>`).join('') : '<div class="inv-vacio">No hay stock de este producto en ninguna sede. Hay que comprarlo (pedido al proveedor).</div>'}</div>`;
            const pedido = Number($('dondeCantidad').value || 0);
            if (pedido > 0) {
                ultimoPlan = { producto_id: p.valor, almacen_id: Number($('dondeSede').value), plan: r.plan };
                const pasos = r.plan.map((x, i) => {
                    const txt = [];
                    if (x.pasos.includes('traslado')) txt.push(`traer de <b>${esc(x.sede)}</b> a <b>${esc(sedeDesp)}</b> (traslado con guía)`);
                    else txt.push(`ya está en <b>${esc(sedeDesp)}</b>`);
                    if (x.pasos.includes('intercompany')) txt.push(`<b>${esc(x.empresa)}</b> se lo vende a <b>${esc(empVenta)}</b> (factura intercompany)`);
                    return `<li><b>${cant(x.tomar)} und</b> de ${esc(x.empresa)}: ${txt.join(' y ')}</li>`;
                }).join('');
                const hayTraslado = r.plan.some(x => x.pasos.includes('traslado'));
                html += `<div class="inv-plan ${r.alcanza ? 'ok' : 'falta'}">
                    <div class="inv-subtitulo">${r.alcanza ? `✔ Sí alcanza para ${cant(pedido)}` : `✖ Faltan ${cant(r.falta)} unidades: hay que pedir al proveedor`}</div>
                    <ol>${pasos}</ol>
                    ${hayTraslado ? `<div class="inv-aviso">⚠ No mandes al cliente a ${esc(sedeDesp)} hasta que lleguen los traslados. Si no, irá y no encontrará todo.</div>` : `<div class="inv-ok">El cliente puede recoger todo en ${esc(sedeDesp)}.</div>`}
                    ${hayTraslado && PUEDE.operar ? `<div class="inv-linea"><input type="text" id="juntarEncargado" placeholder="¿Quién recogerá la mercadería?" maxlength="150">
                        <button class="btn btn-primary" id="btnJuntar">🚚 Crear traslados para juntar todo en ${esc(sedeDesp)}</button></div>` : ''}
                    ${r.plan.some(x => x.pasos.includes('intercompany')) && PUEDE.operar ? '<button class="btn btn-secondary" data-ir="transferencias" data-ic="1">🧾 Registrar venta entre empresas</button>' : ''}
                    ${r.alcanza ? `<button class="btn btn-secondary" id="btnSepararDesde">🔒 Separar para el cliente</button>` : ''}
                </div>`;
            }
            $('dondeResultado').innerHTML = html;
        } catch (e) { aviso(e.message, 'error'); }
    }

    // ========================================================
    // ENTRADAS / SALIDAS / PROBLEMAS
    // ========================================================
    const AYUDA_MOV = {
        ENTRADA: '📥 Usa esto cuando la mercadería <b>llega</b>. Cuenta lo que llegó antes de registrar.',
        SALIDA: '📤 Usa esto cuando la mercadería <b>sale</b> hacia un cliente o proveedor. Siempre con guía o factura.',
        PROBLEMA: '⚠️ Reporta aquí un producto dañado, vencido, perdido o robado. Queda <b>pendiente</b> hasta que un supervisor lo apruebe.'
    };

    function abrirMovimiento(clase, prefill) {
        $('movTitulo').textContent = { ENTRADA: 'Registrar entrada', SALIDA: 'Registrar salida', PROBLEMA: 'Reportar un problema' }[clase];
        $('movAyuda').innerHTML = AYUDA_MOV[clase];
        $('movMotivo').innerHTML = window.INV_MOTIVOS[clase].map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join('');
        ['movCantidad', 'movCosto', 'movDoc', 'movTercero', 'movLote', 'movVenc', 'movObs', 'movRecepcion'].forEach(i => { $(i).value = ''; });
        pickers.mov.limpiar();
        $('movEmpresa').value = cat.empresaDefecto || '';
        app.dataset.claseMov = clase;
        if (prefill) {
            if (prefill.motivo) $('movMotivo').value = prefill.motivo;
            if (prefill.producto_id) pickers.mov.set(prefill.producto_id, prefill.texto, prefill.costo);
            if (prefill.cantidad) $('movCantidad').value = prefill.cantidad;
            if (prefill.costo != null) $('movCosto').value = prefill.costo;
            if (prefill.documento) $('movDoc').value = prefill.documento;
            if (prefill.docTipo) $('movDocTipo').value = prefill.docTipo;
            if (prefill.tercero) $('movTercero').value = prefill.tercero;
            if (prefill.recepcion_id) $('movRecepcion').value = prefill.recepcion_id;
            if (prefill.obs) $('movObs').value = prefill.obs;
            if (prefill.empresa) $('movEmpresa').value = prefill.empresa;
            if (prefill.sede) $('movSede').value = prefill.sede;
            if (prefill.lote) $('movLote').value = prefill.lote;
            if (prefill.venc) $('movVenc').value = prefill.venc;
        }
        // Lo recibido en Compras se ingresa tal como se recibió (misma empresa, sede y producto)
        const fijo = !!(prefill && prefill.fijo);
        ['movEmpresa', 'movSede', 'movMotivo'].forEach(i => { $(i).disabled = fijo; });
        document.querySelector('[data-picker="mov"] .pp-input').disabled = fijo;
        ajustarFormMovimiento();
        abrir('movModal');
    }

    function ajustarFormMovimiento() {
        const clase = app.dataset.claseMov, motivo = $('movMotivo').value;
        const entrada = clase === 'ENTRADA';
        const conDoc = ['COMPRA', 'DEVOLUCION_CLIENTE', 'VENTA', 'DEVOLUCION_PROVEEDOR'].includes(motivo);
        $('movCostoWrap').style.display = entrada ? '' : 'none';
        $('movDocTipoWrap').style.display = conDoc ? '' : 'none';
        $('movDocWrap').style.display = conDoc ? '' : 'none';
        $('movTerceroWrap').style.display = clase === 'PROBLEMA' ? 'none' : '';
        $('movVencWrap').style.display = entrada ? '' : 'none';
        $('movSepWrap').style.display = motivo === 'VENTA' ? '' : 'none';
        const tips = {
            COMPRA: 'El N° de documento es la guía o factura del proveedor. El costo es sin IGV.',
            DEVOLUCION_CLIENTE: 'Escribe la nota de crédito o guía de devolución. Revisa que el producto esté en buen estado.',
            STOCK_INICIAL: 'Solo para cargar el stock que ya existía. Un supervisor debe aprobarlo.',
            VENTA: 'Si el cliente tenía stock separado, elige su separación. Sin separación, el sistema no deja entregar unidades separadas para otro cliente.',
            DEVOLUCION_PROVEEDOR: 'Escribe la guía de devolución.',
            MERMA: 'Describe el daño. Si puedes, toma una foto y guárdala con el número del movimiento.',
            VENCIMIENTO: 'Escribe el lote y la fecha de vencimiento en las observaciones.',
            PERDIDA_ROBO: 'Describe qué se perdió, cuándo se notó y quién estaba a cargo. Avísale a tu supervisor.'
        };
        $('movTip').textContent = '💡 ' + (tips[motivo] || '');
        if (motivo === 'COMPRA') $('movDocTipo').value = $('movDocTipo').value || 'Guía de remisión';
        if (motivo === 'VENTA') cargarSeparacionesMov();
    }

    async function cargarSeparacionesMov() {
        const sel = $('movSeparacion');
        sel.innerHTML = '<option value="">Sin separación</option>';
        if (!pickers.mov.valor) return;
        try {
            const params = new URLSearchParams({ producto_id: pickers.mov.valor, empresa_id: $('movEmpresa').value, almacen_id: $('movSede').value });
            const { data } = await api('/inventario/api/separaciones?' + params);
            sel.innerHTML += data.filter(s => !s.vencida).map(s => `<option value="${s.id}" data-cliente="${esc(s.cliente)}">${esc(s.numero)} · ${esc(s.cliente)} · ${cant(s.cantidad)} und</option>`).join('');
        } catch (e) { /* sin separaciones */ }
    }

    async function guardarMovimiento() {
        const body = {
            motivo: $('movMotivo').value, producto_id: pickers.mov.valor, empresa_id: $('movEmpresa').value,
            almacen_id: $('movSede').value, cantidad: $('movCantidad').value,
            costo_unitario: app.dataset.claseMov === 'ENTRADA' ? $('movCosto').value : null,
            documento_tipo: $('movDocTipoWrap').style.display === 'none' ? null : $('movDocTipo').value,
            documento_numero: $('movDoc').value, tercero: $('movTercero').value, lote_serie: $('movLote').value,
            fecha_vencimiento: $('movVenc').value || null, observaciones: $('movObs').value,
            recepcion_id: $('movRecepcion').value || null,
            separacion_id: $('movSepWrap').style.display === 'none' ? null : ($('movSeparacion').value || null)
        };
        if (!body.producto_id) { aviso('Elige el producto de la lista.', 'error'); return; }
        await guardarCon($('movGuardar'), async () => {
            const r = await post('/inventario/api/movimientos', body);
            aviso(r.message, r.pendiente ? 'warning' : 'success');
            cerrar('movModal');
            refrescar();
        });
    }

    async function cargarRecepciones() {
        try {
            const { data } = await api('/inventario/api/recepciones_pendientes');
            $('recBody').innerHTML = data.length ? data.map(r => `<tr>
                <td>${esc(r.numero_recepcion)}</td><td>${fecha(r.fecha)}</td><td class="left">${esc(r.producto)}${r.desde_compras ? `<small>${esc(nombreEmpresa(r.empresa_id))} · ${esc(nombreSede(r.almacen_id))}${r.cliente ? ' · para ' + esc(r.cliente) : ' · para stock'}</small>` : ''}</td>
                <td class="num">${cant(r.cantidad)} ${esc(r.unidad || '')}</td><td class="left">${esc(r.proveedor_nombre || '')}</td><td>${esc(r.orden_compra || '')}</td>
                <td>${PUEDE.operar ? `<button class="btn-mini" data-rec='${esc(JSON.stringify(r))}'>Ingresar</button>` : '—'}</td></tr>`).join('')
                : '<tr><td colspan="7">No hay recepciones pendientes de ingresar. 👍</td></tr>';
        } catch (e) { $('recBody').innerHTML = `<tr><td colspan="7" class="neg">${esc(e.message)}</td></tr>`; }
    }

    async function cargarMovimientos() {
        const params = new URLSearchParams({ estado: $('movEstado').value, q: $('movBuscar').value.trim() });
        try {
            const { data } = await api('/inventario/api/kardex?' + params);
            $('movBody').innerHTML = data.length ? data.slice(0, 200).map(m => {
                let acc = '—';
                if (m.estado === 'Pendiente' && PUEDE.aprobar) acc = `<button class="btn-mini" data-aprobar="${m.id}">Aprobar</button> <button class="btn-mini danger" data-rechazar="${m.id}">Rechazar</button>`;
                else if (m.estado === 'Registrado' && PUEDE.aprobar && !m.revertido_por_id && !m.revierte_id && !m.traslado_id && !m.conteo_id && !m.grupo)
                    acc = `<button class="btn-mini danger" data-revertir="${m.id}" data-num="${esc(m.numero)}">Corregir</button>`;
                else if (m.revertido_por_id) acc = '<small>Corregido</small>';
                return `<tr class="${m.tipo === 'ENTRADA' ? 'fila-in' : 'fila-out'}">
                    <td>${esc(m.numero)}</td><td>${fecha(m.fecha)}</td><td><span class="tipo tipo-${m.tipo.toLowerCase()}">${m.tipo === 'ENTRADA' ? '📥 Entrada' : '📤 Salida'}</span></td>
                    <td class="left">${esc(m.motivo_texto)}</td><td class="left">${esc(m.codigo)} · ${esc(m.descripcion)}${m.lote_serie ? `<small> · ${esc(m.lote_serie)}</small>` : ''}</td>
                    <td>${esc(m.empresa)}</td><td>${esc(m.sede)}</td><td class="num">${cant(m.cantidad)}</td>
                    <td>${esc([m.documento_tipo, m.documento_numero].filter(Boolean).join(' '))}</td><td class="left">${esc(m.tercero || '')}</td>
                    <td>${esc(m.usuario_nombre || '')}${m.aprobado_por ? `<small>Aprobó: ${esc(m.aprobado_por)}</small>` : ''}</td>
                    <td><span class="est est-${m.estado.toLowerCase()}">${esc(m.estado)}</span>${m.motivo_rechazo ? `<small>${esc(m.motivo_rechazo)}</small>` : ''}</td><td>${acc}</td></tr>`;
            }).join('') : '<tr><td colspan="13">No hay movimientos para este filtro.</td></tr>';
        } catch (e) { $('movBody').innerHTML = `<tr><td colspan="13" class="neg">${esc(e.message)}</td></tr>`; }
    }

    // Ventana de motivo reutilizable
    function pedirMotivo(titulo, ayuda, fn) {
        $('motivoTitulo').textContent = titulo;
        $('motivoAyuda').innerHTML = ayuda;
        $('motivoTexto').value = '';
        $('motivoOk').onclick = () => guardarCon($('motivoOk'), async () => { await fn($('motivoTexto').value.trim()); cerrar('motivoModal'); });
        abrir('motivoModal');
    }

    // ========================================================
    // TRASLADOS
    // ========================================================
    async function cargarTraslados() {
        try {
            const { data } = await api('/inventario/api/traslados?estado=' + encodeURIComponent($('traEstado').value));
            trasladosCache = data;
            $('traBody').innerHTML = data.length ? data.map(t => {
                let acc = '—';
                if (t.estado === 'En camino') {
                    const mismo = t.enviado_por_id === cat.usuarioId && !PUEDE.admin;
                    acc = (PUEDE.operar ? `<button class="btn-mini" data-recibir="${t.id}" ${mismo ? 'disabled title="Debe recibirlo otra persona"' : ''}>Recibir</button> ` : '') +
                        (PUEDE.aprobar ? `<button class="btn-mini danger" data-anular-tra="${t.id}" data-num="${esc(t.numero)}">Anular</button>` : '');
                }
                const items = (t.items || []).map(i => `${cant(i.cantidad)} ${esc(i.descripcion)}${i.cantidad_recibida != null && Number(i.cantidad_recibida) !== Number(i.cantidad) ? ` <b class="neg">(llegó ${cant(i.cantidad_recibida)})</b>` : ''}`).join('<br>');
                return `<tr><td>${esc(t.numero)}</td><td>${fecha(t.fecha)}</td><td>${esc(t.empresa)}</td><td>${esc(t.origen)}</td><td>${esc(t.destino)}</td>
                    <td class="left">${items}</td><td>${esc(t.guia_remision || '') || '<span class="neg">Sin guía</span>'}</td><td>${esc(t.encargado || '')}</td>
                    <td>${esc(t.enviado_por || '')}</td><td>${esc(t.recibido_por || '')}${t.recibido_en ? `<small>${fecha(t.recibido_en)}</small>` : ''}</td>
                    <td><span class="est est-${t.estado.toLowerCase().replace(/\s+/g, '-')}">${esc(t.estado)}</span>${t.horas_en_camino > 24 ? `<small class="neg">${t.horas_en_camino} h</small>` : ''}</td><td>${acc}</td></tr>`;
            }).join('') : '<tr><td colspan="12">No hay traslados.</td></tr>';
        } catch (e) { $('traBody').innerHTML = `<tr><td colspan="12" class="neg">${esc(e.message)}</td></tr>`; }
    }

    function pintarItemsTraslado() {
        $('traItems').innerHTML = trasladoItems.length ? trasladoItems.map((i, n) => `<tr><td class="left">${esc(i.texto)}</td><td class="num">${cant(i.cantidad)}</td>
            <td><button class="btn-mini danger" data-quitar-item="${n}">Quitar</button></td></tr>`).join('') : '<tr><td colspan="3">Agrega productos.</td></tr>';
    }

    function abrirRecibir(id) {
        const t = trasladosCache.find(x => x.id === id);
        if (!t) return;
        $('recTraTitulo').textContent = `Recibir ${t.numero} (${t.origen} → ${t.destino})`;
        $('recTraItems').innerHTML = t.items.map(i => `<tr><td class="left">${esc(i.descripcion)}</td><td class="num">${cant(i.cantidad)}</td>
            <td><input type="number" min="0" step="any" class="inp-num" data-item="${i.id}" placeholder="Contar"></td></tr>`).join('');
        $('recTraObs').value = '';
        $('recTraGuardar').onclick = () => {
            const recibido = {};
            $('recTraItems').querySelectorAll('input[data-item]').forEach(inp => { recibido[inp.dataset.item] = inp.value; });
            guardarCon($('recTraGuardar'), async () => {
                const r = await post(`/inventario/api/traslados/${id}/recibir`, { recibido, observaciones: $('recTraObs').value });
                aviso(r.message, 'success'); cerrar('recTraModal'); refrescar();
            });
        };
        abrir('recTraModal');
    }

    async function cargarIntercompany() {
        try {
            const { data } = await api('/inventario/api/intercompany');
            $('icBody').innerHTML = data.length ? data.map(x => `<tr><td>${esc(x.grupo)}</td><td>${fecha(x.fecha)}</td><td>${esc(x.vende)}</td><td>${esc(x.compra)}</td>
                <td>${esc(x.sede)}</td><td class="left">${esc(x.codigo)} · ${esc(x.descripcion)}</td><td class="num">${cant(x.cantidad)}</td><td class="num">${num4(x.precio)}</td>
                <td>${x.factura ? esc(x.factura) : (PUEDE.operar ? `<button class="btn-mini danger" data-factura-ic="${esc(x.grupo)}">Falta factura</button>` : '<span class="neg">Falta</span>')}</td>
                <td>${esc(x.usuario || '')}</td></tr>`).join('') : '<tr><td colspan="10">No hay ventas entre empresas registradas.</td></tr>';
        } catch (e) { $('icBody').innerHTML = `<tr><td colspan="10" class="neg">${esc(e.message)}</td></tr>`; }
    }

    // ========================================================
    // SEPARACIONES
    // ========================================================
    async function cargarSeparaciones() {
        try {
            const { data } = await api('/inventario/api/separaciones?estado=' + encodeURIComponent($('sepEstado').value));
            $('sepBody').innerHTML = data.length ? data.map(s => `<tr>
                <td>${esc(s.numero)}</td><td class="left">${esc(s.cliente)}</td><td class="left">${esc(s.codigo)} · ${esc(s.descripcion)}</td>
                <td>${esc(s.empresa)}</td><td>${esc(s.sede)}</td><td class="num">${cant(s.cantidad)}${Number(s.cantidad) !== Number(s.cantidad_inicial) ? `<small>de ${cant(s.cantidad_inicial)}</small>` : ''}</td>
                <td>${esc(s.documento || '')}</td><td class="${s.vencida && s.estado === 'Activa' ? 'neg' : ''}">${fecha(s.vence_el)}${s.vencida && s.estado === 'Activa' ? '<small>Vencida</small>' : ''}</td>
                <td>${esc(s.usuario_nombre || '')}</td><td><span class="est est-${s.estado.toLowerCase()}">${esc(s.estado)}</span></td>
                <td>${s.estado === 'Activa' ? `<button class="btn-mini sec" data-liberar="${s.id}">Liberar</button>` : '—'}</td></tr>`).join('')
                : '<tr><td colspan="11">No hay separaciones para este filtro.</td></tr>';
        } catch (e) { $('sepBody').innerHTML = `<tr><td colspan="11" class="neg">${esc(e.message)}</td></tr>`; }
    }

    function abrirSeparacion(prefill) {
        pickers.sep.limpiar();
        ['sepCantidad', 'sepCliente', 'sepDoc', 'sepObs'].forEach(i => { $(i).value = ''; });
        $('sepVence').value = hoyISO(DIAS_SEP);
        $('sepTip').textContent = `💡 Por defecto se separa por ${DIAS_SEP} días. Al entregar, elige esta separación en "Registrar salida".`;
        if (prefill) {
            pickers.sep.set(prefill.producto_id, prefill.texto);
            if (prefill.empresa_id) $('sepEmpresa').value = prefill.empresa_id;
            if (prefill.almacen_id) $('sepSede').value = prefill.almacen_id;
            if (prefill.cantidad) $('sepCantidad').value = prefill.cantidad;
        }
        abrir('sepModal');
    }

    // ========================================================
    // CONTEOS
    // ========================================================
    async function cargarConteos() {
        try {
            const { data } = await api('/inventario/api/conteos');
            $('cntBody').innerHTML = data.length ? data.map(c => {
                let acc = `<button class="btn-mini sec" data-ver-conteo="${c.id}">Ver</button>`;
                if (c.estado === 'En conteo' && PUEDE.contar) acc = `<button class="btn-mini" data-ver-conteo="${c.id}">Contar</button>`;
                if (c.estado === 'Por aprobar' && PUEDE.aprobar) acc = `<button class="btn-mini" data-ver-conteo="${c.id}">Revisar</button>`;
                const dif = c.estado === 'En conteo' ? '—' : `<span class="${Number(c.valor_diferencia) < 0 ? 'neg' : ''}">${soles(c.valor_diferencia)}</span>`;
                return `<tr><td>${esc(c.numero)}</td><td>${fecha(c.fecha)}</td><td>${esc(c.tipo)}</td><td>${esc(c.empresa)}</td><td>${esc(c.sede)}</td>
                    <td class="num">${c.productos}</td><td>${esc(c.contado_por || '')}</td><td class="num">${c.estado === 'En conteo' ? '—' : c.con_diferencia}</td>
                    <td class="num">${dif}</td><td>${esc(c.aprobado_por || '')}</td><td><span class="est est-${c.estado.toLowerCase().replace(/\s+/g, '-')}">${esc(c.estado)}</span></td><td>${acc}</td></tr>`;
            }).join('') : '<tr><td colspan="12">Aún no hay conteos. Haz uno sorpresa cada semana: toma 10 minutos.</td></tr>';
        } catch (e) { $('cntBody').innerHTML = `<tr><td colspan="12" class="neg">${esc(e.message)}</td></tr>`; }
    }

    async function verConteo(id) {
        const { conteo: c, items } = await api('/inventario/api/conteos/' + id);
        $('cntTitulo').textContent = `${c.numero} · ${c.empresa} / ${c.sede} · ${c.estado}`;
        const contando = c.estado === 'En conteo';
        if (contando) {
            $('cntAyuda').innerHTML = '🔢 Ve a la sede, busca cada producto y escribe <b>cuántas unidades ves</b>. Si no hay ninguno, escribe 0. No se muestra lo que dice el sistema a propósito.';
            $('cntHead').innerHTML = '<tr><th class="left">Producto</th><th>Unidad</th><th>Contado</th><th class="left">Comentario</th></tr>';
            $('cntItems').innerHTML = items.map(i => `<tr><td class="left"><b>${esc(i.codigo)}</b> ${esc(i.descripcion)}<small>${esc([i.marca, i.modelo].filter(Boolean).join(' · '))}</small></td><td>${esc(i.unidad || '')}</td>
                <td><input type="number" min="0" step="any" class="inp-num" data-cnt="${i.id}" value="${i.cantidad_contada ?? ''}"></td>
                <td><input type="text" class="inp-txt" data-com="${i.id}" value="${esc(i.comentario || '')}" maxlength="200"></td></tr>`).join('');
            $('cntPie').innerHTML = PUEDE.contar ? `<button class="btn btn-secondary" data-close="cntModal">Cerrar</button>
                <button class="btn btn-secondary" id="cntAvance">Guardar avance</button><button class="btn btn-primary" id="cntTerminar">Terminar y enviar a aprobación</button>` : '';
            const enviar = terminar => {
                const contado = {}, comentarios = {};
                $('cntItems').querySelectorAll('[data-cnt]').forEach(i => { contado[i.dataset.cnt] = i.value; });
                $('cntItems').querySelectorAll('[data-com]').forEach(i => { comentarios[i.dataset.com] = i.value; });
                guardarCon($(terminar ? 'cntTerminar' : 'cntAvance'), async () => {
                    const r = await post(`/inventario/api/conteos/${id}/guardar`, { contado, comentarios, terminar });
                    aviso(r.message, 'success');
                    if (terminar) { cerrar('cntModal'); refrescar(); }
                });
            };
            if ($('cntAvance')) { $('cntAvance').onclick = () => enviar(false); $('cntTerminar').onclick = () => enviar(true); }
        } else {
            $('cntAyuda').innerHTML = `Contó: <b>${esc(c.contado_por || '')}</b> el ${fecha(c.contado_en)}. ` +
                (c.estado === 'Por aprobar' ? 'Revisa las diferencias. Si algo no cuadra, pide volver a contar. Al aprobar, el kardex se ajusta.' : `Aprobó: <b>${esc(c.aprobado_por || '')}</b>.`);
            $('cntHead').innerHTML = '<tr><th class="left">Producto</th><th>Sistema</th><th>Contado</th><th>Diferencia</th><th>Valor S/</th><th class="left">Comentario</th></tr>';
            $('cntItems').innerHTML = items.map(i => `<tr class="${i.diferencia ? 'fila-dif' : ''}"><td class="left"><b>${esc(i.codigo)}</b> ${esc(i.descripcion)}</td>
                <td class="num">${cant(i.stock_sistema)}</td><td class="num">${cant(i.cantidad_contada)}</td>
                <td class="num ${i.diferencia < 0 ? 'neg' : ''}">${i.diferencia > 0 ? '+' : ''}${cant(i.diferencia)}</td><td class="num ${i.valor_diferencia < 0 ? 'neg' : ''}">${soles(i.valor_diferencia)}</td>
                <td class="left">${esc(i.comentario || '')}</td></tr>`).join('');
            const puedeAprobarEste = c.estado === 'Por aprobar' && PUEDE.aprobar;
            $('cntPie').innerHTML = `<button class="btn btn-secondary" data-close="cntModal">Cerrar</button>` + (puedeAprobarEste ?
                `<button class="btn btn-secondary" id="cntRecontar">Volver a contar</button><button class="btn btn-primary" id="cntAprobar">Aprobar y ajustar kardex</button>` : '');
            if (puedeAprobarEste) {
                const accion = a => guardarCon($(a === 'aprobar' ? 'cntAprobar' : 'cntRecontar'), async () => {
                    const r = await post(`/inventario/api/conteos/${id}/aprobar`, { accion: a });
                    aviso(r.message, 'success'); cerrar('cntModal'); refrescar();
                });
                $('cntAprobar').onclick = () => accion('aprobar');
                $('cntRecontar').onclick = () => accion('recontar');
            }
        }
        abrir('cntModal');
    }

    // ========================================================
    // KARDEX
    // ========================================================
    async function cargarKardex() {
        const params = new URLSearchParams({ estado: 'Registrado' });
        if (pickers.kardex.valor) params.set('producto_id', pickers.kardex.valor);
        if ($('kdxEmpresa').value) params.set('empresa_id', $('kdxEmpresa').value);
        if ($('kdxSede').value) params.set('almacen_id', $('kdxSede').value);
        if ($('kdxDesde').value) params.set('desde', $('kdxDesde').value);
        if ($('kdxHasta').value) params.set('hasta', $('kdxHasta').value);
        $('kdxExportar').href = '/inventario/api/kardex/exportar?' + params;
        $('kdxBody').innerHTML = '<tr><td colspan="17">Cargando...</td></tr>';
        try {
            const { data } = await api('/inventario/api/kardex?' + params);
            const filas = data.slice().reverse();  // del más antiguo al más reciente, como un kardex en papel
            // El último movimiento de cada producto + empresa + sede es su SALDO FINAL: se resalta
            const ultimo = {};
            filas.forEach((m, i) => { ultimo[`${m.producto_id}|${m.empresa_id}|${m.almacen_id}`] = i; });
            $('kdxBody').innerHTML = filas.length ? filas.map((m, i) => {
                const e = m.tipo === 'ENTRADA';
                const fin = ultimo[`${m.producto_id}|${m.empresa_id}|${m.almacen_id}`] === i;
                return `<tr${fin ? ' class="kdx-final" title="Saldo final de este producto en esta empresa y sede"' : ''}><td>${fecha(m.fecha)}</td><td>${esc(m.numero)}</td><td>${esc(m.empresa)}</td><td>${esc(m.sede)}</td>
                    <td class="left">${esc(m.codigo)} · ${esc(m.descripcion)}</td><td class="left">${esc(m.motivo_texto)}${m.tercero ? `<small>${esc(m.tercero)}</small>` : ''}</td>
                    <td>${esc(m.documento_numero || '')}</td>
                    <td class="num grp-in">${e ? cant(m.cantidad) : ''}</td><td class="num grp-in">${e ? num4(m.costo_unitario) : ''}</td><td class="num grp-in">${e ? num4(m.costo_total) : ''}</td>
                    <td class="num grp-out">${e ? '' : cant(m.cantidad)}</td><td class="num grp-out">${e ? '' : num4(m.costo_unitario)}</td><td class="num grp-out">${e ? '' : num4(m.costo_total)}</td>
                    <td class="num grp-saldo">${fin ? '<span class="kdx-final-etq">SALDO FINAL</span>' : ''}<b>${cant(m.saldo_cantidad)}</b></td><td class="num grp-saldo">${num4(m.saldo_costo_promedio)}</td><td class="num grp-saldo">${num4(m.saldo_valor)}</td>
                    <td>${esc(m.usuario_nombre || '')}</td></tr>`;
            }).join('') : '<tr><td colspan="17">Sin movimientos para este filtro.</td></tr>';
        } catch (e) { $('kdxBody').innerHTML = `<tr><td colspan="17" class="neg">${esc(e.message)}</td></tr>`; }
    }

    // ========================================================
    // SEDES Y SUNAT
    // ========================================================
    function cargarSedes() {
        const reg = {};
        cat.registro.forEach(r => { reg[`${r.almacen_id}-${r.empresa_id}`] = r; });
        const dis = PUEDE.aprobar ? '' : 'disabled';
        $('sedesBody').innerHTML = cat.sedes.map(s => cat.empresas.map((e, n) => {
            const r = reg[`${s.id}-${e.id}`] || {};
            return `<tr data-sede="${s.id}" data-emp="${e.id}">
                ${n === 0 ? `<td class="left" rowspan="${cat.empresas.length}"><b>📍 ${esc(s.nombre)}</b></td><td class="left" rowspan="${cat.empresas.length}">${esc(s.direccion || '')}</td>` : ''}
                <td><b>${esc(e.nombre)}</b></td>
                <td><input type="checkbox" data-f="es_domicilio_fiscal" ${r.es_domicilio_fiscal ? 'checked' : ''} ${dis}></td>
                <td><input type="checkbox" data-f="registrado_sunat" ${r.registrado_sunat ? 'checked' : ''} ${dis}></td>
                <td><input type="text" class="inp-txt" data-f="codigo_establecimiento" value="${esc(r.codigo_establecimiento || '')}" maxlength="10" placeholder="Ej. 0001" ${dis}></td>
                <td><input type="text" class="inp-txt" data-f="observaciones" value="${esc(r.observaciones || '')}" maxlength="200" ${dis}></td></tr>`;
        }).join('')).join('') || '<tr><td colspan="7">No hay sedes. Créalas en Maestros ▸ Almacenes.</td></tr>';
        $('btnGuardarSedes').style.display = PUEDE.aprobar ? '' : 'none';
    }

    // ========================================================
    // VENCIMIENTOS (amarillo 6 meses, rojo 3 meses, vencido)
    // ========================================================
    const NIVEL_VENC = { vencido: 'VENCIDO', rojo: 'ROJO · 3 meses o menos', amarillo: 'AMARILLO · 6 meses o menos', ok: 'Más de 6 meses' };
    let vencFilas = [];
    async function cargarVencimientos() {
        const nivel = $('vencNivel').value;
        const q = new URLSearchParams();
        if (nivel === 'todo') q.set('dias', '36500'); else if (nivel) q.set('nivel', nivel);
        try {
            const r = await api('/inventario/api/vencimientos?' + q);
            vencFilas = r.data;
            const c = r.conteo;
            $('vencKpis').innerHTML = `
                <div class="inv-kpi venc-kpi venc-vencido"><small>Vencidos</small><b>${c.vencido}</b><span>Sacar de la venta</span></div>
                <div class="inv-kpi venc-kpi venc-rojo"><small>Rojo</small><b>${c.rojo}</b><span>Vencen en 3 meses o menos</span></div>
                <div class="inv-kpi venc-kpi venc-amarillo"><small>Amarillo</small><b>${c.amarillo}</b><span>Vencen en 6 meses o menos</span></div>`;
            pintarVencimientos();
        } catch (e) {
            $('vencBody').innerHTML = `<tr><td colspan="10">${esc(e.message)}</td></tr>`;
        }
    }
    function pintarVencimientos() {
        const q = $('vencBuscar').value.trim().toLowerCase();
        const filas = vencFilas.filter(v => !q || `${v.codigo} ${v.descripcion} ${v.lote_serie || ''}`.toLowerCase().includes(q));
        $('vencBody').innerHTML = filas.map(v => `<tr>
                <td><span class="venc-chip venc-${v.nivel}">${NIVEL_VENC[v.nivel] || v.nivel}</span></td>
                <td><b>${fecha(v.fecha_vencimiento)}</b></td>
                <td class="${v.dias < 0 ? 'neg' : ''}">${v.dias < 0 ? 'Venció hace ' + Math.abs(v.dias) + ' días' : v.dias + ' días'}</td>
                <td>${esc(v.codigo || '')}</td><td class="left">${esc(v.descripcion || '')}</td><td>${esc(v.lote_serie || '-')}</td>
                <td>${cant(v.cantidad)}</td><td>${esc(nombreEmpresa(v.empresa_id))}</td><td>${esc(nombreSede(v.almacen_id))}</td>
                <td>${v.origen === 'Lote' ? 'Ingreso del lote' : 'Ficha del producto'}</td></tr>`).join('')
            || '<tr><td colspan="10">Nada por vencer con este filtro. Para que aparezca un producto, anota su fecha de vencimiento en la ficha del producto o al registrar el ingreso.</td></tr>';
    }

    // ========================================================
    // TABS Y EVENTOS
    // ========================================================
    const cargadores = {
        resumen: cargarResumen, estado_stock: cargarConsolidado, donde: () => {},
        entradas_salidas: () => { cargarRecepciones(); cargarMovimientos(); },
        transferencias: () => { cargarTraslados(); cargarIntercompany(); },
        separaciones: cargarSeparaciones, conteos: cargarConteos, kardex: () => {}, sedes: cargarSedes,
        vencimientos: cargarVencimientos
    };
    let tabActual = 'resumen';

    function cambiarTab(tab, push = true) {
        if (!cargadores[tab]) tab = 'resumen';
        tabActual = tab;
        document.querySelectorAll('#tabsRowInv .tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
        document.querySelectorAll('#invApp > .section').forEach(s => s.classList.toggle('active', s.id === 'sec-' + tab));
        if (push) {
            const url = new URL(window.location);
            url.searchParams.set('tab', tab);
            window.history.replaceState({}, '', url);
        }
        document.querySelectorAll('.child-btn[data-screen]').forEach(b => {
            if (b.getAttribute('href') && b.getAttribute('href').startsWith('/inventario')) b.classList.toggle('active', b.dataset.screen === tab);
        });
        cargadores[tab]();
    }
    const refrescar = () => { cargadores[tabActual](); if (tabActual !== 'resumen') cargarResumen(); };

    document.addEventListener('click', async e => {
        const t = e.target;
        const tab = t.closest('#tabsRowInv .tab-btn');
        if (tab) { cambiarTab(tab.dataset.tab); return; }
        const ir = t.closest('[data-ir]');
        if (ir) {
            if (ir.dataset.rot) $('conRotacion').value = ir.dataset.rot;
            cambiarTab(ir.dataset.ir);
            if (ir.dataset.ic) $('btnNuevoIC').click();
            return;
        }
        const b = t.closest('button, a');
        if (!b) return;
        const d = b.dataset;
        if (d.abrirMov) {
            if (d.abrirMov !== 'PROBLEMA' && !PUEDE.operar) { aviso('Solo el personal de almacén registra entradas y salidas.', 'error'); return; }
            abrirMovimiento(d.abrirMov);
        } else if (d.rec) {
            const r = JSON.parse(d.rec);
            if (r.desde_compras) {
                // Recibida en Compras: empresa, sede, producto y costo ya se saben; solo se confirma
                abrirMovimiento('ENTRADA', { motivo: 'COMPRA', producto_id: r.producto_id_sugerido,
                    texto: (r.codigo ? r.codigo + ' · ' : '') + r.producto, cantidad: r.cantidad, costo: r.costo_unitario,
                    documento: r.guia_proveedor || r.orden_compra, docTipo: 'Guía de remisión', tercero: r.proveedor_nombre,
                    recepcion_id: r.id, empresa: r.empresa_id, sede: r.almacen_id, lote: r.lote_serie, venc: r.fecha_vencimiento,
                    fijo: true, obs: 'Recepción ' + r.numero_recepcion + ' · ' + r.orden_compra + (r.cliente ? ' · Pedido ' + (r.pedido_numero || '') + ' de ' + r.cliente : '') });
            } else {
                abrirMovimiento('ENTRADA', { motivo: 'COMPRA', producto_id: r.producto_id_sugerido, texto: r.producto_id_sugerido ? r.producto : '',
                    cantidad: r.cantidad, documento: r.orden_compra, docTipo: 'Orden de compra', tercero: r.proveedor_nombre,
                    recepcion_id: r.id, obs: 'Recepción ' + r.numero_recepcion });
            }
        } else if (d.stockInicial) {
            abrirMovimiento('ENTRADA', { motivo: 'STOCK_INICIAL', producto_id: Number(d.stockInicial), texto: d.txt });
        } else if (d.ubicar) {
            const s = JSON.parse(d.ubicar);
            abrirMovimiento('ENTRADA', { motivo: 'STOCK_INICIAL', producto_id: s.id, texto: s.txt, cantidad: s.stock, costo: s.costo });
        } else if (d.aprobar) {
            guardarCon(b, async () => { const r = await post(`/inventario/api/movimientos/${d.aprobar}/aprobar`, { aprobar: true }); aviso(r.message, 'success'); refrescar(); });
        } else if (d.rechazar) {
            pedirMotivo('Rechazar movimiento', 'El stock no cambiará. Quien lo reportó verá el motivo.', async m => {
                const r = await post(`/inventario/api/movimientos/${d.rechazar}/aprobar`, { aprobar: false, motivo: m }); aviso(r.message, 'success'); refrescar();
            });
        } else if (d.revertir) {
            pedirMotivo(`Corregir ${d.num}`, 'Se registrará un movimiento contrario con la misma cantidad. El original queda visible en el kardex.', async m => {
                const r = await post(`/inventario/api/movimientos/${d.revertir}/revertir`, { motivo: m }); aviso(r.message, 'success'); refrescar();
            });
        } else if (d.recibir) {
            abrirRecibir(Number(d.recibir));
        } else if (d.anularTra) {
            pedirMotivo(`Anular ${d.num}`, 'La mercadería vuelve a la sede de origen.', async m => {
                const r = await post(`/inventario/api/traslados/${d.anularTra}/anular`, { motivo: m }); aviso(r.message, 'success'); refrescar();
            });
        } else if (d.quitarItem !== undefined) {
            trasladoItems.splice(Number(d.quitarItem), 1); pintarItemsTraslado();
        } else if (d.facturaIc) {
            pedirMotivo('Número de factura', 'Escribe el número de la factura de la venta entre empresas (ej. F001-00000456).', async f => {
                const r = await post(`/inventario/api/intercompany/${encodeURIComponent(d.facturaIc)}/factura`, { factura: f }); aviso(r.message, 'success'); refrescar();
            });
        } else if (d.liberar) {
            guardarCon(b, async () => { const r = await post(`/inventario/api/separaciones/${d.liberar}/liberar`); aviso(r.message, 'success'); refrescar(); });
        } else if (d.verConteo) {
            try { await verConteo(Number(d.verConteo)); } catch (err) { aviso(err.message, 'error'); }
        } else if (d.kardex) {
            pickers.kardex.set(Number(d.kardex), d.txt); cambiarTab('kardex'); cargarKardex();
        } else if (d.donde) {
            pickers.donde.set(Number(d.donde), d.txt); cambiarTab('donde'); ubicar();
        } else if (b.id === 'btnJuntar') {
            guardarCon(b, async () => {
                const r = await post('/inventario/api/juntar', { ...ultimoPlan, encargado: $('juntarEncargado').value });
                aviso(r.message, 'success'); cambiarTab('transferencias');
            });
        } else if (b.id === 'btnSepararDesde') {
            const paso = ultimoPlan && ultimoPlan.plan[0];
            abrirSeparacion({ producto_id: pickers.donde.valor, texto: pickers.donde.texto, cantidad: $('dondeCantidad').value,
                empresa_id: paso ? paso.empresa_id : null, almacen_id: paso ? paso.almacen_id : null });
        }
    });

    function conectar() {
        $('btnRefrescarResumen').onclick = cargarResumen;
        let t;
        $('conBuscar').addEventListener('input', () => { clearTimeout(t); t = setTimeout(cargarConsolidado, 300); });
        $('vencNivel').addEventListener('change', cargarVencimientos);
        $('vencBuscar').addEventListener('input', pintarVencimientos);
        $('conRotacion').onchange = cargarConsolidado;
        $('conTodos').onchange = cargarConsolidado;
        $('btnUbicar').onclick = ubicar;
        $('movMotivo').onchange = ajustarFormMovimiento;
        pickers.mov.onChange = p => {
            if (app.dataset.claseMov === 'ENTRADA' && p.costo && !$('movCosto').value) $('movCosto').value = p.costo;
            if ($('movMotivo').value === 'VENTA') cargarSeparacionesMov();
        };
        ['movEmpresa', 'movSede'].forEach(i => $(i).addEventListener('change', () => { if ($('movMotivo').value === 'VENTA') cargarSeparacionesMov(); }));
        $('movSeparacion').onchange = () => {
            const op = $('movSeparacion').selectedOptions[0];
            if (op && op.dataset.cliente && !$('movTercero').value) $('movTercero').value = op.dataset.cliente;
        };
        $('movGuardar').onclick = guardarMovimiento;
        let tm;
        $('movBuscar').addEventListener('input', () => { clearTimeout(tm); tm = setTimeout(cargarMovimientos, 300); });
        $('movEstado').onchange = cargarMovimientos;

        $('traEstado').onchange = cargarTraslados;
        $('btnNuevoTraslado').onclick = () => {
            if (!PUEDE.operar) { aviso('Solo el personal de almacén crea traslados.', 'error'); return; }
            trasladoItems = []; pintarItemsTraslado(); pickers.tra.limpiar();
            ['traCant', 'traGuia', 'traObs', 'traEncargado'].forEach(i => { $(i).value = ''; });
            abrir('traModal');
        };
        $('traAgregar').onclick = () => {
            if (!pickers.tra.valor || !(Number($('traCant').value) > 0)) { aviso('Elige el producto y la cantidad.', 'error'); return; }
            trasladoItems.push({ producto_id: pickers.tra.valor, texto: pickers.tra.texto, cantidad: Number($('traCant').value) });
            pickers.tra.limpiar(); $('traCant').value = ''; pintarItemsTraslado();
        };
        $('traGuardar').onclick = () => guardarCon($('traGuardar'), async () => {
            const r = await post('/inventario/api/traslados', {
                empresa_id: $('traEmpresa').value, origen_id: $('traOrigen').value, destino_id: $('traDestino').value,
                guia_remision: $('traGuia').value, encargado: $('traEncargado').value, observaciones: $('traObs').value,
                items: trasladoItems.map(i => ({ producto_id: i.producto_id, cantidad: i.cantidad }))
            });
            aviso(r.message, 'success'); cerrar('traModal'); refrescar();
        });

        $('btnNuevoIC').onclick = () => {
            if (!PUEDE.operar) { aviso('Solo el personal de almacén registra ventas entre empresas.', 'error'); return; }
            pickers.ic.limpiar();
            if (pickers.donde.valor && ultimoPlan) {
                const paso = ultimoPlan.plan.find(x => x.pasos.includes('intercompany'));
                pickers.ic.set(pickers.donde.valor, pickers.donde.texto);
                if (paso) { $('icVende').value = paso.empresa_id; $('icCompra').value = $('dondeEmpresa').value; $('icSede').value = paso.almacen_id; $('icCantidad').value = paso.tomar; }
            }
            ['icPrecio', 'icFactura', 'icObs'].forEach(i => { $(i).value = ''; });
            abrir('icModal');
        };
        $('icGuardar').onclick = () => guardarCon($('icGuardar'), async () => {
            if (!pickers.ic.valor) throw new Error('Elige el producto de la lista.');
            const r = await post('/inventario/api/intercompany', {
                empresa_vende_id: $('icVende').value, empresa_compra_id: $('icCompra').value, producto_id: pickers.ic.valor,
                almacen_id: $('icSede').value, cantidad: $('icCantidad').value, precio_unitario: $('icPrecio').value,
                factura: $('icFactura').value, observaciones: $('icObs').value
            });
            aviso(r.message, 'success'); cerrar('icModal'); refrescar();
        });

        $('sepEstado').onchange = cargarSeparaciones;
        $('btnNuevaSep').onclick = () => abrirSeparacion();
        $('sepGuardar').onclick = () => guardarCon($('sepGuardar'), async () => {
            if (!pickers.sep.valor) throw new Error('Elige el producto de la lista.');
            const r = await post('/inventario/api/separaciones', {
                producto_id: pickers.sep.valor, empresa_id: $('sepEmpresa').value, almacen_id: $('sepSede').value,
                cantidad: $('sepCantidad').value, vence_el: $('sepVence').value, cliente: $('sepCliente').value,
                documento: $('sepDoc').value, observaciones: $('sepObs').value
            });
            aviso(r.message, 'success'); cerrar('sepModal'); refrescar();
        });

        const nuevoConteo = tipo => {
            if (!PUEDE.contar) { aviso('Los conteos los hace el personal de control, no logística. Pide acceso a tu supervisor.', 'error'); return; }
            $('cntTipo').value = tipo; $('cntObs').value = '';
            $('cntNuevoTitulo').textContent = tipo === 'Sorpresa' ? 'Conteo sorpresa' : 'Conteo completo';
            $('cntNuevoAyuda').innerHTML = tipo === 'Sorpresa'
                ? '🎲 El sistema elige al azar 10 productos (más probabilidad para los caros y los que más se mueven). Hazlo sin avisar, una vez por semana.'
                : '📋 Se cuentan todos los productos con stock de esa empresa en esa sede. Recomendado una vez al mes.';
            abrir('cntNuevoModal');
        };
        $('btnConteoSorpresa').onclick = () => nuevoConteo('Sorpresa');
        $('btnConteoGeneral').onclick = () => nuevoConteo('General');
        $('cntCrear').onclick = () => guardarCon($('cntCrear'), async () => {
            const r = await post('/inventario/api/conteos', { empresa_id: $('cntEmpresa').value, almacen_id: $('cntSede').value, tipo: $('cntTipo').value, observaciones: $('cntObs').value });
            aviso(r.message, 'success'); cerrar('cntNuevoModal'); await cargarConteos(); verConteo(r.id);
        });

        $('btnKardex').onclick = cargarKardex;
        $('btnGuardarSedes').onclick = () => guardarCon($('btnGuardarSedes'), async () => {
            const filas = [...$('sedesBody').querySelectorAll('tr[data-sede]')].map(tr => {
                const f = { almacen_id: tr.dataset.sede, empresa_id: tr.dataset.emp };
                tr.querySelectorAll('[data-f]').forEach(i => { f[i.dataset.f] = i.type === 'checkbox' ? i.checked : i.value; });
                return f;
            });
            const r = await post('/inventario/api/sedes_empresas', { filas });
            aviso(r.message, 'success');
            const c = await api('/inventario/api/catalogos'); cat.registro = c.registro_sunat; cargarResumen();
        });
    }

    // ---------- inicio ----------
    document.querySelectorAll('.prod-picker').forEach(crearPicker);
    conectar();
    cargarCatalogos().then(() => {
        const tab = new URLSearchParams(window.location.search).get('tab') || 'resumen';
        cambiarTab(tab, false);
        if (tab !== 'resumen') cargarResumen();
    }).catch(e => aviso('No se pudo cargar el inventario: ' + e.message, 'error'));
})();
