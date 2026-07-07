// Mini modal de ordenamiento (compartido por Mis Libros y Mi TV).
// Al elegir una opción se recarga la página con ?orden=..., conservando
// el resto de parámetros (q, tipo).
document.addEventListener('DOMContentLoaded', function () {
    const sortBtn = document.getElementById('sortBtn');
    const sortModal = document.getElementById('sortModal');
    if (!sortBtn || !sortModal) {
        return;
    }

    const currentOrden = new URLSearchParams(window.location.search).get('orden') || 'fecha_desc';

    sortModal.querySelectorAll('.sort-option').forEach(function (option) {
        if (option.dataset.orden === currentOrden) {
            option.classList.add('active');
        }
        option.addEventListener('click', function () {
            const params = new URLSearchParams(window.location.search);
            params.set('orden', option.dataset.orden);
            params.delete('page');
            window.location.search = params.toString();
        });
    });

    sortBtn.addEventListener('click', function () {
        sortModal.style.display = 'flex';
    });

    const closeBtn = sortModal.querySelector('.sort-close');
    if (closeBtn) {
        closeBtn.addEventListener('click', function () {
            sortModal.style.display = 'none';
        });
    }

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            sortModal.style.display = 'none';
        }
    });
});
