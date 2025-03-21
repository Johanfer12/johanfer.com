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
    
    // Actualizar el comportamiento de las tarjetas según el dispositivo
    function updateCardBehavior() {
        document.querySelectorAll('.news-card').forEach(card => {
            const newsId = card.closest('.news-card-container').id.replace('news-', '');
            const container = card.closest('.news-card-container');
            
            if (isMobile()) {
                // En móvil: quitar onclick para evitar que abra el modal
                card.removeAttribute('onclick');
                
                // Añadir botón de eliminación móvil al frente de la tarjeta si no existe ya
                const cardFront = card.querySelector('.card-front');
                if (cardFront && !cardFront.querySelector('.mobile-delete-btn') && container.querySelector('.delete-btn')) {
                    // Eliminar cualquier botón anterior si existe
                    const oldBtn = cardFront.querySelector('.mobile-delete-btn');
                    if (oldBtn) {
                        oldBtn.remove();
                    }
                    
                    // Usar un botón real en lugar de un div
                    const deleteBtn = document.createElement('button');
                    deleteBtn.className = 'mobile-delete-btn';
                    deleteBtn.setAttribute('type', 'button');
                    deleteBtn.setAttribute('data-id', newsId);
                    
                    // Asignar directamente la función
                    deleteBtn.onclick = function() {
                        deleteNews(newsId);
                        return false;
                    };
                    
                    cardFront.appendChild(deleteBtn);
                }
                
                // Añadir botón "Ver más" al reverso de la tarjeta solo si no existe ya
                const cardBack = card.querySelector('.card-back');
                if (cardBack && !cardBack.querySelector('.news-link.modal-opener')) {
                    const linksContainer = cardBack.querySelector('.news-links');
                    if (linksContainer) {
                        const modalLink = document.createElement('a');
                        modalLink.href = 'javascript:void(0)';
                        modalLink.className = 'news-link modal-opener';
                        modalLink.textContent = 'Más';
                        modalLink.addEventListener('click', function(e) {
                            e.stopPropagation();
                            openNewsModal(newsId);
                        });
                        linksContainer.prepend(modalLink);
                    }
                }
            } else {
                // En escritorio: configurar onclick para abrir el modal
                card.setAttribute('onclick', `openNewsModal('${newsId}')`);
                
                // Eliminar botón "Ver más" si existe
                const modalOpener = card.querySelector('.news-link.modal-opener');
                if (modalOpener) {
                    modalOpener.remove();
                }
                
                // Eliminar botón de eliminación móvil si existe
                const mobileDeleteBtn = card.querySelector('.mobile-delete-btn');
                if (mobileDeleteBtn) {
                    mobileDeleteBtn.remove();
                }
            }
        });
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
            deleteNews(newsId);
        });
    }
    
    // Función central para eliminar noticias
    function deleteNews(newsId) {
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
            const animationDuration = isDeviceMobile ? 150 : 500; // 150ms en móviles (mitad del tiempo anterior), 500ms en escritorio
            
            // Primero eliminamos el elemento del DOM para mejorar la experiencia del usuario
            // especialmente en conexiones lentas
            if (isDeviceMobile) {
                setTimeout(() => {
                    container.remove();
                    if (modal) modal.remove();
                }, animationDuration);
            }
            
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
                    
                    // Para dispositivos de escritorio, o si la tarjeta aún no se ha eliminado
                    if (!isDeviceMobile || document.getElementById(`news-${newsId}`)) {
                        setTimeout(() => {
                            if (document.getElementById(`news-${newsId}`)) {
                                container.remove();
                            }
                            // También eliminamos el modal asociado a la noticia eliminada
                            if (modal) {
                                modal.remove();
                            }
                            
                            // Solo animar reposicionamiento en escritorio
                            if (!isDeviceMobile) {
                                animateReposition(oldPositions);
                            }
                        }, animationDuration);
                    }
                    
                    if (data.html) {
                        const temp = document.createElement('div');
                        temp.innerHTML = data.html;
                        const newCard = temp.firstElementChild;
                        
                        // Preparar la nueva tarjeta
                        if (isDeviceMobile) {
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
                        
                        // Asegurar que el evento onclick esté configurado
                        const card = newCard.querySelector('.news-card');
                        if (card) {
                            const newCardId = newCard.id.replace('news-', '');
                            if (!isDeviceMobile) {
                                card.setAttribute('onclick', `openNewsModal('${newCardId}')`);
                            } else {
                                // Para móvil, añadir el botón de eliminación móvil
                                const cardFront = card.querySelector('.card-front');
                                if (cardFront && newCard.querySelector('.delete-btn')) {
                                    // Eliminar cualquier botón anterior si existe
                                    const oldBtn = cardFront.querySelector('.mobile-delete-btn');
                                    if (oldBtn) {
                                        oldBtn.remove();
                                    }
                                    
                                    // Usar un botón real en lugar de un div
                                    const mobileDeleteBtn = document.createElement('button');
                                    mobileDeleteBtn.className = 'mobile-delete-btn';
                                    mobileDeleteBtn.setAttribute('type', 'button');
                                    mobileDeleteBtn.setAttribute('data-id', newCardId);
                                    
                                    // Asignar directamente la función
                                    mobileDeleteBtn.onclick = function(e) {
                                        e.stopPropagation();
                                        deleteNews(newCardId);
                                        return false;
                                    };
                                    
                                    cardFront.appendChild(mobileDeleteBtn);
                                }
                                
                                // Para móvil, añadir el botón "Ver más" en el reverso
                                const cardBack = card.querySelector('.card-back');
                                if (cardBack) {
                                    const linksContainer = cardBack.querySelector('.news-links');
                                    if (linksContainer) {
                                        const modalLink = document.createElement('a');
                                        modalLink.href = 'javascript:void(0)';
                                        modalLink.className = 'news-link modal-opener';
                                        modalLink.textContent = 'Más';
                                        modalLink.addEventListener('click', function(e) {
                                            e.stopPropagation();
                                            openNewsModal(newCardId);
                                        });
                                        linksContainer.prepend(modalLink);
                                    }
                                }
                            }
                        }
                        
                        // Añadir la nueva tarjeta
                        newsGrid.appendChild(newCard);
                        
                        // Para móvil, aplicar el fade-in después de añadir al DOM
                        if (isDeviceMobile) {
                            // Aplicar fade-in inmediatamente para evitar retrasos
                            requestAnimationFrame(() => {
                                newCard.style.opacity = '1';
                            });
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
                        
                        // Solo animar reposicionamiento en escritorio
                        if (!isDeviceMobile) {
                            animateReposition(oldPositions);
                        }
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
        
        // Determinar si estamos en un dispositivo móvil
        const isDeviceMobile = isMobile();
        
        // Guardar posiciones actuales para animación (solo en escritorio)
        const oldPositions = isDeviceMobile ? null : capturePositions();
        
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
                    
                    // Eliminar con fade-out en móvil
                    if (isDeviceMobile) {
                        lastChild.style.transition = 'opacity 0.15s ease';
                        lastChild.style.opacity = '0';
                    }
                    
                    // Eliminar también el modal correspondiente
                    const lastModal = document.getElementById(`modal-${lastChildId}`);
                    if (lastModal) {
                        lastModal.remove();
                    }
                    
                    // En móvil, esperar a que termine la animación
                    if (isDeviceMobile) {
                        setTimeout(() => {
                            lastChild.remove();
                        }, 150);
                    } else {
                        lastChild.remove();
                    }
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
            
            // Preparar animación según el dispositivo
            if (isDeviceMobile) {
                // En móvil, preparar para fade-in
                newsContainer.style.opacity = '0';
                newsContainer.style.transition = 'opacity 0.2s ease';
                void newsContainer.offsetWidth;
            } else {
                // En escritorio, usar la animación CSS existente
                void newsContainer.offsetWidth;
                newsContainer.classList.add('new-news');
            }
            
            // Añadir el modal al contenedor de modales
            const modalTemp = document.createElement('div');
            modalTemp.innerHTML = newsItem.modal;
            const modal = modalTemp.firstElementChild;
            newsModalsContainer.appendChild(modal);
            
            // Añadir evento onclick al contenedor de la tarjeta para abrir el modal (solo en escritorio)
            const card = newsContainer.querySelector('.news-card');
            if (card) {
                if (!isDeviceMobile) {
                    card.setAttribute('onclick', `openNewsModal('${newsItem.id}')`);
                } else {
                    // Para móvil, añadir el botón de eliminación en el frente
                    const cardFront = card.querySelector('.card-front');
                    if (cardFront && newsContainer.querySelector('.delete-btn')) {
                        // Eliminar cualquier botón anterior si existe
                        const oldBtn = cardFront.querySelector('.mobile-delete-btn');
                        if (oldBtn) {
                            oldBtn.remove();
                        }
                        
                        // Usar un botón real en lugar de un div
                        const mobileDeleteBtn = document.createElement('button');
                        mobileDeleteBtn.className = 'mobile-delete-btn';
                        mobileDeleteBtn.setAttribute('type', 'button');
                        mobileDeleteBtn.setAttribute('data-id', newsItem.id);
                        
                        // Asignar directamente la función
                        mobileDeleteBtn.onclick = function(e) {
                            e.stopPropagation();
                            deleteNews(newsItem.id);
                            return false;
                        };
                        
                        cardFront.appendChild(mobileDeleteBtn);
                    }
                    
                    // Para móvil, añadir el botón "Ver más" en el reverso
                    const cardBack = card.querySelector('.card-back');
                    if (cardBack) {
                        const linksContainer = cardBack.querySelector('.news-links');
                        if (linksContainer) {
                            const modalLink = document.createElement('a');
                            modalLink.href = 'javascript:void(0)';
                            modalLink.className = 'news-link modal-opener';
                            modalLink.textContent = 'Más';
                            modalLink.addEventListener('click', function(e) {
                                e.stopPropagation();
                                openNewsModal(newsItem.id);
                            });
                            linksContainer.prepend(modalLink);
                        }
                    }
                }
            }
            
            // Configurar el botón de cierre del modal
            const closeBtn = modal.querySelector('.close');
            if (closeBtn) {
                closeBtn.setAttribute('onclick', `closeNewsModal('${newsItem.id}')`);
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
            
            // Aplicar fade-in para todas las tarjetas en móvil
            if (isDeviceMobile) {
                requestAnimationFrame(() => {
                    newCards.forEach(card => {
                        card.style.opacity = '1';
                    });
                });
            }
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
            
            // Para móviles, hacer la transición más suave
            if (isDeviceMobile) {
                // Eliminar tarjetas existentes con opacidad 0.5
                existingCards.forEach(card => {
                    card.style.transition = 'opacity 0.1s ease';
                    card.style.opacity = '0.5';
                });
                
                // Limpiar el grid con un pequeño retraso
                setTimeout(() => {
                    // Limpiar el grid actual
                    while (newsGrid.firstChild) {
                        newsGrid.removeChild(newsGrid.firstChild);
                    }
                    
                    // Añadir las noticias en el nuevo orden
                    newGridChildren.forEach(card => {
                        newsGrid.appendChild(card);
                    });
                    
                    // Restaurar opacidad para todas las tarjetas
                    requestAnimationFrame(() => {
                        Array.from(newsGrid.children).forEach(card => {
                            card.style.transition = 'opacity 0.2s ease';
                            card.style.opacity = '1';
                        });
                    });
                }, 100);
            } else {
                // En escritorio, simplemente reemplazar
                // Limpiar el grid actual
                while (newsGrid.firstChild) {
                    newsGrid.removeChild(newsGrid.firstChild);
                }
                
                // Añadir las noticias en el nuevo orden
                newGridChildren.forEach(card => {
                    newsGrid.appendChild(card);
                });
            }
        }
        
        // Animar reposicionamiento solo en escritorio
        if (!isDeviceMobile && oldPositions) {
            animateReposition(oldPositions);
        }
        
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