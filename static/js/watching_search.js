// Buscador de Mi TV. El motor esta en search_modal.js, compartido con Mis Libros.
document.addEventListener('DOMContentLoaded', function () {
    window.setupSearchModal({
        ids: {
            button: 'watchSearchBtn',
            modal: 'watchSearchModal',
            form: 'watchSearchForm',
            input: 'watchSearchInput',
            close: 'watchSearchCloseBtn',
            cancel: 'watchSearchCancelBtn',
        },
        searchLabel: 'Buscar',
        applySearch: 'watchingApplySearch',
        countKey: 'total_watched',
    });
});
