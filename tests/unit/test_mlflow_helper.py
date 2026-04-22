"""Unit tests for app/control/mlflow_helper.py using mlflow mocks."""
from unittest.mock import MagicMock, patch
import pytest


def test_list_experiments_returns_dicts():
    exp = MagicMock()
    exp.experiment_id = "1"
    exp.name = "Default"
    exp.lifecycle_stage = "active"
    mock_mlflow_mod = MagicMock()
    mock_mlflow_mod.search_experiments.return_value = [exp]
    with patch("app.control.mlflow_helper.mlflow", mock_mlflow_mod):
        from app.control.mlflow_helper import list_experiments
        result = list_experiments()
    assert result == [{"experiment_id": "1", "name": "Default", "lifecycle_stage": "active"}]


def test_get_run_metrics_returns_dict():
    run = MagicMock()
    run.data.metrics = {"IC": 0.05, "Rank IC": 0.04}
    mock_mlflow_mod = MagicMock()
    mock_mlflow_mod.get_run.return_value = run
    with patch("app.control.mlflow_helper.mlflow", mock_mlflow_mod):
        from app.control.mlflow_helper import get_run_metrics
        result = get_run_metrics("abc123")
    assert result == {"IC": 0.05, "Rank IC": 0.04}


def test_tracking_uri_default():
    import os
    os.environ.pop("MLFLOW_TRACKING_URI", None)
    from app.control import mlflow_helper
    assert mlflow_helper._tracking_uri() == "file:workspace/mlruns"


def test_tracking_uri_env(monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "file:/tmp/test_mlruns")
    from app.control import mlflow_helper
    assert mlflow_helper._tracking_uri() == "file:/tmp/test_mlruns"
