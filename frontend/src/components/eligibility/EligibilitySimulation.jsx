import { useState } from "react";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import Card from "../ui/Card";
import Input from "../ui/Input";
import Select from "../ui/Select";
import { eligibilityService } from "../../services/api";
import { Sparkles, ArrowRight, CheckCircle, XCircle, AlertCircle, RefreshCw } from "lucide-react";
import { categoryLabel } from "../../utils/ruleFormat";

/**
 * Citizen-facing What-If Eligibility Simulation component.
 * Allows citizens to test hypothetical profile overrides against welfare schemes,
 * comparing baseline eligibility and match scores with simulated outcomes.
 *
 * Supported backend SimulationInput attributes:
 * - annual_income (number)
 * - land_holding_size (number)
 * - is_income_tax_payer (boolean)
 * - is_bpl_card_holder (boolean)
 * - employment_status (string)
 * - poverty_category (string)
 * - age (number)
 * - gender (string)
 * - citizen_type (string)
 * - social_category (string)
 * - education_level (string)
 * - disability_status (string)
 * - state (string)
 * - area_type (string)
 */
export default function EligibilitySimulation({ citizenId, className = "" }) {
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  // Form input state (string representations)
  const [form, setForm] = useState({
    annual_income: "",
    land_holding_size: "",
    is_income_tax_payer: "",
    is_bpl_card_holder: "",
    employment_status: "",
    poverty_category: "",
    age: "",
    gender: "",
    citizen_type: "",
    social_category: "",
    education_level: "",
    disability_status: "",
    state: "",
    area_type: "",
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleReset = () => {
    setForm({
      annual_income: "",
      land_holding_size: "",
      is_income_tax_payer: "",
      is_bpl_card_holder: "",
      employment_status: "",
      poverty_category: "",
      age: "",
      gender: "",
      citizen_type: "",
      social_category: "",
      education_level: "",
      disability_status: "",
      state: "",
      area_type: "",
    });
    setResult(null);
    setError(null);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!citizenId) {
      setError("Citizen profile ID is required to simulate eligibility.");
      return;
    }

    // Build payload with only non-empty fields and correct types
    const payload = {};

    if (form.annual_income.trim() !== "") {
      const val = parseFloat(form.annual_income);
      if (!Number.isNaN(val) && val >= 0) payload.annual_income = val;
    }
    if (form.land_holding_size.trim() !== "") {
      const val = parseFloat(form.land_holding_size);
      if (!Number.isNaN(val) && val >= 0) payload.land_holding_size = val;
    }
    if (form.age.trim() !== "") {
      const val = parseInt(form.age, 10);
      if (!Number.isNaN(val) && val >= 0) payload.age = val;
    }

    if (form.is_income_tax_payer !== "") {
      payload.is_income_tax_payer = form.is_income_tax_payer === "true";
    }
    if (form.is_bpl_card_holder !== "") {
      payload.is_bpl_card_holder = form.is_bpl_card_holder === "true";
    }

    if (form.gender.trim() !== "") payload.gender = form.gender.trim();
    if (form.citizen_type.trim() !== "") payload.citizen_type = form.citizen_type.trim();
    if (form.social_category.trim() !== "") payload.social_category = form.social_category.trim();
    if (form.education_level.trim() !== "") payload.education_level = form.education_level.trim();
    if (form.disability_status.trim() !== "") payload.disability_status = form.disability_status.trim();
    if (form.employment_status.trim() !== "") payload.employment_status = form.employment_status.trim();
    if (form.poverty_category.trim() !== "") payload.poverty_category = form.poverty_category.trim();
    if (form.area_type.trim() !== "") payload.area_type = form.area_type.trim();
    if (form.state.trim() !== "") payload.state = form.state.trim();

    if (Object.keys(payload).length === 0) {
      setError("Please specify at least one hypothetical profile attribute to simulate.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await eligibilityService.simulate(citizenId, payload);
      setResult(res.data);
    } catch (err) {
      setError(
        err?.response?.data?.detail ||
          err?.message ||
          "Simulation request failed. Please check your inputs and try again."
      );
    } finally {
      setLoading(false);
    }
  };

  const getOutcomeBadge = (change) => {
    switch (change) {
      case "BECAME_ELIGIBLE":
        return <Badge variant="ok">Newly Eligible</Badge>;
      case "BECAME_INELIGIBLE":
        return <Badge variant="excl">Newly Ineligible</Badge>;
      case "SCORE_IMPROVED":
        return <Badge variant="neutral">Score Improved</Badge>;
      case "SCORE_DECREASED":
        return <Badge variant="excl">Score Decreased</Badge>;
      default:
        return <Badge variant="neutral">Unchanged</Badge>;
    }
  };

  return (
    <Card className={`border-accent/30 bg-paper-raised ${className}`}>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-4 mb-4">
        <div>
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-accent" aria-hidden="true" />
            <h3 className="text-xl font-semibold text-ink mb-0">What-If Eligibility Simulation</h3>
          </div>
          <p className="text-xs text-ink-soft mt-1 mb-0">
            Explore how hypothetical profile changes would affect your eligibility without saving anything to your real profile.
          </p>
        </div>
        <Button
          type="button"
          variant={isOpen ? "ghost" : "secondary"}
          size="sm"
          onClick={() => setIsOpen((prev) => !prev)}
        >
          {isOpen ? "Close Simulation" : "Open Simulation"}
        </Button>
      </div>

      {isOpen && (
        <div>
          {/* Non-guarantee disclaimer */}
          <div className="mb-6 p-3 bg-paper rounded border border-line text-xs text-ink-soft">
            <p className="mb-0 leading-relaxed font-sans">
              <strong>Note:</strong> What-If simulation results are purely hypothetical and do not alter your registered citizen profile, official records, or guarantee government scheme approval or grant disbursement.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="mb-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
              <Input
                label="Annual Family Income (₹)"
                id="sim-annual-income"
                name="annual_income"
                type="number"
                min="0"
                step="1000"
                placeholder="e.g. 200000"
                value={form.annual_income}
                onChange={handleChange}
              />
              <Input
                label="Land Holding Size (Hectares)"
                id="sim-land-holding"
                name="land_holding_size"
                type="number"
                min="0"
                step="0.1"
                placeholder="e.g. 1.5"
                value={form.land_holding_size}
                onChange={handleChange}
              />
              <Input
                label="Age (Years)"
                id="sim-age"
                name="age"
                type="number"
                min="0"
                max="150"
                placeholder="e.g. 25"
                value={form.age}
                onChange={handleChange}
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
              <Select
                label="Citizen Type / Primary Role"
                id="sim-citizen-type"
                name="citizen_type"
                value={form.citizen_type}
                onChange={handleChange}
              >
                <option value="">Keep current profile value</option>
                <option value="FARMER">Farmer</option>
                <option value="STUDENT">Student</option>
                <option value="SENIOR">Senior Citizen</option>
                <option value="GENERAL">General Citizen</option>
              </Select>

              <Select
                label="Income Tax Payer"
                id="sim-tax-payer"
                name="is_income_tax_payer"
                value={form.is_income_tax_payer}
                onChange={handleChange}
              >
                <option value="">Keep current profile value</option>
                <option value="false">No (Non-tax payer)</option>
                <option value="true">Yes (Tax payer)</option>
              </Select>

              <Select
                label="BPL Card Holder"
                id="sim-bpl-card"
                name="is_bpl_card_holder"
                value={form.is_bpl_card_holder}
                onChange={handleChange}
              >
                <option value="">Keep current profile value</option>
                <option value="true">Yes (BPL Card Holder)</option>
                <option value="false">No (Not a BPL Card Holder)</option>
              </Select>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
              <Select
                label="Employment Status"
                id="sim-employment"
                name="employment_status"
                value={form.employment_status}
                onChange={handleChange}
              >
                <option value="">Keep current profile value</option>
                <option value="UNEMPLOYED">Unemployed</option>
                <option value="EMPLOYED">Employed</option>
                <option value="SELF_EMPLOYED">Self-employed</option>
                <option value="RETIRED">Retired</option>
              </Select>

              <Select
                label="Social Category"
                id="sim-social-category"
                name="social_category"
                value={form.social_category}
                onChange={handleChange}
              >
                <option value="">Keep current profile value</option>
                <option value="GEN">General</option>
                <option value="OBC">OBC</option>
                <option value="SC">SC</option>
                <option value="ST">ST</option>
              </Select>

              <Select
                label="Area Type"
                id="sim-area-type"
                name="area_type"
                value={form.area_type}
                onChange={handleChange}
              >
                <option value="">Keep current profile value</option>
                <option value="RURAL">Rural</option>
                <option value="URBAN">Urban</option>
                <option value="SEMI_URBAN">Semi-Urban</option>
              </Select>
            </div>

            {error && (
              <div className="mb-4 p-3 bg-excl-tint text-excl-ink rounded border border-excl-ink/20 text-xs flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span>{error}</span>
              </div>
            )}

            <div className="flex flex-wrap items-center gap-3">
              <Button type="submit" variant="primary" size="sm" disabled={loading}>
                {loading ? "Simulating..." : "Run Simulation"}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={handleReset}
                disabled={loading}
              >
                <RefreshCw className="h-3.5 w-3.5 inline mr-1" aria-hidden="true" />
                Reset Overrides
              </Button>
            </div>
          </form>

          {/* Results Comparison View */}
          {result && (
            <div className="border-t border-line pt-6 mt-6">
              <div className="flex flex-wrap items-baseline justify-between gap-2 mb-4">
                <h4 className="text-lg font-semibold text-ink mb-0">Simulation Comparison</h4>
                <span className="text-xs text-ink-soft font-mono">
                  {result.total_schemes_evaluated} schemes evaluated
                </span>
              </div>

              {/* Summary Cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
                <div className="p-3 bg-paper rounded border border-line">
                  <span className="text-xs text-ink-soft block mb-1">Newly Eligible</span>
                  <span className="text-xl font-bold text-ok-ink">
                    +{result.newly_eligible_count}
                  </span>
                </div>
                <div className="p-3 bg-paper rounded border border-line">
                  <span className="text-xs text-ink-soft block mb-1">Newly Ineligible</span>
                  <span className="text-xl font-bold text-excl-ink">
                    -{result.newly_ineligible_count}
                  </span>
                </div>
                <div className="p-3 bg-paper rounded border border-line">
                  <span className="text-xs text-ink-soft block mb-1">Unaltered Eligible</span>
                  <span className="text-xl font-bold text-ink">
                    {result.unaltered_eligible_count}
                  </span>
                </div>
                <div className="p-3 bg-paper rounded border border-line">
                  <span className="text-xs text-ink-soft block mb-1">Improved Score</span>
                  <span className="text-xl font-bold text-accent-ink">
                    {result.improved_score_count}
                  </span>
                </div>
              </div>

              {result.overall_summary && (
                <p className="text-xs text-ink mb-5 leading-relaxed font-sans bg-paper p-3 rounded border border-line">
                  {result.overall_summary}
                </p>
              )}

              {/* Scheme List with Deltas */}
              <div className="space-y-3">
                {result.simulated_schemes &&
                  result.simulated_schemes.map((scheme) => {
                    const bScore =
                      scheme.baseline_match_score !== null && scheme.baseline_match_score !== undefined
                        ? Math.round(Number(scheme.baseline_match_score))
                        : null;
                    const sScore =
                      scheme.simulated_match_score !== null && scheme.simulated_match_score !== undefined
                        ? Math.round(Number(scheme.simulated_match_score))
                        : null;

                    return (
                      <div
                        key={scheme.scheme_id}
                        className="p-3.5 bg-paper rounded border border-line text-xs"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
                          <div>
                            <div className="flex flex-wrap items-center gap-2 mb-1">
                              <h5 className="text-sm font-semibold text-ink mb-0">
                                {scheme.scheme_name}
                              </h5>
                              {getOutcomeBadge(scheme.outcome_change)}
                            </div>
                            <div className="flex flex-wrap items-center gap-2 text-[11px] text-ink-soft">
                              {scheme.scheme_category && (
                                <Badge variant="neutral" pill>
                                  {categoryLabel(scheme.scheme_category)}
                                </Badge>
                              )}
                              {scheme.department_name && <span>{scheme.department_name}</span>}
                            </div>
                          </div>

                          {/* Side-by-side status */}
                          <div className="flex items-center gap-4 bg-paper-raised px-3 py-1.5 rounded border border-line text-xs">
                            <div className="text-center">
                              <span className="text-[10px] text-ink-soft block">Baseline</span>
                              <span
                                className={`font-semibold inline-flex items-center gap-1 ${
                                  scheme.baseline_eligible ? "text-ok-ink" : "text-excl-ink"
                                }`}
                              >
                                {scheme.baseline_eligible ? (
                                  <CheckCircle className="h-3.5 w-3.5 text-ok" />
                                ) : (
                                  <XCircle className="h-3.5 w-3.5 text-excl" />
                                )}
                                {scheme.baseline_eligible ? "Eligible" : "Ineligible"}
                              </span>
                              {bScore !== null && (
                                <span className="text-[10px] text-ink-soft block font-mono">
                                  {bScore}%
                                </span>
                              )}
                            </div>

                            <ArrowRight className="h-4 w-4 text-ink-soft/60" aria-hidden="true" />

                            <div className="text-center">
                              <span className="text-[10px] text-ink-soft block">Simulated</span>
                              <span
                                className={`font-semibold inline-flex items-center gap-1 ${
                                  scheme.simulated_eligible ? "text-ok-ink" : "text-excl-ink"
                                }`}
                              >
                                {scheme.simulated_eligible ? (
                                  <CheckCircle className="h-3.5 w-3.5 text-ok" />
                                ) : (
                                  <XCircle className="h-3.5 w-3.5 text-excl" />
                                )}
                                {scheme.simulated_eligible ? "Eligible" : "Ineligible"}
                              </span>
                              {sScore !== null && (
                                <span className="text-[10px] text-ink-soft block font-mono">
                                  {sScore}%
                                </span>
                              )}
                            </div>
                          </div>
                        </div>

                        {scheme.summary_explanation && (
                          <p className="text-xs text-ink-soft mb-2 leading-relaxed">
                            {scheme.summary_explanation}
                          </p>
                        )}

                        {/* Condition Deltas if any */}
                        {scheme.changed_conditions && scheme.changed_conditions.length > 0 && (
                          <div className="mt-2 pt-2 border-t border-line/60">
                            <span className="text-[11px] font-medium text-ink block mb-1">
                              Changed Conditions:
                            </span>
                            <div className="space-y-1.5">
                              {scheme.changed_conditions.map((delta, dIdx) => (
                                <div
                                  key={`${delta.parameter}-${dIdx}`}
                                  className="text-[11px] bg-paper-raised p-2 rounded border border-line/80 flex flex-wrap items-center justify-between gap-2"
                                >
                                  <div>
                                    <span className="font-medium text-ink">
                                      {delta.parameter_label || delta.parameter}:
                                    </span>
                                    <span className="text-ink-soft ml-1">
                                      {delta.baseline_value ?? "Not provided"} →{" "}
                                      <strong className="text-ink">
                                        {delta.simulated_value ?? "Not provided"}
                                      </strong>
                                    </span>
                                  </div>
                                  <Badge
                                    variant={
                                      delta.status === "IMPROVED"
                                        ? "ok"
                                        : delta.status === "WORSENED"
                                        ? "excl"
                                        : "neutral"
                                    }
                                  >
                                    {delta.status}
                                  </Badge>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
