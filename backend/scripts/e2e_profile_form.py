"""Temporary live-API E2E branch tester for the citizen profile form.

Drives the real HTTP API (uvicorn on :8000) through the exact flow the React
page performs: create citizen -> create draft -> save answers -> complete ->
normalize -> eligibility. Exercises each major employment branch plus
education / farmer / disability / PwD-student combos, verifying conditional
SHOW/HIDE, requirement enforcement, value integrity after save + reload,
profile facts, and provenance. Deletes every created citizen (CASCADE) at the
end. Run: backend/.venv/Scripts/python.exe scripts/_tmp_branch_e2e.py
"""

import asyncio
import sys
import uuid
from datetime import date

import httpx
from sqlalchemy import delete, text

from app.database import AsyncSessionLocal
from app.models.citizen import CitizenMaster as Citizen

BASE = "http://localhost:8000/api/v1"
CLIENT = httpx.AsyncClient(base_url=BASE, timeout=300.0)

PASS, FAIL = [], []


async def post_retry(path, json_body, tries=3):
    """POST with retry on read-timeout; complete/normalize/eligibility are idempotent."""
    last = None
    for attempt in range(tries):
        try:
            return await CLIENT.post(path, json=json_body)
        except httpx.ReadTimeout as exc:
            last = exc
            print(f"  .... {path} timed out (attempt {attempt + 1}/{tries}), retrying")
    raise last


def check(label, ok, detail=""):
    (PASS if ok else FAIL).append(f"{label}{' — ' + detail if detail and not ok else ''}")
    print(("  ok  " if ok else "  FAIL") + f" {label}" + (f"  [{detail}]" if detail and not ok else ""))


def build_answers(sections, values):
    """Map question_code -> answer value, using the real question_ids.

    Returns (list[AnswerInput-like dicts], qid_by_code, per-question type).
    """
    by_code = {}
    for s in sections:
        for q in s["questions"]:
            by_code[q["question_code"]] = q
    payload, qmap = [], {}
    for code, value in values.items():
        q = by_code.get(code)
        if q is None:
            raise KeyError(f"unknown question_code in fixture: {code}")
        payload.append({"question_id": q["question_id"], "value": value, "source": "USER_INPUT"})
        qmap[q["question_id"]] = q
    return payload, qmap


def applicable_codes(sections, answers_by_code):
    """Mirror of backend compute_applicable_map (frontend semantics)."""
    by_code = {}
    for s in sections:
        for q in s["questions"]:
            by_code[q["question_code"]] = q
    applicable = {code: True for code in by_code}

    def val(dep):
        return answers_by_code.get(dep) if applicable.get(dep, True) else None

    def loose_equal(value, comparison):
        if value is None or comparison is None:
            return False
        if isinstance(value, bool):
            return value is (comparison.strip().lower() in {"yes", "true", "1"})
        return str(value).strip().casefold() == str(comparison).strip().casefold()

    def satisfied(cond):
        v = val(cond["depends_on_question_code"])
        op = cond["operator"].upper()
        comp = cond.get("comparison_value")
        if op in ("EQUALS", "NOT_EQUALS"):
            eq = loose_equal(v, comp)
            return eq if op == "EQUALS" else (v is not None and not eq) if comp else v is not None
        if op == "IN":
            opts = [t.strip() for t in (comp or "").split(",")]
            return v is not None and any(loose_equal(v, t) for t in opts)
        return False

    changed = True
    guard = 0
    while changed and guard < 30:
        changed, guard = False, guard + 1
        for code, q in by_code.items():
            rows = [c for c in q.get("conditions", []) or [] if c["depends_on_question_code"] in by_code]
            if not rows:
                continue
            show_groups, hide_groups = {}, {}
            for c in rows:
                (show_groups if c["action"].upper() == "SHOW" else hide_groups) \
                    .setdefault(c["condition_group"], []).append(c)
            visible = all(any(satisfied(c) for c in grp) for grp in show_groups.values()) if show_groups else True
            if visible and hide_groups and any(all(satisfied(c) for c in grp) for grp in hide_groups.values()):
                visible = False
            if applicable[code] != visible:
                applicable[code] = visible
                changed = True
    return applicable


def required_codes(sections, applicable):
    req = {}
    for s in sections:
        for q in s["questions"]:
            if q.get("required"):
                req[q["question_code"]] = q
    return [c for c in req if applicable.get(c, True)]


async def register_citizen(tag, dob="1996-05-20"):
    name = f"BranchE2E {tag} {uuid.uuid4().hex[:6]}"
    r = await CLIENT.post("/citizens/", json={
        "full_name": name, "date_of_birth": dob, "gender": "FEMALE",
        "citizen_type": "GENERAL",
        "demographic": {"family_size": 4, "social_category": "OBC"},
        "financial": {"annual_income": 180000, "poverty_category": "APL"},
        "location": {"state": "Maharashtra", "district": "Pune", "area_type": "URBAN"},
    })
    assert r.status_code == 201, f"citizen create failed: {r.status_code} {r.text}"
    return r.json()["citizen_id"], name


async def start_form(citizen_id):
    r = await CLIENT.get("/forms/GENERAL_CITIZEN_PROFILE")
    assert r.status_code == 200, r.text
    form = r.json()
    r = await CLIENT.post(f"/forms/GENERAL_CITIZEN_PROFILE/submissions",
                          json={"citizen_id": citizen_id, "answers": []})
    assert r.status_code == 201, f"draft create failed: {r.status_code} {r.text}"
    sub = r.json()
    return form, sub["submission_id"]


async def save(submission_id, citizen_id, answers_payload):
    r = await CLIENT.put(f"/forms/submissions/{submission_id}",
                         json={"citizen_id": citizen_id, "answers": answers_payload})
    return r


def stored_map(sub_json):
    """Extract stored answer values keyed by question_code from a read."""
    out = {}
    for a in sub_json.get("answers", []):
        code = a.get("question_code")
        for col in ("answer_boolean", "answer_decimal", "answer_number", "answer_date", "answer_json", "answer_text"):
            if a.get(col) is not None:
                out[code] = a[col]
                break
        else:
            out[code] = a.get("answer_text")
    return out


async def cleanup(citizen_ids):
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Citizen).where(Citizen.citizen_id.in_(citizen_ids)))
        await db.commit()


async def run_branch(tag, dob, extra_answers, expect_visible, expect_hidden,
                     facts_expected, branch_note, family_members=None):
    """One full lifecycle for one branch. Returns created citizen_id."""
    print(f"\n=== BRANCH: {tag} ===")
    citizen_id, name = await register_citizen(tag, dob)
    form, sub_id = await start_form(citizen_id)
    sections = form["sections"]

    base = {
        "FAMILY_SIZE": 4,
        "STATE": "Maharashtra", "DISTRICT": "Pune", "PINCODE": "411001",
        "AREA_TYPE": "URBAN",
        "ANNUAL_INCOME": 240000,
        "MARITAL_STATUS": "SINGLE", "RELIGION": "HINDU",
        "HAS_AADHAAR": True, "HAS_RATION_CARD": False,
    }
    if family_members:
        base["FAMILY_MEMBERS"] = family_members
    answers = {**base, **extra_answers}

    payload, qmap = build_answers(sections, answers)
    applicable = applicable_codes(sections, answers)

    # Conditional visibility sanity per branch
    for code in expect_visible:
        check(f"{tag}: {code} visible", applicable.get(code) is True, f"got {applicable.get(code)}")
    for code in expect_hidden:
        check(f"{tag}: {code} hidden", applicable.get(code) is False, f"got {applicable.get(code)}")

    # Hidden questions must NOT be sent (frontend rule)
    qcode_by_qid = {q["question_id"]: q["question_code"] for s in sections for q in s["questions"]}
    send_payload = [a for a in payload if applicable.get(qcode_by_qid[a["question_id"]], True)]
    hidden_dropped = len(send_payload) < len(payload)
    print(f"  (sending {len(send_payload)}/{len(payload)} answers; hidden dropped: {hidden_dropped})")

    r = await save(sub_id, citizen_id, send_payload)
    check(f"{tag}: save 200", r.status_code == 200, f"{r.status_code} {r.text[:300]}")
    if r.status_code != 200:
        return citizen_id

    saved = stored_map(r.json())
    for code, want in answers.items():
        if not applicable.get(code, True):
            continue
        got = saved.get(code)
        same = (got == want) if not isinstance(want, float) else abs((got or 0) - want) < 1e-6
        check(f"{tag}: stored {code}={want!r}", same, f"stored {got!r}")

    # Reload (GET) — persistence check
    r2 = await CLIENT.get(f"/forms/submissions/{sub_id}", params={"citizen_id": citizen_id})
    check(f"{tag}: reload 200", r2.status_code == 200, f"{r2.status_code}")
    reloaded = stored_map(r2.json()) if r2.status_code == 200 else {}
    diffs = [c for c, w in answers.items()
             if applicable.get(c, True) and reloaded.get(c) != w and not (isinstance(w, float) and isinstance(reloaded.get(c), (int, float)) and abs(w - reloaded[c]) < 1e-6)]
    check(f"{tag}: reload preserves answers", not diffs, f"diffs: {diffs}")

    # Complete — must succeed only with all applicable required answers
    r = await post_retry(f"/forms/submissions/{sub_id}/complete", {"citizen_id": citizen_id})
    check(f"{tag}: complete 200", r.status_code == 200, f"{r.status_code} {r.text[:300]}")
    if r.status_code != 200:
        return citizen_id

    # Normalize
    r = await post_retry(f"/forms/submissions/{sub_id}/normalize", {"citizen_id": citizen_id})
    check(f"{tag}: normalize 200", r.status_code == 200, f"{r.status_code} {r.text[:300]}")
    norm = r.json() if r.status_code == 200 else {}
    check(f"{tag}: no normalization errors", not norm.get("errors"), str(norm.get("errors"))[:200])

    # Facts present
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(text(
            "SELECT f.fact_code, f.fact_value FROM tbl_profile_fact f "
            "WHERE f.citizen_id = :cid AND f.effective_until IS NULL"), {"cid": citizen_id})).all()
        prov = (await db.execute(text(
            "SELECT count(*) FROM tbl_profile_fact_provenance p JOIN tbl_profile_fact f ON p.fact_id = f.fact_id "
            "WHERE f.citizen_id = :cid"), {"cid": citizen_id})).scalar()
    facts = {c: v for c, v in rows}
    for fc in facts_expected:
        got, want = facts.get(fc), facts_expected[fc]
        if got is None:
            ok = False
        elif isinstance(want, bool):
            ok = str(got).upper() == ("TRUE" if want else "FALSE")
        elif isinstance(want, (int, float)):
            try:
                ok = abs(float(got) - float(want)) < 1e-9
            except (TypeError, ValueError):
                ok = False
        else:
            ok = str(got).upper() == str(want).upper()
        check(f"{tag}: fact {fc}={want!r}", ok, f"got {got!r}")
    check(f"{tag}: provenance rows exist", (prov or 0) > 0, f"count={prov}")

    # Eligibility end-to-end (no 4xx/5xx)
    r = await post_retry(f"/eligibility/evaluate/{citizen_id}", {})
    check(f"{tag}: eligibility 200", r.status_code == 200, f"{r.status_code} {r.text[:300]}")

    return citizen_id


async def switch_branch_test():
    """Answer STUDENT, save, then switch to SELF_EMPLOYED, save, complete.

    Verifies hidden-branch answers are dropped on the second save (frontend
    rule: only applicable answers are sent; backend keeps stale rows but
    complete/normalize must still succeed).
    """
    print("\n=== BRANCH: STUDENT -> SELF_EMPLOYED switch ===")
    citizen_id, _ = await register_citizen("switch")
    form, sub_id = await start_form(citizen_id)
    sections = form["sections"]

    base = {"FAMILY_SIZE": 3, "STATE": "Maharashtra", "DISTRICT": "Pune",
            "ANNUAL_INCOME": 120000, "HAS_AADHAAR": True}

    # 1) student branch
    answers1 = {**base, "CURRENTLY_STUDYING": True, "COURSE_NAME": "B.Sc Physics",
                "YEAR_OF_STUDY": 2, "INSTITUTION_NAME": "Fergusson College",
                "EMPLOYMENT_STATUS": "STUDENT"}
    payload, _ = build_answers(sections, answers1)
    app1 = applicable_codes(sections, answers1)
    check("switch: COURSE_NAME visible when studying", app1.get("COURSE_NAME") is True)
    qcode_by_qid = {q["question_id"]: q["question_code"] for s in sections for q in s["questions"]}
    r = await save(sub_id, citizen_id, [a for a in payload if app1.get(qcode_by_qid[a["question_id"]], True)])
    check("switch: save student 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")

    # 2) switch to self-employed; student specifics must become hidden
    answers2 = {**base, "CURRENTLY_STUDYING": False, "EMPLOYMENT_STATUS": "SELF_EMPLOYED",
                "OCCUPATION": "Tailor", "MONTHLY_INCOME": 15000.5, "WORK_SECTOR": "INFORMAL"}
    payload2, _ = build_answers(sections, answers2)
    app2 = applicable_codes(sections, answers2)
    check("switch: COURSE_NAME hidden after CURRENTLY_STUDYING=false", app2.get("COURSE_NAME") is False)
    check("switch: OCCUPATION visible for SELF_EMPLOYED", app2.get("OCCUPATION") is True)
    r = await save(sub_id, citizen_id, [a for a in payload2 if app2.get(qcode_by_qid[a["question_id"]], True)])
    check("switch: save self-employed 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")

    r = await post_retry(f"/forms/submissions/{sub_id}/complete", {"citizen_id": citizen_id})
    check("switch: complete 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    r = await post_retry(f"/forms/submissions/{sub_id}/normalize", {"citizen_id": citizen_id})
    check("switch: normalize 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    r = await post_retry(f"/eligibility/evaluate/{citizen_id}", {})
    check("switch: eligibility 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    return citizen_id


async def incomplete_required_test():
    """Complete must 422 while an applicable required answer is missing,
    then succeed once it is provided."""
    print("\n=== REQUIRED ENFORCEMENT ===")
    citizen_id, _ = await register_citizen("req")
    form, sub_id = await start_form(citizen_id)
    sections = form["sections"]
    answers = {"FAMILY_SIZE": 2, "STATE": "Maharashtra", "ANNUAL_INCOME": 90000,
               "HAS_AADHAAR": True}
    payload, _ = build_answers(sections, answers)
    app = applicable_codes(sections, answers)
    qcode_by_qid = {q["question_id"]: q["question_code"] for s in sections for q in s["questions"]}
    r = await save(sub_id, citizen_id, [a for a in payload if app.get(qcode_by_qid[a["question_id"]], True)])
    check("req: save 200", r.status_code == 200)
    missing = required_codes(sections, app)
    check("req: DISTRICT correctly still required", "DISTRICT" in missing, str(missing))
    r = await CLIENT.post(f"/forms/submissions/{sub_id}/complete", json={"citizen_id": citizen_id})
    check("req: complete 422 with missing required", r.status_code == 422, f"{r.status_code}")
    body = r.json() if r.status_code == 422 else {}
    detail = body.get("detail", body)
    missing_list = detail.get("missing_required", []) if isinstance(detail, dict) else []
    check("req: missing_required lists DISTRICT", "DISTRICT" in missing_list, str(missing_list))
    # fix and complete
    payload2, _ = build_answers(sections, {**answers, "DISTRICT": "Pune"})
    r = await save(sub_id, citizen_id, [a for a in payload2 if app.get(qcode_by_qid[a["question_id"]], True)])
    check("req: save with DISTRICT 200", r.status_code == 200)
    r = await post_retry(f"/forms/submissions/{sub_id}/complete", {"citizen_id": citizen_id})
    check("req: complete 200 after fix", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    return citizen_id


async def value_type_test():
    """Wrong-typed values must be rejected with a clean 422 (no 500)."""
    print("\n=== TYPE VALIDATION ===")
    citizen_id, _ = await register_citizen("types")
    form, sub_id = await start_form(citizen_id)
    sections = form["sections"]
    fam = [{"relationship": "SPOUSE", "name": "Test Spouse", "income": 50000, "dependent_flag": True}]
    answers = {"FAMILY_SIZE": "not-a-number", "FAMILY_MEMBERS": fam,
               "STATE": "Maharashtra", "DISTRICT": "Pune", "ANNUAL_INCOME": 100000,
               "HAS_AADHAAR": True}
    payload, _ = build_answers(sections, answers)
    r = await save(sub_id, citizen_id, payload)
    check("types: non-integer FAMILY_SIZE rejected (4xx)", 400 <= r.status_code < 500,
          f"{r.status_code} {r.text[:200]}")
    check("types: no server 500", r.status_code < 500)
    return citizen_id


async def ownership_test():
    """Another citizen must not be able to touch a submission (403)."""
    print("\n=== OWNERSHIP ===")
    owner, _ = await register_citizen("owner")
    other, _ = await register_citizen("other")
    form, sub_id = await start_form(owner)
    r = await CLIENT.get(f"/forms/submissions/{sub_id}", params={"citizen_id": other})
    check("ownership: foreign read 403", r.status_code == 403, f"{r.status_code}")
    r = await CLIENT.put(f"/forms/submissions/{sub_id}",
                         json={"citizen_id": other, "answers": []})
    check("ownership: foreign save 403", r.status_code == 403, f"{r.status_code}")
    return owner, other


async def main():
    created = []
    try:
        fam = [
            {"relationship": "SPOUSE", "name": "Test Spouse A", "date_of_birth": "1994-02-10",
             "gender": "MALE", "income": 120000, "dependent_flag": False,
             "education_status": "GRADUATE", "occupation": "Clerk"},
            {"relationship": "SON", "name": "Test Son A", "date_of_birth": "2015-08-01",
             "gender": "MALE", "dependent_flag": True, "education_status": "PRIMARY"},
            {"relationship": "DAUGHTER", "name": "Test Daughter A", "date_of_birth": "2018-03-14",
             "gender": "FEMALE", "dependent_flag": True},
            {"relationship": "FATHER", "name": "Test Father A", "date_of_birth": "1962-06-05",
             "gender": "MALE", "dependent_flag": True},
        ]
        created.append(await run_branch(
            "STUDENT", "2004-09-10",
            {"CURRENTLY_STUDYING": True, "EDUCATION_LEVEL": "HIGHER_SECONDARY",
             "COURSE_NAME": "B.Sc", "YEAR_OF_STUDY": 2, "ACADEMIC_YEAR": "2025-26",
             "INSTITUTION_NAME": "Fergusson College", "INSTITUTION_TYPE": "GOVERNMENT",
             "MARKS_PERCENTAGE": 82.5, "ANNUAL_FEE": 15000.0, "HOSTEL_STATUS": "DAY_SCHOLAR",
             "SCHOLARSHIP_CURRENTLY_RECEIVED": False,
             "EMPLOYMENT_STATUS": "STUDENT"},
            expect_visible=["COURSE_NAME", "YEAR_OF_STUDY", "INSTITUTION_NAME",
                            "SCHOLARSHIP_CURRENTLY_RECEIVED"],
            expect_hidden=["EMPLOYMENT_TYPE", "EMPLOYER_NAME", "MONTHLY_INCOME", "OCCUPATION"],
            facts_expected={"EMPLOYMENT_STATUS": "STUDENT", "CURRENTLY_STUDYING": True,
                            "FAMILY_SIZE": 4},
            branch_note="student", family_members=fam))

        created.append(await run_branch(
            "SELF_EMPLOYED", "1990-01-15",
            {"CURRENTLY_STUDYING": False, "EMPLOYMENT_STATUS": "SELF_EMPLOYED",
             "OCCUPATION": "Tailor", "MONTHLY_INCOME": 22000.75, "WORK_SECTOR": "INFORMAL",
             "EDUCATION_LEVEL": "SECONDARY", "FARMER_STATUS": "NO"},
            expect_visible=["OCCUPATION", "MONTHLY_INCOME", "WORK_SECTOR"],
            expect_hidden=["EMPLOYMENT_TYPE", "EMPLOYER_TYPE", "EMPLOYER_NAME",
                           "FARMER_TYPE", "LAND_OWNERSHIP_STATUS"],
            facts_expected={"EMPLOYMENT_STATUS": "SELF_EMPLOYED", "SELF_EMPLOYED": True},
            branch_note="self-employed"))

        created.append(await run_branch(
            "UNEMPLOYED", "1988-03-03",
            {"CURRENTLY_STUDYING": False, "EMPLOYMENT_STATUS": "UNEMPLOYED",
             "EDUCATION_LEVEL": "GRADUATE", "POVERTY_CATEGORY": "BPL",
             "FARMER_STATUS": "NO", "HAS_DISABILITY": "NO"},  # noqa: boolean-by-string, like the UI's select
            expect_visible=["EDUCATION_LEVEL"],
            expect_hidden=["OCCUPATION", "EMPLOYMENT_TYPE", "MONTHLY_INCOME",
                           "WORK_SECTOR", "DISABILITY_TYPE"],
            facts_expected={"EMPLOYMENT_STATUS": "UNEMPLOYED", "DISABILITY_STATUS": "NO"},
            branch_note="unemployed"))

        created.append(await run_branch(
            "EMPLOYED+FARMER", "1985-07-22",
            {"CURRENTLY_STUDYING": False, "EMPLOYMENT_STATUS": "EMPLOYED",
             "OCCUPATION": "Accountant", "EMPLOYMENT_TYPE": "PERMANENT",
             "EMPLOYER_TYPE": "PRIVATE", "EMPLOYER_NAME": "ACME Ltd",
             "MONTHLY_INCOME": 45000.0, "WORK_SECTOR": "FORMAL",
             "FARMER_STATUS": "SMALL", "FARMER_TYPE": "OWNER",
             "LAND_OWNERSHIP_STATUS": "OWNED", "TOTAL_LAND_AREA": 1.2,
             "LAND_UNIT": "HECTARE", "CULTIVATED_AREA": 1.0, "IRRIGATED_AREA": 0.5,
             "CROP_TYPE": "Cotton, Soybean", "AGRICULTURAL_INCOME": 95000.0,
             "HAS_KCC": True},
            expect_visible=["EMPLOYMENT_TYPE", "EMPLOYER_NAME", "MONTHLY_INCOME",
                            "FARMER_TYPE", "TOTAL_LAND_AREA", "CROP_TYPE", "HAS_KCC"],
            expect_hidden=[],
            facts_expected={"EMPLOYMENT_STATUS": "EMPLOYED", "SELF_EMPLOYED": False,
                            "FARMER_STATUS": "SMALL", "TENANT_FARMER": False,
                            "SHARECROPPER": False},
            branch_note="salaried + farmer"))

        created.append(await run_branch(
            "RETIRED+PwD", "1952-11-30",
            {"EMPLOYMENT_STATUS": "RETIRED", "CURRENTLY_STUDYING": False,
             "HAS_DISABILITY": "YES", "DISABILITY_TYPE": "PHYSICAL",
             "DISABILITY_PERCENTAGE": 65.0, "HAS_DISABILITY_CERTIFICATE": True,
             "OWNS_HOUSE": True, "HOUSE_OWNERSHIP_STATUS": "OWNED",
             "OWNS_VEHICLE": False, "OWNS_LIVESTOCK": False,
             "SOCIAL_CATEGORY": "SC", "HAS_CASTE_CERTIFICATE": True},
            expect_visible=["DISABILITY_TYPE", "DISABILITY_PERCENTAGE",
                            "HOUSE_OWNERSHIP_STATUS", "HAS_CASTE_CERTIFICATE"],
            expect_hidden=["COURSE_NAME", "FARMER_TYPE"],
            facts_expected={"EMPLOYMENT_STATUS": "RETIRED", "DISABILITY_STATUS": "YES",
                            "DISABILITY_PERCENTAGE": 65.0},
            branch_note="retired + PwD"))

        created.append(await switch_branch_test())
        created.append(await incomplete_required_test())
        created.append(await value_type_test())
        owner, other = await ownership_test()
        created.extend([owner, other])

    finally:
        if created:
            await cleanup(created)
        await CLIENT.aclose()

    print(f"\n================ RESULT: {len(PASS)} passed, {len(FAIL)} failed ================")
    for f in FAIL:
        print("FAILED:", f)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
