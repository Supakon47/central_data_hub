"""Optional, in-process scheduler for approved Google Sheets sources.

This is deliberately opt-in through both an environment flag and a per-source
interval. It is designed for the single web container used by this pilot; a
production deployment with multiple web replicas should move scheduling to a
dedicated worker or platform scheduler.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
import threading

from sqlalchemy import select

from .database import Base, SessionLocal, engine
from .models import DataSource, SyncRun
from .sync_google_image_bridge import sync_google_image_bridge
from .sync_google_sheet import sync_google_source


LOGGER = logging.getLogger(__name__)
_RUN_LOCK = threading.Lock()
MAX_ERROR_MESSAGE_LENGTH = 1000


def _last_sync_time(session, source_id: int) -> datetime | None:
    """Return the end time of the latest attempt, including a failed attempt."""
    run = session.scalar(
        select(SyncRun)
        .where(SyncRun.source_id == source_id)
        .order_by(SyncRun.id.desc())
    )
    if run is None:
        return None
    return run.completed_at or run.started_at


def _is_due(last_attempt: datetime | None, interval_minutes: int, now: datetime) -> bool:
    if last_attempt is None:
        return True
    if last_attempt.tzinfo is None:
        last_attempt = last_attempt.replace(tzinfo=timezone.utc)
    return now >= last_attempt + timedelta(minutes=interval_minutes)


def _record_failure(source_id: int, error: Exception) -> None:
    """Keep a visible failed attempt so the next retry respects its schedule."""
    session = SessionLocal()
    try:
        message = str(error).strip() or type(error).__name__
        session.add(
            SyncRun(
                source_id=source_id,
                status="failed",
                completed_at=datetime.now(timezone.utc),
                error_count=1,
                message=f"Automatic sync failed: {message[:MAX_ERROR_MESSAGE_LENGTH]}",
            )
        )
        session.commit()
    except Exception:
        session.rollback()
        LOGGER.exception("Could not record automatic sync failure for source %s", source_id)
    finally:
        session.close()


def _record_bridge_failure(source_id: int, error: Exception) -> None:
    """Preserve a short Image Bridge error without failing the data sync."""
    session = SessionLocal()
    try:
        source = session.get(DataSource, source_id)
        if source and source.image_bridge_config:
            message = str(error).strip() or type(error).__name__
            source.image_bridge_config.last_message = (
                f"automatic image sync failed: {message[:MAX_ERROR_MESSAGE_LENGTH]}"
            )
            session.commit()
    except Exception:
        session.rollback()
        LOGGER.exception("Could not record automatic image sync failure for source %s", source_id)
    finally:
        session.close()


def _due_sources() -> list[tuple[int, str, bool]]:
    """Find eligible sources without keeping a database session during I/O."""
    now = datetime.now(timezone.utc)
    session = SessionLocal()
    try:
        sources = session.scalars(
            select(DataSource)
            .where(
                DataSource.connection_type == "google_sheets",
                DataSource.is_active.is_(True),
                DataSource.sync_frequency_minutes.is_not(None),
            )
            .order_by(DataSource.id)
        ).all()
        due = []
        for source in sources:
            interval = source.sync_frequency_minutes
            if interval and _is_due(_last_sync_time(session, source.id), interval, now):
                due.append((source.id, source.name, source.image_bridge_config is not None))
        return due
    finally:
        session.close()


def run_due_google_syncs() -> list[dict]:
    """Synchronise all due sources once, returning a small operational summary."""
    if not _RUN_LOCK.acquire(blocking=False):
        return [{"status": "skipped", "reason": "another automatic sync is already running"}]
    try:
        Base.metadata.create_all(bind=engine)
        results = []
        for source_id, source_name, has_image_bridge in _due_sources():
            try:
                data_result = sync_google_source(source_name)
                result = {
                    "source_id": source_id,
                    "source_name": source_name,
                    "status": "completed",
                    "rows_read": data_result.get("rows_read", 0),
                }
            except Exception as error:
                LOGGER.exception("Automatic sync failed for source %s", source_name)
                _record_failure(source_id, error)
                results.append({"source_id": source_id, "source_name": source_name, "status": "failed"})
                continue

            if has_image_bridge:
                try:
                    image_result = sync_google_image_bridge(source_name)
                    result["images_changed"] = image_result.get("changed_images", 0)
                except Exception as error:
                    LOGGER.exception("Automatic image sync failed for source %s", source_name)
                    _record_bridge_failure(source_id, error)
                    result["image_status"] = "failed"
            results.append(result)
        return results
    finally:
        _RUN_LOCK.release()


async def automatic_sync_loop(poll_seconds: int) -> None:
    """Run due work in a thread so remote Google requests never block FastAPI."""
    while True:
        try:
            results = await asyncio.to_thread(run_due_google_syncs)
            if results:
                LOGGER.info("Automatic Google Sheets sync results: %s", results)
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("Automatic Google Sheets scheduler loop failed")
        await asyncio.sleep(poll_seconds)
