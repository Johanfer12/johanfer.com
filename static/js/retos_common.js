// Lo que comparten las tres secciones de Retos (clima, economía e IA). Va
// detrás de charts_common.js y delante del script de cada sección: son scripts
// clásicos, así que estos `const` no pueden declararse otra vez en ellos.

const SIN_MOVIMIENTO = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
const ROJO = '#e0745c';
const AZUL = '#5ec4e8';
const MORADO = 'rgba(164, 124, 255, 0.85)';
const DORADO = 'rgba(226, 188, 114, 0.9)';
const LAVANDA = '#b3c4ff';

const leerDatos = (id) => JSON.parse(document.getElementById(id).textContent);

// Números con coma decimal, como en el resto de la página.
const fmt = (v, d = 2) => `${v > 0 ? '+' : ''}${v.toFixed(d).replace('.', ',')}`;
const coma = (v, d = 1) => v.toFixed(d).replace('.', ',');
// Miles con punto, al estilo de Colombia (el sitio corre con locale inglés).
const miles = (v) => Math.round(v).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');

// Animación de la línea que cuenta la historia: se dibuja de izquierda a
// derecha recortando el dataset con un rectángulo que crece. Se hace así y no
// con las animaciones de Chart.js porque estas gráficas van con
// `animation: false` (todo lo demás tiene que aparecer quieto) y porque el
// recorte acaba exactamente en el último dato, no en el borde del eje.
const revelar = {
    id: 'revelar',
    beforeInit(chart) {
        chart.$revelado = SIN_MOVIMIENTO ? 1 : 0;
    },
    beforeDatasetDraw(chart, args) {
        const dataset = chart.data.datasets[args.index];
        if (!dataset.revelar || chart.$revelado >= 1) return;
        const { ctx, chartArea: area, scales } = chart;
        // El barrido es uno solo para toda la gráfica y acaba en el último dato
        // de cualquier serie animada: así la punteada de una proyección aparece
        // cuando la línea medida ya terminó, en vez de adelantarse.
        let fin;
        // Eje lineal (años con decimales, en las nubes de puntos): el último x.
        if (scales.x.type === 'linear') {
            let ultimo = -Infinity;
            chart.data.datasets.filter((d) => d.revelar).forEach((d) => {
                d.data.forEach((p) => { if (p && p.x != null) ultimo = Math.max(ultimo, p.x); });
            });
            fin = scales.x.getPixelForValue(ultimo);
        } else {
            let ultimo = 0;
            chart.data.datasets.filter((d) => d.revelar).forEach((d) => {
                let i = d.data.length - 1;
                while (i > 0 && d.data[i] == null) i -= 1;
                ultimo = Math.max(ultimo, i);
            });
            fin = scales.x.getPixelForValue(ultimo);
        }
        const margen = 8;  // que no corte el grosor de la línea ni los puntos
        const inicio = area.left - margen;
        fin += margen;
        ctx.save();
        ctx.beginPath();
        ctx.rect(inicio, area.top - margen, (fin - inicio) * chart.$revelado, area.bottom - area.top + margen * 2);
        ctx.clip();
        chart.$recortando = true;
    },
    afterDatasetDraw(chart) {
        if (chart.$recortando) {
            chart.ctx.restore();
            chart.$recortando = false;
        }
    },
};

const animarRevelado = (chart, duracion = 2400) => {
    if (SIN_MOVIMIENTO) return;
    const inicio = performance.now();
    const paso = (ahora) => {
        const t = Math.min(1, (ahora - inicio) / duracion);
        chart.$revelado = 1 - Math.pow(1 - t, 2);  // arranca rápido y frena al final
        chart.draw();
        if (t < 1) requestAnimationFrame(paso);
    };
    requestAnimationFrame(paso);
};

// La gráfica se crea (y se anima) cuando su tarjeta entra en pantalla, no al
// abrir la página: las de abajo estarían terminadas antes de que alguien las viera.
const alEntrarEnVista = (canvasId, construir) => {
    const lienzo = document.getElementById(canvasId);
    const arrancar = () => animarRevelado(construir());
    if (!('IntersectionObserver' in window) || SIN_MOVIMIENTO) {
        arrancar();
        return;
    }
    const observador = new IntersectionObserver((entradas) => {
        if (entradas.some((e) => e.isIntersecting)) {
            observador.disconnect();
            arrancar();
        }
    }, { threshold: 0.35 });
    observador.observe(lienzo.closest('.retos-card') || lienzo);
};

const serie = (label, datos, color, extra = {}) => ({
    label,
    data: datos,
    borderColor: color,
    backgroundColor: color,
    pointRadius: 0,
    pointHoverRadius: 4,
    tension: 0.3,
    ...extra,
});

// Línea horizontal punteada de referencia (límite, meta, récord...).
const referencia = (label, n, valor, color) => ({
    label,
    data: Array(n).fill(valor),
    borderColor: color,
    borderDash: [6, 6],
    borderWidth: 1.5,
    pointRadius: 0,
    pointHoverRadius: 0,
});

const leyenda = { labels: { color: 'white', boxWidth: 14, boxHeight: 3, font: { size: 12 } } };

// Eje de categorías largo (años, meses): pocas etiquetas y sin girar.
const ejeLargo = () => categoryAxis({
    ticks: { color: TICK_COLOR, font: { size: 12 }, maxTicksLimit: isMobileChart ? 5 : 8, maxRotation: 0 },
});

const ejeValores = (formato, extra = {}) => ({
    grid: { color: GRID_COLOR },
    border: { display: false },
    ticks: { color: TICK_COLOR, font: { size: 12 }, callback: formato },
    ...extra,
});

// Opciones de una gráfica de líneas de Retos; `tooltip` da el texto de cada fila.
const opcionesLinea = ({ x = categoryAxis(), y, tooltip, mostrarLeyenda = true, extraPlugins = {} }) => ({
    animation: false,
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    scales: { x, y },
    plugins: {
        legend: mostrarLeyenda ? leyenda : { display: false },
        datalabels: { display: false },
        tooltip: {
            displayColors: true,
            filter: (item) => item.parsed.y != null,
            callbacks: { label: tooltip },
        },
        ...extraPlugins,
    },
});

// El «?» de cada límite y la «i» de cada gráfica abren el mismo modal.
document.querySelectorAll('.retos-help, .retos-info').forEach((boton) => {
    boton.addEventListener('click', () => {
        document.getElementById('retos-modal-title').textContent = boton.dataset.title;
        document.getElementById('retos-modal-text').textContent = boton.dataset.text;
        openModal('retos');
    });
});
