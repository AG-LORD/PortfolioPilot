export type ReturnModel = "ml" | "historical";

// Mirrors backend RecommendationRequest: exactly one of universe or tickers is set.
export type RecommendationRequest =
  | { universe: string; tickers: null; return_model: ReturnModel }
  | { universe: null; tickers: string[]; return_model: ReturnModel };

export type UniverseRead = {
  name: string;
  as_of: string | null;
  tickers: string[];
  configured: boolean;
};

// Local ablation: annualized change in the estimate if this input were at its training median.
export type AllocationDriver = {
  feature: string;
  value: string;
  contribution: string;
};

export type RecommendationAllocation = {
  ticker: string;
  expected_return: string;
  target_weight: string;
  amount: string;
  at_position_limit: boolean;
  source: ReturnModel;
  // Optional: older saved recommendations predate these fields.
  clipped?: boolean;
  drivers?: AllocationDriver[];
  typical_estimate?: string | null;
  // Display label from the backend's sectors.json; null when unknown.
  sector?: string | null;
  // The shrunk estimate the optimizer used (expected_return is the model's own); null on older snapshots.
  expected_return_used?: string | null;
  // Why the stock didn't get more weight; null when no limit was binding.
  limit_reason?: "position_limit" | "sector_limit" | null;
};

// negative_estimate: expected to fall; sector_limit: its sector's cap is binding;
// risk_tradeoff: more risk than return at the profile's risk level.
// risk_limit only appears on recommendations saved before the mean-variance optimizer.
export type NotSelectedReason = "negative_estimate" | "sector_limit" | "risk_tradeoff" | "risk_limit";

export type NotSelectedItem = {
  ticker: string;
  sector: string | null;
  expected_return: string;
  source: ReturnModel;
  reason: NotSelectedReason;
  expected_return_used?: string | null;
};

export type RecommendationSummary = {
  id: string;
  created_at: string;
  universe: string;
  return_model: ReturnModel;
  model_version: string | null;
  capital: string;
  cash_weight: string;
  expected_portfolio_return: string;
  expected_portfolio_volatility: string;
};

export type Recommendation = {
  id?: string;
  created_at?: string;
  portfolio_id: string;
  universe: string;
  universe_as_of: string | null;
  return_model: ReturnModel;
  model_version: string | null;
  forecast_as_of: string | null;
  // Nightly stored forecasts vs. a model fitted on request; null when historical only.
  forecast_source?: "precomputed" | "on_request" | null;
  capital: string;
  allocations: RecommendationAllocation[];
  cash_weight: string;
  cash_amount: string;
  expected_portfolio_return: string;
  expected_portfolio_volatility: string;
  constraints: {
    max_position_weight: string;
    target_volatility: string;
    // The profile's sector cap; null when unknown.
    max_sector_weight?: string | null;
  };
  excluded: Array<{ ticker: string; reason: string }>;
  // Eligible stocks the optimizer gave zero weight. null on recommendations saved before
  // this existed (unknown), [] when nothing was left out.
  not_selected?: NotSelectedItem[] | null;
};

export type RebalanceTrade = {
  ticker: string;
  side: "BUY" | "SELL";
  quantity: number;
  estimated_price: string;
  estimated_gross_amount: string;
  estimated_fee: string;
  estimated_net_amount: string;
  current_weight: string;
  target_weight: string;
  resulting_weight: string;
};

export type RebalanceWeight = {
  ticker: string;
  current_weight: string;
  target_weight: string;
  resulting_weight: string;
};

export type RebalanceProposalRequest = {
  recommendation_id: string | null;
};

export type RebalanceProposal = {
  id: string;
  portfolio_id: string;
  recommendation_id: string;
  created_at: string;
  status: "PENDING" | "EXECUTED" | "EXPIRED";
  portfolio_value: string;
  cash_before: string;
  projected_cash: string;
  buy_total: string;
  sell_total: string;
  estimated_fees: string;
  fee_assumption: string;
  trades: RebalanceTrade[];
  resulting_weights: RebalanceWeight[];
};

export type OverviewTotals = {
  portfolio_count: number;
  initial_capital: string;
  cash_balance: string;
  market_value: string | null;
  total_value: string | null;
  unrealized_pnl: string | null;
  valued_portfolio_count?: number;
};

export type PortfolioOverviewItem = {
  id: string;
  name: string;
  risk_category: string;
  initial_capital: string;
  cash_balance: string;
  valuation_status: "ok" | "unavailable";
  market_value: string | null;
  total_value: string | null;
  unrealized_pnl: string | null;
  unrealized_pnl_pct: string | null;
  holdings_count: number;
  latest_recommendation: RecommendationSummary | null;
  // initial_capital plus every later deposit (net of fees).
  total_deposited: string | null;
  // Last change to cash or holdings.
  updated_at: string | null;
  adopted_recommendation_id: string | null;
  adopted_at: string | null;
  // total_value of the last 30 daily snapshots, oldest first; empty with fewer than 2.
  sparkline: string[];
};

export type PortfolioOverview = {
  totals: OverviewTotals;
  portfolios: PortfolioOverviewItem[];
};

export type Portfolio = {
  id: string;
  user_id: string;
  risk_profile_id: string;
  name: string;
  purpose: string | null;
  base_currency: string;
  initial_capital: string;
  cash_balance: string;
  // The recommendation adopted as the plan; null when none.
  adopted_recommendation_id: string | null;
  adopted_at: string | null;
  created_at: string;
  updated_at: string;
};

export type Transaction = {
  id: string;
  portfolio_id: string;
  ticker: string;
  transaction_type: "BUY" | "SELL" | "DEPOSIT";
  quantity: string;
  price: string;
  fees: string;
  occurred_at: string;
  created_at: string;
  source: string;
};

export type HoldingValuation = {
  ticker: string;
  quantity: string;
  average_cost: string;
  current_price: string;
  market_value: string;
  unrealized_pnl: string;
  sector: string | null;
};

export type PortfolioValuation = {
  portfolio_id: string;
  cash_balance: string;
  invested_value: string;
  total_value: string;
  unrealized_pnl: string;
  holdings: HoldingValuation[];
};

export type RiskAnalytics = {
  portfolio_id: string;
  observation_count: number;
  first_snapshot_date: string | null;
  last_snapshot_date: string | null;
  cumulative_return: string | null;
  annualized_volatility: string | null;
  max_drawdown: string | null;
  sharpe_ratio: string | null;
  risk_free_rate_annual: string;
  historical_var: string | null;
  historical_cvar: string | null;
  var_confidence: string;
  message: string | null;
};

// POST /portfolios/{id}/transactions/batch: 1-50 rows, recorded all or nothing.
export type BatchTradeItem = {
  side: "BUY" | "SELL";
  ticker: string;
  quantity: string;
  price: string;
  fees: string;
};

export type HistoryPreview = {
  start: string;
  end: string;
  points: Array<{ date: string; mix: string; benchmark: string }>;
  // Hindsight context with today's weights; not a backtest or forecast.
  note: string;
};

export type PortfolioPerformance = {
  // Empty with fewer than 2 daily snapshots.
  points: Array<{ date: string; portfolio: string; benchmark: string | null }>;
};

export type DriftPosition = {
  ticker: string;
  quantity: string | null;
  current_price: string | null;
  current_value: string | null;
  // Share of the portfolio's current value; null when a price is missing.
  current_weight: string | null;
  target_weight: string | null;
  weight_difference: string | null;
  status: "no_target" | "unavailable" | "overweight" | "underweight" | "at_target";
  excluded: boolean;
  exclusion_reason: string | null;
  requires_attention: boolean;
};

export type PortfolioDrift = {
  portfolio_id: string;
  portfolio_value: string | null;
  valuation_complete: boolean;
  missing_prices: string[];
  target_recommendation_id: string | null;
  target_created_at: string | null;
  target_status: "missing" | "current" | "stale";
  drift_threshold: string;
  attention_count: number;
  positions: DriftPosition[];
};
