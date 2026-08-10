// Service worker del sitio. Lo sirve Django en /sw.js para que su ambito sea
// la raiz; servido bajo /static/ solo controlaria /static/.
const VERSION = '{{ sw_version }}';
const CACHE_NAME = 'bitacora-' + VERSION;
const OFFLINE_URL = '{{ offline_url }}';
const PRECACHE = {{ precache_urls }};

self.addEventListener('install', (event) => {
    event.waitUntil((async () => {
        const cache = await caches.open(CACHE_NAME);
        // addAll es todo-o-nada: si un recurso falla no se instala nada, asi que
        // cada uno se cachea por separado y solo la pagina offline es critica.
        await cache.add(new Request(OFFLINE_URL, { cache: 'reload' }));
        await Promise.all(PRECACHE.map((url) => cache.add(url).catch(() => null)));
        await self.skipWaiting();
    })());
});

self.addEventListener('activate', (event) => {
    event.waitUntil((async () => {
        const names = await caches.keys();
        await Promise.all(
            names
                .filter((name) => name.startsWith('bitacora-') && name !== CACHE_NAME)
                .map((name) => caches.delete(name))
        );
        await self.clients.claim();
    })());
});

// Solo /static/: sus nombres llevan hash, asi que una entrada vieja nunca se
// sirve por error. /media/ (portadas y caratulas) se queda fuera a proposito —
// ya viaja con 30 dias de cache HTTP y meterlo aqui duplicaria cientos de
// imagenes en el disco del navegador sin ganar nada.
function isCacheableAsset(url) {
    return url.pathname.startsWith('/static/');
}

// Navegaciones: siempre red. No se guardan en cache a proposito — el feed, las
// noticias guardadas y el admin son contenido personal y cambiante, y servirlo
// del disco daria una pagina vieja sin que se note. Si no hay red, cae en la
// pagina offline.
async function handleNavigation(request) {
    try {
        return await fetch(request);
    } catch (error) {
        const cache = await caches.open(CACHE_NAME);
        const offline = await cache.match(OFFLINE_URL);
        return offline || Response.error();
    }
}

// Estaticos y portadas: cache primero (los estaticos llevan hash en el nombre y
// las portadas no cambian), revalidando en segundo plano.
async function handleAsset(request) {
    const cache = await caches.open(CACHE_NAME);
    const cached = await cache.match(request);

    const network = fetch(request)
        .then((response) => {
            if (response && response.ok && response.type === 'basic') {
                cache.put(request, response.clone());
            }
            return response;
        })
        .catch(() => null);

    if (cached) {
        return cached;
    }
    const response = await network;
    return response || Response.error();
}

self.addEventListener('fetch', (event) => {
    const request = event.request;

    if (request.method !== 'GET') {
        return;
    }

    const url = new URL(request.url);
    if (url.origin !== self.location.origin) {
        return;
    }
    if (url.pathname.startsWith('/j_admin/')) {
        return;
    }

    if (request.mode === 'navigate') {
        event.respondWith(handleNavigation(request));
        return;
    }

    if (isCacheableAsset(url)) {
        event.respondWith(handleAsset(request));
    }
});
