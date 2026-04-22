"""Tests for src/signals/explainer_shap.py — shap is mocked throughout."""
import json
import numpy as np
import pandas as pd
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.signals.explainer_shap import compute_shap_summary, write_shap_summary


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _feature_df(n: int = 20, cols: list[str] | None = None) -> pd.DataFrame:
    cols = cols or ["f1", "f2", "f3", "f4", "f5"]
    rng = np.random.default_rng(0)
    return pd.DataFrame(rng.normal(0, 1, (n, len(cols))), columns=cols)


def _mock_shap_values(feature_matrix: pd.DataFrame, per_feature_value: float = 0.1):
    """Return fake shap values array (n_samples × n_features)."""
    n, m = feature_matrix.shape
    return np.full((n, m), per_feature_value)


def _build_shap_module(shap_values_array):
    """Construct a minimal shap mock that TreeExplainer returns the given array."""
    mock_shap = MagicMock()
    explainer = MagicMock()
    explainer.shap_values.return_value = shap_values_array
    mock_shap.TreeExplainer.return_value = explainer
    return mock_shap


# ------------------------------------------------------------------ #
# compute_shap_summary — happy path
# ------------------------------------------------------------------ #

def test_compute_returns_top_n_features():
    X = _feature_df(20, cols=["a", "b", "c", "d", "e"])
    shap_vals = _mock_shap_values(X)
    model = MagicMock()

    with patch.dict("sys.modules", {"shap": _build_shap_module(shap_vals)}):
        result = compute_shap_summary(model, X, top_n=3)

    assert len(result["top_features"]) == 3


def test_compute_top_features_sorted_desc():
    X = _feature_df(10, cols=["low", "mid", "high"])
    # assign different mean abs values per column
    vals = np.column_stack([
        np.full(10, 0.1),
        np.full(10, 0.5),
        np.full(10, 0.9),
    ])
    model = MagicMock()

    with patch.dict("sys.modules", {"shap": _build_shap_module(vals)}):
        result = compute_shap_summary(model, X, top_n=3)

    features_in_order = [f["feature"] for f in result["top_features"]]
    assert features_in_order == ["high", "mid", "low"]


def test_compute_reports_n_samples_and_features():
    X = _feature_df(15, cols=["x1", "x2", "x3"])
    with patch.dict("sys.modules", {"shap": _build_shap_module(_mock_shap_values(X))}):
        result = compute_shap_summary(MagicMock(), X, top_n=10)
    assert result["n_samples"] == 15
    assert result["n_features"] == 3


def test_compute_handles_list_shap_values():
    """Binary classifiers may return [neg_class_vals, pos_class_vals]."""
    X = _feature_df(10, cols=["a", "b"])
    neg = np.zeros((10, 2))
    pos = np.ones((10, 2)) * 0.3
    shap_list = [neg, pos]

    mock_shap = MagicMock()
    explainer = MagicMock()
    explainer.shap_values.return_value = shap_list
    mock_shap.TreeExplainer.return_value = explainer

    with patch.dict("sys.modules", {"shap": mock_shap}):
        result = compute_shap_summary(MagicMock(), X, top_n=2)

    assert len(result["top_features"]) == 2
    assert result["top_features"][0]["mean_abs_shap"] == pytest.approx(0.3, rel=1e-3)


def test_compute_empty_dataframe_returns_empty():
    with patch.dict("sys.modules", {"shap": MagicMock()}):
        result = compute_shap_summary(MagicMock(), pd.DataFrame(), top_n=5)
    assert result["top_features"] == []
    assert result["n_samples"] == 0


def test_compute_top_n_capped_at_feature_count():
    X = _feature_df(10, cols=["a", "b"])
    with patch.dict("sys.modules", {"shap": _build_shap_module(_mock_shap_values(X))}):
        result = compute_shap_summary(MagicMock(), X, top_n=99)
    assert len(result["top_features"]) == 2


def test_compute_falls_back_to_generic_explainer():
    X = _feature_df(5, cols=["x"])
    mock_shap = MagicMock()

    tree_exp = MagicMock()
    tree_exp.shap_values.side_effect = Exception("not a tree model")
    mock_shap.TreeExplainer.return_value = tree_exp

    # shap.Explainer(model, X) → generic_explainer_instance
    # generic_explainer_instance(X) → explanation; explanation.values = array
    explanation = MagicMock()
    explanation.values = np.full((5, 1), 0.2)
    generic_explainer_instance = MagicMock(return_value=explanation)
    mock_shap.Explainer.return_value = generic_explainer_instance

    with patch.dict("sys.modules", {"shap": mock_shap}):
        result = compute_shap_summary(MagicMock(), X, top_n=1)

    assert result["top_features"][0]["mean_abs_shap"] == pytest.approx(0.2, rel=1e-3)


# ------------------------------------------------------------------ #
# write_shap_summary
# ------------------------------------------------------------------ #

def test_write_creates_json_file(tmp_path):
    summary = {"top_features": [{"feature": "f1", "mean_abs_shap": 0.5}], "n_samples": 10, "n_features": 1}
    path = write_shap_summary(summary, "run_abc", output_dir=tmp_path)
    assert path.exists()
    assert path.suffix == ".json"
    loaded = json.loads(path.read_text())
    assert loaded["top_features"][0]["feature"] == "f1"


def test_write_creates_nested_dirs(tmp_path):
    summary = {"top_features": [], "n_samples": 0, "n_features": 0}
    path = write_shap_summary(summary, "run_xyz", output_dir=tmp_path / "deep" / "nested")
    assert path.exists()


def test_write_run_id_as_subdirectory(tmp_path):
    summary = {"top_features": [], "n_samples": 0, "n_features": 0}
    path = write_shap_summary(summary, "run_42", output_dir=tmp_path)
    assert "run_42" in str(path)
    assert path.name == "shap_summary.json"
