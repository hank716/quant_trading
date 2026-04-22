"""Tests for src/registry/model_registry.py — mock DB + mock pCloud."""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.registry.model_registry import ModelRegistry


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

class MockDB:
    """Minimal in-memory stand-in for SupabaseClient."""

    def __init__(self):
        self._store: dict[str, list[dict]] = {}

    def insert(self, table, rows):
        self._store.setdefault(table, []).extend(rows)
        return rows

    def update(self, table, match, values):
        updated = []
        for row in self._store.get(table, []):
            if all(row.get(k) == v for k, v in match.items()):
                row.update(values)
                updated.append(row)
        return updated

    def select(self, table, filters=None, limit=100):
        rows = self._store.get(table, [])
        if filters:
            rows = [r for r in rows if all(r.get(k) == v for k, v in filters.items())]
        return rows[:limit]


class MockPCloud:
    mock_mode = True

    def upload_file(self, local_path, remote_path):
        return {"mock": True, "remote": remote_path}

    def download_file(self, remote_path, local_path):
        Path(local_path).write_bytes(b"fake-model-bytes")
        return {"mock": True}


def _registry(db=None, pcloud=None) -> ModelRegistry:
    return ModelRegistry(db=db or MockDB(), pcloud=pcloud or MockPCloud())


def _dummy_model_file(tmp_path: Path) -> Path:
    p = tmp_path / "model.pkl"
    p.write_bytes(b"fake")
    return p


# ------------------------------------------------------------------ #
# register
# ------------------------------------------------------------------ #

def test_register_inserts_candidate(tmp_path):
    db = MockDB()
    reg = _registry(db=db)
    model_path = _dummy_model_file(tmp_path)
    model_id = reg.register(model_path, "m1", "lgbm_binary", {"auc": 0.7})
    assert model_id == "m1"
    rows = db.select("model_versions")
    assert len(rows) == 1
    assert rows[0]["status"] == "candidate"
    assert rows[0]["family"] == "lgbm_binary"


def test_register_stores_metrics(tmp_path):
    db = MockDB()
    reg = _registry(db=db)
    reg.register(_dummy_model_file(tmp_path), "m2", "lgbm_binary", {"auc": 0.82, "n_train": 500})
    row = db.select("model_versions")[0]
    assert row["metrics"]["auc"] == 0.82


def test_register_uses_provided_artifact_uri(tmp_path):
    db = MockDB()
    reg = _registry(db=db)
    reg.register(_dummy_model_file(tmp_path), "m3", "lgbm_binary", {}, artifact_uri="/custom/path.pkl")
    row = db.select("model_versions")[0]
    assert row["artifact_uri"] == "/custom/path.pkl"


# ------------------------------------------------------------------ #
# get_champion / list_candidates
# ------------------------------------------------------------------ #

def test_get_champion_returns_none_when_empty():
    reg = _registry()
    assert reg.get_champion("lgbm_binary") is None


def test_get_champion_returns_champion(tmp_path):
    db = MockDB()
    reg = _registry(db=db)
    reg.register(_dummy_model_file(tmp_path), "m1", "lgbm_binary", {})
    reg.promote("m1", "first model")
    champion = reg.get_champion("lgbm_binary")
    assert champion is not None
    assert champion["model_id"] == "m1"
    assert champion["status"] == "champion"


def test_list_candidates_excludes_champion(tmp_path):
    db = MockDB()
    reg = _registry(db=db)
    reg.register(_dummy_model_file(tmp_path), "m1", "lgbm_binary", {})
    reg.register(_dummy_model_file(tmp_path), "m2", "lgbm_binary", {})
    reg.promote("m1", "first")
    candidates = reg.list_candidates("lgbm_binary")
    assert len(candidates) == 1
    assert candidates[0]["model_id"] == "m2"


# ------------------------------------------------------------------ #
# promote
# ------------------------------------------------------------------ #

def test_promote_unknown_model_returns_false():
    reg = _registry()
    result = reg.promote("does_not_exist", "test")
    assert result is False


def test_promote_retires_previous_champion(tmp_path):
    db = MockDB()
    reg = _registry(db=db)
    reg.register(_dummy_model_file(tmp_path), "m1", "lgbm_binary", {})
    reg.register(_dummy_model_file(tmp_path), "m2", "lgbm_binary", {})
    reg.promote("m1", "initial champion")
    reg.promote("m2", "better model")

    m1 = db.select("model_versions", filters={"model_id": "m1"})[0]
    m2 = db.select("model_versions", filters={"model_id": "m2"})[0]
    assert m1["status"] == "retired"
    assert m2["status"] == "champion"


def test_promote_writes_to_promotions_log(tmp_path):
    db = MockDB()
    reg = _registry(db=db)
    reg.register(_dummy_model_file(tmp_path), "m1", "lgbm_binary", {})
    reg.promote("m1", "test reason")
    logs = db.select("model_promotions")
    assert len(logs) == 1
    assert logs[0]["reason"] == "test reason"
    assert logs[0]["model_id"] == "m1"


# ------------------------------------------------------------------ #
# download_model
# ------------------------------------------------------------------ #

def test_download_model_from_local_uri(tmp_path):
    db = MockDB()
    reg = _registry(db=db)
    src = tmp_path / "model_src.pkl"
    src.write_bytes(b"model-data")
    db.insert("model_versions", [{"model_id": "mx", "artifact_uri": str(src)}])

    dest_dir = tmp_path / "cache"
    path = reg.download_model("mx", dest_dir)
    assert path.exists()
    assert path.read_bytes() == b"model-data"


def test_download_model_not_found_raises(tmp_path):
    reg = _registry()
    with pytest.raises(FileNotFoundError):
        reg.download_model("ghost_model", tmp_path)


def test_download_model_uses_cache(tmp_path):
    db = MockDB()
    src = tmp_path / "model.pkl"
    src.write_bytes(b"x")
    db.insert("model_versions", [{"model_id": "m_cache", "artifact_uri": str(src)}])
    reg = _registry(db=db)
    dest_dir = tmp_path / "cache"

    p1 = reg.download_model("m_cache", dest_dir)
    p2 = reg.download_model("m_cache", dest_dir)
    assert p1 == p2
