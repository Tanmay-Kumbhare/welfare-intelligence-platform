/**
 * Frozen vocabularies mirrored from the BACKEND validation layer.
 *
 * Source of truth — do NOT invent extra values here:
 *   backend/app/services/rule_admin_service.py   (rule vocabularies)
 *   backend/app/services/scheme_admin_service.py (scheme metadata vocabularies)
 *   backend/app/services/document_admin_service.py (document types)
 *
 * The frontend uses these ONLY for usable editors (string inputs vs numeric
 * inputs vs boolean selects, list inputs for IN, dropdown options). Backend
 * validation remains authoritative — a value the UI accepts can still be
 * rejected by the server, and the server error is always surfaced.
 */

// ---- Eligibility rules (rule_admin_service.py) — frozen -----------------

export const ELIGIBILITY_RULE_PARAMETERS = [
  "age",
  "gender",
  "citizen_type",
  "annual_income",
  "poverty_category",
  "land_holding_size",
  "is_bpl_card_holder",
  "is_income_tax_payer",
  "employment_status",
  "social_category",
  "education_level",
  "disability_status",
  "area_type",
  "state",
  "tenth_percentage",
  "twelfth_percentage",
  "twelfth_percentile",
  "livestock_cattle_count",
  "livestock_poultry_count",
];

// Load-bearing: the required_value input type is chosen by which list the
// selected parameter belongs to. Keep in sync with the backend's constants.
export const NUMERIC_RULE_PARAMETERS = [
  "age",
  "annual_income",
  "land_holding_size",
  "tenth_percentage",
  "twelfth_percentage",
  "twelfth_percentile",
  "livestock_cattle_count",
  "livestock_poultry_count",
];

export const BOOLEAN_RULE_PARAMETERS = ["is_bpl_card_holder", "is_income_tax_payer"];

export const ELIGIBILITY_RULE_OPERATORS = ["<", "<=", ">", ">=", "==", "!=", "IN"];

// Comparison operators that make no sense against a boolean citizen value
// (backend rejects them; hidden up front so the admin never types them).
const BOOLEAN_INCOMPATIBLE_OPERATORS = ["<", "<=", ">", ">="];

export const GROUP_OPERATORS = ["AND", "OR"];

export const FAILURE_STAGE_CODES = [
  "S0_ELIGIBILITY",
  "S1_DOCUMENT_DISCREPANCY",
  "S2_DOMICILE_MISMATCH",
];

// ---- Scheme metadata (scheme_admin_service.py) ---------------------------

export const SCHEME_CATEGORIES = [
  "AGRICULTURE",
  "EDUCATION",
  "HEALTHCARE",
  "HOUSING",
  "PENSION",
  "ENERGY",
  "EMPLOYMENT",
];

export const SCHEME_PERSONAS = ["FARMER", "STUDENT", "SENIOR", "GENERAL"];

export const SCHEME_STATUSES = ["ACTIVE", "INACTIVE"];

export const SCHEME_SOURCE_TYPES = [
  "MANUAL_SEED",
  "GOVERNMENT_API",
  "GOVERNMENT_WEBSITE",
  "GOVERNMENT_PORTAL",
  "GOVERNMENT_PDF",
  "OTHER_AUTHORIZED_SOURCE",
];

export const APPLICATION_WINDOW_TYPES = [
  "FRESH_APPLICATION",
  "RENEWAL",
  "BOTH",
  "CONTINUOUS",
  "WINDOW_BASED",
];

// ---- Required documents (document_admin_service.py) ----------------------

export const REQUIRED_DOCUMENT_TYPES = [
  "AADHAAR",
  "BANK_PASSBOOK",
  "BPL_CARD",
  "CASTE_CERTIFICATE",
  "DISABILITY_CERTIFICATE",
  "DOMICILE_CERTIFICATE",
  "INCOME_CERTIFICATE",
  "LAND_RECORD",
  "MARKSHEET",
  "PHOTOGRAPH",
  "RATION_CARD",
  "VOTER_ID",
];

// ---- Rule value input type ----------------------------------------------

/**
 * Which editor the required_value should get for this parameter/operator
 * combination. Backend stays authoritative: numeric/boolean checks here are
 * UX affordances that PREVENT typos — the server re-validates everything and
 * its error surfaces verbatim when it disagrees.
 *
 * IN always wins over the parameter type (mirrors the backend: numeric and
 * boolean constraints do not apply to IN comparisons).
 */
export function requiredValueKind(parameterName, operator) {
  if (operator === "IN") return "list";
  if (NUMERIC_RULE_PARAMETERS.includes(parameterName)) return "numeric";
  if (BOOLEAN_RULE_PARAMETERS.includes(parameterName)) return "boolean";
  return "text";
}

/** Operators valid for the given parameter (backend semantics mirrored). */
export function operatorsForParameter(parameterName, operator) {
  if (!parameterName) return ELIGIBILITY_RULE_OPERATORS;
  if (operator === "IN") return ELIGIBILITY_RULE_OPERATORS;
  if (BOOLEAN_RULE_PARAMETERS.includes(parameterName)) {
    return ELIGIBILITY_RULE_OPERATORS.filter(
      (op) => !BOOLEAN_INCOMPATIBLE_OPERATORS.includes(op)
    );
  }
  return ELIGIBILITY_RULE_OPERATORS;
}

/** Boolean yes/no pairs the backend accepts as true/1/yes, false/0/no. */
export const BOOLEAN_VALUE_OPTIONS = [
  { value: "true", label: "true (1 / yes)" },
  { value: "false", label: "false (0 / no)" },
];
