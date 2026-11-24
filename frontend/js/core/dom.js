export const $ = (selector) => document.querySelector(selector);

export function escapeHtml(value) {
  return String(value ?? "").replace(
    /[&<>'"]/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[
        char
      ],
  );
}

export function compact(value, fallback = "ไม่ระบุ") {
  return value ? escapeHtml(value) : fallback;
}

export function badge(value) {
  return `<span class="badge${value ? "" : " empty"}">${compact(value)}</span>`;
}

export function renderMetric(label, value) {
  return `<article class="metric">
    <span class="label">${label}</span>
    <span class="number">${value.toLocaleString()}</span>
  </article>`;
}

// Show a status line under a form or list; an empty message clears it.
export function showMessage(selector, message = "", isError = false) {
  const target = $(selector);
  target.textContent = message;
  target.classList.toggle("error", isError);
}

// Disable a button and show progress text while work runs; returns a function that undoes it.
export function setBusy(button, busyText) {
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = busyText;
  return () => {
    button.disabled = false;
    button.textContent = originalText;
  };
}
