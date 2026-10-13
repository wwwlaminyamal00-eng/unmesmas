// ============================================================
// MÓDULO MAESTROS - ERP Multiempresa (CONECTADO A SUPABASE)
// ============================================================

console.log('📦 Módulo Maestros cargando...');

// ============================================================
// CONFIGURACIÓN DE MÓDULOS - BASADO EN TABLAS REALES
// ============================================================
const MODULE_CONFIG = {
    clientes: {
        title: 'Clientes',
        subtitle: 'Base comercial de clientes y prospectos',
        table: 'clientes',
        fields: [
            { key: 'codigo_cliente', label: 'Código / Cliente ', type: 'text' },
            { key: 'razon_social', label: 'Razón Social', type: 'text' },
            { key: 'numero_documento', label: 'RUC/DNI', type: 'text' },
            { key: 'nombre_comercial', label: 'Nombre Comercial', type: 'text' },
            { key: 'nombre_contacto', label: 'Contacto', type: 'text' },
            { key: 'telefono_contacto', label: 'Teléfono', type: 'text' },
            { key: 'email_contacto', label: 'Email', type: 'text' },
            { key: 'estado', label: 'Estado', type: 'text' } // 🔧 CAMBIO: antes era { key: 'activo', label: 'Estado', type: 'boolean' }
        ],
        displayFields: ['codigo_cliente', 'razon_social', 'numero_documento', 'nombre_comercial', 'nombre_contacto', 'telefono_contacto', 'email_contacto', 'estado'], // 🔧 CAMBIO: antes era 'activo'
        headers: ['Código / Clientes ', 'Razón Social', 'RUC/DNI', 'Nombre Comercial', 'Contacto', 'Teléfono', 'Email', 'Estado'],
        idField: 'id',
        codeField: 'codigo_cliente',
        apiBase: '/maestros/api',
        dataField: 'created_at'
    },
    proveedores: {
        title: 'Proveedores',
        subtitle: 'Base de proveedores y servicios',
        table: 'proveedores',
        fields: [
            { key: 'codigo_proveedor', label: 'Código / Proveedores ', type: 'text' },
            { key: 'razon_social', label: 'Razón Social', type: 'text' },
            { key: 'ruc', label: 'RUC', type: 'text' },
            { key: 'razon_comercial', label: 'Razón Comercial', type: 'text' },
            { key: 'contacto', label: 'Contacto', type: 'text' },
            { key: 'telefono', label: 'Teléfono', type: 'text' },
            { key: 'email', label: 'Email', type: 'text' },
            { key: 'estado', label: 'Estado', type: 'text' } // 🔧 CAMBIO: antes era { key: 'activo', label: 'Estado', type: 'boolean' }
        ],
        displayFields: ['codigo_proveedor', 'razon_social', 'ruc', 'razon_comercial', 'contacto', 'telefono', 'email', 'estado'], // 🔧 CAMBIO: antes era 'activo'
        headers: ['Código / Proveedores ', 'Razón Social', 'RUC', 'Razón Comercial', 'Contacto', 'Teléfono', 'Email', 'Estado'],
        idField: 'id',
        codeField: 'codigo_proveedor',
        apiBase: '/maestros/api',
        dataField: 'fecha_creacion'
    },
    almacenes: {
        title: 'Almacenes',
        subtitle: 'Gestión de almacenes y ubicaciones',
        table: 'almacenes',
        fields: [
            { key: 'codigo', label: 'Código', type: 'text' },
            { key: 'nombre', label: 'Nombre', type: 'text' },
            { key: 'tipo', label: 'Tipo', type: 'text' },
            { key: 'responsable', label: 'Responsable', type: 'text' },
            { key: 'telefono', label: 'Teléfono', type: 'text' },
            { key: 'direccion', label: 'Dirección', type: 'text' },
            { key: 'activo', label: 'Estado', type: 'boolean' }
        ],
        displayFields: ['codigo', 'nombre', 'tipo', 'responsable', 'telefono', 'activo'],
        headers: ['Código', 'Nombre', 'Tipo', 'Responsable', 'Teléfono', 'Estado'],
        idField: 'id',
        codeField: 'codigo',
        apiBase: '/maestros/api',
        dataField: 'created_at'
    },
    categorias: {
        title: 'Categorías',
        subtitle: 'Clasificación de productos',
        table: 'categorias',
        fields: [
            { key: 'codigo', label: 'Código', type: 'text' },
            { key: 'nombre', label: 'Nombre', type: 'text' },
            { key: 'tipo', label: 'Categoría Principal', type: 'text' },
            { key: 'activo', label: 'Estado', type: 'boolean' }
        ],
        displayFields: ['codigo', 'nombre', 'tipo', 'activo'],
        headers: ['Código', 'Nombre', 'Categoría Principal', 'Estado'],
        idField: 'id',
        codeField: 'codigo',
        apiBase: '/maestros/api',
        dataField: 'created_at'
    },
    marcas: {
        title: 'Marcas',
        subtitle: 'Gestión de marcas y fabricantes',
        table: 'marcas',
        fields: [
            { key: 'codigo', label: 'Código', type: 'text' },
            { key: 'nombre', label: 'Marca', type: 'text' },
            { key: 'tipo', label: 'Tipo', type: 'text' },
            { key: 'activo', label: 'Estado', type: 'boolean' }
        ],
        displayFields: ['codigo', 'nombre', 'tipo', 'activo'],
        headers: ['Código', 'Marca', 'Tipo', 'Estado'],
        idField: 'id',
        codeField: 'codigo',
        apiBase: '/maestros/api',
        dataField: 'created_at'
    },
    um: {
        title: 'Unidades de Medida',
        subtitle: 'Define cómo compras, vendes e inventarias los productos',
        table: 'um',
        fields: [
            { key: 'codigo', label: 'Código', type: 'text' },
            { key: 'nombre', label: 'Unidad', type: 'text' },
            { key: 'abreviatura', label: 'Abreviatura', type: 'text' },
            { key: 'tipo', label: 'Tipo', type: 'text' },
            { key: 'decimales', label: 'Permite decimales', type: 'boolean' },
            { key: 'ambito', label: 'Ámbito', type: 'text' },
            { key: 'uso', label: 'Uso', type: 'number' },
            { key: 'activo', label: 'Estado', type: 'boolean' }
        ],
        displayFields: ['codigo', 'nombre', 'abreviatura', 'tipo', 'decimales', 'ambito', 'uso', 'activo'],
        headers: ['Código', 'Unidad', 'Abreviatura', 'Tipo', 'Decimales', 'Ámbito', 'Uso', 'Estado'],
        idField: 'id',
        codeField: 'codigo',
        apiBase: '/maestros/api',
        dataField: 'created_at'
    }
};

// ============================================================
// VARIABLES GLOBALES
// ============================================================
const MAESTROS = Object.keys(MODULE_CONFIG);
const DS = {};
const sheetMode = {};
let currentModule = 'clientes';
let clientEditId = null;
let ultimoClienteCreadoId = null;

let contactCtr = 0;
let pointCtr = 0;
let provEditId = null;
let almEditId = null;
let catEditId = null;
let marcaEditId = null;
let umEditId = null;



// ============================================================
// BADGE "NUEVO" CON EXPIRACIÓN DE 24 HORAS
// ============================================================

// ============================================================
// BADGE "NUEVO" CON EXPIRACIÓN DE 24 HORAS (CORREGIDO)
// ============================================================

const NUEVO_BADGE_DURATION_MS = 24 * 60 * 60 * 1000; // 24 horas

function esRegistroNuevo(fecha) {
    if (!fecha) return false;
    try {
        const f = typeof fecha === 'string' ? new Date(fecha) : new Date(fecha);
        if (isNaN(f.getTime())) return false;
        
        const ahora = new Date();
        const diff = f.getTime() - ahora.getTime(); // Diferencia en milisegundos
        
        // Si la fecha es futura (diff > 0), considerarla como nueva
        // Si la fecha es pasada (diff < 0), verificar que sea menor a 24 horas
        if (diff > 0) {
            // Fecha futura - considerarla nueva
            return true;
        } else {
            // Fecha pasada - verificar que sea menor a 24 horas
            return Math.abs(diff) < NUEVO_BADGE_DURATION_MS;
        }
    } catch (e) {
        console.warn('⚠️ Error al procesar fecha:', e);
        return false;
    }
}


// ============================================================
// BADGE "NUEVO" - VERSIÓN ULTRA SIMPLE Y DIRECTA
// ============================================================

function badgeNuevo(row, fechaField) {
    // 1. Intentar obtener la fecha
    let fecha = null;
    
    if (fechaField && row[fechaField]) {
        fecha = row[fechaField];
    } else {
        // Buscar automáticamente
        const campos = ['fecha_creacion', 'created_at', 'fechaCreacion', 'fecha_registro'];
        for (const campo of campos) {
            if (row[campo]) {
                fecha = row[campo];
                break;
            }
        }
    }
    
    // Si no hay fecha, NO mostrar badge
    if (!fecha) return '';
    
    try {
        const f = new Date(fecha);
        if (isNaN(f.getTime())) return '';
        
        const ahora = new Date();
        const diffMs = Math.abs(f.getTime() - ahora.getTime());
        const diffHoras = diffMs / (1000 * 60 * 60);
        
        // Mostrar badge si la diferencia es menor a 24 horas
        if (diffHoras <= 24) {
            return ' <span style="display:inline-block;background:#F7FEE7;color:#3F6212;border:1px solid #A3E635;border-radius:20px;padding:1px 9px;font-size:10px;font-weight:800;margin-left:6px;vertical-align:middle;">Nuevo</span>';
        }
        return '';
    } catch (e) {
        return '';
    }
}


// ============================================================
// FUNCIONES API
// ============================================================

function getApiBase(modulo) {
    const config = MODULE_CONFIG[modulo];
    return config?.apiBase || '/maestros/api';
}

async function fetchAPI(endpoint, options = {}) {
    console.log(`🌐 Fetching: ${endpoint}`);
    try {
        const response = await fetch(endpoint, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        });
        
        console.log(`📡 Status: ${response.status}`);
        
        if (!response.ok) {
            let errorMsg = `Error ${response.status}`;
            try {
                const errorData = await response.json();
                console.error('❌ Detalle error:', errorData);
                errorMsg = errorData.error || errorData.message || errorMsg;
            } catch (e) {
                errorMsg = `HTTP ${response.status}: ${response.statusText}`;
            }
            throw new Error(errorMsg);
        }
        
        const data = await response.json();
        console.log(`✅ Datos recibidos:`, data);
        return data;
    } catch (error) {
        console.error(`❌ Error en fetchAPI:`, error);
        throw error;
    }
}

async function fetchData(modulo) {
    try {
        const apiBase = getApiBase(modulo);
        const data = await fetchAPI(`${apiBase}/${modulo}/listar`);
        if (data.success) {
            return data.data || [];
        }
        console.error(`❌ Error cargando ${modulo}:`, data.error);
        return [];
    } catch (error) {
        console.error(`❌ Error en fetchData (${modulo}):`, error);
        showToast(`Error al cargar ${modulo}: ${error.message}`, 'error');
        return [];
    }
}

async function saveData(modulo, data) {
    try {
        const apiBase = getApiBase(modulo);
        const endpoint = `${apiBase}/${modulo}/guardar`;
        const method = 'POST';
        
        console.log(`💾 Guardando ${modulo}:`, { endpoint, method, data });
        
        const result = await fetchAPI(endpoint, {
            method: method,
            body: JSON.stringify(data)
        });
        
        if (result.success) {
            showToast(result.message || 'Datos guardados correctamente', 'success');
            await loadModuleData(modulo, true);
            renderModule(modulo);
        } else {
            showToast(result.error || 'Error al guardar', 'error');
        }
        return result;
    } catch (error) {
        console.error(`❌ Error guardando ${modulo}:`, error);
        showToast(`Error al guardar: ${error.message}`, 'error');
        return { success: false, error: error.message };
    }
}

async function toggleRecord(modulo, id) {
    try {
        const apiBase = getApiBase(modulo);
        const result = await fetchAPI(`${apiBase}/${modulo}/${id}/toggle`, {
            method: 'PUT'
        });
        return result;
    } catch (error) {
        console.error(`❌ Error togglando ${modulo}:`, error);
        showToast(`Error al cambiar estado: ${error.message}`, 'error');
        return { success: false, error: error.message };
    }
}

// ============================================================
// TOAST NOTIFICATIONS
// ============================================================
function showToast(message, type = 'info') {
    const oldToasts = document.querySelectorAll('.toast-custom');
    oldToasts.forEach(t => t.remove());
    
    const toast = document.createElement('div');
    toast.className = `toast-custom toast-${type}`;
    
    const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
    const colors = {
        success: '#10B981',
        error: '#EF4444',
        warning: '#F59E0B',
        info: '#3B82F6'
    };
    
    toast.innerHTML = `
        <div style="display:flex;align-items:center;gap:8px;">
            <span>${icons[type] || 'ℹ️'}</span>
            <span>${message}</span>
        </div>
    `;
    
    toast.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        padding: 12px 20px;
        border-radius: 8px;
        color: white;
        font-weight: 500;
        z-index: 99999;
        animation: slideIn 0.3s ease-out;
        max-width: 450px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.25);
        background: ${colors[type] || colors.info};
        font-size: 14px;
    `;
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(20px)';
        toast.style.transition = 'all 0.3s ease-out';
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

// ============================================================
// CARGAR DATOS CON CACHE
// ============================================================
const dataCache = {};

async function loadModuleData(modulo, force = false) {
    if (!force && dataCache[modulo] && dataCache[modulo].length > 0) {
        DS[modulo] = dataCache[modulo];
        console.log(`📦 Usando cache de ${modulo}: ${DS[modulo].length} registros`);
        return DS[modulo];
    }
    
    console.log(`🔄 Cargando datos de ${modulo}...`);
    DS[modulo] = await fetchData(modulo);
    dataCache[modulo] = DS[modulo];
    console.log(`✅ ${DS[modulo].length} registros cargados de ${modulo}`);
    return DS[modulo];
}

// ============================================================
// UTILIDADES
// ============================================================
function esc(v) {
    return String(v ?? '').replace(/[&<>"']/g, m => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;',
        '"': '&quot;', "'": '&#039;'
    }[m]));
}

function sd(v) {
    return (v === undefined || v === null || String(v).trim() === '') ? '-' : esc(v);
}

function getEstado(valor) {
    if (typeof valor === 'boolean') {
        return valor ? 'Activo' : 'Inactivo';
    }
    if (typeof valor === 'string') {
        const v = valor.toLowerCase();
        if (v === 'true' || v === 'activo' || v === '1') return 'Activo';
        if (v === 'false' || v === 'inactivo' || v === '0') return 'Inactivo';
        return valor.charAt(0).toUpperCase() + valor.slice(1).toLowerCase();
    }
    return 'Inactivo';
}

function bEstado(valor) {
    const estado = getEstado(valor);
    const badges = {
        'Activo': '<span class="badge b-ok">● Activo</span>',
        'Observado': '<span class="badge b-warn">● Observado</span>',
        'Bloqueado': '<span class="badge b-block">● Bloqueado</span>'
        //'Inactivo': '<span class="badge b-gray">● Inactivo</span>'
    };
    return badges[estado] || `<span class="badge b-gray">${estado}</span>`;
}

function bAmbito(v) {
    const ambitos = {
        'KCF': '<span class="badge b-kcf">KCF</span>',
        'AGD': '<span class="badge b-agd">AGD</span>',
        'COMPARTIDO': '<span class="badge b-shared">Compartido</span>'
    };
    return ambitos[v] || '<span class="badge b-shared">Compartido</span>';
}

function getCode(r, modulo) {
    const config = MODULE_CONFIG[modulo];
    return r[config.codeField] || `${modulo.toUpperCase()}-${String(r.id || 0).padStart(6, '0')}`;
}

function empresa() {
    return document.getElementById('empresaActiva')?.value || 'KCF';
}

// ============================================================
// FILTRADO
// ============================================================
function filtered(m) {
    const q = (document.getElementById(`search_${m}`)?.value || '').toLowerCase().trim();
    const st = document.getElementById(`estado_${m}`)?.value || 'TODOS';
    const config = MODULE_CONFIG[m];
    const usaEstadoTexto = config.fields.some(f => f.key === 'estado');

    return (DS[m] || []).filter(r => {
        const okQ = !q || JSON.stringify(r).toLowerCase().includes(q);

        let okSt = true;
        if (st !== 'TODOS') {
            const valorEstado = usaEstadoTexto ? r.estado : r.activo;
            const estado = getEstado(valorEstado);
            okSt = estado === st;
        }

        return okQ && okSt;
    });
}

// ============================================================
// FILTRADO MEJORADO - SIN RECONSTRUIR TODO
// ============================================================

function setupFilters(m) {
    // Filtro de estado (recarga la tabla)
    const estadoFilter = document.getElementById(`estado_${m}`);
    if (estadoFilter) {
        estadoFilter.removeEventListener('change', function() { renderModule(m); });
        estadoFilter.addEventListener('change', function() {
            renderModule(m);
        });
    }
    
    // Filtro de búsqueda (SOLO FILTRA, NO RECARGA)
    const searchInput = document.getElementById(`search_${m}`);
    if (searchInput) {
        const newInput = searchInput.cloneNode(true);
        searchInput.parentNode.replaceChild(newInput, searchInput);
        
        newInput.addEventListener('input', function() {
            filterTable(m);
        });
    }
}

function filterTable(m) {
    const input = document.getElementById(`search_${m}`);
    if (!input) return;
    
    const searchTerm = input.value.toLowerCase().trim();
    const container = document.getElementById(m);
    if (!container) return;
    
    const table = container.querySelector('.master-table');
    if (!table) return;
    
    const rows = table.querySelectorAll('tbody tr');
    let visibleCount = 0;
    
    rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        if (searchTerm === '' || text.includes(searchTerm)) {
            row.style.display = '';
            visibleCount++;
        } else {
            row.style.display = 'none';
        }
    });
    
    // Actualizar contador
    const subtitle = container.querySelector('.master-subtitle');
    if (subtitle) {
        const total = DS[m]?.length || 0;
        const config = MODULE_CONFIG[m];
        subtitle.textContent = `${config?.subtitle || ''} (${visibleCount} registros)`;
    }
}


// ============================================================
// RENDER FUNCTIONS
// ============================================================

function renderStatusBoard(m) {
    const data = DS[m] || [];
    const config = MODULE_CONFIG[m];
    const usaEstadoTexto = config.fields.some(f => f.key === 'estado');

    if (usaEstadoTexto) {
        // Clientes y Proveedores: Activo / Observado / Bloqueado / Total
        const activos = data.filter(r => getEstado(r.estado) === 'Activo').length;
        const observados = data.filter(r => getEstado(r.estado) === 'Observado').length;
        const bloqueados = data.filter(r => getEstado(r.estado) === 'Bloqueado').length;

        return `
            <div class="master-status-board">
                <div class="master-status-card active">
                    <span class="master-status-dot msd-active">●</span>
                    <b>${activos}</b>
                    <small>Act</small>
                </div>
                <div class="master-status-card observed">
                    <span class="master-status-dot msd-observed">●</span>
                    <b>${observados}</b>
                    <small>Obs</small>
                </div>
                <div class="master-status-card blocked">
                    <span class="master-status-dot msd-blocked">●</span>
                    <b>${bloqueados}</b>
                    <small>Bloq</small>
                </div>
                <div class="master-status-card total">
                    <span class="master-status-dot msd-total">●</span>
                    <b>${data.length}</b>
                    <small>Tot</small>
                </div>
            </div>
        `;
    }

    // Almacenes, Categorías, Marcas, UM: solo Activo / Total (sin cambios)
    const activos = data.filter(r => getEstado(r.activo) === 'Activo').length;

    return `
        <div class="master-status-board">
            <div class="master-status-card active">
                <span class="master-status-dot msd-active">●</span>
                <b>${activos}</b>
                <small>Act</small>
            </div>
            <div class="master-status-card total">
                <span class="master-status-dot msd-total">●</span>
                <b>${data.length}</b>
                <small>Tot</small>
            </div>
        </div>
    `;
}



// ============================================================
// RENDER TABLE - CON BOTÓN ELIMINAR (TACHO DE BASURA)
// ============================================================

function renderTable(m, list) {
    if (!list || !list.length) {
        return `<div class="empty-state">
            <div style="font-size: 48px; margin-bottom: 10px;">📭</div>
            <p style="color: #64748B; font-weight: 500;">No se encontraron registros</p>
            <p style="color: #94A3B8; font-size: 14px;">Prueba con otros filtros o crea un nuevo registro</p>
        </div>`;
    }
    
    const config = MODULE_CONFIG[m];
    const mode = sheetMode[m] || 'principal';
    
    // ✅ Vista completa para clientes
    if (mode === 'completa' && m === 'clientes') {
        if (typeof renderClientesCompleta === 'function') {
            return renderClientesCompleta(list);
        }
    }
    
    // ✅ Vista completa para proveedores
    if (mode === 'completa' && m === 'proveedores') {
        if (typeof renderProveedoresCompleta === 'function') {
            return renderProveedoresCompleta(list);
        }
    }
    
    // Modo principal (vista normal)
    const headers = config.headers;
    const displayFields = config.displayFields;
    
    let headersHtml = `<th style="width:50px;">Item</th><th style="width:100px;">Ámbito</th>`;
    headers.forEach(h => { headersHtml += `<th>${h}</th>`; });
    headersHtml += `<th style="width:160px; min-width:160px; max-width; 160px; white-space:nowrap">Acciones</th>`;
    
   const rows = list.map((r, i) => {
       let cells = `<td><b>${i + 1}</b>${badgeNuevo(r, config.dateField || 'created_at')}</td><td>${bAmbito(r.ambito || 'COMPARTIDO')}</td>`;
        
        displayFields.forEach(f => {
            if (f === 'activo' || f === 'estado') {
                cells += `<td>${bEstado(r[f])}</td>`;
            } else if (f === 'decimales') {
                cells += `<td>${r[f] ? '✅ Sí' : '❌ No'}</td>`;
            } else if (f === 'email' || f === 'email_contacto') {
                const email = r[f];
                cells += `<td>${email ? `<a href="mailto:${esc(email)}" style="color:#3B82F6;text-decoration:none;">${esc(email)}</a>` : '-'}</td>`;
            } else if (f === 'uso') {
                cells += `<td style="text-align:center;">${r[f] || 0}</td>`;
            } else {
                // Ya no lleva badge aquí, es normal para todos los campos incluido el código
                cells += `<td class="left">${sd(r[f])}</td>`;
            }
        });
        
        const isActive = getEstado(r.activo) === 'Activo';
        const estadoDisplay = isActive ? 'Desactivar' : 'Activar';
        const estadoClass = isActive ? 'action-delete' : 'action-activate';
        
        cells += `
            <td style="width=120px;">
                <div style="display:flex;gap:5px;justify-content:center;flex-wrap:wrap;">
                    <button class="action-btn action-view" data-view="${m}|${r.id}" title="Ver detalle">👁️</button>
                    <button class="action-btn action-edit" data-edit="${m}|${r.id}" title="Editar">✏️</button>
                    <button class="action-btn ${estadoClass}" data-delete="${m}|${r.id}" title="${estadoDisplay}" style="color:#DC2626;font-size:14px;">🗑️</button>
                </div>
            </td>
        `;
        
        return `<tr>${cells}</tr>`;
    }).join('');
    
    return `<div class="table-scroll" style="min-width: 1350px;">
        <table class="master-table" style= "min-width: 1350px;">
            <thead><tr>${headersHtml}</tr></thead>
            <tbody>${rows}</tbody>
        </table>
    </div>`;
}

function getEstadoFilterOptions(m) {
    const config = MODULE_CONFIG[m];
    const usaEstadoTexto = config.fields.some(f => f.key === 'estado');

    if (usaEstadoTexto) {
        return `
            <option value="TODOS">Todos los estados</option>
            <option value="Activo">✅ Activo</option>
            <option value="Observado">⚠️ Observado</option>
            <option value="Bloqueado">⛔ Bloqueado</option>
        `;
    }

    return `
        <option value="TODOS">Todos los estados</option>
        <option value="Activo">✅ Activo</option>
    `;
}


function renderModule(m) {
    const config = MODULE_CONFIG[m];
    if (!config) {
        const container = document.getElementById(m);
        if (container) container.innerHTML = '<div class="panel"><p>Módulo no configurado</p></div>';
        return;
    }
    
    const list = filtered(m);
    const container = document.getElementById(m);
    if (!container) {
        console.warn(`⚠️ Contenedor para ${m} no encontrado`);
        return;
    }
    
    // Obtener modo actual
    const mode = sheetMode[m] || 'principal';
    const modeLabel = mode === 'principal' ? 'Principal' : 'Completa';
    
    container.innerHTML = `
        ${renderStatusBoard(m)}
        <div class="panel">
            <div class="clean-header">
                <div class="master-title-wrap">
                    <div class="master-title">${config.title}</div>
                    <div class="master-subtitle">${config.subtitle} (${list.length} registros) - Vista: <span style="color:var(--empresa);font-weight:900;">${modeLabel}</span></div>
                </div>
                <div class="search-box">
                    <input type="text" id="search_${m}" placeholder="Buscar..." class="search-input">
                </div>
                <div class="clean-actions">
                    <select id="estado_${m}" class="status-filter">
                        ${getEstadoFilterOptions(m)}
                    </select>
                    <button class="btn btn-secondary" data-bulk="${m}">📥 Importar</button>
                    <button class="btn btn-primary btn-create" data-new="${m}">+ Crear Nuevo ${config.title.slice(0, -1)}</button>
                </div>
            </div>
            ${renderTable(m, list)}
            <div class="bottom-sheet">
                <div class="bottom-left">
                    <span class="bottom-label">📊 Vista de datos</span>
                    <div class="page-group">
                        <button class="page-btn ${mode === 'principal' ? 'active' : ''}" data-sheet="${m}|principal">
                            <span class="page-num">1</span>Principal
                        </button>
                        <button class="page-btn ${mode === 'completa' ? 'active' : ''}" data-sheet="${m}|completa">
                            <span class="page-num">2</span>Completa
                        </button>
                    </div>
                </div>
                <div class="bottom-help">
                    ${mode === 'principal' 
                        ? '💡 Datos clave para trabajar rápido.' 
                        : '📋 Todos los campos registrados (contactos y puntos de entrega).'}
                </div>
            </div>
        </div>
    `;
    
    setupFilters(m);
    
    document.querySelectorAll(`[data-sheet^="${m}|"]`).forEach(btn => {
        btn.addEventListener('click', function(e) {
            const [mod, mode] = this.dataset.sheet.split('|');
            sheetMode[mod] = mode;
            renderModule(mod);
        });
    });
}




// ============================================================
// HANDLERS
// ============================================================

async function toggleRecordHandler(modulo, id) {
    const r = DS[modulo]?.find(x => x.id === id);
    if (!r) {
        showToast('Registro no encontrado', 'error');
        return;
    }
    
    const currentState = getEstado(r.activo);
    const newState = currentState === 'Activo' ? false : true;
    const newStateLabel = newState ? 'Activo' : 'Inactivo';
    
    showToast(`⏳ Cambiando estado...`, 'info');
    
    try {
        const result = await toggleRecord(modulo, id);
        
        if (result.success) {
            r.activo = newState;
            showToast(`✅ Registro ${newStateLabel.toLowerCase()} correctamente`, 'success');
            await loadModuleData(modulo, true);
            renderModule(modulo);
        } else {
            showToast(`❌ Error: ${result.error || 'No se pudo actualizar'}`, 'error');
        }
    } catch (error) {
        showToast(`❌ Error: ${error.message}`, 'error');
    }
}

// ============================================================
// OPEN SCREEN
// ============================================================

async function openScreen(screen) {
    console.log('🔄 Abriendo pantalla:', screen);
    currentModule = screen;

    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    const section = document.getElementById(screen);
    if (section) {
        section.classList.add('active');
    } else {
        console.warn(`⚠️ Sección ${screen} no encontrada`);
        const mainPanel = document.querySelector('.main-inner');
        if (mainPanel) {
            const newSection = document.createElement('section');
            newSection.id = screen;
            newSection.className = 'section active';
            const dashboard = document.getElementById('dashboard');
            if (dashboard && dashboard.parentNode) {
                dashboard.parentNode.insertBefore(newSection, dashboard.nextSibling);
            } else {
                mainPanel.appendChild(newSection);
            }
            console.log(`✅ Sección ${screen} creada`);
        }
    }

    document.querySelectorAll('.tab-btn').forEach(t => t.classList.remove('active'));
    document.querySelectorAll(`.tab-btn[data-tab="${screen}"]`).forEach(t => t.classList.add('active'));

    updateSidebar(screen);

    if (MODULE_CONFIG[screen]) {
        await loadModuleData(screen);
        renderModule(screen);
    } else {
        const el = document.getElementById(screen);
        if (el) {
            el.innerHTML = `<div class="panel" style="padding:40px;text-align:center;color:#64748B;">
                <div style="font-size:48px;margin-bottom:10px;">🚧</div>
                <h3>${screen}</h3>
                <p>Módulo en construcción</p>
            </div>`;
        }
    }
}

// ============================================================
// ACTUALIZAR SIDEBAR
// ============================================================
function updateSidebar(module) {
    console.log(`🔄 Actualizando sidebar para módulo: ${module}`);
    
    const moduleMap = {
        'clientes': 'Clientes',
        'proveedores': 'Proveedores',
        'almacenes': 'Almacenes',
        'categorias': 'Categorías',
        'marcas': 'Marcas',
        'um': 'Unidades de medida'
    };
    
    document.querySelectorAll('.child-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    document.querySelectorAll('.menu-header').forEach(header => {
        header.classList.remove('active');
    });
    
    let sidebarBtn = document.querySelector(`.child-btn[data-screen="${module}"]`);
    
    if (!sidebarBtn) {
        sidebarBtn = document.querySelector(`.child-btn[href*="tab=${module}"]`);
    }
    
    if (!sidebarBtn) {
        const textToFind = moduleMap[module] || module;
        document.querySelectorAll('.child-btn').forEach(btn => {
            const btnText = btn.textContent.trim();
            if (btnText === textToFind || btnText.includes(textToFind)) {
                sidebarBtn = btn;
            }
        });
    }
    
    if (!sidebarBtn) {
        document.querySelectorAll('.child-btn').forEach(btn => {
            const href = btn.getAttribute('href') || '';
            if (href.includes(module)) {
                sidebarBtn = btn;
            }
        });
    }
    
    if (sidebarBtn) {
        sidebarBtn.classList.add('active');
        console.log(`✅ Sidebar activado: ${sidebarBtn.textContent.trim()}`);
        
        const parentGroup = sidebarBtn.closest('.menu-group');
        if (parentGroup) {
            parentGroup.classList.add('open');
            const header = parentGroup.querySelector('.menu-header');
            if (header) {
                header.classList.add('active');
            }
        }
    } else {
        console.warn(`⚠️ No se encontró botón en sidebar para el módulo: ${module}`);
    }
}

// ============================================================
// 🔥 MODAL CLIENTE - FUNCIONES COMPLETAS
// ============================================================

const STATE_CFG = {
  'Activo':   {cls:'s-green',  dot:'#84CC16',pill:'pill-green',  txt:'Cliente habilitado para cotizar, vender y atender normalmente.'},
  'Observado':{cls:'s-yellow', dot:'#F59E0B',pill:'pill-yellow', txt:'Revisar condiciones antes de atender o despachar.'},
  'Bloqueado':{cls:'s-red',    dot:'#FB7185',pill:'pill-red',    txt:'No atender ni vender hasta que Gerencia lo libere.'},
  'Inactivo': {cls:'s-gray',   dot:'#94A3B8',pill:'pill-gray',   txt:'Registro desactivado. No usar en operaciones nuevas.'}
};

function contactBox(d = {}) {
  contactCtr++;
  return `<div class="cm-box" data-cid="${contactCtr}">
    <button class="cm-box-del" data-rc="${contactCtr}">🗑</button>
    <div class="cm-grid cm-grid-contact" style="margin-top:4px">
      <div class="cm-field"><label>NOMBRE *</label><input data-cf="nombre" value="${esc(d.nombre||'')}"></div>
      <div class="cm-field"><label>CARGO</label><input data-cf="cargo" value="${esc(d.cargo||'')}"></div>
      <div class="cm-field"><label>TELÉFONO</label><input data-cf="telefono" value="${esc(d.telefono||'')}"></div>
      <div class="cm-field"><label>EMAIL</label><input data-cf="email" value="${esc(d.email||'')}"></div>
      <div class="cm-field"><label>&nbsp;</label><label class="cm-checkbox"><input type="checkbox" data-cf="principal" ${d.principal?'checked':''}><span>Contacto principal</span></label></div>
    </div>
  </div>`;
}

function pointBox(d = {}) {
  pointCtr++;
  return `<div class="cm-box" data-pid="${pointCtr}">
    <button class="cm-box-del" data-rp="${pointCtr}">🗑</button>
    <div class="cm-grid cm-grid-delivery" style="margin-top:4px">
      <div class="cm-field"><label>PUNTO DE ENTREGA *</label><input data-pf="punto" value="${esc(d.punto||'')}"></div>
      <div class="cm-field"><label>DIRECCIÓN DE ENTREGA</label><input data-pf="direccion" value="${esc(d.direccion||'')}"></div>
      <div class="cm-field"><label>LINK GOOGLE MAPS</label><input data-pf="googleMaps" value="${esc(d.googleMaps||'')}"></div>
      <div class="cm-field"><label>HORARIO / REFERENCIA</label><input data-pf="horario" value="${esc(d.horario||'')}"></div>
      <div class="cm-field"><label>CONTACTO ENTREGA</label><input data-pf="contacto" value="${esc(d.contacto||'')}"></div>
      <div class="cm-field"><label>TELÉFONO PUNTO</label><input data-pf="telefono" value="${esc(d.telefono||'')}"></div>
      <div class="cm-field"><label>&nbsp;</label><label class="cm-checkbox"><input type="checkbox" data-pf="principal" ${d.principal?'checked':''}><span>Punto principal</span></label></div>
      <div class="cm-field full-row"><label>INSTRUCCIONES</label><input data-pf="instrucciones" value="${esc(d.instrucciones||'')}"></div>
    </div>
  </div>`;
}

function syncClientState() {
  const v = document.getElementById('cli_estado')?.value || 'Activo';
  const cfg = STATE_CFG[v] || STATE_CFG['Activo'];
  const box = document.getElementById('cliStateBox');
  if (box) { box.className = 'cm-state-box ' + cfg.cls; }
  const dot = document.getElementById('cliStateDot');
  if (dot) { dot.style.background = cfg.dot; }
  const txt = document.getElementById('cliStateText');
  if (txt) { txt.textContent = cfg.txt; }
  const pill = document.getElementById('cliStatePill');
  if (pill) { pill.className = 'cm-state-pill ' + cfg.pill; pill.textContent = v; }
}

function clearClientForm() {
  document.getElementById('cli_ambito').value = 'COMPARTIDO';
  document.getElementById('cli_tipoDoc').value = 'RUC';
  document.getElementById('cli_numero').value = '';
  document.getElementById('cli_nombre').value = '';
  document.getElementById('cli_nombreComercial').value = '';
  document.getElementById('cli_direccionFiscal').value = '';
  document.getElementById('cli_condicion').value = 'Contado';
  document.getElementById('cli_diasCredito').value = '0';
  document.getElementById('cli_limiteCredito').value = '';
  document.getElementById('cli_descuento').value = '';
  document.getElementById('cli_estado').value = 'Activo';
  document.getElementById('cli_obs').value = '';
  document.getElementById('cliContacts').innerHTML = contactBox({ principal: true });
  document.getElementById('cliPoints').innerHTML = pointBox({ principal: true });
  syncClientState();
}


function fillClientForm(data) {
    console.log('📝 Rellenando formulario con datos:', data);
    
    // Función segura para obtener valor
    const getVal = (field, defaultValue = '') => {
        return data[field] !== undefined && data[field] !== null ? data[field] : defaultValue;
    };
    
    // Mapeo de campos
    const campos = {
        'cli_ambito': getVal('ambito', 'COMPARTIDO'),
        'cli_tipoDoc': getVal('tipo_documento', 'RUC'),
        'cli_numero': getVal('numero_documento', ''),
        'cli_nombre': getVal('razon_social', ''),
        'cli_nombreComercial': getVal('nombre_comercial', getVal('razon_social', '')),
        'cli_direccionFiscal': getVal('direccion_fiscal', ''),
        'cli_condicion': getVal('condicion_pago', 'Contado'),
        'cli_diasCredito': getVal('dias_credito', '0'),
        'cli_limiteCredito': getVal('limite_credito', ''),
        'cli_descuento': getVal('descuento', ''),
        'cli_estado': getVal('estado', 'Activo'),
        'cli_obs': getVal('observaciones', getVal('obs', ''))
    };
    
    // Aplicar valores al formulario
    Object.keys(campos).forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.value = campos[id];
        }
    });
    
    // 🔥 CARGAR CONTACTOS - USANDO DATOS DE LA API
    const cc = document.getElementById('cliContacts');
    if (cc) {
        if (data.contactos && data.contactos.length > 0) {
            // Si la API devuelve contactos, usarlos
            cc.innerHTML = data.contactos.map(c => contactBox({
                nombre: c.nombre || '',
                cargo: c.cargo || '',
                telefono: c.telefono || '',
                email: c.email || '',
                principal: c.principal || false
            })).join('');
        } else {
            // Si no hay contactos, crear uno por defecto con datos del cliente
            cc.innerHTML = contactBox({
                nombre: data.nombre_contacto || 'Contacto Principal',
                cargo: data.cargo || '',
                telefono: data.telefono_contacto || '',
                email: data.email_contacto || '',
                principal: true
            });
        }
    }
    
    // 🔥 CARGAR PUNTOS DE ENTREGA - USANDO DATOS DE LA API
    const cp = document.getElementById('cliPoints');
    if (cp) {
        if (data.puntos_entrega && data.puntos_entrega.length > 0) {
            // Si la API devuelve puntos, usarlos
            cp.innerHTML = data.puntos_entrega.map(p => pointBox({
                punto: p.punto || '',
                direccion: p.direccion || '',
                googleMaps: p.googleMaps || '',
                horario: p.horario || '',
                contacto: p.contacto || '',
                telefono: p.telefono || '',
                instrucciones: p.instrucciones || '',
                principal: p.principal || false
            })).join('');
        } else {
            // Si no hay puntos, crear uno por defecto con la dirección fiscal
            cp.innerHTML = pointBox({
                punto: 'Principal',
                direccion: data.direccion_fiscal || '',
                googleMaps: '',
                horario: '',
                contacto: data.nombre_contacto || '',
                telefono: data.telefono_contacto || '',
                instrucciones: '',
                principal: true
            });
        }
    }
    
    syncClientState();
    console.log('✅ Formulario rellenado correctamente');
}



async function openClientModal(editId = null) {
  clientEditId = editId;
  contactCtr = 0;
  pointCtr = 0;

  document.getElementById('cmTitle').textContent = editId ? 'Editar cliente' : 'Crear cliente';
  document.getElementById('cmHint').textContent = editId ? `Editando ID ${editId}` : 'Modo: creación';

  if (editId) {
    // Mostrar el modal con un loading state, SIN datos viejos
    document.getElementById('cliContacts').innerHTML = '<div style="padding:12px;color:#94A3B8;">Cargando...</div>';
    document.getElementById('cliPoints').innerHTML = '<div style="padding:12px;color:#94A3B8;">Cargando...</div>';
    document.getElementById('clientModal').classList.add('show');
    document.querySelector('#clientModal .cm-body').scrollTop = 0;

    try {
      const r = await fetch(`/maestros/api/clientes/${editId}`);
      const data = await r.json();
      if (data.success) {
        fillClientForm(data.data);
      } else {
        showToast('Error al cargar datos del cliente', 'error');
      }
    } catch (err) {
      console.error('Error cargando cliente:', err);
      showToast('Error al cargar datos del cliente', 'error');
    }
  } else {
    clearClientForm();
    document.getElementById('clientModal').classList.add('show');
    document.querySelector('#clientModal .cm-body').scrollTop = 0;
  }
}

function closeClientModal() {
  document.getElementById('clientModal').classList.remove('show');
}

function getContacts() {
  return Array.from(document.querySelectorAll('[data-cid]')).map(b => ({
    nombre: b.querySelector('[data-cf="nombre"]')?.value.trim() || '',
    cargo: b.querySelector('[data-cf="cargo"]')?.value.trim() || '',
    telefono: b.querySelector('[data-cf="telefono"]')?.value.trim() || '',
    email: b.querySelector('[data-cf="email"]')?.value.trim() || '',
    principal: !!b.querySelector('[data-cf="principal"]')?.checked
  })).filter(c => c.nombre || c.telefono || c.email);
}

function getPoints() {
  const boxes = document.querySelectorAll('[data-pid]');
  const points = [];
  
  boxes.forEach(box => {
    const p = {
      punto: box.querySelector('[data-pf="punto"]')?.value.trim() || '',
      direccion: box.querySelector('[data-pf="direccion"]')?.value.trim() || '',
      googleMaps: box.querySelector('[data-pf="googleMaps"]')?.value.trim() || '',
      horario: box.querySelector('[data-pf="horario"]')?.value.trim() || '',
      contacto: box.querySelector('[data-pf="contacto"]')?.value.trim() || '',
      telefono: box.querySelector('[data-pf="telefono"]')?.value.trim() || '',
      instrucciones: box.querySelector('[data-pf="instrucciones"]')?.value.trim() || '',
      principal: !!box.querySelector('[data-pf="principal"]')?.checked
    };
    
    // Solo incluir si tiene AL MENOS UNO de los campos con valor
    const tieneDatos = 
      p.punto || 
      p.direccion || 
      p.googleMaps || 
      p.horario || 
      p.contacto || 
      p.telefono || 
      p.instrucciones;
    
    if (tieneDatos) {
      points.push(p);
    }
  });
  
  console.log('📦 Puntos de entrega a enviar:', points);
  return points;
}
// ============================================================
// CONSULTAR SUNAT
// ============================================================
async function consultarSunat() {
  const rucInput = document.getElementById('cli_numero');
  const ruc = rucInput?.value.replace(/\D/g, '').trim();
  
  if (!ruc) {
    showToast('⚠️ Ingresa un RUC para consultar.', 'warning');
    return;
  }
  if (ruc.length !== 11) {
    showToast('⚠️ El RUC debe tener 11 dígitos.', 'warning');
    return;
  }
  
  const btn = document.getElementById('btnSunat');
  const originalText = btn.textContent;
  btn.textContent = '⏳ Consultando...';
  btn.disabled = true;
  
  try {
    const response = await fetch(`/api/sunat/consulta?ruc=${ruc}`);
    const data = await response.json();
    
    if (data.success) {
      document.getElementById('cli_nombre').value = data.razon_social || '';
      document.getElementById('cli_nombreComercial').value = data.nombre_comercial || data.razon_social || '';
      document.getElementById('cli_direccionFiscal').value = data.direccion || '';
      
      if (data.estado) {
        const estadoMap = {
          'ACTIVO': 'Activo',
          'BAJA': 'Inactivo',
          'SUSPENDIDO': 'Observado',
          'BAJA DE OFICIO': 'Inactivo'
        };
        const nuevoEstado = estadoMap[data.estado.toUpperCase()] || data.estado;
        if (nuevoEstado) {
          document.getElementById('cli_estado').value = nuevoEstado;
          syncClientState();
        }
      }
      
      showToast('✅ Datos SUNAT cargados correctamente', 'success');
    } else {
      showToast('❌ ' + (data.error || 'Error al consultar SUNAT'), 'error');
    }
  } catch (error) {
    console.error('Error consultando SUNAT:', error);
    showToast('❌ Error al conectar con el servicio SUNAT', 'error');
  } finally {
    btn.textContent = originalText;
    btn.disabled = false;
  }
}

//=============================================================
// Dias de Credito (repuesta personalizada)
//=============================================================

//subfijo(opcional)
function personalizarDiasCredito(selectId, sufijo = '') {
    const valor = prompt('Ingrese el nuevo valor (solo números enteros):');
    if (valor === null) return; // el usuario le dio Cancelar

    const limpio = valor.trim();
    if (!/^\d+$/.test(limpio)) {
        showToast('⚠️ Solo se permiten números enteros.', 'warning');
        return;
    }

    const select = document.getElementById(selectId);
    if (!select) return;

    const yaExiste = Array.from(select.options).some(o => o.value === limpio);
    if (!yaExiste) {
        const opt = document.createElement('option');
        opt.value = limpio;
        opt.textContent = sufijo ? `${limpio} ${sufijo}` : limpio;
        select.appendChild(opt);
    }

    select.value = limpio;
    select.dispatchEvent(new Event('change')); // por si algo más escucha "change"
    showToast(`✅ Se agregó "${limpio}${sufijo ? ' ' + sufijo : ''}"`, 'success');
}

// ============================================================
// ALERTA DE CLIENTE CREADO
// ============================================================
function mostrarAlertaClienteCreado(info) {
    const existing = document.getElementById('alertaClienteCreado');
    if (existing) existing.remove();

    const alerta = document.createElement('div');
    alerta.id = 'alertaClienteCreado';
    alerta.style.cssText = `
        position: fixed;
        top: 30px;
        right: 30px;
        background: white;
        border-radius: 16px;
        padding: 20px 26px;
        box-shadow: 0 20px 60px rgba(0,0,0,0.2);
        z-index: 999999;
        max-width: 380px;
        border-left: 6px solid #10B981;
        display: flex;
        align-items: flex-start;
        gap: 14px;
    `;

    alerta.innerHTML = `
        <div style="font-size:32px;line-height:1;">🎉</div>
        <div style="flex:1;">
            <div style="font-weight:800;font-size:15px;color:#0f172a;margin-bottom:4px;">Cliente creado</div>
            <div style="color:#64748B;font-size:12.5px;margin-bottom:4px;">${info.razon_social || ''}</div>
            <div style="background:#f1f5f9;padding:4px 10px;border-radius:6px;display:inline-block;font-family:monospace;font-weight:700;font-size:12.5px;color:#0f172a;">
                ${info.codigo_cliente || 'ID: ' + info.id}
            </div>
        </div>
        <button onclick="this.parentElement.remove()" style="background:none;border:none;font-size:18px;cursor:pointer;color:#94a3b8;">✕</button>
    `;

    document.body.appendChild(alerta);
    setTimeout(() => { if (alerta.parentNode) alerta.remove(); }, 6000);
}
window.mostrarAlertaClienteCreado = mostrarAlertaClienteCreado;

async function saveClient() {
    const contacts = getContacts();
    const points = getPoints();
    const p = contacts.find(c => c.principal) || contacts[0] || {};

    const data = {
        tipo_documento: document.getElementById('cli_tipoDoc')?.value || 'RUC',
        numero_documento: document.getElementById('cli_numero')?.value?.trim() || '',
        razon_social: document.getElementById('cli_nombre')?.value?.trim() || '',
        nombre_comercial: document.getElementById('cli_nombreComercial')?.value?.trim() || '',
        direccion_fiscal: document.getElementById('cli_direccionFiscal')?.value?.trim() || '',
        contacto: p.nombre || '',
        telefono: p.telefono || '',
        email: p.email || '',
        condicion_pago: document.getElementById('cli_condicion')?.value || 'Contado',
        dias_credito: document.getElementById('cli_diasCredito')?.value || '0',
        limite_credito: document.getElementById('cli_limiteCredito')?.value?.trim() || '',
        descuento: document.getElementById('cli_descuento')?.value?.trim() || '',
        estado: document.getElementById('cli_estado')?.value || 'Activo',
        observaciones: document.getElementById('cli_obs')?.value?.trim() || '',
        contactos: contacts,
        puntos_entrega: points,
        ambito: document.getElementById('cli_ambito')?.value || 'COMPARTIDO'
    };

    if (!data.razon_social) {
        showToast('⚠️ La razón social es obligatoria', 'warning');
        return;
    }

    if (!data.numero_documento) {
        showToast('⚠️ El número de documento es obligatorio', 'warning');
        return;
    }

    // ✅ VERIFICAR DUPLICADO EN FRONTEND - EXCLUYENDO EL REGISTRO ACTUAL
    const ruc = data.numero_documento;
    if (ruc && ruc.length >= 8) {
        try {
            // Buscar si ya existe este RUC
            const checkResponse = await fetch(`/maestros/api/clientes/buscar?q=${ruc}`);
            const checkResult = await checkResponse.json();
            
            if (checkResult.success && checkResult.data && checkResult.data.length > 0) {
                // ✅ Si estamos editando (clientEditId existe), excluir el registro actual
                // Verificar si alguno tiene exactamente el mismo RUC PERO diferente ID
                const exists = checkResult.data.some(c => {
                    const mismoRuc = c.numero_documento === ruc || c.ruc === ruc;
                    
                    // Si estamos editando, permitir el mismo RUC solo si es el mismo registro
                    if (clientEditId) {
                        // Excluir el registro actual de la verificación
                        return mismoRuc && c.id !== clientEditId;
                    }
                    
                    // Si es creación nueva, cualquier coincidencia es duplicado
                    return mismoRuc;
                });
                
                if (exists) {
                    showToast('❌ Este RUC ya está registrado en nuestra base de datos. No se puede volver a cargar.', 'error');
                    return;
                }
            }
        } catch (err) {
            // Si falla la verificación, continuar (el backend capturará el error)
            console.warn('⚠️ No se pudo verificar duplicado en frontend:', err);
        }
    }

    try {
        const url = clientEditId
            ? `/maestros/api/clientes/${clientEditId}`
            : '/maestros/api/clientes/guardar';

        const method = clientEditId ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (result.success) {
            showToast(result.message || '✅ Cliente guardado correctamente', 'success');
            closeClientModal();
            await loadModuleData('clientes', true);
            renderModule('clientes');

            if (!clientEditId) {
                try {
                    mostrarAlertaClienteCreado({
                        id: result.data?.id,
                        ruc: data.numero_documento,
                        razon_social: data.razon_social,
                        nombre_comercial: data.nombre_comercial,
                        codigo_cliente: result.data?.codigo_cliente
                    });
                } catch (alertErr) {
                    console.error('⚠️ Error mostrando alerta de cliente creado:', alertErr);
                }
            }
        } else {
            // ✅ Mostrar el mensaje de error del backend (ya sea duplicado o cualquier otro)
            showToast('❌ ' + (result.error || 'Error al guardar'), 'error');
        }

    } catch (error) {
        console.error('Error al guardar cliente:', error);
        showToast('❌ Error de conexión al guardar el cliente', 'error');
    }
}

// ============================================================
// MODAL PROVEEDOR
// ============================================================
function openProveedorModal(editId = null) {
    provEditId = editId;
    if (editId) {
        fetch(`/maestros/api/proveedores/${editId}`)
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    fillProveedorForm(data.data);
                }
            })
            .catch(err => console.error('Error cargando proveedor:', err));
    } else {
        clearProveedorForm();
    }
    document.getElementById('provTitle').textContent = editId ? 'Editar proveedor' : 'Crear proveedor';
    document.getElementById('provHint').textContent = editId ? `Editando ID ${editId}` : 'Modo: creación';
    document.getElementById('proveedorModal').classList.add('show');
    syncProvState();
}

function clearProveedorForm() {
    document.getElementById('prov_ambito').value = 'COMPARTIDO';
    document.getElementById('prov_tipo').value = 'Recurrente';
    document.getElementById('prov_tipoDoc').value = 'RUC';
    document.getElementById('prov_ruc').value = '';
    document.getElementById('prov_razonSocial').value = '';
    document.getElementById('prov_direccionFiscal').value = '';
    document.getElementById('prov_contacto').value = '';
    document.getElementById('prov_cargo').value = '';
    document.getElementById('prov_telefono').value = '';
    document.getElementById('prov_email').value = '';
    document.getElementById('prov_banco').value = '';
    document.getElementById('prov_tipoCuenta').value = 'Cuenta corriente';
    document.getElementById('prov_cuenta').value = '';
    document.getElementById('prov_cci').value = '';
    document.getElementById('prov_condicion').value = 'Contado';
    document.getElementById('prov_lineaCredito').value = '';
    document.getElementById('prov_moneda').value = 'Soles';
    document.getElementById('prov_descuento').value = '';
    document.getElementById('prov_puntoRecojo').value = '';
    document.getElementById('prov_direccionRecojo').value = '';
    document.getElementById('prov_horarioRecojo').value = '';
    document.getElementById('prov_contactoRecojo').value = '';
    document.getElementById('prov_telefonoRecojo').value = '';
    document.getElementById('prov_instruccionesRecojo').value = '';
    document.getElementById('prov_estado').value = 'Activo';
    document.getElementById('prov_obs').value = '';
    syncProvState();
}

function fillProveedorForm(data) {
    document.getElementById('prov_ambito').value = data.ambito || 'COMPARTIDO';
    document.getElementById('prov_tipo').value = data.tipo || 'Recurrente';
    document.getElementById('prov_tipoDoc').value = data.tipoDoc || 'RUC';
    document.getElementById('prov_ruc').value = data.ruc || '';
    document.getElementById('prov_razonSocial').value = data.razon_social || '';
    document.getElementById('prov_direccionFiscal').value = data.direccion || '';
    document.getElementById('prov_contacto').value = data.contacto || '';
    document.getElementById('prov_cargo').value = data.cargo || '';
    document.getElementById('prov_telefono').value = data.telefono || '';
    document.getElementById('prov_email').value = data.email || '';
    document.getElementById('prov_banco').value = data.banco || '';
    document.getElementById('prov_tipoCuenta').value = data.tipoCuenta || 'Cuenta corriente';
    document.getElementById('prov_cuenta').value = data.cuenta || '';
    document.getElementById('prov_cci').value = data.cci || '';
    document.getElementById('prov_condicion').value = data.condicion_pago || 'Contado';
    document.getElementById('prov_lineaCredito').value = data.lineaCredito || '';
    document.getElementById('prov_moneda').value = data.moneda || 'Soles';
    document.getElementById('prov_descuento').value = data.descuento || '';
    document.getElementById('prov_puntoRecojo').value = data.puntoRecojo || '';
    document.getElementById('prov_direccionRecojo').value = data.direccionRecojo || '';
    document.getElementById('prov_horarioRecojo').value = data.horarioRecojo || '';
    document.getElementById('prov_contactoRecojo').value = data.contactoRecojo || '';
    document.getElementById('prov_telefonoRecojo').value = data.telefonoRecojo || '';
    document.getElementById('prov_instruccionesRecojo').value = data.instruccionesRecojo || '';
    document.getElementById('prov_estado').value = data.estado || 'Activo';
    document.getElementById('prov_obs').value = data.obs || '';
    syncProvState();
}

const PROV_STATE_CFG = {
    'Activo': {cls:'s-green', dot:'#84CC16', pill:'pill-green', txt:'Proveedor habilitado para operar normalmente.'},
    'Observado': {cls:'s-yellow', dot:'#F59E0B', pill:'pill-yellow', txt:'Revisar condiciones antes de operar.'},
    'Bloqueado': {cls:'s-red', dot:'#FB7185', pill:'pill-red', txt:'No usar hasta liberación de Gerencia.'},
    'Inactivo': {cls:'s-gray', dot:'#94A3B8', pill:'pill-gray', txt:'Desactivado para nuevos registros.'}
};

function syncProvState() {
    const v = document.getElementById('prov_estado')?.value || 'Activo';
    const cfg = PROV_STATE_CFG[v] || PROV_STATE_CFG['Activo'];
    const box = document.getElementById('provStateBox');
    if (box) box.className = 'cm-state-box ' + cfg.cls;
    const dot = document.getElementById('provStateDot');
    if (dot) dot.style.background = cfg.dot;
    const txt = document.getElementById('provStateText');
    if (txt) txt.textContent = cfg.txt;
    const pill = document.getElementById('provStatePill');
    if (pill) { pill.className = 'cm-state-pill ' + cfg.pill; pill.textContent = v; }
}

function closeProveedorModal() {
    document.getElementById('proveedorModal').classList.remove('show');
}

async function saveProveedor() {
    const data = {
        ambito: document.getElementById('prov_ambito').value,
        tipo: document.getElementById('prov_tipo').value,
        tipoDoc: document.getElementById('prov_tipoDoc').value,
        ruc: document.getElementById('prov_ruc').value.trim(),
        razon_social: document.getElementById('prov_razonSocial').value.trim(),
        direccion: document.getElementById('prov_direccionFiscal').value.trim(),
        contacto: document.getElementById('prov_contacto').value.trim(),
        cargo: document.getElementById('prov_cargo').value.trim(),
        telefono: document.getElementById('prov_telefono').value.trim(),
        email: document.getElementById('prov_email').value.trim(),
        banco: document.getElementById('prov_banco').value,
        tipoCuenta: document.getElementById('prov_tipoCuenta').value,
        cuenta: document.getElementById('prov_cuenta').value.trim(),
        cci: document.getElementById('prov_cci').value.trim(),
        condicion_pago: document.getElementById('prov_condicion').value,
        lineaCredito: document.getElementById('prov_lineaCredito').value.trim(),
        moneda: document.getElementById('prov_moneda').value,
        descuento: document.getElementById('prov_descuento').value.trim(),
        puntoRecojo: document.getElementById('prov_puntoRecojo').value.trim(),
        direccionRecojo: document.getElementById('prov_direccionRecojo').value.trim(),
        horarioRecojo: document.getElementById('prov_horarioRecojo').value.trim(),
        contactoRecojo: document.getElementById('prov_contactoRecojo').value.trim(),
        telefonoRecojo: document.getElementById('prov_telefonoRecojo').value.trim(),
        instruccionesRecojo: document.getElementById('prov_instruccionesRecojo').value.trim(),
        estado: document.getElementById('prov_estado').value,
        obs: document.getElementById('prov_obs').value.trim()
    };

    if (!data.razon_social) { showToast('⚠️ La razón social es obligatoria', 'warning'); return; }
    if (!data.ruc) { showToast('⚠️ El RUC es obligatorio', 'warning'); return; }

    try {
        const url = provEditId ? `/maestros/api/proveedores/${provEditId}` : '/maestros/api/proveedores/guardar';
        const method = provEditId ? 'PUT' : 'POST';
        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await response.json();
        if (result.success) {
            
            

            showToast(result.message || '✅ Proveedor guardado correctamente', 'success');
            closeProveedorModal();
            await loadModuleData('proveedores', true);
            renderModule('proveedores');
        } else {
            showToast('❌ ' + (result.error || 'Error al guardar'), 'error');
        }
    } catch (error) {
        console.error('Error guardando proveedor:', error);
        showToast('❌ Error al guardar el proveedor', 'error');
    }
}

async function consultarSunatProveedor(ruc) {
    const btn = document.getElementById('provSunat');
    const originalText = btn.textContent;
    btn.textContent = '⏳ Consultando...';
    btn.disabled = true;
    try {
        const response = await fetch(`/api/sunat/consulta?ruc=${ruc}`);
        const data = await response.json();
        if (data.success) {
            document.getElementById('prov_razonSocial').value = data.razon_social || '';
            document.getElementById('prov_direccionFiscal').value = data.direccion || '';
            if (data.estado) {
                const estadoMap = { 'ACTIVO': 'Activo', 'BAJA': 'Inactivo', 'SUSPENDIDO': 'Observado' };
                const nuevoEstado = estadoMap[data.estado.toUpperCase()] || data.estado;
                if (nuevoEstado) { 
                    document.getElementById('prov_estado').value = nuevoEstado; 
                    syncProvState(); 
                }
            }
            showToast('✅ Datos SUNAT cargados correctamente', 'success');
        } else {
            showToast('❌ ' + (data.error || 'Error al consultar SUNAT'), 'error');
        }
    } catch (error) {
        console.error('Error consultando SUNAT:', error);
        showToast('❌ Error al conectar con el servicio SUNAT', 'error');
    } finally {
        btn.textContent = originalText;
        btn.disabled = false;
    }
}

// ============================================================
// MODAL ALMACÉN
// ============================================================
function openAlmacenModal(editId = null) {
    almEditId = editId;
    if (editId) {
        fetch(`/maestros/api/almacenes/${editId}`)
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    fillAlmacenForm(data.data);
                }
            })
            .catch(err => console.error('Error cargando almacén:', err));
    } else {
        clearAlmacenForm();
    }
    document.getElementById('almTitle').textContent = editId ? 'Editar almacén' : 'Crear almacén';
    document.getElementById('almHint').textContent = editId ? `Editando ID ${editId}` : 'Modo: creación';
    document.getElementById('almacenModal').classList.add('show');
    syncAlmState();
}

function clearAlmacenForm() {
    document.getElementById('alm_empresa').value = 'KCF';
    document.getElementById('alm_codigo').value = '';
    document.getElementById('alm_nombre').value = '';
    document.getElementById('alm_tipo').value = 'Principal';
    document.getElementById('alm_responsable').value = '';
    document.getElementById('alm_responsableCargo').value = '';
    document.getElementById('alm_telefono').value = '';
    document.getElementById('alm_email').value = '';
    document.getElementById('alm_direccion').value = '';
    document.getElementById('alm_googleMaps').value = '';
    document.getElementById('alm_horario').value = '';
    document.getElementById('alm_instrucciones').value = '';
    document.getElementById('alm_estado').value = 'Activo';
    document.getElementById('alm_obs').value = '';
    syncAlmState();
}

function fillAlmacenForm(data) {
    document.getElementById('alm_empresa').value = data.empresa || 'KCF';
    document.getElementById('alm_codigo').value = data.codigo || '';
    document.getElementById('alm_nombre').value = data.nombre || '';
    document.getElementById('alm_tipo').value = data.tipo || 'Principal';
    document.getElementById('alm_responsable').value = data.responsable || '';
    document.getElementById('alm_responsableCargo').value = data.responsableCargo || '';
    document.getElementById('alm_telefono').value = data.telefono || '';
    document.getElementById('alm_email').value = data.email || '';
    document.getElementById('alm_direccion').value = data.direccion || '';
    document.getElementById('alm_googleMaps').value = data.googleMaps || '';
    document.getElementById('alm_horario').value = data.horario || '';
    document.getElementById('alm_instrucciones').value = data.instrucciones || '';
    document.getElementById('alm_estado').value = data.estado || 'Activo';
    document.getElementById('alm_obs').value = data.obs || '';
    syncAlmState();
}

const ALM_STATE_CFG = {
    'Activo': {cls:'s-green', dot:'#84CC16', pill:'pill-green', txt:'Almacén habilitado para operar normalmente.'},
    'Observado': {cls:'s-yellow', dot:'#F59E0B', pill:'pill-yellow', txt:'Revisar condiciones antes de operar.'},
    'Bloqueado': {cls:'s-red', dot:'#FB7185', pill:'pill-red', txt:'No usar hasta liberación de Gerencia.'},
    'Inactivo': {cls:'s-gray', dot:'#94A3B8', pill:'pill-gray', txt:'Desactivado para nuevos registros.'}
};

function syncAlmState() {
    const v = document.getElementById('alm_estado')?.value || 'Activo';
    const cfg = ALM_STATE_CFG[v] || ALM_STATE_CFG['Activo'];
    const box = document.getElementById('almStateBox');
    if (box) box.className = 'cm-state-box ' + cfg.cls;
    const dot = document.getElementById('almStateDot');
    if (dot) dot.style.background = cfg.dot;
    const txt = document.getElementById('almStateText');
    if (txt) txt.textContent = cfg.txt;
    const pill = document.getElementById('almStatePill');
    if (pill) { pill.className = 'cm-state-pill ' + cfg.pill; pill.textContent = v; }
}

function closeAlmacenModal() {
    document.getElementById('almacenModal').classList.remove('show');
}

async function saveAlmacen() {
    const data = {
        empresa: document.getElementById('alm_empresa').value,
        codigo: document.getElementById('alm_codigo').value.trim(),
        nombre: document.getElementById('alm_nombre').value.trim(),
        tipo: document.getElementById('alm_tipo').value,
        responsable: document.getElementById('alm_responsable').value.trim(),
        responsableCargo: document.getElementById('alm_responsableCargo').value.trim(),
        telefono: document.getElementById('alm_telefono').value.trim(),
        email: document.getElementById('alm_email').value.trim(),
        direccion: document.getElementById('alm_direccion').value.trim(),
        googleMaps: document.getElementById('alm_googleMaps').value.trim(),
        horario: document.getElementById('alm_horario').value.trim(),
        instrucciones: document.getElementById('alm_instrucciones').value.trim(),
        estado: document.getElementById('alm_estado').value,
        obs: document.getElementById('alm_obs').value.trim()
    };

    if (!data.codigo) { showToast('⚠️ El código es obligatorio', 'warning'); return; }
    if (!data.nombre) { showToast('⚠️ El nombre es obligatorio', 'warning'); return; }
    if (!data.responsable) { showToast('⚠️ El responsable es obligatorio', 'warning'); return; }

    try {
        const url = almEditId ? `/maestros/api/almacenes/${almEditId}` : '/maestros/api/almacenes/guardar';
        const method = almEditId ? 'PUT' : 'POST';
        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await response.json();
        if (result.success) {

            

            showToast(result.message || '✅ Almacén guardado correctamente', 'success');
            closeAlmacenModal();
            await loadModuleData('almacenes', true);
            renderModule('almacenes');
        } else {
            showToast('❌ ' + (result.error || 'Error al guardar'), 'error');
        }
    } catch (error) {
        console.error('Error guardando almacén:', error);
        showToast('❌ Error al guardar el almacén', 'error');
    }
}

// ============================================================
// MODAL CATEGORÍA - USANDO MODAL GENÉRICO
// ============================================================
function openCategoriaModal(editId = null) {
    catEditId = editId;
    
    const modal = document.getElementById('masterModal');
    const title = document.getElementById('mmTitle');
    const hint = document.getElementById('mmMode');
    const fields = document.getElementById('mmFields');
    
    if (!modal) {
        console.error('❌ Modal genérico no encontrado');
        showToast('Error: Modal no configurado', 'error');
        return;
    }
    
    title.textContent = editId ? 'Editar categoría' : 'Crear categoría';
    hint.textContent = editId ? `Editando ID ${editId}` : 'Modo: creación';
    
    fields.innerHTML = `
        <div class="cm-section">
            <div class="cm-section-title">
                <span class="cm-bullet"></span>Información de categoría
            </div>
            <div class="cm-grid cm-grid-main">
                <div class="cm-field">
                    <label>ÁMBITO *</label>
                    <select id="cat_ambito">
                        <option value="COMPARTIDO">Compartido KCF + AGD</option>
                        <option value="KCF">Solo KCF</option>
                        <option value="AGD">Solo AGD</option>
                    </select>
                </div>
                <div class="cm-field">
                    <label>CÓDIGO *</label>
                    <input id="cat_codigo" type="text">
                </div>
                <div class="cm-field">
                    <label>NOMBRE *</label>
                    <input id="cat_nombre" type="text">
                </div>
                <div class="cm-field">
                    <label>CATEGORÍA PRINCIPAL</label>
                    <input id="cat_tipo" type="text" placeholder="Ej: Seguridad Industrial">
                </div>
            </div>
            <div class="cm-field full-row" style="margin-top:10px;">
                <label>OBSERVACIONES</label>
                <textarea id="cat_obs" style="height:60px;"></textarea>
            </div>
        </div>
    `;
    
    if (editId) {
        fetch(`/maestros/api/categorias/${editId}`)
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    document.getElementById('cat_ambito').value = data.data.ambito || 'COMPARTIDO';
                    document.getElementById('cat_codigo').value = data.data.codigo || '';
                    document.getElementById('cat_nombre').value = data.data.nombre || '';
                    document.getElementById('cat_tipo').value = data.data.tipo || '';
                    document.getElementById('cat_obs').value = data.data.obs || '';
                    document.getElementById('mm_estado').value = data.data.estado || 'Activo';
                }
            })
            .catch(err => console.error('Error cargando categoría:', err));
    } else {
        document.getElementById('cat_ambito').value = 'COMPARTIDO';
        document.getElementById('cat_codigo').value = '';
        document.getElementById('cat_nombre').value = '';
        document.getElementById('cat_tipo').value = '';
        document.getElementById('cat_obs').value = '';
        document.getElementById('mm_estado').value = 'Activo';
    }
    
    modal.classList.add('show');
    syncMasterState();
}

function closeCategoriaModal() {
    document.getElementById('masterModal').classList.remove('show');
}

async function saveCategoria() {
    const data = {
        ambito: document.getElementById('cat_ambito').value,
        codigo: document.getElementById('cat_codigo').value.trim(),
        nombre: document.getElementById('cat_nombre').value.trim(),
        tipo: document.getElementById('cat_tipo').value.trim(),
        estado: document.getElementById('mm_estado').value,
        obs: document.getElementById('cat_obs').value.trim()
    };

    if (!data.codigo) { showToast('⚠️ El código es obligatorio', 'warning'); return; }
    if (!data.nombre) { showToast('⚠️ El nombre es obligatorio', 'warning'); return; }

    try {
        const url = catEditId ? `/maestros/api/categorias/${catEditId}` : '/maestros/api/categorias/guardar';
        const method = catEditId ? 'PUT' : 'POST';
        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await response.json();
        if (result.success) {

            

            showToast(result.message || '✅ Categoría guardada correctamente', 'success');
            closeCategoriaModal();
            await loadModuleData('categorias', true);
            renderModule('categorias');
        } else {
            showToast('❌ ' + (result.error || 'Error al guardar'), 'error');
        }
    } catch (error) {
        console.error('Error guardando categoría:', error);
        showToast('❌ Error al guardar la categoría', 'error');
    }
}

// ============================================================
// MODAL MARCA - USANDO MODAL GENÉRICO
// ============================================================
function openMarcaModal(editId = null) {
    marcaEditId = editId;
    
    const modal = document.getElementById('masterModal');
    const title = document.getElementById('mmTitle');
    const hint = document.getElementById('mmMode');
    const fields = document.getElementById('mmFields');
    
    if (!modal) {
        console.error('❌ Modal genérico no encontrado');
        showToast('Error: Modal no configurado', 'error');
        return;
    }
    
    title.textContent = editId ? 'Editar marca' : 'Crear marca';
    hint.textContent = editId ? `Editando ID ${editId}` : 'Modo: creación';
    
    fields.innerHTML = `
        <div class="cm-section">
            <div class="cm-section-title">
                <span class="cm-bullet"></span>Información de marca
            </div>
            <div class="cm-grid cm-grid-main">
                <div class="cm-field">
                    <label>ÁMBITO *</label>
                    <select id="marca_ambito">
                        <option value="COMPARTIDO">Compartido KCF + AGD</option>
                        <option value="KCF">Solo KCF</option>
                        <option value="AGD">Solo AGD</option>
                    </select>
                </div>
                <div class="cm-field">
                    <label>CÓDIGO *</label>
                    <input id="marca_codigo" type="text">
                </div>
                <div class="cm-field">
                    <label>NOMBRE *</label>
                    <input id="marca_nombre" type="text">
                </div>
                <div class="cm-field">
                    <label>TIPO</label>
                    <select id="marca_tipo">
                        <option value="Original">Original</option>
                        <option value="Genérica">Genérica</option>
                        <option value="Licencia">Licencia</option>
                        <option value="Distribuidor">Distribuidor</option>
                    </select>
                </div>
            </div>
            <div class="cm-grid" style="grid-template-columns:1fr 1fr;margin-top:6px;">
                <div class="cm-field">
                    <label>PAÍS DE ORIGEN</label>
                    <input id="marca_paisOrigen" type="text" placeholder="Ej: Perú">
                </div>
                <div class="cm-field">
                    <label>PROVEEDOR REFERENCIA</label>
                    <input id="marca_proveedorReferencia" type="text" placeholder="Ej: Proveedor A">
                </div>
            </div>
            <div class="cm-field" style="margin-top:6px;">
                <label>SITIO WEB DE MARCA</label>
                <input id="marca_webMarca" type="text" placeholder="https://...">
            </div>
            <div class="cm-field full-row" style="margin-top:10px;">
                <label>OBSERVACIONES</label>
                <textarea id="marca_obs" style="height:60px;"></textarea>
            </div>
        </div>
    `;
    
    if (editId) {
        fetch(`/maestros/api/marcas/${editId}`)
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    document.getElementById('marca_ambito').value = data.data.ambito || 'COMPARTIDO';
                    document.getElementById('marca_codigo').value = data.data.codigo || '';
                    document.getElementById('marca_nombre').value = data.data.nombre || '';
                    document.getElementById('marca_tipo').value = data.data.tipo || 'Original';
                    document.getElementById('marca_paisOrigen').value = data.data.paisOrigen || '';
                    document.getElementById('marca_proveedorReferencia').value = data.data.proveedorReferencia || '';
                    document.getElementById('marca_webMarca').value = data.data.webMarca || '';
                    document.getElementById('marca_obs').value = data.data.obs || '';
                    document.getElementById('mm_estado').value = data.data.estado || 'Activo';
                }
            })
            .catch(err => console.error('Error cargando marca:', err));
    } else {
        document.getElementById('marca_ambito').value = 'COMPARTIDO';
        document.getElementById('marca_codigo').value = '';
        document.getElementById('marca_nombre').value = '';
        document.getElementById('marca_tipo').value = 'Original';
        document.getElementById('marca_paisOrigen').value = '';
        document.getElementById('marca_proveedorReferencia').value = '';
        document.getElementById('marca_webMarca').value = '';
        document.getElementById('marca_obs').value = '';
        document.getElementById('mm_estado').value = 'Activo';
    }
    
    modal.classList.add('show');
    syncMasterState();
}

function closeMarcaModal() {
    document.getElementById('masterModal').classList.remove('show');
}

async function saveMarca() {
    const data = {
        ambito: document.getElementById('marca_ambito').value,
        codigo: document.getElementById('marca_codigo').value.trim(),
        nombre: document.getElementById('marca_nombre').value.trim(),
        tipo: document.getElementById('marca_tipo').value,
        paisOrigen: document.getElementById('marca_paisOrigen').value.trim(),
        proveedorReferencia: document.getElementById('marca_proveedorReferencia').value.trim(),
        webMarca: document.getElementById('marca_webMarca').value.trim(),
        estado: document.getElementById('mm_estado').value,
        obs: document.getElementById('marca_obs').value.trim()
    };

    if (!data.codigo) { showToast('⚠️ El código es obligatorio', 'warning'); return; }
    if (!data.nombre) { showToast('⚠️ El nombre es obligatorio', 'warning'); return; }

    try {
        const url = marcaEditId ? `/maestros/api/marcas/${marcaEditId}` : '/maestros/api/marcas/guardar';
        const method = marcaEditId ? 'PUT' : 'POST';
        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await response.json();
        if (result.success) {

            

            showToast(result.message || '✅ Marca guardada correctamente', 'success');
            closeMarcaModal();
            await loadModuleData('marcas', true);
            renderModule('marcas');
        } else {
            showToast('❌ ' + (result.error || 'Error al guardar'), 'error');
        }
    } catch (error) {
        console.error('Error guardando marca:', error);
        showToast('❌ Error al guardar la marca', 'error');
    }
}

// ============================================================
// MODAL UNIDAD DE MEDIDA (UM) - USANDO MODAL GENÉRICO
// ============================================================
function openUmModal(editId = null) {
    umEditId = editId;
    
    const modal = document.getElementById('masterModal');
    const title = document.getElementById('mmTitle');
    const hint = document.getElementById('mmMode');
    const fields = document.getElementById('mmFields');
    
    if (!modal) {
        console.error('❌ Modal genérico no encontrado');
        showToast('Error: Modal no configurado', 'error');
        return;
    }
    
    title.textContent = editId ? 'Editar unidad de medida' : 'Crear unidad de medida';
    hint.textContent = editId ? `Editando ID ${editId}` : 'Modo: creación';
    
    fields.innerHTML = `
        <div class="cm-section">
            <div class="cm-section-title">
                <span class="cm-bullet"></span>Información de unidad de medida
            </div>
            <div class="cm-grid cm-grid-main">
                <div class="cm-field">
                    <label>ÁMBITO *</label>
                    <select id="um_ambito">
                        <option value="COMPARTIDO">Compartido KCF + AGD</option>
                        <option value="KCF">Solo KCF</option>
                        <option value="AGD">Solo AGD</option>
                    </select>
                </div>
                <div class="cm-field">
                    <label>CÓDIGO *</label>
                    <input id="um_codigo" type="text" placeholder="Ej: KGM">
                </div>
                <div class="cm-field">
                    <label>UNIDAD *</label>
                    <input id="um_nombre" type="text" placeholder="Ej: Kilogramo">
                </div>
                <div class="cm-field">
                    <label>ABREVIATURA *</label>
                    <input id="um_simbolo" type="text" placeholder="Ej: kg">
                </div>
            </div>
            <div class="cm-grid" style="grid-template-columns:1fr 1fr;margin-top:6px;">
                <div class="cm-field">
                    <label>TIPO</label>
                    <select id="um_tipo">
                        <option value="Cantidad">Cantidad</option>
                        <option value="Peso">Peso</option>
                        <option value="Volumen">Volumen</option>
                        <option value="Longitud">Longitud</option>
                        <option value="Área">Área</option>
                        <option value="Tiempo">Tiempo</option>
                        <option value="Otro">Otro</option>
                    </select>
                </div>
                <div class="cm-field">
                    <label>PERMITE DECIMALES</label>
                    <select id="um_decimal">
                        <option value="No">No</option>
                        <option value="Sí">Sí</option>
                    </select>
                </div>
            </div>
            <div class="cm-field" style="margin-top:6px;">
                <label>OBSERVACIONES</label>
                <textarea id="um_obs" style="height:60px;"></textarea>
            </div>
        </div>
    `;
    
    if (editId) {
        fetch(`/maestros/api/um/${editId}`)
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    document.getElementById('um_ambito').value = data.data.ambito || 'COMPARTIDO';
                    document.getElementById('um_codigo').value = data.data.codigo || '';
                    document.getElementById('um_nombre').value = data.data.nombre || '';
                    document.getElementById('um_simbolo').value = data.data.abreviatura || '';
                    document.getElementById('um_tipo').value = data.data.tipo || 'Cantidad';
                    document.getElementById('um_decimal').value = data.data.decimales ? 'Sí' : 'No';
                    document.getElementById('um_obs').value = data.data.obs || '';
                    document.getElementById('mm_estado').value = data.data.estado || 'Activo';
                }
            })
            .catch(err => console.error('Error cargando unidad:', err));
    } else {
        document.getElementById('um_ambito').value = 'COMPARTIDO';
        document.getElementById('um_codigo').value = '';
        document.getElementById('um_nombre').value = '';
        document.getElementById('um_simbolo').value = '';
        document.getElementById('um_tipo').value = 'Cantidad';
        document.getElementById('um_decimal').value = 'No';
        document.getElementById('um_obs').value = '';
        document.getElementById('mm_estado').value = 'Activo';
    }
    
    modal.classList.add('show');
    syncMasterState();
}

function closeUmModal() {
    document.getElementById('masterModal').classList.remove('show');
}

async function saveUm() {
    const data = {
        ambito: document.getElementById('um_ambito').value,
        codigo: document.getElementById('um_codigo').value.trim(),
        nombre: document.getElementById('um_nombre').value.trim(),
        abreviatura: document.getElementById('um_simbolo').value.trim(),
        tipo: document.getElementById('um_tipo').value,
        decimales: document.getElementById('um_decimal').value === 'Sí',
        estado: document.getElementById('mm_estado').value,
        obs: document.getElementById('um_obs').value.trim()
    };

    if (!data.codigo) { showToast('⚠️ El código es obligatorio', 'warning'); return; }
    if (!data.abreviatura) { showToast('⚠️ La abreviatura es obligatoria', 'warning'); return; }
    if (!data.nombre) { showToast('⚠️ El nombre es obligatorio', 'warning'); return; }

    try {
        const url = umEditId ? `/maestros/api/um/${umEditId}` : '/maestros/api/um/guardar';
        const method = umEditId ? 'PUT' : 'POST';
        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await response.json();
        if (result.success) {

            
            
            showToast(result.message || '✅ Unidad guardada correctamente', 'success');
            closeUmModal();
            await loadModuleData('um', true);
            renderModule('um');
        } else {
            showToast('❌ ' + (result.error || 'Error al guardar'), 'error');
        }
    } catch (error) {
        console.error('Error guardando unidad:', error);
        showToast('❌ Error al guardar la unidad', 'error');
    }
}

// ============================================================
// SINCORNIZAR ESTADO DEL MODAL GENÉRICO
// ============================================================
function syncMasterState() {
    const v = document.getElementById('mm_estado')?.value || 'Activo';
    const cfg = STATE_CFG[v] || STATE_CFG['Activo'];
    
    const box = document.getElementById('mmStateBox');
    if (box) box.className = 'cm-state-box ' + cfg.cls;
    
    const dot = document.getElementById('mmStateDot');
    if (dot) dot.style.background = cfg.dot;
    
    const txt = document.getElementById('mmStateText');
    if (txt) txt.textContent = cfg.txt;
    
    const pill = document.getElementById('mmStatePill');
    if (pill) { pill.className = 'cm-state-pill ' + cfg.pill; pill.textContent = v; }
}

// ============================================================
// MODAL DE CONFIRMACIÓN GENÉRICO PARA MAESTROS (SIN "IRREVERSIBLE")
// ============================================================
function showConfirmModalMaestro(entidad, onConfirm) {
    // Remover modales existentes
    document.querySelectorAll('.confirm-modal-maestro-overlay').forEach(el => el.remove());

    const overlay = document.createElement('div');
    overlay.className = 'confirm-modal-maestro-overlay';
    overlay.style.cssText = `
        position: fixed;
        inset: 0;
        background: rgba(0, 0, 0, 0.55);
        backdrop-filter: blur(6px);
        z-index: 999999;
        display: flex;
        align-items: center;
        justify-content: center;
        animation: fadeInMaestro 0.25s ease;
    `;

    const modal = document.createElement('div');
    modal.style.cssText = `
        background: #FFFFFF;
        border-radius: 18px;
        max-width: 440px;
        width: 92%;
        padding: 28px 26px 22px;
        box-shadow: 0 24px 60px rgba(0,0,0,0.3);
        animation: modalSlideUpMaestro 0.25s ease;
        text-align: center;
    `;

    modal.innerHTML = `
        <div style="font-size: 42px; margin-bottom: 10px;">❓</div>
        <h2 style="font-size: 19px; font-weight: 900; color: #0F172A; margin-bottom: 6px;">
            ¿Estás seguro de guardar ${entidad}?
        </h2>
        <p style="font-size: 13.5px; color: #64748B; line-height: 1.4; margin-bottom: 22px;">
            Revisa que los datos ingresados sean correctos antes de continuar.
        </p>
        <div style="display: flex; gap: 10px; justify-content: center;">
            <button class="cmm-cancel-btn" style="
                padding: 10px 26px;
                border-radius: 10px;
                border: 1px solid #E5E7EB;
                background: #FFFFFF;
                color: #0F172A;
                font-weight: 800;
                font-size: 13px;
                cursor: pointer;
                transition: all 0.2s;
            ">Cancelar</button>
            <button class="cmm-accept-btn" style="
                padding: 10px 26px;
                border-radius: 10px;
                border: none;
                background: #16A34A;
                color: #FFFFFF;
                font-weight: 800;
                font-size: 13px;
                cursor: pointer;
                transition: all 0.2s;
                box-shadow: 0 4px 14px rgba(22,163,74,0.35);
            ">✅ Sí, guardar</button>
        </div>
    `;

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    // Animaciones (solo se agregan una vez)
    if (!document.getElementById('confirmModalMaestroStyles')) {
        const style = document.createElement('style');
        style.id = 'confirmModalMaestroStyles';
        style.textContent = `
            @keyframes fadeInMaestro {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            @keyframes modalSlideUpMaestro {
                from { opacity: 0; transform: translateY(20px) scale(0.96); }
                to { opacity: 1; transform: translateY(0) scale(1); }
            }
            .cmm-cancel-btn:hover { background: #F1F5F9; }
            .cmm-accept-btn:hover { background: #15803D; transform: translateY(-1px); }
        `;
        document.head.appendChild(style);
    }

    modal.querySelector('.cmm-cancel-btn').addEventListener('click', () => overlay.remove());

    modal.querySelector('.cmm-accept-btn').addEventListener('click', () => {
        overlay.remove();
        if (typeof onConfirm === 'function') onConfirm();
    });

    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) overlay.remove();
    });
}

// ============================================================
// VER DETALLE (GENERICO)
// ============================================================
function openViewModal(modulo, id) {
    const r = DS[modulo]?.find(x => x.id === id);
    if (!r) {
        showToast('Registro no encontrado', 'error');
        return;
    }
    
    const config = MODULE_CONFIG[modulo];
    
    const existing = document.getElementById('modalView');
    if (existing) existing.remove();
    
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.id = 'modalView';
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.5);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 99999;
        padding: 20px;
    `;
    
    let detailsHtml = '';
    config.fields.forEach(f => {
        const value = r[f.key] !== undefined && r[f.key] !== null ? r[f.key] : '-';
        const displayValue = typeof value === 'boolean' ? (value ? '✅ Sí' : '❌ No') : value;
        detailsHtml += `
            <div style="display:flex;padding:6px 0;border-bottom:1px solid #f1f5f9;">
                <span style="font-weight:600;width:150px;color:#64748B;">${f.label}</span>
                <span>${displayValue}</span>
            </div>
        `;
    });
    
    modal.innerHTML = `
        <div style="background:white;border-radius:12px;max-width:600px;width:100%;max-height:90vh;overflow:auto;padding:24px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid #e2e8f0;">
                <h2 style="margin:0;font-size:20px;">👁️ Detalle de ${config.title.slice(0, -1)}</h2>
                <button onclick="closeViewModal()" style="background:none;border:none;font-size:24px;cursor:pointer;color:#64748B;">✕</button>
            </div>
            <div style="background:#f8fafc;padding:16px;border-radius:8px;margin-bottom:16px;">
                <div style="font-size:13px;color:#64748B;">Código</div>
                <div style="font-size:18px;font-weight:700;">${getCode(r, modulo)}</div>
            </div>
            <div>
                ${detailsHtml}
            </div>
            <div style="margin-top:16px;display:flex;gap:10px;justify-content:flex-end;padding-top:12px;border-top:1px solid #e2e8f0;">
                <button onclick="closeViewModal()" style="padding:8px 20px;border:1px solid #e2e8f0;border-radius:6px;background:white;cursor:pointer;">Cerrar</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
}

function closeViewModal() {
    const modal = document.getElementById('modalView');
    if (modal) modal.remove();
}


// ============================================================
// EVENT DELEGATION - TABS, CREAR, EDITAR, ELIMINAR, VIEW
// ============================================================
document.addEventListener('click', function(e) {
    // Navegación de tabs
    const tabBtn = e.target.closest('.tab-btn[data-tab]');
    if (tabBtn) {
        e.preventDefault();
        const tab = tabBtn.dataset.tab;
        if (tab) openScreen(tab);
        return;
    }

    // Crear nuevo
    const newBtn = e.target.closest('[data-new]');
    if (newBtn) {
        e.preventDefault();
        const m = newBtn.dataset.new;
        if (m === 'clientes') openClientModal();
        else if (m === 'proveedores') openProveedorModal();
        else if (m === 'almacenes') openAlmacenModal();
        else if (m === 'categorias') openCategoriaModal();
        else if (m === 'marcas') openMarcaModal();
        else if (m === 'um') openUmModal();
        else {
            showToast(`📝 Funcionalidad: Crear nuevo ${m} (próximamente)`, 'info');
        }
        return;
    }

    // Editar
    const editBtn = e.target.closest('[data-edit]');
    if (editBtn) {
        e.preventDefault();
        const [m, id] = editBtn.dataset.edit.split('|');
        const idNum = parseInt(id);
        if (m === 'clientes') openClientModal(idNum);
        else if (m === 'proveedores') openProveedorModal(idNum);
        else if (m === 'almacenes') openAlmacenModal(idNum);
        else if (m === 'categorias') openCategoriaModal(idNum);
        else if (m === 'marcas') openMarcaModal(idNum);
        else if (m === 'um') openUmModal(idNum);
        else {
            showToast(`✏️ Editar ${m} ID: ${id} (próximamente)`, 'info');
        }
        return;
    }

    // ============================================================
    // ✅ ELIMINAR (data-delete) - CORREGIDO
    // ============================================================
    const deleteBtn = e.target.closest('[data-delete]');
    if (deleteBtn) {
        e.preventDefault();
        e.stopPropagation();
        console.log('🗑️ Click en eliminar:', deleteBtn.dataset.delete);
        
        const [m, id] = deleteBtn.dataset.delete.split('|');
        const idNum = parseInt(id);
        
        console.log('📋 Módulo:', m, 'ID:', idNum);
        
        // Buscar el registro para mostrar el nombre
        const registro = DS[m]?.find(x => x.id === idNum);
        console.log('📋 Registro encontrado:', registro);
        
        const nombre = registro ? (registro.razon_social || registro.nombre || registro.codigo || 'este registro') : 'este registro';
        
        if (confirm(`¿Estás seguro de eliminar "${nombre}"? Esta acción no se puede deshacer.`)) {
            eliminarRegistro(m, idNum);
        }
        return;
    }

    // Ver detalle
    const viewBtn = e.target.closest('[data-view]');
    if (viewBtn) {
        e.preventDefault();
        const [m, id] = viewBtn.dataset.view.split('|');
        openViewModal(m, parseInt(id));
        return;
    }
});

// ============================================================
// DOMContentLoaded - UNIFICADO Y COMPLETO
// ============================================================
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Iniciando Módulo Maestros');
    console.log('📊 Módulos disponibles:', Object.keys(MODULE_CONFIG));
    console.log('📋 ENDPOINTS ESPERADOS:');
    console.log('   - GET  /maestros/api/clientes/listar');
    console.log('   - POST /maestros/api/clientes/guardar');
    console.log('   - PUT  /maestros/api/clientes/<id>/toggle');
    console.log('   - GET  /maestros/api/clientes/<id>');
    
    // VERIFICAR CONTENEDORES
    const containers = Object.keys(MODULE_CONFIG);
    containers.forEach(m => {
        if (!document.getElementById(m)) {
            console.warn(`⚠️ No existe el contenedor #${m} en el HTML, creándolo...`);
            const mainPanel = document.querySelector('.main-inner');
            if (mainPanel) {
                const section = document.createElement('section');
                section.id = m;
                section.className = 'section';
                const dashboard = document.getElementById('dashboard');
                if (dashboard && dashboard.parentNode) {
                    dashboard.parentNode.insertBefore(section, dashboard.nextSibling);
                } else {
                    mainPanel.appendChild(section);
                }
                console.log(`✅ Contenedor #${m} creado`);
            }
        }
    });
    
    // 1. EVENTOS DEL MODAL CLIENTE
    const closeBtn = document.getElementById('cmClose');
    const cancelBtn = document.getElementById('cmCancel');
    const clearBtn = document.getElementById('cmClear');
    const saveBtn = document.getElementById('cmSave');
    const sunatBtn = document.getElementById('btnSunat');
    const addContactBtn = document.getElementById('btnAddContact');
    const addPointBtn = document.getElementById('btnAddPoint');
    const estadoSelect = document.getElementById('cli_estado');
    
    if (closeBtn) closeBtn.addEventListener('click', closeClientModal);
    if (cancelBtn) cancelBtn.addEventListener('click', closeClientModal);
    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            if (clientEditId) {
                openClientModal(clientEditId);
            } else {
                clearClientForm();
            }
        });
    }
    if (saveBtn) saveBtn.addEventListener('click', function() {
    showConfirmModalMaestro('este cliente', saveClient);
    });
    if (sunatBtn) sunatBtn.addEventListener('click', consultarSunat);
    if (addContactBtn) {
        addContactBtn.addEventListener('click', () => {
            document.getElementById('cliContacts').insertAdjacentHTML('beforeend', contactBox({}));
        });
    }
    if (addPointBtn) {
        addPointBtn.addEventListener('click', () => {
            document.getElementById('cliPoints').insertAdjacentHTML('beforeend', pointBox({}));
        });
    }
    if (estadoSelect) estadoSelect.addEventListener('change', syncClientState);
    
    // 2. EVENTOS DEL MODAL PROVEEDOR
    const provClose = document.getElementById('provClose');
    const provCancel = document.getElementById('provCancel');
    const provClear = document.getElementById('provClear');
    const provSave = document.getElementById('provSave');
    const provSunat = document.getElementById('provSunat');
    const provEstado = document.getElementById('prov_estado');
    
    if (provClose) provClose.addEventListener('click', closeProveedorModal);
    if (provCancel) provCancel.addEventListener('click', closeProveedorModal);
    if (provClear) {
        provClear.addEventListener('click', () => {
            if (provEditId) {
                openProveedorModal(provEditId);
            } else {
                clearProveedorForm();
            }
        });
    }
    if (provSave) provSave.addEventListener('click', function() {
    showConfirmModalMaestro('este proveedor', saveProveedor);
    });
    if (provSunat) {
        provSunat.addEventListener('click', function() {
            const ruc = document.getElementById('prov_ruc').value.trim();
            if (!ruc) {
                showToast('⚠️ Ingresa un RUC para consultar.', 'warning');
                return;
            }
            if (ruc.length !== 11) {
                showToast('⚠️ El RUC debe tener 11 dígitos.', 'warning');
                return;
            }
            consultarSunatProveedor(ruc);
        });
    }
    if (provEstado) provEstado.addEventListener('change', syncProvState);

    // 3. EVENTOS DEL MODAL ALMACÉN
    const almClose = document.getElementById('almClose');
    const almCancel = document.getElementById('almCancel');
    const almClear = document.getElementById('almClear');
    const almSave = document.getElementById('almSave');
    const almEstado = document.getElementById('alm_estado');
    
    if (almClose) almClose.addEventListener('click', closeAlmacenModal);
    if (almCancel) almCancel.addEventListener('click', closeAlmacenModal);
    if (almClear) {
        almClear.addEventListener('click', () => {
            if (almEditId) {
                openAlmacenModal(almEditId);
            } else {
                clearAlmacenForm();
            }
        });
    }
    if (almSave) almSave.addEventListener('click', function() {
    showConfirmModalMaestro('este almacén', saveAlmacen);
    });
    if (almEstado) almEstado.addEventListener('change', syncAlmState);

    // 4. EVENTOS DEL MODAL GENÉRICO (masterModal)
    const mmClose = document.getElementById('mmClose');
    const mmCancel = document.getElementById('mmCancel');
    const mmClear = document.getElementById('mmClear');
    const mmSave = document.getElementById('mmSave');
    const mmEstado = document.getElementById('mm_estado');
    const mmModal = document.getElementById('masterModal');

    if (mmClose) {
        mmClose.addEventListener('click', function() {
            if (mmModal) mmModal.classList.remove('show');
        });
    }
    if (mmCancel) {
        mmCancel.addEventListener('click', function() {
            if (mmModal) mmModal.classList.remove('show');
        });
    }
    if (mmClear) {
        mmClear.addEventListener('click', function() {
            const title = document.getElementById('mmTitle')?.textContent || '';
            if (title.includes('categoría')) {
                document.getElementById('cat_codigo').value = '';
                document.getElementById('cat_nombre').value = '';
                document.getElementById('cat_tipo').value = '';
                document.getElementById('cat_obs').value = '';
                if (document.getElementById('mm_estado')) {
                    document.getElementById('mm_estado').value = 'Activo';
                }
                syncMasterState();
                showToast('🧹 Formulario de categoría limpiado', 'info');
            } else if (title.includes('marca')) {
                document.getElementById('marca_codigo').value = '';
                document.getElementById('marca_nombre').value = '';
                document.getElementById('marca_tipo').value = 'Original';
                document.getElementById('marca_paisOrigen').value = '';
                document.getElementById('marca_proveedorReferencia').value = '';
                document.getElementById('marca_webMarca').value = '';
                document.getElementById('marca_obs').value = '';
                if (document.getElementById('mm_estado')) {
                    document.getElementById('mm_estado').value = 'Activo';
                }
                syncMasterState();
                showToast('🧹 Formulario de marca limpiado', 'info');
            } else if (title.includes('unidad')) {
                document.getElementById('um_codigo').value = '';
                document.getElementById('um_nombre').value = '';
                document.getElementById('um_simbolo').value = '';
                document.getElementById('um_tipo').value = 'Cantidad';
                document.getElementById('um_decimal').value = 'No';
                document.getElementById('um_obs').value = '';
                if (document.getElementById('mm_estado')) {
                    document.getElementById('mm_estado').value = 'Activo';
                }
                syncMasterState();
                showToast('🧹 Formulario de unidad limpiado', 'info');
            } else {
                showToast('⚠️ No se pudo determinar qué limpiar', 'warning');
            }
        });
    }
    if (mmSave) {
        mmSave.addEventListener('click', function() {
            const title = document.getElementById('mmTitle')?.textContent || '';
            if (title.includes('categoría')) {
                showConfirmModalMaestro('esta categoría', saveCategoria);
            } else if (title.includes('marca')) {
                showConfirmModalMaestro('esta marca', saveMarca);
            } else if (title.includes('unidad')) {
                showConfirmModalMaestro('esta unidad de medida', saveUm);
            } else {
                showToast('⚠️ No se pudo determinar el tipo de registro', 'warning');
            }
        });
    }
    if (mmEstado) {
        mmEstado.addEventListener('change', syncMasterState);
    }
    if (mmModal) {
        mmModal.addEventListener('click', function(e) {
            if (e.target === this) {
                this.classList.remove('show');
            }
        });
    }

    // 5. ELIMINAR CONTACTO/PUNTO (delegación global)
    document.addEventListener('click', function(e) {
        const rc = e.target.closest('[data-rc]');
        if (rc) {
            const b = rc.closest('[data-cid]');
            if (document.querySelectorAll('[data-cid]').length > 1) {
                b?.remove();
            } else {
                showToast('Debe quedar al menos un contacto.', 'warning');
            }
        }
        const rp = e.target.closest('[data-rp]');
        if (rp) {
            const b = rp.closest('[data-pid]');
            if (document.querySelectorAll('[data-pid]').length > 1) {
                b?.remove();
            } else {
                showToast('Debe quedar al menos un punto.', 'warning');
            }
        }
    });

    // 6. CERRAR CON TECLA ESCAPE (global)
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            if (mmModal && mmModal.classList.contains('show')) {
                mmModal.classList.remove('show');
            }
            const clientModal = document.getElementById('clientModal');
            if (clientModal && clientModal.classList.contains('show')) {
                clientModal.classList.remove('show');
            }
            const provModal = document.getElementById('proveedorModal');
            if (provModal && provModal.classList.contains('show')) {
                provModal.classList.remove('show');
            }
            const almModal = document.getElementById('almacenModal');
            if (almModal && almModal.classList.contains('show')) {
                almModal.classList.remove('show');
            }
        }
    });

    // 7. MODULO INICIAL
    const urlParams = new URLSearchParams(window.location.search);
    const tabParam = urlParams.get('tab');
    const defaultModule = tabParam && MODULE_CONFIG[tabParam] ? tabParam : 'clientes';
    
    console.log(`🎯 Módulo inicial: ${defaultModule}`);
    
    setTimeout(() => {
        openScreen(defaultModule);
    }, 200);

    console.log('✅ Todos los event listeners configurados correctamente');
});

console.log('✅ Maestros JS cargado correctamente');

// ============================================================
// ✅ ACTIVAR BÚSQUEDA EN TIEMPO REAL - EVENTO GLOBAL
// ============================================================

// Escuchar cambios en todos los inputs de búsqueda
document.addEventListener('input', function(e) {
    const input = e.target;
    if (input.classList.contains('search-input') || input.id.startsWith('search_')) {
        const modulo = input.id.replace('search_', '');
        if (MODULE_CONFIG[modulo]) {
            const searchTerm = input.value.toLowerCase().trim();
            
            const container = document.getElementById(modulo);
            if (!container) return;
            
            const table = container.querySelector('.master-table');
            if (!table) return;
            
            const rows = table.querySelectorAll('tbody tr');
            let visibleCount = 0;
            
            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                if (searchTerm === '' || text.includes(searchTerm)) {
                    row.style.display = '';
                    visibleCount++;
                } else {
                    row.style.display = 'none';
                }
            });
            
            // Actualizar contador
            const subtitle = container.querySelector('.master-subtitle');
            if (subtitle) {
                const total = DS[modulo]?.length || 0;
                const config = MODULE_CONFIG[modulo];
                subtitle.textContent = `${config?.subtitle || ''} (${visibleCount} registros)`;
            }
        }
    }
});

console.log('✅ Buscador en tiempo real activado');

// ============================================================
// DETECTAR SCROLL EN TABLA - AGREGAR SOMBRA AL HEADER
// ============================================================

document.addEventListener('scroll', function(e) {
    const scrollContainers = document.querySelectorAll('.table-scroll');
    scrollContainers.forEach(container => {
        if (container.scrollTop > 5) {
            container.classList.add('sticky-shadow');
        } else {
            container.classList.remove('sticky-shadow');
        }
    });
}, { passive: true });

// También detectar scroll dentro del contenedor
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.table-scroll').forEach(container => {
        container.addEventListener('scroll', function() {
            if (this.scrollTop > 5) {
                this.classList.add('sticky-shadow');
            } else {
                this.classList.remove('sticky-shadow');
            }
        });
    });
});



// ============================================================
// OBTENER CLIENTES CON DATOS COMPLETOS (como en el modal)
// ============================================================

async function cargarClientesCompletos() {
    try {
        // ✅ USA EL MISMO ENDPOINT QUE EL MODAL DE EDICIÓN
        const response = await fetch('/maestros/api/clientes/listar');
        const data = await response.json();
        
        if (data.success) {
            // ✅ GUARDA LOS DATOS COMPLETOS EN DS
            DS['clientes'] = data.data;
            dataCache['clientes'] = data.data;
            return data.data;
        }
        return [];
    } catch (error) {
        console.error('❌ Error cargando clientes completos:', error);
        return [];
    }
}


// ============================================================
// VISTA COMPLETA - TODOS LOS CAMPOS DEL CLIENTE (CON BADGE NUEVO)
// ============================================================

function renderClientesCompleta(list) {
    if (!list || !list.length) {
        return `<div class="empty-state">
            <div style="font-size: 48px; margin-bottom: 10px;">📭</div>
            <p style="color: #64748B; font-weight: 500;">No se encontraron registros</p>
        </div>`;
    }
    
    const allFields = [
        { key: 'id', label: 'ID', width: '50px' },
        { key: 'codigo_cliente', label: 'Código / Cliente', width: '100px' },
        { key: 'ambito', label: 'Ámbito', width: '90px' },
        { key: 'tipo_documento', label: 'Tipo Doc.', width: '80px' },
        { key: 'numero_documento', label: 'N° Documento', width: '120px' },
        { key: 'razon_social', label: 'Razón Social', width: '180px' },
        { key: 'nombre_comercial', label: 'Nombre Comercial', width: '150px' },
        { key: 'direccion_fiscal', label: 'Dirección Fiscal', width: '200px' },
        { key: 'condicion_pago', label: 'Condición Pago', width: '100px' },
        { key: 'dias_credito', label: 'Días Crédito', width: '80px' },
        { key: 'limite_credito', label: 'Límite Crédito', width: '100px' },
        { key: 'descuento', label: 'Descuento', width: '80px' },
        { key: 'nombre_contacto', label: 'Contacto Principal', width: '130px' },
        { key: 'telefono_contacto', label: 'Teléfono Principal', width: '110px' },
        { key: 'email_contacto', label: 'Email Principal', width: '160px' },
        { key: 'contactos', label: 'Contactos', width: '200px' },
        { key: 'puntos_entrega', label: 'Puntos de Entrega', width: '280px' },
        { key: 'estado', label: 'Estado', width: '90px' },
        { key: 'activo', label: 'Activo', width: '70px' },
        { key: 'observaciones', label: 'Observaciones', width: '150px' },
        { key: 'created_at', label: 'Creado', width: '110px' },
        { key: 'updated_at', label: 'Actualizado', width: '110px' }
    ];
    
    let headersHtml = '<th style="width:40px;">Item</th>';
    allFields.forEach(f => {
        headersHtml += `<th style="width:${f.width || 'auto'};text-align:center;">${f.label}</th>`;
    });
    headersHtml += '<th style="width:160px; min-width:160px; text-align:center;">Acciones</th>';
    
    const rows = list.map((r, i) => {
        // ✅ BADGE NUEVO - Usa created_at
        const badgeHtml = badgeNuevo(r, 'created_at');
        
        let cells = `<td style="text-align:center;"><b>${i + 1}</b>${badgeHtml}</td>`;
        allFields.forEach(f => {
            let value = r[f.key];
            
            if (value === undefined || value === null || value === '') {
                value = '-';
            } else if (f.key === 'estado') {
                value = bEstado(value);
            } else if (f.key === 'activo') {
                value = value === true || value === 'true' 
                    ? '<span class="badge b-ok">✅ Sí</span>' 
                    : '<span class="badge b-gray">❌ No</span>';
            } else if (f.key === 'ambito') {
                value = bAmbito(value);
            } else if (f.key === 'contactos') {
                if (r.contactos && r.contactos.length > 0) {
                    value = r.contactos.map(c => 
                        `<div style="font-size:10px;padding:2px 0;border-bottom:1px solid #f0f0f0;text-align:left;">
                            <strong>${c.nombre_contacto || c.nombre || '-'}</strong>
                            ${c.cargo ? `<span style="color:#64748B;"> (${c.cargo})</span>` : ''}
                            ${c.principal ? ' ⭐' : ''}
                            <br><small>${c.telefono || ''} ${c.email ? '| ' + c.email : ''}</small>
                        </div>`
                    ).join('');
                } else {
                    value = '-';
                }
            } else if (f.key === 'puntos_entrega') {
                if (r.puntos_entrega && r.puntos_entrega.length > 0) {
                    value = r.puntos_entrega.map(p => {
                        let html = `<div style="font-size:10px;padding:2px 0;border-bottom:1px solid #f0f0f0;text-align:left;">
                            <strong>${p.nombre_punto || p.punto || '-'}</strong>
                            ${p.principal ? ' ⭐' : ''}
                            <br><small>${p.direccion || ''} ${p.telefono_contacto || p.telefono ? '| Tel: ' + (p.telefono_contacto || p.telefono) : ''}</small>`;
                        
                        const mapsLink = p.google_maps || p.googleMaps;
                        if (mapsLink) {
                            html += `<br><a href="${mapsLink}" target="_blank" style="color:#2563EB;text-decoration:underline;font-size:10px;">📍 Ver en Google Maps</a>`;
                        }
                        
                        if (p.instrucciones) {
                            html += `<br><span style="color:#2563EB;">📝 ${p.instrucciones}</span>`;
                        }
                        
                        html += `</div>`;
                        return html;
                    }).join('');
                } else {
                    value = '-';
                }
            } else if (f.key === 'limite_credito' || f.key === 'descuento') {
                if (value && !isNaN(value)) {
                    value = `S/ ${parseFloat(value).toFixed(2)}`;
                }
            } else if (f.key === 'created_at' || f.key === 'updated_at') {
                value = value ? new Date(value).toLocaleDateString('es-PE') : '-';
            } else if (f.key === 'dias_credito') {
                value = value ? `${value} días` : '-';
            } else if (f.key === 'tipo_documento') {
                const tipos = { 'RUC': 'RUC', 'DNI': 'DNI', 'CE': 'C.E.' };
                value = tipos[value] || value || '-';
            }
            
            cells += `<td style="text-align:center;">${value}</td>`;
        });
        
        const isActive = r.estado === 'Activo' || r.estado === 'activo' || r.activo === true;
        const estadoDisplay = isActive ? 'Desactivar' : 'Activar';
        const estadoClass = isActive ? 'action-delete' : 'action-activate';
        
        cells += `
            <td style="text-align:center;">
                <div style="display:flex;gap:4px;justify-content:center;flex-wrap:wrap;">
                    <button class="action-btn action-view" data-view="clientes|${r.id}" title="Ver">👁️</button>
                    <button class="action-btn action-edit" data-edit="clientes|${r.id}" title="Editar">✏️</button>
                    <button class="action-btn ${estadoClass}" data-delete="clientes|${r.id}" title="${estadoDisplay}" style="color:#DC2626;font-size:14px;">🗑️</button>
                </div>
            </td>
        `;
        
        return `<tr>${cells}</tr>`;
    }).join('');
    
    return `<div class="table-scroll" style="max-height:60vh;">
        <div style="padding:8px 12px;background:#FFF8F0;border-bottom:1px solid #E5E7EB;font-size:11px;color:#64748B;">
            📋 Vista completa - Todos los campos del cliente (incluye contactos, puntos de entrega y Google Maps)
        </div>
        <table class="master-table" style="min-width:2600px;">
            <thead><tr>${headersHtml}</tr></thead>
            <tbody>${rows}</tbody>
        </table>
    </div>`;
}

// ============================================================
// VISTA COMPLETA - TODOS LOS CAMPOS DEL PROVEEDOR (CON BADGE NUEVO)
// ============================================================

function renderProveedoresCompleta(list) {
    if (!list || !list.length) {
        return `<div class="empty-state">
            <div style="font-size: 48px; margin-bottom: 10px;">📭</div>
            <p style="color: #64748B; font-weight: 500;">No se encontraron registros</p>
        </div>`;
    }
    
    const allFields = [
        { key: 'id', label: 'ID', width: '50px' },
        { key: 'codigo_proveedor', label: 'Código / Proveedor', width: '100px' },
        { key: 'ambito', label: 'Ámbito', width: '90px' },
        { key: 'ruc', label: 'RUC', width: '120px' },
        { key: 'razon_social', label: 'Razón Social', width: '180px' },
        { key: 'razon_comercial', label: 'Razón Comercial', width: '150px' },
        { key: 'direccion', label: 'Dirección', width: '200px' },
        { key: 'contacto', label: 'Contacto', width: '130px' },
        { key: 'telefono', label: 'Teléfono', width: '110px' },
        { key: 'email', label: 'Email', width: '160px' },
        { key: 'contactos', label: 'Contactos', width: '200px' },
        { key: 'puntos_entrega', label: 'Puntos de Entrega', width: '220px' },
        { key: 'condicion_pago', label: 'Condición Pago', width: '100px' },
        { key: 'tiempo_credito', label: 'Tiempo Crédito', width: '80px' },
        { key: 'banco', label: 'Banco', width: '100px' },
        { key: 'numero_cuenta', label: 'N° Cuenta', width: '120px' },
        { key: 'cci', label: 'CCI', width: '130px' },
        { key: 'lugar_recojo', label: 'Lugar Recojo', width: '150px' },
        { key: 'estado', label: 'Estado', width: '90px' },
        { key: 'activo', label: 'Activo', width: '70px' },
        { key: 'observaciones', label: 'Observaciones', width: '150px' },
        { key: 'fecha_creacion', label: 'Creado', width: '110px' }
    ];
    
    let headersHtml = '<th style="width:40px;">Item</th>';
    allFields.forEach(f => {
        headersHtml += `<th style="width:${f.width || 'auto'};text-align:center;">${f.label}</th>`;
    });
    headersHtml += '<th style="width:160px; min-width:160px; text-align:center;">Acciones</th>';
    
    const rows = list.map((r, i) => {
        // ✅ BADGE NUEVO - Usa fecha_creacion
        const badgeHtml = badgeNuevo(r, 'fecha_creacion');
        
        let cells = `<td style="text-align:center;"><b>${i + 1}</b>${badgeHtml}</td>`;
        allFields.forEach(f => {
            let value = r[f.key];
            
            if (value === undefined || value === null || value === '') {
                value = '-';
            } else if (f.key === 'estado') {
                value = bEstado(value);
            } else if (f.key === 'activo') {
                value = value === true || value === 'true' 
                    ? '<span class="badge b-ok">✅ Sí</span>' 
                    : '<span class="badge b-gray">❌ No</span>';
            } else if (f.key === 'ambito') {
                value = bAmbito(value);
            } else if (f.key === 'contactos') {
                if (r.contactos && r.contactos.length > 0) {
                    value = r.contactos.map(c => 
                        `<div style="font-size:10px;padding:2px 0;border-bottom:1px solid #f0f0f0;text-align:left;">
                            <strong>${c.nombre_contacto || '-'}</strong>
                            ${c.cargo ? `<span style="color:#64748B;"> (${c.cargo})</span>` : ''}
                            ${c.principal ? ' ⭐' : ''}
                            <br><small>${c.telefono || ''} ${c.email ? '| ' + c.email : ''}</small>
                        </div>`
                    ).join('');
                } else {
                    value = '-';
                }
            } else if (f.key === 'puntos_entrega') {
                if (r.puntos_entrega && r.puntos_entrega.length > 0) {
                    value = r.puntos_entrega.map(p => 
                        `<div style="font-size:10px;padding:2px 0;border-bottom:1px solid #f0f0f0;text-align:left;">
                            <strong>${p.nombre_punto || '-'}</strong>
                            ${p.principal ? ' ⭐' : ''}
                            <br><small>${p.direccion || ''} ${p.telefono_contacto ? '| Tel: ' + p.telefono_contacto : ''}</small>
                        </div>`
                    ).join('');
                } else {
                    value = '-';
                }
            } else if (f.key === 'fecha_creacion') {
                value = value ? new Date(value).toLocaleDateString('es-PE') : '-';
            }
            
            cells += `<td style="text-align:center;">${value}</td>`;
        });
        
        // Botones de acción
        const isActive = r.estado === 'Activo' || r.estado === 'activo' || r.activo === true;
        const estadoDisplay = isActive ? 'Desactivar' : 'Activar';
        const estadoClass = isActive ? 'action-delete' : 'action-activate';
        
        cells += `
            <td style="text-align:center;">
                <div style="display:flex;gap:4px;justify-content:center;flex-wrap:wrap;">
                    <button class="action-btn action-view" data-view="proveedores|${r.id}" title="Ver">👁️</button>
                    <button class="action-btn action-edit" data-edit="proveedores|${r.id}" title="Editar">✏️</button>
                    <button class="action-btn ${estadoClass}" data-delete="proveedores|${r.id}" title="${estadoDisplay}" style="color:#DC2626;font-size:14px;">🗑️</button>
                </div>
            </td>
        `;
        
        return `<tr>${cells}</tr>`;
    }).join('');
    
    return `<div class="table-scroll" style="max-height:60vh;">
        <div style="padding:8px 12px;background:#FFF8F0;border-bottom:1px solid #E5E7EB;font-size:11px;color:#64748B;">
            📋 Vista completa - Todos los campos del proveedor (incluye contactos y puntos de entrega)
        </div>
        <table class="master-table" style="min-width:2600px;">
            <thead><tr>${headersHtml}</tr></thead>
            <tbody>${rows}</tbody>
        </table>
    </div>`;
}


// ============================================================
// ELIMINAR REGISTRO (DELETE REAL)
// ============================================================

async function eliminarRegistro(modulo, id) {
    try {
        const apiBase = getApiBase(modulo);
        const response = await fetch(`${apiBase}/${modulo}/${id}`, {
            method: 'DELETE'
        });
        
        const result = await response.json();
        
        if (result.success) {
            showToast(`✅ Registro eliminado correctamente`, 'success');
            await loadModuleData(modulo, true);
            renderModule(modulo);
        } else {
            showToast(`❌ Error: ${result.error || 'No se pudo eliminar'}`, 'error');
        }
    } catch (error) {
        console.error('Error eliminando:', error);
        showToast(`❌ Error: ${error.message}`, 'error');
    }
}