// Keeps a copy of the page so it opens even while YouMixer is off, and can turn it on from there.
const CACHE = "youmixer-v4";
const SHELL = ["/", "/app.js", "/style.css"];
const isLanguage = (path) => path.startsWith("/i18n/") && path.endsWith(".json");

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  // Drop the copies left by earlier versions
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(names.filter((name) => name !== CACHE).map((name) => caches.delete(name))))
      .then(() => self.clients.claim()),
  );
});

// Always the server's version when it is on; the saved copy only when it is off.
// Language files are saved as they get used, so a new language needs no changes here.
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  const cacheable = SHELL.includes(url.pathname) || isLanguage(url.pathname);
  if (event.request.method !== "GET" || url.origin !== location.origin || !cacheable) return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(url.pathname, copy));
        }
        return response;
      })
      .catch(() => caches.match(url.pathname)),
  );
});
