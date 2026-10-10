// Shows Enveliq reminders as pop-ups. It holds no data and makes no requests.
"use strict";
self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = {}; }
  const title = String(data.title || "Enveliq").slice(0, 120);
  const body = String(data.body || "").slice(0, 300);
  const url = typeof data.url === "string" ? data.url : "/";
  event.waitUntil(self.registration.showNotification(title, { body, data: { url }, icon: "/brand/enveliq-icon-128.webp" }));
});
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  let target = self.location.origin + "/";
  try {
    const u = new URL((event.notification.data && event.notification.data.url) || "/", self.location.origin);
    if (u.origin === self.location.origin) target = u.href;
  } catch (e) { /* keep the default */ }
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
    for (const c of list) { if ("focus" in c) { return c.focus(); } }
    return self.clients.openWindow(target);
  }));
});
