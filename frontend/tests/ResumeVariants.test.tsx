import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ResumeVariants } from "../src/features/applications/ResumeVariants";

describe("ResumeVariants", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lists, creates and deletes variants for the active profile", async () => {
    const calls: Array<[string, RequestInit | undefined]> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push([url, init]);
        const body = url.endsWith("/profiles") ? [{ id: "p1", display_name: "Jordan" }]
          : url.endsWith("/role-families") ? [{ id: "f1", name: "AI Engineer" }]
          : url.endsWith("/resume-variants") && init?.method !== "POST" ? [{ id: "v1", name: "Architect", role_family_id: "f1", summary_strategy: null, preferred_skill_categories: ["ai"] }]
          : {};
        return { ok: true, status: 200, json: async () => body };
      }),
    );
    render(<ResumeVariants />);
    expect(await screen.findByText("Architect")).toBeInTheDocument();
    expect(screen.getByText(/AI Engineer/, { selector: "li" })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Analyst" } });
    fireEvent.change(screen.getByLabelText("Preferred skill categories (comma separated)"), { target: { value: "viz, sql" } });
    fireEvent.click(screen.getByRole("button", { name: "Create variant" }));
    await waitFor(() => {
      const post = calls.find(([, i]) => i?.method === "POST");
      expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({ name: "Analyst", preferred_skill_categories: ["viz", "sql"] });
    });
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(calls.some(([u, i]) => u.endsWith("/resume-variants/v1") && i?.method === "DELETE")).toBe(true));
  });
});
