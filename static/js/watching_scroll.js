// Mi TV: la paginación, la búsqueda y el scroll los lleva
// infinite_scroll_core.js, compartido con Mis Libros.
//
// Las tarjetas llegan ya renderizadas por el servidor (templates/watch_item.html,
// el mismo include que pinta la página), con el listón de "Viendo" y el aviso
// de "sin calificar" incluidos. Antes este fichero rearmaba en JS el marcado de
// la tarjeta, la ficha y el aviso, y había que mantener las dos copias a la par.
const watchContainer = document.getElementById('watch-container');
let currentTipo = 'series';
let currentOrden = '';

const renderCards = (data, {replace}) => {
    if (replace) {
        watchContainer.innerHTML = '';
        document.querySelectorAll('div.modal[id^="modal-watch-"]').forEach((modal) => modal.remove());
    }
    watchContainer.insertAdjacentHTML('beforeend', data.html || '');
};

const setWatchedTotalLabel = (count) => {
    const totalLabel = document.querySelector('.header .total');
    if (!totalLabel || typeof count === 'undefined') {
        return;
    }
    const noun = watchContainer.dataset.watchNoun || '';
    totalLabel.textContent = `${count} ${noun}${count === 1 ? '' : 's'}`.trim();
};

document.addEventListener('DOMContentLoaded', function () {
    if (!watchContainer) return;

    const params = new URLSearchParams(window.location.search);
    currentTipo = params.get('tipo') === 'peliculas' ? 'peliculas' : 'series';
    currentOrden = params.get('orden') || '';

    const scroll = window.createInfiniteScroll({
        container: watchContainer,
        endpoint: '/viendo/',
        params: () => ({tipo: currentTipo, orden: currentOrden}),
        render: renderCards,
        onLoaded: (data) => {
            setWatchedTotalLabel(data.total_watched);
        },
    });
    window.watchingApplySearch = scroll.applySearch;
});
