// Data quality: import issues, the location match report, and the location review queue.
import { adminFetch, fetchAdminSession } from "../api.js";
import { $, compact, escapeHtml, renderMetric } from "../core/dom.js";

function renderSelectOptions(items, selectedValue = "") {
  return items
    .map(
      (item) =>
        `<option value="${item.id}"${String(item.id) === String(selectedValue) ? " selected" : ""}>${escapeHtml(item.name)}</option>`,
    )
    .join("");
}

export function createQualityController({ bindRecordLinks, loadAudit, loadCatalog }) {
  function renderLocationRecord(record, location = null) {
    const source = `${record.source_name || "ไม่ทราบแหล่งข้อมูล"} / ${record.source_sheet || "-"}`;
    return `<button class="record-link" data-record-id="${record.id}">${compact(record.registration_no, `ระเบียน #${record.id}`)}</button>
      <br><strong>${compact(record.title_description, "ไม่ระบุรายการ")}</strong>
      ${location?.value ? `<br><span class="location-value">${escapeHtml(location.value)}</span>` : ""}
      <br><span class="muted clamp">${escapeHtml(source)}</span>`;
  }

  function renderLocationMatch(candidate, isAdmin) {
    const caution = candidate.title_conflict
      ? `<span class="quality-severity warning">ชื่อวัตถุไม่ตรงกัน</span>`
      : `<span class="badge">เลขทะเบียนตรงกัน</span>`;
    const actions = isAdmin
      ? `<div class="location-match-actions">
          <button class="small" data-location-match-approve="${candidate.object_record.id}:${candidate.location_record.id}">อนุมัติการเชื่อม</button>
          <button class="small secondary" data-location-match-reject="${candidate.object_record.id}:${candidate.location_record.id}">ไม่ใช่รายการเดียวกัน</button>
        </div>`
      : `<span class="muted">เข้าสู่ระบบผู้ดูแลเพื่อบันทึกผลตรวจ</span>`;
    return `<tr>
      <td><strong>${escapeHtml(candidate.registration_no)}</strong></td>
      <td>${renderLocationRecord(candidate.object_record)}</td>
      <td>${renderLocationRecord(candidate.location_record, candidate.location_record.location)}</td>
      <td>${caution}<br><span class="muted">ต้องตรวจหลักฐานก่อนสรุปตำแหน่งปัจจุบัน</span></td>
      <td>${actions}</td>
    </tr>`;
  }

  function renderReportRow(source, startYear) {
    const n = (value) => Number(value || 0).toLocaleString();
    const percent = (part, whole) => (whole ? ` (${Math.round((part / whole) * 100)}%)` : "");
    const years = source.unmatched_by_year;
    return `<tr>
      <td><strong>${escapeHtml(source.source_name || `แหล่ง #${source.source_id}`)}</strong></td>
      <td>${n(source.rows)}${source.missing_location ? `<br><span class="muted">ไม่มีตำแหน่ง ${n(source.missing_location)}</span>` : ""}</td>
      <td>${n(source.with_key)}</td>
      <td>${n(source.missing_registration + source.placeholder_registration)}
        <br><span class="muted">ว่าง ${n(source.missing_registration)} · ชั่วคราว ${n(source.placeholder_registration)}</span></td>
      <td><strong>${n(source.matched)}</strong>${percent(source.matched, source.with_key)}</td>
      <td>${n(source.unmatched)}
        <br><span class="muted">ก่อนปี ${startYear} ${n(years.before_register)} · ตั้งแต่ ${startYear} ${n(years.since_register)} · ไม่มีปี ${n(years.no_year)}</span></td>
      <td>${n(source.duplicate_keys)} เลข<br><span class="muted">${n(source.duplicate_rows)} แถว</span></td>
      <td>${n(source.title_conflict_pairs)} / ${n(source.pairs)} คู่</td>
      <td>อนุมัติ ${n(source.approved)}<br>ไม่ใช่ ${n(source.rejected)}<br>รอตรวจ ${n(source.pending)}</td>
    </tr>`;
  }

  function renderReviewedMatch(review, isAdmin) {
    const decision = review.decision === "approved"
      ? `<span class="badge">อนุมัติแล้ว</span>`
      : `<span class="quality-severity warning">ไม่ใช่รายการเดียวกัน</span>`;
    const reviewedAt = review.reviewed_at
      ? `<br><span class="muted">${new Date(review.reviewed_at).toLocaleString("th-TH")}</span>`
      : "";
    const action = isAdmin
      ? `<button class="small secondary" data-location-review-undo="${review.id}">ยกเลิกผลตรวจ</button>`
      : `<span class="muted">เข้าสู่ระบบผู้ดูแลเพื่อแก้ไข</span>`;
    return `<tr>
      <td><strong>${escapeHtml(review.object_record.registration_no || "")}</strong></td>
      <td>${renderLocationRecord(review.object_record)}</td>
      <td>${renderLocationRecord(review.location_record, review.location_record.location)}</td>
      <td>${decision}${reviewedAt}${review.note ? `<br><small>${escapeHtml(review.note)}</small>` : ""}</td>
      <td>${action}</td>
    </tr>`;
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


  const OPEN_PANELS_KEY = "quality-open-panels";
  // Sections whose table shows current data; a stale section reloads when opened.
  const freshPanels = new Set();
  const metricValues = {};
  let isAdmin = false;
  let panelsBound = false;

  function rememberOpenPanels() {
    const open = [...document.querySelectorAll("[data-quality-panel]")]
      .filter((panel) => panel.open)
      .map((panel) => panel.dataset.qualityPanel);
    try {
      window.localStorage.setItem(OPEN_PANELS_KEY, JSON.stringify(open));
    } catch {
      // Remembering open sections is only a convenience.
    }
  }

  function restoreOpenPanels() {
    let open = [];
    try {
      open = JSON.parse(window.localStorage.getItem(OPEN_PANELS_KEY) || "[]");
    } catch {
      open = [];
    }
    document.querySelectorAll("[data-quality-panel]").forEach((panel) => {
      panel.open = open.includes(panel.dataset.qualityPanel);
    });
  }

  function setPanelCount(name, text) {
    const target = document.querySelector(`[data-quality-count="${name}"]`);
    if (target) target.textContent = text;
  }

  function bindActions(container) {
    bindRecordLinks(`${container} [data-record-id]`);
    document.querySelectorAll(`${container} [data-location-review-undo]`).forEach((button) => {
      button.addEventListener("click", () => undoLocationReview(button.dataset.locationReviewUndo));
    });
    document.querySelectorAll(`${container} [data-quality-resolve]`).forEach((button) => {
      button.addEventListener("click", () => updateQualityIssue(button.dataset.qualityResolve, true));
    });
    document.querySelectorAll(`${container} [data-quality-reopen]`).forEach((button) => {
      button.addEventListener("click", () => updateQualityIssue(button.dataset.qualityReopen, false));
    });
    document.querySelectorAll(`${container} [data-location-match-approve]`).forEach((button) => {
      button.addEventListener("click", () => {
        const [objectRecordId, locationRecordId] = button.dataset.locationMatchApprove.split(":");
        updateLocationMatch(objectRecordId, locationRecordId, "approved");
      });
    });
    document.querySelectorAll(`${container} [data-location-match-reject]`).forEach((button) => {
      button.addEventListener("click", () => {
        const [objectRecordId, locationRecordId] = button.dataset.locationMatchReject.split(":");
        updateLocationMatch(objectRecordId, locationRecordId, "rejected");
      });
    });
  }

  async function fetchJson(url, failureMessage) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(failureMessage);
    return response.json();
  }

  function renderMetrics() {
    const metrics = [
      ["ประเด็นที่แสดง", metricValues.issues],
      ["ต้องแก้ไข", metricValues.errors],
      ["ควรตรวจสอบ", metricValues.warnings],
      ["รอตรวจตำแหน่ง", metricValues.pending],
    ];
    $("#quality-metrics").innerHTML = metrics
      .map(([label, value]) => renderMetric(label, value ?? "…"))
      .join("");
  }

  async function loadIssues() {
    const sourceSelect = $("#quality-source-filter");
    const selectedSource = sourceSelect.value;
    const params = new URLSearchParams({ page: "1", page_size: "100" });
    if (selectedSource) params.set("source_id", selectedSource);
    const severity = $("#quality-severity-filter").value;
    if (severity) params.set("severity", severity);
    if ($("#quality-include-resolved").checked) params.set("include_resolved", "true");
    const [data, catalog] = await Promise.all([
      fetchJson(`/api/data-quality/issues?${params}`, "ไม่สามารถโหลดประเด็นคุณภาพข้อมูลได้"),
      fetchJson("/api/catalog", "ไม่สามารถโหลดรายชื่อแหล่งข้อมูลได้"),
    ]);
    const sourceStillExists = catalog.sources.some((source) => String(source.id) === selectedSource);
    sourceSelect.innerHTML = `<option value="">ทุกแหล่งข้อมูล</option>${renderSelectOptions(catalog.sources, sourceStillExists ? selectedSource : "")}`;
    Object.assign(metricValues, {
      issues: data.total,
      errors: data.summary.errors,
      warnings: data.summary.warnings,
    });
    renderMetrics();
    setPanelCount("issues", `${data.total.toLocaleString()} ประเด็น`);
    $("#quality-summary").textContent =
      data.total > data.items.length
        ? `พบ ${data.total.toLocaleString()} ประเด็น · แสดง 100 รายการล่าสุด`
        : `พบ ${data.total.toLocaleString()} ประเด็น`;
    $("#quality-body").innerHTML =
      data.items.map((issue) => renderQualityIssue(issue, isAdmin)).join("")
      || `<tr><td colspan="5" class="muted">ไม่พบประเด็นตามเงื่อนไข</td></tr>`;
    bindActions("#quality-body");
  }

  async function loadReport() {
    $("#location-report-summary").textContent = "กำลังโหลดรายงาน…";
    const report = await fetchJson("/api/location-match-report", "ไม่สามารถโหลดรายงานผลการจับคู่ได้");
    const objects = report.object_records;
    $("#location-report-summary").textContent =
      `ทะเบียนวัตถุ ${objects.rows.toLocaleString()} แถว (${objects.distinct_keys.toLocaleString()} เลข) · `
      + `มีตำแหน่งเสนอให้ ${objects.keys_with_location.toLocaleString()} เลข · ${report.message}`;
    $("#location-report-body").innerHTML = report.location_sources
      .map((source) => renderReportRow(source, report.register_start_year))
      .join("") || `<tr><td colspan="9" class="muted">ยังไม่มีแหล่งข้อมูลที่มีคอลัมน์ตำแหน่ง</td></tr>`;
    const matched = report.location_sources.reduce((sum, source) => sum + source.matched, 0);
    setPanelCount("report", `พบในทะเบียน ${matched.toLocaleString()} แถว`);
  }

  async function loadCandidates({ countOnly = false } = {}) {
    if (!countOnly) $("#location-match-summary").textContent = "กำลังโหลดคู่ที่รอตรวจ…";
    const matches = await fetchJson(
      `/api/location-match-candidates?limit=${countOnly ? 1 : 100}`,
      "ไม่สามารถโหลดรายการตรวจการเชื่อมตำแหน่งได้",
    );
    metricValues.pending = matches.total;
    renderMetrics();
    setPanelCount("candidates", `รอตรวจ ${matches.total.toLocaleString()} คู่`);
    if (countOnly) return;
    $("#location-match-summary").textContent = matches.total
      ? `พบ ${matches.total.toLocaleString()} คู่ที่รอตรวจ · แสดงสูงสุด 100 คู่ · ${matches.message}`
      : matches.message;
    $("#location-match-body").innerHTML = matches.items
      .map((candidate) => renderLocationMatch(candidate, isAdmin))
      .join("") || `<tr><td colspan="5" class="muted">ยังไม่มีคู่ข้อมูลที่พร้อมให้ตรวจ โปรดนำเข้าทั้งทะเบียนหลักและข้อมูลตำแหน่งก่อน</td></tr>`;
    bindActions("#location-match-body");
  }

  async function loadReviewed({ countOnly = false } = {}) {
    const reviewed = await fetchJson(
      `/api/location-match-reviews?limit=${countOnly ? 1 : 200}`,
      "ไม่สามารถโหลดผลตรวจที่บันทึกแล้วได้",
    );
    setPanelCount("reviewed", `${reviewed.total.toLocaleString()} คู่`);
    if (countOnly) return;
    $("#location-reviewed-summary").textContent = reviewed.total
      ? `บันทึกผลตรวจแล้ว ${reviewed.total.toLocaleString()} คู่`
      : "ยังไม่มีผลตรวจที่บันทึก";
    $("#location-reviewed-body").innerHTML = reviewed.items
      .map((review) => renderReviewedMatch(review, isAdmin))
      .join("") || `<tr><td colspan="5" class="muted">ยังไม่มีผลตรวจ</td></tr>`;
    bindActions("#location-reviewed-body");
  }

  const PANEL_LOADERS = {
    issues: loadIssues,
    report: loadReport,
    candidates: () => loadCandidates(),
    reviewed: () => loadReviewed(),
  };
  const PANEL_SUMMARY_TARGETS = {
    issues: "#quality-summary",
    report: "#location-report-summary",
    candidates: "#location-match-summary",
    reviewed: "#location-reviewed-summary",
  };

  function loadPanel(name) {
    freshPanels.add(name);
    return runPanel(name);
  }

  async function runPanel(name) {
    try {
      await PANEL_LOADERS[name]();
    } catch (error) {
      freshPanels.delete(name);
      $(PANEL_SUMMARY_TARGETS[name]).textContent = error.message;
    }
  }

  function bindPanels() {
    if (panelsBound) return;
    panelsBound = true;
    restoreOpenPanels();
    document.querySelectorAll("[data-quality-panel]").forEach((panel) => {
      panel.addEventListener("toggle", () => {
        rememberOpenPanels();
        const name = panel.dataset.qualityPanel;
        if (panel.open && !freshPanels.has(name)) loadPanel(name);
      });
    });
  }

  function isPanelOpen(name) {
    return Boolean(document.querySelector(`[data-quality-panel="${name}"]`)?.open);
  }

  // Counts for every section come first; a table loads only while its section is open.
  async function loadDataQuality() {
    bindPanels();
    // Claim the sections loaded here before awaiting, so the toggle events
    // queued by restoring open sections do not load them a second time.
    freshPanels.clear();
    const panels = ["issues", ...["report", "candidates", "reviewed"].filter(isPanelOpen)];
    panels.forEach((name) => freshPanels.add(name));
    const session = await fetchAdminSession();
    isAdmin = Boolean(session.authenticated);
    const ignore = () => {};
    await Promise.all([
      ...panels.map(runPanel),
      panels.includes("candidates") ? null : loadCandidates({ countOnly: true }).catch(ignore),
      panels.includes("reviewed") ? null : loadReviewed({ countOnly: true }).catch(ignore),
    ]);
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

  async function updateLocationMatch(objectRecordId, locationRecordId, decision) {
    const action = decision === "approved" ? "อนุมัติ" : "ระบุว่าไม่ใช่รายการเดียวกัน";
    if (!window.confirm(`ยืนยัน${action}สำหรับคู่นี้ใช่หรือไม่? การทำรายการนี้ไม่แก้ Excel ต้นทาง`)) return;
    try {
      await adminFetch("/api/admin/location-match-reviews", {
        method: "POST",
        body: JSON.stringify({
          object_record_id: Number(objectRecordId),
          location_record_id: Number(locationRecordId),
          decision,
        }),
      });
      await Promise.all([loadDataQuality(), loadCatalog(), loadAudit()]);
    } catch (error) {
      window.alert(error.message);
    }
  }

  async function undoLocationReview(reviewId) {
    if (!window.confirm("ยกเลิกผลตรวจของคู่นี้ใช่หรือไม่? คู่นี้จะกลับไปอยู่ในรายการรอตรวจ")) return;
    try {
      await adminFetch(`/api/admin/location-match-reviews/${reviewId}`, { method: "DELETE" });
      await Promise.all([loadDataQuality(), loadAudit()]);
    } catch (error) {
      window.alert(error.message);
    }
  }

  function bindEvents() {
    $("#quality-filter-form").addEventListener("submit", (event) => {
      event.preventDefault();
      loadPanel("issues");
    });
  }

  return { bindEvents, loadDataQuality };
}
