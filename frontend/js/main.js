import { $, compact, escapeHtml } from "./core/dom.js";
import { state } from "./core/state.js";
import { initialiseTheme } from "./core/theme.js";
import { createDashboardController } from "./views/dashboard.js";
import { createDetailController } from "./views/detail.js";
import { createExplorerController } from "./views/explorer.js";
import { createCatalogController } from "./views/catalog.js";
import { createQualityController } from "./views/quality.js";
import { createAdminController } from "./views/admin.js";
import { createImageIntakeController } from "./views/admin-intake.js";
import { loadAuditLog } from "./views/admin-audit.js";
import { createImageBridgeController } from "./views/admin-image-bridge.js";
import { renderSyncScheduleControls, syncScheduleLabel } from "./views/admin-sync-schedule.js";
import { fetchGoogleSourceState, fillGoogleSourceForm, renderGoogleSourceCard, renderGoogleSourceList } from "./views/admin-sources.js";
import { adminFetch } from "./api.js";
import { pushRoute, routeFromLocation } from "./router.js";

const BUILD_VERSION = "2026.11.23.2";

// Keep card pages even at the common six-card desktop layout.
state.pageSize = 24;

let explorer;
let dashboard;
let detail;
let catalog;
let quality;
let adminRecords;
let imageIntake;
let imageBridge;

function bindRecordLinks(selector = "[data-record-id]") {
  explorer.bindRecordLinks(selector);
}

function loadRecords() {
  return explorer.loadRecords();
}

function loadDetail(recordId, updateHistory = true) {
  return detail.loadDetail(recordId, updateHistory);
}

function loadCatalog() {
  return catalog.loadCatalog();
}

function loadDataQuality() {
  return quality.loadDataQuality();
}

function loadAdminRecords() {
  return adminRecords.loadAdminRecords();
}

function renderAdminEditor(record = null) {
  return adminRecords.renderAdminEditor(record);
}

function setView(view) {
  document
    .querySelectorAll(".view")
    .forEach((element) =>
      element.classList.toggle("active", element.id === view),
    );
  document
    .querySelectorAll(".tab")
    .forEach((element) =>
      element.classList.toggle("active", element.dataset.view === view),
    );
  if (view === "dashboard") dashboard.loadDashboard();
  if (view === "catalog") loadCatalog();
  if (view === "quality") loadDataQuality();
  if (view === "admin") loadAdmin();
}
async function renderRoute() {
  const route = routeFromLocation();
  if (route.view === "detail") await loadDetail(route.recordId, false);
  else setView(route.view);
}
function navigate(view, recordId = null) {
  pushRoute(view, recordId);
  return renderRoute();
}

explorer = createExplorerController({ navigate });
dashboard = createDashboardController({
  navigate,
  bindRecordLinks: explorer.bindRecordLinks,
  loadRecords: explorer.loadRecords,
});
detail = createDetailController({ bindRecordLinks, pushRoute, setView });
imageBridge = createImageBridgeController({
  loadAudit,
  loadCatalog,
  showGoogleMessage: googleSourceMessage,
});
catalog = createCatalogController({
  loadAdminGoogleSources,
  loadAudit,
  loadDataQuality,
  loadFilterOptions,
  loadRecords,
  syncImageBridge,
});
quality = createQualityController({
  bindRecordLinks,
  loadAudit,
  loadCatalog,
});
adminRecords = createAdminController({
  loadAudit,
  loadDashboard: () => dashboard.loadDashboard(),
  loadRecords,
  showMessage: adminMessage,
});
imageIntake = createImageIntakeController({
  loadAudit,
  loadDashboard: () => dashboard.loadDashboard(),
  loadRecords,
});

function syncImageBridge(button) {
  return imageBridge.sync(button);
}
function adminMessage(message = "", isError = false) {
  const target = $("#admin-message");
  target.textContent = message;
  target.classList.toggle("error", isError);
}
function googleSourceMessage(message = "", isError = false) {
  const target = $("#admin-google-source-message");
  target.textContent = message;
  target.classList.toggle("error", isError);
}
function renderImageBridgeControls(source, bridge, canPreview) {
  const enabled = bridge.configured && canPreview;
  const actions = enabled
    ? `<button type="button" class="secondary" data-image-bridge-inspect-source="${source.id}">ตรวจสอบสิทธิ์</button>
       <button type="button" class="secondary" data-image-bridge-preview-source="${source.id}">ทดลองดึงรูป</button>
       <button type="button" data-image-bridge-sync-source="${source.id}" data-source-name="${escapeHtml(source.name)}">ดึงรูปภาพตอนนี้</button>
       <button type="button" class="danger" data-image-bridge-disconnect-source="${source.id}" data-source-name="${escapeHtml(source.name)}">ยกเลิกการเชื่อมต่อ</button>`
    : "";
  const bridgeStatus = bridge.configured
    ? `<p class="image-bridge-status">สถานะ: ตั้งค่าแล้ว${bridge.last_synced_at ? ` · ดึงรูปล่าสุด ${escapeHtml(bridge.last_synced_at)}` : ""}${bridge.last_message ? ` · ${escapeHtml(bridge.last_message)}` : ""}</p>`
    : `<p class="image-bridge-status">สถานะ: ยังไม่ได้ตั้งค่า</p>`;
  return `<div class="image-bridge-config">
    <strong>Image Bridge สำหรับภาพในเซลล์</strong>
    <p class="muted">วางลิงก์โฟลเดอร์ Google Drive ทั้งเส้น หรือ Folder ID ของโฟลเดอร์ที่ Apps Script สร้างไฟล์ Bridge และ manifest</p>
    ${bridgeStatus}
    <label>Google Drive folder URL หรือ Folder ID
      <input
        data-image-bridge-folder="${source.id}"
        value="${escapeHtml(bridge.drive_folder_id || "")}"
        placeholder="https://drive.google.com/drive/folders/..."
      >
    </label>
    <div class="catalog-actions">
      <button type="button" class="secondary" data-image-bridge-save="${source.id}">บันทึก Image Bridge</button>
      ${actions}
    </div>
  </div>`;
}

function bindAdminGoogleSourceActions(sourcesById) {
  document.querySelectorAll("[data-source-fill]").forEach((button) => {
    button.addEventListener("click", () => {
      fillGoogleSourceForm(sourcesById.get(button.dataset.sourceFill));
    });
  });
  document.querySelectorAll("[data-source-preview]").forEach((button) => {
    button.addEventListener("click", () => previewGoogleSource(button));
  });
  document.querySelectorAll("[data-image-bridge-save]").forEach((button) => {
    button.addEventListener("click", () => saveImageBridge(button));
  });
  document.querySelectorAll("[data-image-bridge-inspect-source]").forEach((button) => {
    button.addEventListener("click", () => inspectImageBridge(button));
  });
  document.querySelectorAll("[data-image-bridge-preview-source]").forEach((button) => {
    button.addEventListener("click", () => previewImageBridge(button));
  });
  document
    .querySelectorAll("[data-image-bridge-sync-source]")
    .forEach((button) => {
      button.addEventListener("click", () => syncImageBridge(button));
    });
  document.querySelectorAll("[data-image-bridge-disconnect-source]").forEach((button) => {
    button.addEventListener("click", () => disconnectImageBridge(button));
  });
  document.querySelectorAll("[data-sync-schedule-save]").forEach((button) => {
    button.addEventListener("click", () => saveSyncSchedule(button));
  });
}

async function loadAdminGoogleSources() {
  const { sources, syncState } = await fetchGoogleSourceState();
  const sourcesById = new Map(
    sources.map((source) => [String(source.id), source]),
  );
  $("#admin-google-sources-list").innerHTML = renderGoogleSourceList(
    sources,
    (source) => renderGoogleSourceCard(source, syncState, {
      renderBridge: renderImageBridgeControls,
      renderSchedule: renderSyncScheduleControls,
    }),
  );
  bindAdminGoogleSourceActions(sourcesById);
}
async function saveImageBridge(button) {
  const sourceId = button.dataset.imageBridgeSave;
  const folderId = document
    .querySelector(`[data-image-bridge-folder="${sourceId}"]`)
    .value.trim();
  if (!folderId) {
    googleSourceMessage("กรุณาวางลิงก์โฟลเดอร์ Google Drive หรือ Folder ID ก่อน", true);
    return;
  }
  button.disabled = true;
  try {
    await adminFetch(`/api/admin/google-sheets/${sourceId}/image-bridge`, {
      method: "PUT",
      body: JSON.stringify({ drive_folder_id: folderId }),
    });
    googleSourceMessage(
      "บันทึก Image Bridge แล้ว — กด “ตรวจสอบสิทธิ์” เพื่อดูว่า service account เห็น manifest หรือไม่",
    );
    await Promise.all([loadAdminGoogleSources(), loadCatalog(), loadAudit()]);
  } catch (error) {
    googleSourceMessage(error.message, true);
    button.disabled = false;
  }
}
async function saveSyncSchedule(button) {
  const sourceId = button.dataset.syncScheduleSave;
  const value = document.querySelector(`[data-sync-schedule="${sourceId}"]`).value;
  button.disabled = true;
  const originalText = button.textContent;
  button.textContent = "กำลังบันทึก…";
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
    googleSourceMessage(`${detail} · ${server}`);
    await Promise.all([loadAdminGoogleSources(), loadCatalog(), loadAudit()]);
  } catch (error) {
    googleSourceMessage(error.message, true);
    button.disabled = false;
    button.textContent = originalText;
  }
}
function imageBridgeMessage(button, message = "", isError = false) {
  if (button.closest("#admin-google-sources-list")) {
    googleSourceMessage(message, isError);
    return;
  }
  const target = $("#catalog-message");
  target.textContent = message;
  target.classList.toggle("error", isError);
}

function imageBridgeResultMessage(prefix, result) {
  return `${prefix}: จับคู่ ${result.matched_records.toLocaleString()} ระเบียน · รูปใหม่/เปลี่ยน ${result.changed_images.toLocaleString()} · เอารูปเก่าออก ${result.removed_images.toLocaleString()} · จับคู่ไม่พบ ${result.unmatched_count.toLocaleString()} · ต้องตรวจ ${result.invalid_count.toLocaleString()}`;
}

async function inspectImageBridge(button) {
  button.disabled = true;
  const originalText = button.textContent;
  button.textContent = "กำลังตรวจ…";
  imageBridgeMessage(button, "กำลังตรวจสอบสิทธิ์และไฟล์ใน Google Drive…");
  try {
    const result = await adminFetch(
      `/api/admin/google-sheets/${button.dataset.imageBridgeInspectSource}/image-bridge/inspect`,
      { method: "POST", body: "{}" },
    );
    const visibleCount = result.files_visible_to_service_account.length;
    const manifestStatus = result.manifest_visible ? "พบ manifest แล้ว" : "ยังไม่พบ manifest";
    imageBridgeMessage(
      button,
      `ตรวจสอบแล้ว: service account เห็นโฟลเดอร์ “${result.bridge_folder.name}” และเห็น ${visibleCount.toLocaleString()} ไฟล์ · ${manifestStatus}`,
      !result.manifest_visible,
    );
  } catch (error) {
    imageBridgeMessage(button, error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

async function previewImageBridge(button) {
  button.disabled = true;
  const originalText = button.textContent;
  button.textContent = "กำลังทดลอง…";
  imageBridgeMessage(button, "กำลังอ่าน Image Bridge โดยยังไม่บันทึกรูป…");
  try {
    const result = await adminFetch(
      `/api/admin/google-sheets/${button.dataset.imageBridgePreviewSource}/image-bridge/preview`,
      { method: "POST", body: "{}" },
    );
    imageBridgeMessage(
      button,
      imageBridgeResultMessage("ทดลองดึงรูปแล้ว", result),
      Boolean(result.unmatched_count || result.invalid_count),
    );
  } catch (error) {
    imageBridgeMessage(button, error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

async function disconnectImageBridge(button) {
  const sourceName = button.dataset.sourceName || "แหล่งข้อมูลนี้";
  if (!window.confirm(`ยืนยันว่าต้องการยกเลิก Image Bridge ของ “${sourceName}” ใช่หรือไม่? การทำรายการนี้ไม่ลบระเบียน รูปที่ดึงมาแล้ว หรือไฟล์ใน Google Drive`)) return;
  button.disabled = true;
  const originalText = button.textContent;
  button.textContent = "กำลังยกเลิก…";
  try {
    await adminFetch(
      `/api/admin/google-sheets/${button.dataset.imageBridgeDisconnectSource}/image-bridge`,
      { method: "DELETE" },
    );
    googleSourceMessage("ยกเลิกการเชื่อมต่อ Image Bridge แล้ว โดยเก็บข้อมูลและรูปเดิมไว้");
    await Promise.all([loadAdminGoogleSources(), loadCatalog(), loadAudit()]);
  } catch (error) {
    googleSourceMessage(error.message, true);
    button.disabled = false;
    button.textContent = originalText;
  }
}

async function previewGoogleSource(button) {
  button.disabled = true;
  const originalText = button.textContent;
  button.textContent = "กำลังตรวจสอบ…";
  googleSourceMessage("กำลังอ่าน Google Sheets โดยยังไม่บันทึกข้อมูล…");
  try {
    const result = await adminFetch(
      `/api/admin/google-sheets/${button.dataset.sourcePreview}/preview`,
      { method: "POST", body: "{}" },
    );
    const sheets = result.sheets
      .map(
        (sheet) =>
          `${sheet.sheet}: ${sheet.rows_received.toLocaleString()} แถว${sheet.stable_id_header ? ` · ใช้ ${sheet.stable_id_header}` : " · ยังไม่มี record_id"}${sheet.duplicate_stable_ids ? ` · ID ซ้ำ ${sheet.duplicate_stable_ids}` : ""}`,
      )
      .join(" | ");
    googleSourceMessage(`ตรวจสอบแล้ว: ${sheets || "ไม่พบข้อมูล"}`);
  } catch (error) {
    googleSourceMessage(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}
async function saveGoogleSource(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const values = new FormData(form);
  const payload = {};
  [
    "source_name",
    "spreadsheet_id",
    "sheet_name",
    "read_range",
    "owner_name",
    "description",
  ].forEach((name) => {
    payload[name] = String(values.get(name) || "").trim() || null;
  });
  try {
    const result = await adminFetch("/api/admin/google-sheets", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    googleSourceMessage(
      `บันทึกแล้ว: ${result.source_name} / ${result.sheet_name} — กด “ตรวจสอบก่อน Sync” แล้วจึงไป Sync จาก Data Catalog`,
    );
    form.elements.sheet_name.value = "";
    await Promise.all([loadAdminGoogleSources(), loadCatalog(), loadAudit()]);
  } catch (error) {
    googleSourceMessage(error.message, true);
  }
}
async function loadAdminSheetOptions() {
  const select = $("#admin-sheet-filter");
  const selected = select.value;
  const data = await (await fetch("/api/dashboard")).json();
  select.innerHTML = `<option value="">ทุกชีต</option>${data.by_source_sheet.map((item) => `<option value="${escapeHtml(item.label)}">${escapeHtml(item.label)} (${item.count.toLocaleString()})</option>`).join("")}`;
  select.value = [...select.options].some((option) => option.value === selected)
    ? selected
    : "";
}
async function loadAudit() {
  return loadAuditLog();
}
async function loadAdmin() {
  const session = await (await fetch("/api/admin/session")).json();
  $("#admin-login").hidden = session.authenticated || !session.configured;
  $("#admin-content").hidden = !session.authenticated;
  if (!session.configured) {
    adminMessage("ผู้ดูแลยังไม่ได้ตั้งรหัสผ่านในไฟล์ .env", true);
    return;
  }
  if (!session.authenticated) {
    adminMessage("", false);
    return;
  }
  adminMessage("ปลดล็อกหน้าจัดการแล้ว", false);
  renderAdminEditor();
  await loadAdminSheetOptions();
  await Promise.all([
    loadAdminRecords(),
    loadAudit(),
    loadAdminGoogleSources(),
    imageIntake.loadSources(),
  ]);
}
async function loadFilterOptions() {
  const [data, filterData] = await Promise.all([
    fetch("/api/dashboard").then((response) => response.json()),
    fetch("/api/filter-options").then((response) => response.json()),
  ]);
  const setOptions = (target, items) => {
    const select = $(target);
    const placeholder = select.options[0].outerHTML;
    select.innerHTML = `${placeholder}${items
      .map(
        (item) =>
          `<option value="${escapeHtml(item.label)}">${escapeHtml(item.label)} (${item.count.toLocaleString()})</option>`,
      )
      .join("")}`;
  };
  setOptions("#sheet-filter", data.by_source_sheet);
  setOptions("#year-filter", filterData.registration_years);
  setOptions("#check-filter", data.by_data_check);
  setOptions("#photo-filter", data.by_photo);
  setOptions("#antique-filter", data.by_antique);
  setOptions("#storage-filter", data.by_storage);
  const setGroupedOptions = (target, items) => {
    const select = $(target);
    const placeholder = select.options[0].outerHTML;
    select.innerHTML = `${placeholder}${items
      .map(
        (item) =>
          `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)} (${item.count.toLocaleString()})</option>`,
      )
      .join("")}`;
  };
  setGroupedOptions("#material-filter", filterData.material_groups);
  setGroupedOptions("#period-filter", filterData.period_groups);
}
async function initialise() {
  const health = await (await fetch("/api/health")).json();
  $("#freshness").textContent =
    health.environment === "development"
      ? `โหมดทดลองในเครื่อง · build ${BUILD_VERSION}`
      : `ระบบพร้อมใช้งาน · build ${BUILD_VERSION}`;
  if (!window.history.state)
    window.history.replaceState({ view: "explorer" }, "", window.location.href);
  await loadFilterOptions();
  await loadRecords();
  await renderRoute();
}
document
  .querySelectorAll(".tab")
  .forEach((button) =>
    button.addEventListener("click", () => navigate(button.dataset.view)),
  );
dashboard.bindEvents();
explorer.bindEvents();
$("[data-back]").addEventListener("click", () => navigate("explorer"));
$("#admin-login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await adminFetch("/api/admin/login", {
      method: "POST",
      body: JSON.stringify({ password: $("#admin-password").value }),
    });
    $("#admin-password").value = "";
    await loadAdmin();
  } catch (error) {
    adminMessage(error.message, true);
  }
});
$("#admin-new-record").addEventListener("click", () => renderAdminEditor());
$("#admin-google-source-form").addEventListener("submit", saveGoogleSource);
$("#admin-google-source-reset").addEventListener("click", () => {
  $("#admin-google-source-form").reset();
  googleSourceMessage();
});
$("#admin-image-intake-source").addEventListener(
  "change",
  () => imageIntake.renderSheets(),
);
$("#admin-image-intake-form").addEventListener("submit", (event) =>
  imageIntake.upload(event),
);
$("#quality-filter-form").addEventListener("submit", (event) => {
  event.preventDefault();
  loadDataQuality().catch((error) => {
    $("#quality-summary").textContent = error.message;
  });
});
$("#admin-search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  $("#admin-records-panel").open = true;
  loadAdminRecords();
});
$("#admin-logout").addEventListener("click", async () => {
  await adminFetch("/api/admin/logout", { method: "POST", body: "{}" });
  await loadAdmin();
});
window.addEventListener("popstate", () => renderRoute());
initialiseTheme();
initialise().catch((error) => {
  $("#freshness").textContent = `เกิดข้อผิดพลาด: ${error.message}`;
});
