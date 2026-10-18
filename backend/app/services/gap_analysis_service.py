"""
Eligibility Gap Analysis Service.

Analyzes deterministic evaluation details and scheme document readiness
to produce structured, citizen-friendly explanations of:
1. Failed Conditions: criteria where a citizen provided a value that did not satisfy the rule.
2. Missing Information: required criteria where the citizen profile has no value (None / not provided).
3. Document Gaps: mandatory documents required by the scheme that are not yet valid (missing or pending).

Preserves all deterministic eligibility outcomes, Rule Match Score, and ranking.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict


# Human-readable labels for eligibility parameters
PARAMETER_LABELS: Dict[str, str] = {
    "age": "Age",
    "gender": "Gender",
    "citizen_type": "Citizen type / category",
    "annual_income": "Annual family income",
    "poverty_category": "Poverty category / Ration card type",
    "land_holding_size": "Land holding size",
    "is_bpl_card_holder": "BPL card status",
    "is_income_tax_payer": "Income-tax payer status",
    "employment_status": "Employment status",
    "social_category": "Social / Caste category",
    "education_level": "Education level",
    "currently_studying": "Current student enrollment status",
    "disability_status": "Disability status",
    "area_type": "Area type (Rural/Urban)",
    "state": "State of residence",
    "tenth_percentage": "10th standard percentage",
    "twelfth_percentage": "12th standard percentage",
    "twelfth_percentile": "12th standard percentile",
    "livestock_cattle_count": "Cattle livestock count",
    "livestock_poultry_count": "Poultry livestock count",
}


def _format_value(val: Any) -> str:
    """Format actual/required value for citizen display."""
    if val is None:
        return "Not provided"
    if isinstance(val, bool):
        return "Yes" if val else "No"
    if isinstance(val, (int, float)):
        return f"{val:g}" if isinstance(val, float) else str(val)
    return str(val)


def _format_operator(op: str, required: Any) -> str:
    """Format operator and required value into plain text requirement."""
    req_str = _format_value(required)
    if op == "==":
        return f"Must be {req_str}"
    if op == "!=":
        return f"Must not be {req_str}"
    if op == "<=":
        return f"Must be at most {req_str}"
    if op == "<":
        return f"Must be less than {req_str}"
    if op == ">=":
        return f"Must be at least {req_str}"
    if op == ">":
        return f"Must be greater than {req_str}"
    if op == "IN":
        return f"Must be one of: {req_str}"
    return f"{op} {req_str}"


class FailedConditionGap(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    parameter: str
    parameter_label: str
    actual_value: Any
    actual_display: str
    required_value: str
    operator: str
    requirement_display: str
    rule_description: Optional[str] = None
    message: str


class MissingInformationGap(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    parameter: str
    parameter_label: str
    required_value: str
    operator: str
    requirement_display: str
    rule_description: Optional[str] = None
    message: str


class DocumentGap(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    document_type: str
    document_name: str
    status: str
    required: bool
    message: str


class SchemeGapAnalysis(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    has_gaps: bool
    summary_message: str
    failed_conditions: List[FailedConditionGap] = []
    missing_information: List[MissingInformationGap] = []
    missing_documents: List[DocumentGap] = []


class GapAnalysisService:
    @staticmethod
    def analyze_gaps(
        evaluation_details: Optional[Dict[str, Any]],
        scheme_documents: Optional[List[Dict[str, Any]]] = None,
        eligibility_result: bool = True,
    ) -> SchemeGapAnalysis:
        """
        Analyze gaps from evaluation details and scheme documents.
        """
        failed_conditions: List[FailedConditionGap] = []
        missing_info: List[MissingInformationGap] = []
        missing_docs: List[DocumentGap] = []

        has_rule_evaluation = False

        if evaluation_details and isinstance(evaluation_details, dict):
            groups = evaluation_details.get("groups")
            if isinstance(groups, list) and len(groups) > 0:
                has_rule_evaluation = True
                for group in groups:
                    rules = group.get("rules") or []
                    for r in rules:
                        if r.get("passed") is True:
                            continue

                        param = r.get("parameter") or "unknown"
                        label = PARAMETER_LABELS.get(param, param.replace("_", " ").title())
                        actual = r.get("actual")
                        required = r.get("required") if r.get("required") is not None else ""
                        op = r.get("operator") or "=="
                        desc = r.get("description")
                        req_display = _format_operator(op, required)
                        is_missing = r.get("is_missing") or (actual is None)

                        if is_missing:
                            # Missing profile information
                            msg = f"{label} is not provided in your profile. Requirement: {req_display}."
                            missing_info.append(
                                MissingInformationGap(
                                    parameter=param,
                                    parameter_label=label,
                                    required_value=str(required),
                                    operator=op,
                                    requirement_display=req_display,
                                    rule_description=desc,
                                    message=msg,
                                )
                            )
                        else:
                            # Failed condition with provided value
                            actual_display = _format_value(actual)
                            msg = f"{label} ({actual_display}) does not meet the requirement: {req_display}."
                            failed_conditions.append(
                                FailedConditionGap(
                                    parameter=param,
                                    parameter_label=label,
                                    actual_value=actual,
                                    actual_display=actual_display,
                                    required_value=str(required),
                                    operator=op,
                                    requirement_display=req_display,
                                    rule_description=desc,
                                    message=msg,
                                )
                            )

        # Document gaps analysis
        if scheme_documents and isinstance(scheme_documents, list):
            for doc in scheme_documents:
                # Handle dict or Pydantic model
                d_type = doc.get("document_type") if isinstance(doc, dict) else getattr(doc, "document_type", "")
                d_name = doc.get("name") if isinstance(doc, dict) else getattr(doc, "name", "")
                d_req = doc.get("required") if isinstance(doc, dict) else getattr(doc, "required", False)
                d_status = doc.get("status") if isinstance(doc, dict) else getattr(doc, "status", "MISSING")

                if d_req and d_status != "VALID":
                    if d_status == "MISSING":
                        msg = f"{d_name} has not been uploaded."
                    elif d_status == "INVALID":
                        msg = f"Uploaded {d_name} is invalid or incorrect document type."
                    elif d_status == "REVIEW_REQUIRED":
                        msg = f"Uploaded {d_name} requires verification review."
                    else:
                        msg = f"{d_name} is pending validation (status: {d_status})."

                    missing_docs.append(
                        DocumentGap(
                            document_type=d_type,
                            document_name=d_name or d_type.replace("_", " ").title(),
                            status=d_status,
                            required=d_req,
                            message=msg,
                        )
                    )

        has_gaps = bool(failed_conditions or missing_info or missing_docs)

        # Build overall citizen summary message
        if not has_rule_evaluation:
            if missing_docs:
                count = len(missing_docs)
                summary_message = f"Eligibility details are unavailable; {count} required document{'s' if count > 1 else ''} pending."
            else:
                summary_message = "Eligibility details are unavailable; gaps could not be fully assessed."
        elif not has_gaps:
            summary_message = "All eligibility criteria and required documents are satisfied."
        else:
            summary_parts = []
            if failed_conditions:
                count = len(failed_conditions)
                summary_parts.append(f"{count} condition{'s' if count > 1 else ''} not met")
            if missing_info:
                count = len(missing_info)
                summary_parts.append(f"{count} profile detail{'s' if count > 1 else ''} missing")
            if missing_docs:
                count = len(missing_docs)
                summary_parts.append(f"{count} required document{'s' if count > 1 else ''} pending")
            summary_message = "Gaps identified: " + ", ".join(summary_parts) + "."

        return SchemeGapAnalysis(
            has_gaps=has_gaps,
            summary_message=summary_message,
            failed_conditions=failed_conditions,
            missing_information=missing_info,
            missing_documents=missing_docs,
        )
