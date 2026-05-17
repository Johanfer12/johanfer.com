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
    }
}

function closeModalElement(modal) {
    if (!modal || modal.classList.contains("modal-closing")) return;

    modal.classList.remove("modal-open");
    modal.classList.add("modal-closing");

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
window.onclick = function(event) {
    // Si el usuario hace clic directamente en el .modal (fondo), se cierra
    if (event.target.classList.contains('modal')) {
        closeModalElement(event.target);
    }
} 
