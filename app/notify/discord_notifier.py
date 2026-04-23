"""Discord notifier for Qlib pipeline results."""
from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any

import requests

logger = logging.getLogger(__name__)


def build_message(
    candidates: list[dict],
    run_id: str | None,
    metrics: dict[str, float],
    trade_date: date,
) -> str:
    """Build Discord message with candidate list and Qlib metrics."""
    lines = [f"📊 **fin 選股報告 {trade_date}**"]
    if run_id:
        lines.append(f"MLflow run: `{run_id[:8]}…`")

    metric_parts = []
    for key in ["IC", "Rank IC", "Sharpe", "MDD"]:
        if key in metrics:
            val = metrics[key]
            metric_parts.append(f"{key}: `{val:.4f}`")
    if metric_parts:
        lines.append("  ".join(metric_parts))

    lines.append("")
    if not candidates:
        lines.append("⚠️ 今日無候選標的")
    else:
        lines.append(f"**Top {min(len(candidates), 10)} 候選：**")
        for i, c in enumerate(candidates[:10], 1):
            ticker = c.get("instrument", "?")
            score = c.get("score", 0.0)
            thesis = c.get("thesis", "")
            thesis_short = thesis[:60] + "…" if len(thesis) > 60 else thesis
            line = f"{i}. `{ticker}` score={score:.4f}"
            if thesis_short:
                line += f" — {thesis_short}"
            lines.append(line)

    return "\n".join(lines)


class QlibDiscordNotifier:
    """Discord notifier for the Qlib pipeline (Phase 10+)."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._webhook_url: str | None = None
        url = config.get("webhook_url")
        if url:
            self._webhook_url = url
        else:
            env_key = config.get("webhook_url_env")
            if env_key:
                self._webhook_url = os.getenv(env_key)

    def is_enabled(self) -> bool:
        """Return True if Discord is enabled and a webhook URL is configured."""
        return bool(self._config.get("enabled", False) and self._webhook_url)

    def send(self, content: str) -> dict:
        """Send a message to Discord. Returns status dict."""
        if not self.is_enabled():
            logger.info("Discord notifier disabled or no webhook URL")
            return {"status": "skipped"}
        try:
            resp = requests.post(
                self._webhook_url,
                json={"content": content[:2000]},
                timeout=10,
            )
            resp.raise_for_status()
            logger.info("Discord message sent (status %d)", resp.status_code)
            return {"status": "ok", "http_status": resp.status_code}
        except Exception as exc:
            logger.warning("Discord send failed: %s", exc)
            return {"status": "error", "error": str(exc)}
