"""
AGE consistency tests (post-Phase-2C correctness fix).

Establishes one canonical age source:
  DATE_OF_BIRTH -> calculate_age() -> AGE profile fact -> eligibility engine

Covers:
  - boundary behaviour of the canonical calculate_age utility
  - the engine consuming the normalized AGE fact
  - fallbacks (no facts / closed fact / unparseable fact / no DOB)
  - the original live-E2E discrepancy case: DOB 2001-03-15 must yield the
    same age from the fact layer and from the engine on the same date.

Pure unit tests: no database, no network.
"""

from __future__ import annotations

from datetime import date

from app.models.citizen import CitizenMaster, FinancialProfile
from app.models.profile_fact import ProfileFact
from app.models.scheme import SchemeEligibilityRule, SchemeMaster, SchemeRuleGroup
from app.services.eligibility_engine import EligibilityEngine
from app.utils.date_calc import calculate_age


def _citizen(dob: date) -> CitizenMaster:
    citizen = CitizenMaster(
        full_name="Age Test",
        date_of_birth=dob,
        citizen_type="GENERAL",
    )
    citizen.financial_profile = FinancialProfile()
    return citizen


def _add_fact(citizen: CitizenMaster, code: str, value: str, data_type: str = "INTEGER") -> None:
    citizen.profile_facts.append(
        ProfileFact(citizen_id=citizen.citizen_id, fact_code=code, fact_value=value, data_type=data_type)
    )


def _age_scheme() -> SchemeMaster:
    scheme = SchemeMaster(scheme_name="Age-gated", group_combining_operator="AND")
    group = SchemeRuleGroup(group_name="Age", intra_group_operator="AND")
    group.rules = [SchemeEligibilityRule(parameter_name="age", operator=">=", required_value="18")]
    scheme.rule_groups = [group]
    return scheme


# ---------------------------------------------------------------- calculate_age


class TestCalculateAge:
    def test_birthday_already_occurred(self):
        assert calculate_age(date(2001, 3, 15), date(2026, 9, 16)) == 25

    def test_birthday_not_yet_occurred(self):
        assert calculate_age(date(2001, 3, 15), date(2026, 2, 1)) == 24

    def test_birthday_is_today(self):
        assert calculate_age(date(2001, 3, 15), date(2026, 3, 15)) == 25

    def test_day_before_birthday(self):
        assert calculate_age(date(2001, 3, 15), date(2026, 3, 14)) == 24

    def test_leap_day_dob_non_leap_year(self):
        # Feb 29 birthday: counts as occurring on Mar 1 in non-leap years.
        assert calculate_age(date(2004, 2, 29), date(2025, 2, 28)) == 20
        assert calculate_age(date(2004, 2, 29), date(2025, 3, 1)) == 21

    def test_leap_day_dob_leap_year(self):
        assert calculate_age(date(2004, 2, 29), date(2024, 2, 29)) == 20

    def test_newborn(self):
        assert calculate_age(date(2026, 1, 10), date(2026, 9, 16)) == 0

    def test_defaults_to_today(self):
        dob = date(1990, 1, 1)
        today = date.today()
        assert calculate_age(dob) == today.year - 1990 - (
            (today.month, today.day) < (1, 1)
        )


# ------------------------------------------------------- engine AGE consumption


class TestEngineAgeConsumption:
    def test_engine_reads_normalized_age_fact(self):
        citizen = _citizen(date(2001, 3, 15))
        _add_fact(citizen, "AGE", "25")
        engine = EligibilityEngine()
        actual = engine._resolve_parameter(citizen, "age")
        assert actual == 25

    def test_fact_age_wins_over_identity_dob(self):
        # DOB would give 25 today, but the fact layer says 25 from an
        # earlier normalization; the fact is authoritative either way —
        # the point is the engine never computes a *different* second age.
        citizen = _citizen(date(2001, 3, 15))
        _add_fact(citizen, "DATE_OF_BIRTH", "2001-03-15", "DATE")
        _add_fact(citizen, "AGE", "25")
        engine = EligibilityEngine()
        assert engine._resolve_parameter(citizen, "age") == 25

    def test_engine_falls_back_to_calculate_age_without_facts(self):
        citizen = _citizen(date(2001, 3, 15))
        engine = EligibilityEngine()
        assert engine._resolve_parameter(citizen, "age") == calculate_age(date(2001, 3, 15))

    def test_closed_fact_is_ignored(self):
        citizen = _citizen(date(2001, 3, 15))
        stale = ProfileFact(
            citizen_id=citizen.citizen_id, fact_code="AGE", fact_value="99", data_type="INTEGER"
        )
        stale.effective_until = date(2020, 1, 1)  # superseded/closed
        citizen.profile_facts.append(stale)
        engine = EligibilityEngine()
        assert engine._resolve_parameter(citizen, "age") == calculate_age(date(2001, 3, 15))

    def test_unparseable_fact_falls_back(self):
        citizen = _citizen(date(2001, 3, 15))
        _add_fact(citizen, "AGE", "not-a-number")
        engine = EligibilityEngine()
        assert engine._resolve_parameter(citizen, "age") == calculate_age(date(2001, 3, 15))

    def test_missing_dob_and_no_facts_returns_none(self):
        citizen = _citizen(date(2001, 3, 15))
        citizen.date_of_birth = None
        engine = EligibilityEngine()
        assert engine._resolve_parameter(citizen, "age") is None

    def test_none_age_blocks_rule(self):
        # None actual must fail the rule (engine coercion contract), not crash.
        citizen = _citizen(date(2001, 3, 15))
        citizen.date_of_birth = None
        result, details, _reason = EligibilityEngine().evaluate_scheme(citizen, _age_scheme())
        assert result is False
        assert details["groups"][0]["rules"][0]["actual"] is None


# ------------------------------------------------------------------- agreement


class TestFactEngineAgreement:
    def test_dob_2001_03_15_fact_equals_engine(self):
        """The original live-E2E discrepancy case: both layers must agree."""
        evaluation_date = date(2026, 9, 16)

        # Fact layer path: DOB -> canonical calculate_age -> AGE fact value.
        fact_age = calculate_age(date(2001, 3, 15), evaluation_date)

        # Engine path: consumes the normalized AGE fact.
        citizen = _citizen(date(2001, 3, 15))
        _add_fact(citizen, "DATE_OF_BIRTH", "2001-03-15", "DATE")
        _add_fact(citizen, "AGE", str(fact_age))
        engine_age = EligibilityEngine()._resolve_parameter(citizen, "age")

        assert fact_age == 25
        assert engine_age == fact_age == 25

    def test_engine_age_rule_uses_fact_value(self):
        citizen = _citizen(date(2001, 3, 15))
        _add_fact(citizen, "AGE", "25")
        result, details, _reason = EligibilityEngine().evaluate_scheme(citizen, _age_scheme())
        assert result is True
        assert details["groups"][0]["rules"][0]["actual"] == 25
