import { useState, useCallback, useRef } from "react";

interface ToastState {
  message: string;
  type: "success" | "error" | "info";
  id: number;
}

export function useToast() {
  const [toasts, setToasts] = useState<ToastState[]>([]);
  // Date.now() collides when two toasts fire in the same millisecond (e.g. an
  // ingest error immediately followed by a refresh failure), which produces
  // duplicate React keys and makes removeToast dismiss both at once.
  const nextId = useRef(0);

  const showToast = useCallback((message: string, type: "success" | "error" | "info" = "info") => {
    const id = nextId.current++;
    setToasts((prev) => [...prev, { message, type, id }]);
  }, []);

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return { toasts, showToast, removeToast };
}