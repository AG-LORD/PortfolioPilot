# ML Methodology

This document describes how PortfolioPilot builds features and labels, and
how return-forecasting models are evaluated against a historical-mean
baseline. Code: `backend/app/services/features.py` (features, label, panel)
and `backend/app/ml/` (splits, models, baseline, metrics, evaluation).
Live recommendations can use the ML model (`return_model = "ml"`); see section 9.

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

## 10. Results: NIFTY 50

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

## 11. Known limitations

- **No NSE holiday calendar:** `is_trading_weekday` only knows Monday–Friday. On an exchange holiday the nightly job still runs (the latest feature date is then the previous session, so its stored `as_of` does not match the "latest completed trading weekday" and requests that day fall back to on-request training), and the snapshot script records a snapshot with unchanged prices.
- **Overlapping labels:** 20-day forward returns on consecutive days overlap, so daily metric observations are autocorrelated. The IC standard error in the evaluation report is computed naively and is therefore too small. No significance tests are reported yet.
- **Survivorship bias:** evaluating on today's index constituents over past dates favors stocks that survived into the index. The universe file records the date of its constituent list (`as_of`).
- **One calendar:** splits use the union of dates in the panel and assume all tickers trade on the NSE calendar.
- **Symbol history from yfinance:** some current symbols carry predecessor history. `TMPV` (Tata Motors passenger vehicles, demerged in 2025) returns prices back to 2019, i.e. the pre-demerger Tata Motors series. `ETERNAL` (renamed from Zomato) starts at the 2021 listing. `JIOFIN` starts at its 2023 listing. Pre-event history under a new symbol, and any unadjusted demerger jump, can distort features and labels for those tickers.
- **The universe is fixed at its retrieval date:** the same 50 names are used for every past date (see survivorship bias above).
- **Recursive smoothers depend on the series start** (section 3). `MIN_FEATURE_HISTORY` = 252 makes this negligible for panel rows, at the cost of the first year of each ticker's history.
