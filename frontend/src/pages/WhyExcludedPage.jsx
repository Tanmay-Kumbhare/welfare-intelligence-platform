import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/StatusStates";
import RuleEvaluationDetails from "../components/eligibility/RuleEvaluationDetails";
import { recommendationService } from "../services/api";

export default function WhyExcludedPage() {
  const { citizenId, schemeId } = useParams();
  const [item, setItem] = useState(null);
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    if (!citizenId || !schemeId) return;

    recommendationService.getForCitizen(citizenId)
      .then((response) => {
        const recommendations = response.data;
        if (!recommendations || !Array.isArray(recommendations.ineligible_schemes)) {
          throw new Error("Malformed recommendations response");
        }

        const found = recommendations.ineligible_schemes.find((candidate) => candidate.scheme.scheme_id === schemeId);
        if (!found) {
          setStatus("not-found");
          return;
        }

        setItem(found);
        setStatus("ready");
      })
      .catch((error) => {
        if (error?.response?.status === 404) {
          setStatus("not-found");
          return;
        }
        setStatus("error");
      });
  }, [citizenId, schemeId]);

  if (!citizenId || !schemeId) return <ErrorState title="Missing result information" message="A citizen ID and scheme ID are required to explain an exclusion." />;
  if (status === "loading") return <LoadingState label="Loading eligibility explanation..." />;
  if (status === "not-found") return <ErrorState title="Scheme not found in results" message="This scheme is not present in the citizen’s ineligible recommendation list." />;
  if (status === "error") return <ErrorState title="Unable to load exclusion details" message="We couldn't load the backend eligibility explanation for this scheme." />;
  if (!item) return <EmptyState title="No exclusion details available" />;

  return <div><Link to={`/results/${citizenId}`} className="inline-flex items-center gap-2 text-sm mb-7"><ArrowLeft className="h-4 w-4" aria-hidden="true" /> Back to results</Link><header className="border-b border-line pb-7 mb-8"><p className="font-mono text-xs text-accent-ink mb-2">V1 ELIGIBILITY EXPLANATION</p><h1 className="text-[32px] leading-tight mb-3">Why excluded?</h1><p className="max-w-[68ch] mb-0">This explains eligibility-rule exclusion only. It does not diagnose application status or document discrepancies.</p></header><Card className="mb-7"><h2 className="text-xl mb-2">{item.scheme.scheme_name}</h2>{item.scheme.department_name && <p className="text-sm mb-2">{item.scheme.department_name}</p>}{item.scheme.scheme_category && <p className="text-sm mb-2">{item.scheme.scheme_category}</p>}<p className="text-sm text-excl-ink mb-0">You are not currently eligible because this eligibility condition was not satisfied.</p></Card>{item.reason && <p className="text-sm mb-5">{item.reason}</p>}{item.evaluation_details ? <RuleEvaluationDetails details={item.evaluation_details} failedOnly /> : <EmptyState title="No rule details available" message="The backend returned no evaluation details for this assessment." />}<div className="flex flex-wrap gap-3 border-t border-line pt-6 mt-8"><Button to={`/schemes/${schemeId}`} variant="secondary">View scheme</Button><Button to={`/results/${citizenId}`} variant="ghost">Back to results</Button></div></div>;
}
