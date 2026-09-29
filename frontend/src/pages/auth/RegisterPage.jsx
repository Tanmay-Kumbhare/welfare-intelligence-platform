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
import {
  buildFullName,
  calculateAge,
  hasNoErrors,
  validateDob,
  validateEmail,
  validateFirstName,
  validateIncome,
  validateLastName,
  validateMiddleName,
  validateMobile,
} from "../../utils/profileValidation";

export default function RegisterPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    // Name parts — composed into full_name before sending to the API.
    firstName: "",
    middleName: "",
    lastName: "",
    // Account credentials
    email: "",
    password: "",
    // Identity / contact
    date_of_birth: "",
    gender: "",
    citizen_type: "GENERAL",
    mobile_number: "",
    // Demographic
    education_level: "",
    occupation: "",
    family_size: "",
    marital_status: "",
    social_category: "",
    disability_status: "NONE",
    // Financial
    annual_income: "",
    employment_status: "",
    income_source: "",
    poverty_category: "",
    land_holding_size: "",
    is_bpl_card_holder: false,
    is_income_tax_payer: false,
    // Location
    state: "",
    district: "",
    village_city: "",
    area_type: "",
  });

  // Per-field error messages.  null = valid (or untouched).
  const [fieldErrors, setFieldErrors] = useState({});
  // Top-level form-wide error (e.g. API error).
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const update = (next) => setForm((current) => ({ ...current, ...next }));

  // Re-validate a single field on every change and clear the error once valid.
  const touch = (field, validatorFn, value) => {
    const err = validatorFn(value);
    setFieldErrors((current) => ({ ...current, [field]: err }));
  };

  // Derived display-only age from DOB.
  const age = calculateAge(form.date_of_birth);

  const submit = async (event) => {
    event.preventDefault();
    setError("");

    // Validate all fields that need it.
    const errors = {
      firstName: validateFirstName(form.firstName),
      middleName: validateMiddleName(form.middleName),
      lastName: validateLastName(form.lastName),
      email: validateEmail(form.email, { required: true }),
      mobile_number: validateMobile(form.mobile_number),
      date_of_birth: validateDob(form.date_of_birth),
      annual_income: validateIncome(form.annual_income),
    };

    if (!form.password) {
      errors.password = "Password is required.";
    }

    setFieldErrors(errors);

    if (!hasNoErrors(errors)) {
      setError("Please correct the highlighted fields before continuing.");
      return;
    }

    setLoading(true);
    try {
      const fullName = buildFullName(form.firstName, form.middleName, form.lastName);
      const response = await authService.register({
        email: form.email,
        password: form.password,
        citizen: {
          full_name: fullName,
          date_of_birth: form.date_of_birth,
          gender: form.gender || null,
          mobile_number: form.mobile_number || null,
          email_id: form.email,
          citizen_type: form.citizen_type,
          demographic: {
            education_level: form.education_level || null,
            occupation: form.occupation || null,
            family_size: form.family_size ? Number(form.family_size) : undefined,
            marital_status: form.marital_status || null,
            social_category: form.social_category || null,
            disability_status: form.disability_status || "NONE",
            type_specific_metadata: null,
          },
          financial: {
            annual_income: form.annual_income !== "" ? Number(form.annual_income) : undefined,
            employment_status: form.employment_status || null,
            income_source: form.income_source || null,
            poverty_category: form.poverty_category || null,
            land_holding_size: form.land_holding_size ? Number(form.land_holding_size) : undefined,
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
            {/* ── Account credentials ── */}
            <div className="grid md:grid-cols-2 gap-x-5">
              <Input
                id="reg-email"
                label="Email address"
                type="email"
                required
                value={form.email}
                error={fieldErrors.email}
                onChange={(event) => {
                  const v = event.target.value;
                  update({ email: v });
                  touch("email", (val) => validateEmail(val, { required: true }), v);
                }}
                autoComplete="email"
              />
              <PasswordInput
                id="reg-password"
                label="Password"
                required
                value={form.password}
                error={fieldErrors.password}
                onChange={(event) => {
                  const v = event.target.value;
                  update({ password: v });
                  setFieldErrors((cur) => ({ ...cur, password: v ? null : "Password is required." }));
                }}
                autoComplete="new-password"
                hint="Use a password only you know."
              />
            </div>

            {/* ── Identity / name ── */}
            <div className="border-t border-line pt-6">
              <h2 className="text-xl mb-3">Your profile</h2>
              <div className="grid md:grid-cols-3 gap-x-5">
                <Input
                  id="reg-first-name"
                  label="First name"
                  required
                  value={form.firstName}
                  error={fieldErrors.firstName}
                  onChange={(event) => {
                    const v = event.target.value;
                    update({ firstName: v });
                    touch("firstName", validateFirstName, v);
                  }}
                  autoComplete="given-name"
                />
                <Input
                  id="reg-middle-name"
                  label="Middle name"
                  value={form.middleName}
                  error={fieldErrors.middleName}
                  onChange={(event) => {
                    const v = event.target.value;
                    update({ middleName: v });
                    touch("middleName", validateMiddleName, v);
                  }}
                  autoComplete="additional-name"
                />
                <Input
                  id="reg-last-name"
                  label="Last name"
                  required
                  value={form.lastName}
                  error={fieldErrors.lastName}
                  onChange={(event) => {
                    const v = event.target.value;
                    update({ lastName: v });
                    touch("lastName", validateLastName, v);
                  }}
                  autoComplete="family-name"
                />
              </div>

              <div className="grid md:grid-cols-2 gap-x-5">
                <div>
                  <Input
                    id="reg-dob"
                    label="Date of birth"
                    required
                    type="date"
                    max={new Date().toISOString().slice(0, 10)}
                    value={form.date_of_birth}
                    error={fieldErrors.date_of_birth}
                    onChange={(event) => {
                      const v = event.target.value;
                      update({ date_of_birth: v });
                      touch("date_of_birth", validateDob, v);
                    }}
                    autoComplete="bday"
                  />
                  {age !== null && !fieldErrors.date_of_birth && (
                    <p className="text-xs text-ink-soft -mt-3 mb-5">
                      Age: <strong>{age}</strong> years
                    </p>
                  )}
                </div>
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
                  required
                  type="tel"
                  inputMode="numeric"
                  maxLength={10}
                  value={form.mobile_number}
                  error={fieldErrors.mobile_number}
                  onChange={(event) => {
                    // Strip non-digits as the user types.
                    const v = event.target.value.replace(/\D/g, "").slice(0, 10);
                    update({ mobile_number: v });
                    touch("mobile_number", validateMobile, v);
                  }}
                  autoComplete="tel"
                />
                <Input
                  id="reg-email-profile"
                  label="Email (login)"
                  type="email"
                  value={form.email}
                  readOnly
                  className="opacity-70"
                  hint="Filled from the email address above."
                />
              </div>
            </div>

            {/* ── Demographic / Financial / Location ── */}
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
                  min={1}
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
                  min={0}
                  inputMode="numeric"
                  value={form.annual_income}
                  error={fieldErrors.annual_income}
                  onChange={(event) => {
                    const v = event.target.value;
                    update({ annual_income: v });
                    touch("annual_income", validateIncome, v);
                  }}
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
                  min={0}
                  value={form.land_holding_size}
                  onChange={(event) => update({ land_holding_size: event.target.value })}
                />
                <Select
                  id="reg-bpl"
                  label="BPL card holder"
                  value={String(form.is_bpl_card_holder)}
                  onChange={(event) =>
                    update({ is_bpl_card_holder: event.target.value === "true" })
                  }
                >
                  <option value="false">No</option>
                  <option value="true">Yes</option>
                </Select>
                <Select
                  id="reg-tax"
                  label="Income-tax payer"
                  value={String(form.is_income_tax_payer)}
                  onChange={(event) =>
                    update({ is_income_tax_payer: event.target.value === "true" })
                  }
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