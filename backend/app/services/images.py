"""Central copies of record images uploaded by administrators."""

import hashlib
import shutil

from sqlalchemy.orm import Session

from ..config import IMAGE_STORAGE_DIR
from ..models import Record
from ..record_images import store_record_image

MAX_IMAGE_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_IMAGE_BATCH_FILES = 100
MAX_IMAGE_BATCH_BYTES = 100 * 1024 * 1024


def store_central_image(session: Session, record: Record, content: bytes, suffix: str) -> str:
    """Store a manually supplied image in the multi-image gallery."""
    image, _ = store_record_image(
        session, record, content, suffix, origin="manual", original_filename="manual-upload", position=1
    )
    record.image_url = image.image_url
    record.raw_data = {**(record.raw_data or {}), "_manual_image_url": image.image_url}
    return image.image_url


def remove_xlsx_image_cache(source_name: str) -> int:
    """Remove only the image-cache directory deterministically owned by one XLSX source.

    The original workbook is never located below ``IMAGE_STORAGE_DIR`` and is
    therefore unaffected. The exact child name mirrors ``embedded_images``.
    """
    root = IMAGE_STORAGE_DIR.resolve()
    source_key = hashlib.sha256(source_name.encode("utf-8")).hexdigest()[:16]
    cache_dir = (root / source_key).resolve()
    if cache_dir.parent != root or not cache_dir.is_dir():
        return 0
    file_count = sum(1 for path in cache_dir.rglob("*") if path.is_file())
    shutil.rmtree(cache_dir)
    return file_count
