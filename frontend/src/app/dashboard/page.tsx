"use client";

import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";

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

  async function fetchPortfolios(accessToken: string) {
  const res = await fetch("http://127.0.0.1:8000/portfolios", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  const bodyText = await res.text();

  if (!res.ok) {
    setError(`Status ${res.status} | token length ${accessToken.length} | body: ${bodyText}`);
    return;
  }

  setPortfolios(JSON.parse(bodyText));
}


  const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
    if (session) {
      fetchPortfolios(session.access_token);
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
      {portfolios.length === 0 && <p>No portfolios yet.</p>}
      <ul>
        {portfolios.map((p) => (
          <li key={p.id}>
            {p.name} — {p.base_currency} {p.cash_balance} cash (of {p.initial_capital} initial)
          </li>
        ))}
      </ul>
    </div>
  );
}
