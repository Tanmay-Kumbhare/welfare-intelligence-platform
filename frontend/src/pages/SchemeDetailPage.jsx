import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, ArrowUpRight, FileText } from "lucide-react";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/StatusStates";
import { schemeService } from "../services/api";
import {
  categoryLabel,
  describeRequiredValue,
  describeRule,
  documentLabel,
  parameterLabel,
} from "../utils/ruleFormat";

function loadScheme(id, setScheme, setStatus) {
  schemeService
    .get(id)
    .then((response) => {
      setScheme(response.data);
      setStatus("ready");
    })
    .catch((error) => {
      setScheme(null);
      setStatus([404, 422].includes(error.response?.status) ? "not-found" : "error");
    });
}

export default function SchemeDetailPage() {
  const { id } = useParams();
  const [scheme, setScheme] = useState(null);
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    loadScheme(id, setScheme, setStatus);
  }, [id]);

  if (status === "loading" || (scheme && scheme.scheme_id !== id)) {
    return <LoadingState label="Loading scheme details..." />;
  }
  if (status === "not-found") {
    return <EmptyState title="Scheme not found" message="This scheme is not available in the catalogue." action={<Button to="/schemes" variant="secondary" size="sm">Back to schemes</Button>} />;
  }
  if (status === "error") {
    return (
      <ErrorState
        title="Unable to load scheme"
        message="We could not load this scheme right now. Please try again."
        onRetry={() => {
          setStatus("loading");
          loadScheme(id, setScheme, setStatus);
        }}
      />
    );
  }
  if (!scheme) return <EmptyState title="Scheme not found" message="This scheme is not available in the catalogue." />;

  return (
    <div>
      <Link to="/schemes" className="inline-flex items-center gap-2 text-sm mb-7">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Back to schemes
      </Link>

      <header className="border-b border-line pb-7 mb-8">
        <div className="flex flex-wrap items-center gap-2 mb-4">
          <Badge variant="neutral">{categoryLabel(scheme.scheme_category)}</Badge>
          <Badge variant={scheme.status === "ACTIVE" ? "ok" : "excl"}>{scheme.status}</Badge>
        </div>
        <h1 className="text-[32px] leading-tight mb-3">{scheme.scheme_name}</h1>
        {scheme.department_name && <p className="mb-0">{scheme.department_name}</p>}
      </header>

      <div className="grid lg:grid-cols-[minmax(0,1.5fr)_minmax(260px,1fr)] gap-8">
        <div className="space-y-8">
          <section>
            <h2 className="text-2xl mb-3">Overview</h2>
            {scheme.benefit_description && <p className="text-base mb-3">{scheme.benefit_description}</p>}
            {scheme.description && <p className="mb-0">{scheme.description}</p>}
          </section>

          <section>
            <h2 className="text-2xl mb-3">Eligibility rules</h2>
            <p className="text-sm mb-5">
              Rule groups are combined with <code className="font-mono text-xs">{scheme.group_combining_operator}</code>.
            </p>
            <div className="space-y-4">
              {scheme.rule_groups.length === 0 ? (
                <EmptyState title="No eligibility rules listed" />
              ) : scheme.rule_groups.map((group) => (
                <Card key={group.group_id}>
                  <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line pb-3 mb-4">
                    <h3 className="text-base mb-0">{group.group_name}</h3>
                    <span className="font-mono text-xs text-ink-soft">Rules: {group.intra_group_operator}</span>
                  </div>
                  <ul className="space-y-4">
                    {group.rules.map((rule) => (
                      <li key={rule.rule_id}>
                        <p className="text-sm text-ink mb-1">{describeRule(rule)}</p>
                        <p className="font-mono text-xs text-ink-soft mb-0 wrap-break-word">
                          {parameterLabel(rule.parameter_name)} {rule.operator} {rule.required_value}
                          {rule.operator !== "IN" && ` (${describeRequiredValue(rule)})`}
                        </p>
                      </li>
                    ))}
                  </ul>
                </Card>
              ))}
            </div>
          </section>
        </div>

        <aside className="space-y-6">
          <section>
            <h2 className="text-xl mb-3">Required documents</h2>
            {scheme.documents.length === 0 ? (
              <EmptyState title="No documents listed" />
            ) : (
              <Card>
                <ul className="space-y-4">
                  {scheme.documents.map((document) => (
                    <li key={document.document_id} className="flex gap-3">
                      <FileText className="h-4 w-4 mt-1 text-accent-ink shrink-0" aria-hidden="true" />
                      <div>
                        <p className="text-sm text-ink mb-1">{documentLabel(document.document_type)}</p>
                        <Badge variant={document.mandatory_flag ? "excl" : "neutral"}>
                          {document.mandatory_flag ? "Mandatory" : "Additional"}
                        </Badge>
                        {document.description && <p className="text-xs mt-2 mb-0">{document.description}</p>}
                      </div>
                    </li>
                  ))}
                </ul>
              </Card>
            )}
          </section>

          <section>
            <h2 className="text-xl mb-3">Official information</h2>
            <Card className="flex flex-col items-start gap-3">
              {scheme.official_source_url && (
                <Button href={scheme.official_source_url} target="_blank" rel="noreferrer" variant="secondary" size="sm">
                  Official source <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
                </Button>
              )}
              {scheme.application_url && (
                <Button href={scheme.application_url} target="_blank" rel="noreferrer" variant="primary" size="sm">
                  Application portal <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
                </Button>
              )}
              {scheme.last_verified_at && (
                <p className="text-xs mb-0">Last verified: {scheme.last_verified_at}</p>
              )}
              {!scheme.official_source_url && !scheme.application_url && !scheme.last_verified_at && (
                <p className="text-sm mb-0">No official links or verification date are listed.</p>
              )}
            </Card>
          </section>
        </aside>
      </div>
    </div>
  );
}
