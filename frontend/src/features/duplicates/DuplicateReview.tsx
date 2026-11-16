import { useCallback, useEffect, useState } from "react";

const apiUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const base = `${apiUrl}/api/v1`;

export interface JobBrief {
  id: string;
  title: string;
  company: string;
  location_text: string | null;
  remote_type: string | null;
  salary_min: number | null;
  salary_max: number | null;
  source_count: number;
}

export interface DuplicatePair {
  id: string;
  classification: string;
  score: number;
  reasons: string[];
  status: string;
  job: JobBrief;
  canonical: JobBrief;
}

export interface MergeItem {
  id: string;
  canonical_job_id: string;
  merged_job_id: string;
  merged_at: string;
}

function JobCard({ label, job }: { label: string; job: JobBrief }) {
  return (
    <div>
      <h4>{label}</h4>
      <p>
        <strong>{job.title}</strong> — {job.company}
      </p>
      <p>
        {job.location_text ?? "No location"} · {job.remote_type ?? "arrangement unknown"}
      </p>
      {job.salary_min != null && job.salary_max != null && (
        <p>
          {job.salary_min}–{job.salary_max}
        </p>
      )}
      <p>{job.source_count} source record(s)</p>
    </div>
  );
}

export function DuplicateReview() {
  const [pairs, setPairs] = useState<DuplicatePair[]>([]);
  const [merges, setMerges] = useState<MergeItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetch(`${base}/duplicates?status=PENDING`).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`duplicates ${r.status}`)))),
      fetch(`${base}/merges`).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`merges ${r.status}`)))),
    ])
      .then(([pending, active]) => {
        if (cancelled) return;
        setPairs(pending as DuplicatePair[]);
        setMerges(active as MergeItem[]);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load duplicates");
      });
    return () => {
      cancelled = true;
    };
  }, [tick]);

  const act = useCallback(async (path: string, body?: unknown) => {
    const response = await fetch(`${base}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!response.ok) setError(`Action failed (${response.status})`);
    setTick((value) => value + 1);
  }, []);

  return (
    <section aria-label="Duplicate review">
      <h2>Possible duplicates</h2>
      {error && <p role="alert">{error}</p>}
      {pairs.length === 0 ? (
        <p>No duplicates to review.</p>
      ) : (
        pairs.map((pair) => (
          <article key={pair.id} className="duplicate-pair">
            <p>
              <strong>{pair.classification}</strong> match, {Math.round(pair.score * 100)}% — {pair.reasons.join("; ")}
            </p>
            <div style={{ display: "flex", gap: "2rem" }}>
              <JobCard label="Older posting (kept)" job={pair.canonical} />
              <JobCard label="Newer posting" job={pair.job} />
            </div>
            <button onClick={() => void act(`/duplicates/${pair.id}/merge`, {})}>Merge</button>{" "}
            <button onClick={() => void act(`/duplicates/${pair.id}/merge`, { keep_job_id: pair.job.id })}>
              Merge, keep newer
            </button>{" "}
            <button onClick={() => void act(`/duplicates/${pair.id}/dismiss`)}>Not a duplicate</button>
          </article>
        ))
      )}

      <h2>Merged jobs</h2>
      {merges.length === 0 ? (
        <p>Nothing merged.</p>
      ) : (
        <ul>
          {merges.map((merge) => (
            <li key={merge.id}>
              Merged {merge.merged_job_id.slice(0, 8)} into {merge.canonical_job_id.slice(0, 8)} on{" "}
              {new Date(merge.merged_at).toLocaleString()}{" "}
              <button onClick={() => void act(`/merges/${merge.id}/unmerge`)}>Unmerge</button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
