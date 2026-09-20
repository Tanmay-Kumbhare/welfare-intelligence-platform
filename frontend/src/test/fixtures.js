// Fixtures matching the backend Phase 2A/2B response schemas (app/schemas/form.py).
// Kept minimal but structurally exact: FormDetail → sections → questions →
// options/conditions, and SubmissionResponse with typed answers.
//
// Mirrors GENERAL_CITIZEN_PROFILE v3: NO identity questions (FULL_NAME /
// DATE_OF_BIRTH / GENDER) — identity is established at profile creation and
// shown read-only by the page.

const q = (id, code, overrides = {}) => ({
  question_id: id,
  question_code: code,
  question_text: overrides.question_text || `Question ${code}`,
  question_type: overrides.question_type || "text",
  data_type: overrides.data_type || "STRING",
  required: overrides.required ?? false,
  display_order: overrides.display_order ?? 1,
  profile_field: overrides.profile_field || null,
  validation_rule: overrides.validation_rule || null,
  help_text: overrides.help_text || null,
  placeholder: null,
  options: overrides.options || [],
  conditions: overrides.conditions || [],
});

const opt = (id, code, label, order) => ({
  option_id: id,
  option_code: code,
  option_label: label,
  display_order: order,
});

export const FORM_DETAIL = {
  form_id: "f0000000-0000-0000-0000-000000000001",
  form_code: "GENERAL_CITIZEN_PROFILE",
  form_name: "Citizen Profile",
  description: "Tell us about your household and situation to find schemes you may be eligible for.",
  target_citizen_type: "GENERAL",
  version: 3,
  status: "ACTIVE",
  sections: [
    {
      section_id: "s0000000-0000-0000-0000-000000000001",
      section_code: "PERSONAL_INFO",
      section_name: "Personal Information",
      description: "Household and social context.",
      display_order: 1,
      questions: [
        q("q0000000-0000-0000-0000-000000000001", "MARITAL_STATUS", {
          question_text: "What is your marital status?",
          question_type: "dropdown",
          required: false,
          options: [
            opt("o0000000-0000-0000-0000-000000000001", "SINGLE", "Single", 1),
            opt("o0000000-0000-0000-0000-000000000002", "MARRIED", "Married", 2),
          ],
        }),
      ],
    },
    {
      section_id: "s0000000-0000-0000-0000-000000000002",
      section_code: "EDUCATION",
      section_name: "Education",
      description: "Your study status.",
      display_order: 2,
      questions: [
        q("q0000000-0000-0000-0000-000000000010", "CURRENTLY_STUDYING", {
          question_text: "Are you currently studying?",
          question_type: "boolean",
          data_type: "BOOLEAN",
          required: false,
          options: [
            opt("o0000000-0000-0000-0000-000000000010", "YES", "Yes", 1),
            opt("o0000000-0000-0000-0000-000000000011", "NO", "No", 2),
          ],
        }),
        q("q0000000-0000-0000-0000-000000000011", "COURSE_NAME", {
          question_text: "Which course are you studying?",
          required: true,
          conditions: [
            {
              condition_id: "c0000000-0000-0000-0000-000000000001",
              question_id: "q0000000-0000-0000-0000-000000000011",
              depends_on_question_id: "q0000000-0000-0000-0000-000000000010",
              depends_on_question_code: "CURRENTLY_STUDYING",
              operator: "EQUALS",
              comparison_value: "YES",
              action: "SHOW",
              condition_group: 1,
            },
          ],
        }),
      ],
    },
    {
      section_id: "s0000000-0000-0000-0000-000000000003",
      section_code: "FINANCIAL",
      section_name: "Financial",
      description: "Income details.",
      display_order: 3,
      questions: [
        q("q0000000-0000-0000-0000-000000000020", "ANNUAL_INCOME", {
          question_text: "What is your annual family income (in rupees)?",
          question_type: "decimal",
          data_type: "DECIMAL",
          required: true,
          validation_rule: { min: 0 },
        }),
        q("q0000000-0000-0000-0000-000000000021", "PINCODE", {
          question_text: "What is your postal PIN code?",
          data_type: "STRING",
          required: false,
          validation_rule: { pattern: "[1-9][0-9]{5}" },
        }),
      ],
    },
  ],
};

const answer = (question_id, column, value) => ({
  answer_id: `a0000000-0000-0000-0000-${question_id.slice(-8)}`,
  question_id,
  question_code: null,
  answer_text: column === "answer_text" ? value : null,
  answer_number: column === "answer_number" ? value : null,
  answer_decimal: column === "answer_decimal" ? value : null,
  answer_boolean: column === "answer_boolean" ? value : null,
  answer_date: column === "answer_date" ? value : null,
  answer_json: column === "answer_json" ? value : null,
  source: "USER_INPUT",
  confidence: null,
  updated_at: "2026-09-16T10:00:00Z",
});

// Wrap a raw value as the typed answer row the backend would return for the
// given question — used by update/complete mocks to echo saved answers.
export function typedAnswer(questionId, value) {
  const question = FORM_DETAIL.sections.flatMap((s) => s.questions).find((q) => q.question_id === questionId);
  const row = {
    answer_id: `a0000000-0000-0000-0000-${questionId.slice(-8)}`,
    question_id: questionId,
    question_code: question?.question_code ?? null,
    answer_text: null,
    answer_number: null,
    answer_decimal: null,
    answer_boolean: null,
    answer_date: null,
    answer_json: null,
    source: "USER_INPUT",
    confidence: null,
    updated_at: "2026-09-16T10:00:00Z",
  };
  if (typeof value === "boolean") row.answer_boolean = value;
  else if (typeof value === "number") {
    if ((question?.data_type || "").toUpperCase() === "DECIMAL") row.answer_decimal = value;
    else row.answer_number = value;
  } else if (typeof value === "string") {
    if ((question?.data_type || "").toUpperCase() === "DATE") row.answer_date = value;
    else row.answer_text = value;
  } else if (Array.isArray(value)) row.answer_json = value;
  return row;
}

export function submissionResponse(overrides = {}) {
  return {
    submission_id: "sub00000-0000-0000-0000-000000000001",
    citizen_id: "c0000000-0000-0000-0000-000000000001",
    form_id: FORM_DETAIL.form_id,
    form_code: "GENERAL_CITIZEN_PROFILE",
    form_version: 3,
    status: overrides.status || "IN_PROGRESS",
    completion_percentage: overrides.completion_percentage ?? 0,
    started_at: "2026-09-16T10:00:00Z",
    completed_at: overrides.completed_at || null,
    applicable_questions: overrides.applicable_questions ?? 5,
    answered_questions: overrides.answered_questions ?? 0,
    missing_required: overrides.missing_required ?? [],
    answers: overrides.answers ?? [],
  };
}

export const CITIZEN = {
  citizen_id: "c0000000-0000-0000-0000-000000000001",
  full_name: "Test Citizen",
  citizen_type: "GENERAL",
};

export function httpError(status, data) {
  const error = new Error("Request failed");
  error.response = { status, data };
  return error;
}
