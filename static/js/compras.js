// ============================================================
// COMPRAS - Módulo Principal
// ============================================================

// ============================================================
// DATOS - Sincronizados con window
// ============================================================

if (typeof window.solicitudesData === 'undefined') window.solicitudesData = [];
if (typeof window.comparativosData === 'undefined') window.comparativosData = [];
if (typeof window.ordenesData === 'undefined') window.ordenesData = [];
if (typeof window.comprobantesProveedorData === 'undefined') window.comprobantesProveedorData = [];
if (typeof window.recepcionesData === 'undefined') window.recepcionesData = [];

let solicitudesData = window.solicitudesData;
let comparativosData = window.comparativosData;
let ordenesData = window.ordenesData;
let comprobantesProveedorData = window.comprobantesProveedorData;
let recepcionesData = window.recepcionesData;

// ============================================================
// VARIABLES GLOBALES PARA CONFIRMACIONES
// ============================================================

let confirmActionCallback = null;
let deleteActionCallback = null;
let approveActionCallback = null;
let sendActionCallback = null;
let receiveActionCallback = null;
let editActionCallback = null;
let storeActionCallback = null;

// ============================================================
// FUNCIONES PARA MODALES DE CONFIRMACIÓN
// ============================================================

function showConfirmModal(options) {
    const modal = document.getElementById('confirmModal');
    if (!modal) {
        console.warn('⚠️ confirmModal no encontrado');
        return;
    }
    
    document.getElementById('confirmModalTitle').textContent = options.title || '⚠️ Confirmación';
    document.getElementById('confirmMessage').textContent = options.message || '¿Estás seguro de realizar esta acción?';
    document.getElementById('confirmDetails').textContent = options.details || '';
    document.getElementById('confirmIcon').textContent = options.icon || '⚠️';
    
    const btn = document.getElementById('confirmModalBtn');
    if (btn) {
        btn.textContent = options.confirmText || '✅ Sí, confirmar';
        btn.className = `btn ${options.btnClass || 'btn-primary'}`;
    }
    
    confirmActionCallback = options.onConfirm;
    modal.classList.add('show');
}

function closeConfirmModal() {
    const modal = document.getElementById('confirmModal');
    if (modal) modal.classList.remove('show');
    confirmActionCallback = null;
}

function executeConfirmAction() {
    if (confirmActionCallback) {
        confirmActionCallback();
    }
    closeConfirmModal();
}

// ============================================================
// MODAL DE ELIMINACIÓN
// ============================================================

function showDeleteModal(options) {
    const modal = document.getElementById('deleteModal');
    if (!modal) {
        console.warn('⚠️ deleteModal no encontrado');
        return;
    }
    
    document.getElementById('deleteModalTitle').textContent = options.title || '🗑️ Confirmar eliminación';
    document.getElementById('deleteMessage').textContent = options.message || '¿Estás seguro de eliminar este registro?';
    document.getElementById('deleteDetails').textContent = options.details || '';
    const motivo = document.getElementById('deleteMotivo');
    if (motivo) motivo.value = '';
    const btn = document.getElementById('deleteModalBtn');
    if (btn) btn.textContent = options.confirmText || '🗑️ Sí, eliminar';
    
    deleteActionCallback = options.onConfirm;
    modal.classList.add('show');
    if (motivo) setTimeout(() => motivo.focus(), 50);
}

function closeDeleteModal() {
    const modal = document.getElementById('deleteModal');
    if (modal) modal.classList.remove('show');
    deleteActionCallback = null;
}

function executeDeleteAction() {
    // Candado: anular o eliminar exige motivo (el servidor además exige ser administrador)
    const motivo = (document.getElementById('deleteMotivo')?.value || '').trim();
    if (motivo.length < 5) {
        showToast('⚠️ Escribe el motivo (mínimo 5 letras)', 'warning');
        document.getElementById('deleteMotivo')?.focus();
        return;
    }
    if (deleteActionCallback) {
        deleteActionCallback(motivo);
    }
    closeDeleteModal();
}

// Envía una anulación/eliminación con su motivo
async function enviarConMotivo(url, metodo, motivo, extra) {
    const response = await fetch(url, {
        method: metodo,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.assign({ motivo }, extra || {}))
    });
    return response.json();
}

// ============================================================
// MODAL DE APROBACIÓN
// ============================================================

function showApproveModal(options) {
    const modal = document.getElementById('approveModal');
    if (!modal) {
        console.warn('⚠️ approveModal no encontrado');
        return;
    }
    
    document.getElementById('approveModalTitle').textContent = options.title || '✅ Confirmar aprobación';
    document.getElementById('approveMessage').textContent = options.message || '¿Estás seguro de aprobar este registro?';
    document.getElementById('approveDetails').textContent = options.details || '';
    
    approveActionCallback = options.onConfirm;
    modal.classList.add('show');
}

function closeApproveModal() {
    const modal = document.getElementById('approveModal');
    if (modal) modal.classList.remove('show');
    approveActionCallback = null;
}

function executeApproveAction() {
    if (approveActionCallback) {
        approveActionCallback();
    }
    closeApproveModal();
}

// ============================================================
// MODAL DE ENVÍO
// ============================================================

function showSendModal(options) {
    const modal = document.getElementById('sendModal');
    if (!modal) {
        console.warn('⚠️ sendModal no encontrado');
        return;
    }
    
    document.getElementById('sendModalTitle').textContent = options.title || '📤 Confirmar envío';
    document.getElementById('sendMessage').textContent = options.message || '¿Estás seguro de enviar este documento?';
    document.getElementById('sendDetails').textContent = options.details || '';
    
    sendActionCallback = options.onConfirm;
    modal.classList.add('show');
}

function closeSendModal() {
    const modal = document.getElementById('sendModal');
    if (modal) modal.classList.remove('show');
    sendActionCallback = null;
}

function executeSendAction() {
    if (sendActionCallback) {
        sendActionCallback();
    }
    closeSendModal();
}

// ============================================================
// MODAL DE RECEPCIÓN
// ============================================================

function showReceiveModal(options) {
    const modal = document.getElementById('receiveModal');
    if (!modal) {
        console.warn('⚠️ receiveModal no encontrado');
        return;
    }
    
    document.getElementById('receiveModalTitle').textContent = options.title || '📦 Confirmar recepción';
    document.getElementById('receiveMessage').textContent = options.message || '¿Estás seguro de confirmar la recepción?';
    document.getElementById('receiveDetails').textContent = options.details || '';
    
    receiveActionCallback = options.onConfirm;
    modal.classList.add('show');
}

function closeReceiveModal() {
    const modal = document.getElementById('receiveModal');
    if (modal) modal.classList.remove('show');
    receiveActionCallback = null;
}

function executeReceiveAction() {
    if (receiveActionCallback) {
        receiveActionCallback();
    }
    closeReceiveModal();
}

// ============================================================
// FUNCIONES DE RENDERIZADO
// ============================================================

function renderSolicitudes() {
    const tbody = document.getElementById('solicitudRows');
    if (!tbody) return;
    
    const search = document.getElementById('solicitudSearch')?.value.toLowerCase() || '';
    const statusFilter = document.getElementById('solicitudStatus')?.value || '';
    
    let filtered = (solicitudesData || []).filter(s => {
        const matchSearch = (s.numero || '').toLowerCase().includes(search) ||
                           (s.producto || '').toLowerCase().includes(search) ||
                           (s.solicitante || '').toLowerCase().includes(search) ||
                           (s.area || '').toLowerCase().includes(search);
        const matchStatus = statusFilter === '' || s.estado === statusFilter;
        const matchFecha = filtrarPorFecha(s, 'solicitudFechaInicio', 'solicitudFechaFin');
        return matchSearch && matchStatus && matchFecha;
    });
    
    const countEl = document.getElementById('solicitudCount');
    if (countEl) countEl.textContent = `Mostrando ${filtered.length} de ${(solicitudesData || []).length} solicitudes`;
    
    renderSolicitudKPI();
    
    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;padding:20px;color:#94A3B8;">No hay solicitudes</td></tr>`;
        return;
    }
    
    tbody.innerHTML = filtered.map((s, index) => `
        <tr>
            <td>${index + 1}</td>
            <td class="date-cell">${s.creado || formatearFecha(s.fecha)}</td>
            <td><span class="badge ${getEstadoClass(s.estado)}">${s.estado || 'Borrador'}</span></td>
            <td><span class="code-pill">${s.numero || '-'}</span></td>
            <td class="left">${s.producto || '-'}</td>
            <td>${s.cantidad || 0} ${s.unidad || 'UND'}</td>
            <td>${s.area || '-'} / ${s.solicitante || '-'}</td>
            <td><span class="badge ${s.urgencia === 'Alta' || s.urgencia === 'Urgente' ? 'b-pending' : 'b-ok'}">${s.urgencia || 'Media'}</span></td>
            <td>
                <button class="kebab" onclick="toggleMenu(event, 'solicitud-${s.id}')">⋯</button>
                <div class="menu-pop" id="menu-solicitud-${s.id}" style="display:none;">
                    <button onclick="editSolicitud(${s.id})">✏️ Editar</button>
                    <button class="menu-approve" onclick="approveSolicitud(${s.id})">✅ Aprobar</button>
                    <button onclick="createOrdenFromSolicitud(${s.id})">📄 Crear orden</button>
                    ${ES_ADMIN_COMPRAS ? `<div class="menu-divider"></div>
                    <button class="danger" onclick="deleteSolicitud(${s.id})">🗑️ Eliminar</button>` : ''}
                </div>
            </td>
        </tr>
    `).join('');
}

function renderComparativos() {
    const tbody = document.getElementById('comparativoRows');
    if (!tbody) return;
    
    const search = document.getElementById('comparativoSearch')?.value.toLowerCase() || '';
    const statusFilter = document.getElementById('comparativoStatus')?.value || '';
    
    let filtered = (comparativosData || []).filter(c => {
        const matchSearch = (c.numero || '').toLowerCase().includes(search) ||
                           (c.producto || '').toLowerCase().includes(search) ||
                           (c.proveedores || []).some(p => (p.nombre || '').toLowerCase().includes(search));
        const matchStatus = statusFilter === '' || c.estado === statusFilter;
        const matchFecha = filtrarPorFecha(c, 'comparativoFechaInicio', 'comparativoFechaFin');
        return matchSearch && matchStatus && matchFecha;
    });
    
    const countEl = document.getElementById('comparativoCount');
    if (countEl) countEl.textContent = `Mostrando ${filtered.length} de ${(comparativosData || []).length} comparativos`;
    
    renderComparativoKPI();
    
    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;padding:20px;color:#94A3B8;">No hay comparativos</td></tr>`;
        return;
    }
    
    tbody.innerHTML = filtered.map((c, index) => {
        const mejorPrecio = (c.proveedores || []).reduce((min, p) => {
            if (!min || min.precio === undefined) return p;
            return (p.precio || 0) < (min.precio || 0) ? p : min;
        }, null);
        
        if (!mejorPrecio) {
            return `
            <tr>
                <td>${index + 1}</td>
                <td class="date-cell">${c.creado || formatearFecha(c.fecha)}</td>
                <td><span class="badge ${getEstadoClass(c.estado)}">${c.estado || 'Borrador'}</span></td>
                <td><span class="code-pill">${c.numero || '-'}</span></td>
                <td class="left">${c.producto || '-'}</td>
                <td class="left" colspan="3">Sin proveedores registrados</td>
                <td>
                    <button class="kebab" onclick="toggleMenu(event, 'comparativo-${c.id}')">⋯</button>
                    <div class="menu-pop" id="menu-comparativo-${c.id}" style="display:none;">
                        <button onclick="editComparativo(${c.id})">✏️ Editar</button>
                        <button onclick="selectProveedor(${c.id})">✅ Seleccionar proveedor</button>
                        <div class="menu-divider"></div>
                        <button class="danger" onclick="deleteComparativo(${c.id})">🗑️ Eliminar</button>
                    </div>
                </td>
            </tr>`;
        }
        
        return `
        <tr>
            <td>${index + 1}</td>
            <td class="date-cell">${c.creado || formatearFecha(c.fecha)}</td>
            <td><span class="badge ${getEstadoClass(c.estado)}">${c.estado || 'Borrador'}</span></td>
            <td><span class="code-pill">${c.numero || '-'}</span></td>
            <td class="left">${c.producto || '-'}</td>
            <td class="left">${mejorPrecio.nombre || '-'}</td>
            <td><b>S/${(mejorPrecio.precio || 0).toFixed(2)}</b></td>
            <td>${mejorPrecio.plazo || '-'}</td>
            <td>
                <button class="kebab" onclick="toggleMenu(event, 'comparativo-${c.id}')">⋯</button>
                <div class="menu-pop" id="menu-comparativo-${c.id}" style="display:none;">
                    <button onclick="editComparativo(${c.id})">✏️ Editar</button>
                    <button onclick="selectProveedor(${c.id})">✅ Seleccionar proveedor</button>
                    <div class="menu-divider"></div>
                    <button class="danger" onclick="deleteComparativo(${c.id})">🗑️ Eliminar</button>
                </div>
            </td>
        </tr>`;
    }).join('');
}

function renderOrdenes() {
    const tbody = document.getElementById('ordenRows');
    if (!tbody) return;
    
    const search = document.getElementById('ordenSearch')?.value.toLowerCase() || '';
    const statusFilter = document.getElementById('ordenStatus')?.value || '';
    
    let filtered = (ordenesData || []).filter(o => {
        const matchSearch = (o.numero || '').toLowerCase().includes(search) ||
                           (o.proveedor || '').toLowerCase().includes(search) ||
                           (o.ruc || '').includes(search) ||
                           (o.pc_numeros || '').toLowerCase().includes(search) ||
                           (o.clientes_pedido || '').toLowerCase().includes(search) ||
                           (o.motivo_compra || '').toLowerCase().includes(search) ||
                           (o.items || []).some(i => (i.producto || '').toLowerCase().includes(search));
        const matchStatus = statusFilter === '' || o.estado === statusFilter;
        const matchFecha = filtrarPorFecha(o, 'ordenFechaInicio', 'ordenFechaFin');
        return matchSearch && matchStatus && matchFecha;
    });
    
    const countEl = document.getElementById('ordenCount');
    if (countEl) countEl.textContent = `Mostrando ${filtered.length} de ${(ordenesData || []).length} órdenes`;
    
    renderOrdenKPI();
    
    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="11" style="text-align:center;padding:20px;color:#94A3B8;">No hay órdenes de compra</td></tr>`;
        return;
    }
    
    tbody.innerHTML = filtered.map((o, index) => `
        <tr>
            <td>${index + 1}</td>
            <td class="date-cell">${o.creado || formatearFecha(o.fecha || o.fecha_creacion)}</td>
            <td><span class="badge ${getEstadoClass(o.estado)}">${o.estado || 'Borrador'}</span></td>
            <td><span class="code-pill">${o.numero || '-'}</span></td>
            <td class="left">${o.sin_pedido
                ? `<span class="badge-sin-pedido">Compra sin pedido</span><small class="sub">${escCompras(o.motivo_compra || 'Sin motivo (OC antigua)')}</small>`
                : `<b>${escCompras(o.pc_numeros)}</b><small class="sub">${escCompras(o.clientes_pedido)}${o.cotizaciones_cliente ? ' · ' + escCompras(o.cotizaciones_cliente) : ''}</small>`}</td>
            <td class="left">${o.proveedor || '-'}</td>
            <td>${o.ruc || '-'}</td>
            <td class="left">${(o.items || []).map(i => i.producto).join(', ') || '-'}</td>
            <td><b>${o.moneda || 'S/'} ${(o.total || 0).toFixed(2)}</b></td>
            <td>${condPagoMostrar(o.condicion_pago) || '-'}</td>
            <td>
                <button class="kebab" onclick="toggleMenu(event, 'orden-${o.id}')">⋯</button>
                <div class="menu-pop" id="menu-orden-${o.id}" style="display:none;">
                    <button onclick="editOrden(${o.id})">✏️ Editar</button>
                    <button class="menu-pdf" onclick="window.open('/compras/orden/${o.id}/preview','_blank')">🖨️ Imprimir para el proveedor</button>
                    <button class="menu-order" onclick="sendOrden(${o.id})">📤 Enviar a proveedor</button>
                    <button class="menu-receive" onclick="createRecepcionFromOrden(${o.id})">📦 Recibir mercadería</button>
                    ${ES_ADMIN_COMPRAS ? `<div class="menu-divider"></div>
                    ${o.estado !== 'Anulada' ? `<button class="danger" onclick="anularOrden(${o.id})">⛔ Anular</button>` : ''}
                    <button class="danger" onclick="deleteOrden(${o.id})">🗑️ Eliminar</button>` : ''}
                </div>
            </td>
        </tr>
    `).join('');
}

function renderComprobantesProveedor() {
    const tbody = document.getElementById('compProvRows');
    if (!tbody) return;
    
    const search = document.getElementById('compProvSearch')?.value.toLowerCase() || '';
    const statusFilter = document.getElementById('compProvStatus')?.value || '';
    
    let filtered = (comprobantesProveedorData || []).filter(c => {
        const matchSearch = (c.numero || '').toLowerCase().includes(search) ||
                           (c.proveedor || '').toLowerCase().includes(search) ||
                           (c.ruc || '').includes(search);
        const matchStatus = statusFilter === '' || c.estado === statusFilter;
        const matchFecha = filtrarPorFecha(c, 'compProvFechaInicio', 'compProvFechaFin');
        return matchSearch && matchStatus && matchFecha;
    });
    
    const countEl = document.getElementById('compProvCount');
    if (countEl) countEl.textContent = `Mostrando ${filtered.length} de ${(comprobantesProveedorData || []).length} comprobantes`;
    
    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;padding:20px;color:#94A3B8;">No hay comprobantes de proveedor</td></tr>`;
        return;
    }
    
    tbody.innerHTML = filtered.map((c, index) => `
        <tr>
            <td>${index + 1}</td>
            <td class="date-cell">${c.creado || formatearFecha(c.fecha)}</td>
            <td><span class="badge ${getEstadoClass(c.estado)}">${c.estado || 'Pendiente'}</span></td>
            <td>${c.tipo || 'Factura'}</td>
            <td><span class="code-pill">${c.numero || '-'}</span></td>
            <td class="left">${c.proveedor || '-'}</td>
            <td>${c.ruc || '-'}</td>
            <td><b>S/${(c.monto || 0).toFixed(2)}</b></td>
            <td>
                <button class="kebab" onclick="toggleMenu(event, 'comp-prov-${c.id}')">⋯</button>
                <div class="menu-pop" id="menu-comp-prov-${c.id}" style="display:none;">
                    <button onclick="editComprobanteProveedor(${c.id})">✏️ Editar</button>
                    <button onclick="payComprobanteProveedor(${c.id})">💰 Marcar pagado</button>
                    ${ES_ADMIN_COMPRAS && c.estado !== 'Anulado' ? `<button class="danger" onclick="deleteComprobanteProveedor(${c.id})">⛔ Anular</button>` : ''}
                </div>
            </td>
        </tr>
    `).join('');
}

function renderRecepciones() {
    const tbody = document.getElementById('recepcionRows');
    if (!tbody) return;
    
    const search = document.getElementById('recepcionSearch')?.value.toLowerCase() || '';
    const statusFilter = document.getElementById('recepcionStatus')?.value || '';
    
    let filtered = (recepcionesData || []).filter(r => {
        const matchSearch = (r.numero || '').toLowerCase().includes(search) ||
                           (r.proveedor || '').toLowerCase().includes(search) ||
                           (r.producto || '').toLowerCase().includes(search) ||
                           (r.orden || '').toLowerCase().includes(search);
        const matchStatus = statusFilter === '' || r.estado === statusFilter;
        const matchFecha = filtrarPorFecha(r, 'recepcionFechaInicio', 'recepcionFechaFin');
        return matchSearch && matchStatus && matchFecha;
    });
    
    const countEl = document.getElementById('recepcionCount');
    if (countEl) countEl.textContent = `Mostrando ${filtered.length} de ${(recepcionesData || []).length} recepciones`;
    
    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;padding:20px;color:#94A3B8;">No hay recepciones</td></tr>`;
        return;
    }
    
    tbody.innerHTML = filtered.map((r, index) => `
        <tr>
            <td>${index + 1}</td>
            <td class="date-cell">${r.creado || formatearFecha(r.fecha)}</td>
            <td><span class="badge ${getEstadoClass(r.estado)}">${r.estado || 'Pendiente'}</span></td>
            <td><span class="code-pill">${r.numero || '-'}</span></td>
            <td><span class="code-pill">${r.orden || '-'}</span></td>
            <td class="left">${r.proveedor || '-'}</td>
            <td class="left">${r.producto || '-'}</td>
            <td>${r.cantidad || 0} ${r.unidad || 'UND'}</td>
            <td>
                <button class="kebab" onclick="toggleMenu(event, 'recepcion-${r.id}')">⋯</button>
                <div class="menu-pop" id="menu-recepcion-${r.id}" style="display:none;">
                    <button onclick="editRecepcion(${r.id})">✏️ Editar</button>
                    <button class="menu-approve" onclick="approveRecepcion(${r.id})">✅ Aprobar recepción</button>
                    <button onclick="storeRecepcion(${r.id})">📦 Almacenar</button>
                    <div class="menu-divider"></div>
                    <button class="danger" onclick="deleteRecepcion(${r.id})">🗑️ Eliminar</button>
                </div>
            </td>
        </tr>
    `).join('');
}

// ============================================================
// FUNCIONES DE KPI
// ============================================================

function renderSolicitudKPI() {
    const container = document.getElementById('solicitudKPI');
    if (!container) return;
    
    const total = solicitudesData.length;
    const pendientes = solicitudesData.filter(s => s.estado === 'Pendiente').length;
    const aprobadas = solicitudesData.filter(s => s.estado === 'Aprobada').length;
    const rechazadas = solicitudesData.filter(s => s.estado === 'Rechazada').length;
    const ordenadas = solicitudesData.filter(s => s.estado === 'Ordenada').length;
    
    container.innerHTML = `
        <div class="status-card">
            <div class="status-dot dot-total">${total}</div>
            <div><small>Total</small><b>${total}</b></div>
        </div>
        <div class="status-card">
            <div class="status-dot dot-pending">${pendientes}</div>
            <div><small>Pendientes</small><b>${pendientes}</b></div>
        </div>
        <div class="status-card">
            <div class="status-dot dot-approved">${aprobadas}</div>
            <div><small>Aprobadas</small><b>${aprobadas}</b></div>
        </div>
        <div class="status-card">
            <div class="status-dot" style="background:#F59E0B;color:#fff;">${rechazadas}</div>
            <div><small>Rechazadas</small><b>${rechazadas}</b></div>
        </div>
        <div class="status-card">
            <div class="status-dot dot-ordered">${ordenadas}</div>
            <div><small>Ordenadas</small><b>${ordenadas}</b></div>
        </div>
    `;
}

function renderComparativoKPI() {
    const container = document.getElementById('comparativoKPI');
    if (!container) return;
    
    const total = comparativosData.length;
    const evaluacion = comparativosData.filter(c => c.estado === 'En evaluación').length;
    const seleccionados = comparativosData.filter(c => c.estado === 'Seleccionado').length;
    const rechazados = comparativosData.filter(c => c.estado === 'Rechazado').length;
    
    container.innerHTML = `
        <div class="status-card">
            <div class="status-dot dot-total">${total}</div>
            <div><small>Total</small><b>${total}</b></div>
        </div>
        <div class="status-card">
            <div class="status-dot dot-pending">${evaluacion}</div>
            <div><small>En evaluación</small><b>${evaluacion}</b></div>
        </div>
        <div class="status-card">
            <div class="status-dot dot-approved">${seleccionados}</div>
            <div><small>Seleccionados</small><b>${seleccionados}</b></div>
        </div>
        <div class="status-card">
            <div class="status-dot" style="background:#F59E0B;color:#fff;">${rechazados}</div>
            <div><small>Rechazados</small><b>${rechazados}</b></div>
        </div>
    `;
}

function renderOrdenKPI() {
    const container = document.getElementById('ordenKPI');
    if (!container) return;
    
    const total = ordenesData.length;
    const emitidas = ordenesData.filter(o => o.estado === 'Emitida').length;
    const enviadas = ordenesData.filter(o => o.estado === 'Enviada').length;
    const confirmadas = ordenesData.filter(o => o.estado === 'Confirmada').length;
    const anuladas = ordenesData.filter(o => o.estado === 'Anulada').length;
    
    container.innerHTML = `
        <div class="status-card">
            <div class="status-dot dot-total">${total}</div>
            <div><small>Total</small><b>${total}</b></div>
        </div>
        <div class="status-card">
            <div class="status-dot" style="background:#3B82F6;color:#fff;">${emitidas}</div>
            <div><small>Emitidas</small><b>${emitidas}</b></div>
        </div>
        <div class="status-card">
            <div class="status-dot" style="background:#8B5CF6;color:#fff;">${enviadas}</div>
            <div><small>Enviadas</small><b>${enviadas}</b></div>
        </div>
        <div class="status-card">
            <div class="status-dot dot-approved">${confirmadas}</div>
            <div><small>Confirmadas</small><b>${confirmadas}</b></div>
        </div>
        <div class="status-card">
            <div class="status-dot" style="background:#EF4444;color:#fff;">${anuladas}</div>
            <div><small>Anuladas</small><b>${anuladas}</b></div>
        </div>
    `;
}

// ============================================================
// FUNCIONES DE UTILIDAD
// ============================================================

function getEstadoClass(estado) {
    const map = {
        'Borrador': 'b-draft',
        'Pendiente': 'b-pending',
        'Aprobada': 'b-approved',
        'Aceptada': 'b-approved',
        'Ordenada': 'b-ordered',
        'Rechazada': 'b-canceled',
        'En evaluación': 'b-pending',
        'Seleccionado': 'b-approved',
        'Emitida': 'b-ok',
        'Enviada': 'b-sent',
        'Confirmada': 'b-approved',
        'Anulada': 'b-canceled',
        'Registrado': 'b-ok',
        'Pagado': 'b-approved',
        'En inspección': 'b-pending',
        'Almacenada': 'b-ok'
    };
    return map[estado] || 'b-gray';
}

function toggleMenu(event, menuId) {
    event.stopPropagation();
    document.querySelectorAll('.menu-pop').forEach(el => el.style.display = 'none');
    const menu = document.getElementById(`menu-${menuId}`);
    if (menu) {
        menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
        menu.style.left = `${event.clientX - 180}px`;
        menu.style.top = `${event.clientY - 10}px`;
    }
}

document.addEventListener('click', function() {
    document.querySelectorAll('.menu-pop').forEach(el => el.style.display = 'none');
});

function formatearFecha(fecha) {
    if (!fecha) return '-';
    // "2026-10-16" / "2026-10-16T14:47:48" (hora de Lima): se toma el texto tal cual; new Date() lo corría un día
    const m = String(fecha).match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (m) return `${m[3]}/${m[2]}/${m[1]}`;
    if (window.fechaHoraLima) return window.fechaHoraLima(fecha, false);
    try {
        const date = new Date(fecha);
        if (isNaN(date.getTime())) return fecha;
        const day = String(date.getDate()).padStart(2, '0');
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const year = date.getFullYear();
        return `${day}/${month}/${year}`;
    } catch (e) {
        return fecha;
    }
}

function filtrarPorFecha(item, fechaInicioId, fechaFinId) {
    const fechaInicio = document.getElementById(fechaInicioId)?.value;
    const fechaFin = document.getElementById(fechaFinId)?.value;
    
    if (!fechaInicio && !fechaFin) return true;
    
    // Se compara el texto AAAA-MM-DD: con new Date() la fecha se corría un día por la zona horaria de Lima
    const fechaItem = fechaISO(item.fecha || item.fecha_creacion);
    if (!fechaItem) return false;
    if (fechaInicio && fechaItem < fechaInicio) return false;
    if (fechaFin && fechaItem > fechaFin) return false;
    return true;
}

function fechaISO(v) {
    if (!v) return '';
    const s = String(v);
    if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(0, 10);
    const d = new Date(s);
    if (isNaN(d.getTime())) return '';
    return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

function escCompras(v) {
    return String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// ============================================================
// FILTROS: la tabla se actualiza sola al cambiar cualquier filtro
// (antes no había ningún evento conectado a los filtros, por eso no pasaba nada)
// ============================================================
const FILTROS_COMPRAS = {
    solicitud: { render: () => renderSolicitudes(), ids: ['solicitudSearch', 'solicitudStatus', 'solicitudFechaInicio', 'solicitudFechaFin'] },
    comparativo: { render: () => renderComparativos(), ids: ['comparativoSearch', 'comparativoStatus', 'comparativoFechaInicio', 'comparativoFechaFin'] },
    orden: { render: () => renderOrdenes(), ids: ['ordenSearch', 'ordenStatus', 'ordenFechaInicio', 'ordenFechaFin'] },
    compProv: { render: () => renderComprobantesProveedor(), ids: ['compProvSearch', 'compProvStatus', 'compProvFechaInicio', 'compProvFechaFin'] },
    recepcion: { render: () => renderRecepciones(), ids: ['recepcionSearch', 'recepcionStatus', 'recepcionFechaInicio', 'recepcionFechaFin'] }
};

function conectarFiltrosCompras() {
    Object.values(FILTROS_COMPRAS).forEach(f => {
        f.ids.forEach(id => {
            const el = document.getElementById(id);
            if (!el || el.dataset.filtroConectado) return;
            el.dataset.filtroConectado = '1';
            el.addEventListener('input', f.render);
            el.addEventListener('change', f.render);
        });
    });
}

// La "X" del filtro de fechas: antes llamaba a funciones que no existían (no hacía nada)
function limpiarFechasCompras(clave) {
    const f = FILTROS_COMPRAS[clave];
    if (!f) return;
    document.getElementById(f.ids[2]).value = '';
    document.getElementById(f.ids[3]).value = '';
    f.render();
}
function clearSolicitudDateFilter() { limpiarFechasCompras('solicitud'); }
function clearComparativoDateFilter() { limpiarFechasCompras('comparativo'); }
function clearOrdenDateFilter() { limpiarFechasCompras('orden'); }
function clearCompProvDateFilter() { limpiarFechasCompras('compProv'); }
function clearRecepcionDateFilter() { limpiarFechasCompras('recepcion'); }

const ES_ADMIN_COMPRAS = (document.currentScript && document.currentScript.dataset.admin === 'true')
    || (document.body && document.body.dataset && document.body.dataset.comprasAdmin === 'true');
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', conectarFiltrosCompras);
else conectarFiltrosCompras();

// ============================================================
// FUNCIONES DE EDICIÓN
// ============================================================

function editSolicitud(id) {
    const solicitud = solicitudesData.find(s => s.id === id);
    if (!solicitud) {
        showToast('❌ Solicitud no encontrada', 'error');
        return;
    }
    
    document.getElementById('solicitudModal').classList.add('show');
    document.getElementById('solNumero').value = solicitud.numero || '';
    document.getElementById('solFecha').value = solicitud.fecha ? solicitud.fecha.split('T')[0] : '';
    document.getElementById('solProducto').value = solicitud.producto || '';
    document.getElementById('solCantidad').value = solicitud.cantidad || 1;
    document.getElementById('solUnidad').value = solicitud.unidad || 'UND';
    document.getElementById('solArea').value = solicitud.area || '';
    document.getElementById('solSolicitante').value = solicitud.solicitante || '';
    document.getElementById('solUrgencia').value = solicitud.urgencia || 'Media';
    document.getElementById('solJustificacion').value = solicitud.justificacion || '';
    
    const saveBtn = document.querySelector('#solicitudModal .btn-primary');
    if (saveBtn) {
        saveBtn.dataset.editId = id;
        saveBtn.textContent = '💾 Actualizar solicitud';
    }
    
    document.getElementById('solicitudModalTitle').textContent = `✏️ Editar solicitud: ${solicitud.numero}`;
    showToast(`📝 Editando solicitud: ${solicitud.numero}`, 'info');
}

function editComparativo(id) {
    const comparativo = comparativosData.find(c => c.id === id);
    if (!comparativo) {
        showToast('❌ Comparativo no encontrado', 'error');
        return;
    }
    
    document.getElementById('comparativoModal').classList.add('show');
    document.getElementById('compNumero').value = comparativo.numero || '';
    document.getElementById('compFecha').value = comparativo.fecha ? comparativo.fecha.split('T')[0] : '';
    document.getElementById('compProducto').value = comparativo.producto || '';
    
    const tbody = document.getElementById('comparativoItemsBody');
    tbody.innerHTML = '';
    
    if (comparativo.proveedores && comparativo.proveedores.length > 0) {
        comparativo.proveedores.forEach((p, index) => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${index + 1}</td>
                <td><input style="width:100%;border:none;background:transparent;padding:4px;" value="${p.nombre || ''}" placeholder="Nombre proveedor"></td>
                <td><input style="width:100%;border:none;background:transparent;padding:4px;" value="${p.ruc || ''}" placeholder="RUC"></td>
                <td><input type="number" step="0.01" style="width:100%;border:none;background:transparent;padding:4px;text-align:right;" value="${p.precio || 0}" placeholder="0.00"></td>
                <td><input style="width:100%;border:none;background:transparent;padding:4px;" value="${p.plazo || ''}" placeholder="días"></td>
                <td><input style="width:100%;border:none;background:transparent;padding:4px;" value="${p.condPago || 'Contado'}" placeholder="Contado/Crédito"></td>
                <td><button onclick="this.closest('tr').remove();" type="button" class="btn-tachito" title="Quitar" aria-label="Quitar">🗑️</button></td>
            `;
            tbody.appendChild(tr);
        });
    } else {
        addComparativoRow();
    }
    
    const saveBtn = document.querySelector('#comparativoModal .btn-primary');
    if (saveBtn) {
        saveBtn.dataset.editId = id;
        saveBtn.textContent = '💾 Actualizar comparativo';
    }
    
    document.getElementById('comparativoModalTitle').textContent = `✏️ Editar comparativo: ${comparativo.numero}`;
    showToast(`📝 Editando comparativo: ${comparativo.numero}`, 'info');
}

function editOrden(id) {
    const orden = ordenesData.find(o => o.id === id);
    if (!orden) {
        showToast('❌ Orden no encontrada', 'error');
        return;
    }
    
    ordResetForm();
    window._ordenEditId = id;  // al guardar se actualiza esta orden en lugar de crear otra
    document.getElementById('ordenCompraModal').classList.add('show');
    document.getElementById('ordNumero').value = orden.numero || '';
    document.getElementById('ordFecha').value = orden.fecha ? String(orden.fecha).slice(0, 10) : '';
    document.getElementById('ordProveedor').value = orden.proveedor || '';
    document.getElementById('ordRuc').value = orden.ruc || '';
    document.getElementById('ordDireccion').value = orden.direccion || '';
    document.getElementById('ordContacto').value = orden.contacto_proveedor || '';
    document.getElementById('ordTelefono').value = orden.telefono_proveedor || '';
    document.getElementById('ordEmail').value = orden.email_proveedor || '';
    ordPonerCondicion(orden.condicion_pago || 'Contado');
    document.getElementById('ordMoneda').value = orden.moneda || 'Soles (S/)';
    document.getElementById('ordNotas').value = orden.notas || '';
    document.getElementById('ordMotivo').value = orden.motivo_compra || '';
    document.getElementById('ordMotivoDetalle').value = orden.motivo_stock && orden.motivo_stock !== orden.motivo_compra ? orden.motivo_stock : '';
    ordCargarPedidos(orden.pedido_id || '');
    
    const tbody = document.getElementById('ordenItemsBody');
    tbody.innerHTML = '';
    (orden.items && orden.items.length ? orden.items : [{}]).forEach(item => addOrdenItemRowConDatos(item));
    ordRecalcular();
    
    const saveBtn = document.querySelector('#ordenCompraModal .btn-primary');
    if (saveBtn) {
        saveBtn.dataset.editId = id;
        saveBtn.textContent = '💾 Actualizar orden';
    }
    
    document.getElementById('ordenCompraModalTitle').textContent = `✏️ Editar orden: ${orden.numero}`;
    showToast(`📝 Editando orden: ${orden.numero}`, 'info');
}

function editComprobanteProveedor(id) {
    const comprobante = comprobantesProveedorData.find(c => c.id === id);
    if (!comprobante) {
        showToast('❌ Comprobante no encontrado', 'error');
        return;
    }
    
    document.getElementById('comprobanteProveedorModal').classList.add('show');
    document.getElementById('cpTipo').value = comprobante.tipo || 'Factura';
    document.getElementById('cpNumero').value = comprobante.numero || '';
    document.getElementById('cpFecha').value = comprobante.fecha ? comprobante.fecha.split('T')[0] : '';
    document.getElementById('cpMonto').value = comprobante.monto || 0;
    document.getElementById('cpRuc').value = comprobante.ruc || '';
    document.getElementById('cpProveedor').value = comprobante.proveedor || '';
    document.getElementById('cpOrden').value = comprobante.orden || '';
    document.getElementById('cpObs').value = comprobante.obs || '';
    
    const saveBtn = document.querySelector('#comprobanteProveedorModal .btn-primary');
    if (saveBtn) {
        saveBtn.dataset.editId = id;
        saveBtn.textContent = '💾 Actualizar comprobante';
    }
    
    document.getElementById('compProvModalTitle').textContent = `✏️ Editar comprobante: ${comprobante.numero}`;
    showToast(`📝 Editando comprobante: ${comprobante.numero}`, 'info');
}

function editRecepcion(id) {
    const recepcion = recepcionesData.find(r => r.id === id);
    if (!recepcion) {
        showToast('❌ Recepción no encontrada', 'error');
        return;
    }
    
    document.getElementById('recepcionModal').classList.add('show');
    document.getElementById('recNumero').value = recepcion.numero || '';
    document.getElementById('recFecha').value = recepcion.fecha ? recepcion.fecha.split('T')[0] : '';
    document.getElementById('recOrden').value = recepcion.orden || '';
    document.getElementById('recProveedor').value = recepcion.proveedor || '';
    document.getElementById('recProducto').value = recepcion.producto || '';
    document.getElementById('recCantidad').value = recepcion.cantidad || 1;
    document.getElementById('recUnidad').value = recepcion.unidad || 'UND';
    document.getElementById('recEstadoMercaderia').value = recepcion.estadoMercaderia || 'Buen estado';
    document.getElementById('recObs').value = recepcion.obs || '';
    
    const saveBtn = document.querySelector('#recepcionModal .btn-primary');
    if (saveBtn) {
        saveBtn.dataset.editId = id;
        saveBtn.textContent = '💾 Actualizar recepción';
    }
    
    document.getElementById('recepcionModalTitle').textContent = `✏️ Editar recepción: ${recepcion.numero}`;
    showToast(`📝 Editando recepción: ${recepcion.numero}`, 'info');
}

// ============================================================
// FUNCIONES DE ACCIONES (CON MODALES DE CONFIRMACIÓN)
// ============================================================

async function approveSolicitud(id) {
    const solicitud = solicitudesData.find(s => s.id === id);
    if (!solicitud) {
        showToast('❌ Solicitud no encontrada', 'error');
        return;
    }
    
    showApproveModal({
        title: '✅ Aprobar solicitud de compra',
        message: '¿Estás seguro de aprobar esta solicitud de compra?',
        details: `📋 Solicitud: ${solicitud.numero}\n📦 Producto: ${solicitud.producto}\n👤 Solicitante: ${solicitud.solicitante}\n📅 Fecha: ${formatearFecha(solicitud.fecha)}`,
        onConfirm: async () => {
            try {
                const response = await fetch(`/compras/api/solicitudes/${id}/toggle`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ estado: 'Aprobada' })
                });
                const result = await response.json();
                if (result.success) {
                    showToast('✅ Solicitud aprobada correctamente', 'success');
                    await cargarDatosCompras();
                    renderSolicitudes();
                } else {
                    showToast(`❌ Error: ${result.error}`, 'error');
                }
            } catch (error) {
                console.error('Error aprobando solicitud:', error);
                showToast('❌ Error al aprobar', 'error');
            }
        }
    });
}

async function deleteSolicitud(id) {
    const solicitud = solicitudesData.find(s => s.id === id);
    if (!solicitud) {
        showToast('❌ Solicitud no encontrada', 'error');
        return;
    }
    
    showDeleteModal({
        title: '🗑️ Eliminar solicitud de compra',
        message: '¿Estás seguro de eliminar esta solicitud de compra?',
        details: `📋 Solicitud: ${solicitud.numero}\n📦 Producto: ${solicitud.producto}\n👤 Solicitante: ${solicitud.solicitante}\n📅 Fecha: ${formatearFecha(solicitud.fecha)}`,
        onConfirm: async (motivo) => {
            try {
                const result = await enviarConMotivo(`/compras/api/solicitudes/${id}`, 'DELETE', motivo);
                if (result.success) {
                    showToast('✅ Solicitud eliminada correctamente', 'success');
                    await cargarDatosCompras();
                    renderSolicitudes();
                } else {
                    showToast(`❌ Error: ${result.error}`, 'error');
                }
            } catch (error) {
                console.error('Error eliminando solicitud:', error);
                showToast('❌ Error al eliminar', 'error');
            }
        }
    });
}

async function deleteComparativo(id) {
    const comparativo = comparativosData.find(c => c.id === id);
    if (!comparativo) {
        showToast('❌ Comparativo no encontrado', 'error');
        return;
    }
    
    showDeleteModal({
        title: '🗑️ Eliminar comparativo',
        message: '¿Estás seguro de eliminar este comparativo?',
        details: `📊 Comparativo: ${comparativo.numero}\n📦 Producto: ${comparativo.producto}\n📅 Fecha: ${formatearFecha(comparativo.fecha)}`,
        onConfirm: async () => {
            try {
                const response = await fetch(`/compras/api/comparativos/${id}`, {
                    method: 'DELETE'
                });
                const result = await response.json();
                if (result.success) {
                    showToast('✅ Comparativo eliminado correctamente', 'success');
                    await cargarDatosCompras();
                    renderComparativos();
                } else {
                    showToast(`❌ Error: ${result.error}`, 'error');
                }
            } catch (error) {
                console.error('Error eliminando comparativo:', error);
                showToast('❌ Error al eliminar', 'error');
            }
        }
    });
}

async function deleteOrden(id) {
    const orden = ordenesData.find(o => o.id === id);
    if (!orden) {
        showToast('❌ Orden no encontrada', 'error');
        return;
    }
    
    showDeleteModal({
        title: '🗑️ Eliminar orden de compra',
        message: '¿Estás seguro de eliminar esta orden de compra?',
        details: `📄 Orden: ${orden.numero}\n🏢 Proveedor: ${orden.proveedor}\n💰 Total: ${orden.moneda || 'S/'} ${orden.total.toFixed(2)}`,
        onConfirm: async (motivo) => {
            try {
                const result = await enviarConMotivo(`/compras/api/ordenes/${id}`, 'DELETE', motivo);
                if (result.success) {
                    showToast('✅ Orden eliminada correctamente', 'success');
                    await cargarDatosCompras();
                    renderOrdenes();
                } else {
                    showToast(`❌ Error: ${result.error}`, 'error');
                }
            } catch (error) {
                console.error('Error eliminando orden:', error);
                showToast('❌ Error al eliminar', 'error');
            }
        }
    });
}

async function anularOrden(id) {
    const orden = ordenesData.find(o => o.id === id);
    if (!orden) { showToast('❌ Orden no encontrada', 'error'); return; }
    showDeleteModal({
        title: '⛔ Anular orden de compra',
        message: '¿Anular esta orden de compra? No se borra: queda como "Anulada" con tu motivo.',
        details: `📄 Orden: ${orden.numero}\n🏢 Proveedor: ${orden.proveedor}\n💰 Total: S/ ${orden.total.toFixed(2)}`,
        confirmText: '⛔ Sí, anular',
        onConfirm: async (motivo) => {
            try {
                const result = await enviarConMotivo(`/compras/api/ordenes/${id}/toggle`, 'PUT', motivo, { estado: 'Anulada' });
                if (result.success) {
                    showToast('✅ Orden anulada', 'success');
                    await cargarDatosCompras();
                    renderOrdenes();
                } else {
                    showToast(`❌ Error: ${result.error}`, 'error');
                }
            } catch (error) {
                showToast('❌ Error al anular', 'error');
            }
        }
    });
}

async function sendOrden(id) {
    const orden = ordenesData.find(o => o.id === id);
    if (!orden) {
        showToast('❌ Orden no encontrada', 'error');
        return;
    }
    
    showSendModal({
        title: '📤 Enviar orden de compra',
        message: '¿Estás seguro de enviar esta orden de compra al proveedor?',
        details: `📄 Orden: ${orden.numero}\n🏢 Proveedor: ${orden.proveedor}\n💰 Total: ${orden.moneda || 'S/'} ${orden.total.toFixed(2)}`,
        onConfirm: async () => {
            try {
                const response = await fetch(`/compras/api/ordenes/${id}/toggle`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ estado: 'Enviada' })
                });
                const result = await response.json();
                if (result.success) {
                    showToast('📤 Orden enviada al proveedor correctamente', 'success');
                    await cargarDatosCompras();
                    renderOrdenes();
                } else {
                    showToast(`❌ Error: ${result.error}`, 'error');
                }
            } catch (error) {
                console.error('Error enviando orden:', error);
                showToast('❌ Error al enviar', 'error');
            }
        }
    });
}

async function deleteComprobanteProveedor(id) {
    const comprobante = comprobantesProveedorData.find(c => c.id === id);
    if (!comprobante) {
        showToast('❌ Comprobante no encontrado', 'error');
        return;
    }
    
    showDeleteModal({
        title: '⛔ Anular comprobante del proveedor',
        message: '¿Anular este comprobante? No se borra: queda como "Anulado" con tu motivo y sale de Cuentas por pagar.',
        details: `🧾 Tipo: ${comprobante.tipo}\n📋 N°: ${comprobante.numero}\n🏢 Proveedor: ${comprobante.proveedor}\n💰 Monto: S/ ${comprobante.monto.toFixed(2)}`,
        confirmText: '⛔ Sí, anular',
        onConfirm: async (motivo) => {
            try {
                const result = await enviarConMotivo(`/compras/api/comprobantes-proveedor/${id}`, 'DELETE', motivo);
                if (result.success) {
                    showToast('✅ Comprobante anulado', 'success');
                    await cargarDatosCompras();
                    renderComprobantesProveedor();
                } else {
                    showToast(`❌ Error: ${result.error}`, 'error');
                }
            } catch (error) {
                console.error('Error eliminando comprobante:', error);
                showToast('❌ Error al eliminar', 'error');
            }
        }
    });
}

async function deleteRecepcion(id) {
    const recepcion = recepcionesData.find(r => r.id === id);
    if (!recepcion) {
        showToast('❌ Recepción no encontrada', 'error');
        return;
    }
    
    showDeleteModal({
        title: '🗑️ Eliminar recepción',
        message: '¿Estás seguro de eliminar esta recepción?',
        details: `📦 Recepción: ${recepcion.numero}\n📄 Orden: ${recepcion.orden}\n🏢 Proveedor: ${recepcion.proveedor}\n📦 Producto: ${recepcion.producto}`,
        onConfirm: async () => {
            try {
                const response = await fetch(`/compras/api/recepciones/${id}`, {
                    method: 'DELETE'
                });
                const result = await response.json();
                if (result.success) {
                    showToast('✅ Recepción eliminada correctamente', 'success');
                    await cargarDatosCompras();
                    renderRecepciones();
                } else {
                    showToast(`❌ Error: ${result.error}`, 'error');
                }
            } catch (error) {
                console.error('Error eliminando recepción:', error);
                showToast('❌ Error al eliminar', 'error');
            }
        }
    });
}

async function approveRecepcion(id) {
    const recepcion = recepcionesData.find(r => r.id === id);
    if (!recepcion) {
        showToast('❌ Recepción no encontrada', 'error');
        return;
    }
    
    showApproveModal({
        title: '✅ Aprobar recepción de mercadería',
        message: '¿Estás seguro de aprobar esta recepción?',
        details: `📦 Recepción: ${recepcion.numero}\n📦 Producto: ${recepcion.producto}\n💰 Cantidad: ${recepcion.cantidad} ${recepcion.unidad}\n🏢 Proveedor: ${recepcion.proveedor}`,
        onConfirm: async () => {
            try {
                const response = await fetch(`/compras/api/recepciones/${id}/toggle`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ estado: 'Aprobada' })
                });
                const result = await response.json();
                if (result.success) {
                    showToast('✅ Recepción aprobada correctamente', 'success');
                    await cargarDatosCompras();
                    renderRecepciones();
                } else {
                    showToast(`❌ Error: ${result.error}`, 'error');
                }
            } catch (error) {
                console.error('Error aprobando recepción:', error);
                showToast('❌ Error al aprobar', 'error');
            }
        }
    });
}

async function payComprobanteProveedor(id) {
    const comprobante = comprobantesProveedorData.find(c => c.id === id);
    if (!comprobante) {
        showToast('❌ Comprobante no encontrado', 'error');
        return;
    }
    
    showConfirmModal({
        title: '💰 Confirmar pago',
        message: '¿Estás seguro de marcar este comprobante como pagado?',
        details: `🧾 Comprobante: ${comprobante.numero}\n🏢 Proveedor: ${comprobante.proveedor}\n💰 Monto: S/ ${comprobante.monto.toFixed(2)}`,
        icon: '💰',
        btnClass: 'btn-green',
        confirmText: '💰 Sí, marcar pagado',
        onConfirm: async () => {
            try {
                const response = await fetch(`/compras/api/comprobantes-proveedor/${id}/toggle`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ estado: 'Pagado' })
                });
                const result = await response.json();
                if (result.success) {
                    showToast('💰 Comprobante marcado como pagado', 'success');
                    await cargarDatosCompras();
                    renderComprobantesProveedor();
                } else {
                    showToast(`❌ Error: ${result.error}`, 'error');
                }
            } catch (error) {
                console.error('Error pagando comprobante:', error);
                showToast('❌ Error al pagar', 'error');
            }
        }
    });
}

async function selectProveedor(id) {
    const comparativo = comparativosData.find(c => c.id === id);
    if (!comparativo) {
        showToast('❌ Comparativo no encontrado', 'error');
        return;
    }
    
    const proveedorSeleccionado = (comparativo.proveedores || []).reduce((min, p) => {
        if (!min || min.precio === undefined) return p;
        return (p.precio || 0) < (min.precio || 0) ? p : min;
    }, null);
    
    showConfirmModal({
        title: '✅ Seleccionar proveedor',
        message: '¿Estás seguro de seleccionar este proveedor para la compra?',
        details: `📊 Comparativo: ${comparativo.numero}\n📦 Producto: ${comparativo.producto}\n🏢 Proveedor: ${proveedorSeleccionado?.nombre || 'No disponible'}\n💰 Precio: S/ ${proveedorSeleccionado?.precio?.toFixed(2) || '0.00'}`,
        icon: '✅',
        btnClass: 'btn-green',
        confirmText: '✅ Sí, seleccionar',
        onConfirm: async () => {
            try {
                const response = await fetch(`/compras/api/comparativos/${id}/toggle`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ estado: 'Seleccionado' })
                });
                const result = await response.json();
                if (result.success) {
                    showToast('✅ Proveedor seleccionado correctamente', 'success');
                    await cargarDatosCompras();
                    renderComparativos();
                } else {
                    showToast(`❌ Error: ${result.error}`, 'error');
                }
            } catch (error) {
                console.error('Error seleccionando proveedor:', error);
                showToast('❌ Error al seleccionar', 'error');
            }
        }
    });
}

function createOrdenFromSolicitud(id) {
    const solicitud = solicitudesData.find(s => s.id === id);
    if (!solicitud) {
        showToast('❌ Solicitud no encontrada', 'error');
        return;
    }
    
    showConfirmModal({
        title: '📄 Crear orden de compra',
        message: '¿Estás seguro de crear una orden de compra desde esta solicitud?',
        details: `📋 Solicitud: ${solicitud.numero}\n📦 Producto: ${solicitud.producto}\n💰 Cantidad: ${solicitud.cantidad} ${solicitud.unidad}`,
        icon: '📄',
        btnClass: 'btn-blue',
        confirmText: '📄 Sí, crear orden',
        onConfirm: () => {
            // Antes se creaba una OC "de mentira" solo en pantalla (no se guardaba). Ahora abre el formulario real.
            switchTab('orden_compra');
            openOrdenCompraModal();
            const tbody = document.getElementById('ordenItemsBody');
            tbody.innerHTML = '';
            addOrdenItemRowConDatos({ producto: solicitud.producto, cantidad: solicitud.cantidad, um: solicitud.unidad });
            document.getElementById('ordNotas').value = `Según solicitud ${solicitud.numero}`;
            showToast(`📄 Completa la orden para la solicitud ${solicitud.numero}`, 'info');
        }
    });
}

function createRecepcionFromOrden(id) {
    const orden = ordenesData.find(o => o.id === id);
    if (!orden) {
        showToast('❌ Orden no encontrada', 'error');
        return;
    }
    
    showReceiveModal({
        title: '📦 Confirmar recepción',
        message: '¿Estás seguro de crear una recepción desde esta orden de compra?',
        details: `📄 Orden: ${orden.numero}\n🏢 Proveedor: ${orden.proveedor}\n💰 Total: ${orden.moneda || 'S/'} ${orden.total.toFixed(2)}`,
        onConfirm: () => {
            const nuevaRecepcion = {
                id: recepcionesData.length + 1,
                numero: `REC-${new Date().toISOString().slice(0,10).replace(/-/g,'')}-${String(recepcionesData.length + 1).padStart(4,'0')}`,
                fecha: new Date().toISOString().slice(0,10),
                estado: 'Pendiente',
                orden: orden.numero,
                proveedor: orden.proveedor,
                producto: (orden.items || []).map(i => i.producto).join(', '),
                cantidad: (orden.items || []).reduce((sum, i) => sum + i.cantidad, 0),
                unidad: 'UND',
                estadoMercaderia: 'Buen estado',
                obs: ''
            };
            recepcionesData.push(nuevaRecepcion);
            renderRecepciones();
            showToast(`📦 Recepción creada desde orden ${orden.numero}`, 'success');
            switchTab('recepcion');
        }
    });
}

async function storeRecepcion(id) {
    const recepcion = recepcionesData.find(r => r.id === id);
    if (!recepcion) {
        showToast('❌ Recepción no encontrada', 'error');
        return;
    }
    
    showConfirmModal({
        title: '📦 Almacenar mercadería',
        message: '¿Estás seguro de almacenar esta mercadería en el inventario?',
        details: `📦 Recepción: ${recepcion.numero}\n📦 Producto: ${recepcion.producto}\n💰 Cantidad: ${recepcion.cantidad} ${recepcion.unidad}\n🏢 Proveedor: ${recepcion.proveedor}`,
        icon: '📦',
        btnClass: 'btn-green',
        confirmText: '📦 Sí, almacenar',
        onConfirm: async () => {
            try {
                const response = await fetch(`/compras/api/recepciones/${id}/toggle`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ estado: 'Almacenada' })
                });
                const result = await response.json();
                if (result.success) {
                    showToast('📦 Mercadería almacenada en inventario', 'success');
                    await cargarDatosCompras();
                    renderRecepciones();
                } else {
                    showToast(`❌ Error: ${result.error}`, 'error');
                }
            } catch (error) {
                console.error('Error almacenando recepción:', error);
                showToast('❌ Error al almacenar', 'error');
            }
        }
    });
}

// ============================================================
// FUNCIONES DE MODALES
// ============================================================

function hoyLocalISO() {
    return new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

function resetSolicitudForm() {
    // Antes "+ Nueva solicitud" reabría el último modal (con sus datos y en modo "Actualizar"):
    // el id de edición quedaba guardado en el botón y los campos no se limpiaban.
    const modal = document.getElementById('solicitudModal');
    modal.querySelectorAll('input, textarea').forEach(el => {
        if (el.type === 'number') el.value = el.defaultValue || '';
        else el.value = '';
    });
    modal.querySelectorAll('select').forEach(el => {
        const def = [...el.options].findIndex(o => o.defaultSelected);
        el.selectedIndex = def >= 0 ? def : 0;
    });
    const saveBtn = modal.querySelector('.btn-primary');
    if (saveBtn) {
        delete saveBtn.dataset.editId;
        saveBtn.textContent = '📤 Enviar a aprobación';
    }
    document.getElementById('solicitudModalTitle').textContent = '📋 Nueva solicitud de compra';
    if (typeof solCalcularTotal === 'function') solCalcularTotal();
}

function openSolicitudModal() {
    resetSolicitudForm();
    document.getElementById('solicitudModal').classList.add('show');
    document.getElementById('solFecha').value = hoyLocalISO();
    document.getElementById('solNumero').value = `SOL-${new Date().toISOString().slice(0,10).replace(/-/g,'')}-${String(solicitudesData.length + 1).padStart(4,'0')}`;
}

function openComparativoModal() {
    document.getElementById('comparativoModal').classList.add('show');
    document.getElementById('compFecha').value = new Date().toISOString().slice(0,10);
    document.getElementById('compNumero').value = `CMP-${new Date().toISOString().slice(0,10).replace(/-/g,'')}-${String(comparativosData.length + 1).padStart(4,'0')}`;
}

function openOrdenCompraModal() {
    // Antes solo cambiaba la fecha y el número: proveedor, productos y totales de la OC anterior seguían ahí.
    ordResetForm();
    ordCargarPedidos('');
    ordRecalcular();
    document.getElementById('ordenCompraModal').classList.add('show');
}

function openComprobanteProveedorModal() {
    document.getElementById('comprobanteProveedorModal').classList.add('show');
    document.getElementById('cpFecha').value = new Date().toISOString().slice(0,10);
}

function openRecepcionModal() {
    document.getElementById('recepcionModal').classList.add('show');
    document.getElementById('recFecha').value = new Date().toISOString().slice(0,10);
    document.getElementById('recNumero').value = `REC-${new Date().toISOString().slice(0,10).replace(/-/g,'')}-${String(recepcionesData.length + 1).padStart(4,'0')}`;
}

// ============================================================
// FUNCIONES DE GUARDADO (CON API)
// ============================================================

async function saveSolicitud(estado) {
    const editId = document.querySelector('#solicitudModal .btn-primary')?.dataset?.editId;
    
    const data = {
        id: editId ? parseInt(editId) : null,
        numero_solicitud: document.getElementById('solNumero').value,
        fecha: document.getElementById('solFecha').value,
        estado: estado,
        producto: document.getElementById('solProducto').value,
        cantidad: parseInt(document.getElementById('solCantidad').value) || 1,
        unidad: document.getElementById('solUnidad').value,
        area: document.getElementById('solArea').value,
        solicitante: document.getElementById('solSolicitante').value,
        urgencia: document.getElementById('solUrgencia').value,
        justificacion: document.getElementById('solJustificacion').value
    };
    
    try {
        const response = await fetch('/compras/api/solicitudes/guardar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await response.json();
        if (result.success) {
            showToast(`✅ Solicitud ${data.numero_solicitud} guardada correctamente`, 'success');
            resetSolicitudForm();
            closeModal('solicitudModal');
            await cargarDatosCompras();
            renderSolicitudes();
        } else {
            showToast(`❌ Error: ${result.error}`, 'error');
        }
    } catch (error) {
        console.error('Error guardando solicitud:', error);
        showToast('❌ Error al guardar en la base de datos', 'error');
    }
}

async function saveComparativo(estado) {
    const proveedores = [];
    document.querySelectorAll('#comparativoItemsBody tr').forEach(row => {
        const inputs = row.querySelectorAll('input');
        if (inputs.length >= 4) {
            proveedores.push({
                nombre: inputs[0].value || 'Sin nombre',
                ruc: inputs[1].value || 'Sin RUC',
                precio: parseFloat(inputs[2].value) || 0,
                plazo: inputs[3].value || 'N/A',
                condPago: inputs[4]?.value || 'Contado'
            });
        }
    });
    
    const data = {
        numero_comparativo: document.getElementById('compNumero').value,
        fecha: document.getElementById('compFecha').value,
        estado: estado,
        producto: document.getElementById('compProducto').value,
        proveedores: proveedores
    };
    
    try {
        const response = await fetch('/compras/api/comparativos/guardar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await response.json();
        if (result.success) {
            showToast(`✅ Comparativo ${data.numero_comparativo} guardado`, 'success');
            await cargarDatosCompras();
            renderComparativos();
        } else {
            showToast(`❌ Error: ${result.error}`, 'error');
        }
    } catch (error) {
        console.error('Error guardando comparativo:', error);
        showToast('❌ Error al guardar', 'error');
    }
    closeModal('comparativoModal');
}

async function saveOrdenCompra(estado) {
    const items = [];
    document.querySelectorAll('#ordenItemsBody tr').forEach(row => {
        const desc = row.querySelector('.ord-item-desc');
        if (!desc) return;
        const producto = desc.value.trim() || 'Sin producto';
        const cantidad = parseFloat(row.querySelector('.ord-item-cant')?.value) || 0;
        const precioUnitario = parseFloat(row.querySelector('.ord-item-precio')?.value) || 0;
        items.push({ producto, cantidad, precioUnitario, total: cantidad * precioUnitario,
                     unidad: row.querySelector('.ord-item-unidad')?.value || 'UND' });
    });
    const pedidoId = document.getElementById('ordPedido')?.value || '';
    const motivoCompra = document.getElementById('ordMotivo')?.value || '';
    const motivoDetalle = (document.getElementById('ordMotivoDetalle')?.value || '').trim();
    if (!pedidoId && !motivoCompra) {
        showToast('⚠️ Es una compra SIN pedido: elige el motivo', 'warning');
        document.getElementById('ordMotivo')?.focus();
        return;
    }
    if (!pedidoId && motivoCompra === 'Otro' && motivoDetalle.length < 5) {
        showToast('⚠️ Elegiste "Otro": escribe el detalle del motivo', 'warning');
        return;
    }
    
    const subtotal = items.reduce((sum, i) => sum + i.total, 0);
    const igv = subtotal * 0.18;
    const total = subtotal + igv;
    
    if (document.getElementById('ordCondPago').value === 'Crédito' && !(parseInt(document.getElementById('ordDiasCredito').value, 10) > 0)) {
        showToast('⚠️ Escribe el número de días de crédito', 'warning');
        return;
    }
    const data = {
        id: window._ordenEditId || null,
        numero_orden: document.getElementById('ordNumero').value,
        fecha_creacion: document.getElementById('ordFecha').value,
        estado: estado,
        proveedor: document.getElementById('ordProveedor').value,
        proveedor_id: window._ordProveedorId || null,
        ruc: document.getElementById('ordRuc').value,
        condicion_pago: ordCondicionValor(),
        moneda: document.getElementById('ordMoneda').value,
        fecha_requerida: document.getElementById('ordFechaRequerida').value,
        tiempo_entrega: document.getElementById('ordTiempoEntrega').value,
        lugar_entrega: document.getElementById('ordLugarEntrega').value,
        contacto_proveedor: document.getElementById('ordContacto').value,
        telefono_proveedor: document.getElementById('ordTelefono').value,
        email_proveedor: document.getElementById('ordEmail').value,
        notas: document.getElementById('ordNotas').value,
        descuento_porcentaje: document.getElementById('ordDescuentoTipo').value === 'porcentaje' ? (parseFloat(document.getElementById('ordDescuento').value) || 0) : 0,
        pedido_id: pedidoId || null,
        motivo_compra: pedidoId ? '' : motivoCompra,
        motivo_stock: pedidoId ? '' : motivoDetalle,
        items: items,
        subtotal: subtotal,
        igv: igv,
        total: total
    };
    
    try {
        const response = await fetch('/compras/api/ordenes/guardar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await response.json();
        if (result.success) {
            showToast(`✅ Orden ${(result.data && result.data.numero_orden) || data.numero_orden} guardada`, 'success');
            if (result.advertencia) showToast('⚠️ ' + result.advertencia, 'warning');
            window._ordenEditId = null;
            closeModal('ordenCompraModal');
            await cargarDatosCompras();
            renderOrdenes();
        } else {
            showToast(`❌ Error: ${result.error}`, 'error');
        }
    } catch (error) {
        console.error('Error guardando orden:', error);
        showToast('❌ Error al guardar', 'error');
    }
}

async function saveComprobanteProveedor(estado) {
    const data = {
        tipo: document.getElementById('cpTipo').value,
        numero: document.getElementById('cpNumero').value,
        fecha: document.getElementById('cpFecha').value,
        monto: parseFloat(document.getElementById('cpMonto').value) || 0,
        ruc: document.getElementById('cpRuc').value,
        proveedor: document.getElementById('cpProveedor').value,
        orden_compra: document.getElementById('cpOrden').value,
        estado: estado,
        observaciones: document.getElementById('cpObs').value
    };
    
    try {
        const response = await fetch('/compras/api/comprobantes-proveedor/guardar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await response.json();
        if (result.success) {
            showToast(`✅ Comprobante ${data.numero} guardado`, 'success');
            await cargarDatosCompras();
            renderComprobantesProveedor();
        } else {
            showToast(`❌ Error: ${result.error}`, 'error');
        }
    } catch (error) {
        console.error('Error guardando comprobante:', error);
        showToast('❌ Error al guardar', 'error');
    }
    closeModal('comprobanteProveedorModal');
}

async function saveRecepcion(estado) {
    const data = {
        numero_recepcion: document.getElementById('recNumero').value,
        fecha: document.getElementById('recFecha').value,
        estado: estado,
        orden_compra: document.getElementById('recOrden').value,
        proveedor: document.getElementById('recProveedor').value,
        producto: document.getElementById('recProducto').value,
        cantidad: parseInt(document.getElementById('recCantidad').value) || 1,
        unidad: document.getElementById('recUnidad').value,
        estado_mercaderia: document.getElementById('recEstadoMercaderia').value,
        observaciones: document.getElementById('recObs').value
    };
    
    try {
        const response = await fetch('/compras/api/recepciones/guardar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await response.json();
        if (result.success) {
            showToast(`✅ Recepción ${data.numero_recepcion} guardada`, 'success');
            await cargarDatosCompras();
            renderRecepciones();
        } else {
            showToast(`❌ Error: ${result.error}`, 'error');
        }
    } catch (error) {
        console.error('Error guardando recepción:', error);
        showToast('❌ Error al guardar', 'error');
    }
    closeModal('recepcionModal');
}

// ============================================================
// FUNCIONES DE EXPORTACIÓN
// ============================================================

function exportData(tipo) {
    // Antes bajaba un .json que Excel no abre; ahora exporta la tabla que se ve a Excel (static/js/exportar_tabla.js)
    if (typeof window.exportarModulo === 'function') return window.exportarModulo(tipo);
    let data = [];
    let filename = '';
    
    switch(tipo) {
        case 'solicitud_compra':
            data = solicitudesData;
            filename = `solicitudes_compra_${new Date().toISOString().slice(0,10)}.json`;
            break;
        case 'comparativo':
            data = comparativosData;
            filename = `comparativos_${new Date().toISOString().slice(0,10)}.json`;
            break;
        case 'orden_compra':
            data = ordenesData;
            filename = `ordenes_compra_${new Date().toISOString().slice(0,10)}.json`;
            break;
        case 'comprobante_proveedor':
            data = comprobantesProveedorData;
            filename = `comprobantes_proveedor_${new Date().toISOString().slice(0,10)}.json`;
            break;
        case 'recepcion':
            data = recepcionesData;
            filename = `recepciones_${new Date().toISOString().slice(0,10)}.json`;
            break;
    }
    
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    showToast('📥 Datos exportados correctamente', 'success');
}

// ============================================================
// FUNCIONES PARA AGREGAR FILAS EN MODALES
// ============================================================

function addComparativoRow() {
    const tbody = document.getElementById('comparativoItemsBody');
    const count = tbody.children.length + 1;
    const tr = document.createElement('tr');
    tr.innerHTML = `
        <td>${count}</td>
        <td><input style="width:100%;border:none;background:transparent;padding:4px;" placeholder="Nombre proveedor"></td>
        <td><input style="width:100%;border:none;background:transparent;padding:4px;" placeholder="RUC"></td>
        <td><input type="number" step="0.01" style="width:100%;border:none;background:transparent;padding:4px;text-align:right;" placeholder="0.00"></td>
        <td><input style="width:100%;border:none;background:transparent;padding:4px;" placeholder="días"></td>
        <td><input style="width:100%;border:none;background:transparent;padding:4px;" placeholder="Contado/Crédito"></td>
        <td><button onclick="this.closest('tr').remove();" type="button" class="btn-tachito" title="Quitar" aria-label="Quitar">🗑️</button></td>
    `;
    tbody.appendChild(tr);
}

// Las filas de la OC las crea el modal (orden_compra_modal.html: addOrdenItemRow / ordRecalcular).
// Antes este archivo tenía otra versión de addOrdenItemRow sin clases que la reemplazaba y rompía los totales.
function calcularTotalOrden() { ordRecalcular(); }
function calcularTotalOrdenGeneral() { ordRecalcular(); }

// ============================================================
// FUNCIONES DE UTILIDAD
// ============================================================

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.remove('show');
}

function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.add('show');
}

function showToast(message, type = 'info') {
    const existing = document.querySelector('.toast-custom');
    if (existing) existing.remove();
    
    const toast = document.createElement('div');
    toast.className = `toast-custom toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(20px)';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function switchTab(tabId) {
    // Cambiar pestaña activa
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.tab === tabId) {
            btn.classList.add('active');
        }
    });
    
    // Mostrar la sección correspondiente
    document.querySelectorAll('.section').forEach(sec => {
        sec.classList.remove('active');
    });
    const section = document.getElementById(tabId);
    if (section) {
        section.classList.add('active');
    }
    
    // Actualizar URL
    const url = new URL(window.location);
    url.searchParams.set('tab', tabId);
    window.history.pushState({}, '', url);
    
    // Cargar datos
    initCompras(tabId);
}

// ============================================================
// FUNCIÓN DE INICIALIZACIÓN PRINCIPAL
// ============================================================

async function initCompras(tabId) {
    console.log(`🔄 initCompras llamado con tab: ${tabId}`);
    
    await cargarDatosCompras();
    
    switch(tabId) {
        case 'solicitud_compra':
            renderSolicitudes();
            break;
        case 'comparativo':
            renderComparativos();
            break;
        case 'orden_compra':
            renderOrdenes();
            break;
        case 'comprobante_proveedor':
            renderComprobantesProveedor();
            break;
        case 'recepcion':
            renderRecepciones();
            break;
        default:
            renderSolicitudes();
    }
}

// ============================================================
// FUNCIÓN PARA CARGAR DATOS DESDE LA API
// ============================================================

async function cargarDatosCompras() {
    console.log('📡 Cargando datos de compras desde la API...');
    
    try {
        const solicitudesResp = await fetch('/compras/api/solicitudes/listar');
        const solicitudesDataResp = await solicitudesResp.json();
        if (solicitudesDataResp.success) {
            window.solicitudesData = solicitudesDataResp.data || [];
            solicitudesData = window.solicitudesData;
            console.log(`✅ Solicitudes cargadas: ${solicitudesData.length}`);
        }
        
        const comparativosResp = await fetch('/compras/api/comparativos/listar');
        const comparativosDataResp = await comparativosResp.json();
        if (comparativosDataResp.success) {
            window.comparativosData = comparativosDataResp.data || [];
            comparativosData = window.comparativosData;
            console.log(`✅ Comparativos cargados: ${comparativosData.length}`);
        }
        
        const ordenesResp = await fetch('/compras/api/ordenes/listar');
        const ordenesDataResp = await ordenesResp.json();
        if (ordenesDataResp.success) {
            window.ordenesData = ordenesDataResp.data || [];
            ordenesData = window.ordenesData;
            console.log(`✅ Órdenes cargadas: ${ordenesData.length}`);
        }
        
        const compResp = await fetch('/compras/api/comprobantes-proveedor/listar');
        const compDataResp = await compResp.json();
        if (compDataResp.success) {
            window.comprobantesProveedorData = compDataResp.data || [];
            comprobantesProveedorData = window.comprobantesProveedorData;
            console.log(`✅ Comprobantes cargados: ${comprobantesProveedorData.length}`);
        }
        
        const recepcionesResp = await fetch('/compras/api/recepciones/listar');
        const recepcionesDataResp = await recepcionesResp.json();
        if (recepcionesDataResp.success) {
            window.recepcionesData = recepcionesDataResp.data || [];
            recepcionesData = window.recepcionesData;
            console.log(`✅ Recepciones cargadas: ${recepcionesData.length}`);
        }
        
        console.log('✅ Todos los datos cargados correctamente');
        
    } catch (error) {
        console.error('❌ Error cargando datos:', error);
        showToast('Error al cargar datos de compras', 'error');
    }
}

// ============================================================
// EXPONER FUNCIONES GLOBALMENTE
// ============================================================

window.initCompras = initCompras;
window.renderSolicitudes = renderSolicitudes;
window.renderComparativos = renderComparativos;
window.renderOrdenes = renderOrdenes;
window.renderComprobantesProveedor = renderComprobantesProveedor;
window.renderRecepciones = renderRecepciones;

window.openSolicitudModal = openSolicitudModal;
window.openComparativoModal = openComparativoModal;
window.openOrdenCompraModal = openOrdenCompraModal;
window.openComprobanteProveedorModal = openComprobanteProveedorModal;
window.openRecepcionModal = openRecepcionModal;

window.saveSolicitud = saveSolicitud;
window.saveComparativo = saveComparativo;
window.saveOrdenCompra = saveOrdenCompra;
window.saveComprobanteProveedor = saveComprobanteProveedor;
window.saveRecepcion = saveRecepcion;

window.closeModal = closeModal;
window.openModal = openModal;
window.showToast = showToast;
window.exportData = exportData;
window.toggleMenu = toggleMenu;
window.addComparativoRow = addComparativoRow;
window.calcularTotalOrden = calcularTotalOrden;
window.calcularTotalOrdenGeneral = calcularTotalOrdenGeneral;

window.approveSolicitud = approveSolicitud;
window.deleteSolicitud = deleteSolicitud;
window.deleteComparativo = deleteComparativo;
window.deleteOrden = deleteOrden;
window.anularOrden = anularOrden;
window.clearSolicitudDateFilter = clearSolicitudDateFilter;
window.clearComparativoDateFilter = clearComparativoDateFilter;
window.clearOrdenDateFilter = clearOrdenDateFilter;
window.clearCompProvDateFilter = clearCompProvDateFilter;
window.clearRecepcionDateFilter = clearRecepcionDateFilter;
window.sendOrden = sendOrden;
window.deleteComprobanteProveedor = deleteComprobanteProveedor;
window.deleteRecepcion = deleteRecepcion;
window.approveRecepcion = approveRecepcion;
window.payComprobanteProveedor = payComprobanteProveedor;
window.selectProveedor = selectProveedor;
window.createOrdenFromSolicitud = createOrdenFromSolicitud;
window.createRecepcionFromOrden = createRecepcionFromOrden;
window.storeRecepcion = storeRecepcion;

// Funciones de modales de confirmación
window.showConfirmModal = showConfirmModal;
window.closeConfirmModal = closeConfirmModal;
window.executeConfirmAction = executeConfirmAction;
window.showDeleteModal = showDeleteModal;
window.closeDeleteModal = closeDeleteModal;
window.executeDeleteAction = executeDeleteAction;
window.showApproveModal = showApproveModal;
window.closeApproveModal = closeApproveModal;
window.executeApproveAction = executeApproveAction;
window.showSendModal = showSendModal;
window.closeSendModal = closeSendModal;
window.executeSendAction = executeSendAction;
window.showReceiveModal = showReceiveModal;
window.closeReceiveModal = closeReceiveModal;
window.executeReceiveAction = executeReceiveAction;

console.log('✅ Módulo de Compras cargado correctamente');