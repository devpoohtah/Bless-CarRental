// Opens and closes the sidebar on small screens. On wide screens it is always visible.
(() => {
  const button = document.querySelector("[data-admin-menu]");
  const sidebar = document.getElementById("admin-sidebar");
  const scrim = document.querySelector("[data-admin-scrim]");
  if (!button || !sidebar || !scrim) return;

  const setOpen = (open) => {
    sidebar.toggleAttribute("data-open", open);
    scrim.hidden = !open;
    button.setAttribute("aria-expanded", String(open));
    if (open) sidebar.querySelector("a")?.focus();
  };

  button.addEventListener("click", () => setOpen(!sidebar.hasAttribute("data-open")));
  scrim.addEventListener("click", () => setOpen(false));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && sidebar.hasAttribute("data-open")) {
      setOpen(false);
      button.focus();
    }
  });
  window.matchMedia("(min-width: 64em)").addEventListener("change", (e) => { if (e.matches) setOpen(false); });
})();
