"""
Recommendation ranking service.
Provides deterministic, explainable ranking for citizen scheme recommendations.

Invariants & Ranking Criteria:
1. Eligibility partition: Eligible schemes always rank ahead of ineligible schemes.
2. Rule Match Score: Within the same eligibility group, higher rule_match_score ranks first.
   Missing scores safely default to 0.0.
3. Citizen relevance: Evaluated strictly using genuine, verified data:
   - Target Persona / Profile Type match: Scheme target_persona directly aligns with citizen profile_types or citizen_type.
   - Document Readiness: Complete mandatory documents prioritize eligible schemes.
4. Deterministic tie-breaking:
   - Scheme name (ascending alphabetical)
   - Scheme ID (ascending string UUID)
   No random factors, no floating-point jitter, identical inputs yield identical outputs.
5. Recommendation explanations:
   - Clear, concise explanation factors indicating why the scheme was prioritized.
"""

from __future__ import annotations

import uuid
from typing import Any, List, Optional, Sequence, Tuple

from app.models.citizen import CitizenMaster
from app.schemas.assessment import RecommendationItem


# Canonical profile type / persona normalization
_PERSONA_PROFILE_MAP = {
    "FARMER": {"FARMER"},
    "STUDENT": {"STUDENT"},
    "SENIOR": {"SENIOR_CITIZEN", "SENIOR"},
    "PWD": {"PWD", "PHYSICALLY_DISABLED"},
    "BUSINESS": {"BUSINESS", "SELF_EMPLOYED"},
}


def _matches_target_persona(citizen: Optional[CitizenMaster], target_persona: Optional[str]) -> bool:
    """Check if the scheme's target_persona aligns with the citizen's profile types or citizen_type."""
    if not citizen or not target_persona:
        return False

    target = target_persona.strip().upper()
    if target == "GENERAL":
        return False  # General applies broadly, not a targeted persona boost

    citizen_types = set()
    if citizen.citizen_type:
        citizen_types.add(citizen.citizen_type.strip().upper())

    if citizen.profile_types and isinstance(citizen.profile_types, list):
        for pt in citizen.profile_types:
            if isinstance(pt, str):
                citizen_types.add(pt.strip().upper())

    # Direct match
    if target in citizen_types:
        return True

    # Canonical alias mapping
    aliases = _PERSONA_PROFILE_MAP.get(target, {target})
    if citizen_types.intersection(aliases):
        return True

    # Reverse alias mapping
    for t in citizen_types:
        if target in _PERSONA_PROFILE_MAP.get(t, {t}):
            return True

    return False


def _compute_relevance_and_explanation(
    item: RecommendationItem,
    citizen: Optional[CitizenMaster],
) -> Tuple[int, Optional[str]]:
    """
    Computes (persona_relevance_score, recommendation_explanation).
    persona_relevance_score is 1 if target_persona aligns, else 0.
    """
    relevance_boost = 0
    factors = []

    # 1. Eligibility status
    if getattr(item, "is_stale", False):
        factors.append("Scheme rules changed since your last evaluation. Re-evaluation recommended.")
    elif item.eligibility_result:
        factors.append("Eligible based on profile criteria")
    else:
        factors.append("Not currently eligible")

    # 2. Rule match score
    score = item.rule_match_score
    if score is not None:
        factors.append(f"{score:.1f}% criteria match")

    # 3. Target Persona alignment
    scheme = item.scheme
    target_persona = getattr(scheme, "target_persona", None)
    if _matches_target_persona(citizen, target_persona):
        relevance_boost = 1
        factors.append(f"Directly matches your profile type ({target_persona.title()})")

    # 4. Document readiness
    doc_status = item.document_status
    if item.eligibility_result and doc_status == "COMPLETE":
        factors.append("All required documents uploaded")

    explanation = " \u00b7 ".join(factors)
    return relevance_boost, explanation


def rank_recommendations(
    items: Sequence[RecommendationItem],
    citizen: Optional[CitizenMaster] = None,
) -> List[RecommendationItem]:
    """
    Ranks recommendation items deterministically.

    Ranking Tuple (Higher is prioritized first, except for string tie-breakers):
    1. eligibility_result: bool (True before False)
    2. rule_match_score: float (descending; None defaults to 0.0)
    3. persona_relevance: int (1 if target_persona matches citizen profile, else 0)
    4. document_readiness: int (1 if COMPLETE for eligible, else 0)
    5. scheme_name: str (ascending alphabetical tie-breaker)
    6. scheme_id: str (ascending UUID tie-breaker)
    """
    decorated = []

    for item in items:
        # Score fallback
        score = item.rule_match_score if item.rule_match_score is not None else 0.0

        # Persona relevance & explanation
        persona_boost, explanation = _compute_relevance_and_explanation(item, citizen)

        # Document readiness boost (only relevant for eligible schemes)
        doc_boost = 1 if (item.eligibility_result and item.document_status == "COMPLETE") else 0

        # Stable tie-breakers
        scheme_name = str(item.scheme.scheme_name or "").lower()
        scheme_id_str = str(item.scheme.scheme_id or "")

        # Attach explanation to the RecommendationItem
        item.recommendation_explanation = explanation

        # Sorting key
        # We sort descending on booleans/numeric, ascending on names/IDs
        # In Python sort:
        sort_key = (
            1 if item.eligibility_result else 0,
            score,
            persona_boost,
            doc_boost,
        )

        decorated.append((sort_key, scheme_name, scheme_id_str, item))

    # Sort: primary keys descending, tie-breakers ascending
    decorated.sort(
        key=lambda entry: (
            -entry[0][0],      # eligibility (1 before 0)
            -entry[0][1],      # score (higher before lower)
            -entry[0][2],      # persona match (1 before 0)
            -entry[0][3],      # doc readiness (1 before 0)
            entry[1],          # scheme_name ascending
            entry[2],          # scheme_id ascending
        )
    )

    return [entry[3] for entry in decorated]
