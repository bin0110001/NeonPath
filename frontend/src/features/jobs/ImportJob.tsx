import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { Job, RemoteType } from "./types";

const apiUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export function ImportJob() {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [description, setDescription] = useState("");
  const [url, setUrl] = useState("");
  const [remote, setRemote] = useState<RemoteType | "">("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const body: Record<string, unknown> = {
        title,
        company,
        description_text: description,
      };
      if (url) {
        body.canonical_url = url;
        body.source = { adapter: "manual", source_url: url, raw_payload: { pasted: true } };
      } else {
        body.source = { adapter: "manual", raw_payload: { pasted: true } };
      }
      if (remote) body.remote_type = remote;
      const response = await fetch(`${apiUrl}/api/v1/jobs/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        setError(response.status === 422 ? "Title, company and description are required." : `Import failed (${response.status})`);
        return;
      }
      const job = (await response.json()) as Job;
      navigate(`/jobs/${job.id}`);
    } catch {
      setError("Unable to reach the API");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} aria-label="Import job">
      <h2>Import a job</h2>
      <p>Paste a job description. It is evaluated against every profile when imported.</p>
      <div>
        <label htmlFor="job-title">Title</label>{" "}
        <input id="job-title" value={title} onChange={(e) => setTitle(e.target.value)} required />
      </div>
      <div>
        <label htmlFor="job-company">Company</label>{" "}
        <input id="job-company" value={company} onChange={(e) => setCompany(e.target.value)} required />
      </div>
      <div>
        <label htmlFor="job-url">URL (optional)</label>{" "}
        <input id="job-url" type="url" value={url} onChange={(e) => setUrl(e.target.value)} />
      </div>
      <div>
        <label htmlFor="job-remote">Work arrangement</label>{" "}
        <select id="job-remote" value={remote} onChange={(e) => setRemote(e.target.value as RemoteType | "")}>
          <option value="">Unknown</option>
          <option value="REMOTE">Remote</option>
          <option value="HYBRID">Hybrid</option>
          <option value="ONSITE">Onsite</option>
        </select>
      </div>
      <div>
        <label htmlFor="job-description">Description</label>
        <br />
        <textarea
          id="job-description"
          rows={8}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          required
        />
      </div>
      {error && <p role="alert">{error}</p>}
      <button type="submit" disabled={busy}>
        {busy ? "Importing..." : "Import job"}
      </button>
    </form>
  );
}
