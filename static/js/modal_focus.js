// Foco de teclado atrapado en el modal abierto.
//
// El sitio tiene siete modales distintos (fichas de Libros y TV, buscar,
// ordenar, Retos, comentarios, palabra filtro y los de Visitas), cada uno con
// su forma de abrir, cerrar y bloquear el scroll. Todos se declaran
// `aria-modal="true"`, que promete a un lector de pantalla que lo de detrás no
// existe, pero ninguno retenía el foco: con Tab se salía del modal y se seguía
// recorriendo la página oculta. En vez de reescribir los siete, esto lo
// resuelve para todos a la vez: al pulsar Tab con un modal visible, el foco da
// la vuelta dentro de él.
//
// Un modal cuenta como abierto si está en pantalla (no `hidden`, con caja y
// visible). Si hay varios, manda el último del documento, que es el que se
// pinta encima. Los <dialog> abiertos con showModal() ya los gestiona el
// navegador y no se tocan.
(function () {
    const FOCUSABLE = [
        'a[href]', 'area[href]', 'button:not([disabled])', 'iframe',
        'input:not([disabled]):not([type="hidden"])', 'select:not([disabled])',
        'textarea:not([disabled])', '[tabindex]:not([tabindex="-1"])',
        '[contenteditable="true"]',
    ].join(',');

    const isShown = (el) => !el.hidden
        && el.getAttribute('aria-hidden') !== 'true'
        && el.getClientRects().length > 0
        && getComputedStyle(el).visibility !== 'hidden';

    const openModal = () => {
        const open = Array.from(document.querySelectorAll('[aria-modal="true"]'))
            .filter((el) => el.tagName !== 'DIALOG' && isShown(el));
        return open[open.length - 1] || null;
    };

    document.addEventListener('keydown', (event) => {
        if (event.key !== 'Tab' || event.defaultPrevented) return;
        const modal = openModal();
        if (!modal) return;

        const items = Array.from(modal.querySelectorAll(FOCUSABLE)).filter(isShown);
        if (!items.length) {
            event.preventDefault();
            if (modal.tabIndex < 0 && !modal.hasAttribute('tabindex')) modal.tabIndex = -1;
            modal.focus();
            return;
        }

        const first = items[0];
        const last = items[items.length - 1];
        const active = document.activeElement;
        if (!modal.contains(active)) {
            event.preventDefault();
            (event.shiftKey ? last : first).focus();
        } else if (event.shiftKey && (active === first || active === modal)) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && active === last) {
            event.preventDefault();
            first.focus();
        }
    });
})();
