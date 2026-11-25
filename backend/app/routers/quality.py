"""Data-quality issues found during import or sync."""

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from ..dependencies import AdminDep, SessionDep
from ..models import DataQualityIssue, DataSource, Record
from ..schemas import DataQualityIssueResolution
from ..services import completeness
from ..services.audit import add_audit
from ..services.cache import cached_for_records

router = APIRouter(tags=["data quality"])


@router.get("/api/data-completeness")
def data_completeness(session: SessionDep) -> dict:
    """Filled-field counts per source and sheet, to see what the source files are missing."""
    return cached_for_records(session, "data_completeness", lambda: completeness.data_completeness(session))


@router.get("/api/data-quality/issues")
def list_data_quality_issues(
    session: SessionDep,
    source_id: int | None = None,
    severity: str | None = Query(default=None, pattern="^(warning|error)$"),
    include_resolved: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> dict:
    """Expose import/sync validation findings for staff review without changing sources."""
    conditions = []
    if source_id:
        conditions.append(DataQualityIssue.source_id == source_id)
    if severity:
        conditions.append(DataQualityIssue.severity == severity)
    if not include_resolved:
        conditions.append(DataQualityIssue.is_resolved.is_(False))

    total = session.scalar(select(func.count()).select_from(DataQualityIssue).where(*conditions)) or 0
    severity_counts = dict(session.execute(
        select(DataQualityIssue.severity, func.count(DataQualityIssue.id))
        .where(*conditions)
        .group_by(DataQualityIssue.severity)
    ).all())
    rows = session.execute(
        select(
            DataQualityIssue,
            DataSource.name.label("source_name"),
            Record.registration_no.label("registration_no"),
            Record.title_description.label("title_description"),
        )
        .join(DataSource, DataQualityIssue.source_id == DataSource.id)
        .outerjoin(Record, DataQualityIssue.record_id == Record.id)
        .where(*conditions)
        .order_by(DataQualityIssue.is_resolved, DataQualityIssue.created_at.desc(), DataQualityIssue.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "summary": {
            "errors": severity_counts.get("error", 0),
            "warnings": severity_counts.get("warning", 0),
        },
        "items": [{
            "id": issue.id,
            "source_id": issue.source_id,
            "source_name": source_name,
            "record_id": issue.record_id,
            "registration_no": registration_no,
            "title_description": title_description,
            "source_sheet": issue.source_sheet,
            "source_row_number": issue.source_row_number,
            "severity": issue.severity,
            "code": issue.code,
            "message": issue.message,
            "is_resolved": issue.is_resolved,
            "created_at": issue.created_at,
        } for issue, source_name, registration_no, title_description in rows],
    }


@router.patch("/api/admin/data-quality/issues/{issue_id}")
def resolve_data_quality_issue(
    issue_id: int,
    payload: DataQualityIssueResolution,
    session: SessionDep,
    _: AdminDep,
) -> dict:
    """Mark a finding reviewed; does not hide or modify the original source row."""
    issue = session.get(DataQualityIssue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="ไม่พบประเด็นคุณภาพข้อมูล")
    before = {"is_resolved": issue.is_resolved}
    issue.is_resolved = payload.is_resolved
    add_audit(
        session,
        "resolve_quality_issue" if payload.is_resolved else "reopen_quality_issue",
        issue.id,
        before,
        {"is_resolved": issue.is_resolved, "code": issue.code},
        entity_type="data_quality_issue",
    )
    session.commit()
    return {"id": issue.id, "is_resolved": issue.is_resolved}
