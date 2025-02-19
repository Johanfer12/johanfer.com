document.addEventListener('DOMContentLoaded', function() {
    var floatingButton = document.querySelector('.floating-button');
    var header = document.querySelector('.header');
    var headerHeight = header.offsetHeight;

    window.addEventListener('scroll', function() {
        if (window.pageYOffset > headerHeight) {
            floatingButton.style.display = 'block';
        } else {
            floatingButton.style.display = 'none';
        }
    });

    floatingButton.addEventListener('click', function(e) {
        e.preventDefault();
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    });
});