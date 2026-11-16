import { useCallback, useEffect, useState } from "react";

const apiUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const base = `${apiUrl}/api/v1`;

interface Artifact {
  id: string;
  kind: string;
  format: string;
  version: number;
  redacted: boolean;
  content_sha256: string;
  created_at: string;
  size_bytes: number;
}

const LABELS: Record<string, string> = { markdown: "Markdown", html: "HTML", docx: "Word (DOCX)", pdf: "PDF" };

export function ArtifactsPanel({ profileId, jobId }: { profileId: string; jobId: string }) {
  const [formats, setFormats] = useState<string[]>(["markdown"]);
  const [items, setItems] = useState<Artifact[]>([]);
  const [format, setFormat] = useState("pdf");
  const [redacted, setRedacted] = useState(false);
  const [notes, setNotes] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    fetch(`${base}/artifact-formats`)
      .then((r) => (r.ok ? (r.json() as Promise<string[]>) : Promise.reject(new Error("formats"))))
      .then(setFormats)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetch(`${base}/profiles/${profileId}/artifacts?job_id=${encodeURIComponent(jobId)}`)
      .then((r) => (r.ok ? (r.json() as Promise<Artifact[]>) : Promise.reject(new Error(`Unable to load documents (${r.status})`))))
      .then((loaded) => {
        if (!cancelled) setItems(loaded);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load documents");
      });
    return () => {
      cancelled = true;
    };
  }, [profileId, jobId, tick]);

  const create = useCallback(async () => {
    setError(null);
    setMessage(null);
    const response = await fetch(`${base}/profiles/${profileId}/artifacts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ format, job_id: jobId, redacted, include_cover_letter_notes: notes }),
    });
    if (!response.ok) {
      setError(`Unable to create document (${response.status})`);
      return;
    }
    setTick((value) => value + 1);
  }, [format, jobId, notes, profileId, redacted]);

  const verify = useCallback(
    async (artifact: Artifact) => {
      const response = await fetch(`${base}/profiles/${profileId}/artifacts/${artifact.id}/rerender`, { method: "POST" });
      const data = (await response.json()) as { matches_stored: boolean };
      setMessage(
        data.matches_stored
          ? `Version ${artifact.version} was reproduced exactly from its saved inputs.`
          : `Version ${artifact.version} could not be reproduced identically.`,
      );
    },
    [profileId],
  );

  return (
    <div className="job-section">
      <h3>Documents</h3>
      <p>Generated from your profile records and approved package. Public copies leave out contact details.</p>
      <label htmlFor="artifact-format">Format</label>{" "}
      <select id="artifact-format" value={format} onChange={(e) => setFormat(e.target.value)}>
        {formats.map((f) => (
          <option key={f} value={f}>
            {LABELS[f] ?? f}
          </option>
        ))}
      </select>{" "}
      <label>
        <input type="checkbox" checked={redacted} onChange={(e) => setRedacted(e.target.checked)} /> Public copy (no contact details)
      </label>{" "}
      <label>
        <input type="checkbox" checked={notes} onChange={(e) => setNotes(e.target.checked)} /> Include cover-letter notes
      </label>{" "}
      <button onClick={() => void create()}>Create document</button>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      {items.length === 0 ? (
        <p>No documents yet.</p>
      ) : (
        <ul>
          {items.map((a) => (
            <li key={a.id}>
              {LABELS[a.format] ?? a.format} v{a.version}
              {a.redacted ? " (public)" : ""} · {Math.round(a.size_bytes / 1024) || 1} KB ·{" "}
              {new Date(a.created_at).toLocaleString()}{" "}
              <a href={`${base}/profiles/${profileId}/artifacts/${a.id}/download`} download>
                Download
              </a>{" "}
              <button onClick={() => void verify(a)}>Verify</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
