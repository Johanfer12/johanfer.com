(() => {
    'use strict';

    /* ---------------------------------------------------------------------
     *  Constantes y estado global ligero
     * ------------------------------------------------------------------ */
    const SELECTORS = {
        grid: '.news-grid',
        total: '.total',
        counter: '.header-counter',
        modalsContainer: '#news-modals-container',
        notification: '#new-news-notification',
        notificationCount: '#new-news-count',
        notifCloseBtn: '#close-notification-btn',
        updateFeedBtn: '#updateFeedBtn',
    };

    const MAX_NEWS = 25;
    const NOTIF_DURATION = 10_000;         // 10 s
    const CHECK_INTERVAL = 180_000;        // 3 min

    const $ = (sel, ctx = document) => ctx.querySelector(sel);
    const $$ = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));
    const isMobile = () => window.innerWidth <= 767;
    
    const DOM = Object.fromEntries(Object.entries(SELECTORS).map(([k, v]) => [k, $(v)]));

    const STATE = {
        notifTimer: null,
        notifStart: 0,
        notifRemaining: 0,
        pageVisible: true,
        pendingNews: [],
        totalPending: 0,
        userInteracted: false,
        lastChecked: new Date().toISOString(),
        backupCards: [], // Noticias de respaldo precargadas
        backupModals: [], // Modales de respaldo precargados
    };

    /* ---------------------------------------------------------------------
     *  Utilidades genéricas
     * ------------------------------------------------------------------ */
    const log = (...args) => console.log('[news]', ...args);
    const err = (...args) => console.error('[news]', ...args);

    const getCookie = (name) => {
        const value = document.cookie
            .split(';')
            .map(c => c.trim())
            .find(c => c.startsWith(`${name}=`));
        return value ? decodeURIComponent(value.split('=')[1]) : null;
    };

    /** Envuelve fetch y parsea JSON con control de errores */
    const fetchJson = (url, options = {}) => fetch(url, options)
        .then(r => r.ok ? r.json() : Promise.reject(new Error(r.statusText)));

    /** Devuelve posiciones (DOMRect) de cada contenedor de tarjeta */
    const capturePositions = () => new Map($$('.news-grid .news-card-container').map(el => [el, el.getBoundingClientRect()]));

    /** Animación FLIP (First‑Last Invert Play) para re‑posicionamiento */
    const animateReposition = (oldPos, excludedIds = []) => {
        if (isMobile() || !oldPos.size) return;
        requestAnimationFrame(() => {
            oldPos.forEach((rect, el) => {
                if (!document.body.contains(el) || excludedIds.includes(el.id)) return;
                const newRect = el.getBoundingClientRect();
                const dx = rect.left - newRect.left;
                const dy = rect.top - newRect.top;
                if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) return;
                el.style.transform = `translate(${dx}px,${dy}px)`;
                el.style.transition = 'none';
                requestAnimationFrame(() => {
                    el.style.transition = 'transform 0.5s cubic-bezier(0.25,0.1,0.25,1)';
                    el.style.transform = '';
                    el.addEventListener('transitionend', () => {
                        el.style.transition = '';
                    }, {once: true});
                });
            });
        });
    };

    /** Pequeña animación de fade/scale */
    const animateScaleOpacity = (el, {fromScale = 0.9, toScale = 1, duration = 400} = {}) => {
        el.style.opacity = '0';
        el.style.transform = `scale(${fromScale})`;
        el.style.transition = 'none';
        void el.offsetWidth; // re‑flow
        requestAnimationFrame(() => {
            el.style.transition = `opacity ${duration}ms ease, transform ${duration}ms cubic-bezier(0.25,0.1,0.25,1)`;
            el.style.opacity = '1';
            el.style.transform = `scale(${toScale})`;
            el.addEventListener('transitionend', () => {
                el.style.transition = el.style.opacity = el.style.transform = '';
            }, {once: true});
        });
    };

    /** Asegura que no haya más de MAX_NEWS tarjetas visibles eliminando las más antiguas */
    const enforceCardLimit = () => {
        const cards = $$('.news-card-container', DOM.grid);
        if (cards.length <= MAX_NEWS) return; // Si no se excede, no hacer nada

        // Seleccionar las tarjetas sobrantes desde el índice MAX_NEWS (las más antiguas)
        const excessCards = cards.slice(MAX_NEWS);
        excessCards.forEach(card => {
            const cardId = card.id.replace('news-', '');
            const modal = $(`#modal-${cardId}`);
            card.remove();
            modal?.remove();
            log(`Enforce limit: Removed excess card ${cardId}`);
        });
    };

    /* ---------------------------------------------------------------------
     *  Notificación de nuevas noticias
     * ------------------------------------------------------------------ */
    const showNotification = (count) => {
        if (!STATE.userInteracted && DOM.notification.classList.contains('show')) {
            STATE.totalPending += count;
        } else {
            STATE.totalPending = count;
        }
        DOM.notificationCount.textContent = `${STATE.totalPending} nuevas noticias añadidas`;
        DOM.notification.classList.remove('hiding');
        DOM.notification.classList.add('show');

        clearTimeout(STATE.notifTimer);
        if (STATE.pageVisible) {
            STATE.notifStart = Date.now();
            STATE.notifRemaining = NOTIF_DURATION;
            STATE.notifTimer = setTimeout(hideNotification, NOTIF_DURATION);
        } else {
            STATE.notifRemaining = NOTIF_DURATION;
        }
    };

    const hideNotification = () => {
        DOM.notification.classList.add('hiding');
        setTimeout(() => DOM.notification.classList.remove('show', 'hiding'), 500);
        clearTimeout(STATE.notifTimer);
        STATE.notifRemaining = STATE.totalPending = 0;
        STATE.userInteracted = false;
    };

    /* ---------------------------------------------------------------------
     *  Modales (API pública: openNewsModal / closeNewsModal)
     * ------------------------------------------------------------------ */
    const toggleBodyScroll = (disable) => {
        document.body.style.overflow = disable ? 'hidden' : 'auto';
    };

    const openNewsModal = (id) => {
        const modal = $(`#modal-${id}`);
        if (!modal) return;
        modal.style.display = 'block';
        setTimeout(() => modal.classList.add('show'), 10);
        toggleBodyScroll(true);
    };

    const closeNewsModal = (id) => {
        const modal = $(`#modal-${id}`);
        if (!modal) return;
        modal.classList.remove('show');
        setTimeout(() => {
            modal.style.display = 'none';
            toggleBodyScroll(false);
        }, 300);
    };

    // Exponer en window para atributos inline
    Object.assign(window, {openNewsModal, closeNewsModal});

    // Cerrar al hacer clic fuera del contenido
    window.addEventListener('click', (e) => {
        if (e.target.classList.contains('modal')) closeNewsModal(e.target.id.replace('modal-', ''));
    });

    /* ---------------------------------------------------------------------
     *  Carga inicial y precarga de noticias de respaldo
     * ------------------------------------------------------------------ */
    const initializeBackupCards = () => {
        try {
            const backupDataElement = $('#backup-cards-data');
            if (backupDataElement) {
                const backupData = JSON.parse(backupDataElement.textContent);
                STATE.backupCards = backupData || [];
                STATE.backupModals = backupData?.map(card => card.modal) || [];
                log(`Inicializadas ${STATE.backupCards.length} noticias de respaldo desde el servidor`);
            }
        } catch (e) {
            err('Error al inicializar noticias de respaldo:', e);
            STATE.backupCards = [];
            STATE.backupModals = [];
        }
    };

    /* ---------------------------------------------------------------------
     *  Eliminación de noticias (móvil + escritorio fusionados)
     * ------------------------------------------------------------------ */
    const serverDeleteNews = (newsId, currentPage) => fetchJson(`/noticias/delete/${newsId}/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCookie('csrftoken'),
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
        body: `current_page=${currentPage}`,
    });

    const deleteNews = (newsId) => {
        const container = $(`#news-${newsId}`);
        if (!container) return err(`Contenedor no encontrado (${newsId})`);
        const modal = $(`#modal-${newsId}`);
        const currentPage = new URLSearchParams(location.search).get('page') || 1;
        if (modal?.classList.contains('show')) closeNewsModal(newsId);

        const oldPositions = isMobile() ? null : capturePositions();

        // Ejecutar animación de salida inmediatamente (optimista)
        container.classList.add('deleting');
        
        // Intentar usar una noticia de respaldo precargada primero
        let replacementCard = null;
        let replacementModal = null;
        
        if (STATE.backupCards.length > 0) {
            const backupData = STATE.backupCards.shift(); // Tomar la primera de respaldo
            const backupModalData = STATE.backupModals.shift();
            
            if (backupData) {
                const temp = document.createElement('div');
                temp.innerHTML = backupData.card;
                replacementCard = temp.firstElementChild;
                
                if (backupModalData) {
                    const tempModal = document.createElement('div');
                    tempModal.innerHTML = backupModalData;
                    replacementModal = tempModal.firstElementChild;
                }
                
                if (replacementCard) {
                    const id = replacementCard.id.replace('news-', '');
                    configureNewCard(replacementCard, replacementModal, id);
                    log(`Usando noticia de respaldo precargada: ${id}`);
                }
            }
        }
        
        // Programar eliminación del DOM después de la animación
        const removeFromDOM = () => {
            container.remove();
            modal?.remove();
        };

        // Esperar a que termine la animación CSS antes de remover del DOM
        const animationDuration = 600; // Duración de la animación deleteCard en CSS
        const removeTimeout = setTimeout(() => {
            removeFromDOM();
            
            // Agregar tarjeta de reemplazo si existe
            if (replacementCard && !$("#" + replacementCard.id, DOM.grid)) {
                DOM.grid.appendChild(replacementCard);
                replacementModal && DOM.modalsContainer.appendChild(replacementModal);
                animateScaleOpacity(replacementCard);
            }
            
            if (oldPositions) animateReposition(oldPositions, [`news-${newsId}`]);
            enforceCardLimit();
        }, animationDuration);

        // Llamada al servidor en paralelo
        serverDeleteNews(newsId, currentPage)
            .then(data => {
                if (data.status !== 'success') {
                    // Si el servidor falló, revertir la animación
                    clearTimeout(removeTimeout);
                    container.classList.remove('deleting');
                    
                    // Devolver la noticia de respaldo al array si se había tomado
                    if (replacementCard && STATE.backupCards.length < 5) {
                        const backupData = STATE.backupCards.find(card => card.id == replacementCard.id.replace('news-', ''));
                        if (!backupData) {
                            STATE.backupCards.unshift({
                                id: replacementCard.id.replace('news-', ''),
                                card: replacementCard.outerHTML
                            });
                            STATE.backupModals.unshift(replacementModal?.outerHTML || '');
                        }
                    }
                    
                    err('Error del servidor al eliminar:', data.message);
                    return;
                }

                // Si ya se eliminó del DOM por timeout, actualizar contadores y recargar respaldo
                if (!document.body.contains(container)) {
                    updateCounters(data.total_news, data.total_pages);
                    
                    // Si no había noticia de respaldo precargada, usar la del servidor
                    if (!replacementCard && data.html && data.modal) {
                        const temp = document.createElement('div');
                        temp.innerHTML = data.html;
                        const newCard = temp.firstElementChild;
                        const tempModal = document.createElement('div');
                        tempModal.innerHTML = data.modal;
                        const newModal = tempModal.firstElementChild;
                        
                        if (newCard) {
                            configureNewCard(newCard, newModal, newCard.id.replace('news-', ''));
                            DOM.grid.appendChild(newCard);
                            newModal && DOM.modalsContainer.appendChild(newModal);
                            animateScaleOpacity(newCard);
                        }
                    }
                    
                    // Las noticias de respaldo se recargan automáticamente al cambiar de página
                    
                    return;
                }

                // Si el servidor responde antes del timeout, cancelar timeout y proceder normalmente
                clearTimeout(removeTimeout);
                removeFromDOM();
                updateCounters(data.total_news, data.total_pages);

                // Agregar tarjeta de reemplazo
                if (replacementCard && !$("#" + replacementCard.id, DOM.grid)) {
                    DOM.grid.appendChild(replacementCard);
                    replacementModal && DOM.modalsContainer.appendChild(replacementModal);
                    animateScaleOpacity(replacementCard);
                } else if (!replacementCard && data.html && data.modal) {
                    // Usar la del servidor si no había de respaldo
                    const temp = document.createElement('div');
                    temp.innerHTML = data.html;
                    const newCard = temp.firstElementChild;
                    const tempModal = document.createElement('div');
                    tempModal.innerHTML = data.modal;
                    const newModal = tempModal.firstElementChild;
                    
                    if (newCard) {
                        configureNewCard(newCard, newModal, newCard.id.replace('news-', ''));
                        DOM.grid.appendChild(newCard);
                        newModal && DOM.modalsContainer.appendChild(newModal);
                        animateScaleOpacity(newCard);
                    }
                }

                if (oldPositions) animateReposition(oldPositions, [`news-${newsId}`]);
                enforceCardLimit();
                
                // Las noticias de respaldo se recargan automáticamente al cambiar de página
            })
            .catch(e => {
                // En caso de error de red o servidor, revertir la animación
                clearTimeout(removeTimeout);
                container.classList.remove('deleting');
                
                // Devolver la noticia de respaldo al array si se había tomado
                if (replacementCard && STATE.backupCards.length < 5) {
                    const backupData = STATE.backupCards.find(card => card.id == replacementCard.id.replace('news-', ''));
                    if (!backupData) {
                        STATE.backupCards.unshift({
                            id: replacementCard.id.replace('news-', ''),
                            card: replacementCard.outerHTML
                        });
                        STATE.backupModals.unshift(replacementModal?.outerHTML || '');
                    }
                }
                
                err('Error al eliminar noticia:', e);
                alert('Error al eliminar la noticia. Por favor, inténtalo de nuevo.');
            });
    };



    /* ---------------------------------------------------------------------
     *  Alta de tarjetas nuevas y actualización de feed
     * ------------------------------------------------------------------ */
    const loadNewNews = () => {
        if (!STATE.pendingNews.length) return;
        const newsToAdd = [...STATE.pendingNews];
        STATE.pendingNews.length = 0;

        const oldPositions = isMobile() ? null : capturePositions();
        const currentCards = Array.from(DOM.grid.children);

        // Insertar nuevas (ordenadas por fecha desc.)
        newsToAdd.sort((a, b) => new Date(b.published) - new Date(a.published));
        const frag = document.createDocumentFragment();
        const newIds = [];

        for (const item of newsToAdd) {
            const tmp = document.createElement('div');
            tmp.innerHTML = item.card;
            const card = tmp.firstElementChild;
            if (!card) continue; // Saltar si el HTML de la tarjeta estaba vacío
            // Comprobar duplicados ANTES de añadir al fragmento
            if ($("#" + card.id, DOM.grid)) { 
                log(`Skipping duplicate card from pendingNews: ${card.id}`);
                continue; 
            }
            const id = card.id.replace('news-', '');
            const tmpModal = document.createElement('div');
            tmpModal.innerHTML = item.modal;
            const modalEl = tmpModal.firstElementChild;
            configureNewCard(card, modalEl, id);
            frag.appendChild(card);
            DOM.modalsContainer.appendChild(modalEl);
            newIds.push(card);
        }

        DOM.grid.prepend(frag);
        if (oldPositions) animateReposition(oldPositions);
        newIds.forEach(el => animateScaleOpacity(el));
        enforceCardLimit(); // Asegurar límite DESPUÉS de añadir nuevas
    };

    const checkForNewNews = () => {
        fetchJson(`/noticias/check-new-news/?last_checked=${encodeURIComponent(STATE.lastChecked)}`)
            .then(data => {
                if (data.status !== 'success') throw new Error(data.message);
                STATE.lastChecked = data.current_time;
                if (data.news_cards?.length) {
                    STATE.pendingNews.push(...data.news_cards);
                    updateCounters(data.total_news, data.total_pages);
                    showNotification(data.news_cards.length);
                        loadNewNews();
                }
            })
            .catch(e => err('Chequeo de noticias:', e));
    };

    /* ---------------------------------------------------------------------
     *  Paginación y contadores
     * ------------------------------------------------------------------ */
    const updatePagination = (serverTotalPages) => {
        const itemsPerPage = MAX_NEWS;
        const totalItems = parseInt(DOM.counter?.textContent || '0', 10);
        const totalPages = serverTotalPages ?? Math.ceil(totalItems / itemsPerPage);
        const currentPage = parseInt(new URLSearchParams(location.search).get('page') || '1', 10);

        let pagination = $('.pagination');
        const needs = totalPages > 1;
        if (!needs && pagination) return pagination.remove();
        if (!needs) return;

        const tpl = (pg) => `<a href="?page=${pg}">${pg === currentPage ? '···' : (pg < currentPage ? 'Anterior' : 'Siguiente')}</a>`;
        if (!pagination) {
            pagination = document.createElement('div');
            pagination.className = 'pagination';
            DOM.grid.parentNode.insertBefore(pagination, DOM.grid.nextSibling);
        }
        pagination.innerHTML = `${currentPage > 1 ? tpl(currentPage - 1) : ''}
            <span class="active">${currentPage} / ${totalPages}</span>
            ${currentPage < totalPages ? tpl(currentPage + 1) : ''}`;
    };

    const updateCounters = (totalCount, totalPages) => {
        if (totalCount == null) return;
        if (DOM.counter && +DOM.counter.textContent !== totalCount) {
            DOM.counter.textContent = totalCount;
            DOM.counter.classList.add('counter-updated');
            setTimeout(() => DOM.counter.classList.remove('counter-updated'), 1_000);
        }
        DOM.total && (DOM.total.textContent = `${totalCount} noticias`);
        updatePagination(totalPages);
    };

    /* ---------------------------------------------------------------------
     *  Configuración de tarjetas (botones, hover, etc.)
     * ------------------------------------------------------------------ */
    const configureNewCard = (container, modal, id) => {
        if (!container) return;
        const front = container.querySelector('.card-front');
        const back = container.querySelector('.card-back');
        const links = back?.querySelector('.news-links');

        // Botón eliminar móvil ✕
        if (front && !front.querySelector('.mobile-delete-btn') && container.querySelector('.delete-btn')) {
            const mbBtn = document.createElement('button');
            mbBtn.className = 'mobile-delete-btn';
            mbBtn.type = 'button';
            mbBtn.dataset.id = id;
            const cardElement = container.querySelector('.news-card'); // Reutilizamos la selección
            mbBtn.addEventListener('click', (e) => { e.stopPropagation(); mbBtn.classList.add('pulse'); setTimeout(() => mbBtn.classList.remove('pulse'), 300); deleteNews(id); });
            if (cardElement) { // Aplicar hover al elemento interno .news-card
                mbBtn.addEventListener('mouseenter', (e) => { e.stopPropagation(); cardElement.classList.add('delete-hover'); });
                mbBtn.addEventListener('mouseleave', (e) => { e.stopPropagation(); cardElement.classList.remove('delete-hover'); });
            }
            front.appendChild(mbBtn);
        }

        // Enlace "Más" para modal
        if (links && !links.querySelector('.modal-opener')) {
            const more = document.createElement('a');
            more.href = 'javascript:void(0)';
            more.className = 'news-link modal-opener';
            more.textContent = 'Más';
            more.addEventListener('click', (e) => { e.stopPropagation(); openNewsModal(id); });
            links.prepend(more);
        }

        // Delete dentro de card‑back y modal
        [container.querySelector('.card-back .delete-btn'), modal?.querySelector('.delete-btn')].forEach(btn => {
            btn?.addEventListener('click', (e) => { e.stopPropagation(); deleteNews(id); });
        });

        // Close modal X
        modal?.querySelector('.close')?.addEventListener('click', () => closeNewsModal(id));

        // Evitar flip al pasar por la imagen
        const img = container.querySelector('.news-image');
        const cardElement = container.querySelector('.news-card'); // Selecciona el elemento .news-card interno
        if (img && cardElement) {
            img.addEventListener('mouseenter', () => cardElement.classList.add('image-hover'));
            img.addEventListener('mouseleave', () => cardElement.classList.remove('image-hover'));
        }
    };

    // Configurar tarjetas existentes al cargar
    $$('.news-grid .news-card-container').forEach(el => {
        const id = el.id.replace('news-', '');
        configureNewCard(el, $(`#modal-${id}`), id);
    });

    /* ---------------------------------------------------------------------
     *  Event listeners globales
     * ------------------------------------------------------------------ */
    // Visibilidad de la pestaña → pausa/reanuda notificación
    document.addEventListener('visibilitychange', () => {
        STATE.pageVisible = !document.hidden;
        if (!STATE.pageVisible) {
            clearTimeout(STATE.notifTimer);
            STATE.notifRemaining -= Date.now() - STATE.notifStart;
        } else if (STATE.notifRemaining > 0 && DOM.notification.classList.contains('show')) {
            STATE.notifStart = Date.now();
            STATE.notifTimer = setTimeout(hideNotification, STATE.notifRemaining);
        }
    });

    // Interacción del usuario → reset userInteracted para unir notificaciones
    ['click', 'scroll'].forEach(evt => document.addEventListener(evt, () => { STATE.userInteracted = true; }));

    // Cerrar notificación manualmente
    DOM.notifCloseBtn?.addEventListener('click', hideNotification);

    // Botón de actualizar feed
    DOM.updateFeedBtn?.addEventListener('click', function () {
        const btn = this;
        btn.disabled = true;
        btn.classList.add('loading');
        fetchJson('/noticias/update-feed/', {headers: {'X-CSRFToken': getCookie('csrftoken')}})
            .then(data => {
                if (data.status !== 'success') throw new Error(data.message);
                updateCounters(data.total_news, data.total_pages);
                    checkForNewNews();
            })
            .catch(e => { err('Actualizar feed:', e); alert('Error al actualizar el feed: ' + e.message); })
            .finally(() => { btn.disabled = false; btn.classList.remove('loading'); });
    });

    /* ---------------------------------------------------------------------
     *  Arranque
     * ------------------------------------------------------------------ */
    // Inicializar noticias de respaldo desde el servidor
    document.addEventListener('DOMContentLoaded', () => {
        initializeBackupCards();
    });
    
    setInterval(checkForNewNews, CHECK_INTERVAL);
    enforceCardLimit(); // Aplicar límite al cargar la página inicialmente
    updatePagination();

})();
