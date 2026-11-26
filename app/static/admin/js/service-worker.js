// Service worker for desktop alerts. Registered by push.js. It only shows the notification the server
// sends and opens the booking when it is clicked; it holds no Firebase code and no settings.

self.addEventListener("activate", (event) => {
  // Claim all clients immediately so this worker controls the page without a reload.
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
  let payload = {};
  try { payload = event.data ? event.data.json() : {}; } catch (error) { /* not JSON: show the default text */ }
  // FCM wraps a data-only message as { data: {...} }; accept a bare object too.
  const message = payload.data || payload.notification || payload;
  event.waitUntil(self.registration.showNotification(message.title || "BLESS Admin", {
    body: message.body || "",
    tag: message.tag || undefined,
    icon: "/static/shared/img/bless-logo.webp",
    data: { url: message.url || "" },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  // Only open our own admin pages, whatever the message says.
  const path = String(event.notification.data?.url || "");
  const target = new URL(path.startsWith("/admin/") ? path : "/admin/bookings", self.location.origin).href;
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    const open = windows.find((w) => w.url === target);
    return open ? open.focus() : self.clients.openWindow(target);
  })());
});
