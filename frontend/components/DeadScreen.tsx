export function DeadScreen({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-canvas px-6 text-center">
      <svg
        width="40"
        height="40"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        className="text-muted mb-4"
      >
        <circle cx="12" cy="12" r="9" />
        <path d="M9 9l6 6M15 9l-6 6" strokeLinecap="round" />
      </svg>
      <h1 className="font-[family-name:var(--font-display)] text-xl font-bold text-ink mb-2">
        Can&rsquo;t reach the server
      </h1>
      <p className="text-sm text-muted max-w-sm leading-relaxed mb-6">
        The backend at <code className="font-mono text-xs bg-card border border-hairline rounded px-1.5 py-0.5">localhost:8000</code> isn&rsquo;t
        responding. Make sure it&rsquo;s running — <code className="font-mono text-xs bg-card border border-hairline rounded px-1.5 py-0.5">uvicorn api.main:app --reload --port 8000</code> from
        the project root — then try again.
      </p>
      <button
        type="button"
        onClick={onRetry}
        className="bg-navy text-white rounded-lg px-4 py-2 text-sm font-semibold hover:bg-navy-light transition-colors"
      >
        Retry
      </button>
    </div>
  );
}
