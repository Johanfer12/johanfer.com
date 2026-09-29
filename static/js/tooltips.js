// Pasa los `title` nativos a `data-tip`, que es lo que dibuja el tooltip propio
// del sitio (base.css). Vigila también los que se ponen o cambian después desde
// JS (el ⋮ que pasa a «Cerrar opciones», «Guardar» ↔ «Guardada»...): si no, esos
// volverían a sacar el nativo.
(() => {
    // No se tocan: el `title` de un iframe es su nombre accesible, un campo no
    // puede llevar pseudo-elementos, y la X de las tarjetas en móvil ya dibuja
    // sus dos trazos con ::before y ::after.
    const SKIP = 'iframe, input, select, textarea, img, svg, .mobile-delete-btn';

    const convert = (el) => {
        if (!el.hasAttribute('title') || el.matches(SKIP)) return;
        const text = el.getAttribute('title').trim();
        el.removeAttribute('title');
        if (!text) return;
        el.dataset.tip = text;
        // Sin title ni aria-label, un lector de pantalla se quedaría sin nombre
        // en los elementos que no tienen texto propio (barras, iconos sueltos).
        if (!el.hasAttribute('aria-label') && !el.textContent.trim()) {
            el.setAttribute('aria-label', text);
        }
    };

    const scan = (root) => {
        if (root.nodeType !== 1) return;
        convert(root);
        root.querySelectorAll('[title]').forEach(convert);
    };

    scan(document.body);

    new MutationObserver((mutations) => {
        for (const m of mutations) {
            if (m.type === 'attributes') convert(m.target);
            else m.addedNodes.forEach(scan);
        }
    }).observe(document.body, {
        subtree: true,
        childList: true,
        attributes: true,
        attributeFilter: ['title'],
    });
})();
