"""
Normalization service (Phase 2B): completed form submissions → canonical
domain profiles → profile facts → fact provenance.

Layer separation (spec principle):
    FORM ANSWER ≠ PROFILE FACT ≠ ELIGIBILITY RULE
This service only fills the first two layers. It never touches the
eligibility engine, recommendations, or scheme data.

Flow:
    1. Load the submission (with answers + questions eager-loaded).
    2. Verify ownership and COMPLETED status — drafts are never normalized.
    3. Resolve each answer's question profile_field through the canonical
       registry (app/services/profile_mapping.py) — no per-question code.
    4. Coerce values deterministically; non-normalizable values are
       reported as warnings, never guessed.
    5. Write canonical domain-profile columns (get-or-create singletons).
    6. Upsert open profile facts (verified facts are preserved; new
       evidence is attached as provenance instead of overwriting).
    7. Expand structured family-member JSON into tbl_family_member rows
       (natural-key upsert; invalid member entries are reported, skipped).
    8. Derive deterministic facts (AGE from DATE_OF_BIRTH).
    9. Record provenance per fact (deduplicated per (fact, answer)).
   10. Return a Pydantic summary; unmapped answers are listed, never
       silently discarded.

Idempotency: re-running a normalization creates no duplicate profile rows
(unique citizen_id), no duplicate facts (partial unique open-fact index),
and no duplicate provenance ((fact_id, form_answer_id) dedup); counters
drop to zero on the second run.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.form import FormQuestion
from app.models.submission import FormAnswer, FormSubmission
from app.repositories.profile_repository import ProfileRepository, SINGLETON_DOMAINS
from app.repositories.submission_repository import SubmissionRepository
from app.schemas.normalization import NormalizationSummary, UnmappedAnswerItem
from app.services.form_logic import (
    SubmissionNotFoundError,
    SubmissionOwnershipError,
    answer_value,
    is_answered,
)
from app.services.profile_mapping import (
    DERIVATION_RULES,
    canonical_fact_value,
    coerce_profile_value,
    normalize_number,
    resolve_profile_field,
)

_COMPLETED = "COMPLETED"

# Sources authoritative enough to overwrite an existing VERIFIED fact.
_VERIFIED_SOURCES = ("ADMIN_VERIFIED", "GOVERNMENT_API", "EXTERNAL_VERIFICATION")

# Sources that themselves constitute verification of the new value.
_VERIFICATION_SOURCES = _VERIFIED_SOURCES

# Relationships representable in tbl_family_member.relationship.
_KNOWN_RELATIONSHIPS = (
    "SELF", "SPOUSE", "SON", "DAUGHTER", "FATHER", "MOTHER", "OTHER",
)


class SubmissionNotCompletedError(Exception):
    status_code = 409
    message = "Submission is not COMPLETED; only completed submissions can be normalized"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)
        if message:
            self.message = message


class NormalizationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.submissions = SubmissionRepository(db)
        self.profiles = ProfileRepository(db)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def normalize_submission(
        self, submission_id: uuid.UUID, citizen_id: uuid.UUID
    ) -> NormalizationSummary:
        submission = await self.submissions.get_by_id(submission_id)
        if submission is None:
            raise SubmissionNotFoundError()
        if submission.citizen_id != citizen_id:
            raise SubmissionOwnershipError()
        if submission.status != _COMPLETED:
            raise SubmissionNotCompletedError()

        form = submission.form
        summary = NormalizationSummary(
            submission_id=submission.submission_id,
            citizen_id=submission.citizen_id,
            status="NORMALIZED",
            form_code=form.form_code if form else None,
            form_version=submission.form_version,
        )

        # Structured family block is applied after scalar answers.
        family_payload: list[dict[str, Any]] = []

        for answer in submission.answers:
            question: FormQuestion | None = answer.question
            if question is None:  # pragma: no cover — FK guarantees
                continue
            raw = answer_value(answer)
            if not is_answered(raw):
                continue

            entry = resolve_profile_field(question.profile_field)
            if entry is None:
                summary.unmapped_answers.append(
                    UnmappedAnswerItem(
                        question_code=question.question_code,
                        profile_field=question.profile_field,
                        reason="no canonical profile mapping for this profile_field",
                    )
                )
                continue

            value, warning = coerce_profile_value(entry, raw)
            if warning is not None:
                summary.warnings.append(f"{question.question_code}: {warning}")
                continue
            if value is None:
                continue

            if entry.domain == "family_member":
                if isinstance(value, list):
                    family_payload.extend(value)
                else:
                    summary.warnings.append(
                        f"{question.question_code}: family members answer must be a JSON list"
                    )
                continue

            await self._apply_scalar(
                summary, submission, answer, question, entry, value
            )

        if family_payload:
            await self._apply_family_members(summary, submission, family_payload)

        # Identity facts from registration (FULL_NAME / DATE_OF_BIRTH) when
        # the fact layer lacks them — v3 forms no longer collect identity,
        # and the AGE derivation chain needs DATE_OF_BIRTH (see method doc).
        await self._seed_identity_facts(summary, submission)

        await self._derive_facts(summary, submission)

        summary.profiles_updated = sorted(set(summary.profiles_updated))
        return summary

    # ------------------------------------------------------------------
    # Scalar profile + fact application
    # ------------------------------------------------------------------

    async def _apply_scalar(
        self,
        summary: NormalizationSummary,
        submission: FormSubmission,
        answer: FormAnswer,
        question: FormQuestion,
        entry,
        value: Any,
    ) -> None:
        # 1) Canonical domain-profile column.
        if entry.column is not None and entry.domain != "citizen":
            if entry.domain in SINGLETON_DOMAINS:
                row = await self.profiles.get_or_create_singleton(
                    entry.domain, submission.citizen_id
                )
                setattr(row, entry.column, value)
                if entry.domain not in summary.profiles_updated:
                    summary.profiles_updated.append(entry.domain)
            else:
                # Multi-row domain (e.g. assets): a scalar answer cannot
                # identify which row to update. Facts still normalize below;
                # structured multi-row writing is a future DB requirement.
                summary.warnings.append(
                    f"Scalar column {entry.domain}.{entry.column} skipped: "
                    f"multi-row domain has no singleton row"
                )

        # 2) Interoperability fact (only registry entries with a fact_code).
        if entry.fact_code is None:
            return
        serialized = canonical_fact_value(entry.data_type, value)
        await self._upsert_fact(
            summary,
            submission,
            answer,
            question,
            fact_code=entry.fact_code,
            data_type=entry.data_type,
            serialized=serialized,
            source=answer.source,
        )

    async def _upsert_fact(
        self,
        summary: NormalizationSummary,
        submission: FormSubmission,
        answer: FormAnswer,
        question: FormQuestion,
        *,
        fact_code: str,
        data_type: str,
        serialized: str | None,
        source: str,
        derived: bool = False,
        derived_reference: str | None = None,
        derived_description: str | None = None,
    ) -> None:
        existing = await self.profiles.get_open_fact(
            submission.citizen_id, fact_code
        )

        if existing is None:
            verified = source in _VERIFICATION_SOURCES
            fact = await self.profiles.create_fact(
                citizen_id=submission.citizen_id,
                fact_code=fact_code,
                fact_value=serialized,
                data_type=data_type,
                source=source,
                verified=verified,
            )
            if derived:
                summary.facts_derived += 1
            else:
                summary.facts_created += 1
            await self._ensure_provenance(
                summary,
                fact,
                submission,
                answer,
                question,
                source,
                derived,
                derived_reference,
                derived_description,
            )
            return

        # Verified facts are never overwritten by weaker sources; the new
        # evidence is still recorded against the same fact (Part 10).
        if existing.verified and source not in _VERIFIED_SOURCES:
            await self._ensure_provenance(
                summary,
                existing,
                submission,
                answer,
                question,
                source,
                derived,
                derived_reference,
                derived_description,
            )
            summary.warnings.append(
                f"{fact_code}: existing verified fact preserved; "
                f"new '{source}' evidence recorded without overwrite"
            )
            return

        if existing.fact_value != serialized:
            existing.fact_value = serialized
            existing.data_type = data_type
            existing.source = source
            if source in _VERIFICATION_SOURCES:
                existing.verified = True
            if derived:
                summary.facts_derived += 1
            else:
                summary.facts_updated += 1
        await self._ensure_provenance(
            summary,
            existing,
            submission,
            answer,
            question,
            source,
            derived,
            derived_reference,
            derived_description,
        )

    async def _ensure_provenance(
        self,
        summary: NormalizationSummary,
        fact,
        submission: FormSubmission,
        answer: FormAnswer | None,
        question: FormQuestion | None,
        source: str,
        derived: bool,
        derived_reference: str | None = None,
        derived_description: str | None = None,
    ) -> None:
        """Attach provenance once per (fact, answer) — idempotent re-runs."""
        if derived:
            reference = derived_reference or "DERIVED:DATE_OF_BIRTH"
            existing = await self.profiles.get_provenance_by_reference(
                fact.fact_id, reference
            )
            if existing is not None:
                return
            await self.profiles.add_provenance(
                fact_id=fact.fact_id,
                source_type="SYSTEM_DERIVED",
                source_reference=reference,
                source_text=(
                    derived_description
                    or f"{fact.fact_code} derived from source facts (deterministic)"
                ),
                form_answer_id=None,
                verification_status="PENDING",
            )
            summary.provenance_created += 1
            return

        if answer is None:
            # No form answer: the fact came from a non-answer source with an
            # explicit reference (e.g. CITIZEN_MASTER identity facts). Dedup
            # on the reference so re-runs never stack duplicate rows.
            reference = derived_reference or f"CITIZEN_MASTER:{fact.fact_code}"
            existing = await self.profiles.get_provenance_by_reference(
                fact.fact_id, reference
            )
            if existing is not None:
                return
            await self.profiles.add_provenance(
                fact_id=fact.fact_id,
                source_type=source,
                source_reference=reference,
                source_text=derived_description or f"{fact.fact_code} from citizen registration",
                form_answer_id=None,
                verification_status=(
                    "VERIFIED" if source in _VERIFICATION_SOURCES else "PENDING"
                ),
            )
            summary.provenance_created += 1
            return
        existing = await self.profiles.get_provenance_by_answer(
            fact.fact_id, answer.answer_id
        )
        if existing is not None:
            return
        question_text = question.question_text if question else None
        await self.profiles.add_provenance(
            fact_id=fact.fact_id,
            source_type=source,
            source_reference=f"FORM_SUBMISSION:{submission.submission_id}",
            source_text=(
                f"{question.question_code}: {question_text}"
                if question
                else None
            ),
            form_answer_id=answer.answer_id,
            verification_status=(
                "VERIFIED" if source in _VERIFICATION_SOURCES else "PENDING"
            ),
        )
        summary.provenance_created += 1

    # ------------------------------------------------------------------
    # Family members (Part 5)
    # ------------------------------------------------------------------

    async def _apply_family_members(
        self,
        summary: NormalizationSummary,
        submission: FormSubmission,
        members: list[dict[str, Any]],
    ) -> None:
        for index, item in enumerate(members):
            if not isinstance(item, dict):
                summary.warnings.append(
                    f"family_members[{index}]: expected an object, skipped"
                )
                continue
            relationship = str(item.get("relationship", "")).strip().upper()
            if not relationship:
                summary.warnings.append(
                    f"family_members[{index}]: missing relationship, skipped"
                )
                continue
            if relationship not in _KNOWN_RELATIONSHIPS:
                summary.warnings.append(
                    f"family_members[{index}]: unknown relationship "
                    f"'{relationship}', skipped (allowed: {list(_KNOWN_RELATIONSHIPS)})"
                )
                continue
            name = item.get("name")
            name = name.strip() if isinstance(name, str) else None
            dob_raw = item.get("date_of_birth")
            dob = None
            if isinstance(dob_raw, str) and dob_raw.strip():
                try:
                    dob = date.fromisoformat(dob_raw.strip())
                except ValueError:
                    summary.warnings.append(
                        f"family_members[{index}]: unparseable date_of_birth "
                        f"{dob_raw!r}, member stored without it"
                    )
            if name is None and dob is None:
                summary.warnings.append(
                    f"family_members[{index}]: needs at least a name or a "
                    f"date_of_birth to identify the member, skipped"
                )
                continue

            income = normalize_number(item.get("income"))
            dependent = item.get("dependent_flag")
            if not isinstance(dependent, bool):
                dependent = None
            fields: dict[str, Any] = {}
            if isinstance(item.get("gender"), str) and item["gender"].strip():
                fields["gender"] = item["gender"].strip().upper()
            if isinstance(item.get("education_status"), str) and item["education_status"].strip():
                fields["education_status"] = item["education_status"].strip().upper()
            if isinstance(item.get("occupation"), str) and item["occupation"].strip():
                fields["occupation"] = item["occupation"].strip()
            if income is not None:
                fields["income"] = income
            if dependent is not None:
                fields["dependent_flag"] = dependent
            if isinstance(item.get("disability_status"), str) and item["disability_status"].strip():
                fields["disability_status"] = item["disability_status"].strip().upper()

            _, created, changed = await self.profiles.upsert_family_member(
                citizen_id=submission.citizen_id,
                relationship=relationship,
                name=name,
                date_of_birth=dob,
                **fields,
            )
            if created:
                summary.family_members_created += 1
            elif changed:
                summary.family_members_updated += 1
        if summary.family_members_created or summary.family_members_updated:
            if "family_member" not in summary.profiles_updated:
                summary.profiles_updated.append("family_member")

    # ------------------------------------------------------------------
    # Derived facts (Part 7 / Phase 2C Part on derived-fact validation)
    # ------------------------------------------------------------------

    async def _derive_facts(
        self,
        summary: NormalizationSummary,
        submission: FormSubmission,
    ) -> None:
        """Apply the declarative DERIVATION_RULES from the registry.

        Each rule fires only when every SOURCE FACT exists on the citizen —
        derived facts are never invented from missing data. Chained rules
        (SENIOR_CITIZEN from the derived AGE) are handled by re-scanning
        until no new derivation is produced (bounded, deterministic).
        """
        for _pass in range(3):  # chains are at most 2 deep (DOB→AGE→SENIOR)
            progressed = False
            for rule in DERIVATION_RULES:
                if await self._apply_derivation_rule(summary, submission, rule):
                    progressed = True
            if not progressed:
                break

    async def _apply_derivation_rule(
        self,
        summary: NormalizationSummary,
        submission: FormSubmission,
        rule,
    ) -> bool:
        """Run one derivation rule; True if it produced/updated a fact."""
        facts: dict[str, str | None] = {}
        for code in rule.source_facts:
            fact = await self.profiles.get_open_fact(submission.citizen_id, code)
            if fact is None or not fact.fact_value:
                return False  # source missing — never invent the derived value
            facts[code] = fact.fact_value
        try:
            value = rule.compute(facts)
        except (ValueError, KeyError, TypeError):
            return False  # unparseable source — skip deterministically
        if value is None:
            return False
        await self._upsert_fact(
            summary,
            submission,
            answer=None,
            question=None,
            fact_code=rule.derived_fact,
            data_type=rule.data_type,
            serialized=canonical_fact_value(rule.data_type, value),
            source="SYSTEM_DERIVED",
            derived=True,
            derived_reference=f"DERIVED:{'+'.join(rule.source_facts)}",
            derived_description=(
                f"{rule.derived_fact} derived from {'+'.join(rule.source_facts)} "
                "(deterministic rule)"
            ),
        )
        # Mirror into the canonical domain column where one exists.
        if rule.column and rule.domain and rule.domain != "citizen":
            row = await self.profiles.get_or_create_singleton(
                rule.domain, submission.citizen_id
            )
            setattr(row, rule.column, bool(value))
            if rule.domain not in summary.profiles_updated:
                summary.profiles_updated.append(rule.domain)
        return True

    async def _seed_identity_facts(
        self,
        summary: NormalizationSummary,
        submission: FormSubmission,
    ) -> None:
        """Seed identity facts (FULL_NAME, DATE_OF_BIRTH) from the citizen
        registration record when the citizen has none yet.

        Since GENERAL_CITIZEN_PROFILE v3, the welfare form no longer asks
        identity questions — identity is established once at profile
        creation. The AGE derivation rule needs a DATE_OF_BIRTH fact to
        work from, so for v3-only citizens this method materializes the
        identity facts from the authoritative tbl_citizen_master row before
        derivations run. Already-normalized citizens (v2 answers) are
        untouched: their form-sourced facts keep their original provenance.
        """
        citizen = await self.profiles.get_identity_profile(submission.citizen_id)
        if citizen is None:  # pragma: no cover — FK guarantees existence
            return
        identity_values: list[tuple[str, str, str]] = [
            ("FULL_NAME", citizen.full_name, "STRING"),
            ("DATE_OF_BIRTH", citizen.date_of_birth.isoformat(), "DATE"),
        ]
        existing = await self.profiles.get_open_facts(
            submission.citizen_id, [code for code, _, _ in identity_values]
        )
        for code, value, data_type in identity_values:
            if code in existing:  # fact layer already has it — leave provenance alone
                continue
            await self._upsert_fact(
                summary,
                submission,
                answer=None,
                question=None,
                fact_code=code,
                data_type=data_type,
                serialized=canonical_fact_value(data_type, value),
                source="USER_INPUT",
                derived=False,
                derived_reference=f"CITIZEN_MASTER:{code}",
                derived_description=(
                    f"{code} recorded at citizen profile creation "
                    "(identity is established once, not re-asked in the welfare form)"
                ),
            )
