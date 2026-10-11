"""
Profile Conflict and Stale Fact Auditor Service (Phase 6).

Audits citizen profile attributes, profile facts, document verification states,
and historical provenance to detect:
1. Confirmed Conflicts: Mutually exclusive facts/values across profiles and facts.
2. Possible Conflicts: Self-reported updates that conflict with verified facts or document classes.
3. Stale Facts: Time-sensitive facts exceeding standard validity windows.
4. Missing Information: Key welfare eligibility attributes that have not been provided.

Invariants:
1. Pure read-only auditor: Never modifies, deletes, or reconciles profile facts,
   citizen profiles, documents, or assessments.
2. Explainability: Plainly articulates what is conflicting or stale, cites timestamps
   and sources, and maps potential impacts onto relevant schemes.
3. Truth in uncertainty: Clearly differentiates confirmed conflicts from possible conflicts,
   stale facts, and missing information.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set

from app.models.citizen import CitizenMaster
from app.models.document import CitizenDocument
from app.models.profile_fact import ProfileFact
from app.models.scheme import SchemeMaster
from app.schemas.profile_audit import (
    FactSourceEvidence,
    ProfileAuditIssue,
    ProfileAuditResponse,
    ProfileAuditSummary,
)
from app.services.gap_analysis_service import PARAMETER_LABELS
from app.utils.date_calc import calculate_age

# Operational system default thresholds (in days) after which time-sensitive facts
# are audited as potentially stale.
# NOTE: These thresholds represent operational system guidelines for document freshness
# and renewal cycles (e.g. annual financial declaration cycles), and are not
# statutory legal validity periods unless explicitly mandated by official scheme rules.
STALE_THRESHOLDS_DAYS: Dict[str, int] = {
    "ANNUAL_INCOME": 365,      # Income certificates / declarations: 1 year operational guideline
    "MONTHLY_INCOME": 180,     # Salary slips / declarations: 6 months operational guideline
    "LAND_HOLDING": 730,       # Land records: typically updated biannually (2 years)
    "EMPLOYMENT_STATUS": 365,  # Employment status can change annually
}

# Generalized potential-impact guidance categories used ONLY when no active scheme catalogue
# is provided or when no active evaluated schemes reference the specific parameter.
FALLBACK_SCHEME_IMPACT_CATEGORIES: Dict[str, List[str]] = {
    "annual_income": ["Potential Impact: Means-tested and income-gated welfare schemes"],
    "ANNUAL_INCOME": ["Potential Impact: Means-tested and income-gated welfare schemes"],
    "land_holding_size": ["Potential Impact: Farmer land-holding threshold welfare schemes"],
    "LAND_HOLDING": ["Potential Impact: Farmer land-holding threshold welfare schemes"],
    "citizen_type": ["Potential Impact: Persona-specific schemes (Farmer, Student, Senior)"],
    "is_income_tax_payer": ["Potential Impact: Income-tax payer excluded welfare schemes"],
    "is_bpl_card_holder": ["Potential Impact: BPL and poverty-gated ration/subsidy schemes"],
    "age": ["Potential Impact: Age-gated schemes (Old-age pensions, youth scholarships)"],
    "AGE": ["Potential Impact: Age-gated schemes (Old-age pensions, youth scholarships)"],
    "disability_status": ["Potential Impact: Disability welfare and assistive equipment schemes"],
    "DISABILITY_STATUS": ["Potential Impact: Disability welfare and assistive equipment schemes"],
    "tenth_percentage": ["Potential Impact: Merit-based academic scholarships"],
    "TENTH_PERCENTAGE": ["Potential Impact: Merit-based academic scholarships"],
}


class ProfileAuditService:
    """Orchestrates comprehensive profile conflict and stale fact auditing."""

    @staticmethod
    def audit_citizen_profile(
        citizen: CitizenMaster,
        schemes: Optional[Sequence[SchemeMaster]] = None,
        documents: Optional[Sequence[CitizenDocument]] = None,
        as_of: Optional[datetime] = None,
    ) -> ProfileAuditResponse:
        """
        Audits a citizen profile for conflicting, stale, or missing information.
        """
        now = as_of or datetime.now(timezone.utc)
        issues: List[ProfileAuditIssue] = []

        # Build lookup of active schemes and rules by parameter
        param_to_schemes: Dict[str, Set[str]] = {}
        if schemes:
            for s in schemes:
                for g in getattr(s, "rule_groups", []):
                    for r in getattr(g, "rules", []):
                        param = r.parameter_name.lower()
                        param_to_schemes.setdefault(param, set()).add(s.scheme_name)

        facts_list = getattr(citizen, "profile_facts", None) or []
        docs_list = list(documents or [])

        # 1. Audit Cross-Source Profile vs Profile Fact Conflicts
        issues.extend(ProfileAuditService._check_profile_vs_fact_conflicts(citizen, facts_list, param_to_schemes))

        # 2. Audit Document Verification and Mismatch Conflicts
        issues.extend(ProfileAuditService._check_document_conflicts(citizen, docs_list, param_to_schemes))

        # 3. Audit Stale Profile Facts
        issues.extend(ProfileAuditService._check_stale_facts(facts_list, now, param_to_schemes))

        # 4. Audit Critical Missing Information
        issues.extend(ProfileAuditService._check_missing_information(citizen, facts_list, param_to_schemes))

        # Sort issues deterministically by severity (HIGH -> MEDIUM -> LOW) then attribute
        severity_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        issues.sort(key=lambda i: (severity_rank.get(i.severity, 9), i.attribute_name, i.issue_type))

        # Tally summary metrics
        confirmed = sum(1 for i in issues if i.issue_type == "CONFIRMED_CONFLICT")
        possible = sum(1 for i in issues if i.issue_type == "POSSIBLE_CONFLICT")
        stale = sum(1 for i in issues if i.issue_type == "STALE_FACT")
        missing = sum(1 for i in issues if i.issue_type == "MISSING_INFORMATION")

        is_healthy = (confirmed == 0 and possible == 0)
        summary_msg = ProfileAuditService._format_summary_message(
            confirmed=confirmed, possible=possible, stale=stale, missing=missing
        )

        summary = ProfileAuditSummary(
            total_issues=len(issues),
            confirmed_conflicts_count=confirmed,
            possible_conflicts_count=possible,
            stale_facts_count=stale,
            missing_information_count=missing,
            is_healthy=is_healthy,
            summary_message=summary_msg,
        )

        return ProfileAuditResponse(
            citizen_id=citizen.citizen_id,
            audited_at=now,
            summary=summary,
            issues=issues,
        )

    @staticmethod
    def _resolve_affected_schemes(parameter: str, param_to_schemes: Dict[str, Set[str]]) -> List[str]:
        """
        Returns dynamically discovered schemes whose rules reference the parameter.
        Only if no active evaluated schemes reference the parameter does it return
        clearly labeled potential-impact guidance categories.
        """
        param_key = parameter.lower()
        if param_to_schemes and param_key in param_to_schemes:
            discovered = sorted(list(param_to_schemes[param_key]))
            if discovered:
                return discovered

        # Fallback to clearly labeled guidance category if no active evaluated schemes matched
        fallback = FALLBACK_SCHEME_IMPACT_CATEGORIES.get(parameter) or FALLBACK_SCHEME_IMPACT_CATEGORIES.get(param_key)
        return list(fallback) if fallback else []

    @staticmethod
    def _check_profile_vs_fact_conflicts(
        citizen: CitizenMaster,
        facts: List[ProfileFact],
        param_to_schemes: Dict[str, Set[str]],
    ) -> List[ProfileAuditIssue]:
        issues = []
        open_facts_by_code: Dict[str, ProfileFact] = {}
        for f in facts:
            if getattr(f, "effective_until", None) is None:
                open_facts_by_code[f.fact_code] = f

        # Check Income Conflict (Financial Profile vs Fact Layer)
        fact_inc = open_facts_by_code.get("ANNUAL_INCOME")
        fin = getattr(citizen, "financial_profile", None)
        if fact_inc and fin and fin.annual_income is not None:
            try:
                fact_val = float(fact_inc.fact_value)
                prof_val = float(fin.annual_income)
                if abs(fact_val - prof_val) > 1.0:
                    sources = [
                        FactSourceEvidence(
                            source_type="PROFILE_RECORD",
                            source_reference="financial_profile.annual_income",
                            value=prof_val,
                            verified=False,
                        ),
                        FactSourceEvidence(
                            source_type=fact_inc.source,
                            source_reference=f"profile_fact.ANNUAL_INCOME (id: {fact_inc.fact_id})",
                            value=fact_val,
                            verified=fact_inc.verified,
                            confidence=float(fact_inc.confidence) if fact_inc.confidence is not None else None,
                        ),
                    ]
                    issue_type = "CONFIRMED_CONFLICT" if fact_inc.verified else "POSSIBLE_CONFLICT"
                    severity = "HIGH" if fact_inc.verified else "MEDIUM"
                    affected = ProfileAuditService._resolve_affected_schemes("annual_income", param_to_schemes)
                    issues.append(
                        ProfileAuditIssue(
                            issue_type=issue_type,
                            attribute_name="annual_income",
                            attribute_label="Annual Family Income",
                            current_value=f"₹{prof_val:g}",
                            conflicting_value=f"₹{fact_val:g}",
                            severity=severity,
                            description=f"Direct profile annual income (₹{prof_val:g}) disagrees with stored profile fact (₹{fact_val:g}).",
                            explanation=f"Income criteria in scheme evaluations may produce differing outcomes depending on whether the rule inspects the normalized fact or profile table.",
                            sources=sources,
                            affected_schemes=affected,
                            recommended_action="Review and re-synchronize your income details to ensure accurate scheme eligibility assessment.",
                        )
                    )
            except (ValueError, TypeError):
                pass

        # Check Land Holding Conflict
        fact_land = open_facts_by_code.get("LAND_HOLDING")
        if fact_land and fin and fin.land_holding_size is not None:
            try:
                fact_land_val = float(fact_land.fact_value)
                prof_land_val = float(fin.land_holding_size)
                if abs(fact_land_val - prof_land_val) > 0.01:
                    sources = [
                        FactSourceEvidence(
                            source_type="PROFILE_RECORD",
                            source_reference="financial_profile.land_holding_size",
                            value=prof_land_val,
                            verified=False,
                        ),
                        FactSourceEvidence(
                            source_type=fact_land.source,
                            source_reference=f"profile_fact.LAND_HOLDING (id: {fact_land.fact_id})",
                            value=fact_land_val,
                            verified=fact_land.verified,
                        ),
                    ]
                    affected = ProfileAuditService._resolve_affected_schemes("land_holding_size", param_to_schemes)
                    issues.append(
                        ProfileAuditIssue(
                            issue_type="CONFIRMED_CONFLICT" if fact_land.verified else "POSSIBLE_CONFLICT",
                            attribute_name="land_holding_size",
                            attribute_label="Land Holding Size",
                            current_value=f"{prof_land_val} ha",
                            conflicting_value=f"{fact_land_val} ha",
                            severity="HIGH",
                            description=f"Profile land holding ({prof_land_val} ha) differs from stored fact ({fact_land_val} ha).",
                            explanation="Farmer welfare schemes (such as PM-KISAN) strictly enforce land threshold limits.",
                            sources=sources,
                            affected_schemes=affected,
                            recommended_action="Confirm your actual land records and update your profile.",
                        )
                    )
            except (ValueError, TypeError):
                pass

        # Check Age vs Date of Birth Inconsistency
        fact_age = open_facts_by_code.get("AGE")
        if fact_age and citizen.date_of_birth:
            try:
                calc_age = calculate_age(citizen.date_of_birth)
                stored_age = int(fact_age.fact_value)
                if abs(calc_age - stored_age) >= 1:
                    sources = [
                        FactSourceEvidence(
                            source_type="IDENTITY_DOB",
                            source_reference=f"date_of_birth ({citizen.date_of_birth.isoformat()})",
                            value=calc_age,
                            verified=True,
                        ),
                        FactSourceEvidence(
                            source_type=fact_age.source,
                            source_reference="profile_fact.AGE",
                            value=stored_age,
                            verified=fact_age.verified,
                        ),
                    ]
                    affected = ProfileAuditService._resolve_affected_schemes("age", param_to_schemes)
                    issues.append(
                        ProfileAuditIssue(
                            issue_type="CONFIRMED_CONFLICT",
                            attribute_name="age",
                            attribute_label="Age / Date of Birth",
                            current_value=calc_age,
                            conflicting_value=stored_age,
                            severity="HIGH",
                            description=f"Calculated age from date of birth ({calc_age} years) does not match profile fact age ({stored_age} years).",
                            explanation="Age-restricted welfare schemes (e.g. Senior pensions or Youth schemes) evaluate specific age boundaries.",
                            sources=sources,
                            affected_schemes=affected,
                            recommended_action="Re-sync your profile facts to align your age calculation with your date of birth.",
                        )
                    )
            except (ValueError, TypeError):
                pass

        return issues

    @staticmethod
    def _check_document_conflicts(
        citizen: CitizenMaster,
        documents: List[CitizenDocument],
        param_to_schemes: Dict[str, Set[str]],
    ) -> List[ProfileAuditIssue]:
        issues = []
        for doc in documents:
            if doc.validation_status == "INVALID":
                req_title = doc.requirement_type.replace("_", " ").title()
                det_title = (doc.detected_type or "Unknown").replace("_", " ").title()
                issues.append(
                    ProfileAuditIssue(
                        issue_type="CONFIRMED_CONFLICT",
                        attribute_name=f"document_{doc.requirement_type.lower()}",
                        attribute_label=f"{req_title} Document",
                        current_value=req_title,
                        conflicting_value=det_title,
                        severity="HIGH",
                        description=f"Uploaded file '{doc.original_filename}' was detected as {det_title} instead of the required {req_title}.",
                        explanation="Schemes requiring this document will remain in MISSING_DOCUMENTS status until a valid document is uploaded.",
                        sources=[
                            FactSourceEvidence(
                                source_type="DOCUMENT_CLASSIFIER",
                                source_reference=doc.original_filename,
                                value=det_title,
                                verified=False,
                                observed_at=doc.uploaded_at,
                            )
                        ],
                        affected_schemes=sorted(list(param_to_schemes.get(doc.requirement_type.lower(), set()))),
                        recommended_action=f"Upload a valid {req_title} to satisfy scheme document requirements.",
                    )
                )
        return issues

    @staticmethod
    def _check_stale_facts(
        facts: List[ProfileFact],
        now: datetime,
        param_to_schemes: Dict[str, Set[str]],
    ) -> List[ProfileAuditIssue]:
        issues = []
        for f in facts:
            if getattr(f, "effective_until", None) is not None:
                continue

            max_days = STALE_THRESHOLDS_DAYS.get(f.fact_code)
            if not max_days:
                continue

            ref_date = f.updated_at or f.created_at
            if not ref_date:
                continue

            if ref_date.tzinfo is None:
                ref_date = ref_date.replace(tzinfo=timezone.utc)

            age_days = (now - ref_date).days
            if age_days > max_days:
                param_key = f.fact_code.lower()
                label = PARAMETER_LABELS.get(param_key, f.fact_code.replace("_", " ").title())
                affected = ProfileAuditService._resolve_affected_schemes(f.fact_code, param_to_schemes)
                issues.append(
                    ProfileAuditIssue(
                        issue_type="STALE_FACT",
                        attribute_name=param_key,
                        attribute_label=label,
                        current_value=f.fact_value,
                        conflicting_value=None,
                        severity="MEDIUM" if age_days > (max_days * 1.5) else "LOW",
                        description=f"{label} was recorded {age_days} days ago (exceeds recommended validity period of {max_days} days).",
                        explanation="Government welfare guidelines require income and asset documentation to be current within the last year.",
                        sources=[
                            FactSourceEvidence(
                                source_type=f.source,
                                source_reference=f"profile_fact.{f.fact_code}",
                                value=f.fact_value,
                                verified=f.verified,
                                observed_at=ref_date,
                            )
                        ],
                        affected_schemes=affected,
                        recommended_action=f"Verify and update your {label.lower()} to ensure your eligibility remains up to date.",
                    )
                )

        return issues

    @staticmethod
    def _check_missing_information(
        citizen: CitizenMaster,
        facts: List[ProfileFact],
        param_to_schemes: Dict[str, Set[str]],
    ) -> List[ProfileAuditIssue]:
        issues = []
        open_fact_codes = {f.fact_code for f in facts if getattr(f, "effective_until", None) is None}

        # Check annual income
        fin = getattr(citizen, "financial_profile", None)
        if (not fin or fin.annual_income is None) and "ANNUAL_INCOME" not in open_fact_codes:
            issues.append(
                ProfileAuditIssue(
                    issue_type="MISSING_INFORMATION",
                    attribute_name="annual_income",
                    attribute_label="Annual Family Income",
                    current_value=None,
                    conflicting_value=None,
                    severity="HIGH",
                    description="Annual family income is missing from your profile.",
                    explanation="Income is a mandatory criterion for almost all means-tested welfare programs.",
                    sources=[],
                    affected_schemes=ProfileAuditService._resolve_affected_schemes("annual_income", param_to_schemes),
                    recommended_action="Provide your annual household income in your profile.",
                )
            )

        # Check social category
        demo = getattr(citizen, "demographic_profile", None)
        if (not demo or not demo.social_category) and "SOCIAL_CATEGORY" not in open_fact_codes:
            issues.append(
                ProfileAuditIssue(
                    issue_type="MISSING_INFORMATION",
                    attribute_name="social_category",
                    attribute_label="Social Category / Caste",
                    current_value=None,
                    conflicting_value=None,
                    severity="MEDIUM",
                    description="Social category (General/OBC/SC/ST) is not specified.",
                    explanation="Several affirmative welfare schemes require verified social category membership.",
                    sources=[],
                    affected_schemes=ProfileAuditService._resolve_affected_schemes("social_category", param_to_schemes),
                    recommended_action="Specify your social category in your profile.",
                )
            )

        return issues

    @staticmethod
    def _format_summary_message(
        confirmed: int, possible: int, stale: int, missing: int
    ) -> str:
        if confirmed == 0 and possible == 0 and stale == 0 and missing == 0:
            return "Profile is completely consistent and up to date; no conflicts or stale facts found."

        parts = []
        if confirmed > 0:
            parts.append(f"{confirmed} confirmed conflict{'s' if confirmed > 1 else ''}")
        if possible > 0:
            parts.append(f"{possible} possible conflict{'s' if possible > 1 else ''}")
        if stale > 0:
            parts.append(f"{stale} potentially stale fact{'s' if stale > 1 else ''}")
        if missing > 0:
            parts.append(f"{missing} missing item{'s' if missing > 1 else ''}")

        return f"Audit detected: {', '.join(parts)}. Review recommended to preserve accurate eligibility results."
