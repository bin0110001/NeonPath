import { useState } from "react";

const apiUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const base = `${apiUrl}/api/v1`;

export interface Claim {
  text: string;
  basis: "evidence" | "inference" | "unverified";
  evidence_ids: string[];
  source: "deterministic" | "ai";
  note: string | null;
}

export interface Proposal {
  persisted: boolean;
  existing_package_id: string | null;
  resume_variant_id: string | null;
  recommended_achievement_ids: string[];
  recommended_skill_order: string[];
  summary_suggestion: string | null;
  tailoring_notes: string[];
  cover_letter_notes: string[];
  missing_evidence: string[];
  outreach_draft: string | null;
  warnings: string[];
  claims: Claim[];
  provenance: Record<string, unknown>;
  ai_note: string | null;
}

function Items({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <strong>{title}</strong>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export function ApplicationPrep({ profileId, jobId }: { profileId: string; jobId: string }) {
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [summary, setSummary] = useState("");
  const [outreach, setOutreach] = useState("");
  const [approved, setApproved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function prepare() {
    setBusy(true);
    setError(null);
    setApproved(false);
    try {
      const response = await fetch(`${base}/profiles/${profileId}/jobs/${jobId}/prepare`, { method: "POST" });
      if (!response.ok) throw new Error(`Unable to prepare (${response.status})`);
      const loaded = (await response.json()) as Proposal;
      setProposal(loaded);
      setSummary(loaded.summary_suggestion ?? "");
      setOutreach(loaded.outreach_draft ?? "");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to prepare");
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    if (!proposal) return;
    setError(null);
    const response = await fetch(`${base}/profiles/${profileId}/jobs/${jobId}/prepare/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        resume_variant_id: proposal.resume_variant_id,
        recommended_achievement_ids: proposal.recommended_achievement_ids,
        recommended_skill_order: proposal.recommended_skill_order,
        summary_suggestion: summary || null,
        tailoring_notes: proposal.tailoring_notes,
        missing_evidence: proposal.missing_evidence,
        cover_letter_notes: proposal.cover_letter_notes,
        outreach_draft: outreach || null,
        provenance: proposal.provenance,
      }),
    });
    if (!response.ok) {
      setError(`Unable to approve (${response.status})`);
      return;
    }
    setApproved(true);
  }

  return (
    <div className="job-section">
      <h3>Application preparation</h3>
      <p>
        Suggestions are built only from your profile. Nothing is saved until you approve it, and CareerFlow never sends
        anything.
      </p>
      <button disabled={busy} onClick={() => void prepare()}>
        {proposal ? "Prepare again" : "Prepare application"}
      </button>
      {error && <p role="alert">{error}</p>}
      {proposal && (
        <div>
          {proposal.ai_note && <p>{proposal.ai_note}</p>}
          <Items title="Warnings" items={proposal.warnings} />
          <Items title="Missing evidence (do not claim these)" items={proposal.missing_evidence} />
          <Items title="Tailoring notes" items={proposal.tailoring_notes} />
          <Items title="Recommended skill order" items={proposal.recommended_skill_order} />
          <label htmlFor="prep-summary">Summary suggestion (editable)</label>
          <br />
          <textarea id="prep-summary" rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} />
          <Items title="Cover letter talking points" items={proposal.cover_letter_notes} />
          {proposal.claims.some((c) => c.basis !== "evidence") && (
            <p>
              Some points are marked <em>inference</em> or <em>unverified</em>: they are not backed by a record in your
              profile, so check them before use.
            </p>
          )}
          {proposal.outreach_draft !== null && (
            <div>
              <label htmlFor="prep-outreach">Recruiter message draft (editable, never sent)</label>
              <br />
              <textarea id="prep-outreach" rows={5} value={outreach} onChange={(e) => setOutreach(e.target.value)} />
            </div>
          )}
          <button onClick={() => void approve()} disabled={approved}>
            {approved ? "Approved and saved" : "Approve and save"}
          </button>
          {proposal.existing_package_id && !approved && <p>Approving replaces your existing package for this job.</p>}
        </div>
      )}
    </div>
  );
}
