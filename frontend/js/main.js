// Entry point: create each page's controller, wire them together, and route between pages.
import { getJson } from "./api.js";
import { $ } from "./core/dom.js";
import { state } from "./core/state.js";
import { initialiseTheme } from "./core/theme.js";
import { pushRoute, routeFromLocation } from "./router.js";
import { createAdminPageController, showAdminMessage } from "./views/admin.js";
import { loadAuditLog as loadAudit } from "./views/admin-audit.js";
import { createImageBridgeController } from "./views/admin-image-bridge.js";
import { createImageIntakeController } from "./views/admin-intake.js";
import { createAdminRecordsController } from "./views/admin-records.js";
import { createGoogleSourcesController } from "./views/admin-sources.js";
import { createCatalogController } from "./views/catalog.js";
import { createDashboardController } from "./views/dashboard.js";
import { createDetailController } from "./views/detail.js";
import { createExplorerController } from "./views/explorer.js";
import { createQualityController } from "./views/quality.js";

const BUILD_VERSION = "2026.11.24.2";

// Keep card pages even at the common six-card desktop layout.
state.pageSize = 24;

// Controllers call each other through these small wrappers, so the order in
// which they are created below does not matter.
const loadRecords = () => explorer.loadRecords();
const loadCatalog = () => catalog.loadCatalog();
const loadDashboard = () => dashboard.loadDashboard();
const loadDataQuality = () => quality.loadDataQuality();
const bindRecordLinks = (selector) => explorer.bindRecordLinks(selector);

const explorer = createExplorerController({ navigate });
const dashboard = createDashboardController({ navigate, bindRecordLinks, loadRecords });
const detail = createDetailController({ bindRecordLinks, pushRoute, setView });
const quality = createQualityController({ bindRecordLinks, loadAudit, loadCatalog });
const imageBridge = createImageBridgeController({
  loadAudit,
  loadCatalog,
  reloadSources: () => googleSources.load(),
});
const googleSources = createGoogleSourcesController({
  bindBridgeActions: (container) => imageBridge.bindActions(container),
  loadAudit,
  loadCatalog,
});
const catalog = createCatalogController({
  loadAdminGoogleSources: () => googleSources.load(),
  loadAudit,
  loadDataQuality,
  loadFilterOptions: () => explorer.loadFilterOptions(),
  loadRecords,
  syncImageBridge: (button) => imageBridge.sync(button),
});
const adminRecords = createAdminRecordsController({
  loadAudit,
  loadDashboard,
  loadRecords,
  showMessage: showAdminMessage,
});
const imageIntake = createImageIntakeController({ loadAudit, loadDashboard, loadRecords });
const adminPage = createAdminPageController({ adminRecords, googleSources, imageIntake, loadAudit });

const VIEW_LOADERS = {
  dashboard: loadDashboard,
  catalog: loadCatalog,
  quality: loadDataQuality,
  admin: () => adminPage.loadAdmin(),
};

function setView(view) {
  document.querySelectorAll(".view").forEach((element) => {
    element.classList.toggle("active", element.id === view);
  });
  document.querySelectorAll(".tab").forEach((element) => {
    element.classList.toggle("active", element.dataset.view === view);
  });
  VIEW_LOADERS[view]?.();
}

async function renderRoute() {
  const route = routeFromLocation();
  if (route.view === "detail") await detail.loadDetail(route.recordId, false);
  else setView(route.view);
}

function navigate(view, recordId = null) {
  pushRoute(view, recordId);
  return renderRoute();
}

async function initialise() {
  const health = await getJson("/api/health");
  $("#freshness").textContent =
    health.environment === "development"
      ? `โหมดทดลองในเครื่อง · build ${BUILD_VERSION}`
      : `ระบบพร้อมใช้งาน · build ${BUILD_VERSION}`;
  if (!window.history.state) window.history.replaceState({ view: "explorer" }, "", window.location.href);
  // Filter choices and the first page of records do not depend on each other.
  await Promise.all([explorer.loadFilterOptions(), loadRecords()]);
  await renderRoute();
}

document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => navigate(button.dataset.view));
});
$("[data-back]").addEventListener("click", () => navigate("explorer"));
window.addEventListener("popstate", () => renderRoute());
dashboard.bindEvents();
explorer.bindEvents();
quality.bindEvents();
adminPage.bindEvents();
initialiseTheme();
initialise().catch((error) => {
  $("#freshness").textContent = `เกิดข้อผิดพลาด: ${error.message}`;
});
