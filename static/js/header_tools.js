(() => {
    const menu = document.querySelector('.header-tools');
    if (!menu) return;
    document.addEventListener('click', event => {
        if (!menu.contains(event.target)) menu.open = false;
    });
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && menu.open) {
            menu.open = false;
            menu.querySelector('summary').focus();
        }
    });
    menu.addEventListener('focusout', event => {
        if (!menu.contains(event.relatedTarget)) menu.open = false;
    });
})();
