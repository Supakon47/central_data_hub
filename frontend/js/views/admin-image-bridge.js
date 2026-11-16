import { adminFetch } from "../api.js";
import { $ } from "../core/dom.js";

function resultMessage(prefix, result) {
  return `${prefix}: จับคู่ ${result.matched_records.toLocaleString()} ระเบียน · รูปใหม่/เปลี่ยน ${result.changed_images.toLocaleString()} · เอารูปเก่าออก ${result.removed_images.toLocaleString()} · จับคู่ไม่พบ ${result.unmatched_count.toLocaleString()} · ต้องตรวจ ${result.invalid_count.toLocaleString()}`;
}

export function createImageBridgeController({ loadAudit, loadCatalog, showGoogleMessage }) {
  function showMessage(button, message = "", isError = false) {
    if (button.closest("#admin-google-sources-list")) {
      showGoogleMessage(message, isError);
      return;
    }
    const target = $("#catalog-message");
    target.textContent = message;
    target.classList.toggle("error", isError);
  }

  async function sync(button) {
    const sourceName = button.dataset.sourceName || "แหล่งข้อมูลนี้";
    if (!window.confirm(`ยืนยันการดึงรูปภาพจาก Image Bridge ของ ${sourceName}? ระบบจะอ่านสำเนารูปจาก Google Drive และไม่แก้ Google Sheet ต้นทาง`)) return;
    button.disabled = true;
    const originalText = button.textContent;
    button.textContent = "กำลังดึงรูป…";
    showMessage(button, "กำลังอ่านรายการรูปจาก Google Drive…");
    try {
      const result = await adminFetch(`/api/admin/google-sheets/${button.dataset.imageBridgeSyncSource}/image-bridge/sync`, { method: "POST", body: "{}" });
      showMessage(button, resultMessage("Sync รูปสำเร็จ", result), Boolean(result.unmatched_count || result.invalid_count));
      await Promise.all([loadCatalog(), loadAudit()]);
    } catch (error) {
      showMessage(button, error.message, true);
      button.disabled = false;
      button.textContent = originalText;
    }
  }

  return { sync };
}
