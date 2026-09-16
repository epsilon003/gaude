"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// How far from the bottom still counts as "following along". Generous enough
// to survive the layout shift of a token arriving mid-scroll.
const BOTTOM_THRESHOLD_PX = 120;

export function useStickyScroll<T>(dependency: T) {
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [isPinned, setIsPinned] = useState(true);

  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setIsPinned(distanceFromBottom <= BOTTOM_THRESHOLD_PX);
  }, []);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    bottomRef.current?.scrollIntoView({ behavior });
    setIsPinned(true);
  }, []);

  useEffect(() => {
    if (!isPinned) return;
    // "auto" rather than "smooth": during streaming this fires many times a
    // second, and queued smooth animations visibly lag behind the text.
    bottomRef.current?.scrollIntoView({ behavior: "auto" });
  }, [dependency, isPinned]);

  return { containerRef, bottomRef, isPinned, handleScroll, scrollToBottom };
}