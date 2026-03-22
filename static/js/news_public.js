(() => {
    'use strict';

    const grid = document.querySelector('#public-news-grid');
    const counter = document.querySelector('#public-news-counter');
    const emptyState = document.querySelector('#public-news-empty');
    const resetButton = document.querySelector('#public-news-reset-btn');
    const isMobile = () => window.innerWidth <= 767;

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
            if (!raw) return new Set();
            return new Set(JSON.parse(raw).map((value) => String(value)));
        } catch (_) {
            return new Set();
        }
    };

    const hiddenIds = readHiddenIds();

    const persistHiddenIds = () => {
        localStorage.setItem(storageKey, JSON.stringify([...hiddenIds]));
    };

    const cards = () => Array.from(document.querySelectorAll('.news-card-container'));
    const capturePositions = () => new Map(cards().map((card) => [card, card.getBoundingClientRect()]));

    const animateReposition = (oldPositions, excludedIds = []) => {
        if (isMobile() || !oldPositions.size) return;

        window.requestAnimationFrame(() => {
            oldPositions.forEach((rect, card) => {
                if (!document.body.contains(card) || excludedIds.includes(card.id)) return;

                const newRect = card.getBoundingClientRect();
                const dx = rect.left - newRect.left;
                const dy = rect.top - newRect.top;
                if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) return;

                card.style.transform = `translate(${dx}px, ${dy}px)`;
                card.style.transition = 'none';

                window.requestAnimationFrame(() => {
                    card.style.transition = 'transform 0.4s ease-out';
                    card.style.transform = '';
                    card.addEventListener('transitionend', () => {
                        card.style.transition = '';
                    }, {once: true});
                });
            });
        });
    };

    const configureCard = (container) => {
        if (!container) return;
        const front = container.querySelector('.card-front');
        if (!front || front.querySelector('.mobile-delete-btn') || !container.querySelector('.delete-btn')) return;

        const id = String(container.dataset.newsId || '').trim();
        const button = document.createElement('button');
        button.className = 'mobile-delete-btn';
        button.type = 'button';
        button.dataset.id = id;
        front.appendChild(button);
    };

    const updateCounter = () => {
        const visibleCards = cards();
        if (counter) counter.textContent = String(visibleCards.length);
        if (emptyState) emptyState.hidden = visibleCards.length !== 0;
    };

    const removeCard = (card, id) => {
        if (!card || !id) return;
        const oldPositions = isMobile() ? null : capturePositions();
        hiddenIds.add(String(id));
        persistHiddenIds();
        card.classList.add('is-hiding');
        window.setTimeout(() => {
            card.remove();
            if (oldPositions) animateReposition(oldPositions, [card.id]);
            updateCounter();
        }, 220);
    };

    cards().forEach((card) => {
        configureCard(card);
        const id = String(card.dataset.newsId || '');
        if (hiddenIds.has(id)) {
            card.remove();
        }
    });
    updateCounter();

    grid?.addEventListener('click', (event) => {
        const button = event.target.closest('.delete-btn, .mobile-delete-btn');
        if (!button) return;
        event.preventDefault();
        event.stopPropagation();
        const id = String(button.dataset.id || '');
        const card = button.closest('.news-card-container');
        removeCard(card, id);
    });

    grid?.addEventListener('mouseover', (event) => {
        const container = event.target.closest('.news-card-container');
        if (!container) return;
        const cardElement = container.querySelector('.news-card');
        if (!cardElement) return;

        const deleteButton = event.target.closest('.mobile-delete-btn');
        if (deleteButton && !deleteButton.contains(event.relatedTarget)) {
            cardElement.classList.add('delete-hover');
        }

        const image = event.target.closest('.news-image');
        if (image && !image.contains(event.relatedTarget)) {
            cardElement.classList.add('image-hover');
        }
    });

    grid?.addEventListener('mouseout', (event) => {
        const container = event.target.closest('.news-card-container');
        if (!container) return;
        const cardElement = container.querySelector('.news-card');
        if (!cardElement) return;

        const deleteButton = event.target.closest('.mobile-delete-btn');
        if (deleteButton && !deleteButton.contains(event.relatedTarget)) {
            cardElement.classList.remove('delete-hover');
        }

        const image = event.target.closest('.news-image');
        if (image && !image.contains(event.relatedTarget)) {
            cardElement.classList.remove('image-hover');
        }
    });

    resetButton?.addEventListener('click', () => {
        localStorage.removeItem(storageKey);
        window.location.reload();
    });
})();
