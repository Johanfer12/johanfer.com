(() => {
    const isSmallScreen = window.matchMedia('(max-width: 900px)').matches;
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (isSmallScreen || reduceMotion) return;

    let ticking = false;
    let nextX = 50;
    let nextY = 50;

    const flush = () => {
        document.body.style.backgroundPosition = `${nextX}% ${nextY}%`;
        ticking = false;
    };

    const schedule = () => {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(flush);
    };

    document.addEventListener('mousemove', (event) => {
        const { clientX, clientY } = event;
        const { innerWidth, innerHeight } = window;
        nextX = 50 + (clientX / innerWidth - 0.5) * 20;
        nextY = 50 + (clientY / innerHeight - 0.5) * 20;
        schedule();
    }, { passive: true });
})();
