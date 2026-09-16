"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { apiFetch } from "@/lib/api";

type Portfolio = {
  id: string;
  name: string;
  base_currency: string;
  initial_capital: string;
  cash_balance: string;
};

export default function DashboardPage() {
  const [portfolios, setPortfolios] = useState<Portfolio[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const supabase = createClient();

    async function loadPortfolios(accessToken: string) {
      try {
        const data = await apiFetch<Portfolio[]>("/portfolios", accessToken);
        setPortfolios(data);
      } catch (err) {
        console.error("Failed to load portfolios:", err);
        setError("Unable to load your portfolios. Please try again.");
      }
    }

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session) {
        loadPortfolios(session.access_token);
      } else {
        setError("No active session.");
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  if (error) return <div style={{ padding: 40 }}>{error}</div>;
  if (!portfolios) return <div style={{ padding: 40 }}>Loading...</div>;

  return (
    <div style={{ padding: 40 }}>
      <h1>Your Portfolios</h1>
      <p>
        <Link href="/dashboard/new-portfolio">Create Portfolio</Link>
      </p>
      {portfolios.length === 0 && <p>No portfolios yet.</p>}
      <ul>
        {portfolios.map((p) => (
          <li key={p.id}>
            <Link href={`/dashboard/portfolios/${p.id}`}>
              {p.name} — {p.base_currency} {p.cash_balance} cash (of {p.initial_capital} initial)
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
