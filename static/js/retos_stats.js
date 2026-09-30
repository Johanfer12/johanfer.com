// Gráficas de Retos → Cambio climático. La base está en charts_common.js.

const LIMITES = JSON.parse(document.getElementById('retos-limites').textContent);
const NINO = JSON.parse(document.getElementById('retos-nino34').textContent);
const MAR = JSON.parse(document.getElementById('retos-mar').textContent);
const CO2 = JSON.parse(document.getElementById('retos-co2').textContent);
const AIRE = JSON.parse(document.getElementById('retos-aire').textContent);
const NIVEL = JSON.parse(document.getElementById('retos-nivel').textContent);

const CRUZADO = '#e0745c';
const SEGURO = '#5ec4e8';
const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

const SIN_MOVIMIENTO = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
// Números con coma decimal, como en el resto de la página.
const fmt = (v, d = 2) => `${v > 0 ? '+' : ''}${v.toFixed(d).replace('.', ',')}`;

// Animación de la línea que cuenta la historia (2026; en CO₂, la curva): se
// dibuja de izquierda a derecha recortando el dataset con un rectángulo que
// crece. Se hace así y no con las animaciones de Chart.js porque estas
// gráficas van con `animation: false` (todo lo demás tiene que aparecer
// quieto) y porque el recorte acaba exactamente en el último dato, no en el
// borde del eje: la línea de 2026 solo llega hasta agosto.
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
        let ultimo = 0;
        chart.data.datasets.filter((d) => d.revelar).forEach((d) => {
            let i = d.data.length - 1;
            while (i > 0 && d.data[i] == null) i -= 1;
            ultimo = Math.max(ultimo, i);
        });
        const margen = 8;  // que no corte el grosor de la línea ni los puntos
        const inicio = area.left - margen;
        const fin = scales.x.getPixelForValue(ultimo) + margen;
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

const serie = (year, datos, color, extra = {}) => ({
    label: year,
    data: datos,
    borderColor: color,
    backgroundColor: color,
    pointRadius: 0,
    pointHoverRadius: 4,
    tension: 0.3,
    ...extra,
});

const leyenda = { labels: { color: 'white', boxWidth: 14, boxHeight: 3, font: { size: 12 } } };

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
// El punto de 2026 es enero-agosto: va aparte para que no parezca un año completo.
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
                label: '2026 (ene-ago)',
                data: AIRE.anios.map((a) => (a === 2026 ? AIRE.ene_ago_2026 : null)),
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

// El «?» de cada límite y la «i» de cada gráfica abren el mismo modal.
document.querySelectorAll('.retos-help, .retos-info').forEach((boton) => {
    boton.addEventListener('click', () => {
        document.getElementById('retos-modal-title').textContent = boton.dataset.title;
        document.getElementById('retos-modal-text').textContent = boton.dataset.text;
        openModal('retos');
    });
});
