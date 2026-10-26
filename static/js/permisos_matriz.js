// ============================================================
// MATRIZ DE PERMISOS (pedido de Erika 22/10/2026)
// Filas = módulos (salen de erp_modulos / erp_submodulos: un módulo nuevo aparece solo).
// Columnas = Sin acceso / Solo lectura / Acceso total. El check principal del módulo
// pone el mismo nivel a todas sus funciones; con ▸ se ajusta cada función.
//   Sin acceso   -> no ve el módulo (el servidor bloquea la URL)
//   Solo lectura -> ve y exporta, pero el servidor no le deja grabar
//   Acceso total -> ve, crea, edita, aprueba, anula y exporta
// Aprobar OC, anular y ajustar stock siguen además con sus candados de rol (supervisora / administrador).
// ============================================================
(function () {
    'use strict';

    const NIVELES = [['sin', 'Sin acceso'], ['lectura', 'Solo lectura'], ['total', 'Acceso total']];
    const BANDERAS = {
        sin: { puede_ver: false, puede_crear: false, puede_editar: false, puede_aprobar: false, puede_anular: false,
               puede_eliminar: false, puede_exportar: false, puede_subir_evidencia: false },
        lectura: { puede_ver: true, puede_crear: false, puede_editar: false, puede_aprobar: false, puede_anular: false,
                   puede_eliminar: false, puede_exportar: true, puede_subir_evidencia: false },
        total: { puede_ver: true, puede_crear: true, puede_editar: true, puede_aprobar: true, puede_anular: true,
                 puede_eliminar: true, puede_exportar: true, puede_subir_evidencia: true }
    };
    // Módulos que no se asignan por usuario (se explica por qué)
    const FIJOS = {
        DASHBOARD: 'Todos los usuarios lo ven: es la página de inicio.',
        CONFIG_SEGURIDAD: 'Solo administrador (rol Gerencia total). Aquí se cambian usuarios, permisos y correlativos.',
        HERRAMIENTAS: 'Solo administrador (rol Gerencia total). Importa datos y recalcula stock.',
        PAPELERA: 'Cada uno ve lo que borró. Restaurar, borrar definitivo e historial de cambios: solo administrador.'
    };
    // Nombres claros de cada función (si la base trae un nombre genérico)
    const NOMBRES = {
        EMPRESAS: 'Empresas', USUARIOS_PERMISOS: 'Usuarios y permisos', CORRELATIVOS: 'Correlativos',
        PARAMETROS: 'Parámetros', INTEGRACION: 'Integración ERP',
        CLIENTES: 'Clientes', PROVEEDORES: 'Proveedores', ALMACENES: 'Almacenes / sedes', CATEGORIAS: 'Categorías',
        MARCAS: 'Marcas', UNIDADES_MEDIDA: 'Unidades de medida',
        PRODUCTOS_LISTADO: 'Lista de productos', PRODUCTOS_FICHA: 'Ficha de producto',
        COTIZACIONES: 'Cotizaciones', COMPROBANTES_CLIENTE: 'Pedidos (PV), despachos y facturas', GUIAS_CLIENTE: 'Guías de remisión',
        NOTAS_CREDITO: 'Notas de crédito', SEGUIMIENTO_COMERCIAL: 'Seguimiento comercial',
        SOLICITUD_COMPRA: 'Pedidos por comprar', COMPARATIVO_PROVEEDORES: 'Comparativo y precios de proveedores',
        ORDEN_COMPRA: 'Órdenes de compra (Proveedor)', COMPROBANTES_PROVEEDOR: 'Facturas de proveedores',
        RECEPCION_MERCADERIA: 'Recibir mercadería (logística)',
        ESTADO_STOCK: 'Stock', KARDEX: 'Kardex', ENTRADAS_SALIDAS: 'Entradas y salidas', TRANSFERENCIAS: 'Traslados entre sedes',
        CUENTAS_COBRAR: 'Cuentas por cobrar', CUENTAS_PAGAR: 'Cuentas por pagar', CAJA_BANCOS: 'Cobros y pagos',
        FLUJO_CAJA: 'Flujo de caja', CONCILIACION_BANCARIA: 'Conciliación bancaria', INTERCOMPANY: 'Intercompany KCF ↔ AGD',
        PLANILLA: 'Planilla y RRHH (sueldos)', CAJA_CHICA: 'Caja chica',
        REPORTE_VENTAS: 'Reporte de ventas', REPORTE_COMPRAS: 'Reporte de compras', REPORTE_INVENTARIO: 'Reporte de inventario',
        REPORTE_FINANZAS: 'Reporte de finanzas', SUNAT: 'SUNAT e impuestos'
    };

    let MODULOS = null;          // [{codigo, nombre, submodulos:[{codigo, nombre}]}]
    let actual = null;           // {userId, user, empresaId, empresaCodigo, gerencia, efectivos}

    const esc = v => String(v == null ? '' : v).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const nombreFuncion = s => NOMBRES[s.codigo] || s.nombre || s.codigo;

    function nivel(p) {
        if (!p || !p.puede_ver) return 'sin';
        return (p.puede_crear || p.puede_editar) ? 'total' : 'lectura';
    }

    async function cargarModulos() {
        if (MODULOS) return MODULOS;
        const r = await fetch('/api/config/modulos', { credentials: 'same-origin' });
        const j = await r.json().catch(() => ({}));
        if (!r.ok || !j.success) throw new Error(j.error || 'No se pudieron leer los módulos.');
        MODULOS = (j.data || []).map(m => ({ codigo: m.codigo, nombre: m.nombre, submodulos: m.submodulos || [] }));
        return MODULOS;
    }
    const editable = m => !FIJOS[m.codigo] && m.submodulos.length > 0;

    // Nivel de un módulo: el mismo de todas sus funciones, o 'mixto'
    function nivelModulo(m, efectivos) {
        const niveles = new Set(m.submodulos.map(s => nivel(efectivos[s.codigo])));
        return niveles.size === 1 ? [...niveles][0] : 'mixto';
    }

    // ---------- Resumen en la tabla de usuarios ----------
    window.resumenPermisosHtml = function (estado) {
        if (!estado) return '<span class="pm-gris">Cargando…</span>';
        if (estado.error || !estado.empresaId) return `<span class="pm-gris">${esc(estado.error || estado.motivo || 'Sin acceso a esta empresa')}</span>`;
        if (estado.gerencia) return '<span class="pm-chip pm-total">👑 Todo (Gerencia total)</span>';
        if (!MODULOS) { cargarModulos().then(() => { if (typeof _dibujarTablaUsuarios === 'function') _dibujarTablaUsuarios(); }).catch(() => {}); return '…'; }
        const chips = MODULOS.filter(editable).map(m => {
            const n = nivelModulo(m, estado.efectivos || {});
            if (n === 'sin') return '';
            const cls = n === 'total' ? 'pm-total' : n === 'lectura' ? 'pm-lectura' : 'pm-mixto';
            const t = n === 'total' ? 'Acceso total' : n === 'lectura' ? 'Solo lectura' : 'Parte del módulo';
            return `<span class="pm-chip ${cls}" title="${t}">${esc(m.nombre)}</span>`;
        }).filter(Boolean);
        return chips.length ? chips.join(' ') : '<span class="pm-rojo">Sin módulos</span>';
    };

    // ---------- Modal de la matriz ----------
    function radios(nombre, elegido, deshabilitado) {
        return NIVELES.map(([v, t]) => `<td class="pm-celda pm-col-${v}"><label title="${t}"><input type="radio" name="${esc(nombre)}" value="${v}"
            ${elegido === v ? 'checked' : ''} ${deshabilitado ? 'disabled' : ''}></label></td>`).join('');
    }

    function pintar() {
        const ef = actual.efectivos || {};
        const filas = [];
        MODULOS.forEach((m, i) => {
            if (!editable(m)) {
                const texto = FIJOS[m.codigo] || 'Este módulo todavía no tiene funciones creadas.';
                filas.push(`<tr class="pm-mod pm-fijo"><td class="left"><b>${esc(m.nombre)}</b></td><td colspan="3" class="left pm-gris">🔒 ${esc(texto)}</td></tr>`);
                return;
            }
            const n = actual.gerencia ? 'total' : nivelModulo(m, ef);
            const marca = n === 'mixto' ? '<span class="pm-chip pm-mixto">Personalizado</span>' : '';
            filas.push(`<tr class="pm-mod" data-mod="${i}">
                <td class="left"><button type="button" class="pm-abrir" data-abrir="${i}" title="Ver sus funciones">▸</button>
                    <b>${esc(m.nombre)}</b> <small class="pm-gris">${m.submodulos.length} función(es)</small> ${marca}</td>
                ${radios('mod_' + i, n, actual.gerencia)}</tr>`);
            m.submodulos.forEach(s => {
                const ns = actual.gerencia ? 'total' : nivel(ef[s.codigo]);
                const delRol = ef[s.codigo] && ef[s.codigo].origen === 'rol' ? ' <small class="pm-gris" title="No tiene permiso propio: viene de su rol">(del rol)</small>' : '';
                filas.push(`<tr class="pm-sub" data-padre="${i}" hidden>
                    <td class="left pm-sangria">${esc(nombreFuncion(s))}${delRol}</td>
                    ${radios('sub_' + s.codigo, ns, actual.gerencia)}</tr>`);
            });
        });
        document.getElementById('pmFilas').innerHTML = filas.join('');
        document.getElementById('pmGerencia').hidden = !actual.gerencia;
        document.getElementById('pmGuardar').hidden = !!actual.gerencia;
    }

    function sincronizarModulo(i) {
        const m = MODULOS[i];
        const niveles = new Set(m.submodulos.map(s => (document.querySelector(`input[name="sub_${CSS.escape(s.codigo)}"]:checked`) || {}).value));
        const fila = document.querySelector(`tr.pm-mod[data-mod="${i}"]`);
        document.querySelectorAll(`input[name="mod_${i}"]`).forEach(r => { r.checked = niveles.size === 1 && r.value === [...niveles][0]; });
        let chip = fila.querySelector('.pm-mixto');
        if (niveles.size > 1 && !chip) fila.querySelector('td').insertAdjacentHTML('beforeend', ' <span class="pm-chip pm-mixto">Personalizado</span>');
        if (niveles.size === 1 && chip) chip.remove();
    }

    window.abrirMatrizPermisos = async function (userId) {
        const estado = (typeof PERM_ESTADO !== 'undefined' ? PERM_ESTADO : {})[userId];
        const u = (typeof usuariosData !== 'undefined' ? usuariosData : []).find(x => String(x.id) === String(userId)) || {};
        if (!estado || !estado.empresaId) { toast('❌ Este usuario no tiene acceso a la empresa elegida.'); return; }
        try {
            await cargarModulos();
            const datos = await cargarPermisosUsuario(userId, estado.empresaId);   // lo último de la base
            actual = { userId, user: u.nombres_apellidos || u.usuario_sistema || '', empresaId: estado.empresaId,
                       empresaCodigo: estado.codigo, gerencia: !!datos.es_gerencia_total, efectivos: datos.efectivos || {} };
        } catch (e) { mostrarNotificacion('error', 'No se pudo abrir', e.message); return; }
        document.getElementById('pmTitulo').textContent = `Permisos de ${actual.user} en ${actual.empresaCodigo}`;
        pintar();
        document.getElementById('pmModal').classList.add('show');
    };

    async function guardar() {
        const lista = [];
        MODULOS.filter(editable).forEach(m => m.submodulos.forEach(s => {
            const r = document.querySelector(`input[name="sub_${CSS.escape(s.codigo)}"]:checked`);
            if (r) lista.push(Object.assign({ submodulo_codigo: s.codigo }, BANDERAS[r.value]));
        }));
        const btn = document.getElementById('pmGuardar');
        btn.disabled = true;
        const r = await guardarPermisosUsuario(actual.userId, actual.empresaId, lista);
        btn.disabled = false;
        if (!r.ok) { mostrarNotificacion('error', 'No se guardó', r.error); return; }
        const estado = (typeof PERM_ESTADO !== 'undefined' ? PERM_ESTADO : {})[actual.userId];
        if (estado) { estado.efectivos = r.data?.efectivos || estado.efectivos; estado.gerencia = !!r.data?.es_gerencia_total; }
        document.getElementById('pmModal').classList.remove('show');
        if (typeof _dibujarTablaUsuarios === 'function') _dibujarTablaUsuarios();
        toast(`✅ Permisos de ${actual.user} guardados (${actual.empresaCodigo})`);
    }

    document.addEventListener('change', e => {
        const r = e.target;
        if (r.type !== 'radio' || !r.closest('#pmModal')) return;
        if (r.name.startsWith('mod_')) {
            const i = Number(r.name.slice(4));
            MODULOS[i].submodulos.forEach(s => {
                const x = document.querySelector(`input[name="sub_${CSS.escape(s.codigo)}"][value="${r.value}"]`);
                if (x) x.checked = true;
            });
            sincronizarModulo(i);
        } else if (r.name.startsWith('sub_')) {
            sincronizarModulo(Number(r.closest('tr').dataset.padre));
        }
    });
    document.addEventListener('click', e => {
        const b = e.target.closest('[data-abrir]');
        if (b && b.closest('#pmModal')) {
            const abierto = b.textContent === '▾';
            b.textContent = abierto ? '▸' : '▾';
            document.querySelectorAll(`tr.pm-sub[data-padre="${b.dataset.abrir}"]`).forEach(f => { f.hidden = abierto; });
        }
        const p = e.target.closest('[data-matriz]');
        if (p) abrirMatrizPermisos(p.dataset.matriz);
        if (e.target.id === 'pmCerrar' || e.target.id === 'pmCancelar') document.getElementById('pmModal').classList.remove('show');
        if (e.target.id === 'pmGuardar') guardar();
    });
})();
