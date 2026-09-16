"use client";

import { useEffect, useState } from "react";

interface ToastProps {
  message: string;
  type?: "success" | "error" | "info";
  duration?: number;
  onClose: () => void;
}

export function Toast({ message, type = "info", duration = 4000, onClose }: ToastProps) {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    setIsVisible(true);
    const timer = setTimeout(() => {
      setIsVisible(false);
      setTimeout(onClose, 300);
    }, duration);

    return () => clearTimeout(timer);
  }, [duration, onClose]);

  const accent = {
    success: "border-l-confidence-strong",
    error: "border-l-confidence-weak",
    info: "border-l-accent",
  }[type];

  return (
    <div
      // role=status + aria-live so errors that only ever appeared as a toast
      // are announced rather than silently flashing past screen-reader users.
      role="status"
      aria-live="polite"
      className={`elevated pointer-events-auto bg-card text-ink border border-hairline border-l-4 ${accent} px-4 py-3 rounded-lg shadow-lg text-sm max-w-sm transition-all duration-300 ${
        isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2"
      }`}
    >
      {message}
    </div>
  );
}