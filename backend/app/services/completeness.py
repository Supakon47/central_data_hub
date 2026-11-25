"""How complete each source and sheet is: which fields are filled, and how often.

Used to see what is missing from the source workbooks and to ask data owners
for exactly that; nothing here changes any data.
"""

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..models import DataSource, Record, SourceSheetConfig
from .filters import is_filled
from .locations import location_index

COUNTED_FIELDS = {
    "registration": Record.registration_no,
    "title": Record.title_description,
    "material": Record.material,
    "period": Record.period,
    "dimensions": Record.dimensions_text,
    "image": Record.image_url,
}


def _filled(column):
    return func.sum(case((is_filled(column), 1), else_=0))


def _empty_counts() -> dict:
    return {"rows": 0, "matching_key": 0, "location": 0, **{name: 0 for name in COUNTED_FIELDS}}


def _add(total: dict, part: dict) -> None:
    for name, value in part.items():
        total[name] += value


def data_completeness(session: Session) -> dict:
    statement = (
        select(Record.source_id, Record.source_sheet, func.count(Record.id),
               *(_filled(column) for column in COUNTED_FIELDS.values()))
        .group_by(Record.source_id, Record.source_sheet)
    )
    sheets: dict[tuple[int, str], dict] = {}
    for source_id, sheet, rows, *filled in session.execute(statement):
        counts = _empty_counts()
        counts["rows"] = rows
        counts.update({name: int(value or 0) for name, value in zip(COUNTED_FIELDS, filled, strict=True)})
        sheets[(source_id, sheet)] = counts

    for row in location_index(session).rows:
        counts = sheets.get((row.source_id, row.source_sheet))
        if counts is None:
            continue
        counts["matching_key"] += bool(row.key)
        counts["location"] += bool(row.location)

    names = dict(session.execute(select(DataSource.id, DataSource.name)).all())
    roles = {
        (source_id, sheet): role
        for source_id, sheet, role in session.execute(
            select(SourceSheetConfig.source_id, SourceSheetConfig.sheet_name, SourceSheetConfig.role)
        )
    }
    sources: dict[int, dict] = {}
    for (source_id, sheet), counts in sorted(sheets.items(), key=lambda item: item[0][1]):
        source = sources.setdefault(source_id, {
            "source_id": source_id, "source_name": names.get(source_id), "totals": _empty_counts(), "sheets": [],
        })
        _add(source["totals"], counts)
        source["sheets"].append({"sheet": sheet, "role": roles.get((source_id, sheet)), **counts})
    return {
        "fields": ["registration", "matching_key", "title", "material", "period", "dimensions", "location", "image"],
        "sources": sorted(sources.values(), key=lambda item: item["source_name"] or ""),
    }
