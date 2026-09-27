"use client";

import { CheckCircle2, X } from "lucide-react";
import { useEffect } from "react";
import { Button } from "@/components/ui/Button";

// Bottom-right confirmation that dismisses itself after `durationMs`.
export function Toast({ message, onDismiss, durationMs = 5000 }: { message: string; onDismiss: () => void; durationMs?: number }) {
  useEffect(() => {
    const timer = window.setTimeout(onDismiss, durationMs);
    return () => window.clearTimeout(timer);
  }, [onDismiss, durationMs]);

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed right-4 bottom-4 left-4 z-50 flex items-center gap-3 rounded-lg border border-border bg-popover p-4 text-popover-foreground shadow-2xl sm:left-auto sm:max-w-sm"
    >
      <CheckCircle2 size={18} className="shrink-0 text-success" aria-hidden="true" />
      <p className="flex-1 text-sm">{message}</p>
      <Button variant="ghost" size="icon" aria-label="Dismiss" onClick={onDismiss}>
        <X size={16} aria-hidden="true" />
      </Button>
    </div>
  );
}
