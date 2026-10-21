// ============================================================
// MÓDULO VENTAS - ERP Multiempresa
// VERSIÓN COMPLETA Y FUNCIONAL
// ============================================================

console.log('📦 Módulo Ventas cargando...');

// ============================================================
// CONFIGURACIÓN
// ============================================================
const CONFIG = {
    igv: 0.18,
    monedaDefault: 'Soles (S/.)',
    asesorDefault: 'Helen Blas Príncipe',
    emailAsesorDefault: 'ventas@kcfcorporacion.com',
    telefonoAsesorDefault: '999932051',
    validezDefault: '15 días',
    tiempoEntregaDefault: '5 días hábiles'
};

const SUNAT_UNIDADES = [
    {codigo:'NIU',nombre:'Unidad'},
    {codigo:'MTR',nombre:'Metro'},
    {codigo:'KGM',nombre:'Kilogramo'},
    {codigo:'LTR',nombre:'Litro'},
    {codigo:'CJA',nombre:'Caja'},
    {codigo:'PK',nombre:'Paquete'},
    {codigo:'RO',nombre:'Rollo'},
    {codigo:'SET',nombre:'Juego / Set'},
    {codigo:'PAR',nombre:'Par'},
    {codigo:'DZN',nombre:'Docena'}
];

const ESTADOS_COTIZACION = ['Borrador', 'En Proceso', 'Generada', 'Aceptada por Cliente', 'Anulada'];
const ESTADOS_PC = ['Pendiente', 'Recibido por correo', 'En revisión interna', 'Validado ', 'Listo para despacho', 'Anulado'];
const ESTADOS_DESPACHO = ['Pendiente despacho', 'En preparación', 'Despachado', 'Entregado'];
const ESTADOS_GUIA = ['Borrador', 'Pendiente despacho', 'Emitida', 'Entregada', 'Anulada'];
const ESTADOS_COMPROBANTE = ['Borrador', 'Emitido', 'Enviado', 'Pagado', 'Anulado'];
const ESTADOS_NOTA = ['Borrador', 'Emitida', 'Enviada', 'Aplicada', 'Anulada'];
const ESTADOS_DEVOLUCION = ['Pendiente', 'En revisión', 'Aprobada', 'Rechazada', 'Procesada'];

// Agregar al inicio del archivo, en la sección de variables globales
let validationStatus = {
    precios: false,
    cantidades: false,
    stock: false,
    entrega: false,
    moneda: false,
    transporte: false,
    vigencia: false,
    margen: false
};
// ============================================================
// VARIABLES GLOBALES
// ============================================================
let cotizacionesData = [];
let pedidosData = [];
let despachosData = [];
let guiasData = [];
let comprobantesData = [];
let notasData = [];
let devolucionesData = [];
let eliminadasData = []; 
let currentModule = 'cotizaciones';
let editingId = null;
let quoteProducts = [];
let PRODUCTOS_MAESTROS = [];

// ============================================================
// STOCK EN VENTAS (16/10): siempre número sin ceros de relleno (25.00 -> 25)
// y leído en vivo del catálogo (= suma de todas las empresas y sedes del inventario)
// ============================================================
function numStock(v) {
    const n = Number(v);
    return isFinite(n) ? Math.round(n * 100) / 100 : 0;
}
function stockVivo(codigo, respaldo) {
    const p = (PRODUCTOS_MAESTROS || []).find(x => x.codigo && codigo && String(x.codigo) === String(codigo));
    return p ? numStock(p.stock) : numStock(respaldo);
}
// Fecha guardada -> valor para <input type="datetime-local"> (YYYY-MM-DDTHH:MM)
function fechaParaInput(v) {
    if (!v) return '';
    const s = String(v);
    let m = s.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/);
    if (m) return `${m[1]}T${m[2]}`;
    m = s.match(/^(\d{4}-\d{2}-\d{2})$/);
    if (m) return `${m[1]}T00:00`;
    const d = new Date(s);
    if (isNaN(d)) return '';
    // El servidor manda "... GMT" pero la hora guardada ya es la de Lima: se usan los componentes tal cual
    const p2 = n => String(n).padStart(2, '0');
    return `${d.getUTCFullYear()}-${p2(d.getUTCMonth() + 1)}-${p2(d.getUTCDate())}T${p2(d.getUTCHours())}:${p2(d.getUTCMinutes())}`;
}
// Elige la condición de pago aunque esté escrita distinto ("Credito 30 Dias" = "Crédito 30 días")
// El descuento de la cotización se guarda en la cabecera. Para PC, guía y factura se usa el precio
// por producto YA descontado (precio_neto, calculado en el servidor); la edición de la cotización
// sigue usando el precio de lista.
function preciosNetosCotizacion(data) {
    ((data && data.productos) || []).forEach(p => {
        if (p.precio_neto !== undefined && p.precio_neto !== null) {
            if (p.precio_lista === undefined) p.precio_lista = p.valorVenta;
            p.valorVenta = Number(p.precio_neto);
        }
    });
    return data;
}

function setCondicionPagoPC(valor) {
    const sel = document.getElementById('pcCondicion');
    if (!sel) return;
    const norm = t => String(t || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
    const v = window.normalizarCondicion ? window.normalizarCondicion(valor) : (valor || '');
    if (!v) { sel.value = ''; if (typeof pcAvisoCondicion === 'function') pcAvisoCondicion(); return; }
    let opt = Array.from(sel.options).find(o => norm(o.value) === norm(v));
    if (!opt && window.ponerCondicion) { window.ponerCondicion(sel, v); opt = Array.from(sel.options).find(o => norm(o.value) === norm(v)); }
    const custom = document.getElementById('pcCondicionCustom');
    if (opt) {
        sel.value = opt.value;
        if (custom) { custom.value = ''; custom.style.display = 'none'; }
    } else {
        sel.value = 'Personalizado';
        if (custom) { custom.value = v; custom.style.display = 'block'; }
    }
}
let CLIENTES_MAESTROS = [];


// ============================================================
// UTILIDADES
// ============================================================

// ============================================================
// BADGE "NUEVO" CON EXPIRACIÓN DE 24 HORAS (persistido en localStorage)
// ============================================================
const NUEVO_BADGE_DURATION_MS = 24 * 60 * 60 * 1000; // 24 horas

function esRegistroNuevo(fecha) {
    if (!fecha) return false;
    try {
        const f = new Date(fecha);
        if (isNaN(f.getTime())) return false;
        return (Date.now() - f.getTime()) < NUEVO_BADGE_DURATION_MS;
    } catch (e) {
        return false;
    }
}

function badgeNuevo(row, fechaField) {
    if (!esRegistroNuevo(row[fechaField])) return '';
    return ' <span style="display:inline-block;background:#F7FEE7;color:#3F6212;border:1px solid #A3E635;border-radius:20px;padding:1px 9px;font-size:10px;font-weight:800;margin-left:6px;vertical-align:middle;">Nuevo</span>';
}

function getDescripcionPrincipal(r) {
    // Si ya tiene descripción o nota, se respeta tal cual
    if (r.descripcion && r.descripcion.trim() !== '') return r.descripcion;
    if (r.nota_cotizacion && r.nota_cotizacion.trim() !== '') return r.nota_cotizacion;

    // Autocompletar con el primer producto de la cotización (viene del listado)
    if (r.primer_producto && r.primer_producto.trim() !== '') return r.primer_producto;

    // Fallback: si el objeto trae el array completo de productos (ej. cotización cargada completa)
    const productos = r.productos || r.items || [];
    if (productos.length > 0) {
        const primerProducto = productos[0];
        return primerProducto.producto || primerProducto.descripcion || 'Sin descripción';
    }

    return 'Sin descripción';
}

function esc(v) {
    return String(v ?? '').replace(/[&<>"']/g, m => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;',
        '"': '&quot;', "'": '&#039;'
    }[m]));
}

function sd(v) {
    return (v === undefined || v === null || String(v).trim() === '') ? '-' : esc(v);
}

function money(n) {
    // Espacio que no se corta: en tablas angostas "S/" no queda en una línea y el monto en otra
    return 'S/\u00A0' + Number(n || 0).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function now() {
    return new Date().toLocaleString('es-PE', { hour12: false, timeZone: 'America/Lima' });
}

function today() {
    return isoLima();
}

function badgeStatus(s) {
    const estado = String(s || '').trim();
    const estadoLower = estado.toLowerCase();
    
    const map = {
        'borrador': 'b-draft',
        'por validar': 'b-pending',  // 🔽 NUEVO - Color amarillo
        'en revisión': 'b-review',
        'en revision': 'b-review',
        'en proceso': 'b-review',
        'proceso': 'b-review',
        'validado por hellen': 'b-validated',
        'validado': 'b-validated',
        'validada': 'b-validated',
        'generada': 'b-generated',
        'generado': 'b-generated',
        'emitida': 'b-ok',
        'emitido': 'b-ok',
        'despachado': 'b-info',
        'entregado': 'b-info',
        'pendiente despacho': 'b-draft',
        'pendiente': 'b-draft',
        'en preparación': 'b-pending',
        'aceptada por cliente': 'b-accepted',
        'aceptada': 'b-accepted',
        'aceptado': 'b-accepted',
        'aceptado por cliente': 'b-accepted',
        'anulada': 'b-canceled',
        'anulado': 'b-canceled',
        'rechazada': 'b-rejected',
        'rechazado': 'b-rejected',
        'cancelada': 'b-canceled',
        'cancelado': 'b-canceled',
        'no concretada': 'b-lost',
        'no concretado': 'b-lost',
        'perdida': 'b-lost',
        'perdido': 'b-lost'
    };
    
    let clase = map[estadoLower];
    
    if (!clase) {
        if (estadoLower.includes('borrador')) clase = 'b-draft';
        else if (estadoLower.includes('por validar')) clase = 'b-pending';  // 🔽 NUEVO
        else if (estadoLower.includes('revisión') || estadoLower.includes('revision') || estadoLower.includes('proceso')) clase = 'b-review';
        else if (estadoLower.includes('validado')) clase = 'b-validated';
        else if (estadoLower.includes('generada') || estadoLower.includes('generado')) clase = 'b-generated';
        else if (estadoLower.includes('emitida') || estadoLower.includes('emitido')) clase = 'b-ok';
        else if (estadoLower.includes('despachado') || estadoLower.includes('entregado')) clase = 'b-info';
        else if (estadoLower.includes('pendiente despacho') || estadoLower.includes('pendiente')) clase = 'b-draft';
        else if (estadoLower.includes('en preparación')) clase = 'b-pending';
        else if (estadoLower.includes('aceptada') || estadoLower.includes('aceptado')) clase = 'b-accepted';
        else if (estadoLower.includes('anulada') || estadoLower.includes('anulado') || estadoLower.includes('cancelada') || estadoLower.includes('cancelado')) clase = 'b-canceled';
        else if (estadoLower.includes('no concretada') || estadoLower.includes('no concretado') || estadoLower.includes('perdida') || estadoLower.includes('perdido')) clase = 'b-lost';
        else clase = 'b-gray';
    }
    
    return `<span class="badge ${clase}">${estado || 'Sin estado'}</span>`;
}


function options(arr, selected = '') {
    return arr.map(x => `<option value="${x}" ${x === selected ? 'selected' : ''}>${x}</option>`).join('');
}



function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    
    // 🔑 LIMPIAR EDITING ID AL CERRAR EL MODAL DE COTIZACIÓN
    if (modalId === 'cotizacionModal') {
        editingId = null;
        quoteProducts = [];
    }
    
    if (modalId === 'pedidoCompraModal') {
        setTimeout(() => {
            forzarLimpiezaModalPC();
        }, 100);
    }
    
    modal.classList.remove('show');
    modal.style.display = '';
    document.body.style.overflow = '';
}

function empresa() {
    return document.getElementById('empresaActiva')?.value || 'KCF';
}

// ============================================================
// FUNCIÓN PARA FORMATEAR FECHA DE COMPROBANTE (CON HORA)
// ============================================================
function formatearFechaComprobante(fechaStr) {
    if (!fechaStr) return '-';
    
    try {
        let fecha;
        
        // Si es string ISO con T (ej: 2026-08-24T15:31:17.659662)
        if (typeof fechaStr === 'string' && fechaStr.includes('T')) {
            fecha = new Date(fechaStr);
        } 
        // Si es string con formato YYYY-MM-DD (sin hora)
        else if (typeof fechaStr === 'string' && fechaStr.includes('-') && fechaStr.length === 10) {
            fecha = new Date(fechaStr + 'T00:00:00');
        }
        // Otros formatos
        else {
            fecha = new Date(fechaStr);
        }
        
        // Verificar si la fecha es válida
        if (isNaN(fecha.getTime())) {
            return String(fechaStr);
        }
        
        // Formatear: 24/08/2026 15:31
        const dia = String(fecha.getDate()).padStart(2, '0');
        const mes = String(fecha.getMonth() + 1).padStart(2, '0');
        const anio = fecha.getFullYear();
        const horas = String(fecha.getHours()).padStart(2, '0');
        const minutos = String(fecha.getMinutes()).padStart(2, '0');
        
        // Si la hora es 00:00, mostrar solo la fecha
        if (horas === '00' && minutos === '00') {
            return `${dia}/${mes}/${anio}`;
        }
        
        return `${dia}/${mes}/${anio} ${horas}:${minutos}`;
        
    } catch (e) {
        return String(fechaStr);
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

async function apiFetch(url, options = {}) {
    try {
        const response = await fetch(url, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        });
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            // Guía sin stock (20/10/2026): ventana roja grande con qué producto falta
            // Documento duplicado (20/10/2026 22:54): misma ventana roja con el documento que ya existe
            if (['falta_stock', 'duplicado'].includes(errorData.codigo) && errorData.titulo && typeof mostrarErrorStockDespacho === 'function') {
                mostrarErrorStockDespacho(errorData.faltan, errorData.error, errorData.titulo);
            }
            throw new Error(errorData.error || errorData.message || `HTTP ${response.status}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error('❌ API Error:', error);
        throw error;
    }
}

// ============================================================
// FUNCIÓN PARA FORMATEAR FECHA
// ============================================================

function formatFecha(fechaStr) {
    if (!fechaStr) return '-';
    if (window.fechaHoraLima) return window.fechaHoraLima(fechaStr);   // DD/MM/AAAA HH:MM, hora de Lima
    
    try {
        const fecha = new Date(fechaStr);
        if (isNaN(fecha.getTime())) return fechaStr;
        
        // Formato: 08/07/2026 22:48
        const dia = String(fecha.getDate()).padStart(2, '0');
        const mes = String(fecha.getMonth() + 1).padStart(2, '0');
        const anio = fecha.getFullYear();
        const horas = String(fecha.getHours()).padStart(2, '0');
        const minutos = String(fecha.getMinutes()).padStart(2, '0');
        
        return `${dia}/${mes}/${anio} ${horas}:${minutos}`;
    } catch (e) {
        return fechaStr;
    }
}

function formatearFecha(fechaStr) {
    if (!fechaStr) return '-';
    
    try {
        let fecha;
        if (typeof fechaStr === 'string') {
            // Si la fecha viene con formato ISO (YYYY-MM-DDTHH:MM:SS)
            if (fechaStr.includes('T')) {
                fecha = new Date(fechaStr);
            } 
            // Si viene con formato DD/MM/YYYY HH:MM:SS
            else if (fechaStr.includes('/')) {
                const partes = fechaStr.split(/[\/\s:]/);
                if (partes.length >= 3) {
                    // Formato: DD/MM/YYYY HH:MM:SS
                    fecha = new Date(partes[2], partes[1] - 1, partes[0], 
                                    partes[3] || 0, partes[4] || 0, partes[5] || 0);
                } else {
                    fecha = new Date(fechaStr);
                }
            } 
            // Formato YYYY-MM-DD
            else if (fechaStr.includes('-')) {
                fecha = new Date(fechaStr);
            } 
            else {
                fecha = new Date(fechaStr);
            }
        } else if (fechaStr instanceof Date) {
            fecha = fechaStr;
        } else {
            fecha = new Date(fechaStr);
        }
        
        if (isNaN(fecha.getTime())) {
            return String(fechaStr);
        }
        
        const dia = String(fecha.getDate()).padStart(2, '0');
        const mes = String(fecha.getMonth() + 1).padStart(2, '0');
        const anio = fecha.getFullYear();
        const horas = String(fecha.getHours()).padStart(2, '0');
        const minutos = String(fecha.getMinutes()).padStart(2, '0');
        
        return `${dia}/${mes}/${anio} ${horas}:${minutos}`;
        
    } catch (e) {
        return String(fechaStr);
    }
}

async function cargarProductosMaestros() {
    try {
        console.log('🔄 Cargando productos maestros desde base de datos...');
        
        // Usar la ruta correcta del blueprint productos
        const response = await fetch('/productos/api/productos');
        const data = await response.json();
        
        console.log('📦 Respuesta de productos:', data);
        
        if (data.success && data.data && data.data.length > 0) {
            PRODUCTOS_MAESTROS = data.data.map(p => ({
                id: p.id,
                codigo: p.codigo || '',
                producto: p.descripcion || p.nombre || 'Sin nombre',
                descripcion: p.descripcion_larga || p.descripcion || '',
                modelo: p.modelo || '',
                marca: p.marca || '',
                um: p.unidad || 'NIU',
                stock: numStock(p.stock),
                valorVenta: p.precio_unitario || p.precio_venta || 0,
                entrega: p.tiempo_entrega || 'Inmediata',
                // Guardar también para referencia
                precio_unitario: p.precio_unitario,
                costo_unitario: p.costo_unitario
            }));
            console.log(`✅ ${PRODUCTOS_MAESTROS.length} productos cargados desde base de datos`);
            console.log('📋 Primer producto:', PRODUCTOS_MAESTROS[0]);
        } else {
            console.warn('⚠️ No se encontraron productos en la base de datos');
            // Usar datos de ejemplo
            PRODUCTOS_MAESTROS = [
                // Sin productos de ejemplo: si no se pudo leer el catálogo, la lista queda vacía
                
            ];
        }
        
        // Actualizar el datalist
        cargarDatalistProductos();
        
    } catch (error) {
        console.error('❌ Error cargando productos:', error);
        // Datos de ejemplo en caso de error
        PRODUCTOS_MAESTROS = [
            // Sin productos de ejemplo: si no se pudo leer el catálogo, la lista queda vacía
            
        ];
        cargarDatalistProductos();
    }
}



// Función alternativa para cargar productos desde el módulo de productos
async function cargarProductosDesdeModulo() {
    try {
        console.log('🔄 Intentando cargar productos desde módulo productos...');
        const response = await fetch('/productos/api/listar');
        const data = await response.json();
        
        if (data.success && data.data) {
            PRODUCTOS_MAESTROS = data.data.map(p => ({
                id: p.id,
                codigo: p.codigo,
                producto: p.descripcion || p.nombre || 'Sin nombre',
                descripcion: p.descripcion_larga || p.descripcion || '',
                modelo: p.modelo || '',
                marca: p.marca || '',
                um: p.unidad || 'NIU',
                stock: numStock(p.stock),
                valorVenta: p.precio_unitario || p.precio_venta || 0,
                entrega: p.tiempo_entrega || 'Inmediata'
            }));
            console.log(`✅ ${PRODUCTOS_MAESTROS.length} productos cargados desde módulo productos`);
            cargarDatalistProductos();
        }
    } catch (error) {
        console.error('❌ Error cargando desde módulo productos:', error);
        // Si todo falla, usar datos de ejemplo
        PRODUCTOS_MAESTROS = [
            // Sin productos de ejemplo: si no se pudo leer el catálogo, la lista queda vacía
            
        ];
        console.warn('⚠️ Usando productos de ejemplo (fallback)');
        cargarDatalistProductos();
    }
}


async function cargarClientesMaestros() {
    try {
        const response = await fetch('/maestros/api/clientes/listar');
        const data = await response.json();
        if (data.success) {
            CLIENTES_MAESTROS = data.data || [];
        } else {
            // Fallback
            CLIENTES_MAESTROS = [
                {id:1, codigo_cliente:'CLI-000099', ruc:'20114915026', razon_social:'COMPAÑÍA MINERA ANTAPACCAY S.A.', nombre_comercial:'MINERA ANTAPACCAY', contacto:'Compras', telefono:'999 111 222', email:'compras@antapaccay.com', condicion_pago:'Crédito 30 días', direccion:'Av. Industrial 123 - Lima'},
                {id:2, codigo_cliente:'CLI-000082', ruc:'20543722309', razon_social:'CINDEL S.A.', nombre_comercial:'CINDEL', contacto:'María López', telefono:'999 222 333', email:'compras@cindel.com', condicion_pago:'Crédito 45 días', direccion:'Jr. Los Olivos 456 - Lima'}
            ];
        }
        console.log('✅ Clientes cargados:', CLIENTES_MAESTROS.length);
    } catch (error) {
        console.error('Error cargando clientes:', error);
    }
}


async function loadCotizaciones() {
    console.log('🔄 Cargando cotizaciones...');
    try {
        const data = await apiFetch('/ventas/api/cotizaciones/listar');
        if (data.success) {
            cotizacionesData = data.data || [];
            console.log(`✅ ${cotizacionesData.length} cotizaciones cargadas`);
            renderCotizaciones();
            return cotizacionesData;
        } else {
            showToast('Error al cargar cotizaciones: ' + (data.error || 'Error desconocido'), 'error');
            return [];
        }
    } catch (error) {
        console.error('❌ Error cargando cotizaciones:', error);
        showToast('Error al cargar cotizaciones', 'error');
        return [];
    }
}




async function loadPedidos() {
    console.log('🔄 Cargando pedidos...');
    try {
        const data = await apiFetch('/ventas/api/pedido-compra/listar');
        console.log('📦 Datos recibidos en loadPedidos:', data);
        if (data.success) {
            pedidosData = data.data || [];
            console.log(`✅ ${pedidosData.length} pedidos cargados`);
            console.log('📋 Primer pedido:', pedidosData[0]);
            renderPedidos(); // 🔽 Asegurar que se llama a render
        } else {
            showToast('Error al cargar pedidos', 'error');
        }
    } catch (error) {
        console.error('❌ Error cargando pedidos:', error);
        showToast('Error al cargar pedidos: ' + error.message, 'error');
    }
}

async function loadDespachos() {
    console.log('🔄 Cargando despachos...');
    try {
        const data = await apiFetch('/ventas/api/despachos/listar');
        console.log('📦 Datos de despachos:', data);
        
        if (data.success) {
            despachosData = data.data || [];
            console.log(`✅ ${despachosData.length} despachos cargados`);
            
            // 🔽 Verificar las fechas para debug
            despachosData.forEach(d => {
                console.log(`📅 Despacho ${d.numero}: fecha_despacho = ${d.fecha_despacho}`);
            });
            
            renderDespachos();
        } else {
            showToast('Error al cargar despachos', 'error');
        }
    } catch (error) {
        console.error('Error cargando despachos:', error);
        showToast('Error al cargar despachos: ' + error.message, 'error');
    }
}

async function loadGuias() {
    console.log('🔄 Cargando guías...');
    try {
        const data = await apiFetch('/ventas/api/guias/listar');
        console.log('📦 Datos de guías:', data);
        
        if (data.success) {
            guiasData = data.data || [];
            console.log(`✅ ${guiasData.length} guías cargadas`);
            
            // 🔽 Verificar si hay guías nuevas
            guiasData.forEach(g => {
                console.log(`📦 Guía ${g.numero}: estado ${g.estado}, cliente ${g.cliente}`);
            });
            
            renderGuias();
        } else {
            showToast('Error al cargar guías', 'error');
        }
    } catch (error) {
        console.error('Error cargando guías:', error);
        showToast('Error al cargar guías: ' + error.message, 'error');
    }
}

async function loadComprobantes() {
    console.log('🔄 Cargando comprobantes...');
    try {
        const data = await apiFetch('/ventas/api/comprobantes/listar');
        if (data.success) {
            comprobantesData = data.data || [];
            console.log(`✅ ${comprobantesData.length} comprobantes cargados`);
            renderComprobantes();
        } else {
            showToast('Error al cargar comprobantes', 'error');
        }
    } catch (error) {
        console.error('Error cargando comprobantes:', error);
        showToast('Error al cargar comprobantes', 'error');
    }
}

async function loadNotas() {
    console.log('🔄 Cargando notas de crédito...');
    try {
        const data = await apiFetch('/ventas/api/notas-credito/listar');
        if (data.success) {
            notasData = data.data || [];
            console.log(`✅ ${notasData.length} notas cargadas`);
            renderNotas();
        } else {
            showToast('Error al cargar notas de crédito', 'error');
        }
    } catch (error) {
        console.error('Error cargando notas:', error);
        showToast('Error al cargar notas de crédito', 'error');
    }
}

async function loadDevoluciones() {
    console.log('🔄 Cargando devoluciones...');
    try {
        const data = await apiFetch('/ventas/api/devoluciones/listar');
        if (data.success) {
            devolucionesData = data.data || [];
            console.log(`✅ ${devolucionesData.length} devoluciones cargadas`);
            renderDevoluciones();
        } else {
            showToast('Error al cargar devoluciones', 'error');
        }
    } catch (error) {
        console.error('Error cargando devoluciones:', error);
        showToast('Error al cargar devoluciones', 'error');
    }
}

function renderPedidos() {
    const q = document.getElementById('pcSearch')?.value?.toLowerCase() || '';
    const st = document.getElementById('pcStatus')?.value || '';
    
    // Filtro por fechas
    const fechaInicio = document.getElementById('pcFechaInicio')?.value || '';
    const fechaFin = document.getElementById('pcFechaFin')?.value || '';
    
    console.log(`📊 Renderizando pedidos: ${pedidosData?.length || 0} registros`);
    
    if (!pedidosData || pedidosData.length === 0) {
        const tbody = document.getElementById('pcRows');
        const thead = document.getElementById('pedidosTableHead');
        if (thead) {
            if (pedidoViewMode === 'principal') {
                thead.innerHTML = `
                    <tr>
                        <th>Item</th>
                        <th>Fecha / Hora</th>
                        <th>Estado</th>
                        <th>N° PC (pedido de compra)</th>
                        <th>N° cotización</th>
                        <th>Cliente</th>
                        <th>RUC</th>
                        <th>Lugar entrega</th>
                        <th>Descripción</th>
                        <th>Monto (Sin IGV)</th>
                        <th>Monto (Con IGV)</th>
                        <th>Acciones</th>
                    </tr>
                `;
            } else {
                thead.innerHTML = `
                    <tr>
                        <th>Item</th>
                        <th>Fecha / Hora</th>
                        <th>Estado</th>
                        <th>N° PC (pedido de compra)</th>
                        <th>N° cotización</th>
                        <th>Cliente</th>
                        <th>RUC</th>
                        <th>Lugar entrega</th>
                        <th>Descripción</th>
                        <th>Monto (Sin IGV)</th>
                        <th>Monto (Con IGV)</th>
                        <th>Cond. Pago</th>
                        <th>Vendedor</th>
                        <th>Medio</th>
                        <th>Req. Compra</th>
                        <th>Observaciones</th>
                        <th>Validaciones</th>
                        <th>Acciones</th>
                    </tr>
                `;
            }
        }
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="19" style="text-align:center;color:#94A3B8;padding:40px;">
                📭 No hay PC del cliente registrados. 
                <br><small>Crea un PC desde cotización o directo.</small>
            </td></tr>`;
        }
        return;
    }
    
    const list = pedidosData.filter(r => {
        const searchStr = `${r.numero || ''} ${r.oc_cliente || ''} ${r.cliente || ''} ${r.ruc || ''} ${r.cotizacion_numero || ''}`.toLowerCase();
        const matchText = !q || searchStr.includes(q);
        const matchStatus = !st || r.estado === st;
        
        // Filtro por fechas
        let matchFecha = true;
        if (fechaInicio || fechaFin) {
            let fechaPC = r.fecha || r.created_at || '';
            let fechaStr = '';
            try {
                if (typeof fechaPC === 'string') {
                    // Si la fecha tiene formato YYYY-MM-DD HH:MM:SS, extraer solo la fecha
                    if (fechaPC.includes(' ')) {
                        fechaStr = fechaPC.split(' ')[0];
                    } else if (fechaPC.includes('T')) {
                        fechaStr = fechaPC.split('T')[0];
                    } else if (fechaPC.includes('/')) {
                        // Si viene en formato DD/MM/YYYY
                        const partes = fechaPC.split('/');
                        if (partes.length === 3) {
                            fechaStr = `${partes[2]}-${partes[1]}-${partes[0]}`;
                        }
                    } else {
                        fechaStr = fechaPC;
                    }
                }
            } catch (e) {
                fechaStr = '';
            }
            
            if (fechaStr) {
                if (fechaInicio && fechaFin) {
                    matchFecha = fechaStr >= fechaInicio && fechaStr <= fechaFin;
                } else if (fechaInicio) {
                    matchFecha = fechaStr >= fechaInicio;
                } else if (fechaFin) {
                    matchFecha = fechaStr <= fechaFin;
                }
            } else {
                if (fechaInicio || fechaFin) {
                    matchFecha = false;
                }
            }
        }
        
        return matchText && matchStatus && matchFecha;
    });
    
    const tbody = document.getElementById('pcRows');
    const thead = document.getElementById('pedidosTableHead');
    if (!tbody || !thead) return;
    
    // ============================================================
    // 🔽 FUNCIÓN PARA FORMATEAR FECHA SIN CONVERTIR ZONA HORARIA
    // ============================================================
    function formatearFechaSinZona(fechaStr) {
        if (!fechaStr) return '-';
        
        // Si ya está en formato DD/MM/YYYY HH:MM, devolverlo
        if (typeof fechaStr === 'string' && fechaStr.match(/^\d{2}\/\d{2}\/\d{4} \d{2}:\d{2}/)) {
            return fechaStr;
        }
        
        try {
            // Si es string con formato YYYY-MM-DD HH:MM:SS
            if (typeof fechaStr === 'string' && fechaStr.includes(' ') && fechaStr.includes('-')) {
                const partes = fechaStr.split(' ');
                if (partes.length === 2) {
                    const fechaPartes = partes[0].split('-');
                    const horaPartes = partes[1].split(':');
                    if (fechaPartes.length === 3 && horaPartes.length >= 2) {
                        const dia = fechaPartes[2];
                        const mes = fechaPartes[1];
                        const anio = fechaPartes[0];
                        const horas = horaPartes[0];
                        const minutos = horaPartes[1];
                        return `${dia}/${mes}/${anio} ${horas}:${minutos}`;
                    }
                }
            }
            
            // Si es string con formato YYYY-MM-DDTHH:MM:SS
            if (typeof fechaStr === 'string' && fechaStr.includes('T')) {
                const partes = fechaStr.split('T');
                if (partes.length === 2) {
                    const fechaPartes = partes[0].split('-');
                    const horaPartes = partes[1].split(':');
                    if (fechaPartes.length === 3 && horaPartes.length >= 2) {
                        const dia = fechaPartes[2];
                        const mes = fechaPartes[1];
                        const anio = fechaPartes[0];
                        const horas = horaPartes[0];
                        const minutos = horaPartes[1];
                        return `${dia}/${mes}/${anio} ${horas}:${minutos}`;
                    }
                }
            }
            
            // Si es solo fecha YYYY-MM-DD
            if (typeof fechaStr === 'string' && fechaStr.match(/^\d{4}-\d{2}-\d{2}$/)) {
                const partes = fechaStr.split('-');
                return `${partes[2]}/${partes[1]}/${partes[0]}`;
            }
            
            // Fallback: devolver el string original
            return String(fechaStr);
        } catch (e) {
            return String(fechaStr);
        }
    }
    
    // ============================================================
    // VISTA PRINCIPAL - Columnas resumidas
    // ============================================================
    if (pedidoViewMode === 'principal') {
        thead.innerHTML = `
            <tr>
                <th>Item</th>
                <th>Fecha / Hora</th>
                <th>Estado</th>
                <th>N° PC (pedido de compra)</th>
                <th>N° cotización</th>
                <th>Cliente</th>
                <th>RUC</th>
                <th>Lugar entrega</th>
                <th>Descripción</th>
                <th>Monto (Sin IGV)</th>
                <th>Monto (Con IGV)</th>
                <th>Acciones</th>
            </tr>
        `;
        
        if (list.length === 0) {
            tbody.innerHTML = `<tr><td colspan="13" style="text-align:center;color:#94A3B8;padding:40px;">
                📭 No hay PC del cliente que coincidan con los filtros.
                ${pedidosData.length > 0 ? `(${pedidosData.length} registros cargados)` : ''}
            </td></tr>`;
            return;
        }
        
        tbody.innerHTML = list.map((r, i) => {
            const montoSinIgv = parseFloat(r.monto) || 0;
            const montoConIgv = montoSinIgv * 1.18;
            
            const estado = r.estado || 'Pendiente';
            const esObservado = estado === 'PC observado' || estado === 'Bloqueadof' || estado === 'Observado';
            const estadoBadge = esObservado 
                ? '<span class="badge b-draft">🔴 PC observado</span>' 
                : '<span class="badge b-ok">🟢 PC conforme</span>';
            
            // 🔽 USAR formatearFechaSinZona en lugar de formatearFecha
            const fechaDisplay = formatearFechaSinZona(r.fecha || r.created_at);
            
            return `
            <tr class="${pcDespachado(r) ? 'fila-despachada' : ''}">
                <td>${i + 1}</td>
                <td class="date-cell">${fechaDisplay}${tiemposHTML(r)}</td>
                <td>${estadoBadge}${badgeDespachoPc(r)}${pcDespachado(r) ? '' : abastBadge('pc', r.id)}</td>
                <td><b>${r.numero || '-'}</b>${r.oc_cliente ? `<div style="font-size:10px;font-weight:800;color:#1D4ED8;white-space:nowrap" title="N° OC del cliente">OC cliente: ${esc(r.oc_cliente)}</div>` : ''}${badgeNuevo(r, 'created_at')}</td>
                <td>${r.cotizacion_numero || '-'}</td>
                <td class="left"><b>${r.cliente || '-'}</b></td>
                <td>${r.ruc || '-'}</td>
                <td class="left">${r.entrega || r.lugar_entrega || '-'}</td>
                <td class="left">${r.descripcion || r.observaciones || '-'}</td>
                <td><b>${money(montoSinIgv)}</b></td>
                <td><b>${money(montoConIgv)}</b></td>
                <td>
                    <button class="kebab" onclick="showPedidoMenu(event, ${r.id})">⋮</button>
                </td>
            </tr>`;
        }).join('');
        return;
    }
    
    // ============================================================
    // VISTA COMPLETA - Todas las columnas
    // ============================================================
    thead.innerHTML = `
        <tr>
            <th>Item</th>
            <th>Fecha / Hora</th>
            <th>Estado</th>
            <th>N° PC (pedido de compra)</th>
            <th>N° cotización</th>
            <th>Cliente</th>
            <th>RUC</th>
            <th>Lugar entrega</th>
            <th>Descripción</th>
            <th>Monto (Sin IGV)</th>
            <th>Monto (Con IGV)</th>
            <th>Cond. Pago</th>
            <th>Vendedor</th>
            <th>Medio</th>
            <th>Req. Compra</th>
            <th>Observaciones</th>
            <th>Validaciones</th>
            <th>Acciones</th>
        </tr>
    `;
    
    if (list.length === 0) {
        tbody.innerHTML = `<tr><td colspan="19" style="text-align:center;color:#94A3B8;padding:40px;">
            📭 No hay PC del cliente que coincidan con los filtros.
            ${pedidosData.length > 0 ? `(${pedidosData.length} registros cargados)` : ''}
        </td></tr>`;
        return;
    }
    
    tbody.innerHTML = list.map((r, i) => {
        const montoSinIgv = parseFloat(r.monto) || 0;
        const montoConIgv = montoSinIgv * 1.18;
        
        const estado = r.estado || 'Pendiente';
        const esAnulado = estado === 'Anulado';
        const esObservado = estado === 'PC observado' || estado === 'Bloqueado' || estado === 'Observado';
        const estadoBadge = esObservado 
            ? '<span class="badge b-draft">🔴 PC observado</span>' 
            : '<span class="badge b-ok">🟢 PC conforme</span>';
        
        const menuHtml = esAnulado 
            ? `<button class="kebab" onclick="showPedidoMenu(event, ${r.id})" disabled style="opacity:0.5;cursor:not-allowed;">⋮</button>`
            : `<button class="kebab" onclick="showPedidoMenu(event, ${r.id})">⋮</button>`;

        // Construir string de validaciones
        const validaciones = [];
        if (r.valida_precios !== undefined) validaciones.push(`Precio: ${r.valida_precios ? '✅' : '❌'}`);
        if (r.valida_cantidades !== undefined) validaciones.push(`Cantidad: ${r.valida_cantidades ? '✅' : '❌'}`);
        if (r.valida_stock !== undefined) validaciones.push(`Stock: ${r.valida_stock ? '✅' : '❌'}`);
        if (r.valida_entrega !== undefined) validaciones.push(`Entrega: ${r.valida_entrega ? '✅' : '❌'}`);
        if (r.valida_montos !== undefined) validaciones.push(`Montos: ${r.valida_montos ? '✅' : '❌'}`);
        if (r.valida_vigencia !== undefined) validaciones.push(`Vigencia: ${r.valida_vigencia ? '✅' : '❌'}`);
        if (r.valida_margen !== undefined) validaciones.push(`Margen: ${r.valida_margen ? '✅' : '❌'}`);
        
        const validacionesHtml = validaciones.length > 0 
            ? validaciones.join('<br>') 
            : 'Sin validaciones';
        
        // 🔽 USAR formatearFechaSinZona en lugar de formatearFecha
        const fechaDisplay = formatearFechaSinZona(r.fecha || r.created_at);
        
        return `
        <tr class="${pcDespachado(r) ? 'fila-despachada' : ''}">
            <td>${i + 1}</td>
            <td class="date-cell">${fechaDisplay}${tiemposHTML(r)}</td>
            <td>${estadoBadge}${badgeDespachoPc(r)}${pcDespachado(r) ? '' : abastBadge('pc', r.id)}</td>
            <td><b>${r.numero || '-'}</b></td>
            <td>${r.cotizacion_numero || '-'}</td>
            <td class="left"><b>${r.cliente || '-'}</b></td>
            <td>${r.ruc || '-'}</td>
            <td class="left">${r.entrega || r.lugar_entrega || '-'}</td>
            <td class="left">${r.descripcion || r.observaciones || '-'}</td>
            <td><b>${money(montoSinIgv)}</b></td>
            <td><b>${money(montoConIgv)}</b></td>
            <td>${esc(window.normalizarCondicion(r.condicion_pago) || '-')}</td>
            <td>${r.vendedor || '-'}</td>
            <td>${r.medio || '-'}</td>
            <td>${r.req_compra || '-'}</td>
            <td class="left" style="font-size:9px;">${r.observaciones || '-'}</td>
            <td style="font-size:8px; text-align:left;">${validacionesHtml}</td>
            <td>
                ${menuHtml}
            </td>
        </tr>`;
    }).join('');
    
    // Actualizar contador
    const countEl = document.getElementById('pcCount');
    if (countEl) {
        countEl.textContent = `Mostrando ${list.length} de ${pedidosData.length} pedidos`;
    }
}
// ============================================================
// VISTAS DE COTIZACIONES - PRINCIPAL / COMPLETA
// ============================================================

let cotizacionViewMode = 'principal'; // 'principal' o 'completa'

function setCotizacionView(mode) {
    cotizacionViewMode = mode;
    
    // Actualizar clases de los botones
    const principalBtn = document.getElementById('viewPrincipalBtn');
    const completaBtn = document.getElementById('viewCompletaBtn');
    
    if (principalBtn && completaBtn) {
        if (mode === 'principal') {
            principalBtn.className = 'btn btn-view btn-primary-view active';
            principalBtn.style.background = '#EF233C';
            principalBtn.style.color = '#fff';
            principalBtn.style.border = 'none';
            
            completaBtn.className = 'btn btn-view btn-secondary-view';
            completaBtn.style.background = '#F1F5F9';
            completaBtn.style.color = '#475569';
            completaBtn.style.border = '1px solid #E5E7EB';
        } else {
            principalBtn.className = 'btn btn-view btn-secondary-view';
            principalBtn.style.background = '#F1F5F9';
            principalBtn.style.color = '#475569';
            principalBtn.style.border = '1px solid #E5E7EB';
            
            completaBtn.className = 'btn btn-view btn-secondary-view active';
            completaBtn.style.background = '#EF233C';
            completaBtn.style.color = '#fff';
            completaBtn.style.border = 'none';
        }
    }
    
    // Renderizar la tabla con la vista seleccionada
    renderCotizaciones();
}


function renderCotizaciones() {
    const q = document.getElementById('qSearch')?.value?.toLowerCase() || '';
    const st = document.getElementById('qStatus')?.value || '';
    
    // ============================================================
    // 🔽 FILTRO POR FECHAS
    // ============================================================
    const fechaInicio = document.getElementById('qFechaInicio')?.value || '';
    const fechaFin = document.getElementById('qFechaFin')?.value || '';
    
    // ============================================================
    // FILTRO DE ESTADO MEJORADO - Con mapeo flexible
    // ============================================================
    const list = cotizacionesData.filter(r => {
        const searchStr = `${r.numero || ''} ${r.ruc || ''} ${r.razon || ''} ${r.descripcion || ''} ${r.nota_cotizacion || ''}`.toLowerCase();
        const matchText = !q || searchStr.includes(q);
        
        // 🔽 FILTRO POR FECHAS
        let matchFecha = true;
        if (fechaInicio || fechaFin) {
            let fechaCotizacion = r.fecha || r.created_at || '';
            let fechaObj = null;
            try {
                if (typeof fechaCotizacion === 'string') {
                    fechaObj = new Date(fechaCotizacion);
                    if (fechaCotizacion.includes('/')) {
                        const partes = fechaCotizacion.split(/[\/\s:]/);
                        if (partes.length >= 3) {
                            fechaObj = new Date(partes[2], partes[1] - 1, partes[0]);
                        }
                    }
                } else if (fechaCotizacion instanceof Date) {
                    fechaObj = fechaCotizacion;
                }
            } catch (e) {
                fechaObj = null;
            }
            
            if (fechaObj && !isNaN(fechaObj.getTime())) {
                const fechaStr = isoLima(fechaObj);
                if (fechaInicio && fechaFin) {
                    matchFecha = fechaStr >= fechaInicio && fechaStr <= fechaFin;
                } else if (fechaInicio) {
                    matchFecha = fechaStr >= fechaInicio;
                } else if (fechaFin) {
                    matchFecha = fechaStr <= fechaFin;
                }
            }
        }
        
        // 🔽 FILTRO DE ESTADO
        let matchStatus = true;
        if (st) {
            const estadoActual = (r.estado || '').toLowerCase().trim();
            const estadoFiltro = st.toLowerCase().trim();
            
            const estadoMap = {
                'borrador': ['borrador'],
                'en revisión': ['en revisión', 'en revision', 'en proceso', 'proceso'],
                'en proceso': ['en revisión', 'en revision', 'en proceso', 'proceso'],
                'validado por hellen': ['validado por hellen', 'validada por hellen', 'validada', 'validado'],
                'generada': ['generada', 'generado'],
                'aceptada por cliente': ['aceptada por cliente', 'aceptada', 'aceptado', 'aceptado por cliente'],
                'aceptada': ['aceptada por cliente', 'aceptada', 'aceptado', 'aceptado por cliente'],
                'no concretada': ['no concretada', 'no concretado', 'perdida', 'perdido'],
                'anulada': ['anulada', 'anulado', 'cancelada', 'cancelado'],
                'rechazada': ['rechazada', 'rechazado']
            };
            
            const variaciones = estadoMap[estadoFiltro] || [estadoFiltro];
            matchStatus = variaciones.some(v => 
                estadoActual === v || 
                estadoActual.includes(v) || 
                v.includes(estadoActual)
            );
        }
        
        return matchText && matchStatus && matchFecha;
    });
    
    // ============================================================
    // KPIs
   // En renderCotizaciones(), en la sección de KPIs
const kpiContainer = document.getElementById('cotizacionesKPI');
if (kpiContainer) {
    const total = cotizacionesData.length;
    const borradores = cotizacionesData.filter(x => x.estado === 'Borrador').length;
    const porValidar = cotizacionesData.filter(x => x.estado === 'Por validar').length;  // 🔽 NUEVO
    const generadas = cotizacionesData.filter(x => x.estado === 'Generada').length;
    const aceptadas = cotizacionesData.filter(x => x.estado === 'Aceptada por Cliente' || x.estado === 'Aceptada').length;
    const rechazadas = cotizacionesData.filter(x => x.estado === 'Rechazada').length;
    
    kpiContainer.innerHTML = `
        <div class="status-card"><div class="status-dot dot-total-plomo">T</div><div><small>Total</small><b>${total}</b></div></div>
        <div class="status-card"><div class="status-dot dot-draft">B</div><div><small>Borradores</small><b>${borradores}</b></div></div>
        <div class="status-card"><div class="status-dot dot-pending">⭐</div><div><small>Por validar</small><b>${porValidar}</b></div></div>
        <div class="status-card"><div class="status-dot dot-send">E</div><div><small>Generadas</small><b>${generadas}</b></div></div>
        <div class="status-card"><div class="status-dot dot-ok">A</div><div><small>Aceptadas</small><b>${aceptadas}</b></div></div>
        <div class="status-card"><div class="status-dot dot-rechazada">R</div><div><small>Rechazadas</small><b>${rechazadas}</b></div></div>
    `;
}
    
    const tbody = document.getElementById('qRows');
    const thead = document.getElementById('cotizacionesTableHead');
    if (!tbody || !thead) return;
    
   // ============================================================
// VISTA PRINCIPAL - Columnas resumidas
// ============================================================
if (cotizacionViewMode === 'principal') {
    thead.innerHTML = `
        <tr>
            <th>Item</th>
            <th>Fecha / Hora</th>
            <th>Estado</th>
            <th>N° cotización</th>
            <th>Código de cliente</th>
            <th>Razón social (Cliente)</th>
            <th>RUC</th>
            <th>Descripción principal</th>
            <th>Monto total<br><small>(Sin IGV)</small></th>
            <th>Monto total<br><small>(Incluido IGV)</small></th>
            <th>Cond. pago</th>
            <th>Acciones</th>
        </tr>
    `;
    
    if (list.length === 0) {
        tbody.innerHTML = `<tr><td colspan="12" style="text-align:center;color:#94A3B8;padding:40px;">📭 No hay cotizaciones que coincidan con los filtros</td></tr>`;
        return;
    }
    
    tbody.innerHTML = list.map((r, i) => {
        const totalConIgv = r.total || r.monto || 0;
        const totalSinIgv = totalConIgv / 1.18;
        
        return `
        <tr>
            <td><b>${i + 1}</b></td>
            <td class="date-cell">${formatFecha(r.fecha)}${tiemposHTML(r)}</td>
            <td>${badgeStatus(r.estado)}${cotAceptadaCliente(r) ? abastBadge('cotizaciones', r.id) : ''}</td>
            <td class="quote-number-cell"><b>${sd(r.numero)}</b>${badgeNuevo(r, 'fecha')}</td>
            <td><span class="code-pill">${sd(r.cod_cliente)}</span></td>
            <td class="left"><b>${sd(r.razon)}</b></td>
            <td>${sd(r.ruc)}</td>
            <td class="left">${sd(getDescripcionPrincipal(r))}</td>
            <td><b>${money(totalSinIgv)}</b></td>
            <td><b>${money(totalConIgv)}</b></td>
            <td>${sd(window.normalizarCondicion(r.condicion || r.condicion_pago || r.forma_pago))}</td>
            <td>
                <button class="kebab" onclick="showCotizacionMenu(event, ${r.id})">⋮</button>
            </td>
        </tr>`;
    }).join('');
    return;
}
    
    // ============================================================
    // VISTA COMPLETA - Todas las columnas
    // ============================================================
    thead.innerHTML = `
        <tr>
            <th>Item</th>
            <th>Fecha / Hora</th>
            <th>Estado</th>
            <th>N° cotización</th>
            <th>Código de cliente</th>
            <th>Razón social (Cliente)</th>
            <th>RUC</th>
            <th>Contacto</th>
            <th>Teléfono</th>
            <th>Email</th>
            <th>Descripción</th>
            <th>Subtotal</th>
            <th>IGV</th>
            <th>Total<br><small>(Incluido IGV)</small></th>
            <th>Cond. Pago</th>
            <th>Tiempo Entrega</th>
            <th>Validez</th>
            <th>Lugar entrega</th>
            <th>Requerimiento</th>
            <th>Nota Comercial</th>
            <th>Seguimiento</th>
            <th>Motivo</th>
            <th>Transporte</th>
            <th>Parihuela</th>
            <th>Nota Interna</th>
            <th># Productos</th>
            <th>Acciones</th>
        </tr>
    `;
    
    if (list.length === 0) {
        tbody.innerHTML = `<tr><td colspan="28" style="text-align:center;color:#94A3B8;padding:40px;">📭 No hay cotizaciones que coincidan con los filtros</td></tr>`;
        return;
    }
    
    tbody.innerHTML = list.map((r, i) => {
        const numProductos = r.productos?.length || r.items?.length || 0;
        return `
        <tr>
            <td><b>${i + 1}</b></td>
            <td class="date-cell">${formatFecha(r.fecha)}${tiemposHTML(r)}</td>
            <td>${badgeStatus(r.estado)}${cotAceptadaCliente(r) ? abastBadge('cotizaciones', r.id) : ''}</td>
            <td class="quote-number-cell"><b>${sd(r.numero)}</b></td>
            <td><span class="code-pill">${sd(r.cod_cliente)}</span></td>
            <td class="left"><b>${sd(r.razon)}</b></td>
            <td>${sd(r.ruc)}</td>
            <td>${sd(r.contacto || r.cliente_contacto || r.contacto_cliente)}</td>
            <td>${sd(r.telefono || r.cliente_telefono || r.telefono_cliente)}</td>
            <td>${sd(r.email || r.cliente_email || r.email_cliente)}</td>
            <td class="left">${sd(r.descripcion || r.nota_cotizacion || r.notas || 'Sin descripción')}</td>
            <td><b>${money(r.subtotal || 0)}</b></td>
            <td><b>${money(r.igv || 0)}</b></td>
            <td><b>${money(r.total || r.monto || 0)}</b></td>
            <td>${sd(window.normalizarCondicion(r.condicion || r.condicion_pago || r.forma_pago))}</td>
            <td>${sd(r.tiempo_entrega)}</td>
            <td>${sd(r.validez || r.validez_oferta)}</td>
            <td class="left">${sd(r.direccion_entrega)}</td>
            <td>${sd(r.requerimiento)}</td>
            <td class="left">${sd(r.nota_comercial || r.nota_cotizacion)}</td>
            <td>${sd(r.seguimiento || 'Asesor')}</td>
            <td>${sd(r.motivo || 'Proyecto nuevo')}</td>
            <td>${sd(r.transporte || 'Seleccione')}</td>
            <td>${sd(r.parihuela || 'Seleccione')}</td>
            <td class="left">${sd(r.nota_interna)}</td>
            <td style="text-align:center; font-weight:900;">${numProductos}</td>
            <td>
                <button class="kebab" onclick="showCotizacionMenu(event, ${r.id})">⋮</button>
            </td>
        </tr>`;
    }).join('');
}


// ============================================================
// VISTAS DE PEDIDOS - PRINCIPAL / COMPLETA
// ============================================================

let pedidoViewMode = 'principal'; // 'principal' o 'completa'

function setPedidoView(mode) {
    pedidoViewMode = mode;
    
    // Actualizar clases de los botones
    const principalBtn = document.getElementById('pcViewPrincipalBtn');
    const completaBtn = document.getElementById('pcViewCompletaBtn');
    
    if (principalBtn && completaBtn) {
        if (mode === 'principal') {
            principalBtn.className = 'btn btn-view btn-primary-view active';
            principalBtn.style.background = '#EF233C';
            principalBtn.style.color = '#fff';
            principalBtn.style.border = 'none';
            
            completaBtn.className = 'btn btn-view btn-secondary-view';
            completaBtn.style.background = '#F1F5F9';
            completaBtn.style.color = '#475569';
            completaBtn.style.border = '1px solid #E5E7EB';
        } else {
            principalBtn.className = 'btn btn-view btn-secondary-view';
            principalBtn.style.background = '#F1F5F9';
            principalBtn.style.color = '#475569';
            principalBtn.style.border = '1px solid #E5E7EB';
            
            completaBtn.className = 'btn btn-view btn-secondary-view active';
            completaBtn.style.background = '#EF233C';
            completaBtn.style.color = '#fff';
            completaBtn.style.border = 'none';
        }
    }
    
    // Renderizar la tabla con la vista seleccionada
    renderPedidos();
}

// Entregas (18:09): estado de la compra, guía/factura juntas, fecha de cita, "Generar compra" y factura sin stock
function estadoCompraHTML(r, despachado, anulado) {
    if (anulado) return '-';
    if (despachado) return '<span class="compra-est compra-ok">✔ Comprado</span>';
    const info = (abastData.despachos || {})[r.id];
    if (!info || !info.estado) return '<small title="Sus productos no están en el catálogo o aún se está calculando">-</small>';
    const titulo = (info.detalle || []).join('\n').replace(/"/g, '&quot;');
    const t = {
        'Con stock': ['compra-ok', '✔ Comprado / en stock'],
        'Por llegar': ['compra-camino', '📦 Comprado, por llegar'],
        'Pendiente por recojo': ['compra-camino', '🚚 Comprado, por recoger'],
        'Pendiente por compra': ['compra-falta', '🛒 Pendiente de compra']
    }[info.estado] || ['compra-camino', info.estado];
    return `<span class="compra-est ${t[0]}" title="${titulo}">${t[1]}</span>`;
}
function guiaFacturaDespachoHTML(r) {
    const g = r.guia ? `<div><small>Guía</small><br><b>${sd(r.guia)}</b></div>` : '';
    const f = r.comprobante ? `<div style="margin-top:3px"><small>Factura</small><br><b>${sd(r.comprobante)}</b></div>` : '';
    return g || f ? g + f : '-';
}
function citaDespachoHTML(r, cerrado) {
    let txt = '';
    if (r.fecha_cita) {
        const d = new Date(String(r.fecha_cita).replace(' ', 'T'));
        txt = isNaN(d) ? String(r.fecha_cita) : d.toLocaleString('es-PE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
    }
    if (cerrado) return txt ? `<b>${txt}</b>` : '-';
    return `<button class="cita-btn ${txt ? 'tiene' : ''}" onclick="ponerCitaDespacho(${r.id})" title="Fecha y hora acordadas con el cliente para la entrega">📅 ${txt || 'Poner cita'}</button>`;
}
function ponerCitaDespacho(id) {
    const r = (despachosData || []).find(x => x.id === id);
    if (!r) return;
    document.getElementById('citaDespachoModal')?.remove();
    const actual = r.fecha_cita ? String(r.fecha_cita).replace(' ', 'T').slice(0, 16) : '';
    const d = document.createElement('div');
    d.id = 'citaDespachoModal';
    d.style.cssText = 'position:fixed;inset:0;background:rgba(15,23,42,.55);z-index:10000002;display:flex;align-items:center;justify-content:center;padding:16px';
    d.innerHTML = `<div style="background:#fff;border-radius:14px;max-width:420px;width:100%;padding:20px;box-shadow:0 20px 60px rgba(0,0,0,.35)">
        <div style="font-size:18px;font-weight:900;margin-bottom:4px">📅 Fecha de cita con el cliente</div>
        <div style="font-size:13px;color:#475569;margin-bottom:12px">${sd(r.numero)} · ${sd(r.cliente)}</div>
        <input type="datetime-local" id="citaDespachoValor" value="${actual}" style="width:100%;height:40px;border:2px solid #CBD5E1;border-radius:10px;padding:0 10px;font-size:15px;font-weight:700">
        <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px;flex-wrap:wrap">
          ${actual ? '<button type="button" data-acc="quitar" style="padding:9px 14px;border-radius:10px;border:1px solid #FCA5A5;background:#fff;color:#B91C1C;font-weight:800;cursor:pointer">Quitar cita</button>' : ''}
          <button type="button" data-acc="cancelar" style="padding:9px 14px;border-radius:10px;border:1px solid #CBD5E1;background:#fff;font-weight:800;cursor:pointer">Cancelar</button>
          <button type="button" data-acc="guardar" style="padding:9px 16px;border-radius:10px;border:0;background:#16A34A;color:#fff;font-weight:900;cursor:pointer">💾 Guardar</button>
        </div></div>`;
    document.body.appendChild(d);
    const guardar = async valor => {
        try {
            const res = await apiFetch(`/ventas/api/despachos/${id}/cita`, { method: 'POST', body: JSON.stringify({ fecha_cita: valor }) });
            r.fecha_cita = res.data ? res.data.fecha_cita : valor;
            d.remove();
            showToast(valor ? '✅ Cita guardada' : '✅ Cita quitada', 'success');
            renderDespachos();
        } catch (e) { showToast('❌ ' + e.message, 'error'); }
    };
    d.addEventListener('click', e => {
        const acc = e.target.dataset && e.target.dataset.acc;
        if (e.target === d || acc === 'cancelar') d.remove();
        else if (acc === 'quitar') guardar('');
        else if (acc === 'guardar') {
            const v = document.getElementById('citaDespachoValor').value;
            if (!v) { showToast('⚠️ Elige la fecha y la hora de la cita', 'warning'); return; }
            guardar(v);
        }
    });
}
function generarCompraDesdeDespacho(id) {
    const r = (despachosData || []).find(x => x.id === id);
    if (!r || !r.pc_numero) return;
    window.location.href = '/compras?tab=pedidos&pc=' + encodeURIComponent(r.pc_numero);
}
async function facturaDesdeDespacho(id) {
    const r = (despachosData || []).find(x => x.id === id);
    if (!r) return;
    switchTab('comprobantes');
    await openComprobanteModal();
    setTimeout(() => {
        const pcSel = document.getElementById('compPC');
        const cotSel = document.getElementById('compCotizacion');
        if (r.pc_numero && pcSel && [...pcSel.options].some(o => o.value === r.pc_numero)) {
            pcSel.value = r.pc_numero;
            window.loadComprobanteFromPC(r.pc_numero);
        } else if (r.cotizacion_numero && cotSel && [...cotSel.options].some(o => o.value === r.cotizacion_numero)) {
            cotSel.value = r.cotizacion_numero;
            window.cargarProductosComprobanteDesdeCotizacion(r.cotizacion_numero);
        } else {
            const ruc = document.getElementById('compRuc'), cli = document.getElementById('compCliente');
            if (ruc && !ruc.value) { ruc.value = r.ruc || ''; ruc.dispatchEvent(new Event('change', { bubbles: true })); }
            if (cli && !cli.value) cli.value = r.cliente || '';
        }
        showToast('🧾 Factura del despacho ' + (r.numero || '') + ': se puede emitir aunque todavía no haya stock', 'info');
    }, 400);
}
window.ponerCitaDespacho = ponerCitaDespacho;
window.generarCompraDesdeDespacho = generarCompraDesdeDespacho;
window.facturaDesdeDespacho = facturaDesdeDespacho;

// Entregas (pedido de Erika 20/10/2026): lo pendiente en rojo encendido, lo terminado en verde fluorescente.
// Solo cambia lo que se ve; en la base el estado sigue siendo "Pendiente despacho" / "Despachado".
function estadoDespachoHTML(estado) {
    const e = estado || 'Pendiente despacho';
    if (e === 'Despachado' || e === 'Entregado') return `<span class="desp-hecho">✔ ${e}</span>`;
    if (/pendiente/i.test(e)) return '<span class="desp-por">⏳ Por despachar</span>';
    if (/preparaci/i.test(e)) return '<span class="desp-por">📦 En preparación</span>';
    return badgeStatus(e);
}
window.estadoDespachoHTML = estadoDespachoHTML;

function renderDespachos() {
    const q = document.getElementById('despachoSearch')?.value?.toLowerCase() || '';
    const st = document.getElementById('despachoStatus')?.value || '';
    
    // 🔽 FILTRO POR FECHAS
    const fechaInicio = document.getElementById('despachoFechaInicio')?.value || '';
    const fechaFin = document.getElementById('despachoFechaFin')?.value || '';
    
    const list = despachosData.filter(r => {
        const searchStr = `${r.numero || ''} ${r.cliente || ''} ${r.pc_numero || ''} ${r.destino || ''}`.toLowerCase();
        const matchText = !q || searchStr.includes(q);
        const matchStatus = !st || r.estado === st;
        
        // 🔽 FILTRO POR FECHAS
        let matchFecha = true;
        if (fechaInicio || fechaFin) {
            let fechaDespacho = r.fecha_despacho || r.fecha || r.created_at || '';
            let fechaObj = null;
            try {
                if (typeof fechaDespacho === 'string') {
                    fechaObj = new Date(fechaDespacho);
                    if (fechaDespacho.includes('/')) {
                        const partes = fechaDespacho.split(/[\/\s:]/);
                        if (partes.length >= 3) {
                            fechaObj = new Date(partes[2], partes[1] - 1, partes[0]);
                        }
                    }
                } else if (fechaDespacho instanceof Date) {
                    fechaObj = fechaDespacho;
                }
            } catch (e) {
                fechaObj = null;
            }
            
            if (fechaObj && !isNaN(fechaObj.getTime())) {
                const fechaStr = isoLima(fechaObj);
                if (fechaInicio && fechaFin) {
                    matchFecha = fechaStr >= fechaInicio && fechaStr <= fechaFin;
                } else if (fechaInicio) {
                    matchFecha = fechaStr >= fechaInicio;
                } else if (fechaFin) {
                    matchFecha = fechaStr <= fechaFin;
                }
            } else {
                if (fechaInicio || fechaFin) {
                    matchFecha = false;
                }
            }
        }
        
        return matchText && matchStatus && matchFecha;
    });
    
    const tbody = document.getElementById('despachoRows');
    if (!tbody) return;
    
    if (list.length === 0) {
        tbody.innerHTML = `<tr><td colspan="10" style="text-align:center;color:#94A3B8;padding:40px;">📭 No hay despachos registrados</td></tr>`;
        return;
    }
    
    tbody.innerHTML = list.map((r, i) => {
        let fechaDisplay = '-';
        const fechaRaw = r.fecha_despacho || r.fecha || r.created_at;
        
        if (fechaRaw) {
            try {
                let fecha = new Date(fechaRaw);
                if (!isNaN(fecha.getTime())) {
                    const dia = String(fecha.getDate()).padStart(2, '0');
                    const mes = String(fecha.getMonth() + 1).padStart(2, '0');
                    const anio = fecha.getFullYear();
                    const horas = String(fecha.getHours()).padStart(2, '0');
                    const minutos = String(fecha.getMinutes()).padStart(2, '0');
                    fechaDisplay = `${dia}/${mes}/${anio} ${horas}:${minutos}`;
                } else {
                    fechaDisplay = String(fechaRaw);
                }
            } catch (e) {
                fechaDisplay = String(fechaRaw);
            }
        }
        
        const despachado = r.estado === 'Despachado' || r.estado === 'Entregado';
        const anulado = /anulad/i.test(r.estado || '');
        const compra = ((abastData.despachos || {})[r.id] || {}).estado;
        // Fila entera: rosado bajito si falta despachar, verde bajito si ya salió (Erika 20/10/2026 18:09)
        return `
        <tr class="${despachado ? 'ent-despachado' : (anulado ? 'ent-anulado' : 'ent-pendiente')}">
            <td>${i + 1}</td>
            <td class="date-cell">${fechaDisplay}${tiemposHTML(r)}</td>
            <td>${estadoDespachoHTML(r.estado)}</td>
            <td><b>${sd(r.numero)}</b>${badgeNuevo(r, 'fecha')}</td>
            <td>${sd(r.pc_numero)}</td>
            <td>${sd(r.cotizacion_numero)}</td>
            <td class="left">${sd(r.cliente)}</td>
            <td>${guiaFacturaDespachoHTML(r)}</td>
            <td>${sd(r.destino)}</td>
            <td>${estadoCompraHTML(r, despachado, anulado)}</td>
            <td>${citaDespachoHTML(r, despachado || anulado)}</td>
            <td><div class="acc-col">
                ${!despachado && !anulado ? `
                    ${compra === 'Pendiente por compra' && r.pc_numero ? `<button class="btn-generar-compra" onclick="generarCompraDesdeDespacho(${r.id})" title="Abre Compras con este pedido ya cargado para hacer la orden de compra">Generar compra</button>` : ''}
                    <button class="btn-confirmar-despacho" onclick="marcarDespachado(${r.id})" title="Pendiente: confirma cuando la mercadería ya salió del almacén">Confirmar despacho</button>
                    ${!r.comprobante ? `<button class="btn-factura-desp" onclick="facturaDesdeDespacho(${r.id})" title="La factura se puede hacer aunque todavía no haya stock">Generar factura</button>` : ''}` :
                  despachado ? `<span class="desp-hecho">${r.estado === 'Entregado' ? 'Entregado' : 'Despachado'}</span>
                     <button class="btn-anular-despacho" onclick="anularDespacho(${r.id})" title="Anular: el stock vuelve al inventario">Anular</button>` : ''
                }
                <button class="btn-rotulo" onclick="imprimirRotulo('despacho', ${r.id})" title="Rótulo para pegar en cada caja, con los datos de la empresa">Generar rótulo</button>
            </div></td>
        </tr>`;
    }).join('');
}
// ============================================================
// 🔽 FUNCIÓN PARA FORMATEAR FECHA DE DESPACHO (CON HORA)
// ============================================================
function formatearFechaDespacho(fechaStr) {
    if (!fechaStr) return '-';
    
    try {
        let fecha;
        
        // Si es string, intentar parsear
        if (typeof fechaStr === 'string') {
            // Si viene con formato ISO completo (2026-07-20T14:30:00.000Z)
            if (fechaStr.includes('T')) {
                fecha = new Date(fechaStr);
            }
            // Si viene con formato YYYY-MM-DD (sin hora)
            else if (fechaStr.includes('-') && fechaStr.length === 10) {
                fecha = new Date(fechaStr + 'T00:00:00');
            }
            // Si viene con formato DD/MM/YYYY HH:MM
            else if (fechaStr.includes('/') && fechaStr.includes(':')) {
                const partes = fechaStr.split(' ');
                const fechaParts = partes[0].split('/');
                const horaParts = partes[1].split(':');
                if (fechaParts.length === 3 && horaParts.length >= 2) {
                    fecha = new Date(
                        parseInt(fechaParts[2]),
                        parseInt(fechaParts[1]) - 1,
                        parseInt(fechaParts[0]),
                        parseInt(horaParts[0]),
                        parseInt(horaParts[1])
                    );
                } else {
                    fecha = new Date(fechaStr);
                }
            }
            // Si viene solo con formato DD/MM/YYYY (sin hora)
            else if (fechaStr.includes('/')) {
                const partes = fechaStr.split('/');
                if (partes.length === 3) {
                    fecha = new Date(partes[2], partes[1] - 1, partes[0]);
                } else {
                    fecha = new Date(fechaStr);
                }
            }
            else {
                fecha = new Date(fechaStr);
            }
        } else if (fechaStr instanceof Date) {
            fecha = fechaStr;
        } else {
            fecha = new Date(fechaStr);
        }
        
        // Verificar si la fecha es válida
        if (isNaN(fecha.getTime())) {
            return String(fechaStr);
        }
        
        // Formatear: 20/07/2026 14:30
        const dia = String(fecha.getDate()).padStart(2, '0');
        const mes = String(fecha.getMonth() + 1).padStart(2, '0');
        const anio = fecha.getFullYear();
        const horas = String(fecha.getHours()).padStart(2, '0');
        const minutos = String(fecha.getMinutes()).padStart(2, '0');
        
        // Si la hora es 00:00, mostrar solo la fecha
        if (horas === '00' && minutos === '00') {
            return `${dia}/${mes}/${anio}`;
        }
        
        return `${dia}/${mes}/${anio} ${horas}:${minutos}`;
        
    } catch (e) {
        return String(fechaStr);
    }
}

// ============================================================
// 🔽 FUNCIÓN PARA FORMATEAR FECHA DE DESPACHO
// ============================================================
function formatearFechaDespacho(fechaStr) {
    if (!fechaStr) return '-';
    
    try {
        let fecha;
        
        // Si es string, intentar parsear
        if (typeof fechaStr === 'string') {
            // Si viene con formato ISO (Mon, 20 Jul 2026 00:00:00 GMT)
            if (fechaStr.includes('GMT') || fechaStr.includes('UTC')) {
                fecha = new Date(fechaStr);
            }
            // Si viene con formato ISO (2026-07-20T00:00:00.000Z)
            else if (fechaStr.includes('T')) {
                fecha = new Date(fechaStr);
            }
            // Si viene con formato YYYY-MM-DD
            else if (fechaStr.includes('-') && fechaStr.length === 10) {
                fecha = new Date(fechaStr + 'T00:00:00');
            }
            // Si viene con formato DD/MM/YYYY
            else if (fechaStr.includes('/')) {
                const partes = fechaStr.split('/');
                if (partes.length === 3) {
                    fecha = new Date(partes[2], partes[1] - 1, partes[0]);
                } else {
                    fecha = new Date(fechaStr);
                }
            }
            else {
                fecha = new Date(fechaStr);
            }
        } else if (fechaStr instanceof Date) {
            fecha = fechaStr;
        } else {
            // Si es timestamp (número)
            fecha = new Date(fechaStr);
        }
        
        // Verificar si la fecha es válida
        if (isNaN(fecha.getTime())) {
            return String(fechaStr);
        }
        
        // Formatear: 20/07/2026 14:30
        const dia = String(fecha.getDate()).padStart(2, '0');
        const mes = String(fecha.getMonth() + 1).padStart(2, '0');
        const anio = fecha.getFullYear();
        const horas = String(fecha.getHours()).padStart(2, '0');
        const minutos = String(fecha.getMinutes()).padStart(2, '0');
        
        return `${dia}/${mes}/${anio} ${horas}:${minutos}`;
        
    } catch (e) {
        return String(fechaStr);
    }
}


// ============================================================
// FUNCIÓN PARA FORMATEAR FECHA DE GUÍA (CON HORA)
// ============================================================

function formatearFechaGuia(fechaStr) {
    if (!fechaStr) return '-';
    
    try {
        // Si es un string con formato "YYYY-MM-DD HH:MM:SS"
        if (typeof fechaStr === 'string' && fechaStr.includes(' ') && fechaStr.match(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/)) {
            // Extraer directamente fecha y hora sin conversión de zona horaria
            const partes = fechaStr.split(' ');
            const fechaPartes = partes[0].split('-');
            const horaPartes = partes[1].split(':');
            
            const dia = fechaPartes[2];
            const mes = fechaPartes[1];
            const anio = fechaPartes[0];
            const horas = horaPartes[0];
            const minutos = horaPartes[1];
            
            return `${dia}/${mes}/${anio} ${horas}:${minutos}`;
        }
        
        // Si es "YYYY-MM-DD" (solo fecha)
        if (typeof fechaStr === 'string' && fechaStr.match(/^\d{4}-\d{2}-\d{2}$/)) {
            const partes = fechaStr.split('-');
            return `${partes[2]}/${partes[1]}/${partes[0]}`;
        }
        
        // Para otros formatos, usar Date pero sin convertir zona horaria
        let fecha = new Date(fechaStr);
        if (isNaN(fecha.getTime())) {
            return String(fechaStr);
        }
        
        // Si la hora es 00:00, mostrar solo fecha
        if (fecha.getHours() === 0 && fecha.getMinutes() === 0) {
            const dia = String(fecha.getDate()).padStart(2, '0');
            const mes = String(fecha.getMonth() + 1).padStart(2, '0');
            const anio = fecha.getFullYear();
            return `${dia}/${mes}/${anio}`;
        }
        
        // Para fechas con hora, mostrar fecha y hora
        const dia = String(fecha.getDate()).padStart(2, '0');
        const mes = String(fecha.getMonth() + 1).padStart(2, '0');
        const anio = fecha.getFullYear();
        const horas = String(fecha.getHours()).padStart(2, '0');
        const minutos = String(fecha.getMinutes()).padStart(2, '0');
        
        return `${dia}/${mes}/${anio} ${horas}:${minutos}`;
        
    } catch (e) {
        return String(fechaStr);
    }
}


function renderGuias() {
    const q = document.getElementById('guiaSearch')?.value?.toLowerCase() || '';
    const st = document.getElementById('guiaStatus')?.value || '';
    
    // 🔽 FILTRO POR FECHAS
    const fechaInicio = document.getElementById('guiaFechaInicio')?.value || '';
    const fechaFin = document.getElementById('guiaFechaFin')?.value || '';
    
    const list = guiasData.filter(r => {
        const searchStr = `${r.numero || ''} ${r.serie || ''} ${r.cliente || ''} ${r.ruc || ''} ${r.cotizacion || ''} ${r.pc_numero || ''} ${r.comprobante || ''}`.toLowerCase();
        const matchText = !q || searchStr.includes(q);
        const matchStatus = !st || r.estado === st;
        
        // 🔽 FILTRO POR FECHAS
        let matchFecha = true;
        if (fechaInicio || fechaFin) {
            let fechaGuia = r.fecha || r.created_at || '';
            let fechaObj = null;
            try {
                if (typeof fechaGuia === 'string') {
                    fechaObj = new Date(fechaGuia);
                    if (fechaGuia.includes('/')) {
                        const partes = fechaGuia.split(/[\/\s:]/);
                        if (partes.length >= 3) {
                            fechaObj = new Date(partes[2], partes[1] - 1, partes[0]);
                        }
                    }
                } else if (fechaGuia instanceof Date) {
                    fechaObj = fechaGuia;
                }
            } catch (e) {
                fechaObj = null;
            }
            
            if (fechaObj && !isNaN(fechaObj.getTime())) {
                const fechaStr = isoLima(fechaObj);
                if (fechaInicio && fechaFin) {
                    matchFecha = fechaStr >= fechaInicio && fechaStr <= fechaFin;
                } else if (fechaInicio) {
                    matchFecha = fechaStr >= fechaInicio;
                } else if (fechaFin) {
                    matchFecha = fechaStr <= fechaFin;
                }
            } else {
                if (fechaInicio || fechaFin) {
                    matchFecha = false;
                }
            }
        }
        
        return matchText && matchStatus && matchFecha;
    });
    
    const tbody = document.getElementById('guiaRows');
    if (!tbody) return;
    
    if (list.length === 0) {
        tbody.innerHTML = `<tr><td colspan="12" style="text-align:center;color:#94A3B8;padding:40px;">📭 No hay guías registradas</td></tr>`;
        return;
    }
    
    tbody.innerHTML = list.map((r, i) => `
        <tr>
            <td>${i + 1}</td>
            <td class="date-cell">${formatearFechaGuia(r.fecha)}${tiemposHTML(r)}</td>
            <td>${badgeStatus(r.estado)}</td>
            <td><b>${sd(r.serie)}-${sd(r.numero)}</b>${badgeNuevo(r, 'fecha')}</td>
            <td class="left">${sd(r.cliente)}</td>
            <td>${sd(r.ruc)}</td>
            <td>${sd(r.cotizacion)}</td>
            <td>${sd(r.pc_numero)}</td>
            <td>${sd(r.comprobante)}</td>
            <td>${sd(r.origen)}</td>
            <td>${sd(r.destino)}</td>
            <td style="white-space:nowrap;">
                <button class="kebab" onclick="showGuiaMenu(event, ${r.id})" title="Opciones (Crear factura, PDF, rótulo...)">⋮</button>
            </td>
        </tr>
    `).join('');
}


function renderComprobantes() {
    const q = document.getElementById('comprobanteSearch')?.value?.toLowerCase() || '';
    const st = document.getElementById('comprobanteStatus')?.value || '';
    
    const fechaInicio = document.getElementById('comprobanteFechaInicio')?.value || '';
    const fechaFin = document.getElementById('comprobanteFechaFin')?.value || '';
    
    const list = comprobantesData.filter(r => {
        const searchStr = `${r.numero || ''} ${r.serie || ''} ${r.cliente || ''} ${r.ruc || ''} ${r.condicion || ''} ${r.cotizacion || ''} ${r.pc_numero || ''} ${r.guia_numero || ''}`.toLowerCase();
        const matchText = !q || searchStr.includes(q);
        const matchStatus = !st || r.estado === st;
        
        let matchFecha = true;
        if (fechaInicio || fechaFin) {
            let fechaComp = r.fecha || r.created_at || '';
            let fechaObj = null;
            try {
                if (typeof fechaComp === 'string') {
                    fechaObj = new Date(fechaComp);
                    if (fechaComp.includes('/')) {
                        const partes = fechaComp.split(/[\/\s:]/);
                        if (partes.length >= 3) {
                            fechaObj = new Date(partes[2], partes[1] - 1, partes[0]);
                        }
                    }
                } else if (fechaComp instanceof Date) {
                    fechaObj = fechaComp;
                }
            } catch (e) {
                fechaObj = null;
            }
            
            if (fechaObj && !isNaN(fechaObj.getTime())) {
                const fechaStr = isoLima(fechaObj);
                if (fechaInicio && fechaFin) {
                    matchFecha = fechaStr >= fechaInicio && fechaStr <= fechaFin;
                } else if (fechaInicio) {
                    matchFecha = fechaStr >= fechaInicio;
                } else if (fechaFin) {
                    matchFecha = fechaStr <= fechaFin;
                }
            } else {
                if (fechaInicio || fechaFin) {
                    matchFecha = false;
                }
            }
        }
        return matchText && matchStatus && matchFecha;
    });
    
    const tbody = document.getElementById('comprobanteRows');
    if (!tbody) return;
    
    if (list.length === 0) {
        tbody.innerHTML = `<tr><td colspan="13" style="text-align:center;color:#94A3B8;padding:40px;">📭 No hay comprobantes registrados</td></tr>`;
        return;
    }
    
    tbody.innerHTML = list.map((r, i) => {
        // 🔽 Determinar si tiene retención del IGV
        const tieneRetencion = r.tiene_retencion || false;
        const montoRetenido = parseFloat(r.monto_retenido || 0);
        const montoAPagar = parseFloat(r.monto_a_pagar || r.monto || 0);
        const porcentajeRetencion = parseFloat(r.porcentaje_retencion || 3.00);
        
        // Monto mostrado (con retención si aplica)
        let montoStr = money(r.monto);
        if (tieneRetencion && montoRetenido > 0) {
            montoStr = `${money(r.monto)} <small style="color:#DC2626;font-size:8px;">(Ret: ${money(montoRetenido)})</small>`;
        }
        
        // Estado del crédito
        const esCredito = r.condicion && r.condicion.includes('Crédito');
        const estadoCredito = r.estado_credito || '';
        const diasCredito = r.dias_credito || '';
        
        let badgeCredito = '';
        if (esCredito) {
            if (estadoCredito === 'Aceptada en Crédito') {
                badgeCredito = `<span class="badge b-ok" style="background:#2563EB;border-color:#1D4ED8;">✅ ${estadoCredito}</span>`;
            } else if (estadoCredito === 'Pendiente de aprobación') {
                badgeCredito = `<span class="badge b-pending">⏳ ${estadoCredito}</span>`;
            } else if (estadoCredito === 'Rechazada') {
                badgeCredito = `<span class="badge b-canceled">❌ ${estadoCredito}</span>`;
            } else {
                badgeCredito = `<span class="badge b-gray">🔍 ${estadoCredito || 'Crédito'}</span>`;
            }
        }
        
        // Badge de retención
        let badgeRetencion = '';
        if (tieneRetencion) {
            badgeRetencion = `<span class="badge b-info" style="background:#DC2626;border-color:#991B1B;color:#fff;">🔒 ${porcentajeRetencion}%</span>`;
        }
        
        return `
        <tr>
            <td>${i + 1}</td>
            <td class="date-cell">${formatearFechaComprobante(r.fecha)}${tiemposHTML(r)}</td>
            <td>${badgeStatus(r.estado)}</td>
            <td>${r.tipo || '-'}</td>
            <td class="left">${sd(r.cliente)}</td>
            <td>${sd(r.ruc)}</td>
            <td>${sd(r.cotizacion)}</td>
            <td>${sd(r.pc_numero)}</td>
            <td>${sd(r.guia_numero)}</td>
            <td><b>${sd(r.serie)}-${sd(r.numero)}</b>${badgeNuevo(r, 'fecha')}</td>
            <td><b>${montoStr}</b></td>
            <td>
                <div style="display:flex;flex-direction:column;gap:2px;align-items:center;">
                    <b style="white-space:nowrap;color:${esCredito ? '#1D4ED8' : '#0F172A'}">${sd(window.normalizarCondicion(r.condicion))}</b>
                    ${esCredito && estadoCredito ? badgeCredito : ''}
                    ${badgeRetencion}
                </div>
            </td>
            <td>
                <button class="kebab" onclick="showComprobanteMenu(event, ${r.id})">⋮</button>
            </td>
        </tr>
    `}).join('');
}

// ============================================================
// LIMPIAR FILTROS DE FECHA - DESPACHOS
// ============================================================
function clearDespachoDateFilter() {
    console.log('🧹 Limpiando filtros de fecha de Despachos...');
    
    const fechaInicio = document.getElementById('despachoFechaInicio');
    const fechaFin = document.getElementById('despachoFechaFin');
    
    if (fechaInicio) fechaInicio.value = '';
    if (fechaFin) fechaFin.value = '';
    
    renderDespachos();
    showToast('🧹 Filtros de fecha limpiados', 'info');
}

// ============================================================
// LIMPIAR FILTROS DE FECHA - GUÍAS
// ============================================================
function clearGuiaDateFilter() {
    console.log('🧹 Limpiando filtros de fecha de Guías...');
    
    const fechaInicio = document.getElementById('guiaFechaInicio');
    const fechaFin = document.getElementById('guiaFechaFin');
    
    if (fechaInicio) fechaInicio.value = '';
    if (fechaFin) fechaFin.value = '';
    
    renderGuias();
    showToast('🧹 Filtros de fecha limpiados', 'info');
}

// ============================================================
// LIMPIAR FILTROS DE FECHA - COMPROBANTES
// ============================================================
function clearComprobanteDateFilter() {
    console.log('🧹 Limpiando filtros de fecha de Comprobantes...');
    
    const fechaInicio = document.getElementById('comprobanteFechaInicio');
    const fechaFin = document.getElementById('comprobanteFechaFin');
    
    if (fechaInicio) fechaInicio.value = '';
    if (fechaFin) fechaFin.value = '';
    
    renderComprobantes();
    showToast('🧹 Filtros de fecha limpiados', 'info');
}

function renderNotas() {
    const q = document.getElementById('notaSearch')?.value?.toLowerCase() || '';
    const st = document.getElementById('notaStatus')?.value || '';
    
    const list = notasData.filter(r => {
        const searchStr = `${r.numero || ''} ${r.serie || ''} ${r.cliente || ''} ${r.ruc || ''}`.toLowerCase();
        const matchText = !q || searchStr.includes(q);
        const matchStatus = !st || r.estado === st;
        return matchText && matchStatus;
    });
    
    const tbody = document.getElementById('notaRows');
    if (!tbody) return;
    
    if (list.length === 0) {
        tbody.innerHTML = `<tr><td colspan="11" style="text-align:center;color:#94A3B8;padding:40px;">📭 No hay notas de crédito registradas</td></tr>`;
        return;
    }
    
    tbody.innerHTML = list.map((r, i) => `
        <tr>
            <td>${i + 1}</td>
            <td class="date-cell">${String(r.fecha || '').replace(' ', '<br>')}${tiemposHTML(r)}</td>
            <td>${badgeStatus(r.estado)}</td>
            <td>${sd(r.tipo)}</td>
            <td><b>${sd(r.serie)}-${sd(r.numero)}</b>${badgeNuevo(r, 'fecha')}</td>
            <td class="left">${sd(r.cliente)}</td>
            <td>${sd(r.ruc)}</td>
            <td>${sd(r.comprobante)}</td>
            <td>${sd(r.motivo)}</td>
            <td><b>${money(r.monto)}</b></td>
            <td>
                <button class="kebab" onclick="showNotaMenu(event, ${r.id})">⋮</button>
            </td>
        </tr>
    `).join('');
}

function renderDevoluciones() {
    const q = document.getElementById('devolucionSearch')?.value?.toLowerCase() || '';
    const st = document.getElementById('devolucionStatus')?.value || '';
    
    const list = devolucionesData.filter(r => {
        const searchStr = `${r.numero || ''} ${r.cliente || ''} ${r.ruc || ''}`.toLowerCase();
        const matchText = !q || searchStr.includes(q);
        const matchStatus = !st || r.estado === st;
        return matchText && matchStatus;
    });
    
    const tbody = document.getElementById('devolucionRows');
    if (!tbody) return;
    
    if (list.length === 0) {
        tbody.innerHTML = `<tr><td colspan="10" style="text-align:center;color:#94A3B8;padding:40px;">📭 No hay devoluciones registradas</td></tr>`;
        return;
    }
    
    tbody.innerHTML = list.map((r, i) => `
        <tr>
            <td>${i + 1}</td>
            <td class="date-cell">${String(r.fecha || '').replace(' ', '<br>')}${tiemposHTML(r)}</td>
            <td>${badgeStatus(r.estado)}</td>
            <td><b>${sd(r.numero)}</b>${badgeNuevo(r, 'fecha')}</td>
            <td class="left">${sd(r.cliente)}</td>
            <td>${sd(r.ruc)}</td>
            <td>${sd(r.comprobante_numero)}</td>
            <td>${sd(r.guia)}</td>
            <td>${sd(r.motivo)}</td>
            <td>
                <button class="kebab" onclick="showDevolucionMenu(event, ${r.id})">⋮</button>
            </td>
        </tr>
    `).join('');
}


async function guardarCotizacion(estado) {
    try {
        console.log('🔄 Iniciando guardado de cotización...');
        
        // ============================================================
        // 🔽 VALIDAR CAMPOS OBLIGATORIOS
        // ============================================================
        const ruc = document.getElementById('fRuc')?.value?.trim() || '';
        const condicionPagoSelect = document.getElementById('fCondicion')?.value || '';
        const condicionCustom = document.getElementById('fCondicionCustom')?.value?.trim() || '';
        const tiempoEntregaSelect = document.getElementById('fTiempo')?.value || '';
        const tiempoCustom = document.getElementById('fTiempoCustom')?.value?.trim() || '';

        // Recopilar campos faltantes
        const camposFaltantes = [];

        // 1. Validar RUC
        if (!ruc || ruc.length < 11) {
            camposFaltantes.push('RUC (11 dígitos)');
            const el = document.getElementById('fRuc');
            if (el) {
                el.style.borderColor = '#DC2626';
                el.style.boxShadow = '0 0 0 3px rgba(220,38,38,0.2)';
                setTimeout(() => {
                    el.style.borderColor = '';
                    el.style.boxShadow = '';
                }, 3000);
            }
        }

        // 2. Validar Condición de Pago
        let condicionFinal = '';
        if (condicionPagoSelect === 'Personalizado') {
            condicionFinal = condicionCustom;
            if (!condicionFinal) {
                camposFaltantes.push('Condición de Pago (escribe un valor personalizado)');
                const el = document.getElementById('fCondicionCustom');
                if (el) {
                    el.style.borderColor = '#DC2626';
                    el.style.boxShadow = '0 0 0 3px rgba(220,38,38,0.2)';
                    setTimeout(() => {
                        el.style.borderColor = '';
                        el.style.boxShadow = '';
                    }, 3000);
                }
            }
        } else {
            condicionFinal = condicionPagoSelect;
            if (!condicionFinal || condicionFinal === 'Personalizado') {
                camposFaltantes.push('Condición de Pago');
                const el = document.getElementById('fCondicion');
                if (el) {
                    el.style.borderColor = '#DC2626';
                    el.style.boxShadow = '0 0 0 3px rgba(220,38,38,0.2)';
                    setTimeout(() => {
                        el.style.borderColor = '';
                        el.style.boxShadow = '';
                    }, 3000);
                }
            }
        }

        // 3. Validar Tiempo de Entrega
        let tiempoFinal = '';
        if (tiempoEntregaSelect === 'Personalizado') {
            tiempoFinal = tiempoCustom;
            if (!tiempoFinal) {
                camposFaltantes.push('Tiempo de Entrega (escribe un valor personalizado)');
                const el = document.getElementById('fTiempoCustom');
                if (el) {
                    el.style.borderColor = '#DC2626';
                    el.style.boxShadow = '0 0 0 3px rgba(220,38,38,0.2)';
                    setTimeout(() => {
                        el.style.borderColor = '';
                        el.style.boxShadow = '';
                    }, 3000);
                }
            }
        } else {
            tiempoFinal = tiempoEntregaSelect;
            if (!tiempoFinal || tiempoFinal === 'Personalizado') {
                camposFaltantes.push('Tiempo de Entrega');
                const el = document.getElementById('fTiempo');
                if (el) {
                    el.style.borderColor = '#DC2626';
                    el.style.boxShadow = '0 0 0 3px rgba(220,38,38,0.2)';
                    setTimeout(() => {
                        el.style.borderColor = '';
                        el.style.boxShadow = '';
                    }, 3000);
                }
            }
        }

        faltanCamposCotizacion().forEach(c => {
            if (!camposFaltantes.some(x => x.toLowerCase().startsWith(c.toLowerCase().slice(0, 10)))) camposFaltantes.push(c);
        });
        if (estado === 'Por validar' || estado === 'En revisión') {
            faltanDatosParihuela().forEach(c => {
                if (!camposFaltantes.some(x => x.toLowerCase().startsWith(c.toLowerCase().slice(0, 10)))) camposFaltantes.push(c);
            });
        }
        if (camposFaltantes.length > 0) {
            if (estado === 'Por validar' || estado === 'En revisión') {
                showToast('⛔ Faltan campos obligatorios para enviar a validación: ' + camposFaltantes.join(', '), 'error');
            }
            showValidationWarningModal(camposFaltantes);
            return null;
        }
        const vaciosInfo = infoAdicionalVacia().filter(x => !((estado === 'Por validar' || estado === 'En revisión') && /seguimiento/i.test(x)));
        if (vaciosInfo.length && !(await avisoAmarilloCotizacion(vaciosInfo))) return null;
        // ============================================================
        // 1. BUSCAR EL CLIENTE POR RUC
        // ============================================================
        let clienteId = null;
        let clienteData = null;

        // Buscar en CLIENTES_MAESTROS
        if (CLIENTES_MAESTROS && CLIENTES_MAESTROS.length > 0) {
            const cliente = CLIENTES_MAESTROS.find(c => 
                c.ruc === ruc || 
                c.numero_documento === ruc
            );
            if (cliente) {
                clienteId = cliente.id;
                clienteData = cliente;
                console.log('✅ Cliente encontrado en CLIENTES_MAESTROS con ID:', clienteId);
            }
        }

        // Si no está en memoria, buscar en la base de datos
        if (!clienteId) {
            console.log('🔍 Buscando cliente en BD por RUC:', ruc);
            try {
                const resp = await fetch(`/maestros/api/clientes/buscar?q=${ruc}`);
                const data = await resp.json();
                if (data.success && data.data && data.data.length > 0) {
                    clienteId = data.data[0].id;
                    clienteData = data.data[0];
                    console.log('✅ Cliente encontrado en BD con ID:', clienteId);
                    if (!CLIENTES_MAESTROS.find(c => c.id === clienteId)) {
                        CLIENTES_MAESTROS.push(clienteData);
                    }
                }
            } catch (e) {
                console.warn('⚠️ Error buscando cliente:', e);
            }
        }

        // Si no existe, CREAR el cliente
        if (!clienteId) {
            console.log('🆕 Cliente no encontrado, creando nuevo...');

            const nuevoCliente = {
                ruc: ruc,
                tipo_documento: 'RUC',
                numero_documento: ruc,
                razon_social: document.getElementById('fRazon')?.value?.trim() || `Cliente ${ruc}`,
                nombre_comercial: document.getElementById('fComercial')?.value?.trim() || '',
                direccion_fiscal: document.getElementById('fDireccion')?.value?.trim() || '',
                nombre_contacto: document.getElementById('fContacto')?.value?.trim() || '',
                telefono_contacto: document.getElementById('fTelefono')?.value?.trim() || '',
                email_contacto: document.getElementById('fCorreo')?.value?.trim() || '',
                condicion_pago: 'Contado',   // 20/10/2026: el crédito del cliente se aprueba en Maestros, no al cotizar
                dias_credito: 0,
                estado: 'Activo'
            };

            try {
                const resp = await fetch('/maestros/api/clientes/guardar', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(nuevoCliente)
                });
                const result = await resp.json();
                if (result.success && result.data && result.data.id) {
                    clienteId = result.data.id;
                    clienteData = result.data;
                    console.log('✅ Cliente creado con ID:', clienteId);
                    await cargarClientesMaestros();
                } else {
                    console.error('❌ Error creando cliente:', result.error);
                    showToast('Error al crear el cliente: ' + (result.error || 'Desconocido'), 'error');
                    return null;
                }
            } catch (e) {
                console.error('❌ Error en creación de cliente:', e);
                showToast('Error al crear el cliente', 'error');
                return null;
            }
        }

        if (!clienteId) {
            showToast('⚠️ No se pudo identificar o crear el cliente', 'error');
            return null;
        }

        console.log('🎯 Cliente ID final:', clienteId);

        // ============================================================
        // 2. CALCULAR TOTALES
        // ============================================================

        const subtotal = quoteProducts.reduce((s, p) => s + (Number(p.cantidad || 0) * Number(p.valorVenta || 0)), 0);
        const descuentoValor = parseFloat(document.getElementById('fDiscountValue')?.value || 0);
        const descuentoTipo = document.getElementById('fDiscountType')?.value || '%';
        const descuento = descuentoTipo === '%' 
            ? subtotal * (descuentoValor / 100) 
            : Math.min(descuentoValor, subtotal);
        const valorVenta = subtotal - descuento;
        const igv = valorVenta * 0.18;
        const total = valorVenta + igv;

        // ============================================================
        // 3. PREPARAR DATOS - ¡ESTA ES LA PARTE CLAVE!
        // ============================================================
        
        const data = {
            id: editingId,  // 🔑 Si es edición, se envía el ID
            estado: estado || 'Borrador',
            cliente_id: clienteId,
            ruc: ruc,
            razon: document.getElementById('fRazon')?.value?.trim() || '',
            razon_comercial: document.getElementById('fComercial')?.value?.trim() || '',
            direccion: document.getElementById('fDireccion')?.value?.trim() || '',
            contacto: getContactoSeleccionadoNombre(),
            telefono: document.getElementById('fTelefono')?.value?.trim() || '',
            email: document.getElementById('fCorreo')?.value?.trim() || '',
            vendedor: document.getElementById('fVendedor')?.value || 'Helen Blas Príncipe',
            condicion_pago: condicionFinal,
            tiempo_entrega: tiempoFinal,
            validez: getFieldValue('fValidez', 'fValidezCustom') || '15 días',
            direccion_entrega: getDireccionEntregaValue() || '',
            descuento_valor: descuentoValor,
            descuento_tipo: descuentoTipo,
            subtotal: subtotal,
            descuento_monto: descuento,
            igv: igv,
            total: total,
            seguimiento: document.getElementById('fSeguimiento')?.value || 'Helen Blas Príncipe',
            motivo: document.getElementById('fMotivo')?.value || 'Solicitud única del cliente',
            transporte: document.getElementById('fTransporte')?.value || 'Seleccione',
            parihuela: document.getElementById('fParihuela')?.value || 'Seleccione',
            nota_interna: document.getElementById('fNotaInterna')?.value?.trim() || '',
            requerimiento: document.getElementById('fReq')?.value?.trim() || '',
            productos: quoteProducts.map(p => ({
                codigo: p.codigo,
                producto: p.producto || p.descripcion,
                descripcion: p.descripcion || '',
                modelo: p.modelo || '',
                marca: p.marca || '',
                um: p.um || 'NIU',
                cantidad: p.cantidad || 1,
                valorVenta: p.valorVenta || 0,
                stock: p.stock || 0,
                estado_entrega: p.estado_entrega === 'Entregado' ? 'Entregado' : 'Pendiente'
            }))
        };

        console.log('📦 Enviando cotización:', data);

        // ============================================================
        // 4. ENVIAR A LA API
        // ============================================================

        const response = await apiFetch('/ventas/api/cotizaciones/guardar', {
            method: 'POST',
            body: JSON.stringify(data)
        });

        console.log('📦 Respuesta API:', response);

        if (response.success) {
            // 🔑 GUARDAR EL ID DE EDICIÓN PARA FUTURAS ACTUALIZACIONES
            if (response.data && response.data.id) {
                editingId = response.data.id;
                console.log('✅ ID de cotización guardado:', editingId);
            }
            
            const mensaje = estado === 'Borrador' ? 'guardada como borrador' : 'creada correctamente';
            showToast(`✅ Cotización ${mensaje}`, 'success');
            closeModal('cotizacionModal');
            await loadCotizaciones();
            await cargarClientesMaestros();
            return response;
        } else {
            showToast('❌ Error: ' + (response.error || 'No se pudo guardar'), 'error');
            return null;
        }
    } catch (error) {
        console.error('❌ Error guardando cotización:', error);
        showToast('❌ Error al guardar la cotización: ' + error.message, 'error');
        return null;
    }
}

function saveCotizacionDraft() {
    // Verificar que hay productos en la cotización
    if (quoteProducts.length === 0) {
        showToast('⚠️ Agrega al menos un producto a la cotización', 'warning');
        return;
    }
    
    // Verificar que hay un cliente seleccionado
    const ruc = document.getElementById('fRuc')?.value?.trim() || '';
    if (!ruc) {
        showToast('⚠️ Primero busca un cliente por RUC', 'warning');
        return;
    }
    
    // ============================================================
    // 🔽 VALIDAR CAMPOS OBLIGATORIOS ANTES DE GUARDAR
    // ============================================================
    const camposFaltantes = validarCamposObligatoriosCotizacion();
    
    if (camposFaltantes.length > 0) {
        showValidationWarningModal(camposFaltantes);
        return;
    }
    
    // Guardar como Borrador
    guardarCotizacion('Borrador');
}

function sendCotizacionToReview() {
    // Verificar que hay productos en la cotización
    if (quoteProducts.length === 0) {
        showToast('⚠️ Agrega al menos un producto a la cotización', 'warning');
        return;
    }
    
    // Verificar que hay un cliente seleccionado
    const ruc = document.getElementById('fRuc')?.value?.trim() || '';
    if (!ruc) {
        showToast('⚠️ Primero busca un cliente por RUC', 'warning');
        return;
    }
    
    // ============================================================
    // 🔽 VALIDAR CAMPOS OBLIGATORIOS ANTES DE ENVIAR A REVISIÓN
    // ============================================================
    const camposFaltantes = validarCamposObligatoriosCotizacion();
    
    if (camposFaltantes.length > 0) {
        showValidationWarningModal(camposFaltantes);
        return;
    }
    
    guardarCotizacion('En revisión');
}

// ============================================================
// FUNCIÓN AUXILIAR PARA VALIDAR CAMPOS OBLIGATORIOS DE COTIZACIÓN
// ============================================================
// ============================================================
// 4 CAMPOS OBLIGATORIOS DE LA COTIZACIÓN (pedido de Erika 19/10/2026): condición de pago, tiempo de entrega,
// transporte y parihuela. Sin ellos no se guarda ni se envía a validación. El resto de "información
// adicional" vacío solo muestra un aviso amarillo.
// ============================================================
function _cotMarcarFalta(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.style.borderColor = '#DC2626';
    el.style.boxShadow = '0 0 0 3px rgba(220,38,38,0.25)';
    setTimeout(() => { el.style.borderColor = ''; el.style.boxShadow = ''; }, 4000);
}
function faltanCamposCotizacion() {
    const faltan = [];
    const vacio = v => !v || /^(seleccione|personalizado|--.*)$/i.test(String(v).trim());
    const val = (sel, custom) => {
        const s = document.getElementById(sel)?.value || '';
        return s === 'Personalizado' ? (document.getElementById(custom)?.value || '').trim() : s;
    };
    if (vacio(val('fCondicion', 'fCondicionCustom'))) { faltan.push('Condición de pago'); _cotMarcarFalta(document.getElementById('fCondicion')?.value === 'Personalizado' ? 'fCondicionCustom' : 'fCondicion'); }
    if (vacio(val('fTiempo', 'fTiempoCustom'))) { faltan.push('Tiempo de entrega'); _cotMarcarFalta(document.getElementById('fTiempo')?.value === 'Personalizado' ? 'fTiempoCustom' : 'fTiempo'); }
    if (vacio(document.getElementById('fTransporte')?.value)) { faltan.push('Transporte'); _cotMarcarFalta('fTransporte'); }
    if (vacio(document.getElementById('fParihuela')?.value)) { faltan.push('Parihuela (si incluye o no)'); _cotMarcarFalta('fParihuela'); }
    return faltan;
}
function avisoAmarilloCotizacion(vacios) {
    return new Promise(resolve => {
        document.getElementById('avisoAmarilloCot')?.remove();
        const f = document.createElement('div');
        f.id = 'avisoAmarilloCot';
        f.style.cssText = 'position:fixed;inset:0;background:rgba(15,23,42,.5);z-index:10000002;display:flex;align-items:center;justify-content:center;padding:16px';
        f.innerHTML = `<div style="background:#FEFCE8;border:4px solid #EAB308;border-radius:14px;max-width:480px;width:100%;padding:20px;box-shadow:0 20px 60px rgba(0,0,0,.35);color:#422006">
            <div style="font-size:20px;font-weight:900;margin-bottom:8px">⚠️ Ojo: No has llenado la información adicional. ¿Seguro que deseas continuar?</div>
            <div style="font-size:14px;font-weight:700;margin-bottom:14px">Está vacío: ${vacios.join(', ')}</div>
            <div style="display:flex;gap:10px;justify-content:flex-end">
              <button type="button" data-r="0" style="padding:10px 16px;border-radius:10px;border:2px solid #A16207;background:#fff;color:#713F12;font-weight:800;font-size:15px;cursor:pointer">Volver y llenar</button>
              <button type="button" data-r="1" style="padding:10px 16px;border-radius:10px;border:0;background:#CA8A04;color:#fff;font-weight:900;font-size:15px;cursor:pointer">Sí, continuar</button>
            </div></div>`;
        document.body.appendChild(f);
        f.querySelectorAll('button').forEach(b => b.onclick = () => { f.remove(); resolve(b.dataset.r === '1'); });
    });
}
// Pedido de Erika 20/10/2026: los datos de la fila de la parihuela (sección 5) son obligatorios para
// "Solicitar validación". Un borrador se puede guardar sin ellos.
function faltanDatosParihuela() {
    const faltan = [];
    const vacio = v => !v || /^(seleccione|--.*)$/i.test(String(v).trim());
    // La nota interna NO es obligatoria (Erika, 20/10/2026 17:19)
    [['fSeguimiento', 'Seguimiento'], ['fMotivo', 'Motivo'], ['fTransporte', 'Transporte'],
     ['fParihuela', 'Parihuela (si incluye o no)']]
        .forEach(([id, nombre]) => {
            if (vacio((document.getElementById(id)?.value || '').trim())) { faltan.push(nombre); _cotMarcarFalta(id); }
        });
    return faltan;
}
window.faltanDatosParihuela = faltanDatosParihuela;

function infoAdicionalVacia() {
    const v = [];
    if (!(document.getElementById('fSeguimiento')?.value || '').trim()) v.push('Seguimiento');
    if (!(document.getElementById('fNotaInterna')?.value || '').trim()) v.push('Nota interna');
    const dir = (typeof getDireccionEntregaValue === 'function' ? getDireccionEntregaValue() : '') || '';
    if (!String(dir).trim()) v.push('Dirección de entrega');
    return v;
}

function validarCamposObligatoriosCotizacion() {
    const camposFaltantes = [];
    
    const ruc = document.getElementById('fRuc')?.value?.trim() || '';
    const condicionPagoSelect = document.getElementById('fCondicion')?.value || '';
    const condicionCustom = document.getElementById('fCondicionCustom')?.value?.trim() || '';
    const tiempoEntregaSelect = document.getElementById('fTiempo')?.value || '';
    const tiempoCustom = document.getElementById('fTiempoCustom')?.value?.trim() || '';

    // 1. Validar RUC
    if (!ruc || ruc.length < 11) {
        camposFaltantes.push('RUC (11 dígitos)');
        const el = document.getElementById('fRuc');
        if (el) {
            el.style.borderColor = '#DC2626';
            el.style.boxShadow = '0 0 0 3px rgba(220,38,38,0.2)';
            setTimeout(() => {
                el.style.borderColor = '';
                el.style.boxShadow = '';
            }, 3000);
        }
    }

    // 2. Validar Condición de Pago
    if (condicionPagoSelect === 'Personalizado') {
        if (!condicionCustom) {
            camposFaltantes.push('Condición de Pago (escribe un valor personalizado)');
            const el = document.getElementById('fCondicionCustom');
            if (el) {
                el.style.borderColor = '#DC2626';
                el.style.boxShadow = '0 0 0 3px rgba(220,38,38,0.2)';
                setTimeout(() => {
                    el.style.borderColor = '';
                    el.style.boxShadow = '';
                }, 3000);
            }
        }
    } else {
        if (!condicionPagoSelect || condicionPagoSelect === 'Personalizado') {
            camposFaltantes.push('Condición de Pago');
            const el = document.getElementById('fCondicion');
            if (el) {
                el.style.borderColor = '#DC2626';
                el.style.boxShadow = '0 0 0 3px rgba(220,38,38,0.2)';
                setTimeout(() => {
                    el.style.borderColor = '';
                    el.style.boxShadow = '';
                }, 3000);
            }
        }
    }

    // 3. Validar Tiempo de Entrega
    if (tiempoEntregaSelect === 'Personalizado') {
        if (!tiempoCustom) {
            camposFaltantes.push('Tiempo de Entrega (escribe un valor personalizado)');
            const el = document.getElementById('fTiempoCustom');
            if (el) {
                el.style.borderColor = '#DC2626';
                el.style.boxShadow = '0 0 0 3px rgba(220,38,38,0.2)';
                setTimeout(() => {
                    el.style.borderColor = '';
                    el.style.boxShadow = '';
                }, 3000);
            }
        }
    } else {
        if (!tiempoEntregaSelect || tiempoEntregaSelect === 'Personalizado') {
            camposFaltantes.push('Tiempo de Entrega');
            const el = document.getElementById('fTiempo');
            if (el) {
                el.style.borderColor = '#DC2626';
                el.style.boxShadow = '0 0 0 3px rgba(220,38,38,0.2)';
                setTimeout(() => {
                    el.style.borderColor = '';
                    el.style.boxShadow = '';
                }, 3000);
            }
        }
    }

    faltanCamposCotizacion().forEach(c => {
        if (!camposFaltantes.some(x => x.toLowerCase().startsWith(c.toLowerCase().slice(0, 10)))) camposFaltantes.push(c);
    });
    return camposFaltantes;
}

function generateCotizacionPdfAndSend() {
    // ============================================================
    // 🔽 PRIMERO: VALIDAR CAMPOS OBLIGATORIOS
    // ============================================================
    
    // Verificar que hay productos en la cotización
    if (quoteProducts.length === 0) {
        showToast('⚠️ Agrega al menos un producto a la cotización', 'warning');
        return;
    }
    
    // Verificar que hay un cliente seleccionado
    const ruc = document.getElementById('fRuc')?.value?.trim() || '';
    if (!ruc) {
        showToast('⚠️ Primero busca un cliente por RUC', 'warning');
        return;
    }
    
    // ============================================================
    // 🔽 VALIDAR CAMPOS OBLIGATORIOS ANTES DEL MODAL
    // ============================================================
    const condicionPagoSelect = document.getElementById('fCondicion')?.value || '';
    const condicionCustom = document.getElementById('fCondicionCustom')?.value?.trim() || '';
    const tiempoEntregaSelect = document.getElementById('fTiempo')?.value || '';
    const tiempoCustom = document.getElementById('fTiempoCustom')?.value?.trim() || '';

    const camposFaltantes = [];

    // 1. Validar RUC
    if (!ruc || ruc.length < 11) {
        camposFaltantes.push('RUC (11 dígitos)');
        const el = document.getElementById('fRuc');
        if (el) {
            el.style.borderColor = '#DC2626';
            el.style.boxShadow = '0 0 0 3px rgba(220,38,38,0.2)';
            setTimeout(() => {
                el.style.borderColor = '';
                el.style.boxShadow = '';
            }, 3000);
        }
    }

    // 2. Validar Condición de Pago
    let condicionFinal = '';
    if (condicionPagoSelect === 'Personalizado') {
        condicionFinal = condicionCustom;
        if (!condicionFinal) {
            camposFaltantes.push('Condición de Pago (escribe un valor personalizado)');
            const el = document.getElementById('fCondicionCustom');
            if (el) {
                el.style.borderColor = '#DC2626';
                el.style.boxShadow = '0 0 0 3px rgba(220,38,38,0.2)';
                setTimeout(() => {
                    el.style.borderColor = '';
                    el.style.boxShadow = '';
                }, 3000);
            }
        }
    } else {
        condicionFinal = condicionPagoSelect;
        if (!condicionFinal || condicionFinal === 'Personalizado') {
            camposFaltantes.push('Condición de Pago');
            const el = document.getElementById('fCondicion');
            if (el) {
                el.style.borderColor = '#DC2626';
                el.style.boxShadow = '0 0 0 3px rgba(220,38,38,0.2)';
                setTimeout(() => {
                    el.style.borderColor = '';
                    el.style.boxShadow = '';
                }, 3000);
            }
        }
    }

    // 3. Validar Tiempo de Entrega
    let tiempoFinal = '';
    if (tiempoEntregaSelect === 'Personalizado') {
        tiempoFinal = tiempoCustom;
        if (!tiempoFinal) {
            camposFaltantes.push('Tiempo de Entrega (escribe un valor personalizado)');
            const el = document.getElementById('fTiempoCustom');
            if (el) {
                el.style.borderColor = '#DC2626';
                el.style.boxShadow = '0 0 0 3px rgba(220,38,38,0.2)';
                setTimeout(() => {
                    el.style.borderColor = '';
                    el.style.boxShadow = '';
                }, 3000);
            }
        }
    } else {
        tiempoFinal = tiempoEntregaSelect;
        if (!tiempoFinal || tiempoFinal === 'Personalizado') {
            camposFaltantes.push('Tiempo de Entrega');
            const el = document.getElementById('fTiempo');
            if (el) {
                el.style.borderColor = '#DC2626';
                el.style.boxShadow = '0 0 0 3px rgba(220,38,38,0.2)';
                setTimeout(() => {
                    el.style.borderColor = '';
                    el.style.boxShadow = '';
                }, 3000);
            }
        }
    }

    // ============================================================
    // 🔽 SI HAY CAMPOS FALTANTES, MOSTRAR MODAL Y DETENER
    // ============================================================
    if (camposFaltantes.length > 0) {
        showValidationWarningModal(camposFaltantes);
        return; // ⚠️ IMPORTANTE: Detener la ejecución aquí
    }

    // ============================================================
    // 🔽 TODOS LOS CAMPOS ESTÁN COMPLETOS - MOSTRAR MODAL DE CONFIRMACIÓN
    // ============================================================
    showConfirmModal(
        '¿Estás seguro de generar esta cotización oficial?',
        'Esta acción convertirá la cotización a estado "Generada" y no podrá revertirse. Se enviará al cliente y quedará registrada como documento oficial.',
        '⚠️ Esta acción es irreversible',
        async function() {
            // Mostrar loading en el botón
            const btn = document.querySelector('#cotizacionModal .btn-green');
            const originalText = btn?.textContent || '📄 Generar cotización';
            if (btn) {
                btn.textContent = '⏳ Generando...';
                btn.disabled = true;
            }
            
            try {
                // ✅ GUARDAR LA COTIZACIÓN Y OBTENER EL RESULTADO
                const result = await guardarCotizacion('Generada');
                
                // ✅ OBTENER EL ID DE LA COTIZACIÓN CREADA
                let cotizacionId = null;
                if (result && result.data && result.data.id) {
                    cotizacionId = result.data.id;
                } else {
                    // Si no viene en la respuesta, buscar la última cotización
                    await loadCotizaciones();
                    if (cotizacionesData.length > 0) {
                        cotizacionId = cotizacionesData[0].id;
                    }
                }
                
                // ✅ MOSTRAR MODAL DE ÉXITO CON EL ID
                showSuccessModal(cotizacionId);
                
            } catch (error) {
                console.error('Error generando cotización:', error);
                showToast('❌ Error al generar la cotización: ' + error.message, 'error');
            } finally {
                if (btn) {
                    btn.textContent = originalText;
                    btn.disabled = false;
                }
            }
        }
    );
}


// ============================================================
// SELECCIÓN MÚLTIPLE DE PRODUCTOS PARA PC
// ============================================================

let productSelectorPcData = [];
let selectedPcProductIds = new Set();

/**
 * Abre el selector múltiple de productos para PC
 */
function openProductSelectorPC() {
    // Si no hay productos maestros, cargarlos primero
    if (PRODUCTOS_MAESTROS.length === 0) {
        showToast('⏳ Cargando productos...', 'info');
        cargarProductosMaestros().then(() => {
            setTimeout(() => openProductSelectorPC(), 300);
        });
        return;
    }
    
    // Resetear selecciones
    selectedPcProductIds = new Set();
    productSelectorPcData = [...PRODUCTOS_MAESTROS];
    
    // Renderizar tabla
    renderProductSelectorPc();
    
    // Mostrar modal
    document.getElementById('productSelectorPcModal').classList.add('show');
    
    // Enfocar buscador
    setTimeout(() => {
        document.getElementById('productSelectorPcSearch')?.focus();
    }, 300);
}

/**
 * Renderiza la tabla de productos del selector de PC
 */
function renderProductSelectorPc() {
    const tbody = document.getElementById('productSelectorPcRows');
    const search = document.getElementById('productSelectorPcSearch')?.value?.toLowerCase() || '';
    
    // Filtrar productos
    let filtered = productSelectorPcData;
    if (search) {
        filtered = productSelectorPcData.filter(p => 
            (p.codigo && p.codigo.toLowerCase().includes(search)) ||
            (p.producto && p.producto.toLowerCase().includes(search)) ||
            (p.descripcion && p.descripcion.toLowerCase().includes(search)) ||
            (p.marca && p.marca.toLowerCase().includes(search)) ||
            (p.modelo && p.modelo.toLowerCase().includes(search))
        );
    }
    
    if (!tbody) return;
    
    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;color:#94A3B8;padding:30px;">📭 No se encontraron productos</td></tr>`;
        document.getElementById('selectedPcCount').textContent = selectedPcProductIds.size;
        return;
    }
    
    tbody.innerHTML = filtered.map((p, index) => {
        const idKey = p.id || p.codigo;
        const isChecked = selectedPcProductIds.has(idKey);
        const valorVenta = parseFloat(p.valorVenta) || 0;
        
        return `
        <tr>
            <td style="text-align:center;">
                <input type="checkbox" class="product-select-pc-checkbox" 
                       data-id="${idKey}" 
                       ${isChecked ? 'checked' : ''}
                       onchange="toggleProductSelectionPc('${idKey}', this.checked)">
            </td>
            <td style="font-weight:900; color:#0F172A;">${p.codigo || '-'}</td>
            <td style="text-align:left; font-weight:800;">${p.producto || p.descripcion || 'Sin nombre'}</td>
            <td>${p.marca || '-'}</td>
            <td>${p.modelo || '-'}</td>
            <td>${p.um || 'NIU'}</td>
            <td>${p.stock || 0}</td>
            <td style="font-weight:900; color:#059669;">S/ ${valorVenta.toFixed(2)}</td>
            <td>
                <input type="number" class="product-select-pc-qty" 
                       data-id="${idKey}"
                       value="1" 
                       min="1" 
                       style="width:60px; height:28px; border:1px solid #E5E7EB; border-radius:6px; text-align:center; font-size:12px;">
            </td>
        </tr>
    `}).join('');
    
    document.getElementById('selectedPcCount').textContent = selectedPcProductIds.size;
    
    // Actualizar el checkbox "Seleccionar todos"
    const totalCheckboxes = document.querySelectorAll('.product-select-pc-checkbox').length;
    const checkedCheckboxes = document.querySelectorAll('.product-select-pc-checkbox:checked').length;
    const selectAllCheckbox = document.getElementById('selectAllPcCheckbox');
    if (selectAllCheckbox) {
        if (totalCheckboxes > 0 && checkedCheckboxes === totalCheckboxes) {
            selectAllCheckbox.checked = true;
            selectAllCheckbox.indeterminate = false;
        } else if (checkedCheckboxes > 0) {
            selectAllCheckbox.checked = false;
            selectAllCheckbox.indeterminate = true;
        } else {
            selectAllCheckbox.checked = false;
            selectAllCheckbox.indeterminate = false;
        }
    }
}

/**
 * Alterna la selección de un producto en el selector de PC
 */
function toggleProductSelectionPc(idKey, checked) {
    if (checked) {
        selectedPcProductIds.add(idKey);
    } else {
        selectedPcProductIds.delete(idKey);
    }
    document.getElementById('selectedPcCount').textContent = selectedPcProductIds.size;
    
    // Actualizar el checkbox "Seleccionar todos"
    const totalCheckboxes = document.querySelectorAll('.product-select-pc-checkbox').length;
    const checkedCheckboxes = document.querySelectorAll('.product-select-pc-checkbox:checked').length;
    const selectAllCheckbox = document.getElementById('selectAllPcCheckbox');
    if (selectAllCheckbox) {
        if (totalCheckboxes > 0 && checkedCheckboxes === totalCheckboxes) {
            selectAllCheckbox.checked = true;
            selectAllCheckbox.indeterminate = false;
        } else if (checkedCheckboxes > 0) {
            selectAllCheckbox.checked = false;
            selectAllCheckbox.indeterminate = true;
        } else {
            selectAllCheckbox.checked = false;
            selectAllCheckbox.indeterminate = false;
        }
    }
}

/**
 * Selecciona todos los productos del selector de PC
 */
function selectAllProductsPc() {
    document.querySelectorAll('.product-select-pc-checkbox').forEach(cb => {
        cb.checked = true;
        const idKey = cb.dataset.id;
        selectedPcProductIds.add(idKey);
    });
    document.getElementById('selectedPcCount').textContent = selectedPcProductIds.size;
    const selectAllCheckbox = document.getElementById('selectAllPcCheckbox');
    if (selectAllCheckbox) selectAllCheckbox.checked = true;
}

/**
 * Deselecciona todos los productos del selector de PC
 */
function deselectAllProductsPc() {
    document.querySelectorAll('.product-select-pc-checkbox').forEach(cb => {
        cb.checked = false;
        const idKey = cb.dataset.id;
        selectedPcProductIds.delete(idKey);
    });
    document.getElementById('selectedPcCount').textContent = selectedPcProductIds.size;
    const selectAllCheckbox = document.getElementById('selectAllPcCheckbox');
    if (selectAllCheckbox) selectAllCheckbox.checked = false;
}

/**
 * Filtra los productos del selector de PC por búsqueda
 */
function filterProductSelectorPc() {
    renderProductSelectorPc();
}

/**
 * Agrega los productos seleccionados a la tabla del PC
 */
function addSelectedProductsPc() {
    if (selectedPcProductIds.size === 0) {
        showToast('⚠️ Selecciona al menos un producto', 'warning');
        return;
    }
    
    let addedCount = 0;
    let notFoundCount = 0;
    
    selectedPcProductIds.forEach(idKey => {
        // Buscar el producto por id o codigo
        let product = PRODUCTOS_MAESTROS.find(p => p.id == idKey || p.codigo == idKey);
        
        if (!product) {
            notFoundCount++;
            return;
        }
        
        // Obtener la cantidad del input correspondiente
        const qtyInput = document.querySelector(`.product-select-pc-qty[data-id="${idKey}"]`);
        const cantidad = parseInt(qtyInput?.value || 1);
        
        // Obtener datos del producto
        const codigo = product.codigo || '';
        const descripcion = product.producto || product.descripcion || 'Sin descripción';
        const marca = product.marca || '';
        const modelo = product.modelo || '';
        const precio = parseFloat(product.valorVenta) || 0;
        const stock = parseInt(product.stock) || 0;
        
        // Agregar fila a la tabla del PC
        agregarItemPCTable(codigo, descripcion, marca, modelo, cantidad, precio, stock);
        
        addedCount++;
    });
    
    // Cerrar modal
    closeModal('productSelectorPcModal');
    
    // Mostrar mensaje
    if (addedCount > 0) {
        showToast(`✅ ${addedCount} productos agregados correctamente`, 'success');
    }
    if (notFoundCount > 0) {
        showToast(`⚠️ ${notFoundCount} productos no encontrados`, 'warning');
    }
}

function agregarItemPCTable(codigo, descripcion, marca, modelo, cantidad, precio, stock) {
    const tbody = document.getElementById('pcItemsBody');
    if (!tbody) return;
    stock = stockVivo(codigo, stock);
    cantidad = Number(cantidad) || 0;
    precio = Math.round((Number(precio) || 0) * 100) / 100; // 2 decimales
    
    const rowCount = tbody.children.length + 1;
    const faltante = Math.max(cantidad - stock, 0);
    const valorTotal = cantidad * precio;
    
    const tr = document.createElement('tr');
    tr.id = `item-row-${rowCount}`;
    tr.style.borderBottom = '1px solid #E2E8F0';
    
    tr.innerHTML = `
        <td style="padding:2px 3px; text-align:center; font-weight:800; font-size:9px; background:#F8FAFC;">${rowCount}</td>
        <td style="padding:2px 3px;">
            <input value="${esc(codigo)}" 
                   style="width:100%; border:none; background:#F1F5F9; font-size:9px; padding:0; outline:none; font-weight:800; color:#1D4ED8;"
                   readonly>
        </td>
        <td style="padding:2px 3px;">
            <input value="${esc(descripcion)}" 
                   style="width:100%; border:none; background:#F1F5F9; font-size:9px; padding:0; outline:none; font-weight:800;"
                   readonly>
        </td>
        <td style="padding:2px 3px;">
            <input value="${esc(modelo)}" 
                   style="width:100%; border:none; background:transparent; font-size:9px; padding:0; outline:none; font-weight:700; color:#0F172A;">
        </td>
        <td style="padding:2px 3px;">
            <input value="${esc(marca)}" 
                   style="width:100%; border:none; background:transparent; font-size:9px; padding:0; outline:none; font-weight:700; color:#0F172A;">
        </td>
        <td style="padding:2px 3px; width:55px;">
            <input type="number" value="${cantidad}" 
                   style="width:45px; border:none; background:#F1F5F9; font-size:9px; padding:0; outline:none; text-align:center;"
                   readonly>
        </td>
        <td style="padding:2px 3px; width:55px;">
            <input type="number" value="${cantidad}" 
                   style="width:45px; border:none; background:transparent; font-size:9px; padding:0; outline:none; text-align:center; font-weight:900;"
                   onchange="actualizarResumenDesdeInput(this)">
        </td>
        <td style="padding:2px 3px; width:65px;">
            <input type="number" step="0.01" value="${Number(precio || 0).toFixed(2)}" 
                   style="width:55px; border:none; background:#F1F5F9; font-size:9px; padding:0; outline:none; text-align:center;"
                   readonly>
        </td>
        <td style="padding:2px 3px; width:65px;">
            <input type="number" step="0.01" value="${Number(precio || 0).toFixed(2)}" 
                   style="width:55px; border:none; background:transparent; font-size:9px; padding:0; outline:none; text-align:center; font-weight:900; color:#0F172A;"
                   onchange="actualizarResumenDesdeInput(this)">
        </td>
        <td style="padding:2px 3px; width:70px; text-align:center; font-weight:900; color:#059669; font-size:9px;">
            <span id="valor-total-${rowCount}">${valorTotal.toFixed(2)}</span>
        </td>
        <td style="padding:2px 3px; text-align:center; font-size:8px; color:#64748B; font-weight:800;">${stock}</td>
        <td style="padding:2px 3px; text-align:center; font-size:8px; font-weight:900; color:${faltante > 0 ? '#DC2626' : '#16A34A'};">${faltante}</td>
    `;
    
    tbody.appendChild(tr);
    reordenarItemsSAP();
    actualizarResumenManual();
}


/**
 * Alterna todos los checkboxes del selector de PC
 */
function toggleAllProductCheckboxesPc(checked) {
    document.querySelectorAll('.product-select-pc-checkbox').forEach(cb => {
        cb.checked = checked;
        const idKey = cb.dataset.id;
        if (checked) {
            selectedPcProductIds.add(idKey);
        } else {
            selectedPcProductIds.delete(idKey);
        }
    });
    document.getElementById('selectedPcCount').textContent = selectedPcProductIds.size;
}


// ============================================================
// FUNCIONES DE GUARDADO PARA PC, DESPACHO, GUÍAS, ETC.
// ============================================================

async function _savePedidoCompra(estado) {
    try {
        console.log('🔄 Guardando PC Pedido Compras...', { estado });
        
        // Obtener validaciones
        const validaciones = {
            precio: document.getElementById('vPrecio')?.value || 'Sí',
            cantidad: document.getElementById('vCantidad')?.value || 'Sí',
            producto: document.getElementById('vProducto')?.value || 'Sí',
            entrega: document.getElementById('vEntrega')?.value || 'Sí',
            moneda: document.getElementById('vMoneda')?.value || 'Sí',
            transporte: document.getElementById('vTransporte')?.value || 'Sí',
            vigencia: document.getElementById('vVigencia')?.value || 'Sí',
            margen: document.getElementById('vMargen')?.value || 'Sí'
        };
        
        // Verificar si hay observaciones
        const hasObservations = Object.values(validaciones).some(v => v === 'No');
        const estadoFinal = hasObservations ? 'PC observado' : (estado || 'PC conforme');
        
        // Obtener items
        const items = [];
        const rows = document.querySelectorAll('#pcItemsBody tr');
        rows.forEach(row => {
            const inputs = row.querySelectorAll('input');
            if (inputs.length >= 8) {
                items.push({
                    codigo: inputs[0].value || '',
                    descripcion: inputs[1].value || '',
                    cantidad_cotizada: parseFloat(inputs[2].value) || 0,
                    cantidad_pc: parseFloat(inputs[3].value) || 0,
                    precio_cotizado: parseFloat(inputs[4].value) || 0,
                    precio_pc: parseFloat(inputs[5].value) || 0,
                    stock: parseFloat(inputs[6].value) || 0,
                    faltante: Math.max((parseFloat(inputs[3].value) || 0) - (parseFloat(inputs[6].value) || 0), 0)
                });
            }
        });
        
        const data = {
            id: editingId,
            estado: estadoFinal,
            numero: document.getElementById('pcNumero')?.value || '',
            cotizacion_numero: document.getElementById('pcCotNumero')?.value || '',
            cliente: document.getElementById('pcCliente')?.value || '',
            ruc: document.getElementById('pcRuc')?.value || '',
            monto: parseFloat(document.getElementById('pcMonto')?.value || 0),
            medio: document.getElementById('pcMedio')?.value || 'Correo',
            fecha: document.getElementById('pcFecha')?.value || '',
            contacto: document.getElementById('pcContacto')?.value || '',
            moneda: document.getElementById('pcMoneda')?.value || 'Soles (S/)',
            condicion_pago: getPcCondicionValue(),
            lugar_entrega: document.getElementById('pcEntrega')?.value || '',
            observaciones: document.getElementById('pcObs')?.value || '',
            validaciones: validaciones,
            items: items,
            has_observations: hasObservations,
            req_compra: hasObservations ? 'Bloqueado' : 'Sí'
        };
        
        console.log('📦 Datos a guardar:', data);
        
        const response = await apiFetch('/ventas/api/pedido-compra/guardar', {
            method: 'POST',
            body: JSON.stringify(data)
        });
        
        if (response.success) {

            
        
            const mensaje = hasObservations ? 'guardado con observaciones' : 'guardado correctamente';
            showToast(`✅ PC ${mensaje}`, 'success');
            closeModal('pedidoCompraModal');
            await loadPedidos();
        } else {
            showToast('❌ Error: ' + (response.error || 'No se pudo guardar'), 'error');
        }
    } catch (error) {
        console.error('❌ Error guardando PC:', error);
        showToast('❌ Error al guardar el PC: ' + error.message, 'error');
    }
}

// Nueva función pública con confirmación - MISMO NOMBRE que usa el botón
function savePedidoCompra(estado) {
    const numero = document.getElementById('pcNumero')?.value || 'nuevo PC';
    const cliente = document.getElementById('pcCliente')?.value || 'el cliente';
    const estadoLabel = estado || 'PC conforme';

    showConfirmModal(
        '💾 ¿Guardar Pedido de Compra?',
        `Vas a guardar el PC <b>${numero}</b> de <b>${cliente}</b> como <b>"${estadoLabel}"</b>.`,
        '⚠️ Verifica que los datos y validaciones estén correctos antes de continuar.',
        async function() {
            await _savePedidoCompra(estado);
        },
        '💾 Sí, guardar'
    );
}

// ============================================================
// FUNCIÓN saveDespacho CORREGIDA - CON FECHA Y HORA COMPLETA
// ============================================================
async function _saveDespacho(estado) {
    try {
        // ============================================================
        // 🔽 FECHA CON HORA - IGUAL QUE EN COMPROBANTES Y GUÍAS
        // ============================================================
        const ahora = new Date();
        const year = ahora.getFullYear();
        const month = String(ahora.getMonth() + 1).padStart(2, '0');
        const day = String(ahora.getDate()).padStart(2, '0');
        const hours = String(ahora.getHours()).padStart(2, '0');
        const minutes = String(ahora.getMinutes()).padStart(2, '0');
        const seconds = String(ahora.getSeconds()).padStart(2, '0');
        
        // Formato ISO completo con hora: 2026-08-28T16:17:30
        const fechaHoraISO = `${year}-${month}-${day}T${hours}:${minutes}:${seconds}`;

        console.log(`🕐 Fecha y hora actual para despacho: ${fechaHoraISO}`);

        const data = {
            id: editingId,
            estado: estado || 'Pendiente despacho',
            numero: document.getElementById('despachoNumero')?.value || '',
            pc_numero: document.getElementById('despachoPC')?.value || '',
            cotizacion_numero: document.getElementById('despachoCotizacion')?.value || '',
            items: editingId ? undefined : (window._despachoProductos || []),
            cliente: document.getElementById('despachoCliente')?.value || '',
            ruc: document.getElementById('despachoRuc')?.value || '',
            // 🔽 ENVIAR FECHA CON HORA COMPLETA
            fecha_despacho: fechaHoraISO,
            origen: document.getElementById('despachoOrigen')?.value || '',
            destino: document.getElementById('despachoDestino')?.value || '',
            transportista: document.getElementById('despachoTransportista')?.value || '',
            observaciones: document.getElementById('despachoObs')?.value || ''
        };
        
        console.log('📦 Datos a guardar (despacho):', data);
        
        const response = await apiFetch('/ventas/api/despachos/guardar', {
            method: 'POST',
            body: JSON.stringify(data)
        });
        
        if (response.success) {
            showToast(`✅ Despacho guardado como: ${estado}`, 'success');
            closeModal('despachoModal');
            await loadDespachos();
        } else {
            showToast('❌ Error: ' + (response.error || 'No se pudo guardar'), 'error');
        }
    } catch (error) {
        console.error('❌ Error guardando despacho:', error);
        showToast('❌ Error al guardar el despacho: ' + error.message, 'error');
    }
}

function saveDespacho(estado) {
    const numero = document.getElementById('despachoNumero')?.value || 'nuevo despacho';
    const cliente = document.getElementById('despachoCliente')?.value || 'el cliente';
    const estadoLabel = estado || 'Pendiente despacho';

    showConfirmModal(
        '🚚 ¿Guardar despacho?',
        `Vas a guardar el despacho <b>${numero}</b> de <b>${cliente}</b> como <b>"${estadoLabel}"</b>.`,
        '⚠️ Verifica destino, transportista y observaciones antes de continuar.',
        async function() {
            await _saveDespacho(estado);
        },
        '💾 Sí, guardar'
    );
}
window.saveDespacho = saveDespacho;



// ============================================================
// FUNCIÓN saveGuia CORREGIDA - CON FECHA Y HORA COMPLETA
// ============================================================
async function saveGuia(estado) {
    try {
        console.log('🔄 Guardando guía...', { estado });

        // ============================================================
        // 1. RECOLECTAR PRODUCTOS
        // ============================================================
        let productos = window._guiaProductos || [];

        if (productos.length === 0) {
            document.querySelectorAll('#guiaProductosBody tr').forEach(row => {
                const codigo = row.querySelector('.guia-producto-codigo')?.value || '';
                const descripcion = row.querySelector('.guia-producto-desc')?.value || '';
                const um = row.querySelector('.guia-producto-unidad')?.value || 'NIU';
                const cantidad = parseFloat(row.querySelector('.guia-producto-cant')?.value || 0);
                if (descripcion && cantidad > 0) {
                    productos.push({ codigo, producto: descripcion, um, cantidad });
                }
            });
        }

        if (productos.length === 0) {
            showToast('⚠️ Agrega al menos un producto a la guía', 'warning');
            return;
        }

        // ============================================================
        // 2. VALIDAR CAMPOS MÍNIMOS DEL CONDUCTOR/VEHÍCULO
        // ============================================================
        const placa = document.getElementById('guiaPlaca')?.value?.trim() || '';
        const conductorDni = document.getElementById('guiaConductorDNI')?.value?.trim() || '';
        const conductorNombre = document.getElementById('guiaConductorNombre')?.value?.trim() || '';
        const licencia = document.getElementById('guiaLicencia')?.value?.trim() || '';
        const modalidad = document.getElementById('guiaModalidadTransporte')?.value || 'PRIVADO';

        if (!placa || !conductorDni || !conductorNombre) {
            showToast('⚠️ Completa Placa, DNI y Nombre del conductor', 'warning');
            return;
        }

        // ============================================================
        // 3. 🔽 FECHA CON HORA - IGUAL QUE EN COMPROBANTES
        // ============================================================
        const ahora = new Date();
        const year = ahora.getFullYear();
        const month = String(ahora.getMonth() + 1).padStart(2, '0');
        const day = String(ahora.getDate()).padStart(2, '0');
        const hours = String(ahora.getHours()).padStart(2, '0');
        const minutes = String(ahora.getMinutes()).padStart(2, '0');
        const seconds = String(ahora.getSeconds()).padStart(2, '0');
        
        // Formato ISO completo con hora: 2026-08-28T16:17:30
        const fechaHoraISO = `${year}-${month}-${day}T${hours}:${minutes}:${seconds}`;
        const fechaSolo = `${year}-${month}-${day}`;

        console.log(`🕐 Fecha y hora actual: ${fechaHoraISO}`);

        // ============================================================
        // 4. ARMAR PAYLOAD CON FECHA Y HORA COMPLETA
        // ============================================================
        const data = {
            id: editingId,
            estado: estado || 'Borrador',
            serie: document.getElementById('guiaSerie')?.value || 'T001',
            numero: document.getElementById('guiaNumero')?.value?.trim() || '',  // vacío = el servidor asigna el correlativo

            // 🔽 ENVIAR FECHA CON HORA COMPLETA (IGUAL QUE COMPROBANTES)
            fecha_emision: fechaHoraISO,  // ← CON HORA COMPLETA
            fecha_traslado: fechaSolo,

            // ---- REMITENTE (fijo) ----
            ruc_remitente: document.getElementById('guiaRucRemitente')?.value || (window.EMPRESA_ACTIVA || {}).ruc || '20602095704',
            remitente_nombre: document.getElementById('guiaRemitenteNombre')?.value || (window.EMPRESA_ACTIVA || {}).razon_social || 'KCF CORPORACION E.I.R.L',
            remitente_direccion: document.getElementById('guiaOrigen')?.value || '',
            remitente_ubigeo: document.getElementById('guiaUbigeoOrigen')?.value || '150139',

            // ---- DESTINATARIO ----
            ruc_destinatario: document.getElementById('guiaRuc')?.value || '',
            destinatario_nombre: document.getElementById('guiaCliente')?.value || '',
            destinatario_direccion: document.getElementById('guiaDestino')?.value || '',
            destinatario_ubigeo: document.getElementById('guiaUbigeoDestino')?.value || '',

            // ---- TRANSPORTE / VEHÍCULO / CONDUCTOR ----
            modalidad_transporte: modalidad,
            placa_vehiculo: placa,
            conductor_dni: conductorDni,
            conductor_nombre: conductorNombre,
            licencia_conductor: licencia,

            // ---- TRANSPORTISTA (solo si modalidad = público) ----
            transportista_ruc: modalidad === 'PUBLICO'
                ? (document.getElementById('guiaTransportistaRUC')?.value || '') : '',
            transportista_nombre: modalidad === 'PUBLICO'
                ? (document.getElementById('guiaTransportistaNombre')?.value || '') : '',

            motivo_traslado: document.getElementById('guiaMotivo')?.value || 'VENTA',
            documento_asociado: document.getElementById('guiaCotizacion')?.value || '',
            orden_compra_cliente: document.getElementById('guiaOrdenCompra')?.value || '',
            factura: document.getElementById('guiaFactura')?.value || '',
            peso_total: parseFloat(document.getElementById('guiaPeso')?.value || 0),
            observaciones: document.getElementById('guiaObservaciones')?.value || '',
            items: productos
        };

        console.log('📦 Datos a guardar (guía):', data);
        console.log('📅 fecha_emision enviada:', data.fecha_emision);

        // ============================================================
        // 5. ENVIAR A LA API
        // ============================================================
        const response = await apiFetch('/ventas/api/guias/guardar', {
            method: 'POST',
            body: JSON.stringify(data)
        });

        if (response.success) {
            showToast(`✅ Guía guardada como: ${estado}`, 'success');
            closeModal('guiaModal');
            await loadGuias();
            window._guiaProductos = null;
        } else {
            showToast('❌ Error: ' + (response.error || 'No se pudo guardar'), 'error');
        }
    } catch (error) {
        console.error('❌ Error guardando guía:', error);
        showToast('❌ Error al guardar la guía: ' + error.message, 'error');
    }
}
window.saveGuia = saveGuia;

function renderComprobanteFormContent(isEdit, data) {
    const cotOptions = (cotizacionesData || []).map(q => 
        `<option value="${q.numero}" ${data?.cotizacion === q.numero ? 'selected' : ''}>${q.numero} - ${q.razon || 'Sin cliente'}</option>`
    ).join('');
    
    const guiaOptions = (guiasData || []).map(g => {
        const valor = `${g.serie}-${g.numero}`;
        return `<option value="${valor}" ${data?.guia === valor ? 'selected' : ''}>${valor} - ${g.cliente || 'Sin cliente'}</option>`;
    }).join('');
    
    const pcOptions = (pedidosData || []).map(p => 
        `<option value="${p.numero}" ${data?.pc === p.numero ? 'selected' : ''}>${p.numero} - ${p.cliente || 'Sin cliente'}</option>`
    ).join('');
    
    // Opciones de condición de pago
    const _condFac = window.normalizarCondicion ? window.normalizarCondicion(data?.condicion || data?.condicion_pago || '') : (data?.condicion || '');
    const _opcFac = ['Contado', 'Contra entrega', 'Crédito 7 días', 'Crédito 15 días', 'Crédito 30 días', 'Crédito 45 días', 'Crédito 60 días', 'Crédito 90 días', 'Crédito 120 días'];
    if (_condFac && !_opcFac.includes(_condFac)) _opcFac.push(_condFac);
    // Factura nueva: la condición empieza vacía y se llena sola (PC → guía → cliente); antes quedaba "Contado" sin avisar
    const condicionOptions = (_condFac ? '' : '<option value="" selected>— Se llena sola: elige PC, guía, cotización o RUC —</option>') +
        _opcFac.map(o => `<option value="${o}" ${_condFac === o ? 'selected' : ''}>${o}</option>`).join('');
    const _condicionOptionsAntiguas = `
        <option value="Contado" ${data?.condicion === 'Contado' ? 'selected' : ''}>Contado</option>
        <option value="Crédito 7 días" ${data?.condicion === 'Crédito 7 días' ? 'selected' : ''}>Crédito 7 días</option>
        <option value="Crédito 15 días" ${data?.condicion === 'Crédito 15 días' ? 'selected' : ''}>Crédito 15 días</option>
        <option value="Crédito 30 días" ${data?.condicion === 'Crédito 30 días' ? 'selected' : ''}>Crédito 30 días</option>
        <option value="Crédito 45 días" ${data?.condicion === 'Crédito 45 días' ? 'selected' : ''}>Crédito 45 días</option>
        <option value="Crédito 60 días" ${data?.condicion === 'Crédito 60 días' ? 'selected' : ''}>Crédito 60 días</option>
        <option value="Crédito 90 días" ${data?.condicion === 'Crédito 90 días' ? 'selected' : ''}>Crédito 90 días</option>
        <option value="Crédito 120 días" ${data?.condicion === 'Crédito 120 días' ? 'selected' : ''}>Crédito 120 días</option>
    `;
    
    // Estado del crédito (para retención)
    const estadoCreditoOptions = `
        <option value="Pendiente de aprobación" ${data?.estado_credito === 'Pendiente de aprobación' ? 'selected' : ''}>⏳ Pendiente de aprobación</option>
        <option value="Aceptada en Crédito" ${data?.estado_credito === 'Aceptada en Crédito' ? 'selected' : ''}>✅ Aceptada en Crédito</option>
        <option value="Rechazada" ${data?.estado_credito === 'Rechazada' ? 'selected' : ''}>❌ Rechazada</option>
        <option value="En revisión" ${data?.estado_credito === 'En revisión' ? 'selected' : ''}>🔍 En revisión</option>
    `;
    
    // ============================================================
    // 🔽 DATOS DE RETENCIÓN DEL IGV (3% para Perú)
    // ============================================================
    const tieneRetencion = data?.tiene_retencion || false;
    const porcentajeRetencion = data?.porcentaje_retencion || 3.00;
    const montoRetenido = data?.monto_retenido || 0;
    const montoTotal = data?.total || data?.monto || 0;
    const montoBaseRetencion = montoTotal;
    const montoRetenidoCalculado = (montoBaseRetencion * porcentajeRetencion) / 100;
    
    // Productos
    const productos = data?.items || [];
    const productosHtml = productos.length > 0 ? 
        renderProductosComprobanteHTML(productos) : 
        '<div style="padding:20px;text-align:center;color:#94A3B8;">📭 Seleccione una cotización o guía para ver los productos</div>';
    
    return `
        <!-- SECCIÓN: DOCUMENTOS VINCULADOS -->
        <div class="ficha-section">
            <div class="ficha-section-title">🧾 Documentos vinculados</div>
            <div class="ficha-grid">
                <div class="form-field col-4">
                    <label>Cotización vinculada</label>
                    <select id="compCotizacion" onchange="cargarProductosComprobanteDesdeCotizacion(this.value)">
                        <option value="">-- Ninguna --</option>
                        ${cotOptions || '<option value="" disabled>Sin cotizaciones</option>'}
                    </select>
                </div>
                <div class="form-field col-4">
                    <label>Guía de Remisión vinculada</label>
                    <select id="compGuia" onchange="loadComprobanteFromGuia(this.value); actualizarObservacionesComprobante()">
                        <option value="">-- Ninguna --</option>
                        ${guiaOptions || '<option value="" disabled>Sin guías</option>'}
                    </select>
                </div>
                <div class="form-field col-4">
                    <label>PC vinculado</label>
                    <select id="compPC" onchange="loadComprobanteFromPC(this.value); actualizarObservacionesComprobante()">
                        <option value="">-- Ninguno --</option>
                        ${pcOptions || '<option value="" disabled>Sin PCs</option>'}
                    </select>
                </div>
            </div>
        </div>

        <!-- ============================================================ -->
        <!-- 🔽 NUEVA SECCIÓN: ORDEN DE COMPRA MANUAL (OPCIONAL)        -->
        <!-- ============================================================ -->
        <div class="ficha-section">
            <div class="ficha-grid">
                <div class="form-field col-12">
                    <label>N° Orden de Compra (opcional)</label>
                    <input id="compOrdenCompra" 
                           placeholder="Ej: OC-04705 (se mostrará en el PDF si lo ingresas)" 
                           value="${data?.orden_compra_cliente || ''}">
                </div>
            </div>
        </div>
        
        <!-- SECCIÓN: DATOS DEL COMPROBANTE -->
        <div class="ficha-section">
            <div class="ficha-grid">
                <div class="form-field col-3">
                    <label>Tipo</label>
                    <select id="compTipo">
                        <option value="Factura" ${data?.tipo === 'Factura' ? 'selected' : ''}>Factura</option>
                        <option value="Boleta" ${data?.tipo === 'Boleta' ? 'selected' : ''}>Boleta</option>
                    </select>
                </div>
                <div class="form-field col-3">
                    <label>Serie</label>
                    <input id="compSerie" value="${data?.serie || 'F001'}">
                </div>
                <div class="form-field col-3">
                    <label>Número</label>
                    <input id="compNumero" value="${data?.numero || ''}" placeholder="Automático">
                </div>
                <div class="form-field col-3">
                    <label>Estado</label>
                    <select id="compEstado">
                        ${['Borrador','Emitido','Enviado','Pagado','Anulado'].map(s => `<option value="${s}" ${data?.estado === s ? 'selected' : ''}>${s}</option>`).join('')}
                    </select>
                </div>
                <div class="form-field col-4">
                    <label>Cliente</label>
                    <input id="compCliente" value="${data?.cliente || ''}" placeholder="Razón social">
                </div>
                <div class="form-field col-4">
                    <label>RUC</label>
                    <input id="compRuc" value="${data?.ruc || ''}" placeholder="12345678901">
                </div>
                <div class="form-field col-4">
                    <label>Email</label>
                    <input id="compEmail" value="${data?.cliente_email || data?.email || ''}" placeholder="cliente@email.com">
                </div>
                <div class="form-field col-4">
                    <label>Teléfono</label>
                    <input id="compTelefono" value="${data?.cliente_telefono || data?.telefono || ''}" placeholder="999999999">
                </div>
                <div class="form-field col-4">
                    <label>Dirección</label>
                    <input id="compDireccion" value="${data?.cliente_direccion || data?.direccion || ''}" placeholder="Dirección del cliente">
                </div>
                <div class="form-field col-4">
                    <label>Monto Total</label>
                    <input id="compMonto" type="number" value="${data?.total || data?.monto || 0}" step="0.01" oninput="calcularRetencionComprobante()">
                </div>
                <div class="form-field col-4">
                    <label>Condición de pago</label>
                    <select id="compCondicion" onchange="actualizarEstadoRetencion(); calcularRetencionComprobante()">
                        ${condicionOptions}
                    </select>
                </div>
            </div>
        </div>
        
        <!-- ============================================================ -->
        <!-- 🔽 SECCIÓN DE RETENCIÓN DEL IGV (3% - LEY PERUANA) -->
        <!-- ============================================================ -->
        <div class="ficha-section" style="border: 2px solid #E5E7EB; background: #F8FAFC; margin-bottom: 10px;">
            <div class="ficha-section-title" style="background: #F1F5F9; border-bottom: 1px solid #E5E7EB; display: flex; justify-content: space-between; align-items: center;">
                <span style="color: #0F172A; font-weight: 900;">🔒 Retención del IGV (3%)</span>
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span style="font-size: 11px; color: #64748B; font-weight: 700;" id="retencionStatusLabel">
                        ${tieneRetencion ? '✅ Activa' : '⭕ Inactiva'}
                    </span>
                    <button type="button" id="btnToggleRetencion" 
                        onclick="toggleRetencion()"
                        style="
                            padding: 4px 16px;
                            border-radius: 20px;
                            border: 2px solid ${tieneRetencion ? '#DC2626' : '#22C55E'};
                            background: ${tieneRetencion ? '#FEE2E2' : '#DCFCE7'};
                            color: ${tieneRetencion ? '#991B1B' : '#166534'};
                            font-weight: 900;
                            font-size: 11px;
                            cursor: pointer;
                            transition: all 0.3s ease;
                            display: flex;
                            align-items: center;
                            gap: 6px;
                        "
                        onmouseover="this.style.transform='scale(1.02)'"
                        onmouseout="this.style.transform='scale(1)'">
                        <span id="btnToggleIcon">${tieneRetencion ? '🔴' : '🟢'}</span>
                        <span id="btnToggleText">${tieneRetencion ? 'Desactivar' : 'Activar'}</span>
                    </button>
                </div>
            </div>
            
            <!-- Contenido de retención (se muestra/oculta según el toggle) -->
            <div id="retencionContent" style="${tieneRetencion ? 'display:block;' : 'display:none;'} padding: 10px 14px; background: #FFFFFF;">
                <div class="ficha-grid" style="background: #F8FAFC; padding: 10px; border-radius: 8px;">
                    
                    <!-- Alerta informativa -->
                    <div style="grid-column: span 12; background: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 8px; padding: 8px 12px; margin-bottom: 4px; font-size: 11px; color: #1E3A8A; font-weight: 700; display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 16px;">📌</span>
                        <span>Según normativa peruana, la retención del IGV es del <strong>3%</strong> sobre el importe total de la operación. 
                        Solo aplica en operaciones gravadas con el IGV que superen los <strong>S/ 700</strong>.</span>
                    </div>
                    
                    <!-- Alerta si la condición NO es crédito pero la retención está activa -->
                    <div id="retencionAlert" style="display: ${tieneRetencion && !data?.condicion?.includes('Crédito') ? 'block' : 'none'}; 
                        grid-column: span 12;
                        background: #FFF7ED; border: 1px solid #FDBA74; border-radius: 8px; 
                        padding: 8px 12px; margin-bottom: 4px; font-size: 11px; color: #9A3412; font-weight: 700;">
                        ⚠️ La retención está activa pero la condición de pago NO es crédito. Verifica que sea correcto.
                    </div>
                    
                    <div class="form-field col-3">
                        <label style="font-weight: 900;">Estado del Crédito</label>
                        <select id="compEstadoCredito" style="font-weight: 900; border: 2px solid #2563EB;">
                            ${estadoCreditoOptions}
                        </select>
                    </div>
                    <div class="form-field col-2">
                        <label style="font-weight: 900;">Fecha Aprobación</label>
                        <input id="compFechaAprobacion" type="date" value="${data?.fecha_aprobacion || today()}" style="font-weight: 800;">
                    </div>
                    <div class="form-field col-2">
                        <label style="font-weight: 900; color: #DC2626;">Fecha Vencimiento</label>
                        <input id="compFechaVencimiento" type="date" value="${data?.fecha_vencimiento || ''}" style="font-weight: 800; color: #DC2626;" readonly>
                    </div>
                    <div class="form-field col-2">
                        <label style="font-weight: 900; color: #1D4ED8;">Días de Crédito</label>
                        <input id="compDiasCredito" type="number" value="${data?.dias_credito || 30}" min="1" max="180" style="font-weight: 900; color: #1D4ED8;" 
                               onchange="calcularFechaVencimientoComprobante(); calcularRetencionComprobante()">
                    </div>
                    <div class="form-field col-3">
                        <label style="font-weight: 900; color: #DC2626;">% Retención</label>
                        <input id="compPorcentajeRetencion" type="number" value="${data?.porcentaje_retencion || 3.00}" step="0.01" min="0" max="100" style="font-weight: 900; color: #DC2626; border-color: #DC2626;" 
                               onchange="calcularRetencionComprobante()">
                        <small style="color: #64748B; font-size: 8px;">Por defecto 3% (normativa peruana)</small>
                    </div>
                    <div class="form-field col-3">
                        <label style="font-weight: 900; color: #DC2626;">Monto Retenido</label>
                        <input id="compMontoRetenido" type="number" value="${data?.monto_retenido || montoRetenidoCalculado.toFixed(2)}" step="0.01" style="font-weight: 900; color: #DC2626; border-color: #DC2626;" 
                               onchange="actualizarMontoRetenidoManual()">
                    </div>
                    <div class="form-field col-3">
                        <label style="font-weight: 900; color: #059669;">Monto a Pagar (97%)</label>
                        <input id="compMontoAPagar" type="number" value="${(montoTotal - (data?.monto_retenido || montoRetenidoCalculado)).toFixed(2)}" step="0.01" style="font-weight: 900; color: #059669; border-color: #059669; background: #F1F5F9;" readonly>
                    </div>
                    <div class="form-field col-6">
                        <label style="font-weight: 900;">Observaciones de Retención</label>
                        <input id="compObsRetencion" value="${data?.obs_retencion || ''}" placeholder="Ej: Retención del 3% por IGV según normativa..." style="font-weight: 700; border: 1px solid #2563EB;">
                    </div>
                </div>
                
                <!-- Nota informativa -->
                <div style="padding: 8px 14px; background: #DBEAFE; border-radius: 8px; margin-top: 8px; display: flex; align-items: center; gap: 10px;">
                    <span style="font-size: 18px;">💡</span>
                    <span style="font-size: 11px; font-weight: 700; color: #1D4ED8;">
                        El cliente paga el <strong>97%</strong> del total y retiene el <strong>3%</strong> para entregarlo a la SUNAT.
                        Solo aplica en operaciones con IGV que superen los <strong>S/ 700</strong>.
                    </span>
                </div>
            </div>
        </div>
        
        <!-- SECCIÓN: PRODUCTOS -->
        <div class="ficha-section">
            <div class="ficha-section-title">🧾 Productos</div>
            <div id="compProducts">
                ${productosHtml}
            </div>
        </div>
        
        <!-- SECCIÓN: OBSERVACIONES -->
        <div class="ficha-section">
            <div class="ficha-grid">
                <div class="form-field col-12">
                    <label>Observaciones</label>
                    <textarea id="compObs" placeholder="Observaciones del comprobante">${data?.observaciones || ''}</textarea>
                </div>
            </div>
        </div>
    `;
}





// ============================================================
// FUNCIONES PARA RETENCIÓN DEL IGV (3% - LEY PERUANA)
// ============================================================

/**
 * Calcula la retención del IGV (3%) automáticamente
 */
function calcularRetencionComprobante() {
    const montoTotal = parseFloat(document.getElementById('compMonto')?.value) || 0;
    const porcentajeRetencion = parseFloat(document.getElementById('compPorcentajeRetencion')?.value) || 3.00;
    const diasCredito = parseInt(document.getElementById('compDiasCredito')?.value) || 30;
    
    // Calcular monto retenido (3% del total)
    const montoRetenido = (montoTotal * porcentajeRetencion) / 100;
    const montoAPagar = montoTotal - montoRetenido;
    
    // Actualizar campos
    const montoRetenidoInput = document.getElementById('compMontoRetenido');
    const montoAPagarInput = document.getElementById('compMontoAPagar');
    const retencionStatusLabel = document.getElementById('retencionStatusLabel');
    
    if (montoRetenidoInput) {
        montoRetenidoInput.value = montoRetenido.toFixed(2);
    }
    if (montoAPagarInput) {
        montoAPagarInput.value = montoAPagar.toFixed(2);
    }
    
    // Verificar si aplica retención (monto > S/ 700)
    const aplicaRetencion = montoTotal > 700;
    if (aplicaRetencion && retencionStatusLabel) {
        retencionStatusLabel.textContent = '✅ Activa (S/ ' + montoTotal.toFixed(2) + ' > S/ 700)';
        retencionStatusLabel.style.color = '#16A34A';
    } else if (!aplicaRetencion && retencionStatusLabel) {
        retencionStatusLabel.textContent = '⭕ No aplica (S/ ' + montoTotal.toFixed(2) + ' ≤ S/ 700)';
        retencionStatusLabel.style.color = '#F59E0B';
    }
    
    // Calcular fecha de vencimiento
    calcularFechaVencimientoComprobante();
    
    console.log(`📊 Retención calculada: ${porcentajeRetencion}% de S/ ${montoTotal.toFixed(2)} = S/ ${montoRetenido.toFixed(2)}. A pagar: S/ ${montoAPagar.toFixed(2)}`);
}

/**
 * Actualiza el monto retenido manualmente y recalcula el monto a pagar
 */
function actualizarMontoRetenidoManual() {
    const montoTotal = parseFloat(document.getElementById('compMonto')?.value) || 0;
    const montoRetenido = parseFloat(document.getElementById('compMontoRetenido')?.value) || 0;
    const montoAPagar = montoTotal - montoRetenido;
    
    const montoAPagarInput = document.getElementById('compMontoAPagar');
    if (montoAPagarInput) {
        montoAPagarInput.value = montoAPagar.toFixed(2);
    }
    
    // Calcular porcentaje efectivo
    const porcentajeRetencion = (montoRetenido / montoTotal) * 100;
    const porcentajeInput = document.getElementById('compPorcentajeRetencion');
    if (porcentajeInput && montoTotal > 0) {
        porcentajeInput.value = porcentajeRetencion.toFixed(2);
    }
}

/**
 * Alterna la visibilidad de la sección de retención
 */
function toggleRetencion() {
    const content = document.getElementById('retencionContent');
    const btn = document.getElementById('btnToggleRetencion');
    const icon = document.getElementById('btnToggleIcon');
    const text = document.getElementById('btnToggleText');
    const statusLabel = document.getElementById('retencionStatusLabel');
    
    if (!content || !btn) return;
    
    const isActive = content.style.display !== 'none';
    
    if (isActive) {
        // DESACTIVAR
        content.style.display = 'none';
        btn.style.borderColor = '#22C55E';
        btn.style.background = '#DCFCE7';
        btn.style.color = '#166534';
        icon.textContent = '🟢';
        text.textContent = 'Activar';
        statusLabel.textContent = '⭕ Inactiva';
        statusLabel.style.color = '#64748B';
        
        // Guardar estado
        const hiddenField = document.getElementById('compTieneRetencion');
        if (hiddenField) hiddenField.value = 'false';
        
        showToast('⭕ Retención desactivada', 'info');
    } else {
        // ACTIVAR
        content.style.display = 'block';
        btn.style.borderColor = '#DC2626';
        btn.style.background = '#FEE2E2';
        btn.style.color = '#991B1B';
        icon.textContent = '🔴';
        text.textContent = 'Desactivar';
        statusLabel.textContent = '✅ Activa';
        statusLabel.style.color = '#16A34A';
        
        // Guardar estado
        const hiddenField = document.getElementById('compTieneRetencion');
        if (hiddenField) hiddenField.value = 'true';
        
        // Calcular automáticamente
        calcularRetencionComprobante();
        
        showToast('🔒 Retención del IGV activada (3%)', 'success');
    }
}

/**
 * Actualiza el estado de la retención según la condición de pago
 */
function actualizarEstadoRetencion() {
    const condicion = document.getElementById('compCondicion')?.value || '';
    const esCredito = condicion.includes('Crédito');
    const content = document.getElementById('retencionContent');
    const alert = document.getElementById('retencionAlert');
    
    // Si la retención está activa y la condición cambia a NO crédito, mostrar alerta
    if (content && content.style.display !== 'none' && !esCredito) {
        if (alert) alert.style.display = 'block';
    } else {
        if (alert) alert.style.display = 'none';
    }
    
    // Si es crédito y la retención está activa, calcular automáticamente
    if (esCredito && content && content.style.display !== 'none') {
        calcularRetencionComprobante();
    }
}

/**
 * Renderiza la tabla de productos para el comprobante
 */
function renderProductosComprobanteHTML(productos) {
    if (!productos || productos.length === 0) {
        return '<div style="padding:20px;text-align:center;color:#94A3B8;">📭 No hay productos disponibles.</div>';
    }
    
    const total = productos.reduce((sum, p) => sum + (Number(p.cantidad || 0) * Number(p.valorVenta || 0) * 1.18), 0);
    
    return `
        <div class="table-scroll">
            <table class="master-table" style="font-size:11px;">
                <thead>
                    <tr>
                        <th>Item</th>
                        <th>Código de producto</th>
                        <th>Nombre producto</th>
                        <th>Marca</th>
                        <th>Modelo</th>
                        <th>Unidad</th>
                        <th>Cant.</th>
                        <th>Precio Unit.</th>
                        <th>Total</th>
                    </tr>
                </thead>
                <tbody>
                    ${productos.map((p, i) => {
                        const subtotal = Number(p.cantidad || 0) * Number(p.valorVenta || 0);
                        return `
                        <tr>
                            <td>${i + 1}</td>
                            <td>${p.codigo || '-'}</td>
                            <td class="left">${p.producto || p.descripcion || 'Sin nombre'}</td>
                            <td>${p.marca || '-'}</td>
                            <td>${p.modelo || '-'}</td>
                            <td>${p.um || 'NIU'}</td>
                            <td>${p.cantidad || 1}</td>
                            <td>S/ ${Number(p.valorVenta || 0).toFixed(2)}</td>
                            <td style="font-weight:900; color:#059669;">S/ ${subtotal.toFixed(2)}</td>
                        </tr>
                        `;
                    }).join('')}
                </tbody>
                <tfoot>
                    <tr>
                        <td colspan="7" style="text-align:right; font-weight:900; background:#F8FAFC;">TOTAL</td>
                        <td colspan="2" style="font-weight:900; font-size:14px; color:#EF233C; background:#FFF1F2;">
                            S/ ${total.toFixed(2)}
                        </td>
                    </tr>
                </tfoot>
            </table>
        </div>
    `;
}





/**
 * Alterna la visibilidad de la sección de retención
 */
function toggleRetencion() {
    const content = document.getElementById('retencionContent');
    const btn = document.getElementById('btnToggleRetencion');
    const icon = document.getElementById('btnToggleIcon');
    const text = document.getElementById('btnToggleText');
    const statusLabel = document.getElementById('retencionStatusLabel');
    
    if (!content || !btn) return;
    
    const isActive = content.style.display !== 'none';
    
    if (isActive) {
        // DESACTIVAR
        content.style.display = 'none';
        btn.style.borderColor = '#22C55E';
        btn.style.background = '#DCFCE7';
        btn.style.color = '#166534';
        icon.textContent = '🟢';
        text.textContent = 'Activar';
        statusLabel.textContent = '⭕ Inactiva';
        statusLabel.style.color = '#64748B';
        
        // 🔽 Guardar estado en un campo oculto
        const hiddenField = document.getElementById('compTieneRetencion');
        if (hiddenField) hiddenField.value = 'false';
        
        showToast('⭕ Retención desactivada', 'info');
    } else {
        // ACTIVAR
        content.style.display = 'block';
        btn.style.borderColor = '#DC2626';
        btn.style.background = '#FEE2E2';
        btn.style.color = '#991B1B';
        icon.textContent = '🔴';
        text.textContent = 'Desactivar';
        statusLabel.textContent = '✅ Activa';
        statusLabel.style.color = '#16A34A';
        
        // 🔽 Guardar estado en un campo oculto
        const hiddenField = document.getElementById('compTieneRetencion');
        if (hiddenField) hiddenField.value = 'true';
        
        // Calcular fecha de vencimiento automáticamente
        calcularFechaVencimientoComprobante();
        
        showToast('🔒 Retención activada', 'success');
    }
}

/**
 * Actualiza el estado de la retención según la condición de pago
 */
function actualizarEstadoRetencion() {
    const condicion = document.getElementById('compCondicion')?.value || '';
    const esCredito = condicion.includes('Crédito');
    const content = document.getElementById('retencionContent');
    const alert = document.getElementById('retencionAlert');
    
    // Si la retención está activa y la condición cambia a NO crédito, mostrar alerta
    if (content && content.style.display !== 'none' && !esCredito) {
        if (alert) alert.style.display = 'block';
    } else {
        if (alert) alert.style.display = 'none';
    }
    
    // Si es crédito y la retención está activa, calcular fecha de vencimiento
    if (esCredito && content && content.style.display !== 'none') {
        calcularFechaVencimientoComprobante();
    }
}
/**
 * Renderiza los productos en el comprobante
 */
function renderProductosComprobanteHTML(productos) {
    if (!productos || productos.length === 0) {
        return '<div style="padding:20px;text-align:center;color:#94A3B8;">📭 No hay productos disponibles.</div>';
    }
    
    const total = productos.reduce((sum, p) => sum + (Number(p.cantidad || 0) * Number(p.valorVenta || 0) * 1.18), 0);
    
    return `
        <div class="table-scroll">
            <table class="master-table" style="font-size:11px;">
                <thead>
                    <tr>
                        <th>Item</th>
                        <th>Código de producto</th>
                        <th>Nombre producto</th>
                        <th>Marca</th>
                        <th>Modelo</th>
                        <th>Unidad</th>
                        <th>Cant.</th>
                        <th>Precio Unit.</th>
                        <th>Total</th>
                    </tr>
                </thead>
                <tbody>
                    ${productos.map((p, i) => {
                        const subtotal = Number(p.cantidad || 0) * Number(p.valorVenta || 0);
                        return `
                        <tr>
                            <td>${i + 1}</td>
                            <td>${p.codigo || '-'}</td>
                            <td class="left">${p.producto || 'Sin nombre'}</td>
                            <td>${p.marca || '-'}</td>
                            <td>${p.modelo || '-'}</td>
                            <td>${p.um || 'NIU'}</td>
                            <td>${p.cantidad || 1}</td>
                            <td>S/ ${Number(p.valorVenta || 0).toFixed(2)}</td>
                            <td style="font-weight:900; color:#059669;">S/ ${subtotal.toFixed(2)}</td>
                        </tr>
                        `;
                    }).join('')}
                </tbody>
                <tfoot>
                    <tr>
                        <td colspan="7" style="text-align:right; font-weight:900; background:#F8FAFC;">TOTAL</td>
                        <td colspan="2" style="font-weight:900; font-size:14px; color:#EF233C; background:#FFF1F2;">
                            S/ ${total.toFixed(2)}
                        </td>
                    </tr>
                </tfoot>
            </table>
        </div>
    `;
}

/**
 * Calcula la fecha de vencimiento basado en los días de crédito
 */
function calcularFechaVencimientoComprobante() {
    const diasInput = document.getElementById('compDiasCredito');
    const fechaAprobacion = document.getElementById('compFechaAprobacion');
    const fechaVencimiento = document.getElementById('compFechaVencimiento');
    
    if (!diasInput || !fechaAprobacion || !fechaVencimiento) return;
    
    const dias = parseInt(diasInput.value) || 30;
    const fecha = new Date(fechaAprobacion.value || today());
    
    if (isNaN(fecha.getTime())) {
        fechaVencimiento.value = '';
        return;
    }
    
    fecha.setDate(fecha.getDate() + dias);
    const year = fecha.getFullYear();
    const month = String(fecha.getMonth() + 1).padStart(2, '0');
    const day = String(fecha.getDate()).padStart(2, '0');
    
    fechaVencimiento.value = `${year}-${month}-${day}`;
}

/**
 * Calcula la fecha de vencimiento basado en los días de crédito
 */
function calcularFechaVencimientoComprobante() {
    const diasInput = document.getElementById('compDiasCredito');
    const fechaAprobacion = document.getElementById('compFechaAprobacion');
    const fechaVencimiento = document.getElementById('compFechaVencimiento');
    
    if (!diasInput || !fechaAprobacion || !fechaVencimiento) return;
    
    const dias = parseInt(diasInput.value) || 30;
    const fecha = new Date(fechaAprobacion.value || today());
    
    if (isNaN(fecha.getTime())) {
        fechaVencimiento.value = '';
        return;
    }
    
    fecha.setDate(fecha.getDate() + dias);
    const year = fecha.getFullYear();
    const month = String(fecha.getMonth() + 1).padStart(2, '0');
    const day = String(fecha.getDate()).padStart(2, '0');
    
    fechaVencimiento.value = `${year}-${month}-${day}`;
}

/**
 * Abre el modal de comprobante con la sección de retención toggle
 */
async function openComprobanteModal(id = null) {
    console.log('🧾 Abriendo modal de comprobante', { id });
    editingId = id;
    const isEdit = id !== null;
    
    // Cerrar todos los modales primero
    const todosLosModales = document.querySelectorAll('.modal-bg.show, .modal-bg[style*="display: flex"]');
    todosLosModales.forEach(m => {
        if (m.id !== 'comprobanteModal') {
            m.classList.remove('show');
            m.style.display = 'none';
        }
    });
    
    const modal = document.getElementById('comprobanteModal');
    if (!modal) {
        console.error('❌ #comprobanteModal no encontrado');
        showToast('Error: Modal de comprobante no disponible', 'error');
        return;
    }
    
    modal.classList.remove('show');
    modal.style.cssText = '';
    
    const titleEl = document.getElementById('comprobanteModalTitle');
    if (titleEl) {
        titleEl.textContent = isEdit ? '✏️ Editar comprobante' : '🧾 Nueva factura / Boleta';
    }
    
    const formContainer = document.getElementById('comprobanteForm');
    if (!formContainer) {
        console.error('❌ #comprobanteForm no encontrado');
        showToast('Error: Formulario de comprobante no disponible', 'error');
        return;
    }
    
    // Cargar datos necesarios
    try {
        if (!guiasData || guiasData.length === 0) await loadGuias();
        if (!pedidosData || pedidosData.length === 0) await loadPedidos();
    } catch (error) {
        console.warn('⚠️ Error cargando datos:', error);
    }
    
    let data = null;
    if (isEdit) {
        try {
            const response = await apiFetch(`/ventas/api/comprobantes/${id}`);
            if (response.success) {
                data = response.data;
                console.log('📦 Datos del comprobante cargados:', data);
            }
        } catch (error) {
            console.warn('⚠️ Error cargando comprobante para edición:', error);
        }
    }
    
    // Renderizar el formulario con los datos
    formContainer.innerHTML = renderComprobanteFormContent(isEdit, data);
    
    // Si hay datos, cargarlos
    if (data && isEdit) {
        cargarDatosComprobante(data);
    }
    
    // 🔽 AGREGAR CAMPO OCULTO PARA GUARDAR ESTADO DE RETENCIÓN
    let hiddenField = document.getElementById('compTieneRetencion');
    if (!hiddenField) {
        hiddenField = document.createElement('input');
        hiddenField.type = 'hidden';
        hiddenField.id = 'compTieneRetencion';
        formContainer.appendChild(hiddenField);
    }
    hiddenField.value = data?.tiene_retencion ? 'true' : 'false';
    
    // 🔽 INICIALIZAR EL TOGGLE SEGÚN EL ESTADO GUARDADO
    setTimeout(() => {
        const tieneRetencion = data?.tiene_retencion || false;
        if (tieneRetencion) {
            // Si ya tenía retención, activarla
            const content = document.getElementById('retencionContent');
            const btn = document.getElementById('btnToggleRetencion');
            if (content) content.style.display = 'block';
            if (btn) {
                btn.style.borderColor = '#DC2626';
                btn.style.background = '#FEE2E2';
                btn.style.color = '#991B1B';
                document.getElementById('btnToggleIcon').textContent = '🔴';
                document.getElementById('btnToggleText').textContent = 'Desactivar';
                document.getElementById('retencionStatusLabel').textContent = '✅ Activa';
                document.getElementById('retencionStatusLabel').style.color = '#16A34A';
            }
            calcularFechaVencimientoComprobante();
        }
        
        // Verificar alerta de condición
        actualizarEstadoRetencion();
    }, 100);
    
    // Mostrar el modal
    modal.classList.add('show');
    modal.style.cssText = `
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        z-index: 9999999 !important;
        position: fixed !important;
        inset: 0 !important;
        background: rgba(15, 23, 42, 0.8) !important;
        backdrop-filter: blur(6px) !important;
        align-items: center !important;
        justify-content: center !important;
        padding: 20px !important;
        overflow: auto !important;
    `;
    
    const box = modal.querySelector('.modal-box');
    if (box) {
        box.style.cssText = `
            display: flex !important;
            visibility: visible !important;
            opacity: 1 !important;
            width: min(1100px, 96vw) !important;
            max-height: 95vh !important;
            background: #FFFFFF !important;
            border-radius: 16px !important;
            overflow: hidden !important;
            box-shadow: 0 30px 80px rgba(15,23,42,.45) !important;
            flex-direction: column !important;
            z-index: 9999999 !important;
            position: relative !important;
        `;
    }
    
    document.body.style.overflow = 'hidden';
    console.log('✅ Modal de comprobante abierto correctamente');
}

/**
 * Carga los datos de un comprobante existente en el formulario
 */
function cargarDatosComprobante(data) {
    const setVal = (id, value) => {
        const el = document.getElementById(id);
        if (el) {
            if (el.tagName === 'SELECT') {
                for (let opt of el.options) {
                    if (opt.value === value) {
                        opt.selected = true;
                        return;
                    }
                }
            } else {
                el.value = value ?? '';
            }
        }
    };
    
    setVal('compTipo', data.tipo_comprobante || data.tipo);
    setVal('compSerie', data.serie);
    setVal('compNumero', data.numero);
    setVal('compEstado', data.estado_sunat || data.estado);
    setVal('compCliente', data.cliente_nombre || data.cliente);
    setVal('compRuc', data.cliente_numero_doc || data.ruc);
    setVal('compEmail', data.cliente_email);
    setVal('compTelefono', data.cliente_telefono);
    setVal('compDireccion', data.cliente_direccion);
    setVal('compMonto', data.total || data.monto);
    setVal('compObs', data.observaciones);
    window.ponerCondicion('compCondicion', data.condicion_pago || data.condicion || 'Contado');
    setVal('compCotizacion', data.documento_asociado || data.cotizacion);
    setVal('compGuia', data.guia_vinculada || data.guia);
    setVal('compPC', data.pc_vinculado || data.pc);
    
    // 🔽 NUEVO CAMPO: ORDEN DE COMPRA
    setVal('compOrdenCompra', data.orden_compra_cliente || '');
    
    // 🔽 DATOS DE RETENCIÓN
    setVal('compEstadoCredito', data.estado_credito || 'Pendiente de aprobación');
    setVal('compFechaAprobacion', data.fecha_aprobacion || today());
    setVal('compFechaVencimiento', data.fecha_vencimiento || '');
    setVal('compDiasCredito', data.dias_credito || 30);
    setVal('compMontoRetenido', data.monto_retenido || 0);
    setVal('compObsRetencion', data.obs_retencion || '');
    
    // Productos
    const items = data.items_json || data.items || [];
    if (items.length > 0) {
        window._compProductos = items;
        const productsContainer = document.getElementById('compProducts');
        if (productsContainer) {
            productsContainer.innerHTML = renderProductosComprobanteHTML(items);
        }
    }
}

// ============================================================
// GUARDAR COMPROBANTE CON DATOS DE RETENCIÓN DEL 3%
// ============================================================

// ============================================================
// GUARDAR COMPROBANTE CON DATOS DE RETENCIÓN DEL 3% Y ORDEN DE COMPRA
// ============================================================

async function _saveComprobante(estado) {
    try {
        console.log('🔄 Guardando comprobante...', { estado });
        
        let productos = window._compProductos || [];
        
        // ============================================================
        // 🔽 OBTENER ESTADO DE RETENCIÓN
        // ============================================================
        const hiddenField = document.getElementById('compTieneRetencion');
        const tieneRetencion = hiddenField ? hiddenField.value === 'true' : false;
        
        // Condición de pago obligatoria: si sigue vacía se intenta llenar (PC → guía → cliente) antes de guardar
        if (!document.getElementById('compCondicion')?.value && typeof aplicarCondicionFactura === 'function') {
            await aplicarCondicionFactura(true);
        }
        const condicion = document.getElementById('compCondicion')?.value || '';
        if (!condicion) {
            showToast('⚠️ Falta la condición de pago. Elige el PC o la guía, o escríbela (el cliente no tiene una registrada).', 'error');
            document.getElementById('compCondicion')?.focus();
            return;
        }
        const esCredito = condicion.includes('Crédito');
        
        // ============================================================
        // 🔽 DATOS DE RETENCIÓN DEL IGV (3%)
        // ============================================================
        let estadoCredito = null;
        let fechaAprobacion = null;
        let fechaVencimiento = null;
        let diasCredito = null;
        let porcentajeRetencion = 3.00;
        let montoRetenido = 0;
        let montoAPagar = 0;
        let obsRetencion = '';
        
        // Solo guardar datos de retención si está activa
        if (tieneRetencion) {
            estadoCredito = document.getElementById('compEstadoCredito')?.value || 'Pendiente de aprobación';
            fechaAprobacion = document.getElementById('compFechaAprobacion')?.value || today();
            fechaVencimiento = document.getElementById('compFechaVencimiento')?.value || '';
            diasCredito = parseInt(document.getElementById('compDiasCredito')?.value) || 30;
            porcentajeRetencion = parseFloat(document.getElementById('compPorcentajeRetencion')?.value) || 3.00;
            montoRetenido = parseFloat(document.getElementById('compMontoRetenido')?.value) || 0;
            montoAPagar = parseFloat(document.getElementById('compMontoAPagar')?.value) || 0;
            obsRetencion = document.getElementById('compObsRetencion')?.value || '';
        }
        
        // Calcular totales
        const montoTotal = parseFloat(document.getElementById('compMonto')?.value || 0);
        const subtotalCalc = montoTotal / 1.18;
        const igvCalc = montoTotal - subtotalCalc;
        
        const data = {
            id: editingId,
            estado: estado || 'Borrador',
            tipo: document.getElementById('compTipo')?.value || 'Factura',
            serie: document.getElementById('compSerie')?.value || 'F001',
            numero: document.getElementById('compNumero')?.value?.trim() || '',  // vacío = el servidor asigna el siguiente correlativo
            fecha_emision: new Date().toISOString(),
            cotizacion: document.getElementById('compCotizacion')?.value || '',
            guia: document.getElementById('compGuia')?.value || '',
            pc: document.getElementById('compPC')?.value || '',
            // 🔽 NUEVO CAMPO: ORDEN DE COMPRA MANUAL
            orden_compra_cliente: document.getElementById('compOrdenCompra')?.value?.trim() || '',
            cliente: document.getElementById('compCliente')?.value || '',
            ruc: document.getElementById('compRuc')?.value || '',
            direccion: document.getElementById('compDireccion')?.value || '',
            email: document.getElementById('compEmail')?.value || '',
            telefono: document.getElementById('compTelefono')?.value || '',
            monto: montoTotal,
            total: montoTotal,
            subtotal: subtotalCalc,
            igv: igvCalc,
            condicion: condicion,
            observaciones: (v => v.charAt(0).toLocaleUpperCase('es-PE') + v.slice(1))((document.getElementById('compObs')?.value || '').replace(/^\s+/, '')),
            items: productos,
            // 🔽 DATOS DE RETENCIÓN (3% - LEY PERUANA)
            tiene_retencion: tieneRetencion,
            es_credito: esCredito,
            estado_credito: estadoCredito,
            fecha_aprobacion: fechaAprobacion,
            fecha_vencimiento: fechaVencimiento,
            dias_credito: diasCredito,
            porcentaje_retencion: porcentajeRetencion,
            monto_retenido: montoRetenido,
            monto_a_pagar: montoAPagar,
            obs_retencion: obsRetencion
        };
        
        console.log('📦 Datos a guardar con retención del 3%:', data);
        
        const response = await apiFetch('/ventas/api/comprobantes/guardar', {
            method: 'POST',
            body: JSON.stringify(data)
        });
        
        if (response.success) {
            const eraNueva = !data.id;
            showToast(`✅ Comprobante guardado como: ${estado}`, 'success');
            closeModal('comprobanteModal');
            await loadComprobantes();
            if (typeof loadGuias === 'function') { try { await loadGuias(); } catch (e) {} }
            window._compProductos = null;
            if (eraNueva) {
                const d = response.data || {};
                const nro = d.serie && d.numero ? `${d.serie}-${d.numero}` : (d.numero || '');
                window.mostrarPasos({
                    titulo: `✅ ¡${data.tipo || 'Factura'} creada con éxito!`,
                    subtitulo: nro ? `N° ${nro}${data.guia ? ' · de la guía ' + data.guia : ''}` : '',
                    pasos: [
                        ...(data.guia ? [{ texto: `Guía de remisión ${data.guia} creada.`, hecho: true }] : []),
                        { texto: `${data.tipo || 'Factura'} creada${nro ? ' (' + nro + ')' : ''}.`, hecho: true },
                        { texto: 'Ve al menú <b>"Facturas"</b> para revisarla, descargar el PDF o enviarla.' }
                    ],
                    boton: { texto: '🧾 Ir a Facturas', accion: () => irAPestanaYResaltar('comprobantes', 'comprobanteSearch', [nro, d.serie && d.numero ? `${d.serie}-${parseInt(d.numero, 10)}` : ''], typeof renderComprobantes === 'function' ? renderComprobantes : null) }
                });
            }
        } else {
            showToast('❌ Error: ' + (response.error || 'No se pudo guardar'), 'error');
        }
    } catch (error) {
        console.error('❌ Error guardando comprobante:', error);
        showToast('❌ No se guardó: ' + (error && error.message ? error.message : 'error al guardar el comprobante'), 'error');
    }
}




function saveComprobante(estado) {
    const tipo = document.getElementById('compTipo')?.value || 'Comprobante';
    const numero = document.getElementById('compNumero')?.value || 'nuevo';
    const cliente = document.getElementById('compCliente')?.value || 'el cliente';
    const estadoLabel = estado || 'Borrador';

    // El modal de la factura queda abierto mientras se confirma (antes se cerraba y, si cancelabas, se perdía lo escrito)
    setTimeout(() => {
        showConfirmModal(
            `🧾 ¿Guardar ${tipo.toLowerCase()}?`,
            `Vas a guardar el ${tipo.toLowerCase()} <b>${numero}</b> de <b>${cliente}</b> como <b>"${estadoLabel}"</b>.`,
            '⚠️ Verifica el monto y la condición de pago antes de continuar.',
            async function() {
                await _saveComprobante(estado);
            },
            '💾 Sí, guardar'
        );
    }, 50);
}
// ============================================================
// GUARDAR COMPROBANTE CON DATOS DE RETENCIÓN
// ============================================================

async function _saveNotaCredito(estado) {
    try {
        const data = {
            id: editingId,
            estado: estado || 'Borrador',
            serie: document.getElementById('notaSerie')?.value || 'FC01',
            numero: document.getElementById('notaNumero')?.value || '',
            comprobante_asociado: document.getElementById('notaComprobante')?.value || '',   // 🔧 antes: comprobante
            cliente_nombre: document.getElementById('notaCliente')?.value || '',             // 🔧 antes: cliente
            cliente_numero_doc: document.getElementById('notaRuc')?.value || '',             // 🔧 antes: ruc
            cliente_tipo_doc: 'RUC',                                                          // 🔧 NUEVO
            monto: parseFloat(document.getElementById('notaMonto')?.value || 0),
            motivo: document.getElementById('notaMotivo')?.value || '',
            observaciones: document.getElementById('notaObs')?.value || ''
        };
        
        const response = await apiFetch('/ventas/api/notas-credito/guardar', {
            method: 'POST',
            body: JSON.stringify(data)
        });
        
        if (response.success) {
            showToast(`Nota de crédito guardada como: ${estado}`, 'success');
            closeModal('notaCreditoModal');
            await loadNotas();
        } else {
            showToast('Error: ' + (response.error || 'No se pudo guardar'), 'error');
        }
    } catch (error) {
        console.error('❌ Error guardando nota:', error);
        showToast('Error al guardar la nota de crédito', 'error');
    }
}

function saveNotaCredito(estado) {
    const numero = document.getElementById('notaNumero')?.value || 'nueva nota';
    const cliente = document.getElementById('notaCliente')?.value || 'el cliente';
    const estadoLabel = estado || 'Borrador';

    showConfirmModal(
        '📝 ¿Guardar nota de crédito?',
        `Vas a guardar la nota de crédito <b>${numero}</b> de <b>${cliente}</b> como <b>"${estadoLabel}"</b>.`,
        '⚠️ Verifica el comprobante asociado y el motivo antes de continuar.',
        async function() {
            await _saveNotaCredito(estado);
        },
        '💾 Sí, guardar'
    );
}

async function _saveDevolucion(estado) {
    try {
        const data = {
            id: editingId,
            estado: estado || 'Pendiente',
            numero: document.getElementById('devNumero')?.value || '',
            comprobante_numero: document.getElementById('devComprobante')?.value || '',
            cliente: document.getElementById('devCliente')?.value || '',
            ruc: document.getElementById('devRuc')?.value || '',
            monto: parseFloat(document.getElementById('devMonto')?.value || 0),
            motivo: document.getElementById('devMotivo')?.value || '',
            observaciones: document.getElementById('devObs')?.value || ''
        };
        
        const response = await apiFetch('/ventas/api/devoluciones/guardar', {
            method: 'POST',
            body: JSON.stringify(data)
        });
        
        if (response.success) {

            

            showToast(`Devolución guardada como: ${estado}`, 'success');
            closeModal('devolucionModal');
            await loadDevoluciones();
        } else {
            showToast('Error: ' + (response.error || 'No se pudo guardar'), 'error');
        }
    } catch (error) {
        console.error('❌ Error guardando devolución:', error);
        showToast('Error al guardar la devolución', 'error');
    }
}

function saveDevolucion(estado) {
    const numero = document.getElementById('devNumero')?.value || 'nueva devolución';
    const cliente = document.getElementById('devCliente')?.value || 'el cliente';
    const estadoLabel = estado || 'Pendiente';

    showConfirmModal(
        '🔄 ¿Guardar devolución?',
        `Vas a guardar la devolución <b>${numero}</b> de <b>${cliente}</b> como <b>"${estadoLabel}"</b>.`,
        '⚠️ Verifica el motivo y el monto antes de continuar.',
        async function() {
            await _saveDevolucion(estado);
        },
        '💾 Sí, guardar'
    );
}

// ============================================================
// ACCIONES DE MENÚ (CON API REAL)
// ============================================================

// En ventas.js - Reemplaza la función marcarCotizacionAccepted
async function marcarCotizacionAccepted(id) {
    // Buscar la cotización para mostrar info
    const cotizacion = cotizacionesData.find(c => c.id === id);
    const numero = cotizacion?.numero || 'COT-XXXXXX';
    const cliente = cotizacion?.razon || 'Cliente';
    
    showConfirmModal(
        '✅ ¿Aceptar cotización?',
        `Estás a punto de marcar como <b>"Aceptada por Cliente"</b> la cotización <b>${numero}</b> del cliente <b>${cliente}</b>.`,
        '⚠️ Esta acción es irreversible. Una vez aceptada, no se podrá modificar el estado.',
        async function() {
            try {
                console.log(`🔄 Marcando cotización como aceptada, ID: ${id}`);
                showToast('⏳ Actualizando estado...', 'info');
                
                const response = await apiFetch(`/ventas/api/cotizaciones/${id}/toggle`, {
                    method: 'PUT',
                    body: JSON.stringify({ estado: 'Aceptada por Cliente' })
                });
                
                if (response.success) {
                    showToast('✅ Cotización marcada como aceptada por cliente', 'success');
                    await loadCotizaciones();
                } else {
                    showToast('❌ Error: ' + (response.error || 'No se pudo actualizar'), 'error');
                }
            } catch (error) {
                console.error('❌ Error:', error);
                showToast('❌ Error al actualizar estado: ' + error.message, 'error');
            }
        },
        '✅ Sí, aceptar'
    );
}


async function marcarCotizacionPending(id) {
    try {
        const response = await apiFetch(`/ventas/api/cotizaciones/${id}/toggle`, {
            method: 'PUT',
            body: JSON.stringify({ estado: 'En revisión' })
        });
        if (response.success) {
            showToast('Seguimiento cliente registrado', 'success');
            await loadCotizaciones();
        } else {
            showToast('Error: ' + (response.error || 'No se pudo actualizar'), 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showToast('Error al actualizar estado', 'error');
    }
}

async function marcarCotizacionNotClosed(id) {
    try {
        const response = await apiFetch(`/ventas/api/cotizaciones/${id}/toggle`, {
            method: 'PUT',
            
        });
        if (response.success) {
            
            await loadCotizaciones();
        } else {
            showToast('Error: ' + (response.error || 'No se pudo actualizar'), 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showToast('Error al actualizar estado', 'error');
    }
}

async function reactivarCotizacion(id) {
    try {
        const response = await apiFetch(`/ventas/api/cotizaciones/${id}/toggle`, {
            method: 'PUT',
            body: JSON.stringify({ estado: 'Borrador' })
        });
        if (response.success) {
            showToast('Cotización reactivada como borrador', 'success');
            await loadCotizaciones();
        } else {
            showToast('Error: ' + (response.error || 'No se pudo reactivar'), 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showToast('Error al reactivar cotización', 'error');
    }
}

// ventas.js - Modificar deleteCotizacion

async function deleteCotizacion(id) {
    const cotizacion = cotizacionesData.find(c => c.id === id);
    const numero = cotizacion?.numero || 'COT-XXXXXX';
    const cliente = cotizacion?.razon || 'Cliente';
    const estado = cotizacion?.estado || 'Desconocido';

    showDeleteConfirmModal(
        '🗑️ ¿Eliminar cotización?',
        `Estás a punto de eliminar la cotización <b>${numero}</b> del cliente <b>${cliente}</b>.<br>Estado actual: <b>${estado}</b>`,
        '⚠️ Esta acción cambiará el estado a "Anulada" y no podrá recuperarse. Se guardará un respaldo con el motivo indicado.',
        async function(motivo) {
            try {
                console.log(`🗑️ Eliminando cotización ID: ${id} - Motivo: ${motivo}`);
                showToast('⏳ Anulando cotización...', 'info');

                const response = await apiFetch(`/ventas/api/cotizaciones/${id}`, {
                    method: 'DELETE',
                    body: JSON.stringify({ motivo: motivo })
                });

                if (response.success) {
                    showToast('✅ Cotización anulada correctamente', 'success');
                    
                    // Recargar ambas listas
                    await loadCotizaciones();
                    await loadEliminadas();  // 👈 NUEVO
                    
                    // Si estamos en la pestaña de eliminadas, recargar
                    if (currentModule === 'eliminadas') {
                        renderEliminadas();
                    }
                } else {
                    showToast('❌ Error: ' + (response.error || 'No se pudo eliminar'), 'error');
                }
            } catch (error) {
                console.error('❌ Error eliminando cotización:', error);
                showToast('❌ Error al eliminar la cotización: ' + error.message, 'error');
            }
        }
    );
}

// ============================================================
// FUNCIÓN MARCAR DESPACHADO CORREGIDA - CON DATOS DEL CLIENTE
// ============================================================

async function marcarDespachado(id) {
    const despacho = despachosData.find(d => d.id === id);
    if (!despacho) {
        showToast('❌ Despacho no encontrado', 'error');
        return;
    }
    
    const numero = despacho.numero || 'DESP-XXXXXX';
    const cliente = despacho.cliente || 'Cliente';
    
    // De qué empresa y sede sale la mercadería: el stock se descuenta de ahí (Inventario)
    const ubic = await prepararUbicacionDespacho(id);
    if (!ubic) return;
    
    showConfirmModal(
        '🚚 ¿Marcar como despachado?',
        `Estás a punto de marcar como <b>"Despachado"</b> el despacho <b>${numero}</b> del cliente <b>${cliente}</b>.${ubic.html}`,
        '⚠️ Se descontará el stock de la empresa y sede elegidas y se creará una Guía de Remisión.',
        async function() {
            try {
                const [empresaId, almacenId] = String(window._despUbicacion || '|').split('|');
                if (!empresaId || !almacenId) {
                    showToast('❌ Elige de qué empresa y sede sale la mercadería', 'error');
                    return;
                }
                // Si en esa empresa/sede no alcanza, se avisa en grande antes de intentar (pedido de Erika 20/10/2026)
                const elegida = (window._despOpciones || []).find(o => `${o.empresa_id}|${o.almacen_id}` === `${empresaId}|${almacenId}`);
                if (elegida && !elegida.alcanza && (elegida.faltan || []).length) {
                    mostrarErrorStockDespacho(elegida.faltan.map(f => ({ ...f, empresa: elegida.empresa, sede: elegida.sede })));
                    return;
                }
                showToast('⏳ Procesando despacho...', 'info');
                
                // PASO 1: Cambiar estado del despacho (y descontar el stock)
                const resp = await fetch(`/ventas/api/despachos/${id}/toggle`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ estado: 'Despachado', empresa_id: empresaId, almacen_id: almacenId })
                });
                const response = await resp.json().catch(() => ({ success: false, error: `HTTP ${resp.status}` }));
                
                if (!resp.ok || !response.success) {
                    if (response.codigo === 'falta_stock') { mostrarErrorStockDespacho(response.faltan || [], response.error); return; }
                    showToast('❌ Error al marcar despacho: ' + (response.error || 'Desconocido'), 'error');
                    return;
                }
                
                showToast('✅ ' + (response.message || 'Despacho marcado como Despachado'), 'success');
                
                // ============================================================
                // OBTENER LOS ITEMS DEL DESPACHO
                // ============================================================
                let items = [];
                
                // Primero intentar obtener los items del despacho
                if (despacho.items && despacho.items.length > 0) {
                    items = despacho.items;
                }
                
                // Si no hay items en el despacho, buscar en el PC
                if (items.length === 0 && despacho.pc_id) {
                    try {
                        const pcResponse = await apiFetch(`/ventas/api/pedido-compra/${despacho.pc_id}`);
                        if (pcResponse.success && pcResponse.data) {
                            const pcItems = pcResponse.data.items || [];
                            items = pcItems.map(item => {
                                if (typeof item === 'object' && !Array.isArray(item)) {
                                    return {
                                        codigo: item.codigo || '',
                                        producto: item.producto || item.descripcion || 'Sin descripción',
                                        marca: item.marca || '',
                                        modelo: item.modelo || '',
                                        cantidad: parseFloat(item.cantidad_pc || item.cantidad || 1),
                                        um: item.um || 'NIU',
                                        stock: parseInt(item.stock || 0)
                                    };
                                }
                                if (Array.isArray(item)) {
                                    return {
                                        codigo: item[0] || '',
                                        producto: item[1] || 'Sin descripción',
                                        marca: item[2] || '',
                                        modelo: item[3] || '',
                                        cantidad: parseFloat(item[5] || item[3] || 1),
                                        um: 'NIU',
                                        stock: parseInt(item[8] || 0)
                                    };
                                }
                                return null;
                            }).filter(item => item !== null);
                        }
                    } catch (e) {
                        console.warn('⚠️ No se pudieron obtener items del PC:', e);
                    }
                }
                
                console.log('📦 Items finales para guía:', items);
                
                if (items.length === 0) {
                    showToast('⚠️ No hay productos para crear la guía', 'warning');
                    return;
                }
                
                // ============================================================
                // CREAR GUÍA DE REMISIÓN CON LOS ITEMS Y DATOS DEL CLIENTE
                // ============================================================
                const ahora = new Date();
                const year = ahora.getFullYear();
                const month = String(ahora.getMonth() + 1).padStart(2, '0');
                const day = String(ahora.getDate()).padStart(2, '0');
                const hours = String(ahora.getHours()).padStart(2, '0');
                const minutes = String(ahora.getMinutes()).padStart(2, '0');
                const seconds = String(ahora.getSeconds()).padStart(2, '0');
                
                // ✅ FORMATO ISO COMPLETO CON HORA
                const fechaHoraISO = `${year}-${month}-${day}T${hours}:${minutes}:${seconds}`;
                const fechaSolo = `${year}-${month}-${day}`;
                
                // ✅ OBTENER DATOS DEL CLIENTE DEL DESPACHO
                const rucCliente = despacho.ruc || '';
                const nombreCliente = despacho.cliente || '';
                const direccionCliente = despacho.destino || '';
                
                // ✅ OBTENER UBIGEO DEL CLIENTE (si existe en la cotización)
                let ubigeoCliente = '';
                let departamentoCliente = '';
                let provinciaCliente = '';
                let distritoCliente = '';
                
                // Si el despacho tiene cotizacion_numero, buscar la cotización para obtener el ubigeo
                if (despacho.cotizacion_numero) {
                    try {
                        const cotizacion = cotizacionesData.find(c => c.numero === despacho.cotizacion_numero);
                        if (cotizacion) {
                            // Buscar la cotización completa para obtener el ubigeo
                            const cotCompleta = await apiFetch(`/ventas/api/cotizaciones/${cotizacion.id}/completa`);
                            if (cotCompleta.success && cotCompleta.data) {
                                const data = cotCompleta.data;
                                if (data.cliente_ubigeo) {
                                    ubigeoCliente = data.cliente_ubigeo;
                                }
                                if (data.cliente_departamento) departamentoCliente = data.cliente_departamento;
                                if (data.cliente_provincia) provinciaCliente = data.cliente_provincia;
                                if (data.cliente_distrito) distritoCliente = data.cliente_distrito;
                            }
                        }
                    } catch (e) {
                        console.warn('⚠️ No se pudo obtener ubigeo de la cotización:', e);
                    }
                }
                
                // Si no hay departamento, usar valores por defecto o dejar vacío
                if (!departamentoCliente) {
                    departamentoCliente = 'LIMA';
                    provinciaCliente = 'LIMA';
                    distritoCliente = 'SAN MARTIN DE PORRES';
                    // Intentar adivinar por dirección (simple)
                    if (direccionCliente) {
                        const dirUpper = direccionCliente.toUpperCase();
                        if (dirUpper.includes('CALLAO')) {
                            departamentoCliente = 'CALLAO';
                            provinciaCliente = 'CALLAO';
                            distritoCliente = 'CALLAO';
                        }
                    }
                }
                
                // ✅ ORIGEN FIJO (KCF CORPORACION)
                const ORIGEN_FIJO = {
                    ruc: '20602095704',
                    nombre: 'KCF CORPORACION E.I.R.L',
                    direccion: 'JR. LAS ALMENDRAS VERDES NRO. 284 URB. VIRGEN DEL ROSARIO LIMA - LIMA - SAN MARTIN DE PORRES',
                    ubigeo: '150139'
                };
                aplicarEmpresaAlOrigen(ORIGEN_FIJO);   // multiempresa: remitente = empresa elegida arriba
                
                // ✅ GENERAR NÚMERO DE GUÍA
                const numeroGuia = `G-${year}${month}${day}-${String(ahora.getTime()).slice(-4)}`;
                
                // ✅ PREPARAR DATOS DE LA GUÍA CON TODOS LOS CAMPOS
                const guiaData = {
                    estado: 'Borrador',
                    serie: 'T001',
                    numero: numeroGuia,
                    // 🔽 DATOS DEL CLIENTE (DESTINATARIO)
                    ruc_destinatario: rucCliente,
                    destinatario_nombre: nombreCliente,
                    destinatario_direccion: direccionCliente,
                    destinatario_ubigeo: ubigeoCliente,
                    destinatario_departamento: departamentoCliente,
                    destinatario_provincia: provinciaCliente,
                    destinatario_distrito: distritoCliente,
                    // 🔽 DATOS DEL REMITENTE (FIJOS)
                    ruc_remitente: ORIGEN_FIJO.ruc,
                    remitente_nombre: ORIGEN_FIJO.nombre,
                    remitente_direccion: ORIGEN_FIJO.direccion,
                    remitente_ubigeo: ORIGEN_FIJO.ubigeo,
                    // 🔽 FECHAS
                    fecha_emision: fechaHoraISO,
                    fecha_traslado: fechaSolo,
                    // 🔽 DOCUMENTOS ASOCIADOS
                    documento_asociado: despacho.cotizacion_numero || '',
                    despacho_numero: despacho.numero || '',
                    orden_compra_cliente: '',
                    factura: '',
                    // 🔽 MOTIVO Y OBSERVACIONES
                    motivo_traslado: 'VENTA',
                    observaciones: `Guía generada automáticamente desde despacho ${despacho.numero}`,
                    // 🔽 PRODUCTOS
                    items: items.map(item => ({
                        codigo: item.codigo || '',
                        producto: item.producto || 'Sin descripción',
                        marca: item.marca || '',
                        modelo: item.modelo || '',
                        cantidad: parseFloat(item.cantidad || 1),
                        um: item.um || 'NIU',
                        stock: parseInt(item.stock || 0)
                    })),
                    // 🔽 PESO Y BULTOS (por defecto)
                    peso_total: 0,
                    numero_bultos: 1,
                    unidad_peso_bruto: 'KGM'
                };
                
                console.log('📦 Creando guía con datos completos:', guiaData);
                
                // ✅ ENVIAR A LA API DE GUÍAS
                const guiaResponse = await fetch('/ventas/api/guias/guardar', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(guiaData)
                });
                
                const guiaResult = await guiaResponse.json();
                console.log('📦 Respuesta creación guía:', guiaResult);
                
                if (guiaResult.success) {
                    showToast(`✅ Guía de Remisión creada con ${items.length} productos`, 'success');
                    
                    await loadDespachos();
                    await loadGuias();
                    
                    const g = guiaResult.data || {};
                    const nroGuia = g.serie && g.numero ? `${g.serie}-${g.numero}` : `T001-${guiaData.numero}`;
                    window.mostrarPasos({
                        titulo: '✅ ¡Guía creada con éxito!',
                        subtitulo: `Guía ${nroGuia} · ${items.length} producto(s) · en borrador`,
                        pasos: [
                            { texto: 'Paso 1: Ve al menú <b>"Guías de Remisión"</b>.' },
                            { texto: 'Paso 2: Busca tu guía y haz clic en <b>"Crear Factura"</b> (está en los 3 puntos <b>⋮</b> de su fila; te la dejo marcada en verde).' }
                        ],
                        boton: { texto: '🚚 Ir a Guías de Remisión', accion: () => irAPestanaYResaltar('guias', 'guiaSearch', String(g.numero || guiaData.numero), typeof renderGuias === 'function' ? renderGuias : null) }
                    });
                    
                } else {
                    if (['falta_stock', 'duplicado'].includes(guiaResult.codigo) && guiaResult.titulo) mostrarErrorStockDespacho(guiaResult.faltan || [], guiaResult.error, guiaResult.titulo);
                    showToast('⚠️ Despacho marcado, pero error al crear guía: ' + (guiaResult.error || 'Desconocido'), 'warning');
                }
                
            } catch (error) {
                console.error('❌ Error:', error);
                showToast('❌ Error al procesar: ' + error.message, 'error');
            }
        },
        '🚚 Sí, despachar'
    );
}


// En ventas.js - Reemplaza la función duplicateCotizacion
async function duplicateCotizacion(id) {
    // Buscar la cotización para mostrar info
    const cotizacion = cotizacionesData.find(c => c.id === id);
    const numero = cotizacion?.numero || 'COT-XXXXXX';
    const cliente = cotizacion?.razon || 'Cliente';
    
    showConfirmModal(
        '📋 ¿Duplicar cotización?',
        `Estás a punto de duplicar la cotización <b>${numero}</b> del cliente <b>${cliente}</b>.`,
        '⚠️ Esta acción creará una nueva cotización con el mismo contenido.',
        async function() {
            try {
                console.log(`📋 Duplicando cotización ID: ${id}`);
                showToast('⏳ Duplicando cotización...', 'info');
                
                const response = await apiFetch(`/ventas/api/cotizaciones/${id}/duplicar`, {
                    method: 'POST'
                });
                
                if (response.success) {
                    showToast(`✅ Cotización duplicada correctamente: ${response.data.numero}`, 'success');
                    await loadCotizaciones();
                    
                    // Opcional: Abrir la cotización duplicada para editar
                    setTimeout(() => {
                        if (response.data.id) {
                            openCotizacionModal(response.data.id);
                        }
                    }, 1000);
                } else {
                    showToast('❌ Error al duplicar: ' + (response.error || 'Desconocido'), 'error');
                }
            } catch (error) {
                console.error('❌ Error duplicando cotización:', error);
                showToast('❌ Error al duplicar la cotización: ' + error.message, 'error');
            }
        },
        '📋 Sí, duplicar'
    );
}

function sendCotizacionEmail(id) {
    showToast('Email enviado al cliente', 'success');
}

// ============================================================
// FUNCIÓN PARA GENERAR PDF DE COTIZACIÓN
// ============================================================
window.generateCotizacionPdf = async function(id) {
    console.log(`📄 Generando PDF para cotización ID: ${id}`);
    
    try {
        // Mostrar loading
        showToast('⏳ Generando PDF...', 'info');
        
        // Hacer la solicitud al endpoint que genera el PDF
        const response = await fetch(`/ventas/api/cotizaciones/${id}/pdf`, {
            method: 'GET',
            headers: {
                'Accept': 'application/pdf'
            }
        });
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || `HTTP ${response.status}`);
        }
        
        // Obtener el blob del PDF
        const blob = await response.blob();
        
        // Crear URL para descarga
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        
        // Obtener nombre del archivo desde el header Content-Disposition
        let filename = `cotizacion_${id}.pdf`;
        const contentDisposition = response.headers.get('Content-Disposition');
        if (contentDisposition) {
            const match = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
            if (match && match[1]) {
                filename = match[1].replace(/['"]/g, '');
            }
        }
        
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        
        showToast('✅ PDF generado correctamente', 'success');
        
    } catch (error) {
        console.error('❌ Error generando PDF:', error);
        showToast('❌ Error al generar el PDF: ' + error.message, 'error');
    }
};


// ventas.js - Función completa para generar PDF de guía

window.generateGuiaPdf = async function(id) {
    console.log(`📄 Generando PDF para guía ID: ${id}`);

    try {
        showToast('⏳ Generando PDF de la guía...', 'info');

        const response = await fetch(`/ventas/api/guias/${id}/pdf`, {
            method: 'GET',
            headers: {
                'Accept': 'application/pdf'
            }
        });

        // 🔍 Manejar específicamente el error 401 (No autorizado)
        if (response.status === 401) {
            showToast('⏳ Tu sesión ha expirado. Redirigiendo al login...', 'warning');
            setTimeout(() => {
                window.location.href = '/login';
            }, 2000);
            return;
        }

        // 🔍 Manejar específicamente el error 404 (No encontrado)
        if (response.status === 404) {
            showToast('❌ Guía no encontrada. Verifica el ID.', 'error');
            return;
        }

        // Para cualquier otro error (500, etc.)
        if (!response.ok) {
            let errorMsg = `Error ${response.status}`;
            try {
                const errorData = await response.json();
                errorMsg = errorData.error || errorData.message || errorMsg;
            } catch (e) {
                // Si no se puede parsear el error como JSON, usar el texto de estado
                errorMsg = `Error ${response.status}: ${response.statusText}`;
            }
            throw new Error(errorMsg);
        }

        // Obtener el blob del PDF
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;

        // Obtener nombre del archivo desde el header Content-Disposition
        let filename = `guia_${id}.pdf`;
        const contentDisposition = response.headers.get('Content-Disposition');
        if (contentDisposition) {
            const match = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
            if (match && match[1]) {
                filename = match[1].replace(/['"]/g, '');
            }
        }

        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);

        showToast('✅ PDF de guía generado correctamente', 'success');

    } catch (error) {
        console.error('❌ Error generando PDF de guía:', error);
        showToast(`❌ ${error.message}`, 'error');
    }
};

window.previewGuiaPdf = function(id) {
    try {
        // 🔽 RUTA CORRECTA PARA VISTA PREVIA
         const url = `/ventas/api/guias/${id}/pdf/preview`;
        window.open(url, '_blank');
        showToast('📄 Abriendo vista previa...', 'info');
    } catch (error) {
        showToast('❌ Error: ' + error.message, 'error');
    }
};

window.previewGuiaPdf = function(id) {
    console.log(`👁️ Vista previa PDF guía ID: ${id}`);
    
    try {
        const url = `/ventas/api/guias/${id}/pdf/preview`;
        window.open(url, '_blank');
        showToast('📄 Abriendo vista previa del PDF...', 'info');
    } catch (error) {
        console.error('❌ Error abriendo vista previa:', error);
        showToast('❌ Error al abrir la vista previa: ' + error.message, 'error');
    }
};


// ============================================================
// DESCARGAR RÓTULO DE GUÍA DE REMISIÓN
// ============================================================
window.descargarRotuloGuia = async function(id) {
    console.log(`🏷️ Descargando rótulo para guía ID: ${id}`);

    try {
        // Buscar la guía para verificar su estado
        const guia = guiasData.find(g => g.id === id);
        
        if (!guia) {
            showToast('❌ Guía no encontrada', 'error');
            return;
        }

        // Validar que la guía esté en estado "Generada" o "Emitida"
        const estado = (guia.estado || '').toUpperCase();
        const estadosPermitidos = ['GENERADA', 'EMITIDA', 'EMITIDO', 'ACEPTADA', 'ACEPTADO'];

        if (!estadosPermitidos.includes(estado)) {
            showToast(`⚠️ La guía debe estar en estado "Generada" o "Emitida" para descargar el rótulo. Estado actual: ${guia.estado}`, 'warning');
            return;
        }

        showToast('⏳ Generando rótulo...', 'info');

        // Hacer la petición al endpoint
        const response = await fetch(`/ventas/api/guias/${id}/rotulo`, {
            method: 'GET',
            headers: {
                'Accept': 'application/pdf'
            }
        });

        // Manejar errores específicos
        if (response.status === 401) {
            showToast('⏳ Tu sesión ha expirado. Redirigiendo al login...', 'warning');
            setTimeout(() => {
                window.location.href = '/login';
            }, 2000);
            return;
        }

        if (response.status === 404) {
            showToast('❌ Guía no encontrada.', 'error');
            return;
        }

        if (response.status === 400) {
            // Error de validación (guía no está en estado correcto)
            let errorMsg = 'La guía no está en un estado válido para generar el rótulo';
            try {
                const errorData = await response.json();
                errorMsg = errorData.error || errorMsg;
            } catch (e) {}
            showToast(`⚠️ ${errorMsg}`, 'warning');
            return;
        }

        if (!response.ok) {
            let errorMsg = `Error ${response.status}`;
            try {
                const errorData = await response.json();
                errorMsg = errorData.error || errorData.message || errorMsg;
            } catch (e) {
                errorMsg = `Error ${response.status}: ${response.statusText}`;
            }
            throw new Error(errorMsg);
        }

        // Obtener el blob del PDF
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;

        // Obtener nombre del archivo desde el header Content-Disposition
        let filename = `Rotulo_${guia.serie || 'T001'}_${guia.numero || id}.pdf`;
        const contentDisposition = response.headers.get('Content-Disposition');
        if (contentDisposition) {
            const match = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
            if (match && match[1]) {
                filename = match[1].replace(/['"]/g, '');
            }
        }

        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);

        showToast('✅ Rótulo descargado correctamente', 'success');

    } catch (error) {
        console.error('❌ Error descargando rótulo:', error);
        showToast(`❌ Error al generar el rótulo: ${error.message}`, 'error');
    }
};


// ============================================================
// VISTA PREVIA DEL RÓTULO DE GUÍA
// ============================================================
window.previewRotuloGuia = function(id) {
    console.log(`👁️ Vista previa del rótulo para guía ID: ${id}`);

    try {
        // Buscar la guía para verificar su estado
        const guia = guiasData.find(g => g.id === id);
        
        if (!guia) {
            showToast('❌ Guía no encontrada', 'error');
            return;
        }

        // Validar que la guía esté en estado "Generada" o "Emitida"
        const estado = (guia.estado || '').toUpperCase();
        const estadosPermitidos = ['GENERADA', 'EMITIDA', 'EMITIDO', 'ACEPTADA', 'ACEPTADO'];

        if (!estadosPermitidos.includes(estado)) {
            showToast(`⚠️ La guía debe estar en estado "Generada" o "Emitida" para ver el rótulo. Estado actual: ${guia.estado}`, 'warning');
            return;
        }

        // Abrir en nueva pestaña
        const url = `/ventas/api/guias/${id}/rotulo/preview`;
        window.open(url, '_blank');
        showToast('📄 Abriendo vista previa del rótulo...', 'info');

    } catch (error) {
        console.error('❌ Error abriendo vista previa del rótulo:', error);
        showToast('❌ Error al abrir la vista previa: ' + error.message, 'error');
    }
};

// En ventas.js - Reemplaza la función createDocFromCotizacion
window.createDocFromCotizacion = async function(id, tipo) {
    console.log(`📋 Creando ${tipo} desde cotización ID: ${id}`);
    
    // Buscar la cotización para mostrar info
    const cotizacion = cotizacionesData.find(c => c.id === id);
    const numero = cotizacion?.numero || 'COT-XXXXXX';
    const cliente = cotizacion?.razon || 'Cliente';
    
    const tipos = {
        'guia': { emoji: '📦', nombre: 'Guía de Remisión', color: '#16A34A' },
        'factura': { emoji: '🧾', nombre: 'Factura / Boleta', color: '#2563EB' },
        'despacho': { emoji: '🚚', nombre: 'Despacho', color: '#FF6600' }
    };
    
    const info = tipos[tipo] || { emoji: '📄', nombre: 'Documento', color: '#0F172A' };
    
    let mensajeExtra = '';
    if (tipo === 'guia') {
        mensajeExtra = 'La cotización debe estar <b>"Aceptada por Cliente"</b> para crear una guía.';
    }
    
    showConfirmModal(
        `${info.emoji} ¿Crear ${info.nombre}?`,
        `Estás a punto de crear un(a) <b>${info.nombre}</b> desde la cotización <b>${numero}</b> del cliente <b>${cliente}</b>.${mensajeExtra ? '<br><br>' + mensajeExtra : ''}`,
        `⚠️ Esta acción creará un nuevo registro de ${info.nombre.toLowerCase()} en el sistema.`,
        async function() {
            try {
                // Mostrar loading
                showToast('⏳ Cargando datos de la cotización...', 'info');
                
                // Obtener los datos completos de la cotización
                const response = await apiFetch(`/ventas/api/cotizaciones/${id}/completa`);
                
                if (!response.success) {
                    showToast('❌ Error al cargar cotización: ' + (response.error || 'Desconocido'), 'error');
                    return;
                }
                
                const cotizacion = preciosNetosCotizacion(response.data);
                console.log('📦 Datos de cotización:', cotizacion);
                
                // Verificar que la cotización esté aceptada para crear guía
                if (tipo === 'guia' && cotizacion.estado !== 'Aceptada por Cliente' && cotizacion.estado !== 'Aceptada') {
                    showToast('⚠️ La cotización debe estar "Aceptada por Cliente" para crear una guía', 'warning');
                    return;
                }
                
                // Cerrar el menú si está abierto
                document.querySelectorAll('.menu-pop').forEach(el => el.remove());
                
                switch(tipo) {
                    case 'guia':
                        switchTab('guias');
                        setTimeout(() => {
                            openGuiaModalWithData(null, cotizacion);
                        }, 300);
                        break;
                        
                    case 'factura':
                        switchTab('comprobantes');
                        setTimeout(() => {
                            openComprobanteModalWithData(null, cotizacion);
                        }, 300);
                        break;
                        
                    case 'despacho': {
                        // Orden del negocio: Cotización → PC → Despacho → Guía → Factura.
                        // El despacho se hace desde el PC de esta cotización (así lleva PC, productos y empresa,
                        // y después la guía y la factura lo encuentran). Antes se creaba suelto, sin PC ni productos.
                        if (typeof loadPedidos === 'function') {
                            try { await loadPedidos(); } catch (e) { console.warn('No se pudo leer los PC', e); }
                        }
                        const pcsCot = (pedidosData || []).filter(p =>
                            (Number(p.cotizacion_id) === Number(id) || (p.cotizacion_numero && p.cotizacion_numero === cotizacion.numero_cotizacion))
                            && !/anulad/i.test(p.estado || ''));
                        if (pcsCot.length === 0) {
                            showToast('⚠️ Esta cotización todavía no tiene PC del cliente. Primero registra el PC y luego envíalo a despacho.', 'warning');
                            switchTab('pedido_compra');
                            setTimeout(() => {
                                openPedidoCompraModalSAP('cot');
                                setTimeout(() => seleccionarCotizacionSAP(id), 400);
                            }, 300);
                            break;
                        }
                        const pcCot = pcsCot.sort((a, b) => b.id - a.id)[0];
                        enviarADespacho(pcCot.id);
                        break;
                    }
                        
                    default:
                        showToast(`Tipo "${tipo}" no soportado`, 'error');
                }
                
            } catch (error) {
                console.error('❌ Error creando documento:', error);
                showToast('❌ Error al crear el documento: ' + error.message, 'error');
            }
        },
        `${info.emoji} Sí, crear ${info.nombre}`
    );
};





function switchTab(tabId) {
    const tabs = document.querySelectorAll('.tab-btn');
    const sections = document.querySelectorAll('.section');
    
    // Actualizar tabs
    tabs.forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.tab === tabId) {
            btn.classList.add('active');
        }
    });
    
    // Actualizar secciones
    sections.forEach(section => {
        section.classList.remove('active');
        if (section.id === tabId) {
            section.classList.add('active');
        }
    });
    
    // Actualizar URL
    const url = new URL(window.location);
    url.searchParams.set('tab', tabId);
    window.history.pushState({}, '', url);
    
    // Cargar datos del módulo
    currentModule = tabId;
    
    // ============================================================
    // 🔽 SIEMPRE CARGAR COTIZACIONES PRIMERO
    // ============================================================
    async function cargarDatos() {
        // Primero cargar cotizaciones si no están cargadas
        if (typeof cotizacionesData === 'undefined' || cotizacionesData.length === 0) {
            await loadCotizaciones();
        }
        
        // Luego cargar el módulo específico
        switch(tabId) {
            case 'cotizaciones':
                // Ya están cargadas
                break;
            case 'pedido_compra':
                await loadPedidos();
                break;
            case 'despachar':
                await loadDespachos();
                break;
            case 'guias':
                await loadGuias();
                break;
            case 'comprobantes':
                await loadComprobantes();
                break;
            case 'notas_credito':
                await loadComprobantes();
                await loadNotas();
                break;
            case 'devoluciones':
                await loadDevoluciones();
                break;
        }
    }
    
    cargarDatos();
}



// ============================================================
// 🟢 SISTEMA DE BADGE - VERSIÓN ÚNICA Y ESTABLE
// ============================================================

(function() {
    'use strict';
    
    // Flag para evitar ejecuciones simultáneas
    let actualizando = false;
    let pestañaActual = null;
    let intervaloActivo = null;
    
    /**
     * Función principal - SOLO ESTA FUNCIÓN MANEJA EL BADGE
     */
    function actualizarBadge() {
        // Evitar ejecución simultánea
        if (actualizando) return;
        actualizando = true;
        
        try {
            // Buscar la pestaña activa
            const pestañaActiva = document.querySelector('.tab-btn.active');
            if (!pestañaActiva) {
                actualizando = false;
                return;
            }
            
            const tabId = pestañaActiva.dataset.tab;
            
            // Si ya estamos en la misma pestaña, no hacer nada
            if (tabId === pestañaActual) {
                // Solo asegurar que el badge existe
                asegurarBadge(pestañaActiva);
                actualizando = false;
                return;
            }
            
            // 🔥 REMOVER TODOS LOS BADGES EXISTENTES
            document.querySelectorAll('.tab-btn .tab-badge').forEach(b => b.remove());
            
            // 🔥 CREAR NUEVO BADGE SOLO EN LA PESTAÑA ACTIVA
            const badge = document.createElement('span');
            badge.className = 'tab-badge';
            badge.textContent = '📍';
            badge.style.cssText = `
                display: inline-block !important;
                font-size: 10px !important;
                background: #EF233C !important;
                color: #FFFFFF !important;
                padding: 1px 6px !important;
                border-radius: 4px !important;
                font-weight: 900 !important;
                margin-left: 4px !important;
                animation: pulse-badge 1.5s ease-in-out infinite !important;
                vertical-align: middle !important;
            `;
            pestañaActiva.appendChild(badge);
            
            // Actualizar estado
            pestañaActual = tabId;
            console.log('✅ Badge actualizado en:', pestañaActiva.textContent.trim());
            
        } catch (error) {
            console.warn('⚠️ Error actualizando badge:', error);
        } finally {
            actualizando = false;
        }
    }
    
    /**
     * Asegura que el badge exista (sin recrearlo)
     */
    function asegurarBadge(pestaña) {
        if (!pestaña) return;
        
        let badge = pestaña.querySelector('.tab-badge');
        if (!badge) {
            // Si no existe, crearlo
            badge = document.createElement('span');
            badge.className = 'tab-badge';
            badge.textContent = '📍';
            badge.style.cssText = `
                display: inline-block !important;
                font-size: 10px !important;
                background: #EF233C !important;
                color: #FFFFFF !important;
                padding: 1px 6px !important;
                border-radius: 4px !important;
                font-weight: 900 !important;
                margin-left: 4px !important;
                animation: pulse-badge 1.5s ease-in-out infinite !important;
                vertical-align: middle !important;
            `;
            pestaña.appendChild(badge);
        }
        
        // Asegurar que sea visible
        badge.style.display = 'inline-block';
        badge.style.visibility = 'visible';
        badge.style.opacity = '1';
    }

    // ============================================================
    // EVENTOS - SOLO LOS NECESARIOS
    // ============================================================
    
    // 1️⃣ Click en pestañas
    document.addEventListener('click', function(e) {
        const pestaña = e.target.closest('.tab-btn');
        if (pestaña && pestaña.dataset.tab) {
            // No prevenir default, solo actualizar después del cambio
            setTimeout(actualizarBadge, 50);
        }
    });
    
    // 2️⃣ Cambios de URL (popstate)
    window.addEventListener('popstate', function() {
        setTimeout(actualizarBadge, 50);
    });
    
    // 3️⃣ Observador SOLO para cambios de clase en pestañas
    const observer = new MutationObserver(function(mutations) {
        let necesitaActualizar = false;
        
        for (const mutation of mutations) {
            if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                const target = mutation.target;
                if (target.classList && target.classList.contains('tab-btn')) {
                    const wasActive = mutation.oldValue && mutation.oldValue.includes('active');
                    const isActive = target.classList.contains('active');
                    if (wasActive !== isActive) {
                        necesitaActualizar = true;
                        break;
                    }
                }
            }
        }
        
        if (necesitaActualizar) {
            setTimeout(actualizarBadge, 50);
        }
    });
    
    // Observar SOLO las pestañas
    document.querySelectorAll('.tab-btn').forEach(btn => {
        observer.observe(btn, { 
            attributes: true, 
            attributeFilter: ['class'],
            attributeOldValue: true
        });
    });
    
    // 4️⃣ Verificación periódica (cada 2 segundos, pero solo si es necesario)
    intervaloActivo = setInterval(function() {
        if (!document.hidden) {
            const pestañaActiva = document.querySelector('.tab-btn.active');
            if (!pestañaActiva) {
                console.log('⚠️ No hay pestaña activa - restaurando...');
                const urlParams = new URLSearchParams(window.location.search);
                const tab = urlParams.get('tab') || 'cotizaciones';
                // Activar la pestaña correcta
                const pestaña = document.querySelector(`.tab-btn[data-tab="${tab}"]`);
                if (pestaña) {
                    pestaña.classList.add('active');
                    setTimeout(actualizarBadge, 50);
                }
            } else {
                // Verificar que el badge existe
                const badge = pestañaActiva.querySelector('.tab-badge');
                if (!badge) {
                    console.log('⚠️ Badge desapareció - restaurando...');
                    asegurarBadge(pestañaActiva);
                }
            }
        }
    }, 3000);

    // ============================================================
    // INICIALIZACIÓN
    // ============================================================
    
    // Al cargar la página
    document.addEventListener('DOMContentLoaded', function() {
        setTimeout(actualizarBadge, 200);
        setTimeout(actualizarBadge, 500);
    });
    
    // Si el DOM ya está cargado, ejecutar inmediatamente
    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        setTimeout(actualizarBadge, 100);
    }
    
    // ============================================================
    // EXPORTAR FUNCIÓN ÚTIL
    // ============================================================
    window.actualizarBadge = actualizarBadge;
    window.forzarBadgeActivo = actualizarBadge;
    
    console.log('🟢 Sistema de badge simplificado inicializado');
})();

// ============================================================
// CSS PARA LA ANIMACIÓN DEL BADGE
// ============================================================

const badgeStyles = document.createElement('style');
badgeStyles.textContent = `
    @keyframes pulse-badge {
        0%, 100% { 
            transform: scale(1);
            box-shadow: 0 0 0 0 rgba(239, 35, 60, 0.4);
        }
        50% { 
            transform: scale(1.05);
            box-shadow: 0 0 8px 2px rgba(239, 35, 60, 0.3);
        }
    }
    
    .tab-badge {
        animation: pulse-badge 1.5s ease-in-out infinite !important;
    }
`;
document.head.appendChild(badgeStyles);

console.log('✅ Estilos del badge agregados');

// ============================================================
// FUNCIÓN PARA ABRIR MODAL DE GUÍA CON DATOS PRECARGADOS
// ============================================================
function openGuiaModalWithData(id, cotizacion) {
    // 1. Abre el modal real (mismo HTML de guia_modal.html, no lo destruye)
    window.openGuiaModal(id);

    // 2. Esperar a que el modal esté listo (ids, ubigeos, etc.) y precargar datos
    setTimeout(() => {
        const cotSel = document.getElementById('guiaCotizacion');
        if (cotSel) cotSel.value = cotizacion.numero_cotizacion || '';

        const cliente = document.getElementById('guiaCliente');
        if (cliente) cliente.value = cotizacion.cliente_razon_social || '';

        const ruc = document.getElementById('guiaRuc');
        if (ruc) ruc.value = cotizacion.cliente_ruc || '';

        const destino = document.getElementById('guiaDestino');
        if (destino) destino.value = cotizacion.direccion_entrega || cotizacion.cliente_direccion || '';

        const obs = document.getElementById('guiaObservaciones');
        if (obs) obs.value = `Generado desde cotización ${cotizacion.numero_cotizacion}`;

        // Precargar productos de la cotización en la tabla real (#guiaProductosBody)
        const productos = cotizacion.productos || [];
        window._guiaProductos = productos;
        const body = document.getElementById('guiaProductosBody');
        if (body && productos.length > 0) {
            body.innerHTML = '';
            productos.forEach(p => {
                agregarFilaProductoGuia(); // ya llama actualizarPesoTotalGuia() y actualizarContadorProductosGuia()
                const lastRow = body.lastElementChild;
                if (lastRow) {
                    const codigoInput = lastRow.querySelector('.guia-producto-codigo');
                    const descInput = lastRow.querySelector('.guia-producto-desc');
                    const cantInput = lastRow.querySelector('.guia-producto-cant');
                    if (codigoInput) codigoInput.value = p.codigo || '';
                    if (descInput) descInput.value = p.descripcion || p.producto || '';
                    if (cantInput) cantInput.value = p.cantidad || 1;
                }
            });
            // Recalcular peso/contador ahora que ya se llenaron los valores reales
            actualizarPesoTotalGuia();
            actualizarContadorProductosGuia();
              cargarUnidadesDeMedidaGuia();
        }
    }, 350);
}

function closeGuiaModal() {
    closeModal('guiaModal');
    window._guiaProductos = null;
}

// ============================================================
// FUNCIÓN PARA ABRIR MODAL DE COMPROBANTE CON DATOS PRECARGADOS
// ============================================================
async function openComprobanteModalWithData(id, cotizacion) {
    editingId = id;
    const isEdit = id !== null;
    const title = isEdit ? 'Editar comprobante' : 'Nuevo comprobante - desde cotización';
    document.getElementById('comprobanteModalTitle').textContent = title;
    
    const formContainer = document.getElementById('comprobanteForm');
    if (!formContainer) return;

    
    if (!guiasData || guiasData.length === 0) {
        await loadGuias();
    }
    if (!pedidosData || pedidosData.length === 0) {
        await loadPedidos();
    }
    
    
    const cotOptions = cotizacionesData.map(q => 
        `<option value="${q.numero}" ${q.numero === cotizacion.numero_cotizacion ? 'selected' : ''}>${q.numero} - ${q.razon || 'Sin cliente'}</option>`
    ).join('');
    
    
    const productos = cotizacion.productos || [];
    const productosHtml = productos.length > 0 ? productTableHtml(productos) : 
        '<div style="padding:20px;text-align:center;color:#94A3B8;">No hay productos en esta cotización.</div>';
    
    formContainer.innerHTML = `
    <div class="ficha-section">
        <div class="ficha-section-title">🧾 Documentos vinculados <small>Precargado desde cotización ${cotizacion.numero_cotizacion}</small></div>
        <div class="ficha-grid">
            <div class="form-field col-4">
                <label>Cotización vinculada</label>
                <select id="compCotizacion">
                    ${cotOptions}
                </select>
            </div>
            <div class="form-field col-4">
                <label>Guía de Remisión vinculada</label>
                <select id="compGuia" onchange="loadComprobanteFromGuia(this.value)">
                    <option value="">-- Ninguna --</option>
                    ${(guiasData || []).map(g => `<option value="${g.serie}-${g.numero}">${g.serie}-${g.numero} - ${g.cliente || 'Sin cliente'}</option>`).join('')}
                </select>
            </div>
            <div class="form-field col-4">
                <label>PC vinculado</label>
                <select id="compPC" onchange="loadComprobanteFromPC(this.value)">
                    <option value="">-- Ninguno --</option>
                    ${(pedidosData || []).map(p => `<option value="${p.numero}">${p.numero} - ${p.cliente || 'Sin cliente'}</option>`).join('')}
                </select>
            </div>
        </div>
    </div>
    <div class="ficha-section">
        <div class="ficha-grid">
            <div class="form-field col-3">
                <label>Tipo</label>
                <select id="compTipo">
                    <option>Factura</option>
                    <option>Boleta</option>
                </select>
            </div>
            <div class="form-field col-3">
                <label>Serie</label>
                <input id="compSerie" value="F001">
            </div>
            <div class="form-field col-3">
                <label>Número</label>
                <input id="compNumero" value="" placeholder="Automático">
            </div>
            <div class="form-field col-3">
                <label>Estado</label>
                <select id="compEstado">
                    ${options(ESTADOS_COMPROBANTE, 'Borrador')}
                </select>
            </div>
            <div class="form-field col-4">
                <label>Cliente</label>
                <input id="compCliente" value="${esc(cotizacion.cliente_razon_social || '')}">
            </div>
            <div class="form-field col-4">
                <label>RUC</label>
                <input id="compRuc" value="${esc(cotizacion.cliente_ruc || '')}">
            </div>
            <div class="form-field col-4">
                <label>Email</label>
                <input id="compEmail" value="${esc(cotizacion.cliente_email || cotizacion.email_cliente || cotizacion.email || '')}">
            </div>
            <div class="form-field col-4">
                <label>Teléfono</label>
                <input id="compTelefono" value="${esc(cotizacion.cliente_telefono || cotizacion.telefono_cliente || cotizacion.telefono || '')}">
            </div>
            <div class="form-field col-4">
                <label>Dirección</label>
                <input id="compDireccion" value="${esc(cotizacion.direccion_entrega || cotizacion.cliente_direccion || cotizacion.direccion || '')}">
            </div>
            <div class="form-field col-4">
                <label>Monto</label>
                <input id="compMonto" type="number" value="${cotizacion.total || 0}" step="0.01">
            </div>
            <div class="form-field col-4">
                <label>Condición de pago</label>
                <select id="compCondicion">
                    <option value="" selected>— Se llena sola desde el PC o el cliente —</option>
                    ${['Contado', 'Contra entrega', 'Crédito 7 días', 'Crédito 15 días', 'Crédito 30 días', 'Crédito 45 días', 'Crédito 60 días', 'Crédito 90 días', 'Crédito 120 días'].map(o => `<option>${o}</option>`).join('')}
                </select>
                <small style="display:block;margin-top:3px;font-size:11px;font-weight:700;color:#92400E">La condición sale del PC del cliente, no de la cotización</small>
            </div>
            <div class="form-field col-12">
                <label>Observaciones</label>
                <textarea id="compObs" placeholder="Observaciones del comprobante">Generado desde cotización ${cotizacion.numero_cotizacion}</textarea>
            </div>
        </div>
    </div>
    <div class="ficha-section">
        <div class="ficha-section-title">🧾 Productos</div>
        <div id="compProducts">
            ${productosHtml}
        </div>
    </div>
`;
    
    window._compProductos = productos;
    document.getElementById('comprobanteModal').classList.add('show');
    // Condición de pago desde el PC de esta cotización (o del cliente); antes quedaba "Contado" (20/10/2026)
    if (typeof aplicarCondicionFactura === 'function') setTimeout(aplicarCondicionFactura, 50);
}

function closeComprobanteModal() {
    closeModal('comprobanteModal');
    window._compProductos = null;
}

// ============================================================
// FUNCIÓN PARA ABRIR MODAL DE DESPACHO CON DATOS PRECARGADOS
// ============================================================
function openDespachoModalWithData(id, cotizacion) {
    editingId = id;
    const isEdit = id !== null;
    const title = isEdit ? 'Editar despacho' : 'Nuevo despacho - desde cotización';
    document.getElementById('despachoModalTitle').textContent = title;
    
    const formContainer = document.getElementById('despachoForm');
    if (!formContainer) return;
    
    const productos = cotizacion.productos || [];
    const productosHtml = productos.length > 0 ? productTableHtml(productos) : 
        '<div style="padding:20px;text-align:center;color:#94A3B8;">No hay productos en esta cotización.</div>';
    
    formContainer.innerHTML = `
        <div class="ficha-section">
            <div class="ficha-section-title">🚚 Despacho <small>Precargado desde cotización ${cotizacion.numero_cotizacion}</small></div>
            <div class="ficha-grid">
                <div class="form-field col-4">
                    <label>Cotización vinculada</label>
                    <input id="despachoCotizacion" value="${cotizacion.numero_cotizacion}" readonly style="background:#F1F5F9;">
                </div>
                <div class="form-field col-4">
                    <label>N° Despacho</label>
                    <input id="despachoNumero" value="DESP-${String(Date.now()).slice(-8)}">
                </div>
                <div class="form-field col-4">
                    <label>Estado</label>
                    <select id="despachoEstado">
                        ${options(ESTADOS_DESPACHO, 'Pendiente despacho')}
                    </select>
                </div>
                <div class="form-field col-4">
                    <label>Cliente</label>
                    <input id="despachoCliente" value="${esc(cotizacion.cliente_razon_social || '')}">
                </div>
                <div class="form-field col-4">
                    <label>RUC</label>
                    <input id="despachoRuc" value="${esc(cotizacion.cliente_ruc || '')}">
                </div>
                <div class="form-field col-4">
                    <label>Fecha despacho</label>
                    <input id="despachoFecha" type="date" value="${today()}">
                </div>
                <div class="form-field col-4">
                    <label>Origen</label>
                    <select id="despachoOrigen">
                        <option>ALM-SMP</option>
                        <option>OF-BRE</option>
                        <option>Almacén Central</option>
                    </select>
                </div>
                <div class="form-field col-4">
                    <label>Destino</label>
                    <input id="despachoDestino" value="${esc(cotizacion.direccion_entrega || cotizacion.cliente_direccion || '')}">
                </div>
                <div class="form-field col-4">
                    <label>Transportista</label>
                    <input id="despachoTransportista" placeholder="Nombre o razón social">
                </div>
                <div class="form-field col-12">
                    <label>Observaciones</label>
                    <textarea id="despachoObs" placeholder="Observaciones del despacho">Generado desde cotización ${cotizacion.numero_cotizacion}</textarea>
                </div>
            </div>
        </div>
        <div class="ficha-section">
            <div class="ficha-section-title">Productos a despachar</div>
            <div id="despachoProducts">
                ${productosHtml}
            </div>
        </div>
    `;
    
    window._despachoProductos = productos;
    document.getElementById('despachoModal').classList.add('show');
}

function closeDespachoModal() {
    closeModal('despachoModal');
}





// ============================================================
// MENÚ DE COTIZACIONES (MEJORADO)
// ============================================================
function showCotizacionMenu(event, id) {
    event.stopPropagation();
    
    // Buscar la cotización para ver su estado
    const cotizacion = cotizacionesData.find(c => c.id === id);
    const estado = cotizacion?.estado || '';
    const isAccepted = estado === 'Aceptada por Cliente' || estado === 'Aceptada';
    
    let menuHtml = `
        <button onclick="openCotizacionModal(${id});this.closest('.menu-pop').remove()">👁 Ver / Editar</button>
        <button onclick="duplicateCotizacion(${id});this.closest('.menu-pop').remove()">⧉ Duplicar</button>
        <button onclick="sendCotizacionEmail(${id});this.closest('.menu-pop').remove()">✉ Email</button>
        <button onclick="generateCotizacionPdf(${id});this.closest('.menu-pop').remove()">▣ PDF</button>
        <div style="height:1px;background:#E5E7EB;margin:4px 0;"></div>
    `;
    
    // Orden pedido en el Excel de pendientes: 1) Crear despacho, 2) Crear guía, 3) Crear factura en KCF
    menuHtml += `
        <button onclick="createDocFromCotizacion(${id},'despacho');this.closest('.menu-pop').remove()">🚚 Crear despacho</button>
    `;
    if (isAccepted) {
        menuHtml += `
            <button class="menu-accepted" onclick="createDocFromCotizacion(${id},'guia');this.closest('.menu-pop').remove()">📦 Crear guía</button>
            <button class="menu-accepted" onclick="createDocFromCotizacion(${id},'factura');this.closest('.menu-pop').remove()">🧾 Crear factura en KCF</button>
        `;
    }
    
    menuHtml += `
        <div style="height:1px;background:#E5E7EB;margin:4px 0;"></div>
        <button class="danger" onclick="deleteCotizacion(${id});this.closest('.menu-pop').remove()">🗑 Eliminar</button>
    `;
    
    createMenuWithClose(event, menuHtml);
}

// ============================================================
// FUNCIÓN PARA CARGAR GUÍA DESDE COTIZACIÓN SELECCIONADA
// ============================================================
window.loadGuiaFromCotizacion = function(numeroCotizacion) {
    if (!numeroCotizacion) return;
    
    const cotizacion = cotizacionesData.find(c => c.numero === numeroCotizacion);
    if (!cotizacion) {
        showToast('⚠️ Cotización no encontrada', 'warning');
        return;
    }
    
    showToast('⏳ Cargando datos de cotización...', 'info');
    
    // Cargar los datos de la cotización completa
    apiFetch(`/ventas/api/cotizaciones/${cotizacion.id}/completa`)
        .then(response => {
            if (response.success) {
                const data = preciosNetosCotizacion(response.data);
                document.getElementById('guiaCliente').value = data.cliente_razon_social || '';
                document.getElementById('guiaRuc').value = data.cliente_ruc || '';
                document.getElementById('guiaDestino').value = data.direccion_entrega || data.cliente_direccion || '';
                document.getElementById('guiaObs').value = `Generado desde cotización ${numeroCotizacion}`;
                
                // Actualizar productos
                const productos = data.productos || [];
                window._guiaProductos = productos;
                document.getElementById('guiaProducts').innerHTML = 
                    productos.length > 0 ? productTableHtml(productos) : 
                    '<div style="padding:20px;text-align:center;color:#94A3B8;">No hay productos en esta cotización.</div>';
                
                showToast('✅ Datos cargados desde cotización', 'success');
            } else {
                showToast('❌ Error al cargar datos: ' + (response.error || 'Desconocido'), 'error');
            }
        })
        .catch(error => {
            console.error('Error cargando cotización:', error);
            showToast('❌ Error al cargar datos de la cotización', 'error');
        });
};

//=====================================
// funcion para cargar Datos a Facturas
//=====================================
window.loadComprobanteFromCotizacion = function(numeroCotizacion) {
    if (!numeroCotizacion) return;

    const cotizacion = cotizacionesData.find(c => c.numero === numeroCotizacion);
    if (!cotizacion) {
        showToast('⚠️ Cotización no encontrada', 'warning');
        return;
    }

    showToast('⏳ Cargando datos de cotización...', 'info');

    apiFetch(`/ventas/api/cotizaciones/${cotizacion.id}/completa`)
        .then(response => {
            if (response.success) {
                const data = preciosNetosCotizacion(response.data);

                document.getElementById('compCliente').value = data.cliente_razon_social || '';
                document.getElementById('compRuc').value = data.cliente_ruc || '';
                document.getElementById('compMonto').value = data.total || 0;
                actualizarObservacionesComprobante();

                // Condición de pago: NO se copia de la cotización; la pone aplicarCondicionFactura (PC → guía → cliente)

                // Productos
                const productos = data.productos || [];
                window._compProductos = productos;
                document.getElementById('compProducts').innerHTML =
                    productos.length > 0 ? productTableHtml(productos) :
                    '<div style="padding:20px;text-align:center;color:#94A3B8;">No hay productos en esta cotización.</div>';

                showToast('✅ Datos cargados desde cotización', 'success');
            } else {
                showToast('❌ Error al cargar datos: ' + (response.error || 'Desconocido'), 'error');
            }
        })
        .catch(error => {
            console.error('Error cargando cotización:', error);
            showToast('❌ Error al cargar datos de la cotización', 'error');
        });
};

// ============================================================
// CONSTRUIR OBSERVACIONES A PARTIR DE LOS 3 DOCUMENTOS VINCULADOS
// ============================================================
function actualizarObservacionesComprobante() {
    const cot = document.getElementById('compCotizacion')?.value || '';
    const guia = document.getElementById('compGuia')?.value || '';
    const pc = document.getElementById('compPC')?.value || '';

    const partes = [];
    if (cot) partes.push(`cotización ${cot}`);
    if (guia) partes.push(`guía ${guia}`);
    if (pc) partes.push(`PC ${pc}`);

    const obsEl = document.getElementById('compObs');
    if (obsEl && partes.length > 0) {
        obsEl.value = `Generado desde ${partes.join(', ')}`;
    }
}





function validatePedidoCompra(id) {
    // Buscar el PC para mostrar info
    const pedido = pedidosData.find(p => p.id === id);
    if (!pedido) {
        showToast('❌ PC no encontrado', 'error');
        return;
    }
    
    const numero = pedido.numero || 'PC-XXXXXX';
    const cliente = pedido.cliente || 'Cliente';
    const estado = pedido.estado || 'Desconocido';
    
    // Verificar si ya está validado
    if (estado === 'Validado por Hellen' || estado === 'Validado') {
        showToast('⚠️ Este PC ya está validado', 'warning');
        return;
    }
    
    // Verificar si está anulado
    if (estado === 'Anulado') {
        showToast('⚠️ No se puede validar un PC anulado', 'warning');
        return;
    }
    
    showConfirmModal(
        '✅ ¿Validar PC?',
        `Estás a punto de marcar el PC <b>${numero}</b> del cliente <b>${cliente}</b> como <b>"Validado por Hellen"</b>.<br><br>Estado actual: <b>${estado}</b>`,
        '⚠️ Esta acción confirma que el PC ha sido revisado y validado por Hellen. El PC quedará listo para continuar con el proceso.',
        async function() {
            try {
                console.log(`✅ Validando PC ID: ${id}`);
                showToast('⏳ Validando PC...', 'info');
                
                // Cambiar estado a "Validado por Hellen"
                const response = await apiFetch(`/ventas/api/pedido-compra/${id}/toggle`, {
                    method: 'PUT',
                    body: JSON.stringify({ estado: 'Validado por Hellen' })
                });
                
                if (response.success) {
                    showToast('✅ PC validado por Hellen correctamente', 'success');
                    
                    // Recargar datos
                    await loadPedidos();
                    
                    // Actualizar validación si está visible
                    if (currentModule === 'validacion') {
                        renderValidacion();
                    }
                    
                    // Forzar actualización de la tabla
                    renderPedidos();
                    
                } else {
                    showToast('❌ Error: ' + (response.error || 'No se pudo validar el PC'), 'error');
                }
            } catch (error) {
                console.error('❌ Error validando PC:', error);
                showToast('❌ Error al validar el PC: ' + error.message, 'error');
            }
        },
        '✅ Sí, validar'
    );
}


//==========================================================
//Crear el despacho desde el PC
//==========================================================
async function createDespachoFromPedido(id) {
    try {
        showToast('⏳ Creando despacho desde el PC...', 'info');

        const response = await apiFetch(`/ventas/api/pedido-compra/${id}`);
        if (!response.success) {
            showToast('❌ No se pudo obtener el PC: ' + (response.error || 'Desconocido'), 'error');
            return;
        }
        const pc = response.data;

        const payload = {
            pc_id: pc.id,
            pc_numero: pc.numero || '',
            cotizacion_id: pc.cotizacion_id || null,
            cotizacion_numero: pc.cotizacion_numero || '',
            cliente: pc.cliente || '',
            ruc: pc.ruc || '',
            destino: pc.lugar_entrega || pc.entrega || '',
            origen: 'ALM-SMP',
            estado: 'Pendiente despacho',
            responsable: pc.responsable || 'Hellen',
            observaciones: `Generado automáticamente desde PC ${pc.numero || ''}`
        };

        const result = await apiFetch('/ventas/api/despachos/guardar', {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        if (result.success) {
            const nuevoDesp = (Array.isArray(result.data) ? result.data[0] : result.data) || {};  // antes decía "Despacho undefined"
            showToast(`✅ Despacho ${nuevoDesp.numero || ''} creado desde PC ${pc.numero}`, 'success');
            // Pedido de Erika 20/10/2026: llevar a "Entregas" y resaltar el despacho recién creado
            if (typeof loadDespachos === 'function') await loadDespachos();
            irAPestanaYResaltar('despachar', 'despachoSearch', [nuevoDesp.numero, pc.numero], typeof renderDespachos === 'function' ? renderDespachos : null);
        } else {
            showToast('❌ Error al crear el despacho: ' + (result.error || 'Desconocido'), 'error');
        }

    } catch (error) {
        console.error('❌ Error en createDespachoFromPedido:', error);
        showToast('❌ Error al crear el despacho: ' + error.message, 'error');
    }
}

//==========================================================
//Crear la Guia desde el PC
//==========================================================
async function createGuiaFromPedido(id) {
    try {
        showToast('⏳ Creando guía desde el PC...', 'info');

        // 1) Traer los datos completos del PC (mismo endpoint que ya usamos para editar)
        const response = await apiFetch(`/ventas/api/pedido-compra/${id}`);
        if (!response.success) {
            showToast('❌ No se pudo obtener el PC: ' + (response.error || 'Desconocido'), 'error');
            return;
        }
        const pc = response.data;

        const items = (pc.items || []).map(it => ({
            codigo: it.codigo || '',
            producto: it.producto || '',
            descripcion: it.producto || '',
            marca: it.marca || '',
            modelo: it.modelo || '',
            cantidad: it.cantidad_pc || it.cantidad_cotizada || 1,
            um: 'NIU'
        }));

        if (items.length === 0) {
            showToast('⚠️ Este PC no tiene productos, no se puede crear la guía', 'warning');
            return;
        }

        // 2) Armar el payload con las mismas claves que espera /ventas/api/guias/guardar
        const payload = {
            ruc: pc.ruc || '',
            cliente: pc.cliente || '',
            destino: pc.lugar_entrega || pc.entrega || '',
            motivo_traslado: 'VENTA',
            cotizacion_numero: pc.cotizacion_numero || pc.numero || '',
            peso_total: 0,
            items: items,
            observaciones: `Generado automáticamente desde PC ${pc.numero || ''}`,
            estado: 'BORRADOR'
        };

        // 3) Guardar de verdad
        const result = await apiFetch('/ventas/api/guias/guardar', {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        if (result.success) {
            showToast(`✅ Guía ${result.data.numero} creada desde PC ${pc.numero}`, 'success');
            if (typeof loadGuias === 'function') loadGuias();
        } else {
            showToast('❌ Error al crear la guía: ' + (result.error || 'Desconocido'), 'error');
        }

    } catch (error) {
        console.error('❌ Error en createGuiaFromPedido:', error);
        showToast('❌ Error al crear la guía: ' + error.message, 'error');
    }
}

//==========================================================
//Crear la factura desde el PC
//==========================================================
async function createFacturaFromPedido(id) {
    try {
        showToast('⏳ Creando factura desde el PC...', 'info');

        const response = await apiFetch(`/ventas/api/pedido-compra/${id}`);
        if (!response.success) {
            showToast('❌ No se pudo obtener el PC: ' + (response.error || 'Desconocido'), 'error');
            return;
        }
        const pc = response.data;

        const items = (pc.items || []).map(it => ({
            codigo: it.codigo || '',
            producto: it.producto || '',
            descripcion: it.producto || '',
            marca: it.marca || '',
            modelo: it.modelo || '',
            cantidad: it.cantidad_pc || it.cantidad_cotizada || 1,
            valorVenta: it.precio_pc || it.precio_cotizado || 0,
            um: 'NIU'
        }));

        if (items.length === 0) {
            showToast('⚠️ Este PC no tiene productos, no se puede crear la factura', 'warning');
            return;
        }

        const subtotal = items.reduce((s, it) => s + (Number(it.cantidad) * Number(it.valorVenta)), 0);
        const igv = subtotal * 0.18;
        const total = subtotal + igv;

        const payload = {
            tipo: 'FACTURA',
            serie: 'F001',
            moneda: 'PEN',
            cliente_tipo_doc: 'RUC',
            ruc: pc.ruc || '',
            cliente: pc.cliente || '',
            direccion: pc.lugar_entrega || pc.entrega || '',
            subtotal: subtotal,
            igv: igv,
            total: total,
            items: items,
            observaciones: `Generado automáticamente desde PC ${pc.numero || ''}`,
            estado: 'BORRADOR',
            cotizacion: pc.cotizacion_numero || ''
        };

        const result = await apiFetch('/ventas/api/comprobantes/guardar', {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        if (result.success) {
            showToast(`✅ Factura creada desde PC ${pc.numero}`, 'success');
            if (typeof loadComprobantes === 'function') loadComprobantes();
        } else {
            showToast('❌ Error al crear la factura: ' + (result.error || 'Desconocido'), 'error');
        }

    } catch (error) {
        console.error('❌ Error en createFacturaFromPedido:', error);
        showToast('❌ Error al crear la factura: ' + error.message, 'error');
    }
}

function deletePedidoCompra(id) {
    // Buscar el PC para mostrar info
    const pedido = pedidosData.find(p => p.id === id);
    if (!pedido) {
        showToast('❌ PC no encontrado', 'error');
        return;
    }
    
    const numero = pedido.numero || 'PC-XXXXXX';
    const cliente = pedido.cliente || 'Cliente';
    const estado = pedido.estado || 'Desconocido';
    
    // Verificar si el estado es 'Anulado' para mostrar mensaje diferente
    const esAnulado = estado === 'Anulado';
    const mensajeAdicional = esAnulado 
        ? 'El PC ya está anulado y será eliminado permanentemente.'
        : `⚠️ El PC está en estado "${estado}". Primero será anulado y luego eliminado permanentemente.`;
    
    showConfirmModal(
        '🗑️ ¿Eliminar PC permanentemente?',
        `Estás a punto de <b>ELIMINAR FÍSICAMENTE</b> el PC <b>${numero}</b> del cliente <b>${cliente}</b>.<br><br>${mensajeAdicional}`,
        '⚠️ ⚠️ ⚠️ ¡ATENCIÓN! Esta acción es IRREVERSIBLE. El registro será eliminado de la base de datos permanentemente.',
        async function() {
            try {
                console.log(`🗑️ Eliminando físicamente PC ID: ${id}, estado actual: ${estado}`);
                showToast('⏳ Procesando eliminación...', 'info');
                
                let pcId = id;
                
                // Si NO está anulado, primero anularlo
                if (estado !== 'Anulado') {
                    console.log(`🔄 Anulando PC primero...`);
                    
                    const toggleResponse = await apiFetch(`/ventas/api/pedido-compra/${id}/toggle`, {
                        method: 'PUT',
                        body: JSON.stringify({ estado: 'Anulado' })
                    });
                    
                    if (!toggleResponse.success) {
                        showToast('❌ Error al anular el PC: ' + (toggleResponse.error || 'No se pudo anular'), 'error');
                        return;
                    }
                    
                    showToast('✅ PC anulado, ahora eliminando...', 'info');
                    
                    // Esperar un momento para que la BD se actualice
                    await new Promise(resolve => setTimeout(resolve, 500));
                }
                
                // 🔽 ELIMINAR FÍSICAMENTE
                const response = await apiFetch(`/ventas/api/pedido-compra/${pcId}`, {
                    method: 'DELETE'
                });
                
                if (response.success) {
                    showToast('✅ PC eliminado permanentemente', 'success');
                    
                    // Recargar datos
                    await loadPedidos();
                    
                    // Actualizar validación si está visible
                    if (currentModule === 'validacion') {
                        renderValidacion();
                    }
                    
                    // Forzar actualización de la tabla
                    renderPedidos();
                    
                } else {
                    // Si el DELETE falla, mostrar el error específico
                    const errorMsg = response.error || 'No se pudo eliminar';
                    if (errorMsg.includes('Anulado')) {
                        showToast('❌ Solo se pueden eliminar PCs anulados. Intenta nuevamente.', 'error');
                    } else {
                        showToast('❌ Error: ' + errorMsg, 'error');
                    }
                }
            } catch (error) {
                console.error('❌ Error eliminando PC:', error);
                
                // Mostrar mensaje más descriptivo según el error
                if (error.message.includes('404')) {
                    showToast('❌ El PC ya no existe en el servidor', 'error');
                } else if (error.message.includes('400')) {
                    showToast('❌ Solo se pueden eliminar PCs en estado "Anulado"', 'error');
                } else {
                    showToast('❌ Error al eliminar el PC: ' + error.message, 'error');
                }
            }
        },
        '🗑️ Sí, eliminar permanentemente'
    );
}

// ventas.js - Agregar después de la función generateGuiaPdf

// ============================================================
// GENERAR PDF DE COMPROBANTE (FACTURA / BOLETA)
// ============================================================

window.generateComprobantePdf = async function(id) {
    console.log(`📄 Generando PDF para comprobante ID: ${id}`);
    
    try {
        showToast('⏳ Generando PDF del comprobante...', 'info');
        
        const response = await fetch(`/ventas/api/comprobantes/${id}/pdf`, {
            method: 'GET',
            headers: {
                'Accept': 'application/pdf'
            }
        });
        
        if (response.status === 401) {
            showToast('⏳ Tu sesión ha expirado. Redirigiendo al login...', 'warning');
            setTimeout(() => {
                window.location.href = '/login';
            }, 2000);
            return;
        }
        
        if (response.status === 404) {
            showToast('❌ Comprobante no encontrado.', 'error');
            return;
        }
        
        if (!response.ok) {
            let errorMsg = `Error ${response.status}`;
            try {
                const errorData = await response.json();
                errorMsg = errorData.error || errorData.message || errorMsg;
            } catch (e) {}
            throw new Error(errorMsg);
        }
        
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        
        let filename = `comprobante_${id}.pdf`;
        const contentDisposition = response.headers.get('Content-Disposition');
        if (contentDisposition) {
            const match = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
            if (match && match[1]) {
                filename = match[1].replace(/['"]/g, '');
            }
        }
        
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        
        showToast('✅ PDF del comprobante generado correctamente', 'success');
        
    } catch (error) {
        console.error('❌ Error generando PDF:', error);
        showToast(`❌ ${error.message}`, 'error');
    }
};

window.previewComprobantePdf = function(id) {
    try {
        const url = `/ventas/api/comprobantes/${id}/pdf/preview`;
        window.open(url, '_blank');
        showToast('📄 Abriendo vista previa del PDF...', 'info');
    } catch (error) {
        console.error('❌ Error abriendo vista previa:', error);
        showToast('❌ Error al abrir la vista previa: ' + error.message, 'error');
    }
};

function markGuiaEmitida(id) {
    showToast('Guía emitida correctamente', 'success');
}

// ============================================================
// ELIMINAR GUÍA (con anulación previa + eliminación física)
// ============================================================
async function deleteGuia(id) {
    const guia = guiasData.find(g => g.id === id);
    if (!guia) {
        showToast('❌ Guía no encontrada', 'error');
        return;
    }

    const numero = `${guia.serie || ''}-${guia.numero || ''}`;
    const cliente = guia.cliente || 'Cliente';
    const estadoActual = guia.estado || 'Desconocido';
    const esAnulada = (estadoActual || '').toUpperCase().includes('ANULAD');

    const mensajeAdicional = esAnulada
        ? 'La guía ya está anulada y será eliminada permanentemente.'
        : `⚠️ La guía está en estado "${estadoActual}". Primero será anulada y luego eliminada permanentemente.`;

    showConfirmModal(
        '🗑️ ¿Eliminar guía permanentemente?',
        `Estás a punto de <b>ELIMINAR FÍSICAMENTE</b> la guía <b>${numero}</b> del cliente <b>${cliente}</b>.<br><br>${mensajeAdicional}`,
        '⚠️ Esta acción es IRREVERSIBLE. El registro será eliminado de la base de datos permanentemente.',
        async function() {
            try {
                showToast('⏳ Procesando eliminación...', 'info');

                if (!esAnulada) {
                    const toggleResponse = await apiFetch(`/ventas/api/guias/${id}/toggle`, {
                        method: 'PUT',
                        body: JSON.stringify({ estado: 'Anulada' })
                    });
                    if (!toggleResponse.success) {
                        showToast('❌ Error al anular la guía: ' + (toggleResponse.error || 'No se pudo anular'), 'error');
                        return;
                    }
                    showToast('✅ Guía anulada, ahora eliminando...', 'info');
                    await new Promise(resolve => setTimeout(resolve, 400));
                }

                const response = await apiFetch(`/ventas/api/guias/${id}/permanente`, { method: 'DELETE' });

                if (response.success) {
                    showToast('✅ Guía eliminada permanentemente', 'success');
                    await loadGuias();
                } else {
                    showToast('❌ Error: ' + (response.error || 'No se pudo eliminar'), 'error');
                }
            } catch (error) {
                console.error('❌ Error eliminando guía:', error);
                showToast('❌ Error al eliminar la guía: ' + error.message, 'error');
            }
        },
        '🗑️ Sí, eliminar permanentemente'
    );
}

function generateComprobantePdf(id) {
    showToast('PDF de comprobante generado', 'success');
}

// En ventas.js - Reemplaza la función markComprobanteEmitido
function markComprobanteEmitido(id) {
    const comprobante = comprobantesData.find(c => c.id === id);
    const numero = comprobante?.numero || 'C-XXXXXX';
    const cliente = comprobante?.cliente || 'Cliente';
    
    showConfirmModal(
        '🧾 ¿Emitir comprobante?',
        `Estás a punto de emitir el comprobante <b>${numero}</b> del cliente <b>${cliente}</b>.`,
        '⚠️ Esta acción es irreversible. El comprobante quedará emitido oficialmente.',
        async function() {
            try {
                const response = await apiFetch(`/ventas/api/comprobantes/${id}/toggle`, {
                    method: 'PUT',
                    body: JSON.stringify({ estado: 'Emitido' })
                });
                if (response.success) {
                    showToast('✅ Comprobante emitido correctamente', 'success');
                    await loadComprobantes();
                } else {
                    showToast('❌ Error: ' + (response.error || 'No se pudo emitir'), 'error');
                }
            } catch (error) {
                console.error('❌ Error:', error);
                showToast('❌ Error al emitir comprobante', 'error');
            }
        },
        '🧾 Sí, emitir'
    );
}

// ============================================================
// ELIMINAR COMPROBANTE (con anulación previa + eliminación física)
// ============================================================
async function deleteComprobante(id) {
    const comprobante = comprobantesData.find(c => c.id === id);
    if (!comprobante) {
        showToast('❌ Comprobante no encontrado', 'error');
        return;
    }

    const numero = `${comprobante.serie || ''}-${comprobante.numero || ''}`;
    const cliente = comprobante.cliente || 'Cliente';
    const estadoActual = comprobante.estado || 'Desconocido';
    const esAnulado = (estadoActual || '').toUpperCase().includes('ANULAD');

    const mensajeAdicional = esAnulado
        ? 'El comprobante ya está anulado y será eliminado permanentemente.'
        : `⚠️ El comprobante está en estado "${estadoActual}". Primero será anulado y luego eliminado permanentemente.`;

    showConfirmModal(
        '🗑️ ¿Eliminar comprobante permanentemente?',
        `Estás a punto de <b>ELIMINAR FÍSICAMENTE</b> el comprobante <b>${numero}</b> del cliente <b>${cliente}</b>.<br><br>${mensajeAdicional}`,
        '⚠️ Esta acción es IRREVERSIBLE. El registro será eliminado de la base de datos permanentemente.',
        async function() {
            try {
                showToast('⏳ Procesando eliminación...', 'info');

                if (!esAnulado) {
                    const toggleResponse = await apiFetch(`/ventas/api/comprobantes/${id}/toggle`, {
                        method: 'PUT',
                        body: JSON.stringify({ estado: 'Anulado' })
                    });
                    if (!toggleResponse.success) {
                        showToast('❌ Error al anular el comprobante: ' + (toggleResponse.error || 'No se pudo anular'), 'error');
                        return;
                    }
                    showToast('✅ Comprobante anulado, ahora eliminando...', 'info');
                    await new Promise(resolve => setTimeout(resolve, 400));
                }

                const response = await apiFetch(`/ventas/api/comprobantes/${id}/permanente`, { method: 'DELETE' });

                if (response.success) {
                    showToast('✅ Comprobante eliminado permanentemente', 'success');
                    await loadComprobantes();
                } else {
                    showToast('❌ Error: ' + (response.error || 'No se pudo eliminar'), 'error');
                }
            } catch (error) {
                console.error('❌ Error eliminando comprobante:', error);
                showToast('❌ Error al eliminar el comprobante: ' + error.message, 'error');
            }
        },
        '🗑️ Sí, eliminar permanentemente'
    );
}

function generateNotaPdf(id) {
    showToast('PDF de nota de crédito generado', 'success');
}

function markNotaEmitida(id) {
    showToast('Nota de crédito emitida correctamente', 'success');
}

// ============================================================
// ELIMINAR NOTA DE CRÉDITO (con anulación previa + eliminación física)
// ============================================================
async function deleteNota(id) {
    const nota = notasData.find(n => n.id === id);
    if (!nota) {
        showToast('❌ Nota de crédito no encontrada', 'error');
        return;
    }

    const numero = `${nota.serie || ''}-${nota.numero || ''}`;
    const cliente = nota.cliente || 'Cliente';
    const estadoActual = nota.estado || 'Desconocido';
    const esAnulada = (estadoActual || '').toLowerCase() === 'anulada';

    const mensajeAdicional = esAnulada
        ? 'La nota de crédito ya está anulada y será eliminada permanentemente.'
        : `⚠️ La nota de crédito está en estado "${estadoActual}". Primero será anulada y luego eliminada permanentemente.`;

    showConfirmModal(
        '🗑️ ¿Eliminar nota de crédito permanentemente?',
        `Estás a punto de <b>ELIMINAR FÍSICAMENTE</b> la nota de crédito <b>${numero}</b> del cliente <b>${cliente}</b>.<br><br>${mensajeAdicional}`,
        '⚠️ Esta acción es IRREVERSIBLE. El registro será eliminado de la base de datos permanentemente.',
        async function() {
            try {
                showToast('⏳ Procesando eliminación...', 'info');

                if (!esAnulada) {
                    const toggleResponse = await apiFetch(`/ventas/api/notas-credito/${id}/toggle`, {
                        method: 'PUT',
                        body: JSON.stringify({ estado: 'Anulada' })
                    });
                    if (!toggleResponse.success) {
                        showToast('❌ Error al anular la nota de crédito: ' + (toggleResponse.error || 'No se pudo anular'), 'error');
                        return;
                    }
                    showToast('✅ Nota de crédito anulada, ahora eliminando...', 'info');
                    await new Promise(resolve => setTimeout(resolve, 400));
                }

                const response = await apiFetch(`/ventas/api/notas-credito/${id}/permanente`, { method: 'DELETE' });

                if (response.success) {
                    showToast('✅ Nota de crédito eliminada permanentemente', 'success');
                    await loadNotas();
                } else {
                    showToast('❌ Error: ' + (response.error || 'No se pudo eliminar'), 'error');
                }
            } catch (error) {
                console.error('❌ Error eliminando nota de crédito:', error);
                showToast('❌ Error al eliminar la nota de crédito: ' + error.message, 'error');
            }
        },
        '🗑️ Sí, eliminar permanentemente'
    );
}

function approveDevolucion(id) {
    showToast('Devolución aprobada', 'success');
}

function rejectDevolucion(id) {
    showToast('Devolución rechazada', 'success');
}

function deleteDevolucion(id) {
    if (confirm('¿Estás seguro de eliminar esta devolución?')) {
        showToast('Devolución eliminada', 'success');
    }
}

// Exportar: lo hace static/js/exportar_tabla.js (Excel de la tabla que se ve, con los filtros puestos)
function exportData(module) {
    if (typeof window.exportarModulo === 'function') return window.exportarModulo(module);
    showToast('⚠️ No se pudo cargar el exportador. Recarga la página (Ctrl+F5).', 'warning');
}

// ============================================================
// FUNCIONES PARA MODALES DE COTIZACIÓN
// ============================================================


// ============================================================
// OBTENER ROL DEL USUARIO
// ============================================================
function getUsuarioRol() {
    // Opción 1: Desde el elemento hidden en el HTML
    const rolElement = document.getElementById('usuarioRol');
    if (rolElement) {
        return rolElement.value || 'vendedor';
    }
    
    // Opción 2: Desde FLASK_SESSION (definido en base.html)
    if (typeof FLASK_SESSION !== 'undefined' && FLASK_SESSION.rol) {
        return FLASK_SESSION.rol;
    }
    
    // Opción 3: Desde sessionStorage (fallback)
    try {
        const sessionData = sessionStorage.getItem('erp_session');
        if (sessionData) {
            const parsed = JSON.parse(sessionData);
            return parsed.rol || 'vendedor';
        }
    } catch (e) {
        console.warn('Error obteniendo rol de sessionStorage:', e);
    }
    
    // Opción 4: Desde localStorage (fallback)
    try {
        const sessionData = localStorage.getItem('erp_session');
        if (sessionData) {
            const parsed = JSON.parse(sessionData);
            return parsed.rol || 'vendedor';
        }
    } catch (e) {
        console.warn('Error obteniendo rol de localStorage:', e);
    }
    
    // Default: vendedor
    return 'vendedor';
}

function renderCotizacionFooter(esEdicion = false) {
    const footer = document.getElementById('cotizacionModalFooter');
    if (!footer) return;
    
    const rol = getUsuarioRol();
    const isAdminOrHellen = rol === 'admin' || rol === 'hellen' || rol === 'administrador' || rol === 'superadmin';
    
    console.log('👤 Rol del usuario:', rol, '| Es Admin/Hellen:', isAdminOrHellen);
    
    let botonesHtml = '';
    
    if (isAdminOrHellen) {
        // ============================================================
        // MODO ADMIN / HELLEN
        // ============================================================
        botonesHtml = `
            <!-- Cancelar -->
            <button class="btn btn-secondary" style="padding:4px 14px;font-size:0.8rem;line-height:1.2;min-height:30px;border-radius:8px;border:1px solid #9CA3AF;background:#6B7280;color:#fff;font-weight:800;cursor:pointer;" onclick="closeModal('cotizacionModal')">Cancelar</button>
            
            <!-- 💾 Guardar Borrador - ROJO -->
            <button class="btn btn-danger" style="padding:4px 14px;font-size:0.8rem;line-height:1.2;min-height:30px;border-radius:8px;border:1px solid #DC2626;background:#DC2626;color:#fff;font-weight:900;cursor:pointer;box-shadow:0 0 15px rgba(220,38,38,0.3);" onclick="saveCotizacionDraft()">💾 Guardar Borrador</button>
            
            <!-- 🔽 NUEVO: Solicitar Validación - Amarillo -->
            <button class="btn btn-warning" style="padding:4px 14px;font-size:0.8rem;line-height:1.2;min-height:30px;border-radius:8px;border:1px solid #F59E0B;background:#F59E0B;color:#fff;font-weight:900;cursor:pointer;box-shadow:0 0 15px rgba(245,158,11,0.3);" onclick="solicitarValidacion()">⭐ Solicitar Validación</button>
            
            <!-- Generar - Verde Fluorescente NEON -->
            <button class="btn btn-green" style="padding:4px 14px;font-size:0.8rem;line-height:1.2;min-height:30px;border-radius:8px;border:1px solid #00FF41;background:#00FF41;color:#000;font-weight:900;cursor:pointer;box-shadow:0 0 25px rgba(0,255,65,0.5);" onclick="generateCotizacionPdfAndSend()">📄 Generar</button>
        `;
    } else {
        // ============================================================
        // MODO VENDEDOR
        // ============================================================
        botonesHtml = `
            <!-- Cancelar -->
            <button class="btn btn-secondary" style="padding:4px 14px;font-size:0.8rem;line-height:1.2;min-height:30px;border-radius:8px;border:1px solid #9CA3AF;background:#6B7280;color:#fff;font-weight:800;cursor:pointer;" onclick="closeModal('cotizacionModal')">Cancelar</button>
            
            <!-- 💾 Guardar Borrador - ROJO -->
            <button class="btn btn-danger" style="padding:4px 14px;font-size:0.8rem;line-height:1.2;min-height:30px;border-radius:8px;border:1px solid #DC2626;background:#DC2626;color:#fff;font-weight:900;cursor:pointer;box-shadow:0 0 15px rgba(220,38,38,0.3);" onclick="saveCotizacionDraft()">💾 Guardar Borrador</button>
            
            <!-- 🔽 NUEVO: Solicitar Validación - Amarillo -->
            <button class="btn btn-warning" style="padding:4px 14px;font-size:0.8rem;line-height:1.2;min-height:30px;border-radius:8px;border:1px solid #F59E0B;background:#F59E0B;color:#fff;font-weight:900;cursor:pointer;box-shadow:0 0 15px rgba(245,158,11,0.3);" onclick="solicitarValidacion()">⭐ Solicitar Validación</button>
            
            <!-- Generar - Verde Fluorescente NEON -->
            <button class="btn btn-green" style="padding:4px 14px;font-size:0.8rem;line-height:1.2;min-height:30px;border-radius:8px;border:1px solid #00FF41;background:#00FF41;color:#000;font-weight:900;cursor:pointer;box-shadow:0 0 25px rgba(0,255,65,0.5);" onclick="generateCotizacionPdfAndSend()">📄 Generar</button>
        `;
    }
    
    const flujoHtml = `
        <div class="cotizacion-footer-flow">
            <span class="flow-title">Flujo:</span>

            <div class="flow-step flow-active">
                <span class="flow-number">1</span>
                <span>Borrador</span>
            </div>

            <span class="flow-line"></span>

            <div class="flow-step">
                <span class="flow-number">2</span>
                <span>Por validar</span>
            </div>

            <span class="flow-line"></span>

            <div class="flow-step">
                <span class="flow-number">3</span>
                <span>Aceptada</span>
            </div>

            <span class="flow-line"></span>

            <div class="flow-step">
                <span class="flow-number">4</span>
                <span>Generada</span>
            </div>
        </div>
    `;

    footer.innerHTML = `
        ${flujoHtml}

        <div class="cotizacion-footer-buttons">
            ${botonesHtml}
        </div>
    `;
}


// ============================================================
// SOLICITAR VALIDACIÓN - NUEVA FUNCIÓN
// ============================================================

function solicitarValidacion() {
    // Verificar que hay productos en la cotización
    if (quoteProducts.length === 0) {
        showToast('⚠️ Agrega al menos un producto a la cotización', 'warning');
        return;
    }
    
    // Verificar que hay un cliente seleccionado
    const ruc = document.getElementById('fRuc')?.value?.trim() || '';
    if (!ruc) {
        showToast('⚠️ Primero busca un cliente por RUC', 'warning');
        return;
    }
    const faltanVal = validarCamposObligatoriosCotizacion();
    faltanDatosParihuela().forEach(c => { if (!faltanVal.some(x => x.toLowerCase().startsWith(c.toLowerCase().slice(0, 10)))) faltanVal.push(c); });
    if (faltanVal.length > 0) {
        showToast('⛔ Faltan campos obligatorios para enviar a validación: ' + faltanVal.join(', '), 'error');
        showValidationWarningModal(faltanVal);
        return;
    }
    
    showConfirmModal(
        '⭐ ¿Solicitar validación?',
        'Estás a punto de enviar esta cotización a <b>"Por validar"</b>.',
        '⚠️ Hellen o Erika revisarán la cotización y la aceptarán o rechazarán.',
        async function() {
            const btn = document.querySelector('#cotizacionModal .btn-warning');
            const originalText = btn?.textContent || '⭐ Solicitar Validación';
            if (btn) {
                btn.textContent = '⏳ Enviando...';
                btn.disabled = true;
            }
            
            try {
                // Guardar con estado "Por validar"
                const guardada = await guardarCotizacion('Por validar');
                if (!guardada) return; // no se envió: el motivo ya se mostró
                showToast('⭐ Cotización enviada a validación', 'success');
                closeModal('cotizacionModal');
                await loadCotizaciones();
            } catch (error) {
                console.error('Error enviando a validación:', error);
                showToast('❌ Error al enviar: ' + error.message, 'error');
            } finally {
                if (btn) {
                    btn.textContent = originalText;
                    btn.disabled = false;
                }
            }
        },
        '⭐ Sí, solicitar validación'
    );
}
// ============================================================
// OBTENER ROL DEL USUARIO
// ============================================================
function getUsuarioRol() {
    // Opción 1: Desde un elemento hidden en el HTML
    const rolElement = document.getElementById('usuarioRol');
    if (rolElement) {
        return rolElement.value || 'vendedor';
    }
    
    // Opción 2: Desde un script con data-user
    const userData = document.querySelector('script[data-user]');
    if (userData) {
        try {
            const data = JSON.parse(userData.dataset.user);
            return data.rol || 'vendedor';
        } catch (e) {
            return 'vendedor';
        }
    }
    
    // Opción 3: Fallback - intentar obtener de la sesión desde el HTML
    const sessionScript = document.querySelector('script#sessionData');
    if (sessionScript) {
        try {
            const data = JSON.parse(sessionScript.textContent);
            return data.rol || 'vendedor';
        } catch (e) {
            return 'vendedor';
        }
    }
    
    return 'vendedor';
}




async function cargarCotizacionParaEditar(id) {
    try {
        console.log('📥 Cargando cotización para editar ID:', id);
        
        // Usar la ruta completa que devuelve todos los datos
        const response = await apiFetch(`/ventas/api/cotizaciones/${id}/completa`);
        
        if (!response.success) {
            showToast('Error al cargar cotización: ' + (response.error || 'Desconocido'), 'error');
            return;
        }
        
        const c = response.data;
        console.log('📦 Datos cargados:', c);
        
        // ============================================================
        // LLENAR DATOS DEL CLIENTE
        // ============================================================
        if (document.getElementById('fRuc')) document.getElementById('fRuc').value = c.cliente_ruc || '';
        if (document.getElementById('fRazon')) document.getElementById('fRazon').value = c.cliente_razon_social || '';
        if (document.getElementById('fCodCliente')) document.getElementById('fCodCliente').value = c.cod_cliente || 'PENDIENTE';
        if (document.getElementById('fComercial')) document.getElementById('fComercial').value = c.cliente_nombre_comercial || '';
        if (document.getElementById('fDireccion')) document.getElementById('fDireccion').value = c.cliente_direccion || c.direccion_entrega || '';
        
const contactoGuardado = c.cliente_contacto || c.contacto_cliente || c.contacto || '';
if (contactoGuardado) {
    cargarContactoGuardadoEnSelect(contactoGuardado, c.cliente_telefono || c.telefono_cliente || '', c.cliente_email || c.email_cliente || '');
}
        if (document.getElementById('fTelefono')) document.getElementById('fTelefono').value = c.cliente_telefono || c.telefono_cliente || '';
        if (document.getElementById('fCorreo')) document.getElementById('fCorreo').value = c.cliente_email || c.email_cliente || '';
                
        // ============================================================
// LLENAR CONDICIONES COMERCIALES - con soporte para personalizado
// ============================================================
if (c.condicion_pago) {
    const condN = window.normalizarCondicion ? window.normalizarCondicion(c.condicion_pago) : c.condicion_pago;
    if (condN && window.ponerCondicion) {
        window.ponerCondicion('fCondicion', condN);
        const cc = document.getElementById('fCondicionCustom');
        if (cc) { cc.value = ''; cc.style.display = 'none'; }
    } else {
        setFieldValue('fCondicion', 'fCondicionCustom', c.condicion_pago);
    }
}

if (c.tiempo_entrega) {
    setFieldValue('fTiempo', 'fTiempoCustom', c.tiempo_entrega);
}

if (c.validez_oferta) {
    setFieldValue('fValidez', 'fValidezCustom', c.validez_oferta);
}

// ============================================================
// CARGAR DIRECCIÓN DE ENTREGA CON SOPORTE PARA RECOGO
// ============================================================
if (c.direccion_entrega) {
    cargarDireccionEntregaExistente(c.direccion_entrega);
}
        
        // Punto 4: seguimiento, motivo, transporte, parihuela y nota interna (antes no se cargaban al reabrir)
        const ponerValor = (idCampo, valor) => {
            const el = document.getElementById(idCampo);
            if (!el || valor === undefined || valor === null || valor === '') return;
            if (el.tagName === 'SELECT' && ![...el.options].some(o => o.value === valor)) {
                el.add(new Option(valor, valor));   // valor guardado que ya no está en la lista: se respeta
            }
            el.value = valor;
        };
        ponerValor('fSeguimiento', c.seguimiento);
        ponerValor('fMotivo', c.motivo);
        ponerValor('fTransporte', c.transporte);
        ponerValor('fParihuela', c.parihuela);
        ponerValor('fNotaInterna', c.nota_interna);

        // Punto 3 del resumen: descuento en % o en S/ (antes se perdía al reabrir)
        const tipoDesc = (c.descuento_tipo === 'S/' || c.descuento_tipo === 'monto') ? 'S/' : '%';
        const valorDesc = tipoDesc === '%' ? Number(c.descuento_porcentaje || 0) : Number(c.descuento_monto || 0);
        if (document.getElementById('fDiscountType')) document.getElementById('fDiscountType').value = tipoDesc;
        if (document.getElementById('fDiscountValue')) document.getElementById('fDiscountValue').value = valorDesc;
        
        // Requerimiento
        if (c.requerimiento && document.getElementById('fReq')) {
            document.getElementById('fReq').value = c.requerimiento;
        }
        
        // ============================================================
        // CARGAR PRODUCTOS
        // ============================================================
        if (c.productos && c.productos.length > 0) {
            quoteProducts = c.productos.map(p => ({
                ...p,
                cantidad: p.cantidad || 1,
                valorVenta: p.valorVenta || 0
            }));
            renderQuoteProducts();
            
            // Actualizar la barra de pasos según el estado
            updateQuoteStatusBar(c.estado);
            
            // Calcular totales
            setTimeout(() => { calcQuote(); }, 100);
            
            console.log(`✅ ${quoteProducts.length} productos cargados`);
        } else {
            console.log('📭 No hay productos en esta cotización');
        }
        
        // Mostrar el estado en el título
        const title = document.getElementById('cotizacionModalTitle');
        if (title && c.estado) {
            const estadoEmoji = {
                'Borrador': '📝',
                'En revisión': '🔍',
                'Validada': '✅',
                'Generada': '📄',
                'Aceptada': '🎯',
                
            };
            title.textContent = `Editar cotización ${c.numero_cotizacion || ''} ${estadoEmoji[c.estado] || ''} (${c.estado})`;
        }
        
        showToast('✅ Cotización cargada correctamente', 'success');
        
    } catch (error) {
        console.error('❌ Error cargando cotización para editar:', error);
        showToast('Error al cargar la cotización: ' + error.message, 'error');
    }
}
function updateQuoteStatusBar(estado) {
    const steps = document.querySelectorAll('#quoteStatusBar .step');
    // Mapeo de estados con sus índices
    const estadosMap = {
        'Borrador': 0,
        'En revisión': 1,
        'Validado por Hellen': 2,
        'Validada': 2,
        'Generada': 3,
        'Aceptada por Cliente': 4,
        'Aceptada': 4
    };
    
    const index = estadosMap[estado] !== undefined ? estadosMap[estado] : -1;
    const stepLabels = ['Borrador', 'En revisión', 'Validada ', 'Generada', 'Aceptada'];
    
    steps.forEach((step, i) => {
        // Remover todas las clases de estado
        step.classList.remove('status-draft', 'status-review', 'status-validated', 'status-generated', 'status-accepted', 'inactive');
        
        if (i <= index && index >= 0) {
            // Activo según el estado actual
            if (i === 0) step.classList.add('status-draft');
            else if (i === 1) step.classList.add('status-review');
            else if (i === 2) step.classList.add('status-validated');
            else if (i === 3) step.classList.add('status-generated');
            else if (i === 4) step.classList.add('status-accepted');
        } else {
            // Inactivo
            step.classList.add('inactive');
        }
    });
}

// ============================================================
// INICIALIZACIÓN DE SWITCHES TOGGLE PARA VALIDACIÓN PC
// ============================================================


function updateValidationStatus() {
    console.log('🔄 Actualizando estado de validación...');
    
    const validations = [
        'vPrecio', 'vProducto', 'vEntrega', 
        'vTransporte', 'vCantidad', 'vMoneda', 'vVigencia'
    ];
    
    validations.forEach(id => {
        const checkbox = document.getElementById(id);
        const label = document.getElementById(id + 'Label');
        
        if (checkbox && label) {
            if (checkbox.checked) {
                label.textContent = '✅ Válido';
                label.style.color = '#16A34A';
                // Actualizar el span del switch (si existe)
                const slider = checkbox.closest('.switch')?.querySelector('.slider');
                if (slider) {
                    slider.style.background = '#22C55E';
                }
            } else {
                label.textContent = '❌ No válido';
                label.style.color = '#DC2626';
                const slider = checkbox.closest('.switch')?.querySelector('.slider');
                if (slider) {
                    slider.style.background = '#EF4444';
                }
            }
        }
    });
    
    if (typeof updateValidationSemaphore === 'function') {
        updateValidationSemaphore();
    }
}



function updateValidationSemaphore() {
    console.log('🔄 Actualizando semáforo de validación...');
    
    const semaphore = document.getElementById('validationSemaphore');
    if (!semaphore) return;
    
    const icon = document.getElementById('validationIcon');
    const title = document.getElementById('validationTitle');
    const subtitle = document.getElementById('validationSubtitle');
    const chips = document.getElementById('validationChips');
    
    // ⚠️ VALIDACIONES QUE BLOQUEAN (STOCK NO INCLUIDO)
    const validations = ['vPrecio', 'vProducto', 'vEntrega', 'vTransporte', 'vCantidad', 'vMoneda', 'vVigencia'];
    let allValid = true;
    let invalidCount = 0;
    const invalidItems = [];
    
    validations.forEach(id => {
        const checkbox = document.getElementById(id);
        if (checkbox) {
            if (!checkbox.checked) {
                allValid = false;
                invalidCount++;
                const label = document.getElementById(id + 'Label');
                const text = label ? label.textContent.replace('❌ ', '') : id;
                invalidItems.push(text);
            }
        }
    });
    
    // ⚠️ STOCK SOLO INFORMATIVO
    let stockWarning = false;
    let stockFaltante = 0;
    document.querySelectorAll('#pcItemsBody tr').forEach(row => {
        const inputs = row.querySelectorAll('input');
        if (inputs.length >= 9) {
            const cantidadPC = Number(inputs[5]?.value || 0);
            const stock = Number(inputs[8]?.value || 0);
            if (cantidadPC > stock) {
                stockWarning = true;
                stockFaltante += (cantidadPC - stock);
            }
        }
    });
    
    // Actualizar semáforo
    if (allValid) {
        if (stockWarning) {
            // ⚠️ Validaciones OK, pero stock insuficiente - ADVERTENCIA
            semaphore.style.borderColor = '#F59E0B';
            semaphore.style.background = '#FFFBEB';
            if (icon) icon.textContent = '⚠️';
            if (title) {
                title.textContent = `⚠️ Validaciones OK - Stock insuficiente (faltan ${stockFaltante} unidades)`;
                title.style.color = '#92400E';
            }
            if (subtitle) {
                subtitle.textContent = 'Puedes continuar con el proceso, pero revisa el stock';
                subtitle.style.color = '#92400E';
            }
            if (chips) {
                chips.innerHTML = `<span style="background:#FEF3C7;color:#92400E;padding:2px 10px;border-radius:12px;font-size:9px;font-weight:800;">⚠️ Stock insuficiente</span>`;
            }
        } else {
            // ✅ Todo OK
            semaphore.style.borderColor = '#16A34A';
            semaphore.style.background = '#DCFCE7';
            if (icon) icon.textContent = '✅';
            if (title) {
                title.textContent = '✅ Todas las validaciones OK - Stock suficiente';
                title.style.color = '#065F46';
            }
            if (subtitle) {
                subtitle.textContent = 'El PC está conforme y listo para proceder';
                subtitle.style.color = '#065F46';
            }
            if (chips) {
                chips.innerHTML = `<span style="background:#D1FAE5;color:#065F46;padding:2px 10px;border-radius:12px;font-size:9px;font-weight:800;">✅ Todo OK</span>`;
            }
        }
    } else {
        // ❌ Hay validaciones fallidas - BLOQUEA
        semaphore.style.borderColor = '#DC2626';
        semaphore.style.background = '#FEE2E2';
        if (icon) icon.textContent = '❌';
        if (title) {
            title.textContent = `⚠️ ${invalidCount} validación(es) pendiente(s)`;
            title.style.color = '#991B1B';
        }
        if (subtitle) {
            subtitle.textContent = `Faltan: ${invalidItems.join(', ')}`;
            subtitle.style.color = '#991B1B';
        }
        if (chips) {
            chips.innerHTML = `<span style="background:#FEE2E2;color:#991B1B;padding:2px 10px;border-radius:12px;font-size:9px;font-weight:800;">❌ ${invalidItems.join(', ')}</span>`;
        }
    }
}

// Función para obtener valores de validación (para usar al guardar)
function getValidationValues() {
    const validations = [
        'vPrecio', 'vProducto', 'vEntrega', 
        'vTransporte', 'vCantidad', 'vMoneda', 'vVigencia'
    ];
    
    const result = {};
    validations.forEach(id => {
        const checkbox = document.getElementById(id);
        result[id] = checkbox ? (checkbox.checked ? 'Sí' : 'No') : 'Sí';
    });
    return result;
}

// Inicializar al cargar la página (se ejecuta después de que el DOM esté listo)
document.addEventListener('DOMContentLoaded', function() {
    // Esperar un poco para que el modal se haya renderizado
    setTimeout(function() {
        // Buscar si existe el modal de PC
        const modal = document.getElementById('pedidoCompraModal');
        if (modal) {
            // Inicializar los switches que estén dentro del modal
            const switches = modal.querySelectorAll('.switch input[type="checkbox"]');
            switches.forEach(function(sw) {
                // Asegurar que los switches tengan el estado inicial correcto
                if (sw.checked) {
                    const label = document.getElementById(sw.id + 'Label');
                    if (label) {
                        label.textContent = '✅ Válido';
                        label.style.color = '#16A34A';
                    }
                }
            });
        }
        updateValidationStatus();
    }, 500);
});




// ============================================================
// FUNCIONES PARA GUÍA DE REMISIÓN COMPLETA
// ============================================================

// Variable para almacenar productos de la guía
let guiaProductos = [];

// ============================================================
// UBIGEOS PARA GUÍA
// ============================================================

// Datos de ubigeos completos (solo algunos para ejemplo, usa los que ya tienes)
const UBIGEO_DATA = {
    "LIMA": {"LIMA": ["LIMA", "ANCON", "ATE", "BARRANCO", "BREÑA", "CARABAYLLO", "CHACLACAYO", "CHORRILLOS", "COMAS", "EL AGUSTINO", "INDEPENDENCIA", "JESUS MARIA", "LA MOLINA", "LA VICTORIA", "LINCE", "LOS OLIVOS", "LURIGANCHO", "MAGDALENA DEL MAR", "MIRAFLORES", "PACHACAMAC", "PUEBLO LIBRE", "PUENTE PIEDRA", "RIMAC", "SAN BARTOLO", "SAN BORJA", "SAN ISIDRO", "SAN JUAN DE LURIGANCHO", "SAN JUAN DE MIRAFLORES", "SAN LUIS", "SAN MARTIN DE PORRES", "SAN MIGUEL", "SANTA ANITA", "SANTIAGO DE SURCO", "SURCO", "SURQUILLO", "VILLA EL SALVADOR", "VILLA MARIA DEL TRIUNFO"]},
    "CALLAO": {"CALLAO": ["CALLAO", "BELLAVISTA", "CARMEN DE LA LEGUA REYNOSO", "LA PERLA", "LA PUNTA", "VENTANILLA"]},
    "AREQUIPA": {"AREQUIPA": ["AREQUIPA", "ALTO SELVA ALEGRE", "CAYMA", "CERRO COLORADO", "JACOBO HUNTER", "JOSE LUIS BUSTAMANTE Y RIVERO", "MARIANO MELGAR", "MIRAFLORES", "PAUCARPATA", "SABANDIA", "SACHACA", "SOCABAYA", "TIABAYA", "YANAHUARA", "YURA"]},
    "CUSCO": {"CUSCO": ["CUSCO", "CCORCA", "POROY", "SAN JERONIMO", "SAN SEBASTIAN", "SANTIAGO", "WANCHAQ"]},
    "PIURA": {"PIURA": ["PIURA", "CASTILLA", "CATACAOS", "LA ARENA", "LA UNION", "TAMBO GRANDE"]},
    "TUMBES": {"TUMBES": ["TUMBES", "CORRALES", "LA CRUZ", "SAN JACINTO"]},
    "LA LIBERTAD": {"TRUJILLO": ["TRUJILLO", "EL PORVENIR", "HUANCHACO", "LA ESPERANZA", "LAREDO", "MOCHE", "SALAVERRY", "VICTOR LARCO HERRERA"]},
    "JUNIN": {"HUANCAYO": ["HUANCAYO", "CHILCA", "EL TAMBO", "SAN AGUSTIN", "SAN JERONIMO DE TUNAN"]},
    "SAN MARTIN": {"TARAPOTO": ["TARAPOTO", "LA BANDA DE SHILCAYO", "MORALES"]}
};

function llenarDepartamentosGuia(selectId) {
    const select = document.getElementById(selectId);
    if (!select) return;
    select.innerHTML = '<option value="">Seleccione</option>';
    Object.keys(UBIGEO_DATA).sort().forEach(d => {
        const opt = document.createElement('option');
        opt.value = d;
        opt.textContent = d;
        select.appendChild(opt);
    });
}



// ============================================================
// CARGAR CONTACTO GUARDADO EN EL SELECT (para edición)
// ============================================================
function cargarContactoGuardadoEnSelect(nombreContacto, telefono, email) {
    const select = document.getElementById('fContacto');
    const customInput = document.getElementById('fContactoCustom');
    const fTelefono = document.getElementById('fTelefono');
    const fCorreo = document.getElementById('fCorreo');
    
    if (!select) return;
    
    // Autocompletar teléfono/email
    if (fTelefono) fTelefono.value = telefono || '';
    if (fCorreo) fCorreo.value = email || '';
    
    // Si el contacto guardado está en las opciones, seleccionarlo
    let encontrado = false;
    for (let i = 0; i < select.options.length; i++) {
        const opt = select.options[i];
        const nombreOpt = opt.dataset?.nombre || '';
        if (nombreOpt && nombreOpt.toLowerCase() === nombreContacto.toLowerCase()) {
            select.value = opt.value;
            encontrado = true;
            break;
        }
    }
    
    // Si no está en las opciones, mostrar como personalizado
    if (!encontrado && nombreContacto) {
        // Agregar opción personalizada con este nombre
        const optNew = document.createElement('option');
        optNew.value = '__custom__';
        optNew.textContent = `✏️ ${nombreContacto}`;
        select.appendChild(optNew);
        select.value = '__custom__';
        
        if (customInput) {
            customInput.style.display = 'block';
            customInput.value = nombreContacto;
        }
    }
}

function llenarProvinciasGuia(depto, provSelectId, distSelectId) {
    const provSelect = document.getElementById(provSelectId);
    const distSelect = document.getElementById(distSelectId);
    if (!provSelect || !distSelect) return;
    if (!depto || !UBIGEO_DATA[depto]) {
        provSelect.innerHTML = '<option value="">Primero Departamento</option>';
        provSelect.disabled = true;
        distSelect.innerHTML = '<option value="">Primero Provincia</option>';
        distSelect.disabled = true;
        return;
    }
    provSelect.innerHTML = '<option value="">Seleccione</option>';
    Object.keys(UBIGEO_DATA[depto]).forEach(p => {
        const opt = document.createElement('option');
        opt.value = p;
        opt.textContent = p;
        provSelect.appendChild(opt);
    });
    provSelect.disabled = false;
    distSelect.innerHTML = '<option value="">Primero Provincia</option>';
    distSelect.disabled = true;
}

function llenarDistritosGuia(depto, prov, distSelectId, hiddenId, textSpanId) {
    const distSelect = document.getElementById(distSelectId);
    if (!distSelect) return;
    if (!depto || !prov || !UBIGEO_DATA[depto] || !UBIGEO_DATA[depto][prov]) {
        distSelect.innerHTML = '<option value="">Primero Provincia</option>';
        distSelect.disabled = true;
        document.getElementById(hiddenId).value = '';
        document.getElementById(textSpanId).textContent = 'Ninguno';
        return;
    }
    distSelect.innerHTML = '<option value="">Seleccione</option>';
    UBIGEO_DATA[depto][prov].forEach(d => {
        const opt = document.createElement('option');
        opt.value = d;
        opt.textContent = d;
        distSelect.appendChild(opt);
    });
    distSelect.disabled = false;
}

function configurarUbigeoGuia(baseId) {
    const depto = document.getElementById(`guiaDepto${baseId}`);
    const prov = document.getElementById(`guiaProv${baseId}`);
    const dist = document.getElementById(`guiaDist${baseId}`);
    const hidden = document.getElementById(`guiaUbigeo${baseId}`);
    const textSpan = document.getElementById(`guiaUbigeo${baseId}Texto`);
    
    if (!depto || !prov || !dist || !hidden || !textSpan) return;
    
    depto.addEventListener('change', function() {
        llenarProvinciasGuia(this.value, `guiaProv${baseId}`, `guiaDist${baseId}`);
        hidden.value = '';
        textSpan.textContent = 'Ninguno';
    });
    
    prov.addEventListener('change', function() {
        llenarDistritosGuia(depto.value, this.value, `guiaDist${baseId}`, hidden.id, textSpan.id);
        if (this.value && dist.value) {
            const cod = `${depto.value.substring(0,2)}${this.value.substring(0,2)}${dist.value.substring(0,2)}`.toUpperCase();
            hidden.value = cod;
            textSpan.textContent = `${depto.value} - ${this.value} - ${dist.value}`;
        }
    });
    
    dist.addEventListener('change', function() {
        if (depto.value && prov.value && this.value) {
            const cod = `${depto.value.substring(0,2)}${prov.value.substring(0,2)}${this.value.substring(0,2)}`.toUpperCase();
            hidden.value = cod;
            textSpan.textContent = `${depto.value} - ${prov.value} - ${this.value}`;
        } else {
            hidden.value = '';
            textSpan.textContent = 'Ninguno';
        }
    });
}

// ============================================================
// CARGAR CONDUCTORES PARA GUÍA
// ============================================================

async function cargarConductoresGuia() {
    try {
        const response = await fetch('/ventas/api/transportistas/listar');
        const result = await response.json();
        if (result.success && result.data) {
            const select = document.getElementById('guiaSelectConductor');
            if (select) {
                select.innerHTML = '<option value="">-- Seleccione --</option>';
                result.data.forEach(t => {
                    const option = document.createElement('option');
                    option.value = t.id;
                    let texto = t.nombre_completo || '';
                    if (t.placa) texto += ` - ${t.placa}`;
                    option.textContent = texto;
                    select.appendChild(option);
                });
                // Agregar opción personalizar
                const opt = document.createElement('option');
                opt.value = 'personalizar';
                opt.textContent = '✏️ Personalizar';
                opt.style.fontWeight = '600';
                opt.style.color = '#2563EB';
                select.appendChild(opt);
            }
        }
    } catch (error) {
        console.error('Error cargando conductores:', error);
    }
}

function cargarConductorGuia(id) {
    if (!id) return;
    if (id === 'personalizar') {
        document.getElementById('guiaPlaca').value = '';
        document.getElementById('guiaConductorDNI').value = '';
        document.getElementById('guiaConductorNombre').value = '';
        document.getElementById('guiaLicencia').value = '';
        showToast('✏️ Modo Personalizar: complete los campos manualmente', 'info');
        return;
    }
    fetch(`/ventas/api/transportistas/${id}`)
        .then(r => r.json())
        .then(result => {
            if (result.success && result.data) {
                const t = result.data;
                if (t.placa) document.getElementById('guiaPlaca').value = t.placa;
                if (t.dni) document.getElementById('guiaConductorDNI').value = t.dni;
                if (t.nombre_completo) document.getElementById('guiaConductorNombre').value = t.nombre_completo;
                if (t.licencia) document.getElementById('guiaLicencia').value = t.licencia;
                if (t.telefono) document.getElementById('nuevoConductorGuiaTelefono').value = t.telefono;
                showToast(`✅ Datos de ${t.nombre_completo} cargados`, 'success');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showToast('❌ Error al cargar conductor', 'error');
        });
}

function actualizarResumenDesdeMontoPC(input) {
    if (_timeoutResumen) clearTimeout(_timeoutResumen);
    _timeoutResumen = setTimeout(() => {
        const valor = parseFloat(input.value) || 0;
        const monedaSelect = document.getElementById('pcMoneda');
        const simbolo = (monedaSelect && (monedaSelect.value === '$' || monedaSelect.value === '$/' || monedaSelect.value.includes('$'))) ? '$' : 'S/';
        const formatNum = (num) => `${simbolo} ${num.toFixed(2)}`;
        
        // Calcular IGV y total
        const igv = valor * 0.18;
        const total = valor + igv;
        
        // Actualizar los campos del resumen
        const subtotalEl = document.getElementById('pcResumenSubtotal');
        const valorVentaEl = document.getElementById('pcResumenValorVenta');
        const igvEl = document.getElementById('pcResumenIgv');
        const totalEl = document.getElementById('pcResumenTotal');
        
        if (subtotalEl) subtotalEl.textContent = formatNum(valor);
        if (valorVentaEl) valorVentaEl.textContent = formatNum(valor);
        if (igvEl) igvEl.textContent = formatNum(igv);
        if (totalEl) totalEl.textContent = formatNum(total);
        
        // Actualizar el cuadro de diferencia
        const montoCotizacion = parseFloat(document.getElementById('pcMonto')?.value) || 0;
        const diferencia = valor - montoCotizacion;
        const diferenciaBox = document.getElementById('pcDiferenciaSinIgv');
        if (diferenciaBox) {
            diferenciaBox.textContent = `${simbolo} ${diferencia.toFixed(2)}`;
            if (diferencia > 0) diferenciaBox.style.color = '#DC2626';
            else if (diferencia < 0) diferenciaBox.style.color = '#2563EB';
            else diferenciaBox.style.color = '#6B7280';
        }
        
        console.log(`✅ Resumen actualizado desde Monto PC: ${simbolo} ${valor}`);
        _timeoutResumen = null;
    }, 100);
}

// ============================================================
// LIMPIAR CONDUCTOR EN GUÍA
// ============================================================

function limpiarConductorGuia() {
    // Limpiar el select
    const select = document.getElementById('guiaSelectConductor');
    if (select) select.value = '';
    
    // Limpiar todos los campos del conductor
    document.getElementById('guiaPlaca').value = '';
    document.getElementById('guiaConductorDNI').value = '';
    document.getElementById('guiaConductorNombre').value = '';
    document.getElementById('guiaLicencia').value = '';
    
    showToast('🧹 Campos del conductor limpiados', 'info');
}
// ============================================================
// NUEVO CONDUCTOR DESDE GUÍA
// ============================================================

function openNuevoConductorGuia() {
    document.getElementById('nuevoConductorGuiaModal').classList.add('show');
    // Limpiar campos
    ['nuevoConductorGuiaDNI','nuevoConductorGuiaNombre','nuevoConductorGuiaPlaca','nuevoConductorGuiaLicencia','nuevoConductorGuiaTelefono','nuevoConductorGuiaRUC'].forEach(id => {
        document.getElementById(id).value = '';
    });
}

async function guardarNuevoConductorGuia() {
    const dni = document.getElementById('nuevoConductorGuiaDNI').value.trim();
    const nombre = document.getElementById('nuevoConductorGuiaNombre').value.trim();
    const placa = document.getElementById('nuevoConductorGuiaPlaca').value.trim().toUpperCase();
    const licencia = document.getElementById('nuevoConductorGuiaLicencia').value.trim();
    const telefono = document.getElementById('nuevoConductorGuiaTelefono').value.trim();
    const ruc = document.getElementById('nuevoConductorGuiaRUC').value.trim();
    
    if (!dni || dni.length < 8) { showToast('⚠️ DNI válido (8 dígitos)', 'warning'); return; }
    if (!nombre) { showToast('⚠️ Nombre completo requerido', 'warning'); return; }
    if (!placa) { showToast('⚠️ Placa requerida', 'warning'); return; }
    
    try {
        const response = await fetch('/ventas/api/transportistas/guardar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                nombre_completo: nombre,
                dni: dni,
                placa: placa,
                licencia: licencia,
                telefono: telefono,
                ruc_empresa: ruc
            })
        });
        const result = await response.json();
        if (result.success) {
            showToast('✅ Conductor guardado correctamente', 'success');
            closeModal('nuevoConductorGuiaModal');
            await cargarConductoresGuia();
            const select = document.getElementById('guiaSelectConductor');
            select.value = result.data.id;
            select.dispatchEvent(new Event('change'));
        } else {
            showToast('❌ Error: ' + (result.error || 'No se pudo guardar'), 'error');
        }
    } catch (error) {
        showToast('❌ Error de conexión', 'error');
    }
}


// ============================================================
// SELECTOR DE PRODUCTOS PARA GUÍA
// ============================================================

let productSelectorGuiaData = [];
let selectedGuiaProductIds = new Set();

function openProductSelectorGuia() {
    // Si no hay productos maestros, cargarlos primero
    if (PRODUCTOS_MAESTROS.length === 0) {
        showToast('⏳ Cargando productos...', 'info');
        cargarProductosMaestros().then(() => {
            setTimeout(() => openProductSelectorGuia(), 300);
        });
        return;
    }
    
    // Resetear selecciones
    selectedGuiaProductIds = new Set();
    productSelectorGuiaData = [...PRODUCTOS_MAESTROS];
    
    // Renderizar tabla
    renderProductSelectorGuia();
    
    // Mostrar modal
    document.getElementById('productSelectorGuiaModal').classList.add('show');
    
    // Enfocar buscador
    setTimeout(() => {
        document.getElementById('productSelectorGuiaSearch')?.focus();
    }, 300);
}

function renderProductSelectorGuia() {
    const tbody = document.getElementById('productSelectorGuiaRows');
    const search = document.getElementById('productSelectorGuiaSearch')?.value?.toLowerCase() || '';
    
    // Filtrar productos
    let filtered = productSelectorGuiaData;
    if (search) {
        filtered = productSelectorGuiaData.filter(p => 
            (p.codigo && p.codigo.toLowerCase().includes(search)) ||
            (p.producto && p.producto.toLowerCase().includes(search)) ||
            (p.descripcion && p.descripcion.toLowerCase().includes(search)) ||
            (p.marca && p.marca.toLowerCase().includes(search)) ||
            (p.modelo && p.modelo.toLowerCase().includes(search))
        );
    }
    
    if (!tbody) return;
    
    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:#94A3B8;padding:20px;font-size:11px;">📭 No se encontraron productos</td></tr>`;
        document.getElementById('selectedGuiaCount').textContent = selectedGuiaProductIds.size;
        return;
    }
    
    tbody.innerHTML = filtered.map((p, index) => {
        const idKey = p.id || p.codigo;
        const isChecked = selectedGuiaProductIds.has(idKey);
        const valorVenta = parseFloat(p.valorVenta) || 0;
        
        return `
        <tr>
            <td style="text-align:center; padding:4px 6px;">
                <input type="checkbox" class="product-select-guia-checkbox" 
                       data-id="${idKey}" 
                       ${isChecked ? 'checked' : ''}
                       onchange="toggleProductSelectionGuia('${idKey}', this.checked)"
                       style="width:14px; height:14px; accent-color:#2563EB; cursor:pointer;">
            </td>
            <td style="font-weight:900; color:#0F172A; padding:4px 6px; font-size:10px;">${p.codigo || '-'}</td>
            <td style="text-align:left; font-weight:800; padding:4px 6px; font-size:10px;">${p.producto || p.descripcion || 'Sin nombre'}</td>
            <td style="padding:4px 6px; font-size:10px;">${p.marca || '-'}</td>
            <td style="padding:4px 6px; font-size:10px;">${p.modelo || '-'}</td>
            <td style="text-align:center; padding:4px 6px; font-size:10px;">${p.um || 'NIU'}</td>
            <td style="text-align:center; padding:4px 6px; font-size:10px;">${p.stock || 0}</td>
            <td style="text-align:center; padding:4px 6px;">
                <input type="number" class="product-select-guia-qty" 
                       data-id="${idKey}"
                       value="1" 
                       min="1" 
                       style="width:55px; height:24px; border:1px solid #E5E7EB; border-radius:4px; text-align:center; font-size:10px; font-weight:700;">
            </td>
        </tr>
    `}).join('');
    
    document.getElementById('selectedGuiaCount').textContent = selectedGuiaProductIds.size;
    
    // Actualizar el checkbox "Seleccionar todos"
    const totalCheckboxes = document.querySelectorAll('.product-select-guia-checkbox').length;
    const checkedCheckboxes = document.querySelectorAll('.product-select-guia-checkbox:checked').length;
    const selectAllCheckbox = document.getElementById('selectAllGuiaCheckbox');
    if (selectAllCheckbox) {
        if (totalCheckboxes > 0 && checkedCheckboxes === totalCheckboxes) {
            selectAllCheckbox.checked = true;
            selectAllCheckbox.indeterminate = false;
        } else if (checkedCheckboxes > 0) {
            selectAllCheckbox.checked = false;
            selectAllCheckbox.indeterminate = true;
        } else {
            selectAllCheckbox.checked = false;
            selectAllCheckbox.indeterminate = false;
        }
    }
}

function toggleProductSelectionGuia(idKey, checked) {
    if (checked) {
        selectedGuiaProductIds.add(idKey);
    } else {
        selectedGuiaProductIds.delete(idKey);
    }
    document.getElementById('selectedGuiaCount').textContent = selectedGuiaProductIds.size;
    
    // Actualizar el checkbox "Seleccionar todos"
    const totalCheckboxes = document.querySelectorAll('.product-select-guia-checkbox').length;
    const checkedCheckboxes = document.querySelectorAll('.product-select-guia-checkbox:checked').length;
    const selectAllCheckbox = document.getElementById('selectAllGuiaCheckbox');
    if (selectAllCheckbox) {
        if (totalCheckboxes > 0 && checkedCheckboxes === totalCheckboxes) {
            selectAllCheckbox.checked = true;
            selectAllCheckbox.indeterminate = false;
        } else if (checkedCheckboxes > 0) {
            selectAllCheckbox.checked = false;
            selectAllCheckbox.indeterminate = true;
        } else {
            selectAllCheckbox.checked = false;
            selectAllCheckbox.indeterminate = false;
        }
    }
}

function selectAllProductsGuia() {
    document.querySelectorAll('.product-select-guia-checkbox').forEach(cb => {
        cb.checked = true;
        const idKey = cb.dataset.id;
        selectedGuiaProductIds.add(idKey);
    });
    document.getElementById('selectedGuiaCount').textContent = selectedGuiaProductIds.size;
    const selectAllCheckbox = document.getElementById('selectAllGuiaCheckbox');
    if (selectAllCheckbox) selectAllCheckbox.checked = true;
}

function deselectAllProductsGuia() {
    document.querySelectorAll('.product-select-guia-checkbox').forEach(cb => {
        cb.checked = false;
        const idKey = cb.dataset.id;
        selectedGuiaProductIds.delete(idKey);
    });
    document.getElementById('selectedGuiaCount').textContent = selectedGuiaProductIds.size;
    const selectAllCheckbox = document.getElementById('selectAllGuiaCheckbox');
    if (selectAllCheckbox) selectAllCheckbox.checked = false;
}

function toggleAllProductCheckboxesGuia(checked) {
    document.querySelectorAll('.product-select-guia-checkbox').forEach(cb => {
        cb.checked = checked;
        const idKey = cb.dataset.id;
        if (checked) {
            selectedGuiaProductIds.add(idKey);
        } else {
            selectedGuiaProductIds.delete(idKey);
        }
    });
    document.getElementById('selectedGuiaCount').textContent = selectedGuiaProductIds.size;
}

function addSelectedProductsGuia() {
    if (selectedGuiaProductIds.size === 0) {
        showToast('⚠️ Selecciona al menos un producto', 'warning');
        return;
    }
    
    let addedCount = 0;
    let notFoundCount = 0;
    
    selectedGuiaProductIds.forEach(idKey => {
        // Buscar el producto por id o codigo
        let product = PRODUCTOS_MAESTROS.find(p => p.id == idKey || p.codigo == idKey);
        
        if (!product) {
            notFoundCount++;
            return;
        }
        
        // Obtener la cantidad del input correspondiente
        const qtyInput = document.querySelector(`.product-select-guia-qty[data-id="${idKey}"]`);
        const cantidad = parseInt(qtyInput?.value || 1);
        
        // Obtener datos del producto
        const codigo = product.codigo || '';
        const descripcion = product.producto || product.descripcion || 'Sin descripción';
        const unidad = product.um || 'NIU';
        const peso_unitario = 0.50; // Peso estimado por defecto
        
        // Verificar si ya existe en la tabla (por código)
        let existe = false;
        document.querySelectorAll('#guiaProductosBody tr').forEach(row => {
            const codigoInput = row.querySelector('.guia-producto-codigo');
            if (codigoInput && codigoInput.value === codigo) {
                existe = true;
                // Sumar cantidad
                const cantInput = row.querySelector('.guia-producto-cant');
                if (cantInput) {
                    const current = parseFloat(cantInput.value) || 0;
                    cantInput.value = current + cantidad;
                    cantInput.dispatchEvent(new Event('change'));
                }
            }
        });
        
        if (!existe) {
            // Agregar nuevo producto a la tabla
            const tbody = document.getElementById('guiaProductosBody');
            if (!tbody) return;
            
            const count = tbody.children.length + 1;
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td style="padding:2px 4px; text-align:center; font-weight:800; background:#F8FAFC; font-size:9px;">${count}</td>
                <td style="padding:2px 4px;"><input class="guia-producto-codigo" value="${esc(codigo)}" style="width:100%; border:1px solid #E5E7EB; border-radius:3px; font-size:8px; padding:2px 4px; background:#F1F5F9;" readonly></td>
                <td style="padding:2px 4px;"><input class="guia-producto-desc" value="${esc(descripcion)}" style="width:100%; border:1px solid #E5E7EB; border-radius:3px; font-size:8px; padding:2px 4px; background:#F1F5F9;" readonly onchange="actualizarPesoTotalGuia()"></td>
                <td style="padding:2px 4px;">
                    <select class="guia-producto-unidad" style="width:100%; border:1px solid #E5E7EB; border-radius:3px; font-size:8px; padding:2px 4px; background:#F1F5F9;">
                        <option value="NIU" ${unidad === 'NIU' ? 'selected' : ''}>NIU</option>
                        <option value="KGM" ${unidad === 'KGM' ? 'selected' : ''}>KGM</option>
                        <option value="LTR" ${unidad === 'LTR' ? 'selected' : ''}>LTR</option>
                        <option value="MTR" ${unidad === 'MTR' ? 'selected' : ''}>MTR</option>
                        <option value="ZZ" ${unidad === 'ZZ' ? 'selected' : ''}>ZZ</option>
                    </select>
                </td>
                <td style="padding:2px 4px;"><input class="guia-producto-cant" type="number" value="${cantidad}" min="0.01" step="0.01" style="width:100%; border:1px solid #E5E7EB; border-radius:3px; font-size:8px; padding:2px 4px; text-align:center; font-weight:900;" onchange="actualizarPesoTotalGuia()"></td>
                <td style="padding:2px 4px;"><input class="guia-producto-peso" type="number" value="${peso_unitario}" step="0.01" style="width:100%; border:1px solid #E5E7EB; border-radius:3px; font-size:8px; padding:2px 4px; text-align:center;" onchange="actualizarPesoTotalGuia()"></td>
                <td style="padding:2px 4px; text-align:center;">
                    <button class="btn-tachito" title="Eliminar este producto" onclick="this.closest('tr').remove(); actualizarPesoTotalGuia(); actualizarContadorProductosGuia();">🗑️</button>
                </td>
            `;
            tbody.appendChild(tr);
        }
        
        addedCount++;
    });
    
    // Cerrar modal
    closeModal('productSelectorGuiaModal');
    
    // Actualizar contadores y peso
    actualizarPesoTotalGuia();
    actualizarContadorProductosGuia();
    reordenarItemsGuia();
    
    // Mostrar mensaje
    if (addedCount > 0) {
        showToast(`✅ ${addedCount} productos agregados correctamente`, 'success');
    }
    if (notFoundCount > 0) {
        showToast(`⚠️ ${notFoundCount} productos no encontrados`, 'warning');
    }
}

function reordenarItemsGuia() {
    const rows = document.querySelectorAll('#guiaProductosBody tr');
    rows.forEach((row, index) => {
        const numCell = row.querySelector('td:first-child');
        if (numCell) {
            numCell.textContent = index + 1;
        }
    });
}

// ============================================================
// BUSCAR CLIENTE PARA GUÍA
// ============================================================

async function buscarClienteParaGuia() {
    const input = document.getElementById('guiaBuscarCliente');
    const ruc = input.value.trim();
    if (!ruc || ruc.length !== 11) {
        showToast('⚠️ Ingrese RUC de 11 dígitos', 'warning');
        return;
    }
    showToast('🔍 Buscando cliente...', 'info');
    try {
        // Buscar en BD
        const response = await fetch(`/maestros/api/clientes/buscar?q=${ruc}`);
        const data = await response.json();
        if (data.success && data.data && data.data.length > 0) {
            const c = data.data[0];
            document.getElementById('guiaRuc').value = c.numero_documento || c.ruc || '';
            document.getElementById('guiaCliente').value = c.razon_social || '';
            document.getElementById('guiaDestino').value = c.direccion_fiscal || '';
            if (c.ubigeo) {
                // Intentar preseleccionar ubigeo
            }
            showToast('✅ Cliente encontrado en sistema', 'success');
            return;
        }
        // Si no, consultar SUNAT
        const sunatResponse = await fetch(`/api/sunat/consulta?ruc=${ruc}`);
        const sunatData = await sunatResponse.json();
        if (sunatData.success) {
            document.getElementById('guiaRuc').value = ruc;
            document.getElementById('guiaCliente').value = sunatData.razon_social || '';
            document.getElementById('guiaDestino').value = sunatData.direccion || '';
            showToast('🌞 Datos cargados desde SUNAT', 'info');
        } else {
            showToast('❌ No se encontró el RUC', 'error');
        }
    } catch (error) {
        showToast('❌ Error al consultar', 'error');
    }
}

// ============================================================
// BUSCAR TRANSPORTISTA PARA GUÍA
// ============================================================

async function buscarTransportistaGuia() {
    const ruc = document.getElementById('guiaTransportistaRUC').value.trim();
    if (!ruc || ruc.length !== 11) {
        showToast('⚠️ Ingrese RUC de 11 dígitos', 'warning');
        return;
    }
    try {
        const response = await fetch(`/api/sunat/consulta?ruc=${ruc}`);
        const data = await response.json();
        if (data.success) {
            document.getElementById('guiaTransportistaNombre').value = data.razon_social || '';
            document.getElementById('guiaTransportistaDireccion').value = data.direccion || '';
            showToast('✅ Transportista cargado', 'success');
        } else {
            showToast('❌ No se encontró el RUC', 'error');
        }
    } catch (error) {
        showToast('❌ Error al consultar', 'error');
    }
}

// ============================================================
// TOGGLE TRANSPORTISTA
// ============================================================

function toggleTransportistaGuia() {
    const modalidad = document.getElementById('guiaModalidadTransporte').value;
    const card = document.getElementById('guiaTransportistaCard');
    const msg = document.getElementById('guiaMsgTransportePrivado');
    const ruc = document.getElementById('guiaTransportistaRUC');
    const nombre = document.getElementById('guiaTransportistaNombre');
    const direccion = document.getElementById('guiaTransportistaDireccion');
    
    if (modalidad === 'PRIVADO') {
        card.style.opacity = '0.5';
        msg.style.display = 'block';
        ruc.disabled = true;
        nombre.disabled = true;
        direccion.disabled = true;
        ruc.style.background = '#F1F5F9';
        nombre.style.background = '#F1F5F9';
        direccion.style.background = '#F1F5F9';
    } else {
        card.style.opacity = '1';
        msg.style.display = 'none';
        ruc.disabled = false;
        nombre.disabled = false;
        direccion.disabled = false;
        ruc.style.background = '#FFFFFF';
        nombre.style.background = '#FFFFFF';
        direccion.style.background = '#FFFFFF';
    }
}

// ============================================================
// PRODUCTOS DE GUÍA
// ============================================================

function agregarFilaProductoGuia() {
    const tbody = document.getElementById('guiaProductosBody');
    if (!tbody) {
        console.warn('⚠️ guiaProductosBody no encontrado, no se puede agregar fila');
        return;
    }
    
    const count = tbody.children.length + 1;
    const tr = document.createElement('tr');
    tr.innerHTML = `
        <td style="padding:2px 4px; text-align:center; font-weight:800; background:#F8FAFC; font-size:9px;">${count}</td>
        <td style="padding:2px 4px;">
            <input class="guia-producto-codigo" placeholder="Código" 
                   style="width:100%; border:1px solid #E5E7EB; border-radius:3px; font-size:8px; padding:2px 4px; background:#FFFFFF;">
        </td>
        <td style="padding:2px 4px;">
            <input class="guia-producto-desc" placeholder="Descripción" 
                   style="width:100%; border:1px solid #E5E7EB; border-radius:3px; font-size:8px; padding:2px 4px; background:#FFFFFF;" 
                   onchange="actualizarPesoTotalGuia()">
        </td>
        <td style="padding:2px 4px;">
            <select class="guia-producto-unidad" style="width:100%; border:1px solid #E5E7EB; border-radius:3px; font-size:8px; padding:2px 4px; background:#FFFFFF;">
                <option value="NIU">NIU</option>
                <option value="KGM">KGM</option>
                <option value="LTR">LTR</option>
                <option value="MTR">MTR</option>
                <option value="ZZ">ZZ</option>
            </select>
        </td>
        <td style="padding:2px 4px;">
            <input class="guia-producto-cant" type="number" value="1" min="0.01" step="0.01" 
                   style="width:100%; border:1px solid #E5E7EB; border-radius:3px; font-size:8px; padding:2px 4px; text-align:center; font-weight:900; background:#FFFFFF;" 
                   onchange="actualizarPesoTotalGuia()">
        </td>
        <td style="padding:2px 4px;">
            <input class="guia-producto-peso" type="number" value="0.50" step="0.01" 
                   style="width:100%; border:1px solid #E5E7EB; border-radius:3px; font-size:8px; padding:2px 4px; text-align:center; background:#FFFFFF;" 
                   onchange="actualizarPesoTotalGuia()">
        </td>
        <td style="padding:2px 4px; text-align:center;">
            <button class="btn-tachito" title="Eliminar este producto" onclick="this.closest('tr').remove(); actualizarPesoTotalGuia(); actualizarContadorProductosGuia();">🗑️</button>
        </td>
    `;
    tbody.appendChild(tr);
    
    // Actualizar contadores
    actualizarContadorProductosGuia();
    actualizarPesoTotalGuia();
}

function actualizarPesoTotalGuia() {
    let total = 0;
    let count = 0;
    
    const tbody = document.getElementById('guiaProductosBody');
    if (!tbody) {
        console.warn('⚠️ guiaProductosBody no encontrado');
        return;
    }
    
    tbody.querySelectorAll('tr').forEach(row => {
        const cant = parseFloat(row.querySelector('.guia-producto-cant')?.value || 0);
        const peso = parseFloat(row.querySelector('.guia-producto-peso')?.value || 0);
        if (cant > 0 && peso > 0) {
            total += cant * peso;
            count++;
        }
    });
    
    // Actualizar elementos de forma segura
    const pesoDisplay = document.getElementById('guiaPesoTotalDisplay');
    if (pesoDisplay) pesoDisplay.textContent = total.toFixed(2);
    
    const productosCount = document.getElementById('guiaProductosCount');
    if (productosCount) productosCount.textContent = count + ' productos';
    
    const totalProductosCount = document.getElementById('guiaTotalProductosCount');
    if (totalProductosCount) totalProductosCount.textContent = count;
    
    const pesoField = document.getElementById('guiaPeso');
    if (pesoField) pesoField.value = total.toFixed(2);
}
function actualizarContadorProductosGuia() {
    const tbody = document.getElementById('guiaProductosBody');
    const count = tbody ? tbody.querySelectorAll('tr').length : 0;
    
    const productosCount = document.getElementById('guiaProductosCount');
    if (productosCount) productosCount.textContent = count + ' productos';
    
    const totalProductosCount = document.getElementById('guiaTotalProductosCount');
    if (totalProductosCount) totalProductosCount.textContent = count;
}

// ============================================================
// RECOLECTAR DATOS DE GUÍA
// ============================================================

function recolectarDatosGuia() {
    // ============================================================
    // ORIGEN FIJO - DATOS DEL REMITENTE
    // ============================================================
    const ORIGEN_FIJO = {
        ruc: '20602095704',
        nombre: 'KCF CORPORACION E.I.R.L',
        direccion: 'JR. LAS ALMENDRAS VERDES NRO. 284 URB. VIRGEN DEL ROSARIO LIMA - LIMA - SAN MARTIN DE PORRES',
        ubigeo: '150139',
        departamento: 'LIMA',
        provincia: 'LIMA',
        distrito: 'SAN MARTIN DE PORRES'
    };
    aplicarEmpresaAlOrigen(ORIGEN_FIJO);   // multiempresa: remitente = empresa elegida arriba
    
    const items = [];
    document.querySelectorAll('#guiaProductosBody tr').forEach((row, idx) => {
        const codigo = row.querySelector('.guia-producto-codigo')?.value || '';
        const descripcion = row.querySelector('.guia-producto-desc')?.value || '';
        const unidad = row.querySelector('.guia-producto-unidad')?.value || 'NIU';
        const cantidad = parseFloat(row.querySelector('.guia-producto-cant')?.value || 0);
        const peso_unitario = parseFloat(row.querySelector('.guia-producto-peso')?.value || 0);
        if (descripcion && cantidad > 0) {
            items.push({
                item: idx + 1,
                codigo: codigo || `ITEM-${idx+1}`,
                descripcion: descripcion,
                unidad: unidad,
                cantidad: cantidad,
                peso_unitario: peso_unitario
            });
        }
    });
    
    return {
        serie: "T001",
        fecha_emision: document.getElementById('guiaFechaEmision').value || isoLima(),
        fecha_traslado: document.getElementById('guiaFechaEmision').value || isoLima(),
        fecha_inicio_traslado: document.getElementById('guiaFechaInicio').value || isoLima(),
        motivo_traslado: document.getElementById('guiaMotivo').value || '',
        modalidad_transporte: document.getElementById('guiaModalidadTransporte').value || 'PRIVADO',
        peso_bruto_total: parseFloat(document.getElementById('guiaPeso').value) || 0,
        unidad_peso_bruto: document.getElementById('guiaUnidadPeso').value || 'KGM',
        numero_bultos: parseInt(document.getElementById('guiaBultos').value) || 1,
        orden_compra_cliente: document.getElementById('guiaOrdenCompra').value || '',
        documento_asociado: document.getElementById('guiaCotizacion').value || '',
        factura: document.getElementById('guiaFactura').value || '',
        observaciones: document.getElementById('guiaObservaciones').value || '',
        // ============================================================
        // REMITENTE - DATOS FIJOS
        // ============================================================
        remitente: {
            ruc: ORIGEN_FIJO.ruc,
            nombre: ORIGEN_FIJO.nombre,
            direccion: ORIGEN_FIJO.direccion,
            ubigeo: ORIGEN_FIJO.ubigeo,
            departamento: ORIGEN_FIJO.departamento,
            provincia: ORIGEN_FIJO.provincia,
            distrito: ORIGEN_FIJO.distrito
        },
        // ============================================================
        // DESTINATARIO - DATOS DEL CLIENTE
        // ============================================================
        destinatario: {
            ruc: document.getElementById('guiaRuc').value || '',
            nombre: document.getElementById('guiaCliente').value || '',
            direccion: document.getElementById('guiaDestino').value || '',
            ubigeo: document.getElementById('guiaUbigeoDestino').value || '',
            departamento: document.getElementById('guiaDeptoDestino').value || '',
            provincia: document.getElementById('guiaProvDestino').value || '',
            distrito: document.getElementById('guiaDistDestino').value || ''
        },
        vehiculo: {
            placa: document.getElementById('guiaPlaca').value || '',
            conductor_dni: document.getElementById('guiaConductorDNI').value || '',
            conductor_nombre: document.getElementById('guiaConductorNombre').value || '',
            licencia_conducir: document.getElementById('guiaLicencia').value || ''
        },
        transportista: document.getElementById('guiaModalidadTransporte').value === 'PUBLICO' ? {
            ruc: document.getElementById('guiaTransportistaRUC').value || '',
            nombre: document.getElementById('guiaTransportistaNombre').value || '',
            direccion: document.getElementById('guiaTransportistaDireccion').value || ''
        } : null,
        items: items
    };
}


function validarGuia(data) {
    if (!data.destinatario.ruc) { showToast('⚠️ RUC del destinatario requerido', 'warning'); return false; }
    if (!data.destinatario.nombre) { showToast('⚠️ Razón social requerida', 'warning'); return false; }
    if (!data.vehiculo.placa) { showToast('⚠️ Placa del vehículo requerida', 'warning'); return false; }
    if (!data.motivo_traslado) { showToast('⚠️ Motivo de traslado requerido', 'warning'); return false; }
    if (!data.fecha_inicio_traslado) { showToast('⚠️ Fecha de inicio requerida', 'warning'); return false; }
    if (!data.unidad_peso_bruto) { showToast('⚠️ Unidad de peso requerida', 'warning'); return false; }
    if (data.peso_bruto_total <= 0) { showToast('⚠️ Peso bruto mayor a 0', 'warning'); return false; }
    if (data.numero_bultos <= 0) { showToast('⚠️ N° bultos mayor a 0', 'warning'); return false; }
    if (data.items.length === 0) { showToast('⚠️ Agregue al menos un producto', 'warning'); return false; }
    return true;
}

// ============================================================
// ENVIAR GUÍA
// ============================================================

async function enviarGuiaSunat() {
    const data = recolectarDatosGuia();
    if (!validarGuia(data)) return;
    
    showToast('⏳ Enviando guía a SUNAT...', 'info');
    try {
        const response = await fetch('/guias/api/enviar-sunat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await response.json();
        if (result.success) {
            showToast(`✅ Guía enviada: ${result.numero_guia}`, 'success');
            closeModal('guiaModal');
            if (typeof loadGuias === 'function') loadGuias();
        } else {
            showToast('❌ Error: ' + (result.error || 'No se pudo enviar'), 'error');
        }
    } catch (error) {
        showToast('❌ Error de conexión', 'error');
    }
}




// ============================================================
// VALIDACIÓN PC VS COTIZACIÓN - FUNCIÓN COMPLETA Y CORREGIDA
// ============================================================
function renderValidacion() {
    const q = document.getElementById('valSearch')?.value?.toLowerCase() || '';
    const filtro = document.getElementById('valFiltro')?.value || '';
    
    console.log('🔍 Renderizando validación con', pedidosData?.length || 0, 'PCs');
    
    const validaciones = [];
    
    pedidosData.forEach(p => {
        // 🔽 LEER VALIDACIONES REALES DE LA BD
        const validaPrecios = p.valida_precios !== undefined ? p.valida_precios : true;
        const validaCantidades = p.valida_cantidades !== undefined ? p.valida_cantidades : true;
        const validaStock = p.valida_stock !== undefined ? p.valida_stock : true;
        const validaEntrega = p.valida_entrega !== undefined ? p.valida_entrega : true;
        const validaMoneda = p.valida_moneda !== undefined ? p.valida_moneda : true;
        const validaTransporte = p.valida_transporte !== undefined ? p.valida_transporte : true;
        const validaVigencia = p.valida_vigencia !== undefined ? p.valida_vigencia : true;
        const validaMargen = p.valida_margen !== undefined ? p.valida_margen : true;
        
        // Obtener items del PC
        let items = p.items || [];
        
        // Si items está vacío pero hay items_json, parsearlo
        if (items.length === 0 && p.items_json) {
            try {
                if (typeof p.items_json === 'string') {
                    items = JSON.parse(p.items_json);
                } else if (Array.isArray(p.items_json)) {
                    items = p.items_json;
                }
            } catch(e) {
                console.warn('⚠️ Error parseando items_json:', e);
                items = [];
            }
        }
        
        // Si el PC no tiene items, usar datos básicos
        if (items.length === 0) {
            const estadoPC = p.estado || 'Pendiente';
            // ⚠️ STOCK NO BLOQUEA - solo informativo
            const esObservado = estadoPC === 'PC observado' || 
                               estadoPC === 'Bloqueado' ||
                               !validaPrecios || !validaCantidades || !validaEntrega || !validaMoneda;
            
            // Determinar faltante de stock (informativo)
            let faltante = 0;
            let stockDisplay = '✅ Stock OK';
            if (p.stock !== undefined && p.cantidad_pc !== undefined) {
                faltante = Math.max(p.cantidad_pc - p.stock, 0);
                stockDisplay = faltante > 0 ? `⚠️ Stock insuficiente (faltan ${faltante})` : '✅ Stock OK';
            }
            
            validaciones.push({
                pc: p.numero || p.pc || 'PC-XXXX',
                cliente: p.cliente || 'Sin cliente',
                producto: p.descripcion || p.producto || 'Producto sin descripción',
                precio: validaPrecios ? '✅ Sí' : '❌ No',
                cantidad: validaCantidades ? '✅ Sí' : '❌ No',
                entrega: validaEntrega ? '✅ Sí' : '❌ No',
                moneda: validaMoneda ? '✅ Sí' : '❌ No',
                transporte: validaTransporte ? '✅ Sí' : '❌ No',
                vigencia: validaVigencia ? '✅ Sí' : '❌ No',
                stock: stockDisplay,
                estado: estadoPC,
                id: p.id,
                req_compra: p.req_compra || (esObservado ? 'Bloqueado' : 'Sí'),
                precioOk: validaPrecios,
                cantidadOk: validaCantidades,
                entregaOk: validaEntrega,
                monedaOk: validaMoneda,
                transporteOk: validaTransporte,
                vigenciaOk: validaVigencia,
                stockOk: validaStock,
                margenOk: validaMargen,
                faltante: faltante,
                esObservado: esObservado
            });
        } else {
            // Cada item es una fila de validación
            items.forEach((item, idx) => {
                let codigo, descripcion, cantidad_pc, cantidad_cot, stock, precio_pc, precio_cot;
                
                // Soporte para formato de objeto o array
                if (typeof item === 'object' && !Array.isArray(item)) {
                    codigo = item.codigo || '';
                    descripcion = item.producto || item.descripcion || 'Sin descripción';
                    cantidad_pc = parseFloat(item.cantidad_pc || item.cantidad || 0);
                    cantidad_cot = parseFloat(item.cantidad_cotizada || item.cantidad_cot || 0);
                    stock = parseFloat(item.stock || 0);
                    precio_pc = parseFloat(item.precio_pc || item.precio || 0);
                    precio_cot = parseFloat(item.precio_cotizado || item.precio_cot || 0);
                } else if (Array.isArray(item)) {
                    codigo = item[0] || '';
                    descripcion = item[1] || 'Sin descripción';
                    cantidad_cot = parseFloat(item[2] || 0);
                    cantidad_pc = parseFloat(item[3] || 1);
                    precio_cot = parseFloat(item[4] || 0);
                    precio_pc = parseFloat(item[5] || 0);
                    stock = parseFloat(item[6] || 0);
                } else {
                    codigo = '';
                    descripcion = 'Sin descripción';
                    cantidad_pc = 1;
                    cantidad_cot = 0;
                    stock = 0;
                    precio_pc = 0;
                    precio_cot = 0;
                }
                
                // ⚠️ STOCK NO BLOQUEA - solo informativo
                const precioOk = validaPrecios && (precio_pc === 0 || precio_cot === 0 || Math.abs(precio_pc - precio_cot) / (precio_cot || 1) * 100 <= 5);
                const cantidadOk = validaCantidades && (cantidad_pc === cantidad_cot);
                const stockOk = validaStock && (cantidad_pc <= stock);
                const entregaOk = validaEntrega;
                const monedaOk = validaMoneda;
                const transporteOk = validaTransporte;
                const vigenciaOk = validaVigencia;
                const margenOk = validaMargen;
                
                const estadoPC = p.estado || 'Pendiente';
                // ⚠️ OBSERVADO SOLO POR VALIDACIONES, NO POR STOCK
                const esObservado = estadoPC === 'PC observado' || 
                                   estadoPC === 'Bloqueado' ||
                                   !precioOk || !cantidadOk || !entregaOk || !monedaOk;
                
                const faltante = Math.max(cantidad_pc - stock, 0);
                const stockDisplay = stockOk ? `✅ Stock: ${stock}` : `⚠️ Falta: ${faltante}`;
                
                validaciones.push({
                    pc: p.numero || p.pc || 'PC-XXXX',
                    cliente: p.cliente || 'Sin cliente',
                    producto: descripcion,
                    precio: precioOk ? '✅ Sí' : '❌ No',
                    cantidad: cantidadOk ? '✅ Sí' : '❌ No',
                    entrega: entregaOk ? '✅ Sí' : '❌ No',
                    moneda: monedaOk ? '✅ Sí' : '❌ No',
                    transporte: transporteOk ? '✅ Sí' : '❌ No',
                    vigencia: vigenciaOk ? '✅ Sí' : '❌ No',
                    stock: stockDisplay,
                    estado: estadoPC,
                    id: p.id,
                    req_compra: p.req_compra || (esObservado ? 'Bloqueado' : 'Sí'),
                    item_idx: idx,
                    precioOk: precioOk,
                    cantidadOk: cantidadOk,
                    entregaOk: entregaOk,
                    monedaOk: monedaOk,
                    transporteOk: transporteOk,
                    vigenciaOk: vigenciaOk,
                    stockOk: stockOk,
                    margenOk: margenOk,
                    faltante: faltante,
                    esObservado: esObservado,
                    // Datos para mostrar stock
                    stock_actual: stock,
                    cantidad_pc: cantidad_pc,
                    cantidad_cot: cantidad_cot,
                    precio_pc: precio_pc,
                    precio_cot: precio_cot
                });
            });
        }
    });
    
    // Aplicar filtros
    let data = validaciones;
    
    if (q) {
        data = data.filter(v => 
            JSON.stringify(v).toLowerCase().includes(q)
        );
    }
    
    // ⚠️ FILTROS MODIFICADOS - STOCK NO BLOQUEA
    if (filtro === 'ok') {
        // "Conforme" = TODAS las validaciones OK (incluyendo stock para información)
        data = data.filter(v => 
            v.precio === '✅ Sí' && 
            v.cantidad === '✅ Sí' && 
            v.entrega === '✅ Sí' && 
            v.moneda === '✅ Sí' && 
            v.transporte === '✅ Sí' &&
            v.vigencia === '✅ Sí'
            // ⚠️ STOCK NO INCLUIDO EN EL FILTRO "OK"
        );
    } else if (filtro === 'observado') {
        data = data.filter(v => 
            v.precio === '❌ No' || 
            v.cantidad === '❌ No' || 
            v.entrega === '❌ No' || 
            v.moneda === '❌ No' ||
            v.transporte === '❌ No' ||
            v.vigencia === '❌ No' ||
            v.estado === 'PC observado' ||
            v.estado === 'Bloqueado'
        );
    } else if (filtro === 'compra') {
        // "Requiere compra" = stock insuficiente (informativo)
        data = data.filter(v => 
            v.faltante > 0 || 
            v.req_compra === 'Sí'
        );
    }
    
    const tbody = document.getElementById('valRows');
    if (!tbody) return;
    
    if (data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="12" style="text-align:center;color:#94A3B8;padding:40px;">
            📭 No hay validaciones que coincidan con los filtros
        </td></tr>`;
        const countEl = document.getElementById('valCount');
        if (countEl) countEl.textContent = `Mostrando 0 de ${validaciones.length} validaciones`;
        return;
    }
    
    // ============================================================
    // RENDERIZAR TABLA - STOCK INFORMATIVO
    // ============================================================
    tbody.innerHTML = data.map((v, i) => {
        // ⚠️ TODAS VALIDAS SIN STOCK
        const todasValidas = v.precio === '✅ Sí' && 
                            v.cantidad === '✅ Sí' && 
                            v.entrega === '✅ Sí' && 
                            v.moneda === '✅ Sí' && 
                            v.transporte === '✅ Sí' &&
                            v.vigencia === '✅ Sí' &&
                            v.margenOk !== false;
        
        const esObservado = v.precio === '❌ No' || 
                           v.cantidad === '❌ No' || 
                           v.entrega === '❌ No' || 
                           v.moneda === '❌ No' ||
                           v.transporte === '❌ No' ||
                           v.vigencia === '❌ No';
        
        // Determinar resultado y acción
        let resultado = '';
        let badgeClass = '';
        let accionHtml = '';
        
        if (todasValidas && v.faltante <= 0) {
            resultado = '✅ Listo para despacho';
            badgeClass = 'badge-val-ok';
            accionHtml = `<button class="btn btn-green btn-sm" onclick="enviarADespacho(${v.id})" style="height:20px; padding:0 8px; font-size:8px; border-radius:4px; border:none; background:#16A34A; color:#fff; font-weight:800; cursor:pointer;" title="Crea el despacho y te lleva a Entregas">🚚 Enviar a Entregas</button>`;
        } else if (todasValidas && v.faltante > 0) {
            resultado = '🔄 Requiere compra (stock insuficiente)';
            badgeClass = 'badge-val-warning';
            accionHtml = `<button class="btn btn-warning btn-sm" onclick="generarOrdenCompra(${v.id})" style="height:20px; padding:0 8px; font-size:8px; border-radius:4px; border:none; background:#F59E0B; color:#000; font-weight:800; cursor:pointer;">🛒 Comprar</button>
                          <button class="btn btn-green btn-sm" onclick="enviarADespacho(${v.id})" style="height:20px; padding:0 8px; font-size:8px; border-radius:4px; border:none; background:#16A34A; color:#fff; font-weight:800; cursor:pointer; margin-left:4px;" title="Crea el despacho y te lleva a Entregas">🚚 Enviar a Entregas</button>`;
        } else if (esObservado) {
            resultado = '⚠️ Bloqueado por observación';
            badgeClass = 'badge-val-error';
            accionHtml = `<button class="btn btn-danger btn-sm" onclick="solicitarCorreccion(${v.id})" style="height:20px; padding:0 8px; font-size:8px; border-radius:4px; border:none; background:#DC2626; color:#fff; font-weight:800; cursor:pointer;">📝 Corregir</button>`;
        } else {
            resultado = '⏳ Pendiente de validación';
            badgeClass = 'badge-val-warning';
            accionHtml = `<button class="btn btn-blue btn-sm" onclick="validarPCSAP()" style="height:20px; padding:0 8px; font-size:8px; border-radius:4px; border:none; background:#2563EB; color:#fff; font-weight:800; cursor:pointer;">🔍 Validar</button>`;
        }
        
        // Determinar color de stock
        const stockClass = v.faltante > 0 ? 'val-warning' : 'val-ok';
        const stockBg = v.faltante > 0 ? '#FEF3C7' : '#D1FAE5';
        const stockColor = v.faltante > 0 ? '#92400E' : '#065F46';
        
        return `
        <tr>
            <td style="padding:4px 6px; font-weight:900; font-size:10px;">${esc(v.pc)}</td>
            <td class="left" style="padding:4px 6px; font-weight:800; font-size:10px;">${esc(v.cliente)}</td>
            <td class="left" style="padding:4px 6px; font-size:10px;">${esc(v.producto)}</td>
            <!-- PRECIO -->
            <td style="padding:4px 6px; text-align:center;">
                <div style="display:flex; flex-direction:column; align-items:center; gap:2px;">
                    <span style="font-size:14px;">💰</span>
                    <span class="${v.precio === '✅ Sí' ? 'val-ok' : 'val-error'}" style="font-weight:900; font-size:10px; padding:2px 8px; border-radius:10px; background:${v.precio === '✅ Sí' ? '#D1FAE5' : '#FEE2E2'}; color:${v.precio === '✅ Sí' ? '#065F46' : '#991B1B'};">
                        ${v.precio}
                    </span>
                </div>
            </td>
            <!-- CANTIDAD -->
            <td style="padding:4px 6px; text-align:center;">
                <div style="display:flex; flex-direction:column; align-items:center; gap:2px;">
                    <span style="font-size:14px;">🔢</span>
                    <span class="${v.cantidad === '✅ Sí' ? 'val-ok' : 'val-error'}" style="font-weight:900; font-size:10px; padding:2px 8px; border-radius:10px; background:${v.cantidad === '✅ Sí' ? '#D1FAE5' : '#FEE2E2'}; color:${v.cantidad === '✅ Sí' ? '#065F46' : '#991B1B'};">
                        ${v.cantidad}
                    </span>
                </div>
            </td>
            <!-- ENTREGA -->
            <td style="padding:4px 6px; text-align:center;">
                <div style="display:flex; flex-direction:column; align-items:center; gap:2px;">
                    <span style="font-size:14px;">📍</span>
                    <span class="${v.entrega === '✅ Sí' ? 'val-ok' : 'val-error'}" style="font-weight:900; font-size:10px; padding:2px 8px; border-radius:10px; background:${v.entrega === '✅ Sí' ? '#D1FAE5' : '#FEE2E2'}; color:${v.entrega === '✅ Sí' ? '#065F46' : '#991B1B'};">
                        ${v.entrega}
                    </span>
                </div>
            </td>
            <!-- MONEDA -->
            <td style="padding:4px 6px; text-align:center;">
                <div style="display:flex; flex-direction:column; align-items:center; gap:2px;">
                    <span style="font-size:14px;">💱</span>
                    <span class="${v.moneda === '✅ Sí' ? 'val-ok' : 'val-error'}" style="font-weight:900; font-size:10px; padding:2px 8px; border-radius:10px; background:${v.moneda === '✅ Sí' ? '#D1FAE5' : '#FEE2E2'}; color:${v.moneda === '✅ Sí' ? '#065F46' : '#991B1B'};">
                        ${v.moneda}
                    </span>
                </div>
            </td>
            <!-- TRANSPORTE -->
            <td style="padding:4px 6px; text-align:center;">
                <div style="display:flex; flex-direction:column; align-items:center; gap:2px;">
                    <span style="font-size:14px;">🚚</span>
                    <span class="${v.transporte === '✅ Sí' ? 'val-ok' : 'val-error'}" style="font-weight:900; font-size:10px; padding:2px 8px; border-radius:10px; background:${v.transporte === '✅ Sí' ? '#D1FAE5' : '#FEE2E2'}; color:${v.transporte === '✅ Sí' ? '#065F46' : '#991B1B'};">
                        ${v.transporte || '✅ Sí'}
                    </span>
                </div>
            </td>
            <!-- VIGENCIA -->
            <td style="padding:4px 6px; text-align:center;">
                <div style="display:flex; flex-direction:column; align-items:center; gap:2px;">
                    <span style="font-size:14px;">📅</span>
                    <span class="${v.vigencia === '✅ Sí' ? 'val-ok' : 'val-error'}" style="font-weight:900; font-size:10px; padding:2px 8px; border-radius:10px; background:${v.vigencia === '✅ Sí' ? '#D1FAE5' : '#FEE2E2'}; color:${v.vigencia === '✅ Sí' ? '#065F46' : '#991B1B'};">
                        ${v.vigencia || '✅ Sí'}
                    </span>
                </div>
            </td>
            <!-- STOCK - INFORMATIVO, NO BLOQUEA -->
            <td style="padding:4px 6px; text-align:center;">
                <span class="stock-info" style="font-weight:900; font-size:9px; padding:2px 8px; border-radius:10px; background:${stockBg}; color:${stockColor};">
                    ${v.stock}
                </span>
                ${v.faltante > 0 ? `<div style="font-size:7px; color:#DC2626; margin-top:2px;">⚠️ Faltan ${v.faltante} unidades</div>` : ''}
            </td>
            <!-- RESULTADO -->
            <td style="padding:4px 6px; text-align:center;">
                <span class="badge-val ${badgeClass}" style="font-weight:800; font-size:9px; padding:2px 10px; border-radius:10px; background:${badgeClass === 'badge-val-ok' ? '#D1FAE5' : badgeClass === 'badge-val-error' ? '#FEE2E2' : '#FEF3C7'}; color:${badgeClass === 'badge-val-ok' ? '#065F46' : badgeClass === 'badge-val-error' ? '#991B1B' : '#92400E'};">
                    ${resultado}
                </span>
            </td>
            <!-- ACCIÓN -->
            <td style="padding:4px 6px; text-align:center;">
                ${accionHtml}
            </td>
        </tr>`;
    }).join('');
    
    const countEl = document.getElementById('valCount');
    if (countEl) {
        countEl.textContent = `Mostrando ${data.length} de ${validaciones.length} validaciones`;
    }
}

// Función para vista previa del PDF (abre en nueva pestaña)
window.previewCotizacionPdf = function(id) {
    console.log(`👁️ Abriendo vista previa PDF para cotización ID: ${id}`);
    
    try {
        // Abrir el PDF en una nueva pestaña
        const url = `/ventas/api/cotizaciones/${id}/pdf/preview`;
        window.open(url, '_blank');
        showToast('📄 Abriendo vista previa del PDF...', 'info');
    } catch (error) {
        console.error('❌ Error abriendo vista previa:', error);
        showToast('❌ Error al abrir la vista previa: ' + error.message, 'error');
    }
};

// Función de validación actualizada - SIN MARGEN (solo muestra toast)
function validarPCSAP() {
    console.log('🔍 Validando PC...');
    
    // Obtener valores de validación de los switches
    const validaciones = {
        precio: document.getElementById('vPrecio')?.checked || false,
        producto: document.getElementById('vProducto')?.checked || false,
        entrega: document.getElementById('vEntrega')?.checked || false,
        transporte: document.getElementById('vTransporte')?.checked || false,
        cantidad: document.getElementById('vCantidad')?.checked || false,
        moneda: document.getElementById('vMoneda')?.checked || false,
        vigencia: document.getElementById('vVigencia')?.checked || false
    };
    
    // Contar cuántos están OK
    const total = Object.values(validaciones).length;
    const okCount = Object.values(validaciones).filter(v => v === true).length;
    const noCount = total - okCount;
    
    // Verificar si hay items en la tabla
    const itemsCount = document.querySelectorAll('#pcItemsBody tr').length;
    if (itemsCount === 0) {
        showToast('⚠️ Agrega al menos un producto al PC', 'warning');
        return;
    }
    
    // Verificar stock
    let stockAlert = false;
    let stockFaltante = 0;
    document.querySelectorAll('#pcItemsBody tr').forEach(row => {
        const inputs = row.querySelectorAll('input');
        if (inputs.length >= 9) {
            const cantidadPC = Number(inputs[5]?.value || 0);
            const stock = Number(inputs[8]?.value || 0);
            if (cantidadPC > stock) {
                stockAlert = true;
                stockFaltante += (cantidadPC - stock);
            }
        }
    });
    
    // Construir lista de validaciones fallidas
    const labels = {
        precio: ' Precio',
        producto: ' Producto',
        entrega: ' Lugar Entrega',
        transporte: ' Transporte',
        cantidad: ' Cantidad',
        moneda: ' Moneda',
        vigencia: ' Vigencia'
    };
    
    const detalles = [];
    Object.entries(validaciones).forEach(([key, ok]) => {
        if (!ok) {
            detalles.push(labels[key] || key);
        }
    });
    
    if (stockAlert) {
        detalles.push(`📦 Stock insuficiente (faltan ${stockFaltante} unidades)`);
    }
    
    // Generar mensaje según resultado
    let mensaje = '';
    let tipo = 'info';
    
    if (noCount === 0 && !stockAlert) {
        mensaje = `✅ ¡Validación exitosa! Todos los ${total} puntos están correctos y hay stock suficiente.`;
        tipo = 'success';
    } else if (noCount > 0 && stockAlert) {
        mensaje = `❌ Validación fallida: ${noCount} punto(s) incorrectos y stock insuficiente.\n🔴 ${detalles.join(', ')}`;
        tipo = 'error';
    } else if (noCount > 0) {
        mensaje = `⚠️ Validación con observaciones: ${noCount} punto(s) marcado(s) como "No".\n🔴 ${detalles.join(', ')}`;
        tipo = 'warning';
    } else if (stockAlert) {
        mensaje = `⚠️ Stock insuficiente: faltan ${stockFaltante} unidades para completar el PC.`;
        tipo = 'warning';
    }
    
    // Mostrar toast con el resultado
    showToast(mensaje, tipo);
    
    // Mostrar resumen en consola
    console.log(`📊 Resumen de validación:
    - Total puntos: ${total}
    - Correctos: ${okCount}
    - Incorrectos: ${noCount}
    - Stock alert: ${stockAlert ? '⚠️ Sí' : '✅ No'}
    - Detalles: ${detalles.join(', ') || 'Todos OK'}`);
    
    return {
        success: noCount === 0 && !stockAlert,
        okCount: okCount,
        noCount: noCount,
        stockAlert: stockAlert,
        detalles: detalles
    };
}


// ============================================================
// OBTENER ITEMS DEL PC - FUNCIÓN AUXILIAR
// ============================================================

function obtenerItemsPCSAP() {
    const items = [];
    const rows = document.querySelectorAll('#pcItemsBody tr');
    
    rows.forEach(row => {
        const inputs = row.querySelectorAll('input');
        if (inputs.length >= 8) {
            items.push([
                inputs[0]?.value || '',      // código
                inputs[1]?.value || '',      // descripción
                parseFloat(inputs[2]?.value) || 0,  // cantidad cotizada
                parseFloat(inputs[3]?.value) || 1,   // cantidad PC
                parseFloat(inputs[4]?.value) || 0,   // precio cotizado
                parseFloat(inputs[5]?.value) || 0,   // precio PC
                parseFloat(inputs[6]?.value) || 0    // stock
            ]);
        }
    });
    
    return items;
}


// ============================================================
// ACCIONES DE VALIDACIÓN
// ============================================================
function solicitarCorreccion(id) {
    // Buscar el PC para mostrar info
    const pedido = pedidosData.find(p => p.id === id);
    if (!pedido) {
        showToast('❌ PC no encontrado', 'error');
        return;
    }
    
    const numero = pedido.numero || 'PC-XXXXXX';
    const cliente = pedido.cliente || 'Cliente';
    const estado = pedido.estado || 'Desconocido';
    
    // Mostrar confirmación
    showConfirmModal(
        '📝 Solicitar corrección al cliente',
        `El PC <b>${numero}</b> del cliente <b>${cliente}</b> tiene observaciones.<br><br>
        Estado actual: <b>${estado}</b><br><br>
        Se abrirá el PC en modo edición para que puedas revisar y corregir los datos.<br>
        <span style="color:#DC2626;">⚠️ Después de corregir, deberás guardar nuevamente el PC.</span>`,
        '⚠️ El PC quedará en estado "En revisión interna" hasta que se complete la corrección.',
        async function() {
            try {
                // 1. Cambiar estado a "En revisión interna"
                showToast('⏳ Procesando...', 'info');
                
                const response = await apiFetch(`/ventas/api/pedido-compra/${id}/toggle`, {
                    method: 'PUT',
                    body: JSON.stringify({ estado: 'En revisión interna' })
                });
                
                if (!response.success) {
                    showToast('❌ Error al cambiar estado: ' + (response.error || 'Desconocido'), 'error');
                    return;
                }
                
                showToast('✅ PC enviado a revisión interna', 'success');
                
                // 2. Recargar datos
                await loadPedidos();
                renderValidacion();
                
                // 3. 🔽 ABRIR EL PC EN MODO EDICIÓN CON TODOS LOS DATOS
                setTimeout(() => {
                    // Cambiar a la pestaña de PC
                    const tabBtn = document.querySelector('.tab-btn[data-tab="pedido_compra"]');
                    if (tabBtn) tabBtn.click();
                    
                    // Abrir el modal en modo edición
                    setTimeout(() => {
                        console.log(`📋 Abriendo PC ID: ${id} para corrección`);
                        openPedidoCompraModalSAP('editar', id);
                    }, 400);
                }, 500);
                
            } catch (error) {
                console.error('❌ Error en solicitarCorreccion:', error);
                showToast('❌ Error al solicitar corrección: ' + error.message, 'error');
            }
        },
        '📝 Sí, abrir para corregir'
    );
}


function generarOrdenCompra(id) {
    showConfirmModal(
        '🛒 Generar orden de compra',
        `El PC requiere compra de productos por falta de stock.`,
        '⚠️ Se abrirá Compras → Pedidos por comprar, donde está la tabla de lo que falta comprar.',
        async function() {
            window.location.href = '/compras?tab=pedidos';
        },
        '🛒 Generar compra'
    );
}

async function enviarADespacho(id) {
    const pedido = pedidosData.find(p => p.id === id);
    if (!pedido) {
        showToast('❌ PC no encontrado', 'error');
        return;
    }
    
    const numero = pedido.numero || 'PC-XXXXXX';
    const cliente = pedido.cliente || 'Cliente';
    
    showConfirmModal(
        '🚚 Enviar a despacho',
        `Estás a punto de enviar el PC <b>${numero}</b> del cliente <b>${cliente}</b> a la cola de despacho.`,
        '⚠️ Esta acción creará un registro de despacho y moverá el PC a "Listo para despacho".',
        async function() {
            try {
                showToast('⏳ Procesando envío a despacho...', 'info');
                
                // PASO 1: Cambiar el estado del PC
                const toggleResponse = await apiFetch(`/ventas/api/pedido-compra/${id}/toggle`, {
                    method: 'PUT',
                    body: JSON.stringify({ estado: 'Listo para despacho' })
                });
                
                if (!toggleResponse.success) {
                    showToast('❌ Error al actualizar PC: ' + (toggleResponse.error || 'Desconocido'), 'error');
                    return;
                }
                
                console.log('✅ PC actualizado a "Listo para despacho"');
                
                // ============================================================
                // OBTENER LOS ITEMS DEL PC (PRODUCTOS)
                // ============================================================
                let items = pedido.items || [];
                
                // Si items está vacío pero hay items_json, parsearlo
                if (items.length === 0 && pedido.items_json) {
                    try {
                        if (typeof pedido.items_json === 'string') {
                            items = JSON.parse(pedido.items_json);
                        } else if (Array.isArray(pedido.items_json)) {
                            items = pedido.items_json;
                        }
                    } catch(e) {
                        console.warn('⚠️ Error parseando items_json:', e);
                        items = [];
                    }
                }
                
                // Normalizar items para el despacho
                const itemsNormalizados = items.map(item => {
                    // Si es un objeto con propiedades
                    if (typeof item === 'object' && !Array.isArray(item)) {
                        return {
                            codigo: item.codigo || '',
                            producto: item.producto || item.descripcion || 'Sin descripción',
                            marca: item.marca || '',
                            modelo: item.modelo || '',
                            cantidad: parseFloat(item.cantidad_pc || item.cantidad || 1),
                            um: item.um || 'NIU',
                            stock: parseInt(item.stock || 0)
                        };
                    }
                    // Si es un array
                    if (Array.isArray(item)) {
                        return {
                            codigo: item[0] || '',
                            producto: item[1] || 'Sin descripción',
                            marca: item[2] || '',
                            modelo: item[3] || '',
                            cantidad: parseFloat(item[5] || item[3] || 1),
                            um: 'NIU',
                            stock: parseInt(item[8] || 0)
                        };
                    }
                    return null;
                }).filter(item => item !== null);
                
                console.log('📦 Items normalizados para despacho:', itemsNormalizados);
                
                // ============================================================
                // CREAR EL DESPACHO CON LOS ITEMS
                // ============================================================
                const ahora = new Date();
                const year = ahora.getFullYear();
                const month = String(ahora.getMonth() + 1).padStart(2, '0');
                const day = String(ahora.getDate()).padStart(2, '0');
                const hours = String(ahora.getHours()).padStart(2, '0');
                const minutes = String(ahora.getMinutes()).padStart(2, '0');
                const seconds = String(ahora.getSeconds()).padStart(2, '0');
                
                const fechaHoraISO = `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
                
                const despachoData = {
                    pc_id: id,
                    pc_numero: pedido.numero,
                    cliente: pedido.cliente,
                    ruc: pedido.ruc,
                    cotizacion_id: pedido.cotizacion_id,
                    cotizacion_numero: pedido.cotizacion_numero,
                    fecha_despacho: fechaHoraISO,
                    origen: 'ALM-SMP',
                    destino: pedido.lugar_entrega || pedido.entrega || '',
                    estado: 'Pendiente despacho',
                    observaciones: `Despacho automático desde PC ${pedido.numero}`,
                    responsable: 'Hellen',
                    numero: `DESP-${year}${month}${day}-${String(ahora.getTime()).slice(-4)}`,
                    // 🔽 INCLUIR LOS ITEMS EN EL DESPACHO
                    items: itemsNormalizados
                };
                
                console.log('📦 Enviando despacho con items:', despachoData);
                
                const despachoResponse = await fetch('/ventas/api/despachos/guardar', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(despachoData)
                });
                
                const despachoResult = await despachoResponse.json();
                console.log('📦 Respuesta:', despachoResult);
                
                if (despachoResult.success) {
                    showToast('✅ PC enviado a despacho con sus productos', 'success');
                    
                    await loadPedidos();
                    await loadDespachos();
                    renderValidacion();
                    
                    // Cambiar a "Entregas" y resaltar el despacho recién creado (pedido de Erika 20/10/2026)
                    irAPestanaYResaltar('despachar', 'despachoSearch',
                        [((Array.isArray(despachoResult.data) ? despachoResult.data[0] : despachoResult.data) || {}).numero, despachoData.numero, pedido.numero],
                        typeof renderDespachos === 'function' ? renderDespachos : null);
                    
                } else {
                    showToast('❌ Error al crear despacho: ' + (despachoResult.error || 'Desconocido'), 'error');
                }
                
            } catch (error) {
                console.error('❌ Error:', error);
                showToast('❌ Error al enviar a despacho: ' + error.message, 'error');
            }
        },
        '🚚 Sí, enviar a despacho'
    );
}

// ============================================================
// LIMPIAR FILTROS DE FECHA - PC
// ============================================================

function clearPcDateFilter() {
    console.log('🧹 Limpiando filtros de fecha de PC...');
    
    const fechaInicio = document.getElementById('pcFechaInicio');
    const fechaFin = document.getElementById('pcFechaFin');
    
    if (fechaInicio) {
        fechaInicio.value = '';
    }
    
    if (fechaFin) {
        fechaFin.value = '';
    }
    
    // Volver a renderizar la tabla de pedidos
    renderPedidos();
    
    showToast('🧹 Filtros de fecha limpiados', 'info');
}

// Exportar la función
window.clearPcDateFilter = clearPcDateFilter;


// ==
// ==========================================================
// FUNCIONES PARA PC PEDIDO COMPRAS - ESTILO SAP
// ============================================================

let pcModalMode = 'cot';

function openPedidoCompraModal(mode = 'cot') {
    pcModalMode = mode;
    editingId = null;
    
    const isEdit = mode !== 'cot' && mode !== 'directo';
    const title = isEdit ? 'Editar PC Cliente' : (mode === 'cot' ? 'Crear PC desde cotización' : 'PC directo / sin cotización');
    document.getElementById('pedidoCompraModalTitle').textContent = title;
    
    const formContainer = document.getElementById('pedidoCompraForm');
    if (!formContainer) return;
    
    const modeNote = mode === 'cot' 
        ? '✅ Recomendado: jalar la cotización, crear PC espejo y validar contra el documento real del cliente.' 
        : '';
    
    const showCotBlock = mode === 'cot' ? '' : 'style="display:none;"';
    
    // Generar opciones de cotizaciones
    const cotOptions = cotizacionesData.map(q => 
        `<option value="${q.id}">${q.numero} · ${q.razon || 'Sin cliente'}</option>`
    ).join('');
    
    formContainer.innerHTML = `
        <div class="form-section">
            <div class="section-title">Resumen de control del documento</div>
            <div class="sap-doc-summary">
                <div class="sap-doc-box"><small>Documento</small><b>PC Cliente</b></div>
                <div class="sap-doc-box"><small>Origen</small><b>${mode === 'cot' ? 'Cotización' : 'Directo'}</b></div>
                <div class="sap-doc-box"><small>Control</small><b>Validación obligatoria</b></div>
                <div class="sap-doc-box"><small>Stock</small><b>Reserva / Compra</b></div>
                <div class="sap-doc-box"><small>Salida</small><b>Guía / Factura</b></div>
            </div>
        </div>
        
        <div class="form-section" ${showCotBlock}>
            <div class="section-title">1. Cotización relacionada</div>
            <div class="ficha-grid">
                <div class="form-field col-8">
                    <label>Buscar cotización</label>
                    <select id="pcCotSelect" onchange="loadPedidoCotizacion()">
                        ${cotOptions || '<option value="">Sin cotizaciones disponibles</option>'}
                    </select>
                </div>
                <div class="form-field col-2">
                    <label>N° cotización</label>
                    <input id="pcCotNumero" readonly>
                </div>
                <div class="form-field col-2">
                    <label>Fecha cotización</label>
                    <input id="pcCotFecha" readonly>
                </div>
            </div>
        </div>
        
        <div class="form-section">
            <div class="section-title">2. Datos PC Pedido de Compra Cliente</div>
            <div class="ficha-grid">
                <div class="form-field col-3">
                    <label>Fecha llegada</label>
                    <input id="pcFecha" type="datetime-local">
                </div>
                <div class="form-field col-2">
                    <label>Medio recepción</label>
                    <select id="pcMedio">
                        <option>Correo</option>
                        <option>WhatsApp</option>
                        <option>Plataforma</option>
                        <option>Llamada</option>
                    </select>
                </div>
                <div class="form-field col-3">
                    <label>N° PC / OC cliente</label>
                    <input id="pcNumero" placeholder="PC-20260709-0001">
                </div>
                <div class="form-field col-2">
                    <label>Condición pago</label>
                    <select id="pcCondicion">
                        <option>Contado</option>
                        <option>30 días</option>
                        <option>45 días</option>
                        <option>60 días</option>
                        <option>90 días</option>
                        <option>50% / 50%</option>
                    </select>
                </div>
                <div class="form-field col-2">
                    <label>RUC</label>
                    <input id="pcRuc">
                </div>
                <div class="form-field col-4">
                    <label>Cliente</label>
                    <input id="pcCliente">
                </div>
                <div class="form-field col-2">
                    <label>Moneda</label>
                    <select id="pcMoneda">
                        <option>Soles (S/)</option>
                        <option>Dólares ($)</option>
                    </select>
                </div>
                <div class="form-field col-2">
                    <label>Contacto</label>
                    <input id="pcContacto">
                </div>
                <div class="form-field col-2">
                    <label>Monto PC</label>
                    <input id="pcMonto" type="number" step="0.01" value="0">
                </div>
                <div class="form-field col-4">
                    <label>Lugar entrega PC</label>
                    <input id="pcEntrega">
                </div>
                <div class="form-field col-12">
                    <label>Sustento / observación</label>
                    <textarea id="pcObs" placeholder="Pegar comentario, link de correo, WhatsApp, observación del cliente..."></textarea>
                </div>
            </div>
        </div>
        
        <div class="form-section">
            <div class="section-title">3. Ítems del PC cliente</div>
            <div class="table-scroll">
                <table class="master-table">
                    <thead>
                        <tr>
                            <th>Item</th>
                            <th>Código de producto</th>
                            <th>Descripción</th>
                            <th>Cant. cotizada</th>
                            <th>Cant. PC</th>
                            <th>Precio cotizado</th>
                            <th>Precio PC</th>
                            <th>Stock</th>
                            <th>Faltante</th>
                        </tr>
                    </thead>
                    <tbody id="pcItemsBody"></tbody>
                </table>
            </div>
            <div style="margin-top:8px;">
                <button class="btn btn-soft" onclick="addPedidoItem()">+ Agregar ítem</button>
            </div>
        </div>
        
        <div class="form-section">
    <div class="section-title">4. Validación comercial obligatoria</div>
    <div class="pc-check-grid">
        <div class="pc-check-card">
            <label>
                <span id="vPrecioIcon">⚪</span> Precio coincide
            </label>
            <select id="vPrecio" class="pc-val-select" onchange="updateValidationStatus()">
                <option value="Sí">✅ Sí</option>
                <option value="No">❌ No</option>
            </select>
        </div>
        <div class="pc-check-card">
            <label>
                <span id="vCantidadIcon">⚪</span> Cantidad coincide
            </label>
            <select id="vCantidad" class="pc-val-select" onchange="updateValidationStatus()">
                <option value="Sí">✅ Sí</option>
                <option value="No">❌ No</option>
            </select>
        </div>
        <div class="pc-check-card">
            <label>
                <span id="vProductoIcon">⚪</span> Producto/modelo coincide
            </label>
            <select id="vProducto" class="pc-val-select" onchange="updateValidationStatus()">
                <option value="Sí">✅ Sí</option>
                <option value="No">❌ No</option>
            </select>
        </div>
        <div class="pc-check-card">
            <label>
                <span id="vEntregaIcon">⚪</span> Lugar entrega coincide
            </label>
            <select id="vEntrega" class="pc-val-select" onchange="updateValidationStatus()">
                <option value="Sí">✅ Sí</option>
                <option value="No">❌ No</option>
            </select>
        </div>
        <div class="pc-check-card">
            <label>
                <span id="vMonedaIcon">⚪</span> Moneda coincide
            </label>
            <select id="vMoneda" class="pc-val-select" onchange="updateValidationStatus()">
                <option value="Sí">✅ Sí</option>
                <option value="No">❌ No</option>
            </select>
        </div>
        <div class="pc-check-card">
            <label>
                <span id="vTransporteIcon">⚪</span> Transporte considerado
            </label>
            <select id="vTransporte" class="pc-val-select" onchange="updateValidationStatus()">
                <option value="Sí">✅ Sí</option>
                <option value="No">❌ No</option>
            </select>
        </div>
        <div class="pc-check-card">
            <label>
                <span id="vVigenciaIcon">⚪</span> Cotización vigente
            </label>
            <select id="vVigencia" class="pc-val-select" onchange="updateValidationStatus()">
                <option value="Sí">✅ Sí</option>
                <option value="No">❌ No</option>
            </select>
        </div>
        <div class="pc-check-card">
            <label>
                <span id="vMargenIcon">⚪</span> Margen conforme
            </label>
            <select id="vMargen" class="pc-val-select" onchange="updateValidationStatus()">
                <option value="Sí">✅ Sí</option>
                <option value="No">❌ No</option>
            </select>
        </div>
    </div>
    <div id="validationResult" class="mini-note" style="margin-top:10px;">
        ℹ️ Si algún punto es <b>"No"</b>, el PC quedará <b>observado y bloqueado</b>.
    </div>
</div>
    `;
    
    // Inicializar valores por defecto
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    document.getElementById('pcFecha').value = now.toISOString().slice(0, 16);
    document.getElementById('pcNumero').value = 'PC-' + isoLima().replaceAll('-', '') + '-' + String(Date.now()).slice(-4);
    
    // Agregar un ítem por defecto
    addPedidoItem();
    
    // Si es modo cotización, cargar la primera cotización
    if (mode === 'cot') {
        setTimeout(loadPedidoCotizacion, 100);
    }
    
    document.getElementById('pedidoCompraModal').classList.add('show');
}

function loadPedidoCotizacion() {
    const select = document.getElementById('pcCotSelect');
    if (!select || !select.value) return;
    
    const cotId = parseInt(select.value);
    const cotizacion = cotizacionesData.find(c => c.id === cotId);
    if (!cotizacion) return;
    
    document.getElementById('pcCotNumero').value = cotizacion.numero || '';
    document.getElementById('pcCotFecha').value = cotizacion.fecha || '';
    document.getElementById('pcRuc').value = cotizacion.ruc || '';
    document.getElementById('pcCliente').value = cotizacion.razon || '';
    document.getElementById('pcContacto').value = cotizacion.contacto || '';
    document.getElementById('pcMoneda').value = cotizacion.moneda || 'Soles (S/)';
    document.getElementById('pcEntrega').value = cotizacion.direccion_entrega || '';
    // monto de la cotización ya incluye IGV: base sin IGV = total - igv (evita doble IGV)
    const _pcConIgv = Number(cotizacion.total || cotizacion.monto || 0);
    const _pcSinIgv = cotizacion.igv != null ? _pcConIgv - Number(cotizacion.igv || 0) : Number(cotizacion.subtotal || 0);
    const _pcMontoEl = document.getElementById('pcMonto');
    const _pcMontoIgvEl = document.getElementById('pcMontoConIgv');
    if (_pcMontoEl) _pcMontoEl.value = _pcSinIgv.toFixed(2);
    if (_pcMontoIgvEl) _pcMontoIgvEl.value = _pcConIgv.toFixed(2);
    
    // Cargar productos de la cotización
    const productos = cotizacion.productos || [];
    const tbody = document.getElementById('pcItemsBody');
    if (tbody) {
        tbody.innerHTML = '';
        productos.forEach((p, i) => {
            const faltante = Math.max((p.cantidad || 0) - (p.stock || 0), 0);
            tbody.insertAdjacentHTML('beforeend', `
                <tr>
                    <td>${i + 1}</td>
                    <td><input value="${p.codigo || ''}" style="width:90px;"></td>
                    <td><input value="${p.producto || p.descripcion || ''}" style="width:160px;"></td>
                    <td><input type="number" value="${p.cantidad || 0}" style="width:60px;"></td>
                    <td><input type="number" value="${p.cantidad || 1}" style="width:60px;"></td>
                    <td><input type="number" step="0.01" value="${p.valorVenta || 0}" style="width:80px;"></td>
                    <td><input type="number" step="0.01" value="${p.valorVenta || 0}" style="width:80px;"></td>
                    <td><input type="number" value="${p.stock || 0}" style="width:60px;"></td>
                    <td>${faltante}</td>
                </tr>
            `);
        });
        
        if (productos.length === 0) {
            addPedidoItem();
        }
    }
}

function addPedidoItem() {
    const tbody = document.getElementById('pcItemsBody');
    if (!tbody) return;
    const idx = tbody.children.length + 1;
    tbody.insertAdjacentHTML('beforeend', `
        <tr>
            <td>${idx}</td>
            <td><input value="" style="width:90px;"></td>
            <td><input value="" style="width:160px;"></td>
            <td><input type="number" value="0" style="width:60px;"></td>
            <td><input type="number" value="1" style="width:60px;"></td>
            <td><input type="number" step="0.01" value="0" style="width:80px;"></td>
            <td><input type="number" step="0.01" value="0" style="width:80px;"></td>
            <td><input type="number" value="0" style="width:60px;"></td>
            <td>0</td>
        </tr>
    `);
}


function cargarDatalistProductos() {
    const dl = document.getElementById('productMasterList');
    if (!dl) return;
    
    if (!PRODUCTOS_MAESTROS || PRODUCTOS_MAESTROS.length === 0) {
        dl.innerHTML = `<option value="Cargando productos...">`;
        cargarProductosMaestros();
        return;
    }
    
    // label muestra información extra pero value es solo el código
    dl.innerHTML = PRODUCTOS_MAESTROS.map(p => {
        const label = `${p.codigo} - ${p.producto}${p.marca ? ' (' + p.marca + ')' : ''}`;
        return `<option value="${p.codigo}" label="${label}">${label}</option>`;
    }).join('');
}

function addQuoteProductFromSearch() {
    const input = document.getElementById('quickProductSearch');
    const valor = input ? input.value.trim() : '';
    
    console.log('🔍 Buscando producto por código:', valor);
    
    if (!valor) {
        showToast('💡 Escribe el código del producto', 'info');
        return;
    }
    
    if (PRODUCTOS_MAESTROS.length === 0) {
        showToast('⏳ Cargando productos...', 'info');
        cargarProductosMaestros().then(() => {
            setTimeout(() => addQuoteProductFromSearch(), 500);
        });
        return;
    }
    
    // Buscar por código EXACTO
    const q = valor.trim();
    let productoEncontrado = PRODUCTOS_MAESTROS.find(p => 
        p.codigo && p.codigo.toLowerCase() === q.toLowerCase()
    );
    
    // Si no, buscar por código que contenga
    if (!productoEncontrado) {
        productoEncontrado = PRODUCTOS_MAESTROS.find(p => 
            p.codigo && p.codigo.toLowerCase().includes(q.toLowerCase())
        );
    }
    
    if (!productoEncontrado) {
        showToast(`❌ Producto con código "${q}" no encontrado`, 'error');
        return;
    }
    
    // Agregar el producto
    const nuevoProducto = {
        ...productoEncontrado,
        cantidad: 1,
        valorVenta: parseFloat(productoEncontrado.valorVenta) || 0,
        stock: parseInt(productoEncontrado.stock) || 0
    };
    
    quoteProducts.push(nuevoProducto);
    if (input) input.value = '';
    renderQuoteProducts();
    calcQuote();
    showToast(`✅ "${productoEncontrado.producto}" agregado`, 'success');
}


function renderQuoteProducts() {
    const tbody = document.getElementById('quoteProductRows');
    if (!tbody) return;
    
    if (quoteProducts.length === 0) {
        tbody.innerHTML = `<tr><td colspan="12" style="text-align:center;color:#94A3B8;padding:20px;">📭 Agregue productos a la cotización</td></tr>`;
        return;
    }
    
    tbody.innerHTML = quoteProducts.map((p, i) => {
        const cantidad = Number(p.cantidad || 1);
        p.valorVenta = (window.redondear2 || (n => Math.round((Number(n) || 0) * 100 + Number.EPSILON) / 100))(p.valorVenta); // máximo 2 decimales (pedido de Erika 19/10)
        const valorVenta = Number(p.valorVenta || 0);
        // 🔽 VALOR TOTAL SIN IGV (solo cantidad × valor unitario)
        const valorTotalSinIgv = cantidad * valorVenta;
        
        return `
        <tr>
            <td class="col-item">${i + 1}</td>
            <td class="col-code">${p.codigo || '-'}</td>
            <td class="left">
                <div class="product-name">${p.producto || p.descripcion || 'Sin nombre'}</div>
                <div class="product-desc">${p.descripcion || ''}</div>
            </td>
            <td class="col-model">${p.modelo || '-'}</td>
            <td class="col-brand">${p.marca || '-'}</td>
            <td class="col-unit">
                <select class="um-select" onchange="quoteProducts[${i}].um=this.value">
                    ${SUNAT_UNIDADES.map(u => `<option value="${u.codigo}" ${p.um === u.codigo || p.um === u.nombre ? 'selected' : ''}>${u.codigo}</option>`).join('')}
                </select>
            </td>
            <td class="col-qty"><input style="width:70px;text-align:right" value="${p.cantidad || 1}" type="number" min="1" onchange="quoteProducts[${i}].cantidad=Number(this.value);renderQuoteProducts();calcQuote();"></td>
            <td class="col-price"><input style="width:90px;text-align:right" value="${Number(p.valorVenta || 0).toFixed(2)}" type="number" step="0.01" onchange="quoteProducts[${i}].valorVenta=Math.round(Number(this.value)*100)/100;renderQuoteProducts();calcQuote();"></td>
            <td class="col-total"><b>${money(valorTotalSinIgv)}</b></td>
            <td class="col-stock">${stockVivo(p.codigo, p.stock)}</td>
            <td class="col-delivery">
                <select class="entrega-select ${p.estado_entrega === 'Entregado' ? 'entrega-ok' : 'entrega-pend'}" title="Estado de entrega de este producto"
                        onchange="quoteProducts[${i}].estado_entrega=this.value;this.className='entrega-select '+(this.value==='Entregado'?'entrega-ok':'entrega-pend');">
                    <option value="Pendiente" ${p.estado_entrega !== 'Entregado' ? 'selected' : ''}>Pendiente</option>
                    <option value="Entregado" ${p.estado_entrega === 'Entregado' ? 'selected' : ''}>Entregado</option>
                </select>
            </td>
            <td class="col-actions">
                <button class="btn-tachito" title="Eliminar este producto" onclick="quoteProducts.splice(${i},1);renderQuoteProducts();calcQuote();">🗑️</button>
            </td>
        </tr>
    `}).join('');
}



function calcQuote() {
    const r2 = (window.redondear2 || (n => Math.round((Number(n) || 0) * 100 + Number.EPSILON) / 100));
    const subtotal = r2(quoteProducts.reduce((s, p) => s + r2(Number(p.cantidad || 0) * r2(p.valorVenta)), 0));
    
    // Descuento especial desde el campo fDescuentoEspecial (nuevo)
    const descuentoEspecial = Number(document.getElementById('fDescuentoEspecial')?.value || 0);
    const dv = Number(document.getElementById('fDiscountValue')?.value || 0);
    const dt = document.getElementById('fDiscountType')?.value || '%';
    
    // Sumar descuento especial + descuento normal
    const discount = r2((dt === '%' ? subtotal * (dv / 100) : Math.min(dv, subtotal)) + descuentoEspecial);
    const valorVenta = r2(subtotal - discount);
    const igv = r2(valorVenta * CONFIG.igv);
    const total = r2(valorVenta + igv);
    
    const tiempoEntrega = getFieldValue('fTiempo', 'fTiempoCustom') || '5 días hábiles';
    
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    set('sumSubtotal', money(subtotal));
    set('sumDiscountPct', dt === '%' ? dv.toFixed(2) + '%' : money(dv));
    set('sumDiscount', '-' + money(discount));
    set('sumValorVenta', money(valorVenta));  // ← ESTA LÍNEA ES CLAVE
    set('sumIgv', money(igv));
    set('sumTotal', money(total));
    set('sumTiempoEntrega', tiempoEntrega);
}

async function loadClient() {
    const rucInput = document.getElementById('fRucSearch');
    const ruc = rucInput?.value?.replace(/\D/g, '').trim() || '';
    
    if (!ruc) {
        showToast('⚠️ Ingresa un RUC para consultar.', 'warning');
        return;
    }
    if (ruc.length !== 11) {
        showToast('⚠️ El RUC debe tener 11 dígitos.', 'warning');
        return;
    }
    
    const btnBuscar = document.querySelector('.btn-search-ruc');
    const originalText = btnBuscar?.textContent || '🔍 Buscar';
    if (btnBuscar) {
        btnBuscar.textContent = '⏳ Consultando...';
        btnBuscar.disabled = true;
    }
    
    try {
        console.log('🔍 Buscando cliente en base de datos por RUC:', ruc);
        
        const bdResponse = await fetch(`/maestros/api/clientes/buscar?q=${ruc}`);
        const bdData = await bdResponse.json();
        
        console.log('📦 Respuesta BD:', bdData);
        
        if (bdData.success && bdData.data && bdData.data.length > 0) {
            const cliente = bdData.data[0];
            // 🔽 DEBUG TEMPORAL
console.log('👤 Cliente completo:', cliente);
console.log('📋 Contactos recibidos:', cliente.contactos);
console.log('📍 Puntos de entrega:', cliente.puntos_entrega);
window._ultimoCliente = cliente; // ← para poder inspeccionarlo en consola
            // ============================================================
            // 1. DATOS DEL CLIENTE
            // ============================================================
            const fRuc = document.getElementById('fRuc');
            const fRazon = document.getElementById('fRazon');
            const fDireccion = document.getElementById('fDireccion');
            const fTelefono = document.getElementById('fTelefono');
            const fCorreo = document.getElementById('fCorreo');
            const fReq = document.getElementById('fReq');
            const fFuente = document.getElementById('fFuente');
            
            if (fRuc) fRuc.value = cliente.ruc || ruc;
            if (fRazon) fRazon.value = cliente.razon_social || '';
            if (fDireccion) fDireccion.value = cliente.direccion_fiscal || '';
            
            // ============================================================
            // 2. CARGAR CONTACTOS EN EL SELECT
            // ============================================================
            cargarContactosEnSelect(cliente);
            
            // ============================================================
            // 3. CONDICIONES COMERCIALES - NO SE AUTOCARGA NADA
            // ============================================================
            const fVendedor = document.getElementById('fVendedor');
            const fEmailAsesor = document.getElementById('fEmailAsesor');
            const fTelefonoAsesor = document.getElementById('fTelefonoAsesor');
            const fMoneda = document.getElementById('fMoneda');
            const fValidez = document.getElementById('fValidez');
            const fDescuentoEspecial = document.getElementById('fDescuentoEspecial');
            const fNotaComercial = document.getElementById('fNotaComercial');
            
            if (fVendedor) fVendedor.value = CONFIG.asesorDefault;
            if (fEmailAsesor) fEmailAsesor.value = CONFIG.emailAsesorDefault;
            if (fTelefonoAsesor) fTelefonoAsesor.value = CONFIG.telefonoAsesorDefault;
            if (fMoneda) fMoneda.value = 'Soles (S/.)';
            
            // Dirección de entrega
            let direccionEntrega = '';
            if (cliente.puntos_entrega && cliente.puntos_entrega.length > 0) {
                const principal = cliente.puntos_entrega.find(p => p.principal === true);
                if (principal) {
                    direccionEntrega = principal.direccion || '';
                } else {
                    direccionEntrega = cliente.puntos_entrega[0].direccion || '';
                }
            }
            if (!direccionEntrega && cliente.direccion_fiscal) {
                direccionEntrega = cliente.direccion_fiscal;
            }
            if (direccionEntrega) {
                const fDireccionEntrega = document.getElementById('fDireccionEntrega');
                if (fDireccionEntrega) {
                    setFieldValue('fDireccionEntrega', 'fDireccionEntregaCustom', direccionEntrega);
                }
            }
            
            // Validez por defecto
            if (fValidez) fValidez.value = '15 días';
            
            if (fDescuentoEspecial) fDescuentoEspecial.value = 0;
            if (fNotaComercial) fNotaComercial.value = '';
            if (fReq) fReq.value = '';
            if (fFuente) fFuente.value = 'Correo';
            
            cargarDireccionesClienteEnSelect(cliente);
            
            const confirmBox = document.getElementById('clientConfirmBox');
            if (confirmBox) {
                let mensaje = `✅ Cliente encontrado en sistema`;
                if (cliente.codigo_cliente) {
                    mensaje += ` | Código: ${cliente.codigo_cliente}`;
                }
                confirmBox.textContent = mensaje;
                confirmBox.className = 'show existente';
                setTimeout(() => { confirmBox.className = ''; }, 6000);
            }
            
            showToast(`✅ Cliente encontrado: ${cliente.razon_social}`, 'success');
            return;
        }
        
        // ============================================================
        // SI NO ESTÁ EN BD, CONSULTAR SUNAT
        // ============================================================
        console.log('🌞 Cliente no encontrado en BD, consultando SUNAT...');
        
        const sunatResponse = await fetch(`/api/sunat/consulta?ruc=${ruc}`);
        const sunatData = await sunatResponse.json();
        
        if (sunatData.success) {
            const fRuc = document.getElementById('fRuc');
            const fRazon = document.getElementById('fRazon');
            const fDireccion = document.getElementById('fDireccion');
            const fCorreo = document.getElementById('fCorreo');
            
            if (fRuc) fRuc.value = sunatData.ruc || ruc;
            if (fRazon) fRazon.value = sunatData.razon_social || '';
            if (fDireccion) fDireccion.value = sunatData.direccion || '';
            if (fCorreo) fCorreo.value = sunatData.email || '';
            
            // Limpiar select de contactos (no hay contactos porque es nuevo)
            const selectContacto = document.getElementById('fContacto');
            if (selectContacto) {
                selectContacto.innerHTML = '<option value="">-- Escriba un contacto manualmente --</option>';
            }
            mostrarInputContactoLibre();
            
            const confirmBox = document.getElementById('clientConfirmBox');
            if (confirmBox) {
                confirmBox.textContent = '🌞 Datos consultados en SUNAT';
                confirmBox.className = 'show nuevo';
                setTimeout(() => { confirmBox.className = ''; }, 5000);
            }
            
            showToast('🌞 Datos cargados desde SUNAT', 'info');
        } else {
            showToast('❌ ' + (sunatData.error || 'Error al consultar SUNAT'), 'error');
            const confirmBox = document.getElementById('clientConfirmBox');
            if (confirmBox) {
                confirmBox.textContent = '❌ ' + (sunatData.error || 'Error al consultar SUNAT');
                confirmBox.className = 'show error';
                setTimeout(() => { confirmBox.className = ''; }, 5000);
            }
        }
        
    } catch (error) {
        console.error('❌ Error en loadClient:', error);
        showToast('❌ Error al conectar con el servicio', 'error');
    } finally {
        if (btnBuscar) {
            btnBuscar.textContent = originalText;
            btnBuscar.disabled = false;
        }
    }
}


let __rucAutoTimer = null;

function autoLoadClientByRuc(value) {
    clearTimeout(__rucAutoTimer);
    const ruc = (value || '').trim();
    if (ruc.length === 11) {
        __rucAutoTimer = setTimeout(() => loadClient(), 500);
    } else if (ruc.length > 11) {
        const input = document.getElementById('fRucSearch');
        if (input) input.value = ruc.substring(0, 11);
    }
}


// ============================================================
// CARGAR CONTACTOS DEL CLIENTE EN EL SELECT
// ============================================================
function cargarContactosEnSelect(cliente) {
    const select = document.getElementById('fContacto');
    const customInput = document.getElementById('fContactoCustom');
    const fTelefono = document.getElementById('fTelefono');
    const fCorreo = document.getElementById('fCorreo');
    
    if (!select) return;
    
    // Limpiar select
    select.innerHTML = '';
    
    // Ocultar input personalizado
    if (customInput) {
        customInput.style.display = 'none';
        customInput.value = '';
    }
    
    // Verificar si hay contactos
    const contactos = cliente.contactos || [];
    
    if (contactos.length === 0) {
        // Sin contactos: usar el input libre
        select.innerHTML = '<option value="__custom__">✏️ Escribir contacto manualmente</option>';
        select.value = '__custom__';
        mostrarInputContactoLibre();
        
        // Autocompletar con datos aplanados del cliente (si existen)
        if (fTelefono) fTelefono.value = cliente.telefono_contacto || '';
        if (fCorreo) fCorreo.value = cliente.email_contacto || '';
        return;
    }
    
    // Hay contactos: poblar el select
    select.innerHTML = '<option value="">-- Seleccione un contacto --</option>';
    
    contactos.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.id;
        const nombre = c.nombre || c.nombre_contacto || '';
        const cargo = c.cargo || '';
        const esPrincipal = c.principal === true;
        
        // Formatear texto: ⭐ Nombre (Cargo)
        let texto = nombre;
        if (cargo) texto += ` (${cargo})`;
        if (esPrincipal) texto = `⭐ ${texto} — Principal`;
        
        opt.textContent = texto;
        
        // Guardar datos en dataset para autocompletar
        opt.dataset.telefono = c.telefono || '';
        opt.dataset.email = c.email || '';
        opt.dataset.nombre = nombre;
        opt.dataset.cargo = cargo;
        opt.dataset.principal = esPrincipal ? '1' : '0';
        
        select.appendChild(opt);
    });
    
    // Agregar opción "Personalizado" al final
    const optCustom = document.createElement('option');
    optCustom.value = '__custom__';
    optCustom.textContent = '✏️ Escribir otro contacto...';
    select.appendChild(optCustom);
    
    // Seleccionar el principal por defecto
    const principal = contactos.find(c => c.principal === true);
    if (principal) {
        select.value = principal.id;
    } else if (contactos.length > 0) {
        select.value = contactos[0].id;
    }
    
    // Aplicar el contacto seleccionado
    aplicarContactoSeleccionado();
    
    console.log(`✅ ${contactos.length} contactos cargados en el select`);
}


// ============================================================
// APLICAR CONTACTO SELECCIONADO (autocompletar tel/email)
// ============================================================
function aplicarContactoSeleccionado() {
    const select = document.getElementById('fContacto');
    const customInput = document.getElementById('fContactoCustom');
    const fTelefono = document.getElementById('fTelefono');
    const fCorreo = document.getElementById('fCorreo');
    
    if (!select) return;
    
    const opt = select.options[select.selectedIndex];
    
    // Si es "Personalizado", mostrar input libre
    if (select.value === '__custom__') {
        mostrarInputContactoLibre();
        if (customInput) customInput.focus();
        return;
    }
    
    // Ocultar input libre
    if (customInput) {
        customInput.style.display = 'none';
        customInput.value = '';
    }
    
    // Si no hay opción seleccionada, no hacer nada
    if (!opt || !opt.dataset.nombre) return;
    
    // Autocompletar teléfono y email
    if (fTelefono) fTelefono.value = opt.dataset.telefono || '';
    if (fCorreo) fCorreo.value = opt.dataset.email || '';
    
    console.log(`👤 Contacto aplicado: ${opt.dataset.nombre} | Tel: ${opt.dataset.telefono} | Email: ${opt.dataset.email}`);
}


// ============================================================
// MOSTRAR INPUT LIBRE (cuando no hay contactos o se elige personalizado)
// ============================================================
function mostrarInputContactoLibre() {
    const customInput = document.getElementById('fContactoCustom');
    if (customInput) {
        customInput.style.display = 'block';
    }
}


// En ventas.js - Reemplaza la función markGuiaEmitida
function markGuiaEmitida(id) {
    const guia = guiasData.find(g => g.id === id);
    const numero = guia?.numero || 'G-XXXXXX';
    const cliente = guia?.cliente || 'Cliente';
    
    showConfirmModal(
        '📄 ¿Emitir guía?',
        `Estás a punto de emitir la guía <b>${numero}</b> del cliente <b>${cliente}</b>.`,
        '⚠️ Esta acción es irreversible. La guía quedará emitida oficialmente.',
        async function() {
            try {
                const response = await apiFetch(`/ventas/api/guias/${id}/toggle`, {
                    method: 'PUT',
                    body: JSON.stringify({ estado: 'Emitida' })
                });
                if (response.success) {
                    showToast('✅ Guía emitida correctamente', 'success');
                    await loadGuias();
                } else {
                    showToast('❌ Error: ' + (response.error || 'No se pudo emitir'), 'error');
                }
            } catch (error) {
                console.error('❌ Error:', error);
                showToast('❌ Error al emitir guía', 'error');
            }
        },
        '📄 Sí, emitir'
    );
}

// ============================================================
// FUNCIÓN PARA GUARDAR CLIENTE DESDE COTIZACIÓN
// ============================================================

async function saveClientFromQuote() {
    const ruc = document.getElementById('fRuc')?.value?.trim() || '';
    if (!ruc) {
        showToast('⚠️ Primero busca el RUC', 'warning');
        return;
    }
    
    // Validar que tenga razón social
    const razonSocial = document.getElementById('fRazon')?.value?.trim() || '';
    if (!razonSocial) {
        showToast('⚠️ La razón social es obligatoria', 'warning');
        return;
    }
    
    // Mostrar loading en el botón
    const btn = document.querySelector('.btn-save-client');
    const originalText = btn?.textContent || '💾 Guardar / Actualizar';
    if (btn) {
        btn.textContent = '⏳ Guardando...';
        btn.disabled = true;
    }
    
    try {
        // ============================================================
        // PASO 1: VERIFICAR SI EL CLIENTE YA EXISTE EN LA BD
        // ============================================================
        console.log('🔍 Verificando si cliente existe en BD por RUC:', ruc);
        
        const buscarResponse = await fetch(`/maestros/api/clientes/buscar?q=${ruc}`);
        const buscarData = await buscarResponse.json();
        
        const clienteExistente = buscarData.success && buscarData.data && buscarData.data.length > 0;
        
        // ============================================================
        // PREPARAR DATOS DEL CLIENTE
        // ============================================================
     const clienteData = {
    tipo_documento: 'RUC',
    numero_documento: ruc,
    ruc: ruc,
    razon_social: document.getElementById('fRazon')?.value?.trim() || '',
    nombre_comercial: document.getElementById('fComercial')?.value?.trim() || '',
    direccion_fiscal: document.getElementById('fDireccion')?.value?.trim() || '',
   nombre_contacto: getContactoSeleccionadoNombre(),
telefono_contacto: document.getElementById('fTelefono')?.value?.trim() || '',
email_contacto: document.getElementById('fCorreo')?.value?.trim() || '',
    activo: true,
    estado: 'Activo'
};
        // 20/10/2026: la condición de la cotización NO cambia la del cliente (el crédito se aprueba en Maestros ▸ Clientes).
        // Un cliente nuevo creado desde aquí nace al contado; uno existente conserva su condición, contactos y puntos.
        if (!clienteExistente) { clienteData.condicion_pago = 'Contado'; clienteData.dias_credito = 0; }
        console.log('📦 Datos a guardar:', clienteData);
        
        // ============================================================
        // PASO 2: GUARDAR O ACTUALIZAR
        // ============================================================
        let endpoint = '/maestros/api/clientes/guardar';
        let method = 'POST';
        let mensaje = '';
        
        if (clienteExistente) {
            // Actualizar cliente existente
            const clienteId = buscarData.data[0].id;
            endpoint = `/maestros/api/clientes/${clienteId}`;
            method = 'PUT';
            mensaje = 'actualizado';
            console.log('🔄 Cliente existente, actualizando ID:', clienteId);
        } else {
            // Crear nuevo cliente
            mensaje = 'creado';
            console.log('🆕 Cliente nuevo, creando...');
        }
        
        const response = await fetch(endpoint, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(clienteData)
        });
        
        const result = await response.json();
        console.log('📦 Respuesta del servidor:', result);
        
        if (result.success) {
            // ============================================================
            // MOSTRAR MENSAJE DE ÉXITO
            // ============================================================
            const codigoCliente = result.data?.codigo_cliente || 
                                 buscarData.data?.[0]?.codigo_cliente || 
                                 'PENDIENTE';
            
            // Actualizar el código de cliente en el formulario
            document.getElementById('fCodCliente').value = codigoCliente;
            
            // Mostrar mensaje en el confirm box
            const confirmBox = document.getElementById('clientConfirmBox');
            if (confirmBox) {
                const emoji = mensaje === 'creado' ? '✅' : '🔄';
                const texto = mensaje === 'creado' ? 'creado' : 'actualizado';
                confirmBox.textContent = `${emoji} Cliente ${texto} correctamente | Código: ${codigoCliente}`;
                confirmBox.className = 'show existente';
                setTimeout(() => { confirmBox.className = ''; }, 5000);
            }
            
            // Mostrar toast
            showToast(`✅ Cliente ${mensaje} correctamente: ${clienteData.razon_social}`, 'success');
            
            // Actualizar la lista de clientes maestros
            await cargarClientesMaestros();
            
            // Guardar referencia del cliente para uso en la cotización
            window._clienteConsultado = {
                id: result.data?.id || buscarData.data?.[0]?.id,
                ruc: ruc,
                razon_social: clienteData.razon_social,
                nombre_comercial: clienteData.nombre_comercial,
                direccion: clienteData.direccion_fiscal,
                contacto: clienteData.nombre_contacto,
                telefono: clienteData.telefono_contacto,
                email: clienteData.email_contacto,
                codigo_cliente: codigoCliente,
                origen: 'base_datos'
            };
            
        } else {
            showToast('❌ Error: ' + (result.error || 'No se pudo guardar el cliente'), 'error');
        }
        
    } catch (error) {
        console.error('❌ Error guardando cliente:', error);
        showToast('❌ Error al guardar el cliente: ' + error.message, 'error');
    } finally {
        // Restaurar botón
        if (btn) {
            btn.textContent = originalText;
            btn.disabled = false;
        }
    }
}




function productTableHtml(productos) {
    if (!productos || productos.length === 0) {
        return `<div style="padding:20px;text-align:center;color:#94A3B8;">No hay productos</div>`;
    }
    
    return `
        <div class="table-scroll">
            <table class="master-table">
                <thead><tr>
                    <th>Item</th><th>Código de producto</th><th>Nombre producto</th><th>Marca</th><th>UM SUNAT</th>
                    <th>Cant.</th><th>Stock</th>
                </tr></thead>
                <tbody>
                    ${productos.map((p, i) => `
                        <tr>
                            <td>${i+1}</td>
                            <td>${p.codigo || '-'}</td>
                            <td class="left">${p.producto || p.descripcion || '-'}</td>
                            <td>${p.marca || '-'}</td>
                            <td>${p.um || 'NIU'}</td>
                            <td>${p.cantidad || 1}</td>
                            <td>${p.stock || 0}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

function openDespachoModal(id = null) {
    editingId = id;
    const isEdit = id !== null;
    const title = isEdit ? 'Editar despacho' : 'Nuevo despacho';
    document.getElementById('despachoModalTitle').textContent = title;
    
    const formContainer = document.getElementById('despachoForm');
    if (!formContainer) return;
    
    const pcOptions = pedidosData.map(p => 
        `<option value="${p.numero}">${p.numero} - ${p.cliente || 'Sin cliente'}</option>`
    ).join('');
    
    formContainer.innerHTML = `
        <div class="ficha-section">
            <div class="ficha-grid">
                <div class="form-field col-4"><label>PC vinculado</label>
                    <select id="despachoPC">${pcOptions || '<option value="">Sin PC</option>'}</select>
                </div>
                <div class="form-field col-4"><label>N° Despacho</label>
                    <input id="despachoNumero" value="DESP-${String(Date.now()).slice(-8)}">
                </div>
                <div class="form-field col-4"><label>Estado</label>
                    <select id="despachoEstado">
                        ${options(ESTADOS_DESPACHO, 'Pendiente despacho')}
                    </select>
                </div>
                <div class="form-field col-4"><label>Cliente</label>
                    <input id="despachoCliente" placeholder="Razón social">
                </div>
                <div class="form-field col-4"><label>RUC</label>
                    <input id="despachoRuc" placeholder="12345678901">
                </div>
                <div class="form-field col-4"><label>Fecha despacho</label>
                    <input id="despachoFecha" type="date" value="${today()}">
                </div>
                <div class="form-field col-4"><label>Origen</label>
                    <select id="despachoOrigen">
                        <option>ALM-SMP</option>
                        <option>OF-BRE</option>
                        <option>Almacén Central</option>
                    </select>
                </div>
                <div class="form-field col-4"><label>Destino</label>
                    <input id="despachoDestino" placeholder="Dirección de entrega">
                </div>
                <div class="form-field col-4"><label>Transportista</label>
                    <input id="despachoTransportista" placeholder="Nombre o razón social">
                </div>
                <div class="form-field col-12">
                    <label>Observaciones</label>
                    <textarea id="despachoObs" placeholder="Observaciones del despacho"></textarea>
                </div>
            </div>
        </div>
        <div class="ficha-section">
            <div class="ficha-section-title">Productos a despachar</div>
            <div id="despachoProducts">
                <div style="padding:10px;text-align:center;color:#94A3B8;">Seleccione un PC para ver los productos.</div>
            </div>
        </div>
    `;
    
    document.getElementById('despachoPC')?.addEventListener('change', function() {
        const num = this.value;
        const p = pedidosData.find(x => x.numero === num);
        if (p && p.productos && p.productos.length > 0) {
            document.getElementById('despachoProducts').innerHTML = productTableHtml(p.productos);
            document.getElementById('despachoCliente').value = p.cliente || '';
            document.getElementById('despachoRuc').value = p.ruc || '';
            document.getElementById('despachoDestino').value = p.lugar_entrega || '';
        } else {
            document.getElementById('despachoProducts').innerHTML = `
                <div style="padding:10px;text-align:center;color:#94A3B8;">No hay productos en este PC.</div>
            `;
        }
    });
    
    document.getElementById('despachoModal').classList.add('show');
}



// ============================================================
// OBTENER NOMBRE DEL CONTACTO SELECCIONADO (del select o del input)
// ============================================================
function getContactoSeleccionadoNombre() {
    const select = document.getElementById('fContacto');
    const customInput = document.getElementById('fContactoCustom');
    
    if (!select) return '';
    
    // Si es "Personalizado", devolver el valor del input libre
    if (select.value === '__custom__') {
        return customInput?.value?.trim() || '';
    }
    
    // Si no hay contacto seleccionado
    if (!select.value) return '';
    
    // Devolver el nombre del dataset
    const opt = select.options[select.selectedIndex];
    return opt?.dataset?.nombre || opt?.textContent || '';
}

function openGuiaModal(id = null) {
    // ✅ CERRAR CUALQUIER OTRO MODAL ANTES DE ABRIR GUÍA
    const otrosModales = document.querySelectorAll('.modal-bg.show');
    otrosModales.forEach(m => {
        if (m.id !== 'guiaModal') {
            m.classList.remove('show');
            m.style.display = 'none';
        }
    });
    
    console.log('📦 Abriendo modal de guía', { id });
    editingId = id;
    const isEdit = id !== null;
    
    // Verificar que el modal existe
    const modal = document.getElementById('guiaModal');
    if (!modal) {
        console.error('❌ #guiaModal no encontrado');
        showToast('Error: Modal de guía no disponible', 'error');
        return;
    }
    
    // ORIGEN FIJO - DATOS DEL REMITENTE
    const ORIGEN_FIJO = {
        ruc: '20602095704',
        nombre: 'KCF CORPORACION E.I.R.L',
        direccion: 'JR. LAS ALMENDRAS VERDES NRO. 284 URB. VIRGEN DEL ROSARIO LIMA - LIMA - SAN MARTIN DE PORRES',
        ubigeo: '150139',
        departamento: 'LIMA',
        provincia: 'LIMA',
        distrito: 'SAN MARTIN DE PORRES'
    };
    aplicarEmpresaAlOrigen(ORIGEN_FIJO);   // multiempresa: remitente = empresa elegida arriba
    
    // Establecer título
    const titleEl = document.getElementById('guiaModalTitle');
    if (titleEl) {
        titleEl.textContent = isEdit ? '📦 Editar Guía de Remisión' : '📦 Nueva Guía de Remisión';
    }
    
    const formContainer = document.getElementById('guiaForm');
    if (!formContainer) {
        console.error('❌ #guiaForm no encontrado');
        showToast('Error: Formulario de guía no disponible', 'error');
        return;
    }
    
    // Inicializar fechas
    const hoy = isoLima();
    
    // Generar opciones de motivos
    const motivos = ['VENTA', 'COMPRA', 'TRANSFERENCIA ENTRE ALMACENES', 'DEVOLUCIÓN', 'CONSIGNACIÓN', 'OTRO'];
    const motivoOptions = motivos.map(m => 
        `<option value="${m}" ${m === 'VENTA' ? 'selected' : ''}>${m}</option>`
    ).join('');
    
    const modalidadOptions = `
        <option value="PRIVADO" selected>🚛 Transporte Privado</option>
        <option value="PUBLICO">🚚 Transporte Público</option>
    `;
    
    // RENDERIZAR EL FORMULARIO DE GUÍA (sin productos inicialmente)
    formContainer.innerHTML = `
        <!-- FILA 1: REMITENTE Y DESTINATARIO -->
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:8px;">
            <!-- REMITENTE -->
            <div class="ficha-section" style="border:1px solid #E2E8F0; border-radius:8px; background:#FFFFFF; overflow:hidden;">
                <div class="ficha-section-title" style="padding:4px 10px; background:#F8FAFC; border-bottom:1px solid #E2E8F0; color:#2563EB; font-size:11px; font-weight:900; display:flex; justify-content:space-between; align-items:center;">
                    <span><i class="bi bi-building"></i> Remitente (Origen)</span>
                    <small style="color:#64748B; font-weight:700; font-size:8px;s">🔒 Fijo</small>
                </div>
                <div style="padding:6px 10px;">
                    <div style="display:grid; grid-template-columns:1fr 1fr; gap:4px; margin-bottom:2px;">
                        <div class="form-field">
                            <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">RUC</label>
                            <input id="guiaRucRemitente" value="${ORIGEN_FIJO.ruc}" readonly style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; background:#F1F5F9; font-size:9px; padding:0 6px; color:#64748B; cursor:not-allowed;">
                        </div>
                        <div class="form-field">
                            <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Cód. Anexo</label>
                            <input id="guiaRemitenteAnexo" value="0001" style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; background:#FFFFFF; font-size:9px; padding:0 6px;">
                        </div>
                    </div>
                    <div class="form-field" style="margin-bottom:2px;">
                        <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Razón Social</label>
                        <input id="guiaRemitenteNombre" value="${ORIGEN_FIJO.nombre}" readonly style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; background:#F1F5F9; font-size:9px; padding:0 6px; color:#64748B; cursor:not-allowed;">
                    </div>
                    <div class="form-field" style="margin-bottom:2px;">
                        <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Dirección de Partida</label>
                        <input id="guiaOrigen" value="${ORIGEN_FIJO.direccion}" readonly style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; background:#F1F5F9; font-size:9px; padding:0 6px; color:#64748B; cursor:not-allowed;">
                    </div>
                    <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:4px; margin-top:2px;">
                        <div class="form-field">
                            <label style="font-size:6.5px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Departamento</label>
                            <select id="guiaDeptoOrigen" style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; font-size:8px; padding:0 4px; background:#F1F5F9; cursor:not-allowed;">
                                <option value="${ORIGEN_FIJO.departamento}" selected>${ORIGEN_FIJO.departamento}</option>
                            </select>
                        </div>
                        <div class="form-field">
                            <label style="font-size:6.5px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Provincia</label>
                            <select id="guiaProvOrigen" style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; font-size:8px; padding:0 4px; background:#F1F5F9; cursor:not-allowed;">
                                <option value="${ORIGEN_FIJO.provincia}" selected>${ORIGEN_FIJO.provincia}</option>
                            </select>
                        </div>
                        <div class="form-field">
                            <label style="font-size:6.5px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Distrito</label>
                            <select id="guiaDistOrigen" style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; font-size:8px; padding:0 4px; background:#F1F5F9; cursor:not-allowed;">
                                <option value="${ORIGEN_FIJO.distrito}" selected>${ORIGEN_FIJO.distrito}</option>
                            </select>
                        </div>
                    </div>
                    <div style="font-size:7px; color:#64748B; margin-top:2px;">
                        <i class="bi bi-geo-alt-fill" style="color:#2563EB;"></i> Ubigeo: <span id="guiaUbigeoOrigenTexto">${ORIGEN_FIJO.departamento} - ${ORIGEN_FIJO.provincia} - ${ORIGEN_FIJO.distrito}</span>
                        <input type="hidden" id="guiaUbigeoOrigen" value="${ORIGEN_FIJO.ubigeo}">
                    </div>
                </div>
            </div>
            
            <!-- DESTINATARIO -->
            <div class="ficha-section" style="border:1px solid #E2E8F0; border-radius:8px; background:#FFFFFF; overflow:hidden;">
                <div class="ficha-section-title" style="padding:4px 10px; background:#F8FAFC; border-bottom:1px solid #E2E8F0; color:#059669; font-size:11px; font-weight:900; display:flex; justify-content:space-between; align-items:center;">
                    <span><i class="bi bi-people-fill"></i> Destinatario (Cliente)</span>
                    <small style="color:#64748B; font-weight:700; font-size:8px;">Buscar por RUC</small>
                </div>
                <div style="padding:6px 10px;">
                    <div style="display:grid; grid-template-columns:1fr 60px; gap:4px; margin-bottom:2px;">
                        <div class="form-field">
                            <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Buscar Cliente</label>
                            <input id="guiaBuscarCliente" placeholder="Ingresa RUC" maxlength="11" style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; background:#FFFFFF; font-size:9px; padding:0 6px;" onkeydown="if(event.key==='Enter'){buscarClienteParaGuia();}">
                        </div>
                        <button onclick="buscarClienteParaGuia()" style="height:20px; border-radius:4px; font-size:8px; padding:0 6px; background:#2563EB; color:#fff; border:0; font-weight:900; cursor:pointer;">🔍</button>
                    </div>
                    <div style="display:grid; grid-template-columns:1fr 1fr; gap:4px; margin-bottom:2px;">
                        <div class="form-field">
                            <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">RUC</label>
                            <input id="guiaRuc" placeholder="RUC" style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; background:#FFFFFF; font-size:9px; padding:0 6px;">
                        </div>
                        <div class="form-field">
                            <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Cód. Anexo</label>
                            <input id="guiaDestAnexo" placeholder="0001" style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; background:#FFFFFF; font-size:9px; padding:0 6px;">
                        </div>
                    </div>
                    <div class="form-field" style="margin-bottom:2px;">
                        <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Razón Social</label>
                        <input id="guiaCliente" placeholder="Razón social del cliente" style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; background:#FFFFFF; font-size:9px; padding:0 6px;">
                    </div>
                    <div class="form-field" style="margin-bottom:2px;">
                        <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Dirección de Llegada</label>
                        <input id="guiaDestino" placeholder="Dirección del cliente" style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; background:#FFFFFF; font-size:9px; padding:0 6px;">
                    </div>
                    <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:4px; margin-top:2px;">
                        <div class="form-field">
                            <label style="font-size:6.5px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Departamento</label>
                            <select id="guiaDeptoDestino" style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; font-size:8px; padding:0 4px; background:#FFFFFF;">
                                <option value="">Seleccione</option>
                            </select>
                        </div>
                        <div class="form-field">
                            <label style="font-size:6.5px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Provincia</label>
                            <select id="guiaProvDestino" disabled style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; font-size:8px; padding:0 4px; background:#FFFFFF;">
                                <option value="">Primero Departamento</option>
                            </select>
                        </div>
                        <div class="form-field">
                            <label style="font-size:6.5px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Distrito</label>
                            <select id="guiaDistDestino" disabled style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; font-size:8px; padding:0 4px; background:#FFFFFF;">
                                <option value="">Primero Provincia</option>
                            </select>
                        </div>
                    </div>
                    <div style="font-size:7px; color:#64748B; margin-top:2px;">
                        <i class="bi bi-geo-alt-fill" style="color:#2563EB;"></i> Ubigeo: <span id="guiaUbigeoDestinoTexto">Ninguno</span>
                        <input type="hidden" id="guiaUbigeoDestino" value="">
                    </div>
                    <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:4px; margin-top:4px;">
                        <div class="form-field">
                            <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Orden Compra</label>
                            <input id="guiaOrdenCompra" placeholder="OC-04705" style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; background:#FFFFFF; font-size:8px; padding:0 6px;">
                        </div>
                        <div class="form-field">
                            <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Cotización</label>
                            <input id="guiaCotizacion" placeholder="COT-2026-0001" style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; background:#FFFFFF; font-size:8px; padding:0 6px;">
                        </div>
                        <div class="form-field">
                            <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Factura</label>
                            <input id="guiaFactura" placeholder="F001-123" style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; background:#FFFFFF; font-size:8px; padding:0 6px;">
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- FILA 2: VEHÍCULO Y TRANSPORTISTA -->
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:8px;">
            <div class="ficha-section" style="border:1px solid #E2E8F0; border-radius:8px; background:#FFFFFF; overflow:hidden;">
                <div class="ficha-section-title" style="padding:4px 10px; background:#F8FAFC; border-bottom:1px solid #E2E8F0; color:#EA580C; font-size:11px; font-weight:900; display:flex; justify-content:space-between; align-items:center;">
                    <span><i class="bi bi-truck"></i> Datos de Transporte</span>
                    <small style="color:#64748B; font-weight:700; font-size:8px;">Obligatorio</small>
                </div>
                <div style="padding:6px 10px;">
                    <div style="display:grid; grid-template-columns:1fr 1fr; gap:4px; margin-bottom:2px;">
                        <div class="form-field">
                            <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Modalidad</label>
                            <select id="guiaModalidadTransporte" style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; font-size:9px; padding:0 4px; background:#FFFFFF;" onchange="toggleTransportistaGuia()">
                                ${modalidadOptions}
                            </select>
                        </div>
                        <div class="form-field">
                            <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Seleccionar Conductor</label>
                            <div style="display:flex; gap:4px; align-items:center;">
                                <select id="guiaSelectConductor" style="flex:1; height:20px; border:1px solid #E5E7EB; border-radius:4px; font-size:8px; padding:0 4px; background:#FFFFFF;" onchange="cargarConductorGuia(this.value)">
                                    <option value="">-- Seleccione --</option>
                                    <option value="personalizar" style="font-weight:600;color:#2563EB;">✏️ Personalizar</option>
                                </select>
                                <button onclick="limpiarConductorGuia()" style="height:20px; border-radius:4px; font-size:8px; padding:0 6px; background:#EF4444; color:#fff; border:0; font-weight:900; cursor:pointer; white-space:nowrap;" title="Limpiar campos del conductor">✕</button>
                                <button onclick="openNuevoConductorGuia()" style="height:20px; border-radius:4px; font-size:8px; padding:0 8px; background:#2563EB; color:#fff; border:0; font-weight:900; cursor:pointer; white-space:nowrap;">➕ Nuevo</button>
                            </div>
                        </div>
                    </div>
                    <div style="display:grid; grid-template-columns:1fr 1fr 1fr 1fr; gap:4px; margin-bottom:2px;">
                        <div class="form-field">
                            <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Placa</label>
                            <input id="guiaPlaca" placeholder="ABC-123" style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; background:#FFFFFF; font-size:9px; padding:0 6px; text-transform:uppercase;">
                        </div>
                        <div class="form-field">
                            <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Licencia</label>
                            <input id="guiaLicencia" placeholder="1234567890" style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; background:#FFFFFF; font-size:9px; padding:0 6px;">
                        </div>
                        <div class="form-field">
                            <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">DNI Conductor</label>
                            <input id="guiaConductorDNI" placeholder="DNI" style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; background:#FFFFFF; font-size:9px; padding:0 6px;">
                        </div>
                        <div class="form-field">
                            <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Nombre Conductor</label>
                            <input id="guiaConductorNombre" placeholder="Nombre completo" style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; background:#FFFFFF; font-size:9px; padding:0 6px;">
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="ficha-section" id="guiaTransportistaCard" style="border:1px solid #E2E8F0; border-radius:8px; background:#FFFFFF; overflow:hidden; opacity:0.5;">
                <div class="ficha-section-title" style="padding:4px 10px; background:#F8FAFC; border-bottom:1px solid #E2E8F0; color:#DC2626; font-size:11px; font-weight:900; display:flex; justify-content:space-between; align-items:center;">
                    <span><i class="bi bi-building"></i> Datos del Transportista (Público)</span>
                    <small style="color:#64748B; font-weight:700; font-size:8px;">Solo para Público</small>
                </div>
                <div style="padding:6px 10px;">
                    <div style="display:grid; grid-template-columns:1fr 60px; gap:4px; margin-bottom:2px;">
                        <div class="form-field">
                            <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">RUC Transportista</label>
                            <input id="guiaTransportistaRUC" placeholder="RUC empresa" style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; background:#FFFFFF; font-size:9px; padding:0 6px;">
                        </div>
                        <button onclick="buscarTransportistaGuia()" style="height:20px; border-radius:4px; font-size:8px; padding:0 6px; background:#2563EB; color:#fff; border:0; font-weight:900; cursor:pointer;">🔍</button>
                    </div>
                    <div class="form-field" style="margin-bottom:2px;">
                        <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Razón Social</label>
                        <input id="guiaTransportistaNombre" readonly style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; background:#F1F5F9; font-size:9px; padding:0 6px; color:#64748B; cursor:not-allowed;">
                    </div>
                    <div class="form-field">
                        <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Dirección</label>
                        <input id="guiaTransportistaDireccion" placeholder="Dirección del transportista" style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; background:#FFFFFF; font-size:9px; padding:0 6px;">
                    </div>
                    <div id="guiaMsgTransportePrivado" style="display:none; margin-top:4px; padding:4px 8px; background:#FFF7ED; border:1px solid #FDBA74; border-radius:4px; font-size:8px; color:#9A3412;">
                        <i class="bi bi-info-circle"></i> En transporte privado no se requiere transportista.
                    </div>
                </div>
            </div>
        </div>
        
        <!-- FILA 3: TRASLADO -->
        <div class="ficha-section" style="border:1px solid #E2E8F0; border-radius:8px; background:#FFFFFF; overflow:hidden; margin-bottom:8px;">
            <div class="ficha-section-title" style="padding:4px 10px; background:#F8FAFC; border-bottom:1px solid #E2E8F0; color:#7C3AED; font-size:11px; font-weight:900; display:flex; justify-content:space-between; align-items:center;">
                <span><i class="bi bi-file-text"></i> Datos del Traslado</span>
                <small style="color:#64748B; font-weight:700; font-size:8px;">Campos SUNAT</small>
            </div>
            <div style="padding:6px 10px;">
                <div style="display:grid; grid-template-columns:1fr 1fr 1fr 1fr; gap:4px; margin-bottom:2px;">
                    <div class="form-field">
                        <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Motivo</label>
                        <select id="guiaMotivo" style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; font-size:8px; padding:0 4px; background:#FFFFFF;">
                            ${motivoOptions}
                        </select>
                    </div>
                    <div class="form-field">
                        <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Fecha Emisión</label>
                        <input id="guiaFechaEmision" type="date" value="${hoy}" style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; background:#FFFFFF; font-size:9px; padding:0 6px;">
                    </div>
                    <div class="form-field">
                        <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Fecha Inicio</label>
                        <input id="guiaFechaInicio" type="date" value="${hoy}" style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; background:#FFFFFF; font-size:9px; padding:0 6px;">
                    </div>
                    <div class="form-field">
                        <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">N° Bultos</label>
                        <input id="guiaBultos" type="number" value="1" min="0" style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; background:#FFFFFF; font-size:9px; padding:0 6px;">
                    </div>
                </div>
                
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:4px; margin-top:2px;">
                    <div class="form-field">
                        <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Unidad Peso Bruto</label>
                        <select id="guiaUnidadPeso" style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; font-size:8px; padding:0 4px; background:#FFFFFF;">
                            <option value="">Cargando...</option>
                        </select>
                    </div>
                    <div class="form-field">
                        <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Peso Bruto Total</label>
                        <input id="guiaPeso" type="number" step="0.01" value="0.00" style="width:100%; height:20px; border:1px solid #E5E7EB; border-radius:4px; background:#FFFFFF; font-size:9px; padding:0 6px;">
                    </div>
                </div>
                
                <div class="form-field" style="margin-top:4px;">
                    <label style="font-size:7px; font-weight:900; color:#334155; display:block; margin-bottom:1px; text-transform:uppercase;">Observaciones</label>
                    <textarea id="guiaObservaciones" rows="1" placeholder="Notas adicionales..." style="width:100%; border:1px solid #E5E7EB; border-radius:4px; background:#FFFFFF; font-size:9px; padding:4px 6px; resize:vertical; min-height:24px;"></textarea>
                </div>
            </div>
        </div>
        
        <!-- ✅ SECCIÓN DE PRODUCTOS - SOLO GUÍA -->
        <div class="ficha-section" style="border:1px solid #E2E8F0; border-radius:8px; background:#FFFFFF; overflow:hidden; margin-bottom:8px;">
            <div class="ficha-section-title" style="padding:4px 10px; background:#F8FAFC; border-bottom:1px solid #E2E8F0; color:#059669; font-size:11px; font-weight:900; display:flex; justify-content:space-between; align-items:center;">
                <span><i class="bi bi-box-seam"></i> Productos</span>
                <div style="display:flex; gap:4px; align-items:center;">
                    <button onclick="openProductSelectorGuia()" style="height:20px; padding:0 10px; font-size:8px; border-radius:4px; background:#8B5CF6; color:#fff; border:0; font-weight:800; cursor:pointer;">📋 Agregar productos</button>
                    <button onclick="agregarFilaProductoGuia()" style="height:20px; padding:0 8px; font-size:8px; border-radius:4px; background:#2563EB; color:#fff; border:0; font-weight:800; cursor:pointer;">+ Agregar fila</button>
                </div>
            </div>
            <div style="overflow-x:auto; padding:4px 6px;">
                <table style="width:100%; border-collapse:collapse; font-size:9px; min-width:650px;">
                    <thead>
                        <tr>
                            <th style="padding:2px 4px; background:#FFF1F2; color:#7F1D1D; border:1px solid #FCA5A5; text-align:center; width:35px;">#</th>
                            <th style="padding:2px 4px; background:#FFF1F2; color:#7F1D1D; border:1px solid #FCA5A5; text-align:center; width:80px;">Código de producto</th>
                            <th style="padding:2px 4px; background:#FFF1F2; color:#7F1D1D; border:1px solid #FCA5A5; text-align:center;">Descripción</th>
                            <th style="padding:2px 4px; background:#FFF1F2; color:#7F1D1D; border:1px solid #FCA5A5; text-align:center; width:70px;">Unidad</th>
                            <th style="padding:2px 4px; background:#FFF1F2; color:#7F1D1D; border:1px solid #FCA5A5; text-align:center; width:60px;">Cantidad</th>
                            <th style="padding:2px 4px; background:#FFF1F2; color:#7F1D1D; border:1px solid #FCA5A5; text-align:center; width:70px;">Peso U.</th>
                            <th style="padding:2px 4px; background:#FFF1F2; color:#7F1D1D; border:1px solid #FCA5A5; text-align:center; width:35px;" title="Eliminar">🗑️</th>
                        </tr>
                    </thead>
                    <tbody id="guiaProductosBody">
                        <!-- Productos se agregan aquí -->
                    </tbody>
                </table>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center; padding:4px 10px; background:#F8FAFC; border-top:1px solid #E2E8F0; font-size:9px; font-weight:800; color:#475569;">
                <span id="guiaProductosCount">0 productos</span>
                <span>Peso total: <span id="guiaPesoTotalDisplay">0.00</span> kg</span>
            </div>
        </div>
    `;
    
    // ============================================================
    // CONFIGURAR UBIGEOS DE DESTINO
    // ============================================================
    llenarDepartamentosGuia('guiaDeptoDestino');
    configurarUbigeoGuia('Destino');
    
    // Preseleccionar Lima para destino
    setTimeout(() => {
        const deptoDestino = document.getElementById('guiaDeptoDestino');
        if (deptoDestino) {
            deptoDestino.value = 'LIMA';
            deptoDestino.dispatchEvent(new Event('change'));
            setTimeout(() => {
                const provDestino = document.getElementById('guiaProvDestino');
                if (provDestino) {
                    provDestino.value = 'LIMA';
                    provDestino.dispatchEvent(new Event('change'));
                    setTimeout(() => {
                        const distDestino = document.getElementById('guiaDistDestino');
                        if (distDestino) {
                            distDestino.value = 'SAN MARTIN DE PORRES';
                            distDestino.dispatchEvent(new Event('change'));
                        }
                    }, 50);
                }
            }, 50);
        }
    }, 100);
    
    // ============================================================
    // CARGAR UNIDADES DE MEDIDA
    // ============================================================
    cargarUnidadesDeMedidaGuia();
    
    // ============================================================
    // CARGAR CONDUCTORES
    // ============================================================
    cargarConductoresGuia();
    toggleTransportistaGuia();
    
    // ============================================================
    // AGREGAR FILA DE PRODUCTO
    // ============================================================
    agregarFilaProductoGuia();
    
    // ============================================================
    // MOSTRAR MODAL - SOLO GUÍA
    // ============================================================
    modal.classList.add('show');
    modal.style.cssText = `
        position: fixed !important;
        inset: 0 !important;
        z-index: 99999 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        background: rgba(15, 23, 42, 0.7) !important;
        backdrop-filter: blur(6px) !important;
        visibility: visible !important;
        opacity: 1 !important;
        padding: 20px !important;
        overflow: auto !important;
    `;
    
    const box = modal.querySelector('.modal-box');
    if (box) {
        box.style.cssText = `
            position: relative !important;
            z-index: 99999 !important;
            width: min(1400px, 98vw) !important;
            max-height: 95vh !important;
            background: #FFFFFF !important;
            border-radius: 16px !important;
            overflow: hidden !important;
            box-shadow: 0 30px 80px rgba(15,23,42,.35) !important;
            display: flex !important;
            flex-direction: column !important;
            animation: modalIn 0.3s ease-out !important;
        `;
    }


    const footer = document.getElementById('guiaModalFooter');
if (footer) {
    footer.style.display = 'flex !important';
    footer.style.visibility = 'visible !important';
    footer.style.opacity = '1 !important';
}
    
    else {
        console.error('❌ #guiaModalFooter no encontrado en el DOM');
    }
    
    
    if (isEdit) {
        setTimeout(() => cargarGuiaParaEditar(id), 300);
    }
    
    console.log('✅ Modal de guía abierto correctamente');
}

// ============================================================
// CERRAR MENÚS AL HACER CLIC EN CUALQUIER PARTE DE LA PANTALLA
// ============================================================

(function() {
    'use strict';
    
    // Cerrar todos los menús al hacer clic en cualquier parte
    document.addEventListener('click', function(e) {
        // Si el clic fue en un botón kebab, NO cerrar (el menú se abrirá)
        if (e.target.closest('.kebab')) {
            return;
        }
        
        // Si el clic fue dentro de un menú, NO cerrar
        if (e.target.closest('.menu-pop')) {
            return;
        }
        
        // Cerrar todos los menús
        document.querySelectorAll('.menu-pop').forEach(el => {
            el.remove();
        });
    });
    
    // También cerrar con Escape
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            document.querySelectorAll('.menu-pop').forEach(el => {
                el.remove();
            });
        }
    });
    
    // También cerrar al hacer scroll
    document.addEventListener('scroll', function() {
        document.querySelectorAll('.menu-pop').forEach(el => {
            el.remove();
        });
    });
    
    console.log('✅ Evento global para cerrar menús activado');
})();

// ============================================================
// CARGAR GUÍA EXISTENTE PARA EDICIÓN
// ============================================================
async function cargarGuiaParaEditar(id) {
    try {
        console.log('📥 Cargando guía para editar ID:', id);
        showToast('⏳ Cargando datos de la guía...', 'info');

        const response = await apiFetch(`/ventas/api/guias/${id}`);
        if (!response.success) {
            showToast('Error al cargar guía: ' + (response.error || 'Desconocido'), 'error');
            return;
        }

        const g = response.data;
        console.log('📦 Datos de guía cargados:', g);

        // ============================================================
        // ORIGEN FIJO - SIEMPRE SOBREESCRIBIR
        // ============================================================
        const ORIGEN_FIJO = {
            ruc: '20602095704',
            nombre: 'KCF CORPORACION E.I.R.L',
            direccion: 'JR. LAS ALMENDRAS VERDES NRO. 284 URB. VIRGEN DEL ROSARIO LIMA - LIMA - SAN MARTIN DE PORRES',
            ubigeo: '150139',
            departamento: 'LIMA',
            provincia: 'LIMA',
            distrito: 'SAN MARTIN DE PORRES'
        };
        aplicarEmpresaAlOrigen(ORIGEN_FIJO);   // multiempresa: remitente = empresa elegida arriba

        // ============================================================
        // 🔒 setSelectValue BLINDADO
        // Funciona tanto para <select> como para <input>.
        // Si el elemento no es <select>, actúa como setValue.
        // ============================================================
        const setSelectValue = (id, value) => {
            const el = document.getElementById(id);
            if (!el || value === undefined || value === null) return;

            // Si no es un <select>, tratarlo como input normal
            if (el.tagName !== 'SELECT') {
                el.value = value;
                return;
            }

            const val = String(value).trim();
            let found = false;
            for (const opt of el.options) {
                if (opt.value === val) { opt.selected = true; found = true; break; }
            }
            if (!found) {
                for (const opt of el.options) {
                    if (opt.value.toLowerCase() === val.toLowerCase()) { opt.selected = true; found = true; break; }
                }
            }
        };

        const setValue = (id, value) => {
            const el = document.getElementById(id);
            if (el) el.value = value ?? '';
        };

        // ============================================================
        // CAMPOS BÁSICOS
        // ============================================================
        setValue('guiaSerie', g.serie);
        setValue('guiaNumero', g.numero);
        setSelectValue('guiaEstado', g.estado_sunat || g.estado);
        setValue('guiaCliente', g.destinatario_nombre);
        setValue('guiaRuc', g.ruc_destinatario);
        setSelectValue('guiaOrigen', ORIGEN_FIJO.direccion);
        setValue('guiaDestino', g.destinatario_direccion);
        setSelectValue('guiaMotivo', g.motivo_traslado);

        // ---- OBSERVACIONES (id correcto: guiaObservaciones, no guiaObs) ----
        setValue('guiaObservaciones', g.observaciones);

        // ---- MODALIDAD DE TRANSPORTE (activa/desactiva el bloque transportista) ----
        setSelectValue('guiaModalidadTransporte', g.modalidad_transporte || 'PRIVADO');
        if (typeof toggleTransportistaGuia === 'function') {
            setTimeout(() => toggleTransportistaGuia(), 50);
        }

        // ---- VEHÍCULO Y CONDUCTOR ----
        setValue('guiaPlaca', g.placa_vehiculo);
        setValue('guiaConductorDNI', g.conductor_dni);
        setValue('guiaConductorNombre', g.conductor_nombre);
        setValue('guiaLicencia', g.licencia_conductor);

        // ---- TRANSPORTISTA (solo aplica si modalidad = PUBLICO) ----
        setValue('guiaTransportistaRUC', g.transportista_ruc);
        setValue('guiaTransportistaNombre', g.transportista_nombre);
        setValue('guiaTransportistaDireccion', g.transportista_direccion);

        // ---- FECHAS ----
        // Los inputs son type="date", así que hay que recortar a YYYY-MM-DD
        const normalizarFecha = (valor) => {
            if (!valor) return '';
            const s = String(valor);
            return s.slice(0, 10);
        };
        setValue('guiaFechaEmision', normalizarFecha(g.fecha_emision));
        setValue('guiaFechaInicio', normalizarFecha(g.fecha_traslado));

        // ---- PESO Y BULTOS ----
        setValue('guiaPeso', g.peso_total);
        setValue('guiaBultos', g.numero_bultos || 1);
        setSelectValue('guiaUnidadPeso', g.unidad_peso_bruto || 'KGM');

        // ---- DOCUMENTOS ADICIONALES ----
        setValue('guiaOrdenCompra', g.orden_compra_cliente);
        setValue('guiaFactura', g.factura);

        // ---- DESTINATARIO: UBIGEO (departamento/provincia/distrito) ----
        // Se llenan dinámicamente, así que hay que esperar a que las opciones existan.
        if (g.destinatario_departamento) {
            setTimeout(() => {
                const deptoSel = document.getElementById('guiaDeptoDestino');
                if (deptoSel) {
                    deptoSel.value = g.destinatario_departamento;
                    deptoSel.dispatchEvent(new Event('change'));
                    setTimeout(() => {
                        const provSel = document.getElementById('guiaProvDestino');
                        if (provSel && g.destinatario_provincia) {
                            provSel.value = g.destinatario_provincia;
                            provSel.dispatchEvent(new Event('change'));
                            setTimeout(() => {
                                const distSel = document.getElementById('guiaDistDestino');
                                if (distSel && g.destinatario_distrito) {
                                    distSel.value = g.destinatario_distrito;
                                    distSel.dispatchEvent(new Event('change'));
                                }
                            }, 80);
                        }
                    }, 80);
                }
            }, 150);
        }

        // ============================================================
        // SOBREESCRIBIR ORIGEN CON DATOS FIJOS
        // ============================================================
        const origenInput = document.getElementById('guiaOrigen');
        if (origenInput) {
            origenInput.value = ORIGEN_FIJO.direccion;
            origenInput.readOnly = true;
            origenInput.style.background = '#F1F5F9';
            origenInput.style.color = '#64748B';
            origenInput.style.cursor = 'not-allowed';
        }

        const rucRemitente = document.getElementById('guiaRucRemitente');
        if (rucRemitente) {
            rucRemitente.value = ORIGEN_FIJO.ruc;
            rucRemitente.readOnly = true;
            rucRemitente.style.background = '#F1F5F9';
            rucRemitente.style.color = '#64748B';
        }

        const nombreRemitente = document.getElementById('guiaRemitenteNombre');
        if (nombreRemitente) {
            nombreRemitente.value = ORIGEN_FIJO.nombre;
            nombreRemitente.readOnly = true;
            nombreRemitente.style.background = '#F1F5F9';
            nombreRemitente.style.color = '#64748B';
        }

        const deptoOrigen = document.getElementById('guiaDeptoOrigen');
        if (deptoOrigen) {
            deptoOrigen.value = ORIGEN_FIJO.departamento;
            deptoOrigen.disabled = true;
            deptoOrigen.style.background = '#F1F5F9';
            deptoOrigen.style.cursor = 'not-allowed';
        }

        const provOrigen = document.getElementById('guiaProvOrigen');
        if (provOrigen) {
            provOrigen.value = ORIGEN_FIJO.provincia;
            provOrigen.disabled = true;
            provOrigen.style.background = '#F1F5F9';
            provOrigen.style.cursor = 'not-allowed';
        }

        const distOrigen = document.getElementById('guiaDistOrigen');
        if (distOrigen) {
            distOrigen.value = ORIGEN_FIJO.distrito;
            distOrigen.disabled = true;
            distOrigen.style.background = '#F1F5F9';
            distOrigen.style.cursor = 'not-allowed';
        }

        const ubigeoHidden = document.getElementById('guiaUbigeoOrigen');
        if (ubigeoHidden) {
            ubigeoHidden.value = ORIGEN_FIJO.ubigeo;
        }

        const ubigeoTexto = document.getElementById('guiaUbigeoOrigenTexto');
        if (ubigeoTexto) {
            ubigeoTexto.textContent = `${ORIGEN_FIJO.departamento} - ${ORIGEN_FIJO.provincia} - ${ORIGEN_FIJO.distrito}`;
        }

        // Cotización vinculada
        if (g.documento_asociado) {
            setSelectValue('guiaCotizacion', g.documento_asociado);
        }

        // ============================================================
        // 🔽 PRODUCTOS (items_json) -> pintar filas EDITABLES reales
        //     La tabla real es #guiaProductosBody (no existe #guiaProducts)
        // ============================================================
        let items = [];
        try {
            if (g.items_json) {
                items = typeof g.items_json === 'string' ? JSON.parse(g.items_json) : g.items_json;
            }
        } catch (e) {
            console.warn('⚠️ Error parseando items_json de la guía:', e);
            items = [];
        }

        const tbody = document.getElementById('guiaProductosBody');
        if (tbody) {
            tbody.innerHTML = ''; // limpiar la fila vacía inicial que agrega openGuiaModal

            (items || []).forEach(it => {
                agregarFilaProductoGuia(); // crea la fila con los inputs reales
                const lastRow = tbody.lastElementChild;
                if (lastRow) {
                    const codigoInput = lastRow.querySelector('.guia-producto-codigo');
                    const descInput   = lastRow.querySelector('.guia-producto-desc');
                    const unidadSel   = lastRow.querySelector('.guia-producto-unidad');
                    const cantInput   = lastRow.querySelector('.guia-producto-cant');
                    const pesoInput   = lastRow.querySelector('.guia-producto-peso');

                    if (codigoInput) codigoInput.value = it.codigo || '';
                    if (descInput)   descInput.value   = it.producto || it.descripcion || '';
                    if (unidadSel)   unidadSel.value   = it.um || 'NIU';
                    if (cantInput)   cantInput.value   = it.cantidad || 1;
                    if (pesoInput)   pesoInput.value   = it.peso_unitario || 0.50;
                }
            });

            if (!items || items.length === 0) {
                // si la guía no tenía productos, dejar al menos una fila vacía
                agregarFilaProductoGuia();
            }

            actualizarPesoTotalGuia();
            actualizarContadorProductosGuia();
        }

        window._guiaProductos = items;

        showToast('✅ Guía cargada correctamente', 'success');

    } catch (error) {
        console.error('❌ Error cargando guía para editar:', error);
        showToast('Error al cargar la guía: ' + error.message, 'error');
    }
}


/**
 * Carga los productos de una cotización en el comprobante
 */
async function cargarProductosComprobanteDesdeCotizacion(numeroCotizacion) {
    if (!numeroCotizacion) {
        document.getElementById('compProducts').innerHTML = `
            <div style="padding:20px;text-align:center;color:#94A3B8;">
                Seleccione una cotización para ver los productos.
            </div>
        `;
        return;
    }
    
    console.log('🔄 Cargando productos de cotización:', numeroCotizacion);
    showToast('⏳ Cargando productos...', 'info');
    
    try {
        // Buscar la cotización en los datos cargados
        const cotizacion = cotizacionesData.find(c => c.numero === numeroCotizacion);
        if (!cotizacion) {
            showToast('⚠️ Cotización no encontrada', 'warning');
            return;
        }
        
        // Cargar datos completos de la cotización (con productos)
        const response = await apiFetch(`/ventas/api/cotizaciones/${cotizacion.id}/completa`);
        if (!response.success) {
            showToast('❌ Error al cargar productos: ' + (response.error || 'Desconocido'), 'error');
            return;
        }
        
        const data = preciosNetosCotizacion(response.data);
        const productos = data.productos || [];
        
        console.log(`📦 ${productos.length} productos encontrados`);
        
        // Actualizar cliente y RUC automáticamente
        document.getElementById('compCliente').value = data.cliente_razon_social || '';
        document.getElementById('compRuc').value = data.cliente_ruc || '';
        document.getElementById('compEmail').value = data.cliente_email || data.email_cliente || data.email || '';
        document.getElementById('compTelefono').value = data.cliente_telefono || data.telefono_cliente || data.telefono || '';
        document.getElementById('compDireccion').value = data.cliente_direccion || data.direccion_entrega || data.direccion || data.cliente_direccion_entrega || '';
        
        // Calcular monto total
        const total = productos.reduce((sum, p) => sum + (Number(p.cantidad || 0) * Number(p.valorVenta || 0) * 1.18), 0);
        document.getElementById('compMonto').value = total.toFixed(2);
        
        // Renderizar productos
        if (productos.length === 0) {
            document.getElementById('compProducts').innerHTML = `
                <div style="padding:20px;text-align:center;color:#94A3B8;">
                    📭 Esta cotización no tiene productos.
                </div>
            `;
            showToast('⚠️ Esta cotización no tiene productos', 'warning');
            return;
        }
        
        // Guardar productos en variable global
        window._compProductos = productos;
        
        // Renderizar tabla de productos
        document.getElementById('compProducts').innerHTML = `
            <div class="table-scroll">
                <table class="master-table" style="font-size:11px;">
                    <thead>
                        <tr>
                            <th>Item</th>
                            <th>Código de producto</th>
                            <th>Nombre producto</th>
                            <th>Marca</th>
                            <th>Modelo</th>
                            <th>Unidad</th>
                            <th>Cant.</th>
                            <th>Precio Unit.</th>
                            <th>Total</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${productos.map((p, i) => {
                            const subtotal = Number(p.cantidad || 0) * Number(p.valorVenta || 0);
                            return `
                            <tr>
                                <td>${i + 1}</td>
                                <td>${p.codigo || '-'}</td>
                                <td class="left">${p.producto || p.descripcion || 'Sin nombre'}</td>
                                <td>${p.marca || '-'}</td>
                                <td>${p.modelo || '-'}</td>
                                <td>${p.um || 'NIU'}</td>
                                <td>${p.cantidad || 1}</td>
                                <td>S/ ${Number(p.valorVenta || 0).toFixed(2)}</td>
                                <td style="font-weight:900; color:#059669;">S/ ${subtotal.toFixed(2)}</td>
                            </tr>
                            `;
                        }).join('')}
                    </tbody>
                    <tfoot>
                        <tr>
                            <td colspan="7" style="text-align:right; font-weight:900; background:#F8FAFC;">TOTAL</td>
                            <td colspan="2" style="font-weight:900; font-size:14px; color:#EF233C; background:#FFF1F2;">
                                S/ ${total.toFixed(2)}
                            </td>
                        </tr>
                    </tfoot>
                </table>
            </div>
        `;
        
        // Actualizar observaciones
        actualizarObservacionesComprobante();
        
        showToast(`✅ ${productos.length} productos cargados desde ${data.numero_cotizacion}`, 'success');
        
    } catch (error) {
        console.error('❌ Error cargando productos:', error);
        showToast('❌ Error al cargar productos: ' + error.message, 'error');
    }
}

/**
 * Carga datos desde una guía seleccionada
 */
window.loadComprobanteFromGuia = function(valorSeleccionado) {
    if (!valorSeleccionado) {
        actualizarObservacionesComprobante();
        return;
    }

    const guia = guiasData.find(g => `${g.serie}-${g.numero}` === valorSeleccionado);
    if (!guia) {
        showToast('⚠️ Guía no encontrada', 'warning');
        return;
    }

    console.log('📦 Cargando guía:', guia);

    // Autocompletar cliente/RUC
    const compCliente = document.getElementById('compCliente');
    const compRuc = document.getElementById('compRuc');
    if (compCliente && !compCliente.value.trim()) compCliente.value = guia.cliente || '';
    if (compRuc && !compRuc.value.trim()) compRuc.value = guia.ruc || '';

    // 🔽 CARGAR PRODUCTOS DE LA GUÍA 🔽
    let productos = [];
    
    // Intentar obtener items de la guía
    if (guia.items && guia.items.length > 0) {
        productos = guia.items.map(item => {
            // Normalizar item (puede ser objeto o array)
            if (typeof item === 'object' && !Array.isArray(item)) {
                return {
                    codigo: item.codigo || '',
                    producto: item.producto || item.descripcion || 'Sin nombre',
                    marca: item.marca || '',
                    modelo: item.modelo || '',
                    um: item.um || 'NIU',
                    cantidad: item.cantidad || 1,
                    valorVenta: item.valorVenta || item.precio || 0
                };
            }
            if (Array.isArray(item)) {
                return {
                    codigo: item[0] || '',
                    producto: item[1] || 'Sin nombre',
                    marca: item[2] || '',
                    modelo: item[3] || '',
                    um: 'NIU',
                    cantidad: item[4] || 1,
                    valorVenta: item[5] || 0
                };
            }
            return null;
        }).filter(p => p !== null);
    }
    
    // Si no hay items en la guía, intentar buscar en items_json
    if (productos.length === 0 && guia.items_json) {
        try {
            const itemsJson = typeof guia.items_json === 'string' ? JSON.parse(guia.items_json) : guia.items_json;
            if (Array.isArray(itemsJson) && itemsJson.length > 0) {
                productos = itemsJson.map(item => {
                    if (typeof item === 'object' && !Array.isArray(item)) {
                        return {
                            codigo: item.codigo || '',
                            producto: item.producto || item.descripcion || 'Sin nombre',
                            marca: item.marca || '',
                            modelo: item.modelo || '',
                            um: item.um || 'NIU',
                            cantidad: item.cantidad || 1,
                            valorVenta: item.valorVenta || item.precio || 0
                        };
                    }
                    if (Array.isArray(item)) {
                        return {
                            codigo: item[0] || '',
                            producto: item[1] || 'Sin nombre',
                            marca: item[2] || '',
                            modelo: item[3] || '',
                            um: 'NIU',
                            cantidad: item[4] || 1,
                            valorVenta: item[5] || 0
                        };
                    }
                    return null;
                }).filter(p => p !== null);
            }
        } catch (e) {
            console.warn('⚠️ Error parseando items_json:', e);
        }
    }

    // Si hay productos, mostrarlos
    if (productos.length > 0) {
        window._compProductos = productos;
        renderProductosComprobante(productos);
        
        // Actualizar monto total
        const total = productos.reduce((sum, p) => sum + (Number(p.cantidad || 0) * Number(p.valorVenta || 0) * 1.18), 0);
        document.getElementById('compMonto').value = total.toFixed(2);
        
        showToast(`✅ ${productos.length} productos cargados desde guía`, 'success');
    } else {
        // Si no hay productos, mostrar mensaje
        document.getElementById('compProducts').innerHTML = `
            <div style="padding:20px;text-align:center;color:#94A3B8;">
                📭 Esta guía no tiene productos asociados.
            </div>
        `;
        showToast('⚠️ Esta guía no tiene productos', 'warning');
    }

    actualizarObservacionesComprobante();
    showToast(`✅ Guía ${guia.serie}-${guia.numero} vinculada`, 'success');
};

/**
 * Carga datos desde un PC seleccionado
 */
window.loadComprobanteFromPC = function(numeroPC) {
    if (!numeroPC) {
        actualizarObservacionesComprobante();
        return;
    }

    const pc = pedidosData.find(p => p.numero === numeroPC);
    if (!pc) {
        showToast('⚠️ PC no encontrado', 'warning');
        return;
    }

    console.log('📦 Cargando PC:', pc);

    // Autocompletar cliente/RUC
    const compCliente = document.getElementById('compCliente');
    const compRuc = document.getElementById('compRuc');
    if (compCliente && !compCliente.value.trim()) compCliente.value = pc.cliente || '';
    if (compRuc && !compRuc.value.trim()) compRuc.value = pc.ruc || '';

    // 🔽 CARGAR PRODUCTOS DEL PC 🔽
    let productos = [];
    
    // Intentar obtener items del PC
    if (pc.items && pc.items.length > 0) {
        productos = pc.items.map(item => {
            // Normalizar item (puede ser objeto o array)
            if (typeof item === 'object' && !Array.isArray(item)) {
                return {
                    codigo: item.codigo || '',
                    producto: item.producto || item.descripcion || 'Sin nombre',
                    marca: item.marca || '',
                    modelo: item.modelo || '',
                    um: item.um || 'NIU',
                    cantidad: item.cantidad_pc || item.cantidad || 1,
                    valorVenta: item.precio_pc || item.precio || 0
                };
            }
            if (Array.isArray(item)) {
                return {
                    codigo: item[0] || '',
                    producto: item[1] || 'Sin nombre',
                    marca: item[2] || '',
                    modelo: item[3] || '',
                    um: 'NIU',
                    cantidad: item[5] || 1,
                    valorVenta: item[7] || 0
                };
            }
            return null;
        }).filter(p => p !== null);
    }
    
    // Si no hay items, intentar buscar en items_json
    if (productos.length === 0 && pc.items_json) {
        try {
            const itemsJson = typeof pc.items_json === 'string' ? JSON.parse(pc.items_json) : pc.items_json;
            if (Array.isArray(itemsJson) && itemsJson.length > 0) {
                productos = itemsJson.map(item => {
                    if (typeof item === 'object' && !Array.isArray(item)) {
                        return {
                            codigo: item.codigo || '',
                            producto: item.producto || item.descripcion || 'Sin nombre',
                            marca: item.marca || '',
                            modelo: item.modelo || '',
                            um: item.um || 'NIU',
                            cantidad: item.cantidad_pc || item.cantidad || 1,
                            valorVenta: item.precio_pc || item.precio || 0
                        };
                    }
                    if (Array.isArray(item)) {
                        return {
                            codigo: item[0] || '',
                            producto: item[1] || 'Sin nombre',
                            marca: item[2] || '',
                            modelo: item[3] || '',
                            um: 'NIU',
                            cantidad: item[5] || 1,
                            valorVenta: item[7] || 0
                        };
                    }
                    return null;
                }).filter(p => p !== null);
            }
        } catch (e) {
            console.warn('⚠️ Error parseando items_json:', e);
        }
    }

    // Si hay productos, mostrarlos
    if (productos.length > 0) {
        window._compProductos = productos;
        renderProductosComprobante(productos);
        
        // Actualizar monto total
        const total = productos.reduce((sum, p) => sum + (Number(p.cantidad || 0) * Number(p.valorVenta || 0) * 1.18), 0);
        document.getElementById('compMonto').value = total.toFixed(2);
        
        showToast(`✅ ${productos.length} productos cargados desde PC`, 'success');
    } else {
        // Si no hay productos, mostrar mensaje
        document.getElementById('compProducts').innerHTML = `
            <div style="padding:20px;text-align:center;color:#94A3B8;">
                📭 Este PC no tiene productos asociados.
            </div>
        `;
        showToast('⚠️ Este PC no tiene productos', 'warning');
    }

    actualizarObservacionesComprobante();
    showToast(`✅ PC ${pc.numero} vinculado`, 'success');
};

/**
 * Renderiza los productos en el comprobante
 */
function renderProductosComprobante(productos) {
    if (!productos || productos.length === 0) {
        document.getElementById('compProducts').innerHTML = `
            <div style="padding:20px;text-align:center;color:#94A3B8;">
                📭 No hay productos disponibles.
            </div>
        `;
        return;
    }
    
    const total = productos.reduce((sum, p) => sum + (Number(p.cantidad || 0) * Number(p.valorVenta || 0) * 1.18), 0);
    
    document.getElementById('compProducts').innerHTML = `
        <div class="table-scroll">
            <table class="master-table" style="font-size:11px;">
                <thead>
                    <tr>
                        <th>Item</th>
                        <th>Código de producto</th>
                        <th>Nombre producto</th>
                        <th>Marca</th>
                        <th>Modelo</th>
                        <th>Unidad</th>
                        <th>Cant.</th>
                        <th>Precio Unit.</th>
                        <th>Total</th>
                    </tr>
                </thead>
                <tbody>
                    ${productos.map((p, i) => {
                        const subtotal = Number(p.cantidad || 0) * Number(p.valorVenta || 0);
                        return `
                        <tr>
                            <td>${i + 1}</td>
                            <td>${p.codigo || '-'}</td>
                            <td class="left">${p.producto || 'Sin nombre'}</td>
                            <td>${p.marca || '-'}</td>
                            <td>${p.modelo || '-'}</td>
                            <td>${p.um || 'NIU'}</td>
                            <td>${p.cantidad || 1}</td>
                            <td>S/ ${Number(p.valorVenta || 0).toFixed(2)}</td>
                            <td style="font-weight:900; color:#059669;">S/ ${subtotal.toFixed(2)}</td>
                        </tr>
                        `;
                    }).join('')}
                </tbody>
                <tfoot>
                    <tr>
                        <td colspan="7" style="text-align:right; font-weight:900; background:#F8FAFC;">TOTAL</td>
                        <td colspan="2" style="font-weight:900; font-size:14px; color:#EF233C; background:#FFF1F2;">
                            S/ ${total.toFixed(2)}
                        </td>
                    </tr>
                </tfoot>
            </table>
        </div>
    `;
}



async function cargarComprobanteParaEditar(id) {
    try {
        console.log('📥 Cargando comprobante para editar ID:', id);
        showToast('⏳ Cargando datos...', 'info');

        const response = await apiFetch(`/ventas/api/comprobantes/${id}`);
        if (!response.success) {
            showToast('Error al cargar comprobante: ' + (response.error || 'Desconocido'), 'error');
            return;
        }

        const c = response.data;
        console.log('📦 Datos cargados:', c);

        // Función para setear valor en input/select
        const setVal = (id, value) => {
            const el = document.getElementById(id);
            if (el) {
                if (el.tagName === 'SELECT') {
                    // Buscar opción con ese valor
                    for (let opt of el.options) {
                        if (opt.value === value) {
                            opt.selected = true;
                            return;
                        }
                    }
                } else {
                    el.value = value ?? '';
                }
            }
        };

        // Llenar campos
        setVal('compTipo', c.tipo_comprobante);
        setVal('compSerie', c.serie);
        setVal('compNumero', c.numero);
        setVal('compEstado', c.estado_sunat);
        setVal('compCliente', c.cliente_nombre);
        setVal('compRuc', c.cliente_numero_doc);
        setVal('compMonto', c.total);
        setVal('compObs', c.observaciones);
        window.ponerCondicion('compCondicion', c.condicion_pago || 'Contado');
        setVal('compCotizacion', c.documento_asociado);
        setVal('compGuia', c.guia_vinculada);
        setVal('compPC', c.pc_vinculado);

        // Cargar productos
        const items = Array.isArray(c.items_json) ? c.items_json : [];
        const productsContainer = document.getElementById('compProducts');
        if (productsContainer) {
            if (items.length > 0) {
                productsContainer.innerHTML = productTableHtml(items);
            } else {
                productsContainer.innerHTML = `
                    <div style="padding:20px;text-align:center;color:#94A3B8;">
                        No hay productos en este comprobante.
                    </div>
                `;
            }
        }

        window._compProductos = items;
        showToast('✅ Comprobante cargado correctamente', 'success');

    } catch (error) {
        console.error('❌ Error cargando comprobante:', error);
        showToast('Error al cargar el comprobante: ' + error.message, 'error');
    }
}


function openNotaCreditoModal(id = null) {
    editingId = id;
    const isEdit = id !== null;
    const title = isEdit ? 'Editar nota de crédito' : 'Nueva nota de crédito';
    document.getElementById('notaCreditoModalTitle').textContent = title;

    const formContainer = document.getElementById('notaCreditoForm');
    if (!formContainer) return;

    // 🔽 Asegurar que comprobantesData esté cargado
    const render = () => {
        console.log('📦 comprobantesData:', JSON.stringify(comprobantesData.slice(0,3), null, 2));
        const compOptions = (comprobantesData || []).map(c => {
            const nombreCliente = c.cliente || c.cliente_nombre || c.razon_social || c.razon || 'Sin cliente';
            return `<option value="${c.serie}-${c.numero}" data-comp-id="${c.id}">${c.serie}-${c.numero} - ${nombreCliente}</option>`;
        }).join('');
    
    formContainer.innerHTML = `
        <div class="ficha-section">
            <div class="ficha-section-title">📝 Datos de la nota de crédito</div>
            <div class="ficha-grid">
                <div class="form-field col-4">
                    <label>Comprobante afectado</label>
                    <select id="notaComprobante" onchange="cargarDatosComprobanteAfectado(this.value)">
                        <option value="">-- Seleccione un comprobante --</option>
                        ${compOptions || '<option value="" disabled>Sin comprobantes</option>'}
                    </select>
                </div>
                <div class="form-field col-3">
                    <label>Serie</label>
                    <input id="notaSerie" value="FC01">
                </div>
                <div class="form-field col-3">
                    <label>Número</label>
                    <input id="notaNumero" value="" placeholder="Automático">
                </div>
                <div class="form-field col-3">
                    <label>Estado</label>
                    <select id="notaEstado">
                        ${options(ESTADOS_NOTA, 'Borrador')}
                    </select>
                </div>
                <div class="form-field col-4">
                    <label>Cliente</label>
                    <input id="notaCliente" placeholder="Razón social">
                </div>
                <div class="form-field col-4">
                    <label>RUC</label>
                    <input id="notaRuc" placeholder="12345678901">
                </div>
                <div class="form-field col-4">
                    <label>Monto</label>
                    <input id="notaMonto" type="number" value="0" step="0.01">
                </div>
                <div class="form-field col-6">
                    <label>Motivo</label>
                    <select id="notaMotivo">
                        <option>Anulación de operación</option>
                        <option>Devolución</option>
                        <option>Descuento posterior</option>
                        <option>Error en descripción</option>
                        <option>Ajuste comercial</option>
                    </select>
                </div>
                <div class="form-field col-12">
                    <label>Observaciones</label>
                    <textarea id="notaObs" placeholder="Observaciones de la nota de crédito"></textarea>
                </div>
            </div>
        </div>
    `;
    
    document.getElementById('notaCreditoModal').classList.add('show');
        if (isEdit) setTimeout(() => cargarNotaCreditoParaEditar(id), 50);
    };

    if (!comprobantesData || comprobantesData.length === 0) {
        loadComprobantes().then(render);
    } else {
        render();
    }
}

function closeNotaCreditoModal() {
    closeModal('notaCreditoModal');
}



function cargarDatosComprobanteAfectado(valorSeleccionado) {
    if (!valorSeleccionado) return;

    const comp = comprobantesData.find(c => `${c.serie}-${c.numero}` === valorSeleccionado);

    if (!comp) {
        console.warn('⚠️ No se encontró el comprobante seleccionado:', valorSeleccionado);
        showToast('No se encontraron datos para el comprobante seleccionado', 'warning');
        return;
    }

    const setValue = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.value = value ?? '';
    };

    setValue('notaCliente', comp.cliente || comp.cliente_nombre || comp.razon_social || '');
    setValue('notaRuc', comp.ruc || comp.cliente_numero_doc || '');
    setValue('notaMonto', comp.monto || comp.total || 0);

    showToast(`✅ Datos de ${comp.serie}-${comp.numero} cargados`, 'success');
}



// ============================================================
// CARGAR NOTA DE CRÉDITO EXISTENTE PARA EDICIÓN
// ============================================================
async function cargarNotaCreditoParaEditar(id) {
    try {
        console.log('📥 Cargando nota de crédito para editar ID:', id);
        showToast('⏳ Cargando datos de la nota de crédito...', 'info');

        const response = await apiFetch(`/ventas/api/notas-credito/${id}`);
        if (!response.success) {
            showToast('Error al cargar nota de crédito: ' + (response.error || 'Desconocido'), 'error');
            return;
        }

        const n = response.data;
        console.log('📦 Datos de nota de crédito cargados:', n);

        const setSelectValue = (id, value) => {
            const el = document.getElementById(id);
            if (!el || value === undefined || value === null) return;
            const val = String(value).trim();
            let found = false;
            for (const opt of el.options) {
                if (opt.value === val) { opt.selected = true; found = true; break; }
            }
            if (!found) {
                for (const opt of el.options) {
                    if (opt.value.toLowerCase() === val.toLowerCase()) { opt.selected = true; found = true; break; }
                }
            }
        };

        const setValue = (id, value) => {
            const el = document.getElementById(id);
            if (el) el.value = value ?? '';
        };

        setValue('notaSerie', n.serie);
        setValue('notaNumero', n.numero);
        setSelectValue('notaEstado', n.estado);
        setValue('notaCliente', n.cliente_nombre);
        setValue('notaRuc', n.cliente_numero_doc);
        setValue('notaMonto', n.monto);
        setSelectValue('notaMotivo', n.motivo);
        setValue('notaObs', n.observaciones);

        if (n.comprobante_asociado) {
            setSelectValue('notaComprobante', n.comprobante_asociado);
        }

        showToast('✅ Nota de crédito cargada correctamente', 'success');

    } catch (error) {
        console.error('❌ Error cargando nota de crédito para editar:', error);
        showToast('Error al cargar la nota de crédito: ' + error.message, 'error');
    }
}

function openDevolucionModal(id = null) {
    editingId = id;
    const isEdit = id !== null;
    const title = isEdit ? 'Editar devolución' : 'Nueva devolución';
    document.getElementById('devolucionModalTitle').textContent = title;
    
    const formContainer = document.getElementById('devolucionForm');
    if (!formContainer) return;
    
    const compOptions = comprobantesData.map(c => 
        `<option value="${c.serie}-${c.numero}">${c.serie}-${c.numero} - ${c.cliente || 'Sin cliente'}</option>`
    ).join('');
    
    formContainer.innerHTML = `
        <div class="ficha-section">
            <div class="ficha-section-title">🔄 Datos de la devolución</div>
            <div class="ficha-grid">
                <div class="form-field col-4">
                    <label>Comprobante vinculado</label>
                    <select id="devComprobante">${compOptions || '<option value="">Sin comprobantes</option>'}</select>
                </div>
                <div class="form-field col-4">
                    <label>N° Devolución</label>
                    <input id="devNumero" value="DEV-${String(Date.now()).slice(-8)}">
                </div>
                <div class="form-field col-4">
                    <label>Estado</label>
                    <select id="devEstado">
                        ${options(ESTADOS_DEVOLUCION, 'Pendiente')}
                    </select>
                </div>
                <div class="form-field col-4">
                    <label>Cliente</label>
                    <input id="devCliente" placeholder="Razón social">
                </div>
                <div class="form-field col-4">
                    <label>RUC</label>
                    <input id="devRuc" placeholder="12345678901">
                </div>
                <div class="form-field col-4">
                    <label>Monto</label>
                    <input id="devMonto" type="number" value="0" step="0.01">
                </div>
                <div class="form-field col-6">
                    <label>Motivo</label>
                    <select id="devMotivo">
                        <option>Producto defectuoso</option>
                        <option>Producto incorrecto</option>
                        <option>Exceso de cantidad</option>
                        <option>Daño en transporte</option>
                        <option>Otro</option>
                    </select>
                </div>
                <div class="form-field col-12">
                    <label>Observaciones</label>
                    <textarea id="devObs" placeholder="Observaciones de la devolución"></textarea>
                </div>
            </div>
        </div>
    `;
    
    document.getElementById('devolucionModal').classList.add('show');
}

function closeDevolucionModal() {
    closeModal('devolucionModal');
}


// ============================================================
// FUNCIÓN VALIDADO POR HELLEN - CORREGIDA
// ============================================================

function validateByHellen() {
    // Verificar que hay productos en la cotización
    if (quoteProducts.length === 0) {
        showToast('⚠️ Agrega al menos un producto a la cotización', 'warning');
        return;
    }
    
    // Verificar que hay un cliente seleccionado
    const ruc = document.getElementById('fRuc')?.value?.trim() || '';
    if (!ruc) {
        showToast('⚠️ Primero busca un cliente por RUC', 'warning');
        return;
    }
    
    showConfirmModal(
        '✅ ¿Validar cotización por Hellen?',
        'Estás a punto de marcar esta cotización como <b>"Validado por Hellen"</b>.',
        '⚠️ Esta acción confirma que Hellen ha revisado y validado la cotización.',
        async function() {
            // Mostrar loading en el botón
            const btn = document.querySelector('#cotizacionModal .btn-blue');
            const originalText = btn?.textContent || '✅ Validado por Hellen';
            if (btn) {
                btn.textContent = '⏳ Validando...';
                btn.disabled = true;
            }
            
            try {
                // 🔽 IMPORTANTE: Usar 'Validado por Hellen' (sin espacio al final)
                await guardarCotizacion('Validado por Hellen');
                showToast('✅ Cotización validada por Hellen', 'success');
                closeModal('cotizacionModal');
                await loadCotizaciones();
            } catch (error) {
                console.error('Error validando cotización:', error);
                showToast('❌ Error al validar: ' + error.message, 'error');
            } finally {
                if (btn) {
                    btn.textContent = originalText;
                    btn.disabled = false;
                }
            }
        },
        '✅ Sí, validar'
    );
}



// ventas.js - Después de loadDevoluciones()

async function loadEliminadas() {
    console.log('🔄 Cargando historial de eliminaciones...');
    try {
        const response = await apiFetch('/api/cotizaciones/eliminadas');
        if (response.success) {
            eliminadasData = response.data || [];
            console.log(`✅ ${eliminadasData.length} registros de eliminaciones cargados`);
            renderEliminadas();
        } else {
            showToast('Error al cargar historial de eliminaciones', 'error');
        }
    } catch (error) {
        console.error('❌ Error cargando eliminadas:', error);
        showToast('Error al cargar historial de eliminaciones', 'error');
    }
}

// ventas.js - Después de loadEliminadas()

function renderEliminadas() {
    const q = document.getElementById('eliminadasSearch')?.value?.toLowerCase() || '';
    
    const list = eliminadasData.filter(r => {
        const searchStr = `${r.numero || ''} ${r.cliente || ''} ${r.ruc || ''} ${r.motivo || ''}`.toLowerCase();
        return !q || searchStr.includes(q);
    });
    
    const tbody = document.getElementById('eliminadasRows');
    if (!tbody) return;
    
    if (list.length === 0) {
        tbody.innerHTML = `<tr><td colspan="10" style="text-align:center;color:#94A3B8;padding:40px;">
            🗑️ No hay cotizaciones eliminadas registradas
        </td></tr>`;
        const countEl = document.getElementById('eliminadasCount');
        if (countEl) countEl.textContent = 'Mostrando 0 de 0 registros';
        return;
    }
    
    tbody.innerHTML = list.map((r, i) => {
        return `
        <tr>
            <td>${i + 1}</td>
            <td class="date-cell">${sd(r.fecha_eliminacion)}</td>
            <td><b>${sd(r.numero)}</b></td>
            <td class="left"><b>${sd(r.cliente)}</b></td>
            <td>${sd(r.ruc)}</td>
            <td><b>${money(r.total || 0)}</b></td>
            <td class="left" style="max-width:300px; font-size:10px;">
                <span style="background:#FEE2E2; padding:2px 10px; border-radius:4px; display:inline-block; color:#991B1B; font-weight:800;">
                    ${esc(r.motivo || 'Sin motivo')}
                </span>
            </td>
            <td>
                <span style="background:#DBEAFE; padding:2px 10px; border-radius:4px; font-weight:800; color:#1D4ED8; font-size:10px; white-space:nowrap;">
                    ${sd(r.usuario_elimino || 'Sistema')}
                </span>
            </td>
            <td>${badgeStatus(r.estado)}</td>
            <td>
                <button onclick="verDetalleEliminada(${r.id})" 
                        style="height:24px; padding:0 10px; font-size:9px; border-radius:4px; background:#F8FAFC; border:1px solid #E5E7EB; cursor:pointer; transition:all 0.2s;"
                        onmouseover="this.style.background='#E2E8F0'"
                        onmouseout="this.style.background='#F8FAFC'">
                    👁️ Ver
                </button>
            </td>
        </tr>`;
    }).join('');
    
    const countEl = document.getElementById('eliminadasCount');
    if (countEl) {
        countEl.textContent = `Mostrando ${list.length} de ${eliminadasData.length} registros`;
    }
}


// ventas.js - Después de renderEliminadas()

function limpiarFiltrosEliminadas() {
    const search = document.getElementById('eliminadasSearch');
    if (search) search.value = '';
    renderEliminadas();
    showToast('🧹 Filtros limpiados', 'info');
}

function verDetalleEliminada(id) {
    const registro = eliminadasData.find(r => r.id === id);
    if (!registro) {
        showToast('❌ Registro no encontrado', 'error');
        return;
    }
    
    // Mostrar modal con detalles usando showConfirmModal
    showConfirmModal(
        '🗑️ Detalle de eliminación',
        `
        <div style="text-align:left; font-size:13px; line-height:1.8;">
            <p><strong>📄 Cotización:</strong> ${registro.numero || 'N/A'}</p>
            <p><strong>🏢 Cliente:</strong> ${registro.cliente || 'N/A'}</p>
            <p><strong>📋 RUC:</strong> ${registro.ruc || 'N/A'}</p>
            <p><strong>💰 Total:</strong> ${money(registro.total || 0)}</p>
            <p><strong>📅 Fecha eliminación:</strong> ${registro.fecha_eliminacion || 'N/A'}</p>
            <p><strong>👤 Eliminado por:</strong> ${registro.usuario_elimino || 'Sistema'}</p>
            <p><strong>📝 Motivo:</strong></p>
            <div style="background:#FEF2F2; padding:10px 14px; border-radius:8px; border-left:4px solid #DC2626; color:#991B1B; font-weight:800; margin-top:4px;">
                ${esc(registro.motivo || 'Sin motivo especificado')}
            </div>
        </div>
        `,
        '💡 Este registro es histórico y no se puede recuperar',
        null,
        '🔒 Cerrar'
    );
}

// Función para exportar datos de eliminadas (opcional)
function exportarEliminadasCSV() {
    if (eliminadasData.length === 0) {
        showToast('⚠️ No hay datos para exportar', 'warning');
        return;
    }
    
    // Crear contenido CSV
    let csv = 'N° Cotización,Cliente,RUC,Total,Fecha Eliminación,Motivo,Eliminado por\n';
    eliminadasData.forEach(r => {
        csv += `${r.numero || ''},${r.cliente || ''},${r.ruc || ''},${r.total || 0},${r.fecha_eliminacion || ''},${r.motivo || ''},${r.usuario_elimino || ''}\n`;
    });
    
    // Descargar
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `eliminadas_${isoLima()}.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
    
    showToast('✅ Exportación completada', 'success');
}
// ============================================================
// MODALES DE CONFIRMACIÓN Y ÉXITO
// ============================================================

function showConfirmModal(title, message, warning, onConfirm) {
    // Remover modales existentes
    document.querySelectorAll('.confirm-modal-overlay').forEach(el => el.remove());
    
    const overlay = document.createElement('div');
    overlay.className = 'confirm-modal-overlay';
    overlay.style.cssText = `
        position: fixed;
        inset: 0;
        background: rgba(0, 0, 0, 0.6);
        backdrop-filter: blur(8px);
        z-index: 999999;
        display: flex;
        align-items: center;
        justify-content: center;
        animation: fadeIn 0.3s ease;
    `;
    
    const modal = document.createElement('div');
    modal.style.cssText = `
        background: #FFFFFF;
        border-radius: 20px;
        max-width: 520px;
        width: 95%;
        padding: 32px 28px 24px;
        box-shadow: 0 30px 80px rgba(0,0,0,0.35);
        animation: modalSlideUp 0.3s ease;
        text-align: center;
    `;
    
    modal.innerHTML = `
        <div style="font-size: 48px; margin-bottom: 12px;">⚠️</div>
        <h2 style="font-size: 22px; font-weight: 900; color: #0F172A; margin-bottom: 8px;">${title}</h2>
        <p style="font-size: 15px; color: #475569; line-height: 1.5; margin-bottom: 12px;">${message}</p>
        <div style="background: #FEF2F2; border-radius: 12px; padding: 12px 16px; margin-bottom: 24px; border-left: 4px solid #EF233C;">
            <span style="font-size: 13px; font-weight: 700; color: #DC2626;">${warning}</span>
        </div>
        <div style="display: flex; gap: 12px; justify-content: center;">
            <button class="confirm-cancel-btn" style="
                padding: 12px 32px;
                border-radius: 12px;
                border: 1px solid #E5E7EB;
                background: #FFFFFF;
                color: #0F172A;
                font-weight: 800;
                font-size: 14px;
                cursor: pointer;
                transition: all 0.2s;
            ">Cancelar</button>
            <button class="confirm-accept-btn" style="
                padding: 12px 32px;
                border-radius: 12px;
                border: none;
                background: #EF233C;
                color: #FFFFFF;
                font-weight: 800;
                font-size: 14px;
                cursor: pointer;
                transition: all 0.2s;
                box-shadow: 0 4px 14px rgba(239, 35, 60, 0.35);
            ">✅ Sí, generar cotización</button>
        </div>
    `;
    
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    
    // Animaciones CSS
    const style = document.createElement('style');
    style.textContent = `
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        @keyframes modalSlideUp {
            from { opacity: 0; transform: translateY(30px) scale(0.95); }
            to { opacity: 1; transform: translateY(0) scale(1); }
        }
        .confirm-cancel-btn:hover {
            background: #F1F5F9;
        }
        .confirm-accept-btn:hover {
            background: #D91A30;
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(239, 35, 60, 0.45);
        }
    `;
    document.head.appendChild(style);
    
    // Event listeners
    modal.querySelector('.confirm-cancel-btn').addEventListener('click', function() {
        overlay.remove();
    });
    
    modal.querySelector('.confirm-accept-btn').addEventListener('click', function() {
        overlay.remove();
        if (typeof onConfirm === 'function') {
            onConfirm();
        }
    });
    
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) {
            overlay.remove();
        }
    });
}


// ============================================================
// SELECCIÓN MÚLTIPLE DE PRODUCTOS
// ============================================================

let productSelectorData = [];
let selectedProductIds = new Set();

function openProductSelector() {
    // Si no hay productos maestros, cargarlos primero
    if (PRODUCTOS_MAESTROS.length === 0) {
        showToast('⏳ Cargando productos...', 'info');
        cargarProductosMaestros().then(() => {
            setTimeout(() => openProductSelector(), 300);
        });
        return;
    }
    
    // Resetear selecciones
    selectedProductIds = new Set();
    productSelectorData = [...PRODUCTOS_MAESTROS];
    
    // Renderizar tabla
    renderProductSelector();
    
    // Mostrar modal
    document.getElementById('productSelectorModal').classList.add('show');
    
    // Enfocar buscador
    setTimeout(() => {
        document.getElementById('productSelectorSearch')?.focus();
    }, 300);
}

function renderProductSelector() {
    const tbody = document.getElementById('productSelectorRows');
    const search = document.getElementById('productSelectorSearch')?.value?.toLowerCase() || '';
    
    // Filtrar productos
    let filtered = productSelectorData;
    if (search) {
        filtered = productSelectorData.filter(p => 
            (p.codigo && p.codigo.toLowerCase().includes(search)) ||
            (p.producto && p.producto.toLowerCase().includes(search)) ||
            (p.descripcion && p.descripcion.toLowerCase().includes(search)) ||
            (p.marca && p.marca.toLowerCase().includes(search))
        );
    }
    
    if (!tbody) return;
    
    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:#94A3B8;padding:30px;">📭 No se encontraron productos</td></tr>`;
        document.getElementById('selectedCount').textContent = selectedProductIds.size;
        return;
    }
    
    tbody.innerHTML = filtered.map((p, index) => {
        const isChecked = selectedProductIds.has(p.id) || selectedProductIds.has(p.codigo);
        // Usar id o codigo como identificador
        const idKey = p.id || p.codigo;
        
        // 🔽 FIX: Asegurar que valorVenta sea un número
        const valorVenta = parseFloat(p.valorVenta) || 0;
        
        return `
        <tr>
            <td style="text-align:center;">
                <input type="checkbox" class="product-select-checkbox" 
                       data-id="${idKey}" 
                       ${isChecked ? 'checked' : ''}
                       onchange="toggleProductSelection('${idKey}', this.checked)">
            </td>
            <td style="font-weight:900; color:#0F172A;">${p.codigo || '-'}</td>
            <td style="text-align:left; font-weight:800;">${p.producto || p.descripcion || 'Sin nombre'}</td>
            <td>${p.modelo || '-'}</td>
            <td>${p.marca || '-'}</td>
            <td>${p.um || 'NIU'}</td>
            <td>${p.stock || 0}</td>
            <td style="font-weight:900; color:#059669;">S/ ${valorVenta.toFixed(2)}</td>
            <td>
                <input type="number" class="product-select-qty" 
                       data-id="${idKey}"
                       value="1" 
                       min="1" 
                       style="width:60px; height:28px; border:1px solid #E5E7EB; border-radius:6px; text-align:center; font-size:12px;"
                       onchange="updateProductQty('${idKey}', this.value)">
            </td>
        </tr>
    `}).join('');
    
    document.getElementById('selectedCount').textContent = selectedProductIds.size;
    
    // Actualizar el checkbox "Seleccionar todos"
    const totalCheckboxes = document.querySelectorAll('.product-select-checkbox').length;
    const checkedCheckboxes = document.querySelectorAll('.product-select-checkbox:checked').length;
    const selectAllCheckbox = document.getElementById('selectAllCheckbox');
    if (selectAllCheckbox) {
        if (totalCheckboxes > 0 && checkedCheckboxes === totalCheckboxes) {
            selectAllCheckbox.checked = true;
            selectAllCheckbox.indeterminate = false;
        } else if (checkedCheckboxes > 0) {
            selectAllCheckbox.checked = false;
            selectAllCheckbox.indeterminate = true;
        } else {
            selectAllCheckbox.checked = false;
            selectAllCheckbox.indeterminate = false;
        }
    }
}

function toggleProductSelection(idKey, checked) {
    if (checked) {
        selectedProductIds.add(idKey);
    } else {
        selectedProductIds.delete(idKey);
    }
    document.getElementById('selectedCount').textContent = selectedProductIds.size;
    
    // Actualizar el checkbox "Seleccionar todos"
    const totalCheckboxes = document.querySelectorAll('.product-select-checkbox').length;
    const checkedCheckboxes = document.querySelectorAll('.product-select-checkbox:checked').length;
    const selectAllCheckbox = document.getElementById('selectAllCheckbox');
    if (selectAllCheckbox) {
        if (totalCheckboxes > 0 && checkedCheckboxes === totalCheckboxes) {
            selectAllCheckbox.checked = true;
            selectAllCheckbox.indeterminate = false;
        } else if (checkedCheckboxes > 0) {
            selectAllCheckbox.checked = false;
            selectAllCheckbox.indeterminate = true;
        } else {
            selectAllCheckbox.checked = false;
            selectAllCheckbox.indeterminate = false;
        }
    }
}


// ============================================================
// FUNCIÓN PARA LIMPIAR FILTROS DE FECHA
// ============================================================

function clearDateFilter() {
    console.log('🧹 Limpiando filtros de fecha...');
    
    const fechaInicio = document.getElementById('qFechaInicio');
    const fechaFin = document.getElementById('qFechaFin');
    
    if (fechaInicio) {
        fechaInicio.value = '';
        console.log('  ✅ Fecha inicio limpiada');
    }
    
    if (fechaFin) {
        fechaFin.value = '';
        console.log('  ✅ Fecha fin limpiada');
    }
    
    // Volver a renderizar la tabla de cotizaciones
    renderCotizaciones();
    
    showToast('🧹 Filtros de fecha limpiados', 'info');
}

// ============================================================
// OPEN PEDIDO COMPRA MODAL SAP - VERSIÓN CORREGIDA
// ============================================================
function openPedidoCompraModalSAP(mode, id) {
    console.log('📋 openPedidoCompraModalSAP:', mode, id);
    forzarLimpiezaModalPC();
    // Al editar, guardar sobre ESTE PC (antes quedaba en modo "cotización" y pedía elegir una o creaba otro PC)
    const _esEdicionPC = (mode === 'edit' || mode === 'editar' || (mode === 'directo' && id));
    modalMode = _esEdicionPC ? 'editar' : (mode === 'directo' ? 'directo' : 'cot');
    editingId = _esEdicionPC ? id : null;
    // 🔽 FUNCIÓN SEGURA PARA LIMPIAR ELEMENTOS
    function clearElement(id, defaultValue = '') {
        const el = document.getElementById(id);
        if (el) {
            el.value = defaultValue;
        }
    }
    
    // Limpiar modal (solo si los elementos existen)
    clearElement('pcCotSearch', '');
    clearElement('pcCotNumero', '');
    clearElement('pcCotFecha', '');
    clearElement('pcRuc', '');
    clearElement('pcCliente', '');
    clearElement('pcCondicionPago', '');
    clearElement('pcVendedor', '');
    clearElement('pcMonto', '0');
    clearElement('pcMontoConIgv', '0');
    clearElement('pcMontoPC', '0');
    clearElement('pcNumero', '');
    clearElement('pcContacto', '');
    clearElement('pcEntrega', '');
    clearElement('pcObs', '');
    clearElement('pcFecha', '');
    clearElement('pcEditId', '');
    
    // Limpiar dropdowns
    const condicion = document.getElementById('pcCondicion');
    if (condicion) condicion.value = ''; // se elige leyendo la OC del cliente
    clearElement('pcOcCliente', '');
    
    const moneda = document.getElementById('pcMoneda');
    if (moneda) moneda.value = 'S/)';
    
    // Limpiar tabla de productos
    const tbody = document.getElementById('pcItemsBody');
    if (tbody) {
        tbody.innerHTML = '';
    }
    
    // Limpiar resumen
    const elementosResumen = ['pcResumenSubtotal', 'pcResumenValorVenta', 'pcResumenIgv', 'pcResumenTotal', 'pcResumenProductos'];
    elementosResumen.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            if (id === 'pcResumenProductos') {
                el.textContent = '0';
            } else {
                el.textContent = 'S/ 0.00';
            }
        }
    });
    
    // Limpiar validaciones
    const checkboxes = ['vPrecio', 'vProducto', 'vCantidad', 'vEntrega', 'vTransporte', 'vMoneda', 'vVigencia'];
    checkboxes.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.checked = false;
        }
    });
    
    // Actualizar etiquetas de validación
    if (typeof updateValidationStatus === 'function') {
        updateValidationStatus();
    }
    
    // 🔽 MODO EDICIÓN vs CREACIÓN
    const esEdicion = (mode === 'edit' || mode === 'editar' || (mode === 'directo' && id));
    const esDesdeCotizacion = (mode === 'cot' || mode === 'cotizacion' || mode === 'cotizacion_modal');
    
    console.log('📌 esEdicion:', esEdicion, 'esDesdeCotizacion:', esDesdeCotizacion);
    
    // ============================================================
    // 🔽 CONFIGURAR CAMPOS DE COTIZACIÓN SEGÚN MODO
    // ============================================================
    const camposCotizacion = ['pcCotSearch', 'pcCotNumero', 'pcCotFecha', 'pcRuc', 'pcCliente', 'pcCondicionPago', 'pcVendedor', 'pcMonto', 'pcMontoConIgv'];
    
    if (esEdicion) {
        console.log('🔒 Modo EDICIÓN - campos de cotización en solo lectura');
        camposCotizacion.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.readOnly = true;
                el.style.background = '#F1F5F9';
                el.style.color = '#64748B';
                el.style.cursor = 'not-allowed';
            }
        });
        
        // Ocultar botón de búsqueda
        const searchBtn = document.querySelector('#pcCotSearch + button');
        if (searchBtn) {
            searchBtn.style.opacity = '0.5';
            searchBtn.style.pointerEvents = 'none';
        }
        
        // 🔽 CAMPOS DEL PC - EDITABLES
        const camposPC = ['pcFecha', 'pcNumero', 'pcContacto', 'pcMontoPC', 'pcEntrega', 'pcObs'];
        camposPC.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.style.background = '#FFFFFF';
                el.style.color = '#0F172A';
                el.readOnly = false;
            }
        });
        
        // Dropdowns editables
        ['pcCondicion', 'pcMoneda'].forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.style.background = '#FFFFFF';
                el.style.color = '#0F172A';
                el.disabled = false;
            }
        });
        
        // Botones de producto habilitados
        const productBtn = document.querySelector('.btn-soft[onclick*="openProductSelectorPC"]');
        if (productBtn) {
            productBtn.style.opacity = '1';
            productBtn.style.pointerEvents = 'auto';
        }
        
        // 🔽 CARGAR DATOS DEL PC SI ES EDICIÓN
        if (id && typeof cargarPCParaEdicion === 'function') {
            cargarPCParaEdicion(id);
        }
        
    } else {
        console.log('✏️ Modo CREACIÓN - campos de cotización editables');
        camposCotizacion.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.readOnly = false;
                el.style.background = '#FFFFFF';
                el.style.color = '#0F172A';
                el.style.cursor = 'text';
            }
        });
        
        // Mostrar botón de búsqueda
        const searchBtn = document.querySelector('#pcCotSearch + button');
        if (searchBtn) {
            searchBtn.style.opacity = '1';
            searchBtn.style.pointerEvents = 'auto';
        }
        
        // 🔽 SI ES DESDE COTIZACIÓN (modal de cotización)
        if (esDesdeCotizacion) {
            console.log('📋 Cargando datos desde cotización');
            // Los datos se cargan desde el evento que llama a esta función
        }
    }
    
    // Cambiar título del modal
    const title = document.getElementById('pedidoCompraModalTitle');
    const sub = document.getElementById('modalSub');
    
    if (title) {
        title.textContent = esEdicion ? '✏️ Editar PC Cliente' : '📋 Crear PC Cliente';
    }
    if (sub) {
        sub.textContent = esEdicion 
            ? 'Edita los datos del Pedido de Compra - campos de cotización en solo lectura' 
            : 'Primero se valida. No comprar ni despachar si existe observación.';
    }
    
    // Cambiar texto de los botones de guardar
    const btnYellow = document.querySelector('.btn-neon-yellow');
    const btnGreen = document.querySelector('.btn-neon-green');
    
    if (btnYellow) {
        btnYellow.textContent = esEdicion ? '⚠️ Actualizar PC Observado' : '⚠️ Crear PC Observado';
    }
    if (btnGreen) {
        btnGreen.textContent = esEdicion ? '✅ Actualizar PC Conforme' : '✅ Crear PC Conforme';
    }
    
    // Mostrar modal
    const modal = document.getElementById('pedidoCompraModal');
    if (modal) {
        modal.classList.add('show');
    }
}

function cargarPCParaEdicion(pcId) {
    console.log('📋 Cargando PC para edición:', pcId);
    
    function setValue(id, value, defaultValue = '') {
        const el = document.getElementById(id);
        if (el) {
            el.value = value !== undefined && value !== null ? value : defaultValue;
            return true;
        } else {
            console.warn(`⚠️ Elemento no encontrado: #${id}`);
            return false;
        }
    }
    
    fetch(`/ventas/api/pedido-compra/${pcId}`)
        .then(response => response.json())
        .then(result => {
            if (result.success && result.data) {
                const pc = result.data;
                console.log('📦 Datos del PC:', pc);
                
                // ============================================================
                // 🔽 BLOQUE 1: Cotización relacionada - SOLO LECTURA
                // ============================================================
                // Usar formatearFecha para la fecha de cotización
                const fechaCotizacion = formatearFecha(pc.fecha || pc.fecha_recepcion);
                console.log('📅 Fecha cotización formateada:', fechaCotizacion);
                
                setValue('pcCotNumero', pc.cotizacion_numero || 'SIN COTIZACIÓN');
                setValue('pcCotFecha', fechaCotizacion);
                setValue('pcRuc', pc.ruc || '');
                setValue('pcCliente', pc.cliente || '');
                setValue('pcCondicionPago', pc.condicion_pago || pc.condicion_atencion || 'Contado');
                setValue('pcVendedor', pc.vendedor || pc.responsable || 'Helen Blas Príncipe');
                
                // Montos con 2 decimales
                const montoSinIgv = parseFloat(pc.monto) || 0;
                const montoConIgv = montoSinIgv * 1.18;
                setValue('pcMonto', montoSinIgv.toFixed(2));
                setValue('pcMontoConIgv', montoConIgv.toFixed(2));
                
                // ============================================================
                // 🔽 BLOQUE 2: Datos del PC - EDITABLES
                // ============================================================
                const fechaRecepcion = formatearFecha(pc.fecha_recepcion || pc.fecha);
                console.log('📅 Fecha recepción formateada:', fechaRecepcion);
                
                setValue('pcNumero', pc.numero || '');
                setValue('pcContacto', pc.responsable || pc.cliente_contacto || '');
                setValue('pcFecha', fechaParaInput(pc.fecha || pc.fecha_recepcion));
                setCondicionPagoPC(pc.condicion_pago || pc.condicion_atencion || '');
                setValue('pcOcCliente', pc.oc_cliente || '');
                setValue('pcMoneda', pc.moneda || 'S/)');
                setValue('pcMontoPC', montoSinIgv.toFixed(2));
                setValue('pcEntrega', pc.lugar_entrega || pc.entrega || '');
                setValue('pcObs', pc.observaciones || '');
                
                // ============================================================
                // 🔽 BLOQUE 3: Productos
                // ============================================================
                const items = pc.items || [];
                const tbody = document.getElementById('pcItemsBody');
                if (tbody) {
                    tbody.innerHTML = '';
                    
                    if (items.length > 0) {
                        items.forEach((item, index) => {
                            const cantidad = parseFloat(item.cantidad_pc || item.cantidad || 1);
                            const precio = parseFloat(item.precio_pc || item.precio || 0);
                            const stock = null; // se lee en vivo del inventario (antes se guardaba aquí el valor total)
                            
                            agregarItemPCTable(
                                item.codigo || '',
                                item.producto || item.descripcion || '',
                                item.marca || '',
                                item.modelo || '',
                                cantidad,
                                precio,
                                stock
                            );
                        });
                    } else {
                        tbody.innerHTML = `<tr><td colspan="13" style="text-align:center;padding:20px;color:#94A3B8;font-size:12px;">⚠️ Este PC no tiene productos asociados</td></tr>`;
                    }
                }
                
                // ============================================================
                // 🔽 BLOQUE 4: Validaciones
                // ============================================================
                const checkboxes = {
                    'vPrecio': pc.valida_precios,
                    'vProducto': (pc.valida_productos ?? pc.valida_cantidades),
                    'vCantidad': pc.valida_cantidades,
                    'vEntrega': pc.valida_entrega,
                    'vTransporte': pc.valida_transporte,
                    'vMoneda': pc.valida_montos,
                    'vVigencia': pc.valida_vigencia
                };
                
                Object.keys(checkboxes).forEach(id => {
                    const el = document.getElementById(id);
                    if (el) {
                        el.checked = !!checkboxes[id];
                    }
                });
                
                // Actualizar etiquetas de validación
                updateValidationStatus();
                
                // ============================================================
                // 🔽 ACTUALIZAR RESUMEN
                // ============================================================
                actualizarResumenPC();
                
                // ============================================================
                // 🔽 GUARDAR ID DEL PC PARA ACTUALIZACIÓN
                // ============================================================
                setValue('pcEditId', pc.id);
                
                console.log('✅ PC cargado para edición');
                showToast('✅ PC cargado correctamente', 'success');
                
            } else {
                console.error('❌ Error cargando PC:', result.error);
                showToast('❌ Error cargando PC: ' + (result.error || 'Desconocido'), 'error');
            }
        })
        .catch(error => {
            console.error('❌ Error en fetch:', error);
            showToast('❌ Error al cargar los datos del PC', 'error');
        });
}


async function cargarPCParaEditar(id) {
    try {
        console.log('📥 Cargando PC para editar ID:', id);
        showToast('⏳ Cargando datos del PC...', 'info');
        
        const response = await apiFetch(`/ventas/api/pedido-compra/${id}`);
        
        if (!response.success) {
            showToast('Error al cargar PC: ' + (response.error || 'Desconocido'), 'error');
            return;
        }
        
        const pc = response.data;
        console.log('📦 Datos del PC cargados:', pc);
        
        // ============================================================
        // FUNCIÓN PARA NORMALIZAR ITEMS (con marca y modelo)
        // ============================================================
        const normalizarItems = (items) => {
            if (!items || !Array.isArray(items) || items.length === 0) {
                return [];
            }
            
            return items.map(item => {
                // Si es un objeto con propiedades
                if (typeof item === 'object' && !Array.isArray(item)) {
                    return {
                        codigo: item.codigo || '',
                        producto: item.producto || item.descripcion || '',
                        marca: item.marca || '',
                        modelo: item.modelo || '',
                        cantidad_cotizada: parseFloat(item.cantidad_cotizada || item.cantidad_cot || 0),
                        cantidad_pc: parseFloat(item.cantidad_pc || item.cantidad || 1),
                        precio_cotizado: parseFloat(item.precio_cotizado || item.precio_cot || 0),
                        precio_pc: parseFloat(item.precio_pc || item.precio || 0),
                        stock: parseFloat(item.stock || 0)
                    };
                }
                
                // Si es un array [codigo, descripcion, cant_cot, cant_pc, precio_cot, precio_pc, stock]
                if (Array.isArray(item)) {
                    return {
                        codigo: item[0] || '',
                        producto: item[1] || '',
                        marca: item[2] || '',
                        modelo: item[3] || '',
                        cantidad_cotizada: parseFloat(item[4]) || 0,
                        cantidad_pc: parseFloat(item[5]) || 1,
                        precio_cotizado: parseFloat(item[6]) || 0,
                        precio_pc: parseFloat(item[7]) || 0,
                        stock: parseFloat(item[8]) || 0
                    };
                }
                
                // Fallback
                return {
                    codigo: item.codigo || '',
                    producto: item.producto || '',
                    marca: item.marca || '',
                    modelo: item.modelo || '',
                    cantidad_cotizada: parseFloat(item.cantidad_cotizada || item.cantidad || 0),
                    cantidad_pc: parseFloat(item.cantidad_pc || item.cantidad || 1),
                    precio_cotizado: parseFloat(item.precio_cotizado || item.valorVenta || item.precio || 0),
                    precio_pc: parseFloat(item.precio_pc || item.valorVenta || item.precio || 0),
                    stock: parseFloat(item.stock || 0)
                };
            });
        };

        // NORMALIZAR ITEMS
        const itemsNormalizados = normalizarItems(pc.items || []);
        console.log('📦 Items normalizados:', itemsNormalizados);
        
        // ============================================================
        // FUNCIÓN AUXILIAR PARA SETEAR VALOR
        // ============================================================
        const setValue = (id, value) => {
            const el = document.getElementById(id);
            if (el) {
                el.value = value !== undefined && value !== null ? value : '';
                if (el.hasAttribute('readonly')) {
                    el.removeAttribute('readonly');
                    el.style.background = '#FFFFFF';
                    el.style.color = '#0F172A';
                    el.style.cursor = 'text';
                }
                return true;
            }
            return false;
        };
        
        const formatDateForInput = (dateStr) => {
            if (!dateStr) return '';
            try {
                const date = new Date(dateStr);
                if (isNaN(date.getTime())) return '';
                const year = date.getFullYear();
                const month = String(date.getMonth() + 1).padStart(2, '0');
                const day = String(date.getDate()).padStart(2, '0');
                const hours = String(date.getHours()).padStart(2, '0');
                const minutes = String(date.getMinutes()).padStart(2, '0');
                return `${year}-${month}-${day}T${hours}:${minutes}`;
            } catch (e) {
                return '';
            }
        };
        
        // ============================================================
        // LLENAR CAMPOS BÁSICOS
        // ============================================================
        setValue('pcNumero', pc.numero);
        setValue('pcFecha', formatDateForInput(pc.fecha));
        setValue('pcCliente', pc.cliente);
        setValue('pcRuc', pc.ruc);
        setValue('pcMonto', pc.monto || 0);
        setValue('pcMontoConIgv', (pc.monto || 0) * 1.18);
        setValue('pcEntrega', pc.lugar_entrega || pc.entrega);
        setValue('pcObs', pc.observaciones);
        setValue('pcCondicionPago', pc.condicion_pago || 'Contado');
        setValue('pcVendedor', pc.vendedor || 'Helen Blas Príncipe');
        setValue('pcCotNumero', pc.cotizacion_numero || '');
        
        // Medio
        const medioSelect = document.getElementById('pcMedio');
        if (medioSelect && pc.medio) {
            medioSelect.value = pc.medio;
        }
        
        // Condición pago
        setCondicionPagoPC(pc.condicion_pago || '');
        setValue('pcOcCliente', pc.oc_cliente || '');
        
        // Moneda
        const monedaSelect = document.getElementById('pcMoneda');
        if (monedaSelect && pc.moneda) {
            for (let opt of monedaSelect.options) {
                if (opt.value === pc.moneda || opt.textContent.includes(pc.moneda)) {
                    opt.selected = true;
                    break;
                }
            }
        }
        
        // ============================================================
        // CARGAR PRODUCTOS (ITEMS) EN LA TABLA - SIN BOTÓN ELIMINAR
        // ============================================================
        const tbody = document.getElementById('pcItemsBody');
        if (tbody) {
            tbody.innerHTML = '';
            const items = itemsNormalizados;
            console.log(`📦 Cargando ${items.length} items para edición...`);
            
            if (items.length === 0) {
                // Agregar una fila vacía si no hay items
                addPedidoItemSAP();
            } else {
                items.forEach((item, idx) => {
                    const codigo = item.codigo || '';
                    const producto = item.producto || 'Producto sin nombre';
                    const marca = item.marca || '';
                    const modelo = item.modelo || '';
                    const cantidadCotizada = parseFloat(item.cantidad_cotizada) || 0;
                    const cantidadPC = parseFloat(item.cantidad_pc) || 1;
                    const precioCotizado = Math.round((parseFloat(item.precio_cotizado) || 0) * 100) / 100; // 2 decimales
                    const precioPC = Math.round((parseFloat(item.precio_pc) || 0) * 100) / 100;
                    const stock = parseFloat(item.stock) || 0;
                    const faltante = Math.max(cantidadPC - stock, 0);
                    const valorTotal = cantidadPC * precioPC;
                    
                    const tr = document.createElement('tr');
                    tr.id = `item-row-${idx + 1}`;
                    tr.style.borderBottom = '1px solid #E2E8F0';
                    
                    tr.innerHTML = `
                        <td style="padding:2px 3px; text-align:center; font-weight:800; font-size:9px; background:#F8FAFC;">${idx + 1}</td>
                        <td style="padding:2px 3px;">
                            <input value="${esc(codigo)}" 
                                   style="width:100%; border:none; background:#F1F5F9; font-size:9px; padding:0; outline:none; font-weight:800; color:#1D4ED8;"
                                   readonly>
                        </td>
                        <td style="padding:2px 3px;">
                            <input value="${esc(producto)}" 
                                   style="width:100%; border:none; background:#F1F5F9; font-size:9px; padding:0; outline:none; font-weight:800;"
                                   readonly>
                        </td>
                        <td style="padding:2px 3px;">
                            <input value="${esc(modelo)}" 
                                   style="width:100%; border:none; background:transparent; font-size:9px; padding:0; outline:none; font-weight:700; color:#0F172A;"
                                   onchange="actualizarValorTotalPCSAP(this)">
                        </td>
                        <td style="padding:2px 3px;">
                            <input value="${esc(marca)}" 
                                   style="width:100%; border:none; background:transparent; font-size:9px; padding:0; outline:none; font-weight:700; color:#0F172A;"
                                   onchange="actualizarValorTotalPCSAP(this)">
                        </td>
                        <td style="padding:2px 3px; width:55px;">
                            <input type="number" value="${cantidadCotizada}" 
                                   style="width:45px; border:none; background:#F1F5F9; font-size:9px; padding:0; outline:none; text-align:center;"
                                   readonly>
                        </td>
                        <td style="padding:2px 3px; width:55px;">
                            <input type="number" value="${cantidadPC}" 
                                   style="width:45px; border:none; background:transparent; font-size:9px; padding:0; outline:none; text-align:center; font-weight:900; color:#0F172A;"
                                   onchange="actualizarValorTotalPCSAP(this)">
                        </td>
                        <td style="padding:2px 3px; width:65px;">
                            <input type="number" step="0.01" value="${Number(precioCotizado || 0).toFixed(2)}" 
                                   style="width:55px; border:none; background:#F1F5F9; font-size:9px; padding:0; outline:none; text-align:center;"
                                   readonly>
                        </td>
                        <td style="padding:2px 3px; width:65px;">
                            <input type="number" step="0.01" value="${Number(precioPC || 0).toFixed(2)}" 
                                   style="width:55px; border:none; background:transparent; font-size:9px; padding:0; outline:none; text-align:center; font-weight:900; color:#0F172A;"
                                   onchange="actualizarValorTotalPCSAP(this)">
                        </td>
                        <td style="padding:2px 3px; width:70px; text-align:center; font-weight:900; color:#059669; font-size:9px;">
                            <span id="valor-total-${idx + 1}">${valorTotal.toFixed(2)}</span>
                        </td>
                        <td style="padding:2px 3px; text-align:center; font-size:8px; color:#64748B; font-weight:800;">${stock}</td>
                        <td style="padding:2px 3px; text-align:center; font-size:8px; font-weight:900; color:${faltante > 0 ? '#DC2626' : '#16A34A'};">${faltante}</td>
                    `;
                    
                    tbody.appendChild(tr);
                });
                
                // Reordenar items después de cargar
                reordenarItemsSAP();
            }
        }
        
        // ============================================================
        // CARGAR ESTADO DE VALIDACIONES (switches)
        // ============================================================
        const validationMap = {
            'vPrecio': pc.valida_precios,
            'vCantidad': pc.valida_cantidades,
            'vProducto': pc.valida_stock,
            'vEntrega': pc.valida_entrega,
            'vMoneda': pc.valida_montos,
            'vTransporte': pc.valida_transporte,
            'vVigencia': pc.valida_vigencia,
            'vMargen': pc.valida_margen
        };
        
        Object.keys(validationMap).forEach(id => {
            const checkbox = document.getElementById(id);
            if (checkbox) {
                const isValid = validationMap[id] === true || validationMap[id] === 'Sí';
                checkbox.checked = isValid;
                const label = document.getElementById(id + 'Label');
                if (label) {
                    label.textContent = isValid ? '✅ Válido' : '❌ No válido';
                    label.style.color = isValid ? '#16A34A' : '#DC2626';
                }
            }
        });
        
        // ============================================================
        // ACTUALIZAR ESTADO EN EL HEADER
        // ============================================================
        const estadoDisplay = document.getElementById('pcEstadoDisplay');
        if (estadoDisplay && pc.estado) {
            estadoDisplay.textContent = pc.estado;
            estadoDisplay.style.color = pc.estado === 'PC observado' || pc.estado === 'Bloqueado' ? '#DC2626' : '#16A34A';
        }
        
        // ============================================================
        // ACTUALIZAR SEMÁFORO
        // ============================================================
        setTimeout(() => {
            updateValidationSemaphore();
            updateValidationStatus();
        }, 100);

        const monedaEl = document.getElementById('pcResumenMoneda');
        if (monedaEl) {
            monedaEl.textContent = (pc.moneda && pc.moneda.includes('Soles')) ? 'S/' : (pc.moneda || 'S/');
        }
        setTimeout(() => {
            if (typeof actualizarResumenPC === 'function') {
                actualizarResumenPC();
            }
        }, 50);
        
        setTimeout(() => {
            updateValidationSemaphore();
            updateValidationStatus();
        }, 100);
        
        showToast('✅ PC cargado para editar', 'success');
        
    } catch (error) {
        console.error('❌ Error cargando PC:', error);
        showToast('❌ Error al cargar el PC: ' + error.message, 'error');
    }
}



  // ============================================================
// FUNCIÓN PARA ACTUALIZAR FALTANTE - DEBE ESTAR ANTES DE addPedidoItemSAP
// ============================================================
function actualizarFaltanteDesdeInput(input) {
    const row = input.closest('tr');
    if (!row) return;
    
    const inputs = row.querySelectorAll('input');
    // Índices: [0]=código, [1]=descripción, [2]=marca, [3]=modelo
    // [4]=cant_cot, [5]=cant_pc, [6]=precio_cot, [7]=precio_pc, [8]=stock
    const cantidadPC = Number(inputs[5]?.value || 0);
    const stock = Number(inputs[8]?.value || 0);
    const faltanteCell = row.querySelector('td:nth-child(11)');
    const faltante = Math.max(cantidadPC - stock, 0);
    
    if (faltanteCell) {
        faltanteCell.textContent = faltante;
        faltanteCell.style.color = faltante > 0 ? '#DC2626' : '#16A34A';
    }
}

// ============================================================
// FUNCIÓN PARA AGREGAR ITEM SAP - AHORA actualizarFaltanteDesdeInput YA EXISTE
// ============================================================
function addPedidoItemSAP() {
    const tbody = document.getElementById('pcItemsBody');
    if (!tbody) return;
    
    const rowCount = tbody.children.length + 1;
    
    const tr = document.createElement('tr');
    tr.id = `item-row-${rowCount}`;
    tr.style.borderBottom = '1px solid #E2E8F0';
    
    tr.innerHTML = `
        <td style="padding:2px 3px; text-align:center; font-weight:800; font-size:9px; background:#F8FAFC;">${rowCount}</td>
        <td style="padding:2px 3px;">
            <input type="text" placeholder="Código" 
                   style="width:100%; border:none; background:transparent; font-size:9px; padding:0; outline:none; font-weight:800;">
        </td>
        <td style="padding:2px 3px;">
            <input type="text" placeholder="Descripción" 
                   style="width:100%; border:none; background:transparent; font-size:9px; padding:0; outline:none;">
        </td>
        <td style="padding:2px 3px;">
            <input type="text" placeholder="Modelo" 
                   style="width:100%; border:none; background:transparent; font-size:9px; padding:0; outline:none; font-weight:700;">
        </td>
        <td style="padding:2px 3px;">
            <input type="text" placeholder="Marca" 
                   style="width:100%; border:none; background:transparent; font-size:9px; padding:0; outline:none; font-weight:700;">
        </td>
        <td style="padding:2px 3px; width:55px;">
            <input type="number" value="0" 
                   style="width:45px; border:none; background:transparent; font-size:9px; padding:0; outline:none; text-align:center;">
        </td>
        <td style="padding:2px 3px; width:55px;">
            <input type="number" value="1" 
                   style="width:45px; border:none; background:transparent; font-size:9px; padding:0; outline:none; text-align:center; font-weight:900;">
        </td>
        <td style="padding:2px 3px; width:65px;">
            <input type="number" step="0.01" value="0" 
                   style="width:55px; border:none; background:transparent; font-size:9px; padding:0; outline:none; text-align:center;">
        </td>
        <td style="padding:2px 3px; width:65px;">
            <input type="number" step="0.01" value="0" 
                   style="width:55px; border:none; background:transparent; font-size:9px; padding:0; outline:none; text-align:center; font-weight:900; color:#0F172A;">
        </td>
        <td style="padding:2px 3px; width:70px; text-align:center; font-weight:900; color:#94A3B8; font-size:9px;">
            <span id="valor-total-${rowCount}">0.00</span>
        </td>
        <td style="padding:2px 3px; text-align:center; font-size:8px; color:#64748B; font-weight:800;">0</td>
        <td style="padding:2px 3px; text-align:center; font-size:8px; font-weight:900; color:#EF4444;">0</td>
    `;
    
    tbody.appendChild(tr);
}

// ============================================================
// FUNCIÓN PARA MOSTRAR EL MODAL (separada para claridad)
// ============================================================
function mostrarModalPC(mode) {
    // Limpiar y preparar el modal
    clearPedidoModalSAP();
    
    // Limpiar buscador y resultados
    const searchInput = document.getElementById('pcCotSearch');
    if (searchInput) searchInput.value = '';
    const resultsContainer = document.getElementById('cotizacionSearchResults');
    if (resultsContainer) {
        resultsContainer.style.display = 'none';
        resultsContainer.innerHTML = '';
    }
    
    // Mostrar modal
    document.getElementById('pedidoCompraModal').classList.add('show');
    
    // Si hay cotizaciones, mostrar el conteo
    if (cotizacionesData && cotizacionesData.length > 0) {
        console.log(`📋 ${cotizacionesData.length} cotizaciones disponibles para buscar`);
    } else {
        console.warn('⚠️ No hay cotizaciones cargadas para el buscador');
    }
}



function loadPedidoCotizacionSAP() {
    const select = document.getElementById('pcCotSelect');
    const cotId = select ? parseInt(select.value) : null;
    if (!cotId) return;
    
    const cotizacion = cotizacionesData.find(c => c.id === cotId);
    if (!cotizacion) return;
    
    document.getElementById('pcCotNumero').value = cotizacion.numero || '';
    document.getElementById('pcCotFecha').value = cotizacion.fecha || '';
    document.getElementById('pcCliente').value = cotizacion.razon || '';
    document.getElementById('pcRuc').value = cotizacion.ruc || '';
    // monto de la cotización ya incluye IGV: base sin IGV = total - igv (evita doble IGV)
    const _pcConIgv = Number(cotizacion.total || cotizacion.monto || 0);
    const _pcSinIgv = cotizacion.igv != null ? _pcConIgv - Number(cotizacion.igv || 0) : Number(cotizacion.subtotal || 0);
    const _pcMontoEl = document.getElementById('pcMonto');
    const _pcMontoIgvEl = document.getElementById('pcMontoConIgv');
    if (_pcMontoEl) _pcMontoEl.value = _pcSinIgv.toFixed(2);
    if (_pcMontoIgvEl) _pcMontoIgvEl.value = _pcConIgv.toFixed(2);
    
    // Cargar productos
    const productos = cotizacion.productos || [];
    const tbody = document.getElementById('pcItemsBody');
    if (tbody) {
        tbody.innerHTML = '';
        productos.forEach((p, i) => {
            const faltante = Math.max((p.cantidad || 0) - (p.stock || 0), 0);
            tbody.insertAdjacentHTML('beforeend', `
                <tr>
                    <td>${i + 1}</td>
                    <td><input value="${p.codigo || ''}" style="width:90px; height:28px; border:1px solid #CBD5E1; border-radius:6px; padding:0 6px; font-size:11px;"></td>
                    <td><input value="${p.producto || p.descripcion || ''}" style="width:160px; height:28px; border:1px solid #CBD5E1; border-radius:6px; padding:0 6px; font-size:11px;"></td>
                    <td><input type="number" value="${p.cantidad || 0}" style="width:60px; height:28px; border:1px solid #CBD5E1; border-radius:6px; padding:0 6px; font-size:11px; text-align:center;"></td>
                    <td><input type="number" value="${p.cantidad || 1}" style="width:60px; height:28px; border:1px solid #CBD5E1; border-radius:6px; padding:0 6px; font-size:11px; text-align:center;"></td>
                    <td><input type="number" step="0.01" value="${p.valorVenta || 0}" style="width:80px; height:28px; border:1px solid #CBD5E1; border-radius:6px; padding:0 6px; font-size:11px; text-align:right;"></td>
                    <td><input type="number" step="0.01" value="${p.valorVenta || 0}" style="width:80px; height:28px; border:1px solid #CBD5E1; border-radius:6px; padding:0 6px; font-size:11px; text-align:right;"></td>
                    <td><input type="number" value="${p.stock || 0}" style="width:60px; height:28px; border:1px solid #CBD5E1; border-radius:6px; padding:0 6px; font-size:11px; text-align:center;"></td>
                    <td style="font-weight:900; color:#DC2626;">${faltante}</td>
                </tr>
            `);
        });
        if (productos.length === 0) addPedidoItemSAP();
    }
}



// Función para calcular y actualizar el Valor Total PC
function actualizarValorTotalPCSAP(input) {
    const row = input.closest('tr');
    if (!row) return;
    
    const inputs = row.querySelectorAll('input');
    // Índices: [0]=código, [1]=descripción, [2]=marca, [3]=modelo
    // [4]=cant_cot, [5]=cant_pc, [6]=precio_cot, [7]=precio_pc, [8]=stock
    const cantidadPC = Number(inputs[5]?.value || 0);
    const precioPC = Math.round(Number(inputs[7]?.value || 0) * 100) / 100; // 2 decimales
    if (inputs[7] && inputs[7].value !== '' && Number(inputs[7].value) !== precioPC) inputs[7].value = precioPC.toFixed(2);
    const valorTotal = Math.round(cantidadPC * precioPC * 100) / 100;
    
    // Buscar el span del Valor Total en la columna (10ma columna, index 9)
    const valueSpan = row.querySelector('td:nth-child(10) span');
    if (valueSpan) {
        valueSpan.textContent = valorTotal.toFixed(2);
        // Cambiar color según el valor
        if (valorTotal > 0) {
            valueSpan.style.color = '#059669';
            valueSpan.style.fontWeight = '900';
        } else {
            valueSpan.style.color = '#94A3B8';
            valueSpan.style.fontWeight = '700';
        }
    }
    
    // También actualizar faltante
    actualizarFaltanteDesdeInput(inputs[5] || input);
}

// Función para eliminar ítem
function eliminarItemSAP(rowId) {
    const row = document.getElementById(rowId);
    if (row) {
        row.remove();
        // Re-numerar los ítems
        reordenarItemsSAP();
    }
}

// Función para reordenar números de ítems
function reordenarItemsSAP() {
    const rows = document.querySelectorAll('#pcItemsBody tr');
    rows.forEach((row, index) => {
        const numCell = row.querySelector('td:first-child');
        if (numCell) {
            numCell.textContent = index + 1;
        }
        // Actualizar el ID de la fila
        const newId = `item-row-${index + 1}`;
        row.id = newId;
        // Actualizar el onclick del botón eliminar
        const deleteBtn = row.querySelector('td:last-child button');
        if (deleteBtn) {
            deleteBtn.setAttribute('onclick', `eliminarItemSAP('${newId}')`);
        }
    });
}
// ============================================================
// REVISIÓN - FUNCIONES COMPLETAS
// ============================================================

// Variables globales para revisión
let revisionData = [];
let currentRevisionFilter = '';

/**
 * Obtiene el rol del usuario desde la sesión
 */
function getUsuarioRol() {
    // Intentar desde el elemento HTML
    const rolElement = document.getElementById('usuarioRol');
    if (rolElement) return rolElement.value || 'vendedor';
    
    // Intentar desde sessionStorage
    try {
        const session = JSON.parse(sessionStorage.getItem('erp_session') || '{}');
        if (session.rol) return session.rol;
    } catch (e) {}
    
    // Intentar desde FLASK_SESSION
    if (typeof FLASK_SESSION !== 'undefined' && FLASK_SESSION.rol) {
        return FLASK_SESSION.rol;
    }
    
    return 'vendedor';
}

/**
 * Verifica si el usuario tiene permisos para ver el módulo de revisión
 */
function esUsuarioAutorizado() {
    const rol = getUsuarioRol();
    const rolesPermitidos = ['hellen', 'erika', 'admin', 'superadmin', 'administrador'];
    return rolesPermitidos.includes(rol);
}

/**
 * Carga las cotizaciones en estado de revisión
 */
async function loadRevision() {
    console.log('🔄 Cargando cotizaciones en revisión...');
    
    // Verificar autorización
    if (!esUsuarioAutorizado()) {
        console.warn('⚠️ Usuario no autorizado para ver revisiones');
        const tbody = document.getElementById('revisionRows');
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="10" style="text-align:center;color:#DC2626;padding:40px;">
                🔒 No tienes permisos para ver este módulo.<br>
                <small style="color:#94A3B8;">Solo Hellen y Erika pueden acceder a Revisiones.</small>
            </td></tr>`;
        }
        return;
    }
    
    try {
        const response = await apiFetch('/ventas/api/cotizaciones/revision');
        if (response.success) {
            revisionData = response.data || [];
            console.log(`✅ ${revisionData.length} cotizaciones en revisión cargadas`);
            renderRevision();
        } else {
            showToast('Error al cargar revisiones: ' + (response.error || 'Desconocido'), 'error');
        }
    } catch (error) {
        console.error('❌ Error cargando revisiones:', error);
        showToast('Error al cargar revisiones', 'error');
    }
}

function renderRevision() {
    const q = document.getElementById('revisionSearch')?.value?.toLowerCase() || '';
    const st = document.getElementById('revisionStatus')?.value || '';
    
    const list = revisionData.filter(r => {
        const searchStr = `${r.numero || ''} ${r.cliente || ''} ${r.ruc || ''} ${r.vendedor || ''} ${r.codigo || ''}`.toLowerCase();
        const matchText = !q || searchStr.includes(q);
        const matchStatus = !st || r.estado === st;
        return matchText && matchStatus;
    });
    
    const tbody = document.getElementById('revisionRows');
    if (!tbody) return;
    
    const puedeActuar = esUsuarioAutorizado();
    
    if (list.length === 0) {
        tbody.innerHTML = `<tr><td colspan="10" style="text-align:center;color:#94A3B8;padding:40px;">
            📭 No hay cotizaciones en revisión que coincidan con los filtros.
            ${revisionData.length > 0 ? `(${revisionData.length} registros cargados)` : ''}
        </td></tr>`;
        const countEl = document.getElementById('revisionCount');
        if (countEl) countEl.textContent = `Mostrando 0 de ${revisionData.length}`;
        return;
    }
    
    tbody.innerHTML = list.map((r, i) => {
        const estado = r.estado || 'Por validar';
        let badgeEstado = badgeStatus(estado);
        
        if (estado === 'Rechazada') {
            badgeEstado = `<span class="badge b-canceled">❌ ${estado}</span>`;
            if (r.motivo_rechazo) {
                badgeEstado += `<br><small style="color:#DC2626;font-size:7px;">${r.motivo_rechazo}</small>`;
            }
        } else if (estado === 'Aceptada por Cliente' || estado === 'Aceptada') {
            badgeEstado = `<span class="badge b-accepted">✅ ${estado}</span>`;
        } else if (estado === 'Por validar') {
            badgeEstado = `<span class="badge b-pending">⭐ ${estado}</span>`;
        }
        
        const esRevisable = estado === 'Por validar' || estado === 'Validado por Hellen' || estado === 'Validado';
        
        let accionesHtml = '';
        
        if (puedeActuar && esRevisable) {
            // 🔽 BOTONES EN UNA SOLA LÍNEA HORIZONTAL
            accionesHtml = `
                <div style="display:flex;flex-direction:row;gap:4px;flex-wrap:nowrap;align-items:center;justify-content:center;">
                    <button onclick="openCotizacionModal(${r.id})" 
                            style="height:24px;padding:0 10px;font-size:8px;border-radius:4px;background:#2563EB;color:#fff;border:0;font-weight:800;cursor:pointer;white-space:nowrap;"
                            onmouseover="this.style.background='#1D4ED8'"
                            onmouseout="this.style.background='#2563EB'">
                        👁️ Ver
                    </button>
                    <button onclick="aceptarRevision(${r.id})" 
                            style="height:24px;padding:0 10px;font-size:8px;border-radius:4px;background:#16A34A;color:#fff;border:0;font-weight:800;cursor:pointer;white-space:nowrap;"
                            onmouseover="this.style.background='#15803D'"
                            onmouseout="this.style.background='#16A34A'">
                        ✅ Aceptar
                    </button>
                    <button onclick="rechazarRevision(${r.id})" 
                            style="height:24px;padding:0 10px;font-size:8px;border-radius:4px;background:#DC2626;color:#fff;border:0;font-weight:800;cursor:pointer;white-space:nowrap;"
                            onmouseover="this.style.background='#B91C1C'"
                            onmouseout="this.style.background='#DC2626'">
                        ❌ Rechazar
                    </button>
                </div>
            `;
        } else if (estado === 'Aceptada por Cliente' || estado === 'Aceptada') {
            accionesHtml = `
                <div style="display:flex;flex-direction:row;gap:4px;align-items:center;justify-content:center;">
                    <span class="badge b-ok" style="font-size:8px;padding:2px 8px;">✅ Aceptada</span>
                    <button onclick="openCotizacionModal(${r.id})" 
                            style="height:22px;padding:0 10px;font-size:8px;border-radius:4px;background:#F8FAFC;border:1px solid #E5E7EB;font-weight:800;cursor:pointer;white-space:nowrap;"
                            onmouseover="this.style.background='#E2E8F0'"
                            onmouseout="this.style.background='#F8FAFC'">
                        👁️ Ver
                    </button>
                </div>
            `;
        } else if (estado === 'Rechazada') {
            accionesHtml = `
                <div style="display:flex;flex-direction:row;gap:4px;align-items:center;justify-content:center;">
                    <span class="badge b-canceled" style="font-size:8px;padding:2px 8px;">❌ Rechazada</span>
                    <button onclick="openCotizacionModal(${r.id})" 
                            style="height:22px;padding:0 10px;font-size:8px;border-radius:4px;background:#F8FAFC;border:1px solid #E5E7EB;font-weight:800;cursor:pointer;white-space:nowrap;"
                            onmouseover="this.style.background='#E2E8F0'"
                            onmouseout="this.style.background='#F8FAFC'">
                        👁️ Ver
                    </button>
                </div>
            `;
        } else {
            accionesHtml = `
                <button onclick="openCotizacionModal(${r.id})" 
                        style="height:22px;padding:0 10px;font-size:8px;border-radius:4px;background:#F8FAFC;border:1px solid #E5E7EB;font-weight:800;cursor:pointer;white-space:nowrap;"
                        onmouseover="this.style.background='#E2E8F0'"
                        onmouseout="this.style.background='#F8FAFC'">
                    👁️ Ver
                </button>
            `;
        }
        
        const fechaDisplay = formatearFecha(r.fecha || r.created_at);
        const validador = r.validado_por || '--';
        
        return `
        <tr>
            <td style="font-weight:900;font-size:11px;">${i + 1}</td>
            <td class="date-cell" style="font-size:9px;">${fechaDisplay}</td>
            <td>${badgeEstado}</td>
            <td style="font-weight:1000;font-size:12px;color:#0F172A;">${sd(r.numero)}${badgeNuevo(r, 'fecha')}</td>
            <td class="left" style="font-weight:900;font-size:11px;">${sd(r.cliente)}</td>
            <td style="font-weight:800;">${sd(r.ruc)}</td>
            <td style="font-size:10px;">${sd(r.vendedor || '--')}</td>
            <td style="font-weight:900;color:#EF233C;font-size:12px;">${money(r.total || r.monto || 0)}</td>
            <td style="font-size:9px;font-weight:800;color:#2563EB;">${sd(validador)}</td>
            <td style="min-width:180px;">
                ${accionesHtml}
            </td>
        </tr>
        `;
    }).join('');
    
    const countEl = document.getElementById('revisionCount');
    if (countEl) {
        countEl.textContent = `Mostrando ${list.length} de ${revisionData.length}`;
    }
}

// ventas.js - Reemplazar la función aceptarRevision

async function aceptarRevision(id) {
    const cotizacion = revisionData.find(c => c.id === id);
    if (!cotizacion) {
        showToast('❌ Cotización no encontrada', 'error');
        return;
    }
    
    if (!esUsuarioAutorizado()) {
        showToast('❌ No tienes permisos para aceptar cotizaciones', 'error');
        return;
    }
    
    showConfirmModal(
        '✅ ¿Generar cotización?',
        `Estás a punto de <b>GENERAR</b> la cotización <b>${cotizacion.numero || 'COT-XXXX'}</b> del cliente <b>${cotizacion.cliente || 'Cliente'}</b>.`,
        '⚠️ Al generar, la cotización pasará a estado "Generada" y quedará oficializada.',
        async function() {
            try {
                showToast('⏳ Procesando...', 'info');
                
                // 🔽 CAMBIAR A "Generada"
                const response = await apiFetch(`/ventas/api/cotizaciones/${id}/aceptar`, {
                    method: 'POST',
                    body: JSON.stringify({})
                });
                
                if (response.success) {
                    showToast('✅ Cotización generada correctamente', 'success');
                    await loadRevision();
                    await loadCotizaciones();
                    if (currentModule === 'revision') {
                        renderRevision();
                    }
                } else {
                    showToast('❌ Error: ' + (response.error || 'No se pudo generar'), 'error');
                }
            } catch (error) {
                console.error('❌ Error:', error);
                showToast('❌ Error al generar: ' + error.message, 'error');
            }
        },
        '✅ Sí, generar'
    );
}


/**
 * Rechaza una cotización en revisión con motivo
 */
async function rechazarRevision(id) {
    const cotizacion = revisionData.find(c => c.id === id);
    if (!cotizacion) {
        showToast('❌ Cotización no encontrada', 'error');
        return;
    }
    
    // Verificar que el usuario esté autorizado
    if (!esUsuarioAutorizado()) {
        showToast('❌ No tienes permisos para rechazar cotizaciones', 'error');
        return;
    }
    
    // Crear un modal con campo de motivo usando showDeleteConfirmModal
    showDeleteConfirmModal(
        '❌ ¿Rechazar cotización?',
        `Estás a punto de <b>RECHAZAR</b> la cotización <b>${cotizacion.numero || 'COT-XXXX'}</b> del cliente <b>${cotizacion.cliente || 'Cliente'}</b>.`,
        '⚠️ La cotización volverá a estado "Borrador". El vendedor deberá corregirla y volver a enviarla a revisión.',
        async function(motivo) {
            if (!motivo || motivo.trim() === '') {
                showToast('⚠️ Debes ingresar un motivo de rechazo', 'warning');
                return;
            }
            
            try {
                showToast('⏳ Procesando...', 'info');
                
                const response = await apiFetch(`/ventas/api/cotizaciones/${id}/rechazar`, {
                    method: 'POST',
                    body: JSON.stringify({ motivo_rechazo: motivo })
                });
                
                if (response.success) {
                    showToast('❌ Cotización rechazada', 'warning');
                    
                    // Recargar datos
                    await loadRevision();
                    await loadCotizaciones();
                    
                    if (currentModule === 'revision') {
                        renderRevision();
                    }
                } else {
                    showToast('❌ Error: ' + (response.error || 'No se pudo rechazar'), 'error');
                }
            } catch (error) {
                console.error('❌ Error:', error);
                showToast('❌ Error al rechazar: ' + error.message, 'error');
            }
        },
        '❌ Sí, rechazar'
    );
}

/**
 * Muestra/oculta la pestaña de revisión según el rol del usuario
 */
function mostrarPestanasPorRol() {
    const rol = getUsuarioRol();
    const tabRevision = document.querySelector('.tab-btn[data-tab="revision"]');
    
    if (tabRevision) {
        const autorizado = esUsuarioAutorizado();
        tabRevision.style.display = autorizado ? 'inline-flex' : 'none';
        
        if (!autorizado) {
            console.log('🔒 Pestaña "Revisión" oculta para usuario con rol:', rol);
        }
    }
}

// ============================================================
// MODAL DE CONFIRMACIÓN UNIVERSAL (MEJORADO)
// ============================================================

function showConfirmModal(title, message, warning, onConfirm, confirmText = '✅ Sí, confirmar') {
    // Remover modales existentes
    document.querySelectorAll('.confirm-modal-overlay').forEach(el => el.remove());
    
    const overlay = document.createElement('div');
    overlay.className = 'confirm-modal-overlay';
    overlay.style.cssText = `
        position: fixed;
        inset: 0;
        background: rgba(0, 0, 0, 0.6);
        backdrop-filter: blur(8px);
        z-index: 999999;
        display: flex;
        align-items: center;
        justify-content: center;
        animation: fadeIn 0.3s ease;
    `;
    
    const modal = document.createElement('div');
    modal.style.cssText = `
        background: #FFFFFF;
        border-radius: 20px;
        max-width: 520px;
        width: 95%;
        padding: 32px 28px 24px;
        box-shadow: 0 30px 80px rgba(0,0,0,0.35);
        animation: modalSlideUp 0.3s ease;
        text-align: center;
    `;
    
    // Determinar el icono según el tipo de acción
    let icon = '⚠️';
    let buttonColor = '#EF233C';
    let buttonHover = '#D91A30';
    
    if (title.includes('Duplicar')) {
        icon = '📋';
        buttonColor = '#0EA5E9';
        buttonHover = '#0284C7';
    } else if (title.includes('despacho') || title.includes('Guía') || title.includes('Factura')) {
        icon = '📦';
        buttonColor = '#16A34A';
        buttonHover = '#15803D';
    } else if (title.includes('Aceptada') || title.includes('Aceptar')) {
        icon = '✅';
        buttonColor = '#2563EB';
        buttonHover = '#1D4ED8';
    }
    
    modal.innerHTML = `
        <div style="font-size: 48px; margin-bottom: 12px;">${icon}</div>
        <h2 style="font-size: 22px; font-weight: 900; color: #0F172A; margin-bottom: 8px;">${title}</h2>
        <p style="font-size: 15px; color: #475569; line-height: 1.5; margin-bottom: 12px;">${message}</p>
        <div style="background: #FEF2F2; border-radius: 12px; padding: 12px 16px; margin-bottom: 24px; border-left: 4px solid #EF233C;">
            <span style="font-size: 13px; font-weight: 700; color: #DC2626;">${warning}</span>
        </div>
        <div style="display: flex; gap: 12px; justify-content: center;">
            <button class="confirm-cancel-btn" style="
                padding: 12px 32px;
                border-radius: 12px;
                border: 1px solid #E5E7EB;
                background: #FFFFFF;
                color: #0F172A;
                font-weight: 800;
                font-size: 14px;
                cursor: pointer;
                transition: all 0.2s;
            ">Cancelar</button>
            <button class="confirm-accept-btn" style="
                padding: 12px 32px;
                border-radius: 12px;
                border: none;
                background: ${buttonColor};
                color: #FFFFFF;
                font-weight: 800;
                font-size: 14px;
                cursor: pointer;
                transition: all 0.2s;
                box-shadow: 0 4px 14px ${buttonColor}55;
            ">${confirmText}</button>
        </div>
    `;
    
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    
    // Animaciones CSS
    const style = document.createElement('style');
    style.textContent = `
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        @keyframes modalSlideUp {
            from { opacity: 0; transform: translateY(30px) scale(0.95); }
            to { opacity: 1; transform: translateY(0) scale(1); }
        }
        .confirm-cancel-btn:hover {
            background: #F1F5F9;
        }
        .confirm-accept-btn:hover {
            background: ${buttonHover};
            transform: translateY(-2px);
            box-shadow: 0 6px 20px ${buttonColor}77;
        }
    `;
    document.head.appendChild(style);
    
    // Event listeners
    modal.querySelector('.confirm-cancel-btn').addEventListener('click', function() {
        overlay.remove();
    });
    
    modal.querySelector('.confirm-accept-btn').addEventListener('click', function() {
        overlay.remove();
        if (typeof onConfirm === 'function') {
            onConfirm();
        }
    });
    
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) {
            overlay.remove();
        }
    });
}

// ============================================================
// MODAL DE CONFIRMACIÓN CON CAMPO DE MOTIVO (para eliminaciones)
// ============================================================
function showDeleteConfirmModal(title, message, warning, onConfirm, confirmText = '🗑️ Sí, eliminar') {
    document.querySelectorAll('.confirm-modal-overlay').forEach(el => el.remove());

    const overlay = document.createElement('div');
    overlay.className = 'confirm-modal-overlay';
    overlay.style.cssText = `
        position: fixed;
        inset: 0;
        background: rgba(0, 0, 0, 0.6);
        backdrop-filter: blur(8px);
        z-index: 999999;
        display: flex;
        align-items: center;
        justify-content: center;
        animation: fadeIn 0.3s ease;
    `;

    const modal = document.createElement('div');
    modal.style.cssText = `
        background: #FFFFFF;
        border-radius: 20px;
        max-width: 520px;
        width: 95%;
        padding: 32px 28px 24px;
        box-shadow: 0 30px 80px rgba(0,0,0,0.35);
        animation: modalSlideUp 0.3s ease;
        text-align: center;
    `;

    modal.innerHTML = `
        <div style="font-size: 48px; margin-bottom: 12px;">🗑️</div>
        <h2 style="font-size: 22px; font-weight: 900; color: #0F172A; margin-bottom: 8px;">${title}</h2>
        <p style="font-size: 15px; color: #475569; line-height: 1.5; margin-bottom: 12px;">${message}</p>
        <div style="background: #FEF2F2; border-radius: 12px; padding: 12px 16px; margin-bottom: 18px; border-left: 4px solid #EF233C;">
            <span style="font-size: 13px; font-weight: 700; color: #DC2626;">${warning}</span>
        </div>
        <div style="text-align:left; margin-bottom:20px;">
            <label style="display:block;font-size:13px;font-weight:800;color:#0F172A;margin-bottom:6px;">
                Motivo de eliminación <span style="color:#DC2626;">*</span>
            </label>
            <textarea id="deleteReasonInput" placeholder="Escribe el motivo por el cual se elimina este registro..."
                style="width:100%;min-height:80px;border:1px solid #E5E7EB;border-radius:10px;padding:10px 12px;font-size:13px;font-family:inherit;resize:vertical;outline:none;transition:border-color 0.2s;"></textarea>
            <div id="deleteReasonError" style="display:none;color:#DC2626;font-size:11px;font-weight:700;margin-top:4px;">⚠️ Debes ingresar un motivo para continuar</div>
        </div>
        <div style="display: flex; gap: 12px; justify-content: center;">
            <button class="confirm-cancel-btn" style="
                padding: 12px 32px;
                border-radius: 12px;
                border: 1px solid #E5E7EB;
                background: #FFFFFF;
                color: #0F172A;
                font-weight: 800;
                font-size: 14px;
                cursor: pointer;
                transition: all 0.2s;
            ">Cancelar</button>
            <button class="confirm-accept-btn" style="
                padding: 12px 32px;
                border-radius: 12px;
                border: none;
                background: #EF233C;
                color: #FFFFFF;
                font-weight: 800;
                font-size: 14px;
                cursor: pointer;
                transition: all 0.2s;
                box-shadow: 0 4px 14px rgba(239, 35, 60, 0.35);
            ">${confirmText}</button>
        </div>
    `;

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    const style = document.createElement('style');
    style.textContent = `
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes modalSlideUp { from { opacity: 0; transform: translateY(30px) scale(0.95); } to { opacity: 1; transform: translateY(0) scale(1); } }
        .confirm-cancel-btn:hover { background: #F1F5F9; }
        .confirm-accept-btn:hover { background: #D91A30; transform: translateY(-2px); box-shadow: 0 6px 20px rgba(239,35,60,0.45); }
    `;
    document.head.appendChild(style);

    const textarea = modal.querySelector('#deleteReasonInput');
    const errorMsg = modal.querySelector('#deleteReasonError');

    textarea.addEventListener('input', function() {
        if (this.value.trim()) {
            this.style.borderColor = '#E5E7EB';
            errorMsg.style.display = 'none';
        }
    });

    modal.querySelector('.confirm-cancel-btn').addEventListener('click', function() {
        overlay.remove();
    });

    modal.querySelector('.confirm-accept-btn').addEventListener('click', function() {
        const motivo = textarea.value.trim();
        if (!motivo) {
            textarea.style.borderColor = '#DC2626';
            textarea.style.boxShadow = '0 0 0 3px rgba(220,38,38,0.15)';
            errorMsg.style.display = 'block';
            textarea.focus();
            return;
        }
        overlay.remove();
        if (typeof onConfirm === 'function') {
            onConfirm(motivo);
        }
    });

    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) overlay.remove();
    });

    setTimeout(() => textarea.focus(), 150);
}

function toggleAllProductCheckboxes(checked) {
    document.querySelectorAll('.product-select-checkbox').forEach(cb => {
        cb.checked = checked;
        const idKey = cb.dataset.id;
        if (checked) {
            selectedProductIds.add(idKey);
        } else {
            selectedProductIds.delete(idKey);
        }
    });
    document.getElementById('selectedCount').textContent = selectedProductIds.size;
}

function selectAllProducts() {
    document.querySelectorAll('.product-select-checkbox').forEach(cb => {
        cb.checked = true;
        const idKey = cb.dataset.id;
        selectedProductIds.add(idKey);
    });
    document.getElementById('selectedCount').textContent = selectedProductIds.size;
    const selectAllCheckbox = document.getElementById('selectAllCheckbox');
    if (selectAllCheckbox) selectAllCheckbox.checked = true;
}

function deselectAllProducts() {
    document.querySelectorAll('.product-select-checkbox').forEach(cb => {
        cb.checked = false;
        const idKey = cb.dataset.id;
        selectedProductIds.delete(idKey);
    });
    document.getElementById('selectedCount').textContent = selectedProductIds.size;
    const selectAllCheckbox = document.getElementById('selectAllCheckbox');
    if (selectAllCheckbox) selectAllCheckbox.checked = false;
}

function filterProductSelector() {
    renderProductSelector();
}



// ============================================================
// INICIALIZAR EVENTOS DEL FORMULARIO DE COTIZACIÓN
// ============================================================

function inicializarEventosCotizacion(isEdit) {
    // Evento para el descuento
    const discountValue = document.getElementById('fDiscountValue');
    const discountType = document.getElementById('fDiscountType');
    
    if (discountValue) {
        discountValue.addEventListener('input', calcQuote);
    }
    if (discountType) {
        discountType.addEventListener('change', calcQuote);
    }
    
    // Evento para el buscador rápido de productos (Enter)
    const quickSearch = document.getElementById('quickProductSearch');
    if (quickSearch) {
        quickSearch.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                addQuoteProductFromSearch();
            }
        });
    }
    
    // Inicializar campos personalizados
    document.querySelectorAll('select[onchange*="toggleCustomField"]').forEach(select => {
        const selectId = select.id;
        const inputId = selectId.replace('f', 'f') + 'Custom';
        const input = document.getElementById(inputId);
        if (input) {
            input.style.display = 'none';
        }
    });
}


// ============================================================
// RENDERIZAR CONTENIDO DEL FORMULARIO DE COTIZACIÓN - VERSIÓN COMPLETA
// ============================================================

// ============================================================
// RENDERIZAR CONTENIDO DEL FORMULARIO DE COTIZACIÓN - VERSIÓN COMPLETA
// ============================================================

function renderCotizacionFormContent(isEdit) {
   const condicionOptions = `
    <option value="Contado">Contado</option>
    <option value="Credito 7 Dias">Credito 7 Dias</option>
    <option value="Credito 15 Dias">Credito 15 Dias</option>
    <option value="Credito 30 Dias">Credito 30 Dias</option>
    <option value="Credito 45 Dias">Credito 45 Dias</option>
    <option value="Credito 60 Dias">Credito 60 Dias</option>
    <option value="Credito 90 Dias">Credito 90 Dias</option>
    <option value="Credito 120 Dias">Credito 120 Dias</option>
    <option value="Personalizado" selected>✏️ Personalizado...</option>
`;

   const tiempoOptions = `
    <option value="Inmediata">Inmediata</option>
    <option value="1 día hábil">1 día hábil</option>
    <option value="2 días hábiles">2 días hábiles</option>
    <option value="3 días hábiles">3 días hábiles</option>
    <option value="5 días hábiles" selected>5 días hábiles</option>
    <option value="7 días hábiles">7 días hábiles</option>
    <option value="10 días hábiles">10 días hábiles</option>
    <option value="15 días hábiles">15 días hábiles</option>
    <option value="Personalizado">✏️ Personalizado...</option>
`;

    const validezOptions = `
        <option value="7 días">7 días</option>
        <option value="15 días" selected>15 días</option>
        <option value="30 días">30 días</option>
        <option value="45 días">45 días</option>
        <option value="60 días">60 días</option>
        <option value="Personalizado">✏️ Personalizado...</option>
    `;

    const fuenteOptions = `
        <option value="Correo">Correo</option>
        <option value="WhatsApp">WhatsApp</option>
        <option value="Llamada">Llamada</option>
        <option value="Plataforma">Plataforma</option>
        <option value="Presencial">Presencial</option>
    `;

    const tipoOptions = `
        <option value="0">0</option>
        <option value="1">1</option>
        <option value="2">2</option>
        <option value="3">3</option>
    `;

    return `


<div style="display: grid !important; grid-template-columns: 1fr 1fr 1fr !important; gap: 10px !important; width: 100% !important; margin-bottom: 10px !important;">
    
    <!-- ============================================================ -->
    <!-- 1. DATOS DEL CLIENTE - COMPACTO -->
    <!-- ============================================================ -->
    <div class="create-panel client-card" style="background:#FFFFFF;border:1px solid #E5E7EB;border-radius:10px;box-shadow:0 2px 8px rgba(15,23,42,.04);overflow:hidden;">
        <h3 style="padding:4px 10px;border-bottom:1px solid #E5E7EB;font-size:11px;font-weight:1000;color:#0F172A;background:#FAFBFC;display:flex;align-items:center;gap:5px;margin:0;">
            <span style="color:#EF233C;font-weight:1000;">1.</span> 
            <span style="color:#EF233C;font-weight:1000;">Datos del Cliente</span>
        </h3>
        <div class="body" style="padding:5px 8px;">
            <!-- Buscar por RUC -->
            <div style="display:grid;grid-template-columns:1fr 70px;gap:4px;align-items:end;margin-bottom:2px;">
                <div class="form-field">
                    <label style="display:block;font-size:7px;font-weight:950;color:#334155;margin-bottom:1px;text-transform:uppercase;">Buscar por RUC</label>
                    <input id="fRucSearch" placeholder="Ingresa 11 dígitos" maxlength="11" oninput="autoLoadClientByRuc(this.value)" style="width:100%;height:19px;border:1px solid #E5E7EB;border-radius:5px;background:#FFFFFF;outline:none;color:#0F172A;font-size:9.5px;padding:0 6px;">
                </div>
                <button onclick="loadClient()" style="width:100%;height:19px;border-radius:5px;font-size:8.5px;padding:0 6px;background:#2563EB;color:#fff;border:0;font-weight:950;cursor:pointer;">🔍 Buscar</button>
            </div>
            <!-- RUC | Razón Social -->
            <div style="display:grid;grid-template-columns:1fr 1.8fr;gap:4px;margin-bottom:2px;">
                <div class="form-field">
                    <label style="display:block;font-size:7px;font-weight:950;color:#334155;margin-bottom:1px;text-transform:uppercase;">RUC <span style="color:#DC2626;font-weight:900;">*</span></label>
                    <input id="fRuc" readonly style="width:100%;height:18px;border:1px solid #E5E7EB;border-radius:5px;background:#F1F5F9;outline:none;color:#0F172A;font-size:9.5px;padding:0 5px;border-left:3px solid #DC2626;">
                </div>
                <div class="form-field">
                    <label style="display:block;font-size:7px;font-weight:950;color:#334155;margin-bottom:1px;text-transform:uppercase;">Razón Social</label>
                    <input id="fRazon" readonly style="width:100%;height:18px;border:1px solid #E5E7EB;border-radius:5px;background:#F1F5F9;outline:none;color:#0F172A;font-size:9.5px;padding:0 5px;">
                </div>
            </div>
            <!-- Dirección Fiscal | Contacto | Teléfono | Email -->
            <div style="display:grid;grid-template-columns:1.4fr 1fr 0.9fr 1.2fr;gap:4px;margin-bottom:2px;">
                <div class="form-field">
                    <label style="display:block;font-size:7px;font-weight:950;color:#334155;margin-bottom:1px;text-transform:uppercase;">Dirección Fiscal</label>
                    <input id="fDireccion" placeholder="Dirección fiscal" style="width:100%;height:18px;border:1px solid #E5E7EB;border-radius:5px;background:#FFFFFF;outline:none;color:#0F172A;font-size:9.5px;padding:0 5px;">
                </div>
                <div class="form-field">
    <label style="display:block;font-size:7px;font-weight:950;color:#334155;margin-bottom:1px;text-transform:uppercase;">Contacto</label>
    <div style="display:flex;gap:3px;align-items:center;">
        <select id="fContacto" 
                onchange="aplicarContactoSeleccionado()" 
                style="flex:1;width:100%;height:18px;border:1px solid #E5E7EB;border-radius:5px;background:#FFFFFF;outline:none;color:#0F172A;font-size:9.5px;padding:0 3px;">
            <option value="">-- Seleccione contacto --</option>
        </select>
        <input id="fContactoCustom" 
               placeholder="Nombre" 
               style="display:none;width:100%;height:18px;border:1px solid #E5E7EB;border-radius:5px;background:#FFFFFF;outline:none;color:#0F172A;font-size:9.5px;padding:0 5px;">
    </div>
</div>
                <div class="form-field">
                    <label style="display:block;font-size:7px;font-weight:950;color:#334155;margin-bottom:1px;text-transform:uppercase;">Teléfono</label>
                    <input id="fTelefono" placeholder="Número" style="width:100%;height:18px;border:1px solid #E5E7EB;border-radius:5px;background:#FFFFFF;outline:none;color:#0F172A;font-size:9.5px;padding:0 5px;">
                </div>
                <div class="form-field">
                    <label style="display:block;font-size:7px;font-weight:950;color:#334155;margin-bottom:1px;text-transform:uppercase;">Email</label>
                    <input id="fCorreo" placeholder="email@empresa.com" style="width:100%;height:18px;border:1px solid #E5E7EB;border-radius:5px;background:#FFFFFF;outline:none;color:#0F172A;font-size:9.5px;padding:0 5px;">
                </div>
            </div>
            <!-- N° Requerimiento | Fuente -->
            <div style="display:grid;grid-template-columns:1.5fr 1fr;gap:4px;margin-bottom:2px;">
                <div class="form-field">
                    <label style="display:block;font-size:7px;font-weight:950;color:#334155;margin-bottom:1px;text-transform:uppercase;">N° Requerimiento</label>
                    <input id="fReq" placeholder="Ej: REQ-001" style="width:100%;height:18px;border:1px solid #E5E7EB;border-radius:5px;background:#FFFFFF;outline:none;color:#0F172A;font-size:9.5px;padding:0 5px;">
                </div>
                <div class="form-field">
                    <label style="display:block;font-size:7px;font-weight:950;color:#334155;margin-bottom:1px;text-transform:uppercase;">Fuente</label>
                    <select id="fFuente" style="width:100%;height:18px;border:1px solid #E5E7EB;border-radius:5px;background:#FFFFFF;outline:none;color:#0F172A;font-size:9.5px;padding:0 3px;">
                        <option value="Correo">Correo</option>
                        <option value="WhatsApp">WhatsApp</option>
                        <option value="Llamada">Llamada</option>
                        <option value="Plataforma">Plataforma</option>
                        <option value="Presencial">Presencial</option>
                    </select>
                </div>
            </div>
            <!-- Guardar (de vuelta en su propia fila, como antes) -->
            <div style="display:flex;flex-direction:column;align-items:center;gap:1px;margin-top:2px;">
                <button onclick="saveClientFromQuote()" style="min-width:120px;height:20px;border-radius:6px;font-size:8.5px;font-weight:950;border:0;background:#16A34A;color:#fff;cursor:pointer;">💾 Guardar / Actualizar</button>
                <span style="color:#64748B;font-size:6.5px;font-weight:850;line-height:1;">Se guardará en Maestros</span>
            </div>
            <div id="clientConfirmBox" style="display:none;margin-top:2px;padding:3px 6px;border-radius:4px;font-size:9px;font-weight:900;text-align:center;border:1px solid transparent;"></div>
        </div>
    </div>

    <!-- ============================================================ -->
<!-- 2. CONDICIONES COMERCIALES - COMPACTO -->
<!-- ============================================================ -->
<div class="create-panel" style="background:#FFFFFF;border:1px solid #E5E7EB;border-radius:10px;box-shadow:0 2px 8px rgba(15,23,42,.04);overflow:hidden;">
    <h3 style="padding:4px 10px;border-bottom:1px solid #E5E7EB;font-size:11px;font-weight:1000;color:#0F172A;background:#FAFBFC;display:flex;align-items:center;gap:5px;margin:0;">
        <span style="color:#EF233C;font-weight:1000;">2.</span> 
        <span style="color:#EF233C;font-weight:1000;">Condiciones Comerciales</span>
        <span style="font-size:8px;color:#DC2626;font-weight:700;margin-left:auto;">* Campos obligatorios</span>
    </h3>
    <div class="body" style="padding:6px 8px;">
        <!-- Asesor | Email | Teléfono -->
        <div style="display:grid;grid-template-columns:1fr 1.5fr 1fr;gap:4px;margin-bottom:2px;">
            <div class="form-field">
                <label style="display:block;font-size:7.5px;font-weight:950;color:#334155;margin-bottom:1px;text-transform:uppercase;">Asesor</label>
                <input id="fVendedor" value="${CONFIG.asesorDefault}" style="width:100%;height:22px;border:1px solid #E5E7EB;border-radius:5px;background:#FFFFFF;outline:none;color:#0F172A;font-size:10px;padding:0 5px;">
            </div>
            <div class="form-field">
                <label style="display:block;font-size:7.5px;font-weight:950;color:#334155;margin-bottom:1px;text-transform:uppercase;">Email Asesor</label>
                <input id="fEmailAsesor" value="${CONFIG.emailAsesorDefault}" style="width:100%;height:22px;border:1px solid #E5E7EB;border-radius:5px;background:#FFFFFF;outline:none;color:#0F172A;font-size:10px;padding:0 5px;">
            </div>
            <div class="form-field">
                <label style="display:block;font-size:7.5px;font-weight:950;color:#334155;margin-bottom:1px;text-transform:uppercase;">Teléfono Asesor</label>
                <input id="fTelefonoAsesor" value="${CONFIG.telefonoAsesorDefault}" style="width:100%;height:22px;border:1px solid #E5E7EB;border-radius:5px;background:#FFFFFF;outline:none;color:#0F172A;font-size:10px;padding:0 5px;">
            </div>
        </div>
        <!-- Moneda | Condición Pago | Tiempo Entrega -->
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px;margin-bottom:2px;">
            <div class="form-field">
                <label style="display:block;font-size:7.5px;font-weight:950;color:#334155;margin-bottom:1px;text-transform:uppercase;">Moneda</label>
                <select id="fMoneda" style="width:100%;height:22px;border:1px solid #E5E7EB;border-radius:5px;background:#FFFFFF;outline:none;color:#0F172A;font-size:10px;padding:0 3px;">
                    <option value="Soles (S/.)" selected>Soles (S/.)</option>
                    <option value="Dólares ($)">Dólares ($)</option>
                </select>
            </div>
            <div class="form-field">
                <label style="display:block;font-size:7.5px;font-weight:950;color:#334155;margin-bottom:1px;text-transform:uppercase;">Condición de Pago <span style="color:#DC2626;font-weight:900;">*</span></label>
                <select id="fCondicion" onchange="toggleCustomField('fCondicion','fCondicionCustom')" style="width:100%;height:22px;border:1px solid #E5E7EB;border-radius:5px;background:#FFFFFF;outline:none;color:#0F172A;font-size:10px;padding:0 3px;border-left:3px solid #DC2626;">
                    <option value="" selected>-- Elegir --</option>
                    <option value="Contado">Contado</option>
                    <option value="Contra entrega">Contra entrega</option>
                    <option value="Crédito 7 días">Crédito 7 días</option>
                    <option value="Crédito 15 días">Crédito 15 días</option>
                    <option value="Crédito 30 días">Crédito 30 días</option>
                    <option value="Crédito 45 días">Crédito 45 días</option>
                    <option value="Crédito 60 días">Crédito 60 días</option>
                    <option value="Crédito 90 días">Crédito 90 días</option>
                    <option value="Crédito 120 días">Crédito 120 días</option>
                    <option value="Personalizado">✏️ Personalizado...</option>
                </select>
                <input id="fCondicionCustom" placeholder="Ej: 50% anticipo, 50% contra entrega" style="display:none;margin-top:1px;width:100%;height:20px;border:1px solid #E5E7EB;border-radius:4px;background:#FFFFFF;outline:none;color:#0F172A;font-size:9px;padding:0 5px;border-left:3px solid #DC2626;" value="Personalizado">
            </div>
            <div class="form-field">
                <label style="display:block;font-size:7.5px;font-weight:950;color:#334155;margin-bottom:1px;text-transform:uppercase;">Tiempo de Entrega <span style="color:#DC2626;font-weight:900;">*</span></label>
                <select id="fTiempo" onchange="toggleCustomField('fTiempo','fTiempoCustom')" style="width:100%;height:22px;border:1px solid #E5E7EB;border-radius:5px;background:#FFFFFF;outline:none;color:#0F172A;font-size:10px;padding:0 3px;border-left:3px solid #DC2626;">
                    <option value="" selected>-- Elegir --</option>
                    <option value="Inmediata">Inmediata</option>
                    <option value="1 día hábil">1 día hábil</option>
                    <option value="2 días hábiles">2 días hábiles</option>
                    <option value="3 días hábiles">3 días hábiles</option>
                    <option value="5 días hábiles" >5 días hábiles</option>
                    <option value="7 días hábiles">7 días hábiles</option>
                    <option value="10 días hábiles">10 días hábiles</option>
                    <option value="15 días hábiles">15 días hábiles</option>
                    <option value="Personalizado">✏️ Personalizado...</option>
                </select>
                <input id="fTiempoCustom" placeholder="Ej: 10 días" style="display:none;margin-top:1px;width:100%;height:20px;border:1px solid #E5E7EB;border-radius:4px;background:#FFFFFF;outline:none;color:#0F172A;font-size:9px;padding:0 5px;border-left:3px solid #DC2626;">
            </div>
        </div>
        <!-- Validez Oferta | Dirección de Entrega -->
        <div style="display:grid;grid-template-columns:1fr 1.5fr;gap:4px;margin-bottom:2px;">
            <div class="form-field">
                <label style="display:block;font-size:7.5px;font-weight:950;color:#334155;margin-bottom:1px;text-transform:uppercase;">Validez de Oferta</label>
                <select id="fValidez" onchange="toggleCustomField('fValidez','fValidezCustom')" style="width:100%;height:22px;border:1px solid #E5E7EB;border-radius:5px;background:#FFFFFF;outline:none;color:#0F172A;font-size:10px;padding:0 3px;">
                    <option value="7 días" selected>7 días</option>
                    <option value="15 días">15 días</option>
                    <option value="30 días">30 días</option>
                    <option value="45 días">45 días</option>
                    <option value="60 días">60 días</option>
                    <option value="Personalizado">✏️ Personalizado...</option>
                </select>
                <input id="fValidezCustom" placeholder="Ej: 20 días" style="display:none;margin-top:1px;width:100%;height:20px;border:1px solid #E5E7EB;border-radius:4px;background:#FFFFFF;outline:none;color:#0F172A;font-size:9px;padding:0 5px;">
            </div>
            <div class="form-field">
                <label style="display:block;font-size:7.5px;font-weight:950;color:#334155;margin-bottom:1px;text-transform:uppercase;">Dirección de Entrega</label>
                <div style="display:flex;gap:4px;align-items:center;">
                    <select id="fDireccionEntrega" style="flex:1;height:22px;border:1px solid #E5E7EB;border-radius:5px;background:#FFFFFF;outline:none;color:#0F172A;font-size:10px;padding:0 3px;" onchange="mostrarSubDireccionRecogo(this.value)">
                        <option value="">-- Seleccione --</option>
                        <option value="direccion_recogo">📦 Dirección de Recogo</option>
                        <option value="Personalizado">✏️ Personalizado...</option>
                    </select>
                    <span id="sedeSeleccionadaLabel" style="display:none;font-size:9px;font-weight:800;color:#2563EB;background:#DBEAFE;padding:2px 10px;border-radius:4px;white-space:nowrap;"></span>
                </div>
                <div id="subDireccionRecogo" style="display:none;margin-top:3px;">
                    <select id="fSubDireccionRecogo" style="width:100%;height:22px;border:1px solid #E5E7EB;border-radius:5px;background:#FFFFFF;outline:none;color:#0F172A;font-size:10px;padding:0 3px;" onchange="actualizarDireccionRecogo(this.value)">
                        <option value="">-- Seleccione Sede --</option>
                        <option value="JR. LAS ALMENDRAS VERDES NRO. 284 URB. VIRGEN DEL ROSARIO LIMA - LIMA - SAN MARTIN DE PORRES">📍 San Martin de Porres</option>
                        <option value="AV. BRASIL NRO. 1234 URB. BREÑA LIMA - LIMA - BREÑA">📍 Breña</option>
                        <option value="Personalizado">✏️ Personalizado...</option>
                    </select>
                    <input id="fSubDireccionRecogoCustom" placeholder="Escribe la dirección..." style="display:none;margin-top:3px;width:100%;height:20px;border:1px solid #E5E7EB;border-radius:4px;background:#FFFFFF;outline:none;color:#0F172A;font-size:9px;padding:0 5px;">
                </div>
                <input id="fDireccionEntregaCustom" placeholder="Ej: Av. Los Alamos 123" style="display:none;margin-top:1px;width:100%;height:20px;border:1px solid #E5E7EB;border-radius:4px;background:#FFFFFF;outline:none;color:#0F172A;font-size:9px;padding:0 5px;">
            </div>
        </div>
        <!-- Nota Comercial -->
        <div style="display:grid;grid-template-columns:1fr;gap:3px;">
            <div class="form-field">
                <label style="display:block;font-size:7.5px;font-weight:950;color:#334155;margin-bottom:1px;text-transform:uppercase;">Nota Comercial</label>
                <input id="fNotaComercial" placeholder="Comentarios comerciales..." style="width:100%;height:22px;border:1px solid #E5E7EB;border-radius:5px;background:#FFFFFF;outline:none;color:#0F172A;font-size:10px;padding:0 5px;">
            </div>
        </div>
    </div>
</div>
    <!-- ============================================================ -->
    <!-- 3. RESUMEN - ESTILO IMAGEN (con orden corregido)            -->
    <!-- ============================================================ -->
    <div class="create-panel summary-card" style="background:#FFFFFF;border:1px solid #E5E7EB;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,.05);overflow:hidden;max-width:500px;font-family:'Segoe UI',Roboto,sans-serif;">
        
        <!-- Título "3. Resumen" -->
        <div style="padding:5px 10px;border-bottom:1px solid #E5E7EB;background:#FAFAFA;display:flex;align-items:center;gap:5px;">
            <span style="color:#D32F2F;font-weight:700;font-size:10px;">3.</span>
            <span style="color:#D32F2F;font-weight:700;font-size:10px;">Resumen</span>
        </div>
        
        <!-- Cuerpo del resumen -->
        <div style="padding:6px 10px 8px 10px;">
            
            <!-- FILA: Subtotal -->
            <div style="display:flex;justify-content:space-between;align-items:center;padding:2px 0;border-bottom:1px solid #F0F0F0;">
                <span style="font-size:9.5px;color:#444;font-weight:500;">Subtotal</span>
                <span id="sumSubtotal" style="font-size:10px;font-weight:600;color:#1E1E1E;">S/ 0.00</span>
            </div>
            
            <!-- FILA: IGV 18% -->
            <div style="display:flex;justify-content:space-between;align-items:center;padding:2px 0;border-bottom:1px solid #F0F0F0;">
                <span style="font-size:9.5px;color:#444;font-weight:500;">IGV 18%</span>
                <span id="sumIgv" style="font-size:10px;font-weight:600;color:#1E1E1E;">S/ 0.00</span>
            </div>
            
            <!-- FILA: Descuento + input + select -->
            <div style="display:flex;justify-content:space-between;align-items:center;padding:2px 0;border-bottom:1px solid #F0F0F0;">
                <span style="font-size:9.5px;color:#444;font-weight:500;">Descuento</span>
                <div style="display:flex;align-items:center;gap:3px;">
                    <input id="fDiscountValue" type="number" value="0" step="0.01" style="width:50px;height:18px;border:1px solid #CCC;border-radius:4px;padding:0 3px;text-align:right;font-weight:600;font-size:9.5px;background:#FFF;">
                    <select id="fDiscountType" style="height:18px;border-radius:4px;border:1px solid #CCC;font-weight:600;font-size:9px;background:#FFF;padding:0 3px;" onchange="calcQuote()">
                        <option value="%">%</option>
                        <option value="S/">S/</option>
                    </select>
                </div>
            </div>
            
            <!-- FILA: Dscto aplicado -->
            <div style="display:flex;justify-content:space-between;align-items:center;padding:2px 0;border-bottom:1px solid #F0F0F0;">
                <span style="font-size:9.5px;color:#444;font-weight:500;">Dscto aplicado</span>
                <span id="sumDiscount" style="font-size:10px;font-weight:600;color:#D32F2F;">-S/ 0.00</span>
            </div>
            
            <!-- ============================================================ -->
            <!-- 🔽 FILA: Valor venta (MOVIDA AQUÍ, DEBAJO DE "Dscto aplicado") -->
            <!-- ============================================================ -->
            <div style="display:flex;justify-content:space-between;align-items:center;padding:2px 0;border-bottom:1px solid #F0F0F0;">
                <span style="font-size:9.5px;color:#444;font-weight:500;">Valor Venta Total</span>
                <span id="sumValorVenta" style="font-size:10px;font-weight:600;color:#1E1E1E;">S/ 0.00</span>
            </div>
            
            <!-- TOTAL -->
            <div style="display:flex;justify-content:space-between;align-items:center;padding:5px 0 0 0;margin-top:2px;border-top:2px solid #D32F2F;">
                <span style="font-size:11px;font-weight:700;color:#1E1E1E;">TOTAL A PAGAR</span>
                <span id="sumTotal" style="font-size:15px;font-weight:800;color:#D32F2F;">S/ 0.00</span>
            </div>
            
        </div>
    </div>

</div> <!-- 🔴 CIERRE DEL GRID DE 3 COLUMNAS -->

<!-- ============================================================ -->
<!-- FILA INFERIOR: 4. PRODUCTOS COTIZADOS (OCUPA TODO EL ANCHO) -->
<!-- ============================================================ -->
<div class="create-panel product-wide" style="background:#FFFFFF;border:1px solid #E5E7EB;border-radius:12px;box-shadow:0 4px 12px rgba(15,23,42,.06);overflow:hidden;margin-bottom:10px;">
    <h3 style="padding:8px 14px;border-bottom:1px solid #E5E7EB;font-size:13px;font-weight:1000;color:#0F172A;background:#FAFBFC;display:flex;align-items:center;gap:8px;margin:0;flex-wrap:wrap;">
        <span style="color:#EF233C;font-weight:1000;">4.</span> 
        <span style="color:#EF233C;font-weight:1000;">Productos Cotizados</span>
        <span style="display:flex;align-items:center;gap:8px;margin-left:auto;flex-wrap:wrap;">
            <input id="quickProductSearch" placeholder="Buscar producto por código..." style="width:200px;height:30px;border:1px solid #CBD5E1;border-radius:8px;padding:0 10px;font-size:11px;font-weight:850;outline:none;">

            <button onclick="openProductSelector()" style="height:30px;padding:0 12px;font-size:11px;border-radius:8px;font-weight:1000;background:#8B5CF6;color:#fff;border:0;cursor:pointer;">📋 Seleccionar Producto </button>
        </span>
    </h3>
    <div class="body" style="padding:0;">
        <div style="overflow:auto;max-height:220px;">
            <table style="width:100%;border-collapse:collapse;font-size:10px;min-width:1100px;">
                <thead>
                    <tr>
                        <th style="padding:5px 6px;font-size:9px;background:#FFF1F2;color:#7F1D1D;border:1px solid #FCA5A5;text-align:center;font-weight:1000;width:35px;">Item</th>
                        <th style="padding:5px 6px;font-size:9px;background:#FFF1F2;color:#7F1D1D;border:1px solid #FCA5A5;text-align:center;font-weight:1000;width:80px;">Código Producto</th>
                        <th style="padding:5px 6px;font-size:9px;background:#FFF1F2;color:#7F1D1D;border:1px solid #FCA5A5;text-align:center;font-weight:1000;"> Descripción</th>
                        <th style="padding:5px 6px;font-size:9px;background:#FFF1F2;color:#7F1D1D;border:1px solid #FCA5A5;text-align:center;font-weight:1000;width:80px;">Modelo</th>
                        <th style="padding:5px 6px;font-size:9px;background:#FFF1F2;color:#7F1D1D;border:1px solid #FCA5A5;text-align:center;font-weight:1000;width:75px;">Marca</th>
                        <th style="padding:5px 6px;font-size:9px;background:#FFF1F2;color:#7F1D1D;border:1px solid #FCA5A5;text-align:center;font-weight:1000;width:55px;">Unidad</th>
                        <th style="padding:5px 6px;font-size:9px;background:#FFF1F2;color:#7F1D1D;border:1px solid #FCA5A5;text-align:center;font-weight:1000;width:50px;">Cant</th>
                        <th style="padding:5px 6px;font-size:9px;background:#FFF1F2;color:#7F1D1D;border:1px solid #FCA5A5;text-align:center;font-weight:1000;width:90px;">Valor Venta Unitario S/.</th>
                        <th style="padding:5px 6px;font-size:9px;background:#FFF1F2;color:#7F1D1D;border:1px solid #FCA5A5;text-align:center;font-weight:1000;width:100px;">Valor Total S/.</th>
                        <th style="padding:5px 6px;font-size:9px;background:#FFF1F2;color:#7F1D1D;border:1px solid #FCA5A5;text-align:center;font-weight:1000;width:55px;">Stock</th>
                        <th style="padding:5px 6px;font-size:9px;background:#FFF1F2;color:#7F1D1D;border:1px solid #FCA5A5;text-align:center;font-weight:1000;width:70px;">Estado entrega</th>
                        <th style="padding:5px 6px;font-size:9px;background:#FFF1F2;color:#7F1D1D;border:1px solid #FCA5A5;text-align:center;font-weight:1000;width:40px;">Acciones </th>
                    </tr>
                </thead>
                <tbody id="quoteProductRows">
                    <tr><td colspan="12" style="text-align:center;color:#94A3B8;padding:20px;font-size:11px;">📭 Agregue productos a la cotización</td></tr>
                </tbody>
            </table>
        </div>
    </div>
</div>

<!-- ============================================================ -->
<!-- 5. INFORMACIÓN ADICIONAL -->
<!-- ============================================================ -->
<div class="create-panel" style="background:#FFFFFF;border:1px solid #E5E7EB;border-radius:12px;box-shadow:0 4px 12px rgba(15,23,42,.06);overflow:hidden;margin-bottom:10px; max-width: 100%; flex: 1; grid-column: 1 / -1;">
    <h3 style="padding:6px 12px;border-bottom:1px solid #E5E7EB;font-size:12px;font-weight:1000;color:#0F172A;background:#FAFBGC;display:flex;align-items:center;gap:6px;margin:0;">
        <span style="color:#EF233C;font-weight:1000;">5.</span> 
        <span style="color:#EF233C;font-weight:1000;">Información adicional</span>
        <span style="font-weight:400;font-size:8px;color:#64748B;margin-left:4px;">- interno</span>
    </h3>
    <div class="body" style="padding:8px 12px;">
        
        <!-- FILA ÚNICA: Seguimiento | Motivo | Transporte | Parihuela | Nota interna -->
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr 1fr;gap:8px;">
            <!-- Seguimiento -->
            <div class="form-field">
                <label style="display:block;font-size:8.5px;font-weight:950;color:#334155;margin-bottom:1px;text-transform:uppercase;">Seguimiento</label>
                <input id="fSeguimiento" value="Helen Blas Príncipe" 
                       style="width:100%;height:28px;border:1px solid #E5E7EB;border-radius:6px;background:#FFFFFF;outline:none;color:#0F172A;font-size:11px;padding:0 8px;">
            </div>
            
            <!-- Motivo -->
            <div class="form-field">
                <label style="display:block;font-size:8.5px;font-weight:950;color:#334155;margin-bottom:1px;text-transform:uppercase;">Motivo</label>
                <select id="fMotivo" 
                        style="width:100%;height:28px;border:1px solid #E5E7EB;border-radius:6px;background:#FFFFFF;outline:none;color:#0F172A;font-size:11px;padding:0 4px;">
                    <option value="Proyecto nuevo">Proyecto nuevo</option>
                    <option value="Recompra">Recompra</option>
                    <option value="Licitación">Licitación</option>
                    <option value="Reposición / stock">Reposición / stock</option>
                    <option value="Solicitud única del cliente" selected>Solicitud única del cliente</option>
                </select>
            </div>
            
            <!-- Transporte -->
            <div class="form-field">
                <label style="display:block;font-size:8.5px;font-weight:950;color:#334155;margin-bottom:1px;text-transform:uppercase;">Transporte <span style="color:#DC2626;font-weight:900;">*</span></label>
                <select id="fTransporte" 
                        style="width:100%;height:28px;border:1px solid #E5E7EB;border-left:3px solid #DC2626;border-radius:6px;background:#FFFFFF;outline:none;color:#0F172A;font-size:11px;padding:0 4px;">
                    <option value="Seleccione" selected>-- Seleccione --</option>
                    <option value="Motorizado">Motorizado</option>
                    <option value="Auto">Auto</option>
                    <option value="Minivan">Minivan</option>
                    <option value="Camioneta">Camioneta</option>
                    <option value="Camión">Camión</option>
                    <option value="Agencia">Agencia</option>
                </select>
            </div>
            
            <!-- Parihuela -->
            <div class="form-field">
                <label style="display:block;font-size:8.5px;font-weight:950;color:#334155;margin-bottom:1px;text-transform:uppercase;">Parihuela <span style="color:#DC2626;font-weight:900;">*</span></label>
                <select id="fParihuela" 
                        style="width:100%;height:28px;border:1px solid #E5E7EB;border-left:3px solid #DC2626;border-radius:6px;background:#FFFFFF;outline:none;color:#0F172A;font-size:11px;padding:0 4px;">
                    <option value="Seleccione" selected>-- Seleccione --</option>
                    <option value="No">No</option>
                    <option value="Sí - estándar">Sí - estándar</option>
                    <option value="Sí - a medida">Sí - a medida</option>
                    <option value="Por confirmar">Por confirmar</option>
                </select>
            </div>
            
            <!-- Nota interna -->
            <div class="form-field">
                <label style="display:block;font-size:8.5px;font-weight:950;color:#334155;margin-bottom:1px;text-transform:uppercase;">Nota interna</label>
                <input id="fNotaInterna" placeholder="" value="" 
                       style="width:100%;height:28px;border:1px solid #E5E7EB;border-radius:6px;background:#FFFFFF;outline:none;color:#0F172A;font-size:11px;padding:0 8px;">
            </div>
        </div>
        
    </div>
</div>

        
    `;
}
/**
 * Muestra/oculta el sub-select de Dirección de Recogo, el input personalizado
 * o el label azul según la opción elegida en el select principal.
 * ✅ Versión unificada - maneja los 3 casos
 */
function mostrarSubDireccionRecogo(valor) {
    console.log('🔄 mostrarSubDireccionRecogo - valor:', valor);
    
    const customInput   = document.getElementById('fDireccionEntregaCustom');
    const sedeLabel     = document.getElementById('sedeSeleccionadaLabel');
    const subContainer  = document.getElementById('subDireccionRecogo');
    const subSelect     = document.getElementById('fSubDireccionRecogo');
    const subCustom     = document.getElementById('fSubDireccionRecogoCustom');
    
    // ============================================================
    // 1. OCULTAR TODO PRIMERO
    // ============================================================
    if (customInput)  { customInput.style.display  = 'none'; customInput.value = ''; }
    if (subContainer) { subContainer.style.display = 'none'; }
    if (subCustom)    { subCustom.style.display    = 'none'; subCustom.value   = ''; }
    if (sedeLabel)    { sedeLabel.style.display    = 'none'; sedeLabel.textContent = ''; }
    if (subSelect)    { subSelect.value = ''; }
    
    // ============================================================
    // 2. "Dirección de Recogo" → MOSTRAR SUB-SELECT
    // ============================================================
    if (valor === 'direccion_recogo') {
        console.log('✅ Mostrando sub-select de Dirección de Recogo');
        if (subContainer) subContainer.style.display = 'block';
        return;
    }
    
    // ============================================================
    // 3. "Personalizado" → MOSTRAR INPUT PERSONALIZADO
    // ============================================================
    if (valor === 'Personalizado') {
        console.log('✅ Mostrando input personalizado');
        if (customInput) {
            customInput.style.display = 'block';
            customInput.focus();
        }
        return;
    }
    
    // ============================================================
    // 4. Una dirección del cliente → MOSTRAR LABEL AZUL
    // ============================================================
    if (valor && valor !== '') {
        console.log('✅ Mostrando label de dirección seleccionada');
        if (sedeLabel) {
            const labelCorto = valor.length > 45 ? valor.substring(0, 45) + '...' : valor;
            sedeLabel.textContent = `📍 ${labelCorto}`;
            sedeLabel.style.display = 'inline-block';
        }
    }
    
    // Si valor está vacío, ya se ocultó todo en el paso 1
}


function actualizarDireccionRecogo(valor) {
    console.log('🔄 actualizarDireccionRecogo - valor recibido:', valor);
    
    const mainSelect = document.getElementById('fDireccionEntrega');
    const subContainer = document.getElementById('subDireccionRecogo');
    const subCustom = document.getElementById('fSubDireccionRecogoCustom');
    const sedeLabel = document.getElementById('sedeSeleccionadaLabel');
    
    if (!mainSelect) return;
    
    // Función para obtener el nombre corto de la sede
    function getNombreSede(direccion) {
        if (direccion.includes('SAN MARTIN DE PORRES')) return '📍 San Martin de Porres';
        if (direccion.includes('BREÑA')) return '📍 Breña';
        return direccion;
    }
    
    // Si es "Personalizado", mostrar el input personalizado del sub
    if (valor === 'Personalizado') {
        if (subCustom) {
            subCustom.style.display = 'block';
            subCustom.focus();
        }
        // Mantener el main select en 'direccion_recogo' mientras escribe
        mainSelect.value = 'direccion_recogo';
        if (sedeLabel) {
            sedeLabel.style.display = 'none';
            sedeLabel.textContent = '';
        }
        return;
    }
    
    // Si tiene un valor válido (sede seleccionada)
    if (valor && valor !== '') {
        // Mantener el main select en 'direccion_recogo'
        mainSelect.value = 'direccion_recogo';
        console.log('✅ Sede seleccionada:', valor);
        
        // Guardar la dirección seleccionada en un atributo data
        mainSelect.dataset.direccionSeleccionada = valor;
        
        // ✅ MOSTRAR LA SEDE SELECCIONADA EN EL LABEL
        if (sedeLabel) {
            const nombreSede = getNombreSede(valor);
            sedeLabel.textContent = `📍 ${nombreSede}`;
            sedeLabel.style.display = 'inline-block';
        }
        
        // Ocultar el input personalizado del sub
        if (subCustom) {
            subCustom.style.display = 'none';
            subCustom.value = '';
        }
        
        // ✅ OCULTAR EL SUB-CONTAINER DESPUÉS DE SELECCIONAR
        if (subContainer) {
            subContainer.style.display = 'none';
        }
    }
}

function getDireccionEntregaValue() {
    const mainSelect = document.getElementById('fDireccionEntrega');
    const customInput = document.getElementById('fDireccionEntregaCustom');
    
    if (!mainSelect) return '';
    
    const valor = mainSelect.value;
    console.log('🔍 getDireccionEntregaValue - valor del select:', valor);
    
    // Si es Personalizado, usar el input personalizado
    if (valor === 'Personalizado') {
        return customInput ? customInput.value.trim() : '';
    }
    
    // Si tiene valor seleccionado, devolverlo
    if (valor && valor !== '') {
        return valor;
    }
    
    return '';
}

// Función para cargar una dirección existente en el formulario
function cargarDireccionEntregaExistente(direccion) {
    if (!direccion || direccion === '') return;
    
    console.log('📥 Cargando dirección existente:', direccion);
    
    const mainSelect = document.getElementById('fDireccionEntrega');
    const subSelect = document.getElementById('fSubDireccionRecogo');
    const customInput = document.getElementById('fDireccionEntregaCustom');
    const subCustom = document.getElementById('fSubDireccionRecogoCustom');
    const subContainer = document.getElementById('subDireccionRecogo');
    const sedeLabel = document.getElementById('sedeSeleccionadaLabel');
    
    if (!mainSelect) return;
    
    // Función para obtener el nombre corto de la sede
    function getNombreSede(dir) {
        if (dir.includes('SAN MARTIN DE PORRES')) return '📍 San Martin de Porres';
        if (dir.includes('BREÑA')) return '📍 Breña';
        return dir;
    }
    
    // Definir las sedes
    const sedeSanMartin = 'JR. LAS ALMENDRAS VERDES NRO. 284 URB. VIRGEN DEL ROSARIO LIMA - LIMA - SAN MARTIN DE PORRES';
    const sedeBrena = 'AV. BRASIL NRO. 1234 URB. BREÑA LIMA - LIMA - BREÑA';
    
    // Verificar si es una sede
    if (direccion === sedeSanMartin || direccion === sedeBrena) {
        // Es una sede, seleccionar "direccion_recogo" y guardar la dirección
        mainSelect.value = 'direccion_recogo';
        mainSelect.dataset.direccionSeleccionada = direccion;
        if (subSelect) {
            subSelect.value = direccion;
        }
        // ✅ MOSTRAR LA SEDE EN EL LABEL
        if (sedeLabel) {
            sedeLabel.textContent = `📍 ${getNombreSede(direccion)}`;
            sedeLabel.style.display = 'inline-block';
        }
        // Ocultar el sub-container
        if (subContainer) {
            subContainer.style.display = 'none';
        }
        console.log('✅ Cargada sede:', direccion);
    } 
    // Verificar si es la opción de recogo sin sede específica
    else if (direccion === 'direccion_recogo' || direccion.includes('Recogo')) {
        mainSelect.value = 'direccion_recogo';
        delete mainSelect.dataset.direccionSeleccionada;
        if (sedeLabel) {
            sedeLabel.style.display = 'none';
            sedeLabel.textContent = '';
        }
        if (subContainer) {
            subContainer.style.display = 'block';
        }
        console.log('✅ Cargada opción de recogo');
    }
    // Verificar si está en las opciones del select principal (Personalizado o directa)
    else {
        let found = false;
        for (let opt of mainSelect.options) {
            if (opt.value === direccion) {
                opt.selected = true;
                found = true;
                break;
            }
        }
        if (!found) {
            // No está en las opciones, usar personalizado
            mainSelect.value = 'Personalizado';
            if (customInput) {
                customInput.value = direccion;
                customInput.style.display = 'block';
            }
            if (sedeLabel) {
                sedeLabel.style.display = 'none';
                sedeLabel.textContent = '';
            }
            console.log('✅ Cargada dirección personalizada:', direccion);
        } else {
            console.log('✅ Cargada dirección directa:', direccion);
        }
    }
}





/**
 * Carga las direcciones de entrega del cliente en el desplegable
 * @param {Object} cliente - Datos del cliente con puntos_entrega
 */
function cargarDireccionesClienteEnSelect(cliente) {
    const select = document.getElementById('fDireccionEntrega');
    if (!select) return;
    
    // Limpiar opciones actuales
    select.innerHTML = '<option value="">-- Seleccione --</option>';
    
    // Array de direcciones únicas
    const direcciones = [];
    
    // 1. Agregar la dirección fiscal (si existe)
    if (cliente.direccion_fiscal && cliente.direccion_fiscal.trim()) {
        direcciones.push({
            valor: cliente.direccion_fiscal.trim(),
            label: `🏢 ${cliente.direccion_fiscal.trim()}`,
            tipo: 'fiscal'
        });
    }
    
    // 2. Agregar los puntos de entrega
    if (cliente.puntos_entrega && cliente.puntos_entrega.length > 0) {
        cliente.puntos_entrega.forEach((punto, idx) => {
            const dir = punto.direccion ? punto.direccion.trim() : '';
            if (dir) {
                // Evitar duplicados con la dirección fiscal
                const yaExiste = direcciones.some(d => d.valor === dir);
                if (!yaExiste) {
                    const nombre = punto.punto || punto.nombre_punto || `Punto ${idx + 1}`;
                    const esPrincipal = punto.principal ? ' ⭐' : '';
                    direcciones.push({
                        valor: dir,
                        label: `📍 ${nombre}${esPrincipal} - ${dir}`,
                        tipo: 'punto'
                    });
                }
            }
        });
    }
    
    // 3. Agregar opción personalizada
    direcciones.push({
        valor: 'Personalizado',
        label: '✏️ Ingresar dirección personalizada...',
        tipo: 'custom'
    });
    
    // Si no hay direcciones, al menos dejar el personalizado
    if (direcciones.length === 1) {
        select.innerHTML = '<option value="">-- El cliente no tiene direcciones registradas --</option>' +
                          '<option value="Personalizado">✏️ Ingresar dirección personalizada...</option>';
        return;
    }
    
    // Renderizar opciones
    direcciones.forEach(d => {
        const opt = document.createElement('option');
        opt.value = d.valor;
        opt.textContent = d.label;
        opt.dataset.tipo = d.tipo;
        select.appendChild(opt);
    });
    
    // Si hay una sola dirección (sin contar personalizado), seleccionarla automáticamente
    const opcionesReales = direcciones.filter(d => d.tipo !== 'custom');
    if (opcionesReales.length === 1) {
        select.value = opcionesReales[0].valor;
        // Disparar el evento por si acaso
        select.dispatchEvent(new Event('change'));
    }
    
    console.log(`✅ ${opcionesReales.length} direcciones cargadas para el cliente`);
}
// ============================================================
// MOSTRAR/OCULTAR CAMPOS DE PAGO (Contado)
// ============================================================

function togglePagoCampos() {
    const condicionSelect = document.getElementById('pcCondicion');
    const container = document.getElementById('pagoCamposContainer');
    
    console.log('🔄 togglePagoCampos ejecutándose');
    console.log('  - condicionSelect:', condicionSelect);
    console.log('  - container:', container);
    console.log('  - valor seleccionado:', condicionSelect ? condicionSelect.value : 'no existe');
    
    if (!condicionSelect || !container) {
        console.warn('⚠️ togglePagoCampos: Elementos no encontrados');
        return;
    }
    
    // Mostrar solo cuando la condición es "Contado"
    if (condicionSelect.value === 'Contado') {
        container.style.display = 'block';
        container.style.animation = 'fadeIn 0.3s ease';
        console.log('✅ Mostrando campos de pago (Contado)');
    } else {
        container.style.display = 'none';
        // Limpiar campos al ocultar
        const numOp = document.getElementById('pcNumOperacion');
        const banco = document.getElementById('pcBanco');
        const cuenta = document.getElementById('pcCuentaOCCI');
        if (numOp) numOp.value = '';
        if (banco) banco.value = '';
        if (cuenta) cuenta.value = '';
        console.log('⬜ Ocultando campos de pago');
    }
}

// Función para obtener los datos de pago (para usar al guardar)
function getPagoData() {
    const condicion = document.getElementById('pcCondicion')?.value || '';
    if (condicion !== 'Contado') {
        return {
            num_operacion: '',
            banco: '',
            cuenta_occi: ''
        };
    }
    
    return {
        num_operacion: document.getElementById('pcNumOperacion')?.value || '',
        banco: document.getElementById('pcBanco')?.value || '',
        cuenta_occi: document.getElementById('pcCuentaOCCI')?.value || ''
    };
}

// Función para establecer datos de pago al editar (si vienen de la BD)
function setPagoData(data) {
    if (!data) return;
    
    const condicion = document.getElementById('pcCondicion')?.value || '';
    if (condicion === 'Contado') {
        document.getElementById('pcNumOperacion').value = data.num_operacion || '';
        document.getElementById('pcBanco').value = data.banco || '';
        document.getElementById('pcCuentaOCCI').value = data.cuenta_occi || '';
    }
}

// Inicializar al cargar el modal
function inicializarPagoCampos() {
    // Esperar a que el DOM esté listo
    setTimeout(() => {
        togglePagoCampos();
    }, 100);
}

// Agregar animación fadeIn
const stylePago = document.createElement('style');
stylePago.textContent = `
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(-8px); }
        to { opacity: 1; transform: translateY(0); }
    }
`;
document.head.appendChild(stylePago);
// ============================================================
// FUNCIÓN PARA ABRIR MODAL DE COTIZACIÓN - EXPORTADA AL WINDOW
// ============================================================

window.openCotizacionModal = function(id = null) {
    console.log('📋 Abriendo modal de cotización', { id });
    editingId = id;  // 🔑 Guardar el ID para edición
    const isEdit = id !== null;
    
    const modal = document.getElementById('cotizacionModal');
    if (!modal) {
        console.error('❌ Modal #cotizacionModal no encontrado');
        showToast('Error: Modal de cotización no disponible', 'error');
        return;
    }
    
    const body = document.getElementById('cotizacionForm');
    if (!body) {
        console.error('❌ #cotizacionForm no encontrado');
        showToast('Error: Formulario no disponible', 'error');
        return;
    }
    
    quoteProducts = [];
    cotizacionSeleccionada = null;
    
    const title = document.getElementById('cotizacionModalTitle');
    if (title) {
        title.textContent = isEdit ? '✏️ Editar cotización' : '📄 Nueva cotización';
    }
    
    body.innerHTML = renderCotizacionFormContent(isEdit);
    renderCotizacionFooter(isEdit);
    inicializarEventosCotizacion(isEdit);
    
    if (isEdit) {
        // 🔑 CARGAR LA COTIZACIÓN PARA EDITAR
        setTimeout(() => {
            cargarCotizacionParaEditar(id);
        }, 100);
    } else {
        const now = new Date();
        now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
        const fechaStr = now.toISOString().slice(0, 16);
        document.getElementById('fFecha')?.setAttribute('value', fechaStr);
        document.getElementById('fVendedor')?.setAttribute('value', CONFIG.asesorDefault);
    }
    
    modal.classList.add('show');
    console.log('✅ Modal de cotización abierto correctamente');
};

// ============================================================
// BUSCADOR DE COTIZACIONES CON AUTOCOMPLETADO
// ============================================================

// Variable para almacenar el temporizador de búsqueda
let cotizacionSearchTimer = null;
// Variable para almacenar la cotización seleccionada
let cotizacionSeleccionada = null;

function buscarCotizacionSAP(query) {
    const resultsContainer = document.getElementById('cotizacionSearchResults');
    const searchInput = document.getElementById('pcCotSearch');
    
    // Limpiar timer anterior
    if (cotizacionSearchTimer) {
        clearTimeout(cotizacionSearchTimer);
        cotizacionSearchTimer = null;
    }
    
    const q = (query || '').trim();
    
    if (!q || q.length < 2) {
        resultsContainer.style.display = 'none';
        resultsContainer.innerHTML = '';
        return;
    }
    
    // Mostrar loading
    resultsContainer.innerHTML = `<div style="padding:12px 16px; color:#94A3B8; font-weight:850; text-align:center;">⏳ Buscando cotizaciones...</div>`;
    resultsContainer.style.display = 'block';
    
    // Buscar con debounce
    cotizacionSearchTimer = setTimeout(() => {
        // Buscar en cotizacionesData (cargado desde la API)
        const results = cotizacionesData.filter(c => {
            const searchStr = `${c.numero || ''} ${c.razon || ''} ${c.ruc || ''} ${c.descripcion || ''} ${c.cod_cliente || ''}`.toLowerCase();
            return searchStr.includes(q.toLowerCase());
        });
        
        if (results.length === 0) {
            resultsContainer.innerHTML = `
                <div style="padding:12px 16px; color:#94A3B8; font-weight:850; text-align:center;">
                    ❌ No se encontraron cotizaciones para: "<b>${q}</b>"
                </div>
            `;
            return;
        }
        
        // Renderizar resultados
        resultsContainer.innerHTML = results.map(c => `
            <div onclick="seleccionarCotizacionSAP(${c.id})" 
                 style="padding:10px 14px; border-bottom:1px solid #F1F5F9; cursor:pointer; transition:all 0.15s; display:flex; justify-content:space-between; align-items:center;"
                 onmouseover="this.style.background='#F8FAFC'"
                 onmouseout="this.style.background='#fff'">
                <div>
                    <div style="font-weight:900; color:#0F172A;">${c.numero || 'COT-XXXX'}</div>
                    <div style="font-size:11px; color:#64748B;">${c.razon || 'Sin cliente'} ${c.ruc ? '| RUC: ' + c.ruc : ''}</div>
                </div>
                <div style="font-weight:900; color:#EF233C; font-size:13px;">${money(c.total || c.monto || 0)}</div>
            </div>
        `).join('');
        
        resultsContainer.style.display = 'block';
        
        // Cerrar resultados al hacer clic fuera
        document.addEventListener('click', function closeResults(e) {
            if (!resultsContainer.contains(e.target) && e.target !== searchInput) {
                resultsContainer.style.display = 'none';
                document.removeEventListener('click', closeResults);
            }
        });
        
    }, 300);
}

function seleccionarCotizacionSAP(cotizacionId) {
    // Buscar la cotización en los datos básicos
    const cotizacion = cotizacionesData.find(c => c.id === cotizacionId);
    if (!cotizacion) {
        showToast('❌ Cotización no encontrada', 'error');
        return;
    }
    
    showToast('⏳ Cargando productos de la cotización...', 'info');
    
    apiFetch(`/ventas/api/cotizaciones/${cotizacionId}/completa`)
        .then(response => {
            if (!response.success) {
                showToast('❌ Error al cargar productos: ' + (response.error || 'Desconocido'), 'error');
                return;
            }
            
            const data = preciosNetosCotizacion(response.data);
            console.log('📦 Datos completos de cotización:', data);
            
            // Guardar la cotización completa
            cotizacionSeleccionada = data;
            
            // Cerrar resultados
            const resultsContainer = document.getElementById('cotizacionSearchResults');
            if (resultsContainer) {
                resultsContainer.style.display = 'none';
                resultsContainer.innerHTML = '';
            }
            
            // Actualizar el input de búsqueda
            const searchInput = document.getElementById('pcCotSearch');
            if (searchInput) {
                searchInput.value = `${data.numero_cotizacion || ''} - ${data.cliente_razon_social || ''}`;
            }
            
            // ============================================================
            // FUNCIONES PARA SETEAR VALORES
            // ============================================================
            const setReadonlyValue = (id, val) => {
                const el = document.getElementById(id);
                if (el) {
                    el.value = val !== undefined && val !== null ? val : '';
                    el.readOnly = true;
                    el.style.background = '#F1F5F9';
                    el.style.color = '#64748B';
                    el.style.cursor = 'not-allowed';
                }
            };
            
            const setEditableValue = (id, val) => {
                const el = document.getElementById(id);
                if (el) {
                    el.value = val !== undefined && val !== null ? val : '';
                    el.readOnly = false;
                    el.style.background = '#FFFFFF';
                    el.style.color = '#0F172A';
                    el.style.cursor = 'text';
                }
            };
            
            // ============================================================
            // CARGAR DATOS BÁSICOS
            // ============================================================
            setReadonlyValue('pcCotNumero', data.numero_cotizacion || '');
            setReadonlyValue('pcCotFecha', data.fecha_creacion ? formatFecha(data.fecha_creacion) : '');
            setReadonlyValue('pcCliente', data.cliente_razon_social || '');
            setReadonlyValue('pcRuc', data.cliente_ruc || '');
            setReadonlyValue('pcMontoConIgv', data.total || 0);
            // Monto sin IGV YA con el descuento de la cotización (antes salía el subtotal sin descontar)
            setReadonlyValue('pcMonto', (data.subtotal_neto ?? data.subtotal) || 0);
            setReadonlyValue('pcCondicionPago', data.condicion_pago || 'Contado');
            setReadonlyValue('pcVendedor', data.vendedor || 'Helen Blas Príncipe');
            
            // ============================================================
            // 🔽 ACTUALIZAR LA MONEDA 🔽
            // ============================================================
            const monedaCotizacion = data.moneda || data.moneda_cotizacion || 'Soles (S/)';
            let monedaValue = 'S/)'; // Valor por defecto
            
            if (monedaCotizacion.includes('$') || monedaCotizacion.includes('Dólar') || monedaCotizacion.includes('USD')) {
                monedaValue = '$';
            } else {
                monedaValue = 'S/)';
            }
            
            // Actualizar el select de moneda
            const monedaSelect = document.getElementById('pcMoneda');
            if (monedaSelect) {
                for (let opt of monedaSelect.options) {
                    if (opt.value === monedaValue) {
                        opt.selected = true;
                        break;
                    }
                }
            }
            
            // Actualizar el resumen con la nueva moneda
            actualizarMonedaSelect(monedaValue);
            
            // ============================================================
            // ACTUALIZAR CONDICIÓN DE PAGO
            // ============================================================
            // La condición de la PC NO se copia de la cotización (pedido de Erika 19/10): queda en blanco
            // y se elige leyendo la OC del cliente. Solo se muestra lo cotizado como referencia.
            const condSelect = document.getElementById('pcCondicion');
            if (condSelect) {
                condSelect.value = '';
                const aviso = document.getElementById('pcCondicionAviso');
                if (aviso) {
                    aviso.dataset.cotizada = data.condicion_pago || '';
                    aviso.textContent = data.condicion_pago ? `Cotizado: ${data.condicion_pago}. Elige la de la OC del cliente` : 'Léela en la OC del cliente';
                }
                if (typeof pcAvisoCondicion === 'function') pcAvisoCondicion();
            }
            
            // ============================================================
            // DIRECCIÓN DE ENTREGA
            // ============================================================
            if (data.direccion_entrega) {
                setEditableValue('pcEntrega', data.direccion_entrega);
            }
            
            // ============================================================
            // CARGAR PRODUCTOS EN LA TABLA
            // ============================================================
            const tbody = document.getElementById('pcItemsBody');
            if (!tbody) return;
            
            tbody.innerHTML = '';
            
            const productos = data.productos || [];
            console.log(`📦 ${productos.length} productos encontrados`);
            
            if (productos.length === 0) {
                if (typeof addPedidoItemSAP === 'function') {
                    addPedidoItemSAP();
                }
                showToast('⚠️ Esta cotización no tiene productos', 'warning');
                return;
            }
            
            productos.forEach((p, i) => {
                const cantidadCotizada = p.cantidad || 1;
                const precioCotizado = Math.round((Number(p.valorVenta) || 0) * 100) / 100; // 2 decimales
                const stock = stockVivo(p.codigo, p.stock);
                const faltante = Math.max(cantidadCotizada - stock, 0);
                const valorTotal = cantidadCotizada * precioCotizado;
                
                const tr = document.createElement('tr');
                tr.id = `item-row-${i + 1}`;
                tr.style.borderBottom = '1px solid #E2E8F0';
                
                tr.innerHTML = `
                    <td style="padding:2px 3px; text-align:center; font-weight:800; font-size:9px; background:#F8FAFC;">${i + 1}</td>
                    <td style="padding:2px 3px;">
                        <input value="${esc(p.codigo || '')}" 
                               style="width:100%; border:none; background:#F1F5F9; font-size:8px; padding:0 2px; outline:none; font-weight:800; color:#1D4ED8; cursor:not-allowed; max-width:70px;" readonly>
                    </td>
                    <td style="padding:2px 3px;">
                        <input value="${esc(p.producto || p.descripcion || 'Sin descripción')}" 
                               style="width:100%; border:none; background:#F1F5F9; font-size:9px; padding:0; outline:none; font-weight:800; cursor:not-allowed;" readonly>
                    </td>
                    <td style="padding:2px 3px;">
                        <input value="${esc(p.modelo || '')}" 
                               style="width:100%; border:none; background:#F1F5F9; font-size:9px; padding:0; outline:none; font-weight:700; color:#0F172A; cursor:not-allowed;" readonly>
                    </td>
                    <td style="padding:2px 3px;">
                        <input value="${esc(p.marca || '')}" 
                               style="width:100%; border:none; background:#F1F5F9; font-size:9px; padding:0; outline:none; font-weight:700; color:#0F172A; cursor:not-allowed;" readonly>
                    </td>
                    <td style="padding:2px 3px; width:55px;">
                        <input type="number" value="${cantidadCotizada}" 
                               style="width:45px; border:none; background:#F1F5F9; font-size:9px; padding:0; outline:none; text-align:center; cursor:not-allowed;" readonly>
                    </td>
                    <td style="padding:2px 3px; width:55px;">
                        <input type="number" value="${cantidadCotizada}" 
                               style="width:45px; border:none; background:transparent; font-size:9px; padding:0; outline:none; text-align:center; font-weight:900;"
                               onchange="actualizarValorTotalPCSAP(this)">
                    </td>
                    <td style="padding:2px 3px; width:65px;">
                        <input type="number" step="0.01" value="${Number(precioCotizado || 0).toFixed(2)}" 
                               style="width:55px; border:none; background:#F1F5F9; font-size:9px; padding:0; outline:none; text-align:center; cursor:not-allowed;" readonly>
                    </td>
                    <td style="padding:2px 3px; width:65px;">
                        <input type="number" step="0.01" value="${Number(precioCotizado || 0).toFixed(2)}" 
                               style="width:55px; border:none; background:transparent; font-size:9px; padding:0; outline:none; text-align:center; font-weight:900; color:#0F172A;"
                               onchange="actualizarValorTotalPCSAP(this)">
                    </td>
                    <td style="padding:2px 3px; width:70px; text-align:center; font-weight:900; color:#059669; font-size:9px;">
                        <span id="valor-total-${i + 1}">${valorTotal.toFixed(2)}</span>
                    </td>
                    <td style="padding:2px 3px; text-align:center; font-size:8px; color:#64748B; font-weight:800;">${stock}</td>
                    <td style="padding:2px 3px; text-align:center; font-size:8px; font-weight:900; color:${faltante > 0 ? '#DC2626' : '#16A34A'};">${faltante}</td>
                `;
                
                tbody.appendChild(tr);
            });
            
            // ============================================================
            // ACTUALIZAR RESUMEN Y VALIDACIONES
            // ============================================================
            setTimeout(() => {
                actualizarResumenPC();
                if (typeof updateValidationSemaphore === 'function') {
                    updateValidationSemaphore();
                }
                if (typeof togglePagoCampos === 'function') {
                    togglePagoCampos();
                }
            }, 200);
            
            const _desc = Number(data.descuento_total || 0);
            showToast(`✅ Cotización ${data.numero_cotizacion} cargada con ${productos.length} productos` +
                (_desc > 0 ? ` · descuento de ${_desc.toFixed(2)} ya aplicado en los precios` : ''), 'success');
        })
        .catch(error => {
            console.error('❌ Error cargando cotización completa:', error);
            showToast('❌ Error al cargar los productos de la cotización', 'error');
        });
}


/**
 * Actualiza la moneda en el select y el resumen
 * @param {string} moneda - Valor de la moneda ("S/)" o "$")
 */
function actualizarMonedaSelect(moneda) {
    console.log('💰 Actualizando moneda a:', moneda);
    
    const monedaSelect = document.getElementById('pcMoneda');
    const resumenMoneda = document.getElementById('pcResumenMoneda');
    const diferenciaBox = document.getElementById('pcDiferenciaSinIgv');
    
    // Determinar el símbolo correcto
    let simbolo = 'S/';
    if (moneda === '$' || moneda === '$/' || moneda.includes('$')) {
        simbolo = '$';
    } else {
        simbolo = 'S/';
    }
    
    // Actualizar el select si se pasó un valor
    if (monedaSelect && moneda) {
        for (let opt of monedaSelect.options) {
            if (opt.value === moneda) {
                opt.selected = true;
                break;
            }
        }
    }
    
    // Actualizar el símbolo en el resumen
    if (resumenMoneda) {
        resumenMoneda.textContent = simbolo;
        console.log('✅ Símbolo de resumen actualizado a:', simbolo);
    }
    
    // Actualizar el símbolo en el cuadro de diferencia
    if (diferenciaBox) {
        const currentValue = diferenciaBox.textContent.replace(/[S/$\s]/g, '');
        diferenciaBox.textContent = `${simbolo} ${currentValue}`;
    }
    
    // Actualizar todos los montos del resumen
    actualizarResumenPC();
}

/**
 * Actualiza el resumen completo con la moneda correcta
 */
function actualizarResumenPC() {
    // Evitar loops
    if (_actualizandoResumen) return;
    _actualizandoResumen = true;
    
    try {
        console.log('🔄 Actualizando resumen lateral del PC...');
        
        // Obtener la moneda seleccionada
        const monedaSelect = document.getElementById('pcMoneda');
        const monedaValue = monedaSelect ? monedaSelect.value : 'S/)';
        const simbolo = (monedaValue === '$' || monedaValue === '$/' || monedaValue.includes('$')) ? '$' : 'S/';
        
        // Actualizar el símbolo de moneda en el resumen
        const monedaResumen = document.getElementById('pcResumenMoneda');
        if (monedaResumen) monedaResumen.textContent = simbolo;
        
        // Actualizar el símbolo en el cuadro de diferencia
        const diferenciaBox = document.getElementById('pcDiferenciaSinIgv');
        if (diferenciaBox) {
            const currentValue = parseFloat(diferenciaBox.textContent.replace(/[S/$\s]/g, '')) || 0;
            diferenciaBox.textContent = `${simbolo} ${currentValue.toFixed(2)}`;
        }
        
        // Sumar los valores totales de cada producto en la tabla
        let subtotal = 0;
        const rows = document.querySelectorAll('#pcItemsBody tr');
        let productCount = 0;
        
        rows.forEach(row => {
            const inputs = row.querySelectorAll('input');
            if (inputs.length >= 8) {
                const cantidad = parseFloat(inputs[5]?.value) || 0;
                const precio = parseFloat(inputs[7]?.value) || 0;
                const valorTotal = cantidad * precio;
                
                const valueSpan = row.querySelector('td:nth-child(10) span');
                if (valueSpan) {
                    valueSpan.textContent = valorTotal.toFixed(2);
                    valueSpan.style.color = valorTotal > 0 ? '#059669' : '#94A3B8';
                }
                
                subtotal += valorTotal;
                if (cantidad > 0 || precio > 0) productCount++;
            }
        });
        
        // Calcular IGV y total
        const igv = subtotal * 0.18;
        const total = subtotal + igv;
        
        // Función para formatear números con el símbolo correcto
        const formatNum = (num) => `${simbolo} ${num.toFixed(2)}`;
        
        // Actualizar los campos del resumen
        const subtotalEl = document.getElementById('pcResumenSubtotal');
        const valorVentaEl = document.getElementById('pcResumenValorVenta');
        const igvEl = document.getElementById('pcResumenIgv');
        const totalEl = document.getElementById('pcResumenTotal');
        const productosEl = document.getElementById('pcResumenProductos');
        
        if (subtotalEl) subtotalEl.textContent = formatNum(subtotal);
        if (valorVentaEl) valorVentaEl.textContent = formatNum(subtotal);
        if (igvEl) igvEl.textContent = formatNum(igv);
        if (totalEl) totalEl.textContent = formatNum(total);
        if (productosEl) productosEl.textContent = productCount;
        
        // Actualizar el campo de Monto PC
        const montoPCInput = document.getElementById('pcMontoPC');
        if (montoPCInput) {
            const currentValue = parseFloat(montoPCInput.value) || 0;
            if (Math.abs(currentValue - subtotal) > 0.01) {
                montoPCInput.value = subtotal.toFixed(2);
            }
        }
        
        console.log(`✅ Resumen actualizado: ${simbolo} ${subtotal.toFixed(2)}, IGV=${simbolo} ${igv.toFixed(2)}, Total=${simbolo} ${total.toFixed(2)}`);
        
    } catch (error) {
        console.error('❌ Error actualizando resumen:', error);
    } finally {
        _actualizandoResumen = false;
    }
}

// Funciones auxiliares para la tabla de productos
function actualizarFaltanteSAP(input, index) {
    const row = input.closest('tr');
    const inputs = row.querySelectorAll('input');
    const cantidadPC = Number(inputs[3]?.value || 0);
    const stock = Number(inputs[6]?.value || 0);
    const faltanteCell = row.querySelector('td:last-child');
    const faltante = Math.max(cantidadPC - stock, 0);
    if (faltanteCell) {
        faltanteCell.textContent = faltante;
        faltanteCell.style.color = faltante > 0 ? '#DC2626' : '#16A34A';
    }
}

function actualizarPrecioPCSAP(input, index) {
    // Solo actualiza el valor, no hace más nada
    const value = Number(input.value || 0);
    if (value < 0) input.value = 0;
}


/**
 * Fuerza la visibilidad del badge en la pestaña activa
 * Esta función se ejecuta cada vez que se cambia de pestaña
 */
function forzarBadgeActivo() {
    console.log('🔴 Forzando badge en pestaña activa...');
    
    // Buscar todas las pestañas
    document.querySelectorAll('.tab-btn').forEach(function(btn) {
        const badge = btn.querySelector('.tab-badge');
        if (!badge) return;
        
        if (btn.classList.contains('active')) {
            // Pestaña activa - mostrar badge
            badge.style.display = 'inline-block';
            badge.style.visibility = 'visible';
            badge.style.opacity = '1';
            badge.style.animation = 'pulse-badge 1.5s ease-in-out infinite';
            console.log('✅ Badge mostrado en:', btn.textContent.trim());
        } else {
            // Pestaña inactiva - ocultar badge
            badge.style.display = 'none';
            badge.style.visibility = 'hidden';
            badge.style.opacity = '0';
            badge.style.animation = 'none';
        }
    });
}
function clearPedidoModalSAP() {
    console.log('🧹 Limpiando modal de PC a estado inicial...');
     forzarLimpiezaModalPC();
    // ============================================================
    // FUNCIÓN AUXILIAR PARA LIMPIAR CAMPOS
    // ============================================================
    const setReadonlyValue = (id, value) => {
        const el = document.getElementById(id);
        if (el) {
            el.value = value !== undefined ? value : '';
            el.readOnly = true;
            el.style.background = '#F1F5F9';
            el.style.color = '#64748B';
            el.style.cursor = 'not-allowed';
        }
    };
    
    const setEditableValue = (id, value) => {
        const el = document.getElementById(id);
        if (el) {
            el.value = value !== undefined ? value : '';
            el.readOnly = false;
            el.style.background = '#FFFFFF';
            el.style.color = '#0F172A';
            el.style.cursor = 'text';
        }
    };
    
    // ============================================================
    // 1. RESTAURAR TÍTULO Y SUBTÍTULO
    // ============================================================
    const title = document.getElementById('pedidoCompraModalTitle');
    if (title) {
        title.textContent = 'Crear PC Cliente';
    }
    
    const sub = document.getElementById('modalSub');
    if (sub) {
        sub.textContent = 'Primero se valida. No comprar ni despachar si existe observación.';
    }
    
    // ============================================================
    // 2. FECHA ACTUAL
    // ============================================================
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    const fechaStr = now.toISOString().slice(0, 16);
    
    // ============================================================
    // 3. LIMPIAR CAMPOS DE COTIZACIÓN (READONLY)
    // ============================================================
    setReadonlyValue('pcCotNumero', '');
    setReadonlyValue('pcCotFecha', '');
    setReadonlyValue('pcCliente', '');
    setReadonlyValue('pcRuc', '');
    setReadonlyValue('pcMonto', '0');
    setReadonlyValue('pcMontoConIgv', '0');
    setReadonlyValue('pcCondicionPago', '');
    setReadonlyValue('pcVendedor', '');
    
    // ============================================================
    // 4. LIMPIAR BUSCADOR (EDITABLE)
    // ============================================================
    const searchInput = document.getElementById('pcCotSearch');
    if (searchInput) {
        searchInput.value = '';
        searchInput.placeholder = 'Buscar Cotizacion : Escribe N° cotización, RUC, razón social...';
        searchInput.readOnly = false;
        searchInput.style.background = '#FFFFFF';
        searchInput.style.color = '#0F172A';
        searchInput.style.cursor = 'text';
    }
    
    // ============================================================
    // 5. LIMPIAR RESULTADOS DE BÚSQUEDA
    // ============================================================
    const resultsContainer = document.getElementById('cotizacionSearchResults');
    if (resultsContainer) {
        resultsContainer.style.display = 'none';
        resultsContainer.innerHTML = '';
    }
    
    // ============================================================
    // 6. LIMPIAR CAMPOS DEL PC (EDITABLES)
    // ============================================================
    setEditableValue('pcFecha', fechaStr);
    setEditableValue('pcNumero', '');
    setEditableValue('pcContacto', '');
    setEditableValue('pcEntrega', '');
    setEditableValue('pcObs', '');
    setEditableValue('pcMontoPC', '');
    setEditableValue('pcEditId', '');
    
    // ============================================================
    // 7. 🔽 LIMPIAR SELECT DE CONDICIÓN DE PAGO 🔽
    // ============================================================
    const condSelect = document.getElementById('pcCondicion');
    if (condSelect) {
        condSelect.value = ''; // en blanco: se elige leyendo la OC del cliente
        const aviso = document.getElementById('pcCondicionAviso');
        if (aviso) { aviso.dataset.cotizada = ''; aviso.textContent = 'Léela en la OC del cliente'; }
        const oc = document.getElementById('pcOcCliente');
        if (oc) oc.value = '';
        condSelect.disabled = false;
        condSelect.style.background = '#FFFFFF';
        condSelect.style.cursor = 'pointer';
    }
    
    // ============================================================
    // 8. 🔽 LIMPIAR CAMPO PERSONALIZADO DE CONDICIÓN 🔽
    // ============================================================
    const condCustom = document.getElementById('pcCondicionCustom');
    if (condCustom) {
        condCustom.value = '';
        condCustom.style.display = 'none';
        condCustom.style.background = '#FFFFFF';
        condCustom.style.color = '#0F172A';
    }
    
    // ============================================================
    // 9. 🔽 LIMPIAR SELECT DE MONEDA - FORZAR SOLES 🔽
    // ============================================================
    const monedaSelect = document.getElementById('pcMoneda');
    if (monedaSelect) {
        for (let opt of monedaSelect.options) {
            if (opt.value === 'S/)' || opt.value === 'S/' || opt.value === 'Soles') {
                opt.selected = true;
                break;
            }
        }
        monedaSelect.disabled = false;
        monedaSelect.style.background = '#FFFFFF';
        monedaSelect.style.cursor = 'pointer';
    }
    
    // ============================================================
    // 10. 🔽 LIMPIAR SELECT DE MEDIO 🔽
    // ============================================================
    const medioSelect = document.getElementById('pcMedio');
    if (medioSelect) {
        if (medioSelect.options.length > 0) {
            medioSelect.selectedIndex = 0;
        }
        medioSelect.disabled = false;
        medioSelect.style.background = '#FFFFFF';
        medioSelect.style.cursor = 'pointer';
    }
    
    // ============================================================
    // 11. 🔽 LIMPIAR DIFERENCIA (S/IGV) 🔽 - FORZADO
    // ============================================================
    const diferenciaBox = document.getElementById('pcDiferenciaSinIgv');
    if (diferenciaBox) {
        diferenciaBox.textContent = 'S/ 0.00';
        diferenciaBox.style.color = '#6B7280';
        diferenciaBox.style.background = '#f8f9fa';
        console.log('✅ Diferencia reseteada a:', diferenciaBox.textContent);
    }
    
    // ============================================================
    // 12. OCULTAR CAMPOS DE PAGO (Contado)
    // ============================================================
    const pagoContainer = document.getElementById('pagoCamposContainer');
    if (pagoContainer) {
        pagoContainer.style.display = 'none';
    }
    const numOp = document.getElementById('pcNumOperacion');
    const banco = document.getElementById('pcBanco');
    const cuenta = document.getElementById('pcCuentaOCCI');
    if (numOp) numOp.value = '';
    if (banco) banco.value = '';
    if (cuenta) cuenta.value = '';
    
    // ============================================================
    // 13. LIMPIAR TABLA DE ITEMS (SOLO UNA FILA VACÍA)
    // ============================================================
    const tbody = document.getElementById('pcItemsBody');
    if (tbody) {
        tbody.innerHTML = '';
        addPedidoItemSAP();
    }
    
    // ============================================================
    // 14. RESETEAR SWITCHES DE VALIDACIÓN A "NO VÁLIDO"
    // ============================================================
    const validations = ['vPrecio', 'vProducto', 'vEntrega', 'vTransporte', 'vCantidad', 'vMoneda', 'vVigencia'];
    validations.forEach(id => {
        const checkbox = document.getElementById(id);
        if (checkbox) {
            checkbox.checked = false;
            const label = document.getElementById(id + 'Label');
            if (label) {
                label.textContent = '❌ NO VÁLIDO';
                label.style.color = '#DC2626';
            }
        }
    });
    
    // ============================================================
    // 15. RESETEAR SEMÁFORO DE VALIDACIÓN
    // ============================================================
    const semaphore = document.getElementById('validationSemaphore');
    if (semaphore) {
        semaphore.style.borderColor = '#F59E0B';
        semaphore.style.background = '#FFFBEB';
    }
    
    const icon = document.getElementById('validationIcon');
    if (icon) icon.textContent = '⏳';
    
    const titleSemaphore = document.getElementById('validationTitle');
    if (titleSemaphore) {
        titleSemaphore.textContent = 'Validando...';
        titleSemaphore.style.color = '#92400E';
    }
    
    const subtitleSemaphore = document.getElementById('validationSubtitle');
    if (subtitleSemaphore) {
        subtitleSemaphore.textContent = 'Revisando los puntos de validación';
        subtitleSemaphore.style.color = '#92400E';
    }
    
    const chips = document.getElementById('validationChips');
    if (chips) chips.innerHTML = '';
    
    // ============================================================
    // 16. RESETEAR RESUMEN LATERAL A CEROS
    // ============================================================
    const resumenSubtotal = document.getElementById('pcResumenSubtotal');
    const resumenValorVenta = document.getElementById('pcResumenValorVenta');
    const resumenIgv = document.getElementById('pcResumenIgv');
    const resumenTotal = document.getElementById('pcResumenTotal');
    const resumenProductos = document.getElementById('pcResumenProductos');
    const resumenMoneda = document.getElementById('pcResumenMoneda');
    
    if (resumenSubtotal) resumenSubtotal.textContent = 'S/ 0.00';
    if (resumenValorVenta) resumenValorVenta.textContent = 'S/ 0.00';
    if (resumenIgv) resumenIgv.textContent = 'S/ 0.00';
    if (resumenTotal) resumenTotal.textContent = 'S/ 0.00';
    if (resumenProductos) resumenProductos.textContent = '0';
    if (resumenMoneda) resumenMoneda.textContent = 'S/';
    
    // ============================================================
    // 17. RESETEAR VARIABLES GLOBALES
    // ============================================================
    cotizacionSeleccionada = null;
    modalMode = 'cot';
    editingId = null;
    
    // ============================================================
    // 18. 🔽 FORZAR LIMPIEZA DE DIFERENCIA NUEVAMENTE (DESPUÉS DE TODO) 🔽
    // ============================================================
    setTimeout(() => {
        console.log('🔄 Forzando limpieza final de diferencia...');
        
        // Resetear diferencia nuevamente
        const diffBox = document.getElementById('pcDiferenciaSinIgv');
        if (diffBox) {
            diffBox.textContent = 'S/ 0.00';
            diffBox.style.color = '#6B7280';
            diffBox.style.background = '#f8f9fa';
            console.log('  ✅ Diferencia forzada a:', diffBox.textContent);
        }
        
        // Resetear monto PC
        const montoPC = document.getElementById('pcMontoPC');
        if (montoPC) {
            montoPC.value = '';
            console.log('  ✅ Monto PC limpiado');
        }
        
        if (typeof actualizarResumenPC === 'function') {
            actualizarResumenPC();
        }
        if (typeof updateValidationSemaphore === 'function') {
            updateValidationSemaphore();
        }
        if (typeof togglePagoCampos === 'function') {
            togglePagoCampos();
        }
    }, 200);
    
    console.log('✅ Modal de PC restaurado a estado inicial');
}

/**
 * Forza la limpieza completa del modal de PC
 * Esta función debe llamarse CADA VEZ que se abre el modal
 */
function forzarLimpiezaModalPC() {
    console.log('🧹 FORZANDO limpieza de campos problemáticos...');
    
    // 1. Limpiar Condición de Pago - Forzar "Contado"
    const condSelect = document.getElementById('pcCondicion');
    if (condSelect) {
        condSelect.value = ''; // en blanco: se elige leyendo la OC del cliente
        // Asegurar que el select esté habilitado
        condSelect.disabled = false;
        condSelect.style.background = '#FFFFFF';
        condSelect.style.cursor = 'pointer';
    }
    
    // 2. Limpiar campo personalizado de condición
    const condCustom = document.getElementById('pcCondicionCustom');
    if (condCustom) {
        condCustom.value = '';
        condCustom.style.display = 'none';
        condCustom.style.background = '#FFFFFF';
        condCustom.style.color = '#0F172A';
        console.log('✅ Campo personalizado de condición limpiado');
    }
    
    // 3. Limpiar Diferencia S/IGV - Forzar a 0
    const diferenciaBox = document.getElementById('pcDiferenciaSinIgv');
    if (diferenciaBox) {
        diferenciaBox.textContent = 'S/ 0.00';
        diferenciaBox.style.color = '#6B7280';
        diferenciaBox.style.background = '#f8f9fa';
        console.log('✅ Diferencia forzada a: S/ 0.00');
    }
    
    // 4. Limpiar Monto PC
    const montoPC = document.getElementById('pcMontoPC');
    if (montoPC) {
        montoPC.value = '';
        console.log('✅ Monto PC limpiado');
    }
    
    // 5. Limpiar Moneda - Forzar Soles
    const monedaSelect = document.getElementById('pcMoneda');
    if (monedaSelect) {
        let found = false;
        for (let opt of monedaSelect.options) {
            if (opt.value === 'S/)' || opt.value === 'S/' || opt.value === 'Soles') {
                opt.selected = true;
                found = true;
                console.log('✅ Moneda forzada a: Soles');
                break;
            }
        }
        if (!found && monedaSelect.options.length > 0) {
            monedaSelect.selectedIndex = 0;
        }
        monedaSelect.disabled = false;
        monedaSelect.style.background = '#FFFFFF';
        monedaSelect.style.cursor = 'pointer';
    }
    
    // 6. Actualizar el resumen con los valores limpios
    setTimeout(() => {
        if (typeof actualizarResumenPC === 'function') {
            actualizarResumenPC();
            console.log('✅ Resumen actualizado después de limpieza forzada');
        }
    }, 50);
}


function setEditableValue(id, value) {
    const el = document.getElementById(id);
    if (el) {
        el.value = value !== undefined && value !== null ? value : '';
        el.readOnly = false;
        el.style.background = '#FFFFFF';
        el.style.color = '#0F172A';
        el.style.cursor = 'text';
    }
}


function toggleCustomPcCondicion() {
    const select = document.getElementById('pcCondicion');
    const customInput = document.getElementById('pcCondicionCustom');
    
    if (!select || !customInput) return;
    
    if (select.value === 'Personalizado') {
        customInput.style.display = 'block';
        customInput.focus();
    } else {
        customInput.style.display = 'none';
        customInput.value = '';
    }
    
    // 🔽 También llamar a togglePagoCampos
    togglePagoCampos();
}

/**
 * Obtiene el valor de la condición de pago (incluyendo personalizado)
 */
function getPcCondicionValue() {
    const select = document.getElementById('pcCondicion');
    const customInput = document.getElementById('pcCondicionCustom');
    
    if (!select) return 'Contado';
    
    if (select.value === 'Personalizado' && customInput) {
        return customInput.value.trim() || 'Personalizado';
    }
    
    return select.value;
}

/**
 * Establece el valor de la condición de pago (soporta personalizado)
 */
function setPcCondicionValue(value) {
    const select = document.getElementById('pcCondicion');
    const customInput = document.getElementById('pcCondicionCustom');
    
    if (!select) return;
    
    if (!value) {
        select.value = 'Contado';
        if (customInput) {
            customInput.style.display = 'none';
            customInput.value = '';
        }
        return;
    }
    
    // Verificar si el valor está en las opciones del select
    let found = false;
    for (let opt of select.options) {
        if (opt.value === value) {
            opt.selected = true;
            found = true;
            break;
        }
    }
    
    if (!found && customInput) {
        // Si no está en las opciones, seleccionar "Personalizado"
        select.value = 'Personalizado';
        customInput.value = value;
        customInput.style.display = 'block';
    } else if (customInput) {
        customInput.style.display = 'none';
        customInput.value = '';
    }
}

// ============================================================
// VARIABLE GLOBAL PARA EL MODO DEL MODAL
// ============================================================
let modalMode = 'cot';  // 'cot' | 'directo' | 'editar'


async function savePedidoCompraSAP(force) {
    console.log('🔄 savePedidoCompraSAP ejecutándose...', { force, modalMode, editingId });
    
    try {
        // ============================================================
        // 🔽 VALIDAR CAMPOS OBLIGATORIOS
        // ============================================================
        const pcFecha = document.getElementById('pcFecha')?.value || '';
        const pcNumero = document.getElementById('pcNumero')?.value?.trim() || '';
        const pcContacto = document.getElementById('pcContacto')?.value?.trim() || '';
        const pcCondicion = document.getElementById('pcCondicion')?.value || '';
        const pcMoneda = document.getElementById('pcMoneda')?.value || '';
        const pcMontoPC = document.getElementById('pcMontoPC')?.value || '';
        const pcEntrega = document.getElementById('pcEntrega')?.value?.trim() || '';
        
        // Array de campos obligatorios con sus nombres para mostrar
        const camposObligatorios = [
            { id: 'pcFecha', valor: pcFecha, nombre: 'Fecha recepción' },
            { id: 'pcContacto', valor: pcContacto, nombre: 'Comprador' },
            { id: 'pcCondicion', valor: pcCondicion, nombre: 'Condición de pago' },
            { id: 'pcMoneda', valor: pcMoneda, nombre: 'Moneda' },
            { id: 'pcMontoPC', valor: pcMontoPC, nombre: 'Monto PC' },
            { id: 'pcEntrega', valor: pcEntrega, nombre: 'Lugar entrega' }
        ];
        
        // Verificar campos faltantes
        const camposFaltantes = camposObligatorios.filter(campo => !campo.valor || campo.valor === '' || campo.valor === '0' || campo.valor === '0.00');
        
        if (camposFaltantes.length > 0) {
            const nombresFaltantes = camposFaltantes.map(c => c.nombre).join(', ');
            showToast(`⚠️ Campos obligatorios faltantes: ${nombresFaltantes}`, 'warning');
            
            // Resaltar los campos faltantes
            camposFaltantes.forEach(campo => {
                const el = document.getElementById(campo.id);
                if (el) {
                    el.style.borderColor = '#DC2626';
                    el.style.boxShadow = '0 0 0 2px rgba(220,38,38,0.2)';
                    setTimeout(() => {
                        el.style.borderColor = '';
                        el.style.boxShadow = '';
                    }, 3000);
                }
            });
            
            // Enfocar el primer campo faltante
            const primerCampo = document.getElementById(camposFaltantes[0].id);
            if (primerCampo) {
                primerCampo.focus();
                primerCampo.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
            return;
        }
        
        // ============================================================
        // 🔽 VALIDAR QUE LA TABLA DE PRODUCTOS TENGA DATOS
        // ============================================================
        const tbody = document.getElementById('pcItemsBody');
        const filas = tbody ? Array.from(tbody.querySelectorAll('tr')) : [];
        
        // Verifica que al menos una fila tenga un código de producto real
        // Una fila cuenta si tiene código O descripción (hay productos sin código)
        const hayProductosReales = filas.some(row => {
            const ins = row.querySelectorAll('input');
            return ins.length >= 8 && ((ins[0].value || '').trim() !== '' || (ins[1].value || '').trim() !== '');
        });
        
        if (filas.length === 0 || !hayProductosReales) {
            showToast('⚠️ No hay productos cargados. Agrega al menos un producto.', 'warning');
            return;
        }
        
        // ============================================================
        // 🔽 VALIDAR SWITCHES ANTES DE GUARDAR
        // ============================================================
        const validationSwitches = [
            { id: 'vPrecio', label: 'Precio' },
            { id: 'vCantidad', label: 'Cantidad' },
            { id: 'vProducto', label: 'Nombre producto' },
            { id: 'vEntrega', label: 'Lugar entrega' },
            { id: 'vMoneda', label: 'Moneda' },
            { id: 'vVigencia', label: 'Vigencia' }
        ];
        
        const invalidSwitches = [];
        const validSwitches = [];
        
        validationSwitches.forEach(({ id, label }) => {
            const checkbox = document.getElementById(id);
            if (checkbox) {
                if (checkbox.checked) {
                    validSwitches.push(label);
                } else {
                    invalidSwitches.push(label);
                }
            }
        });
        
        console.log('📋 Switches válidos:', validSwitches);
        console.log('📋 Switches inválidos:', invalidSwitches);
        
        // ============================================================
        // 🔽 SI ES "PC CONFORME" Y HAY SWITCHES INVÁLIDOS, BLOQUEAR
        // ============================================================
        if (force !== 'observado' && invalidSwitches.length > 0) {
            showValidationWarningModal(invalidSwitches);
            return;
        }
        
        // ============================================================
        // 🔽 VALIDAR QUE SE HAYA SELECCIONADO UNA COTIZACIÓN EN MODO 'cot'
        // ============================================================
        if (modalMode === 'cot' && !cotizacionSeleccionada) {
            const searchInput = document.getElementById('pcCotSearch');
            const valor = searchInput?.value?.trim() || '';
            if (!valor) {
                showToast('⚠️ Debes buscar y seleccionar una cotización primero', 'warning');
                searchInput?.focus();
                return;
            }
            // Si hay texto pero no se seleccionó, intentar buscar automáticamente
            const results = cotizacionesData.filter(c => {
                const searchStr = `${c.numero || ''} ${c.razon || ''} ${c.ruc || ''}`.toLowerCase();
                return searchStr.includes(valor.toLowerCase());
            });
            if (results.length === 0) {
                showToast('⚠️ No se encontró la cotización. Verifica el texto ingresado.', 'warning');
                return;
            } else if (results.length === 1) {
                seleccionarCotizacionSAP(results[0].id);
                setTimeout(() => savePedidoCompraSAP(force), 300);
                return;
            } else {
                showToast('⚠️ Se encontraron varias cotizaciones. Selecciona una de la lista.', 'warning');
                buscarCotizacionSAP(valor);
                return;
            }
        }
        
        // ============================================================
        // 🔽 LEER VALIDACIONES DE LOS SWITCHES
        // ============================================================
        const val = ['vPrecio', 'vCantidad', 'vProducto', 'vEntrega', 'vMoneda', 'vTransporte', 'vVigencia']
            .map(id => {
                const el = document.getElementById(id);
                if (el && el.type === 'checkbox') {
                    return el.checked ? 'Sí' : 'No';
                }
                return el?.value || 'Sí';
            });
        
        console.log('📋 Validaciones:', val);
        
        // OBSERVADO SOLO POR VALIDACIONES, NO POR STOCK
        const observed = force === 'observado' || val.some(v => v === 'No');
        
        // ============================================================
        // 🔽 LEER ITEMS DE LA TABLA
        // ============================================================
        const trs = document.querySelectorAll('#pcItemsBody tr');
        const items = [];
        trs.forEach(row => {
            const inputs = row.querySelectorAll('input');
            if (inputs.length >= 8) {
                const tds = row.querySelectorAll('td');
                const stockCell = tds[10]; // columna "Stock" (la 9 es el valor total)
                if (!(inputs[0]?.value || '').trim() && !(inputs[1]?.value || '').trim()) return; // fila vacía
                items.push({
                    codigo: inputs[0]?.value || '',
                    producto: inputs[1]?.value || '',
                    modelo: inputs[2]?.value || '',
                    marca: inputs[3]?.value || '',
                    cantidad_cotizada: Number(inputs[4]?.value || 0),
                    cantidad_pc: Number(inputs[5]?.value || 1),
                    precio_cotizado: Number(inputs[6]?.value || 0),
                    precio_pc: Number(inputs[7]?.value || 0),
                    stock: Number(stockCell?.textContent?.trim() || 0)
                });
            }
        });
        
        console.log('📦 Items del PC:', items);
        
        // ============================================================
        // 🔽 DETERMINAR ESTADO - SIN BLOQUEAR POR STOCK
        // ============================================================
        const estado = observed ? 'PC observado' : 'PC conforme';
        const req_compra = observed ? 'Bloqueado' : 'Sí';
        
        // ============================================================
        // 🔽 OBTENER VALOR DE CONDICIÓN DE PAGO
        // ============================================================
        const condicionSelect = document.getElementById('pcCondicion');
        const condicionCustom = document.getElementById('pcCondicionCustom');
        let condicionPago = condicionSelect?.value || '';
        if (condicionPago === 'Personalizado' && condicionCustom) {
            condicionPago = condicionCustom.value.trim();
        }
        if (!condicionPago || condicionPago === 'Seleccione') {
            showToast('⚠️ Elige la condición de pago leyendo la orden de compra del cliente (no se copia de la cotización)', 'warning');
            condicionSelect?.focus();
            return;
        }
        
        // ============================================================
        // 🔽 OBTENER EL NÚMERO DEL PC
        // ============================================================
        let numeroPC = document.getElementById('pcNumero')?.value || '';
        
        if (modalMode === 'editar' && editingId) {
            const pedidoExistente = pedidosData.find(p => p.id === editingId);
            if (!numeroPC.trim() && pedidoExistente && pedidoExistente.numero) {
                numeroPC = pedidoExistente.numero;
            }
        } else {
            numeroPC = ''; // el N° PC interno lo pone el sistema (correlativo por empresa)
        }
        
        console.log(`📋 Número de PC final: ${numeroPC} | editingId: ${editingId} | modalMode: ${modalMode}`);
        
        // ============================================================
        // 🔽 FECHA CON HORA - FORMATO CORRECTO PARA POSTGRESQL
        // ============================================================
        const ahora = new Date();
        const year = ahora.getFullYear();
        const month = String(ahora.getMonth() + 1).padStart(2, '0');
        const day = String(ahora.getDate()).padStart(2, '0');
        const hours = String(ahora.getHours()).padStart(2, '0');
        const minutes = String(ahora.getMinutes()).padStart(2, '0');
        const seconds = String(ahora.getSeconds()).padStart(2, '0');
        
        // ✅ FORMATO PARA POSTGRESQL: YYYY-MM-DD HH:MM:SS (con espacio)
        const fechaDB = `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
        console.log(`🕐 Fecha y hora para PC: ${fechaDB}`);

        // ============================================================
        // 🔽 PREPARAR DATOS PARA ENVIAR A LA API
        // ============================================================
        const pcData = {
            id: editingId || null,
            numero: numeroPC,
            // La fecha es la que se escribe en "Fecha recepción" (antes se guardaba siempre la hora actual)
            fecha: pcFecha ? (pcFecha.replace('T', ' ') + (pcFecha.length === 16 ? ':00' : '')) : fechaDB,
            fecha_recepcion: (pcFecha || fechaDB).slice(0, 10),
            medio: document.getElementById('pcMedio')?.value || 'Correo',
            estado: estado,
            cliente: document.getElementById('pcCliente')?.value || '',
            ruc: document.getElementById('pcRuc')?.value || '',
            cotizacion_id: cotizacionSeleccionada?.id
                || (modalMode === 'editar' ? ((pedidosData || []).find(p => p.id === editingId)?.cotizacion_id || null) : null),
            cotizacion_numero: document.getElementById('pcCotNumero')?.value || 'SIN COTIZACIÓN',
            monto: Number(document.getElementById('pcMontoPC')?.value || 0),
            entrega: document.getElementById('pcEntrega')?.value || '',
            lugar_entrega: document.getElementById('pcEntrega')?.value || '',
            condicion_pago: condicionPago,
            oc_cliente: (document.getElementById('pcOcCliente')?.value || '').trim(),
            vendedor: document.getElementById('pcVendedor')?.value || 'Helen Blas Príncipe',
            responsable: 'Hellen',
            observaciones: document.getElementById('pcObs')?.value || '',
            items: items,
            valida_precios: val[0] === 'Sí',
            valida_cantidades: val[1] === 'Sí',
            valida_stock: false,
            valida_productos: val[2] === 'Sí',
            valida_margen: true, // no hay interruptor de margen en la pantalla
            valida_entrega: val[3] === 'Sí',
            valida_montos: val[4] === 'Sí',
            valida_transporte: val[5] === 'Sí',
            valida_vigencia: val[6] === 'Sí',
            req_compra: req_compra
        };
        
        console.log('📦 Datos a enviar a la API:', pcData);
        console.log('📅 fecha enviada (formato PostgreSQL):', pcData.fecha);

        // ============================================================
        // 🔽 CONFIRMACIÓN ANTES DE ENVIAR
        // ============================================================
        const confirmado = await new Promise(resolve => {
            showConfirmModal(
                '💾 ¿Guardar Pedido de Compra?',
                `Vas a guardar el PC <b>${pcData.numero || '(N° automático)'}</b> de <b>${pcData.cliente || 'el cliente'}</b> como <b>"${pcData.estado}"</b>.`,
                '⚠️ Esta acción registrará el PC con las validaciones actuales.',
                () => resolve(true),
                '💾 Sí, guardar'
            );
        });
        if (!confirmado) return;
        
        // ============================================================
        // 🔽 ENVIAR A LA API
        // ============================================================
        showToast('⏳ Guardando PC...', 'info');
        
        const response = await fetch('/ventas/api/pedido-compra/guardar', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(pcData)
        });
        
        const result = await response.json();
        console.log('📦 Respuesta del servidor:', result);
        
        if (result.success) {
            const nroGuardado = (result.data && result.data.numero) || pcData.numero;
            let mensaje = `✅ PC ${nroGuardado || ''} guardado como: ${estado}`;
            if (estado === 'PC conforme') {
                const stockFalta = items.some(i => Number(i.cantidad_pc) > Number(i.stock));
                if (stockFalta) {
                    mensaje += ' ⚠️ Stock insuficiente - requiere compra';
                } else {
                    mensaje += ' ✅ Stock OK - listo para despacho';
                }
            }
            showToast(mensaje, 'success');
            
            closeModal('pedidoCompraModal');
            cotizacionSeleccionada = null;
            editingId = null;
            
            if (typeof loadPedidos === 'function') {
                await loadPedidos();
            }
            if (typeof loadCotizaciones === 'function') {
                await loadCotizaciones();
            }
            if (currentModule === 'validacion' && typeof renderValidacion === 'function') {
                renderValidacion();
            }
            
        } else {
            showToast('❌ Error: ' + (result.error || 'No se pudo guardar'), 'error');
        }
        
    } catch (error) {
        console.error('❌ Error en savePedidoCompraSAP:', error);
        showToast('❌ Error al guardar el PC: ' + error.message, 'error');
    }
}
window.savePedidoCompraSAP = savePedidoCompraSAP;

function cargarUnidadesDeMedidaGuia() {
    const selectUnidad = document.getElementById('guiaUnidadPeso');
    if (!selectUnidad) {
        console.warn('⚠️ Select "guiaUnidadPeso" no encontrado.');
        return;
    }

    // Opcional: Mostrar un estado de carga
    selectUnidad.innerHTML = '<option value="">Cargando unidades...</option>';

    fetch('/maestros/api/um/listar')
        .then(response => response.json())
        .then(data => {
            if (data.success && data.data) {
                // Limpiar el select
                selectUnidad.innerHTML = '';
                
                // Agregar una opción por defecto
                const defaultOption = document.createElement('option');
                defaultOption.value = '';
                defaultOption.textContent = '-- Seleccionar Unidad --';
                selectUnidad.appendChild(defaultOption);

                // Agregar las unidades de la base de datos
                data.data.forEach(um => {
                    const option = document.createElement('option');
                    option.value = um.codigo; // Usar 'codigo' que es el identificador SUNAT
                    option.textContent = `${um.codigo} - ${um.nombre}`; // Ejemplo: "KGM - Kilogramo"
                    // Podrías querer mostrar solo el código o el nombre, depende de ti.
                    // Si quieres solo el código: option.textContent = um.codigo;
                    selectUnidad.appendChild(option);
                });

                console.log(`✅ ${data.data.length} unidades de medida cargadas para la guía.`);
            } else {
                console.error('❌ Error al cargar unidades de medida:', data.error || 'Error desconocido');
                selectUnidad.innerHTML = '<option value="">Error al cargar unidades</option>';
                showToast('⚠️ No se pudieron cargar las unidades de medida.', 'warning');
            }
        })
        .catch(error => {
            console.error('❌ Error de red al cargar unidades de medida:', error);
            selectUnidad.innerHTML = '<option value="">Error de conexión</option>';
            showToast('❌ Error al conectar con el servidor para cargar unidades.', 'error');
        });
}


// ============================================================
// MODAL DE ADVERTENCIA DE VALIDACIÓN PARA CAMPOS OBLIGATORIOS
// ============================================================
function showValidationWarningModal(camposFaltantes) {
    // Remover modales existentes
    document.querySelectorAll('.validation-warning-overlay').forEach(el => el.remove());
    
    const overlay = document.createElement('div');
    overlay.className = 'validation-warning-overlay';
    overlay.style.cssText = `
        position: fixed;
        inset: 0;
        background: rgba(0, 0, 0, 0.7);
        backdrop-filter: blur(8px);
        z-index: 999999;
        display: flex;
        align-items: center;
        justify-content: center;
        animation: fadeIn 0.3s ease;
        padding: 20px;
    `;
    
    const modal = document.createElement('div');
    modal.style.cssText = `
        background: #FFFFFF;
        border-radius: 24px;
        max-width: 560px;
        width: 100%;
        padding: 40px 32px 32px;
        box-shadow: 0 30px 80px rgba(0,0,0,0.4);
        animation: modalSlideUp 0.3s ease;
        text-align: center;
    `;
    
    // Generar lista de items pendientes con íconos
    const listaItems = camposFaltantes.map(item => {
        // Asignar ícono según el tipo de campo
        let icono = '❌';
        if (item.includes('RUC')) icono = '📋';
        else if (item.includes('Condición')) icono = '💳';
        else if (item.includes('Tiempo')) icono = '⏰';
        
        return `<li style="color: #DC2626; font-weight: 800; padding: 10px 0; text-align: left; list-style: none; border-bottom: 1px solid #FEE2E2; font-size: 15px; display: flex; align-items: center; gap: 12px;">
            <span style="font-size: 22px;">${icono}</span>
            ${item}
        </li>`;
    }).join('');
    
    // Determinar el mensaje según la cantidad de campos faltantes
    let mensajeIntro = '';
    if (camposFaltantes.length === 1) {
        mensajeIntro = 'Para continuar, completa el siguiente campo obligatorio:';
    } else {
        mensajeIntro = `Para continuar, completa los siguientes ${camposFaltantes.length} campos obligatorios:`;
    }
    
    modal.innerHTML = `
        <div style="font-size: 56px; margin-bottom: 16px;">⚠️</div>
        <h2 style="font-size: 24px; font-weight: 900; color: #0F172A; margin-bottom: 8px;">¡Campos obligatorios faltantes!</h2>
        <p style="font-size: 16px; color: #475569; line-height: 1.6; margin-bottom: 20px;">
            ${mensajeIntro}
        </p>
        <div style="background: #FEF2F2; border-radius: 16px; padding: 16px 20px; margin-bottom: 24px; border-left: 4px solid #DC2626; text-align: left;">
            <ul style="margin: 0; padding: 0; list-style: none;">
                ${listaItems}
            </ul>
        </div>
        <div style="background: #EFF6FF; border-radius: 12px; padding: 12px 16px; margin-bottom: 24px; border-left: 4px solid #2563EB; text-align: left;">
            <span style="font-size: 13px; font-weight: 700; color: #1E3A8A; display: flex; align-items: center; gap: 8px;">
                💡 Los campos marcados con <span style="color:#DC2626;font-weight:900;">*</span> son obligatorios.
            </span>
        </div>
        <button class="warning-close-btn" style="
            padding: 14px 48px;
            border-radius: 14px;
            border: none;
            background: #EF233C;
            color: #FFFFFF;
            font-weight: 900;
            font-size: 16px;
            cursor: pointer;
            transition: all 0.2s;
            box-shadow: 0 4px 14px rgba(239, 35, 60, 0.4);
            width: 100%;
        " onmouseover="this.style.background='#D91A30';this.style.transform='translateY(-2px)';this.style.boxShadow='0 6px 20px rgba(239,35,60,0.5)'" 
           onmouseout="this.style.background='#EF233C';this.style.transform='translateY(0)';this.style.boxShadow='0 4px 14px rgba(239,35,60,0.4)'">
            ✅ Entendido, ir a completar
        </button>
    `;
    
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    
    // Animaciones CSS
    const style = document.createElement('style');
    style.textContent = `
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        @keyframes modalSlideUp {
            from { opacity: 0; transform: translateY(40px) scale(0.95); }
            to { opacity: 1; transform: translateY(0) scale(1); }
        }
    `;
    document.head.appendChild(style);
    
    // Event listener para cerrar y enfocar el primer campo faltante
    modal.querySelector('.warning-close-btn').addEventListener('click', function() {
        overlay.remove();
        // Enfocar el primer campo faltante
        const mapaCampos = {
            'RUC': 'fRuc',
            'Condición de Pago': 'fCondicion',
            'Tiempo de Entrega': 'fTiempo'
        };
        for (const campo of camposFaltantes) {
            let id = null;
            for (const [key, value] of Object.entries(mapaCampos)) {
                if (campo.includes(key)) {
                    id = value;
                    break;
                }
            }
            if (id) {
                const el = document.getElementById(id);
                if (el) {
                    el.focus();
                    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    break;
                }
            }
        }
    });
    
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) {
            overlay.remove();
        }
    });
}

function updateProductQty(idKey, value) {
    // La cantidad se guarda en el atributo data-qty del checkbox o se obtiene cuando se agrega
    // No es necesario hacer nada aquí, se usará al agregar
}


function addSelectedProducts() {
    if (selectedProductIds.size === 0) {
        showToast('⚠️ Selecciona al menos un producto', 'warning');
        return;
    }
    
    let addedCount = 0;
    let notFoundCount = 0;
    
    selectedProductIds.forEach(idKey => {
        // Buscar el producto por id o codigo
        let product = PRODUCTOS_MAESTROS.find(p => p.id == idKey || p.codigo == idKey);
        
        if (!product) {
            notFoundCount++;
            return;
        }
        
        // Obtener la cantidad del input correspondiente
        const qtyInput = document.querySelector(`.product-select-qty[data-id="${idKey}"]`);
        const cantidad = parseInt(qtyInput?.value || 1);
        
        // 🔽 Asegurar que valorVenta sea un número
        const valorVenta = parseFloat(product.valorVenta) || 0;
        
        // Verificar si ya está agregado (por código)
        const existingIndex = quoteProducts.findIndex(p => p.codigo === product.codigo);
        if (existingIndex !== -1) {
            // Si ya existe, sumar cantidad
            quoteProducts[existingIndex].cantidad = (quoteProducts[existingIndex].cantidad || 1) + cantidad;
        } else {
            // Agregar nuevo producto
            const nuevoProducto = {
                ...product,
                cantidad: cantidad,
                valorVenta: valorVenta,
                stock: parseInt(product.stock) || 0
            };
            quoteProducts.push(nuevoProducto);
        }
        addedCount++;
    });
    
    // Cerrar modal
    closeModal('productSelectorModal');
    
    // Renderizar tabla de productos
    renderQuoteProducts();
    calcQuote();
    
    // Mostrar mensaje
    if (addedCount > 0) {
        showToast(`✅ ${addedCount} productos agregados correctamente`, 'success');
    }
    if (notFoundCount > 0) {
        showToast(`⚠️ ${notFoundCount} productos no encontrados`, 'warning');
    }
}


// Event listener para el buscador del selector
document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('productSelectorSearch');
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            renderProductSelector();
        });
        searchInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                renderProductSelector();
            }
        });
    }
});


// ============================================================
// EVENT LISTENERS PARA FILTROS DE FECHA
// ============================================================
const fechaInicio = document.getElementById('qFechaInicio');
const fechaFin = document.getElementById('qFechaFin');

if (fechaInicio) {
    fechaInicio.addEventListener('change', function() {
        renderCotizaciones();
    });
}

if (fechaFin) {
    fechaFin.addEventListener('change', function() {
        renderCotizaciones();
    });
}
function showSuccessModal(cotizacionId) {
    // Si no se pasó el ID, intentar obtenerlo de la respuesta
    if (!cotizacionId) {
        // Buscar la última cotización creada
        const ultimaCotizacion = cotizacionesData.length > 0 ? cotizacionesData[0] : null;
        if (ultimaCotizacion && ultimaCotizacion.id) {
            cotizacionId = ultimaCotizacion.id;
        }
    }
    
    // Obtener datos de la cotización generada
    const ruc = document.getElementById('fRuc')?.value?.trim() || '---';
    const razon = document.getElementById('fRazon')?.value?.trim() || '---';
    const totalSpan = document.getElementById('sumTotal');
    const total = totalSpan?.textContent || 'S/ 0.00';
    const subtotal = document.getElementById('sumSubtotal')?.textContent || 'S/ 0.00';
    const igv = document.getElementById('sumIgv')?.textContent || 'S/ 0.00';
    const now = new Date();
    const fechaHora = now.toLocaleString('es-PE', { 
        day: '2-digit', 
        month: '2-digit', 
        year: 'numeric',
        hour: '2-digit', 
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
        timeZone: 'America/Lima'
    });
    const numeroCotizacion = `COT-${String(Date.now()).slice(-8)}`;
    const productosCount = quoteProducts.length;
    
    // Remover modales existentes
    document.querySelectorAll('.success-modal-overlay').forEach(el => el.remove());
    
    const overlay = document.createElement('div');
    overlay.className = 'success-modal-overlay';
    overlay.style.cssText = `
        position: fixed;
        inset: 0;
        background: rgba(0, 0, 0, 0.5);
        backdrop-filter: blur(6px);
        z-index: 999999;
        display: flex;
        align-items: center;
        justify-content: center;
        animation: fadeIn 0.4s ease;
        padding: 20px;
    `;
    
    const modal = document.createElement('div');
    modal.style.cssText = `
        background: #FFFFFF;
        border-radius: 24px;
        max-width: 560px;
        width: 95%;
        padding: 36px 32px 28px;
        box-shadow: 0 30px 80px rgba(0,0,0,0.3);
        animation: modalSlideUp 0.4s ease;
        max-height: 90vh;
        overflow-y: auto;
    `;
    
    modal.innerHTML = `
        <div style="text-align: center; margin-bottom: 20px;">
            <div style="font-size: 56px; margin-bottom: 8px;">✅</div>
            <h2 style="font-size: 24px; font-weight: 900; color: #0F172A; margin-bottom: 4px;">¡Cotización generada exitosamente!</h2>
            <p style="font-size: 14px; color: #64748B;">La cotización ha sido oficializada y registrada en el sistema.</p>
        </div>
        
        <div style="background: #F8FAFC; border-radius: 16px; padding: 16px 20px; margin-bottom: 20px; border: 1px solid #E5E7EB;">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px; font-size: 13px;">
                <div><span style="color: #64748B; font-weight: 600;">📄 N° Cotización</span></div>
                <div style="font-weight: 900; color: #EF233C; text-align: right;">${esc(numeroCotizacion)}</div>
                
                <div><span style="color: #64748B; font-weight: 600;">🕐 Fecha y hora</span></div>
                <div style="font-weight: 700; color: #0F172A; text-align: right;">${fechaHora}</div>
                
                <div><span style="color: #64748B; font-weight: 600;">🏢 Cliente</span></div>
                <div style="font-weight: 700; color: #0F172A; text-align: right; word-break: break-word;">${esc(razon)}</div>
                
                <div><span style="color: #64748B; font-weight: 600;">📋 RUC</span></div>
                <div style="font-weight: 700; color: #0F172A; text-align: right;">${esc(ruc)}</div>
                
                <div><span style="color: #64748B; font-weight: 600;">📦 Productos</span></div>
                <div style="font-weight: 700; color: #0F172A; text-align: right;">${productosCount} items</div>
                
                <div><span style="color: #64748B; font-weight: 600;">💰 Subtotal</span></div>
                <div style="font-weight: 700; color: #0F172A; text-align: right;">${subtotal}</div>
                
                <div><span style="color: #64748B; font-weight: 600;">📊 IGV 18%</span></div>
                <div style="font-weight: 700; color: #0F172A; text-align: right;">${igv}</div>
            </div>
            
            <div style="border-top: 2px solid #EF233C; margin-top: 12px; padding-top: 12px; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 18px; font-weight: 900; color: #0F172A;">TOTAL</span>
                <span style="font-size: 26px; font-weight: 1000; color: #EF233C; letter-spacing: -0.5px;">${total}</span>
            </div>
        </div>
        
        <div style="display: flex; gap: 10px; flex-wrap: wrap; justify-content: center;">
            <button class="success-close-btn" style="
                padding: 10px 28px;
                border-radius: 12px;
                border: 1px solid #E5E7EB;
                background: #FFFFFF;
                color: #0F172A;
                font-weight: 800;
                font-size: 13px;
                cursor: pointer;
                transition: all 0.2s;
            ">Cerrar</button>
            ${cotizacionId ? `
            <button class="success-pdf-btn" style="
                padding: 10px 28px;
                border-radius: 12px;
                border: none;
                background: #2563EB;
                color: #FFFFFF;
                font-weight: 800;
                font-size: 13px;
                cursor: pointer;
                transition: all 0.2s;
                box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
            ">📄 Descargar PDF</button>
            ` : ''}
            <button class="success-email-btn" style="
                padding: 10px 28px;
                border-radius: 12px;
                border: none;
                background: #16A34A;
                color: #FFFFFF;
                font-weight: 800;
                font-size: 13px;
                cursor: pointer;
                transition: all 0.2s;
                box-shadow: 0 4px 14px rgba(22, 163, 74, 0.35);
            ">✉ Enviar al cliente</button>
        </div>
    `;
    
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    
    // Event listeners
    modal.querySelector('.success-close-btn').addEventListener('click', function() {
        overlay.remove();
        loadCotizaciones();
    });
    
    // ✅ BOTÓN PDF QUE FUNCIONA
    if (cotizacionId) {
        modal.querySelector('.success-pdf-btn').addEventListener('click', function() {
            console.log(`📄 Generando PDF para cotización ID: ${cotizacionId}`);
            if (typeof window.generateCotizacionPdf === 'function') {
                window.generateCotizacionPdf(cotizacionId);
            } else {
                const url = `/ventas/api/cotizaciones/${cotizacionId}/pdf`;
                window.open(url, '_blank');
            }
        });
    }
    
    modal.querySelector('.success-email-btn').addEventListener('click', function() {
        showToast('✉ Enviando email al cliente...', 'info');
        setTimeout(() => {
            showToast('✅ Email enviado correctamente', 'success');
        }, 1500);
    });
    
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) {
            overlay.remove();
            loadCotizaciones();
        }
    });
}



// ============================================================
// FUNCIÓN AUXILIAR PARA MENÚS CON CIERRE AUTOMÁTICO
// ============================================================

/**
 * Crea un menú emergente con cierre automático al hacer clic fuera
 */
function createMenuWithClose(event, htmlContent) {
    // Remover menús existentes
    document.querySelectorAll('.menu-pop').forEach(el => el.remove());
    
    const pop = document.createElement('div');
    pop.className = 'menu-pop';
    const left = Math.max(10, event.clientX - 250);
    const top = Math.min(window.innerHeight - 420, event.clientY + 8);
    pop.style.left = left + 'px';
    pop.style.top = top + 'px';
    pop.innerHTML = htmlContent;
    document.body.appendChild(pop);
    
    // 🔽 FUNCIÓN PARA CERRAR EL MENÚ 🔽
    const closeMenu = function(e) {
        // Si el clic NO fue dentro del menú, cerrarlo
        if (!pop.contains(e.target)) {
            pop.remove();
            // Remover los event listeners
            document.removeEventListener('click', closeMenu);
            document.removeEventListener('contextmenu', closeMenu);
            document.removeEventListener('scroll', closeMenu);
        }
    };
    
    // 🔽 CERRAR AL HACER CLIC EN CUALQUIER PARTE (con delay para evitar cierre inmediato) 🔽
    setTimeout(() => {
        document.addEventListener('click', closeMenu);
        document.addEventListener('contextmenu', closeMenu);
        // También cerrar al hacer scroll
        document.addEventListener('scroll', closeMenu);
    }, 10);
    
    // 🔽 CERRAR CON TECLA ESC 🔽
    const closeOnEsc = function(e) {
        if (e.key === 'Escape') {
            pop.remove();
            document.removeEventListener('keydown', closeOnEsc);
            document.removeEventListener('click', closeMenu);
            document.removeEventListener('contextmenu', closeMenu);
            document.removeEventListener('scroll', closeMenu);
        }
    };
    document.addEventListener('keydown', closeOnEsc);
    
    // Retornar el pop para uso posterior
    return pop;
}


function showCotizacionMenu(event, id) {
    event.stopPropagation();
    
    // Remover menús existentes
    document.querySelectorAll('.menu-pop').forEach(el => el.remove());
    
    const cotizacion = cotizacionesData.find(c => c.id === id);
    const estado = cotizacion?.estado || '';
    const isAccepted = estado === 'Aceptada por Cliente' || estado === 'Aceptada';
    const isGenerated = estado === 'Generada';
    
    let menuHtml = `
        <button class="menu-edit" onclick="openCotizacionModal(${id});this.closest('.menu-pop').remove()">👁 Ver / Editar</button>
        <button class="menu-duplicate" onclick="duplicateCotizacion(${id});this.closest('.menu-pop').remove()">⧉ Duplicar</button>
        <button class="menu-email" onclick="sendCotizacionEmail(${id});this.closest('.menu-pop').remove()">✉ Email</button>
        <button class="menu-preview" onclick="previewCotizacionPdf(${id});this.closest('.menu-pop').remove()" style="color:#8B5CF6;font-weight:900;">
            👁️ Vista Previa
        </button>
        <button class="menu-pdf" onclick="generateCotizacionPdf(${id});this.closest('.menu-pop').remove()">📄 Descargar PDF</button>
        <div class="menu-divider"></div>
    `;
    
    if (isGenerated && !isAccepted) {
        menuHtml += `
            <button class="menu-accepted" onclick="marcarCotizacionAccepted(${id});this.closest('.menu-pop').remove()">✅ Aceptada por Cliente</button>
        `;
    }
    
    // Orden pedido en el Excel de pendientes: 1) Crear despacho, 2) Crear guía, 3) Crear factura en KCF
    menuHtml += `
        <button class="menu-despacho" onclick="createDocFromCotizacion(${id},'despacho');this.closest('.menu-pop').remove()">🚚 Crear despacho</button>
    `;
    if (isAccepted) {
        menuHtml += `
            <button class="menu-guia" onclick="createDocFromCotizacion(${id},'guia');this.closest('.menu-pop').remove()">📦 Crear guía</button>
            <button class="menu-factura" onclick="createDocFromCotizacion(${id},'factura');this.closest('.menu-pop').remove()">🧾 Crear factura en KCF</button>
        `;
    }
    
    menuHtml += `
        <div class="menu-divider"></div>
        <button class="danger" onclick="deleteCotizacion(${id});this.closest('.menu-pop').remove()">🗑 Eliminar</button>
    `;
    
    // Crear el menú con la función mejorada
    const pop = createMenuWithClose(event, menuHtml);
    
    // 🔽 AGREGAR: Cerrar el menú al hacer clic en cualquier parte de la pantalla 🔽
    const closeGlobalMenu = function(e) {
        if (pop && !pop.contains(e.target)) {
            pop.remove();
            document.removeEventListener('click', closeGlobalMenu);
            document.removeEventListener('contextmenu', closeGlobalMenu);
        }
    };
    
    // Delay para evitar que el clic que abrió el menú lo cierre inmediatamente
    setTimeout(() => {
        document.addEventListener('click', closeGlobalMenu);
        document.addEventListener('contextmenu', closeGlobalMenu);
    }, 50);
}

function showPedidoMenu(event, id) {
    event.stopPropagation();
    document.querySelectorAll('.menu-pop').forEach(el => el.remove());
    
    // Buscar el PC para ver su estado
    const pedido = pedidosData.find(p => p.id === id);
    const estado = pedido?.estado || 'Desconocido';
    const esAnulado = estado === 'Anulado';
    const esValidado = estado === 'Validado por Hellen' || estado === 'Validado';
    
    const pop = document.createElement('div');
    pop.className = 'menu-pop';
    const left = Math.max(10, event.clientX - 250);
    const top = Math.min(window.innerHeight - 420, event.clientY + 8);
    pop.style.left = left + 'px';
    pop.style.top = top + 'px';
    
    let menuHtml = `
        <button onclick="openPedidoCompraModalSAP('editar', ${id});this.closest('.menu-pop').remove()">👁 Ver / Editar</button>
    `;
    
    // Solo mostrar "Validación" si NO está validado
    if (!esValidado && !esAnulado) {
        menuHtml += `
            <button onclick="validatePedidoCompra(${id});this.closest('.menu-pop').remove()">✅ Validar PC</button>
        `;
    } else if (esValidado) {
        menuHtml += `
            <button disabled style="opacity:0.5;cursor:not-allowed;">✅ Ya validado</button>
        `;
    } else if (esAnulado) {
        menuHtml += `
            <button disabled style="opacity:0.5;cursor:not-allowed;">⛔ Anulado</button>
        `;
    }
    
    menuHtml += `
        <button onclick="createDespachoFromPedido(${id});this.closest('.menu-pop').remove()">🚚 Crear despacho</button>
        <button onclick="createGuiaFromPedido(${id});this.closest('.menu-pop').remove()">📦 Crear guía</button>
        <button onclick="createFacturaFromPedido(${id});this.closest('.menu-pop').remove()">🧾 Crear factura</button>
        <button onclick="imprimirRotulo('pc', ${id});this.closest('.menu-pop').remove()" style="color:#7C3AED;font-weight:900;">🏷️ Imprimir rótulo</button>
        <div style="height:1px;background:#E5E7EB;margin:4px 0;"></div>
        <button class="danger" onclick="deletePedidoCompra(${id});this.closest('.menu-pop').remove()">
            🗑 Eliminar permanentemente ${estado !== 'Anulado' ? '(Se anulará primero)' : ''}
        </button>
    `;
    
    pop.innerHTML = menuHtml;
    document.body.appendChild(pop);
}

// ============================================================
// 🏢 MULTIEMPRESA: el remitente de la guía es la empresa elegida arriba (antes siempre KCF)
// ============================================================
function aplicarEmpresaAlOrigen(origen) {
    const e = window.EMPRESA_ACTIVA || {};
    if (!e.ruc || e.ruc === origen.ruc) return origen;
    origen.ruc = e.ruc;
    origen.nombre = e.razon_social || origen.nombre;
    origen.direccion = e.direccion_fiscal || origen.direccion;
    if (e.ubigeo) origen.ubigeo = e.ubigeo;
    return origen;
}
window.aplicarEmpresaAlOrigen = aplicarEmpresaAlOrigen;

// ============================================================
// 🏷️ RÓTULO DE PC Y DESPACHO (con logo, datos y color de la empresa del documento)
// ============================================================
function imprimirRotulo(tipo, id) {
    const n = prompt('¿Cuántas cajas o bultos son? Sale una hoja por caja (01/03, 02/03...).', '1');
    if (n === null) return;
    const bultos = Math.max(1, Math.min(99, parseInt(n, 10) || 1));
    window.open(`/ventas/api/rotulo/${tipo}/${id}?bultos=${bultos}`, '_blank');
}
window.imprimirRotulo = imprimirRotulo;

function showGuiaMenu(event, id) {
    event.stopPropagation();
    document.querySelectorAll('.menu-pop').forEach(el => el.remove());
    
    const pop = document.createElement('div');
    pop.className = 'menu-pop';
    const left = Math.max(10, event.clientX - 250);
    const top = Math.min(window.innerHeight - 420, event.clientY + 8);
    pop.style.left = left + 'px';
    pop.style.top = top + 'px';
    
    // Buscar la guía para ver su estado
    const guia = guiasData.find(g => g.id === id);
    const estado = (guia?.estado || '').toUpperCase();
    
    const isEmitida = estado === 'EMITIDA' || estado === 'ENTREGADA';
    const isGenerada = estado === 'GENERADA' || estado === 'EMITIDA' || estado === 'EMITIDO' || estado === 'ACEPTADA' || estado === 'ACEPTADO';
    
    let menuHtml = `
        <button onclick="openGuiaModal(${id});this.closest('.menu-pop').remove()">👁 Ver / Editar</button>
        <button onclick="previewGuiaPdf(${id});this.closest('.menu-pop').remove()" style="color:#8B5CF6;font-weight:900;">👁️ Vista Previa</button>
        <button onclick="generateGuiaPdf(${id});this.closest('.menu-pop').remove()">📄 Descargar PDF</button>
        <button onclick="crearFacturaDesdeGuia(${id});this.closest('.menu-pop').remove()" style="color:#1D4ED8;font-weight:900;">🧾 Crear factura</button>
    `;
    
    // 🔽 MOSTRAR OPCIÓN DE RÓTULO SOLO SI ESTÁ GENERADA/EMITIDA 🔽
    if (isGenerada) {
        menuHtml += `
            <div style="height:1px;background:#E5E7EB;margin:4px 0;"></div>
            <button onclick="previewRotuloGuia(${id});this.closest('.menu-pop').remove()" 
                    style="color:#8B5CF6;font-weight:900;">
                🏷️ Imprimir rótulo
            </button>
            <button onclick="descargarRotuloGuia(${id});this.closest('.menu-pop').remove()" 
                    style="color:#7C3AED;font-weight:900;">
                🏷️ Descargar Rótulo
            </button>
        `;
    }
    
    if (!isEmitida) {
        menuHtml += `
            <div style="height:1px;background:#E5E7EB;margin:4px 0;"></div>
            <button onclick="markGuiaEmitida(${id});this.closest('.menu-pop').remove()">📄 Emitir</button>
        `;
    } else {
        menuHtml += `
            <button disabled style="opacity:0.5;cursor:not-allowed;">✅ Ya emitida</button>
        `;
    }
    
    menuHtml += `
        <div style="height:1px;background:#E5E7EB;margin:4px 0;"></div>
        <button class="danger" onclick="deleteGuia(${id});this.closest('.menu-pop').remove()">🗑 Eliminar</button>
    `;
    
    pop.innerHTML = menuHtml;
    document.body.appendChild(pop);
}



function showComprobanteMenu(event, id) {
    event.stopPropagation();
    document.querySelectorAll('.menu-pop').forEach(el => el.remove());
    
    const pop = document.createElement('div');
    pop.className = 'menu-pop';
    const left = Math.max(10, event.clientX - 250);
    const top = Math.min(window.innerHeight - 420, event.clientY + 8);
    pop.style.left = left + 'px';
    pop.style.top = top + 'px';

    pop.innerHTML = `
        <button onclick="openComprobanteModal(${id});this.closest('.menu-pop').remove()">👁 Ver / Editar</button>
        <button onclick="previewComprobantePdf(${id});this.closest('.menu-pop').remove()" style="color:#8B5CF6;font-weight:900;">👁️ Vista Previa</button>
        <button onclick="generateComprobantePdf(${id});this.closest('.menu-pop').remove()">📄 Descargar PDF</button>
        <button onclick="markComprobanteEmitido(${id});this.closest('.menu-pop').remove()">📄 Emitir</button>
        <div style="height:1px;background:#E5E7EB;margin:4px 0;"></div>
        <button class="danger" onclick="deleteComprobante(${id});this.closest('.menu-pop').remove()">🗑 Eliminar</button>
    `;
    document.body.appendChild(pop);
}

function showNotaMenu(event, id) {
    event.stopPropagation();
    document.querySelectorAll('.menu-pop').forEach(el => el.remove());
    
    const pop = document.createElement('div');
    pop.className = 'menu-pop';
    const left = Math.max(10, event.clientX - 250);
    const top = Math.min(window.innerHeight - 420, event.clientY + 8);
    pop.style.left = left + 'px';
    pop.style.top = top + 'px';
    
    pop.innerHTML = `
        <button onclick="openNotaCreditoModal(${id});this.closest('.menu-pop').remove()">👁 Ver / Editar</button>
        <button onclick="generateNotaPdf(${id});this.closest('.menu-pop').remove()">▣ PDF</button>
        <button onclick="markNotaEmitida(${id});this.closest('.menu-pop').remove()">📄 Emitir</button>
        <button class="danger" onclick="deleteNota(${id});this.closest('.menu-pop').remove()">🗑 Eliminar</button>
    `;
    document.body.appendChild(pop);
}

function showDevolucionMenu(event, id) {
    event.stopPropagation();
    document.querySelectorAll('.menu-pop').forEach(el => el.remove());
    
    const pop = document.createElement('div');
    pop.className = 'menu-pop';
    const left = Math.max(10, event.clientX - 250);
    const top = Math.min(window.innerHeight - 420, event.clientY + 8);
    pop.style.left = left + 'px';
    pop.style.top = top + 'px';
    
    pop.innerHTML = `
        <button onclick="openDevolucionModal(${id});this.closest('.menu-pop').remove()">👁 Ver / Editar</button>
        <button onclick="approveDevolucion(${id});this.closest('.menu-pop').remove()">✅ Aprobar</button>
        <button onclick="rejectDevolucion(${id});this.closest('.menu-pop').remove()">❌ Rechazar</button>
        <button class="danger" onclick="deleteDevolucion(${id});this.closest('.menu-pop').remove()">🗑 Eliminar</button>
    `;
    document.body.appendChild(pop);
}

// Agregar esta función
function updateValidationIcon(elementId, isValid) {
    const el = document.getElementById(elementId);
    if (el) {
        el.textContent = isValid ? '✅' : '❌';
        el.style.color = isValid ? '#16A34A' : '#DC2626';
    }
}



function inicializarSwitchesValidacion() {
    console.log('🔄 Inicializando switches de validación...');
    
    const validations = [
        'vPrecio', 'vProducto', 'vEntrega', 
        'vTransporte', 'vCantidad', 'vMoneda', 'vVigencia'
    ];
    
    validations.forEach(id => {
        const checkbox = document.getElementById(id);
        if (checkbox) {
            // 🔽 FORZAR A QUE ESTÉN DESMARCADOS (NO VÁLIDO)
            checkbox.checked = false;
            
            // Remover listeners anteriores para evitar duplicados
            checkbox.removeEventListener('change', updateValidationStatus);
            checkbox.addEventListener('change', updateValidationStatus);
            
            // Actualizar el label inicial
            const label = document.getElementById(id + 'Label');
            if (label) {
                // 🔽 SIEMPRE MOSTRAR "NO VÁLIDO"
                label.textContent = '❌ No válido';
                label.style.color = '#DC2626';
            }
        }
    });
    
    // Actualizar estado inicial del semáforo
    setTimeout(() => {
        updateValidationStatus();
        console.log('✅ Switches de validación inicializados en "NO VÁLIDO"');
    }, 100);
}

// ============================================================
// FUNCIONES PARA CAMPOS PERSONALIZADOS
// ============================================================

/**
 * Muestra/oculta el campo de entrada personalizado cuando se selecciona "Personalizado"
 * @param {string} selectId - ID del select
 * @param {string} inputId - ID del input personalizado
 */
function toggleCustomField(selectId, inputId) {
    const select = document.getElementById(selectId);
    const input = document.getElementById(inputId);
    
    if (!select || !input) return;
    
    if (select.value === 'Personalizado') {
        input.style.display = 'block';
        input.focus();
    } else {
        input.style.display = 'none';
        input.value = '';
    }
}

/**
 * Obtiene el valor de un campo (incluyendo el valor personalizado si está seleccionado)
 * @param {string} selectId - ID del select
 * @param {string} inputId - ID del input personalizado
 * @returns {string} - Valor seleccionado o personalizado
 */
function getFieldValue(selectId, inputId) {
    const select = document.getElementById(selectId);
    const input = document.getElementById(inputId);
    
    if (!select) return '';
    
    if (select.value === 'Personalizado' && input) {
        return input.value.trim() || select.value;
    }
    
    return select.value;
}

/**
 * Establece el valor de un campo, soportando valores personalizados
 * @param {string} selectId - ID del select
 * @param {string} inputId - ID del input personalizado
 * @param {string} value - Valor a establecer
 */
function setFieldValue(selectId, inputId, value) {
    const select = document.getElementById(selectId);
    const input = document.getElementById(inputId);
    
    if (!select) return;
    
    // Si el valor es null o undefined, no hacer nada
    if (value === null || value === undefined) return;
    
    // Verificar si el valor está en las opciones del select
    let found = false;
    for (let opt of select.options) {
        if (opt.value === value) {
            opt.selected = true;
            found = true;
            break;
        }
    }
    
    if (!found && input) {
        // Si no está en las opciones, seleccionar "Personalizado" y poner el valor en el input
        select.value = 'Personalizado';
        input.value = value;
        input.style.display = 'block';
    } else if (input) {
        // Si está en las opciones, ocultar el input personalizado
        input.style.display = 'none';
        input.value = '';
    }
}

window.initVentas = async function(tab) {
    console.log(`🚀 Inicializando ventas con tab: ${tab}`);
    currentModule = tab || 'cotizaciones';
    
    await Promise.all([
        cargarProductosMaestros(),
        cargarClientesMaestros()
    ]);
    
    // Cargar cotizaciones primero (necesario para PC y validación)
    await loadCotizaciones();
    
    switch(currentModule) {
        case 'cotizaciones':
            break;
        case 'pedido_compra':
            await loadPedidos();
            break;
        case 'validacion':
            await loadPedidos();
            renderValidacion();
            break;
        case 'despachar':
            await loadDespachos();
            break;
        case 'guias':
            await loadGuias();
            break;
        case 'comprobantes':
            await loadComprobantes();
            break;
        case 'notas_credito':
            await loadComprobantes();
            await loadNotas();
            break;
        case 'devoluciones':
            await loadDevoluciones();
            break;
        case 'eliminadas': 
            await loadEliminadas();
            break;
        case 'revision':  // 🔽 NUEVO
            await loadRevision();
            break;
        default:
            break;
    }
    
    // Si es validación, asegurar render
    if (currentModule === 'validacion') {
        renderValidacion();
    }
    
    console.log('✅ Módulo Ventas inicializado correctamente');
};

// ============================================================
// EVENT LISTENERS
// ============================================================
document.addEventListener('DOMContentLoaded', function() {
    console.log('🔄 ventas.js: DOMContentLoaded');
    
    // Configurar eventos de búsqueda
    const searchInputs = [
        { id: 'qSearch', module: 'cotizaciones' },
        { id: 'pcSearch', module: 'pedido_compra' },
        { id: 'despachoSearch', module: 'despachar' },
        { id: 'guiaSearch', module: 'guias' },
        { id: 'comprobanteSearch', module: 'comprobantes' },
        { id: 'notaSearch', module: 'notas_credito' },
        { id: 'devolucionSearch', module: 'devoluciones' }
    ];
    
    searchInputs.forEach(({ id, module }) => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('input', function() {
                switch(module) {
                    case 'cotizaciones': renderCotizaciones(); break;
                    case 'pedido_compra': renderPedidos(); break;
                    case 'despachar': renderDespachos(); break;
                    case 'guias': renderGuias(); break;
                    case 'comprobantes': renderComprobantes(); break;
                    case 'notas_credito': renderNotas(); break;
                    case 'devoluciones': renderDevoluciones(); break;
                }
            });
        }
    });
    
    // Configurar eventos de filtros de estado
    const statusSelects = [
        { id: 'qStatus', module: 'cotizaciones' },
        { id: 'pcStatus', module: 'pedido_compra' },
        { id: 'despachoStatus', module: 'despachar' },
        { id: 'guiaStatus', module: 'guias' },
        { id: 'comprobanteStatus', module: 'comprobantes' },
        { id: 'notaStatus', module: 'notas_credito' },
        { id: 'devolucionStatus', module: 'devoluciones' }
    ];
    
    statusSelects.forEach(({ id, module }) => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('change', function() {
                switch(module) {
                    case 'cotizaciones': renderCotizaciones(); break;
                    case 'pedido_compra': renderPedidos(); break;
                    case 'despachar': renderDespachos(); break;
                    case 'guias': renderGuias(); break;
                    case 'comprobantes': renderComprobantes(); break;
                    case 'notas_credito': renderNotas(); break;
                    case 'devoluciones': renderDevoluciones(); break;
                }
            });
        }
    });
    
    // ============================================================
    // EVENTOS PARA FILTROS DE FECHA - DESPACHOS
    // ============================================================
    const despachoFechaInicio = document.getElementById('despachoFechaInicio');
    const despachoFechaFin = document.getElementById('despachoFechaFin');
    
    if (despachoFechaInicio) {
        despachoFechaInicio.addEventListener('change', function() {
            renderDespachos();
        });
    }
    if (despachoFechaFin) {
        despachoFechaFin.addEventListener('change', function() {
            renderDespachos();
        });
    }
    
    // ============================================================
    // EVENTOS PARA FILTROS DE FECHA - GUÍAS
    // ============================================================
    const guiaFechaInicio = document.getElementById('guiaFechaInicio');
    const guiaFechaFin = document.getElementById('guiaFechaFin');
    
    if (guiaFechaInicio) {
        guiaFechaInicio.addEventListener('change', function() {
            renderGuias();
        });
    }
    if (guiaFechaFin) {
        guiaFechaFin.addEventListener('change', function() {
            renderGuias();
        });
    }
    
    // ============================================================
    // EVENTOS PARA FILTROS DE FECHA - COMPROBANTES (FACTURAS)
    // ============================================================
    const comprobanteFechaInicio = document.getElementById('comprobanteFechaInicio');
    const comprobanteFechaFin = document.getElementById('comprobanteFechaFin');
    
    if (comprobanteFechaInicio) {
        comprobanteFechaInicio.addEventListener('change', function() {
            renderComprobantes();
        });
    }
    if (comprobanteFechaFin) {
        comprobanteFechaFin.addEventListener('change', function() {
            renderComprobantes();
        });
    }
    
    // ============================================================
    // EVENTOS PARA FILTROS DE FECHA - NOTAS DE CRÉDITO (opcional)
    // ============================================================
    const notaFechaInicio = document.getElementById('notaFechaInicio');
    const notaFechaFin = document.getElementById('notaFechaFin');
    
    if (notaFechaInicio) {
        notaFechaInicio.addEventListener('change', function() {
            renderNotas();
        });
    }
    if (notaFechaFin) {
        notaFechaFin.addEventListener('change', function() {
            renderNotas();
        });
    }
    
    // ============================================================
    // EVENTOS PARA FILTROS DE FECHA - DEVOLUCIONES (opcional)
    // ============================================================
    const devolucionFechaInicio = document.getElementById('devolucionFechaInicio');
    const devolucionFechaFin = document.getElementById('devolucionFechaFin');
    
    if (devolucionFechaInicio) {
        devolucionFechaInicio.addEventListener('change', function() {
            renderDevoluciones();
        });
    }
    if (devolucionFechaFin) {
        devolucionFechaFin.addEventListener('change', function() {
            renderDevoluciones();
        });
    }
    
    // ============================================================
    // INICIALIZAR CON EL TAB DE LA URL
    // ============================================================
    const urlParams = new URLSearchParams(window.location.search);
    const tab = urlParams.get('tab') || 'cotizaciones';
    
    if (typeof initVentas === 'function') {
        initVentas(tab);
    } else {
        console.warn('⚠️ initVentas no está disponible');
    }
});
// ============================================================
// EXPORTAR TODAS LAS FUNCIONES AL WINDOW
// ============================================================

console.log('📦 Exportando funciones al window...');

// ============================================================
// 1. FUNCIONES PRINCIPALES (¡LAS MÁS IMPORTANTES!)
// ============================================================
window.initVentas = initVentas;
window.loadCotizaciones = loadCotizaciones;
window.loadPedidos = loadPedidos;
window.loadDespachos = loadDespachos;
window.loadGuias = loadGuias;
window.loadComprobantes = loadComprobantes;
window.loadNotas = loadNotas;
window.loadDevoluciones = loadDevoluciones;

// ============================================================
// 2. FUNCIONES DE RENDER
// ============================================================
window.renderCotizaciones = renderCotizaciones;
window.renderPedidos = renderPedidos;
window.renderDespachos = renderDespachos;
window.renderGuias = renderGuias;
window.renderComprobantes = renderComprobantes;
window.renderNotas = renderNotas;
window.renderDevoluciones = renderDevoluciones;
window.renderValidacion = renderValidacion;

// ============================================================
// 3. FUNCIONES DE VISTA
// ============================================================
window.setCotizacionView = setCotizacionView;
window.setPedidoView = setPedidoView;
window.descargarRotuloGuia = descargarRotuloGuia;
window.previewRotuloGuia = previewRotuloGuia;
// ============================================================
// 4. FUNCIONES DE VALIDACIÓN
// ============================================================
window.updateValidationStatus = updateValidationStatus;
window.updateValidationSemaphore = updateValidationSemaphore;  // <--- ESTA FALTABA
window.updateValidationIcon = updateValidationIcon;
window.inicializarSwitchesValidacion = inicializarSwitchesValidacion;
window.validarPCSAP = validarPCSAP;
window.solicitarCorreccion = solicitarCorreccion;
window.generarOrdenCompra = generarOrdenCompra;
window.enviarADespacho = enviarADespacho;

window.cargarUnidadesDeMedidaGuia = cargarUnidadesDeMedidaGuia;

window.clearDespachoDateFilter = clearDespachoDateFilter;
window.clearGuiaDateFilter = clearGuiaDateFilter;
window.clearComprobanteDateFilter = clearComprobanteDateFilter;
// ============================================================
// 5. FUNCIONES DE MODALES PRINCIPALES
// ============================================================
window.openCotizacionModal = openCotizacionModal;
window.openPedidoCompraModalSAP = openPedidoCompraModalSAP;
window.openPedidoCompraModal = openPedidoCompraModal;  // Versión antigua
window.openDespachoModal = openDespachoModal;
window.openGuiaModal = openGuiaModal;
window.openComprobanteModal = openComprobanteModal;
window.openNotaCreditoModal = openNotaCreditoModal;
window.openDevolucionModal = openDevolucionModal;
window.cargarDatosComprobanteAfectado = cargarDatosComprobanteAfectado;
window.loadComprobanteFromGuia = loadComprobanteFromGuia;
window.loadComprobanteFromPC = loadComprobanteFromPC;

// ============================================================
// 6. FUNCIONES DE COTIZACIÓN
// ============================================================
window.generateCotizacionPdf = generateCotizacionPdf;
window.previewCotizacionPdf = previewCotizacionPdf;
window.createDocFromCotizacion = createDocFromCotizacion;
window.duplicateCotizacion = duplicateCotizacion;
window.deleteCotizacion = deleteCotizacion;
window.marcarCotizacionAccepted = marcarCotizacionAccepted;
window.marcarDespachado = marcarDespachado;
window.validateByHellen = validateByHellen;
window.sendCotizacionToReview = sendCotizacionToReview;
window.generateCotizacionPdfAndSend = generateCotizacionPdfAndSend;
window.saveCotizacionDraft = saveCotizacionDraft;

// ============================================================
// 7. FUNCIONES DE SELECTOR DE PRODUCTOS
// ============================================================
window.openProductSelector = openProductSelector;
window.renderProductSelector = renderProductSelector;
window.toggleProductSelection = toggleProductSelection;
window.selectAllProducts = selectAllProducts;
window.deselectAllProducts = deselectAllProducts;
window.filterProductSelector = filterProductSelector;
window.addSelectedProducts = addSelectedProducts;
window.toggleAllProductCheckboxes = toggleAllProductCheckboxes;
window.togglePagoCampos = togglePagoCampos;

// ============================================================
// 8. FUNCIONES DE SELECTOR DE PRODUCTOS PC
// ============================================================
window.openProductSelectorPC = openProductSelectorPC;
window.renderProductSelectorPc = renderProductSelectorPc;
window.toggleProductSelectionPc = toggleProductSelectionPc;
window.selectAllProductsPc = selectAllProductsPc;
window.deselectAllProductsPc = deselectAllProductsPc;
window.filterProductSelectorPc = filterProductSelectorPc;
window.addSelectedProductsPc = addSelectedProductsPc;
window.toggleAllProductCheckboxesPc = toggleAllProductCheckboxesPc;
window.agregarItemPCTable = agregarItemPCTable;

// ============================================================
// 9. FUNCIONES DE PC SAP
// ============================================================
window.openPedidoCompraModalSAP = openPedidoCompraModalSAP;
window.clearPedidoModalSAP = clearPedidoModalSAP;
window.addPedidoItemSAP = addPedidoItemSAP;
window.eliminarItemSAP = eliminarItemSAP;
window.reordenarItemsSAP = reordenarItemsSAP;
window.savePedidoCompraSAP = savePedidoCompraSAP;
window.buscarCotizacionSAP = buscarCotizacionSAP;
window.seleccionarCotizacionSAP = seleccionarCotizacionSAP;
window.loadPedidoCotizacionSAP = loadPedidoCotizacionSAP;
window.actualizarFaltanteSAP = actualizarFaltanteSAP;
window.actualizarPrecioPCSAP = actualizarPrecioPCSAP;
window.actualizarValorTotalPCSAP = actualizarValorTotalPCSAP;
window.actualizarFaltanteDesdeInput = actualizarFaltanteDesdeInput;

// ============================================================
// 10. FUNCIONES DE CREACIÓN DESDE COTIZACIÓN
// ============================================================
window.openGuiaModalWithData = openGuiaModalWithData;
window.openComprobanteModalWithData = openComprobanteModalWithData;
window.openDespachoModalWithData = openDespachoModalWithData;
window.loadGuiaFromCotizacion = loadGuiaFromCotizacion;

// ============================================================
// 11. FUNCIONES DE MENÚS
// ============================================================
window.showCotizacionMenu = showCotizacionMenu;
window.showPedidoMenu = showPedidoMenu;
window.showGuiaMenu = showGuiaMenu;
window.showComprobanteMenu = showComprobanteMenu;
window.showNotaMenu = showNotaMenu;
window.showDevolucionMenu = showDevolucionMenu;
window.createMenuWithClose = createMenuWithClose;

window.generateComprobantePdf = generateComprobantePdf;
window.previewComprobantePdf = previewComprobantePdf;

// ============================================================
// 12. FUNCIONES DE PRODUCTOS Y CLIENTES
// ============================================================
window.cargarProductosMaestros = cargarProductosMaestros;
window.cargarClientesMaestros = cargarClientesMaestros;
window.cargarDatalistProductos = cargarDatalistProductos;
window.productTableHtml = productTableHtml;

// ============================================================
// 13. FUNCIONES DE UTILIDAD
// ============================================================
window.closeModal = closeModal;
window.clearDateFilter = clearDateFilter;
window.clearPcDateFilter = clearPcDateFilter;
window.exportData = exportData;
window.showSuccessModal = showSuccessModal;
window.showConfirmModal = showConfirmModal;
window.showDeleteConfirmModal = showDeleteConfirmModal;
window.setFieldValue = setFieldValue;
window.getFieldValue = getFieldValue;
window.toggleCustomField = toggleCustomField;
window.setEditableValue = setEditableValue;
window.deletePedidoCompra = deletePedidoCompra;
window.deleteGuia = deleteGuia;
window.deleteComprobante = deleteComprobante;
window.deleteNota = deleteNota;
window.getDescripcionPrincipal = getDescripcionPrincipal;
window.badgeNuevo = badgeNuevo;


window.loadEliminadas = loadEliminadas;
window.renderEliminadas = renderEliminadas;
window.limpiarFiltrosEliminadas = limpiarFiltrosEliminadas;
window.verDetalleEliminada = verDetalleEliminada;
window.exportarEliminadasCSV = exportarEliminadasCSV;



// ============================================================
// EXPORTAR FUNCIONES DE REVISIÓN
// ============================================================
window.loadRevision = loadRevision;
window.renderRevision = renderRevision;
window.aceptarRevision = aceptarRevision;
window.rechazarRevision = rechazarRevision;
window.esUsuarioAutorizado = esUsuarioAutorizado;
window.getUsuarioRol = getUsuarioRol;
window.mostrarPestanasPorRol = mostrarPestanasPorRol;
// ============================================================
// 14. FUNCIONES DE FORMATO
// ============================================================
window.money = money;
window.badgeStatus = badgeStatus;
window.formatFecha = formatFecha;
window.formatearFecha = formatearFecha;
window.esc = esc;
window.sd = sd;
window.options = options;
window.today = today;
window.now = now;


console.log('✅ Todas las funciones exportadas al window correctamente');


// ============================================================
// REQUERIMIENTOS DEL EXCEL DE PENDIENTES (14/10/2026)
// ============================================================

// 1) PC despachado: letras negras con fondo azulito (CSS .fila-despachada en ventas.css)
function pcDespachado(r) {
    return r && (r.despacho_estado === 'Despachado' || r.despacho_estado === 'Entregado');
}
function badgeDespachoPc(r) {
    return pcDespachado(r) ? `<br><span class="badge badge-despachado">🚚 ${r.despacho_estado}</span>` : '';
}

// 4) "Pendiente por compra" / "Pendiente por recojo": lo calcula el servidor con el stock libre del grupo
//    (Inventario) y las órdenes de compra aprobadas (Compras). Ver routes/abastecimiento.py
const abastData = { pc: {}, cotizaciones: {}, despachos: {} };
const ABAST_ESTILOS = {
    'Pendiente por compra': { icono: '🛒', clase: 'abast-compra' },
    'Pendiente por recojo': { icono: '🚚', clase: 'abast-recojo' },
    'Por llegar': { icono: '📦', clase: 'abast-llegar' },
    'Con stock': { icono: '✅', clase: 'abast-ok' }
};
// Pedido de Erika 20/10/2026: en cotizaciones la etiqueta de abastecimiento ("Pendiente por compra") solo sale
// cuando el cliente ya aceptó (no en "Generada" ni antes).
function cotAceptadaCliente(r) {
    return ['Aceptada por Cliente', 'Aceptada'].includes(String((r && r.estado) || '').trim());
}
window.cotAceptadaCliente = cotAceptadaCliente;
function abastBadge(tipo, id) {
    const info = (abastData[tipo] || {})[id];
    if (!info || !info.estado) return '';
    const est = ABAST_ESTILOS[info.estado] || { icono: '•', clase: 'abast-ok' };
    const titulo = (info.detalle || []).join('\n').replace(/"/g, '&quot;');
    return `<br><span class="abast-badge ${est.clase}" title="${titulo}">${est.icono} ${info.estado}</span>`;
}
async function cargarAbastecimiento() {
    const tipos = ['pc', 'cotizaciones', 'despachos'];
    const respuestas = await Promise.all(tipos.map(t =>
        fetch(`/api/abastecimiento/${t}`, { credentials: 'same-origin' })
            .then(r => r.ok ? r.json() : null).catch(() => null)));
    respuestas.forEach((r, i) => { if (r && r.success) abastData[tipos[i]] = r.data || {}; });
    if (typeof pedidosData !== 'undefined' && pedidosData.length) renderPedidos();
    if (typeof cotizacionesData !== 'undefined' && cotizacionesData.length) renderCotizaciones();
    if (typeof despachosData !== 'undefined' && despachosData.length) renderDespachos();
}
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(cargarAbastecimiento, 1500);
    setInterval(cargarAbastecimiento, 120000);
});
window.cargarAbastecimiento = cargarAbastecimiento;

// 5) Crear la factura desde una guía de remisión: abre el comprobante con la guía ya vinculada
async function crearFacturaDesdeGuia(id) {
    const guia = (guiasData || []).find(g => g.id === id);
    if (!guia) {
        showToast('❌ Guía no encontrada', 'error');
        return;
    }
    if (guia.comprobante) {
        showToast(`ℹ️ Esta guía ya tiene el comprobante ${guia.comprobante}`, 'info');
        return;
    }
    await openComprobanteModal();
    const valor = `${guia.serie}-${guia.numero}`;
    const sel = document.getElementById('compGuia');
    if (!sel) return;
    if (![...sel.options].some(o => o.value === valor)) sel.add(new Option(valor, valor));
    sel.value = valor;
    loadComprobanteFromGuia(valor);
    if (typeof actualizarObservacionesComprobante === 'function') actualizarObservacionesComprobante();
    showToast(`🧾 Factura preparada con los datos de la guía ${valor}. Revisa y guarda.`, 'success');
}
window.crearFacturaDesdeGuia = crearFacturaDesdeGuia;

// ============================================================
// STOCK AUTOMÁTICO AL DESPACHAR / ANULAR (15/10/2026)
// ============================================================
async function prepararUbicacionDespacho(id) {
    let info;
    try {
        info = await apiFetch(`/ventas/api/despachos/${id}/ubicaciones`);
    } catch (e) {
        showToast('❌ No se pudo consultar el stock: ' + e.message, 'error');
        return null;
    }
    const opciones = info.opciones || [];
    if (!opciones.length) {
        showToast('❌ No hay empresas o sedes registradas', 'error');
        return null;
    }
    const primera = opciones[0];
    window._despOpciones = opciones;
    window._despUbicacion = primera.alcanza ? `${primera.empresa_id}|${primera.almacen_id}` : '';
    const opts = opciones.map(o => {
        const valor = `${o.empresa_id}|${o.almacen_id}`;
        const texto = o.alcanza ? `✅ ${o.empresa} · ${o.sede} (hay todo)`
                                : `⚠️ ${o.empresa} · ${o.sede} (falta ${o.faltan.length} producto(s))`;
        return `<option value="${valor}" ${valor === window._despUbicacion ? 'selected' : ''}>${texto}</option>`;
    }).join('');
    const productos = (info.productos || []).map(p => `${p.cantidad} × ${p.producto}`).join('<br>');
    const aviso = (info.sin_codigo || []).length
        ? `<div style="color:#B45309;font-size:12px;margin-top:6px">Sin código del catálogo (no se descuentan): ${info.sin_codigo.join(', ')}</div>` : '';
    const html = `
        <div style="text-align:left;margin-top:14px;background:#F8FAFC;border:1px solid #E2E8F0;border-radius:12px;padding:12px">
            <label style="font-weight:800;font-size:13px;color:#0F172A">¿De qué empresa y sede sale?</label>
            <select id="despUbicacion" onchange="window._despUbicacion=this.value"
                    style="width:100%;margin-top:6px;padding:8px;border-radius:8px;border:1px solid #CBD5E1;font-size:13px">
                ${window._despUbicacion ? '' : '<option value="" selected>— Elige empresa y sede —</option>'}${opts}
            </select>
            <div style="font-size:12px;color:#475569;margin-top:8px;max-height:90px;overflow:auto">${productos}</div>${aviso}
        </div>`;
    return { html };
}

// Error de stock al despachar: rojo, grande y diciendo qué producto falta y en qué sede (pedido de Erika 20/10/2026)
function mostrarErrorStockDespacho(faltan, mensaje, titulo) {
    document.getElementById('errorStockDespacho')?.remove();
    const esc = t => String(t ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    const num = n => Number(n || 0).toLocaleString('es-PE', { maximumFractionDigits: 2 });
    const filas = (faltan || []).map(f => `<tr>
            <td style="padding:8px;border-bottom:1px solid #FCA5A5;text-align:left"><b>${esc(f.producto)}</b></td>
            <td style="padding:8px;border-bottom:1px solid #FCA5A5">${esc(f.empresa)} · ${esc(f.sede)}</td>
            <td style="padding:8px;border-bottom:1px solid #FCA5A5;text-align:right">${num(f.pide)}</td>
            <td style="padding:8px;border-bottom:1px solid #FCA5A5;text-align:right">${num(f.hay)}</td>
            <td style="padding:8px;border-bottom:1px solid #FCA5A5;text-align:right;color:#B91C1C;font-weight:900">${num(Math.max((f.pide || 0) - (f.hay || 0), 0))}</td></tr>`).join('');
    const d = document.createElement('div');
    d.id = 'errorStockDespacho';
    d.setAttribute('role', 'alertdialog');
    d.style.cssText = 'position:fixed;inset:0;background:rgba(127,29,29,.55);z-index:10000003;display:flex;align-items:center;justify-content:center;padding:16px';
    d.innerHTML = `<div style="background:#FEF2F2;border:5px solid #DC2626;border-radius:16px;max-width:720px;width:100%;max-height:90vh;overflow:auto;box-shadow:0 24px 70px rgba(0,0,0,.45)">
        <div style="background:#DC2626;color:#fff;padding:16px 20px;font-size:24px;font-weight:950;letter-spacing:.3px">⛔ ${esc(titulo || 'NO SE PUEDE DESPACHAR: FALTA STOCK')}</div>
        <div style="padding:16px 20px;color:#7F1D1D">
          <div style="font-size:16px;font-weight:800;margin-bottom:10px">${filas ? 'Estos productos no alcanzan en la empresa y sede elegidas:' : esc(mensaje || 'No hay stock suficiente.')}</div>
          ${filas ? `<table style="width:100%;border-collapse:collapse;font-size:15px;background:#fff;border:2px solid #FCA5A5;border-radius:10px">
            <thead><tr style="background:#FEE2E2"><th style="padding:8px;text-align:left">Nombre producto</th><th style="padding:8px">Empresa · Sede</th>
              <th style="padding:8px;text-align:right">Pide</th><th style="padding:8px;text-align:right">Hay</th><th style="padding:8px;text-align:right">Falta</th></tr></thead>
            <tbody>${filas}</tbody></table>` : ''}
          <div style="font-size:14px;font-weight:700;margin-top:12px">${titulo ? (filas ? esc(mensaje || '') : '') : 'Qué hacer: elige otra empresa o sede que diga ✅ "hay todo", o pide la compra / la transferencia de esos productos. Nada se descontó.'}</div>
          <div style="text-align:right;margin-top:14px"><button type="button" style="padding:12px 22px;border:0;border-radius:10px;background:#DC2626;color:#fff;font-size:16px;font-weight:900;cursor:pointer">Entendido</button></div>
        </div></div>`;
    document.body.appendChild(d);
    d.querySelector('button').onclick = () => d.remove();
    if (typeof showToast === 'function') showToast(titulo ? '⛔ ' + titulo.charAt(0) + titulo.slice(1).toLowerCase() : '⛔ No se puede despachar: falta stock', 'error');
}
window.mostrarErrorStockDespacho = mostrarErrorStockDespacho;

function anularDespacho(id) {
    const despacho = (despachosData || []).find(d => d.id === id) || {};
    showDeleteConfirmModal(
        '↩️ ¿Anular despacho?',
        `Vas a anular el despacho <b>${despacho.numero || ''}</b> de <b>${despacho.cliente || ''}</b>.`,
        '⚠️ La mercadería vuelve al stock de la misma empresa y sede, y vuelve a quedar separada para el cliente.',
        async function(motivo) {
            try {
                const r = await apiFetch(`/ventas/api/despachos/${id}`, {
                    method: 'DELETE',
                    body: JSON.stringify({ motivo: motivo })
                });
                showToast('✅ ' + (r.message || 'Despacho anulado'), 'success');
                if (typeof loadDespachos === 'function') loadDespachos();
            } catch (e) {
                showToast('❌ ' + e.message, 'error');
            }
        },
        '↩️ Sí, anular'
    );
}
window.anularDespacho = anularDespacho;
window.prepararUbicacionDespacho = prepararUbicacionDespacho;


// ============================================================
// CONDICIÓN DE PAGO DE LA FACTURA (pedido de Erika 19/10/2026)
// Sale del PC de origen; si no hay PC, de la guía; si no, del cliente. Nunca de la cotización.
// Antes un PC a 30 días terminaba en factura "Contado".
// ============================================================
async function aplicarCondicionFactura(alGuardar) {
    const sel = document.getElementById('compCondicion');
    if (!sel) return;
    if (typeof editingId !== 'undefined' && editingId && document.getElementById('compNumero')?.value && !alGuardar) return; // factura ya guardada: se respeta
    const v = id => (document.getElementById(id)?.value || '').trim();
    const qs = new URLSearchParams({ pc: v('compPC'), guia: v('compGuia'), cotizacion: v('compCotizacion'), ruc: v('compRuc') });
    let j = null;
    try {
        const r = await fetch('/ventas/api/comprobantes/condicion-origen?' + qs.toString());
        j = await r.json();
    } catch (e) { return; }
    j = j && j.data ? j.data : j;
    if (!j || !j.condicion) {
        if (!sel.value && v('compRuc')) {
            let aviso = document.getElementById('compCondicionOrigen');
            if (!aviso) { aviso = document.createElement('small'); aviso.id = 'compCondicionOrigen'; sel.insertAdjacentElement('afterend', aviso); }
            aviso.style.cssText = 'display:block;margin-top:3px;font-size:11px;font-weight:800;color:#B91C1C';
            aviso.textContent = '⚠ Elige la condición: no hay PC y el cliente no tiene una registrada';
        }
        return;
    }
    window.ponerCondicion(sel, j.condicion);
    const pcSel = document.getElementById('compPC');
    if (pcSel && !pcSel.value && j.pc) {
        if (![...pcSel.options].some(o => o.value === j.pc)) pcSel.add(new Option(j.pc, j.pc));
        pcSel.value = j.pc;
    }
    const oc = document.getElementById('compOrdenCompra');
    if (oc && !oc.value.trim() && j.oc_cliente) oc.value = j.oc_cliente;
    let nota = document.getElementById('compCondicionOrigen');
    if (!nota) {
        nota = document.createElement('small');
        nota.id = 'compCondicionOrigen';
        sel.insertAdjacentElement('afterend', nota);
    }
    nota.style.cssText = 'display:block;margin-top:3px;font-size:11px;font-weight:800;color:#065F46';
    const fuente = /^PC/i.test(j.fuente || '') ? 'del ' + j.fuente : (j.fuente === 'cliente' ? 'de la ficha del cliente (no hay PC)' : '');
    nota.textContent = fuente ? '✔ Tomada ' + fuente : '';
    if (typeof actualizarEstadoRetencion === 'function') actualizarEstadoRetencion();
    if (typeof calcularRetencionComprobante === 'function') calcularRetencionComprobante();
}
window.aplicarCondicionFactura = aplicarCondicionFactura;
['loadComprobanteFromGuia', 'loadComprobanteFromPC', 'loadComprobanteFromCotizacion', 'cargarProductosComprobanteDesdeCotizacion'].forEach(nombre => {
    const original = window[nombre];
    if (typeof original !== 'function' || original._conCondicion) return;
    const envuelta = function () {
        const r = original.apply(this, arguments);
        Promise.resolve(r).finally(() => setTimeout(aplicarCondicionFactura, 150));
        return r;
    };
    envuelta._conCondicion = true;
    window[nombre] = envuelta;
});
// También se llena al escribir el RUC a mano o al elegir la cotización en la factura (20/10/2026: antes quedaba "Contado")
document.addEventListener('change', e => {
    const id = e.target && e.target.id;
    if (id === 'compRuc' || (id === 'compCotizacion' && !e.target.getAttribute('onchange'))) setTimeout(aplicarCondicionFactura, 150);
});
// Observaciones de la factura: primera letra en mayúscula
document.addEventListener('focusout', e => {
    const el = e.target;
    if (el && el.id === 'compObs' && el.value) {
        const t = el.value.replace(/^\s+/, '');
        el.value = t.charAt(0).toLocaleUpperCase('es-PE') + t.slice(1);
    }
});

// ============================================================
// AYUDA PASO A PASO (pedido de Erika 19/10/2026): después de crear la guía o la factura,
// una ventana grande dice qué hacer y un botón lleva a la lista con el documento resaltado.
// ============================================================
function irAPestanaYResaltar(tab, buscarId, texto, render) {
    const textos = (Array.isArray(texto) ? texto : [texto]).filter(Boolean).map(String);
    const btn = document.querySelector(`.tab-btn[data-tab="${tab}"]`);
    if (btn) btn.click();
    setTimeout(() => {
        const buscador = document.getElementById(buscarId);
        if (buscador && buscador.value) { buscador.value = ''; }
        if (typeof render === 'function') { try { render(); } catch (e) {} }
        setTimeout(() => {
            const filas = [...document.querySelectorAll('tbody tr')].filter(tr => tr.offsetParent !== null && textos.some(t => tr.textContent.includes(t)));
            const fila = filas[0];
            if (fila) {
                fila.classList.add('fila-recien');
                fila.scrollIntoView({ behavior: 'smooth', block: 'center' });
                setTimeout(() => fila.classList.remove('fila-recien'), 6000);
            }
        }, 250);
    }, 300);
}
window.irAPestanaYResaltar = irAPestanaYResaltar;
