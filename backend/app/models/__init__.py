"""ORM models package. Import all models here so Alembic autodiscovery works."""

from app.models.citizen import CitizenMaster, DemographicProfile, FinancialProfile, LocationProfile
from app.models.scheme import SchemeMaster, SchemeRuleGroup, SchemeEligibilityRule, SchemeDocumentMaster
from app.models.assessment import EligibilityAssessment

# Phase 1: dynamic forms
from app.models.form import (
    FormCondition,
    FormDefinition,
    FormQuestion,
    FormQuestionOption,
    FormSection,
    QUESTION_TYPES,
)
# Phase 1: form submissions and typed answers
from app.models.submission import ANSWER_SOURCES, SUBMISSION_STATUSES, FormAnswer, FormSubmission

__all__ = [
    "CitizenMaster",
    "DemographicProfile",
    "FinancialProfile",
    "LocationProfile",
    "SchemeMaster",
    "SchemeRuleGroup",
    "SchemeEligibilityRule",
    "SchemeDocumentMaster",
    "EligibilityAssessment",
    # Phase 1: forms
    "FormDefinition",
    "FormSection",
    "FormQuestion",
    "FormQuestionOption",
    "FormCondition",
    "QUESTION_TYPES",
    # Phase 1: submissions
    "FormSubmission",
    "FormAnswer",
    "SUBMISSION_STATUSES",
    "ANSWER_SOURCES",
]
