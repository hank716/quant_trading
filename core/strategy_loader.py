from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from core.models import ProfileConfig, StrategyConfig


class StrategyLoaderError(ValueError):
    pass


class StrategyLoader:
    @staticmethod
    def _read_yaml(path: str | Path) -> dict[str, Any]:
        file_path = Path(path)
        if not file_path.exists():
            raise StrategyLoaderError(f"YAML file not found: {file_path}")
        with file_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            raise StrategyLoaderError(f"Top-level YAML must be a mapping: {file_path}")
        return data

    @classmethod
    def load_strategy(cls, path: str | Path) -> StrategyConfig:
        payload = cls._read_yaml(path)
        try:
            return StrategyConfig.model_validate(payload)
        except Exception as exc:
            raise StrategyLoaderError(f"Invalid strategy schema in {path}: {exc}") from exc

    @classmethod
    def load_profile(cls, path: str | Path) -> ProfileConfig:
        payload = cls._read_yaml(path)
        try:
            return ProfileConfig.model_validate(payload)
        except Exception as exc:
            raise StrategyLoaderError(f"Invalid profile schema in {path}: {exc}") from exc

    @classmethod
    def load_portfolio(cls, path: str | Path) -> dict[str, dict[str, Any]]:
        payload = cls._read_yaml(path)

        if "holdings" in payload and isinstance(payload["holdings"], dict):
            raw_holdings = payload["holdings"]
        elif all(isinstance(k, str) for k in payload.keys()):
            raw_holdings = payload
        else:
            raise StrategyLoaderError(
                "Portfolio YAML must either be a mapping or contain a 'holdings' mapping."
            )

        normalized: dict[str, dict[str, Any]] = {}
        for raw_stock_id, raw_value in raw_holdings.items():
            stock_id = str(raw_stock_id)
            if isinstance(raw_value, dict):
                entry = dict(raw_value)
                asset_type = entry.get("asset_type") or entry.get("type") or "Unknown"
                normalized[stock_id] = {
                    "name": str(entry.get("name", stock_id)),
                    "asset_type": str(asset_type),
                    "shares": entry.get("shares"),
                    "avg_cost": entry.get("avg_cost"),
                    "note": entry.get("note"),
                }
            else:
                normalized[stock_id] = {
                    "name": stock_id,
                    "asset_type": str(raw_value),
                    "shares": None,
                    "avg_cost": None,
                    "note": None,
                }
        return normalized
