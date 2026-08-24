// Mi TV: solo el marcado de la tarjeta y del modal. La paginación, la búsqueda
// y el scroll los lleva infinite_scroll_core.js, compartido con Mis Libros.
const watchContainer = document.getElementById('watch-container');
const fallbackPoster = watchContainer ? watchContainer.dataset.fallbackPoster : '';
let currentTipo = 'series';
let currentOrden = '';

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
                <a href="${escapeHtml(card.detail_url)}"
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

const renderCards = (data, {replace}) => {
    if (replace) {
        watchContainer.innerHTML = '';
        document.querySelectorAll('div.modal[id^="modal-watch-"]').forEach((modal) => modal.remove());
    }
    (data.cards || []).forEach((card) => {
        watchContainer.appendChild(createWatchItem(card));
        watchContainer.appendChild(createWatchModal(card));
    });
};

const setWatchedTotalLabel = (count) => {
    const totalLabel = document.querySelector('.header .total');
    if (!totalLabel || typeof count === 'undefined') {
        return;
    }
    const noun = watchContainer.dataset.watchNoun || '';
    totalLabel.textContent = `${count} ${noun}${count === 1 ? '' : 's'}`.trim();
};

// Reescribe los enlaces de los toggles series/películas para que arrastren el
// filtro activo (los href vienen del servidor y no saben de la búsqueda AJAX).
const syncToggleLinks = (currentQuery) => {
    document.querySelectorAll('.watch-toggle-btn').forEach((link) => {
        const tipo = link.classList.contains('movies') ? 'peliculas' : 'series';
        const params = new URLSearchParams();
        params.set('tipo', tipo);
        if (currentOrden && currentOrden !== 'fecha_desc') {
            params.set('orden', currentOrden);
        }
        if (currentQuery) {
            params.set('q', currentQuery);
        }
        link.setAttribute('href', `?${params.toString()}`);
    });
};

document.addEventListener('DOMContentLoaded', function () {
    if (!watchContainer) return;

    const params = new URLSearchParams(window.location.search);
    currentTipo = params.get('tipo') === 'peliculas' ? 'peliculas' : 'series';
    currentOrden = params.get('orden') || '';

    const scroll = window.createInfiniteScroll({
        container: watchContainer,
        endpoint: '/viendo/',
        params: () => ({tipo: currentTipo, orden: currentOrden}),
        render: renderCards,
        onLoaded: (data, query) => {
            setWatchedTotalLabel(data.total_watched);
            syncToggleLinks(query);
        },
    });
    window.watchingApplySearch = scroll.applySearch;
});
