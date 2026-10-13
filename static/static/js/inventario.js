/* ============================================================
   INVENTARIO.JS - Módulo de Inventario (Frontend completo + Filtros con Fecha/Hora)
   ============================================================ */

(function() {
    'use strict';

    // ============================================================
    // 1. VARIABLES GLOBALES DEL MÓDULO
    // ============================================================
    const MODULE_NAME = 'Inventario';

    // ============================================================
    // 2. INICIALIZACIÓN PRINCIPAL (CON FILTROS INCLUIDOS)
    // ============================================================
    function initInventario(tabId) {
        console.log(`📦 [${MODULE_NAME}] Inicializando módulo con tab: ${tabId}`);
        
        if (!tabId) {
            const urlParams = new URLSearchParams(window.location.search);
            tabId = urlParams.get('tab') || 'estado_stock';
        }

        // Cargar datos y activar filtros
        cargarDatosSeccion(tabId);
        configurarFiltros(tabId);
    }

    // ✅ EXPONER AL GLOBAL
    window.initInventario = initInventario;

    // ============================================================
    // 3. CAMBIAR DE TAB
    // ============================================================
    window.switchInventarioTab = function(tabId) {
        console.log(`🔄 Cambiando a tab de inventario: ${tabId}`);

        const url = new URL(window.location);
        url.searchParams.set('tab', tabId);
        window.history.pushState({}, '', url);

        document.querySelectorAll('#tabsRowInv .tab-btn').forEach(btn => {
            btn.classList.remove('active');
            if (btn.dataset.tab === tabId) btn.classList.add('active');
        });

        const sections = {
            'estado_stock': document.getElementById('estado_stock'),
            'kardex': document.getElementById('kardex'),
            'entradas_salidas': document.getElementById('entradas_salidas'),
            'transferencias': document.getElementById('transferencias')
        };
        Object.keys(sections).forEach(key => {
            if (sections[key]) sections[key].classList.remove('active');
        });
        if (sections[tabId]) sections[tabId].classList.add('active');

        if (typeof initInventario === 'function') initInventario(tabId);
    };

    // ============================================================
    // 4. CARGA DE DATOS
    // ============================================================
    function cargarDatosSeccion(tabId) {
        const tbodyId = getTbodyId(tabId);
        if (!tbodyId) return;

        document.getElementById(tbodyId).innerHTML = `
            <tr><td colspan="10" style="padding:20px;color:#94A3B8;font-weight:900;">⏳ Cargando datos...</td></tr>
        `;

        setTimeout(() => {
            let data = [];
            let countLabel = '';
            if (tabId === 'estado_stock') { data = getMockStockData(); countLabel = 'productos'; }
            else if (tabId === 'kardex') { data = getMockKardexData(); countLabel = 'movimientos'; }
            else if (tabId === 'entradas_salidas') { data = getMockMovimientosData(); countLabel = 'movimientos'; }
            else if (tabId === 'transferencias') { data = getMockTransferenciasData(); countLabel = 'transferencias'; }

            renderizarTabla(tabId, data);
            
            const countSpan = document.getElementById(`${tabId}Count`);
            if (countSpan) countSpan.textContent = `Mostrando ${data.length} de ${data.length} ${countLabel}`;
        }, 400);
    }

    // ============================================================
    // 5. FILTRADO (BÚSQUEDA + FECHAS/HORA + ESTADO)
    // ============================================================
    window.filtrarDatos = function(tabId) {
        const tbodyId = getTbodyId(tabId);
        if (!tbodyId) return;

        // 1. Búsqueda por texto
        const searchInput = document.getElementById(`${tabId}Search`);
        const textoBusqueda = searchInput ? searchInput.value.toLowerCase() : '';

        // 2. Fechas (solo día, se ignora la hora para el filtro)
        let fechaInicio = null, fechaFin = null;
        const fechaInicioInput = document.getElementById(`${tabId}FechaIicio`);
        const fechaFinInput = document.getElementById(`${tabId}FechaFin`);
        if (fechaInicioInput && fechaInicioInput.value) fechaInicio = new Date(fechaInicioInput.value);
        if (fechaFinInput && fechaFinInput.value) {
            fechaFin = new Date(fechaFinInput.value);
            fechaFin.setHours(23, 59, 59, 999);
        }

        // 3. Estado / Tipo
        const statusSelect = document.getElementById(`${tabId}Tipo`) || document.getElementById(`${tabId}Status`);
        const statusFiltro = statusSelect ? statusSelect.value.toLowerCase() : '';

        // 4. Obtener datos originales
        let datosOriginales = [];
        if (tabId === 'estado_stock') datosOriginales = getMockStockData();
        else if (tabId === 'kardex') datosOriginales = getMockKardexData();
        else if (tabId === 'entradas_salidas') datosOriginales = getMockMovimientosData();
        else if (tabId === 'transferencias') datosOriginales = getMockTransferenciasData();

        // 5. Aplicar filtros
        const datosFiltrados = datosOriginales.filter(item => {
            const coincideTexto = !textoBusqueda || JSON.stringify(item).toLowerCase().includes(textoBusqueda);
            
            let coincideFecha = true;
            if (item.fecha_hora) {
                const fechaItem = new Date(item.fecha_hora);
                // Solo comparar la fecha (día), ignorar la hora
                fechaItem.setHours(0, 0, 0, 0);
                if (fechaInicio && fechaItem < fechaInicio) coincideFecha = false;
                if (fechaFin && fechaItem > fechaFin) coincideFecha = false;
            }
            
            let coincideEstado = true;
            if (statusFiltro) {
                const estadoItem = (item.estado || item.tipo || '').toLowerCase();
                if (!estadoItem.includes(statusFiltro)) coincideEstado = false;
            }
            return coincideTexto && coincideFecha && coincideEstado;
        });

        renderizarTabla(tabId, datosFiltrados);
        const countSpan = document.getElementById(`${tabId}Count`);
        if (countSpan) countSpan.textContent = `Mostrando ${datosFiltrados.length} de ${datosOriginales.length} registros`;
    };

    // ============================================================
    // 6. CONFIGURAR FILTROS (Event Listeners)
    // ============================================================
    function configurarFiltros(tabId) {
        const searchInput = document.getElementById(`${tabId}Search`);
        if (searchInput) {
            let timeoutId;
            searchInput.addEventListener('input', function() {
                clearTimeout(timeoutId);
                timeoutId = setTimeout(() => window.filtrarDatos(tabId), 300);
            });
        }
        const fechaInicio = document.getElementById(`${tabId}FechaIicio`);
        const fechaFin = document.getElementById(`${tabId}FechaFin`);
        if (fechaInicio) fechaInicio.addEventListener('change', () => window.filtrarDatos(tabId));
        if (fechaFin) fechaFin.addEventListener('change', () => window.filtrarDatos(tabId));

        const statusSelect = document.getElementById(`${tabId}Tipo`) || document.getElementById(`${tabId}Status`);
        if (statusSelect) statusSelect.addEventListener('change', () => window.filtrarDatos(tabId));
    }

    // ============================================================
    // 7. LIMPIAR FILTROS
    // ============================================================
    window.clearDateFilter = function(tabId) {
        const fechaInicio = document.getElementById(`${tabId}FechaIicio`);
        const fechaFin = document.getElementById(`${tabId}FechaFin`);
        const searchInput = document.getElementById(`${tabId}Search`);
        const statusSelect = document.getElementById(`${tabId}Tipo`) || document.getElementById(`${tabId}Status`);

        if (fechaInicio) fechaInicio.value = '';
        if (fechaFin) fechaFin.value = '';
        if (searchInput) searchInput.value = '';
        if (statusSelect) statusSelect.value = '';

        window.filtrarDatos(tabId);
    };

    // ============================================================
    // 8. RENDERIZADO DE TABLAS (CON FECHA Y HORA)
    // ============================================================
    function renderizarTabla(tabId, data) {
        const tbodyId = getTbodyId(tabId);
        if (!tbodyId) return;
        const tbody = document.getElementById(tbodyId);
        let html = '';

        if (!data || data.length === 0) {
            html = `<tr><td colspan="10" style="padding:20px;color:#94A3B8;font-weight:900;">📭 No se encontraron registros.</td></tr>`;
        } else {
            data.forEach((item) => {
                html += `<tr>`;
                if (tabId === 'estado_stock') {
                    // Estado de stock no tiene fecha, solo mostramos el último movimiento
                    html += `
                        <td><b>${item.codigo || 'PROD-001'}</b></td>
                        <td>${item.producto || 'Producto genérico'}</td>
                        <td><b>${item.stock_actual || 0}</b></td>
                        <td>${item.stock_minimo || 5}</td>
                        <td>${item.ubicacion || 'Almacén Principal'}</td>
                        <td>${item.ultimo_movimiento || '2026-07-13 10:30'}</td>
                        <td>${getAccionesHTML(item.id, 'stock')}</td>
                    `;
                } else if (tabId === 'kardex') {
                    html += `
                        <td>${item.fecha_hora || '2026-07-13 10:30'}</td>
                        <td><b>${item.numero || 'KARDEX-001'}</b></td>
                        <td>${item.producto || 'Producto'}</td>
                        <td><span class="badge ${item.tipo === 'Entrada' ? 'b-approved' : 'b-canceled'}">${item.tipo || 'Movimiento'}</span></td>
                        <td><b>${item.cantidad || 0}</b></td>
                        <td>${item.responsable || 'Usuario'}</td>
                        <td>${getAccionesHTML(item.id, 'kardex')}</td>
                    `;
                } else if (tabId === 'entradas_salidas') {
                    html += `
                        <td>${item.fecha_hora || '2026-07-13 10:30'}</td>
                        <td><b>${item.documento || 'DOC-001'}</b></td>
                        <td><span class="badge ${item.tipo === 'Entrada' ? 'b-approved' : 'b-canceled'}">${item.tipo || 'Movimiento'}</span></td>
                        <td>${item.producto || 'Producto'}</td>
                        <td><b>${item.cantidad || 0}</b></td>
                        <td>${item.motivo || 'Sin motivo'}</td>
                        <td>${getAccionesHTML(item.id, 'movimiento')}</td>
                    `;
                } else if (tabId === 'transferencias') {
                    html += `
                        <td><b>${item.numero || 'TRF-001'}</b></td>
                        <td>${item.fecha_hora || '2026-07-13 10:30'}</td>
                        <td>${item.origen || 'Almacén A'}</td>
                        <td>${item.destino || 'Almacén B'}</td>
                        <td>${item.producto || 'Producto'}</td>
                        <td><b>${item.cantidad || 0}</b></td>
                        <td><span class="badge ${item.estado === 'Completada' ? 'b-approved' : item.estado === 'En tránsito' ? 'b-info' : 'b-pending'}">${item.estado || 'Pendiente'}</span></td>
                        <td>${getAccionesHTML(item.id, 'transferencia')}</td>
                    `;
                }
                html += `</tr>`;
            });
        }
        tbody.innerHTML = html;
    }

    // ============================================================
    // 9. ACCIONES Y KEBAB
    // ============================================================
    function getAccionesHTML(id, tipo) {
        return `<button class="kebab" onclick="toggleMenu(event, '${id}', '${tipo}')">⋮</button>`;
    }

    window.toggleMenu = function(event, id, tipo) {
        event.stopPropagation();
        const existingMenu = document.querySelector('.menu-pop');
        if (existingMenu) existingMenu.remove();

        const menu = document.createElement('div');
        menu.className = 'menu-pop';
        menu.style.top = (event.clientY + 10) + 'px';
        menu.style.left = (event.clientX - 20) + 'px';

        let opciones = '';
        if (tipo === 'stock') {
            opciones = `
                <button class="menu-edit" onclick="accionStock('ajustar', '${id}')">📝 Ajustar stock</button>
                <button class="menu-pdf" onclick="accionStock('detalle', '${id}')">📄 Ver detalle</button>
                <div class="menu-divider"></div>
                <button class="danger" onclick="accionStock('eliminar', '${id}')">🗑️ Eliminar</button>
            `;
        } else if (tipo === 'kardex' || tipo === 'movimiento') {
            opciones = `
                <button class="menu-edit" onclick="accionMovimiento('ver', '${id}')">👁️ Ver detalle</button>
                <button class="menu-pdf" onclick="accionMovimiento('pdf', '${id}')">📄 Generar comprobante</button>
                <div class="menu-divider"></div>
                <button class="danger" onclick="accionMovimiento('eliminar', '${id}')">🗑️ Eliminar</button>
            `;
        } else if (tipo === 'transferencia') {
            opciones = `
                <button class="menu-edit" onclick="accionTransferencia('editar', '${id}')">✏️ Editar</button>
                <button class="menu-approve" onclick="accionTransferencia('completar', '${id}')">✅ Marcar completada</button>
                <div class="menu-divider"></div>
                <button class="danger" onclick="accionTransferencia('eliminar', '${id}')">🗑️ Eliminar</button>
            `;
        }
        menu.innerHTML = opciones;
        document.body.appendChild(menu);

        setTimeout(() => {
            document.addEventListener('click', function closeMenu(e) {
                if (!menu.contains(e.target)) { menu.remove(); document.removeEventListener('click', closeMenu); }
            });
        }, 100);
    };

    function closeAllMenus() { document.querySelectorAll('.menu-pop').forEach(m => m.remove()); }

    window.accionStock = function(accion, id) {
        closeAllMenus();
        if (accion === 'ajustar') {
            document.getElementById('stockModal').classList.add('active');
            document.getElementById('stkProducto').value = 'Producto ID ' + id;
        } else if (accion === 'detalle') alert(`📊 Ver detalle de stock del ID: ${id}`);
        else if (accion === 'eliminar' && confirm('¿Estás seguro de eliminar este producto?')) alert(`🗑️ Producto ${id} eliminado (simulado)`);
    };

    window.accionMovimiento = function(accion, id) {
        closeAllMenus();
        if (accion === 'ver') {
            document.getElementById('kardexModal').classList.add('active');
            document.getElementById('kdxNumero').value = 'MOV-' + id;
        } else if (accion === 'pdf') alert(`📄 Generando PDF del movimiento ${id}`);
        else if (accion === 'eliminar' && confirm('¿Eliminar este movimiento del kardex?')) alert(`🗑️ Movimiento ${id} eliminado (simulado)`);
    };

    window.accionTransferencia = function(accion, id) {
        closeAllMenus();
        if (accion === 'editar') document.getElementById('transferenciaModal').classList.add('active');
        else if (accion === 'completar') {
            if (confirm('¿Marcar esta transferencia como completada?')) {
                alert(`✅ Transferencia ${id} completada (simulado)`);
                const activeTab = document.querySelector('.tab-btn.active');
                if (activeTab) window.filtrarDatos(activeTab.dataset.tab);
            }
        } else if (accion === 'eliminar' && confirm('¿Eliminar esta transferencia?')) alert(`🗑️ Transferencia ${id} eliminada (simulado)`);
    };

    // ============================================================
    // 10. MODALES
    // ============================================================
    window.openStockModal = function() {
        document.getElementById('stockModal').classList.add('active');
        document.getElementById('stkActual').value = '0';
        document.getElementById('stkNuevo').value = '0';
        document.getElementById('stkProducto').value = '';
    };

    window.openEntradaModal = function() {
        const modal = document.getElementById('entradaSalidaModal');
        if (modal) modal.classList.add('active');
        document.getElementById('movTipo').value = 'Entrada';
        document.getElementById('entradaSalidaModalTitle').textContent = '📥 Nueva entrada de mercadería';
    };

    window.openSalidaModal = function() {
        const modal = document.getElementById('entradaSalidaModal');
        if (modal) modal.classList.add('active');
        document.getElementById('movTipo').value = 'Salida';
        document.getElementById('entradaSalidaModalTitle').textContent = '📤 Nueva salida de mercadería';
    };

    window.openTransferenciaModal = function() {
        const modal = document.getElementById('transferenciaModal');
        if (modal) {
            modal.classList.add('active');
        } else {
            console.error('❌ Error crítico: No se encontró el elemento con ID "transferenciaModal"');
        }
    };

    window.closeModal = function(id) {
        const modal = document.getElementById(id);
        if (modal) modal.classList.remove('active');
    };

    window.exportData = function(tabId) { alert(`📥 Exportando datos de la sección: ${tabId} (Simulado)`); };

    // ============================================================
    // 11. UTILITARIAS
    // ============================================================
    function getTbodyId(tabId) {
        const map = { 'estado_stock': 'stockRows', 'kardex': 'kardexRows', 'entradas_salidas': 'movRows', 'transferencias': 'transRows' };
        return map[tabId] || null;
    }

    // ============================================================
    // 12. MOCK DATA (Con Fecha y Hora)
    // ============================================================
    function getMockStockData() {
        return [
            { id: 1, codigo: 'PROD-001', producto: 'Laptop Lenovo ThinkPad', stock_actual: 45, stock_minimo: 10, ubicacion: 'Estante A3', ultimo_movimiento: '2026-07-10 14:30' },
            { id: 2, codigo: 'PROD-002', producto: 'Monitor Samsung 24"', stock_actual: 12, stock_minimo: 5, ubicacion: 'Estante B1', ultimo_movimiento: '2026-07-11 09:15' },
            { id: 3, codigo: 'PROD-003', producto: 'Teclado Mecánico RGB', stock_actual: 0, stock_minimo: 20, ubicacion: 'Estante C2', ultimo_movimiento: '2026-07-05 16:45' },
        ];
    }
    function getMockKardexData() {
        return [
            { id: 101, fecha_hora: '2026-07-10 10:00', numero: 'MOV-001', producto: 'Laptop Lenovo', tipo: 'Entrada', cantidad: 10, responsable: 'Juan Pérez' },
            { id: 102, fecha_hora: '2026-07-11 15:30', numero: 'MOV-002', producto: 'Monitor Samsung', tipo: 'Salida', cantidad: 2, responsable: 'María García' },
            { id: 103, fecha_hora: '2026-07-12 08:45', numero: 'MOV-003', producto: 'Teclado Mecánico', tipo: 'Salida', cantidad: 5, responsable: 'Carlos López' },
        ];
    }
    function getMockMovimientosData() {
        return [
            { id: 201, fecha_hora: '2026-07-09 11:20', documento: 'OC-001', tipo: 'Entrada', producto: 'Laptop Lenovo', cantidad: 8, motivo: 'Compra' },
            { id: 202, fecha_hora: '2026-07-10 14:00', documento: 'FAC-002', tipo: 'Salida', producto: 'Monitor Samsung', cantidad: 1, motivo: 'Venta' },
            { id: 203, fecha_hora: '2026-07-11 09:10', documento: 'AJ-001', tipo: 'Salida', producto: 'Teclado Mecánico', cantidad: 3, motivo: 'Ajuste' },
        ];
    }
    function getMockTransferenciasData() {
        return [
            { id: 301, numero: 'TRF-001', fecha_hora: '2026-07-08 13:00', origen: 'Almacén Principal', destino: 'Tienda 1', producto: 'Laptop Lenovo', cantidad: 5, estado: 'Completada' },
            { id: 302, numero: 'TRF-002', fecha_hora: '2026-07-10 16:20', origen: 'Almacén Principal', destino: 'Almacén Secundario', producto: 'Monitor Samsung', cantidad: 3, estado: 'En tránsito' },
            { id: 303, numero: 'TRF-003', fecha_hora: '2026-07-12 10:00', origen: 'Tienda 1', destino: 'Tienda 2', producto: 'Teclado Mecánico', cantidad: 2, estado: 'Pendiente' },
        ];
    }

})();