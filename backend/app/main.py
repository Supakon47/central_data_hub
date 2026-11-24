"""Central Data Hub web application: wires the routers, static files and background sync."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from .automatic_sync import automatic_sync_loop
from .config import APP_NAME, AUTO_SYNC_POLL_SECONDS, FRONTEND_DIR, IMAGE_STORAGE_DIR
from .database import Base, engine
from .routers import admin_auth, admin_records, admin_sources, dashboard, locations, quality, records, system
from .services.google import automatic_sync_available


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Tables are created on start; there are no migrations yet.
    Base.metadata.create_all(bind=engine)
    task = None
    if automatic_sync_available():
        task = asyncio.create_task(automatic_sync_loop(AUTO_SYNC_POLL_SECONDS))
    yield
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title=APP_NAME, version="0.1.0", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="assets")
app.mount("/media", StaticFiles(directory=IMAGE_STORAGE_DIR), name="media")


@app.middleware("http")
async def disable_asset_cache_in_demo(request: Request, call_next):
    """Ensure a local pilot always receives the current frontend files."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


for module in (system, records, dashboard, quality, locations, admin_auth, admin_sources, admin_records):
    app.include_router(module.router)
