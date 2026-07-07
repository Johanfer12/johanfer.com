let page = 1;
let loading = false;
let hasNext = true;
let currentQuery = '';

const bookContainer = document.getElementById('book-container');
const loadingDiv = document.getElementById('loading');

const escapeHtml = (value) => {
    const div = document.createElement('div');
    div.textContent = value || '';
    return div.innerHTML;
};

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
        : `<p><strong>Mi Calificación</strong><br>${'★'.repeat(book.my_rating)}</p>`;
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
                <p><strong>Calificación General</strong><br>${escapeHtml(book.public_rating)}</p>
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
                            ${book.is_reading ? '' : `<p><strong>Mi Calificación</strong> <span class="stars">${'★'.repeat(book.my_rating)}</span></p>`}
                            <p><strong>Calificación General:</strong> ${escapeHtml(book.public_rating)}</p>
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

const renderBooks = (books, replace = false) => {
    if (replace) {
        bookContainer.innerHTML = '';
        document.querySelectorAll('div.modal[id^="modal-"]').forEach((modal) => modal.remove());
    }

    books.forEach((book) => {
        bookContainer.appendChild(createBookItem(book));
        bookContainer.appendChild(createBookModal(book));
    });
};

const setTotalBooksLabel = (count) => {
    const totalLabel = document.querySelector('.header .total');
    if (!totalLabel || typeof count === 'undefined') {
        return;
    }
    totalLabel.textContent = `${count} libros`;
};

function loadMoreBooks() {
    if (loading || !hasNext) return;

    loading = true;
    loadingDiv.style.display = 'block';

    const params = new URLSearchParams();
    params.set('page', String(page + 1));
    if (currentQuery) {
        params.set('q', currentQuery);
    }

    fetch(`/bookshelf?${params.toString()}`, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
        .then((response) => response.json())
        .then((data) => {
            renderBooks(data.books || []);
            page += 1;
            hasNext = Boolean(data.has_next);
            loading = false;
            loadingDiv.style.display = 'none';
            if (!hasNext) {
                window.removeEventListener('scroll', handleScroll);
            }
        })
        .catch((error) => {
            console.error('Error al cargar más libros:', error);
            loading = false;
            loadingDiv.style.display = 'none';
        });
}

function handleScroll() {
    if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 500) {
        loadMoreBooks();
    }
}

window.bookshelfApplySearch = function (query) {
    currentQuery = (query || '').trim();
    page = 1;

    const params = new URLSearchParams();
    params.set('page', '1');
    if (currentQuery) {
        params.set('q', currentQuery);
    }

    const url = `${window.location.pathname}?${params.toString()}`;
    window.history.replaceState({}, '', url);

    loading = true;
    loadingDiv.style.display = 'block';

    return fetch(`/bookshelf?${params.toString()}`, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
        .then((response) => response.json())
        .then((data) => {
            renderBooks(data.books || [], true);
            hasNext = Boolean(data.has_next);
            setTotalBooksLabel(data.total_books);
            loading = false;
            loadingDiv.style.display = 'none';

            window.removeEventListener('scroll', handleScroll);
            if (hasNext) {
                window.addEventListener('scroll', handleScroll);
            }

            return data;
        })
        .catch((error) => {
            console.error('Error al aplicar búsqueda:', error);
            loading = false;
            loadingDiv.style.display = 'none';
            throw error;
        });
};

document.addEventListener('DOMContentLoaded', function () {
    const initialQuery = new URLSearchParams(window.location.search).get('q');
    currentQuery = initialQuery ? initialQuery.trim() : '';
    hasNext = bookContainer.dataset.hasNext === 'true';

    if (hasNext) {
        window.addEventListener('scroll', handleScroll);
    }
});
