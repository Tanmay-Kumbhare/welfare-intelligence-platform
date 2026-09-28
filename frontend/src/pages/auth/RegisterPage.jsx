import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import Button from "../../components/ui/Button";
import Input from "../../components/ui/Input";
import PasswordInput from "../../components/ui/PasswordInput";
import { extractApiErrorMessage } from "../../utils/apiError";
import Select from "../../components/ui/Select";
import Card from "../../components/ui/Card";
import { ErrorState } from "../../components/ui/StatusStates";
import { authService } from "../../services/api";
import { saveToken, saveUser } from "../../services/auth";

const TODAY = new Date().toISOString().slice(0, 10);

export default function RegisterPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    email: "",
    password: "",
    full_name: "",
    date_of_birth: "",
    gender: "",
    citizen_type: "GENERAL",
    mobile_number: "",
    education_level: "",
    occupation: "",
    family_size: "",
    marital_status: "",
    social_category: "",
    disability_status: "NONE",
    annual_income: "",
    employment_status: "",
    income_source: "",
    poverty_category: "",
    land_holding_size: "",
    is_bpl_card_holder: false,
    is_income_tax_payer: false,
    state: "",
    district: "",
    village_city: "",
    area_type: "",
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const update = (next) => setForm((current) => ({ ...current, ...next }));

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    if (!form.email || !form.password || !form.full_name || !form.date_of_birth) {
      setError("Please enter your email, password, full name and date of birth.");
      return;
    }
    if (form.date_of_birth >= TODAY) {
      setError("Date of birth must be in the past.");
      return;
    }
    setLoading(true);
    try {
      const response = await authService.register({
        email: form.email,
        password: form.password,
        citizen: {
          full_name: form.full_name.trim(),
          date_of_birth: form.date_of_birth,
          gender: form.gender || null,
          mobile_number: form.mobile_number || null,
          email_id: form.email,
          citizen_type: form.citizen_type,
          demographic: {
            education_level: form.education_level || null,
            occupation: form.occupation || null,
            family_size: form.family_size
              ? Number(form.family_size)
              : undefined,
            marital_status: form.marital_status || null,
            social_category: form.social_category || null,
            disability_status: form.disability_status || "NONE",
            type_specific_metadata: null,
          },
          financial: {
            annual_income: form.annual_income
              ? Number(form.annual_income)
              : undefined,
            employment_status: form.employment_status || null,
            income_source: form.income_source || null,
            poverty_category: form.poverty_category || null,
            land_holding_size: form.land_holding_size
              ? Number(form.land_holding_size)
              : undefined,
            is_bpl_card_holder: Boolean(form.is_bpl_card_holder),
            is_income_tax_payer: Boolean(form.is_income_tax_payer),
          },
          location: {
            state: form.state || null,
            district: form.district || null,
            village_city: form.village_city || null,
            area_type: form.area_type || null,
          },
        },
      });

      const { token, user_id, email: loggedInEmail, roles } = response.data;
      saveToken(token);
      saveUser({ user_id, email: loggedInEmail, roles: roles || [] });
      navigate("/profile");
      return;
    } catch (requestError) {
      setError(
        extractApiErrorMessage(
          requestError,
          "We could not create your account. Please try again."
        )
      );
      return;
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="mb-9 border-b border-line pb-7">
        <h1 className="text-[30px] mb-3">Create your account</h1>
        <p className="max-w-[56ch]">
          Create an account to save your profile, check your eligibility, and
          see your results later. Your email and password let you sign back in.
        </p>
      </div>

      <Card>
        <div className="max-w-[560px] mx-auto">
          <form onSubmit={submit} noValidate className="space-y-7">
            <div className="grid md:grid-cols-2 gap-x-5">
              <Input
                id="reg-email"
                label="Email address"
                type="email"
                required
                value={form.email}
                onChange={(event) => update({ email: event.target.value })}
                autoComplete="email"
              />
              <PasswordInput
                id="reg-password"
                label="Password"
                required
                value={form.password}
                onChange={(event) => update({ password: event.target.value })}
                autoComplete="new-password"
                hint="Use a password only you know."
              />
            </div>

            <div className="border-t border-line pt-6">
              <h2 className="text-xl mb-3">Your profile</h2>
              <div className="grid md:grid-cols-2 gap-x-5">
                <Input
                  id="reg-name"
                  label="Full name"
                  required
                  value={form.full_name}
                  onChange={(event) => update({ full_name: event.target.value })}
                  autoComplete="name"
                />
                <Input
                  id="reg-dob"
                  label="Date of birth"
                  required
                  type="date"
                  max={TODAY}
                  value={form.date_of_birth}
                  onChange={(event) => update({ date_of_birth: event.target.value })}
                  autoComplete="bday"
                />
                <Select
                  id="reg-gender"
                  label="Gender"
                  value={form.gender}
                  onChange={(event) => update({ gender: event.target.value })}
                >
                  <option value="">Prefer not to say</option>
                  <option value="MALE">Male</option>
                  <option value="FEMALE">Female</option>
                  <option value="OTHER">Other</option>
                </Select>
                <Select
                  id="reg-type"
                  label="Citizen type"
                  value={form.citizen_type}
                  onChange={(event) => update({ citizen_type: event.target.value })}
                >
                  <option value="GENERAL">General</option>
                  <option value="STUDENT">Student</option>
                  <option value="FARMER">Farmer</option>
                  <option value="SENIOR">Senior</option>
                </Select>
                <Input
                  id="reg-mobile"
                  label="Mobile number"
                  value={form.mobile_number}
                  onChange={(event) => update({ mobile_number: event.target.value })}
                  autoComplete="tel"
                />
                <Input
                  id="reg-email-profile"
                  label="Email"
                  type="email"
                  value={form.email}
                  onChange={(event) => update({ email: event.target.value })}
                  readOnly
                  className="opacity-70"
                />
              </div>
            </div>

            <div className="border-t border-line pt-6">
              <h2 className="text-xl mb-3">Details you want to share</h2>
              <div className="grid md:grid-cols-2 gap-x-5">
                <Input
                  id="reg-edu"
                  label="Education level"
                  value={form.education_level}
                  onChange={(event) => update({ education_level: event.target.value })}
                />
                <Input
                  id="reg-occupation"
                  label="Occupation"
                  value={form.occupation}
                  onChange={(event) => update({ occupation: event.target.value })}
                />
                <Input
                  id="reg-family-size"
                  label="Family size"
                  type="number"
                  value={form.family_size}
                  onChange={(event) => update({ family_size: event.target.value })}
                />
                <Select
                  id="reg-marital"
                  label="Marital status"
                  value={form.marital_status}
                  onChange={(event) => update({ marital_status: event.target.value })}
                >
                  <option value="">Prefer not to say</option>
                  <option value="SINGLE">Single</option>
                  <option value="MARRIED">Married</option>
                  <option value="WIDOWED">Widowed</option>
                  <option value="DIVORCED">Divorced</option>
                </Select>
                <Select
                  id="reg-social"
                  label="Social category"
                  value={form.social_category}
                  onChange={(event) => update({ social_category: event.target.value })}
                >
                  <option value="">Prefer not to say</option>
                  <option value="GEN">General</option>
                  <option value="OBC">OBC</option>
                  <option value="SC">SC</option>
                  <option value="ST">ST</option>
                </Select>
                <Select
                  id="reg-disability"
                  label="Disability status"
                  value={form.disability_status}
                  onChange={(event) => update({ disability_status: event.target.value })}
                >
                  <option value="NONE">None</option>
                  <option value="PHYSICALLY_DISABLED">Physically disabled</option>
                  <option value="VISUALLY_IMPAIRED">Visually impaired</option>
                  <option value="HEARING_IMPAIRED">Hearing impaired</option>
                  <option value="OTHER">Other</option>
                </Select>
                <Input
                  id="reg-income"
                  label="Annual income (₹)"
                  type="number"
                  value={form.annual_income}
                  onChange={(event) => update({ annual_income: event.target.value })}
                />
                <Select
                  id="reg-emp"
                  label="Employment status"
                  value={form.employment_status}
                  onChange={(event) => update({ employment_status: event.target.value })}
                >
                  <option value="">Prefer not to say</option>
                  <option value="EMPLOYED">Employed</option>
                  <option value="UNEMPLOYED">Unemployed</option>
                  <option value="SELF_EMPLOYED">Self-employed</option>
                  <option value="FARMER">Farmer</option>
                  <option value="STUDENT">Student</option>
                  <option value="RETIRED">Retired</option>
                </Select>
                <Input
                  id="reg-income-source"
                  label="Income source"
                  value={form.income_source}
                  onChange={(event) => update({ income_source: event.target.value })}
                />
                <Select
                  id="reg-poverty"
                  label="Poverty category"
                  value={form.poverty_category}
                  onChange={(event) => update({ poverty_category: event.target.value })}
                >
                  <option value="">Prefer not to say</option>
                  <option value="APL">APL</option>
                  <option value="BPL">BPL</option>
                  <option value="AAY">AAY</option>
                </Select>
                <Input
                  id="reg-land"
                  label="Land holding size (hectares)"
                  type="number"
                  value={form.land_holding_size}
                  onChange={(event) => update({ land_holding_size: event.target.value })}
                />
                <Select
                  id="reg-bpl"
                  label="BPL card holder"
                  value={String(form.is_bpl_card_holder)}
                  onChange={(event) => update({ is_bpl_card_holder: event.target.value === "true" })}
                >
                  <option value="false">No</option>
                  <option value="true">Yes</option>
                </Select>
                <Select
                  id="reg-tax"
                  label="Income-tax payer"
                  value={String(form.is_income_tax_payer)}
                  onChange={(event) => update({ is_income_tax_payer: event.target.value === "true" })}
                >
                  <option value="false">No</option>
                  <option value="true">Yes</option>
                </Select>
                <Input
                  id="reg-state"
                  label="State"
                  value={form.state}
                  onChange={(event) => update({ state: event.target.value })}
                />
                <Input
                  id="reg-district"
                  label="District"
                  value={form.district}
                  onChange={(event) => update({ district: event.target.value })}
                />
                <Input
                  id="reg-village"
                  label="Village / city"
                  value={form.village_city}
                  onChange={(event) => update({ village_city: event.target.value })}
                />
                <Select
                  id="reg-area"
                  label="Area type"
                  value={form.area_type}
                  onChange={(event) => update({ area_type: event.target.value })}
                >
                  <option value="">Prefer not to say</option>
                  <option value="RURAL">Rural</option>
                  <option value="URBAN">Urban</option>
                  <option value="SEMI_URBAN">Semi-Urban</option>
                </Select>
              </div>
            </div>

            {error && (
              <div className="text-[13px] text-excl-ink bg-excl-tint border border-excl-tint rounded-sm px-3 py-2">
                {error}
              </div>
            )}

            <div className="flex justify-end gap-3 pt-2">
              <Link to="/login" className="text-sm text-ink-soft hover:text-ink">
                Already have an account? Sign in
              </Link>
              <Button type="submit" disabled={loading}>
                {loading ? "Creating account..." : "Create account and continue"}
              </Button>
            </div>
          </form>
        </div>
      </Card>

      <p className="mt-8 text-center text-xs text-ink-soft">
        You can edit this information later from your profile page.
      </p>
    </div>
  );
}
