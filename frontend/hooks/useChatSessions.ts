"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { DisplayMessage } from "@/components/ChatMessage";

const STORAGE_KEY = "gaude:chat-sessions:v1";

type Sessions = Record<string, DisplayMessage[]>;

function loadSessions(): Sessions {
  // Guarded for SSR: this hook runs in a "use client" component, but the
  // first render still happens on the server, where sessionStorage is
  // undefined.
  if (typeof window === "undefined") return {};
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? (parsed as Sessions) : {};
  } catch {
    // Corrupt or unreadable storage should never prevent the app booting.
    return {};
  }
}

function persistSessions(sessions: Sessions) {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
  } catch {
    // Quota exceeded or storage disabled (private mode, blocked cookies).
    // Persistence is a nicety -- losing it must not break the live session.
  }
}

export function useChatSessions(collection: string | null) {
  const [sessions, setSessions] = useState<Sessions>({});
  const [hydrated, setHydrated] = useState(false);

  // Load once on mount rather than in useState's initializer, so server and
  // first client render agree (avoids a hydration mismatch).
  useEffect(() => {
    setSessions(loadSessions());
    setHydrated(true);
  }, []);

  // Skip the write on the very first effect run, which would otherwise
  // immediately overwrite stored sessions with the empty initial state.
  const skipFirstPersist = useRef(true);
  useEffect(() => {
    if (!hydrated) return;
    if (skipFirstPersist.current) {
      skipFirstPersist.current = false;
      return;
    }
    persistSessions(sessions);
  }, [sessions, hydrated]);

  const messages: DisplayMessage[] = (collection && sessions[collection]) || [];

  const setMessages = useCallback(
    (updater: (prev: DisplayMessage[]) => DisplayMessage[]) => {
      if (!collection) return;
      setSessions((prev) => ({ ...prev, [collection]: updater(prev[collection] || []) }));
    },
    [collection],
  );

  const clearMessages = useCallback(() => {
    if (!collection) return;
    setSessions((prev) => {
      const next = { ...prev };
      delete next[collection];
      return next;
    });
  }, [collection]);

  return { messages, setMessages, clearMessages, hydrated };
}