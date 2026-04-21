from datetime import date
import pytest
from src.database.client import SupabaseClient
from src.database.crud import PipelineRunCRUD, ArtifactCRUD, CandidateCRUD, CoverageCRUD


@pytest.fixture
def db(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    return SupabaseClient()


def test_pipeline_run_start_finish(db):
    crud = PipelineRunCRUD(db)
    crud.start("r1", date(2026, 4, 21), mode="daily", git_commit="abc")
    rows = db.select("pipeline_runs", {"run_id": "r1"})
    assert rows[0]["status"] == "running"

    crud.finish("r1", status="success", notes="all good")
    rows = db.select("pipeline_runs", {"run_id": "r1"})
    assert rows[0]["status"] == "success"


def test_pipeline_run_latest(db):
    crud = PipelineRunCRUD(db)
    crud.start("r1", date(2026, 4, 20))
    crud.start("r2", date(2026, 4, 21))
    latest = crud.latest(limit=1)
    assert len(latest) >= 1


def test_artifact_register(db):
    crud = ArtifactCRUD(db)
    row = crud.register("r1", "signals.json", "/runs/r1/signals.json")
    assert row["artifact"] == "signals.json"
    rows = db.select("run_artifacts", {"run_id": "r1"})
    assert len(rows) == 1


def test_candidate_bulk_insert_and_query(db):
    crud = CandidateCRUD(db)
    candidates = [
        {"instrument": "2330", "list_type": "eligible", "score": 0.9},
        {"instrument": "3661", "list_type": "eligible", "score": 0.8},
        {"instrument": "1101", "list_type": "watch", "score": 0.5},
    ]
    crud.bulk_insert("r1", date(2026, 4, 21), candidates)
    rows = crud.latest_by_date(date(2026, 4, 21))
    assert len(rows) == 3


def test_coverage_insert_and_latest(db):
    crud = CoverageCRUD(db)
    crud.insert_snapshot(date(2026, 4, 21), "r1", 0.92, 0.85, ["0050"])
    latest = crud.latest(limit=1)
    assert len(latest) == 1
    assert latest[0]["revenue_coverage"] == pytest.approx(0.92)
