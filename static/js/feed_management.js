(() => {
    const tabs = Array.from(document.querySelectorAll('[data-management-tab]'));
    const panels = Array.from(document.querySelectorAll('[data-management-panel]'));

    if (!tabs.length || !panels.length) return;

    const validPanelIds = new Set(panels.map((panel) => panel.id));

    function activate(panelId, { updateHash = false, focus = false } = {}) {
        const selectedId = validPanelIds.has(panelId) ? panelId : panels[0].id;

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
})();
