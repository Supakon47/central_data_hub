// Data Catalog: every source with its sync state, and admin actions on each.
import { adminFetch, fetchAdminSession, getJson } from "../api.js";
import { $, compact, escapeHtml, setBusy, showMessage } from "../core/dom.js";
import { syncScheduleLabel } from "./admin-sync-schedule.js";

const LIST = "#catalog-list";

export function createCatalogController({
  loadAdminGoogleSources,
  loadAudit,
  loadDataQuality,
  loadFilterOptions,
  loadRecords,
  syncImageBridge,
}) {
  const catalogMessage = (message, isError) => showMessage("#catalog-message", message, isError);

  function renderCatalogActions(source, bridge, canSyncFromWeb, isAdmin) {
    if (
      source.connection_type === "xlsx_import" &&
      isAdmin &&
      source.record_count
    ) {
      return `<div class="catalog-actions">
        <button
          type="button"
          class="danger"
          data-clear-source="${source.id}"
          data-source-name="${escapeHtml(source.name)}"
          data-source-kind="xlsx_import"
        >ล้างข้อมูลที่นำเข้าจาก Excel</button>
      </div>`;
    }
    if (source.connection_type !== "google_sheets" || !isAdmin) return "";

    const syncButton = canSyncFromWeb
      ? `<button type="button" data-google-sync-source="${source.id}" data-source-name="${escapeHtml(source.name)}">Sync ข้อมูลล่าสุด</button>`
      : `<span class="muted">ยังไม่ได้ตั้งค่าให้ sync จากหน้าเว็บ</span>`;
    const imageButton =
      bridge.configured && canSyncFromWeb
        ? `<button type="button" class="secondary" data-image-bridge-sync-source="${source.id}" data-source-name="${escapeHtml(source.name)}">Sync รูปภาพ</button>`
        : "";
    const clearButton = source.record_count
      ? `<button type="button" class="danger" data-clear-source="${source.id}" data-source-name="${escapeHtml(source.name)}" data-source-kind="google_sheets">ล้างข้อมูลที่ Sync แล้ว</button>`
      : "";
    return `<div class="catalog-actions">
      ${syncButton}${imageButton}${clearButton}
      <button type="button" class="danger" data-delete-google-source="${source.id}" data-source-name="${escapeHtml(source.name)}">ลบการเชื่อมต่อ</button>
    </div>`;
  }

  function renderCatalogSource(source, canSyncFromWeb, isAdmin) {
    const sheets = (source.configured_sheets || [])
      .filter((sheet) => sheet.is_active)
      .map((sheet) => escapeHtml(sheet.name))
      .join(", ");
    const bridge = source.image_bridge || { configured: false };
    const sync = source.last_sync;
    const syncTime = sync ? sync.completed_at || sync.started_at : "ยังไม่เคย";
    const bridgeStatus = bridge.configured
      ? `<span>Image Bridge: ${bridge.last_synced_at ? `ล่าสุด ${escapeHtml(bridge.last_synced_at)}` : "ตั้งค่าแล้ว"}</span>`
      : "";
    const syncMessage = sync?.message
      ? `<span title="${escapeHtml(sync.message)}">${escapeHtml(sync.message)}</span>`
      : "";
    const schedule = source.sync_frequency_minutes
      ? `<span>รอบอัตโนมัติ: ${escapeHtml(syncScheduleLabel(source.sync_frequency_minutes))}</span>`
      : `<span>รอบ sync: ด้วยมือ</span>`;

    return `<article class="catalog-item">
      <h3>${escapeHtml(source.name)}</h3>
      <p class="muted">${compact(source.description, "ไม่มีคำอธิบาย")}</p>
      <div class="catalog-meta">
        <span>ประเภท: ${escapeHtml(source.connection_type)}</span>
        <span>ชั้นข้อมูล: ${escapeHtml(source.classification)}</span>
        <span>ชีตที่เชื่อม: ${sheets || "-"}</span>
        <span>ระเบียน: ${source.record_count.toLocaleString()}</span>
        <span class="issue">ประเด็นที่ยังไม่ปิด: ${source.unresolved_issues.toLocaleString()}</span>
        <span>sync ล่าสุด: ${escapeHtml(syncTime)}</span>
        ${schedule}
        ${bridgeStatus}${syncMessage}
      </div>
      ${renderCatalogActions(source, bridge, canSyncFromWeb, isAdmin)}
    </article>`;
  }

  function bindCatalogActions() {
    const bind = (attribute, handler) => {
      document.querySelectorAll(`${LIST} [${attribute}]`).forEach((button) => {
        button.addEventListener("click", () => handler(button));
      });
    };
    bind("data-google-sync-source", syncGoogleSource);
    bind("data-image-bridge-sync-source", syncImageBridge);
    bind("data-clear-source", clearCentralData);
    bind("data-delete-google-source", deleteGoogleSource);
  }

  async function loadCatalog() {
    const [data, adminSession, health] = await Promise.all([
      getJson("/api/catalog"),
      fetchAdminSession(),
      getJson("/api/health"),
    ]);
    const canSyncFromWeb =
      adminSession.authenticated && health.google_sheets_web_sync_available;
    $(LIST).innerHTML =
      data.sources
        .map((source) =>
          renderCatalogSource(source, canSyncFromWeb, adminSession.authenticated),
        )
        .join("") || `<p class="muted">ยังไม่มีแหล่งข้อมูล</p>`;
    bindCatalogActions();
  }

  async function syncGoogleSource(button) {
    const sourceName = button.dataset.sourceName || "แหล่งข้อมูลนี้";
    if (
      !window.confirm(
        `ยืนยันการดึงข้อมูลล่าสุดจาก ${sourceName}? ระบบจะอ่าน Google Sheets ต้นทางและอัปเดตสำเนากลางเท่านั้น`,
      )
    ) return;

    const restore = setBusy(button, "กำลัง Sync…");
    catalogMessage("กำลังอ่านข้อมูลจาก Google Sheets…");
    try {
      const result = await adminFetch(
        `/api/admin/google-sheets/${button.dataset.googleSyncSource}/sync`,
        { method: "POST", body: "{}" },
      );
      const imageResult = result.embedded_images_exported
        ? ` · ดึงรูปฝัง ${result.embedded_images_exported.toLocaleString()} รูป`
        : result.image_export_warning
          ? ` · ${result.image_export_warning}`
          : "";
      catalogMessage(
        `Sync สำเร็จ: อ่าน ${result.rows_read.toLocaleString()} แถว · เพิ่ม ${result.inserted.toLocaleString()} · อัปเดต ${result.updated.toLocaleString()} · ลบจากต้นทาง ${result.deleted.toLocaleString()} · ไม่เปลี่ยนแปลง ${result.skipped.toLocaleString()} · ประเด็น ${result.errors.toLocaleString()}${imageResult}`,
      );
      await Promise.all([loadCatalog(), loadRecords(), loadFilterOptions()]);
    } catch (error) {
      catalogMessage(error.message, true);
      restore();
    }
  }

  async function clearCentralData(button) {
    const sourceName = button.dataset.sourceName || "";
    const isExcelImport = button.dataset.sourceKind === "xlsx_import";
    const sourceLabel = isExcelImport
      ? "ข้อมูลที่นำเข้าจาก Excel"
      : "ข้อมูลที่ Sync แล้ว";
    if (
      !window.confirm(
        `ยืนยันว่าต้องการลบ${sourceLabel}ของ “${sourceName}” ออกจาก Data Hub ใช่หรือไม่?`,
      )
    ) return;

    const restore = setBusy(button, "กำลังล้าง…");
    catalogMessage("กำลังล้างข้อมูลจาก Data Hub…");
    try {
      const result = await adminFetch(
        `/api/admin/sources/${button.dataset.clearSource}/clear-central-data`,
        { method: "POST", body: "{}" },
      );
      const imageText = result.deleted_images
        ? ` · รูปที่ระบบเก็บไว้ ${result.deleted_images.toLocaleString()} รูป`
        : "";
      catalogMessage(
        `ล้าง${sourceLabel}แล้ว: ${result.deleted_records.toLocaleString()} ระเบียน · ${result.deleted_quality_issues.toLocaleString()} ประเด็น${imageText} โดยเก็บไฟล์ต้นฉบับ การตั้งค่าแหล่งข้อมูล และประวัติไว้`,
      );
      await Promise.all([
        loadCatalog(),
        loadRecords(),
        loadFilterOptions(),
        loadDataQuality(),
        loadAudit(),
        loadAdminGoogleSources(),
      ]);
    } catch (error) {
      catalogMessage(error.message, true);
      restore();
    }
  }

  async function deleteGoogleSource(button) {
    const sourceName = button.dataset.sourceName || "";
    if (!window.confirm(`ยืนยันว่าต้องการลบการเชื่อมต่อ “${sourceName}” ใช่หรือไม่?`)) return;

    const restore = setBusy(button, "กำลังลบ…");
    catalogMessage("กำลังลบการเชื่อมต่อออกจาก Data Hub…");
    try {
      const result = await adminFetch(
        `/api/admin/google-sheets/${button.dataset.deleteGoogleSource}`,
        { method: "DELETE" },
      );
      catalogMessage(
        `ลบการเชื่อมต่อแล้ว: ${result.source_name} · สำเนาข้อมูล ${result.deleted_records.toLocaleString()} ระเบียนถูกลบจาก Data Hub โดยไม่แก้ Google Sheets ต้นฉบับ`,
      );
      await Promise.all([
        loadCatalog(),
        loadRecords(),
        loadFilterOptions(),
        loadDataQuality(),
        loadAudit(),
        loadAdminGoogleSources(),
      ]);
    } catch (error) {
      catalogMessage(error.message, true);
      restore();
    }
  }

  return { loadCatalog };
}
