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
      try {
        // Chrome can skip pushState entries created without page user activation.
        // Make the notification a real browser navigation so Back has a real
        // previous inbox document, including when the PWA was backgrounded.
        if (path === "/") {
          const opened = await c.navigate(target);
          try { await (opened || c).focus(); } catch (e) { /* navigation succeeded even if focus was denied */ }
          return;
        }
      } catch (e) { /* try another existing app window */ }
    }
    // Cold launch: build a real document navigation stack from inbox to mail.
    // Automatically pushed SPA states may be ignored by Android Back.
    const inbox = await self.clients.openWindow(self.location.origin + "/");
    if (inbox) {
      try {
        const opened = await inbox.navigate(target);
        try { await (opened || inbox).focus(); } catch (e) { /* keep successfully opened window */ }
        return;
      } catch (e) { /* fall back to opening the notification directly */ }
    }
    await self.clients.openWindow(target);
  })());
});
