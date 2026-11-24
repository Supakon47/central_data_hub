"""Shared guards for the Google Sheets and Drive features used from the web."""

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..config import (
    GOOGLE_SERVICE_ACCOUNT_FILE,
    GOOGLE_SERVICE_ACCOUNT_JSON,
    GOOGLE_SHEETS_AUTO_SYNC_ENABLED,
    GOOGLE_SHEETS_ENABLED,
    GOOGLE_SHEETS_WEB_SYNC_ENABLED,
)
from ..google_sheets import GoogleSheetsConfigurationError
from ..models import DataSource


def service_account_configured() -> bool:
    return GOOGLE_SHEETS_ENABLED and bool(GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_SERVICE_ACCOUNT_JSON)


def web_sync_available() -> bool:
    return GOOGLE_SHEETS_WEB_SYNC_ENABLED and service_account_configured()


def automatic_sync_available() -> bool:
    """Only start automatic work when both credentials and the explicit switch exist."""
    return GOOGLE_SHEETS_AUTO_SYNC_ENABLED and service_account_configured()


def require_web_sync_configured() -> None:
    if not GOOGLE_SHEETS_WEB_SYNC_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ยังไม่ได้เปิดใช้การ sync Google Sheets จากหน้าเว็บ",
        )
    if not service_account_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ยังไม่ได้ตั้งค่า service account สำหรับการ sync บนเว็บ",
        )


def get_google_sheet_source(session: Session, source_id: int) -> DataSource:
    """An approved Google Sheets source, or 404 for any other source."""
    source = session.get(DataSource, source_id)
    if source is None or source.connection_type != "google_sheets":
        raise HTTPException(status_code=404, detail="ไม่พบแหล่งข้อมูล Google Sheets ที่ได้รับอนุมัติ")
    return source


@contextmanager
def google_errors(failure_detail: str, *, value_error_is_input: bool = True) -> Iterator[None]:
    """Turn errors from a Google call into HTTP errors staff can act on.

    Missing configuration is a 503, invalid input (``ValueError``) a 422 when
    ``value_error_is_input`` is set, and anything else a 502 with
    ``failure_detail``, so Google's internal messages never reach the browser.
    """
    try:
        yield
    except GoogleSheetsConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except ValueError as error:
        if value_error_is_input:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=failure_detail) from error
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=failure_detail) from error
