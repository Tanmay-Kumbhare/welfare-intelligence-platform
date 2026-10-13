import { useState, useEffect } from "react";
import Card from "../ui/Card";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import { citizenService } from "../../services/api";
import {
  AlertTriangle,
  AlertCircle,
  Clock,
  HelpCircle,
  CheckCircle,
  FileText,
  ChevronDown,
  ChevronUp,
  RefreshCw,
} from "lucide-react";

/**
 * Maps issue_type to appropriate styling, iconography, and title.
 * Backend types: CONFIRMED_CONFLICT, POSSIBLE_CONFLICT, STALE_FACT, MISSING_INFORMATION
 */
function getIssueMeta(issueType) {
  switch (issueType) {
    case "CONFIRMED_CONFLICT":
      return {
        label: "Confirmed Conflict",
        badgeVariant: "excl",
        icon: AlertTriangle,
        iconColor: "text-excl",
        bgColor: "bg-excl-tint/30",
        borderColor: "border-excl/30",
      };
    case "POSSIBLE_CONFLICT":
      return {
        label: "Possible Conflict",
        badgeVariant: "excl",
        icon: AlertCircle,
        iconColor: "text-excl",
        bgColor: "bg-excl-tint/20",
        borderColor: "border-excl/20",
      };
    case "STALE_FACT":
      return {
        label: "Stale Fact",
        badgeVariant: "neutral",
        icon: Clock,
        iconColor: "text-accent-ink",
        bgColor: "bg-accent-tint/30",
        borderColor: "border-accent/30",
      };
    case "MISSING_INFORMATION":
      return {
        label: "Missing Information",
        badgeVariant: "neutral",
        icon: HelpCircle,
        iconColor: "text-ink-soft",
        bgColor: "bg-surface",
        borderColor: "border-line",
      };
    default:
      return {
        label: issueType ? issueType.replace(/_/g, " ") : "Profile Issue",
        badgeVariant: "neutral",
        icon: AlertCircle,
        iconColor: "text-ink-soft",
        bgColor: "bg-surface",
        borderColor: "border-line",
      };
  }
}

/**
 * Returns severity badge styling
 */
function getSeverityBadge(severity) {
  const sev = (severity || "").toUpperCase();
  if (sev === "HIGH") {
    return <Badge variant="excl">HIGH SEVERITY</Badge>;
  }
  if (sev === "MEDIUM") {
    return <Badge variant="neutral">MEDIUM SEVERITY</Badge>;
  }
  return <Badge variant="neutral">LOW SEVERITY</Badge>;
}

/**
 * ProfileAuditAlert component
 * Surfaces read-only findings from `GET /api/v1/citizens/audit/{citizen_id}`.
 *
 * Invariants:
 * - Read-only: Does not mutate profiles, facts, or documents.
 * - Truth in uncertainty: Clearly differentiates confirmed conflicts from possible conflicts,
 *   stale facts, and missing information without claiming fraud or government rejection.
 * - Safe for guest/unauthenticated users (does not call API if citizenId is falsy).
 */
export default function ProfileAuditAlert({ citizenId, className = "" }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isExpanded, setIsExpanded] = useState(false);

  useEffect(() => {
    if (!citizenId) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }

    let isMounted = true;
    setLoading(true);
    setError(null);

    try {
      const auditPromise = citizenService.audit(citizenId);
      if (!auditPromise || typeof auditPromise.then !== "function") {
        setLoading(false);
        return;
      }

      auditPromise
        .then((res) => {
          if (isMounted) {
            setData(res?.data || null);
            setLoading(false);
          }
        })
        .catch((err) => {
          if (isMounted) {
            setError(
              err?.response?.data?.detail ||
                err?.message ||
                "Unable to complete profile audit at this time."
            );
            setLoading(false);
          }
        });
    } catch (err) {
      if (isMounted) {
        setError(err?.message || "Unable to complete profile audit at this time.");
        setLoading(false);
      }
    }

    return () => {
      isMounted = false;
    };
  }, [citizenId]);

  if (!citizenId) {
    return null;
  }

  if (loading) {
    return (
      <Card className={`mb-6 border-line ${className}`}>
        <div className="flex items-center gap-3 text-ink-soft text-sm">
          <RefreshCw className="h-4 w-4 animate-spin text-accent-ink" />
          <span>Auditing profile consistency and record freshness...</span>
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className={`mb-6 border-excl/30 bg-excl-tint/10 ${className}`}>
        <div className="flex items-start gap-3">
          <AlertCircle className="h-5 w-5 text-excl flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="font-medium text-ink text-sm">Profile Audit Unavailable</h3>
            <p className="text-xs text-ink-soft mt-1">{error}</p>
          </div>
        </div>
      </Card>
    );
  }

  if (!data || !data.summary) {
    return null;
  }

  const { summary, issues = [] } = data;
  const isHealthy = summary.is_healthy && (summary.total_issues === 0 || issues.length === 0);

  // If completely healthy, show a clean, reassuring notice
  if (isHealthy) {
    return (
      <Card className={`mb-6 border-ok/30 bg-ok-tint/10 ${className}`}>
        <div className="flex items-start gap-3">
          <CheckCircle className="h-5 w-5 text-ok flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="font-medium text-ink text-sm">Profile Consistent & Up-to-Date</h3>
            <p className="text-xs text-ink-soft mt-1">
              {summary.summary_message ||
                "No conflicting records, stale facts, or critical missing information detected."}
            </p>
          </div>
        </div>
      </Card>
    );
  }

  // Group issues by category for clear presentation
  const confirmedConflicts = issues.filter((i) => i.issue_type === "CONFIRMED_CONFLICT");
  const possibleConflicts = issues.filter((i) => i.issue_type === "POSSIBLE_CONFLICT");
  const staleFacts = issues.filter((i) => i.issue_type === "STALE_FACT");
  const missingInfo = issues.filter((i) => i.issue_type === "MISSING_INFORMATION");
  const otherIssues = issues.filter(
    (i) =>
      !["CONFIRMED_CONFLICT", "POSSIBLE_CONFLICT", "STALE_FACT", "MISSING_INFORMATION"].includes(
        i.issue_type
      )
  );

  return (
    <Card className={`mb-6 border-line bg-paper-raised ${className}`}>
      {/* Header Summary */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="p-2 rounded bg-accent-tint/40 text-accent-ink mt-0.5">
            <AlertTriangle className="h-5 w-5 text-accent-ink" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-lg font-semibold text-ink m-0">Profile Attention Required</h2>
              <Badge variant="excl">{`${summary.total_issues} Item${summary.total_issues !== 1 ? "s" : ""}`}</Badge>
            </div>
            <p className="text-sm text-ink-soft mt-1">
              {summary.summary_message}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 self-end sm:self-center">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => setIsExpanded((prev) => !prev)}
            className="flex items-center gap-1.5"
            aria-expanded={isExpanded}
          >
            <span>{isExpanded ? "Hide Details" : "Review Issues"}</span>
            {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      {/* Summary Pills */}
      <div className="mt-4 pt-4 border-t border-line flex flex-wrap gap-2 text-xs">
        {summary.confirmed_conflicts_count > 0 && (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-sm bg-excl-tint text-excl-ink font-mono">
            <AlertTriangle className="h-3.5 w-3.5" />
            {`${summary.confirmed_conflicts_count} Confirmed Conflict${summary.confirmed_conflicts_count !== 1 ? "s" : ""}`}
          </span>
        )}
        {summary.possible_conflicts_count > 0 && (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-sm bg-excl-tint/70 text-excl-ink font-mono">
            <AlertCircle className="h-3.5 w-3.5" />
            {`${summary.possible_conflicts_count} Possible Conflict${summary.possible_conflicts_count !== 1 ? "s" : ""}`}
          </span>
        )}
        {summary.stale_facts_count > 0 && (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-sm bg-accent-tint text-accent-ink font-mono">
            <Clock className="h-3.5 w-3.5" />
            {`${summary.stale_facts_count} Stale Fact${summary.stale_facts_count !== 1 ? "s" : ""}`}
          </span>
        )}
        {summary.missing_information_count > 0 && (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-sm bg-surface border border-line text-ink-soft font-mono">
            <HelpCircle className="h-3.5 w-3.5" />
            {`${summary.missing_information_count} Missing Detail${summary.missing_information_count !== 1 ? "s" : ""}`}
          </span>
        )}
      </div>

      {/* Expanded Issues Details */}
      {isExpanded && (
        <div className="mt-5 pt-5 border-t border-line space-y-4">
          <div className="text-xs text-ink-soft bg-surface border border-line p-3 rounded">
            <strong>Audit Note:</strong> Findings highlight discrepancies, outdated declarations,
            or missing attributes across your records. They indicate areas where keeping your
            profile updated ensures complete and accurate welfare eligibility assessments.
          </div>

          {/* Render grouped issues */}
          {confirmedConflicts.length > 0 && (
            <IssueGroupSection title="Confirmed Conflicts" issues={confirmedConflicts} />
          )}

          {possibleConflicts.length > 0 && (
            <IssueGroupSection title="Possible Conflicts" issues={possibleConflicts} />
          )}

          {staleFacts.length > 0 && (
            <IssueGroupSection title="Outdated / Stale Information" issues={staleFacts} />
          )}

          {missingInfo.length > 0 && (
            <IssueGroupSection title="Missing Profile Information" issues={missingInfo} />
          )}

          {otherIssues.length > 0 && (
            <IssueGroupSection title="Other Profile Findings" issues={otherIssues} />
          )}

          <div className="pt-2 flex justify-end">
            <Button to="/profile" variant="primary" size="sm">
              Update Profile in Settings →
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}

/**
 * Section grouping related issues with a clear title
 */
function IssueGroupSection({ title, issues }) {
  return (
    <div className="space-y-3">
      <h3 className="text-xs font-mono uppercase tracking-wider text-ink-soft">{title}</h3>
      <div className="space-y-3">
        {issues.map((issue, idx) => (
          <IssueItemCard key={`${issue.attribute_name}-${issue.issue_type}-${idx}`} issue={issue} />
        ))}
      </div>
    </div>
  );
}

/**
 * Individual issue card rendering details from ProfileAuditIssue schema
 */
function IssueItemCard({ issue }) {
  const meta = getIssueMeta(issue.issue_type);
  const Icon = meta.icon;

  return (
    <div className={`p-4 rounded border ${meta.borderColor} ${meta.bgColor} space-y-3`}>
      {/* Title & Badges */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Icon className={`h-4 w-4 ${meta.iconColor} flex-shrink-0`} />
          <span className="font-semibold text-sm text-ink">{issue.attribute_label || issue.attribute_name}</span>
          <Badge variant={meta.badgeVariant}>{meta.label}</Badge>
        </div>
        <div>{getSeverityBadge(issue.severity)}</div>
      </div>

      {/* Description & Explanation */}
      <div className="text-sm text-ink space-y-1">
        <p className="font-medium">{issue.description}</p>
        {issue.explanation && <p className="text-xs text-ink-soft">{issue.explanation}</p>}
      </div>

      {/* Current vs Conflicting Value (if applicable) */}
      {(issue.current_value !== null || issue.conflicting_value !== null) && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-mono bg-paper-raised/80 p-2.5 rounded border border-line">
          {issue.current_value !== null && issue.current_value !== undefined && (
            <div>
              <span className="text-ink-soft block text-[10px] uppercase">Recorded / Active Value</span>
              <span className="text-ink font-semibold">{String(issue.current_value)}</span>
            </div>
          )}
          {issue.conflicting_value !== null && issue.conflicting_value !== undefined && (
            <div>
              <span className="text-excl-ink block text-[10px] uppercase">Conflicting / Alternate Value</span>
              <span className="text-excl-ink font-semibold">{String(issue.conflicting_value)}</span>
            </div>
          )}
        </div>
      )}

      {/* Sources & Evidence */}
      {issue.sources && issue.sources.length > 0 && (
        <div className="text-xs">
          <p className="text-[11px] font-mono text-ink-soft uppercase tracking-wider mb-1">
            Recorded Sources & Evidence:
          </p>
          <ul className="space-y-1 list-none p-0 m-0">
            {issue.sources.map((src, sIdx) => (
              <li
                key={sIdx}
                className="flex items-center gap-2 text-ink-soft bg-paper-raised/60 px-2 py-1 rounded text-[11px]"
              >
                <FileText className="h-3.5 w-3.5 text-ink-soft flex-shrink-0" />
                <span>
                  <strong className="text-ink">{src.source_type}</strong>
                  {src.source_reference ? ` (${src.source_reference})` : ""}:{" "}
                  {src.value !== null && src.value !== undefined ? String(src.value) : "Recorded"}
                  {src.verified ? " [Verified]" : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Affected Schemes */}
      {issue.affected_schemes && issue.affected_schemes.length > 0 && (
        <div className="text-xs">
          <p className="text-[11px] font-mono text-ink-soft uppercase tracking-wider mb-1">
            Potentially Impacted Schemes / Criteria:
          </p>
          <div className="flex flex-wrap gap-1.5">
            {issue.affected_schemes.map((schemeName, scIdx) => (
              <Badge key={scIdx} pill={true}>
                {schemeName}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {/* Recommended Action */}
      {issue.recommended_action && (
        <div className="text-xs bg-paper-raised p-2.5 rounded border border-line flex items-start gap-2">
          <span className="font-semibold text-ink flex-shrink-0">Recommended Action:</span>
          <span className="text-ink-soft">{issue.recommended_action}</span>
        </div>
      )}
    </div>
  );
}
