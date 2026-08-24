import pytest
from app.services.eligibility_engine import EligibilityEngine
from app.models.citizen import CitizenMaster, FinancialProfile
from app.models.scheme import SchemeMaster, SchemeRuleGroup, SchemeEligibilityRule
from datetime import date

def test_pm_kisan_eligibility():
    engine = EligibilityEngine()
    
    # Mock Citizen (Farmer, eligible)
    citizen = CitizenMaster(
        citizen_type="FARMER",
        date_of_birth=date(1980, 1, 1),
    )
    citizen.financial_profile = FinancialProfile(
        land_holding_size=1.5,
        is_income_tax_payer=False
    )
    
    # Mock Scheme (PM-KISAN)
    scheme = SchemeMaster(
        scheme_name="PM-KISAN",
        group_combining_operator="AND",
    )
    
    group1 = SchemeRuleGroup(group_name="Farmer", intra_group_operator="AND")
    group1.rules = [
        SchemeEligibilityRule(parameter_name="citizen_type", operator="==", required_value="FARMER"),
        SchemeEligibilityRule(parameter_name="land_holding_size", operator="<=", required_value="2.0")
    ]
    
    group2 = SchemeRuleGroup(group_name="Exclusion", intra_group_operator="AND")
    group2.rules = [
        SchemeEligibilityRule(parameter_name="is_income_tax_payer", operator="==", required_value="false")
    ]
    
    scheme.rule_groups = [group1, group2]
    
    result, details, reason = engine.evaluate_scheme(citizen, scheme)
    
    assert result is True
