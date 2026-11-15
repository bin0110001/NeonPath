import { expect, test } from "@playwright/test";

const unique = () => `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;

async function importJob(page: import("@playwright/test").Page, title: string) {
  await page.goto("/");
  await page.getByRole("button", { name: "Jobs" }).click();
  await page.getByLabel("Title").fill(title);
  await page.getByLabel("Company").fill("E2E Demo Co");
  await page.getByLabel("Work arrangement").selectOption("REMOTE");
  await page
    .getByLabel("Description")
    .fill("Build LLM applications with Python and distributed systems on Azure.");
  await page.getByRole("button", { name: "Import job" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
}

async function selectProfile(page: import("@playwright/test").Page, name: string) {
  await page.getByLabel("Active profile").selectOption({ label: name });
}

test("seeded profiles exist", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("status")).toContainText("Demo mode");
  await expect(page.getByRole("button", { name: "Jordan Lee" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Morgan Rivera" })).toBeVisible();
});

test("import, evaluate per profile, then shortlist", async ({ page }) => {
  await importJob(page, `Principal AI Engineer ${unique()}`);
  await selectProfile(page, "Jordan Lee");
  await expect(page.getByTestId("workflow-status")).toHaveText("READY_FOR_REVIEW");

  // Auto-evaluated on import: both profiles appear in the comparison with different scores.
  const rows = page.locator("table tbody tr");
  await expect(rows).toHaveCount(2);
  await expect(rows.filter({ hasText: "Jordan Lee" })).toBeVisible();
  await expect(rows.filter({ hasText: "Morgan Rivera" })).toBeVisible();
  const scores = await rows.locator("td:nth-child(2)").allTextContents();
  expect(new Set(scores).size).toBe(2);

  await page.getByRole("button", { name: /^(Re-evaluate|Evaluate)$/ }).click();
  await expect(page.getByText(/Overall score:/)).toBeVisible();

  await page.getByRole("button", { name: "Shortlist" }).click();
  await expect(page.getByTestId("workflow-status")).toHaveText("SHORTLISTED");
  await expect(page.getByText(/READY_FOR_REVIEW → SHORTLISTED/)).toBeVisible();

  // Workflow state is per profile.
  await selectProfile(page, "Morgan Rivera");
  await expect(page.getByTestId("workflow-status")).toHaveText("READY_FOR_REVIEW");
});

test("import then reject; a repeated reject is refused", async ({ page }) => {
  await importJob(page, `Platform Engineer ${unique()}`);
  await selectProfile(page, "Jordan Lee");
  await page.getByRole("button", { name: "Reject" }).click();
  await expect(page.getByTestId("workflow-status")).toHaveText("REJECTED");
  await page.getByRole("button", { name: "Reject" }).click();
  await expect(page.getByRole("alert")).toContainText("not allowed");
  await expect(page.getByTestId("workflow-status")).toHaveText("REJECTED");
});

test("dashboard numbers match the inbox for the active profile", async ({ page }) => {
  await importJob(page, `Staff Engineer ${unique()}`);
  await selectProfile(page, "Jordan Lee");
  await page.getByRole("button", { name: "Shortlist" }).click();
  await expect(page.getByTestId("workflow-status")).toHaveText("SHORTLISTED");

  await page.goto("/");
  await page.getByRole("button", { name: "Jobs" }).click();
  await page.getByLabel("Active profile").selectOption({ label: "Jordan Lee" });
  const shortlisted = Number(await page.getByTestId("tile-Shortlisted").textContent());
  expect(shortlisted).toBeGreaterThanOrEqual(1);

  await page.getByRole("button", { name: "Shortlisted" }).click(); // sets the status filter
  await expect(page.getByText(`(${shortlisted} jobs)`)).toBeVisible();

  // The other profile has not shortlisted anything.
  await page.getByLabel("Active profile").selectOption({ label: "Morgan Rivera" });
  await expect(page.getByTestId("tile-Shortlisted")).toHaveText("0");
});
