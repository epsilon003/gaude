"use client";

import { useState } from "react";
import { ProviderBadge, ConfidenceBadge, TimingBadge } from "./Badges";
import { CitationCard } from "./CitationCard";
import { ThinkingOrbs } from "./ThinkingOrbs";
import type { Citation } from "@/lib/api";

export interface DisplayMessage {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  citations?: Citation[];
  provider?: string | null;
  model?: string | null;
  confidence?: number;
  confidenceLabel?: string;
  resolvedQuestion?: string | null;
  retrievalSeconds?: number;
  error?: string | null;
}

export function ChatMessage({ message }: { message: DisplayMessage }) {
  const [sourcesOpen, setSourcesOpen] = useState(false);

  if (message.role === "user") {
    return (
      <div className="flex justify-end mb-3">
        <div className="elevated bg-navy text-white rounded-2xl rounded-br-sm px-4 py-2.5 max-w-[75%] text-sm">
          {message.content}
        </div>
      </div>
    );
  }

  const hasCitations = !!message.citations?.length;
  const isThinking = !!message.streaming && message.content.length === 0;

  return (
    <div className="flex justify-start mb-4">
      <div className="elevated bg-card border border-hairline rounded-2xl rounded-bl-sm px-4 py-3 max-w-[85%] text-sm transition-colors">
        {isThinking ? (
          <ThinkingOrbs />
        ) : (
          <div className="whitespace-pre-wrap leading-relaxed text-ink">
            {message.content}
            {message.streaming && (
              <span className="inline-block w-1.5 h-4 bg-ink/40 ml-0.5 align-middle animate-pulse" />
            )}
          </div>
        )}

        {message.error && <p className="text-confidence-weak text-xs mt-2">{message.error}</p>}

        {hasCitations && (
          <div className="mt-3 pt-3 border-t border-hairline">
            <div>
              {message.provider && message.model && (
                <ProviderBadge provider={message.provider} model={message.model} />
              )}
              {typeof message.retrievalSeconds === "number" && (
                <TimingBadge seconds={message.retrievalSeconds} />
              )}
              {message.confidenceLabel && <ConfidenceBadge label={message.confidenceLabel} />}
            </div>

            {message.resolvedQuestion && (
              <div className="text-muted text-xs italic mb-2">
                Interpreted as: &ldquo;{message.resolvedQuestion}&rdquo;
              </div>
            )}

            <button
              type="button"
              onClick={() => setSourcesOpen((o) => !o)}
              className="w-full flex items-center gap-1.5 text-muted text-xs hover:text-ink transition-colors py-1"
            >
              <svg
                width="10"
                height="10"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="3"
                className={`shrink-0 transition-transform duration-200 ${sourcesOpen ? "rotate-90" : ""}`}
              >
                <path d="M9 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Sources ({message.citations!.length})
            </button>

            {sourcesOpen && (
              <div className="mt-1.5">
                {message.citations!.map((c, i) => (
                  <CitationCard key={`${c.file_path}-${c.start_line}-${i}`} citation={c} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
