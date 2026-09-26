"""Frontend mock files must match the backend response schemas exactly (same
fields, no extras), so a schema change breaks this test instead of silently
breaking the frontend."""

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from app.schemas.ml import EvaluationReportRead
from app.schemas.overview import PortfolioOverviewRead
from app.schemas.recommendation import RecommendationRead
from app.schemas.universe import UniverseRead

MOCKS_DIR = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "mocks"

MOCK_SCHEMAS = {
    "recommendation.historical.json": RecommendationRead,
    "recommendation.ml.json": RecommendationRead,
    "universes.json": list[UniverseRead],
    "overview.json": PortfolioOverviewRead,
    "ml-evaluation.json": EvaluationReportRead,
}


def _strip_mock_flag(value):
    if isinstance(value, dict):
        return {k: _strip_mock_flag(v) for k, v in value.items() if k != "_mock"}
    if isinstance(value, list):
        return [_strip_mock_flag(v) for v in value]
    return value


def _assert_same_shape(mock, dumped, where="$"):
    if isinstance(dumped, dict):
        assert isinstance(mock, dict), where
        assert set(mock) == set(dumped), f"{where}: mock keys {sorted(mock)} != schema keys {sorted(dumped)}"
        for key in dumped:
            _assert_same_shape(mock[key], dumped[key], f"{where}.{key}")
    elif isinstance(dumped, list):
        assert isinstance(mock, list) and len(mock) == len(dumped), where
        for i, (m, d) in enumerate(zip(mock, dumped)):
            _assert_same_shape(m, d, f"{where}[{i}]")


def test_every_mock_file_has_a_schema():
    assert sorted(p.name for p in MOCKS_DIR.glob("*.json")) == sorted(MOCK_SCHEMAS)


@pytest.mark.parametrize("filename", sorted(MOCK_SCHEMAS))
def test_mock_matches_backend_schema(filename):
    raw = json.loads((MOCKS_DIR / filename).read_text(encoding="utf-8"))

    top_level = raw if isinstance(raw, list) else [raw]
    assert top_level, f"{filename} is empty"
    assert all(item.get("_mock") is True for item in top_level), f'{filename} must be marked "_mock": true'

    adapter = TypeAdapter(MOCK_SCHEMAS[filename])
    data = _strip_mock_flag(raw)
    dumped = adapter.dump_python(adapter.validate_python(data), mode="json")
    _assert_same_shape(data, dumped)


def test_recommendation_mocks_cover_both_return_models():
    for filename, model in (("recommendation.historical.json", "historical"), ("recommendation.ml.json", "ml")):
        assert json.loads((MOCKS_DIR / filename).read_text(encoding="utf-8"))["return_model"] == model
