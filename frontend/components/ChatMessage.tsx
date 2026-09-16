"use client";

import { useState } from "react";
import { ProviderBadge, ConfidenceBadge, TimingBadge } from "./Badges";
import { CitationCard } from "./CitationCard";
import { ThinkingOrbs } from "./ThinkingOrbs";
import { CopyButton } from "./CopyButton";
import { MarkdownMessage } from "./MarkdownMessage";
import type { Citation } from "@/lib/api";

export interface DisplayMessage {
  /** Stable identity for React keys. Index keys broke reconciliation when
   *  retry rewrote the tail of the array via slice(). Optional so older
   *  persisted sessions without ids still render. */
  id?: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  stopped?: boolean;
  citations?: Citation[];
  provider?: string | null;
  model?: string | null;
  confidence?: number;
  confidenceLabel?: string;
  resolvedQuestion?: string | null;
  retrievalSeconds?: number;
  error?: string | null;
}

interface ChatMessageProps {
  message: DisplayMessage;
  onRetry?: () => void;
}

export function ChatMessage({ message, onRetry }: ChatMessageProps) {
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
  const distinctFiles = Array.from(new Set((message.citations ?? []).map((c) => c.file_path)));
  const isThinking = !!message.streaming && message.content.length === 0;
  const showCopy = !message.streaming && message.content.length > 0;

  return (
    <div className="flex justify-start mb-4 group/message">
      <div className="elevated bg-card border border-hairline rounded-2xl rounded-bl-sm px-4 py-3 max-w-[85%] text-sm transition-colors">
        {isThinking ? (
          <ThinkingOrbs />
        ) : (
          <MarkdownMessage content={message.content} streaming={message.streaming} />
        )}

        {message.streaming && !isThinking && (
          <span className="inline-block w-1.5 h-4 bg-ink/40 ml-0.5 align-middle animate-pulse" />
        )}

        {message.stopped && (
          <p className="text-muted text-xs mt-2 italic">Generation stopped.</p>
        )}

        {message.error && (
          <div className="mt-2 flex items-center gap-2">
            <p className="text-confidence-weak text-xs">{message.error}</p>
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="text-xs font-semibold text-accent hover:underline shrink-0 rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
              >
                Retry
              </button>
            )}
          </div>
        )}

        {showCopy && (
          <div className="mt-1.5 opacity-0 group-hover/message:opacity-100 transition-opacity">
            <CopyButton text={message.content} />
          </div>
        )}

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

            {/* The grounding is the product here -- previously you had to
                expand Sources and then expand each citation individually just
                to learn which files an answer rested on. This surfaces the
                distinct files at a glance. */}
            <div className="flex flex-wrap gap-1 mb-1.5">
              {distinctFiles.map((f) => (
                <span
                  key={f}
                  title={f}
                  className="font-mono text-[0.68rem] bg-canvas border border-hairline rounded px-1.5 py-0.5 text-muted max-w-[14rem] truncate"
                >
                  {f.split("/").pop()}
                </span>
              ))}
            </div>

            <button
              type="button"
              onClick={() => setSourcesOpen((o) => !o)}
              aria-expanded={sourcesOpen}
              className="w-full flex items-center gap-1.5 text-muted text-xs hover:text-ink transition-colors py-1 rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
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