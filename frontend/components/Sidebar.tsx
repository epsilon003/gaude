"use client";

import { useState } from "react";
import { ingestRepoStream, type RepoInfo } from "@/lib/api";
import { IngestStepper, currentStepIndex } from "./IngestStepper";
import { shortRepoName } from "@/lib/repoName";

interface SidebarProps {
  repos: RepoInfo[];
  selectedCollection: string | null;
  onSelectCollection: (name: string) => void;
  onIngestComplete: (newCollectionName: string) => void;
  onNotify?: (message: string, type: "success" | "error" | "info") => void;
  /** Mobile only: lets the drawer close itself after a repo is picked. */
  onAfterSelect?: () => void;
}

export function Sidebar({
  repos,
  selectedCollection,
  onSelectCollection,
  onIngestComplete,
  onNotify,
  onAfterSelect,
}: SidebarProps) {
  const [repoUrl, setRepoUrl] = useState("");
  const [ingesting, setIngesting] = useState(false);
  const [latestMessage, setLatestMessage] = useState<string | null>(null);
  const [statusText, setStatusText] = useState<string | null>(null);
  const [statusKind, setStatusKind] = useState<"info" | "success" | "error">("info");
  const [filter, setFilter] = useState("");

  async function handleIngest() {
    const url = repoUrl.trim();
    if (!url) {
      setStatusKind("error");
      setStatusText("Enter a repo URL first.");
      return;
    }

    setIngesting(true);
    setStatusKind("info");
    setStatusText("Starting...");
    setLatestMessage(null);

    const start = performance.now();
    try {
      for await (const evt of ingestRepoStream(url)) {
        if (evt.event === "progress") {
          setLatestMessage(evt.message);
          setStatusText(evt.message);
        } else if (evt.event === "done") {
          const elapsed = ((performance.now() - start) / 1000).toFixed(1);
          const summary = `Ingested ${evt.summary.chunk_count} chunks in ${elapsed}s.`;
          setStatusKind("success");
          setStatusText(summary);
          setLatestMessage("stored"); // forces the stepper to its final "all done" state
          onIngestComplete(evt.summary.collection_name);
          onNotify?.(summary, "success");
        } else if (evt.event === "error") {
          setStatusKind("error");
          setStatusText(`Ingestion failed: ${evt.message}`);
          // Ingestion can take minutes, by which point the user is usually
          // looking elsewhere -- a toast is what actually gets noticed.
          onNotify?.(`Ingestion failed: ${evt.message}`, "error");
        }
      }
    } catch (err) {
      const text = `Ingestion failed: ${err instanceof Error ? err.message : String(err)}`;
      setStatusKind("error");
      setStatusText(text);
      onNotify?.(text, "error");
    } finally {
      setIngesting(false);
    }
  }

  const stepIndex = ingesting
    ? currentStepIndex(latestMessage)
    : statusKind === "success"
    ? 4
    : -1;

  // A <select> stops being usable somewhere around a dozen entries and can't
  // be filtered; a filterable list scales and shows chunk counts inline.
  const visibleRepos = repos.filter((r) => {
    if (!filter.trim()) return true;
    const haystack = `${r.source_url ?? ""} ${r.collection_name}`.toLowerCase();
    return haystack.includes(filter.trim().toLowerCase());
  });

  return (
    <aside className="w-full md:w-80 shrink-0 md:border-r border-hairline bg-card p-4 flex flex-col gap-4 overflow-y-auto transition-colors">
      <section className="bg-canvas border border-hairline rounded-xl p-3.5">
        <div className="text-[0.72rem] font-bold tracking-wider uppercase text-muted mb-2.5">
          Ingest a repository
        </div>
        <label htmlFor="repo-url" className="sr-only">
          Public GitHub repository URL
        </label>
        <input
          id="repo-url"
          type="text"
          value={repoUrl}
          onChange={(e) => setRepoUrl(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !ingesting) handleIngest();
          }}
          placeholder="https://github.com/owner/repo_name"
          disabled={ingesting}
          className="w-full bg-card text-ink placeholder:text-muted border border-hairline rounded-lg px-3 py-2 text-sm mb-2 focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:opacity-60 transition-shadow"
        />
        <button
          type="button"
          onClick={handleIngest}
          disabled={ingesting}
          className="w-full bg-navy text-white rounded-lg px-3 py-2 text-sm font-semibold hover:bg-navy-light disabled:opacity-50 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
        >
          {ingesting ? "Ingesting..." : "Ingest repo"}
        </button>
        {(ingesting || statusText) && <IngestStepper currentIndex={stepIndex} />}
        {statusText && (
          <p
            aria-live="polite"
            className={
              "text-xs mt-1 " +
              (statusKind === "error"
                ? "text-confidence-weak"
                : statusKind === "success"
                ? "text-confidence-strong"
                : "text-muted")
            }
          >
            {statusText}
          </p>
        )}
      </section>

      <section className="bg-canvas border border-hairline rounded-xl p-3.5">
        <div className="text-[0.72rem] font-bold tracking-wider uppercase text-muted mb-2.5">
          Choose repo to query
        </div>
        {repos.length === 0 ? (
          <p className="text-xs text-muted">No repos ingested yet — add one above to get started.</p>
        ) : (
          <>
            {repos.length > 5 && (
              <>
                <label htmlFor="repo-filter" className="sr-only">
                  Filter repositories
                </label>
                <input
                  id="repo-filter"
                  type="text"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  placeholder="Filter repos..."
                  className="w-full bg-card text-ink placeholder:text-muted border border-hairline rounded-lg px-3 py-1.5 text-xs mb-2 focus:outline-none focus:ring-2 focus:ring-accent/40"
                />
              </>
            )}
            <ul className="flex flex-col gap-1" role="list">
              {visibleRepos.map((r) => {
                const isSelected = r.collection_name === selectedCollection;
                return (
                  <li key={r.collection_name}>
                    <button
                      type="button"
                      onClick={() => {
                        onSelectCollection(r.collection_name);
                        onAfterSelect?.();
                      }}
                      aria-current={isSelected ? "true" : undefined}
                      title={r.source_url || r.collection_name}
                      className={
                        "w-full text-left rounded-[10px] px-3 py-2 border transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 " +
                        (isSelected
                          ? "bg-card border-accent/50"
                          : "bg-card/50 border-hairline hover:bg-card-hover")
                      }
                    >
                      <div
                        className={
                          "text-sm truncate " +
                          (isSelected ? "font-semibold text-ink" : "text-ink/85")
                        }
                      >
                        {shortRepoName(r.source_url, r.collection_name)}
                      </div>
                      <div className="text-xs text-muted mt-0.5">
                        {r.chunk_count} chunks indexed
                      </div>
                    </button>
                  </li>
                );
              })}
              {visibleRepos.length === 0 && (
                <li className="text-xs text-muted py-1">No repos match that filter.</li>
              )}
            </ul>
          </>
        )}
      </section>
    </aside>
  );
}