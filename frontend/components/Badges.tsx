const CONFIDENCE_STYLES: Record<string, { color: string; bg: string }> = {
  Strong: { color: "var(--color-confidence-strong)", bg: "var(--color-confidence-strong-bg)" },
  Moderate: { color: "var(--color-confidence-moderate)", bg: "var(--color-confidence-moderate-bg)" },
  Weak: { color: "var(--color-confidence-weak)", bg: "var(--color-confidence-weak-bg)" },
  None: { color: "var(--color-muted)", bg: "color-mix(in srgb, var(--color-muted) 15%, transparent)" },
};

function BadgeBase({
  children,
  color,
  bg,
}: {
  children: React.ReactNode;
  color: string;
  bg: string;
}) {
  return (
    <span
      className="inline-block rounded-full px-2.5 py-0.5 mr-1.5 mb-1.5 text-xs font-semibold"
      style={{ color, backgroundColor: bg }}
    >
      {children}
    </span>
  );
}

export function ProviderBadge({ provider, model }: { provider: string; model: string }) {
  return (
    <BadgeBase color="var(--color-confidence-strong)" bg="var(--color-confidence-strong-bg)">
      {provider} · {model}
    </BadgeBase>
  );
}

export function TimingBadge({ seconds }: { seconds: number }) {
  if (!seconds) return null;
  return (
    <BadgeBase color="var(--color-muted)" bg="color-mix(in srgb, var(--color-muted) 15%, transparent)">
      Retrieved in {seconds.toFixed(2)}s
    </BadgeBase>
  );
}

export function ConfidenceBadge({ label }: { label: string }) {
  if (label === "N/A") return null;
  const style = CONFIDENCE_STYLES[label] ?? CONFIDENCE_STYLES.None;
  return (
    <BadgeBase color={style.color} bg={style.bg}>
      Grounding: {label}
    </BadgeBase>
  );
}
