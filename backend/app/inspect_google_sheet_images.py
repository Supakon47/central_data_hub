"""Read-only diagnostic for images stored in an approved Google Sheets source."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile

from sqlalchemy import select

from .database import SessionLocal
from .embedded_images import extract_embedded_images
from .google_sheets import (
    GoogleSheetSource,
    GoogleSheetsConfigurationError,
    export_workbook_as_xlsx,
    fetch_values,
    google_drive_file_capabilities,
)
from .import_workbook import FIELD_ALIASES, TabularSheet
from .models import DataSource, SourceSheetConfig
from .normalization import normalise_header


def inspect_google_sheet_images(source_name: str) -> dict:
    """Inspect an export only; do not import rows or persist image files."""
    session = SessionLocal()
    try:
        source = session.scalar(select(DataSource).where(DataSource.name == source_name))
        if source is None or source.connection_type != "google_sheets" or not source.external_id:
            raise ValueError("ไม่พบ Google Sheets source ที่ได้รับอนุมัติใน Data Catalog")
        configs = session.scalars(select(SourceSheetConfig).where(
            SourceSheetConfig.source_id == source.id,
            SourceSheetConfig.is_active.is_(True),
        ).order_by(SourceSheetConfig.sheet_name)).all()
        if not configs:
            raise ValueError("source นี้ยังไม่มีชีตที่ได้รับอนุมัติ")

        image_columns_by_sheet: dict[str, int] = {}
        for config in configs:
            values = fetch_values(GoogleSheetSource(source.external_id, config.sheet_name, config.read_range))
            headers = [normalise_header(value) for value in values[0]] if values else []
            image_column = next(
                (index for index, header in enumerate(headers) if header in FIELD_ALIASES["image_url"]),
                None,
            )
            if image_column is not None:
                image_columns_by_sheet[config.sheet_name] = image_column

        if not image_columns_by_sheet:
            return {
                "ok": True,
                "source_name": source.name,
                "message": "ไม่พบหัวคอลัมน์ รูปภาพ, image_url หรือ ลิงก์รูปภาพ ในชีตที่ลงทะเบียน",
                "image_columns": {},
            }

        drive_file = google_drive_file_capabilities(source.external_id)
        try:
            exported = export_workbook_as_xlsx(source.external_id)
        except GoogleSheetsConfigurationError as error:
            return {
                "ok": False,
                "source_name": source.name,
                "drive_file": drive_file,
                "message": str(error),
            }
        with TemporaryDirectory(prefix="central-data-hub-image-inspect-") as directory:
            workbook_path = Path(directory) / "google-sheet-export.xlsx"
            workbook_path.write_bytes(exported)
            with zipfile.ZipFile(workbook_path) as archive:
                parts = archive.namelist()
                media_parts = [name for name in parts if name.startswith("xl/media/")]
                drawing_parts = [name for name in parts if name.startswith("xl/drawings/") and name.endswith(".xml")]
            extracted = extract_embedded_images(
                workbook_path,
                source.name,
                image_columns_by_sheet,
                Path(directory) / "images",
            )

        return {
            "ok": True,
            "source_name": source.name,
            "drive_file": drive_file,
            "xlsx_bytes": len(exported),
            "image_columns": {sheet: column + 1 for sheet, column in image_columns_by_sheet.items()},
            "media_files_in_export": len(media_parts),
            "drawing_files_in_export": len(drawing_parts),
            "images_matched": extracted.exported_count,
            "images_ignored": extracted.ignored_count,
            "matched_rows": {sheet: sorted(rows) for sheet, rows in extracted.urls_by_sheet_row.items()},
            "duplicate_image_rows": {sheet: sorted(rows) for sheet, rows in extracted.duplicate_rows_by_sheet.items()},
            "message": (
                "พบภาพและจับคู่กับแถวได้" if extracted.exported_count else
                "Google export สำเร็จ แต่ยังไม่พบภาพที่จับคู่กับคอลัมน์รูปภาพ"
            ),
        }
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ตรวจรูปภาพที่ฝังใน Google Sheets แบบอ่านอย่างเดียว")
    parser.add_argument("--source-name", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect_google_sheet_images(args.source_name), ensure_ascii=False, indent=2))
    except (GoogleSheetsConfigurationError, ValueError) as error:
        print(json.dumps({"ok": False, "message": str(error)}, ensure_ascii=False, indent=2))
        raise SystemExit(1)
    except Exception as error:
        print(json.dumps({
            "ok": False,
            "message": f"ตรวจไฟล์ export ไม่สำเร็จ ({type(error).__name__}): {str(error)[:300]}",
        }, ensure_ascii=False, indent=2))
        raise SystemExit(1)
