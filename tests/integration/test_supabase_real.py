"""Integration tests against a real Supabase instance. Skipped without credentials."""
import os
from datetime import date

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def db():
    from src.database.client import SupabaseClient
    return SupabaseClient()


@pytest.mark.skipif(
    not (os.getenv("SUPABASE_URL") and
         (os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY"))),
    reason="Needs SUPABASE_URL and SUPABASE_SERVICE_KEY / SUPABASE_ANON_KEY",
)
def test_supabase_not_mock(db):
    assert not db.mock_mode


@pytest.mark.skipif(
    not (os.getenv("SUPABASE_URL") and
         (os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY"))),
    reason="Needs Supabase credentials",
)
def test_pipeline_run_crud_roundtrip(db):
    from src.database.crud import PipelineRunCRUD
    crud = PipelineRunCRUD(db)
    run_id = f"test_integration_{date.today().isoformat()}"

    started = crud.start(run_id, date.today(), mode="daily", git_commit="test")
    assert started["run_id"] == run_id

    finished = crud.finish(run_id, status="success", notes="integration test")
    assert finished["status"] == "success"

    latest = crud.latest(limit=5)
    assert any(r["run_id"] == run_id for r in latest)
