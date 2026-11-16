import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ArtifactsPanel } from "../src/features/applications/ArtifactsPanel";

const artifact = { id: "x1", kind: "resume", format: "pdf", version: 2, redacted: true, content_sha256: "abc", created_at: "2026-01-01T00:00:00Z", size_bytes: 4096 };

describe("ArtifactsPanel", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("creates a public PDF, offers a download link and verifies reproducibility", async () => {
    const calls: Array<[string, RequestInit | undefined]> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push([url, init]);
        const body = url.endsWith("/artifact-formats") ? ["docx", "html", "markdown", "pdf"]
          : url.includes("/rerender") ? { matches_stored: true }
          : init?.method === "POST" ? artifact
          : [artifact];
        return { ok: true, status: 200, json: async () => body };
      }),
    );
    render(<ArtifactsPanel profileId="p1" jobId="j1" />);
    const link = await screen.findByRole("link", { name: "Download" });
    expect(link).toHaveAttribute("href", "http://localhost:8000/api/v1/profiles/p1/artifacts/x1/download");
    expect(screen.getByText(/PDF v2 \(public\)/)).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/Public copy/));
    fireEvent.change(screen.getByLabelText("Format"), { target: { value: "docx" } });
    fireEvent.click(screen.getByRole("button", { name: "Create document" }));
    await waitFor(() => {
      const post = calls.find(([u, i]) => u.endsWith("/profiles/p1/artifacts") && i?.method === "POST");
      expect(JSON.parse(String(post?.[1]?.body))).toEqual({ format: "docx", job_id: "j1", redacted: true, include_cover_letter_notes: false });
    });

    fireEvent.click(screen.getByRole("button", { name: "Verify" }));
    expect(await screen.findByText(/reproduced exactly/)).toBeInTheDocument();
  });
});
