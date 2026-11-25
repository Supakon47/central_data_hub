"""Reviewing links between object records and storage-location records."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from ..dependencies import AdminDep, SessionDep
from ..models import LocationMatchReview, Record
from ..normalization import clean_multiline_text, normalise_registration_no
from ..schemas import LocationMatchReviewMutation
from ..services import locations
from ..services.audit import add_audit

router = APIRouter(tags=["location matching"])


@router.get("/api/location-match-candidates")
def list_location_match_candidates(
    session: SessionDep,
    source_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    """Find reviewable links; this endpoint never creates a relationship."""
    return locations.match_candidates(session, source_id, limit)


@router.get("/api/location-match-report")
def location_match_report(session: SessionDep) -> dict:
    """Summarise how storage-location rows match object rows; read-only."""
    return locations.match_report(session)


@router.get("/api/location-conflicts")
def list_location_conflicts(session: SessionDep, limit: int = Query(default=100, ge=1, le=500)) -> dict:
    """Registration numbers recorded at more than one different storage location."""
    return locations.location_conflicts(session, limit)


@router.get("/api/location-match-reviews")
def list_location_match_reviews(session: SessionDep, limit: int = Query(default=200, ge=1, le=1000)) -> dict:
    """Staff decisions already recorded, newest first."""
    return locations.recorded_reviews(session, limit)


@router.post("/api/admin/location-match-reviews")
def review_location_match(payload: LocationMatchReviewMutation, session: SessionDep, _: AdminDep) -> dict:
    """Approve or reject one proposed relationship without merging source rows."""
    object_record = session.get(Record, payload.object_record_id)
    location_record = session.get(Record, payload.location_record_id)
    if object_record is None or location_record is None:
        raise HTTPException(status_code=404, detail="ไม่พบระเบียนที่ใช้ตรวจการจับคู่")
    object_key = normalise_registration_no(object_record.registration_no)
    location_key = normalise_registration_no(location_record.registration_no)
    if not object_key or object_key != location_key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="เลขทะเบียนของสองระเบียนไม่ตรงกัน จึงไม่สามารถบันทึกผลการตรวจได้",
        )
    if locations.record_location(location_record) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="ระเบียนที่เลือกไม่มีข้อมูลตำแหน่งจากต้นทาง",
        )

    review = session.scalar(select(LocationMatchReview).where(
        LocationMatchReview.object_record_id == object_record.id,
        LocationMatchReview.location_record_id == location_record.id,
    ))
    before = None
    if review is None:
        review = LocationMatchReview(object_record_id=object_record.id, location_record_id=location_record.id)
        session.add(review)
        session.flush()
    else:
        before = {"decision": review.decision, "note": review.note}
    review.decision = payload.decision
    review.note = clean_multiline_text(payload.note)
    review.reviewed_at = datetime.now()
    session.flush()
    after = {
        "decision": review.decision,
        "note": review.note,
        "object_record_id": object_record.id,
        "location_record_id": location_record.id,
        "registration_no": object_record.registration_no,
    }
    add_audit(session, "review_location_match", review.id, before, after, entity_type="location_match_review")
    session.commit()
    return locations.location_review_summary(review, object_record, location_record)


@router.delete("/api/admin/location-match-reviews/{review_id}")
def undo_location_match_review(review_id: int, session: SessionDep, _: AdminDep) -> dict:
    """Withdraw a recorded decision so the pair returns to the review queue.

    Only the review row is removed; both source records stay untouched and the
    withdrawn decision is kept in the audit log.
    """
    review = session.get(LocationMatchReview, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="ไม่พบผลตรวจการเชื่อมตำแหน่งนี้")
    before = {
        "decision": review.decision,
        "note": review.note,
        "object_record_id": review.object_record_id,
        "location_record_id": review.location_record_id,
        "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
    }
    session.delete(review)
    add_audit(session, "undo_location_match", review_id, before, None, entity_type="location_match_review")
    session.commit()
    return {"id": review_id, "message": "ยกเลิกผลตรวจแล้ว คู่นี้กลับไปอยู่ในรายการรอตรวจ"}
