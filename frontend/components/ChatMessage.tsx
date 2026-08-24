import { ProviderBadge, ConfidenceBadge, TimingBadge } from "./Badges";
import { CitationCard } from "./CitationCard";
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
  if (message.role === "user") {
    return (
      <div className="flex justify-end mb-3">
        <div className="bg-navy text-white rounded-2xl rounded-br-sm px-4 py-2.5 max-w-[75%] text-sm">
          {message.content}
        </div>
      </div>
    );
  }

  const hasCitations = !!message.citations?.length;

  return (
    <div className="flex justify-start mb-4">
      <div className="bg-card border border-hairline rounded-2xl rounded-bl-sm px-4 py-3 max-w-[85%] text-sm">
        <div className="whitespace-pre-wrap leading-relaxed text-ink">
          {message.content}
          {message.streaming && <span className="inline-block w-1.5 h-4 bg-ink/40 ml-0.5 align-middle animate-pulse" />}
        </div>

        {message.error && (
          <p className="text-confidence-weak text-xs mt-2">{message.error}</p>
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

            <div className="text-muted text-xs mb-1.5">Sources ({message.citations!.length})</div>
            {message.citations!.map((c, i) => (
              <CitationCard key={`${c.file_path}-${c.start_line}-${i}`} citation={c} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
