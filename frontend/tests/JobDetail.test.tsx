import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { JobDetail } from "../src/features/jobs/JobDetail";

const job = {
  id: "j1",
  title: "Principal AI Engineer",
  company: "Acme Labs",
  description_text: "Build things.",
  status: "READY_FOR_REVIEW",
  discovered_at: "2026-01-01T00:00:00Z",
};

function stubApi(state: { status: string }, posts: string[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const json = (body: unknown, status = 200) => ({
        ok: status < 400,
        status,
        json: async () => body,
      });
      if (init?.method === "POST") {
        posts.push(url);
        if (url.endsWith("/reject") && state.status === "REJECTED") {
          return json({ detail: "Transition REJECTED -> REJECTED is not allowed" }, 409);
        }
        if (url.endsWith("/shortlist")) state.status = "SHORTLISTED";
        if (url.endsWith("/reject")) state.status = "REJECTED";
        return json({});
      }
      if (url.endsWith("/jobs/j1")) return json(job);
      if (url.endsWith("/sources") || url.endsWith("/requirements")) return json([]);
      if (url.endsWith("/profiles")) return json([{ id: "p1", display_name: "Jordan" }, { id: "p2", display_name: "Morgan" }]);
      if (url.includes("/workflow")) return json({ job_id: "j1", profile_id: "p1", status: state.status });
      if (url.includes("/status-history")) return json([]);
      if (url.includes("/evaluations/latest")) return json(null);
      if (url.includes("/comparison")) {
        return json([
          { id: "e1", job_id: "j1", profile_id: "p1", overall_score: 0.95, confidence: 1, blockers: [], strengths: ["Strong role alignment"], gaps: [], unknowns: [], transferable_matches: [], dimension_scores_json: {}, evaluator_version: "deterministic-v2.0", created_at: "2026-01-01T00:00:00Z" },
          { id: "e2", job_id: "j1", profile_id: "p2", overall_score: 0.4, confidence: 1, blockers: [], strengths: [], gaps: ["Weak role alignment"], unknowns: [], transferable_matches: [], dimension_scores_json: {}, evaluator_version: "deterministic-v2.0", created_at: "2026-01-01T00:00:00Z" },
        ]);
      }
      if (url.includes("/evaluations?")) return json([]);
      return json({}, 404);
    }),
  );
}

function renderDetail() {
  render(
    <MemoryRouter initialEntries={["/jobs/j1"]}>
      <Routes>
        <Route path="/jobs/:jobId" element={<JobDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("JobDetail", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows the active profile's status and applies a workflow action", async () => {
    const posts: string[] = [];
    stubApi({ status: "READY_FOR_REVIEW" }, posts);
    renderDetail();
    expect(await screen.findByRole("heading", { name: "Principal AI Engineer" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("workflow-status")).toHaveTextContent("READY_FOR_REVIEW"));

    fireEvent.click(screen.getByRole("button", { name: "Shortlist" }));
    await waitFor(() => expect(screen.getByTestId("workflow-status")).toHaveTextContent("SHORTLISTED"));
    expect(posts).toEqual([expect.stringContaining("/jobs/j1/shortlist")]);
  });

  it("surfaces a 409 for a forbidden transition", async () => {
    stubApi({ status: "REJECTED" }, []);
    renderDetail();
    await waitFor(() => expect(screen.getByTestId("workflow-status")).toHaveTextContent("REJECTED"));
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("not allowed");
  });

  it("compares the same job across profiles with reasons", async () => {
    stubApi({ status: "READY_FOR_REVIEW" }, []);
    renderDetail();
    expect(await screen.findByText("95%")).toBeInTheDocument();
    expect(screen.getByText("40%")).toBeInTheDocument();
    expect(screen.getByText(/Weak role alignment/)).toBeInTheDocument();
    expect(screen.getByText("Morgan", { selector: "td" })).toBeInTheDocument();
  });
});
