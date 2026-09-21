import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronLeft, ChevronRight, Check, Loader2 } from "lucide-react";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import Input from "../components/ui/Input";
import Select from "../components/ui/Select";
import { ErrorState, LoadingState } from "../components/ui/StatusStates";
import { citizenService, eligibilityService, formService, formSubmissionService } from "../services/api";
import { clearStoredCitizenId, getStoredCitizenId, setStoredCitizenId } from "../utils/citizenStorage";
import FormSection from "../components/forms/FormSection";
import FormProgress from "../components/forms/FormProgress";
import ReviewStep from "../components/forms/ReviewStep";
import {
  computeApplicableMap,
  computeProgress,
  storedAnswersByQuestionId,
  percentage,
  backendErrorMessage,
} from "../components/forms/formLogic";

const FORM_CODE = "GENERAL_CITIZEN_PROFILE";
const TODAY = new Date().toISOString().slice(0, 10);

function answersPayload(answersMap) {
  return [...answersMap.entries()]
    .filter(([, value]) => value !== null && value !== undefined)
    .map(([question_id, value]) => ({ question_id, value, source: "USER_INPUT" }));
}

export default function CheckEligibilityPage() {
  const navigate = useNavigate();
  const [phase, setPhase] = useState("loading"); // loading|no-citizen|form|form-error|review|submitting|normalizing|evaluating
  const [identity, setIdentity] = useState(null);
  const [form, setForm] = useState(null);
  const [submission, setSubmission] = useState(null);
  const [answers, setAnswers] = useState(() => new Map());
  const [currentStep, setCurrentStep] = useState(0);
  const [message, setMessage] = useState("");
  const [saveState, setSaveState] = useState("idle"); // idle|saving|saved
  const [fieldErrors, setFieldErrors] = useState(() => new Map());
  const answersRef = useRef(answers);
  answersRef.current = answers;
  const submissionInFlight = useRef(false);
  const [loadKey, setLoadKey] = useState(0);

  // ---------------- identity + form load (parallel) ----------------
  // The citizen pointer (localStorage) and the active form definition are
  // independent — fetch them together instead of serially. The form is the
  // source of truth for every question; the citizen is the source of truth
  // for identity (never re-asked inside the form).
  useEffect(() => {
    let cancelled = false;
    const stored = getStoredCitizenId();
    const citizenPromise = stored
      ? citizenService
          .get(stored)
          .then((response) => response.data)
          .catch(() => {
            clearStoredCitizenId();
            return null;
          })
      : Promise.resolve(null);

    Promise.all([citizenPromise, formService.getActive(FORM_CODE)])
      .then(([citizen, formResponse]) => {
        if (cancelled) return;
        setForm(formResponse.data);
        if (citizen) {
          setIdentity({
            citizenId: citizen.citizen_id,
            fullName: citizen.full_name,
            dateOfBirth: citizen.date_of_birth,
            gender: citizen.gender,
          });
          setPhase("form");
        } else {
          setPhase("no-citizen");
        }
      })
      .catch(() => {
        if (!cancelled) setPhase("form-error");
      });
    return () => {
      cancelled = true;
    };
  }, [loadKey]);

  // ---------------- draft create/resume ----------------
  const ensureSubmission = useCallback(async () => {
    // POST /submissions resumes the citizen's latest editable draft server-
    // side. The in-flight guard stops React StrictMode's double effect fire
    // in dev from racing two creates (harmless server-side, but wasteful).
    if (submissionInFlight.current) return null;
    submissionInFlight.current = true;
    try {
      const response = await formSubmissionService.create(FORM_CODE, {
        citizen_id: identity.citizenId,
        answers: [],
      });
      setSubmission(response.data);
      return response.data;
    } finally {
      submissionInFlight.current = false;
    }
  }, [identity]);

  useEffect(() => {
    if (phase !== "form" || !identity || !form || submission) return;
    let cancelled = false;
    ensureSubmission()
      .then((draft) => {
        if (cancelled || !draft) return;
        setAnswers(storedAnswersByQuestionId(draft));
        if (draft.completion_percentage > 0) setSaveState("saved");
      })
      .catch(() => {
        if (!cancelled) setPhase("form-error");
      });
    return () => {
      cancelled = true;
    };
  }, [phase, identity, form, submission, ensureSubmission]);

  // ---------------- derived state ----------------
  const applicable = useMemo(
    () => (form ? computeApplicableMap(form.sections, answers) : new Map()),
    [form, answers],
  );
  const progress = useMemo(
    () => (form ? computeProgress(form.sections, answers, applicable) : { total: 0, answered: 0, missingRequired: [] }),
    [form, answers, applicable],
  );
  const completion = percentage(progress.answered, progress.total);
  const sectionsCount = form?.sections.length ?? 0;
  const currentSection = form?.sections[currentStep];

  // ---------------- actions ----------------
  const answerQuestion = (question, value) => {
    setAnswers((current) => {
      const next = new Map(current);
      next.set(question.question_id, value);
      return next;
    });
    setFieldErrors((current) => {
      if (!current.has(question.question_id)) return current;
      const next = new Map(current);
      next.delete(question.question_id);
      return next;
    });
  };

  const goToStep = (index) => {
    setCurrentStep(Math.min(Math.max(index, 0), Math.max(sectionsCount - 1, 0)));
    window.scrollTo({ top: 0 });
  };

  const saveProgress = async () => {
    setSaveState("saving");
    setMessage("");
    try {
      // Hidden (conditionally inapplicable) questions are never sent — the
      // visibility map is recomputed from the exact answers being saved.
      const nowApplicable = computeApplicableMap(form.sections, answersRef.current);
      const payload = answersPayload(answersRef.current).filter((a) => nowApplicable.get(a.question_id, true));
      const response = await formSubmissionService.update(submission.submission_id, {
        citizen_id: identity.citizenId,
        answers: payload,
      });
      setSubmission(response.data);
      setSaveState("saved");
      setAnswers(storedAnswersByQuestionId(response.data));
      return true;
    } catch (error) {
      setSaveState("idle");
      setMessage(backendErrorMessage(error, form?.sections || []));
      return false;
    }
  };

  const saveAndContinue = async () => {
    const saved = await saveProgress();
    if (saved) goToStep(currentStep + 1);
  };

  const submitAll = async () => {
    setPhase("submitting");
    setMessage("");
    try {
      await saveProgress();
      try {
        await formSubmissionService.complete(submission.submission_id, { citizen_id: identity.citizenId });
      } catch (error) {
        const detail = error?.response?.data?.detail ?? {};
        const missing = detail.missing_required || [];
        if (missing.length > 0 && form) {
          const nextErrors = new Map();
          let target = -1;
          form.sections.forEach((section, index) => {
            for (const question of section.questions) {
              if (missing.includes(question.question_code) && applicable.get(question.question_id, true)) {
                nextErrors.set(question.question_id, "This answer is required.");
                if (target < 0) target = index;
              }
            }
          });
          setFieldErrors(nextErrors);
          setPhase("form");
          goToStep(target >= 0 ? target : 0);
          setMessage("Some required answers are still missing. They are marked below.");
          return;
        }
        throw error;
      }
      setPhase("normalizing");
      await formSubmissionService.normalize(submission.submission_id, { citizen_id: identity.citizenId });
      // Existing eligibility flow: the results page reads stored assessments,
      // so evaluate (backend engine, unchanged) before navigating.
      setPhase("evaluating");
      await eligibilityService.evaluate(identity.citizenId);
      navigate(`/results/${identity.citizenId}`);
    } catch (error) {
      setPhase("form");
      setMessage(backendErrorMessage(error, form?.sections || []));
    }
  };

  // ---------------- first-time registration (no auth exists yet) ----------------
  const [regForm, setRegForm] = useState({ full_name: "", date_of_birth: "", gender: "" });
  const [regError, setRegError] = useState("");
  const register = async (event) => {
    event.preventDefault();
    setRegError("");
    if (regForm.full_name.trim().length < 2 || !regForm.date_of_birth || regForm.date_of_birth >= TODAY) {
      setRegError("Please enter your full name and a date of birth in the past.");
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
      const citizenId = response.data.citizen_id;
      setStoredCitizenId(citizenId);
      setIdentity({
        citizenId,
        fullName: response.data.full_name,
        dateOfBirth: response.data.date_of_birth,
        gender: response.data.gender,
      });
      // The form definition is already in state (loaded in parallel with the
      // citizen check) — no second fetch, no second identity step.
      setPhase("form");
    } catch {
      setRegError("Unable to create your profile right now. Please try again.");
    }
  };

  // ---------------- review data ----------------
  const reviewSections = useMemo(() => {
    if (!form) return [];
    return form.sections
      .map((section) => ({
        section,
        items: section.questions
          .filter((q) => applicable.get(q.question_id, true))
          .map((q) => ({ question: q, value: answers.get(q.question_id) ?? null })),
      }))
      .filter((entry) => entry.items.length > 0);
  }, [form, answers, applicable]);

  // ---------------- renders ----------------
  if (phase === "loading") return <LoadingState label="Loading your profile..." />;

  if (phase === "form-error") {
    return (
      <ErrorState
        title="Unable to load the form"
        message="The form service is not responding right now. Anything you already saved is safe — please try again."
        onRetry={() => {
          setForm(null);
          setSubmission(null);
          setPhase("loading");
          // Re-run the combined citizen+form load in place (no full page
          // reload — the local context is fine, the fetch just failed).
          setLoadKey((key) => key + 1);
        }}
      />
    );
  }

  if (phase === "no-citizen") {
    return (
      <div>
        <div className="mb-7">
          <h1 className="text-[30px] mb-3">Check your eligibility</h1>
          <p className="max-w-[66ch] mb-5">
            First create your citizen profile, then answer a short set of questions. We use your answers only to work
            out which government schemes you may be eligible for.
          </p>
        </div>
        <Card>
          <form onSubmit={register} noValidate>
            <div className="grid md:grid-cols-2 gap-x-5">
              <Input
                id="reg-name"
                label="Full name"
                required
                value={regForm.full_name}
                autoComplete="name"
                onChange={(event) => setRegForm((current) => ({ ...current, full_name: event.target.value }))}
              />
              <Input
                id="reg-dob"
                label="Date of birth"
                required
                type="date"
                max={TODAY}
                value={regForm.date_of_birth}
                error={regError || undefined}
                onChange={(event) => setRegForm((current) => ({ ...current, date_of_birth: event.target.value }))}
              />
              <Select
                id="reg-gender"
                label="Gender"
                value={regForm.gender}
                onChange={(event) => setRegForm((current) => ({ ...current, gender: event.target.value }))}
              >
                <option value="">Prefer not to say</option>
                <option value="MALE">Male</option>
                <option value="FEMALE">Female</option>
                <option value="OTHER">Other</option>
              </Select>
            </div>
            <div className="flex justify-end mt-4 pt-5 border-t border-line">
              <Button type="submit">Create profile and continue</Button>
            </div>
          </form>
        </Card>
      </div>
    );
  }

  if (phase === "review") {
    return (
      <div>
        <div className="mb-7">
          <h1 className="text-[30px] mb-3">Review your information</h1>
          <p className="max-w-[66ch]">Check everything below. Use Edit to go back to any section.</p>
        </div>
        {message && (
          <div className="mb-5">
            <ErrorState title="Unable to continue" message={message} />
          </div>
        )}
        <ReviewStep reviewSections={reviewSections} onEdit={goToStep} />
        <div className="flex flex-wrap justify-between gap-3 mt-7 pt-5 border-t border-line">
          <Button type="button" variant="ghost" onClick={() => setPhase("form")}>
            <ChevronLeft className="h-4 w-4" aria-hidden="true" /> Back to form
          </Button>
          <Button onClick={submitAll} disabled={phase !== "review"}>
            Submit and check eligibility
          </Button>
        </div>
      </div>
    );
  }

  if (phase === "submitting" || phase === "normalizing" || phase === "evaluating") {
    return (
      <LoadingState
        label={phase === "submitting" ? "Submitting your answers..." : phase === "normalizing" ? "Organising your information..." : "Checking schemes for you..."}
      />
    );
  }

  return (
    <div>
      <div className="mb-7">
        <h1 className="text-[30px] mb-3">{form?.form_name || "Check your eligibility"}</h1>
        <p className="max-w-[66ch] mb-3">
          {form?.description || "Answer the questions below. Your progress is saved as you go."}
        </p>
        {identity && (
          <p className="text-xs text-ink-soft mb-5">
            Answering as <span className="text-ink font-medium">{identity.fullName}</span>
            {identity.dateOfBirth ? ` · DOB ${identity.dateOfBirth}` : ""} — this was set when you created your
            profile and is not asked again here.
          </p>
        )}
        {form && submission && (
          <FormProgress
            sections={form.sections}
            currentStep={currentStep}
            applicable={applicable}
            answers={answers}
            completionPercentage={Math.max(submission.completion_percentage ?? 0, completion)}
          />
        )}
      </div>
      {message && (
        <div className="mb-5">
          <ErrorState title="Unable to continue" message={message} />
        </div>
      )}
      {form && currentSection && submission && (
        <Card>
          <FormSection
            section={currentSection}
            answers={answers}
            applicable={applicable}
            onAnswerChange={answerQuestion}
            fieldErrors={fieldErrors}
            sectionIndex={currentStep}
            totalSections={sectionsCount}
          />
          <div className="flex flex-wrap justify-between items-center gap-3 mt-7 pt-5 border-t border-line">
            <Button type="button" variant="ghost" onClick={() => goToStep(currentStep - 1)} disabled={currentStep === 0}>
              <ChevronLeft className="h-4 w-4" aria-hidden="true" /> Back
            </Button>
            <div className="flex items-center gap-3">
              {saveState === "saving" && (
                <span className="text-xs text-ink-soft flex items-center gap-1">
                  <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" /> Saving...
                </span>
              )}
              {saveState === "saved" && (
                <span className="text-xs text-ok-ink flex items-center gap-1">
                  <Check className="h-3 w-3" aria-hidden="true" /> Progress saved
                </span>
              )}
              <Button type="button" variant="secondary" onClick={saveProgress} disabled={saveState === "saving"}>
                Save draft
              </Button>
              {currentStep < sectionsCount - 1 ? (
                <Button onClick={saveAndContinue}>
                  Save &amp; continue <ChevronRight className="h-4 w-4" aria-hidden="true" />
                </Button>
              ) : (
                <Button onClick={() => setPhase("review")}>Review &amp; submit</Button>
              )}
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
