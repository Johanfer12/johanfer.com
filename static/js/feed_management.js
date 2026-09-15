(() => {
    const tabs = Array.from(document.querySelectorAll('[data-management-tab]'));
    const panels = Array.from(document.querySelectorAll('[data-management-panel]'));

    if (!tabs.length || !panels.length) return;

    const validPanelIds = new Set(panels.map((panel) => panel.id));

    function activate(panelId, { updateHash = false, focus = false } = {}) {
        const defaultPanelId = validPanelIds.has('word-filters') ? 'word-filters' : panels[0].id;
        const selectedId = validPanelIds.has(panelId) ? panelId : defaultPanelId;

        panels.forEach((panel) => {
            const isSelected = panel.id === selectedId;
            panel.classList.toggle('is-active', isSelected);
            panel.hidden = !isSelected;
        });

        tabs.forEach((tab) => {
            const isSelected = tab.getAttribute('aria-controls') === selectedId;
            tab.classList.toggle('is-active', isSelected);
            tab.setAttribute('aria-selected', String(isSelected));
            tab.tabIndex = isSelected ? 0 : -1;
            if (isSelected && focus) tab.focus();
        });

        if (updateHash && window.location.hash !== `#${selectedId}`) {
            window.history.pushState(null, '', `#${selectedId}`);
        }
    }

    tabs.forEach((tab, index) => {
        tab.addEventListener('click', (event) => {
            event.preventDefault();
            activate(tab.getAttribute('aria-controls'), { updateHash: true });
        });

        tab.addEventListener('keydown', (event) => {
            let nextIndex;
            if (event.key === 'ArrowRight') nextIndex = (index + 1) % tabs.length;
            if (event.key === 'ArrowLeft') nextIndex = (index - 1 + tabs.length) % tabs.length;
            if (event.key === 'Home') nextIndex = 0;
            if (event.key === 'End') nextIndex = tabs.length - 1;
            if (nextIndex === undefined) return;

            event.preventDefault();
            activate(tabs[nextIndex].getAttribute('aria-controls'), {
                updateHash: true,
                focus: true,
            });
        });
    });

    window.addEventListener('hashchange', () => activate(window.location.hash.slice(1)));
    activate(window.location.hash.slice(1));

    const editModal = document.querySelector('#word-filter-edit-modal');
    const editForm = document.querySelector('#word-filter-edit-form');
    const wordInput = document.querySelector('#word-filter-edit-word');
    const activeInput = document.querySelector('#word-filter-edit-active');
    const titleOnlyInput = document.querySelector('#word-filter-edit-title-only');

    if (!editModal || !editForm || !wordInput || !activeInput || !titleOnlyInput) return;

    // Por delegación y no tarjeta a tarjeta: las filas de la lista llegan
    // después de cargar la página, así que no existen cuando esto se ejecuta.
    document.addEventListener('click', (event) => {
        const button = event.target.closest('[data-word-filter-edit]');
        if (!button) return;
        if (typeof editModal.showModal !== 'function') return;
        event.preventDefault();
        editForm.action = button.href;
        wordInput.value = button.dataset.word || '';
        activeInput.checked = button.dataset.active === 'true';
        titleOnlyInput.checked = button.dataset.titleOnly === 'true';
        editModal.showModal();
        wordInput.focus();
        wordInput.select();
    });

    editModal.querySelectorAll('[data-modal-close]').forEach((button) => {
        button.addEventListener('click', () => editModal.close());
    });

    editModal.addEventListener('click', (event) => {
        if (event.target === editModal) editModal.close();
    });
})();

// Búsqueda y carga por tandas de las palabras filtro.
//
// En bloque aparte a propósito: el de arriba hace `return` pronto si falta el
// modal de edición, y eso dejaría la búsqueda sin montar.
(() => {
    const grid = document.querySelector('[data-word-filter-grid]');
    const form = document.querySelector('[data-word-filter-search]');
    if (!grid || !form) return;

    const input = form.querySelector('input[name="q"]');
    const estado = form.querySelector('[data-word-filter-estado]');
    const clearButton = form.querySelector('[data-word-filter-clear]');
    const moreButton = document.querySelector('[data-word-filter-more]');
    const summary = document.querySelector('[data-word-filter-summary]');
    const submitButton = form.querySelector('button[type="submit"]');
    const rowsUrl = grid.dataset.rowsUrl;
    const SEARCH_DELAY = 250;

    let timer = null;
    let requestId = 0;

    // Sin JS el botón hace falta; con JS la búsqueda sale sola al escribir.
    if (submitButton) submitButton.hidden = true;

    const emptyNode = () => grid.querySelector('[data-word-filter-empty]');

    function setSummary(matched) {
        if (!summary) return;
        const query = (input?.value || '').trim();
        const state = estado?.value || 'all';
        if (!query && state === 'all') {
            summary.textContent = '';
            return;
        }
        const shown = grid.querySelectorAll('[data-word-filter-card]').length;
        const noun = matched === 1 ? 'coincidencia' : 'coincidencias';
        summary.textContent = shown < matched
            ? `${matched} ${noun}; mostrando ${shown}.`
            : `${matched} ${noun}.`;
    }

    function renderEmptyState(matched) {
        const existing = emptyNode();
        if (matched === 0 && !existing) {
            const node = document.createElement('div');
            node.className = 'management-empty';
            node.dataset.wordFilterEmpty = '';
            node.textContent = 'No hay filtros por palabra que coincidan.';
            grid.appendChild(node);
        } else if (matched > 0 && existing) {
            existing.remove();
        }
    }

    async function loadRows({ append }) {
        const params = new URLSearchParams();
        const query = (input?.value || '').trim();
        if (query) params.set('q', query);
        if (estado?.value && estado.value !== 'all') params.set('estado', estado.value);
        params.set('offset', append ? grid.dataset.nextOffset || '0' : '0');

        const id = ++requestId;
        if (moreButton) moreButton.disabled = true;
        try {
            const response = await fetch(`${rowsUrl}?${params}`, {
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            // Una respuesta que llega tarde no debe pisar a una búsqueda
            // posterior: al escribir rápido salen varias peticiones en vuelo.
            if (id !== requestId) return;

            if (append) {
                grid.insertAdjacentHTML('beforeend', data.html);
            } else {
                grid.innerHTML = data.html;
            }
            grid.dataset.nextOffset = String(data.next_offset);
            grid.dataset.hasMore = data.has_more ? 'true' : 'false';
            grid.dataset.matched = String(data.matched);
            if (moreButton) moreButton.hidden = !data.has_more;
            renderEmptyState(data.matched);
            setSummary(data.matched);
        } catch (error) {
            if (summary) summary.textContent = 'No se pudo cargar la lista de filtros.';
        } finally {
            if (moreButton) moreButton.disabled = false;
        }
    }

    function scheduleSearch() {
        if (clearButton) clearButton.hidden = !(input?.value || '').length;
        clearTimeout(timer);
        timer = setTimeout(() => loadRows({ append: false }), SEARCH_DELAY);
    }

    form.addEventListener('submit', (event) => {
        event.preventDefault();
        clearTimeout(timer);
        loadRows({ append: false });
    });

    input?.addEventListener('input', scheduleSearch);
    estado?.addEventListener('change', () => {
        clearTimeout(timer);
        loadRows({ append: false });
    });
    clearButton?.addEventListener('click', () => {
        if (!input) return;
        input.value = '';
        input.focus();
        scheduleSearch();
    });
    moreButton?.addEventListener('click', () => loadRows({ append: true }));

    // El pausar/activar va por fetch para no recargar: una recarga perdería la
    // búsqueda escrita y devolvería la lista a su primera tanda.
    document.addEventListener('submit', async (event) => {
        const toggleForm = event.target.closest('[data-word-filter-toggle]');
        if (!toggleForm) return;
        event.preventDefault();

        const button = toggleForm.querySelector('button');
        if (button) button.disabled = true;
        try {
            const response = await fetch(toggleForm.action, {
                method: 'POST',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                body: new FormData(toggleForm),
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            applyToggle(toggleForm.closest('[data-word-filter-card]'), data.active);
        } catch (error) {
            // Que el fallo no deje la tarjeta mintiendo sobre su estado.
            toggleForm.submit();
        } finally {
            if (button) button.disabled = false;
        }
    });

    function applyToggle(card, active) {
        if (!card) return;
        card.classList.toggle('is-inactive', !active);

        const pill = card.querySelector('.status-pill');
        if (pill) {
            pill.classList.toggle('is-active', active);
            pill.textContent = active ? 'Activo' : 'Pausado';
        }

        const word = card.querySelector('h3')?.textContent || '';
        const button = card.querySelector('[data-word-filter-toggle] button');
        if (button) {
            const label = active ? 'Pausar' : 'Activar';
            button.title = label;
            button.setAttribute('aria-label', `${label} ${word}`);
            button.querySelector('use')?.setAttribute(
                'href', active ? '#ic-filter-pause' : '#ic-filter-play',
            );
        }

        const editLink = card.querySelector('[data-word-filter-edit]');
        if (editLink) editLink.dataset.active = active ? 'true' : 'false';

        // Con la lista filtrada por estado, la tarjeta deja de pertenecer aquí.
        if ((estado?.value === 'active' && !active) || (estado?.value === 'paused' && active)) {
            loadRows({ append: false });
        }
    }
})();
