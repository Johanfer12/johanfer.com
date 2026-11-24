// Gráficas de Retos → Economía. La base está en charts_common.js y retos_common.js.

const ALIMENTOS = leerDatos('retos-alimentos');
const INFLACION = leerDatos('retos-inflacion');
const TASAS = leerDatos('retos-tasas');
const TRM = leerDatos('retos-trm');
const DEUDA = leerDatos('retos-deuda');
const INTERESES = leerDatos('retos-intereses');
const ARANCELES = leerDatos('retos-aranceles');

// Eje de meses ('AAAA-MM'): solo se rotula enero, y solo uno de cada `cada`
// años. Con el autoSkip de Chart.js las etiquetas caían en meses sueltos.
const ejeMeses = (meses, cada) => categoryAxis({
    ticks: {
        color: TICK_COLOR,
        font: { size: 12 },
        autoSkip: false,
        maxRotation: 0,
        callback: (v, i) => {
            const [anio, mes] = meses[i].split('-');
            return mes === '01' && +anio % cada === 0 ? anio : '';
        },
    },
});
const tituloMes = (items) => {
    const [anio, mes] = items[0].label.split('-');
    return `${MESES[+mes - 1]} ${anio}`;
};
const cadaAnios = (meses, objetivo) => {
    const anios = meses.length / 12;
    return [1, 2, 5, 10].find((n) => anios / n <= objetivo) || 10;
};

// Las gráficas mensuales comparten el título del tooltip ('octubre 2026').
const conTituloMes = (opciones) => {
    opciones.plugins.tooltip.callbacks.title = tituloMes;
    return opciones;
};

const relleno = (color) => color.replace(/^#(..)(..)(..)$/, (_, r, g, b) => `rgba(${parseInt(r, 16)}, ${parseInt(g, 16)}, ${parseInt(b, 16)}, 0.16)`);
const area = (label, datos, color, extra = {}) => serie(label, datos, color, {
    backgroundColor: relleno(color), fill: true, borderWidth: 2.5, tension: 0.2, order: -1, revelar: true, ...extra,
});

// Índice de la FAO: una sola serie, con el 100 de 2014-2016 como referencia.
alEntrarEnVista('alimentosChart', () => new Chart(document.getElementById('alimentosChart'), {
    type: 'line',
    plugins: [revelar],
    data: {
        labels: ALIMENTOS.meses,
        datasets: [
            area('Índice FAO', ALIMENTOS.valores, ROJO),
            referencia('Promedio 2014-2016 (100)', ALIMENTOS.meses.length, 100, 'rgba(238, 243, 251, 0.6)'),
        ],
    },
    options: conTituloMes(opcionesLinea({
        x: ejeMeses(ALIMENTOS.meses, cadaAnios(ALIMENTOS.meses, isMobileChart ? 5 : 8)),
        y: ejeValores((v) => v),
        tooltip: (ctx) => `${ctx.dataset.label}: ${coma(ctx.parsed.y)}`,
    })),
}));
// Inflación interanual: Colombia frente a EE. UU. y la zona euro.
alEntrarEnVista('inflacionChart', () => new Chart(document.getElementById('inflacionChart'), {
    type: 'line',
    plugins: [revelar],
    data: {
        labels: INFLACION.meses,
        datasets: [
            serie('Colombia', INFLACION.colombia, ROJO, { borderWidth: 3.5, order: -1, revelar: true }),
            serie('EE. UU.', INFLACION.eeuu, AZUL, { borderWidth: 2, spanGaps: false }),
            serie('Zona euro', INFLACION.zona_euro, DORADO, { borderWidth: 2 }),
        ],
    },
    options: conTituloMes(opcionesLinea({
        x: ejeMeses(INFLACION.meses, 1),
        y: ejeValores((v) => `${v} %`),
        tooltip: (ctx) => `${ctx.dataset.label}: ${coma(ctx.parsed.y)} %`,
    })),
}));

// Tasas de política monetaria: en escalera, porque cambian en reuniones.
alEntrarEnVista('tasasChart', () => new Chart(document.getElementById('tasasChart'), {
    type: 'line',
    plugins: [revelar],
    data: {
        labels: TASAS.meses,
        datasets: [
            serie('Banco de la República', TASAS.banrep, ROJO, { borderWidth: 3.5, stepped: true, order: -1, revelar: true }),
            serie('Fed', TASAS.fed_techo, AZUL, { borderWidth: 2, stepped: true }),
            serie('BCE', TASAS.bce_deposito, DORADO, { borderWidth: 2, stepped: true }),
        ],
    },
    options: conTituloMes(opcionesLinea({
        x: ejeMeses(TASAS.meses, 1),
        y: ejeValores((v) => `${v} %`, { min: 0 }),
        tooltip: (ctx) => `${ctx.dataset.label}: ${coma(ctx.parsed.y, 2)} %`,
    })),
}));

// TRM: promedio mensual de pesos por dólar.
alEntrarEnVista('trmChart', () => new Chart(document.getElementById('trmChart'), {
    type: 'line',
    plugins: [revelar],
    data: {
        labels: TRM.meses,
        datasets: [area('Pesos por dólar', TRM.valores, AZUL)],
    },
    options: conTituloMes(opcionesLinea({
        x: ejeMeses(TRM.meses, isMobileChart ? 3 : 2),
        y: ejeValores((v) => `$${miles(v)}`, { min: 2000 }),
        tooltip: (ctx) => `$${miles(ctx.parsed.y)}`,
        mostrarLeyenda: false,
    })),
}));

// Deuda pública: medido en línea continua y la proyección del FMI punteada.
const desdeProyeccion = DEUDA.anios.indexOf(DEUDA.primer_proyectado) - 1;
const punteadaDesde = { borderDash: (ctx) => (ctx.p0DataIndex >= desdeProyeccion ? [4, 5] : undefined) };
alEntrarEnVista('deudaChart', () => new Chart(document.getElementById('deudaChart'), {
    type: 'line',
    plugins: [revelar],
    data: {
        labels: DEUDA.anios,
        datasets: [
            serie('EE. UU.', DEUDA.eeuu, AZUL, { borderWidth: 2, segment: punteadaDesde }),
            serie('Mundo', DEUDA.mundo, ROJO, { borderWidth: 3.5, order: -1, revelar: true, segment: punteadaDesde }),
            serie('Colombia', DEUDA.colombia, DORADO, { borderWidth: 2, segment: punteadaDesde }),
        ],
    },
    options: opcionesLinea({
        x: ejeLargo(),
        y: ejeValores((v) => `${v} %`, { min: 0 }),
        tooltip: (ctx) => `${ctx.dataset.label}: ${coma(ctx.parsed.y)} % del PIB${DEUDA.anios[ctx.dataIndex] >= DEUDA.primer_proyectado ? ' (proyección)' : ''}`,
    }),
}));

// Intereses de la deuda federal frente a defensa.
alEntrarEnVista('interesesChart', () => new Chart(document.getElementById('interesesChart'), {
    type: 'line',
    plugins: [revelar],
    data: {
        labels: INTERESES.anios,
        datasets: [
            serie('Intereses', INTERESES.intereses, ROJO, { borderWidth: 3.5, order: -1, revelar: true }),
            serie('Defensa', INTERESES.defensa, LAVANDA, { borderWidth: 2 }),
        ],
    },
    options: opcionesLinea({
        x: ejeLargo(),
        y: ejeValores((v) => miles(v), { min: 0 }),
        tooltip: (ctx) => `${ctx.dataset.label}: ${miles(ctx.parsed.y)} mil millones USD`,
    }),
}));

// Arancel efectivo desde 1929.
alEntrarEnVista('arancelesChart', () => new Chart(document.getElementById('arancelesChart'), {
    type: 'line',
    plugins: [revelar],
    data: {
        labels: ARANCELES.anios,
        datasets: [area('Arancel efectivo', ARANCELES.valores, '#e2bc72')],
    },
    options: opcionesLinea({
        x: ejeLargo(),
        y: ejeValores((v) => `${v} %`, { min: 0 }),
        tooltip: (ctx) => `${coma(ctx.parsed.y)} %`,
        mostrarLeyenda: false,
    }),
}));
