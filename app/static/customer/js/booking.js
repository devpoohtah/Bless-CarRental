// BLESS booking pages (/book/car and /book/tour). The page shows the chosen car or tour, a calendar that
// crosses out dates BLESS has already approved, and posts the request without leaving the page.
// The date inputs hold the real values. The calendar only fills them, so typing a date also works,
// and the form still works if the calendar script cannot load.
(() => {
  "use strict";

  const form = document.getElementById("booking-form");
  if (!form) return;

  const formView = document.getElementById("booking-view-form");
  const doneView = document.getElementById("booking-view-done");
  const errorBox = document.getElementById("booking-errors");
  const item = document.getElementById("bk-item");
  const start = document.getElementById("bk-start");
  const end = document.getElementById("bk-end");
  const people = document.getElementById("bk-people");
  const calendarBox = document.getElementById("bk-calendar");
  const submit = form.querySelector('[type="submit"]');
  const today = form.dataset.today;
  const blocked = JSON.parse(document.getElementById("blocked-dates")?.textContent || "{}");

  const FALLBACK = "Something went wrong. Please try again, or message us on Messenger.";
  const TAKEN = "That item is already booked on some of those dates. Choose dates without a crossed-out day.";
  let picker = null;

  const chosen = () => item.selectedOptions[0];
  const ranges = () => blocked[chosen().dataset.name] || [];
  // ISO dates compare correctly as plain strings.
  const taken = (from, to) => ranges().some(([a, b]) => a <= to && from <= b);

  // The summary beside the form follows the chosen option.
  function showItem() {
    const data = chosen().dataset;
    document.querySelectorAll("[data-bind]").forEach((el) => { el.textContent = data[el.dataset.bind] ?? ""; });
    document.querySelectorAll("[data-bind-src]").forEach((el) => {
      el.src = data[el.dataset.bindSrc] || "";
      el.alt = data[`${el.dataset.bindSrc}Alt`] || "";
    });
    document.querySelectorAll("[data-show-if]").forEach((el) => { el.hidden = !data[el.dataset.showIf]; });
    people.max = data.max || "60";
  }

  const hideErrors = () => { errorBox.hidden = true; };
  function showErrors(messages) {
    errorBox.querySelector("ul").replaceChildren(
      ...messages.map((text) => Object.assign(document.createElement("li"), { textContent: text }))
    );
    errorBox.hidden = false;
    errorBox.focus();
  }

  // ---- dates ----
  function disabledRanges() { return ranges().map(([from, to]) => ({ from, to })); }

  function syncDates() {
    end.min = start.value || today;
    if (end.value && start.value && end.value < start.value) end.value = "";
    if (start.value && taken(start.value, end.value || start.value)) {
      start.value = end.value = "";
      showErrors([TAKEN]);
    }
    picker?.setDate([start.value, end.value].filter(Boolean), false);
  }

  function onPick(dates) {
    if (!dates.length) { start.value = end.value = ""; return; }
    const first = picker.formatDate(dates[0], "Y-m-d");
    const last = dates[1] ? picker.formatDate(dates[1], "Y-m-d") : "";
    if (taken(first, last || first)) {
      picker.clear();
      start.value = end.value = "";
      showErrors([TAKEN]);
      return;
    }
    hideErrors();
    start.value = first;
    end.value = last; // blank until the second click: a one-day tour needs no end date
    end.min = first;
  }

  function setUpCalendar() {
    if (!calendarBox) return;
    if (!window.flatpickr) { calendarBox.closest(".book__calendar").hidden = true; return; }
    picker = window.flatpickr(calendarBox, {
      inline: true, mode: "range", dateFormat: "Y-m-d", minDate: today,
      maxDate: new Date(Date.now() + 730 * 864e5), disable: disabledRanges(), onChange: onPick,
      // Booked days get their own mark, so past days (also unavailable) are not mistaken for booked ones.
      onDayCreate: (_dates, _str, fp, day) => {
        const iso = fp.formatDate(day.dateObj, "Y-m-d");
        if (ranges().some(([from, to]) => from <= iso && iso <= to)) day.classList.add("is-booked");
      },
    });
    // The calendar itself refuses an end date that would cover booked days, but says nothing. Say why.
    // (Flatpickr stops the click from bubbling, so listen while it travels down, then look once it has been handled.)
    picker.calendarContainer.addEventListener("click", (event) => {
      const day = event.target.closest(".flatpickr-day:not(.flatpickr-disabled)");
      const pickedBefore = picker.selectedDates.length;
      setTimeout(() => {
        if (day && pickedBefore === 1 && picker.selectedDates.length === 1 && day.dateObj > picker.selectedDates[0]) {
          showErrors([TAKEN]);
        }
      }, 0);
    }, true);
  }

  // ---- submit ----
  function setBusy(busy) {
    if (busy) {
      submit.dataset.label = submit.textContent;
      submit.textContent = submit.dataset.busyLabel;
      submit.setAttribute("aria-busy", "true");
    } else {
      submit.textContent = submit.dataset.label || submit.textContent;
      submit.removeAttribute("aria-busy");
    }
  }

  function showDone(data, reference) {
    doneView.querySelector("[data-done-name]").textContent = data.get("customer_name");
    doneView.querySelector("[data-done-phone]").textContent = data.get("customer_phone");
    doneView.querySelector("[data-done-ref]").textContent = reference;
    doneView.querySelector("[data-done-ref-row]").hidden = !reference;
    formView.hidden = true;
    doneView.hidden = false;
    doneView.focus();
  }

  item.addEventListener("change", () => {
    showItem();
    picker?.set("disable", disabledRanges());
    syncDates();
  });
  start.addEventListener("change", syncDates);
  end.addEventListener("change", syncDates);

  let sending = false;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (sending || !form.reportValidity()) return;
    sending = true;
    hideErrors();
    setBusy(true);
    const data = new FormData(form);
    try {
      const response = await fetch(form.action, { method: "POST", body: data, headers: { Accept: "application/json" } });
      const body = await response.json().catch(() => ({}));
      if (response.ok) showDone(data, body.reference || "");
      else showErrors(Array.isArray(body.errors) && body.errors.length ? body.errors : [FALLBACK]);
    } catch (error) {
      showErrors([FALLBACK]); // offline or the server could not be reached
    } finally {
      sending = false;
      setBusy(false);
    }
  });

  showItem();
  setUpCalendar();
})();
