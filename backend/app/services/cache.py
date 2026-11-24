"""Reuse whole-table computations until the underlying data changes."""

from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import DataSource, Record

_RESULT_CACHE: dict[str, tuple[tuple, object]] = {}


def records_version(session: Session) -> tuple:
    """A cheap fingerprint that changes whenever records or sources change."""
    records = session.execute(
        select(func.count(Record.id), func.max(Record.id), func.max(Record.updated_at))
    ).one()
    sources = session.execute(select(func.count(DataSource.id), func.max(DataSource.updated_at))).one()
    return (*records, *sources)


def cached_for_records[T](session: Session, name: str, compute: Callable[[], T]) -> T:
    """Return the cached result of ``compute`` while no record or source has changed.

    Callers must treat the returned value as read-only, since it is shared.
    """
    version = records_version(session)
    hit = _RESULT_CACHE.get(name)
    if hit is not None and hit[0] == version:
        return hit[1]  # type: ignore[return-value]
    value = compute()
    _RESULT_CACHE[name] = (version, value)
    return value
