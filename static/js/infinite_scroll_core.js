// Motor de scroll infinito con búsqueda, compartido por Mis Libros y Mi TV.
//
// Las dos páginas repetían la misma máquina de estado: el guard de carga, el
// alta y baja del listener de scroll, el indicador, el reseteo de paginación al
// buscar y las ramas de error. Lo que de verdad cambia entre ellas es el
// endpoint, los filtros propios y cómo se pinta cada tarjeta, y eso se pasa
// como configuración.
//
// Devuelve { applySearch }, que es lo que search_modal.js necesita.
window.createInfiniteScroll = function ({container, endpoint, params, render, onLoaded}) {
    if (!container) {
        return {applySearch: () => Promise.resolve({})};
    }

    const loadingDiv = document.getElementById('loading');
    let page = 1;
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

    const buildParams = (pageNumber) => {
        const search = new URLSearchParams();
        search.set('page', String(pageNumber));
        Object.entries(params() || {}).forEach(([key, value]) => {
            if (value) {
                search.set(key, value);
            }
        });
        if (query) {
            search.set('q', query);
        }
        return search;
    };

    const request = (search) => fetch(`${endpoint}?${search.toString()}`, {
        headers: {'X-Requested-With': 'XMLHttpRequest'},
    }).then((response) => response.json());

    const listenWhileThereIsMore = () => {
        window.removeEventListener('scroll', handleScroll);
        if (hasNext) {
            window.addEventListener('scroll', handleScroll);
        }
    };

    function handleScroll() {
        if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 500) {
            loadMore();
        }
    }

    function loadMore() {
        if (loading || !hasNext) return;

        loading = true;
        setLoadingVisible(true);

        request(buildParams(page + 1))
            .then((data) => {
                render(data, {replace: false});
                page += 1;
                hasNext = Boolean(data.has_next);
                listenWhileThereIsMore();
            })
            .catch((error) => {
                console.error('Error al cargar más resultados:', error);
            })
            .finally(() => {
                loading = false;
                setLoadingVisible(false);
            });
    }

    const applySearch = (value) => {
        query = (value || '').trim();
        page = 1;

        const search = buildParams(1);
        window.history.replaceState({}, '', `${window.location.pathname}?${search.toString()}`);

        loading = true;
        setLoadingVisible(true);

        return request(search)
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
            });
    };

    listenWhileThereIsMore();

    return {applySearch};
};

// Escapado por el DOM, que es el que sabe de verdad qué hay que escapar.
window.escapeHtml = function (value) {
    const div = document.createElement('div');
    div.textContent = value || '';
    return div.innerHTML;
};
