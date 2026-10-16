// Shows Enveliq reminders as pop-ups. It holds no data and makes no requests.
"use strict";
self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = {}; }
  const title = String(data.title || "Enveliq").slice(0, 120);
  const body = String(data.body || "").slice(0, 300);
  const url = typeof data.url === "string" ? data.url : "/";
  event.waitUntil(self.registration.showNotification(title, { body, data: { url }, icon: "/brand/enveliq-icon-128.webp", badge: "/brand/enveliq-badge-96.png" }));
});
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  let target = self.location.origin + "/";
  try {
    const u = new URL((event.notification.data && event.notification.data.url) || "/", self.location.origin);
    if (u.origin === self.location.origin) target = u.href;
  } catch (e) { /* keep the default */ }
  event.waitUntil((async () => {
    const list = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const c of list) {
      let path = "";
      try { const cu = new URL(c.url); if (cu.origin !== self.location.origin) continue; path = cu.pathname; } catch (e) { continue; }
      // Do not navigate an existing PWA activity to the notification URL:
      // navigation can replace its inbox history and Android Back exits.
      if (path === "/") {
        try {
          await c.focus();
          c.postMessage({ type: "enveliq-open", url: target });
          return;
        } catch (e) { /* try another client or a fresh launch */ }
      }
    }
    // On a cold start open the inbox URL with the notification target encoded.
    // This is a normal app launch and the reader must push its own history
    // entry after the inbox document has finished loading.
    await self.clients.openWindow(target);
  })());
});
