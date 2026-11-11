// Minimaler Service Worker – nötig, damit die Seite als App installierbar ist.
// Die Maus braucht ohnehin die Verbindung zum PC, daher kein Offline-Cache.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});
