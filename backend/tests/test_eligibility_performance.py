"""Regression coverage for eligibility-query round-trip reductions.

These tests deliberately inspect repository execution boundaries rather than
asserting a wall-clock threshold, which would make the suite dependent on the
configured remote PostgreSQL latency.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.models.assessment import EligibilityAssessment
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.citizen_repository import CitizenRepository
from app.repositories.scheme_repository import SchemeRepository


def _result_with_rows(rows):
    result = MagicMock()
    result.unique.return_value = result
    result.scalars.return_value.all.return_value = rows
    return result


@pytest.mark.asyncio
async def test_full_profile_joins_singleton_profiles_and_selects_facts():
    """Eligibility must not fan out one query per singleton profile."""
    db = AsyncMock()
    db.execute.return_value = _result_with_rows([])

    await CitizenRepository(db).get_full_profile(uuid.uuid4())

    stmt = db.execute.call_args.args[0]
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "LEFT OUTER JOIN tbl_demographic_profile" in sql
    assert "LEFT OUTER JOIN tbl_financial_profile" in sql
    assert "LEFT OUTER JOIN tbl_location_profile" in sql
    # Profile facts remain a separate select-in collection query, preventing
    # row multiplication while making all fact resolution in-memory.
    assert len(stmt._with_options) == 4


@pytest.mark.asyncio
async def test_evaluation_scheme_loader_joins_only_the_rule_graph():
    """Evaluation loads schemes/groups/rules in one query and omits documents."""
    db = AsyncMock()
    db.execute.return_value = _result_with_rows([])

    schemes = await SchemeRepository(db).get_all_active_for_evaluation()

    assert list(schemes) == []
    stmt = db.execute.call_args.args[0]
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "LEFT OUTER JOIN tbl_scheme_rule_group" in sql
    assert "LEFT OUTER JOIN tbl_scheme_eligibility_rule" in sql
    assert "tbl_scheme_document_master" not in sql


@pytest.mark.asyncio
async def test_batch_assessment_upsert_uses_one_statement_for_all_schemes():
    """Seven scheme results are persisted with one upsert, not seven writes."""
    db = AsyncMock()
    expected = [
        EligibilityAssessment(
            assessment_id=uuid.uuid4(),
            citizen_id=uuid.uuid4(),
            scheme_id=uuid.uuid4(),
            eligibility_result=True,
        )
        for _ in range(7)
    ]
    db.execute.return_value = _result_with_rows(expected)
    rows = [
        {
            "citizen_id": uuid.uuid4(),
            "scheme_id": uuid.uuid4(),
            "eligibility_result": True,
            "reason": "eligible",
            "evaluation_details": {"overall_result": True, "groups": []},
        }
        for _ in range(7)
    ]

    persisted = await AssessmentRepository(db).upsert_assessments(rows)

    assert list(persisted) == expected
    db.execute.assert_awaited_once()
    statement = db.execute.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "INSERT INTO tbl_eligibility_assessment" in sql
    assert "ON CONFLICT ON CONSTRAINT uq_citizen_scheme_assessment" in sql


@pytest.mark.asyncio
async def test_batch_assessment_upsert_skips_database_for_no_schemes():
    db = AsyncMock()

    persisted = await AssessmentRepository(db).upsert_assessments([])

    assert persisted == []
    db.execute.assert_not_awaited()
