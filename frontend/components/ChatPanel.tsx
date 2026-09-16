"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { chatStream, type HistoryTurn } from "@/lib/api";
import { ChatMessage, type DisplayMessage } from "./ChatMessage";
import { useChatSessions } from "@/hooks/useChatSessions";
import { useStickyScroll } from "@/hooks/useStickyScroll";

// Deliberately repo-agnostic. The previous set included "How is
// authentication handled?", which is a dead end for the majority of
// repositories and makes the tool look like it assumes a web app.
const SUGGESTIONS = [
  "What does this repo do, at a high level?",
  "What are the main modules and how do they fit together?",
  "How do I run this locally?",
];

let messageIdCounter = 0;
function nextMessageId() {
  return `m${messageIdCounter++}`;
}

interface ChatPanelProps {
  selectedCollection: string | null;
  repoDisplayName: string | null;
  hasRepos: boolean;
  onNotify?: (message: string, type: "success" | "error" | "info") => void;
}

export function ChatPanel({
  selectedCollection,
  repoDisplayName,
  hasRepos,
  onNotify,
}: ChatPanelProps) {
  // Message state is keyed by collection, so switching repos can never leak
  // one repo's turns into another repo's `history`.
  const { messages, setMessages, clearMessages } = useChatSessions(selectedCollection);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const { containerRef, bottomRef, isPinned, handleScroll, scrollToBottom } =
    useStickyScroll(messages);

  // Cancel any in-flight generation when the user switches repos -- its
  // tokens would otherwise land in the newly-selected repo's session.
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, [selectedCollection]);

  // Auto-grow the textarea up to a cap, then scroll internally.
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [input]);

  // Cmd/Ctrl+K focuses the question input; Escape stops an in-flight
  // generation. No command palette here — this app has nothing meaningful
  // to put in one (no multiple chats, no settings), so Cmd+K just jumps to
  // the input, which is the part of that shortcut people actually rely on.
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      } else if (e.key === "Escape" && busy) {
        abortRef.current?.abort();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [busy]);

  const runQuestion = useCallback(
    async (question: string, historyOverride?: DisplayMessage[]) => {
      if (!question || !selectedCollection || busy) return;

      const baseMessages = historyOverride ?? messages;
      const history: HistoryTurn[] = [];
      for (let i = 0; i < baseMessages.length - 1; i++) {
        if (baseMessages[i].role === "user" && baseMessages[i + 1]?.role === "assistant") {
          history.push({ question: baseMessages[i].content, answer: baseMessages[i + 1].content });
        }
      }

      const controller = new AbortController();
      abortRef.current = controller;

      setBusy(true);
      setMessages((prev) => [
        ...prev,
        { id: nextMessageId(), role: "assistant", content: "", streaming: true },
      ]);

      try {
        let accumulated = "";
        for await (const evt of chatStream(selectedCollection, question, history, controller.signal)) {
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
                ...next[next.length - 1],
                role: "assistant",
                content: accumulated,
                streaming: false,
                citations: evt.citations,
                provider: evt.provider,
                model: evt.model,
                confidence: evt.confidence,
                confidenceLabel: evt.confidence_label,
                // Backend now only sets resolved_question when the LLM
                // actually rewrote a follow-up into a standalone question;
                // guard here too so "Interpreted as: ..." never shows the
                // question back at the user unchanged.
                resolvedQuestion:
                  evt.resolved_question && evt.resolved_question !== question
                    ? evt.resolved_question
                    : undefined,
                retrievalSeconds: evt.retrieval_seconds,
                error: evt.error,
              };
              return next;
            });
            if (evt.error) onNotify?.(evt.error, "error");
          }
        }
      } catch (err) {
        const isAbort = err instanceof DOMException && err.name === "AbortError";
        const errorText = isAbort
          ? undefined
          : err instanceof Error
          ? err.message
          : String(err);
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = {
            ...next[next.length - 1],
            role: "assistant",
            content: next[next.length - 1]?.content || "",
            streaming: false,
            stopped: isAbort,
            error: errorText,
          };
          return next;
        });
        if (errorText) onNotify?.(errorText, "error");
      } finally {
        setBusy(false);
        abortRef.current = null;
      }
    },
    [selectedCollection, busy, messages, setMessages, onNotify],
  );

  function submitQuestion() {
    const question = input.trim();
    if (!question || !selectedCollection || busy) return;

    setInput("");
    const historySnapshot = messages;
    setMessages((prev) => [...prev, { id: nextMessageId(), role: "user", content: question }]);
    scrollToBottom("auto");
    runQuestion(question, historySnapshot);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    submitQuestion();
  }

  // Enter sends, Shift+Enter inserts a newline -- the convention people
  // already expect from every other chat surface.
  function handleInputKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submitQuestion();
    }
  }

  function handleStop() {
    abortRef.current?.abort();
  }

  function handleRetry(assistantIndex: number) {
    const question = messages[assistantIndex - 1]?.content;
    if (!question) return;
    const historySnapshot = messages.slice(0, assistantIndex - 1);
    setMessages((prev) => prev.slice(0, assistantIndex)); // drop the failed answer, keep the user question
    runQuestion(question, historySnapshot);
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
    <div className="flex flex-col flex-1 min-h-0 relative">
      {messages.length > 0 && (
        <div className="flex justify-end px-4 md:px-8 pt-3">
          <button
            type="button"
            onClick={clearMessages}
            disabled={busy}
            className="text-xs text-muted hover:text-ink disabled:opacity-40 transition-colors rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 px-1.5 py-0.5"
          >
            Clear conversation
          </button>
        </div>
      )}

      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-4 md:px-8 py-6"
      >
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
                  onClick={() => {
                    setInput(s);
                    inputRef.current?.focus();
                  }}
                  className="inline-block bg-card border border-hairline rounded-lg px-3 py-1.5 m-1 text-sm text-ink/85 hover:bg-card-hover hover:border-accent/40 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="max-w-3xl mx-auto w-full">
          {messages.map((m, i) => (
            <ChatMessage
              key={m.id ?? i}
              message={m}
              onRetry={m.role === "assistant" && m.error ? () => handleRetry(i) : undefined}
            />
          ))}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Only offered once the user has actually scrolled away, so it never
          covers content during normal top-to-bottom reading. */}
      {!isPinned && messages.length > 0 && (
        <button
          type="button"
          onClick={() => scrollToBottom()}
          className="absolute bottom-24 left-1/2 -translate-x-1/2 elevated bg-card border border-hairline text-ink text-xs rounded-full px-3 py-1.5 flex items-center gap-1.5 hover:bg-card-hover transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 5v14M19 12l-7 7-7-7" />
          </svg>
          Jump to latest
        </button>
      )}

      <form onSubmit={handleSubmit} className="border-t border-hairline p-4 max-w-3xl mx-auto w-full">
        <div className="flex gap-2 items-end">
          <label htmlFor="question-input" className="sr-only">
            Ask a question about the selected repository
          </label>
          <textarea
            id="question-input"
            ref={inputRef}
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleInputKeyDown}
            placeholder="Ask a question about the selected repo..."
            disabled={busy || !selectedCollection}
            className="flex-1 resize-none bg-card border border-hairline rounded-lg px-3 py-2 text-sm text-ink placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:opacity-60 transition-shadow leading-relaxed"
          />
          {busy ? (
            <button
              type="button"
              onClick={handleStop}
              className="bg-navy text-white rounded-lg px-4 py-2 text-sm font-semibold hover:bg-navy-light transition-colors flex items-center gap-1.5 shrink-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
              title="Stop generating (Esc)"
            >
              Stop
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="6" width="12" height="12" rx="1.5" />
              </svg>
            </button>
          ) : (
            <button
              type="submit"
              disabled={!selectedCollection || !input.trim()}
              className="bg-navy text-white rounded-lg px-4 py-2 text-sm font-semibold hover:bg-navy-light disabled:opacity-50 transition-colors flex items-center gap-1.5 shrink-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
            >
              Send
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 12h14M13 6l6 6-6 6" />
              </svg>
            </button>
          )}
        </div>
        {/* The Esc-to-stop shortcut existed but was undiscoverable. */}
        <div className="text-[0.7rem] text-muted mt-1.5 hidden md:block">
          <kbd className="font-mono">Enter</kbd> to send ·{" "}
          <kbd className="font-mono">Shift+Enter</kbd> for a new line ·{" "}
          <kbd className="font-mono">Ctrl/Cmd+K</kbd> to focus
          {busy && (
            <>
              {" "}
              · <kbd className="font-mono">Esc</kbd> to stop
            </>
          )}
        </div>
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