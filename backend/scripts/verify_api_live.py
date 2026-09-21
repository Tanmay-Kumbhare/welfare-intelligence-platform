"""One-off Phase 1 post-migration API verification (safe: deletes only its own test citizen).

Runs all requests inside ONE event loop via httpx ASGITransport, matching
how the app behaves under a real uvicorn server (single loop, pooled DB
connections are loop-bound).
"""
from __future__ import annotations

import asyncio

import httpx

from app.main import app


async def main() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        print("== 1. GET /health ==")
        r = await client.get("/health")
        print(r.status_code, r.json())
        assert r.status_code == 200

        print("\n== 2. GET /api/v1/schemes/ ==")
        r = await client.get("/api/v1/schemes/")
        schemes = r.json()
        print(r.status_code, f"{len(schemes)} schemes")
        assert r.status_code == 200
        assert len(schemes) == 7, f"Expected 7 seeded schemes, got {len(schemes)}"
        print("scheme names:", [s["scheme_name"] for s in schemes])

        print("\n== 3. GET /api/v1/schemes/{id} (detail) ==")
        r = await client.get(f"/api/v1/schemes/{schemes[0]['scheme_id']}")
        detail = r.json()
        print(r.status_code, detail["scheme_name"], "groups:", len(detail["rule_groups"]))
        assert r.status_code == 200
        assert len(detail["rule_groups"]) > 0

        print("\n== 4. POST /api/v1/citizens/ (create citizen) ==")
        citizen_payload = {
            "full_name": "Phase 1 Verification Citizen",
            "date_of_birth": "1990-06-15",
            "gender": "FEMALE",
            "citizen_type": "STUDENT",
            "demographic": {
                "education_level": "GRADUATE",
                "family_size": 4,
                "social_category": "SC",
            },
            "financial": {
                "annual_income": 180000,
                "employment_status": "STUDENT",
                "poverty_category": "BPL",
            },
            "location": {"state": "Maharashtra", "district": "Pune", "area_type": "URBAN"},
        }
        r = await client.post("/api/v1/citizens/", json=citizen_payload)
        print(r.status_code, r.json().get("citizen_id"))
        assert r.status_code == 201, r.text
        citizen = r.json()
        citizen_id = citizen["citizen_id"]

        print("\n== 5. GET /api/v1/citizens/{id} ==")
        r = await client.get(f"/api/v1/citizens/{citizen_id}")
        print(r.status_code, r.json()["full_name"])
        assert r.status_code == 200

        print("\n== 6. POST /api/v1/eligibility/evaluate/{citizen_id} ==")
        r = await client.post(f"/api/v1/eligibility/evaluate/{citizen_id}")
        results = r.json()
        print(r.status_code, f"{len(results)} assessments")
        assert r.status_code == 200
        assert len(results) == 7
        eligible = [a for a in results if a["eligibility_result"]]
        print("eligible:", len(eligible), "| not eligible:", 7 - len(eligible))
        print("sample assessment keys:", sorted(results[0].keys()))

        print("\n== 7. GET /api/v1/recommendations/{citizen_id} ==")
        r = await client.get(f"/api/v1/recommendations/{citizen_id}")
        recs = r.json()
        print(
            r.status_code,
            f"total={recs['total_schemes_evaluated']} eligible={recs['eligible_count']} "
            f"ineligible={recs['ineligible_count']}",
        )
        assert r.status_code == 200
        assert recs["total_schemes_evaluated"] == 7

    print("\n== 8. Cleanup verification citizen (its own data only) ==")
    from sqlalchemy import text

    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        await session.execute(
            text("DELETE FROM tbl_eligibility_assessment WHERE citizen_id = :cid"),
            {"cid": citizen_id},
        )
        await session.execute(
            text(
                "DELETE FROM tbl_citizen_master WHERE citizen_id = :cid "
                "AND full_name = 'Phase 1 Verification Citizen'"
            ),
            {"cid": citizen_id},
        )
        await session.commit()
    print("verification citizen removed")

    await app.router.shutdown()
    from app.database import engine

    await engine.dispose()

    print("\nALL API CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
