"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneLight, oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { useTheme } from "@/lib/theme";
import { completeIncompleteMarkdown } from "@/lib/incompleteMarkdown";
import { CopyButton } from "./CopyButton";

// Re-parsing markdown on every single streamed token causes visible flicker
// (per the streaming-markdown research this was built from) — batch updates
// to this cadence instead. 80ms is frequent enough to still feel live.
const RENDER_THROTTLE_MS = 80;

interface MarkdownMessageProps {
  content: string;
  streaming?: boolean;
}

export function MarkdownMessage({ content, streaming }: MarkdownMessageProps) {
  const { theme } = useTheme();
  const [displayed, setDisplayed] = useState(content);
  const lastFlush = useRef(0);
  const pendingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!streaming) {
      // Not streaming (finished, or a static history message) — show the
      // real content immediately, no throttling, and cancel any pending
      // throttled update so it can't overwrite this with stale text later.
      if (pendingTimer.current) clearTimeout(pendingTimer.current);
      setDisplayed(content);
      return;
    }

    const now = Date.now();
    const elapsed = now - lastFlush.current;
    if (elapsed >= RENDER_THROTTLE_MS) {
      lastFlush.current = now;
      setDisplayed(content);
    } else if (!pendingTimer.current) {
      pendingTimer.current = setTimeout(() => {
        pendingTimer.current = null;
        lastFlush.current = Date.now();
        setDisplayed(content);
      }, RENDER_THROTTLE_MS - elapsed);
    }

    return () => {
      if (pendingTimer.current) {
        clearTimeout(pendingTimer.current);
        pendingTimer.current = null;
      }
    };
  }, [content, streaming]);

  const safeContent = streaming ? completeIncompleteMarkdown(displayed) : displayed;
  const syntaxStyle = theme === "dark" ? oneDark : oneLight;

  return (
    <div
      className="markdown-body text-sm leading-relaxed text-ink"
      aria-live="polite"
      aria-atomic="false"
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          pre({ children }) {
            // Fenced code blocks always reach here already rendered by the
            // `code` component below — pass through unwrapped so we don't
            // get a redundant native <pre> around our custom block.
            return <>{children}</>;
          },
          code(props) {
            const { className, children, ...rest } = props as {
              className?: string;
              children?: React.ReactNode;
            };
            const match = /language-(\w+)/.exec(className || "");
            const text = String(children ?? "").replace(/\n$/, "");
            const isBlock = Boolean(match) || text.includes("\n");

            if (!isBlock) {
              return (
                <code
                  className="font-mono text-[0.85em] bg-card-hover border border-hairline rounded px-1 py-0.5"
                  {...rest}
                >
                  {children}
                </code>
              );
            }

            return (
              <div className="relative group my-2">
                <CopyButton
                  text={text}
                  className="absolute top-1.5 right-1.5 opacity-0 group-hover:opacity-100 transition-opacity z-10"
                />
                <SyntaxHighlighter
                  language={match ? match[1] : undefined}
                  style={syntaxStyle}
                  customStyle={{ margin: 0, borderRadius: "0.5rem", fontSize: "0.8rem" }}
                >
                  {text}
                </SyntaxHighlighter>
              </div>
            );
          },
          a(props) {
            return <a {...props} target="_blank" rel="noreferrer" className="text-accent hover:underline" />;
          },
          ul(props) {
            return <ul className="list-disc pl-5 my-1.5 space-y-0.5" {...props} />;
          },
          ol(props) {
            return <ol className="list-decimal pl-5 my-1.5 space-y-0.5" {...props} />;
          },
          p(props) {
            return <p className="my-1.5 first:mt-0 last:mb-0" {...props} />;
          },
          table(props) {
            return (
              <div className="overflow-x-auto my-2">
                <table className="border-collapse text-xs" {...props} />
              </div>
            );
          },
          th(props) {
            return <th className="border border-hairline px-2 py-1 bg-card-hover text-left" {...props} />;
          },
          td(props) {
            return <td className="border border-hairline px-2 py-1" {...props} />;
          },
        }}
      >
        {safeContent}
      </ReactMarkdown>
    </div>
  );
}
