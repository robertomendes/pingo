// O app do Pingo mudou para /app/. Este service worker antigo (da raiz) se desliga sozinho:
// apaga o cache antigo, sai de cena e recarrega as abas para mostrarem a versão nova.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    const ks = await caches.keys();
    await Promise.all(ks.filter(k => !k.startsWith('pingo-app-')).map(k => caches.delete(k)));
    await self.registration.unregister();
    const cs = await self.clients.matchAll({ type: 'window' });
    cs.forEach(c => { try { c.navigate(c.url); } catch (err) { } });
  })());
});
