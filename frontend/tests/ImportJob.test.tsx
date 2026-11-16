import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ImportJob } from "../src/features/jobs/ImportJob";

function renderForm() {
  render(
    <MemoryRouter>
      <Routes>
        <Route path="/" element={<ImportJob />} />
        <Route path="/jobs/:jobId" element={<p>detail page</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

function fill() {
  fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Staff Engineer" } });
  fireEvent.change(screen.getByLabelText("Company"), { target: { value: "Acme" } });
  fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Build things" } });
}

describe("ImportJob", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts the pasted job and opens its detail page", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ id: "j9" }) });
    vi.stubGlobal("fetch", fetchMock);
    renderForm();
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Import job" }));
    expect(await screen.findByText("detail page")).toBeInTheDocument();
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body).toMatchObject({ title: "Staff Engineer", company: "Acme", description_text: "Build things" });
    expect(body.source.adapter).toBe("manual");
  });

  it("shows a validation message on 422", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 422, json: async () => ({}) }));
    renderForm();
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Import job" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("required"));
  });
});
