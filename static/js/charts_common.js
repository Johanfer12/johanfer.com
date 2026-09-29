// Base compartida de las tres páginas de gráficas: libros (stats.js), música
// (spotify_stats.js) y Mi TV (watching_stats.js).
//
// Los tres ficheros repetían este bloque palabra por palabra. Tiene que ir
// ANTES que el script de cada página: son scripts clásicos, así que un `const`
// declarado dos veces con el mismo nombre es un SyntaxError, no una redefinición.
//
// Lo que no está aquí es lo que solo usa una página: PIE_COLORS y compactLabel
// (música) y POLAR_COLORS (Mi TV).

Chart.register(ChartDataLabels);

// Tooltip con la superficie de las tarjetas en vez de la caja negra por
// defecto. Va en Chart.defaults porque cada gráfica reescribe `plugins` entero.
Object.assign(Chart.defaults.plugins.tooltip, {
    backgroundColor: 'rgba(11, 20, 44, 0.96)',
    borderColor: 'rgba(207, 220, 241, 0.2)',
    borderWidth: 1,
    cornerRadius: 8,
    padding: 10,
    titleColor: '#f2f5fb',
    bodyColor: 'rgba(238, 243, 251, 0.82)',
    displayColors: false,
    caretSize: 6,
});

// Paleta del sitio, derivada del gradiente azul/morado del home.
// `bg`/`border` los usa news_stats.js; `top`, `bottom` y `glow` son del
// degradado y el brillo de barStyle.
const PALETTE = {
    blue: {
        bg: 'rgba(108, 142, 255, 0.62)', border: 'rgba(141, 168, 255, 0.95)',
        top: '#b3c4ff', bottom: '#4a5fd1', glow: 'rgba(110, 138, 255, 0.55)',
    },
    purple: {
        bg: 'rgba(164, 124, 255, 0.58)', border: 'rgba(186, 156, 255, 0.95)',
        top: '#d5bdff', bottom: '#6f47cf', glow: 'rgba(160, 118, 255, 0.55)',
    },
    gold: {
        bg: 'rgba(222, 188, 122, 0.65)', border: 'rgba(240, 212, 150, 0.95)',
        top: '#f7e2ae', bottom: '#b3843d', glow: 'rgba(226, 186, 110, 0.5)',
    },
};
const GRID_COLOR = 'rgba(255, 255, 255, 0.05)';
const TICK_COLOR = 'rgba(238, 243, 251, 0.78)';

// Degradado a lo largo de TODO el eje de valores, no de cada barra: una barra
// baja solo llega a los tonos oscuros y la más alta alcanza el claro, así que
// el color también cuenta cuánto mide. Se recalcula con el área de la gráfica
// (que no existe hasta el primer pintado) y se guarda por tamaño.
const valueGradient = (tone, horizontal) => {
    let cache = null;
    return (ctx) => {
        const { chart } = ctx;
        const area = chart.chartArea;
        if (!area) return tone.bottom;
        const key = `${area.left},${area.right},${area.top},${area.bottom}`;
        if (cache && cache.key === key) return cache.gradient;
        const gradient = horizontal
            ? chart.ctx.createLinearGradient(area.left, 0, area.right, 0)
            : chart.ctx.createLinearGradient(0, area.bottom, 0, area.top);
        gradient.addColorStop(0, tone.bottom);
        gradient.addColorStop(1, tone.top);
        cache = { key, gradient };
        return gradient;
    };
};

// Barras con degradado, punta redondeada y un brillo suave del mismo tono
// (lo pinta el plugin barGlow). Antes eran el relleno translúcido con borde
// que trae Chart.js por defecto, que es justo lo que delata una gráfica sin
// tocar.
const barStyle = (tone, { horizontal = false } = {}) => ({
    backgroundColor: valueGradient(tone, horizontal),
    hoverBackgroundColor: tone.top,
    borderWidth: 0,
    borderRadius: 6,
    borderSkipped: 'start',
    maxBarThickness: 44,
    glow: tone.glow,
});

// Brillo: sombra difusa del color de la serie detrás de sus barras. Solo actúa
// en los datasets que declaran `glow`, así que news_stats.js no cambia.
Chart.register({
    id: 'barGlow',
    beforeDatasetDraw(chart, args) {
        const glow = chart.data.datasets[args.index].glow;
        if (!glow) return;
        const { ctx } = chart;
        ctx.save();
        ctx.shadowColor = glow;
        ctx.shadowBlur = isMobileChart ? 10 : 16;
        ctx.shadowOffsetY = 2;
    },
    afterDatasetDraw(chart, args) {
        if (chart.data.datasets[args.index].glow) chart.ctx.restore();
    },
});

// Eje de categorías (años, estrellas, décadas): solo sus etiquetas.
const categoryAxis = (extra = {}) => ({
    grid: { display: false },
    border: { display: false },
    ticks: {
        color: TICK_COLOR,
        font: { size: isMobileChart ? 11 : 12 },
    },
    ...extra,
});

// Eje de valores de una gráfica que ya pinta la cifra sobre cada barra: se
// oculta entero, con su rejilla. Mostrarlo repetía cada dato dos veces.
const valueAxis = (values, extra = {}) => ({
    display: false,
    beginAtZero: true,
    suggestedMax: paddedAxisMax(values),
    ...extra,
});

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

// Etiqueta del valor encima de cada barra. Libros y Mi TV la repetian entera;
// lo unico que cambia entre sus tres usos es el recorte, el desplazamiento, el
// tamano y el formato, asi que solo eso se pasa.
const valueLabels = ({
    clamp = false,
    offset = 0,
    size = isMobileChart ? 9 : 11,
    formatter = formatNumber,
} = {}) => ({
    // El máximo de cada serie en blanco y algo más grande; el resto, atenuado.
    // Es lo primero que se busca en una gráfica así y ahora se ve sin buscarlo.
    color: (ctx) => (isSeriesMax(ctx) ? '#ffffff' : 'rgba(238, 243, 251, 0.62)'),
    anchor: 'end',
    align: 'end',
    clamp,
    offset,
    font: (ctx) => ({
        weight: 'bold',
        size: isSeriesMax(ctx) ? size + 2 : size,
    }),
    formatter,
});

const isSeriesMax = (ctx) => {
    const data = ctx.dataset.data;
    const value = data[ctx.dataIndex];
    return value > 0 && value === Math.max(...data);
};
