"""Read-only XLSX importer for the local pilot dataset."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Iterable

import openpyxl
from sqlalchemy import select

from .database import Base, SessionLocal, engine
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


def first_value(row: list[object], indexes: dict[str, int], aliases: tuple[str, ...], multiline: bool = False):
    for alias in aliases:
        index = indexes.get(alias)
        if index is not None and index < len(row):
            return clean_multiline_text(row[index]) if multiline else clean_text(row[index])
    return None


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
) -> dict:
    """Validate and upsert approved tabular data into one source.

    The row identity is source + sheet + original row number.  Repeating an
    unchanged sync only increments `skipped`; it does not create new records.
    """
    run = SyncRun(source_id=source.id, status="running")
    session.add(run)
    session.flush()
    known_aliases = {alias for aliases in FIELD_ALIASES.values() for alias in aliases}

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

        for row_number, values in enumerate(rows, start=sheet.header_row_number + 1):
            row = list(values)
            if not any(value not in (None, "") for value in row):
                continue
            run.rows_read += 1
            payload, raw_data = canonical_payload(row, headers)
            raw_json = json.dumps(raw_data, ensure_ascii=False, sort_keys=True)
            raw_hash = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
            row_key = f"row-{row_number}"
            record = session.scalar(select(Record).where(
                Record.source_id == source.id,
                Record.source_sheet == sheet.name,
                Record.source_row_key == row_key,
            ))
            if record is not None and record.raw_hash == raw_hash:
                run.rows_skipped += 1
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

    run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
    run.message = run_message
    return {
        "run_id": run.id,
        "rows_read": run.rows_read,
        "inserted": run.rows_inserted,
        "updated": run.rows_updated,
        "skipped": run.rows_skipped,
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

        sheets = [
            TabularSheet(name=worksheet.title, rows=worksheet.iter_rows(values_only=True))
            for worksheet in workbook.worksheets
        ]
        result = sync_tabular_sheets(session, source, sheets, f"Imported from {workbook_path.name}")
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
