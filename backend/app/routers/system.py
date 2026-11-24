"""The web page itself and the health check."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..admin_security import admin_access_configured
from ..config import APP_ENV, FRONTEND_DIR, GOOGLE_SHEETS_AUTO_SYNC_ENABLED
from ..services.google import automatic_sync_available, web_sync_available

router = APIRouter(tags=["system"])
templates = Jinja2Templates(directory=str(FRONTEND_DIR / "templates"))


@router.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "environment": APP_ENV,
        "admin_access_configured": admin_access_configured(),
        "google_sheets_web_sync_available": web_sync_available(),
        "google_sheets_auto_sync_enabled": GOOGLE_SHEETS_AUTO_SYNC_ENABLED,
        "google_sheets_auto_sync_available": automatic_sync_available(),
    }


@router.get("/")
def home(request: Request) -> HTMLResponse:
    response = templates.TemplateResponse(request=request, name="index.html")
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response
