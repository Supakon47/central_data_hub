const BUILD_VERSION = "2026.10.14.4";
const state = { page: 1, pageSize: 25, total: 0, lastItems: [], currentDetailId: null };
const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"}[char]));
}
function compact(value, fallback = "ไม่ระบุ") { return value ? escapeHtml(value) : fallback; }
function badge(value) { return `<span class="badge${value ? "" : " empty"}">${compact(value)}</span>`; }
function setView(view) {
  document.querySelectorAll(".view").forEach((element) => element.classList.toggle("active", element.id === view));
  document.querySelectorAll(".tab").forEach((element) => element.classList.toggle("active", element.dataset.view === view));
  if (view === "dashboard") loadDashboard();
  if (view === "catalog") loadCatalog();
  if (view === "admin") loadAdmin();
}
function routeFromLocation() {
  const params = new URLSearchParams(window.location.hash.slice(1));
  const recordId = params.get("record");
  if (recordId && /^\d+$/.test(recordId)) return { view: "detail", recordId };
  const view = params.get("view");
  return ["dashboard", "catalog", "admin"].includes(view) ? { view } : { view: "explorer" };
}
function pushRoute(view, recordId = null) {
  const hash = view === "detail" ? `#record=${recordId}` : view === "explorer" ? "" : `#view=${view}`;
  const stateValue = { view, recordId };
  window.history.pushState(stateValue, "", `${window.location.pathname}${hash}`);
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
function filters() {
  const params = new URLSearchParams({ page: state.page, page_size: state.pageSize });
  ["q", "source_sheet", "status_data_check"].forEach((name) => { const value = document.querySelector(`[name="${name}"]`).value.trim(); if (value) params.set(name, value); });
  if ($("#description-filter").checked) params.set("has_description", "true");
  return params;
}
async function loadRecords() {
  const response = await fetch(`/api/records?${filters()}`);
  const data = await response.json(); state.total = data.total; state.lastItems = data.items;
  $("#result-summary").textContent = `พบ ${data.total.toLocaleString()} ระเบียน`;
  $("#records-body").innerHTML = data.items.map((record) => `<tr>
    <td><button class="record-link" data-record-id="${record.id}">${compact(record.registration_no, "ไม่มีเลขทะเบียน")}</button><br><span class="muted">${compact(record.previous_registration_no, "")}</span></td>
    <td><div class="clamp">${compact(record.title_description)}</div></td><td>${compact(record.material)}</td><td>${compact(record.period)}</td>
    <td>${badge(record.status_data_check)}</td><td>${escapeHtml(record.source_sheet)}</td></tr>`).join("") || `<tr><td colspan="6" class="muted">ไม่พบข้อมูลตามเงื่อนไข</td></tr>`;
  $("#page-label").textContent = `หน้า ${state.page} จาก ${Math.max(1, Math.ceil(data.total / state.pageSize))}`;
  $("#previous-page").disabled = state.page === 1; $("#next-page").disabled = state.page * state.pageSize >= data.total;
  document.querySelectorAll("[data-record-id]").forEach((button) => button.addEventListener("click", () => navigate("detail", button.dataset.recordId)));
}
function renderBars(target, items) {
  const max = Math.max(...items.map((item) => item.count), 1);
  $(target).innerHTML = items.map((item) => 
    `<div class="bar-row"><span class="bar-label" title="${escapeHtml(item.label)}">${escapeHtml(item.label)}</span><span class="bar-track"><span class="bar-fill" style="width:${item.count / max * 100}%"></span></span><strong>${item.count.toLocaleString()}</strong></div>`).join("") || `<p class="muted">ยังไม่มีข้อมูล</p>`;
}
async function loadDashboard() {
  const data = await (await fetch("/api/dashboard")).json();
  const metrics = [["ระเบียนทั้งหมด", data.total_records], ["มีเลขทะเบียน", data.with_registration_no], ["มีรายละเอียดรายการ", data.with_description], ["มีลิงก์รูปภาพ", data.with_image_url], ["ทะเบียนที่ซ้ำทั้งหมด", data.duplicate_registration_groups]];
  $("#metrics").innerHTML = metrics.map(([label, value]) => label === "ทะเบียนที่ซ้ำทั้งหมด" ? `<button id="toggle-duplicates" class="metric metric-button" type="button" aria-expanded="false"><span class="label">${label}</span><span class="number">${value.toLocaleString()}</span><span class="metric-action">กดเพื่อดูรายการที่ซ้ำ</span></button>` : `<article class="metric"><span class="label">${label}</span><span class="number">${value.toLocaleString()}</span></article>`).join("");
  renderBars("#chart-sheets", data.by_source_sheet); renderBars("#chart-check", data.by_data_check); renderBars("#chart-photo", data.by_photo); renderBars("#chart-antique", data.by_antique); renderBars("#chart-storage", data.by_storage);
  $("#duplicate-panel").hidden = true;
  $("#toggle-duplicates").addEventListener("click", toggleDuplicateGroups);
}
async function loadDuplicateGroups() {
  $("#duplicate-groups").innerHTML = `<p class="muted">กำลังค้นหารายการที่ซ้ำ…</p>`;
  const duplicates = await (await fetch("/api/duplicates?limit=50")).json();
  const duplicateCaption = duplicates.total_groups > duplicates.groups.length ? `<p class="muted">แสดง ${duplicates.groups.length.toLocaleString()} จาก ${duplicates.total_groups.toLocaleString()} กลุ่ม</p>` : "";
  $("#duplicate-groups").innerHTML = duplicates.groups.length ? `${duplicateCaption}<div class="table-wrap"><table class="duplicate-table"><thead><tr><th>เลขทะเบียน</th><th>จำนวน</th><th>ระเบียนที่ต้องตรวจสอบ</th></tr></thead><tbody>${duplicates.groups.map((group) => `<tr><td>${escapeHtml(group.registration_no)}</td><td>${group.count.toLocaleString()}</td><td>${group.records.map((record) => `<button class="record-link" data-record-id="${record.id}">${compact(record.registration_no)}</button><span class="muted"> — ${escapeHtml(record.source_sheet)} / แถว ${record.source_row_number}</span>`).join("<br>")}</td></tr>`).join("")}</tbody></table></div>` : `<p class="muted">ไม่พบเลขทะเบียนที่ซ้ำกัน</p>`;
  document.querySelectorAll("#duplicate-groups [data-record-id]").forEach((button) => button.addEventListener("click", () => navigate("detail", button.dataset.recordId)));
}
async function toggleDuplicateGroups() {
  const panel = $("#duplicate-panel"); const button = $("#toggle-duplicates"); const opening = panel.hidden;
  panel.hidden = !opening; button.setAttribute("aria-expanded", String(opening));
  if (opening) { await loadDuplicateGroups(); panel.scrollIntoView({ behavior: "smooth", block: "start" }); }
}
function catalogMessage(message = "", isError = false) {
  const target = $("#catalog-message"); target.textContent = message; target.classList.toggle("error", isError);
}
async function loadCatalog() {
  const [catalogResponse, sessionResponse, healthResponse] = await Promise.all([
    fetch("/api/catalog"), fetch("/api/admin/session"), fetch("/api/health"),
  ]);
  const data = await catalogResponse.json(); const adminSession = await sessionResponse.json(); const health = await healthResponse.json();
  const canSyncFromWeb = adminSession.authenticated && health.google_sheets_web_sync_available;
  $("#catalog-list").innerHTML = data.sources.map((source) => {
    const sync = source.last_sync;
    const sheets = (source.configured_sheets || []).filter((sheet) => sheet.is_active).map((sheet) => escapeHtml(sheet.name)).join(", ");
    const syncAction = source.connection_type === "google_sheets" && adminSession.authenticated
      ? `<div class="catalog-actions">${canSyncFromWeb
        ? `<button type="button" data-google-sync-source="${source.id}" data-source-name="${escapeHtml(source.name)}">Sync ข้อมูลล่าสุด</button>`
        : `<span class="muted">ยังไม่ได้ตั้งค่าให้ sync จากหน้าเว็บ</span>`}</div>`
      : "";
    return `<article class="catalog-item"><h3>${escapeHtml(source.name)}</h3><p class="muted">${compact(source.description, "ไม่มีคำอธิบาย")}</p>
      <div class="catalog-meta"><span>ประเภท: ${escapeHtml(source.connection_type)}</span><span>ชั้นข้อมูล: ${escapeHtml(source.classification)}</span><span>ชีตที่เชื่อม: ${sheets || "-"}</span><span>ระเบียน: ${source.record_count.toLocaleString()}</span><span class="issue">ประเด็นที่ยังไม่ปิด: ${source.unresolved_issues.toLocaleString()}</span><span>sync ล่าสุด: ${sync ? escapeHtml(sync.completed_at || sync.started_at) : "ยังไม่เคย"}</span>${sync?.message ? `<span title="${escapeHtml(sync.message)}">${escapeHtml(sync.message)}</span>` : ""}</div>${syncAction}</article>`;
  }).join("") || `<p class="muted">ยังไม่มีแหล่งข้อมูล</p>`;
  document.querySelectorAll("[data-google-sync-source]").forEach((button) => button.addEventListener("click", () => syncGoogleSource(button)));
}
async function syncGoogleSource(button) {
  const sourceName = button.dataset.sourceName || "แหล่งข้อมูลนี้";
  if (!window.confirm(`ยืนยันการดึงข้อมูลล่าสุดจาก ${sourceName}? ระบบจะอ่าน Google Sheets ต้นทางและอัปเดตสำเนากลางเท่านั้น`)) return;
  button.disabled = true; const originalText = button.textContent; button.textContent = "กำลัง Sync…"; catalogMessage("กำลังอ่านข้อมูลจาก Google Sheets…");
  try {
    const result = await adminFetch(`/api/admin/google-sheets/${button.dataset.googleSyncSource}/sync`, { method: "POST", body: "{}" });
    catalogMessage(`Sync สำเร็จ: อ่าน ${result.rows_read.toLocaleString()} แถว · เพิ่ม ${result.inserted.toLocaleString()} · อัปเดต ${result.updated.toLocaleString()} · ลบจากต้นทาง ${result.deleted.toLocaleString()} · ไม่เปลี่ยนแปลง ${result.skipped.toLocaleString()} · ประเด็น ${result.errors.toLocaleString()}`);
    await Promise.all([loadCatalog(), loadRecords(), loadFilterOptions()]);
  } catch (error) {
    catalogMessage(error.message, true); button.disabled = false; button.textContent = originalText;
  }
}
const STATUS_OPTIONS = {
  data_check: ["ตรวจสอบแล้ว", "ยังไม่ตรวจสอบ", "อยู่ในระหว่างการตรวจสอบ"],
  photographed: ["ถ่ายภาพแล้ว", "ยังไม่ถ่ายภาพ", "อยู่ในระหว่างการถ่ายภาพ"],
  antique: ["ลงระบบแล้ว", "ยังไม่ลงระบบ", "อยู่ในระหว่างการลงระบบ"],
  storage: ["ส่งขึ้นห้องคลังแล้ว", "ยังไม่ส่งขึ้นห้องคลัง", "อยู่ในระหว่างการส่งขึ้นห้องคลัง"],
};
const ADMIN_CREATE_REQUIRED = new Set(["registration_no", "title_description"]);
const ADMIN_FIELDS = [
  ["registration_no", "เลขทะเบียน", "text"], ["previous_registration_no", "เลขทะเบียนเดิม", "text"],
  ["title_description", "รายการ", "textarea"], ["dimensions_text", "ขนาด", "textarea"],
  ["material", "ชนิด", "text"], ["period", "อายุสมัย", "textarea"], ["provenance", "ประวัติที่มา", "textarea"],
  ["image_url", "ลิงก์รูปภาพ", "url"], ["status_data_check", "การตรวจสอบข้อมูล", "select", STATUS_OPTIONS.data_check],
  ["status_photographed", "การถ่ายภาพแล้ว", "select", STATUS_OPTIONS.photographed], ["status_antique", "การลงระบบ Antique", "select", STATUS_OPTIONS.antique],
  ["status_storage", "การส่งขึ้นห้องคลัง", "select", STATUS_OPTIONS.storage],
];
function adminMessage(message = "", isError = false) { const target = $("#admin-message"); target.textContent = message; target.classList.toggle("error", isError); }
function googleSourceMessage(message = "", isError = false) { const target = $("#admin-google-source-message"); target.textContent = message; target.classList.toggle("error", isError); }
async function adminFetch(url, options = {}) {
  const response = await fetch(url, { ...options, headers: { "Content-Type": "application/json", ...(options.headers || {}) } });
  if (!response.ok) { const data = await response.json().catch(() => ({})); throw new Error(data.detail || "ไม่สามารถทำรายการได้"); }
  return response.json();
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
async function loadAdminGoogleSources() {
  const [sourceData, healthData] = await Promise.all([adminFetch("/api/admin/google-sheets"), fetch("/api/health").then((response) => response.json())]);
  const canPreview = healthData.google_sheets_web_sync_available;
  const sourcesById = new Map(sourceData.sources.map((source) => [String(source.id), source]));
  $("#admin-google-sources-list").innerHTML = sourceData.sources.map((source) => {
    const tabs = source.sheets.map((sheet) => `${escapeHtml(sheet.name)} <span class="muted">(${escapeHtml(sheet.read_range)})</span>`).join(" · ") || "ยังไม่มีแท็บ";
    return `<article class="catalog-item"><h3>${escapeHtml(source.name)}</h3><p class="muted">${compact(source.description, "ไม่มีคำอธิบาย")}</p><div class="catalog-meta"><span>ผู้รับผิดชอบ: ${compact(source.owner_name)}</span><span>แท็บ: ${tabs}</span></div><div class="catalog-actions"><button type="button" class="secondary" data-source-fill="${source.id}">เพิ่มแท็บในไฟล์นี้</button>${canPreview ? `<button type="button" data-source-preview="${source.id}">ตรวจสอบก่อน Sync</button>` : `<span class="muted">ตั้งค่า key ใน container ก่อนจึงตรวจสอบได้</span>`}</div></article>`;
  }).join("") || `<p class="muted">ยังไม่มี Google Sheets ที่ลงทะเบียน</p>`;
  document.querySelectorAll("[data-source-fill]").forEach((button) => button.addEventListener("click", () => fillGoogleSourceForm(sourcesById.get(button.dataset.sourceFill))));
  document.querySelectorAll("[data-source-preview]").forEach((button) => button.addEventListener("click", () => previewGoogleSource(button)));
}
async function previewGoogleSource(button) {
  button.disabled = true; const originalText = button.textContent; button.textContent = "กำลังตรวจสอบ…"; googleSourceMessage("กำลังอ่าน Google Sheets โดยยังไม่บันทึกข้อมูล…");
  try {
    const result = await adminFetch(`/api/admin/google-sheets/${button.dataset.sourcePreview}/preview`, { method: "POST", body: "{}" });
    const sheets = result.sheets.map((sheet) => `${sheet.sheet}: ${sheet.rows_received.toLocaleString()} แถว${sheet.stable_id_header ? ` · ใช้ ${sheet.stable_id_header}` : " · ยังไม่มี record_id"}${sheet.duplicate_stable_ids ? ` · ID ซ้ำ ${sheet.duplicate_stable_ids}` : ""}`).join(" | ");
    googleSourceMessage(`ตรวจสอบแล้ว: ${sheets || "ไม่พบข้อมูล"}`);
  } catch (error) { googleSourceMessage(error.message, true); }
  finally { button.disabled = false; button.textContent = originalText; }
}
async function saveGoogleSource(event) {
  event.preventDefault(); const form = event.currentTarget; const values = new FormData(form); const payload = {};
  ["source_name", "spreadsheet_id", "sheet_name", "read_range", "owner_name", "description"].forEach((name) => { payload[name] = String(values.get(name) || "").trim() || null; });
  try {
    const result = await adminFetch("/api/admin/google-sheets", { method: "POST", body: JSON.stringify(payload) });
    googleSourceMessage(`บันทึกแล้ว: ${result.source_name} / ${result.sheet_name} — กด “ตรวจสอบก่อน Sync” แล้วจึงไป Sync จาก Data Catalog`);
    form.elements.sheet_name.value = "";
    await Promise.all([loadAdminGoogleSources(), loadCatalog(), loadAudit()]);
  } catch (error) { googleSourceMessage(error.message, true); }
}
function fieldEditor(name, label, type, value, options = [], required = false) {
  const requiredMarker = required ? ` <span class="required" aria-hidden="true">*</span>` : "";
  const requiredAttribute = required ? " required aria-required=\"true\"" : "";
  if (type === "select") {
    const safeOptions = value && !options.includes(value) ? [value, ...options] : options;
    return `<label>${label}${requiredMarker}<select name="${name}"${requiredAttribute}><option value="">ไม่ระบุ</option>${safeOptions.map((option) => `<option value="${escapeHtml(option)}"${option === value ? " selected" : ""}>${escapeHtml(option)}${options.includes(option) ? "" : " (ค่าจากต้นทาง)"}</option>`).join("")}</select></label>`;
  }
  if (type === "textarea") return `<label>${label}${requiredMarker}<textarea name="${name}" rows="3"${requiredAttribute}>${escapeHtml(value || "")}</textarea></label>`;
  return `<label>${label}${requiredMarker}<input name="${name}" type="${type}" value="${escapeHtml(value || "")}"${requiredAttribute} /></label>`;
}
function renderAdminEditor(record = null) {
  const heading = record ? `แก้ไขระเบียน ${escapeHtml(record.registration_no || `#${record.id}`)}` : "เพิ่มระเบียนใหม่";
  const sourceNote = record && record.source_name !== "แก้ไขโดยเจ้าหน้าที่" ? `<p class="warning-text">ระเบียนนี้มาจาก ${escapeHtml(record.source_name || "แหล่งข้อมูล")}; หากมีการ sync แถวต้นทางที่เปลี่ยนแล้ว ข้อมูลที่แก้ในสำเนากลางอาจถูกแทนที่</p>` : "";
  const requiredNote = record ? "" : `<p class="muted">ช่องที่มี <span class="required">*</span> จำเป็นต้องกรอกก่อนสร้างระเบียน</p>`;
  $("#admin-editor").innerHTML = `<h3>${heading}</h3>${requiredNote}${sourceNote}<form id="admin-record-form" class="admin-form"><input name="record_id" type="hidden" value="${record ? record.id : ""}" /><div class="form-grid">${ADMIN_FIELDS.map(([name, label, type, options]) => fieldEditor(name, label, type, record?.[name], options, !record && ADMIN_CREATE_REQUIRED.has(name))).join("")}</div><div class="form-actions"><button type="submit">${record ? "บันทึกการแก้ไข" : "สร้างระเบียน"}</button>${record ? `<button id="admin-cancel-edit" class="secondary" type="button">ยกเลิก</button>` : ""}</div></form>`;
  $("#admin-record-form").addEventListener("submit", saveAdminRecord);
  $("#admin-cancel-edit")?.addEventListener("click", () => renderAdminEditor());
}
async function loadAdminRecords() {
  const query = $("#admin-query").value.trim();
  const sourceSheet = $("#admin-sheet-filter").value;
  const params = new URLSearchParams({ page: "1", page_size: "20" }); if (query) params.set("q", query); if (sourceSheet) params.set("source_sheet", sourceSheet);
  const data = await (await fetch(`/api/records?${params}`)).json();
  $("#admin-record-summary").textContent = data.total > data.items.length ? `พบ ${data.total.toLocaleString()} ระเบียน · แสดง 20 รายการแรก กรุณาค้นหาหรือเลือกชีตเพื่อดูเฉพาะรายการที่ต้องการ` : `พบ ${data.total.toLocaleString()} ระเบียน`;
  $("#admin-records-body").innerHTML = data.items.map((record) => `<tr><td>${compact(record.registration_no)}</td><td><div class="clamp">${compact(record.title_description)}</div></td><td>${escapeHtml(record.source_name || "")}<br><span class="muted">${escapeHtml(record.source_sheet)}</span></td><td class="actions"><button class="small secondary" data-admin-edit="${record.id}">แก้ไข</button><button class="small danger" data-admin-delete="${record.id}">ลบ</button></td></tr>`).join("") || `<tr><td colspan="4" class="muted">ไม่พบระเบียน</td></tr>`;
  document.querySelectorAll("[data-admin-edit]").forEach((button) => button.addEventListener("click", async () => { const record = await (await fetch(`/api/records/${button.dataset.adminEdit}`)).json(); renderAdminEditor(record); window.scrollTo({ top: 0, behavior: "smooth" }); }));
  document.querySelectorAll("[data-admin-delete]").forEach((button) => button.addEventListener("click", () => deleteAdminRecord(button.dataset.adminDelete)));
}
async function loadAdminSheetOptions() {
  const select = $("#admin-sheet-filter"); const selected = select.value;
  const data = await (await fetch("/api/dashboard")).json();
  select.innerHTML = `<option value="">ทุกชีต</option>${data.by_source_sheet.map((item) => `<option value="${escapeHtml(item.label)}">${escapeHtml(item.label)} (${item.count.toLocaleString()})</option>`).join("")}`;
  select.value = [...select.options].some((option) => option.value === selected) ? selected : "";
}
async function loadAudit() {
  const data = await adminFetch("/api/admin/audit");
  $("#audit-list").innerHTML = data.items.map((item) => {
    const entity = item.entity_type === "data_source" ? "แหล่งข้อมูล" : "ระเบียน";
    return `<div class="audit-item"><strong>${escapeHtml(item.action)}</strong> ${entity} #${escapeHtml(item.entity_id)}<br><span class="muted">${new Date(item.created_at).toLocaleString("th-TH")}</span></div>`;
  }).join("") || `<p class="muted">ยังไม่มีประวัติการแก้ไข</p>`;
}
async function loadAdmin() {
  const session = await (await fetch("/api/admin/session")).json();
  $("#admin-login").hidden = session.authenticated || !session.configured;
  $("#admin-content").hidden = !session.authenticated;
  if (!session.configured) { adminMessage("ผู้ดูแลยังไม่ได้ตั้งรหัสผ่านในไฟล์ .env", true); return; }
  if (!session.authenticated) { adminMessage("", false); return; }
  adminMessage("ปลดล็อกหน้าจัดการแล้ว", false); renderAdminEditor(); await loadAdminSheetOptions(); await Promise.all([loadAdminRecords(), loadAudit(), loadAdminGoogleSources()]);
}
async function saveAdminRecord(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget); const recordId = form.get("record_id"); const payload = {};
  ADMIN_FIELDS.forEach(([name]) => { payload[name] = String(form.get(name) || "").trim() || null; });
  try {
    await adminFetch(recordId ? `/api/admin/records/${recordId}` : "/api/admin/records", { method: recordId ? "PATCH" : "POST", body: JSON.stringify(payload) });
    adminMessage(recordId ? "บันทึกการแก้ไขแล้ว" : "เพิ่มระเบียนใหม่แล้ว"); renderAdminEditor(); await Promise.all([loadAdminRecords(), loadAudit(), loadRecords()]);
  } catch (error) { adminMessage(error.message, true); }
}
async function deleteAdminRecord(recordId) {
  if (!window.confirm("ยืนยันการลบระเบียนนี้จากสำเนากลาง? การ sync จากต้นทางอาจนำระเบียนกลับมาอีก")) return;
  try { await adminFetch(`/api/admin/records/${recordId}`, { method: "DELETE" }); adminMessage("ลบระเบียนจากสำเนากลางแล้ว"); renderAdminEditor(); await Promise.all([loadAdminRecords(), loadAudit(), loadRecords()]); }
  catch (error) { adminMessage(error.message, true); }
}
async function loadDetail(recordId, updateHistory = true) {
  if (updateHistory) pushRoute("detail", recordId);
  const record = await (await fetch(`/api/records/${recordId}`)).json();
  state.currentDetailId = recordId;
  setView("detail");
  const fields = [["เลขทะเบียน", record.registration_no], ["เลขทะเบียนเดิม", record.previous_registration_no], ["รายการ", record.title_description], ["ขนาด", record.dimensions_text], ["ชนิด", record.material], ["อายุสมัย", record.period], ["ประวัติที่มา", record.provenance], ["การตรวจสอบข้อมูล", record.status_data_check], ["การถ่ายภาพ", record.status_photographed], ["การลงระบบ Antique", record.status_antique], ["การส่งขึ้นห้องคลัง", record.status_storage], ["แหล่งข้อมูล", `${record.source_name || ""} / ${record.source_sheet} / แถว ${record.source_row_number}`]];
  const rawRows = Object.entries(record.raw_data || {}).map(([key, value]) => `<tr><th>${escapeHtml(key)}</th><td>${compact(value, "")}</td></tr>`).join("");
  const duplicates = record.duplicate_candidates?.length ? `<ul>${record.duplicate_candidates.map((item) => `<li><button class="record-link" data-record-id="${item.id}">${compact(item.registration_no)}</button> — ${escapeHtml(item.source_sheet)}</li>`).join("")}</ul>` : `<p class="muted">ไม่พบเลขทะเบียนเดียวกันจากแหล่งอื่นในสำเนากลาง</p>`;
  const imageSection = record.image_url ? `<section class="detail-image"><h3>รูปภาพ</h3><a href="${escapeHtml(record.image_url)}" target="_blank" rel="noreferrer"><img src="${escapeHtml(record.image_url)}" alt="ภาพประกอบของ ${compact(record.registration_no, "ระเบียน")}" loading="lazy" /></a><p class="muted">คลิกภาพเพื่อเปิดขนาดเต็ม</p></section>` : record.status_photographed ? `<section class="image-unavailable"><h3>รูปภาพ</h3><p class="muted">ระบุว่าถ่ายภาพแล้ว แต่ยังไม่มีลิงก์รูปภาพจากแหล่งข้อมูลให้แสดง</p></section>` : "";
  const sourceDetails = rawRows ? `<details class="source-details detail-section"><summary>ดูข้อมูลต้นทางที่นำเข้า</summary><p class="muted">ข้อมูลนี้เก็บไว้เพื่อการตรวจสอบย้อนกลับจากชีตต้นทาง</p><div class="table-wrap"><table class="raw-table"><tbody>${rawRows}</tbody></table></div></details>` : "";
  $("#detail-content").innerHTML = `<article class="detail-card"><h2>${compact(record.registration_no, "ไม่มีเลขทะเบียน")}</h2><div class="detail-layout"><dl class="detail-grid detail-section">${fields.map(([label, value]) => `<dt>${label}</dt><dd>${compact(value)}</dd>`).join("")}</dl>${imageSection}</div>${sourceDetails}<div class="detail-section"><h3>ระเบียนที่อาจซ้ำ</h3><p class="muted">แสดงจากเลขทะเบียนเดียวกันเท่านั้น และไม่ยืนยันว่าเป็นข้อมูลชิ้นเดียวกัน</p>${duplicates}</div></article>`;
  document.querySelectorAll("#detail-content [data-record-id]").forEach((button) => button.addEventListener("click", () => navigate("detail", button.dataset.recordId)));
}
async function loadFilterOptions() {
  const data = await (await fetch("/api/dashboard")).json();
  const setOptions = (target, items) => { $(target).insertAdjacentHTML("beforeend", items.map((item) => `<option value="${escapeHtml(item.label)}">${escapeHtml(item.label)} (${item.count.toLocaleString()})</option>`).join("")); };
  setOptions("#sheet-filter", data.by_source_sheet); setOptions("#check-filter", data.by_data_check.filter((item) => item.label !== "ไม่ระบุ"));
}
async function initialise() {
  const health = await (await fetch("/api/health")).json(); $("#freshness").textContent = health.environment === "development" ? `โหมดทดลองในเครื่อง · build ${BUILD_VERSION}` : `ระบบพร้อมใช้งาน · build ${BUILD_VERSION}`;
  if (!window.history.state) window.history.replaceState({ view: "explorer" }, "", window.location.href);
  await loadFilterOptions(); await loadRecords(); await renderRoute();
}
document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => navigate(button.dataset.view)));
$("#search-form").addEventListener("submit", (event) => { event.preventDefault(); state.page = 1; loadRecords(); });
$("#previous-page").addEventListener("click", () => { state.page -= 1; loadRecords(); }); $("#next-page").addEventListener("click", () => { state.page += 1; loadRecords(); });
$("[data-back]").addEventListener("click", () => navigate("explorer"));
$("#admin-login-form").addEventListener("submit", async (event) => { event.preventDefault(); try { await adminFetch("/api/admin/login", { method: "POST", body: JSON.stringify({ password: $("#admin-password").value }) }); $("#admin-password").value = ""; await loadAdmin(); } catch (error) { adminMessage(error.message, true); } });
$("#admin-new-record").addEventListener("click", () => renderAdminEditor());
$("#admin-google-source-form").addEventListener("submit", saveGoogleSource);
$("#admin-google-source-reset").addEventListener("click", () => { $("#admin-google-source-form").reset(); googleSourceMessage(); });
$("#admin-search-form").addEventListener("submit", (event) => { event.preventDefault(); $("#admin-records-panel").open = true; loadAdminRecords(); });
$("#admin-logout").addEventListener("click", async () => { await adminFetch("/api/admin/logout", { method: "POST", body: "{}" }); await loadAdmin(); });
window.addEventListener("popstate", () => renderRoute());
initialise().catch((error) => { $("#freshness").textContent = `เกิดข้อผิดพลาด: ${error.message}`; });
