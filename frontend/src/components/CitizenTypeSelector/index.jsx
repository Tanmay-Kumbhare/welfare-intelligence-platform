import { useNavigate } from "react-router-dom";
import {
  GraduationCap,
  Tractor,
  Users,
  HardHat,
  Venus,
  Accessibility,
  Trees,
  Home as HomeIcon,
  User,
} from "lucide-react";
import { countSchemesByCitizenType, countSchemesByLens } from "../../utils/schemeInsights";

// "profile" entries map directly to the real backend citizen_type column
// (FARMER | STUDENT | SENIOR | GENERAL) -- selecting one starts the actual
// eligibility profile with that type pre-selected.
//
// "lens" entries do NOT correspond to any backend citizen_type. They are
// discovery filters over real eligibility-rule parameters already stored
// in the database (Part 3/6: "treat it as an exploration/filter category
// only"). Selecting one takes the citizen to Explore, pre-filtered by
// that parameter -- never a fabricated eligibility outcome.
const CITIZEN_TYPES = [
  { kind: "profile", value: "STUDENT", label: "Student", icon: GraduationCap, blurb: "Education & course-based schemes" },
  { kind: "profile", value: "FARMER", label: "Farmer", icon: Tractor, blurb: "Land holding & agriculture schemes" },
  { kind: "profile", value: "SENIOR", label: "Senior Citizen", icon: Users, blurb: "Age & pension-based schemes" },
  { kind: "lens", value: "employment_status", label: "Worker / Labour", icon: HardHat, blurb: "Schemes that consider employment status" },
  { kind: "lens", value: "gender", label: "Women", icon: Venus, blurb: "Schemes that consider gender" },
  { kind: "lens", value: "disability_status", label: "PwD", icon: Accessibility, blurb: "Schemes that consider disability status" },
  { kind: "lens", value: "social_category", label: "Tribal / Indigenous", icon: Trees, blurb: "Schemes that consider social category" },
  { kind: "lens", value: "area_type", label: "Rural Household", icon: HomeIcon, blurb: "Schemes that consider area type" },
  { kind: "profile", value: "GENERAL", label: "General Citizen", icon: User, blurb: "Income & category-based schemes" },
];

export default function CitizenTypeSelector({ schemesWithRules }) {
  const navigate = useNavigate();

  const handleSelect = (type) => {
    if (type.kind === "profile") {
      navigate(`/check-eligibility?citizenType=${type.value}`);
    } else {
      navigate(`/explore?lens=${type.value}`);
    }
  };

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
      {CITIZEN_TYPES.map((type) => {
        const Icon = type.icon;
        const count = schemesWithRules
          ? type.kind === "profile"
            ? countSchemesByCitizenType(schemesWithRules, type.value)
            : countSchemesByLens(schemesWithRules, type.value)
          : null;

        return (
          <button
            key={type.value}
            onClick={() => handleSelect(type)}
            className="text-left bg-paper-raised border border-line p-4 hover:border-accent transition-colors focus-visible:outline-none group"
          >
            <Icon className="h-5 w-5 text-accent-ink mb-2" />
            <h3 className="text-sm mb-1">{type.label}</h3>
            <p className="text-xs text-ink-soft mb-0 leading-snug">{type.blurb}</p>
            {schemesWithRules && (
              <p className="text-xs mt-2 mb-0 font-mono text-ink-soft">
                {count > 0
                  ? `${count} rule-matched scheme${count === 1 ? "" : "s"}`
                  : "No matching rules"}
              </p>
            )}
          </button>
        );
      })}
    </div>
  );
}
