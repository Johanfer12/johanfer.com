// Mantiene al día la insignia de visitas sin recargar la página.
//
// La cabecera la pinta el context processor al renderizar, así que en una
// pestaña abierta el número se queda congelado. Aquí se vuelve a pedir cada
// minuto, solo mientras la pestaña está a la vista.
(() => {
    const link = document.querySelector('.visits-link[data-badge-url]');
    if (!link) return;

    const url = link.dataset.badgeUrl;
    const POLL_INTERVAL_MS = 60_000;
    let timer = null;
    let inFlight = false;
    let current = Number(link.dataset.badgeCount || 0);

    function render(count) {
        if (count === current) return;
        current = count;

        let badge = link.querySelector('.visits-badge');
        if (!count) {
            badge?.remove();
        } else {
            if (!badge) {
                badge = document.createElement('span');
                badge.className = 'visits-badge';
                link.appendChild(badge);
            }
            badge.textContent = count > 99 ? '99+' : String(count);
        }

        const plural = count === 1 ? 'visita' : 'visitas';
        link.title = count ? `${count} ${plural} desde Colombia` : 'Visitas';
    }

    async function refresh() {
        if (inFlight || document.hidden) return;
        inFlight = true;
        try {
            const response = await fetch(url, {
                // Sin esta cabecera el propio sondeo se registraría como visita.
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
            });
            if (!response.ok) return;
            const data = await response.json();
            if (typeof data.badge === 'number') render(data.badge);
        } catch (error) {
            // Un corte de red no tiene por qué dejar rastro: al siguiente
            // sondeo se recupera solo.
        } finally {
            inFlight = false;
        }
    }

    function start() {
        stop();
        refresh();
        timer = setInterval(refresh, POLL_INTERVAL_MS);
    }

    function stop() {
        if (timer) {
            clearInterval(timer);
            timer = null;
        }
    }

    document.addEventListener('visibilitychange', () => {
        // En una pestaña de fondo el sondeo solo gasta trabajo del servidor,
        // que aquí es una Raspberry con un worker.
        if (document.hidden) stop();
        else start();
    });

    if (!document.hidden) start();
})();
