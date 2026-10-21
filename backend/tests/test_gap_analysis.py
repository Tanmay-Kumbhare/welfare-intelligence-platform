import uuid
from datetime import date
import pytest

from app.models.citizen import CitizenMaster, FinancialProfile
from app.models.scheme import SchemeMaster, SchemeRuleGroup, SchemeEligibilityRule
from app.services.eligibility_engine import EligibilityEngine
from app.services.gap_analysis_service import GapAnalysisService


def test_eligible_scheme_no_gaps():
    """Eligible scheme with satisfied rules and valid documents has has_gaps=False."""
    eval_details = {
        "overall_result": True,
        "rule_match_score": 100.0,
        "groups": [
            {
                "group_name": "General Criteria",
                "rules": [
                    {
                        "parameter": "age",
                        "actual": 25,
                        "required": "18",
                        "operator": ">=",
                        "passed": True,
                        "is_missing": False,
                    }
                ],
            }
        ],
    }
    scheme_docs = [
        {"document_type": "AADHAAR", "name": "Aadhaar Card", "required": True, "status": "VALID"}
    ]

    analysis = GapAnalysisService.analyze_gaps(
        evaluation_details=eval_details,
        scheme_documents=scheme_docs,
        eligibility_result=True,
    )

    assert analysis.has_gaps is False
    assert len(analysis.failed_conditions) == 0
    assert len(analysis.missing_information) == 0
    assert len(analysis.missing_documents) == 0
    assert "satisfied" in analysis.summary_message.lower()


def test_failed_condition_with_actual_and_required():
    """Failed rule correctly populates FailedConditionGap with formatted values and readable message."""
    eval_details = {
        "overall_result": False,
        "rule_match_score": 0.0,
        "groups": [
            {
                "group_name": "Land Holding",
                "rules": [
                    {
                        "parameter": "land_holding_size",
                        "actual": 3.5,
                        "required": "2.0",
                        "operator": "<=",
                        "passed": False,
                        "is_missing": False,
                        "description": "Land holding must not exceed 2.0 hectares",
                    }
                ],
            }
        ],
    }

    analysis = GapAnalysisService.analyze_gaps(evaluation_details=eval_details)

    assert analysis.has_gaps is True
    assert len(analysis.failed_conditions) == 1
    assert len(analysis.missing_information) == 0
    assert len(analysis.missing_documents) == 0

    gap = analysis.failed_conditions[0]
    assert gap.parameter == "land_holding_size"
    assert gap.parameter_label == "Land holding size"
    assert gap.actual_value == 3.5
    assert gap.actual_display == "3.5"
    assert gap.operator == "<="
    assert gap.requirement_display == "Must be at most 2.0"
    assert "does not meet the requirement" in gap.message


def test_missing_profile_information_gap():
    """Rule with actual=None / is_missing=True is classified as MissingInformationGap, not FailedConditionGap."""
    eval_details = {
        "overall_result": False,
        "rule_match_score": 0.0,
        "groups": [
            {
                "group_name": "Category",
                "rules": [
                    {
                        "parameter": "social_category",
                        "actual": None,
                        "required": "SC",
                        "operator": "==",
                        "passed": False,
                        "is_missing": True,
                        "description": "Must belong to SC category",
                    }
                ],
            }
        ],
    }

    analysis = GapAnalysisService.analyze_gaps(evaluation_details=eval_details)

    assert analysis.has_gaps is True
    assert len(analysis.failed_conditions) == 0
    assert len(analysis.missing_information) == 1

    gap = analysis.missing_information[0]
    assert gap.parameter == "social_category"
    assert gap.parameter_label == "Social / Caste category"
    assert gap.required_value == "SC"
    assert gap.operator == "=="
    assert gap.requirement_display == "Must be SC"
    assert "not provided in your profile" in gap.message


def test_missing_mandatory_documents_gap():
    """Mandatory documents that are MISSING or not VALID are captured in missing_documents."""
    eval_details = {"overall_result": True, "groups": []}
    scheme_docs = [
        {"document_type": "AADHAAR", "name": "Aadhaar Card", "required": True, "status": "MISSING"},
        {"document_type": "INCOME_CERTIFICATE", "name": "Income Certificate", "required": True, "status": "INVALID"},
        {"document_type": "OPTIONAL_DOC", "name": "Optional Doc", "required": False, "status": "MISSING"},
    ]

    analysis = GapAnalysisService.analyze_gaps(
        evaluation_details=eval_details,
        scheme_documents=scheme_docs,
        eligibility_result=True,
    )

    assert analysis.has_gaps is True
    assert len(analysis.missing_documents) == 2
    doc_types = [d.document_type for d in analysis.missing_documents]
    assert "AADHAAR" in doc_types
    assert "INCOME_CERTIFICATE" in doc_types
    assert "OPTIONAL_DOC" not in doc_types  # Optional docs do not produce blocking gaps


def test_multiple_simultaneous_gaps():
    """Detects failed condition, missing profile info, and missing document simultaneously."""
    eval_details = {
        "overall_result": False,
        "groups": [
            {
                "group_name": "Income & Age",
                "rules": [
                    {
                        "parameter": "annual_income",
                        "actual": 350000.0,
                        "required": "200000",
                        "operator": "<=",
                        "passed": False,
                        "is_missing": False,
                    },
                    {
                        "parameter": "age",
                        "actual": None,
                        "required": "18",
                        "operator": ">=",
                        "passed": False,
                        "is_missing": True,
                    },
                ],
            }
        ],
    }
    scheme_docs = [
        {"document_type": "RATION_CARD", "name": "Ration Card", "required": True, "status": "MISSING"}
    ]

    analysis = GapAnalysisService.analyze_gaps(
        evaluation_details=eval_details,
        scheme_documents=scheme_docs,
        eligibility_result=False,
    )

    assert analysis.has_gaps is True
    assert len(analysis.failed_conditions) == 1
    assert len(analysis.missing_information) == 1
    assert len(analysis.missing_documents) == 1
    assert "1 condition not met" in analysis.summary_message
    assert "1 profile detail missing" in analysis.summary_message
    assert "1 required document pending" in analysis.summary_message


def test_empty_evaluation_details():
    """None or empty evaluation_details does not claim all criteria are satisfied, but returns a truthful summary."""
    analysis = GapAnalysisService.analyze_gaps(evaluation_details=None, scheme_documents=None)
    assert analysis.has_gaps is False
    assert analysis.failed_conditions == []
    assert analysis.missing_information == []
    assert analysis.missing_documents == []
    assert "Eligibility details are unavailable" in analysis.summary_message

    # Empty dictionary or empty groups
    analysis_dict = GapAnalysisService.analyze_gaps(evaluation_details={}, scheme_documents=None)
    assert "Eligibility details are unavailable" in analysis_dict.summary_message

    analysis_empty_groups = GapAnalysisService.analyze_gaps(evaluation_details={"groups": []}, scheme_documents=None)
    assert "Eligibility details are unavailable" in analysis_empty_groups.summary_message


def test_required_value_zero_preserved():
    """Required value 0 is preserved in requirement display rather than treated as empty."""
    eval_details = {
        "overall_result": False,
        "groups": [
            {
                "group_name": "Livestock",
                "rules": [
                    {
                        "parameter": "livestock_cattle_count",
                        "actual": 2,
                        "required": 0,
                        "operator": "==",
                        "passed": False,
                        "is_missing": False,
                    }
                ],
            }
        ],
    }

    analysis = GapAnalysisService.analyze_gaps(evaluation_details=eval_details)
    assert len(analysis.failed_conditions) == 1
    gap = analysis.failed_conditions[0]
    assert gap.required_value == "0"
    assert gap.requirement_display == "Must be 0"
    assert "Must be 0" in gap.message


def test_required_value_false_preserved():
    """Required value False is preserved in requirement display rather than treated as empty."""
    eval_details = {
        "overall_result": False,
        "groups": [
            {
                "group_name": "Tax Exclusion",
                "rules": [
                    {
                        "parameter": "is_income_tax_payer",
                        "actual": True,
                        "required": False,
                        "operator": "==",
                        "passed": False,
                        "is_missing": False,
                    }
                ],
            }
        ],
    }

    analysis = GapAnalysisService.analyze_gaps(evaluation_details=eval_details)
    assert len(analysis.failed_conditions) == 1
    gap = analysis.failed_conditions[0]
    assert gap.required_value == "False"
    assert gap.requirement_display == "Must be No"
    assert "Must be No" in gap.message


def test_deterministic_explanations():
    """Identical gap inputs produce identical structured outputs and messages."""
    eval_details = {
        "groups": [
            {
                "rules": [
                    {
                        "parameter": "annual_income",
                        "actual": 500000.0,
                        "required": "250000",
                        "operator": "<=",
                        "passed": False,
                        "is_missing": False,
                    }
                ]
            }
        ]
    }
    a1 = GapAnalysisService.analyze_gaps(evaluation_details=eval_details)
    a2 = GapAnalysisService.analyze_gaps(evaluation_details=eval_details)

    assert a1.model_dump() == a2.model_dump()
    assert a1.summary_message == a2.summary_message


def test_existing_eligibility_decisions_remain_unchanged():
    """PM-KISAN baseline evaluation and result remain strictly deterministic and unchanged."""
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

    # Gap analysis on this eligible result should show no gaps
    gap_result = GapAnalysisService.analyze_gaps(evaluation_details=details, eligibility_result=result)
    assert gap_result.has_gaps is False


def test_gap_analysis_all_mandatory_documents_satisfied():
    """All mandatory scheme documents satisfied with VALID status results in has_gaps=False."""
    eval_details = {
        "overall_result": True,
        "rule_match_score": 100.0,
        "groups": [
            {
                "group_name": "Criteria",
                "rules": [
                    {
                        "parameter": "citizen_type",
                        "actual": "FARMER",
                        "required": "FARMER",
                        "operator": "==",
                        "passed": True,
                        "is_missing": False,
                    }
                ],
            }
        ],
    }
    scheme_docs = [
        {"document_type": "AADHAAR", "name": "Aadhaar Card", "required": True, "status": "VALID"},
        {"document_type": "BANK_PASSBOOK", "name": "Bank Passbook", "required": True, "status": "VALID"},
        {"document_type": "INCOME_CERTIFICATE", "name": "Income Certificate", "required": False, "status": "MISSING"},
    ]

    analysis = GapAnalysisService.analyze_gaps(
        evaluation_details=eval_details,
        scheme_documents=scheme_docs,
        eligibility_result=True,
    )

    assert analysis.has_gaps is False
    assert len(analysis.missing_documents) == 0
    assert "All eligibility criteria and required documents are satisfied" in analysis.summary_message


def test_gap_analysis_unsatisfied_document_statuses_and_messages():
    """Unsatisfied documents with various statuses (MISSING, INVALID, REVIEW_REQUIRED, PENDING) are structured properly."""
    eval_details = {
        "overall_result": True,
        "rule_match_score": 100.0,
        "groups": [
            {
                "group_name": "Criteria",
                "rules": [
                    {
                        "parameter": "age",
                        "actual": 30,
                        "required": "18",
                        "operator": ">=",
                        "passed": True,
                        "is_missing": False,
                    }
                ],
            }
        ],
    }
    scheme_docs = [
        {"document_type": "AADHAAR", "name": "Aadhaar Card", "required": True, "status": "MISSING"},
        {"document_type": "BANK_PASSBOOK", "name": "Bank Passbook", "required": True, "status": "INVALID"},
        {"document_type": "MARKSHEET", "name": "Marksheet", "required": True, "status": "REVIEW_REQUIRED"},
        {"document_type": "DOMICILE_CERTIFICATE", "name": "Domicile Certificate", "required": True, "status": "PENDING"},
        {"document_type": "PHOTOGRAPH", "name": "Photograph", "required": False, "status": "MISSING"},
    ]

    analysis = GapAnalysisService.analyze_gaps(
        evaluation_details=eval_details,
        scheme_documents=scheme_docs,
        eligibility_result=True,
    )

    assert analysis.has_gaps is True
    assert len(analysis.missing_documents) == 4

    missing_map = {d.document_type: d for d in analysis.missing_documents}
    assert missing_map["AADHAAR"].message == "Aadhaar Card has not been uploaded."
    assert missing_map["BANK_PASSBOOK"].message == "Uploaded Bank Passbook is invalid or incorrect document type."
    assert missing_map["MARKSHEET"].message == "Uploaded Marksheet requires verification review."
    assert missing_map["DOMICILE_CERTIFICATE"].message == "Domicile Certificate is pending validation (status: PENDING)."
    assert "PHOTOGRAPH" not in missing_map
