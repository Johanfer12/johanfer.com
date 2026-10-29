(() => {
    'use strict';

    // Alta rápida de una palabra filtro desde el menú flotante del feed, sin
    // pasar por la página de configuración. El POST va a la misma vista que el
    // formulario de configuración, que responde JSON a las peticiones AJAX.
    const modal = document.getElementById('news-filter-modal');
    const openButton = document.getElementById('filterWordBtn');
    if (!modal || !openButton) return;

    const form = document.getElementById('news-filter-form');
    const input = document.getElementById('news-filter-word');
    const status = document.getElementById('news-filter-status');
    const submit = form.querySelector('.news-filter-submit');
    const CLOSE_AFTER_SUCCESS_MS = 1200;
    let closeTimer = null;

    const setStatus = (message, {error = false} = {}) => {
        status.textContent = message;
        status.classList.toggle('is-error', error);
        status.classList.toggle('is-success', !error && !!message);
    };

    const openModal = () => {
        clearTimeout(closeTimer);
        // Lo seleccionado en una tarjeta es casi siempre la palabra que se
        // quiere filtrar: se ofrece ya escrita.
        const selection = String(window.getSelection?.() || '').trim().replace(/\s+/g, ' ');
        input.value = selection.length <= 100 ? selection : '';
        setStatus('');
        submit.disabled = false;
        modal.hidden = false;
        document.body.classList.add('comments-modal-open');
        input.focus();
        input.select();
    };

    const closeModal = () => {
        if (modal.hidden) return;
        clearTimeout(closeTimer);
        modal.hidden = true;
        document.body.classList.remove('comments-modal-open');
        openButton.focus({preventScroll: true});
    };

    openButton.addEventListener('click', openModal);
    modal.addEventListener('click', (event) => {
        if (event.target.closest('[data-filter-close]')) closeModal();
    });
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && !modal.hidden) closeModal();
    });

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        if (!input.value.trim()) {
            setStatus('Escribe una palabra o frase.', {error: true});
            input.focus();
            return;
        }

        submit.disabled = true;
        setStatus('Guardando…');
        try {
            const response = await fetch(form.action, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {'X-Requested-With': 'XMLHttpRequest'},
                body: new FormData(form),
            });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok || payload.status !== 'success') {
                throw new Error(payload.message || 'No se pudo crear el filtro.');
            }
            setStatus(payload.message);
            closeTimer = setTimeout(closeModal, CLOSE_AFTER_SUCCESS_MS);
        } catch (error) {
            setStatus(error.message, {error: true});
            submit.disabled = false;
            input.focus();
        }
    });
})();
