// Admin page: attach a batch of image files to records by their record_id file names.
import { adminFetch, uploadForm } from "../api.js";
import { $, escapeHtml, setBusy, showMessage as showStatus } from "../core/dom.js";
import { state } from "../core/state.js";

export function createImageIntakeController({ loadAudit, loadDashboard, loadRecords }) {
  const showMessage = (message, isError) => showStatus("#admin-image-intake-message", message, isError);

  function renderSheets() {
    const sourceSelect = $("#admin-image-intake-source");
    const sheetSelect = $("#admin-image-intake-sheet");
    const source = state.imageIntakeSources.find(
      (item) => String(item.id) === sourceSelect.value,
    );
    sheetSelect.innerHTML = `<option value="">เลือกชีต</option>${(source?.sheets || []).map((sheet) => `<option value="${escapeHtml(sheet.name)}">${escapeHtml(sheet.name)} (${sheet.record_count.toLocaleString()} ระเบียน)</option>`).join("")}`;
    sheetSelect.disabled = !source;
  }

  async function loadSources() {
    const sourceSelect = $("#admin-image-intake-source");
    const selected = sourceSelect.value;
    const data = await adminFetch("/api/admin/image-intake/sources");
    state.imageIntakeSources = data.sources;
    sourceSelect.innerHTML = `<option value="">เลือกแหล่งข้อมูล</option>${data.sources.map((source) => `<option value="${source.id}">${escapeHtml(source.name)}</option>`).join("")}`;
    sourceSelect.value = data.sources.some(
      (source) => String(source.id) === selected,
    ) ? selected : "";
    renderSheets();
    showMessage(data.sources.length ? "" : "ยังไม่พบชีตที่มี record_id สำหรับจับคู่ภาพ");
  }

  async function upload(event) {
    event.preventDefault();
    const sourceId = $("#admin-image-intake-source").value;
    const sheetName = $("#admin-image-intake-sheet").value;
    const files = $("#admin-image-intake-files").files;
    if (!sourceId || !sheetName || !files?.length) {
      showMessage("เลือกแหล่งข้อมูล ชีต และไฟล์รูปภาพก่อน", true);
      return;
    }
    // currentTarget is cleared once the handler awaits, so keep the form now.
    const formElement = event.currentTarget;
    const restore = setBusy(formElement.querySelector("button[type='submit']"), "กำลังนำภาพเข้า…");
    showMessage("กำลังจับคู่ชื่อไฟล์กับ record_id โดยไม่แก้ Google Sheets…");
    try {
      const form = new FormData();
      form.append("sheet_name", sheetName);
      [...files].forEach((file) => form.append("images", file));
      const result = await uploadForm(`/api/admin/image-intake/${sourceId}`, form, "นำภาพเข้าไม่สำเร็จ");
      const notes = [`นำเข้าแล้ว ${result.uploaded.toLocaleString()} ภาพ`];
      if (result.unmatched_count) {
        notes.push(`ไม่พบ record_id ${result.unmatched_count.toLocaleString()} รายการ: ${result.unmatched.join(", ")}${result.unmatched_count > result.unmatched.length ? "…" : ""}`);
      }
      if (result.invalid_count) {
        notes.push(`ข้ามไฟล์ ${result.invalid_count.toLocaleString()} ไฟล์: ${result.invalid_files.join(", ")}${result.invalid_count > result.invalid_files.length ? "…" : ""}`);
      }
      showMessage(notes.join(" · "), Boolean(result.unmatched_count || result.invalid_count));
      formElement.reset();
      renderSheets();
      await Promise.all([loadRecords(), loadDashboard(), loadAudit()]);
    } catch (error) {
      showMessage(error.message, true);
    } finally {
      restore();
    }
  }

  return { loadSources, renderSheets, upload };
}
