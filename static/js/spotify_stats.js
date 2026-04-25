Chart.register(ChartDataLabels);

const isMobileChart = window.innerWidth < 768;
const compactLabel = (label, maxLength = 16) => {
    if (!isMobileChart || typeof label !== 'string' || label.length <= maxLength) {
        return label;
    }

    return `${label.slice(0, maxLength - 1)}…`;
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
            grid: { color: 'rgba(255, 255, 255, 0.1)' }
        },
        x: {
            ticks: { color: 'white' },
            grid: { color: 'rgba(255, 255, 255, 0.1)' }
        }
    }
};

// Gráfico de géneros
new Chart(document.getElementById('genresChart'), {
    type: 'pie',
    data: {
        labels: genresLabels,
        datasets: [{
            data: genresValues,
            backgroundColor: [
                'rgba(255, 99, 132, 0.6)',   // Rojo
                'rgba(54, 162, 235, 0.6)',    // Azul
                'rgba(255, 206, 86, 0.6)',    // Amarillo
                'rgba(75, 192, 192, 0.6)',    // Verde
                'rgba(153, 102, 255, 0.6)'    // Morado
            ]
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        layout: {
            padding: isMobileChart ? 10 : 4
        },
        plugins: {
            legend: {
                position: isMobileChart ? 'bottom' : 'right',
                labels: { 
                    color: 'white',
                    boxWidth: isMobileChart ? 14 : 40,
                    padding: isMobileChart ? 10 : 12,
                    font: {
                        size: isMobileChart ? 11 : 12
                    },
                    generateLabels(chart) {
                        const labels = Chart.overrides.pie.plugins.legend.labels.generateLabels(chart);
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
                    const percentage = ((value * 100) / total).toFixed(1);
                    return `${percentage}%\n(${value})`;
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
            backgroundColor: 'rgba(75, 192, 192, 0.6)',
            borderColor: 'rgba(75, 192, 192, 1)',
            borderWidth: 1
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
                    size: isMobileChart ? 10 : 12
                }
            }
        },
        scales: {
            x: {
                grid: {
                    display: false
                },
                ticks: {
                    color: 'white',
                    font: {
                        size: isMobileChart ? 11 : 12
                    }
                }
            },
            y: {
                grid: {
                    display: false
                },
                ticks: {
                    color: 'white',
                    font: {
                        size: isMobileChart ? 11 : 12
                    },
                    callback(value) {
                        return compactLabel(this.getLabelForValue(value), 15);
                    }
                }
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

// Gráfico mensual
new Chart(document.getElementById('monthlyChart'), {
    type: 'line',
    data: {
        labels: monthsLabels,
        datasets: [{
            label: 'Canciones añadidas',
            data: monthsValues,
            borderColor: 'rgba(153, 102, 255, 1)',
            backgroundColor: 'rgba(153, 102, 255, 0.2)',
            fill: true
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
            point: {
                radius: isMobileChart ? 2 : 3,
                hitRadius: 8
            },
            line: {
                tension: 0.28
            }
        },
        scales: {
            y: {
                ticks: {
                    color: 'white',
                    font: {
                        size: isMobileChart ? 11 : 12
                    }
                },
                grid: { color: 'rgba(255, 255, 255, 0.1)' }
            },
            x: {
                ticks: {
                    color: 'white',
                    autoSkip: true,
                    maxTicksLimit: isMobileChart ? 6 : 10,
                    maxRotation: isMobileChart ? 45 : 0,
                    minRotation: isMobileChart ? 45 : 0,
                    font: {
                        size: isMobileChart ? 10 : 12
                    }
                },
                grid: { color: 'rgba(255, 255, 255, 0.1)' }
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
