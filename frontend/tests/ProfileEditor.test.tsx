import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProfileEditor } from "../src/features/profiles/ProfileEditor";
import { toForm, toPayload } from "../src/features/profiles/fields";

const profile = (id: string, name: string) => ({ id, slug: name.toLowerCase(), display_name: name, headline: "Engineer", summary: "Hi", timezone: "UTC" });

type Call = { method: string; url: string; body: unknown };

/** A tiny in-memory API keyed by profile id, so cross-profile leakage would show up. */
function fakeApi(calls: Call[], failOn?: (c: Call) => boolean) {
  const data: Record<string, Record<string, Array<Record<string, unknown>>>> = {
    p1: { experiences: [{ id: "e1", organization: "Northstar", title: "Principal" }], achievements: [{ id: "a1", title: "Platform", verified: true }], education: [], portfolio: [], "role-families": [{ id: "f1", name: "AI", enabled: true }], "role-targets": [] },
    p2: { experiences: [{ id: "e2", organization: "Cedar", title: "Scientist" }], achievements: [], education: [], portfolio: [], "role-families": [], "role-targets": [] },
  };
  const skills: Record<string, unknown[]> = {
    p1: [{ skill_id: "s1", canonical_name: "Python", category: "language", proficiency: null, years_experience: 12, verified: false, aliases: ["Py"] }],
    p2: [],
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const call: Call = { method: init?.method ?? "GET", url: url.replace("http://localhost:8000/api/v1/profiles", ""), body: init?.body ? JSON.parse(String(init.body)) : undefined };
      calls.push(call);
      const reply = (body: unknown, status = 200) => ({ ok: status < 400, status, json: async () => body });
      if (failOn?.(call)) return reply({ detail: "title: Field required" }, 422);
      const [, pid, kind, itemId] = call.url.split("/");
      if (kind === "skills") return reply(call.method === "GET" ? skills[pid] : { skill_id: "s9", canonical_name: "Go", aliases: [] }, call.method === "DELETE" ? 204 : 200);
      if (kind === "contact") return reply(call.method === "GET" ? { full_name: pid === "p1" ? "Jordan Lee" : "Morgan Rivera", email: null } : {});
      if (kind === "search-preferences") return reply(call.method === "GET" ? { remote_preference: "REQUIRED", allowed_cities: ["Austin"], minimum_base_salary: 150000, relocation_allowed: true, currency: "USD" } : {});
      if (kind === "scoring-preferences") return reply(call.method === "GET" ? { weights: { role_alignment: 0.4 } } : {});
      if (kind === "export") return reply({ schema_version: 2, profile: { slug: "x" } });
      if (pid === "import") return reply(profile("p3", "Imported"), 201);
      if (kind && data[pid]?.[kind]) {
        if (call.method === "GET") return reply(data[pid][kind]);
        if (call.method === "DELETE") return { ok: true, status: 204, json: async () => undefined };
        return reply({ id: itemId ?? "new", ...(call.body as object) });
      }
      return reply({ ...profile(pid, "X"), ...(call.body as object) });
    }),
  );
}

const open = async (tab: string) => fireEvent.click(await screen.findByRole("tab", { name: tab }));

describe("profile editor", () => {
  const calls: Call[] = [];
  beforeEach(() => {
    calls.length = 0;
  });
  afterEach(() => vi.unstubAllGlobals());

  it("field helpers convert lists, numbers and blanks", () => {
    const fields = [
      { name: "title", label: "T", type: "text" as const, required: true },
      { name: "years", label: "Y", type: "number" as const },
      { name: "tags", label: "L", type: "list" as const },
      { name: "ok", label: "O", type: "checkbox" as const },
      { name: "note", label: "N", type: "text" as const },
    ];
    expect(toForm(fields, { title: "A", years: 3, tags: ["x", "y"], ok: true })).toEqual({ title: "A", years: "3", tags: "x, y", ok: true, note: "" });
    expect(toPayload(fields, { title: "A", years: "", tags: " x , y ,, ", ok: false, note: "" })).toEqual({ title: "A", years: null, tags: ["x", "y"], ok: false, note: null });
  });

  it("overview loads the contact and saves the profile and contact", async () => {
    fakeApi(calls);
    render(<ProfileEditor profile={profile("p1", "Jordan")} onChanged={vi.fn()} />);
    expect(await screen.findByDisplayValue("Jordan Lee")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Headline"), { target: { value: "Principal Engineer" } });
    fireEvent.click(screen.getByRole("button", { name: "Save overview" }));
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PUT" && c.url === "/p1")?.body).toMatchObject({ headline: "Principal Engineer", slug: "jordan" });
    expect(calls.some((c) => c.method === "PUT" && c.url === "/p1/contact")).toBe(true);
  });

  it.each([
    ["Experience", "Principal at Northstar", "Organization", "Cedar", "experiences"],
    ["Achievements", "Platform ✓ verified", "Title", "Better platform", "achievements"],
  ])("%s: lists, edits and deletes records", async (tab, summary, label, value, kind) => {
    fakeApi(calls);
    render(<ProfileEditor profile={profile("p1", "Jordan")} onChanged={vi.fn()} />);
    await open(tab);
    expect(await screen.findByText(summary)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT" && c.url.startsWith(`/p1/${kind}/`))).toBe(true));
    fireEvent.click(await screen.findByRole("button", { name: "Delete" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.url.startsWith(`/p1/${kind}/`))).toBe(true));
  });

  it("achievements keep STAR fields, technologies and the verified flag", async () => {
    fakeApi(calls);
    render(<ProfileEditor profile={profile("p1", "Jordan")} onChanged={vi.fn()} />);
    await open("Achievements");
    fireEvent.click(await screen.findByRole("button", { name: "Add achievement" }));
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Cut costs" } });
    fireEvent.change(screen.getByLabelText("Situation"), { target: { value: "Bills were high" } });
    fireEvent.change(screen.getByLabelText("Technologies"), { target: { value: "Python, Azure" } });
    fireEvent.click(screen.getByLabelText(/Verified/));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST" && c.url === "/p1/achievements")?.body).toMatchObject({
      title: "Cut costs", situation: "Bills were high", technologies: ["Python", "Azure"], verified: true, result: null,
    }));
  });

  it("shows server validation errors and keeps the form open", async () => {
    fakeApi(calls, (c) => c.method === "POST" && c.url === "/p1/education");
    render(<ProfileEditor profile={profile("p1", "Jordan")} onChanged={vi.fn()} />);
    await open("Education");
    fireEvent.click(await screen.findByRole("button", { name: "Add education" }));
    fireEvent.change(screen.getByLabelText("Institution"), { target: { value: "Uni" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("title: Field required");
    expect(screen.getByRole("form", { name: "Education form" })).toBeInTheDocument();
  });

  it("skills: add, verify toggle, aliases and remove", async () => {
    fakeApi(calls);
    render(<ProfileEditor profile={profile("p1", "Jordan")} onChanged={vi.fn()} />);
    await open("Skills");
    expect(await screen.findByText("Python")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("New alias for Python"), { target: { value: "Python3" } });
    fireEvent.click(screen.getByRole("button", { name: "Add alias" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST" && c.url === "/p1/skills/s1/aliases")?.body).toEqual({ alias: "Python3" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove alias Py" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.url === "/p1/skills/s1/aliases/Py")).toBe(true));
    fireEvent.click(screen.getByRole("button", { name: "Mark verified" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PUT" && c.url === "/p1/skills/s1")?.body).toEqual({ verified: true }));
    fireEvent.change(screen.getByLabelText("Skill"), { target: { value: "Go" } });
    fireEvent.change(screen.getByLabelText("Aliases (comma separated)"), { target: { value: "Golang, go-lang" } });
    fireEvent.click(screen.getByRole("button", { name: "Add skill" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST" && c.url === "/p1/skills")?.body).toMatchObject({ canonical_name: "Go", aliases: ["Golang", "go-lang"] }));
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.url === "/p1/skills/s1")).toBe(true));
  });

  it("role families and targets share the Role targets tab", async () => {
    fakeApi(calls);
    render(<ProfileEditor profile={profile("p1", "Jordan")} onChanged={vi.fn()} />);
    await open("Role targets");
    expect(await screen.findByText("AI")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add role target" }));
    fireEvent.change(screen.getByLabelText("Title pattern (use * as wildcard)"), { target: { value: "principal*" } });
    fireEvent.change(screen.getByLabelText("Target seniority"), { target: { value: "principal, staff" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST" && c.url === "/p1/role-targets")?.body).toMatchObject({ title_pattern: "principal*", target_seniority: ["principal", "staff"] }));
  });

  it("search preferences load from the API and save every field type", async () => {
    fakeApi(calls);
    render(<ProfileEditor profile={profile("p1", "Jordan")} onChanged={vi.fn()} />);
    await open("Search preferences");
    expect(await screen.findByDisplayValue("Austin")).toBeInTheDocument();
    expect(screen.getByLabelText("Remote work")).toHaveValue("REQUIRED");
    fireEvent.change(screen.getByLabelText("excluded companies"), { target: { value: "Acme, Initech" } });
    fireEvent.click(screen.getByRole("button", { name: "Save search preferences" }));
    expect(await screen.findByText(/Saved/)).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PUT" && c.url === "/p1/search-preferences")?.body).toMatchObject({
      remote_preference: "REQUIRED", allowed_cities: ["Austin"], excluded_companies: ["Acme", "Initech"], minimum_base_salary: 150000, relocation_allowed: true, currency: "USD",
    });
  });

  it("scoring weights save only the dimensions that were set", async () => {
    fakeApi(calls);
    render(<ProfileEditor profile={profile("p1", "Jordan")} onChanged={vi.fn()} />);
    await open("Scoring");
    expect(await screen.findByDisplayValue("0.4")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("technical alignment"), { target: { value: "0.3" } });
    fireEvent.click(screen.getByRole("button", { name: "Save scoring" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PUT" && c.url === "/p1/scoring-preferences")?.body).toEqual({ weights: { role_alignment: 0.4, technical_alignment: 0.3 } }));
  });

  it("scoring errors from the API are shown", async () => {
    fakeApi(calls, (c) => c.method === "PUT" && c.url.endsWith("scoring-preferences"));
    render(<ProfileEditor profile={profile("p1", "Jordan")} onChanged={vi.fn()} />);
    await open("Scoring");
    fireEvent.click(await screen.findByRole("button", { name: "Save scoring" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("imports pasted JSON and reports invalid JSON", async () => {
    fakeApi(calls);
    const onChanged = vi.fn();
    render(<ProfileEditor profile={profile("p1", "Jordan")} onChanged={onChanged} />);
    await open("Export / import");
    fireEvent.change(screen.getByLabelText("Paste an export to import"), { target: { value: "{not json" } });
    fireEvent.click(screen.getByRole("button", { name: "Import" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Paste an export to import"), { target: { value: '{"schema_version": 2, "profile": {"slug": "x", "display_name": "X"}}' } });
    fireEvent.click(screen.getByRole("button", { name: "Import" }));
    expect(await screen.findByText("Imported as Imported.")).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalled();
  });

  it("switching profiles never shows the other profile's records", async () => {
    fakeApi(calls);
    const { rerender } = render(<ProfileEditor key="p1" profile={profile("p1", "Jordan")} onChanged={vi.fn()} />);
    await open("Experience");
    expect(await screen.findByText("Principal at Northstar")).toBeInTheDocument();
    rerender(<ProfileEditor key="p2" profile={profile("p2", "Morgan")} onChanged={vi.fn()} />);
    await open("Experience");
    expect(await screen.findByText("Scientist at Cedar")).toBeInTheDocument();
    expect(screen.queryByText("Principal at Northstar")).toBeNull();
    const region = screen.getByRole("region", { name: "Editing Morgan" });
    expect(within(region).queryByText(/Northstar/)).toBeNull();
    expect(calls.filter((c) => c.url.includes("/experiences")).map((c) => c.url)).toEqual(["/p1/experiences", "/p2/experiences"]);
  });
});
