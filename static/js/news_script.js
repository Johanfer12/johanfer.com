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
    // oldPositionsMap: Mapa con las posiciones antes del cambio
    // excludedIds: Array de IDs de elementos que fueron eliminados y no deben ser animados
    function animateReposition(oldPositionsMap, excludedIds = []) {
        const isDeviceMobile = isMobile();
        // No animar en móvil o si no hay posiciones válidas
        if (isDeviceMobile || !oldPositionsMap || oldPositionsMap.size === 0) return;

        // Usamos requestAnimationFrame para asegurar que el navegador esté listo
        requestAnimationFrame(() => {
            const elementsToAnimate = new Map();

            // 1. Calcular deltas para elementos que aún existen y no están excluidos
            oldPositionsMap.forEach((oldRect, container) => {
                // Comprobar si el contenedor sigue en el DOM y no está en la lista de excluidos
                const containerId = container.id;
                if (!document.body.contains(container) || excludedIds.includes(containerId)) {
                    return; // Saltar si no existe o fue explícitamente excluido (eliminado)
                }

                const newRect = container.getBoundingClientRect();
                const deltaX = oldRect.left - newRect.left;
                const deltaY = oldRect.top - newRect.top;

                // Solo preparar animación si la posición cambió significativamente
                if (Math.abs(deltaX) > 0.5 || Math.abs(deltaY) > 0.5) {
                    elementsToAnimate.set(container, { deltaX, deltaY });
                    // Aplicar transformación inversa INMEDIATAMENTE sin transición
                    container.style.transition = 'none';
                    container.style.transform = `translate(${deltaX}px, ${deltaY}px)`;
                } else {
                    // Si no hay cambio, asegurarse de que no tenga transformaciones pendientes
                    container.style.transform = '';
                    container.style.transition = '';
                }
            });

            // Si no hay nada que animar, salir
            if (elementsToAnimate.size === 0) return;

            // 2. Forzar reflow para que el navegador registre las transformaciones inversas
            void newsGrid.offsetWidth; // Forzar reflow en un elemento padre común

            // 3. Aplicar transición y animar de vuelta a la posición final (transform = '')
            elementsToAnimate.forEach(({ deltaX, deltaY }, container) => {
                 // Re-enable transitions and animate back to (0,0) transform
                 container.style.transition = 'transform 0.5s cubic-bezier(0.25, 0.1, 0.25, 1)';
                 container.style.transform = ''; // Animate back to original spot

                 // Clean up inline styles after the transition ends
                 container.addEventListener('transitionend', function handler() {
                     container.style.transition = '';
                     // No quitar transform aquí, ya está en ''
                     container.removeEventListener('transitionend', handler);
                 }, { once: true });
            });
        });
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
        const container = document.getElementById(`news-${newsId}`);
        const modal = document.getElementById(`modal-${newsId}`);
        const currentPage = new URLSearchParams(window.location.search).get('page') || 1;
        const isDeviceMobile = isMobile();

        if (!container) {
            console.error(`No se encontró el contenedor para el ID: ${newsId}`);
            return;
        }

        // 1. Capturar posiciones ANTES de cualquier cambio
        const oldPositions = isDeviceMobile ? null : capturePositions();
        const containerId = container.id; // Guardar ID para exclusión en FLIP

        // Cerrar modal si está abierto
        if (modal && modal.classList.contains('show')) {
            closeNewsModal(newsId);
        }

        // 2. Aplicar animación de salida
        // Usar una promesa para saber cuándo termina la animación
        const animationPromise = new Promise(resolve => {
            const animationDuration = isDeviceMobile ? 150 : 300; // Duración más corta en móvil

            if (isDeviceMobile) {
                container.style.transition = `opacity ${animationDuration}ms ease, transform ${animationDuration}ms ease`;
                container.style.opacity = '0';
                container.style.transform = 'scale(0.95)';
            } else {
                // Usar clase para animación de escritorio
                container.classList.add('deleting'); // Asegúrate que 'deleting' tenga una animación de ~300ms
            }

            // Esperar que termine la animación
            setTimeout(resolve, animationDuration);
        });

        // 3. Después de la animación de salida -> Realizar fetch y actualizar DOM/FLIP
        animationPromise.then(() => {
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
                    // 4. Eliminar elemento del DOM (AHORA, después de animar salida y ANTES de FLIP)
                    container.remove();
                    if (modal) modal.remove();

                    // Actualizar contadores con datos del servidor
                    updateCountersFromServer(data.total_news, data.total_pages);

                    let newCardElement = null;
                    let newModalElement = null;

                    // 5. Si hay un nuevo elemento para agregar, prepararlo pero NO añadirlo aún
                    if (data.html && data.modal) {
                        const tempCard = document.createElement('div');
                        tempCard.innerHTML = data.html;
                        newCardElement = tempCard.firstElementChild;

                        const tempModal = document.createElement('div');
                        tempModal.innerHTML = data.modal;
                        newModalElement = tempModal.firstElementChild;

                         // Configurar la nueva tarjeta y modal (botones, listeners)
                        configureNewCard(newCardElement, newModalElement, newCardElement.id.replace('news-', ''));

                         // Preparar para animación de entrada
                        newCardElement.style.opacity = '0';
                        newCardElement.style.transform = 'scale(0.9)';
                        newCardElement.style.transition = 'none'; // Sin transición inicial
                    }

                    // 6. Aplicar FLIP a las tarjetas restantes
                    // Pasar el ID de la tarjeta eliminada para excluirla explícitamente
                    if (oldPositions) {
                        animateReposition(oldPositions, [containerId]);
                    }

                    // 7. Añadir la nueva tarjeta (si existe) y animar su entrada DESPUÉS de iniciar FLIP
                    if (newCardElement) {
                        // Añadir al final del grid (o donde corresponda según tu lógica, aquí se asume al final)
                        newsGrid.appendChild(newCardElement);
                        if (newModalElement) newsModalsContainer.appendChild(newModalElement);

                        // Forzar reflow antes de animar entrada
                        void newCardElement.offsetWidth;

                        // Iniciar animación de entrada
                        requestAnimationFrame(() => {
                            newCardElement.style.transition = 'opacity 0.4s ease, transform 0.4s cubic-bezier(0.25, 0.1, 0.25, 1)';
                            newCardElement.style.opacity = '1';
                            newCardElement.style.transform = 'scale(1)';

                            // Limpiar estilos inline después de la animación
                            newCardElement.addEventListener('transitionend', function handler() {
                                newCardElement.style.transition = '';
                                newCardElement.style.opacity = '';
                                newCardElement.style.transform = '';
                                newCardElement.removeEventListener('transitionend', handler);
                            }, { once: true });
                        });
                    }

                } else {
                     // Si falla el fetch, revertir animación de salida (opcional)
                     if (document.body.contains(container)) {
                         container.classList.remove('deleting');
                         container.style.opacity = '1';
                         container.style.transform = 'scale(1)';
                         container.style.transition = ''; // Limpiar transición inline si se usó
                     }
                     console.error('Error en la respuesta del servidor al eliminar:', data.message);
                     // Podrías mostrar un mensaje al usuario aquí
                }
            })
            .catch(error => {
                console.error('Error en fetch al eliminar la noticia:', error);
                 // Revertir animación si falla el fetch
                 if (document.body.contains(container)) {
                     container.classList.remove('deleting');
                     container.style.opacity = '1';
                     container.style.transform = 'scale(1)';
                     container.style.transition = '';
                 }
                // Mostrar mensaje de error al usuario
            });
        });
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
        // showImmediately no se usa actualmente, pero se mantiene por si acaso
        fetch(`/noticias/check-new-news/?last_checked=${encodeURIComponent(lastChecked)}`)
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    lastChecked = data.current_time;
                    if (data.news_cards && data.news_cards.length > 0) {
                        console.log(`Se encontraron ${data.news_cards.length} noticias nuevas`);
                        pendingNews = data.news_cards; // Almacenar para loadNewNews

                        // Actualizar contadores ANTES de mostrar notificación/cargar
                        updateCountersFromServer(data.total_news, data.total_pages);

                        showNotification(pendingNews.length); // Mostrar notificación informativa

                        // Cargar las noticias automáticamente (esta función manejará las animaciones)
                        loadNewNews();
                    }
                }
            })
            .catch(error => {
                console.error('Error al comprobar nuevas noticias:', error);
            });
    }
    
    // Cargar nuevas noticias (llamado por checkForNewNews o manualmente)
    function loadNewNews() {
        if (pendingNews.length === 0) return;

        const isDeviceMobile = isMobile();
        const MAX_NEWS = 25; // Límite de tarjetas a mostrar
        const newsToAdd = pendingNews; // Usar las noticias pendientes
        pendingNews = []; // Limpiar la lista de pendientes

        // 1. Capturar posiciones ANTES de cualquier cambio (solo escritorio)
        const oldPositions = isDeviceMobile ? null : capturePositions();

        // 2. Determinar tarjetas a eliminar
        const currentCards = Array.from(newsGrid.children);
        const currentCount = currentCards.length;
        const newsToAddCount = newsToAdd.length;
        const cardsToRemoveCount = Math.max(0, currentCount + newsToAddCount - MAX_NEWS);
        const cardsToRemoveElements = currentCards.slice(-cardsToRemoveCount); // Últimas 'n' tarjetas
        const cardsToRemoveIds = cardsToRemoveElements.map(el => el.id); // IDs para exclusión en FLIP

        // 3. Animar salida de tarjetas antiguas y obtener promesas
        const removalPromises = cardsToRemoveElements.map(cardElement => {
            return new Promise(resolve => {
                const cardId = cardElement.id.replace('news-', '');
                const modal = document.getElementById(`modal-${cardId}`);
                const animationDuration = 300; // Duración de la animación de salida

                // Aplicar animación de salida (similar a deleteNews pero sin clase 'deleting')
                cardElement.style.transition = `opacity ${animationDuration}ms ease, transform ${animationDuration}ms ease, height ${animationDuration}ms ease, margin ${animationDuration}ms ease, padding ${animationDuration}ms ease, border ${animationDuration}ms ease`;
                cardElement.style.opacity = '0';
                cardElement.style.transform = 'scale(0.8)';
                cardElement.style.height = '0';
                cardElement.style.margin = '0';
                cardElement.style.padding = '0';
                cardElement.style.borderWidth = '0'; // Ocultar borde

                setTimeout(() => {
                    // Eliminar del DOM DESPUÉS de la animación
                    cardElement.remove();
                    if (modal) modal.remove();
                    resolve(); // Resolver la promesa
                }, animationDuration);
            });
        });

        // 4. Esperar a que todas las animaciones de eliminación terminen
        Promise.all(removalPromises).then(() => {
            // 5. Preparar nuevas tarjetas (sin añadirlas al DOM aún)
            const newElementsData = []; // { container: Element, modal: Element, id: string }
            const fragment = document.createDocumentFragment(); // Para inserción eficiente

             // Ordenar noticias nuevas por fecha (más reciente primero) si es necesario
             newsToAdd.sort((a, b) => new Date(b.published) - new Date(a.published));


            newsToAdd.forEach((newsItem) => {
                // Crear elementos de tarjeta y modal
                const tempCard = document.createElement('div');
                tempCard.innerHTML = newsItem.card;
                const newsContainer = tempCard.firstElementChild;
                const newsId = newsContainer.id.replace('news-', ''); // Obtener ID real

                const tempModal = document.createElement('div');
                tempModal.innerHTML = newsItem.modal;
                const modalElement = tempModal.firstElementChild;

                // Configurar tarjeta y modal (botones, listeners, etc.)
                configureNewCard(newsContainer, modalElement, newsId);

                // Preparar para animación de entrada (oculto inicialmente)
                newsContainer.style.opacity = '0';
                newsContainer.style.transform = 'scale(0.9)';
                 newsContainer.style.transition = 'none'; // Asegurar que no haya transición inicial

                // Añadir al fragmento y guardar referencia
                fragment.appendChild(newsContainer);
                newElementsData.push({ container: newsContainer, modal: modalElement, id: newsId });
            });

            // 6. Aplicar FLIP a las tarjetas existentes (las que no se eliminaron)
            // Pasar los IDs de las tarjetas eliminadas para excluirlas
            if (oldPositions) {
                animateReposition(oldPositions, cardsToRemoveIds);
            }

            // 7. Añadir las nuevas tarjetas al DOM (al principio del grid) y sus modales
            // Se hace DESPUÉS de iniciar FLIP para que no interfieran en el cálculo de posiciones
            newsGrid.insertBefore(fragment, newsGrid.firstChild);
            newElementsData.forEach(item => {
                if (item.modal) newsModalsContainer.appendChild(item.modal);
            });


            // 8. Animar la entrada de las nuevas tarjetas
            // Usar requestAnimationFrame para asegurar que se aplica después de la inserción y FLIP
            requestAnimationFrame(() => {
                newElementsData.forEach(({ container }) => {
                    // Forzar reflow individual antes de la animación (más seguro)
                    void container.offsetWidth;

                    container.style.transition = 'opacity 0.4s ease, transform 0.4s cubic-bezier(0.25, 0.1, 0.25, 1)';
                    container.style.opacity = '1';
                    container.style.transform = 'scale(1)';

                    // Limpiar estilos inline después de la animación
                    container.addEventListener('transitionend', function handler() {
                        container.style.transition = '';
                        container.style.opacity = '';
                        container.style.transform = '';
                        container.removeEventListener('transitionend', handler);
                    }, { once: true });
                });
            });

            // 9. Actualizar contadores (ya se hizo en checkForNewNews, pero podemos verificar de nuevo si es necesario)
            // fetch('/noticias/get-news-count/')
            //     .then(response => response.json())
            //     .then(data => {
            //         if (data.status === 'success') {
            //             updateCountersFromServer(data.total_news, data.total_pages);
            //         }
            //     })
            //     .catch(error => console.error('Error al obtener el conteo actualizado post-load:', error));

        }); // Fin de Promise.all(removalPromises).then()
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

    // Función para añadir la nueva tarjeta (usada por deleteNews cuando reemplaza)
    // Esta función ahora es manejada dentro de deleteNews y loadNewNews directamente
    // function addNewCard(data) { ... } // <- Eliminar o comentar esta función si ya no se usa externamente

    // Helper function to configure a new card (centralizada)
    function configureNewCard(newsContainer, modal, newsId) {
        if (!newsContainer) return;

        const card = newsContainer.querySelector('.news-card');
        const cardFront = newsContainer.querySelector('.card-front');
        const cardBack = newsContainer.querySelector('.card-back');
        const linksContainer = cardBack?.querySelector('.news-links');

        // Limpiar handlers previos si existieran (importante si se reconfigura)
        // (Considerar clonar y reemplazar el nodo si los listeners se vuelven complejos)

        // Limpiar onclick de la tarjeta principal por si acaso
        if (card) card.removeAttribute('onclick');

        // Botón de eliminación flotante (móvil/escritorio) en el frente
        // Revisa si el botón .delete-btn (del template original) existe para decidir si añadir el botón flotante
        const canDelete = newsContainer.querySelector('.delete-btn'); // Botón original del backend
        const existingMobileDeleteBtn = cardFront?.querySelector('.mobile-delete-btn');
        if (existingMobileDeleteBtn) existingMobileDeleteBtn.remove(); // Limpiar anterior

        if (cardFront && canDelete) {
            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'mobile-delete-btn';
            deleteBtn.setAttribute('type', 'button');
            deleteBtn.setAttribute('data-id', newsId);
             // Limpiar onclick anterior si existe
             deleteBtn.onclick = null;
            deleteBtn.onclick = function(e) {
                e.stopPropagation();
                // Add pulse animation on click for feedback
                this.classList.add('pulse');
                setTimeout(() => this.classList.remove('pulse'), 300);
                deleteNews(newsId); // Llamar a la función de eliminación principal
                return false;
            };
            cardFront.appendChild(deleteBtn);

             // Añadir listeners de hover para la clase 'delete-hover' en la tarjeta
             deleteBtn.addEventListener('mouseenter', function(e) {
                e.stopPropagation();
                const cardElement = this.closest('.news-card');
                if (cardElement) cardElement.classList.add('delete-hover');
            });
            deleteBtn.addEventListener('mouseleave', function(e) {
                e.stopPropagation();
                const cardElement = this.closest('.news-card');
                if (cardElement) cardElement.classList.remove('delete-hover');
            });
        }

        // Botón "Ver más" (abre modal) en el reverso
        if (linksContainer) {
            const existingModalOpener = linksContainer.querySelector('.news-link.modal-opener');
            if (existingModalOpener) existingModalOpener.remove(); // Limpiar anterior

            const modalLink = document.createElement('a');
            modalLink.href = 'javascript:void(0)';
            modalLink.className = 'news-link modal-opener';
            modalLink.textContent = 'Más';
             // Limpiar listener anterior
             // modalLink.removeEventListener('click', ...); // Más complejo, mejor limpiar onclick
             modalLink.onclick = null;
             modalLink.onclick = function(e) {
                 e.stopPropagation();
                 openNewsModal(newsId);
             };
            // Insertar "Más" antes que otros links (Fuente, Eliminar original)
            linksContainer.insertBefore(modalLink, linksContainer.firstChild);
        }

        // Listener para botón de eliminación DENTRO del modal
        const modalDeleteBtn = modal?.querySelector('.delete-btn'); // Buscar botón de eliminar en el modal
        if (modalDeleteBtn) {
            modalDeleteBtn.setAttribute('data-id', newsId);
             // Asegurar que solo haya un listener onclick
             modalDeleteBtn.onclick = null;
             modalDeleteBtn.onclick = function(e) {
                 e.stopPropagation();
                 // Podríamos añadir feedback aquí también si queremos
                 deleteNews(this.dataset.id);
             };
        }

        // Configurar botón de cierre del modal
        const closeBtn = modal?.querySelector('.close');
        if (closeBtn) {
            // Limpiar onclick anterior
            closeBtn.onclick = null;
            closeBtn.onclick = () => closeNewsModal(newsId);
        }

        // Configurar hover de imagen para la clase 'image-hover' en la tarjeta
        const image = newsContainer.querySelector('.news-image');
        if (image) {
             // Limpiar listeners anteriores antes de añadir nuevos
             // image.removeEventListener('mouseenter', ...); // Complejo, quizás clonar sea mejor a largo plazo
            image.onmouseenter = null;
            image.onmouseleave = null;

            image.addEventListener('mouseenter', function() {
                const cardElement = this.closest('.news-card');
                if (cardElement) cardElement.classList.add('image-hover');
            });
            image.addEventListener('mouseleave', function() {
                const cardElement = this.closest('.news-card');
                if (cardElement) cardElement.classList.remove('image-hover');
            });
        }
    }

    // Eliminar o comentar la función updateCardBehavior si ya no es necesaria
    // updateCardBehavior(); // Comentar o eliminar llamada inicial
    // window.removeEventListener('resize', updateCardBehavior); // Comentar o eliminar listener

    // Inicializar configuración para tarjetas existentes al cargar la página
    document.querySelectorAll('.news-card-container').forEach(container => {
        const newsId = container.id.replace('news-', '');
        const modal = document.getElementById(`modal-${newsId}`);
        configureNewCard(container, modal, newsId);
    });


}); 