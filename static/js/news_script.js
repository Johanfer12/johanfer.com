(() => {
    'use strict';

    /* ---------------------------------------------------------------------
     *  Constantes y estado global ligero
     * ------------------------------------------------------------------ */
    const SELECTORS = {
        grid: '.news-grid',
        total: '.total',
        counter: '.header-counter',
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
        deleteStack: [],
        order: new URLSearchParams(location.search).get('order') || 'desc',
        currentPage: parseInt(new URLSearchParams(location.search).get('page') || '1', 10),
        nextCursor: null,
        loadingMoreBackup: false, // Flag para evitar múltiples peticiones
        backupCursor: null, // Cursor para las siguientes noticias de respaldo
        deletingNews: new Set(), // IDs de noticias siendo eliminadas
        syncingFromDb: false, // evita refrescos simultaneos al recuperar foco/conexion
        lastDbSyncAt: 0, // timestamp del ultimo sync fuerte con DB
    };

    /* ---------------------------------------------------------------------
     *  Utilidades genéricas
     * ------------------------------------------------------------------ */
    const log = (...args) => console.log('[news]', ...args);
    const err = (...args) => console.error('[news]', ...args);
    const SHARE_ICON_HTML = '<svg class="share-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 483 483" aria-hidden="true"><path fill="currentColor" d="M395.72,0c-48.204,0-87.281,39.078-87.281,87.281c0,2.036,0.164,4.03,0.309,6.029l-161.233,75.674 c-15.668-14.971-36.852-24.215-60.231-24.215c-48.204,0.001-87.282,39.079-87.282,87.282c0,48.204,39.078,87.281,87.281,87.281 c15.206,0,29.501-3.907,41.948-10.741l69.789,58.806c-3.056,8.896-4.789,18.396-4.789,28.322c0,48.204,39.078,87.281,87.281,87.281 c48.205,0,87.281-39.078,87.281-87.281s-39.077-87.281-87.281-87.281c-15.205,0-29.5,3.908-41.949,10.74l-69.788-58.805 c3.057-8.891,4.789-18.396,4.789-28.322c0-2.035-0.164-4.024-0.308-6.029l161.232-75.674c15.668,14.971,36.852,24.215,60.23,24.215 c48.203,0,87.281-39.078,87.281-87.281C482.999,39.079,443.923,0,395.72,0z"/></svg>';
    const SHARE_CHECK_HTML = '<svg class="share-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M20.285 6.709a1 1 0 0 1 .006 1.414l-9.3 9.4a1 1 0 0 1-1.421.005L3.71 11.72a1 1 0 1 1 1.414-1.414l5.146 5.146 8.593-8.68a1 1 0 0 1 1.422-.063z"/></svg>';

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

    const normalizeText = (value) => (value || '').replace(/\s+/g, ' ').trim();

    const buildShareCardData = (container) => {
        const front = container?.querySelector('.card-front');
        const back = container?.querySelector('.card-back');
        const header = normalizeText(front?.querySelector('.meta-info')?.textContent) || 'Noticia';
        const title = normalizeText(front?.querySelector('.news-title')?.textContent) || 'Sin titulo';
        const summary = normalizeText(back?.querySelector('.news-description')?.textContent) || 'Sin resumen disponible';
        const imageEl = front?.querySelector('.news-image');
        const imageUrl = imageEl?.currentSrc || imageEl?.src || '';
        return { header, title, summary, imageUrl };
    };

    const wrapText = (ctx, text, maxWidth, maxLines) => {
        const words = (text || '').split(' ');
        const lines = [];
        let current = '';

        for (const word of words) {
            const candidate = current ? `${current} ${word}` : word;
            if (ctx.measureText(candidate).width <= maxWidth) {
                current = candidate;
                continue;
            }
            if (current) lines.push(current);
            current = word;
            if (lines.length >= maxLines) break;
        }
        if (current && lines.length < maxLines) lines.push(current);

        if (lines.length === maxLines) {
            const last = lines[maxLines - 1];
            if (ctx.measureText(last).width > maxWidth) {
                let trimmed = last;
                while (trimmed.length > 1 && ctx.measureText(`${trimmed}...`).width > maxWidth) {
                    trimmed = trimmed.slice(0, -1);
                }
                lines[maxLines - 1] = `${trimmed}...`;
            } else if (words.join(' ') !== lines.join(' ')) {
                let trimmed = last;
                while (trimmed.length > 1 && ctx.measureText(`${trimmed}...`).width > maxWidth) {
                    trimmed = trimmed.slice(0, -1);
                }
                lines[maxLines - 1] = `${trimmed}...`;
            }
        }
        return lines;
    };

    const roundRect = (ctx, x, y, width, height, radius) => {
        const r = Math.min(radius, width / 2, height / 2);
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.lineTo(x + width - r, y);
        ctx.quadraticCurveTo(x + width, y, x + width, y + r);
        ctx.lineTo(x + width, y + height - r);
        ctx.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
        ctx.lineTo(x + r, y + height);
        ctx.quadraticCurveTo(x, y + height, x, y + height - r);
        ctx.lineTo(x, y + r);
        ctx.quadraticCurveTo(x, y, x + r, y);
        ctx.closePath();
    };

    const loadImage = (url) => new Promise((resolve, reject) => {
        if (!url) return reject(new Error('Sin imagen'));
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = () => reject(new Error('No se pudo cargar imagen'));
        img.src = url;
    });

    const drawCenteredParagraph = (ctx, text, boxX, boxY, boxWidth, boxHeight, { font, color, lineHeight, maxLines, verticalAlign = 'center' }) => {
        ctx.save();
        ctx.font = font;
        ctx.fillStyle = color;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        const lines = wrapText(ctx, text, boxWidth - 24, maxLines);
        const totalHeight = lines.length * lineHeight;
        const freeSpace = Math.max(0, boxHeight - totalHeight);
        let y = boxY;
        if (verticalAlign === 'center') {
            y = boxY + (freeSpace / 2);
        } else if (verticalAlign === 'adaptive') {
            // Centrado, pero sin bajar demasiado el bloque para evitar hueco inutil.
            y = boxY + Math.min(freeSpace / 2, 52);
        }
        const x = boxX + (boxWidth / 2);
        lines.forEach((line) => {
            ctx.fillText(line, x, y);
            y += lineHeight;
        });
        ctx.restore();
    };

    const createShareCardBlob = async ({ header, title, summary, imageUrl }) => {
        const width = 844;
        const height = 1424;
        const padding = 54;
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, width, height); // PNG transparente fuera de la tarjeta

        const cardX = 0;
        const cardY = 0;
        const cardW = width;
        const cardH = height;
        roundRect(ctx, cardX, cardY, cardW, cardH, 28);
        ctx.fillStyle = 'rgba(0, 0, 0, 0.84)';
        ctx.fill();

        const darkOverlay = ctx.createLinearGradient(cardX, cardY, cardX, cardY + cardH);
        darkOverlay.addColorStop(0, 'rgba(0, 0, 0, 0.08)');
        darkOverlay.addColorStop(1, 'rgba(0, 0, 0, 0.22)');
        roundRect(ctx, cardX, cardY, cardW, cardH, 28);
        ctx.fillStyle = darkOverlay;
        ctx.fill();

        // Zona de imagen superior con clipping redondeado
        const imageAreaX = cardX + 20;
        const imageAreaY = cardY + 20;
        const imageAreaW = cardW - 40;
        const imageAreaH = 430;
        roundRect(ctx, imageAreaX, imageAreaY, imageAreaW, imageAreaH, 28);
        ctx.save();
        ctx.clip();

        let imageDrawn = false;
        try {
            const safeImageUrl = imageUrl
                ? `/noticias/image-proxy/?url=${encodeURIComponent(imageUrl)}`
                : '';
            const img = await loadImage(safeImageUrl);
            const scale = Math.max(imageAreaW / img.width, imageAreaH / img.height);
            const drawW = img.width * scale;
            const drawH = img.height * scale;
            const drawX = imageAreaX + (imageAreaW - drawW) / 2;
            const drawY = imageAreaY + (imageAreaH - drawH) / 2;
            ctx.drawImage(img, drawX, drawY, drawW, drawH);
            imageDrawn = true;
        } catch (_) {
            imageDrawn = false;
        }

        if (!imageDrawn) {
            const ph = ctx.createLinearGradient(imageAreaX, imageAreaY, imageAreaX, imageAreaY + imageAreaH);
            ph.addColorStop(0, '#334155');
            ph.addColorStop(1, '#1e293b');
            ctx.fillStyle = ph;
            ctx.fillRect(imageAreaX, imageAreaY, imageAreaW, imageAreaH);
            ctx.fillStyle = '#cbd5e1';
            ctx.font = '600 32px Arial, sans-serif';
            ctx.fillText('Imagen no disponible', imageAreaX + 34, imageAreaY + imageAreaH / 2);
        }
        ctx.restore();

        let y = imageAreaY + imageAreaH + 56;

        ctx.fillStyle = '#93c5fd';
        ctx.font = '600 22px Arial, sans-serif';
        ctx.textBaseline = 'top';
        const headerLines = wrapText(ctx, header, width - (padding * 2), 2);
        headerLines.forEach(line => {
            ctx.fillText(line, padding, y);
            y += 30;
        });

        y += 16;
        ctx.fillStyle = '#f8fafc';
        ctx.font = 'bold 48px Arial, sans-serif';
        const titleLines = wrapText(ctx, title, width - (padding * 2), 5);
        titleLines.forEach(line => {
            ctx.fillText(line, padding, y);
            y += 58;
        });

        y += 18;
        const summaryBoxX = padding;
        const summaryBoxY = y;
        const summaryBoxW = width - (padding * 2);
        const summaryBoxH = (cardY + cardH - 36) - summaryBoxY;
        drawCenteredParagraph(ctx, summary, summaryBoxX, summaryBoxY, summaryBoxW, summaryBoxH, {
            font: '400 36px Arial, sans-serif',
            color: '#d1d5db',
            lineHeight: 50,
            maxLines: 11,
            verticalAlign: 'adaptive',
        });

        // Mascara final para exportar PNG con esquinas redondeadas reales
        ctx.save();
        ctx.globalCompositeOperation = 'destination-in';
        roundRect(ctx, 0, 0, width, height, 28);
        ctx.fillStyle = '#000';
        ctx.fill();
        ctx.restore();

        return new Promise((resolve, reject) => {
            canvas.toBlob((blob) => {
                if (!blob) return reject(new Error('No se pudo generar imagen'));
                resolve(blob);
            }, 'image/png');
        });
    };

    const copyImageToClipboard = async (blob) => {
        if (!navigator.clipboard?.write || typeof ClipboardItem === 'undefined') {
            throw new Error('El navegador no soporta copiar imagen al portapapeles');
        }
        await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
    };

    const shareNewsCard = async (container, id, actionButton) => {
        const shareData = buildShareCardData(container);
        try {
            const imageBlob = await createShareCardBlob(shareData);
            await copyImageToClipboard(imageBlob);
            if (actionButton) {
                const previousHTML = actionButton.innerHTML;
                actionButton.innerHTML = SHARE_CHECK_HTML;
                actionButton.classList.add('copied');
                setTimeout(() => {
                    actionButton.innerHTML = previousHTML || SHARE_ICON_HTML;
                    actionButton.classList.remove('copied');
                }, 1100);
            }
        } catch (e) {
            err(`No se pudo copiar la noticia ${id}:`, e);
            alert('No se pudo copiar la imagen al portapapeles en este navegador.');
        }
    };

    /** Crea elemento de tarjeta desde HTML string */
    const createCardFromHTML = (cardHtml) => {
        const temp = document.createElement('div');
        temp.innerHTML = cardHtml;
        const card = temp.firstElementChild;
        return { card };
    };

    /** Asegura que no haya más de MAX_NEWS tarjetas visibles eliminando las más antiguas */
    const enforceCardLimit = () => {
        const cards = $$('.news-card-container', DOM.grid);
        if (cards.length <= MAX_NEWS) return; // Si no se excede, no hacer nada

        // Seleccionar las tarjetas sobrantes desde el índice MAX_NEWS (las más antiguas)
        const excessCards = cards.slice(MAX_NEWS);
        excessCards.forEach(card => {
            const cardId = card.id.replace('news-', '');
            card.remove();
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

    const renderPageFromServerData = (data) => {
        if (!data || data.status !== 'success') return;
        DOM.grid.innerHTML = '';
        const frag = document.createDocumentFragment();
        (data.cards || []).forEach(item => {
            const { card } = createCardFromHTML(item.card);
            const id = card ? card.id.replace('news-', '') : String(item.id);
            configureNewCard(card, id);
            frag.appendChild(card);
        });
        DOM.grid.appendChild(frag);
        STATE.backupCards = data.backup_cards || [];
        STATE.nextCursor = data.next_cursor || null;
        STATE.backupCursor = data.backup_next_cursor || data.next_cursor || null;
        log(`Inicializadas ${STATE.backupCards.length} noticias de respaldo`);
        updateCounters(data.total_news, data.total_pages);
        updatePagination(data.total_pages);
        enforceCardLimit();
    };

    const syncCurrentPageFromDb = async ({force = false} = {}) => {
        const now = Date.now();
        // cooldown para evitar duplicados por focus + visibilitychange seguidos
        if (!force && (now - STATE.lastDbSyncAt) < 1500) return;
        if (STATE.syncingFromDb) return;
        if (!navigator.onLine) return;

        STATE.syncingFromDb = true;
        try {
            const params = new URLSearchParams(location.search);
            const page = parseInt(params.get('page') || String(STATE.currentPage || 1), 10) || 1;
            const order = params.get('order') || STATE.order;
            const q = params.get('q') || '';
            STATE.currentPage = page;
            STATE.order = order;

            const data = await serverGetPage({page: STATE.currentPage, order: STATE.order, q});
            renderPageFromServerData(data);
            STATE.lastDbSyncAt = Date.now();
        } catch (e) {
            err('Sync DB al recuperar foco/conexion:', e);
        } finally {
            STATE.syncingFromDb = false;
        }
    };

    /* ---------------------------------------------------------------------
     *  Carga inicial y precarga de noticias de respaldo
     * ------------------------------------------------------------------ */
    const initializeBackupCards = () => {
        try {
            const backupDataElement = $('#backup-cards-data');
            if (backupDataElement) {
                const backupData = JSON.parse(backupDataElement.textContent);
                STATE.backupCards = backupData || [];
                log(`Inicializadas ${STATE.backupCards.length} noticias de respaldo desde el servidor`);
            }
        } catch (e) {
            err('Error al inicializar noticias de respaldo:', e);
            STATE.backupCards = [];
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
                
                // Actualizar cursor para la siguiente carga de respaldo
                if (data.backup_next_cursor) {
                    STATE.backupCursor = data.backup_next_cursor;
                } else if (newBackups.length > 0) {
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
        const currentPage = new URLSearchParams(location.search).get('page') || 1;

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
        
        // No usar respaldo precargado para evitar problemas de orden cronológico
        // Siempre esperar la respuesta del servidor que calcula el reemplazo correcto
        // Programar eliminación del DOM después de la animación
        const removeFromDOM = () => {
            container.remove();
        };
        const appendServerReplacement = (data) => {
            if (!data?.html) return false;
            const { card: newCard } = createCardFromHTML(data.html);
            if (!newCard) return false;
            const newCardId = newCard.id.replace('news-', '');
            if ($(`#news-${newCardId}`, DOM.grid)) {
                log(`Skipping duplicate server card: ${newCardId}`);
                return false;
            }
            configureNewCard(newCard, newCardId);
            DOM.grid.appendChild(newCard);
            animateScaleOpacity(newCard);
            log(`Agregada noticia del servidor (orden correcto): ${newCardId}`);
            return true;
        };
        const restoreCollapsedCard = () => {
            container.style.transition = 'none';
            container.style.height = '';
            container.style.width = '';
            container.style.marginRight = '';
            container.style.opacity = '';
            container.style.transform = '';
            container.classList.remove('collapsing');
            void container.offsetHeight;
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
            if (oldPositions) animateReposition(oldPositions, [`news-${newsId}`]);
            enforceCardLimit();
            STATE.deletingNews.delete(newsId); // Limpiar flag
        }, animationDuration + 50);

        // Llamada al servidor en paralelo
        serverDeleteNews(newsId, currentPage)
            .then(data => {
                if (data.status !== 'success') {
                    clearTimeout(removeTimeout);
                    container.removeEventListener('transitionend', onAnimEnd);
                    if (document.body.contains(container)) {
                        restoreCollapsedCard();
                    } else {
                        window.location.reload();
                        return;
                    }
                    STATE.deletingNews.delete(newsId);
                    err('Error del servidor al eliminar:', data.message);
                    return;
                }

                // Si ya se eliminó del DOM por timeout, actualizar contadores
                if (!document.body.contains(container)) {
                    appendServerReplacement(data);
                    updateCounters(data.total_news, data.total_pages);
                    enforceCardLimit();

                    // Cargar más noticias de respaldo si quedamos con pocas
                    if (STATE.backupCards.length < 5) {
                        loadMoreBackupNews();
                    }

                    return;
                }

                // Si el servidor responde antes del timeout, cancelar timeout y proceder normalmente
                clearTimeout(removeTimeout);
                container.removeEventListener('transitionend', onAnimEnd);
                removed = true;
                removeFromDOM();
                STATE.deletingNews.delete(newsId); // Liberar flag incluso si se elimina antes de la animación
                appendServerReplacement(data);
                updateCounters(data.total_news, data.total_pages);

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
                container.removeEventListener('transitionend', onAnimEnd);
                if (document.body.contains(container)) {
                    restoreCollapsedCard();
                } else {
                    window.location.reload();
                    return;
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
            const { card } = createCardFromHTML(item.card);
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
            
            configureNewCard(card, id);
            frag.appendChild(card);
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
                
                // Mover al respaldo
                STATE.backupCards.push({
                    id: cardId,
                    card: card.outerHTML
                });
                
                // Remover del DOM
                card.remove();
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
                
                if (backupData && backupData.card) {
                    const { card: newCard } = createCardFromHTML(backupData.card);
                    
                    if (newCard) {
                        const id = newCard.id.replace('news-', '');
                        // Verificar que no esté duplicada
                        if (!$(`#news-${id}`, DOM.grid)) {
                            configureNewCard(newCard, id);
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
    const configureNewCard = (container, id) => {
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

        // Acción compartir para copiar tarjeta compacta al portapapeles
        if (links && !links.querySelector('.share-opener')) {
            const share = document.createElement('button');
            share.type = 'button';
            share.className = 'news-link share-opener';
            share.title = 'Copiar tarjeta';
            share.setAttribute('aria-label', 'Copiar tarjeta');
            share.innerHTML = SHARE_ICON_HTML;
            share.addEventListener('click', (e) => {
                e.stopPropagation();
                shareNewsCard(container, id, share);
            });
            links.prepend(share);
        }

        // Delete dentro del reverso
        [container.querySelector('.card-back .delete-btn')].forEach(btn => {
            btn?.addEventListener('click', (e) => { e.stopPropagation(); deleteNews(id); });
        });

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
        configureNewCard(el, id);
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
        if (STATE.pageVisible) syncCurrentPageFromDb();
    });
    window.addEventListener('focus', () => syncCurrentPageFromDb());
    window.addEventListener('pageshow', () => syncCurrentPageFromDb({force: true}));
    window.addEventListener('online', () => syncCurrentPageFromDb({force: true}));

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
                
                if (data.html) {
                    const { card } = createCardFromHTML(data.html);
                    const id = card.id.replace('news-', '');
                    
                    // Si ya tenemos 25 noticias, mover la última al respaldo antes de agregar la nueva
                    if (currentCardsCount >= MAX_NEWS) {
                        const cardsArray = $$('.news-card-container', DOM.grid);
                        const lastCard = STATE.order === 'desc' ? cardsArray[cardsArray.length - 1] : cardsArray[0];
                        
                        if (lastCard) {
                            const lastId = lastCard.id.replace('news-', '');
                            
                            // Mover al respaldo
                            STATE.backupCards.unshift({
                                id: lastId,
                                card: lastCard.outerHTML
                            });
                            
                            // Remover del DOM
                            lastCard.remove();
                            log(`Noticia ${lastId} movida al respaldo por undo`);
                        }
                    }
                    
                    // Agregar la noticia restaurada
                    if (STATE.order === 'desc') {
                        DOM.grid.prepend(card);
                    } else {
                        DOM.grid.appendChild(card);
                    }
                    configureNewCard(card, id);
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
                renderPageFromServerData(data);
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
        syncCurrentPageFromDb({force: true})
            .catch(e => err('Error al cargar página inicial:', e));
        // Establecer icono inicial según orden actual
        setOrderIcon();
    });
    
    setInterval(checkForNewNews, CHECK_INTERVAL);
    enforceCardLimit(); // Aplicar límite al cargar la página inicialmente
    // updatePagination será llamada por updateCounters en la carga inicial

})();
