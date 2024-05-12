window.onscroll = function() {
    var floatingButton = document.querySelector('.floating-button');
    var header = document.querySelector('.header');
    var headerHeight = header.offsetHeight;

    if (window.pageYOffset > headerHeight) {
        floatingButton.style.display = 'block';
    } else {
        floatingButton.style.display = 'none';
    }
};