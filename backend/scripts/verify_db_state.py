"""One-off Phase 1 pre-migration verification (safe, read-only)."""
import asyncio

from sqlalchemy import text

from app.database import AsyncSessionLocal


async def main() -> None:
    async with AsyncSessionLocal() as s:
        tables = (
            await s.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
            )
        ).scalars().all()
        print(f"TABLES ({len(tables)}):")
        for t in tables:
            print("  -", t)

        rules = (await s.execute(text("SELECT count(*) FROM tbl_scheme_eligibility_rule"))).scalar()
        docs = (await s.execute(text("SELECT count(*) FROM tbl_scheme_document_master"))).scalar()
        citizens = (await s.execute(text("SELECT count(*) FROM tbl_citizen_master"))).scalar()
        assessments = (await s.execute(text("SELECT count(*) FROM tbl_eligibility_assessment"))).scalar()
        print(f"rules={rules} docs={docs} citizens={citizens} assessments={assessments}")

        cols = (
            await s.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'tbl_eligibility_assessment' ORDER BY ordinal_position"
                )
            )
        ).scalars().all()
        print("tbl_eligibility_assessment columns:", cols)


if __name__ == "__main__":
    asyncio.run(main())
