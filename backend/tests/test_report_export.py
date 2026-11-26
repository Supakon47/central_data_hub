"""The data-request workbook sent to data owners."""

from io import BytesIO

import openpyxl

from .factories import add_record, add_source

SHEETS = ["อ่านก่อน", "สรุปต่อแหล่ง", "ความครบถ้วนต่อชีต", "ไม่พบในทะเบียน", "ไม่มีเลขทะเบียน", "ตำแหน่งขัดแย้ง"]
URL = "/api/admin/reports/data-request.xlsx"


def seed(session):
    register = add_source(session, "บัญชีเดินทุ่ง")
    room = add_source(session, "ห้องโลหะ")
    other_room = add_source(session, "ห้องหิน")
    add_record(session, register, "99/1/2564", "พระพุทธรูป", material="สำริด")
    add_record(session, room, "99/1/2564", "พระพุทธรูป", shelf="A-1")
    add_record(session, room, "99/5/2565", "ตะเกียง", shelf="A-2")        # since 2564, not in the register
    add_record(session, room, "LM.12/2530", "กระดิ่ง", shelf="A-3")       # before 2564
    add_record(session, room, "ไม่มีเลข 3", "เศษภาชนะ", shelf="A-4")     # no registration
    add_record(session, other_room, "99/1/2564", "พระพุทธรูป", shelf="S-9")  # location conflict
    session.commit()


def download(client):
    response = client.get(URL)
    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"].startswith('attachment; filename="data-hub-data-request-')
    return openpyxl.load_workbook(BytesIO(response.content), read_only=True)


def rows(workbook, name):
    return [list(row) for row in workbook[name].iter_rows(min_row=2, values_only=True)]


def test_the_report_needs_an_administrator(client):
    assert client.get(URL).status_code == 401


def test_the_report_lists_what_is_missing(admin_client, session):
    seed(session)
    workbook = download(admin_client)
    assert workbook.sheetnames == SHEETS

    not_found = rows(workbook, "ไม่พบในทะเบียน")
    assert [row[1] for row in not_found] == ["99/5/2565", "LM.12/2530"]  # numbers since 2564 first
    source, sheet, row_number, location = not_found[0][3:]
    assert (source, sheet, location) == ("ห้องโลหะ", "Sheet1", "A-2")
    assert isinstance(row_number, int)  # the row in the original file, for staff to find it

    no_number = rows(workbook, "ไม่มีเลขทะเบียน")
    assert [(row[0], row[1]) for row in no_number] == [("ไม่มีเลข 3", "เศษภาชนะ")]

    conflicts = rows(workbook, "ตำแหน่งขัดแย้ง")
    assert sorted(row[2] for row in conflicts) == ["A-1", "S-9"]

    summary = {row[0]: row for row in rows(workbook, "สรุปต่อแหล่ง")}
    assert summary["ห้องโลหะ"][1] == 4
    assert summary["บัญชีเดินทุ่ง"][5] == 1  # material filled on every row: 100%


def test_an_empty_database_still_gives_a_readable_report(admin_client):
    workbook = download(admin_client)
    assert workbook.sheetnames == SHEETS
    assert rows(workbook, "ไม่พบในทะเบียน") == []
