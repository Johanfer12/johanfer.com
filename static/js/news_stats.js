// Gráficas del feed: qué trae cada fuente y qué llega cada día.
//
// Las dos son barras APILADAS, no agrupadas: lo que interesa de una fuente es
// cuánto trae en total y qué proporción se queda por el camino, y apilando se
// leen las dos cosas de una vez.

const totalsOf = (feed, discarded) => feed.map((value, index) => value + discarded[index]);

// La etiqueta solo se pinta sobre el tramo de arriba, con el total de la barra:
// una por tramo se solaparía en las barras cortas.
const stackTotalLabels = (totals) => ({
    ...valueLabels({ clamp: true, offset: 2 }),
    display: (context) => context.datasetIndex === 1 && totals[context.dataIndex] > 0,
    formatter: (_value, context) => formatNumber(totals[context.dataIndex]),
});

const stackedScales = (totals) => ({
    ...commonOptions.scales,
    x: { ...commonOptions.scales.x, stacked: true },
    y: {
        ...commonOptions.scales.y,
        stacked: true,
        beginAtZero: true,
        suggestedMax: paddedAxisMax(totals),
        ticks: { color: 'white', precision: 0 },
    },
});

const stackedDatasets = (feed, discarded) => ([
    {
        label: 'En el feed',
        data: feed,
        backgroundColor: PALETTE.blue.bg,
        borderColor: PALETTE.blue.border,
        borderWidth: 1,
    },
    {
        label: 'Descartadas',
        data: discarded,
        backgroundColor: PALETTE.purple.bg,
        borderColor: PALETTE.purple.border,
        borderWidth: 1,
    },
]);

const sourceTotals = totalsOf(sourceFeed, sourceDiscarded);

new Chart(document.getElementById('perSourceChart'), {
    type: 'bar',
    data: { labels: sourceLabels, datasets: stackedDatasets(sourceFeed, sourceDiscarded) },
    options: {
        ...commonOptions,
        // En móvil las barras van tumbadas: los nombres de fuente no caben de
        // pie y Chart.js los recortaría o los giraría.
        indexAxis: isMobileChart ? 'y' : 'x',
        scales: isMobileChart
            ? {
                ...commonOptions.scales,
                x: {
                    ...commonOptions.scales.x,
                    stacked: true,
                    beginAtZero: true,
                    suggestedMax: paddedAxisMax(sourceTotals),
                    ticks: { color: 'white', precision: 0 },
                },
                y: { ...commonOptions.scales.y, stacked: true },
            }
            : stackedScales(sourceTotals),
        plugins: {
            ...commonOptions.plugins,
            datalabels: stackTotalLabels(sourceTotals),
            tooltip: {
                callbacks: {
                    footer: (items) => `Total: ${formatNumber(sourceTotals[items[0].dataIndex])}`,
                },
            },
        },
    },
});

const dayTotals = totalsOf(dayFeed, dayDiscarded);

new Chart(document.getElementById('perDayChart'), {
    type: 'bar',
    data: { labels: dayLabels, datasets: stackedDatasets(dayFeed, dayDiscarded) },
    options: {
        ...commonOptions,
        scales: stackedScales(dayTotals),
        plugins: {
            ...commonOptions.plugins,
            datalabels: stackTotalLabels(dayTotals),
            tooltip: {
                callbacks: {
                    footer: (items) => `Total: ${formatNumber(dayTotals[items[0].dataIndex])}`,
                },
            },
        },
    },
});
