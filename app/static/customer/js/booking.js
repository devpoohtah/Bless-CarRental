// BLESS booking dialog. One form serves cars and tour packages: the fields and labels follow the
// chosen item, and the request is posted to /bookings without leaving the page.
(() => {
  "use strict";

  const dialog = document.getElementById("booking-dialog");
  if (!dialog) return;

  const form = document.getElementById("booking-form");
  const formView = document.getElementById("booking-view-form");
  const doneView = document.getElementById("booking-view-done");
  const errorBox = document.getElementById("booking-errors");
  const item = document.getElementById("bk-item");
  const start = document.getElementById("bk-start");
  const end = document.getElementById("bk-end");
  const submit = form.querySelector('[type="submit"]');
  const today = form.dataset.today;

  const FALLBACK = "Something went wrong. Please try again, or message us on Messenger.";
  const typeOf = (value) => (value.startsWith("car:") ? "car" : value.startsWith("tour:") ? "tour" : "");

  // Show only the fields and wording that fit the chosen item. Hidden fields are also disabled,
  // so they are neither validated nor sent.
  function syncType() {
    const type = typeOf(item.value);
    dialog.querySelectorAll("[data-for]").forEach((field) => {
      const show = field.dataset.for === type;
      field.hidden = !show;
      field.querySelectorAll("input, select, textarea").forEach((control) => { control.disabled = !show; });
    });
    dialog.querySelectorAll("[data-label-car]").forEach((label) => {
      if (!label.dataset.label) label.dataset.label = label.textContent;
      label.textContent = (type && label.dataset[type === "car" ? "labelCar" : "labelTour"]) || label.dataset.label;
    });
    end.required = type === "car"; // a car needs a return date; a one-day tour does not
  }

  function syncDates() {
    start.min = end.min = today;
    if (start.value) end.min = start.value;
    if (end.value && start.value && end.value < start.value) end.value = "";
  }

  const hideErrors = () => { errorBox.hidden = true; };
  function showErrors(messages) {
    const list = errorBox.querySelector("ul");
    list.replaceChildren(...messages.map((text) => Object.assign(document.createElement("li"), { textContent: text })));
    errorBox.hidden = false;
    errorBox.focus();
  }

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

  function showForm() {
    doneView.hidden = true;
    formView.hidden = false;
    dialog.setAttribute("aria-labelledby", "booking-title");
  }

  function showDone(data, reference) {
    doneView.querySelector("[data-done-name]").textContent = data.get("customer_name");
    doneView.querySelector("[data-done-phone]").textContent = data.get("customer_phone");
    doneView.querySelector("[data-done-ref]").textContent = reference;
    doneView.querySelector("[data-done-ref-row]").hidden = !reference;
    formView.hidden = true;
    doneView.hidden = false;
    dialog.setAttribute("aria-labelledby", "booking-done-title");
    doneView.focus();
  }

  function open(value) {
    showForm();
    hideErrors();
    if (value && [...item.options].some((option) => option.value === value)) item.value = value;
    syncType();
    syncDates();
    dialog.showModal();
  }

  // Any [data-book] button opens the form. If it sits inside a details dialog, close that first.
  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-book]");
    if (!trigger) return;
    trigger.closest("dialog")?.close();
    open(trigger.dataset.book);
  });

  item.addEventListener("change", syncType);
  start.addEventListener("change", syncDates);

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

  // After a finished request, closing the dialog gives the next visitor a clean form.
  dialog.addEventListener("close", () => {
    if (doneView.hidden) return;
    form.reset();
    showForm();
    syncType();
  });
})();
