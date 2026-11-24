// Admin page: register Google Sheets tabs, preview them, and set their sync schedule.
import { adminFetch, getJson } from "../api.js";
import { $, compact, escapeHtml, setBusy, showMessage } from "../core/dom.js";
import { renderImageBridgeControls } from "./admin-image-bridge.js";
import { renderSyncScheduleControls, syncScheduleLabel } from "./admin-sync-schedule.js";

const LIST = "#admin-google-sources-list";
const FORM_FIELDS = ["source_name", "spreadsheet_id", "sheet_name", "read_range", "owner_name", "description"];

const message = (text, isError) => showMessage("#admin-google-source-message", text, isError);

async function fetchGoogleSourceState() {
  const [sourceData, healthData] = await Promise.all([
    adminFetch("/api/admin/google-sheets"),
    getJson("/api/health"),
  ]);
  return {
    sources: sourceData.sources,
    syncState: {
      canManual: healthData.google_sheets_web_sync_available,
      automaticReady: healthData.google_sheets_auto_sync_available,
    },
  };
}

function renderGoogleSourceCard(source, syncState) {
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
    ${renderSyncScheduleControls(source, syncState)}
    ${renderImageBridgeControls(source, bridge, syncState.canManual)}
  </article>`;
}

function fillGoogleSourceForm(source) {
  const form = $("#admin-google-source-form");
  form.elements.source_name.value = source.name || "";
  form.elements.spreadsheet_id.value = source.spreadsheet_id || "";
  form.elements.owner_name.value = source.owner_name || "";
  form.elements.description.value = source.description || "";
  form.elements.sheet_name.value = "";
  form.elements.read_range.value = "A:ZZ";
  $("#admin-google-sources-panel").open = true;
  form.elements.sheet_name.focus();
}

// `bindBridgeActions(container)` wires the Image Bridge buttons rendered in each card.
export function createGoogleSourcesController({ bindBridgeActions, loadAudit, loadCatalog }) {
  async function load() {
    const { sources, syncState } = await fetchGoogleSourceState();
    const sourcesById = new Map(sources.map((source) => [String(source.id), source]));
    $(LIST).innerHTML = sources.length
      ? sources.map((source) => renderGoogleSourceCard(source, syncState)).join("")
      : `<p class="muted">ยังไม่มี Google Sheets ที่ลงทะเบียน</p>`;
    document.querySelectorAll(`${LIST} [data-source-fill]`).forEach((button) => {
      button.addEventListener("click", () => fillGoogleSourceForm(sourcesById.get(button.dataset.sourceFill)));
    });
    document.querySelectorAll(`${LIST} [data-source-preview]`).forEach((button) => {
      button.addEventListener("click", () => preview(button));
    });
    document.querySelectorAll(`${LIST} [data-sync-schedule-save]`).forEach((button) => {
      button.addEventListener("click", () => saveSchedule(button));
    });
    bindBridgeActions(LIST);
  }

  async function preview(button) {
    const restore = setBusy(button, "กำลังตรวจสอบ…");
    message("กำลังอ่าน Google Sheets โดยยังไม่บันทึกข้อมูล…");
    try {
      const result = await adminFetch(`/api/admin/google-sheets/${button.dataset.sourcePreview}/preview`, {
        method: "POST",
        body: "{}",
      });
      const sheets = result.sheets
        .map(
          (sheet) =>
            `${sheet.sheet}: ${sheet.rows_received.toLocaleString()} แถว${sheet.stable_id_header ? ` · ใช้ ${sheet.stable_id_header}` : " · ยังไม่มี record_id"}${sheet.duplicate_stable_ids ? ` · ID ซ้ำ ${sheet.duplicate_stable_ids}` : ""}`,
        )
        .join(" | ");
      message(`ตรวจสอบแล้ว: ${sheets || "ไม่พบข้อมูล"}`);
    } catch (error) {
      message(error.message, true);
    } finally {
      restore();
    }
  }

  async function saveSchedule(button) {
    const sourceId = button.dataset.syncScheduleSave;
    const value = document.querySelector(`[data-sync-schedule="${sourceId}"]`).value;
    const restore = setBusy(button, "กำลังบันทึก…");
    try {
      const result = await adminFetch(`/api/admin/google-sheets/${sourceId}/sync-schedule`, {
        method: "PUT",
        body: JSON.stringify({ sync_frequency_minutes: value ? Number(value) : null }),
      });
      const detail = result.sync_frequency_minutes
        ? `ตั้งรอบ ${syncScheduleLabel(result.sync_frequency_minutes)} แล้ว`
        : "ตั้งให้ซิงก์ด้วยมือเท่านั้นแล้ว";
      const server = result.automatic_sync_server_enabled
        ? " ระบบอัตโนมัติพร้อมทำงาน"
        : " ระบบอัตโนมัติยังปิดอยู่ใน .env";
      message(`${detail} · ${server}`);
      await Promise.all([load(), loadCatalog(), loadAudit()]);
    } catch (error) {
      message(error.message, true);
      restore();
    }
  }

  async function save(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const payload = Object.fromEntries(
      FORM_FIELDS.map((name) => [name, String(values.get(name) || "").trim() || null]),
    );
    try {
      const result = await adminFetch("/api/admin/google-sheets", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      message(`บันทึกแล้ว: ${result.source_name} / ${result.sheet_name} — กด “ตรวจสอบก่อน Sync” แล้วจึงไป Sync จาก Data Catalog`);
      form.elements.sheet_name.value = "";
      await Promise.all([load(), loadCatalog(), loadAudit()]);
    } catch (error) {
      message(error.message, true);
    }
  }

  function bindEvents() {
    $("#admin-google-source-form").addEventListener("submit", save);
    $("#admin-google-source-reset").addEventListener("click", () => {
      $("#admin-google-source-form").reset();
      message();
    });
  }

  return { bindEvents, load };
}
