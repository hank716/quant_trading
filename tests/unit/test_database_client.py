import pytest
from src.database.client import SupabaseClient


@pytest.fixture
def db(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    return SupabaseClient()


def test_mock_mode_when_no_credentials(db):
    assert db.mock_mode is True


def test_insert_and_select(db):
    db.insert("test_table", [{"id": 1, "val": "a"}, {"id": 2, "val": "b"}])
    rows = db.select("test_table")
    assert len(rows) == 2


def test_select_with_filter(db):
    db.insert("items", [{"name": "foo", "status": "ok"},
                         {"name": "bar", "status": "err"}])
    result = db.select("items", filters={"status": "ok"})
    assert len(result) == 1
    assert result[0]["name"] == "foo"


def test_select_limit(db):
    db.insert("big", [{"i": i} for i in range(10)])
    rows = db.select("big", limit=3)
    assert len(rows) == 3


def test_update(db):
    db.insert("runs", [{"run_id": "r1", "status": "running"}])
    db.update("runs", {"run_id": "r1"}, {"status": "success"})
    rows = db.select("runs", {"run_id": "r1"})
    assert rows[0]["status"] == "success"


def test_select_latest(db):
    db.insert("events", [{"ts": "2026-04-20", "v": 1},
                          {"ts": "2026-04-21", "v": 2}])
    latest = db.select_latest("events", "ts", limit=1)
    assert latest[0]["v"] == 2


def test_insert_empty_rows(db):
    result = db.insert("empty_test", [])
    assert result == []
