(() => {
    'use strict';

    const isMobile = () => window.innerWidth <= 767;
    const cards = (root = document) => Array.from(root.querySelectorAll('.news-card-container'));

    const capturePositions = (root = document) => new Map(
        cards(root).map((card) => [card, card.getBoundingClientRect()])
    );

    const animateReposition = (oldPositions, {excludedIds = [], onSettled = null} = {}) => {
        if (isMobile() || !oldPositions?.size) return;

        requestAnimationFrame(() => {
            let hasMovingCards = false;
            oldPositions.forEach((rect, card) => {
                if (!document.body.contains(card) || excludedIds.includes(card.id)) return;

                const newRect = card.getBoundingClientRect();
                const dx = rect.left - newRect.left;
                const dy = rect.top - newRect.top;
                if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) return;

                hasMovingCards = true;
                card.style.transform = `translate(${dx}px,${dy}px)`;
                card.style.transition = 'none';

                requestAnimationFrame(() => {
                    card.style.transition = 'transform 0.4s ease-out';
                    card.style.transform = '';
                    card.addEventListener('transitionend', () => {
                        card.style.transition = '';
                        if (typeof onSettled === 'function') onSettled();
                    }, {once: true});
                });
            });

            if (hasMovingCards && typeof onSettled === 'function') {
                requestAnimationFrame(onSettled);
                setTimeout(onSettled, 430);
            }
        });
    };

    const addMobileDeleteButton = (container, id) => {
        const mediaZone = container?.querySelector('.card-front .news-media-zone');
        if (!mediaZone || mediaZone.querySelector('.mobile-delete-btn') || !container.querySelector('.delete-btn')) return null;

        const button = document.createElement('button');
        button.className = 'mobile-delete-btn';
        button.type = 'button';
        button.dataset.id = id || String(container.dataset.newsId || '').trim();
        mediaZone.appendChild(button);
        return button;
    };

    const isPointerInProtectedMediaZone = (container, pointerEvent) => {
        if (!container || !pointerEvent) return false;
        const mediaZone = container.querySelector('.news-media-zone');
        if (!mediaZone) return false;

        const containerRect = container.getBoundingClientRect();
        const protectedHeight = mediaZone.offsetHeight;
        const bleed = 3;
        const x = pointerEvent.clientX;
        const y = pointerEvent.clientY;

        return x >= (containerRect.left - bleed) &&
            x <= (containerRect.right + bleed) &&
            y >= (containerRect.top - bleed) &&
            y <= (containerRect.top + protectedHeight + bleed);
    };

    const isPointerWithinCardBounds = (container, pointerEvent) => {
        if (!container || !pointerEvent) return false;
        const rect = container.getBoundingClientRect();
        const bleed = 1;
        const x = pointerEvent.clientX;
        const y = pointerEvent.clientY;

        return x >= (rect.left - bleed) &&
            x <= (rect.right + bleed) &&
            y >= (rect.top - bleed) &&
            y <= (rect.bottom + bleed);
    };

    const isCardActionTarget = (target) => !!target?.closest?.([
        'a',
        'button',
        'input',
        'textarea',
        'select',
        '[role="button"]',
        '.news-link',
        '.news-links',
        '.mobile-delete-btn',
    ].join(', '));

    const resetFlipState = (container) => {
        const card = container?.querySelector('.news-card');
        if (!card) return;
        if (card._flipUnlockTimer) {
            clearTimeout(card._flipUnlockTimer);
            card._flipUnlockTimer = null;
        }
        card.classList.remove('is-flipped', 'image-hover', 'delete-hover');
        container.classList.remove('pointer-delete-hover');
        delete card.dataset.hoverMode;
        delete card.dataset.flipLocked;
    };

    window.NewsCards = {
        isMobile,
        cards,
        capturePositions,
        animateReposition,
        addMobileDeleteButton,
        isPointerInProtectedMediaZone,
        isPointerWithinCardBounds,
        isCardActionTarget,
        resetFlipState,
    };
})();
