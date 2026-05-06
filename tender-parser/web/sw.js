// Service Worker — Тендер PRO
// Стратегия: Cache-First для статики, Network-First для API

const CACHE_NAME = 'tender-pro-v2';
const STATIC_ASSETS = [
  '/web/',
  '/web/index.html',
  '/web/auctions.html',
  '/web/grants.html',
  '/web/favorites.html',
  '/web/subscribe.html',
  '/web/stats.html',
  '/web/social-contract.html',
  '/web/about.html',
  '/web/app.js',
  '/web/auctions.js',
  '/web/grants.js',
  '/web/favorites.js',
  '/web/subscribe.js',
  '/web/stats.js',
  '/web/social-contract.js',
  '/web/navbar.js',
  '/web/shared.js',
  '/web/styles.css',
  '/web/vendor/chart.umd.min.js',
  '/web/manifest.json',
  '/web/icon-192.png',
  '/web/icon-512.png',
];

// Install: skip waiting (no pre-cache — lazy-cache on first use)
self.addEventListener('install', () => {
  self.skipWaiting();
});

// Activate: чистим старые кеши
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      );
    })
  );
  self.clients.claim();
});

// Fetch: Cache-first для статики, Network-first для API
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // API запросы — только сеть (не кешируем динамические данные)
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(event.request).catch(() => {
        return new Response(
          JSON.stringify({ error: 'offline', detail: 'Нет подключения к сети' }),
          { status: 503, headers: { 'Content-Type': 'application/json' } }
        );
      })
    );
    return;
  }

  // Статика — cache-first
  if (event.request.method === 'GET') {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        // Обновляем кеш в фоне (stale-while-revalidate)
        const fetchPromise = fetch(event.request).then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(event.request, clone);
            });
          }
          return response;
        }).catch(() => cached);
        return cached || fetchPromise;
      })
    );
  }
});
