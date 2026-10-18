"""
Regression tests for SchemeRepository date-aware active filtering.

Verifies that get_all_active_for_evaluation and get_all_active:
  - Exclude schemes whose end_date is in the past.
  - Exclude schemes whose start_date is in the future.
  - Include schemes within their valid date range.
  - Include schemes with no end_date (or no start_date).
  - Exclude inactive or expired-status schemes regardless of dates.
  - Correctly handle exact boundary dates (start_date == today, end_date == today).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.models.scheme import SchemeMaster
from app.repositories.scheme_repository import SchemeRepository


# ----------------------------------------------------------------------
# Fast Unit / Query-Compilation Tests (No Database Roundtrips)
# ----------------------------------------------------------------------


def _mock_db_result():
    mock_res = MagicMock()
    mock_res.unique.return_value = mock_res
    mock_res.scalars.return_value.all.return_value = []
    return mock_res


@pytest.mark.asyncio
async def test_evaluation_query_compilation_with_explicit_as_of_date():
    """SQL statement for get_all_active_for_evaluation contains date and status filters."""
    db = AsyncMock()
    db.execute.return_value = _mock_db_result()

    repo = SchemeRepository(db)
    ref_date = date(2026, 6, 15)
    await repo.get_all_active_for_evaluation(as_of=ref_date)

    stmt = db.execute.call_args.args[0]
    sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    # Must filter on status == ACTIVE
    assert "tbl_scheme_master.status = 'ACTIVE'" in sql
    # Start date must be NULL or <= ref_date
    assert "tbl_scheme_master.start_date IS NULL OR tbl_scheme_master.start_date <= '2026-06-15'" in sql
    # End date must be NULL or >= ref_date
    assert "tbl_scheme_master.end_date IS NULL OR tbl_scheme_master.end_date >= '2026-06-15'" in sql
    # Must join rules graph and omit document master
    assert "LEFT OUTER JOIN tbl_scheme_rule_group" in sql
    assert "LEFT OUTER JOIN tbl_scheme_eligibility_rule" in sql
    assert "tbl_scheme_document_master" not in sql


@pytest.mark.asyncio
async def test_evaluation_query_compilation_defaults_to_today_utc():
    """Default as_of date uses UTC today."""
    db = AsyncMock()
    db.execute.return_value = _mock_db_result()

    repo = SchemeRepository(db)
    await repo.get_all_active_for_evaluation()

    stmt = db.execute.call_args.args[0]
    sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    today_utc = datetime.now(timezone.utc).date().isoformat()

    assert f"tbl_scheme_master.start_date <= '{today_utc}'" in sql
    assert f"tbl_scheme_master.end_date >= '{today_utc}'" in sql


@pytest.mark.asyncio
async def test_get_all_active_query_compilation_with_date_filters():
    """get_all_active also filters by status and validity dates."""
    db = AsyncMock()
    db.execute.return_value = _mock_db_result()

    repo = SchemeRepository(db)
    ref_date = date(2026, 8, 1)
    await repo.get_all_active(as_of=ref_date)

    stmt = db.execute.call_args.args[0]
    sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    assert "tbl_scheme_master.status = 'ACTIVE'" in sql
    assert "tbl_scheme_master.start_date <= '2026-08-01'" in sql
    assert "tbl_scheme_master.end_date >= '2026-08-01'" in sql


# ----------------------------------------------------------------------
# Live Database Integration Tests (Rolled-back Session)
# ----------------------------------------------------------------------

_test_engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
_TestSession = async_sessionmaker(_test_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db():
    """Yield an async session whose transaction is always rolled back."""
    async with _TestSession() as session:
        try:
            yield session
        finally:
            await session.rollback()


def _build_test_schemes(
    ref_date: date, prefix: str = "DateTest"
) -> tuple[list[SchemeMaster], dict[str, SchemeMaster]]:
    """Generate a consistent set of test schemes covering all inclusion/exclusion date scenarios."""
    run_id = uuid.uuid4().hex[:8]

    def _create(name_suffix: str, status: str, start_d: date | None, end_d: date | None) -> SchemeMaster:
        return SchemeMaster(
            scheme_name=f"{prefix} {name_suffix} {run_id}",
            status=status,
            start_date=start_d,
            end_date=end_d,
            group_combining_operator="AND",
        )

    schemes = {
        "valid": _create("Valid", "ACTIVE", date(2026, 1, 1), date(2026, 12, 31)),
        "no_dates": _create("NoDates", "ACTIVE", None, None),
        "no_end": _create("NoEnd", "ACTIVE", date(2026, 1, 1), None),
        "bound_start": _create("BoundStart", "ACTIVE", ref_date, date(2026, 12, 31)),
        "bound_end": _create("BoundEnd", "ACTIVE", date(2026, 1, 1), ref_date),
        "expired_date": _create("ExpiredDate", "ACTIVE", date(2026, 1, 1), ref_date - timedelta(days=1)),
        "future_start": _create("FutureStart", "ACTIVE", ref_date + timedelta(days=1), date(2026, 12, 31)),
        "inactive": _create("Inactive", "INACTIVE", date(2026, 1, 1), date(2026, 12, 31)),
        "expired_status": _create("ExpiredStatus", "EXPIRED", date(2026, 1, 1), date(2026, 12, 31)),
    }
    return list(schemes.values()), schemes


def _assert_scheme_filtering_expectations(
    returned_ids: set[uuid.UUID], schemes: dict[str, SchemeMaster]
) -> None:
    """Verify inclusions and exclusions for date-aware filtering."""
    # Verify expected inclusions
    assert schemes["valid"].scheme_id in returned_ids, "Scheme within valid date range must be included"
    assert schemes["no_dates"].scheme_id in returned_ids, "Scheme with no dates must be included"
    assert schemes["no_end"].scheme_id in returned_ids, "Scheme with no end date must be included"
    assert schemes["bound_start"].scheme_id in returned_ids, "Scheme starting today must be included"
    assert schemes["bound_end"].scheme_id in returned_ids, "Scheme ending today must be included"

    # Verify expected exclusions
    assert schemes["expired_date"].scheme_id not in returned_ids, "Scheme with past end_date must be excluded"
    assert schemes["future_start"].scheme_id not in returned_ids, "Scheme with future start_date must be excluded"
    assert schemes["inactive"].scheme_id not in returned_ids, "INACTIVE scheme must be excluded"
    assert schemes["expired_status"].scheme_id not in returned_ids, "EXPIRED status scheme must be excluded"


@pytest.mark.asyncio
async def test_live_db_scheme_date_filtering_scenarios(db: AsyncSession):
    """Verify that get_all_active_for_evaluation filters schemes by date and status in live DB."""
    ref_date = date(2026, 6, 15)
    all_schemes, scheme_map = _build_test_schemes(ref_date, prefix="EvalDateTest")
    db.add_all(all_schemes)
    await db.flush()

    repo = SchemeRepository(db)
    active_schemes = await repo.get_all_active_for_evaluation(as_of=ref_date)
    returned_ids = {s.scheme_id for s in active_schemes}

    _assert_scheme_filtering_expectations(returned_ids, scheme_map)


@pytest.mark.asyncio
async def test_live_db_get_all_active_date_filtering_scenarios(db: AsyncSession):
    """Verify that get_all_active filters schemes by date and status in live DB."""
    ref_date = date(2026, 6, 15)
    all_schemes, scheme_map = _build_test_schemes(ref_date, prefix="ActiveDateTest")
    db.add_all(all_schemes)
    await db.flush()

    repo = SchemeRepository(db)
    active_schemes = await repo.get_all_active(as_of=ref_date)
    returned_ids = {s.scheme_id for s in active_schemes}

    _assert_scheme_filtering_expectations(returned_ids, scheme_map)
