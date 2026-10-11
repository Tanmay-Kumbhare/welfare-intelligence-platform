import uuid
from datetime import date
import pytest

from app.models.citizen import CitizenMaster
from app.models.scheme import SchemeMaster, SchemeRuleGroup, SchemeEligibilityRule
from app.schemas.assessment import RecommendationItem
from app.schemas.scheme import SchemeResponse
from app.services.eligibility_engine import EligibilityEngine
from app.services.recommendation_service import rank_recommendations


def _make_item(
    scheme_id: uuid.UUID,
    scheme_name: str,
    eligibility_result: bool,
    rule_match_score: float | None = None,
    target_persona: str | None = None,
    document_status: str | None = None,
) -> RecommendationItem:
    scheme_dict = {
        "scheme_id": scheme_id,
        "scheme_name": scheme_name,
        "status": "ACTIVE",
        "group_combining_operator": "AND",
        "target_persona": target_persona,
    }
    return RecommendationItem(
        scheme=SchemeResponse(**scheme_dict),
        eligibility_result=eligibility_result,
        rule_match_score=rule_match_score,
        assessment_date=date(2026, 1, 1),
        document_status=document_status,
    )


def test_empty_recommendation_list():
    """Empty recommendation list returns empty list safely."""
    assert rank_recommendations([]) == []


def test_eligible_schemes_rank_above_ineligible_schemes():
    """Eligible schemes always rank before ineligible schemes regardless of score."""
    id1 = uuid.uuid4()
    id2 = uuid.uuid4()
    # Ineligible scheme with 90% match score vs Eligible scheme with 50% match score
    ineligible_high_score = _make_item(
        id1, "Scheme Ineligible", eligibility_result=False, rule_match_score=90.0
    )
    eligible_low_score = _make_item(
        id2, "Scheme Eligible", eligibility_result=True, rule_match_score=50.0
    )

    ranked = rank_recommendations([ineligible_high_score, eligible_low_score])

    assert ranked[0].scheme.scheme_id == id2
    assert ranked[0].eligibility_result is True
    assert ranked[1].scheme.scheme_id == id1
    assert ranked[1].eligibility_result is False


def test_higher_match_scores_rank_first_within_same_eligibility_group():
    """Within the same eligibility group, higher match scores rank first."""
    id1 = uuid.uuid4()
    id2 = uuid.uuid4()
    id3 = uuid.uuid4()

    item_low = _make_item(id1, "Scheme A", eligibility_result=True, rule_match_score=40.0)
    item_high = _make_item(id2, "Scheme B", eligibility_result=True, rule_match_score=95.0)
    item_mid = _make_item(id3, "Scheme C", eligibility_result=True, rule_match_score=75.0)

    ranked = rank_recommendations([item_low, item_high, item_mid])

    assert [r.scheme.scheme_name for r in ranked] == ["Scheme B", "Scheme C", "Scheme A"]


def test_missing_match_scores_handled_safely():
    """Missing scores safely default to 0.0 and rank after scored schemes."""
    id1 = uuid.uuid4()
    id2 = uuid.uuid4()

    item_none = _make_item(id1, "Scheme None", eligibility_result=True, rule_match_score=None)
    item_scored = _make_item(id2, "Scheme Scored", eligibility_result=True, rule_match_score=10.0)

    ranked = rank_recommendations([item_none, item_scored])

    assert ranked[0].scheme.scheme_name == "Scheme Scored"
    assert ranked[1].scheme.scheme_name == "Scheme None"


def test_equal_scores_deterministic_tie_breaker():
    """Equal scores use alphabetical scheme_name, then scheme_id tie breaker."""
    id_z = uuid.UUID("11111111-1111-1111-1111-111111111111")
    id_a = uuid.UUID("22222222-2222-2222-2222-222222222222")

    # Both have 80.0 score, but "Alpha Scheme" < "Beta Scheme"
    item_beta = _make_item(id_z, "Beta Scheme", eligibility_result=True, rule_match_score=80.0)
    item_alpha = _make_item(id_a, "Alpha Scheme", eligibility_result=True, rule_match_score=80.0)

    ranked = rank_recommendations([item_beta, item_alpha])
    assert [r.scheme.scheme_name for r in ranked] == ["Alpha Scheme", "Beta Scheme"]

    # Identical names use scheme_id tie breaker
    id_lower = uuid.UUID("00000000-0000-0000-0000-000000000001")
    id_higher = uuid.UUID("00000000-0000-0000-0000-000000000002")
    item_same_name_higher = _make_item(id_higher, "Same Scheme", eligibility_result=True, rule_match_score=80.0)
    item_same_name_lower = _make_item(id_lower, "Same Scheme", eligibility_result=True, rule_match_score=80.0)

    ranked_same = rank_recommendations([item_same_name_higher, item_same_name_lower])
    assert ranked_same[0].scheme.scheme_id == id_lower
    assert ranked_same[1].scheme.scheme_id == id_higher


def test_citizen_persona_relevance_boost():
    """When match scores are equal, schemes matching citizen's target persona rank higher."""
    citizen = CitizenMaster(
        citizen_type="FARMER",
        profile_types=["FARMER"],
        date_of_birth=date(1990, 1, 1),
    )

    id_general = uuid.uuid4()
    id_farmer = uuid.uuid4()

    # Both 80% match score, but one targets FARMER and one GENERAL
    item_general = _make_item(
        id_general, "A General Welfare Scheme", eligibility_result=True,
        rule_match_score=80.0, target_persona="GENERAL"
    )
    item_farmer = _make_item(
        id_farmer, "Z Farmer Welfare Scheme", eligibility_result=True,
        rule_match_score=80.0, target_persona="FARMER"
    )

    # Even though "A General" comes first alphabetically, item_farmer has persona match boost
    ranked = rank_recommendations([item_general, item_farmer], citizen=citizen)
    assert ranked[0].scheme.scheme_id == id_farmer
    assert "Directly matches your profile type" in ranked[0].recommendation_explanation


def test_document_readiness_boost_for_eligible_schemes():
    """Eligible schemes with COMPLETE documents rank ahead of incomplete documents at equal score."""
    id1 = uuid.uuid4()
    id2 = uuid.uuid4()

    item_missing_docs = _make_item(
        id1, "A Scheme Pending Docs", eligibility_result=True,
        rule_match_score=80.0, document_status="MISSING_DOCUMENTS"
    )
    item_complete_docs = _make_item(
        id2, "Z Scheme Complete Docs", eligibility_result=True,
        rule_match_score=80.0, document_status="COMPLETE"
    )

    ranked = rank_recommendations([item_missing_docs, item_complete_docs])
    assert ranked[0].scheme.scheme_id == id2
    assert "All required documents uploaded" in ranked[0].recommendation_explanation


def test_existing_eligibility_decisions_remain_unchanged():
    """PM-KISAN eligibility evaluation and deterministic outcome remain unchanged."""
    engine = EligibilityEngine()

    citizen = CitizenMaster(
        citizen_type="FARMER",
        date_of_birth=date(1980, 1, 1),
    )
    from app.models.citizen import FinancialProfile
    citizen.financial_profile = FinancialProfile(
        land_holding_size=1.5,
        is_income_tax_payer=False,
    )

    scheme = SchemeMaster(
        scheme_name="PM-KISAN",
        group_combining_operator="AND",
        target_persona="FARMER",
    )
    group1 = SchemeRuleGroup(group_name="Farmer", intra_group_operator="AND")
    group1.rules = [
        SchemeEligibilityRule(parameter_name="citizen_type", operator="==", required_value="FARMER"),
        SchemeEligibilityRule(parameter_name="land_holding_size", operator="<=", required_value="2.0"),
    ]
    scheme.rule_groups = [group1]

    result, details, reason = engine.evaluate_scheme(citizen, scheme)

    # Outcome is strictly deterministic
    assert result is True
    assert details["overall_result"] is True
    assert details["rule_match_score"] == 100.0
