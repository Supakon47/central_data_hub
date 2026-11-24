"""Browsing records, the Dashboard, and administrator edits."""

import pytest
from sqlalchemy import select

from app.models import AuditLog, DataQualityIssue, Record

from .factories import add_issue, add_record, add_source


@pytest.fixture
def register(session):
    source = add_source(session, "บัญชีเดินทุ่ง")
    add_record(session, source, "99/1/2564", "พระพุทธรูป", material="สำริด", status_photographed="ถ่ายภาพแล้ว")
    add_record(session, source, "99/2/2565", "ตะเกียง", material="ดินเผา", image_url="https://example.org/a.jpg")
    add_record(session, source, "99/2/2565", "ตะเกียงซ้ำ", material=None)
    add_record(session, source, None, None, sheet="Sheet2")
    session.commit()
    return source


def test_health_reports_admin_access(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["admin_access_configured"] is True


def test_home_page_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store, max-age=0"


def test_records_can_be_filtered(client, register):
    def total(**params):
        return client.get("/api/records", params=params).json()["total"]

    assert total() == 4
    assert total(q="ตะเกียง") == 2
    assert total(material_group="metal") == 1
    assert total(material_group="none") == 2
    assert total(has_image="true") == 1
    assert total(has_description="false") == 1
    assert total(registration_year="2565") == 2
    assert total(attention="photographed") == 3
    assert total(source_sheet="Sheet2") == 1


def test_invalid_filters_are_rejected(client, register):
    assert client.get("/api/records", params={"material_group": "nope"}).status_code == 422
    assert client.get("/api/records", params={"registration_year": "64"}).status_code == 422


def test_record_detail_lists_duplicates(client, register, session):
    first, second = client.get("/api/records", params={"q": "ตะเกียง"}).json()["items"]
    detail = client.get(f"/api/records/{first['id']}").json()
    assert [item["id"] for item in detail["duplicate_candidates"]] == [second["id"]]
    assert detail["location"] is None
    assert client.get("/api/records/999999").status_code == 404


def test_dashboard_counts(client, register):
    body = client.get("/api/dashboard").json()
    assert body["total_records"] == 4
    assert body["with_registration_no"] == 3
    assert body["with_image_url"] == 1
    assert body["duplicate_registration_groups"] == 1
    assert body["follow_up"]["photographed"] == 3
    duplicates = client.get("/api/duplicates").json()
    assert duplicates["total_groups"] == 1
    assert duplicates["groups"][0]["registration_no"] == "99/2/2565"


def test_filter_options_group_materials_and_years(client, register):
    body = client.get("/api/filter-options").json()
    groups = {item["value"]: item["count"] for item in body["material_groups"]}
    assert groups["metal"] == 1
    assert groups["terracotta"] == 1
    assert groups["none"] == 2
    assert body["registration_years"] == [{"label": "2565", "count": 2}, {"label": "2564", "count": 1}]


def test_cached_counts_refresh_after_an_edit(admin_client, register):
    assert admin_client.get("/api/dashboard").json()["total_records"] == 4
    admin_client.post("/api/admin/records", json={"registration_no": "99/3/2566", "title_description": "ถ้วย"})
    assert admin_client.get("/api/dashboard").json()["total_records"] == 5


def test_admin_creates_updates_and_deletes_a_record(admin_client, register, session):
    created = admin_client.post("/api/admin/records", json={
        "registration_no": " 99/3/2566 ", "title_description": "ถ้วย\r\n\r\n\r\nลายคราม",
    })
    assert created.status_code == 201, created.text
    record = created.json()
    assert record["registration_no"] == "99/3/2566"
    assert record["title_description"] == "ถ้วย\n\nลายคราม"
    assert record["source_name"] == "แก้ไขโดยเจ้าหน้าที่"

    updated = admin_client.patch(f"/api/admin/records/{record['id']}", json={"material": "กระเบื้อง"})
    assert updated.json()["material"] == "กระเบื้อง"
    assert admin_client.patch(f"/api/admin/records/{record['id']}", json={}).status_code == 422

    deleted = admin_client.delete(f"/api/admin/records/{record['id']}").json()
    assert deleted == {"deleted": True, "record_id": record["id"]}
    assert admin_client.get(f"/api/records/{record['id']}").status_code == 404
    actions = session.scalars(select(AuditLog.action).order_by(AuditLog.id)).all()
    assert actions == ["create", "update", "delete"]


def test_creating_a_record_needs_registration_and_title(admin_client):
    response = admin_client.post("/api/admin/records", json={"registration_no": "99/3/2566"})
    assert response.status_code == 422
    assert "รายการ" in response.json()["detail"]


def test_deleting_a_record_keeps_its_quality_issue(admin_client, register, session):
    record_id = admin_client.get("/api/records", params={"q": "พระพุทธรูป"}).json()["items"][0]["id"]
    issue = add_issue(session, register, session.get(Record, record_id))
    session.commit()
    admin_client.delete(f"/api/admin/records/{record_id}")
    session.expire_all()
    assert session.get(DataQualityIssue, issue.id).record_id is None


def test_admin_routes_need_a_session(client):
    assert client.get("/api/admin/audit").status_code == 401
    assert client.post("/api/admin/records", json={}).status_code == 401
    assert client.get("/api/admin/session").json() == {"configured": True, "authenticated": False}


def test_wrong_password_is_refused(client):
    assert client.post("/api/admin/login", json={"password": "wrong-password"}).status_code == 401


def test_logout_ends_the_session(admin_client):
    assert admin_client.get("/api/admin/session").json()["authenticated"] is True
    admin_client.post("/api/admin/logout")
    assert admin_client.get("/api/admin/session").json()["authenticated"] is False
