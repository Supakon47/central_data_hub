import { adminFetch } from "../api.js";

export async function fetchGoogleSourceState() {
  const [sourceData, healthData] = await Promise.all([
    adminFetch("/api/admin/google-sheets"),
    fetch("/api/health").then((response) => response.json()),
  ]);
  return {
    sources: sourceData.sources,
    syncState: {
      canManual: healthData.google_sheets_web_sync_available,
      automaticReady: healthData.google_sheets_auto_sync_available,
    },
  };
}

export function renderGoogleSourceList(sources, renderSource) {
  if (!sources.length) return `<p class="muted">ยังไม่มี Google Sheets ที่ลงทะเบียน</p>`;
  return sources.map((source) => renderSource(source)).join("");
}
