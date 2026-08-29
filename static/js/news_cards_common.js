(() => {
    'use strict';

    const isMobile = () => window.innerWidth <= 767;
    const cards = (root = document) => Array.from(root.querySelectorAll('.news-card-container'));

    const capturePositions = (root = document) => new Map(
        cards(root).map((card) => [card, card.getBoundingClientRect()])
    );

    const animateReposition = (oldPositions, {
        excludedIds = [],
        onSettled = null,
        allowMobile = false,
        viewportOnly = false,
    } = {}) => {
        if ((isMobile() && !allowMobile) || !oldPositions?.size) return;
        if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
            if (typeof onSettled === 'function') onSettled();
            return;
        }

        requestAnimationFrame(() => {
            let hasMovingCards = false;
            oldPositions.forEach((rect, card) => {
                if (!document.body.contains(card) || excludedIds.includes(card.id)) return;

                const newRect = card.getBoundingClientRect();
                if (viewportOnly) {
                    const buffer = Math.min(window.innerHeight * 0.5, 360);
                    const outsideBefore = rect.bottom < -buffer || rect.top > window.innerHeight + buffer;
                    const outsideAfter = newRect.bottom < -buffer || newRect.top > window.innerHeight + buffer;
                    if (outsideBefore && outsideAfter) return;
                }
                const dx = rect.left - newRect.left;
                const dy = rect.top - newRect.top;
                if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) return;

                hasMovingCards = true;
                card.style.transform = `translate3d(${dx}px,${dy}px,0)`;
                card.style.transition = 'none';
                card.style.willChange = 'transform';

                requestAnimationFrame(() => {
                    const duration = isMobile() ? 300 : 400;
                    let settled = false;
                    const finish = () => {
                        if (settled) return;
                        settled = true;
                        card.style.transition = '';
                        card.style.willChange = '';
                        card.removeEventListener('transitionend', onTransitionEnd);
                        if (typeof onSettled === 'function') onSettled();
                    };
                    const onTransitionEnd = (event) => {
                        if (event.target === card && event.propertyName === 'transform') finish();
                    };
                    card.style.transition = `transform ${duration}ms cubic-bezier(0.22, 0.61, 0.36, 1)`;
                    card.style.transform = '';
                    card.addEventListener('transitionend', onTransitionEnd);
                    setTimeout(finish, duration + 80);
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

    const hasTextSelectionWithin = (container) => {
        const selection = window.getSelection?.();
        if (!selection || selection.isCollapsed || selection.rangeCount === 0) return false;
        if (!container) return true;

        const isNodeWithin = (node) => {
            if (!node) return false;
            const element = node.nodeType === 3 ? node.parentElement : node;
            return !!element && container.contains(element);
        };

        if (isNodeWithin(selection.anchorNode) || isNodeWithin(selection.focusNode)) return true;

        try {
            return selection.getRangeAt(0).intersectsNode(container);
        } catch (_) {
            return false;
        }
    };

    const isValidMobileTap = (state, container, {maxDuration = 500} = {}) => {
        if (!state || state.moved || state.selectionActiveAtStart) return false;
        if (state.startedAt && (Date.now() - state.startedAt) > maxDuration) return false;
        return !hasTextSelectionWithin(container);
    };

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
            if (image.dataset.newsCardBound === 'true') return;
            image.dataset.newsCardBound = 'true';
            image.addEventListener('load', () => fitCardText(image.closest('.news-card-container') || document), {once: true});
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
            const container = front.closest('.news-card-container');
            // Una tarjeta que entra o sale todavia no tiene su altura real. Si
            // se mide durante el colapso, el titulo queda limitado a una o dos
            // lineas incluso despues de recuperar su tamano normal.
            if (container?.classList.contains('is-inserting') ||
                container?.classList.contains('inserting') ||
                container?.classList.contains('collapsing')) return;

            const title = front.querySelector('.news-title');
            if (!title) return;

            title.classList.remove('is-title-clamped');
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

    const fitDescriptionToCard = (scope = document) => {
        scope.querySelectorAll?.('.news-description').forEach((description) => {
            const container = description.closest('.news-card-container');
            if (container?.classList.contains('is-inserting') ||
                container?.classList.contains('inserting') ||
                container?.classList.contains('collapsing')) return;

            description.classList.remove('is-description-compact', 'is-description-tight');
            if (isMobile() || description.scrollHeight <= description.clientHeight + 1) return;

            description.classList.add('is-description-compact');
            if (description.scrollHeight <= description.clientHeight + 1) return;

            description.classList.add('is-description-tight');
        });
    };

    const fitCardText = (scope = document) => {
        fitTitleToSummary(scope);
        fitDescriptionToCard(scope);
    };

    document.addEventListener('error', (event) => {
        if (event.target?.matches?.('.news-image')) useFallbackImage(event.target);
    }, true);

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            bindImageFallbacks();
            fitCardText();
        });
    } else {
        bindImageFallbacks();
        fitCardText();
    }

    // Coalescar pasadas de ajuste de títulos: cada pasada fuerza reflows por
    // tarjeta, así que múltiples llamadas seguidas (load + resize) se agrupan
    // en una sola. Las imágenes que cargan tarde ya re-ajustan su propia
    // tarjeta vía bindImageFallbacks.
    let cardTextFitTimer = null;
    const scheduleCardTextFit = () => {
        if (cardTextFitTimer) clearTimeout(cardTextFitTimer);
        cardTextFitTimer = window.setTimeout(() => {
            cardTextFitTimer = null;
            fitCardText();
        }, 120);
    };

    window.addEventListener('load', scheduleCardTextFit);
    window.addEventListener('resize', scheduleCardTextFit);

    window.NewsCards = {
        isMobile,
        cards,
        capturePositions,
        animateReposition,
        addMobileDeleteButton,
        isPointerInProtectedMediaZone,
        isPointerWithinCardBounds,
        isCardActionTarget,
        hasTextSelectionWithin,
        isValidMobileTap,
        resetFlipState,
        bindImageFallbacks,
        fitTitleToSummary,
        fitDescriptionToCard,
        fitCardText,
    };
})();
