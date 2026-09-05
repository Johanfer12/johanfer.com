// Abre el modal específico según el ID del libro
function openModal(bookId) {
    var modal = document.getElementById("modal-" + bookId);
    if (modal) {
        if (modal._closeTimer) {
            clearTimeout(modal._closeTimer);
            modal._closeTimer = null;
        }
        modal.classList.remove("modal-closing");
        modal.classList.add("modal-open");
        modal.style.display = "flex";
        modal._returnFocus = document.activeElement;
        (modal.querySelector('.close') || modal).focus({preventScroll: true});
    }
}

document.addEventListener('scroll', function(event) {
    const scrollArea = event.target;
    if (!scrollArea.classList || !scrollArea.classList.contains('book-description-scroll')) return;

    scrollArea.classList.add('is-scrolling');
    clearTimeout(scrollArea._scrollbarTimer);
    scrollArea._scrollbarTimer = setTimeout(function() {
        scrollArea.classList.remove('is-scrolling');
    }, 700);
}, true);

function closeModalElement(modal) {
    if (!modal || modal.classList.contains("modal-closing")) return;

    modal.classList.remove("modal-open");
    modal.classList.add("modal-closing");

    if (modal._returnFocus && modal._returnFocus.isConnected) {
        modal._returnFocus.focus({preventScroll: true});
        modal._returnFocus = null;
    }

    if (modal._closeTimer) clearTimeout(modal._closeTimer);
    modal._closeTimer = setTimeout(function() {
        modal.style.display = "none";
        modal.classList.remove("modal-closing");
        modal._closeTimer = null;
    }, 230);
}

// Cierra el modal específico
function closeModal(bookId) {
    closeModalElement(document.getElementById("modal-" + bookId));
}

// Cerrar el modal al hacer clic fuera del contenido
window.addEventListener('click', function(event) {
    // Si el usuario hace clic directamente en el .modal (fondo), se cierra
    if (event.target.classList.contains('modal')) {
        closeModalElement(event.target);
    }
});

// Delegación para incluir las portadas añadidas por el scroll infinito.
document.addEventListener('keydown', function(event) {
    const cover = event.target.closest('.book-cover[role="button"]');
    if (cover && (event.key === 'Enter' || event.key === ' ')) {
        event.preventDefault();
        cover.click();
        return;
    }

    const modal = document.querySelector('.modal.modal-open:not(.modal-closing)');
    if (!modal) return;
    if (event.key === 'Escape') {
        event.preventDefault();
        closeModalElement(modal);
    } else if (event.key === 'Tab') {
        const focusable = Array.from(modal.querySelectorAll(
            'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )).filter((element) => element.getClientRects().length && element.tabIndex >= 0);
        const first = focusable[0] || modal;
        const last = focusable[focusable.length - 1] || modal;
        if (!modal.contains(document.activeElement) ||
            (event.shiftKey && document.activeElement === first) ||
            (!event.shiftKey && document.activeElement === last) || !focusable.length) {
            event.preventDefault();
            (event.shiftKey ? last : first).focus();
        }
    }
});
