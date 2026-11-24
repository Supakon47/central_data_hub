"""The review workflow: propose pairs, report them, approve, and undo."""

import pytest
from sqlalchemy import select

from app.models import AuditLog

from .factories import add_record, add_source


@pytest.fixture
def pilot(session):
    """A register with three objects and a storage room with four rows."""
    register = add_source(session, "บัญชีเดินทุ่ง")
    room = add_source(session, "ห้องโลหะ 3")
    records = {
        "object_a": add_record(session, register, "99/1/2564", "พระพุทธรูป"),
        "object_b": add_record(session, register, "99/2/2564", "ตะเกียง"),
        "object_c": add_record(session, register, "99/9/2564", "ถ้วย"),
        "shelf_a": add_record(session, room, "99/1/2564", "พระพุทธรูปสำริด", shelf="A-1"),
        "shelf_b": add_record(session, room, "99/2/2564", "ขันน้ำ", shelf="B-2"),
        # Merged cell: a storage row with a blank shelf is not an object.
        "blank_shelf": add_record(session, room, "99/9/2564", "ถ้วย", shelf=""),
        "old_number": add_record(session, room, "LM.5834/2534", "กระดิ่ง", shelf="C-3"),
        "placeholder": add_record(session, room, "ไม่มีเลข 3", "เศษภาชนะ", shelf="C-4"),
    }
    session.commit()
    return records


def candidate_pairs(client):
    items = client.get("/api/location-match-candidates").json()["items"]
    return {(item["object_record"]["id"], item["location_record"]["id"]): item for item in items}


def test_candidates_pair_objects_with_located_storage_rows(client, pilot):
    pairs = candidate_pairs(client)
    assert set(pairs) == {
        (pilot["object_a"].id, pilot["shelf_a"].id),
        (pilot["object_b"].id, pilot["shelf_b"].id),
    }
    assert pairs[(pilot["object_a"].id, pilot["shelf_a"].id)]["title_conflict"] is False
    assert pairs[(pilot["object_b"].id, pilot["shelf_b"].id)]["title_conflict"] is True
    assert pairs[(pilot["object_a"].id, pilot["shelf_a"].id)]["location_record"]["location"]["value"] == "A-1"


def test_report_counts_storage_rows(client, pilot):
    report = client.get("/api/location-match-report").json()
    assert report["object_records"] == {"rows": 3, "distinct_keys": 3, "keys_with_location": 2}
    [room] = report["location_sources"]
    assert room["source_name"] == "ห้องโลหะ 3"
    assert room["rows"] == 5
    assert room["missing_location"] == 1
    assert room["placeholder_registration"] == 1
    assert room["with_key"] == 4
    assert room["matched"] == 3
    assert room["unmatched"] == 1
    assert room["unmatched_by_year"] == {"before_register": 1, "since_register": 0, "no_year": 0}
    assert (room["pairs"], room["title_conflict_pairs"], room["pending"]) == (2, 1, 2)


def test_approve_then_undo_returns_the_pair_to_the_queue(admin_client, pilot, session):
    object_a, shelf_a = pilot["object_a"], pilot["shelf_a"]
    response = admin_client.post("/api/admin/location-match-reviews", json={
        "object_record_id": object_a.id, "location_record_id": shelf_a.id, "decision": "approved",
    })
    assert response.status_code == 200, response.text
    review_id = response.json()["id"]

    assert (object_a.id, shelf_a.id) not in candidate_pairs(admin_client)
    detail = admin_client.get(f"/api/records/{object_a.id}").json()
    assert [item["location"]["value"] for item in detail["linked_locations"]] == ["A-1"]
    assert admin_client.get("/api/location-match-report").json()["location_sources"][0]["approved"] == 1

    response = admin_client.delete(f"/api/admin/location-match-reviews/{review_id}")
    assert response.status_code == 200, response.text
    assert (object_a.id, shelf_a.id) in candidate_pairs(admin_client)
    assert admin_client.get(f"/api/records/{object_a.id}").json()["linked_locations"] == []

    actions = session.scalars(select(AuditLog.action).order_by(AuditLog.id)).all()
    assert actions == ["review_location_match", "undo_location_match"]


def test_reviewing_again_updates_the_same_decision(admin_client, pilot):
    pair = {"object_record_id": pilot["object_b"].id, "location_record_id": pilot["shelf_b"].id}
    first = admin_client.post("/api/admin/location-match-reviews", json={**pair, "decision": "approved"}).json()
    second = admin_client.post("/api/admin/location-match-reviews", json={**pair, "decision": "rejected"}).json()
    assert first["id"] == second["id"]
    reviews = admin_client.get("/api/location-match-reviews").json()
    assert reviews["total"] == 1
    assert reviews["items"][0]["decision"] == "rejected"


def test_pairs_with_different_registrations_are_refused(admin_client, pilot):
    response = admin_client.post("/api/admin/location-match-reviews", json={
        "object_record_id": pilot["object_a"].id, "location_record_id": pilot["shelf_b"].id, "decision": "approved",
    })
    assert response.status_code == 422


def test_reviews_need_an_administrator(client, pilot):
    response = client.post("/api/admin/location-match-reviews", json={
        "object_record_id": pilot["object_a"].id, "location_record_id": pilot["shelf_a"].id, "decision": "approved",
    })
    assert response.status_code == 401
    assert client.delete("/api/admin/location-match-reviews/1").status_code == 401


def test_undoing_an_unknown_review_is_404(admin_client, pilot):
    assert admin_client.delete("/api/admin/location-match-reviews/999").status_code == 404
