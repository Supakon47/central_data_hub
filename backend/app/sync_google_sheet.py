"""Synchronise pre-approved Google Sheets tabs into the central database."""

import argparse
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import select

from .database import Base, SessionLocal, engine
from .config import IMAGE_STORAGE_DIR
from .embedded_images import extract_embedded_images
from .google_sheets import GoogleSheetSource, GoogleSheetsConfigurationError, export_workbook_as_xlsx, fetch_values
from .import_workbook import FIELD_ALIASES, STABLE_ROW_ID_ALIASES, TabularSheet, sync_tabular_sheets
from .models import DataSource, SourceSheetConfig
from .normalization import clean_text, image_url_from_google_sheets_formula, normalise_header


def merge_google_sheets_image_formulas(
    formatted_rows: list[list[object]],
    formula_rows: list[list[object]],
) -> list[list[object]]:
    """Replace image-formula display cells with their URL for the importer.

    Google Sheets returns a rendered image (often an empty value) for an
    ``IMAGE()`` cell in formatted-value mode. The same cell is available as a
    formula in formula mode. We only merge that formula into columns named
    ``รูปภาพ`` so ordinary formulas and all other source data stay untouched.
    """
    rows = [list(row) for row in formatted_rows]
    if not rows:
        return rows
    image_columns = {
        index for index, header in enumerate(rows[0])
        if normalise_header(header) in FIELD_ALIASES["image_url"]
    }
    if not image_columns:
        return rows

    for row_index in range(1, len(rows)):
        formula_row = formula_rows[row_index] if row_index < len(formula_rows) else []
        for column_index in image_columns:
            formula_value = formula_row[column_index] if column_index < len(formula_row) else None
            image_url = image_url_from_google_sheets_formula(formula_value)
            if image_url:
                while len(rows[row_index]) <= column_index:
                    rows[row_index].append(None)
                rows[row_index][column_index] = image_url
    return rows


def extract_google_sheets_embedded_images(
    source_name: str,
    spreadsheet_id: str,
    sheets: list[TabularSheet],
) -> tuple[dict[str, dict[int, str]], dict[str, set[int]], int]:
    """Read images preserved by Google's read-only XLSX export.

    The export is held only in a temporary directory. Extracted image files are
    saved through the same controlled local storage used for regular Excel
    imports, and only anchors under the ``รูปภาพ`` column are accepted.
    """
    photo_columns_by_sheet: dict[str, int] = {}
    for sheet in sheets:
        rows = list(sheet.rows)
        if not rows:
            continue
        for index, header in enumerate(rows[0]):
            if normalise_header(header) in FIELD_ALIASES["image_url"]:
                photo_columns_by_sheet[sheet.name] = index
                break
    if not photo_columns_by_sheet:
        return {}, {}, 0

    exported_workbook = export_workbook_as_xlsx(spreadsheet_id)
    with TemporaryDirectory(prefix="central-data-hub-") as directory:
        workbook_path = Path(directory) / "google-sheet-export.xlsx"
        workbook_path.write_bytes(exported_workbook)
        result = extract_embedded_images(
            workbook_path,
            source_name,
            photo_columns_by_sheet,
            IMAGE_STORAGE_DIR,
        )
    return result.urls_by_sheet_row, result.duplicate_rows_by_sheet, result.exported_count


def _preview(sheets: list[TabularSheet]) -> dict:
    known_aliases = {alias for aliases in FIELD_ALIASES.values() for alias in aliases}
    tabs = []
    for sheet in sheets:
        values = list(sheet.rows)
        headers = [normalise_header(value) for value in values[0]] if values else []
        stable_id_index = next((headers.index(alias) for alias in STABLE_ROW_ID_ALIASES if alias in headers), None)
        stable_ids = [
            clean_text(row[stable_id_index]) if stable_id_index is not None and stable_id_index < len(row) else None
            for row in values[1:]
        ]
        non_empty_stable_ids = [stable_id for stable_id in stable_ids if stable_id]
        tabs.append({
            "sheet": sheet.name,
            "rows_received": max(len(values) - 1, 0),
            "recognised_headers": sorted(set(headers).intersection(known_aliases)),
            "ready_to_import": bool(set(headers).intersection(known_aliases)),
            "stable_id_header": headers[stable_id_index] if stable_id_index is not None else None,
            "rows_with_stable_id": len(non_empty_stable_ids),
            "rows_missing_stable_id": max(len(values) - 1 - len(non_empty_stable_ids), 0),
            "duplicate_stable_ids": len(non_empty_stable_ids) - len(set(non_empty_stable_ids)),
        })
    return {"dry_run": True, "sheets": tabs}


def sync_google_source(source_name: str, dry_run: bool = False) -> dict:
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        source = session.scalar(select(DataSource).where(DataSource.name == source_name))
        if source is None or source.connection_type != "google_sheets":
            raise ValueError("ไม่พบ Google Sheets source ที่ได้รับอนุมัติใน Data Catalog")
        if not source.is_active:
            raise ValueError("source นี้ถูกปิดการใช้งาน")
        if not source.external_id:
            raise ValueError("source นี้ไม่มี spreadsheet ID")
        configs = session.scalars(select(SourceSheetConfig).where(
            SourceSheetConfig.source_id == source.id,
            SourceSheetConfig.is_active.is_(True),
        ).order_by(SourceSheetConfig.sheet_name)).all()
        if not configs:
            raise ValueError("source นี้ยังไม่มีชีตที่ได้รับอนุมัติ")

        # Fetch all remote data before opening a database sync run. A remote
        # failure therefore cannot partially import another tab.
        sheets = []
        for config in configs:
            google_source = GoogleSheetSource(source.external_id, config.sheet_name, config.read_range)
            values = fetch_values(google_source)
            formula_values = fetch_values(google_source, value_render_option="FORMULA")
            sheets.append(TabularSheet(
                name=config.sheet_name,
                rows=merge_google_sheets_image_formulas(values, formula_values),
                header_row_number=config.header_row_number,
                source_url=f"https://docs.google.com/spreadsheets/d/{source.external_id}/edit",
            ))
        if dry_run:
            return _preview(sheets)

        image_exported_count = 0
        image_export_warning = None
        try:
            image_urls, duplicate_image_rows, image_exported_count = extract_google_sheets_embedded_images(
                source.name,
                source.external_id,
                sheets,
            )
            sheets = [replace(
                sheet,
                embedded_image_urls_by_row=image_urls.get(sheet.name, {}),
                duplicate_embedded_image_rows=duplicate_image_rows.get(sheet.name, set()),
            ) for sheet in sheets]
        except GoogleSheetsConfigurationError as error:
            image_export_warning = str(error)
        except Exception as error:
            # A failure in the optional Drive export must not stop normal text
            # sync. Formula/URL image support remains available in that case.
            # Keep a short non-sensitive error type so staff can distinguish an
            # export permission failure from an unsupported image layout.
            image_export_warning = (
                "export Google Sheets สำเร็จไม่ครบ จึงยังอ่านรูปภาพที่ฝังไม่ได้ "
                f"({type(error).__name__})"
            )

        result = sync_tabular_sheets(
            session,
            source,
            sheets,
            "Synced from approved Google Sheets source"
            + (f"; embedded images exported: {image_exported_count}" if image_exported_count else "")
            + (f"; {image_export_warning}" if image_export_warning else ""),
            reconcile_missing=True,
        )
        result["embedded_images_exported"] = image_exported_count
        if image_export_warning:
            result["image_export_warning"] = image_export_warning
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read-only sync for an approved Google Sheets source")
    parser.add_argument("--source-name", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(sync_google_source(args.source_name, args.dry_run), ensure_ascii=False, indent=2))
