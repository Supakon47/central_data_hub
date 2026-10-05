"""Read-only Google Sheets connector boundary for the next milestone.

This module deliberately does not accept spreadsheet IDs or credentials from web requests.
Sources must be approved in the Data Catalog before a scheduled worker can call it.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class GoogleSheetSource:
    spreadsheet_id: str
    sheet_name: str
    read_range: str


def fetch_values(_: GoogleSheetSource) -> list[list[object]]:
    raise NotImplementedError(
        "Google Sheets sync is disabled until service-account credentials, approved source IDs, "
        "and a scheduled-worker configuration are available. The connector must remain read-only."
    )
