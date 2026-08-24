"use client";

import { useState } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import type { Citation } from "@/lib/api";

// Mirrors app.py's _LANGUAGE_MAP so citation previews highlight the same way
// the Streamlit UI does.
const LANGUAGE_MAP: Record<string, string> = {
  ".py": "python",
  ".js": "javascript",
  ".jsx": "javascript",
  ".mjs": "javascript",
  ".ts": "typescript",
  ".tsx": "typescript",
  ".java": "java",
  ".go": "go",
  ".rb": "ruby",
  ".php": "php",
  ".cpp": "cpp",
  ".cc": "cpp",
  ".c": "c",
  ".h": "c",
  ".hpp": "cpp",
  ".cs": "csharp",
  ".rs": "rust",
  ".kt": "kotlin",
  ".scala": "scala",
  ".swift": "swift",
  ".md": "markdown",
  ".html": "markup",
  ".htm": "markup",
  ".json": "json",
  ".yaml": "yaml",
  ".yml": "yaml",
  ".sh": "bash",
  ".sql": "sql",
  ".toml": "toml",
};

function guessLanguage(filePath: string): string {
  const match = filePath.match(/\.[^./]+$/);
  const ext = match ? match[0].toLowerCase() : "";
  return LANGUAGE_MAP[ext] ?? "text";
}

export function CitationCard({ citation }: { citation: Citation }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-hairline rounded-lg mb-1.5 overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-center justify-between px-3 py-2 text-left text-sm hover:bg-canvas transition-colors"
      >
        <span className="font-mono text-ink">
          {citation.file_path}:{citation.start_line}-{citation.end_line}
        </span>
        <span className="text-muted text-xs ml-3 shrink-0">
          relevance {citation.rerank_score.toFixed(2)}
        </span>
      </button>
      {expanded && (
        <div className="border-t border-hairline px-3 py-2">
          {citation.github_url && (
            <a
              href={citation.github_url}
              target="_blank"
              rel="noreferrer"
              className="inline-block text-xs text-accent hover:underline mb-2"
            >
              View on GitHub
            </a>
          )}
          <SyntaxHighlighter
            language={guessLanguage(citation.file_path)}
            style={oneLight}
            customStyle={{ margin: 0, borderRadius: "0.375rem", fontSize: "0.8rem" }}
          >
            {citation.text || "(no preview available)"}
          </SyntaxHighlighter>
        </div>
      )}
    </div>
  );
}
