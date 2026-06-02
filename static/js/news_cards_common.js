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

    const useFallbackImage = (image) => {
        const fallbackSrc = image?.dataset?.fallbackSrc;
        if (!image || !fallbackSrc || image.dataset.fallbackApplied === 'true') return;
        image.dataset.fallbackApplied = 'true';
        image.src = fallbackSrc;
    };

    const bindImageFallbacks = (root = document) => {
        root.querySelectorAll?.('.news-image').forEach((image) => {
            if (!image.isConnected) return;
            if (image.complete && image.naturalWidth === 0) useFallbackImage(image);
            image.addEventListener('load', () => fitTitleToSummary(image.closest('.news-card-container') || document), {once: true});
        });
    };

    const getLineHeight = (element) => {
        if (!element) return 0;
        const style = window.getComputedStyle(element);
        const lineHeight = Number.parseFloat(style.lineHeight);
        if (!Number.isNaN(lineHeight)) return lineHeight;
        const fontSize = Number.parseFloat(style.fontSize) || 16;
        return fontSize * 1.2;
    };

    const fitTitleToSummary = (scope = document) => {
        scope.querySelectorAll?.('.card-front').forEach((front) => {
            const title = front.querySelector('.news-title');
            if (!title) return;

            title.classList.remove('is-title-overflow-4', 'is-title-clamped');
            title.style.removeProperty('--title-lines');

            const lineHeight = getLineHeight(title);
            if (!lineHeight) return;

            if (front.scrollHeight <= front.clientHeight + 1) return;

            const naturalTitleLines = Math.max(1, Math.ceil(title.scrollHeight / lineHeight));
            for (let titleLines = naturalTitleLines - 1; titleLines >= 1; titleLines -= 1) {
                title.style.setProperty('--title-lines', String(titleLines));
                title.classList.add('is-title-clamped');
                if (front.scrollHeight <= front.clientHeight + 1) break;
            }
        });
    };

    document.addEventListener('error', (event) => {
        if (event.target?.matches?.('.news-image')) useFallbackImage(event.target);
    }, true);

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            bindImageFallbacks();
            fitTitleToSummary();
        });
    } else {
        bindImageFallbacks();
        fitTitleToSummary();
    }

    const scheduleTitleFit = () => {
        fitTitleToSummary();
        window.setTimeout(fitTitleToSummary, 80);
        window.setTimeout(fitTitleToSummary, 240);
    };

    window.addEventListener('load', scheduleTitleFit);
    window.addEventListener('resize', scheduleTitleFit);

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
        bindImageFallbacks,
        fitTitleToSummary,
    };
})();
