"""Administrator management of data sources: Google Sheets, Image Bridge, central copies.

The browser only ever sends a central source ID. Spreadsheet IDs, tab
allow-lists and credentials are resolved on the server, so a user cannot point
the system at an arbitrary sheet. No route here writes to a Google file.
"""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..configure_google_sheet import configure_google_sheet
from ..dependencies import AdminDep, SessionDep
from ..google_sheets import GoogleSheetsConfigurationError, normalise_drive_folder_id, normalise_spreadsheet_id
from ..inspect_google_image_bridge import inspect_google_image_bridge
from ..models import DataQualityIssue, DataSource, ImageBridgeConfig, Record, SourceSheetConfig, SyncRun
from ..normalization import clean_multiline_text, clean_text
from ..schemas import GoogleSheetConfigMutation, ImageBridgeConfigMutation, SyncScheduleMutation
from ..services.audit import add_audit
from ..services.google import (
    automatic_sync_available,
    get_google_sheet_source,
    google_errors,
    require_web_sync_configured,
)
from ..services.images import remove_xlsx_image_cache
from ..services.records import sheet_configs
from ..sync_google_image_bridge import sync_google_image_bridge
from ..sync_google_sheet import sync_google_source

router = APIRouter(tags=["admin: data sources"])

BRIDGE_DISCONNECT_KEPT = ["ข้อมูลกลาง", "รูปภาพที่ดึงมาแล้ว", "Google Drive ต้นทาง"]


def count_rows(session: Session, model, source_id: int) -> int:
    return session.scalar(select(func.count()).select_from(model).where(model.source_id == source_id)) or 0


def delete_central_rows(session: Session, source_id: int) -> tuple[int, int]:
    """Delete a source's quality issues and records; return how many of each."""
    records = session.scalars(select(Record).where(Record.source_id == source_id)).all()
    issue_count = count_rows(session, DataQualityIssue, source_id)
    for issue in session.scalars(select(DataQualityIssue).where(DataQualityIssue.source_id == source_id)).all():
        session.delete(issue)
    session.flush()
    for record in records:
        session.delete(record)
    return len(records), issue_count


@router.get("/api/admin/google-sheets")
def admin_google_sheet_sources(session: SessionDep, _: AdminDep) -> dict:
    """Return the editable allow-list only to an authenticated administrator."""
    sources = session.scalars(
        select(DataSource).where(DataSource.connection_type == "google_sheets").order_by(DataSource.name)
    ).all()
    return {"sources": [{
        "id": source.id,
        "name": source.name,
        "spreadsheet_id": source.external_id,
        "owner_name": source.owner_name,
        "description": source.description,
        "is_active": source.is_active,
        "sync_frequency_minutes": source.sync_frequency_minutes,
        "sheets": [{
            "name": config.sheet_name,
            "read_range": config.read_range,
            "is_active": config.is_active,
        } for config in sheet_configs(session, source.id)],
        "image_bridge": ({
            "configured": True,
            "drive_folder_id": source.image_bridge_config.drive_folder_id,
            "manifest_file_name": source.image_bridge_config.manifest_file_name,
            "is_active": source.image_bridge_config.is_active,
            "last_synced_at": source.image_bridge_config.last_synced_at,
            "last_message": source.image_bridge_config.last_message,
        } if source.image_bridge_config else {"configured": False}),
    } for source in sources]}


@router.put("/api/admin/google-sheets/{source_id}/sync-schedule")
def update_google_sheet_sync_schedule(
    source_id: int, payload: SyncScheduleMutation, session: SessionDep, _: AdminDep,
) -> dict:
    """Set a source-specific interval; the server-wide automatic switch stays separate."""
    source = get_google_sheet_source(session, source_id)
    before = {"sync_frequency_minutes": source.sync_frequency_minutes}
    source.sync_frequency_minutes = payload.sync_frequency_minutes
    after = {"sync_frequency_minutes": source.sync_frequency_minutes}
    add_audit(session, "update_google_sheet_sync_schedule", source.id, before, after, entity_type="data_source")
    session.commit()
    return {
        "source_id": source.id,
        "source_name": source.name,
        "sync_frequency_minutes": source.sync_frequency_minutes,
        "automatic_sync_server_enabled": automatic_sync_available(),
    }


@router.post("/api/admin/google-sheets")
def configure_google_sheet_from_web(payload: GoogleSheetConfigMutation, session: SessionDep, _: AdminDep) -> dict:
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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="กรุณากรอกชื่อแหล่งข้อมูล, URL/Spreadsheet ID และชื่อแท็บ",
        )
    try:
        values["spreadsheet_id"] = normalise_spreadsheet_id(values["spreadsheet_id"])
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
    existing_source = session.scalar(select(DataSource).where(DataSource.name == values["source_name"]))
    if (
        existing_source
        and existing_source.connection_type == "google_sheets"
        and existing_source.external_id != values["spreadsheet_id"]
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ชื่อแหล่งข้อมูลนี้ผูกกับ Spreadsheet ID อื่นอยู่แล้ว กรุณาใช้ชื่อแหล่งข้อมูลใหม่",
        )
    try:
        result = configure_google_sheet(**values)
    except (ValueError, GoogleSheetsConfigurationError) as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error

    add_audit(session, "configure", result["source_id"], None, {
        "source_name": result["source_name"],
        "sheet_name": result["sheet_name"],
        "read_range": result["read_range"],
    }, entity_type="data_source")
    session.commit()
    return result


@router.post("/api/admin/google-sheets/{source_id}/preview")
def preview_google_sheets_from_web(source_id: int, session: SessionDep, _: AdminDep) -> dict:
    """Read the approved tabs without saving anything."""
    require_web_sync_configured()
    source = get_google_sheet_source(session, source_id)
    with google_errors(
        "ไม่สามารถตรวจสอบ Google Sheets ได้ โปรดตรวจสิทธิ์การแชร์ชีตและการเชื่อมต่อ",
        value_error_is_input=False,
    ):
        return {"source_id": source.id, "source_name": source.name, **sync_google_source(source.name, dry_run=True)}


@router.post("/api/admin/google-sheets/{source_id}/sync")
def sync_google_sheets_from_web(source_id: int, session: SessionDep, _: AdminDep) -> dict:
    """Sync one pre-approved Google Sheets source after an admin confirms it."""
    require_web_sync_configured()
    source = get_google_sheet_source(session, source_id)
    if not source.is_active:
        raise HTTPException(status_code=409, detail="แหล่งข้อมูลนี้ถูกปิดการใช้งาน")
    with google_errors("ไม่สามารถอ่าน Google Sheets ได้ โปรดตรวจสิทธิ์การแชร์ชีตและการเชื่อมต่อ แล้วลองใหม่"):
        result = sync_google_source(source.name)
    add_audit(session, "sync", source.id, None, result, entity_type="data_source")
    session.commit()
    return {"source_id": source.id, "source_name": source.name, **result}


@router.post("/api/admin/sources/{source_id}/clear-central-data")
def clear_source_central_copy(source_id: int, session: SessionDep, _: AdminDep) -> dict:
    """Remove an imported source's central copy without touching its origin.

    Supports approved Google Sheets and Excel imports. Source configuration,
    original files, previous sync history, and audit history remain available
    so the same source can be imported or synced again later.
    """
    source = session.get(DataSource, source_id)
    if source is None or source.connection_type not in {"google_sheets", "xlsx_import"}:
        raise HTTPException(status_code=404, detail="ไม่พบแหล่งข้อมูลที่สามารถล้างสำเนากลางได้")

    record_count, issue_count = delete_central_rows(session, source.id)
    result = {
        "source_id": source.id,
        "source_name": source.name,
        "connection_type": source.connection_type,
        "deleted_records": record_count,
        "deleted_quality_issues": issue_count,
        "kept": ["ไฟล์ต้นฉบับ", "การตั้งค่าแหล่งข้อมูล", "ประวัติการ sync", "audit log"],
    }
    add_audit(session, "clear_central_data", source.id, {
        "record_count": record_count,
        "quality_issue_count": issue_count,
    }, result, entity_type="data_source")
    session.commit()
    # Excel's embedded-image cache is the only source-level media directory.
    # Remove it only after the database deletion has committed successfully.
    result["deleted_images"] = remove_xlsx_image_cache(source.name) if source.connection_type == "xlsx_import" else 0
    return result


@router.delete("/api/admin/google-sheets/{source_id}")
def delete_google_sheet_source(source_id: int, session: SessionDep, _: AdminDep) -> dict:
    """Forget an approved Google Sheets connection and its central copy.

    This intentionally never calls Google APIs to change the original
    spreadsheet. Audit logs are preserved because their entity IDs are stored
    as plain historical references.
    """
    source = get_google_sheet_source(session, source_id)
    source_name = source.name
    sync_count = count_rows(session, SyncRun, source.id)
    record_count, issue_count = delete_central_rows(session, source.id)
    for model in (SyncRun, SourceSheetConfig):
        for row in session.scalars(select(model).where(model.source_id == source.id)).all():
            session.delete(row)
    if source.image_bridge_config:
        session.delete(source.image_bridge_config)

    result = {
        "deleted": True,
        "source_id": source.id,
        "source_name": source_name,
        "deleted_records": record_count,
        "deleted_quality_issues": issue_count,
        "deleted_sync_history": sync_count,
        "kept": ["Google Sheets ต้นฉบับ", "audit log"],
    }
    add_audit(session, "delete_google_sheet_source", source.id, {
        "source_name": source_name,
        "record_count": record_count,
        "quality_issue_count": issue_count,
        "sync_run_count": sync_count,
    }, result, entity_type="data_source")
    session.delete(source)
    session.commit()
    return result


@router.put("/api/admin/google-sheets/{source_id}/image-bridge")
def configure_image_bridge_from_web(
    source_id: int, payload: ImageBridgeConfigMutation, session: SessionDep, _: AdminDep,
) -> dict:
    """Allow-list one Drive folder that contains a Script-owned image manifest."""
    source = get_google_sheet_source(session, source_id)
    folder_value = clean_text(payload.drive_folder_id)
    manifest_file_name = clean_text(payload.manifest_file_name)
    if not folder_value or not manifest_file_name or "/" in manifest_file_name or "\\" in manifest_file_name:
        raise HTTPException(status_code=422, detail="กรุณาระบุ Drive folder URL/ID และชื่อไฟล์ manifest ที่ปลอดภัย")
    try:
        folder_id = normalise_drive_folder_id(folder_value)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    bridge = source.image_bridge_config
    before = None
    if bridge is None:
        bridge = ImageBridgeConfig(
            source_id=source.id,
            drive_folder_id=folder_id,
            manifest_file_name=manifest_file_name,
            is_active=True,
        )
        session.add(bridge)
    else:
        before = {"drive_folder_id": bridge.drive_folder_id, "manifest_file_name": bridge.manifest_file_name}
        bridge.drive_folder_id = folder_id
        bridge.manifest_file_name = manifest_file_name
        bridge.is_active = True
    session.flush()
    after = {"drive_folder_id": bridge.drive_folder_id, "manifest_file_name": bridge.manifest_file_name}
    add_audit(session, "configure_image_bridge", bridge.id, before, after, entity_type="image_bridge")
    session.commit()
    return {"source_id": source.id, "configured": True, **after}


@router.post("/api/admin/google-sheets/{source_id}/image-bridge/inspect")
def inspect_image_bridge_from_web(source_id: int, session: SessionDep, _: AdminDep) -> dict:
    """Read-only check that the service account can see a Bridge folder."""
    require_web_sync_configured()
    source = get_google_sheet_source(session, source_id)
    with google_errors("ไม่สามารถตรวจสอบ Image Bridge ได้ โปรดตรวจสิทธิ์การแชร์โฟลเดอร์ Google Drive"):
        return inspect_google_image_bridge(source.name)


@router.post("/api/admin/google-sheets/{source_id}/image-bridge/preview")
def preview_image_bridge_from_web(source_id: int, session: SessionDep, _: AdminDep) -> dict:
    """Read and match Bridge contents without changing central image records."""
    require_web_sync_configured()
    source = get_google_sheet_source(session, source_id)
    with google_errors("ไม่สามารถทดลองดึงรูปจาก Image Bridge ได้ โปรดตรวจโฟลเดอร์และ manifest"):
        result = sync_google_image_bridge(source.name, dry_run=True)
    return {"source_id": source.id, "source_name": source.name, **result}


@router.post("/api/admin/google-sheets/{source_id}/image-bridge/sync")
def sync_image_bridge_from_web(source_id: int, session: SessionDep, _: AdminDep) -> dict:
    """Pull only manifest-listed image files; never exports or writes a Sheet."""
    require_web_sync_configured()
    source = get_google_sheet_source(session, source_id)
    with google_errors("ไม่สามารถดึงคลังภาพจาก Google Drive ได้ โปรดตรวจโฟลเดอร์ที่แชร์และไฟล์ manifest"):
        result = sync_google_image_bridge(source.name)
    add_audit(session, "sync_image_bridge", source.id, None, result, entity_type="image_bridge")
    session.commit()
    return {"source_id": source.id, "source_name": source.name, **result}


@router.delete("/api/admin/google-sheets/{source_id}/image-bridge")
def disconnect_image_bridge_from_web(source_id: int, session: SessionDep, _: AdminDep) -> dict:
    """Forget one Bridge configuration without deleting records or their images."""
    source = get_google_sheet_source(session, source_id)
    bridge = source.image_bridge_config
    if bridge is None:
        raise HTTPException(status_code=404, detail="แหล่งข้อมูลนี้ยังไม่ได้ตั้งค่า Image Bridge")
    bridge_id = bridge.id
    before = {"drive_folder_id": bridge.drive_folder_id, "manifest_file_name": bridge.manifest_file_name}
    session.delete(bridge)
    add_audit(
        session,
        "disconnect_image_bridge",
        bridge_id,
        before,
        {"source_id": source.id, "kept": BRIDGE_DISCONNECT_KEPT},
        entity_type="image_bridge",
    )
    session.commit()
    return {"source_id": source.id, "disconnected": True, "kept": BRIDGE_DISCONNECT_KEPT}
