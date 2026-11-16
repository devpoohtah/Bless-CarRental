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
