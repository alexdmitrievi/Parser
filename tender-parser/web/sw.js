/* Service Worker — Тендер PRO v5
 *
 * Стратегия:
 *   - HTML: network-first с таймаутом 2.5 сек → fallback на кэш (защита от зависания CDN/DNS)
 *   - Статика (CSS/JS/PNG/JSON): stale-while-revalidate (мгновенно из кэша + фон-обновление)
 *   - API: network-first с таймаутом 4 сек → fallback на кэш или 503
 *
 * Бамп версии CACHE_NAME при изменении стратегии — это инвалидирует старый "poison cache",
 * из-за которого пользователи могли получать сломанный сайт после неудачного деплоя.
 */

const CACHE_VERSION = 'tender-pro-v5';
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const RUNTIME_CACHE = `${CACHE_VERSION}-runtime`;
const API_CACHE = `${CACHE_VERSION}-api`;

// Предкэш — ровно то, что нужно для первого мгновенного отображения
const PRECACHE_URLS = [
  '/web/index.html',
  '/web/styles.css',
  '/web/shared.js',
  '/web/navbar.js',
  '/web/app.js',
  '/web/manifest.json',
  '/web/hero.json',
  '/web/icon-192.png',
];

const HTML_TIMEOUT_MS = 2500;
const API_TIMEOUT_MS = 4000;

// fetch с таймаутом — без таймаута SW зависал при проблемах с сетью/Vercel
function fetchWithTimeout(request, timeoutMs) {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error('timeout')), timeoutMs);
    fetch(request).then((res) => { clearTimeout(t); resolve(res); }, (err) => { clearTimeout(t); reject(err); });
  });
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => cache.addAll(PRECACHE_URLS).catch(() => null))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => ![STATIC_CACHE, RUNTIME_CACHE, API_CACHE].includes(k))
          .map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// Позволяем странице принудительно обновить SW (вызов: navigator.serviceWorker.controller.postMessage('skipWaiting'))
self.addEventListener('message', (event) => {
  if (event.data === 'skipWaiting') self.skipWaiting();
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // Только same-origin — кросс-домен не трогаем (Telegram WebApp, аналитика и пр.)
  if (url.origin !== self.location.origin) return;

  // API: network-first с таймаутом, кэш как fallback
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(handleApi(req));
    return;
  }

  // HTML-страницы: network-first с быстрым таймаутом → fallback на precache
  const acceptsHtml = req.headers.get('Accept') && req.headers.get('Accept').includes('text/html');
  if (acceptsHtml || url.pathname.endsWith('.html') || url.pathname === '/' || url.pathname === '/web/') {
    event.respondWith(handleHtml(req));
    return;
  }

  // Статика: stale-while-revalidate
  event.respondWith(handleStatic(req));
});

async function handleHtml(req) {
  try {
    const fresh = await fetchWithTimeout(req, HTML_TIMEOUT_MS);
    if (fresh && fresh.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(req, fresh.clone()).catch(() => {});
      return fresh;
    }
    throw new Error('not ok');
  } catch (_) {
    const cached = await caches.match(req) || await caches.match('/web/index.html');
    if (cached) return cached;
    return new Response(
      '<!doctype html><meta charset="utf-8"><title>Офлайн</title><div style="font-family:sans-serif;padding:2rem;text-align:center"><h1>Нет соединения</h1><p>Проверьте интернет и обновите страницу.</p></div>',
      { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
    );
  }
}

async function handleStatic(req) {
  const cache = await caches.open(RUNTIME_CACHE);
  const cached = await cache.match(req) || await caches.match(req);

  const networkPromise = fetch(req).then((res) => {
    if (res && res.ok) cache.put(req, res.clone()).catch(() => {});
    return res;
  }).catch(() => null);

  if (cached) {
    networkPromise.catch(() => {});
    return cached;
  }
  const fresh = await networkPromise;
  if (fresh) return fresh;
  return new Response('', { status: 504 });
}

async function handleApi(req) {
  try {
    const fresh = await fetchWithTimeout(req, API_TIMEOUT_MS);
    if (fresh && fresh.ok) {
      const cache = await caches.open(API_CACHE);
      cache.put(req, fresh.clone()).catch(() => {});
    }
    return fresh;
  } catch (_) {
    const cached = await caches.match(req);
    if (cached) return cached;
    return new Response(
      JSON.stringify({ error: 'offline', detail: 'Нет соединения' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  }
}
