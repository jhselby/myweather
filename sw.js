// Wyman Cove Weather — Service Worker
// Bump CACHE_VERSION with each deploy to invalidate old caches
const CACHE_VERSION = 'wc-v1';
const APP_SHELL = [
  '/myweather/',
  '/myweather/index.html',
  '/myweather/styles/app.css',
  '/myweather/styles/briefing.css',
  '/myweather/js/app-main.js',
  '/myweather/js/briefing.js',
  '/myweather/icon-192.png',
  '/myweather/icon-512.png',
  '/myweather/manifest.json'
];

// Pre-cache app shell on install
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_VERSION)
      .then(cache => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting())
  );
});

// Clean up old caches on activate
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_VERSION).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Fetch strategy:
// - Weather data (GCS bucket): network-only, never cache stale weather
// - App shell / CDN assets: stale-while-revalidate
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Never cache weather data or analytics
  if (url.pathname.includes('weather_data') ||
      url.hostname.includes('goatcounter') ||
      url.hostname.includes('storage.googleapis.com')) {
    return; // let browser handle normally
  }

  event.respondWith(
    caches.match(event.request).then(cached => {
      // Return cache hit, but also fetch in background to update cache
      const fetchPromise = fetch(event.request).then(response => {
        if (response && response.status === 200 && response.type === 'basic') {
          const clone = response.clone();
          caches.open(CACHE_VERSION).then(cache => cache.put(event.request, clone));
        }
        return response;
      }).catch(() => cached);

      return cached || fetchPromise;
    })
  );
});
