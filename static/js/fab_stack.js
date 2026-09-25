// Grupo de botones flotantes de Libros y TV: un botón despliega el resto.
document.addEventListener('DOMContentLoaded', function () {
    const stack = document.getElementById('fabStack');
    const toggle = document.getElementById('fabToggle');
    if (!stack || !toggle) {
        return;
    }

    const setOpen = (open) => {
        stack.classList.toggle('is-open', open);
        toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        toggle.title = open ? 'Cerrar opciones' : 'Más opciones';
        toggle.setAttribute('aria-label', toggle.title);
    };

    toggle.addEventListener('click', function () {
        setOpen(!stack.classList.contains('is-open'));
    });

    // Al elegir una opción se pliega: la opción abre un modal o navega.
    document.getElementById('fabMenu')?.addEventListener('click', function (event) {
        if (event.target.closest('a, button')) {
            setOpen(false);
        }
    });

    document.addEventListener('click', function (event) {
        if (!stack.contains(event.target)) {
            setOpen(false);
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && stack.classList.contains('is-open')) {
            setOpen(false);
            toggle.focus();
        }
    });
});
