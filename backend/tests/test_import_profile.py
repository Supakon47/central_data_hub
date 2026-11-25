"""Import profiles: sheet roles, skipped sheets and rows, sheet locations, dry runs."""

import json

import openpyxl
import pytest
from sqlalchemy import func, select

from app.import_profile import ProfileError, load_profile, run_profile
from app.models import DataSource, Record, SourceSheetConfig


def build_workbook(path):
    """A storage-room workbook with the problems found in the real files."""
    workbook = openpyxl.Workbook()
    register = workbook.active
    register.title = "ทะเบียน"
    register.append(["เลขทะเบียน", "รายการ", "วัสดุ"])
    register.append(["99/1/2564", "พระพุทธรูป", "สำริด"])
    register.append(["99/2/2564", "ตะเกียง", "ดินเผา"])

    shelf = workbook.create_sheet("ชั้น A")
    shelf.append(["รายการวัตถุห้องทดลอง"])  # title row above the header
    shelf.append(["ลำดับ", "เลขทะเบียน", "ชื่อวัตถุ", "ชั้นวาง"])
    shelf.append([1, "99/1/2564", "พระพุทธรูปสำริด", "A-1"])
    shelf.append([2, "99/C0001-1 ไม่มีเลข 3", "เศษภาชนะ", "A-2"])  # real object, no registration
    shelf.append([3, None, None, None])  # running number only
    shelf.append([4, None, None, None])
    shelf.append([None, "จำนวนทั้งหมด", None, None])  # total row

    outside = workbook.create_sheet("นอกชั้น")
    outside.append(["ลำดับ", "เลขทะเบียน", "ชื่อวัตถุ"])
    outside.append([1, "99/2/2564", "ตะเกียง"])

    summary = workbook.create_sheet("สรุปยอด")
    summary.append(["จำนวนโบราณวัตถุ"])
    summary.append(["ชั้น", "จำนวน"])
    workbook.save(path)


def write_profile(path, **overrides):
    profile = {
        "source_name": "ห้องทดลอง",
        "file": "room.xlsx",
        "role": "location",
        "sheets": {
            "ทะเบียน": {"role": "register"},
            "ชั้น A": {"header_row": 2},
            "นอกชั้น": {"location": "นอกชั้น"},
            "สรุปยอด": {"skip": "ชีตสรุปยอด"},
        },
        **overrides,
    }
    path.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def rawdata(tmp_path):
    build_workbook(tmp_path / "room.xlsx")
    return tmp_path


def sheet_report(result, name):
    return next(item for item in result["sheets"] if item["sheet"] == name)


def test_dry_run_counts_everything_and_saves_nothing(rawdata, session):
    result = run_profile(load_profile(write_profile(rawdata / "p.json")), rawdata, dry_run=True)
    assert result["dry_run"] is True
    assert sheet_report(result, "ทะเบียน")["inserted"] == 2
    shelf = sheet_report(result, "ชั้น A")
    assert (shelf["inserted"], shelf["unidentified_rows"], shelf["summary_rows"]) == (2, 2, 1)
    assert sheet_report(result, "สรุปยอด") == {"sheet": "สรุปยอด", "status": "skipped", "reason": "ชีตสรุปยอด"}
    assert session.scalar(select(func.count()).select_from(Record)) == 0
    assert session.scalar(select(func.count()).select_from(DataSource)) == 0


def test_import_records_sheet_roles_and_skips_junk_rows(rawdata, session):
    run_profile(load_profile(write_profile(rawdata / "p.json")), rawdata, dry_run=False)
    rows = session.execute(select(Record.source_sheet, Record.registration_no, Record.source_row_number)).all()
    assert sorted(rows) == [
        ("ชั้น A", "99/1/2564", 3),
        ("ชั้น A", "99/C0001-1 ไม่มีเลข 3", 4),
        ("ทะเบียน", "99/1/2564", 2),
        ("ทะเบียน", "99/2/2564", 3),
        ("นอกชั้น", "99/2/2564", 2),
    ]
    roles = dict(session.execute(select(SourceSheetConfig.sheet_name, SourceSheetConfig.role)).all())
    assert roles == {"ทะเบียน": "register", "ชั้น A": "location", "นอกชั้น": "location", "สรุปยอด": None}


def test_importing_again_changes_nothing(rawdata, session):
    profile = load_profile(write_profile(rawdata / "p.json"))
    run_profile(profile, rawdata, dry_run=False)
    again = run_profile(profile, rawdata, dry_run=False)
    assert (again["inserted"], again["updated"], again["skipped"]) == (0, 0, 5)


def test_one_source_can_hold_both_register_and_location_sheets(rawdata, client):
    run_profile(load_profile(write_profile(rawdata / "p.json")), rawdata, dry_run=False)
    pairs = client.get("/api/location-match-candidates").json()["items"]
    by_number = {item["registration_no"]: item for item in pairs}
    assert set(by_number) == {"99/1/2564", "99/2/2564"}
    assert by_number["99/1/2564"]["object_record"]["source_sheet"] == "ทะเบียน"
    assert by_number["99/1/2564"]["location_record"]["location"]["value"] == "A-1"
    # The "นอกชั้น" sheet has no shelf column; the sheet name is the location.
    assert by_number["99/2/2564"]["location_record"]["location"] == {"field": "ชื่อชีต", "value": "นอกชั้น"}


def test_location_conflicts_are_reported(rawdata, client):
    run_profile(load_profile(write_profile(rawdata / "p.json")), rawdata, dry_run=False)
    other = openpyxl.Workbook()
    other.active.title = "ชั้น B"
    other.active.append(["เลขทะเบียน", "ชื่อวัตถุ", "ชั้นวาง"])
    other.active.append(["99/1/2564", "พระพุทธรูป", "B-9"])
    other.save(rawdata / "other.xlsx")
    second = write_profile(rawdata / "q.json", source_name="ห้องอื่น", file="other.xlsx", sheets={})
    run_profile(load_profile(second), rawdata, dry_run=False)

    conflicts = client.get("/api/location-conflicts").json()
    assert conflicts["total"] == 1
    [item] = conflicts["items"]
    assert item["registration_no"] == "99/1/2564"
    assert sorted(row["location"]["value"] for row in item["rows"]) == ["A-1", "B-9"]
    report = client.get("/api/location-match-report").json()
    assert report["location_conflicts"] == 1
    assert {source["source_name"]: source["location_conflict_keys"] for source in report["location_sources"]} == {
        "ห้องทดลอง": 1, "ห้องอื่น": 1,
    }


def test_completeness_is_counted_per_sheet(rawdata, client):
    run_profile(load_profile(write_profile(rawdata / "p.json")), rawdata, dry_run=False)
    [source] = client.get("/api/data-completeness").json()["sources"]
    assert source["source_name"] == "ห้องทดลอง"
    assert source["totals"]["rows"] == 5
    assert source["totals"]["matching_key"] == 4
    sheets = {sheet["sheet"]: sheet for sheet in source["sheets"]}
    assert sheets["ทะเบียน"]["material"] == 2
    assert sheets["ทะเบียน"]["role"] == "register"
    assert sheets["ชั้น A"]["location"] == 2
    assert sheets["นอกชั้น"]["location"] == 1


def test_a_profile_naming_a_missing_sheet_is_refused(rawdata):
    profile = load_profile(write_profile(rawdata / "p.json", sheets={"ไม่มีชีตนี้": {"skip": "x"}}))
    with pytest.raises(ProfileError):
        run_profile(profile, rawdata, dry_run=True)


def test_a_profile_with_an_unknown_role_is_refused(tmp_path):
    with pytest.raises(ProfileError):
        load_profile(write_profile(tmp_path / "p.json", role="shelf"))


def test_the_bundled_profiles_are_valid():
    from pathlib import Path

    profiles = sorted((Path(__file__).resolve().parents[1] / "import_profiles").glob("*.json"))
    assert len(profiles) == 9
    names = [load_profile(path).source_name for path in profiles]
    assert len(set(names)) == len(names)
