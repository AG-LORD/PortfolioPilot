"""Offline walk-forward evaluation of the return models.

Run from backend/:
    python -m scripts.run_evaluation --tickers RELIANCE,TCS,INFY,HDFCBANK,ICICIBANK --no-cache
    python -m scripts.run_evaluation --universe NIFTY50

--no-cache downloads prices into memory with one batched yfinance request and
never imports the database layer (asserted at the end of the run). Without
it, prices are read through the price cache in DATABASE_URL, which stores
any newly fetched prices there.

Prints the metrics table, per-block IC and a data summary, and writes the same
report as JSON to results/evaluation_<run date>.json.
"""

import argparse
import json
import math
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path

from app.ml.evaluation import (
    EvaluationError,
    ic_standard_errors,
    per_block_ic,
    run_walk_forward,
    summarize_walk_forward,
)
from app.ml.splits import N_TEST_BLOCKS
from app.services import market_data
from app.services.features import (
    DEFAULT_HORIZON,
    MIN_FEATURE_HISTORY,
    FeaturePanel,
    build_panel_from_prices,
)
from app.services.market_calendar import MARKET_TIMEZONE, last_completed_trading_day
from app.services.market_data import MarketDataUnavailableError
from app.services.universe import CUSTOM_UNIVERSE, UniverseError, get_universe, normalize_tickers

DEFAULT_START = date(2019, 1, 1)
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
IC_SE_NOTE = (
    "IC standard error = std(daily IC) / sqrt(number of IC dates). It treats daily ICs as "
    "independent, but overlapping multi-day labels make them autocorrelated, so this "
    "understates the true uncertainty. Context only, not a significance test."
)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Walk-forward evaluation of return models.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--universe", help="named universe, e.g. NIFTY50")
    source.add_argument("--tickers", help="comma-separated bare NSE symbols, e.g. RELIANCE,TCS")
    parser.add_argument("--start", type=date.fromisoformat, default=DEFAULT_START, help="first price date")
    parser.add_argument(
        "--end",
        type=date.fromisoformat,
        default=None,
        help="last price date, inclusive (default: last completed IST trading day)",
    )
    parser.add_argument("--blocks", type=int, default=N_TEST_BLOCKS, help="number of test blocks")
    parser.add_argument("--horizon", type=int, default=DEFAULT_HORIZON, help="label horizon in trading days")
    parser.add_argument(
        "--no-cache", action="store_true", help="fetch into memory only; never touch a database"
    )
    parser.add_argument("--output-dir", type=Path, default=RESULTS_DIR, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def resolve_tickers(args: argparse.Namespace) -> tuple[str, list[str]]:
    if args.universe:
        universe = get_universe(args.universe)
        return universe.name, universe.tickers
    return CUSTOM_UNIVERSE, normalize_tickers(args.tickers.split(","))


def load_panel_in_memory(tickers: list[str], start: date, end: date, horizon: int) -> FeaturePanel:
    fetched = market_data.download_history_batch(tickers, start, end)
    return build_panel_from_prices(tickers, fetched, errors={}, horizon=horizon)


def load_panel_from_cache(tickers: list[str], start: date, end: date, horizon: int) -> FeaturePanel:
    from app.database import SessionLocal
    from app.services.features import build_feature_panel

    with SessionLocal() as db:
        return build_feature_panel(db, tickers, start, end, horizon)


def _number(value) -> float | None:
    value = float(value)
    return None if math.isnan(value) else round(value, 6)


def _date_range(dates) -> list[str] | None:
    if len(dates) == 0:
        return None
    return [str(min(dates))[:10], str(max(dates))[:10]]


def run(args: argparse.Namespace) -> dict:
    end = args.end or last_completed_trading_day(datetime.now(MARKET_TIMEZONE))
    universe, tickers = resolve_tickers(args)
    loader = load_panel_in_memory if args.no_cache else load_panel_from_cache
    feature_panel = loader(tickers, args.start, end + timedelta(days=1), args.horizon)

    result = run_walk_forward(feature_panel.panel, n_blocks=args.blocks, horizon=args.horizon)
    evaluations = summarize_walk_forward(result)
    standard_errors = ic_standard_errors(result)
    blocks = per_block_ic(result)
    panel, predictions = feature_panel.panel, result.predictions

    report = {
        "generated_at": datetime.now(MARKET_TIMEZONE).isoformat(timespec="seconds"),
        "settings": {
            "universe": universe,
            "start": args.start.isoformat(),
            "end": end.isoformat(),
            "blocks": args.blocks,
            "horizon": args.horizon,
            "min_feature_history": MIN_FEATURE_HISTORY,
            "source": "yfinance, in memory" if args.no_cache else "price cache",
        },
        "data": {
            "requested_tickers": len(tickers),
            "tickers_used": sorted(panel["ticker"].unique().tolist()),
            "excluded": [asdict(e) for e in feature_panel.excluded],
            "panel_rows": len(panel),
            "panel_dates": _date_range(panel["date"]),
            "scored_rows": len(predictions),
            "scored_dates": _date_range(predictions["date"]),
        },
        "metrics": [
            {
                "model": e.model,
                "mae": _number(e.mae),
                "hit_rate": _number(e.hit_rate),
                "mean_ic": _number(e.mean_ic),
                "ic_std_error": _number(standard_errors[e.model]),
                "test_blocks": e.test_blocks,
                "as_of": e.as_of.isoformat(),
            }
            for e in evaluations
        ],
        "ic_std_error_note": IC_SE_NOTE,
        "per_block_ic": {
            model: [
                {
                    "block": b.block,
                    "start": b.start.isoformat(),
                    "end": b.end.isoformat(),
                    "ic_dates": b.ic_dates,
                    "mean_ic": _number(b.mean_ic),
                }
                for b in model_blocks
            ]
            for model, model_blocks in blocks.items()
        },
    }

    # Explicit check rather than `assert` so it also runs under python -O.
    if args.no_cache and "app.database" in sys.modules:
        raise RuntimeError("--no-cache run imported the database layer")
    return report


def format_report(report: dict) -> str:
    s, d = report["settings"], report["data"]
    fmt = lambda v: "n/a" if v is None else f"{v:.4f}"  # noqa: E731
    lines = [
        f"Walk-forward evaluation: {s['universe']}, prices {s['start']} to {s['end']}, "
        f"horizon {s['horizon']}, {s['blocks']} test blocks ({s['source']})",
        "",
        f"{'Model':<24}{'MAE':>10}{'Hit rate':>10}{'Mean IC':>10}{'IC s.e.*':>10}{'Blocks':>8}",
    ]
    for m in report["metrics"]:
        lines.append(
            f"{m['model']:<24}{fmt(m['mae']):>10}{fmt(m['hit_rate']):>10}{fmt(m['mean_ic']):>10}"
            f"{fmt(m['ic_std_error']):>10}{m['test_blocks']:>8}"
        )
    lines += ["", f"* {report['ic_std_error_note']}", "", "Per-block mean IC"]

    models = list(report["per_block_ic"])
    lines.append(f"{'Block':<7}{'Dates':<25}" + "".join(f"{m:>24}" for m in models))
    first = report["per_block_ic"][models[0]]
    for i, block in enumerate(first):
        row = f"{block['block']:<7}{block['start'] + ' to ' + block['end']:<25}"
        row += "".join(f"{fmt(report['per_block_ic'][m][i]['mean_ic']):>24}" for m in models)
        lines.append(row)

    panel_dates = " to ".join(d["panel_dates"]) if d["panel_dates"] else "none"
    scored_dates = " to ".join(d["scored_dates"]) if d["scored_dates"] else "none"
    lines += [
        "",
        "Data",
        f"  Feature rows: {d['panel_rows']} ({panel_dates})",
        f"  Scored rows:  {d['scored_rows']} ({scored_dates})",
        f"  Tickers used ({len(d['tickers_used'])} of {d['requested_tickers']}): "
        + (", ".join(d["tickers_used"]) or "none"),
        f"  Excluded ({len(d['excluded'])}):",
        *[f"    {e['ticker']}: {e['reason']}" for e in d["excluded"]],
    ]
    return "\n".join(lines)


def write_report(report: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"evaluation_{report['generated_at'][:10]}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> dict:
    args = parse_args(argv)
    try:
        report = run(args)
    except (UniverseError, MarketDataUnavailableError, EvaluationError, ValueError) as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(format_report(report))
    print(f"\nWrote {write_report(report, args.output_dir)}")
    return report


if __name__ == "__main__":
    main()
