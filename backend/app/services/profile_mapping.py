"""
Canonical profile-field registry and deterministic value normalization
(Phase 2B).

This module is the SINGLE source of truth for mapping form-question
`profile_field` metadata to:

  1. canonical domain-profile columns (tbl_demographic_profile,
     tbl_financial_profile, tbl_location_profile, tbl_education_profile,
     tbl_employment_profile, tbl_agriculture_profile, tbl_disability_profile,
     tbl_asset_profile, tbl_citizen_master)
  2. profile facts (tbl_profile_fact rows for the interoperability layer)

Mapping strategy (Part 1 of the Phase 2B spec):
  - The form question's own `profile_field` metadata drives everything.
    Dotted paths ("financial.annual_income") are authoritative.
  - Bare names are resolved through REGISTRY_ONLY fields below, which exist
    to disambiguate the Phase 2A seed's bare names deterministically
    (e.g. annual_income -> financial profile) without any per-question
    Python mapping. An unknown bare name is reported UNMAPPED, never guessed.
  - Facts are emitted only for registry entries where fact_code is not None,
    so UI-only questions never become facts (Part 6).

Value handling (Parts 9/10):
  - Domain-column values are coerced to the column's declared Python type.
  - fact_value is TEXT (per tbl_profile_fact design) + data_type; canonical
    serialization is deterministic: numbers plain, booleans TRUE/FALSE,
    dates ISO, strings upper-cased trim-safe, JSON compact. Currency
    strings ("₹2,40,000", "2.4 lakh") are parsed deterministically here —
    no LLM involved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from typing import Callable

from app.services.form_logic import is_answered
from app.utils.date_calc import calculate_age


# ------------------------------------------------------------------
# Registry entry
# ------------------------------------------------------------------


@dataclass(frozen=True)
class ProfileField:
    """One canonical profile target."""

    domain: str                    # citizen | demographic | financial | location |
                                   # education | employment | agriculture | disability | asset
    column: str | None             # ORM attribute name on the domain profile
    data_type: str                 # STRING | INTEGER | DECIMAL | BOOLEAN | DATE | JSON
    fact_code: str | None          # profile-fact code; None = never a fact
    fact_only: bool = False        # fact exists but has no canonical column
    bare_names: tuple[str, ...] = field(default=())
    choices: tuple[str, ...] | None = None  # allowed values, if enumerated


def _pf(**kwargs) -> ProfileField:
    return ProfileField(**kwargs)


# ------------------------------------------------------------------
# The registry — every canonical target currently representable in the DB
# ------------------------------------------------------------------

REGISTRY: dict[str, ProfileField] = {
    # ---- citizen identity (fact-only: identity table is owned by
    # citizen registration; form answers never rewrite identity columns) ----
    "citizen.full_name": _pf(domain="citizen", column=None, data_type="STRING",
                             fact_code="FULL_NAME", fact_only=False,
                             bare_names=("full_name",)),
    "citizen.mobile_number": _pf(domain="citizen", column=None, data_type="STRING",
                                 fact_code="MOBILE_NUMBER", fact_only=False,
                                 bare_names=("mobile_number", "phone_number")),
    "citizen.email_id": _pf(domain="citizen", column=None, data_type="STRING",
                            fact_code="EMAIL", fact_only=False,
                            bare_names=("email", "email_id")),
    # ---- demographic ----
    "demographic.date_of_birth": _pf(
        domain="demographic", column=None, data_type="DATE",
        fact_code="DATE_OF_BIRTH", fact_only=False,
        bare_names=("date_of_birth", "dob"),
        # citizen.date_of_birth is NOT NULL and set at registration; a form
        # answer to the same value is expressed as a fact, not an overwrite.
    ),
    "demographic.gender": _pf(domain="demographic", column="gender",
                              data_type="STRING", fact_code="GENDER",
                              bare_names=("gender",),
                              choices=("MALE", "FEMALE", "OTHER")),
    "demographic.social_category": _pf(domain="demographic", column="social_category",
                                       data_type="STRING", fact_code="SOCIAL_CATEGORY",
                                       bare_names=("social_category", "category"),
                                       choices=("GEN", "OBC", "SC", "ST")),
    "demographic.marital_status": _pf(domain="demographic", column="marital_status",
                                      data_type="STRING", fact_code="MARITAL_STATUS",
                                      bare_names=("marital_status",),
                                      choices=("SINGLE", "MARRIED", "WIDOWED", "DIVORCED")),
    "demographic.disability_status": _pf(domain="demographic", column="disability_status",
                                         data_type="STRING", fact_code="DISABILITY_STATUS",
                                         bare_names=("disability_status",),
                                         choices=("NONE", "PHYSICALLY_DISABLED",
                                                  "VISUALLY_IMPAIRED", "HEARING_IMPAIRED",
                                                  "OTHER")),
    # ---- financial ----
    "financial.annual_income": _pf(domain="financial", column="annual_income",
                                   data_type="DECIMAL", fact_code="ANNUAL_INCOME",
                                   bare_names=("annual_income", "income")),
    "financial.income_source": _pf(domain="financial", column="income_source",
                                   data_type="STRING", fact_code="INCOME_SOURCE",
                                   bare_names=("income_source",)),
    "financial.poverty_category": _pf(domain="financial", column="poverty_category",
                                      data_type="STRING", fact_code="POVERTY_CATEGORY",
                                      bare_names=("poverty_category",),
                                      choices=("APL", "BPL", "AAY", "NONE")),
    "financial.is_bpl_card_holder": _pf(domain="financial", column="is_bpl_card_holder",
                                        data_type="BOOLEAN", fact_code="IS_BPL_CARD_HOLDER",
                                        bare_names=("is_bpl_card_holder", "has_bpl_card")),
    "financial.is_income_tax_payer": _pf(domain="financial", column="is_income_tax_payer",
                                         data_type="BOOLEAN", fact_code="IS_INCOME_TAX_PAYER",
                                         bare_names=("is_income_tax_payer",)),
    # ---- location ----
    "location.state": _pf(domain="location", column="state", data_type="STRING",
                          fact_code="STATE", bare_names=("state",)),
    "location.district": _pf(domain="location", column="district", data_type="STRING",
                             fact_code="DISTRICT", bare_names=("district",)),
    "location.village_city": _pf(domain="location", column="village_city",
                                 data_type="STRING", fact_code="VILLAGE_CITY",
                                 bare_names=("village_city", "village", "city", "taluka",
                                             "town")),
    "location.pincode": _pf(domain="location", column=None, data_type="STRING",
                            fact_code="PINCODE", fact_only=False,
                            bare_names=("pincode", "pin_code", "zip_code")),
    "location.area_type": _pf(domain="location", column="area_type", data_type="STRING",
                              fact_code="AREA_TYPE", bare_names=("area_type",),
                              choices=("RURAL", "URBAN", "SEMI_URBAN")),
    # ---- education ----
    "education.education_level": _pf(domain="education", column="education_level",
                                     data_type="STRING", fact_code="EDUCATION_LEVEL",
                                     bare_names=("education_level",),
                                     choices=("ILLITERATE", "PRIMARY", "SECONDARY",
                                              "HIGHER_SECONDARY", "GRADUATE",
                                              "POST_GRADUATE")),
    "education.institution_name": _pf(domain="education", column="institution_name",
                                      data_type="STRING", fact_code=None,
                                      bare_names=("institution_name", "institution",
                                                  "college_name", "school_name")),
    "education.course_name": _pf(domain="education", column="course_name",
                                 data_type="STRING", fact_code=None,
                                 bare_names=("course_name", "course", "course_studying")),
    "education.year_of_study": _pf(domain="education", column="year_of_study",
                                   data_type="INTEGER", fact_code="YEAR_OF_STUDY",
                                   bare_names=("year_of_study", "current_year")),
    "education.academic_year": _pf(domain="education", column="academic_year",
                                   data_type="STRING", fact_code=None,
                                   bare_names=("academic_year",)),
    "education.marks_percentage": _pf(domain="education", column="marks_percentage",
                                      data_type="DECIMAL", fact_code="MARKS_PERCENTAGE",
                                      bare_names=("marks_percentage", "marks")),
    "education.annual_fee": _pf(domain="education", column="annual_fee",
                                data_type="DECIMAL", fact_code=None,
                                bare_names=("annual_fee",)),
    "education.hostel_status": _pf(domain="education", column="hostel_status",
                                   data_type="STRING", fact_code="HOSTEL_STATUS",
                                   bare_names=("hostel_status",),
                                   choices=("HOSTELLER", "DAY_SCHOLAR", "NONE")),
    "education.currently_studying": _pf(domain="education", column=None,
                                        data_type="BOOLEAN",
                                        fact_code="CURRENTLY_STUDYING",
                                        fact_only=False,
                                        bare_names=("currently_studying", "is_studying")),
    # ---- employment ----
    "employment.employment_status": _pf(domain="employment", column="employment_status",
                                        data_type="STRING", fact_code="EMPLOYMENT_STATUS",
                                        bare_names=("employment_status",),
                                        choices=("EMPLOYED", "UNEMPLOYED", "SELF_EMPLOYED",
                                                 "STUDENT", "RETIRED")),
    "employment.occupation": _pf(domain="employment", column="occupation",
                                 data_type="STRING", fact_code=None,
                                 bare_names=("occupation", "job_title")),
    "employment.employment_type": _pf(domain="employment", column="employment_type",
                                      data_type="STRING", fact_code=None,
                                      bare_names=("employment_type",)),
    "employment.monthly_income": _pf(domain="employment", column="monthly_income",
                                     data_type="DECIMAL", fact_code="MONTHLY_INCOME",
                                     bare_names=("monthly_income",)),
    "employment.work_sector": _pf(domain="employment", column="work_sector",
                                  data_type="STRING", fact_code=None,
                                  bare_names=("work_sector", "sector")),
    "employment.self_employed": _pf(domain="employment", column="self_employed",
                                    data_type="BOOLEAN", fact_code="SELF_EMPLOYED",
                                    bare_names=("self_employed", "is_self_employed")),
                                   # Phase 2C: derived from EMPLOYMENT_STATUS — never asked (DERIVED_ONLY).
    "employment.employer_name": _pf(domain="employment", column="employer_name",
                                    data_type="STRING", fact_code=None,
                                    bare_names=("employer_name",)),
    "employment.employer_type": _pf(domain="employment", column="employer_type",
                                    data_type="STRING", fact_code=None,
                                    bare_names=("employer_type",),
                                    choices=("GOVERNMENT", "PRIVATE", "COOPERATIVE",
                                             "NGO", "HOUSEHOLD", "OTHER")),
    # ---- agriculture ----
    "agriculture.farmer_status": _pf(domain="agriculture", column="farmer_status",
                                     data_type="STRING", fact_code="FARMER_STATUS",
                                     bare_names=("farmer_status", "is_farmer"),
                                     choices=("YES", "NO", "MARGINAL", "SMALL", "OTHER")),
    "agriculture.land_ownership_status": _pf(
        domain="agriculture", column="land_ownership_status", data_type="STRING",
        fact_code=None, bare_names=("land_ownership_status", "land_ownership"),
        choices=("OWNED", "LEASED", "BOTH", "NONE")),
    "agriculture.total_land_area": _pf(domain="agriculture", column="total_land_area",
                                       data_type="DECIMAL", fact_code=None,
                                       bare_names=("total_land_area", "land_area")),
    "agriculture.land_holding_size": _pf(
        domain="financial", column="land_holding_size", data_type="DECIMAL",
        # Mirrors into financial.land_holding_size — the V1 column the current
        # eligibility engine reads (PM-KISAN <= 2.0 ha threshold).
        fact_code="LAND_HOLDING",
        bare_names=("land_holding_size",)),
    "agriculture.crop_type": _pf(domain="agriculture", column="crop_type",
                                 data_type="STRING", fact_code=None,
                                 bare_names=("crop_type", "crops")),
    "agriculture.season": _pf(domain="agriculture", column="season",
                              data_type="STRING", fact_code=None,
                              bare_names=("season",),
                              choices=("KHARIF", "RABI", "ZAYAD", "WHOLE_YEAR")),
    "agriculture.farmer_type": _pf(domain="agriculture", column="farmer_type",
                                   data_type="STRING", fact_code="FARMER_TYPE",
                                   bare_names=("farmer_type",),
                                   choices=("OWNER", "TENANT", "SHARECROPPER", "OTHER")),
    "agriculture.land_unit": _pf(domain="agriculture", column="land_unit",
                                 data_type="STRING", fact_code=None,
                                 bare_names=("land_unit",),
                                 choices=("HECTARE", "ACRE", "BIGHA", "GUNTHA")),
    "agriculture.cultivated_land_area": _pf(
        domain="agriculture", column="cultivated_land_area", data_type="DECIMAL",
        fact_code=None, bare_names=("cultivated_land_area", "cultivated_area")),
    "agriculture.irrigated_land_area": _pf(
        domain="agriculture", column="irrigated_land_area", data_type="DECIMAL",
        fact_code=None, bare_names=("irrigated_land_area", "irrigated_area")),
    "agriculture.tenant_farmer": _pf(domain="agriculture", column="tenant_farmer",
                                     data_type="BOOLEAN", fact_code="TENANT_FARMER",
                                     bare_names=("tenant_farmer",)),
                                     # Phase 2C: derived from FARMER_TYPE — never asked (DERIVED_ONLY).
    "agriculture.sharecropper": _pf(domain="agriculture", column="sharecropper",
                                    data_type="BOOLEAN", fact_code="SHARECROPPER",
                                    bare_names=("sharecropper",)),
                                    # Phase 2C: derived from FARMER_TYPE — never asked (DERIVED_ONLY).
    "agriculture.has_kcc": _pf(domain="agriculture", column=None, data_type="BOOLEAN",
                               fact_code="HAS_KCC", fact_only=False,
                               bare_names=("has_kcc", "has_kisan_credit_card")),
    "agriculture.agricultural_income": _pf(
        domain="agriculture", column="agricultural_income", data_type="DECIMAL",
        fact_code=None, bare_names=("agricultural_income",)),
    # ---- disability ----
    "disability.disability_status": _pf(domain="disability", column="disability_status",
                                        data_type="STRING", fact_code="DISABILITY_STATUS",
                                        bare_names=("has_disability",),
                                        choices=("YES", "NO", "PENDING")),
    "disability.disability_type": _pf(domain="disability", column="disability_type",
                                      data_type="STRING", fact_code=None,
                                      bare_names=("disability_type",)),
    "disability.disability_percentage": _pf(
        domain="disability", column="disability_percentage", data_type="DECIMAL",
        fact_code="DISABILITY_PERCENTAGE", bare_names=("disability_percentage",)),
    "disability.certificate_available": _pf(
        domain="disability", column="certificate_available", data_type="BOOLEAN",
        fact_code="DISABILITY_CERTIFICATE", bare_names=("has_disability_certificate",)),
    # ---- assets (multi-row domain; single-answer fields only) ----
    "asset.asset_type": _pf(domain="asset", column="asset_type", data_type="STRING",
                            fact_code=None, bare_names=("asset_type",)),
    "asset.ownership_status": _pf(domain="asset", column="ownership_status",
                                  data_type="STRING", fact_code=None,
                                  bare_names=("ownership_status", "house_ownership_status"),
                                  choices=("OWNED", "JOINT", "LEASED", "NONE")),
    "asset.owns_house": _pf(domain="asset", column=None, data_type="BOOLEAN",
                            fact_code="OWNS_HOUSE", fact_only=False,
                            bare_names=("owns_house",)),
    "asset.owns_vehicle": _pf(domain="asset", column=None, data_type="BOOLEAN",
                              fact_code="OWNS_VEHICLE", fact_only=False,
                              bare_names=("owns_vehicle",)),
    "asset.owns_livestock": _pf(domain="asset", column=None, data_type="BOOLEAN",
                                fact_code="OWNS_LIVESTOCK", fact_only=False,
                                bare_names=("owns_livestock",)),
    "asset.estimated_value": _pf(domain="asset", column="estimated_value",
                                 data_type="DECIMAL", fact_code=None,
                                 bare_names=("asset_value", "estimated_value")),
    # ---- family (scalar side) ----
    "family.family_size": _pf(domain="demographic", column="family_size",
                              data_type="INTEGER", fact_code="FAMILY_SIZE",
                              bare_names=("family_size",)),
    # ---- identity documents (fact-only by design: certificate/document
    # numbers are sensitive; only possession flags become facts) ----
    "document.has_aadhaar": _pf(domain="citizen", column=None, data_type="BOOLEAN",
                                fact_code="HAS_AADHAAR", fact_only=False,
                                bare_names=("has_aadhaar", "aadhaar_available")),
    "document.has_ration_card": _pf(domain="citizen", column=None, data_type="BOOLEAN",
                                    fact_code="HAS_RATION_CARD", fact_only=False,
                                    bare_names=("has_ration_card",)),
    "document.has_income_certificate": _pf(domain="citizen", column=None, data_type="BOOLEAN",
                                           fact_code="HAS_INCOME_CERTIFICATE",
                                           fact_only=False,
                                           bare_names=("has_income_certificate",
                                                       "income_certificate_available")),
    "document.has_caste_certificate": _pf(domain="citizen", column=None, data_type="BOOLEAN",
                                          fact_code="HAS_CASTE_CERTIFICATE", fact_only=False,
                                          bare_names=("has_caste_certificate",
                                                      "caste_certificate_available")),
    "document.has_domicile_certificate": _pf(
        domain="citizen", column=None, data_type="BOOLEAN",
        fact_code="HAS_DOMICILE_CERTIFICATE", fact_only=False,
        bare_names=("has_domicile_certificate", "domicile_available")),
    "document.has_bonafide_certificate": _pf(
        domain="citizen", column=None, data_type="BOOLEAN",
        fact_code="HAS_BONAFIDE_CERTIFICATE", fact_only=False,
        bare_names=("has_bonafide_certificate", "bonafide_available")),
    "document.has_marksheet": _pf(domain="citizen", column=None, data_type="BOOLEAN",
                                  fact_code="HAS_MARKSHEET", fact_only=False,
                                  bare_names=("has_marksheet", "has_markssheet")),
    "document.has_land_records": _pf(domain="citizen", column=None, data_type="BOOLEAN",
                                     fact_code="HAS_LAND_RECORDS", fact_only=False,
                                     bare_names=("has_land_records",)),
    "document.has_bank_account": _pf(domain="citizen", column=None, data_type="BOOLEAN",
                                     fact_code="HAS_BANK_ACCOUNT", fact_only=False,
                                     bare_names=("has_bank_account",)),
    # ---- structured repeating block (Part 5) ----
    "family.members": _pf(domain="family_member", column=None, data_type="JSON",
                          fact_code=None, fact_only=False,
                          bare_names=("family_members",)),
    "family.has_dependents": _pf(domain="citizen", column=None, data_type="BOOLEAN",
                                 fact_code="HAS_DEPENDENTS", fact_only=False,
                                 bare_names=("has_dependents",)),
    # ------------------------------------------------------------------
    # Phase 2C additions (v2 form). Religion has no canonical column yet
    # (spec Task 12: type_specific_metadata/column deferred); it is
    # fact-only so minority schemes can key off MINORITY_STATUS later.
    # ------------------------------------------------------------------
    "demographic.religion": _pf(domain="demographic", column=None, data_type="STRING",
                                fact_code="RELIGION", fact_only=False,
                                bare_names=("religion",),
                                choices=("HINDU", "MUSLIM", "CHRISTIAN", "SIKH",
                                         "BUDDHIST", "JAIN", "OTHER")),
    "education.institution_type": _pf(domain="education", column="institution_type",
                                      data_type="STRING", fact_code=None,
                                      bare_names=("institution_type",),
                                      choices=("GOVERNMENT", "PRIVATE", "AIDED", "OTHER")),
    "education.scholarship_currently_received": _pf(
        domain="education", column="scholarship_currently_received",
        data_type="BOOLEAN", fact_code="SCHOLARSHIP_STATUS",
        bare_names=("scholarship_currently_received", "receiving_scholarship")),
}

# Fields whose value must NEVER be asked directly: normalization derives
# them from their source facts (Part 7/14 of the Phase 2C spec). The seed
# validator fails fast if a form question maps to one of these.
DERIVED_ONLY_FIELDS: frozenset[str] = frozenset({
    "financial.is_bpl_card_holder",   # derived from POVERTY_CATEGORY (BPL/AAY)
    "employment.self_employed",       # derived from EMPLOYMENT_STATUS
    "agriculture.tenant_farmer",      # derived from FARMER_TYPE
    "agriculture.sharecropper",       # derived from FARMER_TYPE
})

# ----------------------------------------------------------------------
# Declarative derivation rules (Phase 2C, spec Part 7/14).
#
# Each rule: SOURCE FACT(S) -> DETERMINISTIC DERIVATION -> DERIVED FACT.
# Every source fact is collected by the v2 form; nothing is inferred from
# unrelated or sensitive data (MINORITY_STATUS uses only the explicitly
# collected RELIGION, never geography or surname heuristics).
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class DerivationRule:
    """A deterministic source-fact -> derived-fact rule."""

    derived_fact: str            # fact_code of the derived fact
    data_type: str               # STRING | INTEGER | DECIMAL | BOOLEAN | DATE
    source_facts: tuple[str, ...]  # fact_codes that must exist to derive
    column: str | None           # canonical column to mirror (if any)
    domain: str | None           # domain owning `column`
    skip_if_derived_absent: bool = False  # chain rule (source itself derived)
    compute: Callable[[dict[str, dict[str, str | None] | None]], Any] | Callable[[dict[str, str | None]], Any] = None  # type: ignore[assignment]


_MINORITY_RELIGIONS: frozenset[str] = frozenset(
    {"MUSLIM", "CHRISTIAN", "SIKH", "BUDDHIST", "JAIN"}
)


def _compute_age(f: dict[str, str | None]) -> int:
    dob = date.fromisoformat(f["DATE_OF_BIRTH"])  # checked by caller
    return calculate_age(dob)


def _compute_senior(f: dict[str, str | None]) -> bool:
    return int(f["AGE"]) >= 60


def _flag_from_equal(f: dict[str, str | None], fact: str, expected: str) -> bool:
    return (f.get(fact) or "").strip().upper() == expected


def _flag_in(f: dict[str, str | None], fact: str, expected: frozenset[str]) -> bool:
    return (f.get(fact) or "").strip().upper() in expected


DERIVATION_RULES: tuple[DerivationRule, ...] = (
    # DATE_OF_BIRTH -> calendar age
    DerivationRule(
        derived_fact="AGE",
        data_type="INTEGER",
        source_facts=("DATE_OF_BIRTH",),
        column=None,
        domain=None,
        compute=_compute_age,
    ),
    # AGE (itself derived) -> senior-citizen flag (old-age pension schemes)
    DerivationRule(
        derived_fact="SENIOR_CITIZEN",
        data_type="BOOLEAN",
        source_facts=("AGE",),
        column=None,
        domain=None,
        skip_if_derived_absent=False,
        compute=_compute_senior,
    ),
    # RELIGION (explicitly asked) -> minority flag for minority-welfare schemes
    DerivationRule(
        derived_fact="MINORITY_STATUS",
        data_type="BOOLEAN",
        source_facts=("RELIGION",),
        column=None,
        domain=None,
        compute=lambda f: _flag_in(f, "RELIGION", _MINORITY_RELIGIONS),
    ),
    # MARITAL_STATUS + GENDER -> widow status (widow pension schemes).
    # Both sources are explicitly collected; nothing inferred.
    DerivationRule(
        derived_fact="WIDOW_STATUS",
        data_type="BOOLEAN",
        source_facts=("MARITAL_STATUS", "GENDER"),
        column=None,
        domain=None,
        compute=lambda f: (
            _flag_from_equal(f, "MARITAL_STATUS", "WIDOWED")
            and _flag_in(f, "GENDER", frozenset({"FEMALE", "MALE"}))
        ),
    ),
    # POVERTY_CATEGORY in {BPL, AAY} -> BPL-card flag (card-gated schemes)
    DerivationRule(
        derived_fact="IS_BPL_CARD_HOLDER",
        data_type="BOOLEAN",
        source_facts=("POVERTY_CATEGORY",),
        column="is_bpl_card_holder",
        domain="financial",
        compute=lambda f: _flag_in(f, "POVERTY_CATEGORY", frozenset({"BPL", "AAY"})),
    ),
    # EMPLOYMENT_STATUS = SELF_EMPLOYED -> self-employed flag
    DerivationRule(
        derived_fact="SELF_EMPLOYED",
        data_type="BOOLEAN",
        source_facts=("EMPLOYMENT_STATUS",),
        column="self_employed",
        domain="employment",
        compute=lambda f: _flag_from_equal(f, "EMPLOYMENT_STATUS", "SELF_EMPLOYED"),
    ),
    # FARMER_TYPE TENANT/SHARECROPPER -> the two tenancy flags
    DerivationRule(
        derived_fact="TENANT_FARMER",
        data_type="BOOLEAN",
        source_facts=("FARMER_TYPE",),
        column="tenant_farmer",
        domain="agriculture",
        compute=lambda f: _flag_from_equal(f, "FARMER_TYPE", "TENANT"),
    ),
    DerivationRule(
        derived_fact="SHARECROPPER",
        data_type="BOOLEAN",
        source_facts=("FARMER_TYPE",),
        column="sharecropper",
        domain="agriculture",
        compute=lambda f: _flag_from_equal(f, "FARMER_TYPE", "SHARECROPPER"),
    ),
)

# Bare-name -> dotted-key index (built once at import).
_BY_BARE_NAME: dict[str, str] = {
    bare: key for key, entry in REGISTRY.items() for bare in entry.bare_names
}

FACT_CODE_INDEX: dict[str, str] = {
    entry.fact_code: key for key, entry in REGISTRY.items() if entry.fact_code
}


def resolve_profile_field(profile_field: str | None) -> ProfileField | None:
    """
    Resolve a question's profile_field metadata to a registry entry.
    Dotted paths are authoritative; bare names resolve via the registry's
    declared bare-name aliases; anything else is UNMAPPED (returns None).
    """
    if not profile_field or not profile_field.strip():
        return None
    key = profile_field.strip().lower()
    if key in REGISTRY:
        return REGISTRY[key]
    if key in _BY_BARE_NAME:
        return REGISTRY[_BY_BARE_NAME[key]]
    return None


# ------------------------------------------------------------------
# Deterministic value normalization (no LLM anywhere)
# ------------------------------------------------------------------

_LAKH = re.compile(r"^([\d.]+)\s*(?:lakh|lac|l)$", re.IGNORECASE)
_CRORE = re.compile(r"^([\d.]+)\s*(?:crore|cr)$", re.IGNORECASE)
_THOUSAND = re.compile(r"^([\d.]+)\s*(?:thousand|k)$", re.IGNORECASE)
_BARE_NUMBER = re.compile(r"^[\d,]+(?:\.\d+)?$")


def normalize_number(value: Any) -> float | None:
    """Deterministic numeric normalization: native numbers pass through;
    Decimal (e.g. asyncpg Numeric round-trips) and strings strip currency
    symbols, Indian digit grouping, and lakh/crore/thousand words."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if not text:
        return None
    text = text.replace("₹", "").replace("rs.", "").replace("rs", "").replace("inr", "")
    text = text.strip()
    for pattern, multiplier in ((_LAKH, 100_000.0), (_CRORE, 10_000_000.0),
                                (_THOUSAND, 1_000.0)):
        match = pattern.match(text)
        if match:
            try:
                return float(match.group(1)) * multiplier
            except ValueError:
                return None
    if _BARE_NUMBER.match(text):
        try:
            return float(text.replace(",", ""))
        except ValueError:
            return None
    return None


def normalize_choice(value: Any, choices: tuple[str, ...] | None) -> str | None:
    """Map free text to one of the declared choice tokens (case/space
    insensitive, hyphen-normalized). None when no deterministic match."""
    if value is None or not isinstance(value, str):
        return None
    text = value.strip().upper().replace("-", "_").replace(" ", "_")
    if choices and text in choices:
        return text
    if not choices:
        return text
    return None


def canonical_fact_value(data_type: str, value: Any) -> str | None:
    """Serialize a canonical value into the deterministic TEXT form stored
    in tbl_profile_fact.fact_value (typed via data_type)."""
    if value is None:
        return None
    dtype = (data_type or "STRING").upper()
    if dtype == "BOOLEAN":
        return "TRUE" if value else "FALSE"
    if dtype == "INTEGER":
        return str(int(value))
    if dtype == "DECIMAL":
        number = float(value)
        return str(int(number)) if number.is_integer() else f"{number:.4f}".rstrip("0").rstrip(".")
    if dtype == "DATE":
        return value.isoformat() if isinstance(value, date) else str(value)
    if dtype == "JSON":
        import json

        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    text = str(value).strip()
    return text if text else None


def coerce_profile_value(entry: ProfileField, raw: Any) -> tuple[Any, str | None]:
    """
    Coerce one raw answer into the entry's canonical Python type.
    Returns (value, warning): value None means "nothing to store";
    a warning string means the answer could not be deterministically
    normalized (callers report it and skip storage — never guess).
    """
    if not is_answered(raw):
        return None, None

    dtype = entry.data_type
    if dtype == "STRING":
        if not isinstance(raw, str):
            raw = str(raw)
        text = raw.strip()
        if entry.choices:
            normalized = normalize_choice(text, entry.choices)
            if normalized is None:
                return None, (
                    f"value '{raw}' does not match allowed values "
                    f"{list(entry.choices)}"
                )
            return normalized, None
        return text, None
    if dtype in ("DECIMAL", "INTEGER"):
        number = normalize_number(raw)
        if number is None:
            return None, f"cannot deterministically parse numeric value {raw!r}"
        if dtype == "INTEGER":
            if not float(number).is_integer():
                return None, f"value {raw!r} is not an integer"
            return int(number), None
        return number, None
    if dtype == "BOOLEAN":
        if isinstance(raw, bool):
            return raw, None
        text = str(raw).strip().lower()
        if text in ("yes", "true", "1"):
            return True, None
        if text in ("no", "false", "0"):
            return False, None
        return None, f"cannot deterministically parse boolean value {raw!r}"
    if dtype == "DATE":
        if isinstance(raw, date):
            return raw, None
        if isinstance(raw, str):
            try:
                return date.fromisoformat(raw.strip()), None
            except ValueError:
                return None, f"cannot parse date value {raw!r}"
        return None, f"cannot parse date value {raw!r}"
    if dtype == "JSON":
        return raw, None
    return str(raw), None
