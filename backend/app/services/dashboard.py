"""Counts for the Dashboard and the duplicate-registration review list."""

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Record
from .filters import ATTENTION_STATUS_FIELDS, UNSPECIFIED, is_filled
from .records import record_summary

# Only the summary columns: loading whole records (with raw_data) is slow.
DASHBOARD_COLUMNS = (
    Record.registration_no, Record.title_description, Record.image_url, Record.source_sheet,
    Record.status_data_check, Record.status_photographed, Record.status_antique, Record.status_storage,
)


def scope_conditions(source_id: int | None, source_sheet: str | None) -> list:
    conditions = []
    if source_id:
        conditions.append(Record.source_id == source_id)
    if source_sheet:
        conditions.append(Record.source_sheet == source_sheet)
    return conditions


def dashboard_summary(session: Session, source_id: int | None, source_sheet: str | None) -> dict:
    records = session.execute(select(*DASHBOARD_COLUMNS).where(*scope_conditions(source_id, source_sheet))).all()
    registration_counts = Counter(record.registration_no for record in records if record.registration_no)
    duplicate_registration_counts = {
        registration_no: count for registration_no, count in registration_counts.items() if count > 1
    }

    def counter(field: str) -> list[dict]:
        counts = Counter(getattr(record, field) or UNSPECIFIED for record in records)
        return [{"label": label, "count": count} for label, count in counts.most_common()]

    def pending_count(field: str, completed_status: str) -> int:
        return sum((getattr(record, field) or "").strip() != completed_status for record in records)

    return {
        "total_records": len(records),
        "with_registration_no": sum(bool(record.registration_no) for record in records),
        "with_description": sum(bool(record.title_description) for record in records),
        "with_image_url": sum(bool(record.image_url) for record in records),
        "duplicate_registration_groups": len(duplicate_registration_counts),
        "records_in_duplicate_registration_groups": sum(duplicate_registration_counts.values()),
        "follow_up": {
            attention: pending_count(column.key, completed_status)
            for attention, (column, completed_status) in ATTENTION_STATUS_FIELDS.items()
        },
        "by_source_sheet": counter("source_sheet"),
        "by_data_check": counter("status_data_check"),
        "by_photo": counter("status_photographed"),
        "by_antique": counter("status_antique"),
        "by_storage": counter("status_storage"),
    }


def duplicate_groups(session: Session, source_id: int | None, source_sheet: str | None, limit: int) -> dict:
    """Exact duplicate registration numbers for staff review, never for automatic merging."""
    scope = scope_conditions(source_id, source_sheet)
    grouped_statement = (
        select(Record.registration_no, func.count(Record.id).label("record_count"))
        .where(is_filled(Record.registration_no), *scope)
        .group_by(Record.registration_no)
        .having(func.count(Record.id) > 1)
    )
    total_groups = session.scalar(select(func.count()).select_from(grouped_statement.subquery())) or 0
    grouped = session.execute(
        grouped_statement.order_by(func.count(Record.id).desc(), Record.registration_no).limit(limit)
    ).all()
    registration_numbers = [row.registration_no for row in grouped]
    records_by_registration: dict[str, list[Record]] = {registration_no: [] for registration_no in registration_numbers}
    if registration_numbers:
        ordered_records = (
            select(Record).join(Record.source)
            .where(Record.registration_no.in_(registration_numbers), *scope)
            .order_by(Record.registration_no, Record.source_sheet, Record.source_row_number)
        )
        for record in session.scalars(ordered_records).all():
            records_by_registration[record.registration_no].append(record)
    return {
        "total_groups": total_groups,
        "groups": [{
            "registration_no": row.registration_no,
            "count": row.record_count,
            "records": [record_summary(record) for record in records_by_registration[row.registration_no]],
        } for row in grouped],
    }
