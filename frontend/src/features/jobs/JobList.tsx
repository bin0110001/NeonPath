import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { type InboxFilters, PAGE_SIZE, buildJobsQuery } from "./inbox";
import type { JobListItem } from "./types";

const apiUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
export function JobList({ profileId, filters }: { profileId: string; filters: InboxFilters }) {
  // Filters/profile changes remount this component (see key in JobsHome), which resets paging.
  const [page, setPage] = useState(0);
  const [result, setResult] = useState<{ key: string; jobs: JobListItem[]; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const query = buildJobsQuery(profileId, filters, page);

  useEffect(() => {
    let cancelled = false;
    fetch(`${apiUrl}/api/v1/jobs?${query}`)
      .then(async (response) => {
        if (!response.ok) throw new Error(`Unable to load jobs (${response.status})`);
        return {
          data: (await response.json()) as JobListItem[],
          count: Number(response.headers.get("X-Total-Count") ?? 0),
        };
      })
      .then(({ data, count }) => {
        if (cancelled) return;
        setResult({ key: query, jobs: data, total: count });
        setError(null);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load jobs");
      });
    return () => {
      cancelled = true;
    };
  }, [query]);

  const loading = result?.key !== query;
  const jobs = result?.jobs ?? [];
  const total = result?.total ?? 0;
  if (error) return <div role="alert">Error: {error}</div>;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div>
      <h2>Job Listings</h2>
      {loading && <p>Loading jobs...</p>}
      {!loading && jobs.length === 0 ? (
        <p>No jobs found.</p>
      ) : (
        <ul>
          {jobs.map((job) => (
            <li key={job.id}>
              <h3>
                <Link to={`/jobs/${job.id}?profile=${encodeURIComponent(profileId)}`}>{job.title}</Link>
              </h3>
              <p><strong>Company:</strong> {job.company}</p>
              <p><strong>Location:</strong> {job.location_text || "Not specified"}</p>
              {job.remote_type && <p><strong>Remote:</strong> {job.remote_type}</p>}
              <p>
                <strong>Status:</strong> {job.workflow_status}
                {job.score != null && (
                  <>
                    {" "}· <strong>Fit:</strong> {Math.round(job.score * 100)}%
                  </>
                )}
                {job.has_blockers && (
                  <>
                    {" "}· <strong>Blocked</strong>
                  </>
                )}
              </p>
              <p><strong>Discovered:</strong> {new Date(job.discovered_at).toLocaleDateString()}</p>
            </li>
          ))}
        </ul>
      )}
      <nav aria-label="Pagination">
        <button disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Previous</button>{" "}
        <span>
          Page {page + 1} of {pages} ({total} jobs)
        </span>{" "}
        <button disabled={page + 1 >= pages} onClick={() => setPage((p) => p + 1)}>Next</button>
      </nav>
    </div>
  );
}
