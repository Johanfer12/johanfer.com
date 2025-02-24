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

    // Función para capturar las posiciones actuales de cada tarjeta
    function capturePositions() {
        const positions = new Map();
        document.querySelectorAll('.news-card-container').forEach(container => {
            positions.set(container, container.getBoundingClientRect());
        });
        return positions;
    }

    // Función que aplica la técnica FLIP para animar el reordenamiento
    function animateReposition(oldPositions) {
        // Verificar si estamos en un dispositivo móvil
        const isMobile = window.innerWidth <= 767;
        
        if (!isMobile) {
            document.querySelectorAll('.news-card-container').forEach(container => {
                const oldRect = oldPositions.get(container);
                const newRect = container.getBoundingClientRect();
                if (oldRect) {
                    const deltaX = oldRect.left - newRect.left;
                    const deltaY = oldRect.top - newRect.top;
                    if (deltaX !== 0 || deltaY !== 0) {
                        container.style.transform = `translate(${deltaX}px, ${deltaY}px)`;
                        container.getBoundingClientRect();
                        container.style.transition = 'transform 0.5s ease';
                        container.style.transform = '';
                        container.addEventListener('transitionend', function handler() {
                            container.style.transition = '';
                            container.removeEventListener('transitionend', handler);
                        });
                    }
                }
            });
        }
    }

    // Función para manejar el borrado
    function attachDeleteListener(button) {
        button.addEventListener('click', function(e) {
            e.stopPropagation();
            const newsId = this.dataset.id;
            const oldPositions = capturePositions();
            
            const container = document.querySelector(`.news-card-container:has([data-id="${newsId}"])`);
            const modal = document.getElementById(`modal-${newsId}`);
            const currentPage = new URLSearchParams(window.location.search).get('page') || 1;
            
            container.classList.add('deleting');
            
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
                    const currentTotal = parseInt(totalCounter.textContent);
                    totalCounter.textContent = `${currentTotal - 1} noticias`;
                    
                    modal.style.display = 'none';
                    document.body.style.overflow = 'auto';
                    
                    if (data.html) {
                        setTimeout(() => {
                            container.remove();
                            
                            const temp = document.createElement('div');
                            temp.innerHTML = data.html;
                            const newCard = temp.firstElementChild;
                            newCard.classList.add('inserting');
                            
                            // Corregir la orientación del reverso de la nueva tarjeta
                            const cardBack = newCard.querySelector('.card-back');
                            if (cardBack) {
                                cardBack.style.transform = 'rotateY(180deg)';
                            }
                            
                            const newDeleteBtn = newCard.querySelector('.delete-btn');
                            attachDeleteListener(newDeleteBtn);
                            
                            newsGrid.appendChild(newCard);
                            animateReposition(oldPositions);
                        }, 500);
                    } else {
                        setTimeout(() => {
                            container.remove();
                            animateReposition(oldPositions);
                        }, 500);
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