const BUILD_VERSION = "2026.10.05.3";
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
}
function routeFromLocation() {
  const params = new URLSearchParams(window.location.hash.slice(1));
  const recordId = params.get("record");
  if (recordId && /^\d+$/.test(recordId)) return { view: "detail", recordId };
  const view = params.get("view");
  return ["dashboard", "catalog"].includes(view) ? { view } : { view: "explorer" };
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
  $(target).innerHTML = items.map((item) => `<div class="bar-row"><span class="bar-label" title="${escapeHtml(item.label)}">${escapeHtml(item.label)}</span><span class="bar-track"><span class="bar-fill" style="width:${item.count / max * 100}%"></span></span><strong>${item.count.toLocaleString()}</strong></div>`).join("") || `<p class="muted">ยังไม่มีข้อมูล</p>`;
}
async function loadDashboard() {
  const data = await (await fetch("/api/dashboard")).json();
  const metrics = [["ระเบียนทั้งหมด", data.total_records], ["มีเลขทะเบียน", data.with_registration_no], ["มีรายละเอียดรายการ", data.with_description], ["มีลิงก์รูปภาพ", data.with_image_url]];
  $("#metrics").innerHTML = metrics.map(([label, value]) => `<article class="metric"><span class="label">${label}</span><span class="number">${value.toLocaleString()}</span></article>`).join("");
  renderBars("#chart-sheets", data.by_source_sheet); renderBars("#chart-check", data.by_data_check); renderBars("#chart-photo", data.by_photo); renderBars("#chart-antique", data.by_antique); renderBars("#chart-storage", data.by_storage);
}
async function loadCatalog() {
  const data = await (await fetch("/api/catalog")).json();
  $("#catalog-list").innerHTML = data.sources.map((source) => { const sync = source.last_sync; return `<article class="catalog-item"><h3>${escapeHtml(source.name)}</h3><p class="muted">${compact(source.description, "ไม่มีคำอธิบาย")}</p><div class="catalog-meta"><span>ประเภท: ${escapeHtml(source.connection_type)}</span><span>ชั้นข้อมูล: ${escapeHtml(source.classification)}</span><span>ระเบียน: ${source.record_count.toLocaleString()}</span><span class="issue">ประเด็นที่ยังไม่ปิด: ${source.unresolved_issues.toLocaleString()}</span><span>sync ล่าสุด: ${sync ? escapeHtml(sync.completed_at || sync.started_at) : "ยังไม่เคย"}</span></div></article>`; }).join("") || `<p class="muted">ยังไม่มีแหล่งข้อมูล</p>`;
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
window.addEventListener("popstate", () => renderRoute());
initialise().catch((error) => { $("#freshness").textContent = `เกิดข้อผิดพลาด: ${error.message}`; });
