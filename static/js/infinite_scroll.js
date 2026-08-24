// Mis Libros: solo el marcado de la tarjeta y del modal. La paginación, la
// búsqueda y el scroll los lleva infinite_scroll_core.js, compartido con Mi TV.
const bookContainer = document.getElementById('book-container');

const formatDate = (isoDate) => {
    if (!isoDate) return '';
    const [year, month, day] = isoDate.split('-');
    return `${day}/${month}/${year}`;
};

const createBookItem = (book) => {
    const item = document.createElement('div');
    item.className = 'book-item';
    const coverImage = (book.cover_image || '').replace('.jpg', '.webp');
    const readingRibbon = book.is_reading
        ? '<div class="watching-ribbon"><span>Leyendo</span></div>'
        : '';
    const ratingRow = book.is_reading
        ? ''
        : `<p><strong>Mi Calificación</strong><br>${book.my_rating_html || ''}</p>`;
    const dateRow = book.is_reading
        ? ''
        : `<p><strong>Lo leí el...</strong><br>${escapeHtml(formatDate(book.date_read))}</p>`;

    item.innerHTML = `
        <div class="book-info-container">
            <div class="book-cover" onclick="openModal('${book.id}')">
                <img src="${escapeHtml(coverImage)}" alt="${escapeHtml(book.title)}">
                ${readingRibbon}
            </div>
            <div class="book-info">
            <a href="${escapeHtml(book.book_link)}" class="book-title" target="_blank">${escapeHtml(book.title)}</a>
                <p><strong>Autor</strong><br>${escapeHtml(book.author)}</p>
                ${ratingRow}
                <p><strong>Calificación General</strong><br>${book.public_rating_html || ''}</p>
                ${dateRow}
            </div>
        </div>
    `;

    return item;
};

const createBookModal = (book) => {
    const modal = document.createElement('div');
    modal.id = `modal-${book.id}`;
    modal.className = 'modal';
    const coverImage = (book.cover_image || '').replace('.jpg', '.webp');
    modal.innerHTML = `
        <div class="modal-content book-modal-content">
            <span class="close" onclick="closeModal('${book.id}')">&times;</span>
            <div class="book-modal-body">
                <div class="book-modal-cover">
                    <img src="${escapeHtml(coverImage)}" alt="${escapeHtml(book.title)}" loading="lazy">
                    ${book.is_reading ? '<div class="watching-ribbon"><span>Leyendo</span></div>' : ''}
                </div>
                <div class="book-modal-info">
                    <h2>${escapeHtml(book.title)}</h2>
                    <div class="book-modal-metadata">
                        <div>
                            <p><strong>Autor:</strong> ${escapeHtml(book.author)}</p>
                            ${book.is_reading ? '' : `<p><strong>Mi Calificación:</strong> ${book.my_rating_html || ''}</p>`}
                            <p><strong>Calificación General:</strong> ${book.public_rating_html || ''}</p>
                        </div>
                        <div>
                            ${book.num_pages ? `<p><strong>Páginas:</strong> ${escapeHtml(String(book.num_pages))}</p>` : ''}
                            ${book.published_year ? `<p><strong>Publicado:</strong> ${escapeHtml(String(book.published_year))}</p>` : ''}
                            ${book.is_reading ? '' : `<p><strong>Leído el:</strong> ${escapeHtml(formatDate(book.date_read))}</p>`}
                        </div>
                    </div>
                    <div class="book-description">
                        <div class="book-description-scroll">
                            <strong>Descripción</strong><br><br>
                            ${book.description || 'No hay descripción disponible'}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
    return modal;
};

const renderBooks = (data, {replace}) => {
    if (replace) {
        bookContainer.innerHTML = '';
        document.querySelectorAll('div.modal[id^="modal-"]').forEach((modal) => modal.remove());
    }
    (data.books || []).forEach((book) => {
        bookContainer.appendChild(createBookItem(book));
        bookContainer.appendChild(createBookModal(book));
    });
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
