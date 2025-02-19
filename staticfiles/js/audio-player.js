document.addEventListener('DOMContentLoaded', function() {
    const buttons = document.querySelectorAll('.play-button');
    let currentlyPlaying = null;

    buttons.forEach(button => {
        const audio = button.nextElementSibling;

        button.addEventListener('click', function() {
            if (currentlyPlaying && currentlyPlaying !== audio) {
                currentlyPlaying.pause();
                currentlyPlaying.currentTime = 0;
                currentlyPlaying.previousElementSibling.classList.remove('playing');
            }

            if (audio.paused) {
                audio.play();
                button.classList.add('playing');
                currentlyPlaying = audio;
            } else {
                audio.pause();
                audio.currentTime = 0;
                button.classList.remove('playing');
                currentlyPlaying = null;
            }
        });

        audio.addEventListener('ended', function() {
            button.classList.remove('playing');
            currentlyPlaying = null;
        });
    });
}); 