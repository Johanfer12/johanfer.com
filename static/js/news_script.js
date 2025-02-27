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
                    // Cerrar el modal si está abierto
                    if (modal) {
                        modal.style.display = 'none';
                        document.body.style.overflow = 'auto';
                    }
                    
                    // Usar el total de noticias devuelto por el servidor para actualizar los contadores
                    updateCountersFromServer(data.total_news, data.total_pages);
                    
                    if (data.html) {
                        setTimeout(() => {
                            container.remove();
                            // También eliminamos el modal asociado a la noticia eliminada
                            if (modal) {
                                modal.remove();
                            }
                            
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
                            
                            // Añadir la nueva tarjeta
                            newsGrid.appendChild(newCard);
                            
                            // Añadir el modal para la nueva noticia
                            if (data.modal) {
                                const modalTemp = document.createElement('div');
                                modalTemp.innerHTML = data.modal;
                                const newModal = modalTemp.firstElementChild;
                                
                                // Añadir al contenedor de modales
                                newsModalsContainer.appendChild(newModal);
                                
                                // Configurar el botón de cierre
                                const closeBtn = newModal.querySelector('.close');
                                if (closeBtn) {
                                    closeBtn.onclick = function() {
                                        closeNewsModal(newCardId);
                                    };
                                }
                                
                                // Configurar botón de eliminación en el modal
                                const modalDeleteBtn = newModal.querySelector('.btn-danger');
                                if (modalDeleteBtn) {
                                    modalDeleteBtn.setAttribute('data-id', newCardId);
                                    attachDeleteListener(modalDeleteBtn);
                                }
                            }
                            
                            animateReposition(oldPositions);
                        }, 500); // Esperar 500ms para que la animación de eliminación termine
                    } else {
                        setTimeout(() => {
                            container.remove();
                            // También eliminamos el modal asociado a la noticia eliminada
                            if (modal) {
                                modal.remove();
                            }
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
            // Asegurarnos de que el nuevo valor no sea negativo
            const newValue = Math.max(0, current + change);
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
                        
                        // Actualizar el contador total si está disponible en la respuesta
                        updateCountersFromServer(data.total_news, data.total_pages);
                        
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
        
        // Variable para contar cuántas noticias realmente se añadieron (después del límite)
        let actuallyAddedCount = 0;
        
        // IMPORTANTE: Asegurarnos que las noticias estén ordenadas por fecha (más reciente primero)
        // Para esto, necesitamos extraer la fecha de publicación de cada noticia
        pendingNews.forEach(item => {
            // Extraer fecha de publicación del HTML
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = item.card;
            const dateText = tempDiv.querySelector('.news-meta').textContent;
            const dateParts = dateText.split(' - ')[1].trim().split(' ');
            const datePart = dateParts[0]; // dd/mm/yyyy
            const timePart = dateParts[1]; // hh:mm
            
            // Convertir a objeto Date de JavaScript
            const [day, month, year] = datePart.split('/');
            const [hours, minutes] = timePart.split(':');
            item.publishedDate = new Date(year, month-1, day, hours, minutes);
        });
        
        // Ordenar las noticias por fecha (más reciente primero)
        pendingNews.sort((a, b) => b.publishedDate - a.publishedDate);
        
        // Ahora insertamos las noticias en el orden correcto
        // Primero, eliminar las noticias actuales que exceden el límite cuando añadamos las nuevas
        const currentCount = newsGrid.children.length;
        const willExceedBy = Math.max(0, currentCount + pendingNews.length - MAX_NEWS);
        
        // Si hay que eliminar noticias antiguas, hacerlo antes de añadir las nuevas
        if (willExceedBy > 0) {
            // Obtener las últimas noticias que serán eliminadas
            for (let i = 0; i < willExceedBy; i++) {
                if (newsGrid.lastElementChild) {
                    const lastChild = newsGrid.lastElementChild;
                    const lastChildId = lastChild.id.replace('news-', '');
                    
                    // Eliminar también el modal correspondiente
                    const lastModal = document.getElementById(`modal-${lastChildId}`);
                    if (lastModal) {
                        lastModal.remove();
                    }
                    
                    lastChild.remove();
                }
            }
        }
        
        // Crear un fragmento para todas las nuevas noticias
        const fragment = document.createDocumentFragment();
        const newCards = [];
        
        // Preparar todas las noticias nuevas
        pendingNews.forEach((newsItem) => {
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
            
            // Guardar la noticia para insertar después
            newCards.push(newsContainer);
            actuallyAddedCount++;
        });
        
        // Ahora necesitamos encontrar dónde insertar cada noticia para mantener el orden correcto
        if (newsGrid.children.length === 0) {
            // Si no hay noticias, simplemente añadir todas
            newCards.forEach(card => {
                fragment.appendChild(card);
            });
            newsGrid.appendChild(fragment);
        } else {
            // Necesitamos insertar las nuevas noticias en el orden correcto
            // Primero, recolectar todas las fechas de las noticias actuales
            const existingCards = Array.from(newsGrid.children);
            const existingDates = [];
            
            existingCards.forEach(card => {
                const dateText = card.querySelector('.news-meta').textContent;
                const dateParts = dateText.split(' - ')[1].trim().split(' ');
                const datePart = dateParts[0]; // dd/mm/yyyy
                const timePart = dateParts[1]; // hh:mm
                
                const [day, month, year] = datePart.split('/');
                const [hours, minutes] = timePart.split(':');
                const date = new Date(year, month-1, day, hours, minutes);
                
                existingDates.push({ card, date });
            });
            
            // Ordenar las noticias existentes por fecha (más reciente primero)
            existingDates.sort((a, b) => b.date - a.date);
            
            // Combinar las nuevas noticias con las existentes manteniendo el orden
            let newGridChildren = [];
            let newIdx = 0;
            let existingIdx = 0;
            
            while (newIdx < newCards.length && existingIdx < existingDates.length) {
                const newCardDate = pendingNews[newIdx].publishedDate;
                const existingCardDate = existingDates[existingIdx].date;
                
                if (newCardDate >= existingCardDate) {
                    newGridChildren.push(newCards[newIdx]);
                    newIdx++;
                } else {
                    newGridChildren.push(existingDates[existingIdx].card);
                    existingIdx++;
                }
            }
            
            // Añadir las noticias restantes
            while (newIdx < newCards.length) {
                newGridChildren.push(newCards[newIdx]);
                newIdx++;
            }
            
            while (existingIdx < existingDates.length) {
                newGridChildren.push(existingDates[existingIdx].card);
                existingIdx++;
            }
            
            // Limpiar el grid actual
            while (newsGrid.firstChild) {
                newsGrid.removeChild(newsGrid.firstChild);
            }
            
            // Añadir las noticias en el nuevo orden
            newGridChildren.forEach(card => {
                newsGrid.appendChild(card);
            });
        }
        
        // Animar reposicionamiento
        animateReposition(oldPositions);
        
        // Aquí ya no actualizamos directamente los contadores, usamos el valor del servidor
        // Hacemos una solicitud para obtener el conteo actualizado
        fetch('/noticias/get-news-count/')
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    updateCountersFromServer(data.total_news, data.total_pages);
                }
            })
            .catch(error => {
                console.error('Error al obtener el conteo actualizado:', error);
                // En caso de error, actualizamos con un valor estimado
                if (headerCounter && totalCounter) {
                    const currentTotal = parseInt(headerCounter.textContent || "0");
                    const newTotal = currentTotal + actuallyAddedCount;
                    updateCountersFromServer(newTotal);
                }
            });
        
        console.log(`Se añadieron ${actuallyAddedCount} noticias nuevas de ${pendingNews.length} totales`);
        
        // Limpiar las noticias pendientes
        pendingNews = [];
    }
    
    // Función para actualizar la paginación
    function updatePagination(serverTotalPages) {
        // Obtener el total de noticias y calcular el número de páginas
        const totalItems = parseInt(headerCounter?.textContent || "0");
        const itemsPerPage = 25; // Mismo valor que en el backend
        
        // Usar el total de páginas del servidor si está disponible, de lo contrario calcularlo
        const totalPages = serverTotalPages !== undefined ? serverTotalPages : Math.ceil(totalItems / itemsPerPage);
        
        // Obtener la página actual
        const currentPage = parseInt(new URLSearchParams(window.location.search).get('page') || "1");
        
        // Verificar si necesitamos paginación
        const needsPagination = totalPages > 1;
        
        // Buscar el elemento de paginación existente
        let pagination = document.querySelector('.pagination');
        
        // Si no hay paginación y no la necesitamos, no hacemos nada
        if (!pagination && !needsPagination) {
            return;
        }
        
        // Si necesitamos paginación pero no existe el elemento, lo creamos
        if (!pagination && needsPagination) {
            // Crear el elemento de paginación
            pagination = document.createElement('div');
            pagination.className = 'pagination';
            
            // Crear enlace "Anterior"
            const prevLink = document.createElement('a');
            prevLink.href = '#';
            prevLink.textContent = 'Anterior';
            pagination.appendChild(prevLink);
            
            // Crear el span activo
            const activeSpan = document.createElement('span');
            activeSpan.className = 'active';
            pagination.appendChild(activeSpan);
            
            // Crear enlace "Siguiente"
            const nextLink = document.createElement('a');
            nextLink.href = '#';
            nextLink.textContent = 'Siguiente';
            pagination.appendChild(nextLink);
            
            // Añadir funcionalidad a los enlaces
            prevLink.addEventListener('click', function(e) {
                e.preventDefault();
                if (currentPage > 1) {
                    window.location.href = `?page=${currentPage - 1}`;
                }
            });
            
            nextLink.addEventListener('click', function(e) {
                e.preventDefault();
                if (currentPage < totalPages) {
                    window.location.href = `?page=${currentPage + 1}`;
                }
            });
            
            // Añadir la paginación después del grid de noticias
            const newsGrid = document.querySelector('.news-grid');
            if (newsGrid) {
                newsGrid.parentNode.insertBefore(pagination, newsGrid.nextSibling);
            }
        }
        
        // Si ya no necesitamos paginación pero existe el elemento, lo eliminamos
        if (pagination && !needsPagination) {
            pagination.remove();
            return;
        }
        
        // Actualizar el texto de la página actual
        const activeSpan = pagination.querySelector('.active');
        if (activeSpan) {
            activeSpan.textContent = `${currentPage} / ${totalPages}`;
        }
        
        // Actualizar enlaces de navegación
        const prevLink = pagination.querySelector('a:first-child');
        const nextLink = pagination.querySelector('a:last-child');
        
        if (prevLink) {
            if (currentPage > 1) {
                prevLink.style.display = '';
                prevLink.href = `?page=${currentPage - 1}`;
            } else {
                prevLink.style.display = 'none';
            }
        }
        
        if (nextLink) {
            if (currentPage < totalPages) {
                nextLink.style.display = '';
                nextLink.href = `?page=${currentPage + 1}`;
            } else {
                nextLink.style.display = 'none';
            }
        }
    }
    
    // Nueva función para actualizar todos los contadores desde el servidor
    function updateCountersFromServer(totalCount, totalPages) {
        if (totalCount === undefined) return;
        
        // Actualizar contador en el header
        if (headerCounter) {
            const current = parseInt(headerCounter.textContent || "0");
            
            // Verificar si realmente hay un cambio para evitar animaciones innecesarias
            if (current !== totalCount) {
                headerCounter.textContent = totalCount;
                
                // Añadir animación sutil para destacar el cambio
                headerCounter.classList.add('counter-updated');
                setTimeout(() => {
                    headerCounter.classList.remove('counter-updated');
                }, 1000);
                
                console.log(`Contador actualizado desde servidor: ${current} → ${totalCount}`);
            }
        }
        
        // Actualizar contador de "total" si existe
        if (totalCounter) {
            totalCounter.textContent = `${totalCount} noticias`;
        }
        
        // Actualizar la paginación si el total ha cambiado
        updatePagination(totalPages);
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
                // Actualizar los contadores si se recibe el total de noticias
                if (data.total_news !== undefined) {
                    updateCountersFromServer(data.total_news, data.total_pages);
                }
                
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
    
    // Iniciar comprobación periódica
    setInterval(checkForNewNews, CHECK_INTERVAL);
}); 