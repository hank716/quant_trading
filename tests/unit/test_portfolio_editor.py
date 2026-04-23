"""Unit tests for app/control/portfolio_editor.py."""
import tempfile, os
from pathlib import Path
import pytest


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    return tmp_path


def test_load_empty_portfolio(tmp_config):
    from app.control.portfolio_editor import load_portfolio
    result = load_portfolio("test_profile")
    assert result == []


def test_add_and_load(tmp_config):
    from app.control.portfolio_editor import add_holding, load_portfolio
    add_holding("p1", "2330", name="台積電", shares=100, avg_cost=500.0)
    holdings = load_portfolio("p1")
    assert len(holdings) == 1
    assert holdings[0]["ticker"] == "2330"
    assert holdings[0]["name"] == "台積電"


def test_save_and_reload(tmp_config):
    from app.control.portfolio_editor import save_portfolio, load_portfolio
    data = [{"ticker": "0050", "name": "元大50", "shares": 500, "avg_cost": 100.0, "note": ""}]
    save_portfolio("p1", data)
    loaded = load_portfolio("p1")
    assert loaded[0]["ticker"] == "0050"
    assert loaded[0]["shares"] == 500


def test_remove_holding(tmp_config):
    from app.control.portfolio_editor import add_holding, remove_holding, load_portfolio
    add_holding("p1", "2330", name="台積電")
    add_holding("p1", "0050", name="元大50")
    removed = remove_holding("p1", "2330")
    assert removed is True
    holdings = load_portfolio("p1")
    assert all(h["ticker"] != "2330" for h in holdings)
    assert len(holdings) == 1


def test_remove_nonexistent(tmp_config):
    from app.control.portfolio_editor import remove_holding
    assert remove_holding("p1", "9999") is False


def test_atomic_write_creates_file(tmp_config):
    from app.control.portfolio_editor import save_portfolio
    save_portfolio("p1", [{"ticker": "2330", "name": "台積電", "shares": 0, "avg_cost": 0}])
    assert (tmp_config / "config" / "portfolio_p1.yaml").exists()
