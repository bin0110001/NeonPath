import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DuplicateReview } from "../src/features/duplicates/DuplicateReview";

const brief = (id: string, title: string, sources: number) => ({
  id, title, company: "Contoso", location_text: "Austin", remote_type: null, salary_min: null, salary_max: null, source_count: sources,
});
const pair = {
  id: "d1", classification: "LIKELY", score: 0.91, reasons: ["same company", "similar title (95%)"], status: "PENDING",
  canonical: brief("a", "Platform Engineer", 1), job: brief("b", "Platform Engineer (Remote)", 1),
};

describe("DuplicateReview", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows pairs side by side and merges / dismisses through the API", async () => {
    const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<unknown>>(async (url) => ({
      ok: true,
      status: 200,
      json: async () => (url.includes("/duplicates?") ? [pair] : []),
    }));
    vi.stubGlobal("fetch", fetchMock);
    render(<DuplicateReview />);
    expect(await screen.findByText(/91%/)).toBeInTheDocument();
    expect(screen.getByText("Platform Engineer")).toBeInTheDocument();
    expect(screen.getByText("Platform Engineer (Remote)")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Merge, keep newer" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/duplicates/d1/merge"));
      expect(call && JSON.parse(String(call[1]?.body))).toEqual({ keep_job_id: "b" });
    });
    fireEvent.click(screen.getByRole("button", { name: "Not a duplicate" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/duplicates/d1/dismiss"))).toBe(true));
  });

  it("lists active merges with an unmerge action", async () => {
    const merge = { id: "m1", canonical_job_id: "aaaaaaaa-1", merged_job_id: "bbbbbbbb-2", merged_at: "2026-01-01T00:00:00Z" };
    const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<unknown>>(async (url) => ({
      ok: true, status: 200, json: async () => (url.endsWith("/merges") ? [merge] : []),
    }));
    vi.stubGlobal("fetch", fetchMock);
    render(<DuplicateReview />);
    expect(await screen.findByText("No duplicates to review.")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "Unmerge" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/merges/m1/unmerge"))).toBe(true));
  });
});
