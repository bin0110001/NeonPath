import { useEffect, useState } from "react";
import type { Dashboard as DashboardData } from "./types";

const apiUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export function Dashboard({
  profileId,
  onSelectStatus,
}: {
  profileId: string;
  onSelectStatus?: (status: string) => void;
}) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${apiUrl}/api/v1/jobs/dashboard?profile_id=${encodeURIComponent(profileId)}`)
      .then((response) => {
        if (!response.ok) throw new Error(`Unable to load dashboard (${response.status})`);
        return response.json() as Promise<DashboardData>;
      })
      .then((loaded) => {
        if (!cancelled) setData(loaded);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load dashboard");
      });
    return () => {
      cancelled = true;
    };
  }, [profileId]);

  if (error) return <div role="alert">{error}</div>;
  if (!data) return <p>Loading dashboard...</p>;

  const tiles: Array<[string, number, string?]> = [
    ["New jobs", data.new_jobs],
    ["Needs review", data.needs_review, "READY_FOR_REVIEW"],
    ["High fit", data.high_fit],
    ["Shortlisted", data.shortlisted, "SHORTLISTED"],
    ["Blocked", data.blocked],
    ["Not evaluated", data.unevaluated],
  ];
  return (
    <section aria-label="Dashboard">
      <h2>Dashboard</h2>
      <ul className="dashboard-tiles">
        {tiles.map(([label, value, status]) => (
          <li key={label}>
            <strong data-testid={`tile-${label}`}>{value}</strong>{" "}
            {status && onSelectStatus ? (
              <button onClick={() => onSelectStatus(status)}>{label}</button>
            ) : (
              <span>{label}</span>
            )}
          </li>
        ))}
      </ul>
      <p>
        {data.total} jobs in total:{" "}
        {Object.entries(data.by_status)
          .map(([status, count]) => `${status} ${count}`)
          .join(", ") || "none"}
      </p>
    </section>
  );
}
