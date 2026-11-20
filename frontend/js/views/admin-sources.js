import { adminFetch } from "../api.js";
import { compact, escapeHtml } from "../core/dom.js";

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

export function renderGoogleSourceCard(source, syncState, { renderBridge, renderSchedule }) {
  const tabs = source.sheets
    .map((sheet) => `${escapeHtml(sheet.name)} <span class="muted">(${escapeHtml(sheet.read_range)})</span>`)
    .join(" · ") || "ยังไม่มีแท็บ";
  const bridge = source.image_bridge || { configured: false };
  const preview = syncState.canManual
    ? `<button type="button" data-source-preview="${source.id}">ตรวจสอบก่อน Sync</button>`
    : `<span class="muted">ตั้งค่า key ใน container ก่อนจึงตรวจสอบได้</span>`;
  return `<article class="catalog-item">
    <h3>${escapeHtml(source.name)}</h3>
    <p class="muted">${compact(source.description, "ไม่มีคำอธิบาย")}</p>
    <div class="catalog-meta"><span>ผู้รับผิดชอบ: ${compact(source.owner_name)}</span><span>แท็บ: ${tabs}</span></div>
    <div class="catalog-actions"><button type="button" class="secondary" data-source-fill="${source.id}">เพิ่มแท็บในไฟล์นี้</button>${preview}</div>
    ${renderSchedule(source, syncState)}
    ${renderBridge(source, bridge, syncState.canManual)}
  </article>`;
}

export function fillGoogleSourceForm(source) {
  const form = document.querySelector("#admin-google-source-form");
  form.elements.source_name.value = source.name || "";
  form.elements.spreadsheet_id.value = source.spreadsheet_id || "";
  form.elements.owner_name.value = source.owner_name || "";
  form.elements.description.value = source.description || "";
  form.elements.sheet_name.value = "";
  form.elements.read_range.value = "A:ZZ";
  document.querySelector("#admin-google-sources-panel").open = true;
  form.elements.sheet_name.focus();
}
