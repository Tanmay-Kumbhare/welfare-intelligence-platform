"""
Rule admin service — validated admin CRUD over the eligibility rule graph
(tbl_scheme_rule_group + tbl_scheme_eligibility_rule).

Complements SchemeAdminService (scheme master fields only): this layer owns
the group/rule write paths. Every mutation is validated server-side against
the FROZEN vocabularies the deterministic eligibility engine actually reads
(see app.services.eligibility_engine). No second rule system, no new
operators, no invented parameters.

MANDATORY-CONDITION SEMANTICS (existing design, preserved unchanged):
Every rule in the graph IS a mandatory eligibility gate — there is no
per-rule mandatory flag, and none is added. Group/scheme combining
operators decide HOW hard gates combine (AND / OR), never whether a rule
binds. There is no ranking/weighting layer in the eligibility path, so
nothing can override a failed rule. rule_priority is diagnostic ordering
only, NOT a weight.

group_combining_operator is administered here (scheme-scope setter) and
NOT through the generic scheme PATCH: changing it materially changes
eligibility outcomes (AND of groups ↔ OR of groups), so the change is
explicit, validated against the existing AND|OR vocabulary, and covered
by dedicated semantics tests.

DELETION SAFETY: rules carry tbl_scheme_rule_provenance citations; provenance
must survive rule administration, so a rule (or a group containing any rule)
with provenance is never hard-deleted (409). Assessment history is safe:
tbl_eligibility_assessment stores immutable evaluation_details snapshots and
references the scheme, not individual rules, so past rows keep their meaning
when a rule is later removed.

Transactions: flush-only — commit/rollback belong to the get_db lifecycle,
matching SchemeAdminService.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.scheme import (
    SchemeEligibilityRule,
    SchemeMaster,
    SchemeRuleGroup,
)
from app.models.scheme_source import SchemeRuleProvenance

# ------------------------------------------------------------------
# Frozen vocabularies — exactly what the eligibility engine consumes.
# parameter_name: every branch of EligibilityEngine._resolve_parameter.
# operator:       every comparison EligibilityEngine._apply_operator handles.
# ------------------------------------------------------------------

ELIGIBILITY_RULE_PARAMETERS = (
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
    "currently_studying",
    "is_studying",
    "is_enrolled",
    "is_currently_enrolled",
    "disability_status",
    "area_type",
    "state",
    "tenth_percentage",
    "twelfth_percentage",
    "twelfth_percentile",
    "graduation_percentage",
    "graduation_cgpa",
    "current_education_level",
    "current_degree",
    "current_branch",
    "current_year",
    "current_semester",
    "highest_education_level",
    "livestock_cattle_count",
    "livestock_poultry_count",
)

# Comparison of citizen-side values. IN compares a comma-separated list
# (engine: str(actual) in [item, ...]).
ELIGIBILITY_RULE_OPERATORS = ("<", "<=", ">", ">=", "==", "!=", "IN")

# How rules inside one group combine (engine: all() / any()).
GROUP_OPERATORS = ("AND", "OR")

# Diagnostic failure stage (tbl_scheme_eligibility_rule.failure_stage_code).
FAILURE_STAGE_CODES = (
    "S0_ELIGIBILITY",
    "S1_DOCUMENT_DISCREPANCY",
    "S2_DOMICILE_MISMATCH",
)

# Parameters the citizen side resolves to numbers or booleans. Their
# required_value must be parseable accordingly for comparisons to be
# deterministic; string-valued parameters stay free-form (the engine
# compares the citizen's stored value directly — values are not invented
# here).
NumericRuleParameters = (
    "age",
    "annual_income",
    "land_holding_size",
    "tenth_percentage",
    "twelfth_percentage",
    "twelfth_percentile",
    "graduation_percentage",
    "graduation_cgpa",
    "livestock_cattle_count",
    "livestock_poultry_count",
)
BooleanRuleParameters = (
    "is_bpl_card_holder",
    "is_income_tax_payer",
    "currently_studying",
    "is_studying",
    "is_enrolled",
    "is_currently_enrolled",
)

_BOOLEAN_TRUE = ("true", "1", "yes")
_BOOLEAN_FALSE = ("false", "0", "no")


class RuleAdminError(Exception):
    """Raised by the rule admin service; carries an HTTP status + detail."""

    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RuleAdminService:
    """Validated admin CRUD over rule groups + eligibility rules (flush-only)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _enum(field: str, value: str, allowed: tuple[str, ...]) -> str:
        if value not in allowed:
            raise RuleAdminError(f"{field} must be one of: {', '.join(allowed)}", 400)
        return value

    @staticmethod
    def _require_text(field: str, value: str | None, max_len: int) -> str:
        if value is None:
            raise RuleAdminError(f"{field} is required", 400)
        value = value.strip()
        if not value:
            raise RuleAdminError(f"{field} must not be empty", 400)
        if len(value) > max_len:
            raise RuleAdminError(f"{field} must be at most {max_len} characters", 400)
        return value

    def _validate_required_value(
        self, rule: dict, *, existing_rule: SchemeEligibilityRule | None = None
    ) -> str:
        """Validate required_value against the EFFECTIVE (new-or-existing)
        parameter/operator pair. Mirrors how the engine coerces the citizen
        value before comparing, so an accepted rule is always deterministic.
        """
        parameter_name = rule.get("parameter_name")
        if parameter_name is not None:
            parameter_name = parameter_name.strip()
            self._enum(
                "parameter_name", parameter_name, ELIGIBILITY_RULE_PARAMETERS
            )
        elif existing_rule is not None:
            parameter_name = existing_rule.parameter_name

        operator = rule.get("operator")
        if operator is not None:
            operator = operator.strip()
            self._enum("operator", operator, ELIGIBILITY_RULE_OPERATORS)
        elif existing_rule is not None:
            operator = existing_rule.operator

        raw_value = rule.get("required_value")
        if raw_value is None:
            if existing_rule is None:
                raise RuleAdminError("required_value is required", 400)
            # Inherit the existing value — but it is re-validated against the
            # effective parameter/operator pair below, so a partial update
            # can never leave a type-incompatible rule behind.
            raw_value = existing_rule.required_value
        else:
            if not isinstance(raw_value, str):
                raise RuleAdminError("required_value must be a string", 400)
            raw_value = raw_value.strip()
            if not raw_value:
                raise RuleAdminError("required_value must not be empty", 400)
            if len(raw_value) > 255:
                raise RuleAdminError(
                    "required_value must be at most 255 characters", 400
                )

        assert parameter_name is not None and operator is not None

        if parameter_name in NumericRuleParameters and operator != "IN":
            try:
                float(raw_value)
            except ValueError:
                raise RuleAdminError(
                    f"required_value for numeric parameter '{parameter_name}' "
                    f"must be a number (e.g. '18'), got '{raw_value}'",
                    400,
                ) from None

        if parameter_name in BooleanRuleParameters and operator != "IN":
            if operator in ("==", "!="):
                lowered = raw_value.lower()
                if lowered not in _BOOLEAN_TRUE + _BOOLEAN_FALSE:
                    raise RuleAdminError(
                        f"required_value for boolean parameter "
                        f"'{parameter_name}' must be true/1/yes or "
                        f"false/0/no, got '{raw_value}'",
                        400,
                    )
            else:  # < <= > >= are meaningless against a boolean
                raise RuleAdminError(
                    f"operator '{operator}' is not valid for boolean "
                    f"parameter '{parameter_name}' (use == or !=)",
                    400,
                )

        if operator == "IN":
            items = [item.strip() for item in raw_value.split(",") if item.strip()]
            if not items:
                raise RuleAdminError(
                    "required_value for operator 'IN' must be a "
                    "comma-separated list with at least one item",
                    400,
                )
            # The engine can only ever match citizen values that exist as
            # single items, so empty items are rejected rather than ignored.
            if len(items) != len(raw_value.split(",")):
                raise RuleAdminError(
                    "required_value for operator 'IN' must not contain "
                    "empty items (e.g. 'BPL,,AAY')",
                    400,
                )
            normalized = ",".join(items)
            # Items are trimmed, so the normalized value is never longer
            # than the already length-capped raw input.
            return normalized

        return raw_value

    # ------------------------------------------------------------------
    # Group queries / mutations
    # ------------------------------------------------------------------

    async def _require_scheme(self, scheme_id: uuid.UUID) -> SchemeMaster:
        scheme = await self.db.get(SchemeMaster, scheme_id)
        if scheme is None:
            raise RuleAdminError("Scheme not found", 404)
        return scheme

    async def list_groups(self, scheme_id: uuid.UUID) -> list[SchemeRuleGroup]:
        """Groups (any rule state) of one scheme, priority-ordered, rules eager.

        Rules are selectin-loaded because async sessions cannot lazy-load
        nested relationships (MissingGreenlet).
        """
        await self._require_scheme(scheme_id)
        result = await self.db.execute(
            select(SchemeRuleGroup)
            .where(SchemeRuleGroup.scheme_id == scheme_id)
            .options(selectinload(SchemeRuleGroup.rules))
            .order_by(SchemeRuleGroup.group_priority)
        )
        return list(result.scalars().all())

    async def get_group(self, scheme_id: uuid.UUID, group_id: uuid.UUID) -> SchemeRuleGroup:
        await self._require_scheme(scheme_id)
        result = await self.db.execute(
            select(SchemeRuleGroup)
            .where(
                SchemeRuleGroup.group_id == group_id,
                SchemeRuleGroup.scheme_id == scheme_id,
            )
            .options(selectinload(SchemeRuleGroup.rules))
        )
        group = result.scalars().first()
        if group is None:
            raise RuleAdminError("Rule group not found for this scheme", 404)
        return group

    async def create_group(
        self,
        scheme_id: uuid.UUID,
        *,
        group_name: str,
        intra_group_operator: str = "AND",
        group_priority: int = 1,
    ) -> SchemeRuleGroup:
        scheme = await self._require_scheme(scheme_id)
        name = self._require_text("group_name", group_name, 100)
        intra_group_operator = (
            self._enum("intra_group_operator", intra_group_operator, GROUP_OPERATORS)
        )
        group = SchemeRuleGroup(
            scheme_id=scheme_id,
            group_name=name,
            intra_group_operator=intra_group_operator,
            group_priority=group_priority,
        )
        self.db.add(group)
        scheme.last_updated_at = _utcnow()
        await self.db.flush()
        # Re-fetch eagerly: the fresh object's `rules` relationship is not
        # loaded after flush, and async sessions cannot lazy-load it.
        return await self.get_group(scheme_id, group.group_id)

    async def update_group(
        self,
        scheme_id: uuid.UUID,
        group_id: uuid.UUID,
        *,
        group_name: str | None = None,
        intra_group_operator: str | None = None,
        group_priority: int | None = None,
    ) -> SchemeRuleGroup:
        """Edit a group where safe.

        Changing intra_group_operator changes eligibility outcomes for the
        whole group (all() <-> any()) — it IS supported here because the
        change is explicit, validated against the existing AND|OR vocabulary,
        and semantics-tested. The change never alters individual rules.
        """
        scheme = await self._require_scheme(scheme_id)
        group = await self.get_group(scheme_id, group_id)
        if group_name is not None:
            group.group_name = self._require_text("group_name", group_name, 100)
        if intra_group_operator is not None:
            group.intra_group_operator = self._enum(
                "intra_group_operator", intra_group_operator, GROUP_OPERATORS
            )
        if group_priority is not None:
            group.group_priority = group_priority
        scheme.last_updated_at = _utcnow()
        await self.db.flush()
        # Re-fetch eagerly (see create_group): the rules relationship must
        # be loaded for async serialization.
        return await self.get_group(scheme_id, group.group_id)

    async def delete_group(self, scheme_id: uuid.UUID, group_id: uuid.UUID) -> None:
        """Hard delete a group ONLY when it carries no provenance-bearing rule.

        The FK cascade would silently destroy rule provenance along with the
        rules, losing the rule→source citation chain — refused instead (409).
        """
        scheme = await self._require_scheme(scheme_id)
        group = await self.get_group(scheme_id, group_id)
        rules = (
            (
                await self.db.execute(
                    select(SchemeEligibilityRule).where(
                        SchemeEligibilityRule.group_id == group_id
                    )
                )
            )
            .scalars()
            .all()
        )
        if rules and await self._provenance_exists([r.rule_id for r in rules]):
            raise RuleAdminError(
                "Rule group contains rules with source provenance; "
                "remove the provenance links first",
                409,
            )
        await self.db.delete(group)
        scheme.last_updated_at = _utcnow()
        await self.db.flush()

    # ------------------------------------------------------------------
    # Rule queries / mutations
    # ------------------------------------------------------------------

    async def list_rules(self, scheme_id: uuid.UUID) -> list[SchemeEligibilityRule]:
        await self._require_scheme(scheme_id)
        result = await self.db.execute(
            select(SchemeEligibilityRule)
            .where(SchemeEligibilityRule.scheme_id == scheme_id)
            .order_by(SchemeEligibilityRule.rule_priority)
        )
        return list(result.scalars().all())

    async def get_rule(self, scheme_id: uuid.UUID, rule_id: uuid.UUID) -> SchemeEligibilityRule:
        await self._require_scheme(scheme_id)
        rule = await self.db.get(SchemeEligibilityRule, rule_id)
        if rule is None or rule.scheme_id != scheme_id:
            raise RuleAdminError("Rule not found for this scheme", 404)
        return rule

    async def create_rule(
        self,
        scheme_id: uuid.UUID,
        *,
        group_id: uuid.UUID,
        parameter_name: str,
        operator: str,
        required_value: str,
        rule_description: str | None = None,
        rule_priority: int = 1,
        failure_stage_code: str | None = None,
        remedy_template: str | None = None,
    ) -> SchemeEligibilityRule:
        """Create one mandatory eligibility rule inside an existing group.

        The rule joins the scheme's live eligibility graph immediately —
        it is a hard gate the next evaluation consumes.
        """
        scheme = await self._require_scheme(scheme_id)
        group = await self.get_group(scheme_id, group_id)  # validates association
        validated_value = self._validate_required_value(
            {
                "parameter_name": parameter_name,
                "operator": operator,
                "required_value": required_value,
            }
        )
        if failure_stage_code is not None:
            self._enum("failure_stage_code", failure_stage_code, FAILURE_STAGE_CODES)

        rule = SchemeEligibilityRule(
            scheme_id=scheme_id,
            group_id=group.group_id,
            group=group,
            parameter_name=parameter_name.strip(),
            operator=(operator or "").strip(),
            required_value=validated_value,
            rule_description=rule_description,
            rule_priority=rule_priority,
            failure_stage_code=failure_stage_code,
            remedy_template=remedy_template,
        )
        self.db.add(rule)
        scheme.last_updated_at = _utcnow()
        await self.db.flush()
        return rule

    async def update_rule(
        self,
        scheme_id: uuid.UUID,
        rule_id: uuid.UUID,
        *,
        group_id: uuid.UUID | None = None,
        parameter_name: str | None = None,
        operator: str | None = None,
        required_value: str | None = None,
        rule_description: str | None = None,
        rule_priority: int | None = None,
        failure_stage_code: str | None = None,
        remedy_template: str | None = None,
    ) -> SchemeEligibilityRule:
        """Edit an existing rule. Validation runs against the EFFECTIVE
        parameter/operator/value triple (new-or-existing fields combined).
        Provenance is not checked on edit: provenance annotates the rule row,
        it does not freeze it (citation still applies to the rule id); only
        deletion is provenance-restricted.
        """
        scheme = await self._require_scheme(scheme_id)
        rule = await self.get_rule(scheme_id, rule_id)

        if group_id is not None and group_id != rule.group_id:
            # Moving a rule between groups must stay within this scheme.
            new_group = await self.get_group(scheme_id, group_id)
            rule.group_id = new_group.group_id
            await self.db.flush()

        effective = {
            "parameter_name": parameter_name,
            "operator": operator,
            "required_value": required_value,
        }
        value = self._validate_required_value(
            effective, existing_rule=rule
        )
        rule.parameter_name = (
            effective["parameter_name"].strip()
            if effective["parameter_name"] is not None
            else rule.parameter_name
        )
        rule.operator = (
            effective["operator"].strip() if effective["operator"] is not None else rule.operator
        )
        rule.required_value = value

        if rule_description is not None:
            rule.rule_description = rule_description
        if rule_priority is not None:
            rule.rule_priority = rule_priority
        if failure_stage_code is not None:
            rule.failure_stage_code = self._enum(
                "failure_stage_code", failure_stage_code, FAILURE_STAGE_CODES
            )
        if remedy_template is not None:
            rule.remedy_template = remedy_template

        scheme.last_updated_at = _utcnow()
        await self.db.flush()
        return rule

    async def delete_rule(self, scheme_id: uuid.UUID, rule_id: uuid.UUID) -> None:
        """Hard delete a rule ONLY when it carries no source provenance (409).
        Assessment history is unaffected: assessments snapshot evidence
        against the scheme and are never recreated when rules change."""
        scheme = await self._require_scheme(scheme_id)
        rule = await self.get_rule(scheme_id, rule_id)
        if await self._provenance_exists([rule.rule_id]):
            raise RuleAdminError(
                "Rule has source provenance; it must stay traceable — "
                "archive the scheme or unlink the provenance first",
                409,
            )
        await self.db.delete(rule)
        scheme.last_updated_at = _utcnow()
        await self.db.flush()

    # ------------------------------------------------------------------
    # Scheme-level group combining operator (explicit, material change)
    # ------------------------------------------------------------------

    async def set_group_combining_operator(
        self, scheme_id: uuid.UUID, operator: str
    ) -> SchemeMaster:
        """Change how the scheme's rule groups are combined (AND | OR).

        Material eligibility change: for AND the citizen must satisfy EVERY
        group; for OR satisfying ANY group is enough. Deliberately routed
        here rather than through the generic scheme PATCH so the change is
        always deliberate, vocabulary-validated, and semantics-tested.
        """
        scheme = await self._require_scheme(scheme_id)
        normalized = operator.strip().upper() if isinstance(operator, str) else operator
        scheme.group_combining_operator = self._enum(
            "group_combining_operator", normalized, GROUP_OPERATORS
        )
        scheme.last_updated_at = _utcnow()
        await self.db.flush()
        return scheme

    # ------------------------------------------------------------------
    # Referential safety
    # ------------------------------------------------------------------

    async def _provenance_exists(self, rule_ids: list[uuid.UUID]) -> bool:
        if not rule_ids:
            return False
        result = await self.db.execute(
            select(func.count())
            .select_from(SchemeRuleProvenance)
            .where(SchemeRuleProvenance.rule_id.in_(rule_ids))
        )
        return result.scalar_one() > 0
