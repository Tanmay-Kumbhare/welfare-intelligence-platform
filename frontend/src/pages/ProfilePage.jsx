import { useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { citizenService, eligibilityService } from "../services/api";

export default function ProfilePage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const citizenType = searchParams.get("type") || "GENERAL";
  const [loading, setLoading] = useState(false);

  // Simplified form state for prototype
  const [formData, setFormData] = useState({
    full_name: "",
    date_of_birth: "",
    gender: "MALE",
    mobile_number: "",
    email_id: "",
    citizen_type: citizenType,
    demographic: {
      education_level: "PRIMARY",
      social_category: "GEN",
      disability_status: "NONE",
      family_size: 4
    },
    financial: {
      annual_income: 0,
      poverty_category: "APL",
      employment_status: citizenType === "STUDENT" ? "STUDENT" : "EMPLOYED",
      land_holding_size: 0,
      is_bpl_card_holder: false,
      is_income_tax_payer: false
    },
    location: {
      state: "Maharashtra",
      district: "Pune",
      area_type: "URBAN"
    }
  });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      // 1. Register citizen
      const { data: citizen } = await citizenService.register(formData);
      // 2. Evaluate eligibility
      await eligibilityService.evaluate(citizen.citizen_id);
      // 3. Navigate to results
      navigate(`/results/${citizen.citizen_id}`);
    } catch (error) {
      console.error(error);
      alert("Failed to submit profile");
    } finally {
      setLoading(false);
    }
  };

  const updateField = (section, field, value) => {
    if (section) {
      setFormData(prev => ({
        ...prev,
        [section]: { ...prev[section], [field]: value }
      }));
    } else {
      setFormData(prev => ({ ...prev, [field]: value }));
    }
  };

  return (
    <div className="max-w-4xl mx-auto py-8">
      <h2 className="text-2xl font-bold mb-6">Complete Your Profile ({citizenType})</h2>
      <form onSubmit={handleSubmit} className="space-y-8 bg-white p-8 shadow rounded-lg">
        
        {/* Basic Info */}
        <section>
          <h3 className="text-lg font-medium border-b pb-2 mb-4">Basic Information</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium">Full Name</label>
              <input required type="text" className="mt-1 block w-full border rounded-md p-2" value={formData.full_name} onChange={e => updateField(null, "full_name", e.target.value)} />
            </div>
            <div>
              <label className="block text-sm font-medium">Date of Birth</label>
              <input required type="date" className="mt-1 block w-full border rounded-md p-2" value={formData.date_of_birth} onChange={e => updateField(null, "date_of_birth", e.target.value)} />
            </div>
            <div>
              <label className="block text-sm font-medium">Gender</label>
              <select className="mt-1 block w-full border rounded-md p-2" value={formData.gender} onChange={e => updateField(null, "gender", e.target.value)}>
                <option value="MALE">Male</option>
                <option value="FEMALE">Female</option>
                <option value="OTHER">Other</option>
              </select>
            </div>
          </div>
        </section>

        {/* Demographic & Financial */}
        <section>
          <h3 className="text-lg font-medium border-b pb-2 mb-4">Socio-Economic Details</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium">Social Category</label>
              <select className="mt-1 block w-full border rounded-md p-2" value={formData.demographic.social_category} onChange={e => updateField("demographic", "social_category", e.target.value)}>
                <option value="GEN">General</option>
                <option value="OBC">OBC</option>
                <option value="SC">SC</option>
                <option value="ST">ST</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium">Poverty Category</label>
              <select className="mt-1 block w-full border rounded-md p-2" value={formData.financial.poverty_category} onChange={e => {
                updateField("financial", "poverty_category", e.target.value);
                updateField("financial", "is_bpl_card_holder", e.target.value !== "APL");
              }}>
                <option value="APL">APL (Above Poverty Line)</option>
                <option value="BPL">BPL (Below Poverty Line)</option>
                <option value="AAY">AAY (Antyodaya Anna Yojana)</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium">Annual Income (₹)</label>
              <input type="number" min="0" className="mt-1 block w-full border rounded-md p-2" value={formData.financial.annual_income} onChange={e => updateField("financial", "annual_income", parseFloat(e.target.value))} />
            </div>
            <div>
              <label className="block text-sm font-medium">Area Type</label>
              <select className="mt-1 block w-full border rounded-md p-2" value={formData.location.area_type} onChange={e => updateField("location", "area_type", e.target.value)}>
                <option value="URBAN">Urban</option>
                <option value="RURAL">Rural</option>
                <option value="SEMI_URBAN">Semi-Urban</option>
              </select>
            </div>
          </div>
        </section>

        {/* Type Specific */}
        {citizenType === "FARMER" && (
          <section>
            <h3 className="text-lg font-medium border-b pb-2 mb-4 text-green-700">Farmer Specific Details</h3>
            <div className="grid grid-cols-1 gap-4">
              <div>
                <label className="block text-sm font-medium">Land Holding Size (Hectares)</label>
                <input type="number" step="0.1" min="0" className="mt-1 block w-full border rounded-md p-2" value={formData.financial.land_holding_size} onChange={e => updateField("financial", "land_holding_size", parseFloat(e.target.value))} />
              </div>
              <div className="flex items-center">
                <input type="checkbox" id="tax" className="h-4 w-4" checked={formData.financial.is_income_tax_payer} onChange={e => updateField("financial", "is_income_tax_payer", e.target.checked)} />
                <label htmlFor="tax" className="ml-2 block text-sm">I pay income tax</label>
              </div>
            </div>
          </section>
        )}

        {citizenType === "STUDENT" && (
          <section>
            <h3 className="text-lg font-medium border-b pb-2 mb-4 text-blue-700">Student Specific Details</h3>
            <div className="grid grid-cols-1 gap-4">
              <div>
                <label className="block text-sm font-medium">Current Education Level</label>
                <select className="mt-1 block w-full border rounded-md p-2" value={formData.demographic.education_level} onChange={e => updateField("demographic", "education_level", e.target.value)}>
                  <option value="PRIMARY">Primary</option>
                  <option value="SECONDARY">Secondary (10th)</option>
                  <option value="HIGHER_SECONDARY">Higher Secondary (12th)</option>
                  <option value="GRADUATE">Graduate</option>
                  <option value="POST_GRADUATE">Post Graduate</option>
                </select>
              </div>
            </div>
          </section>
        )}

        <div className="flex justify-end pt-4">
          <button type="submit" disabled={loading} className="bg-blue-600 text-white px-6 py-2 rounded shadow hover:bg-blue-700 disabled:opacity-50">
            {loading ? "Processing..." : "Find Schemes"}
          </button>
        </div>
      </form>
    </div>
  );
}
