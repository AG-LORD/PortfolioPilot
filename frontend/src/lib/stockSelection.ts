import type { RecommendationRequest } from "@/lib/types/api";

export type StockSelection = { mode: "nifty50" } | { mode: "custom"; tickers: string[] };

export const DEFAULT_SELECTION: StockSelection = { mode: "nifty50" };

function storageKey(portfolioId: string) {
  return `pp:selection:${portfolioId}`;
}

export function loadSelection(portfolioId: string): StockSelection {
  try {
    const raw = window.localStorage.getItem(storageKey(portfolioId));
    if (!raw) return DEFAULT_SELECTION;
    const parsed = JSON.parse(raw) as Partial<{ mode: string; tickers: unknown }>;
    if (
      parsed.mode === "custom" &&
      Array.isArray(parsed.tickers) &&
      parsed.tickers.length > 0 &&
      parsed.tickers.every((ticker) => typeof ticker === "string")
    ) {
      return { mode: "custom", tickers: parsed.tickers as string[] };
    }
  } catch {
    // Corrupt or unavailable storage falls back to the whole NIFTY 50.
  }
  return DEFAULT_SELECTION;
}

export function saveSelection(portfolioId: string, selection: StockSelection) {
  try {
    window.localStorage.setItem(storageKey(portfolioId), JSON.stringify(selection));
  } catch {
    // Storage can be unavailable (private mode); the default selection is used instead.
  }
}

export function isSelectionValid(selection: StockSelection): boolean {
  return selection.mode === "nifty50" || selection.tickers.length > 0;
}

export function selectionToRequest(selection: StockSelection): RecommendationRequest {
  return selection.mode === "custom"
    ? { universe: null, tickers: selection.tickers, return_model: "ml" }
    : { universe: "NIFTY50", tickers: null, return_model: "ml" };
}
