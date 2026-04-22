"""SHAP-based feature importance explainer for LightGBM models.

Computes mean absolute SHAP values per feature and writes a ranked summary
JSON suitable for Streamlit visualisation and pCloud archiving.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_shap_summary(
    model: Any,
    feature_matrix: pd.DataFrame,
    top_n: int = 10,
) -> dict:
    """Compute mean |SHAP| per feature and return a ranked summary.

    Uses ``shap.TreeExplainer`` for tree-based models (LightGBM, XGBoost).
    Falls back to ``shap.Explainer`` if TreeExplainer raises.

    Args:
        model: trained model with a ``predict`` / ``predict_proba`` method.
        feature_matrix: DataFrame of features; rows = samples, cols = feature names.
        top_n: number of top features to include in the summary.

    Returns:
        dict with keys:
          - ``top_features``: list of ``{feature, mean_abs_shap}`` dicts (sorted desc)
          - ``n_samples``: number of samples used
          - ``n_features``: total feature count
    """
    import shap

    if feature_matrix.empty:
        return {"top_features": [], "n_samples": 0, "n_features": 0}

    X = feature_matrix.copy().fillna(0.0)

    try:
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X)
    except Exception as tree_exc:
        logger.warning("TreeExplainer failed (%s); trying generic Explainer", tree_exc)
        try:
            explainer = shap.Explainer(model, X)
            shap_values = explainer(X).values
        except Exception as exc:
            raise RuntimeError(f"SHAP computation failed: {exc}") from exc

    # For binary classifiers shap_values may be a list [neg_class, pos_class]
    if isinstance(shap_values, list):
        shap_arr = np.array(shap_values[1])
    else:
        shap_arr = np.array(shap_values)

    # If 3-D (samples × features × outputs), take the last output
    if shap_arr.ndim == 3:
        shap_arr = shap_arr[:, :, -1]

    mean_abs = np.abs(shap_arr).mean(axis=0)
    feature_names = list(feature_matrix.columns)

    ranked = sorted(
        zip(feature_names, mean_abs.tolist()),
        key=lambda x: x[1],
        reverse=True,
    )

    top = [{"feature": f, "mean_abs_shap": round(v, 6)} for f, v in ranked[:top_n]]

    return {
        "top_features": top,
        "n_samples": int(len(X)),
        "n_features": int(len(feature_names)),
    }


def write_shap_summary(
    summary: dict,
    run_id: str,
    output_dir: Optional[Path | str] = None,
) -> Path:
    """Write SHAP summary dict to ``{output_dir}/{run_id}/shap_summary.json``.

    Args:
        summary: output of :func:`compute_shap_summary`.
        run_id: pipeline run identifier (used as sub-directory name).
        output_dir: base directory; defaults to ``workspace/runs``.

    Returns:
        Path to the written JSON file.
    """
    base = Path(output_dir or "workspace/runs")
    dest = base / run_id / "shap_summary.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    logger.info("SHAP summary written: %s", dest)
    return dest
