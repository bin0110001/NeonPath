import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApplicationPrep } from "../src/features/applications/ApplicationPrep";

const proposal = {
  persisted: false, existing_package_id: null, resume_variant_id: "v1", recommended_achievement_ids: ["a1"],
  recommended_skill_order: ["Python", "Azure"], summary_suggestion: "Emphasise Python", tailoring_notes: ["Use the 'AI' variant."],
  cover_letter_notes: ["Talk about 'LLM platform'.", "Managed 400 engineers [unverified: not backed by your profile]"],
  missing_evidence: ["No profile evidence for required skill: Kubernetes"], outreach_draft: "Hello!\n\n[DRAFT for your review. CareerFlow never sends messages.]",
  warnings: ["Skill 'Tableau' is not marked verified."],
  claims: [
    { text: "Talk about 'LLM platform'.", basis: "evidence", evidence_ids: ["achievement:a1"], source: "deterministic", note: null },
    { text: "Managed 400 engineers", basis: "unverified", evidence_ids: [], source: "ai", note: "no evidence cited" },
  ],
  provenance: { generator: "deterministic+ai" }, ai_note: null,
};

describe("ApplicationPrep", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows the proposal with warnings and saves only after approval", async () => {
    const calls: Array<[string, RequestInit | undefined]> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push([url, init]);
        return { ok: true, status: 200, json: async () => (url.endsWith("/prepare") ? proposal : { id: "p1" }) };
      }),
    );
    render(<ApplicationPrep profileId="p" jobId="j" />);
    expect(screen.getByText(/Nothing is saved until you approve/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Prepare application" }));

    expect(await screen.findByText("No profile evidence for required skill: Kubernetes")).toBeInTheDocument();
    expect(screen.getByText("Skill 'Tableau' is not marked verified.")).toBeInTheDocument();
    expect(screen.getByText(/Managed 400 engineers \[unverified/)).toBeInTheDocument();
    expect(screen.getByText(/inference.*unverified|not backed by a record/)).toBeInTheDocument();
    expect(calls.map(([u]) => u.split("/api/v1")[1])).toEqual(["/profiles/p/jobs/j/prepare"]); // read-only so far

    fireEvent.change(screen.getByLabelText("Summary suggestion (editable)"), { target: { value: "My own summary" } });
    fireEvent.click(screen.getByRole("button", { name: "Approve and save" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Approved and saved" })).toBeDisabled());
    const approve = calls.find(([u]) => u.endsWith("/prepare/approve"));
    const body = JSON.parse(String(approve?.[1]?.body));
    expect(body).toMatchObject({ summary_suggestion: "My own summary", resume_variant_id: "v1", provenance: { generator: "deterministic+ai" } });
    expect(body.outreach_draft).toContain("never sends");
  });

  it("shows an error when preparing fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 404, json: async () => ({}) })));
    render(<ApplicationPrep profileId="p" jobId="j" />);
    fireEvent.click(screen.getByRole("button", { name: "Prepare application" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to prepare (404)");
  });
});
