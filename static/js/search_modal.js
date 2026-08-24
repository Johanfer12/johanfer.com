// Motor del buscador con modal, compartido por Mis Libros y Mi TV.
//
// Las dos paginas tenian el mismo fichero copiado (98 de 111 lineas iguales);
// lo unico que cambiaba eran los ids del marcado, el texto del boton, el nombre
// del callback que aplica el filtro y la clave del contador en su respuesta.
//
// El boton hace de interruptor: sin filtro abre el modal, con filtro lo limpia.
window.setupSearchModal = function ({ids, searchLabel, applySearch, countKey}) {
    const el = (id) => document.getElementById(id);
    const searchBtn = el(ids.button);
    if (!searchBtn) {
        return;
    }

    const searchModal = el(ids.modal);
    const searchForm = el(ids.form);
    const searchInput = el(ids.input);
    const searchCloseBtn = el(ids.close);
    const searchCancelBtn = el(ids.cancel);

    const SEARCH_ICON = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" aria-hidden="true"><path d="M416 208c0 45.9-14.9 88.3-40 122.7L502.6 457.4c12.5 12.5 12.5 32.8 0 45.3s-32.8 12.5-45.3 0L330.7 376c-34.4 25.2-76.8 40-122.7 40C93.1 416 0 322.9 0 208S93.1 0 208 0S416 93.1 416 208zM208 352a144 144 0 1 0 0-288 144 144 0 1 0 0 288z"/></svg>';
    const CLEAR_ICON = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" aria-hidden="true"><rect width="256" height="256" fill="none"/><circle cx="128" cy="128" r="96" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="24"/><line x1="160" y1="96" x2="96" y2="160" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="24"/><line x1="160" y1="160" x2="96" y2="96" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="24"/></svg>';

    let currentQuery = '';

    const normalize = (value) => (value || '').trim();
    const hasActiveFilter = () => Boolean(normalize(currentQuery));
    const apply = () => (typeof window[applySearch] === 'function' ? window[applySearch] : null);

    const updateButtonState = (visibleCount = null) => {
        if (hasActiveFilter()) {
            searchBtn.classList.add('is-clear');
            searchBtn.setAttribute('aria-label', 'Limpiar búsqueda');
            searchBtn.title = visibleCount !== null ? `Limpiar búsqueda (${visibleCount} resultados)` : 'Limpiar búsqueda';
            searchBtn.innerHTML = CLEAR_ICON;
        } else {
            searchBtn.classList.remove('is-clear');
            searchBtn.setAttribute('aria-label', searchLabel);
            searchBtn.title = searchLabel;
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
        const run = apply();
        if (run) {
            run('');
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
            const run = apply();
            if (run) {
                run(currentQuery)
                    .then((data) => {
                        closeModal();
                        updateButtonState(data[countKey]);
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
};
