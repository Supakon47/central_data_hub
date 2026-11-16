import { $, badge, compact, escapeHtml } from "../core/dom.js";
import { state } from "../core/state.js";

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

export function createExplorerController({ navigate }) {
  function bindRecordLinks(selector = "[data-record-id]") {
    document.querySelectorAll(selector).forEach((button) => {
      button.addEventListener("click", () => {
        navigate("detail", button.dataset.recordId);
      });
    });
  }

  function clearDashboardContext() {
    state.explorerSourceId = "";
    state.explorerAttention = "";
    state.explorerContextLabel = "";
  }

  function filters() {
    const params = new URLSearchParams({ page: state.page, page_size: state.pageSize });
    ["q", "source_sheet", "status_data_check"].forEach((name) => {
      const value = document.querySelector(`[name="${name}"]`).value.trim();
      if (value) params.set(name, value);
    });
    if ($("#description-filter").checked) params.set("has_description", "true");
    if (state.explorerSourceId) params.set("source_id", state.explorerSourceId);
    if (state.explorerAttention) params.set("attention", state.explorerAttention);
    return params;
  }

  async function loadRecords() {
    const response = await fetch(`/api/records?${filters()}`);
    const data = await response.json();
    state.total = data.total;
    state.lastItems = data.items;
    $("#result-summary").textContent =
      `พบ ${data.total.toLocaleString()} ระเบียน${state.explorerContextLabel ? ` · ${state.explorerContextLabel}` : ""}`;
    $("#records-body").innerHTML = data.items.map(renderRecordRow).join("")
      || `<tr><td colspan="6" class="muted">ไม่พบข้อมูลตามเงื่อนไข</td></tr>`;
    $("#page-label").textContent = `หน้า ${state.page} จาก ${Math.max(1, Math.ceil(data.total / state.pageSize))}`;
    $("#previous-page").disabled = state.page === 1;
    $("#next-page").disabled = state.page * state.pageSize >= data.total;
    bindRecordLinks();
  }

  function bindEvents() {
    $("#search-form").addEventListener("submit", (event) => {
      event.preventDefault();
      clearDashboardContext();
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
  }

  return { bindEvents, bindRecordLinks, clearDashboardContext, loadRecords };
}
