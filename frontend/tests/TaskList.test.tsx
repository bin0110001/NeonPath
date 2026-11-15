import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TaskList } from "../src/features/tasks/TaskList";

const failed = {
  id: "t1", task_type: "extract_requirements", status: "FAILED", attempts: 3, max_attempts: 3,
  created_at: "2026-01-01T00:00:00Z", error_code: "AiTimeoutError", error_message: "provider timed out",
};

describe("TaskList", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows failed tasks with their error and can retry them", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => ({
      ok: true, status: 200, json: async () => (init?.method === "POST" ? { ...failed, status: "QUEUED" } : [failed]),
    }));
    vi.stubGlobal("fetch", fetchMock);
    render(<TaskList />);
    expect(await screen.findByText("AiTimeoutError: provider timed out")).toBeInTheDocument();
    expect(screen.getByText("3/3")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([u, i]) => String(u).endsWith("/tasks/t1/retry") && i?.method === "POST")).toBe(true),
    );
  });

  it("filters to failed tasks via the API", async () => {
    const fetchMock = vi.fn<(url: string) => Promise<unknown>>(async () => ({ ok: true, status: 200, json: async () => [] }));
    vi.stubGlobal("fetch", fetchMock);
    render(<TaskList />);
    expect(await screen.findByText("No tasks.")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Failed only"));
    await waitFor(() => expect(String(fetchMock.mock.calls.at(-1)?.[0])).toContain("status=FAILED"));
  });
});
