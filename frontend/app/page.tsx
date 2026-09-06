"use client";

import { useState, useEffect, useCallback } from "react";
import { listRepos, type RepoInfo } from "@/lib/api";
import { Sidebar } from "@/components/Sidebar";
import { ChatPanel } from "@/components/ChatPanel";
import { ThemeToggle } from "@/components/ThemeToggle";
import { LoadingScreen } from "@/components/LoadingScreen";
import { DeadScreen } from "@/components/DeadScreen";

type ConnectionStatus = "checking" | "connected" | "unreachable";

export default function Home() {
  const [repos, setRepos] = useState<RepoInfo[]>([]);
  const [selectedCollection, setSelectedCollection] = useState<string | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>("checking");

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

  const selectedInfo = repos.find((r) => r.collection_name === selectedCollection);

  if (status === "checking") {
    return <LoadingScreen />;
  }

  if (status === "unreachable") {
    return <DeadScreen onRetry={() => { setStatus("checking"); refreshRepos(); }} />;
  }

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <header className="sticky top-0 z-10 border-b border-hairline px-4 md:px-8 py-4 flex items-center justify-between gap-4 bg-canvas/85 backdrop-blur-sm">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-[1.5rem] font-bold text-ink leading-tight">
            Grounded Q&A for Internal Codebases
          </h1>
          <p className="text-sm text-muted mt-0.5">
            Ask natural-language questions about a GitHub repo. Answers are grounded in
            retrieved code/doc chunks with file + line citations — free-tier stack only.
          </p>
        </div>
        <ThemeToggle />
      </header>
      <div className="flex flex-1 min-h-0 flex-col md:flex-row">
        <Sidebar
          repos={repos}
          selectedCollection={selectedCollection}
          onSelectCollection={setSelectedCollection}
          onIngestComplete={(name) => refreshRepos(name)}
        />
        <ChatPanel
          selectedCollection={selectedCollection}
          repoDisplayName={selectedInfo?.source_url ?? null}
          hasRepos={repos.length > 0}
        />
      </div>
    </div>
  );
}