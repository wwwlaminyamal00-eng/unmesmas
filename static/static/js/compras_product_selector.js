// ============================================================
// COMPRAS - SELECTOR DE PRODUCTOS + CONSULTA RUC
// Archivo: static/js/compras_product_selector.js
// ============================================================

console.log('🚀 Cargando compras_product_selector.js...');

// ============================================================
// 1) SELECTOR GENÉRICO DE PRODUCTOS PARA COMPRAS
// ============================================================
(function() {
    'use strict';

    let _productSelComprasData = [];
    let _productSelComprasSelected = new Set();
    let _productSelComprasCallback = null;

    function _closeModalSafe(modalId) {
        if (typeof window.closeModal === 'function') {
            window.closeModal(modalId);
        } else {
            const modal = document.getElementById(modalId);
            if (modal) modal.classList.remove('show');
        }
    }

    function _showToastSafe(msg, type) {
        if (typeof window.showToast === 'function') {
            window.showToast(msg, type);
        } else {
            console.log(`[${type}] ${msg}`);
        }
    }

    function _getProductos() {
        if (typeof window.PRODUCTOS_MAESTROS !== 'undefined' && Array.isArray(window.PRODUCTOS_MAESTROS)) {
            return window.PRODUCTOS_MAESTROS;
        }
        if (typeof PRODUCTOS_MAESTROS !== 'undefined' && Array.isArray(PRODUCTOS_MAESTROS)) {
            return PRODUCTOS_MAESTROS;
        }
        return [];
    }

    async function _cargarProductosSiHaceFalta() {
        let productos = _getProductos();
        if (productos.length > 0) return productos;

        try {
            console.log('🔄 Cargando productos desde /productos/api/productos...');
            const resp = await fetch('/productos/api/productos');
            const data = await resp.json();
            if (data.success && data.data && data.data.length > 0) {
                window.PRODUCTOS_MAESTROS = data.data.map(p => ({
                    id: p.id,
                    codigo: p.codigo || '',
                    producto: p.descripcion || p.nombre || 'Sin nombre',
                    descripcion: p.descripcion_larga || p.descripcion || '',
                    marca: p.marca || '',
                    modelo: p.modelo || '',
                    um: p.unidad || 'UND',
                    stock: p.stock || 0,
                    valorVenta: p.precio_unitario || p.precio_venta || 0
                }));
                console.log(`✅ ${window.PRODUCTOS_MAESTROS.length} productos cargados`);
                return window.PRODUCTOS_MAESTROS;
            }
        } catch (e) {
            console.error('❌ Error cargando productos:', e);
        }
        return [];
    }

    window.openProductSelectorCompras = async function(onAddCallback) {
        console.log('📋 openProductSelectorCompras llamado');

        const productos = await _cargarProductosSiHaceFalta();

        if (!productos || productos.length === 0) {
            _showToastSafe('⚠️ No hay productos cargados. Ve al módulo Productos.', 'warning');
            return;
        }

        _productSelComprasData = [...productos];
        _productSelComprasSelected = new Set();
        _productSelComprasCallback = (typeof onAddCallback === 'function') ? onAddCallback : null;

        const searchInput = document.getElementById('productSelComprasSearch');
        if (searchInput) searchInput.value = '';

        window.renderProductSelectorCompras();

        const modal = document.getElementById('productSelectorComprasModal');
        if (!modal) {
            console.error('❌ #productSelectorComprasModal NO existe en el DOM');
            _showToastSafe('❌ Modal no encontrado. Revisa el include en index.html.', 'error');
            return;
        }
        modal.classList.add('show');
        console.log('✅ Modal de productos abierto');
    };

    window.renderProductSelectorCompras = function() {
        const tbody = document.getElementById('productSelectorComprasRows');
        if (!tbody) return;

        const search = (document.getElementById('productSelComprasSearch')?.value || '').toLowerCase().trim();

        let filtered = _productSelComprasData;
        if (search) {
            filtered = _productSelComprasData.filter(p => {
                return (p.codigo && p.codigo.toLowerCase().includes(search)) ||
                       (p.producto && p.producto.toLowerCase().includes(search)) ||
                       (p.descripcion && p.descripcion.toLowerCase().includes(search)) ||
                       (p.marca && p.marca.toLowerCase().includes(search)) ||
                       (p.modelo && p.modelo.toLowerCase().includes(search));
            });
        }

        if (filtered.length === 0) {
            tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;padding:20px;color:#94A3B8;">📭 No se encontraron productos</td></tr>`;
            const cnt = document.getElementById('selectedComprasCount');
            if (cnt) cnt.textContent = _productSelComprasSelected.size;
            return;
        }

        tbody.innerHTML = filtered.map(p => {
            const idKey = p.id || p.codigo;
            const checked = _productSelComprasSelected.has(idKey);
            const precio = parseFloat(p.valorVenta || p.precio_unitario || 0);

            return `
                <tr>
                    <td style="text-align:center;">
                        <input type="checkbox" class="sel-compras-checkbox" data-id="${idKey}" ${checked ? 'checked' : ''}
                               onchange="toggleProductSelectionCompras('${idKey}', this.checked)">
                    </td>
                    <td style="font-weight:900; color:#1D4ED8;">${p.codigo || '-'}</td>
                    <td style="text-align:left; font-weight:800;">${p.producto || p.descripcion || 'Sin nombre'}</td>
                    <td>${p.marca || '-'}</td>
                    <td>${p.modelo || '-'}</td>
                    <td>${p.um || 'UND'}</td>
                    <td>${p.stock || 0}</td>
                    <td style="font-weight:900; color:#059669; text-align:right;">S/ ${precio.toFixed(2)}</td>
                    <td>
                        <input type="number" class="sel-compras-qty" data-id="${idKey}" value="1" min="0.01" step="0.01"
                               style="width:60px; height:26px; border:1px solid #E5E7EB; border-radius:6px; text-align:center; font-size:11px;">
                    </td>
                </tr>
            `;
        }).join('');

        const cnt = document.getElementById('selectedComprasCount');
        if (cnt) cnt.textContent = _productSelComprasSelected.size;

        const total = document.querySelectorAll('.sel-compras-checkbox').length;
        const checkedCount = document.querySelectorAll('.sel-compras-checkbox:checked').length;
        const selectAll = document.getElementById('selectAllComprasCheckbox');
        if (selectAll) {
            selectAll.checked = total > 0 && checkedCount === total;
            selectAll.indeterminate = checkedCount > 0 && checkedCount < total;
        }
    };

    window.toggleProductSelectionCompras = function(idKey, checked) {
        if (checked) _productSelComprasSelected.add(idKey);
        else _productSelComprasSelected.delete(idKey);
        const cnt = document.getElementById('selectedComprasCount');
        if (cnt) cnt.textContent = _productSelComprasSelected.size;
    };

    window.selectAllProductsCompras = function() {
        document.querySelectorAll('.sel-compras-checkbox').forEach(cb => {
            cb.checked = true;
            _productSelComprasSelected.add(cb.dataset.id);
        });
        const cnt = document.getElementById('selectedComprasCount');
        if (cnt) cnt.textContent = _productSelComprasSelected.size;
    };

    window.deselectAllProductsCompras = function() {
        document.querySelectorAll('.sel-compras-checkbox').forEach(cb => {
            cb.checked = false;
            _productSelComprasSelected.delete(cb.dataset.id);
        });
        const cnt = document.getElementById('selectedComprasCount');
        if (cnt) cnt.textContent = _productSelComprasSelected.size;
    };

    window.toggleAllProductCheckboxesCompras = function(checked) {
        document.querySelectorAll('.sel-compras-checkbox').forEach(cb => {
            cb.checked = checked;
            if (checked) _productSelComprasSelected.add(cb.dataset.id);
            else _productSelComprasSelected.delete(cb.dataset.id);
        });
        const cnt = document.getElementById('selectedComprasCount');
        if (cnt) cnt.textContent = _productSelComprasSelected.size;
    };

    window.filterProductSelectorCompras = function() {
        window.renderProductSelectorCompras();
    };

    window.addSelectedProductsCompras = function() {
        if (_productSelComprasSelected.size === 0) {
            _showToastSafe('⚠️ Selecciona al menos un producto', 'warning');
            return;
        }

        const seleccionados = [];
        _productSelComprasSelected.forEach(idKey => {
            const prod = _productSelComprasData.find(p => (p.id == idKey) || (p.codigo == idKey));
            if (!prod) return;
            const qtyInput = document.querySelector(`.sel-compras-qty[data-id="${idKey}"]`);
            const cantidad = parseFloat(qtyInput?.value || 1);

            seleccionados.push({
                codigo: prod.codigo || '',
                producto: prod.producto || prod.descripcion || '',
                descripcion: prod.descripcion || prod.producto || '',
                marca: prod.marca || '',
                modelo: prod.modelo || '',
                um: prod.um || 'UND',
                cantidad: cantidad,
                precio_unitario: parseFloat(prod.valorVenta || prod.precio_unitario || 0),
                stock: parseInt(prod.stock || 0)
            });
        });

        _closeModalSafe('productSelectorComprasModal');

        if (typeof _productSelComprasCallback === 'function') {
            _productSelComprasCallback(seleccionados);
        }

        _showToastSafe(`✅ ${seleccionados.length} producto(s) agregado(s)`, 'success');
    };

    console.log('✅ Selector genérico de productos de Compras cargado');
})();


// ============================================================
// 2) CONSULTA DE RUC CON MODALES VISUALES
// ============================================================

// Estado global expuesto en window
window._rucResultadoActual = null;
window._rucCallbackUsarDatos = null;

/**
 * Muestra el modal de carga
 */
window.mostrarLoadingRuc = function(ruc) {
    const modal = document.getElementById('loadingRucModal');
    const numero = document.getElementById('loadingRucNumero');
    if (numero) numero.textContent = ruc;
    if (modal) {
        modal.classList.add('show');
        modal.style.display = 'flex';
    }
};

/**
 * Oculta el modal de carga
 */
window.ocultarLoadingRuc = function() {
    const modal = document.getElementById('loadingRucModal');
    if (modal) {
        modal.classList.remove('show');
        modal.style.display = 'none';
    }
};

/**
 * Cierra el modal de resultado del RUC
 */
window.cerrarModalRUC = function(event) {
    if (event) {
        try { event.preventDefault(); } catch (e) {}
        try { event.stopPropagation(); } catch (e) {}
    }
    console.log('🔒 cerrando modal RUC');

    const modal = document.getElementById('rucResultModal');
    if (modal) {
        modal.classList.remove('show');
        modal.style.display = 'none';
    }
};

/**
 * Muestra el modal con los datos recibidos
 */
window.mostrarResultadoRUC = function(datos, origen, callbackUsarDatos) {
    if (!datos) return;

    window._rucResultadoActual = datos;
    window._rucCallbackUsarDatos = (typeof callbackUsarDatos === 'function') ? callbackUsarDatos : null;

    const setText = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val || '-';
    };

    setText('rucResultRazon', datos.razon_social || datos.razon_comercial || 'Sin razón social');
    setText('rucResultRuc', datos.ruc || '-');
    setText('rucResultEstado', (datos.estado || 'ACTIVO').toUpperCase());
    setText('rucResultDireccion', datos.direccion || 'Sin dirección registrada');
    setText('rucResultCondicion', datos.condicion || 'HABIDO');

    const partesUbicacion = [];
    if (datos.distrito)     partesUbicacion.push(datos.distrito);
    if (datos.provincia)    partesUbicacion.push(datos.provincia);
    if (datos.departamento) partesUbicacion.push(datos.departamento);
    setText('rucResultUbicacion', partesUbicacion.length > 0
        ? partesUbicacion.join(' / ')
        : 'Sin ubicación registrada');

    const origenEl = document.getElementById('rucResultOrigen');
    if (origenEl) {
        origenEl.textContent = origen === 'bd'
            ? '📁 Fuente: Base de datos local'
            : '🌞 Fuente: SUNAT (consulta en vivo)';
    }

    const estadoEl = document.getElementById('rucResultEstado');
    const estadoUpper = (datos.estado || '').toUpperCase();
    if (estadoEl) {
        if (estadoUpper.includes('BAJA') || estadoUpper.includes('SUSPEND')) {
            estadoEl.style.color = '#DC2626';
        } else if (estadoUpper.includes('ACTIVO')) {
            estadoEl.style.color = '#16A34A';
        } else {
            estadoEl.style.color = '#0F172A';
        }
    }

    const modal = document.getElementById('rucResultModal');
    if (modal) {
        modal.classList.add('show');
        modal.style.display = 'flex';
    }
};

/**
 * Aplica los datos al formulario cuando el usuario pulsa "Usar estos datos"
 */
window.usarDatosRUC = function(event) {
    if (event) {
        try { event.preventDefault(); } catch (e) {}
        try { event.stopPropagation(); } catch (e) {}
    }

    console.log('✅ usarDatosRUC');
    console.log('   resultado:', window._rucResultadoActual);
    console.log('   callback:', typeof window._rucCallbackUsarDatos);

    if (typeof window._rucCallbackUsarDatos === 'function' && window._rucResultadoActual) {
        try {
            window._rucCallbackUsarDatos(window._rucResultadoActual);
        } catch (e) {
            console.error('❌ Error en callback:', e);
            if (typeof window.showToast === 'function') {
                window.showToast('❌ Error aplicando datos: ' + e.message, 'error');
            }
        }
    } else {
        console.warn('⚠️ No hay callback o datos guardados');
    }

    window.cerrarModalRUC();
};

/**
 * FUNCIÓN PRINCIPAL: consulta un RUC con modales visuales
 */
window.consultarRUCConspinner = async function(ruc, onUsarDatos) {
    if (!ruc || ruc.length !== 11 || !/^\d+$/.test(ruc)) {
        if (typeof window.showToast === 'function') {
            window.showToast('⚠️ El RUC debe tener 11 dígitos numéricos', 'warning');
        }
        return null;
    }

    window.mostrarLoadingRuc(ruc);

    try {
        const resp = await fetch(`/compras/api/proveedores/buscar?q=${ruc}`);
        const data = await resp.json();

        window.ocultarLoadingRuc();

        if (data.success && data.data && data.data.length > 0) {
            const proveedor = data.data[0];
            const origen = proveedor.origen || data.source || 'sunat';

            await new Promise(r => setTimeout(r, 300));

            window.mostrarResultadoRUC(proveedor, origen, onUsarDatos);
            return proveedor;
        } else {
            if (typeof window.showToast === 'function') {
                window.showToast(`❌ ${data.error || 'RUC no encontrado en SUNAT'}`, 'error');
            }
            return null;
        }
    } catch (error) {
        window.ocultarLoadingRuc();
        console.error('❌ Error consultando RUC:', error);
        if (typeof window.showToast === 'function') {
            window.showToast('❌ Error de conexión. Intenta de nuevo.', 'error');
        }
        return null;
    }
};

console.log('✅ Sistema de consulta RUC con modales cargado');