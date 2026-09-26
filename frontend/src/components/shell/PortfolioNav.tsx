"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch, getAccessToken } from "@/lib/api";

type Props = {
  portfolioId: string;
  current: "current" | "recommendation";
  // Pages that already loaded the portfolio pass its name to skip a second fetch.
  portfolioName?: string;
};

export function PortfolioNav({ portfolioId, current, portfolioName }: Props) {
  const [fetchedName, setFetchedName] = useState<string | null>(null);
  const name = portfolioName ?? fetchedName;

  useEffect(() => {
    if (portfolioName) return;
    let cancelled = false;
    async function loadName() {
      try {
        const accessToken = await getAccessToken();
        if (!accessToken) return;
        const portfolio = await apiFetch<{ name: string }>(`/portfolios/${portfolioId}`, accessToken);
        if (!cancelled) setFetchedName(portfolio.name);
      } catch (err) {
        console.error("Failed to load portfolio name:", err);
      }
    }
    void loadName();
    return () => {
      cancelled = true;
    };
  }, [portfolioId, portfolioName]);

  const base = `/dashboard/portfolios/${portfolioId}`;

  return (
    <div className="portfolio-nav">
      <nav aria-label="Breadcrumb">
        <ol className="breadcrumbs">
          <li><Link href="/dashboard">Portfolios</Link></li>
          <li>
            {current === "current" ? <span aria-current="page">{name ?? "Portfolio"}</span> : <Link href={base}>{name ?? "Portfolio"}</Link>}
          </li>
          {current === "recommendation" && <li><span aria-current="page">Recommendation</span></li>}
        </ol>
      </nav>
      <div className="page-tabs" role="tablist" aria-label="Portfolio views">
        <Link href={base} role="tab" aria-selected={current === "current"} className={`page-tab ${current === "current" ? "active" : ""}`}>
          Current
        </Link>
        <Link
          href={`${base}/recommendation`}
          role="tab"
          aria-selected={current === "recommendation"}
          className={`page-tab ${current === "recommendation" ? "active" : ""}`}
        >
          Recommendation
        </Link>
      </div>
    </div>
  );
}
