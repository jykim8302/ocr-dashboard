/* 사과 송장 앱 서비스 워커
   - 문자 앱 등에서 "공유 → 사과 송장"으로 보낸 문자·사진을 받아서 앱에 넘겨줘요
   - 한 번 열었던 화면은 인터넷이 끊겨도 열리게 저장해 둬요 */
const APP_CACHE = 'apple-invoice-app-v2';
const SHARE_CACHE = 'apple-invoice-share';
const APP_FILES = ['apple_invoice.html', 'manifest.webmanifest', 'icon-192.png', 'icon-512.png', 'icon-maskable-512.png', 'apple-touch-icon.png', 'install-qr.png'];
const here = path => new URL(path, self.registration.scope).href;

self.addEventListener('install', event => {
  event.waitUntil(caches.open(APP_CACHE).then(cache => cache.addAll(APP_FILES.map(here))).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if (key !== APP_CACHE && key !== SHARE_CACHE) await caches.delete(key);
    }
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method === 'POST' && url.href === here('share-target')) {
    event.respondWith(receiveShare(event.request));
    return;
  }
  // 우편번호·글자 인식 같은 다른 사이트 요청은 그대로 보내요
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;
  event.respondWith(networkFirst(event.request));
});

/* 공유받은 문자·사진을 잠깐 저장해 두고 앱 화면으로 넘어가요 */
async function receiveShare(request) {
  const form = await request.formData();
  const text = ['title', 'text', 'url']
    .map(key => form.get(key))
    .filter(v => typeof v === 'string' && v.trim())
    .join('\n');
  const image = form.getAll('image').find(f => f && typeof f !== 'string' && f.size);
  const cache = await caches.open(SHARE_CACHE);
  await cache.put(here('shared-text'), new Response(text, { headers: { 'Content-Type': 'text/plain; charset=utf-8' } }));
  if (image) await cache.put(here('shared-image'), new Response(image, { headers: { 'Content-Type': image.type || 'image/png' } }));
  else await cache.delete(here('shared-image'));
  return Response.redirect(here('apple_invoice.html?shared=1'), 303);
}

/* 새 버전이 있으면 받아오고, 인터넷이 안 되면 저장해 둔 화면을 보여줘요 */
async function networkFirst(request) {
  const cache = await caches.open(APP_CACHE);
  try {
    const response = await fetch(request);
    if (response.ok) cache.put(request, response.clone());
    return response;
  } catch (e) {
    return (await cache.match(request, { ignoreSearch: true })) || Response.error();
  }
}
