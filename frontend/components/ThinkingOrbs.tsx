/**
 * Shown in place of the assistant message bubble's content during the gap
 * between submitting a question and the first token arriving — covers
 * condensation (for follow-ups) + retrieval + reranking, which previously
 * had zero visual feedback in this UI (unlike the Streamlit version's
 * "Retrieving context..." spinner for the same phase).
 */
export function ThinkingOrbs() {
  return (
    <div className="flex items-center gap-1.5 py-1" role="status" aria-label="Thinking">
      <span className="thinking-orb w-2 h-2 rounded-full bg-accent" style={{ animationDelay: "0ms" }} />
      <span className="thinking-orb w-2 h-2 rounded-full bg-accent" style={{ animationDelay: "150ms" }} />
      <span className="thinking-orb w-2 h-2 rounded-full bg-accent" style={{ animationDelay: "300ms" }} />
    </div>
  );
}
