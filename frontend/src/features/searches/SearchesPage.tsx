import { FormEvent, useCallback, useEffect, useState } from "react";

const apiUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const base = `${apiUrl}/api/v1`;

interface Profile {
  id: string;
  display_name: string;
}
interface Source {
  id: string;
  name: string;
  adapter: string;
  health: string;
}
interface Search {
  id: string;
  name: string;
  source_id: string;
  query: string | null;
  schedule_minutes: number | null;
  enabled: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
  last_schedule_status: string | null;
}
interface Run {
  id: string;
  trigger: string;
  status: string;
  started_at: string;
  discovered: number;
  created: number;
  skipped: number;
  failed: number;
  error_code: string | null;
  error_message: string | null;
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return (await response.json()) as T;
}

export function SearchesPage() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [profileId, setProfileId] = useState("");
  const [sources, setSources] = useState<Source[]>([]);
  const [searches, setSearches] = useState<Search[]>([]);
  const [runs, setRuns] = useState<Record<string, Run[]>>({});
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [form, setForm] = useState({ name: "", sourceId: "", query: "", keywords: "", schedule: "" });

  useEffect(() => {
    Promise.all([getJson<Profile[]>(`${base}/profiles`), getJson<Source[]>(`${base}/sources`)])
      .then(([loadedProfiles, loadedSources]) => {
        setProfiles(loadedProfiles);
        setSources(loadedSources);
        setProfileId((current) => current || loadedProfiles[0]?.id || "");
        setForm((current) => ({ ...current, sourceId: current.sourceId || loadedSources[0]?.id || "" }));
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to load"));
  }, []);

  useEffect(() => {
    if (!profileId) return;
    let cancelled = false;
    getJson<Search[]>(`${base}/profiles/${profileId}/searches`)
      .then(async (loaded) => {
        const history = await Promise.all(
          loaded.map(async (s) => [s.id, await getJson<Run[]>(`${base}/profiles/${profileId}/searches/${s.id}/runs?limit=5`)] as const),
        );
        if (cancelled) return;
        setSearches(loaded);
        setRuns(Object.fromEntries(history));
        setError(null);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load searches");
      });
    return () => {
      cancelled = true;
    };
  }, [profileId, tick]);

  const create = useCallback(
    async (event: FormEvent) => {
      event.preventDefault();
      const keywords = form.keywords.split(",").map((k) => k.trim()).filter(Boolean);
      const response = await fetch(`${base}/profiles/${profileId}/searches`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: form.name,
          source_id: form.sourceId,
          query: form.query || null,
          filters: { keywords_any: keywords },
          schedule_minutes: form.schedule ? Number(form.schedule) : null,
        }),
      });
      if (!response.ok) {
        setError(`Unable to create search (${response.status})`);
        return;
      }
      setForm((current) => ({ ...current, name: "", query: "", keywords: "", schedule: "" }));
      setTick((value) => value + 1);
    },
    [form, profileId],
  );

  const act = useCallback(
    async (searchId: string, action: "run" | "delete") => {
      const url = `${base}/profiles/${profileId}/searches/${searchId}`;
      const response = await fetch(action === "run" ? `${url}/run` : url, { method: action === "run" ? "POST" : "DELETE" });
      if (!response.ok) setError(`Action failed (${response.status})`);
      setTick((value) => value + 1);
    },
    [profileId],
  );

  return (
    <section aria-label="Searches">
      <h2>Saved searches</h2>
      {error && <p role="alert">{error}</p>}
      <label htmlFor="search-profile">Profile</label>{" "}
      <select id="search-profile" value={profileId} onChange={(e) => setProfileId(e.target.value)}>
        {profiles.map((p) => (
          <option key={p.id} value={p.id}>
            {p.display_name}
          </option>
        ))}
      </select>

      <form onSubmit={(event) => void create(event)} aria-label="New search">
        <h3>New search</h3>
        <label htmlFor="s-name">Name</label>{" "}
        <input id="s-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />{" "}
        <label htmlFor="s-source">Source</label>{" "}
        <select id="s-source" value={form.sourceId} onChange={(e) => setForm({ ...form, sourceId: e.target.value })} required>
          {sources.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name} ({s.adapter}, {s.health})
            </option>
          ))}
        </select>{" "}
        <label htmlFor="s-query">Query</label>{" "}
        <input id="s-query" value={form.query} onChange={(e) => setForm({ ...form, query: e.target.value })} />{" "}
        <label htmlFor="s-keywords">Keywords (any, comma separated)</label>{" "}
        <input id="s-keywords" value={form.keywords} onChange={(e) => setForm({ ...form, keywords: e.target.value })} />{" "}
        <label htmlFor="s-schedule">Run every (minutes)</label>{" "}
        <input id="s-schedule" type="number" min={5} value={form.schedule} onChange={(e) => setForm({ ...form, schedule: e.target.value })} />{" "}
        <button type="submit">Create search</button>
      </form>

      {searches.length === 0 ? (
        <p>No searches yet.</p>
      ) : (
        searches.map((search) => (
          <article key={search.id}>
            <h3>{search.name}</h3>
            <p>
              {search.query ? `Query "${search.query}" · ` : ""}
              {search.schedule_minutes ? `every ${search.schedule_minutes} min` : "manual only"}
              {search.next_run_at ? ` · next ${new Date(search.next_run_at).toLocaleString()}` : ""}
            </p>
            <button onClick={() => void act(search.id, "run")}>Run now</button>{" "}
            <button onClick={() => void act(search.id, "delete")}>Delete</button>
            <h4>Run history</h4>
            {(runs[search.id] ?? []).length === 0 ? (
              <p>No runs yet.</p>
            ) : (
              <ul>
                {(runs[search.id] ?? []).map((run) => (
                  <li key={run.id}>
                    {new Date(run.started_at).toLocaleString()} · {run.trigger} · {run.status}: {run.discovered} found,{" "}
                    {run.created} new, {run.skipped} filtered out, {run.failed} failed
                    {run.error_code && (
                      <strong>
                        {" "}
                        — {run.error_code}: {run.error_message}
                      </strong>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </article>
        ))
      )}
    </section>
  );
}
