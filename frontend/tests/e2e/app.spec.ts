import { test, expect } from "@playwright/test";

/**
 * These tests exercise app/page.tsx's connection-status state machine
 * (checking -> connected / unreachable) by mocking the backend's
 * GET /api/repos call -- the one request the page makes before it decides
 * which screen to show. No live FastAPI backend is required.
 */

test.describe("backend unreachable", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/repos", (route) => route.abort("connectionrefused"));
  });

  test("shows the dead-server screen with a working retry button", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("heading", { name: /can.t reach the server/i })).toBeVisible();
    await expect(page.getByText(/localhost:8000/)).toBeVisible();

    const retryButton = page.getByRole("button", { name: /retry/i });
    await expect(retryButton).toBeVisible();

    // Retry should re-fire the same (still-failing) request rather than
    // silently doing nothing -- assert the request actually happens again.
    const retryRequest = page.waitForRequest("**/api/repos");
    await retryButton.click();
    await retryRequest;

    // Still unreachable since the route is still mocked to abort.
    await expect(page.getByRole("heading", { name: /can.t reach the server/i })).toBeVisible();
  });
});

test.describe("backend reachable", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/repos", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            collection_name: "https-github-com-epsilon003-gaude",
            source_url: "https://github.com/epsilon003/gaude",
            commit_sha: "abc1234",
            chunk_count: 128,
          },
        ]),
      })
    );
  });

  test("renders the main chat UI once repos load", async ({ page }) => {
    await page.goto("/");

    await expect(
      page.getByRole("heading", { name: /grounded q&a for internal codebases/i })
    ).toBeVisible();

    // The dead-server screen should not be showing when the backend responds.
    await expect(page.getByRole("heading", { name: /can.t reach the server/i })).not.toBeVisible();

    // The ingested repo should be selectable in the sidebar, shown as
    // owner/repo. Scoped to the repo-picker button specifically -- the
    // mobile header and the empty-state heading also render this text
    // (hidden responsively via CSS, not removed from the DOM), so a plain
    // getByText matches three elements and trips Playwright's strict mode.
    await expect(page.getByRole("button", { name: /epsilon003\/gaude/ })).toBeVisible();
  });

  test("has no unhandled console errors on initial load", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));

    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: /grounded q&a for internal codebases/i })
    ).toBeVisible();

    expect(errors).toEqual([]);
  });
});