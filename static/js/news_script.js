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
        undoBtn: '#undoBtn',
        orderBtn: '#orderBtn',
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
        backupCards: [], // Noticias de respaldo precargadas (ahora hasta 25)
        backupModals: [], // Modales de respaldo precargados
        deleteStack: [],
        order: new URLSearchParams(location.search).get('order') || 'desc',
        currentPage: parseInt(new URLSearchParams(location.search).get('page') || '1', 10),
        nextCursor: null,
        loadingMoreBackup: false, // Flag para evitar múltiples peticiones
        backupCursor: null, // Cursor para las siguientes noticias de respaldo
        deletingNews: new Set(), // IDs de noticias siendo eliminadas
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
                    el.style.transition = 'transform 0.4s ease-out';
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

    /** Crea elementos de tarjeta y modal desde HTML string */
    const createCardFromHTML = (cardHtml, modalHtml = null) => {
        const temp = document.createElement('div');
        temp.innerHTML = cardHtml;
        const card = temp.firstElementChild;
        
        let modal = null;
        if (modalHtml) {
            const tempModal = document.createElement('div');
            tempModal.innerHTML = modalHtml;
            modal = tempModal.firstElementChild;
        }
        
        return { card, modal };
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
        body: `current_page=${currentPage}&order=${STATE.order}`,
    });

    const serverUndoNews = (newsId) => fetchJson(`/noticias/undo/${newsId}/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken'),
        },
    });

    const serverGetPage = ({cursor, page, order, q, backupOnly = false}) => {
        const params = new URLSearchParams();
        if (cursor) params.set('cursor', cursor);
        else if (page) params.set('page', page);
        if (order) params.set('order', order);
        if (q) params.set('q', q);
        if (backupOnly) params.set('backup_only', 'true');
        return fetchJson(`/noticias/get-page/?${params.toString()}`);
    };

    // Nueva función para cargar más noticias de respaldo
    const loadMoreBackupNews = async () => {
        if (STATE.loadingMoreBackup) return; // Evitar múltiples peticiones
        
        const currentPageNum = parseInt(new URLSearchParams(location.search).get('page') || '1', 10);
        if (currentPageNum !== 1) return; // Solo cargar respaldo en página 1
        
        STATE.loadingMoreBackup = true;
        log('Cargando más noticias de respaldo...');
        
        try {
            const q = new URLSearchParams(location.search).get('q') || '';
            // Usar el cursor de respaldo o calcular desde dónde seguir
            const cursor = STATE.backupCursor || STATE.nextCursor;
            
            const data = await serverGetPage({
                cursor: cursor,
                order: STATE.order,
                q: q,
                backupOnly: true
            });
            
            if (data.status === 'success' && data.backup_cards) {
                // Filtrar noticias duplicadas
                const newBackups = data.backup_cards.filter(card => 
                    !$(`#news-${card.id}`, DOM.grid) && 
                    !STATE.backupCards.some(existing => existing.id == card.id)
                );
                
                STATE.backupCards.push(...newBackups);
                STATE.backupModals.push(...newBackups.map(x => x.modal));
                
                // Actualizar cursor para la siguiente carga
                if (newBackups.length > 0) {
                    // Por ahora usamos el cursor actual, podríamos construirlo desde lastBackup
                    STATE.backupCursor = cursor;
                }
                
                log(`Cargadas ${newBackups.length} noticias adicionales de respaldo. Total: ${STATE.backupCards.length}`);
            }
        } catch (e) {
            err('Error cargando más noticias de respaldo:', e);
        } finally {
            STATE.loadingMoreBackup = false;
        }
    };

    const deleteNews = (newsId) => {
        // Protección contra eliminaciones simultáneas
        if (STATE.deletingNews.has(newsId)) return;
        STATE.deletingNews.add(newsId);
        
        const container = $(`#news-${newsId}`);
        if (!container) {
            STATE.deletingNews.delete(newsId);
            return err(`Contenedor no encontrado (${newsId})`);
        }
        const modal = $(`#modal-${newsId}`);
        const currentPage = new URLSearchParams(location.search).get('page') || 1;
        if (modal?.classList.contains('show')) closeNewsModal(newsId);

        const mobileView = isMobile();
        const oldPositions = mobileView ? null : capturePositions();

        // Ejecutar animación de salida: móvil (height) vs escritorio (width)
        const initialHeight = container.offsetHeight;
        const initialWidth = container.offsetWidth;
        container.classList.add('collapsing');
        
        if (mobileView) {
            container.style.height = initialHeight + 'px';
            void container.offsetHeight;
            requestAnimationFrame(() => {
                container.style.height = '0px';
                container.style.opacity = '0';
                container.style.transform = 'scale(0.85)';
            });
        } else {
            container.style.width = initialWidth + 'px';
            container.style.marginRight = '0px';
            void container.offsetWidth;
            requestAnimationFrame(() => {
                container.style.width = '0px';
                container.style.marginRight = '-20px'; // Ayuda a que las tarjetas se muevan antes
                container.style.opacity = '0';
                container.style.transform = 'scale(0.85)';
            });
        }
        
        // Intentar usar una noticia de respaldo precargada primero
        let replacementCard = null;
        let replacementModal = null;
        
        if (STATE.backupCards.length > 0) {
            // Buscar una noticia de respaldo que no esté duplicada
            let backupIndex = -1;
            for (let i = 0; i < STATE.backupCards.length; i++) {
                const backupData = STATE.backupCards[i];
                if (backupData && backupData.id) {
                    const existingCard = $(`#news-${backupData.id}`, DOM.grid);
                    if (!existingCard) {
                        backupIndex = i;
                        break;
                    } else {
                        log(`Skipping duplicate backup card: ${backupData.id}`);
                    }
                }
            }
            
            if (backupIndex >= 0) {
                const backupData = STATE.backupCards.splice(backupIndex, 1)[0];
                const backupModalData = STATE.backupModals.splice(backupIndex, 1)[0];
                
                if (backupData && backupData.card) {
                    const { card, modal } = createCardFromHTML(backupData.card, backupModalData);
                    replacementCard = card;
                    replacementModal = modal;
                    
                    if (replacementCard) {
                        const id = replacementCard.id.replace('news-', '');
                        configureNewCard(replacementCard, replacementModal, id);
                        log(`Usando noticia de respaldo precargada: ${id}`);
                    }
                }
            } else {
                log('No hay noticias de respaldo válidas (sin duplicados)');
            }
        }
        
        // Programar eliminación del DOM después de la animación
        const removeFromDOM = () => {
            container.remove();
            modal?.remove();
        };

        // Eliminar por transitionend con fallback por tiempo
        const animationDuration = 500; // margen para height/opacity/transform
        let removed = false;
        const onAnimEnd = (ev) => {
            const expectedProp = mobileView ? 'height' : 'width';
            if (ev.target !== container || ev.propertyName !== expectedProp) return;
            container.removeEventListener('transitionend', onAnimEnd);
            if (removed) return;
            removed = true;
            removeFromDOM();
            if (replacementCard && !$(`#${replacementCard.id}`, DOM.grid)) {
                if (STATE.order === 'asc') {
                    DOM.grid.appendChild(replacementCard);
                } else {
                    DOM.grid.prepend(replacementCard);
                }
                replacementModal && DOM.modalsContainer.appendChild(replacementModal);
                animateScaleOpacity(replacementCard);
            }
            if (oldPositions) animateReposition(oldPositions, [`news-${newsId}`]);
            enforceCardLimit();
            STATE.deletingNews.delete(newsId); // Limpiar flag
        };
        container.addEventListener('transitionend', onAnimEnd, { once: true });
        const removeTimeout = setTimeout(() => {
            if (removed) return;
            removed = true;
            container.removeEventListener('transitionend', onAnimEnd);
            removeFromDOM();
            if (replacementCard && !$(`#${replacementCard.id}`, DOM.grid)) {
                if (STATE.order === 'asc') {
                    DOM.grid.appendChild(replacementCard);
                } else {
                    DOM.grid.prepend(replacementCard);
                }
                replacementModal && DOM.modalsContainer.appendChild(replacementModal);
                animateScaleOpacity(replacementCard);
            }
            if (oldPositions) animateReposition(oldPositions, [`news-${newsId}`]);
            enforceCardLimit();
            STATE.deletingNews.delete(newsId); // Limpiar flag
        }, animationDuration + 50);

        // Llamada al servidor en paralelo
        serverDeleteNews(newsId, currentPage)
            .then(data => {
                if (data.status !== 'success') {
                    // Si el servidor falló, revertir la animación
                    clearTimeout(removeTimeout);
                    container.removeEventListener('transitionend', onAnimEnd);
                    // revertir colapso
                    container.style.transition = 'none';
                    container.style.height = '';
                    container.style.width = '';
                    container.style.marginRight = '';
                    container.style.opacity = '';
                    container.style.transform = '';
                    container.classList.remove('collapsing');
                    void container.offsetHeight;
                    
                    // Devolver la noticia de respaldo al array si se había tomado
                    if (replacementCard && STATE.backupCards.length < 5) {
                        const cardId = replacementCard.id.replace('news-', '');
                        const backupData = STATE.backupCards.find(card => card.id == cardId);
                        if (!backupData && !$(`#news-${cardId}`, DOM.grid)) {
                            STATE.backupCards.unshift({
                                id: cardId,
                                card: replacementCard.outerHTML
                            });
                            STATE.backupModals.unshift(replacementModal?.outerHTML || '');
                            log(`Devuelta noticia de respaldo al array: ${cardId}`);
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
                        const { card: newCard, modal: newModal } = createCardFromHTML(data.html, data.modal);
                        
                        if (newCard) {
                            const newCardId = newCard.id.replace('news-', '');
                            // Verificar que no esté duplicada
                            if (!$(`#news-${newCardId}`, DOM.grid)) {
                                configureNewCard(newCard, newModal, newCardId);
                                if (STATE.order === 'asc') {
                                    DOM.grid.appendChild(newCard);
                                } else {
                                    DOM.grid.prepend(newCard);
                                }
                                newModal && DOM.modalsContainer.appendChild(newModal);
                                animateScaleOpacity(newCard);
                                log(`Agregada noticia del servidor: ${newCardId}`);
                            } else {
                                log(`Skipping duplicate server card: ${newCardId}`);
                            }
                        }
                    }
                    
                    // Cargar más noticias de respaldo si quedamos con pocas
                    if (STATE.backupCards.length < 5) {
                        loadMoreBackupNews();
                    }
                    
                    return;
                }

                // Si el servidor responde antes del timeout, cancelar timeout y proceder normalmente
                clearTimeout(removeTimeout);
                container.removeEventListener('transitionend', onAnimEnd);
                removeFromDOM();
                updateCounters(data.total_news, data.total_pages);

                // Agregar tarjeta de reemplazo
                if (replacementCard && !$(`#${replacementCard.id}`, DOM.grid)) {
                    DOM.grid.appendChild(replacementCard);
                    replacementModal && DOM.modalsContainer.appendChild(replacementModal);
                    animateScaleOpacity(replacementCard);
                } else if (!replacementCard && data.html && data.modal) {
                    // Usar la del servidor si no había de respaldo
                    const { card: newCard, modal: newModal } = createCardFromHTML(data.html, data.modal);
                    
                    if (newCard) {
                        const newCardId = newCard.id.replace('news-', '');
                        // Verificar que no esté duplicada
                        if (!$(`#news-${newCardId}`, DOM.grid)) {
                            configureNewCard(newCard, newModal, newCardId);
                            DOM.grid.appendChild(newCard);
                            newModal && DOM.modalsContainer.appendChild(newModal);
                            animateScaleOpacity(newCard);
                            log(`Agregada noticia del servidor (fallback): ${newCardId}`);
                        } else {
                            log(`Skipping duplicate server card (fallback): ${newCardId}`);
                        }
                    }
                }

                if (oldPositions) animateReposition(oldPositions, [`news-${newsId}`]);
                enforceCardLimit();
                
                // Cargar más noticias de respaldo si quedamos con pocas
                if (STATE.backupCards.length < 5) {
                    loadMoreBackupNews();
                }
            })
            .catch(e => {
                // En caso de error de red o servidor, revertir la animación
                clearTimeout(removeTimeout);
                container.classList.remove('deleting');
                
                // Devolver la noticia de respaldo al array si se había tomado
                if (replacementCard && STATE.backupCards.length < 5) {
                    const cardId = replacementCard.id.replace('news-', '');
                    const backupData = STATE.backupCards.find(card => card.id == cardId);
                    if (!backupData && !$(`#news-${cardId}`, DOM.grid)) {
                        STATE.backupCards.unshift({
                            id: cardId,
                            card: replacementCard.outerHTML
                        });
                        STATE.backupModals.unshift(replacementModal?.outerHTML || '');
                        log(`Devuelta noticia de respaldo al array (catch): ${cardId}`);
                    }
                }
                
                err('Error al eliminar noticia:', e);
                alert('Error al eliminar la noticia. Por favor, inténtalo de nuevo.');
                STATE.deletingNews.delete(newsId); // Limpiar flag en error
            });

        // Apilar para deshacer
        STATE.deleteStack.unshift(newsId);
        if (STATE.deleteStack.length > 5) STATE.deleteStack.length = 5;
    };



    /* ---------------------------------------------------------------------
     *  Alta de tarjetas nuevas y actualización de feed
     * ------------------------------------------------------------------ */
    const loadNewNews = () => {
        if (!STATE.pendingNews.length) return;
        const newsToAdd = [...STATE.pendingNews];
        STATE.pendingNews.length = 0;

        const oldPositions = isMobile() ? null : capturePositions();

        // Insertar nuevas según el orden activo
        if (STATE.order === 'asc') {
            newsToAdd.sort((a, b) => new Date(a.published) - new Date(b.published));
        } else {
            newsToAdd.sort((a, b) => new Date(b.published) - new Date(a.published));
        }
        const frag = document.createDocumentFragment();
        const newIds = [];

        for (const item of newsToAdd) {
            const { card, modal: modalEl } = createCardFromHTML(item.card, item.modal);
            if (!card) continue; // Saltar si el HTML de la tarjeta estaba vacío
            
            const id = card.id.replace('news-', '');
            
            // Comprobar duplicados ANTES de añadir al fragmento
            if ($(`#${card.id}`, DOM.grid)) { 
                log(`Skipping duplicate card from pendingNews: ${card.id}`);
                continue; 
            }
            
            // También verificar en noticias de respaldo para evitar duplicados futuros
            const existsInBackup = STATE.backupCards.some(backup => backup.id == id);
            if (existsInBackup) {
                log(`Skipping card already in backup: ${card.id}`);
                continue;
            }
            
            configureNewCard(card, modalEl, id);
            frag.appendChild(card);
            modalEl && DOM.modalsContainer.appendChild(modalEl);
            newIds.push(card);
        }

        if (STATE.order === 'asc') {
            DOM.grid.appendChild(frag);
        } else {
            DOM.grid.prepend(frag);
        }
        
        // Manejar exceso de noticias moviéndolas al respaldo en lugar de eliminarlas
        const allCurrentCards = $$('.news-card-container', DOM.grid);
        if (allCurrentCards.length > MAX_NEWS) {
            const excess = allCurrentCards.length - MAX_NEWS;
            const cardsToMove = STATE.order === 'desc' 
                ? allCurrentCards.slice(-excess) // Últimas en orden desc
                : allCurrentCards.slice(0, excess); // Primeras en orden asc
            
            cardsToMove.forEach(card => {
                const cardId = card.id.replace('news-', '');
                const modal = $(`#modal-${cardId}`);
                
                // Mover al respaldo
                STATE.backupCards.push({
                    id: cardId,
                    card: card.outerHTML
                });
                STATE.backupModals.push(modal?.outerHTML || '');
                
                // Remover del DOM
                card.remove();
                modal?.remove();
                log(`Nueva noticia ${cardId} movida al respaldo para mantener límite de ${MAX_NEWS}`);
            });
        }
        
        if (oldPositions) animateReposition(oldPositions);
        newIds.forEach(el => animateScaleOpacity(el));
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
                    
                    // Si tenemos pocas noticias de respaldo después de cargar nuevas, pedir más
                    if (STATE.backupCards.length < 5) {
                        loadMoreBackupNews();
                    }
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
        const currentPage = parseInt(new URLSearchParams(location.search).get('page') || '1', 10);
        
        // Calcular páginas considerando noticias disponibles (incluyendo las de respaldo)
        let effectiveTotalPages = serverTotalPages ?? Math.ceil(totalItems / itemsPerPage);
        
        // Si estamos en página 1 y tenemos suficientes noticias (incluyendo respaldo) para llenar la página,
        // pero el total es <= 25, entonces solo hay 1 página efectiva
        if (currentPage === 1) {
            const cardsInCurrentPage = $$('.news-card-container', DOM.grid).length;
            const totalVisibleAndBackup = cardsInCurrentPage + STATE.backupCards.length;
            
            if (totalVisibleAndBackup <= MAX_NEWS) {
                effectiveTotalPages = 1;
                log(`Página 2 eliminada: solo ${totalVisibleAndBackup} noticias disponibles (visible + respaldo)`);
            }
        }

        let pagination = $('.pagination');
        const needs = effectiveTotalPages > 1;
        if (!needs && pagination) {
            pagination.remove();
            log('Paginación removida: solo 1 página efectiva');
            return;
        }
        if (!needs) return;

        const tpl = (pg) => `<a href="?page=${pg}">${pg === currentPage ? '···' : (pg < currentPage ? 'Anterior' : 'Siguiente')}</a>`;
        if (!pagination) {
            pagination = document.createElement('div');
            pagination.className = 'pagination';
            DOM.grid.parentNode.insertBefore(pagination, DOM.grid.nextSibling);
        }
        pagination.innerHTML = `${currentPage > 1 ? tpl(currentPage - 1) : ''}
            <span class="active">${currentPage} / ${effectiveTotalPages}</span>
            ${currentPage < effectiveTotalPages ? tpl(currentPage + 1) : ''}`;
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
        
        // Si quedamos sin noticias en la página actual y hay respaldo disponible, cargarlas automáticamente
        const currentPage = parseInt(new URLSearchParams(location.search).get('page') || '1', 10);
        const cardsInPage = $$('.news-card-container', DOM.grid).length;
        let newsMovedFromBackup = 0;
        
        if (cardsInPage < MAX_NEWS && totalCount > cardsInPage && STATE.backupCards.length > 0) {
            // Llenar la página actual con noticias de respaldo
            const needed = Math.min(MAX_NEWS - cardsInPage, STATE.backupCards.length);
            
            for (let i = 0; i < needed; i++) {
                if (STATE.backupCards.length === 0) break;
                
                const backupData = STATE.backupCards.shift();
                const backupModalData = STATE.backupModals.shift();
                
                if (backupData && backupData.card) {
                    const { card: newCard, modal: newModal } = createCardFromHTML(backupData.card, backupModalData);
                    if (newModal) DOM.modalsContainer.appendChild(newModal);
                    
                    if (newCard) {
                        const id = newCard.id.replace('news-', '');
                        // Verificar que no esté duplicada
                        if (!$(`#news-${id}`, DOM.grid)) {
                            configureNewCard(newCard, newModal, id);
                            if (STATE.order === 'asc') {
                                DOM.grid.appendChild(newCard);
                            } else {
                                DOM.grid.appendChild(newCard); // Agregar al final para orden descendente también
                            }
                            animateScaleOpacity(newCard);
                            newsMovedFromBackup++;
                            log(`Auto-cargada noticia de respaldo: ${id}`);
                        }
                    }
                }
            }
            
            // Pedir más noticias de respaldo si quedamos con pocas
            if (STATE.backupCards.length < 5) {
                loadMoreBackupNews();
            }
            
            // Recalcular paginación después de mover noticias del respaldo
            if (newsMovedFromBackup > 0) {
                const newTotalPages = Math.ceil(totalCount / MAX_NEWS);
                updatePagination(newTotalPages);
                log(`Movidas ${newsMovedFromBackup} noticias del respaldo. Nueva paginación: ${newTotalPages} páginas`);
            }
        }
        
        // Si quedamos sin noticias en la página actual, ir a página 1
        if (cardsInPage === 0 && totalCount > 0 && currentPage > 1) {
            const params = new URLSearchParams(location.search);
            params.set('page', '1');
            window.location.href = `?${params.toString()}`;
        }
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
                
                // Recargar respaldo si tenemos pocas noticias después de actualizar feed
                if (STATE.backupCards.length < 5) {
                    loadMoreBackupNews();
                }
            })
            .catch(e => { err('Actualizar feed:', e); alert('Error al actualizar el feed: ' + e.message); })
            .finally(() => { btn.disabled = false; btn.classList.remove('loading'); });
    });

    // Botón deshacer
    DOM.undoBtn?.addEventListener('click', () => {
        const last = STATE.deleteStack.shift();
        if (!last) return;
        serverUndoNews(last)
            .then(data => {
                if (data.status !== 'success') throw new Error(data.message);
                
                const currentCardsCount = $$('.news-card-container', DOM.grid).length;
                
                if (data.html && data.modal) {
                    const { card, modal } = createCardFromHTML(data.html, data.modal);
                    const id = card.id.replace('news-', '');
                    
                    // Si ya tenemos 25 noticias, mover la última al respaldo antes de agregar la nueva
                    if (currentCardsCount >= MAX_NEWS) {
                        const cardsArray = $$('.news-card-container', DOM.grid);
                        const lastCard = STATE.order === 'desc' ? cardsArray[cardsArray.length - 1] : cardsArray[0];
                        
                        if (lastCard) {
                            const lastId = lastCard.id.replace('news-', '');
                            const lastModal = $(`#modal-${lastId}`);
                            
                            // Mover al respaldo
                            STATE.backupCards.unshift({
                                id: lastId,
                                card: lastCard.outerHTML
                            });
                            STATE.backupModals.unshift(lastModal?.outerHTML || '');
                            
                            // Remover del DOM
                            lastCard.remove();
                            lastModal?.remove();
                            log(`Noticia ${lastId} movida al respaldo por undo`);
                        }
                    }
                    
                    // Agregar la noticia restaurada
                    if (STATE.order === 'desc') {
                        DOM.grid.prepend(card);
                    } else {
                        DOM.grid.appendChild(card);
                    }
                    configureNewCard(card, modal, id);
                    modal && DOM.modalsContainer.appendChild(modal);
                    animateScaleOpacity(card);
                    
                    // Actualizar contadores y paginación
                    updateCounters(data.total_news, data.total_pages);
                    
                    log(`Noticia ${id} restaurada. Respaldo actual: ${STATE.backupCards.length} noticias`);
                } else {
                    updateCounters(data.total_news, data.total_pages);
                }
            })
            .catch(e => { err('Deshacer:', e); alert('No se pudo deshacer'); });
    });

    // Botón cambiar orden
    const applyOrder = (order) => {
        STATE.order = order;
        const q = new URLSearchParams(location.search).get('q') || '';
        serverGetPage({page: STATE.currentPage, order: STATE.order, q})
            .then(data => {
                if (data.status !== 'success') throw new Error(data.message);
                DOM.grid.innerHTML = '';
                DOM.modalsContainer.innerHTML = '';
                const frag = document.createDocumentFragment();
                (data.cards || []).forEach(item => {
                    const { card, modal } = createCardFromHTML(item.card, item.modal);
                    const id = card ? card.id.replace('news-', '') : String(item.id);
                    configureNewCard(card, modal, id);
                    frag.appendChild(card);
                    modal && DOM.modalsContainer.appendChild(modal);
                });
                DOM.grid.appendChild(frag);
                STATE.backupCards = data.backup_cards || [];
                STATE.backupModals = (data.backup_cards || []).map(x => x.modal);
                STATE.nextCursor = data.next_cursor || null;
                STATE.backupCursor = data.next_cursor || null; // Usar el mismo cursor para las siguientes cargas
                log(`Inicializadas ${STATE.backupCards.length} noticias de respaldo`);
                updateCounters(data.total_news, data.total_pages);
                updatePagination(data.total_pages);
                const params = new URLSearchParams(location.search);
                params.set('order', STATE.order);
                history.replaceState(null, '', `?${params.toString()}`);
            })
            .catch(e => { err('Cambiar orden:', e); alert('No se pudo cambiar el orden'); });
    };

    const setOrderIcon = () => {
        if (!DOM.orderBtn) return;
        const ascIcon = '<svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-sort-ascending-numbers" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"> <path stroke="none" d="M0 0h24v24H0z" fill="none"/> <path d="M4 15l3 3l3 -3" /> <path d="M7 6v12" /> <path d="M17 3a 2 2 0 0 1 2 2v3a 2 2 0 1 1 -4 0v-3a 2 2 0 0 1 2 -2z" /> <circle cx="17" cy="16" r="2" /> <path d="M19 16v3a 2 2 0 0 1 -2 2h-1.5" /> </svg>';
        const descIcon = '<svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-sort-descending-numbers" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"> <path stroke="none" d="M0 0h24v24H0z" fill="none"/> <path d="M4 15l3 3l3 -3" /> <path d="M7 6v12" /> <path d="M17 14a 2 2 0 0 1 2 2v3a 2 2 0 1 1 -4 0v-3a 2 2 0 0 1 2 -2z" /> <circle cx="17" cy="5" r="2" /> <path d="M19 5v3a 2 2 0 0 1 -2 2h-1.5" /> </svg>';
        DOM.orderBtn.innerHTML = STATE.order === 'asc' ? ascIcon : descIcon;
    };

    DOM.orderBtn?.addEventListener('click', () => {
        const newOrder = STATE.order === 'desc' ? 'asc' : 'desc';
        applyOrder(newOrder);
        STATE.order = newOrder;
        setOrderIcon();
    });

    /* ---------------------------------------------------------------------
     *  Arranque
     * ------------------------------------------------------------------ */
    // Inicializar noticias de respaldo y sincronizar con DB al abrir
    document.addEventListener('DOMContentLoaded', () => {
        initializeBackupCards();
        const q = new URLSearchParams(location.search).get('q') || '';
        serverGetPage({page: STATE.currentPage, order: STATE.order, q})
            .then(data => {
                if (data.status !== 'success') return;
                DOM.grid.innerHTML = '';
                DOM.modalsContainer.innerHTML = '';
                const frag = document.createDocumentFragment();
                (data.cards || []).forEach(item => {
                    const { card, modal } = createCardFromHTML(item.card, item.modal);
                    const id = card ? card.id.replace('news-', '') : String(item.id);
                    configureNewCard(card, modal, id);
                    frag.appendChild(card);
                    modal && DOM.modalsContainer.appendChild(modal);
                });
                DOM.grid.appendChild(frag);
                STATE.backupCards = data.backup_cards || [];
                STATE.backupModals = (data.backup_cards || []).map(x => x.modal);
                STATE.nextCursor = data.next_cursor || null;
                STATE.backupCursor = data.next_cursor || null; // Usar el mismo cursor para las siguientes cargas
                log(`Inicializadas ${STATE.backupCards.length} noticias de respaldo`);
                updateCounters(data.total_news, data.total_pages);
                updatePagination(data.total_pages);
            })
            .catch(e => err('Error al cargar página inicial:', e));
        // Establecer icono inicial según orden actual
        setOrderIcon();
    });
    
    setInterval(checkForNewNews, CHECK_INTERVAL);
    enforceCardLimit(); // Aplicar límite al cargar la página inicialmente
    // updatePagination será llamada por updateCounters en la carga inicial

})();
