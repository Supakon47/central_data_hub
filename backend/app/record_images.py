"""Safe central storage helpers for one-or-many record images."""

from __future__ import annotations

import hashlib
from pathlib import Path
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import IMAGE_STORAGE_DIR
from .models import Record, RecordImage


IMAGE_SIGNATURES = (
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
    (b"RIFF", ".webp"),
)


def uploaded_image_suffix(content: bytes) -> str | None:
    """Return a browser-safe suffix after checking the file signature."""
    for signature, suffix in IMAGE_SIGNATURES:
        if content.startswith(signature):
            if suffix != ".webp" or content[8:12] == b"WEBP":
                return suffix
    return None


def image_summary(image: RecordImage) -> dict:
    return {
        "id": image.id,
        "url": image.image_url,
        "original_filename": image.original_filename,
        "origin": image.origin,
        "source_sheet": image.source_sheet,
        "position": image.position,
    }


def store_record_image(
    session: Session,
    record: Record,
    content: bytes,
    suffix: str,
    *,
    origin: str,
    source_id: int | None = None,
    source_sheet: str | None = None,
    remote_file_id: str | None = None,
    original_filename: str | None = None,
    position: int = 1,
) -> tuple[RecordImage, bool]:
    """Persist an image copy and return ``(image, changed)``.

    A Drive file ID is treated as stable identity. Re-running an unchanged
    bridge manifest therefore does not duplicate an image in the gallery.
    """
    digest = hashlib.sha256(content).hexdigest()
    existing = None
    if remote_file_id:
        existing = session.scalar(select(RecordImage).where(
            RecordImage.record_id == record.id,
            RecordImage.origin == origin,
            RecordImage.remote_file_id == remote_file_id,
        ))
        if existing and existing.content_sha256 == digest:
            existing.position = position
            existing.original_filename = original_filename or existing.original_filename
            existing.source_sheet = source_sheet or existing.source_sheet
            return existing, False

    relative_path = Path(origin) / f"record-{record.id}" / f"{uuid.uuid4().hex}{suffix}"
    output_path = IMAGE_STORAGE_DIR / relative_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(content)
    image_url = f"/media/{relative_path.as_posix()}"

    if existing is None:
        image = RecordImage(
            record_id=record.id,
            source_id=source_id,
            image_url=image_url,
            storage_path=relative_path.as_posix(),
            original_filename=original_filename,
            content_sha256=digest,
            origin=origin,
            remote_file_id=remote_file_id,
            source_sheet=source_sheet,
            position=position,
        )
        session.add(image)
    else:
        # Keep the old local copy on disk for now; deleting a file that may be
        # open in a browser is not worth risking a broken detail page. It can
        # be cleaned up later by a deliberate maintenance task.
        image = existing
        image.image_url = image_url
        image.storage_path = relative_path.as_posix()
        image.original_filename = original_filename
        image.content_sha256 = digest
        image.source_id = source_id
        image.source_sheet = source_sheet
        image.position = position

    session.flush()
    # Existing screens still use ``image_url`` as their single preview. Make
    # the first central image available there without removing any source URL.
    if not record.image_url:
        record.image_url = image_url
    return image, True
