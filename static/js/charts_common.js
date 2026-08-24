// Base compartida de las tres páginas de gráficas: libros (stats.js), música
// (spotify_stats.js) y Mi TV (watching_stats.js).
//
// Los tres ficheros repetían este bloque palabra por palabra. Tiene que ir
// ANTES que el script de cada página: son scripts clásicos, así que un `const`
// declarado dos veces con el mismo nombre es un SyntaxError, no una redefinición.
//
// Lo que no está aquí es lo que solo usa una página: PIE_COLORS y compactLabel
// (música), POLAR_COLORS (Mi TV) y barValueLabels (libros).

Chart.register(ChartDataLabels);

// Paleta del sitio, derivada del gradiente azul/morado del home.
const PALETTE = {
    blue: { bg: 'rgba(108, 142, 255, 0.62)', border: 'rgba(141, 168, 255, 0.95)' },
    purple: { bg: 'rgba(164, 124, 255, 0.58)', border: 'rgba(186, 156, 255, 0.95)' },
    gold: { bg: 'rgba(222, 188, 122, 0.65)', border: 'rgba(240, 212, 150, 0.95)' },
};
const GRID_COLOR = 'rgba(255, 255, 255, 0.05)';

const isMobileChart = window.innerWidth < 768;
const formatNumber = (value) => new Intl.NumberFormat('es-CO').format(value);

// Deja aire sobre la barra más alta para que su etiqueta no toque el borde.
const paddedAxisMax = (values) => {
    const max = Math.max(...values, 0);
    return max > 0 ? Math.ceil(max * 1.18) : undefined;
};

const chartDefaults = {
    devicePixelRatio: 2,
    animation: {
        // Sin animación: en la Pi los reflows del arranque se notaban.
        duration: 0
    },
    layout: {
        padding: isMobileChart ? 8 : 0
    }
};

const commonOptions = {
    ...chartDefaults,
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
        legend: {
            labels: {
                color: 'white',
                boxWidth: isMobileChart ? 12 : 40,
                padding: isMobileChart ? 10 : 12,
                font: {
                    size: isMobileChart ? 11 : 12
                }
            }
        }
    },
    scales: {
        y: {
            ticks: { color: 'white' },
            grid: { color: GRID_COLOR }
        },
        x: {
            ticks: { color: 'white' },
            grid: { color: GRID_COLOR }
        }
    }
};
