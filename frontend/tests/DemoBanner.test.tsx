import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/App";

function stub(config: { demo_mode: boolean }) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => ({
      ok: true,
      json: async () => (url.endsWith("/config") ? config : []),
    })),
  );
}

describe("demo banner", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("is shown only when the API reports demo mode", async () => {
    stub({ demo_mode: true });
    render(<App />);
    expect(await screen.findByRole("status")).toHaveTextContent("Demo mode");
  });

  it("is absent otherwise", async () => {
    stub({ demo_mode: false });
    render(<App />);
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.queryByRole("status")).toBeNull();
  });
});
