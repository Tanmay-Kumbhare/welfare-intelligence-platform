import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  HelpCircle,
  Loader2,
  RefreshCw,
  Sparkles,
  XCircle,
  AlertTriangle,
  ArrowRight,
} from "lucide-react";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import Input from "../components/ui/Input";
import Select from "../components/ui/Select";
import { ErrorState, LoadingState } from "../components/ui/StatusStates";
import {
  authService,
  citizenService,
  eligibilityService,
  formService,
  formSubmissionService,
  recommendationService,
} from "../services/api";
import { clearStoredCitizenId, getStoredCitizenId, setStoredCitizenId } from "../utils/citizenStorage";
import FormSection from "../components/forms/FormSection";
import FormProgress from "../components/forms/FormProgress";
import {
  computeApplicableMap,
  computeProgress,
  storedAnswersByQuestionId,
  percentage,
} from "../components/forms/formLogic";
import { categoryLabel } from "../utils/ruleFormat";

const FORM_CODE = "GENERAL_CITIZEN_PROFILE";
const TODAY = new Date().toISOString().slice(0, 10);

function formatTimestamp(ts) {
  if (!ts) return "Just now";
  try {
    const d = new Date(ts);
    return d.toLocaleDateString("en-IN", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return String(ts);
  }
}

function SchemeMeta({ scheme }) {
  if (!scheme) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-ink-soft">
      {scheme.department_name && <span className="font-medium text-ink">{scheme.department_name}</span>}
      {scheme.scheme_category && <Badge variant="neutral">{categoryLabel(scheme.scheme_category)}</Badge>}
      <Badge variant={scheme.status === "ACTIVE" ? "ok" : "excl"}>{scheme.status}</Badge>
    </div>
  );
}

function SchemeDocuments({ item }) {
  if (!item?.scheme_documents || item.scheme_documents.length === 0) return null;
  const missingCount = item.scheme_documents.filter((d) => d.required && d.status !== "VALID").length;

  return (
    <div className="mt-4 pt-4 border-t border-line">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-soft mb-2.5 flex items-center justify-between">
        <span>Required Documents</span>
        {item.document_status === "COMPLETE" ? (
          <Badge variant="ok">All Documents Verified ✓</Badge>
        ) : (
          <Badge variant="excl">Action Needed ({missingCount} Pending)</Badge>
        )}
      </h4>
      <ul className="space-y-2 mb-3">
        {item.scheme_documents.map((d) => {
          const isValid = d.status === "VALID";
          const isRejected = d.status === "REJECTED";
          return (
            <li key={d.document_type} className="text-xs flex items-center justify-between gap-2 p-1.5 rounded bg-surface/50 border border-line/60">
              <div className="flex items-center gap-2">
                {isValid ? (
                  <CheckCircle2 className="h-3.5 w-3.5 text-ok shrink-0" />
                ) : isRejected ? (
                  <XCircle className="h-3.5 w-3.5 text-excl shrink-0" />
                ) : (
                  <AlertTriangle className="h-3.5 w-3.5 text-amber-500 shrink-0" />
                )}
                <span className="text-ink font-medium">
                  {d.name} {!d.required && <span className="text-ink-soft font-normal text-[11px]">(Optional)</span>}
                </span>
              </div>
              <span className={`text-[11px] font-semibold px-2 py-0.5 rounded border ${
                isValid
                  ? "bg-ok-soft/30 text-ok-ink border-ok-soft"
                  : isRejected
                  ? "bg-excl-soft/30 text-excl-ink border-excl-soft"
                  : "bg-amber-500/15 text-amber-700 border-amber-300"
              }`}>
                {isValid ? "✓ Verified" : isRejected ? "✕ Rejected" : "⚠ Pending"}
              </span>
            </li>
          );
        })}
      </ul>
      <Button to="/documents" variant="secondary" size="sm">
        {missingCount > 0 ? "Upload Missing Documents" : "View Documents"}
      </Button>
    </div>
  );
}

function MatchScoreBadge({ score, label = "Rule Match Score" }) {
  if (score === null || score === undefined) return null;
  const numScore = Math.round(Number(score));

  const isHigh = numScore >= 90;
  const isMed = numScore >= 70 && numScore < 90;

  const barClasses = isHigh ? "bg-ok" : isMed ? "bg-amber-500" : "bg-ink-soft";
  const textClasses = isHigh ? "text-ok-ink font-bold" : isMed ? "text-amber-700 font-bold" : "text-ink font-semibold";

  return (
    <div className="my-2.5 p-2.5 rounded-lg bg-surface-soft/60 border border-line">
      <div className="flex items-center justify-between text-xs font-medium mb-1.5">
        <span className="text-ink font-semibold">{label}</span>
        <span className={textClasses}>{numScore}%</span>
      </div>
      <div className="w-full bg-line/80 h-2 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${barClasses}`}
          style={{ width: `${Math.min(Math.max(numScore, 0), 100)}%` }}
        />
      </div>
    </div>
  );
}



export default function CheckEligibilityPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const modeParam = searchParams.get("mode"); // 'form' to view questionnaire mode

  // ---------------------------------------------------------------------------
  // ALL HOOKS DEFINED UNCONDITIONALLY AT THE TOP OF THE COMPONENT
  // ---------------------------------------------------------------------------

  // Phase states: loading | no-citizen | ready | results | form | form-error
  const [phase, setPhase] = useState("loading");
  const [citizen, setCitizen] = useState(null);
  const [evaluating, setEvaluating] = useState(false);
  const [resultsData, setResultsData] = useState(null);
  const [showNonMatching, setShowNonMatching] = useState(false);

  // Form Questionnaire states
  const [form, setForm] = useState(null);
  const [submission, setSubmission] = useState(null);
  const [answers, setAnswers] = useState(() => new Map());
  const [currentStep, setCurrentStep] = useState(0);
  const [message, setMessage] = useState("");
  const [saveState, setSaveState] = useState("idle");
  const [fieldErrors, setFieldErrors] = useState(() => new Map());
  const [loadKey, setLoadKey] = useState(0);

  const answersRef = useRef(answers);
  answersRef.current = answers;
  const submissionInFlight = useRef(false);

  // 1. Initial Load: Authenticated User, Citizen & Form Definition
  useEffect(() => {
    let cancelled = false;

    const loadData = async () => {
      let resolvedCitizen = null;
      let isAuthenticated = false;

      try {
        const me = await authService.me();
        if (me?.data) {
          isAuthenticated = true;
          const cid = me.data.citizen_id;
          if (cid) {
            const res = await citizenService.get(cid);
            resolvedCitizen = res.data;
          }
        }
      } catch {
        isAuthenticated = false;
      }

      if (cancelled) return;

      if (!isAuthenticated) {
        setPhase("unauthenticated");
        return;
      }

      if (!resolvedCitizen) {
        setPhase("incomplete-profile");
        return;
      }

      let formDef = null;
      try {
        const formRes = await formService.getActive(FORM_CODE);
        formDef = formRes.data;
      } catch (err) {
        console.warn("Form definition load notice:", err);
      }

      if (cancelled) return;

      setCitizen(resolvedCitizen);
      if (formDef) setForm(formDef);

      if (resolvedCitizen.profile_status !== "COMPLETE") {
        setPhase("incomplete-profile");
      } else if (modeParam === "form") {
        setPhase("form");
      } else {
        setPhase("ready");
      }
    };

    loadData().catch(() => {
      if (!cancelled) setPhase("form-error");
    });

    return () => {
      cancelled = true;
    };
  }, [loadKey, modeParam]);

  // 2. Perform Scheme Eligibility Evaluation on user action
  const runEligibilityCheck = useCallback(async () => {
    if (!citizen?.citizen_id || citizen.profile_status !== "COMPLETE") return;
    setEvaluating(true);
    setMessage("");

    try {
      // Step A: Evaluate schemes against bulk facts in PostgreSQL / Redis
      await eligibilityService.evaluate(citizen.citizen_id);

      // Step B: Fetch formatted recommendations & required documents
      const recRes = await recommendationService.getForCitizen(citizen.citizen_id);
      setResultsData(recRes.data);
      setPhase("results");
    } catch (err) {
      console.error("Eligibility check failed:", err);
      const errMsg = err.response?.data?.detail?.message || "Unable to complete eligibility check. Please try again.";
      setMessage(errMsg);
    } finally {
      setEvaluating(false);
    }
  }, [citizen]);

  // 4. Form Evaluation & Submission Helpers for questionnaire mode
  const ensureSubmission = useCallback(async () => {
    if (submissionInFlight.current || !citizen?.citizen_id) return null;
    submissionInFlight.current = true;
    try {
      const response = await formSubmissionService.create(FORM_CODE, {
        citizen_id: citizen.citizen_id,
        answers: [],
      });
      return response.data;
    } finally {
      submissionInFlight.current = false;
    }
  }, [citizen]);

  useEffect(() => {
    if (phase !== "form" || !citizen || !form || submission) return;
    let cancelled = false;

    ensureSubmission().then(async (draft) => {
      if (cancelled || !draft) return;
      const stored = storedAnswersByQuestionId(draft);
      setSubmission(draft);
      setAnswers(stored);
    });

    return () => {
      cancelled = true;
    };
  }, [phase, citizen, form, submission, ensureSubmission]);

  // Derived Form Mappings (Safe with null fallbacks)
  const applicable = useMemo(
    () => (form ? computeApplicableMap(form.sections, answers) : new Map()),
    [form, answers]
  );
  const progress = useMemo(
    () => (form ? computeProgress(form.sections, answers, applicable) : { total: 0, answered: 0, missingRequired: [] }),
    [form, answers, applicable]
  );
  const completion = percentage(progress.answered, progress.total);
  const sectionsCount = form?.sections?.length ?? 0;
  const currentSection = form?.sections?.[currentStep] ?? null;

  // Derived Scheme Results (Safe with null fallbacks)
  const eligibleSchemes = useMemo(() => resultsData?.eligible_schemes || [], [resultsData]);
  const ineligibleSchemes = useMemo(() => resultsData?.ineligible_schemes || [], [resultsData]);

  const answerQuestion = useCallback((question, value) => {
    setAnswers((current) => {
      const next = new Map(current);
      next.set(question.question_id, value);
      return next;
    });
  }, []);

  const goToStep = useCallback(
    (index) => {
      setCurrentStep(Math.min(Math.max(index, 0), Math.max(sectionsCount - 1, 0)));
      window.scrollTo({ top: 0 });
    },
    [sectionsCount]
  );

  const submitFormAndEvaluate = useCallback(async () => {
    if (!citizen?.citizen_id || !submission?.submission_id) return;
    setEvaluating(true);
    try {
      await formSubmissionService.update(submission.submission_id, {
        citizen_id: citizen.citizen_id,
        answers: [...answers.entries()].map(([qid, val]) => ({ question_id: qid, value: val, source: "USER_INPUT" })),
      });
      await formSubmissionService.complete(submission.submission_id, { citizen_id: citizen.citizen_id });
      await formSubmissionService.normalize(submission.submission_id, { citizen_id: citizen.citizen_id });
      await runEligibilityCheck();
    } catch (err) {
      console.error(err);
      setPhase("form");
      setMessage("Failed to submit form answers.");
    } finally {
      setEvaluating(false);
    }
  }, [citizen, submission, answers, runEligibilityCheck]);

  // ---------------------------------------------------------------------------
  // CONDITIONAL VIEW RENDERING AFTER ALL HOOKS
  // ---------------------------------------------------------------------------

  if (phase === "loading") {
    return <LoadingState label="Loading your profile & eligibility..." />;
  }

  if (phase === "form-error") {
    return (
      <ErrorState
        title="Unable to load eligibility service"
        message="The service is currently reconnecting. Please retry."
        onRetry={() => {
          setPhase("loading");
          setLoadKey((k) => k + 1);
        }}
      />
    );
  }

  // 1. Unauthenticated View (Login / Register Gate)
  if (phase === "unauthenticated") {
    return (
      <div className="max-w-xl mx-auto py-12 text-center">
        <Card className="p-8 space-y-4">
          <div className="h-14 w-14 rounded-full bg-brand-soft/30 text-brand flex items-center justify-center mx-auto mb-2">
            <Sparkles className="h-7 w-7" />
          </div>
          <h1 className="text-2xl font-bold text-ink">Check Your Eligibility</h1>
          <p className="text-sm text-ink-soft max-w-md mx-auto leading-relaxed">
            Sign in to securely check which welfare schemes and scholarships you qualify for based on your canonical citizen profile.
          </p>
          <div className="pt-4 flex justify-center">
            <Button to="/login" variant="primary" size="lg" className="px-8">
              Login / Register
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  // 2. Incomplete Profile View (Profile Completeness Gate)
  if (phase === "incomplete-profile" || (citizen && citizen.profile_status !== "COMPLETE")) {
    const missing = citizen?.missing_fields?.length
      ? citizen.missing_fields
      : ["Education Details", "Annual Income", "Social Category", "State / Location"];
    const completionRate = citizen?.profile_completion || 0;

    return (
      <div className="max-w-2xl mx-auto py-8 space-y-6">
        <div>
          <h1 className="text-3xl font-bold text-ink mb-1">Complete Your Profile</h1>
          <p className="text-ink-soft text-sm">
            Add your education, income, category, and location details so we can accurately evaluate scheme eligibility.
          </p>
        </div>

        <Card className="p-6 border-l-4 border-l-amber-500">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-ink">Profile Completion</span>
              <span className="text-xs font-bold px-2.5 py-0.5 rounded bg-amber-500/10 text-amber-700 border border-amber-300">
                {completionRate}%
              </span>
            </div>

            <div className="w-full bg-line/80 h-2.5 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full bg-amber-500 transition-all duration-500"
                style={{ width: `${Math.min(Math.max(completionRate, 0), 100)}%` }}
              />
            </div>

            <div className="bg-surface-soft p-4 rounded-lg border border-line space-y-2">
              <p className="text-xs font-semibold text-ink-soft uppercase tracking-wider">
                Required for Scheme Eligibility:
              </p>
              <ul className="space-y-1.5 text-xs text-ink">
                {missing.map((field, idx) => (
                  <li key={idx} className="flex items-center gap-2">
                    <AlertTriangle className="h-3.5 w-3.5 text-amber-500 shrink-0" />
                    <span>{field}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="pt-2 flex items-center justify-between gap-3">
              <Button to="/profile" variant="primary" size="md">
                Complete My Profile <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            </div>
          </div>
        </Card>
      </div>
    );
  }

  // 2. Questionnaire Form View (if mode=form)
  if (phase === "form" && form && currentSection) {
    return (
      <div className="max-w-3xl mx-auto py-4">
        <div className="flex items-center justify-between mb-4">
          <Button variant="ghost" size="sm" onClick={() => setPhase("ready")}>
            <ChevronLeft className="h-4 w-4 mr-1" /> Back to Profile Summary
          </Button>
          <span className="text-xs text-ink-soft">
            Section {currentStep + 1} of {sectionsCount}
          </span>
        </div>
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-ink mb-1">{form.form_name}</h1>
          <p className="text-xs text-ink-soft">{form.description}</p>
          <div className="mt-4">
            <FormProgress
              sections={form.sections}
              currentStep={currentStep}
              applicable={applicable}
              answers={answers}
              completionPercentage={completion}
            />
          </div>
        </div>
        {message && (
          <div className="mb-4">
            <ErrorState title="Error" message={message} />
          </div>
        )}
        <Card className="p-6">
          <FormSection
            section={currentSection}
            answers={answers}
            applicable={applicable}
            onAnswerChange={answerQuestion}
            fieldErrors={fieldErrors}
            sectionIndex={currentStep}
            totalSections={sectionsCount}
          />
          <div className="flex items-center justify-between mt-6 pt-4 border-t border-line">
            <Button
              type="button"
              variant="ghost"
              onClick={() => goToStep(currentStep - 1)}
              disabled={currentStep === 0}
            >
              <ChevronLeft className="h-4 w-4 mr-1" /> Back
            </Button>
            <div className="flex items-center gap-2">
              {currentStep < sectionsCount - 1 ? (
                <Button onClick={() => goToStep(currentStep + 1)}>
                  Next Section <ChevronRight className="h-4 w-4 ml-1" />
                </Button>
              ) : (
                <Button onClick={submitFormAndEvaluate} disabled={evaluating}>
                  {evaluating ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null} Submit &amp; Evaluate
                </Button>
              )}
            </div>
          </div>
        </Card>
      </div>
    );
  }

  // 3. Standard Clean Check Eligibility View
  return (
    <div className="max-w-3xl mx-auto py-6 space-y-6">
      {/* Title */}
      <div>
        <h1 className="text-3xl font-bold text-ink mb-1">Check Scheme Eligibility</h1>
        <p className="text-ink-soft text-sm">
          Instantly evaluate which government welfare schemes and scholarships match your profile.
        </p>
      </div>

      {/* Citizen Profile Status Summary Card */}
      {citizen && (
        <Card className="p-6 border-l-4 border-l-brand">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="space-y-1.5">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-bold uppercase tracking-wider text-brand">Citizen Profile</span>
                <span className="inline-flex items-center gap-1 text-xs font-semibold text-ok-ink bg-ok-soft/30 px-2 py-0.5 rounded-full border border-ok-soft">
                  <Check className="h-3 w-3 text-ok" /> Profile Complete ✓
                </span>
                <span className="text-xs text-ink-soft bg-surface px-2 py-0.5 rounded border border-line">
                  v{citizen.profile_version || 1}
                </span>
              </div>

              <div className="flex flex-wrap items-baseline gap-2">
                <h2 className="text-xl font-bold text-ink">{citizen.full_name}</h2>
                <span className="text-xs text-ink-soft">
                  {citizen.gender ? `${citizen.gender} · ` : ""}DOB: {citizen.date_of_birth || "N/A"}
                </span>
              </div>

              {/* Profile badges */}
              <div className="flex flex-wrap items-center gap-1.5 pt-1">
                {(citizen.profile_types || ["GENERAL"]).map((type) => (
                  <Badge key={type} variant="brand">
                    {type}
                  </Badge>
                ))}
                {citizen.demographic?.social_category && (
                  <Badge variant="neutral">{citizen.demographic.social_category}</Badge>
                )}
                {citizen.location?.state && (
                  <Badge variant="neutral">{citizen.location.state}</Badge>
                )}
                {citizen.demographic?.education_level && (
                  <Badge variant="neutral">{citizen.demographic.education_level}</Badge>
                )}
                {citizen.financial?.is_bpl_card_holder && <Badge variant="ok">BPL</Badge>}
              </div>

              <p className="text-xs text-ink-soft pt-1">
                Last Updated:{" "}
                <span className="font-medium text-ink">
                  {formatTimestamp(citizen.updated_at || citizen.created_at || citizen.registration_date)}
                </span>
              </p>
            </div>

            <div className="flex flex-col sm:flex-col gap-2 shrink-0">
              <Button
                variant="primary"
                size="lg"
                onClick={runEligibilityCheck}
                disabled={evaluating}
                className="shadow-sm font-semibold"
              >
                {evaluating ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    Checking...
                  </>
                ) : resultsData ? (
                  <>
                    <RefreshCw className="h-4 w-4 mr-2" />
                    Re-check Eligibility
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4 mr-2" />
                    Check My Eligibility
                  </>
                )}
              </Button>

              <Button to="/profile" variant="secondary" size="sm" className="justify-center">
                Review My Profile
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* Evaluating Status State */}
      {evaluating && (
        <Card className="p-8 text-center bg-brand-soft/10 border border-brand/20">
          <Loader2 className="h-8 w-8 animate-spin text-brand mx-auto mb-3" />
          <h3 className="text-lg font-semibold text-ink">Checking your eligibility...</h3>
          <p className="text-xs text-ink-soft max-w-md mx-auto mt-1">
            Evaluating active central and state welfare rules against your canonical profile facts.
          </p>
        </Card>
      )}

      {/* Error Message */}
      {message && (
        <div>
          <ErrorState title="Evaluation Error" message={message} onRetry={runEligibilityCheck} />
        </div>
      )}

      {/* Results Presentation */}
      {resultsData && !evaluating && (
        <div className="space-y-6 pt-2">
          {/* Section: Eligible Schemes */}
          {eligibleSchemes.length > 0 ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between pb-2 border-b border-line">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="h-5 w-5 text-ok" />
                  <h2 className="text-xl font-bold text-ink">
                    Eligible for You <span className="text-sm font-normal text-ink-soft">({eligibleSchemes.length} matching)</span>
                  </h2>
                </div>
              </div>

              <div className="space-y-4">
                {eligibleSchemes.map((item, index) => (
                  <Card key={item.scheme.scheme_id} eligible className="p-5">
                    <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-xs font-bold text-brand bg-brand-soft/20 px-2 py-0.5 rounded border border-brand/20">
                            #{index + 1}
                          </span>
                          <h3 className="text-lg font-bold text-ink">{item.scheme.scheme_name}</h3>
                        </div>
                        <SchemeMeta scheme={item.scheme} />
                      </div>
                      <Button to={`/schemes/${item.scheme.scheme_id}`} variant="primary" size="sm">
                        View Scheme <ArrowRight className="h-3.5 w-3.5 ml-1" />
                      </Button>
                    </div>

                    {item.scheme.benefit_description && (
                      <p className="text-xs text-ink mt-2.5 mb-0 leading-relaxed">
                        {item.scheme.benefit_description}
                      </p>
                    )}

                    {/* Eligibility Match Score */}
                    <MatchScoreBadge score={item.match_score} />

                    {/* Required Documents Section */}
                    <SchemeDocuments item={item} />
                  </Card>
                ))}
              </div>
            </div>
          ) : (
            /* Zero Matches State */
            <Card className="p-6 border border-line bg-surface">
              <div className="text-center py-4 max-w-md mx-auto">
                <div className="h-12 w-12 rounded-full bg-surface-soft border border-line flex items-center justify-center mx-auto mb-3 text-ink-soft">
                  <HelpCircle className="h-6 w-6" />
                </div>
                <h3 className="text-lg font-bold text-ink mb-1">No matching schemes found yet</h3>
                <p className="text-xs text-ink-soft mb-4">
                  We checked available schemes against your profile. You may not meet specific criteria for currently published schemes.
                </p>

                <div className="text-left bg-surface-soft p-3.5 rounded-lg border border-line text-xs text-ink space-y-1.5 mb-4">
                  <p className="font-semibold text-ink-soft uppercase tracking-wider text-[11px]">Possible reasons:</p>
                  <p>• Missing profile information (e.g. academic marks, farmer type)</p>
                  <p>• Required education level or branch criteria</p>
                  <p>• Income threshold limits</p>
                  <p>• Social category or location restrictions</p>
                </div>

                <Button to="/profile" variant="primary">
                  Review &amp; Update Profile
                </Button>
              </div>
            </Card>
          )}

          {/* Section: Non-Matching Schemes (Collapsed by Default) */}
          {ineligibleSchemes.length > 0 && (
            <div className="pt-2">
              <button
                type="button"
                onClick={() => setShowNonMatching((prev) => !prev)}
                className="w-full flex items-center justify-between p-3.5 bg-surface-soft hover:bg-line/40 rounded-lg border border-line text-xs font-semibold text-ink-soft hover:text-ink transition-colors"
              >
                <span>Why other schemes didn't match ({ineligibleSchemes.length})</span>
                {showNonMatching ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </button>

              {showNonMatching && (
                <div className="mt-3 space-y-3">
                  {ineligibleSchemes.map((item) => {
                    const numScore =
                      item.match_score !== null && item.match_score !== undefined
                        ? Math.round(Number(item.match_score))
                        : null;
                    return (
                      <Card key={item.scheme.scheme_id} className="p-4 bg-surface/60">
                        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2">
                          <div>
                            <div className="flex items-center gap-2 mb-0.5">
                              <h4 className="text-sm font-semibold text-ink">{item.scheme.scheme_name}</h4>
                              {numScore !== null && (
                                <span className="text-[11px] font-bold px-2 py-0.5 rounded bg-surface-soft text-ink-soft border border-line">
                                  {numScore}% Match
                                </span>
                              )}
                            </div>
                            <span className="text-xs text-ink-soft">{item.scheme.department_name}</span>
                          </div>
                          <Button to={`/schemes/${item.scheme.scheme_id}`} variant="ghost" size="sm">
                            View Details
                          </Button>
                        </div>
                        <p className="text-xs text-excl-ink font-medium mt-2 mb-0">
                          Reason: {item.reason || "Eligibility conditions were not satisfied."}
                        </p>
                      </Card>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
