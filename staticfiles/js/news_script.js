document.addEventListener('DOMContentLoaded', function() {
    const newsGrid = document.querySelector('.news-grid');
    const totalCounter = document.querySelector('.total');
    
    // Funciones para el modal
    window.openNewsModal = function(id) {
        const modal = document.getElementById(`modal-${id}`);
        modal.style.display = 'block';
        document.body.style.overflow = 'hidden';
    }

    window.closeNewsModal = function(id) {
        const modal = document.getElementById(`modal-${id}`);
        modal.style.display = 'none';
        document.body.style.overflow = 'auto';
    }

    // Cerrar modal al hacer clic fuera
    window.onclick = function(event) {
        if (event.target.classList.contains('modal')) {
            event.target.style.display = 'none';
            document.body.style.overflow = 'auto';
        }
    }

    // Función para manejar el borrado
    function attachDeleteListener(button) {
        button.addEventListener('click', function(e) {
            e.stopPropagation();
            const newsId = this.dataset.id;
            const container = document.querySelector(`.news-card-container:has([data-id="${newsId}"])`);
            const modal = document.getElementById(`modal-${newsId}`);
            const currentPage = new URLSearchParams(window.location.search).get('page') || 1;
            
            fetch(`/noticias/delete/${newsId}/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCookie('csrftoken'),
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: `current_page=${currentPage}`
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    // Actualizar el contador
                    const currentTotal = parseInt(totalCounter.textContent);
                    totalCounter.textContent = `${currentTotal - 1} noticias`;
                    
                    // Cerrar el modal
                    modal.style.display = 'none';
                    document.body.style.overflow = 'auto';
                    
                    if (data.html) {
                        const temp = document.createElement('div');
                        temp.innerHTML = data.html;
                        const newCard = temp.firstElementChild;
                        
                        const newDeleteBtn = newCard.querySelector('.delete-btn');
                        attachDeleteListener(newDeleteBtn);
                        
                        container.style.transition = 'opacity 0.3s ease-out';
                        container.style.opacity = '0';
                        
                        setTimeout(() => {
                            container.remove();
                            newCard.style.opacity = '0';
                            newsGrid.appendChild(newCard);
                            
                            requestAnimationFrame(() => {
                                newCard.style.transition = 'opacity 0.3s ease-in';
                                newCard.style.opacity = '1';
                            });
                        }, 300);
                    } else {
                        container.remove();
                    }
                }
            });
        });
    }

    // Inicializar los botones de borrado
    document.querySelectorAll('.delete-btn').forEach(button => {
        attachDeleteListener(button);
    });

    // Función para obtener el token CSRF
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    // Código para el botón de actualización del feed
    document.getElementById('updateFeedBtn').addEventListener('click', function() {
        const button = this;
        button.disabled = true;
        button.classList.add('loading');

        fetch('/noticias/update-feed/', {
            method: 'GET',
            headers: {
                'X-CSRFToken': getCookie('csrftoken'),
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                window.location.reload();
            } else {
                alert(data.message);
            }
        })
        .catch(error => {
            alert('Error al actualizar el feed');
            console.error('Error:', error);
        })
        .finally(() => {
            button.disabled = false;
            button.classList.remove('loading');
        });
    });
}); 