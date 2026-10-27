const BUILD_VERSION = "2026.10.27.1";
const state = {
  page: 1,
  pageSize: 25,
  total: 0,
  lastItems: [],
  currentDetailId: null,
  imageIntakeSources: [],
};
const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
  return String(value ?? "").replace(
    /[&<>'"]/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[
        char
      ],
  );
}
function compact(value, fallback = "ไม่ระบุ") {
  return value ? escapeHtml(value) : fallback;
}
function badge(value) {
  return `<span class="badge${value ? "" : " empty"}">${compact(value)}</span>`;
}

function bindRecordLinks(selector = "[data-record-id]") {
  document.querySelectorAll(selector).forEach((button) => {
    button.addEventListener("click", () => {
      navigate("detail", button.dataset.recordId);
    });
  });
}

function renderRecordRow(record) {
  return `<tr>
    <td>
      <button class="record-link" data-record-id="${record.id}">
        ${compact(record.registration_no, "ไม่มีเลขทะเบียน")}
      </button>
      <br>
      <span class="muted">${compact(record.previous_registration_no, "")}</span>
    </td>
    <td><div class="clamp">${compact(record.title_description)}</div></td>
    <td>${compact(record.material)}</td>
    <td>${compact(record.period)}</td>
    <td>${badge(record.status_data_check)}</td>
    <td>${escapeHtml(record.source_sheet)}</td>
  </tr>`;
}

function renderBar(item, max) {
  const width = (item.count / max) * 100;
  return `<div class="bar-row">
    <span class="bar-label" title="${escapeHtml(item.label)}">${escapeHtml(item.label)}</span>
    <span class="bar-track"><span class="bar-fill" style="width:${width}%"></span></span>
    <strong>${item.count.toLocaleString()}</strong>
  </div>`;
}

function renderMetric(label, value) {
  if (label === "ทะเบียนที่ซ้ำทั้งหมด") {
    return `<button id="toggle-duplicates" class="metric metric-button" type="button" aria-expanded="false">
      <span class="label">${label}</span>
      <span class="number">${value.toLocaleString()}</span>
      <span class="metric-action">กดเพื่อดูรายการที่ซ้ำ</span>
    </button>`;
  }
  return `<article class="metric">
    <span class="label">${label}</span>
    <span class="number">${value.toLocaleString()}</span>
  </article>`;
}

function renderDuplicateGroup(group) {
  const records = group.records
    .map(
      (record) => `<button class="record-link" data-record-id="${record.id}">
        ${compact(record.registration_no)}
      </button>
      <span class="muted"> — ${escapeHtml(record.source_sheet)} / แถว ${record.source_row_number}</span>`,
    )
    .join("<br>");
  return `<tr>
    <td>${escapeHtml(group.registration_no)}</td>
    <td>${group.count.toLocaleString()}</td>
    <td>${records}</td>
  </tr>`;
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
  if (view === "dashboard") loadDashboard();
  if (view === "catalog") loadCatalog();
  if (view === "quality") loadDataQuality();
  if (view === "admin") loadAdmin();
}
function routeFromLocation() {
  const params = new URLSearchParams(window.location.hash.slice(1));
  const recordId = params.get("record");
  if (recordId && /^\d+$/.test(recordId)) return { view: "detail", recordId };
  const view = params.get("view");
  return ["dashboard", "catalog", "quality", "admin"].includes(view)
    ? { view }
    : { view: "explorer" };
}
function pushRoute(view, recordId = null) {
  const hash =
    view === "detail"
      ? `#record=${recordId}`
      : view === "explorer"
        ? ""
        : `#view=${view}`;
  const stateValue = { view, recordId };
  window.history.pushState(
    stateValue,
    "",
    `${window.location.pathname}${hash}`,
  );
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
  const params = new URLSearchParams({
    page: state.page,
    page_size: state.pageSize,
  });
  ["q", "source_sheet", "status_data_check"].forEach((name) => {
    const value = document.querySelector(`[name="${name}"]`).value.trim();
    if (value) params.set(name, value);
  });
  if ($("#description-filter").checked) params.set("has_description", "true");
  return params;
}
async function loadRecords() {
  const response = await fetch(`/api/records?${filters()}`);
  const data = await response.json();
  state.total = data.total;
  state.lastItems = data.items;
  $("#result-summary").textContent =
    `พบ ${data.total.toLocaleString()} ระเบียน`;
  $("#records-body").innerHTML =
    data.items.map(renderRecordRow).join("") ||
    `<tr><td colspan="6" class="muted">ไม่พบข้อมูลตามเงื่อนไข</td></tr>`;
  $("#page-label").textContent =
    `หน้า ${state.page} จาก ${Math.max(1, Math.ceil(data.total / state.pageSize))}`;
  $("#previous-page").disabled = state.page === 1;
  $("#next-page").disabled = state.page * state.pageSize >= data.total;
  bindRecordLinks();
}
function renderBars(target, items) {
  const max = Math.max(...items.map((item) => item.count), 1);
  $(target).innerHTML =
    items.map((item) => renderBar(item, max)).join("") ||
    `<p class="muted">ยังไม่มีข้อมูล</p>`;
}
async function loadDashboard() {
  const data = await (await fetch("/api/dashboard")).json();
  const metrics = [
    ["ระเบียนทั้งหมด", data.total_records],
    ["มีเลขทะเบียน", data.with_registration_no],
    ["มีรายละเอียดรายการ", data.with_description],
    ["มีลิงก์รูปภาพ", data.with_image_url],
    ["ทะเบียนที่ซ้ำทั้งหมด", data.duplicate_registration_groups],
  ];
  $("#metrics").innerHTML = metrics
    .map(([label, value]) => renderMetric(label, value))
    .join("");
  renderBars("#chart-sheets", data.by_source_sheet);
  renderBars("#chart-check", data.by_data_check);
  renderBars("#chart-photo", data.by_photo);
  renderBars("#chart-antique", data.by_antique);
  renderBars("#chart-storage", data.by_storage);
  $("#duplicate-panel").hidden = true;
  $("#toggle-duplicates").addEventListener("click", toggleDuplicateGroups);
}
async function loadDuplicateGroups() {
  $("#duplicate-groups").innerHTML =
    `<p class="muted">กำลังค้นหารายการที่ซ้ำ…</p>`;
  const duplicates = await (await fetch("/api/duplicates?limit=50")).json();
  const duplicateCaption =
    duplicates.total_groups > duplicates.groups.length
      ? `<p class="muted">แสดง ${duplicates.groups.length.toLocaleString()} จาก ${duplicates.total_groups.toLocaleString()} กลุ่ม</p>`
      : "";
  const duplicateTable = duplicates.groups.length
    ? `<div class="table-wrap">
      <table class="duplicate-table">
        <thead><tr><th>เลขทะเบียน</th><th>จำนวน</th><th>ระเบียนที่ต้องตรวจสอบ</th></tr></thead>
        <tbody>${duplicates.groups.map(renderDuplicateGroup).join("")}</tbody>
      </table>
    </div>`
    : `<p class="muted">ไม่พบเลขทะเบียนที่ซ้ำกัน</p>`;
  $("#duplicate-groups").innerHTML = `${duplicateCaption}${duplicateTable}`;
  bindRecordLinks("#duplicate-groups [data-record-id]");
}
async function toggleDuplicateGroups() {
  const panel = $("#duplicate-panel");
  const button = $("#toggle-duplicates");
  const opening = panel.hidden;
  panel.hidden = !opening;
  button.setAttribute("aria-expanded", String(opening));
  if (opening) {
    await loadDuplicateGroups();
    panel.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}
function catalogMessage(message = "", isError = false) {
  const target = $("#catalog-message");
  target.textContent = message;
  target.classList.toggle("error", isError);
}

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
      ${bridgeStatus}${syncMessage}
    </div>
    ${renderCatalogActions(source, bridge, canSyncFromWeb, isAdmin)}
  </article>`;
}

function bindCatalogActions() {
  document.querySelectorAll("[data-google-sync-source]").forEach((button) => {
    button.addEventListener("click", () => syncGoogleSource(button));
  });
  document
    .querySelectorAll("[data-image-bridge-sync-source]")
    .forEach((button) => {
      button.addEventListener("click", () => syncImageBridge(button));
    });
  document.querySelectorAll("[data-clear-source]").forEach((button) => {
    button.addEventListener("click", () => clearCentralData(button));
  });
  document.querySelectorAll("[data-delete-google-source]").forEach((button) => {
    button.addEventListener("click", () => deleteGoogleSource(button));
  });
}

async function loadCatalog() {
  const [catalogResponse, sessionResponse, healthResponse] = await Promise.all([
    fetch("/api/catalog"),
    fetch("/api/admin/session"),
    fetch("/api/health"),
  ]);
  const data = await catalogResponse.json();
  const adminSession = await sessionResponse.json();
  const health = await healthResponse.json();
  const canSyncFromWeb =
    adminSession.authenticated && health.google_sheets_web_sync_available;
  $("#catalog-list").innerHTML =
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
  )
    return;
  button.disabled = true;
  const originalText = button.textContent;
  button.textContent = "กำลัง Sync…";
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
    button.disabled = false;
    button.textContent = originalText;
  }
}
async function syncImageBridge(button) {
  const sourceName = button.dataset.sourceName || "แหล่งข้อมูลนี้";
  if (
    !window.confirm(
      `ยืนยันการดึงรูปภาพจาก Image Bridge ของ ${sourceName}? ระบบจะอ่านสำเนารูปจาก Google Drive และไม่แก้ Google Sheet ต้นทาง`,
    )
  )
    return;
  button.disabled = true;
  const originalText = button.textContent;
  button.textContent = "กำลังดึงรูป…";
  catalogMessage("กำลังอ่านรายการรูปจาก Google Drive…");
  try {
    const result = await adminFetch(
      `/api/admin/google-sheets/${button.dataset.imageBridgeSyncSource}/image-bridge/sync`,
      { method: "POST", body: "{}" },
    );
    catalogMessage(
      `Sync รูปสำเร็จ: จับคู่ ${result.matched_records.toLocaleString()} ระเบียน · รูปใหม่/เปลี่ยน ${result.changed_images.toLocaleString()} · เอารูปเก่าออก ${result.removed_images.toLocaleString()} · จับคู่ไม่พบ ${result.unmatched_count.toLocaleString()} · ต้องตรวจ ${result.invalid_count.toLocaleString()}`,
      Boolean(result.unmatched_count || result.invalid_count),
    );
    await Promise.all([loadCatalog(), loadAudit()]);
  } catch (error) {
    catalogMessage(error.message, true);
    button.disabled = false;
    button.textContent = originalText;
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
  )
    return;
  button.disabled = true;
  const originalText = button.textContent;
  button.textContent = "กำลังล้าง…";
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
    button.disabled = false;
    button.textContent = originalText;
  }
}
async function deleteGoogleSource(button) {
  const sourceName = button.dataset.sourceName || "";
  if (
    !window.confirm(
      `ยืนยันว่าต้องการลบการเชื่อมต่อ “${sourceName}” ใช่หรือไม่?`,
    )
  )
    return;
  button.disabled = true;
  const originalText = button.textContent;
  button.textContent = "กำลังลบ…";
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
    button.disabled = false;
    button.textContent = originalText;
  }
}

function renderSelectOptions(items, selectedValue = "") {
  return items
    .map(
      (item) =>
        `<option value="${item.id}"${String(item.id) === String(selectedValue) ? " selected" : ""}>${escapeHtml(item.name)}</option>`,
    )
    .join("");
}

function renderQualityIssue(issue, isAdmin) {
  const location = `${escapeHtml(issue.source_name)}<br>
    <span class="muted">${escapeHtml(issue.source_sheet || "-")}${issue.source_row_number ? ` / แถว ${issue.source_row_number}` : ""}</span>`;
  const record = issue.record_id
    ? `<button class="record-link" data-record-id="${issue.record_id}">
        ${compact(issue.registration_no, `ระเบียน #${issue.record_id}`)}
      </button><br>
      <span class="muted clamp">${compact(issue.title_description, "")}</span>`
    : `<span class="muted">ไม่มีระเบียนที่เชื่อมอยู่</span>`;
  const state = issue.is_resolved
    ? `<span class="badge">ปิดแล้ว</span>${isAdmin ? `<button class="small secondary" data-quality-reopen="${issue.id}">เปิดอีกครั้ง</button>` : ""}`
    : isAdmin
      ? `<button class="small" data-quality-resolve="${issue.id}">ทำเครื่องหมายว่าตรวจแล้ว</button>`
      : `<span class="badge empty">รอตรวจสอบ</span>`;
  const severityLabel = issue.severity === "error" ? "ต้องแก้ไข" : "ควรตรวจสอบ";
  return `<tr>
    <td><span class="quality-severity ${escapeHtml(issue.severity)}">${severityLabel}</span></td>
    <td><strong>${escapeHtml(issue.code)}</strong><br>${escapeHtml(issue.message)}</td>
    <td>${location}</td>
    <td>${record}</td>
    <td class="quality-state">${state}</td>
  </tr>`;
}

function bindQualityActions() {
  bindRecordLinks("#quality-body [data-record-id]");
  document.querySelectorAll("[data-quality-resolve]").forEach((button) => {
    button.addEventListener("click", () => {
      updateQualityIssue(button.dataset.qualityResolve, true);
    });
  });
  document.querySelectorAll("[data-quality-reopen]").forEach((button) => {
    button.addEventListener("click", () => {
      updateQualityIssue(button.dataset.qualityReopen, false);
    });
  });
}

async function loadDataQuality() {
  const sourceSelect = $("#quality-source-filter");
  const selectedSource = sourceSelect.value;
  const params = new URLSearchParams({ page: "1", page_size: "100" });
  if (selectedSource) params.set("source_id", selectedSource);
  const severity = $("#quality-severity-filter").value;
  if (severity) params.set("severity", severity);
  if ($("#quality-include-resolved").checked)
    params.set("include_resolved", "true");
  const [issuesResponse, catalogResponse, sessionResponse] = await Promise.all([
    fetch(`/api/data-quality/issues?${params}`),
    fetch("/api/catalog"),
    fetch("/api/admin/session"),
  ]);
  if (!issuesResponse.ok)
    throw new Error("ไม่สามารถโหลดประเด็นคุณภาพข้อมูลได้");
  const data = await issuesResponse.json();
  const catalog = await catalogResponse.json();
  const adminSession = await sessionResponse.json();
  const sourceStillExists = catalog.sources.some(
    (source) => String(source.id) === selectedSource,
  );
  sourceSelect.innerHTML = `<option value="">ทุกแหล่งข้อมูล</option>${renderSelectOptions(catalog.sources, sourceStillExists ? selectedSource : "")}`;
  const metrics = [
    ["ประเด็นที่แสดง", data.total],
    ["ต้องแก้ไข", data.summary.errors],
    ["ควรตรวจสอบ", data.summary.warnings],
  ];
  $("#quality-metrics").innerHTML = metrics
    .map(([label, value]) => renderMetric(label, value))
    .join("");
  $("#quality-summary").textContent =
    data.total > data.items.length
      ? `พบ ${data.total.toLocaleString()} ประเด็น · แสดง 100 รายการล่าสุด`
      : `พบ ${data.total.toLocaleString()} ประเด็น`;
  $("#quality-body").innerHTML =
    data.items
      .map((issue) => renderQualityIssue(issue, adminSession.authenticated))
      .join("") ||
    `<tr><td colspan="5" class="muted">ไม่พบประเด็นตามเงื่อนไข</td></tr>`;
  bindQualityActions();
}
async function updateQualityIssue(issueId, isResolved) {
  try {
    await adminFetch(`/api/admin/data-quality/issues/${issueId}`, {
      method: "PATCH",
      body: JSON.stringify({ is_resolved: isResolved }),
    });
    await Promise.all([loadDataQuality(), loadCatalog(), loadAudit()]);
  } catch (error) {
    window.alert(error.message);
  }
}
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
const ADMIN_CREATE_REQUIRED = new Set(["registration_no", "title_description"]);
const ADMIN_FIELDS = [
  ["registration_no", "เลขทะเบียน", "text"],
  ["previous_registration_no", "เลขทะเบียนเดิม", "text"],
  ["title_description", "รายการ", "textarea"],
  ["dimensions_text", "ขนาด", "textarea"],
  ["material", "ชนิด", "text"],
  ["period", "อายุสมัย", "textarea"],
  ["provenance", "ประวัติที่มา", "textarea"],
  ["image_url", "ลิงก์รูปภาพ", "url"],
  [
    "status_data_check",
    "การตรวจสอบข้อมูล",
    "select",
    STATUS_OPTIONS.data_check,
  ],
  [
    "status_photographed",
    "การถ่ายภาพแล้ว",
    "select",
    STATUS_OPTIONS.photographed,
  ],
  ["status_antique", "การลงระบบ Antique", "select", STATUS_OPTIONS.antique],
  ["status_storage", "การส่งขึ้นห้องคลัง", "select", STATUS_OPTIONS.storage],
];
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
function imageIntakeMessage(message = "", isError = false) {
  const target = $("#admin-image-intake-message");
  target.textContent = message;
  target.classList.toggle("error", isError);
}
async function adminFetch(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "ไม่สามารถทำรายการได้");
  }
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

function renderGoogleSourceTabs(sheets) {
  return (
    sheets
      .map(
        (sheet) =>
          `${escapeHtml(sheet.name)} <span class="muted">(${escapeHtml(sheet.read_range)})</span>`,
      )
      .join(" · ") || "ยังไม่มีแท็บ"
  );
}

function renderImageBridgeControls(source, bridge, canPreview) {
  const bridgeSync =
    bridge.configured && canPreview
      ? `<button type="button" data-image-bridge-sync-source="${source.id}" data-source-name="${escapeHtml(source.name)}">ดึงรูปภาพตอนนี้</button>`
      : "";
  return `<div class="image-bridge-config">
    <strong>Image Bridge สำหรับภาพในเซลล์</strong>
    <p class="muted">วาง Folder ID ของโฟลเดอร์ที่ Apps Script สร้างรูปและ manifest แล้วบันทึกหนึ่งครั้ง</p>
    <label>Google Drive Folder ID
      <input
        data-image-bridge-folder="${source.id}"
        value="${escapeHtml(bridge.drive_folder_id || "")}"
        placeholder="ข้อความหลัง folders/ ใน URL"
      >
    </label>
    <div class="catalog-actions">
      <button type="button" class="secondary" data-image-bridge-save="${source.id}">บันทึก Image Bridge</button>
      ${bridgeSync}
    </div>
  </div>`;
}

function renderAdminGoogleSource(source, canPreview) {
  const bridge = source.image_bridge || { configured: false };
  const previewAction = canPreview
    ? `<button type="button" data-source-preview="${source.id}">ตรวจสอบก่อน Sync</button>`
    : `<span class="muted">ตั้งค่า key ใน container ก่อนจึงตรวจสอบได้</span>`;
  return `<article class="catalog-item">
    <h3>${escapeHtml(source.name)}</h3>
    <p class="muted">${compact(source.description, "ไม่มีคำอธิบาย")}</p>
    <div class="catalog-meta">
      <span>ผู้รับผิดชอบ: ${compact(source.owner_name)}</span>
      <span>แท็บ: ${renderGoogleSourceTabs(source.sheets)}</span>
    </div>
    <div class="catalog-actions">
      <button type="button" class="secondary" data-source-fill="${source.id}">เพิ่มแท็บในไฟล์นี้</button>
      ${previewAction}
    </div>
    ${renderImageBridgeControls(source, bridge, canPreview)}
  </article>`;
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
  document
    .querySelectorAll("[data-image-bridge-sync-source]")
    .forEach((button) => {
      button.addEventListener("click", () => syncImageBridge(button));
    });
}

async function loadAdminGoogleSources() {
  const [sourceData, healthData] = await Promise.all([
    adminFetch("/api/admin/google-sheets"),
    fetch("/api/health").then((response) => response.json()),
  ]);
  const canPreview = healthData.google_sheets_web_sync_available;
  const sourcesById = new Map(
    sourceData.sources.map((source) => [String(source.id), source]),
  );
  $("#admin-google-sources-list").innerHTML =
    sourceData.sources
      .map((source) => renderAdminGoogleSource(source, canPreview))
      .join("") || `<p class="muted">ยังไม่มี Google Sheets ที่ลงทะเบียน</p>`;
  bindAdminGoogleSourceActions(sourcesById);
}
async function saveImageBridge(button) {
  const sourceId = button.dataset.imageBridgeSave;
  const folderId = document
    .querySelector(`[data-image-bridge-folder="${sourceId}"]`)
    .value.trim();
  if (!folderId) {
    googleSourceMessage("กรุณาวาง Google Drive Folder ID ก่อน", true);
    return;
  }
  button.disabled = true;
  try {
    await adminFetch(`/api/admin/google-sheets/${sourceId}/image-bridge`, {
      method: "PUT",
      body: JSON.stringify({ drive_folder_id: folderId }),
    });
    googleSourceMessage(
      "บันทึก Image Bridge แล้ว — เมื่อ Apps Script สร้าง manifest แล้วจึงกดดึงรูปภาพได้",
    );
    await Promise.all([loadAdminGoogleSources(), loadCatalog(), loadAudit()]);
  } catch (error) {
    googleSourceMessage(error.message, true);
    button.disabled = false;
  }
}
function renderImageIntakeSheets() {
  const sourceSelect = $("#admin-image-intake-source");
  const sheetSelect = $("#admin-image-intake-sheet");
  const source = state.imageIntakeSources.find(
    (item) => String(item.id) === sourceSelect.value,
  );
  sheetSelect.innerHTML = `<option value="">เลือกชีต</option>${(source?.sheets || []).map((sheet) => `<option value="${escapeHtml(sheet.name)}">${escapeHtml(sheet.name)} (${sheet.record_count.toLocaleString()} ระเบียน)</option>`).join("")}`;
  sheetSelect.disabled = !source;
}
async function loadImageIntakeSources() {
  const sourceSelect = $("#admin-image-intake-source");
  const selected = sourceSelect.value;
  const data = await adminFetch("/api/admin/image-intake/sources");
  state.imageIntakeSources = data.sources;
  sourceSelect.innerHTML = `<option value="">เลือกแหล่งข้อมูล</option>${data.sources.map((source) => `<option value="${source.id}">${escapeHtml(source.name)}</option>`).join("")}`;
  sourceSelect.value = data.sources.some(
    (source) => String(source.id) === selected,
  )
    ? selected
    : "";
  renderImageIntakeSheets();
  imageIntakeMessage(
    data.sources.length ? "" : "ยังไม่พบชีตที่มี record_id สำหรับจับคู่ภาพ",
  );
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
function fieldEditor(name, label, type, value, options = [], required = false) {
  const requiredMarker = required
    ? ` <span class="required" aria-hidden="true">*</span>`
    : "";
  const requiredAttribute = required ? ' required aria-required="true"' : "";
  if (type === "select") {
    const safeOptions =
      value && !options.includes(value) ? [value, ...options] : options;
    const selectOptions = safeOptions
      .map((option) => {
        const selected = option === value ? " selected" : "";
        const originalValueNote = options.includes(option)
          ? ""
          : " (ค่าจากต้นทาง)";
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

function renderAdminImageUpload(record) {
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

function renderAdminRecordForm(record) {
  const fields = ADMIN_FIELDS.map(([name, label, type, options]) => {
    const required = !record && ADMIN_CREATE_REQUIRED.has(name);
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
    ${renderAdminRecordForm(record)}
    ${renderAdminImageUpload(record)}`;
  $("#admin-record-form").addEventListener("submit", saveAdminRecord);
  $("#admin-cancel-edit")?.addEventListener("click", () => renderAdminEditor());
  $("#admin-image-upload")?.addEventListener("click", () =>
    uploadAdminImage(record.id),
  );
}
async function loadAdminRecords() {
  const query = $("#admin-query").value.trim();
  const sourceSheet = $("#admin-sheet-filter").value;
  const params = new URLSearchParams({ page: "1", page_size: "20" });
  if (query) params.set("q", query);
  if (sourceSheet) params.set("source_sheet", sourceSheet);
  const data = await (await fetch(`/api/records?${params}`)).json();
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
  document.querySelectorAll("[data-admin-edit]").forEach((button) =>
    button.addEventListener("click", async () => {
      const record = await (
        await fetch(`/api/records/${button.dataset.adminEdit}`)
      ).json();
      renderAdminEditor(record);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }),
  );
  document
    .querySelectorAll("[data-admin-delete]")
    .forEach((button) =>
      button.addEventListener("click", () =>
        deleteAdminRecord(button.dataset.adminDelete),
      ),
    );
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
  const data = await adminFetch("/api/admin/audit");
  $("#audit-list").innerHTML =
    data.items
      .map((item) => {
        const entity =
          item.entity_type === "data_source"
            ? "แหล่งข้อมูล"
            : item.entity_type === "data_quality_issue"
              ? "ประเด็นคุณภาพข้อมูล"
              : "ระเบียน";
        return `<div class="audit-item"><strong>${escapeHtml(item.action)}</strong> ${entity} #${escapeHtml(item.entity_id)}<br><span class="muted">${new Date(item.created_at).toLocaleString("th-TH")}</span></div>`;
      })
      .join("") || `<p class="muted">ยังไม่มีประวัติการแก้ไข</p>`;
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
    loadImageIntakeSources(),
  ]);
}
async function saveAdminRecord(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const recordId = form.get("record_id");
  const payload = {};
  ADMIN_FIELDS.forEach(([name]) => {
    payload[name] = String(form.get(name) || "").trim() || null;
  });
  try {
    await adminFetch(
      recordId ? `/api/admin/records/${recordId}` : "/api/admin/records",
      { method: recordId ? "PATCH" : "POST", body: JSON.stringify(payload) },
    );
    adminMessage(recordId ? "บันทึกการแก้ไขแล้ว" : "เพิ่มระเบียนใหม่แล้ว");
    renderAdminEditor();
    await Promise.all([loadAdminRecords(), loadAudit(), loadRecords()]);
  } catch (error) {
    adminMessage(error.message, true);
  }
}
async function uploadAdminImage(recordId) {
  const input = $("#admin-image-file");
  const image = input.files?.[0];
  if (!image) {
    adminMessage("กรุณาเลือกไฟล์รูปภาพก่อน", true);
    return;
  }
  const button = $("#admin-image-upload");
  button.disabled = true;
  const originalText = button.textContent;
  button.textContent = "กำลังอัปโหลด…";
  try {
    const form = new FormData();
    form.append("image", image);
    const response = await fetch(`/api/admin/records/${recordId}/image`, {
      method: "POST",
      body: form,
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || "อัปโหลดภาพไม่สำเร็จ");
    }
    await response.json();
    const record = await (await fetch(`/api/records/${recordId}`)).json();
    adminMessage("อัปโหลดภาพกลางแล้ว ภาพนี้พร้อมใช้ในขั้นตอน AI ต่อไป");
    renderAdminEditor(record);
    await Promise.all([loadRecords(), loadDashboard(), loadAudit()]);
  } catch (error) {
    adminMessage(error.message, true);
    button.disabled = false;
    button.textContent = originalText;
  }
}
async function uploadImageIntake(event) {
  event.preventDefault();
  const sourceId = $("#admin-image-intake-source").value;
  const sheetName = $("#admin-image-intake-sheet").value;
  const files = $("#admin-image-intake-files").files;
  if (!sourceId || !sheetName || !files?.length) {
    imageIntakeMessage("เลือกแหล่งข้อมูล ชีต และไฟล์รูปภาพก่อน", true);
    return;
  }
  const button = event.currentTarget.querySelector("button[type='submit']");
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "กำลังนำภาพเข้า…";
  imageIntakeMessage(
    "กำลังจับคู่ชื่อไฟล์กับ record_id โดยไม่แก้ Google Sheets…",
  );
  try {
    const form = new FormData();
    form.append("sheet_name", sheetName);
    [...files].forEach((file) => form.append("images", file));
    const response = await fetch(`/api/admin/image-intake/${sourceId}`, {
      method: "POST",
      body: form,
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || "นำภาพเข้าไม่สำเร็จ");
    }
    const result = await response.json();
    const notes = [`นำเข้าแล้ว ${result.uploaded.toLocaleString()} ภาพ`];
    if (result.unmatched_count)
      notes.push(
        `ไม่พบ record_id ${result.unmatched_count.toLocaleString()} รายการ: ${result.unmatched.join(", ")}${result.unmatched_count > result.unmatched.length ? "…" : ""}`,
      );
    if (result.invalid_count)
      notes.push(
        `ข้ามไฟล์ ${result.invalid_count.toLocaleString()} ไฟล์: ${result.invalid_files.join(", ")}${result.invalid_count > result.invalid_files.length ? "…" : ""}`,
      );
    imageIntakeMessage(
      notes.join(" · "),
      Boolean(result.unmatched_count || result.invalid_count),
    );
    event.currentTarget.reset();
    renderImageIntakeSheets();
    await Promise.all([loadRecords(), loadDashboard(), loadAudit()]);
  } catch (error) {
    imageIntakeMessage(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}
async function deleteAdminRecord(recordId) {
  if (
    !window.confirm(
      "ยืนยันการลบระเบียนนี้จากสำเนากลาง? การ sync จากต้นทางอาจนำระเบียนกลับมาอีก",
    )
  )
    return;
  try {
    await adminFetch(`/api/admin/records/${recordId}`, { method: "DELETE" });
    adminMessage("ลบระเบียนจากสำเนากลางแล้ว");
    renderAdminEditor();
    await Promise.all([loadAdminRecords(), loadAudit(), loadRecords()]);
  } catch (error) {
    adminMessage(error.message, true);
  }
}

function renderDetailFields(fields) {
  return fields
    .map(([label, value]) => `<dt>${label}</dt><dd>${compact(value)}</dd>`)
    .join("");
}

function renderRawDataRows(rawData) {
  return Object.entries(rawData || {})
    .map(
      ([key, value]) =>
        `<tr><th>${escapeHtml(key)}</th><td>${compact(value, "")}</td></tr>`,
    )
    .join("");
}

function renderDuplicateCandidates(candidates) {
  if (!candidates?.length) {
    return `<p class="muted">ไม่พบเลขทะเบียนเดียวกันจากแหล่งอื่นในสำเนากลาง</p>`;
  }
  const items = candidates
    .map(
      (item) => `<li>
        <button class="record-link" data-record-id="${item.id}">${compact(item.registration_no)}</button>
        — ${escapeHtml(item.source_sheet)}
      </li>`,
    )
    .join("");
  return `<ul>${items}</ul>`;
}

function recordGalleryImages(record) {
  if (record.images?.length) return record.images;
  return record.image_url
    ? [{ url: record.image_url, position: 1, origin: "legacy" }]
    : [];
}

function renderImageSection(record) {
  const images = recordGalleryImages(record);
  if (!images.length) {
    return record.status_photographed
      ? `<section class="image-unavailable">
          <h3>รูปภาพ</h3>
          <p class="muted">ระบุว่าถ่ายภาพแล้ว แต่ยังไม่มีภาพที่นำเข้าในคลังกลาง</p>
        </section>`
      : "";
  }
  const gallery = images
    .map((image, index) => {
      const imageNumber = index + 1;
      const origin =
        image.origin === "google_sheets_bridge" ? " · จาก Google Sheets" : "";
      return `<a href="${escapeHtml(image.url)}" target="_blank" rel="noreferrer">
        <img src="${escapeHtml(image.url)}" alt="ภาพที่ ${imageNumber} ของ ${compact(record.registration_no, "ระเบียน")}" loading="lazy">
        <span>ภาพที่ ${imageNumber}${origin}</span>
      </a>`;
    })
    .join("");
  return `<section class="detail-image">
    <h3>รูปภาพ <span class="muted">(${images.length.toLocaleString()} รูป)</span></h3>
    <div class="image-gallery">${gallery}</div>
    <p class="muted">คลิกภาพเพื่อเปิดขนาดเต็ม</p>
  </section>`;
}

function renderSourceDetails(rawRows) {
  if (!rawRows) return "";
  return `<details class="source-details detail-section">
    <summary>ดูข้อมูลต้นทางที่นำเข้า</summary>
    <p class="muted">ข้อมูลนี้เก็บไว้เพื่อการตรวจสอบย้อนกลับจากชีตต้นทาง</p>
    <div class="table-wrap"><table class="raw-table"><tbody>${rawRows}</tbody></table></div>
  </details>`;
}

async function loadDetail(recordId, updateHistory = true) {
  if (updateHistory) pushRoute("detail", recordId);
  const record = await (await fetch(`/api/records/${recordId}`)).json();
  state.currentDetailId = recordId;
  setView("detail");
  const fields = [
    ["เลขทะเบียน", record.registration_no],
    ["เลขทะเบียนเดิม", record.previous_registration_no],
    ["รายการ", record.title_description],
    ["ขนาด", record.dimensions_text],
    ["ชนิด", record.material],
    ["อายุสมัย", record.period],
    ["ประวัติที่มา", record.provenance],
    ["การตรวจสอบข้อมูล", record.status_data_check],
    ["การถ่ายภาพ", record.status_photographed],
    ["การลงระบบ Antique", record.status_antique],
    ["การส่งขึ้นห้องคลัง", record.status_storage],
    [
      "แหล่งข้อมูล",
      `${record.source_name || ""} / ${record.source_sheet} / แถว ${record.source_row_number}`,
    ],
  ];
  const rawRows = renderRawDataRows(record.raw_data);
  const detailFields = renderDetailFields(fields);
  const imageSection = renderImageSection(record);
  const sourceDetails = renderSourceDetails(rawRows);
  const duplicates = renderDuplicateCandidates(record.duplicate_candidates);
  $("#detail-content").innerHTML = `<article class="detail-card">
    <h2>${compact(record.registration_no, "ไม่มีเลขทะเบียน")}</h2>
    <div class="detail-layout">
      <dl class="detail-grid detail-section">${detailFields}</dl>
      ${imageSection}
    </div>
    ${sourceDetails}
    <div class="detail-section">
      <h3>ระเบียนที่อาจซ้ำ</h3>
      <p class="muted">แสดงจากเลขทะเบียนเดียวกันเท่านั้น และไม่ยืนยันว่าเป็นข้อมูลชิ้นเดียวกัน</p>
      ${duplicates}
    </div>
  </article>`;
  bindRecordLinks("#detail-content [data-record-id]");
}
async function loadFilterOptions() {
  const data = await (await fetch("/api/dashboard")).json();
  const setOptions = (target, items) => {
    $(target).insertAdjacentHTML(
      "beforeend",
      items
        .map(
          (item) =>
            `<option value="${escapeHtml(item.label)}">${escapeHtml(item.label)} (${item.count.toLocaleString()})</option>`,
        )
        .join(""),
    );
  };
  setOptions("#sheet-filter", data.by_source_sheet);
  setOptions(
    "#check-filter",
    data.by_data_check.filter((item) => item.label !== "ไม่ระบุ"),
  );
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
$("#search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  state.page = 1;
  loadRecords();
});
$("#previous-page").addEventListener("click", () => {
  state.page -= 1;
  loadRecords();
});
$("#next-page").addEventListener("click", () => {
  state.page += 1;
  loadRecords();
});
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
  renderImageIntakeSheets,
);
$("#admin-image-intake-form").addEventListener("submit", uploadImageIntake);
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
initialise().catch((error) => {
  $("#freshness").textContent = `เกิดข้อผิดพลาด: ${error.message}`;
});
