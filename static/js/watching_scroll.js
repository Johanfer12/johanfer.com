// Scroll infinito de Mi TV, calcado del de libros (infinite_scroll.js)
let page = 1;
let loading = false;
let hasNext = true;
let currentTipo = 'series';
let currentOrden = '';

const watchContainer = document.getElementById('watch-container');
const loadingDiv = document.getElementById('loading');
const fallbackPoster = watchContainer ? watchContainer.dataset.fallbackPoster : '';

const escapeHtml = (value) => {
    const div = document.createElement('div');
    div.textContent = value || '';
    return div.innerHTML;
};

const posterImg = (card) => `
    <img src="${escapeHtml(card.poster_url)}"
         alt="${escapeHtml(card.title)}"
         loading="lazy"
         onerror="this.onerror=null;this.src='${escapeHtml(fallbackPoster)}';">
`;

const createWatchItem = (card) => {
    const item = document.createElement('div');
    item.className = 'book-item';

    let infoRows = '';
    if (card.media_type === 'episode') {
        infoRows += `<p><strong>Episodios vistos</strong><br>${escapeHtml(String(card.episode_total || ''))}</p>`;
        infoRows += `<p><strong>Último</strong><br>${escapeHtml(card.display_label)}</p>`;
    } else if (card.plays > 1) {
        infoRows += `<p><strong>Vista</strong><br>${escapeHtml(String(card.plays))} veces</p>`;
    }
    if (card.year) {
        infoRows += `<p><strong>Año</strong><br>${escapeHtml(String(card.year))}</p>`;
    }
    if (card.user_rating_html) {
        infoRows += `<p><strong>Mi Calificación</strong><br>${card.user_rating_html}</p>`;
    }
    if (card.public_rating_html) {
        infoRows += `<p><strong>Calificación General</strong><br>${card.public_rating_html}</p>`;
    }
    infoRows += `<p><strong>Lo vi el...</strong><br>${escapeHtml(card.watched_at)}</p>`;

    item.innerHTML = `
        <div class="book-info-container">
            <div class="book-cover" onclick="openModal('watch-${card.id}')">
                ${posterImg(card)}
                ${card.is_watching ? '<div class="watching-ribbon"><span>Viendo</span></div>' : ''}
            </div>
            <div class="book-info">
                <a href="${escapeHtml(card.trakt_url)}"
                   class="book-title"
                   target="_blank"
                   rel="noopener noreferrer">
                   ${escapeHtml(card.title)}
                </a>
                ${infoRows}
            </div>
        </div>
    `;

    return item;
};

const createWatchModal = (card) => {
    const modal = document.createElement('div');
    modal.id = `modal-watch-${card.id}`;
    modal.className = 'modal';

    let metaLeft = '';
    if (card.media_type === 'episode') {
        metaLeft += `<p><strong>Episodios vistos:</strong> ${escapeHtml(String(card.episode_total || ''))}</p>`;
        metaLeft += `<p><strong>Último:</strong> ${escapeHtml(card.display_label)}${card.episode_title ? ' - ' + escapeHtml(card.episode_title) : ''}</p>`;
    } else if (card.plays > 1) {
        metaLeft += `<p><strong>Vista:</strong> ${escapeHtml(String(card.plays))} veces</p>`;
    } else {
        metaLeft += '<p><strong>Tipo:</strong> Película</p>';
    }
    if (card.user_rating_html) {
        metaLeft += `<p><strong>Mi Calificación:</strong> ${card.user_rating_html}</p>`;
    }
    if (card.public_rating_html) {
        metaLeft += `<p><strong>Calificación General:</strong> ${card.public_rating_html}</p>`;
    }

    let metaRight = '';
    if (card.year) {
        metaRight += `<p><strong>Año:</strong> ${escapeHtml(String(card.year))}</p>`;
    }
    metaRight += `<p><strong>Visto el:</strong> ${escapeHtml(card.watched_at)}</p>`;

    modal.innerHTML = `
        <div class="modal-content book-modal-content">
            <span class="close" onclick="closeModal('watch-${card.id}')">&times;</span>
            <div class="book-modal-body">
                <div class="book-modal-cover">
                    ${posterImg(card)}
                </div>
                <div class="book-modal-info">
                    <h2>${escapeHtml(card.title)}</h2>
                    <div class="book-modal-metadata">
                        <div>${metaLeft}</div>
                        <div>${metaRight}</div>
                    </div>
                    <div class="book-description">
                        <div class="book-description-scroll">
                            <strong>Descripción</strong><br><br>
                            ${card.overview || 'No hay descripción disponible.'}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
    return modal;
};

function loadMoreCards() {
    if (loading || !hasNext) return;

    loading = true;
    loadingDiv.style.display = 'block';

    const params = new URLSearchParams();
    params.set('page', String(page + 1));
    params.set('tipo', currentTipo);
    if (currentOrden) {
        params.set('orden', currentOrden);
    }

    fetch(`/viendo/?${params.toString()}`, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
        .then((response) => response.json())
        .then((data) => {
            (data.cards || []).forEach((card) => {
                watchContainer.appendChild(createWatchItem(card));
                watchContainer.appendChild(createWatchModal(card));
            });
            page += 1;
            hasNext = Boolean(data.has_next);
            loading = false;
            loadingDiv.style.display = 'none';
            if (!hasNext) {
                window.removeEventListener('scroll', handleScroll);
            }
        })
        .catch((error) => {
            console.error('Error al cargar más tarjetas:', error);
            loading = false;
            loadingDiv.style.display = 'none';
        });
}

function handleScroll() {
    if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 500) {
        loadMoreCards();
    }
}

document.addEventListener('DOMContentLoaded', function () {
    if (!watchContainer) return;

    const params = new URLSearchParams(window.location.search);
    currentTipo = params.get('tipo') === 'peliculas' ? 'peliculas' : 'series';
    currentOrden = params.get('orden') || '';
    hasNext = watchContainer.dataset.hasNext === 'true';

    if (hasNext) {
        window.addEventListener('scroll', handleScroll);
    }
});
