"""Browsing records: the Explorer list, its filters and the record detail page."""

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from ..config import PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX
from ..dependencies import SessionDep
from ..models import Record
from ..record_images import image_summary
from ..services import filters
from ..services.cache import cached_for_records
from ..services.locations import approved_locations, record_location
from ..services.records import record_summary

router = APIRouter(tags=["records"])


@router.get("/api/records")
def list_records(
    session: SessionDep,
    q: str | None = None,
    source_id: int | None = None,
    source_sheet: str | None = None,
    material: str | None = None,
    period: str | None = None,
    material_group: str | None = None,
    period_group: str | None = None,
    status_data_check: str | None = None,
    status_photographed: str | None = None,
    status_antique: str | None = None,
    status_storage: str | None = None,
    registration_year: str | None = Query(default=None, pattern=r"^\d{4}$"),
    attention: str | None = Query(default=None, pattern="^(data_check|photographed|antique|storage)$"),
    has_description: bool | None = None,
    has_image: bool | None = None,
    sort_by: str = Query(default="registration", pattern="^(registration|source)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
) -> dict:
    record_filters = filters.RecordFilters(
        q=q, source_id=source_id, source_sheet=source_sheet, material=material, period=period,
        material_group=material_group, period_group=period_group,
        status_data_check=status_data_check, status_photographed=status_photographed,
        status_antique=status_antique, status_storage=status_storage,
        registration_year=registration_year, attention=attention,
        has_description=has_description, has_image=has_image,
    )
    statement = filters.apply_record_filters(select(Record).join(Record.source), record_filters)
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    order_by = (
        (Record.source_sheet, Record.source_row_number, Record.id)
        if sort_by == "source"
        else (Record.registration_no, Record.id)
    )
    records = session.scalars(
        statement.order_by(*order_by).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [record_summary(record) for record in records],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/api/filter-options")
def filter_options(session: SessionDep) -> dict:
    return cached_for_records(session, "filter_options", lambda: filters.filter_options(session))


@router.get("/api/records/{record_id}")
def get_record(record_id: int, session: SessionDep) -> dict:
    record = session.get(Record, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="ไม่พบระเบียน")
    duplicates = []
    if record.registration_no:
        duplicates = session.scalars(select(Record).where(
            Record.registration_no == record.registration_no,
            Record.id != record.id,
        ).limit(20)).all()
    return {
        **record_summary(record),
        "dimensions_text": record.dimensions_text,
        "provenance": record.provenance,
        "image_url": record.image_url,
        "source_url": record.source_url,
        "source_row_number": record.source_row_number,
        "raw_data": record.raw_data,
        "images": [image_summary(image) for image in record.images],
        "duplicate_candidates": [record_summary(candidate) for candidate in duplicates],
        # The record's own storage location when its source is a storage-room list.
        "location": record_location(record),
        "linked_locations": approved_locations(session, record),
    }
