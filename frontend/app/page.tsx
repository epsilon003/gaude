"use client";

import { useState, useEffect, useCallback } from "react";
import { listRepos, type RepoInfo } from "@/lib/api";
import { Sidebar } from "@/components/Sidebar";
import { ChatPanel } from "@/components/ChatPanel";
import { ThemeToggle } from "@/components/ThemeToggle";
import { LoadingScreen } from "@/components/LoadingScreen";
import { DeadScreen } from "@/components/DeadScreen";
import { Toast } from "@/components/Toast";
import { useToast } from "@/hooks/useToast";
import { shortRepoName } from "@/lib/repoName";

type ConnectionStatus = "checking" | "connected" | "unreachable";

export default function Home() {
  const [repos, setRepos] = useState<RepoInfo[]>([]);
  const [selectedCollection, setSelectedCollection] = useState<string | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>("checking");
  // On mobile the sidebar is a drawer rather than a stacked block that pushed
  // the entire chat below the fold.
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { toasts, showToast, removeToast } = useToast();

  const refreshRepos = useCallback(async (selectAfter?: string) => {
    try {
      const list = await listRepos();
      setRepos(list);
      setStatus("connected");
      if (selectAfter) {
        setSelectedCollection(selectAfter);
      } else {
        setSelectedCollection((prev) => prev ?? (list.length > 0 ? list[0].collection_name : null));
      }
    } catch {
      // Covers both "backend not running" (connection refused) and any
      // other failure to reach /api/repos — either way the app isn't
      // usable, so both surface as the same unreachable state.
      setStatus("unreachable");
    }
  }, []);

  useEffect(() => {
    refreshRepos();
  }, [refreshRepos]);

  // Close the mobile drawer on Escape, matching the backdrop click.
  useEffect(() => {
    if (!drawerOpen) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setDrawerOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  const selectedInfo = repos.find((r) => r.collection_name === selectedCollection);

  if (status === "checking") {
    return <LoadingScreen />;
  }

  if (status === "unreachable") {
    return <DeadScreen onRetry={() => { setStatus("checking"); refreshRepos(); }} />;
  }

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <header className="sticky top-0 z-10 border-b border-hairline px-4 md:px-8 py-4 flex items-center justify-between gap-3 bg-canvas/85 backdrop-blur-sm">
        <div className="flex items-center gap-2 min-w-0">
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open repositories panel"
            aria-expanded={drawerOpen}
            className="md:hidden shrink-0 p-1.5 -ml-1.5 rounded-lg text-ink hover:bg-card-hover transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M3 6h18M3 12h18M3 18h18" />
            </svg>
          </button>
          <div className="min-w-0">
            <h1 className="font-[family-name:var(--font-display)] text-[1.15rem] md:text-[1.5rem] font-bold text-ink leading-tight truncate">
              Grounded Q&amp;A for Internal Codebases
            </h1>
            {/* On mobile the sidebar is hidden, so the header carries which
                repo you're actually querying. */}
            {selectedInfo && (
              <p className="md:hidden text-xs text-muted truncate">
                {shortRepoName(selectedInfo.source_url, selectedInfo.collection_name)}
              </p>
            )}
          </div>
        </div>
        <ThemeToggle />
      </header>

      <div className="flex flex-1 min-h-0 flex-row">
        {/* Desktop: a normal column. */}
        <div className="hidden md:flex">
          <Sidebar
            repos={repos}
            selectedCollection={selectedCollection}
            onSelectCollection={setSelectedCollection}
            onIngestComplete={(name) => refreshRepos(name)}
            onNotify={showToast}
          />
        </div>

        {/* Mobile: an off-canvas drawer. */}
        {drawerOpen && (
          <div className="md:hidden fixed inset-0 z-30 flex">
            <div
              className="absolute inset-0 bg-black/40"
              onClick={() => setDrawerOpen(false)}
              aria-hidden="true"
            />
            <div
              role="dialog"
              aria-modal="true"
              aria-label="Repositories"
              className="relative w-[85%] max-w-sm h-full bg-card shadow-xl flex flex-col overflow-y-auto"
            >
              <div className="flex justify-end p-2">
                <button
                  type="button"
                  onClick={() => setDrawerOpen(false)}
                  aria-label="Close repositories panel"
                  className="p-1.5 rounded-lg text-ink hover:bg-card-hover transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
                >
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                    <path d="M18 6L6 18M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <Sidebar
                repos={repos}
                selectedCollection={selectedCollection}
                onSelectCollection={setSelectedCollection}
                onIngestComplete={(name) => refreshRepos(name)}
                onNotify={showToast}
                onAfterSelect={() => setDrawerOpen(false)}
              />
            </div>
          </div>
        )}

        <ChatPanel
          selectedCollection={selectedCollection}
          repoDisplayName={
            selectedInfo ? shortRepoName(selectedInfo.source_url, selectedInfo.collection_name) : null
          }
          hasRepos={repos.length > 0}
          onNotify={showToast}
        />
      </div>

      {/* Stacked in a fixed container: previously every toast rendered at the
          same bottom-4 right-4 coordinates and sat on top of each other. */}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 items-end pointer-events-none">
        {toasts.map((toast) => (
          <Toast
            key={toast.id}
            message={toast.message}
            type={toast.type}
            onClose={() => removeToast(toast.id)}
          />
        ))}
      </div>
    </div>
  );
}