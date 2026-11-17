// Admin sign-in. Firebase proves who the person is; the server then decides if they may enter.
// Flow: Firebase sign-in -> ID token -> POST /admin/session (sets an httpOnly cookie) -> dashboard.
import { initializeApp } from "https://www.gstatic.com/firebasejs/11.0.2/firebase-app.js";
import {
  getAuth, GoogleAuthProvider, signInWithPopup, signInWithEmailAndPassword, signOut,
} from "https://www.gstatic.com/firebasejs/11.0.2/firebase-auth.js";

const auth = getAuth(initializeApp(JSON.parse(document.getElementById("firebase-config").textContent)));
const errorBox = document.getElementById("login-error");
const status = document.getElementById("login-status");
// Everything that can start a sign-in or change what is being signed in with.
const controls = document.querySelectorAll("#google-signin, #password-form button, #password-form input");

const MESSAGES = {
  "auth/invalid-credential": "The email or password is incorrect.",
  "auth/wrong-password": "The email or password is incorrect.",
  "auth/user-not-found": "The email or password is incorrect.",
  "auth/invalid-email": "Enter a valid email address.",
  "auth/too-many-requests": "Too many attempts. Wait a few minutes and try again.",
  "auth/network-request-failed": "Network problem. Check your connection and try again.",
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
  const response = await fetch("/admin/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ id_token: idToken }),
  });
  await signOut(auth); // the server cookie is the session; do not keep a second one in the browser
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "Sign-in failed. Try again.");
  }
  window.location.assign("/admin/dashboard");
}

async function run(signIn, button) {
  if (working) return;
  showError("");
  busy(true, button);
  try {
    await finish((await signIn()).user);
  } catch (error) {
    if (error.code === "auth/popup-closed-by-user" || error.code === "auth/cancelled-popup-request") {
      busy(false, button);
      return;
    }
    showError(MESSAGES[error.code] || (error.code ? "Sign-in failed. Try again." : error.message));
    busy(false, button);
  }
}

const googleButton = document.getElementById("google-signin");
googleButton.addEventListener("click", () => {
  run(() => signInWithPopup(auth, new GoogleAuthProvider()), googleButton);
});

document.getElementById("password-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  run(() => signInWithEmailAndPassword(auth, form.get("email"), form.get("password")),
    event.currentTarget.querySelector('[type="submit"]'));
});
