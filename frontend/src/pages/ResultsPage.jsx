import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { CheckCircle, XCircle } from "lucide-react";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/StatusStates";
import RuleEvaluationDetails from "../components/eligibility/RuleEvaluationDetails";
import { citizenService, recommendationService } from "../services/api";
import { categoryLabel } from "../utils/ruleFormat";

function validRecommendations(value) {
  return value && Array.isArray(value.eligible_schemes) && Array.isArray(value.ineligible_schemes);
}

function countFailedRules(details) {
  if (!details || !Array.isArray(details.groups)) return 0;

  return details.groups.reduce((count, group) => {
    const failed = Array.isArray(group.rules) ? group.rules.filter((rule) => rule && rule.passed === false).length : 0;
    return count + failed;
  }, 0);
}

function SchemeMeta({ scheme }) {
  return <div className="flex flex-wrap items-center gap-2 text-xs text-ink-soft">{scheme.department_name && <span>{scheme.department_name}</span>}{scheme.scheme_category && <Badge variant="neutral">{categoryLabel(scheme.scheme_category)}</Badge>}<Badge variant={scheme.status === "ACTIVE" ? "ok" : "excl"}>{scheme.status}</Badge></div>;
}

export default function ResultsPage() {
  const { citizenId } = useParams();
  const [data, setData] = useState(null);
  const [citizen, setCitizen] = useState(null);
  const [status, setStatus] = useState("loading");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!citizenId) return;

    recommendationService.getForCitizen(citizenId)
      .then((response) => {
        if (!validRecommendations(response.data)) {
          throw new Error("Malformed recommendations response");
        }
        setData(response.data);
        setStatus("ready");
      })
      .catch((error) => {
        const apiStatus = error?.response?.status;
        if (apiStatus === 404) {
          setStatus("not-found");
        } else {
          setStatus("error");
        }
      });

    citizenService.get(citizenId)
      .then((response) => setCitizen(response.data))
      .catch(() => setCitizen(null));
  }, [citizenId, reloadKey]);

  if (!citizenId) return <ErrorState title="Missing citizen ID" message="We need a citizen profile ID to load eligibility results." />;
  if (status === "loading") return <LoadingState label="Loading eligibility results..." />;
  if (status === "not-found") return <ErrorState title="Citizen not found" message="No citizen profile exists for this evaluation result." onRetry={() => setReloadKey((value) => value + 1)} />;
  if (status === "error") return <ErrorState title="Unable to load your eligibility results." message="The backend recommendation service could not be loaded. Please try again." onRetry={() => setReloadKey((value) => value + 1)} />;
  if (!data) return <EmptyState title="No evaluated schemes currently match..." message="The backend returned no eligibility results for this citizen." />;

  const eligible = data.eligible_schemes || [];
  const ineligible = data.ineligible_schemes || [];
  const total = eligible.length + ineligible.length;

  return <div>
    <header className="border-b border-line pb-7 mb-8"><h1 className="text-[32px] leading-tight mb-3">Your eligibility results</h1><p className="max-w-[68ch] mb-3">These results are based on the eligibility rules currently stored for each evaluated scheme.</p>{citizen && <p className="text-sm mb-0">Results for <strong className="text-ink">{citizen.full_name}</strong> · {citizen.citizen_type}</p>}</header>
    <Card className="mb-9"><div className="flex flex-wrap items-center gap-x-8 gap-y-3"><div><p className="font-mono text-xs text-ink-soft mb-1">EVALUATED</p><p className="text-2xl text-ink mb-0">{total} schemes</p></div><div><p className="font-mono text-xs text-ink-soft mb-1">ELIGIBLE</p><p className="text-2xl text-ok-ink mb-0">{eligible.length}</p></div><div><p className="font-mono text-xs text-ink-soft mb-1">NOT ELIGIBLE</p><p className="text-2xl text-excl-ink mb-0">{ineligible.length}</p></div></div></Card>

    <section className="mb-10" aria-labelledby="eligible-heading">
      <div className="flex items-center gap-2 border-b border-line pb-2.5 mb-4.5"><CheckCircle className="h-5 w-5 text-ok" aria-hidden="true" /><h2 id="eligible-heading" className="text-2xl mb-0">Eligible schemes <span className="font-sans text-sm font-normal text-ink-soft">({eligible.length})</span></h2></div>
      {eligible.length === 0 ? <EmptyState title="No evaluated schemes currently match..." message="No evaluated schemes currently match your information." /> : <div className="space-y-4">{eligible.map((item) => <Card key={item.scheme.scheme_id} eligible><div className="flex flex-wrap items-start justify-between gap-4"><div><h3 className="text-xl mb-2">{item.scheme.scheme_name}</h3><SchemeMeta scheme={item.scheme} /></div><Button to={`/schemes/${item.scheme.scheme_id}`} variant="secondary" size="sm">View scheme</Button></div><p className="text-sm mt-4 mb-0">Your information meets the stored eligibility requirements.</p>{(item.scheme.benefit_description || item.scheme.description) && <p className="text-sm mt-2 mb-0">{item.scheme.benefit_description || item.scheme.description}</p>}</Card>)}</div>}
    </section>

    <section className="mb-10" aria-labelledby="excluded-heading">
      <div className="flex items-center gap-2 border-b border-line pb-2.5 mb-4.5"><XCircle className="h-5 w-5 text-excl" aria-hidden="true" /><h2 id="excluded-heading" className="text-2xl mb-0">Not currently eligible <span className="font-sans text-sm font-normal text-ink-soft">({ineligible.length})</span></h2></div>
      {ineligible.length === 0 ? <EmptyState title="All evaluated schemes match your current information." /> : <div className="space-y-4">{ineligible.map((item) => <Card key={item.scheme.scheme_id}><div className="flex flex-wrap items-start justify-between gap-4"><div><h3 className="text-xl mb-2">{item.scheme.scheme_name}</h3><SchemeMeta scheme={item.scheme} /></div><div className="flex flex-wrap gap-2"><Button to={`/why-excluded/${citizenId}/${item.scheme.scheme_id}`} variant="secondary" size="sm">Why excluded?</Button><Button to={`/schemes/${item.scheme.scheme_id}`} variant="ghost" size="sm">View scheme</Button></div></div><p className="text-sm text-excl-ink mt-4 mb-2">You are not currently eligible because this eligibility condition was not satisfied.</p>{item.reason && <p className="text-sm mb-3">{item.reason}</p>}<div className="flex flex-wrap items-center gap-2 text-xs text-ink-soft border-t border-line pt-3 mt-3"><span>Failed rule count: {countFailedRules(item.evaluation_details)}</span></div><details className="border-t border-line pt-3"><summary className="cursor-pointer text-sm font-medium text-ink">Show failed eligibility rules</summary><div className="mt-3"><RuleEvaluationDetails details={item.evaluation_details} failedOnly /></div></details></Card>)}</div>}
    </section>

    <div className="flex flex-wrap gap-3 border-t border-line pt-6"><Button to="/check-eligibility" variant="primary">Check eligibility again</Button><Button to="/profile" variant="secondary">My profile</Button>{citizen?.location?.state && <span className="text-xs text-ink-soft self-center">Location: {citizen.location.state}</span>}</div>
  </div>;
}