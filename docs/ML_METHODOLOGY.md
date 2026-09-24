# ML Methodology

This document describes how PortfolioPilot builds features and labels, and
how return-forecasting models are evaluated against a historical-mean
baseline. Code: `backend/app/services/features.py` (features, label, panel)
and `backend/app/ml/` (splits, models, baseline, metrics, evaluation).
No model is used for live recommendations yet.

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
- This is the same estimator the live historical provider uses (mean daily return × 252 per year), rescaled to the 20-day horizon so it is compared on the same target.
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

## 9. Known limitations

- **Overlapping labels:** 20-day forward returns on consecutive days overlap, so daily metric observations are autocorrelated. The IC standard error in the evaluation report is computed naively and is therefore too small. No significance tests are reported yet.
- **Survivorship bias:** evaluating on today's index constituents over past dates favors stocks that survived into the index. The universe file records the date of its constituent list (`as_of`).
- **One calendar:** splits use the union of dates in the panel and assume all tickers trade on the NSE calendar.
- **Recursive smoothers depend on the series start** (section 3). `MIN_FEATURE_HISTORY` = 252 makes this negligible for panel rows, at the cost of the first year of each ticker's history.
