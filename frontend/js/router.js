export function routeFromLocation() {
  const params = new URLSearchParams(window.location.hash.slice(1));
  const recordId = params.get("record");
  if (recordId && /^\d+$/.test(recordId)) return { view: "detail", recordId };
  const view = params.get("view");
  return ["dashboard", "catalog", "quality", "admin"].includes(view)
    ? { view }
    : { view: "explorer" };
}

export function pushRoute(view, recordId = null) {
  const hash = view === "detail"
    ? `#record=${recordId}`
    : view === "explorer" ? "" : `#view=${view}`;
  window.history.pushState({ view, recordId }, "", `${window.location.pathname}${hash}`);
}
