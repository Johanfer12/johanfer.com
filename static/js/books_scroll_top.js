document.addEventListener('DOMContentLoaded', function () {
    const scrollTopBtn = document.getElementById('bookScrollTopBtn');
    if (!scrollTopBtn) {
        return;
    }

    const updateVisibility = () => {
        const threshold = Math.max(window.innerHeight * 1.5, 900);
        scrollTopBtn.style.display = window.scrollY > threshold ? 'flex' : 'none';
    };

    window.addEventListener('scroll', updateVisibility, { passive: true });
    window.addEventListener('resize', updateVisibility);
    updateVisibility();

    scrollTopBtn.addEventListener('click', function () {
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });
});
