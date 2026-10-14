"""Synchronise pre-approved Google Sheets tabs into the central database."""

import argparse
import json

from sqlalchemy import select

from .database import Base, SessionLocal, engine
from .google_sheets import GoogleSheetSource, fetch_values
from .import_workbook import FIELD_ALIASES, STABLE_ROW_ID_ALIASES, TabularSheet, sync_tabular_sheets
from .models import DataSource, SourceSheetConfig
from .normalization import clean_text, normalise_header


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
            values = fetch_values(GoogleSheetSource(source.external_id, config.sheet_name, config.read_range))
            sheets.append(TabularSheet(
                name=config.sheet_name,
                rows=values,
                header_row_number=config.header_row_number,
                source_url=f"https://docs.google.com/spreadsheets/d/{source.external_id}/edit",
            ))
        if dry_run:
            return _preview(sheets)

        result = sync_tabular_sheets(
            session,
            source,
            sheets,
            "Synced from approved Google Sheets source",
            reconcile_missing=True,
        )
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
