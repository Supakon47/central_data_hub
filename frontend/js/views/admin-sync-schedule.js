import { escapeHtml } from "../core/dom.js";

const SCHEDULE_OPTIONS = [
  ["", "ซิงก์ด้วยมือเท่านั้น"],
  ["15", "ทุก 15 นาที"],
  ["30", "ทุก 30 นาที"],
  ["60", "ทุก 1 ชั่วโมง"],
  ["360", "ทุก 6 ชั่วโมง"],
  ["1440", "ทุก 1 วัน"],
];

export function syncScheduleLabel(minutes) {
  const known = SCHEDULE_OPTIONS.find(([value]) => Number(value) === Number(minutes));
  return known ? known[1] : `ทุก ${Number(minutes).toLocaleString()} นาที`;
}

export function renderSyncScheduleControls(source, syncState) {
  const currentValue = String(source.sync_frequency_minutes || "");
  const options = [...SCHEDULE_OPTIONS];
  if (currentValue && !options.some(([value]) => value === currentValue)) {
    options.push([currentValue, syncScheduleLabel(source.sync_frequency_minutes)]);
  }
  const serverStatus = syncState.automaticReady
    ? "ระบบอัตโนมัติพร้อมทำงานบนเครื่องนี้"
    : "บันทึกรอบได้ แต่ยังไม่เปิดระบบอัตโนมัติบนเครื่องนี้";
  return `<div class="image-bridge-config sync-schedule-config">
    <strong>ตั้งรอบ Sync ข้อมูล</strong>
    <p class="muted">${serverStatus} · ระบบจะอ่านข้อมูล Google Sheets ก่อน แล้วค่อยดึงรูปจาก Image Bridge หากตั้งค่าไว้</p>
    <label>รอบซิงก์
      <select data-sync-schedule="${source.id}">
        ${options.map(([value, label]) => `<option value="${value}"${value === currentValue ? " selected" : ""}>${escapeHtml(label)}</option>`).join("")}
      </select>
    </label>
    <div class="catalog-actions">
      <button type="button" class="secondary" data-sync-schedule-save="${source.id}">บันทึกรอบ Sync</button>
    </div>
  </div>`;
}
