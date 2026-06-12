// Al inicio del archivo
Chart.register(ChartDataLabels);

// Paleta del sitio (derivada del gradiente azul/morado del home)
const PALETTE = {
    blue: { bg: 'rgba(108, 142, 255, 0.62)', border: 'rgba(141, 168, 255, 0.95)' },
    purple: { bg: 'rgba(164, 124, 255, 0.58)', border: 'rgba(186, 156, 255, 0.95)' },
    gold: { bg: 'rgba(222, 188, 122, 0.65)', border: 'rgba(240, 212, 150, 0.95)' },
};
const GRID_COLOR = 'rgba(255, 255, 255, 0.05)';

const isMobileChart = window.innerWidth < 768;
const compactLabel = (label, maxLength = 16) => {
    if (!isMobileChart || typeof label !== 'string' || label.length <= maxLength) {
        return label;
    }

    return `${label.slice(0, maxLength - 1)}…`;
};
const formatNumber = (value) => new Intl.NumberFormat('es-CO').format(value);
const paddedAxisMax = (values) => {
    const max = Math.max(...values, 0);
    return max > 0 ? Math.ceil(max * 1.18) : undefined;
};
const barValueLabels = {
    color: 'rgba(238, 243, 251, 0.88)',
    anchor: 'end',
    align: 'end',
    clamp: false,
    offset: 0,
    font: {
        weight: 'bold',
        size: isMobileChart ? 9 : 11
    },
    formatter: (value) => formatNumber(value)
};

// Al inicio del archivo, antes de commonOptions
const chartDefaults = {
    devicePixelRatio: 2,
    animation: {
        duration: 0 // Desactiva las animaciones que pueden causar problemas
    },
    layout: {
        padding: isMobileChart ? 8 : 0
    }
};

// Configuración común para todos los gráficos
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
            ticks: {
                color: 'white'
            },
            grid: {
                color: GRID_COLOR
            }
        },
        x: {
            ticks: {
                color: 'white'
            },
            grid: {
                color: GRID_COLOR
            }
        }
    }
};

// Gráfico de libros por año
new Chart(document.getElementById('booksPerYearChart'), {
    type: 'bar',
    data: {
        labels: booksPerYearData,
        datasets: [{
            label: 'Libros leídos',
            data: booksPerYearValues,
            backgroundColor: PALETTE.blue.bg,
            borderColor: PALETTE.blue.border,
            borderWidth: 1
        }]
    },
    options: {
        ...commonOptions,
        scales: {
            ...commonOptions.scales,
            y: {
                ...commonOptions.scales.y,
                suggestedMax: paddedAxisMax(booksPerYearValues)
            }
        },
        plugins: {
            legend: {
                display: false
            },
            datalabels: barValueLabels
        },
        animation: {
            y: {
                duration: 2000,
                from: 500 
            }
        }
    }
});
// Gráfico de estrellas
new Chart(document.getElementById('starsChart'), {
    type: 'bar',
    data: {
        labels: ['★★★★★', '★★★★', '★★★', '★★', '★'],
        datasets: [{
            label: 'Libros',
            data: [...starsValues].reverse(),
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
                suggestedMax: paddedAxisMax(starsValues),
                ticks: {
                    color: 'white',
                    precision: 0
                },
                grid: {
                    color: GRID_COLOR
                }
            },
            y: {
                ticks: {
                    color: 'white',
                    font: {
                        size: isMobileChart ? 11 : 12
                    }
                },
                grid: {
                    color: GRID_COLOR
                }
            }
        },
        plugins: {
            legend: {
                display: false
            },
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

// Gráfico de páginas leídas por año
new Chart(document.getElementById('pagesPerYearChart'), {
    type: 'bar',
    data: {
        labels: pagesPerYearLabels,
        datasets: [{
            label: 'Páginas leídas',
            data: pagesPerYearValues,
            backgroundColor: PALETTE.purple.bg,
            borderColor: PALETTE.purple.border,
            borderWidth: 1
        }]
    },
    options: {
        ...commonOptions,
        scales: {
            x: {
                ticks: {
                    color: 'white',
                    font: {
                        size: isMobileChart ? 11 : 12
                    }
                },
                grid: {
                    color: GRID_COLOR
                }
            },
            y: {
                beginAtZero: true,
                suggestedMax: paddedAxisMax(pagesPerYearValues),
                ticks: {
                    color: 'white',
                    callback(value) {
                        return formatNumber(value);
                    },
                    font: {
                        size: isMobileChart ? 11 : 12
                    }
                },
                grid: {
                    color: GRID_COLOR
                }
            }
        },
        plugins: {
            legend: {
                display: false
            },
            datalabels: barValueLabels
        },
        maintainAspectRatio: false,
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
