"use client";

import { useState } from "react";
import { ingestRepoStream, type RepoInfo } from "@/lib/api";
import { IngestStepper, currentStepIndex } from "./IngestStepper";

interface SidebarProps {
  repos: RepoInfo[];
  selectedCollection: string | null;
  onSelectCollection: (name: string) => void;
  onIngestComplete: (newCollectionName: string) => void;
}

export function Sidebar({
  repos,
  selectedCollection,
  onSelectCollection,
  onIngestComplete,
}: SidebarProps) {
  const [repoUrl, setRepoUrl] = useState("");
  const [ingesting, setIngesting] = useState(false);
  const [latestMessage, setLatestMessage] = useState<string | null>(null);
  const [statusText, setStatusText] = useState<string | null>(null);
  const [statusKind, setStatusKind] = useState<"info" | "success" | "error">("info");

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
          setStatusKind("success");
          setStatusText(`Ingested ${evt.summary.chunk_count} chunks in ${elapsed}s.`);
          setLatestMessage("stored"); // forces the stepper to its final "all done" state
          onIngestComplete(evt.summary.collection_name);
        } else if (evt.event === "error") {
          setStatusKind("error");
          setStatusText(`Ingestion failed: ${evt.message}`);
        }
      }
    } catch (err) {
      setStatusKind("error");
      setStatusText(`Ingestion failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIngesting(false);
    }
  }

  const stepIndex = ingesting
    ? currentStepIndex(latestMessage)
    : statusKind === "success"
      ? 4
      : -1;

  return (
    <aside className="w-full md:w-80 shrink-0 border-r border-hairline bg-card p-4 flex flex-col gap-4 overflow-y-auto transition-colors">
      <section className="bg-canvas border border-hairline rounded-xl p-3.5">
        <div className="text-[0.72rem] font-bold tracking-wider uppercase text-muted mb-2.5">
          Ingest a repository
        </div>
        <input
          type="text"
          value={repoUrl}
          onChange={(e) => setRepoUrl(e.target.value)}
          placeholder="https://github.com/owner/repo_name"
          disabled={ingesting}
          className="w-full bg-card text-ink placeholder:text-muted border border-hairline rounded-lg px-3 py-2 text-sm mb-2 focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:opacity-60 transition-shadow"
        />
        <button
          type="button"
          onClick={handleIngest}
          disabled={ingesting}
          className="w-full bg-navy text-white rounded-lg px-3 py-2 text-sm font-semibold hover:bg-navy-light disabled:opacity-50 transition-colors"
        >
          {ingesting ? "Ingesting..." : "Ingest repo"}
        </button>

        {(ingesting || statusText) && <IngestStepper currentIndex={stepIndex} />}
        {statusText && (
          <p
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
            <select
              value={selectedCollection ?? ""}
              onChange={(e) => onSelectCollection(e.target.value)}
              className="w-full bg-card text-ink border border-hairline rounded-lg px-3 py-2 text-sm mb-2"
            >
              {repos.map((r) => (
                <option key={r.name} value={r.name}>
                  {r.display_name}
                </option>
              ))}
            </select>
            {selectedCollection &&
              (() => {
                const info = repos.find((r) => r.name === selectedCollection);
                if (!info) return null;
                return (
                  <div className="bg-card border border-hairline rounded-[10px] px-3 py-2 text-sm">
                    <div className="font-semibold text-ink">{info.display_name}</div>
                    <div className="text-xs text-muted mt-0.5">{info.chunk_count} chunks indexed</div>
                  </div>
                );
              })()}
          </>
        )}
      </section>
    </aside>
  );
}
