// Gráficas de Retos → Cambio climático. La base está en charts_common.js y
// retos_common.js.

const LIMITES = leerDatos('retos-limites');
const NINO = leerDatos('retos-nino34');
const MAR = leerDatos('retos-mar');
const CO2 = leerDatos('retos-co2');
const AIRE = leerDatos('retos-aire');
const NIVEL = leerDatos('retos-nivel');

const CRUZADO = ROJO;
const SEGURO = AZUL;

// Nueve porciones iguales: rojas las superadas, azules las que aguantan.
new Chart(document.getElementById('boundariesChart'), {
    type: 'doughnut',
    data: {
        labels: LIMITES.map((l) => l.nombre),
        datasets: [{
            data: LIMITES.map(() => 1),
            backgroundColor: LIMITES.map((l) => (l.superado ? CRUZADO : SEGURO)),
            borderWidth: 0,
            borderRadius: 4,
            spacing: 3,
        }],
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '66%',
        plugins: {
            legend: { display: false },
            datalabels: { display: false },
            tooltip: {
                callbacks: {
                    label: (ctx) => (LIMITES[ctx.dataIndex].superado ? 'Superado' : 'Dentro del margen seguro'),
                },
            },
        },
    },
});

// Anomalía mensual de Niño 3.4: 2026 contra los dos super El Niño.
alEntrarEnVista('ninoChart', () => new Chart(document.getElementById('ninoChart'), {
    type: 'line',
    plugins: [revelar],
    data: {
        labels: MESES,
        datasets: [
            serie('1997', NINO['1997'], 'rgba(164, 124, 255, 0.75)', { borderWidth: 2 }),
            serie('2015', NINO['2015'], 'rgba(226, 188, 114, 0.85)', { borderWidth: 2 }),
            serie('2026', NINO['2026'], '#e0745c', { borderWidth: 4, pointRadius: 3, order: -1, revelar: true }),
        ],
    },
    options: {
        animation: false,
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        scales: {
            x: categoryAxis(),
            y: {
                grid: { color: GRID_COLOR },
                border: { display: false },
                ticks: { color: TICK_COLOR, font: { size: 12 }, callback: (v) => `${fmt(v, 1)}°` },
            },
        },
        plugins: {
            legend: leyenda,
            datalabels: { display: false },
            tooltip: {
                displayColors: true,
                callbacks: { label: (ctx) => `${ctx.dataset.label}: ${fmt(ctx.parsed.y)} °C` },
            },
        },
    },
}));

// Temperatura media de los océanos: 2026 frente a los tres años anteriores.
alEntrarEnVista('marChart', () => new Chart(document.getElementById('marChart'), {
    type: 'line',
    plugins: [revelar],
    data: {
        labels: MESES,
        datasets: [
            serie('2023', MAR['2023'], 'rgba(164, 124, 255, 0.75)', { borderWidth: 2 }),
            serie('2024', MAR['2024'], 'rgba(226, 188, 114, 0.85)', { borderWidth: 2 }),
            serie('2025', MAR['2025'], 'rgba(94, 196, 232, 0.8)', { borderWidth: 2 }),
            serie('2026', MAR['2026'], '#e0745c', { borderWidth: 4, pointRadius: 3, order: -1, revelar: true }),
        ],
    },
    options: {
        animation: false,
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        scales: {
            x: categoryAxis(),
            y: {
                min: 0.6,
                grid: { color: GRID_COLOR },
                border: { display: false },
                ticks: { color: TICK_COLOR, font: { size: 12 }, callback: (v) => `${fmt(v, 1)}°` },
            },
        },
        plugins: {
            legend: leyenda,
            datalabels: { display: false },
            tooltip: {
                displayColors: true,
                callbacks: { label: (ctx) => `${ctx.dataset.label}: ${fmt(ctx.parsed.y)} °C` },
            },
        },
    },
}));

// CO₂ en Mauna Loa, media anual, con la referencia preindustrial y el límite seguro.
const linea = (label, valor, color) => ({
    label,
    data: CO2.anios.map(() => valor),
    borderColor: color,
    borderDash: [6, 6],
    borderWidth: 1.5,
    pointRadius: 0,
    pointHoverRadius: 0,
});

alEntrarEnVista('co2Chart', () => new Chart(document.getElementById('co2Chart'), {
    type: 'line',
    plugins: [revelar],
    data: {
        labels: CO2.anios,
        datasets: [
            {
                label: 'CO₂ (ppm)',
                data: CO2.valores,
                borderColor: '#e0745c',
                backgroundColor: 'rgba(224, 116, 92, 0.18)',
                fill: true,
                borderWidth: 3,
                pointRadius: 0,
                pointHoverRadius: 4,
                tension: 0.2,
                order: -1,
                revelar: true,
            },
            linea('Límite seguro (350)', CO2.limite, '#5ec4e8'),
            linea('Preindustrial (280)', CO2.preindustrial, 'rgba(238, 243, 251, 0.6)'),
        ],
    },
    options: {
        animation: false,
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        scales: {
            x: categoryAxis({ ticks: { color: TICK_COLOR, font: { size: 12 }, maxTicksLimit: isMobileChart ? 5 : 8, maxRotation: 0 } }),
            y: {
                min: 260,
                grid: { color: GRID_COLOR },
                border: { display: false },
                ticks: { color: TICK_COLOR, font: { size: 12 } },
            },
        },
        plugins: {
            legend: leyenda,
            datalabels: { display: false },
            tooltip: {
                displayColors: true,
                callbacks: { label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(ctx.datasetIndex ? 0 : 1).replace('.', ',')}` },
            },
        },
    },
}));

// Temperatura del aire: anomalía anual sobre 1850-1900, con la meta de París.
// El punto de 2026 es lo que va del año: va aparte para que no parezca un año completo.
alEntrarEnVista('airChart', () => new Chart(document.getElementById('airChart'), {
    type: 'line',
    plugins: [revelar],
    data: {
        labels: AIRE.anios,
        datasets: [
            {
                label: 'Anomalía anual',
                data: AIRE.valores,
                borderColor: '#e0745c',
                backgroundColor: 'rgba(224, 116, 92, 0.16)',
                fill: true,
                borderWidth: 2.5,
                pointRadius: 0,
                pointHoverRadius: 4,
                tension: 0.25,
                order: -1,
                revelar: true,
            },
            {
                label: AIRE.etiqueta_2026,
                data: AIRE.anios.map((a) => (a === 2026 ? AIRE.acumulado_2026 : null)),
                borderColor: '#ffffff',
                backgroundColor: '#e0745c',
                borderWidth: 2,
                pointRadius: 6,
                pointHoverRadius: 7,
                showLine: false,
                order: -2,
                revelar: true,
            },
            {
                label: 'Meta de París (1,5)',
                data: AIRE.anios.map(() => AIRE.objetivo),
                borderColor: '#5ec4e8',
                borderDash: [6, 6],
                borderWidth: 1.5,
                pointRadius: 0,
                pointHoverRadius: 0,
            },
        ],
    },
    options: {
        animation: false,
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        scales: {
            x: categoryAxis({ ticks: { color: TICK_COLOR, font: { size: 12 }, maxTicksLimit: isMobileChart ? 5 : 8, maxRotation: 0 } }),
            y: {
                grid: { color: GRID_COLOR },
                border: { display: false },
                ticks: { color: TICK_COLOR, font: { size: 12 }, callback: (v) => `${fmt(v, 1)}°` },
            },
        },
        plugins: {
            legend: leyenda,
            datalabels: { display: false },
            tooltip: {
                displayColors: true,
                callbacks: {
                    label: (ctx) => `${ctx.dataset.label}: ${fmt(ctx.parsed.y)} °C`,
                },
            },
        },
    },
}));

// Nivel del mar: centímetros sobre 1993, con la tendencia punteada hasta 2030.
alEntrarEnVista('nivelChart', () => new Chart(document.getElementById('nivelChart'), {
    type: 'line',
    plugins: [revelar],
    data: {
        labels: NIVEL.anios,
        datasets: [
            {
                label: 'Medido por satélite',
                data: NIVEL.medido,
                borderColor: '#5ec4e8',
                backgroundColor: 'rgba(94, 196, 232, 0.16)',
                fill: true,
                borderWidth: 3,
                pointRadius: 0,
                pointHoverRadius: 4,
                tension: 0.25,
                order: -1,
                revelar: true,
            },
            {
                label: 'Tendencia hacia 2030',
                data: NIVEL.proyeccion,
                borderColor: '#b3c4ff',
                borderDash: [3, 6],
                borderCapStyle: 'round',
                borderWidth: 3,
                pointRadius: 0,
                pointHoverRadius: 4,
                tension: 0.25,
                revelar: true,
            },
        ],
    },
    options: {
        animation: false,
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        scales: {
            x: categoryAxis({ ticks: { color: TICK_COLOR, font: { size: 12 }, maxTicksLimit: isMobileChart ? 5 : 8, maxRotation: 0 } }),
            y: {
                min: 0,
                grid: { color: GRID_COLOR },
                border: { display: false },
                ticks: { color: TICK_COLOR, font: { size: 12 }, callback: (v) => `${v} cm` },
            },
        },
        plugins: {
            legend: leyenda,
            datalabels: { display: false },
            tooltip: {
                displayColors: true,
                filter: (item) => item.parsed.y != null,
                callbacks: { label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1).replace('.', ',')} cm` },
            },
        },
    },
}));
