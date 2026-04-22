"""Unit tests for src/database/qlib_crud.py."""
from unittest.mock import MagicMock
import pytest
from src.database.qlib_crud import QlibRunCRUD


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def crud(mock_client):
    return QlibRunCRUD(mock_client)


def test_register_calls_insert(crud, mock_client):
    mock_client.insert.return_value = [{"id": 1, "mlflow_run_id": "abc"}]
    result = crud.register("abc", experiment_name="workflow", family="lgbm_binary_tw",
                           workflow_config="daily_lgbm.yaml", status="success", metrics={"IC": 0.05})
    mock_client.insert.assert_called_once()
    call_args = mock_client.insert.call_args
    assert call_args[0][0] == "qlib_runs"
    rows = call_args[0][1]
    assert isinstance(rows, list)
    row = rows[0]
    assert row["mlflow_run_id"] == "abc"
    assert row["status"] == "success"
    assert row["metrics"] == {"IC": 0.05}


def test_register_default_metrics_empty(crud, mock_client):
    mock_client.insert.return_value = [{}]
    crud.register("run1")
    rows = mock_client.insert.call_args[0][1]
    assert rows[0]["metrics"] == {}


def test_update_status(crud, mock_client):
    mock_client.update.return_value = [{}]
    crud.update_status("abc", "success", {"IC": 0.06})
    mock_client.update.assert_called_once_with(
        "qlib_runs", {"mlflow_run_id": "abc"}, {"status": "success", "metrics": {"IC": 0.06}}
    )


def test_update_status_no_metrics(crud, mock_client):
    mock_client.update.return_value = [{}]
    crud.update_status("abc", "failed")
    update_payload = mock_client.update.call_args[0][2]
    assert "metrics" not in update_payload


def test_get_by_run_id(crud, mock_client):
    mock_client.select.return_value = [{"id": 1}]
    result = crud.get_by_run_id("abc")
    mock_client.select.assert_called_once_with(
        "qlib_runs", filters={"mlflow_run_id": "abc"}, limit=1
    )
    assert result == {"id": 1}


def test_get_by_run_id_not_found(crud, mock_client):
    mock_client.select.return_value = []
    result = crud.get_by_run_id("nonexistent")
    assert result is None


def test_list_by_family(crud, mock_client):
    mock_client.select.return_value = [{"id": 1}]
    result = crud.list_by_family("lgbm_binary_tw")
    mock_client.select.assert_called_once_with(
        "qlib_runs", filters={"family": "lgbm_binary_tw"}, order="created_at.desc", limit=20
    )
