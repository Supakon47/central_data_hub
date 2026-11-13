"""Read-only diagnostics for a configured Google Sheets Image Bridge."""

from __future__ import annotations

import argparse
import json

from sqlalchemy import select

from .database import Base, SessionLocal, engine
from .google_sheets import _credential_info, google_drive_read_service
from .models import DataSource, ImageBridgeConfig


def inspect_google_image_bridge(source_name: str) -> dict:
    """Show what the configured service account can see in one Bridge folder.

    This does not create, modify, download, or delete any Google Drive files.
    """
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        source = session.scalar(select(DataSource).where(DataSource.name == source_name))
        if source is None or source.connection_type != "google_sheets":
            raise ValueError("ไม่พบแหล่งข้อมูล Google Sheets ที่ได้รับอนุมัติ")
        config = session.scalar(select(ImageBridgeConfig).where(
            ImageBridgeConfig.source_id == source.id,
            ImageBridgeConfig.is_active.is_(True),
        ))
        if config is None:
            raise ValueError("แหล่งข้อมูลนี้ยังไม่ได้ตั้งค่า Image Bridge")

        credential = _credential_info()
        drive = google_drive_read_service()
        folder = drive.files().get(
            fileId=config.drive_folder_id,
            fields="id,name,mimeType,capabilities(canListChildren)",
            supportsAllDrives=True,
        ).execute()
        response = drive.files().list(
            q=f"'{config.drive_folder_id}' in parents and trashed = false",
            pageSize=100,
            orderBy="name",
            fields="files(id,name,mimeType,size,modifiedTime)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files = response.get("files", [])
        return {
            "source_name": source.name,
            "service_account_email": credential.get("client_email"),
            "bridge_folder": folder,
            "expected_manifest": config.manifest_file_name,
            "files_visible_to_service_account": files,
            "manifest_visible": any(file.get("name") == config.manifest_file_name for file in files),
        }
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inspect a configured Google Sheets Image Bridge")
    parser.add_argument("--source-name", required=True)
    args = parser.parse_args()
    print(json.dumps(inspect_google_image_bridge(args.source_name), ensure_ascii=False, indent=2))
