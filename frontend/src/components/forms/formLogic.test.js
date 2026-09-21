import { describe, expect, it } from "vitest";
import {
  conditionSatisfied,
  computeApplicableMap,
  computeProgress,
  percentage,
  validateQuestionValue,
  backendErrorMessage,
  storedAnswersByQuestionId,
} from "./formLogic";
import { FORM_DETAIL, submissionResponse } from "../../test/fixtures";

const byCode = (code) => FORM_DETAIL.sections.flatMap((s) => s.questions).find((q) => q.question_code === code);

function answers(...pairs) {
  const map = new Map();
  for (const [code, value] of pairs) map.set(byCode(code).question_id, value);
  return map;
}

describe("conditionSatisfied", () => {
  const cond = (operator, comparison = null) => ({ operator, comparison_value: comparison, condition_group: 1 });

  it("EQUALS matches booleans against YES/NO strings", () => {
    expect(conditionSatisfied(cond("EQUALS", "YES"), true)).toBe(true);
    expect(conditionSatisfied(cond("EQUALS", "YES"), false)).toBe(false);
  });

  it("NOT_EQUALS and case-insensitive strings", () => {
    expect(conditionSatisfied(cond("NOT_EQUALS", "MALE"), "FEMALE")).toBe(true);
    expect(conditionSatisfied(cond("EQUALS", "male"), "MALE")).toBe(true);
  });

  it("IN / NOT_IN work with comma-separated lists and multi answers", () => {
    expect(conditionSatisfied(cond("IN", "BPL,AAY"), "BPL")).toBe(true);
    expect(conditionSatisfied(cond("NOT_IN", "BPL,AAY"), "APL")).toBe(true);
    expect(conditionSatisfied(cond("IN", "BPL,AAY"), ["APL", "AAY"])).toBe(true);
  });

  it("IS_EMPTY / IS_NOT_EMPTY", () => {
    expect(conditionSatisfied(cond("IS_EMPTY"), "")).toBe(true);
    expect(conditionSatisfied(cond("IS_NOT_EMPTY"), "x")).toBe(true);
  });

  it("ordering operators compare numerically", () => {
    expect(conditionSatisfied(cond("GREATER_THAN", "60"), 65)).toBe(true);
    expect(conditionSatisfied(cond("GREATER_THAN", "60"), 55)).toBe(false);
    expect(conditionSatisfied(cond("LESS_THAN_OR_EQUAL", "250000"), 240000)).toBe(true);
  });

  it("ordering operators fall back to dates", () => {
    expect(conditionSatisfied(cond("GREATER_THAN", "2010-01-01"), "2000-05-05")).toBe(false);
    expect(conditionSatisfied(cond("GREATER_THAN", "1990-01-01"), "2000-05-05")).toBe(true);
  });

  it("unanswered dependency satisfies nothing except emptiness checks", () => {
    expect(conditionSatisfied(cond("EQUALS", "YES"), null)).toBe(false);
    expect(conditionSatisfied(cond("IS_EMPTY"), null)).toBe(true);
  });
});

describe("computeApplicableMap", () => {
  it("shows conditional questions only when the SHOW condition holds", () => {
    const hidden = computeApplicableMap(FORM_DETAIL.sections, answers(["CURRENTLY_STUDYING", false]));
    expect(hidden.get(byCode("COURSE_NAME").question_id)).toBe(false);
    expect(hidden.get(byCode("MARITAL_STATUS").question_id)).toBe(true);

    const shown = computeApplicableMap(FORM_DETAIL.sections, answers(["CURRENTLY_STUDYING", true]));
    expect(shown.get(byCode("COURSE_NAME").question_id)).toBe(true);
  });
});

describe("computeProgress", () => {
  it("excludes hidden questions from the denominator", () => {
    const applicableMap = computeApplicableMap(FORM_DETAIL.sections, answers(["CURRENTLY_STUDYING", false]));
    const stats = computeProgress(
      FORM_DETAIL.sections,
      answers(
        ["CURRENTLY_STUDYING", false],
        ["MARITAL_STATUS", "MARRIED"],
        ["ANNUAL_INCOME", 240000],
      ),
      applicableMap,
    );
    // Applicable: marital status, studying, income, pincode = 4 (course hidden)
    // Answered: marital + income + studying(false counts as answered) = 3
    expect(stats.total).toBe(4);
    expect(stats.answered).toBe(3);
    expect(percentage(stats.answered, stats.total)).toBe(75);
  });

  it("counts hidden required questions as satisfied", () => {
    const applicableMap = computeApplicableMap(FORM_DETAIL.sections, answers(["CURRENTLY_STUDYING", false]));
    const stats = computeProgress(FORM_DETAIL.sections, answers(["CURRENTLY_STUDYING", false]), applicableMap);
    expect(stats.missingRequired).toEqual(["ANNUAL_INCOME"]);
    // COURSE_NAME (required, hidden) is NOT in the list.
    expect(stats.missingRequired).not.toContain("COURSE_NAME");
  });
});

describe("validateQuestionValue", () => {
  it("enforces min/max, length, pattern, and email rules from the definition", () => {
    const income = byCode("ANNUAL_INCOME");
    expect(validateQuestionValue(income, -5)).toMatch(/at least 0/);
    expect(validateQuestionValue(income, 1000)).toBeNull();

    const pincode = byCode("PINCODE");
    expect(validateQuestionValue(pincode, "41")).toMatch(/correct format/);
    expect(validateQuestionValue(pincode, "411001")).toBeNull();
  });

  it("unanswered values are left to completion validation", () => {
    expect(validateQuestionValue(byCode("ANNUAL_INCOME"), null)).toBeNull();
  });
});

describe("backendErrorMessage", () => {
  it("maps missing_required codes to human question text", () => {
    const error = { response: { status: 422, data: { detail: { message: "Incomplete", missing_required: ["ANNUAL_INCOME"] } } } };
    expect(backendErrorMessage(error, FORM_DETAIL.sections)).toMatch(/annual family income/i);
  });

  it("passes through backend messages and falls back gracefully", () => {
    expect(backendErrorMessage({ response: { data: { detail: { message: "No longer editable" } } } }, [])).toMatch(/No longer editable/);
    expect(backendErrorMessage({}, [])).toMatch(/Something went wrong/);
  });
});

describe("storedAnswersByQuestionId", () => {
  it("extracts native values from typed answer columns", () => {
    const submission = submissionResponse({
      answers: [
        { question_id: "q0000000-0000-0000-0000-000000000001", answer_text: "Asha", answer_number: null, answer_decimal: null, answer_boolean: null, answer_date: null, answer_json: null },
        { question_id: "q0000000-0000-0000-0000-000000000020", answer_text: null, answer_number: null, answer_decimal: 240000, answer_boolean: null, answer_date: null, answer_json: null },
      ],
    });
    const map = storedAnswersByQuestionId(submission);
    expect(map.get("q0000000-0000-0000-0000-000000000001")).toBe("Asha");
    expect(map.get("q0000000-0000-0000-0000-000000000020")).toBe(240000);
  });
});
