"use client";

import Link from "next/link";
import { BarChart3, Menu, X } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { OnboardingGuide } from "@/components/onboarding/OnboardingGuide";
import { ThemeToggle, ThemeToggleWide } from "@/components/shell/ThemeToggle";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { createClient } from "@/lib/supabase/client";

export function DashboardNav() {
  const pathname = usePathname();
  const router = useRouter();
  const [signingOut, setSigningOut] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);


  async function handleSignOut() {
    setSigningOut(true);
    await createClient().auth.signOut();
    router.push("/login");
  }

  const links = [{ href: "/dashboard", label: "Portfolios", active: pathname.startsWith("/dashboard") }];

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-3 px-4 sm:px-6">
        <Link href="/dashboard" className="flex items-center gap-2 font-bold text-foreground">
          <span className="grid size-8 place-items-center rounded-md bg-primary text-primary-foreground">
            <BarChart3 size={17} aria-hidden="true" />
          </span>
          <span>PortfolioPilot</span>
        </Link>
        <div className="flex items-center gap-1">
          <nav className="hidden items-center gap-1 md:flex" aria-label="Main">
            {links.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                aria-current={link.active ? "page" : undefined}
                className={cn(
                  "rounded-md px-3 py-2 text-sm font-medium",
                  link.active ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {link.label}
              </Link>
            ))}
          </nav>
          {/* Always rendered (also on mobile) so the first-time guide can open. */}
          <OnboardingGuide autoOpen={pathname === "/dashboard"} />
          <div className="hidden items-center gap-1 md:flex">
            <ThemeToggle />
            <Button variant="ghost" size="sm" onClick={() => void handleSignOut()} disabled={signingOut}>
              {signingOut ? "Signing out…" : "Sign out"}
            </Button>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
            aria-expanded={mobileOpen}
            aria-controls="mobile-nav"
            onClick={() => setMobileOpen(!mobileOpen)}
          >
            {mobileOpen ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
          </Button>
        </div>
      </div>
      {mobileOpen && (
        <div id="mobile-nav" className="border-t border-border px-4 py-3 md:hidden">
          <nav className="flex flex-col gap-1" aria-label="Main">
            {links.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                aria-current={link.active ? "page" : undefined}
                className={cn("py-2 text-sm", link.active ? "font-semibold text-foreground" : "text-muted-foreground")}
                onClick={() => setMobileOpen(false)}
              >
                {link.label}
              </Link>
            ))}
            <ThemeToggleWide />
            <Button variant="ghost" className="justify-start px-0" onClick={() => void handleSignOut()} disabled={signingOut}>
              {signingOut ? "Signing out…" : "Sign out"}
            </Button>
          </nav>
        </div>
      )}
    </header>
  );
}
