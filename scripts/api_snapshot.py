"""Record or compare the responses of the read-only API, for safe refactoring.

Usage (with the app running on http://localhost:8000):

    python scripts/api_snapshot.py record  <directory>
    python scripts/api_snapshot.py compare <directory>

``record`` saves every response; ``compare`` fetches again and lists every
case whose status code or body changed. Only GET requests are sent, so the
database is never modified. Cases are built from live data (sheet names,
record IDs), so record and compare must run against the same data.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_URL = "http://localhost:8000"


def fetch(path: str) -> tuple[int, object]:
    try:
        with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=60) as response:
            status, body = response.status, response.read()
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as error:
        status, body = error.code, error.read()
        content_type = error.headers.get("Content-Type", "")
    text = body.decode("utf-8")
    return status, json.loads(text) if "json" in content_type else text


def query(path: str, **params: object) -> str:
    return f"{path}?{urllib.parse.urlencode(params)}" if params else path


def build_cases() -> dict[str, str]:
    _, dashboard = fetch("/api/dashboard")
    _, catalog = fetch("/api/catalog")
    _, records = fetch(query("/api/records", page_size=5))
    _, candidates = fetch(query("/api/location-match-candidates", limit=2))
    _, metal = fetch(query("/api/records", material_group="metal", page_size=1))
    _, ayutthaya = fetch(query("/api/records", period_group="ayutthaya", page_size=1))
    sheet = dashboard["by_source_sheet"][0]["label"]
    material = metal["items"][0]["material"]
    period = ayutthaya["items"][0]["period"]
    source_ids = [source["id"] for source in catalog["sources"]]
    record_ids = [item["id"] for item in records["items"]]
    for pair in candidates["items"]:
        record_ids += [pair["object_record"]["id"], pair["location_record"]["id"]]

    cases = {
        "home": "/",
        "health": "/api/health",
        "admin_session": "/api/admin/session",
        "admin_audit_unauthenticated": "/api/admin/audit",
        "catalog": "/api/catalog",
        "dashboard": "/api/dashboard",
        "dashboard_sheet": query("/api/dashboard", source_sheet=sheet),
        "filter_options": "/api/filter-options",
        "duplicates": "/api/duplicates",
        "duplicates_sheet": query("/api/duplicates", source_sheet=sheet, limit=5),
        "records": "/api/records",
        "records_page2_source_sort": query("/api/records", page=2, page_size=10, sort_by="source"),
        "records_q": query("/api/records", q="พระ"),
        "records_material_group": query("/api/records", material_group="metal"),
        "records_material_none": query("/api/records", material_group="none"),
        "records_material_other": query("/api/records", material_group="other"),
        "records_period_group": query("/api/records", period_group="ayutthaya"),
        "records_material_exact": query("/api/records", material=material),
        "records_period_exact": query("/api/records", period=period),
        "records_attention": query("/api/records", attention="photographed"),
        "records_unspecified_status": query("/api/records", status_storage="ไม่ระบุ"),
        "records_has_image": query("/api/records", has_image="true"),
        "records_no_description": query("/api/records", has_description="false"),
        "records_year": query("/api/records", registration_year="2564"),
        "records_sheet": query("/api/records", source_sheet=sheet),
        "records_bad_group": query("/api/records", material_group="nope"),
        "records_bad_year": query("/api/records", registration_year="64"),
        "record_missing": "/api/records/999999999",
        "location_candidates": "/api/location-match-candidates",
        "location_candidates_all": query("/api/location-match-candidates", limit=500),
        "location_report": "/api/location-match-report",
        "location_reviews": "/api/location-match-reviews",
        "quality_issues": "/api/data-quality/issues",
        "quality_issues_resolved": query("/api/data-quality/issues", include_resolved="true", page_size=100),
        "quality_issues_warning": query("/api/data-quality/issues", severity="warning"),
    }
    for source_id in source_ids:
        cases[f"dashboard_source_{source_id}"] = query("/api/dashboard", source_id=source_id)
        cases[f"records_source_{source_id}"] = query("/api/records", source_id=source_id)
        cases[f"location_candidates_source_{source_id}"] = query("/api/location-match-candidates", source_id=source_id)
        cases[f"quality_issues_source_{source_id}"] = query("/api/data-quality/issues", source_id=source_id)
    for record_id in dict.fromkeys(record_ids):
        cases[f"record_{record_id}"] = f"/api/records/{record_id}"
    return cases


def record(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    cases = build_cases()
    (directory / "_cases.json").write_text(json.dumps(cases, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, path in cases.items():
        status, body = fetch(path)
        snapshot = {"path": path, "status": status, "body": body}
        (directory / f"{name}.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"recorded {len(cases)} cases in {directory}")


def compare(directory: Path) -> int:
    cases = json.loads((directory / "_cases.json").read_text(encoding="utf-8"))
    changed = []
    for name, path in cases.items():
        expected = json.loads((directory / f"{name}.json").read_text(encoding="utf-8"))
        status, body = fetch(path)
        if status != expected["status"] or body != expected["body"]:
            changed.append(f"{name}: {path} (status {expected['status']} -> {status})")
    print(f"compared {len(cases)} cases, {len(changed)} changed")
    for line in changed:
        print(f"  CHANGED {line}")
    return 1 if changed else 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 3 or sys.argv[1] not in {"record", "compare"}:
        print(__doc__)
        return 2
    directory = Path(sys.argv[2])
    if sys.argv[1] == "record":
        record(directory)
        return 0
    return compare(directory)


if __name__ == "__main__":
    raise SystemExit(main())
