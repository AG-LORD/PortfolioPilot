# Evaluation results

Output of `python -m scripts.run_evaluation` (run from `backend/`), one file per
run date: `evaluation_<YYYY-MM-DD>.json`. A second run on the same day
overwrites that day's file.

These files are not committed (see `.gitignore`); only this README is.

Each report contains:
- `settings`: universe, price date range, test blocks, horizon, minimum feature history, and the data source (in-memory yfinance or the price cache).
- `data`: tickers used, tickers excluded with reasons, and feature and scored row counts with their date ranges.
- `metrics`: MAE, hit rate, mean IC, IC standard error and test blocks per model. The IC standard error is optimistic because overlapping 20-day labels make daily ICs autocorrelated; see `ic_std_error_note`.
- `per_block_ic`: mean IC per test block for each model.

Method: `docs/ML_METHODOLOGY.md`.
