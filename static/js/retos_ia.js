// Gráficas de Retos → Inteligencia artificial. La base está en charts_common.js
// y retos_common.js.

const COMPUTO = leerDatos('retos-computo');
const HORIZONTE = leerDatos('retos-horizonte');
const PRECIO = leerDatos('retos-precio');
const CAPEX = leerDatos('retos-capex');
const ELECTRICIDAD = leerDatos('retos-electricidad');
const USUARIOS = leerDatos('retos-usuarios');

const fechaCorta = (f) => {
    const [anio, mes] = f.split('-');
    return `${MESES[+mes - 1]} ${anio}`;
};

// Eje de años para las nubes de puntos (x = año con decimales).
const ejeAnios = (desde, hasta, paso = 1) => ({
    type: 'linear',
    min: desde,
    max: hasta,
    grid: { display: false },
    border: { color: GRID_COLOR },
    // Las rayas caen en años enteros aunque el eje empiece a mitad de año.
    afterBuildTicks: (eje) => {
        const ticks = [];
        for (let a = Math.ceil(desde); a <= hasta; a += 1) if (a % paso === 0) ticks.push({ value: a });
        eje.ticks = ticks;
    },
    ticks: { color: TICK_COLOR, font: { size: 12 }, maxRotation: 0, callback: (v) => v },
});

// Eje logarítmico: solo se rotulan las potencias que se piden.
const ejeLog = (rotulos, extra = {}) => ({
    type: 'logarithmic',
    grid: { color: GRID_COLOR },
    border: { display: false },
    afterBuildTicks: (eje) => {
        eje.ticks = Object.keys(rotulos).map(Number).filter((v) => v >= eje.min && v <= eje.max).map((value) => ({ value }));
    },
    ticks: { color: TICK_COLOR, font: { size: 12 }, callback: (v) => rotulos[v] ?? '' },
    ...extra,
});

const opcionesPuntos = ({ x, y, tooltip, mostrarLeyenda = true }) => ({
    animation: false,
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'nearest', intersect: false },
    scales: { x, y },
    plugins: {
        legend: mostrarLeyenda ? leyenda : { display: false },
        datalabels: { display: false },
        tooltip: { displayColors: false, callbacks: { title: () => '', label: tooltip } },
    },
});

const flop = (v) => {
    const exp = Math.floor(Math.log10(v));
    return `${coma(v / 10 ** exp, 1)} × 10^${exp} FLOP`;
};

// Cómputo de entrenamiento: modelos de frontera en rojo, el resto en lavanda.
const POTENCIAS_FLOP = {};
for (let e = 15; e <= 30; e += 3) POTENCIAS_FLOP[10 ** e] = `10^${e}`;
alEntrarEnVista('computoChart', () => new Chart(document.getElementById('computoChart'), {
    type: 'scatter',
    plugins: [revelar],
    data: {
        datasets: [
            { label: 'De frontera', data: COMPUTO.filter((p) => p.frontera), backgroundColor: ROJO, pointRadius: 3.5, pointHoverRadius: 6, revelar: true },
            { label: 'Otros notables', data: COMPUTO.filter((p) => !p.frontera), backgroundColor: LAVANDA, pointRadius: 3, pointHoverRadius: 6, revelar: true },
        ],
    },
    options: opcionesPuntos({
        x: ejeAnios(2010, 2027, isMobileChart ? 4 : 2),
        y: ejeLog(POTENCIAS_FLOP),
        tooltip: (ctx) => [`${ctx.raw.modelo} (${fechaCorta(ctx.raw.fecha)})`, flop(ctx.raw.y)],
    }),
}));

// Horizonte de METR: minutos en escala logarítmica, unidos en orden de fecha.
const ROTULOS_TIEMPO = { 0.1: '6 s', 1: '1 min', 10: '10 min', 60: '1 h', 480: '8 h', 2400: '40 h' };
const duracion = (min) => (min >= 90 ? `${coma(min / 60, 1)} h` : min >= 1 ? `${coma(min, 0)} min` : `${coma(min * 60, 0)} s`);
const punteros = HORIZONTE.filter((p) => p.sota).sort((a, b) => a.x - b.x);
alEntrarEnVista('horizonteChart', () => new Chart(document.getElementById('horizonteChart'), {
    type: 'scatter',
    plugins: [revelar],
    data: {
        datasets: [
            { label: 'El mejor de su momento', data: punteros, backgroundColor: ROJO, borderColor: ROJO, showLine: true, borderWidth: 2, pointRadius: 4, pointHoverRadius: 6, revelar: true },
            { label: 'Otros', data: HORIZONTE.filter((p) => !p.sota), backgroundColor: LAVANDA, pointRadius: 3.5, pointHoverRadius: 6, revelar: true },
        ],
    },
    options: opcionesPuntos({
        x: ejeAnios(2019, 2027, isMobileChart ? 2 : 1),
        y: ejeLog(ROTULOS_TIEMPO, { min: 0.05, max: 4000 }),
        tooltip: (ctx) => [
            `${ctx.raw.modelo} (${fechaCorta(ctx.raw.fecha)})`,
            `${duracion(ctx.raw.y)} (margen: ${duracion(ctx.raw.bajo)} a ${duracion(ctx.raw.alto)})`,
        ],
    }),
}));

// Precio de inferencia: el modelo más barato para cada nota, en escalera.
const ROTULOS_PRECIO = { 0.01: '0,01 $', 0.1: '0,1 $', 1: '1 $', 10: '10 $', 100: '100 $' };
const escalera = (label, datos, color, extra = {}) => ({
    label, data: datos, borderColor: color, backgroundColor: color, showLine: true, stepped: 'before',
    borderWidth: 2, pointRadius: 3.5, pointHoverRadius: 6, revelar: true, ...extra,
});
alEntrarEnVista('precioChart', () => new Chart(document.getElementById('precioChart'), {
    type: 'scatter',
    plugins: [revelar],
    data: {
        datasets: [
            escalera('GPT-4 en MMLU', PRECIO.mmlu_nivel_gpt4, ROJO, { borderWidth: 3.5, order: -1 }),
            escalera('GPT-4 en GPQA', PRECIO.gpqa_nivel_gpt4, DORADO),
            escalera('GPT-3.5 en MMLU', PRECIO.mmlu_nivel_gpt35, AZUL),
        ],
    },
    options: opcionesPuntos({
        x: ejeAnios(2022.75, 2025.25, 1),
        y: ejeLog(ROTULOS_PRECIO, { min: 0.03, max: 60 }),
        tooltip: (ctx) => [`${ctx.raw.modelo} (${fechaCorta(ctx.raw.fecha)})`, `${coma(ctx.raw.y, ctx.raw.y < 1 ? 3 : 2)} $ por millón de tokens`],
    }),
}));

// Capex: barras apiladas por empresa; la de 2026 (previsión) va más tenue.
const EMPRESAS = [
    ['microsoft', 'Microsoft', '#5ec4e8'],
    ['alphabet', 'Alphabet', '#e2bc72'],
    ['amazon', 'Amazon', '#e0745c'],
    ['meta', 'Meta', '#a47cff'],
];
const ultimaBarra = CAPEX.anios.length - 1;
alEntrarEnVista('capexChart', () => new Chart(document.getElementById('capexChart'), {
    type: 'bar',
    data: {
        labels: CAPEX.anios.map((a) => a.replace(' (previsión)', '*')),
        datasets: EMPRESAS.map(([clave, nombre, color]) => ({
            label: nombre,
            data: CAPEX[clave],
            backgroundColor: CAPEX[clave].map((_, i) => (i === ultimaBarra ? `${color}66` : color)),
            borderColor: color,
            borderWidth: CAPEX[clave].map((_, i) => (i === ultimaBarra ? 1.5 : 0)),
            borderRadius: 3,
            stack: 'total',
        })),
    },
    options: {
        animation: false,
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        scales: {
            x: categoryAxis({ stacked: true, ticks: { color: TICK_COLOR, font: { size: 12 }, maxRotation: 0, autoSkip: true } }),
            y: ejeValores((v) => v, { stacked: true }),
        },
        plugins: {
            legend: { labels: { color: 'white', boxWidth: 12, boxHeight: 12, font: { size: 12 } } },
            datalabels: { display: false },
            tooltip: {
                displayColors: true,
                callbacks: {
                    title: (items) => CAPEX.anios[items[0].dataIndex],
                    label: (ctx) => `${ctx.dataset.label}: ${coma(ctx.parsed.y)} mil millones USD`,
                    footer: (items) => `Total: ${miles(items.reduce((s, i) => s + i.parsed.y, 0))} mil millones`,
                },
            },
        },
    },
}));

// Electricidad: medido, caso base punteado y la franja entre escenarios.
alEntrarEnVista('electricidadChart', () => new Chart(document.getElementById('electricidadChart'), {
    type: 'line',
    plugins: [revelar],
    data: {
        labels: ELECTRICIDAD.anios,
        datasets: [
            serie('Medido', ELECTRICIDAD.historico, AZUL, { borderWidth: 3.5, backgroundColor: 'rgba(94, 196, 232, 0.16)', fill: true, order: -1, revelar: true }),
            serie('Caso base (AIE)', ELECTRICIDAD.caso_base, LAVANDA, { borderWidth: 3, borderDash: [3, 6], borderCapStyle: 'round', revelar: true }),
            serie('Escenario bajo', ELECTRICIDAD.bajo, 'rgba(179, 196, 255, 0)', { pointHoverRadius: 0 }),
            serie('Escenario alto', ELECTRICIDAD.alto, 'rgba(179, 196, 255, 0)', { pointHoverRadius: 0, backgroundColor: 'rgba(179, 196, 255, 0.14)', fill: '-1' }),
        ],
    },
    options: opcionesLinea({
        x: ejeLargo(),
        y: ejeValores((v) => miles(v), { min: 0 }),
        tooltip: (ctx) => `${ctx.dataset.label}: ${miles(ctx.parsed.y)} TWh`,
        extraPlugins: {
            legend: { labels: { ...leyenda.labels, filter: (item) => !item.text.startsWith('Escenario') } },
        },
    }),
}));

// Usuarios semanales de ChatGPT, en millones.
alEntrarEnVista('usuariosChart', () => new Chart(document.getElementById('usuariosChart'), {
    type: 'scatter',
    plugins: [revelar],
    data: {
        datasets: [{
            label: 'Usuarios semanales',
            data: USUARIOS,
            borderColor: ROJO,
            backgroundColor: 'rgba(224, 116, 92, 0.16)',
            pointBackgroundColor: ROJO,
            showLine: true,
            fill: 'origin',
            tension: 0.25,
            borderWidth: 3,
            pointRadius: 4,
            pointHoverRadius: 6,
            revelar: true,
        }],
    },
    options: opcionesPuntos({
        x: ejeAnios(2023.5, 2026.5, 1),
        y: ejeValores((v) => `${miles(v)} M`, { min: 0, max: 1000 }),
        tooltip: (ctx) => [fechaCorta(ctx.raw.fecha), `${miles(ctx.raw.y)} millones a la semana`],
        mostrarLeyenda: false,
    }),
}));
