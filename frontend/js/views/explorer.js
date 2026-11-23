import { $, badge, compact, escapeHtml } from "../core/dom.js";
import { state } from "../core/state.js";

function renderRecordRow(record) {
  const thumbnail = record.image_url
    ? `<img class="record-thumbnail" src="${escapeHtml(record.image_url)}" alt="" loading="lazy">`
    : `<span class="record-thumbnail placeholder">–</span>`;
  return `<tr>
    <td>${thumbnail}</td>
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

function renderRecordCard(record) {
  const image = record.image_url
    ? `<img src="${escapeHtml(record.image_url)}" alt="${escapeHtml(record.title_description || record.registration_no || "ภาพวัตถุ")}" loading="lazy">`
    : `<div class="record-image-placeholder">ยังไม่มีภาพ</div>`;
  return `<article class="record-card" data-record-id="${record.id}" tabindex="0">
    <div class="record-image">${image}</div>
    <div class="record-card-body">
      <p class="record-accession">${compact(record.registration_no, "ไม่มีเลขทะเบียน")}</p>
      <h3>${compact(record.title_description, "ไม่ระบุรายการ")}</h3>
      <div class="record-tags"><span>${compact(record.material, "ไม่ระบุชนิด")}</span><span>${compact(record.period, "ไม่ระบุอายุสมัย")}</span></div>
      <p class="record-source">${escapeHtml(record.source_sheet || record.source_name || "ไม่ระบุแหล่งข้อมูล")}</p>
    </div>
  </article>`;
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
    [
      "q",
      "source_sheet",
      "registration_year",
      "material",
      "period",
      "status_data_check",
      "status_photographed",
      "status_antique",
      "status_storage",
      "has_description",
      "has_image",
      "sort_by",
    ].forEach((name) => {
      const value = document.querySelector(`[name="${name}"]`).value.trim();
      if (value) params.set(name, value);
    });
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
      || `<tr><td colspan="7" class="muted">ไม่พบข้อมูลตามเงื่อนไข</td></tr>`;
    $("#records-cards").innerHTML = data.items.map(renderRecordCard).join("")
      || `<p class="muted">ไม่พบข้อมูลตามเงื่อนไข</p>`;
    $("#page-label").textContent = `หน้า ${state.page} จาก ${Math.max(1, Math.ceil(data.total / state.pageSize))}`;
    $("#previous-page").disabled = state.page === 1;
    $("#next-page").disabled = state.page * state.pageSize >= data.total;
    bindRecordLinks();
    document.querySelectorAll(".record-card").forEach((card) => {
      const openDetail = () => navigate("detail", card.dataset.recordId);
      card.addEventListener("click", openDetail);
      card.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") openDetail();
      });
    });
  }

  function bindEvents() {
    $("#search-form").addEventListener("submit", (event) => {
      event.preventDefault();
      clearDashboardContext();
      state.page = 1;
      loadRecords();
    });
    $("#reset-filters").addEventListener("click", () => {
      $("#search-form").reset();
      clearDashboardContext();
      state.page = 1;
      loadRecords();
    });
    document.querySelectorAll("#search-form select").forEach((select) => {
      select.addEventListener("change", () => {
        clearDashboardContext();
        state.page = 1;
        loadRecords();
      });
    });
    let queryTimer;
    $("#query").addEventListener("input", () => {
      window.clearTimeout(queryTimer);
      queryTimer = window.setTimeout(() => {
        clearDashboardContext();
        state.page = 1;
        loadRecords();
      }, 300);
    });
    $("#previous-page").addEventListener("click", () => {
      state.page -= 1;
      loadRecords();
    });
    $("#next-page").addEventListener("click", () => {
      state.page += 1;
      loadRecords();
    });
    document.querySelectorAll("[data-explorer-view]").forEach((button) => {
      button.addEventListener("click", () => {
        state.explorerView = button.dataset.explorerView;
        const cards = state.explorerView === "cards";
        $("#records-cards").hidden = !cards;
        $("#records-table-wrap").hidden = cards;
        document.querySelectorAll("[data-explorer-view]").forEach((item) =>
          item.classList.toggle("active", item === button),
        );
      });
    });
  }

  return { bindEvents, bindRecordLinks, clearDashboardContext, loadRecords };
}
