"""Read-only Google Sheets client used only by the sync command.

The web application never accepts a spreadsheet ID or service-account
credential from a request. Both are configured by an administrator first.
"""

from dataclasses import dataclass
import json
from pathlib import Path
import re

from .config import (
    GOOGLE_SERVICE_ACCOUNT_FILE,
    GOOGLE_SERVICE_ACCOUNT_JSON,
    GOOGLE_SHEETS_ENABLED,
)


READONLY_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
RANGE_PATTERN = re.compile(r"^[A-Za-z0-9:$]+$")


class GoogleSheetsConfigurationError(RuntimeError):
    """Raised when a safe read-only sync has not been configured yet."""


@dataclass(frozen=True)
class GoogleSheetSource:
    spreadsheet_id: str
    sheet_name: str
    read_range: str = "A:ZZ"

    @property
    def a1_range(self) -> str:
        read_range = self.read_range.strip()
        if not RANGE_PATTERN.fullmatch(read_range):
            raise GoogleSheetsConfigurationError(
                "read_range ต้องเป็น A1 notation เฉพาะคอลัมน์/แถว เช่น A:Z หรือ A1:Z500"
            )
        sheet_name = self.sheet_name.replace("'", "''")
        return f"'{sheet_name}'!{read_range}"


def _credential_info() -> dict:
    if not GOOGLE_SHEETS_ENABLED:
        raise GoogleSheetsConfigurationError(
            "Google Sheets sync ยังปิดอยู่: ตั้ง GOOGLE_SHEETS_ENABLED=true ก่อนสั่ง sync"
        )
    if GOOGLE_SERVICE_ACCOUNT_JSON and GOOGLE_SERVICE_ACCOUNT_FILE:
        raise GoogleSheetsConfigurationError(
            "กำหนด credential ได้เพียง GOOGLE_SERVICE_ACCOUNT_JSON หรือ GOOGLE_SERVICE_ACCOUNT_FILE อย่างใดอย่างหนึ่ง"
        )
    raw_json = GOOGLE_SERVICE_ACCOUNT_JSON
    if GOOGLE_SERVICE_ACCOUNT_FILE:
        credential_path = Path(GOOGLE_SERVICE_ACCOUNT_FILE)
        if not credential_path.is_file():
            raise GoogleSheetsConfigurationError("ไม่พบไฟล์ service account ที่กำหนดใน container")
        raw_json = credential_path.read_text(encoding="utf-8")
    if not raw_json:
        raise GoogleSheetsConfigurationError(
            "ยังไม่ได้ตั้งค่า service account: กำหนด GOOGLE_SERVICE_ACCOUNT_FILE หรือ GOOGLE_SERVICE_ACCOUNT_JSON"
        )
    try:
        info = json.loads(raw_json)
    except json.JSONDecodeError as error:
        raise GoogleSheetsConfigurationError("service-account JSON ไม่ถูกต้อง") from error
    if not isinstance(info, dict) or info.get("type") != "service_account":
        raise GoogleSheetsConfigurationError("credential ต้องเป็น Google service-account JSON")
    return info


def fetch_values(source: GoogleSheetSource) -> list[list[object]]:
    """Fetch formatted cell values from one pre-approved tab, with read-only scope."""
    if not source.spreadsheet_id.strip() or not source.sheet_name.strip():
        raise GoogleSheetsConfigurationError("แหล่งข้อมูล Google Sheets ต้องมี spreadsheet ID และชื่อชีต")
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as error:
        raise GoogleSheetsConfigurationError(
            "ยังไม่ได้ติดตั้ง Google Sheets dependencies; rebuild container หลังอัปเดต requirements"
        ) from error

    credentials = service_account.Credentials.from_service_account_info(
        _credential_info(), scopes=[READONLY_SCOPE]
    )
    service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    response = service.spreadsheets().values().get(
        spreadsheetId=source.spreadsheet_id,
        range=source.a1_range,
        majorDimension="ROWS",
        valueRenderOption="FORMATTED_VALUE",
    ).execute()
    return [list(row) for row in response.get("values", [])]
