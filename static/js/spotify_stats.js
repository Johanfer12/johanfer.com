const PIE_COLORS = [
    '#7d95ff',  // azul
    '#a57cff',  // morado
    '#e2bc72',  // dorado
    '#5ec4e8',  // cian
    '#d884c4',  // rosa-violeta
];

const compactLabel = (label, maxLength = 16) => {
    if (!isMobileChart || typeof label !== 'string' || label.length <= maxLength) {
        return label;
    }

    return `${label.slice(0, maxLength - 1)}…`;
};

// Géneros: anillo con separación entre porciones, en vez de la tarta maciza.
new Chart(document.getElementById('genresChart'), {
    type: 'doughnut',
    data: {
        labels: genresLabels,
        datasets: [{
            data: genresValues,
            backgroundColor: PIE_COLORS,
            hoverOffset: 8,
            borderWidth: 0,
            borderRadius: 6,
            spacing: 4,
            glow: 'rgba(120, 130, 255, 0.35)',
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '58%',
        layout: {
            padding: isMobileChart ? 10 : 8
        },
        plugins: {
            legend: {
                position: isMobileChart ? 'bottom' : 'right',
                labels: { 
                    color: 'white',
                    boxWidth: 12,
                    boxHeight: 12,
                    padding: isMobileChart ? 10 : 12,
                    font: {
                        size: isMobileChart ? 11 : 12
                    },
                    generateLabels(chart) {
                        const labels = Chart.overrides.doughnut.plugins.legend.labels.generateLabels(chart);
                        return labels.map((item) => ({
                            ...item,
                            text: compactLabel(item.text || chart.data.labels[item.index] || '', 18)
                        }));
                    }
                }
            },
            datalabels: {
                display: !isMobileChart,
                color: 'white',
                font: {
                    weight: 'bold'
                },
                formatter: (value, ctx) => {
                    const total = ctx.dataset.data.reduce((acc, data) => acc + data, 0);
                    // En el anillo solo cabe el porcentaje; la cifra va en el tooltip.
                    return `${Math.round((value * 100) / total)}%`;
                }
            }
        },
        animation: {
            animateRotate: true,
            animateScale: true,
            duration: 2000
        }
    }
});

// Gráfico de artistas
new Chart(document.getElementById('artistsChart'), {
    type: 'bar',
    data: {
        labels: artistsLabels,
        datasets: [{
            label: 'Canciones por artista',
            data: artistsValues,
            ...barStyle(PALETTE.blue, { horizontal: true }),
        }]
    },
    options: {
        ...commonOptions,
        indexAxis: 'y',
        plugins: {
            legend: { display: false },
            datalabels: {
                color: 'white',
                anchor: 'end',
                align: 'start',
                clamp: true,
                font: {
                    size: isMobileChart ? 11 : 12
                }
            }
        },
        scales: {
            x: valueAxis(artistsValues),
            y: categoryAxis({
                ticks: {
                    color: TICK_COLOR,
                    font: {
                        size: isMobileChart ? 11 : 12
                    },
                    callback(value) {
                        return compactLabel(this.getLabelForValue(value), 15);
                    }
                }
            }),
        },
        animation: {
            x: {
                duration: 2000,
                from: 0
            }
        }
    }
});

// Gráfico mensual
new Chart(document.getElementById('monthlyChart'), {
    type: 'line',
    data: {
        labels: monthsLabels,
        datasets: [{
            label: 'Canciones añadidas',
            data: monthsValues,
            borderColor: PALETTE.purple.top,
            borderWidth: 2.5,
            // Relleno que se desvanece hacia abajo. Arranca en el pico de los
            // datos y no en el borde de la gráfica: la curva va casi siempre por
            // la mitad baja y, anclado arriba, bajo ella apenas quedaba color.
            backgroundColor: (ctx) => {
                const { chart } = ctx;
                const area = chart.chartArea;
                if (!area || !chart.scales.y) return 'rgba(164, 124, 255, 0.2)';
                const peak = chart.scales.y.getPixelForValue(Math.max(...monthsValues));
                const gradient = chart.ctx.createLinearGradient(0, peak, 0, area.bottom);
                gradient.addColorStop(0, 'rgba(164, 124, 255, 0.55)');
                gradient.addColorStop(1, 'rgba(164, 124, 255, 0.04)');
                return gradient;
            },
            fill: true,
            glow: PALETTE.purple.glow,
        }]
    },
    options: {
        ...commonOptions,
        plugins: {
            legend: { display: false },
            datalabels: {
                display: false
            }
        },
        elements: {
            // Sin puntos en reposo: con decenas de meses eran un collar de
            // cuentas sobre la línea. Aparecen al pasar por encima.
            point: {
                radius: 0,
                hoverRadius: 5,
                hitRadius: 10,
                hoverBackgroundColor: '#ffffff',
            },
            // `monotone` y no una tensión libre: la curva no se sale por debajo de
            // cero entre dos meses flojos ni se inventa picos que no hubo.
            line: {
                cubicInterpolationMode: 'monotone'
            }
        },
        // Esta sí conserva el eje de valores: la línea no lleva cifras encima.
        scales: {
            y: {
                beginAtZero: true,
                border: { display: false },
                ticks: {
                    color: TICK_COLOR,
                    maxTicksLimit: 5,
                    font: {
                        size: isMobileChart ? 11 : 12
                    }
                },
                grid: { color: GRID_COLOR }
            },
            x: {
                border: { display: false },
                ticks: {
                    color: TICK_COLOR,
                    autoSkip: true,
                    maxTicksLimit: isMobileChart ? 6 : 10,
                    maxRotation: isMobileChart ? 45 : 0,
                    minRotation: isMobileChart ? 45 : 0,
                    font: {
                        size: isMobileChart ? 11 : 12
                    }
                },
                grid: { display: false }
            }
        },
        animation: {
            y: {
                duration: 2000,
                from: 500
            }
        }
    }
}); 
