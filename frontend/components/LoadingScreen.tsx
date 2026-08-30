export function LoadingScreen() {
  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-canvas px-6">
      <p className="font-[family-name:var(--font-display)] text-ink text-xl md:text-2xl text-center italic leading-relaxed whitespace-nowrap">
        &ldquo;AND GAUDE SAID, LET NEWTON BE! AND ALL WAS LIGHT&rdquo;
      </p>
      <div className="flex items-center gap-1.5 mt-8">
        <span className="thinking-orb w-2 h-2 rounded-full bg-accent" style={{ animationDelay: "0ms" }} />
        <span className="thinking-orb w-2 h-2 rounded-full bg-accent" style={{ animationDelay: "150ms" }} />
        <span className="thinking-orb w-2 h-2 rounded-full bg-accent" style={{ animationDelay: "300ms" }} />
      </div>
    </div>
  );
}
