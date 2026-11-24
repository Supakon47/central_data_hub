"""Pull a safe, manifest-based image gallery from an approved Drive folder.

The paired Apps Script owns all writes to Google Drive.  This service only
reads a JSON manifest and the specific image file IDs it names, then stores a
central copy beside the existing Data Hub media.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import unquote

import openpyxl
from sqlalchemy import or_, select

from .config import IMAGE_STORAGE_DIR
from .database import Base, SessionLocal, engine
from .embedded_images import extract_embedded_images
from .google_sheets import (
    GoogleSheetsConfigurationError,
    download_drive_file,
    find_drive_file_in_folder,
)
from .import_workbook import FIELD_ALIASES
from .models import DataSource, ImageBridgeConfig, Record, RecordImage
from .normalization import clean_text, normalise_header
from .record_images import store_record_image, uploaded_image_suffix

MAX_BRIDGE_IMAGES = 2_000
MAX_BRIDGE_IMAGE_BYTES = 25 * 1024 * 1024
MAX_BRIDGE_SHEET_EXPORTS = 100
MAX_BRIDGE_EXPORT_BYTES = 150 * 1024 * 1024
BRIDGE_ORIGIN = "google_sheets_bridge"
BRIDGE_EXPORT_ORIGIN = "google_sheets_bridge_export"
SUPPORTED_IMAGE_KINDS = {"in_cell", "over_grid"}


def _manifest_entries(payload: object, expected_spreadsheet_id: str) -> tuple[list[dict], list[dict]]:
    if not isinstance(payload, dict):
        raise ValueError("ไฟล์ manifest ต้องเป็น JSON object")
    if payload.get("version") not in {1, 2}:
        raise ValueError("manifest เวอร์ชันไม่รองรับ")
    if payload.get("spreadsheet_id") != expected_spreadsheet_id:
        raise ValueError("manifest ไม่ได้มาจาก Google Sheets ที่ลงทะเบียนไว้")
    images = payload.get("images")
    if not isinstance(images, list):
        raise ValueError("manifest ไม่มีรายการ images")
    if len(images) > MAX_BRIDGE_IMAGES:
        raise ValueError(f"manifest มีรูปมากเกิน {MAX_BRIDGE_IMAGES:,} รูปต่อครั้ง")
    exports = payload.get("sheet_exports", [])
    if not isinstance(exports, list):
        raise ValueError("manifest มี sheet_exports ไม่ถูกต้อง")
    if len(exports) > MAX_BRIDGE_SHEET_EXPORTS:
        raise ValueError(f"manifest มีชีตมากเกิน {MAX_BRIDGE_SHEET_EXPORTS:,} ชีตต่อครั้ง")
    return (
        [item for item in images if isinstance(item, dict)],
        [item for item in exports if isinstance(item, dict)],
    )


def _bridge_image_path(image_url: str) -> Path:
    """Resolve a locally generated media URL without accepting an external path."""
    prefix = "/media/"
    if not image_url.startswith(prefix):
        raise ValueError("ตำแหน่งรูปจาก Bridge ไม่ถูกต้อง")
    relative_path = Path(unquote(image_url.removeprefix(prefix)))
    resolved = (IMAGE_STORAGE_DIR / relative_path).resolve()
    storage_root = IMAGE_STORAGE_DIR.resolve()
    if storage_root not in resolved.parents and resolved != storage_root:
        raise ValueError("ตำแหน่งรูปจาก Bridge อยู่นอกคลังกลาง")
    return resolved


def _export_sheet_images(
    session,
    source: DataSource,
    exports: list[dict],
    *,
    dry_run: bool,
) -> dict:
    """Read images from one-sheet XLSX files made by the Apps Script bridge.

    This keeps the original Google Sheet untouched.  The Script creates an
    isolated export per approved tab, and we match drawing anchors by source
    sheet plus row number after the tabular data has been synchronised.
    """
    result = {
        "matched": 0,
        "changed": 0,
        "declared_file_ids": set(),
        "unmatched": [],
        "invalid": [],
    }
    image_headers = {normalise_header(value) for value in FIELD_ALIASES["image_url"]}
    for item in exports:
        sheet_name = clean_text(item.get("sheet_name"))
        drive_file_id = clean_text(item.get("drive_file_id"))
        filename = clean_text(item.get("filename")) or "bridge-sheet.xlsx"
        try:
            image_column = int(item.get("image_column"))
            header_row = int(item.get("header_row", 1))
        except (TypeError, ValueError):
            image_column = 0
            header_row = 0
        if not sheet_name or not drive_file_id or image_column < 1 or header_row < 1:
            result["invalid"].append("sheet_exports มีข้อมูล sheet_name, image_column หรือ drive_file_id ไม่ครบ")
            continue

        records = session.scalars(select(Record).where(
            Record.source_id == source.id,
            Record.source_sheet == sheet_name,
        )).all()
        record_by_row = {record.source_row_number: record for record in records}
        if not record_by_row:
            result["unmatched"].append(f"{sheet_name} (ยังไม่มีข้อมูลชีตนี้ใน Data Hub)")
            continue
        try:
            content = download_drive_file(drive_file_id)
        except GoogleSheetsConfigurationError as error:
            result["invalid"].append(f"{sheet_name} ({error})")
            continue
        if not content:
            result["invalid"].append(f"{sheet_name} (ไฟล์ Excel จาก Bridge ว่าง)")
            continue
        if len(content) > MAX_BRIDGE_EXPORT_BYTES:
            result["invalid"].append(f"{sheet_name} (ไฟล์ Excel จาก Bridge เกิน 150 MB)")
            continue

        with TemporaryDirectory(prefix="central-data-hub-bridge-") as temporary_directory:
            workbook_path = Path(temporary_directory) / "sheet.xlsx"
            workbook_path.write_bytes(content)
            try:
                workbook = openpyxl.load_workbook(workbook_path, read_only=True, data_only=True)
                worksheet = workbook.worksheets[0]
                exported_header = normalise_header(worksheet.cell(header_row, image_column).value)
                workbook.close()
            except Exception as error:
                result["invalid"].append(f"{sheet_name} (เปิดไฟล์ Excel ไม่ได้: {error})")
                continue
            if exported_header not in image_headers:
                result["invalid"].append(f"{sheet_name} (คอลัมน์รูปภาพในไฟล์ Bridge ไม่ตรงกับต้นทาง)")
                continue
            source_key = f"google-bridge:{source.id}:{sheet_name}"
            extracted = extract_embedded_images(
                workbook_path,
                source_key,
                {worksheet.title: image_column - 1},
                IMAGE_STORAGE_DIR,
            )

        urls_by_row = extracted.urls_by_sheet_row.get(worksheet.title, {})
        duplicate_rows = extracted.duplicate_rows_by_sheet.get(worksheet.title, set())
        for row_number in sorted(duplicate_rows):
            result["invalid"].append(
                f"{sheet_name}:แถว {row_number} (พบรูปมากกว่า 1 รูปในช่องเดียว จึงไม่จับคู่เอง)"
            )
        for row_number, image_url in urls_by_row.items():
            record = record_by_row.get(row_number)
            if record is None:
                result["unmatched"].append(f"{sheet_name}:แถว {row_number}")
                continue
            stable_image_id = f"sheet-export:{sheet_name}:row-{row_number}"
            result["declared_file_ids"].add(stable_image_id)
            if dry_run:
                result["matched"] += 1
                continue
            try:
                image_content = _bridge_image_path(image_url).read_bytes()
            except (OSError, ValueError) as error:
                result["invalid"].append(f"{sheet_name}:แถว {row_number} ({error})")
                continue
            suffix = uploaded_image_suffix(image_content)
            if suffix is None:
                result["invalid"].append(f"{sheet_name}:แถว {row_number} (รูปแบบไฟล์ไม่รองรับ)")
                continue
            _, did_change = store_record_image(
                session,
                record,
                image_content,
                suffix,
                origin=BRIDGE_EXPORT_ORIGIN,
                source_id=source.id,
                source_sheet=sheet_name,
                remote_file_id=stable_image_id,
                original_filename=f"{filename}#row-{row_number}",
                position=1,
            )
            result["matched"] += 1
            result["changed"] += int(did_change)
    return result


def sync_google_image_bridge(source_name: str, dry_run: bool = False) -> dict:
    """Synchronise central image copies without exporting a whole spreadsheet."""
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        source = session.scalar(select(DataSource).where(DataSource.name == source_name))
        if source is None or source.connection_type != "google_sheets":
            raise ValueError("ไม่พบแหล่งข้อมูล Google Sheets ที่ได้รับอนุมัติ")
        if not source.is_active or not source.external_id:
            raise ValueError("แหล่งข้อมูลนี้ยังไม่พร้อมใช้งาน")
        config = session.scalar(select(ImageBridgeConfig).where(
            ImageBridgeConfig.source_id == source.id,
            ImageBridgeConfig.is_active.is_(True),
        ))
        if config is None:
            raise ValueError("ยังไม่ได้ตั้งค่าโฟลเดอร์รูปภาพ Image Bridge สำหรับแหล่งข้อมูลนี้")

        manifest_file = find_drive_file_in_folder(config.drive_folder_id, config.manifest_file_name)
        if manifest_file is None:
            raise ValueError(
                f"ไม่พบ {config.manifest_file_name} ในโฟลเดอร์ Google Drive ที่ตั้งค่าไว้"
            )
        try:
            manifest = json.loads(download_drive_file(manifest_file["id"]).decode("utf-8"))
        except UnicodeDecodeError as error:
            raise ValueError("manifest ต้องเป็นไฟล์ UTF-8") from error
        entries, sheet_exports = _manifest_entries(manifest, source.external_id)

        accepted: list[dict] = []
        invalid: list[str] = []
        for item in entries:
            stable_id = clean_text(item.get("record_id"))
            registration_no = clean_text(item.get("registration_no"))
            sheet_name = clean_text(item.get("sheet_name"))
            file_id = clean_text(item.get("drive_file_id"))
            kind = clean_text(item.get("kind")) or "in_cell"
            identity = stable_id or registration_no or "?"
            if kind not in SUPPORTED_IMAGE_KINDS:
                invalid.append(f"{sheet_name or '?'}:{identity} (รูปแบบ {kind} ไม่รองรับ)")
                continue
            if not (stable_id or registration_no) or not sheet_name or not file_id:
                invalid.append("รายการใน manifest ขาด record_id/เลขทะเบียน, sheet_name หรือ drive_file_id")
                continue
            try:
                position = max(1, int(item.get("position", 1)))
            except (TypeError, ValueError):
                position = 1
            accepted.append({
                "record_id": stable_id,
                "registration_no": registration_no,
                "sheet_name": sheet_name,
                "drive_file_id": file_id,
                "position": position,
                "filename": clean_text(item.get("filename")) or f"{identity}-{position}",
            })

        record_keys = {f"id-{item['record_id']}" for item in accepted if item["record_id"]}
        registration_nos = {item["registration_no"] for item in accepted if item["registration_no"]}
        sheets = {item["sheet_name"] for item in accepted}
        match_conditions = []
        if record_keys:
            match_conditions.append(Record.source_row_key.in_(record_keys))
        if registration_nos:
            match_conditions.append(Record.registration_no.in_(registration_nos))
        records = []
        if match_conditions:
            records = session.scalars(select(Record).where(
                Record.source_id == source.id,
                Record.source_sheet.in_(sheets),
                or_(*match_conditions),
            )).all()
        record_by_key_and_sheet = {(record.source_row_key, record.source_sheet): record for record in records}
        records_by_registration_and_sheet: dict[tuple[str, str], list[Record]] = {}
        for record in records:
            if record.registration_no:
                key = (record.registration_no, record.source_sheet)
                records_by_registration_and_sheet.setdefault(key, []).append(record)

        matched = 0
        changed = 0
        unmatched: list[str] = []
        declared_file_ids: set[str] = set()
        for item in accepted:
            stable_id = item["record_id"]
            registration_no = item["registration_no"]
            record = None
            if stable_id:
                record = record_by_key_and_sheet.get((f"id-{stable_id}", item["sheet_name"]))
            if record is None and registration_no:
                candidates = records_by_registration_and_sheet.get(
                    (registration_no, item["sheet_name"]), []
                )
                if len(candidates) == 1:
                    record = candidates[0]
                elif len(candidates) > 1:
                    invalid.append(
                        f"{item['sheet_name']}:{registration_no} (เลขทะเบียนซ้ำในชีต จึงไม่จับคู่รูปอัตโนมัติ)"
                    )
                    continue
            if record is None:
                unmatched.append(f"{item['sheet_name']}:{stable_id or registration_no}")
                continue
            declared_file_ids.add(item["drive_file_id"])
            if dry_run:
                matched += 1
                continue
            content = download_drive_file(item["drive_file_id"])
            if not content:
                invalid.append(f"{item['sheet_name']}:{stable_id or registration_no} (ไฟล์รูปว่าง)")
                continue
            if len(content) > MAX_BRIDGE_IMAGE_BYTES:
                invalid.append(f"{item['sheet_name']}:{stable_id or registration_no} (ไฟล์เกิน 25 MB)")
                continue
            suffix = uploaded_image_suffix(content)
            if suffix is None:
                invalid.append(
                    f"{item['sheet_name']}:{stable_id or registration_no} "
                    "(ไม่ใช่ JPEG, PNG, GIF หรือ WebP)"
                )
                continue
            _, did_change = store_record_image(
                session,
                record,
                content,
                suffix,
                origin=BRIDGE_ORIGIN,
                source_id=source.id,
                source_sheet=item["sheet_name"],
                remote_file_id=item["drive_file_id"],
                original_filename=item["filename"],
                position=item["position"],
            )
            matched += 1
            changed += int(did_change)

        export_result = _export_sheet_images(
            session,
            source,
            sheet_exports,
            dry_run=dry_run,
        )
        matched += export_result["matched"]
        changed += export_result["changed"]
        declared_file_ids.update(export_result["declared_file_ids"])
        unmatched.extend(export_result["unmatched"])
        invalid.extend(export_result["invalid"])

        removed = 0
        if not dry_run:
            stale_statement = select(RecordImage).where(
                RecordImage.source_id == source.id,
                RecordImage.origin.in_((BRIDGE_ORIGIN, BRIDGE_EXPORT_ORIGIN)),
            )
            if declared_file_ids:
                stale_statement = stale_statement.where(RecordImage.remote_file_id.not_in(declared_file_ids))
            for image in session.scalars(stale_statement).all():
                session.delete(image)
                removed += 1
            config.last_synced_at = datetime.now(UTC)
            config.last_message = (
                f"imported {matched}; changed {changed}; "
                f"unmatched {len(unmatched)}; invalid {len(invalid)}"
            )
            session.commit()

        return {
            "source_name": source.name,
            "dry_run": dry_run,
            "manifest_file": manifest_file["name"],
            "entries_received": len(entries),
            "sheet_exports_received": len(sheet_exports),
            "matched_records": matched,
            "changed_images": changed,
            "removed_images": removed,
            "unmatched": unmatched[:20],
            "unmatched_count": len(unmatched),
            "invalid": invalid[:20],
            "invalid_count": len(invalid),
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pull a Google Sheets Image Bridge manifest from Drive")
    parser.add_argument("--source-name", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(sync_google_image_bridge(args.source_name, args.dry_run), ensure_ascii=False, indent=2))
