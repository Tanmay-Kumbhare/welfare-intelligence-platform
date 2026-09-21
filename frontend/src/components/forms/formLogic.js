/**
 * Pure form-state logic for the dynamic form (Phase 2C Step 5).
 *
 * Presentation-level applicability and progress mirroring the backend's
 * deterministic condition semantics (backend/app/services/form_logic.py):
 *   - conditions sharing one condition_group are ANDed; groups are ORed
 *   - SHOW/HIDE/REQUIRE actions
 *   - a hidden dependency counts as unanswered → chains cascade
 *
 * The backend remains the final validation authority — nothing here blocks a
 * save (drafts never enforce required), it only guides the citizen. No
 * question catalogue is duplicated here: everything is derived from the API's
 * form definition.
 */

// Backend answer_value() extraction priority order.
const TYPED_VALUE_KEYS = ["answer_json", "answer_date", "answer_boolean", "answer_decimal", "answer_number", "answer_text"];

const TRUTHY = new Set(["yes", "true", "1"]);
const FALSY = new Set(["no", "false", "0"]);

export function answerValue(answer) {
  if (!answer) return null;
  for (const key of TYPED_VALUE_KEYS) {
    if (answer[key] !== null && answer[key] !== undefined) return answer[key];
  }
  return null;
}

export function isAnswered(value) {
  if (value === null || value === undefined) return false;
  if (typeof value === "string" && value.trim() === "") return false;
  if (Array.isArray(value) && value.length === 0) return false;
  return true;
}

function toNumber(value) {
  if (typeof value === "boolean") return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value.trim());
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function toDate(value) {
  if (value instanceof Date) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = new Date(value.trim());
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }
  return null;
}

function looseEqual(value, comparison) {
  if (value === null || value === undefined || comparison === null || comparison === undefined) return false;
  if (typeof value === "boolean") {
    const token = String(comparison).trim().toLowerCase();
    if (TRUTHY.has(token)) return value === true;
    if (FALSY.has(token)) return value === false;
    return false;
  }
  if (typeof value === "number") {
    const other = toNumber(comparison);
    return other !== null && value === other;
  }
  if (value instanceof Date) {
    const other = toDate(comparison);
    return other !== null && value.getTime() === other.getTime();
  }
  return String(value).trim().toLowerCase() === String(comparison).trim().toLowerCase();
}

export function conditionSatisfied(condition, dependencyValue) {
  const operator = (condition.operator || "").toUpperCase();
  const comparison = condition.comparison_value;

  if (operator === "IS_EMPTY") return !isAnswered(dependencyValue);
  if (operator === "IS_NOT_EMPTY") return isAnswered(dependencyValue);

  if (operator === "IN" || operator === "NOT_IN") {
    const allowed = (comparison || "")
      .split(",")
      .map((c) => c.trim())
      .filter(Boolean);
    const values = Array.isArray(dependencyValue) ? dependencyValue : [dependencyValue];
    const member = values.some((v) => allowed.some((option) => looseEqual(v, option)));
    return operator === "IN" ? member : !member;
  }

  if (dependencyValue === null || dependencyValue === undefined) return false;

  if (operator === "EQUALS") return looseEqual(dependencyValue, comparison);
  if (operator === "NOT_EQUALS") return !looseEqual(dependencyValue, comparison);

  // Ordering: numeric first, then date.
  let left = toNumber(dependencyValue);
  let right = toNumber(comparison);
  if (left === null || right === null) {
    const leftDate = toDate(dependencyValue);
    const rightDate = toDate(comparison);
    if (leftDate === null || rightDate === null) return false;
    left = leftDate.getTime();
    right = rightDate.getTime();
  }
  if (operator === "GREATER_THAN") return left > right;
  if (operator === "LESS_THAN") return left < right;
  if (operator === "GREATER_THAN_OR_EQUAL") return left >= right;
  if (operator === "LESS_THAN_OR_EQUAL") return left <= right;
  return false;
}

function groupsSatisfied(groups, valueOf) {
  // Groups ORed; conditions within a group ANDed.
  return Object.values(groups).some((rows) => rows.every((condition) => conditionSatisfied(condition, valueOf(condition.depends_on_question_id))));
}

/**
 * Visibility map { question_id: boolean } over the full form hierarchy,
 * iterated to a fixed point so conditional chains resolve deterministically.
 * A hidden dependency counts as unanswered, matching backend semantics.
 */
export function computeApplicableMap(sections, answersByQuestionId) {
  const allQuestions = sections.flatMap((s) => s.questions);
  const byId = new Map(allQuestions.map((q) => [q.question_id, q]));
  const conditionsByTarget = new Map();
  for (const question of allQuestions) {
    for (const condition of question.conditions || []) {
      if (byId.has(condition.depends_on_question_id)) {
        const list = conditionsByTarget.get(question.question_id) || [];
        list.push(condition);
        conditionsByTarget.set(question.question_id, list);
      }
    }
  }

  const applicable = new Map(allQuestions.map((q) => [q.question_id, true]));
  const valueOf = (depQid) => (applicable.get(depQid, true) ? answersByQuestionId.get(depQid) ?? null : null);

  for (let pass = 0; pass <= allQuestions.length; pass += 1) {
    let changed = false;
    for (const question of allQuestions) {
      const rows = conditionsByTarget.get(question.question_id);
      if (!rows) continue;
      const showGroups = {};
      const hideGroups = {};
      for (const condition of rows) {
        const action = (condition.action || "SHOW").toUpperCase();
        if (action === "SHOW") (showGroups[condition.condition_group] ||= []).push(condition);
        else if (action === "HIDE") (hideGroups[condition.condition_group] ||= []).push(condition);
        // REQUIRE affects required-ness, not visibility.
      }
      let visible = true;
      if (Object.keys(showGroups).length > 0) visible = groupsSatisfied(showGroups, valueOf);
      if (visible && Object.keys(hideGroups).length > 0 && groupsSatisfied(hideGroups, valueOf)) visible = false;
      if (applicable.get(question.question_id) !== visible) {
        applicable.set(question.question_id, visible);
        changed = true;
      }
    }
    if (!changed) break;
  }
  return applicable;
}

export function computeRequiredIds(sections, answersByQuestionId, applicable) {
  const required = new Set();
  for (const question of sections.flatMap((s) => s.questions)) {
    if (question.required) {
      required.add(question.question_id);
      continue;
    }
    for (const condition of question.conditions || []) {
      if ((condition.action || "").toUpperCase() !== "REQUIRE") continue;
      if (!applicable.get(condition.depends_on_question_id, true)) continue;
      if (conditionSatisfied(condition, answersByQuestionId.get(condition.depends_on_question_id) ?? null)) {
        required.add(question.question_id);
        break;
      }
    }
  }
  return required;
}

/** Progress over applicable questions only — hidden ones never count. */
export function computeProgress(sections, answersByQuestionId, applicable) {
  const questions = sections.flatMap((s) => s.questions);
  const applicableQuestions = questions.filter((q) => applicable.get(q.question_id, true));
  const required = computeRequiredIds(sections, answersByQuestionId, applicable);
  const missingRequired = applicableQuestions
    .filter((q) => required.has(q.question_id) && !isAnswered(answersByQuestionId.get(q.question_id)))
    .map((q) => q.question_code)
    .sort();
  return {
    total: applicableQuestions.length,
    answered: applicableQuestions.filter((q) => isAnswered(answersByQuestionId.get(q.question_id))).length,
    missingRequired,
  };
}

export function percentage(answered, total) {
  return total === 0 ? 0 : Math.round((answered / total) * 100);
}

/** The stored answer value of a question from a SubmissionResponse. */
export function storedAnswersByQuestionId(submission) {
  const map = new Map();
  for (const answer of submission?.answers || []) map.set(answer.question_id, answerValue(answer));
  return map;
}

/** Per-section progress for step indicators. */
export function sectionProgress(section, answersByQuestionId, applicable) {
  const applicableQuestions = section.questions.filter((q) => applicable.get(q.question_id, true));
  return {
    total: applicableQuestions.length,
    answered: applicableQuestions.filter((q) => isAnswered(answersByQuestionId.get(q.question_id))).length,
  };
}

/**
 * Local, definition-driven validation — guidance only, never a save blocker.
 * Reads the same validation_rule JSONB the backend enforces:
 *   { min, max, min_length, max_length, pattern, email }
 */
export function validateQuestionValue(question, value) {
  if (isAnswered(value) && question.required === false) {
    // Optional but filled — still worth checking format below.
  }
  if (!isAnswered(value)) return null; // required-ness handled by completion
  const rules = question.validation_rule || {};
  if (typeof value === "string") {
    if (rules.min_length !== undefined && value.length < rules.min_length) {
      return `Please enter at least ${rules.min_length} characters.`;
    }
    if (rules.max_length !== undefined && value.length > rules.max_length) {
      return `Please enter at most ${rules.max_length} characters.`;
    }
    if (rules.email) {
      return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value) ? null : "Please enter a valid email address.";
    }
    if (rules.pattern) {
      try {
        if (!new RegExp(`^(?:${rules.pattern})$`).test(value)) return "Please enter a value in the correct format.";
      } catch {
        // Broken pattern in the definition — never block the citizen on it.
      }
    }
  }
  if (!["string", "boolean"].includes(typeof value)) {
    const numeric = toNumber(value);
    if (numeric !== null) {
      if (rules.min !== undefined && numeric < rules.min) return `Please enter a value of at least ${rules.min}.`;
      if (rules.max !== undefined && numeric > rules.max) return `Please enter a value of at most ${rules.max}.`;
    }
  }
  return null;
}

/**
 * Human message for a backend 422 AnswerValidationError / completion error.
 * The backend detail is { message, missing_required? } or { detail: {...} }
 * after axios unwraps; map missing codes to the citizen's own questions.
 */
export function backendErrorMessage(error, sections) {
  const detail = error?.response?.data?.detail ?? error?.response?.data;
  const byCode = new Map(sections.flatMap((s) => s.questions).map((q) => [q.question_code, q]));
  const missing = detail?.missing_required || [];
  if (Array.isArray(missing) && missing.length > 0) {
    const labels = missing.map((code) => byCode.get(code)?.question_text || code);
    const shown = labels.slice(0, 4).join(", ");
    const more = labels.length > 4 ? ` and ${labels.length - 4} more` : "";
    return `Please answer the required questions: ${shown}${more}.`;
  }
  if (typeof detail?.message === "string") return detail.message;
  if (typeof error?.response?.data?.detail === "string") return error.response.data.detail;
  return "Something went wrong while saving. Please check your answers and try again.";
}
