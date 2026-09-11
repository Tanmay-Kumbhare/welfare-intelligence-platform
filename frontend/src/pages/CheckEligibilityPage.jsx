import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Check, ChevronLeft, ChevronRight, ClipboardCheck } from "lucide-react";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import Input from "../components/ui/Input";
import Select from "../components/ui/Select";
import { ErrorState, LoadingState } from "../components/ui/StatusStates";
import { citizenService, eligibilityService } from "../services/api";
import { clearStoredCitizenId, getStoredCitizenId, setStoredCitizenId } from "../utils/citizenStorage";

const STEPS = ["About you", "Education / Work", "Financial", "Social / Family", "Location", "Review"];
const CITIZEN_TYPES = [["FARMER", "Farmer"], ["STUDENT", "Student"], ["SENIOR", "Senior Citizen"], ["GENERAL", "General Citizen"]];
const TODAY = new Date().toISOString().slice(0, 10);
const EMPTY_FORM = {
  full_name: "", date_of_birth: "", gender: "", citizen_type: "GENERAL", education_level: "", occupation: "",
  employment_status: "", annual_income: "", poverty_category: "", is_bpl_card_holder: false,
  is_income_tax_payer: false, land_holding_size: "", social_category: "", disability_status: "NONE",
  family_size: "", marital_status: "", state: "", district: "", village_city: "", area_type: "",
};

const text = (value) => value === null || value === undefined ? "" : String(value);
function formFromCitizen(citizen) {
  const demographic = citizen.demographic || {};
  const financial = citizen.financial || {};
  const location = citizen.location || {};
  return {
    full_name: text(citizen.full_name), date_of_birth: text(citizen.date_of_birth), gender: text(citizen.gender), citizen_type: citizen.citizen_type,
    education_level: text(demographic.education_level), occupation: text(demographic.occupation), employment_status: text(financial.employment_status),
    annual_income: text(financial.annual_income), poverty_category: text(financial.poverty_category), is_bpl_card_holder: Boolean(financial.is_bpl_card_holder),
    is_income_tax_payer: Boolean(financial.is_income_tax_payer), land_holding_size: text(financial.land_holding_size), social_category: text(demographic.social_category),
    disability_status: text(demographic.disability_status) || "NONE", family_size: text(demographic.family_size), marital_status: text(demographic.marital_status),
    state: text(location.state), district: text(location.district), village_city: text(location.village_city), area_type: text(location.area_type),
  };
}

function numberOrNull(value) { return value === "" ? null : Number(value); }
function payload(form) {
  return {
    full_name: form.full_name.trim(), date_of_birth: form.date_of_birth, gender: form.gender || null, citizen_type: form.citizen_type,
    demographic: { education_level: form.education_level || null, occupation: form.occupation.trim() || null, family_size: form.family_size === "" ? null : Number(form.family_size), marital_status: form.marital_status || null, social_category: form.social_category || null, disability_status: form.disability_status, type_specific_metadata: null },
    financial: { annual_income: numberOrNull(form.annual_income), employment_status: form.employment_status || null, income_source: null, poverty_category: form.poverty_category || null, land_holding_size: numberOrNull(form.land_holding_size), is_bpl_card_holder: form.is_bpl_card_holder, is_income_tax_payer: form.is_income_tax_payer },
    location: { state: form.state.trim() || null, district: form.district.trim() || null, village_city: form.village_city.trim() || null, area_type: form.area_type || null },
  };
}

function validate(form, step) {
  const errors = {};
  if (step === 0) {
    if (form.full_name.trim().length < 2) errors.full_name = "Enter your full name.";
    if (!form.date_of_birth) errors.date_of_birth = "Enter your date of birth.";
    else if (form.date_of_birth >= TODAY) errors.date_of_birth = "Date of birth must be in the past.";
    if (!CITIZEN_TYPES.some(([value]) => value === form.citizen_type)) errors.citizen_type = "Choose a valid citizen type.";
  }
  if (step === 2) {
    for (const [field, label] of [["annual_income", "Annual income"], ["land_holding_size", "Land holding size"]]) {
      if (form[field] !== "" && (!Number.isFinite(Number(form[field])) || Number(form[field]) < 0)) errors[field] = `${label} must be a non-negative number.`;
    }
  }
  if (step === 3 && form.family_size !== "") {
    const size = Number(form.family_size);
    if (!Number.isInteger(size) || size < 1 || size > 50) errors.family_size = "Family size must be a whole number from 1 to 50.";
  }
  return errors;
}

function Summary({ label, value }) { return <div className="flex flex-col sm:flex-row sm:justify-between gap-1 py-2 border-b border-line last:border-0"><dt className="text-xs text-ink-soft">{label}</dt><dd className="text-sm text-ink sm:text-right">{value || "Not provided"}</dd></div>; }

export default function CheckEligibilityPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [form, setForm] = useState({ ...EMPTY_FORM, citizen_type: searchParams.get("citizenType") || "GENERAL" });
  const [step, setStep] = useState(0);
  const [mode, setMode] = useState(() => getStoredCitizenId() ? "checking" : "create");
  const [existing, setExisting] = useState(null);
  const [errors, setErrors] = useState({});
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const id = getStoredCitizenId();
    if (!id) return;
    citizenService.get(id).then((response) => { setExisting(response.data); setForm(formFromCitizen(response.data)); setMode("existing"); }).catch(() => { clearStoredCitizenId(); setMode("create"); });
  }, []);

  const update = (field, value) => { setForm((current) => ({ ...current, [field]: value })); setErrors((current) => ({ ...current, [field]: undefined })); };
  const next = () => { const nextErrors = validate(form, step); setErrors(nextErrors); if (!Object.keys(nextErrors).length) setStep((current) => Math.min(current + 1, STEPS.length - 1)); };
  const evaluate = async (id) => { setSubmitting(true); setMessage(""); try { await eligibilityService.evaluate(id); navigate(`/results/${id}`); } catch { setMessage("Unable to check eligibility right now. Please try again."); } finally { setSubmitting(false); } };
  const submit = async (event) => {
    event.preventDefault();
    const formErrors = validate(form, 0); setErrors(formErrors); if (Object.keys(formErrors).length) { setStep(0); return; }
    setSubmitting(true); setMessage("");
    try { const response = await citizenService.register(payload(form)); const id = response.data.citizen_id; setStoredCitizenId(id); await evaluate(id); }
    catch { setSubmitting(false); setMessage("Unable to create your profile right now. Please check your details and try again."); }
  };

  if (mode === "checking") return <LoadingState label="Loading your profile..." />;
  if (mode === "existing" && existing) return <div><h1 className="text-[30px] mb-3">Check your eligibility</h1><p className="max-w-[64ch] mb-7">Your saved citizen profile is ready. Run the backend eligibility check again or create a separate profile.</p>{message ? <ErrorState title="Eligibility check failed" message={message} onRetry={() => evaluate(existing.citizen_id)} /> : <Card><div className="flex items-start gap-4 mb-5"><ClipboardCheck className="h-6 w-6 text-accent-ink shrink-0" aria-hidden="true" /><div><h2 className="text-xl mb-1">{existing.full_name}</h2><p className="text-sm mb-0">{existing.citizen_type} profile loaded from the backend.</p></div></div><div className="flex flex-wrap gap-3"><Button onClick={() => evaluate(existing.citizen_id)} disabled={submitting}>{submitting ? "Checking..." : "Check eligibility"}</Button><Button to="/profile" variant="secondary">View profile</Button><Button variant="ghost" onClick={() => { clearStoredCitizenId(); setExisting(null); setForm(EMPTY_FORM); setMode("create"); }}>Create a new profile</Button></div></Card>}</div>;

  return <div>
    <div className="mb-7"><h1 className="text-[30px] mb-3">Check your eligibility</h1><p className="max-w-[66ch] mb-5">Complete a short profile. The backend EligibilityEngine will evaluate it against the active scheme rules.</p><div className="flex items-center gap-2 text-xs font-mono text-ink-soft" aria-label={`Step ${step + 1} of ${STEPS.length}`}><span>STEP {step + 1} OF {STEPS.length}</span><div className="flex-1 h-1 bg-line max-w-65" aria-hidden="true"><div className="h-1 bg-accent" style={{ width: `${((step + 1) / STEPS.length) * 100}%` }} /></div></div></div>
    {message && <div className="mb-5"><ErrorState title="Unable to continue" message={message} /></div>}
    <form onSubmit={submit} noValidate><Card><div className="border-b border-line pb-4 mb-6"><p className="font-mono text-xs text-accent-ink mb-1">SECTION {step + 1}</p><h2 className="text-2xl mb-0">{STEPS[step]}</h2></div>
      {step === 0 && <div className="grid md:grid-cols-2 gap-x-5"><Input id="full-name" label="Full name" required value={form.full_name} onChange={(event) => update("full_name", event.target.value)} error={errors.full_name} autoComplete="name" /><Input id="date-of-birth" label="Date of birth" required type="date" max={TODAY} value={form.date_of_birth} onChange={(event) => update("date_of_birth", event.target.value)} error={errors.date_of_birth} /><Select id="gender" label="Gender" value={form.gender} onChange={(event) => update("gender", event.target.value)}><option value="">Prefer not to say</option><option value="MALE">Male</option><option value="FEMALE">Female</option><option value="OTHER">Other</option></Select><Select id="citizen-type" label="Citizen type" required value={form.citizen_type} onChange={(event) => update("citizen_type", event.target.value)} error={errors.citizen_type}>{CITIZEN_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select></div>}
      {step === 1 && <div className="grid md:grid-cols-2 gap-x-5"><Select id="education-level" label="Education level" value={form.education_level} onChange={(event) => update("education_level", event.target.value)}><option value="">Not provided</option><option value="ILLITERATE">Illiterate</option><option value="PRIMARY">Primary</option><option value="SECONDARY">Secondary (10th)</option><option value="HIGHER_SECONDARY">Higher Secondary (12th)</option><option value="GRADUATE">Graduate</option><option value="POST_GRADUATE">Post Graduate</option></Select><Input id="occupation" label="Occupation" value={form.occupation} onChange={(event) => update("occupation", event.target.value)} /><Select id="employment-status" label="Employment status" value={form.employment_status} onChange={(event) => update("employment_status", event.target.value)}><option value="">Not provided</option><option value="EMPLOYED">Employed</option><option value="UNEMPLOYED">Unemployed</option><option value="SELF_EMPLOYED">Self-employed</option><option value="FARMER">Farmer</option><option value="STUDENT">Student</option><option value="RETIRED">Retired</option></Select><p className="text-xs text-ink-soft mt-2">Optional profile information; eligibility is decided by backend rules.</p></div>}
      {step === 2 && <div className="grid md:grid-cols-2 gap-x-5"><Input id="annual-income" label="Annual family income (INR)" type="number" min="0" step="0.01" value={form.annual_income} onChange={(event) => update("annual_income", event.target.value)} error={errors.annual_income} hint="Optional" /><Input id="land-holding-size" label="Land holding size (hectares)" type="number" min="0" step="0.01" value={form.land_holding_size} onChange={(event) => update("land_holding_size", event.target.value)} error={errors.land_holding_size} hint="Optional; useful for farmer profiles" /><Select id="poverty-category" label="Poverty category" value={form.poverty_category} onChange={(event) => update("poverty_category", event.target.value)}><option value="">Not provided</option><option value="APL">APL</option><option value="BPL">BPL</option><option value="AAY">AAY</option></Select><div className="space-y-3 mb-5 md:mt-8"><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.is_bpl_card_holder} onChange={(event) => update("is_bpl_card_holder", event.target.checked)} /> BPL card holder</label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.is_income_tax_payer} onChange={(event) => update("is_income_tax_payer", event.target.checked)} /> Income-tax payer</label></div></div>}
      {step === 3 && <div className="grid md:grid-cols-2 gap-x-5"><Select id="social-category" label="Social category" value={form.social_category} onChange={(event) => update("social_category", event.target.value)}><option value="">Not provided</option><option value="GEN">General</option><option value="OBC">OBC</option><option value="SC">SC</option><option value="ST">ST</option></Select><Select id="disability-status" label="Disability status" value={form.disability_status} onChange={(event) => update("disability_status", event.target.value)}><option value="NONE">None</option><option value="PHYSICALLY_DISABLED">Physically disabled</option><option value="VISUALLY_IMPAIRED">Visually impaired</option><option value="HEARING_IMPAIRED">Hearing impaired</option><option value="OTHER">Other</option></Select><Input id="family-size" label="Family size" type="number" min="1" max="50" step="1" value={form.family_size} onChange={(event) => update("family_size", event.target.value)} error={errors.family_size} hint="Optional; 1 to 50 people" /><Select id="marital-status" label="Marital status" value={form.marital_status} onChange={(event) => update("marital_status", event.target.value)}><option value="">Not provided</option><option value="SINGLE">Single</option><option value="MARRIED">Married</option><option value="WIDOWED">Widowed</option><option value="DIVORCED">Divorced</option></Select></div>}
      {step === 4 && <div className="grid md:grid-cols-2 gap-x-5"><Input id="state" label="State" value={form.state} onChange={(event) => update("state", event.target.value)} /><Input id="district" label="District" value={form.district} onChange={(event) => update("district", event.target.value)} /><Input id="village-city" label="Village / city" value={form.village_city} onChange={(event) => update("village_city", event.target.value)} /><Select id="area-type" label="Area type" value={form.area_type} onChange={(event) => update("area_type", event.target.value)}><option value="">Not provided</option><option value="RURAL">Rural</option><option value="URBAN">Urban</option><option value="SEMI_URBAN">Semi-Urban</option></Select></div>}
      {step === 5 && <div><div className="flex items-center gap-2 mb-5 text-sm text-ok-ink"><Check className="h-4 w-4" aria-hidden="true" /> Review your information before creating the profile.</div><dl className="border border-line px-4"><Summary label="Name" value={form.full_name} /><Summary label="Date of birth" value={form.date_of_birth} /><Summary label="Citizen type" value={CITIZEN_TYPES.find(([value]) => value === form.citizen_type)?.[1]} /><Summary label="Education / work" value={[form.education_level, form.occupation, form.employment_status].filter(Boolean).join(" · ")} /><Summary label="Financial" value={[form.annual_income && `INR ${form.annual_income}`, form.poverty_category, form.land_holding_size && `${form.land_holding_size} ha`].filter(Boolean).join(" · ")} /><Summary label="Social / family" value={[form.social_category, form.disability_status !== "NONE" && form.disability_status, form.family_size && `${form.family_size} people`].filter(Boolean).join(" · ")} /><Summary label="Location" value={[form.village_city, form.district, form.state, form.area_type].filter(Boolean).join(" · ")} /></dl></div>}
      <div className="flex flex-wrap justify-between gap-3 mt-7 pt-5 border-t border-line"><Button type="button" variant="ghost" onClick={() => setStep((current) => Math.max(current - 1, 0))} disabled={step === 0 || submitting}><ChevronLeft className="h-4 w-4" aria-hidden="true" /> Back</Button>{step < STEPS.length - 1 ? <Button type="button" onClick={next}>Next <ChevronRight className="h-4 w-4" aria-hidden="true" /></Button> : <Button type="submit" disabled={submitting}>{submitting ? "Creating and checking..." : "Create profile and check eligibility"}</Button>}</div>
    </Card></form>
  </div>;
}
