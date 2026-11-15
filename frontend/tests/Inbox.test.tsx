import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Dashboard } from "../src/features/jobs/Dashboard";
import { JobList } from "../src/features/jobs/JobList";
import { PAGE_SIZE, buildJobsQuery, defaultFilters } from "../src/features/jobs/inbox";

function job(i: number) {
  return {
    id: `j${i}`,
    title: `Job ${i}`,
    company: "Acme",
    description_text: "d",
    status: "READY_FOR_REVIEW",
    discovered_at: "2026-01-01T00:00:00Z",
    workflow_status: "READY_FOR_REVIEW",
    score: 0.5,
    has_blockers: false,
    location_text: null,
    remote_type: null,
  };
}

describe("buildJobsQuery", () => {
  it("always scopes to the profile and sends filters to the API", () => {
    const query = new URLSearchParams(
      buildJobsQuery("p1", { ...defaultFilters, status: "SHORTLISTED", minScore: "70", remoteType: "REMOTE" }, 2),
    );
    expect(query.get("profile_id")).toBe("p1");
    expect(query.get("status")).toBe("SHORTLISTED");
    expect(query.get("min_score")).toBe("0.7");
    expect(query.get("remote_type")).toBe("REMOTE");
    expect(query.get("offset")).toBe(String(2 * PAGE_SIZE));
    expect(new URLSearchParams(buildJobsQuery("p1", defaultFilters, 0)).has("status")).toBe(false);
  });
});

describe("Dashboard", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows the counts returned by the API for the active profile", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        profile_id: "p1", total: 4, new_jobs: 3, needs_review: 3, high_fit: 1,
        shortlisted: 1, blocked: 2, unevaluated: 0, by_status: { READY_FOR_REVIEW: 3, SHORTLISTED: 1 },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const onSelect = vi.fn();
    render(<Dashboard profileId="p1" onSelectStatus={onSelect} />);
    expect(await screen.findByTestId("tile-Shortlisted")).toHaveTextContent("1");
    expect(screen.getByTestId("tile-Blocked")).toHaveTextContent("2");
    expect(screen.getByText(/4 jobs in total/)).toBeInTheDocument();
    expect(String(fetchMock.mock.calls[0][0])).toContain("profile_id=p1");
    fireEvent.click(screen.getByRole("button", { name: "Shortlisted" }));
    expect(onSelect).toHaveBeenCalledWith("SHORTLISTED");
  });
});

describe("JobList", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("pages through server results using X-Total-Count", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      const offset = Number(new URL(url).searchParams.get("offset"));
      const data = offset === 0 ? Array.from({ length: PAGE_SIZE }, (_, i) => job(i)) : [job(99)];
      return { ok: true, headers: new Headers({ "X-Total-Count": String(PAGE_SIZE + 1) }), json: async () => data };
    });
    vi.stubGlobal("fetch", fetchMock);
    render(
      <MemoryRouter>
        <JobList profileId="p1" filters={defaultFilters} />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Job 0")).toBeInTheDocument();
    expect(screen.getByText(/Page 1 of 2/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("Job 99")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    await waitFor(() => expect(String(fetchMock.mock.calls.at(-1)?.[0])).toContain(`offset=${PAGE_SIZE}`));
  });

  it("shows an empty state and API errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, headers: new Headers({ "X-Total-Count": "0" }), json: async () => [] }),
    );
    const { unmount } = render(
      <MemoryRouter>
        <JobList profileId="p1" filters={defaultFilters} />
      </MemoryRouter>,
    );
    expect(await screen.findByText("No jobs found.")).toBeInTheDocument();
    unmount();

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500, headers: new Headers(), json: async () => ({}) }));
    render(
      <MemoryRouter>
        <JobList profileId="p1" filters={defaultFilters} />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load jobs");
  });
});
