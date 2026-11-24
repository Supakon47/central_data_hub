// Admin page shell: sign-in, sign-out, and loading the page's panels.
import { adminFetch, getJson } from "../api.js";
import { $, escapeHtml, showMessage } from "../core/dom.js";

// The status line at the top of the admin page; record edits report here too.
export function showAdminMessage(text, isError) {
  showMessage("#admin-message", text, isError);
}

export function createAdminPageController({ adminRecords, googleSources, imageIntake, loadAudit }) {
  async function loadSheetOptions() {
    const select = $("#admin-sheet-filter");
    const selected = select.value;
    const data = await getJson("/api/dashboard");
    select.innerHTML = `<option value="">ทุกชีต</option>${data.by_source_sheet.map((item) => `<option value="${escapeHtml(item.label)}">${escapeHtml(item.label)} (${item.count.toLocaleString()})</option>`).join("")}`;
    select.value = [...select.options].some((option) => option.value === selected) ? selected : "";
  }

  async function loadAdmin() {
    const session = await getJson("/api/admin/session");
    $("#admin-login").hidden = session.authenticated || !session.configured;
    $("#admin-content").hidden = !session.authenticated;
    if (!session.configured) {
      showAdminMessage("ผู้ดูแลยังไม่ได้ตั้งรหัสผ่านในไฟล์ .env", true);
      return;
    }
    if (!session.authenticated) {
      showAdminMessage("", false);
      return;
    }
    showAdminMessage("ปลดล็อกหน้าจัดการแล้ว", false);
    adminRecords.renderAdminEditor();
    await loadSheetOptions();
    await Promise.all([
      adminRecords.loadAdminRecords(),
      loadAudit(),
      googleSources.load(),
      imageIntake.loadSources(),
    ]);
  }

  function bindEvents() {
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
        showAdminMessage(error.message, true);
      }
    });
    $("#admin-logout").addEventListener("click", async () => {
      await adminFetch("/api/admin/logout", { method: "POST", body: "{}" });
      await loadAdmin();
    });
    $("#admin-new-record").addEventListener("click", () => adminRecords.renderAdminEditor());
    $("#admin-search-form").addEventListener("submit", (event) => {
      event.preventDefault();
      $("#admin-records-panel").open = true;
      adminRecords.loadAdminRecords();
    });
    $("#admin-image-intake-source").addEventListener("change", () => imageIntake.renderSheets());
    $("#admin-image-intake-form").addEventListener("submit", (event) => imageIntake.upload(event));
    googleSources.bindEvents();
  }

  return { bindEvents, loadAdmin };
}
