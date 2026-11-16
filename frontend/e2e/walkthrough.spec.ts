import { expect, test, type Page } from "@playwright/test";

// The "public v1 success criteria" (plan section 42), steps 3-12, as one stranger-style walkthrough
// against a freshly started, seeded stack. Run with SCREENSHOTS=1 to refresh docs/screenshots.

const SHOTS = process.env.SCREENSHOTS === "1";
const shot = async (page: Page, name: string) => {
  if (SHOTS) await page.screenshot({ path: `../docs/screenshots/${name}.png`, fullPage: true });
};

test("a stranger can follow the section 42 steps", async ({ page }) => {
  test.setTimeout(90_000);
  // 3. open the application (demo banner shows)
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "CareerFlow" })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("Demo mode");

  // 4. switch between two fictional profiles
  await page.getByRole("button", { name: "Jordan Lee" }).click();
  await expect(page.getByRole("heading", { name: "Jordan Lee" })).toBeVisible();
  await shot(page, "01-profile-editor");
  await page.getByRole("button", { name: "Morgan Rivera" }).click();
  await expect(page.getByRole("heading", { name: "Morgan Rivera" })).toBeVisible();
  await page.getByRole("button", { name: "Jordan Lee" }).click();

  // 5. view sample jobs, with dashboard counts
  await page.getByRole("button", { name: "Jobs" }).click();
  await expect(page.getByRole("link", { name: "Principal AI Platform Engineer" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Senior Data Scientist, Forecasting" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await shot(page, "02-job-inbox");

  // 6-7. the same job is evaluated differently per profile, and the reasons are visible
  await page.getByRole("link", { name: "Principal AI Platform Engineer" }).click();
  const rows = page.locator("table tbody tr");
  await expect(rows).toHaveCount(2);
  const score = async (name: string) => Number((await rows.filter({ hasText: name }).locator("td:nth-child(2)").innerText()).replace("%", ""));
  expect(await score("Jordan Lee")).toBeGreaterThan((await score("Morgan Rivera")) + 20);
  await expect(page.getByText(/Strong role alignment|Seniority matches/).first()).toBeVisible();
  await expect(page.getByText(/Unknown \(not scored\)/)).toBeVisible();
  await shot(page, "03-evaluation-comparison");

  // 8-9. manually import another job and see it evaluated
  await page.goto("/");
  await page.getByRole("button", { name: "Jobs" }).click();
  const title = `Staff Platform Engineer ${Date.now()}`;
  await page.getByLabel("Title").fill(title);
  await page.getByLabel("Company").fill("Walkthrough Co");
  await page.getByLabel("Work arrangement").selectOption("REMOTE");
  await page.getByLabel("Description").fill("Build LLM platforms with Python and Azure; lead distributed systems work.");
  await page.getByRole("button", { name: "Import job" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await page.getByLabel("Active profile").selectOption({ label: "Jordan Lee" });
  await expect(page.getByText(/Overall score:|Evaluate/).first()).toBeVisible();

  // 10. shortlist it
  await page.getByRole("button", { name: "Shortlist" }).click();
  await expect(page.getByTestId("workflow-status")).toHaveText("SHORTLISTED");

  // 11. prepare an application package (nothing is saved until approved)
  await page.getByRole("button", { name: "Prepare application" }).click();
  await expect(page.getByRole("button", { name: "Approve and save" })).toBeVisible();
  await shot(page, "04-application-preparation");
  await page.getByRole("button", { name: "Approve and save" }).click();
  await expect(page.getByRole("button", { name: "Approved and saved" })).toBeDisabled();

  // 12. move it through the application pipeline with validated transitions
  await page.goto("/");
  await page.getByRole("button", { name: "Pipeline" }).click();
  await page.getByLabel("Profile").selectOption({ label: "Jordan Lee" });
  for (const next of ["PREPARING", "READY_TO_APPLY", "APPLIED"]) {
    await page.getByLabel(`Move ${title}`).selectOption(next);
    await expect(page.getByLabel(`${next} column`)).toContainText(title);
  }
  await page.getByLabel(`Move ${title}`).selectOption("OFFER"); // not an allowed move from APPLIED
  await expect(page.getByRole("alert")).toContainText("not allowed");
  await expect(page.getByLabel("APPLIED column")).toContainText(title);
  await shot(page, "05-pipeline");

  // AI is optional: settings explain it and the app works with it off
  await page.getByRole("button", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "AI provider" })).toBeVisible();
  await shot(page, "06-ai-settings");
});
