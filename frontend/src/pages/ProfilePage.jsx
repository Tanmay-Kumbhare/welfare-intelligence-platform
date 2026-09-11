import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/StatusStates";
import { citizenService } from "../services/api";
import { clearStoredCitizenId, getStoredCitizenId } from "../utils/citizenStorage";

function Row({ label, value }) { return <div className="flex flex-col sm:flex-row sm:justify-between gap-1 py-3 first:pt-0 last:pb-0"><dt className="text-xs text-ink-soft">{label}</dt><dd className="text-sm text-ink sm:text-right">{value === null || value === undefined || value === "" ? "Not provided" : String(value)}</dd></div>; }
function Section({ title, children }) { return <section><h2 className="text-xl mb-3">{title}</h2><Card><dl className="divide-y divide-line">{children}</dl></Card></section>; }

export default function ProfilePage() {
  const navigate = useNavigate();
  const [citizen, setCitizen] = useState(null);
  const [status, setStatus] = useState(() => getStoredCitizenId() ? "loading" : "empty");
  useEffect(() => {
    const id = getStoredCitizenId();
    if (!id) return;
    citizenService.get(id).then((response) => { setCitizen(response.data); setStatus("ready"); }).catch(() => setStatus("error"));
  }, []);
  if (status === "loading") return <LoadingState label="Loading your profile..." />;
  if (status === "error") return <ErrorState title="Unable to load profile" message="We couldn't load your saved citizen profile. Please try again." onRetry={() => window.location.reload()} />;
  if (status === "empty") return <EmptyState title="No citizen profile yet" message="Create a profile to check your eligibility against the active scheme rules." action={<Button to="/check-eligibility">Create profile</Button>} />;
  const demographic = citizen.demographic || {}; const financial = citizen.financial || {}; const location = citizen.location || {};
  const createNew = () => { clearStoredCitizenId(); navigate("/check-eligibility"); };
  return <div><div className="flex flex-wrap items-start justify-between gap-4 mb-8"><div><h1 className="text-[30px] mb-3">My profile</h1><p className="mb-0">Information stored for your citizen record.</p></div><div className="flex flex-wrap gap-2"><Button to="/check-eligibility" size="sm">Check eligibility</Button><Button onClick={createNew} variant="secondary" size="sm">Create a new profile</Button></div></div><div className="space-y-7"><Section title="Personal"><Row label="Full name" value={citizen.full_name} /><Row label="Date of birth" value={citizen.date_of_birth} /><Row label="Gender" value={citizen.gender} /><Row label="Citizen type" value={citizen.citizen_type} /><Row label="Verification status" value={citizen.verification_status} /></Section><Section title="Education / Employment"><Row label="Education level" value={demographic.education_level} /><Row label="Occupation" value={demographic.occupation} /><Row label="Employment status" value={financial.employment_status} /></Section><Section title="Financial"><Row label="Annual income" value={financial.annual_income} /><Row label="Poverty category" value={financial.poverty_category} /><Row label="BPL card holder" value={financial.is_bpl_card_holder ? "Yes" : "No"} /><Row label="Income-tax payer" value={financial.is_income_tax_payer ? "Yes" : "No"} /><Row label="Land holding size" value={financial.land_holding_size ? `${financial.land_holding_size} hectares` : null} /></Section><Section title="Social / Family"><Row label="Social category" value={demographic.social_category} /><Row label="Disability status" value={demographic.disability_status} /><Row label="Family size" value={demographic.family_size} /><Row label="Marital status" value={demographic.marital_status} /></Section><Section title="Location"><Row label="State" value={location.state} /><Row label="District" value={location.district} /><Row label="Village / city" value={location.village_city} /><Row label="Area type" value={location.area_type} /></Section></div><p className="text-xs text-ink-soft mt-7">The current backend supports profile creation and retrieval, but not editing an existing citizen record. “Create a new profile” starts a separate record; it does not delete this one.</p></div>;
}
