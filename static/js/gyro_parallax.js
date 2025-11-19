const isTouchDevice = () => {
    return (('ontouchstart' in window) ||
        (navigator.maxTouchPoints > 0) ||
        (navigator.msMaxTouchPoints > 0));
}

if (isTouchDevice() && window.DeviceOrientationEvent) {
    window.addEventListener('deviceorientation', function(event) {
        const body = document.body;
        let { beta, gamma } = event;

        // Constrain the values to a range of -45 to 45
        beta = Math.max(-45, Math.min(45, beta));
        gamma = Math.max(-45, Math.min(45, gamma));

        // Map the gamma value (-45 to 45) to a background-position-x percentage (40% to 60%)
        const x = 50 + (gamma / 45) * 10;

        // Map the beta value (-45 to 45) to a background-position-y percentage (40% to 60%)
        const y = 50 + (beta / 45) * 10;

        // Request animation frame to avoid performance issues
        requestAnimationFrame(function() {
            body.style.backgroundPosition = `${x}% ${y}%`;
        });
    });
} else {
    document.addEventListener('mousemove', function(event) {
        const { clientX, clientY } = event;
        const { innerWidth, innerHeight } = window;
        const body = document.body;

        const x = 50 + (clientX / innerWidth - 0.5) * 20; // Maps mouse X to 40-60 range
        const y = 50 + (clientY / innerHeight - 0.5) * 20; // Maps mouse Y to 40-60 range

        requestAnimationFrame(function() {
            body.style.backgroundPosition = `${x}% ${y}%`;
        });
    });
}
