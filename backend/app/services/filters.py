"""Record search filters and the curated material/period groups behind them.

Source values are never altered: spelling variants are only tolerated while
matching and displaying.
"""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import Select, and_, func, not_, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from ..models import Record

UNSPECIFIED = "ไม่ระบุ"
# Status a record must reach to leave each follow-up list.
ATTENTION_STATUS_FIELDS = {
    "data_check": (Record.status_data_check, "ตรวจสอบแล้ว"),
    "photographed": (Record.status_photographed, "ถ่ายภาพแล้ว"),
    "antique": (Record.status_antique, "ลงระบบแล้ว"),
    "storage": (Record.status_storage, "ส่งขึ้นห้องคลังแล้ว"),
}

MATERIAL_DISPLAY_ALIASES = {
    "หิo": "หิน",
    "หิิน": "หิน",
    "เหล็็ก": "เหล็ก",
    "สำริิด": "สำริด",
    "สําริด": "สำริด",
    "ดิินเผา": "ดินเผา",
    "ดิีบุก โลหะ": "ดีบุก โลหะ",
    "โลหะ ไม้้": "โลหะไม้",
    "ดินเผา เคลือบ": "ดินเผาเคลือบ",
    "โลหะ ไม้": "โลหะไม้",
    "เหล็ก ไม้": "เหล็กไม้",
    "ปูน ปลาสเตอร์": "ปูนปลาสเตอร์",
    "หิน ทรายแดง": "หินทรายแดง",
    "หินทราย แดง": "หินทรายแดง",
    "ทอง เหลือง": "ทองเหลือง",
    "โลหะ งา": "โลหะงา",
}

PERIOD_DISPLAY_ALIASES = {
    "ก่อน ประวัติ ศาสตร์": "ก่อนประวัติศาสตร์",
    "ก่อน ประวัติศาสตร์": "ก่อนประวัติศาสตร์",
    "ก่อนประวัติ ศาสตร์": "ก่อนประวัติศาสตร์",
    "รัตน โกสินทร์": "รัตนโกสินทร์",
    "พุทธศตวรรษ ที่": "พุทธศตวรรษที่",
    "เขมร ในประเทศไทย": "เขมรในประเทศไทย",
    "เลียนแบบ ศิลปะเขมรในประเทศไทย": "เลียนแบบศิลปะเขมรในประเทศไทย",
    "พุทธศตรรษที่": "พุทธศตวรรษที่",
    "พุทธศตวรษที่": "พุทธศตวรรษที่",
    "พุทธศตววรษที่": "พุทธศตวรรษที่",
    "พุทธสตวรรษที่": "พุทธศตวรรษที่",
    "ล้านา": "ล้านนา",
}

# These groups are deliberately short, curated choices for discovery.  The
# source values remain untouched; a group can therefore include several
# spellings or composite materials without creating an overwhelming dropdown.
MATERIAL_FILTER_GROUPS = (
    ("metal", "โลหะ (ทุกชนิด)", ("โลหะ", "สำริด", "เงิน", "ทอง", "เหล็ก", "ตะกั่ว", "นิเกิล", "ดีบุก", "ทองเหลือง", "ทองแดง")),
    ("bronze", "สำริด", ("สำริด",)),
    ("silver", "เงิน", ("เงิน",)),
    ("gold", "ทอง/ทองคำ", ("ทองคำ", "ทอง ")),
    ("copper", "ทองแดง", ("ทองแดง",)),
    ("brass", "ทองเหลือง", ("ทองเหลือง",)),
    ("iron", "เหล็ก", ("เหล็ก",)),
    ("lead-tin", "ตะกั่ว/ดีบุก", ("ตะกั่ว", "ดีบุก")),
    ("terracotta", "ดินเผา", ("ดินเผา",)),
    ("ceramic", "เครื่องเคลือบ/กระเบื้อง", ("เคลือบ", "กระเบื้อง", "พอร์ซเลน", "เซรามิก")),
    ("stone", "หิน (ทุกชนิด)", ("หิน",)),
    ("wood", "ไม้", ("ไม้",)),
    ("textile", "ผ้า/สิ่งทอ", ("ผ้า", "ไหม", "ด้าย")),
    ("plaster", "ปูน", ("ปูน",)),
    ("glass", "แก้ว/กระจก", ("แก้ว", "กระจก")),
    ("paper", "กระดาษ", ("กระดาษ",)),
    ("leather", "หนัง", ("หนัง",)),
    ("organic", "งา/กระดูก/เขา/เปลือกหอย", ("งา", "กระดูก", "เขา", "เปลือกหอย", "อินทรีย์")),
    ("lacquer", "รัก/ลงรักปิดทอง", ("รัก",)),
    ("modern", "พลาสติก/วัสดุสมัยใหม่", ("พลาสติก", "เรซิน")),
)

PERIOD_FILTER_GROUPS = (
    ("prehistory", "ก่อนประวัติศาสตร์", ("ก่อนประวัติ",)),
    ("dvaravati", "ทวารวดี", ("ทวารวดี",)),
    ("srivijaya", "ศรีวิชัย", ("ศรีวิชัย",)),
    ("lopburi", "ลพบุรี", ("ลพบุรี",)),
    ("sukhothai", "สุโขทัย", ("สุโขทัย",)),
    ("lanna", "ล้านนา", ("ล้านนา",)),
    ("ayutthaya", "อยุธยา", ("อยุธยา",)),
    ("thonburi", "ธนบุรี", ("ธนบุรี",)),
    ("rattanakosin", "รัตนโกสินทร์", ("รัตนโกสินทร์",)),
    ("china", "จีน", ("จีน",)),
    ("japan", "ญี่ปุ่น", ("ญี่ปุ่น",)),
    ("foreign", "ต่างประเทศ", ("ต่างประเทศ",)),
)

# Thai vowel and tone marks that some sources type twice in a row.
REPEATED_THAI_MARK = r"([ิีึืุู็่้๊๋ั])\1+"
# Characters dropped before an exact material or period comparison, in order.
COMPACT_REMOVED_CHARACTERS = (" ", "\n", "\r", "\t", "​", "﻿", " ")
# Common material misspellings corrected before an exact comparison, in order.
COMPACT_MATERIAL_FIXES = (("หิo", "หิน"), ("เหล็็ก", "เหล็ก"), ("หิิน", "หิน"))
SOURCE_YEAR = re.compile(r"/(\d{4})(?:\D|$)")


@dataclass(frozen=True)
class RecordFilters:
    """Every way the Explorer can narrow the record list."""

    q: str | None = None
    source_id: int | None = None
    source_sheet: str | None = None
    material: str | None = None
    period: str | None = None
    material_group: str | None = None
    period_group: str | None = None
    status_data_check: str | None = None
    status_photographed: str | None = None
    status_antique: str | None = None
    status_storage: str | None = None
    registration_year: str | None = None
    attention: str | None = None
    has_description: bool | None = None
    has_image: bool | None = None


def normalise_filter_display(value: str, aliases: dict[str, str]) -> str:
    """Clean values only for matching and display; never alter source data."""
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("​", "").replace("﻿", "").replace(" ", " ")
    value = re.sub(REPEATED_THAI_MARK, r"\1", value)
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\s*-\s*", " - ", value)
    for variant, replacement in aliases.items():
        value = value.replace(variant, replacement)
    return value


def group_matches(value: str, terms: tuple[str, ...]) -> bool:
    comparable = f"{value.casefold()} "
    return any(term.casefold() in comparable for term in terms)


def group_option_items(session: Session, column, groups, aliases, empty_label: str) -> list[dict]:
    """Return concise discovery groups with counts, instead of every raw value."""
    counts: Counter[str] = Counter()
    for raw_value in session.scalars(select(column)).all():
        if not raw_value or not raw_value.strip():
            counts["none"] += 1
            continue
        value = normalise_filter_display(raw_value, aliases)
        matched = False
        for group_value, _, terms in groups:
            if group_matches(value, terms):
                counts[group_value] += 1
                matched = True
        if not matched:
            counts["other"] += 1

    items = []
    if counts["none"]:
        items.append({"value": "none", "label": empty_label, "count": counts["none"]})
    items.extend(
        {"value": value, "label": label, "count": counts[value]}
        for value, label, _ in groups
        if counts[value]
    )
    if counts["other"]:
        items.append({"value": "other", "label": "อื่น ๆ", "count": counts["other"]})
    return items


def group_filter_condition(column, group_value: str, groups, aliases: dict[str, str]):
    """Build a tolerant database predicate for one curated filter group."""
    group_by_value = {value: terms for value, _, terms in groups}
    if group_value == "none":
        return or_(column.is_(None), column == "")

    all_terms = tuple(term for _, _, terms in groups for term in terms)
    if group_value == "other":
        patterns = [column.ilike(f"%{term}%") for term in all_terms]
        return and_(column.is_not(None), column != "", not_(or_(*patterns)))

    terms = group_by_value.get(group_value)
    if terms is None:
        raise HTTPException(status_code=422, detail="กลุ่มตัวกรองไม่ถูกต้อง")
    tolerant_terms = list(terms)
    for variant, replacement in aliases.items():
        if any(term in replacement for term in terms):
            tolerant_terms.append(variant)
    return or_(*(column.ilike(f"%{term}%") for term in tolerant_terms))


def compact_value_condition(column: InstrumentedAttribute, value: str):
    """Match a material or period exactly, ignoring spacing and doubled Thai marks."""
    compact_column = column
    for character in COMPACT_REMOVED_CHARACTERS:
        compact_column = func.replace(compact_column, character, "")
    if column.key == "material":
        for variant, replacement in COMPACT_MATERIAL_FIXES:
            compact_column = func.replace(compact_column, variant, replacement)
    compact_column = func.regexp_replace(compact_column, REPEATED_THAI_MARK, r"\1", "g")
    compact_value = re.sub(REPEATED_THAI_MARK, r"\1", re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)))
    return compact_column == compact_value


def is_blank(column):
    return or_(column.is_(None), column == "")


def is_filled(column):
    return and_(column.is_not(None), column != "")


def apply_record_filters(statement: Select, filters: RecordFilters) -> Select:
    """Narrow a record query by every filter that was supplied."""
    if filters.q:
        pattern = f"%{filters.q.strip()}%"
        statement = statement.where(or_(
            Record.registration_no.ilike(pattern),
            Record.previous_registration_no.ilike(pattern),
            Record.title_description.ilike(pattern),
            Record.material.ilike(pattern),
            Record.period.ilike(pattern),
            Record.provenance.ilike(pattern),
        ))
    for column, value in [
        (Record.source_id, filters.source_id),
        (Record.source_sheet, filters.source_sheet),
        (Record.status_data_check, filters.status_data_check),
        (Record.status_photographed, filters.status_photographed),
        (Record.status_antique, filters.status_antique),
        (Record.status_storage, filters.status_storage),
    ]:
        if value == UNSPECIFIED:
            statement = statement.where(is_blank(column))
        elif value is not None:
            statement = statement.where(column == value)
    if filters.material_group:
        statement = statement.where(group_filter_condition(
            Record.material, filters.material_group, MATERIAL_FILTER_GROUPS, MATERIAL_DISPLAY_ALIASES,
        ))
    if filters.period_group:
        statement = statement.where(group_filter_condition(
            Record.period, filters.period_group, PERIOD_FILTER_GROUPS, PERIOD_DISPLAY_ALIASES,
        ))
    for column, value in [(Record.material, filters.material), (Record.period, filters.period)]:
        if value is not None:
            statement = statement.where(compact_value_condition(column, value))
    if filters.attention:
        status_field, completed_status = ATTENTION_STATUS_FIELDS[filters.attention]
        statement = statement.where(or_(status_field.is_(None), status_field != completed_status))
    if filters.has_description is not None:
        check = is_filled if filters.has_description else is_blank
        statement = statement.where(check(Record.title_description))
    if filters.has_image is not None:
        check = is_filled if filters.has_image else is_blank
        statement = statement.where(check(Record.image_url))
    if filters.registration_year:
        statement = statement.where(Record.registration_no.ilike(f"%/{filters.registration_year}%"))
    return statement


def filter_options(session: Session) -> dict:
    """Choices and counts for the Explorer's grouped filters."""
    registration_year_counts: Counter[str] = Counter()
    current_buddhist_year = datetime.now().year + 543
    registration_numbers = session.scalars(select(Record.registration_no).where(is_filled(Record.registration_no)))
    for registration_no in registration_numbers:
        match = SOURCE_YEAR.search(registration_no or "")
        if match and 2400 <= int(match.group(1)) <= current_buddhist_year:
            registration_year_counts[match.group(1)] += 1

    return {
        "material_groups": group_option_items(
            session, Record.material, MATERIAL_FILTER_GROUPS, MATERIAL_DISPLAY_ALIASES, "ไม่ระบุชนิด",
        ),
        "period_groups": group_option_items(
            session, Record.period, PERIOD_FILTER_GROUPS, PERIOD_DISPLAY_ALIASES, "ไม่ระบุ",
        ),
        "registration_years": [
            {"label": year, "count": count}
            for year, count in sorted(registration_year_counts.items(), reverse=True)
        ],
    }
