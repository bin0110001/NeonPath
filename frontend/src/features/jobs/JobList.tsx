import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { Job } from "./types";

const apiUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export function JobList() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${apiUrl}/api/v1/jobs`)
      .then((response) => {
        if (!response.ok) throw new Error(`Unable to load jobs (${response.status})`);
        return response.json() as Promise<Job[]>;
      })
      .then((data) => {
        if (!cancelled) setJobs(data);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load jobs");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) return <div>Loading jobs...</div>;
  if (error) return <div role="alert">Error: {error}</div>;

  return (
    <div>
      <h2>Job Listings</h2>
      {jobs.length === 0 ? (
        <p>No jobs found.</p>
      ) : (
        <ul>
          {jobs.map((job) => (
            <li key={job.id}>
              <h3>
                <Link to={`/jobs/${job.id}`}>{job.title}</Link>
              </h3>
              <p><strong>Company:</strong> {job.company}</p>
              <p><strong>Location:</strong> {job.location_text || "Not specified"}</p>
              {job.remote_type && <p><strong>Remote:</strong> {job.remote_type}</p>}
              {job.salary_min != null && job.salary_max != null && job.salary_currency && (
                <p>
                  <strong>Salary:</strong> {job.salary_currency} {job.salary_min} - {job.salary_max}{" "}
                  {job.salary_period}
                </p>
              )}
              <p><strong>Discovered:</strong> {new Date(job.discovered_at).toLocaleDateString()}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
