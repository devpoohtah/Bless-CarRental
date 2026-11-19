// Live "pending bookings" badge using Firestore onSnapshot.
// Requires an authenticated Firebase user (see login.js signOut behavior).
import { initializeApp } from "https://www.gstatic.com/firebasejs/11.0.2/firebase-app.js";
import { getAuth, onAuthStateChanged } from "https://www.gstatic.com/firebasejs/11.0.2/firebase-auth.js";
import { getFirestore, collection, query, where, onSnapshot } from "https://www.gstatic.com/firebasejs/11.0.2/firebase-firestore.js";

const badge = document.querySelector("[data-pending-badge]");
if (!badge) {
  // No badge element on this page (e.g., login page)
} else {
  // Firebase config is embedded in the page by the server (same as login.js uses).
  const configEl = document.getElementById("firebase-config");
  if (!configEl) {
    console.warn("[pending-badge] Firebase config not found on page; badge will not update.");
  } else {
    const firebaseConfig = JSON.parse(configEl.textContent);
    const app = initializeApp(firebaseConfig);
    const auth = getAuth(app);
    const db = getFirestore(app);

    let unsubscribe = null;

    function attachListener(user) {
      if (unsubscribe) {
        unsubscribe();
        unsubscribe = null;
      }
      if (!user) {
        badge.hidden = true;
        return;
      }
      // Query for pending bookings. Status value must match what the server writes ("pending").
      const q = query(collection(db, "bookings"), where("status", "==", "pending"));
      unsubscribe = onSnapshot(q, (snapshot) => {
        const count = snapshot.size;
        badge.textContent = count > 99 ? "99+" : String(count);
        badge.title = `${count} pending booking${count === 1 ? "" : "s"}`;
        badge.hidden = count < 1;
        // Also update the tab title like the old polling badge did
        const baseTitle = document.title.replace(/^\(\d+\)\s*/, "");
        document.title = count > 0 ? `(${count}) ${baseTitle}` : baseTitle;
      }, (error) => {
        if (error.code === "permission-denied") {
          console.warn("[pending-badge] Permission denied reading bookings; hiding badge.");
          badge.hidden = true;
        } else {
          console.error("[pending-badge] Firestore listener error:", error);
        }
        if (unsubscribe) {
          unsubscribe();
          unsubscribe = null;
        }
      });
    }

    // Attach listener when auth state is known (user signed in)
    onAuthStateChanged(auth, (user) => {
      attachListener(user);
    });

    // Clean up on page hide (user navigates away)
    window.addEventListener("pagehide", () => {
      if (unsubscribe) {
        unsubscribe();
        unsubscribe = null;
      }
    });
  }
}