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

function galleryImages(record) {
  if (record.images?.length) return record.images;
  return record.image_url ? [{ url: record.image_url, position: 1, origin: "legacy" }] : [];
}

function renderImageSection(record) {
  const images = galleryImages(record);
  if (!images.length) {
    return record.status_photographed
      ? `<section class="image-unavailable"><h3>รูปภาพ</h3><p class="muted">ระบุว่าถ่ายภาพแล้ว แต่ยังไม่มีภาพที่นำเข้าในคลังกลาง</p></section>`
      : "";
  }
  const gallery = images.map((image, index) => {
    const imageNumber = index + 1;
    const origin = image.origin === "google_sheets_bridge" ? " · จาก Google Sheets" : "";
    return `<a href="${escapeHtml(image.url)}" target="_blank" rel="noreferrer">
      <img src="${escapeHtml(image.url)}" alt="ภาพที่ ${imageNumber} ของ ${compact(record.registration_no, "ระเบียน")}" loading="lazy">
      <span>ภาพที่ ${imageNumber}${origin}</span>
    </a>`;
  }).join("");
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

export function createDetailController({ bindRecordLinks, pushRoute, setView }) {
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
      ["แหล่งข้อมูล", `${record.source_name || ""} / ${record.source_sheet} / แถว ${record.source_row_number}`],
    ];
    $("#detail-content").innerHTML = `<article class="detail-card">
      <h2>${compact(record.registration_no, "ไม่มีเลขทะเบียน")}</h2>
      <div class="detail-layout">
        <dl class="detail-grid detail-section">${renderFields(fields)}</dl>
        ${renderImageSection(record)}
      </div>
      ${renderSourceDetails(renderRawDataRows(record.raw_data))}
      <div class="detail-section">
        <h3>ระเบียนที่อาจซ้ำ</h3>
        <p class="muted">แสดงจากเลขทะเบียนเดียวกันเท่านั้น และไม่ยืนยันว่าเป็นข้อมูลชิ้นเดียวกัน</p>
        ${renderDuplicateCandidates(record.duplicate_candidates)}
      </div>
    </article>`;
    bindRecordLinks("#detail-content [data-record-id]");
  }

  return { loadDetail };
}
