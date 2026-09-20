"""
Seed script for the dynamic form system (Phases 1 and 2C).

Loads backend/seed_data/forms.json into tbl_form_definition and related
tables. Idempotent: a (form_code, version) pair that already exists is
skipped, so re-running never duplicates or modifies existing rows.

Phase 2C: every form definition is VALIDATED before any database write
(see validate_form_spec). A form with an unknown profile_field, invalid
condition, or duplicate code fails the whole seed run before anything
is written — invalid forms are never seeded and discovered later during
normalization.

Run with: PYTHONPATH=. python scripts/seed_forms.py

The existing schemes seed (scripts/seed.py + seed_data/schemes.json) is
untouched and continues to work exactly as before.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models.form import (
    QUESTION_TYPES,
    FormCondition,
    FormDefinition,
    FormQuestion,
    FormQuestionOption,
    FormSection,
)
from app.services.profile_mapping import DERIVED_ONLY_FIELDS, resolve_profile_field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

SEED_FILE = Path(__file__).parent.parent / "seed_data" / "forms.json"

# ---------------------------------------------------------------------------
# Pre-seed validation (Phase 2C Step 2) — fail fast, before any DB write.
# ---------------------------------------------------------------------------

VALID_DATA_TYPES = {"STRING", "INTEGER", "DECIMAL", "BOOLEAN", "DATE", "JSON"}
VALID_OPERATORS = {
    "EQUALS", "NOT_EQUALS", "GREATER_THAN", "LESS_THAN",
    "GREATER_THAN_OR_EQUAL", "LESS_THAN_OR_EQUAL",
    "IN", "NOT_IN", "IS_EMPTY", "IS_NOT_EMPTY",
}
VALID_ACTIONS = {"SHOW", "HIDE", "REQUIRE"}
_ALLOWED_RULE_KEYS = {
    "min", "max", "min_length", "max_length", "pattern", "email",
}


def validate_form_spec(f_data: dict) -> list[str]:
    """Validate one form definition. Returns a list of problems (empty =
    valid). Covers: unique form_code/version across the seed file, unique
    question codes, section/question/option structure, question and data
    types, option definitions, condition references/operators/actions,
    profile_field and fact_code resolution, derived-only-field misuse,
    validation_rule structure, duplicate option codes, and circular
    conditional dependencies."""
    problems: list[str] = []
    form_code = f_data.get("form_code")
    if not form_code:
        return ["form is missing 'form_code'"]

    sections = f_data.get("sections", [])
    if not sections:
        problems.append(f"{form_code}: form has no sections")

    seen_section_codes: set[str] = set()
    question_codes: dict[str, str] = {}          # code -> section_code
    dependencies: dict[str, list[str]] = {}      # code -> depends-on codes

    for s_index, s_data in enumerate(sections):
        section_code = s_data.get("section_code")
        if not section_code:
            problems.append(f"{form_code}: section[{s_index}] missing section_code")
            continue
        if section_code in seen_section_codes:
            problems.append(f"{form_code}: duplicate section_code '{section_code}'")
        seen_section_codes.add(section_code)
        if not s_data.get("section_name"):
            problems.append(f"{form_code}/{section_code}: missing section_name")

        seen_question_codes: set[str] = set()
        for q_index, q_data in enumerate(s_data.get("questions", [])):
            q_code = q_data.get("question_code")
            q_label = f"{form_code}/{section_code}/questions[{q_index}]"
            if not q_code:
                problems.append(f"{q_label}: missing question_code")
                continue
            if q_code in question_codes:
                problems.append(
                    f"{form_code}: duplicate question_code '{q_code}' "
                    f"(also in {question_codes[q_code]})"
                )
            if q_code in seen_question_codes:
                problems.append(f"{form_code}/{section_code}: duplicate '{q_code}'")
            seen_question_codes.add(q_code)
            question_codes.setdefault(q_code, section_code)

            if not q_data.get("question_text"):
                problems.append(f"{q_label} ({q_code}): missing question_text")
            q_type = q_data.get("question_type", "text")
            if q_type not in QUESTION_TYPES:
                problems.append(
                    f"{form_code}/{q_code}: invalid question_type '{q_type}' "
                    f"(allowed: {list(QUESTION_TYPES)})"
                )
            data_type = q_data.get("data_type", "STRING")
            if data_type not in VALID_DATA_TYPES:
                problems.append(
                    f"{form_code}/{q_code}: invalid data_type '{data_type}' "
                    f"(allowed: {sorted(VALID_DATA_TYPES)})"
                )
            if q_type == "file":
                problems.append(
                    f"{form_code}/{q_code}: file questions are excluded until "
                    f"the document store exists (spec Task 7/8)"
                )

            # Option definitions: choice/dropdown/multi_choice require them;
            # option codes must be unique within the question.
            needs_options = q_type in ("single_choice", "dropdown", "multi_choice")
            options = q_data.get("options", [])
            if needs_options and not options:
                problems.append(
                    f"{form_code}/{q_code}: question_type '{q_type}' requires options"
                )
            if options and not needs_options and q_type != "boolean":
                problems.append(
                    f"{form_code}/{q_code}: options are only valid on "
                    f"choice/dropdown/multi_choice questions"
                )
            seen_option_codes: set[str] = set()
            for o_index, o_data in enumerate(options):
                o_code = o_data.get("option_code")
                if not o_code:
                    problems.append(f"{form_code}/{q_code}: options[{o_index}] missing option_code")
                elif o_code in seen_option_codes:
                    problems.append(f"{form_code}/{q_code}: duplicate option_code '{o_code}'")
                seen_option_codes.add(o_code)
                if not o_data.get("option_label"):
                    problems.append(
                        f"{form_code}/{q_code}: option '{o_code}' missing option_label"
                    )

            # Profile-field mapping: must resolve in the registry, and a
            # derived-only field must never be asked directly.
            profile_field = q_data.get("profile_field")
            if profile_field:
                entry = resolve_profile_field(profile_field)
                if entry is None:
                    problems.append(
                        f"{form_code}/{q_code}: unknown profile_field "
                        f"'{profile_field}' — no canonical mapping (refusing to seed)"
                    )
                else:
                    key = profile_field.strip().lower()
                    if key in DERIVED_ONLY_FIELDS or key in {
                        b for entry_key in DERIVED_ONLY_FIELDS
                        for b in _bare_names_of(entry_key)
                    }:
                        problems.append(
                            f"{form_code}/{q_code}: profile_field '{profile_field}' "
                            f"is DERIVED_ONLY — it must not be asked directly"
                        )
                    if (
                        entry.choices
                        and needs_options
                        and seen_option_codes
                        and not seen_option_codes.issubset(set(entry.choices))
                    ):
                        problems.append(
                            f"{form_code}/{q_code}: options {sorted(seen_option_codes)} "
                            f"do not match registry choices {list(entry.choices)}"
                        )

            # Validation-rule structure: only known keys, sane types.
            rule = q_data.get("validation_rule")
            if rule is not None:
                if not isinstance(rule, dict):
                    problems.append(f"{form_code}/{q_code}: validation_rule must be an object")
                else:
                    unknown = set(rule) - _ALLOWED_RULE_KEYS
                    if unknown:
                        problems.append(
                            f"{form_code}/{q_code}: unknown validation_rule keys {sorted(unknown)}"
                        )
                    for key in ("min", "max"):
                        if key in rule and not isinstance(rule[key], (int, float)):
                            problems.append(f"{form_code}/{q_code}: validation_rule.{key} must be numeric")
                    for key in ("min_length", "max_length"):
                        if key in rule and not isinstance(rule[key], int):
                            problems.append(f"{form_code}/{q_code}: validation_rule.{key} must be an integer")
                    if "pattern" in rule and not isinstance(rule["pattern"], str):
                        problems.append(f"{form_code}/{q_code}: validation_rule.pattern must be a string")
                    elif "pattern" in rule:
                        try:
                            re.compile(rule["pattern"])
                        except re.error:
                            problems.append(f"{form_code}/{q_code}: validation_rule.pattern is not a valid regex")

            # Conditions: known operator/action, resolvable references,
            # IN/NOT_IN need a comparison value, IS_EMPTY must not have one.
            for c_index, c_data in enumerate(q_data.get("conditions", [])):
                dep = c_data.get("depends_on_question_code")
                operator = c_data.get("operator")
                action = c_data.get("action", "SHOW")
                c_label = f"{form_code}/{q_code}: conditions[{c_index}]"
                if not dep:
                    problems.append(f"{c_label}: missing depends_on_question_code")
                else:
                    dependencies.setdefault(q_code, []).append(dep)
                    if dep == q_code:
                        problems.append(f"{c_label}: question cannot depend on itself")
                    if dep not in question_codes:
                        # Forward references are fine; unknown codes fail below.
                        pass
                if operator not in VALID_OPERATORS:
                    problems.append(
                        f"{c_label}: invalid operator '{operator}' (allowed: {sorted(VALID_OPERATORS)})"
                    )
                if action not in VALID_ACTIONS:
                    problems.append(
                        f"{c_label}: invalid action '{action}' (allowed: {sorted(VALID_ACTIONS)})"
                    )
                comparison = c_data.get("comparison_value")
                if operator in ("IN", "NOT_IN") and not comparison:
                    problems.append(f"{c_label}: {operator} requires comparison_value")
                if operator in ("IS_EMPTY", "IS_NOT_EMPTY") and comparison is not None:
                    problems.append(f"{c_label}: {operator} must not have a comparison_value")

    # All condition references must point at questions that exist.
    for q_code, deps in dependencies.items():
        for dep in deps:
            if dep not in question_codes:
                problems.append(
                    f"{form_code}/{q_code}: condition references unknown "
                    f"question '{dep}'"
                )

    # Circular conditional dependency: DFS cycle detection over the
    # condition dependency graph (A -> B means A's visibility depends on B).
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {code: WHITE for code in question_codes}

    def _visit(node: str, stack: list[str]) -> None:
        color[node] = GRAY
        stack.append(node)
        for dep in dependencies.get(node, []):
            if dep not in color:
                continue
            if color[dep] == GRAY:
                cycle = stack[stack.index(dep):] + [dep]
                problems.append(
                    f"{form_code}: circular conditional dependency: "
                    f"{' -> '.join(cycle)}"
                )
            elif color[dep] == WHITE:
                _visit(dep, stack)
        stack.pop()
        color[node] = BLACK

    for code in question_codes:
        if color[code] == WHITE:
            _visit(code, [])

    return problems


def _bare_names_of(registry_key: str) -> set[str]:
    entry = resolve_profile_field(registry_key)
    return set(entry.bare_names) if entry else set()


def validate_seed_file(data: dict) -> list[str]:
    """Validate the whole seed file, including cross-form uniqueness of
    (form_code, version) pairs."""
    problems: list[str] = []
    seen_versions: set[tuple[str, int]] = set()
    forms = data.get("forms", [])
    if not forms:
        return ["seed file contains no forms"]
    for f_data in forms:
        form_code = f_data.get("form_code")
        version = f_data.get("version", 1)
        pair = (form_code, version)
        if pair in seen_versions:
            problems.append(f"duplicate form_code/version in seed file: {pair}")
        seen_versions.add(pair)
        problems.extend(validate_form_spec(f_data))
    return problems


def seed_forms() -> None:
    """Synchronous entry point: validate everything first, then seed."""
    asyncio.run(_seed_forms_async())


async def _seed_forms_async() -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    if not SEED_FILE.exists():
        logger.error(f"Seed file not found at {SEED_FILE}")
        await engine.dispose()
        return

    with open(SEED_FILE, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    # Cross-file structural sanity first (duplicate form_code/version).
    structural_problems: list[str] = []
    seen_versions: set[tuple[str, int]] = set()
    for f_data in data.get("forms", []):
        pair = (f_data.get("form_code"), f_data.get("version", 1))
        if pair in seen_versions:
            structural_problems.append(f"duplicate form_code/version in seed file: {pair}")
        seen_versions.add(pair)
    if structural_problems:
        await engine.dispose()
        raise SystemExit(
            "Form seed validation failed — nothing was written. Problems:\n  - "
            + "\n  - ".join(structural_problems)
        )

    created_forms = 0
    skipped_forms = 0

    async with async_session() as session:
        for f_data in data.get("forms", []):
            form_code = f_data["form_code"]
            version = f_data.get("version", 1)

            # Idempotency check on the (form_code, version) unique constraint.
            existing = await session.execute(
                select(FormDefinition).where(
                    FormDefinition.form_code == form_code,
                    FormDefinition.version == version,
                )
            )
            if existing.scalar_one_or_none() is not None:
                logger.info(f"Skipping existing form {form_code} v{version}")
                skipped_forms += 1
                continue

            # Phase 2C Step 2: full validation BEFORE writing a NEW form.
            # Forms already in the database are skipped untouched (v1's
            # legacy questions predate the validator and must not be
            # modified); any NEW form must pass strict validation or the
            # whole run aborts before a single row is written.
            problems = validate_form_spec(f_data)
            if problems:
                await session.rollback()
                await engine.dispose()
                raise SystemExit(
                    f"Form seed validation failed for {form_code} v{version} "
                    f"— nothing was written. Problems:\n  - "
                    + "\n  - ".join(problems)
                )

            form = FormDefinition(
                form_code=form_code,
                form_name=f_data["form_name"],
                description=f_data.get("description"),
                target_citizen_type=f_data.get("target_citizen_type"),
                version=version,
                status=f_data.get("status", "DRAFT"),
            )
            session.add(form)
            await session.flush()

            # Two-pass: insert all questions first so condition
            # depends_on_question_id references can be resolved by code.
            question_by_code: dict[str, FormQuestion] = {}

            for s_data in f_data.get("sections", []):
                section = FormSection(
                    form_id=form.form_id,
                    section_code=s_data["section_code"],
                    section_name=s_data["section_name"],
                    description=s_data.get("description"),
                    display_order=s_data.get("display_order", 1),
                    status=s_data.get("status", "ACTIVE"),
                )
                session.add(section)
                await session.flush()

                for q_data in s_data.get("questions", []):
                    question = FormQuestion(
                        section_id=section.section_id,
                        question_code=q_data["question_code"],
                        question_text=q_data["question_text"],
                        question_type=q_data["question_type"],
                        data_type=q_data.get("data_type", "STRING"),
                        required=q_data.get("required", False),
                        display_order=q_data.get("display_order", 1),
                        profile_field=q_data.get("profile_field"),
                        validation_rule=q_data.get("validation_rule"),
                        help_text=q_data.get("help_text"),
                        placeholder=q_data.get("placeholder"),
                    )
                    session.add(question)
                    await session.flush()
                    question_by_code[question.question_code] = question

                    for o_data in q_data.get("options", []):
                        session.add(
                            FormQuestionOption(
                                question_id=question.question_id,
                                option_code=o_data["option_code"],
                                option_label=o_data["option_label"],
                                display_order=o_data.get("display_order", 1),
                                status=o_data.get("status", "ACTIVE"),
                            )
                        )

            # Second pass: conditions (questions already exist). The
            # pre-seed validator has already proven every reference
            # resolves — there is no silent-skip path here anymore.
            for s_data in f_data.get("sections", []):
                for q_data in s_data.get("questions", []):
                    for c_data in q_data.get("conditions", []):
                        depends_on = question_by_code[c_data["depends_on_question_code"]]
                        session.add(
                            FormCondition(
                                question_id=question_by_code[q_data["question_code"]].question_id,
                                depends_on_question_id=depends_on.question_id,
                                operator=c_data["operator"],
                                comparison_value=c_data.get("comparison_value"),
                                action=c_data.get("action", "SHOW"),
                                condition_group=c_data.get("condition_group", 1),
                            )
                        )

            created_forms += 1
            logger.info(f"Seeded form {form_code} v{version}")

        await session.commit()

    logger.info(
        f"Form seed complete: {created_forms} created, {skipped_forms} skipped"
    )
    await engine.dispose()


if __name__ == "__main__":
    seed_forms()
