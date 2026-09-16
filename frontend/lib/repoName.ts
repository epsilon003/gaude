/**
 * Display helpers for repo identifiers.
 *
 * The sidebar used to show raw source URLs, which are mostly boilerplate
 * ("https://github.com/") with the part you actually scan for buried at the
 * end and truncated first when space runs out.
 */

/** "https://github.com/epsilon003/gaude" -> "epsilon003/gaude" */
export function shortRepoName(sourceUrl: string | null | undefined, fallback: string): string {
  if (!sourceUrl) return fallback;
  try {
    const url = new URL(sourceUrl);
    const parts = url.pathname.replace(/\.git$/, "").split("/").filter(Boolean);
    if (parts.length >= 2) return `${parts[parts.length - 2]}/${parts[parts.length - 1]}`;
    return parts[parts.length - 1] || fallback;
  } catch {
    // Not a parseable URL -- show whatever was stored rather than nothing.
    return sourceUrl || fallback;
  }
}