// Admin page: create, edit and delete records in the central copy, and upload their images.
import { adminFetch, getJson, uploadForm } from "../api.js";
import { $, compact, escapeHtml, setBusy } from "../core/dom.js";

const STATUS_OPTIONS = {
  data_check: ["ตรวจสอบแล้ว", "ยังไม่ตรวจสอบ", "อยู่ในระหว่างการตรวจสอบ"],
  photographed: ["ถ่ายภาพแล้ว", "ยังไม่ถ่ายภาพ", "อยู่ในระหว่างการถ่ายภาพ"],
  antique: ["ลงระบบแล้ว", "ยังไม่ลงระบบ", "อยู่ในระหว่างการลงระบบ"],
  storage: [
    "ส่งขึ้นห้องคลังแล้ว",
    "ยังไม่ส่งขึ้นห้องคลัง",
    "อยู่ในระหว่างการส่งขึ้นห้องคลัง",
  ],
};

const CREATE_REQUIRED = new Set(["registration_no", "title_description"]);
const RECORD_FIELDS = [
  ["registration_no", "เลขทะเบียน", "text"],
  ["previous_registration_no", "เลขทะเบียนเดิม", "text"],
  ["title_description", "รายการ", "textarea"],
  ["dimensions_text", "ขนาด", "textarea"],
  ["material", "ชนิด", "text"],
  ["period", "อายุสมัย", "textarea"],
  ["provenance", "ประวัติที่มา", "textarea"],
  ["image_url", "ลิงก์รูปภาพ", "url"],
  ["status_data_check", "การตรวจสอบข้อมูล", "select", STATUS_OPTIONS.data_check],
  ["status_photographed", "การถ่ายภาพแล้ว", "select", STATUS_OPTIONS.photographed],
  ["status_antique", "การลงระบบ Antique", "select", STATUS_OPTIONS.antique],
  ["status_storage", "การส่งขึ้นห้องคลัง", "select", STATUS_OPTIONS.storage],
];

export function createAdminRecordsController({
  loadAudit,
  loadDashboard,
  loadRecords,
  showMessage,
}) {
  function fieldEditor(name, label, type, value, options = [], required = false) {
    const requiredMarker = required
      ? ` <span class="required" aria-hidden="true">*</span>`
      : "";
    const requiredAttribute = required ? ' required aria-required="true"' : "";
    if (type === "select") {
      const safeOptions = value && !options.includes(value) ? [value, ...options] : options;
      const selectOptions = safeOptions
        .map((option) => {
          const selected = option === value ? " selected" : "";
          const originalValueNote = options.includes(option) ? "" : " (ค่าจากต้นทาง)";
          return `<option value="${escapeHtml(option)}"${selected}>${escapeHtml(option)}${originalValueNote}</option>`;
        })
        .join("");
      return `<label>${label}${requiredMarker}
        <select name="${name}"${requiredAttribute}>
          <option value="">ไม่ระบุ</option>${selectOptions}
        </select>
      </label>`;
    }
    if (type === "textarea") {
      return `<label>${label}${requiredMarker}
        <textarea name="${name}" rows="3"${requiredAttribute}>${escapeHtml(value || "")}</textarea>
      </label>`;
    }
    return `<label>${label}${requiredMarker}
      <input name="${name}" type="${type}" value="${escapeHtml(value || "")}"${requiredAttribute}>
    </label>`;
  }

  function renderImageUpload(record) {
    if (!record) {
      return `<p class="muted">สร้างระเบียนก่อน จึงจะอัปโหลดภาพกลางสำหรับ AI ได้</p>`;
    }
    return `<section class="image-upload">
      <h4>ภาพกลางสำหรับ AI</h4>
      <p class="muted">อัปโหลด JPEG, PNG, GIF หรือ WebP ไม่เกิน 10 MB ระบบเก็บสำเนาไว้ใน Central Data Hub และไม่เขียนกลับไปที่ Google Sheets</p>
      <div class="image-upload-controls">
        <input id="admin-image-file" type="file" accept="image/jpeg,image/png,image/gif,image/webp">
        <button id="admin-image-upload" type="button">อัปโหลดภาพ</button>
      </div>
    </section>`;
  }

  function renderRecordForm(record) {
    const fields = RECORD_FIELDS.map(([name, label, type, options]) => {
      const required = !record && CREATE_REQUIRED.has(name);
      return fieldEditor(name, label, type, record?.[name], options, required);
    }).join("");
    const recordId = record ? record.id : "";
    const submitLabel = record ? "บันทึกการแก้ไข" : "สร้างระเบียน";
    const cancelButton = record
      ? `<button id="admin-cancel-edit" class="secondary" type="button">ยกเลิก</button>`
      : "";
    return `<form id="admin-record-form" class="admin-form">
      <input name="record_id" type="hidden" value="${recordId}">
      <div class="form-grid">${fields}</div>
      <div class="form-actions">
        <button type="submit">${submitLabel}</button>${cancelButton}
      </div>
    </form>`;
  }

  function renderAdminEditor(record = null) {
    const heading = record
      ? `แก้ไขระเบียน ${escapeHtml(record.registration_no || `#${record.id}`)}`
      : "เพิ่มระเบียนใหม่";
    const sourceNote =
      record && record.source_name !== "แก้ไขโดยเจ้าหน้าที่"
        ? `<p class="warning-text">ระเบียนนี้มาจาก ${escapeHtml(record.source_name || "แหล่งข้อมูล")}; หากมีการ sync แถวต้นทางที่เปลี่ยนแล้ว ข้อมูลที่แก้ในสำเนากลางอาจถูกแทนที่</p>`
        : "";
    const requiredNote = record
      ? ""
      : `<p class="muted">ช่องที่มี <span class="required">*</span> จำเป็นต้องกรอกก่อนสร้างระเบียน</p>`;
    $("#admin-editor").innerHTML = `<h3>${heading}</h3>
      ${requiredNote}${sourceNote}
      ${renderRecordForm(record)}
      ${renderImageUpload(record)}`;
    $("#admin-record-form").addEventListener("submit", saveAdminRecord);
    $("#admin-cancel-edit")?.addEventListener("click", () => renderAdminEditor());
    $("#admin-image-upload")?.addEventListener("click", () => uploadAdminImage(record.id));
  }

  async function loadAdminRecords() {
    const query = $("#admin-query").value.trim();
    const sourceSheet = $("#admin-sheet-filter").value;
    const params = new URLSearchParams({ page: "1", page_size: "20" });
    if (query) params.set("q", query);
    if (sourceSheet) params.set("source_sheet", sourceSheet);
    const data = await getJson(`/api/records?${params}`);
    $("#admin-record-summary").textContent =
      data.total > data.items.length
        ? `พบ ${data.total.toLocaleString()} ระเบียน · แสดง 20 รายการแรก กรุณาค้นหาหรือเลือกชีตเพื่อดูเฉพาะรายการที่ต้องการ`
        : `พบ ${data.total.toLocaleString()} ระเบียน`;
    $("#admin-records-body").innerHTML =
      data.items
        .map(
          (record) =>
            `<tr><td>${compact(record.registration_no)}</td><td><div class="clamp">${compact(record.title_description)}</div></td><td>${escapeHtml(record.source_name || "")}<br><span class="muted">${escapeHtml(record.source_sheet)}</span></td><td class="actions"><button class="small secondary" data-admin-edit="${record.id}">แก้ไข</button><button class="small danger" data-admin-delete="${record.id}">ลบ</button></td></tr>`,
        )
        .join("") || `<tr><td colspan="4" class="muted">ไม่พบระเบียน</td></tr>`;
    document.querySelectorAll("#admin-records-body [data-admin-edit]").forEach((button) =>
      button.addEventListener("click", async () => {
        const record = await getJson(`/api/records/${button.dataset.adminEdit}`);
        renderAdminEditor(record);
        window.scrollTo({ top: 0, behavior: "smooth" });
      }),
    );
    document.querySelectorAll("#admin-records-body [data-admin-delete]").forEach((button) =>
      button.addEventListener("click", () => deleteAdminRecord(button.dataset.adminDelete)),
    );
  }

  async function saveAdminRecord(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const recordId = form.get("record_id");
    const payload = {};
    RECORD_FIELDS.forEach(([name]) => {
      payload[name] = String(form.get(name) || "").trim() || null;
    });
    try {
      await adminFetch(
        recordId ? `/api/admin/records/${recordId}` : "/api/admin/records",
        { method: recordId ? "PATCH" : "POST", body: JSON.stringify(payload) },
      );
      showMessage(recordId ? "บันทึกการแก้ไขแล้ว" : "เพิ่มระเบียนใหม่แล้ว");
      renderAdminEditor();
      await Promise.all([loadAdminRecords(), loadAudit(), loadRecords()]);
    } catch (error) {
      showMessage(error.message, true);
    }
  }

  async function uploadAdminImage(recordId) {
    const input = $("#admin-image-file");
    const image = input.files?.[0];
    if (!image) {
      showMessage("กรุณาเลือกไฟล์รูปภาพก่อน", true);
      return;
    }
    const restore = setBusy($("#admin-image-upload"), "กำลังอัปโหลด…");
    try {
      const form = new FormData();
      form.append("image", image);
      await uploadForm(`/api/admin/records/${recordId}/image`, form, "อัปโหลดภาพไม่สำเร็จ");
      const record = await getJson(`/api/records/${recordId}`);
      showMessage("อัปโหลดภาพกลางแล้ว ภาพนี้พร้อมใช้ในขั้นตอน AI ต่อไป");
      renderAdminEditor(record);
      await Promise.all([loadRecords(), loadDashboard(), loadAudit()]);
    } catch (error) {
      showMessage(error.message, true);
      restore();
    }
  }

  async function deleteAdminRecord(recordId) {
    if (!window.confirm("ยืนยันการลบระเบียนนี้จากสำเนากลาง? การ sync จากต้นทางอาจนำระเบียนกลับมาอีก")) return;
    try {
      await adminFetch(`/api/admin/records/${recordId}`, { method: "DELETE" });
      showMessage("ลบระเบียนจากสำเนากลางแล้ว");
      renderAdminEditor();
      await Promise.all([loadAdminRecords(), loadAudit(), loadRecords()]);
    } catch (error) {
      showMessage(error.message, true);
    }
  }

  return { loadAdminRecords, renderAdminEditor };
}
