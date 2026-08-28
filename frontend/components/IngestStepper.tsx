const STEPS = ["Clone", "Chunk", "Embed", "Store"] as const;

const STEP_KEYWORDS: Record<(typeof STEPS)[number], string[]> = {
  Clone: ["cloning"],
  Chunk: ["chunking", "chunked", "done chunking"],
  Embed: ["embedding"],
  Store: ["stored"],
};

/** Best-effort mapping of the latest progress line to a stepper stage.
 * -1 = not started, STEPS.length = all done. Mirrors app.py's logic exactly
 * so behavior is consistent between the Streamlit and Next.js UIs. */
export function currentStepIndex(latestMessage: string | null): number {
  if (!latestMessage) return -1;
  const lower = latestMessage.toLowerCase();
  for (let i = 0; i < STEPS.length; i++) {
    if (STEP_KEYWORDS[STEPS[i]].some((kw) => lower.includes(kw))) {
      return i;
    }
  }
  return -1;
}

export function IngestStepper({ currentIndex }: { currentIndex: number }) {
  return (
    <div className="flex gap-1.5 my-2">
      {STEPS.map((step, i) => {
        const done = i < currentIndex;
        const active = i === currentIndex;
        return (
          <div
            key={step}
            className="flex-1 text-center text-[0.68rem] font-semibold rounded-md px-1 py-1.5 transition-colors duration-300"
            style={{
              backgroundColor: done
                ? "var(--color-confidence-strong-bg)"
                : active
                  ? "var(--color-info-bg)"
                  : "color-mix(in srgb, var(--color-muted) 12%, transparent)",
              color: done
                ? "var(--color-confidence-strong)"
                : active
                  ? "var(--color-info)"
                  : "var(--color-muted)",
              opacity: done || active ? 1 : 0.55,
            }}
          >
            {step}
          </div>
        );
      })}
    </div>
  );
}
