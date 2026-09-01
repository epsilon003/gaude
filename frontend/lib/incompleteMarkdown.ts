/**
 * Auto-closes unclosed inline markdown syntax so mid-stream tokens don't
 * render as literal asterisks/backticks (e.g. "this is **bold" showing the
 * raw "**" instead of starting bold text). Only applied while a message is
 * actively streaming — finished messages render their real content as-is.
 *
 * Deliberately does NOT touch code fences (```): remark already treats an
 * unclosed fence as an open code block through end-of-input, which is
 * exactly the correct visual behavior while a code block is still
 * streaming in (it renders as code and keeps growing, rather than being
 * hidden until the closing fence arrives).
 *
 * Also deliberately does NOT touch single `*`/`_` (italic) — too easy to
 * false-positive on ordinary text like "3 * 4" or code containing
 * underscores, and bold/code/strikethrough cover the cases that look most
 * visibly broken mid-stream.
 */

function countOccurrences(text: string, token: string): number {
  let count = 0;
  let idx = 0;
  while ((idx = text.indexOf(token, idx)) !== -1) {
    count++;
    idx += token.length;
  }
  return count;
}

function isInsideCodeFence(text: string): boolean {
  return countOccurrences(text, "```") % 2 === 1;
}

function closeIfUnclosed(text: string, marker: string): string {
  if (isInsideCodeFence(text)) return text;

  const count = countOccurrences(text, marker);
  if (count % 2 !== 1) return text;

  // Only close if there's real (non-whitespace) content after the last
  // marker — avoids turning a bare trailing "**" into "****" with nothing
  // between them.
  const lastIdx = text.lastIndexOf(marker);
  const after = text.slice(lastIdx + marker.length);
  if (after.trim().length === 0) return text;

  return text + marker;
}

export function completeIncompleteMarkdown(text: string): string {
  let result = text;
  // Order matters: check longer/more-specific markers first so "***" isn't
  // miscounted as one "*" plus one "**".
  result = closeIfUnclosed(result, "***");
  result = closeIfUnclosed(result, "**");
  result = closeIfUnclosed(result, "~~");
  result = closeIfUnclosed(result, "`");
  return result;
}
