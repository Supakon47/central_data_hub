// Dashboard: record counts, follow-up lists and duplicate registrations.
import { getJson } from "../api.js";
import { $, escapeHtml } from "../core/dom.js";
import { state } from "../core/state.js";

const FOLLOW_UP_ITEMS = [
  ["data_check", "ต้องตรวจสอบข้อมูล", "ยังไม่อยู่ในสถานะตรวจสอบแล้ว"],
  ["photographed", "ต้องติดตามการถ่ายภาพ", "ยังไม่อยู่ในสถานะถ่ายภาพแล้ว"],
  ["antique", "ต้องลงระบบ Antique", "ยังไม่อยู่ในสถานะลงระบบแล้ว"],
  ["storage", "ต้องส่งขึ้นห้องคลัง", "ยังไม่อยู่ในสถานะส่งขึ้นห้องคลังแล้ว"],
];

function percentOf(value, total) {
  if (!total) return "0%";
  return `${Math.round((value / total) * 100).toLocaleString()}%`;
}

function renderBar(item, max) {
  const width = (item.count / max) * 100;
  return `<div class="bar-row">
    <span class="bar-label" title="${escapeHtml(item.label)}">${escapeHtml(item.label)}</span>
    <span class="bar-track"><span class="bar-fill" style="width:${width}%"></span></span>
    <strong>${item.count.toLocaleString()}</strong>
  </div>`;
}

function renderBars(target, items) {
  const max = Math.max(...items.map((item) => item.count), 1);
  $(target).innerHTML = items.map((item) => renderBar(item, max)).join("")
    || `<p class="muted">ยังไม่มีข้อมูล</p>`;
}

function renderMetric(label, value, note = "") {
  if (label === "ทะเบียนที่ซ้ำทั้งหมด") {
    return `<button id="toggle-duplicates" class="metric metric-button dashboard-metric" type="button" aria-expanded="false">
      <span class="label">${label}</span>
      <span class="number">${value.toLocaleString()}</span>
      <span class="metric-action">กดเพื่อดูรายการที่ซ้ำ</span>
    </button>`;
  }
  return `<article class="metric dashboard-metric">
    <span class="label">${label}</span>
    <span class="number">${value.toLocaleString()}</span>
    <span class="dashboard-metric-note">${escapeHtml(note)}</span>
  </article>`;
}

function renderSourceTable(items, total) {
  const target = $("#dashboard-source-table");
  target.innerHTML = items.length
    ? items.slice(0, 8).map((item) => `<tr>
      <td title="${escapeHtml(item.label)}">${escapeHtml(item.label)}</td>
      <td>${item.count.toLocaleString()}</td>
      <td><span class="table-progress"><span style="width:${percentOf(item.count, total)}"></span></span>${percentOf(item.count, total)}</td>
    </tr>`).join("")
    : `<tr><td colspan="3" class="muted">ยังไม่มีข้อมูล</td></tr>`;
}

export function createDashboardController({ navigate, bindRecordLinks, loadRecords }) {
  function filterParams() {
    const params = new URLSearchParams();
    const sourceId = $("#dashboard-source-filter").value;
    const sourceSheet = $("#dashboard-sheet-filter").value;
    if (sourceId) params.set("source_id", sourceId);
    if (sourceSheet) params.set("source_sheet", sourceSheet);
    return params;
  }

  async function loadFilterSources() {
    if (state.dashboardSources.length) return;
    const catalog = await getJson("/api/catalog");
    state.dashboardSources = catalog.sources;
    const sourceSelect = $("#dashboard-source-filter");
    const selectedSource = sourceSelect.value;
    sourceSelect.innerHTML = `<option value="">ทุกแหล่งข้อมูล</option>${catalog.sources
      .map((source) => `<option value="${source.id}">${escapeHtml(source.name)} (${source.record_count.toLocaleString()})</option>`)
      .join("")}`;
    sourceSelect.value = [...sourceSelect.options].some(
      (option) => option.value === selectedSource,
    ) ? selectedSource : "";
  }

  async function updateSheetOptions() {
    const sourceId = $("#dashboard-source-filter").value;
    const sheetSelect = $("#dashboard-sheet-filter");
    const selectedSheet = sheetSelect.value;
    if (!sourceId) {
      sheetSelect.innerHTML = `<option value="">ทุกชีต</option>`;
      sheetSelect.disabled = true;
      return;
    }
    sheetSelect.innerHTML = `<option value="">กำลังโหลดชีต…</option>`;
    sheetSelect.disabled = true;
    let sheets = state.dashboardSheetsBySource.get(sourceId);
    if (!sheets) {
      const source = state.dashboardSources.find((item) => String(item.id) === sourceId);
      const configuredSheets = (source?.configured_sheets || []).map((item) => item.name);
      const sourceDashboard = await getJson(`/api/dashboard?source_id=${encodeURIComponent(sourceId)}`);
      sheets = [...new Set([
        ...configuredSheets,
        ...sourceDashboard.by_source_sheet.map((item) => item.label),
      ])].sort((left, right) => left.localeCompare(right, "th"));
      state.dashboardSheetsBySource.set(sourceId, sheets);
    }
    sheetSelect.innerHTML = `<option value="">ทุกชีต</option>${sheets
      .map((sheet) => `<option value="${escapeHtml(sheet)}">${escapeHtml(sheet)}</option>`)
      .join("")}`;
    sheetSelect.disabled = false;
    sheetSelect.value = sheets.includes(selectedSheet) ? selectedSheet : "";
  }

  function scopeLabel() {
    const sourceSelect = $("#dashboard-source-filter");
    const sheetSelect = $("#dashboard-sheet-filter");
    const scope = [];
    if (sourceSelect.value) scope.push(sourceSelect.selectedOptions[0].text);
    if (sheetSelect.value) scope.push(sheetSelect.value);
    return scope.length ? ` · ${scope.join(" / ")}` : " · ทุกข้อมูล";
  }

  async function openFollowUpInExplorer(attention) {
    const sourceSelect = $("#dashboard-source-filter");
    const sheetSelect = $("#dashboard-sheet-filter");
    const [, label] = FOLLOW_UP_ITEMS.find(([key]) => key === attention);
    state.explorerSourceId = sourceSelect.value;
    state.explorerAttention = attention;
    state.explorerContextLabel = `ติดตามงาน: ${label}`;
    if (sourceSelect.value) state.explorerContextLabel += ` · ${sourceSelect.selectedOptions[0].text}`;
    if (sheetSelect.value) {
      $("#sheet-filter").value = sheetSelect.value;
      state.explorerContextLabel += ` / ${sheetSelect.value}`;
    }
    state.page = 1;
    await navigate("explorer");
    await loadRecords();
  }

  function renderFollowUp(data) {
    const cards = FOLLOW_UP_ITEMS.map(([key, label, description]) => {
      const count = data.follow_up?.[key] || 0;
      return `<button class="follow-up-card" type="button" data-follow-up="${key}">
        <span class="follow-up-label">${label}</span>
        <strong>${count.toLocaleString()}</strong>
        <span class="follow-up-description">${description}</span>
        <span class="follow-up-action">ดูระเบียน →</span>
      </button>`;
    });
    cards.push(`<button class="follow-up-card follow-up-duplicates" type="button" data-follow-up="duplicates">
      <span class="follow-up-label">ทะเบียนที่ซ้ำ</span>
      <strong>${data.duplicate_registration_groups.toLocaleString()}</strong>
      <span class="follow-up-description">กลุ่มเลขทะเบียนที่ควรตรวจสอบ</span>
      <span class="follow-up-action">ดูรายการ →</span>
    </button>`);
    $("#follow-up-list").innerHTML = cards.join("");
    document.querySelectorAll("[data-follow-up]").forEach((button) => {
      button.onclick = () => {
        if (button.dataset.followUp === "duplicates") {
          $("#toggle-duplicates").click();
          return;
        }
        openFollowUpInExplorer(button.dataset.followUp);
      };
    });
  }

  function renderDuplicateGroup(group) {
    const records = group.records.map((record) => `<button class="record-link" data-record-id="${record.id}">
      ${escapeHtml(record.registration_no || "ไม่ระบุ")}
    </button><span class="muted"> — ${escapeHtml(record.source_sheet)} / แถว ${record.source_row_number}</span>`).join("<br>");
    return `<tr><td>${escapeHtml(group.registration_no)}</td><td>${group.count.toLocaleString()}</td><td>${records}</td></tr>`;
  }

  async function loadDuplicateGroups() {
    $("#duplicate-groups").innerHTML = `<p class="muted">กำลังค้นหารายการที่ซ้ำ…</p>`;
    const params = filterParams();
    params.set("limit", "50");
    const duplicates = await getJson(`/api/duplicates?${params}`);
    const caption = duplicates.total_groups > duplicates.groups.length
      ? `<p class="muted">แสดง ${duplicates.groups.length.toLocaleString()} จาก ${duplicates.total_groups.toLocaleString()} กลุ่ม</p>`
      : "";
    const table = duplicates.groups.length
      ? `<div class="table-wrap"><table class="duplicate-table"><thead><tr><th>เลขทะเบียน</th><th>จำนวน</th><th>ระเบียนที่ต้องตรวจสอบ</th></tr></thead><tbody>${duplicates.groups.map(renderDuplicateGroup).join("")}</tbody></table></div>`
      : `<p class="muted">ไม่พบเลขทะเบียนที่ซ้ำกัน</p>`;
    $("#duplicate-groups").innerHTML = `${caption}${table}`;
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

  async function loadDashboard() {
    await loadFilterSources();
    const params = filterParams();
    const endpoint = params.size ? `/api/dashboard?${params}` : "/api/dashboard";
    const data = await getJson(endpoint);
    const metrics = [
      ["ระเบียนทั้งหมด", data.total_records, "ข้อมูลที่นำเข้าในระบบกลาง"],
      ["มีเลขทะเบียน", data.with_registration_no, `${percentOf(data.with_registration_no, data.total_records)} ของทั้งหมด`],
      ["มีรายละเอียดรายการ", data.with_description, `${percentOf(data.with_description, data.total_records)} ของทั้งหมด`],
      ["มีรูปภาพ", data.with_image_url, `${percentOf(data.with_image_url, data.total_records)} ของทั้งหมด`],
      ["ทะเบียนที่ซ้ำทั้งหมด", data.duplicate_registration_groups],
    ];
    $("#metrics").innerHTML = metrics.map(([label, value, note]) => renderMetric(label, value, note)).join("");
    $("#dashboard-status").textContent = `มีข้อมูล ${data.total_records.toLocaleString()} ระเบียน${scopeLabel()}`;
    renderBars("#chart-sheets", data.by_source_sheet);
    renderBars("#chart-check", data.by_data_check);
    renderBars("#chart-photo", data.by_photo);
    renderBars("#chart-antique", data.by_antique);
    renderBars("#chart-storage", data.by_storage);
    renderSourceTable(data.by_source_sheet, data.total_records);
    renderFollowUp(data);
    $("#duplicate-panel").hidden = true;
    $("#toggle-duplicates").onclick = toggleDuplicateGroups;
    $("#open-explorer").onclick = async () => {
      const sourceSelect = $("#dashboard-source-filter");
      const selectedSheet = $("#dashboard-sheet-filter").value;
      state.explorerSourceId = sourceSelect.value;
      state.explorerAttention = "";
      state.explorerContextLabel = sourceSelect.value
        ? `ขอบเขตจาก Dashboard: ${sourceSelect.selectedOptions[0].text}` : "";
      if (selectedSheet) $("#sheet-filter").value = selectedSheet;
      if (selectedSheet) state.explorerContextLabel += ` / ${selectedSheet}`;
      state.page = 1;
      await navigate("explorer");
      await loadRecords();
    };
  }

  function bindEvents() {
    $("#dashboard-source-filter").addEventListener("change", () => {
      updateSheetOptions().catch((error) => {
        $("#dashboard-status").textContent = `เกิดข้อผิดพลาด: ${error.message}`;
      });
    });
    $("#dashboard-filter-form").addEventListener("submit", (event) => {
      event.preventDefault();
      loadDashboard().catch((error) => {
        $("#dashboard-status").textContent = `เกิดข้อผิดพลาด: ${error.message}`;
      });
    });
    $("#dashboard-filter-reset").addEventListener("click", async () => {
      $("#dashboard-source-filter").value = "";
      await updateSheetOptions();
      await loadDashboard();
    });
  }

  return { bindEvents, loadDashboard };
}
