import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/App";

describe("App", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the product shell", () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => [] }));
    render(<App />);
    expect(screen.getByRole("heading", { name: "CareerFlow" })).toBeInTheDocument();
  });
});
