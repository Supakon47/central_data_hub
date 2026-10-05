"""Register one approved, read-only Google Sheets source in Data Catalog."""

import argparse
import json

from sqlalchemy import select

from .database import Base, SessionLocal, engine
from .google_sheets import GoogleSheetSource
from .models import DataSource, SourceSheetConfig


def configure_google_sheet(
    source_name: str,
    spreadsheet_id: str,
    sheet_name: str,
    read_range: str = "A:ZZ",
    header_row_number: int = 1,
    owner_name: str | None = None,
    description: str | None = None,
    classification: str = "internal",
    sync_frequency_minutes: int | None = None,
) -> dict:
    """Create or update an allow-listed source without reading Google data."""
    if not source_name.strip() or not spreadsheet_id.strip() or not sheet_name.strip():
        raise ValueError("ต้องระบุ source name, spreadsheet ID และชื่อชีต")
    GoogleSheetSource(spreadsheet_id, sheet_name, read_range).a1_range
    if header_row_number != 1:
        raise ValueError("MVP ปัจจุบันรองรับหัวตารางที่แถวแรกของ range เท่านั้น (--header-row 1)")

    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        source = session.scalar(select(DataSource).where(DataSource.name == source_name))
        if source is not None and source.connection_type != "google_sheets":
            raise ValueError("พบชื่อแหล่งข้อมูลนี้แล้ว แต่เป็นคนละประเภทการเชื่อมต่อ")
        if source is None:
            source = DataSource(
                name=source_name,
                owner_name=owner_name or "ยังไม่ระบุ",
                description=description or "Google Sheets ที่อนุมัติให้ sync แบบอ่านอย่างเดียว",
                connection_type="google_sheets",
                external_id=spreadsheet_id,
                classification=classification,
                sync_frequency_minutes=sync_frequency_minutes,
                is_active=True,
            )
            session.add(source)
            session.flush()
        else:
            source.external_id = spreadsheet_id
            source.classification = classification
            if sync_frequency_minutes is not None:
                source.sync_frequency_minutes = sync_frequency_minutes
            if owner_name:
                source.owner_name = owner_name
            if description:
                source.description = description

        config = session.scalar(select(SourceSheetConfig).where(
            SourceSheetConfig.source_id == source.id,
            SourceSheetConfig.sheet_name == sheet_name,
        ))
        if config is None:
            config = SourceSheetConfig(source_id=source.id, sheet_name=sheet_name)
            session.add(config)
        config.read_range = read_range
        config.header_row_number = header_row_number
        config.is_active = True
        session.commit()
        return {
            "source_id": source.id,
            "source_name": source.name,
            "connection_type": source.connection_type,
            "spreadsheet_id": source.external_id,
            "sheet_name": config.sheet_name,
            "read_range": config.read_range,
            "header_row_number": config.header_row_number,
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Register an approved Google Sheets tab for read-only sync")
    parser.add_argument("--source-name", required=True)
    parser.add_argument("--spreadsheet-id", required=True)
    parser.add_argument("--sheet", required=True, dest="sheet_name")
    parser.add_argument("--read-range", default="A:ZZ")
    parser.add_argument("--header-row", type=int, default=1, dest="header_row_number")
    parser.add_argument("--owner")
    parser.add_argument("--description")
    parser.add_argument("--classification", default="internal")
    parser.add_argument("--sync-frequency-minutes", type=int)
    args = parser.parse_args()
    print(json.dumps(configure_google_sheet(**vars(args)), ensure_ascii=False, indent=2))
