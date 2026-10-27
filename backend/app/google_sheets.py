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
DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
XLSX_EXPORT_MIME_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
RANGE_PATTERN = re.compile(r"^[A-Za-z0-9:$]+$")
SPREADSHEET_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{20,}$")
SPREADSHEET_URL_PATTERN = re.compile(r"/spreadsheets/d/([A-Za-z0-9_-]+)(?:/|$)")


class GoogleSheetsConfigurationError(RuntimeError):
    """Raised when a safe read-only sync has not been configured yet."""


def normalise_spreadsheet_id(value: str) -> str:
    """Accept a Google Sheets URL or an ID, and return only a safe ID."""
    candidate = value.strip()
    url_match = SPREADSHEET_URL_PATTERN.search(candidate)
    if url_match:
        candidate = url_match.group(1)
    if not SPREADSHEET_ID_PATTERN.fullmatch(candidate):
        raise ValueError(
            "กรุณาวาง URL ของ Google Sheets หรือ Spreadsheet ID ที่ถูกต้อง "
            "(URL ต้องมีส่วน /spreadsheets/d/<ID>/)"
        )
    return candidate


def _drive_export_error(error: Exception) -> GoogleSheetsConfigurationError:
    """Turn a Drive API response into a safe, actionable Thai message."""
    response = getattr(error, "resp", None)
    status = getattr(response, "status", None)
    reason = None
    api_message = None
    content = getattr(error, "content", b"")
    if isinstance(content, bytes):
        try:
            content = content.decode("utf-8")
        except UnicodeDecodeError:
            content = ""
    try:
        details = json.loads(content) if content else {}
        errors = details.get("error", {}).get("errors", [])
        reason = errors[0].get("reason") if errors else None
        api_message = details.get("error", {}).get("message")
    except (TypeError, ValueError, AttributeError):
        pass

    if reason in {"accessNotConfigured", "SERVICE_DISABLED"}:
        return GoogleSheetsConfigurationError(
            "Google Drive API ยังไม่พร้อมใน Google Cloud project ของ service account "
            "(ลองรอ 2 นาทีหลังเปิด API แล้ว sync ใหม่)"
        )
    if reason in {"fileNotDownloadable", "cannotDownloadFile", "downloadRestricted"}:
        return GoogleSheetsConfigurationError(
            "เจ้าของ Google Sheet ปิดสิทธิ์ดาวน์โหลด/ส่งออกไฟล์สำหรับผู้ดู จึงดึงรูปที่ฝังไม่ได้"
        )
    if status in {401, 403}:
        return GoogleSheetsConfigurationError(
            "service account เปิดชีตได้ แต่ไม่มีสิทธิ์ export ไฟล์ผ่าน Google Drive "
            "(ตรวจการแชร์ไฟล์ การอนุญาตดาวน์โหลด และนโยบาย Shared Drive/Workspace)"
            + (f" [Google reason: {reason}]" if reason else "")
            + (f" [Google message: {api_message}]" if api_message else "")
        )
    if status == 404:
        return GoogleSheetsConfigurationError(
            "ไม่พบไฟล์ใน Google Drive สำหรับ service account (ตรวจ Spreadsheet ID และการแชร์ไฟล์)"
        )
    if status:
        reason_text = f", reason: {reason}" if reason else ""
        return GoogleSheetsConfigurationError(
            f"Google Drive export ล้มเหลว (HTTP {status}{reason_text})"
        )
    return GoogleSheetsConfigurationError("Google Drive export ล้มเหลวโดยไม่ทราบสาเหตุ")


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


def fetch_values(
    source: GoogleSheetSource,
    value_render_option: str = "FORMATTED_VALUE",
) -> list[list[object]]:
    """Fetch one safe representation of values from an approved tab.

    ``FORMATTED_VALUE`` is used for normal import data. ``FORMULA`` is used
    only as a companion read so an ``=IMAGE(\"https://...\")`` cell can provide
    its URL; Google Sheets otherwise renders that cell as an image rather than
    a readable URL.
    """
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
        valueRenderOption=value_render_option,
    ).execute()
    return [list(row) for row in response.get("values", [])]


def export_workbook_as_xlsx(spreadsheet_id: str) -> bytes:
    """Export one approved Google Sheet as XLSX without modifying its source.

    This is a fallback for pictures inserted into Google Sheets as image
    objects. The Sheets values endpoint does not return their binary content,
    but Google Drive can export an authorised spreadsheet as an XLSX file,
    where the existing embedded-image importer can safely inspect anchors.
    """
    if not spreadsheet_id.strip():
        raise GoogleSheetsConfigurationError("แหล่งข้อมูล Google Sheets ต้องมี spreadsheet ID")
    drive = google_drive_read_service()
    try:
        return drive.files().export(
            fileId=spreadsheet_id,
            mimeType=XLSX_EXPORT_MIME_TYPE,
        ).execute()
    except Exception as error:
        raise _drive_export_error(error) from error


def google_drive_read_service():
    """Build a Drive client with the existing server-side read-only identity."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as error:
        raise GoogleSheetsConfigurationError(
            "ยังไม่ได้ติดตั้ง Google API dependencies; rebuild container หลังอัปเดต requirements"
        ) from error
    credentials = service_account.Credentials.from_service_account_info(
        _credential_info(), scopes=[DRIVE_READONLY_SCOPE]
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def download_drive_file(file_id: str) -> bytes:
    """Read one already-approved Drive file; never writes to Google Drive."""
    if not file_id.strip():
        raise GoogleSheetsConfigurationError("ไม่พบรหัสไฟล์ภาพ Google Drive")
    try:
        return google_drive_read_service().files().get_media(
            fileId=file_id,
            supportsAllDrives=True,
        ).execute()
    except Exception as error:
        raise _drive_export_error(error) from error


def find_drive_file_in_folder(folder_id: str, file_name: str) -> dict | None:
    """Find a manifest by exact name inside one approved Drive folder."""
    if not folder_id.strip() or not file_name.strip():
        raise GoogleSheetsConfigurationError("ต้องระบุ Drive folder ID และชื่อไฟล์ manifest")
    escaped_name = file_name.replace("'", "\\'")
    query = f"'{folder_id}' in parents and name = '{escaped_name}' and trashed = false"
    try:
        response = google_drive_read_service().files().list(
            q=query,
            pageSize=2,
            fields="files(id,name,mimeType,size,modifiedTime)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
    except Exception as error:
        raise _drive_export_error(error) from error
    files = response.get("files", [])
    if len(files) > 1:
        raise GoogleSheetsConfigurationError("พบไฟล์ manifest ชื่อซ้ำในโฟลเดอร์รูปภาพ")
    return files[0] if files else None


def google_drive_file_capabilities(spreadsheet_id: str) -> dict:
    """Return only safe export-related metadata as seen by the service account."""
    if not spreadsheet_id.strip():
        raise GoogleSheetsConfigurationError("แหล่งข้อมูล Google Sheets ต้องมี spreadsheet ID")
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as error:
        raise GoogleSheetsConfigurationError(
            "ยังไม่ได้ติดตั้ง Google API dependencies; rebuild container หลังอัปเดต requirements"
        ) from error

    credentials = service_account.Credentials.from_service_account_info(
        _credential_info(), scopes=[DRIVE_READONLY_SCOPE]
    )
    drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
    try:
        metadata = drive.files().get(
            fileId=spreadsheet_id,
            fields="id,name,mimeType,driveId,capabilities(canDownload,canCopy,canEdit),copyRequiresWriterPermission",
            supportsAllDrives=True,
        ).execute()
    except Exception as error:
        raise _drive_export_error(error) from error
    return {
        "name": metadata.get("name"),
        "mime_type": metadata.get("mimeType"),
        "is_in_shared_drive": bool(metadata.get("driveId")),
        "can_download": metadata.get("capabilities", {}).get("canDownload"),
        "can_copy": metadata.get("capabilities", {}).get("canCopy"),
        "can_edit": metadata.get("capabilities", {}).get("canEdit"),
        "copy_requires_writer_permission": metadata.get("copyRequiresWriterPermission"),
    }
