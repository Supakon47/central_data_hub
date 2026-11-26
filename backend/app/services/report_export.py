"""An Excel workbook listing what the source files are missing, to send to data owners.

Every listed row names its source, sheet and row number in the original file,
so staff can find and complete it there. Nothing is changed in Data Hub.
"""

from datetime import datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import DataSource, Record
from ..normalization import clean_text
from .completeness import data_completeness
from .locations import (
    REGISTER_START_YEAR,
    location_conflict_groups,
    location_index,
    match_report,
    registration_year_bucket,
)

HEADER_FILL = PatternFill("solid", fgColor="E7DCCF")
YEAR_LABELS = {
    "since_register": f"ตั้งแต่ปี {REGISTER_START_YEAR} (ควรอยู่ในบัญชีเดินทุ่ง)",
    "before_register": f"ก่อนปี {REGISTER_START_YEAR} (ต้องใช้ทะเบียนเก่า)",
    "no_year": "ไม่มีปีในเลข",
}
YEAR_ORDER = {"since_register": 0, "before_register": 1, "no_year": 2}
COMPLETENESS_COLUMNS = [
    ("registration", "มีเลขทะเบียน"),
    ("matching_key", "เลขใช้จับคู่ได้"),
    ("title", "มีชื่อ/รายการ"),
    ("material", "มีวัสดุ"),
    ("period", "มีอายุสมัย"),
    ("dimensions", "มีขนาด"),
    ("location", "มีตำแหน่ง"),
    ("image", "มีภาพ"),
]


def _sheet(workbook: Workbook, title: str, headers: list[str], widths: list[int]):
    sheet = workbook.create_sheet(title)
    for index, width in enumerate(widths):
        sheet.column_dimensions[chr(ord("A") + index)].width = width
    sheet.freeze_panes = "A2"
    cells = []
    for header in headers:
        cell = WriteOnlyCell(sheet, value=header)
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        cells.append(cell)
    sheet.append(cells)
    return sheet


def _percent(sheet, filled: int, rows: int):
    cell = WriteOnlyCell(sheet, value=(filled / rows) if rows else 0)
    cell.number_format = "0%"
    return cell


def _location(row) -> str | None:
    return row.location["value"] if row.location else None


def build_data_request_workbook(session: Session) -> bytes:
    index = location_index(session)
    names = dict(session.execute(select(DataSource.id, DataSource.name)).all())
    row_numbers = dict(session.execute(select(Record.id, Record.source_row_number)).all())
    completeness = data_completeness(session)
    report = match_report(session)
    matches_by_source = {source["source_id"]: source for source in report["location_sources"]}
    register_keys = {row.key for row in index.rows if row.key and not row.is_storage}

    workbook = Workbook(write_only=True)

    readme = _sheet(workbook, "อ่านก่อน", ["หัวข้อ", "รายละเอียด"], [28, 110])
    for line in [
        ("สร้างเมื่อ", datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("ที่มา", "Central Data Hub — สำเนากลางจากไฟล์ Excel/Google Sheets; ไฟล์ต้นฉบับไม่ถูกแก้ไข"),
        ("สรุปต่อแหล่ง", "แต่ละไฟล์มีข้อมูลช่องไหนกี่ % และจับคู่กับบัญชีเดินทุ่งได้เท่าไร"),
        ("ความครบถ้วนต่อชีต", "เหมือนสรุปต่อแหล่ง แต่แยกรายชีต ใช้ดูว่าชีตไหนขาดคอลัมน์หรือข้อมูล"),
        ("ไม่พบในทะเบียน", f"แถวในบัญชีห้องคลังที่เลขทะเบียนไม่พบในทะเบียนกลาง เรียงเลขตั้งแต่ปี {REGISTER_START_YEAR} ก่อน "
                           f"(ควรมีในบัญชีเดินทุ่งแล้ว อาจตกหล่นหรือเขียนต่างรูปแบบ) ตามด้วยเลขก่อนปี {REGISTER_START_YEAR} "
                           "(ต้องใช้ทะเบียนเก่าในการเชื่อม)"),
        ("ไม่มีเลขทะเบียน", "แถวที่ช่องเลขทะเบียนว่าง หรือเป็นรหัสชั่วคราว เช่น 'ไม่มีเลข 3' — วัตถุเหล่านี้ยังเชื่อมกับทะเบียนไม่ได้"),
        ("ตำแหน่งขัดแย้ง", "เลขทะเบียนเดียวกันถูกบันทึกไว้หลายตำแหน่ง — อาจเป็นวัตถุชุดหลายชิ้น หรือบันทึกผิด ต้องตรวจว่าอยู่ที่ใดจริง"),
        ("แถวในไฟล์", "เลขแถวตาม Excel ต้นฉบับ ใช้เปิดหาแถวนั้นในไฟล์ได้โดยตรง"),
    ]:
        readme.append(list(line))

    summary_headers = ["แหล่งข้อมูล", "แถว", *(label for _, label in COMPLETENESS_COLUMNS),
                       "พบในทะเบียน", f"ไม่พบ: ตั้งแต่ {REGISTER_START_YEAR}", f"ไม่พบ: ก่อน {REGISTER_START_YEAR}",
                       "ไม่พบ: ไม่มีปี", "ตำแหน่งขัดแย้ง (เลข)"]
    summary = _sheet(workbook, "สรุปต่อแหล่ง", summary_headers, [34, 10, *[12] * 8, 12, 14, 14, 12, 14])
    for source in completeness["sources"]:
        totals = source["totals"]
        match = matches_by_source.get(source["source_id"])
        years = match["unmatched_by_year"] if match else {}
        summary.append([
            source["source_name"], totals["rows"],
            *(_percent(summary, totals[field], totals["rows"]) for field, _ in COMPLETENESS_COLUMNS),
            match["matched"] if match else None,
            years.get("since_register"), years.get("before_register"), years.get("no_year"),
            match["location_conflict_keys"] if match else None,
        ])

    roles = {"register": "ทะเบียน", "location": "ตำแหน่ง"}
    per_sheet = _sheet(workbook, "ความครบถ้วนต่อชีต",
                       ["แหล่งข้อมูล", "ชีต", "บทบาท", "แถว", *(label for _, label in COMPLETENESS_COLUMNS)],
                       [34, 30, 10, 10, *[12] * 8])
    for source in completeness["sources"]:
        for sheet in source["sheets"]:
            per_sheet.append([
                source["source_name"], sheet["sheet"], roles.get(sheet["role"], ""), sheet["rows"],
                *(_percent(per_sheet, sheet[field], sheet["rows"]) for field, _ in COMPLETENESS_COLUMNS),
            ])

    unmatched = sorted(
        (row for row in index.rows if row.is_storage and row.key and row.key not in register_keys),
        key=lambda row: (YEAR_ORDER[registration_year_bucket(row.key)], names.get(row.source_id) or "",
                         row.source_sheet, row_numbers.get(row.id) or 0),
    )
    not_found = _sheet(workbook, "ไม่พบในทะเบียน",
                       ["กลุ่มปี", "เลขทะเบียน", "ชื่อ/รายการ", "แหล่งข้อมูล", "ชีต", "แถวในไฟล์", "ตำแหน่ง"],
                       [34, 22, 40, 30, 22, 10, 22])
    for row in unmatched:
        not_found.append([
            YEAR_LABELS[registration_year_bucket(row.key)], row.registration_no, row.title_description,
            names.get(row.source_id), row.source_sheet, row_numbers.get(row.id), _location(row),
        ])

    no_number = _sheet(workbook, "ไม่มีเลขทะเบียน",
                       ["ค่าในช่องเลขทะเบียน", "ชื่อ/รายการ", "แหล่งข้อมูล", "ชีต", "แถวในไฟล์", "ตำแหน่ง"],
                       [34, 40, 30, 22, 10, 22])
    for row in sorted(
        (row for row in index.rows if not row.key),
        key=lambda row: (names.get(row.source_id) or "", row.source_sheet, row_numbers.get(row.id) or 0),
    ):
        no_number.append([
            clean_text(row.registration_no) or "(ว่าง)", row.title_description, names.get(row.source_id),
            row.source_sheet, row_numbers.get(row.id), _location(row),
        ])

    conflicts = _sheet(workbook, "ตำแหน่งขัดแย้ง",
                       ["เลขทะเบียน", "ชื่อ/รายการ", "ตำแหน่ง", "แหล่งข้อมูล", "ชีต", "แถวในไฟล์"],
                       [22, 40, 22, 30, 22, 10])
    for key, rows in sorted(location_conflict_groups(index).items()):
        for row in sorted(rows, key=lambda row: (names.get(row.source_id) or "", row.source_sheet)):
            conflicts.append([
                key, row.title_description, _location(row), names.get(row.source_id),
                row.source_sheet, row_numbers.get(row.id),
            ])

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
