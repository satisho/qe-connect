import io

from openpyxl import Workbook


def test_lobs_add_and_guarded_delete(sampled):
    lobs = sampled.get("/api/lobs").json()
    assert [x["name"] for x in lobs][:2] == ["Customer & Digital Channels", "Operations & Enterprise Systems"]
    assert sampled.post("/api/lobs", json={"name": "Corporate Services"}).status_code == 200
    assert sampled.post("/api/lobs", json={"name": "corporate services"}).status_code == 409
    used = lobs[0]
    assert sampled.delete(f"/api/lobs/{used['id']}").status_code == 409
    new = [x for x in sampled.get("/api/lobs").json() if x["name"] == "Corporate Services"][0]
    assert sampled.delete(f"/api/lobs/{new['id']}").status_code == 200


def test_import_applications_paste(sampled):
    text = ("Application\tProject ID\tLine of Business\tDelivery team / ART\tRespondent name\tRespondent email\n"
            "Web check-in\tPRJ-2001\tCorporate Services\tART#4\tNina Patel\tnina.patel@example.com\n"
            "Bad row\t\tCustomer & Digital Channels\t\tTom\tnot-an-email\n"
            "Customer portal\tPRJ-1042\tCustomer & Digital Channels\tART#1\tJordan Lee\tjordan.new@example.com\n")
    r = sampled.post("/api/applications/import", data={"mode": "add", "text": text})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["added"] == 2 and res["updated"] == 1
    assert res["created_lobs"] == ["Corporate Services"]
    assert any("not-an-email" in w for w in res["warnings"])
    apps = {a["name"]: a for a in sampled.get("/api/applications").json()}
    assert apps["Customer portal"]["respondent_email"] == "jordan.new@example.com"
    assert apps["Customer portal"]["status"] == "completed"  # updating kept the response


def test_import_applications_needs_header(sampled):
    r = sampled.post("/api/applications/import", data={"mode": "add", "text": "foo,bar\n1,2\n"})
    assert r.status_code == 422 and "Application" in r.json()["detail"]


def _bank_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Survey Questions"
    ws.append(["Sample question bank"])  # a title row above the header
    ws.append(["Q ID", "Section", "Pillar", "Focus area", "Question (as shown to respondent)", "Help text (shown under the question)",
               "Response type", "Answer options (one per line)", "Required?", "Priority", "Show-if logic", "Source"])
    ws.append(["A2", "A. About You & the Application", "Context (not scored)", "Respondent", "Which Line of Business?", "",
               "Single choice", "", "Yes", "Core", "Options mirror the LOBs on the 'Lists' tab", ""])
    ws.append(["B8", "B. Application Profile", "QE Engineering", "Integration", "How many systems?", "", "Single choice",
               "None\n1-3\n4-10\nNot known", "Yes", "Core", "", "#9"])
    ws.append(["B9", "B. Application Profile", "QE Engineering", "Integration", "List them.", "", "Long text", "", "No",
               "Optional", "Show if B8 is not 'None' or 'Not known'", ""])
    ws2 = wb.create_sheet("Additional Survey Questions")
    ws2.append(["Q ID", "Section", "Question (as shown to respondent)", "Pillar", "Response type", "Answer options (one per line)",
                "Required?", "Priority", "Show-if logic"])
    ws2.append(["L8", "L. Planning, Governance & Capacity", "Vendor evidence reviewed?", "Quality Governance", "Single choice",
                "Always\nSometimes\nNot sure", "No", "Optional", "Show if C3 includes a vendor, system integrator or SaaS vendor"])
    ws3 = wb.create_sheet("Lists")
    ws3.append(["LOB", "Response types"])
    ws3.append(["Customer & Digital Channels", "Single choice"])
    ws3.append(["Shared Services", "Long text"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_import_questions_from_workbook(admin):
    r = admin.post("/api/questions/import", data={"mode": "replace"},
                   files={"file": ("QA_Survey_Question_Bank.xlsx", _bank_xlsx(),
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["imported"] == 4
    assert len(res["sheets"]) == 2
    assert set(res["created_lobs"]) == {"Customer & Digital Channels", "Shared Services"}
    assert any("L8" in w and "not recognised" in w for w in res["warnings"])
    qs = {q["qid"]: q for q in admin.get("/api/questions").json()}
    assert qs["B8"]["options"] == ["None", "1-3", "4-10", "Not known"]
    assert qs["B9"]["rule"] == {"kind": "match", "qid": "B8", "negate": True, "values": 2, "match": ["none", "not known"]}
    assert qs["A2"]["rule"]["kind"] == "lobs"
    assert qs["L8"]["rule"]["kind"] == "bad" and qs["L8"]["core"] is False
    # fix the rule in the portal
    r = admin.patch(f"/api/questions/{qs['L8']['id']}", json={"show_if": "Show if B8 is '4-10'"})
    assert r.json()["rule"]["kind"] == "match"
    prev = admin.get("/api/survey-preview").json()["questions"]
    a2 = [q for q in prev if q["qid"] == "A2"][0]
    assert "Shared Services" in a2["options"] and a2["options"][-1].startswith("Other")


def test_rejects_xls_and_bad_files(admin):
    r = admin.post("/api/questions/import", data={"mode": "replace"}, files={"file": ("old.xls", b"\xd0\xcf", "application/vnd.ms-excel")})
    assert r.status_code == 422 and ".xlsx" in r.json()["detail"]
    r = admin.post("/api/questions/import", data={"mode": "replace"}, files={"file": ("x.xlsx", b"not a zip", "application/octet-stream")})
    assert r.status_code == 422


def test_templates(admin):
    for kind in ("applications", "questions"):
        r = admin.get(f"/api/templates/{kind}.xlsx")
        assert r.status_code == 200 and r.content[:2] == b"PK"


def test_email_template_needs_link(admin):
    r = admin.put("/api/settings/email", json={"subject": "Hi", "body": "No link here"})
    assert r.status_code == 422
    r = admin.put("/api/settings/email", json={"subject": "Hi {application}", "body": "Go: {survey_link}"})
    assert r.status_code == 200
