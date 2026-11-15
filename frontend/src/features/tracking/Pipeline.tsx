import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

const apiUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const base = `${apiUrl}/api/v1`;

const COLUMNS = [
  "SHORTLISTED", "PREPARING", "READY_TO_APPLY", "APPLIED", "SCREENING", "INTERVIEWING", "FINAL", "OFFER", "REJECTED", "WITHDRAWN",
] as const;

interface Profile {
  id: string;
  display_name: string;
}
export interface Card {
  job_id: string;
  title: string;
  company: string;
  status: string;
  score: number | null;
  application_id: string | null;
  applied_at: string | null;
  next_follow_up_at: string | null;
  next_interview_at: string | null;
}
export interface Metrics {
  jobs_reviewed: number;
  shortlisted: number;
  applications_submitted: number;
  screens: number;
  interviews: number;
  final_interviews: number;
  offers: number;
  responded: number;
  response_rate: number | null;
  median_days_to_response: number | null;
}
interface FollowUp {
  id: string;
  application_id: string;
  due_at: string;
  type: string;
  status: string;
}
interface Interview {
  id: string;
  application_id: string;
  type: string;
  scheduled_at: string | null;
}
interface Overview {
  due_follow_ups: FollowUp[];
  upcoming_interviews: Interview[];
  metrics: Metrics;
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return (await response.json()) as T;
}

interface Prep {
  focus_areas: string[];
  relevant_achievements: Array<{ id: string; title: string; why: string }>;
  technical_topics: string[];
  system_design_themes: string[];
  ai_ml_topics: string[];
  leadership_stories: Array<{ id: string; title: string }>;
  weak_spots: string[];
  questions_to_ask: string[];
  warnings: string[];
  ai_stories: Array<{ text: string; basis: string; evidence_ids: string[] }>;
  ai_note: string | null;
}

function Section({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <strong>{title}</strong>
      <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>
    </div>
  );
}

function InterviewPrepView({ profileId, interviewId }: { profileId: string; interviewId: string }) {
  const [prep, setPrep] = useState<Prep | null>(null);
  const [error, setError] = useState<string | null>(null);
  async function load() {
    setError(null);
    const response = await fetch(`${base}/profiles/${profileId}/interviews/${interviewId}/prepare`, { method: "POST" });
    if (!response.ok) {
      setError(`Unable to prepare (${response.status})`);
      return;
    }
    setPrep((await response.json()) as Prep);
  }
  return (
    <div>
      <button onClick={() => void load()}>Prepare</button>
      {error && <p role="alert">{error}</p>}
      {prep && (
        <div aria-label="Interview preparation">
          {prep.ai_note && <p>{prep.ai_note}</p>}
          <Section title="Focus areas" items={prep.focus_areas} />
          <Section title="Your relevant achievements" items={prep.relevant_achievements.map((a) => `${a.title} (${a.why})`)} />
          <Section title="Technical topics" items={prep.technical_topics} />
          <Section title="System design themes" items={prep.system_design_themes} />
          <Section title="AI/ML topics" items={prep.ai_ml_topics} />
          <Section title="Leadership stories" items={prep.leadership_stories.map((a) => a.title)} />
          <Section title="Suggested stories (AI)" items={prep.ai_stories.map((s) => (s.basis === "evidence" ? s.text : `${s.text} [${s.basis}]`))} />
          <Section title="Weak spots" items={[...prep.weak_spots, ...prep.warnings]} />
          <Section title="Questions to ask" items={prep.questions_to_ask} />
        </div>
      )}
    </div>
  );
}

export function MetricsPanel({ metrics }: { metrics: Metrics }) {
  const pct = metrics.response_rate === null ? "n/a" : `${Math.round(metrics.response_rate * 100)}%`;
  return (
    <ul aria-label="Funnel metrics">
      <li>Jobs reviewed: <strong>{metrics.jobs_reviewed}</strong></li>
      <li>Shortlisted: <strong>{metrics.shortlisted}</strong></li>
      <li>Applications submitted: <strong>{metrics.applications_submitted}</strong></li>
      <li>Screens: <strong>{metrics.screens}</strong> · Interviews: <strong>{metrics.interviews}</strong> · Final: <strong>{metrics.final_interviews}</strong> · Offers: <strong>{metrics.offers}</strong></li>
      <li>Response rate: <strong data-testid="response-rate">{pct}</strong>
        {metrics.median_days_to_response !== null && ` (median ${metrics.median_days_to_response} days to respond)`}</li>
    </ul>
  );
}

export function Pipeline() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [profileId, setProfileId] = useState("");
  const [columns, setColumns] = useState<Record<string, Card[]>>({});
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [followUp, setFollowUp] = useState({ applicationId: "", due: "", type: "check_in" });
  const [interview, setInterview] = useState({ applicationId: "", at: "", type: "recruiter" });

  useEffect(() => {
    getJson<Profile[]>(`${base}/profiles`)
      .then((loaded) => {
        setProfiles(loaded);
        setProfileId((current) => current || loaded[0]?.id || "");
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to load profiles"));
  }, []);

  useEffect(() => {
    if (!profileId) return;
    let cancelled = false;
    Promise.all([
      getJson<{ columns: Record<string, Card[]> }>(`${base}/profiles/${profileId}/pipeline`),
      getJson<Overview>(`${base}/profiles/${profileId}/overview`),
    ])
      .then(([board, summary]) => {
        if (cancelled) return;
        setColumns(board.columns);
        setOverview(summary);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load the pipeline");
      });
    return () => {
      cancelled = true;
    };
  }, [profileId, tick]);

  const move = useCallback(
    async (jobId: string, to: string) => {
      setError(null);
      const response = await fetch(`${base}/jobs/${jobId}/transition`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile_id: profileId, to_status: to }),
      });
      if (response.status === 409) {
        const detail = (await response.json()) as { detail?: string };
        setError(detail.detail ?? "That move is not allowed from the current status");
      } else if (!response.ok) {
        setError(`Move failed (${response.status})`);
      }
      setTick((value) => value + 1);
    },
    [profileId],
  );

  const post = useCallback(
    async (path: string, body: unknown) => {
      const response = await fetch(`${base}/profiles/${profileId}/${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) setError(`Unable to save (${response.status})`);
      setTick((value) => value + 1);
    },
    [profileId],
  );

  const applications = Object.values(columns).flat().filter((c) => c.application_id);

  function addFollowUp(event: FormEvent) {
    event.preventDefault();
    void post("follow-ups", { application_id: followUp.applicationId, due_at: new Date(followUp.due).toISOString(), type: followUp.type });
  }
  function addInterview(event: FormEvent) {
    event.preventDefault();
    void post("interviews", {
      application_id: interview.applicationId,
      type: interview.type,
      scheduled_at: interview.at ? new Date(interview.at).toISOString() : null,
    });
  }

  return (
    <section aria-label="Pipeline">
      <h2>Pipeline</h2>
      {error && <p role="alert">{error}</p>}
      <label htmlFor="pipeline-profile">Profile</label>{" "}
      <select id="pipeline-profile" value={profileId} onChange={(e) => setProfileId(e.target.value)}>
        {profiles.map((p) => (
          <option key={p.id} value={p.id}>
            {p.display_name}
          </option>
        ))}
      </select>

      {overview && (
        <div>
          <h3>Funnel</h3>
          <MetricsPanel metrics={overview.metrics} />
          <h3>Follow-ups due ({overview.due_follow_ups.length})</h3>
          {overview.due_follow_ups.length === 0 ? <p>Nothing due.</p> : (
            <ul>
              {overview.due_follow_ups.map((f) => (
                <li key={f.id}>
                  {f.type} · due {new Date(f.due_at).toLocaleString()}{" "}
                  <button onClick={() => void post(`follow-ups/${f.id}/complete`, {})}>Done</button>
                </li>
              ))}
            </ul>
          )}
          <h3>Upcoming interviews ({overview.upcoming_interviews.length})</h3>
          {overview.upcoming_interviews.length === 0 ? <p>None scheduled.</p> : (
            <ul>
              {overview.upcoming_interviews.map((i) => (
                <li key={i.id}>
                  {i.type} · {i.scheduled_at ? new Date(i.scheduled_at).toLocaleString() : "unscheduled"}
                  <InterviewPrepView profileId={profileId} interviewId={i.id} />
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div style={{ display: "flex", gap: "1rem", overflowX: "auto" }}>
        {COLUMNS.map((column) => (
          <div key={column} aria-label={`${column} column`} style={{ minWidth: "12rem" }}>
            <h3>
              {column} ({(columns[column] ?? []).length})
            </h3>
            {(columns[column] ?? []).map((card) => (
              <article key={card.job_id} className="pipeline-card">
                <Link to={`/jobs/${card.job_id}?profile=${profileId}`}>{card.title}</Link>
                <p>{card.company}{card.score !== null && ` · ${Math.round(card.score * 100)}%`}</p>
                {card.next_follow_up_at && <p>Follow up {new Date(card.next_follow_up_at).toLocaleDateString()}</p>}
                {card.next_interview_at && <p>Interview {new Date(card.next_interview_at).toLocaleString()}</p>}
                <label>
                  Move to{" "}
                  <select
                    aria-label={`Move ${card.title}`}
                    value={card.status}
                    onChange={(e) => void move(card.job_id, e.target.value)}
                  >
                    {COLUMNS.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </label>
              </article>
            ))}
          </div>
        ))}
      </div>

      {applications.length > 0 && (
        <div>
          <form onSubmit={addFollowUp} aria-label="New follow-up">
            <h3>Add follow-up</h3>
            <select aria-label="Follow-up application" value={followUp.applicationId} onChange={(e) => setFollowUp({ ...followUp, applicationId: e.target.value })} required>
              <option value="">Application…</option>
              {applications.map((c) => <option key={c.application_id} value={c.application_id ?? ""}>{c.title}</option>)}
            </select>{" "}
            <input aria-label="Follow-up due" type="datetime-local" value={followUp.due} onChange={(e) => setFollowUp({ ...followUp, due: e.target.value })} required />{" "}
            <button type="submit">Add follow-up</button>
          </form>
          <form onSubmit={addInterview} aria-label="New interview">
            <h3>Add interview</h3>
            <select aria-label="Interview application" value={interview.applicationId} onChange={(e) => setInterview({ ...interview, applicationId: e.target.value })} required>
              <option value="">Application…</option>
              {applications.map((c) => <option key={c.application_id} value={c.application_id ?? ""}>{c.title}</option>)}
            </select>{" "}
            <select aria-label="Interview type" value={interview.type} onChange={(e) => setInterview({ ...interview, type: e.target.value })}>
              {["recruiter", "hiring_manager", "coding", "system_design", "machine_learning", "architecture", "behavioral", "panel", "executive", "other"].map((t) => <option key={t}>{t}</option>)}
            </select>{" "}
            <input aria-label="Interview time" type="datetime-local" value={interview.at} onChange={(e) => setInterview({ ...interview, at: e.target.value })} />{" "}
            <button type="submit">Add interview</button>
          </form>
        </div>
      )}
    </section>
  );
}
