// BLESS booking pages (/book/car and /book/tour). The page shows the chosen car or tour, a calendar that
// crosses out dates BLESS has already approved, and posts the request without leaving the page.
// The form is a row of steps (the fieldsets marked data-step), one on screen at a time, and the 6-digit email code
// is the last one: nothing is saved until the customer confirms their email. Without this script every step shows at once.
// The date inputs hold the real values. The calendar only fills them, so typing a date also works,
// and the form still works if the calendar script cannot load.
(() => {
  "use strict";

  const form = document.getElementById("booking-form");
  // /book/verify and /book/resend are sent from script, so they carry the CSRF token in a header
  // (the forms themselves carry it as a hidden field).
  const csrfHeaders = { "X-CSRF-Token": form.elements.csrf_token?.value || "" };
  if (!form) return;

  const formView = document.getElementById("booking-view-form");
  const codeView = document.getElementById("booking-view-code");
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

  // Returns the selected option, or null if the empty placeholder is selected
  const chosen = () => {
    const opt = item.selectedOptions[0];
    return opt && opt.value ? opt : null;
  };
  const ranges = () => {
    const ch = chosen();
    return ch ? blocked[ch.dataset.name] || [] : [];
  };
  // ISO dates compare correctly as plain strings.
  const taken = (from, to) => ranges().some(([a, b]) => a <= to && from <= b);

  // The summary beside the form follows the chosen option.
  function showItem() {
    const ch = chosen();
    if (!ch) {
      // Clear summary when no car/tour selected
      document.querySelectorAll("[data-bind]").forEach((el) => { el.textContent = ""; });
      document.querySelectorAll("[data-bind-src]").forEach((el) => { el.src = ""; el.alt = ""; });
      document.querySelectorAll("[data-show-if]").forEach((el) => { el.hidden = true; });
      people.max = "60";
      return;
    }
    const data = ch.dataset;
    document.querySelectorAll("[data-bind]").forEach((el) => { el.textContent = data[el.dataset.bind] ?? ""; });
    document.querySelectorAll("[data-bind-src]").forEach((el) => {
      el.src = data[el.dataset.bindSrc] || "";
      el.alt = data[`${el.dataset.bindSrc}Alt`] || "";
    });
    document.querySelectorAll("[data-show-if]").forEach((el) => { el.hidden = !data[el.dataset.showIf]; });
    people.max = data.max || "60";
  }

  // Problems open as a SweetAlert2 dialog. If it did not load, the inline boxes in the page show them instead,
  // so a problem is never silent. Customer-typed text is only ever set as text, never as HTML.
  const dialogButtons = { buttonsStyling: false, customClass: { confirmButton: "btn btn--primary" }, confirmButtonText: "OK" };

  const hideErrors = () => { errorBox.hidden = true; };
  function showErrors(messages) {
    const items = messages.map((text) => Object.assign(document.createElement("li"), { textContent: text }));
    if (window.Swal) {
      const list = Object.assign(document.createElement("ul"), { className: "swal-list" });
      list.append(...items);
      Swal.fire({ icon: "error", title: "Please fix the following", html: list, ...dialogButtons });
      return;
    }
    errorBox.querySelector("ul").replaceChildren(...items);
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
    form.dispatchEvent(new Event("quote-input"));
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
    form.dispatchEvent(new Event("quote-input"));
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

  // ---- steps ----
  const steps = [...form.querySelectorAll("fieldset[data-step]")];
  const multi = steps.length > 1;
  let finalOnly = form.querySelectorAll("[data-final-only]");
  const nav = form.querySelector("[data-step-nav]");
  const backButton = nav.querySelector("[data-step-back]");
  const nextButton = nav.querySelector("[data-step-next]");
  const steppers = document.querySelectorAll("[data-stepper]");
  const CODE_TITLE = "Confirm your email";
  let step = 0;

  // Turnstile is drawn fresh when the last step opens. A widget drawn inside a hidden step may never make its
  // token, and the server refuses a booking without one. The Send button stays off until the token arrives.
  // The api script loads on its own schedule, so wait for it.
  let challengeBox = form.querySelector(".cf-turnstile");
  let challengeId = null;
  let challengeWaiting = false;
  function drawChallenge(tries = 0) {
    if (!challengeBox || challengeId !== null) return;
    if (window.turnstile) {
      // Throw away whatever the api script drew while the box was hidden, and draw into a fresh one.
      const fresh = challengeBox.cloneNode(false);
      fresh.classList.remove("cf-turnstile"); // so the api script does not draw it a second time
      challengeBox.replaceWith(fresh);
      challengeBox = fresh;
      finalOnly = form.querySelectorAll("[data-final-only]");
      submit.disabled = true;
      challengeId = window.turnstile.render(fresh, {
        sitekey: fresh.dataset.sitekey, theme: fresh.dataset.theme,
        callback: () => { submit.disabled = false; },
        "expired-callback": () => { submit.disabled = true; },
        "error-callback": () => { submit.disabled = false; }, // let the server say what is wrong
      });
      challengeWaiting = false;
    } else if (tries < 50) {
      challengeWaiting = true;
      setTimeout(() => drawChallenge(tries + 1), 200);
    }
  }

  function paintProgress(index, title) { // index counts from 0; the email code is the step after the last fieldset
    steppers.forEach((el) => {
      el.hidden = false;
      el.querySelector(".stepper__count").textContent = `Step ${index + 1} of ${steps.length + 1}`;
      el.querySelector(".stepper__title").textContent = title;
      const bar = el.querySelector(".stepper__bar");
      bar.max = steps.length + 1;
      bar.value = index + 1;
    });
  }

  function showStep(index, { focus = true } = {}) {
    step = Math.max(0, Math.min(index, steps.length - 1));
    const last = step === steps.length - 1;
    steps.forEach((el, i) => { el.hidden = i !== step; });
    finalOnly.forEach((el) => { el.hidden = !last; });
    backButton.hidden = step === 0;
    nextButton.hidden = last;
    paintProgress(step, steps[step].querySelector("legend").textContent.trim());
    picker?.redraw(); // the calendar was set up while its step was hidden
    if (last && !challengeWaiting) drawChallenge();
    if (focus) {
      steppers[0].scrollIntoView({ block: "start" });
      steps[step].focus({ preventScroll: true }); // a screen reader announces the step's legend
    }
  }

  const fieldsOf = (el) => [...el.querySelectorAll("input, select, textarea")];
  const firstProblem = (index) => fieldsOf(steps[index]).find((field) => !field.checkValidity()) || null;

  function goNext() {
    const bad = firstProblem(step);
    if (bad) { bad.reportValidity(); return; }
    hideErrors();
    showStep(step + 1);
  }

  if (multi) {
    // The browser would check every field, hidden steps included, and block Enter and the Send button with
    // "An invalid form control is not focusable". Each step is checked above instead, and all of them again on send.
    form.noValidate = true;
    steps.forEach((el) => { el.tabIndex = -1; });
    nav.hidden = false;
    nextButton.addEventListener("click", goNext);
    backButton.addEventListener("click", () => { hideErrors(); showStep(step - 1); });
  }

  // ---- phone: fixed +63 prefix, digits grouped as 917 123 4567 ----
  const phone = document.getElementById("bk-phone");
  function formatPhone(raw) {
    let digits = raw.replace(/\D/g, "");
    // A pasted or autofilled "0917..." or "+63917..." keeps only the 10 digits after 0 / 63.
    if (digits.startsWith("63") && digits.length > 10) digits = digits.slice(2);
    else if (digits.startsWith("0")) digits = digits.slice(1);
    digits = digits.slice(0, 10);
    return [digits.slice(0, 3), digits.slice(3, 6), digits.slice(6)].filter(Boolean).join(" ");
  }
  phone.addEventListener("input", () => {
    const formatted = formatPhone(phone.value);
    if (formatted !== phone.value) phone.value = formatted;
  });

  // ---- license photo: car page only, always required (self-drive only) ----
  const licenseBox = form.querySelector("[data-license]");
  const licenseFrontInput = document.getElementById("bk-license-front");
  const licenseBackInput = document.getElementById("bk-license-back");
  const LICENSE_TYPES = ["image/jpeg", "image/png", "image/webp"];
  const LICENSE_MAX_BYTES = 5 * 1024 * 1024;

  function checkLicense(input) {
    const file = input.files[0];
    let problem = "";
    if (file && !LICENSE_TYPES.includes(file.type)) problem = "The license must be a JPEG, PNG or WebP photo.";
    else if (file && file.size > LICENSE_MAX_BYTES) problem = "The photo is larger than 5 MB. Use a smaller file.";
    input.setCustomValidity(problem);
    if (problem) input.reportValidity();
  }

  if (licenseFrontInput) licenseFrontInput.addEventListener("change", () => checkLicense(licenseFrontInput));
  if (licenseBackInput) licenseBackInput.addEventListener("change", () => checkLicense(licenseBackInput));

  // ---- estimated total: car page only. The server does the sum; this only asks and shows the answer ----
  const quotePanels = form.querySelectorAll("[data-quote]");
  const startTime = document.getElementById("bk-start-time");
  const endTime = document.getElementById("bk-end-time");
  let quoteTimer = null;
  let quoteRequest = null;

  function showQuote(result) {
    quotePanels.forEach((panel) => {
      panel.replaceChildren();
      if (!result || !result.ok) { panel.hidden = true; return; }
      const total = document.createElement("p");
      total.className = "quote__total";
      const amount = document.createElement("strong");
      amount.textContent = result.total;
      total.append("Estimated total: ", amount);
      const lines = document.createElement("ul");
      lines.className = "quote__lines";
      for (const line of result.lines) {
        const row = document.createElement("li");
        const label = document.createElement("span");
        label.textContent = line.label;
        const price = document.createElement("span");
        price.textContent = line.amount;
        row.append(label, price);
        lines.append(row);
      }
      const note = document.createElement("p");
      note.className = "quote__note";
      note.textContent = "This is an estimate from your pick-up and return times. We confirm the final price when we approve your request. Returning late is charged extra per hour.";
      panel.append(total, lines, note);
      panel.hidden = false;
    });
  }

  async function updateQuote() {
    if (!item.value || !start.value || !end.value || !startTime.value || !endTime.value) { showQuote(null); return; }
    quoteRequest?.abort();
    quoteRequest = new AbortController();
    const query = new URLSearchParams({ car: item.value, start_date: start.value, start_time: startTime.value,
                                        end_date: end.value, end_time: endTime.value });
    try {
      const response = await fetch(`/book/car/quote?${query}`, { headers: { Accept: "application/json" }, signal: quoteRequest.signal });
      showQuote(response.ok ? await response.json() : null);
    } catch (error) {
      if (error.name !== "AbortError") showQuote(null);
    }
  }

  function scheduleQuote() { clearTimeout(quoteTimer); quoteTimer = setTimeout(updateQuote, 250); }

  if (quotePanels.length && startTime && endTime) {
    for (const field of [item, start, end, startTime, endTime]) {
      field.addEventListener("change", scheduleQuote);
      field.addEventListener("input", scheduleQuote);
    }
    form.addEventListener("quote-input", scheduleQuote); // the calendar sets the dates without a change event
    scheduleQuote();
  }

  // ---- submit ----
  function setBusy(button, busy) {
    if (busy) {
      button.dataset.label = button.textContent;
      button.textContent = button.dataset.busyLabel;
      button.setAttribute("aria-busy", "true");
    } else {
      button.textContent = button.dataset.label || button.textContent;
      button.removeAttribute("aria-busy");
    }
  }

  // A Turnstile token works once: ask for a new one, and keep the button off until it arrives.
  const resetChallenge = () => { if (challengeId !== null) { submit.disabled = true; window.turnstile?.reset(challengeId); } };

  function showDone(data, reference) {
    stopCountdown();
    doneView.querySelector("[data-done-name]").textContent = data.get("customer_name");
    doneView.querySelector("[data-done-phone]").textContent = "+63 " + data.get("customer_phone");
    doneView.querySelector("[data-done-ref]").textContent = reference;
    doneView.querySelector("[data-done-ref-row]").hidden = !reference;
    formView.hidden = codeView.hidden = true;
    doneView.hidden = false;
    doneView.focus();
  }

  // ---- code view ----
  const codeForm = document.getElementById("code-form");
  const codeInput = document.getElementById("bk-code");
  const codeError = document.getElementById("code-errors");
  const codeSubmit = codeForm.querySelector('[type="submit"]');
  const resendButton = codeView.querySelector("[data-code-resend]");
  const OFFLINE = "Could not reach the server. Check your connection and try again.";
  let challenge = "";
  let countdown = null;
  let sentData = null;

  function showCodeError(text) {
    if (window.Swal) {
      // Back to the code box once the dialog is closed, so the customer can type again right away.
      Swal.fire({ icon: "error", title: "Could not confirm", text, ...dialogButtons, didClose: () => codeInput.focus() });
      return;
    }
    codeError.querySelector("p").textContent = text;
    codeError.hidden = false;
  }
  const hideCodeError = () => { codeError.hidden = true; };

  function stopCountdown() { clearInterval(countdown); countdown = null; }

  function startCountdown(seconds) {
    stopCountdown();
    let left = seconds;
    const paint = () => {
      resendButton.disabled = left > 0;
      resendButton.textContent = left > 0 ? `Send a new code (${left}s)` : "Send a new code";
    };
    paint();
    if (left <= 0) return;
    countdown = setInterval(() => { left -= 1; paint(); if (left <= 0) stopCountdown(); }, 1000);
  }

  function showTestCode(code) {
    const note = codeView.querySelector("[data-code-test]");
    note.hidden = !code;
    codeView.querySelector("[data-code-test-value]").textContent = code || "";
  }

  function showCodeView(body) {
    challenge = body.challenge;
    codeView.querySelector("[data-code-email]").textContent = body.email;
    showTestCode(body.test_code);
    codeInput.value = "";
    hideCodeError();
    startCountdown(body.resend_in ?? 60);
    if (multi) paintProgress(steps.length, CODE_TITLE);
    formView.hidden = true;
    codeView.hidden = false;
    codeInput.focus();
  }

  // Back to the form with everything the customer typed kept. messages (if any) explain why.
  function backToForm(messages) {
    stopCountdown();
    challenge = "";
    codeView.hidden = true;
    formView.hidden = false;
    resetChallenge();
    if (multi) showStep(step, { focus: false }); // repaint the progress; the customer lands on the last step
    if (messages) showErrors(messages); else hideErrors();
  }

  codeInput.addEventListener("input", () => { codeInput.value = codeInput.value.replace(/\D/g, "").slice(0, 6); });
  codeView.querySelector("[data-code-back]").addEventListener("click", () => backToForm());

  let verifying = false;
  codeForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (verifying) return;
    if (!/^\d{6}$/.test(codeInput.value)) { showCodeError("Enter the 6-digit code from your email."); codeInput.focus(); return; }
    verifying = true;
    hideCodeError();
    setBusy(codeSubmit, true);
    try {
      const response = await fetch("/book/verify", { method: "POST", headers: { Accept: "application/json", ...csrfHeaders },
        body: new URLSearchParams({ challenge, code: codeInput.value }) });
      const body = await response.json().catch(() => ({}));
      const message = (Array.isArray(body.errors) && body.errors[0]) || FALLBACK;
      if (response.ok) showDone(sentData, body.reference || "");
      else if (body.code === "wrong_code") { showCodeError(message); codeInput.select(); }
      else backToForm([message]); // expired, locked, or the dates were taken meanwhile: start again
    } catch (error) {
      showCodeError(OFFLINE); // the code is still valid: the customer can press the button again
    } finally {
      verifying = false;
      setBusy(codeSubmit, false);
    }
  });

  let resending = false;
  resendButton.addEventListener("click", async () => {
    if (resending || resendButton.disabled) return;
    resending = true;
    hideCodeError();
    resendButton.disabled = true;
    try {
      const response = await fetch("/book/resend", { method: "POST", headers: { Accept: "application/json", ...csrfHeaders },
        body: new URLSearchParams({ challenge }) });
      const body = await response.json().catch(() => ({}));
      if (response.ok) { showTestCode(body.test_code); codeInput.value = ""; startCountdown(body.resend_in ?? 60); codeInput.focus(); }
      else if (body.code === "cooldown") { showCodeError(body.errors?.[0] || FALLBACK); startCountdown(body.retry_after ?? 60); }
      else if (body.code === "expired") backToForm([body.errors?.[0] || FALLBACK]);
      else { showCodeError(body.errors?.[0] || FALLBACK); startCountdown(0); }
    } catch (error) {
      showCodeError(OFFLINE);
      startCountdown(0);
    } finally {
      resending = false;
    }
  });

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
    // Enter inside a field on an earlier step moves on instead of sending.
    if (multi && step < steps.length - 1) { goNext(); return; }
    if (sending) return;
    if (multi) {
      // Take the customer to the first step with a problem (they may have gone back and changed something).
      const index = steps.findIndex((_, i) => firstProblem(i));
      if (index !== -1) { showStep(index); firstProblem(index).reportValidity(); return; }
    }
    if (!form.reportValidity()) return; // the terms checkbox
    sending = true;
    hideErrors();
    setBusy(submit, true);
    const data = new FormData(form);
    try {
      const response = await fetch(form.action, { method: "POST", body: data, headers: { Accept: "application/json" } });
      const body = await response.json().catch(() => ({}));
      if (response.status === 202 && body.challenge) { sentData = data; showCodeView(body); }
      else if (response.ok) showDone(data, body.reference || ""); // the hidden trap field was filled: a bot sees "success"
      else { showErrors(Array.isArray(body.errors) && body.errors.length ? body.errors : [FALLBACK]); resetChallenge(); }
    } catch (error) {
      showErrors([FALLBACK]); // offline or the server could not be reached
      resetChallenge();
    } finally {
      sending = false;
      setBusy(submit, false);
    }
  });

  showItem();
  setUpCalendar();
  if (multi) showStep(0, { focus: false });
})();