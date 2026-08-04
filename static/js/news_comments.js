(() => {
    'use strict';

    const modal = document.getElementById('news-comments-modal');
    if (!modal) return;

    const panel = modal.querySelector('.news-comments-panel');
    const title = document.getElementById('news-comments-title');
    const summary = document.getElementById('news-comments-summary');
    const status = document.getElementById('news-comments-status');
    const list = document.getElementById('news-comments-list');
    const sourceLink = document.getElementById('news-comments-source-link');
    const responseCache = new Map();
    const pendingRequests = new Map();
    const prefetchTimers = new Map();
    let opener = null;
    let activeRequestUrl = null;

    const formatDate = (value) => {
        if (!value) return '';
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return '';
        return new Intl.DateTimeFormat('es-CO', {
            dateStyle: 'medium',
            timeStyle: 'short',
        }).format(date);
    };

    // Mensaje de texto plano (vacío o error): quita la pastilla de carga, que
    // es lo único que mete nodos hijos en el status.
    const setStatusMessage = (message, {error = false} = {}) => {
        status.hidden = false;
        status.classList.remove('is-loading');
        status.classList.toggle('is-error', error);
        status.textContent = message;
    };

    const buildLoaderPill = (text) => {
        const pill = document.createElement('span');
        pill.className = 'feed-loader-pill';

        const orbit = document.createElement('span');
        orbit.className = 'feed-loader-orbit';
        orbit.setAttribute('aria-hidden', 'true');

        const label = document.createElement('span');
        label.className = 'feed-loader-text';
        label.textContent = text;

        pill.append(orbit, label);
        return pill;
    };

    const setLoading = () => {
        title.textContent = 'Comentarios';
        summary.textContent = '';
        list.replaceChildren();
        status.hidden = false;
        status.classList.remove('is-error');
        status.classList.add('is-loading');
        status.replaceChildren(buildLoaderPill('Cargando comentarios…'));
        sourceLink.hidden = true;
    };

    const renderComments = (payload) => {
        title.textContent = payload.title || 'Comentarios';
        sourceLink.href = payload.article_url || '#';
        sourceLink.hidden = !payload.article_url;
        list.replaceChildren();

        const comments = Array.isArray(payload.comments) ? payload.comments : [];
        const total = Number.isFinite(Number(payload.total)) ? Number(payload.total) : comments.length;
        const source = payload.source ? ` · ${payload.source}` : '';
        summary.textContent = comments.length < total
            ? `Mostrando ${comments.length} de ${total}${source}`
            : `${total} ${total === 1 ? 'comentario' : 'comentarios'}${source}`;

        if (!comments.length) {
            setStatusMessage('Esta noticia todavía no tiene comentarios.');
            return;
        }

        status.hidden = true;
        status.classList.remove('is-loading');
        status.replaceChildren();

        const normalizedComments = comments.map((comment, index) => ({
            ...comment,
            id: String(comment.id || `comment-${index}`),
            parent_id: comment.parent_id === null || comment.parent_id === undefined
                ? null
                : String(comment.parent_id),
        }));
        const commentsById = new Map(normalizedComments.map((comment) => [comment.id, comment]));
        const findThreadRoot = (comment) => {
            let current = comment;
            const visited = new Set();
            while (current.parent_id && commentsById.has(current.parent_id) && !visited.has(current.id)) {
                visited.add(current.id);
                current = commentsById.get(current.parent_id);
            }
            return current.id;
        };
        const threadRoots = new Map();
        normalizedComments.forEach((comment) => {
            const rootId = findThreadRoot(comment);
            comment.threadRootId = rootId;
            if (comment.id !== rootId) {
                threadRoots.set(rootId, (threadRoots.get(rootId) || 0) + 1);
            }
        });

        normalizedComments.forEach((comment) => {
            const item = document.createElement('li');
            item.className = 'news-comment';
            item.style.setProperty('--comment-depth', String(Math.min(Number(comment.depth) || 0, 4)));
            item.dataset.commentId = comment.id;
            item.dataset.threadRoot = comment.threadRootId;

            const header = document.createElement('div');
            header.className = 'news-comment-header';

            const user = document.createElement('strong');
            user.className = 'news-comment-user';
            user.textContent = comment.user || 'Anónimo';
            header.appendChild(user);

            const metadataParts = [];
            const date = formatDate(comment.date);
            if (date) metadataParts.push(date);
            if (metadataParts.length) {
                const metadata = document.createElement('span');
                metadata.className = 'news-comment-meta';
                metadata.textContent = metadataParts.join(' · ');
                header.appendChild(metadata);
            }

            const votes = Number(comment.votes) || 0;
            const voteIndicator = document.createElement('span');
            const hasVoteBreakdown = comment.upvotes !== null && comment.upvotes !== undefined
                && comment.downvotes !== null && comment.downvotes !== undefined;
            const upvotes = hasVoteBreakdown ? Math.max(Number(comment.upvotes) || 0, 0) : 0;
            const downvotes = hasVoteBreakdown ? Math.max(Number(comment.downvotes) || 0, 0) : 0;
            voteIndicator.className = [
                'news-comment-votes',
                hasVoteBreakdown ? 'has-breakdown' : '',
                upvotes > 0 ? 'has-upvotes' : '',
                downvotes > 0 ? 'has-downvotes' : '',
                votes > 0 ? 'is-positive' : votes < 0 ? 'is-negative' : 'is-neutral',
            ].filter(Boolean).join(' ');

            if (hasVoteBreakdown) {
                const upLabel = `${upvotes} ${upvotes === 1 ? 'voto arriba' : 'votos arriba'}`;
                const downLabel = `${downvotes} ${downvotes === 1 ? 'voto abajo' : 'votos abajo'}`;
                voteIndicator.title = `${upLabel}, ${downLabel}; puntuación neta: ${votes}`;
                voteIndicator.innerHTML = `
                    <span class="news-comment-vote-side vote-up-side">
                        <svg class="news-comment-vote-arrow vote-up" viewBox="0 0 24 24" aria-hidden="true">
                            <path d="M12 5L5 14H9V19H15V14H19L12 5Z"></path>
                        </svg>
                        <span class="news-comment-vote-count">${new Intl.NumberFormat('es-CO').format(upvotes)}</span>
                    </span>
                    <span class="news-comment-vote-side vote-down-side">
                        <svg class="news-comment-vote-arrow vote-down" viewBox="0 0 24 24" aria-hidden="true">
                            <path d="M12 19L19 10H15V5H9V10H5L12 19Z"></path>
                        </svg>
                        <span class="news-comment-vote-count">${new Intl.NumberFormat('es-CO').format(downvotes)}</span>
                    </span>
                `;
            } else {
                voteIndicator.title = `Puntuación: ${votes} ${Math.abs(votes) === 1 ? 'voto' : 'votos'}`;
                voteIndicator.innerHTML = `
                    <svg class="news-comment-vote-arrow vote-up" viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M12 5L5 14H9V19H15V14H19L12 5Z"></path>
                    </svg>
                    <span class="news-comment-vote-score">${new Intl.NumberFormat('es-CO').format(votes)}</span>
                    <svg class="news-comment-vote-arrow vote-down" viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M12 19L19 10H15V5H9V10H5L12 19Z"></path>
                    </svg>
                `;
            }
            voteIndicator.setAttribute('aria-label', voteIndicator.title);
            header.appendChild(voteIndicator);

            const replyCount = threadRoots.get(comment.id) || 0;
            if (replyCount) {
                const toggle = document.createElement('button');
                toggle.type = 'button';
                toggle.className = 'news-comment-thread-toggle';
                toggle.dataset.threadRoot = comment.id;
                toggle.dataset.replyCount = String(replyCount);
                toggle.setAttribute('aria-expanded', 'true');
                toggle.textContent = `${replyCount} ${replyCount === 1 ? 'respuesta' : 'respuestas'}`;
                header.appendChild(toggle);
            }

            const body = document.createElement('p');
            body.className = 'news-comment-text';
            body.textContent = comment.comment || '';

            item.appendChild(header);
            if (body.textContent) item.appendChild(body);

            const mediaItems = Array.isArray(comment.media) ? comment.media : [];
            if (mediaItems.length) {
                const gallery = document.createElement('div');
                gallery.className = 'news-comment-media';
                mediaItems.forEach((media) => {
                    try {
                        const mediaUrl = new URL(media.url);
                        const thumbnailUrl = new URL(media.thumbnail_url || media.url);
                        if (mediaUrl.protocol !== 'https:' || thumbnailUrl.protocol !== 'https:') return;

                        const link = document.createElement('a');
                        link.href = mediaUrl.href;
                        link.target = '_blank';
                        link.rel = 'noopener noreferrer';
                        link.className = 'news-comment-media-link';
                        link.setAttribute('aria-label', 'Abrir imagen del comentario');

                        const image = document.createElement('img');
                        image.src = thumbnailUrl.href;
                        image.alt = 'Imagen adjunta al comentario';
                        image.loading = 'lazy';
                        image.decoding = 'async';
                        image.referrerPolicy = 'no-referrer';
                        link.appendChild(image);
                        gallery.appendChild(link);
                    } catch (_) {
                        // Ignorar adjuntos con URL inválida.
                    }
                });
                if (gallery.childElementCount) item.appendChild(gallery);
            }

            list.appendChild(item);
        });
    };

    const toggleThread = (button) => {
        const rootId = button.dataset.threadRoot;
        const willExpand = button.getAttribute('aria-expanded') !== 'true';
        list.querySelectorAll('.news-comment').forEach((item) => {
            if (item.dataset.threadRoot === rootId && item.dataset.commentId !== rootId) {
                item.hidden = !willExpand;
            }
        });
        button.setAttribute('aria-expanded', String(willExpand));
        const count = Number(button.dataset.replyCount) || 0;
        const label = `${count} ${count === 1 ? 'respuesta' : 'respuestas'}`;
        button.textContent = willExpand ? label : `Mostrar ${label}`;
    };

    const renderError = (message) => {
        list.replaceChildren();
        summary.textContent = '';
        setStatusMessage(message || 'No se pudieron cargar los comentarios.', {error: true});
    };

    const totalOf = (payload) => {
        const comments = Array.isArray(payload?.comments) ? payload.comments : [];
        const total = Number(payload?.total);
        return Number.isFinite(total) && total >= 0 ? total : comments.length;
    };

    // La insignia se pinta con lo que ya trae la precarga: el contador no
    // cuesta una petición extra, solo aprovecha la que iba a hacerse igual.
    const paintBadge = (button, total) => {
        let badge = button.querySelector('.comments-badge');
        if (!badge) {
            badge = document.createElement('span');
            badge.className = 'comments-badge';
            badge.setAttribute('aria-hidden', 'true');
            button.appendChild(badge);
        }
        const text = total > 99 ? '99+' : String(total);
        if (badge.textContent !== text) badge.textContent = text;

        const label = total === 0
            ? 'Comentarios (ninguno todavía)'
            : `Ver comentarios (${total})`;
        button.title = label;
        button.setAttribute('aria-label', label);
    };

    // Se pintan todos los botones que apunten a la misma noticia: la rejilla
    // puede tener el mismo enlace en más de una tarjeta tras un refresco.
    const paintBadgesFor = (url, total) => {
        document.querySelectorAll('.comments-btn').forEach((button) => {
            if (button.dataset.commentsUrl === url) paintBadge(button, total);
        });
    };

    // Un refresco parcial reemplaza el nodo del botón y se lleva la insignia
    // por delante, así que se repinta desde el caché al volver a tocarlo.
    const hydrateBadge = (button) => {
        const url = button.dataset.commentsUrl;
        const cached = url ? responseCache.get(url) : null;
        if (cached) paintBadge(button, totalOf(cached));
    };

    const fetchComments = (url) => {
        if (responseCache.has(url)) return Promise.resolve(responseCache.get(url));
        if (pendingRequests.has(url)) return pendingRequests.get(url);

        const request = fetch(url, {
            credentials: 'same-origin',
            headers: {'X-Requested-With': 'XMLHttpRequest'},
        })
            .then(async (response) => {
                const payload = await response.json().catch(() => ({}));
                if (!response.ok || payload.status !== 'success') {
                    throw new Error(payload.message || 'No se pudieron cargar los comentarios.');
                }
                responseCache.set(url, payload);
                paintBadgesFor(url, totalOf(payload));
                return payload;
            })
            .finally(() => pendingRequests.delete(url));

        pendingRequests.set(url, request);
        return request;
    };

    const startPrefetch = (button) => {
        const url = button.dataset.commentsUrl;
        cancelPrefetch(button);
        hydrateBadge(button);
        if (!url || responseCache.has(url) || pendingRequests.has(url)) return;
        fetchComments(url).catch(() => {
            // El modal mostrará el error si el usuario decide abrirlo.
        });
    };

    const schedulePrefetch = (button, delay = 300) => {
        const url = button.dataset.commentsUrl;
        hydrateBadge(button);
        if (!url || responseCache.has(url) || pendingRequests.has(url) || prefetchTimers.has(button)) {
            return;
        }
        const timer = window.setTimeout(() => {
            prefetchTimers.delete(button);
            startPrefetch(button);
        }, delay);
        prefetchTimers.set(button, timer);
    };

    const cancelPrefetch = (button) => {
        const timer = prefetchTimers.get(button);
        if (timer === undefined) return;
        window.clearTimeout(timer);
        prefetchTimers.delete(button);
    };

    const closeModal = () => {
        if (modal.hidden) return;
        activeRequestUrl = null;
        modal.hidden = true;
        document.body.classList.remove('comments-modal-open');
        opener?.focus({preventScroll: true});
        opener = null;
    };

    const openModal = async (button) => {
        const url = button.dataset.commentsUrl;
        if (!url) return;

        opener = button;
        activeRequestUrl = url;
        setLoading();
        modal.hidden = false;
        document.body.classList.add('comments-modal-open');
        panel.focus({preventScroll: true});

        try {
            const payload = await fetchComments(url);
            if (activeRequestUrl === url && !modal.hidden) renderComments(payload);
        } catch (error) {
            if (activeRequestUrl === url && !modal.hidden) renderError(error.message);
        }
    };

    document.addEventListener('pointerover', (event) => {
        const button = event.target.closest('.comments-btn');
        if (button && !button.contains(event.relatedTarget)) {
            startPrefetch(button);
            return;
        }

        const card = event.target.closest('.news-card-container');
        if (card && !card.contains(event.relatedTarget)) {
            const cardCommentsButton = card.querySelector('.comments-btn');
            if (cardCommentsButton) schedulePrefetch(cardCommentsButton);
        }
    });

    document.addEventListener('pointerout', (event) => {
        // El dedo también "sale" de la tarjeta al levantarlo, justo después de
        // darle la vuelta. Cancelar ahí dejaría el táctil sin contador.
        if (event.pointerType === 'touch') return;

        const card = event.target.closest('.news-card-container');
        if (card && !card.contains(event.relatedTarget)) {
            const cardCommentsButton = card.querySelector('.comments-btn');
            if (cardCommentsButton) cancelPrefetch(cardCommentsButton);
        }
    });

    // En móvil no hay hover: el reverso se descubre tocando. Observar el giro
    // cubre las dos formas de llegar al botón con un solo disparador, y
    // mantiene el mismo retardo para no lanzar peticiones al pasar de largo.
    const flipObserver = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            const card = mutation.target;
            if (!card.classList?.contains('news-card')) return;

            const button = card.querySelector('.comments-btn');
            if (!button) return;

            if (card.classList.contains('is-flipped')) {
                schedulePrefetch(button);
            } else {
                cancelPrefetch(button);
            }
        });
    });
    flipObserver.observe(document.body, {
        subtree: true,
        attributes: true,
        attributeFilter: ['class'],
    });

    document.addEventListener('focusin', (event) => {
        const button = event.target.closest('.comments-btn');
        if (button) startPrefetch(button);
    });

    document.addEventListener('click', (event) => {
        const threadToggle = event.target.closest('.news-comment-thread-toggle');
        if (threadToggle) {
            event.preventDefault();
            toggleThread(threadToggle);
            return;
        }

        const button = event.target.closest('.comments-btn');
        if (button) {
            event.preventDefault();
            event.stopPropagation();
            cancelPrefetch(button);
            openModal(button);
            return;
        }
        if (event.target.closest('[data-comments-close]')) closeModal();
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && !modal.hidden) closeModal();
    });
})();
