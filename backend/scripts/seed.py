"""
Seed script to load schemes.json into the database.
Run with: PYTHONPATH=. python scripts/seed.py
"""

import asyncio
import json
import logging
import os
from pathlib import Path

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

    seed_file = Path(__file__).parent.parent / "seed_data" / "schemes.json"
    if not seed_file.exists():
        logger.error(f"Seed file not found at {seed_file}")
        return

    with open(seed_file, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    async with async_session() as session:
        for s_data in data["schemes"]:
            # Check if scheme already exists
            # We don't do complex upserts here for simplicity; just skip if it exists
            # by name. In a real system, you might wipe and recreate or do upserts.
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
        logger.info("Seed data successfully loaded!")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(seed_data())
