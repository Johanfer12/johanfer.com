// Buscador de Mis Libros. El motor esta en search_modal.js, compartido con Mi TV.
document.addEventListener('DOMContentLoaded', function () {
    window.setupSearchModal({
        ids: {
            button: 'bookSearchBtn',
            modal: 'booksSearchModal',
            form: 'booksSearchForm',
            input: 'booksSearchInput',
            close: 'booksSearchCloseBtn',
            cancel: 'booksSearchCancelBtn',
        },
        searchLabel: 'Buscar libros',
        applySearch: 'bookshelfApplySearch',
        countKey: 'total_books',
    });
});
