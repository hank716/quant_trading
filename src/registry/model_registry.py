"""Model registry — register, promote, and retrieve LightGBM models.

Backed by Supabase (model_versions / model_promotions tables) and pCloud for
binary artefact storage.  Falls back gracefully when both clients are in mock
mode.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Thin wrapper around Supabase + pCloud for model lifecycle management."""

    def __init__(self, db=None, pcloud=None):
        if db is None:
            from src.database.client import SupabaseClient
            db = SupabaseClient()
        if pcloud is None:
            from src.storage.pcloud_client import PCloudClient
            pcloud = PCloudClient()
        self._db = db
        self._pcloud = pcloud

    # ------------------------------------------------------------------ #
    # Registration
    # ------------------------------------------------------------------ #

    def register(
        self,
        model_path: Path | str,
        model_id: str,
        family: str,
        metrics: dict[str, Any],
        feature_set_version: str = "v1",
        artifact_uri: Optional[str] = None,
    ) -> str:
        """Register a model as a *candidate* in the registry.

        Args:
            model_path: local path to the saved model artefact (for upload).
            model_id: unique identifier (e.g. ``lgbm_20240101_abc123``).
            family: model family name (e.g. ``lgbm_binary``).
            metrics: dict of evaluation metrics (AUC, n_train, …).
            feature_set_version: feature schema version used during training.
            artifact_uri: override pCloud URI (skip upload when provided).

        Returns:
            The ``model_id`` string.
        """
        model_path = Path(model_path)
        remote = artifact_uri

        if remote is None:
            remote_path = f"/models/{family}/{model_id}.pkl"
            try:
                result = self._pcloud.upload_file(model_path, remote_path)
                remote = result.get("remote") or remote_path
            except Exception as exc:
                logger.warning("pCloud upload failed (%s); storing local path", exc)
                remote = str(model_path)

        row = {
            "model_id": model_id,
            "family": family,
            "feature_set_version": feature_set_version,
            "metrics": metrics,
            "artifact_uri": remote,
            "status": "candidate",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._db.insert("model_versions", [row])
        logger.info("Registered candidate model: %s (family=%s)", model_id, family)
        return model_id

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #

    def get_champion(self, family: str) -> Optional[dict]:
        """Return the current champion model record for *family*, or None."""
        rows = self._db.select(
            "model_versions",
            filters={"family": family, "status": "champion"},
            limit=10,
        )
        if not rows:
            return None
        # pick the most recently created champion
        try:
            rows = sorted(rows, key=lambda r: r.get("created_at", ""), reverse=True)
        except TypeError:
            pass
        return rows[0]

    def list_candidates(self, family: str) -> list[dict]:
        """Return all *candidate* model records for *family*."""
        return self._db.select(
            "model_versions",
            filters={"family": family, "status": "candidate"},
            limit=100,
        )

    # ------------------------------------------------------------------ #
    # Promotion
    # ------------------------------------------------------------------ #

    def promote(self, candidate_id: str, reason: str = "") -> bool:
        """Promote *candidate_id* to champion; retire the previous champion.

        Returns True on success.
        """
        # verify candidate exists
        rows = self._db.select("model_versions", filters={"model_id": candidate_id})
        if not rows:
            logger.error("Cannot promote — model_id not found: %s", candidate_id)
            return False

        row = rows[0]
        family = row.get("family", "")

        # retire existing champion(s) for this family
        existing = self._db.select(
            "model_versions",
            filters={"family": family, "status": "champion"},
        )
        for champ in existing:
            self._db.update(
                "model_versions",
                match={"model_id": champ["model_id"]},
                values={"status": "retired"},
            )

        # promote candidate
        self._db.update(
            "model_versions",
            match={"model_id": candidate_id},
            values={"status": "champion"},
        )

        # record in promotions log
        self._db.insert("model_promotions", [{
            "model_id": candidate_id,
            "promoted_by": "system",
            "reason": reason,
            "promoted_at": datetime.now(timezone.utc).isoformat(),
        }])

        logger.info("Promoted model %s to champion (family=%s)", candidate_id, family)
        return True

    # ------------------------------------------------------------------ #
    # Download
    # ------------------------------------------------------------------ #

    def download_model(self, model_id: str, local_dir: Path | str) -> Path:
        """Download model artefact from pCloud (or copy from local path).

        Returns the local path to the model file.
        """
        local_dir = Path(local_dir)
        local_dir.mkdir(parents=True, exist_ok=True)
        dest = local_dir / f"{model_id}.pkl"

        if dest.exists():
            logger.debug("Model already cached locally: %s", dest)
            return dest

        rows = self._db.select("model_versions", filters={"model_id": model_id})
        if not rows:
            raise FileNotFoundError(f"model_id not found in registry: {model_id}")

        uri = rows[0].get("artifact_uri", "")
        if not uri:
            raise ValueError(f"No artifact_uri for model: {model_id}")

        # if uri looks like a local path, just copy it
        local_uri = Path(uri)
        if local_uri.exists():
            import shutil
            shutil.copy2(local_uri, dest)
            logger.info("Copied model from local URI: %s -> %s", uri, dest)
            return dest

        # otherwise try pCloud download
        try:
            self._pcloud.download_file(uri, dest)
            logger.info("Downloaded model from pCloud: %s -> %s", uri, dest)
        except Exception as exc:
            raise RuntimeError(f"Failed to download model {model_id} from {uri}: {exc}") from exc

        return dest
