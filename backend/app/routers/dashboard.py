"""The Dashboard and the Data Catalog."""

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from ..dependencies import SessionDep
from ..models import DataQualityIssue, DataSource, Record, SyncRun
from ..services.cache import cached_for_records
from ..services.dashboard import dashboard_summary, duplicate_groups
from ..services.records import sheet_configs

router = APIRouter(tags=["dashboard"])


@router.get("/api/dashboard")
def dashboard(session: SessionDep, source_id: int | None = None, source_sheet: str | None = None) -> dict:
    return cached_for_records(
        session,
        f"dashboard:{source_id or ''}:{source_sheet or ''}",
        lambda: dashboard_summary(session, source_id, source_sheet),
    )


@router.get("/api/duplicates")
def duplicate_registration_groups(
    session: SessionDep,
    source_id: int | None = None,
    source_sheet: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """Exact duplicate registration numbers for staff review, not automatic merging."""
    return duplicate_groups(session, source_id, source_sheet, limit)


def image_bridge_status(source: DataSource) -> dict:
    bridge = source.image_bridge_config
    if bridge is None:
        return {"configured": False}
    return {
        "configured": True,
        "is_active": bridge.is_active,
        "manifest_file_name": bridge.manifest_file_name,
        "last_synced_at": bridge.last_synced_at,
        "last_message": bridge.last_message,
    }


def last_sync_summary(run: SyncRun | None) -> dict | None:
    if run is None:
        return None
    return {
        "status": run.status,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "rows_read": run.rows_read,
        "inserted": run.rows_inserted,
        "updated": run.rows_updated,
        "skipped": run.rows_skipped,
        "errors": run.error_count,
        "message": run.message,
    }


@router.get("/api/catalog")
def catalog(session: SessionDep) -> dict:
    sources = session.scalars(select(DataSource).order_by(DataSource.name)).all()
    response = []
    for source in sources:
        last_run = session.scalar(select(SyncRun).where(SyncRun.source_id == source.id).order_by(SyncRun.id.desc()))
        record_count = session.scalar(
            select(func.count()).select_from(Record).where(Record.source_id == source.id)
        ) or 0
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
                for config in sheet_configs(session, source.id)
            ],
            "image_bridge": image_bridge_status(source),
            "record_count": record_count,
            "unresolved_issues": unresolved_issues,
            "last_sync": last_sync_summary(last_run),
        })
    return {"sources": response}
