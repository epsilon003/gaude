"use client";
import { useEffect, useState } from "react";

const PHRASES = [
  "Thinking",
  "Searching the codebase",
  "Scanning relevant files",
  "Analyzing the request",
  "Understanding context",
  "Finding relevant code",
  "Tracing dependencies",
  "Inspecting project structure",
  "Reading through the code",
  "Connecting the dots",
  "Reranking results",
  "Filtering relevant results",
  "Cross-checking findings",
  "Validating assumptions",
  "Comparing approaches",
  "Checking edge cases",
  "Reviewing implementation details",
  "Formulating a solution",
  "Drafting an answer",
  "Polishing the response",
  "Putting it all together"
];
const PHRASE_INTERVAL_MS = 2000;

/**
 * Shown in place of the assistant message bubble's content during the gap
 * between submitting a question and the first token arriving — covers
 * condensation (for follow-ups) + retrieval + reranking, which previously
 * had zero visual feedback in this UI.
 */
export function ThinkingOrbs() {
  const [phraseIndex, setPhraseIndex] = useState(0);

  useEffect(() => {
    const id = setInterval(() => {
      setPhraseIndex((i) => (i + 1) % PHRASES.length);
    }, PHRASE_INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="flex items-center gap-2 py-0.5" role="status" aria-label="Thinking">
      <div className="flex items-center gap-1">
        <span className="thinking-orb w-1.5 h-1.5 rounded-full bg-accent" style={{ animationDelay: "0ms" }} />
        <span className="thinking-orb w-1.5 h-1.5 rounded-full bg-accent" style={{ animationDelay: "150ms" }} />
        <span className="thinking-orb w-1.5 h-1.5 rounded-full bg-accent" style={{ animationDelay: "300ms" }} />
      </div>
      <span className="text-xs text-muted">{PHRASES[phraseIndex]}&hellip;</span>
    </div>
  );
}
