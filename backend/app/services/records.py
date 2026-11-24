"""Record serialisation and the rules for records edited by administrators."""

import hashlib
import json
from collections.abc import Sequence

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import DataSource, Record, SourceSheetConfig
from ..normalization import clean_multiline_text, clean_text, normalise_image_url
from ..schemas import RecordMutation

EDITABLE_RECORD_FIELDS = (
    "registration_no", "previous_registration_no", "title_description", "dimensions_text", "material",
    "period", "provenance", "image_url", "status_data_check", "status_photographed",
    "status_antique", "status_storage",
)
MULTILINE_RECORD_FIELDS = {"title_description", "dimensions_text", "period", "provenance"}
CREATE_REQUIRED_FIELDS = {
    "registration_no": "เลขทะเบียน",
    "title_description": "รายการ",
}
MANUAL_SOURCE_NAME = "แก้ไขโดยเจ้าหน้าที่"


def record_summary(record: Record) -> dict:
    """The fields shown in lists and cards."""
    return {
        "id": record.id,
        "registration_no": record.registration_no,
        "previous_registration_no": record.previous_registration_no,
        "title_description": record.title_description,
        "material": record.material,
        "period": record.period,
        "image_url": record.image_url,
        "status_data_check": record.status_data_check,
        "status_photographed": record.status_photographed,
        "status_antique": record.status_antique,
        "status_storage": record.status_storage,
        "source_id": record.source_id,
        "source_name": record.source.name if record.source else None,
        "source_sheet": record.source_sheet,
        "source_row_number": record.source_row_number,
        "updated_at": record.updated_at,
    }


def editable_snapshot(record: Record) -> dict:
    return {field: getattr(record, field) for field in EDITABLE_RECORD_FIELDS}


def record_hash(values: dict) -> str:
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def mutation_values(payload: RecordMutation) -> dict:
    """Clean only the fields the administrator actually sent."""
    values = {}
    for field in payload.model_fields_set:
        value = getattr(payload, field)
        if field == "image_url":
            values[field] = normalise_image_url(value)
        elif field in MULTILINE_RECORD_FIELDS:
            values[field] = clean_multiline_text(value)
        else:
            values[field] = clean_text(value)
    return values


def require_create_values(values: dict) -> None:
    missing_labels = [label for field, label in CREATE_REQUIRED_FIELDS.items() if not values.get(field)]
    if missing_labels:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"กรุณากรอกข้อมูลบังคับ: {', '.join(missing_labels)}",
        )


def manual_source(session: Session) -> DataSource:
    """The source that owns records created by hand in the admin page."""
    source = session.scalar(select(DataSource).where(DataSource.name == MANUAL_SOURCE_NAME))
    if source is None:
        source = DataSource(
            name=MANUAL_SOURCE_NAME,
            owner_name="ผู้ดูแลระบบ",
            description="ระเบียนที่สร้างจากหน้าจัดการข้อมูลของ Central Data Hub",
            connection_type="manual_entry",
            classification="internal",
            is_active=True,
        )
        session.add(source)
        session.flush()
    return source


def sheet_configs(session: Session, source_id: int) -> Sequence[SourceSheetConfig]:
    """The approved tabs of one source, by name."""
    return session.scalars(
        select(SourceSheetConfig).where(SourceSheetConfig.source_id == source_id).order_by(SourceSheetConfig.sheet_name)
    ).all()
