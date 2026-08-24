"""ORM models package. Import all models here so Alembic autodiscovery works."""

from app.models.citizen import CitizenMaster, DemographicProfile, FinancialProfile, LocationProfile
from app.models.scheme import SchemeMaster, SchemeRuleGroup, SchemeEligibilityRule, SchemeDocumentMaster
from app.models.assessment import EligibilityAssessment

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
]
