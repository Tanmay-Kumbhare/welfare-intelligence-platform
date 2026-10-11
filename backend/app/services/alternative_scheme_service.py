"""
Alternative Scheme Suggestions Service.

Identifies and ranks relevant alternative scheme suggestions for citizens
who are currently ineligible for a scheme.

Invariants & Principles:
1. Pure suggestion layer: Does not alter eligibility outcomes or Rule Match Scores.
2. Clearly labeled: Suggestions are explicitly marked as exploratory suggestions, not guaranteed eligibility.
3. No self-suggestion: The original scheme is never suggested as its own alternative.
4. Explanations: Plainly explains why each alternative is suggested based on:
   - Same category (e.g. Housing, Agriculture, Education)
   - Same target persona / profile type (e.g. Student, Farmer, Senior)
   - Confirmed eligibility status (schemes the citizen is already eligible for)
   - Higher criteria match score
5. Performance & Safety: Reuses already-evaluated recommendation items in memory;
   performs zero extra DB queries and handles empty lists or missing scores safely.
"""

from __future__ import annotations

import uuid
from typing import Any, List, Optional, Sequence
from pydantic import BaseModel, ConfigDict

from app.schemas.assessment import RecommendationItem
from app.schemas.scheme import SchemeResponse


class AlternativeSchemeSuggestion(BaseModel):
    """A suggested alternative scheme for an ineligible evaluation."""
    model_config = ConfigDict(from_attributes=True)

    scheme_id: uuid.UUID
    scheme_name: str
    department_name: Optional[str] = None
    scheme_category: Optional[str] = None
    target_persona: Optional[str] = None
    eligibility_result: bool
    rule_match_score: Optional[float] = None
    suggestion_reason: str
    is_confirmed_eligible: bool


class AlternativeSchemeService:
    @staticmethod
    def find_alternatives_for_item(
        target_item: RecommendationItem,
        all_items: Sequence[RecommendationItem],
        max_suggestions: int = 3,
    ) -> List[AlternativeSchemeSuggestion]:
        """
        Finds the top alternative suggestions for an ineligible RecommendationItem
        from the set of all evaluated RecommendationItems.
        """
        target_scheme_id = getattr(target_item.scheme, "scheme_id", None)
        target_category = getattr(target_item.scheme, "scheme_category", None)
        target_persona = getattr(target_item.scheme, "target_persona", None)

        candidates = []

        for candidate in all_items:
            candidate_scheme_id = getattr(candidate.scheme, "scheme_id", None)
            if not candidate_scheme_id or candidate_scheme_id == target_scheme_id:
                # Do not suggest the original scheme as its own alternative
                continue

            # Evaluate suitability criteria
            c_category = getattr(candidate.scheme, "scheme_category", None)
            c_persona = getattr(candidate.scheme, "target_persona", None)
            c_score = candidate.rule_match_score if candidate.rule_match_score is not None else 0.0

            is_same_category = bool(target_category and c_category and target_category.upper() == c_category.upper())
            is_same_persona = bool(
                target_persona
                and c_persona
                and target_persona.upper() != "GENERAL"
                and target_persona.upper() == c_persona.upper()
            )
            is_eligible = bool(candidate.eligibility_result)

            # A candidate is viable if it shares category, persona, is eligible, or has strong match score
            if not (is_same_category or is_same_persona or is_eligible or c_score >= 50.0):
                continue

            # Prioritization scoring for alternatives:
            # 1. Confirmed eligible schemes get highest base weight (1000)
            # 2. Same category (+200)
            # 3. Same persona (+100)
            # 4. Rule match score (+0 to 100)
            priority_score = (
                (1000 if is_eligible else 0)
                + (200 if is_same_category else 0)
                + (100 if is_same_persona else 0)
                + c_score
            )

            # Formulate truthful, factual explanation
            reasons = []
            if is_eligible:
                reasons.append("You meet the stored criteria for this scheme")
            elif c_score > 0:
                reasons.append(f"{c_score:.1f}% criteria match")

            if is_same_category and target_category:
                reasons.append(f"offers benefits in the same category ({target_category.title()})")
            elif is_same_persona and target_persona:
                reasons.append(f"also supports {target_persona.title()} citizens")

            if not reasons:
                reasons.append("Suggested alternative based on your overall welfare profile")

            reason_str = "Suggestion: " + " · ".join(reasons) + "."

            suggestion = AlternativeSchemeSuggestion(
                scheme_id=candidate.scheme.scheme_id,
                scheme_name=candidate.scheme.scheme_name,
                department_name=getattr(candidate.scheme, "department_name", None),
                scheme_category=c_category,
                target_persona=c_persona,
                eligibility_result=candidate.eligibility_result,
                rule_match_score=candidate.rule_match_score,
                suggestion_reason=reason_str,
                is_confirmed_eligible=is_eligible,
            )

            # Sort tuple:
            # (-priority_score, scheme_name_lower, scheme_id_str)
            sort_key = (
                -priority_score,
                str(candidate.scheme.scheme_name or "").lower(),
                str(candidate_scheme_id),
            )
            candidates.append((sort_key, suggestion))

        # Sort candidates deterministically
        candidates.sort(key=lambda x: x[0])

        return [c[1] for c in candidates[:max_suggestions]]

    @staticmethod
    def attach_alternatives_to_recommendations(
        eligible_items: Sequence[RecommendationItem],
        ineligible_items: Sequence[RecommendationItem],
        max_suggestions: int = 3,
    ) -> None:
        """
        Attaches alternative suggestions in-place to all ineligible RecommendationItems
        using the full evaluated catalogue (eligible + ineligible).
        """
        all_items = list(eligible_items) + list(ineligible_items)

        for item in ineligible_items:
            item.alternative_schemes = AlternativeSchemeService.find_alternatives_for_item(
                target_item=item,
                all_items=all_items,
                max_suggestions=max_suggestions,
            )
