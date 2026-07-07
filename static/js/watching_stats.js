Chart.register(ChartDataLabels);

// Paleta del sitio (la misma familia azul/morado del home)
const PALETTE = {
    blue: { bg: 'rgba(108, 142, 255, 0.62)', border: 'rgba(141, 168, 255, 0.95)' },
    purple: { bg: 'rgba(164, 124, 255, 0.58)', border: 'rgba(186, 156, 255, 0.95)' },
    gold: { bg: 'rgba(222, 188, 122, 0.65)', border: 'rgba(240, 212, 150, 0.95)' },
};
const POLAR_COLORS = [
    'rgba(108, 142, 255, 0.72)',  // azul
    'rgba(164, 124, 255, 0.68)',  // morado
    'rgba(222, 188, 122, 0.72)',  // dorado
    'rgba(96, 196, 232, 0.68)',   // cian
    'rgba(214, 132, 196, 0.66)',  // rosa-violeta
    'rgba(126, 217, 173, 0.66)',  // verde menta
    'rgba(240, 156, 130, 0.68)',  // coral
];
const GRID_COLOR = 'rgba(255, 255, 255, 0.05)';

const isMobileChart = window.innerWidth < 768;
const formatNumber = (value) => new Intl.NumberFormat('es-CO').format(value);
const paddedAxisMax = (values) => {
    const max = Math.max(...values, 0);
    return max > 0 ? Math.ceil(max * 1.18) : undefined;
};

const chartDefaults = {
    devicePixelRatio: 2,
    animation: {
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

// Series y películas por año (barras agrupadas)
new Chart(document.getElementById('perYearChart'), {
    type: 'bar',
    data: {
        labels: yearsLabels,
        datasets: [
            {
                label: 'Series',
                data: showsPerYear,
                backgroundColor: PALETTE.blue.bg,
                borderColor: PALETTE.blue.border,
                borderWidth: 1
            },
            {
                label: 'Películas',
                data: moviesPerYear,
                backgroundColor: PALETTE.purple.bg,
                borderColor: PALETTE.purple.border,
                borderWidth: 1
            }
        ]
    },
    options: {
        ...commonOptions,
        scales: {
            ...commonOptions.scales,
            y: {
                ...commonOptions.scales.y,
                beginAtZero: true,
                suggestedMax: paddedAxisMax([...showsPerYear, ...moviesPerYear]),
                ticks: {
                    color: 'white',
                    precision: 0
                }
            }
        },
        plugins: {
            legend: {
                position: 'bottom',
                labels: {
                    color: 'white',
                    boxWidth: isMobileChart ? 12 : 24,
                    padding: isMobileChart ? 10 : 12,
                    font: {
                        size: isMobileChart ? 11 : 12
                    }
                }
            },
            datalabels: {
                color: 'rgba(238, 243, 251, 0.88)',
                anchor: 'end',
                align: 'end',
                clamp: false,
                offset: 0,
                font: {
                    weight: 'bold',
                    size: isMobileChart ? 9 : 11
                },
                formatter: (value) => (value > 0 ? formatNumber(value) : '')
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

// Mis calificaciones (área polar: obras por cantidad de estrellas)
new Chart(document.getElementById('ratingsChart'), {
    type: 'polarArea',
    data: {
        labels: ratingsLabels,
        datasets: [{
            data: ratingsValues,
            backgroundColor: POLAR_COLORS,
            borderColor: 'rgba(10, 16, 32, 0.55)',
            borderWidth: 2
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        layout: {
            padding: isMobileChart ? 10 : 4
        },
        scales: {
            r: {
                ticks: {
                    color: 'rgba(238, 243, 251, 0.7)',
                    backdropColor: 'transparent',
                    precision: 0
                },
                grid: { color: 'rgba(255, 255, 255, 0.12)' },
                angleLines: { color: 'rgba(255, 255, 255, 0.12)' }
            }
        },
        plugins: {
            legend: {
                position: isMobileChart ? 'bottom' : 'right',
                labels: {
                    color: 'white',
                    boxWidth: isMobileChart ? 14 : 20,
                    padding: isMobileChart ? 8 : 10,
                    font: {
                        size: isMobileChart ? 11 : 12
                    }
                }
            },
            datalabels: {
                display: !isMobileChart,
                color: 'white',
                font: {
                    weight: 'bold'
                },
                formatter: (value) => formatNumber(value)
            }
        },
        animation: {
            animateRotate: true,
            animateScale: true,
            duration: 2000
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
            backgroundColor: PALETTE.gold.bg,
            borderColor: PALETTE.gold.border,
            borderWidth: 1
        }]
    },
    options: {
        ...commonOptions,
        indexAxis: 'y',
        scales: {
            x: {
                beginAtZero: true,
                suggestedMax: paddedAxisMax(decadesValues),
                ticks: {
                    color: 'white',
                    precision: 0
                },
                grid: { color: GRID_COLOR }
            },
            y: {
                ticks: {
                    color: 'white',
                    font: {
                        size: isMobileChart ? 11 : 12
                    }
                },
                grid: { color: GRID_COLOR }
            }
        },
        plugins: {
            legend: { display: false },
            datalabels: {
                color: 'rgba(238, 243, 251, 0.88)',
                anchor: 'end',
                align: 'end',
                clamp: true,
                offset: 4,
                font: {
                    weight: 'bold',
                    size: isMobileChart ? 10 : 12
                },
                formatter: (value) => formatNumber(value)
            }
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
