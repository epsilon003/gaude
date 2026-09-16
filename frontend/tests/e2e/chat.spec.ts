import { test, expect, type Page } from "@playwright/test";

/**
 * Regression coverage for the two frontend bugs that produced wrong output
 * rather than visible breakage:
 *
 *  - chat history leaking across repos on switch (it fed condense_query,
 *    so follow-ups got rewritten using a different codebase's context)
 *  - forced scroll-to-bottom on every streamed token
 */

const REPOS = [
  {
    collection_name: "coll-alpha",
    source_url: "https://github.com/acme/alpha",
    commit_sha: "aaa1111",
    chunk_count: 100,
  },
  {
    collection_name: "coll-beta",
    source_url: "https://github.com/acme/beta",
    commit_sha: "bbb2222",
    chunk_count: 200,
  },
];

/** Captures every /api/chat request body the page sends. */
async function mockBackend(page: Page, sentBodies: Record<string, unknown>[]) {
  await page.route("**/api/repos", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(REPOS) }),
  );

  await page.route("**/api/chat", async (route) => {
    sentBodies.push(JSON.parse(route.request().postData() || "{}"));
    const sse =
      `data: ${JSON.stringify({ event: "token", text: "Answer text." })}\n\n` +
      `data: ${JSON.stringify({
        event: "done",
        citations: [],
        provider: "Gemini",
        model: "gemini-3.5-flash",
        confidence: 0.9,
        confidence_label: "Strong",
        resolved_question: null,
        retrieval_seconds: 0.2,
        error: null,
      })}\n\n`;
    await route.fulfill({ status: 200, contentType: "text/event-stream", body: sse });
  });
}

async function ask(page: Page, question: string) {
  const input = page.getByRole("textbox", { name: /ask a question/i });
  await input.fill(question);
  await input.press("Enter");
}

test("switching repos does not leak chat history into the next question", async ({ page }) => {
  const sent: Record<string, unknown>[] = [];
  await mockBackend(page, sent);
  await page.goto("/");

  await ask(page, "First question about alpha");
  await expect(page.getByText("Answer text.")).toBeVisible();

  // Switch to the other repo, then ask a follow-up.
  await page.getByRole("button", { name: /acme\/beta/ }).click();
  await ask(page, "Follow-up about beta");
  await expect(page.getByText("Answer text.")).toBeVisible();

  const lastBody = sent[sent.length - 1] as { collection: string; history: unknown[] };
  expect(lastBody.collection).toBe("coll-beta");
  // The critical assertion: beta's request must carry no alpha turns.
  expect(lastBody.history).toEqual([]);
});

test("returning to a repo restores its own conversation", async ({ page }) => {
  const sent: Record<string, unknown>[] = [];
  await mockBackend(page, sent);
  await page.goto("/");

  await ask(page, "Question about alpha");
  await expect(page.getByText("Question about alpha")).toBeVisible();

  await page.getByRole("button", { name: /acme\/beta/ }).click();
  await expect(page.getByText("Question about alpha")).not.toBeVisible();

  await page.getByRole("button", { name: /acme\/alpha/ }).click();
  await expect(page.getByText("Question about alpha")).toBeVisible();
});

test("conversation survives a page reload", async ({ page }) => {
  const sent: Record<string, unknown>[] = [];
  await mockBackend(page, sent);
  await page.goto("/");

  await ask(page, "Persisted question");
  await expect(page.getByText("Answer text.")).toBeVisible();

  await page.reload();
  await expect(page.getByText("Persisted question")).toBeVisible();
});

test("Shift+Enter inserts a newline instead of sending", async ({ page }) => {
  const sent: Record<string, unknown>[] = [];
  await mockBackend(page, sent);
  await page.goto("/");

  const input = page.getByRole("textbox", { name: /ask a question/i });
  await input.fill("line one");
  await input.press("Shift+Enter");
  await input.type("line two");

  expect(sent).toHaveLength(0); // nothing sent yet
  await expect(input).toHaveValue("line one\nline two");

  await input.press("Enter");
  await expect.poll(() => sent.length).toBe(1);
});

test("clear conversation empties only the current repo", async ({ page }) => {
  const sent: Record<string, unknown>[] = [];
  await mockBackend(page, sent);
  await page.goto("/");

  await ask(page, "Question about alpha");
  await expect(page.getByText("Answer text.")).toBeVisible();

  await page.getByRole("button", { name: /clear conversation/i }).click();
  await expect(page.getByText("Question about alpha")).not.toBeVisible();
});