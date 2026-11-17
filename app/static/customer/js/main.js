// BLESS landing page behaviour: mobile menu, active nav link, detail dialogs.
(() => {
  "use strict";

  const toggle = document.getElementById("menu-toggle");
  const menu = document.getElementById("mobile-menu");

  // Mobile menu.
  const setMenu = (open) => {
    menu.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    toggle.querySelector('[data-icon="open"]').hidden = open;
    toggle.querySelector('[data-icon="close"]').hidden = !open;
  };
  toggle.addEventListener("click", () => setMenu(menu.hidden));
  menu.addEventListener("click", (e) => { if (e.target.closest("a, [data-book]")) setMenu(false); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !menu.hidden) { setMenu(false); toggle.focus(); }
  });
  window.matchMedia("(min-width: 80em)").addEventListener("change", (e) => { if (e.matches) setMenu(false); });

  // Highlight the nav link for the section currently in view.
  const links = document.querySelectorAll("[data-section]");
  const sections = [...new Set([...links].map((a) => a.dataset.section))]
    .map((id) => document.getElementById(id))
    .filter(Boolean);
  const setActive = (id) =>
    links.forEach((a) => (a.dataset.section === id ? a.setAttribute("aria-current", "true") : a.removeAttribute("aria-current")));
  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(
      (entries) => entries.forEach((entry) => entry.isIntersecting && setActive(entry.target.id)),
      { rootMargin: "-40% 0px -55% 0px" }
    );
    sections.forEach((s) => observer.observe(s));
  }

  // Detail dialogs (native <dialog>): open from buttons, close on backdrop click.
  document.querySelectorAll("[data-open-dialog]").forEach((btn) =>
    btn.addEventListener("click", () => document.getElementById(btn.dataset.openDialog)?.showModal())
  );
  document.querySelectorAll("dialog").forEach((dialog) =>
    // The booking form keeps its own dialog open on a stray click, so typed answers are not lost.
    dialog.addEventListener("click", (e) => { if (e.target === dialog && !dialog.hasAttribute("data-no-backdrop-close")) dialog.close(); })
  );
})();
