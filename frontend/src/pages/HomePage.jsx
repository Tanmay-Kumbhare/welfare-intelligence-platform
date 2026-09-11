import { useEffect, useState } from "react";
import { ArrowUpRight, ClipboardList, Lightbulb, Scale, ShieldCheck } from "lucide-react";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import Badge from "../components/ui/Badge";
import SectionHeader from "../components/ui/SectionHeader";
import { LoadingState, ErrorState, EmptyState } from "../components/ui/StatusStates";
import CitizenTypeSelector from "../components/CitizenTypeSelector";
import { schemeService } from "../services/api";
import { deriveCategoryCounts } from "../utils/schemeInsights";
import { categoryLabel } from "../utils/ruleFormat";

const FEATURED_LIMIT = 3;

const HOW_IT_WORKS = [
  {
    icon: ClipboardList,
    title: "Tell us about yourself",
    body: "Answer a short structured profile -- the same fields the eligibility engine actually checks.",
  },
  {
    icon: Scale,
    title: "Match against scheme rules",
    body: "Your profile is evaluated against every active scheme's stored rules, deterministically.",
  },
  {
    icon: Lightbulb,
    title: "Understand why you qualify (or don't)",
    body: "See the exact rule, your value, and the required value -- for every eligible and excluded scheme.",
  },
  {
    icon: ArrowUpRight,
    title: "Continue to official application",
    body: "Apply directly through the scheme's real government portal, with the required documents in hand.",
  },
];

export default function HomePage() {
  const [schemes, setSchemes] = useState(null);
  const [schemeDetails, setSchemeDetails] = useState(null);
  const [status, setStatus] = useState("loading"); // loading | ready | error

  const loadSchemes = () => {
    schemeService
      .getAll()
      .then(async (res) => {
        const list = res.data || [];
        setSchemes(list);
        setStatus("ready");
        // Fetch full rule detail for each scheme so citizen-type discovery
        // cards can show real, rule-grounded counts. Best-effort: if this
        // fails, the page still works, just without per-card counts.
        try {
          const details = await Promise.all(list.map((s) => schemeService.get(s.scheme_id)));
          setSchemeDetails(details.map((r) => r.data));
        } catch {
          setSchemeDetails(null);
        }
      })
      .catch(() => setStatus("error"));
  };

  useEffect(() => {
    loadSchemes();
  }, []);

  const categoryCounts = schemes ? deriveCategoryCounts(schemes) : [];
  const featured = schemes ? schemes.slice(0, FEATURED_LIMIT) : [];
  const officialSources = schemes
    ? [...new Set(schemes.map((s) => s.official_source_url).filter(Boolean))].slice(0, 4)
    : [];

  return (
    <div>
      {/* HERO */}
      <div className="pb-9 border-b border-line mb-9">
        <h1 className="text-[38px] leading-tight max-w-[16ch] mb-4.5">
          Know exactly why, not just whether.
        </h1>
        <p className="max-w-[62ch] text-[15px]">
          VidyaSetu helps citizens discover government welfare schemes and
          checks which ones you qualify for using structured, deterministic
          scheme rules -- stored in a real database, not estimated. If you
          don't qualify for a scheme, you can see the specific rule behind
          that result.
        </p>
        <div className="flex gap-3 flex-wrap mt-2">
          <Button to="/check-eligibility" variant="primary" size="lg">
            Check My Eligibility
          </Button>
          <Button to="/schemes" variant="secondary" size="lg">
            Explore Schemes
          </Button>
        </div>
      </div>

      {/* CITIZEN TYPE DISCOVERY */}
      <div className="mb-11">
        <SectionHeader title="What best describes you?" />
        <CitizenTypeSelector schemesWithRules={schemeDetails} />
        <p className="text-xs text-ink-soft mt-3 mb-0">
          Student, Farmer, Senior Citizen and General Citizen start a profile
          matched to your actual citizen record. The other categories filter
          schemes by real eligibility factors already in the database (like
          gender, area type, or employment status) rather than a guaranteed
          eligibility outcome.
        </p>
      </div>

      {/* FEATURED SCHEMES */}
      <div className="mb-11">
        <SectionHeader
          title="Available schemes"
          count={schemes ? schemes.length : undefined}
          action={
            <Button to="/schemes" variant="ghost" size="sm">
              View all schemes →
            </Button>
          }
        />

        {status === "loading" && <LoadingState label="Loading schemes from the database..." />}

        {status === "error" && (
          <ErrorState
            title="Couldn't load schemes"
            message="The scheme catalogue couldn't be reached right now."
            onRetry={loadSchemes}
          />
        )}

        {status === "ready" && featured.length === 0 && (
          <EmptyState
            title="No active schemes yet"
            message="Once schemes are added to the database, they'll appear here automatically."
          />
        )}

        {status === "ready" && featured.length > 0 && (
          <div className="grid sm:grid-cols-3 gap-4">
            {featured.map((s) => (
              <Card key={s.scheme_id} className="flex flex-col">
                <Badge variant="neutral" className="mb-3 self-start">
                  {categoryLabel(s.scheme_category)}
                </Badge>
                <h3 className="mb-1 text-base">{s.scheme_name}</h3>
                {s.department_name && (
                  <p className="text-xs text-ink-soft mb-3">{s.department_name}</p>
                )}
                <p className="text-sm mb-4 flex-1">{s.benefit_description || s.description}</p>
                <Button to={`/schemes/${s.scheme_id}`} variant="secondary" size="sm">
                  View details
                </Button>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* HOW IT WORKS */}
      <div className="mb-11">
        <SectionHeader title="How it works" />
        <div className="grid sm:grid-cols-2 gap-4">
          {HOW_IT_WORKS.map((step, i) => {
            const Icon = step.icon;
            return (
              <Card key={step.title} className="flex gap-4">
                <div className="shrink-0 h-9 w-9 rounded-full bg-accent-tint flex items-center justify-center font-mono text-sm text-accent-ink">
                  {i + 1}
                </div>
                <div>
                  <h3 className="text-sm mb-1 flex items-center gap-2">
                    <Icon className="h-4 w-4 text-accent-ink" />
                    {step.title}
                  </h3>
                  <p className="text-sm mb-0">{step.body}</p>
                </div>
              </Card>
            );
          })}
        </div>
      </div>

      {/* TRUST / SOURCE */}
      <div>
        <SectionHeader title="Where this data comes from" />
        <Card>
          <div className="flex gap-4">
            <ShieldCheck className="h-6 w-6 text-ok shrink-0" />
            <div>
              <p className="mb-3">
                Every scheme's eligibility rules, benefit description, and
                required documents are stored ahead of time from official
                government sources -- the same rules are applied to every
                citizen who checks eligibility, so results are consistent
                and repeatable.
              </p>
              {categoryCounts.length > 0 && (
                <p className="text-sm mb-3">
                  Schemes currently span{" "}
                  {categoryCounts
                    .map((c) => categoryLabel(c.category).toLowerCase())
                    .join(", ")}
                  .
                </p>
              )}
              {officialSources.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {officialSources.map((url) => {
                    let hostname = url;
                    try {
                      hostname = new URL(url).hostname;
                    } catch {
                      // Malformed URL from data -- fall back to showing it as-is
                    }
                    return (
                      <a
                        key={url}
                        href={url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-xs inline-flex items-center gap-1 border border-line rounded-full px-2.5 py-1 text-ink-soft hover:border-ink-soft"
                      >
                        {hostname}
                        <ArrowUpRight className="h-3 w-3" />
                      </a>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
