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

    const readHiddenIds = () => {
        try {
            const raw = localStorage.getItem(storageKey);
            return raw ? new Set(JSON.parse(raw).map(String)) : new Set();
        } catch (_) {
            return new Set();
        }
    };

    const hiddenIds = readHiddenIds();
    const cards = () => CardUi.cards(grid || document);

    const persistHiddenIds = () => {
        localStorage.setItem(storageKey, JSON.stringify([...hiddenIds]));
    };

    const updateCounter = () => {
        const visibleCards = cards();
        if (counter) counter.textContent = String(visibleCards.length);
        if (emptyState) emptyState.hidden = visibleCards.length !== 0;
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
        }, 220);
    };

    cards().forEach((card) => {
        CardUi.addMobileDeleteButton(card);
        if (hiddenIds.has(String(card.dataset.newsId || ''))) card.remove();
    });
    updateCounter();

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

    grid?.addEventListener('mouseleave', (event) => {
        CardUi.resetFlipState(event.target.closest('.news-card-container'));
    }, true);

    resetButton?.addEventListener('click', () => {
        resetButton.disabled = true;
        localStorage.removeItem(storageKey);
        window.location.reload();
    });
})();
