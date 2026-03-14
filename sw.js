// Sovereign News Curator — Service Worker
// Strategy: network-first with cache fallback for offline reading.

const CACHE = 'snc-v1';
const PRECACHE = ['./', './manifest.json', './version.json'];
const VERSION_STORE_KEY = 'snc-digest-version';

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(PRECACHE)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  e.respondWith(
    fetch(e.request)
      .then(response => {
        const clone = response.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return response;
      })
      .catch(() => caches.match(e.request))
  );
});

// ── Periodic Background Sync: check for new digest hourly ──
async function checkForNewDigest() {
  try {
    const res = await fetch('./version.json', { cache: 'no-store' });
    if (!res.ok) return;
    const { date } = await res.json();

    const stored = await self.registration.getNotifications
      ? null // will read from IDB or just fire notification
      : null;

    // Notify all open clients to update their localStorage and show banner
    const clientList = await self.clients.matchAll({ type: 'window' });
    for (const client of clientList) {
      client.postMessage({ type: 'NEW_DIGEST', date });
    }

    // Show push notification if no window is focused
    const focused = clientList.some(c => c.focused);
    if (!focused && self.registration.showNotification) {
      await self.registration.showNotification('ملخص جديد متاح', {
        body: `ملخص ${date} جاهز للقراءة`,
        icon: './icon-180.png',
        badge: './icon-180.png',
        data: { url: './' },
        tag: 'new-digest',
        renotify: true,
      });
    }
  } catch (_) {
    // Network unavailable — silently skip
  }
}

self.addEventListener('periodicsync', e => {
  if (e.tag === 'check-digest') {
    e.waitUntil(checkForNewDigest());
  }
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clientList => {
      for (const client of clientList) {
        if ('focus' in client) return client.focus();
      }
      return self.clients.openWindow(e.notification.data?.url || './');
    })
  );
});
