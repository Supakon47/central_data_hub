"""Proposing, reporting and recording links between objects and storage locations.

A *storage source* is any source with at least one row that has a location
(shelf) value; every row of such a source is a storage row, and every row of
any other source is an object row. Rows are linked only when their normalised
registration numbers match, and only staff decisions turn a proposal into a
link. Source rows are never merged or edited.
"""

import re
import unicodedata
from collections import Counter
from typing import NamedTuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..models import DataSource, LocationMatchReview, Record
from ..normalization import clean_multiline_text, clean_text, normalise_header, normalise_registration_no
from .cache import cached_for_records
from .records import record_summary

LOCATION_FIELD_ALIASES = ("สถานที่เก็บ", "ที่เก็บ", "ชั้นวาง", "ชั้น")
REGISTRATION_YEAR = re.compile(r"(?<!\d)(2[45]\d\d)(?!\d)")
# The first Buddhist-era year covered by the central register (บัญชีเดินทุ่ง).
REGISTER_START_YEAR = 2564


def location_from_raw(raw_data: dict | None) -> dict | None:
    """The first non-empty location column in a source row, with its header."""
    for key, value in (raw_data or {}).items():
        if normalise_header(key) not in LOCATION_FIELD_ALIASES:
            continue
        location = clean_multiline_text(value)
        if location:
            return {"field": key, "value": location}
    return None


def record_location(record: Record) -> dict | None:
    """Return a location value stored in source raw data, with its header.

    Location is intentionally read from the source payload rather than copied
    onto the object record. This preserves the source evidence and supports
    several observations for one registration number.
    """
    return location_from_raw(record.raw_data)


def titles_conflict(object_title: str | None, location_title: str | None) -> bool:
    """Flag clearly different titles as a review aid, never as a rejection."""
    object_title = clean_text(object_title)
    location_title = clean_text(location_title)
    if not object_title or not location_title:
        return False
    left = re.sub(r"\s+", "", unicodedata.normalize("NFKC", object_title)).casefold()
    right = re.sub(r"\s+", "", unicodedata.normalize("NFKC", location_title)).casefold()
    return left not in right and right not in left


def registration_year_bucket(registration_no: str | None) -> str:
    """Group a registration by the Buddhist-era year it carries, if any."""
    years = REGISTRATION_YEAR.findall(registration_no or "")
    if not years:
        return "no_year"
    return "since_register" if int(years[-1]) >= REGISTER_START_YEAR else "before_register"


class LocationIndexRow(NamedTuple):
    id: int
    source_id: int
    registration_no: str | None
    title_description: str | None
    location: dict | None
    key: str | None


class LocationIndex(NamedTuple):
    rows: list[LocationIndexRow]
    storage_sources: frozenset[int]
    groups: dict[str, list[LocationIndexRow]]


def location_index(session: Session) -> LocationIndex:
    """Registration keys and storage locations for every record, cached.

    Reading every raw_data payload is the slow part of location matching, so it
    is done once per data version and shared by the review queue and the report.
    """
    def build() -> LocationIndex:
        rows = [
            LocationIndexRow(
                row.id, row.source_id, row.registration_no, row.title_description,
                location_from_raw(row.raw_data), normalise_registration_no(row.registration_no),
            )
            for row in session.execute(select(
                Record.id, Record.source_id, Record.registration_no, Record.title_description, Record.raw_data,
            ))
        ]
        storage_sources = frozenset(row.source_id for row in rows if row.location)
        groups: dict[str, list[LocationIndexRow]] = {}
        for row in rows:
            if row.key:
                groups.setdefault(row.key, []).append(row)
        return LocationIndex(rows, storage_sources, groups)

    return cached_for_records(session, "location_index", build)


def location_review_summary(review: LocationMatchReview, object_record: Record, location_record: Record) -> dict:
    return {
        "id": review.id,
        "decision": review.decision,
        "note": review.note,
        "reviewed_at": review.reviewed_at,
        "object_record": record_summary(object_record),
        "location_record": {
            **record_summary(location_record),
            "location": record_location(location_record),
        },
    }


def match_candidates(session: Session, source_id: int | None, limit: int) -> dict:
    """Pairs with matching registration numbers that no one has reviewed yet."""
    index = location_index(session)
    reviewed_pairs = set(session.execute(
        select(LocationMatchReview.object_record_id, LocationMatchReview.location_record_id)
    ).tuples())
    pairs = []
    for registration_no, group in sorted(index.groups.items()):
        candidates = [row for row in group if row.source_id == source_id] if source_id else group
        location_rows = [row for row in candidates if row.source_id in index.storage_sources and row.location]
        if not location_rows:
            continue
        # A storage-list row with a blank shelf is still a storage row, never an object row.
        object_rows = [row for row in candidates if row.source_id not in index.storage_sources]
        for object_row in object_rows:
            for location_row in location_rows:
                if (object_row.id, location_row.id) not in reviewed_pairs:
                    pairs.append((registration_no, object_row, location_row))

    shown = pairs[:limit]
    record_ids = {row.id for _, object_row, location_row in shown for row in (object_row, location_row)}
    records = {
        record.id: record
        for record in session.scalars(
            select(Record).where(Record.id.in_(record_ids)).options(selectinload(Record.source))
        )
    } if record_ids else {}
    items = [
        {
            "registration_no": registration_no,
            "object_record": record_summary(records[object_row.id]),
            "location_record": {**record_summary(records[location_row.id]), "location": location_row.location},
            "title_conflict": titles_conflict(object_row.title_description, location_row.title_description),
            "requires_review": True,
        }
        for registration_no, object_row, location_row in shown
    ]
    return {
        "total": len(pairs),
        "items": items,
        "message": "รายการนี้เป็นเพียงข้อเสนอการจับคู่ ยังไม่เปลี่ยนข้อมูลตำแหน่งของวัตถุ",
    }


def _empty_source_summary(source_id: int, source_name: str | None) -> dict:
    return {
        "source_id": source_id,
        "source_name": source_name,
        "rows": 0, "missing_location": 0,
        "missing_registration": 0, "placeholder_registration": 0, "with_key": 0,
        "matched": 0, "unmatched": 0,
        "unmatched_by_year": {"before_register": 0, "since_register": 0, "no_year": 0},
        "duplicate_keys": 0, "duplicate_rows": 0,
        "pairs": 0, "title_conflict_pairs": 0, "approved": 0, "rejected": 0, "pending": 0,
    }


def match_report(session: Session) -> dict:
    """Summarise how storage rows match object rows, per storage source.

    A storage row counts as "matched" when its normalised registration number
    also appears on at least one object row. It is a measure of what *could* be
    linked, not of what staff have approved.
    """
    source_names = dict(session.execute(select(DataSource.id, DataSource.name)).all())
    index = location_index(session)

    object_rows_by_key: dict[str, list[LocationIndexRow]] = {}
    storage_rows = []
    object_total = 0
    for row in index.rows:
        if row.source_id in index.storage_sources:
            storage_rows.append(row)
            continue
        object_total += 1
        if row.key:
            object_rows_by_key.setdefault(row.key, []).append(row)

    decisions = {
        (object_id, location_id): decision
        for object_id, location_id, decision in session.execute(select(
            LocationMatchReview.object_record_id, LocationMatchReview.location_record_id, LocationMatchReview.decision,
        ))
    }

    sources: dict[int, dict] = {}
    keys_by_source: dict[int, Counter] = {}
    matched_object_keys: set[str] = set()
    for row in storage_rows:
        summary = sources.get(row.source_id)
        if summary is None:
            summary = sources[row.source_id] = _empty_source_summary(row.source_id, source_names.get(row.source_id))
        summary["rows"] += 1
        if not row.location:
            summary["missing_location"] += 1
        if not clean_text(row.registration_no):
            summary["missing_registration"] += 1
            continue
        if not row.key:
            summary["placeholder_registration"] += 1
            continue
        summary["with_key"] += 1
        keys_by_source.setdefault(row.source_id, Counter())[row.key] += 1
        objects = object_rows_by_key.get(row.key)
        if not objects:
            summary["unmatched"] += 1
            summary["unmatched_by_year"][registration_year_bucket(row.key)] += 1
            continue
        summary["matched"] += 1
        if not row.location:
            # Registered object, but this row has no shelf to propose.
            continue
        matched_object_keys.add(row.key)
        for object_row in objects:
            summary["pairs"] += 1
            if titles_conflict(object_row.title_description, row.title_description):
                summary["title_conflict_pairs"] += 1
            summary[decisions.get((object_row.id, row.id), "pending")] += 1

    for source_id, counter in keys_by_source.items():
        duplicates = [count for count in counter.values() if count > 1]
        sources[source_id]["duplicate_keys"] = len(duplicates)
        sources[source_id]["duplicate_rows"] = sum(duplicates)

    return {
        "register_start_year": REGISTER_START_YEAR,
        "object_records": {
            "rows": object_total,
            "distinct_keys": len(object_rows_by_key),
            "keys_with_location": len(matched_object_keys),
        },
        "location_sources": sorted(sources.values(), key=lambda item: item["source_name"] or ""),
        "message": "รายงานนี้นับจากเลขทะเบียนที่ตรงกันเท่านั้น ไม่ใช่ผลยืนยันว่าเป็นวัตถุชิ้นเดียวกัน",
    }


def recorded_reviews(session: Session, limit: int) -> dict:
    """Staff decisions already recorded, newest first."""
    reviews = session.scalars(
        select(LocationMatchReview).order_by(LocationMatchReview.reviewed_at.desc()).limit(limit)
    ).all()
    items = []
    for review in reviews:
        object_record = session.get(Record, review.object_record_id)
        location_record = session.get(Record, review.location_record_id)
        if object_record and location_record:
            items.append(location_review_summary(review, object_record, location_record))
    total = session.scalar(select(func.count()).select_from(LocationMatchReview)) or 0
    return {"total": total, "items": items}


def approved_locations(session: Session, record: Record) -> list[dict]:
    """Storage locations staff approved for this record, from either side of the link."""
    reviews = session.scalars(
        select(LocationMatchReview).where(
            LocationMatchReview.decision == "approved",
            or_(
                LocationMatchReview.object_record_id == record.id,
                LocationMatchReview.location_record_id == record.id,
            ),
        )
    ).all()
    locations = []
    for review in reviews:
        location_record = session.get(Record, review.location_record_id)
        if location_record is None:
            continue
        locations.append({
            "review_id": review.id,
            "note": review.note,
            "reviewed_at": review.reviewed_at,
            "location": record_location(location_record),
            "source": record_summary(location_record),
        })
    return locations
