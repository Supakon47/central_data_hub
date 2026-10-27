"""Pull a safe, manifest-based image gallery from an approved Drive folder.

The paired Apps Script owns all writes to Google Drive.  This service only
reads a JSON manifest and the specific image file IDs it names, then stores a
central copy beside the existing Data Hub media.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json

from sqlalchemy import select

from .database import Base, SessionLocal, engine
from .google_sheets import (
    GoogleSheetsConfigurationError,
    download_drive_file,
    find_drive_file_in_folder,
)
from .models import DataSource, ImageBridgeConfig, Record, RecordImage
from .normalization import clean_text
from .record_images import store_record_image, uploaded_image_suffix


MAX_BRIDGE_IMAGES = 2_000
MAX_BRIDGE_IMAGE_BYTES = 25 * 1024 * 1024
BRIDGE_ORIGIN = "google_sheets_bridge"


def _manifest_entries(payload: object, expected_spreadsheet_id: str) -> list[dict]:
    if not isinstance(payload, dict):
        raise ValueError("ไฟล์ manifest ต้องเป็น JSON object")
    if payload.get("version") != 1:
        raise ValueError("manifest เวอร์ชันไม่รองรับ")
    if payload.get("spreadsheet_id") != expected_spreadsheet_id:
        raise ValueError("manifest ไม่ได้มาจาก Google Sheets ที่ลงทะเบียนไว้")
    images = payload.get("images")
    if not isinstance(images, list):
        raise ValueError("manifest ไม่มีรายการ images")
    if len(images) > MAX_BRIDGE_IMAGES:
        raise ValueError(f"manifest มีรูปมากเกิน {MAX_BRIDGE_IMAGES:,} รูปต่อครั้ง")
    return [item for item in images if isinstance(item, dict)]


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
        entries = _manifest_entries(manifest, source.external_id)

        accepted: list[dict] = []
        invalid: list[str] = []
        for item in entries:
            stable_id = clean_text(item.get("record_id"))
            sheet_name = clean_text(item.get("sheet_name"))
            file_id = clean_text(item.get("drive_file_id"))
            kind = clean_text(item.get("kind")) or "in_cell"
            if kind != "in_cell":
                # Over-grid images are deliberately reported, not guessed.
                invalid.append(f"{sheet_name or '?'}:{stable_id or '?'} (รูปแบบ {kind} ต้องตรวจสอบเอง)")
                continue
            if not stable_id or not sheet_name or not file_id:
                invalid.append("รายการใน manifest ขาด record_id, sheet_name หรือ drive_file_id")
                continue
            try:
                position = max(1, int(item.get("position", 1)))
            except (TypeError, ValueError):
                position = 1
            accepted.append({
                "record_id": stable_id,
                "sheet_name": sheet_name,
                "drive_file_id": file_id,
                "position": position,
                "filename": clean_text(item.get("filename")) or f"{stable_id}-{position}",
            })

        record_keys = {f"id-{item['record_id']}" for item in accepted}
        records = session.scalars(select(Record).where(
            Record.source_id == source.id,
            Record.source_row_key.in_(record_keys),
        )).all()
        record_by_key_and_sheet = {(record.source_row_key, record.source_sheet): record for record in records}

        matched = 0
        changed = 0
        unmatched: list[str] = []
        declared_file_ids: set[str] = set()
        for item in accepted:
            record = record_by_key_and_sheet.get((f"id-{item['record_id']}", item["sheet_name"]))
            if record is None:
                unmatched.append(f"{item['sheet_name']}:{item['record_id']}")
                continue
            declared_file_ids.add(item["drive_file_id"])
            if dry_run:
                matched += 1
                continue
            content = download_drive_file(item["drive_file_id"])
            if not content:
                invalid.append(f"{item['sheet_name']}:{item['record_id']} (ไฟล์รูปว่าง)")
                continue
            if len(content) > MAX_BRIDGE_IMAGE_BYTES:
                invalid.append(f"{item['sheet_name']}:{item['record_id']} (ไฟล์เกิน 25 MB)")
                continue
            suffix = uploaded_image_suffix(content)
            if suffix is None:
                invalid.append(f"{item['sheet_name']}:{item['record_id']} (ไม่ใช่ JPEG, PNG, GIF หรือ WebP)")
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

        removed = 0
        if not dry_run:
            stale_statement = select(RecordImage).where(
                RecordImage.source_id == source.id,
                RecordImage.origin == BRIDGE_ORIGIN,
            )
            if declared_file_ids:
                stale_statement = stale_statement.where(RecordImage.remote_file_id.not_in(declared_file_ids))
            for image in session.scalars(stale_statement).all():
                session.delete(image)
                removed += 1
            config.last_synced_at = datetime.now(timezone.utc)
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
