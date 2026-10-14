from collections import Counter
from datetime import datetime
import hashlib
import json
import uuid
from typing import Annotated

from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .admin_security import admin_access_configured, create_session_token, valid_session_token, verify_password
from .config import (
    ADMIN_SESSION_TTL_SECONDS,
    APP_ENV,
    APP_NAME,
    FRONTEND_DIR,
    GOOGLE_SERVICE_ACCOUNT_FILE,
    GOOGLE_SERVICE_ACCOUNT_JSON,
    GOOGLE_SHEETS_ENABLED,
    GOOGLE_SHEETS_WEB_SYNC_ENABLED,
    IMAGE_STORAGE_DIR,
    PAGE_SIZE_DEFAULT,
    PAGE_SIZE_MAX,
)
from .configure_google_sheet import configure_google_sheet
from .database import Base, engine, get_session
from .google_sheets import GoogleSheetsConfigurationError
from .models import AuditLog, DataQualityIssue, DataSource, Record, SourceSheetConfig, SyncRun
from .normalization import clean_multiline_text, clean_text, normalise_image_url
from .sync_google_sheet import sync_google_source


app = FastAPI(title=APP_NAME, version="0.1.0")
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="assets")
app.mount("/media", StaticFiles(directory=IMAGE_STORAGE_DIR), name="media")


EDITABLE_RECORD_FIELDS = (
    "registration_no", "previous_registration_no", "title_description", "dimensions_text", "material",
    "period", "provenance", "image_url", "status_data_check", "status_photographed",
    "status_antique", "status_storage",
)
MULTILINE_RECORD_FIELDS = {"title_description", "dimensions_text", "period", "provenance"}
CREATE_REQUIRED_FIELDS = {
    "registration_no": "เลขทะเบียน",
    "title_description": "รายการ",
}


class AdminLogin(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


class RecordMutation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registration_no: str | None = None
    previous_registration_no: str | None = None
    title_description: str | None = None
    dimensions_text: str | None = None
    material: str | None = None
    period: str | None = None
    provenance: str | None = None
    image_url: str | None = None
    status_data_check: str | None = None
    status_photographed: str | None = None
    status_antique: str | None = None
    status_storage: str | None = None


class GoogleSheetConfigMutation(BaseModel):
    """An admin-only allow-list entry; credentials never come from this form."""

    model_config = ConfigDict(extra="forbid")

    source_name: str = Field(min_length=1, max_length=255)
    spreadsheet_id: str = Field(min_length=1, max_length=512)
    sheet_name: str = Field(min_length=1, max_length=255)
    read_range: str = Field(default="A:ZZ", min_length=1, max_length=255)
    owner_name: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=5000)


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


def require_admin(admin_session: Annotated[str | None, Cookie()] = None) -> None:
    if not admin_access_configured():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="ยังไม่ได้ตั้งค่ารหัสผ่านผู้ดูแล")
    if not valid_session_token(admin_session):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ต้องเข้าสู่ระบบผู้ดูแล")


def mutation_values(payload: RecordMutation) -> dict:
    values = {}
    for field in payload.model_fields_set:
        value = getattr(payload, field)
        if field == "image_url":
            values[field] = normalise_image_url(value)
        elif field in MULTILINE_RECORD_FIELDS:
            values[field] = clean_multiline_text(value)
        else:
            values[field] = clean_text(value)
    return values


def require_create_values(values: dict) -> None:
    missing_labels = [label for field, label in CREATE_REQUIRED_FIELDS.items() if not values.get(field)]
    if missing_labels:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"กรุณากรอกข้อมูลบังคับ: {', '.join(missing_labels)}",
        )


def require_google_web_sync_configured() -> None:
    if not GOOGLE_SHEETS_WEB_SYNC_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ยังไม่ได้เปิดใช้การ sync Google Sheets จากหน้าเว็บ",
        )
    if not GOOGLE_SHEETS_ENABLED or not (GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_SERVICE_ACCOUNT_JSON):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ยังไม่ได้ตั้งค่า service account สำหรับการ sync บนเว็บ",
        )


def editable_snapshot(record: Record) -> dict:
    return {field: getattr(record, field) for field in EDITABLE_RECORD_FIELDS}


def record_hash(values: dict) -> str:
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def manual_source(session: Session) -> DataSource:
    source = session.scalar(select(DataSource).where(DataSource.name == "แก้ไขโดยเจ้าหน้าที่"))
    if source is None:
        source = DataSource(
            name="แก้ไขโดยเจ้าหน้าที่",
            owner_name="ผู้ดูแลระบบ",
            description="ระเบียนที่สร้างจากหน้าจัดการข้อมูลของ Central Data Hub",
            connection_type="manual_entry",
            classification="internal",
            is_active=True,
        )
        session.add(source)
        session.flush()
    return source


def add_audit(
    session: Session,
    action: str,
    entity_id: int | str,
    before: dict | None,
    after: dict | None,
    entity_type: str = "record",
) -> None:
    session.add(AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        actor="local-admin",
        before_data=before,
        after_data=after,
    ))


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
        "source_row_number": record.source_row_number,
        "updated_at": record.updated_at,
    }


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "environment": APP_ENV,
        "admin_access_configured": admin_access_configured(),
        "google_sheets_web_sync_available": (
            GOOGLE_SHEETS_WEB_SYNC_ENABLED
            and GOOGLE_SHEETS_ENABLED
            and bool(GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_SERVICE_ACCOUNT_JSON)
        ),
    }


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
    registration_counts = Counter(record.registration_no for record in records if record.registration_no)
    duplicate_registration_counts = {
        registration_no: count for registration_no, count in registration_counts.items() if count > 1
    }

    def counter(field: str) -> list[dict]:
        counts = Counter(getattr(record, field) or "ไม่ระบุ" for record in records)
        return [{"label": label, "count": count} for label, count in counts.most_common()]

    return {
        "total_records": len(records),
        "with_registration_no": sum(bool(record.registration_no) for record in records),
        "with_description": sum(bool(record.title_description) for record in records),
        "with_image_url": sum(bool(record.image_url) for record in records),
        "duplicate_registration_groups": len(duplicate_registration_counts),
        "records_in_duplicate_registration_groups": sum(duplicate_registration_counts.values()),
        "by_source_sheet": counter("source_sheet"),
        "by_data_check": counter("status_data_check"),
        "by_photo": counter("status_photographed"),
        "by_antique": counter("status_antique"),
        "by_storage": counter("status_storage"),
    }


@app.get("/api/duplicates")
def duplicate_registration_groups(
    session: Annotated[Session, Depends(get_session)],
    source_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """Return exact duplicate registration numbers for staff review, not automatic merging."""
    grouped_statement = select(Record.registration_no, func.count(Record.id).label("record_count")).where(
        Record.registration_no.is_not(None),
        Record.registration_no != "",
    )
    if source_id:
        grouped_statement = grouped_statement.where(Record.source_id == source_id)
    grouped_statement = grouped_statement.group_by(Record.registration_no).having(func.count(Record.id) > 1)
    total_groups = session.scalar(select(func.count()).select_from(grouped_statement.subquery())) or 0
    grouped = session.execute(
        grouped_statement.order_by(func.count(Record.id).desc(), Record.registration_no).limit(limit)
    ).all()
    registration_numbers = [row.registration_no for row in grouped]
    records_by_registration: dict[str, list[Record]] = {registration_no: [] for registration_no in registration_numbers}
    if registration_numbers:
        record_statement = select(Record).join(Record.source).where(Record.registration_no.in_(registration_numbers))
        if source_id:
            record_statement = record_statement.where(Record.source_id == source_id)
        for record in session.scalars(record_statement.order_by(Record.registration_no, Record.source_sheet, Record.source_row_number)).all():
            records_by_registration[record.registration_no].append(record)
    return {
        "total_groups": total_groups,
        "groups": [{
            "registration_no": row.registration_no,
            "count": row.record_count,
            "records": [record_summary(record) for record in records_by_registration[row.registration_no]],
        } for row in grouped],
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
            "configured_sheets": [
                {
                    "name": config.sheet_name,
                    "read_range": config.read_range,
                    "header_row_number": config.header_row_number,
                    "is_active": config.is_active,
                }
                for config in session.scalars(select(SourceSheetConfig).where(
                    SourceSheetConfig.source_id == source.id
                ).order_by(SourceSheetConfig.sheet_name)).all()
            ],
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
                "message": last_run.message,
            } if last_run else None,
        })
    return {"sources": response}


@app.get("/api/admin/session")
def admin_session_status(admin_session: Annotated[str | None, Cookie()] = None) -> dict:
    return {
        "configured": admin_access_configured(),
        "authenticated": valid_session_token(admin_session),
    }


@app.post("/api/admin/login")
def admin_login(credentials: AdminLogin, response: Response) -> dict:
    if not admin_access_configured():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="ผู้ดูแลยังไม่ได้เปิดใช้หน้าจัดการข้อมูล")
    if not verify_password(credentials.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="รหัสผ่านไม่ถูกต้อง")
    response.set_cookie(
        key="admin_session",
        value=create_session_token(),
        max_age=max(900, ADMIN_SESSION_TTL_SECONDS),
        httponly=True,
        samesite="strict",
        secure=APP_ENV not in {"development", "test"},
    )
    return {"authenticated": True}


@app.post("/api/admin/logout")
def admin_logout(response: Response) -> dict:
    response.delete_cookie("admin_session", httponly=True, samesite="strict")
    return {"authenticated": False}


@app.get("/api/admin/google-sheets")
def admin_google_sheet_sources(
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[None, Depends(require_admin)],
) -> dict:
    """Return the editable allow-list only to an authenticated administrator."""
    sources = session.scalars(select(DataSource).where(
        DataSource.connection_type == "google_sheets"
    ).order_by(DataSource.name)).all()
    return {"sources": [{
        "id": source.id,
        "name": source.name,
        "spreadsheet_id": source.external_id,
        "owner_name": source.owner_name,
        "description": source.description,
        "is_active": source.is_active,
        "sheets": [{
            "name": config.sheet_name,
            "read_range": config.read_range,
            "is_active": config.is_active,
        } for config in session.scalars(select(SourceSheetConfig).where(
            SourceSheetConfig.source_id == source.id
        ).order_by(SourceSheetConfig.sheet_name)).all()],
    } for source in sources]}


@app.post("/api/admin/google-sheets")
def configure_google_sheet_from_web(
    payload: GoogleSheetConfigMutation,
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[None, Depends(require_admin)],
) -> dict:
    """Add one approved tab to the central Google Sheets allow-list."""
    values = {
        "source_name": clean_text(payload.source_name),
        "spreadsheet_id": clean_text(payload.spreadsheet_id),
        "sheet_name": clean_text(payload.sheet_name),
        "read_range": clean_text(payload.read_range) or "A:ZZ",
        "owner_name": clean_text(payload.owner_name),
        "description": clean_multiline_text(payload.description),
    }
    if not all(values[name] for name in ("source_name", "spreadsheet_id", "sheet_name")):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="กรุณากรอกชื่อแหล่งข้อมูล, Spreadsheet ID และชื่อแท็บ")
    existing_source = session.scalar(select(DataSource).where(DataSource.name == values["source_name"]))
    if existing_source and existing_source.connection_type == "google_sheets" and existing_source.external_id != values["spreadsheet_id"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ชื่อแหล่งข้อมูลนี้ผูกกับ Spreadsheet ID อื่นอยู่แล้ว กรุณาใช้ชื่อแหล่งข้อมูลใหม่",
        )
    try:
        result = configure_google_sheet(**values)
    except (ValueError, GoogleSheetsConfigurationError) as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error

    add_audit(session, "configure", result["source_id"], None, {
        "source_name": result["source_name"],
        "sheet_name": result["sheet_name"],
        "read_range": result["read_range"],
    }, entity_type="data_source")
    session.commit()
    return result


@app.post("/api/admin/google-sheets/{source_id}/preview")
def preview_google_sheets_from_web(
    source_id: int,
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[None, Depends(require_admin)],
) -> dict:
    require_google_web_sync_configured()
    source = session.get(DataSource, source_id)
    if source is None or source.connection_type != "google_sheets":
        raise HTTPException(status_code=404, detail="ไม่พบแหล่งข้อมูล Google Sheets ที่ได้รับอนุมัติ")
    try:
        return {"source_id": source.id, "source_name": source.name, **sync_google_source(source.name, dry_run=True)}
    except GoogleSheetsConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="ไม่สามารถตรวจสอบ Google Sheets ได้ โปรดตรวจสิทธิ์การแชร์ชีตและการเชื่อมต่อ",
        ) from error


@app.post("/api/admin/google-sheets/{source_id}/sync")
def sync_google_sheets_from_web(
    source_id: int,
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[None, Depends(require_admin)],
) -> dict:
    """Sync one pre-approved Google Sheets source after an admin confirms it.

    The browser supplies only a central source ID. The service resolves the
    spreadsheet ID, tab allow-list, and credential on the server, so a user
    cannot point the system at an arbitrary Google Sheet.
    """
    require_google_web_sync_configured()
    source = session.get(DataSource, source_id)
    if source is None or source.connection_type != "google_sheets":
        raise HTTPException(status_code=404, detail="ไม่พบแหล่งข้อมูล Google Sheets ที่ได้รับอนุมัติ")
    if not source.is_active:
        raise HTTPException(status_code=409, detail="แหล่งข้อมูลนี้ถูกปิดการใช้งาน")

    try:
        result = sync_google_source(source.name)
    except GoogleSheetsConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="ไม่สามารถอ่าน Google Sheets ได้ โปรดตรวจสิทธิ์การแชร์ชีตและการเชื่อมต่อ แล้วลองใหม่",
        ) from error

    add_audit(
        session,
        "sync",
        source.id,
        None,
        result,
        entity_type="data_source",
    )
    session.commit()
    return {"source_id": source.id, "source_name": source.name, **result}


@app.post("/api/admin/records", status_code=status.HTTP_201_CREATED)
def create_record(
    payload: RecordMutation,
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[None, Depends(require_admin)],
) -> dict:
    values = mutation_values(payload)
    require_create_values(values)
    source = manual_source(session)
    source_row_key = f"manual-{uuid.uuid4()}"
    record = Record(
        source_id=source.id,
        source_sheet="Manual",
        source_row_number=0,
        source_row_key=source_row_key,
        source_url=None,
        raw_hash=record_hash(values),
        raw_data={"_manual_entry": True, **values},
        **values,
    )
    session.add(record)
    session.flush()
    add_audit(session, "create", record.id, None, editable_snapshot(record))
    session.commit()
    session.refresh(record)
    return record_summary(record)


@app.patch("/api/admin/records/{record_id}")
def update_record(
    record_id: int,
    payload: RecordMutation,
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[None, Depends(require_admin)],
) -> dict:
    record = session.get(Record, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="ไม่พบระเบียน")
    values = mutation_values(payload)
    if not values:
        raise HTTPException(status_code=422, detail="ยังไม่ได้ระบุข้อมูลที่ต้องการแก้ไข")
    before = {field: getattr(record, field) for field in values}
    for field, value in values.items():
        setattr(record, field, value)
    # raw_hash intentionally remains tied to imported raw data. An unchanged
    # source row will not erase a local correction; a changed source row will.
    add_audit(session, "update", record.id, before, {field: getattr(record, field) for field in values})
    session.commit()
    session.refresh(record)
    return record_summary(record)


@app.delete("/api/admin/records/{record_id}")
def delete_record(
    record_id: int,
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[None, Depends(require_admin)],
) -> dict:
    record = session.get(Record, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="ไม่พบระเบียน")
    before = editable_snapshot(record)
    add_audit(session, "delete", record.id, before, None)
    for issue in session.scalars(select(DataQualityIssue).where(DataQualityIssue.record_id == record.id)).all():
        issue.record_id = None
    session.delete(record)
    session.commit()
    return {"deleted": True, "record_id": record_id}


@app.get("/api/admin/audit")
def admin_audit(
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[None, Depends(require_admin)],
) -> dict:
    items = session.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(20)).all()
    return {"items": [{
        "id": item.id,
        "action": item.action,
        "entity_type": item.entity_type,
        "entity_id": item.entity_id,
        "actor": item.actor,
        "created_at": item.created_at,
        "before_data": item.before_data,
        "after_data": item.after_data,
    } for item in items]}


@app.get("/")
def home() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")
