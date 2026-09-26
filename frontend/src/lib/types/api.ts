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
  };
  excluded: Array<{ ticker: string; reason: string }>;
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
};

export type PortfolioOverview = {
  totals: OverviewTotals;
  portfolios: PortfolioOverviewItem[];
};
