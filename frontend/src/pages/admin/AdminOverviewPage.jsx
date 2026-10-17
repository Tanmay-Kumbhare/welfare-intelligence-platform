import { useCallback, useEffect, useState } from "react";
import Card from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import { ErrorState, LoadingState } from "../../components/ui/StatusStates";
import { adminService } from "../../services/api";

const COUNT_LABELS = {
  users: "User accounts",
  citizens: "Citizen profiles",
  schemes: "Schemes",
  submissions: "Form submissions",
  assessments: "Eligibility assessments",
};

export default function AdminOverviewPage() {
  const [stats, setStats] = useState(null);
  const [schemes, setSchemes] = useState(null);
  const [error, setError] = useState("");
  const [schemesError, setSchemesError] = useState("");

  const load = useCallback(() => {
    setError("");
    setSchemesError("");
    adminService
      .stats()
      .then((response) => setStats(response.data))
      .catch((requestError) =>
        setError(requestError?.response?.data?.detail || "Could not load platform statistics.")
      );
    // The search/filter-free admin scheme list is the supported way to split
    // ACTIVE vs INACTIVE — /admin/stats only returns the total.
    adminService
      .listSchemes()
      .then((response) => setSchemes(response.data))
      .catch(() => setSchemesError("Scheme breakdown could not be loaded."));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) {
    return (
      <ErrorState
        title="Unable to load overview"
        message={error}
        onRetry={load}
      />
    );
  }
  if (!stats) {
    return <LoadingState label="Loading platform statistics..." />;
  }

  // Client-side split from the returned records — no invented data; when the
  // list itself failed we simply omit the breakdown instead of guessing.
  const activeSchemes =
    schemes?.filter((scheme) => scheme.status === "ACTIVE").length ?? null;
  const inactiveSchemes =
    schemes?.filter((scheme) => scheme.status !== "ACTIVE").length ?? null;
  const schemesWithoutRules =
    schemes?.filter(
      (scheme) => scheme.status === "ACTIVE" && (scheme.rule_count ?? 0) === 0
    ) ?? null;

  return (
    <div>
      <div className="mb-7">
        <h1 className="text-[30px] mb-2">Overview</h1>
        <p className="max-w-[60ch]">
          Platform-wide snapshot. Counts are live from the database — nothing
          cached or estimated.
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-4">
        {Object.entries(COUNT_LABELS).map(([key, label]) => (
          <Card key={key}>
            <div className="text-center py-2">
              <p className="text-[32px] font-display font-semibold text-ink leading-none mb-1">
                {stats.counts?.[key] ?? 0}
              </p>
              <p className="text-xs text-ink-soft">{label}</p>
            </div>
          </Card>
        ))}
      </div>

      <section aria-label="Scheme breakdown" className="mb-8">
        <h2 className="text-xl mb-3">Schemes by state</h2>
        {schemesError && !schemes ? (
          <Card>
            <p className="text-sm text-excl-ink py-2">{schemesError}</p>
          </Card>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <Card>
              <div className="text-center py-2">
                <p className="text-[26px] font-display font-semibold text-ink leading-none mb-1">
                  {schemes ? (activeSchemes ?? 0) : "—"}
                </p>
                <p className="text-xs text-ink-soft">Active schemes</p>
              </div>
            </Card>
            <Card>
              <div className="text-center py-2">
                <p className="text-[26px] font-display font-semibold text-ink leading-none mb-1">
                  {schemes ? (inactiveSchemes ?? 0) : "—"}
                </p>
                <p className="text-xs text-ink-soft">Inactive / archived</p>
              </div>
            </Card>
            <Card>
              <div className="text-center py-2">
                <p className="text-[26px] font-display font-semibold text-ink leading-none mb-1">
                  {schemes ? schemesWithoutRules.length : "—"}
                </p>
                <p className="text-xs text-ink-soft">
                  Active schemes without rules{" "}
                  <span className="text-accent-ink">(need attention)</span>
                </p>
              </div>
            </Card>
          </div>
        )}
        <p className="mt-3">
          <Button to="/admin/schemes" variant="ghost" size="sm">
            Manage schemes →
          </Button>
        </p>
      </section>

      <section>
        <h2 className="text-xl mb-3">Recent registrations</h2>
        <Card>
          {stats.recent_registrations?.length > 0 ? (
            <ul className="divide-y divide-line">
              {stats.recent_registrations.map((entry, index) => (
                <li key={index} className="flex justify-between gap-4 py-2.5 text-sm">
                  <span className="text-ink truncate">{entry.email}</span>
                  <span className="text-xs text-ink-soft shrink-0">
                    {new Date(entry.created_at).toLocaleString()}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-ink-soft py-2">No registrations yet.</p>
          )}
        </Card>
      </section>
    </div>
  );
}
