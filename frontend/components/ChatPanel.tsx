"use client";

import { useState, useRef, useEffect } from "react";
import { chatStream, type HistoryTurn } from "@/lib/api";
import { ChatMessage, type DisplayMessage } from "./ChatMessage";

const SUGGESTIONS = [
  "What does this repo do, at a high level?",
  "Where is the main entry point?",
  "How is authentication handled?",
];

interface ChatPanelProps {
  selectedCollection: string | null;
  repoDisplayName: string | null;
  hasRepos: boolean;
}

export function ChatPanel({ selectedCollection, repoDisplayName, hasRepos }: ChatPanelProps) {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const question = input.trim();
    if (!question || !selectedCollection || busy) return;

    const history: HistoryTurn[] = [];
    for (let i = 0; i < messages.length - 1; i++) {
      if (messages[i].role === "user" && messages[i + 1]?.role === "assistant") {
        history.push({ question: messages[i].content, answer: messages[i + 1].content });
      }
    }

    setInput("");
    setBusy(true);
    setMessages((prev) => [
      ...prev,
      { role: "user", content: question },
      { role: "assistant", content: "", streaming: true },
    ]);

    try {
      let accumulated = "";
      for await (const evt of chatStream(selectedCollection, question, history)) {
        if (evt.event === "token") {
          accumulated += evt.text;
          setMessages((prev) => {
            const next = [...prev];
            next[next.length - 1] = { ...next[next.length - 1], content: accumulated, streaming: true };
            return next;
          });
        } else if (evt.event === "done") {
          setMessages((prev) => {
            const next = [...prev];
            next[next.length - 1] = {
              role: "assistant",
              content: accumulated,
              streaming: false,
              citations: evt.citations,
              provider: evt.provider,
              model: evt.model,
              confidence: evt.confidence,
              confidenceLabel: evt.confidence_label,
              resolvedQuestion: evt.resolved_question,
              retrievalSeconds: evt.retrieval_seconds,
              error: evt.error,
            };
            return next;
          });
        }
      }
    } catch (err) {
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = {
          role: "assistant",
          content: next[next.length - 1]?.content || "",
          streaming: false,
          error: err instanceof Error ? err.message : String(err),
        };
        return next;
      });
    } finally {
      setBusy(false);
    }
  }

  if (!hasRepos) {
    return (
      <EmptyState
        title="No repositories ingested yet"
        desc="Paste a public GitHub URL into the sidebar and click Ingest repo to build a searchable knowledge base you can ask questions against."
      />
    );
  }

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="flex-1 overflow-y-auto px-4 md:px-8 py-6">
        {messages.length === 0 && (
          <div className="mb-4">
            <EmptyState
              title={`Ask something about ${repoDisplayName ?? "this repo"}`}
              desc="Try one of these to get started, or type your own question below."
            />
            <div className="flex flex-wrap justify-center mt-3">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setInput(s)}
                  className="inline-block bg-card border border-hairline rounded-lg px-3 py-1.5 m-1 text-sm text-ink/85 hover:bg-card-hover hover:border-accent/40 transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="max-w-3xl mx-auto w-full">
          {messages.map((m, i) => (
            <ChatMessage key={i} message={m} />
          ))}
          <div ref={scrollRef} />
        </div>
      </div>

      <form
        onSubmit={handleSubmit}
        className="border-t border-hairline p-4 flex gap-2 max-w-3xl mx-auto w-full"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question about the selected repo..."
          disabled={busy || !selectedCollection}
          className="flex-1 bg-card border border-hairline rounded-lg px-3 py-2 text-sm text-ink placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:opacity-60 transition-shadow"
        />
        <button
          type="submit"
          disabled={busy || !selectedCollection || !input.trim()}
          className="bg-navy text-white rounded-lg px-4 py-2 text-sm font-semibold hover:bg-navy-light disabled:opacity-50 transition-colors flex items-center gap-1.5"
        >
          Send
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 12h14M13 6l6 6-6 6" />
          </svg>
        </button>
      </form>
    </div>
  );
}

function EmptyState({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="text-center py-14 px-6 bg-card/40 border border-dashed border-hairline rounded-2xl mt-2 max-w-2xl mx-auto">
      <div className="font-semibold text-[1.1rem] mb-1.5 text-ink">{title}</div>
      <div className="text-sm text-muted max-w-md mx-auto leading-relaxed">{desc}</div>
    </div>
  );
}
