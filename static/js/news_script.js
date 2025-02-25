document.addEventListener('DOMContentLoaded', function() {
    const newsGrid = document.querySelector('.news-grid');
    const totalCounter = document.querySelector('.total');
    const newsModalsContainer = document.getElementById('news-modals-container');
    const newNewsNotification = document.getElementById('new-news-notification');
    const newNewsCountElement = document.getElementById('new-news-count');
    const headerCounter = document.querySelector('.header-counter'); // Contador en el header
    const closeNotificationBtn = document.getElementById('close-notification-btn');
    
    // Variables para el temporizador y control de visibilidad
    let notificationTimer = null;
    let notificationStartTime = 0;
    let notificationTimeLeft = 0;
    let isPageVisible = true;
    let totalPendingNewsCount = 0; // Contador acumulativo de noticias
    let userInteracted = false; // Indica si el usuario ha interactuado con la página
    const NOTIFICATION_DURATION = 10000; // 10 segundos
    
    // Detectar cuando la página cambia de visibilidad
    document.addEventListener('visibilitychange', function() {
        if (document.hidden) {
            // La página está en segundo plano
            isPageVisible = false;
            userInteracted = false;
            
            // Si hay un temporizador activo, pausarlo
            if (notificationTimer) {
                clearTimeout(notificationTimer);
                notificationTimer = null;
                
                // Calcular tiempo restante
                const elapsedTime = Date.now() - notificationStartTime;
                notificationTimeLeft = Math.max(0, NOTIFICATION_DURATION - elapsedTime);
                console.log(`Notificación pausada. Tiempo restante: ${notificationTimeLeft}ms`);
            }
        } else {
            // La página está visible nuevamente
            isPageVisible = true;
            
            // Si había un temporizador pausado, reanudarlo con el tiempo restante
            if (notificationTimeLeft > 0 && newNewsNotification.classList.contains('show')) {
                notificationStartTime = Date.now();
                notificationTimer = setTimeout(() => {
                    hideNotification();
                }, notificationTimeLeft);
                console.log(`Notificación reanudada. Tiempo restante: ${notificationTimeLeft}ms`);
            }
        }
    });
    
    // Detectar interacción del usuario
    document.addEventListener('click', function() {
        userInteracted = true;
    });
    
    document.addEventListener('scroll', function() {
        userInteracted = true;
    });
    
    // Log para verificar que el contador se ha encontrado
    if (headerCounter) {
        console.log('Contador en el header encontrado:', headerCounter.textContent);
    } else {
        console.warn('No se pudo encontrar el contador en el header (.header-counter)');
    }
    
    // Almacenar la última vez que se comprobaron las noticias
    let lastChecked = new Date().toISOString();
    
    // Comprobación periódica de nuevas noticias (cada 30 segundos)
    const CHECK_INTERVAL = 30000; // 30 segundos
    let pendingNews = [];
    
    // Añadir onclick a todas las tarjetas al cargar la página
    document.querySelectorAll('.news-card').forEach(card => {
        const newsId = card.closest('.news-card-container').id.replace('news-', '');
        card.setAttribute('onclick', `openNewsModal('${newsId}')`);
    });

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
    
    // Función para mostrar la notificación con auto-cierre
    function showNotification(count) {
        // Acumular el conteo de noticias si no ha habido interacción
        if (!userInteracted && newNewsNotification.classList.contains('show')) {
            totalPendingNewsCount += count;
        } else {
            totalPendingNewsCount = count;
        }
        
        // Actualizar el contenido con el total acumulado
        newNewsCountElement.textContent = `${totalPendingNewsCount} nuevas noticias añadidas`;
        
        // Mostrar la notificación
        newNewsNotification.classList.remove('hiding');
        newNewsNotification.classList.add('show');
        
        // Limpiar temporizador anterior si existe
        if (notificationTimer) {
            clearTimeout(notificationTimer);
            notificationTimer = null;
        }
        
        // Solo iniciar el temporizador si la página está visible
        if (isPageVisible) {
            notificationStartTime = Date.now();
            notificationTimeLeft = NOTIFICATION_DURATION;
            
            // Configurar el temporizador para ocultar la notificación después de 10 segundos
            notificationTimer = setTimeout(() => {
                hideNotification();
            }, NOTIFICATION_DURATION);
            
            console.log(`Notificación mostrada. Se ocultará en ${NOTIFICATION_DURATION/1000} segundos si la página sigue visible.`);
        } else {
            // Si la página no está visible, guardar el tiempo completo para cuando vuelva a ser visible
            notificationTimeLeft = NOTIFICATION_DURATION;
            console.log('Notificación mostrada. El temporizador iniciará cuando la página sea visible.');
        }
    }
    
    // Función para ocultar la notificación
    function hideNotification() {
        newNewsNotification.classList.add('hiding');
        setTimeout(() => {
            newNewsNotification.classList.remove('show', 'hiding');
        }, 500); // Tiempo para que termine la animación de opacidad
        
        // Limpiar el temporizador y reiniciar variables
        if (notificationTimer) {
            clearTimeout(notificationTimer);
            notificationTimer = null;
        }
        notificationTimeLeft = 0;
        totalPendingNewsCount = 0; // Reiniciar el contador acumulativo
        userInteracted = false; // Reiniciar la bandera de interacción
        console.log('Notificación ocultada.');
    }
    
    // Cerrar notificación cuando se haga clic en el botón de cierre
    closeNotificationBtn.addEventListener('click', function() {
        hideNotification();
    });

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
            
            // Encontrar el contenedor y el modal
            const container = document.getElementById(`news-${newsId}`);
            const modal = document.getElementById(`modal-${newsId}`);
            const currentPage = new URLSearchParams(window.location.search).get('page') || 1;
            
            // Asegurarse de que se encontró el contenedor antes de continuar
            if (!container) {
                console.error(`No se encontró el contenedor para el ID: ${newsId}`);
                return;
            }
            
            // Aplicar clase para animación de eliminación
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
                    // Actualizar contador en el header inmediatamente
                    updateHeaderCounter(-1);
                    
                    // Actualizar contador de "total" si existe
                    const currentTotal = parseInt(totalCounter?.textContent || "0");
                    if (totalCounter) {
                        totalCounter.textContent = `${currentTotal - 1} noticias`;
                    }
                    
                    // Cerrar el modal si está abierto
                    if (modal) {
                        modal.style.display = 'none';
                        document.body.style.overflow = 'auto';
                    }
                    
                    if (data.html) {
                        setTimeout(() => {
                            container.remove();
                            
                            const temp = document.createElement('div');
                            temp.innerHTML = data.html;
                            const newCard = temp.firstElementChild;
                            newCard.classList.add('inserting');
                            
                            const newDeleteBtn = newCard.querySelector('.delete-btn');
                            if (newDeleteBtn) {
                                attachDeleteListener(newDeleteBtn);
                            }
                            
                            // Asegurar que el evento onclick esté configurado
                            const card = newCard.querySelector('.news-card');
                            if (card) {
                                const newCardId = newCard.id.replace('news-', '');
                                card.setAttribute('onclick', `openNewsModal('${newCardId}')`);
                            }
                            
                            newsGrid.appendChild(newCard);
                            animateReposition(oldPositions);
                        }, 500); // Esperar 500ms para que la animación de eliminación termine
                    } else {
                        setTimeout(() => {
                            container.remove();
                            animateReposition(oldPositions);
                        }, 500); // Esperar 500ms para que la animación de eliminación termine
                    }
                }
            });
        });
    }

    // Función auxiliar para encontrar el contenedor por el ID del botón (ya no la usamos)
    function findContainerByButtonId(buttonId) {
        // Buscar primero en los botones de la tarjeta
        const button = document.querySelector(`.delete-btn[data-id="${buttonId}"]`);
        if (button && button.closest('.news-card-container')) {
            return button.closest('.news-card-container');
        }
        
        // Si no se encuentra, buscar en los botones del modal y relacionarlo con el contenedor correspondiente
        const modalButton = document.querySelector(`.btn-danger[data-id="${buttonId}"]`);
        if (modalButton) {
            // Buscar el contenedor por ID
            return document.getElementById(`news-${buttonId}`);
        }
        
        return null;
    }
    
    // Función para actualizar el contador en el header
    function updateHeaderCounter(change) {
        if (headerCounter) {
            const current = parseInt(headerCounter.textContent || "0");
            const newValue = current + change;
            headerCounter.textContent = newValue;
            
            // Añadir animación sutil para destacar el cambio
            headerCounter.classList.add('counter-updated');
            setTimeout(() => {
                headerCounter.classList.remove('counter-updated');
            }, 1000);
            
            console.log(`Contador actualizado: ${current} → ${newValue}`);
        } else {
            console.warn('No se encontró el elemento del contador en el header');
        }
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
                checkForNewNews(true);
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
    
    // Comprobar nuevas noticias
    function checkForNewNews(showImmediately = false) {
        fetch(`/noticias/check-new-news/?last_checked=${encodeURIComponent(lastChecked)}`)
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    // Actualizar la última vez que se comprobaron las noticias
                    lastChecked = data.current_time;
                    
                    // Si hay nuevas noticias
                    if (data.news_cards && data.news_cards.length > 0) {
                        console.log(`Se encontraron ${data.news_cards.length} noticias nuevas`);
                        
                        // Almacenar las nuevas noticias
                        pendingNews = data.news_cards;
                        
                        // Mostrar notificación de nuevas noticias (solo informativa)
                        showNotification(pendingNews.length);
                        
                        // Cargar las noticias automáticamente
                        loadNewNews();
                    }
                }
            })
            .catch(error => {
                console.error('Error al comprobar nuevas noticias:', error);
            });
    }
    
    // Cargar nuevas noticias
    function loadNewNews() {
        if (pendingNews.length === 0) return;
        
        // Guardar posiciones actuales para animación
        const oldPositions = capturePositions();
        
        // Número máximo de noticias en la página (25)
        const MAX_NEWS = 25;
        
        // Invertir el array para que las noticias más recientes aparezcan primero
        pendingNews.reverse();
        
        // Variable para contar cuántas noticias realmente se añadieron (después del límite)
        let actuallyAddedCount = 0;
        
        // Actualizar inmediatamente el contador en el header
        // Si ya hay una notificación visible, usar el conteo acumulado
        if (newNewsNotification.classList.contains('show') && !userInteracted) {
            // Ya hay una notificación visible, usar la cantidad acumulada para actualizar el header
            updateHeaderCounter(pendingNews.length);
        } else {
            // Primera actualización o después de interacción del usuario
            updateHeaderCounter(pendingNews.length);
        }
        
        // Añadir las nuevas noticias al inicio del grid
        pendingNews.forEach((newsItem, index) => {
            // Crear elemento temporal para convertir el HTML en un nodo DOM
            const temp = document.createElement('div');
            temp.innerHTML = newsItem.card;
            
            // Obtener el contenedor de la noticia
            const newsContainer = temp.firstElementChild;
            newsContainer.classList.add('new-news');
            
            // Añadir el modal al contenedor de modales
            const modalTemp = document.createElement('div');
            modalTemp.innerHTML = newsItem.modal;
            const modal = modalTemp.firstElementChild;
            newsModalsContainer.appendChild(modal);
            
            // Añadir evento onclick al contenedor de la tarjeta para abrir el modal
            const card = newsContainer.querySelector('.news-card');
            if (card) {
                card.setAttribute('onclick', `openNewsModal('${newsItem.id}')`);
            }
            
            // Configurar el botón de cierre del modal
            const closeBtn = modal.querySelector('.close');
            if (closeBtn) {
                closeBtn.onclick = function() {
                    closeNewsModal(newsItem.id);
                };
            }
            
            // Añadir listener para botones de eliminación en la tarjeta
            const deleteBtn = newsContainer.querySelector('.delete-btn');
            if (deleteBtn) {
                attachDeleteListener(deleteBtn);
            }
            
            // Añadir listener para botones de eliminación en el modal
            const modalDeleteBtn = modal.querySelector('.btn-danger');
            if (modalDeleteBtn) {
                modalDeleteBtn.setAttribute('data-id', newsItem.id);
                attachDeleteListener(modalDeleteBtn);
            }
            
            // Añadir al principio del grid
            newsGrid.insertBefore(newsContainer, newsGrid.firstChild);
            actuallyAddedCount++;
            
            // Si superamos el límite, eliminar las más antiguas
            if (newsGrid.children.length > MAX_NEWS) {
                const lastChild = newsGrid.lastElementChild;
                const lastChildId = lastChild.id.replace('news-', '');
                
                // Eliminar también el modal correspondiente
                const lastModal = document.getElementById(`modal-${lastChildId}`);
                if (lastModal) {
                    lastModal.remove();
                }
                
                lastChild.remove();
                actuallyAddedCount--; // Restamos una noticia del contador porque es reemplazada, no añadida
            }
        });
        
        // Animar reposicionamiento
        animateReposition(oldPositions);
        
        // Actualizar el contador total si existe
        if (totalCounter) {
            const currentTotal = parseInt(totalCounter.textContent.split(' ')[0] || "0");
            totalCounter.textContent = `${currentTotal + actuallyAddedCount} noticias`;
        }
        
        console.log(`Se añadieron ${actuallyAddedCount} noticias nuevas de ${pendingNews.length} totales`);
        
        // Limpiar las noticias pendientes
        pendingNews = [];
    }
    
    // Iniciar comprobación periódica
    setInterval(checkForNewNews, CHECK_INTERVAL);
}); 