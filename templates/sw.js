// Service worker del sitio. Lo sirve Django en /sw.js para que su ambito sea
// la raiz; servido bajo /static/ solo controlaria /static/.
const VERSION = '{{ sw_version }}';
const CACHE_NAME = 'bitacora-' + VERSION;
const OFFLINE_URL = '{{ offline_url }}';
const HOME_URL = '{{ home_url }}';
const PRECACHE = {{ precache_urls }};

// Nombre con hash de ManifestStaticFilesStorage: `base.56e2f08b3ba8.css`. Una
// URL asi es inmutable por definicion —si el fichero cambia, cambia la URL—,
// de modo que revalidarla no puede devolver nada distinto.
const HASHED_ASSET = /\.[0-9a-f]{12}\.[^./]+$/;

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

// Navegaciones: red, salvo la portada. El feed, las noticias guardadas y el
// admin son contenido personal y cambiante, y servirlos del disco daria una
// pagina vieja sin que se note. Si no hay red, cae en la pagina offline.
async function handleNavigation(request) {
    try {
        return await fetch(request);
    } catch (error) {
        const cache = await caches.open(CACHE_NAME);
        const offline = await cache.match(OFFLINE_URL);
        return offline || Response.error();
    }
}

// La portada es la excepcion, y solo ella: es `start_url`, o sea la pantalla
// con la que abre la aplicacion instalada, y no tiene NADA personal — titulo,
// lema, cuatro enlaces y el pie. Iba por red como el resto, asi que cada
// arranque de la app esperaba el TTFB del servidor (medido: 500-660 ms) con la
// ventana en blanco. Eso es lo que se veia "siempre al abrir la app".
//
// Se sirve de cache y se revalida por detras, de manera que:
//  - la ventana pinta al instante,
//  - el servidor recibe igual su peticion, asi que la visita se sigue
//    registrando y la copia guardada queda fresca para el proximo arranque,
//  - un cambio en el texto de la portada se ve un arranque tarde. Es el precio.
//
// Lo que SI habria que vigilar: el HTML guardado apunta a los estaticos con su
// hash, y `collectstatic --clear` borra los viejos. Por eso todos los estaticos
// que usa la portada estan en PRECACHE, cuyo hash da nombre a la cache: si
// cambia cualquiera de ellos la cache entera se descarta y el HTML viejo con
// ella. Al anadir un estatico a la portada hay que anadirlo tambien alli.
async function handleHome(request, event) {
    const cache = await caches.open(CACHE_NAME);
    const cached = await cache.match(HOME_URL);

    const network = fetch(request)
        .then((response) => {
            if (response && response.ok && response.type === 'basic') {
                cache.put(HOME_URL, response.clone());
            }
            return response;
        })
        .catch(() => null);

    if (cached) {
        // Sin esto el navegador puede matar el worker en cuanto respondemos y
        // la revalidacion se quedaria a medias: la copia no se refrescaria nunca.
        event.waitUntil(network);
        return cached;
    }

    const response = await network;
    if (response) {
        return response;
    }
    const offline = await cache.match(OFFLINE_URL);
    return offline || Response.error();
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

// Con hash en el nombre no hay nada que revalidar: la respuesta de red seria
// byte por byte la misma. Antes se pedia igual, asi que cada carga de la app
// disparaba una docena de peticiones de fondo contra el servidor para
// reescribir en la cache lo que ya estaba.
async function handleImmutableAsset(request) {
    const cache = await caches.open(CACHE_NAME);
    const cached = await cache.match(request);
    if (cached) {
        return cached;
    }
    return handleAsset(request);
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
        // Sin `search`: la portada con parametros (una campana, una vuelta
        // desde fuera) se pide a la red como cualquier otra navegacion.
        if (url.pathname === HOME_URL && !url.search) {
            event.respondWith(handleHome(request, event));
        } else {
            event.respondWith(handleNavigation(request));
        }
        return;
    }

    if (isCacheableAsset(url)) {
        event.respondWith(
            HASHED_ASSET.test(url.pathname)
                ? handleImmutableAsset(request)
                : handleAsset(request)
        );
    }
});
