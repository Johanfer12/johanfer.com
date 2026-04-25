// Al inicio del archivo
Chart.register(ChartDataLabels);

const isMobileChart = window.innerWidth < 768;
const compactLabel = (label, maxLength = 16) => {
    if (!isMobileChart || typeof label !== 'string' || label.length <= maxLength) {
        return label;
    }

    return `${label.slice(0, maxLength - 1)}…`;
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
        plugins: {
            legend: {
                labels: {
                    color: 'white'
                }
            },
            datalabels: {
                color: 'white',
                anchor: 'end',
                align: 'start',
                clamp: true,
                font: {
                    weight: 'bold',
                    size: isMobileChart ? 10 : 12
                },
                formatter: (value) => value
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
// Gráfico de estrellas
new Chart(document.getElementById('starsChart'), {
    type: 'pie',
    data: {
        labels: starsLabels,
        datasets: [{
            data: starsValues,
            backgroundColor: [
                'rgba(255, 99, 132, 0.6)',
                'rgba(54, 162, 235, 0.6)',
                'rgba(255, 206, 86, 0.6)',
                'rgba(75, 192, 192, 0.6)',
                'rgba(153, 102, 255, 0.6)'
            ]
        }]
    },
    options: {
        ...commonOptions,
        scales: {
            x: {
                display: false
            },
            y: {
                display: false
            }
        },
        plugins: {
            legend: {
                position: isMobileChart ? 'bottom' : 'right',
                align: 'center',
                labels: {
                    color: 'white',
                    padding: isMobileChart ? 10 : 12,
                    boxWidth: isMobileChart ? 14 : 15,
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
                    weight: 'bold',
                    size: 12
                },
                formatter: (value, context) => {
                    const total = context.dataset.data.reduce((acc, data) => acc + data, 0);
                    const percentage = ((value * 100) / total).toFixed(1) + '%';
                    return percentage;
                },
                anchor: function(context) {
                    const value = context.dataset.data[context.dataIndex];
                    const total = context.dataset.data.reduce((acc, data) => acc + data, 0);
                    return (value / total) < 0.1 ? 'end' : 'center';
                },
                align: function(context) {
                    const value = context.dataset.data[context.dataIndex];
                    const total = context.dataset.data.reduce((acc, data) => acc + data, 0);
                    return (value / total) < 0.1 ? 'end' : 'center';
                },
                offset: function(context) {
                    const value = context.dataset.data[context.dataIndex];
                    const total = context.dataset.data.reduce((acc, data) => acc + data, 0);
                    return (value / total) < 0.1 ? 20 : 0;
                }
            }
        },
        animation: {
            animateRotate: true, 
            animateScale: true 
        }
    }
});

// Gráfico de generos más leídos
new Chart(document.getElementById('topGenresChart'), {
    type: 'bar',
    data: {
        labels: topGenresLabels,
        datasets: [{
            label: 'Libros por género',
            data: topGenresValues,
            backgroundColor: 'rgba(153, 102, 255, 0.6)',
            borderColor: 'rgba(153, 102, 255, 1)',
            borderWidth: 1
        }]
    },
    options: {
        ...commonOptions,
        indexAxis: 'y',
        scales: {
            x: {
                beginAtZero: true,
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
                ticks: {
                    color: 'white',
                    font: {
                        size: isMobileChart ? 11 : 12
                    },
                    callback(value) {
                        return compactLabel(this.getLabelForValue(value), 15);
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
                align: 'start',
                clamp: true,
                offset: 0,
                font: {
                    weight: 'bold',
                    size: isMobileChart ? 10 : 14
                },
                formatter: (value) => value
            }
        },
        maintainAspectRatio: false,
        animation: {
            x: {
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
