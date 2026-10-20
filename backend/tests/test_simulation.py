import uuid
from datetime import date
import pytest

from app.models.citizen import CitizenMaster, FinancialProfile, DemographicProfile, LocationProfile
from app.models.profile_fact import ProfileFact
from app.models.scheme import SchemeMaster, SchemeRuleGroup, SchemeEligibilityRule
from app.schemas.simulation import SimulationInput
from app.services.eligibility_engine import EligibilityEngine
from app.services.simulation_service import SimulationService, SimulationEligibilityEngine


def _create_test_scheme_kisan() -> SchemeMaster:
    """PM-KISAN: FARMER, land_holding_size <= 2.0, is_income_tax_payer == false."""
    scheme = SchemeMaster(
        scheme_id=uuid.uuid4(),
        scheme_name="PM-KISAN",
        group_combining_operator="AND",
        target_persona="FARMER",
        scheme_category="AGRICULTURE",
    )
    group1 = SchemeRuleGroup(group_name="Farmer Criteria", intra_group_operator="AND")
    group1.rules = [
        SchemeEligibilityRule(parameter_name="citizen_type", operator="==", required_value="FARMER", rule_description="Must be a Farmer"),
        SchemeEligibilityRule(parameter_name="land_holding_size", operator="<=", required_value="2.0", rule_description="Land holding at most 2 ha"),
    ]
    group2 = SchemeRuleGroup(group_name="Exclusion Criteria", intra_group_operator="AND")
    group2.rules = [
        SchemeEligibilityRule(parameter_name="is_income_tax_payer", operator="==", required_value="false", rule_description="Must not pay income tax"),
    ]
    scheme.rule_groups = [group1, group2]
    return scheme


def _create_test_scheme_scholarship() -> SchemeMaster:
    """Scholarship: STUDENT, annual_income <= 250000, tenth_percentage >= 75."""
    scheme = SchemeMaster(
        scheme_id=uuid.uuid4(),
        scheme_name="Merit Scholarship",
        group_combining_operator="AND",
        target_persona="STUDENT",
        scheme_category="EDUCATION",
    )
    group = SchemeRuleGroup(group_name="Eligibility", intra_group_operator="AND")
    group.rules = [
        SchemeEligibilityRule(parameter_name="citizen_type", operator="==", required_value="STUDENT", rule_description="Must be a Student"),
        SchemeEligibilityRule(parameter_name="annual_income", operator="<=", required_value="250000", rule_description="Family income <= 2.5L"),
        SchemeEligibilityRule(parameter_name="tenth_percentage", operator=">=", required_value="75", rule_description="10th marks >= 75%"),
    ]
    scheme.rule_groups = [group]
    return scheme


def test_simulation_improves_outcome_to_eligible():
    """Citizen initially ineligible due to land holding becomes eligible when land <= 2.0."""
    citizen = CitizenMaster(
        citizen_id=uuid.uuid4(),
        citizen_type="FARMER",
        date_of_birth=date(1985, 1, 1),
    )
    citizen.financial_profile = FinancialProfile(
        land_holding_size=3.5,  # Ineligible (> 2.0)
        is_income_tax_payer=False,
    )
    scheme = _create_test_scheme_kisan()

    # Simulate hypothetical land holding size of 1.5
    sim_input = SimulationInput(land_holding_size=1.5)
    resp = SimulationService.simulate_citizen_eligibility(
        citizen=citizen,
        schemes=[scheme],
        simulation_input=sim_input,
    )

    assert resp.total_schemes_evaluated == 1
    assert resp.newly_eligible_count == 1
    assert resp.newly_ineligible_count == 0

    res = resp.simulated_schemes[0]
    assert res.baseline_eligible is False
    assert res.simulated_eligible is True
    assert res.outcome_change == "BECAME_ELIGIBLE"
    assert "would now be eligible" in res.summary_explanation.lower()
    assert len(res.changed_conditions) >= 1
    land_delta = next(c for c in res.changed_conditions if c.parameter == "land_holding_size")
    assert land_delta.status == "IMPROVED"
    assert land_delta.baseline_passed is False
    assert land_delta.simulated_passed is True
    assert land_delta.baseline_value == 3.5
    assert land_delta.simulated_value == 1.5


def test_simulation_worsens_outcome_to_ineligible():
    """Citizen initially eligible becomes ineligible when hypothetical income tax payer is True."""
    citizen = CitizenMaster(
        citizen_id=uuid.uuid4(),
        citizen_type="FARMER",
        date_of_birth=date(1985, 1, 1),
    )
    citizen.financial_profile = FinancialProfile(
        land_holding_size=1.5,
        is_income_tax_payer=False,  # Eligible
    )
    scheme = _create_test_scheme_kisan()

    sim_input = SimulationInput(is_income_tax_payer=True)
    resp = SimulationService.simulate_citizen_eligibility(
        citizen=citizen,
        schemes=[scheme],
        simulation_input=sim_input,
    )

    assert resp.newly_ineligible_count == 1
    assert resp.newly_eligible_count == 0

    res = resp.simulated_schemes[0]
    assert res.baseline_eligible is True
    assert res.simulated_eligible is False
    assert res.outcome_change == "BECAME_INELIGIBLE"
    assert "no longer qualify" in res.summary_explanation.lower()
    tax_delta = next(c for c in res.changed_conditions if c.parameter == "is_income_tax_payer")
    assert tax_delta.status == "WORSENED"
    assert tax_delta.baseline_passed is True
    assert tax_delta.simulated_passed is False


def test_simulation_score_improves_without_eligibility():
    """Missing condition provided improves Rule Match Score from 33.3% to 66.7%."""
    citizen = CitizenMaster(
        citizen_id=uuid.uuid4(),
        citizen_type="STUDENT",
        date_of_birth=date(2005, 1, 1),
    )
    citizen.financial_profile = FinancialProfile(
        annual_income=400000.0,  # Fails income rule (> 250000)
    )
    # tenth_percentage is missing in baseline profile
    scheme = _create_test_scheme_scholarship()

    # Simulate supplying tenth_percentage = 80.0
    sim_input = SimulationInput(tenth_percentage=80.0)
    resp = SimulationService.simulate_citizen_eligibility(
        citizen=citizen,
        schemes=[scheme],
        simulation_input=sim_input,
    )

    res = resp.simulated_schemes[0]
    assert res.baseline_eligible is False
    assert res.simulated_eligible is False
    assert res.outcome_change == "SCORE_IMPROVED"
    assert res.simulated_match_score > res.baseline_match_score
    assert "improved by" in res.summary_explanation.lower()


def test_simulation_unchanged_outcome():
    """Unchanged input returns UNCHANGED outcome with accurate match score."""
    citizen = CitizenMaster(
        citizen_id=uuid.uuid4(),
        citizen_type="FARMER",
        date_of_birth=date(1985, 1, 1),
    )
    citizen.financial_profile = FinancialProfile(
        land_holding_size=1.5,
        is_income_tax_payer=False,
    )
    scheme = _create_test_scheme_kisan()

    # Overriding with irrelevant state does not affect PM-KISAN
    sim_input = SimulationInput(state="Maharashtra")
    resp = SimulationService.simulate_citizen_eligibility(
        citizen=citizen,
        schemes=[scheme],
        simulation_input=sim_input,
    )

    res = resp.simulated_schemes[0]
    assert res.baseline_eligible is True
    assert res.simulated_eligible is True
    assert res.outcome_change == "UNCHANGED"
    assert "remain fully eligible" in res.summary_explanation.lower()


def test_no_persistence_or_side_effects():
    """Simulated changes NEVER mutate citizen attributes or sub-profiles."""
    original_land = 4.0
    original_tax = False
    citizen = CitizenMaster(
        citizen_id=uuid.uuid4(),
        citizen_type="FARMER",
        date_of_birth=date(1985, 1, 1),
    )
    citizen.financial_profile = FinancialProfile(
        land_holding_size=original_land,
        is_income_tax_payer=original_tax,
    )
    scheme = _create_test_scheme_kisan()

    sim_input = SimulationInput(
        land_holding_size=1.0,
        is_income_tax_payer=True,
        citizen_type="STUDENT",
    )
    SimulationService.simulate_citizen_eligibility(
        citizen=citizen,
        schemes=[scheme],
        simulation_input=sim_input,
    )

    # Assert citizen profile strictly remains intact
    assert citizen.financial_profile.land_holding_size == original_land
    assert citizen.financial_profile.is_income_tax_payer == original_tax
    assert citizen.citizen_type == "FARMER"


def test_empty_schemes_and_empty_inputs_handled_safely():
    """Safe execution on empty scheme list and empty simulation inputs."""
    citizen = CitizenMaster(
        citizen_id=uuid.uuid4(),
        citizen_type="GENERAL",
        date_of_birth=date(1990, 1, 1),
    )

    # Empty schemes
    resp_empty = SimulationService.simulate_citizen_eligibility(
        citizen=citizen,
        schemes=[],
        simulation_input=SimulationInput(),
    )
    assert resp_empty.total_schemes_evaluated == 0
    assert resp_empty.simulated_schemes == []
    assert "no net impact" in resp_empty.overall_summary.lower()

    # Empty input with active scheme
    scheme = _create_test_scheme_kisan()
    resp_no_input = SimulationService.simulate_citizen_eligibility(
        citizen=citizen,
        schemes=[scheme],
        simulation_input=SimulationInput(),
    )
    assert resp_no_input.total_schemes_evaluated == 1
    assert resp_no_input.simulated_schemes[0].outcome_change == "UNCHANGED"


def test_baseline_deterministic_eligibility_engine_untouched():
    """Core baseline PM-KISAN evaluation remains 100% deterministic and unaffected."""
    engine = EligibilityEngine()
    citizen = CitizenMaster(
        citizen_type="FARMER",
        date_of_birth=date(1980, 1, 1),
    )
    citizen.financial_profile = FinancialProfile(
        land_holding_size=1.5,
        is_income_tax_payer=False,
    )
    scheme = _create_test_scheme_kisan()

    result, details, reason = engine.evaluate_scheme(citizen, scheme)
    assert result is True
    assert details["overall_result"] is True
    assert details["rule_match_score"] == 100.0


def test_condition_delta_handles_duplicate_parameter_and_description_rules():
    """Rules in the same group with identical parameter and description do not collide."""
    scheme = SchemeMaster(
        scheme_id=uuid.uuid4(),
        scheme_name="Range Scheme",
        group_combining_operator="AND",
    )
    # Group with two rules for annual_income with identical description (e.g. bounded range)
    group = SchemeRuleGroup(group_name="Income Range", intra_group_operator="AND")
    group.rules = [
        SchemeEligibilityRule(
            parameter_name="annual_income",
            operator=">=",
            required_value="100000",
            rule_description="Annual income requirement",
        ),
        SchemeEligibilityRule(
            parameter_name="annual_income",
            operator="<=",
            required_value="300000",
            rule_description="Annual income requirement",
        ),
    ]
    scheme.rule_groups = [group]

    citizen = CitizenMaster(
        citizen_id=uuid.uuid4(),
        date_of_birth=date(1990, 1, 1),
    )
    citizen.financial_profile = FinancialProfile(
        annual_income=50000.0,  # Fails first rule (>= 100000), passes second (<= 300000)
    )

    # Simulate hypothetical income of 200000 (passes both)
    sim_input = SimulationInput(annual_income=200000.0)
    resp = SimulationService.simulate_citizen_eligibility(
        citizen=citizen,
        schemes=[scheme],
        simulation_input=sim_input,
    )

    res = resp.simulated_schemes[0]
    assert res.baseline_eligible is False
    assert res.simulated_eligible is True
    assert res.outcome_change == "BECAME_ELIGIBLE"

    # Both rules saw annual_income change from 50000.0 to 200000.0
    assert len(res.changed_conditions) == 2
    delta0 = res.changed_conditions[0]
    assert delta0.parameter == "annual_income"
    assert delta0.status == "IMPROVED"
    assert delta0.baseline_passed is False
    assert delta0.simulated_passed is True
    assert delta0.baseline_value == 50000.0
    assert delta0.simulated_value == 200000.0

    delta1 = res.changed_conditions[1]
    assert delta1.parameter == "annual_income"
    assert delta1.status == "UNCHANGED"
    assert delta1.baseline_passed is True
    assert delta1.simulated_passed is True
    assert delta1.baseline_value == 50000.0
    assert delta1.simulated_value == 200000.0


def test_simulation_with_facts_dict_preserves_non_overridden_facts():
    """
    Simulating with facts_dict ensures non-overridden parameters resolve from
    authoritative profile facts, while overrides take effect as expected.
    """
    citizen = CitizenMaster(
        citizen_id=uuid.uuid4(),
        citizen_type="STUDENT",
        date_of_birth=date(2000, 1, 1),
    )
    # Profile facts: student has high income (fails) and tenth_percentage (passes)
    facts_dict = {
        "ANNUAL_INCOME": "400000",
        "TENTH_PERCENTAGE": "85.0",
        "AGE": "24",
    }
    scheme = _create_test_scheme_scholarship()

    # Simulate hypothetical income of 180000 (qualifies)
    sim_input = SimulationInput(annual_income=180000.0)
    resp = SimulationService.simulate_citizen_eligibility(
        citizen=citizen,
        schemes=[scheme],
        simulation_input=sim_input,
        facts_dict=facts_dict,
    )

    res = resp.simulated_schemes[0]
    # Baseline failed because annual_income was 400000 from facts_dict
    assert res.baseline_eligible is False
    # Simulation succeeded because income override (180000) applied and tenth_percentage (85.0) resolved from facts_dict
    assert res.simulated_eligible is True
    assert res.outcome_change == "BECAME_ELIGIBLE"

    income_delta = next(c for c in res.changed_conditions if c.parameter == "annual_income")
    assert income_delta.baseline_value == 400000.0
    assert income_delta.simulated_value == 180000.0
    assert income_delta.status == "IMPROVED"


def test_simulation_override_takes_precedence_over_stored_facts():
    """Explicit hypothetical override strictly takes precedence over facts_dict."""
    citizen = CitizenMaster(
        citizen_id=uuid.uuid4(),
        citizen_type="GENERAL",
        date_of_birth=date(1980, 1, 1),
    )
    facts_dict = {
        "ANNUAL_INCOME": "500000",
        "AGE": "45",
        "LAND_HOLDING_SIZE": "5.0",
    }
    engine = SimulationEligibilityEngine(
        overrides={"annual_income": 120000.0, "age": 22},
        facts_dict=facts_dict,
    )

    # Overridden parameters return override value
    assert engine._resolve_parameter(citizen, "annual_income", facts_dict=facts_dict) == 120000.0
    assert engine._resolve_parameter(citizen, "age", facts_dict=facts_dict) == 22

    # Non-overridden parameter resolves from facts_dict
    assert engine._resolve_parameter(citizen, "land_holding_size", facts_dict=facts_dict) == 5.0


def test_simulation_engine_resolve_parameter_signature_no_type_error():
    """
    SimulationEligibilityEngine._resolve_parameter accepts facts_dict keyword argument
    directly without raising TypeError.
    """
    citizen = CitizenMaster(citizen_id=uuid.uuid4())
    facts = {"AGE": "28"}
    engine = SimulationEligibilityEngine(overrides={}, facts_dict=facts)

    # Calling with facts_dict kwarg must succeed
    val = engine._resolve_parameter(citizen, "age", facts_dict=facts)
    assert val == 28

    # Calling without facts_dict kwarg must fall back to engine.facts_dict
    val_default = engine._resolve_parameter(citizen, "age")
    assert val_default == 28


def test_simulation_fallback_to_citizen_profile_facts_if_facts_dict_omitted():
    """
    When facts_dict is omitted, SimulationService extracts active facts from
    citizen.profile_facts if loaded on the instance.
    """
    citizen = CitizenMaster(
        citizen_id=uuid.uuid4(),
        citizen_type="STUDENT",
        date_of_birth=date(2002, 5, 20),
    )
    citizen.profile_facts = [
        ProfileFact(
            fact_id=uuid.uuid4(),
            citizen_id=citizen.citizen_id,
            fact_code="TENTH_PERCENTAGE",
            fact_value="88.0",
            effective_until=None,
        ),
        ProfileFact(
            fact_id=uuid.uuid4(),
            citizen_id=citizen.citizen_id,
            fact_code="ANNUAL_INCOME",
            fact_value="500000",
            effective_until=None,
        ),
    ]
    scheme = _create_test_scheme_scholarship()

    sim_input = SimulationInput(annual_income=200000.0)
    resp = SimulationService.simulate_citizen_eligibility(
        citizen=citizen,
        schemes=[scheme],
        simulation_input=sim_input,
        # facts_dict omitted
    )

    res = resp.simulated_schemes[0]
    assert res.baseline_eligible is False
    assert res.simulated_eligible is True
    assert res.outcome_change == "BECAME_ELIGIBLE"

