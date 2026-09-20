"""
Pure form logic for Phase 2A: condition evaluation, question applicability,
typed-answer validation/mapping, and completion computation.

No database access here — every function operates on already-loaded ORM
question/option/condition objects and plain Python values, so the logic is
deterministic, reusable, and testable in isolation. The form and submission
services call into this module; routers never do.

Condition semantics (tbl_form_condition):
  - A condition is evaluated against the answer of depends_on_question_id.
  - Rows sharing one condition_group are ANDed; different groups are ORed.
  - action=SHOW   → the question is visible only when a group is satisfied.
  - action=HIDE   → the question is hidden when a group is satisfied.
  - action=REQUIRE → the question becomes required when a group is satisfied
    (on top of its static `required` flag).
  - A dependency that is itself hidden is treated as unanswered, so
    conditional chains cascade deterministically.
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any, Mapping, NamedTuple, Sequence

from app.models.form import FormCondition, FormQuestion
from app.models.submission import ANSWER_SOURCES, FormAnswer


# ------------------------------------------------------------------
# Service errors (mapped to HTTP responses by the router; messages are
# always safe, user-facing text — never raw database errors)
# ------------------------------------------------------------------


class FormServiceError(Exception):
    """Base class for form-domain errors carrying an HTTP status."""

    status_code = 500
    message = "Form service error"

    def __init__(self, message: str | None = None, *, extra: dict | None = None) -> None:
        super().__init__(message or self.message)
        if message:
            self.message = message
        self.extra = extra or {}

    def to_detail(self) -> dict:
        return {"message": self.message, **self.extra}


class FormNotFoundError(FormServiceError):
    status_code = 404
    message = "Form not found"


class FormVersionNotFoundError(FormServiceError):
    status_code = 404
    message = "Form version not found"


class CitizenNotFoundError(FormServiceError):
    status_code = 404
    message = "Citizen not found"


class SubmissionNotFoundError(FormServiceError):
    status_code = 404
    message = "Submission not found"


class SubmissionOwnershipError(FormServiceError):
    status_code = 403
    message = "Submission belongs to another citizen"


class SubmissionNotEditableError(FormServiceError):
    status_code = 409
    message = "Submission can no longer be modified"


class InvalidStatusTransitionError(FormServiceError):
    status_code = 409
    message = "Invalid submission status transition"


class QuestionNotInFormError(FormServiceError):
    status_code = 422
    message = "Question does not belong to this submission's form version"


class AnswerValidationError(FormServiceError):
    status_code = 422
    message = "Invalid answer"


class IncompleteSubmissionError(FormServiceError):
    status_code = 422
    message = "Submission is incomplete: applicable required questions are unanswered"


# ------------------------------------------------------------------
# Value helpers
# ------------------------------------------------------------------

_TRUTHY = {"yes", "true", "1"}
_FALSY = {"no", "false", "0"}

# Typed answer columns in FormAnswer, in extraction priority order.
TYPED_ANSWER_COLUMNS = (
    "answer_json",
    "answer_date",
    "answer_boolean",
    "answer_decimal",
    "answer_number",
    "answer_text",
)


def _to_float(value: Any) -> float | None:
    """Best-effort numeric coercion; None when not numeric."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _to_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def _loose_equal(value: Any, comparison: str | None) -> bool:
    """Type-tolerant equality between an answer value and a stored
    comparison string (booleans map to YES/NO, numbers compare numerically,
    strings compare case-insensitively)."""
    if value is None or comparison is None:
        return False
    if isinstance(value, bool):
        token = comparison.strip().lower()
        if token in _TRUTHY:
            return value is True
        if token in _FALSY:
            return value is False
        return False
    if isinstance(value, (int, float)):
        other = _to_float(comparison)
        return other is not None and float(value) == other
    if isinstance(value, date):
        other = _to_date(comparison)
        return other is not None and value == other
    return str(value).strip().casefold() == str(comparison).strip().casefold()


def is_answered(value: Any) -> bool:
    """A value counts as answered when present and non-empty."""
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    if isinstance(value, (list, dict)) and len(value) == 0:
        return False
    return True


def answer_value(answer: FormAnswer) -> Any:
    """Extract the native Python value from a FormAnswer row."""
    for column in TYPED_ANSWER_COLUMNS:
        value = getattr(answer, column)
        if value is not None:
            return value
    return None


# ------------------------------------------------------------------
# Condition evaluation
# ------------------------------------------------------------------


def condition_satisfied(condition: FormCondition, dependency_value: Any) -> bool:
    """Evaluate one condition row against a dependency answer value."""
    operator = (condition.operator or "").upper()
    comparison = condition.comparison_value

    if operator in ("IS_EMPTY", "IS_NOT_EMPTY"):
        empty = not is_answered(dependency_value)
        return empty if operator == "IS_EMPTY" else not empty

    if operator in ("IN", "NOT_IN"):
        allowed = [c.strip() for c in (comparison or "").split(",") if c.strip()]
        values = dependency_value if isinstance(dependency_value, list) else [dependency_value]
        member = any(_loose_equal(v, option) for v in values for option in allowed)
        return member if operator == "IN" else not member

    if dependency_value is None:
        return False

    if operator == "EQUALS":
        return _loose_equal(dependency_value, comparison)
    if operator == "NOT_EQUALS":
        return not _loose_equal(dependency_value, comparison)

    # Ordering operators: numeric comparison first, then date comparison.
    left, right = _to_float(dependency_value), _to_float(comparison)
    if left is None or right is None:
        left_d, right_d = _to_date(dependency_value), _to_date(comparison)
        if left_d is None or right_d is None:
            return False
        left, right = left_d, right_d

    if operator == "GREATER_THAN":
        return left > right
    if operator == "LESS_THAN":
        return left < right
    if operator == "GREATER_THAN_OR_EQUAL":
        return left >= right
    if operator == "LESS_THAN_OR_EQUAL":
        return left <= right
    return False


def _groups_satisfied(
    groups: dict[int, list[FormCondition]],
    value_of: Any,
) -> bool:
    """Groups are ORed; conditions within a group are ANDed."""
    return any(
        all(condition_satisfied(c, value_of(c.depends_on_question_id)) for c in rows)
        for rows in groups.values()
    )


def compute_applicable_map(
    questions: Sequence[FormQuestion],
    answers_by_qid: Mapping[uuid.UUID, Any],
) -> dict[uuid.UUID, bool]:
    """
    Compute question visibility for one form version.

    Iterates to a fixed point so conditional chains (C depends on B which
    depends on A) resolve deterministically. A hidden dependency counts as
    unanswered for its dependent conditions.
    """
    qids = {q.question_id for q in questions}
    conditions_by_target: dict[uuid.UUID, list[FormCondition]] = {}
    for question in questions:
        for condition in question.conditions:
            # Conditions referencing questions outside this form version
            # cannot be evaluated and are ignored.
            if condition.depends_on_question_id in qids:
                conditions_by_target.setdefault(question.question_id, []).append(condition)

    applicable: dict[uuid.UUID, bool] = {q.question_id: True for q in questions}

    def value_of(dep_qid: uuid.UUID) -> Any:
        return answers_by_qid.get(dep_qid) if applicable.get(dep_qid, True) else None

    for _ in range(len(questions) + 2):
        changed = False
        for question in questions:
            rows = conditions_by_target.get(question.question_id)
            if not rows:
                continue
            show_groups: dict[int, list[FormCondition]] = {}
            hide_groups: dict[int, list[FormCondition]] = {}
            for condition in rows:
                action = (condition.action or "SHOW").upper()
                if action == "SHOW":
                    show_groups.setdefault(condition.condition_group, []).append(condition)
                elif action == "HIDE":
                    hide_groups.setdefault(condition.condition_group, []).append(condition)
                # REQUIRE affects required-ness, not visibility.

            visible = True
            if show_groups:
                visible = _groups_satisfied(show_groups, value_of)
            if visible and hide_groups and _groups_satisfied(hide_groups, value_of):
                visible = False

            if applicable[question.question_id] != visible:
                applicable[question.question_id] = visible
                changed = True
        if not changed:
            break
    return applicable


def compute_required_qids(
    questions: Sequence[FormQuestion],
    answers_by_qid: Mapping[uuid.UUID, Any],
    applicable: Mapping[uuid.UUID, bool],
) -> set[uuid.UUID]:
    """Static required flags plus REQUIRE-action conditions that currently hold."""
    required = {q.question_id for q in questions if q.required}
    for question in questions:
        if question.question_id in required:
            continue
        for condition in question.conditions:
            if (condition.action or "").upper() != "REQUIRE":
                continue
            dep_qid = condition.depends_on_question_id
            if not applicable.get(dep_qid, True):
                continue
            if condition_satisfied(condition, answers_by_qid.get(dep_qid)):
                required.add(question.question_id)
                break
    return required


class ProgressStats(NamedTuple):
    applicable_map: dict[uuid.UUID, bool]
    applicable_count: int
    answered_count: int
    percentage: int
    missing_required: list[str]  # question codes, sorted


def compute_progress(
    questions: Sequence[FormQuestion],
    answers_by_qid: Mapping[uuid.UUID, Any],
) -> ProgressStats:
    """
    Completion over APPLICABLE questions only: hidden (conditionally or
    structurally inactive) questions never enter the denominator and a
    hidden required question never blocks completion.
    """
    applicable_map = compute_applicable_map(questions, answers_by_qid)
    applicable = [q for q in questions if applicable_map[q.question_id]]
    required = compute_required_qids(questions, answers_by_qid, applicable_map)

    answered = [q for q in applicable if is_answered(answers_by_qid.get(q.question_id))]
    missing = sorted(
        q.question_code
        for q in applicable
        if q.question_id in required and not is_answered(answers_by_qid.get(q.question_id))
    )

    percentage = round(len(answered) / len(applicable) * 100) if applicable else 0
    return ProgressStats(
        applicable_map=applicable_map,
        applicable_count=len(applicable),
        answered_count=len(answered),
        percentage=percentage,
        missing_required=missing,
    )


# ------------------------------------------------------------------
# Typed answer validation and column mapping
# ------------------------------------------------------------------


def _active_option_codes(question: FormQuestion) -> set[str]:
    return {o.option_code for o in question.options if o.status == "ACTIVE"}


def _apply_validation_rules(question: FormQuestion, typed_value: Any) -> None:
    """
    Apply the question's own validation_rule JSONB metadata. The definition
    is the single source of validation truth — nothing question-specific is
    hardcoded here. Unknown/unparseable rule keys fail open.
    """
    rules = question.validation_rule or {}
    if not isinstance(rules, dict) or typed_value is None:
        return

    numeric = _to_float(typed_value)
    if numeric is not None and not isinstance(typed_value, bool):
        minimum, maximum = rules.get("min"), rules.get("max")
        if isinstance(minimum, (int, float)) and numeric < minimum:
            raise AnswerValidationError(
                f"Question '{question.question_code}' expects a value >= {minimum}"
            )
        if isinstance(maximum, (int, float)) and numeric > maximum:
            raise AnswerValidationError(
                f"Question '{question.question_code}' expects a value <= {maximum}"
            )

    if isinstance(typed_value, str):
        min_len, max_len = rules.get("min_length"), rules.get("max_length")
        if isinstance(min_len, int) and len(typed_value) < min_len:
            raise AnswerValidationError(
                f"Question '{question.question_code}' expects at least {min_len} characters"
            )
        if isinstance(max_len, int) and len(typed_value) > max_len:
            raise AnswerValidationError(
                f"Question '{question.question_code}' allows at most {max_len} characters"
            )
        pattern = rules.get("pattern")
        if isinstance(pattern, str):
            try:
                if re.fullmatch(pattern, typed_value) is None:
                    raise AnswerValidationError(
                        f"Question '{question.question_code}' has an invalid value format"
                    )
            except re.error:
                # Broken pattern in the definition must not block users.
                pass
        if rules.get("email"):
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", typed_value):
                raise AnswerValidationError(
                    f"Question '{question.question_code}' expects a valid email address"
                )


def validate_and_map_answer(
    question: FormQuestion,
    value: Any,
    source: str = "USER_INPUT",
) -> tuple[str | None, Any]:
    """
    Validate one incoming answer against the question definition and map it
    to the matching typed FormAnswer column.

    Returns (column_name, typed_value); (None, None) means "clear the
    answer". Raises AnswerValidationError on any mismatch. The choice/dropdown
    and multi_choice paths rely on the question's configured ACTIVE options.
    """
    if source not in ANSWER_SOURCES:
        raise AnswerValidationError(
            f"Invalid answer source '{source}'; expected one of {list(ANSWER_SOURCES)}"
        )

    if value is None:
        return (None, None)

    question_type = (question.question_type or "").lower()
    data_type = (question.data_type or "STRING").upper()
    code = question.question_code

    if question_type == "multi_choice":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise AnswerValidationError(
                f"Question '{code}' expects a list of option codes"
            )
        valid_codes = _active_option_codes(question)
        invalid = [v for v in value if v not in valid_codes]
        if invalid:
            raise AnswerValidationError(
                f"Question '{code}' has invalid option(s): {invalid}; "
                f"expected from {sorted(valid_codes)}"
            )
        _apply_validation_rules(question, value)
        return ("answer_json", value)

    if question_type in ("single_choice", "dropdown"):
        if not isinstance(value, str) or value not in _active_option_codes(question):
            raise AnswerValidationError(
                f"Question '{code}' expects one of {sorted(_active_option_codes(question))}"
            )
        _apply_validation_rules(question, value)
        return ("answer_text", value)

    if data_type == "BOOLEAN":
        if not isinstance(value, bool):
            raise AnswerValidationError(f"Question '{code}' expects a boolean value")
        return ("answer_boolean", value)

    if data_type == "INTEGER":
        if isinstance(value, bool):
            raise AnswerValidationError(f"Question '{code}' expects an integer value")
        if isinstance(value, int):
            typed = value
        elif isinstance(value, float) and value.is_integer():
            typed = int(value)
        else:
            raise AnswerValidationError(f"Question '{code}' expects an integer value")
        _apply_validation_rules(question, typed)
        return ("answer_number", typed)

    if data_type == "DECIMAL":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise AnswerValidationError(f"Question '{code}' expects a numeric value")
        typed = float(value)
        _apply_validation_rules(question, typed)
        return ("answer_decimal", typed)

    if data_type == "DATE":
        if not isinstance(value, str):
            raise AnswerValidationError(f"Question '{code}' expects an ISO date string")
        try:
            typed = date.fromisoformat(value.strip())
        except ValueError:
            raise AnswerValidationError(
                f"Question '{code}' expects a valid date in YYYY-MM-DD format"
            )
        _apply_validation_rules(question, typed)
        return ("answer_date", typed)

    if data_type == "JSON":
        if not isinstance(value, (dict, list)):
            raise AnswerValidationError(
                f"Question '{code}' expects a JSON object or list"
            )
        return ("answer_json", value)

    # STRING default — covers text, file references, and string locations.
    if not isinstance(value, str):
        raise AnswerValidationError(f"Question '{code}' expects a string value")
    _apply_validation_rules(question, value)
    return ("answer_text", value)


def set_typed_value(answer: FormAnswer, column: str, value: Any) -> None:
    """Write one typed column and clear the others (an answer occupies
    exactly one typed column, so re-typing never leaves stale values)."""
    for col in TYPED_ANSWER_COLUMNS:
        setattr(answer, col, value if col == column else None)
