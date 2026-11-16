import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SearchesPage } from "../src/features/searches/SearchesPage";

const search = { id: "s1", name: "Platform roles", source_id: "src1", query: "platform", schedule_minutes: 60, enabled: true, last_run_at: null, next_run_at: "2026-01-01T13:00:00Z", last_schedule_status: null };
const failedRun = { id: "r1", trigger: "schedule", status: "FAILED", started_at: "2026-01-01T12:00:00Z", discovered: 0, created: 0, skipped: 0, failed: 0, error_code: "SourceFetchError", error_message: "source returned HTTP 500" };

function stub(calls: string[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? "GET"} ${url}`);
      const body = url.endsWith("/profiles") ? [{ id: "p1", display_name: "Jordan" }]
        : url.endsWith("/sources") ? [{ id: "src1", name: "Demo feed", adapter: "rss", health: "HEALTHY" }]
        : url.includes("/runs") ? [failedRun]
        : url.endsWith("/searches") && init?.method !== "POST" ? [search]
        : {};
      return { ok: true, status: 200, json: async () => body };
    }),
  );
}

describe("SearchesPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lists searches with run history and source errors, and runs one now", async () => {
    const calls: string[] = [];
    stub(calls);
    render(<SearchesPage />);
    expect(await screen.findByText("Platform roles")).toBeInTheDocument();
    expect(await screen.findByText(/SourceFetchError: source returned HTTP 500/)).toBeInTheDocument();
    expect(screen.getByText(/every 60 min/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Run now" }));
    await waitFor(() => expect(calls).toContain("POST http://localhost:8000/api/v1/profiles/p1/searches/s1/run"));
  });

  it("creates a search with keywords and a schedule", async () => {
    const calls: string[] = [];
    stub(calls);
    render(<SearchesPage />);
    await screen.findByText("Platform roles");
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "ML roles" } });
    fireEvent.change(screen.getByLabelText("Keywords (any, comma separated)"), { target: { value: "ml, llm" } });
    fireEvent.change(screen.getByLabelText("Run every (minutes)"), { target: { value: "30" } });
    fireEvent.click(screen.getByRole("button", { name: "Create search" }));
    await waitFor(() => expect(calls.some((c) => c.startsWith("POST") && c.endsWith("/profiles/p1/searches"))).toBe(true));
  });
});
