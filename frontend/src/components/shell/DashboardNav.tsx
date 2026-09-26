"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { ThemeToggle } from "@/components/shell/ThemeToggle";
import { createClient } from "@/lib/supabase/client";

export function DashboardNav() {
  const pathname = usePathname();
  const router = useRouter();
  const [signingOut, setSigningOut] = useState(false);

  const researchActive = pathname.startsWith("/dashboard/model-evaluation");
  const portfoliosActive = !researchActive;

  async function handleSignOut() {
    setSigningOut(true);
    await createClient().auth.signOut();
    router.push("/login");
  }

  return (
    <header className="shell-bar">
      <nav className="shell-nav" aria-label="Main">
        <Link href="/dashboard" className="shell-brand">
          <span className="shell-brand-mark" aria-hidden="true">P</span>
          PortfolioPilot
        </Link>
        <div className="shell-links">
          <Link href="/dashboard" className={`shell-link ${portfoliosActive ? "active" : ""}`} aria-current={portfoliosActive ? "page" : undefined}>
            Portfolios
          </Link>
          <Link
            href="/dashboard/model-evaluation"
            className={`shell-link ${researchActive ? "active" : ""}`}
            aria-current={researchActive ? "page" : undefined}
          >
            Research
          </Link>
        </div>
        <div className="shell-actions">
          <ThemeToggle />
          <button type="button" className="ghost-button shell-signout" onClick={() => void handleSignOut()} disabled={signingOut}>
            {signingOut ? "Signing out…" : "Sign out"}
          </button>
        </div>
      </nav>
    </header>
  );
}
