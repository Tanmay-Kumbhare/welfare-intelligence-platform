import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import Input from "../components/ui/Input";
import Select from "../components/ui/Select";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/StatusStates";
import { authService, citizenService, formService } from "../services/api";
import { getUser, clearAuth } from "../services/auth";
import { extractApiErrorMessage } from "../utils/apiError";
import {
  buildFullName,
  calculateAge,
  hasNoErrors,
  splitFullName,
  validateDob,
  validateEmail,
  validateFirstName,
  validateIncome,
  validateLastName,
  validateMiddleName,
  validateMobile,
} from "../utils/profileValidation";


const FORM_CODE = "GENERAL_CITIZEN_PROFILE";

const PROFILE_TYPE_OPTIONS = [
  { value: "STUDENT", label: "Student" },
  { value: "FARMER", label: "Farmer" },
  { value: "EMPLOYEE", label: "Employee / Worker" },
  { value: "BUSINESS", label: "Business / Entrepreneur" },
  { value: "SENIOR_CITIZEN", label: "Senior Citizen" },
  { value: "HOMEMAKER", label: "Homemaker" },
  { value: "PWD", label: "Person with Disability" },
  { value: "OTHER", label: "Other" },
];

function Row({ label, value }) {
  return (
    <div className="flex flex-col sm:flex-row sm:justify-between gap-1 py-3 first:pt-0 last:pb-0">
      <dt className="text-xs text-ink-soft">{label}</dt>
      <dd className="text-sm text-ink sm:text-right">
        {value === null || value === undefined || value === "" ? "Not provided" : String(value)}
      </dd>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <section>
      <h2 className="text-xl mb-3">{title}</h2>
      <Card>
        <dl className="divide-y divide-line">{children}</dl>
      </Card>
    </section>
  );
}

function formatAnswer(value) {
  if (value === null || value === undefined || value === "") return "Not provided";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) {
    return value
      .map((item) =>
        typeof item === "object" && item !== null
          ? [item.name, item.relationship].filter(Boolean).join(" · ") || "Family member"
          : String(item)
      )
      .join(", ");
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function data(citizen) {
  const { firstName, middleName, lastName } = splitFullName(citizen.full_name || "");
  return {
    // Split name fields — composed into full_name before API calls.
    firstName,
    middleName,
    lastName,
    date_of_birth: citizen.date_of_birth || "",
    gender: citizen.gender || "",
    mobile_number: citizen.mobile_number || "",
    email_id: citizen.email_id || "",
    citizen_type: citizen.citizen_type || "GENERAL",
    profile_types: citizen.profile_types || [],
    demographic: {
      disability_status: "NONE",
      ...(citizen.demographic || {}),
    },
    financial: {
      is_bpl_card_holder: false,
      is_income_tax_payer: false,
      ...(citizen.financial || {}),
    },
    location: {
      ...(citizen.location || {}),
    },
  };
}

function Editor({ value, setValue, save, cancel, saving, error, fieldErrors, onFieldChange }) {
  const nested = (group, field, next) =>
    setValue((current) => ({ ...current, [group]: { ...current[group], [field]: next } }));

  // Generic field renderer for profile sub-objects (no validation needed for these).
  const field = (group, key, label, type = "text") => (
    <Input
      id={`profile-${key}`}
      key={key}
      label={label}
      type={type}
      value={value[group][key] ?? ""}
      onChange={(e) =>
        nested(group, key, e.target.value === "" ? null : type === "number" ? Number(e.target.value) : e.target.value)
      }
    />
  );

  // Derived age — display only.
  const age = calculateAge(value.date_of_birth);

  return (
    <form onSubmit={save} noValidate className="space-y-7">
      {error && <ErrorState title="Unable to save profile" message={error} />}
      <section>
        <h2 className="text-xl mb-3">Personal</h2>
        <Card>
          <div className="grid md:grid-cols-3 gap-x-5">
            <Input
              id="profile-first-name"
              label="First name"
              required
              value={value.firstName}
              error={fieldErrors?.firstName}
              onChange={(e) => {
                const v = e.target.value;
                setValue((cur) => ({ ...cur, firstName: v }));
                onFieldChange("firstName", validateFirstName, v);
              }}
              autoComplete="given-name"
            />
            <Input
              id="profile-middle-name"
              label="Middle name"
              value={value.middleName}
              error={fieldErrors?.middleName}
              onChange={(e) => {
                const v = e.target.value;
                setValue((cur) => ({ ...cur, middleName: v }));
                onFieldChange("middleName", validateMiddleName, v);
              }}
              autoComplete="additional-name"
            />
            <Input
              id="profile-last-name"
              label="Last name"
              required
              value={value.lastName}
              error={fieldErrors?.lastName}
              onChange={(e) => {
                const v = e.target.value;
                setValue((cur) => ({ ...cur, lastName: v }));
                onFieldChange("lastName", validateLastName, v);
              }}
              autoComplete="family-name"
            />
          </div>
          <div className="grid md:grid-cols-2 gap-x-5">
            <div>
              <Input
                id="profile-dob"
                label="Date of birth"
                required
                type="date"
                max={new Date().toISOString().slice(0, 10)}
                value={value.date_of_birth}
                error={fieldErrors?.date_of_birth}
                onChange={(e) => {
                  const v = e.target.value;
                  setValue((cur) => ({ ...cur, date_of_birth: v }));
                  onFieldChange("date_of_birth", validateDob, v);
                }}
                autoComplete="bday"
              />
              {age !== null && !fieldErrors?.date_of_birth && (
                <p className="text-xs text-ink-soft -mt-3 mb-5">
                  Age: <strong>{age}</strong> years
                </p>
              )}
            </div>
            <Select
              id="profile-gender"
              label="Gender"
              value={value.gender || ""}
              onChange={(e) => setValue((cur) => ({ ...cur, gender: e.target.value || null }))}
            >
              <option value="">Prefer not to say</option>
              <option value="MALE">Male</option>
              <option value="FEMALE">Female</option>
              <option value="OTHER">Other</option>
            </Select>
            <Select
              id="profile-type"
              label="Citizen type"
              value={value.citizen_type}
              onChange={(e) => setValue((cur) => ({ ...cur, citizen_type: e.target.value }))}
            >
              <option value="GENERAL">General</option>
              <option value="FARMER">Farmer</option>
              <option value="STUDENT">Student</option>
              <option value="SENIOR">Senior</option>
            </Select>
            <div className="col-span-full md:col-span-3 mt-2">
              <label className="block text-sm font-medium mb-2">Profile types (Select all that apply)</label>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                {PROFILE_TYPE_OPTIONS.map((opt) => (
                  <label key={opt.value} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      className="w-4 h-4 accent-accent-ink"
                      checked={value.profile_types.includes(opt.value)}
                      onChange={(e) => {
                        const checked = e.target.checked;
                        setValue((cur) => ({
                          ...cur,
                          profile_types: checked
                            ? [...cur.profile_types, opt.value]
                            : cur.profile_types.filter((t) => t !== opt.value)
                        }));
                      }}
                    />
                    <span className="text-sm">{opt.label}</span>
                  </label>
                ))}
              </div>
            </div>
            <Input
              id="profile-mobile"
              label="Mobile number"
              required
              type="tel"
              inputMode="numeric"
              maxLength={10}
              value={value.mobile_number || ""}
              error={fieldErrors?.mobile_number}
              onChange={(e) => {
                const v = e.target.value.replace(/\D/g, "").slice(0, 10);
                setValue((cur) => ({ ...cur, mobile_number: v || null }));
                onFieldChange("mobile_number", validateMobile, v);
              }}
              autoComplete="tel"
            />
            <Input
              id="profile-email"
              label="Email"
              type="email"
              value={value.email_id || ""}
              readOnly
              className="opacity-70"
              hint="Email cannot be changed here."
            />
          </div>
        </Card>
      </section>
      <section>
        <h2 className="text-xl mb-3">Profile details</h2>
        <Card>
          <div className="grid md:grid-cols-2 gap-x-5">
            {field("demographic", "education_level", "Education level")}
            {field("demographic", "occupation", "Occupation")}
            {field("demographic", "family_size", "Family size", "number")}
            {field("demographic", "marital_status", "Marital status")}
            {field("demographic", "social_category", "Social category")}
            {field("demographic", "disability_status", "Disability status")}
            <Input
              id="profile-annual-income"
              label="Annual income (₹)"
              type="number"
              min={0}
              inputMode="numeric"
              value={value.financial?.annual_income ?? ""}
              error={fieldErrors?.annual_income}
              onChange={(e) => {
                const v = e.target.value;
                nested("financial", "annual_income", v === "" ? null : Number(v));
                onFieldChange("annual_income", validateIncome, v);
              }}
            />
            {field("financial", "employment_status", "Employment status")}
            {field("financial", "income_source", "Income source")}
            {field("financial", "poverty_category", "Poverty category")}
            {field("financial", "land_holding_size", "Land holding size (hectares)", "number")}
            {field("location", "state", "State")}
            {field("location", "district", "District")}
            {field("location", "village_city", "Village / city")}
            {field("location", "area_type", "Area type")}
            <Select id="profile-bpl" label="BPL card holder" value={String(value.financial.is_bpl_card_holder)} onChange={(e) => nested("financial", "is_bpl_card_holder", e.target.value === "true")}>
              <option value="false">No</option>
              <option value="true">Yes</option>
            </Select>
            <Select id="profile-tax" label="Income-tax payer" value={String(value.financial.is_income_tax_payer)} onChange={(e) => nested("financial", "is_income_tax_payer", e.target.value === "true")}>
              <option value="false">No</option>
              <option value="true">Yes</option>
            </Select>
          </div>
        </Card>
      </section>
      <div className="flex justify-end gap-3">
        <Button type="button" variant="secondary" onClick={cancel} disabled={saving}>Cancel</Button>
        <Button type="submit" disabled={saving}>{saving ? "Saving..." : "Save profile"}</Button>
      </div>
    </form>
  );
}



export default function ProfilePage() {
  const navigate = useNavigate();
  const [citizen, setCitizen] = useState(null);
  const [citizenId, setCitizenId] = useState(null);
  const [draft, setDraft] = useState(null);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [status, setStatus] = useState("loading");
  // Full submitted record from the eligibility form (every answer, not just
  // the fields with a canonical profile column).
  const [savedAnswers, setSavedAnswers] = useState(null);
  const [formSections, setFormSections] = useState(null);

  const reloadProfile = useCallback(async () => {
    try {
      const me = await authService.me();
      const id = me.data.citizen_id;
      setCitizenId(id);
      if (!id) {
        setStatus("empty");
        return;
      }
      const response = await citizenService.get(id);
      setCitizen(response.data);
      setDraft(data(response.data));
      setStatus("ready");
      // Load the full submitted record in the background — display-only,
      // failures here never block the profile page.
      try {
        const [savedResp, formResp] = await Promise.all([
          formService.getSavedAnswers(FORM_CODE),
          formService.getActive(FORM_CODE),
        ]);
        setSavedAnswers(savedResp.data?.values || null);
        setFormSections(formResp.data?.sections || null);
      } catch {
        setSavedAnswers(null);
        setFormSections(null);
      }
    } catch (requestError) {
      const code = requestError?.response?.status;
      if (code === 401) {
        clearAuth();
        setStatus("empty");
        return;
      }
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    reloadProfile();
  }, [reloadProfile]);

  // Live per-field validation callback (passed to Editor).
  const onFieldChange = (field, validatorFn, value) => {
    const err = validatorFn(value);
    setFieldErrors((current) => ({ ...current, [field]: err }));
  };

  const save = async (event) => {
    event.preventDefault();
    // Run a full validation pass before sending to the API.
    const errors = {
      firstName: validateFirstName(draft.firstName),
      middleName: validateMiddleName(draft.middleName),
      lastName: validateLastName(draft.lastName),
      mobile_number: validateMobile(draft.mobile_number),
      date_of_birth: validateDob(draft.date_of_birth),
      annual_income: validateIncome(draft.financial?.annual_income),
    };
    setFieldErrors(errors);
    if (!hasNoErrors(errors)) {
      setError("Please correct the highlighted fields before saving.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      // Compose full_name from the three split name parts.
      const full_name = buildFullName(draft.firstName, draft.middleName, draft.lastName);
      const payload = {
        full_name,
        date_of_birth: draft.date_of_birth,
        gender: draft.gender || null,
        mobile_number: draft.mobile_number || null,
        email_id: draft.email_id || null,
        citizen_type: draft.citizen_type,
        profile_types: draft.profile_types,
        demographic: draft.demographic,
        financial: draft.financial,
        location: draft.location,
      };
      const response = await citizenService.update(citizenId, payload);
      setCitizen(response.data);
      setDraft(data(response.data));
      setFieldErrors({});
      setEditing(false);
    } catch (requestError) {
      setError(
        extractApiErrorMessage(
          requestError,
          "Your changes could not be saved. Please check the fields and try again."
        )
      );
    } finally {
      setSaving(false);
    }
  };

  if (status === "loading") {
    return <LoadingState label="Loading your profile..." />;
  }

  if (status === "error") {
    return (
      <ErrorState
        title="Unable to load profile"
        message="We couldn't load your saved citizen profile. Please try again."
        onRetry={reloadProfile}
      />
    );
  }

  if (status === "empty" || !citizenId) {
    return (
      <EmptyState
        title="No citizen profile yet"
        message="Create an account and complete your profile to check your eligibility against the active scheme rules."
        action={<Button to="/register" variant="primary">Create account</Button>}
      />
    );
  }

  const d = citizen.demographic || {};
  const f = citizen.financial || {};
  const l = citizen.location || {};

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-4 mb-8">
        <div>
          <h1 className="text-[30px] mb-3">My profile</h1>
          <p className="mb-0">Information stored for your citizen record.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button to="/check-eligibility" size="sm">Check eligibility</Button>
          {!editing && (
            <Button onClick={() => { setDraft(data(citizen)); setEditing(true); }} variant="secondary" size="sm">Edit profile</Button>
          )}
        </div>
      </div>
      {editing ? (
        <Editor
          value={draft}
          setValue={setDraft}
          save={save}
          cancel={() => { setDraft(data(citizen)); setError(""); setFieldErrors({}); setEditing(false); }}
          saving={saving}
          error={error}
          fieldErrors={fieldErrors}
          onFieldChange={onFieldChange}
        />
      ) : (
        <div className="space-y-7">
          {savedAnswers && formSections && formSections.length > 0 && (
            <section>
              <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                <h2 className="text-xl mb-0">Your eligibility form answers</h2>
                <Button to="/check-eligibility?edit=1" size="sm" variant="secondary">
                  Review &amp; edit answers
                </Button>
              </div>
              <p className="text-sm text-ink-soft mb-3 max-w-[70ch]">
                The complete record you submitted in the eligibility form —
                everything here was already answered and is reused
                automatically. Use “Review &amp; edit answers” to change any
                of it (the form opens fully prefilled).
              </p>
              {formSections.map((section) => {
                const answered = section.questions.filter(
                  (q) => savedAnswers[q.question_code] !== undefined
                );
                if (answered.length === 0) return null;
                return (
                  <Card key={section.section_id} className="mb-4">
                    <h3 className="text-base mb-2">{section.section_name}</h3>
                    <dl className="divide-y divide-line">
                      {answered.map((q) => (
                        <Row
                          key={q.question_id}
                          label={q.question_text}
                          value={formatAnswer(savedAnswers[q.question_code])}
                        />
                      ))}
                    </dl>
                  </Card>
                );
              })}
            </section>
          )}
          <Section title="Personal">
            <Row label="Full name" value={citizen.full_name} />
            <Row label="Date of birth" value={citizen.date_of_birth} />
            <Row label="Gender" value={citizen.gender} />
            <Row label="Citizen type" value={citizen.citizen_type} />
            <Row 
              label="Profile types" 
              value={citizen.profile_types?.map(t => PROFILE_TYPE_OPTIONS.find(o => o.value === t)?.label || t).join(", ")} 
            />
          </Section>
          <Section title="Education / Employment">
            <Row label="Education level" value={d.education_level} />
            <Row label="Occupation" value={d.occupation} />
            <Row label="Employment status" value={f.employment_status} />
          </Section>
          <Section title="Financial">
            <Row label="Annual income" value={f.annual_income} />
            <Row label="Poverty category" value={f.poverty_category} />
            <Row label="BPL card holder" value={f.is_bpl_card_holder ? "Yes" : "No"} />
            <Row label="Income-tax payer" value={f.is_income_tax_payer ? "Yes" : "No"} />
          </Section>
          <Section title="Social / Family">
            <Row label="Social category" value={d.social_category} />
            <Row label="Disability status" value={d.disability_status} />
            <Row label="Family size" value={d.family_size} />
            <Row label="Marital status" value={d.marital_status} />
          </Section>
          <Section title="Location">
            <Row label="State" value={l.state} />
            <Row label="District" value={l.district} />
            <Row label="Village / city" value={l.village_city} />
            <Row label="Area type" value={l.area_type} />
          </Section>
        </div>
      )}
    </div>
  );
}
