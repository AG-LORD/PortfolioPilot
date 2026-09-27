"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { cn } from "@/lib/cn";

type Props = {
  open: boolean;
  onClose: () => void;
  labelledBy: string;
  describedBy?: string;
  // "dialog": centred card; "sheet": right-side panel.
  variant?: "dialog" | "sheet";
  // Dialog width: max-w-md by default, max-w-lg when wide.
  wide?: boolean;
  className?: string;
  children: ReactNode;
};

// Native <dialog> opened with showModal(): the page behind is inert (focus stays
// inside) and Esc closes it. Clicking the overlay closes it too.
export function Modal({ open, onClose, labelledBy, describedBy, variant = "dialog", wide, className, children }: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={labelledBy}
      aria-describedby={describedBy}
      onClose={onClose}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) event.currentTarget.close();
      }}
      className={cn(
        "border border-border p-0 text-card-foreground shadow-2xl backdrop:bg-overlay",
        variant === "dialog"
          ? cn("m-auto w-[calc(100%-2rem)] rounded-lg bg-card", wide ? "max-w-lg" : "max-w-md")
          : "ml-auto mr-0 h-dvh max-h-dvh w-full max-w-md rounded-none border-y-0 border-r-0 bg-background",
        className,
      )}
    >
      {open && children}
    </dialog>
  );
}
