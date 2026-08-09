import { expect, test } from "@playwright/test";

import {
  clarificationFixture,
  ids,
  projectFixture,
  runFixture,
  sessionFixture,
} from "../src/test/fixtures";

test("dark theme is available on sign-in and persists across reloads", async ({ page }) => {
  await page.goto("/sign-in");

  const toggle = page.getByRole("button", { name: "Switch to dark theme" });
  await expect(toggle).toBeVisible();
  await toggle.click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("body")).toHaveCSS("background-color", "rgb(12, 18, 32)");

  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByRole("button", { name: "Switch to light theme" })).toBeVisible();

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("planning launch uses readable dark-theme surfaces and text", async ({ page }) => {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    const responses = new Map<string, unknown>([
      ["/auth/session", sessionFixture],
      [`/projects/${ids.project}`, projectFixture],
      [`/projects/${ids.project}/planning-runs/active`, null],
      [
        "/system/capabilities",
        {
          planning_ai_configured: true,
          planning_provider: "test",
          planning_model: "test-model",
        },
      ],
    ]);
    if (responses.has(path)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(responses.get(path)),
      });
      return;
    }
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `Unhandled GET ${path}` }),
    });
  });

  await page.goto(`/projects/${ids.project}/planning`);
  await expect(
    page.getByRole("heading", { name: "Turn the project intake into an actionable plan" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Switch to dark theme" }).click();

  const launch = page.locator(".planning-launch");
  await expect(launch).toHaveCSS("background-color", "rgb(20, 29, 46)");
  await expect(launch.getByRole("heading", { level: 1 })).toHaveCSS(
    "color",
    "rgb(233, 238, 248)",
  );
  await expect(launch.locator(":scope > p")).toHaveCSS("color", "rgb(169, 181, 201)");

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("clarification action bar uses readable dark-theme surfaces and text", async ({ page }) => {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    const responses = new Map<string, unknown>([
      ["/auth/session", sessionFixture],
      [`/projects/${ids.project}`, projectFixture],
      [`/agent-runs/${ids.run}`, runFixture],
      [`/projects/${ids.project}/clarifications`, [clarificationFixture]],
    ]);
    if (responses.has(path)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(responses.get(path)),
      });
      return;
    }
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `Unhandled GET ${path}` }),
    });
  });

  await page.goto(`/projects/${ids.project}/clarify?run=${ids.run}`);
  await expect(page.getByRole("heading", { name: "Resolve planning questions" })).toBeVisible();
  await page.getByRole("button", { name: "Switch to dark theme" }).click();

  const actionBar = page.locator(".sticky-form-actions");
  await expect(actionBar).toHaveCSS("background-color", "rgb(25, 35, 56)");
  await expect(actionBar).toHaveCSS("border-color", "rgb(75, 92, 121)");
  await expect(actionBar.locator("strong")).toHaveCSS("color", "rgb(233, 238, 248)");
  await expect(actionBar.locator("span")).toHaveCSS("color", "rgb(169, 181, 201)");
  await expect(actionBar.getByRole("button", { name: "Save answers and resume" })).toHaveCSS(
    "color",
    "rgb(255, 255, 255)",
  );
});
