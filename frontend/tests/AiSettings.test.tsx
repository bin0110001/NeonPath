import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AiSettings } from "../src/features/settings/AiSettings";

const config = {
  enabled: false, provider: "anthropic", model: "claude-x", endpoint: "", api_key_set: true, source: "environment",
  providers: {
    fixture: { label: "Fixture (offline demo)", needs_key: false, needs_endpoint: false },
    anthropic: { label: "Anthropic (hosted)", needs_key: true, needs_endpoint: false },
    ollama: { label: "Ollama (local)", needs_key: false, needs_endpoint: true },
  },
};

function stub(testResult: unknown, calls: Array<[string, RequestInit | undefined]>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push([url, init]);
      if (url.endsWith("/test")) return { ok: true, status: 200, json: async () => testResult };
      if (init?.method === "PUT") return { ok: true, status: 200, json: async () => ({ ...config, ...JSON.parse(String(init.body)), source: "saved" }) };
      return { ok: true, status: 200, json: async () => config };
    }),
  );
}

describe("AiSettings", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows only whether a key is set, never a key field", async () => {
    stub({}, []);
    render(<AiSettings />);
    expect(await screen.findByText("set")).toBeInTheDocument();
    expect(screen.getByText("AI_API_KEY")).toBeInTheDocument();
    expect(screen.queryByLabelText(/api key/i)).toBeNull();
  });

  it("saves the non-secret selection and reveals the endpoint field for local providers", async () => {
    const calls: Array<[string, RequestInit | undefined]> = [];
    stub({}, calls);
    render(<AiSettings />);
    await screen.findByText("set");
    fireEvent.change(screen.getByLabelText("Provider"), { target: { value: "ollama" } });
    fireEvent.change(screen.getByLabelText("Endpoint"), { target: { value: "http://gpu:11434/v1" } });
    fireEvent.click(screen.getByLabelText("Enable AI"));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    const put = calls.find(([, init]) => init?.method === "PUT");
    expect(JSON.parse(String(put?.[1]?.body))).toEqual({ enabled: true, provider: "ollama", model: "claude-x", endpoint: "http://gpu:11434/v1" });
  });

  it("reports connectivity success and readable failures", async () => {
    stub({ ok: true, provider: "anthropic", model: "claude-x", latency_ms: 123.4, error: null }, []);
    const { unmount } = render(<AiSettings />);
    await screen.findByText("set");
    fireEvent.click(screen.getByRole("button", { name: "Test connection" }));
    await waitFor(() => expect(screen.getByTestId("test-result")).toHaveTextContent("Connected to anthropic (claude-x) in 123.4 ms."));
    unmount();

    stub({ ok: false, provider: "anthropic", model: "claude-x", latency_ms: null, error: "anthropic rejected the credentials (HTTP 401)" }, []);
    render(<AiSettings />);
    await screen.findByText("set");
    fireEvent.click(screen.getByRole("button", { name: "Test connection" }));
    await waitFor(() => expect(screen.getByTestId("test-result")).toHaveTextContent("Connection failed: anthropic rejected the credentials (HTTP 401)"));
  });
});
