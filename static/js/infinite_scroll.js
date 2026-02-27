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

const createBookItem = (book) => {
    const item = document.createElement('div');
    item.className = 'book-item';
    const coverImage = (book.cover_image || '').replace('.jpg', '.webp');

    item.innerHTML = `
        <div class="book-info-container">
            <div class="book-cover" onclick="openModal('${book.id}')">
                <img src="${escapeHtml(coverImage)}" alt="${escapeHtml(book.title)}">
            </div>
            <div class="book-info">
                <a href="https://www.goodreads.com${escapeHtml(book.book_link)}" class="book-title" target="_blank">${escapeHtml(book.title)}</a>
                <p><strong>Autor</strong><br>${escapeHtml(book.author)}</p>
                <p><strong>Mi Calificación</strong><br>${'★'.repeat(book.my_rating)}</p>
                <p><strong>Calificación General</strong><br>${escapeHtml(book.public_rating)}</p>
                <p><strong>Lo leí el...</strong><br>${escapeHtml(book.date_read)}</p>
            </div>
        </div>
    `;

    return item;
};

const createBookModal = (book) => {
    const modal = document.createElement('div');
    modal.id = `modal-${book.id}`;
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content">
            <span class="close" onclick="closeModal('${book.id}')">&times;</span>
            <h2>${escapeHtml(book.title)}</h2>
            <p><strong>Autor:</strong> ${escapeHtml(book.author)}</p>
            <p><strong>Mi Calificación</strong> ${'★'.repeat(book.my_rating)}</p>
            <p><strong>Calificación General:</strong> ${escapeHtml(book.public_rating)}</p>
            <p><strong>Géneros:</strong> ${escapeHtml(book.genres || 'Sin género')}</p>
            <p><strong>Lo leí el...</strong> ${escapeHtml(book.date_read)}</p>
            <div class="book-description">
                <strong>Descripción</strong><br><br>
                ${book.description || 'No hay descripción disponible'}
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
