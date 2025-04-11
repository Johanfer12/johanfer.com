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
    
    // Detectar si estamos en un dispositivo móvil
    const isMobile = () => window.innerWidth <= 767;
    
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
    
    // Añadir detector de eventos para evitar la rotación al pasar el mouse sobre las imágenes
    function setupImageHoverHandlers() {
        document.querySelectorAll('.news-card .news-image').forEach(image => {
            image.addEventListener('mouseenter', function() {
                const card = this.closest('.news-card');
                if (card) {
                    card.classList.add('image-hover');
                }
            });
            
            image.addEventListener('mouseleave', function() {
                const card = this.closest('.news-card');
                if (card) {
                    card.classList.remove('image-hover');
                }
            });
        });
        
        // Agregar evento para el botón de eliminar
        document.querySelectorAll('.mobile-delete-btn').forEach(button => {
            button.addEventListener('mouseenter', function(e) {
                // Detener propagación para evitar conflictos
                e.stopPropagation();
                const card = this.closest('.news-card');
                if (card) {
                    card.classList.add('delete-hover');
                }
            });
            
            button.addEventListener('mouseleave', function(e) {
                // Detener propagación para evitar conflictos
                e.stopPropagation();
                const card = this.closest('.news-card');
                if (card) {
                    card.classList.remove('delete-hover');
                }
            });
        });
    }
    
    // Invocar la función para configurar los manejadores de hover
    setupImageHoverHandlers();
    
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
    
    // Comprobación periódica de nuevas noticias (cada 3 minutos)
    const CHECK_INTERVAL = 180000; // 3 minutos (3 * 60 * 1000 ms)
    let pendingNews = [];
    
    // Actualizar el comportamiento de las tarjetas según el dispositivo
    function updateCardBehavior() {
        document.querySelectorAll('.news-card').forEach(card => {
            const newsId = card.closest('.news-card-container').id.replace('news-', '');
            const container = card.closest('.news-card-container');
            const cardBack = card.querySelector('.card-back');
            const linksContainer = cardBack?.querySelector('.news-links');
            const cardFront = card.querySelector('.card-front');

            // Eliminar el onclick de la tarjeta principal SIEMPRE primero
            card.removeAttribute('onclick');

            // Limpiar botones específicos de vista (modal opener y delete móvil en front)
            const existingModalOpener = cardBack?.querySelector('.news-link.modal-opener');
            if (existingModalOpener) existingModalOpener.remove();
            const existingMobileDeleteBtn = cardFront?.querySelector('.mobile-delete-btn');
            if (existingMobileDeleteBtn) existingMobileDeleteBtn.remove();


            if (isMobile()) {
                // --- Comportamiento Móvil ---

                // Añadir botón de eliminación móvil al frente de la tarjeta
                if (cardFront && container.querySelector('.delete-btn')) {
                    const deleteBtn = document.createElement('button');
                    deleteBtn.className = 'mobile-delete-btn';
                    deleteBtn.setAttribute('type', 'button');
                    deleteBtn.setAttribute('data-id', newsId);
                    deleteBtn.onclick = function(e) {
                        e.stopPropagation();
                        deleteNews(newsId);
                        return false;
                    };
                    cardFront.appendChild(deleteBtn);
                }

                // Añadir botón "Ver más" al reverso de la tarjeta
                if (linksContainer) {
                    const modalLink = document.createElement('a');
                    modalLink.href = 'javascript:void(0)';
                    modalLink.className = 'news-link modal-opener';
                    modalLink.textContent = 'Más';
                    modalLink.addEventListener('click', function(e) {
                        e.stopPropagation();
                        openNewsModal(newsId);
                    });
                    // Insertar "Más" antes que otros links (Fuente, Eliminar)
                    linksContainer.insertBefore(modalLink, linksContainer.firstChild);
                }

            } else {
                // --- Comportamiento Escritorio ---

                // Añadir botón de eliminación (estilo móvil) al frente
                if (cardFront && container.querySelector('.delete-btn')) {
                    const deleteBtn = document.createElement('button');
                    deleteBtn.className = 'mobile-delete-btn'; // Reutilizamos estilo
                    deleteBtn.setAttribute('type', 'button');
                    deleteBtn.setAttribute('data-id', newsId);
                    deleteBtn.onclick = function(e) {
                        e.stopPropagation();
                        deleteNews(newsId);
                        return false;
                    };
                    cardFront.appendChild(deleteBtn);
                }

                // Añadir botón "Ver más" al reverso de la tarjeta (igual que en móvil)
                if (linksContainer) {
                    const modalLink = document.createElement('a');
                    modalLink.href = 'javascript:void(0)';
                    modalLink.className = 'news-link modal-opener';
                    modalLink.textContent = 'Más';
                    modalLink.addEventListener('click', function(e) {
                        e.stopPropagation();
                        openNewsModal(newsId);
                    });
                     // Insertar "Más" antes que otros links (Fuente, Eliminar)
                    linksContainer.insertBefore(modalLink, linksContainer.firstChild);
                }
            }
        });

        // Configurar los manejadores de hover para las imágenes
        setupImageHoverHandlers();
    }

    // Actualizar comportamiento al cargar y al cambiar tamaño de ventana
    updateCardBehavior();
    window.addEventListener('resize', updateCardBehavior);

    // Funciones para el modal
    window.openNewsModal = function(id) {
        const modal = document.getElementById(`modal-${id}`);
        modal.style.display = 'block';
        // Agregar la clase 'show' después de un breve retardo para permitir la transición
        setTimeout(() => modal.classList.add('show'), 10);
        document.body.style.overflow = 'hidden';
    }

    window.closeNewsModal = function(id) {
        const modal = document.getElementById(`modal-${id}`);
        modal.classList.remove('show');
        // Esperar a que termine la transición para ocultar el modal
        setTimeout(() => {
            modal.style.display = 'none';
            document.body.style.overflow = 'auto';
        }, 300);
    }

    // Cerrar modal al hacer clic fuera
    window.onclick = function(event) {
        if (event.target.classList.contains('modal')) {
            const modalId = event.target.id.replace('modal-', '');
            closeNewsModal(modalId);
        }
    }
    
    // Configurar correctamente todos los botones de cierre al cargar la página
    document.querySelectorAll('.modal .close').forEach(closeBtn => {
        const modalId = closeBtn.closest('.modal').id.replace('modal-', '');
        closeBtn.setAttribute('onclick', `closeNewsModal('${modalId}')`);
    });
    
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
    function animateReposition(oldPositionsMap) {
        const isDeviceMobile = isMobile();
        if (isDeviceMobile || !oldPositionsMap || oldPositionsMap.size === 0) return; // Skip on mobile or if no map/empty map

        // Small delay to ensure DOM is ready after insertions/removals
        setTimeout(() => {
            // Iterate over the keys (DOM elements) in the map
            oldPositionsMap.forEach((oldRect, container) => {
                 // Ensure the container is still in the DOM before getting its new position
                 if (!document.body.contains(container)) return;

                const newRect = container.getBoundingClientRect();
                const deltaX = oldRect.left - newRect.left;
                const deltaY = oldRect.top - newRect.top;

                // Only animate if the position actually changed
                if (Math.abs(deltaX) > 1 || Math.abs(deltaY) > 1) {
                    container.style.transition = 'none'; // Disable transitions during setup
                    container.style.transform = `translate(${deltaX}px, ${deltaY}px)`;
                    void container.offsetWidth; // Force reflow

                    // Re-enable transitions and animate back to (0,0) transform
                    container.style.transition = 'transform 0.5s cubic-bezier(0.25, 0.1, 0.25, 1)';
                    container.style.transform = ''; // Animate back to original spot

                    // Clean up inline styles after the transition ends
                    container.addEventListener('transitionend', function handler() {
                        container.style.transition = '';
                        container.style.transform = ''; // Ensure transform is explicitly cleared
                        container.removeEventListener('transitionend', handler);
                    }, { once: true }); // Use 'once' to auto-remove the listener
                }
            });
        }, 50); // Adjust delay if needed (50ms seems reasonable)
    }

    // Función para manejar el borrado
    function attachDeleteListener(button) {
        button.addEventListener('click', function(e) {
            e.stopPropagation();
            const newsId = this.dataset.id;
            deleteNews(newsId);
        });
    }
    
    // Función central para eliminar noticias
    function deleteNews(newsId) {
        // Capturar las posiciones ANTES de cualquier cambio
        const oldPositions = capturePositions();
        
        // Encontrar el contenedor y el modal
        const container = document.getElementById(`news-${newsId}`);
        const modal = document.getElementById(`modal-${newsId}`);
        const currentPage = new URLSearchParams(window.location.search).get('page') || 1;
        const isDeviceMobile = isMobile();
        
        // Asegurarse de que se encontró el contenedor antes de continuar
        if (!container) {
            console.error(`No se encontró el contenedor para el ID: ${newsId}`);
            return;
        }

        // Si el modal está abierto, cerrarlo con animación
        if (modal && modal.classList.contains('show')) {
            closeNewsModal(newsId);
            // Esperar a que termine la animación del modal
            setTimeout(() => processDeletion(), 300);
        } else {
            processDeletion();
        }
        
        function processDeletion() {
            // Asegurarse de que todas las animaciones previas hayan terminado
            container.classList.remove('new-news', 'inserting');
            
            // Forzar un reflow para asegurar que el navegador procese los cambios
            void container.offsetWidth;
            
            // Aplicar animación según el dispositivo
            if (isDeviceMobile) {
                // En móviles, animar la opacidad para un efecto fade-out más rápido
                container.style.transition = 'opacity 0.15s ease, transform 0.15s ease';
                container.style.opacity = '0';
                container.style.transform = 'scale(0.95)';
            } else {
                // En escritorio, usar la animación definida en CSS
                container.classList.add('deleting');
            }
            
            // Reducir la duración de la animación para móviles
            const animationDuration = isDeviceMobile ? 150 : 500; // 150ms en móviles, 500ms en escritorio
            
            // Esperar a que termine la animación antes de realizar la solicitud al servidor
            setTimeout(() => {
                // Para móviles, eliminar inmediatamente del DOM
                if (isDeviceMobile) {
                    container.remove();
                    if (modal) modal.remove();
                }
                
                // Realizar la solicitud al servidor
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
                        // Usar el total de noticias devuelto por el servidor para actualizar los contadores
                        updateCountersFromServer(data.total_news, data.total_pages);
                        
                        // Para dispositivos de escritorio, eliminar el elemento si aún no se ha eliminado
                        if (!isDeviceMobile && document.getElementById(`news-${newsId}`)) {
                            container.remove();
                            // También eliminamos el modal asociado a la noticia eliminada
                            if (modal) {
                                modal.remove();
                            }
                        }
                        
                        // Animar las tarjetas actuales y luego añadir la nueva si existe
                        if (!isDeviceMobile) {
                            // Animar reposicionamiento con las posiciones capturadas al inicio
                            animateReposition(oldPositions);
                            
                            // Si hay un nuevo elemento para agregar, lo hacemos después
                            if (data.html) {
                                setTimeout(() => {
                                    addNewCard(data);
                                }, 300); // Agregar después de que termine la animación de reposicionamiento
                            }
                        } else if (data.html) {
                            // En móvil simplemente añadimos la nueva tarjeta
                            addNewCard(data);
                        }
                    }
                })
                .catch(error => {
                    console.error('Error al eliminar la noticia:', error);
                    // En caso de error, restaurar la opacidad
                    if (container && document.body.contains(container)) {
                        container.style.opacity = '1';
                        container.style.transform = 'scale(1)';
                    }
                });
            }, animationDuration);
        }
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

        const isDeviceMobile = isMobile();
        const MAX_NEWS = 25;
        const newsToAddCount = pendingNews.length;

        // 1. Capture initial positions (for FLIP) - Only if not mobile
        const oldPositions = isDeviceMobile ? null : capturePositions();

        // 2. Determine cards to remove
        const currentCards = Array.from(newsGrid.children);
        const currentCount = currentCards.length;
        const cardsToRemoveCount = Math.max(0, currentCount + newsToAddCount - MAX_NEWS);
        const cardsToRemoveElements = currentCards.slice(currentCount - cardsToRemoveCount); // Get the last 'n' cards

        // 3. Animate removal of old cards and collect promises
        const removalPromises = cardsToRemoveElements.map(cardElement => {
            return new Promise(resolve => {
                const cardId = cardElement.id.replace('news-', '');
                const modal = document.getElementById(`modal-${cardId}`);

                // Add removal animation class/style
                cardElement.style.transition = 'opacity 0.3s ease, transform 0.3s ease, height 0.3s ease, margin 0.3s ease, padding 0.3s ease'; // Smooth transition out
                 cardElement.style.opacity = '0';
                 cardElement.style.transform = 'scale(0.8)';
                 cardElement.style.height = '0'; // Collapse height
                 cardElement.style.margin = '0';
                 cardElement.style.padding = '0';
                 cardElement.style.border = 'none'; // Hide border during animation


                const animationDuration = 300; // Consistent duration

                setTimeout(() => {
                    cardElement.remove();
                    if (modal) modal.remove();
                    resolve();
                }, animationDuration);
            });
        });

        // Wait for all removal animations to finish before proceeding
        Promise.all(removalPromises).then(() => {
            // 4. Prepare and insert new cards at the beginning
            const newCardElements = [];
            const fragment = document.createDocumentFragment();

            // Sort pendingNews newest first
            pendingNews.sort((a, b) => new Date(b.published) - new Date(a.published));

            pendingNews.forEach((newsItem) => {
                // Create card element
                const temp = document.createElement('div');
                temp.innerHTML = newsItem.card;
                const newsContainer = temp.firstElementChild;

                // Prepare entry animation (set initial state)
                 newsContainer.style.opacity = '0';
                 newsContainer.style.transform = 'scale(0.9)';
                 newsContainer.style.transition = 'opacity 0.4s ease, transform 0.4s cubic-bezier(0.25, 0.1, 0.25, 1)';


                // Add modal
                const modalTemp = document.createElement('div');
                modalTemp.innerHTML = newsItem.modal;
                const modal = modalTemp.firstElementChild;
                newsModalsContainer.appendChild(modal);

                // Configure buttons, listeners etc. for the new card and its modal
                configureNewCard(newsContainer, modal, newsItem.id);

                fragment.appendChild(newsContainer); // Add to fragment
                newCardElements.push(newsContainer); // Keep track of new elements
            });

            // Add the fragment with new cards to the grid's beginning
            newsGrid.insertBefore(fragment, newsGrid.firstChild);

            // Trigger entry animation for new cards
            requestAnimationFrame(() => {
                 newCardElements.forEach(card => {
                     card.style.opacity = '1';
                     card.style.transform = 'scale(1)';
                     // Clean up inline styles after animation
                     card.addEventListener('transitionend', function handler() {
                         card.style.transition = '';
                         card.style.transform = '';
                         card.style.opacity = '';
                         card.removeEventListener('transitionend', handler);
                     }, { once: true });
                 });
            });

            // 5. Animate repositioning of existing cards (FLIP) - Only if not mobile
            if (!isDeviceMobile && oldPositions) {
                 // We need to update oldPositions map to exclude the cards that were removed
                 const remainingOldPositions = new Map();
                 oldPositions.forEach((rect, card) => {
                    // Check if the card still exists in the DOM and was not marked for removal
                     if (document.body.contains(card) && !cardsToRemoveElements.includes(card)) {
                         remainingOldPositions.set(card, rect);
                     }
                 });
                 // Pass the filtered map to animateReposition
                 animateReposition(remainingOldPositions);
             }

            // 6. Update counters and clean up
            fetch('/noticias/get-news-count/')
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        updateCountersFromServer(data.total_news, data.total_pages);
                    }
                })
                .catch(error => console.error('Error al obtener el conteo actualizado:', error));

            pendingNews = [];
            // setupImageHoverHandlers(); // No longer needed here as configureNewCard handles it per card
        });
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

    // Función para añadir la nueva tarjeta
    function addNewCard(data) {
        if (!data.html) return;
        
        const temp = document.createElement('div');
        temp.innerHTML = data.html;
        const newCard = temp.firstElementChild;
        
        // Antes de añadir la nueva tarjeta, capturar posiciones actuales
        const positionsBeforeInsert = capturePositions();
        
        // Preparar la nueva tarjeta
        if (isMobile()) {
            // En móvil, iniciar con opacidad 0 para hacer fade-in
            newCard.style.opacity = '0';
            newCard.style.transition = 'opacity 0.2s ease';
            
            // Forzar reflow
            void newCard.offsetWidth;
        } else {
            // En escritorio, usar la animación de CSS
            newCard.classList.add('inserting');
        }
        
        const newDeleteBtn = newCard.querySelector('.delete-btn');
        if (newDeleteBtn) {
            attachDeleteListener(newDeleteBtn);
        }
        
        // Asegurar que el evento onclick esté configurado correctamente
        const card = newCard.querySelector('.news-card');
        const cardFront = newCard.querySelector('.card-front');
        const cardBack = newCard.querySelector('.card-back');
        const linksContainer = cardBack?.querySelector('.news-links');
        const newCardId = newCard.id.replace('news-', '');

        // Limpiar onclick de la tarjeta principal
        if(card) card.removeAttribute('onclick');

        // Configuración común para móvil y escritorio
        if (cardFront && newCard.querySelector('.delete-btn')) {
             // Eliminar cualquier botón anterior si existe
            const oldBtn = cardFront.querySelector('.mobile-delete-btn');
            if (oldBtn) oldBtn.remove();

            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'mobile-delete-btn';
            deleteBtn.setAttribute('type', 'button');
            deleteBtn.setAttribute('data-id', newCardId);
            deleteBtn.onclick = function(e) {
                e.stopPropagation();
                deleteNews(newCardId);
                return false;
            };
            cardFront.appendChild(deleteBtn);
        }

        if (linksContainer) {
             // Eliminar cualquier botón anterior si existe
            const oldModalOpener = linksContainer.querySelector('.news-link.modal-opener');
            if (oldModalOpener) oldModalOpener.remove();

            const modalLink = document.createElement('a');
            modalLink.href = 'javascript:void(0)';
            modalLink.className = 'news-link modal-opener';
            modalLink.textContent = 'Más';
            modalLink.addEventListener('click', function(e) {
                e.stopPropagation();
                openNewsModal(newCardId);
            });
            linksContainer.insertBefore(modalLink, linksContainer.firstChild);
        }
        
        // Añadir la nueva tarjeta
        newsGrid.appendChild(newCard);
        
        // Para móvil, aplicar el fade-in después de añadir al DOM
        if (isMobile()) {
            // Aplicar fade-in inmediatamente para evitar retrasos
            requestAnimationFrame(() => {
                newCard.style.opacity = '1';
            });
        } else {
            // Animamos el reposicionamiento de todas las tarjetas
            // después de añadir la nueva
            setTimeout(() => {
                // Capturar las nuevas posiciones después de insertar
                const newPositions = capturePositions();
                
                // Animar todas las tarjetas excepto la recién insertada
                document.querySelectorAll('.news-card-container:not(.inserting)').forEach(container => {
                    const oldRect = positionsBeforeInsert.get(container);
                    if (!oldRect) return;
                    
                    const newRect = newPositions.get(container);
                    if (!newRect) return;
                    
                    const deltaX = oldRect.left - newRect.left;
                    const deltaY = oldRect.top - newRect.top;
                    
                    // Solo animar si hay un cambio significativo
                    if (Math.abs(deltaX) > 1 || Math.abs(deltaY) > 1) {
                        container.style.transition = 'none';
                        container.style.transform = `translate(${deltaX}px, ${deltaY}px)`;
                        
                        // Forzar reflow
                        void container.offsetWidth;
                        
                        // Usar la misma curva de aceleración que en CSS
                        container.style.transition = 'transform 0.5s cubic-bezier(0.25, 0.1, 0.25, 1)';
                        container.style.transform = '';
                        
                        container.addEventListener('transitionend', function handler() {
                            container.style.transition = '';
                            container.removeEventListener('transitionend', handler);
                        });
                    }
                });
            }, 50);
        }
        
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
                const newCardId = newCard.id.replace('news-', '');
                closeBtn.setAttribute('onclick', `closeNewsModal('${newCardId}')`);
            }
            
            // Configurar botón de eliminación en el modal
            const modalDeleteBtn = newModal.querySelector('.btn-danger');
            if (modalDeleteBtn) {
                const newCardId = newCard.id.replace('news-', '');
                modalDeleteBtn.setAttribute('data-id', newCardId);
                attachDeleteListener(modalDeleteBtn);
            }
        }
        
        // Aplicar los manejadores de hover para imágenes a la nueva tarjeta
        setupImageHoverHandlers();
        
        // Eliminar la clase de inserción después de completar la animación
        setTimeout(() => {
            newCard.classList.remove('inserting');
        }, 700);
    }

    // Helper function to configure a new card (refactored from existing code)
    function configureNewCard(newsContainer, modal, newsItemId) {
        const card = newsContainer.querySelector('.news-card');
        const cardFront = newsContainer.querySelector('.card-front');
        const cardBack = newsContainer.querySelector('.card-back');
        const linksContainer = cardBack?.querySelector('.news-links');
        const newsId = newsItemId; // Already have the ID

        // Limpiar onclick de la tarjeta principal por si acaso
        if (card) card.removeAttribute('onclick');

        // Botón de eliminación móvil/escritorio en el frente
        // Revisa si el botón .delete-btn existe en el template original para decidir si añadir el botón flotante
        const canDelete = newsContainer.querySelector('.delete-btn'); // Busca el botón original del backend
        if (cardFront && canDelete) {
            const oldBtn = cardFront.querySelector('.mobile-delete-btn');
            if (oldBtn) oldBtn.remove();

            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'mobile-delete-btn';
            deleteBtn.setAttribute('type', 'button');
            deleteBtn.setAttribute('data-id', newsId);
            deleteBtn.onclick = function(e) {
                e.stopPropagation();
                // Add pulse animation on click for feedback
                this.classList.add('pulse');
                setTimeout(() => this.classList.remove('pulse'), 300);
                deleteNews(newsId);
                return false;
            };
            cardFront.appendChild(deleteBtn);
        }

        // Botón "Ver más" en el reverso
        if (linksContainer) {
            const oldModalOpener = linksContainer.querySelector('.news-link.modal-opener');
            if (oldModalOpener) oldModalOpener.remove();

            const modalLink = document.createElement('a');
            modalLink.href = 'javascript:void(0)';
            modalLink.className = 'news-link modal-opener';
            modalLink.textContent = 'Más';
            modalLink.addEventListener('click', function(e) {
                e.stopPropagation();
                openNewsModal(newsId);
            });
            linksContainer.insertBefore(modalLink, linksContainer.firstChild);
        }

        // Listener para botón de eliminación en el modal
        const modalDeleteBtn = modal?.querySelector('.btn-danger');
        if (modalDeleteBtn) {
            modalDeleteBtn.setAttribute('data-id', newsId);
            // Ensure listener is attached (attachDeleteListener might need adjustment or just call deleteNews directly)
            if (!modalDeleteBtn.onclick) { // Avoid attaching multiple listeners
                 modalDeleteBtn.onclick = function(e) {
                     e.stopPropagation();
                     deleteNews(this.dataset.id);
                 };
             }
        }

         // Configurar botón de cierre del modal
         const closeBtn = modal?.querySelector('.close');
         if (closeBtn && !closeBtn.onclick) {
             closeBtn.onclick = () => closeNewsModal(newsId);
         }

         // Volver a aplicar manejadores de hover de imagen específicamente para esta tarjeta
         const image = newsContainer.querySelector('.news-image');
         if (image) {
            image.addEventListener('mouseenter', function() {
                const cardElement = this.closest('.news-card');
                if (cardElement) cardElement.classList.add('image-hover');
            });
            image.addEventListener('mouseleave', function() {
                const cardElement = this.closest('.news-card');
                if (cardElement) cardElement.classList.remove('image-hover');
            });
         }
         const mobileDeleteButton = newsContainer.querySelector('.mobile-delete-btn');
         if (mobileDeleteButton) {
            mobileDeleteButton.addEventListener('mouseenter', function(e) {
                e.stopPropagation();
                const cardElement = this.closest('.news-card');
                if (cardElement) cardElement.classList.add('delete-hover');
            });
            mobileDeleteButton.addEventListener('mouseleave', function(e) {
                e.stopPropagation();
                const cardElement = this.closest('.news-card');
                if (cardElement) cardElement.classList.remove('delete-hover');
            });
         }
    }
}); 