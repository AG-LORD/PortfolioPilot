import Link from "next/link";
import { ChevronRight, Info } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export function Metric({
  label,
  value,
  note,
  info,
  valueClassName,
  action,
}: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  info?: string;
  valueClassName?: string;
  // Small control in the top-right corner, e.g. an "Add money" button.
  action?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          {label}
          {info && (
            <span title={info} aria-label={info} role="img" className="cursor-help">
              <Info size={14} aria-hidden="true" />
            </span>
          )}
        </div>
        {action}
      </div>
      <p className={cn("mt-2 text-xl font-bold whitespace-nowrap tabular-nums sm:text-2xl", valueClassName)}>{value}</p>
      {note && <p className="mt-1 text-xs text-muted-foreground">{note}</p>}
    </div>
  );
}

export function Section({
  title,
  subtitle,
  action,
  children,
  id,
}: {
  title: string;
  subtitle?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  id?: string;
}) {
  return (
    <section className="scroll-mt-20 py-7" id={id} aria-label={title}>
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold">{title}</h2>
          {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function PageTitle({ eyebrow, title, action }: { eyebrow?: ReactNode; title: string; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <p className="mb-1 text-xs font-semibold uppercase tracking-widest text-muted-foreground">{eyebrow}</p>}
        <h1 className="text-2xl font-bold wrap-break-word sm:text-3xl">{title}</h1>
      </div>
      {action}
    </div>
  );
}

export function Breadcrumbs({ current }: { current?: string }) {
  return (
    <nav aria-label="Breadcrumb" className="mb-5 flex items-center gap-1 text-xs text-muted-foreground">
      <Link href="/dashboard" className="hover:text-foreground">
        Portfolios
      </Link>
      {current && (
        <>
          <ChevronRight size={13} aria-hidden="true" />
          <span className="text-foreground" aria-current="page">
            {current}
          </span>
        </>
      )}
    </nav>
  );
}

export function PortfolioTabs({ portfolioId, active }: { portfolioId: string; active: "current" | "plan" }) {
  const base = `/dashboard/portfolios/${portfolioId}`;
  const tab = (isActive: boolean) =>
    cn(
      "-mb-px px-4 py-3 text-sm font-semibold",
      isActive ? "border-b-2 border-primary text-primary" : "text-muted-foreground hover:text-foreground",
    );
  return (
    <nav className="flex border-b border-border" aria-label="Portfolio views">
      <Link href={base} className={tab(active === "current")} aria-current={active === "current" ? "page" : undefined}>
        Current
      </Link>
      <Link
        href={`${base}/recommendation`}
        className={tab(active === "plan")}
        aria-current={active === "plan" ? "page" : undefined}
      >
        Plan
      </Link>
    </nav>
  );
}

export function RiskBadge({ category, className }: { category: string; className?: string }) {
  return (
    <span
      className={cn(
        "rounded-full bg-warning/15 px-2 py-1 text-[11px] font-semibold text-warning-foreground",
        className,
      )}
    >
      {category.charAt(0).toUpperCase() + category.slice(1)}
    </span>
  );
}

export function SourcePill({ source }: { source: "ml" | "historical" }) {
  return (
    <span
      className="rounded bg-muted px-2 py-1 text-[11px] font-bold"
      title={source === "ml" ? "Machine-learning forecast" : "Historical average (fallback)"}
    >
      {source === "ml" ? "ML" : "Historical"}
    </span>
  );
}

export function Notice({
  tone = "info",
  children,
  role,
}: {
  tone?: "info" | "error" | "warning" | "success";
  children: ReactNode;
  role?: "alert" | "status" | "note";
}) {
  const tones = {
    info: "border-border bg-muted/50 text-foreground",
    error: "border-destructive/30 bg-destructive/10 text-foreground",
    warning: "border-warning/30 bg-warning/10 text-foreground",
    success: "border-success/25 bg-success/10 text-foreground",
  };
  return (
    <div className={cn("rounded-lg border p-4 text-sm", tones[tone])} role={role ?? (tone === "error" ? "alert" : "status")}>
      {children}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-lg bg-muted", className)} />;
}

export function PageContainer({ children }: { children: ReactNode }) {
  return <main className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 sm:py-10">{children}</main>;
}
