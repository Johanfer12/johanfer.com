document.addEventListener('DOMContentLoaded', (event) => {
    
    const WIDTH_IN_PERCENT_OF_PARENT = 100;
    const HEIGHT_IN_PERCENT_OF_PARENT = 50;
    const booksPerYearChartContainer = document.getElementById('booksPerYearChart');
    const starsChartContainer = document.getElementById('starsChart');
    const topAuthorsChartContainer = document.getElementById('topAuthorsChart');
    var d3 = Plotly.d3;

    function createNonInteractiveChart(container, data, layout) {
        const gd3 = d3.select(container)
            .style({
                width: `${WIDTH_IN_PERCENT_OF_PARENT}%`,
                'margin-left': `${(100 - WIDTH_IN_PERCENT_OF_PARENT) / 2}%`,
                height: `${HEIGHT_IN_PERCENT_OF_PARENT}vh`
            });
    
        const gd = gd3.node();
    
        // Determinar el tamaño de la fuente según la orientación de la pantalla
        const isLandscape = window.innerWidth > window.innerHeight;
        const fontSize = isLandscape ? 13 : 26;
    
        // Modificar la configuración de la fuente en el layout
        layout.font.size = fontSize;
    
        // Configuración para gráficas no interactivas
        const config = {
            staticPlot: true,
            displayModeBar: false
        };
    
        Plotly.newPlot(gd, data, layout, config);
    
        window.onresize = function() {
            Plotly.Plots.resize(gd);
        };
    }
    
    const booksPerYearData = {
        x: JSON.parse(document.getElementById('books-per-year-data').textContent),
        y: JSON.parse(document.getElementById('books-per-year-values').textContent),
        type: 'bar',
        marker: { color: 'rgba(75, 192, 192, 0.6)' },
        text: JSON.parse(document.getElementById('books-per-year-values').textContent),
        textposition: 'auto',
        textfont: { color: 'white' }
    };

    const starsData = {
        labels: JSON.parse(document.getElementById('stars-labels').textContent),
        values: JSON.parse(document.getElementById('stars-values').textContent),
        type: 'pie',
        textfont: { color: 'white' },
        marker: { colors: [
            'rgba(255, 99, 132, 0.6)',
            'rgba(54, 162, 235, 0.6)',
            'rgba(255, 43, 41, 0.6)',
            'rgba(75, 192, 192, 0.6)',
            'rgba(153, 102, 255, 0.6)'
        ]}
    };

    const topAuthorsLabels = JSON.parse(document.getElementById('top-authors-labels').textContent).reverse();
    const topAuthorsValues = JSON.parse(document.getElementById('top-authors-values').textContent).reverse();
    
    const topAuthorsData = {
        x: topAuthorsValues,
        y: topAuthorsLabels,
        type: 'bar',
        orientation: 'h',
        marker: { color: 'rgba(125, 118, 166, 0.6)' },
        text: topAuthorsValues,
        textposition: 'auto',
        textfont: { color: 'white' }
    };

    createNonInteractiveChart(booksPerYearChartContainer, [booksPerYearData], {
        paper_bgcolor: 'rgba(0,0,0,0.5)',
        plot_bgcolor: '#212121',
        font: {
            color: 'white',
        },
        xaxis: {
            gridcolor: 'rgba(255, 255, 255, 0.2)',
            tickcolor: 'white',
            tickmode: 'array',
            tickvals: JSON.parse(document.getElementById('books-per-year-data').textContent),
            ticktext: JSON.parse(document.getElementById('books-per-year-data').textContent),
            tickangle: -45
        },
        yaxis: {
            gridcolor: 'rgba(255, 255, 255, 0.2)',
            tickcolor: 'white'
        }
    });

    createNonInteractiveChart(starsChartContainer, [starsData], {
        paper_bgcolor: 'rgba(0,0,0,0.5)',
        font: {
            color: 'white',
        },
        legend_bgcolor: '#212121',
        legend: {
            font: {
                color: 'white' 
            },
            bgcolor : '#212121',
        }
    });

    createNonInteractiveChart(topAuthorsChartContainer, [topAuthorsData], {
        paper_bgcolor: 'rgba(0,0,0,0.5)',
        plot_bgcolor: '#212121',
        font: {
            color: 'white',
        },
        xaxis: {
            gridcolor: 'rgba(255, 255, 255, 0.2)',
            tickcolor: 'white'
        },
        yaxis: {
            gridcolor: 'rgba(255, 255, 255, 0.2)',
            tickcolor: 'white',
            tickangle: 0,
            automargin: true
        },
        margin: {
            l: 100
        },
        bargap: 0.1
    });
});