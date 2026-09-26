"use client";

import { useEffect, useState } from "react";
import { apiFetch, getAccessToken } from "@/lib/api";
import { getErrorMessage } from "@/lib/errors";
import { formatPercent } from "@/lib/format";
import type { StockSelection } from "@/lib/stockSelection";
import type { UniverseRead } from "@/lib/types/api";

type Props = {
  value: StockSelection;
  onChange: (selection: StockSelection) => void;
  maxPositionWeight?: number | string | null;
};

export function StockSelector({ value, onChange, maxPositionWeight }: Props) {
  const [universeTickers, setUniverseTickers] = useState<string[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function loadUniverse() {
      try {
        const accessToken = await getAccessToken();
        if (!accessToken) throw new Error("You are signed out. Please log in again.");
        const universes = await apiFetch<UniverseRead[]>("/universes", accessToken);
        const nifty = universes.find((universe) => universe.name === "NIFTY50");
        if (!nifty) throw new Error("The NIFTY 50 stock list is not available.");
        if (!cancelled) setUniverseTickers([...nifty.tickers].sort());
      } catch (err) {
        console.error("Failed to load NIFTY 50 tickers:", err);
        if (!cancelled) setLoadError(getErrorMessage(err, "We couldn't load the NIFTY 50 stock list."));
      }
    }
    void loadUniverse();
    return () => {
      cancelled = true;
    };
  }, []);

  const selected = value.mode === "custom" ? value.tickers : [];
  const selectedSet = new Set(selected);
  const query = search.trim().toUpperCase();
  const visibleTickers = (universeTickers ?? []).filter((ticker) => ticker.includes(query));

  function setTickers(tickers: string[]) {
    onChange({ mode: "custom", tickers });
  }

  function toggle(ticker: string) {
    setTickers(selectedSet.has(ticker) ? selected.filter((item) => item !== ticker) : [...selected, ticker]);
  }

  return (
    <div className="stock-selector">
      <div className="option-grid" role="radiogroup" aria-label="Stocks to analyze">
        <button
          type="button"
          role="radio"
          aria-checked={value.mode === "nifty50"}
          className={`option-card ${value.mode === "nifty50" ? "selected" : ""}`}
          onClick={() => onChange({ mode: "nifty50" })}
          style={{ textAlign: "left" }}
        >
          <span className="option-title">Use all NIFTY 50</span>
          <span className="option-body">Let PortfolioPilot consider every stock in the index.</span>
        </button>
        <button
          type="button"
          role="radio"
          aria-checked={value.mode === "custom"}
          className={`option-card ${value.mode === "custom" ? "selected" : ""}`}
          onClick={() => onChange({ mode: "custom", tickers: selected })}
          style={{ textAlign: "left" }}
        >
          <span className="option-title">Pick stocks</span>
          <span className="option-body">Choose the NIFTY 50 stocks you want considered.</span>
        </button>
      </div>

      {maxPositionWeight !== undefined && maxPositionWeight !== null && (
        <p className="field-hint">
          Your profile caps each stock at {formatPercent(maxPositionWeight)}. Choosing only a few stocks leaves more capital in cash.
        </p>
      )}

      {value.mode === "custom" && (
        <div className="stock-picker">
          {loadError && <div className="notice error" role="alert">{loadError}</div>}
          {!loadError && universeTickers === null && <p className="utility-text">Loading NIFTY 50 stocks…</p>}
          {universeTickers !== null && (
            <>
              <div className="stock-picker-toolbar">
                <input
                  className="text-input"
                  type="search"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search tickers"
                  aria-label="Search NIFTY 50 tickers"
                />
                <span className="stock-picker-count" aria-live="polite">Selected: {selected.length}</span>
                <button type="button" className="ghost-button" onClick={() => setTickers(universeTickers)}>
                  Select all
                </button>
                <button type="button" className="ghost-button" onClick={() => setTickers([])}>
                  Clear
                </button>
              </div>

              {selected.length > 0 ? (
                <ul className="stock-chips" aria-label="Selected stocks">
                  {selected.map((ticker) => (
                    <li key={ticker} className="stock-chip">
                      {ticker}
                      <button type="button" aria-label={`Remove ${ticker}`} onClick={() => toggle(ticker)}>×</button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="field-hint" role="status" style={{ color: "var(--danger)" }}>Select at least 1 stock.</p>
              )}

              <div className="stock-grid">
                {visibleTickers.map((ticker) => (
                  <label key={ticker} className={`stock-option ${selectedSet.has(ticker) ? "selected" : ""}`}>
                    <input type="checkbox" checked={selectedSet.has(ticker)} onChange={() => toggle(ticker)} />
                    <span>{ticker}</span>
                  </label>
                ))}
                {visibleTickers.length === 0 && <p className="utility-text">No tickers match “{search}”.</p>}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
