"use client";

import { useState, useEffect, useCallback } from "react";
import { listRepos, type RepoInfo } from "@/lib/api";
import { Sidebar } from "@/components/Sidebar";
import { ChatPanel } from "@/components/ChatPanel";

export default function Home() {
  const [repos, setRepos] = useState<RepoInfo[]>([]);
  const [selectedCollection, setSelectedCollection] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const refreshRepos = useCallback(async (selectAfter?: string) => {
    try {
      const list = await listRepos();
      setRepos(list);
      if (selectAfter) {
        setSelectedCollection(selectAfter);
      } else if (!selectedCollection && list.length > 0) {
        setSelectedCollection(list[0].name);
      }
    } catch {
      // Backend not reachable yet (e.g. still starting up) — leave repos
      // empty, the empty-state UI handles this gracefully either way.
    } finally {
      setLoaded(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    refreshRepos();
  }, [refreshRepos]);

  const selectedInfo = repos.find((r) => r.name === selectedCollection);

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <header className="border-b border-hairline px-4 md:px-8 py-4">
        <h1 className="font-[family-name:var(--font-display)] text-[1.5rem] font-bold text-ink">
          Grounded Q&A for Internal Codebases
        </h1>
        <p className="text-sm text-muted mt-0.5">
          Ask natural-language questions about a GitHub repo. Answers are grounded in
          retrieved code/doc chunks with file + line citations — free-tier stack only.
        </p>
      </header>

      <div className="flex flex-1 min-h-0 flex-col md:flex-row">
        <Sidebar
          repos={repos}
          selectedCollection={selectedCollection}
          onSelectCollection={setSelectedCollection}
          onIngestComplete={(name) => refreshRepos(name)}
        />
        {loaded && (
          <ChatPanel
            selectedCollection={selectedCollection}
            repoDisplayName={selectedInfo?.display_name ?? null}
            hasRepos={repos.length > 0}
          />
        )}
      </div>
    </div>
  );
}
