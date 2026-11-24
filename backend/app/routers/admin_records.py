"""Administrator edits to central records and their images. Source files stay read-only."""

import uuid
from collections import Counter
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..dependencies import AdminDep, SessionDep
from ..models import DataQualityIssue, DataSource, Record
from ..normalization import clean_text
from ..record_images import uploaded_image_suffix
from ..schemas import RecordMutation
from ..services.audit import add_audit
from ..services.images import (
    MAX_IMAGE_BATCH_BYTES,
    MAX_IMAGE_BATCH_FILES,
    MAX_IMAGE_UPLOAD_BYTES,
    store_central_image,
)
from ..services.records import (
    editable_snapshot,
    manual_source,
    mutation_values,
    record_hash,
    record_summary,
    require_create_values,
)

router = APIRouter(tags=["admin: records"])

# Source rows with a stable ID have a row key of "id-<record_id>".
STABLE_ID_PREFIX = "id-"


def get_record_or_404(session: Session, record_id: int) -> Record:
    record = session.get(Record, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="ไม่พบระเบียน")
    return record


@router.post("/api/admin/records", status_code=status.HTTP_201_CREATED)
def create_record(payload: RecordMutation, session: SessionDep, _: AdminDep) -> dict:
    values = mutation_values(payload)
    require_create_values(values)
    source = manual_source(session)
    record = Record(
        source_id=source.id,
        source_sheet="Manual",
        source_row_number=0,
        source_row_key=f"manual-{uuid.uuid4()}",
        source_url=None,
        raw_hash=record_hash(values),
        raw_data={"_manual_entry": True, **values},
        **values,
    )
    session.add(record)
    session.flush()
    add_audit(session, "create", record.id, None, editable_snapshot(record))
    session.commit()
    session.refresh(record)
    return record_summary(record)


@router.patch("/api/admin/records/{record_id}")
def update_record(record_id: int, payload: RecordMutation, session: SessionDep, _: AdminDep) -> dict:
    record = get_record_or_404(session, record_id)
    values = mutation_values(payload)
    if not values:
        raise HTTPException(status_code=422, detail="ยังไม่ได้ระบุข้อมูลที่ต้องการแก้ไข")
    before = {field: getattr(record, field) for field in values}
    for field, value in values.items():
        setattr(record, field, value)
    # raw_hash intentionally remains tied to imported raw data. An unchanged
    # source row will not erase a local correction; a changed source row will.
    add_audit(session, "update", record.id, before, {field: getattr(record, field) for field in values})
    session.commit()
    session.refresh(record)
    return record_summary(record)


@router.delete("/api/admin/records/{record_id}")
def delete_record(record_id: int, session: SessionDep, _: AdminDep) -> dict:
    record = get_record_or_404(session, record_id)
    add_audit(session, "delete", record.id, editable_snapshot(record), None)
    for issue in session.scalars(select(DataQualityIssue).where(DataQualityIssue.record_id == record.id)).all():
        issue.record_id = None
    session.delete(record)
    session.commit()
    return {"deleted": True, "record_id": record_id}


@router.post("/api/admin/records/{record_id}/image")
async def upload_record_image(
    record_id: int,
    image: Annotated[UploadFile, File(description="ภาพ JPEG, PNG, GIF หรือ WebP ขนาดไม่เกิน 10 MB")],
    session: SessionDep,
    _: AdminDep,
) -> dict:
    """Store an administrator-approved central image for one existing record."""
    record = get_record_or_404(session, record_id)
    content = await image.read(MAX_IMAGE_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(status_code=422, detail="กรุณาเลือกไฟล์รูปภาพ")
    if len(content) > MAX_IMAGE_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="ไฟล์รูปต้องมีขนาดไม่เกิน 10 MB")
    suffix = uploaded_image_suffix(content)
    if suffix is None:
        raise HTTPException(status_code=422, detail="รองรับเฉพาะไฟล์ JPEG, PNG, GIF และ WebP")

    before = {"image_url": record.image_url}
    image_url = store_central_image(session, record, content, suffix)
    add_audit(session, "upload_image", record.id, before, {"image_url": image_url})
    session.commit()
    return {"record_id": record.id, "image_url": image_url}


@router.get("/api/admin/image-intake/sources")
def image_intake_sources(session: SessionDep, _: AdminDep) -> dict:
    """List only source tabs that have stable IDs suitable for batch image matching."""
    sources = session.scalars(
        select(DataSource).where(DataSource.is_active.is_(True)).order_by(DataSource.name)
    ).all()
    items = []
    for source in sources:
        sheets = session.execute(
            select(Record.source_sheet, func.count(Record.id))
            .where(Record.source_id == source.id, Record.source_row_key.like(f"{STABLE_ID_PREFIX}%"))
            .group_by(Record.source_sheet)
            .order_by(Record.source_sheet)
        ).all()
        if sheets:
            items.append({
                "id": source.id,
                "name": source.name,
                "sheets": [{"name": sheet_name, "record_count": count} for sheet_name, count in sheets],
            })
    return {"sources": items}


def stable_ids_from_filenames(images: list[UploadFile]) -> tuple[list[tuple[str, UploadFile]], list[str]]:
    """Pair each upload with the record ID in its filename; report unusable names."""
    candidates: list[tuple[str, UploadFile]] = []
    invalid_files: list[str] = []
    for image in images:
        file_name = (image.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
        stable_id = clean_text(Path(file_name).stem)
        if not stable_id:
            invalid_files.append(file_name or "ไฟล์ไม่มีชื่อ")
            continue
        candidates.append((stable_id, image))

    duplicate_ids = {stable_id for stable_id, count in Counter(item[0] for item in candidates).items() if count > 1}
    candidates = [item for item in candidates if item[0] not in duplicate_ids]
    invalid_files.extend(f"{stable_id} (ชื่อไฟล์ซ้ำในชุดที่เลือก)" for stable_id in sorted(duplicate_ids))
    return candidates, invalid_files


@router.post("/api/admin/image-intake/{source_id}")
async def upload_source_images(
    source_id: int,
    sheet_name: Annotated[str, Form(min_length=1, max_length=255)],
    images: Annotated[list[UploadFile], File(description="ชื่อไฟล์ต้องตรงกับ record_id")],
    session: SessionDep,
    _: AdminDep,
) -> dict:
    """Match a batch of local image filenames to stable record_id values in one tab.

    The source spreadsheet remains read-only.  Files named e.g. ARC-69-0001.jpg
    match a record whose source row key is id-ARC-69-0001.
    """
    source = session.get(DataSource, source_id)
    if source is None or not source.is_active:
        raise HTTPException(status_code=404, detail="ไม่พบแหล่งข้อมูลที่ใช้งานอยู่")
    if not images:
        raise HTTPException(status_code=422, detail="กรุณาเลือกไฟล์รูปภาพอย่างน้อย 1 ไฟล์")
    if len(images) > MAX_IMAGE_BATCH_FILES:
        raise HTTPException(status_code=413, detail=f"เลือกได้ไม่เกิน {MAX_IMAGE_BATCH_FILES} ไฟล์ต่อครั้ง")

    candidates, invalid_files = stable_ids_from_filenames(images)
    records = session.scalars(
        select(Record).where(
            Record.source_id == source.id,
            Record.source_sheet == sheet_name,
            Record.source_row_key.in_([f"{STABLE_ID_PREFIX}{stable_id}" for stable_id, _ in candidates]),
        )
    ).all()
    records_by_stable_id = {record.source_row_key.removeprefix(STABLE_ID_PREFIX): record for record in records}

    unmatched: list[str] = []
    uploaded = 0
    total_bytes = 0
    for stable_id, image in candidates:
        record = records_by_stable_id.get(stable_id)
        if record is None:
            unmatched.append(stable_id)
            continue
        content = await image.read(MAX_IMAGE_UPLOAD_BYTES + 1)
        if not content:
            invalid_files.append(f"{stable_id} (ไฟล์ว่าง)")
            continue
        if len(content) > MAX_IMAGE_UPLOAD_BYTES:
            invalid_files.append(f"{stable_id} (เกิน 10 MB)")
            continue
        if total_bytes + len(content) > MAX_IMAGE_BATCH_BYTES:
            invalid_files.append(f"{stable_id} (เกินขนาดรวม {MAX_IMAGE_BATCH_BYTES // 1024 // 1024} MB ต่อครั้ง)")
            continue
        suffix = uploaded_image_suffix(content)
        if suffix is None:
            invalid_files.append(f"{stable_id} (ไม่ใช่ JPEG, PNG, GIF หรือ WebP)")
            continue
        before = {"image_url": record.image_url}
        image_url = store_central_image(session, record, content, suffix)
        add_audit(
            session,
            "batch_upload_image",
            record.id,
            before,
            {"image_url": image_url, "matched_record_id": stable_id},
        )
        uploaded += 1
        total_bytes += len(content)

    session.commit()
    return {
        "source_name": source.name,
        "sheet_name": sheet_name,
        "uploaded": uploaded,
        "unmatched": unmatched[:20],
        "unmatched_count": len(unmatched),
        "invalid_files": invalid_files[:20],
        "invalid_count": len(invalid_files),
    }
