from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests

from core.models import DailyResult, DiscordConfig


class DiscordNotifierError(RuntimeError):
    pass


class DiscordNotifier:
    def __init__(self, config: DiscordConfig):
        self.config = config

    def resolve_webhook_url(self) -> str | None:
        if self.config.webhook_url:
            return self.config.webhook_url
        if self.config.webhook_url_env:
            return os.getenv(self.config.webhook_url_env)
        return None

    def is_enabled(self) -> bool:
        return bool(self.config.enabled and self.resolve_webhook_url())

    def build_message_content(self, result: DailyResult, markdown_text: str | None = None) -> str:
        consider_assets = "、".join(candidate.asset for candidate in result.eligible_candidates[:5]) or "無"
        watch_assets = "、".join(candidate.asset for candidate in result.watch_only_candidates[:8]) or "無"
        lines = [
            self.config.mention_text or "",
            "📘 **每日選股報告**",
            f"- 日期：{result.date}",
            f"- 產生時間：{result.generated_at or '未提供'}",
            f"- 使用者：{result.profile_display_name or result.profile_name or '未提供'}",
            f"- 策略：{result.strategy}",
            f"- 動作：{'可進一步研究' if result.action == 'consider' else '先觀察'}",
            f"- Consider：{len(result.eligible_candidates)} 檔（{consider_assets}）",
            f"- Watch：{len(result.watch_only_candidates)} 檔（{watch_assets}）",
        ]
        if markdown_text and self.config.include_report_body:
            lines.extend(["", "---", ""])
            lines.append(markdown_text[: self.config.max_report_chars].strip())
            if len(markdown_text) > self.config.max_report_chars:
                lines.append("\n（內容過長，完整版本請看附件 Markdown 檔。）")
        return "\n".join(line for line in lines if line is not None).strip()

    def send(self, result: DailyResult, markdown_path: Path, json_path: Path) -> dict[str, Any]:
        webhook_url = self.resolve_webhook_url()
        if not self.config.enabled:
            return {"status": "disabled", "reason": "discord disabled in profile"}
        if not webhook_url:
            return {"status": "skipped", "reason": "webhook url missing"}

        markdown_text = markdown_path.read_text(encoding="utf-8") if markdown_path.exists() else None
        content = self.build_message_content(result, markdown_text=markdown_text)
        payload = {
            "content": content,
            "allowed_mentions": {"parse": []},
        }
        if self.config.username:
            payload["username"] = self.config.username
        if self.config.avatar_url:
            payload["avatar_url"] = self.config.avatar_url

        files: dict[str, Any] = {}
        handles = []
        try:
            if self.config.include_markdown_file and markdown_path.exists():
                markdown_handle = markdown_path.open("rb")
                handles.append(markdown_handle)
                files["files[0]"] = (markdown_path.name, markdown_handle, "text/markdown")
            if self.config.include_json_file and json_path.exists():
                json_handle = json_path.open("rb")
                handles.append(json_handle)
                files[f"files[{len(files)}]"] = (json_path.name, json_handle, "application/json")

            if files:
                response = requests.post(
                    webhook_url,
                    params={"wait": "true"},
                    data={"payload_json": json.dumps(payload, ensure_ascii=False)},
                    files=files,
                    timeout=30,
                )
            else:
                response = requests.post(
                    webhook_url,
                    params={"wait": "true"},
                    json=payload,
                    timeout=30,
                )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise DiscordNotifierError(f"Discord webhook send failed: {exc}") from exc
        finally:
            for handle in handles:
                handle.close()

        body: dict[str, Any] = {}
        try:
            body = response.json() if response.content else {}
        except ValueError:
            body = {}

        return {
            "status": "sent",
            "message_id": body.get("id"),
            "channel_id": body.get("channel_id"),
        }
