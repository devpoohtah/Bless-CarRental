// BLESS landing page behaviour: mobile menu, active nav link, hero slideshow, detail dialogs.
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

  // Hero slideshow: crossfade, autoplay, prev/next, dots, pause, swipe and arrow keys.
  const hero = document.querySelector("[data-hero]");
  const bar = hero?.querySelector("[data-hero-bar]");
  if (hero && bar) {
    const AUTOPLAY_MS = 6000;
    const slides = [...hero.querySelectorAll("[data-slide]")];
    const dots = [...hero.querySelectorAll("[data-hero-dot]")];
    const caption = hero.querySelector("[data-hero-caption]");
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    let index = 0;
    let timer = null;
    let userPaused = false;
    let hovering = false;
    let visible = true; // the hero is on screen
    let seq = 0; // the latest request wins when someone clicks quickly

    // Only the first image comes with the page; the rest get their src when they are about to be needed.
    const ready = (i) => {
      const img = slides[i].querySelector("img");
      if (img.dataset.src) { img.src = img.dataset.src; delete img.dataset.src; }
      if (img.complete) return Promise.resolve();
      return new Promise((resolve) => { img.addEventListener("load", resolve, { once: true }); img.addEventListener("error", resolve, { once: true }); });
    };

    const show = (i) => {
      index = (i + slides.length) % slides.length;
      slides.forEach((slide, n) => {
        slide.classList.toggle("is-active", n === index);
        if (n === index) slide.removeAttribute("aria-hidden"); else slide.setAttribute("aria-hidden", "true");
      });
      dots.forEach((dot, n) => (n === index ? dot.setAttribute("aria-current", "true") : dot.removeAttribute("aria-current")));
      const text = slides[index].dataset.caption || "";
      caption.textContent = text;
      caption.hidden = !text;
      ready((index + 1) % slides.length); // warm up the next one
    };

    const goTo = async (i) => {
      const mine = ++seq;
      await ready((i + slides.length) % slides.length);
      if (mine === seq) show(i);
    };

    const stop = () => { clearInterval(timer); timer = null; };
    const sync = () => {
      stop();
      const run = !userPaused && !hovering && visible && !document.hidden;
      if (run) timer = setInterval(() => goTo(index + 1), AUTOPLAY_MS);
      // While playing, do not announce each change; once paused, announce it politely.
    };
    const setPaused = (paused) => {
      userPaused = paused;
      toggleBtn.setAttribute("aria-label", paused ? "Play slideshow" : "Pause slideshow");
      toggleBtn.querySelector('[data-icon="pause"]').hidden = paused;
      toggleBtn.querySelector('[data-icon="play"]').hidden = !paused;
      sync();
    };
    // Any manual move restarts the timer so the next auto-advance is a full interval away.
    const move = (i) => { goTo(i); sync(); };


    dots.forEach((dot, n) => dot.addEventListener("click", () => move(n)));

    // Hovering or focusing the controls pauses the slideshow; leaving resumes it (unless paused with the button).
    bar.addEventListener("pointerenter", () => { hovering = true; sync(); });
    bar.addEventListener("pointerleave", () => { hovering = false; sync(); });
    bar.addEventListener("focusin", () => { hovering = true; sync(); });
    bar.addEventListener("focusout", () => { hovering = false; sync(); });

    hero.addEventListener("keydown", (e) => {
      if (e.key === "ArrowLeft") { move(index - 1); e.preventDefault(); }
      if (e.key === "ArrowRight") { move(index + 1); e.preventDefault(); }
    });

    // Swipe: a mostly horizontal drag of 50 px or more.
    let startX = 0;
    let startY = 0;
    hero.addEventListener("touchstart", (e) => { startX = e.touches[0].clientX; startY = e.touches[0].clientY; }, { passive: true });
    hero.addEventListener("touchend", (e) => {
      const dx = e.changedTouches[0].clientX - startX;
      const dy = e.changedTouches[0].clientY - startY;
      if (Math.abs(dx) >= 50 && Math.abs(dx) > Math.abs(dy) * 1.5) move(index + (dx < 0 ? 1 : -1));
    }, { passive: true });

    // Do not run while the tab is hidden or the hero is scrolled out of view.
    document.addEventListener("visibilitychange", sync);
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; sync(); }).observe(hero);
    }
    reduced.addEventListener("change", () => { userPaused = reduced.matches; sync(); });

    bar.hidden = false;
    sync();
    show(0);
  }

  // Car Rental carousel: previous/next buttons and a counter over a scroll-snap track. Off-screen slides are inert so Tab skips them.
  document.querySelectorAll("[data-vcar]").forEach((root) => {
    const track = root.querySelector("[data-vcar-track]");
    const controls = root.querySelector("[data-vcar-controls]");
    if (!track || !controls) return;
    const slides = [...track.querySelectorAll("[data-vslide]")];
    const infos = [...root.querySelectorAll("[data-vinfo]")];
    const count = controls.querySelector("[data-vcar-count]");
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    let index = 0;
    const update = () => {
      index = Math.min(slides.length - 1, Math.max(0, Math.round(track.scrollLeft / track.clientWidth)));
      count.textContent = `${index + 1} of ${slides.length}`;
      slides.forEach((slide, n) => slide.toggleAttribute("inert", n !== index));
      infos.forEach((info, n) => { info.hidden = n !== index; });
    };
    const goTo = (i) => track.scrollTo({ left: ((i + slides.length) % slides.length) * track.clientWidth, behavior: reduced.matches ? "auto" : "smooth" });
    controls.querySelector("[data-vcar-prev]").addEventListener("click", () => goTo(index - 1));
    controls.querySelector("[data-vcar-next]").addEventListener("click", () => goTo(index + 1));
    let frame = 0;
    track.addEventListener("scroll", () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(update); }, { passive: true });
    window.addEventListener("resize", () => track.scrollTo({ left: index * track.clientWidth, behavior: "auto" }));
    controls.hidden = false;
    root.dataset.ready = "";
    update();
  });

  // Detail dialogs (native <dialog>): open from buttons, close on backdrop click.
  document.querySelectorAll("[data-open-dialog]").forEach((btn) =>
    btn.addEventListener("click", () => document.getElementById(btn.dataset.openDialog)?.showModal())
  );
  document.querySelectorAll("dialog").forEach((dialog) =>
    // The booking form keeps its own dialog open on a stray click, so typed answers are not lost.
    dialog.addEventListener("click", (e) => { if (e.target === dialog && !dialog.hasAttribute("data-no-backdrop-close")) dialog.close(); })
  );
})();
