// Barra de secciones del móvil: se esconde al bajar y vuelve al subir, para
// dejar la pantalla al contenido mientras se lee. Solo actúa cuando la barra
// está fija abajo (ver header.css, max-width: 720px); en escritorio va dentro
// de la cabecera y no se toca.
(() => {
    const bar = document.querySelector('.header-sections');
    if (!bar) return;

    const mobile = window.matchMedia('(max-width: 720px)');
    // Por debajo de esto un gesto es un temblor del dedo, no una intención.
    const THRESHOLD = 8;
    // Cerca de arriba o del final siempre se ve: arriba no estorba, y al final
    // es por donde se sigue a otra sección.
    const EDGE = 60;

    let lastY = window.scrollY;
    let ticking = false;

    // La clase en <html> es la que baja los botones flotantes (header.css).
    const setHidden = (hidden) => {
        bar.classList.toggle('is-hidden', hidden);
        document.documentElement.classList.toggle('tabbar-hidden', hidden);
    };

    const update = () => {
        ticking = false;
        if (!mobile.matches) {
            setHidden(false);
            return;
        }
        const y = window.scrollY;
        const nearTop = y < EDGE;
        const nearBottom = window.innerHeight + y >= document.documentElement.scrollHeight - EDGE;
        if (nearTop || nearBottom) {
            setHidden(false);
        } else if (y - lastY > THRESHOLD) {
            setHidden(true);
        } else if (lastY - y > THRESHOLD) {
            setHidden(false);
        } else {
            return;  // Movimiento corto: se acumula hasta pasar el umbral.
        }
        lastY = y;
    };

    window.addEventListener('scroll', () => {
        if (!ticking) {
            ticking = true;
            requestAnimationFrame(update);
        }
    }, { passive: true });

    mobile.addEventListener('change', update);
    // Si se llega a ella con el teclado, que aparezca.
    bar.addEventListener('focusin', () => setHidden(false));
})();
