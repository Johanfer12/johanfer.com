document.addEventListener('DOMContentLoaded', function () {
    const searchBtn = document.getElementById('bookSearchBtn');
    const searchModal = document.getElementById('booksSearchModal');
    const searchForm = document.getElementById('booksSearchForm');
    const searchInput = document.getElementById('booksSearchInput');
    const searchCloseBtn = document.getElementById('booksSearchCloseBtn');
    const searchCancelBtn = document.getElementById('booksSearchCancelBtn');
    if (!searchBtn) {
        return;
    }

    const SEARCH_ICON = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" aria-hidden="true"><path d="M416 208c0 45.9-14.9 88.3-40 122.7L502.6 457.4c12.5 12.5 12.5 32.8 0 45.3s-32.8 12.5-45.3 0L330.7 376c-34.4 25.2-76.8 40-122.7 40C93.1 416 0 322.9 0 208S93.1 0 208 0S416 93.1 416 208zM208 352a144 144 0 1 0 0-288 144 144 0 1 0 0 288z"/></svg>';
    const CLEAR_ICON = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" aria-hidden="true"><rect width="256" height="256" fill="none"/><circle cx="128" cy="128" r="96" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="24"/><line x1="160" y1="96" x2="96" y2="160" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="24"/><line x1="160" y1="160" x2="96" y2="96" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="24"/></svg>';

    let currentQuery = '';

    const normalize = (value) => (value || '').trim();
    const hasActiveFilter = () => Boolean(normalize(currentQuery));

    const updateButtonState = (visibleCount = null) => {
        if (hasActiveFilter()) {
            searchBtn.classList.add('is-clear');
            searchBtn.setAttribute('aria-label', 'Limpiar búsqueda');
            searchBtn.title = visibleCount !== null ? `Limpiar búsqueda (${visibleCount} resultados)` : 'Limpiar búsqueda';
            searchBtn.innerHTML = CLEAR_ICON;
        } else {
            searchBtn.classList.remove('is-clear');
            searchBtn.setAttribute('aria-label', 'Buscar libros');
            searchBtn.title = 'Buscar libros';
            searchBtn.innerHTML = SEARCH_ICON;
        }
    };

    const openModal = () => {
        if (!searchModal) {
            return;
        }
        searchModal.style.display = 'flex';
        if (searchInput) {
            searchInput.value = currentQuery;
            searchInput.focus();
            searchInput.select();
        }
    };

    const closeModal = () => {
        if (searchModal) {
            searchModal.style.display = 'none';
        }
    };

    const clearFilter = () => {
        currentQuery = '';
        if (typeof window.bookshelfApplySearch === 'function') {
            window.bookshelfApplySearch('');
        }
        if (searchInput) {
            searchInput.value = '';
        }
        updateButtonState();
    };

    searchBtn.addEventListener('click', function () {
        if (hasActiveFilter()) {
            clearFilter();
            return;
        }
        openModal();
    });

    if (searchForm) {
        searchForm.addEventListener('submit', function (event) {
            event.preventDefault();
            currentQuery = normalize(searchInput ? searchInput.value : '');
            if (typeof window.bookshelfApplySearch === 'function') {
                window.bookshelfApplySearch(currentQuery)
                    .then((data) => {
                        closeModal();
                        updateButtonState(data.total_books);
                    })
                    .catch(() => {
                        closeModal();
                    });
            } else {
                closeModal();
            }
        });
    }

    if (searchCloseBtn) {
        searchCloseBtn.addEventListener('click', closeModal);
    }

    if (searchCancelBtn) {
        searchCancelBtn.addEventListener('click', closeModal);
    }

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            closeModal();
        }
    });

    const urlQuery = normalize(new URLSearchParams(window.location.search).get('q'));
    if (urlQuery) {
        currentQuery = urlQuery;
    }

    updateButtonState();
});
