import Link from "next/link";
import { CheckCircle2, CircleDashed, ClipboardList } from "lucide-react";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format";

export type PlanStatus =
  | { kind: "none" }
  | { kind: "loading"; adoptedAt: string | null }
  | { kind: "unavailable"; adoptedAt: string | null; message: string }
  | { kind: "orders"; adoptedAt: string | null; remaining: number };

export function PlanStatusBanner({ status, planHref }: { status: PlanStatus; planHref: string }) {
  const matched = status.kind === "orders" && status.remaining === 0;
  const pending = status.kind === "orders" && status.remaining > 0;

  let title: string;
  let detail: string;
  if (status.kind === "none") {
    title = "No active plan yet";
    detail = "Review the proposed plan and adopt it to get a list of orders to place at your broker.";
  } else if (status.kind === "loading") {
    title = "Active plan";
    detail = "Checking which orders are still open…";
  } else if (status.kind === "unavailable") {
    title = "Active plan";
    detail = status.message;
  } else if (matched) {
    title = "Holdings match your plan ✓";
    detail = `All orders from your plan adopted on ${formatDate(status.adoptedAt)} have been recorded.`;
  } else {
    title = `${status.remaining} order${status.remaining === 1 ? "" : "s"} remaining`;
    detail = "Place them at your broker, then tick them off in the plan's order checklist.";
  }

  const Icon = matched ? CheckCircle2 : pending ? ClipboardList : CircleDashed;

  return (
    <div
      role="status"
      className={cn(
        "mt-6 flex flex-col gap-3 rounded-lg border p-4 sm:flex-row sm:items-center sm:justify-between",
        matched && "border-success/25 bg-success/10",
        pending && "border-warning/30 bg-warning/10",
        !matched && !pending && "border-border bg-muted/50",
      )}
    >
      <div className="flex items-center gap-3">
        <Icon
          size={20}
          aria-hidden="true"
          className={cn("shrink-0", matched ? "text-success" : pending ? "text-warning-foreground" : "text-muted-foreground")}
        />
        <div>
          <p className="font-semibold">{title}</p>
          <p className="text-xs text-muted-foreground">{detail}</p>
        </div>
      </div>
      <Link href={planHref} className="text-sm font-semibold text-primary hover:underline">
        View plan
      </Link>
    </div>
  );
}
