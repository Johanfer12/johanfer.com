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

    document.querySelectorAll('[data-word-filter-edit]').forEach((button) => {
        button.addEventListener('click', (event) => {
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
    });

    editModal.querySelectorAll('[data-modal-close]').forEach((button) => {
        button.addEventListener('click', () => editModal.close());
    });

    editModal.addEventListener('click', (event) => {
        if (event.target === editModal) editModal.close();
    });
})();
