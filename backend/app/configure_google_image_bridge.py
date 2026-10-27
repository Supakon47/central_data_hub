"""Register one Apps-Script-owned Drive image folder for an approved source."""

import argparse
import json

from sqlalchemy import select

from .database import Base, SessionLocal, engine
from .models import DataSource, ImageBridgeConfig


def configure_google_image_bridge(
    source_name: str,
    drive_folder_id: str,
    manifest_file_name: str = "central-data-hub-images.json",
) -> dict:
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        source = session.scalar(select(DataSource).where(DataSource.name == source_name))
        if source is None or source.connection_type != "google_sheets":
            raise ValueError("ไม่พบแหล่งข้อมูล Google Sheets ที่ได้รับอนุมัติ")
        if not drive_folder_id.strip() or not manifest_file_name.strip():
            raise ValueError("ต้องระบุ Drive folder ID และชื่อไฟล์ manifest")
        if "/" in manifest_file_name or "\\" in manifest_file_name:
            raise ValueError("ชื่อไฟล์ manifest ต้องไม่มี / หรือ \\")
        config = session.scalar(select(ImageBridgeConfig).where(ImageBridgeConfig.source_id == source.id))
        if config is None:
            config = ImageBridgeConfig(
                source_id=source.id,
                drive_folder_id=drive_folder_id.strip(),
                manifest_file_name=manifest_file_name.strip(),
                is_active=True,
            )
            session.add(config)
        else:
            config.drive_folder_id = drive_folder_id.strip()
            config.manifest_file_name = manifest_file_name.strip()
            config.is_active = True
        session.commit()
        return {
            "source_name": source.name,
            "source_id": source.id,
            "drive_folder_id": config.drive_folder_id,
            "manifest_file_name": config.manifest_file_name,
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Configure an approved Google Sheets Image Bridge folder")
    parser.add_argument("--source-name", required=True)
    parser.add_argument("--drive-folder-id", required=True)
    parser.add_argument("--manifest-file-name", default="central-data-hub-images.json")
    args = parser.parse_args()
    print(json.dumps(configure_google_image_bridge(**vars(args)), ensure_ascii=False, indent=2))
