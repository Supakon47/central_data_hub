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
