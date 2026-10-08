import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import {
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  FileText,
  HelpCircle,
  Info,
  Loader2,
  RefreshCw,
  Sparkles,
  UserCheck,
  XCircle,
  AlertTriangle,
  ArrowRight,
} from "lucide-react";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import Input from "../components/ui/Input";
import Select from "../components/ui/Select";
import { ErrorState, LoadingState, EmptyState } from "../components/ui/StatusStates";
import RuleEvaluationDetails from "../components/eligibility/RuleEvaluationDetails";
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
      <ul className="space-y-1.5 mb-3">
        {item.scheme_documents.map((d) => (
          <li key={d.document_type} className="text-xs flex items-center gap-2">
            {d.status === "VALID" ? (
              <CheckCircle2 className="h-3.5 w-3.5 text-ok shrink-0" />
            ) : (
              <XCircle className="h-3.5 w-3.5 text-excl shrink-0" />
            )}
            <span className={d.status === "VALID" ? "text-ink" : "text-excl-ink font-medium"}>
              {d.name} {!d.required && <span className="text-ink-soft font-normal">(Optional)</span>}
            </span>
          </li>
        ))}
      </ul>
      <Button to="/documents" variant="secondary" size="sm">
        {missingCount > 0 ? "Upload Missing Documents" : "View Documents"}
      </Button>
    </div>
  );
}

function SatisfiedRulesList({ details }) {
  if (!details || !Array.isArray(details.groups)) return null;

  const passedRules = [];
  details.groups.forEach((group) => {
    if (Array.isArray(group.rules)) {
      group.rules.forEach((r) => {
        if (r && r.passed) {
          passedRules.push(r.description || `${r.parameter.replace(/_/g, " ")} requirement satisfied`);
        }
      });
    }
  });

  if (passedRules.length === 0) return null;

  return (
    <div className="mt-3.5 pt-3 border-t border-line/60">
      <p className="text-xs font-semibold text-ink-soft mb-2 uppercase tracking-wider">Satisfied Criteria:</p>
      <ul className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 text-xs text-ink">
        {passedRules.map((desc, idx) => (
          <li key={idx} className="flex items-start gap-1.5">
            <Check className="h-3.5 w-3.5 text-ok shrink-0 mt-0.5" />
            <span>{desc}</span>
          </li>
        ))}
      </ul>
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

  // Guest registration form state
  const [regForm, setRegForm] = useState({ full_name: "", date_of_birth: "", gender: "" });
  const [regError, setRegError] = useState("");

  const answersRef = useRef(answers);
  answersRef.current = answers;
  const submissionInFlight = useRef(false);

  // 1. Initial Load: Authenticated Citizen & Form Definition
  useEffect(() => {
    let cancelled = false;

    const loadData = async () => {
      let resolvedCitizen = null;
      try {
        const me = await authService.me();
        const cid = me.data?.citizen_id;
        if (cid) {
          const res = await citizenService.get(cid);
          resolvedCitizen = res.data;
        }
      } catch {
        // Not authenticated, fallback to local storage
      }

      if (!resolvedCitizen) {
        const stored = getStoredCitizenId();
        if (stored) {
          try {
            const res = await citizenService.get(stored);
            resolvedCitizen = res.data;
          } catch {
            clearStoredCitizenId();
          }
        }
      }

      let formDef = null;
      try {
        const formRes = await formService.getActive(FORM_CODE);
        formDef = formRes.data;
      } catch (err) {
        console.warn("Form definition load notice:", err);
      }

      if (cancelled) return;

      if (resolvedCitizen) {
        setCitizen(resolvedCitizen);
        if (formDef) setForm(formDef);
        if (modeParam === "form") {
          setPhase("form");
        } else {
          setPhase("ready");
        }
      } else {
        if (formDef) setForm(formDef);
        setPhase("no-citizen");
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
    if (!citizen?.citizen_id) return;
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
      setMessage("Unable to complete eligibility check. Please try again.");
    } finally {
      setEvaluating(false);
    }
  }, [citizen]);

  // 3. Guest Registration Handler
  const registerGuest = useCallback(
    async (event) => {
      event.preventDefault();
      setRegError("");
      if (regForm.full_name.trim().length < 2 || !regForm.date_of_birth || regForm.date_of_birth >= TODAY) {
        setRegError("Please enter your full name and a valid date of birth in the past.");
        return;
      }
      try {
        const response = await citizenService.register({
          full_name: regForm.full_name.trim(),
          date_of_birth: regForm.date_of_birth,
          gender: regForm.gender || null,
          citizen_type: "GENERAL",
          demographic: { disability_status: "NONE" },
          financial: { is_bpl_card_holder: false, is_income_tax_payer: false },
          location: {},
        });
        const cid = response.data.citizen_id;
        setStoredCitizenId(cid);
        setCitizen(response.data);
        setPhase("ready");
      } catch {
        setRegError("Unable to create profile right now. Please try again.");
      }
    },
    [regForm]
  );

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

  // 1. Guest View (Profile registration before checking)
  if (phase === "no-citizen") {
    return (
      <div className="max-w-2xl mx-auto py-6">
        <div className="mb-6">
          <div className="inline-flex items-center gap-2 px-3 py-1 bg-brand-soft/30 text-brand rounded-full text-xs font-semibold mb-3">
            <Sparkles className="h-3.5 w-3.5" /> VidyaSetu Eligibility Portal
          </div>
          <h1 className="text-3xl font-bold text-ink mb-2">Check Your Welfare Eligibility</h1>
          <p className="text-ink-soft text-sm">
            Enter your basic details below to instantly evaluate your eligibility across all active government schemes.
          </p>
        </div>
        <Card className="p-6">
          <form onSubmit={registerGuest} noValidate>
            <div className="grid md:grid-cols-2 gap-4">
              <Input
                id="reg-name"
                label="Full Name"
                required
                value={regForm.full_name}
                autoComplete="name"
                placeholder="As per official ID"
                onChange={(e) => setRegForm((c) => ({ ...c, full_name: e.target.value }))}
              />
              <Input
                id="reg-dob"
                label="Date of Birth"
                required
                type="date"
                max={TODAY}
                value={regForm.date_of_birth}
                error={regError || undefined}
                onChange={(e) => setRegForm((c) => ({ ...c, date_of_birth: e.target.value }))}
              />
              <Select
                id="reg-gender"
                label="Gender"
                value={regForm.gender}
                onChange={(e) => setRegForm((c) => ({ ...c, gender: e.target.value }))}
              >
                <option value="">Select Gender</option>
                <option value="MALE">Male</option>
                <option value="FEMALE">Female</option>
                <option value="OTHER">Other</option>
              </Select>
            </div>
            <div className="flex justify-end mt-6 pt-4 border-t border-line">
              <Button type="submit" variant="primary">
                Continue to Eligibility Check <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            </div>
          </form>
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
                {eligibleSchemes.map((item) => (
                  <Card key={item.scheme.scheme_id} eligible className="p-5">
                    <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                      <div>
                        <h3 className="text-lg font-bold text-ink mb-1">{item.scheme.scheme_name}</h3>
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

                    {/* Satisfied Criteria Checklist */}
                    <SatisfiedRulesList details={item.evaluation_details} />

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
                  {ineligibleSchemes.map((item) => (
                    <Card key={item.scheme.scheme_id} className="p-4 bg-surface/60">
                      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2">
                        <div>
                          <h4 className="text-sm font-semibold text-ink">{item.scheme.scheme_name}</h4>
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
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
