// Image Bridge: the Drive folder an Apps Script fills with a source's cell images.
import { adminFetch } from "../api.js";
import { escapeHtml, setBusy, showMessage } from "../core/dom.js";

function resultMessage(prefix, result) {
  return `${prefix}: จับคู่ ${result.matched_records.toLocaleString()} ระเบียน · รูปใหม่/เปลี่ยน ${result.changed_images.toLocaleString()} · เอารูปเก่าออก ${result.removed_images.toLocaleString()} · จับคู่ไม่พบ ${result.unmatched_count.toLocaleString()} · ต้องตรวจ ${result.invalid_count.toLocaleString()}`;
}

export function renderImageBridgeControls(source, bridge, canPreview) {
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

// `reloadSources` refreshes the admin source list after a change.
export function createImageBridgeController({ loadAudit, loadCatalog, reloadSources }) {
  const googleMessage = (message, isError) => showMessage("#admin-google-source-message", message, isError);

  // Buttons appear both in the admin source list and in the Data Catalog.
  function bridgeMessage(button, message = "", isError = false) {
    const target = button.closest("#admin-google-sources-list") ? "#admin-google-source-message" : "#catalog-message";
    showMessage(target, message, isError);
  }

  async function save(button) {
    const sourceId = button.dataset.imageBridgeSave;
    const folderId = document.querySelector(`[data-image-bridge-folder="${sourceId}"]`).value.trim();
    if (!folderId) {
      googleMessage("กรุณาวางลิงก์โฟลเดอร์ Google Drive หรือ Folder ID ก่อน", true);
      return;
    }
    button.disabled = true;
    try {
      await adminFetch(`/api/admin/google-sheets/${sourceId}/image-bridge`, {
        method: "PUT",
        body: JSON.stringify({ drive_folder_id: folderId }),
      });
      googleMessage("บันทึก Image Bridge แล้ว — กด “ตรวจสอบสิทธิ์” เพื่อดูว่า service account เห็น manifest หรือไม่");
      await Promise.all([reloadSources(), loadCatalog(), loadAudit()]);
    } catch (error) {
      googleMessage(error.message, true);
      button.disabled = false;
    }
  }

  async function inspect(button) {
    const restore = setBusy(button, "กำลังตรวจ…");
    bridgeMessage(button, "กำลังตรวจสอบสิทธิ์และไฟล์ใน Google Drive…");
    try {
      const result = await adminFetch(
        `/api/admin/google-sheets/${button.dataset.imageBridgeInspectSource}/image-bridge/inspect`,
        { method: "POST", body: "{}" },
      );
      const visibleCount = result.files_visible_to_service_account.length;
      const manifestStatus = result.manifest_visible ? "พบ manifest แล้ว" : "ยังไม่พบ manifest";
      bridgeMessage(
        button,
        `ตรวจสอบแล้ว: service account เห็นโฟลเดอร์ “${result.bridge_folder.name}” และเห็น ${visibleCount.toLocaleString()} ไฟล์ · ${manifestStatus}`,
        !result.manifest_visible,
      );
    } catch (error) {
      bridgeMessage(button, error.message, true);
    } finally {
      restore();
    }
  }

  async function preview(button) {
    const restore = setBusy(button, "กำลังทดลอง…");
    bridgeMessage(button, "กำลังอ่าน Image Bridge โดยยังไม่บันทึกรูป…");
    try {
      const result = await adminFetch(
        `/api/admin/google-sheets/${button.dataset.imageBridgePreviewSource}/image-bridge/preview`,
        { method: "POST", body: "{}" },
      );
      bridgeMessage(button, resultMessage("ทดลองดึงรูปแล้ว", result), Boolean(result.unmatched_count || result.invalid_count));
    } catch (error) {
      bridgeMessage(button, error.message, true);
    } finally {
      restore();
    }
  }

  async function sync(button) {
    const sourceName = button.dataset.sourceName || "แหล่งข้อมูลนี้";
    if (!window.confirm(`ยืนยันการดึงรูปภาพจาก Image Bridge ของ ${sourceName}? ระบบจะอ่านสำเนารูปจาก Google Drive และไม่แก้ Google Sheet ต้นทาง`)) return;
    const restore = setBusy(button, "กำลังดึงรูป…");
    bridgeMessage(button, "กำลังอ่านรายการรูปจาก Google Drive…");
    try {
      const result = await adminFetch(
        `/api/admin/google-sheets/${button.dataset.imageBridgeSyncSource}/image-bridge/sync`,
        { method: "POST", body: "{}" },
      );
      bridgeMessage(button, resultMessage("Sync รูปสำเร็จ", result), Boolean(result.unmatched_count || result.invalid_count));
      await Promise.all([loadCatalog(), loadAudit()]);
    } catch (error) {
      bridgeMessage(button, error.message, true);
      restore();
    }
  }

  async function disconnect(button) {
    const sourceName = button.dataset.sourceName || "แหล่งข้อมูลนี้";
    if (!window.confirm(`ยืนยันว่าต้องการยกเลิก Image Bridge ของ “${sourceName}” ใช่หรือไม่? การทำรายการนี้ไม่ลบระเบียน รูปที่ดึงมาแล้ว หรือไฟล์ใน Google Drive`)) return;
    const restore = setBusy(button, "กำลังยกเลิก…");
    try {
      await adminFetch(
        `/api/admin/google-sheets/${button.dataset.imageBridgeDisconnectSource}/image-bridge`,
        { method: "DELETE" },
      );
      googleMessage("ยกเลิกการเชื่อมต่อ Image Bridge แล้ว โดยเก็บข้อมูลและรูปเดิมไว้");
      await Promise.all([reloadSources(), loadCatalog(), loadAudit()]);
    } catch (error) {
      googleMessage(error.message, true);
      restore();
    }
  }

  // Wire the bridge buttons inside `container` (a CSS selector).
  function bindActions(container) {
    const bind = (attribute, handler) => {
      document.querySelectorAll(`${container} [${attribute}]`).forEach((button) => {
        button.addEventListener("click", () => handler(button));
      });
    };
    bind("data-image-bridge-save", save);
    bind("data-image-bridge-inspect-source", inspect);
    bind("data-image-bridge-preview-source", preview);
    bind("data-image-bridge-sync-source", sync);
    bind("data-image-bridge-disconnect-source", disconnect);
  }

  return { bindActions, sync };
}
