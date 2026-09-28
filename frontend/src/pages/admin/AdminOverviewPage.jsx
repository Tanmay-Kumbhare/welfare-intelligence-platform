import { useEffect, useState } from "react";
import Card from "../../components/ui/Card";
import { ErrorState, LoadingState } from "../../components/ui/StatusStates";
import { api } from "../../services/api";

const COUNT_LABELS = {
  users: "User accounts",
  citizens: "Citizen profiles",
  schemes: "Schemes",
  submissions: "Form submissions",
  assessments: "Eligibility assessments",
};

export default function AdminOverviewPage() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get("/admin/stats")
      .then((response) => setStats(response.data))
      .catch((requestError) =>
        setError(
          requestError?.response?.data?.detail ||
            "Could not load platform statistics."
        )
      );
  }, []);

  if (error) {
    return <ErrorState title="Unable to load overview" message={error} />;
  }
  if (!stats) {
    return <LoadingState label="Loading platform statistics..." />;
  }

  return (
    <div>
      <div className="mb-7">
        <h1 className="text-[30px] mb-2">Overview</h1>
        <p className="max-w-[60ch]">
          Platform-wide snapshot. Counts are live from the database — nothing
          cached or estimated.
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
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
