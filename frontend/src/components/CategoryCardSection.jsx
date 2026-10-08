import { useNavigate } from "react-router-dom";
import {
  GraduationCap,
  BookOpen,
  Tractor,
  Users,
  Accessibility,
  Layers,
  ArrowRight,
} from "lucide-react";
import { countSchemesByCitizenType, countSchemesByLens } from "../utils/schemeInsights";

const CATEGORIES = [
  {
    id: "college-student",
    title: "College Student",
    description: "Higher education, scholarships & course assistance",
    image: "/College Students.webp",
    icon: GraduationCap,
    targetUrl: "/schemes?discovery=STUDENT",
    filterKind: "persona",
    filterValue: "STUDENT",
  },
  {
    id: "school-student",
    title: "School Student",
    description: "School education, stipends & student welfare",
    image: "/School Student Image_1.webp",
    icon: BookOpen,
    targetUrl: "/schemes?discovery=STUDENT",
    filterKind: "persona",
    filterValue: "STUDENT",
  },
  {
    id: "farmer",
    title: "Farmer",
    description: "Agriculture, crop insurance & landholding support",
    image: "/Farmers.webp",
    icon: Tractor,
    targetUrl: "/schemes?discovery=FARMER",
    filterKind: "persona",
    filterValue: "FARMER",
  },
  {
    id: "pensioner",
    title: "Senior Citizen / Pensioner",
    description: "Old age pension, financial security & assistance",
    image: "/pensioners.webp",
    icon: Users,
    targetUrl: "/schemes?discovery=SENIOR",
    filterKind: "persona",
    filterValue: "SENIOR",
  },
  {
    id: "divyang",
    title: "Divyang / PwD",
    description: "Disability assistance, aid & inclusive welfare",
    image: "/Divyang_new.webp",
    icon: Accessibility,
    targetUrl: "/schemes?discovery=disability_status",
    filterKind: "lens",
    filterValue: "disability_status",
  },
  {
    id: "other",
    title: "Other Citizen Schemes",
    description: "General welfare, employment, health & family support",
    image: "/others images.webp",
    icon: Layers,
    targetUrl: "/schemes?discovery=GENERAL",
    filterKind: "persona",
    filterValue: "GENERAL",
  },
];

export default function CategoryCardSection({ schemes, schemesWithRules }) {
  const navigate = useNavigate();

  const getSchemeCount = (cat) => {
    if (!schemesWithRules || schemesWithRules.length === 0) {
      if (schemes && schemes.length > 0) {
        if (cat.filterKind === "persona") {
          const direct = schemes.filter(
            (s) => s.target_persona === cat.filterValue || s.scheme_category === cat.filterValue
          ).length;
          return direct > 0 ? direct : null;
        }
      }
      return null;
    }

    if (cat.filterKind === "persona") {
      const count = countSchemesByCitizenType(schemesWithRules, cat.filterValue);
      return count > 0 ? count : null;
    }
    if (cat.filterKind === "lens") {
      const count = countSchemesByLens(schemesWithRules, cat.filterValue);
      return count > 0 ? count : null;
    }
    return null;
  };

  return (
    <section className="mb-12">
      <div className="flex items-baseline justify-between gap-4 mb-4 flex-wrap">
        <div>
          <h2 className="text-2xl font-semibold text-ink tracking-tight mb-1">
            Explore schemes by category
          </h2>
          <p className="text-sm text-ink-soft max-w-[65ch]">
            Browse welfare schemes tailored to your profile, occupation, or specific eligibility requirements.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {CATEGORIES.map((cat) => {
          const Icon = cat.icon;
          const count = getSchemeCount(cat);

          return (
            <div
              key={cat.id}
              role="button"
              tabIndex={0}
              onClick={() => navigate(cat.targetUrl)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  navigate(cat.targetUrl);
                }
              }}
              className="group relative overflow-hidden rounded-md border border-line bg-ink text-white cursor-pointer shadow-sm hover:shadow-md hover:border-accent transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent aspect-[16/11] flex flex-col justify-end p-5"
            >
              {/* Background Image with lazy loading */}
              <img
                src={cat.image}
                alt={cat.title}
                loading="lazy"
                className="absolute inset-0 h-full w-full object-cover object-center group-hover:scale-105 transition-transform duration-300 ease-out brightness-[0.85]"
              />

              {/* Gradient overlay for readability */}
              <div
                className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/55 to-black/15"
                aria-hidden="true"
              />

              {/* Content overlay */}
              <div className="relative z-10">
                <div className="flex items-center justify-between gap-2 mb-2">
                  <div className="inline-flex items-center justify-center h-8 w-8 rounded-full bg-accent-tint/20 backdrop-blur-sm border border-accent/40 text-amber-300">
                    <Icon className="h-4.5 w-4.5" />
                  </div>
                  {count !== null && (
                    <span className="text-xs font-mono font-medium px-2 py-0.5 rounded bg-black/50 text-amber-200 border border-amber-400/30 backdrop-blur-sm">
                      {String(count).padStart(2, "0")} Schemes
                    </span>
                  )}
                </div>

                <h3 className="text-lg font-semibold text-white mb-1 group-hover:text-amber-200 transition-colors flex items-center justify-between">
                  <span>{cat.title}</span>
                  <ArrowRight className="h-4 w-4 opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all text-amber-300" />
                </h3>

                <p className="text-xs text-slate-200 line-clamp-2 leading-relaxed opacity-90 mb-0">
                  {cat.description}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
