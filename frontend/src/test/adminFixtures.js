// Admin fixtures matching backend response schemas:
//   SchemeOut / AdminSchemeDetailOut        (backend/app/api/v1/admin.py)
//   RuleGroupOut / RuleOut                  (rule section of admin.py)
//   DocumentOut                             (document section of admin.py)
//   SourceDocumentOut                       (source-documents section of admin.py)

export const SCHEME_DETAIL_FIELDS = {
  scheme_id: "s0000000-0000-0000-0000-000000000001",
  department_name: "Department of Education",
  scheme_category: "EDUCATION",
  description: "A test education scheme.",
  benefit_description: "Money for education.",
  status: "ACTIVE",
  official_source_url: "https://gov.example/scheme",
  application_url: "https://gov.example/apply",
  target_persona: "STUDENT",
  rule_count: 2,
};

export function schemeListItem(overrides = {}) {
  return {
    ...SCHEME_DETAIL_FIELDS,
    scheme_name: "Test Scholarship",
    ...overrides,
  };
}

export function schemeDetail(overrides = {}) {
  return {
    ...SCHEME_DETAIL_FIELDS,
    scheme_name: "Test Scholarship",
    start_date: "2026-01-01",
    end_date: "2026-12-31",
    last_verified_at: null,
    official_scheme_identifier: "TS-1",
    source_type: "MANUAL_SEED",
    source_name: "Seed data",
    source_url: null,
    application_window_type: "CONTINUOUS",
    group_combining_operator: "AND",
    scheme_version: 1,
    last_updated_at: "2026-10-01T00:00:00Z",
    rule_group_count: 1,
    document_count: 1,
    ...overrides,
  };
}

export const GROUP = {
  group_id: "g0000000-0000-0000-0000-000000000001",
  scheme_id: SCHEME_DETAIL_FIELDS.scheme_id,
  group_name: "Income gate",
  intra_group_operator: "AND",
  group_priority: 1,
  rules: [],
};

export function rule(overrides = {}) {
  return {
    rule_id: "r0000000-0000-0000-0000-000000000001",
    group_id: GROUP.group_id,
    scheme_id: SCHEME_DETAIL_FIELDS.scheme_id,
    parameter_name: "age",
    operator: ">=",
    required_value: "18",
    rule_description: "Must be an adult",
    rule_priority: 1,
    failure_stage_code: "S0_ELIGIBILITY",
    remedy_template: null,
    ...overrides,
  };
}

export const PROVENANCE = {
  rule_provenance_id: "p0000000-0000-0000-0000-000000000001",
  rule_id: "r0000000-0000-0000-0000-000000000001",
  source_text: "The applicant must be at least 18 years old.",
  document_url: "https://gov.example/scheme.pdf",
  verification_status: "PENDING",
  verified_at: null,
};

export function documentRequirement(overrides = {}) {
  return {
    document_id: "d0000000-0000-0000-0000-000000000001",
    scheme_id: SCHEME_DETAIL_FIELDS.scheme_id,
    document_type: "INCOME_CERTIFICATE",
    mandatory_flag: true,
    description: "Recent income certificate",
    ...overrides,
  };
}

export function sourceDocument(overrides = {}) {
  return {
    source_document_id: "00000000-0000-0000-0000-000000000009",
    source_id: "00000000-0000-0000-0000-000000000008",
    scheme_id: SCHEME_DETAIL_FIELDS.scheme_id,
    document_name: "Scheme circular 2026.pdf",
    document_url: "https://gov.example/files/circular.pdf",
    document_type: "PDF",
    version: 1,
    processing_status: "COMPLETED",
    retrieved_at: "2026-10-01T00:00:00Z",
    content_hash: "a".repeat(64),
    ...overrides,
  };
}

export function httpError(status, data) {
  const error = new Error("Request failed");
  error.response = { status, data };
  return error;
}
