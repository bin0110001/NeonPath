import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MetricsPanel, Pipeline } from "../src/features/tracking/Pipeline";

const metrics = { jobs_reviewed: 5, shortlisted: 4, applications_submitted: 4, screens: 2, interviews: 2, final_interviews: 1, offers: 1, responded: 3, response_rate: 0.75, median_days_to_response: 1 };
const card = { job_id: "j1", title: "Platform Engineer", company: "Contoso", status: "APPLIED", score: 0.9, application_id: "a1", applied_at: null, next_follow_up_at: null, next_interview_at: null };

function stub(calls: Array<[string, RequestInit | undefined]>, transitionStatus = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push([url, init]);
      if (url.endsWith("/transition")) {
        return { ok: transitionStatus < 400, status: transitionStatus, json: async () => ({ detail: "Transition APPLIED -> OFFER is not allowed" }) };
      }
      const body = url.endsWith("/profiles") ? [{ id: "p1", display_name: "Jordan" }]
        : url.endsWith("/pipeline") ? { columns: { APPLIED: [card] } }
        : url.endsWith("/overview") ? { metrics, due_follow_ups: [{ id: "f1", application_id: "a1", due_at: "2026-01-01T00:00:00Z", type: "check_in", status: "OPEN" }], upcoming_interviews: [{ id: "i1", application_id: "a1", type: "system_design", scheduled_at: "2026-02-01T10:00:00Z" }] }
        : url.endsWith("/interviews/i1/prepare") ? { focus_areas: ["Requirements, constraints and capacity estimates"], relevant_achievements: [{ id: "a1", title: "Scaled LLM platform", why: "matches the job" }], technical_topics: [], system_design_themes: [], ai_ml_topics: [], leadership_stories: [], weak_spots: ["No profile evidence for required skill: Rust"], questions_to_ask: ["What does success look like?"], warnings: [], ai_stories: [], ai_note: "AI is disabled" }
        : {};
      return { ok: true, status: 200, json: async () => body };
    }),
  );
}

describe("MetricsPanel", () => {
  it("shows n/a without applications", () => {
    render(<MetricsPanel metrics={{ ...metrics, applications_submitted: 0, response_rate: null, median_days_to_response: null }} />);
    expect(screen.getByTestId("response-rate")).toHaveTextContent("n/a");
  });
});

describe("Pipeline", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders cards per column with funnel metrics and due follow-ups", async () => {
    stub([]);
    render(<MemoryRouter><Pipeline /></MemoryRouter>);
    await screen.findByRole("link", { name: "Platform Engineer" });
    expect(within(screen.getByLabelText("APPLIED column")).getByRole("link", { name: "Platform Engineer" })).toBeInTheDocument();
    expect(screen.getByLabelText("SHORTLISTED column")).toHaveTextContent("SHORTLISTED (0)");
    expect(screen.getByTestId("response-rate")).toHaveTextContent("75%");
    expect(screen.getByText("Follow-ups due (1)")).toBeInTheDocument();
  });

  it("moves a card with a validated transition and shows the server's refusal", async () => {
    const calls: Array<[string, RequestInit | undefined]> = [];
    stub(calls, 409);
    render(<MemoryRouter><Pipeline /></MemoryRouter>);
    const select = await screen.findByLabelText("Move Platform Engineer");
    fireEvent.change(select, { target: { value: "OFFER" } });
    expect(await screen.findByRole("alert")).toHaveTextContent("not allowed");
    const call = calls.find(([u]) => u.endsWith("/jobs/j1/transition"));
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ profile_id: "p1", to_status: "OFFER" });
  });

  it("adds a follow-up for an application", async () => {
    const calls: Array<[string, RequestInit | undefined]> = [];
    stub(calls);
    render(<MemoryRouter><Pipeline /></MemoryRouter>);
    await screen.findByLabelText("Follow-up application");
    fireEvent.change(screen.getByLabelText("Follow-up application"), { target: { value: "a1" } });
    fireEvent.change(screen.getByLabelText("Follow-up due"), { target: { value: "2026-02-01T09:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Add follow-up" }));
    await waitFor(() => expect(calls.some(([u, i]) => u.endsWith("/profiles/p1/follow-ups") && i?.method === "POST")).toBe(true));
  });

  it("prepares an upcoming interview and shows grounded suggestions and weak spots", async () => {
    stub([]);
    render(<MemoryRouter><Pipeline /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "Prepare" }));
    expect(await screen.findByText("Scaled LLM platform (matches the job)")).toBeInTheDocument();
    expect(screen.getByText("No profile evidence for required skill: Rust")).toBeInTheDocument();
    expect(screen.getByText("What does success look like?")).toBeInTheDocument();
  });
});
