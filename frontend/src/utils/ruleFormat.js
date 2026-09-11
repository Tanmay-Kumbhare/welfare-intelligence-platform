// Translates the raw parameter/operator/value vocabulary used by the
// EligibilityEngine (backend/app/services/eligibility_engine.py) into
// plain-language sentences for citizens. This file only formats text —
// it never re-derives or alters eligibility semantics. The backend
// remains the sole source of truth for whether a rule passed or failed.

export const PARAMETER_LABELS = {
  age: "Age",
  gender: "Gender",
  citizen_type: "Citizen type",
  annual_income: "Annual family income",
  poverty_category: "Poverty category (ration card type)",
  land_holding_size: "Land holding size",
  is_bpl_card_holder: "BPL card",
  is_income_tax_payer: "Income-tax payer status",
  employment_status: "Employment status",
  social_category: "Social category",
  education_level: "Education level",
  disability_status: "Disability status",
  area_type: "Area type",
  state: "State",
};

export const VALUE_LABELS = {
  FARMER: "Farmer",
  STUDENT: "Student",
  SENIOR: "Senior Citizen",
  GENERAL: "General Citizen",
  MALE: "Male",
  FEMALE: "Female",
  OTHER: "Other",
  APL: "APL (Above Poverty Line)",
  BPL: "BPL (Below Poverty Line)",
  AAY: "AAY (Antyodaya Anna Yojana)",
  RURAL: "Rural",
  URBAN: "Urban",
  SEMI_URBAN: "Semi-Urban",
  GEN: "General",
  OBC: "OBC",
  SC: "SC",
  ST: "ST",
  NONE: "None",
  PHYSICALLY_DISABLED: "Physically disabled",
  VISUALLY_IMPAIRED: "Visually impaired",
  HEARING_IMPAIRED: "Hearing impaired",
  EMPLOYED: "Employed",
  UNEMPLOYED: "Unemployed",
  SELF_EMPLOYED: "Self-employed",
  RETIRED: "Retired",
  ILLITERATE: "Illiterate",
  PRIMARY: "Primary",
  SECONDARY: "Secondary (10th)",
  HIGHER_SECONDARY: "Higher Secondary (12th)",
  GRADUATE: "Graduate",
  POST_GRADUATE: "Post Graduate",
  true: "Yes",
  false: "No",
};

function labelValue(paramName, raw) {
  if (raw === null || raw === undefined || raw === "") return "Not provided";
  if (paramName === "annual_income") return formatCurrency(raw);
  if (paramName === "land_holding_size") return `${raw} hectares`;
  if (paramName === "age") return `${raw} years`;
  const key = String(raw);
  return VALUE_LABELS[key] || key.replace(/_/g, " ");
}

function labelRequiredList(paramName, requiredValue) {
  // IN-operator values are stored as a comma-separated string.
  return String(requiredValue)
    .split(",")
    .map((v) => labelValue(paramName, v.trim()))
    .join(" or ");
}

export function formatCurrency(value) {
  const num = Number(value);
  if (Number.isNaN(num)) return String(value);
  return `₹${num.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

const OPERATOR_PHRASES = {
  "<=": "must be",
  "<": "must be",
  ">=": "must be",
  ">": "must be",
  "==": "must be",
  "!=": "must not be",
  IN: "must be",
};

function operatorSuffix(operator) {
  switch (operator) {
    case "<=":
      return "or below";
    case "<":
      return "below";
    case ">=":
      return "or above";
    case ">":
      return "above";
    default:
      return "";
  }
}

/**
 * Turns a single rule (parameter_name, operator, required_value,
 * rule_description) into a citizen-readable sentence. Prefers the
 * backend-authored rule_description when present, since that is the
 * scheme author's own explanation; falls back to a generated sentence
 * built strictly from the rule's own fields otherwise.
 */
export function describeRule(rule) {
  if (rule.rule_description) return rule.rule_description;

  const label = PARAMETER_LABELS[rule.parameter_name] || rule.parameter_name;

  if (rule.operator === "IN") {
    return `${label} must be one of: ${labelRequiredList(rule.parameter_name, rule.required_value)}.`;
  }

  const valueLabel = labelValue(rule.parameter_name, rule.required_value);
  const phrase = OPERATOR_PHRASES[rule.operator] || "must satisfy";
  const suffix = operatorSuffix(rule.operator);

  return `${label} ${phrase} ${valueLabel}${suffix ? " " + suffix : ""}.`.replace(/\s+/g, " ");
}

/** Formats the citizen's actual value for a rule, for side-by-side display. */
export function describeActualValue(rule) {
  return labelValue(rule.parameter_name, rule.actual);
}

/** Formats the rule's required value, for side-by-side display. */
export function describeRequiredValue(rule) {
  const requiredValue = rule.required_value ?? rule.required;
  if (rule.operator === "IN") {
    return labelRequiredList(rule.parameter_name, requiredValue);
  }
  const suffix = operatorSuffix(rule.operator);
  const valueLabel = labelValue(rule.parameter_name, requiredValue);
  return suffix ? `${valueLabel} ${suffix}` : valueLabel;
}

export function parameterLabel(paramName) {
  return PARAMETER_LABELS[paramName] || paramName.replace(/_/g, " ");
}

export function documentLabel(documentType) {
  return documentType
    .split("_")
    .map((w) => w.charAt(0) + w.slice(1).toLowerCase())
    .join(" ");
}

export function categoryLabel(category) {
  if (!category) return "Other";
  return category.charAt(0) + category.slice(1).toLowerCase();
}
