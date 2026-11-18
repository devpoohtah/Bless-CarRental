// Sidebar behaviour. Small screens: a menu button opens the sidebar as a drawer.
// Wide screens: the sidebar is always visible and can be collapsed to an icon rail.
(() => {
  const root = document.documentElement;
  const sidebar = document.getElementById("admin-sidebar");
  if (!sidebar) return;

  // --- Drawer (small screens) ---
  const menuButton = document.querySelector("[data-admin-menu]");
  const scrim = document.querySelector("[data-admin-scrim]");
  const setOpen = (open) => {
    sidebar.toggleAttribute("data-open", open);
    if (scrim) scrim.hidden = !open;
    menuButton?.setAttribute("aria-expanded", String(open));
    if (open) sidebar.querySelector("a")?.focus();
  };
  menuButton?.addEventListener("click", () => setOpen(!sidebar.hasAttribute("data-open")));
  scrim?.addEventListener("click", () => setOpen(false));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && sidebar.hasAttribute("data-open")) {
      setOpen(false);
      menuButton?.focus();
    }
  });
  window.matchMedia("(min-width: 64em)").addEventListener("change", (e) => { if (e.matches) setOpen(false); });

  // --- Collapse (wide screens). The choice is remembered in this browser only. ---
  const collapseButton = sidebar.querySelector("[data-admin-collapse]");
  const label = sidebar.querySelector("[data-collapse-label]");
  const syncCollapse = () => {
    const collapsed = root.dataset.sidebar === "collapsed";
    collapseButton.setAttribute("aria-expanded", String(!collapsed));
    collapseButton.title = collapsed ? "Expand sidebar" : "Collapse sidebar";
    label.textContent = collapsed ? "Expand" : "Collapse";
  };
  collapseButton?.addEventListener("click", () => {
    const collapsed = root.dataset.sidebar !== "collapsed";
    if (collapsed) root.dataset.sidebar = "collapsed"; else delete root.dataset.sidebar;
    try { localStorage.setItem("admin-sidebar", collapsed ? "collapsed" : "expanded"); } catch (e) { /* storage unavailable */ }
    syncCollapse();
  });
  if (collapseButton) syncCollapse();
})();

// Buttons with data-confirm ask before they submit (delete, reject, cancel). The dialog is SweetAlert2;
// if it did not load, the browser's own dialog is used so the check is never skipped.
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-confirm]");
  if (!button || !button.form) return;
  event.preventDefault();
  const form = button.form;
  let confirmed;
  if (window.Swal) {
    const result = await Swal.fire({
      title: button.dataset.confirm,
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: (button.dataset.label || button.textContent).trim(),
      cancelButtonText: "Go back",
      reverseButtons: true,
      focusCancel: true,
      buttonsStyling: false,
      customClass: { confirmButton: "btn btn--primary", cancelButton: "btn btn--outline" },
    });
    confirmed = result.isConfirmed;
  } else {
    confirmed = window.confirm(button.dataset.confirm);
  }
  // requestSubmit keeps the clicked button as the submitter, so its name, value and formaction are sent.
  if (confirmed) form.requestSubmit(button);
});

// The "saved" notice rendered by the server becomes a toast. Without SweetAlert2 it stays on the page.
(() => {
  const notice = document.querySelector(".notice[role='status']");
  if (!notice || !window.Swal) return;
  const text = notice.textContent.trim();
  notice.hidden = true;
  Swal.fire({ toast: true, position: "top-end", icon: "success", title: text, showConfirmButton: false, timer: 4000, timerProgressBar: true });
})();

// Submit buttons show a busy state while a form posts, and a second click cannot post it twice.
// The button is marked aria-busy rather than disabled on purpose: a disabled button's name and
// value are not sent, and Approve / Reject / Cancel booking rely on theirs.
const resetBusyButtons = () => {
  document.querySelectorAll("form[data-submitting]").forEach((form) => delete form.dataset.submitting);
  document.querySelectorAll('button[aria-busy="true"]').forEach((button) => {
    button.removeAttribute("aria-busy");
    if (button.dataset.label) button.textContent = button.dataset.label;
  });
};
document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || form.method !== "post") return;
  if (form.dataset.submitting) { event.preventDefault(); return; }
  form.dataset.submitting = "true";
  const button = event.submitter || form.querySelector('[type="submit"]');
  if (!button) return;
  button.setAttribute("aria-busy", "true");
  if (button.dataset.busyLabel) {
    button.dataset.label = button.textContent;
    button.textContent = button.dataset.busyLabel;
  }
});

// When the next admin page is slow to arrive, replace the current one with a placeholder of that
// page instead of leaving it frozen. It appears after 300 ms, so quick page loads never flash it.
(() => {
  const main = document.getElementById("main");
  if (!main) return;
  const SHOW_AFTER_MS = 300;
  const GIVE_UP_MS = 20000; // the visitor pressed Stop, or the request hung: put the page back

  const kindFor = (path) => {
    if (path === "/admin/dashboard") return "dashboard";
    if (path === "/admin/calendar") return "calendar";
    if (/^\/admin\/(services\/(cars|tours)|bookings)\/?$/.test(path)) return "table";
    return "form"; // add, edit and detail pages
  };

  let saved = null;
  let showTimer;
  let giveUpTimer;
  const restore = () => {
    clearTimeout(showTimer);
    clearTimeout(giveUpTimer);
    if (saved !== null) main.innerHTML = saved;
    saved = null;
    main.removeAttribute("aria-busy");
  };
  const show = (template) => {
    saved = main.innerHTML;
    main.setAttribute("aria-busy", "true");
    main.replaceChildren(template.content.cloneNode(true));
    giveUpTimer = setTimeout(restore, GIVE_UP_MS);
  };

  document.addEventListener("click", (event) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest("a[href]");
    if (!link || link.target || link.hasAttribute("download") || link.origin !== location.origin) return;
    if (!link.pathname.startsWith("/admin/")) return;
    if (link.pathname === location.pathname && link.search === location.search) return;
    const template = document.getElementById(`skeleton-${kindFor(link.pathname)}`);
    if (!template) return;
    clearTimeout(showTimer);
    showTimer = setTimeout(() => { if (!event.defaultPrevented) show(template); }, SHOW_AFTER_MS);
  });

  // Back / forward can bring an old page back from the browser's memory: undo any busy state.
  window.addEventListener("pageshow", (event) => {
    if (!event.persisted) return;
    restore();
    resetBusyButtons();
  });
})();

// Badge on the Bookings link: how many bookings wait for a decision. The server counts them behind the
// admin sign-in, so no database access is opened to the browser. Polls while the tab is visible and
// shows the number in the tab title too, so a background tab still shows it.
(() => {
  const badge = document.querySelector("[data-pending-badge]");
  if (!badge) return;
  const INTERVAL_MS = 30000;
  const baseTitle = document.title;
  let timer = null;

  const show = (count) => {
    badge.textContent = count > 99 ? "99+" : String(count);
    badge.title = `${count} pending booking${count === 1 ? "" : "s"}`;
    badge.hidden = count < 1;
    document.title = count > 0 ? `(${count}) ${baseTitle}` : baseTitle;
  };
  const stop = () => { clearInterval(timer); timer = null; };

  async function refresh() {
    try {
      const response = await fetch("/admin/pending-count", { credentials: "same-origin", headers: { Accept: "application/json" } });
      if (response.redirected) return stop(); // signed out: the sign-in page came back instead of a number
      if (!response.ok) return; // keep the last number; try again next time
      const { pending } = await response.json();
      if (Number.isInteger(pending)) show(pending);
    } catch (error) { /* offline: keep the last number */ }
  }
  const start = () => { if (!timer) { refresh(); timer = setInterval(refresh, INTERVAL_MS); } };

  document.addEventListener("visibilitychange", () => { if (document.hidden) stop(); else start(); });
  if (!document.hidden) start();
})();

// Image fields: preview the chosen file before saving, check its type and size, and let "Remove image"
// show what will happen. The server checks the real file again; this only saves a round trip.
(() => {
  const MAX_BYTES = 5 * 1024 * 1024;
  const TYPES = ["image/jpeg", "image/png", "image/webp"];

  document.querySelectorAll("[data-image-field]").forEach((field) => {
    const input = field.querySelector("[data-image-input]");
    const preview = field.querySelector("[data-image-preview]");
    const note = field.querySelector("[data-image-note]");
    const remove = field.querySelector("[data-image-remove]");
    const original = preview.dataset.original || "";
    let objectUrl = null;

    const say = (text) => { note.textContent = text; note.hidden = !text; };
    const reset = () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      objectUrl = null;
      preview.classList.remove("is-removing");
      if (original) { preview.src = original; preview.hidden = false; } else { preview.removeAttribute("src"); preview.hidden = true; }
      say("");
    };

    input.addEventListener("change", () => {
      const file = input.files[0];
      reset();
      if (remove) remove.checked = false;
      if (!file) return;
      if (!TYPES.includes(file.type)) { input.value = ""; say("That file is not a JPEG, PNG or WebP image."); return; }
      if (file.size > MAX_BYTES) { input.value = ""; say("That image is larger than 5 MB. Choose a smaller file."); return; }
      objectUrl = URL.createObjectURL(file);
      preview.src = objectUrl;
      preview.hidden = false;
      say(original ? "New image shown above. It replaces the current one when you save." : "New image shown above. It is uploaded when you save.");
    });

    remove?.addEventListener("change", () => {
      if (remove.checked) {
        input.value = "";
        reset();
        preview.classList.add("is-removing");
        say("The image will be removed when you save, and the placeholder is shown instead.");
      } else {
        reset();
      }
    });
  });
})();
