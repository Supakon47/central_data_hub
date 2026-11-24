import pytest

from app.normalization import normalise_registration_no
from app.services.filters import group_matches, normalise_filter_display
from app.services.locations import location_from_raw, registration_year_bucket, titles_conflict


@pytest.mark.parametrize(("value", "expected"), [
    ("99/1192/2564", "99/1192/2564"),
    (" 99 / 1192 / 2564 ", "99/1192/2564"),
    ("๙๙/๑๑๙๒/๒๕๖๔", "99/1192/2564"),
    ("lm.5834/34", "LM.5834/34"),
    ("99／1192／2564", "99/1192/2564"),
])
def test_registration_numbers_are_normalised(value, expected):
    assert normalise_registration_no(value) == expected


@pytest.mark.parametrize("value", [
    None, "", "-", "ไม่มี", "ไม่พบ", "ไม่ระบุ", "ชิ้นส่วน",
    "ไม่มีเลข 3", "ไม่มีเลขวัตถุ(3)", "ไม่ให้เลขปพ.12", "เลขไม่ชัดเจน", "99/เลขลบเลือน",
    "99/C1-1-ไม่มีเลข 5", "รอหาเลขใหม่",
    "2", "(1)", "99/",
    "ไม่มีตัวเลข", "abc",
])
def test_placeholders_never_become_matching_keys(value):
    assert normalise_registration_no(value) is None


@pytest.mark.parametrize(("object_title", "location_title", "conflict"), [
    ("พระพุทธรูป", "พระพุทธรูป", False),
    ("พระพุทธรูปปางมารวิชัย", "พระพุทธรูป", False),
    ("พระ พุทธรูป", "พระพุทธรูป", False),
    ("พระพุทธรูป", "ตะเกียง", True),
    (None, "ตะเกียง", False),
    ("พระพุทธรูป", "  ", False),
])
def test_titles_conflict_only_when_neither_contains_the_other(object_title, location_title, conflict):
    assert titles_conflict(object_title, location_title) is conflict


@pytest.mark.parametrize(("registration_no", "bucket"), [
    ("99/1192/2564", "since_register"),
    ("99/1192/2570", "since_register"),
    ("99/1192/2563", "before_register"),
    ("LM.5834/2534", "before_register"),
    ("ปพ.123", "no_year"),
    (None, "no_year"),
])
def test_registration_year_bucket(registration_no, bucket):
    assert registration_year_bucket(registration_no) == bucket


def test_location_is_read_from_any_location_column():
    assert location_from_raw({"เลขทะเบียน": "1", "ชั้นวาง": " A-1 "}) == {"field": "ชั้นวาง", "value": "A-1"}
    assert location_from_raw({"สถานที่เก็บ ": "ห้อง 3"}) == {"field": "สถานที่เก็บ ", "value": "ห้อง 3"}


def test_blank_location_is_no_location():
    assert location_from_raw({"ชั้นวาง": "  "}) is None
    assert location_from_raw({"เลขทะเบียน": "1"}) is None
    assert location_from_raw(None) is None


def test_filter_display_fixes_spacing_and_doubled_marks_only_for_matching():
    assert normalise_filter_display("หิิน  ทราย", {}) == "หิน ทราย"
    assert normalise_filter_display("ทอง เหลือง", {"ทอง เหลือง": "ทองเหลือง"}) == "ทองเหลือง"


def test_group_terms_match_at_word_end():
    # "ทอง " (with a space) matches a value that ends in ทอง, but not ทองแดง.
    assert group_matches("ทอง", ("ทอง ",))
    assert not group_matches("ทองแดง", ("ทอง ",))
