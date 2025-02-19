Chart.register(ChartDataLabels);

const chartDefaults = {
    devicePixelRatio: 2,
    animation: {
        duration: 0
    }
};

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
        maintainAspectRatio: true,
        aspectRatio: 2,
        plugins: {
            legend: {
                position: 'right',
                labels: { 
                    color: 'white',
                    font: {
                        size: 12
                    }
                }
            },
            datalabels: {
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
        aspectRatio: 2,
        indexAxis: 'y',
        plugins: {
            legend: { display: false },
            datalabels: {
                color: 'white',
                anchor: 'center',
                align: 'center'
            }
        },
        scales: {
            x: {
                grid: {
                    display: false
                },
                ticks: {
                    color: 'white'
                }
            },
            y: {
                grid: {
                    display: false
                },
                ticks: {
                    color: 'white'
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
        aspectRatio: window.innerWidth < 768 ? 1.6 : 2,
        plugins: {
            legend: { display: false },
            datalabels: {
                display: false
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