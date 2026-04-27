from datetime import date
import pytest
from src.database.client import SupabaseClient
from src.database.crud import CoverageCRUD


@pytest.fixture
def db(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    return SupabaseClient()


def test_coverage_insert_and_latest(db):
    crud = CoverageCRUD(db)
    crud.insert_snapshot(date(2026, 4, 21), "r1", 0.92, 0.85, ["0050"])
    latest = crud.latest(limit=1)
    assert len(latest) == 1
    assert latest[0]["revenue_coverage"] == pytest.approx(0.92)


def test_coverage_latest_empty(db):
    crud = CoverageCRUD(db)
    rows = crud.latest(limit=5)
    assert isinstance(rows, list)


def test_coverage_insert_multiple(db):
    crud = CoverageCRUD(db)
    crud.insert_snapshot(date(2026, 4, 20), "r1", 0.80, 0.75, [])
    crud.insert_snapshot(date(2026, 4, 21), "r2", 0.90, 0.88, ["2330"])
    rows = crud.latest(limit=5)
    assert len(rows) == 2
