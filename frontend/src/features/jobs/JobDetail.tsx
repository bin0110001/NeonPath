import { useCallback, useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import type {
  Job,
  JobEvaluation,
  JobRequirement,
  JobSourceRecord,
  ProfileSummary,
  StatusHistoryEntry,
  WorkflowState,
} from "./types";

const apiUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const base = `${apiUrl}/api/v1`;

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return (await response.json()) as T;
}

type Action = "shortlist" | "save" | "reject" | "archive";

export function JobDetail() {
  const { jobId } = useParams();
  const [searchParams] = useSearchParams();
  const [job, setJob] = useState<Job | null>(null);
  const [sources, setSources] = useState<JobSourceRecord[]>([]);
  const [requirements, setRequirements] = useState<JobRequirement[]>([]);
  const [profiles, setProfiles] = useState<ProfileSummary[]>([]);
  const [profileId, setProfileId] = useState(searchParams.get("profile") ?? "");
  const [workflow, setWorkflow] = useState<WorkflowState | null>(null);
  const [history, setHistory] = useState<StatusHistoryEntry[]>([]);
  const [evaluation, setEvaluation] = useState<JobEvaluation | null>(null);
  const [aiAvailable, setAiAvailable] = useState(false);
  const [comparison, setComparison] = useState<JobEvaluation[]>([]);
  const [evaluationHistory, setEvaluationHistory] = useState<JobEvaluation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    Promise.all([
      getJson<Job>(`${base}/jobs/${jobId}`),
      getJson<JobSourceRecord[]>(`${base}/jobs/${jobId}/sources`),
      getJson<JobRequirement[]>(`${base}/jobs/${jobId}/requirements`),
      getJson<ProfileSummary[]>(`${base}/profiles`),
    ])
      .then(([loadedJob, loadedSources, loadedRequirements, loadedProfiles]) => {
        if (cancelled) return;
        setJob(loadedJob);
        setSources(loadedSources);
        setRequirements(loadedRequirements);
        setProfiles(loadedProfiles);
        setProfileId((current) => current || loadedProfiles[0]?.id || "");
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load job");
      });
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  useEffect(() => {
    getJson<{ available: boolean }>(`${base}/ai/status`)
      .then((status) => setAiAvailable(status.available))
      .catch(() => setAiAvailable(false));
  }, []);

  const loadProfileState = useCallback(async () => {
    if (!jobId || !profileId) return;
    const query = `profile_id=${encodeURIComponent(profileId)}`;
    const [state, entries, latest, compared, evaluations] = await Promise.all([
      getJson<WorkflowState>(`${base}/jobs/${jobId}/workflow?${query}`),
      getJson<StatusHistoryEntry[]>(`${base}/jobs/${jobId}/status-history?${query}`),
      getJson<JobEvaluation | null>(`${base}/jobs/${jobId}/evaluations/latest?${query}`),
      getJson<JobEvaluation[]>(`${base}/jobs/${jobId}/comparison`),
      getJson<JobEvaluation[]>(`${base}/jobs/${jobId}/evaluations?${query}`),
    ]);
    setWorkflow(state);
    setHistory(entries);
    setEvaluation(latest);
    setComparison(compared);
    setEvaluationHistory(evaluations);
  }, [jobId, profileId]);

  useEffect(() => {
    // Fetch on mount/profile change; state is set only after the async call resolves.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadProfileState().catch(() => setActionError("Unable to load profile status"));
  }, [loadProfileState]);

  async function post(path: string, body: Record<string, unknown>) {
    setActionError(null);
    const response = await fetch(`${base}/jobs/${jobId}/${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (response.status === 409) {
      const detail = (await response.json()) as { detail?: string };
      setActionError(detail.detail ?? "That change is not allowed from the current status");
      return;
    }
    if (!response.ok) {
      setActionError(`Request failed (${response.status})`);
      return;
    }
    await loadProfileState();
  }

  const act = (action: Action) => post(action, { profile_id: profileId });
  const evaluate = () => post("evaluate", { profile_id: profileId });
  const evaluateWithAi = () => post("evaluate", { profile_id: profileId, semantic: true });
  const evaluateAll = () => post("evaluate-all", {});
  const profileName = (id: string) => profiles.find((p) => p.id === id)?.display_name ?? id;

  if (error) return <div role="alert">Error: {error}</div>;
  if (!job) return <div>Loading job details...</div>;

  return (
    <div>
      <h2>Job Details</h2>
      <div className="job-detail">
        <h1>{job.title}</h1>
        <div className="job-meta">
          <span><strong>Company:</strong> {job.company}</span>
          <span><strong>Location:</strong> {job.location_text || "Not specified"}</span>
          {job.remote_type && <span><strong>Remote:</strong> {job.remote_type}</span>}
        </div>
        {job.salary_min != null && job.salary_max != null && job.salary_currency && (
          <div className="salary">
            <strong>Salary:</strong> {job.salary_currency} {job.salary_min} - {job.salary_max}{" "}
            {job.salary_period}
          </div>
        )}
        <div className="job-description">
          <h3>Description</h3>
          <p>{job.description_text}</p>
        </div>

        {requirements.length > 0 && (
          <div className="job-section">
            <h3>Requirements</h3>
            <ul>
              {requirements.map((req) => (
                <li key={req.id}>
                  <strong>{req.type}:</strong> {req.normalized_text}
                  {req.required_level && ` (${req.required_level})`}
                </li>
              ))}
            </ul>
          </div>
        )}

        {sources.length > 0 && (
          <div className="job-section">
            <h3>Sources</h3>
            {sources.map((source) => (
              <div key={source.id} className="source-item">
                {source.adapter}
                {source.source_url && (
                  <>
                    {" "}
                    <a href={source.source_url} target="_blank" rel="noopener noreferrer">
                      View original
                    </a>
                  </>
                )}
              </div>
            ))}
          </div>
        )}

        <div className="job-section">
          <label htmlFor="active-profile">Active profile</label>{" "}
          <select
            id="active-profile"
            value={profileId}
            onChange={(event) => setProfileId(event.target.value)}
          >
            {profiles.map((profile) => (
              <option key={profile.id} value={profile.id}>
                {profile.display_name}
              </option>
            ))}
          </select>
        </div>

        {profileId && (
          <>
            <div className="job-section">
              <h3>Status</h3>
              <p data-testid="workflow-status">{workflow?.status ?? "…"}</p>
              <div className="job-actions">
                <button onClick={() => void act("shortlist")}>Shortlist</button>
                <button onClick={() => void act("save")}>Save</button>
                <button onClick={() => void act("reject")}>Reject</button>
                <button onClick={() => void act("archive")}>Archive</button>
              </div>
              {actionError && <p role="alert">{actionError}</p>}
              <h4>History</h4>
              {history.length === 0 ? (
                <p>No status changes yet.</p>
              ) : (
                <ol>
                  {history.map((entry) => (
                    <li key={entry.id}>
                      {entry.old_status} → {entry.new_status} by {entry.actor ?? "unknown"} on{" "}
                      {new Date(entry.timestamp).toLocaleString()}
                      {entry.reason && ` — ${entry.reason}`}
                    </li>
                  ))}
                </ol>
              )}
            </div>

            <div className="job-section">
              <h3>Evaluation</h3>
              <button onClick={() => void evaluate()}>
                {evaluation ? "Re-evaluate" : "Evaluate"}
              </button>
              {aiAvailable && (
                <button onClick={() => void evaluateWithAi()}>Evaluate with AI</button>
              )}
              {evaluation && <EvaluationView evaluation={evaluation} />}
              {evaluationHistory.length > 1 && (
                <details>
                  <summary>Evaluation history ({evaluationHistory.length})</summary>
                  <ol>
                    {evaluationHistory.map((item) => (
                      <li key={item.id}>
                        {new Date(item.created_at).toLocaleString()}: {Math.round(item.overall_score * 100)}% (
                        {item.evaluator_version})
                      </li>
                    ))}
                  </ol>
                </details>
              )}
            </div>

            <div className="job-section">
              <h3>Compare profiles</h3>
              <button onClick={() => void evaluateAll()}>Evaluate for all profiles</button>
              {comparison.length > 0 && (
                <table>
                  <thead>
                    <tr>
                      <th>Profile</th>
                      <th>Overall</th>
                      <th>Confidence</th>
                      <th>Blockers</th>
                      <th>Why</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparison.map((item) => (
                      <tr key={item.profile_id}>
                        <td>{profileName(item.profile_id)}</td>
                        <td>{Math.round(item.overall_score * 100)}%</td>
                        <td>{Math.round((item.confidence ?? 0) * 100)}%</td>
                        <td>{item.blockers.length > 0 ? item.blockers.join("; ") : "none"}</td>
                        <td>{[...item.strengths.slice(0, 2), ...item.gaps.slice(0, 2)].join("; ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function List({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <strong>{title}:</strong>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function EvaluationView({ evaluation }: { evaluation: JobEvaluation }) {
  return (
    <div className="evaluation-content">
      <p>
        <strong>Overall score:</strong> {Math.round(evaluation.overall_score * 100)}%{" "}
        <span>
          (confidence {Math.round((evaluation.confidence ?? 0) * 100)}%, {evaluation.evaluator_version})
        </span>
      </p>
      {evaluation.explanation && <p>{evaluation.explanation}</p>}
      <div>
        <strong>Dimension scores:</strong>
        <ul>
          {Object.entries(evaluation.dimension_scores_json).map(([dimension, score]) => (
            <li key={dimension}>
              {dimension}: {Math.round(score * 100)}%
            </li>
          ))}
        </ul>
      </div>
      {evaluation.claims_json.length > 0 && (
        <div>
          <strong>AI claims (prompt {evaluation.prompt_version}):</strong>
          <ul>
            {evaluation.claims_json.map((claim, index) => (
              <li key={index}>
                [{claim.kind}] {claim.text}{" "}
                {claim.basis === "evidence" ? (
                  <span title={claim.evidence_ids.join(", ")}>
                    — evidence: {claim.evidence_ids.length} profile record(s)
                  </span>
                ) : (
                  <em>({claim.basis}{claim.note ? `: ${claim.note}` : ""})</em>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      <List title="Strengths" items={evaluation.strengths} />
      <List title="Transferable matches" items={evaluation.transferable_matches} />
      <List title="Gaps" items={evaluation.gaps} />
      <List title="Blockers" items={evaluation.blockers} />
      <List title="Unknown (not scored)" items={evaluation.unknowns} />
    </div>
  );
}
