import { Link } from "react-router-dom";
import Badge from "../ui/Badge";
import Card from "../ui/Card";
import { Sparkles, ArrowRight, CheckCircle, HelpCircle } from "lucide-react";
import { categoryLabel } from "../../utils/ruleFormat";

/**
 * Renders suggested alternative schemes for an ineligible scheme assessment:
 * - Scheme name and link to /schemes/:schemeId
 * - Suggestion reason formulated by backend
 * - Rule match score (if present)
 * - Distinct styling for confirmed-eligible schemes vs unconfirmed suggestions
 * - Clear citizen disclaimer: "These are suggested alternatives, not a guarantee of eligibility or approval."
 * - Filters out targetSchemeId to guarantee no self-recommendation
 */
export default function AlternativeSchemesCard({
  alternatives,
  targetSchemeId,
  className = "",
}) {
  if (!Array.isArray(alternatives) || alternatives.length === 0) {
    return null;
  }

  // Filter out any self-recommendation if targetSchemeId is provided
  const validAlternatives = alternatives.filter((item) => {
    if (!item || !item.scheme_id) return false;
    if (targetSchemeId && String(item.scheme_id) === String(targetSchemeId)) {
      return false;
    }
    return true;
  });

  if (validAlternatives.length === 0) {
    return null;
  }

  return (
    <Card className={`border-line bg-paper/50 ${className}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line pb-3 mb-3">
        <div className="flex items-center gap-1.5">
          <Sparkles className="h-4 w-4 text-accent" aria-hidden="true" />
          <h4 className="text-base font-semibold text-ink mb-0">
            Suggested Alternative Schemes
          </h4>
        </div>
        <span className="font-mono text-xs text-ink-soft">
          {validAlternatives.length} {validAlternatives.length === 1 ? "suggestion" : "suggestions"}
        </span>
      </div>

      <p className="text-xs text-ink-soft mb-3 leading-relaxed font-sans">
        Based on your profile, you may be interested in these related schemes.
      </p>

      <div className="space-y-3">
        {validAlternatives.map((alt, index) => {
          const isEligible = Boolean(alt.is_confirmed_eligible);
          const hasScore =
            alt.rule_match_score !== null &&
            alt.rule_match_score !== undefined &&
            !Number.isNaN(Number(alt.rule_match_score));
          const scoreDisplay = hasScore
            ? `${Math.max(0, Math.min(100, Math.round(Number(alt.rule_match_score))))}%`
            : null;

          return (
            <div
              key={alt.scheme_id || index}
              className="p-3 bg-paper-raised rounded border border-line text-xs"
            >
              <div className="flex flex-wrap items-start justify-between gap-2 mb-1.5">
                <div>
                  <h5 className="text-sm font-semibold text-ink mb-1">
                    {alt.scheme_name}
                  </h5>
                  <div className="flex flex-wrap items-center gap-2 text-[11px] text-ink-soft">
                    {alt.department_name && <span>{alt.department_name}</span>}
                    {alt.scheme_category && (
                      <Badge variant="neutral" pill>
                        {categoryLabel(alt.scheme_category)}
                      </Badge>
                    )}
                    {scoreDisplay && (
                      <span className="font-mono bg-paper px-1.5 py-0.5 rounded border border-line text-ink">
                        Match: {scoreDisplay}
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex flex-col items-end gap-1.5">
                  {isEligible ? (
                    <Badge variant="ok" className="flex items-center gap-1">
                      <CheckCircle className="h-3 w-3" aria-hidden="true" />
                      Confirmed Eligible
                    </Badge>
                  ) : (
                    <Badge variant="neutral" className="flex items-center gap-1">
                      <HelpCircle className="h-3 w-3" aria-hidden="true" />
                      Suggested Option
                    </Badge>
                  )}
                </div>
              </div>

              {alt.suggestion_reason && (
                <p className="text-xs text-ink-soft mb-2 leading-relaxed">
                  {alt.suggestion_reason}
                </p>
              )}

              <div className="flex justify-end pt-1 border-t border-line/60">
                <Link
                  to={`/schemes/${alt.scheme_id}`}
                  className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
                >
                  View scheme details <ArrowRight className="h-3 w-3" aria-hidden="true" />
                </Link>
              </div>
            </div>
          );
        })}
      </div>

      <p className="text-[11px] text-ink-soft border-t border-line pt-2.5 mt-3 mb-0 italic leading-normal">
        These are suggested alternatives, not a guarantee of eligibility or approval.
      </p>
    </Card>
  );
}
