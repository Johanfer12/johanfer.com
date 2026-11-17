// Aviso de que la página se ejecutó: distingue un navegador de un script que
// solo baja el HTML (home_page/bot_detection.py, «sin-javascript»). Va aquí
// porque pwa.js lo cargan todas las plantillas.
(function () {
    try {
        if (navigator.sendBeacon) {
            navigator.sendBeacon('/visitas/js/');
        } else {
            fetch('/visitas/js/', { method: 'POST', keepalive: true, credentials: 'same-origin' });
        }
    } catch (error) {
        // Sin aviso la visita solo queda marcada como robot probable.
    }
})();

// Registro del service worker. Sin él Edge no ofrece instalar la web como app.
(function () {
    if (!('serviceWorker' in navigator)) {
        return;
    }

    window.addEventListener('load', function () {
        navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function (error) {
            console.warn('No se pudo registrar el service worker:', error);
        });
    });

    // Cuando un service worker NUEVO releva al anterior, se recarga una sola vez
    // para no dejar la pestaña con una mezcla de versiones. En la primera
    // instalación no hay controlador previo y recargar solo molestaría.
    var hadController = !!navigator.serviceWorker.controller;
    var reloading = false;
    navigator.serviceWorker.addEventListener('controllerchange', function () {
        if (reloading || !hadController) {
            return;
        }
        reloading = true;
        window.location.reload();
    });
})();
