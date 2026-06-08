// Al inicio del archivo
Chart.register(ChartDataLabels);

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
    color: 'white',
    anchor: 'end',
    align: 'end',
    clamp: false,
    offset: 2,
    rotation: -45,
    backgroundColor: 'rgba(22, 27, 54, 0.82)',
    borderColor: 'rgba(255, 255, 255, 0.22)',
    borderRadius: 4,
    borderWidth: 1,
    padding: {
        top: 2,
        right: 4,
        bottom: 2,
        left: 4
    },
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
                color: 'rgba(255, 255, 255, 0.1)'
            }
        },
        x: {
            ticks: {
                color: 'white'
            },
            grid: {
                color: 'rgba(255, 255, 255, 0.1)'
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
            backgroundColor: 'rgba(75, 192, 192, 0.6)',
            borderColor: 'rgba(75, 192, 192, 1)',
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
            backgroundColor: 'rgba(232, 184, 90, 0.68)',
            borderColor: 'rgba(255, 216, 128, 0.95)',
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
                    color: 'rgba(255, 255, 255, 0.1)'
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
                    color: 'rgba(255, 255, 255, 0.1)'
                }
            }
        },
        plugins: {
            legend: {
                display: false
            },
            datalabels: {
                color: 'white',
                anchor: 'end',
                align: 'end',
                clamp: true,
                offset: 4,
                backgroundColor: 'rgba(22, 27, 54, 0.82)',
                borderColor: 'rgba(255, 255, 255, 0.22)',
                borderRadius: 4,
                borderWidth: 1,
                padding: {
                    top: 2,
                    right: 4,
                    bottom: 2,
                    left: 4
                },
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
            backgroundColor: 'rgba(153, 102, 255, 0.6)',
            borderColor: 'rgba(153, 102, 255, 1)',
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
                    color: 'rgba(255, 255, 255, 0.1)'
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
                    color: 'rgba(255, 255, 255, 0.1)'
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

window.addEventListener('resize', function() {
    Object.values(Chart.instances).forEach(chart => {
        chart.resize();
    });
});
