import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import Input from "../components/ui/Input";
import Select from "../components/ui/Select";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/StatusStates";
import { authService, citizenService } from "../services/api";
import { getUser, clearAuth } from "../services/auth";
import { extractApiErrorMessage } from "../utils/apiError";

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

function data(citizen) {
  return {
    full_name: citizen.full_name || "",
    date_of_birth: citizen.date_of_birth || "",
    gender: citizen.gender || "",
    mobile_number: citizen.mobile_number || "",
    email_id: citizen.email_id || "",
    citizen_type: citizen.citizen_type || "GENERAL",
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

function Editor({ value, setValue, save, cancel, saving, error }) {
  const root = (field, next) => setValue((current) => ({ ...current, [field]: next }));
  const nested = (group, field, next) =>
    setValue((current) => ({ ...current, [group]: { ...current[group], [field]: next } }));

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

  return (
    <form onSubmit={save} noValidate className="space-y-7">
      {error && <ErrorState title="Unable to save profile" message={error} />}
      <section>
        <h2 className="text-xl mb-3">Personal</h2>
        <Card>
          <div className="grid md:grid-cols-2 gap-x-5">
            <Input id="profile-name" label="Full name" required value={value.full_name} onChange={(e) => root("full_name", e.target.value)} />
            <Input id="profile-dob" label="Date of birth" required type="date" value={value.date_of_birth} onChange={(e) => root("date_of_birth", e.target.value)} />
            <Select id="profile-gender" label="Gender" value={value.gender} onChange={(e) => root("gender", e.target.value || null)}>
              <option value="">Prefer not to say</option>
              <option value="MALE">Male</option>
              <option value="FEMALE">Female</option>
              <option value="OTHER">Other</option>
            </Select>
            <Select id="profile-type" label="Citizen type" value={value.citizen_type} onChange={(e) => root("citizen_type", e.target.value)}>
              <option value="GENERAL">General</option>
              <option value="FARMER">Farmer</option>
              <option value="STUDENT">Student</option>
              <option value="SENIOR">Senior</option>
            </Select>
            <Input id="profile-mobile" label="Mobile number" value={value.mobile_number} onChange={(e) => root("mobile_number", e.target.value || null)} />
            <Input id="profile-email" label="Email" type="email" value={value.email_id} onChange={(e) => root("email_id", e.target.value || null)} readOnly className="opacity-70" />
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
            {field("financial", "annual_income", "Annual income", "number")}
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
  const [status, setStatus] = useState("loading");

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

  const save = async (event) => {
    event.preventDefault();
    if (!draft.full_name.trim() || !draft.date_of_birth) {
      return setError("Full name and date of birth are required.");
    }
    setSaving(true);
    setError("");
    try {
      const response = await citizenService.update(citizenId, draft);
      setCitizen(response.data);
      setDraft(data(response.data));
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
          cancel={() => { setDraft(data(citizen)); setError(""); setEditing(false); }}
          saving={saving}
          error={error}
        />
      ) : (
        <div className="space-y-7">
          <Section title="Personal">
            <Row label="Full name" value={citizen.full_name} />
            <Row label="Date of birth" value={citizen.date_of_birth} />
            <Row label="Gender" value={citizen.gender} />
            <Row label="Citizen type" value={citizen.citizen_type} />
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
