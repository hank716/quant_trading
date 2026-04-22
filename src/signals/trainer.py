"""LightGBM walk-forward trainer for the Taiwan quant signal model."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

logger = logging.getLogger(__name__)

_DEFAULT_LGB_PARAMS: dict[str, Any] = {
    "objective": "binary",
    "metric": "auc",
    "num_leaves": 31,
    "learning_rate": 0.05,
    "n_estimators": 100,
    "min_child_samples": 5,
    "verbosity": -1,
    "random_state": 42,
}


def walk_forward_split(
    df: pd.DataFrame,
    date_col: str,
    n_splits: int = 3,
) -> list[tuple[list, list]]:
    """Generate time-ordered (train_indices, val_indices) pairs.

    Each fold trains on everything before a cut-off date and validates on
    the next equal-sized period. Indices are positional (iloc-compatible).

    Args:
        df: DataFrame containing ``date_col``.
        date_col: column name for the date dimension.
        n_splits: number of walk-forward folds.

    Returns:
        List of ``(train_idx, val_idx)`` integer-position lists.
    """
    if df.empty or n_splits < 1:
        return []

    sorted_df = df.sort_values(date_col).reset_index(drop=True)
    n = len(sorted_df)
    fold_size = max(1, n // (n_splits + 1))

    splits = []
    for i in range(n_splits):
        train_end = (i + 1) * fold_size
        val_end = min((i + 2) * fold_size, n)
        if train_end >= n or val_end <= train_end:
            break
        splits.append((list(range(train_end)), list(range(train_end, val_end))))

    return splits


def train(
    feature_matrix: pd.DataFrame,
    label: pd.Series,
    params: dict[str, Any] | None = None,
    output_dir: Path | str = "workspace/runs/models",
) -> tuple[Any, dict[str, Any]]:
    """Train a LightGBM binary classifier on ``feature_matrix``.

    Uses the last 20 % of rows as validation (time-ordered split).

    Args:
        feature_matrix: DataFrame indexed by (trade_date, instrument) or flat.
        label: binary Series aligned to ``feature_matrix`` index.
        params: LightGBM / LGBMClassifier kwargs (merged with defaults).
        output_dir: where to persist the model (not saved here; use save_model).

    Returns:
        (model, metrics) where metrics contains ``auc``, ``n_train``, ``n_val``.
    """
    import lightgbm as lgb
    from sklearn.metrics import roc_auc_score

    lgb_params = {**_DEFAULT_LGB_PARAMS, **(params or {})}

    # Align label → features, drop NaN labels
    X = feature_matrix.copy().fillna(0.0)
    y = label.reindex(X.index).dropna()
    X = X.loc[y.index]
    y = y.astype(int)

    if len(X) < 10:
        raise ValueError(f"Too few labelled samples to train: {len(X)}")

    n_val = max(1, int(len(X) * 0.2))
    X_train, X_val = X.iloc[:-n_val], X.iloc[-n_val:]
    y_train, y_val = y.iloc[:-n_val], y.iloc[-n_val:]

    model = lgb.LGBMClassifier(**lgb_params)
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        callbacks=[lgb.log_evaluation(period=-1)],
    )

    y_pred_proba = model.predict_proba(X_val)[:, 1]
    if len(y_val.unique()) > 1:
        auc = round(float(roc_auc_score(y_val, y_pred_proba)), 4)
    else:
        auc = float("nan")
        logger.warning("AUC undefined — validation set has only one class")

    metrics: dict[str, Any] = {
        "auc": auc,
        "n_train": int(len(X_train)),
        "n_val": int(len(X_val)),
        "n_features": int(X.shape[1]),
        "positive_rate": round(float(y.mean()), 4),
    }
    logger.info("Training complete: %s", metrics)
    return model, metrics


def save_model(
    model: Any,
    model_id: str,
    output_dir: Path | str,
) -> Path:
    """Persist model to ``{output_dir}/{model_id}.pkl`` via joblib.

    Returns the saved path.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{model_id}.pkl"
    joblib.dump(model, path)
    logger.info("Model saved: %s", path)
    return path
