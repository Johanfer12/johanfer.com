(() => {
    'use strict';

    const root = document.documentElement;
    const pausedClass = 'background-motion-paused';

    const pause = () => {
        root.classList.add(pausedClass);
    };

    const resume = () => {
        if (document.hidden) return;
        requestAnimationFrame(() => {
            requestAnimationFrame(() => root.classList.remove(pausedClass));
        });
    };

    if (document.hidden) pause();

    document.addEventListener('visibilitychange', () => {
        if (document.hidden) pause();
        else resume();
    });
    window.addEventListener('pagehide', pause);
    window.addEventListener('blur', pause);
    window.addEventListener('focus', resume);
})();
