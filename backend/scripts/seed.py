"""
Seed script to load schemes.json into the database.
Run with: PYTHONPATH=. python scripts/seed.py
"""

import asyncio
import json
import logging
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models.scheme import (
    SchemeDocumentMaster,
    SchemeEligibilityRule,
    SchemeMaster,
    SchemeRuleGroup,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

async def seed_data():
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    seed_files = [
        Path(__file__).parent.parent / "seed_data" / "schemes.json",
        Path(__file__).parent.parent / "seed_data" / "schemes_extended.json",
    ]
    schemes_payload = {"schemes": []}
    loaded_any = False
    for seed_file in seed_files:
        if not seed_file.exists():
            logger.warning(f"Seed file not found, skipping: {seed_file}")
            continue
        with open(seed_file, "r", encoding="utf-8-sig") as f:
            schemes_payload["schemes"].extend(json.load(f)["schemes"])
        loaded_any = True
    if not loaded_any:
        logger.error("No seed files found")
        return
    data = schemes_payload

    async with async_session() as session:
        # Idempotent seeding: skip schemes that already exist by name so a
        # re-run never duplicates rows (the seeder previously inserted
        # unconditionally, which duplicated every scheme on a second run).
        existing_names = set(
            (await session.execute(select(SchemeMaster.scheme_name))).scalars()
        )
        seeded = 0
        skipped = 0

        for s_data in data["schemes"]:
            if s_data["scheme_name"] in existing_names:
                logger.info(f"Skipping existing scheme: {s_data['scheme_name']}")
                skipped += 1
                continue

            scheme = SchemeMaster(
                scheme_name=s_data["scheme_name"],
                department_name=s_data.get("department_name"),
                scheme_category=s_data.get("scheme_category"),
                description=s_data.get("description"),
                benefit_description=s_data.get("benefit_description"),
                status=s_data.get("status", "ACTIVE"),
                official_source_url=s_data.get("official_source_url"),
                application_url=s_data.get("application_url"),
                group_combining_operator=s_data.get("group_combining_operator", "AND"),
            )
            session.add(scheme)
            await session.flush()
            seeded += 1

            # Add groups and rules
            for g_data in s_data.get("rule_groups", []):
                group = SchemeRuleGroup(
                    scheme_id=scheme.scheme_id,
                    group_name=g_data["group_name"],
                    intra_group_operator=g_data["intra_group_operator"],
                    group_priority=g_data.get("group_priority", 1),
                )
                session.add(group)
                await session.flush()

                for r_data in g_data.get("rules", []):
                    rule = SchemeEligibilityRule(
                        scheme_id=scheme.scheme_id,
                        group_id=group.group_id,
                        parameter_name=r_data["parameter_name"],
                        operator=r_data["operator"],
                        required_value=str(r_data["required_value"]),
                        rule_description=r_data.get("rule_description"),
                        rule_priority=r_data.get("rule_priority", 1),
                    )
                    session.add(rule)

            # Add documents
            for d_data in s_data.get("documents", []):
                doc = SchemeDocumentMaster(
                    scheme_id=scheme.scheme_id,
                    document_type=d_data["document_type"],
                    mandatory_flag=d_data.get("mandatory_flag", True),
                    description=d_data.get("description"),
                )
                session.add(doc)

        await session.commit()
        logger.info(f"Seed complete: {seeded} schemes inserted, {skipped} skipped (already exist).")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(seed_data())
