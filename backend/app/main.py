from collections import Counter
from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .config import APP_ENV, APP_NAME, FRONTEND_DIR, PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX
from .database import Base, engine, get_session
from .models import DataQualityIssue, DataSource, Record, SyncRun


app = FastAPI(title=APP_NAME, version="0.1.0")
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="assets")


@app.middleware("http")
async def disable_asset_cache_in_demo(request: Request, call_next):
    """Ensure a local pilot always receives the current frontend files."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.on_event("startup")
def initialise_database() -> None:
    Base.metadata.create_all(bind=engine)


def record_summary(record: Record) -> dict:
    return {
        "id": record.id,
        "registration_no": record.registration_no,
        "previous_registration_no": record.previous_registration_no,
        "title_description": record.title_description,
        "material": record.material,
        "period": record.period,
        "status_data_check": record.status_data_check,
        "status_photographed": record.status_photographed,
        "status_antique": record.status_antique,
        "status_storage": record.status_storage,
        "source_id": record.source_id,
        "source_name": record.source.name if record.source else None,
        "source_sheet": record.source_sheet,
        "updated_at": record.updated_at,
    }


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "environment": APP_ENV}


@app.get("/api/records")
def list_records(
    session: Annotated[Session, Depends(get_session)],
    q: str | None = None,
    source_id: int | None = None,
    source_sheet: str | None = None,
    status_data_check: str | None = None,
    status_photographed: str | None = None,
    status_antique: str | None = None,
    status_storage: str | None = None,
    has_description: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
) -> dict:
    statement = select(Record).join(Record.source)
    if q:
        pattern = f"%{q.strip()}%"
        statement = statement.where(or_(
            Record.registration_no.ilike(pattern),
            Record.previous_registration_no.ilike(pattern),
            Record.title_description.ilike(pattern),
            Record.material.ilike(pattern),
            Record.period.ilike(pattern),
            Record.provenance.ilike(pattern),
        ))
    for column, value in [
        (Record.source_id, source_id),
        (Record.source_sheet, source_sheet),
        (Record.status_data_check, status_data_check),
        (Record.status_photographed, status_photographed),
        (Record.status_antique, status_antique),
        (Record.status_storage, status_storage),
    ]:
        if value is not None:
            statement = statement.where(column == value)
    if has_description is True:
        statement = statement.where(Record.title_description.is_not(None))
    if has_description is False:
        statement = statement.where(Record.title_description.is_(None))

    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    records = session.scalars(
        statement.order_by(Record.registration_no, Record.id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {"items": [record_summary(record) for record in records], "total": total, "page": page, "page_size": page_size}


@app.get("/api/records/{record_id}")
def get_record(record_id: int, session: Annotated[Session, Depends(get_session)]) -> dict:
    record = session.get(Record, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="ไม่พบระเบียน")
    duplicates = []
    if record.registration_no:
        duplicates = session.scalars(select(Record).where(
            Record.registration_no == record.registration_no,
            Record.id != record.id,
        ).limit(20)).all()
    return {
        **record_summary(record),
        "dimensions_text": record.dimensions_text,
        "provenance": record.provenance,
        "image_url": record.image_url,
        "source_url": record.source_url,
        "source_row_number": record.source_row_number,
        "raw_data": record.raw_data,
        "duplicate_candidates": [record_summary(candidate) for candidate in duplicates],
    }


@app.get("/api/dashboard")
def dashboard(session: Annotated[Session, Depends(get_session)], source_id: int | None = None) -> dict:
    statement = select(Record)
    if source_id:
        statement = statement.where(Record.source_id == source_id)
    records = session.scalars(statement).all()

    def counter(field: str) -> list[dict]:
        counts = Counter(getattr(record, field) or "ไม่ระบุ" for record in records)
        return [{"label": label, "count": count} for label, count in counts.most_common()]

    return {
        "total_records": len(records),
        "with_registration_no": sum(bool(record.registration_no) for record in records),
        "with_description": sum(bool(record.title_description) for record in records),
        "with_image_url": sum(bool(record.image_url) for record in records),
        "by_source_sheet": counter("source_sheet"),
        "by_data_check": counter("status_data_check"),
        "by_photo": counter("status_photographed"),
        "by_antique": counter("status_antique"),
        "by_storage": counter("status_storage"),
    }


@app.get("/api/catalog")
def catalog(session: Annotated[Session, Depends(get_session)]) -> dict:
    sources = session.scalars(select(DataSource).order_by(DataSource.name)).all()
    response = []
    for source in sources:
        last_run = session.scalar(select(SyncRun).where(SyncRun.source_id == source.id).order_by(SyncRun.id.desc()))
        record_count = session.scalar(select(func.count()).select_from(Record).where(Record.source_id == source.id)) or 0
        unresolved_issues = session.scalar(select(func.count()).select_from(DataQualityIssue).where(
            DataQualityIssue.source_id == source.id,
            DataQualityIssue.is_resolved.is_(False),
        )) or 0
        response.append({
            "id": source.id,
            "name": source.name,
            "owner_name": source.owner_name,
            "description": source.description,
            "connection_type": source.connection_type,
            "classification": source.classification,
            "sync_frequency_minutes": source.sync_frequency_minutes,
            "is_active": source.is_active,
            "record_count": record_count,
            "unresolved_issues": unresolved_issues,
            "last_sync": {
                "status": last_run.status,
                "started_at": last_run.started_at,
                "completed_at": last_run.completed_at,
                "rows_read": last_run.rows_read,
                "inserted": last_run.rows_inserted,
                "updated": last_run.rows_updated,
                "skipped": last_run.rows_skipped,
                "errors": last_run.error_count,
            } if last_run else None,
        })
    return {"sources": response}


@app.get("/")
def home() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")
