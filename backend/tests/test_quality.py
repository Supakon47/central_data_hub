"""Data-quality issues and the Data Catalog."""

from .factories import add_issue, add_record, add_source


def test_issues_are_listed_and_can_be_resolved_and_reopened(admin_client, session):
    source = add_source(session, "บัญชีเดินทุ่ง")
    record = add_record(session, source, "99/1/2564", "พระพุทธรูป")
    issue = add_issue(session, source, record)
    add_issue(session, source, severity="error")
    session.commit()

    body = admin_client.get("/api/data-quality/issues").json()
    assert body["total"] == 2
    assert body["summary"] == {"errors": 1, "warnings": 1}
    assert admin_client.get("/api/data-quality/issues", params={"severity": "error"}).json()["total"] == 1

    resolved = admin_client.patch(f"/api/admin/data-quality/issues/{issue.id}", json={"is_resolved": True})
    assert resolved.json() == {"id": issue.id, "is_resolved": True}
    assert admin_client.get("/api/data-quality/issues").json()["total"] == 1
    assert admin_client.get("/api/data-quality/issues", params={"include_resolved": "true"}).json()["total"] == 2

    admin_client.patch(f"/api/admin/data-quality/issues/{issue.id}", json={"is_resolved": False})
    assert admin_client.get("/api/data-quality/issues").json()["total"] == 2
    assert admin_client.patch("/api/admin/data-quality/issues/999", json={"is_resolved": True}).status_code == 404


def test_catalog_lists_sources_with_counts(client, session):
    source = add_source(session, "ห้องโลหะ 3")
    add_record(session, source, "99/1/2564", "พระพุทธรูป", shelf="A-1")
    add_issue(session, source)
    session.commit()

    [entry] = client.get("/api/catalog").json()["sources"]
    assert entry["name"] == "ห้องโลหะ 3"
    assert entry["record_count"] == 1
    assert entry["unresolved_issues"] == 1
    assert entry["image_bridge"] == {"configured": False}
    assert entry["last_sync"] is None
