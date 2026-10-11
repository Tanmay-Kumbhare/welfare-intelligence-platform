import uuid
from datetime import date
import pytest

from app.models.citizen import CitizenMaster, FinancialProfile
from app.models.scheme import SchemeMaster, SchemeRuleGroup, SchemeEligibilityRule
from app.schemas.assessment import RecommendationItem
from app.schemas.scheme import SchemeResponse
from app.services.alternative_scheme_service import (
    AlternativeSchemeService,
    AlternativeSchemeSuggestion,
)
from app.services.eligibility_engine import EligibilityEngine


def _make_item(
    scheme_id: uuid.UUID,
    scheme_name: str,
    eligibility_result: bool,
    rule_match_score: float | None = None,
    scheme_category: str | None = None,
    target_persona: str | None = None,
) -> RecommendationItem:
    scheme_dict = {
        "scheme_id": scheme_id,
        "scheme_name": scheme_name,
        "status": "ACTIVE",
        "group_combining_operator": "AND",
        "scheme_category": scheme_category,
        "target_persona": target_persona,
    }
    return RecommendationItem(
        scheme=SchemeResponse(**scheme_dict),
        eligibility_result=eligibility_result,
        rule_match_score=rule_match_score,
        assessment_date=date(2026, 1, 1),
    )


def test_empty_catalogues_handled_safely():
    """Empty lists of items produce empty alternative suggestions without error."""
    id1 = uuid.uuid4()
    item = _make_item(id1, "Single Scheme", eligibility_result=False, rule_match_score=30.0)

    # All items empty
    alts = AlternativeSchemeService.find_alternatives_for_item(item, [])
    assert alts == []

    # Attaching on empty lists
    AlternativeSchemeService.attach_alternatives_to_recommendations([], [])


def test_no_self_recommendation():
    """The original scheme is NEVER suggested as its own alternative."""
    id1 = uuid.uuid4()
    ineligible_item = _make_item(
        id1, "PM-KISAN", eligibility_result=False, rule_match_score=60.0,
        scheme_category="AGRICULTURE", target_persona="FARMER"
    )

    # Catalogue containing only the scheme itself
    alts = AlternativeSchemeService.find_alternatives_for_item(ineligible_item, [ineligible_item])
    assert alts == []
    assert not any(a.scheme_id == id1 for a in alts)


def test_alternative_selection_by_category_and_eligibility():
    """Prioritizes confirmed-eligible schemes and schemes in the same category."""
    id_target = uuid.uuid4()
    id_eligible_same_cat = uuid.uuid4()
    id_eligible_diff_cat = uuid.uuid4()
    id_ineligible_same_cat = uuid.uuid4()
    id_unrelated = uuid.uuid4()

    # Target scheme: Ineligible Housing scheme
    target_item = _make_item(
        id_target, "PMAY-Gramin", eligibility_result=False,
        rule_match_score=40.0, scheme_category="HOUSING"
    )

    # 1. Eligible scheme in same category (HOUSING)
    alt_eligible_same_cat = _make_item(
        id_eligible_same_cat, "Housing Aid", eligibility_result=True,
        rule_match_score=100.0, scheme_category="HOUSING"
    )

    # 2. Eligible scheme in different category (AGRICULTURE)
    alt_eligible_diff_cat = _make_item(
        id_eligible_diff_cat, "Kisan Credit", eligibility_result=True,
        rule_match_score=100.0, scheme_category="AGRICULTURE"
    )

    # 3. Ineligible scheme in same category with partial match (HOUSING)
    alt_ineligible_same_cat = _make_item(
        id_ineligible_same_cat, "Urban Housing", eligibility_result=False,
        rule_match_score=60.0, scheme_category="HOUSING"
    )

    # 4. Unrelated scheme with 0 score (HEALTHCARE)
    alt_unrelated = _make_item(
        id_unrelated, "Health Cover", eligibility_result=False,
        rule_match_score=10.0, scheme_category="HEALTHCARE"
    )

    all_items = [
        target_item,
        alt_eligible_same_cat,
        alt_eligible_diff_cat,
        alt_ineligible_same_cat,
        alt_unrelated,
    ]

    alts = AlternativeSchemeService.find_alternatives_for_item(target_item, all_items, max_suggestions=3)

    # Should select top 3: eligible same cat > eligible diff cat > ineligible same cat
    assert len(alts) == 3
    assert alts[0].scheme_id == id_eligible_same_cat
    assert alts[0].is_confirmed_eligible is True
    assert "Housing" in alts[0].suggestion_reason

    assert alts[1].scheme_id == id_eligible_diff_cat
    assert alts[1].is_confirmed_eligible is True

    assert alts[2].scheme_id == id_ineligible_same_cat
    assert alts[2].is_confirmed_eligible is False
    assert alts[2].eligibility_result is False


def test_alternative_selection_by_persona():
    """Schemes sharing citizen target persona are suggested with clear reason."""
    id_target = uuid.uuid4()
    id_student_alt = uuid.uuid4()

    target_item = _make_item(
        id_target, "National Scholarship", eligibility_result=False,
        rule_match_score=50.0, scheme_category="EDUCATION", target_persona="STUDENT"
    )
    student_alt = _make_item(
        id_student_alt, "State Free Laptop", eligibility_result=False,
        rule_match_score=60.0, scheme_category="IT", target_persona="STUDENT"
    )

    alts = AlternativeSchemeService.find_alternatives_for_item(target_item, [target_item, student_alt])

    assert len(alts) == 1
    assert alts[0].scheme_id == id_student_alt
    assert "Student" in alts[0].suggestion_reason


def test_clearly_labeled_as_suggestions():
    """All suggestions are clearly labeled as suggestions with suggestion_reason."""
    id1 = uuid.uuid4()
    id2 = uuid.uuid4()

    ineligible = _make_item(id1, "Scheme A", eligibility_result=False, rule_match_score=40.0, scheme_category="ENERGY")
    alt = _make_item(id2, "Scheme B", eligibility_result=False, rule_match_score=70.0, scheme_category="ENERGY")

    alts = AlternativeSchemeService.find_alternatives_for_item(ineligible, [ineligible, alt])

    assert len(alts) == 1
    assert alts[0].suggestion_reason.startswith("Suggestion: ")


def test_attach_alternatives_in_place():
    """attach_alternatives_to_recommendations attaches alternative_schemes to ineligible items."""
    id_ineligible = uuid.uuid4()
    id_eligible = uuid.uuid4()

    ineligible_item = _make_item(id_ineligible, "Ineligible Scheme", eligibility_result=False, scheme_category="EDUCATION")
    eligible_item = _make_item(id_eligible, "Eligible Scheme", eligibility_result=True, scheme_category="EDUCATION")

    ineligible_list = [ineligible_item]
    eligible_list = [eligible_item]

    AlternativeSchemeService.attach_alternatives_to_recommendations(eligible_list, ineligible_list)

    assert hasattr(ineligible_item, "alternative_schemes")
    assert isinstance(ineligible_item.alternative_schemes, list)
    assert len(ineligible_item.alternative_schemes) == 1
    assert ineligible_item.alternative_schemes[0].scheme_id == id_eligible


def test_existing_eligibility_decisions_remain_unchanged():
    """Baseline PM-KISAN evaluation remains 100% deterministic and untouched."""
    engine = EligibilityEngine()

    citizen = CitizenMaster(
        citizen_type="FARMER",
        date_of_birth=date(1980, 1, 1),
    )
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

    assert result is True
    assert details["overall_result"] is True
    assert details["rule_match_score"] == 100.0
