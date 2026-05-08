(() => {
    'use strict';

    const CardUi = window.NewsCards;
    const grid = document.querySelector('#public-news-grid');
    const counter = document.querySelector('#public-news-counter');
    const emptyState = document.querySelector('#public-news-empty');
    const resetButton = document.querySelector('#public-news-reset-btn');

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

    const resetAllDesktopHoverCards = () => {
        if (CardUi.isMobile()) return;
        cards().forEach(CardUi.resetFlipState);
    };

    const persistHiddenIds = () => {
        localStorage.setItem(storageKey, JSON.stringify([...hiddenIds]));
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
        card.classList.remove('is-hiding');
        CardUi.addMobileDeleteButton(card);
        card.querySelectorAll('.news-image').forEach((image) => {
            image.loading = 'eager';
        });
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
            setTimeout(() => card.classList.remove('inserting'), 450);
        }
    };

    const fetchRefillPage = async (pageNumber) => {
        const response = await fetch(pageUrl(pageNumber), {
            credentials: 'same-origin',
            headers: {'X-Requested-With': 'XMLHttpRequest'},
        });
        if (!response.ok) return;
        const html = await response.text();
        const doc = new DOMParser().parseFromString(html, 'text/html');
        doc.querySelectorAll('#public-news-grid .news-card-container').forEach((card) => {
            const id = getCardId(card);
            if (id && !hiddenIds.has(id) && !currentCardIds().has(id)) refillQueue.push(card);
        });
    };

    const refillCards = async () => {
        if (!grid || refillInFlight || cards().length >= pageSize) return;
        refillInFlight = true;
        try {
            drainRefillQueue();
            while (cards().length < pageSize && nextRefillPage <= totalPages) {
                await fetchRefillPage(nextRefillPage);
                nextRefillPage += 1;
                drainRefillQueue();
            }
        } catch (error) {
            console.warn('No se pudieron cargar tarjetas adicionales.', error);
        } finally {
            refillInFlight = false;
            updateCounter();
        }
    };

    const removeCard = (card, id) => {
        if (!card || !id) return;
        const oldPositions = CardUi.isMobile() ? null : CardUi.capturePositions(grid || document);
        hiddenIds.add(String(id));
        persistHiddenIds();
        card.classList.add('is-hiding');
        setTimeout(() => {
            card.remove();
            if (oldPositions) CardUi.animateReposition(oldPositions, {excludedIds: [card.id]});
            updateCounter();
            refillCards();
        }, 220);
    };

    cards().forEach((card) => {
        CardUi.addMobileDeleteButton(card);
        if (hiddenIds.has(String(card.dataset.newsId || ''))) card.remove();
    });
    updateCounter();
    refillCards();

    grid?.addEventListener('click', (event) => {
        const button = event.target.closest('.delete-btn, .mobile-delete-btn');
        if (!button) return;
        event.preventDefault();
        event.stopPropagation();
        const id = String(button.dataset.id || '');
        removeCard(button.closest('.news-card-container'), id);
    });

    grid?.addEventListener('mousemove', (event) => {
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
    });

    grid?.addEventListener('pointerout', (event) => {
        const container = event.target.closest('.news-card-container');
        if (!container || (event.relatedTarget && container.contains(event.relatedTarget))) return;
        if (CardUi.isPointerWithinCardBounds(container, event)) return;
        CardUi.resetFlipState(container);
    });

    document.addEventListener('mousemove', (event) => {
        const container = event.target.closest?.('.news-card-container');
        cards().forEach((card) => {
            if (card !== container) CardUi.resetFlipState(card);
        });
    }, true);

    document.addEventListener('mouseleave', resetAllDesktopHoverCards);
    window.addEventListener('blur', resetAllDesktopHoverCards);

    resetButton?.addEventListener('click', () => {
        resetButton.disabled = true;
        localStorage.removeItem(storageKey);
        window.location.reload();
    });
})();
