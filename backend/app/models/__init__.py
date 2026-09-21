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
# Phase 1: profile facts
from app.models.profile_fact import (
    FACT_DATA_TYPES,
    FACT_SOURCES,
    ProfileFact,
    ProfileFactProvenance,
)
# Phase 1: normalized domain profiles
from app.models.domain_profile import (
    AgricultureProfile,
    AssetProfile,
    DisabilityProfile,
    EducationProfile,
    EmploymentProfile,
    FamilyMember,
)
# Phase 1: scheme sources and ingestion infrastructure
from app.models.scheme_source import (
    CONTENT_TYPES,
    PROCESSING_STATUSES,
    SCHEME_SOURCE_TYPES,
    SchemeIngestionRun,
    SchemeRuleProvenance,
    SchemeSource,
    SchemeSourceContent,
    SchemeSourceDocument,
)

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
    # Phase 1: profile facts
    "ProfileFact",
    "ProfileFactProvenance",
    "FACT_DATA_TYPES",
    "FACT_SOURCES",
    # Phase 1: domain profiles
    "EducationProfile",
    "EmploymentProfile",
    "FamilyMember",
    "AgricultureProfile",
    "DisabilityProfile",
    "AssetProfile",
    # Phase 1: scheme sources
    "SchemeSource",
    "SchemeSourceDocument",
    "SchemeSourceContent",
    "SchemeRuleProvenance",
    "SchemeIngestionRun",
    "SCHEME_SOURCE_TYPES",
    "CONTENT_TYPES",
    "PROCESSING_STATUSES",
]
