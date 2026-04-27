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
def test_coverage_crud_roundtrip(db):
    from src.database.crud import CoverageCRUD
    crud = CoverageCRUD(db)
    td = date.today()
    row = crud.insert_snapshot(td, "integration_test", 0.9, 0.85, ["2330"])
    assert row.get("revenue_coverage") == pytest.approx(0.9)

    latest = crud.latest(limit=5)
    assert any(r.get("run_id") == "integration_test" for r in latest)
