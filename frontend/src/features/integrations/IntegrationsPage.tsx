import { resolveActive, useActiveProfileId } from "../profiles/activeProfile";
import { useCallback, useEffect, useState } from "react";

const apiUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const base = `${apiUrl}/api/v1`;

interface Profile {
  id: string;
  display_name: string;
}
interface Account {
  kind: "email" | "calendar";
  connected: boolean;
  provider: string | null;
  scopes: string[];
  allow_writes: boolean;
  last_synced_at: string | null;
}
interface Link {
  id: string;
  application_id: string | null;
  classification: string;
  score: number;
  reasons: string[];
  received_at: string;
  status: string;
}
interface WriteRequest {
  id: string;
  action: string;
  status: string;
  payload_json: { title?: string; starts_at?: string };
  error: string | null;
}

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const detail = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(detail.detail ?? `Request failed (${response.status})`);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

export function IntegrationsPage() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [profileId, setProfileId] = useActiveProfileId();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [links, setLinks] = useState<Link[]>([]);
  const [requests, setRequests] = useState<WriteRequest[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [writes, setWrites] = useState(false);

  useEffect(() => {
    call<Profile[]>(`${base}/profiles`)
      .then((loaded) => {
        setProfiles(loaded);
        setProfileId((current) => resolveActive(current, loaded.map((p) => p.id)));
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to load profiles"));
  }, [setProfileId]);

  useEffect(() => {
    if (!profileId) return;
    let cancelled = false;
    Promise.all([
      call<Account[]>(`${base}/profiles/${profileId}/integrations`),
      call<Link[]>(`${base}/profiles/${profileId}/email/links`),
      call<WriteRequest[]>(`${base}/profiles/${profileId}/calendar/requests`),
    ])
      .then(([a, l, r]) => {
        if (cancelled) return;
        setAccounts(a);
        setLinks(l);
        setRequests(r);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load integrations");
      });
    return () => {
      cancelled = true;
    };
  }, [profileId, tick]);

  const run = useCallback(async (work: () => Promise<string | void>) => {
    setError(null);
    setMessage(null);
    try {
      const result = await work();
      if (result) setMessage(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Something went wrong");
    }
    setTick((value) => value + 1);
  }, []);

  const post = (path: string) => call<Record<string, unknown>>(`${base}/profiles/${profileId}/${path}`, { method: "POST" });

  return (
    <section aria-label="Integrations">
      <h2>Integrations</h2>
      <p>
        Mailbox access is read-only and CareerFlow never sends email: replies are drafts you copy yourself. Calendar
        events are only written after you approve each one. Not available in demo mode.
      </p>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      <label htmlFor="int-profile">Profile</label>{" "}
      <select id="int-profile" value={profileId} onChange={(e) => setProfileId(e.target.value)}>
        {profiles.map((p) => (
          <option key={p.id} value={p.id}>
            {p.display_name}
          </option>
        ))}
      </select>

      <ul>
        {accounts.map((a) => (
          <li key={a.kind}>
            <strong>{a.kind === "email" ? "Email (read-only)" : "Calendar"}</strong>:{" "}
            {a.connected ? `connected via ${a.provider}${a.allow_writes ? " (can create events after approval)" : ""}` : "not connected"}{" "}
            {a.connected ? (
              <>
                <button onClick={() => void run(() => call(`${base}/profiles/${profileId}/integrations/${a.kind}`, { method: "DELETE" }))}>Disconnect</button>{" "}
                {a.kind === "email" ? (
                  <button onClick={() => void run(async () => { const r = await post("email/sync"); return `Scanned ${String(r.scanned)} messages, linked ${String(r.linked)}.`; })}>
                    Sync email
                  </button>
                ) : (
                  <button onClick={() => void run(async () => { const r = await post("calendar/import"); return `Imported ${String(r.created)} new, ${String(r.updated)} updated events.`; })}>
                    Import events
                  </button>
                )}
              </>
            ) : (
              <>
                {a.kind === "calendar" && (
                  <label>
                    <input type="checkbox" checked={writes} onChange={(e) => setWrites(e.target.checked)} /> allow creating events (still needs approval)
                  </label>
                )}{" "}
                <button
                  onClick={() =>
                    void run(async () => {
                      const r = await call<{ authorization_url: string }>(`${base}/profiles/${profileId}/integrations/${a.kind}/connect`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ allow_writes: a.kind === "calendar" && writes }),
                      });
                      window.open(r.authorization_url, "_blank", "noopener");
                      return "Finish connecting in the window that opened.";
                    })
                  }
                >
                  Connect {a.kind}
                </button>
              </>
            )}
          </li>
        ))}
      </ul>

      <h3>Recognised messages</h3>
      {links.length === 0 ? (
        <p>None yet.</p>
      ) : (
        <ul>
          {links.map((l) => (
            <li key={l.id}>
              <strong>{l.classification.replace("_", " ")}</strong> · {new Date(l.received_at).toLocaleDateString()} ·{" "}
              {l.application_id ? `linked (${Math.round(l.score * 100)}%)` : "not linked"} · {l.status}
              {l.reasons.length > 0 && <small> — {l.reasons.join("; ")}</small>}{" "}
              <button onClick={() => void run(async () => { const d = await post(`email/links/${l.id}/draft`); setDrafts((c) => ({ ...c, [l.id]: String(d.body) })); })}>Draft reply</button>{" "}
              <button onClick={() => void run(() => post(`email/links/${l.id}/dismiss`).then(() => undefined))}>Dismiss</button>
              {drafts[l.id] && <pre aria-label="Reply draft">{drafts[l.id]}</pre>}
            </li>
          ))}
        </ul>
      )}

      <h3>Calendar changes awaiting your approval</h3>
      {requests.filter((r) => r.status === "PENDING").length === 0 ? (
        <p>Nothing pending.</p>
      ) : (
        <ul>
          {requests.filter((r) => r.status === "PENDING").map((r) => (
            <li key={r.id}>
              {r.action}: {r.payload_json.title} at {r.payload_json.starts_at && new Date(r.payload_json.starts_at).toLocaleString()}{" "}
              <button onClick={() => void run(async () => { await post(`calendar/requests/${r.id}/approve`); return "Approved and written to your calendar."; })}>Approve</button>{" "}
              <button onClick={() => void run(() => post(`calendar/requests/${r.id}/reject`).then(() => undefined))}>Reject</button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
