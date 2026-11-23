"""Read-only preflight report for joining an object register to storage locations.

The command deliberately does not write to PostgreSQL or change either workbook.
It only identifies possible links using the shared business identifier found under
one of four Thai header names: registration number, register number, object
number, or object identifier.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import openpyxl

from .normalization import clean_text, normalise_header, normalise_registration_no


REGISTRATION_HEADERS = {
    "เลขทะเบียน",
    "ทะเบียน",
    "เลขวัตถุ",
    "เลขประจำวัตถุ",
}


@dataclass(frozen=True)
class SourceRow:
    workbook: str
    sheet: str
    row_number: int
    registration_raw: str | None
    registration_normalized: str | None
    title: str | None
    location: str | None


def normalize_registration(value: object | None) -> str | None:
    """Produce a conservative comparison value while retaining the raw value.

    This deliberately avoids guessing missing year components or correcting
    digits. It resolves harmless representation differences only.
    """
    return normalise_registration_no(value)


def first_cell_value(values: tuple[object, ...], indexes: dict[str, int], aliases: tuple[str, ...]) -> str | None:
    for alias in aliases:
        index = indexes.get(alias)
        if index is not None and index < len(values):
            value = clean_text(values[index])
            if value:
                return value
    return None


def find_header_row(worksheet) -> tuple[int, list[str]] | None:
    """Find a row with a known registration header in the first 12 rows."""
    for row_number, row in enumerate(worksheet.iter_rows(min_row=1, max_row=12, values_only=True), start=1):
        headers = [normalise_header(value) for value in row]
        if set(headers).intersection(REGISTRATION_HEADERS):
            return row_number, headers
    return None


def inspect_workbook(path: Path) -> tuple[list[SourceRow], dict]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    source_rows: list[SourceRow] = []
    skipped_sheets: list[str] = []
    placeholder_rows = 0

    try:
        for worksheet in workbook.worksheets:
            header = find_header_row(worksheet)
            if header is None:
                skipped_sheets.append(worksheet.title)
                continue
            header_row, headers = header
            indexes = {header: index for index, header in enumerate(headers) if header}
            registration_index = next(indexes[name] for name in REGISTRATION_HEADERS if name in indexes)

            for row_number, values in enumerate(
                worksheet.iter_rows(min_row=header_row + 1, values_only=True), start=header_row + 1
            ):
                if not any(value not in (None, "") for value in values):
                    continue
                raw_registration = clean_text(values[registration_index]) if registration_index < len(values) else None
                normalized_registration = normalize_registration(raw_registration)
                if raw_registration and not normalized_registration:
                    placeholder_rows += 1
                source_rows.append(
                    SourceRow(
                        workbook=path.name,
                        sheet=worksheet.title,
                        row_number=row_number,
                        registration_raw=raw_registration,
                        registration_normalized=normalized_registration,
                        title=first_cell_value(values, indexes, ("ชื่อโบราณวัตถุ", "ชื่อวัตถุ", "ชื่อ", "รายการ", "รายละเอียด")),
                        location=first_cell_value(values, indexes, ("สถานที่เก็บ", "ที่เก็บ", "ชั้นวาง", "ชั้น")),
                    )
                )
    finally:
        workbook.close()

    valid_rows = sum(bool(row.registration_normalized) for row in source_rows)
    groups: dict[str, list[SourceRow]] = defaultdict(list)
    for row in source_rows:
        if row.registration_normalized:
            groups[row.registration_normalized].append(row)
    return source_rows, {
        "file": path.name,
        "sheets_with_registration_header": sorted({row.sheet for row in source_rows}),
        "skipped_sheets": skipped_sheets,
        "rows_read": len(source_rows),
        "rows_with_valid_registration": valid_rows,
        "placeholder_or_unusable_registration_rows": placeholder_rows,
        "unique_valid_registrations": len(groups),
        "duplicate_registration_groups_in_file": sum(len(rows) > 1 for rows in groups.values()),
    }


def grouped_rows(rows: list[SourceRow]) -> dict[str, list[SourceRow]]:
    groups: dict[str, list[SourceRow]] = defaultdict(list)
    for row in rows:
        if row.registration_normalized:
            groups[row.registration_normalized].append(row)
    return groups


def row_preview(row: SourceRow) -> dict:
    return {
        "sheet": row.sheet,
        "row": row.row_number,
        "registration_raw": row.registration_raw,
        "title": row.title,
        "location": row.location,
    }


def title_conflicts(master_rows: list[SourceRow], location_rows: list[SourceRow]) -> bool:
    """Flag obvious title differences without pretending to identify an artefact.

    A title can be absent or shorter in a storage ledger, so this only raises a
    review flag when both sides contain text and neither looks like an expanded
    version of the other.
    """
    def title_key(value: str | None) -> str | None:
        text = clean_text(value)
        if not text:
            return None
        return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).upper()

    master_titles = {key for row in master_rows if (key := title_key(row.title))}
    location_titles = {key for row in location_rows if (key := title_key(row.title))}
    if not master_titles or not location_titles:
        return False
    return not any(
        master_title in location_title or location_title in master_title
        for master_title in master_titles
        for location_title in location_titles
    )


def inspect_location_merge(master_path: str, location_path: str, sample_limit: int = 20) -> dict:
    master = Path(master_path).expanduser().resolve()
    location = Path(location_path).expanduser().resolve()
    if not master.is_file() or master.suffix.lower() != ".xlsx":
        raise ValueError("ไฟล์ทะเบียนกลางต้องเป็น .xlsx ที่มีอยู่จริง")
    if not location.is_file() or location.suffix.lower() != ".xlsx":
        raise ValueError("ไฟล์ตำแหน่งห้องคลังต้องเป็น .xlsx ที่มีอยู่จริง")

    master_rows, master_summary = inspect_workbook(master)
    location_rows, location_summary = inspect_workbook(location)
    master_groups = grouped_rows(master_rows)
    location_groups = grouped_rows(location_rows)
    matched_keys = sorted(set(master_groups).intersection(location_groups))

    one_to_one = [key for key in matched_keys if len(master_groups[key]) == len(location_groups[key]) == 1]
    ambiguous = [key for key in matched_keys if key not in set(one_to_one)]
    title_conflict_keys = [
        key for key in matched_keys if title_conflicts(master_groups[key], location_groups[key])
    ]
    review_keys = set(ambiguous).union(title_conflict_keys)
    sample_keys = matched_keys[:sample_limit]

    return {
        "mode": "read_only_preflight",
        "master": master_summary,
        "location": location_summary,
        "matches": {
            "matched_registration_values": len(matched_keys),
            "one_to_one_candidates": len(one_to_one),
            "ambiguous_candidates": len(ambiguous),
            "candidates_with_differing_titles": len(title_conflict_keys),
            "unmatched_master_registration_values": len(set(master_groups) - set(location_groups)),
            "unmatched_location_registration_values": len(set(location_groups) - set(master_groups)),
            "samples": [
                {
                    "registration_no": key,
                    "master_records": [row_preview(row) for row in master_groups[key]],
                    "location_records": [row_preview(row) for row in location_groups[key]],
                    "requires_review": key in review_keys,
                    "title_conflict": key in title_conflict_keys,
                }
                for key in sample_keys
            ],
        },
        "next_action": (
            "ตรวจ samples และผล ambiguous ก่อนสร้างข้อมูลรวม; คำสั่งนี้ไม่ได้ import "
            "แก้ Excel หรือเขียนข้อมูลลงฐานข้อมูล"
        ),
    }


def main() -> None:
    # Windows PowerShell can default to a legacy console encoding.  The report
    # includes Thai field names and source values, so make CLI output portable.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Read-only preflight: compare registration numbers between two XLSX workbooks"
    )
    parser.add_argument("--master", required=True, help="path to the master registration workbook")
    parser.add_argument("--location", required=True, help="path to the storage/location workbook")
    parser.add_argument("--sample-limit", type=int, default=20)
    args = parser.parse_args()
    print(json.dumps(
        inspect_location_merge(args.master, args.location, max(args.sample_limit, 0)),
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
