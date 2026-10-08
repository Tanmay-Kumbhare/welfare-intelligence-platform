import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import Input from "../components/ui/Input";
import Select from "../components/ui/Select";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/StatusStates";
import { authService, citizenService, formService } from "../services/api";
import { clearAuth } from "../services/auth";
import { extractApiErrorMessage } from "../utils/apiError";
import {
  AREA_TYPE_OPTIONS,
  CITIZEN_TYPE_OPTIONS,
  CURRENT_YEAR_OPTIONS,
  DISABILITY_STATUS_OPTIONS,
  DISABILITY_TYPE_OPTIONS,
  EDUCATION_LEVEL_OPTIONS,
  EMPLOYMENT_STATUS_OPTIONS,
  GENDER_OPTIONS,
  HSC_STREAM_OPTIONS,
  INCOME_SOURCE_OPTIONS,
  INDIAN_STATES,
  INDIAN_STATES_DISTRICTS,
  MARITAL_STATUS_OPTIONS,
  PG_DEGREE_OPTIONS,
  POVERTY_CATEGORY_OPTIONS,
  PROFILE_TYPE_OPTIONS,
  RESULT_STATUS_OPTIONS,
  SOCIAL_CATEGORIES,
  SSC_BOARD_OPTIONS,
  UG_DEGREE_OPTIONS,
  WIZARD_STEPS,
} from "../utils/profileData";
import {
  buildFullName,
  calculateAge,
  hasNoErrors,
  splitFullName,
  validateDob,
  validateFirstName,
  validateIncome,
  validateLastName,
  validateMiddleName,
  validateMobile,
  validatePincode,
} from "../utils/profileValidation";

const FORM_CODE = "GENERAL_CITIZEN_PROFILE";

function Row({ label, value }) {
  return (
    <div className="flex flex-col sm:flex-row sm:justify-between gap-1 py-3 first:pt-0 last:pb-0">
      <dt className="text-xs font-medium text-ink-soft">{label}</dt>
      <dd className="text-sm text-ink sm:text-right font-medium">
        {value === null || value === undefined || value === "" ? (
          <span className="text-ink-soft/60 font-normal italic">Not provided</span>
        ) : (
          String(value)
        )}
      </dd>
    </div>
  );
}

function Section({ title, onEdit, children }) {
  return (
    <section>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">{title}</h2>
        {onEdit && (
          <Button size="sm" variant="secondary" onClick={onEdit}>
            Edit
          </Button>
        )}
      </div>
      <Card>
        <dl className="divide-y divide-line">{children}</dl>
      </Card>
    </section>
  );
}

function formatEducationLevel(level) {
  const match = EDUCATION_LEVEL_OPTIONS.find((o) => o.value === level);
  return match ? match.label : level;
}

function formatOption(options, value) {
  if (!value) return "Not provided";
  const match = options.find((o) => o.value === value);
  return match ? match.label : value;
}

function formatAnswer(value) {
  if (value === null || value === undefined || value === "") return "Not provided";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) {
    return value
      .map((item) =>
        typeof item === "object" && item !== null
          ? [item.name, item.relationship].filter(Boolean).join(" · ") || "Item"
          : String(item)
      )
      .join(", ");
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function initProfileState(citizen = {}, authenticatedEmail = "") {
  const { firstName, middleName, lastName } = splitFullName(citizen.full_name || "");
  const meta = citizen.demographic?.type_specific_metadata || {};
  const loc = citizen.location || {};
  const curAddr = loc.current_address || {};

  return {
    firstName,
    middleName,
    lastName,
    date_of_birth: citizen.date_of_birth || "",
    gender: citizen.gender || "",
    mobile_number: citizen.mobile_number || "",
    // Authenticated email takes precedence; immutable from citizen profile UI
    email_id: authenticatedEmail || citizen.email_id || "",
    citizen_type: citizen.citizen_type || "GENERAL",
    profile_types: Array.isArray(citizen.profile_types) ? citizen.profile_types : [],
    demographic: {
      education_level: citizen.demographic?.education_level || "",
      occupation: citizen.demographic?.occupation || "",
      other_occupation: meta.other_occupation || "",
      family_size: citizen.demographic?.family_size ?? null,
      marital_status: citizen.demographic?.marital_status || "",
      social_category: citizen.demographic?.social_category || "",
      other_social_category: meta.other_social_category || "",
      disability_status: citizen.demographic?.disability_status || "NONE",
      disability_type: meta.disability_type || "",
      disability_percentage: meta.disability_percentage || null,
      udid_number: meta.udid_number || "",
      student_hostel_status: meta.student_hostel_status || "",
      student_admission_quota: meta.student_admission_quota || "",
      farmer_category: meta.farmer_category || "",
      farmer_irrigation_type: meta.farmer_irrigation_type || "",
      farmer_crop_types: meta.farmer_crop_types || "",
      business_nature: meta.business_nature || "",
      business_msme_registered: meta.business_msme_registered || false,
      employee_sector: meta.employee_sector || "",
      ...(citizen.demographic || {}),
    },
    financial: {
      annual_income: citizen.financial?.annual_income ?? null,
      employment_status: citizen.financial?.employment_status || "",
      income_source: citizen.financial?.income_source || "",
      poverty_category: citizen.financial?.poverty_category || "",
      land_holding_size: citizen.financial?.land_holding_size ?? null,
      is_bpl_card_holder: Boolean(citizen.financial?.is_bpl_card_holder),
      is_income_tax_payer: Boolean(citizen.financial?.is_income_tax_payer),
      ...(citizen.financial || {}),
    },
    location: {
      address_line_1: loc.address_line_1 || "",
      address_line_2: loc.address_line_2 || "",
      state: loc.state || "Maharashtra",
      district: loc.district || "",
      village_city: loc.village_city || "",
      pincode: loc.pincode || "",
      area_type: loc.area_type || "URBAN",
      same_as_permanent: loc.same_as_permanent !== undefined ? loc.same_as_permanent : true,
      current_address: {
        address_line_1: curAddr.address_line_1 || "",
        address_line_2: curAddr.address_line_2 || "",
        state: curAddr.state || "Maharashtra",
        district: curAddr.district || "",
        village_city: curAddr.village_city || "",
        pincode: curAddr.pincode || "",
        area_type: curAddr.area_type || "URBAN",
      },
    },
  };
}

// ---------------------------------------------------------------------------
// Education Record Form Dialog/Card
// ---------------------------------------------------------------------------
function EducationRecordEditor({ initialRecord, onSave, onCancel, saving }) {
  const [level, setLevel] = useState(initialRecord?.level || "UNDERGRADUATE");
  const [isCurrent, setIsCurrent] = useState(Boolean(initialRecord?.is_current));
  const [passingYear, setPassingYear] = useState(initialRecord?.passing_year ?? "");
  const [percentage, setPercentage] = useState(initialRecord?.percentage ?? "");
  const [details, setDetails] = useState(initialRecord?.details || {});
  const [evaluationType, setEvaluationType] = useState(
    initialRecord?.details?.evaluation_type || (initialRecord?.details?.cgpa ? "CGPA" : "PERCENTAGE")
  );
  const [error, setError] = useState("");

  const updateDetail = (key, val) => setDetails((prev) => ({ ...prev, [key]: val }));

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!level) {
      setError("Please select an education level.");
      return;
    }

    const cleanPercentage = percentage === "" ? null : Number(percentage);
    const cleanYear = passingYear === "" ? null : Number(passingYear);

    const enrichedDetails = {
      ...details,
      evaluation_type: evaluationType,
      is_current: isCurrent,
    };

    onSave({
      level,
      is_current: isCurrent,
      passing_year: cleanYear,
      percentage: cleanPercentage,
      details: enrichedDetails,
    });
  };

  return (
    <div className="bg-paper border border-line p-5 rounded-md mb-6 shadow-sm">
      <div className="flex justify-between items-center mb-4 pb-2 border-b border-line">
        <h3 className="text-base font-semibold text-ink">
          {initialRecord?.record_id ? "Edit Qualification" : "Add New Qualification"}
        </h3>
        <Button size="sm" variant="secondary" onClick={onCancel} disabled={saving}>
          ✕ Close
        </Button>
      </div>

      {error && <p className="text-xs text-excl-ink mb-3">{error}</p>}

      <form onSubmit={handleSubmit}>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-1">
          <Select
            id="edu-level"
            label="Education Level"
            required
            value={level}
            onChange={(e) => {
              setLevel(e.target.value);
              if (["UNDERGRADUATE", "POSTGRADUATE"].includes(e.target.value)) {
                setEvaluationType("CGPA");
              } else {
                setEvaluationType("PERCENTAGE");
              }
            }}
          >
            {EDUCATION_LEVEL_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </Select>

          <div className="flex items-center gap-2 pt-6 mb-4">
            <input
              id="edu-is-current"
              type="checkbox"
              className="w-4 h-4 accent-accent-ink cursor-pointer"
              checked={isCurrent}
              onChange={(e) => setIsCurrent(e.target.checked)}
            />
            <label htmlFor="edu-is-current" className="text-sm font-medium text-ink cursor-pointer">
              Currently Pursuing this Qualification
            </label>
          </div>

          {/* Level Specific Fields */}
          {level === "10TH_SSC" && (
            <>
              <Select
                id="edu-ssc-board"
                label="State / Central Board"
                value={details.board || ""}
                onChange={(e) => updateDetail("board", e.target.value)}
              >
                <option value="">Select Board</option>
                {SSC_BOARD_OPTIONS.map((b) => (
                  <option key={b.value} value={b.value}>
                    {b.label}
                  </option>
                ))}
                <option value="OTHER">Other Board</option>
              </Select>
              {details.board === "OTHER" && (
                <Input
                  id="edu-ssc-board-other"
                  label="Specify Board Name"
                  value={details.other_board || ""}
                  placeholder="Enter full board name"
                  onChange={(e) => updateDetail("other_board", e.target.value)}
                />
              )}
              <Input
                id="edu-school"
                label="School / High School Name"
                value={details.institute || ""}
                placeholder="e.g. Saraswati High School"
                onChange={(e) => updateDetail("institute", e.target.value)}
              />
              <Input
                id="edu-ssc-seat"
                label="Seat / Roll Number (Optional)"
                value={details.seat_number || ""}
                placeholder="e.g. M012345 (Optional)"
                onChange={(e) => updateDetail("seat_number", e.target.value)}
              />
            </>
          )}

          {level === "12TH_HSC" && (
            <>
              <Select
                id="edu-hsc-stream"
                label="Stream"
                value={details.stream || ""}
                onChange={(e) => updateDetail("stream", e.target.value)}
              >
                <option value="">Select Stream</option>
                {HSC_STREAM_OPTIONS.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </Select>
              {details.stream === "OTHER" && (
                <Input
                  id="edu-hsc-stream-other"
                  label="Specify Stream"
                  value={details.other_stream || ""}
                  placeholder="e.g. Fine Arts"
                  onChange={(e) => updateDetail("other_stream", e.target.value)}
                />
              )}
              <Input
                id="edu-junior-college"
                label="Junior College / School Name"
                value={details.institute || ""}
                placeholder="e.g. Fergusson College Junior Wing"
                onChange={(e) => updateDetail("institute", e.target.value)}
              />
              <Select
                id="edu-hsc-board"
                label="Board"
                value={details.board || ""}
                onChange={(e) => updateDetail("board", e.target.value)}
              >
                <option value="">Select Board</option>
                {SSC_BOARD_OPTIONS.map((b) => (
                  <option key={b.value} value={b.value}>
                    {b.label}
                  </option>
                ))}
                <option value="OTHER">Other Board</option>
              </Select>
              {details.board === "OTHER" && (
                <Input
                  id="edu-hsc-board-other"
                  label="Specify Board Name"
                  value={details.other_board || ""}
                  placeholder="Enter full board name"
                  onChange={(e) => updateDetail("other_board", e.target.value)}
                />
              )}
            </>
          )}

          {level === "DIPLOMA" && (
            <>
              <Input
                id="edu-diploma-branch"
                label="Branch / Discipline"
                value={details.branch || ""}
                placeholder="e.g. Mechanical Engineering"
                onChange={(e) => updateDetail("branch", e.target.value)}
              />
              <Input
                id="edu-polytechnic"
                label="Polytechnic / College Name"
                value={details.institute || ""}
                placeholder="e.g. Govt Polytechnic Pune"
                onChange={(e) => updateDetail("institute", e.target.value)}
              />
            </>
          )}

          {level === "ITI" && (
            <>
              <Input
                id="edu-iti-trade"
                label="Trade / Specialization"
                value={details.trade || ""}
                placeholder="e.g. Electrician / Fitter"
                onChange={(e) => updateDetail("trade", e.target.value)}
              />
              <Input
                id="edu-iti-inst"
                label="ITI Institute Name"
                value={details.institute || ""}
                onChange={(e) => updateDetail("institute", e.target.value)}
              />
            </>
          )}

          {level === "UNDERGRADUATE" && (
            <>
              <Select
                id="edu-ug-degree"
                label="Degree / Program"
                value={details.degree || ""}
                onChange={(e) => updateDetail("degree", e.target.value)}
              >
                <option value="">Select Degree</option>
                {UG_DEGREE_OPTIONS.map((d) => (
                  <option key={d.value} value={d.value}>
                    {d.label}
                  </option>
                ))}
              </Select>
              {details.degree === "OTHER_UG" && (
                <Input
                  id="edu-ug-degree-other"
                  label="Specify Bachelor's Degree"
                  value={details.other_degree || ""}
                  placeholder="e.g. B.Des / B.Voc"
                  onChange={(e) => updateDetail("other_degree", e.target.value)}
                />
              )}
              <Input
                id="edu-ug-branch"
                label="Branch / Major Specialization"
                value={details.branch || ""}
                placeholder="e.g. Computer Science / Electronics"
                onChange={(e) => updateDetail("branch", e.target.value)}
              />
              <Input
                id="edu-ug-course"
                label="Course / Program Name"
                value={details.course || ""}
                placeholder="e.g. Four Year B.Tech Program"
                onChange={(e) => updateDetail("course", e.target.value)}
              />
              <Input
                id="edu-ug-college"
                label="College / Institute Name"
                value={details.institute || ""}
                placeholder="e.g. College of Engineering Pune (COEP)"
                onChange={(e) => updateDetail("institute", e.target.value)}
              />
              <Input
                id="edu-ug-uni"
                label="University"
                value={details.university || ""}
                placeholder="e.g. SPPU Pune / Autonomous"
                onChange={(e) => updateDetail("university", e.target.value)}
              />
              <Input
                id="edu-admission-year"
                label="Admission Year"
                type="number"
                min={2000}
                max={2035}
                placeholder="e.g. 2022"
                value={details.admission_year ?? ""}
                onChange={(e) =>
                  updateDetail(
                    "admission_year",
                    e.target.value === "" ? null : Number(e.target.value)
                  )
                }
              />
              {isCurrent && (
                <>
                  <Select
                    id="edu-current-year"
                    label="Current Year of Study"
                    value={details.current_year || ""}
                    onChange={(e) => updateDetail("current_year", e.target.value)}
                  >
                    <option value="">Select Current Year</option>
                    {CURRENT_YEAR_OPTIONS.map((y) => (
                      <option key={y.value} value={y.value}>
                        {y.label}
                      </option>
                    ))}
                  </Select>
                  <Input
                    id="edu-semester"
                    label="Current Semester (1-10)"
                    type="number"
                    min={1}
                    max={10}
                    value={details.current_semester ?? ""}
                    onChange={(e) =>
                      updateDetail(
                        "current_semester",
                        e.target.value === "" ? null : Number(e.target.value)
                      )
                    }
                  />
                  <Select
                    id="edu-backlogs"
                    label="Active Backlogs / ATKT"
                    value={String(details.has_backlogs || false)}
                    onChange={(e) => updateDetail("has_backlogs", e.target.value === "true")}
                  >
                    <option value="false">No (All Cleared)</option>
                    <option value="true">Yes (Active Backlogs)</option>
                  </Select>
                  {details.has_backlogs && (
                    <Input
                      id="edu-backlogs-count"
                      label="Number of Backlog Subjects"
                      type="number"
                      min={1}
                      max={20}
                      value={details.backlogs_count ?? ""}
                      onChange={(e) =>
                        updateDetail(
                          "backlogs_count",
                          e.target.value === "" ? null : Number(e.target.value)
                        )
                      }
                    />
                  )}
                </>
              )}
            </>
          )}

          {level === "POSTGRADUATE" && (
            <>
              <Select
                id="edu-pg-degree"
                label="Postgraduate Degree"
                value={details.degree || ""}
                onChange={(e) => updateDetail("degree", e.target.value)}
              >
                <option value="">Select Degree</option>
                {PG_DEGREE_OPTIONS.map((d) => (
                  <option key={d.value} value={d.value}>
                    {d.label}
                  </option>
                ))}
              </Select>
              {details.degree === "OTHER_PG" && (
                <Input
                  id="edu-pg-degree-other"
                  label="Specify Master's Degree"
                  value={details.other_degree || ""}
                  placeholder="e.g. M.Des"
                  onChange={(e) => updateDetail("other_degree", e.target.value)}
                />
              )}
              <Input
                id="edu-pg-branch"
                label="Specialization / Subject"
                value={details.branch || ""}
                placeholder="e.g. Data Science / Structural Engineering"
                onChange={(e) => updateDetail("branch", e.target.value)}
              />
              <Input
                id="edu-pg-college"
                label="College / University"
                value={details.university || ""}
                placeholder="e.g. IIT Bombay / SPPU"
                onChange={(e) => updateDetail("university", e.target.value)}
              />
              {isCurrent && (
                <Select
                  id="edu-pg-current-year"
                  label="Current Year of Study"
                  value={details.current_year || ""}
                  onChange={(e) => updateDetail("current_year", e.target.value)}
                >
                  <option value="">Select Year</option>
                  <option value="FIRST_YEAR">1st Year</option>
                  <option value="SECOND_YEAR">2nd Year (Final Year)</option>
                  <option value="THIRD_YEAR">3rd Year</option>
                </Select>
              )}
            </>
          )}

          {level === "PHD" && (
            <>
              <Input
                id="edu-phd-field"
                label="Research Domain / Topic"
                value={details.research_field || ""}
                placeholder="e.g. Renewable Energy Systems"
                onChange={(e) => updateDetail("research_field", e.target.value)}
              />
              <Input
                id="edu-phd-uni"
                label="University / Research Institute"
                value={details.university || ""}
                onChange={(e) => updateDetail("university", e.target.value)}
              />
            </>
          )}

          {level === "OTHER" && (
            <>
              <Input
                id="edu-other-title"
                label="Qualification Title"
                value={details.qualification_title || ""}
                placeholder="e.g. Advanced Diploma in Cloud Computing"
                onChange={(e) => updateDetail("qualification_title", e.target.value)}
              />
              <Input
                id="edu-other-inst"
                label="Institute / Organization"
                value={details.institute || ""}
                onChange={(e) => updateDetail("institute", e.target.value)}
              />
            </>
          )}

          {/* Academic Performance & Evaluation Type (CGPA vs Percentage) */}
          <div className="col-span-full border-t border-line pt-3 mt-2">
            <label className="block text-[13px] font-medium text-ink mb-2">
              Academic Performance Evaluation Type
            </label>
            <div className="flex gap-6 mb-3">
              <label className="flex items-center gap-2 cursor-pointer text-sm font-medium">
                <input
                  type="radio"
                  name="evaluation-type"
                  value="CGPA"
                  checked={evaluationType === "CGPA"}
                  onChange={() => setEvaluationType("CGPA")}
                  className="accent-accent-ink"
                />
                CGPA / SGPA (Grading Scale)
              </label>
              <label className="flex items-center gap-2 cursor-pointer text-sm font-medium">
                <input
                  type="radio"
                  name="evaluation-type"
                  value="PERCENTAGE"
                  checked={evaluationType === "PERCENTAGE"}
                  onChange={() => setEvaluationType("PERCENTAGE")}
                  className="accent-accent-ink"
                />
                Percentage (%) / Marks
              </label>
            </div>
          </div>

          {evaluationType === "CGPA" ? (
            <>
              <Input
                id="edu-cgpa-score"
                label="CGPA / SGPA Score"
                type="number"
                step="0.01"
                min={0}
                max={10}
                placeholder="e.g. 8.75"
                value={details.cgpa ?? ""}
                onChange={(e) => {
                  const val = e.target.value === "" ? null : Number(e.target.value);
                  updateDetail("cgpa", val);
                  // Approximate percentage conversion (e.g. CGPA * 9.5 or * 10) for engine fallback
                  if (val !== null) {
                    setPercentage(String(Math.min(100, Math.round(val * 9.5 * 100) / 100)));
                  }
                }}
              />
              <Input
                id="edu-cgpa-scale"
                label="Max Scale (Base)"
                type="number"
                value={details.cgpa_scale || 10}
                placeholder="10"
                onChange={(e) => updateDetail("cgpa_scale", Number(e.target.value) || 10)}
              />
            </>
          ) : (
            <Input
              id="edu-percentage-val"
              label="Percentage Score (%)"
              type="number"
              step="0.01"
              min={0}
              max={100}
              placeholder="e.g. 84.50"
              value={percentage}
              onChange={(e) => setPercentage(e.target.value)}
            />
          )}

          <Input
            id="edu-passing-year"
            label={isCurrent ? "Expected Year of Graduation" : "Passing Year"}
            type="number"
            min={1960}
            max={2035}
            placeholder="e.g. 2024"
            value={passingYear}
            onChange={(e) => setPassingYear(e.target.value)}
          />

          <Select
            id="edu-result-status"
            label="Result Status"
            value={details.result_status || (isCurrent ? "PURSUING" : "PASSED")}
            onChange={(e) => updateDetail("result_status", e.target.value)}
          >
            {RESULT_STATUS_OPTIONS.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </Select>
        </div>

        <div className="flex justify-end gap-3 mt-5 pt-3 border-t border-line">
          <Button type="button" variant="secondary" size="sm" onClick={onCancel} disabled={saving}>
            Cancel
          </Button>
          <Button type="submit" size="sm" disabled={saving}>
            {saving
              ? initialRecord?.record_id
                ? "Updating..."
                : "Adding..."
              : initialRecord?.record_id
              ? "Update Qualification"
              : "Add Qualification"}
          </Button>
        </div>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Profile Wizard Component
// ---------------------------------------------------------------------------
export default function ProfilePage() {
  const navigate = useNavigate();
  const [citizen, setCitizen] = useState(null);
  const [citizenId, setCitizenId] = useState(null);
  const [authenticatedEmail, setAuthenticatedEmail] = useState("");
  const [draft, setDraft] = useState(null);
  const [educationRecords, setEducationRecords] = useState([]);
  const [editing, setEditing] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [savingEdu, setSavingEdu] = useState(false);
  const [deletingEduId, setDeletingEduId] = useState(null);
  const [saveSuccessMsg, setSaveSuccessMsg] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [status, setStatus] = useState("loading");
  const [currentStep, setCurrentStep] = useState(1);

  // Form question placeholders loaded from dynamic form system
  const [placeholders, setPlaceholders] = useState({});
  const [helpTexts, setHelpTexts] = useState({});

  // Active education editor state
  const [editingEduRecord, setEditingEduRecord] = useState(null);
  const [isAddingEdu, setIsAddingEdu] = useState(false);

  // Submitted answers for review
  const [savedAnswers, setSavedAnswers] = useState(null);
  const [formSections, setFormSections] = useState(null);

  const reloadProfile = useCallback(async () => {
    try {
      const me = await authService.me();
      const email = me.data.email || me.data.email_id || "";
      setAuthenticatedEmail(email);

      const id = me.data.citizen_id;
      setCitizenId(id);

      // Load form definition questions for dynamic placeholders
      try {
        const formResp = await formService.getActive(FORM_CODE);
        const pMap = {};
        const hMap = {};
        if (formResp.data?.sections) {
          formResp.data.sections.forEach((sec) => {
            sec.questions?.forEach((q) => {
              if (q.placeholder) {
                pMap[q.question_code] = q.placeholder;
                if (q.profile_field) pMap[q.profile_field] = q.placeholder;
              }
              if (q.help_text) {
                hMap[q.question_code] = q.help_text;
                if (q.profile_field) hMap[q.profile_field] = q.help_text;
              }
            });
          });
        }
        setPlaceholders(pMap);
        setHelpTexts(hMap);
        setFormSections(formResp.data?.sections || null);
      } catch {
        // Fallback to empty placeholders
      }

      if (!id) {
        setDraft(
          initProfileState(
            {
              full_name: me.data.full_name || me.data.citizen_name || "",
              email_id: email,
            },
            email
          )
        );
        setEditing(true);
        setStatus("needs-profile");
        return;
      }

      const [citizenResp, eduResp] = await Promise.all([
        citizenService.get(id),
        citizenService.getEducation(id).catch(() => ({ data: [] })),
      ]);

      setCitizen(citizenResp.data);
      setDraft(initProfileState(citizenResp.data, email));
      setEducationRecords(eduResp.data || citizenResp.data.education_records || []);
      setStatus("ready");

      try {
        const savedResp = await formService.getSavedAnswers(FORM_CODE);
        setSavedAnswers(savedResp.data?.values || null);
      } catch {
        setSavedAnswers(null);
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

  const nested = (group, field, next) =>
    setDraft((current) => ({
      ...current,
      [group]: { ...(current[group] || {}), [field]: next },
    }));

  const nestedCurrentAddress = (field, next) =>
    setDraft((current) => ({
      ...current,
      location: {
        ...(current.location || {}),
        current_address: {
          ...(current.location?.current_address || {}),
          [field]: next,
        },
      },
    }));

  const onFieldChange = (field, validatorFn, value) => {
    const err = validatorFn(value);
    setFieldErrors((current) => ({ ...current, [field]: err }));
  };

  // -------------------------------------------------------------------------
  // Education Record Actions
  // -------------------------------------------------------------------------
  const handleSaveEducationRecord = async (recordData) => {
    setSavingEdu(true);
    setError("");
    try {
      if (citizenId) {
        if (editingEduRecord?.record_id) {
          const res = await citizenService.updateEducation(
            citizenId,
            editingEduRecord.record_id,
            recordData
          );
          setEducationRecords((prev) =>
            prev.map((r) => (r.record_id === editingEduRecord.record_id ? res.data : r))
          );
        } else {
          const res = await citizenService.addEducation(citizenId, recordData);
          setEducationRecords((prev) => [...prev, res.data]);
        }
      } else {
        // Staged locally for new user before initial citizen profile save
        if (editingEduRecord?._tempId) {
          setEducationRecords((prev) =>
            prev.map((r) =>
              r._tempId === editingEduRecord._tempId ? { ...recordData, _tempId: r._tempId } : r
            )
          );
        } else {
          setEducationRecords((prev) => [...prev, { ...recordData, _tempId: Date.now() }]);
        }
      }
      setIsAddingEdu(false);
      setEditingEduRecord(null);
    } catch (err) {
      setError(extractApiErrorMessage(err, "Failed to save education qualification."));
    } finally {
      setSavingEdu(false);
    }
  };

  const handleDeleteEducationRecord = async (rec) => {
    if (!window.confirm("Are you sure you want to delete this qualification?")) return;
    const recId = rec.record_id || rec._tempId;
    setDeletingEduId(recId);
    setError("");
    try {
      if (citizenId && rec.record_id) {
        await citizenService.deleteEducation(citizenId, rec.record_id);
        setEducationRecords((prev) => prev.filter((r) => r.record_id !== rec.record_id));
      } else {
        setEducationRecords((prev) =>
          prev.filter((r) => (rec._tempId ? r._tempId !== rec._tempId : r.record_id !== rec.record_id))
        );
      }
    } catch (err) {
      setError(extractApiErrorMessage(err, "Failed to delete education record."));
    } finally {
      setDeletingEduId(null);
    }
  };

  // -------------------------------------------------------------------------
  // Step Validation & Navigation
  // -------------------------------------------------------------------------
  const validateCurrentStep = (step) => {
    const errs = {};
    if (step === 1) {
      errs.firstName = validateFirstName(draft.firstName);
      errs.middleName = validateMiddleName(draft.middleName);
      errs.lastName = validateLastName(draft.lastName);
      errs.date_of_birth = validateDob(draft.date_of_birth);
      errs.mobile_number = validateMobile(draft.mobile_number);
    } else if (step === 3) {
      errs.annual_income = validateIncome(draft.financial?.annual_income);
    } else if (step === 5) {
      if (draft.location?.pincode) {
        errs.pincode = validatePincode(draft.location.pincode);
      }
      if (!draft.location?.same_as_permanent && draft.location?.current_address?.pincode) {
        errs.current_pincode = validatePincode(draft.location.current_address.pincode);
      }
    }
    setFieldErrors(errs);
    return hasNoErrors(errs);
  };

  const handleNextStep = () => {
    if (validateCurrentStep(currentStep)) {
      setError("");
      setCurrentStep((s) => Math.min(s + 1, 7));
      window.scrollTo({ top: 0, behavior: "smooth" });
    } else {
      setError("Please correct the highlighted fields before proceeding.");
    }
  };

  const handlePrevStep = () => {
    setError("");
    setCurrentStep((s) => Math.max(s - 1, 1));
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // Build clean payload for API
  const buildPayload = () => {
    const full_name = buildFullName(draft.firstName, draft.middleName, draft.lastName);
    const loc = draft.location || {};
    const curAddr = loc.same_as_permanent
      ? {
          address_line_1: loc.address_line_1 || "",
          address_line_2: loc.address_line_2 || "",
          state: loc.state || "",
          district: loc.district || "",
          village_city: loc.village_city || "",
          pincode: loc.pincode || "",
          area_type: loc.area_type || "URBAN",
        }
      : loc.current_address || {};

    return {
      full_name: full_name || undefined,
      date_of_birth: draft.date_of_birth || undefined,
      gender: draft.gender || null,
      mobile_number: draft.mobile_number || null,
      email_id: authenticatedEmail || draft.email_id || null,
      citizen_type: draft.citizen_type,
      profile_types: draft.profile_types,
      demographic: {
        ...draft.demographic,
        type_specific_metadata: {
          other_occupation: draft.demographic.other_occupation,
          other_social_category: draft.demographic.other_social_category,
          disability_type: draft.demographic.disability_type,
          disability_percentage: draft.demographic.disability_percentage,
          udid_number: draft.demographic.udid_number,
          student_hostel_status: draft.demographic.student_hostel_status,
          student_admission_quota: draft.demographic.student_admission_quota,
          farmer_category: draft.demographic.farmer_category,
          farmer_irrigation_type: draft.demographic.farmer_irrigation_type,
          farmer_crop_types: draft.demographic.farmer_crop_types,
          business_nature: draft.demographic.business_nature,
          business_msme_registered: draft.demographic.business_msme_registered,
          employee_sector: draft.demographic.employee_sector,
        },
      },
      financial: draft.financial,
      location: {
        address_line_1: loc.address_line_1 || null,
        address_line_2: loc.address_line_2 || null,
        state: loc.state || null,
        district: loc.district || null,
        village_city: loc.village_city || null,
        pincode: loc.pincode || null,
        area_type: loc.area_type || "URBAN",
        same_as_permanent: Boolean(loc.same_as_permanent),
        current_address: curAddr,
      },
    };
  };

  // -------------------------------------------------------------------------
  // Save Draft & Submit Profile
  // -------------------------------------------------------------------------
  const handleSaveDraft = async () => {
    setSavingDraft(true);
    setError("");
    setSaveSuccessMsg("");
    try {
      const payload = buildPayload();
      if (citizenId) {
        const response = await citizenService.update(citizenId, payload);
        setCitizen(response.data);
      } else {
        const response = await citizenService.register(payload);
        setCitizen(response.data);
        setCitizenId(response.data.citizen_id);
      }
      setSaveSuccessMsg("Draft saved successfully.");
      setTimeout(() => setSaveSuccessMsg(""), 4000);
    } catch (err) {
      setError(extractApiErrorMessage(err, "Could not save draft."));
    } finally {
      setSavingDraft(false);
    }
  };

  const handleSubmitProfile = async () => {
    // Validate all required steps
    const errors = {
      firstName: validateFirstName(draft.firstName),
      middleName: validateMiddleName(draft.middleName),
      lastName: validateLastName(draft.lastName),
      date_of_birth: validateDob(draft.date_of_birth),
      mobile_number: validateMobile(draft.mobile_number),
      annual_income: validateIncome(draft.financial?.annual_income),
    };
    if (draft.location?.pincode) {
      errors.pincode = validatePincode(draft.location.pincode);
    }
    if (!draft.location?.same_as_permanent && draft.location?.current_address?.pincode) {
      errors.current_pincode = validatePincode(draft.location.current_address.pincode);
    }

    setFieldErrors(errors);
    if (!hasNoErrors(errors)) {
      setError("Please fix the highlighted validation errors before submitting.");
      return;
    }

    setSubmitting(true);
    setError("");
    try {
      const payload = buildPayload();
      let activeId = citizenId;
      if (citizenId) {
        const response = await citizenService.update(citizenId, payload);
        setCitizen(response.data);
        activeId = response.data.citizen_id;
      } else {
        const response = await citizenService.register(payload);
        setCitizen(response.data);
        activeId = response.data.citizen_id;
        setCitizenId(activeId);

        // Sync staged education records if any
        if (educationRecords.length > 0 && activeId) {
          for (const rec of educationRecords) {
            await citizenService.addEducation(activeId, rec);
          }
        }
      }

      setEditing(false);
      setStatus("ready");
      await reloadProfile();
    } catch (err) {
      setError(extractApiErrorMessage(err, "Failed to submit profile. Please try again."));
    } finally {
      setSubmitting(false);
    }
  };

  if (status === "loading") {
    return <LoadingState label="Loading citizen profile..." />;
  }

  if (status === "error") {
    return (
      <ErrorState
        title="Unable to load profile"
        message="We couldn't load your citizen record. Please try again."
        onRetry={reloadProfile}
      />
    );
  }

  if (status === "empty" || (!citizenId && status !== "needs-profile")) {
    return (
      <EmptyState
        title="Sign in required"
        message="Please sign in or register to access and manage your citizen profile."
        action={
          <Button to="/login" variant="primary">
            Sign in
          </Button>
        }
      />
    );
  }

  const age = calculateAge(draft?.date_of_birth);
  const isStudent =
    draft?.citizen_type === "STUDENT" || draft?.profile_types?.includes("STUDENT");
  const isFarmer =
    draft?.citizen_type === "FARMER" || draft?.profile_types?.includes("FARMER");
  const isBusiness = draft?.profile_types?.includes("BUSINESS");
  const isEmployee = draft?.profile_types?.includes("EMPLOYEE");

  // -------------------------------------------------------------------------
  // Render Step Form Content
  // -------------------------------------------------------------------------
  const renderStepContent = () => {
    switch (currentStep) {
      case 1:
        return (
          <section className="space-y-4">
            <div className="border-b border-line pb-3 mb-4">
              <h2 className="text-xl font-semibold text-ink">Step 1 — Basic Information</h2>
              <p className="text-xs text-ink-soft">Enter your legal identity and demographic details.</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-x-5">
              <Input
                id="wizard-first-name"
                label="First Name"
                required
                placeholder={placeholders.firstName || placeholders.first_name}
                hint={helpTexts.firstName || helpTexts.first_name}
                value={draft.firstName}
                error={fieldErrors?.firstName}
                onChange={(e) => {
                  const v = e.target.value;
                  setDraft((cur) => ({ ...cur, firstName: v }));
                  onFieldChange("firstName", validateFirstName, v);
                }}
                autoComplete="given-name"
              />
              <Input
                id="wizard-middle-name"
                label="Middle Name"
                placeholder={placeholders.middleName || placeholders.middle_name}
                hint={helpTexts.middleName || helpTexts.middle_name}
                value={draft.middleName}
                error={fieldErrors?.middleName}
                onChange={(e) => {
                  const v = e.target.value;
                  setDraft((cur) => ({ ...cur, middleName: v }));
                  onFieldChange("middleName", validateMiddleName, v);
                }}
                autoComplete="additional-name"
              />
              <Input
                id="wizard-last-name"
                label="Last Name"
                required
                placeholder={placeholders.lastName || placeholders.last_name}
                hint={helpTexts.lastName || helpTexts.last_name}
                value={draft.lastName}
                error={fieldErrors?.lastName}
                onChange={(e) => {
                  const v = e.target.value;
                  setDraft((cur) => ({ ...cur, lastName: v }));
                  onFieldChange("lastName", validateLastName, v);
                }}
                autoComplete="family-name"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-x-5">
              <div>
                <Input
                  id="wizard-dob"
                  label="Date of Birth"
                  required
                  type="date"
                  max={new Date().toISOString().slice(0, 10)}
                  value={draft.date_of_birth}
                  error={fieldErrors?.date_of_birth}
                  onChange={(e) => {
                    const v = e.target.value;
                    setDraft((cur) => ({ ...cur, date_of_birth: v }));
                    onFieldChange("date_of_birth", validateDob, v);
                  }}
                  autoComplete="bday"
                />
                {age !== null && !fieldErrors?.date_of_birth && (
                  <p className="text-xs text-ink-soft -mt-3 mb-4">
                    Derived Age: <strong className="text-ink font-semibold">{age} years</strong>
                  </p>
                )}
              </div>

              <Select
                id="wizard-gender"
                label="Gender"
                required
                value={draft.gender || ""}
                onChange={(e) => setDraft((cur) => ({ ...cur, gender: e.target.value || null }))}
              >
                <option value="">Select Gender</option>
                {GENDER_OPTIONS.map((g) => (
                  <option key={g.value} value={g.value}>
                    {g.label}
                  </option>
                ))}
              </Select>

              <Select
                id="wizard-citizen-type"
                label="Primary Citizen Category"
                required
                value={draft.citizen_type}
                onChange={(e) => setDraft((cur) => ({ ...cur, citizen_type: e.target.value }))}
              >
                {CITIZEN_TYPE_OPTIONS.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </Select>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-5">
              <Input
                id="wizard-mobile"
                label="Mobile Number (10 digits)"
                required
                type="tel"
                inputMode="numeric"
                maxLength={10}
                placeholder={placeholders.mobile_number || placeholders.mobile}
                hint={helpTexts.mobile_number || "Used for scheme notifications & verification"}
                value={draft.mobile_number || ""}
                error={fieldErrors?.mobile_number}
                onChange={(e) => {
                  const v = e.target.value.replace(/\D/g, "").slice(0, 10);
                  setDraft((cur) => ({ ...cur, mobile_number: v || null }));
                  onFieldChange("mobile_number", validateMobile, v);
                }}
                autoComplete="tel"
              />

              <Input
                id="wizard-email"
                label="Registered Email"
                type="email"
                value={authenticatedEmail || draft.email_id || ""}
                readOnly
                className="opacity-80 bg-paper cursor-not-allowed font-mono text-xs"
                hint="Linked with your sign-in account. Email cannot be changed here."
              />
            </div>

            <div className="mt-4 p-4 border border-line rounded-md bg-paper">
              <label className="block text-sm font-semibold text-ink mb-1">
                Profile Types (Select all that apply to you)
              </label>
              <p className="text-xs text-ink-soft mb-3">
                Selecting multiple roles unlocks cross-category schemes (e.g. Student + PWD, Farmer + Senior Citizen).
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                {PROFILE_TYPE_OPTIONS.map((opt) => {
                  const currentTypes = Array.isArray(draft.profile_types) ? draft.profile_types : [];
                  const checked = currentTypes.includes(opt.value);
                  return (
                    <label
                      key={opt.value}
                      className={`flex items-center gap-2 p-2 rounded border cursor-pointer transition-colors ${
                        checked ? "border-accent-ink bg-white shadow-xs" : "border-line bg-paper/50"
                      }`}
                    >
                      <input
                        type="checkbox"
                        className="w-4 h-4 accent-accent-ink"
                        checked={checked}
                        onChange={(e) => {
                          const isChecked = e.target.checked;
                          setDraft((cur) => {
                            const list = Array.isArray(cur.profile_types) ? cur.profile_types : [];
                            return {
                              ...cur,
                              profile_types: isChecked
                                ? [...list, opt.value]
                                : list.filter((t) => t !== opt.value),
                            };
                          });
                        }}
                      />
                      <span className="text-xs font-medium text-ink">{opt.label}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          </section>
        );

      case 2:
        return (
          <section className="space-y-4">
            <div className="flex flex-wrap items-center justify-between border-b border-line pb-3 mb-4 gap-2">
              <div>
                <h2 className="text-xl font-semibold text-ink">Step 2 — Education History</h2>
                <p className="text-xs text-ink-soft">
                  Canonical educational records (SSC, HSC, Diploma, Degree, etc.). Add multiple qualifications.
                </p>
              </div>
              {!isAddingEdu && !editingEduRecord && (
                <Button
                  size="sm"
                  onClick={() => {
                    setEditingEduRecord(null);
                    setIsAddingEdu(true);
                  }}
                >
                  + Add Qualification
                </Button>
              )}
            </div>

            {(isAddingEdu || editingEduRecord) && (
              <EducationRecordEditor
                initialRecord={editingEduRecord}
                onSave={handleSaveEducationRecord}
                onCancel={() => {
                  setIsAddingEdu(false);
                  setEditingEduRecord(null);
                }}
                saving={savingEdu}
              />
            )}

            {educationRecords.length === 0 && !isAddingEdu && (
              <div className="text-center py-10 px-4 border-2 border-dashed border-line rounded-md">
                <p className="text-sm font-medium text-ink mb-2">No education records added yet.</p>
                <p className="text-xs text-ink-soft mb-4">
                  Add your 10th (SSC), 12th (HSC), Diploma, or Degree qualifications to match scholarship criteria.
                </p>
                <Button
                  size="sm"
                  onClick={() => {
                    setEditingEduRecord(null);
                    setIsAddingEdu(true);
                  }}
                >
                  + Add Qualification
                </Button>
              </div>
            )}

            {educationRecords.length > 0 && (
              <div className="space-y-3">
                {educationRecords.map((rec, idx) => {
                  const d = rec.details || {};
                  const recKey = rec.record_id || rec._tempId || idx;
                  const isDeleting = deletingEduId === recKey;
                  return (
                    <div
                      key={recKey}
                      className="p-4 bg-white border border-line rounded-md flex flex-col md:flex-row md:items-center justify-between gap-3 shadow-xs hover:border-accent transition-colors"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-semibold text-sm text-ink">
                            {formatEducationLevel(rec.level)}
                          </span>
                          {rec.is_current && (
                            <Badge variant="neutral" pill>
                              Current Course
                            </Badge>
                          )}
                          {d.result_status && (
                            <Badge variant={d.result_status === "PASSED" ? "ok" : "neutral"}>
                              {d.result_status}
                            </Badge>
                          )}
                        </div>

                        <div className="text-xs text-ink-soft flex flex-wrap gap-x-4 gap-y-1">
                          {d.degree && (
                            <span>
                              Degree: <strong>{d.degree === "OTHER_UG" || d.degree === "OTHER_PG" ? d.other_degree || d.degree : d.degree}</strong>
                            </span>
                          )}
                          {d.branch && (
                            <span>
                              Branch: <strong>{d.branch}</strong>
                            </span>
                          )}
                          {d.stream && (
                            <span>
                              Stream: <strong>{d.stream === "OTHER" ? d.other_stream || d.stream : d.stream}</strong>
                            </span>
                          )}
                          {d.institute && (
                            <span>
                              Institute: <strong>{d.institute}</strong>
                            </span>
                          )}
                          {d.university && (
                            <span>
                              University: <strong>{d.university}</strong>
                            </span>
                          )}
                          {d.board && (
                            <span>
                              Board: <strong>{d.board === "OTHER" ? d.other_board || d.board : d.board}</strong>
                            </span>
                          )}
                          {d.current_year && (
                            <span>
                              Year: <strong>{formatOption(CURRENT_YEAR_OPTIONS, d.current_year)}</strong>
                            </span>
                          )}
                          {d.current_semester && (
                            <span>
                              Semester: <strong>{d.current_semester}</strong>
                            </span>
                          )}
                          {rec.passing_year && (
                            <span>
                              Year: <strong>{rec.passing_year}</strong>
                            </span>
                          )}
                          {d.cgpa !== null && d.cgpa !== undefined && (
                            <span>
                              CGPA: <strong>{d.cgpa} / {d.cgpa_scale || 10}</strong>
                            </span>
                          )}
                          {rec.percentage !== null && rec.percentage !== undefined && (
                            <span>
                              Percentage: <strong>{rec.percentage}%</strong>
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center gap-2 self-end md:self-center">
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => {
                            setEditingEduRecord(rec);
                            setIsAddingEdu(false);
                          }}
                          disabled={isDeleting}
                        >
                          Edit
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          className="text-excl-ink hover:border-excl"
                          onClick={() => handleDeleteEducationRecord(rec)}
                          disabled={isDeleting}
                        >
                          {isDeleting ? "Deleting..." : "Remove"}
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        );

      case 3:
        return (
          <section className="space-y-4">
            <div className="border-b border-line pb-3 mb-4">
              <h2 className="text-xl font-semibold text-ink">Step 3 — Family &amp; Income</h2>
              <p className="text-xs text-ink-soft">Financial criteria for scholarships and welfare entitlement.</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-5">
              <Input
                id="wizard-income"
                label="Annual Family Income (₹)"
                type="number"
                min={0}
                inputMode="numeric"
                placeholder={placeholders.annual_income || placeholders.income || "e.g. 150000"}
                hint={helpTexts.annual_income || "Total gross family income from all sources in ₹"}
                value={draft.financial?.annual_income ?? ""}
                error={fieldErrors?.annual_income}
                onChange={(e) => {
                  const v = e.target.value;
                  nested("financial", "annual_income", v === "" ? null : Number(v));
                  onFieldChange("annual_income", validateIncome, v);
                }}
              />

              <Select
                id="wizard-employment-status"
                label="Employment Status"
                value={draft.financial?.employment_status || ""}
                onChange={(e) => nested("financial", "employment_status", e.target.value)}
              >
                <option value="">Select Employment Status</option>
                {EMPLOYMENT_STATUS_OPTIONS.map((e) => (
                  <option key={e.value} value={e.value}>
                    {e.label}
                  </option>
                ))}
              </Select>

              <Select
                id="wizard-income-source"
                label="Primary Income Source"
                value={draft.financial?.income_source || ""}
                onChange={(e) => nested("financial", "income_source", e.target.value)}
              >
                <option value="">Select Income Source</option>
                {INCOME_SOURCE_OPTIONS.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </Select>

              <Select
                id="wizard-poverty-cat"
                label="Poverty / Ration Category"
                value={draft.financial?.poverty_category || ""}
                onChange={(e) => nested("financial", "poverty_category", e.target.value)}
              >
                <option value="">Select Category</option>
                {POVERTY_CATEGORY_OPTIONS.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </Select>

              <Input
                id="wizard-family-size"
                label="Total Family Members"
                type="number"
                min={1}
                max={30}
                placeholder={placeholders.family_size || "e.g. 4"}
                value={draft.demographic?.family_size ?? ""}
                onChange={(e) =>
                  nested(
                    "demographic",
                    "family_size",
                    e.target.value === "" ? null : Number(e.target.value)
                  )
                }
              />

              <Input
                id="wizard-land"
                label="Agricultural Land Holding (Hectares)"
                type="number"
                step="0.01"
                min={0}
                placeholder="e.g. 1.5"
                value={draft.financial?.land_holding_size ?? ""}
                onChange={(e) =>
                  nested(
                    "financial",
                    "land_holding_size",
                    e.target.value === "" ? null : Number(e.target.value)
                  )
                }
              />

              <Select
                id="wizard-bpl"
                label="BPL (Below Poverty Line) Card Holder"
                value={String(draft.financial?.is_bpl_card_holder)}
                onChange={(e) => nested("financial", "is_bpl_card_holder", e.target.value === "true")}
              >
                <option value="false">No</option>
                <option value="true">Yes</option>
              </Select>

              <Select
                id="wizard-tax"
                label="Income Tax Payer in Family"
                value={String(draft.financial?.is_income_tax_payer)}
                onChange={(e) => nested("financial", "is_income_tax_payer", e.target.value === "true")}
              >
                <option value="false">No</option>
                <option value="true">Yes</option>
              </Select>
            </div>
          </section>
        );

      case 4:
        return (
          <section className="space-y-4">
            <div className="border-b border-line pb-3 mb-4">
              <h2 className="text-xl font-semibold text-ink">Step 4 — Social &amp; Special Categories</h2>
              <p className="text-xs text-ink-soft">Reservation, category, and disability benefits.</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-5">
              <Select
                id="wizard-social-category"
                label="Social Category / Caste Group"
                value={draft.demographic?.social_category || ""}
                onChange={(e) => nested("demographic", "social_category", e.target.value)}
              >
                <option value="">Select Social Category</option>
                {SOCIAL_CATEGORIES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </Select>

              {draft.demographic?.social_category === "OTHER" && (
                <Input
                  id="wizard-social-category-other"
                  label="Specify Social Category"
                  placeholder="Enter social category name"
                  value={draft.demographic?.other_social_category || ""}
                  onChange={(e) => nested("demographic", "other_social_category", e.target.value)}
                />
              )}

              <Select
                id="wizard-marital-status"
                label="Marital Status"
                value={draft.demographic?.marital_status || ""}
                onChange={(e) => nested("demographic", "marital_status", e.target.value)}
              >
                <option value="">Select Marital Status</option>
                {MARITAL_STATUS_OPTIONS.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </Select>

              <Select
                id="wizard-disability-status"
                label="Disability Status"
                value={draft.demographic?.disability_status || "NONE"}
                onChange={(e) => nested("demographic", "disability_status", e.target.value)}
              >
                {DISABILITY_STATUS_OPTIONS.map((d) => (
                  <option key={d.value} value={d.value}>
                    {d.label}
                  </option>
                ))}
              </Select>
            </div>

            {draft.demographic?.disability_status !== "NONE" && (
              <div className="mt-4 p-4 border border-line rounded-md bg-paper space-y-4">
                <h3 className="text-sm font-semibold text-ink">Disability Details (Divyangjan)</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-x-4">
                  <Select
                    id="wizard-disability-type"
                    label="Disability Type"
                    value={draft.demographic?.disability_type || ""}
                    onChange={(e) => nested("demographic", "disability_type", e.target.value)}
                  >
                    <option value="">Select Disability Type</option>
                    {DISABILITY_TYPE_OPTIONS.map((t) => (
                      <option key={t.value} value={t.value}>
                        {t.label}
                      </option>
                    ))}
                  </Select>

                  <Input
                    id="wizard-disability-pct"
                    label="Disability Percentage (%)"
                    type="number"
                    min={1}
                    max={100}
                    placeholder="e.g. 45"
                    value={draft.demographic?.disability_percentage ?? ""}
                    onChange={(e) =>
                      nested(
                        "demographic",
                        "disability_percentage",
                        e.target.value === "" ? null : Number(e.target.value)
                      )
                    }
                  />

                  <Input
                    id="wizard-udid"
                    label="UDID / Certificate No."
                    placeholder="e.g. MH1234567890"
                    value={draft.demographic?.udid_number || ""}
                    onChange={(e) => nested("demographic", "udid_number", e.target.value)}
                  />
                </div>
              </div>
            )}
          </section>
        );

      case 5:
        return (
          <section className="space-y-6">
            <div className="border-b border-line pb-3 mb-4">
              <h2 className="text-xl font-semibold text-ink">Step 5 — Address &amp; Location</h2>
              <p className="text-xs text-ink-soft">
                Permanent domicile and current communication addresses.
              </p>
            </div>

            {/* Permanent Address */}
            <div className="p-4 bg-white border border-line rounded-md space-y-4">
              <h3 className="text-sm font-semibold text-ink border-b border-line pb-2">
                A. Permanent Address (Domicile)
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-x-5">
                <Input
                  id="perm-addr-1"
                  label="Address Line 1 (House No. / Street)"
                  placeholder="e.g. Flat 101, Shivneri Heights"
                  value={draft.location?.address_line_1 || ""}
                  onChange={(e) => nested("location", "address_line_1", e.target.value)}
                />
                <Input
                  id="perm-addr-2"
                  label="Address Line 2 (Landmark / Area)"
                  placeholder="e.g. Near Ganpati Temple"
                  value={draft.location?.address_line_2 || ""}
                  onChange={(e) => nested("location", "address_line_2", e.target.value)}
                />
                <Select
                  id="perm-state"
                  label="Permanent State"
                  value={draft.location?.state || ""}
                  onChange={(e) => {
                    const newState = e.target.value;
                    setDraft((cur) => ({
                      ...cur,
                      location: {
                        ...(cur.location || {}),
                        state: newState,
                        district: "", // reset district on state switch
                      },
                    }));
                  }}
                >
                  <option value="">Select State</option>
                  {INDIAN_STATES.map((st) => (
                    <option key={st} value={st}>
                      {st}
                    </option>
                  ))}
                </Select>

                {INDIAN_STATES_DISTRICTS[draft.location?.state]?.length > 0 ? (
                  <Select
                    id="perm-district"
                    label="District"
                    value={draft.location?.district || ""}
                    onChange={(e) => nested("location", "district", e.target.value)}
                  >
                    <option value="">Select District</option>
                    {INDIAN_STATES_DISTRICTS[draft.location?.state].map((dst) => (
                      <option key={dst} value={dst}>
                        {dst}
                      </option>
                    ))}
                  </Select>
                ) : (
                  <Input
                    id="perm-district-text"
                    label="District"
                    placeholder="Enter district name"
                    value={draft.location?.district || ""}
                    onChange={(e) => nested("location", "district", e.target.value)}
                  />
                )}

                <Input
                  id="perm-city"
                  label="Village / Town / City"
                  placeholder="e.g. Pune / Baramati"
                  value={draft.location?.village_city || ""}
                  onChange={(e) => nested("location", "village_city", e.target.value)}
                />

                <Input
                  id="perm-pincode"
                  label="PIN Code (6 digits)"
                  type="tel"
                  maxLength={6}
                  placeholder="e.g. 411005"
                  value={draft.location?.pincode || ""}
                  error={fieldErrors?.pincode}
                  onChange={(e) => {
                    const val = e.target.value.replace(/\D/g, "").slice(0, 6);
                    nested("location", "pincode", val);
                    onFieldChange("pincode", validatePincode, val);
                  }}
                />

                <Select
                  id="perm-area-type"
                  label="Area Type"
                  value={draft.location?.area_type || "URBAN"}
                  onChange={(e) => nested("location", "area_type", e.target.value)}
                >
                  {AREA_TYPE_OPTIONS.map((a) => (
                    <option key={a.value} value={a.value}>
                      {a.label}
                    </option>
                  ))}
                </Select>
              </div>
            </div>

            {/* Same as Permanent Checkbox */}
            <div className="p-3 bg-paper border border-line rounded-md flex items-center gap-3">
              <input
                id="same-as-perm"
                type="checkbox"
                className="w-4 h-4 accent-accent-ink cursor-pointer"
                checked={Boolean(draft.location?.same_as_permanent)}
                onChange={(e) => {
                  const checked = e.target.checked;
                  nested("location", "same_as_permanent", checked);
                }}
              />
              <label htmlFor="same-as-perm" className="text-sm font-medium text-ink cursor-pointer">
                Current address is same as permanent address
              </label>
            </div>

            {/* Current Address (if different) */}
            {!draft.location?.same_as_permanent && (
              <div className="p-4 bg-white border border-line rounded-md space-y-4">
                <h3 className="text-sm font-semibold text-ink border-b border-line pb-2">
                  B. Current Address (Communication)
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-x-5">
                  <Input
                    id="curr-addr-1"
                    label="Address Line 1"
                    placeholder="e.g. Hostel / Room No."
                    value={draft.location?.current_address?.address_line_1 || ""}
                    onChange={(e) => nestedCurrentAddress("address_line_1", e.target.value)}
                  />
                  <Input
                    id="curr-addr-2"
                    label="Address Line 2"
                    placeholder="e.g. Area / Landmark"
                    value={draft.location?.current_address?.address_line_2 || ""}
                    onChange={(e) => nestedCurrentAddress("address_line_2", e.target.value)}
                  />
                  <Select
                    id="curr-state"
                    label="Current State"
                    value={draft.location?.current_address?.state || ""}
                    onChange={(e) => {
                      const newState = e.target.value;
                      setDraft((cur) => ({
                        ...cur,
                        location: {
                          ...(cur.location || {}),
                          current_address: {
                            ...(cur.location?.current_address || {}),
                            state: newState,
                            district: "",
                          },
                        },
                      }));
                    }}
                  >
                    <option value="">Select State</option>
                    {INDIAN_STATES.map((st) => (
                      <option key={st} value={st}>
                        {st}
                      </option>
                    ))}
                  </Select>

                  {INDIAN_STATES_DISTRICTS[draft.location?.current_address?.state]?.length > 0 ? (
                    <Select
                      id="curr-district"
                      label="Current District"
                      value={draft.location?.current_address?.district || ""}
                      onChange={(e) => nestedCurrentAddress("district", e.target.value)}
                    >
                      <option value="">Select District</option>
                      {INDIAN_STATES_DISTRICTS[draft.location?.current_address?.state].map((dst) => (
                        <option key={dst} value={dst}>
                          {dst}
                        </option>
                      ))}
                    </Select>
                  ) : (
                    <Input
                      id="curr-district-text"
                      label="Current District"
                      value={draft.location?.current_address?.district || ""}
                      onChange={(e) => nestedCurrentAddress("district", e.target.value)}
                    />
                  )}

                  <Input
                    id="curr-city"
                    label="Current City / Town"
                    placeholder="e.g. Mumbai / Pune"
                    value={draft.location?.current_address?.village_city || ""}
                    onChange={(e) => nestedCurrentAddress("village_city", e.target.value)}
                  />

                  <Input
                    id="curr-pincode"
                    label="Current PIN Code (6 digits)"
                    type="tel"
                    maxLength={6}
                    placeholder="e.g. 400001"
                    value={draft.location?.current_address?.pincode || ""}
                    error={fieldErrors?.current_pincode}
                    onChange={(e) => {
                      const val = e.target.value.replace(/\D/g, "").slice(0, 6);
                      nestedCurrentAddress("pincode", val);
                      onFieldChange("current_pincode", validatePincode, val);
                    }}
                  />

                  <Select
                    id="curr-area-type"
                    label="Area Type"
                    value={draft.location?.current_address?.area_type || "URBAN"}
                    onChange={(e) => nestedCurrentAddress("area_type", e.target.value)}
                  >
                    {AREA_TYPE_OPTIONS.map((a) => (
                      <option key={a.value} value={a.value}>
                        {a.label}
                      </option>
                    ))}
                  </Select>
                </div>
              </div>
            )}
          </section>
        );

      case 6:
        return (
          <section className="space-y-4">
            <div className="border-b border-line pb-3 mb-4">
              <h2 className="text-xl font-semibold text-ink">Step 6 — Additional &amp; Category Specifics</h2>
              <p className="text-xs text-ink-soft">
                Contextual details based on your selected profile roles (Student, Farmer, Business, etc.).
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-5">
              <Input
                id="wizard-occupation"
                label="General Occupation / Designation"
                placeholder={placeholders.occupation || "e.g. Software Engineer / Farming / Student"}
                value={draft.demographic?.occupation || ""}
                onChange={(e) => nested("demographic", "occupation", e.target.value)}
              >
              </Input>
            </div>

            {isStudent && (
              <div className="p-4 border border-line rounded-md bg-paper space-y-3">
                <h3 className="text-sm font-semibold text-ink">Student Specifics</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-x-4">
                  <Select
                    id="wizard-hostel"
                    label="Accommodation Type"
                    value={draft.demographic?.student_hostel_status || ""}
                    onChange={(e) => nested("demographic", "student_hostel_status", e.target.value)}
                  >
                    <option value="">Select Accommodation</option>
                    <option value="DAY_SCHOLAR">Day Scholar</option>
                    <option value="GOVERNMENT_HOSTEL">Government Hostel</option>
                    <option value="PRIVATE_HOSTEL_RENT">Private Hostel / PG</option>
                  </Select>

                  <Select
                    id="wizard-admission-quota"
                    label="Admission Category / Quota"
                    value={draft.demographic?.student_admission_quota || ""}
                    onChange={(e) => nested("demographic", "student_admission_quota", e.target.value)}
                  >
                    <option value="">Select Admission Quota</option>
                    <option value="CAP_ROUND_MERIT">CAP Round / Government Merit</option>
                    <option value="MANAGEMENT_QUOTA">Management Quota</option>
                    <option value="SPORTS_QUOTA">Sports / Special Quota</option>
                  </Select>
                </div>
              </div>
            )}

            {isFarmer && (
              <div className="p-4 border border-line rounded-md bg-paper space-y-3">
                <h3 className="text-sm font-semibold text-ink">Farmer Specifics</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-x-4">
                  <Select
                    id="wizard-farmer-cat"
                    label="Farmer Category"
                    value={draft.demographic?.farmer_category || ""}
                    onChange={(e) => nested("demographic", "farmer_category", e.target.value)}
                  >
                    <option value="">Select Category</option>
                    <option value="MARGINAL">Marginal (Under 1 Hectare)</option>
                    <option value="SMALL">Small (1 - 2 Hectares)</option>
                    <option value="SEMI_MEDIUM">Semi-Medium (2 - 4 Hectares)</option>
                    <option value="LARGE">Large (Above 4 Hectares)</option>
                  </Select>

                  <Select
                    id="wizard-irrigation"
                    label="Irrigation Type"
                    value={draft.demographic?.farmer_irrigation_type || ""}
                    onChange={(e) => nested("demographic", "farmer_irrigation_type", e.target.value)}
                  >
                    <option value="">Select Irrigation</option>
                    <option value="IRRIGATED">Well / Canal Irrigated</option>
                    <option value="DRIP_SPRINKLER">Drip / Sprinkler</option>
                    <option value="RAIN_FED">Rain-fed (Dryland)</option>
                  </Select>

                  <Input
                    id="wizard-crops"
                    label="Major Crops Grown"
                    placeholder="e.g. Cotton, Soyabean, Sugarcane"
                    value={draft.demographic?.farmer_crop_types || ""}
                    onChange={(e) => nested("demographic", "farmer_crop_types", e.target.value)}
                  />
                </div>
              </div>
            )}

            {isBusiness && (
              <div className="p-4 border border-line rounded-md bg-paper space-y-3">
                <h3 className="text-sm font-semibold text-ink">Business &amp; Enterprise Details</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-x-4">
                  <Input
                    id="wizard-biz-nature"
                    label="Nature of Business"
                    placeholder="e.g. Retail Trading / Food Processing"
                    value={draft.demographic?.business_nature || ""}
                    onChange={(e) => nested("demographic", "business_nature", e.target.value)}
                  />
                  <Select
                    id="wizard-msme"
                    label="Udyam / MSME Registered"
                    value={String(draft.demographic?.business_msme_registered)}
                    onChange={(e) =>
                      nested("demographic", "business_msme_registered", e.target.value === "true")
                    }
                  >
                    <option value="false">No</option>
                    <option value="true">Yes (Udyam Registered)</option>
                  </Select>
                </div>
              </div>
            )}

            {isEmployee && (
              <div className="p-4 border border-line rounded-md bg-paper space-y-3">
                <h3 className="text-sm font-semibold text-ink">Employment Sector</h3>
                <Select
                  id="wizard-emp-sector"
                  label="Sector"
                  value={draft.demographic?.employee_sector || ""}
                  onChange={(e) => nested("demographic", "employee_sector", e.target.value)}
                >
                  <option value="">Select Sector</option>
                  <option value="GOVERNMENT">State / Central Government</option>
                  <option value="PSU">Public Sector Undertaking (PSU)</option>
                  <option value="PRIVATE_ORG">Organized Private Sector</option>
                  <option value="UNORGANIZED">Unorganized / Contractual</option>
                </Select>
              </div>
            )}
          </section>
        );

      case 7:
        return (
          <section className="space-y-6">
            <div className="border-b border-line pb-3 mb-2">
              <h2 className="text-xl font-semibold text-ink">Step 7 — Review &amp; Submit Profile</h2>
              <p className="text-xs text-ink-soft">
                Verify all information before final submission. Click “Edit” on any section to make changes.
              </p>
            </div>

            {/* Section 1 Review */}
            <Section title="1. Basic Information" onEdit={() => setCurrentStep(1)}>
              <Row
                label="Full Name"
                value={buildFullName(draft.firstName, draft.middleName, draft.lastName)}
              />
              <Row label="Date of Birth" value={`${draft.date_of_birth} (Age: ${age ?? "—"})`} />
              <Row label="Gender" value={formatOption(GENDER_OPTIONS, draft.gender)} />
              <Row
                label="Primary Category"
                value={formatOption(CITIZEN_TYPE_OPTIONS, draft.citizen_type)}
              />
              <Row
                label="Profile Types"
                value={
                  draft.profile_types?.length > 0
                    ? draft.profile_types
                        .map((t) => PROFILE_TYPE_OPTIONS.find((o) => o.value === t)?.label || t)
                        .join(", ")
                    : "General"
                }
              />
              <Row label="Mobile Number" value={draft.mobile_number} />
              <Row label="Registered Email" value={authenticatedEmail || draft.email_id} />
            </Section>

            {/* Section 2 Review */}
            <Section title="2. Education Qualifications" onEdit={() => setCurrentStep(2)}>
              {educationRecords.length === 0 ? (
                <p className="text-xs text-ink-soft py-2">No education records added.</p>
              ) : (
                educationRecords.map((r, i) => {
                  const d = r.details || {};
                  return (
                    <Row
                      key={i}
                      label={formatEducationLevel(r.level)}
                      value={[
                        d.degree ? (d.degree === "OTHER_UG" || d.degree === "OTHER_PG" ? d.other_degree || d.degree : d.degree) : null,
                        d.branch || d.stream,
                        d.institute || d.university,
                        d.cgpa ? `CGPA ${d.cgpa}/${d.cgpa_scale || 10}` : null,
                        r.percentage ? `${r.percentage}%` : null,
                        r.passing_year ? `Year ${r.passing_year}` : null,
                        r.is_current ? "(Current)" : null,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    />
                  );
                })
              )}
            </Section>

            {/* Section 3 Review */}
            <Section title="3. Family & Income" onEdit={() => setCurrentStep(3)}>
              <Row
                label="Annual Family Income"
                value={
                  draft.financial?.annual_income !== null && draft.financial?.annual_income !== undefined
                    ? `₹${Number(draft.financial.annual_income).toLocaleString("en-IN")}`
                    : "Not provided"
                }
              />
              <Row
                label="Employment Status"
                value={formatOption(EMPLOYMENT_STATUS_OPTIONS, draft.financial?.employment_status)}
              />
              <Row
                label="Income Source"
                value={formatOption(INCOME_SOURCE_OPTIONS, draft.financial?.income_source)}
              />
              <Row
                label="Poverty Category"
                value={formatOption(POVERTY_CATEGORY_OPTIONS, draft.financial?.poverty_category)}
              />
              <Row label="Family Members" value={draft.demographic?.family_size} />
              <Row
                label="Land Holding"
                value={
                  draft.financial?.land_holding_size !== null && draft.financial?.land_holding_size !== undefined
                    ? `${draft.financial.land_holding_size} Hectares`
                    : "None"
                }
              />
              <Row label="BPL Card Holder" value={draft.financial?.is_bpl_card_holder ? "Yes" : "No"} />
              <Row
                label="Income Tax Payer"
                value={draft.financial?.is_income_tax_payer ? "Yes" : "No"}
              />
            </Section>

            {/* Section 4 Review */}
            <Section title="4. Social & Special Status" onEdit={() => setCurrentStep(4)}>
              <Row
                label="Social Category"
                value={
                  draft.demographic?.social_category === "OTHER"
                    ? `Other (${draft.demographic?.other_social_category || "Not specified"})`
                    : formatOption(SOCIAL_CATEGORIES, draft.demographic?.social_category)
                }
              />
              <Row
                label="Marital Status"
                value={formatOption(MARITAL_STATUS_OPTIONS, draft.demographic?.marital_status)}
              />
              <Row
                label="Disability Status"
                value={formatOption(DISABILITY_STATUS_OPTIONS, draft.demographic?.disability_status)}
              />
              {draft.demographic?.disability_status !== "NONE" && (
                <>
                  <Row
                    label="Disability Type"
                    value={formatOption(DISABILITY_TYPE_OPTIONS, draft.demographic?.disability_type)}
                  />
                  <Row
                    label="Disability Percentage"
                    value={
                      draft.demographic?.disability_percentage
                        ? `${draft.demographic.disability_percentage}%`
                        : "Not provided"
                    }
                  />
                  <Row label="UDID Number" value={draft.demographic?.udid_number} />
                </>
              )}
            </Section>

            {/* Section 5 Review */}
            <Section title="5. Address & Location" onEdit={() => setCurrentStep(5)}>
              <Row
                label="Permanent Address"
                value={[
                  draft.location?.address_line_1,
                  draft.location?.address_line_2,
                  draft.location?.village_city,
                  draft.location?.district,
                  draft.location?.state,
                  draft.location?.pincode ? `PIN: ${draft.location.pincode}` : null,
                ]
                  .filter(Boolean)
                  .join(", ") || "Not provided"}
              />
              <Row
                label="Current Address"
                value={
                  draft.location?.same_as_permanent
                    ? "Same as permanent address"
                    : [
                        draft.location?.current_address?.address_line_1,
                        draft.location?.current_address?.address_line_2,
                        draft.location?.current_address?.village_city,
                        draft.location?.current_address?.district,
                        draft.location?.current_address?.state,
                        draft.location?.current_address?.pincode
                          ? `PIN: ${draft.location.current_address.pincode}`
                          : null,
                      ]
                        .filter(Boolean)
                        .join(", ") || "Not provided"
                }
              />
              <Row label="Area Type" value={draft.location?.area_type} />
            </Section>

            {/* Section 6 Review */}
            <Section title="6. Specifics" onEdit={() => setCurrentStep(6)}>
              <Row label="Occupation" value={draft.demographic?.occupation} />
              {isStudent && (
                <>
                  <Row label="Accommodation" value={draft.demographic?.student_hostel_status} />
                  <Row label="Admission Quota" value={draft.demographic?.student_admission_quota} />
                </>
              )}
              {isFarmer && (
                <>
                  <Row label="Farmer Category" value={draft.demographic?.farmer_category} />
                  <Row label="Irrigation" value={draft.demographic?.farmer_irrigation_type} />
                  <Row label="Crops" value={draft.demographic?.farmer_crop_types} />
                </>
              )}
              {isBusiness && (
                <>
                  <Row label="Business Nature" value={draft.demographic?.business_nature} />
                  <Row
                    label="MSME Registered"
                    value={draft.demographic?.business_msme_registered ? "Yes" : "No"}
                  />
                </>
              )}
            </Section>
          </section>
        );

      default:
        return null;
    }
  };

  // -------------------------------------------------------------------------
  // Main Return
  // -------------------------------------------------------------------------
  return (
    <div className="max-w-4xl mx-auto pb-16">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6 border-b border-line pb-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-display font-semibold text-ink">
            {editing || status === "needs-profile" ? "Citizen Profile Wizard" : "My Profile"}
          </h1>
          <p className="text-xs sm:text-sm text-ink-soft mb-0">
            {editing || status === "needs-profile"
              ? "Complete your 7-step profile to unlock and apply for government welfare schemes & scholarships."
              : "Canonical profile record for eligibility evaluation and scheme applications."}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {!editing && status !== "needs-profile" ? (
            <>
              <Button to="/check-eligibility" size="sm">
                Check Eligibility
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  setDraft(initProfileState(citizen, authenticatedEmail));
                  setEditing(true);
                  setCurrentStep(1);
                }}
              >
                Edit Profile
              </Button>
            </>
          ) : (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                if (status === "needs-profile") {
                  navigate("/");
                } else {
                  setDraft(initProfileState(citizen, authenticatedEmail));
                  setEditing(false);
                }
              }}
            >
              {status === "needs-profile" ? "Exit" : "View Profile"}
            </Button>
          )}
        </div>
      </div>

      {/* Notifications */}
      {error && (
        <div className="mb-6">
          <ErrorState title="Notice" message={error} />
        </div>
      )}
      {saveSuccessMsg && (
        <div className="mb-6 p-3 bg-ok-tint text-ok-ink text-sm rounded border border-ok/30 flex items-center gap-2">
          <span>✓</span> {saveSuccessMsg}
        </div>
      )}

      {/* WIZARD MODE */}
      {editing || status === "needs-profile" ? (
        <div className="space-y-6">
          {/* Progress Indicator Bar */}
          <div className="bg-white border border-line rounded-md p-4 shadow-xs">
            <div className="flex items-center justify-between text-xs font-semibold text-ink mb-2">
              <span>
                Step {currentStep} of {WIZARD_STEPS.length}: {WIZARD_STEPS[currentStep - 1].name}
              </span>
              <span>{Math.round((currentStep / WIZARD_STEPS.length) * 100)}% Completed</span>
            </div>
            <div className="w-full bg-paper rounded-full h-2 overflow-hidden mb-4">
              <div
                className="bg-accent-ink h-full transition-all duration-300"
                style={{ width: `${(currentStep / WIZARD_STEPS.length) * 100}%` }}
              />
            </div>

            {/* Stepper Dots/Tabs */}
            <div className="grid grid-cols-7 gap-1 sm:gap-2">
              {WIZARD_STEPS.map((step) => {
                const isActive = step.id === currentStep;
                const isPassed = step.id < currentStep;
                return (
                  <button
                    key={step.id}
                    type="button"
                    onClick={() => {
                      if (validateCurrentStep(currentStep) || isPassed) {
                        setCurrentStep(step.id);
                        window.scrollTo({ top: 0, behavior: "smooth" });
                      }
                    }}
                    className={`py-2 px-1 text-center rounded text-[11px] sm:text-xs font-medium transition-all ${
                      isActive
                        ? "bg-accent-tint text-accent-ink border border-accent font-semibold shadow-xs"
                        : isPassed
                        ? "bg-paper text-ink hover:bg-line/40 cursor-pointer"
                        : "text-ink-soft/60 cursor-default"
                    }`}
                  >
                    <span className="block font-mono text-[10px]">{step.id}</span>
                    <span className="hidden md:inline truncate block">{step.name}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Step Form Card */}
          <Card className="p-6">{renderStepContent()}</Card>

          {/* Navigation Controls */}
          <div className="flex flex-wrap items-center justify-between gap-3 pt-4 border-t border-line">
            <Button
              type="button"
              variant="secondary"
              onClick={handlePrevStep}
              disabled={currentStep === 1 || savingDraft || submitting}
            >
              ← Previous Step
            </Button>

            <div className="flex items-center gap-3">
              <Button
                type="button"
                variant="secondary"
                onClick={handleSaveDraft}
                disabled={savingDraft || submitting}
              >
                {savingDraft ? "Saving Draft..." : "Save Draft"}
              </Button>

              {currentStep < 7 ? (
                <Button
                  type="button"
                  onClick={handleNextStep}
                  disabled={savingDraft || submitting}
                >
                  Next Step →
                </Button>
              ) : (
                <Button
                  type="button"
                  onClick={handleSubmitProfile}
                  disabled={savingDraft || submitting}
                >
                  {submitting ? "Submitting Profile..." : "Submit Profile ✓"}
                </Button>
              )}
            </div>
          </div>
        </div>
      ) : (
        /* READ-ONLY VIEW MODE */
        <div className="space-y-7">
          {savedAnswers && formSections && formSections.length > 0 && (
            <section>
              <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                <h2 className="text-lg font-semibold mb-0">Eligibility Form Answers</h2>
                <Button to="/check-eligibility?edit=1" size="sm" variant="secondary">
                  Review &amp; Edit Answers
                </Button>
              </div>
              <Card>
                {formSections.map((section) => {
                  const answered = section.questions.filter(
                    (q) => savedAnswers[q.question_code] !== undefined
                  );
                  if (answered.length === 0) return null;
                  return (
                    <div key={section.section_id} className="mb-4 last:mb-0">
                      <h3 className="text-sm font-semibold text-accent-ink mb-2">
                        {section.section_name}
                      </h3>
                      <dl className="divide-y divide-line">
                        {answered.map((q) => (
                          <Row
                            key={q.question_id}
                            label={q.question_text}
                            value={formatAnswer(savedAnswers[q.question_code])}
                          />
                        ))}
                      </dl>
                    </div>
                  );
                })}
              </Card>
            </section>
          )}

          {/* Basic Personal Details */}
          <Section
            title="Personal & Identity"
            onEdit={() => {
              setDraft(initProfileState(citizen, authenticatedEmail));
              setEditing(true);
              setCurrentStep(1);
            }}
          >
            <Row label="Full Name" value={citizen.full_name} />
            <Row
              label="Date of Birth"
              value={`${citizen.date_of_birth} (Age: ${calculateAge(citizen.date_of_birth) ?? "—"})`}
            />
            <Row label="Gender" value={formatOption(GENDER_OPTIONS, citizen.gender)} />
            <Row
              label="Citizen Category"
              value={formatOption(CITIZEN_TYPE_OPTIONS, citizen.citizen_type)}
            />
            <Row
              label="Profile Types"
              value={citizen.profile_types
                ?.map((t) => PROFILE_TYPE_OPTIONS.find((o) => o.value === t)?.label || t)
                .join(", ")}
            />
            <Row label="Mobile" value={citizen.mobile_number} />
            <Row label="Registered Email" value={authenticatedEmail || citizen.email_id} />
          </Section>

          {/* Education Records */}
          <Section
            title="Education Qualifications"
            onEdit={() => {
              setDraft(initProfileState(citizen, authenticatedEmail));
              setEditing(true);
              setCurrentStep(2);
            }}
          >
            {educationRecords.length === 0 ? (
              <p className="text-xs text-ink-soft py-2">No education records on file.</p>
            ) : (
              educationRecords.map((r, i) => {
                const d = r.details || {};
                return (
                  <Row
                    key={i}
                    label={formatEducationLevel(r.level)}
                    value={[
                      d.degree ? (d.degree === "OTHER_UG" || d.degree === "OTHER_PG" ? d.other_degree || d.degree : d.degree) : null,
                      d.branch || d.stream,
                      d.institute || d.university,
                      d.cgpa ? `CGPA ${d.cgpa}/${d.cgpa_scale || 10}` : null,
                      r.percentage ? `${r.percentage}%` : null,
                      r.passing_year ? `Year ${r.passing_year}` : null,
                      r.is_current ? "(Current)" : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  />
                );
              })
            )}
          </Section>

          {/* Financial Details */}
          <Section
            title="Financial & Household"
            onEdit={() => {
              setDraft(initProfileState(citizen, authenticatedEmail));
              setEditing(true);
              setCurrentStep(3);
            }}
          >
            <Row
              label="Annual Family Income"
              value={
                citizen.financial?.annual_income !== null && citizen.financial?.annual_income !== undefined
                  ? `₹${Number(citizen.financial.annual_income).toLocaleString("en-IN")}`
                  : null
              }
            />
            <Row
              label="Employment Status"
              value={formatOption(EMPLOYMENT_STATUS_OPTIONS, citizen.financial?.employment_status)}
            />
            <Row
              label="Income Source"
              value={formatOption(INCOME_SOURCE_OPTIONS, citizen.financial?.income_source)}
            />
            <Row
              label="Poverty Category"
              value={formatOption(POVERTY_CATEGORY_OPTIONS, citizen.financial?.poverty_category)}
            />
            <Row label="Family Size" value={citizen.demographic?.family_size} />
            <Row
              label="Land Holding"
              value={
                citizen.financial?.land_holding_size !== null &&
                citizen.financial?.land_holding_size !== undefined
                  ? `${citizen.financial.land_holding_size} Hectares`
                  : null
              }
            />
            <Row
              label="BPL Card Holder"
              value={citizen.financial?.is_bpl_card_holder ? "Yes" : "No"}
            />
            <Row
              label="Income Tax Payer"
              value={citizen.financial?.is_income_tax_payer ? "Yes" : "No"}
            />
          </Section>

          {/* Social Details */}
          <Section
            title="Social & Special Categories"
            onEdit={() => {
              setDraft(initProfileState(citizen, authenticatedEmail));
              setEditing(true);
              setCurrentStep(4);
            }}
          >
            <Row
              label="Social Category"
              value={
                citizen.demographic?.social_category === "OTHER"
                  ? `Other (${citizen.demographic?.type_specific_metadata?.other_social_category || "Not specified"})`
                  : formatOption(SOCIAL_CATEGORIES, citizen.demographic?.social_category)
              }
            />
            <Row
              label="Marital Status"
              value={formatOption(MARITAL_STATUS_OPTIONS, citizen.demographic?.marital_status)}
            />
            <Row
              label="Disability Status"
              value={formatOption(DISABILITY_STATUS_OPTIONS, citizen.demographic?.disability_status)}
            />
            <Row label="Disability Type" value={citizen.demographic?.type_specific_metadata?.disability_type} />
            <Row
              label="Disability Percentage"
              value={
                citizen.demographic?.type_specific_metadata?.disability_percentage
                  ? `${citizen.demographic.type_specific_metadata.disability_percentage}%`
                  : null
              }
            />
            <Row label="UDID Number" value={citizen.demographic?.type_specific_metadata?.udid_number} />
          </Section>

          {/* Address & Location */}
          <Section
            title="Address & Location"
            onEdit={() => {
              setDraft(initProfileState(citizen, authenticatedEmail));
              setEditing(true);
              setCurrentStep(5);
            }}
          >
            <Row
              label="Permanent Address"
              value={[
                citizen.location?.address_line_1,
                citizen.location?.address_line_2,
                citizen.location?.village_city,
                citizen.location?.district,
                citizen.location?.state,
                citizen.location?.pincode ? `PIN: ${citizen.location.pincode}` : null,
              ]
                .filter(Boolean)
                .join(", ") || null}
            />
            <Row
              label="Current Address"
              value={
                citizen.location?.same_as_permanent
                  ? "Same as permanent address"
                  : [
                      citizen.location?.current_address?.address_line_1,
                      citizen.location?.current_address?.address_line_2,
                      citizen.location?.current_address?.village_city,
                      citizen.location?.current_address?.district,
                      citizen.location?.current_address?.state,
                      citizen.location?.current_address?.pincode
                        ? `PIN: ${citizen.location.current_address.pincode}`
                        : null,
                    ]
                      .filter(Boolean)
                      .join(", ") || "Not provided"
              }
            />
            <Row label="Area Type" value={citizen.location?.area_type} />
          </Section>
        </div>
      )}
    </div>
  );
}
