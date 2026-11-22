// Mis Libros: la paginación, la búsqueda y el scroll los lleva
// infinite_scroll_core.js, compartido con Mi TV.
//
// Las tarjetas llegan ya renderizadas por el servidor (templates/book_item.html,
// el mismo include que pinta la página). Antes este fichero rearmaba en JS el
// marcado de la tarjeta y de la ficha a partir de un JSON, y cualquier cambio
// había que hacerlo dos veces; las dos copias ya se habían separado (el título
// de la portada, el formato de la fecha).
const bookContainer = document.getElementById('book-container');

const renderBooks = (data, {replace}) => {
    if (replace) {
        bookContainer.innerHTML = '';
        document.querySelectorAll('div.modal[id^="modal-"]').forEach((modal) => modal.remove());
    }
    bookContainer.insertAdjacentHTML('beforeend', data.html || '');
};

const setTotalBooksLabel = (count) => {
    const totalLabel = document.querySelector('.header .total');
    if (!totalLabel || typeof count === 'undefined') {
        return;
    }
    totalLabel.textContent = `${count} libro${count === 1 ? '' : 's'}`;
};

document.addEventListener('DOMContentLoaded', function () {
    const orden = new URLSearchParams(window.location.search).get('orden') || '';
    const scroll = window.createInfiniteScroll({
        container: bookContainer,
        endpoint: '/bookshelf',
        params: () => ({orden}),
        render: renderBooks,
        onLoaded: (data) => setTotalBooksLabel(data.total_books),
    });
    window.bookshelfApplySearch = scroll.applySearch;
});
