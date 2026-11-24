"""Small helpers that insert test rows the way an import would."""

from itertools import count

from sqlalchemy.orm import Session

from app.models import DataQualityIssue, DataSource, Record

_row_numbers = count(1)


def add_source(session: Session, name: str, connection_type: str = "xlsx_import") -> DataSource:
    source = DataSource(name=name, connection_type=connection_type)
    session.add(source)
    session.flush()
    return source


def add_record(
    session: Session,
    source: DataSource,
    registration_no: str | None,
    title: str | None = None,
    shelf: str | None = None,
    sheet: str = "Sheet1",
    **fields,
) -> Record:
    """A source row; ``shelf`` adds the location column a storage-room list has."""
    row_number = next(_row_numbers)
    raw_data = {"เลขทะเบียน": registration_no, "รายการ": title}
    if shelf is not None:
        raw_data["ชั้นวาง"] = shelf
    record = Record(
        source_id=source.id,
        source_sheet=sheet,
        source_row_number=row_number,
        source_row_key=f"row-{row_number}",
        raw_hash=f"hash-{row_number}",
        registration_no=registration_no,
        title_description=title,
        raw_data=raw_data,
        **fields,
    )
    session.add(record)
    session.flush()
    return record


def add_issue(
    session: Session, source: DataSource, record: Record | None = None, severity: str = "warning",
) -> DataQualityIssue:
    issue = DataQualityIssue(
        source_id=source.id,
        record_id=record.id if record else None,
        severity=severity,
        code="missing_registration",
        message="ไม่พบเลขทะเบียน",
    )
    session.add(issue)
    session.flush()
    return issue
