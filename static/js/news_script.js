document.addEventListener('DOMContentLoaded', function() {
    const newsGrid = document.querySelector('.news-grid');
    const totalCounter = document.querySelector('.total');
    const newsModalsContainer = document.getElementById('news-modals-container');
    const newNewsNotification = document.getElementById('new-news-notification');
    const newNewsCountElement = document.getElementById('new-news-count');
    const headerCounter = document.querySelector('.header-counter');
    const closeNotificationBtn = document.getElementById('close-notification-btn');
    
    let notificationTimer = null;
    let notificationStartTime = 0;
    let notificationTimeLeft = 0;
    let isPageVisible = true;
    let totalPendingNewsCount = 0;
    let userInteracted = false;
    const NOTIFICATION_DURATION = 10000; // 10 segundos
    
    const isMobile = () => window.innerWidth <= 767;
    
    document.addEventListener('visibilitychange', function() {
        if (document.hidden) {
            isPageVisible = false;
            userInteracted = false;
            if (notificationTimer) {
                clearTimeout(notificationTimer);
                notificationTimer = null;
                const elapsedTime = Date.now() - notificationStartTime;
                notificationTimeLeft = Math.max(0, NOTIFICATION_DURATION - elapsedTime);
            }
        } else {
            isPageVisible = true;
            if (notificationTimeLeft > 0 && newNewsNotification.classList.contains('show')) {
                notificationStartTime = Date.now();
                notificationTimer = setTimeout(() => {
                    hideNotification();
                }, notificationTimeLeft);
            }
        }
    });
    
    document.addEventListener('click', () => { userInteracted = true; });
    document.addEventListener('scroll', () => { userInteracted = true; });
    
    let lastChecked = new Date().toISOString();
    const CHECK_INTERVAL = 180000; // 3 minutos
    let pendingNews = [];
    
    window.openNewsModal = function(id) {
        const modal = document.getElementById(`modal-${id}`);
        if (!modal) return;
        modal.style.display = 'block';
        setTimeout(() => modal.classList.add('show'), 10);
        document.body.style.overflow = 'hidden';
    }

    window.closeNewsModal = function(id) {
        const modal = document.getElementById(`modal-${id}`);
        if (!modal) return;
        modal.classList.remove('show');
        setTimeout(() => {
            modal.style.display = 'none';
            document.body.style.overflow = 'auto';
        }, 300);
    }

    window.addEventListener('click', function(event) {
        if (event.target.classList.contains('modal')) {
            const modalId = event.target.id.replace('modal-', '');
            closeNewsModal(modalId);
        }
    });
    
    function showNotification(count) {
        if (!userInteracted && newNewsNotification.classList.contains('show')) {
            totalPendingNewsCount += count;
        } else {
            totalPendingNewsCount = count;
        }

        newNewsCountElement.textContent = `${totalPendingNewsCount} nuevas noticias añadidas`;
        newNewsNotification.classList.remove('hiding');
        newNewsNotification.classList.add('show');

        if (notificationTimer) {
            clearTimeout(notificationTimer);
            notificationTimer = null;
        }

        if (isPageVisible) {
            notificationStartTime = Date.now();
            notificationTimeLeft = NOTIFICATION_DURATION;
            notificationTimer = setTimeout(hideNotification, NOTIFICATION_DURATION);
        } else {
            notificationTimeLeft = NOTIFICATION_DURATION;
        }
    }

    function hideNotification() {
        newNewsNotification.classList.add('hiding');
        setTimeout(() => {
            newNewsNotification.classList.remove('show', 'hiding');
        }, 500);

        if (notificationTimer) {
            clearTimeout(notificationTimer);
            notificationTimer = null;
        }
        notificationTimeLeft = 0;
        totalPendingNewsCount = 0;
        userInteracted = false;
    }

    closeNotificationBtn.addEventListener('click', hideNotification);

    function capturePositions() {
        const positions = new Map();
        document.querySelectorAll('.news-grid .news-card-container').forEach(container => {
            positions.set(container, container.getBoundingClientRect());
        });
        return positions;
    }

    function animateReposition(oldPositionsMap, excludedIds = []) {
        if (isMobile() || !oldPositionsMap || oldPositionsMap.size === 0) return;

        requestAnimationFrame(() => {
            const elementsToAnimate = new Map();

            oldPositionsMap.forEach((oldRect, container) => {
                const containerId = container.id;
                if (!document.body.contains(container) || excludedIds.includes(containerId)) {
                    return;
                }

                const newRect = container.getBoundingClientRect();
                const deltaX = oldRect.left - newRect.left;
                const deltaY = oldRect.top - newRect.top;

                if (Math.abs(deltaX) > 0.5 || Math.abs(deltaY) > 0.5) {
                    elementsToAnimate.set(container, { deltaX, deltaY });
                    container.style.transition = 'none';
                    container.style.transform = `translate(${deltaX}px, ${deltaY}px)`;
                } else {
                    container.style.transform = '';
                    container.style.transition = '';
                }
            });

            if (elementsToAnimate.size === 0) return;

            void newsGrid.offsetWidth;

            elementsToAnimate.forEach(({ deltaX, deltaY }, container) => {
                 container.style.transition = 'transform 0.5s cubic-bezier(0.25, 0.1, 0.25, 1)';
                 container.style.transform = '';

                 container.addEventListener('transitionend', function handler() {
                     container.style.transition = '';
                     container.removeEventListener('transitionend', handler);
                 }, { once: true });
            });
        });
    }

    function deleteNews(newsId) {
        const container = document.getElementById(`news-${newsId}`);
        const modal = document.getElementById(`modal-${newsId}`);
        const currentPage = new URLSearchParams(window.location.search).get('page') || 1;
        const isDeviceMobile = isMobile();

        if (!container) {
            console.error(`Contenedor no encontrado para ID: ${newsId}`);
            return;
        }

        if (modal && modal.classList.contains('show')) {
            closeNewsModal(newsId);
        }

        if (isDeviceMobile) {
            const fetchPromise = fetch(`/noticias/delete/${newsId}/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCookie('csrftoken'),
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: `current_page=${currentPage}`
            }).then(response => response.json());

            const animationDuration = 150;
            container.style.transition = `opacity ${animationDuration}ms ease, transform ${animationDuration}ms ease`;
            container.style.opacity = '0';
            container.style.transform = 'scale(0.95)';

            setTimeout(() => {
                if (container.parentNode) container.remove();
                if (modal && modal.parentNode) modal.remove();
            }, animationDuration);

            fetchPromise.then(data => {
                if (data.status === 'success') {
                    updateCountersFromServer(data.total_news, data.total_pages);

                    let newCardElement = null;
                    let newModalElement = null;

                    if (data.html && data.modal) {
                        const tempCard = document.createElement('div');
                        tempCard.innerHTML = data.html;
                        newCardElement = tempCard.firstElementChild;

                        const tempModal = document.createElement('div');
                        tempModal.innerHTML = data.modal;
                        newModalElement = tempModal.firstElementChild;

                        configureNewCard(newCardElement, newModalElement, newCardElement.id.replace('news-', ''));

                        newCardElement.style.opacity = '0';
                        newCardElement.style.transform = 'scale(0.9)';
                        newCardElement.style.transition = 'none';
                    }

                    if (newCardElement) {
                        const existingCard = newsGrid.querySelector(`#${newCardElement.id}`);
                        if (!existingCard) {
                            newsGrid.appendChild(newCardElement);
                            if (newModalElement) newsModalsContainer.appendChild(newModalElement);

                            void newCardElement.offsetWidth;

                            requestAnimationFrame(() => {
                                newCardElement.style.transition = 'opacity 0.4s ease, transform 0.4s cubic-bezier(0.25, 0.1, 0.25, 1)';
                                newCardElement.style.opacity = '1';
                                newCardElement.style.transform = 'scale(1)';

                                newCardElement.addEventListener('transitionend', function handler() {
                                    newCardElement.style.transition = '';
                                    newCardElement.style.opacity = '';
                                    newCardElement.style.transform = '';
                                    newCardElement.removeEventListener('transitionend', handler);
                                }, { once: true });
                            });
                        } else {
                            console.warn(`Intento de añadir tarjeta duplicada (${newCardElement.id}) [Móvil].`);
                            updatePagination(data.total_pages);
                        }
                    } else {
                         updatePagination(data.total_pages);
                    }

                } else {
                    console.error('Error servidor al eliminar [Móvil]:', data.message);
                    if (data.total_news !== undefined) {
                         updateCountersFromServer(data.total_news, data.total_pages);
                    }
                }
            })
            .catch(error => {
                console.error('Error fetch al eliminar [Móvil]:', error);
            });

        } else {
            const oldPositions = capturePositions();
            const containerId = container.id;

            const animationPromise = new Promise(resolve => {
                container.classList.add('deleting');
                setTimeout(resolve, 500);
            });

            animationPromise.then(() => {
                fetch(`/noticias/delete/${newsId}/`, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': getCookie('csrftoken'), 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: `current_page=${currentPage}`
                })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        container.remove();
                        if (modal) modal.remove();

                        updateCountersFromServer(data.total_news, data.total_pages);

                        let newCardElement = null;
                        let newModalElement = null;

                        if (data.html && data.modal) {
                            const tempCard = document.createElement('div');
                            tempCard.innerHTML = data.html;
                            newCardElement = tempCard.firstElementChild;

                            const tempModal = document.createElement('div');
                            tempModal.innerHTML = data.modal;
                            newModalElement = tempModal.firstElementChild;

                            configureNewCard(newCardElement, newModalElement, newCardElement.id.replace('news-', ''));

                            newCardElement.style.opacity = '0';
                            newCardElement.style.transform = 'scale(0.9)';
                            newCardElement.style.transition = 'none';
                        }

                        if (oldPositions) {
                            animateReposition(oldPositions, [containerId]);
                        }

                        if (newCardElement) {
                            const existingCard = newsGrid.querySelector(`#${newCardElement.id}`);
                            if (!existingCard) {
                                newsGrid.appendChild(newCardElement);
                                if (newModalElement) newsModalsContainer.appendChild(newModalElement);

                                void newCardElement.offsetWidth;

                                requestAnimationFrame(() => {
                                    newCardElement.style.transition = 'opacity 0.4s ease, transform 0.4s cubic-bezier(0.25, 0.1, 0.25, 1)';
                                    newCardElement.style.opacity = '1';
                                    newCardElement.style.transform = 'scale(1)';

                                    newCardElement.addEventListener('transitionend', function handler() {
                                        newCardElement.style.transition = '';
                                        newCardElement.style.opacity = '';
                                        newCardElement.style.transform = '';
                                        newCardElement.removeEventListener('transitionend', handler);
                                    }, { once: true });
                                });
                            } else {
                                console.warn(`Intento de añadir tarjeta duplicada (${newCardElement.id}) [Escritorio].`);
                                updatePagination(data.total_pages);
                            }
                        } else {
                            updatePagination(data.total_pages);
                        }

                    } else {
                        if (document.body.contains(container)) {
                            container.classList.remove('deleting');
                        }
                        console.error('Error servidor al eliminar [Escritorio]:', data.message);
                        if (data.total_news !== undefined) {
                             updateCountersFromServer(data.total_news, data.total_pages);
                        }
                    }
                })
                .catch(error => {
                    console.error('Error fetch al eliminar [Escritorio]:', error);
                    if (document.body.contains(container)) {
                        container.classList.remove('deleting');
                    }
                });
            });
        }
    }

    function checkForNewNews() {
        fetch(`/noticias/check-new-news/?last_checked=${encodeURIComponent(lastChecked)}`)
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    lastChecked = data.current_time;
                    if (data.news_cards && data.news_cards.length > 0) {
                        console.log(`${data.news_cards.length} nuevas noticias encontradas.`);
                        pendingNews = data.news_cards;

                        updateCountersFromServer(data.total_news, data.total_pages);
                        showNotification(pendingNews.length);
                        loadNewNews();
                    }
                } else {
                    console.error('Error chequeando noticias:', data.message);
                }
            })
            .catch(error => {
                console.error('Error en fetch al comprobar nuevas noticias:', error);
            });
    }

    function loadNewNews() {
        if (pendingNews.length === 0) return;

        const isDeviceMobile = isMobile();
        const MAX_NEWS = 25;
        const newsToAdd = pendingNews;
        pendingNews = [];

        const oldPositions = isDeviceMobile ? null : capturePositions();

        const currentCards = Array.from(newsGrid.children);
        const cardsToRemoveCount = Math.max(0, currentCards.length + newsToAdd.length - MAX_NEWS);
        const cardsToRemoveElements = currentCards.slice(-cardsToRemoveCount);
        const cardsToRemoveIds = cardsToRemoveElements.map(el => el.id);

        const removalPromises = cardsToRemoveElements.map(cardElement => {
            return new Promise(resolve => {
                const cardId = cardElement.id.replace('news-', '');
                const modal = document.getElementById(`modal-${cardId}`);
                const animationDuration = 300;

                cardElement.style.transition = `opacity ${animationDuration}ms ease, transform ${animationDuration}ms ease, height ${animationDuration}ms ease, margin ${animationDuration}ms ease, padding ${animationDuration}ms ease, border ${animationDuration}ms ease`;
                cardElement.style.opacity = '0';
                cardElement.style.transform = 'scale(0.8)';
                cardElement.style.height = '0';
                cardElement.style.margin = '0';
                cardElement.style.padding = '0';
                cardElement.style.borderWidth = '0';

                setTimeout(() => {
                    if (cardElement.parentNode) cardElement.remove();
                    if (modal && modal.parentNode) modal.remove();
                    resolve();
                }, animationDuration);
            });
        });

        Promise.all(removalPromises).then(() => {
            const newElementsData = [];
            const fragment = document.createDocumentFragment();

            newsToAdd.sort((a, b) => new Date(b.published) - new Date(a.published));

            newsToAdd.forEach((newsItem) => {
                const tempCard = document.createElement('div');
                tempCard.innerHTML = newsItem.card;
                const newsContainer = tempCard.firstElementChild;
                if (!newsContainer) return;
                const newsId = newsContainer.id.replace('news-', '');

                if (newsGrid.querySelector(`#${newsContainer.id}`)) {
                    console.warn(`Intento de añadir tarjeta duplicada (${newsContainer.id}) durante carga. Se omitió.`);
                    return;
                }

                const tempModal = document.createElement('div');
                tempModal.innerHTML = newsItem.modal;
                const modalElement = tempModal.firstElementChild;

                configureNewCard(newsContainer, modalElement, newsId);

                newsContainer.style.opacity = '0';
                newsContainer.style.transform = 'scale(0.9)';
                newsContainer.style.transition = 'none';

                fragment.appendChild(newsContainer);
                newElementsData.push({ container: newsContainer, modal: modalElement, id: newsId });
            });

            if (oldPositions) {
                animateReposition(oldPositions, cardsToRemoveIds);
            }

            newsGrid.insertBefore(fragment, newsGrid.firstChild);
            newElementsData.forEach(item => {
                if (item.modal) newsModalsContainer.appendChild(item.modal);
            });

            requestAnimationFrame(() => {
                newElementsData.forEach(({ container }) => {
                    void container.offsetWidth;

                    container.style.transition = 'opacity 0.4s ease, transform 0.4s cubic-bezier(0.25, 0.1, 0.25, 1)';
                    container.style.opacity = '1';
                    container.style.transform = 'scale(1)';

                    container.addEventListener('transitionend', function handler() {
                        container.style.transition = '';
                        container.style.opacity = '';
                        container.style.transform = '';
                        container.removeEventListener('transitionend', handler);
                    }, { once: true });
                });
            });
        });
    }

    function updatePagination(serverTotalPages) {
        const totalItems = parseInt(headerCounter?.textContent || "0");
        const itemsPerPage = 25;
        const totalPages = serverTotalPages !== undefined ? serverTotalPages : Math.ceil(totalItems / itemsPerPage);
        const currentPage = parseInt(new URLSearchParams(window.location.search).get('page') || "1");
        const needsPagination = totalPages > 1;
        let pagination = document.querySelector('.pagination');

        if (!pagination && !needsPagination) return;

        if (!pagination && needsPagination) {
            pagination = document.createElement('div');
            pagination.className = 'pagination';
            pagination.innerHTML = `
                <a href="?page=${currentPage - 1}" style="display: ${currentPage > 1 ? '' : 'none'}">Anterior</a>
                <span class="active">${currentPage} / ${totalPages}</span>
                <a href="?page=${currentPage + 1}" style="display: ${currentPage < totalPages ? '' : 'none'}">Siguiente</a>
            `;
            const newsGridParent = newsGrid.parentNode;
            newsGridParent.insertBefore(pagination, newsGrid.nextSibling);
        } else if (pagination && !needsPagination) {
            pagination.remove();
        } else if (pagination) {
            const activeSpan = pagination.querySelector('.active');
            const prevLink = pagination.querySelector('a:first-child');
            const nextLink = pagination.querySelector('a:last-child');

            if (activeSpan) activeSpan.textContent = `${currentPage} / ${totalPages}`;
            if (prevLink) {
                prevLink.href = `?page=${currentPage - 1}`;
                prevLink.style.display = currentPage > 1 ? '' : 'none';
            }
            if (nextLink) {
                nextLink.href = `?page=${currentPage + 1}`;
                nextLink.style.display = currentPage < totalPages ? '' : 'none';
            }
        }
    }

    function updateCountersFromServer(totalCount, totalPages) {
        if (totalCount === undefined) return;

        if (headerCounter) {
            const current = parseInt(headerCounter.textContent || "0");
            if (current !== totalCount) {
                headerCounter.textContent = totalCount;
                headerCounter.classList.add('counter-updated');
                setTimeout(() => {
                    headerCounter.classList.remove('counter-updated');
                }, 1000);
            }
        }

        if (totalCounter) {
            totalCounter.textContent = `${totalCount} noticias`;
        }

        updatePagination(totalPages);
    }

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

    function configureNewCard(newsContainer, modal, newsId) {
        if (!newsContainer) return;

        const cardFront = newsContainer.querySelector('.card-front');
        const cardBack = newsContainer.querySelector('.card-back');
        const linksContainer = cardBack?.querySelector('.news-links');

        const canDelete = newsContainer.querySelector('.delete-btn');
        const existingMobileDeleteBtn = cardFront?.querySelector('.mobile-delete-btn');
        if (existingMobileDeleteBtn) existingMobileDeleteBtn.remove();

        if (cardFront && canDelete) {
            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'mobile-delete-btn';
            deleteBtn.type = 'button';
            deleteBtn.dataset.id = newsId;
            deleteBtn.onclick = function(e) {
                e.stopPropagation();
                this.classList.add('pulse');
                setTimeout(() => this.classList.remove('pulse'), 300);
                deleteNews(newsId);
                return false;
            };
            cardFront.appendChild(deleteBtn);

            deleteBtn.onmouseenter = function(e) {
                e.stopPropagation();
                this.closest('.news-card')?.classList.add('delete-hover');
            };
            deleteBtn.onmouseleave = function(e) {
                e.stopPropagation();
                this.closest('.news-card')?.classList.remove('delete-hover');
            };
        }

        if (linksContainer) {
            const existingModalOpener = linksContainer.querySelector('.news-link.modal-opener');
            if (existingModalOpener) existingModalOpener.remove();

            const modalLink = document.createElement('a');
            modalLink.href = 'javascript:void(0)';
            modalLink.className = 'news-link modal-opener';
            modalLink.textContent = 'Más';
            modalLink.onclick = function(e) {
                 e.stopPropagation();
                 openNewsModal(newsId);
             };
            linksContainer.insertBefore(modalLink, linksContainer.firstChild);
        }

        const cardBackDeleteBtn = newsContainer.querySelector('.card-back .delete-btn');
        if (cardBackDeleteBtn) {
            cardBackDeleteBtn.dataset.id = newsId;
            cardBackDeleteBtn.onclick = function(e) {
                e.stopPropagation();
                deleteNews(this.dataset.id);
            };
        }

        const modalDeleteBtn = modal?.querySelector('.delete-btn');
        if (modalDeleteBtn) {
            modalDeleteBtn.dataset.id = newsId;
            modalDeleteBtn.onclick = function(e) {
                 e.stopPropagation();
                 deleteNews(this.dataset.id);
             };
        }

        const closeBtn = modal?.querySelector('.close');
        if (closeBtn) {
            closeBtn.onclick = () => closeNewsModal(newsId);
        }

        const image = newsContainer.querySelector('.news-image');
        if (image) {
            image.onmouseenter = function() { this.closest('.news-card')?.classList.add('image-hover'); };
            image.onmouseleave = function() { this.closest('.news-card')?.classList.remove('image-hover'); };
        }
    }

    const updateFeedBtn = document.getElementById('updateFeedBtn');
    if (updateFeedBtn) {
        updateFeedBtn.addEventListener('click', function() {
            const button = this;
            button.disabled = true;
            button.classList.add('loading');

            fetch('/noticias/update-feed/', { method: 'GET', headers: { 'X-CSRFToken': getCookie('csrftoken') } })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    if (data.total_news !== undefined) {
                        updateCountersFromServer(data.total_news, data.total_pages);
                    }
                    checkForNewNews();
                } else {
                    console.error('Error al actualizar feed:', data.message);
                    alert('Error al actualizar el feed: ' + data.message);
                }
            })
            .catch(error => {
                console.error('Error fetch al actualizar feed:', error);
                alert('Error de conexión al actualizar el feed.');
            })
            .finally(() => {
                button.disabled = false;
                button.classList.remove('loading');
            });
        });
    }

    document.querySelectorAll('.news-grid .news-card-container').forEach(container => {
        const newsId = container.id.replace('news-', '');
        const modal = document.getElementById(`modal-${newsId}`);
        configureNewCard(container, modal, newsId);
    });

    setInterval(checkForNewNews, CHECK_INTERVAL);

    updatePagination();

}); 