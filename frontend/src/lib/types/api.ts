export type ReturnModel = "ml" | "historical";

export type RecommendationRequest = {
  universe: "NIFTY50";
  tickers: null;
  return_model: ReturnModel;
};

export type RecommendationAllocation = {
  ticker: string;
  expected_return: string;
  target_weight: string;
  amount: string;
  at_position_limit: boolean;
  source: ReturnModel;
};

export type RecommendationHistoryItem = {
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
