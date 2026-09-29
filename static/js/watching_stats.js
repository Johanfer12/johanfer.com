// Gráficas de TV. La base (paleta, ejes, etiquetas) está en charts_common.js.

// Series y películas por año (barras agrupadas)
new Chart(document.getElementById('perYearChart'), {
    type: 'bar',
    data: {
        labels: yearsLabels,
        datasets: [
            {
                label: 'Series',
                data: showsPerYear,
                ...barStyle(PALETTE.blue),
            },
            {
                label: 'Películas',
                data: moviesPerYear,
                ...barStyle(PALETTE.purple),
            }
        ]
    },
    options: {
        ...commonOptions,
        scales: {
            x: categoryAxis(),
            y: valueAxis([...showsPerYear, ...moviesPerYear]),
        },
        plugins: {
            legend: {
                position: 'bottom',
                labels: {
                    color: TICK_COLOR,
                    boxWidth: 12,
                    boxHeight: 12,
                    padding: isMobileChart ? 10 : 14,
                    font: {
                        size: isMobileChart ? 11 : 12
                    }
                }
            },
            datalabels: valueLabels({
                formatter: (value) => (value > 0 ? formatNumber(value) : ''),
            })
        },
        animation: {
            y: {
                duration: 2000,
                from: 500
            }
        }
    }
});

// Mis calificaciones. Era un gráfico polar, que obliga a comparar áreas de
// cuñas; unas barras con las estrellas en el eje se leen de un vistazo y son
// las mismas que las de Libros. Llegan de menor a mayor nota: se invierten
// para que las cinco estrellas queden arriba.
new Chart(document.getElementById('ratingsChart'), {
    type: 'bar',
    data: {
        labels: [...ratingsLabels].reverse(),
        datasets: [{
            label: 'Títulos',
            data: [...ratingsValues].reverse(),
            ...barStyle(PALETTE.gold, { horizontal: true }),
        }]
    },
    options: {
        ...commonOptions,
        indexAxis: 'y',
        scales: {
            x: valueAxis(ratingsValues),
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

// Décadas de estreno de lo que veo (barras horizontales)
new Chart(document.getElementById('decadesChart'), {
    type: 'bar',
    data: {
        labels: decadesLabels,
        datasets: [{
            label: 'Títulos',
            data: decadesValues,
            ...barStyle(PALETTE.blue, { horizontal: true }),
        }]
    },
    options: {
        ...commonOptions,
        indexAxis: 'y',
        scales: {
            x: valueAxis(decadesValues),
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

let chartResizeTimer;
window.addEventListener('resize', function() {
    clearTimeout(chartResizeTimer);
    chartResizeTimer = setTimeout(function() {
        Object.values(Chart.instances).forEach(chart => {
            chart.resize();
        });
    }, 250);
});
