// Admin sign-in. Firebase proves who the person is; the server then decides if they may enter.
// Flow: Firebase sign-in -> ID token -> POST /admin/session (sets an httpOnly cookie) -> dashboard.
import { initializeApp } from "https://www.gstatic.com/firebasejs/11.0.2/firebase-app.js";
import {
  getAuth, GoogleAuthProvider, signInWithPopup, signInWithEmailAndPassword, signOut,
} from "https://www.gstatic.com/firebasejs/11.0.2/firebase-auth.js";

const auth = getAuth(initializeApp(JSON.parse(document.getElementById("firebase-config").textContent)));
const errorBox = document.getElementById("login-error");
const buttons = document.querySelectorAll("#google-signin, #password-form button");

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

function busy(state) {
  buttons.forEach((button) => { button.disabled = state; });
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

async function run(signIn) {
  showError("");
  busy(true);
  try {
    await finish((await signIn()).user);
  } catch (error) {
    if (error.code === "auth/popup-closed-by-user" || error.code === "auth/cancelled-popup-request") {
      busy(false);
      return;
    }
    showError(MESSAGES[error.code] || (error.code ? "Sign-in failed. Try again." : error.message));
    busy(false);
  }
}

document.getElementById("google-signin").addEventListener("click", () => {
  run(() => signInWithPopup(auth, new GoogleAuthProvider()));
});

document.getElementById("password-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  run(() => signInWithEmailAndPassword(auth, form.get("email"), form.get("password")));
});
