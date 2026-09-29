// Gráficas de Libros. La base (paleta, ejes, etiquetas) está en charts_common.js.

// Libros por año
new Chart(document.getElementById('booksPerYearChart'), {
    type: 'bar',
    data: {
        labels: booksPerYearData,
        datasets: [{
            label: 'Libros leídos',
            data: booksPerYearValues,
            ...barStyle(PALETTE.blue),
        }]
    },
    options: {
        ...commonOptions,
        scales: {
            x: categoryAxis(),
            y: valueAxis(booksPerYearValues),
        },
        plugins: {
            legend: { display: false },
            datalabels: valueLabels()
        },
        animation: {
            y: {
                duration: 2000,
                from: 500
            }
        }
    }
});

// Estrellas
new Chart(document.getElementById('starsChart'), {
    type: 'bar',
    data: {
        labels: ['★★★★★', '★★★★', '★★★', '★★', '★'],
        datasets: [{
            label: 'Libros',
            data: [...starsValues].reverse(),
            ...barStyle(PALETTE.gold, { horizontal: true }),
        }]
    },
    options: {
        ...commonOptions,
        indexAxis: 'y',
        scales: {
            x: valueAxis(starsValues),
            y: categoryAxis(),
        },
        plugins: {
            legend: { display: false },
            datalabels: valueLabels({
                clamp: true,
                offset: 4,
                size: isMobileChart ? 11 : 12,
            })
        },
        animation: {
            x: {
                duration: 2000,
                from: 0
            }
        }
    }
});

// Páginas leídas por año
new Chart(document.getElementById('pagesPerYearChart'), {
    type: 'bar',
    data: {
        labels: pagesPerYearLabels,
        datasets: [{
            label: 'Páginas leídas',
            data: pagesPerYearValues,
            ...barStyle(PALETTE.purple),
        }]
    },
    options: {
        ...commonOptions,
        scales: {
            x: categoryAxis(),
            y: valueAxis(pagesPerYearValues),
        },
        plugins: {
            legend: { display: false },
            datalabels: valueLabels()
        },
        animation: {
            y: {
                duration: 2000,
                from: 0
            }
        }
    }
});

let chartResizeTimer;
window.addEventListener('resize', function() {
    clearTimeout(chartResizeTimer);
    chartResizeTimer = setTimeout(function() {
        Object.values(Chart.instances).forEach(chart => {
            chart.resize();
        });
    }, 250);
});
