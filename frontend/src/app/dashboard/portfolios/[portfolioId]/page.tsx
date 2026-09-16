"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { apiFetch } from "@/lib/api";

type Portfolio = {
  id: string;
  name: string;
  purpose: string | null;
  base_currency: string;
  initial_capital: string;
  cash_balance: string;
};

type Holding = {
  id: string;
  ticker: string;
  quantity: string;
  average_cost: string;
};

type Transaction = {
  id: string;
  transaction_type: string;
  ticker: string;
  quantity: string;
  price: string;
  fees: string;
  occurred_at: string;
  source: string;
};

type HoldingValuation = {
  ticker: string;
  quantity: string;
  average_cost: string;
  current_price: string;
  market_value: string;
  unrealized_pnl: string;
};

type PortfolioValuation = {
  portfolio_id: string;
  cash_balance: string;
  invested_value: string;
  total_value: string;
  unrealized_pnl: string;
  holdings: HoldingValuation[];
};

export default function PortfolioDetailPage() {
  const { portfolioId } = useParams<{ portfolioId: string }>();

  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [holdings, setHoldings] = useState<Holding[] | null>(null);
  const [transactions, setTransactions] = useState<Transaction[] | null>(null);
  const [valuation, setValuation] = useState<PortfolioValuation | null>(null);

  const [authError, setAuthError] = useState<string | null>(null);
  const [portfolioError, setPortfolioError] = useState<string | null>(null);
  const [holdingsError, setHoldingsError] = useState<string | null>(null);
  const [transactionsError, setTransactionsError] = useState<string | null>(null);
  const [valuationError, setValuationError] = useState<string | null>(null);

  useEffect(() => {
    const supabase = createClient();

    async function loadAll(accessToken: string) {
      try {
        setPortfolio(await apiFetch<Portfolio>(`/portfolios/${portfolioId}`, accessToken));
      } catch (err) {
        console.error("Failed to load portfolio:", err);
        setPortfolioError("Unable to load this portfolio.");
      }

      try {
        setHoldings(await apiFetch<Holding[]>(`/portfolios/${portfolioId}/holdings`, accessToken));
      } catch (err) {
        console.error("Failed to load holdings:", err);
        setHoldingsError("Unable to load holdings.");
      }

      try {
        setTransactions(
          await apiFetch<Transaction[]>(`/portfolios/${portfolioId}/transactions`, accessToken),
        );
      } catch (err) {
        console.error("Failed to load transactions:", err);
        setTransactionsError("Unable to load transactions.");
      }

      try {
        setValuation(
          await apiFetch<PortfolioValuation>(`/portfolios/${portfolioId}/valuation`, accessToken),
        );
      } catch (err) {
        console.error("Failed to load valuation:", err);
        setValuationError("Live valuation is currently unavailable.");
      }
    }

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session) {
        loadAll(session.access_token);
      } else {
        setAuthError("No active session.");
      }
    });

    return () => subscription.unsubscribe();
  }, [portfolioId]);

  if (authError) return <div style={{ padding: 40 }}>{authError}</div>;
  if (portfolioError) return <div style={{ padding: 40 }}>{portfolioError}</div>;
  if (!portfolio) return <div style={{ padding: 40 }}>Loading...</div>;

  const valuationByTicker = new Map(valuation?.holdings.map((h) => [h.ticker, h]) ?? []);

  return (
    <div style={{ padding: 40 }}>
      <h1>{portfolio.name}</h1>
      <p>Purpose: {portfolio.purpose ?? "—"}</p>
      <p>Base currency: {portfolio.base_currency}</p>
      <p>Initial capital: {portfolio.initial_capital}</p>
      <p>Cash balance: {portfolio.cash_balance}</p>

      <h2>Valuation</h2>
      {valuationError && <p>{valuationError}</p>}
      {!valuationError && valuation === null && <p>Loading valuation...</p>}
      {valuation !== null && (
        <ul>
          <li>Total Portfolio Value: {valuation.total_value}</li>
          <li>Cash: {valuation.cash_balance}</li>
          <li>Invested Value: {valuation.invested_value}</li>
          <li>Unrealized P&amp;L: {valuation.unrealized_pnl}</li>
        </ul>
      )}

      <h2>Holdings</h2>
      {holdingsError && <p>{holdingsError}</p>}
      {!holdingsError && holdings === null && <p>Loading holdings...</p>}
      {holdings !== null && holdings.length === 0 && <p>No holdings yet.</p>}
      {holdings !== null && holdings.length > 0 && (
        <ul>
          {holdings.map((h) => {
            const hv = valuationByTicker.get(h.ticker);
            return (
              <li key={h.id}>
                {h.ticker} — qty {h.quantity} @ avg cost {h.average_cost}
                {hv && (
                  <>
                    {" "}
                    — current price {hv.current_price}, market value {hv.market_value}, unrealized
                    P&amp;L {hv.unrealized_pnl}
                  </>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <h2>Transactions</h2>
      {transactionsError && <p>{transactionsError}</p>}
      {!transactionsError && transactions === null && <p>Loading transactions...</p>}
      {transactions !== null && transactions.length === 0 && <p>No transactions yet.</p>}
      {transactions !== null && transactions.length > 0 && (
        <ul>
          {transactions.map((t) => (
            <li key={t.id}>
              {t.transaction_type} {t.ticker} — qty {t.quantity} @ {t.price} (fees {t.fees}) on{" "}
              {new Date(t.occurred_at).toLocaleString()} [{t.source}]
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
