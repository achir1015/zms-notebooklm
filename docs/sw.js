// 離線快取：改了程式要遞增 CACHE，使用者才會拿到新版
const CACHE = "zms-notebooklm-v2";
const CORE = ["./", "index.html", "icon.png", "manifest.webmanifest", "app/", "app/index.html", "app/style.css", "app/app.js",
  "app/data.js", "app/engine.js", "app/deck.js", "app/render.js", "app/webpage.tpl.html", "app/icon.png",
  "app/lib/jszip.min.js", "app/lib/pptxgen.bundle.js"];
self.addEventListener("install", (e) => { e.waitUntil(caches.open(CACHE).then((c) => c.addAll(CORE)).then(() => self.skipWaiting())); });
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin) return;
  e.respondWith(caches.match(e.request).then((hit) => hit || fetch(e.request).then((r) => {
    if (r.ok) { const copy = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); }
    return r;
  })));
});
