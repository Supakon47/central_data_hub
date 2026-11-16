import { adminFetch } from "../api.js";
import { $, escapeHtml } from "../core/dom.js";

function entityLabel(type) {
  if (type === "data_source") return "แหล่งข้อมูล";
  if (type === "data_quality_issue") return "ประเด็นคุณภาพข้อมูล";
  return "ระเบียน";
}

export async function loadAuditLog() {
  const data = await adminFetch("/api/admin/audit");
  $("#audit-list").innerHTML =
    data.items
      .map(
        (item) =>
          `<div class="audit-item"><strong>${escapeHtml(item.action)}</strong> ${entityLabel(item.entity_type)} #${escapeHtml(item.entity_id)}<br><span class="muted">${new Date(item.created_at).toLocaleString("th-TH")}</span></div>`,
      )
      .join("") || `<p class="muted">ยังไม่มีประวัติการแก้ไข</p>`;
}
