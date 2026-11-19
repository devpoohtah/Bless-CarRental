// Admin sign-in. Firebase proves who the person is; the server then decides if they may enter.
// Flow: Firebase sign-in -> ID token -> POST /admin/session (sets an httpOnly cookie) -> dashboard.
import { initializeApp } from "https://www.gstatic.com/firebasejs/11.0.2/firebase-app.js";
import {
  getAuth, GoogleAuthProvider, signInWithPopup, signInWithEmailAndPassword, signOut,
} from "https://www.gstatic.com/firebasejs/11.0.2/firebase-auth.js";

const auth = getAuth(initializeApp(JSON.parse(document.getElementById("firebase-config").textContent)));
const errorBox = document.getElementById("login-error");
const status = document.getElementById("login-status");
const passwordForm = document.getElementById("password-form");
const turnstileWidget = document.querySelector(".cf-turnstile");

// Everything that can start a sign-in or change what is being signed in with.
const controls = document.querySelectorAll("#google-signin, #password-form button, #password-form input");

// Turnstile callbacks - must be global for implicit rendering
window.onTurnstileSuccess = () => {
  // token will be read at submit time via turnstile.getResponse()
};
window.onTurnstileError = (code) => {
  console.error("[login.js] Turnstile error:", code);
  showError("Verification failed. Please complete the challenge, or disable extensions / try another browser.");
  return true; // allow retry
};
window.onTurnstileExpired = () => {
  // token cleared automatically by widget
};

const MESSAGES = {
  "auth/invalid-credential": "The email or password is incorrect.",
  "auth/wrong-password": "The email or password is incorrect.",
  "auth/user-not-found": "The email or password is incorrect.",
  "auth/invalid-email": "Enter a valid email address.",
  "auth/too-many-requests": "Too many attempts. Wait a few minutes and try again.",
  "auth/network-request-failed": "Network problem. Check your connection and try again.",
  "rate_limited": "Too many sign-in attempts. Please wait a few minutes.",
  "turnstile": "We could not confirm you are human. Please try again.",
};

function showError(message) {
  errorBox.textContent = message;
  errorBox.hidden = !message;
}

// While a sign-in is running the clicked button shows a spinner and "Signing in…" and everything
// else is disabled. The clicked button is marked aria-busy instead of disabled so it keeps its look.
let working = false;
function busy(state, button) {
  working = state;
  controls.forEach((control) => { control.disabled = state && control !== button; });
  if (!button) return;
  if (state) {
    button.dataset.label = button.textContent;
    button.textContent = button.dataset.busyLabel;
    button.setAttribute("aria-busy", "true");
  } else {
    button.textContent = button.dataset.label || button.textContent;
    button.removeAttribute("aria-busy");
  }
  status.textContent = state ? button.dataset.busyLabel : "";
}

async function finish(user) {
  const idToken = await user.getIdToken();
  const formData = new FormData(passwordForm);
  formData.append("id_token", idToken);

  const response = await fetch("/admin/session", {
    method: "POST",
    credentials: "same-origin",
    body: formData,
  });
  await signOut(auth);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body.detail;
    const msg = (typeof detail === "object" && detail.message) ? detail.message : (detail || "Sign-in failed. Try again.");
    const code = (typeof detail === "object" && detail.code) ? detail.code : "";
    const err = new Error(msg);
    err.code = code;
    throw err;
  }
  window.location.assign("/admin/dashboard");
}

async function run(signIn, button) {
  if (working) return;
  showError("");
  busy(true, button);
  try {
    const user = (await signIn()).user;
    await finish(user);
  } catch (error) {
    if (error.code === "auth/popup-closed-by-user" || error.code === "auth/cancelled-popup-request") {
      busy(false, button);
      return;
    }
    // reset Turnstile after any failed sign-in (tokens are single-use)
    if (window.turnstile && turnstileWidget) {
      try { window.turnstile.reset(turnstileWidget); } catch (e) {}
    }
    showError(MESSAGES[error.code] || (error.code ? "Sign-in failed: " + error.code : error.message));
    busy(false, button);
  }
}

const googleButton = document.getElementById("google-signin");
googleButton.addEventListener("click", () => {
  run(() => signInWithPopup(auth, new GoogleAuthProvider()), googleButton);
});

passwordForm.addEventListener("submit", (event) => {
  event.preventDefault();
  // Read token at submit time from the widget (not hidden input - callback may not fire)
  const token = (window.turnstile && turnstileWidget) ? window.turnstile.getResponse(turnstileWidget) : "";
  if (!token) {
    showError("Please complete the verification, or disable extensions / try another browser.");
    return;
  }
  const form = new FormData(event.currentTarget);
  form.set("cf-turnstile-response", token); // exact field name auth.py expects
  run(() => signInWithEmailAndPassword(auth, form.get("email"), form.get("password")),
    event.currentTarget.querySelector('[type="submit"]'));
});