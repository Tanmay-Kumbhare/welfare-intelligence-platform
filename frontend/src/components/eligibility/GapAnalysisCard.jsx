import Badge from "../ui/Badge";
import Card from "../ui/Card";
import { AlertCircle, HelpCircle, FileText } from "lucide-react";

/**
 * Renders structured eligibility gap analysis from the backend SchemeGapAnalysis schema:
 * - Failed conditions (criteria not met)
 * - Missing information (profile parameters not provided)
 * - Required documents to review or provide (missing/invalid/pending)
 * - Summary message and citizen-friendly non-guarantee disclaimer
 */
export default function GapAnalysisCard({ gapAnalysis, className = "" }) {
  if (!gapAnalysis || typeof gapAnalysis !== "object") return null;

  const failedConditions = Array.isArray(gapAnalysis.failed_conditions)
    ? gapAnalysis.failed_conditions
    : [];
  const missingInfo = Array.isArray(gapAnalysis.missing_information)
    ? gapAnalysis.missing_information
    : [];
  const missingDocs = Array.isArray(gapAnalysis.missing_documents)
    ? gapAnalysis.missing_documents
    : [];

  const totalGaps = failedConditions.length + missingInfo.length + missingDocs.length;
  if (!gapAnalysis.has_gaps && totalGaps === 0 && !gapAnalysis.summary_message) {
    return null;
  }

  return (
    <Card className={`border-line bg-paper/50 ${className}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line pb-3 mb-3">
        <h4 className="text-base font-semibold text-ink mb-0">Eligibility Gap Analysis</h4>
        <span className="font-mono text-xs text-ink-soft">
          {totalGaps} potential {totalGaps === 1 ? "gap" : "gaps"} identified
        </span>
      </div>

      {gapAnalysis.summary_message && (
        <p className="text-xs text-ink-soft mb-4 leading-relaxed font-sans">
          {gapAnalysis.summary_message}
        </p>
      )}

      {/* 1. Criteria not met (Failed conditions) */}
      {failedConditions.length > 0 && (
        <div className="mb-4">
          <h5 className="text-xs font-mono uppercase text-excl-ink flex items-center gap-1.5 mb-2 font-semibold">
            <AlertCircle className="h-3.5 w-3.5" aria-hidden="true" />
            Criteria Not Met ({failedConditions.length})
          </h5>
          <div className="space-y-2">
            {failedConditions.map((gap, index) => (
              <div
                key={`failed-${gap.parameter || index}`}
                className="p-2.5 bg-paper-raised rounded border border-line text-xs"
              >
                <div className="flex flex-wrap items-center justify-between gap-1 mb-1">
                  <span className="font-medium text-ink">
                    {gap.parameter_label || gap.parameter}
                  </span>
                  <Badge variant="excl">Does not meet requirement</Badge>
                </div>
                <p className="text-xs text-ink-soft mb-1">{gap.message}</p>
                <div className="grid grid-cols-2 gap-2 text-[11px] text-ink-soft border-t border-line/60 pt-1.5 mt-1.5 font-mono">
                  <div>
                    <span>Your value: </span>
                    <strong className="text-ink">{gap.actual_display || "Not provided"}</strong>
                  </div>
                  <div>
                    <span>Required: </span>
                    <strong className="text-ink">{gap.requirement_display || gap.required_value}</strong>
                  </div>
                </div>
                {gap.rule_description && (
                  <p className="text-[11px] text-ink-soft/80 mt-1 mb-0 italic">
                    {gap.rule_description}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 2. Missing information */}
      {missingInfo.length > 0 && (
        <div className="mb-4">
          <h5 className="text-xs font-mono uppercase text-accent-ink flex items-center gap-1.5 mb-2 font-semibold">
            <HelpCircle className="h-3.5 w-3.5" aria-hidden="true" />
            Missing Information ({missingInfo.length})
          </h5>
          <div className="space-y-2">
            {missingInfo.map((gap, index) => (
              <div
                key={`missing-${gap.parameter || index}`}
                className="p-2.5 bg-paper-raised rounded border border-line text-xs"
              >
                <div className="flex flex-wrap items-center justify-between gap-1 mb-1">
                  <span className="font-medium text-ink">
                    {gap.parameter_label || gap.parameter}
                  </span>
                  <Badge variant="neutral">Information not provided</Badge>
                </div>
                <p className="text-xs text-ink-soft mb-1">{gap.message}</p>
                <div className="text-[11px] text-ink-soft border-t border-line/60 pt-1.5 mt-1.5 font-mono">
                  <span>Requirement: </span>
                  <strong className="text-ink">{gap.requirement_display || gap.required_value}</strong>
                </div>
                {gap.rule_description && (
                  <p className="text-[11px] text-ink-soft/80 mt-1 mb-0 italic">
                    {gap.rule_description}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 3. Documents to review or provide */}
      {missingDocs.length > 0 && (
        <div className="mb-4">
          <h5 className="text-xs font-mono uppercase text-ink-soft flex items-center gap-1.5 mb-2 font-semibold">
            <FileText className="h-3.5 w-3.5" aria-hidden="true" />
            Documents to Review or Provide ({missingDocs.length})
          </h5>
          <div className="space-y-2">
            {missingDocs.map((doc, index) => (
              <div
                key={`doc-${doc.document_type || index}`}
                className="p-2.5 bg-paper-raised rounded border border-line text-xs flex flex-wrap items-start justify-between gap-2"
              >
                <div>
                  <div className="font-medium text-ink mb-0.5">
                    {doc.document_name || doc.document_type}
                  </div>
                  <p className="text-xs text-ink-soft mb-0">{doc.message}</p>
                </div>
                <Badge variant={doc.status === "INVALID" ? "excl" : "neutral"}>
                  {doc.status || "MISSING"}
                </Badge>
              </div>
            ))}
          </div>
        </div>
      )}

      <p className="text-[11px] text-ink-soft border-t border-line pt-2.5 mt-2 mb-0 italic leading-normal">
        Addressing these gaps helps align your profile criteria with scheme rules. It does not guarantee scheme eligibility, approval, or disbursement.
      </p>
    </Card>
  );
}
