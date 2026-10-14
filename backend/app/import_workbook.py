"""Read-only XLSX importer for the local pilot dataset."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Iterable

import openpyxl
from sqlalchemy import select

from .database import Base, SessionLocal, engine
from .config import IMAGE_STORAGE_DIR
from .embedded_images import extract_embedded_images
from .models import DataQualityIssue, DataSource, Record, SyncRun
from .normalization import clean_multiline_text, clean_text, normalise_header, normalise_image_url


FIELD_ALIASES = {
    "registration_no": ("เลขทะเบียน", "."),
    "previous_registration_no": ("เลขทะเบียนเดิม",),
    "title_description": ("รายการ",),
    "dimensions_text": ("ขนาด ซ.ม.",),
    "material": ("ชนิด",),
    "period": ("อายุสมัย",),
    "provenance": ("ประวัติที่มา",),
    "image_url": ("รูปภาพ",),
    "status_data_check": ("การตรวจสอบข้อมูล",),
    "status_photographed": ("การถ่ายภาพแล้ว",),
    "status_antique": ("การลงระบบ Antique",),
    "status_storage": ("การส่งขึ้นห้องคลัง",),
}

# This value is not displayed as an artefact registration number. It is a
# source-owned, immutable row identifier used only to preserve identity when
# staff sort or move rows in an approved tab.
STABLE_ROW_ID_ALIASES = ("record_id", "Record ID", "รหัสประจำรายการ", "รหัสรายการ")
MAX_STABLE_ROW_ID_LENGTH = 220


@dataclass(frozen=True)
class TabularSheet:
    """A normalised view of one approved spreadsheet tab.

    `rows` includes the header as its first row.  This keeps Excel and Google
    Sheets on the same validation and idempotent-import path.
    """

    name: str
    rows: Iterable[list[object] | tuple[object, ...]]
    header_row_number: int = 1
    source_url: str | None = None
    embedded_image_urls_by_row: dict[int, str] = field(default_factory=dict)
    duplicate_embedded_image_rows: set[int] = field(default_factory=set)


def first_value(row: list[object], indexes: dict[str, int], aliases: tuple[str, ...], multiline: bool = False):
    for alias in aliases:
        index = indexes.get(alias)
        if index is not None and index < len(row):
            return clean_multiline_text(row[index]) if multiline else clean_text(row[index])
    return None


def stable_row_key(row: list[object], indexes: dict[str, int], row_number: int) -> tuple[str, str | None]:
    """Return an immutable source key when a sheet supplies `record_id`.

    Existing sources without the optional column retain their current
    row-based identity so this change is backwards compatible.
    """
    stable_id = first_value(row, indexes, STABLE_ROW_ID_ALIASES)
    if stable_id and len(stable_id) <= MAX_STABLE_ROW_ID_LENGTH:
        return f"id-{stable_id}", stable_id
    return f"row-{row_number}", None


def canonical_payload(row: list[object], headers: list[str]) -> tuple[dict, dict]:
    indexes = {header: index for index, header in enumerate(headers) if header}
    raw_data = {
        headers[index] or f"column_{index + 1}": clean_multiline_text(value)
        for index, value in enumerate(row)
        if value not in (None, "")
    }
    payload = {
        "registration_no": first_value(row, indexes, FIELD_ALIASES["registration_no"]),
        "previous_registration_no": first_value(row, indexes, FIELD_ALIASES["previous_registration_no"]),
        "title_description": first_value(row, indexes, FIELD_ALIASES["title_description"], multiline=True),
        "dimensions_text": first_value(row, indexes, FIELD_ALIASES["dimensions_text"], multiline=True),
        "material": first_value(row, indexes, FIELD_ALIASES["material"]),
        "period": first_value(row, indexes, FIELD_ALIASES["period"], multiline=True),
        "provenance": first_value(row, indexes, FIELD_ALIASES["provenance"], multiline=True),
        "image_url": first_value(row, indexes, FIELD_ALIASES["image_url"]),
        "status_data_check": first_value(row, indexes, FIELD_ALIASES["status_data_check"]),
        "status_photographed": first_value(row, indexes, FIELD_ALIASES["status_photographed"]),
        "status_antique": first_value(row, indexes, FIELD_ALIASES["status_antique"]),
        "status_storage": first_value(row, indexes, FIELD_ALIASES["status_storage"]),
    }
    payload["image_url"] = normalise_image_url(payload["image_url"])
    return payload, raw_data


def sync_tabular_sheets(
    session,
    source: DataSource,
    sheets: Iterable[TabularSheet],
    run_message: str,
    reconcile_missing: bool = False,
) -> dict:
    """Validate and upsert approved tabular data into one source.

    The row identity is source + sheet + original row number.  Repeating an
    unchanged sync only increments `skipped`; it does not create new records.
    When `reconcile_missing` is true, rows that were previously imported from
    a successfully validated tab but no longer exist there are removed from the
    central copy. This is intentionally opt-in so an Excel import never
    deletes records merely because a workbook was imported partially.
    """
    run = SyncRun(source_id=source.id, status="running")
    session.add(run)
    session.flush()
    known_aliases = {alias for aliases in FIELD_ALIASES.values() for alias in aliases}
    removed_count = 0

    for sheet in sheets:
        rows = iter(sheet.rows)
        first_row = next(rows, None)
        if first_row is None:
            continue
        headers = [normalise_header(value) for value in first_row]
        if not set(headers).intersection(known_aliases):
            run.error_count += 1
            session.add(DataQualityIssue(
                source_id=source.id,
                source_sheet=sheet.name,
                severity="error",
                code="UNRECOGNISED_HEADERS",
                message="ไม่พบหัวตารางที่ระบบรู้จัก จึงข้ามชีตนี้",
            ))
            continue

        indexes = {header: index for index, header in enumerate(headers) if header}
        observed_row_keys: set[str] = set()
        seen_stable_ids: set[str] = set()
        identity_error = False
        for row_number, values in enumerate(rows, start=sheet.header_row_number + 1):
            row = list(values)
            if not any(value not in (None, "") for value in row):
                continue
            run.rows_read += 1
            row_key, stable_id = stable_row_key(row, indexes, row_number)
            if stable_id and stable_id in seen_stable_ids:
                run.error_count += 1
                identity_error = True
                session.add(DataQualityIssue(
                    source_id=source.id,
                    source_sheet=sheet.name,
                    source_row_number=row_number,
                    severity="error",
                    code="DUPLICATE_STABLE_ROW_ID",
                    message=f"พบ record_id ซ้ำ ({stable_id}) จึงข้ามแถวนี้เพื่อไม่ให้ทับข้อมูล",
                ))
                continue
            if stable_id:
                seen_stable_ids.add(stable_id)
            payload, raw_data = canonical_payload(row, headers)
            embedded_image_url = sheet.embedded_image_urls_by_row.get(row_number)
            if embedded_image_url:
                payload["image_url"] = embedded_image_url
                raw_data["_embedded_image_url"] = embedded_image_url
            raw_json = json.dumps(raw_data, ensure_ascii=False, sort_keys=True)
            raw_hash = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
            observed_row_keys.add(row_key)
            record = session.scalar(select(Record).where(
                Record.source_id == source.id,
                Record.source_sheet == sheet.name,
                Record.source_row_key == row_key,
            ))
            # During adoption of record_id, retain the existing central record
            # for the same row instead of creating a duplicate just because
            # its source key changed from row-12 to id-ARCH-00012.
            if record is None and stable_id:
                record = session.scalar(select(Record).where(
                    Record.source_id == source.id,
                    Record.source_sheet == sheet.name,
                    Record.source_row_key == f"row-{row_number}",
                ))
            if record is not None and record.raw_hash == raw_hash:
                run.rows_skipped += 1
                # The content can be unchanged even when staff sorted the
                # sheet. Keep the traceability fields current without
                # treating that as a content update.
                record.source_row_number = row_number
                record.source_row_key = row_key
                record.source_url = sheet.source_url
                if row_number in sheet.duplicate_embedded_image_rows:
                    run.error_count += 1
                    session.add(DataQualityIssue(
                        source_id=source.id,
                        record_id=record.id,
                        source_sheet=sheet.name,
                        source_row_number=row_number,
                        severity="warning",
                        code="MULTIPLE_EMBEDDED_IMAGES",
                        message="พบรูปภาพฝังมากกว่า 1 รูปในช่องรูปภาพ จึงไม่จับคู่รูปอัตโนมัติ",
                    ))
                continue
            if record is None:
                record = Record(
                    source_id=source.id,
                    source_sheet=sheet.name,
                    source_row_number=row_number,
                    source_row_key=row_key,
                    source_url=sheet.source_url,
                    raw_hash=raw_hash,
                    raw_data=raw_data,
                    **payload,
                )
                session.add(record)
                session.flush()
                run.rows_inserted += 1
            else:
                for field, value in payload.items():
                    setattr(record, field, value)
                record.source_row_number = row_number
                record.source_row_key = row_key
                record.source_url = sheet.source_url
                record.raw_hash = raw_hash
                record.raw_data = raw_data
                run.rows_updated += 1

            if not payload["registration_no"]:
                run.error_count += 1
                session.add(DataQualityIssue(
                    source_id=source.id,
                    record_id=record.id,
                    source_sheet=sheet.name,
                    source_row_number=row_number,
                    severity="warning",
                    code="MISSING_REGISTRATION_NO",
                    message="แถวนี้ไม่มีเลขทะเบียน",
                ))
            if row_number in sheet.duplicate_embedded_image_rows:
                run.error_count += 1
                session.add(DataQualityIssue(
                    source_id=source.id,
                    record_id=record.id,
                    source_sheet=sheet.name,
                    source_row_number=row_number,
                    severity="warning",
                    code="MULTIPLE_EMBEDDED_IMAGES",
                    message="พบรูปภาพฝังมากกว่า 1 รูปในช่องรูปภาพ จึงไม่จับคู่รูปอัตโนมัติ",
                ))

        # A duplicate record_id makes it ambiguous which original record was
        # removed. Keep the previous central copy intact until staff fix the
        # conflicting IDs in the source sheet.
        if reconcile_missing and not identity_error:
            stale_statement = select(Record).where(
                Record.source_id == source.id,
                Record.source_sheet == sheet.name,
            )
            if observed_row_keys:
                stale_statement = stale_statement.where(Record.source_row_key.not_in(observed_row_keys))
            stale_records = session.scalars(stale_statement).all()
            for stale_record in stale_records:
                # Preserve data-quality history while allowing the imported
                # record to disappear with its source row.
                for issue in session.scalars(select(DataQualityIssue).where(
                    DataQualityIssue.record_id == stale_record.id
                )).all():
                    issue.record_id = None
                session.delete(stale_record)
                removed_count += 1

    run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
    run.message = (
        f"{run_message}; removed stale records: {removed_count}"
        if reconcile_missing else run_message
    )
    return {
        "run_id": run.id,
        "rows_read": run.rows_read,
        "inserted": run.rows_inserted,
        "updated": run.rows_updated,
        "skipped": run.rows_skipped,
        "deleted": removed_count,
        "errors": run.error_count,
    }


def import_xlsx(path: str, source_name: str = "บัญชีเดินทุ่ง (ต้นแบบ)") -> dict:
    Base.metadata.create_all(bind=engine)
    workbook_path = Path(path).resolve()
    if not workbook_path.is_file() or workbook_path.suffix.lower() != ".xlsx":
        raise ValueError("ระบุไฟล์ .xlsx ที่มีอยู่จริง")

    workbook = openpyxl.load_workbook(workbook_path, read_only=True, data_only=True)
    session = SessionLocal()
    try:
        source = session.scalar(select(DataSource).where(DataSource.name == source_name))
        if source is None:
            source = DataSource(
                name=source_name,
                owner_name="ยังไม่ระบุ",
                description="ข้อมูลทดลองจากไฟล์ Excel เพื่อทดสอบ Data Explorer และ Dashboard",
                connection_type="xlsx_import",
                external_id=str(workbook_path),
                classification="internal",
            )
            session.add(source)
            session.flush()

        photo_columns_by_sheet = {}
        for worksheet in workbook.worksheets:
            header_row = next(worksheet.iter_rows(values_only=True), None) or ()
            for index, value in enumerate(header_row):
                if normalise_header(value) == "รูปภาพ":
                    photo_columns_by_sheet[worksheet.title] = index
                    break
        embedded_images = extract_embedded_images(
            workbook_path, source_name, photo_columns_by_sheet, IMAGE_STORAGE_DIR
        )
        sheets = [
            TabularSheet(
                name=worksheet.title,
                rows=worksheet.iter_rows(values_only=True),
                embedded_image_urls_by_row=embedded_images.urls_by_sheet_row.get(worksheet.title, {}),
                duplicate_embedded_image_rows=embedded_images.duplicate_rows_by_sheet.get(worksheet.title, set()),
            )
            for worksheet in workbook.worksheets
        ]
        result = sync_tabular_sheets(
            session,
            source,
            sheets,
            f"Imported from {workbook_path.name}; embedded images exported: {embedded_images.exported_count}; ambiguous rows: {sum(len(rows) for rows in embedded_images.duplicate_rows_by_sheet.values())}",
        )
        result["embedded_images_exported"] = embedded_images.exported_count
        result["embedded_images_ambiguous"] = sum(len(rows) for rows in embedded_images.duplicate_rows_by_sheet.values())
        session.commit()
        return result
    except Exception as error:
        session.rollback()
        raise RuntimeError(f"การนำเข้าล้มเหลว: {error}") from error
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import an XLSX file into Central Data Hub")
    parser.add_argument("path", help="absolute or relative path to .xlsx")
    parser.add_argument("--source-name", default="บัญชีเดินทุ่ง (ต้นแบบ)")
    args = parser.parse_args()
    print(json.dumps(import_xlsx(args.path, args.source_name), ensure_ascii=False, indent=2))
