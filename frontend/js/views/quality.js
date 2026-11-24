import { adminFetch } from "../api.js";
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

  function bindQualityActions() {
    bindRecordLinks("#quality-body [data-record-id]");
    bindRecordLinks("#location-match-body [data-record-id]");
    bindRecordLinks("#location-reviewed-body [data-record-id]");
    document.querySelectorAll("[data-location-review-undo]").forEach((button) => {
      button.addEventListener("click", () => undoLocationReview(button.dataset.locationReviewUndo));
    });
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
    document.querySelectorAll("[data-location-match-approve]").forEach((button) => {
      button.addEventListener("click", () => {
        const [objectRecordId, locationRecordId] = button.dataset.locationMatchApprove.split(":");
        updateLocationMatch(objectRecordId, locationRecordId, "approved");
      });
    });
    document.querySelectorAll("[data-location-match-reject]").forEach((button) => {
      button.addEventListener("click", () => {
        const [objectRecordId, locationRecordId] = button.dataset.locationMatchReject.split(":");
        updateLocationMatch(objectRecordId, locationRecordId, "rejected");
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
    if ($("#quality-include-resolved").checked) {
      params.set("include_resolved", "true");
    }
    const [issuesResponse, catalogResponse, sessionResponse, locationResponse, reportResponse, reviewedResponse] = await Promise.all([
      fetch(`/api/data-quality/issues?${params}`),
      fetch("/api/catalog"),
      fetch("/api/admin/session"),
      fetch("/api/location-match-candidates?limit=100"),
      fetch("/api/location-match-report"),
      fetch("/api/location-match-reviews"),
    ]);
    if (!issuesResponse.ok) {
      throw new Error("ไม่สามารถโหลดประเด็นคุณภาพข้อมูลได้");
    }
    const data = await issuesResponse.json();
    const catalog = await catalogResponse.json();
    const adminSession = await sessionResponse.json();
    const locationMatches = locationResponse.ok
      ? await locationResponse.json()
      : { total: 0, items: [], message: "ไม่สามารถโหลดรายการตรวจการเชื่อมตำแหน่งได้" };
    const sourceStillExists = catalog.sources.some(
      (source) => String(source.id) === selectedSource,
    );
    sourceSelect.innerHTML = `<option value="">ทุกแหล่งข้อมูล</option>${renderSelectOptions(catalog.sources, sourceStillExists ? selectedSource : "")}`;
    const metrics = [
      ["ประเด็นที่แสดง", data.total],
      ["ต้องแก้ไข", data.summary.errors],
      ["ควรตรวจสอบ", data.summary.warnings],
      ["รอตรวจตำแหน่ง", locationMatches.total],
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
    $("#location-match-summary").textContent = locationMatches.total
      ? `พบ ${locationMatches.total.toLocaleString()} คู่ที่รอตรวจ · แสดงสูงสุด 100 คู่ · ${locationMatches.message}`
      : locationMatches.message;
    $("#location-match-body").innerHTML = locationMatches.items
      .map((candidate) => renderLocationMatch(candidate, adminSession.authenticated))
      .join("") || `<tr><td colspan="5" class="muted">ยังไม่มีคู่ข้อมูลที่พร้อมให้ตรวจ โปรดนำเข้าทั้งทะเบียนหลักและข้อมูลตำแหน่งก่อน</td></tr>`;

    if (reportResponse.ok) {
      const report = await reportResponse.json();
      const objects = report.object_records;
      $("#location-report-summary").textContent =
        `ทะเบียนวัตถุ ${objects.rows.toLocaleString()} แถว (${objects.distinct_keys.toLocaleString()} เลข) · `
        + `มีตำแหน่งเสนอให้ ${objects.keys_with_location.toLocaleString()} เลข · ${report.message}`;
      $("#location-report-body").innerHTML = report.location_sources
        .map((source) => renderReportRow(source, report.register_start_year))
        .join("") || `<tr><td colspan="9" class="muted">ยังไม่มีแหล่งข้อมูลที่มีคอลัมน์ตำแหน่ง</td></tr>`;
    } else {
      $("#location-report-summary").textContent = "ไม่สามารถโหลดรายงานผลการจับคู่ได้";
      $("#location-report-body").innerHTML = "";
    }

    const reviewed = reviewedResponse.ok ? await reviewedResponse.json() : { total: 0, items: [] };
    $("#location-reviewed-summary").textContent = reviewed.total
      ? `บันทึกผลตรวจแล้ว ${reviewed.total.toLocaleString()} คู่`
      : "ยังไม่มีผลตรวจที่บันทึก";
    $("#location-reviewed-body").innerHTML = reviewed.items
      .map((review) => renderReviewedMatch(review, adminSession.authenticated))
      .join("") || `<tr><td colspan="5" class="muted">ยังไม่มีผลตรวจ</td></tr>`;
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

  return { loadDataQuality };
}
