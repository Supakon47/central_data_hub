import { $, compact, escapeHtml } from "../core/dom.js";
import { state } from "../core/state.js";

function renderFields(fields) {
  return fields
    .map(([label, value]) => `<dt>${label}</dt><dd>${compact(value)}</dd>`)
    .join("");
}

function renderRawDataRows(rawData) {
  return Object.entries(rawData || {})
    .map(([key, value]) => `<tr><th>${escapeHtml(key)}</th><td>${compact(value, "")}</td></tr>`)
    .join("");
}

function renderDuplicateCandidates(candidates) {
  if (!candidates?.length) {
    return `<p class="muted">ไม่พบเลขทะเบียนเดียวกันจากแหล่งอื่นในสำเนากลาง</p>`;
  }
  return `<ul>${candidates.map((item) => `<li>
    <button class="record-link" data-record-id="${item.id}">${compact(item.registration_no)}</button>
    — ${escapeHtml(item.source_sheet)}
  </li>`).join("")}</ul>`;
}

function renderLinkedLocations(locations) {
  if (!locations?.length) {
    return `<p class="muted">ยังไม่มีตำแหน่งที่เจ้าหน้าที่อนุมัติการเชื่อม</p>`;
  }
  return `<ul class="linked-locations">${locations.map((item) => {
    const source = item.source || {};
    return `<li>
      <strong>${escapeHtml(item.location?.value || "ไม่ระบุตำแหน่ง")}</strong>
      <span>${escapeHtml(`${source.source_name || ""} / ${source.source_sheet || ""} / แถว ${source.source_row_number || "-"}`)}</span>
      ${item.note ? `<small>${escapeHtml(item.note)}</small>` : ""}
    </li>`;
  }).join("")}</ul>`;
}

// Where the object is stored: the record's own location when it comes from a
// storage-room list, otherwise the locations staff approved for it.
function storageLocations(record) {
  if (record.location?.value) {
    return [{ room: record.source_name, shelf: record.location.value }];
  }
  return (record.linked_locations || [])
    .filter((item) => item.location?.value)
    .map((item) => ({ room: item.source?.source_name, shelf: item.location.value }));
}

function storageFields(record) {
  const locations = storageLocations(record);
  if (!locations.length) {
    return [["ห้องจัดเก็บ", null], ["ชั้นวาง", null]];
  }
  const unique = (values) => [...new Set(values.filter(Boolean))].join("\n");
  return [
    ["ห้องจัดเก็บ", unique(locations.map((item) => item.room))],
    ["ชั้นวาง", unique(locations.map((item) => item.shelf))],
  ];
}

function galleryImages(record) {
  if (record.images?.length) return record.images;
  return record.image_url ? [{ url: record.image_url, position: 1, origin: "legacy" }] : [];
}

function renderImagePane(record) {
  const images = galleryImages(record);
  if (!images.length) {
    const message = record.status_photographed
      ? "ระบุว่าถ่ายภาพแล้ว แต่ยังไม่มีภาพที่นำเข้าในคลังกลาง"
      : "ยังไม่มีภาพสำหรับระเบียนนี้";
    return `<section class="detail-media-pane image-unavailable"><p>${message}</p></section>`;
  }
  const primary = images[0];
  const thumbnails = images.map((image, index) => {
    const imageNumber = index + 1;
    return `<button class="detail-thumbnail${index === 0 ? " active" : ""}" type="button"
      data-detail-image-url="${escapeHtml(image.url)}"
      data-detail-image-alt="ภาพที่ ${imageNumber} ของ ${escapeHtml(record.registration_no || "ระเบียน")}">
      <img src="${escapeHtml(image.url)}" alt="" loading="lazy">
    </button>`;
  }).join("");
  return `<section class="detail-media-pane">
    <a id="detail-hero-link" class="detail-hero-link" href="${escapeHtml(primary.url)}" target="_blank" rel="noreferrer">
      <img id="detail-hero-image" src="${escapeHtml(primary.url)}" alt="ภาพที่ 1 ของ ${escapeHtml(record.registration_no || "ระเบียน")}">
    </a>
    ${images.length > 1 ? `<div class="detail-thumbnails" aria-label="เลือกรูปภาพ">${thumbnails}</div>` : ""}
    <p class="detail-image-caption">คลิกภาพเพื่อเปิดขนาดเต็ม · ${images.length.toLocaleString()} รูป</p>
  </section>`;
}

function statusBox(label, value, completedValue) {
  const tone = !value ? "empty" : value === completedValue ? "complete" : "pending";
  return `<article class="detail-status ${tone}">
    <span>${label}</span><strong>${compact(value, "ไม่ได้บันทึก")}</strong>
  </article>`;
}

function renderRecordNavigation(recordId) {
  const index = state.lastItems.findIndex((item) => String(item.id) === String(recordId));
  if (index < 0) return "";
  const previous = state.lastItems[index - 1];
  const next = state.lastItems[index + 1];
  return `<div class="detail-record-navigation">
    <button class="secondary" type="button" data-detail-record-id="${previous?.id ?? ""}" ${previous ? "" : "disabled"}>ก่อนหน้า</button>
    <span>${(index + 1).toLocaleString()} / ${state.lastItems.length.toLocaleString()}</span>
    <button type="button" data-detail-record-id="${next?.id ?? ""}" ${next ? "" : "disabled"}>ถัดไป</button>
  </div>`;
}

function renderSourceDetails(rawRows) {
  if (!rawRows) return "";
  return `<details class="source-details detail-section">
    <summary>ดูข้อมูลต้นทางที่นำเข้า</summary>
    <p class="muted">ข้อมูลนี้เก็บไว้เพื่อการตรวจสอบย้อนกลับจากชีตต้นทาง</p>
    <div class="table-wrap"><table class="raw-table"><tbody>${rawRows}</tbody></table></div>
  </details>`;
}

export function createDetailController({ bindRecordLinks, pushRoute, setView }) {
  async function loadDetail(recordId, updateHistory = true) {
    if (updateHistory) pushRoute("detail", recordId);
    const record = await (await fetch(`/api/records/${recordId}`)).json();
    state.currentDetailId = recordId;
    setView("detail");
    const fields = [
      ["เลขทะเบียนเดิม", record.previous_registration_no],
      ["รายการ", record.title_description],
      ["ขนาด", record.dimensions_text],
      ["ชนิด", record.material],
      ["อายุสมัย", record.period],
      ["ประวัติที่มา", record.provenance],
      ...storageFields(record),
    ];
    $("#detail-content").innerHTML = `<article class="detail-card">
      <div class="detail-layout">
        ${renderImagePane(record)}
        <section class="detail-info-pane">
          <p class="detail-accession">${compact(record.registration_no, "ไม่มีเลขทะเบียน")}</p>
          <h2>${compact(record.title_description, "ไม่ระบุรายการ")}</h2>
          <dl class="detail-grid">${renderFields(fields)}</dl>
          <div class="detail-status-grid">
            ${statusBox("การตรวจสอบข้อมูล", record.status_data_check, "ตรวจสอบแล้ว")}
            ${statusBox("การถ่ายภาพ", record.status_photographed, "ถ่ายภาพแล้ว")}
            ${statusBox("การลงระบบ Antique", record.status_antique, "ลงระบบแล้ว")}
            ${statusBox("การส่งขึ้นห้องคลัง", record.status_storage, "ส่งขึ้นห้องคลังแล้ว")}
          </div>
          <p class="detail-source">${escapeHtml(`${record.source_name || ""} / ${record.source_sheet || ""} / แถว ${record.source_row_number || "-"}`)}</p>
          ${renderRecordNavigation(record.id)}
        </section>
      </div>
      <div class="detail-extras">
        ${renderSourceDetails(renderRawDataRows(record.raw_data))}
        <div class="detail-section">
          <h3>ตำแหน่งจัดเก็บที่ยืนยันแล้ว</h3>
          <p class="muted">แสดงเฉพาะความสัมพันธ์ที่ผู้ดูแลอนุมัติจากหลักฐานต้นทาง ไม่ใช่การแก้ไข Excel ต้นฉบับ</p>
          ${renderLinkedLocations(record.linked_locations)}
        </div>
        <div class="detail-section">
          <h3>ระเบียนที่อาจซ้ำ</h3>
          <p class="muted">แสดงจากเลขทะเบียนเดียวกันเท่านั้น และไม่ยืนยันว่าเป็นข้อมูลชิ้นเดียวกัน</p>
          ${renderDuplicateCandidates(record.duplicate_candidates)}
        </div>
      </div>
    </article>`;
    bindRecordLinks("#detail-content [data-record-id]");
    document.querySelectorAll("[data-detail-record-id]").forEach((button) => {
      button.addEventListener("click", () => {
        if (button.dataset.detailRecordId) loadDetail(button.dataset.detailRecordId);
      });
    });
    document.querySelectorAll(".detail-thumbnail").forEach((button) => {
      button.addEventListener("click", () => {
        $("#detail-hero-image").src = button.dataset.detailImageUrl;
        $("#detail-hero-image").alt = button.dataset.detailImageAlt;
        $("#detail-hero-link").href = button.dataset.detailImageUrl;
        document.querySelectorAll(".detail-thumbnail").forEach((item) =>
          item.classList.toggle("active", item === button),
        );
      });
    });
  }

  return { loadDetail };
}
