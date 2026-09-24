"""The offline evaluation script, end to end on synthetic prices.

main() runs in a fresh subprocess: the test process has already imported
app.database (via conftest), so only a clean process can show that the
--no-cache path never imports it.
"""

import json
import os
import subprocess
import sys
import textwrap
from datetime import date, timedelta
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
TESTS_DIR = Path(__file__).resolve().parent
UNREACHABLE_DB_URL = "postgresql+psycopg://pp_no_db@pp-no-db.invalid:5432/pp_no_db?connect_timeout=1"

GOOD = [f"ZZTEST_{c}" for c in "ABCDEF"]

SCRIPT = textwrap.dedent(
    """
    import sys
    from datetime import date

    from price_fakes import make_series
    from app.services import market_data

    end = date(2025, 12, 31)
    series = {{t: make_series(i, n_days=640, end=end, weekdays_only=True) for i, t in enumerate({good!r})}}
    series["ZZTEST_SHORT"] = make_series(99, n_days=200, end=end, weekdays_only=True)
    calls = []

    def fake_download(tickers, start, stop):
        calls.append(list(tickers))
        return {{t: [p for p in series.get(t, []) if start <= p.date < stop] for t in tickers}}

    market_data.download_history_batch = fake_download

    from scripts.run_evaluation import main

    main([
        "--tickers", ",".join({good!r} + ["ZZTEST_SHORT", "ZZTEST_MISSING"]),
        "--start", "2023-01-01", "--end", "2025-12-31",
        "--blocks", "3", "--horizon", "20", "--no-cache",
        "--output-dir", sys.argv[1],
    ])
    assert len(calls) == 1, calls
    assert "app.database" not in sys.modules
    assert "app.models" not in sys.modules
    print("SUBPROCESS_OK")
    """
).format(good=GOOD)


def _run_script(output_dir: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": UNREACHABLE_DB_URL}
    env.pop("TEST_DATABASE_URL", None)
    env["PYTHONPATH"] = os.pathsep.join([str(BACKEND_DIR), str(TESTS_DIR)])
    return subprocess.run(
        [sys.executable, "-c", SCRIPT, str(output_dir)],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


@pytest.fixture(scope="module")
def script_run(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("results")
    completed = _run_script(output_dir)
    assert completed.returncode == 0, completed.stderr[-3000:]
    [report_file] = output_dir.glob("evaluation_*.json")
    return completed.stdout, json.loads(report_file.read_text(encoding="utf-8"))


def test_no_cache_run_never_imports_the_database_layer(script_run):
    stdout, _ = script_run
    assert "SUBPROCESS_OK" in stdout


def test_report_prints_metrics_per_block_ic_and_data_summary(script_run):
    stdout, _ = script_run
    for text in ("MAE", "Hit rate", "Mean IC", "IC s.e.", "Per-block mean IC", "Tickers used (6 of 8)", "Excluded (2)"):
        assert text in stdout
    for model in ("historical_mean", "ridge", "hist_gradient_boosting"):
        assert model in stdout


def test_report_json_contents(script_run):
    _, report = script_run
    assert report["settings"]["source"] == "yfinance, in memory"
    assert report["settings"]["min_feature_history"] == 252
    data = report["data"]
    assert data["tickers_used"] == GOOD
    short_rows = sum((date(2025, 12, 31) - timedelta(days=i)).weekday() < 5 for i in range(200))
    assert {e["ticker"]: e["reason"] for e in data["excluded"]} == {
        "ZZTEST_SHORT": f"only {short_rows} trading day(s) of history; at least 253 are needed",
        "ZZTEST_MISSING": "no historical data returned",
    }
    assert data["scored_rows"] > 0
    assert [m["model"] for m in report["metrics"]] == ["historical_mean", "ridge", "hist_gradient_boosting"]
    for m in report["metrics"]:
        assert m["test_blocks"] == 3
        assert m["ic_std_error"] is not None and m["ic_std_error"] > 0
        assert len(report["per_block_ic"][m["model"]]) == 3
    assert "understates" in report["ic_std_error_note"]


def test_parse_args_requires_exactly_one_ticker_source():
    from scripts.run_evaluation import parse_args

    with pytest.raises(SystemExit):
        parse_args([])
    with pytest.raises(SystemExit):
        parse_args(["--universe", "NIFTY50", "--tickers", "A"])
    args = parse_args(["--tickers", "A,B"])
    assert (args.start.isoformat(), args.end, args.blocks, args.horizon, args.no_cache) == (
        "2019-01-01",
        None,
        5,
        20,
        False,
    )
