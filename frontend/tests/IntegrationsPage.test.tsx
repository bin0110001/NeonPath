import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IntegrationsPage } from "../src/features/integrations/IntegrationsPage";

const link = { id: "l1", application_id: "a1", classification: "interview_request", score: 0.8, reasons: ["sender domain matches contoso.com"], received_at: "2026-06-01T00:00:00Z", status: "SUGGESTED" };
const pending = { id: "r1", action: "create", status: "PENDING", payload_json: { title: "Interview: Platform Engineer at Contoso", starts_at: "2026-06-03T10:00:00Z" }, error: null };

function stub(calls: string[], accounts: unknown[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? "GET"} ${url.replace("http://localhost:8000/api/v1", "")}`);
      const body = url.endsWith("/profiles") ? [{ id: "p1", display_name: "Jordan" }]
        : url.endsWith("/integrations") ? accounts
        : url.endsWith("/email/links") ? [link]
        : url.endsWith("/calendar/requests") ? [pending]
        : url.endsWith("/draft") ? { body: "[DRAFT for you to review and send yourself. CareerFlow never sends email.]\n\nHello," }
        : { scanned: 3, linked: 1, created: 1, updated: 0 };
      return { ok: true, status: 200, json: async () => body };
    }),
  );
}

const connected = [
  { kind: "email", connected: true, provider: "google", scopes: ["gmail.readonly"], allow_writes: false, last_synced_at: null },
  { kind: "calendar", connected: true, provider: "google", scopes: [], allow_writes: true, last_synced_at: null },
];

describe("IntegrationsPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("has no send action; drafts are shown for the user to copy", async () => {
    const calls: string[] = [];
    stub(calls, connected);
    render(<IntegrationsPage />);
    expect(await screen.findByText(/interview request/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^send/i })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Draft reply" }));
    expect(await screen.findByLabelText("Reply draft")).toHaveTextContent("CareerFlow never sends email");
  });

  it("syncs email and requires explicit approval for calendar writes", async () => {
    const calls: string[] = [];
    stub(calls, connected);
    render(<IntegrationsPage />);
    expect(await screen.findByText("Interview: Platform Engineer at Contoso", { exact: false })).toBeInTheDocument();
    expect(calls.some((c) => c.includes("/approve"))).toBe(false); // listing a request never writes
    fireEvent.click(screen.getByRole("button", { name: "Sync email" }));
    expect(await screen.findByText("Scanned 3 messages, linked 1.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(calls).toContain("POST /profiles/p1/calendar/requests/r1/approve"));
  });

  it("offers to connect unconnected accounts and shows readable errors", async () => {
    const calls: string[] = [];
    stub(calls, [
      { kind: "email", connected: false, provider: null, scopes: [], allow_writes: false, last_synced_at: null },
      { kind: "calendar", connected: false, provider: null, scopes: [], allow_writes: false, last_synced_at: null },
    ]);
    vi.stubGlobal("open", vi.fn());
    render(<IntegrationsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Connect email" }));
    await waitFor(() => expect(calls).toContain("POST /profiles/p1/integrations/email/connect"));
  });
});
