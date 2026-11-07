// Cache only static app shell assets; CRM data, APIs and identity tokens are never cached.
const CACHE = "revenueos-static-v1";
self.addEventListener("install", event => {self.skipWaiting();event.waitUntil(caches.open(CACHE));});
self.addEventListener("activate", event => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", event => {
  if(event.request.method !== "GET" || event.request.mode === "navigate") return;
  const url = new URL(event.request.url);
  if(url.origin !== self.location.origin || !url.pathname.startsWith("/_next/static/")) return;
  event.respondWith(caches.match(event.request).then(hit => hit || fetch(event.request).then(res => {
    if(res.ok){const copy=res.clone();caches.open(CACHE).then(c=>c.put(event.request,copy));}return res;
  })));
});
