# ML Methodology

This document describes how PortfolioPilot builds features and labels, and
how return-forecasting models are evaluated against a historical-mean
baseline. Code: `backend/app/services/features.py` (features, label, panel)
and `backend/app/ml/` (splits, models, baseline, metrics, evaluation).
Live recommendations can use the ML model (`return_model = "ml"`); see section 9.
Research-only feature groups and their ablation are in section 13.

## 1. Data

- Daily OHLCV per NSE ticker from yfinance with `auto_adjust=True`: open, high, low and close are all adjusted for splits and dividends on the same basis, so returns and ranges are consistent across corporate actions.
- Prices are read through the persistent price cache (`daily_prices`). Cached history is re-fetched in full when it may have been re-based by a corporate action (see the cache documentation in `app/services/price_history.py`).
- One row is one trading day. "k days" below always means k trading-day rows, not calendar days.

## 2. Features

All features are computed per ticker from that ticker's own series, sorted by date. Every window length is a named constant in `features.py`.

| Feature | Formula at date t | Window | Why scale-free |
|---|---|---|---|
| `close_to_sma_20` | close_t / SMA20_t − 1 | 20 | ratio of prices |
| `close_to_sma_50` | close_t / SMA50_t − 1 | 50 | ratio of prices |
| `sma_20_to_sma_50` | SMA20_t / SMA50_t − 1 | 20, 50 | ratio of prices |
| `momentum_5` | close_t / close_{t−5} − 1 | 5 | ratio of prices |
| `momentum_20` | close_t / close_{t−20} − 1 | 20 | ratio of prices |
| `momentum_60` | close_t / close_{t−60} − 1 | 60 | ratio of prices |
| `rsi_14` | 100 · G_t / (G_t + L_t), Wilder-smoothed average gain G and loss L of daily close changes (50 when both are 0) | 14 | ratio of price changes |
| `macd_line` | (EMA12_t − EMA26_t) / close_t | 12, 26 | EMAs are linear in price; divided by price |
| `macd_signal` | EMA9(MACD line)_t / close_t | 9 | as above |
| `macd_hist` | (MACD line_t − signal_t) / close_t | 12, 26, 9 | as above |
| `atr_14` | Wilder-smoothed true range_t / close_t | 14 | range divided by price |
| `realized_vol_20` | sample std (ddof 1) of the last 20 daily returns × √252 | 20 | uses returns only |

Definitions:
- SMA_n: simple mean of the last n closes, including t.
- EMA_s: exponential moving average, α = 2/(s+1), started at the series' first close (`adjust=False`).
- Wilder smoothing (window n): seeded with the plain mean of the first n values, then avg_t = (avg_{t−1}·(n−1) + x_t)/n.
- True range_t = max(high_t − low_t, |high_t − close_{t−1}|, |low_t − close_{t−1}|). It starts at the second row because it needs a previous close.
- Daily return_t = close_t / close_{t−1} − 1. 252 is the same annualization factor used in risk analytics.

Because every feature is a ratio of prices or a function of returns, multiplying all prices by a constant leaves it unchanged. That lets one model be trained across all stocks, whatever their price level.

## 3. Point-in-time rule

A feature at date t uses only rows dated ≤ t:
- Only trailing windows: no centered windows, no backfill, no negative shifts, and no full-series statistics (no global mean/std normalization).
- Warm-up rows, where any window is still incomplete, are dropped and never filled. The warm-up is `WARMUP_ROWS` = 60 rows (set by the longest window, the 60-day momentum). `compute_features` produces its first row from 61 rows of prices; panels require more history (see below).
- Normalization happens only inside the model pipeline, fitted on the training fold (section 6).

Evidence (tests in `backend/tests/test_features.py`):
- **Truncation invariance:** for every feature, values for all dates ≤ T are bit-identical whether computed on data ending at T or on data extended beyond T.
- **Future shocks:** tripling all prices after a cutoff leaves every earlier feature bit-identical.
- **Scale invariance:** prices × 4 give bit-identical features; prices × 3.7 agree to a relative 1e-10.
- **The test detects leaks:** replacing the SMA with a centered window makes the truncation test fail (checked manually during development).

Caveat: EMA and Wilder smoothers are recursive and start at the first row of the series they are given. A value at t therefore also depends, with exponentially decaying weight, on where the fetched series *starts*. It never depends on later data. At the first row after the 60-row warm-up, the starting values would still carry about 1% of the weight in MACD's EMA26 ((25/27)^60) and about 3% in the Wilder-smoothed RSI and ATR ((13/14)^46).

To make this negligible, every panel row (for forecasting and evaluation alike) requires `MIN_FEATURE_HISTORY` = 252 trading days of history before its date, the same as the baseline lookback. At that point the starting values' weight is about 4·10⁻⁹ for EMA26 ((25/27)^252) and about 2·10⁻⁸ for RSI/ATR ((13/14)^238).

`compute_features` itself still only drops the 60-row warm-up. The 252-day rule is enforced where panels are built (`build_panel_from_prices`, used by both `build_feature_panel` and the evaluation script).

## 4. Label

`label` = forward_return_t = close_{t+h} / close_t − 1, with h = `DEFAULT_HORIZON` = 20 trading days.

- This is the only negative shift in the pipeline, and it is kept out of the features.
- The last h rows of each ticker have no label (NaN). They are usable for prediction but never for training or scoring.

## 5. Panel

`build_feature_panel(db, tickers, start, end, horizon=20)` returns one long table with the columns `date, ticker, <12 features>, label, hist_mean_forecast`.

- It reads prices through the cache. The same in-memory builder, `build_panel_from_prices`, is used by the offline evaluation script (section 8).
- Rows start at a ticker's 253rd trading day, so each has at least `MIN_FEATURE_HISTORY` = 252 days of history before it (section 3). The baseline is therefore available on every panel row.
- Tickers with no data, or fewer than 253 rows, are excluded with a reason, in the same style as recommendations.
- Training rows also start at day 253. That discards some early training data in exchange for features that do not depend on the series start.

## 6. Walk-forward evaluation

**Splits** (`app/ml/splits.py`), with `N_TEST_BLOCKS` = 5 by default:
- The sorted unique dates are cut into n_blocks + 1 equal chunks. Chunk 0 is only ever used for training; chunks 1…n are the test blocks. The last test block also takes any remainder, so the test blocks cover every date after chunk 0 exactly once.
- The training window expands: test block i trains on all dates before it…
- …except the last h dates before the block (the purge gap). A training row's label looks h days ahead, so without the purge the last training labels would overlap the test period. With it, every training label ends strictly before the test block starts.
- Only rows with a label are used for training and scoring.

**Models** (`app/ml/models.py`) are sklearn Pipelines, so any scaling is fit only on the training fold. The hyperparameters are fixed constants chosen before any evaluation, and there is no tuning on test data.

| Model | Pipeline | Fixed hyperparameters |
|---|---|---|
| `ridge` | StandardScaler → Ridge | `alpha = 1.0` |
| `hist_gradient_boosting` | HistGradientBoostingRegressor (trees need no scaling) | `learning_rate = 0.05`, `max_iter = 200`, `max_depth = 3`, `min_samples_leaf = 50`, `l2_regularization = 1.0`, `early_stopping = False`, `random_state = 0` |

Early stopping is disabled because it would hold out a random validation slice of the training fold. With it off, each fold trains on all its rows and results are fully deterministic.

**Baseline** (`app/ml/baseline.py`), `historical_mean`:
- forecast_t = h × arithmetic mean of the daily returns over the trailing 252 trading days, up to and including t.
- The live `HistoricalMeanProvider` uses exactly this definition (it calls the same function), in annual units: 252 × the mean of the last 252 daily returns. The baseline here is that value rescaled to the 20-day horizon, so it is compared on the same target.
- Rows without 252 trailing returns get no baseline forecast.

**Common scoring set:** every model, baseline included, is scored on the same rows: test-block rows that have both a label and a baseline forecast. Otherwise the baseline would be scored on fewer, later dates than the ML models.

## 7. Metrics

Metrics are computed over all scored rows of all test blocks (`app/ml/metrics.py`):
- **MAE:** mean |forecast − realized forward return|.
- **Hit rate:** share of rows where sign(forecast) = sign(realized). Rows with a realized return of exactly 0 are excluded, since there is no direction to hit. A forecast of exactly 0 counts as a miss.
- **Mean IC:** on each test date, the Spearman rank correlation between forecasts and realized returns across tickers, then averaged over dates. A date is skipped if it has fewer than `MIN_IC_TICKERS` = 5 tickers, or if either side is constant (rank correlation undefined).

`evaluate_models(panel)` returns one result per model with the fields `model, mae, hit_rate, mean_ic, test_blocks, as_of`, matching the `GET /ml/evaluation` response.
- `as_of` is the last scored date.
- If a metric is undefined on the scored rows (for example, no date has 5 tickers), evaluation raises an error instead of returning a partial result.

Tests on synthetic panels (`backend/tests/test_ml.py`):
- Splits keep training dates before test dates, with a gap of at least h, and test blocks cover the dates without overlap.
- The fitted scaler's mean equals the training-fold mean.
- The baseline is truncation invariant.
- A perfect forecast gives IC = 1 and hit rate = 1; reversed ranks give IC = −1; MAE matches a hand calculation.
- Results are deterministic.
- On a panel where one feature truly drives the label, IC ≈ 0.6. On pure noise, |IC| < 0.02.

## 8. Offline evaluation script

`backend/scripts/run_evaluation.py` runs the full evaluation on real prices. From `backend/`:

```
python -m scripts.run_evaluation --tickers RELIANCE,TCS,INFY,HDFCBANK,ICICIBANK --no-cache
python -m scripts.run_evaluation --universe NIFTY50 --start 2019-01-01 --blocks 5 --horizon 20
```

- **Arguments:** `--universe` or `--tickers` (exactly one); `--start` (default 2019-01-01); `--end` (inclusive, default the last completed IST trading day); `--blocks` (default 5); `--horizon` (default 20).
- **`--no-cache`:** fetches prices with one batched yfinance download into memory. It never imports the database layer; the run checks this and fails otherwise. Without the flag, prices are read through the price cache in `DATABASE_URL`, and newly fetched prices are stored there.
- **Output:** a metrics table, per-block mean IC per model, and a data summary (date ranges, tickers used, tickers excluded with reasons, scored rows). The same report is written to `backend/results/evaluation_<run date>.json` (not committed).
- **IC standard error:** the report adds std(daily IC) / √(number of IC dates) per model. It treats daily ICs as independent, but consecutive 20-day labels overlap, so daily ICs are autocorrelated and this standard error is optimistic. It is reported for context only, not as a significance test. Example: on synthetic random-walk prices with 6 tickers, one model showed a mean IC of −0.23 with a naive standard error of 0.034, which is pure noise.

## 9. Live expected-return providers

`POST /portfolios/{id}/recommendation` takes `return_model` = `historical` or `ml`. The code is in `backend/app/services/return_providers.py`. Both providers return **annualized arithmetic** expected returns (mean daily return × 252), the unit the optimizer uses. Covariance is the same for both: Ledoit-Wolf on the last 252 common daily returns, annualized.

- **HistoricalMeanProvider:** 252 × the mean of each ticker's last 252 daily returns. This is the evaluation baseline (section 6) in annual units. Earlier versions used every return in a 365-calendar-day window and accepted as few as 31 days; that was standardized to this definition. A ticker now needs 253 prices.
- **MLForecastProvider** runs per request, with no persistence:
  1. Load about 6 years of prices through the price cache.
  2. Build the point-in-time panel (section 5).
  3. Fit the fixed-hyperparameter HistGradientBoosting model on every row whose label is already known, meaning labels ending on or before the latest price date.
  4. Predict each ticker's feature row on the latest panel date.
  5. Clip r₂₀ to the training-label range (signal control, below).
  6. Convert the 20-day forecast r₂₀ to annual units as r₂₀ × 252 / 20. This arithmetic scaling matches the historical provider's convention; it is not compounding.
- **Fallback:** a ticker with no feature row on the latest date, or a non-finite forecast, falls back to its historical estimate, recorded per ticker as `source = "historical"`. With fewer than 500 labelled training rows, no model is trained and every ticker is historical.
- **Metadata:** `model_version` is the fixed string `hist_gradient_boosting-h20-f12-v1` (model, horizon, feature count, version), so identical inputs give identical outputs. `forecast_as_of` is the latest panel date.
- **Signal control (clipping):** each raw 20-day forecast is clipped to the [`CLIP_LOWER_Q`, `CLIP_UPPER_Q`] = [0.01, 0.99] quantiles of the **training labels of that fit** (the labelled rows the model was trained on, so the bounds are point-in-time and never use the rows being forecast), then annualized as above. The response marks such tickers `clipped: true` (default `false`). Clipping guards against extreme outputs, capping extrapolation beyond the range of 20-day returns the model has seen. It was not binding in the observed fits (a synthetic 6-ticker fit had bounds of −16.1% to +17.4% over 20 days and clipped none of the 6 forecasts). It is not a calibration step and does not make an in-range forecast more accurate.
- **Per-stock explanations (local ablation):** for every ML-sourced ticker, and for each of the 12 features, the contribution is the model's prediction with the ticker's actual features minus its prediction with that one feature replaced by its **training-set median**, annualized × 252 / 20 (the `expected_return` unit). `typical_estimate` is the annualized prediction with every feature at its training median. The response carries `drivers: [{feature, value, contribution}]` (all 12, sorted by |contribution| descending) and `typical_estimate`; historical-fallback tickers get `drivers = []` and `typical_estimate = null`. Both are stored in the recommendation snapshot.
  - Contributions use the unclipped prediction, and they are approximate: because of feature interactions, they need not add up to `expected_return − typical_estimate` (or to anything).
  - They explain **the model, not the market**: a large contribution says the model's estimate for this stock moves a lot when that input is set to a typical value, not that the input causes returns.
  - The computation is deterministic (a fixed-seed model and fixed medians), and a feature exactly at its training median contributes 0.
- **Nightly precomputed forecasts:** `backend/scripts/nightly_jobs.py` runs after the close on trading weekdays. It trains the model **once on the pooled NIFTY 50 panel** with `fit_and_forecast()`, the same feature, label, clipping and attribution code as on-request forecasts, and upserts one row per ticker into `ml_forecasts`, keyed by (ticker, `as_of` = latest feature date, horizon, `model_version`), with the training window and row count. Storing forecasts per day with a model version makes same-day recommendations reproducible: every request that day uses the same numbers.
- **Fast path:** for `return_model = "ml"`, the stored forecasts for the latest completed trading weekday and the current `model_version` are used for the requested tickers without training. If any requested ticker has no stored forecast (a custom ticker outside NIFTY 50, or no nightly run yet that day), the model is fitted on request on the requested tickers' panel, as before, and the stored values are kept for the tickers that have them. The response's `forecast_source` is `"precomputed"` when every ML forecast came from the store and `"on_request"` otherwise (null when historical only). **On-request training on a user's subset uses a different training panel than the pooled nightly model, so its forecasts can differ for the same stock and day; that is why the source is shown.**
- **Model choice:** HistGradientBoosting was chosen because it had the highest mean IC in the NIFTY 50 evaluation below. That selection used the evaluation period, so its IC there is not an independent out-of-sample estimate for the chosen model.

## 10. Optimizer (portfolio construction)

Code: `backend/app/services/optimization.py`. The optimizer turns the expected returns (section 9) and the Ledoit-Wolf covariance Σ into target weights. Cash is an explicit variable with zero return and zero risk, so "all cash" is always a feasible answer and a tight profile never makes the problem infeasible.

**Objective (default `mean_variance`):** maximize μₛᵀw − (λ/2)·wᵀΣw. λ is the risk aversion of the profile: conservative 8, moderate 4, aggressive 2 (`RISK_AVERSION`). The previous objective, maximize μₛᵀw, is kept as `objective="max_return"` for comparison; the backtest endpoint still uses it without shrinkage because backtest requests carry no risk profile.

**Constraints:**
- weights + cash = 1, cash ≥ 0;
- 0 ≤ wᵢ ≤ `max_position_weight`;
- portfolio volatility √(wᵀΣw) ≤ `target_volatility` (solved as a variance constraint);
- for every sector, Σ wᵢ in that sector ≤ `max_sector_weight`, with sectors from `backend/app/data/sectors.json`; a ticker without a sector is its own one-ticker sector;
- a ticker whose own estimate is ≤ 0 gets weight 0 (see shrinkage);
- no position below `MIN_POSITION_WEIGHT` = 2% (see minimum position).

**Shrinkage:** before optimizing, μₛ = α·μ + (1−α)·mean(μ) over the eligible tickers, with α = 0.5 (`SHRINKAGE_ALPHA`). This damps noisy forecasts toward the cross-sectional mean without changing their ranking. Because it can lift a negative estimate above zero, a ticker the model expects to fall is still never bought. The response keeps `expected_return` = the model's own estimate and adds `expected_return_used` = μₛ. The plan's estimated return is Σ wᵢ·μₛ,ᵢ, the estimates the optimizer actually used, so the headline figure is as damped as the weights behind it. On the Plan page the per-stock "Estimate" column shows `expected_return_used`, the Why? drawer shows both ("Estimate used for your plan" and "Model's raw estimate"), and the plan metric's tooltip says the estimates are pulled toward the average. The "Considered, not bought" table keeps the model's own estimate, since "Expected to fall" refers to it. Recommendations saved before shrinkage have no `expected_return_used`; they show the raw estimate and their stored plan return (computed with raw estimates) is unchanged.

**Minimum position:** after solving, any stock with a weight in (0, 2%) is fixed to 0 and the problem is re-solved without it, repeating until no such weight remains (at most 5 re-solves; anything still left is moved to cash directly, scaling the stock weights down if that raised volatility). Removing stocks keeps "all cash" feasible, so the feasibility guarantee holds, and every re-solve applies the full constraint set. A position that small is not worth an order: at ₹1 lakh, 1% is ₹1,000, often less than one share. Removed stocks are reported as `too_small`. Backtests pass `min_position_weight=0` so they stay comparable with earlier runs.

**Why mean-variance:** maximizing return under caps fills the highest-estimate stocks to their caps in order, ignoring how risky or correlated they are. The variance penalty spreads weight toward stocks with a better return per unit of risk, and a higher λ gives a lower-volatility portfolio for the same inputs. When the volatility cap binds, the penalty is the same everywhere on that boundary, so both objectives can give the same portfolio (the conservative profile in the sensitivity report below).

**Reasons reported:**
- Not selected: `negative_estimate` (estimate ≤ 0), `too_small` (removed by the minimum position), `sector_limit` (its sector's cap is binding), else `risk_tradeoff` (it adds more risk than return for the profile). Snapshots from before this optimizer may carry `risk_limit`.
- Selected: `limit_reason` = `position_limit` (at the per-stock cap), `sector_limit` (its sector's cap is binding) or null.

**Sensitivity report:** `python -m scripts.objective_sensitivity` (run from `backend/`, no database writes) prints, for NIFTY 50 and each profile, both objectives' number of holdings, largest and smallest weight, cash, ex-ante return (with the shrunk estimates, as on the plan) and volatility, number of sectors, number of stocks dropped as too small and a "min w ok" check that no weight is below 2%, plus a λ grid (1, 2, 4, 8, 16) for the moderate profile.

## 11. Results: NIFTY 50

Source file: `backend/results/evaluation_2026-09-25.json` (gitignored). Produced by `python -m scripts.run_evaluation --universe NIFTY50 --no-cache`.

**Settings:**
- Universe: the official NIFTY 50 list retrieved 2026-09-25 (revision recorded in the file).
- Prices: 2019-01-01 to 2026-09-24, in memory (no database).
- Walk-forward: 5 test blocks, 20-day horizon.

**Data:**
- All 50 tickers used.
- 80,970 feature rows (2020-01-14 to 2026-09-24).
- 67,139 scored rows (2021-02-16 to 2026-08-27).

| Model | MAE | Hit rate | Mean IC | IC s.e.* |
|---|---|---|---|---|
| historical_mean | 0.0601 | 0.5378 | 0.0274 | 0.0059 |
| ridge | 0.0596 | 0.5249 | 0.0237 | 0.0052 |
| hist_gradient_boosting | 0.0617 | 0.5267 | 0.0515 | 0.0047 |

\* Naive standard error; optimistic because 20-day labels overlap (section 8).

Per-block mean IC:

| Block | Dates | historical_mean | ridge | hist_gradient_boosting |
|---|---|---|---|---|
| 1 | 2021-02-16 to 2022-03-24 | 0.0462 | −0.0715 | 0.0196 |
| 2 | 2022-03-25 to 2023-05-03 | −0.0510 | 0.0391 | 0.0561 |
| 3 | 2023-05-04 to 2024-06-12 | 0.1616 | 0.1362 | 0.1260 |
| 4 | 2024-06-13 to 2025-07-17 | −0.0512 | 0.0071 | 0.0621 |
| 5 | 2025-07-18 to 2026-08-27 | 0.0313 | 0.0079 | −0.0053 |

**Reading these results:**
- **Weak signal:** all ICs are small, and they vary a lot from block to block.
- **HistGradientBoosting** has the highest mean IC and is positive in 4 of 5 blocks, but its MAE is the worst of the three.
- **Ridge** has the lowest MAE but the lowest mean IC.
- **The historical baseline** has the best hit rate. That is consistent with mostly positive trailing means during a rising market.
- These are forecast metrics only. They say nothing yet about the performance of optimized portfolios.

## 12. Known limitations

- **No NSE holiday calendar:** `is_trading_weekday` only knows Monday–Friday. On an exchange holiday the nightly job still runs (the latest feature date is then the previous session, so its stored `as_of` does not match the "latest completed trading weekday" and requests that day fall back to on-request training), and the snapshot script records a snapshot with unchanged prices.
- **Overlapping labels:** 20-day forward returns on consecutive days overlap, so daily metric observations are autocorrelated. The IC standard error in the evaluation report is computed naively and is therefore too small. No significance tests are reported yet.
- **Survivorship bias:** evaluating on today's index constituents over past dates favors stocks that survived into the index. The universe file records the date of its constituent list (`as_of`).
- **One calendar:** splits use the union of dates in the panel and assume all tickers trade on the NSE calendar.
- **Symbol history from yfinance:** some current symbols carry predecessor history. `TMPV` (Tata Motors passenger vehicles, demerged in 2025) returns prices back to 2019, i.e. the pre-demerger Tata Motors series. `ETERNAL` (renamed from Zomato) starts at the 2021 listing. `JIOFIN` starts at its 2023 listing. Pre-event history under a new symbol, and any unadjusted demerger jump, can distort features and labels for those tickers.
- **The universe is fixed at its retrieval date:** the same 50 names are used for every past date (see survivorship bias above).
- **Recursive smoothers depend on the series start** (section 3). `MIN_FEATURE_HISTORY` = 252 makes this negligible for panel rows, at the cost of the first year of each ticker's history.

## 13. Research feature groups (offline only; not used by the live model)

Code: `backend/app/ml/feature_groups/` and `backend/app/ml/ablation.py`. These groups test whether causally built market-structure, chart-pattern, accumulation/distribution and price-geometry features improve 20-day return forecasts beyond the 12 technical features. **None of them is used by live recommendations.** `return_providers.py`, `ML_MODEL_VERSION` (`hist_gradient_boosting-h20-f12-v1`), stored forecasts, the API and the optimizer are unchanged. Changing the live feature set needs the results below plus explicit approval.

### 13.1 Registry

- `registry.py` maps a group name to its columns and a `compute(prices)` function on one ticker's OHLCV frame.
- `build_panel_from_prices(..., groups=...)` and `run_walk_forward(..., feature_columns=...)` accept a configuration. The defaults (`groups=None`, `FEATURE_COLUMNS`) are the original code path.
- **Zero-change check:** on the same downloaded NIFTY 50 prices (2019-01-01 to 2026-09-29), the refactored code produced a panel and walk-forward predictions identical to the pre-refactor code (`assert_frame_equal`, exact).

| Group | Columns | Module |
|---|---|---|
| `technical` | 12 | the existing `FEATURE_COLUMNS` |
| `dow` | 37 | `dow.py` |
| `patterns` | 39 | `patterns.py` |
| `accdist` | 13 | `accumulation.py` |
| `geometry` | 20 | `geometry.py` |
| `fibonacci` | 1 | `geometry.py`; descriptive, excluded from configurations A–G |

The exact formula, window, denominator and missing-value rule for every column are in each module's docstring. They are summarised below.

### 13.2 Causal pivots (`pivots.py`)

- **Rule:** a fractal pivot of order k.
  - Pivot high: a high strictly above the k bars before it and ≥ the k bars after it.
  - Pivot low: the mirror of that.
  - Ties go to the earliest bar.
- **Confirmation:** a pivot that occurs at bar i is **confirmed at i + k**. Features at bar t use only pivots with `confirmed ≤ t`.
- **Scales:** k = 2, 5 and 10, fixed before evaluation.
- **Alternating swing sequence** (used by the patterns and geometry groups):
  - Built from confirmed pivots in confirmation order.
  - A same-kind pivot replaces the last swing only if it is more extreme.
- **Timestamps:**
  - Pivot occurrence and confirmation are kept separately.
  - A pattern's detection bar is the confirmation bar of its last pivot.
  - Its breakout bar is the first bar whose **close** is beyond the level, evaluated at that bar.

### 13.3 Groups

**Dow Theory** (`dow`), per scale k with counting window W = 20 / 60 / 120 bars:
- trend state from the last confirmed high and low (HH+HL = +1, LH+LL = −1, else 0);
- counts of HH, HL, LH and LL in the window;
- structure strength = (HH + HL − LH − LL) ÷ total;
- signed run length of the current sequence;
- distance to the last swing high and low ÷ ATR14;
- bars since the last confirmation;
- break flag: a close beyond the last confirmed swing against the trend. It is only a flag; the trend state changes only on a new confirmed pivot.
- a structure-present flag;
- plus agreement across the three scales.

**Patterns** (`patterns`, scale k = 5):
- **Patterns:** double top and bottom, head and shoulders and its inverse, ascending, descending and symmetrical triangles, and range.
- **Tolerances** are in ATR units at detection and fixed a priori:
  - "equal" within 0.5 ATR;
  - height ≥ 2 ATR;
  - width 10–120 bars.
- **Lifecycle:** candidate → confirmed on a close beyond the breakout level → shown for 20 bars. A candidate is cancelled on a close beyond its invalidation level, or expires after 40 bars without a breakout.
- **Per-pattern columns:** state, age, boundary distance ÷ ATR, and confidence (mean margin inside each tolerance).
- **Summary columns** for the latest pattern: height, width, symmetry, swing difference, completeness, breakout direction, active count.
- **Flags are not implemented:** defining the "pole" would need thresholds tuned on the evaluated data.

**Accumulation/distribution** (`accdist`), using R = 20, L = 120 and M = 5 bars:
- **Observable features:**
  - range width;
  - `range_position`;
  - Chaikin-style money flow;
  - `volume_imbalance`;
  - relative volume;
  - effort vs result;
  - `volatility_compression`;
  - `breakout_volume_ratio`;
  - `failed_breakout_flag`;
  - distance to the range boundaries ÷ ATR.
- **Scores:** `accumulation_score` and `distribution_score` are fixed equal-weight means of bounded components, in [0, 1]. They describe *accumulation-like* or *distribution-like* conditions. They are not a validated label of who is buying or selling.

**Geometry** (`geometry`):
- slope, R² and acceleration of log price over 20 and 60 bars, normalised by σ = the 60-day std of daily log returns;
- slope change and curvature;
- efficiency ratio over 20 and 60 bars;
- from the k = 5 swings:
  - retracement;
  - log ratios of leg size and duration;
  - leg symmetry;
  - leg height ÷ ATR and leg width;
  - convergence of the support and resistance trendlines;
  - distance to each trendline ÷ ATR.
- `fib_nearest_dist` is a separate descriptive group and is not assumed predictive.

**Numerical rules for every group:**
- A zero or undefined denominator gives a documented neutral value: 0, 0.5 for `range_position`, 1 for `fib_nearest_dist`.
- Ratios are log- or tanh-transformed and clipped.
- Every column is finite from row `MIN_FEATURE_HISTORY` = 252 on. So every configuration has exactly the same panel rows, and the walk-forward refuses non-finite inputs.

### 13.4 Leakage controls and tests

`tests/test_feature_groups.py` runs these checks on every registered group:
- **Future-data invariance:** two series identical through bar t and different afterwards (a −40% price shock and ×5 volume) give exactly the same features through t.
- **Truncation invariance**, exact.
- **Scale invariance** in price and volume.
- **Determinism.**
- **Finite values** after the warm-up.
- **Identical scored rows** across configurations.
- **Label and identifier columns** are rejected as model inputs.

Group tests:
- `test_dow_structure.py`: confirmation delay, ties, synthetic up and down structures, break versus trend.
- `test_patterns.py`:
  - every pattern's constraints, plus near-miss negatives;
  - no detection before the last pivot is confirmed;
  - no confirmation before the breakout close;
  - invalidation, expiry and the 20-bar hold;
  - bar-by-bar truncation.
- `test_accumulation_geometry.py`: bounds, zero volume, flat prices, failed breakouts, known slopes, zero-length legs.
- `test_ablation.py`: the seven configurations, identical rows, and the screening rule.

### 13.5 Ablation (2026-10-12, prices 2019-01-01 to 2026-09-29)

**Which numbers are which.** Every run of the evaluation script downloads prices from Yahoo again, and the downloaded values can differ slightly between runs. HistGradientBoosting itself is deterministic: the same data gave identical results on repeated runs and with 1, 2, 4 or all CPU threads. Its IC is therefore only comparable between runs on the same download.

| Figure | Run | Data |
|---|---|---|
| **0.0523** | Baseline (12 features) and ablation configuration A, **same download** (the table below) | 80,921 panel rows, 67,090 scored |
| 0.0532 | Configuration A in an earlier ablation run on 2026-10-12 | Separate download, same row counts; superseded by the table below |
| 0.0541 | Baseline run on 2026-09-29 | Different download, 81,120 panel rows, 67,242 scored rows, blocks ending 2026-09-01 |
| 0.0515 | Baseline in section 11 (2026-09-25) | Different download, 80,970 panel rows |

**Provenance of the table below:**
- One price download was saved to `backend/results/prices_2026-10-12.pkl` (local, not committed) and fed through the unmodified script.
- The 12-feature baseline run (`evaluation_2026-10-12_same-download.json`) and the ablation run (`ablation_2026-10-12_same-download.json`) both come from it.
- On that data, configuration A's predictions are **exactly identical** to the baseline run's (`assert_frame_equal`, exact). So configuration A **is** the live baseline here.
- Command for a fresh download (from `backend/`): `python -m scripts.run_evaluation --universe NIFTY50 --no-cache --end 2026-09-29 --ablation`.

Setup:
- Same panel, splits (5 expanding blocks, 20-day purge), models and fixed hyperparameters as section 6.
- 67,090 scored rows (2021-02-16 to 2026-08-31), identical for every configuration (checked).
- No embargo was added: training never uses dates after a test block, and the purge already ends every training label before the block.

**Screening rule, agreed before the run:**
- mean IC > the live baseline (A, HistGradientBoosting) + 2 naive s.e., and
- IC > 0 in at least 4 of the 5 blocks.

Passing would only qualify a configuration for confirmation on untouched data. Threshold here: 0.0523 + 2 × 0.0047 = 0.0616.

| Cfg | Groups | # features | Model | MAE | Hit rate | Mean IC | s.e.* | Block-IC sd | IC > 0 blocks | Screen |
|---|---|---|---|---|---|---|---|---|---|---|
| A | technical (live) | 12 | ridge | 0.0597 | 0.5245 | 0.0238 | 0.0052 | 0.0750 | 4 | — |
| | | | hist_gradient_boosting | 0.0618 | 0.5262 | **0.0523** | 0.0047 | 0.0488 | 4 | — |
| B | dow | 37 | ridge | 0.0605 | 0.5476 | 0.0188 | 0.0041 | 0.0351 | 4 | no |
| | | | hist_gradient_boosting | 0.0619 | 0.5490 | 0.0093 | 0.0039 | 0.0234 | 4 | no |
| C | patterns | 39 | ridge | 0.0605 | 0.5565 | 0.0092 | 0.0040 | 0.0284 | 3 | no |
| | | | hist_gradient_boosting | 0.0607 | 0.5562 | 0.0145 | 0.0039 | 0.0179 | 4 | no |
| D | accdist | 13 | ridge | 0.0607 | 0.5294 | 0.0328 | 0.0045 | 0.0427 | 4 | no |
| | | | hist_gradient_boosting | 0.0624 | 0.5141 | 0.0266 | 0.0047 | 0.0319 | 3 | no |
| E | geometry | 20 | ridge | 0.0601 | 0.5548 | −0.0026 | 0.0050 | 0.0452 | 3 | no |
| | | | hist_gradient_boosting | 0.0617 | 0.5474 | 0.0172 | 0.0047 | 0.0321 | 4 | no |
| F | all four new groups | 109 | ridge | 0.0642 | 0.5183 | 0.0320 | 0.0044 | 0.0363 | 4 | no |
| | | | hist_gradient_boosting | 0.0616 | 0.5266 | 0.0433 | 0.0043 | 0.0467 | 5 | no |
| G | technical + all four | 121 | ridge | 0.0644 | 0.5161 | 0.0477 | 0.0044 | 0.0404 | 5 | no |
| | | | hist_gradient_boosting | 0.0625 | 0.5181 | 0.0452 | 0.0041 | 0.0369 | 5 | no |
| — | historical_mean (no features) | — | — | 0.0602 | 0.5375 | 0.0273 | 0.0059 | 0.0876 | 3 | — |

\* Naive standard error (overlapping labels make it too small).

Per-block mean IC (blocks: B1 2021-02-16 to 2022-03-24, B2 2022-03-25 to 2023-05-03, B3 2023-05-04 to 2024-06-12, B4 2024-06-13 to 2025-07-17, B5 2025-07-18 to 2026-08-31):

| Cfg | Model | B1 | B2 | B3 | B4 | B5 |
|---|---|---|---|---|---|---|
| A | ridge | −0.0715 | 0.0391 | 0.1362 | 0.0071 | 0.0082 |
| A | hist_gradient_boosting | 0.0196 | 0.0561 | 0.1260 | 0.0621 | −0.0016 |
| B | ridge | −0.0199 | 0.0052 | 0.0125 | 0.0754 | 0.0207 |
| B | hist_gradient_boosting | 0.0034 | −0.0212 | 0.0442 | 0.0099 | 0.0101 |
| C | ridge | −0.0286 | 0.0140 | 0.0390 | −0.0103 | 0.0317 |
| C | hist_gradient_boosting | −0.0076 | 0.0321 | 0.0102 | 0.0041 | 0.0335 |
| D | ridge | 0.0218 | 0.0147 | 0.0913 | 0.0573 | −0.0204 |
| D | hist_gradient_boosting | −0.0012 | 0.0288 | 0.0687 | 0.0451 | −0.0077 |
| E | ridge | −0.0639 | 0.0311 | 0.0190 | 0.0380 | −0.0367 |
| E | hist_gradient_boosting | 0.0063 | 0.0162 | 0.0155 | 0.0684 | −0.0199 |
| F | ridge | 0.0130 | 0.0213 | 0.0668 | 0.0718 | −0.0126 |
| F | hist_gradient_boosting | 0.0079 | 0.0297 | 0.1193 | 0.0540 | 0.0061 |
| G | ridge | 0.0296 | 0.0240 | 0.1029 | 0.0767 | 0.0057 |
| G | hist_gradient_boosting | 0.0080 | 0.0357 | 0.1038 | 0.0546 | 0.0241 |
| — | historical_mean | 0.0462 | −0.0510 | 0.1616 | −0.0512 | 0.0311 |

**Reading the results:**
- **No configuration passes.** None beats the live baseline's mean IC (0.0523) at all, let alone by 2 s.e. The live configuration stays on the 12 technical features (`hist_gradient_boosting-h20-f12-v1`).
- **New groups alone are weak.** On their own, the Dow, pattern and geometry groups have mean ICs between −0.003 and 0.019, well below the technical features.
- **Accumulation/distribution is the strongest single new group:** Ridge IC 0.033, positive in 4 of 5 blocks. It is still below the baseline.
- **Combining helps steadiness more than level.**
  - F and G are positive in all 5 blocks (Ridge F: 4), and their block-to-block IC spread is a little lower than the live model's (0.036–0.047 vs 0.049).
  - Adding the new groups to the technical set doubles Ridge's IC (0.024 → 0.048) but lowers HistGradientBoosting's (0.052 → 0.045).
  - Neither is a gain over the live model, and with seven configurations compared on one period these differences may be selection noise.
- **MAE** gets slightly worse as features are added (Ridge 0.0597 → 0.0644).
- **Hit rates** of B, C and E (0.547–0.557) are higher than A's, but their ICs are near zero. That suggests the models mostly predict a positive return in a rising market. Direction alone is not evidence of better ranking.
- **Portfolio metrics:** no Sharpe ratio or drawdown is reported. The existing backtester has no point-in-time walk-forward simulation for these configurations, and none was approximated.

**Sensitivity to data revisions.** The earlier ablation run on a separate download reached the same conclusion: nothing passed, and A·HGB was 0.0532. But several research-group ICs moved more than the baseline did:

| Model | IC, earlier download | IC, same download |
|---|---|---|
| B·HGB | 0.0020 | 0.0093 |
| C·Ridge | 0.0144 | 0.0092 |
| G·HGB | 0.0383 | 0.0452 |
| A·HGB (for comparison) | 0.0532 | 0.0523 |

Pivot- and pattern-based features are discrete: a tiny price revision can add or remove a pivot and change many later feature values. Their measured IC is therefore less stable than the standard errors suggest.

**Coverage** (share of labelled rows):
- k = 5 Dow structure is present on 100% of rows, with a non-neutral trend on 63%.
- At least one pattern is active on 53% of rows, and a confirmed breakout on 38%.
- The symmetrical triangle is confirmed on 20% of rows. Its two sloped lines converge, so a close crosses one of them quickly, often on the detection bar itself. The rule is permissive, but it was not retuned, because tuning on these results would leak.

### 13.6 Limitations of this experiment

- **One evaluation period, seven configurations:** the comparison is exploratory. Any future claim of improvement needs a period none of these runs has seen. Prices after 2026-09-29 are untouched by this run and can serve as that hold-out once enough of them exist (at least one full test block).
- **Data revisions:** re-downloaded Yahoo prices differ slightly between runs, and the pivot- and pattern-based features amplify that (section 13.5). A confirmation run should save its price download and evaluate every configuration on it.
- **Fixed thresholds:** tolerances, windows and scales were set from the definitions, not optimised. Other reasonable choices could give different results; trying them on this period would be tuning on test data.
- **Event features are sparse and categorical:** the patterns are rule-based, and the ATR tolerances are one defensible choice among many.
- **Volume:** the volume features use yfinance volume as delivered (zero-volume days handled as neutral). Corporate actions may leave volume less consistently adjusted than price.
- **Inherited limitations:** everything in section 12 also applies here, including survivorship bias, overlapping labels and pre-event history under renamed symbols.
