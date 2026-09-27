import Link from "next/link";
import { BarChart3 } from "lucide-react";
import type { ReactNode } from "react";

export const AUTH_INPUT =
  "h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function AuthShell({ title, subtitle, children, footer }: { title: string; subtitle: string; children: ReactNode; footer: ReactNode }) {
  return (
    <main className="grid min-h-screen place-items-center bg-background px-4 py-10">
      <div className="w-full max-w-md">
        <Link href="/" className="mb-6 flex items-center justify-center gap-2 font-bold text-foreground">
          <span className="grid size-8 place-items-center rounded-md bg-primary text-primary-foreground">
            <BarChart3 size={17} aria-hidden="true" />
          </span>
          PortfolioPilot
        </Link>
        <section className="rounded-lg border border-border bg-card p-6 shadow-sm sm:p-8">
          <h1 className="text-2xl font-bold">{title}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
          <div className="mt-6">{children}</div>
        </section>
        <p className="mt-5 text-center text-sm text-muted-foreground">{footer}</p>
      </div>
    </main>
  );
}

export function AuthField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium">{label}</span>
      {children}
    </label>
  );
}
