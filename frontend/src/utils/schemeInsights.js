// All functions here operate on the scheme array returned by
// GET /api/v1/schemes/ (schemeService.getAll()). They only aggregate or
// filter data that already came from the backend — they never invent
// counts, schemes, or rules.

/** Unique scheme categories present in the real data, with a live count each. */
export function deriveCategoryCounts(schemes) {
  const counts = new Map();
  for (const s of schemes) {
    const key = s.scheme_category || "OTHER";
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return Array.from(counts.entries()).map(([category, count]) => ({ category, count }));
}

// A citizen-type "lens" maps a homepage discovery category to the real
// eligibility-rule parameter(s) it corresponds to. This lets us honestly
// say "N schemes have rules that consider this factor" for categories
// that are not real backend citizen_type values, without inventing new
// eligibility logic — see Part 3 / Part 6 of the product brief.
export const CITIZEN_TYPE_LENSES = {
  employment_status: {
    parameterNames: ["employment_status"],
  },
  gender: {
    parameterNames: ["gender"],
    requiredValues: ["FEMALE"],
  },
  disability_status: {
    parameterNames: ["disability_status"],
    requiredValues: ["PHYSICALLY_DISABLED", "VISUALLY_IMPAIRED", "HEARING_IMPAIRED"],
  },
  social_category: {
    parameterNames: ["social_category"],
    requiredValues: ["ST"],
  },
  area_type: {
    parameterNames: ["area_type"],
    requiredValues: ["RURAL"],
  },
};

export const DISCOVERY_FILTERS = [
  { value: "FARMER", label: "Farmer", kind: "persona" },
  { value: "STUDENT", label: "Student", kind: "persona" },
  { value: "SENIOR", label: "Senior Citizen", kind: "persona" },
  { value: "GENERAL", label: "General Citizen", kind: "persona" },
  { value: "employment_status", label: "Worker / Labour", kind: "lens" },
  { value: "gender", label: "Women", kind: "lens" },
  { value: "disability_status", label: "PwD", kind: "lens" },
  { value: "social_category", label: "Tribal / Indigenous", kind: "lens" },
  { value: "area_type", label: "Rural Household", kind: "lens" },
];

function schemeRules(scheme) {
  const rules = [];
  for (const group of scheme.rule_groups || []) {
    for (const rule of group.rules || []) {
      rules.push(rule);
    }
  }
  return rules;
}

/**
 * Counts how many real schemes have at least one eligibility rule that
 * reads the given parameter(s). Used for the "discovery filter" citizen
 * types (Worker/Labour, Women, PwD, Tribal/Indigenous, Rural Household)
 * that don't map to a real citizen_type column.
 */
export function countSchemesByLens(schemes, lensKey) {
  const lens = CITIZEN_TYPE_LENSES[lensKey];
  if (!lens) return 0;

  return schemes.filter((s) => {
    return schemeRules(s).some((rule) => {
      if (!lens.parameterNames.includes(rule.parameter_name)) return false;
      if (!lens.requiredValues) return true;

      const values = String(rule.required_value)
        .split(",")
        .map((value) => value.trim());
      return lens.requiredValues.some((value) => values.includes(value));
    });
  }).length;
}

/** Counts real schemes whose rules reference citizen_type == value (e.g. FARMER). */
export function countSchemesByCitizenType(schemes, citizenType) {
  return schemes.filter((s) =>
    (s.rule_groups || []).some((g) =>
      (g.rules || []).some(
        (r) => r.parameter_name === "citizen_type" && r.required_value === citizenType
      )
    )
  ).length;
}

/** Matches a scheme to a real persona tag or a rule-grounded discovery lens. */
export function matchesDiscoveryFilter(scheme, detail, filterValue) {
  const filter = DISCOVERY_FILTERS.find((item) => item.value === filterValue);
  if (!filter) return true;
  if (filter.kind === "persona") {
    if (detail && countSchemesByCitizenType([detail], filter.value) > 0) return true;
    return scheme.target_persona === filter.value;
  }
  return countSchemesByLens(detail ? [detail] : [], filter.value) > 0;
}
