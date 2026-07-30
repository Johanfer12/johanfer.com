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
    let opener = null;
    let requestController = null;

    const formatDate = (value) => {
        if (!value) return '';
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return '';
        return new Intl.DateTimeFormat('es-CO', {
            dateStyle: 'medium',
            timeStyle: 'short',
        }).format(date);
    };

    const setLoading = () => {
        title.textContent = 'Comentarios';
        summary.textContent = '';
        list.replaceChildren();
        status.hidden = false;
        status.classList.remove('is-error');
        status.textContent = 'Cargando comentarios…';
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
            status.hidden = false;
            status.classList.remove('is-error');
            status.textContent = 'Esta noticia todavía no tiene comentarios.';
            return;
        }

        status.hidden = true;

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
            if (Number(comment.votes)) {
                const votes = Number(comment.votes);
                metadataParts.push(`${votes} ${Math.abs(votes) === 1 ? 'voto' : 'votos'}`);
            }
            if (metadataParts.length) {
                const metadata = document.createElement('span');
                metadata.className = 'news-comment-meta';
                metadata.textContent = metadataParts.join(' · ');
                header.appendChild(metadata);
            }

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
        status.hidden = false;
        status.classList.add('is-error');
        status.textContent = message || 'No se pudieron cargar los comentarios.';
    };

    const closeModal = () => {
        if (modal.hidden) return;
        requestController?.abort();
        requestController = null;
        modal.hidden = true;
        document.body.classList.remove('comments-modal-open');
        opener?.focus({preventScroll: true});
        opener = null;
    };

    const openModal = async (button) => {
        const url = button.dataset.commentsUrl;
        if (!url) return;

        opener = button;
        setLoading();
        modal.hidden = false;
        document.body.classList.add('comments-modal-open');
        panel.focus({preventScroll: true});

        if (responseCache.has(url)) {
            renderComments(responseCache.get(url));
            return;
        }

        requestController?.abort();
        requestController = new AbortController();
        try {
            const response = await fetch(url, {
                credentials: 'same-origin',
                headers: {'X-Requested-With': 'XMLHttpRequest'},
                signal: requestController.signal,
            });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok || payload.status !== 'success') {
                throw new Error(payload.message || 'No se pudieron cargar los comentarios.');
            }
            responseCache.set(url, payload);
            renderComments(payload);
        } catch (error) {
            if (error.name !== 'AbortError') renderError(error.message);
        } finally {
            requestController = null;
        }
    };

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
            openModal(button);
            return;
        }
        if (event.target.closest('[data-comments-close]')) closeModal();
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && !modal.hidden) closeModal();
    });
})();
