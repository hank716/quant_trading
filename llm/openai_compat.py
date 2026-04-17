from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import requests


class LLMRequestError(RuntimeError):
    """Raised when an LLM request fails and cannot be recovered."""


class LLMRateLimitError(LLMRequestError):
    """Raised when the upstream LLM provider keeps returning 429."""


_REQUEST_LOCK = threading.Lock()
_LAST_REQUEST_TS = 0.0
_RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _throttle(min_interval_seconds: float) -> None:
    global _LAST_REQUEST_TS
    if min_interval_seconds <= 0:
        return

    with _REQUEST_LOCK:
        now = time.monotonic()
        elapsed = now - _LAST_REQUEST_TS
        remaining = min_interval_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)
        _LAST_REQUEST_TS = time.monotonic()


def _parse_retry_after_seconds(response: requests.Response) -> float | None:
    retry_after = response.headers.get("Retry-After")
    if not retry_after:
        return None
    try:
        return max(0.0, float(retry_after))
    except ValueError:
        return None


def _cache_path(cache_dir: Path, namespace: str, cache_key_payload: dict[str, Any]) -> Path:
    encoded = json.dumps(
        cache_key_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return cache_dir / namespace / f"{digest}.json"


def _read_cache(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def request_chat_completion(
    *,
    api_key: str,
    base_url: str,
    request_body: dict[str, Any],
    timeout: int,
    cache_namespace: str,
    cache_key_payload: dict[str, Any],
    use_cache: bool | None = None,
    cache_dir: str | None = None,
    min_interval_seconds: float | None = None,
    max_retries: int | None = None,
    retry_backoff_seconds: float | None = None,
) -> dict[str, Any]:
    effective_use_cache = env_bool("LLM_CACHE_ENABLED", True) if use_cache is None else use_cache
    effective_cache_dir = Path(cache_dir or os.getenv("LLM_CACHE_DIR", ".cache/llm"))
    effective_min_interval = (
        _env_float("LLM_MIN_INTERVAL_SECONDS", 3.0)
        if min_interval_seconds is None
        else float(min_interval_seconds)
    )
    effective_max_retries = _env_int("LLM_MAX_RETRIES", 4) if max_retries is None else int(max_retries)
    effective_backoff = (
        _env_float("LLM_RETRY_BACKOFF_SECONDS", 2.0)
        if retry_backoff_seconds is None
        else float(retry_backoff_seconds)
    )

    cache_path = _cache_path(effective_cache_dir, cache_namespace, cache_key_payload)
    if effective_use_cache:
        cached = _read_cache(cache_path)
        if cached is not None:
            return cached

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_error: Exception | None = None
    for attempt in range(effective_max_retries + 1):
        _throttle(effective_min_interval)
        try:
            response = requests.post(url, headers=headers, json=request_body, timeout=timeout)
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= effective_max_retries:
                raise LLMRequestError(f"LLM request failed after retries: {exc}") from exc
            time.sleep(effective_backoff * (2 ** attempt))
            continue

        if response.status_code in _RETRYABLE_STATUS_CODES:
            if response.status_code == 429:
                last_error = LLMRateLimitError("LLM provider returned 429 Too Many Requests")
            else:
                last_error = LLMRequestError(
                    f"LLM provider temporary error: status={response.status_code}"
                )

            if attempt >= effective_max_retries:
                raise last_error

            retry_after_seconds = _parse_retry_after_seconds(response)
            wait_seconds = retry_after_seconds or (effective_backoff * (2 ** attempt))
            time.sleep(max(wait_seconds, effective_backoff))
            continue

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            body_snippet = response.text[:400].replace("\n", " ")
            raise LLMRequestError(
                f"LLM request failed with status={response.status_code}: {body_snippet}"
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise LLMRequestError("LLM response was not valid JSON") from exc

        if effective_use_cache:
            _write_cache(cache_path, payload)
        return payload

    raise LLMRequestError(f"LLM request failed after retries: {last_error}")


def extract_message_content(response_payload: dict[str, Any]) -> str:
    choices = response_payload.get("choices", [])
    if not choices:
        raise LLMRequestError(f"Unexpected LLM response: {response_payload}")

    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            text = item.get("text") or item.get("content")
            if text:
                parts.append(str(text))
        return "\n".join(part.strip() for part in parts if part).strip()

    return str(content).strip()
