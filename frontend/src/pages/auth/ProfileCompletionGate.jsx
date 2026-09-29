import { useEffect, useState } from "react";
import { Outlet, useNavigate } from "react-router-dom";
import Button from "../../components/ui/Button";
import Card from "../../components/ui/Card";
import { LoadingState, ErrorState } from "../../components/ui/StatusStates";
import { authService, citizenService } from "../../services/api";
import { getUser } from "../../services/auth";

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

export default function ProfileCompletionGate() {
  const navigate = useNavigate();
  const [status, setStatus] = useState("loading"); // loading | guest | error | needs-profile | needs-onboarding | ready
  const [citizen, setCitizen] = useState(null);
  const [selectedTypes, setSelectedTypes] = useState([]);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  useEffect(() => {
    const user = getUser();
    if (!user?.user_id) {
      setStatus("guest");
      return;
    }
    authService
      .me()
      .then((response) => {
        const data = response.data;
        if (!data.citizen_id) {
          setStatus("needs-profile");
          return;
        }
        return citizenService
          .get(data.citizen_id)
          .then((res) => {
            setCitizen(res.data);
            if (!res.data.profile_types || res.data.profile_types.length === 0) {
              setStatus("needs-onboarding");
            } else {
              setStatus("ready");
            }
          })
          .catch(() => setStatus("error"));
      })
      .catch(() => setStatus("guest"));
  }, []);

  const handleSaveOnboarding = async () => {
    if (selectedTypes.length === 0) {
      setSaveError("Please select at least one profile type.");
      return;
    }
    setSaving(true);
    setSaveError("");
    try {
      await citizenService.update(citizen.citizen_id, {
        ...citizen,
        profile_types: selectedTypes,
      });
      setStatus("ready");
    } catch (e) {
      setSaveError("Failed to save profile types. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  const toggleType = (value) => {
    setSelectedTypes((prev) =>
      prev.includes(value) ? prev.filter((t) => t !== value) : [...prev, value]
    );
    setSaveError(""); // Clear error when interacting
  };

  if (status === "loading") {
    return <LoadingState />;
  }

  if (status === "guest") {
    // Not signed in — AuthLayout's AuthGate normally redirects first, but if
    // we end up here anyway, just render the nested routes.
    return <Outlet />;
  }

  if (status === "error") {
    return (
      <ErrorState
        title="Could not load your profile"
        message="Your account exists, but we could not load your profile right now."
        action={<Button onClick={() => navigate("/profile")}>Go to profile</Button>}
      />
    );
  }

  if (status === "needs-profile") {
    return (
      <div>
        <div className="mb-8 border-b border-line pb-7">
          <h1 className="text-[30px] mb-3">Complete your profile</h1>
          <p className="max-w-[60ch]">
            You have an account, but your profile is not ready yet. Please fill
            in your details so we can check your eligibility and save your
            results.
          </p>
        </div>
        <Card>
          <div className="max-w-[520px] mx-auto text-sm text-ink-soft">
            <p className="mb-4">
              Your profile lets you check welfare schemes, save your answers,
              and return later. You can still browse public schemes, but
              eligibility checks require a completed profile.
            </p>
            <Button to="/profile" variant="primary" size="lg">
              Fill in my profile
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  if (status === "needs-onboarding") {
    return (
      <div>
        <div className="mb-8 border-b border-line pb-7">
          <h1 className="text-[30px] mb-3">What best describes you?</h1>
          <p className="max-w-[60ch]">
            Select all that apply. This helps us customize the questions and sections relevant to you.
          </p>
        </div>
        <Card>
          <div className="max-w-[520px] mx-auto text-sm text-ink-soft">
            <div className="space-y-3 mb-6">
              {PROFILE_TYPE_OPTIONS.map((opt) => (
                <label key={opt.value} className="flex items-center gap-3 p-3 border border-line rounded cursor-pointer hover:bg-slate-50 transition-colors">
                  <input
                    type="checkbox"
                    className="w-5 h-5 accent-accent-ink"
                    checked={selectedTypes.includes(opt.value)}
                    onChange={() => toggleType(opt.value)}
                  />
                  <span className="text-base text-ink font-medium">{opt.label}</span>
                </label>
              ))}
            </div>
            
            {saveError && (
              <div className="mb-4 text-[13px] text-excl-ink bg-excl-tint border border-excl-tint rounded-sm px-3 py-2">
                {saveError}
              </div>
            )}

            <Button onClick={handleSaveOnboarding} variant="primary" size="lg" disabled={saving}>
              {saving ? "Saving..." : "Continue"}
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  return <Outlet />;
}
