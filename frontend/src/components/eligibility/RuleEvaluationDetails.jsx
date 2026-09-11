import Badge from "../ui/Badge";
import Card from "../ui/Card";
import { describeActualValue, describeRequiredValue, parameterLabel } from "../../utils/ruleFormat";

function formatRule(rule) {
  return {
    parameter_name: rule.parameter,
    operator: rule.operator,
    required: rule.required,
    actual: rule.actual,
  };
}

export default function RuleEvaluationDetails({ details, failedOnly = false }) {
  if (!details || !Array.isArray(details.groups)) return null;

  return (
    <div className="space-y-4">
      {details.groups.map((group) => {
        const rules = (group.rules || []).filter((rule) => !failedOnly || !rule.passed);
        if (rules.length === 0) return null;
        const isOr = String(group.intra_group_operator).toUpperCase() === "OR";

        return (
          <Card key={group.group_name} className="p-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line pb-3 mb-3">
              <h3 className="text-sm mb-0">{group.group_name}</h3>
              <span className="font-mono text-xs text-ink-soft">
                {isOr ? "At least one of these conditions must be satisfied." : "All of these conditions must be satisfied."}
              </span>
            </div>
            <div className="space-y-3">
              {rules.map((rule, index) => {
                const formatted = formatRule(rule);
                return (
                  <div key={`${rule.parameter}-${index}`} className="border-b border-line last:border-0 pb-3 last:pb-0">
                    <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
                      <p className="text-sm text-ink mb-0">{parameterLabel(rule.parameter)}</p>
                      <Badge variant={rule.passed ? "ok" : "excl"}>
                        {rule.passed ? "Meets requirement" : "Does not meet requirement"}
                      </Badge>
                    </div>
                    <dl className="grid sm:grid-cols-4 gap-2 text-xs">
                      <div><dt className="text-ink-soft">Parameter</dt><dd className="font-mono text-ink mt-1">{parameterLabel(rule.parameter)}</dd></div>
                      <div><dt className="text-ink-soft">Your value</dt><dd className="font-mono text-ink mt-1">{describeActualValue(formatted)}</dd></div>
                      <div><dt className="text-ink-soft">Requirement</dt><dd className="font-mono text-ink mt-1">{describeRequiredValue(formatted)}</dd></div>
                      <div><dt className="text-ink-soft">Result</dt><dd className="font-mono text-ink mt-1">{rule.passed ? "Meets requirement" : "Does not meet requirement"}</dd></div>
                    </dl>
                    {rule.description && <p className="text-xs mt-2 mb-0">{rule.description}</p>}
                  </div>
                );
              })}
            </div>
          </Card>
        );
      })}
    </div>
  );
}
