(() => {
    'use strict';

    const CardUi = window.NewsCards;
    const grid = document.querySelector('#public-news-grid');
    const counter = document.querySelector('#public-news-counter');
    const emptyState = document.querySelector('#public-news-empty');
    const resetButton = document.querySelector('#public-news-reset-btn');
    const retryButton = document.querySelector('#public-news-retry-btn');
    const loadError = document.querySelector('#public-news-load-error');

    let storageKey = 'public-news-hidden';
    try {
        const raw = document.querySelector('#public-news-storage-key')?.textContent;
        if (raw) storageKey = JSON.parse(raw);
    } catch (_) {
        storageKey = 'public-news-hidden';
    }

    const readPageData = () => {
        try {
            const raw = document.querySelector('#public-news-page-data')?.textContent;
            return raw ? JSON.parse(raw) : {};
        } catch (_) {
            return {};
        }
    };

    const readHiddenIds = () => {
        try {
            const raw = localStorage.getItem(storageKey);
            return raw ? new Set(JSON.parse(raw).map(String)) : new Set();
        } catch (_) {
            return new Set();
        }
    };

    const hiddenIds = readHiddenIds();
    const totalNews = Number.parseInt(
        counter?.dataset.totalNews || counter?.textContent || '0',
        10
    ) || 0;
    const cards = () => CardUi.cards(grid || document);
    const pageData = readPageData();
    const pageSize = Number.parseInt(pageData.page_size || '0', 10) || cards().length || 25;
    let nextRefillPage = (Number.parseInt(pageData.current_page || '1', 10) || 1) + 1;
    const totalPages = Number.parseInt(pageData.total_pages || '1', 10) || 1;
    const refillQueue = [];
    let refillInFlight = false;
    const MOBILE_REMOVE_MS = 320;
    const INSERT_MS = {mobile: 380, desktop: 600};
    const mobileTapState = {
        startX: 0,
        startY: 0,
        startScrollY: 0,
        startedAt: 0,
        moved: false,
        touchActive: false,
        selectionActiveAtStart: false,
        suppressCompatibilityClick: false,
        scrolling: false,
        scrollEndTimer: null,
    };

    const resetAllDesktopHoverCards = () => {
        if (CardUi.isMobile()) return;
        cards().forEach(CardUi.resetFlipState);
    };

    const persistHiddenIds = () => {
        try {
            localStorage.setItem(storageKey, JSON.stringify([...hiddenIds]));
        } catch (_) {
            // Si el navegador bloquea el almacenamiento, ocultar sigue
            // funcionando durante esta sesión de la página.
        }
    };

    const updateCounter = () => {
        const visibleCards = cards();
        if (counter) counter.textContent = String(Math.max(totalNews - hiddenIds.size, 0));
        if (emptyState) emptyState.hidden = visibleCards.length !== 0;
    };

    const getCardId = (card) => String(card?.dataset.newsId || '').trim();
    const currentCardIds = () => new Set(cards().map(getCardId).filter(Boolean));

    const pageUrl = (pageNumber) => {
        const url = new URL(window.location.href);
        url.searchParams.set('page', String(pageNumber));
        return url.toString();
    };

    const prepareIncomingCard = (card) => {
        CardUi.addMobileDeleteButton(card);
        return card;
    };

    const drainRefillQueue = () => {
        if (!grid) return;
        while (cards().length < pageSize && refillQueue.length) {
            const card = refillQueue.shift();
            const id = getCardId(card);
            if (!id || hiddenIds.has(id) || currentCardIds().has(id)) continue;
            card.classList.add('inserting');
            grid.appendChild(prepareIncomingCard(card));
            CardUi.bindImageFallbacks(card);
            // El texto se mide despues de retirar la capa de animacion, ya con
            // la altura definitiva. En movil se libera antes para ahorrar GPU.
            setTimeout(() => {
                card.classList.remove('inserting');
                CardUi.fitCardText?.(card);
            }, CardUi.isMobile() ? INSERT_MS.mobile : INSERT_MS.desktop);
        }
    };

    const fetchRefillPage = async (pageNumber) => {
        const response = await fetch(pageUrl(pageNumber), {
            credentials: 'same-origin',
            headers: {'X-Requested-With': 'XMLHttpRequest'},
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const html = await response.text();
        const doc = new DOMParser().parseFromString(html, 'text/html');
        const loadedIds = currentCardIds();
        doc.querySelectorAll('#public-news-grid .news-card-container').forEach((card) => {
            const id = getCardId(card);
            if (id && !hiddenIds.has(id) && !loadedIds.has(id)) {
                refillQueue.push(card);
                loadedIds.add(id);
            }
        });
    };

    const refillCards = async () => {
        if (!grid || refillInFlight || cards().length >= pageSize) return;
        refillInFlight = true;
        if (loadError) loadError.hidden = true;
        if (retryButton) retryButton.disabled = true;
        try {
            drainRefillQueue();
            while (cards().length < pageSize && nextRefillPage <= totalPages) {
                await fetchRefillPage(nextRefillPage);
                nextRefillPage += 1;
                drainRefillQueue();
            }
        } catch (error) {
            console.warn('No se pudieron cargar tarjetas adicionales.', error);
            if (loadError) loadError.hidden = false;
        } finally {
            refillInFlight = false;
            if (retryButton) retryButton.disabled = false;
            updateCounter();
        }
    };

    const removeCard = (card, id) => {
        if (!card || !id) return;
        const mobile = CardUi.isMobile();
        const oldPositions = CardUi.capturePositions(grid || document);
        const rect = card.getBoundingClientRect();
        const exitClone = card.cloneNode(true);
        exitClone.id = '';
        exitClone.removeAttribute('data-news-id');
        Object.assign(exitClone.style, {
            position: 'fixed',
            left: `${rect.left}px`,
            top: `${rect.top}px`,
            width: `${rect.width}px`,
            height: `${rect.height}px`,
            margin: '0',
            pointerEvents: 'none',
            zIndex: '1000',
            transformOrigin: 'center center',
            willChange: 'transform, opacity',
            transition: `opacity 0.2s ease, transform ${mobile ? 300 : 200}ms cubic-bezier(0.22, 0.61, 0.36, 1)`,
        });
        hiddenIds.add(String(id));
        persistHiddenIds();
        card.remove();
        document.body.appendChild(exitClone);
        CardUi.animateReposition(oldPositions, {
            excludedIds: [card.id],
            allowMobile: true,
            viewportOnly: mobile,
        });
        requestAnimationFrame(() => {
            exitClone.style.opacity = '0';
            exitClone.style.transform = 'scale(0.94)';
        });
        setTimeout(() => {
            exitClone.remove();
            updateCounter();
            refillCards();
        }, mobile ? MOBILE_REMOVE_MS : 220);
    };

    cards().forEach((card) => {
        CardUi.addMobileDeleteButton(card);
        if (hiddenIds.has(String(card.dataset.newsId || ''))) card.remove();
    });
    retryButton?.addEventListener('click', refillCards);
    updateCounter();
    refillCards();

    const toggleCardFromTapTarget = (target) => {
        const container = target.closest('.news-card-container');
        if (!container || CardUi.isCardActionTarget(target)) return false;
        if (!CardUi.isValidMobileTap(mobileTapState, container)) return false;

        const card = container.querySelector('.news-card');
        if (!card) return false;

        cards().forEach((item) => {
            if (item !== container) CardUi.resetFlipState(item);
        });
        card.classList.toggle('is-flipped', !card.classList.contains('is-flipped'));
        card.classList.remove('image-hover', 'delete-hover');
        return true;
    };

    grid?.addEventListener('click', (event) => {
        const button = event.target.closest('.delete-btn, .mobile-delete-btn');
        if (button) {
            event.preventDefault();
            event.stopPropagation();
            const id = String(button.dataset.id || '');
            removeCard(button.closest('.news-card-container'), id);
            return;
        }

        if (!CardUi.isMobile()) return;

        if (mobileTapState.scrolling) return;
        if (mobileTapState.suppressCompatibilityClick) {
            mobileTapState.suppressCompatibilityClick = false;
            return;
        }
        toggleCardFromTapTarget(event.target);
    });

    grid?.addEventListener('pointerdown', (event) => {
        if (!CardUi.isMobile() || event.pointerType !== 'touch') return;
        mobileTapState.startX = event.clientX;
        mobileTapState.startY = event.clientY;
        mobileTapState.startScrollY = window.scrollY;
        mobileTapState.startedAt = Date.now();
        mobileTapState.moved = false;
        mobileTapState.touchActive = true;
        mobileTapState.selectionActiveAtStart = CardUi.hasTextSelectionWithin(
            event.target.closest('.news-card-container')
        );
    }, {passive: true});

    grid?.addEventListener('pointermove', (event) => {
        if (!CardUi.isMobile() || event.pointerType !== 'touch') return;
        const dx = Math.abs(event.clientX - mobileTapState.startX);
        const dy = Math.abs(event.clientY - mobileTapState.startY);
        const scrolled = Math.abs(window.scrollY - mobileTapState.startScrollY);
        if (dx > 8 || dy > 8 || scrolled > 2) mobileTapState.moved = true;
    }, {passive: true});

    grid?.addEventListener('pointerup', (event) => {
        if (!CardUi.isMobile() || event.pointerType !== 'touch') return;
        mobileTapState.touchActive = false;
        const dx = Math.abs(event.clientX - mobileTapState.startX);
        const dy = Math.abs(event.clientY - mobileTapState.startY);
        const scrolled = Math.abs(window.scrollY - mobileTapState.startScrollY);
        if (dx > 8 || dy > 8 || scrolled > 2) mobileTapState.moved = true;
        if (CardUi.isCardActionTarget(event.target)) return;

        // Todo pointerup táctil sobre la superficie de la tarjeta ya fue
        // clasificado aquí, incluso si era scroll, pulsación larga o selección.
        mobileTapState.suppressCompatibilityClick = true;
        window.setTimeout(() => {
            mobileTapState.suppressCompatibilityClick = false;
        }, 500);
        toggleCardFromTapTarget(event.target);
    }, {passive: true});

    grid?.addEventListener('pointercancel', (event) => {
        if (!CardUi.isMobile() || event.pointerType !== 'touch') return;
        mobileTapState.moved = true;
        mobileTapState.touchActive = false;
    }, {passive: true});

    window.addEventListener('scroll', () => {
        if (!CardUi.isMobile()) return;
        if (mobileTapState.touchActive) mobileTapState.moved = true;
        mobileTapState.scrolling = true;
        if (mobileTapState.scrollEndTimer) {
            window.clearTimeout(mobileTapState.scrollEndTimer);
        }
        mobileTapState.scrollEndTimer = window.setTimeout(() => {
            mobileTapState.scrolling = false;
            mobileTapState.scrollEndTimer = null;
        }, 160);
    }, {passive: true});

    const updateDesktopHover = (event) => {
        // Instagram y la emulación táctil pueden emitir mousemove antes del
        // click compatible. En móvil el giro pertenece únicamente al toque.
        if (CardUi.isMobile()) return;
        const container = event.target.closest('.news-card-container');
        if (!container) return;
        const card = container.querySelector('.news-card');
        if (!card || card.classList.contains('is-flipped')) return;
        if (!CardUi.isPointerWithinCardBounds(container, event)) return;

        const overMediaZone = CardUi.isPointerInProtectedMediaZone(container, event);
        const overDeleteButton = !!event.target.closest('.mobile-delete-btn');
        const shouldFlip = !overMediaZone && !overDeleteButton;

        card.classList.toggle('is-flipped', shouldFlip);
        card.classList.toggle('image-hover', overMediaZone);
        card.classList.toggle('delete-hover', overDeleteButton);
    };

    grid?.addEventListener('pointerout', (event) => {
        if (CardUi.isMobile()) return;
        const container = event.target.closest('.news-card-container');
        if (!container || (event.relatedTarget && container.contains(event.relatedTarget))) return;
        if (CardUi.isPointerWithinCardBounds(container, event)) return;
        CardUi.resetFlipState(container);
    });

    let hoverFrame = null;
    let lastHoverEvent = null;
    document.addEventListener('mousemove', (event) => {
        if (CardUi.isMobile()) return;
        lastHoverEvent = event;
        if (hoverFrame !== null) return;
        hoverFrame = requestAnimationFrame(() => {
            hoverFrame = null;
            const container = lastHoverEvent.target.closest?.('.news-card-container');
            CardUi.activeCards(grid || document).forEach((card) => {
                if (card !== container) CardUi.resetFlipState(card);
            });
            if (container?.isConnected) updateDesktopHover(lastHoverEvent);
        });
    }, {capture: true, passive: true});
    const cancelHoverFrame = () => {
        cancelAnimationFrame(hoverFrame);
        hoverFrame = null;
    };
    document.addEventListener('mouseleave', cancelHoverFrame);
    window.addEventListener('blur', cancelHoverFrame);

    document.addEventListener('mouseleave', resetAllDesktopHoverCards);
    window.addEventListener('blur', resetAllDesktopHoverCards);

    resetButton?.addEventListener('click', () => {
        resetButton.disabled = true;
        try {
            localStorage.removeItem(storageKey);
        } catch (_) {
            resetButton.disabled = false;
            return;
        }
        window.location.reload();
    });
})();
