// Motor de scroll infinito con búsqueda, compartido por Mis Libros y Mi TV.
//
// Las dos páginas repetían la misma máquina de estado: el guard de carga, el
// alta y baja del listener de scroll, el indicador, el reseteo al buscar y las
// ramas de error. Lo que de verdad cambia entre ellas es el endpoint, los
// filtros propios y cómo se pinta cada tarjeta, y eso se pasa como
// configuración.
//
// Las tandas se piden por offset y límite, y el límite lo decide la pantalla:
// las columnas que caben en la rejilla y las filas que llenan la ventana. Con
// tandas fijas de 20, un monitor de 8 columnas dejaba la última fila a medias
// y, si la página no llegaba a pasar de la altura de la ventana, no había
// scroll que pidiera la siguiente. Ahora cada tanda acaba en fila completa y,
// tras cada carga y al cambiar el tamaño de la ventana, se sigue pidiendo
// mientras falte una fila por completar o la página no llene la pantalla.
//
// Devuelve { applySearch }, que es lo que search_modal.js necesita.
window.createInfiniteScroll = function ({container, endpoint, params, render, onLoaded}) {
    if (!container) {
        return {applySearch: () => Promise.resolve({})};
    }

    // Tope del servidor (TANDA_MAXIMA en Bookshelf/http_utils.py).
    const MAX_BATCH = 96;
    // Margen bajo la ventana: se pide la siguiente tanda antes de llegar al final.
    const PREFETCH_PX = 500;

    const loadingDiv = document.getElementById('loading');
    let loading = false;
    let hasNext = container.dataset.hasNext === 'true';
    let query = (new URLSearchParams(window.location.search).get('q') || '').trim();

    // El indicador se muestra con una clase, no con style.display: la pastilla
    // necesita display:flex y un estilo en línea lo pisaría.
    const setLoadingVisible = (visible) => {
        if (loadingDiv) {
            loadingDiv.classList.toggle('is-visible', visible);
        }
    };

    const items = () => container.querySelectorAll(':scope > .book-item');

    const columns = () => {
        const tracks = getComputedStyle(container).gridTemplateColumns.split(' ').filter(Boolean);
        return Math.max(tracks.length, 1);
    };

    const rowHeight = () => {
        const first = items()[0];
        const gap = parseFloat(getComputedStyle(container).rowGap) || 0;
        return (first ? first.getBoundingClientRect().height : 300) + gap;
    };

    // Cuántas tarjetas pedir para que, tras la tanda, la rejilla acabe en una
    // fila completa y haya al menos una pantalla más de filas.
    const batchSize = (alreadyShown) => {
        const cols = columns();
        const toCompleteRow = (cols - (alreadyShown % cols)) % cols;
        const screenRows = Math.max(2, Math.ceil(window.innerHeight / rowHeight()));
        const maxRows = Math.max(1, Math.floor((MAX_BATCH - toCompleteRow) / cols));
        return toCompleteRow + cols * Math.min(screenRows, maxRows);
    };

    const buildParams = (offset, limit) => {
        const search = new URLSearchParams();
        Object.entries(params() || {}).forEach(([key, value]) => {
            if (value) {
                search.set(key, value);
            }
        });
        if (query) {
            search.set('q', query);
        }
        if (typeof offset === 'number') {
            search.set('offset', String(offset));
            search.set('limit', String(limit));
        }
        return search;
    };

    const request = (search) => fetch(`${endpoint}?${search.toString()}`, {
        headers: {'X-Requested-With': 'XMLHttpRequest'},
    }).then((response) => response.json());

    const nearBottom = () =>
        window.innerHeight + window.scrollY >= document.body.offsetHeight - PREFETCH_PX;

    const rowIsIncomplete = () => items().length % columns() !== 0;

    // Tras cada carga, al arrancar y al cambiar el tamaño: si falta completar
    // una fila o la página no llena la pantalla, pedir otra tanda.
    const fill = () => {
        if (hasNext && !loading && (rowIsIncomplete() || nearBottom())) {
            loadMore();
        }
    };

    const listenWhileThereIsMore = () => {
        window.removeEventListener('scroll', handleScroll);
        if (hasNext) {
            window.addEventListener('scroll', handleScroll, {passive: true});
        }
    };

    function handleScroll() {
        if (nearBottom()) {
            loadMore();
        }
    }

    function loadMore() {
        if (loading || !hasNext) return;

        loading = true;
        setLoadingVisible(true);

        const shown = items().length;
        request(buildParams(shown, batchSize(shown)))
            .then((data) => {
                render(data, {replace: false});
                hasNext = Boolean(data.has_next);
                listenWhileThereIsMore();
            })
            .catch((error) => {
                console.error('Error al cargar más resultados:', error);
                // Sin esto, un fallo de red dejaría fill() pidiendo en bucle.
                hasNext = false;
                listenWhileThereIsMore();
            })
            .finally(() => {
                loading = false;
                setLoadingVisible(false);
                requestAnimationFrame(fill);
            });
    }

    const applySearch = (value) => {
        query = (value || '').trim();

        // La URL solo guarda filtros y búsqueda: el tamaño de tanda depende de
        // la pantalla de cada uno.
        window.history.replaceState({}, '', `${window.location.pathname}?${buildParams().toString()}`);

        loading = true;
        setLoadingVisible(true);

        return request(buildParams(0, batchSize(0)))
            .then((data) => {
                render(data, {replace: true});
                hasNext = Boolean(data.has_next);
                if (onLoaded) {
                    onLoaded(data, query);
                }
                listenWhileThereIsMore();
                return data;
            })
            .catch((error) => {
                console.error('Error al aplicar búsqueda:', error);
                throw error;
            })
            .finally(() => {
                loading = false;
                setLoadingVisible(false);
                requestAnimationFrame(fill);
            });
    };

    let resizeTimer = null;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(fill, 200);
    }, {passive: true});

    listenWhileThereIsMore();
    fill();

    return {applySearch};
};
