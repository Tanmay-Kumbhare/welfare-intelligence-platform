import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { User, FileText, CheckCircle, Clock, AlertCircle, Search, Settings } from "lucide-react";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import { LoadingState, ErrorState } from "../components/ui/StatusStates";
import { authService, citizenService, recommendationService } from "../services/api";
import api from "../services/api";

export default function DashboardPage() {
  const [data, setData] = useState({
    citizen: null,
    recommendations: null,
    requirements: null
  });
  const [status, setStatus] = useState("loading"); // loading | ready | error

  useEffect(() => {
    let cancelled = false;

    const loadDashboard = async () => {
      try {
        const me = await authService.me();
        const citizenId = me.data?.citizen_id;
        
        if (!citizenId) {
          if (!cancelled) setStatus("no-citizen");
          return;
        }

        const [citRes, recRes, reqRes] = await Promise.allSettled([
          citizenService.get(citizenId),
          recommendationService.getForCitizen(citizenId),
          api.get(`/documents/requirements/${citizenId}`)
        ]);

        if (cancelled) return;

        const citizen = citRes.status === "fulfilled" ? citRes.value.data : null;
        // 404 is fine for recommendations if they haven't evaluated yet
        const recommendations = recRes.status === "fulfilled" ? recRes.value.data : null;
        const requirements = reqRes.status === "fulfilled" ? reqRes.value.data : null;

        if (!citizen) {
          setStatus("no-citizen");
          return;
        }

        setData({ citizen, recommendations, requirements });
        setStatus("ready");
      } catch (err) {
        if (!cancelled) setStatus("error");
      }
    };

    loadDashboard();

    return () => {
      cancelled = true;
    };
  }, []);

  if (status === "loading") return <LoadingState label="Loading your dashboard..." />;
  if (status === "error") return <ErrorState title="Unable to load dashboard" message="Please try again later." />;
  if (status === "no-citizen") {
    return (
      <div className="max-w-[800px] py-8">
        <h1 className="text-3xl mb-4">Welcome to VidyaSetu</h1>
        <Card>
          <h2 className="text-xl mb-2">Complete your profile</h2>
          <p className="text-sm text-ink-soft mb-4">You need to create your citizen profile before you can see your dashboard and welfare recommendations.</p>
          <Button to="/check-eligibility" variant="primary">Start Profile</Button>
        </Card>
      </div>
    );
  }

  const { citizen, recommendations, requirements } = data;
  
  const isProfileComplete = citizen?.profile_types && citizen.profile_types.length > 0;
  
  // Doc stats
  let reqDocs = 0, validDocs = 0, invalidDocs = 0, reviewDocs = 0, notUploaded = 0;
  let missingRequiredDocs = [];
  
  if (requirements) {
    Object.values(requirements).forEach(reqs => {
      reqs.forEach(req => {
        if (req.required) {
          reqDocs++;
          if (!req.document) {
            notUploaded++;
            missingRequiredDocs.push(req.name);
          } else if (req.document.validation_status === "VALID") {
            validDocs++;
          } else if (req.document.validation_status === "INVALID") {
            invalidDocs++;
            missingRequiredDocs.push(req.name);
          } else if (req.document.validation_status === "REVIEW_REQUIRED") {
            reviewDocs++;
            missingRequiredDocs.push(req.name);
          } else {
            notUploaded++;
            missingRequiredDocs.push(req.name);
          }
        }
      });
    });
  }
  missingRequiredDocs = [...new Set(missingRequiredDocs)];

  return (
    <div className="max-w-[1000px] mx-auto py-4">
      <header className="mb-8">
        <h1 className="text-3xl font-semibold mb-2">Welcome back, {citizen.full_name || "Citizen"}</h1>
        <p className="text-ink-soft">Here is a summary of your current welfare status and pending actions.</p>
      </header>

      <div className="grid md:grid-cols-2 gap-6 mb-6">
        {/* Profile Status */}
        <Card className="flex flex-col">
          <div className="flex items-center gap-3 mb-4">
            <User className="h-6 w-6 text-accent-ink" />
            <h2 className="text-xl font-medium m-0">Profile Status</h2>
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-3">
              {isProfileComplete ? <CheckCircle className="h-5 w-5 text-ok" /> : <AlertCircle className="h-5 w-5 text-excl" />}
              <span className="font-medium text-lg">{isProfileComplete ? "Profile Complete" : "Profile Incomplete"}</span>
            </div>
            {citizen.profile_types && citizen.profile_types.length > 0 && (
              <div className="mb-4">
                <p className="text-xs text-ink-soft mb-2 font-mono uppercase tracking-wider">Your Domains</p>
                <div className="flex flex-wrap gap-2">
                  {citizen.profile_types.map(pt => (
                    <Badge key={pt} variant="neutral">{pt.replace(/_/g, " ")}</Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
          <div className="mt-4 pt-4 border-t border-line flex gap-3">
            <Button to="/profile" variant="secondary" size="sm">View / Edit Profile</Button>
            <Button to="/check-eligibility" variant="ghost" size="sm">Edit Domains</Button>
          </div>
        </Card>

        {/* Eligibility Summary */}
        <Card className="flex flex-col">
          <div className="flex items-center gap-3 mb-4">
            <Search className="h-6 w-6 text-accent-ink" />
            <h2 className="text-xl font-medium m-0">Eligibility Summary</h2>
          </div>
          <div className="flex-1">
            {!recommendations ? (
              <p className="text-ink-soft text-sm">Eligibility has not been checked yet. Update your profile to generate recommendations.</p>
            ) : (
              <div className="flex gap-8 items-center h-full">
                <div>
                  <p className="text-4xl font-semibold text-ok-ink mb-1">{recommendations.eligible_count}</p>
                  <p className="text-sm text-ink-soft">Eligible Schemes</p>
                </div>
                <div className="h-12 w-px bg-line" />
                <div>
                  <p className="text-4xl font-semibold text-excl-ink mb-1">{recommendations.ineligible_count}</p>
                  <p className="text-sm text-ink-soft">Not Eligible</p>
                </div>
              </div>
            )}
          </div>
          <div className="mt-4 pt-4 border-t border-line">
            <Button to={recommendations ? `/results/${citizen.citizen_id}` : "/check-eligibility"} variant={recommendations ? "secondary" : "primary"} size="sm">
              {recommendations ? "View All Results" : "Check Eligibility"}
            </Button>
          </div>
        </Card>

        {/* Document Status */}
        <Card className="flex flex-col md:col-span-2">
          <div className="flex items-center gap-3 mb-4">
            <FileText className="h-6 w-6 text-accent-ink" />
            <h2 className="text-xl font-medium m-0">Document Status</h2>
          </div>
          
          {!requirements ? (
            <p className="text-ink-soft text-sm flex-1">No documents uploaded yet.</p>
          ) : (
            <div className="flex-1 grid md:grid-cols-2 gap-6">
              <div>
                <p className="text-sm font-medium mb-3">Overall Completion</p>
                <div className="flex items-center gap-4 text-sm mb-2">
                  <span className="w-40 flex items-center gap-2"><CheckCircle className="h-4 w-4 text-ok" /> Valid</span>
                  <span className="font-semibold">{validDocs}</span>
                </div>
                <div className="flex items-center gap-4 text-sm mb-2">
                  <span className="w-40 flex items-center gap-2"><XCircle className="h-4 w-4 text-excl" /> Invalid</span>
                  <span className="font-semibold">{invalidDocs}</span>
                </div>
                <div className="flex items-center gap-4 text-sm mb-2">
                  <span className="w-40 flex items-center gap-2"><Clock className="h-4 w-4 text-accent-ink" /> Review Required</span>
                  <span className="font-semibold">{reviewDocs}</span>
                </div>
                <div className="flex items-center gap-4 text-sm mb-2">
                  <span className="w-40 flex items-center gap-2"><span className="h-4 w-4 rounded-full border border-ink-soft" /> Not Uploaded</span>
                  <span className="font-semibold">{notUploaded}</span>
                </div>
              </div>
              
              <div className="bg-surface rounded p-4 border border-line">
                <p className="text-sm font-medium mb-3 flex items-center gap-2">
                  {missingRequiredDocs.length === 0 ? <CheckCircle className="h-4 w-4 text-ok" /> : <AlertCircle className="h-4 w-4 text-excl" />}
                  {missingRequiredDocs.length === 0 ? "All required documents are complete." : "Documents needing attention:"}
                </p>
                {missingRequiredDocs.length > 0 && (
                  <ul className="list-disc pl-5 text-sm text-excl-ink space-y-1">
                    {missingRequiredDocs.map(name => (
                      <li key={name}>{name}</li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
          
          <div className="mt-4 pt-4 border-t border-line">
            <Button to="/documents" variant="secondary" size="sm">Manage Documents</Button>
          </div>
        </Card>

        {/* Recommended Schemes Preview */}
        <Card className="flex flex-col md:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-medium m-0">Recommended Schemes Preview</h2>
            {recommendations && recommendations.eligible_count > 0 && (
              <Button to={`/results/${citizen.citizen_id}`} variant="ghost" size="sm">View All Schemes →</Button>
            )}
          </div>
          <div className="flex-1">
            {!recommendations || recommendations.eligible_count === 0 ? (
              <p className="text-ink-soft text-sm">No eligible schemes found based on the current profile.</p>
            ) : (
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {recommendations.eligible_schemes.slice(0, 3).map(item => (
                  <div key={item.scheme.scheme_id} className="border border-line rounded p-4 flex flex-col">
                    <h3 className="font-medium text-base mb-2 line-clamp-1" title={item.scheme.scheme_name}>{item.scheme.scheme_name}</h3>
                    <div className="flex items-center gap-2 text-sm text-ok-ink mb-2">
                      <CheckCircle className="h-4 w-4" /> Eligible
                    </div>
                    <div className="mt-auto pt-3 border-t border-line text-sm text-ink-soft">
                      {item.document_status === "COMPLETE" ? (
                        <span className="text-ok-ink flex items-center gap-1"><CheckCircle className="h-3 w-3" /> Documents Complete</span>
                      ) : (
                        <span className="text-excl-ink flex items-center gap-1"><AlertCircle className="h-3 w-3" /> Documents Pending</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Card>

      </div>
    </div>
  );
}
