import { useCallback, useEffect, useState } from "react";
import Button from "../ui/Button";
import Card from "../ui/Card";
import Input from "../ui/Input";
import Select from "../ui/Select";
import Badge from "../ui/Badge";
import { EmptyState, ErrorState, LoadingState } from "../ui/StatusStates";
import ConfirmDialog from "./ConfirmDialog";
import ProvenanceCitation from "./ProvenanceCitation";
import { extractApiErrorMessage } from "../../utils/apiError";
import { adminService } from "../../services/api";
import {
  BOOLEAN_VALUE_OPTIONS,
  ELIGIBILITY_RULE_PARAMETERS,
  FAILURE_STAGE_CODES,
  GROUP_OPERATORS,
  operatorsForParameter,
  requiredValueKind,
} from "./rulesVocabulary";

/**
 * Rule admin UI over the backend RuleAdminService endpoints.
 *
 * SEMANTICS PRESERVED (do not weaken them in the UI):
 * - Every rule IS a hard eligibility gate — no "mandatory" checkbox and no
 *   "weight" field exists in the backend, so none is shown. rule_priority is
 *   diagnostic ordering only, NOT a ranking weight.
 * - group_combining_operator (AND/OR across groups) is a material eligibility
 *   change → explicit confirming action, never part of generic metadata edit.
 * - Rules carrying provenance citations cannot be deleted (backend 409);
 *   dialogs say exactly what the backend does, never more.
 */

const PRIORITY_HINT =
  "Diagnostic ordering of failures in explanations — NOT a ranking weight.";

/** Dynamic value editor per the frozen parameter vocabulary. */
function ValueEditor({ parameterName, operator, value, onChange, inputId }) {
  const kind = requiredValueKind(parameterName, operator);

  if (kind === "list") {
    return (
      <Input
        id={inputId}
        label="Value (comma-separated list)"
        required
        hint="IN matches if the citizen value equals any trimmed item, e.g. BPL,AAY"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  if (kind === "numeric") {
    return (
      <Input
        id={inputId}
        label="Value (number)"
        required
        type="number"
        step="any"
        inputMode="decimal"
        hint="Backend rejects a non-numeric value for this parameter"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  if (kind === "boolean") {
    return (
      <Select
        id={inputId}
        label="Value"
        required
        hint="Stores the truth tokens the engine coerces (true/1/yes, false/0/no)"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">— select —</option>
        {BOOLEAN_VALUE_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </Select>
    );
  }
  return (
    <Input
      id={inputId}
      label="Value (text)"
      required
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

function RuleEditor({ schemeId, existingRule, groups, groupId, onError, onDone }) {
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [fields, setFields] = useState({
    group_id: existingRule?.group_id || groupId || groups[0]?.group_id || "",
    parameter_name: existingRule?.parameter_name || "",
    operator: existingRule?.operator || "==",
    required_value: existingRule?.required_value || "",
    rule_description: existingRule?.rule_description || "",
    rule_priority: String(existingRule?.rule_priority ?? 1),
    failure_stage_code: existingRule?.failure_stage_code || "S0_ELIGIBILITY",
    remedy_template: existingRule?.remedy_template || "",
  });
  const setField = (name, value) =>
    setFields((current) => ({ ...current, [name]: value }));

  const key = existingRule?.rule_id ?? "new";
  const effectiveOperators = operatorsForParameter(
    fields.parameter_name,
    fields.operator
  );
  if (!effectiveOperators.includes(fields.operator)) {
    // Parameter changed to a boolean parameter with an incompatible operator
    // selected — nudge the operator back to a valid choice (UX only).
    setField("operator", effectiveOperators[0] || "==");
  }

  const valueKind = requiredValueKind(fields.parameter_name, fields.operator);
  const clientErrors = [];
  if (!fields.parameter_name) clientErrors.push("Parameter is required");
  if (!fields.operator) clientErrors.push("Operator is required");
  if (!fields.required_value.trim()) {
    clientErrors.push("Value is required");
  } else if (valueKind === "numeric" && Number.isNaN(Number(fields.required_value))) {
    clientErrors.push("This parameter expects a numeric value");
  } else if (
    valueKind === "boolean" &&
    !["true", "1", "yes", "false", "0", "no"].includes(
      fields.required_value.trim().toLowerCase()
    )
  ) {
    clientErrors.push("Boolean parameters take true/1/yes or false/0/no");
  } else if (valueKind === "list" && !fields.required_value.includes(",")) {
    clientErrors.push("IN expects a comma-separated list — a single value is accepted but deliberate");
  }

  const save = async (event) => {
    event.preventDefault();
    setSaving(true);
    setFormError("");
    const payload = {
      group_id: fields.group_id,
      parameter_name: fields.parameter_name,
      operator: fields.operator,
      required_value: fields.required_value.trim(),
      rule_description: fields.rule_description || null,
      rule_priority: Number(fields.rule_priority) || 1,
      failure_stage_code: fields.failure_stage_code || null,
      remedy_template: fields.remedy_template || null,
    };
    try {
      if (existingRule) {
        await adminService.updateRule(schemeId, existingRule.rule_id, payload);
      } else {
        await adminService.createRule(schemeId, payload);
      }
      onDone();
    } catch (requestError) {
      // Backend validation is authoritative — surface its verdict verbatim.
      setFormError(
        extractApiErrorMessage(requestError, "The server rejected this rule.")
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={save} className="border border-line rounded-sm p-4 bg-white mt-2">
      {formError && <p className="text-sm text-excl-ink mb-3">{formError}</p>}
      <div className="grid md:grid-cols-2 gap-x-5">
        <Select
          id={`rule-group-${key}`}
          label="Rule group"
          required
          hint="Which set of conditions this gate belongs to"
          value={fields.group_id}
          onChange={(e) => setField("group_id", e.target.value)}
        >
          {groups.map((group) => (
            <option key={group.group_id} value={group.group_id}>
              {group.group_name} ({group.intra_group_operator})
            </option>
          ))}
        </Select>
        <Select
          id={`rule-param-${key}`}
          label="Parameter"
          required
          hint="Only attributes the deterministic engine can resolve"
          value={fields.parameter_name}
          onChange={(e) => setField("parameter_name", e.target.value)}
        >
          <option value="">— select parameter —</option>
          {ELIGIBILITY_RULE_PARAMETERS.map((parameter) => (
            <option key={parameter} value={parameter}>{parameter}</option>
          ))}
        </Select>
        <Select
          id={`rule-op-${key}`}
          label="Operator"
          required
          value={fields.operator}
          onChange={(e) => setField("operator", e.target.value)}
        >
          {effectiveOperators.map((operator) => (
            <option key={operator} value={operator}>{operator}</option>
          ))}
        </Select>
        <ValueEditor
          parameterName={fields.parameter_name}
          operator={fields.operator}
          inputId={`rule-value-${key}`}
          value={fields.required_value}
          onChange={(v) => setField("required_value", v)}
        />
        <div className="md:col-span-2">
          <Input
            id={`rule-desc-${key}`}
            label="Rule description"
            hint="Shown in citizen-facing evaluation explanations"
            value={fields.rule_description}
            onChange={(e) => setField("rule_description", e.target.value)}
          />
        </div>
        <Input
          id={`rule-priority-${key}`}
          label="Rule priority"
          type="number"
          hint={PRIORITY_HINT}
          value={fields.rule_priority}
          onChange={(e) => setField("rule_priority", e.target.value)}
        />
        <Select
          id={`rule-stage-${key}`}
          label="Failure stage"
          hint="Where a failed rule is reported in the pipeline"
          value={fields.failure_stage_code}
          onChange={(e) => setField("failure_stage_code", e.target.value)}
        >
          <option value="">— none —</option>
          {FAILURE_STAGE_CODES.map((stage) => (
            <option key={stage} value={stage}>{stage}</option>
          ))}
        </Select>
        <div className="md:col-span-2">
          <Input
            id={`rule-remedy-${key}`}
            label="Remedy template"
            hint="Guidance shown to the citizen when the rule fails"
            value={fields.remedy_template}
            onChange={(e) => setField("remedy_template", e.target.value)}
          />
        </div>
      </div>
      <p className="text-[11px] text-ink-soft italic mt-3 max-w-[75ch]">
        Every rule is a hard eligibility gate: the scheme fails unless the rule
        passes (subject to the group and scheme combining operators). There is
        no per-rule mandatory flag, no weighting, and no soft bypass.
      </p>
      {clientErrors.length > 0 && (
        <ul className="text-[13px] text-excl-ink mt-2 list-disc list-inside">
          {clientErrors.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      )}
      <div className="flex gap-2 mt-4">
        <button
          type="submit"
          disabled={saving || clientErrors.length > 0 || !fields.group_id}
          className="px-4 py-2 text-sm rounded-sm bg-accent text-white hover:bg-accent-ink disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? "Saving…" : existingRule ? "Save rule" : "Add rule"}
        </button>
        <Button
          type="button"
          variant="secondary"
          onClick={onDone}
          disabled={saving}
        >
          Cancel
        </Button>
      </div>
    </form>
  );
}

function GroupEditor({ schemeId, existingGroup, onError, onDone }) {
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [fields, setFields] = useState({
    group_name: existingGroup?.group_name || "",
    intra_group_operator: existingGroup?.intra_group_operator || "AND",
    group_priority: String(existingGroup?.group_priority ?? 1),
  });
  const setField = (name, value) =>
    setFields((current) => ({ ...current, [name]: value }));

  const save = async (event) => {
    event.preventDefault();
    setSaving(true);
    setFormError("");
    try {
      const payload = {
        group_name: fields.group_name,
        intra_group_operator: fields.intra_group_operator,
        group_priority: Number(fields.group_priority) || 1,
      };
      if (existingGroup) {
        await adminService.updateRuleGroup(schemeId, existingGroup.group_id, payload);
      } else {
        await adminService.createRuleGroup(schemeId, payload);
      }
      onDone();
    } catch (requestError) {
      setFormError(
        extractApiErrorMessage(requestError, "The server rejected this group.")
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={save} className="border border-line rounded-sm p-4 bg-white mt-2">
      {formError && <p className="text-sm text-excl-ink mb-3">{formError}</p>}
      <div className="grid md:grid-cols-3 gap-x-5">
        <Input
          id={`group-name-${existingGroup?.group_id ?? "new"}`}
          label="Group name"
          required
          value={fields.group_name}
          onChange={(e) => setField("group_name", e.target.value)}
        />
        <Select
          id={`group-op-${existingGroup?.group_id ?? "new"}`}
          label="Intra-group operator"
          required
          hint="How the rules inside this group combine"
          value={fields.intra_group_operator}
          onChange={(e) => setField("intra_group_operator", e.target.value)}
        >
          {GROUP_OPERATORS.map((operator) => (
            <option key={operator} value={operator}>{operator}</option>
          ))}
        </Select>
        <Input
          id={`group-priority-${existingGroup?.group_id ?? "new"}`}
          label="Group priority"
          type="number"
          hint="Diagnostic ordering only — not a weight"
          value={fields.group_priority}
          onChange={(e) => setField("group_priority", e.target.value)}
        />
      </div>
      <div className="flex gap-2 mt-4">
        <Button type="submit" disabled={saving || !fields.group_name.trim()}>
          {saving ? "Saving…" : existingGroup ? "Save group" : "Add group"}
        </Button>
        <Button type="button" variant="secondary" onClick={onDone} disabled={saving}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function RuleRow({ rule, schemeId, groups, onChanged, onError, editingActive, onToggleEdit }) {
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [busy, setBusy] = useState(false);

  const deleteRule = async () => {
    setBusy(true);
    try {
      await adminService.deleteRule(schemeId, rule.rule_id);
      setConfirmingDelete(false);
      onChanged();
    } catch (requestError) {
      onError(extractApiErrorMessage(requestError, "Rule deletion failed."));
      setConfirmingDelete(false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border border-line rounded-sm p-3 bg-paper">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-sm text-ink">
          <span className="font-mono">{rule.parameter_name}</span>{" "}
          {rule.operator}{" "}
          <span className="font-mono">{rule.required_value}</span>
          {rule.rule_description ? ` — ${rule.rule_description}` : ""}
          <span className="text-[11px] text-ink-soft ml-2">
            priority {rule.rule_priority}
          </span>
        </p>
        <div className="flex gap-1.5">
          <Button size="sm" variant="ghost" onClick={onToggleEdit}>
            {editingActive ? "Close editor" : "Edit"}
          </Button>
          <Button
            size="sm"
            variant="danger"
            aria-label={`Delete rule ${rule.parameter_name} (${rule.operator} ${rule.required_value})`}
            onClick={() => setConfirmingDelete(true)}
          >
            Delete
          </Button>
        </div>
      </div>

      {editingActive && (
        <RuleEditor
          schemeId={schemeId}
          existingRule={/** @type {any} */ (rule)}
          groups={groups}
          onError={onError}
          onDone={() => {
            onToggleEdit();
            onChanged();
          }}
        />
      )}

      {rule.failure_stage_code && (
        <p className="text-[11px] text-ink-soft mt-1">
          failure stage: {rule.failure_stage_code}
        </p>
      )}
      {rule.remedy_template && (
        <p className="text-[11px] text-ink-soft italic mt-0.5">
          remedy: {rule.remedy_template}
        </p>
      )}

      <ProvenanceCitation rule={rule} provenance={rule._provenance} onChanged={onChanged} onError={onError} />

      {confirmingDelete && (
        <ConfirmDialog
          danger
          busy={busy}
          title="Delete this rule?"
          onConfirm={deleteRule}
          onCancel={() => setConfirmingDelete(false)}
          body={
            <>
              <p>
                The rule is removed permanently — this cannot be undone. Past
                assessments are not re-evaluated; they keep their own stored
                evidence snapshots.
              </p>
              <p>
                If this rule carries a source citation the backend refuses the
                deletion (409) — the citation must be removed first.
              </p>
            </>
          }
        />
      )}
    </div>
  );
}

function GroupRow({ group, schemeId, groups, onChanged, onError }) {
  const [editing, setEditing] = useState(false);
  const [editingRuleId, setEditingRuleId] = useState(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [busy, setBusy] = useState(false);

  const rules = group.rules || [];
  const anyProvenance = rules.some((rule) => rule._provenance);

  const deleteGroup = async () => {
    setBusy(true);
    try {
      await adminService.deleteRuleGroup(schemeId, group.group_id);
      setConfirmingDelete(false);
      onChanged();
    } catch (requestError) {
      onError(extractApiErrorMessage(requestError, "Group deletion failed."));
      setConfirmingDelete(false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-base text-ink flex items-center gap-2">
            {group.group_name}
            <Badge variant="neutral">{group.intra_group_operator}</Badge>
            <Badge pill>priority {group.group_priority}</Badge>
          </h3>
          <p className="text-xs text-ink-soft mt-0.5">
            {rules.length} rule{rules.length === 1 ? "" : "s"} in this group
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setEditingRuleId("new");
              setEditing(false);
            }}
          >
            + Add rule
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setEditing((v) => !v);
              setEditingRuleId(null);
            }}
          >
            Edit group
          </Button>
          <Button size="sm" variant="danger" onClick={() => setConfirmingDelete(true)}>
            Delete group
          </Button>
        </div>
      </div>

      {editing && (
        <GroupEditor
          schemeId={schemeId}
          existingGroup={group}
          onError={onError}
          onDone={() => {
            setEditing(false);
            onChanged();
          }}
        />
      )}
      {!editing && editingRuleId === "new" && (
        <RuleEditor
          schemeId={schemeId}
          groups={groups}
          groupId={group.group_id}
          onError={onError}
          onDone={() => {
            setEditingRuleId(null);
            onChanged();
          }}
        />
      )}

      <div className="mt-3 space-y-2">
        {rules.length === 0 ? (
          <p className="text-sm text-ink-soft">No rules in this group yet.</p>
        ) : (
          rules.map((rule) => (
            <RuleRow
              key={rule.rule_id}
              rule={rule}
              schemeId={schemeId}
              groups={groups}
              onChanged={onChanged}
              onError={onError}
              editingActive={editingRuleId === rule.rule_id}
              onToggleEdit={() =>
                setEditingRuleId(editingRuleId === rule.rule_id ? null : rule.rule_id)
              }
            />
          ))
        )}
      </div>

      {confirmingDelete && (
        <ConfirmDialog
          danger
          busy={busy}
          title="Delete this rule group?"
          onConfirm={deleteGroup}
          onCancel={() => setConfirmingDelete(false)}
          body={
            <>
              <p>
                <strong>{group.group_name}</strong> and all its rules are
                removed permanently — this cannot be undone, and changing
                eligibility can change real citizen outcomes.
              </p>
              {anyProvenance && (
                <p className="text-excl-ink">
                  At least one rule here carries a source citation — the
                  backend will refuse the deletion (409) to protect the
                  evidence chain.
                </p>
              )}
            </>
          }
        />
      )}
    </Card>
  );
}

export default function RuleManager({ scheme, onSchemeChanged }) {
  const schemeId = scheme.scheme_id;
  const [groups, setGroups] = useState(null);
  const [error, setError] = useState("");
  const [bannerError, setBannerError] = useState("");
  const [creatingGroup, setCreatingGroup] = useState(false);
  const [confirmingOperator, setConfirmingOperator] = useState(null);
  const [busyOperator, setBusyOperator] = useState(false);

  // Loads groups AND the provenance map, then attaches per-rule citations so
  // the citation UI can live inside the rules it belongs to.
  const load = useCallback(async () => {
    try {
      const [groupsResponse, provenanceResponse] = await Promise.all([
        adminService.listRuleGroups(schemeId),
        adminService.rulesWithProvenance(schemeId),
      ]);
      const byRuleId = {};
      for (const entry of provenanceResponse.data.rules || []) {
        if (entry.provenance) byRuleId[entry.rule_id] = entry.provenance;
      }
      setGroups(
        (groupsResponse.data || []).map((group) => ({
          ...group,
          rules: (group.rules || []).map((rule) => ({
            ...rule,
            _provenance: byRuleId[rule.rule_id] || null,
          })),
        }))
      );
      setError("");
    } catch (requestError) {
      setError(extractApiErrorMessage(requestError, "Could not load rule groups."));
    }
  }, [schemeId]);

  useEffect(() => {
    load();
  }, [load]);

  const reloadAll = () => {
    load();
    onSchemeChanged?.();
  };

  const setCombiningOperator = async () => {
    setBusyOperator(true);
    try {
      await adminService.setGroupCombiningOperator(schemeId, confirmingOperator);
      setConfirmingOperator(null);
      reloadAll();
    } catch (requestError) {
      setBannerError(extractApiErrorMessage(requestError, "Operator change failed."));
      setConfirmingOperator(null);
    } finally {
      setBusyOperator(false);
    }
  };

  if (error && !groups) {
    return <ErrorState title="Unable to load rules" message={error} onRetry={load} />;
  }
  if (!groups) {
    return <LoadingState label="Loading rule groups..." />;
  }

  return (
    <section aria-label="Eligibility rules">
      {bannerError && <p className="text-sm text-excl-ink mb-3">{bannerError}</p>}

      <Card className="mb-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-base text-ink flex items-center gap-2">
              Groups combine with
              <Badge variant="neutral">{scheme.group_combining_operator}</Badge>
            </h3>
            <p className="text-xs text-ink-soft mt-1 max-w-[65ch]">
              Scheme-level operator: with AND, every group's conditions must
              pass; with OR, one passing group is enough. Changing it changes
              eligibility outcomes for every citizen evaluated against this
              scheme — never part of ordinary metadata editing.
            </p>
          </div>
          <div className="flex gap-2">
            {GROUP_OPERATORS.filter((op) => op !== scheme.group_combining_operator).map(
              (op) => (
                <Button
                  key={op}
                  size="sm"
                  variant="secondary"
                  onClick={() => setConfirmingOperator(op)}
                >
                  Switch to {op}
                </Button>
              )
            )}
          </div>
        </div>
      </Card>

      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg text-ink">Rule groups</h2>
        <Button size="sm" variant="primary" onClick={() => setCreatingGroup((v) => !v)}>
          {creatingGroup ? "Close" : "+ Add group"}
        </Button>
      </div>

      {creatingGroup && (
        <GroupEditor
          schemeId={schemeId}
          onError={setBannerError}
          onDone={() => {
            setCreatingGroup(false);
            reloadAll();
          }}
        />
      )}

      <div className="space-y-4">
        {groups.length === 0 ? (
          <EmptyState
            title="No rule groups yet"
            message="An active scheme with zero rules is treated as not eligible for every citizen. Add the first group to start defining eligibility."
            action={
              !creatingGroup && (
                <Button variant="secondary" onClick={() => setCreatingGroup(true)}>
                  + Add group
                </Button>
              )
            }
          />
        ) : (
          groups.map((group) => (
            <GroupRow
              key={group.group_id}
              group={group}
              schemeId={schemeId}
              groups={groups}
              onChanged={reloadAll}
              onError={setBannerError}
            />
          ))
        )}
      </div>

      {confirmingOperator && (
        <ConfirmDialog
          danger
          busy={busyOperator}
          title={`Switch group combining to ${confirmingOperator}?`}
          onConfirm={setCombiningOperator}
          onCancel={() => setConfirmingOperator(null)}
          body={
            <>
              <p>
                With <strong>{confirmingOperator}</strong>, rule groups combine
                as{" "}
                {confirmingOperator === "AND"
                  ? "ALL groups must pass"
                  : "ANY passing group makes the citizen eligible"}
                . This changes real eligibility outcomes immediately.
              </p>
              <p>The current value is {scheme.group_combining_operator}.</p>
            </>
          }
        />
      )}
    </section>
  );
}
