// Desktop alerts for the admin: asks the browser for permission, subscribes through Firebase Cloud
// Messaging and gives the server the token. The server then pushes each new booking.
// Needs HTTPS (or localhost). The sidebar button stays hidden where the browser cannot do this.
import { initializeApp } from "https://www.gstatic.com/firebasejs/11.0.2/firebase-app.js";
import { getMessaging, getToken, isSupported } from "https://www.gstatic.com/firebasejs/11.0.2/firebase-messaging.js";

// Served from the site root (see main.py) so its scope can be the whole origin.
// FCM web push with VAPID keys requires root scope; the worker itself filters to /admin/ pages.
const SW_URL = "/service-worker.js";
const SW_SCOPE = "/";
const OLD_SW_SCOPES = ["/static/admin/js/", "/admin/"]; // old scopes to clean up
const STORAGE_KEY = "admin-push";
const RESEND_AFTER_MS = 24 * 60 * 60 * 1000;
const button = document.querySelector("[data-push-toggle]");
const label = document.querySelector("[data-push-label]");
const config = JSON.parse(document.getElementById("push-config").textContent);

function show(text, { enabled = false, hint = "" } = {}) {
  label.textContent = text;
  button.title = hint || text;
  button.disabled = !enabled;
  button.hidden = false;
}

// Wait for this registration to be active before asking for a token.
async function activated(registration) {
  const worker = registration.installing || registration.waiting || registration.active;
  if (!worker || worker.state === "activated") return;
  await new Promise((resolve) => worker.addEventListener("statechange", () => { if (worker.state === "activated") resolve(); }));
}

function remembered() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}"); } catch (error) { return {}; }
}

async function subscribe() {
  // Drop the old registrations. Their push subscriptions then end, and the server
  // removes those dead tokens the next time it sends.
  let hadOld = false;
  for (const old of await navigator.serviceWorker.getRegistrations()) {
    if (OLD_SW_SCOPES.includes(new URL(old.scope).pathname)) {
      await old.unregister();
      hadOld = true;
    }
  }
  // If we removed an old worker that was controlling the page, reload so the new root-scope
  // worker becomes the active controller. getToken() needs the worker to be controlling.
  if (hadOld && navigator.serviceWorker.controller) {
    window.location.reload();
    return; // the reload will re-run subscribe() with a clean slate
  }
  const registration = await navigator.serviceWorker.register(SW_URL, { scope: SW_SCOPE });
  await activated(registration);
  const messaging = getMessaging(initializeApp(config.firebase, "push"));
  const token = await getToken(messaging, { vapidKey: config.vapidKey, serviceWorkerRegistration: registration });
  if (!token) throw new Error("no token");
  // Tell the server when the token is new, and once a day otherwise.
  const saved = remembered();
  if (saved.token !== token || Date.now() - (saved.at || 0) > RESEND_AFTER_MS) {
    const response = await fetch("/admin/push/register", {
      method: "POST", credentials: "same-origin",
      // The CSRF cookie is not readable from script, so the page carries the token (admin/base.html).
      headers: { "Content-Type": "application/json", "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]')?.content || "" },
      body: JSON.stringify({ token }),
    });
    if (!response.ok) throw new Error(`register ${response.status}`);
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ token, at: Date.now() })); } catch (error) { /* storage unavailable */ }
  }
}

async function sync() {
  if (Notification.permission === "denied") {
    return show("Alerts blocked", { hint: "Allow notifications for this site in your browser settings." });
  }
  if (Notification.permission === "default") {
    return show("Turn on desktop alerts", { enabled: true });
  }
  try {
    await subscribe();
    show("Desktop alerts on", { hint: "Turn them off in your browser's site settings." });
  } catch (error) {
    console.warn("Desktop alerts could not be set up", error);
    show("Alerts failed. Retry", { enabled: true, hint: "Could not set up desktop alerts. Click to try again." });
  }
}

async function start() {
  if (!button || !("Notification" in window) || !("serviceWorker" in navigator) || !(await isSupported())) return;
  button.addEventListener("click", async () => {
    button.disabled = true;
    if (Notification.permission === "default") await Notification.requestPermission();
    await sync();
  });
  await sync();
}

start();
