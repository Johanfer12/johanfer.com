// Al inicio del archivo
Chart.register(ChartDataLabels);

// Al inicio del archivo, antes de commonOptions
const chartDefaults = {
    devicePixelRatio: 2,
    animation: {
        duration: 0 // Desactiva las animaciones que pueden causar problemas
    }
};

// Configuración común para todos los gráficos
const commonOptions = {
    ...chartDefaults,
    responsive: true,
    maintainAspectRatio: true,
    plugins: {
        legend: {
            labels: {
                color: 'white'
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
        aspectRatio: window.innerWidth < 768 ? 1 : 2,
        plugins: {
            legend: {
                labels: {
                    color: 'white'
                }
            },
            datalabels: {
                color: 'white',
                anchor: 'center',
                align: 'center',
                font: {
                    weight: 'bold'
                },
                formatter: (value) => value
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
                position: 'right',
                align: 'center',
                labels: {
                    color: 'white',
                    padding: 10,
                    boxWidth: 15
                }
            },
            datalabels: {
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
        }
    }
});

// Gráfico de autores más leídos
new Chart(document.getElementById('topAuthorsChart'), {
    type: 'bar',
    data: {
        labels: topAuthorsLabels,
        datasets: [{
            label: 'Libros por autor',
            data: topAuthorsValues,
            backgroundColor: 'rgba(153, 102, 255, 0.6)',
            borderColor: 'rgba(153, 102, 255, 1)',
            borderWidth: 1
        }]
    },
    options: {
        ...commonOptions,
        indexAxis: 'y',  // Hace que el gráfico sea horizontal
        scales: {
            x: {
                beginAtZero: true,
                ticks: {
                    color: 'white'
                },
                grid: {
                    color: 'rgba(255, 255, 255, 0.1)'
                }
            },
            y: {
                ticks: {
                    color: 'white',
                    font: {
                        size: 12  // Ajusta el tamaño del texto para los nombres de autores
                    }
                },
                grid: {
                    color: 'rgba(255, 255, 255, 0.1)'
                }
            }
        },
        plugins: {
            legend: {
                display: false  // Oculta la leyenda ya que no es necesaria
            },
            datalabels: {
                color: 'white',
                anchor: 'end',
                align: 'end',
                offset: -5,
                font: {
                    weight: 'bold',
                    size: 14
                },
                formatter: (value) => value
            }
        },
        maintainAspectRatio: true,
        aspectRatio: 1.5
    }
});

window.addEventListener('resize', function() {
    Object.values(Chart.instances).forEach(chart => {
        chart.resize();
    });
});