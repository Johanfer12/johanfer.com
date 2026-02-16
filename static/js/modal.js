// Abre el modal específico según el ID del libro
function openModal(bookId) {
    var modal = document.getElementById("modal-" + bookId);
    if (modal) {
        modal.style.display = "flex";
    }
}

// Cierra el modal específico
function closeModal(bookId) {
    var modal = document.getElementById("modal-" + bookId);
    if (modal) {
        modal.style.display = "none";
    }
}

// Cerrar el modal al hacer clic fuera del contenido
window.onclick = function(event) {
    // Si el usuario hace clic directamente en el .modal (fondo), se cierra
    if (event.target.classList.contains('modal')) {
        event.target.style.display = "none";
    }
} 
